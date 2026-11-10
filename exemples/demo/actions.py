"""Commande d'actions de la démonstration.

Le bureau la lance pour chaque geste de l'utilisateur et lui donne une demande en JSON (UTF-8) sur l'entrée
standard. Ici, « le projet » est le fichier `releve.json` voisin : on y applique la demande, et le bureau
montre l'effet au relevé suivant. Dans un vrai projet, c'est l'orchestrateur qui lit la demande et agit.

Code de sortie 0 : demande prise. Autre code : refusée (la première ligne écrite est montrée à l'utilisateur).
Compatible Python 3.9 et plus, bibliothèque standard seulement.
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RELEVE = Path(__file__).resolve().parent / "releve.json"
REPONSE = "Bien reçu (démo)."


def refuser(message):
    sys.stdout.buffer.write(message.encode("utf-8"))  # le bureau lit du UTF-8, quelle que soit la console
    sys.stdout.flush()
    sys.exit(1)


def maintenant():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def enregistrer(r):
    """Remplacement atomique : le bureau ne lit jamais un fichier à moitié écrit."""
    fd, tmp = tempfile.mkstemp(dir=str(RELEVE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, RELEVE)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def bouton(r, d):
    actions = r.get("actions", [])
    if d.get("id") not in [a["id"] for a in actions]:
        refuser("Bouton inconnu : " + str(d.get("id")))
    # L'identifiant dit l'état voulu : un double clic ne défait pas la demande.
    if d["id"] == "pause":
        r["factory"]["etat"] = "en pause"
        r["factory"]["depuis"] = maintenant()
        nouveau = {"id": "reprendre", "libelle": "Reprendre"}
    elif d["id"] == "reprendre":
        r["factory"]["etat"] = "en marche"
        r["factory"]["depuis"] = maintenant()
        nouveau = {"id": "pause", "libelle": "Pause", "confirmer": "Mettre la factory de démonstration en pause ?"}
    else:
        return  # un autre bouton : rien à changer dans la démonstration
    r["actions"] = [nouveau if a["id"] in ("pause", "reprendre") else a for a in actions]


def deplacer(r, d):
    if d.get("colonne") not in [c["id"] for c in r["colonnes"]]:
        refuser("Colonne inconnue : " + str(d.get("colonne")))
    tache = next((t for t in r["taches"] if t["id"] == d.get("tache")), None)
    if tache is None:
        file = r.get("file", {})
        visibles, suite = file.get("visibles", []), file.get("suite", [])
        q = next((q for q in visibles + suite if q["id"] == d.get("tache")), None)
        if q is None:
            refuser("Tâche inconnue : " + str(d.get("tache")))
        file["visibles"] = [x for x in visibles if x["id"] != q["id"]]
        if suite:
            file["suite"] = [x for x in suite if x["id"] != q["id"]]
        if file.get("reste", 0) > 0:
            file["reste"] -= 1
        if q in visibles:  # un élément de plus devient visible
            if file.get("suite"):
                file["visibles"].append(file["suite"].pop(0))
            elif file.get("reste", 0) > 0:
                file["visibles"].append({"id": q["id"] + "-suite", "titre": "Élément suivant de la file"})
        tache = {"id": q["id"], "titre": q.get("titre") or q["id"], "titulaire": None, "postit": True, "etape": "", "active": True}
        r["taches"].append(tache)
    tache["colonne"] = d["colonne"]
    tache["maj"] = maintenant()


def retour(r, d):
    tache = next((t for t in r["taches"] if t["id"] == d.get("tache")), None)
    if tache is None:
        refuser("Tâche inconnue : " + str(d.get("tache")))
    tache.setdefault("retours", []).append({"t": maintenant(), "texte": d["texte"], "reponse": REPONSE})


def lecon(r, d):
    if d.get("id") not in [x["id"] for x in r.get("lecons", [])]:
        refuser("Leçon inconnue : " + str(d.get("id")))
    r["lecons"] = [x for x in r["lecons"] if x["id"] != d["id"]]
    for t in r["titulaires"]:
        if "lecons" not in t:
            continue
        if d.get("verdict") == "valider":
            for x in t["lecons"]:
                if x["id"] == d["id"]:
                    x["etat"] = "validée"
        else:
            t["lecons"] = [x for x in t["lecons"] if x["id"] != d["id"]]


def _libre(pris, base):
    """Un identifiant qui n'est pas encore pris : base1, base2…"""
    n = 1
    while f"{base}{n}" in pris:
        n += 1
    return f"{base}{n}"


def _ajouter_solution(r, ch, texte, auteur):
    pris = {s["id"] for c in r.get("challenges", []) for s in c.get("solutions", [])}
    ch.setdefault("solutions", []).append(
        {"id": _libre(pris, ch["id"] + ":s"), "texte": texte, "auteur": auteur, "etat": "proposée"})


