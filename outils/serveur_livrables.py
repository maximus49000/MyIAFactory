"""Les livrables d'un agent du serveur rapatriés au poste (apk, aab, zip…) : seuls les COMMITS reviennent par le paquet Git,
or un livrable construit est ignoré par git (`/android_app/build/`) ; il revient ici, en octets, par SSH.

Conception (sécurité d'abord : tout ce que le serveur renvoie est une donnée NON FIABLE) :
- la liste vient du RAPPORT de l'agent, lu par le moteur sur le poste (`fichiers` avec `livrable: true`) ; chaque chemin est
  revalidé ici (`valider_chemin`) : relatif au projet, sans `..` ni lecteur ni `/` initial, segments au motif strict (jamais
  un segment qui commence par « . », donc ni `.git` ni `.android`), extension dans la liste fermée des livrables
  téléchargeables du bureau (`releve.TELECHARGEABLES`), jamais une clé ni un certificat (`EXCLUS_EXTENSIONS`) ni rien sous
  `maison/` (`EXCLUS_SEGMENTS`) ; 8 fichiers au plus, 500 Mo chacun, 1 Go en tout ;
- le serveur ne reçoit que des chemins validés, insérés dans deux scripts FIGÉS (`_MANIFESTE`, `_ENVOI`) : le fichier doit
  être ordinaire (ni lien symbolique, ni lien dur, ni dossier lié sur le chemin : chemin physique == chemin demandé) sous
  `~/taches/<id>/travail/projet/` ; le manifeste rend sa taille et son SHA-256 (et refuse un fichier qui contient le jeton de
  l'abonnement, comme le contrôle de sortie de l'enveloppe) ;
- le poste reçoit les octets dans un fichier temporaire du MÊME dossier, vérifie taille et SHA-256 contre le manifeste, puis
  renomme (atomique). La destination doit rester dans le projet (aucun lien suivi), être ignorée par git (un livrable
  n'entre jamais dans l'historique) ; un fichier déjà là n'est remplacé que s'il est plus ancien que la tâche ET sous un
  dossier de build : sinon refusé, raison dite.
`rapatrier` ne lève jamais : chaque fichier a son résultat (rapatrié, ou refusé avec sa raison)."""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import plateforme_acces
import plateforme_ssh
import serveur_etat
import serveur_tache as st

MAX_FICHIERS = 8
MAX_OCTETS = 500 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_CHEMIN = 400
# Jamais rapatriés, quoi que dise le rapport : clés et certificats (la clé de debug ~/android-signature, maison/.android).
EXCLUS_EXTENSIONS = (".keystore", ".jks", ".pem", ".key", ".p12", ".pfx", ".der", ".crt", ".cer")
EXCLUS_SEGMENTS = ("maison", "android-signature", "agent-identifiants")
# Un fichier existant n'est remplacé que sous l'un de ces dossiers (et ignoré par git, et plus ancien que la tâche).
DOSSIERS_BUILD = frozenset({"build", "builds", "dist", "out", "outputs", "release", "releases", "target", "bin",
                            "flutter-apk", "bundle"})
_SEGMENT = r"[A-Za-z0-9_](?:[A-Za-z0-9_.+-]{0,98}[A-Za-z0-9_+-])?"
MOTIF_CHEMIN = re.compile(rf"{_SEGMENT}(?:/{_SEGMENT}){{0,23}}", re.ASCII)
MOTIF_SHA = re.compile(r"[0-9a-f]{64}", re.ASCII)
DELAI_MANIFESTE_S = 600
DELAI_ENVOI_S = 1800

