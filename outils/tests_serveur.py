"""La route serveur d'une campagne de tests (conception § 5.4) : instantané tar de l'arbre de travail, déposé par SSH dans
`~/tests/<id>/entree/entree.tar`, puis UNE session SSH qui lance l'enveloppe `lancer_tests.sh` (place, conteneur sans
réseau, sortie en direct, `#fin`) ; l'entrée standard de la session est la laisse.

Repli au poste (sous le verrou du poste, `campagne.executer`), UNE fois, avec une ligne, dans ces cas seulement :
  R1 aucun serveur prêt pour `tests-image` (état local) ; R2 dépôt en échec de connexion (255/124) ; R3 l'enveloppe refuse
  AVANT le départ du conteneur : disque (76), image (77), cache des dépendances (78), échauffement (79 : réseau non
  accordé, wrapper Gradle modifié, échec, plafond…), docker qui n'a pas démarré (125–127) ; R4 session perdue avant `#fin`
  SANS rien reçu du conteneur (connexion, ou seulement l'attente d'une place) ; R5 instantané hors limites, projet hors git,
  échauffement qui exécute du code du projet sans l'accord réseau du Directeur (et tout ce qui empêche l'envoi avant la
  moindre connexion).
Dépendances (§ 5.13) : `deps` = `tests_profil.empreinte_deps` de la famille lancée ; l'enveloppe prépare le cache s'il manque.
Gradle Android : le SDK de l'hôte est sondé par SSH (`sonder_sdk`) avant l'envoi.
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
import serveur_modele  # noqa: E402
import serveur_tache  # noqa: E402
import tests_images  # noqa: E402
import tests_instantane  # noqa: E402
from plateforme import DOSSIER_DISTANT  # noqa: E402

LIMITES = {"cpus": 4, "memoire_mo": 8192, "duree_s": 1800}
# Bornes des limites d'une campagne (§ 5.14) : au-delà, décision du Directeur (le profil forcé ne les dépasse jamais).
BORNES_LIMITES = {"cpus": 8, "memoire_mo": 16384, "duree_s": 3600}
UNITE_MEMOIRE_MO = 2048        # un jeton de mémoire de l'enveloppe (~/taches/.jeton-tests-1..20)
BUDGET_UNITES_DEFAUT = 16      # celui de l'enveloppe quand le 14e argument est absent (= 32 768 Mo)
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
    `python3` ; `npx.cmd`/`npm.cmd` → `npx`/`npm` ; `gradlew.bat`/`mvnw.cmd` → `./gradlew`/`./mvnw` ; `dotnet.exe` → `dotnet` ;
    `godot*.exe` → `godot` ; le reste tel quel."""
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
    nu = tete.replace("\\", "/")
    if nu.startswith("./"):
        nu = nu[2:]
    if nu in ("gradlew.bat", "mvnw.cmd"):
        return ["./" + nu.rsplit(".", 1)[0], *commande[1:]]
    if tete == "dotnet.exe":
        return ["dotnet", *commande[1:]]
    if re.fullmatch(r"godot[a-z0-9_.-]*\.exe", tete):
        return ["godot", *commande[1:]]
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


def _analyse_par_defaut(racine, **options):
    """`tests_profil.analyser` (importé à l'appel : il lit le projet, ce que les routes refusées n'ont pas à payer)."""
    import tests_profil
    return tests_profil.analyser(racine, **options)


def _profil_de_la_campagne(analyse, racine, commande):
    """Le profil du projet pour la commande lancée ; `Repli` (R5, avant toute connexion) s'il est non déportable POUR CETTE
    COMMANDE (un projet React Native avec ios/ reste déportable pour jest) ou si l'analyse échoue (jamais de route sur un doute)."""
    try:
        profil = analyse(racine, lancee=list(commande))
    except Exception as e:  # noqa: BLE001
        raise Repli(f"refusé (analyse du projet impossible : {type(e).__name__})") from None
    if profil.non_deportable:
        raise Repli(f"refusé (non déportable : {profil.non_deportable})")
    return profil


