"""Le rapport structuré d'un agent : le dernier bloc ```json de sa réponse, lu et traduit en commandes `lancer`.

Forme (voir la consigne de fin d'étape de `orchestrateur/depart.py`) :
    {"statut": "fait" | "accord_requis" | "outil_refuse" | "echec",
     "message": {"texte", "images"?, "questions"?, "glossaire"?, "attend"}?,
     "fichiers": [{"chemin", "titre", "element"?, "livrable"?}],
     "lecons": [{"texte", "roles", "etage_propose", "texte_general"?}],
     "controles": [{"texte", "origine"}], "retours_factory": [str],
     "verdicts": [{"element", "conforme", "points": [str]}],
     "accord": {"quoi", "partenaire", "cout"}?, "outil": str?, "lignes": int?,
     "nom": str?, "cahier": {"maquette": [chemin], "etapes": [texte]}?, "methode_prete": bool?,
     "usage_estime": int?}
`usage_estime` : le total de tokens que l'agent estime avoir employés (un agent cloud ne peut pas faire mieux : le
moteur le note comme une estimation).
Les trois derniers champs sont demandés par la matière des seuls agents qui en ont l'usage (cadrage : `nom`, `cahier` ;
prototype : `methode_prete`), pas par la consigne de fin commune.
Le texte libre qui entoure le bloc ne sert qu'au journal. Le moteur n'écrit rien lui-même : `commandes` rend les
`(commande, entrée)` à passer à `lancer`.
"""
from moteur.jugement import extraire_json

STATUTS = ("fait", "accord_requis", "outil_refuse", "echec")
ETAGES = ("projet", "genre", "skill")


class RapportIllisible(Exception):
    """La réponse de l'agent ne porte pas de rapport utilisable."""


def _texte(v):
    return isinstance(v, str) and v.strip() != ""


def _liste(rapport, cle, genre):
    v = rapport.get(cle, [])
    if not isinstance(v, list) or not all(isinstance(x, genre) for x in v):
        raise RapportIllisible(f"« {cle} » doit être une liste de {'textes' if genre is str else 'objets'}.")
    return v


def lire(texte):
    """Le rapport de l'agent (le dernier bloc ```json de `texte`), complété de ses valeurs vides. Lève `RapportIllisible`."""
    brut = extraire_json(texte)
    if brut is None:
        raise RapportIllisible("aucun bloc ```json lisible dans la réponse de l'agent")
    if brut.get("statut") not in STATUTS:
        raise RapportIllisible(f"« statut » doit valoir {', '.join(STATUTS)}")
    r = dict(brut)
    m = r.get("message")
    if m is not None and (not isinstance(m, dict) or not isinstance(m.get("texte", ""), str)):
        raise RapportIllisible("« message » doit être un objet avec un « texte »")
    for cle in ("fichiers", "lecons", "controles", "verdicts"):
        _liste(r, cle, dict)
        r[cle] = r.get(cle, [])
    _liste(r, "retours_factory", str)
    r["retours_factory"] = r.get("retours_factory", [])
    for f in r["fichiers"]:
        if not _texte(f.get("chemin")) or not _texte(f.get("titre")):
            raise RapportIllisible("chaque fichier a un « chemin » et un « titre »")
    for x in r["lecons"]:
        if not _texte(x.get("texte")) or x.get("etage_propose") not in ETAGES:
            raise RapportIllisible("chaque leçon a un « texte » et un « etage_propose » (projet, genre ou skill)")
        if x["etage_propose"] != "projet" and not _texte(x.get("texte_general")):
            raise RapportIllisible("une leçon de genre ou de skill demande son « texte_general »")
    for c in r["controles"]:
        if not _texte(c.get("texte")) or not _texte(c.get("origine")):
            raise RapportIllisible("chaque contrôle a un « texte » et une « origine »")
    for v in r["verdicts"]:
        if not _texte(v.get("element")) or not isinstance(v.get("conforme"), bool):
            raise RapportIllisible("chaque verdict a un « element » et un « conforme » (vrai ou faux)")
        v["points"] = list(v.get("points") or [])
    if r["statut"] == "accord_requis":
        a = r.get("accord")
        if not isinstance(a, dict) or not all(_texte(a.get(c)) for c in ("quoi", "partenaire", "cout")):
            raise RapportIllisible("« accord_requis » demande « accord » : quoi, partenaire, cout")
    if r["statut"] == "outil_refuse" and not _texte(r.get("outil")):
        raise RapportIllisible("« outil_refuse » demande le nom de l'« outil »")
    if "nom" in r and not _texte(r["nom"]):
        raise RapportIllisible("« nom » doit être un texte non vide")
    if "cahier" in r:
        c = r["cahier"]
        if (not isinstance(c, dict) or not isinstance(c.get("maquette"), list) or not c["maquette"]
                or not all(_texte(x) for x in c["maquette"]) or not isinstance(c.get("etapes"), list)
                or not c["etapes"] or not all(_texte(x) for x in c["etapes"])):
            raise RapportIllisible("« cahier » demande « maquette » et « etapes » (listes de textes non vides)")
    if "methode_prete" in r and not isinstance(r["methode_prete"], bool):
        raise RapportIllisible("« methode_prete » doit être vrai ou faux")
    if "usage_estime" in r and (not isinstance(r["usage_estime"], int) or isinstance(r["usage_estime"], bool)
                                or r["usage_estime"] < 0):
        raise RapportIllisible("« usage_estime » doit être un entier positif (tokens)")
    if "lignes" in r and (not isinstance(r["lignes"], int) or isinstance(r["lignes"], bool) or r["lignes"] < 0):
        raise RapportIllisible("« lignes » doit être un entier positif")
    return r


