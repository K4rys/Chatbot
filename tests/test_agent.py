"""Teste la boucle agent et l'API avec un faux client Anthropic (aucun appel réseau)."""

import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import config
from app.agent import Assistant, _contenu_a_renvoyer
from app.prompt import system_prompt
from app.tools import executer

config.JOURNALISER_CONVERSATIONS = False


class Bloc(SimpleNamespace):
    def to_dict(self):
        return dict(self.__dict__)


class FauxStream:
    def __init__(self, reponse):
        self.reponse = reponse

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for b in self.reponse.content:
                if b.type == "text":
                    yield SimpleNamespace(type="text", text=b.text)
        return gen()

    async def get_final_message(self):
        return self.reponse


class FauxClient:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        self.appels.append(json.loads(json.dumps(params, default=str)))
        return FauxStream(self.reponses.pop(0))


ENTREE = {"surface_vendable_m2": 120, "prix_sortie_m2": 6500, "prix_acquisition": 520000,
          "travaux_ht": 90000, "duree_mois": 12, "honoraires_etudes": 12000, "portage": 6000}


def _collecter(assistant, conv, msg):
    async def run():
        return [e async for e in assistant.repondre(conv, msg)]
    return asyncio.run(run())


def test_boucle_outil_puis_reponse():
    client = FauxClient([
        SimpleNamespace(stop_reason="tool_use", content=[
            Bloc(type="text", text="Je calcule."),
            Bloc(type="tool_use", id="t1", name="simuler_operation", input=ENTREE)]),
        SimpleNamespace(stop_reason="end_turn", content=[Bloc(type="text", text="Marge 91 862 €.")]),
    ])
    a = Assistant(client)
    evts = _collecter(a, None, "Ça tient ?")
    textes = "".join(e["text"] for e in evts if e["type"] == "text")
    assert "Marge 91 862 €." in textes and evts[-1]["type"] == "done"
    # Le second appel contient le résultat d'outil, calculé avec le modèle.
    resultat = client.appels[1]["messages"][-1]["content"][0]
    assert resultat["tool_use_id"] == "t1" and resultat["is_error"] is False
    assert json.loads(resultat["content"])["bilan"]["marge_nette_avant_is"] == 91862
    # Paramètres de requête attendus.
    p = client.appels[0]
    assert p["model"] == config.MODEL and p["fallbacks"] == "default"
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_historique_conserve_entre_messages():
    client = FauxClient([
        SimpleNamespace(stop_reason="end_turn", content=[Bloc(type="text", text="A")]),
        SimpleNamespace(stop_reason="end_turn", content=[Bloc(type="text", text="B")]),
    ])
    a = Assistant(client)
    conv = _collecter(a, None, "1")[0]["id"]
    _collecter(a, conv, "2")
    assert [m["role"] for m in client.appels[1]["messages"]] == ["user", "assistant", "user"]


def test_refus_retire_la_question():
    client = FauxClient([SimpleNamespace(stop_reason="refusal", content=[])])
    a = Assistant(client)
    evts = _collecter(a, None, "x")
    assert evts[-1]["type"] == "error"
    assert a.conversations.get(evts[0]["id"])[1] == []


def test_erreur_saisie_outil():
    contenu, erreur = executer("simuler_operation", {"surface_vendable_m2": 100})
    assert erreur and "manquants" in contenu
    contenu, erreur = executer("simuler_operation", {**ENTREE, "duree_mois": 50})
    assert erreur and "durée" in contenu
    contenu, erreur = executer("simuler_operation", {**ENTREE, "pirate": 1})
    assert erreur and "inconnus" in contenu


def test_defauts_signales():
    contenu, erreur = executer("simuler_operation", ENTREE)
    d = json.loads(contenu)
    assert not erreur and "frais_acquisition_pct" in d["defauts_appliques"]
    assert d["tresorerie"]["mois_point_bas"] == 11


def test_fallback_omet_thinking_avant_bascule():
    blocs = [Bloc(type="thinking", thinking="", signature="s"), Bloc(type="text", text="début"),
             Bloc(type="fallback"), Bloc(type="thinking", thinking="", signature="s2"), Bloc(type="text", text="fin")]
    types = [b["type"] for b in _contenu_a_renvoyer(blocs)]
    assert types == ["text", "fallback", "thinking", "text"]


def test_prompt_contient_la_methode():
    p = system_prompt()
    for attendu in ("Offre A", "IOBSP", "carte T", "SGO IMMO recommande, le client décide", "simuler_operation"):
        assert attendu in p
    assert "{conseiller}" not in p and "{contact}" not in p


def test_api_http():
    from app.server import app
    app.state.assistant = Assistant(FauxClient([
        SimpleNamespace(stop_reason="end_turn", content=[Bloc(type="text", text="Bonjour")])]))
    with TestClient(app) as c:
        assert c.get("/").status_code == 200
        assert c.post("/api/chat", json={"message": "  "}).status_code == 400
        r = c.post("/api/chat", json={"message": "Salut"})
        assert r.status_code == 200 and '"text": "Bonjour"' in r.text