def _image_de_la_campagne(profil, sdk_android):
    """(image, famille, capacités requises) d'après le catalogue ; `image` est None pour l'image par défaut (l'enveloppe la
    prend seule : la ligne de commande reste celle d'avant). `Repli` si aucune image du catalogue ne convient (les images
    dérivées ne sont pas encore construites) ou si le SDK Android du serveur ne couvre pas le projet."""
    choix = tests_images.choisir_image(profil, sdk_android)
    if choix["derivee"]:
        raise Repli("indisponible (aucune image du catalogue ne convient à ce projet : image dérivée à construire)")
    if choix["manque"]:
        raise Repli("indisponible (SDK Android du serveur incomplet : " + ", ".join(choix["manque"]) + ")")
    if not tests_images.CACHE_GRADLE_PRET and any(f.startswith("gradle") for f in profil.familles):
        # TÂCHE 14d : voir tests_images.CACHE_GRADLE_PRET (cache préchauffé, sonde réelle du SDK, AGP et SDK en :ro)
        raise Repli("indisponible (cache Gradle du serveur pas encore préparé : 14d)")
    image = choix["image"]
    requises = tuple(choix["capacites"])
    if image == tests_images.IMAGE_DEFAUT:
        return None, None, requises
    famille = next((f for f in profil.familles if f in tests_images.CATALOGUE_IMAGES[image]["familles"]), None)
    if not tests_images.MOTIF_IMAGE.fullmatch(image) or famille is None:
        raise Repli("refusé (image ou famille hors catalogue)")
    return image, famille, requises


def _projet_par_defaut(dossier):
    return _tests_mesures().projet_enregistre(dossier)


# --- dépendances : sonde du SDK, accord du réseau d'échauffement (§ 5.13, tâche 14d) ---------------------------------

BUDGET_CACHES_GO = 40
# Une commande courte et fixe, sans secret ni valeur du poste : les NOMS des dossiers du SDK de l'hôte (jamais un contenu).
SONDE_SDK = ('for d in platforms build-tools ndk licenses; do printf \'#%s\\n\' "$d"; '
             'ls -1 -- "$HOME/android-sdk/$d" 2>/dev/null | head -n 200; done')
_MOTIFS_SDK = {"platforms": re.compile(r"android-[0-9]{1,3}", re.ASCII),
               "build-tools": re.compile(r"[0-9]{1,3}(\.[0-9]{1,3}){1,3}(-rc[0-9]{1,2})?", re.ASCII),
               "ndk": re.compile(r"[0-9]{1,3}(\.[0-9]{1,5}){1,3}", re.ASCII),
               "licenses": re.compile(r"[a-z][a-z0-9-]{0,40}", re.ASCII)}
_CLES_SDK = {"platforms": "platforms", "build-tools": "build_tools", "ndk": "ndk", "licenses": "licences"}


def lire_sonde_sdk(sortie) -> dict:
    """`{platforms, build_tools, ndk, licences}` lus dans la sortie de `SONDE_SDK` ; toute ligne hors motif fermé est ignorée."""
    sdk = {v: [] for v in _CLES_SDK.values()}
    section = None
    texte = sortie.decode("utf-8", "replace") if isinstance(sortie, bytes) else str(sortie or "")
    for ligne in texte.splitlines()[:1000]:
        ligne = ligne.strip()
        if ligne.startswith("#"):
            section = ligne[1:] if ligne[1:] in _MOTIFS_SDK else None
        elif section and _MOTIFS_SDK[section].fullmatch(ligne):
            sdk[_CLES_SDK[section]].append(ligne)
    return sdk


