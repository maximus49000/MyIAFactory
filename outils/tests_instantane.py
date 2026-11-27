"""Instantané de l'arbre de travail envoyé au serveur pour une campagne de tests (conception § 5.2 et § 6).

Ce module décide de CE QUI QUITTE LE POSTE : il est volontairement strict, et chaque doute écarte le fichier.

- Liste : `git ls-files -co --exclude-standard -z` dans la racine (suivis et non suivis non ignorés, commités ou non),
  plus `AJOUTS` s'ils existent (même ignorés). Hors dépôt git : `HorsLimites` (la route se replie au poste). Git est lancé
  durci (`_git_local`) : le dépôt est écrit par des agents, sa configuration ne doit rien pouvoir exécuter.
- Jamais (même suivis par erreur) : les motifs `EXCLUS` (conception) et `EXCLUS_EN_PLUS` (autres fichiers de secrets
  courants, dont la licence et la session Unity : `*.ulf`, `Unity_lic`, `Unity_lic.*`, `UnityEntitlementLicense*`,
  `Unity.Licensing.Client*`, `Unity-LicenseClient-*`, `unityhub/`), comparés sans tenir compte de la casse à CHAQUE segment du chemin (un dossier
  `.git`, `node_modules`, `.factory` à n'importe quel niveau ; un `.env` ou un `id_ed25519` dans n'importe quel dossier),
  et les suites de segments `EXCLUS_SEGMENTS` (`.config/unity3d/`, `.local/share/unity3d/`, à n'importe quel niveau).
  `exclus_de_famille` y ajoute, à la racine seulement, les dossiers générés de la famille (`Library/`, `Temp/`… pour Unity). Ils sont écartés en
  silence : c'est attendu. Règle de contenu en plus des noms : les 64 premiers Ko de chaque fichier texte sont lus, et une
  clé privée PEM avec son corps base64 (au moins 2 lignes de 40 caractères après l'en-tête ; un en-tête seul cité dans du
  code n'en est pas une) ou un compte de service Google (`"client_email"` et un `"private_key"` qui contient une telle
  clé) écarte le fichier (« clé privée »).
- Écartés et nommés (une anomalie à dire) : nom dangereux (`nom_sur`) ; sous Windows, nom court 8.3 (`ENV~1` désigne
  `.env`), flux secondaire (`a:b`), périphérique (`nul.txt`), point ou espace final ; lien symbolique, jonction ou point
  d'analyse Windows inconnu sur le fichier OU sur un de ses dossiers parents ; lien dur (un lien dur peut désigner
  `~/.ssh/id_ed25519` sous un nom anodin) ; fichier spécial ; dossier (sous-module, dépôt imbriqué) ; fichier absent du
  disque sans que git le sache supprimé, ou illisible ; doublon d'un même fichier (casse différente dans l'index) ; chemin
  réel du fichier ouvert différent du nom demandé (vérifié sur le descripteur ouvert : nom court, lien ou jonction
  glissés entre la vérification et l'ouverture). Les fichiers suivis supprimés du disque ne sont pas nommés.
- Archive (`ecrire_tar`) : USTAR, chaque fichier revérifié comme ci-dessus, propriétaire 0, date 0, droits 0644 ou 0755,
  aucun dossier, aucun lien ; contenu lu par blocs (jamais tout en mémoire) ; limites `MAX_FICHIER`, `MAX_TOTAL`,
  `MAX_FICHIERS` ; un fichier qui change pendant la lecture arrête tout (`HorsLimites`) : l'archive partielle est à jeter
  par l'appelant.

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
          "id_ed25519*", "bureau.json", "*.local.json", "tests-sceau.json", "local.properties")
# Ajouts de l'implémentation (secrets courants hors de la liste de la conception) : autres clés SSH, magasins de
# certificats et de clés, jetons de gestionnaires de paquets, identifiants git/netrc/cloud/bases, propriétés de signature
# Android, états Terraform, comptes de service, secrets d'outils (Streamlit, Wrangler, Azure, MCP). Même règle : n'importe
# quel segment, sans tenir compte de la casse. Restent volontairement admis : google-services.json,
# GoogleService-Info.plist, gradle.properties, appsettings.*.json, *.user, .vscode/ (nécessaires aux builds).
EXCLUS_EN_PLUS = (".ssh/", ".aws/", ".azure/", ".gnupg/", ".docker/", ".kube/", ".m2/", ".streamlit/", "id_dsa*",
                  "id_ecdsa*", "*.pfx", "*.p8", "*.ppk", "*.kdbx", "*.asc", "*.gpg", "*.env", "*.secret", "*.secrets",
                  "*.publishsettings", ".npmrc", ".yarnrc.yml", ".pypirc", ".netrc", "_netrc", ".pgpass",
                  ".git-credentials", ".gitconfig", ".dev.vars", ".mcp.json", "credentials.json",
                  "client_secret*.json", "service-account*.json", "*-firebase-adminsdk-*.json", "token.json",
                  "keystore.properties", "signing.properties", "secrets.properties",
                  "secrets.toml", "*.tfstate", "*.tfstate.*", "*.tfvars", ".htpasswd",
                  # Licence et session Unity (§ 5.16) : jamais au serveur, même suivies par erreur.
                  "*.ulf", "Unity_lic", "Unity_lic.*", "UnityEntitlementLicense*", "Unity.Licensing.Client*",
                  "Unity-LicenseClient-*", "unityhub/")
# Suites de segments consécutifs, à n'importe quel niveau, sans tenir compte de la casse (préférences et licences Unity de
# l'utilisateur) : un `Assets/Unity3D/` du projet reste admis.
EXCLUS_SEGMENTS = (".config/unity3d/", ".local/share/unity3d/")
AJOUTS = (".durees-tests.json",)
# Instantané maximal par famille (conception § 5.14) : 200 Mo, 1 Go pour les moteurs de jeu (ressources lourdes).
EXCLUS_DE_FAMILLE = {"unity": ("Library/", "Temp/", "Logs/", "UserSettings/", "obj/", "Build/", "Builds/")}
MAX_TOTAL_FAMILLE = {"godot": 1024 * 1024 * 1024, "unity": 1024 * 1024 * 1024}


def exclus_de_famille(famille: Optional[str]) -> Tuple[str, ...]:
    """Les dossiers d'une famille qui ne partent pas, à la RACINE du projet seulement (`Library/` de la racine Unity, pas
    `Assets/Library/`) : générés par l'éditeur, lourds et sans valeur pour un test."""
    return EXCLUS_DE_FAMILLE.get(famille or "", ())


