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


AVIS_COURT = f"Mot de passe trop court dans {FICHIER_MDP} : remplacé par un mot de passe généré."


def _ecrire_atomique(chemin, mdp):
    """Temporaire créé en 0600 (O_EXCL) dans le même dossier, écrit puis `os.replace` : jamais de fichier tronqué."""
    tmp = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
    try:
        tmp.unlink()
    except OSError:
        pass
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    try:
        _restreindre_windows(tmp)        # avant d'y écrire le secret
        with os.fdopen(fd, "wb") as f:
            f.write((mdp + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, chemin)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _lire_ou_generer(dossier):
    """(mot de passe, avis) ; l'avis est non vide quand un fichier trop court a été remplacé. Un fichier présent mais
    inaccessible lève OSError : il n'est jamais écrasé à l'aveugle."""
    chemin = Path(dossier) / FICHIER_MDP
    avis = ""
    try:
        brut = chemin.read_text(encoding="utf-8-sig")
        premiere = (brut.splitlines() or [""])[0].strip()
        if len(premiere) >= LONGUEUR_MIN:
            return premiere, ""
        avis = AVIS_COURT
    except FileNotFoundError:
        pass
    except UnicodeDecodeError:
        avis = AVIS_COURT
    mdp = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_MDP))
    Path(dossier).mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(chemin, mdp)
    return mdp, avis


def mot_de_passe(dossier):
    """Relit le mot de passe de session (1re ligne, 16 caractères au moins) ou en génère un et l'écrit."""
    return _lire_ou_generer(dossier)[0]


def etape_bureau_distant(c, lancer_etape):
    """Envoie le mot de passe par stdin à l'étape distante `bureau_distant` ; renvoie son rapport."""
    try:
        mdp, avis = _lire_ou_generer(c.dossier)
    except OSError as e:
        return {"statut": "bloque", "detail": f"Mot de passe de session illisible ou impossible à écrire ({type(e).__name__}).",
                "geste": f"Vérifiez les droits de {Path(c.dossier) / FICHIER_MDP}, puis relancez."}
    if mdp not in c.secrets:
        c.secrets.append(mdp)        # masqué partout AVANT le premier envoi
    r = lancer_etape(c, "bureau_distant", stdin=mdp + "\n")
    if avis:
        r["detail"] = f"{avis} {r.get('detail', '')}".strip()
    if r["statut"] == "fait":
        r["geste"] = (f"Lancez py -3.12 lancer.py plateforme bureau-distant pour ouvrir la session ; "
                      f"le mot de passe est dans {Path(c.dossier) / FICHIER_MDP}.")
    return r