# Le manifeste : une ligne par chemin demandé, « ok <taille> <sha256> <chemin> » ou « refus <motif> <chemin> ». Les chemins
# (@CHEMINS@) sont validés par MOTIF_CHEMIN sur le poste : ni espace, ni guillemet, ni caractère de motif du shell.
_MANIFESTE = """# tache:livrables_manifeste @ID@
set -u
r=$(cd -P -- "$HOME/taches/@ID@/travail/projet" 2>/dev/null && pwd -P) || { echo "racine"; exit 3; }
j="$HOME/agent-identifiants/jeton"
for c in @CHEMINS@; do
  f="$r/$c"
  p=$(cd -P -- "$(dirname -- "$f")" 2>/dev/null && pwd -P) || { echo "refus absent $c"; continue; }
  [ "$p/$(basename -- "$f")" = "$f" ] || { echo "refus lien $c"; continue; }
  [ -e "$f" ] || [ -L "$f" ] || { echo "refus absent $c"; continue; }
  [ -f "$f" ] && [ ! -L "$f" ] || { echo "refus lien $c"; continue; }
  [ -n "$(find "$f" -maxdepth 0 -type f -links 1 2>/dev/null)" ] || { echo "refus lien $c"; continue; }
  [ -n "$(find "$f" -maxdepth 0 -type f -size -@MAX@c 2>/dev/null)" ] || { echo "refus trop_gros $c"; continue; }
  if [ -f "$j" ] && [ ! -L "$j" ] && [ -s "$j" ]; then
    grep -F -q -f "$j" -- "$f" 2>/dev/null
    g=$?
    [ "$g" = 1 ] || { echo "refus secret $c"; continue; }
  fi
  t=$(stat -c %s -- "$f" 2>/dev/null) && s=$(sha256sum < "$f" 2>/dev/null) || { echo "refus illisible $c"; continue; }
  echo "ok $t ${s%% *} $c"
done
exit 0
"""
# L'envoi d'UN fichier : mêmes contrôles, puis ses octets (au plus @MAX@). 3 : absent ; 5 : lien ou trop gros.
_ENVOI = """# tache:livrables_envoi @ID@
set -u
r=$(cd -P -- "$HOME/taches/@ID@/travail/projet" 2>/dev/null && pwd -P) || exit 3
f="$r/@CHEMIN@"
p=$(cd -P -- "$(dirname -- "$f")" 2>/dev/null && pwd -P) || exit 3
[ "$p/$(basename -- "$f")" = "$f" ] || exit 5
[ -f "$f" ] && [ ! -L "$f" ] || exit 5
[ -n "$(find "$f" -maxdepth 0 -type f -links 1 -size -@MAX@c 2>/dev/null)" ] || exit 5
exec head -c @MAX@ -- "$f"
"""
MOTIFS_SERVEUR = {"absent": "absent du serveur (sous travail/projet de la tâche)",
                  "lien": "lien (symbolique ou dur) ou dossier lié : refusé",
                  "trop_gros": "trop gros (au-delà de la limite par fichier)",
                  "secret": "contient le secret de l'abonnement : jamais rapatrié",
                  "illisible": "illisible sur le serveur"}


def _extensions():
    """Les extensions des livrables téléchargeables du bureau (`releve.TELECHARGEABLES`), liste fermée."""
    racine = str(Path(__file__).resolve().parent.parent)
    if racine not in sys.path:
        sys.path.append(racine)
    from bureau import releve
    return frozenset(releve.TELECHARGEABLES)


def _extension(nom):
    return ("." + nom.rsplit(".", 1)[1].lower()) if "." in nom.strip(".") else ""


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
    if any(s.lower() in EXCLUS_SEGMENTS or s.startswith(".") for s in segments):
        return None, "dossier exclu (maison, clés, dossier caché) : jamais rapatrié"
    if _extension(segments[-1]) not in _extensions():
        return None, "extension hors de la liste des livrables téléchargeables"
    if len(c) > MAX_CHEMIN or not MOTIF_CHEMIN.fullmatch(c):
        return None, "caractères non admis dans le chemin"
    if any(s.split(".", 1)[0].lower() in st.NOMS_RESERVES for s in segments):
        return None, "nom réservé sous Windows"
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
    """La ligne du journal de la tâche pour un résultat de `rapatrier`."""
    if resultat.get("statut") == "rapatrie":
        return (f"Livrable rapatrié : {resultat['chemin']} ({taille_lisible(resultat['taille'])}, "
                f"{resultat['sha256'][:16]})")
    return f"Livrable non rapatrié : {str(resultat.get('chemin'))[:200]} : {resultat.get('raison')}"


# ---------------------------------------------------------------- poste

