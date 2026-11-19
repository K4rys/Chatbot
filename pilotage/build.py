"""Construit l'application de pilotage et les exports Notion / Airtable.

    python pilotage/build.py

Entrée  : pilotage/referentiel.json (source unique, modifiable) + pilotage/app.html (gabarit).
Sorties : pilotage/index.html (application autonome, s'ouvre sans serveur)
          pilotage/export/*.csv (import Notion / Airtable)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ICI = Path(__file__).resolve().parent
REFERENTIEL = ICI / "referentiel.json"
GABARIT = ICI / "app.html"
SORTIE_HTML = ICI / "index.html"
EXPORT = ICI / "export"
MARQUEUR = "/*__REFERENTIEL__*/null"
MARQUEUR_OPS = "/*__OPERATIONS__*/[]"

CHAMPS_OBLIGATOIRES = ("id", "cat", "sc", "nom", "desc", "resp", "dep", "crit", "risque", "typo", "duree")


def charger(chemin: Path = REFERENTIEL) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def valider(ref: dict) -> list[str]:
    """Renvoie la liste des erreurs de cohérence (vide si le référentiel est sain)."""
    erreurs: list[str] = []
    taches = ref["taches"]
    ids = [t.get("id") for t in taches]
    doublons = {i for i in ids if ids.count(i) > 1}
    if doublons:
        erreurs.append(f"ID en double : {sorted(doublons)}")
    par_id = {t["id"]: t for t in taches}
    cats = {c["code"] for c in ref["categories"]}
    typos = {t["code"] for t in ref["typologies"]}
    groupes = {g["code"] for g in ref["groupes_typologies"]}
    for code, membres in ref["alias"].items():
        for m in membres:
            if m not in typos:
                erreurs.append(f"Alias {code} : typologie inconnue {m}")
    for t in ref["typologies"]:
        if t["groupe"] not in groupes:
            erreurs.append(f"Typologie {t['code']} : groupe inconnu {t['groupe']}")
    for t in taches:
        for champ in CHAMPS_OBLIGATOIRES:
            if champ not in t:
                erreurs.append(f"{t.get('id')} : champ manquant {champ}")
        if t.get("cat") not in cats:
            erreurs.append(f"{t['id']} : catégorie inconnue {t.get('cat')}")
        if t.get("crit") not in ref["criticites"]:
            erreurs.append(f"{t['id']} : criticité inconnue {t.get('crit')}")
        for d in t.get("dep", []):
            if d not in par_id:
                erreurs.append(f"{t['id']} : dépendance inconnue {d}")
        for c in t.get("typo", []):
            if c not in typos and c not in ref["alias"]:
                erreurs.append(f"{t['id']} : typologie inconnue {c}")
    for j in ref["jalons"]:
        if j["tache"] not in par_id:
            erreurs.append(f"Jalon {j['code']} : tâche inconnue {j['tache']}")
    # cycles
    etat: dict[str, int] = {}

    def visiter(i: str, pile: list[str]) -> None:
        if etat.get(i) == 2:
            return
        if etat.get(i) == 1:
            erreurs.append("Cycle de dépendances : " + " → ".join(pile + [i]))
            return
        etat[i] = 1
        for d in par_id.get(i, {}).get("dep", []):
            if d in par_id:
                visiter(d, pile + [i])
        etat[i] = 2

    for i in par_id:
        visiter(i, [])
    return erreurs


def _js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def construire_html(ref: dict, operations: list[dict] | None = None) -> str:
    """Gabarit + référentiel ; `operations` = opérations préchargées (au format de la sauvegarde JSON)."""
    gabarit = GABARIT.read_text(encoding="utf-8")
    if MARQUEUR not in gabarit or MARQUEUR_OPS not in gabarit:
        raise ValueError("Marqueur absent du gabarit")
    return gabarit.replace(MARQUEUR, _js(ref)).replace(MARQUEUR_OPS, _js(operations or []))


def page_autonome(fragment: str) -> str:
    return ('<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
            "body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n"
            "</head>\n<body>\n" + fragment + "\n</body>\n</html>\n")


def exporter_csv(ref: dict) -> None:
    EXPORT.mkdir(exist_ok=True)
    cats = {c["code"]: c["nom"] for c in ref["categories"]}
    jalons = {j["tache"]: j for j in ref["jalons"]}
    typos = {t["code"]: t["nom"] for t in ref["typologies"]}

    def noms_typo(codes: list[str]) -> str:
        if not codes:
            return "Toutes"
        out: list[str] = []
        for c in codes:
            for m in ref["alias"].get(c, [c]):
                if typos[m] not in out:
                    out.append(typos[m])
        return ", ".join(out)

    with (EXPORT / "taches.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Tâche", "Catégorie", "Sous-catégorie", "Description", "Responsable", "Déclenchement",
                    "Dépendances", "Criticité", "Risque si oubli", "Documents", "Typologies", "Durée (j)", "Jalon",
                    "Pratique terrain", "À vérifier", "Statut", "Date cible", "Date réelle", "Commentaires",
                    "Validation finale"])
        for t in ref["taches"]:
            j = jalons.get(t["id"])
            w.writerow([t["id"], t["nom"], f"{t['cat']} · {cats[t['cat']]}", t["sc"], t["desc"], ", ".join(t["resp"]),
                        t.get("decl", ""), ", ".join(t["dep"]), t["crit"], t["risque"], ", ".join(t.get("docs", [])),
                        noms_typo(t["typo"]), t["duree"], f"{j['code']} {j['nom']}" if j else "",
                        t.get("conseil", ""), "Oui" if t.get("verif") else "Non", "À faire", "", "", "", "Non"])
    with (EXPORT / "typologies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        groupes = {g["code"]: g for g in ref["groupes_typologies"]}
        w.writerow(["Code", "Typologie", "Groupe", "Choix", "Nombre de tâches spécifiques"])
        for t in ref["typologies"]:
            n = sum(1 for x in ref["taches"]
                    if any(t["code"] in ref["alias"].get(c, [c]) for c in x["typo"]))
            g = groupes[t["groupe"]]
            w.writerow([t["code"], t["nom"], g["nom"], g["choix"], n])
    with (EXPORT / "jalons.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Code", "Jalon", "Tâche", "Catégorie"])
        par_id = {t["id"]: t for t in ref["taches"]}
        for j in ref["jalons"]:
            t = par_id[j["tache"]]
            w.writerow([j["code"], j["nom"], f"{t['id']} {t['nom']}", cats[t["cat"]]])


def main() -> None:
    """Sans argument : build du dépôt. Avec `--operation op.json --sortie page.html` : page préchargée
    d'opérations réelles, à générer hors du dépôt (données confidentielles)."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--operation", action="append", default=[], help="JSON d'une opération à précharger")
    ap.add_argument("--sortie", help="Fichier HTML (fragment) à produire avec les opérations")
    args = ap.parse_args()
    ref = charger()
    erreurs = valider(ref)
    if erreurs:
        raise SystemExit("Référentiel incohérent :\n- " + "\n- ".join(erreurs))
    if args.operation:
        if not args.sortie:
            raise SystemExit("--sortie est obligatoire avec --operation")
        ops = [json.loads(Path(f).read_text(encoding="utf-8")) for f in args.operation]
        Path(args.sortie).write_text(construire_html(ref, ops), encoding="utf-8")
        print(f"{len(ops)} opération(s) préchargée(s) → {args.sortie}")
        return
    fragment = construire_html(ref)
    SORTIE_HTML.write_text(page_autonome(fragment), encoding="utf-8")
    exporter_csv(ref)
    print(f"{len(ref['taches'])} tâches, {len(ref['typologies'])} typologies, {len(ref['jalons'])} jalons")
    print(f"→ {SORTIE_HTML.relative_to(ICI.parent)} et {EXPORT.relative_to(ICI.parent)}/*.csv")


if __name__ == "__main__":
    main()
