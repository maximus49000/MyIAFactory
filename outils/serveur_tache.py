"""Tâches d'émulation sur le serveur : demande validée, identifiant, index local `taches.json`, motifs des verbes du
pont, lanceur (lancer, état, arrêt, rapatriement, relais d'un verbe).

L'index du poste n'est qu'un cache : la vérité est sur le serveur (`~/taches/<id>/etat.json`, écrit par
`serveur_ovh/taches/lancer_emulation.sh`). Sections : demande ; index du poste ; motifs du pont ; lanceur.
"""
import io
import json
import os
import re
import secrets
import shlex
import tarfile
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import plateforme
import plateforme_acces
import plateforme_ssh
import serveur_etat
import serveur_installation
import serveur_modele
from plateforme import DOSSIER_DISTANT, RACINE_SERVEUR, pid_vivant
from serveur_modele import ecrire_atomique

# ---------------------------------------------------------------- demande

# inactivite_s (mode pilote) : 600 s et non les 5 min de départ (décision R9) : elle doit dépasser le budget de démarrage
# de l'émulateur par le pont (PONT_DEMARRAGE_S, 300 s), sinon un `demarrer` lent serait pris pour de l'inactivité.
LIMITES_DEFAUT = MappingProxyType({"duree_s": 1200, "inactivite_s": 600, "captures": 50, "octets": 104857600})
INACTIVITE_MIN_S = 300           # mode pilote : jamais sous le budget de démarrage du pont
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
    limites = _limites(brut.get("limites"))
    if mode == "pilote" and limites["inactivite_s"] < INACTIVITE_MIN_S:
        raise ValueError(f"En mode pilote, « inactivite_s » doit valoir au moins {INACTIVITE_MIN_S} s (le démarrage de "
                         "l'émulateur peut durer jusque-là) et au plus " f"{LIMITES_DEFAUT['inactivite_s']} s.")
    return Demande(id=ident, type="emulation", projet=_texte_court(brut.get("projet"), "projet"), mode=mode,
                   scenario=scenario, limites=limites,
                   demandeur=_texte_court(brut.get("demandeur"), "demandeur"),
                   apk=_texte_court(brut.get("apk"), "apk", None))


# ---------------------------------------------------------------- index du poste

INDEX = "taches.json"
INDEX_MAX_OCTETS = 8 * 1024 * 1024        # au-delà, l'index n'est pas lu (affichage vide, écriture refusée)
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

    def _contenu(self):
        """Texte de l'index ; `ValueError` (message français) s'il dépasse INDEX_MAX_OCTETS (taille vérifiée avant la
        lecture, puis sur ce qui a été lu) ou s'il n'est pas en UTF-8."""
        if self.chemin.stat().st_size > INDEX_MAX_OCTETS:
            raise ValueError(f"Index des tâches démesuré (plus de {INDEX_MAX_OCTETS // (1024 * 1024)} Mo)")
        try:
            contenu = self.chemin.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Index des tâches illisible (pas en UTF-8)") from None
        if len(contenu) > INDEX_MAX_OCTETS:
            raise ValueError(f"Index des tâches démesuré (plus de {INDEX_MAX_OCTETS // (1024 * 1024)} Mo)")
        return contenu

    def lire(self):
        """Pour affichage : vide si absent, abîmé, illisible ou démesuré. Jamais d'exception."""
        try:
            return self._analyser(self._contenu())
        except (OSError, ValueError, RecursionError):
            return {}

    def _lire_pour_ecrire(self):
        try:
            contenu = self._contenu()
        except FileNotFoundError:
            return {}
        except OSError as e:
            raise ErreurIndex(f"Index des tâches illisible ({type(e).__name__}) : rien n'a été modifié.") from e
        except ValueError as e:      # démesuré ou pas en UTF-8 : jamais réécrit à partir de rien (il serait vidé)
            raise ErreurIndex(f"{e} : rien n'a été modifié.") from e
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

    def fusionner(self, ident, champs):
        """Ajoute `champs` à la fiche existante (créée si absente), lecture et écriture sous le même verrou : deux mises à
        jour simultanées de la même fiche ne se perdent pas. Une erreur de lecture transitoire lève `ErreurIndex` sans rien
        écrire (jamais une fiche réduite aux seuls nouveaux champs)."""
        _id_valide(ident)
        if not isinstance(champs, dict):
            raise ValueError("Champs de fiche invalides.")

        def agir(tout):
            fiche = {**(tout[ident] if isinstance(tout.get(ident), dict) else {}), **champs}
            if fiche.get("etat") not in ETATS:
                raise ValueError("Fiche de tâche invalide : « etat » doit valoir " + ", ".join(ETATS) + ".")
            tout[ident] = fiche
        self._modifier(agir)

    def reserver(self, ident, cle, maximum):
        """Incrémente le compteur `cle` de la fiche s'il est sous le maximum, lecture et écriture sous le verrou.
        `maximum` : un entier, ou une fonction de la fiche lue sous le verrou (jamais d'une lecture sans verrou).
        Renvoie (réservé, maximum appliqué)."""
        _id_valide(ident)
        resultat = []

        def agir(tout):
            fiche = tout.get(ident)
            if not isinstance(fiche, dict):
                raise ValueError("Tâche absente de l'index.")
            borne = maximum(fiche) if callable(maximum) else maximum
            n = fiche.get(cle, 0)
            n = n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else 0
            if n < borne:
                tout[ident] = {**fiche, cle: n + 1}
            resultat.append((n < borne, borne))
        self._modifier(agir)
        return resultat[0]

    def liberer(self, ident, cle):
        """Rend une réservation de `reserver` (jamais sous zéro)."""
        _id_valide(ident)

        def agir(tout):
            fiche = tout.get(ident)
            if isinstance(fiche, dict):
                n = fiche.get(cle, 0)
                if isinstance(n, int) and not isinstance(n, bool) and n > 0:
                    tout[ident] = {**fiche, cle: n - 1}
        self._modifier(agir)

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


# ---------------------------------------------------------------- motifs du pont (miroir de pont.sh, décision R2)

# Copie EXACTE de la table « MOTIFS DU PONT » en tête de serveur_ovh/taches/pont.sh. Le test
# test_motifs_python_et_pont_s_accordent fait passer les mêmes exemples par les deux. Toujours `re.fullmatch` avec
# `re.ASCII` (le `$` de Python accepterait un retour à la ligne final, celui de bash non).
MOTIF_ENTIER = r"[0-9]{1,4}"                              # coordonnée : 0 à 9999
MOTIF_DUREE = r"([0-9]{1,2}|1[01][0-9]|120)"               # attendre : 0 à 120 secondes
MOTIF_NOM = r"[a-z0-9][a-z0-9_-]{0,39}"                   # nom de capture
MOTIF_TEXTE = r"[A-Za-z0-9][A-Za-z0-9 .,_-]{0,59}"        # texte saisi
MOTIF_FILTRE = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,59}"        # filtre du journal
MOTIF_TOUCHE = r"(retour|accueil|menu)"
# Noms de capture refusés en plus de MOTIF_NOM : noms réservés de Windows (le poste ne pourrait pas écrire <nom>.png ;
# majuscules et extension déjà exclues par MOTIF_NOM). Même règle dans pont.sh (MOTIF_NOM_RESERVE).
MOTIF_NOM_RESERVE = r"(con|prn|aux|nul|com[0-9]|lpt[0-9])"
MOTIF_SECONDES_FILM = r"([1-9][0-9]?|1[0-7][0-9]|180)"    # filmer : 1 à 180 secondes
# verbe -> motifs de ses arguments, dans l'ordre ; FACULTATIFS : nombre de derniers arguments facultatifs.
VERBES = MappingProxyType({
    "demarrer": (), "installer": (), "lancer": (), "arreter": (),
    "toucher": (MOTIF_ENTIER, MOTIF_ENTIER),
    "glisser": (MOTIF_ENTIER, MOTIF_ENTIER, MOTIF_ENTIER, MOTIF_ENTIER),
    "texte": (MOTIF_TEXTE,),
    "touche": (MOTIF_TOUCHE,),
    "attendre": (MOTIF_DUREE,),
    "capturer": (MOTIF_NOM,),
    "journal": (MOTIF_FILTRE,),
    "filmer": (MOTIF_NOM, MOTIF_SECONDES_FILM),
    "finfilm": (),
})
FACULTATIFS = MappingProxyType({"journal": 1, "filmer": 1})
_NUMERIQUES = (MOTIF_ENTIER, MOTIF_DUREE, MOTIF_SECONDES_FILM)   # seuls arguments qui peuvent être donnés en entier Python


def valider_verbe(verbe, args):
    """Arguments validés (tuple de textes) ; `ValueError` en français sinon. Aucun texte refusé n'est recopié dans le
    message. Un entier Python (pas un booléen) est admis pour une coordonnée ou une durée, puis validé comme texte."""
    if not isinstance(verbe, str) or verbe not in VERBES:
        raise ValueError("Verbe inconnu : liste fermée (" + ", ".join(VERBES) + ").")
    if not isinstance(args, (list, tuple)):
        raise ValueError(f"Arguments de {verbe} : une liste est attendue.")
    motifs = VERBES[verbe]
    if not len(motifs) - FACULTATIFS.get(verbe, 0) <= len(args) <= len(motifs):
        raise ValueError(f"Nombre d'arguments refusé pour {verbe}.")
    sortie = []
    for i, (a, motif) in enumerate(zip(args, motifs), 1):
        if motif in _NUMERIQUES and isinstance(a, int) and not isinstance(a, bool):
            a = str(a)
        if not isinstance(a, str) or not re.fullmatch(motif, a, re.ASCII):
            raise ValueError(f"Argument {i} refusé pour {verbe} (forme non permise).")
        if motif == MOTIF_NOM and re.fullmatch(MOTIF_NOM_RESERVE, a, re.ASCII):
            raise ValueError(f"Argument {i} refusé pour {verbe} (nom réservé sous Windows).")
        sortie.append(a)
    return tuple(sortie)


