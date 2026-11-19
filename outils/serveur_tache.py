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
            raise ValueError("Limite inconnue : " + repr(str(cle)[:40]) + ".")
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
        raise ValueError("Champ inconnu dans la demande : " + ", ".join(sorted(repr(str(c)[:40]) for c in inconnues)) + ".")
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
TEMOIN_PERIME_S = 30
VERROU_VIDE_S = 5          # fichier verrou vide ou illisible plus vieux que cela : créé puis jamais rempli (arrêt brutal)
ATTENTE_S = 10.0
PAUSE_S = 0.02
_VERROU_PROCESSUS = threading.Lock()


def _id_valide(ident):
    if not isinstance(ident, str) or not MOTIF_ID.fullmatch(ident):
        raise ValueError("Identifiant de tâche invalide.")


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
    except (ValueError, RecursionError, AttributeError):
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
    `serveur_installation`. Un verrou est périmé si son pid est mort ou est le nôtre (le verrou de processus est pris),
    ou si le fichier est vide/invalide depuis plus de 5 s. La reprise est exclusive : un seul repreneur à la fois, grâce
    au fichier témoin `taches.lock.reprise` (créé en `x`, toujours retiré ; un témoin périmé se retire selon la même
    règle, ou après 30 s). Sous le témoin le verrou est relu, sa péremption revérifiée sur CETTE lecture, et il n'est
    supprimé que s'il est encore périmé (le témoin est relu juste avant : s'il n'est plus à nous, on renonce) ; il
    n'est jamais renommé. Reste, honnêtement : (1) un repreneur bloqué plus de 30 s en tenant le témoin peut se le voir
    retirer par un autre, et deux repreneurs peuvent alors agir en même temps ; (2) un créateur bloqué plus de 5 s entre
    la création du fichier verrou et l'écriture de son pid (fichier alors vide) peut se voir reprendre son verrou ; (3) la
    suppression du fichier verrou par un tiers qui ne respecte pas le protocole n'est pas détectée. Le fichier verrou est
    écrit après création en `x` (pas de `os.link` d'un temporaire : absent des systèmes de fichiers FAT/exFAT)."""

    def __init__(self, dossier=plateforme_acces.DOSSIER, attente=ATTENTE_S, vivant=pid_vivant, pid=os.getpid):
        self.dossier = Path(dossier)
        self.attente = attente
        self.vivant = vivant
        self.pid = pid
        self._avant_temoin = None            # points d'arrêt des tests : avant la prise du témoin,
        self._apres_verification = None      # puis entre la vérification sous témoin et la suppression

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
        except (OSError, ValueError, RecursionError):
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
        except (ValueError, RecursionError):
            return {}

    def enregistrer(self, ident, fiche):
        _id_valide(ident)
        if not isinstance(fiche, dict) or fiche.get("etat") not in ETATS:
            raise ValueError("Fiche de tâche invalide : « etat » doit valoir " + ", ".join(ETATS) + ".")
        copie = dict(fiche)
        self._modifier(lambda tout: tout.__setitem__(ident, copie))

    def retirer(self, ident):
        _id_valide(ident)
        self._modifier(lambda tout: tout.pop(ident, None))

    def _modifier(self, agir):
        with self._verrou():
            tout = self._lire_pour_ecrire()
            agir(tout)
            ecrire_atomique(self.chemin, json.dumps(tout, ensure_ascii=False, indent=2) + "\n")

    def _perime(self, genre, valeur):
        if genre == "pid":
            return valeur == self.pid() or not self.vivant(valeur)
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
                    if _pid_verrou(self.chemin) == ("pid", index.pid()):     # jamais le verrou d'un autre
                        self.chemin.unlink()
                except OSError:
                    pass
                finally:
                    _VERROU_PROCESSUS.release()
        return _Verrou()

    def _temoin_perime(self, temoin):
        genre, valeur = _pid_verrou(temoin)
        if genre == "absent":
            return False
        if genre == "pid" and self._perime(genre, valeur):
            return True
        try:
            return (time.time() - temoin.stat().st_mtime > TEMOIN_PERIME_S
                    or (genre == "invalide" and valeur > VERROU_VIDE_S))
        except OSError:
            return False

    def _reprendre(self, chemin):
        """Retire un verrou périmé, un seul repreneur à la fois (fichier témoin). Vrai si le verrou a disparu."""
        temoin = chemin.with_name(chemin.name + ".reprise")
        if self._avant_temoin is not None:
            self._avant_temoin()
        try:
            with open(temoin, "x", encoding="utf-8") as f:
                f.write(json.dumps({"pid": self.pid()}))
        except FileExistsError:
            if self._temoin_perime(temoin):
                try:
                    temoin.unlink()
                except OSError:
                    pass
            return False
        except OSError:
            return False
        try:
            genre, valeur = _pid_verrou(chemin)          # relu sous le témoin : c'est CETTE lecture qui décide
            if genre == "absent":
                return True
            if not self._perime(genre, valeur):
                return False
            if self._apres_verification is not None:
                self._apres_verification()
            if _pid_verrou(temoin) != ("pid", self.pid()):   # témoin repris par un autre (nous étions trop lents)
                return False
            try:
                chemin.unlink()
            except OSError:
                return False
            return True
        finally:
            try:
                if _pid_verrou(temoin) == ("pid", self.pid()):
                    temoin.unlink()
            except OSError:
                pass

    def _prendre(self, limite):
        chemin = self.dossier / VERROU
        self.dossier.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                with open(chemin, "x", encoding="utf-8") as f:
                    f.write(json.dumps({"pid": self.pid()}))
                return chemin
            except FileExistsError:
                genre, valeur = _pid_verrou(chemin)
                repris = self._perime(genre, valeur) and self._reprendre(chemin)
            if time.monotonic() >= limite:
                raise TimeoutError("Index des tâches occupé : réessayez.")
            if not repris:
                time.sleep(PAUSE_S)
