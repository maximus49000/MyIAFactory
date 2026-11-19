"""Lecture de l'état d'un serveur distant par SSH : capacités présentes, droits d'accès, charge. Lecture seule.

Règles : UNE connexion SSH par lecture, le script passe par l'entrée standard de `bash -s` (jamais dans les arguments),
aucune commande qui modifie le serveur. Chaque sonde du catalogue tourne dans son propre sous-shell (un `exit` ou une
option de shell ne déborde pas sur les autres) ; la sortie est une ligne `<id>=0|1` par capacité.

Une panne de connexion ou une sortie illisible donne « inconnue », JAMAIS « absente » : un souci de réseau ne doit pas
passer pour une capacité manquante (il déclencherait une installation à tort). Aucune fonction ne lève d'exception.
Tout passe par `ssh` (injectable, le module `plateforme_ssh` par défaut) : les tests ne font aucune connexion réelle.
"""
import math
import re

import plateforme_ssh
from serveur_capacites import CATALOGUE

PRESENTE, ABSENTE, INCONNUE = "presente", "absente", "inconnue"
_SAIN = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]*$")


def cible(serveur):
    """`utilisateur@hote` après contrôle ; `ValueError` avant toute connexion si une valeur est douteuse."""
    hote, utilisateur, cle = serveur.hote, serveur.utilisateur, serveur.cle
    if not isinstance(hote, str) or not _SAIN.match(hote):
        raise ValueError("Adresse du serveur invalide.")
    if not isinstance(utilisateur, str) or not _SAIN.match(utilisateur):
        raise ValueError("Utilisateur du serveur invalide.")
    if not cle or not str(cle).strip():
        raise ValueError("Clé SSH du serveur absente.")
    return f"{utilisateur}@{hote}"


_cible = cible      # ancien nom conservé


def _executer(serveur, script, ssh, runner, delai=60):
    """(code, sortie, erreur) d'un `bash -s` ; `ValueError` si l'hôte est invalide, `ErreurSsh` etc. remontent."""
    destination = _cible(serveur)
    options = {} if runner is None else {"runner": runner}
    code, sortie, erreur = ssh.executer(destination, "bash -s", serveur.cle, stdin=script, delai=delai, **options)
    return code, sortie if isinstance(sortie, str) else "", erreur if isinstance(erreur, str) else ""


def _lignes_cle_valeur(sortie):
    """{clé: valeur} des lignes `clé=valeur` ; une clé répétée avec des valeurs différentes devient None (contradiction)."""
    trouvees = {}
    for ligne in sortie.splitlines():
        cle, egal, valeur = ligne.strip().partition("=")
        if not egal or not cle:
            continue
        if cle in trouvees and trouvees[cle] != valeur:
            trouvees[cle] = None
        elif cle not in trouvees:
            trouvees[cle] = valeur
    return trouvees


def _script_sondes():
    return "\n".join(f'( {c.sonde} ) </dev/null >/dev/null 2>&1 && echo "{c.id}=0" || echo "{c.id}=1"'
                     for c in CATALOGUE.values()) + "\n"


def sonder(serveur, ssh=plateforme_ssh, runner=None):
    """{capacité: "presente" | "absente" | "inconnue"} pour TOUTES les capacités du catalogue (une seule connexion)."""
    tout_inconnu = {i: INCONNUE for i in CATALOGUE}
    try:
        code, sortie, _ = _executer(serveur, _script_sondes(), ssh, runner)
    except Exception:
        return tout_inconnu
    if code != 0:
        return tout_inconnu
    lues = _lignes_cle_valeur(sortie)
    etat = {}
    for i in CATALOGUE:
        etat[i] = {"0": PRESENTE, "1": ABSENTE}.get(lues.get(i), INCONNUE)
    return etat


_SCRIPT_ACCES = ('echo "user=$(id -un 2>/dev/null)"\n'
                 'sudo -n true </dev/null >/dev/null 2>&1 && echo "sudo=0" || echo "sudo=1"\n')


def refus_acces(serveur, ssh=plateforme_ssh, runner=None):
    """None si l'utilisateur n'est pas root et que `sudo -n true` réussit ; sinon la raison, en français."""
    hote = getattr(serveur, "hote", "?")
    try:
        code, sortie, erreur = _executer(serveur, _SCRIPT_ACCES, ssh, runner, delai=30)
    except ValueError as e:
        return f"Serveur refusé avant toute connexion : {e}"
    except Exception as e:
        return f"Connexion SSH impossible : {e}"
    if code != 0:
        if getattr(ssh, "CHANGEMENT_CLE", plateforme_ssh.CHANGEMENT_CLE) in erreur:
            return (f"L'empreinte SSH de {hote} a changé (serveur réinstallé, ou intrus). Si c'est bien votre serveur, "
                    f"oubliez l'ancienne empreinte vous-même : ssh-keygen -R {hote} ; rien n'est oublié automatiquement.")
        return f"Connexion SSH impossible vers {hote} (code {code}) : vérifiez l'adresse, la clé et le pare-feu."
    lues = _lignes_cle_valeur(sortie)
    utilisateur, sudo = lues.get("user"), lues.get("sudo")
    if not utilisateur or sudo not in ("0", "1"):
        return f"Réponse illisible de {hote} : impossible de vérifier les droits de l'utilisateur."
    if utilisateur == "root":
        return "L'utilisateur est root : créez un utilisateur avec sudo (sans mot de passe) et utilisez-le."
    if sudo != "0":
        return (f"L'utilisateur {utilisateur} n'a pas sudo sans mot de passe : sudo sans mot de passe obligatoire "
                "(ajoutez-le au groupe sudo avec NOPASSWD).")
    return None


_SCRIPT_CHARGE = ('read a b c rest </proc/loadavg; echo "load=$b"\n'
                  'echo "cpu=$(nproc)"\n'
                  "awk '/^MemTotal:/{t=$2} /^MemAvailable:/{l=$2} END{print \"memtotal=\" t; print \"memlibre=\" l}' /proc/meminfo\n"
                  'echo "conteneurs=$(docker ps -q 2>/dev/null | wc -l | tr -d \' \')"\n')


def charge(serveur, ssh=plateforme_ssh, runner=None):
    """{"charge_par_coeur", "memoire_libre_ratio", "conteneurs_outils"} ou None si injoignable ou illisible.
    La charge est la moyenne sur 5 minutes (plus stable que celle d'une minute)."""
    try:
        code, sortie, _ = _executer(serveur, _SCRIPT_CHARGE, ssh, runner, delai=30)
        if code != 0:
            return None
        v = _lignes_cle_valeur(sortie)
        coeurs, total, libre = int(v["cpu"]), int(v["memtotal"]), int(v["memlibre"])
        conteneurs, load = int(v["conteneurs"]), float(v["load"])
        if coeurs <= 0 or total <= 0 or libre < 0 or conteneurs < 0 or not math.isfinite(load) or load < 0:
            return None
        return {"charge_par_coeur": load / coeurs, "memoire_libre_ratio": min(1.0, libre / total),
                "conteneurs_outils": conteneurs}
    except Exception:
        return None
