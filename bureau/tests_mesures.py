"""Le journal des campagnes de tests d'un projet : `<racine>/.factory/tests-mesures.jsonl`, une ligne JSON par campagne.

`{"t": "2026-11-23T10:12:03+01:00", "lieu": "poste", "source": "mesure", "tache": null, "commande": "npx vitest run",
"portee": "complete", "duree_s": 412.6, "attente_s": 35.0, "code": 0, "nb_tests": 318, "sortie_octets": 48211}`
(plus `n`, le numéro de campagne donné par le sceau, et `run`, l'exécution GitHub, quand on les connaît).

Seul un projet ENREGISTRÉ au bureau a un journal (un sous-dossier ou une copie de travail est rangé sous son projet ;
un dossier non enregistré n'écrit rien). La mesure est passive et ne casse jamais une campagne : `noter_campagne` et
`noter_declarations` taisent toute erreur ; `lire` ne lève jamais et ignore les lignes abîmées.

Reste compatible Python 3.9 : le lanceur des agents (`outils/campagne.py`, `outils/deporter.py`) l'importe."""
import json
import math
import os
import re
import stat
import tempfile
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

from . import tests_sceau
from .deport_types import _lire_json_sur, _norme, _racine_des_reglages, _sans_prefixe
from .tests_sceau import SCEAU, SceauIllisible, _maintenant  # noqa: F401 — SceauIllisible : pour les appelants
from .verrou_fichier import remplacer, verrou_fichier

BUREAU = Path("~/MyIAFactory/bureau.json").expanduser()
NOM_JOURNAL = "tests-mesures.jsonl"
MAX_LIGNES = 2000
LIGNES_APRES_ROTATION = 1800      # la rotation garde de la marge : une réécriture toutes les 200 campagnes
MAX_OCTETS_LIGNE = 2048
MAX_COMMANDE = 200
LIEUX = ("poste", "github", "cloud", "serveur")
SOURCES = ("mesure", "declare")
PORTEES = ("complete", "partielle")
SEUIL_BAISSE = 0.02

MAX_TACHE = 100                  # bornes des autres textes : une ligne reste sous 2 Ko, même tout en caractères de 4 octets
MAX_RUN = 40
MAX_T = 40
MAX_DECLARATIONS = 20            # comme le champ `tests` d'un rapport
RUN_RECENTS = 50                 # une exécution GitHub déjà notée dans ces dernières lignes ne l'est pas deux fois
LECTURE_MAX = MAX_LIGNES * MAX_OCTETS_LIGNE      # on ne lit jamais plus que la fin utile du journal (4 Mo)
SEUIL_ROTATION = MAX_LIGNES * 64                 # en dessous, le journal ne peut pas dépasser 2 000 vraies lignes
_PORTEE_AGENT = {"touches": "partielle", "partielle": "partielle", "complete": "complete"}
_MOTIF_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")      # celui de `releve.MOTIF_GENRE` (id de projet)


# ---------------------------------------------------------------------------------------------------- le projet


def _id_par_defaut(fichier):
    """La règle de `reglages._id_par_defaut` : le nom du dossier des réglages (son parent pour `.factory`), ramené à
    `[a-z0-9-]`."""
    dossier = Path(fichier).parent
    if dossier.name == ".factory":
        dossier = dossier.parent
    texte = unicodedata.normalize("NFKD", dossier.name).encode("ascii", "ignore").decode("ascii").lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")
    return texte[:40].rstrip("-") or "projet"