# ---------------------------------------------------------------- lanceur
# Toute commande distante est un texte fixe où ne s'insèrent que des valeurs validées : identifiant (MOTIF_ID), mode
# (MODES), nombres entiers (limites validées), verbe et arguments (valider_verbe, puis shlex.quote pour les espaces de
# `texte`, en dernier recours). La première ligne de chaque script, `# tache:<opération> <id>`, est un simple commentaire
# pour le shell distant (et un repère pour les tests). Les données (APK, demande, enveloppe) passent par l'entrée
# standard dans une archive tar, jamais dans une commande.

class RefusLancement(ValueError):
    """Refus avant tout envoi (aucun serveur prêt, demande ou APK invalide) : message français, rien n'a été lancé."""


CAPACITES_REQUISES = ("android-emulateur", "emulateur-image")
STATUTS_PRETS = ("presente", "fait")
STATUTS_RAPPORT = ("ok", "plantage", "limite", "erreur")
FINAUX = ("terminee", "arretee", "echouee")
INJOIGNABLE = (124, 255)                   # délai dépassé, connexion SSH impossible
APK_MAX_OCTETS = 200 * 1024 * 1024
PAUSE_CRENEAU_S = 15
ESSAIS_ID = 5
CODE_EXISTE = 73                           # préparation : le dossier ~/taches/<id> existe déjà
VEILLEUR_ABSENT_S = 180                    # sans veilleur.pid si longtemps après « debut » : veilleur jamais né
#   (l'enveloppe écrit en_cours AVANT `docker run`, borné à 120 s, puis lance le veilleur : 180 s laisse la marge)
AVD_ATTENTE_S = 300
AVD_PAS_S = 5
REPONSE_PONT_MAX = 256 * 1024              # journal : 200 lignes de 500 caractères au plus, plus l'enveloppe JSON
ETAT_MAX = 4096
JOURNAL_MAX_OCTETS = 5 * 1024 * 1024       # chaque journal rapatrié ; au-delà il n'est pas rapatrié
LOGCAT_MAX_OCTETS = 2 * 1024 * 1024        # logcat.txt (sauvegarde des lignes de `journal`), plafonné aussi par le pont
VIDEO_MAX_OCTETS = 60 * 1024 * 1024        # chaque vidéo (mp4) ; toutes les médias partagent limites["octets"]
VIDEOS_MAX = 5                             # vidéos par tâche
IMAGES_PAR_FILM = 30                       # images tirées d'une vidéo (le pont en tire 30 au plus)
IMAGES_FILM_MAX = VIDEOS_MAX * IMAGES_PAR_FILM
# journaux + logcat + en-têtes tar (des 150 images comprises), en plus des médias
TAILLE_ARCHIVE_MARGE = 4 * JOURNAL_MAX_OCTETS + LOGCAT_MAX_OCTETS + 2 * 1024 * 1024
ENVELOPPE = "taches/lancer_emulation.sh"
ENVELOPPE_DISTANTE = f"{DOSSIER_DISTANT}/{ENVELOPPE}"
COMMUN = "taches/commun.sh"          # sourcé par l'enveloppe : déposé avec elle, juste avant elle
COMMUN_DISTANT = f"{DOSSIER_DISTANT}/{COMMUN}"
# Délai SSH de chaque verbe relayé, au-dessus de la borne propre du pont : `arreter` (adb + attentes 10 + 5 + 5 s, jusqu'à
# ~80 s, plus la fin d'un film resté en cours), `installer` (4 appels adb, jusqu'à ~180 s), `demarrer` (PONT_DEMARRAGE_S
# 300 s), `finfilm` (verrou, SIGINT et attente 10 s, adb pull, ffmpeg 120 s : jusqu'à ~250 s), `filmer` (1 s d'attente).
DELAIS_VERBE_S = MappingProxyType({"demarrer": 360, "installer": 240, "arreter": 480, "attendre": 150,
                                   "capturer": 150, "filmer": 60, "finfilm": 420})
DELAI_VERBE_S = 90
# Mémoire et processeurs du conteneur passés à l'enveloppe (ses propres valeurs par défaut : la demande ne les règle pas).
MEMOIRE_MO = 6144
CPUS = 2
# Fichiers rapatriés : ces journaux (nom sur le serveur -> nom local), captures/<nom>.png, videos/<nom>.mp4 et
# videos/<nom>-img/<nom>-NNN.png (le même nom dans le dossier et le fichier), rien d'autre.
JOURNAUX = MappingProxyType({"pont.log": "journal.txt", "plantage.txt": "plantage.txt",
                             "entree-tache.log": "entree-tache.log", "emulateur.log": "emulateur.log",
                             "logcat.txt": "logcat.txt"})
MOTIF_CAPTURE = re.compile(r"captures/([a-z0-9][a-z0-9_-]{0,39})\.png", re.ASCII)
MOTIF_VIDEO = re.compile(r"videos/([a-z0-9][a-z0-9_-]{0,39})\.mp4", re.ASCII)
MOTIF_IMAGE_FILM = re.compile(r"videos/([a-z0-9][a-z0-9_-]{0,39})-img/\1-([0-9]{3})\.png", re.ASCII)
MOTIF_DETAIL_FILM = re.compile(r"videos/([a-z0-9][a-z0-9_-]{0,39})\.mp4 \(", re.ASCII)   # réponse de finfilm
SIGNATURE_MP4 = b"ftyp"                    # octets 4 à 8 d'un fichier MP4 (boîte ftyp)
MOTIF_ISO = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", re.ASCII)
NOMS_RESERVES = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))})
SIGNATURE_PNG = b"\x89PNG\r\n\x1a\n"


def _maintenant_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _court(texte, n=300):
    return " ".join(str(texte or "").split())[:n]


def _masqueur(dossier):
    """Masque comme `outils/plateforme.py` : secrets d'ovh.json, licence, chemins des clés des serveurs."""
    c = plateforme._Contexte(dossier, False, None, None, None)
    try:
        c.preparer_secrets()
    except Exception:  # noqa: BLE001 - un fichier de secrets abîmé n'empêche pas de masquer les clés
        c.secrets = []
    c.secrets += [str(s.cle) for s in serveur_modele.lire(dossier) if len(str(s.cle)) >= 8]
    return c


def _masque(valeur, dossier):
    return _masqueur(dossier).masquer_arbre(valeur)


def _iso_valide(v):
    return v if isinstance(v, str) and MOTIF_ISO.fullmatch(v) else None


def _epoch(iso):
    try:
        return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
    except (TypeError, ValueError):
        return None


def _duree(lu):
    debut, fin = _epoch(lu.get("debut")), _epoch(lu.get("fin"))
    return fin - debut if debut is not None and fin is not None and fin >= debut else None


def _limites_fiche(fiche):
    brut = fiche.get("limites")
    try:
        return _limites(dict(brut) if isinstance(brut, dict) else None)
    except ValueError:
        return MappingProxyType(dict(LIMITES_DEFAUT))


def _noter(dossier, ident, champs):
    """Met à jour la fiche de l'index (champs masqués) ; None, ou le message si l'index a refusé (jamais d'exception)."""
    try:
        Index(dossier).fusionner(ident, {**_masque(champs, dossier), "maj": _maintenant_iso()})
    except (ErreurIndex, TimeoutError, ValueError, OSError) as e:
        return f"Index des tâches non mis à jour : {_court(e)}"
    return None


# --- choix du serveur et appels distants

def choisir_serveur(dossier=plateforme_acces.DOSSIER, requises=CAPACITES_REQUISES):
    """Premier serveur déclaré, joignable à la dernière sonde, avec les capacités `requises` présentes (par défaut
    `android-emulateur` et `emulateur-image` : tranche A ; état local `serveurs-etat.json` : aucune connexion) ;
    `RefusLancement` avec la raison sinon."""
    serveurs = serveur_modele.lire(dossier)
    if not serveurs:
        raise RefusLancement("Aucun serveur déclaré : déclarez-en un dans le bureau (Serveurs) ou par "
                             "« lancer.py plateforme serveurs declarer ».")
    connu = serveur_installation.lire_etat_vivant(dossier)
    raisons = []
    for s in serveurs:
        caps = (connu.get(s.id) or {}).get("capacites")
        caps = caps if isinstance(caps, dict) else {}
        statuts = {c: caps[c].get("statut") if isinstance(caps.get(c), dict) else None for c in requises}
        if all(v in STATUTS_PRETS for v in statuts.values()):
            return s
        if not caps:
            raisons.append(f"{s.id} : état inconnu (jamais sondé : lancez une sonde)")
        elif any(v == "inconnue" for v in statuts.values()):
            raisons.append(f"{s.id} : serveur injoignable ou état inconnu à la dernière sonde")
        else:
            def libelle(c):     # une capacité notée périmée par l'installation (empreinte) est dite « à mettre à jour »
                detail = caps[c].get("detail") if isinstance(caps.get(c), dict) else None
                detail = detail if isinstance(detail, str) else ""
                return f"{c} périmée (à mettre à jour)" if ("mettre à jour" in detail or "périm" in detail) else c
            raisons.append(f"{s.id} : capacité(s) absente(s) ou périmée(s) : "
                           + ", ".join(libelle(c) for c, v in statuts.items() if v not in STATUTS_PRETS))
    usage = "l'émulation" if tuple(requises) == CAPACITES_REQUISES else "un agent (" + ", ".join(requises) + ")"
    raise RefusLancement(f"Aucun serveur prêt pour {usage} (" + " ; ".join(raisons) + ").")


def _serveur_de(ident, dossier):
    """Serveur de la fiche (index local) ; sans fiche, le serveur que choisirait un lancement."""
    sid = (Index(dossier).lire().get(ident) or {}).get("serveur_id")
    if isinstance(sid, str):
        for s in serveur_modele.lire(dossier):
            if s.id == sid:
                return s
        raise RefusLancement(f"Le serveur « {_court(sid, 64)} » de cette tâche n'est plus déclaré.")
    return choisir_serveur(dossier)


