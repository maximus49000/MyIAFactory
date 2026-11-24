"""Aides HÔTE de l'enveloppe des campagnes de tests (`taches/lancer_tests.sh`), lancées par `python3 -I` sur le serveur.

Bibliothèque standard seulement (Python 3.9 et plus) ; aucune donnée lue ici n'est jamais une consigne.

- `--commande` : la commande (entrée standard) doit être un tableau JSON de 1 à 64 chaînes, 4 096 octets au plus, premier
  élément non vide, aucun NUL : la règle même de `entree-tests.sh`, contrôlée AVANT toute écriture. Code 0 admise, 2 refusée.
- `--archive <entree.tar>` : l'instantané déposé par le poste est relu en-tête par en-tête AVANT `docker run`, sans
  `tarfile` (qui comprend trop de formats) : seulement des membres USTAR (`ustar\\0` + `00`) de type fichier ordinaire
  (`0` ou NUL), somme de contrôle juste, taille en octal (jamais base 256), aucun lien (nom de lien vide), droits sans
  bit spécial, nom relatif sûr (`nom_sur`, la règle de `outils/tests_instantane.py`), aucun doublon ni fichier qui serait
  aussi un dossier, `MAX_FICHIER` par fichier, `MAX_TOTAL` au total, `MAX_FICHIERS` membres, archive de `MAX_ARCHIVE`
  octets au plus, multiple de 512, et rien que des zéros après le premier bloc nul. Ni dossier, ni lien symbolique ou dur,
  ni périphérique, ni membre GNU (noms longs, éparpillés), ni en-tête pax : l'extraction de `tar -x` du conteneur ne peut
  donc créer que des fichiers ordinaires sous /work. Code 0 admise, 3 refusée (raison sur la sortie d'erreur) ; tout autre
  code (plantage de python : 1) n'est pas un refus de l'archive.
- `--prefixer <marque> <max>` : relaie l'entrée vers la sortie en mettant `| ` au début de CHAQUE ligne (bloc par bloc, sans
  attendre la fin des lignes : la sortie reste en direct) et finit toujours par un retour à la ligne ; \r devient \n et les
  autres séparateurs de lignes (\x0b \x0c \x1c-\x1e U+0085 U+2028 U+2029) sont écrits sous forme de texte (`Nettoyeur`) :
  aucune ligne du conteneur ne peut ressembler à une ligne de l'enveloppe (`#fin`, `#refus`, `#attente`). Au-delà de
  `<max>` octets ÉCRITS (après réécriture et préfixe), le reste est lu et jeté (le conteneur n'est jamais bloqué) et le fichier `<marque>` est créé.
- `--couper <marque> <max>` : relaie l'entrée (mêmes séparateurs réécrits, sans préfixe), `<max>` octets écrits au plus, puis lit
  et jette le reste et crée `<marque>`. Une sortie fermée (poste parti) ne bloque jamais : l'entrée est vidée jusqu'au bout.
- Messages (`texte_sur`) : contrôles et séparateurs d'un nom refusé écrits sous forme de texte, sur une seule ligne.
Dépendances (conception § 5.13, tâche 14d) :
- `--hors-ligne <clé>` : la commande (entrée standard, même règle que `--commande`) avec les drapeaux hors ligne de la table
  fermée (`hors_ligne`) ; écrite sur la sortie standard.
- `--wrapper <entree.tar>` : « <sha256 du gradle-wrapper.jar> <version de la distribution> », ou code 3 et la raison
  (`wrapper-absent`, `distribution-hors-services-gradle`) ; l'enveloppe compare à la somme PUBLIÉE par Gradle.
- `--echauffer <clé> <famille>` : DANS le conteneur deps-<id> (monté en lecture seule sur /opt/myiafactory/tests_hote.py) :
  `plan_echauffement` puis les outils (aucune valeur du projet dans une commande), contenu dans /deps, verrou produit et
  marques dans /deps-meta.
- `--mandataire <port> <durée_s> <hôte>...` : DANS le conteneur mandataire-<id> : `CONNECT <hôte>:443` vers la liste fermée
  seulement (`hote_permis`), tout le reste refusé (403).
"""
import json
import os
import re
import stat
import sys

MAX_FICHIER = 50 * 1024 * 1024           # mêmes limites que outils/tests_instantane.py
MAX_TOTAL = 200 * 1024 * 1024
MAX_FICHIERS = 50000
BLOC = 512
# Chaque membre : un en-tête et au plus 511 octets de bourrage ; fin : deux blocs nuls et le bourrage jusqu'à un
# enregistrement de 10 240 octets (tarfile).
MAX_ARCHIVE = MAX_TOTAL + MAX_FICHIERS * 2 * BLOC + 2 * 10240
MAX_COMMANDE = 4096
REFUS_ARCHIVE = 3                        # code de --archive pour une archive refusée (l'enveloppe rend alors 70)
LIRE = 65536

_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_LECTEUR = re.compile(r"^[A-Za-z]:")
_OCTAL = re.compile(rb"^ *([0-7]{1,12}) *$")


