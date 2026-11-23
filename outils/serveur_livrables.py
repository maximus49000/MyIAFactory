"""Les livrables d'un agent du serveur rapatriés au poste (apk, aab, zip) : seuls les COMMITS reviennent par le paquet Git,
or un livrable construit est ignoré par git (`/android_app/build/`) ; il revient ici, en octets, par SSH.

Conception (sécurité d'abord : tout ce que le serveur renvoie est une donnée NON FIABLE) :
- la liste vient du RAPPORT de l'agent, lu par le moteur sur le poste (`fichiers` avec `livrable: true`) ; chaque chemin est
  revalidé ici (`valider_chemin`) : relatif au projet, sans `..` ni lecteur ni `/` initial, segments au motif strict (jamais
  un segment qui commence par « . »), extension dans une liste FERMÉE et minimale (`EXTENSIONS` : apk, aab, zip ; aucun
  exécutable du poste), jamais une clé ni un certificat (`EXCLUS_EXTENSIONS`), rien sous `maison/` ni sous un dossier de
  dépendances (`EXCLUS_SEGMENTS`), et le chemin doit être celui d'une sortie de build Android (`MOTIF_SORTIE`, exigé pour un
  fichier neuf comme pour un fichier existant) ; 8 fichiers au plus, 500 Mo chacun, 1 Go en tout ;
- le serveur ne reçoit que des chemins validés, insérés dans deux scripts FIGÉS (`_MANIFESTE`, `_ENVOI`) : la racine
  `~/taches/<id>/travail/projet` doit être physique (aucun lien, `pwd -P` égal), aucun composant du chemin n'est un lien ; le
  fichier est ouvert UNE fois (descripteur 3), vérifié sur ce descripteur (fichier ordinaire, un seul lien, même inode que le
  chemin), puis haché (manifeste) ou envoyé (envoi) depuis ce descripteur ; un fichier qui contient le jeton de l'abonnement
  est refusé, comme au contrôle de sortie de l'enveloppe ;
- le poste reçoit les octets dans un fichier temporaire du MÊME dossier, vérifie taille et SHA-256 contre le manifeste, puis
  renomme (atomique). La destination reste dans le projet (aucun lien suivi), n'est jamais un fichier suivi par git, et son
  chemin est écrit dans `.git/info/exclude` (local, jamais commité) avant le renommage : le commit « Factory : … » (`git add
  -A`) ne l'ajoute jamais. Un fichier déjà là n'est remplacé que s'il est plus ancien que la tâche. Les dossiers créés pour
  un fichier refusé sont retirés ; l'espace libre (taille + 1 Go) est vérifié avant d'écrire. Un arrêt demandé est lu avant
  chaque fichier et pendant le transfert (ssh coupé).
`rapatrier` ne lève jamais : chaque fichier a son résultat (rapatrié, ou refusé avec sa raison)."""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import plateforme_acces
import plateforme_ssh
import serveur_etat
import serveur_tache as st

MAX_FICHIERS = 8
MAX_OCTETS = 500 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_CHEMIN = 400
MARGE_DISQUE = 1024 * 1024 * 1024        # espace libre exigé au poste : taille du fichier + 1 Go
# La liste fermée des livrables rapatriés : ce qu'un APK, un AAB ou une archive exige, rien d'autre (aucun exécutable).
EXTENSIONS = frozenset({".apk", ".aab", ".zip"})
# Jamais rapatriés, quoi que dise le rapport : clés et certificats (la clé de debug ~/android-signature, maison/.android).
EXCLUS_EXTENSIONS = (".keystore", ".jks", ".pem", ".key", ".p12", ".pfx", ".der", ".crt", ".cer")
EXCLUS_SEGMENTS = frozenset({"maison", "android-signature", "agent-identifiants", "node_modules", "venv", ".venv",
                             "vendor", ".git", ".factory", "site-packages"})
