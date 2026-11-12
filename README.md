# Assistant SGO IMMO

Chatbot disponible 24 h/24 qui répond aux clients avec la méthode SGO IMMO :
revue d'opération (offre A), promesse et financement (B), stratégie de sortie (C),
suivi d'opération (D). **Gratuit** : il fonctionne avec une IA locale (Ollama) ou avec
l'offre gratuite de Gemini, au choix par une ligne de configuration.

## Ce qu'il fait
- **Calcule** bilans, prix d'achat maximal, sensibilités et trésorerie avec un moteur Python
  qui reproduit **exactement** le classeur `07_Bilan_operation.xlsx` (vérifié par les tests).
  L'IA ne calcule jamais de tête : elle appelle ce moteur.
- **Raisonne** avec ta méthode : hypothèses client vs corrigées, GO / GO sous conditions / NO GO,
  points à valider par le notaire, l'avocat, l'expert-comptable…
- **Reste dans le périmètre** : pas de conseil juridique ou fiscal, pas d'intermédiation bancaire
  (IOBSP), pas de commercialisation (carte T), mention de portée de l'avis.
- **Se présente comme une IA** et renvoie vers toi pour tout avis engageant.

## Choisir l'IA

| | Ollama (local) | Gemini (offre gratuite) |
|---|---|---|
| Coût | 0 € | 0 € dans la limite des quotas gratuits |
| Confidentialité | Rien ne sort de ta machine | Conversations envoyées à Google ; vérifier dans les conditions de l'offre gratuite si elles peuvent servir à entraîner ses modèles |
| Qualité | Correcte avec un modèle 7B, meilleure avec un plus gros si ta machine suit | Bonne |
| Contraintes | Machine assez puissante (16 Go de RAM conseillés), allumée 24 h/24 | Quotas journaliers ; Google peut changer l'offre ou retirer un modèle |

Les noms de modèles par défaut (`qwen2.5:7b`, `gemini-2.5-flash`) étaient valables au moment
de l'écriture ; s'ils n'existent plus, en choisir un autre avec `SGO_MODELE`.

## Lancer en local

```bash
git clone https://github.com/K4rys/Chatbot.git && cd Chatbot
```
```bash
pip install -r requirements.txt
```
```bash
cp .env.example .env
```
(sous Windows : `copy .env.example .env`, puis `notepad .env` pour l'éditer.)
Dans `.env` : renseigner `SGO_CONSEILLER`, `SGO_CONTACT`, et le fournisseur.

### Option A : Ollama
1. Installer Ollama : https://ollama.com/download
2. Télécharger le modèle (environ 5 Go) :
```bash
ollama pull qwen2.5:7b
```
3. **Important** : le prompt de l'assistant fait environ 6 000 tokens. Si Ollama tourne avec une
   petite fenêtre de contexte, il tronque silencieusement les instructions et l'assistant
   « oublie » sa méthode. Lancer Ollama avec une fenêtre plus grande (variable reconnue par les
   versions récentes d'Ollama ; sinon voir la documentation d'Ollama sur `num_ctx`) :
```bash
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```

### Option B : Gemini
1. Créer une clé gratuite sur https://aistudio.google.com (rubrique « Get API key »).
2. Dans `.env` : `SGO_FOURNISSEUR=gemini` et `SGO_API_KEY=ta_clé`.

### Démarrer le chatbot
Depuis le dossier du projet (Windows, Mac ou Linux) ; le fichier `.env` est lu automatiquement :
```bash
python -m uvicorn app.server:app --port 8000
```
Ouvrir http://localhost:8000.

Tests :
```bash
python -m pytest -q
```

## Structure
| Chemin | Rôle |
|---|---|
| `knowledge/*.md` | Ce que sait l'assistant : posture, offres, méthodes, modèle de bilan. **Modifiable sans toucher au code.** |
| `knowledge/07_infos_pratiques.md` | À compléter : tarifs, zone, délais, pièces à fournir. |
| `knowledge/sources/` | Tes trames d'origine (Word, Excel). |
| `app/bilan.py` | Moteur de calcul (réplique de l'Excel). |
| `app/tools.py` | Outil `simuler_operation` exposé à l'IA. |
| `app/agent.py` | Conversation avec l'IA (protocole compatible OpenAI), streaming, garde-fous. |
| `app/config.py` | Choix du fournisseur et des réglages. |
| `app/server.py`, `app/static/index.html` | Serveur web et page de chat. |

## Mettre en ligne pour tes clients
- **Avec Gemini** : n'importe quel hébergeur Python. Certains ont une offre gratuite limitée
  (souvent avec mise en veille après inactivité : la première réponse est alors lente).
  Commande de démarrage `uvicorn app.server:app --host 0.0.0.0 --port $PORT`.
- **Avec Ollama** : l'IA tourne sur ta machine ; pour que tes clients y accèdent, il faut que
  cette machine reste allumée et soit joignable depuis Internet (tunnel type Cloudflare Tunnel,
  ou serveur dédié). Un serveur assez puissant pour faire tourner un modèle n'est pas gratuit.

Limites actuelles : historique des conversations et limiteur de débit en mémoire
(une seule instance ; un redémarrage efface les conversations en cours).

## Points à traiter avant d'ouvrir au public
- **Transparence IA** : l'assistant se déclare comme IA (page d'accueil + premier message).
- **RGPD** : le journal `logs/` conserve les échanges (sans adresse IP). Prévoir une mention
  d'information, une durée de conservation et la purge, ou désactiver avec `SGO_LOG_CONVERSATIONS=0`.
  Avec Gemini, les échanges transitent aussi par Google : à mentionner.
- **Qualité** : tester sur des cas réels avant ouverture, puis relire régulièrement le journal.
