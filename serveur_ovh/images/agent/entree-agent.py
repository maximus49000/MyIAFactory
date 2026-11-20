#!/usr/bin/env python3
"""Point d'entrée de l'agent dans le conteneur `myiafactory/agent` (Python 3, bibliothèque standard seule).

`entree-agent` (conteneur de l'agent, lancé par serveur_ovh/taches/lancer_agent.sh) :
  1. relit /entree/demande.json et /entree/argv.json ; chaque option de argv.json passe par la liste blanche `DRAPEAUX`
     (miroir de moteur/executeur_serveur.py, test de concordance) : toute autre option, tout argument libre, tout doublon
     est refusé, claude n'est pas lancé ; `--max-turns <tours>` est ajouté (200 au plus, jamais fourni par argv.json) ;
  2. premier passage : `git clone --branch <branche> /entree/projet.bundle /travail/projet`, HEAD vérifié égal à `base`,
     identité « Agent serveur MyIAFactory » / agent@myiafactory.invalid, `git switch -c agent/<tâche>` ; reprise
     (`reprend`) : le dépôt gardé (copié par l'hôte) est repris tel quel ;
  3. lance claude dans /travail/projet : message sur l'entrée standard, CLAUDE_CODE_OAUTH_TOKEN lu dans
     /run/identifiants/jeton et posé dans l'environnement de CE SEUL processus (jamais dans celui de entree-agent, de git,
     ni sur une ligne de commande, ni dans un fichier écrit ici) ; flux vers /sortie/flux.jsonl (coupé à 20 Mo : claude est
     alors arrêté), erreurs vers /sortie/claude.err (64 Ko au plus) ; échéance INTERNE : claude est arrêté à
     `echeance_interne(duree_s)` (duree_s - 120 s, à mi-chemin pour une tâche très courte), AVANT celle du veilleur, puis
     l'entrée conclut (le travail déjà commité est rapporté, fin.json porte alors "echeance": true) ;
  4. tue tout processus restant du conteneur (PID 1 seulement : kill(-1), puis récolte des zombies), commite les restes
     (« Agent : travail non commité à la fin »), écrit /sortie/resultat.bundle (`git bundle create … <base>..agent/<tâche>`,
     rien si aucun commit), retire de /sortie TOUT ce que l'agent y a déposé (seuls flux.jsonl, claude.err et le paquet créé
     ici restent) puis écrit /sortie/fin.json {"code", "commits", "branche", "base"[, "echeance": true]} (temporaire puis
     renommage). Ces commandes git tournent dans le dépôt QUE L'AGENT A ÉCRIT (configuration, .gitattributes compris) : elles
     ne lancent rien de lui (`SURETE_GIT` : ni crochet, ni fsmonitor, ni signature gpg, ni maintenance automatique ;
     GIT_ATTR_NOSYSTEM et core.attributesFile neutre ; $GIT_DIR/info/attributes, prioritaire, remplacé le temps de conclure
     par « * -filter -text -ident -working-tree-encoding » : aucun filtre clean/process, contenu brut) et tiennent une
     échéance globale (DELAI_CONCLURE_S, sous la marge de 120 s) : l'agent ne peut pas bloquer sa propre conclusion.
Signaux : SIGTERM et SIGINT (docker stop, ou `kill -TERM 1` lancé par l'agent lui-même) n'arrêtent que le groupe de processus
de claude ; l'entrée conclut quand même (étape 4). PID 1 d'un espace de noms ne reçoit de l'intérieur aucun signal sans
gestionnaire, SIGKILL compris : l'agent ne peut pas tuer l'entrée pour l'empêcher de conclure. Il garde en revanche la main
sur ce que l'entrée met dans le paquet (ses commits, ses références, ses objets) : resultat.bundle n'est jamais « sûr ».
Sur l'hôte, kernel.yama.ptrace_scope >= 1 est exigé (vérifié par lancer_agent.sh) : sinon claude, même utilisateur que
l'entrée, pourrait la tracer (ptrace) et lui faire écrire n'importe quoi.
Ces garanties ne valent qu'à l'intérieur du conteneur : fin.json, flux.jsonl et resultat.bundle restent des données NON
FIABLES pour l'hôte et le poste (T3 : paquet vérifié, seule référence agent/<tâche>, tailles bornées) ; données non fiables.

`entree-agent --verifier` (conteneur de CONTRÔLE lancé par le veilleur de l'hôte : sans jeton, `--network none`, /travail,
/sortie et /entree en lecture seule) : écrit sur la sortie standard le texte de
`git log -p --no-textconv --no-ext-diff <base>..agent/<tâche>` (et --text, -m, --no-renames, format brut : rien de ce que
l'agent a commité n'est caché par .gitattributes, une fusion ou un renommage) puis le contenu brut de CHAQUE objet du paquet
/sortie/resultat.bundle. Tout tourne dans un dépôt neuf de /tmp dont les objets de /travail ne sont qu'une réserve
(alternates) : ni la configuration, ni les crochets, ni les objets de remplacement, ni les greffes du dépôt de l'agent ne
jouent. L'hôte y cherche le jeton (grep -F). Code 0 : texte complet ; 3 : contrôle impossible (l'hôte n'en rapatrie rien).

Environnement posé par lancer_agent.sh : HOME et AGENT_DUREE_S (la durée duree_s passée à l'enveloppe, celle de son veilleur ;
elle l'emporte sur limites.duree_s de demande.json : l'échéance interne et celle du veilleur partent de la même valeur).
Réservées aux tests (jamais posées par lancer_agent.sh) : AGENT_RACINE (préfixe des chemins /entree, /travail, /sortie,
/maison, /run/identifiants/jeton ; « / » par défaut) et AGENT_CLAUDE (commande de claude, liste JSON ; ["claude"] par défaut).
"""
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

