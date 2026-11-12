"""Les fiches d'agents : un fichier texte par agent, en-tête `Clé : valeur`, texte libre, puis `## Leçons`.

    Clé : dev-1
    Prénom : Léa
    Rôle : dev
    Service : dev
    Modèle : Sonnet
    Lieu : local
    Session : (cloud seulement)
    Spécialité : écrans et mise en page
    Outils : Read, Write, Edit, Bash(py:*)   (facultatif : les outils d'un agent lancé par le moteur)
    Fable : accordé par le Directeur le 2026-11-12   (facultatif : la seule façon d'avoir `Modèle : Fable`)

    Texte libre…

    ## Leçons
    - [à valider] dev-1:L1 : Relancer les tests après chaque changement.
    - [validée] dev-1:L0 : Nommer les écrans comme dans la maquette.
"""
import os
import re
import tempfile
from pathlib import Path

ENTETES = ("Clé", "Prénom", "Rôle", "Service", "Modèle", "Lieu", "Session", "Spécialité", "Outils", "Fable")
# Les outils d'un agent lancé sans fenêtre quand sa fiche n'en déclare pas : lire, écrire et modifier dans le dossier
# du projet, lancer Python (`py`, mais aussi `python`, que les agents emploient d'eux-mêmes : refusé, il bloquait toute
# production à l'essai de la phase D), créer un dossier, `git`. Jamais le mode qui contourne les autorisations.
OUTILS_PAR_DEFAUT = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(py:*)", "Bash(python:*)", "Bash(python3:*)",
                     "Bash(mkdir:*)", "Bash(git:*)"]
MODELES = ("Haiku", "Sonnet", "Opus")
# Fable n'est jamais choisi par le moteur ni par un outil : une fiche l'a seulement si le Directeur l'a accordé, pour
# cet agent seulement, et la fiche le dit (ligne `Fable :`).
ACCORD_FABLE = re.compile(r"^accordé par le Directeur le \d{4}-\d{2}-\d{2}\Z")
ETATS = ("à valider", "validée")
_ENTETE = re.compile(r"^(Clé|Prénom|Rôle|Service|Modèle|Lieu|Session|Spécialité|Outils|Fable)\s*:\s*(.*?)\s*$")
_LECON = re.compile(r"^-\s*\[(à valider|validée)\]\s*(\S+)\s*:\s*(.*)$")


class FicheInvalide(Exception):
    pass


def lire_fiche(chemin):
    """Une fiche : {cle, prenom, role, service, modele, lieu, session, specialite, texte, lecons, chemin}."""
    chemin = Path(chemin)
    lignes = chemin.read_text(encoding="utf-8-sig").splitlines()
    champs, i = {}, 0
    while i < len(lignes):
        m = _ENTETE.match(lignes[i])
        if not m:
            if lignes[i].strip() == "" and champs:
                break
            if lignes[i].strip() == "":
                i += 1
                continue
            break
        champs[m.group(1)] = m.group(2)
        i += 1
    corps, lecons, dans_lecons = [], [], False
    for ligne in lignes[i:]:
        if ligne.strip() == "## Leçons":
            dans_lecons = True
            continue
        if dans_lecons:
            m = _LECON.match(ligne.strip())
            if m:
                lecons.append({"etat": m.group(1), "id": m.group(2), "texte": m.group(3)})
        else:
            corps.append(ligne)
    for c in ("Clé", "Rôle", "Modèle", "Lieu"):
        if not champs.get(c):
            raise FicheInvalide(f"Fiche {chemin.name} : « {c} » est obligatoire.")
    accord = champs.get("Fable") or None
    if accord is not None and not ACCORD_FABLE.match(accord):
        raise FicheInvalide(f"Fiche {chemin.name} : « Fable » doit dire « accordé par le Directeur le AAAA-MM-JJ ».")
    if champs["Modèle"] not in MODELES and not (champs["Modèle"] == "Fable" and accord):
        raise FicheInvalide(f"Fiche {chemin.name} : « Modèle » doit valoir Haiku, Sonnet ou Opus (Fable seulement "
                            "avec l'accord du Directeur, ligne « Fable : »).")
    if champs["Lieu"] not in ("local", "cloud"):
        raise FicheInvalide(f"Fiche {chemin.name} : « Lieu » doit valoir local ou cloud.")
    return {"cle": champs["Clé"], "prenom": champs.get("Prénom") or None, "role": champs["Rôle"],
            "service": champs.get("Service") or None, "modele": champs["Modèle"], "lieu": champs["Lieu"],
            "session": champs.get("Session") or None, "specialite": champs.get("Spécialité") or None,
            "outils": champs.get("Outils") or None, "fable": accord,
            "texte": "\n".join(corps).strip(), "lecons": lecons, "chemin": chemin}