# Les sorties de build Android (Flutter et Gradle) : le seul endroit où un livrable rapatrié s'écrit.
MOTIF_SORTIE = re.compile(r"(?:^|/)build/(?:app/)?outputs/(?:flutter-apk|apk|bundle)/[^/]+\Z", re.ASCII)
_SEGMENT = r"[A-Za-z0-9_](?:[A-Za-z0-9_.+-]{0,98}[A-Za-z0-9_+-])?"
MOTIF_CHEMIN = re.compile(rf"{_SEGMENT}(?:/{_SEGMENT}){{0,23}}", re.ASCII)
MOTIF_SHA = re.compile(r"[0-9a-f]{64}", re.ASCII)
DELAI_MANIFESTE_S = 180
DELAI_ENVOI_MAX_S = 1800
ARRET = "arrêt demandé"

# Commun aux deux scripts : la racine physique de la tâche, puis `ouvrir <chemin>` : 0 (descripteur 3 ouvert, T = taille),
# 3 absent, 5 lien (symbolique, dur, composant lié, inode différent), 6 trop gros (au-delà de @MAX@ octets).
_OUVRIR = """set -u
set -f
h=$(cd -P -- "$HOME" 2>/dev/null && pwd -P) || exit 3
b="$h/taches/@ID@"
[ -d "$b" ] && [ ! -L "$b" ] && [ ! -L "$b/travail" ] && [ ! -L "$b/travail/projet" ] || { echo "racine"; exit 3; }
r=$(cd -P -- "$b/travail/projet" 2>/dev/null && pwd -P) && [ "$r" = "$b/travail/projet" ] || { echo "racine"; exit 3; }
ouvrir() {
  f="$r"
  local s v n i
  local IFS=/
  for s in $1; do
    f="$f/$s"
    [ -L "$f" ] && return 5
  done
  IFS=' '
  [ -e "$f" ] || return 3
  [ -f "$f" ] || return 5
  exec 3<"$f" || return 3
  [ -f /proc/self/fd/3 ] || { exec 3<&-; return 5; }
  v=$(stat -L -c '%h %i %s' /proc/self/fd/3 2>/dev/null) || { exec 3<&-; return 5; }
  n=${v%% *}; v=${v#* }; i=${v%% *}; T=${v#* }
  [ "$n" = 1 ] && [ ! -L "$f" ] && [ "$(stat -c %i -- "$f" 2>/dev/null)" = "$i" ] || { exec 3<&-; return 5; }
  [ "$T" -le @MAX@ ] || { exec 3<&-; return 6; }
  return 0
}
"""
# Le manifeste : une ligne par chemin demandé, « ok <taille> <sha256> <chemin> » ou « refus <motif> <chemin> ». Les chemins
# (@CHEMINS@) sont validés par MOTIF_CHEMIN sur le poste : ni espace, ni guillemet, ni caractère de motif du shell. Le jeton
# est cherché par /proc/self/fd/3 (le même fichier ouvert, sans relire le chemin), le hachage lit le descripteur 3.
_MANIFESTE = "# tache:livrables_manifeste @ID@\n" + _OUVRIR + """j="$h/agent-identifiants/jeton"
for c in @CHEMINS@; do
  ouvrir "$c"
  e=$?
  case "$e" in
    0) ;;
    3) echo "refus absent $c"; continue ;;
    6) echo "refus trop_gros $c"; continue ;;
    *) echo "refus lien $c"; continue ;;
  esac
  if [ -f "$j" ] && [ ! -L "$j" ] && [ -s "$j" ]; then
    grep -F -q -f "$j" /proc/self/fd/3 2>/dev/null
    g=$?
    [ "$g" = 1 ] || { exec 3<&-; echo "refus secret $c"; continue; }
  fi
  s=$(sha256sum <&3 2>/dev/null) || { exec 3<&-; echo "refus illisible $c"; continue; }
  exec 3<&-
  echo "ok $T ${s%% *} $c"
done
exit 0
"""
# L'envoi d'UN fichier, au plus @MAX@ octets (la taille du manifeste), depuis le descripteur vérifié.
_ENVOI = "# tache:livrables_envoi @ID@\n" + _OUVRIR + """ouvrir "@CHEMIN@"
e=$?
[ "$e" = 0 ] || exit "$e"
exec head -c @MAX@ <&3
"""
MOTIFS_SERVEUR = {"absent": "absent du serveur (sous travail/projet de la tâche)",
                  "lien": "lien (symbolique ou dur) ou dossier lié : refusé",
                  "trop_gros": "trop gros (au-delà de la limite par fichier)",
                  "secret": "contient le secret de l'abonnement : jamais rapatrié",
                  "illisible": "illisible sur le serveur"}


