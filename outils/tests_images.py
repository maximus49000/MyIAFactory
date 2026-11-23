"""Catalogue des images des campagnes de tests au serveur et choix d'après le profil (conception § 5.12) : données et logique
pures (ni SSH ni docker). Les images dérivées (Node 18, JDK 11, .NET, Go…) sont construites ailleurs (tâche 14c) : ici,
`choisir_image` dit seulement qu'aucune image du catalogue ne convient (`derivee`).

`myiafactory/android` (Gradle 8.7, plateforme 34, root, curl) et `unityci/editor` ne sont PAS au catalogue des tests : le
premier ne convient à aucun projet réel (compileSdk 36, wrapper Gradle 9), le second ne sert que de base à une image
`myiafactory/tests-unity-<version>` (tâche 14g)."""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

IMAGE_DEFAUT = "myiafactory/tests"
# Sans réseau, une campagne Gradle ne réussit qu'avec un cache de dépendances préchauffé (§ 5.13). Vrai depuis la tâche 14d : le
# poste ne sait pas si le cache `.pret` existe au serveur, mais l'enveloppe le PRÉPARE quand il manque (échauffement, code 79 et
# repli au poste s'il échoue) ; les conditions restantes sont vérifiées par la route avant tout envoi : accord du réseau
# d'échauffement (code du projet, R5 sinon), sonde réelle du SDK de l'hôte (`tests_serveur.sonder_sdk` : plateformes,
# build-tools, NDK, licences), et au serveur le wrapper Gradle contre les sommes publiées. Le SDK est monté en copie sur écriture
# (AGP peut y écrire, ~/android-sdk jamais). Le garder comme interrupteur : faux renvoie tout Gradle au poste.
CACHE_GRADLE_PRET = True
# Motifs fermés (les mêmes que ceux de l'enveloppe hôte `taches/lancer_tests.sh`, qui ne croit jamais le poste).
MOTIF_IMAGE = re.compile(r"myiafactory/tests(-[a-z0-9]{1,24})?", re.ASCII)

CATALOGUE_IMAGES = {
    "myiafactory/tests": {"capacite": "tests-image", "familles": ("python", "node", "make"),
                          "outils": {"python": "3.12", "node": "22"}},
    "myiafactory/tests-android": {"capacite": "tests-android", "familles": ("gradle-android", "gradle-jvm"),
                                  "outils": {"jdk": ("17", "21")}},
}
# Outils du profil que l'image n'a pas à porter : Gradle vient du wrapper du projet ; le SDK Android est celui de l'hôte (sonde).
_FOURNIS_AILLEURS = ("gradle", "android")
_VERSION = re.compile(r"v?(\d{1,4})(?:\.(\d{1,4}))?")


def _majeure(outil: str, texte) -> Optional[tuple]:
    """(majeur,) ou (majeur, mineur) pour python : la précision qui décide de la compatibilité."""
    m = _VERSION.match(str(texte))
    if not m:
        return None
    return (m.group(1), m.group(2) or "0") if outil == "python" else (m.group(1),)


def _convient(profil, image: dict) -> bool:
    if not all(f in image["familles"] for f in profil.familles):
        return False
    for outil, version in profil.outils.items():
        if outil in _FOURNIS_AILLEURS:
            continue
        offerte = image["outils"].get(outil)
        if offerte is None:
            return False
        voulue = _majeure(outil, version)
        offertes = offerte if isinstance(offerte, tuple) else (offerte,)
        if voulue is None or voulue not in [_majeure(outil, o) for o in offertes]:
            return False
    return True


def _plateforme(x) -> str:
    return str(x) if str(x).startswith("android-") else f"android-{x}"


