"""Étape facultative « session graphique » de la plateforme : mot de passe de session et envoi à l'étape distante.

Le mot de passe vit dans `<dossier>/bureau-distant.txt` (UTF-8, réservé à l'utilisateur) et nulle part ailleurs : il est
envoyé par l'entrée standard SSH, ajouté aux secrets masqués AVANT tout envoi, jamais écrit dans le cache, l'état ni les journaux.
"""
import getpass
import os
import secrets
import subprocess
import sys
from pathlib import Path

FICHIER_MDP = "bureau-distant.txt"
LONGUEUR_MDP = 24
LONGUEUR_MIN = 16
ALPHABET = "".join(c for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0Oo1lI")


def _restreindre_windows(chemin):
    """Au mieux : retire les droits hérités et ne laisse que l'utilisateur courant (sans effet hors Windows)."""
    if sys.platform != "win32":
        return
    try:
        subprocess.run(["icacls", str(chemin), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:F"],
                       capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def mot_de_passe(dossier):
    """Relit le mot de passe de session (1re ligne, 16 caractères au moins) ou en génère un et l'écrit."""
    chemin = Path(dossier) / FICHIER_MDP
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
        if lignes and len(lignes[0].strip()) >= LONGUEUR_MIN:
            return lignes[0].strip()
    except (OSError, ValueError):
        pass
    mdp = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_MDP))
    Path(dossier).mkdir(parents=True, exist_ok=True)
    chemin.write_text(mdp + "\n", encoding="utf-8")
    try:
        os.chmod(chemin, 0o600)
    except OSError:
        pass
    _restreindre_windows(chemin)
    return mdp


def etape_bureau_distant(c, lancer_etape):
    """Envoie le mot de passe par stdin à l'étape distante `bureau_distant` ; renvoie son rapport."""
    mdp = mot_de_passe(c.dossier)
    if mdp not in c.secrets:
        c.secrets.append(mdp)        # masqué partout AVANT le premier envoi
    r = lancer_etape(c, "bureau_distant", stdin=mdp + "\n")
    if r["statut"] == "fait":
        r["geste"] = (f"Lancez py -3.12 lancer.py plateforme bureau-distant pour ouvrir la session ; "
                      f"le mot de passe est dans {Path(c.dossier) / FICHIER_MDP}.")
    return r