def _bash(serveur, ssh, script, delai=60):
    """(code, sortie texte, erreur) d'un script passé à `bash -s` ; toute exception (hôte invalide, ssh absent) -> 255."""
    try:
        code, sortie, erreur = ssh.executer(serveur_etat.cible(serveur), "bash -s", serveur.cle, stdin=script,
                                            delai=delai)
    except Exception as e:  # noqa: BLE001
        return 255, "", f"{type(e).__name__} : {e}"
    return code, sortie if isinstance(sortie, str) else "", erreur if isinstance(erreur, str) else ""


def _octets(serveur, ssh, commande, entree, delai, silencieux=False):
    """(code, sortie octets, erreur) : octets intacts dans les deux sens. `silencieux` : variante sans bannière ni
    avertissement de ssh sur la sortie d'erreur (`executer_octets_silencieux`), quand l'appelant juge cette sortie."""
    appel = (getattr(ssh, "executer_octets_silencieux", None) if silencieux else None) or ssh.executer_octets
    try:
        code, sortie, erreur = appel(serveur_etat.cible(serveur), commande, serveur.cle, entree=entree, delai=delai)
    except Exception as e:  # noqa: BLE001
        return 255, b"", f"{type(e).__name__} : {e}"
    return code, sortie if isinstance(sortie, bytes) else b"", erreur if isinstance(erreur, str) else ""


def _archive(membres):
    """Archive tar en mémoire de (nom, octets, droits) : fichiers ordinaires, propriétaire root, octets tels quels.

    Mémoire (M8) : `BytesIO(donnees)` partage les octets de l'APK sans les copier, et `getvalue()` rend le tampon tel
    quel quand il n'a plus d'autre référence : l'APK ne coexiste qu'avec UNE copie (l'archive), mesuré par
    test_archive_sans_copie_superflue. L'archive est ensuite passée telle quelle à ssh (entrée standard), sans autre
    copie ici. La lecture de l'APK sur le poste n'alloue que sa taille (`serveur_tache_cli._lire_apk`)."""
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for nom, donnees, droits in membres:
            info = tarfile.TarInfo(nom)
            info.size, info.mode, info.mtime = len(donnees), droits, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


# --- scripts distants (@ID@ remplacé par un identifiant validé, et rien d'autre de libre)

# Vivant = PID du fichier dont /proc/<pid>/cmdline porte le marqueur (jamais un PID recyclé par un autre programme).
_VIE = r"""d="$HOME/taches/@ID@"
vivant() {
  p=""; [ -f "$1" ] && IFS= read -r p < "$1"
  case "$p" in ''|*[!0-9]*) return 1 ;; esac
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -qF -e "$2"
}
v=absent; [ -f "$d/veilleur.pid" ] && v=mort; vivant "$d/veilleur.pid" "--veilleur @ID@" && v=vivant
e=absent; [ -f "$d/enveloppe.pid" ] && e=mort; { vivant "$d/enveloppe.pid" "lancer_emulation.sh @ID@" || vivant "$d/enveloppe.pid" "lancer_agent.sh @ID@"; } && e=vivant
"""
_ETAT = """# tache:etat @ID@
set -u
""" + _VIE + """[ -f "$d/etat.json" ] || exit 3
printf 'maintenant=%s\\nveilleur=%s\\nenveloppe=%s\\n' "$(date +%s)" "$v" "$e"
printf 'etat='; head -c 4096 "$d/etat.json" | tr -d '\\r\\n'; printf '\\n'
"""
# Nettoyage d'une tâche dont ni le veilleur ni l'enveloppe ne vivent (revérifié ici, sur le serveur) : conteneur supprimé,
# etat.json réécrit (temporaire puis mv) seulement s'il dit encore en_cours. @JSON@ : objet construit par json.dumps de
# valeurs validées (une ligne ASCII qui commence par « { », donc jamais égale au délimiteur du document).
_NETTOYER = """# tache:nettoyer @ID@
set -u
""" + _VIE + """if [ "$v" = vivant ] || [ "$e" = vivant ]; then exit 4; fi
timeout 60 sudo -n docker rm -f tache-@ID@ >/dev/null 2>&1
grep -q '"etat": "en_cours"' "$d/etat.json" 2>/dev/null || exit 0
umask 077
cat > "$d/etat.json.lanceur.tmp" <<'FIN_ETAT'
@JSON@
FIN_ETAT
mv -f "$d/etat.json.lanceur.tmp" "$d/etat.json"
"""
# Arrêt : tâche jamais démarrée (pas d'etat.json, ou en_attente : créneau occupé) -> APK retiré puis etat.json arretee
# (temporaire puis mv ; l'enveloppe refuse ensuite de démarrer un identifiant à l'état final, et un lanceur qui attend le
# créneau relit arretee et s'arrête). Tâche en cours -> fichier arret (le veilleur l'honore, arrête le conteneur et écrit
# l'état final), attente bornée de cet état. Puis docker stop dans tous les cas (sans effet si le conteneur n'existe plus :
# idempotent). @JSON@ : comme pour _NETTOYER, une ligne ASCII construite par json.dumps de valeurs validées.
_ARRETER = """# tache:arreter @ID@
set -u
d="$HOME/taches/@ID@"
[ -d "$d" ] || exit 3
umask 077
if [ ! -e "$d/etat.json" ] || grep -q '"etat": "en_attente"' "$d/etat.json" 2>/dev/null; then
  rm -f -- "$d/entree/app.apk" "$d/entree/projet.bundle"
  cat > "$d/etat.json.lanceur.tmp" <<'FIN_ETAT'
@JSON@
FIN_ETAT
  if [ ! -e "$d/etat.json" ] || grep -q '"etat": "en_attente"' "$d/etat.json" 2>/dev/null; then
    mv -f "$d/etat.json.lanceur.tmp" "$d/etat.json"
  else
    rm -f "$d/etat.json.lanceur.tmp"
  fi
elif grep -q '"etat": "en_cours"' "$d/etat.json" 2>/dev/null; then
  printf '%s\\n' @MOTIF@ > "$d/arret.tmp" && mv -f "$d/arret.tmp" "$d/arret"
  i=0
  while [ "$i" -lt 30 ] && grep -q '"etat": "en_cours"' "$d/etat.json" 2>/dev/null; do sleep 1; i=$((i + 1)); done
fi
# Une tâche d'AGENT (entree/demande.json : "type": "agent") : son veilleur tient l'arrêt (docker stop -t 60, le temps que
# l'entrée conclue) ; un docker stop -t 10 ici l'écourterait. Les autres tâches (émulation) : comme avant.
a="$d/entree/demande.json"
if ! { [ -f "$a" ] && [ ! -L "$a" ] && head -c 65536 -- "$a" 2>/dev/null | grep -Eq '"type"[[:space:]]*:[[:space:]]*"agent"'; }; then
  timeout 60 sudo -n docker stop -t 10 tache-@ID@ >/dev/null 2>&1
fi
exit 0
"""
# Préparation (commande, shell POSIX : l'entrée standard porte l'archive) : le dossier de la tâche est créé par mkdir
# (atomique : il ne doit pas exister, code 73 sinon), l'archive extraite dans un temporaire privé puis chaque fichier
# déplacé à sa place ; le temporaire est toujours supprimé.
_PREPARER = """# tache:preparer @ID@
umask 077
mkdir -p "$HOME/taches" || exit 1
d="$HOME/taches/@ID@"
mkdir "$d" 2>/dev/null || exit 73
t=$(mktemp -d "$HOME/taches/.depot.XXXXXX") || exit 1
r=1
if tar -x --no-same-owner -C "$t" -f - && [ -f "$t/entree/app.apk" ] && [ ! -L "$t/entree/app.apk" ] \\
   && [ -f "$t/demande.json" ] && [ ! -L "$t/demande.json" ]; then
  # entree/ et app.apk lisibles par l'utilisateur 1000 du conteneur (l'enveloppe refait aussi chmod 755 entree)
  mkdir "$d/entree" && chmod 755 "$d/entree" 2>/dev/null; chmod 644 "$t/entree/app.apk" 2>/dev/null
  [ -d "$d/entree" ] && mv -f "$t/entree/app.apk" "$d/entree/app.apk" && mv -f "$t/demande.json" "$d/demande.json" && r=0
fi
rm -rf "$t"
exit $r
"""
# Dépôt de l'enveloppe (commande ; l'archive sur l'entrée standard), même discipline que le moteur d'installation : archive
# extraite dans un temporaire privé, rien n'est déplacé si tar échoue ou si le fichier attendu manque, est vide ou est un
# lien ; le temporaire est toujours supprimé.
_DEPOSER = f"""# tache:deposer
umask 077
mkdir -p "$HOME/myiafactory" || exit 1
d=$(mktemp -d "$HOME/myiafactory/.depot.XXXXXX") || exit 1
f="$d/{ENVELOPPE}"
c="$d/{COMMUN}"
r=1
if tar -x --no-same-owner -C "$d" -f - && [ -f "$f" ] && [ ! -L "$f" ] && [ -s "$f" ] && [ -f "$c" ] && [ ! -L "$c" ] && [ -s "$c" ]; then
  mkdir -p "{DOSSIER_DISTANT}/taches" && mv -f "$c" "{COMMUN_DISTANT}" && mv -f "$f" "{ENVELOPPE_DISTANTE}" && r=0
fi
rm -rf "$d"
exit $r
"""
# Arguments de l'enveloppe : <id> <mode> <duree_s> <inactivite_s> <memoire_mo> <cpus> <captures> <octets>, tous des entiers
# validés (limites de la demande, toujours dans les bornes de l'enveloppe : captures 1..50, octets 1..104857600).
_LANCER = f"""# tache:lancer @ID@
exec bash "{ENVELOPPE_DISTANTE}" @ID@ @MODE@ @DUREE@ @INACTIVITE@ @MEMOIRE@ @CPUS@ @CAPTURES@ @OCTETS@
"""
# Empreinte de l'image de l'émulateur sur le serveur (marqueur écrit par l'étape d'installation) : une lecture fixe.
_IMAGE = f"""# tache:image
head -c 256 "{serveur_installation.MARQUEURS['emulateur-image'][1]}" 2>/dev/null
"""
_EFFACER = """# tache:effacer @ID@
d="$HOME/taches/@ID@"
[ -e "$d/etat.json" ] && exit 4
rm -rf -- "$d"
"""
_ABANDON = """# tache:abandon @ID@
rm -f -- "$HOME/taches/@ID@/entree/app.apk"
"""
_AVD = """# tache:avd @ID@
d="$HOME/taches/@ID@"
if [ -e "$d/sortie/.avd-pret" ]; then echo pret
elif grep -q '"etat": "en_cours"' "$d/etat.json" 2>/dev/null; then echo attente
else echo fini; fi
"""
# Relais d'un verbe : jamais de -e ni d'environnement de l'appelant ; le pont revalide tout.
_VERBE = """# tache:verbe @ID@
exec sudo -n docker exec tache-@ID@ /usr/local/bin/pont @VERBE@
"""
# Archive de sortie/ : fichiers ORDINAIRES seulement (find sans -L ne suit aucun lien ; -type f écarte les liens
# symboliques ; -links 1 écarte les liens durs), noms fixes, profondeur et nombre bornés, taille de chaque fichier et du
# flux bornées. Deux archives tar à la suite : les journaux, lus depuis sortie/ (point de montage, que le conteneur ne peut
# pas remplacer), puis les captures, lues DEPUIS l'intérieur de captures/ après `cd -P` et vérification du chemin physique :
# des noms d'un seul composant, préfixés `captures/` par --transform ; un dossier captures/ remplacé par un lien n'est pas
# lu, un fichier remplacé par un lien entre find et tar est archivé comme lien, que le poste refuse. Le poste revérifie tout.
# Archive complète : au plus captures + 1 captures, pour que le poste voie le dépassement (statut limite).
# Vidéos : de même, lues depuis l'intérieur de videos/ (`cd -P` + chemin physique vérifié) : les mp4 (noms d'un composant),
# puis chaque dossier d'images `<nom>-img` (vrai dossier : find -type d n'en suit aucun lien ; nom revérifié par motif avant
# tout usage), lu depuis son intérieur de la même façon. Au plus VIDEOS_MAX + 1 vidéos et IMAGES_PAR_FILM + 1 images par
# dossier, pour que le poste voie un dépassement.
_RAPATRIER = """# tache:@OP@ @ID@ @NOM@
set -u
set -f
r=$(cd -P -- "$HOME/taches/@ID@" 2>/dev/null && pwd -P) || exit 3
cd -P -- "$r/sortie" 2>/dev/null && [ "$(pwd -P)" = "$r/sortie" ] || exit 3
{
@JOURNAUX@
@CAPTURES@
@VIDEOS@
} | head -c @TOTAL@
"""
_LISTE_JOURNAUX = ("  for f in pont.log plantage.txt entree-tache.log emulateur.log logcat.txt; do\n"
                   "    find \"./$f\" -maxdepth 0 -type f -links 1 -size -@JMAX@c -print0 2>/dev/null\n"
                   "  done | tar --null --no-recursion -c -f - -T -")