def _sdk_manquant(profil, sdk_android: Optional[dict]) -> list:
    """Ce que le profil exige du SDK de l'hôte et qu'il n'a pas ; `sdk_android` (relevé de `tests_serveur.sonder_sdk` :
    `{"platforms": [...], "build_tools": [...], "ndk": [...], "licences": [...]}`) None = non relevé, rien n'est dit ; sans la
    clé `licences`, les licences ne sont pas vérifiées."""
    info = profil.outils.get("android")
    if sdk_android is None or not isinstance(info, dict):
        return []
    manque = []
    plateformes = {_plateforme(p) for p in sdk_android.get("platforms") or ()}
    if info.get("compileSdk") and _plateforme(info["compileSdk"]) not in plateformes:
        manque.append(f"platforms;{_plateforme(info['compileSdk'])}")
    if info.get("build_tools") and str(info["build_tools"]) not in {str(b) for b in sdk_android.get("build_tools") or ()}:
        manque.append(f"build-tools;{info['build_tools']}")
    if info.get("ndk") and str(info["ndk"]) not in {str(n) for n in sdk_android.get("ndk") or ()}:
        manque.append(f"ndk;{info['ndk']}")
    # Sans la licence acceptée, AGP refuse d'utiliser le SDK (ou tente de l'installer : réseau et SDK en écriture).
    if "licences" in sdk_android and "android-sdk-license" not in (sdk_android.get("licences") or ()):
        manque.append("licenses;android-sdk-license")
    return manque


def choisir_image(profil, sdk_android: Optional[dict] = None) -> dict:
    """`{"image", "capacites", "derivee", "manque"}` : la première image du catalogue où chaque famille est connue et chaque
    outil du profil est à la même version majeure (Python : majeur.mineur). Une pile inconnue (aucune famille) reçoit l'image
    par défaut. Aucune image ne convient : `derivee` vrai, `image` None, `capacites` celle de l'image de base. Pour
    `gradle-android`, `manque` liste ce que le SDK de l'hôte n'a pas (`platforms;android-N`, `build-tools;V`, `ndk;V`)."""
    if not profil.familles:
        return {"image": IMAGE_DEFAUT, "capacites": [CATALOGUE_IMAGES[IMAGE_DEFAUT]["capacite"]], "derivee": False, "manque": []}
    for nom, image in CATALOGUE_IMAGES.items():
        if _convient(profil, image):
            manque = _sdk_manquant(profil, sdk_android) if "gradle-android" in profil.familles else []
            return {"image": nom, "capacites": [image["capacite"]], "derivee": False, "manque": manque}
    return {"image": None, "capacites": [CATALOGUE_IMAGES[IMAGE_DEFAUT]["capacite"]], "derivee": True, "manque": []}


# =====================================================================================================================
# Images dérivées (conception § 5.12, tâche 14c) : gabarit fermé, étiquette, registre local. CODE SENSIBLE : le Dockerfile
# rendu est construit au serveur avec accès au réseau (par `serveur_ovh/taches/construire_image_tests.sh`).
#
# Règles du gabarit : aucun texte du projet n'entre dans le Dockerfile. Seules les valeurs de `profil.outils` pour un outil de la
# table fermée `OUTILS`, après un `fullmatch` strict sur `MOTIFS_VERSION`, sont écrites (jamais autre chose : ni commande, ni
# nom de fichier, ni URL du projet). Chaque téléchargement va dans un fichier, puis sa somme est vérifiée contre une somme
# OFFICIELLE récupérée dans le même contexte de construction (jamais écrite ici : aucune somme n'est devinée) ; la construction
# échoue sinon (`set -e`, `sha*sum -c`). Interdits : `curl | sh`, `| bash`, nvm, sdkman, pyenv, `ADD <url>`.
# Racine de confiance de chaque téléchargement = TLS vers l'hôte officiel (voir le commentaire « Source » de chaque bloc) ; aucune
# vérification de signature GPG (clés non connues ici sans téléchargement).
# =====================================================================================================================
# Version du gabarit : change l'etiquette ET la somme du Dockerfile rendu (un gabarit corrige ne reutilise jamais l'ancienne image).
# La reproductibilite est celle du RENDU (memes octets a profil egal), pas du resultat de la construction : les sources officielles
# (dernieres versions, paquets apt) evoluent.
GABARIT_VERSION = "1"
REGISTRE = Path.home() / "MyIAFactory" / "tests-images.json"
ETIQUETTE_DERIVEE = re.compile(r"myiafactory/tests-[0-9a-f]{12}", re.ASCII)
EMPREINTE_64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
UNITY_GAMECI = "4.0.0"   # miroir de serveur_ovh/versions.json (unity_gameci : unityci/editor:ubuntu-<version>-android-4.0.0)
OPT = "/opt/outils"
# Ce que l'image de base `myiafactory/tests` porte déjà (aucun bloc si la version voulue y correspond, `_majeure`).
_BASE_OFFRE = CATALOGUE_IMAGES[IMAGE_DEFAUT]["outils"]
# Clés de `profil.outils` qui ne sont pas des outils à installer (Gradle vient du wrapper ; SDK Android de l'hôte ; révision Unity).
_IGNORES = _FOURNIS_AILLEURS + ("unity_revision",)