def limites_pour(famille: Optional[str]) -> Dict[str, int]:
    """Les limites de l'instantané d'une famille de projet : `max_fichier`, `max_total`, `max_fichiers`."""
    return {"max_fichier": MAX_FICHIER, "max_total": MAX_TOTAL_FAMILLE.get(famille or "", MAX_TOTAL),
            "max_fichiers": MAX_FICHIERS}

DELAI_GIT_S = 60
LIMITE_USTAR_NOM, LIMITE_USTAR_PREFIXE = 100, 155
BLOC = 1024 * 1024
LECTURE_CONTENU = 64 * 1024              # octets lus au début de chaque fichier texte pour la règle de contenu
# Fichiers binaires dont le contenu n'est pas examiné (borne le coût de la règle de contenu sur un gros arbre).
EXTENSIONS_BINAIRES = frozenset(
    ".png .jpg .jpeg .gif .webp .bmp .ico .tif .tiff .psd .svgz .mp3 .mp4 .m4a .wav .ogg .flac .mov .avi .webm .mkv "
    ".zip .gz .tgz .bz2 .xz .7z .rar .zst .jar .aar .apk .aab .war .class .dex .so .dll .exe .dylib .a .lib .o .obj "
    ".pyc .pyd .whl .glb .fbx .blend .ttf .otf .woff .woff2 .eot .pdf .sqlite .db .bin".split())
_CLE_PEM = re.compile(rb"-----BEGIN [A-Z0-9 ]{0,60}PRIVATE KEY-----")
_FIN_PEM = re.compile(rb"-----END [A-Z0-9 ]{0,60}PRIVATE KEY-----")
_SEPARATEUR_PEM = re.compile(rb"\r?\n|(?:\\r)?\\n")       # vrai retour à la ligne ou `\n` échappé (chaîne JSON)
_LIGNE_BASE64 = re.compile(rb"[A-Za-z0-9+/=]{40,}")
_CLE_GOOGLE = re.compile(rb'"private_key"\s*:\s*"(-----BEGIN[^"]{0,8192})')