def commande_valide(brut):
    """Vrai si `brut` (octets) est la commande admise par entree-tests.sh."""
    if not isinstance(brut, bytes) or len(brut) > MAX_COMMANDE:
        return False
    try:
        c = json.loads(brut.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    if not (isinstance(c, list) and 1 <= len(c) <= 64 and all(isinstance(x, str) and "\0" not in x for x in c)
            and c[0]):
        return False
    try:                                 # demi-substitut seul (« \ud800 ») : l'entrée du conteneur ne l'encoderait pas
        for x in c:
            x.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def nom_sur(nom):
    """Relatif, segments non vides, ni `.` ni `..`, ni `\\`, ni caractère de contrôle, ni lettre de lecteur."""
    if not nom or nom.startswith("/") or "\\" in nom or _CONTROLE.search(nom) or _LECTEUR.match(nom):
        return False
    return all(s not in ("", ".", "..") for s in nom.split("/"))


def _champ(entete, debut, longueur):
    """Champ texte d'en-tête : jusqu'au premier NUL (comme tar)."""
    return entete[debut:debut + longueur].split(b"\0", 1)[0]


def _octal(champ):
    m = _OCTAL.match(champ.split(b"\0", 1)[0])
    return int(m.group(1), 8) if m else None


def verifier_archive(chemin):
    """None si l'archive est admise, sinon la raison (français)."""
    try:
        if stat.S_ISLNK(os.lstat(chemin).st_mode):     # O_NOFOLLOW n'existe pas partout : le lien est refusé d'abord
            return "archive : lien refusé"
        fd = os.open(chemin, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as e:
        return "archive illisible (%s)" % e.strerror
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            return "archive : pas un fichier ordinaire"
        taille = st.st_size
        if taille > MAX_ARCHIVE:
            return "archive trop grosse (%d octets, %d au plus)" % (taille, MAX_ARCHIVE)
        if taille % BLOC:
            return "archive : taille non multiple de 512"
        noms, dossiers = set(), set()
        total = n = 0
        while True:
            entete = f.read(BLOC)
            if len(entete) < BLOC:
                return "archive tronquée (pas de bloc de fin)"
            if entete == b"\0" * BLOC:
                break
            somme = _octal(entete[148:156])
            calcul = sum(entete[:148]) + 8 * 32 + sum(entete[156:])
            if somme is None or somme != calcul:
                return "en-tête invalide (somme de contrôle) au membre %d" % (n + 1)
            if entete[257:263] != b"ustar\0" or entete[263:265] != b"00":
                return "membre %d hors USTAR (GNU, ancien format ou autre)" % (n + 1)
            if entete[156:157] not in (b"0", b"\0"):
                return "membre %d : type %r refusé (fichiers ordinaires seulement)" % (n + 1, entete[156:157])
            if _champ(entete, 157, 100):
                return "membre %d : nom de lien refusé" % (n + 1)
            mode, t = _octal(entete[100:108]), _octal(entete[124:136])
            if mode is None or mode & ~0o777:
                return "membre %d : droits refusés" % (n + 1)
            if t is None:
                return "membre %d : taille illisible" % (n + 1)
            try:
                nom = _champ(entete, 0, 100).decode("utf-8")
                prefixe = _champ(entete, 345, 155).decode("utf-8")
            except UnicodeDecodeError:
                return "membre %d : nom non UTF-8" % (n + 1)
            if prefixe:
                nom = prefixe + "/" + nom
            if not nom_sur(nom):
                return "nom refusé : %r" % nom[:200]
            n += 1
            if n > MAX_FICHIERS:
                return "trop de fichiers (%d au plus)" % MAX_FICHIERS
            if t > MAX_FICHIER:
                return "fichier trop gros : %s" % nom
            total += t
            if total > MAX_TOTAL:
                return "instantané trop gros (plus de %d octets)" % MAX_TOTAL
            parties = nom.split("/")
            parents = {"/".join(parties[:i]) for i in range(1, len(parties))}
            if nom in noms or nom in dossiers or parents & noms:
                return "nom en double ou fichier et dossier à la fois : %s" % nom
            noms.add(nom)
            dossiers |= parents
            saut = (t + BLOC - 1) // BLOC * BLOC
            if f.tell() + saut > taille:
                return "archive tronquée au membre %s" % nom
            f.seek(saut, os.SEEK_CUR)
        while True:                                     # après le premier bloc nul : des zéros seulement
            reste = f.read(LIRE)
            if not reste:
                return None
            if reste.strip(b"\0"):
                return "données après la fin de l'archive"


def _vider(entree):
    while os.read(entree, LIRE):
        pass


def _marquer(marque):
    try:
        os.close(os.open(marque, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600))
    except OSError:
        pass


def _ecrire(sortie, octets):
    """Écrit tout ; False si la sortie est fermée (le poste est parti)."""
    try:
        while octets:
            octets = octets[os.write(sortie, octets):]
        return True
    except OSError:
        return False


# Séparateurs de lignes autres que \n (str.splitlines, terminaux) : un « \r#fin 0 … » ou « \x0c#fin 0 … » du conteneur ne
# doit jamais commencer une ligne, même pour un lecteur moins strict que le poste. \r et \r\n deviennent \n (la ligne qui
# suit est donc préfixée) ; \x0b, \x0c, \x1c-\x1e et U+0085, U+2028, U+2029 (en UTF-8) sont écrits sous forme de texte
# (« \x0c », «   »). Contrat du poste : la sortie d'erreur se coupe sur b"\n" SEULEMENT, et seule la DERNIÈRE ligne
# (`#fin`) et celle qui la précède (`#refus`) sont crues.
_SEPARATEURS = re.compile(rb"\r\n?|[\x0b\x0c\x1c-\x1e]|\xc2\x85|\xe2\x80[\xa8\xa9]")
_DEBUTS = (b"\xe2\x80", b"\xe2", b"\xc2", b"\r")         # début possible d'un séparateur coupé entre deux blocs


def _remplacer(m):
    s = m.group()
    if s[:1] == b"\r":
        return b"\n"
    if len(s) == 1:
        return b"\\x%02x" % s[0]
    return b"\\u%04x" % ord(s.decode("utf-8"))


class Nettoyeur:
    """Réécrit les séparateurs bloc par bloc ; un séparateur coupé entre deux blocs est gardé pour le bloc suivant."""

    def __init__(self):
        self.reste = b""

    def traiter(self, bloc):
        d, self.reste = self.reste + bloc, b""
        for debut in _DEBUTS:
            if d.endswith(debut):
                d, self.reste = d[:-len(debut)], debut
                break
        return _SEPARATEURS.sub(_remplacer, d)

    def finir(self):
        d, self.reste = self.reste, b""
        return _SEPARATEURS.sub(_remplacer, d)


def _prefixer_texte(propre, debut):
    """(texte avec `| ` au début de chaque ligne, vrai si le texte finit par \n) ; seul \n sépare les lignes ici."""
    morceaux = []
    parties = propre.split(b"\n")
    for i, partie in enumerate(parties):
        dernier = i == len(parties) - 1
        if dernier and not partie:
            break
        if debut:
            morceaux.append(b"| ")
        morceaux.append(partie)
        if dernier:
            debut = False
        else:
            morceaux.append(b"\n")
            debut = True
    return b"".join(morceaux), debut


def _relayer(entree, sortie, marque, maximum, prefixe):
    """Le plafond compte les octets ÉCRITS (après réécriture et préfixe : le flux peut grossir de 3 à 4 fois)."""
    nettoyeur, etat = Nettoyeur(), {"ouverte": True, "debut": True, "ecrits": 0}

    def envoyer(propre):   # vrai si le plafond est atteint
        if prefixe:
            propre, etat["debut"] = _prefixer_texte(propre, etat["debut"])
        coupe = etat["ecrits"] + len(propre) > maximum
        if coupe:
            propre = propre[:maximum - etat["ecrits"]]
            etat["debut"] = propre.endswith(b"\n") if propre else etat["debut"]
        etat["ecrits"] += len(propre)
        if etat["ouverte"] and propre:
            etat["ouverte"] = _ecrire(sortie, propre)
        return coupe

    coupe = False
    while not coupe:
        bloc = os.read(entree, LIRE)
        if not bloc:
            coupe = envoyer(nettoyeur.finir())
            break
        coupe = envoyer(nettoyeur.traiter(bloc))
    if coupe:
        _marquer(marque)
        _vider(entree)
    if prefixe and etat["ouverte"] and not etat["debut"]:
        _ecrire(sortie, b"\n")


def couper(entree, sortie, marque, maximum):
    _relayer(entree, sortie, marque, maximum, False)


def prefixer(entree, sortie, marque, maximum):
    _relayer(entree, sortie, marque, maximum, True)


_TEXTE_DOUTEUX = re.compile("[\x00-\x1f\x7f-\x9f  ]")


def texte_sur(texte):
    """Un message sur UNE ligne : contrôles et séparateurs écrits sous forme de texte (« \\u000a »)."""
    return _TEXTE_DOUTEUX.sub(lambda m: "\\u%04x" % ord(m.group()), texte)


# =====================================================================================================================
# Dépendances (conception § 5.13, tâche 14d). Les clés d'échauffement sont celles de la table fermée ECH de lancer_tests.sh.
# =====================================================================================================================

CLES = ("npm", "pnpm", "yarn", "yarn-berry", "pip", "pip-sources", "gradle", "maven", "dotnet", "cargo", "go", "unity")
_MOTIF_CLE = re.compile(r"[a-z][a-z-]{1,23}")      # familles comprises (« gradle-android » : 14 caractères)


def _executable(x):
    return x.replace("\\", "/").rsplit("/", 1)[-1].lower()


def hors_ligne(commande, cle):
    """La commande des tests avec les drapeaux hors ligne de la famille (table fermée : Gradle `--offline --no-daemon`,
    Maven `-o`, Cargo `--offline`, .NET `--no-restore`), ajoutés seulement si l'exécutable est celui de la famille ; les
    familles réglées par variables (Go, pip, npm) ne changent pas. Au-delà de 64 éléments : inchangée."""
    c = list(commande)
    if not c:
        return c
    exe = _executable(c[0])
    if cle == "gradle" and exe in ("gradlew", "gradle"):
        nouvelle = [c[0], "--offline", "--no-daemon"] + [x for x in c[1:] if x not in ("--offline", "--no-daemon")]
    elif cle == "maven" and exe in ("mvn", "mvnw"):
        nouvelle = c if "-o" in c[1:] or "--offline" in c[1:] else [c[0], "-o"] + c[1:]
    elif cle == "cargo" and exe == "cargo":
        nouvelle = c if "--offline" in c[1:] else [c[0], "--offline"] + c[1:]
    elif cle == "dotnet" and exe == "dotnet" and len(c) > 1 and c[1] in ("test", "build", "run", "publish", "pack"):
        nouvelle = c if "--no-restore" in c[2:] else c[:2] + ["--no-restore"] + c[2:]
    else:
        nouvelle = c
    if len(nouvelle) > 64 or len(json.dumps(nouvelle, ensure_ascii=False).encode("utf-8")) > MAX_COMMANDE:
        return c
    return nouvelle


_CONNECT = re.compile(r"CONNECT ([A-Za-z0-9.-]{1,253}):443 HTTP/1\.[01]")


def hote_permis(ligne, hotes):
    """L'hôte (en minuscules) d'une requête `CONNECT <hôte>:443` dont l'hôte est EXACTEMENT dans la liste fermée ; sinon None
    (autre port, autre méthode, adresse IP, suffixe trompeur)."""
    m = _CONNECT.fullmatch(ligne or "")
    if not m:
        return None
    hote = m.group(1).lower()
    return hote if hote in {h.lower() for h in hotes} else None


def adresse_interne():
    """L'adresse du conteneur sur le réseau INTERNE de l'échauffement : le conteneur y est créé seul (le réseau bridge n'est
    branché qu'après), son nom d'hôte y résout donc. ValueError pour une adresse de bouclage (jamais d'écoute partout)."""
    import socket
    ip = socket.gethostbyname(socket.gethostname())
    if not re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){3}", ip) or ip.startswith("127.") or ip == "0.0.0.0":
        raise ValueError("adresse interne introuvable")
    return ip


def mandataire(port, duree_s, hotes):
    """Mandataire éphémère (dans son conteneur, créé sur le réseau interne de l'échauffement puis branché au bridge) :
    n'écoute QUE l'adresse interne ; seulement `CONNECT` vers les hôtes de la liste, port 443 ; 64 connexions au plus ;
    s'arrête seul après `duree_s` (l'enveloppe le supprime avant)."""
    import select
    import socket
    import threading
    import time
    fin = time.time() + duree_s
    places = threading.BoundedSemaphore(64)
    serveur = socket.create_server((adresse_interne(), port))
    serveur.settimeout(1.0)

    def servir(client):
        amont = None
        try:
            client.settimeout(30)
            tete = b""
            while b"\r\n\r\n" not in tete and len(tete) < 8192:
                bloc = client.recv(4096)
                if not bloc:
                    return
                tete += bloc
            ligne = tete.split(b"\r\n", 1)[0].decode("ascii", "replace")
            hote = hote_permis(ligne, hotes)
            if hote is None:
                client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            amont = socket.create_connection((hote, 443), timeout=30)
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            reste = tete.split(b"\r\n\r\n", 1)[1]
            if reste:
                amont.sendall(reste)
            paires = {client: amont, amont: client}
            while time.time() < fin:
                lisibles, _, _ = select.select(list(paires), [], [], 300)
                if not lisibles:
                    return
                for s in lisibles:
                    donnees = s.recv(65536)
                    if not donnees:
                        return
                    paires[s].sendall(donnees)
        except OSError:
            return
        finally:
            for s in (client, amont):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass
            places.release()

    while time.time() < fin:
        try:
            client, _ = serveur.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        if not places.acquire(blocking=False):
            client.close()
            continue
        threading.Thread(target=servir, args=(client,), daemon=True).start()
    return 0


# Fichiers que voit l'échauffement d'une famille qui n'exécute pas de code du projet (les autres fichiers sont effacés de la
# copie de travail du conteneur avant l'outil) ; Gradle, Maven, pip sans roue et Cargo gardent tout (l'outil l'exige).
_MANIFESTES = {
    "npm": re.compile(r"(.*/)?(package\.json|package-lock\.json|npm-shrinkwrap\.json)"),
    "pnpm": re.compile(r"(.*/)?(package\.json|pnpm-lock\.yaml|pnpm-workspace\.yaml)"),
    "yarn": re.compile(r"(.*/)?(package\.json|yarn\.lock|\.yarnrc\.yml)"),
    "pip": re.compile(r"(.*/)?(requirements|constraints)[^/]*\.txt"),
    "go": re.compile(r"(.*/)?(go\.mod|go\.sum|go\.work|go\.work\.sum)"),
    "dotnet": re.compile(r"(.*/)?([^/]+\.(csproj|fsproj|vbproj|sln|props|targets)|global\.json|nuget\.config|"
                         r"packages\.lock\.json)", re.I),
}
_INIT_GRADLE = """allprojects {
  tasks.register("myiafactoryResoudre") {
    doLast {
      (project.configurations + project.buildscript.configurations).findAll { it.canBeResolved }.each { c ->
        try { c.resolve() } catch (Exception e) { logger.warn("myiafactory : configuration " + c.name + " non resolue") }
      }
    }
  }
}
"""
_GRADLE_OPTS = ("-Dorg.gradle.daemon=false -Dorg.gradle.vfs.watch=false -Dkotlin.compiler.execution.strategy=in-process "
                "-Dorg.gradle.project.android.builder.sdkDownload=false")


def _garder_manifestes(travail, motif):
    for dossier, _sous, fichiers in os.walk(travail, topdown=False):
        for f in fichiers:
            chemin = os.path.join(dossier, f)
            rel = os.path.relpath(chemin, travail).replace(os.sep, "/")
            if not motif.fullmatch(rel):
                os.unlink(chemin)
        if dossier != travail:
            try:
                os.rmdir(dossier)
            except OSError:
                pass


def _yarn_berry(travail):
    """Yarn 2+ : `.yarnrc.yml` ou `.yarn/` présents, ou `packageManager` yarn@2+ dans package.json."""
    if any(os.path.lexists(os.path.join(travail, n)) for n in (".yarnrc.yml", ".yarn")):
        return True
    try:
        with open(os.path.join(travail, "package.json"), encoding="utf-8", errors="replace") as f:
            pj = json.loads(f.read(MAX_COMMANDE * 64))
    except (OSError, ValueError):
        return False
    m = re.fullmatch(r"yarn@(\d{1,3})\..*", str(pj.get("packageManager") or "") if isinstance(pj, dict) else "")
    return bool(m and int(m.group(1)) >= 2)


_EXIGENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}(\[[A-Za-z0-9,._ -]{0,100}\])?\s*"
                       r"([<>=!~]=?[^;@]{0,200})?(;[^@]{0,300})?")