MOTIFS_VERSION = {
    "jdk": re.compile(r"[0-9]{1,2}", re.ASCII),                                   # majeur : paquet Ubuntu openjdk-<N>
    "node": re.compile(r"[0-9]{1,3}(\.[0-9]{1,4}\.[0-9]{1,4})?", re.ASCII),       # majeur ou X.Y.Z
    # X.Y seulement (dernier correctif de la derniere publication de python-build-standalone : un correctif precis ne peut pas
    # etre garanti) ; 3.12.N passe, la base le porte deja et aucun bloc n'est rendu.
    "python": re.compile(r"3\.12(\.[0-9]{1,2})?|3\.[0-9]{1,2}", re.ASCII),
    "maven": re.compile(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}", re.ASCII),         # version complète (dossier d'archive)
    "dotnet": re.compile(r"[0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,4})?", re.ASCII),     # canal X.Y (dernier SDK) ou SDK X.Y.Z
    "go": re.compile(r"[0-9]{1,2}\.[0-9]{1,3}(\.[0-9]{1,3})?", re.ASCII),
    "rust": re.compile(r"[0-9]{1,2}\.[0-9]{1,3}(\.[0-9]{1,2})?|stable|beta|nightly(-[0-9]{4}-[0-9]{2}-[0-9]{2})?", re.ASCII),
    "godot": re.compile(r"[0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,2})?(-stable)?", re.ASCII),
    "unity": re.compile(r"[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3}", re.ASCII),
}

# Estimations montrées dans la décision de Direction (taille de la couche en Mo, durée de construction en s).
_ESTIMATION = {"jdk": (400, 60), "node": (200, 60), "python": (120, 60), "maven": (120, 60), "dotnet": (700, 180),
               "go": (500, 120), "rust": (900, 300), "godot": (120, 90), "unity": (600, 120)}


def _re_points(v: str) -> str:
    return v.replace(".", r"\.")


def _run(*commandes: str) -> str:
    return "RUN " + " \\\n    && ".join(commandes)


def _telechargement(extra_apt: str, *commandes: str) -> str:
    """Une couche : curl installé, téléchargements vérifiés, curl purgé dans la MÊME couche (l'image n'a pas de client réseau)."""
    return _run("apt-get update",
                f"apt-get install -y --no-install-recommends curl ca-certificates{extra_apt}",
                f"install -d -m 0755 {OPT}",
                "mkdir /tmp/dl && cd /tmp/dl",
                *commandes,
                "cd / && rm -rf /tmp/dl",
                "apt-get purge -y curl",
                "rm -rf /var/lib/apt/lists/*")


def _lien(source: str, nom: str) -> str:
    return f"ln -sf {source} /usr/local/bin/{nom}"