def _ids_du_bureau(projets, base):
    """`[(id, fichier de réglages)]` dans l'ordre du bureau, les id comme `reglages.lire_bureau` (donnés, sinon le nom
    du dossier, doublons suffixés `-2`, `-3`). `None` si le bureau est de ceux que `lire_bureau` refuse sur les id ou
    les chemins (on ne devine pas un id)."""
    entrees = []
    for p in projets:
        id_ = None
        if isinstance(p, dict):
            id_ = p.get("id")
            p = p.get("chemin")
            if id_ is not None and (not isinstance(id_, str) or not _MOTIF_ID.match(id_)):
                return None
        if not isinstance(p, str) or not p.strip() or "\x00" in p:
            return None
        entrees.append((id_, Path(base) / p))
    donnes = [i for i, _ in entrees if i is not None]
    if len(donnes) != len(set(donnes)):
        return None
    pris, sortie = set(donnes), []
    for id_, fichier in entrees:
        if id_ is None:
            base_id = _id_par_defaut(fichier)
            id_, n = base_id, 1
            while id_ in pris:
                n += 1
                suffixe = "-%d" % n
                id_ = base_id[:40 - len(suffixe)].rstrip("-") + suffixe
            pris.add(id_)
        sortie.append((id_, str(fichier)))
    return sortie


def _contient(racine, cible):
    return cible == racine or cible.startswith(racine if racine.endswith(os.sep) else racine + os.sep)


def projet_enregistre(dossier, bureau=BUREAU) -> Optional[Tuple[str, Path]]:
    """`(id, racine)` du projet du bureau dont la racine (dossier de `reglages.json`, ou parent de `.factory`) contient
    `dossier` — le plus long s'ils s'emboîtent ; chemins comparés par `deport_types._norme` (préfixe `\\\\?\\`, casse
    sous Windows, liens). Une entrée dont le fichier de réglages mène dans un autre projet (lien, jonction) est écartée.
    Aucun : `None`. Ne lève jamais."""
    try:
        donnees = _lire_json_sur(str(bureau))
        projets = donnees.get("projets") if isinstance(donnees, dict) else None
        if not isinstance(projets, list):
            return None
        base = os.path.dirname(os.path.abspath(str(bureau)))
        entrees = _ids_du_bureau(projets, base)
        if not entrees:
            return None
        cible = _norme(dossier)
        meilleur = None
        for id_, fichier in entrees:
            try:
                fichier = os.path.abspath(_sans_prefixe(fichier))
                racine = _racine_des_reglages(fichier)
                norme = _norme(racine)
                if _norme(_racine_des_reglages(os.path.realpath(fichier))) != norme:
                    continue
            except (OSError, ValueError):
                continue
            if _contient(norme, cible) and (meilleur is None or len(norme) > len(meilleur[0])):
                meilleur = (norme, id_, Path(racine))
        return None if meilleur is None else (meilleur[1], meilleur[2])
    except Exception:  # noqa: BLE001 — la résolution ne casse jamais une campagne
        return None


def journal_de(racine) -> Path:
    return Path(racine) / ".factory" / NOM_JOURNAL


# ---------------------------------------------------------------------------------------------------- une ligne


