"""Agents sur le serveur (tranche B) : demande d'agent validée, paquet Git à l'aller (`git bundle`), lancement de
`serveur_ovh/taches/lancer_agent.sh`, rapatriement du flux, de `fin.json` et du paquet résultat.

Aucune écriture sur GitHub depuis le serveur : l'aller est un paquet Git envoyé par SSH, le retour un paquet rapatrié en
octets. Tout ce que le serveur renvoie (fin.json, flux, paquet) est une DONNÉE NON FIABLE : `fin.json` est revalidé champ par
champ, le paquet est analysé (en-tête relu ici, puis `git bundle verify` et `list-heads`) et seule la référence
`refs/heads/agent/<tâche>` est acceptée, sans jamais exécuter ce que contient un dépôt du serveur. Sections : demande ;
paquets Git ; scripts distants ; lancer ; récupérer ; index.
"""
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import plateforme_acces
import plateforme_ssh
import serveur_capacites
import serveur_etat
import serveur_tache as st
from plateforme import DOSSIER_DISTANT, RACINE_SERVEUR

# ---------------------------------------------------------------- demande

LIMITES_AGENT = {"duree_s": 2400, "tours": 200, "memoire_mo": 4096, "cpus": 2, "paquet_octets": 524288000,
                 "flux_octets": 20971520}
# Projet Flutter : un build APK (démons Gradle et Kotlin, gen_snapshot, flutter) dépasse 4 Go (essai réel : démon Gradle
# tué par le cgroup) : 12 Go et 4 processeurs par défaut et au plus ; les autres projets gardent LIMITES_AGENT.
LIMITES_AGENT_FLUTTER = {**LIMITES_AGENT, "memoire_mo": 12288, "cpus": 4}
MODES_AGENT = ("seul", "pilote")
PLACES_DEFAUT = 2
CLES_DEMANDE_AGENT = frozenset({"id", "projet", "tache", "mode", "modele", "branche", "base", "limites", "reprend", "places",
                                "genre", "flutter", "flutter_dossier", "signature"})
# Signature des APK (tâche 15e, réglage `signature_apk` du projet) : `debug_serveur` monte la clé de debug du serveur en lecture seule
# dans le conteneur de l'agent ; `aucune` et `poste_signe` ne montent aucune clé (la clé de release reste au poste).
SIGNATURES = ("aucune", "debug_serveur", "poste_signe")
# `tache` : l'agent de la tâche ; `reponse` : sa réponse aux questions de l'utilisateur (même tâche, jamais confondues)
GENRES_AGENT = ("tache", "reponse")
# Mêmes motifs que serveur_ovh/images/agent/entree-agent.py (qui les revérifie sur le serveur).
MOTIF_TACHE = re.compile(r"[A-Za-z0-9_.-]{1,60}", re.ASCII)
MOTIF_BRANCHE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}", re.ASCII)
MOTIF_BASE = re.compile(r"[0-9a-f]{40}", re.ASCII)
# le dossier Flutter du projet (`projet_flutter.dossier_flutter`) : « . » ou un sous-dossier direct, jamais « .. » (relu par
# lancer_agent.sh et par les commandes uniques de l'agent avec le même motif)
MOTIF_DOSSIER_FLUTTER = re.compile(r"\.|[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}", re.ASCII)
MOTIF_MODELE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\[\]-]{0,59}", re.ASCII)
ENTETE_MAX = 65536                 # en-tête d'un paquet Git : lu sur 64 Ko au plus
FIN_MAX_OCTETS = 65536
DELAI_GIT_S = 300


@dataclass(frozen=True)
class DemandeAgent:
    id: str
    projet: str
    tache: str
    mode: str
    modele: object
    branche: str
    base: str
    limites: object          # MappingProxyType : immuable
    reprend: object
    places: int
    genre: str = "tache"
    # projet Flutter (vu sur le poste, `projet_flutter`) : le serveur doit avoir flutter-sdk, monté en lecture seule
    flutter: bool = False
    flutter_dossier: object = None     # le sous-dossier Flutter du projet (« . » pour la racine), ou None
    signature: str = "aucune"


class RefusRecuperation(ValueError):
    """Ce que le serveur a renvoyé est refusé (fin.json ou paquet suspect, branche locale divergente) : message français.
    `transitoire` : True si le refus peut venir d'une panne passagère (transfert coupé, dépôt verrouillé) et mérite un
    nouvel essai ; False (défaut) si le refus est définitif (paquet ou fin.json suspects, branche extraite)."""

    def __init__(self, message, transitoire=False):
        super().__init__(message)
        self.transitoire = transitoire is True


_COMMANDE_GIT = ["git"]            # remplaçable par les tests (faux git qui inonde stderr ou ne finit jamais)
ERREUR_MAX = 65536                 # texte d'erreur gardé de git (le reste est jeté)
BLOC = 1 << 20


def _tuer_arbre(p):
    """Tue git ET ses descendants (pack-objects, ssh, filtres…) qui tiendraient sa sortie ouverte. POSIX : le groupe de
    processus (git démarré dans sa propre session). Windows : `taskkill /T` (l'arbre tant que git vit encore)."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(p.pid, 9)
        except OSError:
            pass
    try:
        p.kill()
    except OSError:
        pass


def _git(projet, args, max_octets=None, vers=None):
    """(code, sortie octets, erreur texte) d'un appel `git` en tableau d'arguments (aucun shell), dans `projet`.

    Ne se fige jamais, même quand un petit-enfant de git garde la sortie ouverte : sortie et erreur sont lues par deux fils,
    le fil appelant n'attend que jusqu'à l'échéance (`DELAI_GIT_S`, mesurée sur l'horloge monotone, sans minuterie qui
    pourrait se déclencher après une fin normale) ; échéance passée, l'arbre de processus est tué : code 124 (un fil de
    lecture resté bloqué sur un petit-enfant orphelin est abandonné, il finit avec lui). Sortie plus grande que `max_octets` :
    même arrêt, code 99. L'erreur est bornée à `ERREUR_MAX` octets gardés EN MÉMOIRE (le reste est lu et jeté : aucun fichier
    qui grossirait). `vers` (fichier binaire ouvert) : la sortie y est écrite au fil de l'eau au lieu d'être gardée (paquet
    Git sans double copie en mémoire) ; la sortie rendue est alors vide. Langue C (messages de git stables), jamais d'invite."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "LANGUAGE": "C"}
    options = {} if os.name == "nt" else {"start_new_session": True}
    try:
        p = subprocess.Popen([*_COMMANDE_GIT, *args], cwd=str(projet), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, env=env, **options)
    except OSError as e:
        return 127, b"", f"git introuvable ou inutilisable ({type(e).__name__})"
    echeance = time.monotonic() + DELAI_GIT_S
    morceaux, erreurs = [], []
    etat = {"total": 0, "trop": False, "ecriture": None}
    fini = threading.Event()

    def lire_sortie():
        try:
            while True:
                bloc = p.stdout.read1(BLOC)
                if not bloc:
                    return
                etat["total"] += len(bloc)
                if max_octets is not None and etat["total"] > max_octets:
                    etat["trop"] = True
                    return
                if vers is None:
                    morceaux.append(bloc)
                else:
                    try:
                        vers.write(bloc)
                    except (OSError, ValueError) as e:
                        etat["ecriture"] = f"{type(e).__name__} : {e}"
                        return
        except (OSError, ValueError):
            return
        finally:
            fini.set()

    def lire_erreur():
        garde = 0
        try:
            while True:
                bloc = p.stderr.read1(BLOC)
                if not bloc:
                    return
                if garde < ERREUR_MAX:
                    erreurs.append(bloc[:ERREUR_MAX - garde])
                    garde += len(erreurs[-1])
        except (OSError, ValueError):
            return

    fils = [threading.Thread(target=lire_sortie, daemon=True), threading.Thread(target=lire_erreur, daemon=True)]
    for f in fils:
        f.start()
    depasse = not fini.wait(max(0.0, echeance - time.monotonic()))
    if not depasse and not etat["trop"] and etat["ecriture"] is None:
        try:
            p.wait(timeout=max(0.0, echeance - time.monotonic()))
        except subprocess.TimeoutExpired:
            depasse = True
    if depasse or etat["trop"] or etat["ecriture"] is not None or p.poll() is None:
        _tuer_arbre(p)
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    fils[1].join(max(0.0, min(5.0, echeance - time.monotonic())) if not depasse else 0.5)
    if not any(f.is_alive() for f in fils):        # un fil encore bloqué lit toujours : ses tuyaux restent à lui
        p.stdout.close()
        p.stderr.close()
    if depasse:
        return 124, b"", "git : délai dépassé"
    if etat["trop"]:
        return 99, b"", ""
    if etat["ecriture"] is not None:
        return 98, b"", f"écriture de la sortie de git impossible ({etat['ecriture']})"
    return p.returncode, b"".join(morceaux), b"".join(erreurs).decode("utf-8", "replace")