def _bloc_jdk(v: str) -> str:
    # Source : paquets Ubuntu (signés par la distribution).
    home = f"/usr/lib/jvm/java-{v}-openjdk-amd64"
    return "\n".join([
        _run("apt-get update",
             f"apt-get install -y --no-install-recommends openjdk-{v}-jdk-headless",
             "rm -rf /var/lib/apt/lists/*",
             f"test -x {home}/bin/java",
             f"update-alternatives --set java {home}/bin/java",
             f"update-alternatives --set javac {home}/bin/javac"),
        f"ENV JAVA_HOME={home}"])


def _bloc_node(v: str) -> str:
    # Source : nodejs.org/dist, fichier SHASUMS256.txt du même répertoire (le fichier de sommes officiel de Node).
    base = f"https://nodejs.org/dist/v{v}" if "." in v else f"https://nodejs.org/dist/latest-v{v}.x"
    nom = f"node-v{_re_points(v)}" if "." in v else f"node-v{v}\\.[0-9]+\\.[0-9]+"
    dest = f"{OPT}/node-{v}"
    return _telechargement(
        " xz-utils",
        f'curl -fsSL -o SHASUMS256.txt "{base}/SHASUMS256.txt"',
        f"grep -E '^[0-9a-f]{{64}}  {nom}-linux-x64\\.tar\\.xz$' SHASUMS256.txt > somme.txt",
        'test "$(wc -l < somme.txt)" = 1',
        "archive=\"$(cut -d' ' -f3 somme.txt)\"",
        f'curl -fsSL -o "$archive" "{base}/$archive"',
        "sha256sum -c somme.txt",
        f'install -d -m 0755 {dest} && tar -xJf "$archive" -C {dest} --strip-components=1 --no-same-owner',
        *[_lien(f"{dest}/bin/{x}", x) for x in ("node", "npm", "npx")],
        f"node --version | grep '^v{v.split('.')[0]}\\.' >/dev/null")


def _bloc_python(v: str) -> str:
    # Source : github.com/astral-sh/python-build-standalone, fichier SHA256SUMS de la dernière version publiée.
    depot = "https://github.com/astral-sh/python-build-standalone/releases"
    nom = f"cpython-{_re_points(v)}" + r"\.[0-9]+"
    dest = f"{OPT}/python-{v}"
    mm = ".".join(v.split(".")[:2])
    return _telechargement(
        "",
        f'curl -fsSL -o SHA256SUMS "{depot}/latest/download/SHA256SUMS"',
        f"grep -E '^[0-9a-f]{{64}}  {nom}\\+[0-9]{{8}}-x86_64-unknown-linux-gnu-install_only\\.tar\\.gz$' SHA256SUMS"
        " | sort -V -k2,2 | tail -n 1 > somme.txt",
        'test "$(wc -l < somme.txt)" = 1',
        "archive=\"$(cut -d' ' -f3 somme.txt)\"",
        'jour="${archive#*+}" && jour="${jour%%-*}"',
        f'curl -fsSL -o "$archive" "{depot}/download/$jour/${{archive//+/%2B}}"',
        "sha256sum -c somme.txt",
        f'install -d -m 0755 {dest} && tar -xzf "$archive" -C {dest} --strip-components=1 --no-same-owner',
        *[_lien(f"{dest}/bin/python3", x) for x in ("python3", "python", f"python{mm}")],
        _lien(f"{dest}/bin/pip3", "pip3"),
        f"python3 --version | grep '^Python {_re_points(mm)}\\.' >/dev/null")


def _bloc_maven(v: str) -> str:
    # Source : archive.apache.org/dist/maven, fichier .sha512 voisin de l'archive.
    base = f"https://archive.apache.org/dist/maven/maven-{v.split('.')[0]}/{v}/binaries"
    fichier = f"apache-maven-{v}-bin.tar.gz"
    dest = f"{OPT}/maven-{v}"
    return _telechargement(
        "",
        f'curl -fsSL -o {fichier} "{base}/{fichier}"',
        f'curl -fsSL -o {fichier}.sha512 "{base}/{fichier}.sha512"',
        f"somme=\"$(cut -d' ' -f1 {fichier}.sha512)\"",
        f"printf '%s  %s\\n' \"$somme\" {fichier} > somme.txt",
        "sha512sum -c somme.txt",
        f"install -d -m 0755 {dest} && tar -xzf {fichier} -C {dest} --strip-components=1 --no-same-owner",
        _lien(f"{dest}/bin/mvn", "mvn"))


