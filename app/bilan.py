"""Réplique en Python du modèle « 07_Bilan_operation.xlsx » de SGO IMMO.

Chaque fonction reproduit un onglet du classeur, avec les mêmes conventions :
- montants HT, résultat avant impôt sur les sociétés ;
- frais financiers du Bilan calculés de façon prudente (crédit supposé
  entièrement débloqué sur toute la durée) ;
- l'onglet Trésorerie donne le coût du crédit « au fil de l'eau ».

Les tests (tests/test_bilan.py) comparent les résultats aux valeurs recalculées
du classeur d'origine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields

DUREE_MAX_MOIS = 36


@dataclass(frozen=True)
class Hypotheses:
    # Recettes
    surface_vendable_m2: float
    prix_sortie_m2: float
    autres_recettes: float = 0.0
    # Acquisition
    prix_acquisition: float = 0.0
    frais_acquisition_pct: float = 0.03
    # Travaux
    travaux_ht: float = 0.0
    aleas_travaux_pct: float = 0.10
    mois_debut_travaux: int = 2
    mois_fin_travaux: int = 6
    # Frais annexes
    honoraires_etudes: float = 0.0
    frais_commercialisation_pct: float = 0.0
    portage: float = 0.0
    tva_nette: float = 0.0
    # Financement
    quotite_financee_pct: float = 0.80
    taux_interet_annuel: float = 0.055
    frais_dossier_garantie_pct: float = 0.015
    duree_mois: int = 12
    # Objectif
    marge_cible_pct: float = 0.15

    def __post_init__(self) -> None:
        erreurs = []
        if self.surface_vendable_m2 <= 0:
            erreurs.append("la surface vendable doit être positive")
        if self.prix_sortie_m2 <= 0:
            erreurs.append("le prix de sortie au m² doit être positif")
        if not 1 <= self.duree_mois <= DUREE_MAX_MOIS:
            erreurs.append(f"la durée doit être comprise entre 1 et {DUREE_MAX_MOIS} mois")
        if self.mois_debut_travaux < 1 or self.mois_fin_travaux < self.mois_debut_travaux:
            erreurs.append("les mois de travaux sont incohérents (début ≥ 1 et fin ≥ début)")
        for nom in ("frais_acquisition_pct", "aleas_travaux_pct", "frais_commercialisation_pct",
                    "quotite_financee_pct", "taux_interet_annuel", "frais_dossier_garantie_pct",
                    "marge_cible_pct"):
            v = getattr(self, nom)
            if not 0 <= v < 1:
                erreurs.append(f"{nom} doit être un ratio entre 0 et 1 (ex. 0.15 pour 15 %)")
        for nom in ("prix_acquisition", "travaux_ht", "honoraires_etudes", "portage", "autres_recettes"):
            if getattr(self, nom) < 0:
                erreurs.append(f"{nom} ne peut pas être négatif")
        if erreurs:
            raise ValueError("; ".join(erreurs))

    @classmethod
    def champs(cls) -> list[str]:
        return [f.name for f in fields(cls)]


def _coef_financement(h: Hypotheses, duree: float | None = None) -> float:
    d = h.duree_mois if duree is None else duree
    return 1 + h.quotite_financee_pct * (h.taux_interet_annuel * d / 12 + h.frais_dossier_garantie_pct)


def chiffre_affaires(h: Hypotheses) -> float:
    return h.surface_vendable_m2 * h.prix_sortie_m2 + h.autres_recettes


def bilan(h: Hypotheses) -> dict:
    """Onglet « Bilan »."""
    ca = chiffre_affaires(h)
    acquisition = h.prix_acquisition
    frais_acq = h.prix_acquisition * h.frais_acquisition_pct
    travaux = h.travaux_ht * (1 + h.aleas_travaux_pct)
    commercialisation = ca * h.frais_commercialisation_pct
    credit = (acquisition + frais_acq + travaux) * h.quotite_financee_pct
    frais_fin = credit * h.taux_interet_annuel * h.duree_mois / 12 + credit * h.frais_dossier_garantie_pct
    cout_revient = (acquisition + frais_acq + travaux + h.honoraires_etudes + commercialisation
                    + h.portage + h.tva_nette + frais_fin)
    marge = ca - cout_revient
    fonds_propres = cout_revient - credit
    rfp = marge / fonds_propres if fonds_propres else 0.0
    return {
        "chiffre_affaires": ca,
        "prix_acquisition": acquisition,
        "frais_acquisition": frais_acq,
        "travaux_avec_aleas": travaux,
        "honoraires_etudes": h.honoraires_etudes,
        "frais_commercialisation": commercialisation,
        "taxes_assurances_portage": h.portage,
        "tva_nette": h.tva_nette,
        "montant_credit": credit,
        "frais_financiers": frais_fin,
        "cout_revient_total": cout_revient,
        "marge_nette_avant_is": marge,
        "marge_sur_ca": marge / ca if ca else 0.0,
        "fonds_propres_mobilises": fonds_propres,
        "rentabilite_fonds_propres": rfp,
        "rentabilite_fonds_propres_annualisee": rfp * 12 / h.duree_mois,
    }


def prix_max(h: Hypotheses) -> dict:
    """Onglet « Prix max » : prix hors frais qui laisse exactement la marge cible."""
    ca = chiffre_affaires(h)
    marge_cible = ca * h.marge_cible_pct
    couts_hors = h.honoraires_etudes + ca * h.frais_commercialisation_pct + h.portage + h.tva_nette
    coef = _coef_financement(h)
    pmax = ((ca - marge_cible - couts_hors) / coef - h.travaux_ht * (1 + h.aleas_travaux_pct)) / (
        1 + h.frais_acquisition_pct)
    nego = h.prix_acquisition - pmax
    return {
        "chiffre_affaires": ca,
        "marge_cible": marge_cible,
        "couts_hors_acquisition_travaux_financement": couts_hors,
        "coefficient_financement": coef,
        "prix_acquisition_maximal_hors_frais": pmax,
        "prix_demande": h.prix_acquisition,
        "marge_negociation": nego,
        "marge_negociation_pct": nego / h.prix_acquisition if h.prix_acquisition else 0.0,
        "lecture": ("baisse de prix à obtenir pour atteindre la marge cible" if nego > 0
                    else "le prix demandé laisse au moins la marge cible"),
    }


def _marge_variation(h: Hypotheses, var_prix: float, var_travaux: float) -> float:
    ca = chiffre_affaires(h) * (1 + var_prix)
    base = h.prix_acquisition * (1 + h.frais_acquisition_pct) + h.travaux_ht * (1 + var_travaux) * (
        1 + h.aleas_travaux_pct)
    return ca - (base * _coef_financement(h) + h.honoraires_etudes + ca * h.frais_commercialisation_pct
                 + h.portage + h.tva_nette)


def _marge_allongement(h: Hypotheses, mois_sup: int) -> float:
    ca = chiffre_affaires(h)
    d = h.duree_mois + mois_sup
    base = h.prix_acquisition * (1 + h.frais_acquisition_pct) + h.travaux_ht * (1 + h.aleas_travaux_pct)
    return ca - (base * _coef_financement(h, d) + h.honoraires_etudes + ca * h.frais_commercialisation_pct
                 + h.portage * d / h.duree_mois + h.tva_nette)


def sensibilites(
    h: Hypotheses,
    variations_prix: tuple[float, ...] = (-0.15, -0.10, -0.05, 0.0, 0.05),
    variations_travaux: tuple[float, ...] = (0.0, 0.10, 0.20, 0.30),
    mois_supplementaires: tuple[int, ...] = (0, 3, 6, 12),
) -> dict:
    """Onglet « Sensibilités » (+ scénarios du rapport de revue A)."""
    ca = chiffre_affaires(h)
    matrice = [
        {"variation_prix_sortie": vp,
         "marges": {f"travaux_{vt:+.0%}": _marge_variation(h, vp, vt) for vt in variations_travaux}}
        for vp in variations_prix
    ]
    allongement = [
        {"mois_supplementaires": m, "marge": (mg := _marge_allongement(h, m)),
         "marge_sur_ca": mg / ca if ca else 0.0}
        for m in mois_supplementaires
    ]

    def scen(nom, mg, ca_s):
        return {"scenario": nom, "marge": mg, "marge_sur_ca": mg / ca_s if ca_s else 0.0}

    # Scénarios du tableau « Sensibilités » du rapport A. Le cumul défavorable
    # combine prix −10 %, travaux +20 % et durée +6 mois.
    cumul = _cumul_defavorable(h)
    scenarios = [
        scen("Base", _marge_variation(h, 0, 0), ca),
        scen("Prix de sortie −10 %", _marge_variation(h, -0.10, 0), ca * 0.9),
        scen("Travaux +20 %", _marge_variation(h, 0, 0.20), ca),
        scen("Durée +6 mois", _marge_allongement(h, 6), ca),
        scen("Cumul défavorable (prix −10 %, travaux +20 %, durée +6 mois)", cumul, ca * 0.9),
    ]
    return {"matrice_prix_x_travaux": matrice, "allongement_duree": allongement, "scenarios": scenarios}


def _cumul_defavorable(h: Hypotheses) -> float:
    ca = chiffre_affaires(h) * 0.9
    d = h.duree_mois + 6
    base = h.prix_acquisition * (1 + h.frais_acquisition_pct) + h.travaux_ht * 1.2 * (1 + h.aleas_travaux_pct)
    return ca - (base * _coef_financement(h, d) + h.honoraires_etudes + ca * h.frais_commercialisation_pct
                 + h.portage * d / h.duree_mois + h.tva_nette)


def tresorerie(h: Hypotheses) -> dict:
    """Onglet « Trésorerie » : plan mensuel, point bas et coût réel du crédit."""
    ca = chiffre_affaires(h)
    duree = h.duree_mois
    nb_mois_travaux = h.mois_fin_travaux - h.mois_debut_travaux + 1
    cumul, encours = 0.0, 0.0
    lignes = []
    for m in range(1, DUREE_MAX_MOIS + 1):
        acq = -h.prix_acquisition * (1 + h.frais_acquisition_pct) if m == 1 else 0.0
        trav = (-h.travaux_ht * (1 + h.aleas_travaux_pct) / nb_mois_travaux
                if h.mois_debut_travaux <= m <= h.mois_fin_travaux and m <= duree else 0.0)
        hon = -h.honoraires_etudes if m == 1 else 0.0
        port = -h.portage / duree if m <= duree else 0.0
        deblocage = -(acq + trav) * h.quotite_financee_pct
        interets = -encours * h.taux_interet_annuel / 12 - deblocage * h.frais_dossier_garantie_pct
        rembt = -(encours + deblocage) if m == duree else 0.0
        vente = ca * (1 - h.frais_commercialisation_pct) - h.tva_nette if m == duree else 0.0
        flux = acq + trav + hon + port + deblocage + interets + rembt + vente
        cumul += flux
        encours = encours + deblocage + rembt
        lignes.append({"mois": m, "acquisition_frais": acq, "travaux": trav, "honoraires": hon,
                       "portage": port, "deblocage_credit": deblocage, "interets_frais_credit": interets,
                       "remboursement": rembt, "vente_nette": vente, "flux_net": flux,
                       "tresorerie_cumulee": cumul, "encours_credit": encours})
    point_bas = min(l["tresorerie_cumulee"] for l in lignes)
    mois_point_bas = next(l["mois"] for l in lignes if l["tresorerie_cumulee"] == point_bas)
    return {
        "besoin_fonds_propres_max": -point_bas,
        "mois_point_bas": mois_point_bas,
        "cout_reel_credit": -sum(l["interets_frais_credit"] for l in lignes),
        "marge_nette_fil_de_l_eau": lignes[-1]["tresorerie_cumulee"],
        "mois": lignes[:duree],
    }


def analyse_complete(h: Hypotheses) -> dict:
    return {
        "hypotheses": asdict(h),
        "bilan": bilan(h),
        "prix_max": prix_max(h),
        "sensibilites": sensibilites(h),
        "tresorerie": tresorerie(h),
    }
