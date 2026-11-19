"""Gestion des comptes du pilotage MDB en ligne de commande.

    python -m app.pilotage_admin ajouter <login> [--admin]   (mot de passe demandé, non affiché)
    python -m app.pilotage_admin mdp <login>
    python -m app.pilotage_admin desactiver <login>
    python -m app.pilotage_admin activer <login>
    python -m app.pilotage_admin lister
"""

import sys
from datetime import datetime
from getpass import getpass

from . import config
from .pilotage_comptes import base_depuis_env


def main(argv: list[str]) -> None:
    base = base_depuis_env(config.ROOT / "data" / "pilotage.sqlite3")
    if not argv:
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "lister":
            for u in base.lister():
                etat = "actif" if u["actif"] else "désactivé"
                print(f"{u['login']:<24} {u['role']:<12} {etat:<10} créé le {datetime.fromtimestamp(u['cree']):%d/%m/%Y}")
        elif cmd == "ajouter" and args:
            mdp = getpass("Mot de passe : ")
            if getpass("Confirmer : ") != mdp:
                raise ValueError("Les deux saisies diffèrent.")
            base.creer_utilisateur(args[0], mdp, "admin" if "--admin" in args else "utilisateur")
            print(f"Compte {args[0]} créé.")
        elif cmd == "mdp" and args:
            u = base.utilisateur(args[0])
            if u is None:
                raise ValueError("Utilisateur inconnu.")
            mdp = getpass("Nouveau mot de passe : ")
            if getpass("Confirmer : ") != mdp:
                raise ValueError("Les deux saisies diffèrent.")
            base.changer_mdp(u["id"], mdp)
            print("Mot de passe changé ; les sessions ouvertes sont fermées.")
        elif cmd in ("desactiver", "activer") and args:
            base.activer(args[0], cmd == "activer")
            print(f"Compte {args[0]} {'activé' if cmd == 'activer' else 'désactivé'}.")
        else:
            raise SystemExit(__doc__)
    except ValueError as e:
        raise SystemExit(f"Erreur : {e}") from None


if __name__ == "__main__":
    main(sys.argv[1:])
