"""La route serveur d'une campagne de tests (conception § 5.4) : instantané tar de l'arbre de travail, déposé par SSH dans
`~/tests/<id>/entree/entree.tar`, puis UNE session SSH qui lance l'enveloppe `lancer_tests.sh` (place, conteneur sans
réseau, sortie en direct, `#fin`) ; l'entrée standard de la session est la laisse.

Repli au poste (sous le verrou du poste, `campagne.executer`), UNE fois, avec une ligne, dans ces cas seulement :
  R1 aucun serveur prêt pour `tests-image` (état local) ; R2 dépôt en échec de connexion (255/124) ; R3 l'enveloppe refuse
  AVANT le départ du conteneur : disque (76), image (77), cache des dépendances (78), échauffement (79), docker qui n'a
  pas démarré (125–127) ; R4 session perdue avant `#fin` SANS rien reçu du conteneur (connexion, ou seulement l'attente
  d'une place) ; R5 instantané hors limites, projet hors git (et tout ce qui empêche l'envoi avant la moindre connexion).
Jamais de repli : test en échec (code de la commande), Ctrl-C (130, rien n'est relancé), `--serveur` (code 4), argument
refusé par l'enveloppe (2), `--sans-attendre` sur places prises (3), campagne arrêtée au serveur après son départ (74 :
disque, inodes, dossier de travail ; 124 délai ; 130 signal ; 1 enveloppe en échec), session perdue après que le conteneur
a parlé (1 : résultat inconnu). Après R2 ou R4 (et une session perdue), le serveur est noté injoignable 300 s
(`INJOIGNABLE`) : pendant ce temps, poste sans aucun essai SSH ; une session menée à `#fin` par CE serveur l'efface.

Le code rendu n'est JAMAIS lu dans la sortie : seule la marque `#fin` validée par `plateforme_ssh.executer_en_flux` fait
foi, et un code de l'enveloppe n'est pris pour un refus que si la session a lu `#refus` (clé `refus`).

Les attentes d'une place au serveur sont notées dans `ATTENTES_SERVEUR`, un dossier à part : la file du poste
(`campagne._file`, `_devant`, `attendre_son_tour`, `en_attente`, lue par `bureau/serveur.py:_attentes_tests`) les ignore.

Python 3.12 ; importé à l'appel seulement, ou lancé à part : `serveur-tests [--dossier D] [--sans-attendre] [--serveur]
-- <commande>`.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

import campagne  # noqa: E402
import plateforme_acces  # noqa: E402
import plateforme_ssh  # noqa: E402
import serveur_etat  # noqa: E402
import serveur_tache  # noqa: E402
import tests_instantane  # noqa: E402
from plateforme import DOSSIER_DISTANT  # noqa: E402

LIMITES = {"cpus": 4, "memoire_mo": 8192, "duree_s": 1800}
PLACES_DEFAUT = 3      # mesuré (J3) : 3 campagnes complètes simultanées = 179 s chacune, comme une seule (165 s) ; 4 : 207 s
PLACES_MAX = 4
INJOIGNABLE_S = 300
INJOIGNABLE = Path("~/MyIAFactory/tests-serveur-injoignable.json").expanduser()
# Hors de `campagne.ATTENTES` : une attente au serveur ne doit jamais retenir la file du poste (ni en fausser les rangs).
ATTENTES_SERVEUR = Path("~/MyIAFactory/tests-en-attente-serveur").expanduser()


def attentes_serveur_par_defaut():
    """`ATTENTES_SERVEUR`, sauf dans un processus de test lancé par le lanceur (`campagne.isole()`) : le même nom sous
    `campagne.dossier_etat()`, jamais le vrai dossier. Résolu à chaque appel."""
    return ATTENTES_SERVEUR if not campagne.isole() else campagne.dossier_etat() / ATTENTES_SERVEUR.name
ENVELOPPE_DISTANTE = f"{DOSSIER_DISTANT}/taches/lancer_tests.sh"
REQUISES = ("tests-image",)
DEPOT_MIN_S = 120
DEPOT_MAX_S = 1800
DEPOT_OCTETS_S = 1_000_000 / 8           # 1 Mbit/s au pire
NETTOYAGE_S = 30
COMMANDE_MAX_OCTETS = 4096
COMMANDE_MAX_ELEMENTS = 64
INJOIGNABLES = (124, 255)                # délai dépassé, connexion SSH impossible ou perdue
CODE_EXISTE = serveur_tache.CODE_EXISTE  # le dépôt trouve ~/tests/<id> : identifiant pris, un autre est tiré
ESSAIS_ID = serveur_tache.ESSAIS_ID
REFUS_REPLI = (76, 77, 78, 79, 125, 126, 127)   # l'enveloppe n'a pas lancé le conteneur
ARRET_SERVEUR = 74                       # campagne arrêtée au serveur après son départ (disque, inodes, travail/)
CODES_CTRL_C = (130, 0xC000013A, -2)     # ssh tué par le Ctrl-C (console Windows : STATUS_CONTROL_C_EXIT ; POSIX : SIGINT)
FIN_GARDEE = 4096
TRAVAIL_GO_MIN, TRAVAIL_GO_MAX = 1, 200     # absent : l'enveloppe prend 10 Go
MOTIF_PROJET = re.compile(r"[a-z0-9][a-z0-9-]{0,39}", re.ASCII)
MOTIF_DEPS = re.compile(r"[0-9a-f]{16}", re.ASCII)
MOTIF_DISTANT = re.compile(r"\$HOME(/[A-Za-z0-9_.-]+)+", re.ASCII)
OPTIONS_DEPOT = ("-o", "LogLevel=ERROR", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4")
MESSAGES_ARRET = {
    # 74 : TOUT arrêt de l'enveloppe en cours de campagne (disque < 2 Go, inodes, travail/ au-delà de travail_go, échéance
    # du surveillant, conteneur dans un état inattendu après docker run).
    ARRET_SERVEUR: ("campagne arrêtée au serveur par l'enveloppe (disque, inodes, taille du dossier de travail, échéance ou "
                    "état inattendu du conteneur) : le résultat est inconnu"),
    124: "délai dépassé au serveur (durée maximale de la campagne)",
    130: "campagne arrêtée au serveur (signal)",
    1: "l'enveloppe a échoué au serveur",
}


class Repli(Exception):
    """La campagne ne peut pas partir au serveur (ou le serveur ne l'a pas lancée) ; `.raison` est dite au poste."""

    def __init__(self, raison, injoignable=None):
        Exception.__init__(self, raison)
        self.raison = raison
        self.injoignable = injoignable      # identifiant du serveur à noter injoignable (R2, R4), sinon None


class _Rendu(Exception):
    """Fin sans repli avec ce code (Ctrl-C pendant le dépôt)."""

    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


def commande_conteneur(commande: List[str]) -> List[str]:
    """La commande du poste telle que le conteneur Linux la lance : `py`, `py -3.12`, `python`, `python.exe` en tête →
    `python3` ; `npx.cmd`/`npm.cmd` → `npx`/`npm` ; le reste tel quel."""
    commande = [str(x) for x in commande]
    if not commande:
        return commande
    tete = commande[0].lower()
    if tete in ("py", "py.exe"):
        reste = commande[1:]
        if reste and reste[0].startswith("-3"):
            reste = reste[1:]
        return ["python3", *reste]
    if tete in ("python", "python.exe"):
        return ["python3", *commande[1:]]
    if tete in ("npx.cmd", "npm.cmd"):
        return [tete[:-4], *commande[1:]]
    return commande


# --- mémoire de l'injoignable --------------------------------------------------------------------------------------

def _lire_memoire(chemin):
    try:
        with open(chemin, "rb") as f:
            x = json.loads(f.read(4096).decode("utf-8"))
        return x if isinstance(x, dict) else None
    except (OSError, ValueError):
        return None


def _injoignable_actif(chemin, serveur_id, maintenant):
    """Vrai si `chemin` dit ce serveur injoignable jusqu'à une date à venir, et au plus 300 s devant (horloge reculée ou
    fichier forgé : ignoré). Ne lève jamais."""
    x = _lire_memoire(chemin)
    if x is None:
        return False
    jusqu_a = x.get("jusqu_a")
    if x.get("serveur_id") != serveur_id or isinstance(jusqu_a, bool) or not isinstance(jusqu_a, (int, float)):
        return False
    return maintenant < jusqu_a <= maintenant + INJOIGNABLE_S


def _noter_injoignable(chemin, serveur_id, maintenant):
    try:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        temporaire = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
        temporaire.write_text(json.dumps({"serveur_id": serveur_id, "jusqu_a": maintenant + INJOIGNABLE_S}),
                              encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        pass        # une économie : sans elle, la prochaine campagne réessaie


def _oublier_injoignable(chemin, serveur_id):
    """Efface la mémoire seulement si elle parle de ce serveur (un autre serveur reste noté)."""
    x = _lire_memoire(chemin)
    if x is None or x.get("serveur_id") != serveur_id:
        return
    try:
        Path(chemin).unlink()
    except OSError:
        pass


# --- sorties ---------------------------------------------------------------------------------------------------------

class _ErreurMontree:
    """Reçoit de `executer_en_flux` la sortie d'erreur ligne par ligne (marques déjà retirées). Le préfixe `| ` de
    l'enveloppe (sortie d'erreur du conteneur : unittest y écrit) est ôté pour l'affichage, sauf si la ligne du conteneur
    imite une ligne de l'enveloppe (`#…`, `lancer_tests…`) : elle reste alors marquée `| `. Le chemin de la clé SSH (que
    ssh peut citer dans ses erreurs) est masqué. `conteneur_vu` : une ligne du conteneur est arrivée. 4 Ko de fin gardés
    pour compter les tests."""

    def __init__(self, flux, cle=None):
        self.flux = flux
        self.fin = b""
        self.conteneur_vu = False
        self.masques = []
        if cle:
            texte = str(cle)
            for forme in {texte, texte.replace("\\", "/"), texte.replace("/", "\\")}:
                self.masques.append(forme.encode("utf-8"))

    def write(self, b):
        if b.startswith(b"| ") or b == b"|\n":
            self.conteneur_vu = True
            reste = b[2:] if b.startswith(b"| ") else b"\n"
            imite = reste.startswith(b"#") or reste.lstrip().lower().startswith(b"lancer_tests")
            montre, compte = (b if imite else reste), reste
        else:
            montre = compte = b
        for m in self.masques:
            montre = montre.replace(m, b"<cle>")
        self.fin = (self.fin + compte)[-FIN_GARDEE:]
        if self.flux is not None:
            try:
                self.flux.write(montre)
            except (OSError, ValueError):
                self.flux = None

    def flush(self):
        if self.flux is not None:
            try:
                self.flux.flush()
            except (OSError, ValueError):
                self.flux = None


def _erreur_du_poste():
    flux = sys.stderr
    if flux is None:
        return None
    try:
        flux.flush()
    except (OSError, ValueError):
        pass
    tampon = getattr(flux, "buffer", None)
    return tampon if tampon is not None else campagne._VersTexte(flux)


def _tests_mesures():
    try:
        from bureau import tests_mesures
    except ImportError:
        sys.path.append(str(ICI.parent))
        from bureau import tests_mesures
    return tests_mesures


def _fin_pour_la_mesure(fin_sortie, fin_erreur):
    """Le texte dont `tests_mesures.nb_tests_de` lit les dernières lignes : unittest résume sur la sortie d'erreur, les
    autres outils (vitest, jest, tests_paralleles) sur la sortie standard ; celle qui porte un résumé passe en dernier."""
    try:
        nb = _tests_mesures().nb_tests_de
    except ImportError:
        return fin_sortie + "\n" + fin_erreur
    if nb(fin_sortie) is not None and nb(fin_erreur) is None:
        return fin_erreur + "\n" + fin_sortie
    return fin_sortie + "\n" + fin_erreur


def _noter_par_defaut(dossier, **mesure):
    return campagne._noter_par_defaut(dossier, **mesure)


def _refus_par_defaut(racine):
    """L'accord du Directeur pour ce dossier (`deport_types.refus_route`, le vrai bureau) : None, ou la raison du refus.
    Une erreur inattendue est un refus."""
    try:
        try:
            from bureau import deport_types
        except ImportError:
            sys.path.append(str(ICI.parent))
            from bureau import deport_types
        return deport_types.refus_route(racine, "tests")
    except Exception as e:  # noqa: BLE001 — jamais de route sur un doute
        return f"accord illisible ({type(e).__name__})"


def _projet_par_defaut(dossier):
    return _tests_mesures().projet_enregistre(dossier)


# --- la route --------------------------------------------------------------------------------------------------------

def _premiere_ligne(commande):
    distante = commande_conteneur(commande)
    if not distante or len(distante) > COMMANDE_MAX_ELEMENTS:
        raise Repli(f"refusé (commande de {len(distante)} éléments : 1 à {COMMANDE_MAX_ELEMENTS})")
    ligne = json.dumps(distante, ensure_ascii=False).encode("utf-8")
    if len(ligne) > COMMANDE_MAX_OCTETS:
        raise Repli(f"refusé (commande de plus de {COMMANDE_MAX_OCTETS} octets)")
    return ligne


def _instantane(instantane, racine, fichier, dire):
    """Écrit l'archive dans `fichier` (fermé en sortant, même sur Ctrl-C) ; `Repli` (R5) si elle ne peut pas partir."""
    try:
        fichiers, ecartes = instantane.lister(racine)
        if ecartes:
            dire(f"Instantané : {len(ecartes)} fichier(s) écarté(s) : " + ", ".join(str(e) for e in ecartes[:10])
                 + (" …" if len(ecartes) > 10 else ""))
        executables = instantane.executables(racine)
        with open(fichier, "wb") as f:
            instantane.ecrire_tar(racine, fichiers, f, executables=executables)
    except instantane.HorsLimites as e:
        raise Repli(f"refusé (instantané : {e.raison})") from None
    except OSError as e:
        raise Repli(f"refusé (instantané impossible : {type(e).__name__})") from None


def _effacer(dossier, dormir):
    """Efface le dossier privé de l'archive ; sous Windows un fichier encore ouvert (ssh tué à l'instant) résiste un
    moment : quelques essais."""
    for _ in range(5):
        shutil.rmtree(dossier, ignore_errors=True)
        if not os.path.exists(dossier):
            return
        dormir(0.2)


def _ssh_octets(serveur, ssh, commande, entree, delai, options=()):
    """(code, erreur) d'un appel `executer_octets` ; toute exception (hôte invalide, ssh absent) → 255."""
    try:
        if options:
            code, _sortie, erreur = ssh.executer_octets(serveur_etat.cible(serveur), commande, serveur.cle,
                                                        entree=entree, delai=delai, _plus=options)
        else:
            code, _sortie, erreur = ssh.executer_octets(serveur_etat.cible(serveur), commande, serveur.cle,
                                                        entree=entree, delai=delai)
    except Exception as e:  # noqa: BLE001
        return 255, type(e).__name__
    return code, erreur if isinstance(erreur, str) else ""


def _dossier_distant(ident):
    return f"\"$HOME/tests/{ident}\""


def _nettoyer(serveur, ssh, ident):
    """Au mieux : efface `~/tests/<id>` que NOUS avons créé (dépôt raté, refus 2 : l'enveloppe ne l'efface pas)."""
    _ssh_octets(serveur, ssh, f"rm -rf -- {_dossier_distant(ident)}", None, NETTOYAGE_S)


def _deposer(serveur, ssh, ident, fichier):
    """Dépose l'archive (lue depuis le fichier par ssh, jamais en mémoire). Rend vrai si déposée, faux si l'identifiant
    est déjà pris au serveur ; `Repli` (R2 et autres échecs), `_Rendu(130)` sur Ctrl-C."""
    d = _dossier_distant(ident)
    commande = (f"umask 077 && mkdir -p -- \"$HOME/tests\" && "
                f"{{ mkdir -m 700 -- {d} || {{ [ -e {d} ] && exit {CODE_EXISTE}; exit 1; }}; }} && "
                f"mkdir -m 700 -- {d}/entree && set -C && cat > {d}/entree/entree.tar")
    taille = os.path.getsize(fichier)
    delai = int(min(DEPOT_MAX_S, DEPOT_MIN_S + taille / DEPOT_OCTETS_S))
    with open(fichier, "rb") as f:
        code, erreur = _ssh_octets(serveur, ssh, commande, f, delai, OPTIONS_DEPOT)
    if code == 0:
        return True
    if code == CODE_EXISTE:
        return False
    if code in CODES_CTRL_C:
        raise _Rendu(130)
    if plateforme_ssh.CHANGEMENT_CLE in erreur:
        raise Repli("injoignable (clé d'hôte changée : à vérifier dans le bureau, Serveurs)", injoignable=serveur.id)
    if "Permission denied" in erreur:
        raise Repli("injoignable (accès refusé par le serveur)", injoignable=serveur.id)
    if code in INJOIGNABLES:
        raise Repli(f"injoignable (dépôt de l'instantané : code {code})", injoignable=serveur.id)
    _nettoyer(serveur, ssh, ident)
    raise Repli(f"refusé (dépôt de l'instantané : code {code})")


class _Attente:
    """`#attente r t` : note pour le bureau (dossier `ATTENTES_SERVEUR`, hors de la file du poste), une ligne à chaque
    changement ; sans attendre, la session est coupée dès la première (places toutes prises : code 3)."""

    def __init__(self, attentes, racine, attendre, dire, maintenant):
        self.attentes, self.racine, self.attendre, self.dire = attentes, racine, attendre, dire
        self.maintenant = maintenant
        self.processus = None
        self.refuse = None
        self.dit = None
        self.notee = False
        self.depuis = None
        self.arrivee = None
        self.verrou = threading.Lock()

    def popen(self, base):
        def lancer(*a, **k):
            p = base(*a, **k)
            with self.verrou:
                self.processus = p
            return p
        return lancer

    def __call__(self, rang, total):
        motif = f"place de tests au serveur (rang {rang}/{total})"
        if not self.attendre:
            with self.verrou:
                if self.refuse is None:
                    self.refuse = motif
                p = self.processus
            if p is not None:
                try:
                    p.kill()        # la laisse tombe : l'enveloppe quitte la file, aucun conteneur ne reste
                except OSError:
                    pass
            return
        if motif == self.dit:
            return
        self.dit = motif
        self.dire(f"En attente : {motif}.", flush=True)
        self.depuis = self.depuis or datetime.now().astimezone().isoformat(timespec="seconds")
        self.arrivee = self.arrivee or self.maintenant()
        campagne._noter_l_attente(self.attentes, self.racine, motif, self.depuis, self.arrivee)
        self.notee = True

    def oublier(self):
        if self.notee:
            campagne._oublier_l_attente(self.attentes)


def places_de(serveur):
    """Campagnes simultanées voulues pour ce serveur : son réglage `places_tests` (1 à 4), sinon `PLACES_DEFAUT`."""
    voulues = getattr(serveur, "places_tests", None)
    if isinstance(voulues, bool) or not isinstance(voulues, int) or not 1 <= voulues <= PLACES_MAX:
        return PLACES_DEFAUT
    return voulues


def _au_serveur(commande, racine, attendre, places, dossier_etat, ssh, noter, horloge, maintenant, dire, choisir,
                instantane, projet_de, injoignable, attentes, sortie, sortie_erreur, nouvel_id, forcer, popen_base,
                dormir, travail_go=None):
    """La campagne au serveur ; rend son code, ou lève `Repli`. `KeyboardInterrupt` remonte telle quelle."""
    appel = horloge()
    try:
        serveur = choisir(dossier_etat, requises=REQUISES)
    except serveur_tache.RefusLancement as e:
        raise Repli(f"indisponible ({e})") from None
    if not forcer and _injoignable_actif(injoignable, serveur.id, maintenant()):
        raise Repli("injoignable il y a moins de 5 minutes")
    try:
        serveur_etat.cible(serveur)
    except ValueError as e:
        raise Repli(f"mal déclaré ({e})") from None
    if not MOTIF_DISTANT.fullmatch(ENVELOPPE_DISTANTE):
        raise Repli("refusé (chemin de l'enveloppe au serveur invalide)")
    trouve = projet_de(racine)
    projet = trouve[0] if trouve else None
    if not isinstance(projet, str) or not MOTIF_PROJET.fullmatch(projet):
        raise Repli("refusé (projet non enregistré au bureau)")
    if places is None:
        places = places_de(serveur)
    if isinstance(places, bool) or not isinstance(places, int) or not 1 <= places <= PLACES_MAX:
        raise Repli(f"refusé (places {places!r} : 1 à {PLACES_MAX})")
    if travail_go is not None and (isinstance(travail_go, bool) or not isinstance(travail_go, int)
                                   or not TRAVAIL_GO_MIN <= travail_go <= TRAVAIL_GO_MAX):
        raise Repli(f"refusé (travail_go {travail_go!r} : {TRAVAIL_GO_MIN} à {TRAVAIL_GO_MAX} Go)")
    ligne = _premiere_ligne(commande)

    prive = tempfile.mkdtemp(prefix="myiafactory-tests-")      # 0700 ; jamais dans le projet
    try:
        archive = os.path.join(prive, "entree.tar")
        _instantane(instantane, racine, archive, dire)
        deps = instantane.empreinte_verrou_node(racine) or "-"
        if deps != "-" and not (isinstance(deps, str) and MOTIF_DEPS.fullmatch(deps)):
            raise Repli("refusé (empreinte du verrou Node invalide)")
        ident = None
        for _ in range(ESSAIS_ID):
            essai = nouvel_id()
            if not isinstance(essai, str) or not serveur_tache.MOTIF_ID.fullmatch(essai):
                raise Repli("refusé (identifiant de campagne invalide)")
            if _deposer(serveur, ssh, essai, archive):
                ident = essai
                break
        if ident is None:
            raise Repli(f"refusé (identifiant de campagne déjà pris {ESSAIS_ID} fois)")
    finally:
        _effacer(prive, dormir)

    distante = (f"\"{ENVELOPPE_DISTANTE}\" {ident} {places} {LIMITES['cpus']} {LIMITES['memoire_mo']} "
                f"{LIMITES['duree_s']} {projet} {deps}")
    if travail_go is not None:
        distante += f" {int(travail_go)}"         # 8e argument (facultatif) : taille maximale de travail/, en Go
    attente = _Attente(attentes, racine, attendre, dire, maintenant)
    erreur = _ErreurMontree(sortie_erreur if sortie_erreur is not None else _erreur_du_poste(), serveur.cle)
    depart = horloge()
    try:
        r = ssh.executer_en_flux(serveur_etat.cible(serveur), distante, serveur.cle, ligne,
                                 sortie if sortie is not None else campagne._sortie_du_poste(),
                                 sur_attente=attente, popen=attente.popen(popen_base), sortie_erreur=erreur)
    finally:
        attente.oublier()
    fin_serveur, refus = r.get("fin_serveur"), r.get("refus")
    code, code_ssh, octets = r.get("code"), r.get("code_ssh"), r.get("octets") or 0

    if attente.refuse is not None and (fin_serveur is None or fin_serveur[0] == 130):
        dire(f"Refusé : {attente.refuse} toutes prises. Les campagnes attendent leur tour au serveur.")
        return 3
    if fin_serveur is None:
        if code_ssh in CODES_CTRL_C or code in CODES_CTRL_C:
            return 130                   # ssh arrêté par le Ctrl-C : rien n'est relancé
        if code in INJOIGNABLES or r.get("raison") == "connexion":
            if r.get("raison") == "connexion" or (octets == 0 and not erreur.conteneur_vu):
                raise Repli(f"injoignable (session perdue avant le départ des tests : {r.get('raison') or code})",
                            injoignable=serveur.id)
            _noter_injoignable(injoignable, serveur.id, maintenant())
            dire("Serveur : session perdue au serveur après le départ des tests : résultat inconnu, rien n'est relancé.")
            return 1
        dire(f"Serveur : fin de campagne non confirmée (code {code}) ; résultat inconnu, compté en échec.")
        return 1
    _oublier_injoignable(injoignable, serveur.id)       # ce serveur a mené la session jusqu'à #fin
    if refus is not None:
        if refus in REFUS_REPLI:
            raise Repli(f"en refus (code {refus} de l'enveloppe, tests non lancés)")
        if refus not in MESSAGES_ARRET:
            if refus == 2:
                _nettoyer(serveur, ssh, ident)
            dire(f"Serveur : l'enveloppe a refusé la campagne (code {refus}) ; rien n'est relancé.")
            return refus
        dire(f"Serveur : {MESSAGES_ARRET[refus]}, rien n'est relancé.")
        code = refus
    try:
        _code, debut, fin, attente_s = fin_serveur
        (noter or _noter_par_defaut)(
            racine, commande=" ".join(str(x) for x in commande), duree_s=max(0, fin - debut),
            attente_s=max(0.0, depart - appel) + max(0, attente_s), code=code,
            fin=_fin_pour_la_mesure(r.get("fin") or "", erreur.fin.decode("utf-8", "replace")),
            octets=r.get("octets"), lieu="serveur", tache=os.environ.get(campagne.VARIABLE_TACHE) or None)
    except Exception:  # noqa: BLE001 — la mesure ne casse jamais une campagne
        pass
    return code


def executer(commande, dossier=None, attendre=True, forcer=False, places=None, dossier_etat=plateforme_acces.DOSSIER,
             ssh=plateforme_ssh, executer_poste=campagne.executer, noter=None, horloge=time.monotonic,
             maintenant=time.time, dire=print, *, choisir=None, instantane=tests_instantane, projet_de=None,
             injoignable=INJOIGNABLE, attentes=None, sortie=None, sortie_erreur=None,
             nouvel_id=serveur_tache.nouvel_id, _popen=subprocess.Popen, dormir=time.sleep, accord=None,
             travail_go=None) -> int:
    """Lance `commande` au serveur et rend son code ; sinon (règles R1–R5) au poste, une fois, sous son verrou. Avec
    `forcer` (`--serveur`) : jamais de repli, la raison est dite et le code est 4. `KeyboardInterrupt` remonte (le
    lanceur rend 130) : rien n'est relancé, rien n'est noté.
    L'accord du Directeur (`deport_types.refus_route(racine, "tests")`, `accord(racine) -> refus | None`) est revérifié
    ici à chaque appel, sur le dossier résolu, avant toute connexion : sans lui, le poste avec une ligne, ou code 2 avec
    `forcer` (`--serveur` force la route, jamais l'accord)."""
    commande = [str(x) for x in commande]
    if attentes is None:
        attentes = attentes_serveur_par_defaut()
    racine = str(Path(dossier or os.getcwd()).resolve())
    refus = (accord or _refus_par_defaut)(racine)
    if refus:
        if forcer:
            dire(f"Tests au serveur refusés : {refus}")
            return 2
        dire(f"Serveur refusé ({refus.splitlines()[0]}) : tests au poste (une campagne à la fois).")
        return executer_poste(commande, dossier=dossier, attendre=attendre)
    try:
        return _au_serveur(commande, racine, attendre, places, dossier_etat, ssh, noter, horloge, maintenant, dire,
                           choisir or serveur_tache.choisir_serveur, instantane, projet_de or _projet_par_defaut,
                           injoignable, attentes, sortie, sortie_erreur, nouvel_id, forcer, _popen, dormir,
                           travail_go=travail_go)
    except _Rendu as e:
        return e.code
    except Repli as e:
        repli = e
    if isinstance(repli.injoignable, str):
        _noter_injoignable(injoignable, repli.injoignable, maintenant())
    if forcer:
        dire(f"Serveur {repli.raison}.")
        return 4
    dire(f"Serveur {repli.raison} : tests au poste (une campagne à la fois).")
    return executer_poste(commande, dossier=dossier, attendre=attendre)


def main(argv=None, executer=executer) -> int:
    """`serveur-tests [--dossier D] [--sans-attendre] [--serveur] -- <commande>`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv or argv.index("--") == len(argv) - 1:
        print("Usage : serveur-tests [--dossier <dossier>] [--sans-attendre] [--serveur] -- <commande de test>",
              file=sys.stderr)
        return 2
    i = argv.index("--")
    options, commande = argv[:i], argv[i + 1:]
    dossier, attendre, forcer = None, True, False
    while options:
        o = options.pop(0)
        if o == "--dossier" and options:
            dossier = options.pop(0)
        elif o == "--sans-attendre":
            attendre = False
        elif o == "--serveur":
            forcer = True
        else:
            print(f"Option inconnue : {o}", file=sys.stderr)
            return 2
    try:
        return executer(commande, dossier=dossier, attendre=attendre, forcer=forcer)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
