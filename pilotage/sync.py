"""Synchronisation du pipeline Drive « MS PROJETS / 02 - Projets MdB » avec l'application.

Ce script ne lit pas le Drive lui-même : la session quotidienne (voir SYNC.md) liste les
dossiers d'opération avec le connecteur Google Drive et lui passe le résultat.

    python pilotage/sync.py extraire page.html ops.json
        Récupère les opérations embarquées dans une page publiée (état de la veille).

    python pilotage/sync.py appliquer ops.json pipeline.json ops_maj.json [--date AAAA-MM-JJ]
        pipeline.json = [{"dossier": "<id dossier Drive>", "nom": "25.03 MONTMORENCY - GRETRY",
                          "etape": "03 - PV SIGNEE"}, ...]
        - opération connue : met à jour son étape (déplacement de dossier) ;
        - nouveau dossier en 02, 02B, 03 ou 04 : crée l'opération avec les tâches
          que son étape implique (statut déduit, sans validation finale) ;
        - dossier passé en 06 - OUT : l'opération est marquée abandonnée.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ETAPES = ["01 - A L'ETUDE", "02 - OFFRE ENVOYEE", "02B - OFFRE ACCEPTEE", "03 - PV SIGNEE",
          "04 - AAE SIGNEE", "05 - ACHEVES", "06 - OUT"]
ETAPES_SUIVIES = ETAPES[1:]          # étapes suivies (changements d'étape)
ETAPES_CREATION = ETAPES[1:5]        # création d'opération : 02 à 04 seulement (05 et 06 = dossiers clos)

# Tâches réputées faites en arrivant à chaque étape (cumulatif).
FAIT_A = {
    "02 - OFFRE ENVOYEE": ["A01", "A02", "A03", "A04", "A14", "A05"],
    "02B - OFFRE ACCEPTEE": ["A06"],
    "03 - PV SIGNEE": ["A07", "A08", "A09", "A12", "A15", "A16", "A18", "A22", "A28", "A29",
                       "B06", "B07", "B08", "B10"],
    "04 - AAE SIGNEE": ["B14", "B15", "B16", "B17", "B18", "B19", "B20", "B21", "D01", "D02", "D03",
                        "D04", "D05", "D08", "B11", "B13"],
}
EN_COURS_A = {"02 - OFFRE ENVOYEE": ["A06"], "02B - OFFRE ACCEPTEE": ["A07", "B06"],
              "03 - PV SIGNEE": ["B14", "B16"], "04 - AAE SIGNEE": ["F03", "F04"]}
MARQUEUR = re.compile(r'<script type="application/json" id="seed-ops">(.*?)</script>', re.S)


def norm_etape(e: str) -> str:
    e = re.sub(r"\s+", " ", e.strip().upper())
    for ref in ETAPES:
        if e.startswith(ref.split(" - ")[0] + " "):
            return ref
    raise ValueError(f"Étape inconnue : {e}")


def op_id(dossier: str) -> str:
    return "drv-" + dossier


def nom_affiche(nom: str) -> str:
    """« 25.03 MONTMORENCY - GRETRY » → « 25.03 Montmorency – Gretry »."""
    nom = re.sub(r"\s+", " ", nom.strip())
    m = re.match(r"^([\d.]+)\s*-?\s*(.*)$", nom)
    code, reste = (m.group(1), m.group(2)) if m else ("", nom)
    reste = " – ".join(p.strip().title() for p in reste.split(" - ") if p.strip())
    return f"{code} {reste}".strip()


def baseline(etape: str, jour: str) -> dict:
    taches: dict[str, dict] = {}
    if etape in ("05 - ACHEVES",):
        return taches                       # traité via l'étape (opération close)
    rang = ETAPES.index(etape)
    for e in ETAPES[1:rang + 1]:
        for t in FAIT_A.get(e, []):
            taches[t] = {"statut": "Terminé", "comm": f"Statut déduit de l'étape Drive « {e} » ({jour}) ; pièce non revue."}
    for t in EN_COURS_A.get(etape, []):
        taches.setdefault(t, {"statut": "En cours", "comm": f"Étape Drive « {etape} »."})
    return taches


def nouvelle_operation(dossier: dict, jour: str) -> dict:
    etape = norm_etape(dossier["etape"])
    m = re.match(r"^(\d{2})\.(\d{2})", dossier["nom"].strip())
    debut = f"20{m.group(1)}-{m.group(2)}-01" if m and 1 <= int(m.group(2)) <= 12 else jour
    return {"id": op_id(dossier["dossier"]), "dossier": dossier["dossier"], "nom": nom_affiche(dossier["nom"]),
            "adresse": "", "etape": etape, "source": "Drive MS PROJETS (création automatique)",
            "debut": debut, "replan": jour, "maj": jour,
            "typos": ["ACHAT_REVENTE", "LIBRE", "VENTE_UNITE"],
            "taches": baseline(etape, jour),
            "custom": [{"id": "X90", "cat": "A", "sc": "Spécifique opération", "drive": True,
                        "nom": "Compléter la fiche de l'opération", "crit": "Important", "statut": "À faire",
                        "desc": "Opération créée automatiquement depuis le Drive : vérifier les typologies, l'adresse et les statuts déduits de l'étape.",
                        "resp": ["MDB"], "decl": "Création automatique", "dep": [], "risque": "Checklist inadaptée à l'opération.",
                        "docs": [], "typo": [], "duree": 2}]}


def appliquer(ops: list[dict], pipeline: list[dict], jour: str) -> tuple[list[dict], list[str]]:
    par_dossier = {o.get("dossier"): o for o in ops if o.get("dossier")}
    journal: list[str] = []
    for d in pipeline:
        etape = norm_etape(d["etape"])
        o = par_dossier.get(d["dossier"])
        if o is None:
            if etape not in ETAPES_CREATION:
                continue
            o = nouvelle_operation(d, jour)
            ops.append(o)
            par_dossier[d["dossier"]] = o
            journal.append(f"Nouvelle opération : {o['nom']} ({etape})")
            continue
        if o.get("etape") != etape:
            journal.append(f"{o['nom']} : {o.get('etape')} → {etape}")
            avant = o.get("etape")
            o["etape"] = etape
            o["maj"] = jour
            if avant in ETAPES and ETAPES.index(etape) > ETAPES.index(avant) and etape != "06 - OUT":
                for tid, t in baseline(etape, jour).items():
                    cur = o["taches"].get(tid, {})
                    if cur.get("statut", "À faire") in ("À faire", "En cours"):
                        o["taches"][tid] = t
    return ops, journal


def extraire(page: str) -> list[dict]:
    m = MARQUEUR.search(page)
    if not m:
        raise SystemExit("Bloc des opérations introuvable dans la page")
    return json.loads(m.group(1).replace("<\\/", "</"))


def main(argv: list[str]) -> None:
    if len(argv) >= 3 and argv[0] == "extraire":
        ops = extraire(Path(argv[1]).read_text(encoding="utf-8"))
        Path(argv[2]).write_text(json.dumps(ops, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(ops)} opération(s) extraite(s)")
        return
    if len(argv) >= 4 and argv[0] == "appliquer":
        jour = argv[argv.index("--date") + 1] if "--date" in argv else date.today().isoformat()
        ops = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        pipeline = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        ops, journal = appliquer(ops, pipeline, jour)
        Path(argv[3]).write_text(json.dumps(ops, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n".join(journal) or "Aucun changement de pipeline")
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
