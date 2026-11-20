#!/usr/bin/env python3
"""Pont HÔTE d'un agent en mode pilote : socket Unix ~/taches/<id>/pont/pont.sock (montée dans le conteneur de l'agent sous
/pont), seule porte de l'agent vers l'émulateur. Lancé détaché par lancer_agent.sh (setsid + nohup, `python3 -I`, chef de
son groupe), arrêté par le veilleur de l'agent (SIGTERM au groupe) ; bibliothèque standard seulement.

Usage : python3 -I pont_hote.py <id_agent>

L'AGENT N'EST PAS DE CONFIANCE : il tient le client de la socket. Donc :
- une connexion = UNE requête, une ligne JSON de 4 Ko au plus {"verbe": str, "args": [str]} (exactement ces deux clés),
  traitée seule (une requête à la fois) ; réponse : une ligne JSON {"ok": bool, "verbe": str, "code": int, "detail": str} ;
- clé dupliquée, type faux, clé en plus, verbe hors liste, argument hors motif, JSON ou UTF-8 invalide : code 2 SANS RIEN
  EXÉCUTER ; la liste fermée et les motifs sont ceux de pont.sh et de serveur_tache.VERBES (décision R2 : un test fait passer
  les mêmes exemples par les trois) ;
- chaque verbe : ["sudo", "-n", "docker", "exec", "tache-<emu>", "/usr/local/bin/pont", verbe, *args], un tableau (aucun
  shell), avec l'environnement fixe ENV_FIXE (jamais celui de l'appelant ; docker exec sans -e), borné par DELAIS_VERBE_S ;
  le nom du conteneur est celui de l'émulation que CE pont a créée, jamais une valeur reçue ;
- 2000 appels au plus (les refus comptent) : au-delà, code 3 sans rien exécuter ;
- le pont hôte ne voit jamais le jeton de l'abonnement (il n'est ni lu, ni monté, ni transmis ici).

Émulation liée : au premier `demarrer` (ou si la précédente est finie ou arrêtée), une tâche d'émulation ~/taches/<emu>/ est
créée (identifiant MOTIF_ID ; entree/app.apk copié de ~/taches/<id>/entree/app.apk ; demande.json "type": "emulation" ;
agent = <id>), ~/taches/<id>/emulation (HÔTE SEUL, hors de tout montage : le veilleur de l'agent ne lit que lui) reçoit
<emu>, puis `bash lancer_emulation.sh <emu> pilote` est lancé dans sa propre session (créneau d'émulation : son verrou à
lui, distinct des places d'agent ; 75 = occupé -> code 4 « créneau d'émulation occupé, réessaie plus tard », la même tâche
est relancée au demarrer suivant), l'AVD attendu (sortie/.avd-pret), et seulement alors `demarrer` est relayé.
`arreter` : relayé au pont, puis « fin » écrit dans ~/taches/<emu>/arret. À la fin du pont (SIGTERM du veilleur, SIGINT,
SIGHUP, ou état final de la tâche d'agent constaté), l'émulation encore liée reçoit « fin » de même. Le veilleur de
l'émulation surveille aussi l'agent lié (état final ou pont hôte disparu : il s'arrête de lui-même).
Après `arreter` (ou une émulation finie), le `demarrer` suivant crée une NOUVELLE tâche d'émulation : un autre <emu>, donc
un autre conteneur tache-<emu> ; l'APK de la précédente est retiré. EMULATIONS_MAX (5) émulations par pont au plus
(au-delà : code 4 « limite d'émulations » ; une émulation compte dès son dossier créé, et un dossier à demi écrit est
retiré). Un lancement refusé pour de bon par lancer_emulation.sh (code 2, ou code 1 avec l'état « arretee » : agent lié fini
ou arrêt demandé) rend les `demarrer` suivants en échec immédiat (code 4), sans nouveau dossier ; un autre échec (code 1
« echouee » comme un docker run en échec, délai, code inattendu) arrête l'émulation (« fin ») et le `demarrer` suivant en
crée une neuve, dans la limite.

Retour des médias : après `capturer`, `journal`, `finfilm` (et `arreter` qui finit un film), la capture, logcat.txt, la vidéo
et ses images sont COPIÉS de ~/taches/<emu>/sortie (écrit par le conteneur d'émulation, que l'agent ne peut pas toucher) vers
~/taches/<id>/outil (monté en lecture seule sous /outil ; dossier de l'hôte seul) : noms revalidés par les motifs de la
tranche A, chaque composant ouvert sans suivre de lien (O_NOFOLLOW, par descripteur de dossier), fichiers ORDINAIRES à un
seul lien seulement, bornés en taille apparente (MEDIA_MAX_OCTETS par fichier, OUTIL_MAX_OCTETS en tout), écrits dans un
temporaire O_CREAT | O_EXCL | O_NOFOLLOW puis renommés. `detail` donne le chemin /outil/... .

Socket : dossier pont/ (créé 0700 par lancer_agent.sh, vérifié ici : vrai dossier, à nous), socket 0600 (umask au bind),
propriétaire l'utilisateur de l'hôte, le même uid que le conteneur (--user) ; un pair d'un autre uid (SO_PEERCRED) est
refusé. Journal : ~/taches/<id>/pont-hote.log (hôte seul ; pont/ est inscriptible par l'agent), une ligne par appel : heure,
verbe et arguments VALIDÉS seulement (rien du texte d'une requête refusée), code, durée."""
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time

