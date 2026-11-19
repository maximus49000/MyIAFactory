"""Migration du serveur OVH déjà installé (ancien flux « plateforme ») vers la liste générique des serveurs.

`detecter` ne lit que des fichiers (`ovh.json` pour vérifier sa présence, `plateforme.json` pour l'adresse, la clé dédiée pour
son chemin) et ne se connecte à rien ; `apercu` ne fait que des sondes SSH en lecture seule ; `confirmer` n'écrit qu'avec
`accord is True` : l'entrée dans `serveurs.json` puis l'état sondé dans `serveurs-etat.json`, ou rien du tout.

Jamais : lecture ou affichage d'une clé privée ou d'un secret OVH, appel au fournisseur OVH (aucune réinstallation, aucune
lecture), modification de `ovh.json`, de `plateforme.json` ou du serveur. Les anciens fichiers restent (retour arrière).
"""
import json
import os
from dataclasses import asdict
from pathlib import Path

import plateforme_ssh
import serveur_etat
import serveur_installation
import serveur_modele
from plateforme_acces import DOSSIER, ErreurAcces, charger_ovh

UTILISATEUR = "ubuntu"
NOM = "Serveur OVH"
CACHE = "plateforme.json"
OVH = "ovh.json"


class ErreurMigration(Exception):
    """Refus de migrer. `code` : « accord » (400), « deja » (409), « occupe » (409)."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _cle_dediee(dossier):
    return Path(os.path.abspath(os.path.expanduser(str(Path(dossier) / plateforme_ssh.NOM_CLE))))


def _ip_du_cache(dossier):
    try:
        donnees = json.loads((Path(dossier) / CACHE).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    ip = donnees.get("ip") if isinstance(donnees, dict) else None
    return ip.strip() if isinstance(ip, str) and ip.strip() else None


def _deja_declare(dossier):
    """Vrai si `serveurs.json` existe avec la moindre entrée, valide ou non (ou est abîmé) : on n'y touche pas."""
    serveurs, rejets = serveur_modele.lire_avec_rejets(dossier)
    return bool(serveurs or rejets)


def detecter(dossier=DOSSIER):
    """La proposition `{"serveur": Serveur, "source": [noms de fichiers]}`, ou `None`. Fichiers seulement, jamais de réseau."""
    try:
        if _deja_declare(dossier):
            return None
        charger_ovh(dossier)                 # présence et forme seulement : la valeur n'est ni gardée ni montrée
        ip = _ip_du_cache(dossier)
        cle = _cle_dediee(dossier)
        if ip is None or not cle.is_file():
            return None
        serveur = serveur_modele.valider({"nom": NOM, "id": "serveur-ovh", "hote": ip, "utilisateur": UTILISATEUR,
                                          "cle": str(cle), "fournisseur": "ovh"})
    except (ErreurAcces, ValueError, OSError):
        return None
    return {"serveur": serveur, "source": [OVH, CACHE, plateforme_ssh.NOM_CLE]}


def _serveur_de(proposition):
    try:
        brut = proposition["serveur"]
        return serveur_modele.valider(asdict(brut) if hasattr(brut, "__dataclass_fields__") else brut)
    except (KeyError, TypeError, ValueError):
        raise ErreurMigration("Proposition de migration illisible : relancez la détection.", "deja") from None


def apercu(proposition, ssh=plateforme_ssh):
    """La proposition et l'état réel des capacités (sondes SSH en lecture seule ; n'écrit aucun fichier).

    Serveur injoignable ou réponse illisible : toutes les capacités « inconnue », jamais « absente »."""
    serveur = _serveur_de(proposition)
    etat = serveur_etat.sonder(serveur, ssh=ssh)
    return {"serveur": serveur, "source": list(proposition.get("source", [])), "capacites": etat,
            "joignable": not all(s == serveur_etat.INCONNUE for s in etat.values())}


def confirmer(proposition, accord, dossier=DOSSIER, ssh=plateforme_ssh):
    """Déclare le serveur proposé et enregistre l'état de ses capacités. `accord` doit être exactement `True`.

    Tout ou rien : si l'état ne peut être écrit (installation en cours), `serveurs.json` retrouve son contenu d'avant.
    `ErreurMigration` sinon ; ne touche ni `ovh.json`, ni `plateforme.json`, ni le serveur, et n'appelle pas OVH."""
    if accord is not True:
        raise ErreurMigration("Migration refusée : l'accord n'a pas été donné.", "accord")
    serveur = _serveur_de(proposition)
    if _deja_declare(dossier):
        raise ErreurMigration("Un serveur est déjà déclaré : la migration n'a rien changé.", "deja")
    occupe = ErreurMigration("Une installation est en cours sur ce poste : réessayez à sa fin.", "occupe")
    if serveur_installation.installation_en_cours(dossier):
        raise occupe
    etat = serveur_etat.sonder(serveur, ssh=ssh)             # lecture seule, avant la moindre écriture
    charge = serveur_etat.charge(serveur, ssh=ssh) if not all(s == serveur_etat.INCONNUE for s in etat.values()) else None
    chemin = Path(dossier) / serveur_modele.FICHIER
    avant = chemin.read_bytes() if chemin.exists() else None     # absent ici (aucune entrée), gardé par prudence
    try:
        declare = serveur_modele.ajouter(serveur, dossier)
        try:
            serveur_installation.enregistrer_sonde(dossier, declare, etat, charge=charge)
        except serveur_installation.ErreurInstallation:
            raise occupe from None
    except BaseException:
        _restaurer(chemin, avant)
        raise
    return declare


def _restaurer(chemin, avant):
    try:
        if avant is None:
            chemin.unlink(missing_ok=True)
        else:
            serveur_modele.ecrire_atomique(chemin, avant.decode("utf-8"))
    except OSError:
        pass
