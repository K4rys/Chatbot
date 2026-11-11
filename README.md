# Assistant SGO IMMO

Chatbot disponible 24 h/24 qui répond aux clients avec la méthode SGO IMMO :
revue d'opération (offre A), promesse et financement (B), stratégie de sortie (C),
suivi d'opération (D). Il s'appuie sur Claude (API Anthropic).

## Ce qu'il fait
- **Calcule** bilans, prix d'achat maximal, sensibilités et trésorerie avec un moteur Python
  qui reproduit **exactement** le classeur `07_Bilan_operation.xlsx` (vérifié par les tests
  contre les valeurs recalculées du classeur). Le modèle d'IA ne calcule jamais de tête.
- **Raisonne** avec ta méthode : hypothèses client vs corrigées, GO / GO sous conditions / NO GO,
  points à valider par le notaire, l'avocat, l'expert-comptable…
- **Reste dans le périmètre** : pas de conseil juridique ou fiscal, pas d'intermédiation bancaire
  (IOBSP), pas de commercialisation (carte T), mention de portée de l'avis.
- **Se présente comme une IA** et renvoie vers toi pour tout avis engageant.

## Structure
| Chemin | Rôle |
|---|---|
| `knowledge/*.md` | Ce que sait l'assistant : posture, offres, méthodes, modèle de bilan. **Modifiable sans toucher au code.** |
| `knowledge/07_infos_pratiques.md` | À compléter : tarifs, zone, délais, pièces à fournir. |
| `knowledge/sources/` | Tes trames d'origine (Word, Excel). |
| `app/bilan.py` | Moteur de calcul (réplique de l'Excel). |
| `app/tools.py` | Outil `simuler_operation` exposé à l'IA. |
| `app/agent.py` | Conversation avec Claude, streaming, garde-fous. |
| `app/server.py`, `app/static/index.html` | Serveur web et page de chat. |

## Lancer en local
```bash
pip install -r requirements.txt
```
```bash
cp .env.example .env   # puis renseigner ANTHROPIC_API_KEY, SGO_CONSEILLER, SGO_CONTACT
```
```bash
set -a; . ./.env; set +a; uvicorn app.server:app --host 0.0.0.0 --port 8000
```
Ouvrir http://localhost:8000.

Tests :
```bash
python -m pytest -q
```

## Mettre en ligne
N'importe quel hébergeur Python (Render, Railway, Fly.io, Scalingo, un VPS) :
commande de démarrage `uvicorn app.server:app --host 0.0.0.0 --port $PORT`, variables
d'environnement de `.env.example`. Mettre le site en HTTPS. Pour l'intégrer à ton site
existant, une `<iframe>` vers l'URL du chatbot suffit.

Limites actuelles : historique des conversations et limiteur de débit en mémoire
(une seule instance du serveur ; un redémarrage efface les conversations en cours).

## Points à traiter avant d'ouvrir au public
- **Transparence IA** : l'assistant se déclare comme IA (page d'accueil + premier message).
- **RGPD** : le journal `logs/` conserve les échanges (sans adresse IP). Prévoir une mention
  d'information, une durée de conservation et la purge, ou désactiver avec `SGO_LOG_CONVERSATIONS=0`.
- **Responsabilité** : relire régulièrement le journal pour vérifier la qualité des réponses.
- **Coût** : chaque message consomme des tokens ; ajuster `SGO_RATE_LIMIT_HOUR` et `SGO_EFFORT`.