def _probleme(r, cible):
    """Le texte du challenge quand la demande n'en porte pas : le bureau n'écrit le constat que pour ce
    qu'il calcule lui-même ; un KPI ou une connaissance du projet, c'est au projet de les retrouver."""
    if cible["type"] == "kpi":
        for s in r["services"]:
            for k in s.get("kpi", []):
                if cible["id"] == f"kpi:{s['id']}:{k['id']}":
                    return k.get("texte") or f"{k['nom']} : {k['valeur']}"
    if cible["type"] == "connaissance":
        for t in r["titulaires"]:
            for x in t.get("connaissances", []) + t.get("lecons", []):
                if x["id"] == cible["id"]:
                    return "Connaissance contestée : « " + x["texte"] + " »"
    return "Challenge ouvert depuis le bureau."


def challenge(r, d):
    """Ouvre un challenge. La démo joue aussi le projet : le Directeur et le service proposent aussitôt
    chacun une solution (dans un vrai projet, ce sont les agents qui les écrivent)."""
    cible = d.get("cible")
    if (not isinstance(cible, dict) or cible.get("type") not in ("kpi", "connaissance", "source")
            or not isinstance(cible.get("id"), str) or not cible["id"]):
        refuser("Cible illisible.")
    cible = {"type": cible["type"], "id": cible["id"]}
    challenges = r.setdefault("challenges", [])
    if any(c["cible"] == cible for c in challenges):
        refuser("Un challenge existe déjà sur cette cible.")
    ch = {"id": _libre({c["id"] for c in challenges}, "c"), "cible": cible,
          "texte": d.get("texte") or _probleme(r, cible), "date": maintenant(), "solutions": []}
    challenges.append(ch)
    _ajouter_solution(r, ch, "Solution du Directeur (démo) : revoir la consigne donnée au service.", "directeur")
    _ajouter_solution(r, ch, "Solution du service (démo) : ajouter une vérification avant de livrer.", "service")
    if d.get("solution"):
        _ajouter_solution(r, ch, d["solution"], "utilisateur")


def _challenge(r, d):
    ch = next((c for c in r.get("challenges", []) if c["id"] == d.get("challenge")), None)
    if ch is None:
        refuser("Challenge inconnu : " + str(d.get("challenge")))
    return ch


def solution(r, d):
    if not isinstance(d.get("texte"), str) or not d["texte"].strip():
        refuser("La solution est vide.")
    _ajouter_solution(r, _challenge(r, d), d["texte"], "utilisateur")


def _agents_concernes(r, cible):
    """Qui reçoit la connaissance : le titulaire de la connaissance contestée, ou les agents du service
    visé par le KPI ou la source (`kpi:<service>:<id>`, `source:<service>:<genre>:<tâche>`)."""
    if cible["type"] == "connaissance":
        return [t for t in r["titulaires"]
                if any(x["id"] == cible["id"] for x in t.get("connaissances", []) + t.get("lecons", []))]
    reste = cible["id"].split(":", 1)[-1]
    services = sorted((s["id"] for s in r["services"] if reste.startswith(s["id"] + ":")), key=len)
    return [t for t in r["titulaires"] if services and t.get("service") == services[-1]]


def verdict_solution(r, d):
    ch = _challenge(r, d)
    sol = next((s for s in ch.get("solutions", []) if s["id"] == d.get("solution")), None)
    if sol is None:
        refuser("Solution inconnue : " + str(d.get("solution")))
    if d.get("verdict") == "ecarter":
        sol["etat"] = "écartée"
        return
    if d.get("verdict") != "valider":
        refuser("Verdict inconnu : " + str(d.get("verdict")))
    sol["etat"] = "validée"
    # La solution validée devient une connaissance des agents concernés ; son origine est le challenge.
    for t in _agents_concernes(r, ch["cible"]):
        i = f"k:{sol['id']}:{t['cle']}"  # un identifiant de connaissance est unique dans tout le relevé
        connaissances = t.setdefault("connaissances", [])
        if all(c["id"] != i for c in connaissances):
            connaissances.append({"id": i, "texte": sol["texte"], "date": maintenant(), "origine": ch["id"]})


GESTES = {"bouton": bouton, "deplacer": deplacer, "retour": retour, "lecon": lecon,
          "challenge": challenge, "solution": solution, "verdict_solution": verdict_solution}


def main():
    try:
        d = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        geste = GESTES[d["type"]]
    except (ValueError, KeyError, TypeError):
        refuser("Demande illisible.")
    r = json.loads(RELEVE.read_text(encoding="utf-8-sig"))
    geste(r, d)
    enregistrer(r)


if __name__ == "__main__":
    main()