# ==============================================================================================================
# MOTIFS DU PONT : copie EXACTE de la table de serveur_ovh/taches/pont.sh et de outils/serveur_tache.py (décision R2 ;
# test_motifs_pont_sh_python_et_pont_hote_s_accordent). Toujours re.fullmatch avec re.ASCII.
MOTIF_ENTIER = r"[0-9]{1,4}"                              # coordonnée : 0 à 9999
MOTIF_DUREE = r"([0-9]{1,2}|1[01][0-9]|120)"               # attendre : 0 à 120 secondes
MOTIF_NOM = r"[a-z0-9][a-z0-9_-]{0,39}"                   # nom de capture
MOTIF_TEXTE = r"[A-Za-z0-9][A-Za-z0-9 .,_-]{0,59}"        # texte saisi
MOTIF_FILTRE = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,59}"        # filtre du journal
MOTIF_TOUCHE = r"(retour|accueil|menu)"
MOTIF_NOM_RESERVE = r"(con|prn|aux|nul|com[0-9]|lpt[0-9])"
MOTIF_SECONDES_FILM = r"([1-9][0-9]?|1[0-7][0-9]|180)"    # filmer : 1 à 180 secondes
VERBES = {
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
}
FACULTATIFS = {"journal": 1, "filmer": 1}
# Délais (s) de chaque verbe relayé : ceux de serveur_tache.DELAIS_VERBE_S (test de concordance).
DELAIS_VERBE_S = {"demarrer": 360, "installer": 240, "arreter": 480, "attendre": 150,
                  "capturer": 150, "filmer": 60, "finfilm": 420}
DELAI_VERBE_S = 90
# ==============================================================================================================
MOTIF_ID = r"t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}"
MOTIF_CAPTURE = r"captures/([a-z0-9][a-z0-9_-]{0,39})\.png"
MOTIF_VIDEO = r"videos/([a-z0-9][a-z0-9_-]{0,39})\.mp4"
MOTIF_DETAIL_FILM = r"videos/([a-z0-9][a-z0-9_-]{0,39})\.mp4 \("    # réponse de finfilm (et d'arreter qui finit un film)

ENV_FIXE = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}   # tout l'environnement des commandes lancées
REQUETE_MAX = 4096
APPELS_MAX = 2000
LECTURE_S = 10                    # une requête doit arriver en entier dans ce délai (sinon : refusée, code 2)
ECRITURE_S = 10
REPONSE_PONT_MAX = 256 * 1024     # détail rendu à l'agent (journal : 200 lignes de 500 caractères au plus)
SORTIE_MAX_OCTETS = 512 * 1024    # sortie standard de docker exec gardée au plus (le reste est lu et jeté)
REPONSE_OCTETS_MAX = 768 * 1024   # ligne de réponse, échappement JSON compris (le client en lit 1 Mo au plus)
GRACE_ARRET_S = 5                 # entre SIGTERM et SIGKILL d'une commande au délai dépassé
EMULATIONS_MAX = 5                # tâches d'émulation créées par un même pont
LANCEMENT_EMULATION_S = 240       # lancer_emulation.sh : docker run borné à 120 s, plus la marge
AVD_ATTENTE_S = 300
AVD_PAS_S = 2
APK_MAX_OCTETS = 200 * 1024 * 1024
MEDIA_MAX_OCTETS = 64 * 1024 * 1024       # chaque fichier copié dans outil/ (vidéo : 60 Mo au plus côté pont)
OUTIL_MAX_OCTETS = 160 * 1024 * 1024      # outil/ en tout (médias 100 Mo + logcat 2 Mo + marge)
IMAGES_MAX = 30
FINAUX = ("terminee", "arretee", "echouee")
CODE_OCCUPE = 75
MESSAGE_OCCUPE = "créneau d'émulation occupé, réessaie plus tard"
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)          # absent sous Windows seulement (tests) ; exigé par main()
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
O_BINARY = getattr(os, "O_BINARY", 0)
PAR_DESCRIPTEUR = os.open in os.supports_dir_fd and os.listdir in os.supports_fd and bool(O_NOFOLLOW)


