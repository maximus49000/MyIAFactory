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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import plateforme_acces
from plateforme import pid_vivant
from serveur_modele import ecrire_atomique

# ---------------------------------------------------------------- demande

LIMITES_DEFAUT = MappingProxyType({"duree_s": 1200, "inactivite_s": 300, "captures": 50, "octets": 104857600})
ETATS = ("en_attente", "en_cours", "terminee", "echouee", "arretee")
TYPES = ("emulation",)
MODES = ("scenario", "pilote")
CLES_DEMANDE = frozenset({"id", "type", "projet", "mode", "scenario", "limites", "demandeur", "apk"})
MOTIF_ID = re.compile(r"t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", re.ASCII)
MOTIF_SCENARIO = re.compile(r"[a-z0-9_-]{1,40}", re.ASCII)


@dataclass(frozen=True)
class Demande:
    id: str
    type: str
    projet: str
    mode: str
    scenario: object
    limites: object          # MappingProxyType : immuable
    demandeur: str
    apk: object


def nouvel_id(maintenant=time.time, hasard=secrets.token_hex):
    """`t<AAAAMMJJ-HHMMSS>-<4 hex>` (heure UTC)."""
    quand = datetime.fromtimestamp(maintenant(), timezone.utc)
    return f"t{quand:%Y%m%d-%H%M%S}-{hasard(2)}"


def _limites(brut):
    if brut is None:
        return MappingProxyType(dict(LIMITES_DEFAUT))
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
    return MappingProxyType(sortie)


def _controle(c):
    o = ord(c)
    return o < 32 or 0x7F <= o <= 0x9F or o in (0x2028, 0x2029)


def _texte_court(valeur, nom, defaut=""):
    if valeur is None:
        return defaut
    if not isinstance(valeur, str) or len(valeur) > 200 or any(_controle(c) for c in valeur):
        raise ValueError(f"Valeur invalide pour « {nom} ».")
    return valeur


def valider_demande(brut):
    """`Demande` validée ; `ValueError` (message français) sinon. Les limites ne dépassent jamais `LIMITES_DEFAUT`."""
    if not isinstance(brut, dict):
        raise ValueError("La demande doit être un dictionnaire.")
    inconnues = set(brut) - CLES_DEMANDE
    if inconnues:
        raise ValueError("Champ inconnu dans la demande : " + ", ".join(sorted(str(c)[:40] for c in inconnues)) + ".")
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
VERROU_VIDE_S = 5          # fichier verrou vide ou illisible plus vieux que cela : créé puis jamais rempli (arrêt brutal)
ATTENTE_S = 10.0
PAUSE_S = 0.02
_VERROU_PROCESSUS = threading.Lock()


class ErreurIndex(Exception):
    """L'index n'a pas pu être lu pour une modification (accès refusé, disque) : rien n'a été écrit."""


def _pid_verrou(chemin):
    """("absent", None) si le fichier n'existe pas ; ("pid", n) pour un pid valide (entier > 1, pas un booléen) ;
    ("invalide", age_s) sinon ; ("illisible", None) si l'accès échoue."""
    try:
        contenu = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "absent", None
    except OSError:
        return "illisible", None
    try:
        pid = json.loads(contenu).get("pid")
    except (ValueError, AttributeError):
        pid = None
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1:
        return "pid", pid
    try:
        return "invalide", time.time() - chemin.stat().st_mtime
    except OSError:
        return "absent", None


