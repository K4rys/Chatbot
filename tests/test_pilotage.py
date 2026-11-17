"""Cohérence du référentiel de pilotage MDB et de l'application générée."""

import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_pilotage", RACINE / "pilotage" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
REF = build.charger()


def test_referentiel_sans_erreur():
    assert build.valider(REF) == []


def test_toutes_les_categories_ont_des_taches():
    cats = {t["cat"] for t in REF["taches"]}
    assert cats == {c["code"] for c in REF["categories"]}


def test_les_huit_jalons_demandes_existent():
    noms = [j["nom"] for j in REF["jalons"]]
    assert len(noms) == 8
    for attendu in ("Promesse", "conditions suspensives", "Acte authentique", "Autorisations purgées",
                    "commercialisation", "Premières ventes", "Remboursement", "Clôture"):
        assert any(attendu in n for n in noms), attendu


def test_chaque_typologie_est_utilisee_ou_generique():
    utilisees = set()
    for t in REF["taches"]:
        for c in t["typo"]:
            utilisees.update(REF["alias"].get(c, [c]))
    generiques = {"ACHAT_REVENTE", "LIBRE", "VENTE_UNITE", "FONDS_PROPRES", "DECOUPE"}
    for t in REF["typologies"]:
        assert t["code"] in utilisees or t["code"] in generiques, t["code"]


def test_validation_detecte_cycle_et_dependance_inconnue():
    import copy
    ref = copy.deepcopy(REF)
    ref["taches"][0]["dep"] = ["I08"]          # A01 dépend de la clôture → cycle
    ref["taches"][1]["dep"] = ["ZZ99"]
    erreurs = build.valider(ref)
    assert any("Cycle" in e for e in erreurs)
    assert any("ZZ99" in e for e in erreurs)


def test_html_embarque_le_referentiel():
    html = build.construire_html(REF)
    assert build.MARQUEUR not in html
    assert '"id":"I08"' in html