_ATTR_POINT_ANALYSE = 0x400                 # FILE_ATTRIBUTE_REPARSE_POINT
_ETIQUETTE_SUBSTITUT = 0x20000000           # bit « substitut de nom » : liens symboliques, jonctions, montages
_ETIQUETTE_NUAGE, _MASQUE_NUAGE = 0x9000001A, 0xFFFF0FFF   # IO_REPARSE_TAG_CLOUD_* (fichiers OneDrive à la demande)
_ETIQUETTES_LISIBLES = (0x80000013, 0x80000017)            # déduplication, WOF (compression Windows)
_NOMS_RESERVES_WINDOWS = frozenset(["con", "prn", "aux", "nul", "conin$", "conout$"]
                                   + ["com%d" % i for i in range(10)] + ["lpt%d" % i for i in range(10)])
_LECTEUR = re.compile(r"^[A-Za-z]:")
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_NOM_COURT = re.compile(r"~\d")
_MOTIFS = tuple(m.rstrip("/").lower() for m in EXCLUS + EXCLUS_EN_PLUS)
_SUITES = tuple(tuple(m.strip("/").lower().split("/")) for m in EXCLUS_SEGMENTS)
_GIT_DURCI = ("-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "-c", "core.hooksPath=" + os.devnull,
              "-c", "core.quotepath=off")
_MODIFIE = "fichier modifié pendant la lecture : "

Git = Callable[[List[str], str], Tuple[int, str]]


class HorsLimites(Exception):
    """L'instantané ne peut pas partir ; `.raison` (français) dit pourquoi, la route se replie au poste."""

    def __init__(self, raison: str):
        Exception.__init__(self, raison)
        self.raison = raison


# ---------------------------------------------------------------- git