def _ref_valide(nom, git_, drapeau=()):
    code, sortie, _e = git_(Path("."), ["check-ref-format", *drapeau, nom])
    return code == 0, sortie.decode("utf-8", "replace").strip()


def _entier_limite(cle, v, plafonds=None):
    plafonds = plafonds or LIMITES_AGENT
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"La limite « {cle} » doit être un nombre entier.")
    if not 1 <= v <= plafonds[cle]:
        raise ValueError(f"La limite « {cle} » doit être comprise entre 1 et {plafonds[cle]}.")
    return v


def valider_demande_agent(brut, git=_git):
    """`DemandeAgent` validée ; `ValueError` (message français) sinon. Les limites ne dépassent jamais `LIMITES_AGENT`."""
    if not isinstance(brut, dict):
        raise ValueError("La demande d'agent doit être un dictionnaire.")
    inconnues = set(brut) - CLES_DEMANDE_AGENT
    if inconnues:
        raise ValueError("Champ inconnu dans la demande d'agent : "
                         + ", ".join(sorted(repr(str(c)[:40]) for c in inconnues)) + ".")
    mode = brut.get("mode")
    if mode not in MODES_AGENT:
        raise ValueError("Mode inconnu : « seul » ou « pilote ».")
    tache = brut.get("tache")
    if (not isinstance(tache, str) or not MOTIF_TACHE.fullmatch(tache) or tache.startswith(".") or ".." in tache
            or tache.endswith((".", ".lock")) or tache.split(".")[0].lower() in st.NOMS_RESERVES):
        raise ValueError("Nom de tâche invalide (lettres, chiffres, _ . - ; 60 caractères au plus ; ni « .. » ni point "
                         "au début ou à la fin ; pas de nom réservé de Windows comme « con » ou « nul »).")
    base = brut.get("base")
    if not isinstance(base, str) or not MOTIF_BASE.fullmatch(base):
        raise ValueError("Base invalide : 40 caractères hexadécimaux (minuscules) attendus.")
    branche = brut.get("branche")
    if (not isinstance(branche, str) or not MOTIF_BRANCHE.fullmatch(branche) or ".." in branche or "//" in branche
            or branche.endswith(("/", ".", ".lock")) or "/." in branche):
        raise ValueError("Nom de branche invalide.")
    bon, _s = _ref_valide(branche, git, ("--branch",))
    if not bon or _s != branche:
        raise ValueError("Nom de branche refusé par git (check-ref-format).")
    bon, _s = _ref_valide(f"refs/heads/agent/{tache}", git)
    if not bon:
        raise ValueError("Nom de tâche refusé par git : la branche agent/<tâche> serait invalide.")
    reprend = brut.get("reprend")
    if reprend is not None and (not isinstance(reprend, str) or not st.MOTIF_ID.fullmatch(reprend)):
        raise ValueError("Reprise invalide : identifiant de tâche attendu.")
    ident = brut["id"] if "id" in brut else st.nouvel_id()
    if not isinstance(ident, str) or not st.MOTIF_ID.fullmatch(ident):
        raise ValueError("Identifiant de tâche invalide.")
    projet = brut.get("projet")
    if (not isinstance(projet, str) or not projet or len(projet.encode("utf-8")) > 200 or '"' in projet or "\\" in projet
            or any(st._controle(c) for c in projet)):
        raise ValueError("Nom de projet invalide (1 à 200 octets, ni guillemet, ni antislash, ni caractère de contrôle).")
    modele = brut.get("modele")
    if modele is not None and (not isinstance(modele, str) or not MOTIF_MODELE.fullmatch(modele)):
        raise ValueError("Nom de modèle invalide.")
    places = brut.get("places", PLACES_DEFAUT)
    if isinstance(places, bool) or not isinstance(places, int) or not 1 <= places <= 4:
        raise ValueError("Le nombre de places d'agent doit être compris entre 1 et 4.")
    genre = brut.get("genre", "tache")
    if genre not in GENRES_AGENT:
        raise ValueError("Genre d'agent inconnu : « tache » ou « reponse ».")
    flutter = brut.get("flutter", False)
    if flutter is not True and flutter is not False:
        raise ValueError("« flutter » vaut true ou false.")
    flutter_dossier = brut.get("flutter_dossier")
    if flutter_dossier is not None and (not flutter or not isinstance(flutter_dossier, str)
                                        or not MOTIF_DOSSIER_FLUTTER.fullmatch(flutter_dossier) or flutter_dossier == ".."):
        raise ValueError("Dossier Flutter invalide : « . » ou un nom de sous-dossier direct (lettres, chiffres, _ . -), "
                         "pour un projet Flutter seulement.")
    signature = brut.get("signature", "aucune")
    if not isinstance(signature, str) or signature not in SIGNATURES:
        raise ValueError("« signature » vaut aucune, debug_serveur ou poste_signe.")
    limites_brutes = brut.get("limites")
    if limites_brutes is not None and not isinstance(limites_brutes, dict):
        raise ValueError("Les limites doivent être un dictionnaire.")
    plafonds = LIMITES_AGENT_FLUTTER if flutter else LIMITES_AGENT
    limites = dict(plafonds)
    for cle, v in (limites_brutes or {}).items():
        if cle not in LIMITES_AGENT:
            raise ValueError("Limite inconnue : " + repr(str(cle)[:40]) + ".")
        limites[cle] = _entier_limite(cle, v, plafonds)
    return DemandeAgent(id=ident, projet=projet, tache=tache, mode=mode, modele=modele, branche=branche, base=base,
                        limites=MappingProxyType(limites), reprend=reprend, places=places, genre=genre,
                        flutter=flutter, flutter_dossier=flutter_dossier, signature=signature)


