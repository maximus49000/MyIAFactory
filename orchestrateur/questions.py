"""Les questions sur le projet : ce que l'utilisateur demande au bouton « ? Une question », et les réponses de la
factory (d'après les documents, puis d'après le code).

Un fichier du projet, à côté du fichier de factory (`.factory/questions.jsonl`), un fil par ligne :
`{id, ouverte, fonctionnalite, etat (en_cours | repondue | en_lecture), messages: [{auteur (utilisateur | factory),
texte, t, images?, niveau? (documents | code), sur?, suggestion?, fichiers_lus?}]}`. Il n'est écrit que par
`lancer questions` ; le relevé le publie (`questions`). Une ligne illisible est ignorée.
"""
import json
import os
import re
from pathlib import Path

from orchestrateur import suivi as su

FICHIER = "questions.jsonl"
ETATS = ("en_cours", "repondue", "en_lecture")
AUTEURS = ("utilisateur", "factory")
NIVEAUX = ("documents", "code")
TEXTE_MAX = 6000
MAX_QUESTIONS = 200
MAX_MESSAGES = 40            # un fil trop long : les plus anciens messages partent, la question d'origine reste


def chemin(f):
    return Path(f["chemin"]).parent / FICHIER


def _valide(x):
    return (isinstance(x, dict) and isinstance(x.get("id"), str) and re.fullmatch(r"q[0-9]+", x["id"])
            and x.get("etat") in ETATS and isinstance(x.get("messages"), list) and x["messages"]
            and all(isinstance(m, dict) and m.get("auteur") in AUTEURS and isinstance(m.get("texte"), str)
                    for m in x["messages"]))


def lire(f):
    """Les fils, du plus ancien au plus récent (liste vide sans fichier)."""
    try:
        lignes = chemin(f).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    rendu = []
    for ligne in lignes:
        try:
            x = json.loads(ligne)
        except ValueError:
            continue
        if _valide(x):
            rendu.append(x)
    return rendu


def fil(f, ident):
    return next((x for x in lire(f) if x["id"] == ident), None)


def _ecrire(f, fils):
    c = chemin(f)
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_name(c.name + ".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fils), encoding="utf-8")
    os.replace(tmp, c)


def _texte(e):
    v = e.get("texte")
    if not isinstance(v, str) or not v.strip():
        raise ValueError("« texte » est obligatoire.")
    v = v.strip()
    if len(v) > TEXTE_MAX:
        raise ValueError(f"« texte » tient en {TEXTE_MAX} caractères au plus.")
    return v


def _message(e):
    auteur = e.get("auteur", "utilisateur")
    if auteur not in AUTEURS:
        raise ValueError("« auteur » vaut utilisateur ou factory.")
    m = {"auteur": auteur, "texte": _texte(e), "t": su.maintenant()}
    if e.get("images"):
        m["images"] = [str(x) for x in e["images"]][:4]
    if auteur == "factory":
        if e.get("niveau") not in NIVEAUX:
            raise ValueError("« niveau » vaut documents ou code.")
        m["niveau"], m["sur"] = e["niveau"], bool(e.get("sur"))
        m["suggestion"] = e.get("suggestion") if isinstance(e.get("suggestion"), dict) else None
        if isinstance(e.get("fichiers_lus"), list):
            m["fichiers_lus"] = [str(x)[:200] for x in e["fichiers_lus"]][:20]
    return m


def ouvrir(f, e):
    """Un fil nouveau : `texte`, et facultatifs `images`, `fonctionnalite`. Rend le fil."""
    fils = lire(f)
    numero = max([int(x["id"][1:]) for x in fils] or [0]) + 1
    fonc = e.get("fonctionnalite") if isinstance(e.get("fonctionnalite"), str) else None
    x = {"id": f"q{numero}", "ouverte": su.maintenant(), "fonctionnalite": fonc, "etat": "en_cours",
         "messages": [_message({**e, "auteur": "utilisateur"})]}
    fils.append(x)
    del fils[:max(0, len(fils) - MAX_QUESTIONS)]
    _ecrire(f, fils)
    return x


def ajouter(f, ident, e):
    """Un message de plus dans le fil `ident` ; un message de l'utilisateur rouvre le fil (`en_cours`)."""
    fils = lire(f)
    x = next((q for q in fils if q["id"] == ident), None)
    if x is None:
        raise ValueError(f"Question inconnue : {ident}")
    m = _message(e)
    x["messages"].append(m)
    if len(x["messages"]) > MAX_MESSAGES:
        x["messages"] = x["messages"][:1] + x["messages"][-(MAX_MESSAGES - 1):]
    if m["auteur"] == "utilisateur":
        x["etat"] = "en_cours"
    _ecrire(f, fils)
    return x


def marquer(f, ident, etat):
    if etat not in ETATS:
        raise ValueError("« etat » vaut en_cours, repondue ou en_lecture.")
    fils = lire(f)
    x = next((q for q in fils if q["id"] == ident), None)
    if x is None:
        raise ValueError(f"Question inconnue : {ident}")
    x["etat"] = etat
    _ecrire(f, fils)
    return x
