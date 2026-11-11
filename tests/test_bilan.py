"""Compare le moteur Python aux valeurs du classeur 07_Bilan_operation.xlsx
recalculé par LibreOffice avec ses hypothèses d'exemple."""

import pytest

from app.bilan import Hypotheses, bilan, prix_max, sensibilites, tresorerie

EXEMPLE = Hypotheses(
    surface_vendable_m2=120, prix_sortie_m2=6500, autres_recettes=0,
    prix_acquisition=520000, frais_acquisition_pct=0.03,
    travaux_ht=90000, aleas_travaux_pct=0.10, mois_debut_travaux=2, mois_fin_travaux=6,
    honoraires_etudes=12000, frais_commercialisation_pct=0, portage=6000, tva_nette=0,
    quotite_financee_pct=0.8, taux_interet_annuel=0.055, frais_dossier_garantie_pct=0.015,
    duree_mois=12, marge_cible_pct=0.15,
)

approx = lambda v: pytest.approx(v, abs=0.01)  # noqa: E731


def test_bilan_identique_excel():
    b = bilan(EXEMPLE)
    assert b["chiffre_affaires"] == approx(780000)
    assert b["frais_acquisition"] == approx(15600)
    assert b["travaux_avec_aleas"] == approx(99000)
    assert b["montant_credit"] == approx(507680)
    assert b["frais_financiers"] == approx(35537.6)
    assert b["cout_revient_total"] == approx(688137.6)
    assert b["marge_nette_avant_is"] == approx(91862.4)
    assert b["fonds_propres_mobilises"] == approx(180457.6)
    assert b["rentabilite_fonds_propres"] == pytest.approx(0.509052541982161)


def test_prix_max_identique_excel():
    p = prix_max(EXEMPLE)
    assert p["marge_cible"] == approx(117000)
    assert p["coefficient_financement"] == pytest.approx(1.056)
    assert p["prix_acquisition_maximal_hors_frais"] == approx(496888.79082083)
    assert p["marge_negociation"] == approx(23111.2091791704)
    assert p["marge_negociation_pct"] == pytest.approx(0.0444446330368662)


def test_prix_max_donne_bien_la_marge_cible():
    p = prix_max(EXEMPLE)
    h = Hypotheses(**{**EXEMPLE.__dict__, "prix_acquisition": p["prix_acquisition_maximal_hors_frais"]})
    assert bilan(h)["marge_sur_ca"] == pytest.approx(0.15)


def test_sensibilites_identiques_excel():
    s = sensibilites(EXEMPLE)
    excel = {
        -0.15: [-25137.6, -35592, -46046.4, -56500.8],
        -0.10: [13862.4, 3408, -7046.4, -17500.8],
        -0.05: [52862.4, 42408, 31953.6, 21499.2],
        0.0: [91862.4, 81408, 70953.6, 60499.2],
        0.05: [130862.4, 120408, 109953.6, 99499.2],
    }
    for ligne in s["matrice_prix_x_travaux"]:
        assert list(ligne["marges"].values()) == [approx(v) for v in excel[ligne["variation_prix_sortie"]]]
    assert [a["marge"] for a in s["allongement_duree"]] == [approx(v) for v in (91862.4, 83381.8, 74901.2, 57940)]


def test_tresorerie_identique_excel():
    t = tresorerie(EXEMPLE)
    assert t["besoin_fonds_propres_max"] == approx(174214.866666667)
    assert t["mois_point_bas"] == 11
    assert t["cout_reel_credit"] == approx(32121.7333333333)
    assert t["marge_nette_fil_de_l_eau"] == approx(95278.2666666667)
    assert t["mois"][0]["tresorerie_cumulee"] == approx(-126047.2)
    assert t["mois"][10]["encours_credit"] == approx(507680)
    assert len(t["mois"]) == 12


@pytest.mark.parametrize("champ,valeur", [
    ("duree_mois", 0), ("duree_mois", 40), ("surface_vendable_m2", 0),
    ("marge_cible_pct", 15), ("mois_fin_travaux", 1),
])
def test_hypotheses_invalides(champ, valeur):
    with pytest.raises(ValueError):
        Hypotheses(**{**EXEMPLE.__dict__, champ: valeur})
