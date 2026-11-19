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


def _sync():
    s = importlib.util.spec_from_file_location("sync_pilotage", RACINE / "pilotage" / "sync.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_sync_cree_les_nouvelles_operations_a_partir_de_02():
    sync = _sync()
    pipeline = [{"dossier": "A1", "nom": "26.11 NOGENT - TEST", "etape": "02 - OFFRE ENVOYEE"},
                {"dossier": "A2", "nom": "26.11 VIEUX", "etape": "06 - OUT"},
                {"dossier": "A3", "nom": "26.11 PV", "etape": "03 - PV SIGNEE"}]
    ops, journal = sync.appliquer([], pipeline, "2026-11-20")
    ids = {o["id"] for o in ops}
    assert ids == {"drv-A1", "drv-A3"}
    pv = next(o for o in ops if o["id"] == "drv-A3")
    assert pv["taches"]["B08"]["statut"] == "Terminé" and pv["debut"] == "2026-11-01"
    assert all(t in REF_IDS for o in ops for t in o["taches"])


def test_sync_change_d_etape_sans_ecraser_le_termine():
    sync = _sync()
    op = sync.nouvelle_operation({"dossier": "B1", "nom": "25.01 X", "etape": "02 - OFFRE ENVOYEE"}, "2026-01-02")
    op["taches"]["B08"] = {"statut": "Bloqué"}
    ops, _ = sync.appliquer([op], [{"dossier": "B1", "nom": "25.01 X", "etape": "04 - AAE SIGNEE"}], "2026-11-20")
    assert ops[0]["etape"] == "04 - AAE SIGNEE" and ops[0]["maj"] == "2026-11-20"
    assert ops[0]["taches"]["B08"]["statut"] == "Bloqué"          # statut posé ailleurs conservé
    assert ops[0]["taches"]["B19"]["statut"] == "Terminé"


def test_sync_extraire_relit_la_page_construite():
    sync = _sync()
    op = sync.nouvelle_operation({"dossier": "C1", "nom": "26.02 Y </script>", "etape": "03 - PV SIGNEE"}, "2026-11-20")
    page = build.construire_html(REF, [op])
    assert sync.extraire(page)[0]["nom"] == op["nom"]


REF_IDS = {t["id"] for t in REF["taches"]} | {"X90"}
