"""Exécuteur SSH et clé dédiée de la plateforme (client OpenSSH de Windows).

Règles : jamais `StrictHostKeyChecking=no` (`accept-new`), toujours `BatchMode=yes` et `PasswordAuthentication=no`
(aucun mot de passe), clé dédiée `-i`. Un texte sensible (licence) passe par l'entrée standard (`input=` du runner),
jamais dans les arguments de la commande. `oublier_hote` retire une empreinte connue : accord explicite requis.
Tout sous-processus passe par `runner` (injectable) : les tests ne font aucune connexion réelle.
"""
import subprocess
import time
from pathlib import Path

from plateforme_ovh import ErreurAccord

NOM_CLE = "id_ed25519_myiafactory"


class ErreurSsh(Exception):
    """Le client OpenSSH est introuvable ou un utilitaire SSH n'a pas répondu à temps."""


def _lancer(runner, args, delai, entree=None):
    """Lance `args` : entrée standard fermée sans `entree` (jamais d'invite qui bloque), erreurs lisibles."""
    options = {"input": entree} if entree is not None else {"stdin": subprocess.DEVNULL}
    try:
        return runner(args, capture_output=True, text=True, timeout=delai, **options)
    except FileNotFoundError:
        raise ErreurSsh(f"« {args[0]} » est introuvable : le client OpenSSH de Windows est requis "
                        "(Paramètres > Applications > Fonctionnalités facultatives > Client OpenSSH).") from None


def _verifier_hote(hote):
    if not isinstance(hote, str) or not hote.strip() or hote.startswith("-"):
        raise ValueError("Adresse du serveur invalide : elle ne doit être ni vide ni commencer par un tiret.")


def _options(cle):
    return ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "PasswordAuthentication=no", "-o", "IdentitiesOnly=yes", "-i", str(cle)]


def _lancer_court(runner, args, delai):
    try:
        return _lancer(runner, args, delai)
    except subprocess.TimeoutExpired:
        raise ErreurSsh(f"« {args[0]} » n'a pas répondu en {delai} s.") from None


def generer_cle(dossier, runner=subprocess.run):
    """Renvoie (chemin privé, clé publique) ; crée la clé ed25519 sans phrase de passe si elle n'existe pas.

    Une clé existante n'est jamais régénérée ni écrasée.
    """
    dossier = Path(dossier)
    prive = dossier / NOM_CLE
    publique = Path(str(prive) + ".pub")
    if prive.exists():
        if not publique.exists():
            r = _lancer_court(runner, ["ssh-keygen", "-y", "-f", str(prive)], 30)
            if r.returncode != 0:
                raise RuntimeError("La clé privée existe mais sa partie publique n'a pu être relue.")
            return prive, (r.stdout or "").strip()
        return prive, publique.read_text(encoding="utf-8").strip()
    dossier.mkdir(parents=True, exist_ok=True)
    r = _lancer_court(runner, ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "myiafactory", "-f", str(prive)], 60)
    if r.returncode != 0 or not publique.exists():
        raise RuntimeError("La génération de la clé SSH a échoué.")
    return prive, publique.read_text(encoding="utf-8").strip()


def executer(hote, commande, cle, stdin=None, delai=60, runner=subprocess.run):
    """Exécute `commande` sur l'hôte ; renvoie (code, sortie, erreur). Un dépassement de délai donne un code 124."""
    _verifier_hote(hote)
    args = ["ssh", *_options(cle), "-o", f"ConnectTimeout={max(1, min(int(delai), 30))}", "--", hote, commande]
    try:
        r = _lancer(runner, args, delai, stdin)
    except subprocess.TimeoutExpired:
        return 124, "", f"délai dépassé ({delai} s)"
    return r.returncode, r.stdout or "", r.stderr or ""


def attendre_ssh(hote, cle, delai_total, pas=10, runner=subprocess.run, dormir=time.sleep):
    """Réessaie une commande triviale jusqu'au succès ; renvoie False une fois `delai_total` secondes écoulées."""
    ecoule = 0
    while True:
        if executer(hote, "true", cle, delai=min(pas, 30), runner=runner)[0] == 0:
            return True
        if ecoule >= delai_total:
            return False
        dormir(pas)
        ecoule += pas
        if ecoule >= delai_total:
            return False


def oublier_hote(hote, accord, runner=subprocess.run):
    """Retire l'hôte de known_hosts (`ssh-keygen -R`) ; exige un accord strictement booléen."""
    if accord is not True:
        raise ErreurAccord("Oublier l'empreinte de l'hôte exige l'accord explicite de l'utilisateur.")
    _verifier_hote(hote)
    _lancer_court(runner, ["ssh-keygen", "-R", hote], 30)