def _verifier_exigences(travail, nom, vus):
    """Les exigences nommées de `nom` (requirements*.txt) ; ValueError pour toute option (index, find-links, hôte de
    confiance, -e…), URL, chemin ou référence directe (« @ ») : rien dans le projet ne choisit l'hôte. Seul `-r <fichier>`
    vers un fichier du projet est suivi."""
    base = os.path.realpath(travail)
    chemin = os.path.realpath(os.path.join(travail, nom))
    if not chemin.startswith(base + os.sep) or not os.path.isfile(chemin):
        raise ValueError("requirements hors du projet")
    if chemin in vus:
        return []
    vus.add(chemin)
    with open(chemin, encoding="utf-8", errors="replace") as f:
        texte = f.read(MAX_FICHIER).replace("\\\n", " ")
    noms = []
    for brute in texte.splitlines():
        ligne = re.sub(r"(^|\s)#.*$", "", brute).strip()
        if not ligne:
            continue
        m = re.fullmatch(r"(?:-r|--requirement)(?:\s+|=)(\S+)", ligne)
        if m:
            if not nom_sur(m.group(1)):
                raise ValueError("-r hors du projet")
            noms += _verifier_exigences(travail, os.path.join(os.path.dirname(nom), m.group(1)), vus)
            continue
        if ligne.startswith("-") or "://" in ligne or "@" in ligne or "/" in ligne or "\\" in ligne \
                or not _EXIGENCE.fullmatch(ligne):
            raise ValueError("ligne de requirements refusée (option, URL ou chemin)")
        noms.append(ligne)
    return noms


