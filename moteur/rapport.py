"""Le rapport structuré d'un agent : le dernier bloc ```json de sa réponse, lu et traduit en commandes `lancer`.

Forme (voir la consigne de fin d'étape de `orchestrateur/depart.py`) :
    {"statut": "fait" | "accord_requis" | "outil_refuse" | "a_faire_chez_partenaire" | "echec",
     "message": {"texte", "images"?, "questions"?, "glossaire"?, "attend"}?,   (image : chemin ou {chemin, legende})
     "fichiers": [{"chemin", "titre", "element"?, "livrable"?}],
     "lecons": [{"texte", "roles", "etage_propose", "texte_general"?}],
     "controles": [{"texte", "origine"}], "retours_factory": [str],
     "verdicts": [{"element", "conforme", "points": [str]}],
     "accord": {"quoi", "partenaire", "cout"}?, "outil": str?, "lignes": int?,
     "chez_partenaire": {"partenaire", "quoi", "prompt", "reglages"?, "mode_operatoire", "a_rapporter", "elements"?}?,
     "nom": str?, "cahier": {"maquette": [chemin ou {chemin, legende}], "etapes": [texte], "partenaires": [{id, mode}]?,
                             "taille": {valeur: petite | moyenne | grande, pourquoi, fichiers?}?}?,
     "fiche_correction": {"en_clair"?, "symptome", "reproduction": [texte], "attendu", "piste"?, "taille"?: petite | normale}?,   (cadrage d'une correction)
     "methode_prete": bool?, "recette_reussie": bool?, "echecs_preexistants": [str]?, "apk_utilise": {variante, empreinte, date}?, "non_faites": [id de tâche]?,
     "usage_estime": int?, "comptes_rendus": [{"element", "texte", "images"?, "points_a_verifier"?, "acces"?, "doit_marcher"?, "pas_encore"?, "conclusion"?, "nature"?, "mode_operatoire"?}]?,
     "points_a_verifier": [str]?, "acces": {"url", "description"?}?,
     "nature": "en_jeu" | "visuel" | "son" | "mecanique" | "autre"?, "mode_operatoire": [str]?}
`points_a_verifier` et `acces` : rendus par l'étape qui précède une validation du Directeur (fenêtre de validation) ;
une forme fautive est écartée, jamais une raison de refuser le rapport.
`comptes_rendus` : dans un lot, le compte rendu de chaque élément à part (ce que le Directeur voit à sa validation) ;
une entrée mal formée est écartée, jamais une raison de refuser le rapport.
`recette_reussie` : rendu par une tâche de recette (métier testeur) : faux = la recette a échoué, la tâche n'est pas faite,
une correction reçoit les défauts et l'étape suivante ne s'ouvre pas ; sans le champ, le texte « recette non réussie » vaut
faux. Une valeur qui n'est pas vrai/faux est écartée.
`echecs_preexistants` : rendu par une tâche de recette : les noms des tests en échec qui échouaient DÉJÀ avant la correction
(rejoués sur la base) et étrangers à l'évolution ; ils ne comptent pas dans `recette_reussie` et le moteur ouvre une tâche
dédiée à chacun (une seule fois par test). Une valeur mal formée est écartée.
`echecs_a_classer` : rendu par une tâche de recette : les tests en échec que la recette n'a pas pu rejouer sur la base (préexistant
ou non ?) ; ils ne comptent pas dans `recette_reussie` : le moteur ouvre UNE tâche à chacun, qui les rejoue sur la base (jamais une
correction de l'évolution). `hors_perimetre` : les défauts relevés hors des critères de l'élément vérifié : chacun devient une
anomalie séparée, jamais un échec de la recette. `non_verifie` : ce que le cadre de la recette ne permet pas de vérifier : dit au
Directeur, jamais un échec. Une valeur mal formée est écartée.
`apk_utilise` : rendu par une tâche de test qui a reçu un APK (voir `registre_apk`) : lequel (variante, empreinte des sources,
date de construction), pour que la recette soit traçable. Une valeur mal formée est écartée.
`non_faites` : dans un lot, les tâches que l'agent n'a pas faites (ou en partie) ; le moteur ne les marque pas faites,
elles repartent à part. Une forme fautive est écartée.
`usage_estime` : le total de tokens que l'agent estime avoir employés (un agent cloud ne peut pas faire mieux : le
moteur le note comme une estimation).
Les trois derniers champs sont demandés par la matière des seuls agents qui en ont l'usage (cadrage : `nom`, `cahier` ;
prototype : `methode_prete`), pas par la consigne de fin commune.
Le texte libre qui entoure le bloc ne sert qu'au journal. Le moteur n'écrit rien lui-même : `commandes` rend les
`(commande, entrée)` à passer à `lancer`.
"""
from bureau import releve as rel
from moteur.jugement import extraire_json

