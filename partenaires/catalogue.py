"""Le catalogue des partenaires (ce qui existe) : lecture, contrôle, tri par catégorie.

Le catalogue est générique et universel : il vit dans le dépôt de la skill, sans rien de propre à un projet.
Les partenaires sont facultatifs. Une URL qui n'a pas été relevée sur le site du partenaire reste `null`.
"""
import datetime
import json
import re
from pathlib import Path

from orchestrateur.factory import MOTIF_ID

CATEGORIES = ("voix-audio", "images", "video-3d-avatars", "langue-web-agents", "medias-design", "mise-en-ligne-equipe")
TARIFS = ("gratuit", "inclus", "usage", "inconnu")
STATUTS = ("actif", "ferme", "sans_api", "restreint")
CONNEXIONS = ("mcp", "api", "studio", "compte")
PERIODES = ("mois", "an", "usage", "jour", "heure", "minute", None)
FIABILITES = ("officielle", "tiers")
MOTIF_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}\Z")
CHEMIN = Path(__file__).resolve().parent / "catalogue.json"


def lire(chemin=None):
    """Le catalogue (le fichier du paquet par défaut)."""
    return json.loads(Path(chemin or CHEMIN).read_text(encoding="utf-8"))


def _url_ok(u):
    return u is None or (isinstance(u, str) and u.startswith("https://") and " " not in u and len(u) > 8)


def _date_ok(s):
    try:
        datetime.date.fromisoformat(s)
        return isinstance(s, str) and len(s) == 10
    except (TypeError, ValueError):
        return False


def verifier(d):
    """Les erreurs du catalogue `d` (liste vide s'il est valide)."""
    if not isinstance(d, dict) or d.get("version") != 1 or not isinstance(d.get("partenaires"), list):
        return ["le catalogue doit être {\"version\": 1, \"partenaires\": [...]}"]
    erreurs, vus = [], set()
    for p in d["partenaires"]:
        i = p.get("id") if isinstance(p, dict) else None
        if not (isinstance(i, str) and MOTIF_ID.match(i)):
            erreurs.append(f"identifiant invalide : {i!r}")
            continue
        if i in vus:
            erreurs.append(f"{i} : identifiant en double")
        vus.add(i)

        def e(msg, i=i):
            erreurs.append(f"{i} : {msg}")
        if not (isinstance(p.get("nom"), str) and p["nom"].strip()):
            e("nom manquant")
        if p.get("categorie") not in CATEGORIES:
            e(f"catégorie inconnue ({p.get('categorie')!r})")
        if not (isinstance(p.get("sous_categorie"), str) and p["sous_categorie"]):
            e("sous-catégorie manquante")
        for champ in ("site", "inscription"):
            if not _url_ok(p.get(champ)):
                e(f"{champ} doit être une URL en https:// ou null")
        if p.get("statut") not in STATUTS:
            e(f"statut inconnu ({p.get('statut')!r})")
        if p.get("fiabilite") not in FIABILITES:
            e("fiabilité inconnue")
        if not _date_ok(p.get("verifie_le")):
            e("date de vérification invalide (AAAA-MM-JJ)")
        if p.get("quota_lisible") not in ("oui", "non", "inconnu"):
            e("quota_lisible doit valoir oui, non ou inconnu")
        if p.get("lecteur") is not None and p.get("quota_lisible") != "oui":
            e("lecteur seulement si quota_lisible vaut oui")
        if not isinstance(p.get("illimite"), bool):
            e("illimite doit être un booléen")
        if p.get("gratuit") is not None and not isinstance(p["gratuit"], str):
            e("gratuit doit être un texte ou null")
        if not isinstance(p.get("connexions"), list):
            e("connexions doit être une liste")
        for c in p.get("connexions") or []:
            if not isinstance(c, dict) or c.get("type") not in CONNEXIONS:
                e("connexion de type inconnu")
                continue
            if not _url_ok(c.get("url")):
                e("l'URL d'une connexion doit être en https:// ou null")
            if c.get("commande") is not None and not isinstance(c["commande"], str):
                e("commande doit être un texte ou null")
            v = c.get("variables", [])
            if not (isinstance(v, list) and all(isinstance(x, str) and MOTIF_VARIABLE.match(x) for x in v)):
                e("variables : des noms de variables d'environnement")
        if not isinstance(p.get("plans"), list):
            e("plans doit être une liste")
        for pl in p.get("plans") or []:
            if not (isinstance(pl, dict) and isinstance(pl.get("nom"), str)):
                e("plan sans nom")
                continue
            if pl.get("tarif") not in TARIFS:
                e(f"tarif inconnu ({pl.get('tarif')!r})")
            if pl.get("prix") is not None and (isinstance(pl["prix"], bool) or not isinstance(pl["prix"], (int, float)) or pl["prix"] < 0):
                e("prix : un nombre positif ou null")
            if pl.get("periode") not in PERIODES:
                e(f"période inconnue ({pl.get('periode')!r})")
    return erreurs


def par_categorie(d):
    """Les partenaires de chaque catégorie, les actifs d'abord (l'ordre du catalogue ensuite)."""
    sortie = {c: [] for c in CATEGORIES}
    for p in d["partenaires"]:
        if p.get("categorie") in sortie:
            sortie[p["categorie"]].append(p)
    for c in sortie:
        sortie[c].sort(key=lambda p: p.get("statut") != "actif")  # tri stable
    return sortie