# Une ligne « <somme> <url> » du SDK linux-x64 lue dans releases.json de Microsoft (hash : sha512 hexadécimal).
_PY_DOTNET = ('import json,sys; v=sys.argv[1]; d=json.load(open("releases.json")); v=d["latest-sdk"] if v=="latest" else v; '
              'print(next("%s %s"%(f["hash"],f["url"]) for r in d["releases"] for s in [r.get("sdk") or {}]+(r.get("sdks") or []) '
              'if s.get("version")==v for f in s.get("files",[]) if f.get("rid")=="linux-x64" and f.get("name","").endswith(".tar.gz")))')
# Une ligne « <sha256> <fichier> » de l'archive Go linux-amd64 lue dans https://go.dev/dl/?mode=json&include=all.
_PY_GO = ('import json,sys; v="go"+sys.argv[1]; d=json.load(open("go.json")); '
          'print(next("%s %s"%(f["sha256"],f["filename"]) for r in d if r["version"]==v or r["version"].startswith(v+".") '
          'for f in r["files"] if f["os"]=="linux" and f["arch"]=="amd64" and f["kind"]=="archive"))')


def _bloc_dotnet(v: str) -> str:
    # Source : builds.dotnet.microsoft.com, releases.json du canal (sha512 publié par Microsoft pour chaque fichier).
    canal = ".".join(v.split(".")[:2])
    cible = v if v.count(".") == 2 else "latest"
    dest = f"{OPT}/dotnet-{v}"
    return "\n".join([_telechargement(
        " libicu74 libssl3t64",
        f'curl -fsSL -o releases.json "https://builds.dotnet.microsoft.com/dotnet/release-metadata/{canal}/releases.json"',
        f"ligne=\"$(python3 -I -c '{_PY_DOTNET}' {cible})\"",
        'somme="${ligne%% *}" && url="${ligne#* }"',
        "[[ $somme =~ ^[0-9a-f]{128}$ ]]",
        "[[ $url =~ ^https://(builds\\.dotnet\\.microsoft\\.com|dotnetcli\\.azureedge\\.net|download\\.visualstudio\\.microsoft\\.com)"
        "/[A-Za-z0-9./_-]+\\.tar\\.gz$ ]]",
        'curl -fsSL -o dotnet.tar.gz "$url"',
        "printf '%s  dotnet.tar.gz\\n' \"$somme\" > somme.txt",
        "sha512sum -c somme.txt",
        f"install -d -m 0755 {dest} && tar -xzf dotnet.tar.gz -C {dest} --no-same-owner",
        _lien(f"{dest}/dotnet", "dotnet"),
        "dotnet --version >/dev/null"),
        f"ENV DOTNET_ROOT={dest} DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1"])


def _bloc_go(v: str) -> str:
    # Source : go.dev/dl, liste JSON officielle (sha256 de chaque archive).
    dest = f"{OPT}/go-{v}"
    return "\n".join([_telechargement(
        "",
        'curl -fsSL -o go.json "https://go.dev/dl/?mode=json&include=all"',
        f"ligne=\"$(python3 -I -c '{_PY_GO}' {v})\"",
        'somme="${ligne%% *}" && fichier="${ligne#* }"',
        "[[ $somme =~ ^[0-9a-f]{64}$ ]]",
        "[[ $fichier =~ ^go[0-9.]+\\.linux-amd64\\.tar\\.gz$ ]]",
        'curl -fsSL -o "$fichier" "https://go.dev/dl/$fichier"',
        "printf '%s  %s\\n' \"$somme\" \"$fichier\" > somme.txt",
        "sha256sum -c somme.txt",
        f'install -d -m 0755 {dest} && tar -xzf "$fichier" -C {dest} --strip-components=1 --no-same-owner',
        _lien(f"{dest}/bin/go", "go"), _lien(f"{dest}/bin/gofmt", "gofmt"),
        "go version | grep ' linux/amd64' >/dev/null"),
        "ENV GOTOOLCHAIN=local"])


