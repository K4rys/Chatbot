"""Outils mis à disposition du modèle."""

from __future__ import annotations

import json

from .bilan import Hypotheses, analyse_complete

_OBLIGATOIRES = {
    "surface_vendable_m2": "Surface vendable en m² (Carrez / habitable / terrain selon la nature).",
    "prix_sortie_m2": "Prix de sortie en € HT par m².",
    "prix_acquisition": "Prix d'acquisition hors frais, en €.",
    "travaux_ht": "Montant des travaux en € HT, hors aléas.",
    "duree_mois": "Durée de l'opération en mois, de l'acquisition à la dernière vente (1 à 36).",
}
_OPTIONNELS = {
    "autres_recettes": "Autres recettes en € (parking, cave, loyers perçus pendant le portage). Défaut 0.",
    "frais_acquisition_pct": "Frais d'acquisition en ratio du prix (0.03 = 3 %). Défaut 0.03, à remplacer par le chiffrage du notaire.",
    "aleas_travaux_pct": "Aléas travaux en ratio des travaux. Défaut 0.10.",
    "mois_debut_travaux": "Mois de début des travaux (mois 1 = acquisition). Défaut 2.",
    "mois_fin_travaux": "Mois de fin des travaux. Défaut 6.",
    "honoraires_etudes": "Honoraires et études en € (géomètre, architecte, BET, diagnostics, conseil). Défaut 0.",
    "frais_commercialisation_pct": "Frais de commercialisation en ratio du CA. Défaut 0.",
    "portage": "Taxes, assurances, charges de portage en € sur toute la durée. Défaut 0.",
    "tva_nette": "TVA nette à décaisser estimée en €. Défaut 0, régime à valider par l'expert-comptable.",
    "quotite_financee_pct": "Quotité financée en ratio de (acquisition + frais + travaux). Défaut 0.80. Mettre 0 si achat sans crédit.",
    "taux_interet_annuel": "Taux d'intérêt annuel nominal en ratio. Défaut 0.055.",
    "frais_dossier_garantie_pct": "Frais de dossier et garantie en ratio du crédit. Défaut 0.015.",
    "marge_cible_pct": "Marge cible en ratio du CA, pour le prix d'achat maximal. Défaut 0.15.",
}
_ENTIERS = {"duree_mois", "mois_debut_travaux", "mois_fin_travaux"}

_FONCTION = {
    "name": "simuler_operation",
    "description": (
        "Calcule le bilan prévisionnel d'une opération de marchand de biens avec le modèle SGO IMMO "
        "(identique au classeur 07_Bilan_operation) : bilan et marge nette avant IS, fonds propres et "
        "rentabilité, prix d'achat maximal pour la marge cible et marge de négociation, sensibilités "
        "(prix de sortie × travaux, allongement de durée, scénarios du rapport de revue dont le cumul "
        "défavorable), plan de trésorerie mensuel avec point bas. Tous les ratios s'expriment en "
        "décimal (15 % = 0.15). Appelle l'outil plusieurs fois pour comparer hypothèses client et "
        "hypothèses corrigées, ou plusieurs scénarios de sortie."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **{k: {"type": "integer" if k in _ENTIERS else "number", "description": d}
               for k, d in _OBLIGATOIRES.items()},
            **{k: {"type": "integer" if k in _ENTIERS else "number", "description": d}
               for k, d in _OPTIONNELS.items()},
            "libelle": {"type": "string", "description": "Nom court du scénario (ex. « hypothèses client »)."},
        },
        "required": list(_OBLIGATOIRES),
        "additionalProperties": False,
    },
}

# Format « tools » du protocole compatible OpenAI (Ollama, Gemini, Mistral, Groq…).
TOOLS = [{"type": "function", "function": _FONCTION}]


def _arrondi(obj):
    if isinstance(obj, float):
        return round(obj, 4) if abs(obj) < 10 else round(obj)
    if isinstance(obj, dict):
        return {k: _arrondi(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_arrondi(v) for v in obj]
    return obj


def simuler_operation(entree: dict) -> dict:
    """Valide l'entrée produite par le modèle (jamais fiable à 100 %) et calcule."""
    if not isinstance(entree, dict):
        raise ValueError("l'entrée doit être un objet JSON")
    inconnus = set(entree) - set(_OBLIGATOIRES) - set(_OPTIONNELS) - {"libelle"}
    if inconnus:
        raise ValueError(f"paramètres inconnus : {', '.join(sorted(inconnus))}")
    manquants = [k for k in _OBLIGATOIRES if k not in entree]
    if manquants:
        raise ValueError(f"paramètres obligatoires manquants : {', '.join(manquants)}")
    valeurs = {}
    for k, v in entree.items():
        if k == "libelle":
            continue
        if isinstance(v, str):  # les petits modèles envoient parfois « "520000" » ou « "0,15" »
            try:
                v = float(v.replace(" ", "").replace(" ", "").replace(",", "."))
            except ValueError:
                raise ValueError(f"{k} doit être un nombre") from None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{k} doit être un nombre")
        if k in _ENTIERS and float(v) != int(v):
            raise ValueError(f"{k} doit être un nombre entier de mois")
        valeurs[k] = int(v) if k in _ENTIERS else float(v)
    h = Hypotheses(**valeurs)
    resultat = analyse_complete(h)
    # Trésorerie : on garde les colonnes utiles pour limiter le volume renvoyé au modèle.
    resultat["tresorerie"]["mois"] = [
        {"mois": m["mois"], "flux_net": m["flux_net"], "tresorerie_cumulee": m["tresorerie_cumulee"],
         "encours_credit": m["encours_credit"]}
        for m in resultat["tresorerie"]["mois"]
    ]
    resultat["defauts_appliques"] = sorted(k for k in _OPTIONNELS if k not in entree)
    if "libelle" in entree:
        resultat["libelle"] = str(entree["libelle"])
    return _arrondi(resultat)


def executer(nom: str, arguments) -> tuple[str, bool]:
    """Renvoie (contenu, erreur). `arguments` est le JSON texte produit par le modèle, ou un dict."""
    if nom != "simuler_operation":
        return f"Outil inconnu : {nom}", True
    try:
        entree = json.loads(arguments or "{}") if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        return "Erreur : les paramètres ne sont pas un JSON valide. Rappelle l'outil avec un JSON correct.", True
    try:
        return json.dumps(simuler_operation(entree), ensure_ascii=False), False
    except (ValueError, TypeError) as e:
        return f"Erreur de saisie : {e}. Corrige les paramètres ou demande l'information au client.", True