# Liste blanche des options de `claude` (miroir exact de moteur/executeur_serveur.py, décision R2) : nom -> None (option sans
# valeur) ou motif que la valeur suivante doit vérifier EN ENTIER (re.fullmatch). Une valeur ne commence jamais par « - ».
DRAPEAUX = {
    "-p": None,
    "--output-format": r"stream-json",
    "--verbose": None,
    "--model": r"claude-[a-z0-9][a-z0-9.-]{0,62}|fable",
    "--tools": r"|[A-Za-z][A-Za-z0-9_]{0,63}(?:,[A-Za-z][A-Za-z0-9_]{0,63}){0,63}",
    # règles « Nom » ou « Nom(motif sans parenthèse) », séparées par « , » ou une espace, 64 au plus, 8 Ko au plus
    "--allowedTools": r"(?=[\s\S]{1,8192}\Z)"
                      r"[A-Za-z][A-Za-z0-9_]{0,63}(?:\([^()\x00-\x1f\x7f]*\))?"
                      r"(?:[, ][A-Za-z][A-Za-z0-9_]{0,63}(?:\([^()\x00-\x1f\x7f]*\))?){0,63}",
    "--permission-prompts": r"none",
    "--append-system-prompt-file": r"/entree/consigne\.md",
    "--system-prompt-file": r"/entree/consigne\.md",
    "--strict-mcp-config": None,
    "--setting-sources": r"",
    "--disable-slash-commands": None,
    "--resume": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "--no-session-persistence": None,
}
OBLIGATOIRES = ("-p", "--output-format")
LIMITE_FLUX = 20 * 1024 * 1024
LIMITE_ERREURS = 64 * 1024
TOURS_MAX = 200
DUREE_MAX_S = 86400
DUREE_DEFAUT_S = 2400
MARGE_ECHEANCE_S = 120                    # l'entrée arrête claude 120 s avant l'échéance du veilleur, puis conclut
DELAI_CONCLURE_S = 100                    # échéance de TOUT `conclure` (restes, paquet) : sous la marge, fin.json écrit à temps
MOTIF_DUREE = re.compile(r"[1-9][0-9]{0,5}")
# Options de CHACUNE de nos commandes git (elles l'emportent sur la configuration du dépôt, que l'agent a pu écrire).
SURETE_GIT = ("-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false",
              "-c", "gpg.program=false", "-c", f"core.attributesFile={os.devnull}", "-c", "core.autocrlf=false",
              "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "submodule.recurse=false")
# $GIT_DIR/info/attributes (priorité la plus haute) le temps de conclure : aucun filtre, aucune conversion, contenu brut.
ATTRIBUTS_NEUTRES = b"* -filter -text -ident -working-tree-encoding\n"
JSON_MAX_OCTETS = 65536
IDENTITE = ("Agent serveur MyIAFactory", "agent@myiafactory.invalid")
MESSAGE_RESTES = "Agent : travail non commité à la fin"
MOTIF_TACHE = re.compile(r"[A-Za-z0-9_.-]{1,60}")
MOTIF_BRANCHE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}")
MOTIF_BASE = re.compile(r"[0-9a-f]{40}")
MOTIF_ID = re.compile(r"t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}")
MOTIF_JETON = re.compile(r"[A-Za-z0-9._-]{20,400}")
SANS_LIEN = getattr(os, "O_NOFOLLOW", 0)


class Refus(Exception):
    """Une entrée refusée : claude n'est pas lancé. Le message ne cite jamais le contenu du jeton."""


