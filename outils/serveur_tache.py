"""Tâches d'émulation sur le serveur : demande validée, identifiant, index local `taches.json`.

L'index du poste n'est qu'un cache : la vérité est sur le serveur (`~/taches/<id>/etat.json`). Les sections
suivantes (lanceur, verbes) s'ajoutent à ce module.
"""
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import plateforme_acces
from plateforme import pid_vivant
from serveur_modele import ecrire_atomique

# ---------------------------------------------------------------- demande

LIMITES_DEFAUT = {"duree_s": 1200, "inactivite_s": 300, "captures": 50, "octets": 104857600}
ETATS = ("en_attente", "en_cours", "terminee", "echouee", "arretee")
TYPES = ("emulation",)
MODES = ("scenario", "pilote")
MOTIF_ID = re.compile(r"t\d{8}-\d{6}-[0-9a-f]{4}")
MOTIF_SCENARIO = re.compile(r"[a-z0-9_-]{1,40}")


@dataclass(frozen=True)
class Demande:
    id: str
    type: str
    projet: str
    mode: str
    scenario: object
    limites: dict
    demandeur: str
    apk: object


def nouvel_id(maintenant=time.time, hasard=secrets.token_hex):
    """`t<AAAAMMJJ-HHMMSS>-<4 hex>` (heure UTC)."""
    quand = datetime.fromtimestamp(maintenant(), timezone.utc)
    return f"t{quand:%Y%m%d-%H%M%S}-{hasard(2)}"


def _limites(brut):
    if brut is None:
        return dict(LIMITES_DEFAUT)
    if not isinstance(brut, dict):
        raise ValueError("Les limites doivent être un dictionnaire.")
    for cle in brut:
        if cle not in LIMITES_DEFAUT:
            raise ValueError(f"Limite inconnue : {str(cle)[:40]}.")
    sortie = dict(LIMITES_DEFAUT)
    for cle, v in brut.items():
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"La limite « {cle} » doit être un nombre entier.")
        if not 1 <= v <= LIMITES_DEFAUT[cle]:
            raise ValueError(f"La limite « {cle} » doit être comprise entre 1 et {LIMITES_DEFAUT[cle]}.")
        sortie[cle] = v
    return sortie


def _texte_court(valeur, nom, defaut=""):
    if valeur is None:
        return defaut
    if not isinstance(valeur, str) or len(valeur) > 200 or any(ord(c) < 32 for c in valeur):
        raise ValueError(f"Valeur invalide pour « {nom} ».")
    return valeur


def valider_demande(brut):
    """`Demande` validée ; `ValueError` (message français) sinon. Les limites ne dépassent jamais `LIMITES_DEFAUT`."""
    if not isinstance(brut, dict):
        raise ValueError("La demande doit être un dictionnaire.")
    if brut.get("type") != "emulation":
        raise ValueError("Type de tâche inconnu : seul « emulation » est accepté.")
    mode = brut.get("mode")
    if mode not in MODES:
        raise ValueError("Mode inconnu : « scenario » ou « pilote ».")
    scenario = brut.get("scenario")
    if mode == "scenario":
        if not isinstance(scenario, str) or not scenario:
            raise ValueError("Le mode scénario exige un scénario.")
        if not MOTIF_SCENARIO.fullmatch(scenario):
            raise ValueError("Nom de scénario invalide (a-z, 0-9, _ et - ; 40 caractères au plus).")
    elif scenario is not None and not (isinstance(scenario, str) and MOTIF_SCENARIO.fullmatch(scenario)):
        raise ValueError("Nom de scénario invalide (a-z, 0-9, _ et - ; 40 caractères au plus).")
    ident = brut["id"] if "id" in brut else nouvel_id()
    if not isinstance(ident, str) or not MOTIF_ID.fullmatch(ident):
        raise ValueError("Identifiant de tâche invalide.")
    return Demande(id=ident, type="emulation", projet=_texte_court(brut.get("projet"), "projet"), mode=mode,
                   scenario=scenario, limites=_limites(brut.get("limites")),
                   demandeur=_texte_court(brut.get("demandeur"), "demandeur"),
                   apk=_texte_court(brut.get("apk"), "apk", None))


# ---------------------------------------------------------------- index du poste

INDEX = "taches.json"
VERROU = "taches.lock"
VERROU_JEUNE_S = 30
ATTENTE_S = 10.0
_VERROU_PROCESSUS = threading.Lock()


class Index:
    """Cache local des tâches `{id: fiche}` (états : `ETATS`). Lecture sans exception ; écritures sous verrou."""

    def __init__(self, dossier=plateforme_acces.DOSSIER, attente=ATTENTE_S, vivant=pid_vivant):
        self.dossier = Path(dossier)
        self.attente = attente
        self.vivant = vivant

    @property
    def chemin(self):
        return self.dossier / INDEX

    def lire(self):
        try:
            donnees = json.loads(self.chemin.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in donnees.items() if isinstance(v, dict)} if isinstance(donnees, dict) else {}

    def enregistrer(self, ident, fiche):
        def agir(tout):
            tout[ident] = dict(fiche)
        self._modifier(agir)

    def retirer(self, ident):
        self._modifier(lambda tout: tout.pop(ident, None))

    def _modifier(self, agir):
        with self._verrou():
            tout = self.lire()
            agir(tout)
            ecrire_atomique(self.chemin, json.dumps(tout, ensure_ascii=False, indent=2) + "\n")

    def _verrou_tenu(self, chemin):
        """Pid d'un autre processus vivant, ou fichier vide trop récent pour être périmé (créé puis rempli)."""
        try:
            autre = json.loads(chemin.read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError, AttributeError):
            autre = None
        if isinstance(autre, int):
            return autre != os.getpid() and bool(self.vivant(autre))  # notre pid : verrou périmé (le verrou de processus est pris)
        try:
            return time.time() - chemin.stat().st_mtime < VERROU_JEUNE_S
        except OSError:
            return False

    def _verrou(self):
        index = self

        class _Verrou:
            def __enter__(self):
                limite = time.monotonic() + index.attente
                if not _VERROU_PROCESSUS.acquire(timeout=index.attente):
                    raise TimeoutError("Index des tâches occupé : réessayez.")
                try:
                    self.chemin = index._prendre(limite)
                except BaseException:
                    _VERROU_PROCESSUS.release()
                    raise

            def __exit__(self, *_):
                try:
                    self.chemin.unlink()
                except OSError:
                    pass
                _VERROU_PROCESSUS.release()
        return _Verrou()

    def _prendre(self, limite):
        chemin = self.dossier / VERROU
        self.dossier.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                with open(chemin, "x", encoding="utf-8") as f:
                    f.write(json.dumps({"pid": os.getpid()}))
                return chemin
            except FileExistsError:
                if not self._verrou_tenu(chemin):
                    try:
                        chemin.unlink()
                    except OSError:
                        pass
                    continue
            if time.monotonic() >= limite:
                raise TimeoutError("Index des tâches occupé : réessayez.")
            time.sleep(0.02)
