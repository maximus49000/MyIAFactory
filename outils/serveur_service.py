"""Service permanent d'un projet sur le serveur, côté poste (docs/serveur-services.md).

Dépose le script hôte (`serveur_ovh/services/service.py`) sur le serveur, lui envoie les sources du commit (git archive),
les variables (réglage du projet) et les secrets (saisis par le Directeur seul), puis le déploie ou le gère. Tout passe par
SSH avec des valeurs VALIDÉES (identifiant du projet, commit) : rien de libre dans les lignes de commande, les valeurs
sensibles voyagent par l'entrée standard.

Le jeton du service est rangé au coffre du poste (`~/MyIAFactory/services/<projet>.jeton`, 0600 / ACL de l'utilisateur) ;
le cache `~/MyIAFactory/services.json` (état, adresse, dernier journal) ne contient jamais ni jeton ni secret : le bureau
l'affiche.

Commande : `py -3.12 lancer.py service <commande> [--dossier <projet>] [--commit <sha>] [--lignes N]`.
- `etat`, `journal` : ouverts aux agents (aussi par `python lancer.py deporter service etat|journal`).
- `deployer`, `mettre-a-jour`, `redemarrer`, `arreter`, `supprimer`, `jeton`, `secrets <NOM>...` : le Directeur seul
  (refusés quand `MYIAFACTORY_AGENT` est posé, la marque des agents lancés par le moteur) ; `secrets` saisit chaque valeur
  sans écho, au terminal seulement (jamais par l'entrée standard ni en argument).
Accord : le projet est enregistré au bureau et l'action `service` y est réglée sur « serveur » (comme la recette).
Codes : 0 réussi ; 1 échec (serveur injoignable, déploiement refusé et retour arrière) ; 2 usage, accord ou déclaration
refusés ; 75 un déploiement du projet est déjà en cours.
"""
import getpass
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import plateforme_acces  # noqa: E402
import plateforme_ssh  # noqa: E402
import serveur_tache  # noqa: E402
from plateforme import DOSSIER_DISTANT, RACINE_SERVEUR  # noqa: E402
from serveur_modele import ecrire_atomique  # noqa: E402

from bureau import deport_types  # noqa: E402

ACTION = "service"
SCRIPT_LOCAL = RACINE_SERVEUR / "services" / "service.py"
SCRIPT_DISTANT = f"{DOSSIER_DISTANT}/services/service.py"
CAPACITES = ("base",)
COMMANDES_AGENT = ("etat", "journal")
GESTION = ("etat", "journal", "redemarrer", "arreter", "supprimer")
COMMANDES = ("deployer", "mettre-a-jour", "secrets", "jeton") + GESTION
VARIABLE_AGENT = "MYIAFACTORY_AGENT"
CACHE = "services.json"
COFFRE = "services"
SOURCES_MAX = 500 * 1024 * 1024
DELAIS = {"recevoir": 600, "deployer": 2400, "etat": 60, "journal": 60, "redemarrer": 180, "arreter": 120,
          "supprimer": 180, "jeton": 60, "poser-secrets": 60, "poser-variables": 60}
INJOIGNABLE = (124, 255)
_VERROU_CACHE = threading.Lock()
MSG_DIRECTEUR = ("« %s » est réservé au Directeur (bureau, zone Services, ou « py -3.12 lancer.py service %s » à la main) : "
                 "un agent ne déploie ni ne gère jamais le service ; il ne lit que « etat » et « journal ».")

# Le dépôt du script hôte : archive extraite dans un temporaire privé, déplacée seulement si le fichier est là (ni lien,
# ni vide) ; le temporaire est toujours supprimé (même discipline que l'enveloppe des tâches).
_DEPOSER = f"""# service:deposer
umask 077
mkdir -p "$HOME/myiafactory" || exit 1
d=$(mktemp -d "$HOME/myiafactory/.depot.XXXXXX") || exit 1
f="$d/services/service.py"
r=1
if tar -x --no-same-owner -C "$d" -f - && [ -f "$f" ] && [ ! -L "$f" ] && [ -s "$f" ]; then
  mkdir -p "{DOSSIER_DISTANT}/services" && mv -f "$f" "{SCRIPT_DISTANT}" && r=0
fi
rm -rf "$d"
exit $r
"""