def capacites_requises(d):
    """Les capacités du serveur pour cette demande : celles du mode (`agent-serveur` ou `agent-pilote`), plus
    `agent-flutter` (le SDK Flutter de l'hôte) pour un projet Flutter ; sans doublon, dans l'ordre."""
    requises = list(serveur_capacites.BESOINS["agent-pilote" if d.mode == "pilote" else "agent-serveur"])
    if d.flutter:
        requises += serveur_capacites.BESOINS["agent-flutter"]
    return tuple(dict.fromkeys(requises))


def _demande_dict(d):
    """Contenu de entree/demande.json. `projet` et `reprend` n'y figurent qu'une fois (l'enveloppe les relit par motif) ;
    `limites.duree_s` est la valeur même passée à l'enveloppe (une seule source) ; `flutter` (true ou false, une seule
    fois) est relu par l'enveloppe par motif strict."""
    brut = {"id": d.id, "type": "agent", "projet": d.projet, "tache": d.tache, "mode": d.mode, "modele": d.modele,
            "branche": d.branche, "base": d.base, "limites": dict(d.limites), "reprend": d.reprend, "flutter": d.flutter,
            "flutter_dossier": d.flutter_dossier}
    if d.signature != "aucune":      # une seule fois, relue par l'enveloppe par motif strict ; absente = aucune
        brut["signature"] = d.signature
    return brut


def _demande_sure(demande):
    if isinstance(demande, DemandeAgent):
        brut = {"id": demande.id, "projet": demande.projet, "tache": demande.tache, "mode": demande.mode,
                "modele": demande.modele, "branche": demande.branche, "base": demande.base,
                "limites": dict(demande.limites), "reprend": demande.reprend, "places": demande.places,
                "genre": demande.genre, "flutter": demande.flutter, "flutter_dossier": demande.flutter_dossier,
                "signature": demande.signature}
    elif isinstance(demande, dict):
        brut = demande
    else:
        raise st.RefusLancement("La demande doit être une DemandeAgent ou un dictionnaire.")
    try:
        return valider_demande_agent(brut)
    except ValueError as e:
        raise st.RefusLancement(str(e)) from None


# ---------------------------------------------------------------- paquets Git

def preparer_paquet(projet, git=_git, fichier=None):
    """`(paquet, branche, base)` de `HEAD` du dépôt `projet` : `git bundle create - HEAD <branche>`. Refuse un HEAD détaché,
    un dépôt sans commit et un paquet au-dessus de `LIMITES_AGENT["paquet_octets"]`. Les changements non commités ne partent
    pas : `changements_non_commites` les liste pour que `lancer_agent` en avertisse.

    `fichier` (chemin) : le paquet est écrit dans ce fichier au fil de l'eau et `paquet` est ce chemin (`Path`), jamais les
    octets en mémoire (un paquet de 500 Mo ne coûte alors que des tampons de 1 Mo ; `lancer_agent` l'envoie de même)."""
    projet = Path(projet)
    code, sortie, _e = git(projet, ["symbolic-ref", "-q", "HEAD"])
    ref_tete = sortie.decode("utf-8", "replace").strip()
    if code != 0 or not ref_tete.startswith("refs/heads/"):
        raise st.RefusLancement("HEAD est détaché : placez le projet sur une branche avant de lancer un agent serveur "
                                "(seuls les commits de la branche partent).")
    branche = ref_tete[len("refs/heads/"):]
    if not MOTIF_BRANCHE.fullmatch(branche):
        raise st.RefusLancement("Le nom de la branche courante n'est pas admis pour un agent serveur (lettres, chiffres, "
                                "_ . / - ; 200 caractères au plus) : renommez la branche.")
    code, sortie, erreur = git(projet, ["rev-parse", "--verify", "-q", "HEAD^{commit}"])
    base = sortie.decode("ascii", "replace").strip()
    if code != 0 or not MOTIF_BASE.fullmatch(base):
        raise st.RefusLancement("Le projet n'a aucun commit : rien à envoyer à l'agent serveur.")
    maximum = LIMITES_AGENT["paquet_octets"]
    trop_gros = (f"Le paquet Git du projet dépasse {maximum // (1024 * 1024)} Mo : trop gros pour l'agent serveur.")
    if fichier is not None:
        fichier = Path(fichier)
        try:
            with open(fichier, "wb") as f:
                code, _o, erreur = git(projet, ["bundle", "create", "-", "HEAD", ref_tete], max_octets=maximum, vers=f)
            taille = fichier.stat().st_size
        except OSError as e:
            raise st.RefusLancement(f"Paquet Git impossible à écrire sur le poste : {type(e).__name__}.") from None
        if code == 99 or taille > maximum:
            raise st.RefusLancement(trop_gros)
        if code != 0 or not taille:
            raise st.RefusLancement(f"Paquet Git impossible (git bundle, code {code}) : {st._court(erreur, 200)}")
        return fichier, branche, base
    code, paquet, erreur = git(projet, ["bundle", "create", "-", "HEAD", ref_tete], max_octets=maximum)
    if code == 99:
        raise st.RefusLancement(f"Le paquet Git du projet dépasse {maximum // (1024 * 1024)} Mo : trop gros pour "
                                "l'agent serveur.")
    if code != 0 or not paquet:
        raise st.RefusLancement(f"Paquet Git impossible (git bundle, code {code}) : {st._court(erreur, 200)}")
    if len(paquet) > maximum:
        raise st.RefusLancement(f"Le paquet Git du projet dépasse {maximum // (1024 * 1024)} Mo : trop gros pour "
                                "l'agent serveur.")
    return paquet, branche, base


def changements_non_commites(projet, git=_git):
    """Lignes de `git status --porcelain` du projet (fichiers modifiés ou nouveaux) : ce qui NE PART PAS à l'agent, seuls les
    commits partant. Liste vide si tout est commité ; None si git n'a pas pu répondre (rien n'est affirmé : `lancer_agent`
    le dit dans son avertissement). `--no-optional-locks` : la lecture ne prend jamais le verrou de l'index (un autre
    git du poste n'est pas gêné)."""
    code, sortie, _e = git(Path(projet), ["--no-optional-locks", "status", "--porcelain"], max_octets=4 * 1024 * 1024)
    if code != 0:
        return None
    return [ligne for ligne in sortie.decode("utf-8", "replace").splitlines() if ligne.strip()]