def geler(venv):
    """Les paquets installés dans `venv`, « nom==version » triés, lus dans les métadonnées (importlib.metadata) par le
    Python qui exécute CETTE aide : jamais le Python du venv, aucun .pth du venv exécuté."""
    import glob
    from importlib import metadata
    chemins = sorted(glob.glob(os.path.join(venv, "lib", "python*", "site-packages")))
    paquets = set()
    for d in metadata.distributions(path=chemins):
        nom, version = d.metadata.get("Name"), d.version
        if nom and version and nom.lower() not in ("pip", "setuptools", "wheel"):
            paquets.add("%s==%s" % (nom, version))
    return "".join(x + "\n" for x in sorted(paquets))


def plan_echauffement(cle, famille, travail, deps="/deps"):
    """Le plan de l'échauffement `cle` dans `travail` (copie de travail du conteneur) : `{"etapes": [{"commande", "env",
    "obligatoire"}], "deplacer": [(source, destination)], "produit": verrou produit ou None, "verrouille": bool}`. Efface
    d'abord de `travail` tout ce qui n'est pas un manifeste pour les familles qui n'exécutent pas de code du projet. Aucune
    valeur du projet n'entre dans une commande (seulement des noms de fichiers trouvés par motif fermé). ValueError : clé
    refusée ou rien à préparer."""
    if cle not in CLES:
        raise ValueError("clé d'échauffement refusée")
    if cle == "unity":
        raise ValueError("unity : échauffement par la tâche 14g (licence)")
    if cle == "yarn" and _yarn_berry(travail):
        raise ValueError("yarn berry (yarnPath, extensions) : clé yarn-berry, avec l'accord réseau")
    motif = _MANIFESTES.get("pip" if cle in ("pip", "pip-sources") else cle)
    if motif is not None:
        _garder_manifestes(travail, motif)
    existe = lambda n: os.path.isfile(os.path.join(travail, n))   # noqa: E731
    etapes, deplacer, produit, verrouille = [], [], None, True

    def etape(commande, env=None, obligatoire=True):
        etapes.append({"commande": list(commande), "env": dict(env or {}), "obligatoire": obligatoire})

    if cle in ("npm", "pnpm", "yarn", "yarn-berry"):
        if not existe("package.json"):
            raise ValueError("package.json absent")
        verrou = {"npm": next((n for n in ("package-lock.json", "npm-shrinkwrap.json") if existe(n)), None),
                  "pnpm": "pnpm-lock.yaml" if existe("pnpm-lock.yaml") else None,
                  "yarn": "yarn.lock" if existe("yarn.lock") else None,
                  "yarn-berry": "yarn.lock" if existe("yarn.lock") else None}[cle]
        # Pour toutes les familles node : jamais le yarnPath du projet, jamais une URL de gestionnaire choisie par le projet.
        corepack = {"COREPACK_HOME": "/tmp/corepack", "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0", "YARN_IGNORE_PATH": "1",
                    "COREPACK_ENABLE_UNSAFE_CUSTOM_URLS": "0"}
        if cle == "npm":
            etape(["npm", "ci" if verrou else "install", "--ignore-scripts", "--no-audit", "--no-fund"], corepack)
        elif cle == "pnpm":
            etape(["corepack", "pnpm", "install", "--ignore-scripts"] + (["--frozen-lockfile"] if verrou else []), corepack)
        elif cle == "yarn-berry":
            etape(["corepack", "yarn", "install", "--mode=skip-build"] + (["--immutable"] if verrou else []), corepack)
        else:
            etape(["corepack", "yarn", "install", "--ignore-scripts", "--non-interactive"]
                  + (["--frozen-lockfile"] if verrou else []), corepack)
        if not verrou:
            produit, verrouille = {"npm": "package-lock.json", "pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock",
                                   "yarn-berry": "yarn.lock"}[cle], False
        deplacer.append(("node_modules", "node_modules"))
    elif cle in ("pip", "pip-sources"):
        exigences = sorted(n for n in os.listdir(travail) if re.fullmatch(r"requirements[^/]*\.txt", n) and existe(n))
        if not exigences:
            raise ValueError("requirements*.txt absent")
        venv = f"{deps}/venv"
        noms = []
        for n in exigences:
            noms += _verifier_exigences(travail, n, set())
        etape(["python3", "-m", "venv", venv])
        # L'index est imposé ici (jamais celui d'une ligne du projet : elles sont refusées par _verifier_exigences).
        commande = [f"{venv}/bin/python", "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                    "--index-url", "https://pypi.org/simple"]
        if cle == "pip":
            commande.append("--only-binary=:all:")
        for n in exigences:
            commande += ["-r", n]
        etape(commande)
        if any("==" not in x for x in noms):
            verrouille, produit = False, "pip-freeze"          # gel par `geler` : jamais le Python du venv
    elif cle == "gradle":
        if not existe("gradlew"):
            raise ValueError("gradlew absent")
        env = {"GRADLE_USER_HOME": f"{deps}/gradle", "GRADLE_OPTS": _GRADLE_OPTS}
        base = ["./gradlew", "--no-daemon", "--no-configuration-cache"]
        etape(base + ["--init-script", "/tmp/myiafactory-resoudre.gradle", "myiafactoryResoudre"], env)
        # gradle-android : testDebugUnitTest, pas seulement la compilation : les jars d'exécution des tests
        # (debugUnitTestRuntimeClasspath, transformés par AGP) ne sont téléchargés qu'à l'exécution (jalon J8).
        etape(base + ["testDebugUnitTest" if famille == "gradle-android" else "testClasses"], env, obligatoire=False)
        verrouille = existe("gradle.lockfile")
    elif cle == "maven":
        outil = "./mvnw" if existe("mvnw") else "mvn"
        etape([outil, "-B", f"-Dmaven.repo.local={deps}/m2", "dependency:go-offline"], {"MAVEN_USER_HOME": f"{deps}/m2home"})
        verrouille = False
    elif cle == "dotnet":
        etape(["dotnet", "restore"], {"NUGET_PACKAGES": f"{deps}/nuget", "DOTNET_CLI_HOME": "/tmp",
                                      "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"})
        verrouille = existe("packages.lock.json")
    elif cle == "cargo":
        verrou = existe("Cargo.lock")
        etape(["cargo", "fetch"], {"CARGO_HOME": f"{deps}/cargo"})
        if not verrou:
            produit, verrouille = "Cargo.lock", False
    elif cle == "go":
        verrou = existe("go.sum")
        # Hôtes imposés : le proxy et la base de sommes officiels, jamais « direct » (un chemin de module choisirait l'hôte).
        etape(["go", "mod", "download"], {"GOMODCACHE": f"{deps}/gomod", "GOPATH": "/tmp/go", "GOFLAGS": "-mod=mod",
                                          "GOTOOLCHAIN": "local", "GOPROXY": "https://proxy.golang.org",
                                          "GOSUMDB": "sum.golang.org", "GOPRIVATE": "", "GONOPROXY": "", "GONOSUMDB": "",
                                          "GOINSECURE": ""})
        if not verrou:
            produit, verrouille = "go.sum", False
    return {"etapes": etapes, "deplacer": deplacer, "produit": produit, "verrouille": verrouille}


def echauffer(cle, famille, travail="/work", deps="/deps", meta="/deps-meta"):
    """Dans le conteneur `deps-<id>` (entrée : /work = l'instantané extrait) : le plan, puis le contenu dans `deps`, le verrou
    produit dans `meta/verrou-produit`, `meta/non-verrouille` le cas échéant, enfin `meta/ok`. Code 0, ou 1 (raison dite)."""
    import shutil
    import subprocess
    try:
        plan = plan_echauffement(cle, famille, travail, deps)
    except (ValueError, OSError) as e:
        sys.stderr.write("echauffement refusé : %s\n" % texte_sur(str(e)))
        return 1
    if cle == "gradle":
        with open("/tmp/myiafactory-resoudre.gradle", "w", encoding="utf-8") as f:
            f.write(_INIT_GRADLE)
    for e in plan["etapes"]:
        env = dict(os.environ, **e["env"])
        commande = list(e["commande"])
        if commande[1:4] == ["-m", "pip", "install"] and os.environ.get("HTTPS_PROXY"):
            commande += ["--proxy", os.environ["HTTPS_PROXY"]]
        r = subprocess.run(commande, cwd=travail, env=env, stdin=subprocess.DEVNULL)
        if r.returncode != 0 and e["obligatoire"]:
            sys.stderr.write("echauffement : %s a rendu %d\n" % (e["commande"][0], r.returncode))
            return 1
        if r.returncode != 0:
            sys.stderr.write("echauffement : étape facultative en échec (%s), le cache peut être incomplet\n" % e["commande"][-1])
    for source, destination in plan["deplacer"]:
        if os.path.isdir(os.path.join(travail, source)):
            shutil.move(os.path.join(travail, source), os.path.join(deps, destination))
    if plan["produit"] == "pip-freeze":
        with open(os.path.join(meta, "verrou-produit"), "w", encoding="utf-8") as f:
            f.write(geler(os.path.join(deps, "venv")))
    elif plan["produit"] and os.path.isfile(os.path.join(travail, plan["produit"])):
        shutil.copyfile(os.path.join(travail, plan["produit"]), os.path.join(meta, "verrou-produit"))
    if not plan["verrouille"]:
        open(os.path.join(meta, "non-verrouille"), "w").close()
    open(os.path.join(meta, "ok"), "w").close()
    return 0


_DISTRIBUTION = re.compile(r"https://services\.gradle\.org/distributions/gradle-"
                           r"([0-9]{1,2}\.[0-9]{1,2}(?:\.[0-9]{1,2})?(?:-rc-[0-9]{1,2})?)-(bin|all)\.zip")
_CLE_DISTRIBUTION = re.compile(r"\s*distributionUrl\s*[=:\s]\s*(.*)")


def _membres(chemin, voulus):
    """{nom: octets} des membres `voulus` de l'archive (déjà relue par `verifier_archive` : USTAR, fichiers ordinaires)."""
    trouves = {}
    with open(chemin, "rb") as f:
        while True:
            entete = f.read(BLOC)
            if len(entete) < BLOC or entete == b"\0" * BLOC:
                break
            nom = _champ(entete, 0, 100).decode("utf-8", "replace")
            prefixe = _champ(entete, 345, 155).decode("utf-8", "replace")
            if prefixe:
                nom = prefixe + "/" + nom
            taille = _octal(_champ(entete, 124, 12)) or 0
            blocs = (taille + BLOC - 1) // BLOC * BLOC
            if nom in voulus and taille <= MAX_FICHIER:
                trouves[nom] = f.read(taille)
                f.seek(blocs - taille, 1)
            else:
                f.seek(blocs, 1)
    return trouves


def _base36(n):
    chiffres = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = chiffres[r] + s
    return s or "0"


def wrapper_gradle(chemin):
    """`(sha256 du gradle-wrapper.jar, version, bin|all, dossier)` lus dans l'instantané ; `dossier` = celui où le wrapper
    cherche la distribution (base 36 du MD5 de l'URL, comme `PathAssembler` de Gradle). La DERNIÈRE `distributionUrl` fait foi
    (comme java.util.Properties). ValueError : jar ou propriétés absents, ou URL hors de services.gradle.org."""
    import hashlib
    jar, props = "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties"
    m = _membres(chemin, {jar, props})
    if jar not in m or props not in m:
        raise ValueError("wrapper-absent")
    # LIMITE CONNUE (relecture M2) : ce n'est pas un analyseur java.util.Properties complet (lignes continuées par « \\ »,
    # échappements \\uXXXX, clés échappées) : une telle forme est refusée (URL hors motif) ou ignorée, jamais suivie. La somme du
    # jar et le mandataire restent les garde-fous.
    derniere = None
    for ligne in m[props].decode("utf-8", "replace").splitlines():
        c = _CLE_DISTRIBUTION.fullmatch(ligne)
        if c:
            derniere = c.group(1).strip().replace("\\:", ":").replace("\\=", "=")
    d = _DISTRIBUTION.fullmatch(derniere or "")
    if not d:
        raise ValueError("distribution-hors-services-gradle")
    hache = _base36(int.from_bytes(hashlib.md5(derniere.encode("utf-8")).digest(), "big"))
    return hashlib.sha256(m[jar]).hexdigest(), d.group(1), d.group(2), hache


def versions_publiees(chemin):
    """Les versions de https://services.gradle.org/versions/all dont `wrapperChecksumUrl` est EXACTEMENT l'URL officielle
    attendue (toute autre est ignorée : jamais une URL lue dans la réponse n'est suivie)."""
    with open(chemin, "rb") as f:
        donnees = json.loads(f.read(32 * 1024 * 1024).decode("utf-8"))
    versions = []
    for e in donnees if isinstance(donnees, list) else []:
        v = e.get("version") if isinstance(e, dict) else None
        if (isinstance(v, str) and re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,2})?(-rc-[0-9]{1,2})?", v)
                and e.get("wrapperChecksumUrl") == "https://services.gradle.org/distributions/gradle-%s-wrapper.jar.sha256" % v):
            versions.append(v)
    return versions


