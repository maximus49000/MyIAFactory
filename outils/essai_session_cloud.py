"""Un essai unique : `claude --cloud` dans le faux terminal (pseudo-console Windows invisible), sur un vrai dépôt.

    py -3.12 outils/essai_session_cloud.py <dossier du projet> [--modele haiku] [--delai 180]

Le moteur n'utilise pas encore cette voie (voir docs/superpowers/specs/2026-11-12-sessions-cloud-design.md) : le
2026-11-12, `claude --cloud` (Claude Code 2.1.321) a accepté la pseudo-console mais s'est arrêté sur l'approbation du
dossier, que seul l'utilisateur peut donner. Cet essai permet de le refaire après avoir lancé une fois `claude` dans le
dossier du projet et répondu « Yes, I trust this folder ».

L'essai crée **une** session cloud (sur l'abonnement : la clé API est retirée de l'environnement) avec un message court
qui ne modifie rien. Il répond seulement aux écrans sans risque de la première utilisation (thème proposé, notes de
sécurité), s'arrête sur toute autre demande, et quitte le processus local quelques secondes après l'adresse de la
session. Il affiche ce qu'il a vu (fin de l'écran), sans jeton ni adresse e-mail.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moteur import appel, cloud, pseudo_terminal  # noqa: E402

MESSAGE = ("Lis la liste des fichiers du dépôt et réponds en une phrase ce que contient le projet ; ne modifie rien, "
           "ne committe rien.")


def masquer(texte):
    texte = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<e-mail>", texte)
    return re.sub(r"(sk-ant-[\w-]+|oauth[\w-]*|token[=:]\s*\S+)", "<jeton>", texte, flags=re.I)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("dossier")
    p.add_argument("--modele", default="haiku", choices=appel.MODELES)
    p.add_argument("--delai", type=int, default=180)
    a = p.parse_args(argv)
    if not pseudo_terminal.disponible():
        print("Pas de pseudo-console sur ce poste (Windows 10 1809 ou plus récent seulement).")
        return 2
    claude = appel.trouver_claude()
    if not claude:
        print("La commande claude n'est pas installée.")
        return 2
    try:
        r = cloud.essai_pseudo_terminal([claude, "--cloud", MESSAGE, "--model", a.modele], a.dossier,
                                        env=pseudo_terminal.environnement_sans(appel.VARIABLE_CLE), delai_s=a.delai)
    except cloud.ErreurCloud as e:
        print(f"Essai impossible : {e.raison}")
        return 1
    print(masquer(r["ecran"]))
    print("---")
    print(f"Issue : {r['issue']}" + (f" ; session {r['session']} ({r['adresse']})" if r["session"] else "")
          + (f" ; {r['raison']}" if r["raison"] else ""))
    return 0 if r["issue"] == "session" else 1


if __name__ == "__main__":
    sys.exit(main())