def sonder_sdk(serveur, ssh) -> dict:
    """Le SDK Android de l'hôte relevé par une session SSH courte ; `Repli` (injoignable) si la sonde échoue."""
    try:
        code, sortie, _erreur = ssh.executer_octets(serveur_etat.cible(serveur), SONDE_SDK, serveur.cle, entree=None,
                                                    delai=60)
    except Exception as e:  # noqa: BLE001
        raise Repli(f"injoignable (sonde du SDK Android : {type(e).__name__})", injoignable=serveur.id) from None
    if code != 0:
        raise Repli(f"injoignable (sonde du SDK Android : code {code})",
                    injoignable=serveur.id if code in INJOIGNABLES else None)
    return lire_sonde_sdk(sortie)


def _reseau_code_par_defaut(racine):
    """Vrai seulement si TOUS les réglages que le bureau enregistre pour ce projet disent
    `tests.adoption.reseau_echauffement == "accorde"` (décision d'adoption, § 5.15) ; toute erreur : faux."""
    return _adoption_accordee(racine, "reseau_echauffement")


def _reseau_licence_par_defaut(racine):
    """Licence Unity B3 (réseau vers les hôtes de licence pendant les tests, § 5.16, QU1) : vrai seulement si TOUS les réglages
    du projet disent `tests.adoption.reseau_licence == "accorde"` ; toute erreur : faux."""
    return _adoption_accordee(racine, "reseau_licence")


def _adoption_accordee(racine, cle):
    try:
        try:
            from bureau import deport_types
        except ImportError:
            sys.path.append(str(ICI.parent))
            from bureau import deport_types
        fichiers = deport_types.reglages_enregistres(racine)
        if not fichiers:
            return False
        for fichier in fichiers:
            x = deport_types._lire_json_sur(fichier)       # refuse un fichier en lien, comme l'accord de la route
            tests = x.get("tests") if isinstance(x, dict) else None
            adoption = tests.get("adoption") if isinstance(tests, dict) else None
            if not isinstance(adoption, dict) or adoption.get(cle) != "accorde":
                return False
        return True
    except Exception:  # noqa: BLE001 — jamais de réseau sur un doute
        return False


# Exécuteur et licence Unity (tâche 14g) : 15e à 17e arguments de l'enveloppe. Motifs miroirs de lancer_tests.sh.
EXECUTEURS = ("conteneur", "hote_bac_a_sable")
LICENCES = ("B1", "B2", "B3")
MOTIF_HOTE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+", re.ASCII)
HOTES_LICENCE_MAX = 8
HOTES_LICENCE_OCTETS = 512
# Table FERMÉE des domaines de licence Unity (miroir de SUFFIXES_LICENCE de l'enveloppe, qui fait foi) : un hôte de B3 est l'un
# d'eux ou un nom dessous ; jamais une adresse IP (dernier libellé alphabétique), jamais un autre domaine.
SUFFIXES_LICENCE = ("unity3d.com", "unity.com")


def _hote_de_licence(h):
    return (isinstance(h, str) and MOTIF_HOTE.fullmatch(h) is not None
            and re.fullmatch(r"[a-z]{2,63}", h.rsplit(".", 1)[-1], re.ASCII) is not None
            and any(h == s or h.endswith("." + s) for s in SUFFIXES_LICENCE))


