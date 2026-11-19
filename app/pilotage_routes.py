"""Routes de l'accès en ligne au pilotage MDB (montées par app/server.py)."""

from __future__ import annotations

import hmac
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from . import config
from .pilotage_comptes import ConflitVersion, LimiteurConnexion, base_depuis_env

DOSSIER = config.ROOT / "pilotage"
WEB = DOSSIER / "web"
COOKIE = "pilotage_session"
COOKIE_SECURE = os.getenv("PILOTAGE_COOKIE_SECURE", "1") == "1"
ENTETE_CSRF = "x-pilotage"

router = APIRouter()
base = base_depuis_env(config.ROOT / "data" / "pilotage.sqlite3")
limiteur = LimiteurConnexion()

TETE_PWA = """
<link rel="manifest" href="/pilotage/manifest.webmanifest">
<meta name="theme-color" content="#23508f">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Pilotage MDB">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="/pilotage/icone-180.png">
<link rel="icon" type="image/png" href="/pilotage/icone-192.png">
"""


def _ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()


def _utilisateur(request: Request):
    return base.session(request.cookies.get(COOKIE))


def _refus(code: int, msg: str) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=code)


def _ecriture_autorisee(request: Request) -> bool:
    """Protection CSRF : en-tête personnalisé exigé (un formulaire tiers ne peut pas l'envoyer)."""
    return request.headers.get(ENTETE_CSRF) == "1"


# ---------- pages ----------
@router.get("/pilotage", include_in_schema=False)
async def page_app(request: Request):
    u = _utilisateur(request)
    if u is None:
        return RedirectResponse("/pilotage/connexion", status_code=303)
    html = (DOSSIER / "index.html").read_text(encoding="utf-8")
    flags = ("<script>window.PILOTAGE_SERVEUR=true;window.PILOTAGE_UTILISATEUR="
             + json.dumps({"login": u["login"], "role": u["role"]}).replace("</", "<\\/") + ";</script>")
    html = html.replace("</head>", TETE_PWA + flags + "\n</head>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/pilotage/connexion", include_in_schema=False)
async def page_connexion(request: Request):
    if _utilisateur(request) is not None:
        return RedirectResponse("/pilotage", status_code=303)
    html = (WEB / "connexion.html").read_text(encoding="utf-8").replace("</head>", TETE_PWA + "</head>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/pilotage/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")


@router.get("/pilotage/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(WEB / "sw.js", media_type="text/javascript",
                        headers={"Service-Worker-Allowed": "/pilotage", "Cache-Control": "no-cache"})


@router.get("/pilotage/icone-{taille}.png", include_in_schema=False)
async def icone(taille: int):
    f = WEB / f"icone-{taille}.png"
    if taille not in (180, 192, 512) or not f.exists():
        return Response(status_code=404)
    return FileResponse(f, media_type="image/png")


# ---------- API ----------
@router.post("/api/pilotage/connexion")
async def connexion(request: Request):
    try:
        d = await request.json()
        login, mdp = str(d.get("login", "")).strip(), str(d.get("mdp", ""))
    except (ValueError, AttributeError):
        return _refus(400, "Requête invalide.")
    cles = ("ip:" + _ip(request), "login:" + login.lower())
    if limiteur.bloque(*cles):
        return _refus(429, "Trop d'essais. Réessayez dans 15 minutes.")
    u = base.authentifier(login, mdp)
    if u is None:
        limiteur.echec(*cles)
        return _refus(401, "Identifiant ou mot de passe incorrect.")
    limiteur.reussite(*cles)
    r = JSONResponse({"login": u["login"], "role": u["role"]})
    r.set_cookie(COOKIE, base.ouvrir_session(u["id"]), max_age=30 * 24 * 3600, httponly=True,
                 secure=COOKIE_SECURE, samesite="strict", path="/")
    return r


@router.post("/api/pilotage/deconnexion")
async def deconnexion(request: Request):
    base.fermer_session(request.cookies.get(COOKIE))
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE, path="/")
    return r


