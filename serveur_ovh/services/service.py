#!/usr/bin/env python3
"""Service permanent d'un projet sur le serveur (hôte, Python 3 de la distribution, bibliothèque standard seulement).

Conception : docs/superpowers/specs/2026-11-25-service-permanent-serveur-design.md ; guide : docs/serveur-services.md.
Le poste dépose ce fichier dans ~/myiafactory/serveur_ovh/services/service.py, puis l'appelle par SSH :

  service.py recevoir <projet> <commit>      stdin : archive tar des sources du commit (git archive) ; liens refusés
  service.py poser-variables <projet>        stdin : {"NOM": "valeur"} (valeurs non secrètes)
  service.py poser-secrets <projet>          stdin : {"NOM": "valeur"} (saisis par le Directeur) ; rend les NOMS seuls
  service.py deployer <projet> <commit>      construit, démarre, contrôle la santé et le jeton, bascule ou revient en arrière
  service.py mettre-a-jour <projet> <commit> même chose (nom de la commande du bureau)
  service.py etat <projet>                   état (sans secret ni jeton)
  service.py journal <projet> [--lignes N]   200 dernières lignes au plus, secrets et jeton masqués
  service.py redemarrer|arreter|supprimer <projet>
  service.py jeton <projet>                  la SEULE commande qui rend le jeton (pour le coffre du poste)
  Option commune : --simuler (aucune commande docker, ufw ni sudo ; aucun fichier écrit ; le plan est rendu).

Sortie standard : UN SEUL objet JSON {"commande", "projet", "statut", "detail", ...}, masqué (secrets et jeton).
Codes : 0 réussi ; 1 échec (avec ou sans retour arrière) ; 2 usage ou refus (déclaration, archive, secret manquant) ;
75 un déploiement de ce projet est déjà en cours.

Tout ce qui vient du projet (déclaration, archive) est une donnée hostile : validée avant usage, jamais passée à un shell
(les commandes sont des tableaux). Le jeton et les secrets ne sont écrits que dans des fichiers 0600 du dossier du service
(`jeton`, `secrets.json`, `env`) et passés au conteneur par `--env-file` : jamais en argument, jamais dans un journal.
"""
import json
import os
import re
import secrets as _hasard
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Constantes (la plage de ports et les limites ne sont jamais lues de la déclaration) ---------------------------------

PORT_MIN, PORT_MAX = 18000, 18999
MEMOIRE_MO = 1024
CPUS = "1"
PROCESSUS = 256
TMP_MO = 256
DELAI_SANTE_S = 120          # le service a ce délai pour répondre 200 à /sante après son démarrage
PAS_SANTE_S = 2
DELAI_CONSTRUCTION_S = 1800
DELAI_DOCKER_S = 120
DELAI_ARRET_S = 20
DECLARATION_MAX = 16 * 1024
ENTREE_MAX = 64 * 1024        # variables et secrets
ARCHIVE_MAX = 500 * 1024 * 1024
MEMBRES_MAX = 20000
LIGNES_MAX = 200
LIGNE_MAX = 500
VALEUR_MAX = 4096
NOMS_MAX = 32
MASQUE = "***masqué***"

MOTIF_PROJET = re.compile(r"[a-z][a-z0-9-]{1,39}", re.ASCII)
MOTIF_COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)
MOTIF_NOM = re.compile(r"[a-z][a-z0-9-]{1,39}", re.ASCII)
MOTIF_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,99}", re.ASCII)
MOTIF_SANTE = re.compile(r"/[a-z0-9_-]{1,40}(/[a-z0-9_-]{1,40}){0,3}", re.ASCII)
MOTIF_VARIABLE = re.compile(r"[A-Z][A-Z0-9_]{0,63}", re.ASCII)
# Image : dépôt en minuscules, ÉPINGLÉE par empreinte (jamais une étiquette flottante).
MOTIF_IMAGE = re.compile(r"[a-z0-9]+([._-][a-z0-9]+)*(\.[a-z0-9-]+)*(:[0-9]{1,5})?(/[a-z0-9]+([._-][a-z0-9]+)*){0,4}"
                         r"(:[A-Za-z0-9_][A-Za-z0-9._-]{0,63})?@sha256:[0-9a-f]{64}", re.ASCII)
CLES = frozenset({"nom", "image", "dockerfile", "port_interne", "sante", "donnees", "variables", "secrets"})
RESERVEES = frozenset({"PATH", "HOME", "USER", "HOSTNAME", "SHELL", "PWD", "TERM", "LANG", "TZ"})
PREFIXES_RESERVES = ("SERVICE_", "MYIAFACTORY_", "LD_", "DOCKER_", "PYTHON", "NODE_OPTIONS", "JAVA_TOOL_OPTIONS")
DONNEES = "/data"
COMMANDES = ("recevoir", "poser-variables", "poser-secrets", "deployer", "mettre-a-jour", "etat", "journal",
             "redemarrer", "arreter", "supprimer", "jeton")