def controle_branche_agent(projet, tache, base, git=_git):
    """Message de refus, AVANT tout envoi, si `agent/<tâche>` est la branche extraite d'un dossier de travail du projet (le
    travail de l'agent ne pourrait pas y être récupéré). None sinon. (Une branche existante qui n'est pas un ancêtre de la
    base n'est plus un refus : `ranger_branche_agent` la renomme.)"""
    ref = f"refs/heads/agent/{tache}"
    code, sortie, _e = git(Path(projet), ["worktree", "list", "--porcelain"], max_octets=4 * 1024 * 1024)
    if code == 0 and f"branch {ref}" in sortie.decode("utf-8", "replace").splitlines():
        return (f"La branche agent/{tache} est extraite dans un dossier de travail du projet : changez de branche avant de "
                "lancer l'agent (son travail ne pourrait pas y être récupéré).")
    return None


def ranger_branche_agent(projet, tache, base, git=_git, maintenant=None):
    """Règle seul le cas d'une tâche relancée : si `agent/<tâche>` existe déjà et n'est pas un ancêtre de `base`, elle est
    RENOMMÉE en `agent/<tâche>-ancienne-<horodatage>` (`git branch -m` : même commit, rien supprimé ni réécrit), de sorte que
    la branche repart de la base. Rend le nouveau nom, ou None si rien n'a été renommé (branche absente, ancêtre de la base,
    ou renommage impossible : le résultat de l'agent sera alors refusé à la récupération, sans rien perdre)."""
    ref = f"refs/heads/agent/{tache}"
    code, _o, _e = git(Path(projet), ["rev-parse", "--verify", "-q", ref])
    if code != 0:
        return None
    code, _o, _e = git(Path(projet), ["merge-base", "--is-ancestor", ref, base])
    if code == 0:
        return None
    horodatage = (maintenant or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    for i in range(100):
        nouveau = f"agent/{tache}-ancienne-{horodatage}" + (f"-{i}" if i else "")
        if git(Path(projet), ["rev-parse", "--verify", "-q", f"refs/heads/{nouveau}"])[0] == 0:
            continue
        code, _o, _e = git(Path(projet), ["branch", "-m", f"agent/{tache}", nouveau])
        return nouveau if code == 0 else None
    return None


def _analyser_entete(paquet, ref, base):
    """Relit l'en-tête du paquet (texte avant la première ligne vide) : version 2 ou 3 (`object-format=sha1` seul),
    exactement un prérequis égal à `base`, exactement une référence `ref`. `RefusRecuperation` sinon. Rend la tête."""
    fin = paquet.find(b"\n\n", 0, ENTETE_MAX)
    if fin < 0:
        raise RefusRecuperation("Paquet Git refusé : en-tête introuvable.")
    lignes = paquet[:fin].decode("utf-8", "replace").split("\n")
    if lignes[0] not in ("# v2 git bundle", "# v3 git bundle"):
        raise RefusRecuperation("Paquet Git refusé : ce n'est pas un paquet reconnu (v2 ou v3).")
    prerequis, refs = [], []
    for ligne in lignes[1:]:
        if ligne.startswith("@"):
            if ligne != "@object-format=sha1" or lignes[0] != "# v3 git bundle":
                raise RefusRecuperation("Paquet Git refusé : capacité non admise.")
            continue
        m = re.fullmatch(r"-([0-9a-f]{40})( .*)?", ligne, re.ASCII | re.DOTALL)
        if m:
            prerequis.append(m.group(1))
            continue
        m = re.fullmatch(r"([0-9a-f]{40}) (\S.*)", ligne, re.ASCII)
        if not m:
            raise RefusRecuperation("Paquet Git refusé : ligne d'en-tête inattendue.")
        refs.append((m.group(1), m.group(2)))
    if [r for _t, r in refs] != [ref] or len(refs) != 1:
        raise RefusRecuperation(f"Paquet Git refusé : la seule référence admise est {ref}.")
    if prerequis != [base]:
        raise RefusRecuperation("Paquet Git refusé : son prérequis n'est pas la base envoyée à l'agent.")
    return refs[0][0]


def _verifier_et_recuperer_paquet(projet, paquet, tache, base, git):
    """Vérifie le paquet (en-tête, `git bundle verify`, `list-heads`) puis le récupère dans le dépôt `projet` par un
    `git fetch` simple de la seule référence admise (jamais forcé : une branche locale divergente n'est pas réécrite).
    Le fichier temporaire est toujours effacé. Rien du dépôt du serveur n'est exécuté : le paquet est un fichier de données,
    lu par git avec les contrôles d'intégrité des objets (`transfer.fsckObjects`), hooks et moniteur de fichiers coupés."""
    ref = f"refs/heads/agent/{tache}"
    if isinstance(paquet, os.PathLike):         # paquet rapatrié dans un fichier : seul l'en-tête est lu en mémoire
        try:
            with open(paquet, "rb") as f:
                debut = f.read(ENTETE_MAX)
        except OSError as e:
            raise RefusRecuperation(f"Paquet Git illisible sur le poste ({type(e).__name__}).", transitoire=True) from None
        tete = _analyser_entete(debut, ref, base)
    else:
        tete = _analyser_entete(paquet, ref, base)
    sur =["-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false", "-c", "gc.auto=0",
           "-c", "maintenance.auto=false", "-c", "transfer.fsckObjects=true"]
    code, sortie, _e = git(projet, ["symbolic-ref", "-q", "HEAD"])
    if code == 0 and sortie.decode("utf-8", "replace").strip() == ref:
        raise RefusRecuperation(f"La branche agent/{tache} est la branche extraite du projet : changez de branche pour "
                                "recevoir le travail de l'agent (rien n'a été modifié).")
    with tempfile.TemporaryDirectory(prefix="agent-paquet-", ignore_cleanup_errors=True) as tmp:
        if isinstance(paquet, os.PathLike):
            fichier = Path(paquet)
        else:
            fichier = Path(tmp) / "resultat.bundle"
            fichier.write_bytes(paquet)
        code, _o, erreur = git(projet, [*sur, "bundle", "verify", str(fichier)])
        if code != 0:
            raise RefusRecuperation(f"Paquet Git abîmé ou incomplet (git bundle verify) : {st._court(erreur, 200)}",
                                    transitoire=True)
        code, sortie, erreur = git(projet, [*sur, "bundle", "list-heads", str(fichier)])
        tetes = [ligne.split(" ", 1) for ligne in sortie.decode("utf-8", "replace").splitlines() if ligne.strip()]
        if code != 0 or tetes != [[tete, ref]]:
            raise RefusRecuperation(f"Paquet Git refusé : la seule référence admise est {ref}.")
        code, _o, erreur = git(projet, [*sur, "fetch", "--no-tags", "--no-recurse-submodules", "--quiet",
                                        str(fichier), f"{ref}:{ref}"])
        if code != 0:
            if "checked out" in erreur or "refusing to fetch into" in erreur:
                raise RefusRecuperation(f"La branche agent/{tache} est extraite dans un dossier de travail du projet : "
                                        "changez de branche pour recevoir le travail de l'agent (rien n'a été modifié).")
            raise RefusRecuperation("Branche non récupérée : la branche locale agent/" + tache + " a divergé ou ne "
                                    f"peut pas être mise à jour (non réécrite) : {st._court(erreur, 200)}",
                                    transitoire=True)
        code, sortie, _e = git(projet, ["rev-parse", "--verify", "-q", ref])
        if sortie.decode("ascii", "replace").strip() != tete:
            raise RefusRecuperation("Branche récupérée inattendue : vérification impossible.", transitoire=True)


# ---------------------------------------------------------------- scripts distants

AGENT_SCRIPT = "taches/lancer_agent.sh"
AGENT_DISTANT = f"{DOSSIER_DISTANT}/{AGENT_SCRIPT}"
OUTIL_FLUTTER = "agent-outils/outil-flutter.sh"     # les commandes uniques d'un agent Flutter (montées sur /opt/outils)
PONT_HOTE = "taches/pont_hote.py"          # mode pilote : le pont hôte, et l'enveloppe d'émulation qu'il lance
EMULATION_SCRIPT = st.ENVELOPPE            # taches/lancer_emulation.sh
FICHIERS_ENTREE = ("projet.bundle", "argv.json", "consigne.md", "message.md", "demande.json")
FICHIERS_SORTIE = ("flux.jsonl", "fin.json", "resultat.bundle")
CODE_TROP_GROS = 5

# Préparation : le dossier de la tâche est créé par mkdir (atomique ; 73 s'il existe), l'archive extraite dans un temporaire
# privé, chaque fichier d'entrée vérifié (ordinaire, pas un lien) puis déplacé à sa place ; le temporaire est toujours supprimé.
_PREPARER_AGENT = """# tache:preparer_agent @ID@
umask 077
mkdir -p "$HOME/taches" || exit 1
d="$HOME/taches/@ID@"
mkdir "$d" 2>/dev/null || exit 73
t=$(mktemp -d "$HOME/taches/.depot.XXXXXX") || exit 1
r=1
if tar -x --no-same-owner -C "$t" -f -; then
  ok=1
  for f in @FICHIERS@; do
    [ -f "$t/entree/$f" ] && [ ! -L "$t/entree/$f" ] || ok=0
  done
  if [ "$ok" = 1 ] && mkdir "$d/entree" && chmod 755 "$d/entree" 2>/dev/null; then
    r=0
    for f in @FICHIERS@; do mv -f "$t/entree/$f" "$d/entree/$f" || r=1; done
  fi
fi
rm -rf "$t"
exit $r
"""
_DEPOSER_AGENT = f"""# tache:deposer_agent
umask 077
mkdir -p "$HOME/myiafactory" || exit 1
d=$(mktemp -d "$HOME/myiafactory/.depot.XXXXXX") || exit 1
f="$d/{AGENT_SCRIPT}"
c="$d/{st.COMMUN}"
p="$d/{PONT_HOTE}"
o="$d/{OUTIL_FLUTTER}"
e="$d/{EMULATION_SCRIPT}"
r=1
if tar -x --no-same-owner -C "$d" -f - && [ -f "$f" ] && [ ! -L "$f" ] && [ -s "$f" ] && [ -f "$c" ] && [ ! -L "$c" ] && [ -s "$c" ]; then
  mkdir -p "{DOSSIER_DISTANT}/taches" && mv -f "$c" "{st.COMMUN_DISTANT}" && mv -f "$f" "{AGENT_DISTANT}" && r=0
  if [ "$r" = 0 ] && [ -f "$e" ] && [ ! -L "$e" ] && [ -s "$e" ]; then mv -f "$e" "{st.ENVELOPPE_DISTANTE}" || r=1; fi
  if [ "$r" = 0 ] && [ -f "$p" ] && [ ! -L "$p" ] && [ -s "$p" ]; then mv -f "$p" "{DOSSIER_DISTANT}/{PONT_HOTE}" || r=1; fi
  if [ "$r" = 0 ] && [ -f "$o" ] && [ ! -L "$o" ] && [ -s "$o" ]; then
    mkdir -p "{DOSSIER_DISTANT}/agent-outils" && mv -f "$o" "{DOSSIER_DISTANT}/{OUTIL_FLUTTER}" || r=1
  fi
fi
rm -rf "$d"
exit $r
"""
# <id> <mode> <duree_s> <memoire_mo> <cpus> <places> : tous validés (identifiant, mode, entiers dans les bornes).
_LANCER_AGENT = f"""# tache:lancer_agent @ID@
exec bash "{AGENT_DISTANT}" @ID@ @MODE@ @DUREE@ @MEMOIRE@ @CPUS@ @PLACES@
"""
# Un fichier de sortie/ : seulement ordinaire (ni lien symbolique, ni lien dur), de taille APPARENTE sous @MAX@ octets, dans
# un sortie/ dont le chemin physique est bien celui de la tâche ; jamais rien d'autre (pont/, travail/, maison/ sont ignorés).
# 3 : absent ; 5 : trop gros ou lien.
# Abandon (aucune place) : le paquet et l'APK déposés n'ont plus rien à faire sur le serveur.
_ABANDON_AGENT = """# tache:abandon_agent @ID@
rm -f -- "$HOME/taches/@ID@/entree/projet.bundle" "$HOME/taches/@ID@/entree/app.apk"
"""
_FICHIER = """# tache:fichier @ID@ @NOM@
set -u
r=$(cd -P -- "$HOME/taches/@ID@" 2>/dev/null && pwd -P) || exit 3
cd -P -- "$r/sortie" 2>/dev/null && [ "$(pwd -P)" = "$r/sortie" ] || exit 3
[ -e "./@NOM@" ] || exit 3
[ -f "./@NOM@" ] && [ ! -L "./@NOM@" ] || exit 5
[ -n "$(find "./@NOM@" -maxdepth 0 -type f -links 1 -size -@MAX@c 2>/dev/null)" ] || exit 5
exec head -c @MAX@ -- "./@NOM@"
"""


def _script(modele, ident, **valeurs):
    return st._script(modele, ident, **valeurs)


def _deposer_agent(serveur, ssh, avec_pont, avec_flutter=False):
    """Dépose lancer_agent.sh, commun.sh (qu'il source) et, pour le mode pilote, pont_hote.py et lancer_emulation.sh (que le
    pont hôte lance au premier `demarrer`). None si réussi, sinon le message."""
    fichiers = []
    a_deposer = [(AGENT_SCRIPT, 0o755), (st.COMMUN, 0o644)]
    if avec_pont:
        a_deposer += [(EMULATION_SCRIPT, 0o755), (PONT_HOTE, 0o644)]
    if avec_flutter:
        a_deposer.append((OUTIL_FLUTTER, 0o755))
    for rel, mode in a_deposer:
        source = RACINE_SERVEUR / rel
        if source.is_symlink() or not source.is_file():
            return f"Fichier du dépôt introuvable : serveur_ovh/{rel}."
        donnees = source.read_bytes()
        if rel.endswith('.sh'):                         # un script depose au serveur est TOUJOURS en LF (un CRLF casse son shebang)
            donnees = donnees.replace(bytes([13, 10]), bytes([10]))
        fichiers.append((rel, donnees, mode))
    code, _o, erreur = st._octets(serveur, ssh, _DEPOSER_AGENT, st._archive(fichiers), delai=120, silencieux=True)
    if code != 0:
        return f"Dépôt de l'enveloppe d'agent sur le serveur impossible (code {code}) : {st._court(erreur, 200)}"
    messages = [ligne for ligne in erreur.splitlines()
                if ligne.strip() and not ligne.strip().startswith("Warning: Permanently added ")]
    if messages:
        return f"Dépôt de l'enveloppe d'agent douteux (messages du serveur) : {st._court(' '.join(messages), 200)}"
    return None


# ---------------------------------------------------------------- lancer

def _texte_octets(valeur, nom):
    if isinstance(valeur, str):
        return valeur.encode("utf-8")
    if isinstance(valeur, (bytes, bytearray)):
        return bytes(valeur)
    raise st.RefusLancement(f"{nom} : du texte est attendu.")


def _archive_fichier(membres, sortie):
    """Archive tar de (nom, données, droits) écrite dans le fichier binaire `sortie` : comme `serveur_tache._archive`, mais
    une donnée peut être un CHEMIN (`os.PathLike`, le paquet Git) recopié par blocs, jamais chargé en mémoire."""
    with tarfile.open(fileobj=sortie, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for nom, donnees, droits in membres:
            info = tarfile.TarInfo(nom)
            info.mode, info.mtime = droits, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if isinstance(donnees, os.PathLike):
                with open(donnees, "rb") as source:
                    info.size = os.fstat(source.fileno()).st_size
                    tar.addfile(info, source)
            else:
                info.size = len(donnees)
                tar.addfile(info, io.BytesIO(donnees))


def _envoyer(serveur, ssh, d, paquet, argv, consigne, message, apk):
    """Crée ~/taches/<id> (qui ne doit pas exister) avec entree/ ; (code, erreur), 73 si l'identifiant est pris. L'archive est
    écrite dans un fichier temporaire, puis ce FICHIER est l'entrée standard de ssh (aucune copie du paquet en mémoire)."""
    demande = (json.dumps(_demande_dict(d), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    membres = [("entree/projet.bundle", paquet, 0o600),
               ("entree/argv.json", (json.dumps(argv, ensure_ascii=False) + "\n").encode("utf-8"), 0o600),
               ("entree/consigne.md", consigne, 0o600), ("entree/message.md", message, 0o600),
               ("entree/demande.json", demande, 0o600)]
    fichiers = list(FICHIERS_ENTREE)
    if d.mode == "pilote":
        membres.append(("entree/app.apk", apk, 0o644))
        fichiers.append("app.apk")
    try:
        archive = tempfile.TemporaryFile(prefix="agent-entree-")
    except OSError as e:
        return 1, f"Archive des entrées impossible sur le poste ({type(e).__name__})."
    with archive:
        try:
            _archive_fichier(membres, archive)
            archive.flush()
            archive.seek(0)
        except OSError as e:
            return 1, f"Archive des entrées impossible sur le poste ({type(e).__name__} : {e})."
        code, _s, erreur = st._octets(serveur, ssh, _script(_PREPARER_AGENT, d.id, FICHIERS=" ".join(fichiers)),
                                      archive, delai=900)
    return code, erreur


def _doublon(dossier, d):
    """Message de refus si une tâche d'agent ACTIVE du même projet porte le même nom de tâche, à la casse près (deux agents
    sur la même branche agent/<tâche>, ou deux branches qui se confondent sous Windows) ; None sinon. Une tâche abandonnée
    faute de place (`abandonnee`, jamais démarrée et jamais démarrable) ne compte pas."""
    for i, f in st.Index(dossier).lire().items():
        if f.get("abandonnee") is True and f.get("etat") == "en_attente":
            continue
        if (f.get("type") == "agent" and f.get("etat") in ("en_attente", "en_cours") and f.get("projet") == d.projet
                and isinstance(f.get("tache"), str) and f["tache"].lower() == d.tache.lower() and i != d.id):
            return (f"Une tâche d'agent « {f['tache']} » est déjà en cours pour ce projet ({i}) : attendez sa fin ou "
                    "choisissez un autre nom de tâche (les noms ne se distinguent pas par la casse).")
    return None


def lancer_agent(demande, paquet, argv, consigne, message, apk=None, dossier=plateforme_acces.DOSSIER,
                 ssh=plateforme_ssh, attente_max_s=600, dormir=time.sleep, projet=None, git=_git):
    """Voir `_lancer_agent`. `projet` (dossier du dépôt, facultatif) : les changements non commités sont listés dans
    `avertissement` du résultat (ils ne partent pas : seuls les commits partent) et une branche `agent/<tâche>` locale qui
    ne serait pas un ancêtre de la base est refusée avant tout envoi."""
    d = _demande_sure(demande)
    avertissement = None
    sauvegarde = None
    if projet is not None:
        message_branche = controle_branche_agent(projet, d.tache, d.base, git)
        if message_branche:
            raise st.RefusLancement(message_branche)
        sauvegarde = ranger_branche_agent(projet, d.tache, d.base, git)
        lignes = changements_non_commites(projet, git)
        if lignes is None:
            avertissement = ("État des fichiers du projet illisible (git status en échec) : d'éventuels changements non "
                             "commités ne partiront pas, seuls les commits partent à l'agent.")
        elif lignes:
            avertissement = (f"{len(lignes)} changement(s) non commité(s) restent sur le poste : seuls les commits partent à "
                             "l'agent (" + st._court(" ; ".join(l.strip() for l in lignes[:5]), 200)
                             + (" ; ..." if len(lignes) > 5 else "") + ").")
    resultat = _lancer_agent(d, paquet, argv, consigne, message, apk, dossier, ssh, attente_max_s, dormir)
    if sauvegarde and isinstance(resultat, dict) and resultat.get("id"):
        ligne = (f"{st._maintenant_iso()} La branche agent/{d.tache} existait déjà sans être un ancêtre de la base : "
                 f"renommée en {sauvegarde} (sauvegarde, rien supprimé) ; la tâche repart de la base.")
        st._noter(dossier, resultat["id"], {"branche_sauvegardee": sauvegarde, "journal": [ligne]})
    if avertissement and isinstance(resultat, dict):
        resultat["avertissement"] = avertissement
    return resultat


def _lancer_agent(demande, paquet, argv, consigne, message, apk, dossier, ssh, attente_max_s, dormir):
    """Envoie les entrées de l'agent (paquet Git, `argv.json`, consigne, message, demande ; `apk` obligatoire en mode pilote),
    démarre `lancer_agent.sh` sur le serveur choisi (capacités `BESOINS["agent-serveur"]` ou `["agent-pilote"]`), attend une
    place (nouvel essai toutes les 15 s jusqu'à `attente_max_s`) et tient l'index (fiche `type: agent`).

    Renvoie `{id, etat, serveur_id}`, plus `erreur` en cas d'échec ou d'abandon, comme `serveur_tache.lancer`.
    `RefusLancement` avant tout envoi : demande, paquet, argv, APK ou délai invalide, aucun serveur prêt, tâche du même
    nom déjà active (à la casse près).

    Rejouer le même nom de tâche avec une base nouvelle : une `agent/<tâche>` locale qui n'est pas un ancêtre de la base
    est renommée en sauvegarde (voir `ranger_branche_agent`) ; sinon la nouvelle branche avance l'ancienne."""
    d = demande
    if not isinstance(d, DemandeAgent):
        d = _demande_sure(demande)
    doublon = _doublon(dossier, d)
    if doublon:
        raise st.RefusLancement(doublon)
    if isinstance(paquet, os.PathLike):        # paquet écrit dans un fichier par `preparer_paquet(fichier=...)`
        try:
            taille = Path(paquet).stat().st_size if Path(paquet).is_file() else 0
        except OSError:
            taille = 0
        if not taille:
            raise st.RefusLancement("Paquet Git absent ou vide : le fichier du paquet est introuvable ou vide.")
    elif isinstance(paquet, (bytes, bytearray)) and paquet:
        taille = len(paquet)
    else:
        raise st.RefusLancement("Paquet Git absent ou vide : les octets du paquet (ou son fichier) sont attendus.")
    if taille > d.limites["paquet_octets"]:
        raise st.RefusLancement(f"Paquet Git trop gros : {d.limites['paquet_octets'] // (1024 * 1024)} Mo au plus.")
    if (not isinstance(argv, list) or not argv or not all(isinstance(a, str) and "\0" not in a for a in argv)
            or len(json.dumps(argv)) > 65536):
        raise st.RefusLancement("argv invalide : une liste de textes (la commande claude et ses options) est attendue.")
    consigne, message = _texte_octets(consigne, "Consigne"), _texte_octets(message, "Message")
    for nom, v in (("Consigne", consigne), ("Message", message)):
        if not v or len(v) > 1024 * 1024:
            raise st.RefusLancement(f"{nom} vide ou trop long (1 Mo au plus).")
    if d.mode == "pilote":
        st._apk_sur(apk)
    else:
        apk = None
    if isinstance(attente_max_s, bool) or not isinstance(attente_max_s, int) or attente_max_s < 0:
        raise st.RefusLancement("attente_max_s doit être un nombre entier de secondes, positif ou nul.")
    requises = capacites_requises(d)
    serveur = st.choisir_serveur(dossier, requises)

    def sortie(etat_, **plus):
        return st._masque({"id": d.id, "etat": etat_, "serveur_id": serveur.id, **plus}, dossier)

    candidat = d.id
    for _ in range(st.ESSAIS_ID):
        if candidat not in st.Index(dossier).lire():
            code, erreur = _envoyer(serveur, ssh, replace(d, id=candidat), paquet, argv, consigne, message, apk)
            if code == 0:
                break
            if code != st.CODE_EXISTE:
                d = replace(d, id=candidat)
                if code not in st.INJOIGNABLE:
                    st._bash(serveur, ssh, _script(st._EFFACER, candidat))
                return sortie("echouee", erreur=f"Envoi des entrées de l'agent impossible (code {code}) : "
                                                f"{st._court(erreur, 200)}")
        candidat = st.nouvel_id()
    else:
        raise st.RefusLancement("Aucun identifiant de tâche libre après plusieurs essais : réessayez.")
    d = replace(d, id=candidat)
    fiche = {"type": "agent", "etat": "en_attente", "serveur_id": serveur.id, "mode": d.mode, "projet": d.projet,
             "tache": d.tache, "genre": d.genre, "session": None, "branche": d.branche, "base": d.base, "reprend": d.reprend,
             "limites": dict(d.limites), "cree": st._maintenant_iso(), "debut": None, "fin": None, "statut": None,
             "raison": "Entrées envoyées : démarrage demandé."}
    try:
        st.Index(dossier).enregistrer(d.id, st._masque(fiche, dossier))
    except (st.ErreurIndex, TimeoutError, ValueError, OSError) as e:
        st._bash(serveur, ssh, _script(st._EFFACER, d.id))
        return sortie("echouee", erreur=f"{st._court(e)} : tâche non démarrée, rien ne tourne sur le serveur.")

    probleme = _deposer_agent(serveur, ssh, d.mode == "pilote", d.flutter)
    if probleme:
        st._bash(serveur, ssh, _script(st._EFFACER, d.id))
        avert = st._noter(dossier, d.id, {"etat": "echouee", "statut": "erreur", "fin": st._maintenant_iso(),
                                          "raison": probleme})
        return sortie("echouee", erreur=probleme + (f" ({avert})" if avert else ""))
    commande = _script(_LANCER_AGENT, d.id, MODE=d.mode, DUREE=str(int(d.limites["duree_s"])),
                       MEMOIRE=str(int(d.limites["memoire_mo"])), CPUS=str(int(d.limites["cpus"])),
                       PLACES=str(int(d.places)))
    attendu = 0
    while True:
        code, sortie_texte, erreur = st._bash(serveur, ssh, commande, delai=180)
        if code != 75:
            break
        if attendu >= attente_max_s:
            message_abandon = (f"Aucune place d'agent libre après {attendu} s : lancement abandonné (la tâche reste en "
                               "attente sur le serveur ; relancez plus tard).")
            st._bash(serveur, ssh, _script(_ABANDON_AGENT, d.id))
            avert = st._noter(dossier, d.id, {"etat": "en_attente", "raison": message_abandon, "abandonnee": True})
            return sortie("en_attente", erreur=message_abandon + (f" ({avert})" if avert else ""))
        dormir(st.PAUSE_CRENEAU_S)
        attendu += st.PAUSE_CRENEAU_S

    lu = st._derniere_ligne_json(sortie_texte, d.id)
    if code in (0, 3):
        avert = st._noter(dossier, d.id, {"etat": "en_cours", "debut": (lu or {}).get("debut"),
                                          "raison": (lu or {}).get("raison", "")})
        return sortie("en_cours", erreur=avert) if avert else sortie("en_cours")
    if code in st.INJOIGNABLE or code == 4:
        relu = st._etat(d.id, dossier, ssh)
        if relu["etat"] == "arretee":
            return sortie("arretee", raison=relu.get("raison", ""))
        motif = ("Réponse du serveur perdue pendant le démarrage : état relu sur le serveur."
                 if code != 4 else "Identifiant déjà utilisé sur le serveur : état relu sur le serveur.")
        return sortie(relu["etat"], erreur=f"{motif} {relu.get('raison', '')}".strip())
    raison = (lu or {}).get("raison") or f"Démarrage refusé par l'enveloppe (code {code}) : {st._court(erreur, 200)}"
    if lu is None:                      # argument refusé (code 2) : rien n'a été écrit, le dossier d'entrée est effacé
        st._bash(serveur, ssh, _script(st._EFFACER, d.id))
    avert = st._noter(dossier, d.id, {"etat": "echouee", "statut": "erreur",
                                      "fin": (lu or {}).get("fin") or st._maintenant_iso(), "raison": raison})
    return sortie("echouee", erreur=raison + (f" ({avert})" if avert else ""))


# ---------------------------------------------------------------- récupérer

def _fichier_sortie(serveur, ssh, ident, nom, maximum):
    """Octets d'un fichier de sortie/ ; None s'il est absent ; `RefusRecuperation` s'il est trop gros, n'est pas un fichier
    ordinaire ou si le serveur est muet. Taille bornée par la taille apparente, vérifiée aussi sur ce qui est reçu."""
    if nom not in FICHIERS_SORTIE:
        raise ValueError("Fichier de sortie inconnu.")
    code, donnees, erreur = st._octets(serveur, ssh, "bash -s",
                                       _script(_FICHIER, ident, NOM=nom, MAX=str(maximum + 1)).encode("utf-8"),
                                       delai=900)
    if code == 3:
        return None
    _juger_code(nom, code, erreur, maximum)
    if len(donnees) > maximum:
        raise RefusRecuperation(f"{nom} refusé : plus de {maximum} octets reçus.")
    return donnees


def _juger_code(nom, code, erreur, maximum):
    if code in (CODE_TROP_GROS, 99):
        raise RefusRecuperation(f"{nom} refusé : fichier trop gros (plus de {maximum} octets) ou qui n'est pas ordinaire.")
    if code != 0:
        raise RefusRecuperation(f"Rapatriement de {nom} en échec (code {code}) : {st._court(erreur, 200)}",
                                transitoire=True)


def _fichier_sortie_vers(serveur, ssh, ident, nom, maximum, destination):
    """Comme `_fichier_sortie`, mais la sortie de ssh va DROIT dans le fichier `destination` par blocs bornés
    (`ssh.executer_vers_fichier`) : un paquet résultat de 500 Mo n'est jamais en mémoire. Taille reçue, ou None si le
    fichier est absent sur le serveur. Un exécuteur SSH sans cette fonction (faux SSH) passe par les octets."""
    vers = getattr(ssh, "executer_vers_fichier", None)
    if vers is None:
        donnees = _fichier_sortie(serveur, ssh, ident, nom, maximum)
        if donnees is None:
            return None
        Path(destination).write_bytes(donnees)
        return len(donnees)
    if nom not in FICHIERS_SORTIE:
        raise ValueError("Fichier de sortie inconnu.")
    script = _script(_FICHIER, ident, NOM=nom, MAX=str(maximum + 1)).encode("utf-8")
    try:
        code, taille, erreur = vers(serveur_etat.cible(serveur), "bash -s", serveur.cle, destination, maximum,
                                    entree=script, delai=900)
    except Exception as e:  # noqa: BLE001 - ssh absent, hôte invalide : panne de transfert
        code, taille, erreur = 255, 0, f"{type(e).__name__} : {e}"
    if code == 3:
        return None
    _juger_code(nom, code, erreur, maximum)
    if not isinstance(taille, int) or taille > maximum:
        raise RefusRecuperation(f"{nom} refusé : plus de {maximum} octets reçus.")
    return taille


def _entier_fin(v, nom, maxi):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= maxi:
        raise RefusRecuperation(f"fin.json refusé : « {nom} » invalide.")
    return v


def _lire_fin(octets, tache, base):
    """fin.json NON FIABLE -> `{"code", "commits", "branche", "base"[, "echeance"]}` revalidé (clés inconnues ignorées)."""
    try:
        brut = json.loads(octets.decode("utf-8"))
    except (ValueError, RecursionError):
        raise RefusRecuperation("fin.json refusé : JSON illisible.") from None
    if not isinstance(brut, dict):
        raise RefusRecuperation("fin.json refusé : objet attendu.")
    if isinstance(brut.get("code"), bool) or not isinstance(brut.get("code"), int) or abs(brut["code"]) > 1000:
        raise RefusRecuperation("fin.json refusé : « code » invalide.")
    commits = _entier_fin(brut.get("commits"), "commits", 1_000_000)
    branche = brut.get("branche")
    if commits > 0 and branche != f"agent/{tache}":
        raise RefusRecuperation(f"fin.json refusé : la seule branche admise est agent/{tache}.")
    if branche is not None and (not isinstance(branche, str) or branche != f"agent/{tache}"):
        raise RefusRecuperation(f"fin.json refusé : la seule branche admise est agent/{tache}.")
    if brut.get("base") != base:
        raise RefusRecuperation("fin.json refusé : la base ne correspond pas à celle envoyée à l'agent.")
    fin = {"code": brut["code"], "commits": commits, "branche": branche, "base": base}
    if isinstance(brut.get("echeance"), bool):
        fin["echeance"] = brut["echeance"]
    return fin


def recuperer(ident, projet, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, git=_git):
    """Rapatrie la sortie d'une tâche d'agent FINIE (`terminee` ou `arretee` seulement : `echouee` peut signaler un secret
    trouvé, sortie vidée) : `{"flux": octets, "fin": dict, "branche": "agent/<tâche>" | None}` plus `etat` et, hors fin
    normale, `raison`. Le paquet est vérifié puis la branche récupérée dans le dépôt `projet` (voir
    `_verifier_et_recuperer_paquet`). Une tâche qui n'est pas finie, ou finie en échec, ne rapatrie rien (flux vide, branche
    None). `RefusRecuperation` si le serveur renvoie du suspect (fin.json, paquet, branche divergente)."""
    st._id_valide(ident)
    fiche = st.Index(dossier).lire().get(ident) or {}
    tache, base = fiche.get("tache"), fiche.get("base")
    if (fiche.get("type") != "agent" or not isinstance(tache, str) or not MOTIF_TACHE.fullmatch(tache)
            or not isinstance(base, str) or not MOTIF_BASE.fullmatch(base)):
        raise RefusRecuperation("Cette tâche n'est pas une tâche d'agent connue de l'index (tâche ou base inconnue).")
    lu = st.etat(ident, dossier, ssh)
    if lu.get("etat") not in ("terminee", "arretee"):
        return {"flux": b"", "fin": {}, "branche": None, "etat": lu.get("etat"), "raison": lu.get("raison", "")}
    serveur = st._serveur_de(ident, dossier)
    flux = _fichier_sortie(serveur, ssh, ident, "flux.jsonl", LIMITES_AGENT["flux_octets"]) or b""
    brut_fin = _fichier_sortie(serveur, ssh, ident, "fin.json", FIN_MAX_OCTETS)
    fin = _lire_fin(brut_fin, tache, base) if brut_fin is not None else {}
    branche = None
    if fin.get("commits", 0) > 0:
        with tempfile.TemporaryDirectory(prefix="agent-resultat-", ignore_cleanup_errors=True) as tmp:
            fichier = Path(tmp) / "resultat.bundle"
            taille = _fichier_sortie_vers(serveur, ssh, ident, "resultat.bundle", LIMITES_AGENT["paquet_octets"], fichier)
            if not taille:
                raise RefusRecuperation("Le paquet résultat est absent alors que fin.json annonce des commits.")
            _verifier_et_recuperer_paquet(Path(projet), fichier, tache, base, git)
        branche = f"agent/{tache}"
    return {"flux": flux, "fin": fin, "branche": branche, "etat": lu["etat"], "raison": lu.get("raison", "")}


# ---------------------------------------------------------------- index

def taches_agent_actives(dossier=plateforme_acces.DOSSIER):
    """Fiches des tâches d'agent en attente ou en cours, lues dans l'index seul (aucune connexion) : pour le rattachement
    après un redémarrage et pour la bascule entre lieux. `[{"id": ..., **fiche}]`."""
    return [{"id": i, **f} for i, f in sorted(st.Index(dossier).lire().items())
            if f.get("type") == "agent" and f.get("etat") in ("en_attente", "en_cours")]
