"""Accès en ligne au pilotage : comptes, sessions, données par utilisateur."""

import pytest
from fastapi.testclient import TestClient

from app import pilotage_routes
from app.pilotage_comptes import Base, LimiteurConnexion, hacher_mdp, mdp_valide, verifier_mdp
from app.server import app

MDP = "Gallieni2026x"
H = {"X-Pilotage": "1"}


@pytest.fixture()
def env(monkeypatch):
    base = Base(":memory:")
    base.creer_utilisateur("seb", MDP, "admin")
    base.creer_utilisateur("associe", "Associe2026y")
    monkeypatch.setattr(pilotage_routes, "base", base)
    monkeypatch.setattr(pilotage_routes, "limiteur", LimiteurConnexion())
    return base


def client(login=None, mdp=None):
    c = TestClient(app, base_url="https://testserver")
    if login:
        r = c.post("/api/pilotage/connexion", json={"login": login, "mdp": mdp})
        assert r.status_code == 200, r.text
    return c


def test_hachage_et_robustesse():
    h = hacher_mdp(MDP)
    assert MDP not in h and verifier_mdp(MDP, h) and not verifier_mdp("autre", h)
    assert mdp_valide("court") and mdp_valide("toutenminuscules12") and mdp_valide(MDP) is None


def test_page_protegee_redirige_vers_connexion(env):
    r = client().get("/pilotage", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/pilotage/connexion"
    assert "Se connecter" in client().get("/pilotage/connexion").text


def test_connexion_et_page_application(env):
    c = client("seb", MDP)
    page = c.get("/pilotage").text
    assert "PILOTAGE_SERVEUR=true" in page and '"login": "seb"' in page and "manifest.webmanifest" in page
    assert client().post("/api/pilotage/connexion", json={"login": "seb", "mdp": "mauvais"}).status_code == 401


def test_cookie_httponly_securise(env):
    r = client().post("/api/pilotage/connexion", json={"login": "seb", "mdp": MDP})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "secure" in sc and "samesite=strict" in sc


def test_donnees_isolees_par_utilisateur(env):
    a, b = client("seb", MDP), client("associe", "Associe2026y")
    assert a.put("/api/pilotage/etat", json={"etat": {"ops": {"x": {"nom": "Gallieni"}}}, "version": 0}, headers=H).json() == {"version": 1}
    assert b.get("/api/pilotage/etat").json()["etat"] is None
    assert a.get("/api/pilotage/etat").json()["etat"]["ops"]["x"]["nom"] == "Gallieni"


def test_conflit_de_version_entre_appareils(env):
    tel, pc = client("seb", MDP), client("seb", MDP)
    assert tel.put("/api/pilotage/etat", json={"etat": {"ops": {}}, "version": 0}, headers=H).status_code == 200
    r = pc.put("/api/pilotage/etat", json={"etat": {"ops": {}}, "version": 0}, headers=H)
    assert r.status_code == 409 and r.json()["version"] == 1


def test_ecriture_refusee_sans_entete_csrf_ou_session(env):
    c = client("seb", MDP)
    assert c.put("/api/pilotage/etat", json={"etat": {"ops": {}}, "version": 0}).status_code == 403
    assert client().put("/api/pilotage/etat", json={"etat": {"ops": {}}, "version": 0}, headers=H).status_code == 401


def test_limitation_des_essais(env):
    c = client()
    for _ in range(8):
        c.post("/api/pilotage/connexion", json={"login": "seb", "mdp": "faux"})
    assert c.post("/api/pilotage/connexion", json={"login": "seb", "mdp": MDP}).status_code == 429


def test_deconnexion_et_changement_mdp(env):
    c = client("seb", MDP)
    autre = client("seb", MDP)
    r = c.post("/api/pilotage/mdp", json={"ancien": MDP, "nouveau": "Nouveau2026z"}, headers=H)
    assert r.status_code == 200
    assert autre.get("/api/pilotage/etat").status_code == 401          # autres sessions fermées
    assert c.get("/api/pilotage/etat").status_code == 200              # session courante renouvelée
    c.post("/api/pilotage/deconnexion")
    assert c.get("/api/pilotage/etat").status_code == 401


def test_administration_des_comptes(env):
    admin, user = client("seb", MDP), client("associe", "Associe2026y")
    assert user.get("/api/pilotage/utilisateurs").status_code == 403
    r = admin.post("/api/pilotage/utilisateurs", json={"login": "notaire", "mdp": "Provisoire2026"}, headers=H)
    assert any(u["login"] == "notaire" for u in r.json()["utilisateurs"])
    assert admin.post("/api/pilotage/utilisateurs", json={"login": "x", "mdp": "faible"}, headers=H).status_code == 400
    admin.post("/api/pilotage/utilisateurs", json={"action": "desactiver", "login": "associe"}, headers=H)
    assert user.get("/api/pilotage/etat").status_code == 401
    assert admin.post("/api/pilotage/utilisateurs", json={"action": "desactiver", "login": "seb"}, headers=H).status_code == 400


def test_synchronisation_drive_par_jeton(env, monkeypatch):
    monkeypatch.setenv("PILOTAGE_SYNC_TOKEN", "j" * 32)
    c = client()
    ops = [{"id": "drv-1", "nom": "25.03 Montmorency"}]
    assert c.post("/api/pilotage/sync", json={"login": "seb", "operations": ops}).status_code == 401
    r = c.post("/api/pilotage/sync", json={"login": "seb", "operations": ops}, headers={"Authorization": "Bearer " + "j" * 32})
    assert r.status_code == 200
    assert client("seb", MDP).get("/api/pilotage/etat").json()["operations_sync"] == ops
    assert client("associe", "Associe2026y").get("/api/pilotage/etat").json()["operations_sync"] == []


def test_fichiers_application_mobile(env):
    c = client()
    assert c.get("/pilotage/manifest.webmanifest").json()["display"] == "standalone"
    assert "serviceWorker" not in c.get("/pilotage/sw.js").text and c.get("/pilotage/sw.js").status_code == 200
    assert c.get("/pilotage/icone-192.png").content[:8] == b"\x89PNG\r\n\x1a\n"
