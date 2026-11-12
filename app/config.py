"""Configuration lue dans les variables d'environnement (voir .env.example)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _charger_env(fichier: Path) -> None:
    """Lit le fichier .env (lignes CLE=valeur) sans écraser les variables déjà définies.
    Fonctionne sous Windows, Mac et Linux sans commande particulière."""
    if not fichier.is_file():
        return
    for ligne in fichier.read_text(encoding="utf-8-sig").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        cle, valeur = cle.strip(), valeur.strip()
        if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
            valeur = valeur[1:-1]
        if cle and valeur and cle not in os.environ:
            os.environ[cle] = valeur


_charger_env(Path(os.getenv("SGO_ENV_FILE", ROOT / ".env")))

KNOWLEDGE_DIR = ROOT / "knowledge"
LOG_DIR = Path(os.getenv("SGO_LOG_DIR", ROOT / "logs"))

# Fournisseurs gratuits pré-configurés. Tous parlent le même protocole (« compatible OpenAI ») :
# pour en changer, il suffit de modifier SGO_FOURNISSEUR, ou de renseigner SGO_API_URL et
# SGO_MODELE pour tout autre service compatible.
FOURNISSEURS = {
    # IA locale : gratuite, aucune donnée ne sort de la machine. https://ollama.com
    "ollama": {"url": "http://localhost:11434/v1", "modele": "qwen2.5:7b", "cle": "ollama"},
    # Offre gratuite de l'API Gemini. Clé sur https://aistudio.google.com
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "modele": "gemini-2.5-flash", "cle": None},
}

FOURNISSEUR = os.getenv("SGO_FOURNISSEUR", "ollama").lower()
_preset = FOURNISSEURS.get(FOURNISSEUR, {"url": None, "modele": None, "cle": None})
API_URL = os.getenv("SGO_API_URL") or _preset["url"]
MODELE = os.getenv("SGO_MODELE") or _preset["modele"]
API_KEY = os.getenv("SGO_API_KEY") or _preset["cle"] or ""
TEMPERATURE = float(os.getenv("SGO_TEMPERATURE", "0.3"))

CONSEILLER = os.getenv("SGO_CONSEILLER", "votre conseiller SGO IMMO")
CONTACT = os.getenv("SGO_CONTACT", "[coordonnées à configurer : SGO_CONTACT]")

# Garde-fous d'exploitation (le chatbot est public).
MAX_MESSAGES_PAR_CONVERSATION = int(os.getenv("SGO_MAX_MESSAGES", "40"))
MAX_CARACTERES_MESSAGE = int(os.getenv("SGO_MAX_CHARS", "6000"))
MESSAGES_PAR_HEURE_PAR_IP = int(os.getenv("SGO_RATE_LIMIT_HOUR", "60"))
MAX_TOURS_OUTILS = 6
JOURNALISER_CONVERSATIONS = os.getenv("SGO_LOG_CONVERSATIONS", "1") == "1"


def verifier() -> list[str]:
    """Problèmes de configuration bloquants, en français."""
    problemes = []
    if not API_URL or not MODELE:
        problemes.append(f"fournisseur « {FOURNISSEUR} » inconnu : choisir ollama ou gemini, "
                         "ou renseigner SGO_API_URL et SGO_MODELE")
    if not API_KEY:
        problemes.append("clé API manquante : renseigner SGO_API_KEY (clé gratuite Gemini sur aistudio.google.com)")
    return problemes
