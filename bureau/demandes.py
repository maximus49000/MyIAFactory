"""Les demandes : ce que la page demande au projet. Le bureau ne fait que les vérifier et les remettre."""
import json
import subprocess
from datetime import datetime
from pathlib import Path

from . import releve

MAX_RETOUR = 3500
CHAMPS = {"bouton": ("id",), "deplacer": ("tache", "colonne"),
          "retour": ("tache", "texte"), "lecon": ("id", "verdict")}


def nettoyer(demande):
    """La demande réduite à ses champs connus (rien d'autre n'est transmis au projet)."""
    if not isinstance(demande, dict) or demande.get("type") not in CHAMPS:
        return demande
    return {k: demande[k] for k in ("type",) + CHAMPS[demande["type"]] if k in demande}


def commande_declaree(regl):
    """Vrai si les réglages déclarent une commande d'actions utilisable."""
    actions = regl.get("actions")
    cmd = actions.get("commande") if isinstance(actions, dict) else None
    return isinstance(cmd, list) and bool(cmd) and all(isinstance(c, str) for c in cmd)


def _ids_taches(r):
    ids = {t["id"] for t in r.get("taches", [])}
    ids.update(q["id"] for q in r.get("file", {}).get("visibles", []))
    return ids


def verifier(demande, r):
    """Message d'erreur (français) ou None. `r` : le dernier relevé normalisé valide."""
    if not isinstance(demande, dict):
        return "La demande doit être un objet."
    genre = demande.get("type")
    if genre not in CHAMPS:
        return "Type de demande inconnu."
    for champ in CHAMPS[genre]:
        if not isinstance(demande.get(champ), str):
            return f"« {champ} » est obligatoire (texte)."
    if genre == "bouton":
        a = next((a for a in r.get("actions", []) if a["id"] == demande["id"]), None)
        if a is None:
            return "Bouton inconnu."
        if a.get("lien") is not None or a.get("actif") is False:
            return "Ce bouton n'envoie pas de demande."
    elif genre == "deplacer":
        if demande["tache"] not in _ids_taches(r):
            return "Tâche inconnue."
        if demande["colonne"] not in {c["id"] for c in r.get("colonnes", [])}:
            return "Colonne inconnue."
    elif genre == "retour":
        if demande["tache"] not in {t["id"] for t in r.get("taches", [])}:
            return "Tâche inconnue."
        texte = demande["texte"].strip()
        if not texte:
            return "Le retour est vide."
        if len(demande["texte"]) > MAX_RETOUR:
            return f"Le retour dépasse {MAX_RETOUR} caractères."
    else:
        if demande["id"] not in {le["id"] for le in r.get("lecons", [])}:
            return "Leçon inconnue."
        if demande["verdict"] not in ("valider", "invalider"):
            return "Verdict inconnu (valider ou invalider)."
    return None


def envoyer(regl, demande):
    """(True, "") si la commande d'actions a pris la demande, sinon (False, message)."""
    if not commande_declaree(regl):
        return False, "Aucune commande d'actions dans les réglages."
    actions = regl["actions"]
    cmd = actions["commande"]
    cwd = Path(regl.get("dossier") or ".") / str(actions.get("dossier", "."))
    corps = json.dumps({**demande, "t": datetime.now().astimezone().isoformat(timespec="seconds")},
                       ensure_ascii=False).encode("utf-8")
    try:
        code, sortie, erreurs = releve._executer(cmd, str(cwd), corps)
    except subprocess.TimeoutExpired:
        return False, f"La commande d'actions a dépassé {releve.DELAI_COMMANDE_S} s."
    except OSError as e:
        return False, f"La commande d'actions n'a pas pu démarrer : {e}"[:200]
    if code == 0:
        return True, ""
    for flux in (sortie, erreurs):
        ligne = flux.decode("utf-8", "replace").strip().splitlines()
        if ligne and ligne[0].strip():
            return False, ligne[0].strip()[:200]
    return False, f"La commande d'actions a échoué (code {code})."