def chemins():
    racine = os.environ.get("AGENT_RACINE") or "/"
    def c(*p):
        return os.path.join(racine, *p)
    return {"entree": c("entree"), "travail": c("travail"), "sortie": c("sortie"), "maison": c("maison"),
            "jeton": c("run", "identifiants", "jeton"), "depot": c("travail", "projet")}


# ------------------------------------------------------------------------------------------------------------- entrées

def _sans_doublon(paires):
    vu = {}
    for cle, valeur in paires:
        if cle in vu:
            raise Refus(f"clé JSON en double : {cle[:40]}")
        vu[cle] = valeur
    return vu


def lire_octets(chemin, maximum):
    """Les octets d'un fichier ordinaire, jamais par un lien, `maximum` octets au plus (sinon Refus)."""
    try:
        fd = os.open(chemin, os.O_RDONLY | SANS_LIEN | getattr(os, "O_BINARY", 0))
    except OSError:
        raise Refus(f"{os.path.basename(chemin)} absent ou illisible")
    with os.fdopen(fd, "rb") as f:
        donnees = f.read(maximum + 1)
    if len(donnees) > maximum:
        raise Refus(f"{os.path.basename(chemin)} trop gros ({maximum} octets au plus)")
    return donnees


def lire_json(chemin):
    try:                                  # un Refus de _sans_doublon (clé en double) traverse tel quel
        return json.loads(lire_octets(chemin, JSON_MAX_OCTETS).decode("utf-8"), object_pairs_hook=_sans_doublon)
    except ValueError:                    # JSON ou UTF-8 invalide
        raise Refus(f"{os.path.basename(chemin)} illisible (JSON attendu)")


def _entier(valeur, nom, mini, maxi, defaut):
    if valeur is None:
        return defaut
    if type(valeur) is not int or not mini <= valeur <= maxi:
        raise Refus(f"limite {nom} refusée ({mini} à {maxi})")
    return valeur


def valider_demande(brut):
    """La demande (demande.json) : tâche, branche, base, reprise et limites, validées par motifs fermés."""
    if not isinstance(brut, dict):
        raise Refus("demande.json : objet attendu")
    tache, branche, base, reprend = brut.get("tache"), brut.get("branche"), brut.get("base"), brut.get("reprend")
    if not isinstance(tache, str) or not MOTIF_TACHE.fullmatch(tache) or tache.startswith(".") or ".." in tache \
            or tache.endswith((".", ".lock")):
        raise Refus("tâche refusée")
    if not isinstance(branche, str) or not MOTIF_BRANCHE.fullmatch(branche) or ".." in branche or "//" in branche \
            or branche.endswith(("/", ".", ".lock")) or "/." in branche:
        raise Refus("branche refusée")
    if not isinstance(base, str) or not MOTIF_BASE.fullmatch(base):
        raise Refus("base refusée (40 hexadécimaux)")
    if reprend is not None and (not isinstance(reprend, str) or not MOTIF_ID.fullmatch(reprend)):
        raise Refus("reprise refusée (identifiant de tâche attendu)")
    limites = brut.get("limites")
    if limites is None:
        limites = {}
    if not isinstance(limites, dict):
        raise Refus("limites : objet attendu")
    return {"tache": tache, "branche": branche, "base": base, "reprend": reprend,
            "tours": _entier(limites.get("tours"), "tours", 1, TOURS_MAX, TOURS_MAX),
            "flux_octets": _entier(limites.get("flux_octets"), "flux_octets", 1, LIMITE_FLUX, LIMITE_FLUX),
            "duree_s": _entier(limites.get("duree_s"), "duree_s", 1, DUREE_MAX_S, DUREE_DEFAUT_S)}


def duree_hote(duree_demande):
    """La durée qui fait foi : AGENT_DUREE_S (posée par lancer_agent.sh, la même que celle de son veilleur), sinon celle de
    demande.json (tests). Une valeur posée mais hors motif (1 à 86400, sans zéro initial) : Refus."""
    brut = os.environ.get("AGENT_DUREE_S")
    if brut is None:
        return duree_demande
    if not MOTIF_DUREE.fullmatch(brut) or int(brut) > DUREE_MAX_S:
        raise Refus(f"AGENT_DUREE_S refusée (1 à {DUREE_MAX_S})")
    return int(brut)


