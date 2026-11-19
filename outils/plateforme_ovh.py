"""Opérations OVH sur le serveur dédié : lecture, clé SSH, modèles d'OS, réinstallation, suivi de tâche.

La réinstallation EFFACE le disque : `reinstaller` refuse (ErreurAccord) sans accord explicite, avant tout appel réseau.
Aucun secret dans les messages d'erreur (la clé publique n'est pas un secret mais n'est pas répétée pour autant).
"""
import re
from urllib.parse import quote

from ovh_api import ErreurOvh


class ErreurAccord(Exception):
    """Action destructive demandée sans l'accord explicite de l'utilisateur."""


class ErreurCleSsh(Exception):
    """Une clé SSH du même nom existe déjà chez OVH avec un autre contenu."""


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


def choisir_ubuntu_lts(modeles):
    """Ubuntu Server LTS (année paire, avril) le plus récent, ex. `ubuntu2404-server_64`."""
    candidats = []
    for m in modeles:
        bas = m.lower()
        trouve = re.match(r"ubuntu(\d{2})(\d{2})", bas)
        if trouve and "server" in bas and int(trouve.group(1)) % 2 == 0 and trouve.group(2) == "04":
            candidats.append((int(trouve.group(1)), m))
    if not candidats:
        raise ValueError("Aucun modèle Ubuntu Server LTS n'est proposé par OVH pour ce serveur.")
    return max(candidats)[1]


def enregistrer_cle_ssh(client, nom_cle, cle_publique):
    cle = cle_publique.strip()
    try:
        client.appeler("POST", "/me/sshKey", {"keyName": nom_cle, "key": cle})
    except ErreurOvh as e:
        try:
            existante = client.appeler("GET", "/me/sshKey/" + quote(nom_cle, safe=""))
        except ErreurOvh:
            raise e from None
        if not isinstance(existante, dict) or not existante.get("key"):
            raise e from None
        if existante["key"].strip() == cle:
            return
        raise ErreurCleSsh(f"Une clé SSH nommée « {nom_cle} » existe déjà chez OVH avec un autre contenu.") from None


def reinstaller(client, nom, modele_os, nom_cle, accord):
    """Lance la réinstallation (efface le disque) et renvoie l'id de tâche."""
    if not accord:
        raise ErreurAccord("La réinstallation efface le disque du serveur : l'accord explicite est requis.")
    if modele_os not in modeles_os(client, nom):
        raise ValueError(f"Le modèle « {modele_os} » n'est pas compatible avec ce serveur.")
    reponse = client.appeler("POST", _serveur(nom) + "/install/start",
                             {"templateName": modele_os, "details": {"sshKeyName": nom_cle}})
    return int(reponse["taskId"])


def etat_tache(client, nom, id_tache):
    statut = (client.appeler("GET", f"{_serveur(nom)}/task/{int(id_tache)}") or {}).get("status")
    if statut == "done":
        return "fini"
    if statut in ("error", "cancelled", "customerError", "ovhError"):
        return "echec"
    return "en_cours"
