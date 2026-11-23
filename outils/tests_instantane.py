"""Instantané de l'arbre de travail envoyé au serveur pour une campagne de tests (conception § 5.2 et § 6).

Ce module décide de CE QUI QUITTE LE POSTE : il est volontairement strict, et chaque doute écarte le fichier.

- Liste : `git ls-files -co --exclude-standard -z` dans la racine (suivis et non suivis non ignorés, commités ou non),
  plus `AJOUTS` s'ils existent (même ignorés). Hors dépôt git : `HorsLimites` (la route se replie au poste).
- Jamais (même suivis par erreur) : les motifs `EXCLUS` (conception) et `EXCLUS_EN_PLUS` (autres fichiers de secrets
  courants), comparés sans tenir compte de la casse à CHAQUE segment du chemin (un dossier `.git`, `node_modules`,
  `.factory` à n'importe quel niveau ; un `.env` ou un `id_ed25519` dans n'importe quel dossier). Ils sont écartés en
  silence : c'est attendu.
- Écartés et nommés (une anomalie à dire) : nom dangereux (`nom_sur`), lien symbolique, jonction ou autre point
  d'analyse « substitut de nom » Windows sur le fichier OU sur un de ses dossiers parents, lien dur (un lien dur peut
  désigner `~/.ssh/id_ed25519` sous un nom anodin), fichier spécial, dossier (sous-module, dépôt imbriqué), fichier
  absent ou illisible, doublon d'un même fichier (casse différente dans l'index sous Windows).
- Archive (`ecrire_tar`) : USTAR, noms relatifs revérifiés, propriétaire 0, date 0, droits 0644 ou 0755, aucun dossier,
  aucun lien ; contenu lu par blocs (jamais tout en mémoire) ; limites `MAX_FICHIER`, `MAX_TOTAL`, `MAX_FICHIERS` ; un
  fichier qui change pendant la lecture arrête tout (`HorsLimites`) : l'archive partielle est à jeter par l'appelant.

Python 3.9 et bibliothèque standard seulement : importé par le lanceur des agents (`deporter`, `campagne`).
"""
import fnmatch
import hashlib
import os
import re
import stat
import subprocess
import tarfile
from typing import BinaryIO, Callable, Dict, Iterable, List, Optional, Set, Tuple

MAX_FICHIER = 50 * 1024 * 1024
MAX_TOTAL = 200 * 1024 * 1024
MAX_FICHIERS = 50000

EXCLUS = (".git/", ".factory/", "node_modules/", ".env*", "*.pem", "*.key", "*.p12", "*.jks", "*.keystore", "id_rsa*",
          "id_ed25519*", "bureau.json", "*.local.json", "tests-sceau.json")
# Ajouts de l'implémentation (secrets courants hors de la liste de la conception) : autres clés SSH, magasins de
# certificats et de clés, jetons de gestionnaires de paquets, identifiants git/netrc/cloud, propriétés de signature
# Android, états Terraform, comptes de service. Même règle : n'importe quel segment, sans tenir compte de la casse.
EXCLUS_EN_PLUS = (".ssh/", ".aws/", ".azure/", ".gnupg/", ".docker/", ".kube/", "id_dsa*", "id_ecdsa*", "*.pfx", "*.p8",
                  "*.ppk", "*.kdbx", "*.asc", "*.gpg", ".npmrc", ".yarnrc.yml", ".pypirc", ".netrc", "_netrc",
                  ".git-credentials", ".gitconfig", "credentials.json", "client_secret*.json",
                  "service-account*.json", "token.json", "local.properties", "keystore.properties",
                  "signing.properties", "*.tfstate", "*.tfstate.*", "*.tfvars", ".htpasswd")
AJOUTS = (".durees-tests.json",)

DELAI_GIT_S = 60
LIMITE_USTAR_NOM, LIMITE_USTAR_PREFIXE = 100, 155
BLOC = 1024 * 1024