AVEC_COMMIT = ("recevoir", "deployer", "mettre-a-jour")
OCCUPE = 75


class Refus(ValueError):
    """Une donnée refusée (déclaration, archive, argument, secret manquant) : code 2."""


class Echec(RuntimeError):
    """Une étape a échoué (docker, santé, plage pleine) : code 1."""


def maintenant_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def nom_conteneur(projet):
    return f"svc-{projet}"


def nom_image(projet, commit):
    return f"myiafactory-service-{projet}:{commit[:12]}"


# --- Validation de la déclaration (.factory/service.json) --------------------------------------------------------------

def _sans_doublon(paires):
    vu = {}
    for cle, valeur in paires:
        if cle in vu:
            raise Refus(f"Clé JSON en double : {cle[:40]!r}.")
        vu[cle] = valeur
    return vu


def lire_json(brut, maximum, quoi):
    if not isinstance(brut, (bytes, bytearray)) or len(brut) > maximum:
        raise Refus(f"{quoi} : absent ou plus de {maximum} octets.")
    try:
        return json.loads(bytes(brut).decode("utf-8"), object_pairs_hook=_sans_doublon)
    except Refus:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise Refus(f"{quoi} : JSON UTF-8 invalide.") from None


def _noms(valeur, quoi):
    if valeur is None:
        return []
    if not isinstance(valeur, list) or len(valeur) > NOMS_MAX:
        raise Refus(f"« {quoi} » : une liste de {NOMS_MAX} noms au plus est attendue.")
    for n in valeur:
        if not isinstance(n, str) or not MOTIF_VARIABLE.fullmatch(n):
            raise Refus(f"« {quoi} » : nom refusé ({str(n)[:40]!r}) : majuscules, chiffres et _, 64 caractères au plus.")
        if n in RESERVEES or n.startswith(PREFIXES_RESERVES):
            raise Refus(f"« {quoi} » : le nom {n} est réservé à la plateforme ou au système.")
    if len(set(valeur)) != len(valeur):
        raise Refus(f"« {quoi} » : nom en double.")
    return list(valeur)


def _chemin_relatif(valeur):
    if not isinstance(valeur, str) or not 0 < len(valeur) <= 200:
        raise Refus("« dockerfile » : chemin relatif de 200 caractères au plus attendu.")
    segments = valeur.split("/")
    for s in segments:
        if not MOTIF_SEGMENT.fullmatch(s) or s in (".", ".."):
            raise Refus(f"« dockerfile » : segment refusé ({s[:40]!r}) : lettres, chiffres, . _ -, sans « .. » ni "
                        "segment caché.")
    return valeur


def valider_declaration(brut):
    """La déclaration validée (dict) ; `Refus` au moindre écart. Rien d'autre que les clés connues n'est lu."""
    d = lire_json(brut, DECLARATION_MAX, ".factory/service.json")
    if not isinstance(d, dict):
        raise Refus(".factory/service.json : un objet JSON est attendu.")
    inconnues = sorted(set(d) - CLES)
    if inconnues:
        raise Refus("Clé(s) inconnue(s) dans .factory/service.json : " + ", ".join(k[:40] for k in inconnues[:5]))
    nom = d.get("nom")
    if not isinstance(nom, str) or not MOTIF_NOM.fullmatch(nom):
        raise Refus("« nom » : minuscules, chiffres et -, 2 à 40 caractères, commence par une lettre.")
    if ("image" in d) == ("dockerfile" in d):
        raise Refus("Exactement une source est attendue : « image » (épinglée par @sha256) ou « dockerfile ».")
    sortie = {"nom": nom}
    if "image" in d:
        if not isinstance(d["image"], str) or len(d["image"]) > 255 or not MOTIF_IMAGE.fullmatch(d["image"]):
            raise Refus("« image » : référence refusée ; elle doit être épinglée par empreinte (…@sha256:<64 hex>).")
        sortie["image"] = d["image"]
    else:
        sortie["dockerfile"] = _chemin_relatif(d["dockerfile"])
    port = d.get("port_interne")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise Refus("« port_interne » : un entier de 1024 à 65535 (le service tourne sans privilège).")
    sortie["port_interne"] = port
    sante = d.get("sante", "/sante")
    if not isinstance(sante, str) or not MOTIF_SANTE.fullmatch(sante):
        raise Refus("« sante » : un chemin comme /sante (minuscules, chiffres, _ -).")
    sortie["sante"] = sante
    if d.get("donnees", DONNEES) != DONNEES:
        raise Refus("« donnees » : seul /data est permis (le volume du service).")
    sortie["donnees"] = DONNEES
    sortie["variables"] = _noms(d.get("variables"), "variables")
    sortie["secrets"] = _noms(d.get("secrets"), "secrets")
    if set(sortie["variables"]) & set(sortie["secrets"]):
        raise Refus("Un même nom ne peut pas être à la fois variable et secret.")
    return sortie