class Index:
    """Cache local des tâches `{id: fiche}` (états : `ETATS`). Lecture sans exception ; écritures sous verrou.

    Verrou : verrou de processus (fils) + fichier `taches.lock` créé en exclusif (`x`) avec le pid, comme
    `serveur_installation`. Un verrou périmé (pid mort, notre propre pid, fichier invalide de plus de 5 s) est repris en
    le renommant sous un nom unique puis en revérifiant son contenu avant de le supprimer. Reste : deux reprises
    simultanées d'un même verrou périmé se départagent par ce renommage (une seule réussit) ; un verrou vivant
    renommé par erreur est remis en place, avec une très brève absence possible du fichier."""

    def __init__(self, dossier=plateforme_acces.DOSSIER, attente=ATTENTE_S, vivant=pid_vivant):
        self.dossier = Path(dossier)
        self.attente = attente
        self.vivant = vivant

    @property
    def chemin(self):
        return self.dossier / INDEX

    @staticmethod
    def _analyser(contenu):
        donnees = json.loads(contenu)
        return {k: v for k, v in donnees.items() if isinstance(v, dict)} if isinstance(donnees, dict) else {}

    def lire(self):
        """Pour affichage : vide si absent, abîmé ou illisible. Jamais d'exception."""
        try:
            return self._analyser(self.chemin.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}

    def _lire_pour_ecrire(self):
        try:
            contenu = self.chemin.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return {}
        except OSError as e:
            raise ErreurIndex(f"Index des tâches illisible ({type(e).__name__}) : rien n'a été modifié.") from e
        try:
            return self._analyser(contenu)
        except ValueError:
            return {}

    def enregistrer(self, ident, fiche):
        if not isinstance(fiche, dict) or fiche.get("etat") not in ETATS:
            raise ValueError("Fiche de tâche invalide : « etat » doit valoir " + ", ".join(ETATS) + ".")
        copie = dict(fiche)
        self._modifier(lambda tout: tout.__setitem__(ident, copie))

    def retirer(self, ident):
        self._modifier(lambda tout: tout.pop(ident, None))

    def _modifier(self, agir):
        with self._verrou():
            tout = self._lire_pour_ecrire()
            agir(tout)
            ecrire_atomique(self.chemin, json.dumps(tout, ensure_ascii=False, indent=2) + "\n")

    def _perime(self, genre, valeur):
        if genre == "pid":
            return valeur == os.getpid() or not self.vivant(valeur)
        return genre == "invalide" and valeur > VERROU_VIDE_S

    def _verrou(self):
        index = self

        class _Verrou:
            def __enter__(self):
                limite = time.monotonic() + index.attente
                if not _VERROU_PROCESSUS.acquire(timeout=max(index.attente, 0)):
                    raise TimeoutError("Index des tâches occupé : réessayez.")
                try:
                    self.chemin = index._prendre(limite)
                except BaseException:
                    _VERROU_PROCESSUS.release()
                    raise

            def __exit__(self, *_):
                try:
                    if _pid_verrou(self.chemin) == ("pid", os.getpid()):     # jamais le verrou d'un autre
                        self.chemin.unlink()
                except OSError:
                    pass
                finally:
                    _VERROU_PROCESSUS.release()
        return _Verrou()

    def _reprendre(self, chemin):
        """Retire un verrou jugé périmé : renommé sous un nom unique, contenu revérifié, puis supprimé. Faux si échec."""
        mort = chemin.with_name(f"{chemin.name}.{os.getpid()}.{uuid.uuid4().hex}.perime")
        try:
            os.rename(chemin, mort)
        except OSError:
            return False
        genre, valeur = _pid_verrou(mort)
        if genre != "illisible" and self._perime(genre, valeur):
            try:
                mort.unlink()
            except OSError:
                pass
            return True
        try:                                     # c'était un verrou vivant : on le remet (sans écraser un nouveau)
            os.link(mort, chemin)
        except OSError:
            pass
        try:
            mort.unlink()
        except OSError:
            pass
        return False

    def _prendre(self, limite):
        chemin = self.dossier / VERROU
        self.dossier.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                with open(chemin, "x", encoding="utf-8") as f:
                    f.write(json.dumps({"pid": os.getpid()}))
                return chemin
            except FileExistsError:
                genre, valeur = _pid_verrou(chemin)
                if self._perime(genre, valeur) and self._reprendre(chemin):
                    continue
            if time.monotonic() >= limite:
                raise TimeoutError("Index des tâches occupé : réessayez.")
            time.sleep(PAUSE_S)