_BLOC_CAPTURES = """  if cd -P -- "$r/sortie/captures" 2>/dev/null && [ "$(pwd -P)" = "$r/sortie/captures" ]; then
    find . -mindepth 1 -maxdepth 1 -type f -links 1 -name '@MOTIF@' -size -@CMAX@c -print0 2>/dev/null \\
      | head -z -n @NMAX@ | tar --null --no-recursion --transform 's,^\\./,captures/,' -c -f - -T -
  fi"""
_BLOC_VIDEOS = """  if cd -P -- "$r/sortie/videos" 2>/dev/null && [ "$(pwd -P)" = "$r/sortie/videos" ]; then
    find . -mindepth 1 -maxdepth 1 -type f -links 1 -name '@VMOTIF@' -size -@VMAX@c -print0 2>/dev/null \\
      | head -z -n @VNMAX@ | tar --null --no-recursion --transform 's,^\\./,videos/,' -c -f - -T -
    find . -mindepth 1 -maxdepth 1 -type d -name '@IMOTIF@' -print 2>/dev/null | head -n @VNMAX@ | while IFS= read -r i; do
      n="${i#./}"
      [[ $n =~ ^[a-z0-9][a-z0-9_-]{0,39}-img$ ]] || continue
      if cd -P -- "$r/sortie/videos/$n" 2>/dev/null && [ "$(pwd -P)" = "$r/sortie/videos/$n" ]; then
        find . -mindepth 1 -maxdepth 1 -type f -links 1 -name '*.png' -size -@CMAX@c -print0 2>/dev/null \\
          | head -z -n @INMAX@ | tar --null --no-recursion --transform "s,^\\./,videos/$n/," -c -f - -T -
      fi
    done
  fi"""


def _script(modele, ident, **valeurs):
    _id_valide(ident)
    texte = modele.replace("@ID@", ident)
    for cle, v in valeurs.items():
        texte = texte.replace(f"@{cle}@", v)
    return texte


def _script_rapatrier(ident, limites, nom=None, film=None):
    """Toute la sortie (ni `nom` ni `film`), la seule capture `nom`, ou le seul film `film` (sa vidéo et ses images) ;
    `nom` et `film` déjà validés par MOTIF_NOM."""
    for v in (nom, film):
        if v is not None and not re.fullmatch(MOTIF_NOM, v, re.ASCII):
            raise ValueError("Nom refusé.")
    tout = nom is None and film is None
    modele = (_RAPATRIER.replace("@JOURNAUX@\n", _LISTE_JOURNAUX + "\n" if tout else "")
              .replace("@CAPTURES@\n", _BLOC_CAPTURES + "\n" if film is None else "")
              .replace("@VIDEOS@\n", _BLOC_VIDEOS + "\n" if nom is None else ""))
    octets = int(limites["octets"])
    return _script(modele, ident, OP="capture" if nom else ("film" if film else "rapatrier"),
                   MOTIF=f"{nom}.png" if nom else "*.png", NOM=nom or film or "",
                   VMOTIF=f"{film}.mp4" if film else "*.mp4", IMOTIF=f"{film}-img" if film else "*-img",
                   JMAX=str(JOURNAL_MAX_OCTETS + 1), CMAX=str(octets + 1), VMAX=str(min(VIDEO_MAX_OCTETS, octets) + 1),
                   NMAX=str(1 if nom else int(limites["captures"]) + 1), VNMAX=str(1 if film else VIDEOS_MAX + 1),
                   INMAX=str(IMAGES_PAR_FILM + 1),
                   TOTAL=str(octets + TAILLE_ARCHIVE_MARGE)).replace(" \nset -u", "\nset -u")


# --- lecture de l'état

def _cles(sortie):
    trouvees = {}
    for ligne in sortie.splitlines():
        cle, egal, valeur = ligne.partition("=")
        if egal and cle and cle not in trouvees:
            trouvees[cle] = valeur
    return trouvees


def _etat_json(texte, ident):
    """État lu (etat.json ou ligne de l'enveloppe) sous une forme sûre ; None s'il est illisible ou d'une autre tâche."""
    if not isinstance(texte, str) or len(texte) > ETAT_MAX:
        return None
    try:
        d = json.loads(texte)
    except (ValueError, RecursionError):
        return None
    if not isinstance(d, dict) or d.get("id") != ident or d.get("etat") not in ETATS:
        return None
    return {"etat": d["etat"], "statut": d.get("statut") if d.get("statut") in STATUTS_RAPPORT else None,
            "debut": _iso_valide(d.get("debut")), "fin": _iso_valide(d.get("fin")),
            "raison": _court(d.get("raison")) if isinstance(d.get("raison"), str) else ""}


def _derniere_ligne_json(sortie, ident):
    for ligne in reversed(sortie.strip().splitlines()):
        if ligne.lstrip().startswith("{"):
            return _etat_json(ligne.strip(), ident)
    return None


def _inconnu(ident, raison, **plus):
    return {"id": ident if isinstance(ident, str) and MOTIF_ID.fullmatch(ident) else None, "etat": "inconnu",
            "raison": raison, **plus}


def _veilleur_mort(cles, lu):
    """Vrai seulement si ni le veilleur ni l'enveloppe ne vivent, et que le veilleur est mort (fichier présent) ou n'est
    jamais né (pas de veilleur.pid plus de VEILLEUR_ABSENT_S après le début, horloge du serveur)."""
    v, e = cles.get("veilleur"), cles.get("enveloppe")
    if v not in ("vivant", "mort", "absent") or e not in ("vivant", "mort", "absent") or "vivant" in (v, e):
        return False
    if v == "mort":
        return True
    debut = _epoch(lu.get("debut"))
    try:
        maintenant = int(cles.get("maintenant", ""))
    except ValueError:
        return False
    return debut is not None and maintenant - debut > VEILLEUR_ABSENT_S


RAISON_VEILLEUR_MORT = ("Le veilleur de la tâche ne tourne plus (processus disparu) : conteneur supprimé, tâche "
                        "marquée en échec.")


def _nettoyer(serveur, ssh, ident, lu):
    nouveau = {"id": ident, "etat": "echouee", "statut": "erreur", "debut": lu.get("debut"),
               "fin": _maintenant_iso(), "raison": RAISON_VEILLEUR_MORT}
    code, _s, _e = _bash(serveur, ssh, _script(_NETTOYER, ident, JSON=json.dumps(nouveau, ensure_ascii=True)), 90)
    if code != 0:                    # 4 : quelqu'un vit encore (rien touché) ; autre : serveur muet, rien affirmé
        return lu
    return {k: nouveau[k] for k in ("etat", "statut", "debut", "fin", "raison")}