def _bloc_rust(v: str) -> str:
    # Source : static.rust-lang.org, rustup-init et son .sha256 voisin ; rustup vérifie lui-même les sommes de la chaîne d'outils.
    base = "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu"
    return "\n".join([_telechargement(
        "",
        f'curl -fsSL -o rustup-init "{base}/rustup-init"',
        f'curl -fsSL -o rustup-init.sha256 "{base}/rustup-init.sha256"',
        "somme=\"$(cut -d' ' -f1 rustup-init.sha256)\"",
        "printf '%s  rustup-init\\n' \"$somme\" > somme.txt",
        "sha256sum -c somme.txt",
        "chmod 0755 rustup-init",
        f"CARGO_HOME={OPT}/cargo RUSTUP_HOME={OPT}/rustup ./rustup-init -y --no-modify-path --profile minimal "
        f"--default-toolchain {v}",
        f"chmod -R a+rX {OPT}/cargo {OPT}/rustup",
        *[_lien(f"{OPT}/cargo/bin/{x}", x) for x in ("cargo", "rustc", "rustup", "rustdoc")],
        "RUSTUP_HOME=" + f"{OPT}/rustup cargo --version"),
        f"ENV RUSTUP_HOME={OPT}/rustup"])


def _bloc_godot(v: str) -> str:
    # Source : github.com/godotengine/godot-builds, SHA512-SUMS.txt de la même publication.
    v = v.removesuffix("-stable")
    base = f"https://github.com/godotengine/godot-builds/releases/download/{v}-stable"
    binaire = f"Godot_v{v}-stable_linux.x86_64"
    dest = f"{OPT}/godot-{v}"
    return _telechargement(
        " unzip libfontconfig1 libgl1 libx11-6 libxcursor1 libxi6 libxinerama1 libxrandr2",
        f'curl -fsSL -o SHA512-SUMS.txt "{base}/SHA512-SUMS.txt"',
        f"grep -E '^[0-9a-f]{{128}}  {_re_points(binaire)}\\.zip$' SHA512-SUMS.txt > somme.txt",
        'test "$(wc -l < somme.txt)" = 1',
        f'curl -fsSL -o {binaire}.zip "{base}/{binaire}.zip"',
        "sha512sum -c somme.txt",
        f"install -d -m 0755 {dest} && unzip -q {binaire}.zip -d {dest}",
        f"chmod 0755 {dest}/{binaire}",
        _lien(f"{dest}/{binaire}", "godot"))


OUTILS = {"jdk": _bloc_jdk, "node": _bloc_node, "python": _bloc_python, "maven": _bloc_maven, "dotnet": _bloc_dotnet,
          "go": _bloc_go, "rust": _bloc_rust, "godot": _bloc_godot, "unity": None}   # unity : socle (FROM), voir rendre_dockerfile


def _socle_unity() -> str:
    """Par-dessus l'image GameCI : git (dépendances UPM git), python3 et l'entrée, l'utilisateur 1000 (source : paquets Ubuntu)."""
    return "\n".join([
        _run("apt-get update",
             "apt-get install -y --no-install-recommends ca-certificates git python3 bash util-linux tar",
             "rm -rf /var/lib/apt/lists/*",
             "(getent passwd 1000 >/dev/null || useradd -u 1000 -M -s /usr/sbin/nologin tests)"),
        "COPY entree-tests.sh /usr/local/bin/entree-tests.sh",
        _run("chown root:root /usr/local/bin/entree-tests.sh", "chmod 0555 /usr/local/bin/entree-tests.sh",
             "install -d -o 1000 -m 0755 /work"),
        "ENV HOME=/tmp"])