class Refus(Exception):
    """Requête refusée ou verbe en échec : `code` et `detail` (français, jamais le texte reçu)."""

    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


class Fin(BaseException):
    """Signal de fin (SIGTERM du veilleur, SIGINT, SIGHUP)."""


def _maintenant_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- validation

def valider_verbe(verbe, args):
    """Arguments validés (tuple de textes) ; `Refus(2, ...)` sinon. Mêmes règles que pont.sh et serveur_tache.valider_verbe,
    sans entier Python : la requête ne porte que des textes."""
    if not isinstance(verbe, str) or verbe not in VERBES:
        raise Refus(2, "Verbe inconnu : liste fermée (" + ", ".join(VERBES) + ").")
    if not isinstance(args, (list, tuple)):
        raise Refus(2, f"Arguments de {verbe} : une liste est attendue.")
    motifs = VERBES[verbe]
    if not len(motifs) - FACULTATIFS.get(verbe, 0) <= len(args) <= len(motifs):
        raise Refus(2, f"Nombre d'arguments refusé pour {verbe}.")
    for i, (a, motif) in enumerate(zip(args, motifs), 1):
        if not isinstance(a, str) or not re.fullmatch(motif, a, re.ASCII):
            raise Refus(2, f"Argument {i} refusé pour {verbe} (forme non permise).")
        if motif == MOTIF_NOM and re.fullmatch(MOTIF_NOM_RESERVE, a, re.ASCII):
            raise Refus(2, f"Argument {i} refusé pour {verbe} (nom réservé sous Windows).")
    return tuple(args)


def _sans_doublon(paires):
    vues = {}
    for cle, valeur in paires:
        if cle in vues:
            raise Refus(2, "Requête refusée : clé en double.")
        vues[cle] = valeur
    return vues


def lire_requete(ligne):
    """(verbe, args) validés d'une ligne de requête (octets, sans le retour à la ligne final) ; `Refus(2, ...)` sinon."""
    if not isinstance(ligne, (bytes, bytearray)) or len(ligne) > REQUETE_MAX:
        raise Refus(2, f"Requête refusée : une ligne de {REQUETE_MAX} octets au plus.")
    try:
        texte = bytes(ligne).decode("utf-8")
        objet = json.loads(texte, object_pairs_hook=_sans_doublon)
    except Refus:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refus(2, "Requête refusée : une ligne JSON {\"verbe\": ..., \"args\": [...]} est attendue.") from None
    if not isinstance(objet, dict) or set(objet) != {"verbe", "args"}:
        raise Refus(2, "Requête refusée : exactement les clés verbe et args.")
    if not isinstance(objet["args"], list) or not all(isinstance(a, str) for a in objet["args"]):
        raise Refus(2, "Requête refusée : args doit être une liste de textes.")
    return objet["verbe"], valider_verbe(objet["verbe"], objet["args"])


