"""Commande d'actions de la démonstration.

Le bureau la lance pour chaque geste de l'utilisateur et lui donne une demande en JSON (UTF-8) sur l'entrée
standard. Ici, « le projet » est le fichier `releve.json` voisin : on y applique la demande, et le bureau
montre l'effet au relevé suivant. Dans un vrai projet, c'est l'orchestrateur qui lit la demande et agit.

Code de sortie 0 : demande prise. Autre code : refusée (la première ligne écrite est montrée à l'utilisateur).
Compatible Python 3.9 et plus, bibliothèque standard seulement.

Les demandes de la version 4 (nouvelle fonctionnalité, discussion, cahier des charges, méthode, genre, session
cloud, retour sur un élément du catalogue) reçoivent des réponses fixes : la démo fait passer une fonctionnalité du
cadrage à la série en quatre gestes. La démo B (`exemples/demo-b/actions.py`) réutilise ce fichier sur son dossier.
"""
import base64
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

DOSSIER = Path(globals().get("DOSSIER") or Path(__file__).resolve().parent)   # la démo B donne le sien
RELEVE = DOSSIER / "releve.json"
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


# --- Version 4 : le parcours d'une fonctionnalité, joué avec des réponses fixes.
ETAPES_DEMO = ["Décrire le besoin en une page", "Faire la maquette de l'écran", "Écrire l'écran",
               "Le relire à deux", "Le mettre en ligne"]


def _fonctionnalite(r, d):
    f = next((x for x in r.get("fonctionnalites", []) if x["id"] == d.get("fonctionnalite")), None)
    if f is None:
        refuser("Fonctionnalité inconnue : " + str(d.get("fonctionnalite")))
    return f


def _agent_cadrage(r):
    """Le premier agent du service Métier, sinon le premier titulaire."""
    return next((t["cle"] for t in r["titulaires"] if t.get("service") == "metier"), r["titulaires"][0]["cle"])


def _ranger_images(f_id, images):
    """Le bureau n'écrit rien dans le projet : c'est la commande d'actions qui range les images jointes."""
    chemins = []
    dossier = DOSSIER / "images" / "pieces" / f_id
    dossier.mkdir(parents=True, exist_ok=True)
    for i in images or []:
        nom = Path(i["nom"]).name
        cible = dossier / nom
        n = 1
        while cible.exists():
            cible = dossier / f"{Path(nom).stem}-{n}{Path(nom).suffix}"
            n += 1
        cible.write_bytes(base64.b64decode(i["donnees"]))
        chemins.append(cible.relative_to(DOSSIER).as_posix())
    return chemins


def _dire(f, auteur, texte, images=None):
    m = {"id": _libre({x["id"] for x in f["discussion"]}, "m"), "t": maintenant(), "auteur": auteur, "texte": texte}
    if images:
        m["images"] = images
    f["discussion"].append(m)


def _decision_id(r):
    pris = {x["id"] for f in r.get("fonctionnalites", []) for x in f.get("decisions", [])}
    pris |= {x["id"] for x in r.get("decisions_projet", [])}
    return _libre(pris, "d")


def _poser(r, f, genre, texte):
    f["decisions"] = [x for x in f["decisions"] if x["genre"] != genre]
    f["decisions"].append({"id": _decision_id(r), "genre": genre, "texte": texte})


def _lever(f, *genres):
    f["decisions"] = [x for x in f["decisions"] if x["genre"] not in genres]


def fonctionnalite(r, d):
    fonctionnalites = r.setdefault("fonctionnalites", [])
    f = {"id": _libre({x["id"] for x in fonctionnalites}, "f"), "nom": d["texte"].strip()[:40] or "Sans nom",
         "etape": "cadrage", "agent_cadrage": _agent_cadrage(r), "attend_reponse": False, "catalogue": False,
         "discussion": [], "decisions": []}
    _dire(f, "utilisateur", d["texte"], _ranger_images(f["id"], d.get("images")))
    _dire(f, f["agent_cadrage"], "Merci ! Pour bien cibler : qui s'en servira, et à quel moment ? (réponse de démo)")
    fonctionnalites.append(f)


def message(r, d):
    f = _fonctionnalite(r, d)
    _dire(f, "utilisateur", d["texte"], _ranger_images(f["id"], d.get("images")))
    if f["etape"] == "cadrage":   # la démo considère le besoin clair : le cahier des charges est prêt
        f["etape"] = "cahier"
        f["cahier"] = {"maquette": ["images/parcours/maquette.png"], "etapes": list(ETAPES_DEMO)}
        _dire(f, f["agent_cadrage"], "C'est clair. Voici la maquette et les étapes : le cahier des charges est à "
                                     "valider.", ["images/parcours/maquette.png"])
        _poser(r, f, "valider_cahier", "Valider le cahier des charges de « " + f["nom"] + " »")
    elif f["etape"] == "prototype":
        _dire(f, f["agent_cadrage"], "Retour pris : nouveau tour du prototype.", ["images/parcours/prototype.png"])
    else:
        _dire(f, f["agent_cadrage"], REPONSE)