def _nombre(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and v >= 0


def _texte(v, maxi):
    """`v` tronqué à `maxi` caractères, toujours encodable en UTF-8 (un caractère orphelin devient `?`)."""
    return v[:maxi].encode("utf-8", "replace").decode("utf-8")


def _entier_ou_rien(v, nom):
    if v is not None and (type(v) is not int or v < 0):
        raise ValueError("« %s » doit être un entier positif ou nul" % nom)
    return v


def ligne(*, lieu, source, tache, commande, portee, duree_s, attente_s, code, nb_tests=None, sortie_octets=None,
          n=None, run=None, t) -> dict:
    """Une ligne du journal, à la forme du spec. `ValueError` si une valeur est hors de sa liste ou de son type."""
    if lieu not in LIEUX:
        raise ValueError("lieu inconnu : %r" % (lieu,))
    if source not in SOURCES:
        raise ValueError("source inconnue : %r" % (source,))
    if portee not in PORTEES:
        raise ValueError("portée inconnue : %r" % (portee,))
    if not isinstance(commande, str):
        raise ValueError("« commande » doit être un texte")
    if tache is not None and not isinstance(tache, str):
        raise ValueError("« tache » doit être un texte ou nul")
    if not _nombre(duree_s) or not _nombre(attente_s):
        raise ValueError("« duree_s » et « attente_s » doivent être des nombres positifs ou nuls")
    if code is not None and type(code) is not int:
        raise ValueError("« code » doit être un entier")
    if not isinstance(t, str):
        raise ValueError("« t » doit être une date (texte)")
    if run is not None and (isinstance(run, bool) or not isinstance(run, (int, str))):
        raise ValueError("« run » doit être un entier ou un texte")
    sortie = {"t": _texte(t, MAX_T), "lieu": lieu, "source": source,
              "tache": None if tache is None else _texte(tache, MAX_TACHE),
              "commande": _texte(commande, MAX_COMMANDE), "portee": portee,
              "duree_s": round(float(duree_s), 1), "attente_s": round(float(attente_s), 1), "code": code,
              "nb_tests": _entier_ou_rien(nb_tests, "nb_tests"),
              "sortie_octets": _entier_ou_rien(sortie_octets, "sortie_octets")}
    if n is not None:
        sortie["n"] = _entier_ou_rien(n, "n")
    if run is not None:
        sortie["run"] = _texte(run, MAX_RUN) if isinstance(run, str) else run
    return sortie


# ---------------------------------------------------------------------------------------------------- le fichier


def _refuser_constante(nom):
    raise ValueError("valeur non JSON : %s" % nom)


_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _est_un_lien(s):
    """Vrai pour un lien symbolique, ou, sous Windows, tout point d'analyse (jonction, lien) : jamais suivi."""
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, "st_file_attributes", 0) & _REPARSE)


def _exiger_dossier_sur(dossier):
    """`OSError` si le dossier du journal (`.factory`) est un lien, une jonction ou autre chose qu'un dossier : on
    n'écrit jamais dans un autre dossier par ce détour."""
    s = os.lstat(str(dossier))
    if _est_un_lien(s) or not stat.S_ISDIR(s.st_mode):
        raise OSError("le dossier du journal est un lien ou n'est pas un dossier : %s" % dossier)


def _exiger_fichier_ordinaire(chemin, unique=False):
    """`OSError` si `chemin` existe sans être un fichier ordinaire (dossier, lien, jonction, périphérique) ou, avec
    `unique`, s'il a d'autres noms (lien dur : écrire dedans écrirait dans un autre fichier). Absent : rien à dire."""
    try:
        s = os.lstat(str(chemin))
    except FileNotFoundError:
        return None
    if _est_un_lien(s) or not stat.S_ISREG(s.st_mode):
        raise OSError("le journal n'est pas un fichier ordinaire : %s" % chemin)
    if unique and s.st_nlink != 1:
        raise OSError("le journal a plusieurs noms (lien dur) : %s" % chemin)
    return s


