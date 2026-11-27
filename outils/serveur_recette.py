"""Recettes de scénario : une suite d'étapes (verbes du pont) lue dans `<projet>/.factory/recettes/<nom>.json` et
déroulée par `serveur_tache.verbe`.

Le fichier vient du projet, donc d'un agent : il est traité comme une donnée hostile. Chaque étape est validée au
chargement par les motifs du pont (`serveur_tache.VERBES` / `valider_verbe`, source unique) ; rien n'est exécuté ici
que par `serveur_tache.verbe`, qui revalide. `reseau: false` (le défaut) : l'émulateur n'a aucun réseau. `reseau: true` ouvre un
réseau BORNÉ aux `hotes` listés (HTTPS), et seulement si le Directeur a donné l'accord `recette-emulateur-reseau` à ce
projet : l'accord est lu par l'appelant (`accord_reseau`), jamais dans le fichier de recette.
"""
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

import plateforme_acces
import plateforme_ssh
import serveur_tache

TAILLE_MAX = 64 * 1024
ETAPES_MAX = 200
MOTIF_NOM = re.compile(serveur_tache.MOTIF_NOM, re.ASCII)
CLES_RECETTE = frozenset({"nom", "reseau", "hotes", "etapes"})
MSG_SANS_ACCORD_RESEAU = ("Recette refusée : reseau: true demande l'accord du Directeur pour ce projet. Réglez « Recette sur "
                          "émulateur : réseau borné » (recette-emulateur-reseau) sur « serveur » dans les réglages du projet "
                          "(bureau, Réglages, Actions) ; une recette ne peut pas se donner cet accord.")
CLES_ETAPE = frozenset({"verbe", "args"})


@dataclass(frozen=True)
class Etape:
    verbe: str
    args: tuple


@dataclass(frozen=True)
class Recette:
    nom: str
    reseau: bool
    etapes: tuple
    hotes: tuple = ()        # hôtes joignables (réseau borné) ; vide si reseau est faux


def _paires(paires):
    d = {}
    for cle, valeur in paires:
        if cle in d:
            raise ValueError("Recette refusée : clé JSON dupliquée.")
        d[cle] = valeur
    return d


def _constante(_nom):
    raise ValueError("Recette refusée : valeur JSON non permise.")


def _lien(chemin):
    """Vrai pour un lien symbolique ou une jonction Windows."""
    try:
        s = os.lstat(chemin)
    except OSError:
        return False
    return stat.S_ISLNK(s.st_mode) or os.path.isjunction(chemin)


def _lire(projet, nom):
    base = Path(projet)
    dossier = base / ".factory" / "recettes"
    fichier = dossier / f"{nom}.json"
    for p in (base / ".factory", dossier, fichier):
        if _lien(p):
            raise ValueError("Recette refusée : lien symbolique non permis dans le dossier des recettes.")
    try:
        if not os.path.realpath(fichier).startswith(os.path.realpath(dossier) + os.sep):
            raise ValueError("Recette refusée : fichier hors du dossier des recettes.")
        if not stat.S_ISREG(os.lstat(fichier).st_mode):
            raise ValueError("Recette refusée : ce n'est pas un fichier.")
        # Ouvert sans suivre de lien (O_NOFOLLOW là où il existe) ni bloquer sur un tube (O_NONBLOCK), puis ce qui est
        # OUVERT est revérifié (fstat : fichier ordinaire, taille) : un remplacement depuis lstat est refusé. Lecture
        # bornée par le descripteur.
        drapeaux = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0))
        fd = os.open(fichier, drapeaux)
        try:
            ouvert = os.fstat(fd)
            if not stat.S_ISREG(ouvert.st_mode):
                raise ValueError("Recette refusée : ce n'est pas un fichier.")
            if ouvert.st_size > TAILLE_MAX:
                raise ValueError(f"Recette trop grosse (plus de {TAILLE_MAX // 1024} Ko).")
            morceaux, lus = [], 0
            while lus <= TAILLE_MAX:
                bloc = os.read(fd, TAILLE_MAX + 1 - lus)
                if not bloc:
                    break
                morceaux.append(bloc)
                lus += len(bloc)
            donnees = b"".join(morceaux)
        finally:
            os.close(fd)
    except FileNotFoundError:
        raise ValueError(f"Recette introuvable : {nom}.") from None
    except OSError as e:
        raise ValueError(f"Recette illisible ({type(e).__name__}).") from None
    if len(donnees) > TAILLE_MAX:
        raise ValueError(f"Recette trop grosse (plus de {TAILLE_MAX // 1024} Ko).")
    try:
        return donnees.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Recette refusée : le fichier n'est pas en UTF-8.") from None