ALIAS_TEXTE = ("question", "intitule", "libelle")       # ce que les agents écrivent à la place de « texte »
ALIAS_CHOIX = ("options", "reponses")


def normaliser_questions(questions):
    """Les questions d'un message, dans la forme de l'outil : `texte` pour `question`/`intitule`/`libelle`, `choix` pour
    `options`/`reponses`. Rien d'autre n'est inventé : ce qui reste mal formé est refusé par l'outil."""
    if not isinstance(questions, list):
        return questions
    sortie = []
    for q in questions:
        if not isinstance(q, dict):
            sortie.append(q)
            continue
        q = dict(q)
        for champ, alias in (("texte", ALIAS_TEXTE), ("choix", ALIAS_CHOIX)):
            if champ in q:
                for a in alias:
                    q.pop(a, None)
                continue
            bon = next((a for a in alias if (_texte(q.get(a)) if champ == "texte" else isinstance(q.get(a), list))),
                       None)
            if bon:
                q[champ] = q.pop(bon)
        sortie.append(q)
    return sortie


def commandes(rapport, *, fonctionnalite, tache, agent, etape):
    """Les `(commande, entrée)` à passer à `lancer`, dans l'ordre : message, documents, contrôles, leçons.
    Un rapport qui n'est pas « fait » ne rend que son message : rien n'est produit ni noté tant que l'accord n'est pas
    donné ou que l'outil n'est pas réglé (la boucle relance l'agent)."""
    sortie = []
    m = rapport.get("message")
    if m and _texte(m.get("texte")) and fonctionnalite:
        e = {"fonctionnalite": fonctionnalite, "auteur": agent, "texte": m["texte"]}
        for cle in ("images", "questions", "glossaire", "attend"):
            if m.get(cle):
                e[cle] = normaliser_questions(m[cle]) if cle == "questions" else m[cle]
        if "attend" in m and isinstance(m["attend"], bool):
            e["attend"] = m["attend"]
        sortie.append(("message", e))
    if rapport["statut"] != "fait":
        return sortie
    if fonctionnalite:
        for f in rapport["fichiers"]:
            e = {"fonctionnalite": fonctionnalite, "chemin": f["chemin"], "titre": f["titre"], "agent": agent,
                 "etape": etape, "tache": tache}
            if f.get("element"):
                e["element"] = f["element"]
            if f.get("livrable"):
                e["livrable"] = True
            sortie.append(("document", e))
    for c in rapport["controles"]:
        sortie.append(("controle", {"texte": c["texte"], "origine": c["origine"]}))
    for x in rapport["lecons"]:
        e = {"action": "noter", "agent": agent, "texte": x["texte"], "tache": tache,
             "roles": x.get("roles") or ["tous"], "etage_propose": x["etage_propose"]}
        if x.get("texte_general"):
            e["texte_general"] = x["texte_general"]
        sortie.append(("lecon", e))
    return sortie