def principal(argv):
    if argv[:1] == ["--hors-ligne"] and len(argv) == 2 and argv[1] in CLES:
        brut = sys.stdin.buffer.read(MAX_COMMANDE + 1)
        if not commande_valide(brut):
            return 2
        sys.stdout.write(json.dumps(hors_ligne(json.loads(brut.decode("utf-8")), argv[1]), ensure_ascii=False))
        return 0
    if argv[:1] == ["--wrapper"] and len(argv) == 2:
        try:
            sys.stdout.write("%s %s %s %s\n" % wrapper_gradle(argv[1]))
        except (ValueError, OSError) as e:
            sys.stderr.write("%s\n" % texte_sur(str(e)))
            return 3
        return 0
    if argv[:1] == ["--versions-gradle"] and len(argv) == 2:
        try:
            sys.stdout.write("".join(v + "\n" for v in versions_publiees(argv[1])[:2000]))
        except (ValueError, OSError):
            return 3
        return 0
    if argv[:1] == ["--echauffer"] and len(argv) == 3 and argv[1] in CLES and _MOTIF_CLE.fullmatch(argv[2]):
        return echauffer(argv[1], argv[2])
    if (argv[:1] == ["--mandataire"] and len(argv) >= 4 and re.fullmatch(r"[1-9][0-9]{0,4}", argv[1])
            and re.fullmatch(r"[1-9][0-9]{0,4}", argv[2])
            and all(re.fullmatch(r"[a-z0-9.-]{1,253}", h) for h in argv[3:])):
        return mandataire(int(argv[1]), int(argv[2]), tuple(argv[3:]))
    if argv[:1] == ["--commande"] and len(argv) == 1:
        brut = sys.stdin.buffer.read(MAX_COMMANDE + 1)
        if commande_valide(brut):
            return 0
        sys.stderr.write("commande refusée : un tableau JSON de 1 à 64 chaînes (4 Ko au plus) est attendu.\n")
        return 2
    if argv[:1] == ["--archive"] and len(argv) == 2:
        raison = verifier_archive(argv[1])
        if raison is None:
            return 0
        sys.stderr.write("instantané refusé : %s\n" % texte_sur(raison))
        return REFUS_ARCHIVE                # 3 : refus explicite ; un plantage de python rend 1, jamais 3
    if argv[:1] in (["--prefixer"], ["--couper"]) and len(argv) == 3 and re.match(r"^[1-9][0-9]{0,9}$", argv[2]):
        relais = prefixer if argv[0] == "--prefixer" else couper
        relais(sys.stdin.fileno(), sys.stdout.fileno(), argv[1], int(argv[2]))
        return 0
    sys.stderr.write("usage : tests_hote.py --commande | --archive <tar> | --prefixer|--couper <marque> <max>\n")
    return 2


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
