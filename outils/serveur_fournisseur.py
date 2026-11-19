"""Fournisseurs de serveurs distants : interface commune et fournisseur OVH (enveloppe du code OVH existant, inchangé).

Construire un fournisseur ne touche ni le disque ni le réseau : les clés (`ovh.json`) sont lues au premier usage.
`lire` est strictement en lecture seule. Aucun secret dans les messages ajoutés ici.
"""
from typing import Protocol

import ovh_api
import plateforme_acces
import plateforme_ovh


class Fournisseur(Protocol):
    nom: str

    def lire(self, serveur) -> dict:
        """`{"os": str, "etat": str, "ip": str}` (lecture seule)."""

    def reinstaller(self, serveur, cle_publique: str, accord: bool) -> int:
        """Lance la réinstallation (efface le disque) et renvoie l'id de tâche ; `accord` doit être exactement True."""

    def etat_tache(self, serveur, id_tache: int) -> str:
        """`"en_cours"`, `"fini"` ou `"echec"`."""


class FournisseurOvh:
    nom = "ovh"

    def __init__(self, dossier=plateforme_acces.DOSSIER, client=None):
        self._dossier = dossier
        self._client = client
        self._acces = None

    def _charger(self):
        if self._acces is None:
            self._acces = plateforme_acces.charger_ovh(self._dossier)
        return self._acces

    def _client_ovh(self):
        if self._client is None:
            a = self._charger()
            self._client = ovh_api.ClientOvh(a["point"], a["cle_app"], a["secret"], a["consommateur"])
        return self._client

    def _nom_service(self, serveur):
        reglages = getattr(serveur, "reglages_fournisseur", None) or {}
        nom = reglages.get("serveur")
        if isinstance(nom, str) and nom.strip():
            return nom.strip()
        return self._charger()["serveur"]

    def lire(self, serveur):
        d = plateforme_ovh.lire_serveur(self._client_ovh(), self._nom_service(serveur))
        return {"os": d.get("os"), "etat": d.get("etat"), "ip": d.get("ip")}

    def reinstaller(self, serveur, cle_publique, accord):
        if accord is not True:      # avant tout accès disque ou réseau
            raise plateforme_ovh.ErreurAccord("La réinstallation efface le disque du serveur : l'accord explicite est requis.")
        return plateforme_ovh.reinstaller(self._client_ovh(), self._nom_service(serveur), plateforme_ovh.OS_CIBLE,
                                          cle_publique, accord)

    def etat_tache(self, serveur, id_tache):
        return plateforme_ovh.etat_tache(self._client_ovh(), self._nom_service(serveur), id_tache)


def obtenir(nom, dossier=plateforme_acces.DOSSIER, client=None):
    """Fournisseur du nom donné ; `None` pour un serveur sans fournisseur ; `ValueError` si le nom est inconnu."""
    if nom is None:
        return None
    if nom == "ovh":
        return FournisseurOvh(dossier, client)
    raise ValueError("Fournisseur inconnu : seuls « ovh » ou aucun fournisseur sont acceptés.")
