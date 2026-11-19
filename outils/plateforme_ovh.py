"""Opérations OVH sur le serveur dédié : lecture, modèles d'OS, réinstallation (clé SSH incluse), suivi de tâche.

La réinstallation EFFACE le disque : `reinstaller` refuse (ErreurAccord) sans accord explicite, avant tout appel réseau.
La clé publique SSH voyage dans `customizations.sshKey` de `POST /reinstall`. Aucun secret dans les messages d'erreur.
"""
import re
from urllib.parse import quote

from ovh_api import ErreurOvh

OS_CIBLE = "ubuntu2404-server_64"   # Ubuntu 24.04 LTS : système cible fixe (dépôt Docker officiel et images GameCI éprouvés dessus)


class ErreurAccord(Exception):
    """Action destructive demandée sans l'accord explicite de l'utilisateur."""


class ErreurAvantEcriture(Exception):
    """Échec prouvé AVANT l'envoi de la requête qui efface le disque : rien n'est parti, une nouvelle tentative est sûre."""


def _serveur(nom):
    return "/dedicated/server/" + quote(nom, safe="")


def lire_serveur(client, nom):
    d = client.appeler("GET", _serveur(nom)) or {}
    return {"os": d.get("os"), "ip": d.get("ip"), "etat": d.get("state"), "modele": d.get("commercialRange")}


def modeles_os(client, nom):
    """Noms des modèles d'installation compatibles (listes `ovh` et `personal` fusionnées)."""
    d = client.appeler("GET", _serveur(nom) + "/install/compatibleTemplates") or {}
    if isinstance(d, list):
        return list(d)
    return list(d.get("ovh") or []) + list(d.get("personal") or [])


def est_ubuntu_lts(nom_os):
    """Ubuntu LTS (année paire, avril : 22.04, 24.04, 26.04 ...) : jamais réinstallé s'il est déjà là."""
    m = re.match(r"ubuntu(\d{2})(\d{2})", (nom_os or "").lower())
    return bool(m and int(m.group(1)) % 2 == 0 and m.group(2) == "04")


def choisir_os_cible(modeles):
    """`OS_CIBLE` s'il est proposé par OVH pour ce serveur ; sinon ValueError (la réinstallation n'est pas tentée)."""
    if OS_CIBLE not in modeles:
        raise ValueError(f"Le modèle {OS_CIBLE} (Ubuntu 24.04 LTS) n'est pas proposé par OVH pour ce serveur : "
                         "la réinstallation n'est pas tentée.")
    return OS_CIBLE


def reinstaller(client, nom, modele_os, cle_publique, accord):
    """Lance la réinstallation (efface le disque) avec la clé publique SSH et renvoie l'id de tâche.

    Le contrôle d'accord précède tout appel réseau ; le modèle est vérifié (lecture seule) avant l'unique écriture.
    """
    if accord is not True:
        raise ErreurAccord("La réinstallation efface le disque du serveur : l'accord explicite est requis.")
    cle = cle_publique.strip() if isinstance(cle_publique, str) else ""
    if not cle:
        raise ValueError("La clé publique SSH est vide : la réinstallation n'est pas lancée.")
    try:
        compatibles = modeles_os(client, nom)
    except (ErreurOvh, OSError) as e:      # lecture seule, avant l'unique écriture : rien n'est parti
        raise ErreurAvantEcriture(f"Vérification du modèle impossible avant la réinstallation ({e}) : rien n'a été demandé.") from None
    if modele_os not in compatibles:
        raise ValueError(f"Le modèle « {modele_os} » n'est pas compatible avec ce serveur.")
    reponse = client.appeler("POST", _serveur(nom) + "/reinstall",
                             {"operatingSystem": modele_os, "customizations": {"sshKey": cle}})
    try:
        return int(reponse["taskId"])
    except (KeyError, TypeError, ValueError):
        raise ErreurOvh(0, "la réinstallation a été lancée mais l'identifiant de tâche est inconnu : "
                           "vérifiez l'état du serveur dans l'espace client OVH") from None


def etat_tache(client, nom, id_tache):
    statut = (client.appeler("GET", f"{_serveur(nom)}/task/{int(id_tache)}") or {}).get("status")
    if statut == "done":
        return "fini"
    if statut in ("error", "cancelled", "customerError", "ovhError"):
        return "echec"
    return "en_cours"
