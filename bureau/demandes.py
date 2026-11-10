"""Les demandes : ce que la page demande au projet. Le bureau ne fait que les vérifier et les remettre."""
import json
import subprocess
from datetime import datetime
from pathlib import Path

from . import releve

MAX_RETOUR = 3500
MAX_TEXTE = MAX_RETOUR
CHAMPS = {"bouton": ("id",), "deplacer": ("tache", "colonne"),
          "retour": ("tache", "texte"), "lecon": ("id", "verdict"),
          "challenge": ("cible",), "solution": ("challenge", "texte"),
          "verdict_solution": ("challenge", "solution", "verdict")}
FACULTATIFS = {"challenge": ("texte", "solution")}
TYPES_CIBLE = ("kpi", "connaissance", "source")


def nettoyer(demande):
    """La demande réduite à ses champs connus (rien d'autre n'est transmis au projet)."""
    if not isinstance(demande, dict) or not isinstance(demande.get("type"), str) or demande["type"] not in CHAMPS:
        return demande
    genre = demande["type"]
    d = {k: demande[k] for k in ("type",) + CHAMPS[genre] + FACULTATIFS.get(genre, ()) if k in demande}
    if isinstance(d.get("cible"), dict):
        d["cible"] = {k: d["cible"][k] for k in ("type", "id") if k in d["cible"]}
    return d


def commande_declaree(regl):
    """Vrai si les réglages déclarent une commande d'actions utilisable."""
    actions = regl.get("actions")
    cmd = actions.get("commande") if isinstance(actions, dict) else None
    return isinstance(cmd, list) and bool(cmd) and all(isinstance(c, str) for c in cmd)


def _ids_taches(r):
    ids = {t["id"] for t in r.get("taches", [])}
    file = r.get("file", {})
    ids.update(q["id"] for q in file.get("visibles", []) + file.get("suite", []))
    return ids


def verifier(demande, r, cibles_calculees=frozenset()):
    """Message d'erreur (français) ou None. `r` : le dernier relevé normalisé valide.
    `cibles_calculees` : les identifiants des cibles que le bureau recalcule (KPI calculés, sources
    d'amélioration) ; un dict (id -> constat) convient aussi."""
    if not isinstance(demande, dict):
        return "La demande doit être un objet."
    genre = demande.get("type")
    if not isinstance(genre, str) or genre not in CHAMPS:
        return "Type de demande inconnu."
    if genre in ("challenge", "solution", "verdict_solution"):
        return _verifier_challenge(demande, r, cibles_calculees)
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


def _texte_libre(valeur, nom):
    """Message d'erreur pour un texte de l'utilisateur, ou None."""
    if not isinstance(valeur, str):
        return f"« {nom} » doit être un texte."
    if not valeur.strip():
        return f"« {nom} » est vide."
    if len(valeur) > MAX_TEXTE:
        return f"« {nom} » dépasse {MAX_TEXTE} caractères."
    return None


def connaissances_du_releve(r):
    """Les identifiants qu'une cible « connaissance » peut viser : connaissances et leçons validées."""
    ids = set()
    for ti in r.get("titulaires", []):
        ids.update(c["id"] for c in ti.get("connaissances") or [])
        ids.update(le["id"] for le in ti.get("lecons") or [] if le.get("etat") == "validée")
    return ids


def kpi_du_releve(r):
    """Les cibles « kpi » du projet : `kpi:<service>:<id>` (les id de KPI ne sont uniques que par service)."""
    return {f"kpi:{s['id']}:{k['id']}" for s in r.get("services", []) if isinstance(s.get("kpi"), list)
            for k in s["kpi"] if isinstance(k, dict) and isinstance(k.get("id"), str)}


def _verifier_challenge(demande, r, cibles_calculees):
    if r.get("version", 1) < 3:
        return "Le relevé de ce projet ne gère pas les challenges (version 3)."
    genre = demande["type"]
    challenges = {c["id"]: c for c in r.get("challenges") or []}
    if genre == "challenge":
        cible = demande.get("cible")
        if not isinstance(cible, dict) or not isinstance(cible.get("id"), str) or not cible["id"]:
            return "« cible » est obligatoire ({type, id})."
        if cible.get("type") not in TYPES_CIBLE:
            return "Type de cible inconnu (kpi, connaissance ou source)."
        for champ in ("texte", "solution"):
            if champ in demande:
                message = _texte_libre(demande[champ], champ)
                if message:
                    return message
        genre_cible, i = cible["type"], cible["id"]
        if genre_cible == "connaissance":
            connue = i in connaissances_du_releve(r)
        elif genre_cible == "kpi":
            connue = i in kpi_du_releve(r) or i in cibles_calculees
        else:
            connue = i in cibles_calculees
        if not connue:
            return "Cible inconnue : elle n'est plus dans le relevé."
        if any(c["cible"].get("type") == genre_cible and c["cible"].get("id") == i for c in challenges.values()):
            return "Un challenge existe déjà : ouvrez-le."
        return None
    for champ in CHAMPS[genre]:
        if not isinstance(demande.get(champ), str):
            return f"« {champ} » est obligatoire (texte)."
    ch = challenges.get(demande["challenge"])
    if ch is None:
        return "Challenge inconnu."
    if genre == "solution":
        return _texte_libre(demande["texte"], "texte")
    if demande["solution"] not in {s["id"] for s in ch.get("solutions") or []}:
        return "Solution inconnue."
    if demande["verdict"] not in ("valider", "ecarter"):
        return "Verdict inconnu (valider ou ecarter)."
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
