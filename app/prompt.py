"""Construit le prompt système à partir des fichiers de knowledge/.

Le prompt est figé au démarrage (aucune date ni donnée variable) pour que le cache
de prompt fonctionne : seul l'historique de conversation change d'une requête à l'autre.
"""

from functools import lru_cache

from . import config

CONSIGNES_REPONSE = """
# Comment répondre
- Réponds en français, en Markdown simple (titres courts, listes, tableaux pour les chiffres).
- Commence ta toute première réponse d'une conversation en te présentant en une phrase comme
  l'assistant virtuel (IA) de {conseiller}, SGO IMMO.
- Dès que le client donne des chiffres d'opération, appelle `simuler_operation`. S'il manque une
  donnée indispensable (surface vendable, prix de sortie au m², prix d'acquisition, travaux, durée),
  demande-la plutôt que d'en inventer une.
- Présente les montants arrondis à l'euro (ou au millier pour les ordres de grandeur) avec un
  espace comme séparateur de milliers, et les ratios en % avec une décimale.
- Termine par la prochaine étape concrète : une question à trancher, un document à obtenir,
  un professionnel à consulter, ou un rendez-vous avec {conseiller}.
"""


@lru_cache(maxsize=1)
def system_prompt() -> str:
    parties = []
    for fichier in sorted(config.KNOWLEDGE_DIR.glob("*.md")):
        parties.append(fichier.read_text(encoding="utf-8").strip())
    parties.append(CONSIGNES_REPONSE.strip())
    texte = "\n\n---\n\n".join(parties)
    return texte.replace("{conseiller}", config.CONSEILLER).replace("{contact}", config.CONTACT)