def _etat(ident, dossier, ssh):
    if not isinstance(ident, str) or not MOTIF_ID.fullmatch(ident):
        return _inconnu(ident, "Identifiant de tâche invalide.")
    try:
        serveur = _serveur_de(ident, dossier)
    except RefusLancement as e:
        return _inconnu(ident, str(e))
    code, sortie, erreur = _bash(serveur, ssh, _script(_ETAT, ident), delai=30)
    if code in INJOIGNABLE:
        return _inconnu(ident, f"Serveur injoignable ou délai dépassé : {_court(erreur, 200)}", serveur_id=serveur.id)
    if code == 3:
        return _inconnu(ident, "Aucun état de cette tâche sur le serveur.", serveur_id=serveur.id)
    if code != 0:
        return _inconnu(ident, f"Lecture de l'état en échec (code {code}) : {_court(erreur, 200)}",
                        serveur_id=serveur.id)
    cles = _cles(sortie)
    lu = _etat_json(cles.get("etat"), ident)
    if lu is None:
        return _inconnu(ident, "État illisible sur le serveur (etat.json).", serveur_id=serveur.id)
    if lu["etat"] == "en_cours" and _veilleur_mort(cles, lu):
        lu = _nettoyer(serveur, ssh, ident, lu)
    resultat = {"id": ident, **lu, "serveur_id": serveur.id}
    avertissement = _noter(dossier, ident, dict(lu))
    if avertissement:
        resultat["avertissement"] = avertissement
    return resultat


def etat(ident, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh):
    """État d'une tâche lu sur le serveur (`~/taches/<id>/etat.json`) ; met l'index à jour. Une tâche « en_cours » dont
    ni le veilleur ni l'enveloppe ne vivent est nettoyée (conteneur supprimé) et devient « echouee ». Serveur
    injoignable, identifiant invalide ou état illisible : `{"etat": "inconnu", "raison": ...}`. Jamais d'exception."""
    try:
        return _masque(_etat(ident, dossier, ssh), dossier)
    except Exception as e:  # noqa: BLE001 - filet : l'état ne lève jamais
        return _inconnu(ident, f"Lecture de l'état impossible ({type(e).__name__}).")


# --- lancer

def _demande_sure(demande):
    if isinstance(demande, Demande):
        limites = demande.limites
        brut = {"id": demande.id, "type": demande.type, "projet": demande.projet, "mode": demande.mode,
                "scenario": demande.scenario, "demandeur": demande.demandeur, "apk": demande.apk,
                "limites": dict(limites) if isinstance(limites, (dict, MappingProxyType)) else limites}
    elif isinstance(demande, dict):
        brut = demande
    else:
        raise RefusLancement("La demande doit être une Demande ou un dictionnaire.")
    try:
        return valider_demande(brut)
    except ValueError as e:
        raise RefusLancement(str(e)) from None


def _demande_dict(d):
    return {"id": d.id, "type": d.type, "projet": d.projet, "mode": d.mode, "scenario": d.scenario,
            "limites": dict(d.limites), "demandeur": d.demandeur, "apk": d.apk}


