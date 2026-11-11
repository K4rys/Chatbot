"""Boucle de conversation avec Claude : streaming du texte + appels à l'outil de calcul."""

from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import anthropic

from . import config
from .prompt import system_prompt
from .tools import TOOLS, executer

FALLBACK_BETA = "server-side-fallback-2026-07-01"
_INTERNES_AVANT_FALLBACK = {"thinking", "redacted_thinking", "tool_use"}


class Conversations:
    """Historique en mémoire (append-only), borné en nombre de conversations."""

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


def _contenu_a_renvoyer(blocs: list) -> list[dict]:
    """Prépare le contenu assistant pour l'historique.

    Après une bascule de modèle en cours de réponse (bloc « fallback »), l'API demande
    d'omettre les blocs thinking / tool_use situés avant le dernier bloc fallback.
    """
    dicts = [b.to_dict() if hasattr(b, "to_dict") else dict(b) for b in blocs]
    idx_fallback = max((i for i, b in enumerate(dicts) if b.get("type") == "fallback"), default=-1)
    return [b for i, b in enumerate(dicts)
            if not (i < idx_fallback and b.get("type") in _INTERNES_AVANT_FALLBACK)]


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
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        self._client = client
        self.conversations = Conversations()

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic()
        return self._client

    def _params(self, messages: list[dict]) -> dict:
        return dict(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=[{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": config.EFFORT},
            cache_control={"type": "ephemeral"},  # met aussi en cache l'historique de conversation
            betas=[FALLBACK_BETA],
            fallbacks="default",  # bascule automatique si le modèle décline une requête
        )

    async def repondre(self, conv_id: str | None, message: str) -> AsyncIterator[dict]:
        """Génère des événements : conversation, text, status, error, done."""
        conv_id, messages = self.conversations.get(conv_id)
        yield {"type": "conversation", "id": conv_id}

        if len(messages) >= config.MAX_MESSAGES_PAR_CONVERSATION:
            yield {"type": "error", "text": "Cette conversation est devenue très longue. Ouvrez-en une "
                   f"nouvelle, ou contactez directement {config.CONSEILLER} : {config.CONTACT}"}
            return

        n_avant = len(messages)
        messages.append({"role": "user", "content": message})
        _journaliser(conv_id, "client", message)
        texte_final: list[str] = []

        try:
            for _tour in range(config.MAX_TOURS_OUTILS):
                reponse = None
                for _essai in range(2):  # une relance si l'entrée d'outil streamée est illisible
                    try:
                        async with self.client.beta.messages.stream(**self._params(messages)) as stream:
                            async for event in stream:
                                if event.type == "text":
                                    texte_final.append(event.text)
                                    yield {"type": "text", "text": event.text}
                            reponse = await stream.get_final_message()
                        break
                    except ValueError:
                        continue
                if reponse is None:
                    raise RuntimeError("réponse illisible")

                if reponse.stop_reason == "refusal":
                    del messages[n_avant:]  # on retire la question refusée, l'historique reste cohérent
                    yield {"type": "error", "text": "Je ne peux pas répondre à cette demande. "
                           f"Vous pouvez contacter {config.CONSEILLER} : {config.CONTACT}"}
                    return

                messages.append({"role": "assistant", "content": _contenu_a_renvoyer(reponse.content)})

                if reponse.stop_reason == "pause_turn":
                    continue
                appels = [b for b in reponse.content if b.type == "tool_use"]
                if reponse.stop_reason != "tool_use" or not appels:
                    if reponse.stop_reason == "max_tokens":
                        yield {"type": "text", "text": "\n\n_(Réponse tronquée : demandez-moi la suite.)_"}
                    break

                yield {"type": "status", "text": "Calcul du bilan avec le modèle SGO IMMO…"}
                resultats = []
                for appel in appels:
                    contenu, erreur = executer(appel.name, appel.input)
                    resultats.append({"type": "tool_result", "tool_use_id": appel.id,
                                      "content": contenu, "is_error": erreur})
                messages.append({"role": "user", "content": resultats})
                yield {"type": "text", "text": "\n\n"}
            else:
                yield {"type": "text", "text": "\n\n_(Analyse interrompue : trop d'étapes de calcul.)_"}
        except anthropic.RateLimitError:
            del messages[n_avant:]
            yield {"type": "error", "text": "Le service est très sollicité. Réessayez dans une minute."}
            return
        except (anthropic.APIConnectionError, anthropic.APIStatusError, RuntimeError):
            del messages[n_avant:]
            yield {"type": "error", "text": "Le service est momentanément indisponible. Réessayez dans "
                   f"quelques instants, ou contactez {config.CONSEILLER} : {config.CONTACT}"}
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
