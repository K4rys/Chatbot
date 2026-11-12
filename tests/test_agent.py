"""Teste la boucle agent et l'API avec un faux client (aucun appel réseau)."""

import asyncio
import json
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from app import config
from app.agent import Assistant
from app.prompt import system_prompt
from app.tools import executer

config.JOURNALISER_CONVERSATIONS = False
config.API_KEY = config.API_KEY or "test"

ENTREE = {"surface_vendable_m2": 120, "prix_sortie_m2": 6500, "prix_acquisition": 520000,
          "travaux_ht": 90000, "duree_mois": 12, "honoraires_etudes": 12000, "portage": 6000}


def chunk(content=None, tool_calls=None, fin=None):
    return NS(choices=[NS(delta=NS(content=content, tool_calls=tool_calls), finish_reason=fin)])


def tc(index, id=None, name=None, args=None):
    return NS(index=index, id=id, function=NS(name=name, arguments=args), model_extra={})


class FauxClient:
    """Rejoue des suites de « chunks » comme le ferait un serveur compatible OpenAI."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.chat = NS(completions=NS(create=self._create))

    async def _create(self, **params):
        self.appels.append(json.loads(json.dumps(params)))
        chunks = self.reponses.pop(0)

        async def gen():
            for c in chunks:
                yield c
        return gen()


def _collecter(assistant, conv, msg):
    async def run():
        return [e async for e in assistant.repondre(conv, msg)]
    return asyncio.run(run())


def test_boucle_outil_puis_reponse():
    args = json.dumps(ENTREE)
    client = FauxClient([
        # L'appel d'outil arrive découpé en plusieurs morceaux, comme en streaming réel.
        [chunk(content="Je calcule."), chunk(tool_calls=[tc(0, id="c1", name="simuler_operation", args=args[:30])]),
         chunk(tool_calls=[tc(0, args=args[30:])]), chunk(fin="tool_calls")],
        [chunk(content="Marge "), chunk(content="91 862 €."), chunk(fin="stop")],
    ])
    a = Assistant(client)
    evts = _collecter(a, None, "Ça tient ?")
    textes = "".join(e["text"] for e in evts if e["type"] == "text")
    assert "Marge 91 862 €." in textes and evts[-1]["type"] == "done"
    msgs = client.appels[1]["messages"]
    assert msgs[0]["role"] == "system" and "SGO IMMO" in msgs[0]["content"]
    assert msgs[2]["tool_calls"][0]["function"]["arguments"] == args
    outil = msgs[3]
    assert outil["role"] == "tool" and outil["tool_call_id"] == "c1"
    assert json.loads(outil["content"])["bilan"]["marge_nette_avant_is"] == 91862
    assert client.appels[0]["model"] == config.MODELE and client.appels[0]["tools"][0]["type"] == "function"


def test_appel_sans_identifiant_ni_index():
    # Certains fournisseurs n'envoient ni index ni id : on en génère un.
    sans = NS(index=None, id=None, function=NS(name="simuler_operation", arguments=json.dumps(ENTREE)),
              model_extra={})
    client = FauxClient([[chunk(tool_calls=[sans]), chunk(fin="tool_calls")],
                         [chunk(content="OK"), chunk(fin="stop")]])
    _collecter(Assistant(client), None, "x")
    msgs = client.appels[1]["messages"]
    assert msgs[-1]["tool_call_id"] == msgs[-2]["tool_calls"][0]["id"]


def test_historique_conserve_entre_messages():
    client = FauxClient([[chunk(content="A"), chunk(fin="stop")], [chunk(content="B"), chunk(fin="stop")]])
    a = Assistant(client)
    conv = _collecter(a, None, "1")[0]["id"]
    _collecter(a, conv, "2")
    assert [m["role"] for m in client.appels[1]["messages"]] == ["system", "user", "assistant", "user"]


def test_cle_manquante_signalee(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    evts = _collecter(Assistant(FauxClient([])), None, "x")
    assert evts[-1]["type"] == "error" and "clé API" in evts[-1]["text"]


def test_erreurs_outil():
    contenu, erreur = executer("simuler_operation", '{"surface_vendable_m2": 100}')
    assert erreur and "manquants" in contenu
    contenu, erreur = executer("simuler_operation", {**ENTREE, "duree_mois": 50})
    assert erreur and "durée" in contenu
    contenu, erreur = executer("simuler_operation", {**ENTREE, "pirate": 1})
    assert erreur and "inconnus" in contenu
    contenu, erreur = executer("simuler_operation", '{"surface_vendable_m2": 1')
    assert erreur and "JSON" in contenu


def test_nombres_en_texte_acceptes():
    contenu, erreur = executer("simuler_operation", {**ENTREE, "prix_acquisition": "520 000",
                                                     "marge_cible_pct": "0,15"})
    assert not erreur and json.loads(contenu)["bilan"]["prix_acquisition"] == 520000


def test_defauts_signales():
    contenu, erreur = executer("simuler_operation", json.dumps(ENTREE))
    d = json.loads(contenu)
    assert not erreur and "frais_acquisition_pct" in d["defauts_appliques"]
    assert d["tresorerie"]["mois_point_bas"] == 11


def test_prompt_contient_la_methode():
    p = system_prompt()
    for attendu in ("Offre A", "IOBSP", "carte T", "SGO IMMO recommande, le client décide", "simuler_operation"):
        assert attendu in p
    assert "{conseiller}" not in p and "{contact}" not in p


def test_api_http():
    from app.server import app
    app.state.assistant = Assistant(FauxClient([[chunk(content="Bonjour"), chunk(fin="stop")]]))
    with TestClient(app) as c:
        assert c.get("/").status_code == 200
        assert c.post("/api/chat", json={"message": "  "}).status_code == 400
        r = c.post("/api/chat", json={"message": "Salut"})
        assert r.status_code == 200 and '"text": "Bonjour"' in r.text


def _erreur_404():
    import openai
    e = openai.NotFoundError.__new__(openai.NotFoundError)  # indépendant de la version du SDK
    Exception.__init__(e, "model not found")
    e.status_code = 404
    return e


def test_modele_introuvable_liste_les_modeles(monkeypatch):
    monkeypatch.setattr(config, "FOURNISSEUR", "gemini")

    class Client404(FauxClient):
        async def _create(self, **params):
            raise _erreur_404()

    client = Client404([])

    async def lister():
        return NS(data=[NS(id="models/gemini-3.8-flash"), NS(id="models/text-embedding-004")])
    client.models = NS(list=lister)
    evts = _collecter(Assistant(client), None, "x")
    assert evts[-1]["type"] == "error"
    assert "introuvable" in evts[-1]["text"] and "gemini-3.8-flash" in evts[-1]["text"]
    assert "embedding" not in evts[-1]["text"]


def _erreur(classe, code):
    e = classe.__new__(classe)
    Exception.__init__(e, "erreur simulée")
    e.status_code = code
    return e


def test_bascule_sur_modele_de_secours_si_sature(monkeypatch):
    import openai
    monkeypatch.setattr(config, "MODELES_SECOURS", ["modele-secours"])

    class ClientSature(FauxClient):
        async def _create(self, **params):
            self.appels.append(params["model"])
            if params["model"] != "modele-secours":
                raise _erreur(openai.InternalServerError, 503)
            return await FauxClient._create(self, **params)

    client = ClientSature([[chunk(content="Réponse de secours"), chunk(fin="stop")]])
    client.appels = []
    evts = _collecter(Assistant(client), None, "x")
    assert evts[-1]["type"] == "done"
    assert client.appels[0] == config.MODELE and client.appels[1] == "modele-secours"


def test_tous_les_modeles_satures(monkeypatch):
    import openai
    monkeypatch.setattr(config, "MODELES_SECOURS", ["modele-secours"])

    class ClientSature(FauxClient):
        async def _create(self, **params):
            raise _erreur(openai.InternalServerError, 503)

    evts = _collecter(Assistant(ClientSature([])), None, "x")
    assert evts[-1]["type"] == "error" and "surchargé" in evts[-1]["text"]