def _version(outil: str, valeur) -> str:
    if isinstance(valeur, bool) or not isinstance(valeur, (str, int)):
        raise ValueError(f"version de {outil} illisible")
    texte = str(valeur)
    if MOTIFS_VERSION[outil].fullmatch(texte) is None:
        raise ValueError(f"version de {outil} refusée")
    return texte


def outils_a_installer(profil) -> list:
    """`[(outil, version)]` dans l'ordre fixe de `OUTILS`, versions validées, sans ce que la base porte déjà. ValueError pour
    un outil ou une version hors table."""
    voulus = {}
    for outil, valeur in profil.outils.items():
        if outil in _IGNORES:
            continue
        if outil not in OUTILS:
            raise ValueError("outil hors de la table")
        voulus[outil] = _version(outil, valeur)
    if "maven" in voulus and "jdk" not in voulus:
        raise ValueError("maven exige un JDK déclaré par le profil")
    resultat = []
    for outil in OUTILS:
        v = voulus.get(outil)
        if v is None:
            continue
        if outil in _BASE_OFFRE and _majeure(outil, v) == _majeure(outil, _BASE_OFFRE[outil]):
            continue
        resultat.append((outil, v))
    return resultat


def rendre_dockerfile(profil, base_digest: Optional[str] = None) -> Tuple[str, str]:
    """`(texte, sha256)` : le Dockerfile de l'image dérivée du profil. Mêmes octets à profil égal ; ValueError pour tout outil ou
    version hors table (rien n'est écrit alors). `base_digest` (`sha256:<64 hexa>`) épingle l'image de base par son digest."""
    a_installer = outils_a_installer(profil)
    if base_digest is not None and DIGEST.fullmatch(base_digest) is None:
        raise ValueError("digest de base refusé")
    unity = dict(a_installer).get("unity")
    if unity:
        base = f"unityci/editor@{base_digest}" if base_digest else f"unityci/editor:ubuntu-{unity}-android-{UNITY_GAMECI}"
    else:
        base = f"{IMAGE_DEFAUT}@{base_digest}" if base_digest else IMAGE_DEFAUT
    lignes = ["# Image derivee des campagnes de tests : rendue par outils/tests_images.py (gabarit ferme), jamais ecrite a la main.",
              f"# gabarit {GABARIT_VERSION}",
              f"FROM {base}",
              'SHELL ["/bin/bash", "-euo", "pipefail", "-c"]',
              "USER root",
              "ENV DEBIAN_FRONTEND=noninteractive"]
    if unity:
        lignes.append(_socle_unity())
    for outil, v in a_installer:
        if outil != "unity":
            lignes.append(OUTILS[outil](v))
    lignes += ["USER 1000:1000", "WORKDIR /work", 'ENTRYPOINT ["/usr/local/bin/entree-tests.sh"]']
    texte = "\n".join(lignes) + "\n"
    return texte, hashlib.sha256(texte.encode("utf-8")).hexdigest()


def etiquette_derivee(profil) -> str:
    """`myiafactory/tests-<12 hexa de empreinte_image>` : ne dépend que des outils (jamais du verrou ni du code)."""
    from tests_profil import empreinte_image
    return f"{IMAGE_DEFAUT}-{hashlib.sha256(f'{empreinte_image(profil)}:{GABARIT_VERSION}'.encode()).hexdigest()[:12]}"


def estimation(profil) -> Tuple[int, int]:
    """`(taille_estimee_mo, duree_estimee_s)` de la construction, d'après les outils à installer."""
    taille, duree = 50, 30
    for outil, _ in outils_a_installer(profil):
        t, d = _ESTIMATION[outil]
        taille, duree = taille + t, duree + d
    return taille, duree


def decision_image_derivee(profil, base_digest: Optional[str] = None) -> dict:
    """Charge de la décision de Direction `tests_image_derivee` (posée par la tâche 15b) ; réponses `construire`,
    `plus_tard`, `garder_poste`."""
    texte, sha = rendre_dockerfile(profil, base_digest)
    taille, duree = estimation(profil)
    return {"dockerfile": texte, "sha256": sha, "etiquette": etiquette_derivee(profil),
            "taille_estimee_mo": taille, "duree_estimee_s": duree}