STATUTS = ("fait", "accord_requis", "outil_refuse", "a_faire_chez_partenaire", "echec")
ETAGES = ("projet", "genre", "skill")


class RapportIllisible(Exception):
    """La réponse de l'agent ne porte pas de rapport utilisable."""


def _texte(v):
    return isinstance(v, str) and v.strip() != ""


def _image(x):
    """Une image rendue par l'agent : un chemin, ou `{chemin, legende?}` (la longueur de la légende est jugée par l'outil)."""
    if isinstance(x, dict):
        return _texte(x.get("chemin")) and (x.get("legende") is None or _texte(x["legende"]))
    return _texte(x)


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
        if v["conforme"] and v["points"]:
            v["conforme"] = False      # un défaut relevé est un refus : ses points ne sont plus ignorés (essai de coûts, 2026-11-19)
    if "recette_reussie" in r and not isinstance(r["recette_reussie"], bool):
        del r["recette_reussie"]
    if "apk_utilise" in r:
        a = r["apk_utilise"]
        if isinstance(a, dict) and all(isinstance(a.get(k), str) and a[k].strip() for k in ("variante", "empreinte", "date")):
            r["apk_utilise"] = {k: a[k].strip()[:80] for k in ("variante", "empreinte", "date")}
        else:
            del r["apk_utilise"]
    if "echecs_preexistants" in r:
        noms = r["echecs_preexistants"]
        if isinstance(noms, list):
            r["echecs_preexistants"] = [" ".join(n.split())[:120] for n in noms if isinstance(n, str) and n.strip()][:10]
        else:
            del r["echecs_preexistants"]
    for cle in ("echecs_a_classer", "hors_perimetre", "non_verifie"):
        if cle in r:
            v = r[cle]
            if isinstance(v, list):
                r[cle] = [" ".join(n.split())[:300] for n in v if isinstance(n, str) and n.strip()][:10]
            else:
                del r[cle]
    if r["statut"] == "accord_requis":
        a = r.get("accord")
        if not isinstance(a, dict) or not all(_texte(a.get(c)) for c in ("quoi", "partenaire", "cout")):
            raise RapportIllisible("« accord_requis » demande « accord » : quoi, partenaire, cout")
    if r["statut"] == "a_faire_chez_partenaire":
        r["chez_partenaire"] = _chez_partenaire(r.get("chez_partenaire"))
    if r["statut"] == "outil_refuse" and not _texte(r.get("outil")):
        raise RapportIllisible("« outil_refuse » demande le nom de l'« outil »")
    if "nom" in r and not _texte(r["nom"]):
        raise RapportIllisible("« nom » doit être un texte non vide")
    if "cahier" in r:
        c = r["cahier"]
        if (not isinstance(c, dict) or not isinstance(c.get("maquette"), list) or not c["maquette"]
                or not all(_image(x) for x in c["maquette"]) or not isinstance(c.get("etapes"), list)
                or not c["etapes"] or not all(_texte(x) for x in c["etapes"])):
            raise RapportIllisible("« cahier » demande « maquette » (chemins, ou {chemin, legende}) et « etapes » "
                                   "(listes non vides)")
    if isinstance(r.get("cahier"), dict) and "taille" in r["cahier"] and not rel.taille_ok(r["cahier"]["taille"]):
        r["cahier"] = {k: v for k, v in r["cahier"].items() if k != "taille"}   # mal formée : écartée (parcours complet)
    if isinstance(r.get("cahier"), dict) and "partenaires" in r["cahier"]:
        if not rel.partenaires_cahier_ok(r["cahier"]["partenaires"]):
            raise RapportIllisible("« cahier.partenaires » est une liste de {id, mode} (mode : direct, inscrit ou aucun), un "
                                   "partenaire au plus une fois")
    if "methode_prete" in r and not isinstance(r["methode_prete"], bool):
        raise RapportIllisible("« methode_prete » doit être vrai ou faux")
    if "usage_estime" in r and (not isinstance(r["usage_estime"], int) or isinstance(r["usage_estime"], bool)
                                or r["usage_estime"] < 0):
        raise RapportIllisible("« usage_estime » doit être un entier positif (tokens)")
    comptes = r.get("comptes_rendus")
    if comptes is not None:      # facultatif : un compte rendu par élément d'un lot (une forme fautive est ignorée)
        r["comptes_rendus"] = [_de_quoi_valider(x) for x in comptes if isinstance(x, dict) and _texte(x.get("element"))
                               and isinstance(x.get("texte", ""), str)] if isinstance(comptes, list) else []
    nf = r.get("non_faites")
    r["non_faites"] = [x.strip() for x in nf if _texte(x)] if isinstance(nf, list) else []
    r = _de_quoi_valider(r)
    if "lignes" in r and (not isinstance(r["lignes"], int) or isinstance(r["lignes"], bool) or r["lignes"] < 0):
        raise RapportIllisible("« lignes » doit être un entier positif")
    return r