def valider_valeurs(brut, quoi):
    d = lire_json(brut, ENTREE_MAX, quoi)
    if not isinstance(d, dict) or len(d) > NOMS_MAX:
        raise Refus(f"{quoi} : un objet {{NOM: valeur}} de {NOMS_MAX} entrées au plus est attendu.")
    _noms(list(d), quoi)
    for n, v in d.items():
        if not isinstance(v, str) or len(v) > VALEUR_MAX or any(c in v for c in "\r\n\x00"):
            raise Refus(f"{quoi} : valeur de {n} refusée (texte d'une ligne, {VALEUR_MAX} caractères au plus).")
    return d


# --- Fichiers du service ------------------------------------------------------------------------------------------------

class Verrou:
    """Verrou exclusif non bloquant sur un fichier (flock sur l'hôte ; repli msvcrt pour les tests sous Windows)."""

    def __init__(self, chemin, attendre=False):
        self.chemin, self.attendre, self.f = Path(chemin), attendre, None

    def __enter__(self):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.chemin, "a+b")
        try:
            try:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX if self.attendre else fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK if self.attendre else msvcrt.LK_NBLCK, 1)
        except OSError:
            self.f.close()
            self.f = None
            raise BlockingIOError("verrou tenu") from None
        return self

    def __exit__(self, *_):
        if self.f:
            try:
                try:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
                except ImportError:
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self.f.close()


def ecrire_prive(chemin, texte):
    """Écrit `texte` dans un fichier 0600 (temporaire créé 0600 puis renommé : jamais lisible par d'autres)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
    try:
        tmp.unlink()
    except OSError:
        pass
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(texte.encode("utf-8"))
        os.chmod(tmp, 0o600)
        os.replace(tmp, chemin)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def lire_fichier_sur(chemin, maximum):
    """Octets d'un fichier ordinaire (jamais un lien) d'au plus `maximum` octets ; None s'il manque."""
    chemin = Path(chemin)
    try:
        if chemin.is_symlink() or not chemin.is_file():
            return None
        with open(chemin, "rb") as f:
            brut = f.read(maximum + 1)
    except OSError:
        return None
    if len(brut) > maximum:
        raise Refus(f"{chemin.name} : plus de {maximum} octets.")
    return brut


def lire_json_local(chemin, defaut):
    try:
        brut = lire_fichier_sur(chemin, 1024 * 1024)
        return defaut if brut is None else json.loads(brut.decode("utf-8"))
    except (Refus, ValueError, UnicodeError):
        return defaut


