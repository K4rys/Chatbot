"""Accès en ligne au pilotage MDB : comptes, sessions et données par utilisateur.

- Mots de passe hachés avec scrypt (sel aléatoire), jamais stockés en clair.
- Session : jeton aléatoire en cookie HttpOnly / SameSite=Strict ; seule son empreinte SHA-256 est stockée.
- Données : un état JSON par utilisateur (version pour détecter les modifications concurrentes
  téléphone / ordinateur) + les opérations poussées par la synchronisation Drive.
- Stockage SQLite (fichier PILOTAGE_DB), sans dépendance supplémentaire.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

DUREE_SESSION = 30 * 24 * 3600
MDP_MIN = 10
TAILLE_MAX_ETAT = 3 * 1024 * 1024
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


# ---------- mots de passe ----------
def hacher_mdp(mdp: str) -> str:
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(mdp.encode("utf-8"), salt=sel, **_SCRYPT)
    return f"scrypt${sel.hex()}${h.hex()}"


def verifier_mdp(mdp: str, stocke: str) -> bool:
    try:
        algo, sel, h = stocke.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(mdp.encode("utf-8"), salt=bytes.fromhex(sel), **_SCRYPT)
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, TypeError):
        return False


def mdp_valide(mdp: str) -> str | None:
    """Message d'erreur si le mot de passe est trop faible, sinon None."""
    if len(mdp) < MDP_MIN:
        return f"Le mot de passe doit contenir au moins {MDP_MIN} caractères."
    if mdp.lower() == mdp or mdp.upper() == mdp or not any(c.isdigit() for c in mdp):
        return "Le mot de passe doit mélanger majuscules, minuscules et chiffres."
    return None


def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