def _liste_de_textes(v, quoi, minimum=0):
    if not isinstance(v, list) or len(v) < minimum or not all(_texte(x) for x in v):
        raise RapportIllisible(f"« {quoi} » doit être une liste de textes" + (" non vide" if minimum else ""))
    return [x.strip() for x in v]


def _chez_partenaire(c):
    """La demande « À faire chez <partenaire> » d'un agent : l'utilisateur est inscrit chez ce partenaire (hors liaison
    directe), l'agent ne l'appelle pas : il prépare ce que l'utilisateur fait sur son site. `partenaire` (identifiant du
    catalogue), `quoi`, `prompt` (prêt à copier), `reglages` (chacun des réglages du partenaire), `mode_operatoire` (où
    cliquer), `a_rapporter` `{description, nom?}` (le fichier attendu au retour), `elements` (ce que groupe le prompt).
    Les longueurs et le partenaire sont jugés par l'outil, qui pose la décision."""
    if (not isinstance(c, dict) or not all(_texte(c.get(k)) for k in ("partenaire", "quoi", "prompt"))
            or not isinstance(c.get("a_rapporter"), dict) or not _texte(c["a_rapporter"].get("description"))
            or (c["a_rapporter"].get("nom") is not None and not _texte(c["a_rapporter"]["nom"]))):
        raise RapportIllisible("« a_faire_chez_partenaire » demande « chez_partenaire » : partenaire, quoi, prompt, "
                               "mode_operatoire, a_rapporter {description, nom?}")
    sortie = {"partenaire": c["partenaire"].strip(), "quoi": c["quoi"].strip(), "prompt": c["prompt"].strip(),
              "mode_operatoire": _liste_de_textes(c.get("mode_operatoire"), "mode_operatoire", 1),
              "reglages": _liste_de_textes(c.get("reglages", []), "reglages"),
              "a_rapporter": {k: c["a_rapporter"][k].strip() for k in ("description", "nom") if c["a_rapporter"].get(k)}}
    if c.get("elements") is not None:
        sortie["elements"] = _liste_de_textes(c["elements"], "elements")
    return sortie


def _de_quoi_valider(x):
    """`points_a_verifier` et `acces` (fenêtre de validation), facultatifs, dans le rapport ou le compte rendu d'un
    élément : une forme fautive est écartée sans refuser le rapport (le moteur dérive alors des points de l'objectif).
    Points : les phrases valides (160 caractères au plus, sans doublon), 8 au plus."""
    x = dict(x)
    if "points_a_verifier" in x:
        points, vus = [], set()
        for p in x["points_a_verifier"] if isinstance(x["points_a_verifier"], list) else []:
            if rel.point_ok(p) and p.strip() not in vus:
                vus.add(p.strip())
                points.append(" ".join(p.split()))
        x["points_a_verifier"] = points[:rel.MAX_POINTS]
    if "acces" in x and not rel.acces_ok(x["acces"]):
        del x["acces"]
    for c, maximum, vide in rel.CHAMPS_DIT:      # ce que dit la validation ; une forme fautive est écartée
        if c in x:
            if rel.texte_dit_ok(x[c], maximum, vide):
                x[c] = " ".join(x[c].split())
            else:
                del x[c]
    if "nature" in x and not rel.nature_ok(x["nature"]):
        del x["nature"]
    if "mode_operatoire" in x:
        if rel.mode_operatoire_ok(x["mode_operatoire"]):
            x["mode_operatoire"] = rel.mode_operatoire_propre(x["mode_operatoire"])
        else:
            del x["mode_operatoire"]
    return x


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
