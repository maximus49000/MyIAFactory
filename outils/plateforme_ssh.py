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


def _options(cle):
    return ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "PasswordAuthentication=no", "-i", str(cle)]


def generer_cle(dossier, runner=subprocess.run):
    """Renvoie (chemin privé, clé publique) ; crée la clé ed25519 sans phrase de passe si elle n'existe pas.

    Une clé existante n'est jamais régénérée ni écrasée.
    """
    dossier = Path(dossier)
    prive = dossier / NOM_CLE
    publique = Path(str(prive) + ".pub")
    if prive.exists():
        if not publique.exists():
            r = runner(["ssh-keygen", "-y", "-f", str(prive)], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise RuntimeError("La clé privée existe mais sa partie publique n'a pu être relue.")
            return prive, (r.stdout or "").strip()
        return prive, publique.read_text(encoding="utf-8").strip()
    dossier.mkdir(parents=True, exist_ok=True)
    r = runner(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "myiafactory", "-f", str(prive)],
               capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not publique.exists():
        raise RuntimeError("La génération de la clé SSH a échoué.")
    return prive, publique.read_text(encoding="utf-8").strip()


def executer(hote, commande, cle, stdin=None, delai=60, runner=subprocess.run):
    """Exécute `commande` sur l'hôte ; renvoie (code, sortie, erreur). Un dépassement de délai donne un code 124."""
    args = ["ssh", *_options(cle), "-o", f"ConnectTimeout={max(1, min(int(delai), 30))}", hote, commande]
    try:
        r = runner(args, input=stdin, capture_output=True, text=True, timeout=delai)
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
    runner(["ssh-keygen", "-R", hote], capture_output=True, text=True, timeout=30)