def _arguments_executeur(executeur, licence, hotes_licence, reseau_licence, racine):
    """Le suffixe de la ligne de l'enveloppe (« » sans exécuteur ni licence : la ligne d'avant ; sinon « <executeur> <licence>
    [<hôtes>] ») ; `Repli` (avant toute connexion) pour une valeur hors table, une liste d'hôtes hors motif ou sans B3, et pour
    B3 sans l'accord du Directeur (`tests.adoption.reseau_licence`, QU1) : B3 ouvre le réseau des tests vers les hôtes de licence."""
    if executeur is None and licence is None and not hotes_licence:
        return ""
    if executeur is not None and executeur not in EXECUTEURS:
        raise Repli("refusé (exécuteur hors table)")
    if licence is not None and licence not in LICENCES:
        raise Repli("refusé (licence Unity hors table : B1, B2 ou B3)")
    hotes = list(hotes_licence or ())
    if licence == "B3":
        if not (reseau_licence or _reseau_licence_par_defaut)(racine):
            raise Repli("refusé (licence Unity B3 : réseau de licence non accordé par le Directeur)")
        if not 1 <= len(hotes) <= HOTES_LICENCE_MAX:
            raise Repli(f"refusé (licence Unity B3 : 1 à {HOTES_LICENCE_MAX} hôtes de licence attendus)")
    elif hotes:
        raise Repli("refusé (hôtes de licence sans la licence B3)")
    if not all(_hote_de_licence(h) for h in hotes):
        raise Repli("refusé (hôte de licence hors motif ou hors des domaines de licence Unity)")
    if len(",".join(hotes)) > HOTES_LICENCE_OCTETS:
        raise Repli(f"refusé (hôtes de licence : {HOTES_LICENCE_OCTETS} caractères au plus)")
    suffixe = f" {executeur or 'conteneur'} {licence or '-'}"
    return suffixe + (f" {','.join(hotes)}" if hotes else "")


def _deps_de_la_campagne(profil, famille, commande, racine, empreinte):
    """(clé d'échauffement, deps 16 hexa ou « - », famille des dépendances)."""
    import tests_profil
    cible = famille or tests_profil._famille_cible(commande_conteneur(commande), list(profil.familles))
    cle = tests_profil.cle_echauffement(profil, cible) if cible else None
    if cle is None:
        return None, "-", cible
    try:
        deps = (empreinte or tests_profil.empreinte_deps)(profil, racine, famille=cible)
    except Exception as e:  # noqa: BLE001
        raise Repli(f"refusé (empreinte des dépendances impossible : {type(e).__name__})") from None
    if deps is None:
        return None, "-", cible
    if not (isinstance(deps, str) and MOTIF_DEPS.fullmatch(deps)):
        raise Repli("refusé (empreinte des dépendances invalide)")
    return cle, deps, cible


# --- la route --------------------------------------------------------------------------------------------------------

def _premiere_ligne(commande):
    distante = commande_conteneur(commande)
    if not distante or len(distante) > COMMANDE_MAX_ELEMENTS:
        raise Repli(f"refusé (commande de {len(distante)} éléments : 1 à {COMMANDE_MAX_ELEMENTS})")
    ligne = json.dumps(distante, ensure_ascii=False).encode("utf-8")
    if len(ligne) > COMMANDE_MAX_OCTETS:
        raise Repli(f"refusé (commande de plus de {COMMANDE_MAX_OCTETS} octets)")
    return ligne


def _famille_exclusion(racine):
    """« unity » dès que `ProjectSettings/ProjectVersion.txt` existe à la racine : `Library/`, `Temp/`, `obj/`, `Builds/`
    ne partent pas, même pour une commande d'une autre famille (projet mixte)."""
    return "unity" if os.path.isfile(os.path.join(racine, "ProjectSettings", "ProjectVersion.txt")) else None


def _instantane(instantane, racine, fichier, dire, famille=None):
    """Écrit l'archive dans `fichier` (fermé en sortant, même sur Ctrl-C) ; `famille` (« unity ») ajoute les exclusions de la famille ; `Repli` (R5) si elle ne peut pas partir."""
    plus = {"famille": famille} if famille else {}
    try:
        fichiers, ecartes = instantane.lister(racine, **plus)
        if ecartes:
            dire(f"Instantané : {len(ecartes)} fichier(s) écarté(s) : " + ", ".join(str(e) for e in ecartes[:10])
                 + (" …" if len(ecartes) > 10 else ""))
        executables = instantane.executables(racine)
        with open(fichier, "wb") as f:
            instantane.ecrire_tar(racine, fichiers, f, executables=executables, **plus)
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