def reponse(code, verbe, detail, ajout=""):
    """La ligne de réponse, bornée en OCTETS après l'échappement JSON (REPONSE_OCTETS_MAX) : seul `detail` est raccourci,
    `ajout` (chemin /outil/... du pont hôte, court) est toujours gardé en fin. Un caractère inencodable (demi-paire UTF-16
    venue du pont) devient « ? »."""
    while True:
        ligne = (json.dumps({"ok": code == 0, "verbe": verbe, "code": code, "detail": detail + ajout}, ensure_ascii=False)
                 + "\n").encode("utf-8", "replace")
        if len(ligne) <= REPONSE_OCTETS_MAX or not detail:
            return ligne
        detail = detail[:len(detail) * 3 // 4]


# ---------------------------------------------------------------- exécution (tableau, sans shell)

def executer(argv, delai, env, nouvelle_session=False):
    """(code, sortie standard) d'une commande en TABLEAU, sans shell, avec l'environnement `env` et rien d'autre ; code None
    si le délai est dépassé. Une commande de la même session est tuée au délai ou à la fin du pont ; une commande dans sa
    propre session (lancer_emulation.sh) est laissée finir seule (la tuer à demi laisserait un conteneur sans veilleur).
    Arrêt : SIGTERM, GRACE_ARRET_S secondes, puis SIGKILL, et toujours wait(). La sortie standard est lue au fil de l'eau
    par un fil : SORTIE_MAX_OCTETS gardés au plus, le reste lu et jeté (jamais un tube plein qui bloquerait la commande)."""
    p = subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         env=dict(env), close_fds=True, start_new_session=nouvelle_session)
    gardes = []

    def lire():
        taille = 0
        try:
            while True:
                m = p.stdout.read1(65536)
                if not m:
                    break
                if taille < SORTIE_MAX_OCTETS:
                    m = m[:SORTIE_MAX_OCTETS - taille]
                    gardes.append(m)
                    taille += len(m)
        except (OSError, ValueError):
            pass

    fil = threading.Thread(target=lire, daemon=True)
    fil.start()

    def arreter():
        p.terminate()
        try:
            p.wait(timeout=GRACE_ARRET_S)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()

    try:
        p.wait(timeout=delai)
    except subprocess.TimeoutExpired:
        if not nouvelle_session:
            arreter()
        return None, b""
    except BaseException:
        if not nouvelle_session:
            arreter()
        raise
    fil.join(timeout=GRACE_ARRET_S)
    return p.returncode, b"".join(gardes)


# ---------------------------------------------------------------- fichiers sûrs