# ---------------------------------------------------------------- registre local des images construites

def _horodatage(maintenant) -> str:
    if isinstance(maintenant, datetime):
        return maintenant.isoformat(timespec="seconds")
    if isinstance(maintenant, str) and re.fullmatch(r"[0-9TZ:+.-]{10,40}", maintenant):
        return maintenant
    raise ValueError("horodatage refusé")


def _lire_registre(registre) -> dict:
    try:
        x = json.loads(Path(registre).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return x if isinstance(x, dict) else {}


def _lire_pour_ecrire(registre) -> dict:
    """Comme `_lire_registre`, mais un fichier existant illisible est mis de cote (`<registre>.abime`) avant d'etre remplace :
    il n'est jamais reecrit a vide en silence."""
    chemin = Path(registre)
    if chemin.exists():
        try:
            x = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            x = None
        if not isinstance(x, dict):
            os.replace(chemin, str(chemin) + ".abime")
            return {}
        return x
    return {}


def _ecrire_registre(registre, donnees: dict) -> None:
    registre = Path(registre)
    registre.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(registre.parent), prefix=registre.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, sort_keys=True, indent=1, ensure_ascii=True)
        os.replace(tmp, registre)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _entrees(donnees: dict, serveur_id: str) -> dict:
    x = donnees.get(serveur_id)
    return x if isinstance(x, dict) else {}


def noter_image(serveur_id: str, etiquette: str, empreinte: str, taille_mo: int, maintenant, registre=None) -> None:
    """Note une image construite (ligne `#image` de l'enveloppe) : `{serveur_id: {etiquette: {empreinte, construite_le,
    utilisee_le, taille_mo}}}`."""
    if ETIQUETTE_DERIVEE.fullmatch(str(etiquette)) is None or EMPREINTE_64.fullmatch(str(empreinte)) is None:
        raise ValueError("étiquette ou empreinte refusée")
    if isinstance(taille_mo, bool) or not isinstance(taille_mo, int) or not 0 <= taille_mo <= 10_000_000:
        raise ValueError("taille refusée")
    quand = _horodatage(maintenant)
    registre = registre or REGISTRE
    donnees = _lire_pour_ecrire(registre)
    entrees = dict(_entrees(donnees, str(serveur_id)))
    entrees[etiquette] = {"empreinte": empreinte, "construite_le": quand, "utilisee_le": quand, "taille_mo": taille_mo}
    donnees[str(serveur_id)] = entrees
    _ecrire_registre(registre, donnees)


def image_connue(serveur_id: str, empreinte: str, registre=None) -> Optional[str]:
    """L'étiquette de l'image déjà construite pour cette empreinte d'image sur ce serveur, ou None."""
    for etiquette, e in sorted(_entrees(_lire_registre(registre or REGISTRE), str(serveur_id)).items()):
        if isinstance(e, dict) and e.get("empreinte") == empreinte:
            return etiquette
    return None


def noter_usage(serveur_id: str, etiquette: str, maintenant, registre=None) -> bool:
    """Date d'usage de l'image (une campagne l'a prise) ; faux si l'image n'est pas au registre."""
    quand = _horodatage(maintenant)
    registre = registre or REGISTRE
    donnees = _lire_pour_ecrire(registre)
    e = _entrees(donnees, str(serveur_id)).get(etiquette)
    if not isinstance(e, dict):
        return False
    e["utilisee_le"] = quand
    _ecrire_registre(registre, donnees)
    return True


def oublier_image(serveur_id: str, etiquette: str, registre=None) -> None:
    """Retire l'image du registre (ligne `#ramassee`)."""
    registre = registre or REGISTRE
    donnees = _lire_pour_ecrire(registre)
    if _entrees(donnees, str(serveur_id)).pop(etiquette, None) is not None:
        _ecrire_registre(registre, donnees)