def limites_de(profil, forces=None):
    """Les limites de la campagne : `cpus`, `memoire_mo`, `duree_s` du profil (`ressources_par_defaut`, § 5.14), relevées par
    `forces` (`tests.profil_force.ressources` du projet, écrit par le bureau seul) qui ne font que RELEVER (jamais sous le profil) ;
    une valeur absente ou invalide retombe sur `LIMITES`. Au-delà de `BORNES_LIMITES` : `Repli` (décision du Directeur requise), avant toute connexion."""
    limites = dict(LIMITES)
    profil_res = getattr(profil, "ressources", None)
    for source in (profil_res, forces):
        if isinstance(source, dict):
            for cle in limites:
                v = source.get(cle)
                if isinstance(v, int) and not isinstance(v, bool) and v > 0:
                    limites[cle] = v if source is profil_res else max(v, limites[cle])
    for cle, maximum in BORNES_LIMITES.items():
        if limites[cle] > maximum:
            raise Repli(f"refusé ({cle} {limites[cle]} au-delà de {maximum} : décision du Directeur requise)")
    return limites


def _limites_forcees_par_defaut(racine):
    """Les `tests.profil_force.ressources` enregistrés au bureau pour ce projet (le plus haut de chaque clé s'ils diffèrent) ;
    toute erreur : rien (les limites du profil)."""
    forces = {}
    try:
        try:
            from bureau import deport_types
        except ImportError:
            sys.path.append(str(ICI.parent))
            from bureau import deport_types
        for fichier in deport_types.reglages_enregistres(racine) or []:
            x = deport_types._lire_json_sur(fichier)
            tests = x.get("tests") if isinstance(x, dict) else None
            force = tests.get("profil_force") if isinstance(tests, dict) else None
            res = force.get("ressources") if isinstance(force, dict) else None
            for cle in LIMITES:
                v = res.get(cle) if isinstance(res, dict) else None
                if isinstance(v, int) and not isinstance(v, bool) and v > forces.get(cle, 0):
                    forces[cle] = v
    except Exception:  # noqa: BLE001 — jamais de limite relevée sur un doute
        return {}
    return forces


def budget_unites_de(serveur):
    """Le budget mémoire des tests du serveur, en jetons de 2 Go (4 à 20) : `budget_tests_mo` // 2 048, sinon le défaut (16)."""
    mo = serveur_modele.budget_tests_valide(getattr(serveur, "budget_tests_mo", None))
    return BUDGET_UNITES_DEFAUT if mo is None else mo // UNITE_MEMOIRE_MO


def places_de(serveur):
    """Campagnes simultanées voulues pour ce serveur : son réglage `places_tests` (1 à 4), sinon `PLACES_DEFAUT`."""
    voulues = getattr(serveur, "places_tests", None)
    if isinstance(voulues, bool) or not isinstance(voulues, int) or not 1 <= voulues <= PLACES_MAX:
        return PLACES_DEFAUT
    return voulues