def valider_argv(argv):
    """argv.json -> les options de claude (sans argv[0]), chacune passée par DRAPEAUX. Refus pour tout le reste."""
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise Refus("argv.json : liste de textes attendue")
    if argv[0] != "claude":
        raise Refus("argv.json : la commande doit être claude")
    options, vues, i = [], set(), 1
    while i < len(argv):
        nom = argv[i]
        if nom not in DRAPEAUX:
            raise Refus(f"option hors liste refusée : {nom[:60]}")
        if nom in vues:
            raise Refus(f"option en double refusée : {nom}")
        vues.add(nom)
        motif = DRAPEAUX[nom]
        if motif is None:
            options.append(nom)
            i += 1
            continue
        if i + 1 >= len(argv):
            raise Refus(f"valeur manquante pour {nom}")
        valeur = argv[i + 1]
        if valeur.startswith("-") or not re.fullmatch(motif, valeur):
            raise Refus(f"valeur refusée pour {nom}")
        options += [nom, valeur]
        i += 2
    for nom in OBLIGATOIRES:
        if nom not in vues:
            raise Refus(f"option obligatoire absente : {nom}")
    if ("--system-prompt-file" in vues) == ("--append-system-prompt-file" in vues):
        raise Refus("une et une seule consigne (--system-prompt-file ou --append-system-prompt-file)")
    return options


def lire_jeton(chemin):
    try:
        texte = lire_octets(chemin, 1024).decode("ascii").strip()
    except (Refus, UnicodeDecodeError):
        raise Refus("jeton de l'abonnement absent ou illisible (/run/identifiants/jeton)")
    if not MOTIF_JETON.fullmatch(texte):
        raise Refus("jeton de l'abonnement mal formé (/run/identifiants/jeton) : à réenregistrer sur le serveur")
    return texte


# ------------------------------------------------------------------------------------------------------------- git

def env_git(maison):
    """L'environnement de NOS commandes git : jamais le jeton, ni la configuration globale ou système, ni les objets de
    remplacement, ni les attributs du système."""
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": maison, "LC_ALL": "C", "LANG": "C",
           "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_NO_REPLACE_OBJECTS": "1", "GIT_ATTR_NOSYSTEM": "1"}
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def git(depot, *args, env, **kw):
    """git avec SURETE_GIT (ni crochet, ni fsmonitor, ni gpg...), en tableau d'arguments ; `check` par défaut."""
    kw.setdefault("check", True)
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(["git", *SURETE_GIT, "-C", depot, *args], env=env, **kw)


def sortie_git(depot, *args, env, timeout=None):
    return git(depot, *args, env=env, capture_output=True, timeout=timeout).stdout.decode("utf-8", "replace").strip()


def preparer_depot(c, d, env):
    depot = c["depot"]
    if d["reprend"]:
        if not os.path.isdir(os.path.join(depot, ".git")):
            raise Refus("reprise demandée sans dépôt gardé dans /travail/projet")
        ref = f"refs/heads/agent/{d['tache']}"
        if git(depot, "rev-parse", "-q", "--verify", ref, env=env, check=False, capture_output=True).returncode == 0:
            git(depot, "switch", "-q", f"agent/{d['tache']}", env=env, check=False, capture_output=True)
        return depot
    if os.path.lexists(depot):
        raise Refus("premier passage : /travail/projet existe déjà")
    paquet = os.path.join(c["entree"], "projet.bundle")
    if os.path.islink(paquet) or not os.path.isfile(paquet):
        raise Refus("projet.bundle absent")
    r = subprocess.run(["git", *SURETE_GIT, "clone", "--quiet", "--branch", d["branche"], "--",
                        paquet, depot], env=env, stdin=subprocess.DEVNULL, capture_output=True)
    if r.returncode != 0:
        raise Refus("git clone du paquet impossible : " + r.stderr.decode("utf-8", "replace").strip()[:300])
    if sortie_git(depot, "rev-parse", "HEAD", env=env) != d["base"]:
        raise Refus("le paquet ne porte pas la base annoncée")
    git(depot, "config", "user.name", IDENTITE[0], env=env, capture_output=True)
    git(depot, "config", "user.email", IDENTITE[1], env=env, capture_output=True)
    git(depot, "switch", "-q", "-c", f"agent/{d['tache']}", env=env, capture_output=True)
    return depot


def neutraliser_attributs(depot):
    """Pose ATTRIBUTS_NEUTRES dans $GIT_DIR/info/attributes (jamais à travers un lien) ; rend les octets du fichier de l'agent
    (None s'il n'y en avait pas, ou s'il n'était pas un fichier ordinaire de 1 Mo au plus) pour `restaurer_attributs`."""
    info = os.path.join(depot, ".git", "info")
    if os.path.islink(info) or (os.path.lexists(info) and not os.path.isdir(info)):
        retirer(info)
    os.makedirs(info, exist_ok=True)
    chemin = os.path.join(info, "attributes")
    try:
        ancien = lire_octets(chemin, 1024 * 1024) if os.path.lexists(chemin) else None
    except Refus:
        ancien = None
    retirer(chemin)
    _creer(chemin, ATTRIBUTS_NEUTRES)
    return ancien