@router.get("/api/pilotage/etat")
async def lire_etat(request: Request):
    u = _utilisateur(request)
    if u is None:
        return _refus(401, "Session expirée.")
    etat, version = base.lire_etat(u["id"])
    return JSONResponse({"etat": etat, "version": version, "operations_sync": base.lire_operations_sync(u["id"])},
                        headers={"Cache-Control": "no-store"})


@router.put("/api/pilotage/etat")
async def ecrire_etat(request: Request):
    u = _utilisateur(request)
    if u is None:
        return _refus(401, "Session expirée.")
    if not _ecriture_autorisee(request):
        return _refus(403, "Requête refusée.")
    try:
        d = await request.json()
        etat, version = d["etat"], int(d["version"])
        if not isinstance(etat, dict) or not isinstance(etat.get("ops"), dict):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return _refus(400, "Données invalides.")
    try:
        return {"version": base.ecrire_etat(u["id"], etat, version)}
    except ConflitVersion as c:
        return JSONResponse({"error": "Modifié depuis un autre appareil.", "version": c.courante}, status_code=409)
    except ValueError as e:
        return _refus(413, str(e))


@router.post("/api/pilotage/mdp")
async def changer_mdp(request: Request):
    u = _utilisateur(request)
    if u is None:
        return _refus(401, "Session expirée.")
    if not _ecriture_autorisee(request):
        return _refus(403, "Requête refusée.")
    d = await request.json()
    if base.authentifier(u["login"], str(d.get("ancien", ""))) is None:
        return _refus(400, "Mot de passe actuel incorrect.")
    try:
        base.changer_mdp(u["id"], str(d.get("nouveau", "")))
    except ValueError as e:
        return _refus(400, str(e))
    r = JSONResponse({"ok": True})
    r.set_cookie(COOKIE, base.ouvrir_session(u["id"]), max_age=30 * 24 * 3600, httponly=True,
                 secure=COOKIE_SECURE, samesite="strict", path="/")
    return r


@router.get("/api/pilotage/utilisateurs")
async def lister_utilisateurs(request: Request):
    u = _utilisateur(request)
    if u is None or u["role"] != "admin":
        return _refus(403, "Réservé à l'administrateur.")
    return {"utilisateurs": base.lister()}


@router.post("/api/pilotage/utilisateurs")
async def creer_utilisateur(request: Request):
    u = _utilisateur(request)
    if u is None or u["role"] != "admin":
        return _refus(403, "Réservé à l'administrateur.")
    if not _ecriture_autorisee(request):
        return _refus(403, "Requête refusée.")
    d = await request.json()
    try:
        if d.get("action") == "desactiver":
            if str(d.get("login")).lower() == u["login"].lower():
                return _refus(400, "Vous ne pouvez pas désactiver votre propre compte.")
            base.activer(str(d.get("login")), False)
        elif d.get("action") == "activer":
            base.activer(str(d.get("login")), True)
        else:
            base.creer_utilisateur(str(d.get("login", "")), str(d.get("mdp", "")), str(d.get("role", "utilisateur")))
    except ValueError as e:
        return _refus(400, str(e))
    return {"utilisateurs": base.lister()}


@router.post("/api/pilotage/sync")
async def recevoir_sync(request: Request):
    """Dépôt des opérations issues du Drive par la tâche quotidienne (jeton PILOTAGE_SYNC_TOKEN)."""
    jeton = os.getenv("PILOTAGE_SYNC_TOKEN", "")
    fourni = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if len(jeton) < 24 or not hmac.compare_digest(fourni, jeton):
        return _refus(401, "Jeton de synchronisation invalide.")
    d = await request.json()
    u = base.utilisateur(str(d.get("login", "")))
    ops = d.get("operations")
    if u is None or not isinstance(ops, list):
        return _refus(400, "Utilisateur inconnu ou opérations invalides.")
    base.ecrire_operations_sync(u["id"], ops)
    return {"ok": True, "operations": len(ops)}