class Service:
    def __init__(self, racine, projet):
        self.racine = Path(racine)
        self.projet = projet
        self.dossier = self.racine / projet

    def chemin(self, nom):
        return self.dossier / nom

    def sources(self, commit):
        return self.dossier / "sources" / commit

    def etat(self):
        e = lire_json_local(self.chemin("etat.json"), {})
        return e if isinstance(e, dict) else {}

    def ecrire_etat(self, etat):
        etat = dict(etat, projet=self.projet, maj=maintenant_iso())
        self.dossier.mkdir(parents=True, exist_ok=True)
        tmp = self.chemin(f".etat.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(etat, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, self.chemin("etat.json"))

    def secrets(self):
        s = lire_json_local(self.chemin("secrets.json"), {})
        return s if isinstance(s, dict) else {}

    def variables(self):
        v = lire_json_local(self.chemin("variables.json"), {})
        return v if isinstance(v, dict) else {}

    def jeton(self):
        brut = lire_fichier_sur(self.chemin("jeton"), 1024)
        j = brut.decode("ascii", "replace").strip() if brut else ""
        return j if re.fullmatch(r"[A-Za-z0-9_-]{40,128}", j) else ""

    def valeurs_a_masquer(self):
        vals = [str(v) for v in self.secrets().values()] + [self.jeton()]
        return sorted({v for v in vals if len(v) >= 4}, key=len, reverse=True)


# --- Ports --------------------------------------------------------------------------------------------------------------

def _ports(racine):
    p = lire_json_local(Path(racine) / "ports.json", {})
    return p if isinstance(p, dict) else {}


def port_du_projet(racine, projet):
    """Le port attribué, s'il est dans la plage ; None sinon (jamais une règle de pare-feu hors plage)."""
    p = _ports(racine).get(projet)
    return p if isinstance(p, int) and not isinstance(p, bool) and PORT_MIN <= p <= PORT_MAX else None


def attribuer_port(racine, projet, ecrire=True):
    """Le port du projet (déjà attribué, sinon le premier libre de la plage, mémorisé dans ports.json sous verrou).
    `ecrire=False` (simulation) : rien n'est écrit, pas même le verrou."""
    import contextlib
    with (Verrou(Path(racine) / ".ports.lock", attendre=True) if ecrire else contextlib.nullcontext()):
        ports = _ports(racine)
        deja = port_du_projet(racine, projet)
        if deja:
            return deja
        pris = {v for v in ports.values() if isinstance(v, int)}
        for p in range(PORT_MIN, PORT_MAX + 1):
            if p not in pris:
                if ecrire:
                    ports[projet] = p
                    tmp = Path(racine) / f".ports.{os.getpid()}.tmp"
                    tmp.write_text(json.dumps(ports, indent=1), "utf-8")
                    os.replace(tmp, Path(racine) / "ports.json")
                return p
    raise Echec(f"Plus aucun port libre dans la plage {PORT_MIN}-{PORT_MAX}.")


def liberer_port(racine, projet):
    with Verrou(Path(racine) / ".ports.lock", attendre=True):
        ports = _ports(racine)
        if ports.pop(projet, None) is not None:
            tmp = Path(racine) / f".ports.{os.getpid()}.tmp"
            tmp.write_text(json.dumps(ports, indent=1), "utf-8")
            os.replace(tmp, Path(racine) / "ports.json")


# --- Archive des sources ------------------------------------------------------------------------------------------------

def extraire_sources(brut, destination):
    """Extrait l'archive tar (octets) dans `destination` (créée) : fichiers ordinaires et dossiers seulement, noms
    relatifs sans « .. », droits 0644/0755, tailles bornées. `Refus` au premier membre douteux (rien n'est gardé)."""
    import io
    if len(brut) > ARCHIVE_MAX:
        raise Refus("Archive des sources trop grosse.")
    try:
        tar = tarfile.open(fileobj=io.BytesIO(brut), mode="r:")
        membres = tar.getmembers()
    except (tarfile.TarError, EOFError, OSError):
        raise Refus("Archive des sources illisible (tar attendu).") from None
    if len(membres) > MEMBRES_MAX:
        raise Refus("Archive des sources : trop de fichiers.")
    destination = Path(destination)
    tmp = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        for m in membres:
            nom = m.name.rstrip("/")
            if m.type == tarfile.XGLTYPE or nom in ("", ".", "pax_global_header"):
                continue
            segments = nom.split("/")
            if (nom.startswith("/") or "\\" in nom or ":" in nom or "\x00" in nom
                    or any(s in ("", ".", "..") for s in segments)):
                raise Refus(f"Archive des sources : chemin refusé ({nom[:80]!r}).")
            cible = tmp.joinpath(*segments)
            if m.isdir():
                cible.mkdir(parents=True, exist_ok=True)
                os.chmod(cible, 0o755)
            elif m.isreg():
                cible.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(m)
                with open(cible, "wb") as sortie:
                    shutil.copyfileobj(f, sortie)
                os.chmod(cible, 0o755 if m.mode & 0o100 else 0o644)
            else:
                raise Refus(f"Archive des sources : membre refusé (lien ou fichier spécial : {nom[:80]!r}).")
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, destination)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def declaration_des_sources(service, commit):
    racine = service.sources(commit)
    if not racine.is_dir() or racine.is_symlink():
        raise Refus(f"Sources du commit {commit[:12]} absentes sur le serveur : à recevoir d'abord.")
    f = racine / ".factory" / "service.json"
    for p in (racine / ".factory", f):
        if p.is_symlink():
            raise Refus(".factory/service.json : lien refusé.")
    brut = lire_fichier_sur(f, DECLARATION_MAX)
    if brut is None:
        raise Refus("Le projet n'a pas de .factory/service.json à ce commit.")
    return valider_declaration(brut)


# --- L'hôte : docker, ufw, sonde HTTP -----------------------------------------------------------------------------------

