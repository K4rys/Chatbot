"""Boucle de conversation : streaming du texte + appels à l'outil de calcul.

Utilise le protocole « compatible OpenAI », parlé par Ollama (IA locale gratuite),
l'API Gemini (offre gratuite) et la plupart des autres fournisseurs.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import openai

from . import config
from .prompt import system_prompt
from .tools import TOOLS, executer


class Conversations:
    """Historique en mémoire, borné en nombre de conversations."""

    def __init__(self, capacite: int = 2000):
        self._data: OrderedDict[str, list[dict]] = OrderedDict()
        self._capacite = capacite

    def get(self, conv_id: str | None) -> tuple[str, list[dict]]:
        if not conv_id or conv_id not in self._data:
            conv_id = uuid.uuid4().hex
            self._data[conv_id] = []
        self._data.move_to_end(conv_id)
        while len(self._data) > self._capacite:
            self._data.popitem(last=False)
        return conv_id, self._data[conv_id]


def _journaliser(conv_id: str, role: str, texte: str) -> None:
    if not config.JOURNALISER_CONVERSATIONS:
        return
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ligne = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "conversation": conv_id,
             "role": role, "texte": texte}
    with open(config.LOG_DIR / f"conversations-{jour}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


class Assistant:
    def __init__(self, client: openai.AsyncOpenAI | None = None):
        self._client = client
        self.conversations = Conversations()

    @property
    def client(self) -> openai.AsyncOpenAI:
        if self._client is None:
            self._client = openai.AsyncOpenAI(base_url=config.API_URL, api_key=config.API_KEY, timeout=180)
        return self._client

    async def _tour(self, messages: list[dict]) -> AsyncIterator[dict]:
        """Un appel au modèle. Émet les morceaux de texte puis {"type": "_fin", ...}."""
        stream = await self.client.chat.completions.create(
            model=config.MODELE,
            messages=[{"role": "system", "content": system_prompt()}, *messages],
            tools=TOOLS,
            temperature=config.TEMPERATURE,
            stream=True,
        )
        texte, appels, fin = [], {}, None
        async for chunk in stream:
            if not chunk.choices:
                continue
            choix = chunk.choices[0]
            delta = choix.delta
            if delta is not None and delta.content:
                texte.append(delta.content)
                yield {"type": "text", "text": delta.content}
            for tc in (delta.tool_calls or []) if delta is not None else []:
                # Les fournisseurs découpent les appels d'outils différemment : on les rassemble
                # par index, ou par identifiant quand l'index manque.
                cle = tc.index if tc.index is not None else (tc.id or len(appels))
                appel = appels.setdefault(cle, {"id": None, "nom": "", "arguments": "", "extra": {}})
                # Champs propres à un fournisseur (ex. signature de raisonnement Gemini) :
                # on les conserve pour les renvoyer tels quels au tour suivant.
                appel["extra"].update({k: v for k, v in (getattr(tc, "model_extra", None) or {}).items()
                                       if k not in ("index",) and v is not None})
                if tc.id:
                    appel["id"] = tc.id
                if tc.function is not None:
                    if tc.function.name:
                        appel["nom"] = tc.function.name
                    if tc.function.arguments:
                        appel["arguments"] += tc.function.arguments
            if choix.finish_reason:
                fin = choix.finish_reason
        for appel in appels.values():
            appel["id"] = appel["id"] or f"appel_{uuid.uuid4().hex[:12]}"
        yield {"type": "_fin", "texte": "".join(texte), "appels": list(appels.values()), "fin": fin}

    async def repondre(self, conv_id: str | None, message: str) -> AsyncIterator[dict]:
        """Génère des événements : conversation, text, status, error, done."""
        conv_id, messages = self.conversations.get(conv_id)
        yield {"type": "conversation", "id": conv_id}

        problemes = config.verifier()
        if problemes:
            yield {"type": "error", "text": "Assistant mal configuré : " + " ; ".join(problemes)}
            return
        if len(messages) >= config.MAX_MESSAGES_PAR_CONVERSATION:
            yield {"type": "error", "text": "Cette conversation est devenue très longue. Ouvrez-en une "
                   f"nouvelle, ou contactez directement {config.CONSEILLER} : {config.CONTACT}"}
            return

        n_avant = len(messages)
        messages.append({"role": "user", "content": message})
        _journaliser(conv_id, "client", message)
        texte_final: list[str] = []

        try:
            for _ in range(config.MAX_TOURS_OUTILS):
                fin = None
                async for evt in self._tour(messages):
                    if evt["type"] == "_fin":
                        fin = evt
                    else:
                        texte_final.append(evt["text"])
                        yield evt

                if not fin["appels"]:
                    messages.append({"role": "assistant", "content": fin["texte"]})
                    if fin["fin"] == "length":
                        yield {"type": "text", "text": "\n\n_(Réponse tronquée : demandez-moi la suite.)_"}
                    break

                messages.append({
                    "role": "assistant",
                    "content": fin["texte"] or None,
                    "tool_calls": [{**a["extra"], "id": a["id"], "type": "function",
                                    "function": {"name": a["nom"], "arguments": a["arguments"] or "{}"}}
                                   for a in fin["appels"]],
                })
                yield {"type": "status", "text": "Calcul du bilan avec le modèle SGO IMMO…"}
                for a in fin["appels"]:
                    contenu, _erreur = executer(a["nom"], a["arguments"])
                    messages.append({"role": "tool", "tool_call_id": a["id"], "content": contenu})
                if fin["texte"]:
                    yield {"type": "text", "text": "\n\n"}
            else:
                yield {"type": "text", "text": "\n\n_(Analyse interrompue : trop d'étapes de calcul.)_"}
        except openai.RateLimitError:
            del messages[n_avant:]
            yield {"type": "error", "text": "Le quota gratuit du service d'IA est atteint pour le moment. "
                   f"Réessayez plus tard, ou contactez {config.CONSEILLER} : {config.CONTACT}"}
            return
        except openai.APIConnectionError:
            del messages[n_avant:]
            yield {"type": "error", "text": "Le service d'IA ne répond pas (serveur Ollama arrêté ?). "
                   f"Réessayez dans quelques instants, ou contactez {config.CONSEILLER} : {config.CONTACT}"}
            return
        except openai.APIStatusError as e:
            del messages[n_avant:]
            detail = "clé API refusée" if e.status_code in (401, 403) else (
                "modèle introuvable (pour Ollama : lancer « ollama pull " + config.MODELE + " »)"
                if e.status_code == 404 else f"erreur {e.status_code}")
            yield {"type": "error", "text": f"Le service d'IA est indisponible ({detail}). "
                   f"Vous pouvez contacter {config.CONSEILLER} : {config.CONTACT}"}
            return

        _journaliser(conv_id, "assistant", "".join(texte_final))
        yield {"type": "done"}


class LimiteurDebit:
    """Limite simple par IP (fenêtre glissante d'une heure), en mémoire."""

    def __init__(self, par_heure: int):
        self.par_heure = par_heure
        self._hits: dict[str, list[float]] = {}

    def autoriser(self, cle: str) -> bool:
        maintenant = time.monotonic()
        hits = [t for t in self._hits.get(cle, []) if maintenant - t < 3600]
        if len(hits) >= self.par_heure:
            self._hits[cle] = hits
            return False
        hits.append(maintenant)
        self._hits[cle] = hits
        return True