def _charger_hote():
    spec = importlib.util.spec_from_file_location("service_hote_poste", SCRIPT_LOCAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOTE = _charger_hote()        # une seule source des motifs et de la validation : le script hôte lui-même


def _maintenant_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def identifiant(racine):
    """L'identifiant du projet au serveur, tiré du nom de son dossier : minuscules, chiffres, tirets (motif du script
    hôte), préfixé de « p- » s'il ne commence pas par une lettre."""
    brut = unicodedata.normalize("NFKD", Path(racine).name).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", brut).strip("-")
    if not s or not s[0].isalpha():
        s = ("p-" + s).rstrip("-")
    s = s[:40].rstrip("-")
    return s if HOTE.MOTIF_PROJET.fullmatch(s) else "projet"


def lire_declaration(racine):
    """La déclaration validée du projet (`.factory/service.json`) ; `ValueError` sinon (absente, lien, hostile)."""
    f = Path(racine) / ".factory" / "service.json"
    if (Path(racine) / ".factory").is_symlink() or f.is_symlink():
        raise ValueError(".factory/service.json : lien refusé.")
    brut = HOTE.lire_fichier_sur(f, HOTE.DECLARATION_MAX)
    if brut is None:
        raise ValueError("Le projet n'a pas de .factory/service.json : rien à déployer.")
    return HOTE.valider_declaration(brut)


def a_un_service(racine):
    try:
        f = Path(racine) / ".factory" / "service.json"
        return f.is_file() and not f.is_symlink()
    except OSError:
        return False


# --- Coffre et cache du poste ---------------------------------------------------------------------------------------------

def _coffre(dossier, projet):
    return Path(dossier) / COFFRE / f"{projet}.jeton"


def lire_jeton(projet, dossier=plateforme_acces.DOSSIER):
    """Le jeton du service rangé au coffre du poste ; "" s'il n'y est pas. Pour le Directeur (bureau) seulement."""
    try:
        j = _coffre(dossier, projet).read_text("utf-8").strip()
    except (OSError, UnicodeError):
        return ""
    return j if re.fullmatch(r"[A-Za-z0-9_-]{40,128}", j) else ""


def _ranger_jeton(projet, jeton, dossier):
    chemin = _coffre(dossier, projet)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    ecrire_atomique(chemin, jeton + "\n")


def _oublier_jeton(projet, dossier):
    try:
        _coffre(dossier, projet).unlink()
    except OSError:
        pass


AUTO = "services-auto.json"      # {identifiant du projet: true} : la case « Déployer automatiquement » de la zone Services


def lire_auto(dossier=plateforme_acces.DOSSIER):
    """{projet: bool} : les projets dont le Directeur a coché le déploiement automatique à chaque modification."""
    try:
        brut = (Path(dossier) / AUTO).read_bytes()
        d = json.loads(brut.decode("utf-8")) if len(brut) < 64 * 1024 else {}
    except (OSError, ValueError, UnicodeError):
        return {}
    return {k: True for k, v in d.items() if isinstance(k, str) and v is True} if isinstance(d, dict) else {}


def poser_auto(projet, actif, dossier=plateforme_acces.DOSSIER):
    """Coche ou décoche le déploiement automatique du projet (écrit au poste, jamais au serveur)."""
    with _VERROU_CACHE:
        auto = lire_auto(dossier)
        if actif:
            auto[projet] = True
        else:
            auto.pop(projet, None)
        Path(dossier).mkdir(parents=True, exist_ok=True)
        ecrire_atomique(Path(dossier) / AUTO, json.dumps(auto, ensure_ascii=False, indent=1))
    return bool(actif)


def lire_cache(dossier=plateforme_acces.DOSSIER):
    try:
        brut = (Path(dossier) / CACHE).read_bytes()
        d = json.loads(brut.decode("utf-8")) if len(brut) < 4 * 1024 * 1024 else {}
    except (OSError, ValueError, UnicodeError):
        return {}
    return d if isinstance(d, dict) else {}


def _noter(dossier, projet, champs, masques):
    """Met à jour la fiche du projet dans le cache (valeurs masquées une fois de plus : jamais de jeton ni de secret)."""
    champs = HOTE.masquer(champs, masques)
    with _VERROU_CACHE:
        cache = lire_cache(dossier)
        fiche = cache.get(projet) if isinstance(cache.get(projet), dict) else {}
        fiche.update(champs, maj=_maintenant_iso())
        cache[projet] = fiche
        try:
            Path(dossier).mkdir(parents=True, exist_ok=True)
            ecrire_atomique(Path(dossier) / CACHE, json.dumps(cache, ensure_ascii=False, indent=1))
        except OSError:
            pass


# --- Appels au serveur ----------------------------------------------------------------------------------------------------

def _serveur(dossier):
    return serveur_tache.choisir_serveur(dossier, requises=CAPACITES)


def _deposer(serveur, ssh):
    if SCRIPT_LOCAL.is_symlink() or not SCRIPT_LOCAL.is_file():
        return "Fichier du dépôt introuvable : serveur_ovh/services/service.py."
    donnees = serveur_tache._archive([("services/service.py", SCRIPT_LOCAL.read_bytes(), 0o644)])
    code, _o, erreur = serveur_tache._octets(serveur, ssh, _DEPOSER, donnees, delai=120, silencieux=True)
    if code != 0:
        return f"Dépôt du script du service sur le serveur impossible (code {code}) : {serveur_tache._court(erreur, 200)}"
    return None


def _appel(serveur, ssh, commande, projet, commit=None, entree=b"", lignes=None, masques=()):
    """(code, réponse) du script hôte ; la réponse est l'objet JSON qu'il imprime (une seule ligne), masqué."""
    if not HOTE.MOTIF_PROJET.fullmatch(projet) or (commit is not None and not HOTE.MOTIF_COMMIT.fullmatch(commit)):
        raise ValueError("Identifiant de projet ou commit refusé.")
    argv = ["python3", f'"{SCRIPT_DISTANT}"', commande, projet] + ([commit] if commit else [])
    if lignes is not None:
        argv += ["--lignes", str(int(lignes))]
    code, sortie, erreur = serveur_tache._octets(serveur, ssh, " ".join(argv), entree,
                                                 delai=DELAIS.get(commande, 120), silencieux=True)
    texte = sortie.decode("utf-8", "replace").strip().splitlines() if isinstance(sortie, bytes) else []
    rep = None
    if texte:
        try:
            rep = json.loads(texte[-1])
        except ValueError:
            rep = None
    if not isinstance(rep, dict):
        raison = ("serveur injoignable" if code in INJOIGNABLE
                  else f"réponse illisible du serveur (code {code})")
        rep = {"statut": "echec", "detail": f"{commande} : {raison}. {serveur_tache._court(erreur, 200)}".strip()}
        code = code if code not in (0, 2, 75) else 1
    return code, HOTE.masquer(rep, list(masques))


def _sources(racine, commit, git=None):
    """L'archive tar des fichiers du commit (`git archive`, rien du dossier de travail) ; ValueError sinon."""
    executer = git or (lambda argv: subprocess.run(argv, cwd=str(racine), capture_output=True, timeout=600,
                                                   stdin=subprocess.DEVNULL))
    r = executer(["git", "-c", "core.fsmonitor=false", "archive", "--format=tar", commit])
    if r.returncode != 0 or not r.stdout:
        raise ValueError(f"git archive {commit[:12]} impossible.")
    if len(r.stdout) > SOURCES_MAX:
        raise ValueError("Sources du commit trop grosses (500 Mo au plus).")
    return r.stdout


def _commit(racine, commit=None):
    if commit is None:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(racine), capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        commit = r.stdout.strip() if r.returncode == 0 else ""
    if not HOTE.MOTIF_COMMIT.fullmatch(commit or ""):
        raise ValueError("Commit introuvable ou refusé (40 caractères hexadécimaux attendus).")
    return commit


def _variables(racine, bureau):
    """Les variables (non secrètes) que les réglages ENREGISTRÉS du projet donnent au service (`service.variables`)."""
    for fichier in deport_types.reglages_enregistres(racine, bureau):
        d = deport_types._lire_json_sur(fichier)
        s = d.get("service") if isinstance(d, dict) else None
        v = s.get("variables") if isinstance(s, dict) else None
        if isinstance(v, dict):
            return v
    return {}


def _preparer(racine, dossier, bureau):
    """(projet, serveur) après l'accord ; `_Refus` (code 2) ou `_Panne` (code 1) sinon."""
    racine = Path(racine).resolve()
    refus = deport_types.refus_accord(str(racine), ACTION, bureau=None if bureau is None else str(bureau))
    if refus:
        raise _Refus(refus)
    try:
        serveur = _serveur(dossier)
    except serveur_tache.RefusLancement as e:
        raise _Panne(str(e)) from None
    return identifiant(racine), serveur


class _Refus(Exception):
    pass


class _Panne(Exception):
    pass


def _adresse(serveur, port):
    return f"http://{serveur.hote}:{port}" if isinstance(port, int) else None


def _masques(projet, dossier):
    j = lire_jeton(projet, dossier)
    return [j] if j else []


def _garder(fonction):
    def enveloppe(racine, *a, **k):
        try:
            return fonction(racine, *a, **k)
        except _Refus as e:
            return 2, {"statut": "refus", "detail": str(e)}
        except _Panne as e:
            return 1, {"statut": "echec", "detail": str(e)}
        except ValueError as e:
            return 2, {"statut": "refus", "detail": str(e)}
    enveloppe.__name__, enveloppe.__doc__ = fonction.__name__, fonction.__doc__
    return enveloppe


@_garder
def poser_secrets(racine, valeurs, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, bureau=None):
    """Pose les secrets `valeurs` ({NOM: valeur}, saisis par le Directeur) sur le serveur : ils voyagent par l'entrée
    standard, sont rangés en 0600 et ne reviennent jamais (la réponse ne porte que les noms). Les secrets déjà posés
    et non repris sont gardés."""
    projet, serveur = _preparer(racine, dossier, bureau)
    HOTE.valider_valeurs(json.dumps(valeurs).encode("utf-8"), "secrets")
    masques = [v for v in valeurs.values() if isinstance(v, str) and len(v) >= 4] + _masques(projet, dossier)
    erreur = _deposer(serveur, ssh)
    if erreur:
        return 1, {"statut": "echec", "detail": erreur}
    code, rep = _appel(serveur, ssh, "poser-secrets", projet, entree=json.dumps(valeurs).encode("utf-8"),
                       masques=masques)
    if code == 0:
        _c, etat = _appel(serveur, ssh, "etat", projet, masques=masques)
        _noter(dossier, projet, {"etat": etat, "dossier": str(Path(racine).resolve())}, masques)
    return code, rep


def deploiement_abandonne(deploiement):
    """Vrai si un déploiement « en cours » du cache n'a plus de processus pour le mener (le moteur ou le bureau qui l'avait
    lancé a été relancé : essai réel FM_Stats, 2026-11-26, « en cours » resté affiché 20 minutes sans rien qui tourne)."""
    if not isinstance(deploiement, dict) or deploiement.get("statut") != "en_cours":
        return False
    pid = deploiement.get("pid")
    if not isinstance(pid, int):
        return False
    from moteur.verrou import pid_vivant
    return not pid_vivant(pid)


@_garder
def deployer(racine, commit=None, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, bureau=None, git=None):
    """Déploie le service du projet au commit donné (HEAD par défaut) : dépôt du script, sources, variables, puis
    déploiement avec santé et retour arrière au serveur. Le jeton est rangé au coffre du poste au premier succès."""
    racine = Path(racine).resolve()
    lire_declaration(racine)                       # refus au poste, avant toute connexion
    commit = _commit(racine, commit)
    projet, serveur = _preparer(racine, dossier, bureau)
    variables = _variables(racine, bureau)
    sources = _sources(racine, commit, git)
    masques = _masques(projet, dossier)
    _noter(dossier, projet, {"dossier": str(racine), "deploiement": {"commit": commit, "debut": _maintenant_iso(),
                                                                      "statut": "en_cours", "pid": os.getpid()}}, masques)
    erreur = _deposer(serveur, ssh)
    if erreur:
        _noter(dossier, projet, {"deploiement": {"commit": commit, "statut": "echec", "detail": erreur}}, masques)
        return 1, {"statut": "echec", "detail": erreur}
    etapes = [("recevoir", commit, sources)]
    if variables:
        etapes.append(("poser-variables", None, json.dumps(variables).encode("utf-8")))
    etapes.append(("deployer", commit, b""))
    for commande, c, entree in etapes:
        code, rep = _appel(serveur, ssh, commande, projet, c, entree, masques=masques)
        if code != 0:
            break
    if rep.get("statut") in ("ok", "retour_arriere") and not lire_jeton(projet, dossier):
        cj, rj = _appel(serveur, ssh, "jeton", projet)
        if cj == 0 and isinstance(rj.get("jeton"), str) and re.fullmatch(r"[A-Za-z0-9_-]{40,128}", rj["jeton"]):
            _ranger_jeton(projet, rj["jeton"], dossier)
    masques = _masques(projet, dossier)
    rep = HOTE.masquer(rep, masques)
    rep["adresse"] = _adresse(serveur, rep.get("port"))
    _ce, etat = _appel(serveur, ssh, "etat", projet, masques=masques)
    _noter(dossier, projet, {"etat": etat, "adresse": _adresse(serveur, etat.get("port")), "serveur": serveur.id,
                             "deploiement": {"commit": commit, "statut": rep.get("statut"),
                                             "detail": rep.get("detail"), "fin": _maintenant_iso()}}, masques)
    return code, rep


@_garder
def gerer(racine, commande, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, bureau=None, lignes=200):
    """`etat`, `journal`, `redemarrer`, `arreter`, `supprimer` sur le service du projet ; le cache est mis à jour."""
    if commande not in GESTION:
        raise ValueError(f"Commande inconnue : {commande!r}.")
    racine = Path(racine).resolve()
    projet, serveur = _preparer(racine, dossier, bureau)
    masques = _masques(projet, dossier)
    erreur = _deposer(serveur, ssh)
    if erreur:
        return 1, {"statut": "echec", "detail": erreur}
    code, rep = _appel(serveur, ssh, commande, projet, lignes=lignes if commande == "journal" else None,
                       masques=masques)
    champs = {"dossier": str(racine), "serveur": serveur.id}
    if commande == "journal":
        champs["journal"] = {"lignes": rep.get("lignes", []), "le": _maintenant_iso()}
    elif commande == "supprimer" and code == 0:
        _oublier_jeton(projet, dossier)
    if commande != "journal":
        _ce, etat = (code, rep) if commande == "etat" else _appel(serveur, ssh, "etat", projet, masques=masques)
        champs["etat"] = etat
        champs["adresse"] = _adresse(serveur, etat.get("port"))
        rep = dict(rep, adresse=champs["adresse"]) if commande == "etat" else rep
    champs["derniere_action"] = {"commande": commande, "statut": rep.get("statut"), "detail": rep.get("detail"),
                                 "le": _maintenant_iso()}
    _noter(dossier, projet, champs, masques)
    return code, rep


@_garder
def jeton_depuis_serveur(racine, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, bureau=None):
    """Relit le jeton au serveur et le range au coffre (s'il manque au poste). Ne le rend qu'à l'appelant."""
    projet, serveur = _preparer(racine, dossier, bureau)
    j = lire_jeton(projet, dossier)
    if j:
        return 0, {"statut": "ok", "jeton": j}
    if _deposer(serveur, ssh):
        return 1, {"statut": "echec", "detail": "Dépôt du script impossible."}
    code, rep = _appel(serveur, ssh, "jeton", projet)
    if code == 0 and isinstance(rep.get("jeton"), str) and re.fullmatch(r"[A-Za-z0-9_-]{40,128}", rep["jeton"]):
        _ranger_jeton(projet, rep["jeton"], dossier)
    return code, rep


# --- Commande -------------------------------------------------------------------------------------------------------------

USAGE = ("Usage : py -3.12 lancer.py service <etat|journal|deployer|mettre-a-jour|redemarrer|arreter|supprimer|jeton|"
         "secrets <NOM>...> [--dossier <projet>] [--commit <sha>] [--lignes N]")


def _analyser(argv):
    argv = list(argv)
    opt = {"commande": None, "dossier": None, "commit": None, "lignes": 200, "noms": []}
    while argv:
        o = argv.pop(0)
        if o in ("--dossier", "--commit", "--lignes") and argv:
            v = argv.pop(0)
            if o == "--lignes":
                if not re.fullmatch(r"[1-9][0-9]{0,2}", v) or int(v) > 200:
                    return None
                v = int(v)
            opt[o[2:]] = v
        elif not o.startswith("-") and opt["commande"] is None:
            opt["commande"] = o
        elif not o.startswith("-") and opt["commande"] == "secrets":
            opt["noms"].append(o)
        else:
            return None
    return opt if opt["commande"] in COMMANDES else None


def _imprimer(rep):
    print(json.dumps(rep, ensure_ascii=False, indent=1))


def main(argv=None, environ=None, saisir=getpass.getpass, est_tty=None, dossier=plateforme_acces.DOSSIER,
         ssh=plateforme_ssh, bureau=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["service"]:
        argv = argv[1:]
    environ = os.environ if environ is None else environ
    est_tty = est_tty or (lambda: sys.stdin.isatty())
    opt = _analyser(argv)
    if opt is None:
        print(USAGE, file=sys.stderr)
        return 2
    commande = opt["commande"]
    if environ.get(VARIABLE_AGENT) and commande not in COMMANDES_AGENT:
        print(MSG_DIRECTEUR % (commande, commande), file=sys.stderr)
        return 2
    racine = deport_types.racine_du_projet(opt["dossier"] or os.getcwd())
    k = {"dossier": dossier, "ssh": ssh, "bureau": bureau}
    if commande == "secrets":
        if not opt["noms"]:
            print("Donnez le nom de chaque secret : service secrets <NOM>...", file=sys.stderr)
            return 2
        if not est_tty():
            print("Les secrets se saisissent au terminal (sans écho) ou au bureau (zone Services), jamais par l'entrée "
                  "standard ni en argument.", file=sys.stderr)
            return 2
        valeurs = {n: saisir(f"Valeur de {n} (rien ne s'affiche) : ") for n in opt["noms"]}
        code, rep = poser_secrets(racine, valeurs, **k)
    elif commande == "jeton":
        code, rep = jeton_depuis_serveur(racine, **k)
        if code == 0:
            print(rep["jeton"])
            return 0
    elif commande in ("deployer", "mettre-a-jour"):
        code, rep = deployer(racine, opt["commit"], **k)
    else:
        code, rep = gerer(racine, commande, lignes=opt["lignes"], **k)
    _imprimer({k2: v for k2, v in rep.items() if k2 != "jeton"})
    return code


if __name__ == "__main__":
    sys.exit(main())