def _ecrire_atomique(chemin, donnees, mode=0o600):
    """Écrit `donnees` dans `chemin` (dossier de l'HÔTE seul) : temporaire O_EXCL sans suivre de lien, puis renommage."""
    dossier, nom = os.path.split(chemin)
    tmp = os.path.join(dossier, f".{nom}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_BINARY, mode)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)               # lancer_agent.sh lance le pont sous umask 077 : le mode voulu, exactement
        with os.fdopen(fd, "wb") as f:
            f.write(donnees)
        os.replace(tmp, chemin)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ouvrir_sous(racine, rel, dossier=False):
    """Descripteur de `racine/rel` ouvert SANS suivre aucun lien, à aucun niveau (Linux : chaque composant par
    descripteur de dossier, O_NOFOLLOW). Sous Windows (tests seulement), chaque composant est vérifié par lstat."""
    parties = rel.split("/") if rel else []
    if any(p in ("", ".", "..") for p in parties):
        raise OSError("chemin refusé")
    if PAR_DESCRIPTEUR:
        fd = os.open(racine, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
        try:
            for i, p in enumerate(parties):
                dernier = i == len(parties) - 1
                drapeaux = os.O_RDONLY | O_NOFOLLOW | (O_DIRECTORY if (dossier or not dernier) else O_NONBLOCK)
                suivant = os.open(p, drapeaux, dir_fd=fd)
                os.close(fd)
                fd = suivant
            return fd
        except BaseException:
            os.close(fd)
            raise
    chemin = racine
    for p in [None] + parties:
        if p is not None:
            chemin = os.path.join(chemin, p)
        if stat.S_ISLNK(os.lstat(chemin).st_mode):
            raise OSError("lien symbolique refusé")
    if dossier:
        if not stat.S_ISDIR(os.lstat(chemin).st_mode):
            raise OSError("pas un dossier")
        return chemin                       # Windows : pas de descripteur de dossier ; le chemin vérifié
    return os.open(chemin, os.O_RDONLY | O_BINARY)


def _lister_sous(racine, rel):
    d = _ouvrir_sous(racine, rel, dossier=True)
    if isinstance(d, str):
        return os.listdir(d)
    try:
        return os.listdir(d)
    finally:
        os.close(d)


def _lire_ordinaire(racine, rel, plafond):
    """Octets d'un fichier ORDINAIRE à un seul lien, jamais par un lien, de taille apparente <= plafond ; None sinon."""
    try:
        fd = _ouvrir_sous(racine, rel)
    except OSError:
        return None
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_size > plafond:
            return None
        morceaux, total = [], 0
        while True:
            m = os.read(fd, min(1 << 20, plafond + 1 - total))
            if not m:
                break
            morceaux.append(m)
            total += len(m)
            if total > plafond:
                return None
        return b"".join(morceaux)
    finally:
        os.close(fd)


# ---------------------------------------------------------------- contexte du pont

class Contexte:
    """État d'un pont hôte : tâche d'agent `ident` sous `home`/taches, scripts dans `ici` ; `executer(argv, delai, env,
    nouvelle_session)` -> (code, sortie) et `dormir(s)` remplaçables (tests)."""

    def __init__(self, ident, home, ici, executer=None, dormir=time.sleep):
        if not isinstance(ident, str) or not re.fullmatch(MOTIF_ID, ident, re.ASCII):
            raise ValueError("identifiant refusé")
        self.id = ident
        self.home = str(home)
        self.ici = str(ici)
        self.taches = os.path.join(self.home, "taches")
        self.dossier = os.path.join(self.taches, ident)
        self.outil = os.path.join(self.dossier, "outil")
        self.executer = executer or globals()["executer"]
        self.dormir = dormir
        self.appels = 0
        self.emu = None              # tâche d'émulation créée par CE pont
        self.emu_arretee = False
        self.emulations = 0          # tâches d'émulation créées (EMULATIONS_MAX au plus)
        self.echec_lancement = None  # refus définitif de lancer_emulation.sh (2, ou 1 « arretee ») : plus de nouvel essai

    # --- journal (hôte seul)
    def noter(self, texte, debut):
        ligne = f"{_maintenant_iso()} {texte} {int((time.monotonic() - debut) * 1000)}ms\n"
        try:
            fd = os.open(os.path.join(self.dossier, "pont-hote.log"),
                         os.O_WRONLY | os.O_APPEND | os.O_CREAT | O_NOFOLLOW | O_BINARY, 0o600)
            with os.fdopen(fd, "ab") as f:
                f.write(ligne.encode("utf-8"))
        except OSError:
            pass

    # --- émulation liée
    def _dossier_emu(self, emu=None):
        return os.path.join(self.taches, emu or self.emu)

    def etat_emu(self):
        """(etat, raison) de etat.json de l'émulation liée (écrit par son enveloppe, sur l'hôte), (None, "") sinon."""
        donnees = _lire_ordinaire(self._dossier_emu(), "etat.json", 4096)
        try:
            e = json.loads(donnees.decode("utf-8"))
            return (e.get("etat") if isinstance(e.get("etat"), str) else None,
                    e.get("raison") if isinstance(e.get("raison"), str) else "")
        except (AttributeError, ValueError):
            return None, ""

    def _nouvelle_emulation(self):
        if self.emulations >= EMULATIONS_MAX:
            raise Refus(4, f"Limite d'émulations atteinte ({EMULATIONS_MAX} pour cette tâche) : plus de nouvelle émulation.")
        apk = _lire_ordinaire(os.path.join(self.dossier, "entree"), "app.apk", APK_MAX_OCTETS)
        if not apk:
            raise Refus(4, "APK de l'agent absent ou invalide (entree/app.apk) : émulation impossible.")
        if self.emu:                 # la précédente (finie ou arrêtée) n'a plus besoin de son APK : disque rendu
            try:
                os.unlink(os.path.join(self._dossier_emu(), "entree", "app.apk"))
            except OSError:
                pass
        for _ in range(5):
            emu = time.strftime("t%Y%m%d-%H%M%S-", time.gmtime()) + secrets.token_hex(2)
            if emu == self.id:
                continue
            try:
                os.mkdir(self._dossier_emu(emu), 0o700)
                break
            except FileExistsError:
                continue
        else:
            raise Refus(4, "Identifiant d'émulation introuvable (déjà pris).")
        self.emulations += 1         # compté dès le dossier créé : un échec plus loin entame aussi la limite
        d = self._dossier_emu(emu)
        try:
            os.mkdir(os.path.join(d, "entree"), 0o755)
            os.chmod(os.path.join(d, "entree"), 0o755)
            _ecrire_atomique(os.path.join(d, "entree", "app.apk"), apk, 0o644)   # lu par l'utilisateur 1000 du conteneur
            demande = {"id": emu, "type": "emulation", "mode": "pilote", "agent": self.id}
            _ecrire_atomique(os.path.join(d, "demande.json"), (json.dumps(demande, indent=2) + "\n").encode("ascii"))
            _ecrire_atomique(os.path.join(d, "agent"), (self.id + "\n").encode("ascii"))
            # Lien de l'agent vers son émulation : HÔTE SEUL (jamais sous pont/, inscriptible par l'agent), écrit AVANT le
            # lancement : un veilleur qui arrête l'agent pendant le lancement arrête aussi cette émulation.
            _ecrire_atomique(os.path.join(self.dossier, "emulation"), (emu + "\n").encode("ascii"))
        except OSError:              # dossier à demi écrit : retiré (rien n'a été lancé dessus)
            shutil.rmtree(d, ignore_errors=True)
            raise Refus(4, "Préparation de l'émulation impossible (écriture sur le disque du serveur en échec).") from None
        self.emu, self.emu_arretee = emu, False

    def preparer_emulation(self):
        """Émulation liée en marche et AVD prêt ; `Refus(4, ...)` sinon (créneau occupé, échec, délai)."""
        if self.echec_lancement:
            raise Refus(4, self.echec_lancement)
        if self.emu and not self.emu_arretee:
            etat, _r = self.etat_emu()
            if etat in FINAUX:
                self.emu_arretee = True
        if not self.emu or self.emu_arretee:
            self._nouvelle_emulation()
        etat, raison = self.etat_emu()
        if etat != "en_cours":
            env = dict(ENV_FIXE, HOME=self.home)
            code, sortie = self.executer(["bash", os.path.join(self.ici, "lancer_emulation.sh"), self.emu, "pilote"],
                                         LANCEMENT_EMULATION_S, env, nouvelle_session=True)
            if code == CODE_OCCUPE:
                raise Refus(4, MESSAGE_OCCUPE)
            if code not in (0, 3):
                etat, raison = self.etat_emu()
                message = f"Démarrage de l'émulation impossible (code {code}) : {raison[:300] or 'voir etat.json'}"
                self.arreter_emulation()       # « fin » : jamais une émulation à demi lancée laissée sans suite
                # Refus définitifs : argument refusé (2), ou émulation liée refusée parce que l'agent est fini ou son arrêt
                # demandé (1 avec l'état « arretee »). Un autre code 1 (docker run en échec, créneau inaccessible : état
                # « echouee ») peut être passager : le demarrer suivant en crée une neuve, dans la limite EMULATIONS_MAX.
                if code == 2 or (code == 1 and etat == "arretee"):
                    self.echec_lancement = message + " (inutile de réessayer pendant cette tâche)"
                raise Refus(4, message)
        debut = time.monotonic()
        while True:
            if os.path.lexists(os.path.join(self._dossier_emu(), "sortie", ".avd-pret")):
                return
            etat, raison = self.etat_emu()
            if etat in FINAUX:
                self.emu_arretee = True
                raise Refus(4, f"L'émulation s'est arrêtée avant d'être prête : {raison[:300]}")
            if time.monotonic() - debut >= AVD_ATTENTE_S:
                raise Refus(4, f"L'AVD de l'émulation n'est pas prêt en {AVD_ATTENTE_S} s.")
            self.dormir(AVD_PAS_S)

    def arreter_emulation(self):
        """« fin » dans ~/taches/<emu>/arret (son veilleur arrête le conteneur et libère le créneau d'émulation)."""
        if self.emu and not self.emu_arretee:
            try:
                _ecrire_atomique(os.path.join(self._dossier_emu(), "arret"), b"fin\n")
            except OSError:
                pass
            self.emu_arretee = True

    def fin(self):
        self.arreter_emulation()

    def tache_finie(self):
        donnees = _lire_ordinaire(self.dossier, "etat.json", 4096)
        try:
            return json.loads(donnees.decode("utf-8")).get("etat") in FINAUX
        except (AttributeError, ValueError):
            return False

    # --- relais d'un verbe
    def relayer(self, verbe, args):
        argv = ["sudo", "-n", "docker", "exec", f"tache-{self.emu}", "/usr/local/bin/pont", verbe, *args]
        code, sortie = self.executer(argv, DELAIS_VERBE_S.get(verbe, DELAI_VERBE_S), dict(ENV_FIXE))
        detail = None
        lignes = [x for x in (sortie or b"")[:REPONSE_PONT_MAX * 2].decode("utf-8", "replace").splitlines() if x.strip()]
        if lignes:
            try:
                d = json.loads(lignes[-1])
                if isinstance(d, dict) and isinstance(d.get("detail"), str):
                    detail = d["detail"][:REPONSE_PONT_MAX]
            except ValueError:
                pass
        if code is None:
            return 4, f"Délai dépassé pour {verbe} ({DELAIS_VERBE_S.get(verbe, DELAI_VERBE_S)} s)."
        if code not in (0, 2, 3, 4) or detail is None:
            return 4, (f"Émulation injoignable (docker exec, code {code}) : elle s'est peut-être arrêtée ; "
                       "demarrer en relance une.")
        return code, detail

    # --- médias
    def _taille_outil(self):
        total = 0
        for racine, _dossiers, fichiers in os.walk(self.outil):
            for f in fichiers:
                try:
                    total += os.lstat(os.path.join(racine, f)).st_size
                except OSError:
                    pass
        return total

    def copier(self, rel):
        """Copie sortie/<rel> de l'émulation vers outil/<rel> ; le chemin /outil/<rel>, ou None (refusé ou impossible)."""
        if not (re.fullmatch(MOTIF_CAPTURE, rel, re.ASCII) or re.fullmatch(MOTIF_VIDEO, rel, re.ASCII)
                or re.fullmatch(r"videos/([a-z0-9][a-z0-9_-]{0,39})-img/\1-[0-9]{3}\.png", rel, re.ASCII)
                or rel == "logcat.txt"):
            return None
        donnees = _lire_ordinaire(os.path.join(self._dossier_emu(), "sortie"), rel, MEDIA_MAX_OCTETS)
        if donnees is None:
            return None
        cible = os.path.join(self.outil, *rel.split("/"))
        try:
            ancien = os.lstat(cible).st_size if os.path.lexists(cible) else 0
            if self._taille_outil() - ancien + len(donnees) > OUTIL_MAX_OCTETS:
                return None
            dossier = os.path.dirname(cible)
            os.makedirs(dossier, mode=0o700, exist_ok=True)
            if os.path.islink(dossier) or os.path.islink(self.outil):
                return None
            _ecrire_atomique(cible, donnees)
        except OSError:
            return None
        return "/outil/" + rel

    def copier_film(self, nom):
        """La vidéo et ses images ; texte à ajouter au détail."""
        video = self.copier(f"videos/{nom}.mp4")
        if not video:
            return f" Vidéo non copiée dans /outil (refusée ou au-delà des limites)."
        n = 0
        try:
            noms = sorted(_lister_sous(os.path.join(self._dossier_emu(), "sortie"), f"videos/{nom}-img"))
        except OSError:
            noms = []
        for f in noms:
            if n >= IMAGES_MAX:
                break
            if re.fullmatch(re.escape(nom) + r"-[0-9]{3}\.png", f, re.ASCII) and self.copier(f"videos/{nom}-img/{f}"):
                n += 1
        return f" Copie : {video} et /outil/videos/{nom}-img/ ({n} images)."

    def apres(self, verbe, args, code, detail):
        """Copie des médias produits par un verbe réussi ; le texte à ajouter au détail (chemin /outil/...), gardé à part :
        `reponse` ne raccourcit jamais cet ajout, seulement le détail du pont."""
        if verbe == "capturer" and code == 0:
            chemin = self.copier(f"captures/{args[0]}.png")
            return f" Copie : {chemin}." if chemin else " Capture non copiée dans /outil (refusée ou au-delà des limites)."
        if verbe == "journal" and code == 0:
            chemin = self.copier("logcat.txt")
            return f"\n(copie : {chemin})" if chemin else "\n(logcat.txt non copié dans /outil)"
        if verbe in ("finfilm", "arreter"):
            m = re.search(MOTIF_DETAIL_FILM, detail, re.ASCII)
            if m and (verbe == "arreter" or m.start() == 0):
                return self.copier_film(m.group(1))
        return ""

    def executer_verbe(self, verbe, args):
        """(code, détail du pont, ajout du pont hôte)."""
        if verbe == "demarrer":
            self.preparer_emulation()
        elif not self.emu or self.emu_arretee:
            raise Refus(4, "Aucune émulation en cours : demarrer d'abord.")
        code, detail = self.relayer(verbe, args)
        if verbe == "arreter":
            self.arreter_emulation()
        return code, detail, self.apres(verbe, args, code, detail)


def traiter_requete(ligne, ctx):
    """La ligne de réponse (octets) à UNE ligne de requête ; rien n'est exécuté si la requête est refusée."""
    debut = time.monotonic()
    ctx.appels += 1
    if ctx.appels > APPELS_MAX:
        ctx.noter("limite code=3", debut)
        return reponse(3, "", f"Limite d'appels du pont atteinte ({APPELS_MAX}).")
    try:
        verbe, args = lire_requete(ligne)
    except Refus as r:
        ctx.noter(f"refus code={r.code}", debut)
        return reponse(r.code, "", r.detail)
    ajout = ""
    try:
        code, detail, ajout = ctx.executer_verbe(verbe, args)
    except Refus as r:
        code, detail = r.code, r.detail
    except Exception as e:           # une réponse inattendue ne fait jamais mourir le pont (Fin, elle, passe)
        code, detail = 4, f"Erreur du pont hôte ({type(e).__name__})."
    ctx.noter(" ".join((verbe, *args, f"code={code}")), debut)       # arguments validés seulement
    try:
        return reponse(code, verbe, detail, ajout)
    except Exception as e:           # même une réponse inencodable ne fait jamais mourir le pont
        return reponse(4, verbe, f"Erreur du pont hôte ({type(e).__name__}).")


# ---------------------------------------------------------------- socket

def _lire_ligne(conn, horloge=time.monotonic):
    """La ligne de requête, lue avant une échéance GLOBALE de LECTURE_S secondes (un client qui envoie goutte à goutte
    n'obtient pas plus) ; ce qui est arrivé à l'échéance est jugé tel quel (incomplet : refusé)."""
    echeance = horloge() + LECTURE_S
    donnees = b""
    try:
        while b"\n" not in donnees and len(donnees) <= REQUETE_MAX:
            reste = echeance - horloge()
            if reste <= 0:
                break
            conn.settimeout(reste)
            morceau = conn.recv(REQUETE_MAX + 2 - len(donnees))     # au plus la ligne, son \n, et un octet de trop
            if not morceau:
                break
            donnees += morceau
    except OSError:
        pass
    if b"\n" in donnees:
        return donnees.split(b"\n", 1)[0]
    return donnees if len(donnees) <= REQUETE_MAX else donnees[:REQUETE_MAX + 1]


def _pair_admis(conn):
    so_peercred = getattr(socket, "SO_PEERCRED", None)
    if so_peercred is None:
        return True
    try:
        _pid, uid, _gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, so_peercred, struct.calcsize("3i")))
    except OSError:
        return False
    return uid == os.getuid()