def restaurer_attributs(depot, ancien):
    chemin = os.path.join(depot, ".git", "info", "attributes")
    retirer(chemin)
    if ancien is not None:
        _creer(chemin, ancien)


def _creer(chemin, donnees):
    fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL | SANS_LIEN | getattr(os, "O_BINARY", 0), 0o644)
    try:
        ecrire_tout(fd, donnees)
    finally:
        os.close(fd)


def conclure(depot, d, env, sortie, erreurs, delai=DELAI_CONCLURE_S):
    """Commit des restes, puis le paquet <base>..agent/<tâche>. Rend (commits, branche ou None). Le dépôt est celui de l'agent :
    git y tourne avec SURETE_GIT et des attributs neutres, et le tout tient en `delai` secondes (au-delà :
    subprocess.TimeoutExpired, le reste est abandonné, l'appelant conclut sans paquet)."""
    limite = time.monotonic() + delai

    def reste_s():
        r = limite - time.monotonic()
        if r <= 0:
            raise subprocess.TimeoutExpired("git", delai)
        return r

    ref = f"refs/heads/agent/{d['tache']}"
    paquet = os.path.join(sortie, "resultat.bundle")
    retirer(paquet)
    gitdir = os.path.join(depot, ".git")
    if os.path.islink(gitdir) or not os.path.isdir(gitdir):
        erreurs.ecrire("entree-agent : /travail/projet/.git n'est plus un dossier : rien à rapporter\n")
        return 0, None
    reste_s()
    try:
        ancien, neutre = neutraliser_attributs(depot), True
    except OSError:                       # .git rendu non inscriptible : les commits seuls partent, aucun `add` sans filtre sûr
        ancien, neutre = None, False
    try:
        if git(depot, "rev-parse", "-q", "--verify", ref + "^{commit}", env=env, check=False, capture_output=True,
               timeout=reste_s()).returncode:
            erreurs.ecrire(f"entree-agent : la branche agent/{d['tache']} n'existe plus : rien à rapporter\n")
            return 0, None
        tete = git(depot, "symbolic-ref", "-q", "HEAD", env=env, check=False, capture_output=True,
                   timeout=reste_s()).stdout.decode("utf-8", "replace").strip()
        reste = b""
        if not neutre:                    # sans attributs neutres, même `git status` pourrait lancer un filtre de l'agent
            erreurs.ecrire("entree-agent : .git/info non inscriptible : travail non commité laissé de côté\n")
        else:
            reste = git(depot, "status", "--porcelain", "-z", "--untracked-files=all", "--ignore-submodules=all",
                        env=env, capture_output=True, timeout=reste_s()).stdout
        if reste:
            if tete != ref:
                erreurs.ecrire(f"entree-agent : travail non commité hors de agent/{d['tache']} : laissé de côté\n")
            else:
                git(depot, "add", "-A", env=env, capture_output=True, timeout=reste_s())
                git(depot, "-c", f"user.name={IDENTITE[0]}", "-c", f"user.email={IDENTITE[1]}", "commit", "-q",
                    "--no-verify", "--no-gpg-sign", "-m", MESSAGE_RESTES, env=env, capture_output=True, timeout=reste_s())
        if git(depot, "cat-file", "-e", d["base"] + "^{commit}", env=env, check=False, capture_output=True,
               timeout=reste_s()).returncode:
            erreurs.ecrire("entree-agent : la base n'est pas dans le dépôt : aucun paquet\n")
            return 0, None
        commits = int(sortie_git(depot, "rev-list", "--count", f"{d['base']}..{ref}", env=env, timeout=reste_s()) or 0)
        if commits == 0:
            return 0, None
        git(depot, "bundle", "create", "-q", paquet, f"{d['base']}..{ref}", env=env, capture_output=True, timeout=reste_s())
        return commits, f"agent/{d['tache']}"
    finally:
        if neutre:
            try:
                restaurer_attributs(depot, ancien)
            except OSError:
                pass


# ------------------------------------------------------------------------------------------------------------- sorties

def retirer(chemin):
    """Retire un fichier ou un lien laissé par l'agent à la place d'une de nos sorties (jamais suivi)."""
    try:
        if os.path.islink(chemin) or not os.path.isdir(chemin):
            os.unlink(chemin)
        else:
            import shutil
            shutil.rmtree(chemin)
    except FileNotFoundError:
        pass


def ouvrir_sortie(chemin):
    retirer(chemin)
    return os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | SANS_LIEN | getattr(os, "O_BINARY", 0), 0o600)