def lire_toutes(dossier):
    """Les fiches du dossier (`*.md`, par nom de fichier), sans les sous-dossiers (briefs) ni les modèles."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        return []
    fiches, vues = [], set()
    for chemin in sorted(dossier.glob("*.md")):
        f = lire_fiche(chemin)
        if f["cle"] in vues:
            raise FicheInvalide(f"Fiches : clé en double « {f['cle']} ».")
        vues.add(f["cle"])
        fiches.append(f)
    return fiches


def ecrire_fiche(f):
    """Réécrit la fiche (le texte libre et les leçons sont gardés)."""
    lignes = [f"Clé : {f['cle']}"]
    for nom, cle in (("Prénom", "prenom"), ("Rôle", "role"), ("Service", "service"), ("Modèle", "modele"),
                     ("Lieu", "lieu"), ("Session", "session"), ("Spécialité", "specialite"), ("Outils", "outils"),
                     ("Fable", "fable")):
        if f.get(cle):
            lignes.append(f"{nom} : {f[cle]}")
    lignes += ["", f["texte"], "", "## Leçons"] if f["texte"] else ["", "## Leçons"]
    lignes += [f"- [{le['etat']}] {le['id']} : {le['texte']}" for le in f["lecons"]]
    chemin = Path(f["chemin"])
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as sortie:
            sortie.write("\n".join(lignes) + "\n")
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def fable_accorde(fiche):
    """Vrai si la fiche est sur Fable ET porte l'accord du Directeur (ligne `Fable : accordé par le Directeur le …`).
    Le moteur ne lance Fable que pour une telle fiche, pour cet agent seulement ; jamais pour un jugement."""
    return (isinstance(fiche, dict) and str(fiche.get("modele") or "").strip().lower() == "fable"
            and isinstance(fiche.get("fable"), str) and bool(ACCORD_FABLE.match(fiche["fable"])))


def accorder_fable(agents, cles, jour):
    """Les agents (copies) dont la clé est dans `cles` passent sur Fable avec l'accord du Directeur daté de `jour`
    (`AAAA-MM-JJ`). `ValueError` pour une clé dont l'agent n'a pas de `fable_suggere` vrai (ou qui n'existe pas)."""
    suggerees = {a["cle"] for a in agents if a.get("fable_suggere") is True}
    hors = [c for c in cles if c not in suggerees]
    if hors:
        raise ValueError("Fable n'a pas été suggéré pour : " + ", ".join(hors) + ".")
    accord = f"accordé par le Directeur le {jour}"
    return [dict(a, modele="Fable", fable=accord) if a["cle"] in cles else dict(a) for a in agents]


def outils(fiche):
    """Les outils de l'agent : la ligne `Outils :` de sa fiche (séparée par des virgules, hors parenthèses : une règle
    comme `Bash(py:*)` reste entière), sinon `OUTILS_PAR_DEFAUT`."""
    brut = (fiche.get("outils") or "").strip()
    if not brut:
        return list(OUTILS_PAR_DEFAUT)
    liste, courant, profondeur = [], "", 0
    for c in brut:
        profondeur += (c == "(") - (c == ")")
        if c == "," and profondeur <= 0:
            liste.append(courant.strip())
            courant = ""
        else:
            courant += c
    liste.append(courant.strip())
    return [o for o in liste if o] or list(OUTILS_PAR_DEFAUT)


def trouver(fiches, cle):
    return next((f for f in fiches if f["cle"] == cle), None)