class Hote:
    """Exécute les commandes (tableaux, jamais de shell), sonde le service en HTTP sur 127.0.0.1."""

    def lancer(self, argv, delai=DELAI_DOCKER_S, entree=None):
        try:
            r = subprocess.run(list(argv), input=entree, capture_output=True, timeout=delai,
                               stdin=None if entree is not None else subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return 124, "", f"délai de {delai} s dépassé"
        except OSError as e:
            return 127, "", type(e).__name__
        return (r.returncode, r.stdout.decode("utf-8", "replace") if r.stdout else "",
                r.stderr.decode("utf-8", "replace") if r.stderr else "")

    def http(self, url, jeton=None, delai=3):
        requete = urllib.request.Request(url, method="GET")
        if jeton:
            requete.add_header("Authorization", f"Bearer {jeton}")
        try:
            with urllib.request.urlopen(requete, timeout=delai) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def dormir(self, s):
        time.sleep(s)


class Simulation:
    """Ne lance rien : note le plan. Le conteneur est supposé absent, toute commande réussie."""

    def __init__(self):
        self.plan = []

    def lancer(self, argv, delai=DELAI_DOCKER_S, entree=None):
        self.plan.append(list(argv))
        if len(argv) > 3 and argv[3] == "inspect":
            return 1, "", "Error: No such object"
        return 0, "", ""

    def http(self, url, jeton=None, delai=3):
        return 200 if (jeton or url.endswith("/sante")) else 401

    def dormir(self, s):
        pass


def docker(hote, *args, delai=DELAI_DOCKER_S):
    return hote.lancer(["sudo", "-n", "docker", *args], delai=delai)


def ufw(hote, *args):
    return hote.lancer(["sudo", "-n", "ufw", *args], delai=60)


def inspecter(hote, nom):
    """(existe, en_marche, image) ; Echec si docker ne répond pas nettement."""
    code, sortie, erreur = docker(hote, "inspect", "-f", "{{.State.Running}} {{.Config.Image}}", nom)
    if code != 0:
        if re.search(r"no such (object|container)|not found", erreur, re.IGNORECASE):
            return False, False, None
        raise Echec(f"docker inspect {nom} : pas de réponse nette (code {code}).")
    m = re.fullmatch(r"(true|false) (\S+)", sortie.strip())
    if not m:
        raise Echec(f"docker inspect {nom} : réponse illisible.")
    return True, m.group(1) == "true", m.group(2)


def ouvrir_port(hote, port):
    if not (isinstance(port, int) and PORT_MIN <= port <= PORT_MAX):
        raise Echec("Port hors de la plage réservée : aucune règle de pare-feu touchée.")
    code, _o, e = ufw(hote, "allow", f"{port}/tcp")
    if code != 0:
        raise Echec(f"ufw allow {port}/tcp : échec (code {code}).")


def fermer_port(hote, port):
    if isinstance(port, int) and PORT_MIN <= port <= PORT_MAX:
        ufw(hote, "delete", "allow", f"{port}/tcp")


def argv_run(projet, image, port, declaration, uid, gid, racine):
    service = Service(racine, projet)
    return ["run", "-d", "--name", nom_conteneur(projet),
            "--restart", "unless-stopped",
            "--read-only", "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={TMP_MO}m",
            "-v", f"{service.chemin('data')}:{DONNEES}:rw",
            "--user", f"{uid}:{gid}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", f"{MEMOIRE_MO}m", "--memory-swap", f"{MEMOIRE_MO}m", "--cpus", CPUS,
            "--pids-limit", str(PROCESSUS),
            "--log-opt", "max-size=10m", "--log-opt", "max-file=3",
            "--label", f"myiafactory.service={projet}",
            "--env-file", str(service.chemin("env")),
            "-p", f"{port}:{declaration['port_interne']}",
            image]


def attendre_sante(hote, port, declaration, jeton):
    """None si le service répond 200 à sa santé ET refuse une requête sans jeton (401/403) ; sinon la raison."""
    base = f"http://127.0.0.1:{port}"
    debut = time.monotonic()
    tours = max(1, DELAI_SANTE_S // PAS_SANTE_S)
    code = None
    for _ in range(tours):
        code = hote.http(base + declaration["sante"], delai=3)
        if code == 200:
            break
        hote.dormir(PAS_SANTE_S)
        if time.monotonic() - debut > DELAI_SANTE_S:
            break
    if code != 200:
        return f"santé {declaration['sante']} sans réponse 200 en {DELAI_SANTE_S} s (dernier code : {code})"
    sans = hote.http(base + "/", delai=3)
    if sans not in (401, 403):
        return (f"le service ne demande pas le jeton : « / » sans Authorization rend {sans} (401 ou 403 attendu, "
                "seule la santé est publique)")
    avec = hote.http(base + declaration["sante"], jeton=jeton, delai=3)
    if avec != 200:
        return f"santé avec jeton : code {avec}"
    return None


# --- Commandes ----------------------------------------------------------------------------------------------------------

def _env(service, declaration, jeton):
    secrets, variables = service.secrets(), service.variables()
    manquants = [n for n in declaration["secrets"] if n not in secrets]
    if manquants:
        raise Refus("Secret(s) non posé(s) : " + ", ".join(manquants) + " : le Directeur doit les saisir au bureau "
                    "(zone Services) avant le déploiement.")
    lignes = [f"SERVICE_JETON={jeton}", f"SERVICE_PORT={declaration['port_interne']}", f"SERVICE_DONNEES={DONNEES}"]
    lignes += [f"{n}={variables[n]}" for n in declaration["variables"] if n in variables]
    lignes += [f"{n}={secrets[n]}" for n in declaration["secrets"]]
    return "\n".join(lignes) + "\n"


def cmd_recevoir(service, commit, entree, hote, simuler, **_):
    brut = entree.read(ARCHIVE_MAX + 1)
    if simuler:
        return 0, {"statut": "simule", "detail": f"{len(brut)} octets reçus, rien d'extrait."}
    extraire_sources(brut, service.sources(commit))
    declaration = declaration_des_sources(service, commit)
    return 0, {"statut": "ok", "detail": f"Sources du commit {commit[:12]} reçues.", "declaration": declaration}


def cmd_poser(service, entree, simuler, fichier, quoi, **_):
    """Ajoute ou remplace les valeurs reçues ; celles déjà posées et non reprises sont gardées. Ne rend que les NOMS."""
    valeurs = valider_valeurs(entree.read(ENTREE_MAX + 1), quoi)
    deja = lire_json_local(service.chemin(fichier), {})
    tout = dict(deja if isinstance(deja, dict) else {}, **valeurs)
    if len(tout) > NOMS_MAX:
        raise Refus(f"{quoi} : {NOMS_MAX} au plus.")
    if not simuler:
        ecrire_prive(service.chemin(fichier), json.dumps(tout, ensure_ascii=False))
    return 0, {"statut": "simule" if simuler else "ok", "detail": f"{len(valeurs)} {quoi} posé(s).",
               quoi: sorted(tout)}


def cmd_deployer(service, commit, hote, simuler, uid, gid, **_):
    if uid == 0:
        raise Refus("Le service ne tourne jamais sous root : lancez le script avec l'utilisateur du serveur.")
    declaration = declaration_des_sources(service, commit)
    nom = nom_conteneur(service.projet)
    ancien = nom + "-ancien"
    try:
        verrou = Verrou(service.chemin(".deploiement")).__enter__() if not simuler else None
    except BlockingIOError:
        return OCCUPE, {"statut": "occupe", "detail": "Un déploiement de ce projet est déjà en cours."}
    try:
        return _deployer(service, commit, declaration, hote, simuler, uid, gid, nom, ancien)
    finally:
        if verrou:
            verrou.__exit__(None, None, None)


def _deployer(service, commit, declaration, hote, simuler, uid, gid, nom, ancien):
    jeton = service.jeton() or (_hasard.token_urlsafe(32) if not simuler else "x" * 43)
    env = _env(service, declaration, jeton)              # refus d'un secret manquant AVANT toute commande
    port = attribuer_port(service.racine, service.projet, ecrire=not simuler)
    if not simuler:
        if not service.jeton():
            ecrire_prive(service.chemin("jeton"), jeton + "\n")
        ecrire_prive(service.chemin("env"), env)
        (service.chemin("data")).mkdir(parents=True, exist_ok=True)
        os.chmod(service.chemin("data"), 0o700)
    image = nom_image(service.projet, commit)
    etat = service.etat()
    deploiement = {"commit": commit, "le": maintenant_iso()}

    # 1. Reprise d'un déploiement interrompu : un `-ancien` seul redevient le service ; avec le service, il est retiré.
    a_existe, _m, _i = inspecter(hote, ancien)
    s_existe, s_marche, s_image = inspecter(hote, nom)
    if a_existe and not s_existe:
        docker(hote, "rename", ancien, nom)
        docker(hote, "start", nom)
        s_existe, s_marche, s_image = True, True, None
    elif a_existe:
        docker(hote, "rm", "-f", ancien)

    # 2. L'image : construite depuis les sources du commit, ou tirée par empreinte. Un échec ne touche pas au service.
    if "dockerfile" in declaration:
        contexte = service.sources(commit)
        fichier = contexte.joinpath(*declaration["dockerfile"].split("/"))
        if not simuler and (fichier.is_symlink() or not fichier.is_file()):
            raise Refus(f"Dockerfile introuvable dans les sources : {declaration['dockerfile']}.")
        code, _o, err = docker(hote, "build", "--label", f"myiafactory.service={service.projet}", "-t", image, "-f",
                               str(fichier), str(contexte), delai=DELAI_CONSTRUCTION_S)
    else:
        code, _o, err = docker(hote, "pull", declaration["image"], delai=DELAI_CONSTRUCTION_S)
        if code == 0:
            code, _o, err = docker(hote, "tag", declaration["image"], image)
    if code != 0:
        raise Echec(f"Construction de l'image impossible (code {code}) : le service en place n'est pas touché.")

    # 3. Bascule : l'ancien est arrêté et GARDÉ (jamais deux instances sur /data), le nouveau prend le port.
    if s_existe:
        docker(hote, "rename", nom, ancien)
        docker(hote, "stop", "-t", str(DELAI_ARRET_S), ancien, delai=DELAI_ARRET_S + 60)
    code, _o, err = docker(hote, *argv_run(service.projet, image, port, declaration, uid, gid, service.racine))
    raison = None if code == 0 else f"démarrage du conteneur impossible (code {code})"
    if raison is None and not simuler:
        raison = attendre_sante(hote, port, declaration, jeton)

    if raison:
        docker(hote, "rm", "-f", nom)
        if s_existe:                                                   # retour arrière automatique
            docker(hote, "rename", ancien, nom)
            docker(hote, "start", nom)
            statut, detail = "retour_arriere", f"Nouvelle version refusée ({raison}) : l'ancienne est remise en place."
        else:
            statut, detail = "echec", f"Premier déploiement refusé ({raison}) : rien n'est ouvert."
        if not simuler:
            etat["dernier_deploiement"] = dict(deploiement, statut=statut, raison=raison)
            etat.setdefault("etat", "actif" if s_existe else "echec")
            service.ecrire_etat(etat)
        return 1, {"statut": statut, "detail": detail, "port": port}

    ouvrir_port(hote, port)
    if s_existe:
        docker(hote, "rm", "-f", ancien)
    precedente = etat.get("image") if etat.get("image") != image else etat.get("image_precedente")
    if not simuler:
        vieille = etat.get("image_precedente")
        if isinstance(vieille, str) and vieille not in (image, precedente) and vieille.startswith("myiafactory-service-"):
            docker(hote, "rmi", vieille)
        garder = {commit, etat.get("commit")}
        for d in (service.dossier / "sources").iterdir():
            if d.name not in garder and not d.name.startswith("."):
                shutil.rmtree(d, ignore_errors=True)
        service.ecrire_etat({
            "etat": "actif", "nom": declaration["nom"], "port": port, "port_interne": declaration["port_interne"],
            "sante": declaration["sante"], "image": image, "image_precedente": precedente, "commit": commit,
            "commit_precedent": etat.get("commit") if etat.get("commit") != commit else etat.get("commit_precedent"),
            "deploye_le": deploiement["le"], "dernier_deploiement": dict(deploiement, statut="ok", raison=None)})
    return 0, {"statut": "simule" if simuler else "ok", "port": port,
               "detail": f"Service {declaration['nom']} déployé au commit {commit[:12]}, port {port}."}


def cmd_etat(service, hote, simuler, **_):
    etat = service.etat()
    if not etat:
        return 0, {"statut": "ok", "etat": "absent", "detail": "Aucun service déployé pour ce projet."}
    existe, en_marche, _image = inspecter(hote, nom_conteneur(service.projet))
    port = port_du_projet(service.racine, service.projet)
    sante = None
    if en_marche and port and not simuler:
        sante = hote.http(f"http://127.0.0.1:{port}{etat.get('sante', '/sante')}", delai=3) == 200
    lu = "actif" if en_marche else ("arrete" if existe else etat.get("etat", "absent"))
    garde = ("nom", "port", "port_interne", "sante", "image", "image_precedente", "commit", "commit_precedent",
             "deploye_le", "dernier_deploiement")
    return 0, dict({k: etat.get(k) for k in garde}, statut="ok", etat=lu, en_marche=en_marche, sante_ok=sante,
                   port=port, secrets=presence_secrets(service, etat.get("commit")), detail=f"Service {lu}.")


def presence_secrets(service, commit=None):
    """{nom: présent ?} pour chaque secret déclaré (déclaration du commit en place) ou déjà posé : JAMAIS la valeur."""
    noms = []
    if isinstance(commit, str) and MOTIF_COMMIT.fullmatch(commit):
        try:
            noms = declaration_des_sources(service, commit)["secrets"]
        except Refus:
            noms = []
    poses = service.secrets()
    return {n: n in poses for n in sorted(set(noms) | {k for k in poses if isinstance(k, str)})}


def cmd_journal(service, hote, lignes, **_):
    code, sortie, erreur = docker(hote, "logs", "--tail", str(lignes), nom_conteneur(service.projet))
    if code != 0:
        raise Echec(f"Journal illisible (code {code}).")
    texte = (sortie or "") + (("\n" + erreur) if erreur else "")
    rendues = [l[:LIGNE_MAX] for l in texte.splitlines()][-lignes:]
    return 0, {"statut": "ok", "lignes": rendues, "detail": f"{len(rendues)} ligne(s)."}


def cmd_redemarrer(service, hote, simuler, **_):
    nom = nom_conteneur(service.projet)
    existe, en_marche, _i = inspecter(hote, nom)
    if not existe:
        raise Echec("Aucun conteneur pour ce service : déployez-le d'abord.")
    docker(hote, "restart", "-t", str(DELAI_ARRET_S), nom, delai=DELAI_ARRET_S + 60)
    port = port_du_projet(service.racine, service.projet)
    ouvrir_port(hote, port)
    if not simuler:
        service.ecrire_etat(dict(service.etat(), etat="actif"))
    return 0, {"statut": "simule" if simuler else "ok", "detail": "Service redémarré."}


def cmd_arreter(service, hote, simuler, **_):
    docker(hote, "stop", "-t", str(DELAI_ARRET_S), nom_conteneur(service.projet), delai=DELAI_ARRET_S + 60)
    fermer_port(hote, port_du_projet(service.racine, service.projet))
    if not simuler and service.etat():
        service.ecrire_etat(dict(service.etat(), etat="arrete"))
    return 0, {"statut": "simule" if simuler else "ok", "detail": "Service arrêté, port fermé."}


def cmd_supprimer(service, hote, simuler, **_):
    nom = nom_conteneur(service.projet)
    etat = service.etat()
    for n in (nom, nom + "-ancien"):
        docker(hote, "rm", "-f", n)
    for img in (etat.get("image"), etat.get("image_precedente")):
        if isinstance(img, str) and img.startswith(f"myiafactory-service-{service.projet}:"):
            docker(hote, "rmi", img)
    fermer_port(hote, port_du_projet(service.racine, service.projet))
    if not simuler:
        liberer_port(service.racine, service.projet)
        shutil.rmtree(service.dossier / "sources", ignore_errors=True)
        for f in ("jeton", "env", "secrets.json", "variables.json"):
            try:
                service.chemin(f).unlink()
            except OSError:
                pass
        service.ecrire_etat({"etat": "supprime"})
    return 0, {"statut": "simule" if simuler else "ok",
               "detail": "Service supprimé ; ses données (~/services/<projet>/data) sont gardées."}


def cmd_jeton(service, **_):
    j = service.jeton()
    if not j:
        raise Echec("Aucun jeton : le service n'a jamais été déployé.")
    return 0, {"statut": "ok", "jeton": j, "detail": "Jeton du service."}


# --- Entrée -------------------------------------------------------------------------------------------------------------

def masquer(valeur, secrets):
    if isinstance(valeur, str):
        for s in secrets:
            valeur = valeur.replace(s, MASQUE)
        return valeur
    if isinstance(valeur, list):
        return [masquer(v, secrets) for v in valeur]
    if isinstance(valeur, dict):
        return {k: masquer(v, secrets) for k, v in valeur.items()}
    return valeur


def _analyser(argv):
    argv = list(argv)
    simuler = "--simuler" in argv
    argv = [a for a in argv if a != "--simuler"]
    lignes = LIGNES_MAX
    if "--lignes" in argv:
        i = argv.index("--lignes")
        if i + 1 >= len(argv) or not re.fullmatch(r"[1-9][0-9]{0,2}", argv[i + 1]) or int(argv[i + 1]) > LIGNES_MAX:
            raise Refus(f"--lignes : un entier de 1 à {LIGNES_MAX}.")
        lignes = int(argv[i + 1])
        del argv[i:i + 2]
    if not argv or argv[0] not in COMMANDES:
        raise Refus("Commande inconnue. Attendu : " + ", ".join(COMMANDES) + ".")
    commande = argv[0]
    attendus = 3 if commande in AVEC_COMMIT else 2
    if len(argv) != attendus:
        raise Refus(f"« {commande} » attend {attendus - 1} argument(s).")
    projet = argv[1]
    if not MOTIF_PROJET.fullmatch(projet):
        raise Refus("Projet refusé : minuscules, chiffres et -, 2 à 40 caractères.")
    commit = argv[2] if attendus == 3 else None
    if commit is not None and not MOTIF_COMMIT.fullmatch(commit):
        raise Refus("Commit refusé : 40 caractères hexadécimaux en minuscules.")
    return commande, projet, commit, simuler, lignes


def main(argv=None, entree=None, sortie=None, hote=None, racine=None, uid=None, gid=None):
    argv = sys.argv[1:] if argv is None else argv
    entree = sys.stdin.buffer if entree is None else entree
    sortie = sys.stdout if sortie is None else sortie
    racine = Path(racine) if racine is not None else Path.home() / "services"
    uid = os.getuid() if uid is None and hasattr(os, "getuid") else (uid if uid is not None else 1000)
    gid = (os.getgid() if hasattr(os, "getgid") else uid) if gid is None else gid
    reponse = {"commande": argv[0] if argv and isinstance(argv[0], str) and len(argv[0]) < 40 else None,
               "projet": None}
    service = None
    try:
        commande, projet, commit, simuler, lignes = _analyser(argv)
        reponse["projet"] = projet
        service = Service(racine, projet)
        if not simuler and commande not in ("etat", "journal", "jeton"):
            racine.mkdir(parents=True, exist_ok=True)
            os.chmod(racine, 0o700)
        execution = Simulation() if simuler else (hote or Hote())
        fonctions = {
            "recevoir": cmd_recevoir, "deployer": cmd_deployer, "mettre-a-jour": cmd_deployer, "etat": cmd_etat,
            "journal": cmd_journal, "redemarrer": cmd_redemarrer, "arreter": cmd_arreter, "supprimer": cmd_supprimer,
            "jeton": cmd_jeton,
            "poser-variables": lambda **k: cmd_poser(fichier="variables.json", quoi="variables", **k),
            "poser-secrets": lambda **k: cmd_poser(fichier="secrets.json", quoi="secrets", **k),
        }
        masquables = service.valeurs_a_masquer()
        code, plus = fonctions[commande](service=service, commit=commit, entree=entree, hote=execution,
                                         simuler=simuler, uid=uid, gid=gid, lignes=lignes)
        if simuler:
            plus["commandes"] = execution.plan
        reponse.update(plus)
        if commande != "jeton":
            reponse = masquer(reponse, sorted(set(masquables) | set(service.valeurs_a_masquer()), key=len,
                                              reverse=True))
    except Refus as e:
        code = 2
        reponse.update(statut="refus", detail=str(e))
    except Echec as e:
        code = 1
        reponse.update(statut="echec", detail=str(e))
    except BlockingIOError:
        code = OCCUPE
        reponse.update(statut="occupe", detail="Opération déjà en cours pour ce projet.")
    except Exception as e:  # noqa: BLE001 - jamais de trace : le type seulement
        code = 1
        reponse.update(statut="echec", detail=f"Erreur inattendue ({type(e).__name__}).")
    if service is not None and reponse.get("statut") in ("refus", "echec", "occupe"):
        reponse = masquer(reponse, service.valeurs_a_masquer())
    sortie.write(json.dumps(reponse, ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