def _env_git() -> Dict[str, str]:
    """Environnement hérité sans aucune variable `GIT_*` (GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, GIT_CONFIG_PARAMETERS,
    GIT_CONFIG_COUNT/KEY_*/VALUE_*, GIT_CEILING_DIRECTORIES…), sans configuration système, sans invite, sans verrou
    facultatif (git ne réécrit pas l'index)."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return env


def _git_local(argv: List[str], cwd: str) -> Tuple[int, str]:
    """(code, sortie) de git durci : ni fsmonitor (une commande de la configuration du dépôt), ni cache des non suivis,
    ni crochets, environnement nettoyé (`_env_git`). Sortie décodée en UTF-8 avec `surrogateescape` (un nom non UTF-8 ne
    se réencode pas et sera écarté par `nom_sur`) ; (127, message) si git est absent ou bloqué."""
    try:
        f = subprocess.run(["git"] + list(_GIT_DURCI) + list(argv), cwd=str(cwd), capture_output=True,
                           timeout=DELAI_GIT_S, stdin=subprocess.DEVNULL, env=_env_git(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)
    sortie = f.stdout if f.returncode == 0 else (f.stderr or f.stdout)
    return f.returncode, (sortie or b"").decode("utf-8", "surrogateescape")


# ---------------------------------------------------------------- noms

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
    segments = [s.lower() for s in nom.split("/")]
    if any(fnmatch.fnmatchcase(segment, motif) for segment in segments for motif in _MOTIFS):
        return True
    return any(segments[i:i + len(suite)] == list(suite) for suite in _SUITES for i in range(len(segments)))


def _exclu_famille(nom: str, famille: Optional[str], exclus: Iterable[str] = ()) -> bool:
    """Vrai si `nom` est sous un dossier de `exclus_de_famille(famille)` ou de `exclus` (les dossiers que le projet déclare
    ne pas envoyer, voir `exclus_valides`), à la racine (sans tenir compte de la casse)."""
    bas = nom.lower()
    return any(bas.startswith(d.lower()) for d in tuple(exclus_de_famille(famille)) + tuple(exclus))


MAX_EXCLUS = 16


def exclus_valides(valeurs: object) -> Tuple[str, ...]:
    """Les dossiers que le projet déclare ne pas envoyer (réglage `tests.exclus_instantane`) : une liste de chemins relatifs
    à la racine, chacun un dossier (`android_app/`). Une entrée invalide (pas du texte, vide, absolue, `..`, antislash,
    deux-points, caractère nul, trop longue) est IGNORÉE : elle n'exclut rien, donc davantage part, jamais moins que voulu par
    erreur. Au plus `MAX_EXCLUS` ; rendu normalisé (barre oblique, un `/` final), sans doublon."""
    if not isinstance(valeurs, (list, tuple)):
        return ()
    rendus = []                         # type: List[str]
    for v in valeurs[:MAX_EXCLUS]:
        if not isinstance(v, str):
            continue
        d = v.strip()
        if not d or len(d) > 200 or d.startswith("/") or chr(92) in d or ":" in d or chr(0) in d:
            continue
        morceaux = [m for m in d.split("/") if m]
        if not morceaux or any(m in (".", "..") for m in morceaux):
            continue
        d = "/".join(morceaux) + "/"
        if d.lower() not in [x.lower() for x in rendus]:
            rendus.append(d)
    return tuple(rendus)


def _nom_windows_douteux(nom: str) -> Optional[str]:
    """Sous Windows, ces noms désignent autre chose que le fichier de l'index : nom court 8.3 (`ENV~1` → `.env`), flux
    secondaire (`a:b`), périphérique (`nul`, `com1.txt`), fichier voisin (`a.py.` ou `a.py ` ouvrent `a.py`)."""
    for segment in nom.split("/"):
        if _NOM_COURT.search(segment):
            return "nom court 8.3"
        if ":" in segment or segment.endswith((".", " ")):
            return "nom refusé sous Windows"
        if segment.split(".")[0].rstrip(" ").lower() in _NOMS_RESERVES_WINDOWS:
            return "nom refusé sous Windows"
    return None


def _affiche(nom: str) -> str:
    return nom if nom_sur(nom) else ascii(nom)


# ---------------------------------------------------------------- disque

def _analyse(st: os.stat_result) -> Optional[str]:
    """None : entrée ordinaire ; « lire » : point d'analyse admis à condition de se lire (OneDrive à la demande,
    déduplication, compression WOF) ; sinon la raison du refus (lien, jonction, point d'analyse inconnu)."""
    if stat.S_ISLNK(st.st_mode):
        return "lien"
    if not (getattr(st, "st_file_attributes", 0) or 0) & _ATTR_POINT_ANALYSE:
        return None
    etiquette = getattr(st, "st_reparse_tag", 0) or 0
    if etiquette & _ETIQUETTE_SUBSTITUT:
        return "lien"
    if (etiquette & _MASQUE_NUAGE) == _ETIQUETTE_NUAGE or etiquette in _ETIQUETTES_LISIBLES:
        return "lire"
    return "point d'analyse Windows inconnu (étiquette 0x%08X)" % etiquette


def _chemin(racine: str, nom: str) -> str:
    return os.path.join(racine, *nom.split("/"))


def _verifier(racine: str, nom: str, parents: Dict[str, Optional[str]]) -> Tuple[Optional[os.stat_result], str]:
    """(stat du fichier, "") s'il peut partir, sinon (None, raison). `parents` met en cache la vérification des dossiers
    (chaque dossier parent doit être un vrai dossier : ni lien, ni jonction). `HorsLimites` si le disque ne donne pas
    l'identité des fichiers (sans elle, un remplacement entre vérification et lecture passerait inaperçu)."""
    if not nom_sur(nom):
        return None, "nom refusé"
    if os.name == "nt":
        douteux = _nom_windows_douteux(nom)
        if douteux:
            return None, douteux
    segments = nom.split("/")
    for i in range(1, len(segments)):
        dossier = "/".join(segments[:i])
        if dossier not in parents:
            try:
                st = os.lstat(_chemin(racine, dossier))
                genre = _analyse(st)
                if genre not in (None, "lire"):
                    parents[dossier] = "%s dans le chemin : %s" % (genre, dossier)
                else:
                    parents[dossier] = None if stat.S_ISDIR(st.st_mode) else "chemin cassé : " + dossier
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
    genre = _analyse(st)
    if genre not in (None, "lire"):
        return None, genre
    if stat.S_ISDIR(st.st_mode):
        return None, "dossier : sous-module ou dépôt imbriqué"
    if not stat.S_ISREG(st.st_mode):
        return None, "fichier spécial"
    if st.st_nlink > 1:
        return None, "lien dur"
    if not st.st_ino:
        raise HorsLimites("le disque du projet ne donne pas l'identité des fichiers (numéro nul, %s) : un remplacement "
                          "pendant la lecture ne serait pas vu" % nom)
    return st, ""


_final_par_descripteur = None   # type: Optional[Callable[[int], Optional[str]]]


def _final_windows(fd: int) -> Optional[str]:
    """Chemin réel du fichier OUVERT (GetFinalPathNameByHandleW sur son descripteur), noms longs, liens résolus."""
    global _final_par_descripteur
    if _final_par_descripteur is None:
        try:
            import ctypes
            import msvcrt
            from ctypes import wintypes
            fonction = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
            fonction.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
            fonction.restype = wintypes.DWORD

            def par_descripteur(d):
                tampon = ctypes.create_unicode_buffer(32768)
                n = fonction(msvcrt.get_osfhandle(d), tampon, 32768, 0)
                return tampon.value if 0 < n < 32768 else None
            _final_par_descripteur = par_descripteur
        except (ImportError, AttributeError, OSError):
            _final_par_descripteur = lambda d: None  # noqa: E731
    try:
        return _final_par_descripteur(fd)
    except (OSError, ValueError):
        return None


def _sans_prefixe(chemin: str) -> str:
    if chemin.startswith("\\\\?\\UNC\\"):
        return "\\\\" + chemin[8:]
    return chemin[4:] if chemin.startswith("\\\\?\\") else chemin


def _racine_reelle(racine: str) -> str:
    """Chemin réel de la racine (les liens AU-DESSUS de la racine sont admis : copies de travail, dossiers déplacés)."""
    try:
        if os.name == "nt":
            import nt
            return _sans_prefixe(nt._getfinalpathname(racine))
        return os.path.realpath(racine)
    except (ImportError, AttributeError, OSError):
        raise HorsLimites("chemin réel du projet invérifiable : " + str(racine)) from None


def _chemin_reel(fd: int, chemin: str) -> Optional[str]:
    if os.name == "nt":
        reel = _final_windows(fd)
        return _sans_prefixe(reel) if reel else None
    try:
        return os.readlink("/proc/self/fd/%d" % fd) if os.path.isdir("/proc/self/fd") else os.path.realpath(chemin)
    except OSError:
        return None


def _ouvrir(racine: str, racine_reelle: str, nom: str, st: os.stat_result):
    """(fichier ouvert, "") si le fichier ouvert est bien celui vérifié : même identité (périphérique, numéro), fichier
    ordinaire, et chemin réel du descripteur égal à racine/nom (sans casse sous Windows). Sinon (None, raison) ; une
    vérification impossible refuse."""
    try:
        f = open(_chemin(racine, nom), "rb")
    except OSError:
        return None, "illisible"
    try:
        ouvert = os.fstat(f.fileno())
        if not stat.S_ISREG(ouvert.st_mode) or (ouvert.st_dev, ouvert.st_ino) != (st.st_dev, st.st_ino):
            raison = "remplacé pendant la lecture"
        else:
            reel = _chemin_reel(f.fileno(), _chemin(racine, nom))
            attendu = os.path.join(racine_reelle, *nom.split("/"))
            if reel is None:
                raison = "chemin réel invérifiable"
            elif (reel.casefold() == attendu.casefold()) if os.name == "nt" else (reel == attendu):
                return f, ""
            else:
                raison = "chemin réel différent du nom (nom court, lien ou jonction)"
    except OSError:
        raison = "illisible"
    f.close()
    return None, raison


def _a_examiner(nom: str) -> bool:
    return os.path.splitext(nom)[1].lower() not in EXTENSIONS_BINAIRES


def _pem_avec_corps(debut: bytes) -> bool:
    """Un en-tête `-----BEGIN … PRIVATE KEY-----` suivi d'au moins 2 lignes de corps base64 (>= 40 caractères) avant
    le `-----END … PRIVATE KEY-----` (ou la fin de la lecture bornée). Les lignes sont séparées par de vrais retours ou
    par des `\\n` échappés (clé rangée dans une chaîne JSON). Un en-tête seul, cité comme motif, expression régulière ou
    exemple dans du code source, n'est pas une clé."""
    for m in _CLE_PEM.finditer(debut):
        suite = debut[m.end():]
        fin = _FIN_PEM.search(suite)
        corps = suite[:fin.start()] if fin else suite
        if sum(1 for ligne in _SEPARATEUR_PEM.split(corps) if _LIGNE_BASE64.fullmatch(ligne.strip())) >= 2:
            return True
    return False


def _contenu_secret(debut: bytes) -> bool:
    """Clé privée PEM/OpenSSH avec son corps base64, ou compte de service Google (`"private_key"` dont la valeur est
    une clé PEM avec corps, et `"client_email"`). Un fichier qui ne fait que nommer ces champs ou l'en-tête PEM n'est
    pas écarté."""
    if _pem_avec_corps(debut):
        return True
    if b'"client_email"' not in debut:
        return False
    return any(_pem_avec_corps(m.group(1)) for m in _CLE_GOOGLE.finditer(debut))


# ---------------------------------------------------------------- liste

def lister(racine: str, git: Optional[Git] = None, famille: Optional[str] = None,
           exclus: Iterable[str] = ()) -> Tuple[List[str], List[str]]:
    """(fichiers retenus triés, écartés nommés « nom (raison) ») ; `famille` ajoute les dossiers de `exclus_de_famille`,
    écartés en silence comme les `EXCLUS`, comme `exclus` (dossiers que le projet déclare ne pas envoyer) ;
    `HorsLimites` hors dépôt git, sans git, au-delà de
    MAX_FICHIERS candidats ou sur un disque sans identité de fichier."""
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
    retenus, ecartes, candidats = [], [], []    # type: List[str], List[str], List[str]
    for nom in sorted(set(noms)):
        if nom.endswith("/") and nom_sur(nom.rstrip("/")):
            if not _exclu(nom):
                ecartes.append("%s (dossier : sous-module ou dépôt imbriqué)" % nom.rstrip("/"))
            continue
        if nom_sur(nom) and (_exclu(nom) or _exclu_famille(nom, famille, exclus)):
            continue
        candidats.append(nom)
    if len(candidats) > MAX_FICHIERS:
        raise HorsLimites("trop de fichiers : %d (%d au plus)" % (len(candidats), MAX_FICHIERS))
    code, sortie = git(["ls-files", "-d", "-z"], racine)
    supprimes = set(n for n in sortie.split("\0") if n) if code == 0 else set()
    racine_reelle = _racine_reelle(racine)
    parents = {}                        # type: Dict[str, Optional[str]]
    vus = {}                            # type: Dict[object, str]
    for nom in candidats:
        st, raison = _verifier(racine, nom, parents)
        if st is None:
            if not (raison == "absent du disque" and nom in supprimes):
                ecartes.append("%s (%s)" % (_affiche(nom), raison))
            continue
        cles = [(st.st_dev, st.st_ino)] + ([nom.casefold()] if os.name == "nt" else [])
        double = next((vus[c] for c in cles if c in vus), None)
        if double is not None:
            ecartes.append("%s (même fichier que %s)" % (nom, double))
            continue
        f, raison = _ouvrir(racine, racine_reelle, nom, st)
        if f is None:
            ecartes.append("%s (%s)" % (nom, raison))
            continue
        with f:
            try:
                debut = f.read(LECTURE_CONTENU) if (_a_examiner(nom) or _analyse(st) == "lire") else b""
            except OSError:
                ecartes.append("%s (%s)" % (nom, "illisible (fichier à la demande, dédupliqué ou compressé)"
                                            if _analyse(st) == "lire" else "illisible"))
                continue
        if _a_examiner(nom) and _contenu_secret(debut):
            ecartes.append("%s (clé privée)" % nom)
            continue
        for c in cles:
            vus[c] = nom
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


# ---------------------------------------------------------------- archive

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
               executables: Optional[Iterable[str]] = None, famille: Optional[str] = None,
               exclus: Iterable[str] = ()) -> Tuple[int, int]:
    """Écrit l'archive USTAR de `fichiers` (relatifs à `racine`) dans `destination` (flux en écriture, sans retour en
    arrière) ; (nombre de fichiers, octets de contenu). Droits 0755 si le fichier est exécutable sur le disque, commence
    par `#!` ou est dans `executables` (voir `executables()`), 0644 sinon. Chaque fichier est revérifié (nom, exclusions,
    liens, doublons, chemin réel, clé privée) ; `HorsLimites` au premier refus, à la première limite dépassée ou à un
    fichier qui change pendant sa lecture."""
    fichiers = list(fichiers)
    if len(fichiers) > MAX_FICHIERS:
        raise HorsLimites("trop de fichiers : %d (%d au plus)" % (len(fichiers), MAX_FICHIERS))
    exec_git = set(executables or ())
    racine_reelle = _racine_reelle(racine)
    parents = {}                        # type: Dict[str, Optional[str]]
    vus = {}                            # type: Dict[object, str]
    total = 0
    with tarfile.open(fileobj=destination, mode="w|", format=tarfile.USTAR_FORMAT, encoding="utf-8",
                      errors="strict") as tar:
        for nom in fichiers:
            if nom_sur(nom) and (_exclu(nom) or _exclu_famille(nom, famille, exclus)):
                raise HorsLimites("fichier exclu de l'instantané : " + nom)
            st, raison = _verifier(racine, nom, parents)
            if st is None:
                raise HorsLimites("fichier refusé : %s (%s)" % (_affiche(nom), raison))
            cles = [(st.st_dev, st.st_ino)] + ([nom.casefold()] if os.name == "nt" else [])
            double = next((vus[c] for c in cles if c in vus), None)
            if double is not None:
                raise HorsLimites("même fichier sous deux noms : %s et %s" % (double, nom))
            for c in cles:
                vus[c] = nom
            if st.st_size > MAX_FICHIER:
                raise HorsLimites("fichier trop gros : %s (%s, %s au plus)" % (nom, _mo(st.st_size), _mo(MAX_FICHIER)))
            total += st.st_size
            maximum = MAX_TOTAL_FAMILLE.get(famille or "", MAX_TOTAL)       # la limite de la famille (`limites_pour`)
            if total > maximum:
                raise HorsLimites("instantané trop gros : plus de %s" % _mo(maximum))
            source, raison = _ouvrir(racine, racine_reelle, nom, st)
            if source is None:
                raise HorsLimites("fichier refusé : %s (%s)" % (nom, raison))
            lecteur = None
            with source:
                try:
                    ouvert = os.fstat(source.fileno())
                    if ouvert.st_size != st.st_size:
                        raise HorsLimites(_MODIFIE + nom)
                    debut = source.read(LECTURE_CONTENU)
                    if _a_examiner(nom) and _contenu_secret(debut):
                        raise HorsLimites("clé privée dans le fichier : " + nom)
                    source.seek(0)
                    info = tarfile.TarInfo(nom)
                    info.size, info.mtime, info.type = st.st_size, 0, tarfile.REGTYPE
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    executable = bool(st.st_mode & 0o111) and os.name != "nt"
                    info.mode = 0o755 if (executable or debut[:2] == b"#!" or nom in exec_git) else 0o644
                    lecteur = _Lecteur(source, st.st_size)
                    tar.addfile(info, lecteur)
                    if lecteur.court or source.read(1) or os.fstat(source.fileno()).st_mtime_ns != ouvert.st_mtime_ns:
                        raise HorsLimites(_MODIFIE + nom)
                except OSError:
                    if lecteur is not None and lecteur.court:
                        raise HorsLimites(_MODIFIE + nom) from None
                    raise HorsLimites("lecture impossible : " + nom) from None
    return len(fichiers), total


def empreinte_verrou_node(racine: str) -> Optional[str]:
    """16 hexa du SHA-256 de `package-lock.json` à la racine (fichier ordinaire, pas un lien), sinon None."""
    chemin = os.path.join(racine, "package-lock.json")
    try:
        st = os.lstat(chemin)
    except OSError:
        return None
    if _analyse(st) not in (None, "lire") or not stat.S_ISREG(st.st_mode):
        return None
    empreinte = hashlib.sha256()
    try:
        with open(chemin, "rb") as f:
            for bloc in iter(lambda: f.read(BLOC), b""):
                empreinte.update(bloc)
    except OSError:
        return None
    return empreinte.hexdigest()[:16]