_ATTR_POINT_ANALYSE = 0x400                 # FILE_ATTRIBUTE_REPARSE_POINT
_ETIQUETTE_SUBSTITUT = 0x20000000           # bit « substitut de nom » : liens symboliques, jonctions, montages
_ETIQUETTE_NUAGE, _MASQUE_NUAGE = 0x9000001A, 0xFFFF0FFF   # IO_REPARSE_TAG_CLOUD_* (fichiers OneDrive à la demande)
_NOMS_RESERVES_WINDOWS = frozenset(["con", "prn", "aux", "nul", "conin$", "conout$"]
                                   + ["com%d" % i for i in range(10)] + ["lpt%d" % i for i in range(10)])
_LECTEUR = re.compile(r"^[A-Za-z]:")
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_MOTIFS = tuple(m.rstrip("/").lower() for m in EXCLUS + EXCLUS_EN_PLUS)

Git = Callable[[List[str], str], Tuple[int, str]]


class HorsLimites(Exception):
    """L'instantané ne peut pas partir ; `.raison` (français) dit pourquoi, la route se replie au poste."""

    def __init__(self, raison: str):
        Exception.__init__(self, raison)
        self.raison = raison


def _git_local(argv: List[str], cwd: str) -> Tuple[int, str]:
    """(code, sortie) de git, sortie décodée en UTF-8 avec `surrogateescape` (un nom non UTF-8 ne se réencode pas et
    sera écarté par `nom_sur`) ; (127, message) si git est absent ou bloqué."""
    try:
        f = subprocess.run(["git", "-c", "core.quotepath=off"] + list(argv), cwd=str(cwd), capture_output=True,
                           timeout=DELAI_GIT_S, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)
    sortie = f.stdout if f.returncode == 0 else (f.stderr or f.stdout)
    return f.returncode, (sortie or b"").decode("utf-8", "surrogateescape")


def nom_sur(nom: str) -> bool:
    """Vrai si `nom` peut entrer tel quel dans l'archive : relatif, segments non vides, ni `.` ni `..`, ni `\\`, ni octet
    nul ni caractère de contrôle, ni lettre de lecteur, UTF-8 valide, et qu'il tient en USTAR (100 octets de nom et 155
    de préfixe coupés à un `/`, 255 au plus)."""
    if not isinstance(nom, str) or not nom or nom.startswith("/") or "\\" in nom or _CONTROLE.search(nom):
        return False
    if _LECTEUR.match(nom) or any(s in ("", ".", "..") for s in nom.split("/")):
        return False
    try:
        octets = nom.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if len(octets) <= LIMITE_USTAR_NOM:
        return True
    if len(octets) > LIMITE_USTAR_NOM + 1 + LIMITE_USTAR_PREFIXE:
        return False
    return any(o == 0x2F and i <= LIMITE_USTAR_PREFIXE and len(octets) - i - 1 <= LIMITE_USTAR_NOM
               for i, o in enumerate(octets))


def _exclu(nom: str) -> bool:
    return any(fnmatch.fnmatchcase(segment.lower(), motif) for segment in nom.split("/") for motif in _MOTIFS)


def _nom_windows_douteux(nom: str) -> bool:
    """Sous Windows, ces noms désignent autre chose que le fichier de l'index : flux secondaire (`a:b`), périphérique
    (`nul`, `com1.txt`), fichier voisin (`a.py.` ou `a.py ` ouvrent `a.py`)."""
    for segment in nom.split("/"):
        if ":" in segment or segment.endswith((".", " ")):
            return True
        if segment.split(".")[0].rstrip(" ").lower() in _NOMS_RESERVES_WINDOWS:
            return True
    return False


def _substitut(st: os.stat_result) -> bool:
    """Lien symbolique, jonction ou autre point d'analyse Windows (hors fichiers OneDrive à la demande)."""
    if stat.S_ISLNK(st.st_mode):
        return True
    if getattr(st, "st_file_attributes", 0) & _ATTR_POINT_ANALYSE:
        etiquette = getattr(st, "st_reparse_tag", 0)
        return bool(etiquette & _ETIQUETTE_SUBSTITUT) or (etiquette & _MASQUE_NUAGE) != _ETIQUETTE_NUAGE
    return False


def _chemin(racine: str, nom: str) -> str:
    return os.path.join(racine, *nom.split("/"))