def _extension(nom):
    return ("." + nom.rsplit(".", 1)[1].lower()) if "." in nom.strip(".") else ""


def propre(texte, n=300):
    """Le texte sans caractère de contrôle (retours à la ligne compris) : sûr pour une ligne de journal."""
    return "".join("?" if (ord(c) < 32 or 127 <= ord(c) < 160 or c in "  ") else c for c in str(texte))[:n]


def valider_chemin(brut):
    """`(chemin, None)` si le chemin déclaré peut être rapatrié, sinon `(None, raison)`."""
    if not isinstance(brut, str) or not brut.strip() or "\x00" in brut:
        return None, "chemin vide ou illisible"
    c = brut.strip().replace("\\", "/")
    if c.startswith("./"):
        c = c[2:]
    if c.startswith("/") or ":" in c or c.startswith("~"):
        return None, "chemin absolu ou avec lecteur : refusé"
    segments = c.split("/")
    if ".." in segments:
        return None, "chemin avec « .. » : refusé"
    if _extension(segments[-1]) in EXCLUS_EXTENSIONS:
        return None, "clé ou certificat : jamais rapatrié"
    if _extension(segments[-1]) not in EXTENSIONS:
        return None, "extension hors de la liste des livrables rapatriés (apk, aab, zip)"
    if any(s.lower() in EXCLUS_SEGMENTS or s.startswith(".") for s in segments):
        return None, "dossier exclu (maison, clés, dépendances, dossier caché) : jamais rapatrié"
    if len(c) > MAX_CHEMIN or not MOTIF_CHEMIN.fullmatch(c):
        return None, "caractères non admis dans le chemin"
    if any(s.split(".", 1)[0].lower() in st.NOMS_RESERVES for s in segments):
        return None, "nom réservé sous Windows"
    if not MOTIF_SORTIE.search(c):
        return None, "hors d'un dossier de sortie Android (build/[app/]outputs/flutter-apk|apk|bundle/<fichier>)"
    return c, None


def declares(rapport):
    """Les chemins que le rapport de l'agent déclare livrables (`fichiers` avec `livrable: true`), dans l'ordre, sans
    doublon (textes bruts : `valider_chemin` les juge)."""
    vus = []
    fichiers = rapport.get("fichiers") if isinstance(rapport, dict) else None
    for f in fichiers if isinstance(fichiers, list) else []:
        if isinstance(f, dict) and f.get("livrable") is True and isinstance(f.get("chemin"), str):
            if f["chemin"] not in vus:
                vus.append(f["chemin"])
    return vus


def taille_lisible(n):
    for unite, puissance in (("Go", 3), ("Mo", 2), ("Ko", 1)):
        if n >= 1024 ** puissance:
            return f"{n / 1024 ** puissance:.1f} {unite}".replace(".", ",")
    return f"{n} o"


def ligne(resultat):
    """La ligne du journal de la tâche pour un résultat de `rapatrier` (aucun caractère de contrôle)."""
    if resultat.get("statut") == "rapatrie":
        return propre(f"Livrable rapatrié : {resultat['chemin']} ({taille_lisible(resultat['taille'])}, "
                      f"{resultat['sha256'][:16]})", 500)
    return propre(f"Livrable non rapatrié : {propre(resultat.get('chemin'), 200)} : {resultat.get('raison')}", 500)


