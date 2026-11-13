"""Les métiers : un brief `briefs/<role>.md` enrichi. Le métier est l'unité de spécialité d'un agent polyvalent : la
consigne, le service, le modèle par défaut, le lieu réservé, la spécialité, les outils et les leçons.

    Service : dev                 (facultatif)
    Modèle : Haiku|Sonnet|Opus    (facultatif ; jamais Fable)
    Lieu : local|cloud|indifférent (facultatif ; indifférent par défaut)
    Spécialité : écrans           (facultatif)
    Outils : Read, Bash(py:*)     (facultatif)

    Texte du brief…

    ## Leçons
    - [à valider|validée] <id> : texte

Un brief sans en-tête (l'ancien format) se lit : tous les champs facultatifs sont `None`, le lieu est « indifférent ».
"""
import os
import re
import tempfile
from pathlib import Path

MODELES = ("Haiku", "Sonnet", "Opus")
LIEUX = ("local", "cloud", "indifférent")
ETATS = ("à valider", "validée")
_ENTETE = re.compile(r"^(Service|Modèle|Lieu|Spécialité|Outils)\s*:\s*(.*?)\s*$")
_LECON = re.compile(r"^-\s*\[(à valider|validée)\]\s*(\S+)\s*:\s*(.*)$")


class MetierInvalide(Exception):
    pass


def _chemin(dossier_briefs, role):
    return Path(dossier_briefs) / f"{role}.md"


def lire_metier(dossier_briefs, role):
    """Le métier `role`, ou `None` si son brief n'existe pas. {role, service, modele, lieu, specialite, outils, texte,
    lecons, chemin}. `MetierInvalide` si l'en-tête est faux (modèle ou lieu inconnu, Fable)."""
    chemin = _chemin(dossier_briefs, role)
    if not chemin.is_file():
        return None
    lignes = chemin.read_text(encoding="utf-8-sig").splitlines()
    champs, i = {}, 0
    while i < len(lignes):
        m = _ENTETE.match(lignes[i])
        if m:
            champs[m.group(1)] = m.group(2)
        elif lignes[i].strip() == "" and not champs:
            pass
        else:
            break
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
    modele = champs.get("Modèle") or None
    if modele is not None and modele not in MODELES:
        raise MetierInvalide(f"Brief {chemin.name} : « Modèle » doit valoir Haiku, Sonnet ou Opus (jamais Fable : "
                             "l'accord du Directeur se donne par tâche).")
    lieu = champs.get("Lieu") or "indifférent"
    if lieu not in LIEUX:
        raise MetierInvalide(f"Brief {chemin.name} : « Lieu » doit valoir local, cloud ou indifférent.")
    return {"role": role, "service": champs.get("Service") or None, "modele": modele, "lieu": lieu,
            "specialite": champs.get("Spécialité") or None, "outils": champs.get("Outils") or None,
            "texte": "\n".join(corps).strip(), "lecons": lecons, "chemin": chemin}


def lire_tous(dossier_briefs):
    """{role: métier} pour chaque `*.md` du dossier des briefs (par nom de fichier) ; {} s'il n'existe pas."""
    dossier = Path(dossier_briefs)
    if not dossier.is_dir():
        return {}
    return {c.stem: lire_metier(dossier, c.stem) for c in sorted(dossier.glob("*.md"))}


def ecrire_metier(metier):
    """Réécrit le brief (en-tête, texte, leçons) de façon atomique."""
    if metier.get("modele") is not None and metier["modele"] not in MODELES:
        raise MetierInvalide("« Modèle » doit valoir Haiku, Sonnet ou Opus (jamais Fable dans un brief).")
    if metier.get("lieu", "indifférent") not in LIEUX:
        raise MetierInvalide("« Lieu » doit valoir local, cloud ou indifférent.")
    lignes = []
    for nom, cle in (("Service", "service"), ("Modèle", "modele"), ("Spécialité", "specialite"), ("Outils", "outils")):
        if metier.get(cle):
            lignes.append(f"{nom} : {metier[cle]}")
    if metier.get("lieu") and metier["lieu"] != "indifférent":
        lignes.append(f"Lieu : {metier['lieu']}")
    if lignes:
        lignes.append("")
    if metier.get("texte"):
        lignes += [metier["texte"], ""]
    lignes.append("## Leçons")
    lignes += [f"- [{le['etat']}] {le['id']} : {le['texte']}" for le in metier.get("lecons", [])]
    chemin = Path(metier["chemin"])
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as sortie:
            sortie.write("\n".join(lignes) + "\n")
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ajouter_lecon(metier, lecon):
    """Ajoute la leçon `{id, etat, texte}` au métier (sans l'écrire). Faux, sans rien changer, si une leçon de même
    texte y est déjà."""
    texte = lecon["texte"].strip()
    if any(le["texte"].strip() == texte for le in metier["lecons"]):
        return False
    metier["lecons"].append({"id": lecon["id"], "etat": lecon["etat"], "texte": texte})
    return True