def _verifier(racine: str, nom: str, parents: Dict[str, Optional[str]]) -> Tuple[Optional[os.stat_result], str]:
    """(stat du fichier, "") s'il peut partir, sinon (None, raison). `parents` met en cache la vérification des dossiers
    (chaque dossier parent doit être un vrai dossier : ni lien, ni jonction)."""
    if not nom_sur(nom):
        return None, "nom refusé"
    if os.name == "nt" and _nom_windows_douteux(nom):
        return None, "nom refusé sous Windows"
    segments = nom.split("/")
    for i in range(1, len(segments)):
        dossier = "/".join(segments[:i])
        if dossier not in parents:
            try:
                st = os.lstat(_chemin(racine, dossier))
                parents[dossier] = ("lien dans le chemin : " + dossier if _substitut(st)
                                    else None if stat.S_ISDIR(st.st_mode) else "chemin cassé : " + dossier)
            except FileNotFoundError:
                parents[dossier] = "absent du disque"
            except OSError:
                parents[dossier] = "illisible"
        if parents[dossier]:
            return None, parents[dossier]
    try:
        st = os.lstat(_chemin(racine, nom))
    except FileNotFoundError:
        return None, "absent du disque"
    except OSError:
        return None, "illisible"
    if _substitut(st):
        return None, "lien"
    if stat.S_ISDIR(st.st_mode):
        return None, "dossier : sous-module ou dépôt imbriqué"
    if not stat.S_ISREG(st.st_mode):
        return None, "fichier spécial"
    if st.st_nlink > 1:
        return None, "lien dur"
    return st, ""


def _affiche(nom: str) -> str:
    return nom if nom_sur(nom) else ascii(nom)


def lister(racine: str, git: Optional[Git] = None) -> Tuple[List[str], List[str]]:
    """(fichiers retenus triés, écartés nommés « nom (raison) ») ; `HorsLimites` hors dépôt git ou sans git."""
    git = git or _git_local
    code, sortie = git(["ls-files", "-co", "--exclude-standard", "-z"], racine)
    if code == 127:
        raise HorsLimites("git est introuvable sur le poste : " + sortie.strip()[:200])
    if code != 0:
        if "not a git repository" in sortie.lower() or "pas un dépôt git" in sortie.lower():
            raise HorsLimites("le projet n'est pas un dépôt git")
        raise HorsLimites("git ls-files a échoué (code %d) : %s" % (code, sortie.strip()[:200]))
    noms = [n for n in sortie.split("\0") if n]
    for ajout in AJOUTS:
        if ajout not in noms and os.path.lexists(_chemin(racine, ajout)):
            noms.append(ajout)
    retenus, ecartes = [], []           # type: List[str], List[str]
    parents = {}                        # type: Dict[str, Optional[str]]
    vus = {}                            # type: Dict[Tuple[int, int], str]
    for nom in sorted(set(noms)):
        if nom.endswith("/") and nom_sur(nom.rstrip("/")):
            if not _exclu(nom):
                ecartes.append("%s (dossier : sous-module ou dépôt imbriqué)" % nom.rstrip("/"))
            continue
        if nom_sur(nom) and _exclu(nom):
            continue
        st, raison = _verifier(racine, nom, parents)
        if st is None:
            ecartes.append("%s (%s)" % (_affiche(nom), raison))
            continue
        identite = (st.st_dev, st.st_ino)
        if st.st_ino and identite in vus:
            ecartes.append("%s (même fichier que %s)" % (nom, vus[identite]))
            continue
        vus[identite] = nom
        retenus.append(nom)
    return retenus, ecartes


def executables(racine: str, git: Optional[Git] = None) -> Set[str]:
    """Noms que l'index git marque exécutables (mode 100755) : sous Windows, le disque ne porte pas ce bit."""
    code, sortie = (git or _git_local)(["ls-files", "-s", "-z"], racine)
    if code != 0:
        return set()
    resultat = set()
    for entree in sortie.split("\0"):
        tete, _, nom = entree.partition("\t")
        if nom and tete.split(" ")[0] == "100755":
            resultat.add(nom)
    return resultat


def _mo(octets: int) -> str:
    return ("%.1f Mo" % (octets / (1024 * 1024))).replace(".", ",")