def _delai_envoi(taille):
    """Délai d'un envoi : 1 Mo/s plus 60 s, 30 min au plus."""
    return min(DELAI_ENVOI_MAX_S, int(taille) // (1024 * 1024) + 60)


# ---------------------------------------------------------------- poste

def _git(projet, *args):
    try:
        return subprocess.run(["git", "-C", str(projet), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None


def _suivi(projet, chemin):
    """Vrai si `chemin` est suivi par git (ou si git ne répond pas : prudence)."""
    r = _git(projet, "ls-files", "--error-unmatch", "--", chemin)
    return r is None or r.returncode == 0


def _exclure(projet, chemin):
    """Écrit `/chemin` dans `.git/info/exclude` du dépôt (local, jamais commité ; une fois) puis vérifie que git l'ignore.
    None, ou la raison."""
    r = _git(projet, "rev-parse", "--git-path", "info/exclude")
    if r is None or r.returncode != 0:
        return "dépôt git du projet introuvable au poste"
    fichier = Path(r.stdout.decode("utf-8", "replace").strip())
    if not fichier.is_absolute():
        fichier = Path(projet) / fichier
    ligne_ = f"/{chemin}"
    try:
        if _lien(fichier):
            return "exclusion git impossible (info/exclude est un lien)"
        fichier.parent.mkdir(parents=True, exist_ok=True)
        existant = fichier.read_text(encoding="utf-8", errors="replace") if fichier.exists() else ""
        if ligne_ not in existant.splitlines():
            with open(fichier, "a", encoding="utf-8", newline="\n") as f:
                f.write(("" if not existant or existant.endswith("\n") else "\n") + ligne_ + "\n")
    except OSError as e:
        return f"exclusion git impossible ({type(e).__name__})"
    r = _git(projet, "check-ignore", "-q", "--", chemin)
    if r is None or r.returncode != 0:
        return "git n'ignore pas le livrable malgré l'exclusion locale : refusé"
    return None


def _lien(p):
    try:
        p = Path(p)
        return os.path.islink(p) or (hasattr(p, "is_junction") and p.is_junction())
    except OSError:
        return True


def _dossier_sur(racine, segments, crees=None):
    """Le dossier de destination sous `racine` (aucun lien suivi) ; créé si `crees` (liste qui reçoit les dossiers créés).
    `(dossier, None)` ou `(None, raison)`."""
    courant = racine
    for s in segments:
        courant = courant / s
        if _lien(courant):
            return None, "lien dans le chemin du projet : refusé"
        if courant.exists():
            if not courant.is_dir():
                return None, f"« {s} » existe dans le projet et n'est pas un dossier"
        elif crees is not None:
            try:
                courant.mkdir()
                crees.append(courant)
            except OSError as e:
                return None, f"dossier non créable ({type(e).__name__})"
    if crees is not None:
        try:
            courant.resolve().relative_to(racine)
        except (OSError, ValueError):
            return None, "la destination sort du projet : refusé"
    return courant, None


def _destination(racine, chemin, debut):
    """None si `chemin` peut être écrit au poste, sinon la raison (rien n'est créé ici)."""
    segments = chemin.split("/")
    _d, raison = _dossier_sur(racine, segments[:-1])
    if raison:
        return raison
    cible = racine.joinpath(*segments)
    if os.path.lexists(cible):
        if _lien(cible) or not cible.is_file():
            return "un élément du même nom existe au poste et n'est pas un fichier ordinaire"
        if _suivi(racine, chemin):
            return "un fichier du même nom est suivi par git au poste : jamais remplacé"
        try:
            date = cible.stat().st_mtime
        except OSError:
            return "le fichier existant au poste est illisible"
        if debut is None or date >= debut:
            return "un fichier plus récent que la tâche existe déjà au poste : gardé"
    elif _suivi(racine, chemin):
        return "chemin suivi par git au poste : jamais écrit"
    return None


def _sha256(fichier):
    h = hashlib.sha256()
    with open(fichier, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _recevoir(serveur, ssh, ident, chemin, taille, destination, arret):
    """Reçoit les octets de `chemin` dans le fichier `destination` ; None ou la raison. Un arrêt demandé pendant le
    transfert coupe ssh (le processus lancé ici, rien d'autre)."""
    script = st._script(_ENVOI, ident, CHEMIN=chemin, MAX=str(taille))
    delai = _delai_envoi(taille)
    vers = getattr(ssh, "executer_vers_fichier", None)
    if vers is not None:
        processus, fini = [], threading.Event()

        def popen(*a, **kw):
            p = subprocess.Popen(*a, **kw)
            processus.append(p)
            return p

        def guetter():
            while not fini.wait(0.2):
                if arret():
                    for p in processus:
                        try:
                            p.kill()
                        except OSError:
                            pass
                    return
        guetteur = threading.Thread(target=guetter, daemon=True)
        guetteur.start()
        try:
            code, recu, erreur = vers(serveur_etat.cible(serveur), "bash -s", serveur.cle, str(destination), taille,
                                      entree=script.encode("utf-8"), delai=delai, popen=popen)
        except Exception as e:  # noqa: BLE001 - ssh absent, hôte invalide : panne de transfert
            code, recu, erreur = 255, 0, f"{type(e).__name__} : {e}"
        finally:
            fini.set()
            guetteur.join(5)
    else:
        code, donnees, erreur = st._octets(serveur, ssh, "bash -s", script.encode("utf-8"), delai=delai)
        recu = len(donnees)
        if code == 0 and recu <= taille:
            Path(destination).write_bytes(donnees)
    if arret():
        return f"{ARRET} : transfert coupé"
    if code in (5, 6, 99):
        return "changé sur le serveur depuis le manifeste (lien ou taille)"
    if code == 3:
        return "disparu du serveur depuis le manifeste"
    if code != 0:
        return f"transfert en échec (code {code}) : {st._court(erreur, 150)}"
    if recu != taille:
        return f"taille reçue ({recu} o) différente du manifeste ({taille} o)"
    return None


def _retirer(crees):
    for d in reversed(crees):
        try:
            d.rmdir()                     # seulement vide : jamais ce que quelqu'un d'autre y a mis
        except OSError:
            pass


def _ecrire(serveur, ssh, ident, racine, chemin, taille, sha, debut, arret):
    """Rapatrie un fichier du manifeste : None ou la raison du refus."""
    raison = _destination(racine, chemin, debut)      # revu juste avant l'écriture
    if raison:
        return raison
    segments = chemin.split("/")
    try:
        libre = shutil.disk_usage(str(racine))[2]
    except OSError:
        libre = None
    if libre is None or libre < taille + MARGE_DISQUE:
        return f"espace disque libre insuffisant au poste (il faut {taille_lisible(taille + MARGE_DISQUE)})"
    crees, temp, fait = [], None, False
    try:
        dossier, raison = _dossier_sur(racine, segments[:-1], crees)
        if raison:
            return raison
        raison = _exclure(racine, chemin)
        if raison:
            return raison
        fd, temp = tempfile.mkstemp(prefix=".rapatrie-", suffix=".part", dir=str(dossier))
        os.close(fd)
        temp = Path(temp)
        raison = _recevoir(serveur, ssh, ident, chemin, taille, temp, arret)
        if raison:
            return raison
        if temp.stat().st_size != taille:
            return "taille écrite différente du manifeste"
        if _sha256(temp) != sha:
            return "SHA-256 reçu différent de celui du manifeste : fichier jeté"
        cible = dossier / segments[-1]
        if _lien(cible):
            return "un lien a pris la place de la destination : refusé"
        os.replace(temp, cible)
        fait = True
        return None
    except OSError as e:
        return f"écriture au poste impossible ({type(e).__name__} : {e})"
    finally:
        try:
            if temp is not None and temp.exists():
                temp.unlink()
        except OSError:
            pass
        if not fait:
            _retirer(crees)


def _manifeste(serveur, ssh, ident, chemins, max_octets):
    """`{chemin: ("ok", taille, sha) | ("refus", raison)}` ; une raison (texte) si le manifeste n'a pas pu être lu."""
    script = st._script(_MANIFESTE, ident, CHEMINS=" ".join(chemins), MAX=str(max_octets))
    code, sortie, erreur = st._bash(serveur, ssh, script, delai=DELAI_MANIFESTE_S)
    if code == 3:
        return "dossier de travail de la tâche absent ou lié sur le serveur"
    if code != 0:
        return f"manifeste impossible (code {code}) : {st._court(erreur, 150)}"
    lu = {}
    for brut in sortie.splitlines()[:4 * MAX_FICHIERS]:
        mots = brut.strip().split(" ")
        if len(mots) == 4 and mots[0] == "ok" and mots[3] in chemins and mots[3] not in lu:
            if mots[1].isdigit() and int(mots[1]) <= max_octets and MOTIF_SHA.fullmatch(mots[2]):
                lu[mots[3]] = ("ok", int(mots[1]), mots[2])
            else:
                lu[mots[3]] = ("refus", "ligne du manifeste invalide")
        elif len(mots) == 3 and mots[0] == "refus" and mots[2] in chemins and mots[2] not in lu:
            lu[mots[2]] = ("refus", MOTIFS_SERVEUR.get(mots[1], "refusé par le serveur"))
    return lu


def rapatrier(ident, projet, chemins, debut=None, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh,
              max_octets=MAX_OCTETS, max_total=MAX_TOTAL, max_fichiers=MAX_FICHIERS, arret=None):
    """Rapatrie au poste, sous le dossier `projet`, les `chemins` déclarés livrables par l'agent de la tâche serveur `ident`.
    `debut` : l'instant (epoch) de création de la tâche (un fichier existant plus ancien peut être remplacé) ; `arret` :
    fonction sans argument, vraie quand l'arrêt est demandé (lue avant chaque fichier et pendant les transferts).
    Rend `[{"chemin", "statut": "rapatrie" | "refuse", "taille"?, "sha256"?, "raison"?}]` ; ne lève jamais."""
    arret = arret if callable(arret) else (lambda: False)
    resultats, valides = [], []
    for brut in chemins or []:
        chemin, raison = valider_chemin(brut)
        if raison:
            resultats.append({"chemin": propre(brut, 200), "statut": "refuse", "raison": raison})
        elif chemin in valides:
            continue
        elif len(valides) >= max_fichiers:
            resultats.append({"chemin": chemin, "statut": "refuse",
                              "raison": f"au plus {max_fichiers} livrables rapatriés par tâche"})
        else:
            valides.append(chemin)
    if not valides:
        return resultats
    if arret():
        return resultats + [{"chemin": c, "statut": "refuse", "raison": f"{ARRET} : non rapatrié"} for c in valides]
    try:
        st._id_valide(ident)
        racine = Path(projet).resolve()
        if not racine.is_dir():
            raise ValueError("dossier du projet introuvable")
        serveur = st._serveur_de(ident, dossier)
    except Exception as e:  # noqa: BLE001 - jamais une raison de faire échouer la tâche
        return resultats + [{"chemin": c, "statut": "refuse", "raison": f"rapatriement impossible : {st._court(e, 150)}"}
                            for c in valides]
    a_demander = []
    for c in valides:
        raison = _destination(racine, c, debut)
        if raison:
            resultats.append({"chemin": c, "statut": "refuse", "raison": raison})
        else:
            a_demander.append(c)
    if not a_demander:
        return resultats
    lu = _manifeste(serveur, ssh, ident, a_demander, max_octets)
    if isinstance(lu, str):
        return resultats + [{"chemin": c, "statut": "refuse", "raison": lu} for c in a_demander]
    total = 0
    for c in a_demander:
        entree = lu.get(c) or ("refus", "absent du manifeste du serveur")
        if arret():
            resultats.append({"chemin": c, "statut": "refuse", "raison": f"{ARRET} : non rapatrié"})
            continue
        if entree[0] != "ok":
            resultats.append({"chemin": c, "statut": "refuse", "raison": entree[1]})
            continue
        _ok, taille, sha = entree
        if total + taille > max_total:
            resultats.append({"chemin": c, "statut": "refuse",
                              "raison": f"total des livrables au-delà de {taille_lisible(max_total)}"})
            continue
        total += taille
        try:
            raison = _ecrire(serveur, ssh, ident, racine, c, taille, sha, debut, arret)
        except Exception as e:  # noqa: BLE001
            raison = f"{type(e).__name__} : {st._court(e, 150)}"
        if raison:
            resultats.append({"chemin": c, "statut": "refuse", "raison": raison})
        else:
            resultats.append({"chemin": c, "statut": "rapatrie", "taille": taille, "sha256": sha})
    return resultats