def cahier(r, d):
    f = _fonctionnalite(r, d)
    if d.get("verdict") == "corriger":
        _dire(f, f["agent_cadrage"], "Cahier corrigé (démo) : " + (d.get("texte") or "sans précision") + ".")
        _poser(r, f, "valider_cahier", "Valider le cahier des charges corrigé de « " + f["nom"] + " »")
        return
    if d.get("verdict") != "valider":
        refuser("Verdict inconnu : " + str(d.get("verdict")))
    f.setdefault("cahier", {"maquette": [], "etapes": []})["valide_le"] = maintenant()
    _lever(f, "valider_cahier")
    # Découpage puis premier tour du prototype, joués d'un coup par la démo.
    f["etape"] = "prototype"
    _dire(f, f["agent_cadrage"], "Découpage fait : trois écrans, un seul modèle qui se répète. Voici le premier tour "
                                 "du prototype.", ["images/parcours/prototype.png"])
    _poser(r, f, "valider_methode", "Valider la méthode du prototype de « " + f["nom"] + " »")


def methode(r, d):
    f = _fonctionnalite(r, d)
    verdict = d.get("verdict")
    if verdict == "valider":
        version = (f.get("methode") or {}).get("version", 0) + 1
        f["methode"] = {"version": version, "chemin": f"methodes/{f['id']}.md", "validee_le": maintenant()}
        f["etape"] = "serie"
        _lever(f, "valider_methode", "methode_a_revoir")
        _dire(f, f["agent_cadrage"], f"Méthode version {version} écrite : la série commence.")
    elif verdict == "revoir":
        f["etape"] = "prototype"
        _lever(f, "methode_a_revoir")
        _dire(f, f["agent_cadrage"], "Nouvelle mise au point de la méthode : prototype, nouveau tour.",
              ["images/parcours/prototype.png"])
        _poser(r, f, "valider_methode", "Valider la méthode revue de « " + f["nom"] + " »")
    elif verdict == "garder":
        _lever(f, "methode_a_revoir")
        _dire(f, f["agent_cadrage"], "Méthode gardée : l'élément passe en « bloqué ».")
    else:
        refuser("Verdict inconnu : " + str(verdict))


def _decision_projet(r, d, genre):
    x = next((x for x in r.get("decisions_projet", []) if x["id"] == d.get("decision") and x["genre"] == genre), None)
    if x is None:
        refuser("Décision inconnue : " + str(d.get("decision")))
    r["decisions_projet"] = [y for y in r["decisions_projet"] if y is not x]
    return x


def genre(r, d):
    _decision_projet(r, d, "confirmer_genre")
    r["genre"] = d["genre"]


def session_cloud(r, d):
    x = _decision_projet(r, d, "session_cloud")
    for t in r["titulaires"]:
        if t["cle"] == x.get("agent"):
            t["lieu"] = "cloud"


def retour_element(r, d):
    """Le retour est noté sur l'élément, dans le fichier du catalogue de la fonctionnalité."""
    f = _fonctionnalite(r, d)
    regl = json.loads((DOSSIER / "reglages.json").read_text(encoding="utf-8-sig"))
    decl = (regl.get("catalogues") or {}).get(f["id"])
    if not decl or "fichier" not in decl:
        refuser("Pas de catalogue pour cette fonctionnalité.")
    chemin = DOSSIER / decl["fichier"]
    cat = json.loads(chemin.read_text(encoding="utf-8-sig"))
    e = next((x for x in cat.get("elements", []) if x["id"] == d.get("element")), None)
    if e is None:
        refuser("Élément inconnu : " + str(d.get("element")))
    e.setdefault("retours", []).append({"t": maintenant(), "texte": d["texte"], "etat": "pris en compte",
                                        "reponse": "Bien reçu (démo) : la correction passera à la prochaine passe."})
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as sortie:
            json.dump(cat, sortie, ensure_ascii=False, indent=2)
            sortie.write("\n")
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


GESTES = {"bouton": bouton, "deplacer": deplacer, "retour": retour, "lecon": lecon,
          "challenge": challenge, "solution": solution, "verdict_solution": verdict_solution,
          "fonctionnalite": fonctionnalite, "message": message, "cahier": cahier, "methode": methode,
          "genre": genre, "session_cloud": session_cloud, "retour_element": retour_element}


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