class _Lecteur:
    """Rend au plus `taille` octets du fichier, par blocs ; une fin prématurée est signalée par `court`."""

    def __init__(self, fichier, taille: int):
        self.fichier, self.reste, self.court = fichier, taille, False

    def read(self, n: int = -1) -> bytes:
        n = self.reste if n is None or n < 0 else min(n, self.reste)
        donnees = self.fichier.read(min(n, BLOC)) if n else b""
        if n and not donnees:
            self.court = True
        self.reste -= len(donnees)
        return donnees


def ecrire_tar(racine: str, fichiers: Iterable[str], destination: BinaryIO,
               executables: Optional[Iterable[str]] = None) -> Tuple[int, int]:
    """Écrit l'archive USTAR de `fichiers` (relatifs à `racine`) dans `destination` (flux en écriture, sans retour en
    arrière) ; (nombre de fichiers, octets de contenu). Droits 0755 si le fichier est exécutable sur le disque, commence
    par `#!` ou est dans `executables` (voir `executables()`), 0644 sinon. Chaque fichier est revérifié (nom, exclusions,
    liens) ; `HorsLimites` au premier refus, à la première limite dépassée ou à un fichier qui change pendant sa lecture."""
    fichiers = list(fichiers)
    if len(fichiers) > MAX_FICHIERS:
        raise HorsLimites("trop de fichiers : %d (%d au plus)" % (len(fichiers), MAX_FICHIERS))
    exec_git = set(executables or ())
    parents = {}                        # type: Dict[str, Optional[str]]
    total = 0
    with tarfile.open(fileobj=destination, mode="w|", format=tarfile.USTAR_FORMAT, encoding="utf-8",
                      errors="strict") as tar:
        for nom in fichiers:
            if nom_sur(nom) and _exclu(nom):
                raise HorsLimites("fichier exclu de l'instantané : " + nom)
            st, raison = _verifier(racine, nom, parents)
            if st is None:
                raise HorsLimites("fichier refusé : %s (%s)" % (_affiche(nom), raison))
            if st.st_size > MAX_FICHIER:
                raise HorsLimites("fichier trop gros : %s (%s, %s au plus)" % (nom, _mo(st.st_size), _mo(MAX_FICHIER)))
            total += st.st_size
            if total > MAX_TOTAL:
                raise HorsLimites("instantané trop gros : plus de %s" % _mo(MAX_TOTAL))
            with open(_chemin(racine, nom), "rb") as source:
                ouvert = os.fstat(source.fileno())
                if (ouvert.st_size != st.st_size or (st.st_ino and ouvert.st_ino and ouvert.st_ino != st.st_ino)
                        or not stat.S_ISREG(ouvert.st_mode)):
                    raise HorsLimites("fichier modifié pendant la lecture : " + nom)
                debut = source.read(2)
                source.seek(0)
                info = tarfile.TarInfo(nom)
                info.size, info.mtime, info.type = st.st_size, 0, tarfile.REGTYPE
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                executable = bool(st.st_mode & 0o111) and os.name != "nt"
                info.mode = 0o755 if (executable or debut == b"#!" or nom in exec_git) else 0o644
                lecteur = _Lecteur(source, st.st_size)
                try:
                    tar.addfile(info, lecteur)
                except OSError:
                    raise HorsLimites("fichier modifié pendant la lecture : " + nom) from None
                if lecteur.court or source.read(1) or os.fstat(source.fileno()).st_mtime_ns != ouvert.st_mtime_ns:
                    raise HorsLimites("fichier modifié pendant la lecture : " + nom)
    return len(fichiers), total


def empreinte_verrou_node(racine: str) -> Optional[str]:
    """16 hexa du SHA-256 de `package-lock.json` à la racine (fichier ordinaire, pas un lien), sinon None."""
    chemin = os.path.join(racine, "package-lock.json")
    try:
        st = os.lstat(chemin)
    except OSError:
        return None
    if _substitut(st) or not stat.S_ISREG(st.st_mode):
        return None
    empreinte = hashlib.sha256()
    try:
        with open(chemin, "rb") as f:
            for bloc in iter(lambda: f.read(BLOC), b""):
                empreinte.update(bloc)
    except OSError:
        return None
    return empreinte.hexdigest()[:16]