def _au_serveur(commande, racine, attendre, places, dossier_etat, ssh, noter, horloge, maintenant, dire, choisir,
                instantane, projet_de, injoignable, attentes, sortie, sortie_erreur, nouvel_id, forcer, popen_base,
                dormir, travail_go=None, analyse=None, sdk_android=None, empreinte=None, reseau_code=None,
                ressources_forcees=None, executeur=None, licence=None, hotes_licence=None, reseau_licence=None):
    """La campagne au serveur ; rend son code, ou lève `Repli`. `KeyboardInterrupt` remonte telle quelle."""
    appel = horloge()
    suffixe = _arguments_executeur(executeur, licence, hotes_licence, reseau_licence, racine)   # avant tout (B3 : accord)
    profil = _profil_de_la_campagne(analyse or _analyse_par_defaut, racine, commande)
    limites = limites_de(profil, (ressources_forcees or _limites_forcees_par_defaut)(racine))
    image, famille, requises = _image_de_la_campagne(profil, sdk_android)
    if licence is not None and famille != "unity":
        raise Repli("refusé (licence Unity hors de la famille unity)")
    cle, deps, famille_deps = _deps_de_la_campagne(profil, famille, commande, racine, empreinte)
    reseau = "refuse"
    if cle is not None:
        import tests_profil
        if tests_profil.ECHAUFFEMENTS[cle]["execute_du_code"]:
            if not (reseau_code or _reseau_code_par_defaut)(racine):
                raise Repli("refusé (échauffement réseau non accordé : les dépendances exécutent du code du projet)")
            reseau = "accorde"
    try:
        serveur = choisir(dossier_etat, requises=requises)
    except serveur_tache.RefusLancement as e:
        raise Repli(f"indisponible ({e})") from None
    if not forcer and _injoignable_actif(injoignable, serveur.id, maintenant()):
        raise Repli("injoignable il y a moins de 5 minutes")
    try:
        serveur_etat.cible(serveur)
    except ValueError as e:
        raise Repli(f"mal déclaré ({e})") from None
    if famille == "gradle-android" and sdk_android is None:
        manque = tests_images._sdk_manquant(profil, sonder_sdk(serveur, ssh))
        if manque:
            raise Repli("indisponible (SDK Android du serveur incomplet : " + ", ".join(manque) + ")")
    if not MOTIF_DISTANT.fullmatch(ENVELOPPE_DISTANTE):
        raise Repli("refusé (chemin de l'enveloppe au serveur invalide)")
    trouve = projet_de(racine)
    projet = trouve[0] if trouve else None
    if not isinstance(projet, str) or not MOTIF_PROJET.fullmatch(projet):
        raise Repli("refusé (projet non enregistré au bureau)")
    poids = -(-limites["memoire_mo"] // UNITE_MEMOIRE_MO)
    if poids > budget_unites_de(serveur):
        raise Repli(f"refusé (la campagne demande {poids} jetons de mémoire, le budget du serveur en offre "
                    f"{budget_unites_de(serveur)})")
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
        _instantane(instantane, racine, archive, dire, _famille_exclusion(racine))
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

    distante = (f"\"{ENVELOPPE_DISTANTE}\" {ident} {places} {limites['cpus']} {limites['memoire_mo']} "
                f"{limites['duree_s']} {projet} {deps}")
    unites = budget_unites_de(serveur)
    plus = unites != BUDGET_UNITES_DEFAUT or bool(suffixe)   # le 14e (ou 15e+) force les 8e à 13e : sans eux, la ligne d'avant
    if travail_go is not None or image is not None or cle is not None or plus:
        distante += f" {int(travail_go) if travail_go is not None else 10}"   # 8e argument (facultatif) : taille maximale de travail/, en Go
    if image is not None or cle is not None or plus:
        # 9e et 10e (facultatifs) : image du catalogue et sa famille (celle des dépendances pour l'image par défaut)
        distante += f" {image or tests_images.IMAGE_DEFAUT} {famille or famille_deps or 'python'}"
    if cle is not None or plus:
        budget = getattr(serveur, "budget_caches_go", None)
        if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 1000:
            budget = BUDGET_CACHES_GO
        distante += f" {cle or '-'} {reseau} {budget}"     # 11e à 13e : échauffement, accord réseau (code du projet), budget Q5
    if plus:
        distante += f" {unites}"                           # 14e : budget de mémoire des tests, en jetons de 2 Go
    distante += suffixe                                    # 15e à 17e : exécuteur, licence Unity, hôtes de licence (B3)
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
        if refus == 79:
            raise Repli("en refus (échauffement des dépendances impossible au serveur, tests non lancés)")
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
             travail_go=None, analyse=None, sdk_android=None, empreinte=None, reseau_code=None,
             ressources_forcees=None, executeur=None, licence=None, hotes_licence=None, reseau_licence=None) -> int:
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
                           travail_go=travail_go, analyse=analyse, sdk_android=sdk_android, empreinte=empreinte,
                           reseau_code=reseau_code, ressources_forcees=ressources_forcees, executeur=executeur,
                           licence=licence, hotes_licence=hotes_licence, reseau_licence=reseau_licence)
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