def servir(ctx, continuer=None, attente_s=30):
    """Boucle de la socket : une connexion, une requête, une réponse, à la suite. Rend la main quand `continuer()` est faux
    ou que la tâche d'agent est finie (sondée toutes les `attente_s` secondes sans connexion)."""
    pont = os.path.join(ctx.dossier, "pont")
    s = os.lstat(pont)
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid():
        raise OSError("dossier pont/ invalide (lien, ou pas à nous)")
    os.chmod(pont, 0o700)
    chemin = os.path.join(pont, "pont.sock")
    if os.path.lexists(chemin) and not stat.S_ISDIR(os.lstat(chemin).st_mode):
        os.unlink(chemin)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    ancien = os.umask(0o177)                     # socket 0600 dès sa création (jamais de chmod à travers un lien)
    try:
        srv.bind(chemin)
    finally:
        os.umask(ancien)
    try:
        srv.listen(4)
        srv.settimeout(attente_s)
        while continuer is None or continuer():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                if ctx.tache_finie():
                    return
                continue
            with conn:
                if not _pair_admis(conn):
                    continue
                r = traiter_requete(_lire_ligne(conn), ctx)
                try:
                    conn.settimeout(ECRITURE_S)
                    conn.sendall(r)
                except OSError:
                    pass
    finally:
        srv.close()
        try:
            os.unlink(chemin)
        except OSError:
            pass


def _signal(_numero, _cadre):
    raise Fin()


def main(argv):
    if len(argv) != 2 or not re.fullmatch(MOTIF_ID, argv[1], re.ASCII):
        print("pont_hote : usage : pont_hote.py <id_agent>", file=sys.stderr)
        return 2
    if not hasattr(socket, "AF_UNIX") or not O_NOFOLLOW or not PAR_DESCRIPTEUR:
        print("pont_hote : système sans socket Unix ni O_NOFOLLOW : refusé.", file=sys.stderr)
        return 2
    home = os.environ.get("HOME", "")
    if not home.startswith("/"):
        print("pont_hote : HOME absent.", file=sys.stderr)
        return 2
    ctx = Contexte(argv[1], home, os.path.dirname(os.path.abspath(__file__)))
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, _signal)
    try:
        servir(ctx)
    except Fin:
        pass
    except OSError as e:
        print(f"pont_hote : {type(e).__name__} : {e}", file=sys.stderr)
        return 1
    finally:
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):    # la fin n'est jamais interrompue à demi
            signal.signal(s, signal.SIG_IGN)
        ctx.fin()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
