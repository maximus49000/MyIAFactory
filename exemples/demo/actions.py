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


GESTES = {"bouton": bouton, "deplacer": deplacer, "retour": retour, "lecon": lecon}


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