def ecrire_tout(fd, donnees):
    vue = memoryview(donnees)
    while vue:
        n = os.write(fd, vue)
        vue = vue[n:]


class Borne:
    """Un fichier de sortie borné à `limite` octets ; `depasse` est appelé (une fois) au premier octet en trop."""

    def __init__(self, chemin, limite, depasse=None):
        self.fd, self.limite, self.ecrits, self.depasse, self.coupe = ouvrir_sortie(chemin), limite, 0, depasse, False
        self.verrou = threading.Lock()

    def ecrire(self, donnees):
        if isinstance(donnees, str):
            donnees = donnees.encode("utf-8", "replace")
        with self.verrou:
            reste = self.limite - self.ecrits
            if reste > 0:
                part = donnees[:reste]
                ecrire_tout(self.fd, part)
                self.ecrits += len(part)
            if len(donnees) > max(reste, 0) and not self.coupe:
                self.coupe = True
                if self.depasse:
                    self.depasse()

    def fermer(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def pomper(source, borne):
    try:
        while True:
            bloc = source.read1(65536) if hasattr(source, "read1") else source.read(65536)
            if not bloc:
                break
            borne.ecrire(bloc)
    except (OSError, ValueError):
        pass


def ecrire_fin(sortie, fin):
    chemin = os.path.join(sortie, "fin.json")
    tmp = os.path.join(sortie, ".fin.json.tmp")
    fd = ouvrir_sortie(tmp)
    try:
        ecrire_tout(fd, (json.dumps(fin, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    retirer(chemin)
    os.replace(tmp, chemin)


# ------------------------------------------------------------------------------------------------------------- claude

def commande_claude():
    brut = os.environ.get("AGENT_CLAUDE")
    if not brut:
        return ["claude"]
    prog = json.loads(brut)
    if not isinstance(prog, list) or not prog or not all(isinstance(x, str) and x for x in prog):
        raise Refus("AGENT_CLAUDE mal formé")
    return prog


def tuer_groupe(proc):
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass


def tuer_les_restes():
    """Dans le conteneur (PID 1) : tout processus laissé par claude (démon, tâche de fond) est tué avant que entree-agent
    n'écrive le paquet et fin.json ; kill(-1) épargne le processus appelant et le PID 1. Les zombies sont ensuite récoltés."""
    if os.getpid() == 1:
        try:
            os.kill(-1, signal.SIGKILL)
        except OSError:
            pass
        recolter_orphelins(None)


def recolter_orphelins(epargne):
    """PID 1 seulement : récolte les processus orphelins terminés (reparentés au PID 1), qui sinon resteraient zombies et
    useraient --pids-limit. `epargne` (le PID de claude) n'est jamais récolté ici : subprocess garde son code de retour. Le
    prochain enfant terminé est d'abord regardé sans être récolté (WNOWAIT)."""
    if os.getpid() != 1 or not hasattr(os, "waitid"):
        return
    while True:
        try:
            info = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return
        if info is None or info.si_pid == epargne:
            return
        try:
            os.waitpid(info.si_pid, os.WNOHANG)
        except ChildProcessError:
            return


def echeance_interne(duree_s):
    """Secondes après lesquelles l'entrée arrête claude pour conclure : 120 s avant l'échéance du veilleur, ou à mi-chemin
    pour une tâche de moins de 240 s (au moins 1 s)."""
    return max(duree_s - MARGE_ECHEANCE_S, (duree_s + 1) // 2, 1)


# SIGTERM / SIGINT : seul le groupe de claude est tué ; `principal` conclut ensuite (jamais de sortie immédiate du
# processus ni de signal ignoré).
SIGNAL = {"proc": None, "recu": False}


def signal_recu(_numero, _cadre):
    SIGNAL["recu"] = True
    if SIGNAL["proc"] is not None:
        tuer_groupe(SIGNAL["proc"])


def lancer_claude(c, options, d, jeton, depot, erreurs):
    """Lance claude ; rend (code, echeance) : code 128 + signal s'il a été tué, non nul si le flux a été coupé, l'échéance
    interne atteinte ou un signal reçu ; echeance vrai si l'échéance interne l'a arrêté."""
    if SIGNAL["recu"]:
        raise Refus("arrêt demandé avant le lancement de claude")
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": c["maison"], "LANG": "C.UTF-8",
           "BASH_DEFAULT_TIMEOUT_MS": "1800000", "BASH_MAX_TIMEOUT_MS": "1800000", "DISABLE_AUTOUPDATER": "1",
           "CLAUDE_CODE_OAUTH_TOKEN": jeton}
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    flux = Borne(os.path.join(c["sortie"], "flux.jsonl"), d["flux_octets"],
                 depasse=lambda: SIGNAL["proc"] is not None and tuer_groupe(SIGNAL["proc"]))
    try:
        message = os.open(os.path.join(c["entree"], "message.md"), os.O_RDONLY | SANS_LIEN | getattr(os, "O_BINARY", 0))
    except OSError:
        flux.fermer()
        raise Refus("message.md absent ou illisible")
    try:
        proc = subprocess.Popen(commande_claude() + options, cwd=depot, env=env, stdin=message, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, **({"start_new_session": True} if os.name == "posix" else {}))
    finally:
        os.close(message)
    SIGNAL["proc"] = proc
    if SIGNAL["recu"]:                      # signal arrivé entre la vérification et Popen
        tuer_groupe(proc)
    fils = [threading.Thread(target=pomper, args=(proc.stdout, flux), daemon=True),
            threading.Thread(target=pomper, args=(proc.stderr, erreurs), daemon=True)]
    for f in fils:
        f.start()
    echeance = False
    limite = time.monotonic() + echeance_interne(d["duree_s"])
    while proc.poll() is None:
        if time.monotonic() >= limite:
            echeance = True
            tuer_groupe(proc)
            proc.wait()
            break
        recolter_orphelins(proc.pid)
        time.sleep(0.2)
    SIGNAL["proc"] = None
    tuer_groupe(proc)                       # les petits-enfants qui tiendraient encore les tuyaux
    for f in fils:
        f.join(timeout=10)
    flux.fermer()
    code = proc.returncode
    if code < 0:
        code = 128 - code
    if flux.coupe:
        erreurs.ecrire(f"\nentree-agent : flux coupé à {d['flux_octets']} octets : claude arrêté\n")
        code = code or 1
    if echeance:
        erreurs.ecrire(f"\nentree-agent : échéance interne ({echeance_interne(d['duree_s'])} s) : claude arrêté, "
                       "travail conclu\n")
        code = code or 1
    if SIGNAL["recu"]:
        erreurs.ecrire("\nentree-agent : signal d'arrêt reçu : claude arrêté, travail conclu\n")
        code = code or 143
    return code, echeance


def nettoyer_sortie(sortie, garder):
    """Retire de /sortie tout ce qui n'est pas l'une de nos sorties (`garder`, fichiers ordinaires seulement) : rien de ce que
    l'agent y a déposé (faux paquet, faux fin.json, autre fichier, lien, dossier) ne reste."""
    try:
        noms = os.listdir(sortie)
    except OSError:
        return
    for nom in noms:
        chemin = os.path.join(sortie, nom)
        if nom in garder and not os.path.islink(chemin) and os.path.isfile(chemin):
            continue
        try:
            retirer(chemin)
        except OSError:
            pass


def principal():
    c = chemins()
    signal.signal(signal.SIGTERM, signal_recu)
    signal.signal(signal.SIGINT, signal_recu)
    erreurs = Borne(os.path.join(c["sortie"], "claude.err"), LIMITE_ERREURS)
    d = depot = None
    code, commits, branche, echeance = 1, 0, None, False
    env = env_git(c["maison"])
    try:
        d = valider_demande(lire_json(os.path.join(c["entree"], "demande.json")))
        d["duree_s"] = duree_hote(d["duree_s"])           # celle de l'enveloppe fait foi (même échéance que le veilleur)
        options = valider_argv(lire_json(os.path.join(c["entree"], "argv.json"))) + ["--max-turns", str(d["tours"])]
        jeton = lire_jeton(c["jeton"])
        depot = preparer_depot(c, d, env)
        code, echeance = lancer_claude(c, options, d, jeton, depot, erreurs)
        jeton = None
    except Refus as e:
        erreurs.ecrire(f"entree-agent : refusé : {e}\n")
        code = 2
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        erreurs.ecrire(f"entree-agent : {type(e).__name__} : {str(e)[:300]}\n")
        code = 1
    tuer_les_restes()
    if d is not None and depot is not None and os.path.isdir(depot):
        try:
            commits, branche = conclure(depot, d, env, c["sortie"], erreurs)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            erreurs.ecrire(f"entree-agent : paquet impossible : {type(e).__name__}\n")
            commits, branche = 0, None
            code = code or 1
    tuer_les_restes()
    erreurs.fermer()
    # Seules nos sorties restent ; le paquet seulement s'il vient d'être créé ici (sinon tout resultat.bundle part).
    nettoyer_sortie(c["sortie"], {"flux.jsonl", "claude.err"} | ({"resultat.bundle"} if branche else set()))
    fin = {"code": code, "commits": commits, "branche": branche, "base": d["base"] if d else None}
    if echeance:
        fin["echeance"] = True
    ecrire_fin(c["sortie"], fin)
    return 0


# ------------------------------------------------------------------------------------------------------------- contrôle

def lire_ref(depot, ref):
    """Le SHA d'une référence lue dans les fichiers du dépôt (référence libre puis packed-refs), sans lancer git dessus."""
    gitdir = os.path.join(depot, ".git")
    try:
        texte = lire_octets(os.path.join(gitdir, *ref.split("/")), 200).decode("ascii", "replace").strip()
        if MOTIF_BASE.fullmatch(texte):
            return texte
    except Refus:
        pass
    try:
        for ligne in lire_octets(os.path.join(gitdir, "packed-refs"), 64 * 1024 * 1024).decode("utf-8", "replace").splitlines():
            parties = ligne.split()
            if len(parties) == 2 and parties[1] == ref and MOTIF_BASE.fullmatch(parties[0]):
                return parties[0]
    except Refus:
        pass
    return None


def objets(propre, env):
    """Tous les objets du dépôt propre : ceux des paquets (git show-index) et les objets libres."""
    vus = []
    dossier = os.path.join(propre, "objects")
    paquets = os.path.join(dossier, "pack")
    for nom in sorted(os.listdir(paquets)) if os.path.isdir(paquets) else []:
        if nom.endswith(".idx"):
            with open(os.path.join(paquets, nom), "rb") as idx:
                r = subprocess.run(["git", "-C", propre, "show-index"], stdin=idx, env=env, capture_output=True, check=True)
            for ligne in r.stdout.decode("ascii", "replace").splitlines():
                parties = ligne.split()
                if len(parties) >= 2 and MOTIF_BASE.fullmatch(parties[1]):
                    vus.append(parties[1])
    for sous in sorted(os.listdir(dossier)):
        if re.fullmatch(r"[0-9a-f]{2}", sous):
            for nom in sorted(os.listdir(os.path.join(dossier, sous))):
                if re.fullmatch(r"[0-9a-f]{38}", nom):
                    vus.append(sous + nom)
    return vus


def verifier():
    c = chemins()
    try:
        d = valider_demande(lire_json(os.path.join(c["entree"], "demande.json")))
        sys.stdout.flush()
        with tempfile.TemporaryDirectory(prefix="verif-", ignore_cleanup_errors=True) as tmp:
            env = env_git(tmp)
            propre = os.path.join(tmp, "propre.git")
            subprocess.run(["git", "init", "-q", "--bare", propre], env=env, stdin=subprocess.DEVNULL, check=True,
                           stdout=subprocess.DEVNULL)
            reserve = os.path.join(c["depot"], ".git", "objects")
            if os.path.isdir(reserve):
                with open(os.path.join(propre, "objects", "info", "alternates"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(os.path.abspath(reserve).replace(os.sep, "/") + "\n")
            sha = lire_ref(c["depot"], f"refs/heads/agent/{d['tache']}") if os.path.isdir(c["depot"]) else None
            if sha and sha != d["base"]:
                subprocess.run(["git", "-C", propre, "-c", "log.showSignature=false", "-c", "i18n.logOutputEncoding=UTF-8",
                                "--no-pager", "log", "-p", "--no-textconv", "--no-ext-diff", "--text", "-m", "--no-renames",
                                "--no-color", "--pretty=raw", "--no-abbrev", f"{d['base']}..{sha}"],
                               env=env, stdin=subprocess.DEVNULL, check=True)
            paquet = os.path.join(c["sortie"], "resultat.bundle")
            if os.path.lexists(paquet):
                if os.path.islink(paquet) or not os.path.isfile(paquet):
                    raise Refus("resultat.bundle n'est pas un fichier ordinaire")
                subprocess.run(["git", "-C", propre, "bundle", "unbundle", paquet], env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, check=True)
                liste = objets(propre, env)
                if not liste:
                    raise Refus("paquet sans objet lisible")
                sys.stdout.flush()
                subprocess.run(["git", "-C", propre, "cat-file", "--batch"], input=("\n".join(liste) + "\n").encode("ascii"),
                               env=env, check=True)
        return 0
    except (Refus, OSError, ValueError, subprocess.SubprocessError) as e:
        sys.stderr.write(f"entree-agent --verifier : contrôle impossible : {type(e).__name__} : {str(e)[:200]}\n")
        return 3


if __name__ == "__main__":
    if sys.argv[1:] == ["--verifier"]:
        sys.exit(verifier())
    if sys.argv[1:]:
        sys.stderr.write("usage : entree-agent | entree-agent --verifier\n")
        sys.exit(2)
    sys.exit(principal())
