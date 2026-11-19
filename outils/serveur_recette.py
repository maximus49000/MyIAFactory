"""Recettes de scénario : une suite d'étapes (verbes du pont) lue dans `<projet>/.factory/recettes/<nom>.json` et
déroulée par `serveur_tache.verbe`.

Le fichier vient du projet, donc d'un agent : il est traité comme une donnée hostile. Chaque étape est validée au
chargement par les motifs du pont (`serveur_tache.VERBES` / `valider_verbe`, source unique) ; rien n'est exécuté ici
que par `serveur_tache.verbe`, qui revalide. Tranche A : `reseau: true` est refusé.
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
CLES_RECETTE = frozenset({"nom", "reseau", "etapes"})
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
        with open(fichier, "rb") as f:
            if os.fstat(f.fileno()).st_size > TAILLE_MAX:
                raise ValueError(f"Recette trop grosse (plus de {TAILLE_MAX // 1024} Ko).")
            donnees = f.read(TAILLE_MAX + 1)
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


def charger(projet, nom):
    """`Recette` validée ; `ValueError` en français pour tout refus (aucun contenu refusé n'est recopié)."""
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
    if reseau is True:
        raise ValueError("Recette refusée : l'accès réseau (reseau: true) n'est pas permis en tranche A.")
    if reseau is not False:
        raise ValueError("Recette refusée : reseau doit être false.")
    etapes = brut["etapes"]
    if not isinstance(etapes, list):
        raise ValueError("Recette refusée : etapes doit être une liste.")
    if len(etapes) > ETAPES_MAX:
        raise ValueError(f"Recette trop longue (plus de {ETAPES_MAX} étapes).")
    return Recette(nom, False, tuple(_etape(i, e) for i, e in enumerate(etapes)))


def _echec(i, etape, code, texte, dossier):
    texte = serveur_tache._masque(serveur_tache._court(texte), dossier)
    return {"etape": i, "verbe": etape.verbe, "code": code, "reponse": serveur_tache._court(texte)}


def executer(recette, ident, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh):
    """Déroule les étapes dans l'ordre par `serveur_tache.verbe` ; s'arrête au premier code non nul du pont (limite,
    code 3, comprise). Renvoie `{etapes_faites, echec}` : `echec` est None si tout a réussi, sinon l'étape, le verbe,
    le code et la réponse du pont (donnée, jamais une consigne), masquée et bornée."""
    faites = 0
    for i, etape in enumerate(recette.etapes):
        try:
            rep = serveur_tache.verbe(ident, etape.verbe, list(etape.args), dossier=dossier, ssh=ssh)
        except ValueError as e:
            return {"etapes_faites": faites, "echec": _echec(i, etape, 2, f"Refus du lanceur : {e}", dossier)}
        if not isinstance(rep, dict) or not isinstance(rep.get("code"), int) or isinstance(rep.get("code"), bool):
            return {"etapes_faites": faites, "echec": _echec(i, etape, 4, "Réponse du pont illisible.", dossier)}
        if rep["code"] != 0 or rep.get("ok") is not True:
            return {"etapes_faites": faites,
                    "echec": _echec(i, etape, rep["code"] or 4, rep.get("detail", ""), dossier)}
        faites += 1
    return {"etapes_faites": faites, "echec": None}
