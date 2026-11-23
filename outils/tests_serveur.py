"""La route serveur d'une campagne de tests (conception § 5.4) : instantané tar de l'arbre de travail, déposé par SSH dans
`~/tests/<id>/entree/entree.tar`, puis UNE session SSH qui lance l'enveloppe `lancer_tests.sh` (place, conteneur sans
réseau, sortie en direct, `#fin`) ; l'entrée standard de la session est la laisse.

Repli au poste (sous le verrou du poste, `campagne.executer`), UNE fois, avec une ligne, dans ces cas seulement :
  R1 aucun serveur prêt pour `tests-image` (état local) ; R2 dépôt en échec de connexion (255/124) ; R3 l'enveloppe refuse
  pour le disque (76), l'image (77) ou le cache des dépendances (78, 79) ; R4 session perdue avant `#fin` (255/124) ;
  R5 instantané hors limites ou projet hors git (et tout ce qui empêche l'envoi avant la moindre connexion).
Jamais de repli : test en échec (code de la commande), Ctrl-C (130, rien n'est relancé), `--serveur` (code 4), argument
refusé par l'enveloppe (2), `--sans-attendre` sur places prises (3). Après R2 ou R4, le serveur est noté injoignable
300 s (`INJOIGNABLE`) : pendant ce temps, poste sans aucun essai SSH ; une campagne menée à `#fin` l'efface.

Le code rendu n'est JAMAIS lu dans la sortie : seule la marque `#fin` validée par `plateforme_ssh.executer_en_flux` fait
foi, et un code de l'enveloppe (2, 70, 76, 77, 78…) n'est pris pour un refus que si la session a lu `#refus` (clé `refus`).

Python 3.12 ; importé à l'appel seulement, ou lancé à part : `serveur-tests [--dossier D] [--sans-attendre] [--serveur]
-- <commande>`.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

import campagne  # noqa: E402
import plateforme_acces  # noqa: E402
import plateforme_ssh  # noqa: E402
import serveur_etat  # noqa: E402
import serveur_tache  # noqa: E402
import tests_instantane  # noqa: E402
from plateforme import DOSSIER_DISTANT  # noqa: E402

LIMITES = {"cpus": 4, "memoire_mo": 8192, "duree_s": 1800}
PLACES_DEFAUT = 2
PLACES_MAX = 4
INJOIGNABLE_S = 300
INJOIGNABLE = Path("~/MyIAFactory/tests-serveur-injoignable.json").expanduser()
ENVELOPPE_DISTANTE = f"{DOSSIER_DISTANT}/taches/lancer_tests.sh"
REQUISES = ("tests-image",)
DELAI_DEPOT_S = 900                     # 200 Mo au plus : large même sur une liaison lente
COMMANDE_MAX_OCTETS = 4096
COMMANDE_MAX_ELEMENTS = 64
INJOIGNABLES = (124, 255)               # délai dépassé, connexion SSH impossible ou perdue
REFUS_REPLI = (76, 77, 78, 79)          # disque, image, cache des dépendances absent, échauffement en échec
CODES_CTRL_C = (130, 0xC000013A, -2)    # ssh tué par le Ctrl-C (console Windows : STATUS_CONTROL_C_EXIT ; POSIX : SIGINT)
FIN_GARDEE = 4096
MOTIF_PROJET = re.compile(r"[a-z0-9][a-z0-9-]{0,39}", re.ASCII)
MOTIF_DEPS = re.compile(r"[0-9a-f]{16}", re.ASCII)


class Repli(Exception):
    """La campagne ne peut pas partir au serveur (ou n'y a pas été menée) ; `.raison` est dite au poste."""

    def __init__(self, raison, injoignable=None):
        Exception.__init__(self, raison)
        self.raison = raison
        self.injoignable = injoignable      # identifiant du serveur à noter injoignable (R2, R4), sinon None


def commande_conteneur(commande: List[str]) -> List[str]:
    """La commande du poste telle que le conteneur Linux la lance : `py`, `py -3.12`, `python`, `python.exe` en tête →
    `python3` ; `npx.cmd`/`npm.cmd` → `npx`/`npm` ; le reste tel quel."""
    commande = [str(x) for x in commande]
    if not commande:
        return commande
    tete = commande[0].lower()
    if tete in ("py", "py.exe"):
        reste = commande[1:]
        if reste and reste[0].startswith("-3"):
            reste = reste[1:]
        return ["python3", *reste]
    if tete in ("python", "python.exe"):
        return ["python3", *commande[1:]]
    if tete in ("npx.cmd", "npm.cmd"):
        return [tete[:-4], *commande[1:]]
    return commande


# --- mémoire de l'injoignable --------------------------------------------------------------------------------------

def _injoignable_actif(chemin, serveur_id, maintenant):
    """Vrai si `chemin` dit ce serveur injoignable jusqu'à une date à venir, et au plus 300 s devant (horloge reculée ou
    fichier forgé : ignoré). Ne lève jamais."""
    try:
        with open(chemin, "rb") as f:
            x = json.loads(f.read(4096).decode("utf-8"))
        jusqu_a = x.get("jusqu_a")
        if x.get("serveur_id") != serveur_id or isinstance(jusqu_a, bool) or not isinstance(jusqu_a, (int, float)):
            return False
        return maintenant < jusqu_a <= maintenant + INJOIGNABLE_S
    except (OSError, ValueError, AttributeError):
        return False


def _noter_injoignable(chemin, serveur_id, maintenant):
    try:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        temporaire = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
        temporaire.write_text(json.dumps({"serveur_id": serveur_id, "jusqu_a": maintenant + INJOIGNABLE_S}),
                              encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        pass        # une économie : sans elle, la prochaine campagne réessaie


def _oublier_injoignable(chemin):
    try:
        Path(chemin).unlink()
    except OSError:
        pass


# --- sorties ---------------------------------------------------------------------------------------------------------

class _ErreurMontree:
    """Reçoit de `executer_en_flux` la sortie d'erreur ligne par ligne (marques déjà retirées) : le préfixe `| ` de
    l'enveloppe (sortie d'erreur du conteneur : unittest y écrit) est ôté pour l'affichage ; la fin (4 Ko) est gardée
    pour compter les tests."""

    def __init__(self, flux):
        self.flux = flux
        self.fin = b""

    def write(self, b):
        if b.startswith(b"| "):
            b = b[2:]
        elif b == b"|\n":
            b = b"\n"
        self.fin = (self.fin + b)[-FIN_GARDEE:]
        if self.flux is not None:
            try:
                self.flux.write(b)
            except (OSError, ValueError):
                self.flux = None

    def flush(self):
        if self.flux is not None:
            try:
                self.flux.flush()
            except (OSError, ValueError):
                self.flux = None


def _erreur_du_poste():
    flux = sys.stderr
    if flux is None:
        return None
    try:
        flux.flush()
    except (OSError, ValueError):
        pass
    tampon = getattr(flux, "buffer", None)
    return tampon if tampon is not None else campagne._VersTexte(flux)


def _fin_pour_la_mesure(fin_sortie, fin_erreur):
    """Le texte dont `tests_mesures.nb_tests_de` lit les dernières lignes : unittest résume sur la sortie d'erreur, les
    autres outils (vitest, jest, tests_paralleles) sur la sortie standard ; celle qui porte un résumé passe en dernier."""
    try:
        from bureau import tests_mesures
    except ImportError:
        try:
            sys.path.append(str(ICI.parent))
            from bureau import tests_mesures
        except ImportError:
            return fin_sortie + "\n" + fin_erreur
    if tests_mesures.nb_tests_de(fin_sortie) is not None and tests_mesures.nb_tests_de(fin_erreur) is None:
        return fin_erreur + "\n" + fin_sortie
    return fin_sortie + "\n" + fin_erreur


def _noter_par_defaut(dossier, **mesure):
    return campagne._noter_par_defaut(dossier, **mesure)


def _projet_par_defaut(dossier):
    try:
        from bureau import tests_mesures
    except ImportError:
        sys.path.append(str(ICI.parent))
        from bureau import tests_mesures
    return tests_mesures.projet_enregistre(dossier)


# --- la route --------------------------------------------------------------------------------------------------------

def _premiere_ligne(commande):
    distante = commande_conteneur(commande)
    if not distante or len(distante) > COMMANDE_MAX_ELEMENTS:
        raise Repli(f"refusé (commande de {len(distante)} éléments : 1 à {COMMANDE_MAX_ELEMENTS})")
    ligne = json.dumps(distante, ensure_ascii=False).encode("utf-8")
    if len(ligne) > COMMANDE_MAX_OCTETS:
        raise Repli(f"refusé (commande de plus de {COMMANDE_MAX_OCTETS} octets)")
    return ligne


def _instantane(instantane, racine, fichier, dire):
    """Écrit l'archive dans `fichier` ; `Repli` (R5) si elle ne peut pas partir."""
    try:
        fichiers, ecartes = instantane.lister(racine)
        if ecartes:
            dire(f"Instantané : {len(ecartes)} fichier(s) écarté(s) : " + ", ".join(ecartes[:10])
                 + (" …" if len(ecartes) > 10 else ""))
        executables = instantane.executables(racine)
        with open(fichier, "wb") as f:
            instantane.ecrire_tar(racine, fichiers, f, executables=executables)
    except instantane.HorsLimites as e:
        raise Repli(f"refusé (instantané : {e.raison})") from None
    except OSError as e:
        raise Repli(f"refusé (instantané impossible : {type(e).__name__})") from None


def _deposer(serveur, ssh, ident, fichier):
    """Dépose l'archive (lue depuis le fichier par ssh, jamais en mémoire) ; `Repli` (R2) si le serveur ne répond pas."""
    base = f"\"$HOME/tests/{ident}/entree\""
    commande = f"umask 077 && install -d -m 700 {base} && set -C && cat > \"$HOME/tests/{ident}/entree/entree.tar\""
    with open(fichier, "rb") as f:
        code, _sortie, _erreur = serveur_tache._octets(serveur, ssh, commande, f, DELAI_DEPOT_S)
    if code in INJOIGNABLES:
        raise Repli(f"injoignable (dépôt de l'instantané : code {code})", injoignable=serveur.id)
    if code != 0:
        raise Repli(f"refusé (dépôt de l'instantané : code {code})")


class _Attente:
    """`#attente r t` : note pour le bureau (comme l'attente du verrou), une ligne à chaque changement ; sans attendre,
    la session est coupée dès la première (places toutes prises : code 3)."""

    def __init__(self, attentes, racine, attendre, dire, maintenant):
        self.attentes, self.racine, self.attendre, self.dire = attentes, racine, attendre, dire
        self.maintenant = maintenant
        self.processus = None
        self.refuse = None
        self.dit = None
        self.notee = False
        self.depuis = None
        self.arrivee = None
        self.verrou = threading.Lock()

    def popen(self, base):
        def lancer(*a, **k):
            p = base(*a, **k)
            with self.verrou:
                self.processus = p
            return p
        return lancer

    def __call__(self, rang, total):
        motif = f"place de tests au serveur (rang {rang}/{total})"
        if not self.attendre:
            with self.verrou:
                if self.refuse is None:
                    self.refuse = motif
                p = self.processus
            if p is not None:
                try:
                    p.kill()        # la laisse tombe : l'enveloppe quitte la file, aucun conteneur ne reste
                except OSError:
                    pass
            return
        if motif == self.dit:
            return
        self.dit = motif
        self.dire(f"En attente : {motif}.", flush=True)
        self.depuis = self.depuis or datetime.now().astimezone().isoformat(timespec="seconds")
        self.arrivee = self.arrivee or self.maintenant()
        campagne._noter_l_attente(self.attentes, self.racine, motif, self.depuis, self.arrivee)
        self.notee = True

    def oublier(self):
        if self.notee:
            campagne._oublier_l_attente(self.attentes)


def _au_serveur(commande, racine, attendre, places, dossier_etat, ssh, noter, horloge, maintenant, dire, choisir,
                instantane, projet_de, injoignable, attentes, sortie, sortie_erreur, nouvel_id, forcer, popen_base):
    """La campagne au serveur ; rend son code, ou lève `Repli`. `KeyboardInterrupt` remonte telle quelle."""
    appel = horloge()
    try:
        serveur = choisir(dossier_etat, requises=REQUISES)
    except serveur_tache.RefusLancement as e:
        raise Repli(f"indisponible ({e})") from None
    if not forcer and _injoignable_actif(injoignable, serveur.id, maintenant()):
        raise Repli("injoignable il y a moins de 5 minutes")
    try:
        serveur_etat.cible(serveur)
    except ValueError as e:
        raise Repli(f"mal déclaré ({e})") from None
    trouve = projet_de(racine)
    projet = trouve[0] if trouve else None
    if not isinstance(projet, str) or not MOTIF_PROJET.fullmatch(projet):
        raise Repli("refusé (projet non enregistré au bureau)")
    if places is None:
        places = PLACES_DEFAUT
    if isinstance(places, bool) or not isinstance(places, int) or not 1 <= places <= PLACES_MAX:
        raise Repli(f"refusé (places {places!r} : 1 à {PLACES_MAX})")
    ligne = _premiere_ligne(commande)
    ident = nouvel_id()
    if not isinstance(ident, str) or not serveur_tache.MOTIF_ID.fullmatch(ident):
        raise Repli("refusé (identifiant de campagne invalide)")

    prive = tempfile.mkdtemp(prefix="myiafactory-tests-")      # 0700 ; jamais dans le projet
    try:
        archive = os.path.join(prive, "entree.tar")
        _instantane(instantane, racine, archive, dire)
        deps = instantane.empreinte_verrou_node(racine) or "-"
        if deps != "-" and not MOTIF_DEPS.fullmatch(deps):
            raise Repli("refusé (empreinte du verrou Node invalide)")
        _deposer(serveur, ssh, ident, archive)
    finally:
        shutil.rmtree(prive, ignore_errors=True)

    distante = (f"{ENVELOPPE_DISTANTE} {ident} {places} {LIMITES['cpus']} {LIMITES['memoire_mo']} {LIMITES['duree_s']} "
                f"{projet} {deps}")
    attente = _Attente(attentes, racine, attendre, dire, maintenant)
    erreur = _ErreurMontree(sortie_erreur if sortie_erreur is not None else _erreur_du_poste())
    depart = horloge()
    try:
        r = ssh.executer_en_flux(serveur_etat.cible(serveur), distante, serveur.cle, ligne,
                                 sortie if sortie is not None else campagne._sortie_du_poste(),
                                 sur_attente=attente, popen=attente.popen(popen_base), sortie_erreur=erreur)
    finally:
        attente.oublier()
    fin_serveur, refus = r.get("fin_serveur"), r.get("refus")
    code, code_ssh = r.get("code"), r.get("code_ssh")

    if attente.refuse is not None and (fin_serveur is None or fin_serveur[0] == 130):
        dire(f"Refusé : {attente.refuse} toutes prises. Les campagnes attendent leur tour au serveur.")
        return 3
    if fin_serveur is None:
        if code_ssh in CODES_CTRL_C or code in CODES_CTRL_C:
            return 130                   # ssh arrêté par le Ctrl-C : rien n'est relancé
        if code in INJOIGNABLES:
            raise Repli(f"injoignable (session perdue avant la fin : {r.get('raison') or code})",
                        injoignable=serveur.id)
        dire(f"Serveur : fin de campagne non confirmée (code {code}) ; résultat inconnu, compté en échec.")
        return 1
    _oublier_injoignable(injoignable)       # le serveur a mené la session jusqu'à #fin
    if refus is not None:
        if refus in REFUS_REPLI:
            raise Repli(f"en refus (code {refus} de l'enveloppe)")
        if refus == 130:
            return 130               # laisse coupée : la session est partie, rien n'est relancé
        dire(f"Serveur : l'enveloppe a refusé la campagne (code {refus}).")
        return refus
    try:
        _code, debut, fin, attente_s = fin_serveur
        (noter or _noter_par_defaut)(
            racine, commande=" ".join(str(x) for x in commande), duree_s=max(0, fin - debut),
            attente_s=max(0.0, depart - appel) + max(0, attente_s), code=code,
            fin=_fin_pour_la_mesure(r.get("fin") or "", erreur.fin.decode("utf-8", "replace")),
            octets=r.get("octets"), lieu="serveur", tache=os.environ.get(campagne.VARIABLE_TACHE) or None)
    except Exception:  # noqa: BLE001 — la mesure ne casse jamais une campagne
        pass
    return code


def executer(commande, dossier=None, attendre=True, forcer=False, places=None, dossier_etat=plateforme_acces.DOSSIER,
             ssh=plateforme_ssh, executer_poste=campagne.executer, noter=None, horloge=time.monotonic,
             maintenant=time.time, dire=print, *, choisir=None, instantane=tests_instantane, projet_de=None,
             injoignable=INJOIGNABLE, attentes=campagne.ATTENTES, sortie=None, sortie_erreur=None,
             nouvel_id=serveur_tache.nouvel_id, _popen=subprocess.Popen) -> int:
    """Lance `commande` au serveur et rend son code ; sinon (règles R1–R5) au poste, une fois, sous son verrou. Avec
    `forcer` (`--serveur`) : jamais de repli, la raison est dite et le code est 4. `KeyboardInterrupt` remonte (le
    lanceur rend 130) : rien n'est relancé, rien n'est noté."""
    commande = [str(x) for x in commande]
    racine = str(Path(dossier or os.getcwd()).resolve())
    try:
        return _au_serveur(commande, racine, attendre, places, dossier_etat, ssh, noter, horloge, maintenant, dire,
                           choisir or serveur_tache.choisir_serveur, instantane, projet_de or _projet_par_defaut,
                           injoignable, attentes, sortie, sortie_erreur, nouvel_id, forcer, _popen)
    except Repli as e:
        repli = e
    if isinstance(repli.injoignable, str):
        _noter_injoignable(injoignable, repli.injoignable, maintenant())
    if forcer:
        dire(f"Serveur {repli.raison}.")
        return 4
    dire(f"Serveur {repli.raison} : tests au poste (une campagne à la fois).")
    return executer_poste(commande, dossier=dossier, attendre=attendre)


def main(argv=None, executer=executer) -> int:
    """`serveur-tests [--dossier D] [--sans-attendre] [--serveur] -- <commande>`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv or argv.index("--") == len(argv) - 1:
        print("Usage : serveur-tests [--dossier <dossier>] [--sans-attendre] [--serveur] -- <commande de test>",
              file=sys.stderr)
        return 2
    i = argv.index("--")
    options, commande = argv[:i], argv[i + 1:]
    dossier, attendre, forcer = None, True, False
    while options:
        o = options.pop(0)
        if o == "--dossier" and options:
            dossier = options.pop(0)
        elif o == "--sans-attendre":
            attendre = False
        elif o == "--serveur":
            forcer = True
        else:
            print(f"Option inconnue : {o}", file=sys.stderr)
            return 2
    try:
        return executer(commande, dossier=dossier, attendre=attendre, forcer=forcer)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