def _ouvrir_sur(chemin, drapeaux):
    """Ouvre le journal sans suivre de lien, puis vérifie sur le descripteur que c'est bien un fichier ordinaire à un
    seul nom, et le même que celui du chemin (pas d'échange entre la vérification et l'ouverture). Rend le
    descripteur ; `OSError` sinon (descripteur fermé)."""
    _exiger_fichier_ordinaire(chemin, unique=True)
    fd = os.open(str(chemin), drapeaux | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        f = os.fstat(fd)
        l = _exiger_fichier_ordinaire(chemin, unique=True)
        if (not stat.S_ISREG(f.st_mode) or f.st_nlink != 1 or l is None
                or (f.st_ino and l.st_ino and f.st_ino != l.st_ino)):
            raise OSError("le journal a changé pendant son ouverture : %s" % chemin)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _lire_fin(chemin, maxi=LECTURE_MAX, strict=False):
    """`(octets, complet)` : tout le fichier s'il fait au plus `maxi` octets, sinon sa fin, à partir d'une ligne
    entière. Fichier ordinaire seulement (`OSError` sinon) ; `strict` : ouvert comme pour écrire (un seul nom)."""
    if strict:
        fd = _ouvrir_sur(chemin, os.O_RDONLY)
    else:
        _exiger_fichier_ordinaire(chemin)
        fd = os.open(str(chemin), os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as f:
        taille = os.fstat(f.fileno()).st_size
        if taille <= maxi:
            return f.read(maxi + 1), True
        f.seek(taille - maxi)
        brut = f.read(maxi)
    coupure = brut.find(b"\n")
    return (brut[coupure + 1:] if coupure >= 0 else b""), False


def ajouter(chemin: Path, ligne: dict) -> None:
    """Ajoute `ligne` (JSON sur une ligne, 2 Ko au plus, sinon `ValueError`) au journal ; au-delà de `MAX_LIGNES`, le
    réécrit par fichier temporaire puis `os.replace` en gardant les `LIGNES_APRES_ROTATION` dernières (la marge évite
    une réécriture à chaque ajout). Jamais à travers un lien, une jonction ou un lien dur. Peut lever `OSError`."""
    brut = json.dumps(ligne, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    if len(brut) > MAX_OCTETS_LIGNE:
        raise ValueError("ligne de journal trop longue (%d octets)" % len(brut))
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    _exiger_dossier_sur(chemin.parent)
    fd = _ouvrir_sur(chemin, os.O_RDWR | os.O_APPEND | os.O_CREAT)
    try:
        taille = os.fstat(fd).st_size
        if taille:                                       # une dernière ligne tronquée ne doit pas avaler la nôtre
            os.lseek(fd, taille - 1, os.SEEK_SET)
            if os.read(fd, 1) != b"\n":
                brut = b"\n" + brut
        reste = memoryview(brut)
        while reste:
            reste = reste[os.write(fd, reste):]
        taille += len(brut)
    finally:
        os.close(fd)
    if taille > SEUIL_ROTATION:
        _tourner(chemin)


def _tourner(chemin):
    """Garde les `LIGNES_APRES_ROTATION` dernières lignes si le journal en compte plus de `MAX_LIGNES` (ou s'il dépasse
    la lecture bornée). Même prudence qu'à l'ajout : dossier et fichier vérifiés avant de lire et avant de remplacer."""
    _exiger_dossier_sur(chemin.parent)
    brut, complet = _lire_fin(chemin, strict=True)
    lignes = [l for l in brut.split(b"\n") if l.strip()]
    if complet and len(lignes) <= MAX_LIGNES:
        return
    fd, temporaire = tempfile.mkstemp(prefix=".tests-mesures-", suffix=".tmp", dir=str(chemin.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(b"".join(l + b"\n" for l in lignes[-LIGNES_APRES_ROTATION:]))
            f.flush()
            os.fsync(f.fileno())
        _exiger_dossier_sur(chemin.parent)
        _exiger_fichier_ordinaire(chemin, unique=True)
        remplacer(temporaire, chemin)
    except BaseException:
        try:
            os.unlink(temporaire)
        except OSError:
            pass
        raise


def _valide(d):
    return (isinstance(d, dict) and d.get("lieu") in LIEUX and d.get("source") in SOURCES
            and d.get("portee") in PORTEES and _nombre(d.get("duree_s")))


def _analyser(brut):
    sortie = []
    for b in brut.split(b"\n"):
        if len(b) > MAX_OCTETS_LIGNE:
            continue
        try:
            texte = b.decode("utf-8").lstrip("﻿").strip()
            if not texte:
                continue
            d = json.loads(texte, parse_constant=_refuser_constante)
        except (ValueError, RecursionError):
            continue
        if _valide(d):
            sortie.append(d)
    return sortie


def lire(chemin: Path) -> List[dict]:
    """Les lignes valides du journal, dans l'ordre (JSON objet de 2 Ko au plus, `lieu`, `source` et `portee` connus,
    `duree_s` nombre positif ou nul) ; absent ou illisible : `[]`. Ne lève jamais."""
    try:
        return _analyser(_lire_fin(chemin)[0])
    except Exception:  # noqa: BLE001 — absent, dossier, lien, droits : rien à lire
        return []


def _dernieres(chemin, n):
    """Les `n` dernières lignes valides, en ne lisant que la fin du journal (`n` × 2 Ko au plus). Ne lève jamais."""
    try:
        return _analyser(_lire_fin(chemin, maxi=n * MAX_OCTETS_LIGNE)[0])[-n:]
    except Exception:  # noqa: BLE001
        return []


def max_n(chemin: Path) -> int:
    """Le plus grand numéro de campagne `n` des lignes `source: "mesure"` du journal (0 s'il n'y en a pas). Les règles
    d'alerte comparent ce numéro aux compteurs du sceau (`max n` < `campagnes` : des mesures ont disparu) au lieu de
    compter des lignes, que la rotation enlève. Ne lève jamais."""
    return max([l["n"] for l in lire(chemin)
                if l.get("source") == "mesure" and type(l.get("n")) is int and l["n"] >= 0] or [0])


# ---------------------------------------------------------------------------------------------------- la sortie


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_UNITTEST = re.compile(r"^Ran (\d+) tests? in ")
_VITEST = re.compile(r"^Tests\s+.*\b(?:passed|failed|skipped|todo)\b.*\((\d+)\)$")
_JEST = re.compile(r"^Tests:\s+.*?\b(\d+) total\b")
_PYTEST_FIN = re.compile(r"\bin \d+(?:\.\d+)?s\b")
_PYTEST_COMPTE = re.compile(r"\b(\d+) (?:passed|failed|errors?|skipped)\b")
LIGNES_LUES = 30
LONGUEUR_LUE = 400


def nb_tests_de(fin: str) -> Optional[int]:
    """Le nombre de tests d'après les dernières lignes d'une sortie : unittest `Ran N tests` ; pytest (somme des
    `passed`, `failed`, `error(s)`, `skipped` de la dernière ligne de résumé) ; vitest `Tests  N passed (T)` → T ; jest
    `Tests: … T total` → T. Format non reconnu : `None` (jamais une erreur)."""
    try:
        lignes = _ANSI.sub("", fin[-8192:]).splitlines()[-LIGNES_LUES:]
        for l in reversed(lignes):
            l = l.strip().strip("=").strip()
            if len(l) > LONGUEUR_LUE:
                continue                  # une ligne de résumé est courte ; borne le coût des motifs
            for motif in (_UNITTEST, _VITEST, _JEST):
                m = motif.match(l)
                if m:
                    return int(m.group(1))
            if _PYTEST_FIN.search(l):
                comptes = _PYTEST_COMPTE.findall(l)
                if comptes:
                    return sum(int(c) for c in comptes)
    except Exception:  # noqa: BLE001 — un format inattendu donne `None`
        return None
    return None


def meme_commande(a: str, b: Optional[str]) -> bool:
    """Vrai si `a` est la commande enregistrée `b`, aux blancs près ; `b` nul ou vide : faux (rien n'est complet)."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    b = " ".join(b.split())
    return bool(b) and " ".join(a.split()) == b


# ---------------------------------------------------------------------------------------------------- noter




class _DejaNote(Exception):
    """Cette exécution GitHub est déjà au journal : rien à écrire, ni au sceau."""


def _cle_run(run):
    """La forme comparable d'un identifiant d'exécution : celle que garde le journal (texte de 40 caractères au plus),
    pour qu'un `run` long soit reconnu malgré la troncature."""
    return _texte(str(run), MAX_RUN)


def noter_campagne(dossier, *, commande: str, duree_s, attente_s, code, fin="", octets=None, lieu="poste", tache=None,
                   run=None, bureau=BUREAU, sceau=SCEAU, maintenant=_maintenant) -> Optional[dict]:
    """Note une campagne mesurée par le lanceur : la ligne du journal du projet enregistré qui contient `dossier`, et
    au sceau, sous son verrou (attente courte, `tests_sceau.ATTENTE_LANCEUR_S`), `campagnes += 1`,
    `cumul_s += duree_s`, `n = campagnes`. La portée vient de la commande enregistrée (`complete` si c'est elle, aux
    blancs près). Une campagne complète verte avec un nombre de tests met `derniers_nb_tests` à jour, sauf baisse de
    plus de 2 % (l'alerte tient jusqu'à « C'est voulu »). La ligne est écrite SOUS le verrou du sceau, avant lui :
    compteurs et journal avancent ensemble, et un journal qu'on ne peut pas écrire ne compte rien. Une exécution GitHub
    (`run`) déjà présente dans les 50 dernières lignes n'est pas notée deux fois. Rend la ligne ; projet non enregistré,
    `run` déjà noté ou toute erreur : `None` (la mesure ne casse jamais une campagne)."""
    try:
        trouve = projet_enregistre(dossier, bureau)
        if trouve is None:
            return None
        id_, racine = trouve
        journal = journal_de(racine)
        nb = nb_tests_de(fin) if isinstance(fin, str) and fin else None
        note = {}

        def changer(entree):
            if run is not None:
                cle = _cle_run(run)
                if any("run" in l and _cle_run(l["run"]) == cle for l in _dernieres(journal, RUN_RECENTS)):
                    raise _DejaNote()
            portee = "complete" if meme_commande(commande, entree["commande_complete"]) else "partielle"
            l = ligne(lieu=lieu, source="mesure", tache=tache, commande=commande, portee=portee, duree_s=duree_s,
                      attente_s=attente_s, code=code, nb_tests=nb, sortie_octets=octets,
                      n=entree["campagnes"] + 1, run=run, t=maintenant())
            entree["campagnes"] += 1
            entree["cumul_s"] = round(entree["cumul_s"] + l["duree_s"], 1)
            if portee == "complete" and code == 0 and nb is not None:
                ancien = entree["derniers_nb_tests"]
                if ancien is None or nb >= ancien * (1 - SEUIL_BAISSE):
                    entree["derniers_nb_tests"] = nb
            ajouter(journal, l)
            note["ligne"] = l

        tests_sceau.modifier(id_, changer, sceau=sceau, maintenant=maintenant,
                             attente_s=tests_sceau.ATTENTE_LANCEUR_S)
        return note.get("ligne")
    except Exception:  # noqa: BLE001 — OSError, ValueError, TimeoutError, SceauIllisible, _DejaNote… : tues
        return None


def noter_declarations(dossier, lieu, tache, declarations: list, bureau=BUREAU, sceau=SCEAU,
                       maintenant=_maintenant) -> int:
    """Une ligne `source: "declare"` par déclaration valide d'un agent du cloud ou du serveur (`{"commande", "portee":
    "touches" | "complete", "duree_s", "code"}` ; `touches` devient `partielle`), 20 au plus. Le sceau n'est pas
    modifié, mais son verrou est pris (attente courte) : les campagnes du poste écrivent le journal sous ce même verrou,
    et une rotation ne peut pas perdre une déclaration. Verrou indisponible : rien n'est écrit. Rend le nombre de lignes
    écrites ; ne lève jamais."""
    ecrites = 0
    try:
        if lieu not in LIEUX or not isinstance(declarations, list):
            return 0
        trouve = projet_enregistre(dossier, bureau)
        if trouve is None:
            return 0
        journal = journal_de(trouve[1])
        lignes = []
        for d in declarations[:MAX_DECLARATIONS]:
            if not isinstance(d, dict) or not isinstance(d.get("portee"), str):
                continue
            portee = _PORTEE_AGENT.get(d["portee"])
            if portee is None:
                continue
            try:
                lignes.append(ligne(lieu=lieu, source="declare", tache=tache, commande=d.get("commande"),
                                    portee=portee, duree_s=d.get("duree_s"), attente_s=0.0, code=d.get("code"),
                                    t=maintenant()))
            except ValueError:
                continue
        if not lignes:
            return 0
        Path(os.path.abspath(str(sceau))).parent.mkdir(parents=True, exist_ok=True)
        with verrou_fichier(sceau, attente_s=tests_sceau.ATTENTE_LANCEUR_S):
            for l in lignes:
                ajouter(journal, l)
                ecrites += 1
    except Exception:  # noqa: BLE001 — une déclaration ne casse jamais le moteur
        return ecrites
    return ecrites