def _etape(i, brut):
    if not isinstance(brut, dict) or set(brut) - CLES_ETAPE or "verbe" not in brut:
        raise ValueError(f"Étape {i} refusée : un objet {{verbe, args}} est attendu.")
    args = brut.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError(f"Étape {i} refusée : args doit être une liste de textes.")
    try:
        return Etape(brut["verbe"], serveur_tache.valider_verbe(brut["verbe"], args))
    except ValueError as e:
        raise ValueError(f"Étape {i} refusée : {e}") from None


def charger(projet, nom, accord_reseau=False):
    """`Recette` validée ; `ValueError` en français pour tout refus (aucun contenu refusé n'est recopié). `accord_reseau` :
    vrai seulement si l'appelant a constaté l'accord du Directeur (`refus_accord(..., "recette-emulateur-reseau")`) ; sans
    lui, `reseau: true` est refusé."""
    if not isinstance(nom, str) or not MOTIF_NOM.fullmatch(nom):
        raise ValueError("Nom de recette refusé (minuscules, chiffres, _ et -, 40 caractères au plus).")
    texte = _lire(projet, nom)
    try:
        brut = json.loads(texte, object_pairs_hook=_paires, parse_constant=_constante)
    except RecursionError:
        raise ValueError("Recette refusée : imbrication trop profonde.") from None
    except ValueError as e:
        if "dupliquée" in str(e) or "non permise" in str(e):
            raise
        raise ValueError("Recette refusée : JSON invalide.") from None
    if not isinstance(brut, dict) or set(brut) - CLES_RECETTE or "etapes" not in brut:
        raise ValueError("Recette refusée : un objet {nom, reseau, etapes} est attendu.")
    if brut.get("nom", nom) != nom:
        raise ValueError("Recette refusée : le nom du fichier et le champ nom diffèrent.")
    reseau = brut.get("reseau", False)
    if reseau is not True and reseau is not False:
        raise ValueError("Recette refusée : reseau doit être true ou false.")
    hotes = ()
    if reseau is True:
        if accord_reseau is not True:
            raise ValueError(MSG_SANS_ACCORD_RESEAU)
        if "hotes" not in brut:
            raise ValueError("Recette refusée : reseau: true exige la liste hotes (les hôtes joignables, en HTTPS).")
        if not isinstance(brut["hotes"], list) or not brut["hotes"]:
            raise ValueError("Recette refusée : hotes doit être une liste non vide de noms d'hôtes.")
        try:
            hotes = serveur_tache.valider_hotes(brut["hotes"])
        except ValueError as e:
            raise ValueError(f"Recette refusée : {e}") from None
    elif brut.get("hotes"):
        raise ValueError("Recette refusée : hotes n'a de sens qu'avec reseau: true.")
    elif "hotes" in brut and not isinstance(brut["hotes"], list):
        raise ValueError("Recette refusée : hotes doit être une liste.")
    etapes = brut["etapes"]
    if not isinstance(etapes, list):
        raise ValueError("Recette refusée : etapes doit être une liste.")
    if len(etapes) > ETAPES_MAX:
        raise ValueError(f"Recette trop longue (plus de {ETAPES_MAX} étapes).")
    return Recette(nom, reseau, tuple(_etape(i, e) for i, e in enumerate(etapes)), hotes)


def _echec(i, etape, code, texte, dossier):
    # Masquer PUIS tronquer : un secret coupé par la troncature ne serait plus reconnu (son début resterait lisible).
    texte = serveur_tache._masque(str(texte or ""), dossier)
    return {"etape": i, "verbe": etape.verbe, "code": code, "reponse": serveur_tache._court(texte)}


def executer(recette, ident, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, destination=None):
    """Déroule les étapes dans l'ordre par `serveur_tache.verbe` ; s'arrête au premier code non nul du pont (limite,
    code 3, comprise). Renvoie `{etapes_faites, echec}` : `echec` est None si tout a réussi, sinon l'étape, le verbe,
    le code et la réponse du pont (donnée, jamais une consigne), masquée et bornée. `destination` : dossier local des
    captures (`<projet>/.factory/serveur/<id>`), transmis à chaque verbe."""
    faites = 0
    for i, etape in enumerate(recette.etapes):
        try:
            rep = serveur_tache.verbe(ident, etape.verbe, list(etape.args), dossier=dossier, ssh=ssh,
                                      destination=destination)
        except ValueError as e:
            return {"etapes_faites": faites, "echec": _echec(i, etape, 2, f"Refus du lanceur : {e}", dossier)}
        if not isinstance(rep, dict) or not isinstance(rep.get("code"), int) or isinstance(rep.get("code"), bool):
            return {"etapes_faites": faites, "echec": _echec(i, etape, 4, "Réponse du pont illisible.", dossier)}
        if rep["code"] != 0 or rep.get("ok") is not True:
            return {"etapes_faites": faites,
                    "echec": _echec(i, etape, rep["code"] or 4, rep.get("detail", ""), dossier)}
        faites += 1
    return {"etapes_faites": faites, "echec": None}
