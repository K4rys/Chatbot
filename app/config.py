"""Configuration lue dans les variables d'environnement (voir .env.example)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
LOG_DIR = Path(os.getenv("SGO_LOG_DIR", ROOT / "logs"))

MODEL = os.getenv("SGO_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("SGO_EFFORT", "medium")  # low | medium | high | xhigh | max
MAX_TOKENS = int(os.getenv("SGO_MAX_TOKENS", "16000"))

CONSEILLER = os.getenv("SGO_CONSEILLER", "votre conseiller SGO IMMO")
CONTACT = os.getenv("SGO_CONTACT", "[coordonnées à configurer : SGO_CONTACT]")

# Garde-fous d'exploitation (le chatbot est public : chaque message coûte des tokens).
MAX_MESSAGES_PAR_CONVERSATION = int(os.getenv("SGO_MAX_MESSAGES", "40"))
MAX_CARACTERES_MESSAGE = int(os.getenv("SGO_MAX_CHARS", "6000"))
MESSAGES_PAR_HEURE_PAR_IP = int(os.getenv("SGO_RATE_LIMIT_HOUR", "60"))
MAX_TOURS_OUTILS = 6
JOURNALISER_CONVERSATIONS = os.getenv("SGO_LOG_CONVERSATIONS", "1") == "1"