# ---------- base ----------
class Base:
    def __init__(self, chemin: str | Path):
        self.chemin = str(chemin)
        if self.chemin != ":memory:":
            Path(self.chemin).parent.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self._cx = sqlite3.connect(self.chemin, check_same_thread=False)
        self._cx.row_factory = sqlite3.Row
        self._cx.execute("PRAGMA foreign_keys = ON")
        self._cx.executescript("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id INTEGER PRIMARY KEY, login TEXT UNIQUE NOT NULL COLLATE NOCASE, hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'utilisateur', actif INTEGER NOT NULL DEFAULT 1, cree REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            empreinte TEXT PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
            expire REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS etats (
            utilisateur INTEGER PRIMARY KEY REFERENCES utilisateurs(id) ON DELETE CASCADE,
            json TEXT NOT NULL, version INTEGER NOT NULL, maj REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS operations_sync (
            utilisateur INTEGER PRIMARY KEY REFERENCES utilisateurs(id) ON DELETE CASCADE,
            json TEXT NOT NULL, maj REAL NOT NULL);
        """)
        self._cx.commit()

    @contextmanager
    def tx(self):
        with self._verrou:
            try:
                yield self._cx
                self._cx.commit()
            except Exception:
                self._cx.rollback()
                raise

    # utilisateurs
    def creer_utilisateur(self, login: str, mdp: str, role: str = "utilisateur") -> int:
        login = login.strip()
        if not login or len(login) > 64 or any(c.isspace() for c in login):
            raise ValueError("Identifiant invalide (sans espace, 64 caractères maximum).")
        err = mdp_valide(mdp)
        if err:
            raise ValueError(err)
        if role not in ("utilisateur", "admin"):
            raise ValueError("Rôle inconnu.")
        with self.tx() as cx:
            try:
                cur = cx.execute("INSERT INTO utilisateurs (login, hash, role, cree) VALUES (?, ?, ?, ?)",
                                 (login, hacher_mdp(mdp), role, time.time()))
            except sqlite3.IntegrityError:
                raise ValueError("Cet identifiant existe déjà.") from None
            return cur.lastrowid

    def utilisateur(self, login: str):
        return self._cx.execute("SELECT * FROM utilisateurs WHERE login = ?", (login.strip(),)).fetchone()

    def lister(self) -> list[dict]:
        rows = self._cx.execute("SELECT login, role, actif, cree FROM utilisateurs ORDER BY login").fetchall()
        return [dict(r) for r in rows]

    def nb_utilisateurs(self) -> int:
        return self._cx.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0]

    def changer_mdp(self, uid: int, mdp: str) -> None:
        err = mdp_valide(mdp)
        if err:
            raise ValueError(err)
        with self.tx() as cx:
            cx.execute("UPDATE utilisateurs SET hash = ? WHERE id = ?", (hacher_mdp(mdp), uid))
            cx.execute("DELETE FROM sessions WHERE utilisateur = ?", (uid,))

    def activer(self, login: str, actif: bool) -> None:
        with self.tx() as cx:
            n = cx.execute("UPDATE utilisateurs SET actif = ? WHERE login = ?", (int(actif), login)).rowcount
            if not n:
                raise ValueError("Utilisateur inconnu.")
            if not actif:
                cx.execute("DELETE FROM sessions WHERE utilisateur = (SELECT id FROM utilisateurs WHERE login = ?)", (login,))

    def authentifier(self, login: str, mdp: str):
        u = self.utilisateur(login)
        if u is None:
            verifier_mdp(mdp, hacher_mdp("leurre-temps-constant"))   # même coût qu'un vrai essai
            return None
        if not u["actif"] or not verifier_mdp(mdp, u["hash"]):
            return None
        return u

    # sessions
    def ouvrir_session(self, uid: int) -> str:
        jeton = secrets.token_urlsafe(32)
        with self.tx() as cx:
            cx.execute("DELETE FROM sessions WHERE expire < ?", (time.time(),))
            cx.execute("INSERT INTO sessions VALUES (?, ?, ?)", (_empreinte(jeton), uid, time.time() + DUREE_SESSION))
        return jeton

    def session(self, jeton: str | None):
        if not jeton:
            return None
        return self._cx.execute(
            "SELECT u.* FROM sessions s JOIN utilisateurs u ON u.id = s.utilisateur "
            "WHERE s.empreinte = ? AND s.expire > ? AND u.actif = 1", (_empreinte(jeton), time.time())).fetchone()

    def fermer_session(self, jeton: str | None) -> None:
        if jeton:
            with self.tx() as cx:
                cx.execute("DELETE FROM sessions WHERE empreinte = ?", (_empreinte(jeton),))

    # données
    def lire_etat(self, uid: int) -> tuple[dict | None, int]:
        r = self._cx.execute("SELECT json, version FROM etats WHERE utilisateur = ?", (uid,)).fetchone()
        return (json.loads(r["json"]), r["version"]) if r else (None, 0)

    def ecrire_etat(self, uid: int, etat: dict, version: int) -> int:
        """Écrit si `version` est la version courante ; sinon lève ConflitVersion."""
        data = json.dumps(etat, ensure_ascii=False, separators=(",", ":"))
        if len(data.encode()) > TAILLE_MAX_ETAT:
            raise ValueError("Données trop volumineuses.")
        with self.tx() as cx:
            r = cx.execute("SELECT version FROM etats WHERE utilisateur = ?", (uid,)).fetchone()
            courante = r["version"] if r else 0
            if version != courante:
                raise ConflitVersion(courante)
            cx.execute("INSERT INTO etats VALUES (?, ?, ?, ?) ON CONFLICT(utilisateur) DO UPDATE "
                       "SET json = excluded.json, version = excluded.version, maj = excluded.maj",
                       (uid, data, courante + 1, time.time()))
            return courante + 1

    def lire_operations_sync(self, uid: int) -> list:
        r = self._cx.execute("SELECT json FROM operations_sync WHERE utilisateur = ?", (uid,)).fetchone()
        return json.loads(r["json"]) if r else []

    def ecrire_operations_sync(self, uid: int, ops: list) -> None:
        with self.tx() as cx:
            cx.execute("INSERT INTO operations_sync VALUES (?, ?, ?) ON CONFLICT(utilisateur) DO UPDATE "
                       "SET json = excluded.json, maj = excluded.maj",
                       (uid, json.dumps(ops, ensure_ascii=False), time.time()))


class ConflitVersion(Exception):
    def __init__(self, courante: int):
        super().__init__(courante)
        self.courante = courante


class LimiteurConnexion:
    """Au plus `essais` échecs par fenêtre de `fenetre` secondes, par IP et par identifiant."""

    def __init__(self, essais: int = 8, fenetre: int = 900):
        self.essais, self.fenetre = essais, fenetre
        self._echecs: dict[str, list[float]] = {}

    def _actifs(self, cle: str) -> list[float]:
        t = time.monotonic()
        self._echecs[cle] = [x for x in self._echecs.get(cle, []) if t - x < self.fenetre]
        return self._echecs[cle]

    def bloque(self, *cles: str) -> bool:
        return any(len(self._actifs(c)) >= self.essais for c in cles)

    def echec(self, *cles: str) -> None:
        for c in cles:
            self._actifs(c).append(time.monotonic())

    def reussite(self, *cles: str) -> None:
        for c in cles:
            self._echecs.pop(c, None)


def base_depuis_env(defaut: Path) -> Base:
    b = Base(os.getenv("PILOTAGE_DB", str(defaut)))
    login, mdp = os.getenv("PILOTAGE_ADMIN_LOGIN"), os.getenv("PILOTAGE_ADMIN_MDP")
    if login and mdp and b.nb_utilisateurs() == 0:
        b.creer_utilisateur(login, mdp, "admin")
    return b