def _envoyer(serveur, ssh, demande, apk):
    """Crée ~/taches/<id> (qui ne doit pas exister) avec entree/app.apk et demande.json ; (code, erreur), 73 si pris."""
    contenu = (json.dumps(_demande_dict(demande), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    apk = apk if type(apk) is bytes else bytes(apk)          # jamais une copie de plus pour des octets déjà `bytes`
    donnees = _archive([("entree/app.apk", apk, 0o644), ("demande.json", contenu, 0o600)])
    code, _sortie, erreur = _octets(serveur, ssh, _script(_PREPARER, demande.id), donnees, delai=600)
    return code, erreur


def _deposer_enveloppe(serveur, ssh):
    """Dépose lancer_emulation.sh et commun.sh (qu'il source) dans $HOME/myiafactory/serveur_ovh/taches/ (`_DEPOSER` :
    temporaire privé puis mv, commun.sh d'abord). None si réussi, sinon le message."""
    fichiers = []
    for rel, mode in ((ENVELOPPE, 0o755), (COMMUN, 0o644)):
        source = RACINE_SERVEUR / rel
        if source.is_symlink() or not source.is_file():
            return f"Fichier du dépôt introuvable : serveur_ovh/{rel}."
        fichiers.append((rel, source.read_bytes(), mode))
    donnees = _archive(fichiers)
    code, _o, erreur = _octets(serveur, ssh, _DEPOSER, donnees, delai=120, silencieux=True)
    if code != 0:
        return f"Dépôt de l'enveloppe sur le serveur impossible (code {code}) : {_court(erreur, 200)}"
    # Code 0 mais un message (tar, mv, mkdir...) sur la sortie d'erreur : dépôt douteux. LogLevel=ERROR (variante
    # silencieuse) écarte la bannière de sshd ; l'avertissement de première connexion (« Warning: Permanently added ... »,
    # StrictHostKeyChecking=accept-new) reste admis pour un ssh qui ne connaîtrait pas cette variante.
    messages = [ligne for ligne in erreur.splitlines()
                if ligne.strip() and not ligne.strip().startswith("Warning: Permanently added ")]
    if messages:
        return f"Dépôt de l'enveloppe douteux (messages du serveur) : {_court(' '.join(messages), 200)}"
    return None


def _verifier_image(serveur, ssh):
    """`RefusLancement` si l'image de l'émulateur du serveur est périmée : son marqueur ne porte pas l'empreinte des
    fichiers du dépôt (`serveur_installation.empreinte_etape`, la même règle que l'installation). Une lecture fixe ;
    serveur injoignable pendant cette lecture : rien n'est affirmé (l'envoi qui suit le dira)."""
    try:
        attendue = serveur_installation.empreinte_etape("emulateur_image")
    except (OSError, ValueError, KeyError):
        attendue = None
    code, sortie, _e = _bash(serveur, ssh, _IMAGE, delai=20)
    if attendue is None:
        raise RefusLancement("L'empreinte locale de l'image de l'émulateur est illisible (fichiers du dépôt serveur_ovh "
                             "absents ou illisibles sur ce poste) : lancement refusé, rien n'a été envoyé.")
    if code in INJOIGNABLE:
        return
    if code != 0 or sortie.strip() != attendue:
        raise RefusLancement(f"L'image de l'émulateur du serveur {serveur.id} est périmée, à mettre à jour (les fichiers "
                             "du dépôt ont changé depuis son installation) : relancez l'installation de "
                             "« emulateur-image » dans le bureau (Serveurs).")


def _apk_sur(apk):
    if not isinstance(apk, (bytes, bytearray)) or not apk:
        raise RefusLancement("APK absent ou vide : les octets du fichier sont attendus.")
    if len(apk) > APK_MAX_OCTETS:
        raise RefusLancement(f"APK trop gros : {APK_MAX_OCTETS // (1024 * 1024)} Mo au plus.")


def lancer(demande, apk, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, attente_max_s=600, dormir=time.sleep):
    """Envoie l'APK et la demande, démarre l'enveloppe `lancer_emulation.sh` sur le serveur choisi, gère l'attente du
    créneau (nouvel essai, même identifiant, toutes les 15 s jusqu'à `attente_max_s`) et tient l'index.

    Renvoie `{id, etat, serveur_id}`, plus `erreur` en cas d'échec ou d'abandon : envoi impossible, index indisponible
    juste après l'envoi (dossier effacé sur le serveur, rien n'a démarré) ou enveloppe en échec -> `etat` « echouee » ;
    créneau toujours occupé -> « en_attente » (abandon) ; réponse perdue -> l'état relu sur le serveur. `RefusLancement`
    avant tout envoi : demande, APK ou `attente_max_s` invalide, aucun serveur prêt, aucun identifiant libre. Un
    identifiant déjà dans l'index ou sur le serveur est remplacé par un nouveau (`nouvel_id`) : l'identifiant rendu fait
    foi. Seul le code 75 (créneau occupé) est réessayé avec le même identifiant ; tout autre échec le « brûle » (l'APK
    déposé est alors retiré). Une tâche arrêtée pendant l'attente (`arreter`) est relue « arretee » et rien ne démarre."""
    d = _demande_sure(demande)
    _apk_sur(apk)
    if isinstance(attente_max_s, bool) or not isinstance(attente_max_s, int) or attente_max_s < 0:
        raise RefusLancement("attente_max_s doit être un nombre entier de secondes, positif ou nul.")
    serveur = choisir_serveur(dossier)          # l'état connu (aucune connexion) : une image déjà dite à refaire refuse ici
    _verifier_image(serveur, ssh)              # puis l'empreinte relue sur le serveur, avant tout envoi

    def sortie(etat_, **plus):
        return _masque({"id": d.id, "etat": etat_, "serveur_id": serveur.id, **plus}, dossier)

    # 1. identifiant libre (index puis serveur, par mkdir atomique) et envoi
    candidat = d.id
    for _ in range(ESSAIS_ID):
        if candidat not in Index(dossier).lire():
            code, erreur = _envoyer(serveur, ssh, replace(d, id=candidat), apk)
            if code == 0:
                break
            if code != CODE_EXISTE:
                d = replace(d, id=candidat)
                if code not in INJOIGNABLE:        # réponse perdue : le dossier n'est peut-être pas le nôtre, on n'y touche pas
                    _bash(serveur, ssh, _script(_EFFACER, candidat))
                return sortie("echouee", erreur=f"Envoi de l'APK impossible (code {code}) : {_court(erreur, 200)}")
        candidat = nouvel_id()
    else:
        raise RefusLancement("Aucun identifiant de tâche libre après plusieurs essais : réessayez.")
    d = replace(d, id=candidat)
    fiche = {"etat": "en_attente", "serveur_id": serveur.id, "mode": d.mode, "projet": d.projet,
             "scenario": d.scenario, "demandeur": d.demandeur, "limites": dict(d.limites), "cree": _maintenant_iso(),
             "debut": None, "fin": None, "statut": None, "raison": "APK envoyé : démarrage demandé."}
    try:
        Index(dossier).enregistrer(d.id, _masque(fiche, dossier))
    except (ErreurIndex, TimeoutError, ValueError, OSError) as e:
        _bash(serveur, ssh, _script(_EFFACER, d.id))
        return sortie("echouee", erreur=f"{_court(e)} : tâche non démarrée, rien ne tourne sur le serveur.")

    # 2. enveloppe à jour, puis démarrage (le créneau occupé est réessayé avec le même identifiant)
    probleme = _deposer_enveloppe(serveur, ssh)
    if probleme:
        _bash(serveur, ssh, _script(_EFFACER, d.id))
        avert = _noter(dossier, d.id, {"etat": "echouee", "statut": "erreur", "fin": _maintenant_iso(),
                                        "raison": probleme})
        return sortie("echouee", erreur=probleme + (f" ({avert})" if avert else ""))
    commande = _script(_LANCER, d.id, MODE=d.mode, DUREE=str(int(d.limites["duree_s"])),
                       INACTIVITE=str(int(d.limites["inactivite_s"])), MEMOIRE=str(MEMOIRE_MO), CPUS=str(CPUS),
                       CAPTURES=str(int(d.limites["captures"])), OCTETS=str(int(d.limites["octets"])))
    attendu = 0
    while True:
        code, sortie_texte, erreur = _bash(serveur, ssh, commande, delai=180)
        if code != 75:
            break
        if attendu >= attente_max_s:
            _bash(serveur, ssh, _script(_ABANDON, d.id))
            message = (f"Créneau d'émulation toujours occupé après {attendu} s : lancement abandonné "
                       "(la tâche reste en attente sur le serveur, sans APK ; relancez plus tard).")
            avert = _noter(dossier, d.id, {"etat": "en_attente", "raison": message, "abandonnee": True})
            return sortie("en_attente", erreur=message + (f" ({avert})" if avert else ""))
        dormir(PAUSE_CRENEAU_S)
        attendu += PAUSE_CRENEAU_S

    # 3. résultat
    lu = _derniere_ligne_json(sortie_texte, d.id)
    if code in (0, 3):
        maj = {"etat": "en_cours", "debut": (lu or {}).get("debut"), "raison": (lu or {}).get("raison", "")}
        avert = _noter(dossier, d.id, maj)
        return sortie("en_cours", erreur=avert) if avert else sortie("en_cours")
    if code in INJOIGNABLE or code == 4:
        # Réponse perdue (la tâche démarre peut-être encore) ou identifiant déjà utilisé : on relit l'état sur le
        # serveur, jamais de relance à l'aveugle ; le nettoyage n'a lieu que si rien n'y vit (voir etat).
        relu = _etat(d.id, dossier, ssh)
        if relu["etat"] == "arretee":            # arrêtée pendant l'attente du créneau : issue normale, pas une erreur
            return sortie("arretee", raison=relu.get("raison", ""))
        motif = ("Réponse du serveur perdue pendant le démarrage : état relu sur le serveur."
                 if code != 4 else "Identifiant déjà utilisé sur le serveur : état relu sur le serveur.")
        return sortie(relu["etat"], erreur=f"{motif} {relu.get('raison', '')}".strip())
    raison = (lu or {}).get("raison") or f"Démarrage refusé par l'enveloppe (code {code}) : {_court(erreur, 200)}"
    _bash(serveur, ssh, _script(_ABANDON, d.id))          # identifiant brûlé : l'APK n'a plus rien à faire sur le serveur
    avert = _noter(dossier, d.id, {"etat": "echouee", "statut": "erreur", "fin": (lu or {}).get("fin") or
                                   _maintenant_iso(), "raison": raison})
    return sortie("echouee", erreur=raison + (f" ({avert})" if avert else ""))


# --- arrêter

RAISON_ARRET_AVANT_DEMARRAGE = "Arrêtée avant son démarrage (créneau occupé) : rien n'a tourné, APK retiré."
RAISON_AUCUNE_TACHE = "Aucune tâche de cet identifiant sur le serveur."     # dossier absent : rien n'a été envoyé

def arreter(ident, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, fin=False):
    """Tâche en cours : demande l'arrêt (fichier `arret` : « fin » si `fin is True`, fin normale d'un scénario ; « arret »
    sinon) et attend que le veilleur écrive l'état final (30 s au plus). Tâche jamais démarrée (en_attente ou sans état) :
    l'APK est retiré et l'état devient « arretee » (un `lancer` qui attend le créneau le relit et ne démarre rien). Puis
    `docker stop` dans tous les cas. Idempotent. Renvoie l'état relu (comme `etat`) ; jamais d'exception."""
    try:
        if not isinstance(ident, str) or not MOTIF_ID.fullmatch(ident):
            return _masque(_inconnu(ident, "Identifiant de tâche invalide."), dossier)
        try:
            serveur = _serveur_de(ident, dossier)
        except RefusLancement as e:
            return _masque(_inconnu(ident, str(e)), dossier)
        jamais = {"id": ident, "etat": "arretee", "statut": None, "debut": None, "fin": _maintenant_iso(),
                  "raison": RAISON_ARRET_AVANT_DEMARRAGE}
        code, _s, erreur = _bash(serveur, ssh, _script(_ARRETER, ident, MOTIF="fin" if fin is True else "arret",
                                                       JSON=json.dumps(jamais, ensure_ascii=True)), delai=150)
        if code in INJOIGNABLE:
            return _masque(_inconnu(ident, f"Serveur injoignable ou délai dépassé : {_court(erreur, 200)}",
                                    serveur_id=serveur.id), dossier)
        if code == 3:
            return _masque(_inconnu(ident, RAISON_AUCUNE_TACHE, serveur_id=serveur.id), dossier)
        return _masque(_etat(ident, dossier, ssh), dossier)
    except Exception as e:  # noqa: BLE001
        return _inconnu(ident, f"Arrêt impossible ({type(e).__name__}).")


# --- rapatrier

def _dossier_sur(chemin):
    """Crée le dossier local s'il manque ; refuse un lien, une jonction ou un fichier à sa place."""
    jonction = getattr(os.path, "isjunction", lambda p: False)
    if chemin.is_symlink() or jonction(chemin) or (chemin.exists() and not chemin.is_dir()):
        raise ValueError(f"Destination refusée (lien ou fichier à la place d'un dossier) : {chemin}")
    chemin.mkdir(parents=True, exist_ok=True)
    if chemin.is_symlink() or jonction(chemin) or not chemin.is_dir():
        raise ValueError(f"Destination refusée : {chemin}")


def _ecrire_sur(chemin, donnees):
    """Temporaire créé en exclusif (`xb` : jamais un fichier existant ni un lien suivi) puis `os.replace` (qui remplace
    un lien éventuel lui-même, sans le suivre) ; octets écrits tels quels."""
    tmp = chemin.with_name(f".{chemin.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        with open(tmp, "xb") as f:
            f.write(donnees)
        os.replace(tmp, chemin)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _nom_local(nom):
    """(nom local, genre, nom du film) pour un nom admis de l'archive ; None sinon (chemins, liens, noms inconnus, noms
    réservés de Windows). Genres : journal, logcat, capture, video, image. Les noms locaux sont reconstruits à partir des
    seuls groupes validés, jamais recopiés de l'archive."""
    if nom in JOURNAUX:
        return JOURNAUX[nom], ("logcat" if nom == "logcat.txt" else "journal"), None
    m = MOTIF_CAPTURE.fullmatch(nom)
    if m and m.group(1) not in NOMS_RESERVES:
        return f"captures/{m.group(1)}.png", "capture", None
    m = MOTIF_VIDEO.fullmatch(nom)
    if m and m.group(1) not in NOMS_RESERVES:
        return f"videos/{m.group(1)}.mp4", "video", m.group(1)
    m = MOTIF_IMAGE_FILM.fullmatch(nom)
    if m and m.group(1) not in NOMS_RESERVES:
        f = m.group(1)
        return f"videos/{f}-img/{f}-{m.group(2)}.png", "image", f
    return None


def _depasse(genre, taille, res, total, limites, film=None):
    """Vrai si ce membre ferait dépasser une limite (le flux est alors « tronqué » : statut limite)."""
    if genre == "journal":
        return taille > JOURNAL_MAX_OCTETS
    if genre == "logcat":
        # Un léger dépassement (ajouts concurrents passés avant le verrou du pont) est toléré : le fichier est alors lu
        # coupé au plafond ; au-delà du double, il n'est pas pris du tout.
        return taille > 2 * LOGCAT_MAX_OCTETS
    if total + taille > int(limites["octets"]):          # captures, vidéos et images partagent les octets de la demande
        return True
    if genre == "capture":
        return len(res["captures"]) >= int(limites["captures"])
    if genre == "video":
        return taille > VIDEO_MAX_OCTETS or sum(1 for v in res["videos"].values() if v["mp4"]) >= VIDEOS_MAX
    return (len(res["videos"][film]["images"]) >= IMAGES_PAR_FILM
            or sum(len(v["images"]) for v in res["videos"].values()) >= IMAGES_FILM_MAX)


def _extraire(donnees, destination, limites):
    """Extrait l'archive dans `destination` sans jamais écrire ailleurs. Admis : membres ordinaires aux noms fixes
    (JOURNAUX, captures/<nom>.png et videos/<nom>-img/<nom>-NNN.png à signature PNG, videos/<nom>.mp4 à signature
    « ftyp » aux octets 4..8), au plus `captures` captures, VIDEOS_MAX vidéos de VIDEO_MAX_OCTETS chacune, IMAGES_FILM_MAX
    images, `octets` octets de médias (captures, vidéos, images) au total, JOURNAL_MAX_OCTETS par journal et
    LOGCAT_MAX_OCTETS pour logcat.txt. Tout autre membre (lien, périphérique, dossier, chemin absolu, `..`, lettre de lecteur, doublon) est
    compté dans `refuses` ; un flux plus grand que le plafond n'est pas analysé du tout. Plusieurs archives à la suite
    sont lues (`ignore_zeros`). Flux coupé exactement au plafond (head -c du serveur) : `tronque` ; archive abîmée ou
    lecture courte avant le plafond : `corrompue`. Limite connue : avec `ignore_zeros`, tarfile saute bloc par bloc ce
    qu'il ne sait pas lire au milieu du flux, si bien qu'une zone abîmée suivie d'en-têtes valides peut passer inaperçue
    (seule la fin du flux est vérifiée) ; le confinement, lui, ne dépend pas de cette détection (chaque membre admis est
    revérifié : type, nom, taille, signature). `videos` : {nom du film: {"mp4": chemin | None, "images": [chemins]}}."""
    res = {"captures": [], "fichiers": {}, "videos": {}, "refuses": 0, "tronque": False, "corrompue": False}
    plafond = int(limites["octets"]) + TAILLE_ARCHIVE_MARGE
    if len(donnees) > plafond:
        res["tronque"] = True
        return res
    coupe = len(donnees) == plafond                 # le serveur a peut-être coupé le flux (head -c)
    res["tronque"] = coupe
    if not donnees:
        return res
    max_fichiers = int(limites["captures"]) + len(JOURNAUX) + VIDEOS_MAX + IMAGES_FILM_MAX
    # Les octets de la demande ne comptent que les MÉDIAS (M6 : captures, vidéos, images des vidéos) ; les journaux ont
    # leur propre plafond (JOURNAL_MAX_OCTETS chacun, LOGCAT_MAX_OCTETS pour logcat.txt), pour que des journaux longs ne
    # fassent pas passer en « limite » des médias dans les clous.
    total, examines, vus, films_coupes = 0, 0, set(), set()

    def abime():
        res["tronque" if coupe else "corrompue"] = True
    fin, interrompu = 0, False

    def traiter(tar, m, nom_local, genre, film):
        """Vérifie puis écrit un membre admis par son nom ; faux si le flux est abîmé (lecture courte : on s'arrête)."""
        nonlocal total
        if genre == "image" and not (res["videos"].get(film) or {}).get("mp4"):
            # Une image n'est admise qu'avec SA vidéo : sans elle, jamais écrite ; « limite » si la vidéo a été écartée
            # par une limite, refusée sinon.
            if film in films_coupes:
                res["tronque"] = True
            else:
                res["refuses"] += 1
            return True
        if len(res["fichiers"]) >= max_fichiers or m.size < 0 or _depasse(genre, m.size, res, total, limites, film):
            res["tronque"] = True
            if genre == "video":
                films_coupes.add(film)
            return True
        contenu = tar.extractfile(m).read(m.size)
        if len(contenu) != m.size:
            abime()
            return False
        if genre == "logcat":
            contenu = contenu[:LOGCAT_MAX_OCTETS]
        if ((genre in ("capture", "image") and not contenu.startswith(SIGNATURE_PNG))
                or (genre == "video" and contenu[4:8] != SIGNATURE_MP4)):
            res["refuses"] += 1
            return True
        cible = destination / nom_local
        if genre == "capture":
            _dossier_sur(destination / "captures")
        elif genre in ("video", "image"):
            _dossier_sur(destination / "videos")
            if genre == "image":
                _dossier_sur(destination / "videos" / f"{film}-img")
        _ecrire_sur(cible, contenu)
        if genre in ("capture", "video", "image"):
            total += m.size
        res["fichiers"][nom_local] = str(cible)
        if genre == "capture":
            res["captures"].append(str(cible))
        elif film is not None:
            v = res["videos"].setdefault(film, {"mp4": None, "images": []})
            if genre == "video":
                v["mp4"] = str(cible)
            else:
                v["images"].append(str(cible))
        return True

    try:
        with tarfile.open(fileobj=io.BytesIO(donnees), mode="r:", ignore_zeros=True) as tar:
            images = []                 # les images sont traitées après toutes les vidéos (l'ordre de l'archive n'y fait rien)
            for m in tar:
                examines += 1
                if examines > 4 * max_fichiers + 20:
                    res["tronque"] = interrompu = True
                    break
                blocs = -(-max(m.size, 0) // tarfile.BLOCKSIZE)
                fin = max(fin, m.offset_data + blocs * tarfile.BLOCKSIZE)
                nom = m.name[2:] if m.name.startswith("./") else m.name
                local = _nom_local(nom)
                if local is None or m.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or nom in vus:
                    res["refuses"] += 1
                    continue
                vus.add(nom)
                if local[1] == "image":
                    images.append((m, local))
                    continue
                if not traiter(tar, m, *local):
                    interrompu = True
                    break
            for m, local in ([] if interrompu else images):
                if not traiter(tar, m, *local):
                    interrompu = True
                    break
    except (tarfile.TarError, EOFError, ValueError) as e:
        if isinstance(e, ValueError) and "Destination" in str(e):
            raise
        abime()
        return res
    # tarfile s'arrête sans erreur sur un en-tête tronqué : une archive complète finit par au moins deux blocs nuls
    # après le dernier membre, et rien d'autre que des zéros.
    reste = donnees[fin:]
    if not interrompu and (len(reste) < 2 * tarfile.BLOCKSIZE or reste.strip(b"\0")):
        abime()
    return res


def _code_echec(echec):
    code = echec.get("code") if isinstance(echec, dict) else None
    return code if isinstance(code, int) and not isinstance(code, bool) else 4


def _statut(lu, fiche, res, echec=None):
    """ok | plantage | limite | erreur, d'après etat.json, plantage.txt, le code 3 du pont noté dans la fiche et l'échec
    éventuel de la recette (`echec` : code 3 du pont -> limite, tout autre échec -> erreur ; le plantage prime)."""
    if "plantage.txt" in res["fichiers"] or lu.get("statut") == "plantage":
        return "plantage"
    if (lu.get("etat") not in FINAUX or lu.get("etat") == "echouee" or lu.get("statut") == "erreur" or res["refuses"]
            or res.get("corrompue") or (echec is not None and _code_echec(echec) != 3)):
        return "erreur"
    if (lu.get("statut") == "limite" or fiche.get("limite_atteinte") is True or res["tronque"]
            or echec is not None):
        return "limite"
    return "ok" if lu.get("statut") == "ok" else "erreur"


def _liste_videos(res):
    """Les films extraits, par nom : [{"mp4": chemin | None, "images": [chemins triés]}]."""
    return [{"mp4": v["mp4"], "images": sorted(v["images"])} for _n, v in sorted(res.get("videos", {}).items())]


def rapatrier(ident, destination, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, echec=None):
    """Rapatrie `sortie/` de la tâche dans `destination` (captures/*.png, journal.txt, plantage.txt...) et y écrit
    `rapport.json`. Renvoie le manifeste `{statut, captures, journal, rapport, duree_s, ...}` ; jamais d'exception.
    `echec` : l'échec de la recette (`{etape, verbe, code, reponse}`, de `serveur_recette.executer`), pris en compte
    dans le statut (jamais « ok ») et recopié dans le rapport."""
    manifeste = {"id": ident if isinstance(ident, str) and MOTIF_ID.fullmatch(ident) else None, "statut": "erreur",
                 "captures": [], "journal": None, "rapport": None, "duree_s": None, "etat": "inconnu", "raison": "",
                 "tronque": False, "refuses": 0, "logcat": None, "videos": []}
    try:
        lu = _etat(ident, dossier, ssh)
        manifeste.update(etat=lu["etat"], raison=lu.get("raison", ""), duree_s=_duree(lu))
        if manifeste["id"] is None or lu["etat"] == "inconnu":
            return _masque(manifeste, dossier)
        fiche = Index(dossier).lire().get(ident) or {}
        limites = _limites_fiche(fiche)
        dest = Path(destination)
        _dossier_sur(dest)
        serveur = _serveur_de(ident, dossier)
        code, donnees, erreur = _octets(serveur, ssh, "bash -s", _script_rapatrier(ident, limites).encode("utf-8"),
                                        delai=600)
        if code != 0:
            res = {"captures": [], "fichiers": {}, "videos": {}, "refuses": 0, "tronque": False}
            manifeste["raison"] = f"Rapatriement en échec (code {code}) : {_court(erreur, 200)}"
            statut = "erreur"
        else:
            res = _extraire(donnees, dest, limites)
            statut = _statut(lu, fiche, res, echec)
            if res["refuses"]:
                manifeste["raison"] = (f"Archive suspecte : {res['refuses']} élément(s) refusé(s) (lien, chemin ou nom "
                                       "non admis). " + manifeste["raison"]).strip()
            if res["corrompue"]:
                manifeste["raison"] = ("Archive de sortie abîmée ou incomplète : rapatriement partiel. "
                                       + manifeste["raison"]).strip()
        journal = res["fichiers"].get("journal.txt")
        verbes = None
        if journal:
            verbes = sum(1 for ligne in Path(journal).read_bytes().splitlines() if ligne.strip())
        logcat = res["fichiers"].get("logcat.txt")
        videos = _liste_videos(res)
        manifeste.update(statut=statut, captures=res["captures"], journal=journal, tronque=res["tronque"],
                         refuses=res["refuses"], rapport=str(dest / "rapport.json"), logcat=logcat, videos=videos)

        def relatif(c):
            return Path(c).relative_to(dest).as_posix()
        rapport = {"id": ident, "statut": statut, "etat": lu["etat"], "raison": manifeste["raison"],
                   "debut": lu.get("debut"), "fin": lu.get("fin"), "duree_s": manifeste["duree_s"], "verbes": verbes,
                   "limites": dict(limites), "limite_atteinte": fiche.get("limite_atteinte") is True,
                   "tronque": res["tronque"], "refuses": res["refuses"],
                   "captures": [relatif(c) for c in res["captures"]],
                   "videos": [{"mp4": relatif(v["mp4"]) if v["mp4"] else None, "images": [relatif(i) for i in v["images"]]}
                              for v in videos],
                   "journal": "journal.txt" if journal else None, "logcat": "logcat.txt" if logcat else None,
                   "rapatrie": _maintenant_iso()}
        if echec is not None:
            e = echec if isinstance(echec, dict) else {}
            rapport["echec"] = {"etape": e.get("etape") if isinstance(e.get("etape"), int) else None,
                                "verbe": _court(e.get("verbe"), 40) if isinstance(e.get("verbe"), str) else None,
                                "code": _code_echec(e), "reponse": _court(e.get("reponse"))}
        ecrire_atomique(dest / "rapport.json",
                        json.dumps(_masque(rapport, dossier), ensure_ascii=False, indent=2) + "\n")
    except Exception as e:  # noqa: BLE001 - destination refusée, disque, serveur non déclaré : statut erreur
        manifeste.update(statut="erreur", raison=_court(f"{manifeste['raison']} Rapatriement interrompu : "
                                                         f"{e if isinstance(e, (ValueError, OSError)) else type(e).__name__}"))
        if manifeste["rapport"] and not Path(manifeste["rapport"]).exists():
            manifeste["rapport"] = None
    return _masque(manifeste, dossier)


# --- relais d'un verbe

def _reponse_pont(nom, code, sortie, erreur):
    """Ligne JSON du pont lue avec prudence : une seule ligne, taille bornée, types attendus, `ok` cohérent avec le code."""
    if code in INJOIGNABLE:
        return {"ok": False, "verbe": nom, "code": code, "detail": f"Serveur injoignable ou délai dépassé : {_court(erreur, 200)}"}
    illisible = {"ok": False, "verbe": nom, "code": code or 4,
                 "detail": f"Réponse illisible du pont (code {code}) : {_court(erreur, 200)}".rstrip(" :")}
    if len(sortie) > REPONSE_PONT_MAX:
        return illisible
    lignes = [ligne for ligne in sortie.splitlines() if ligne.strip()]
    if len(lignes) != 1:
        return illisible
    try:
        d = json.loads(lignes[0])
    except (ValueError, RecursionError):
        return illisible
    if (not isinstance(d, dict) or not isinstance(d.get("ok"), bool) or not isinstance(d.get("detail"), str)
            or not isinstance(d.get("verbe"), str) or d["ok"] != (code == 0)):
        return illisible
    return {"ok": d["ok"], "verbe": nom, "code": code, "detail": d["detail"], "_lisible": True}


def _attendre_avd(serveur, ssh, ident, dormir, dossier=plateforme_acces.DOSSIER):
    """None quand sortie/.avd-pret existe (l'AVD est créé) ; sinon la réponse d'échec (attente bornée). Tâche finie : la raison
    écrite par le veilleur (ex. « Le conteneur s'est arrêté au démarrage : Création de l'AVD ... ») est jointe au détail."""
    attendu = 0
    while True:
        code, sortie, erreur = _bash(serveur, ssh, _script(_AVD, ident), delai=30)
        if code in INJOIGNABLE:
            return _reponse_pont("demarrer", code, "", erreur)
        mot = sortie.strip()
        if mot == "pret":
            return None
        if mot != "attente":
            raison = _etat(ident, dossier, ssh).get("raison") or ""
            return {"ok": False, "verbe": "demarrer", "code": 4,
                    "detail": ("La tâche n'est plus en cours : l'émulateur ne peut pas démarrer."
                               + (f" {_court(raison)}" if raison else ""))}
        if attendu >= AVD_ATTENTE_S:
            return {"ok": False, "verbe": "demarrer", "code": 4,
                    "detail": f"L'AVD n'est pas prêt après {AVD_ATTENTE_S} s (voir sortie/entree-tache.log)."}
        dormir(AVD_PAS_S)
        attendu += AVD_PAS_S


def _rapatrier_capture(serveur, ssh, ident, nom, destination, limites):
    """(chemin local, None) ou (None, raison) : la seule capture `nom`, par la même extraction sûre."""
    if nom in NOMS_RESERVES:
        return None, "nom de capture réservé sous Windows"
    code, donnees, erreur = _octets(serveur, ssh, "bash -s",
                                    _script_rapatrier(ident, limites, nom).encode("utf-8"), delai=120)
    if code != 0:
        return None, f"capture non rapatriée (code {code}) {_court(erreur, 200)}".strip()
    dest = Path(destination)
    _dossier_sur(dest)
    res = _extraire(donnees, dest, limites)
    chemin = dest / "captures" / f"{nom}.png"
    if str(chemin) in res["captures"]:
        return chemin, None
    return None, "capture absente ou refusée au rapatriement"


def _rapatrier_film(serveur, ssh, ident, nom, destination, limites):
    """(chemin du mp4, [images], None) ou (None, [], raison) : la seule vidéo `nom` et ses images, par la même extraction
    sûre (signature, tailles, noms)."""
    if nom in NOMS_RESERVES or not re.fullmatch(MOTIF_NOM, nom, re.ASCII):
        return None, [], "nom de vidéo refusé"
    code, donnees, erreur = _octets(serveur, ssh, "bash -s",
                                    _script_rapatrier(ident, limites, film=nom).encode("utf-8"), delai=300)
    if code != 0:
        return None, [], f"vidéo non rapatriée (code {code}) {_court(erreur, 200)}".strip()
    dest = Path(destination)
    _dossier_sur(dest)
    res = _extraire(donnees, dest, limites)
    v = res["videos"].get(nom)
    if v and v["mp4"]:
        return Path(v["mp4"]), sorted(v["images"]), None
    return None, [], "vidéo absente ou refusée au rapatriement"


def verbe(ident, nom, arguments, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, destination=None,
          dormir=time.sleep):
    """Relaie UN verbe au pont du conteneur (`sudo -n docker exec tache-<id> /usr/local/bin/pont <verbe> <args>`, sans
    environnement), après validation locale par `valider_verbe` : `ValueError` avant toute connexion sinon.

    Renvoie `{ok, verbe, code, detail}` (code du pont : 0, 2 refus, 3 limite, 4 échec ; 124/255 serveur injoignable).
    `demarrer` attend d'abord `sortie/.avd-pret` (AVD_ATTENTE_S au plus). `capturer` réussi : la capture est rapatriée
    dans `destination/captures/` (par défaut `<dossier>/taches/<id>/`) et `capture` donne son chemin local. `finfilm`
    réussi : la vidéo et ses images sont rapatriées dans `destination/videos/` (`video`, `images`). Un code 3
    est noté dans la fiche (`limite_atteinte`) pour le statut du rapport.

    Le lanceur applique lui-même la limite de captures de la demande (le pont n'applique que ses propres valeurs par
    défaut) : chaque `capturer` réserve une place dans la fiche (`captures_prises`, sous le verrou de l'index) ; au-delà
    de `limites["captures"]`, refus code 3 sans rien relayer ; une capture refusée par le pont rend sa place."""
    _id_valide(ident)
    args = valider_verbe(nom, arguments)
    serveur = _serveur_de(ident, dossier)
    if nom == "demarrer":
        echec = _attendre_avd(serveur, ssh, ident, dormir, dossier)
        if echec:
            return _masque(echec, dossier)
    reservee = False
    if nom == "capturer":
        try:
            reservee, maximum = Index(dossier).reserver(ident, "captures_prises",
                                                        lambda fiche: int(_limites_fiche(fiche)["captures"]))
        except (ErreurIndex, TimeoutError, ValueError, OSError) as e:
            return _masque({"ok": False, "verbe": nom, "code": 4,
                            "detail": f"Comptage des captures impossible ({_court(e)}) : capture refusée."}, dossier)
        if not reservee:
            res = {"ok": False, "verbe": nom, "code": 3,
                   "detail": f"Limite de captures de la tâche atteinte ({maximum})."}
            avert = _noter(dossier, ident, {"limite_atteinte": True})
            if avert:
                res["avertissement"] = avert
            return _masque(res, dossier)
    script = _script(_VERBE, ident, VERBE=" ".join([nom, *(shlex.quote(a) for a in args)]))
    code, sortie, erreur = _bash(serveur, ssh, script, delai=DELAIS_VERBE_S.get(nom, DELAI_VERBE_S))
    res = _reponse_pont(nom, code, sortie, erreur)
    lisible = res.pop("_lisible", False)
    # La place n'est rendue que sur un refus certain du pont (ligne JSON lisible, ok faux) ; réponse perdue (124/255) ou
    # illisible : on ne sait pas si la capture a été prise, la place reste comptée (côté prudent).
    if reservee and lisible and not res["ok"]:
        try:
            Index(dossier).liberer(ident, "captures_prises")
        except (ErreurIndex, TimeoutError, ValueError, OSError):
            pass                                   # place perdue : la limite reste du côté prudent
    if code == 3:
        avert = _noter(dossier, ident, {"limite_atteinte": True})
        if avert:
            res["avertissement"] = avert
    if nom == "capturer" and res["ok"]:
        limites = _limites_fiche(Index(dossier).lire().get(ident) or {})
        try:
            chemin, raison = _rapatrier_capture(serveur, ssh, ident, args[0],
                                                destination or Path(dossier) / "taches" / ident, limites)
        except (ValueError, OSError) as e:
            chemin, raison = None, _court(e)
        if chemin:
            res["capture"] = str(chemin)
        else:
            res["ok"] = False
            res["detail"] = f"{res['detail']} Capture prise mais non rapatriée : {raison}."
    if nom == "finfilm" and res["ok"]:
        # Le nom du film vient de la réponse du pont (« videos/<nom>.mp4 (...) ») : une donnée, revalidée par le motif des
        # noms et les noms réservés avant de servir ; rien n'est rapatrié sinon.
        m = MOTIF_DETAIL_FILM.match(res["detail"])
        film = m.group(1) if m and m.group(1) not in NOMS_RESERVES else None
        chemin, images, raison = None, [], "réponse du pont inattendue"
        if film:
            limites = _limites_fiche(Index(dossier).lire().get(ident) or {})
            try:
                chemin, images, raison = _rapatrier_film(serveur, ssh, ident, film,
                                                         destination or Path(dossier) / "taches" / ident, limites)
            except (ValueError, OSError) as e:
                chemin, images, raison = None, [], _court(e)
        if chemin:
            res["video"], res["images"] = str(chemin), [str(i) for i in images]
        else:
            res["ok"] = False
            res["detail"] = f"{res['detail']} Film fini mais non rapatrié : {raison}."
    return _masque(res, dossier)