def _git_ignore(projet, chemin):
    """Vrai si git ignore `chemin` dans le dépôt `projet` (un fichier suivi n'est jamais « ignoré »)."""
    try:
        r = subprocess.run(["git", "-C", str(projet), "check-ignore", "-q", "--", chemin], capture_output=True,
                           timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _lien(p):
    try:
        return os.path.islink(p) or (hasattr(p, "is_junction") and p.is_junction())
    except OSError:
        return True


def _dossier_sur(racine, segments, creer):
    """Le dossier de destination sous `racine` (aucun lien suivi), créé si `creer` ; `(dossier, None)` ou `(None, raison)`."""
    courant = racine
    for s in segments:
        courant = courant / s
        if _lien(courant):
            return None, "lien dans le chemin du projet : refusé"
        if courant.exists():
            if not courant.is_dir():
                return None, f"« {s} » existe dans le projet et n'est pas un dossier"
        elif creer:
            try:
                courant.mkdir()
            except OSError as e:
                return None, f"dossier non créable ({type(e).__name__})"
    if creer:
        try:
            courant.resolve().relative_to(racine)
        except (OSError, ValueError):
            return None, "la destination sort du projet : refusé"
    return courant, None


def _destination(racine, chemin, debut, git_ignore):
    """None si `chemin` peut être écrit au poste, sinon la raison (rien n'est créé ici)."""
    segments = chemin.split("/")
    _d, raison = _dossier_sur(racine, segments[:-1], creer=False)
    if raison:
        return raison
    if not git_ignore(racine, chemin):
        return "non ignoré par git au poste : il entrerait dans l'historique (ajoutez-le au .gitignore)"
    cible = racine.joinpath(*segments)
    if os.path.lexists(cible):
        if _lien(cible) or not cible.is_file():
            return "un élément du même nom existe au poste et n'est pas un fichier ordinaire"
        if not any(s.lower() in DOSSIERS_BUILD for s in segments[:-1]):
            return "un fichier du même nom existe au poste hors d'un dossier de build : jamais écrasé"
        try:
            date = cible.stat().st_mtime
        except OSError:
            return "le fichier existant au poste est illisible"
        if debut is None or date >= debut:
            return "un fichier plus récent que la tâche existe déjà au poste : gardé"
    return None


def _sha256(fichier):
    h = hashlib.sha256()
    with open(fichier, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _recevoir(serveur, ssh, ident, chemin, taille, destination):
    """Reçoit les octets de `chemin` dans le fichier `destination` ; None ou la raison."""
    script = st._script(_ENVOI, ident, CHEMIN=chemin, MAX=str(taille + 1))
    vers = getattr(ssh, "executer_vers_fichier", None)
    if vers is not None:
        try:
            code, recu, erreur = vers(serveur_etat.cible(serveur), "bash -s", serveur.cle, str(destination), taille,
                                      entree=script.encode("utf-8"), delai=DELAI_ENVOI_S)
        except Exception as e:  # noqa: BLE001 - ssh absent, hôte invalide : panne de transfert
            code, recu, erreur = 255, 0, f"{type(e).__name__} : {e}"
    else:
        code, donnees, erreur = st._octets(serveur, ssh, "bash -s", script.encode("utf-8"), delai=DELAI_ENVOI_S)
        recu = len(donnees)
        if code == 0 and recu <= taille:
            Path(destination).write_bytes(donnees)
    if code in (5, 99):
        return "changé sur le serveur depuis le manifeste (lien ou trop gros)"
    if code == 3:
        return "disparu du serveur depuis le manifeste"
    if code != 0:
        return f"transfert en échec (code {code}) : {st._court(erreur, 150)}"
    if recu != taille:
        return f"taille reçue ({recu} o) différente du manifeste ({taille} o)"
    return None


def _ecrire(serveur, ssh, ident, racine, chemin, taille, sha, debut, git_ignore):
    """Rapatrie un fichier du manifeste : None ou la raison du refus."""
    raison = _destination(racine, chemin, debut, git_ignore)      # revu juste avant l'écriture
    if raison:
        return raison
    segments = chemin.split("/")
    dossier, raison = _dossier_sur(racine, segments[:-1], creer=True)
    if raison:
        return raison
    try:
        fd, temp = tempfile.mkstemp(prefix=".rapatrie-", suffix=".part", dir=str(dossier))
        os.close(fd)
    except OSError as e:
        return f"fichier temporaire impossible au poste ({type(e).__name__})"
    temp = Path(temp)
    try:
        raison = _recevoir(serveur, ssh, ident, chemin, taille, temp)
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
        return None
    except OSError as e:
        return f"écriture au poste impossible ({type(e).__name__} : {e})"
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def _manifeste(serveur, ssh, ident, chemins, max_octets):
    """`{chemin: ("ok", taille, sha) | ("refus", raison)}` ; une raison (texte) si le manifeste n'a pas pu être lu."""
    script = st._script(_MANIFESTE, ident, CHEMINS=" ".join(chemins), MAX=str(max_octets + 1))
    code, sortie, erreur = st._bash(serveur, ssh, script, delai=DELAI_MANIFESTE_S)
    if code == 3:
        return "dossier de travail de la tâche absent du serveur"
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
              git_ignore=_git_ignore, max_octets=MAX_OCTETS, max_total=MAX_TOTAL, max_fichiers=MAX_FICHIERS):
    """Rapatrie au poste, sous le dossier `projet`, les `chemins` déclarés livrables par l'agent de la tâche serveur `ident`.
    `debut` : l'instant (epoch) de création de la tâche (un fichier existant plus ancien peut être remplacé).
    Rend `[{"chemin", "statut": "rapatrie" | "refuse", "taille"?, "sha256"?, "raison"?}]` ; ne lève jamais."""
    resultats, valides = [], []
    for brut in chemins or []:
        chemin, raison = valider_chemin(brut)
        if raison:
            resultats.append({"chemin": str(brut)[:200], "statut": "refuse", "raison": raison})
        elif chemin in valides:
            continue
        elif len(valides) >= max_fichiers:
            resultats.append({"chemin": chemin, "statut": "refuse",
                              "raison": f"au plus {max_fichiers} livrables rapatriés par tâche"})
        else:
            valides.append(chemin)
    if not valides:
        return resultats
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
        raison = _destination(racine, c, debut, git_ignore)
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
            raison = _ecrire(serveur, ssh, ident, racine, c, taille, sha, debut, git_ignore)
        except Exception as e:  # noqa: BLE001
            raison = f"{type(e).__name__} : {st._court(e, 150)}"
        if raison:
            resultats.append({"chemin": c, "statut": "refuse", "raison": raison})
        else:
            resultats.append({"chemin": c, "statut": "rapatrie", "taille": taille, "sha256": sha})
    return resultats
