"""Le relevé : valider, normaliser, obtenir (fichier ou commande)."""
import copy
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .statuts import TRES_ANCIEN, lire_date

MAX_SERVICES = 8
MAX_IMAGES = 40
MAX_SUITE = 500
MAX_USAGE = 5000
VERSIONS = (1, 2, 3, 4)
ETAPES = ("cadrage", "cahier", "decoupage", "prototype", "methode", "serie", "terminee")
DECISIONS_FONCTIONNALITE = ("valider_cahier", "valider_methode", "methode_a_revoir")
DECISIONS_PROJET = ("confirmer_genre", "session_cloud", "organisation")
ETAGES = ("projet", "genre", "skill")
MOTIF_GENRE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")
MAX_FONCTIONNALITES = 100
MAX_MESSAGES = 1000
MAX_DOCUMENTS = 2000
MAX_QUESTIONS, MAX_CHOIX = 10, 12   # les questions à choix d'un message d'agent
MAX_GLOSSAIRE, MAX_MOT, MAX_DEFINITION = 500, 60, 400   # le vocabulaire défini par les agents
CHAMPS_DOCUMENT = ("agent", "etape", "tache", "element", "sous_tache", "date", "remplace")   # d'où vient un document
MAX_IMAGES_MESSAGE = 4
SCHEMAS_LIENS = ("https", "http", "claude")
DELAI_COMMANDE_S = 10


def _est_dict(x):
    return isinstance(x, dict)


def _liste_de_dicts(r, cle, erreurs):
    v = r.get(cle)
    if not isinstance(v, list):
        erreurs.append(f"« {cle} » est obligatoire et doit être une liste.")
        return []
    ok = []
    for i, el in enumerate(v):
        if _est_dict(el):
            ok.append(el)
        else:
            erreurs.append(f"« {cle} » : l'élément {i + 1} doit être un objet.")
    return ok


def _doublons(elements, cle, nom, erreurs):
    vus = set()
    for el in elements:
        v = el.get(cle)
        if not isinstance(v, str) or not v:
            erreurs.append(f"{nom} : « {cle} » est obligatoire (texte non vide).")
            continue
        if v in vus:
            erreurs.append(f"{nom} : identifiant en double « {v} ».")
        vus.add(v)
    return vus


def lien_valide(url):
    """Schéma https, http ou claude ; ni espace ni caractère de contrôle."""
    if not isinstance(url, str) or not url:
        return False
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return False
    schema, sep, reste = url.partition(":")
    return bool(sep) and schema.lower() in SCHEMAS_LIENS and len(reste) > 0


def _dans(valeur, ensemble):
    """Appartenance sûre : une valeur qui n'est pas un texte (liste, objet…) n'est jamais connue."""
    return isinstance(valeur, str) and valeur in ensemble


def valider(r):
    """Messages d'erreur en français ; liste vide si le relevé est valide."""
    if not _est_dict(r):
        return ["Le relevé doit être un objet JSON."]
    erreurs = []
    if r.get("version") not in VERSIONS or isinstance(r.get("version"), bool):
        erreurs.append("« version » doit valoir 1, 2, 3 ou 4.")
    if not isinstance(r.get("projet"), str) or not r.get("projet"):
        erreurs.append("« projet » est obligatoire (texte non vide).")
    factory = r.get("factory")
    if not _est_dict(factory) or factory.get("etat") not in ("en marche", "en pause"):
        erreurs.append("« factory.etat » doit valoir « en marche » ou « en pause ».")
    services = _liste_de_dicts(r, "services", erreurs)
    colonnes = _liste_de_dicts(r, "colonnes", erreurs)
    titulaires = _liste_de_dicts(r, "titulaires", erreurs)
    taches = _liste_de_dicts(r, "taches", erreurs)
    if len(services) > MAX_SERVICES:
        erreurs.append(f"Au plus {MAX_SERVICES} services (il y en a {len(services)}).")
    ids_services = _doublons(services, "id", "Services", erreurs)
    ids_colonnes = _doublons(colonnes, "id", "Colonnes", erreurs)
    cles = _doublons(titulaires, "cle", "Titulaires", erreurs)
    _doublons(taches, "id", "Tâches", erreurs)
    chefs = 0
    for t in titulaires:
        cle = t.get("cle")
        if t.get("lieu") not in ("local", "cloud"):
            erreurs.append(f"Titulaire « {cle} » : « lieu » doit valoir « local » ou « cloud ».")
        if t.get("chef") is True:
            chefs += 1
        elif not _dans(t.get("service"), ids_services):
            erreurs.append(f"Titulaire « {cle} » : service inconnu « {t.get('service')} ».")
    if chefs > 1:
        erreurs.append("Un seul titulaire peut avoir « chef » à vrai.")
    for t in taches:
        i = t.get("id")
        if not _dans(t.get("colonne"), ids_colonnes):
            erreurs.append(f"Tâche « {i} » : colonne inconnue « {t.get('colonne')} ».")
        if not isinstance(t.get("titre"), str):
            erreurs.append(f"Tâche « {i} » : « titre » est obligatoire.")
        if not isinstance(t.get("active"), bool):
            erreurs.append(f"Tâche « {i} » : « active » doit être vrai ou faux.")
        if t.get("titulaire") is not None and not _dans(t.get("titulaire"), cles):
            erreurs.append(f"Tâche « {i} » : titulaire inconnu « {t.get('titulaire')} ».")
        if "postit" in t and not isinstance(t["postit"], bool):
            erreurs.append(f"Tâche « {i} » : « postit » doit être vrai ou faux.")
        for champ in ("etape", "maj"):
            if not _texte_ou_nul(t.get(champ)):
                erreurs.append(f"Tâche « {i} » : « {champ} » doit être un texte.")
    _verifier_facultatifs(r, services, colonnes, titulaires, erreurs)
    if _version(r) >= 2:
        _verifier_v2(r, titulaires, taches, cles, erreurs)
    if _version(r) >= 3:
        _verifier_usage(r, titulaires, taches, cles, erreurs)
        _verifier_connaissances(r, titulaires, cles, erreurs)
        _verifier_kpi(services, erreurs)
    if _version(r) >= 4:
        _verifier_v4(r, titulaires, taches, cles, erreurs)
    return erreurs


def _version(r):
    v = r.get("version")
    return v if v in VERSIONS and not isinstance(v, bool) else 0


def _verifier_usage(r, titulaires, taches, cles, erreurs):
    """`usage` (version 3) : une entrée par discussion, compteurs de tokens bruts."""
    v = r.get("usage")
    if v is None:
        return
    if not isinstance(v, list):
        erreurs.append("« usage » doit être une liste.")
        return
    if len(v) > MAX_USAGE:
        erreurs.append(f"« usage » : au plus {MAX_USAGE} entrées (il y en a {len(v)}).")
        return
    ids_taches = {t.get("id") for t in taches if isinstance(t.get("id"), str)}
    agents = _agents_connus(titulaires, cles)
    vus = set()
    for k, u in enumerate(v):
        if not _est_dict(u):
            erreurs.append(f"« usage » : l'élément {k + 1} doit être un objet.")
            continue
        i = u.get("id")
        if not _texte(i) or not i:
            erreurs.append(f"« usage » : l'élément {k + 1} doit avoir un « id » (texte non vide).")
        elif i in vus:
            erreurs.append(f"« usage » : identifiant en double « {i} ».")
        else:
            vus.add(i)
        nom = f"« usage » : l'entrée « {i} »"
        if u.get("tache") is not None and not _dans(u.get("tache"), ids_taches):
            erreurs.append(f"{nom} : tâche inconnue « {u.get('tache')} ».")
        if u.get("agent") is not None and not _dans(u.get("agent"), agents):
            erreurs.append(f"{nom} : agent inconnu « {u.get('agent')} ».")
        if not _texte(u.get("modele")) or not u.get("modele"):
            erreurs.append(f"{nom} : « modele » est obligatoire (texte non vide).")
        if not _texte_ou_nul(u.get("etape")):
            erreurs.append(f"{nom} : « etape » doit être un texte.")
        if not _texte_ou_nul(u.get("lot")):
            erreurs.append(f"{nom} : « lot » doit être un texte.")
        if u.get("reparti") is not None and u["reparti"] not in ("temps", "egal"):
            erreurs.append(f"{nom} : « reparti » doit valoir temps ou egal.")
        if not _texte(u.get("t")) or lire_date(u.get("t")) == TRES_ANCIEN:
            erreurs.append(f"{nom} : « t » doit être une date ISO 8601 (texte).")
        for champ in ("entree", "sortie"):
            if not _entier_positif(u.get(champ)):
                erreurs.append(f"{nom} : « {champ} » doit être un nombre entier de tokens positif ou nul.")
        for champ in ("cache_lecture", "cache_ecriture"):
            if u.get(champ) is not None and not _entier_positif(u[champ]):
                erreurs.append(f"{nom} : « {champ} » doit être un nombre entier de tokens positif ou nul.")


def _genre_valide(v):
    return isinstance(v, str) and MOTIF_GENRE.match(v) is not None


def _chemin_ou_lien(o):
    """Exactement un de `lien` (valide) et `chemin` (texte non vide)."""
    a_lien, a_chemin = o.get("lien") is not None, o.get("chemin") is not None
    if a_lien == a_chemin:
        return False
    return lien_valide(o["lien"]) if a_lien else _texte_plein(o["chemin"])


def _livrable_ok(v):
    return (_est_dict(v) and _texte_plein(v.get("libelle")) and _texte_ou_nul(v.get("date"))
            and _chemin_ou_lien(v))


def _liste_de_textes(v, max_n=None):
    return (isinstance(v, list) and all(_texte_plein(x) for x in v)
            and (max_n is None or len(v) <= max_n))


def _verifier_fonctionnalites(r, cles_agents, erreurs, ids_decisions):
    fonctionnalites = r.get("fonctionnalites")
    if fonctionnalites is None:
        return set()
    liste = _liste_facultative(fonctionnalites, "« fonctionnalites »", erreurs)
    if len(liste) > MAX_FONCTIONNALITES:
        erreurs.append(f"« fonctionnalites » : au plus {MAX_FONCTIONNALITES} fonctionnalités (il y en a {len(liste)}).")
    vus = set()
    for f in liste:
        i = f.get("id")
        if not _texte_plein(i):
            erreurs.append("« fonctionnalites » : « id » est obligatoire (texte non vide).")
        elif i in vus:
            erreurs.append(f"« fonctionnalites » : identifiant en double « {i} ».")
        else:
            vus.add(i)
        nom = f"« fonctionnalites » : la fonctionnalité « {i} »"
        if not _texte(f.get("nom")):
            erreurs.append(f"{nom} doit avoir un « nom » (texte).")
        if f.get("etape") not in ETAPES:
            erreurs.append(f"{nom} : « etape » inconnue « {f.get('etape')} » ({', '.join(ETAPES)}).")
        ac = f.get("agent_cadrage")
        if ac is not None and not _dans(ac, cles_agents):
            erreurs.append(f"{nom} : « agent_cadrage » inconnu « {ac} ».")
        for champ in ("attend_reponse", "catalogue"):
            if f.get(champ) is not None and not isinstance(f[champ], bool):
                erreurs.append(f"{nom} : « {champ} » doit être vrai ou faux.")
        _verifier_discussion(f, nom, cles_agents, erreurs)
        _verifier_cahier_methode(f, nom, erreurs)
        if f.get("livrable") is not None and not _livrable_ok(f["livrable"]):
            erreurs.append(f"{nom} : « livrable » doit avoir un « libelle », une « date » et un seul de "
                           "« lien » (https, http ou claude) ou « chemin ».")
        for d in _liste_facultative(f.get("decisions"), f"{nom} : « decisions »", erreurs):
            _verifier_decision(d, DECISIONS_FONCTIONNALITE, f"{nom} : « decisions »", ids_decisions, erreurs)
        _verifier_documents(f, nom, erreurs)
        if f.get("glossaire") is not None:
            probleme = erreur_glossaire(f["glossaire"])
            if probleme:
                erreurs.append(f"{nom} : {probleme}")
    return vus


def erreur_glossaire(glossaire):
    """Un glossaire : `[{mot, definition}]` (le mot : 60 caractères au plus ; la définition : 400). Rend le problème
    en clair, ou `None`."""
    if not isinstance(glossaire, list) or len(glossaire) > MAX_GLOSSAIRE:
        return f"« glossaire » doit être une liste d'au plus {MAX_GLOSSAIRE} mots."
    for k, g in enumerate(glossaire, 1):
        if (not _est_dict(g) or not _texte_plein(g.get("mot")) or len(g["mot"]) > MAX_MOT
                or not _texte_plein(g.get("definition")) or len(g["definition"]) > MAX_DEFINITION):
            return (f"« glossaire » : l'entrée {k} doit avoir un « mot » ({MAX_MOT} caractères au plus) et une "
                    f"« definition » ({MAX_DEFINITION} caractères au plus).")
    return None


def erreur_questions(questions):
    """Les questions à choix d'un message d'agent : `[{texte, choix: [2 à 12 textes], multiple?}]`, 10 au plus.
    Rend le problème en clair, ou `None`."""
    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_QUESTIONS:
        return f"« questions » doit être une liste de 1 à {MAX_QUESTIONS} questions."
    for k, q in enumerate(questions, 1):
        if not _est_dict(q) or not _texte_plein(q.get("texte")):
            return f"« questions » : la question {k} doit avoir un « texte »."
        choix = q.get("choix")
        if (not isinstance(choix, list) or not 2 <= len(choix) <= MAX_CHOIX
                or not all(_texte_plein(c) for c in choix)):
            return f"« questions » : la question {k} doit avoir de 2 à {MAX_CHOIX} « choix » (textes non vides)."
        if q.get("multiple") is not None and not isinstance(q["multiple"], bool):
            return f"« questions » : « multiple » de la question {k} doit être vrai ou faux."
    return None


def _verifier_documents(f, nom, erreurs):
    """Les documents produits pour la fonctionnalité : `{chemin, titre}` et, facultatifs, d'où ils viennent."""
    documents = _liste_facultative(f.get("documents"), f"{nom} : « documents »", erreurs)
    if len(documents) > MAX_DOCUMENTS:
        erreurs.append(f"{nom} : « documents » : au plus {MAX_DOCUMENTS} documents (il y en a {len(documents)}).")
        return
    for k, d in enumerate(documents, 1):
        ici = f"{nom} : « documents », le document {k}"
        c = d.get("chemin")
        if not _texte_plein(c) or "\x00" in c or Path(c).is_absolute() or c[0] in "/\\":
            erreurs.append(f"{ici} : « chemin » doit être un chemin relatif aux réglages.")
        if not _texte_plein(d.get("titre")):
            erreurs.append(f"{ici} : « titre » est obligatoire (texte non vide).")
        for champ in CHAMPS_DOCUMENT:
            if d.get(champ) is not None and not _texte(d[champ]):
                erreurs.append(f"{ici} : « {champ} » doit être un texte.")
        if d.get("livrable") is not None and not isinstance(d["livrable"], bool):
            erreurs.append(f"{ici} : « livrable » doit être vrai ou faux (le livrable final de son élément).")


def _verifier_discussion(f, nom, cles_agents, erreurs):
    discussion = _liste_facultative(f.get("discussion"), f"{nom} : « discussion »", erreurs)
    if len(discussion) > MAX_MESSAGES:
        erreurs.append(f"{nom} : « discussion » : au plus {MAX_MESSAGES} messages (il y en a {len(discussion)}).")
        return
    vus = set()
    for m in discussion:
        i = m.get("id")
        if not _texte_plein(i):
            erreurs.append(f"{nom} : « discussion » : chaque message a un « id » (texte non vide).")
        elif i in vus:
            erreurs.append(f"{nom} : « discussion » : identifiant de message en double « {i} ».")
        else:
            vus.add(i)
        if not _texte(m.get("t")) or lire_date(m.get("t")) == TRES_ANCIEN:
            erreurs.append(f"{nom} : « discussion » : le message « {i} » : « t » doit être une date ISO 8601 (texte).")
        if m.get("auteur") != "utilisateur" and not _dans(m.get("auteur"), cles_agents):
            erreurs.append(f"{nom} : « discussion » : le message « {i} » a un « auteur » inconnu "
                           f"« {m.get('auteur')} » (utilisateur ou un titulaire).")
        if not _texte(m.get("texte")):
            erreurs.append(f"{nom} : « discussion » : le message « {i} » doit avoir un « texte ».")
        if m.get("images") is not None and not _liste_de_textes(m["images"], MAX_IMAGES_MESSAGE):
            erreurs.append(f"{nom} : « discussion » : le message « {i} » : « images » doit être une liste "
                           f"d'au plus {MAX_IMAGES_MESSAGE} chemins (textes non vides).")
        if m.get("attend") is not None and not isinstance(m["attend"], bool):
            erreurs.append(f"{nom} : « discussion » : le message « {i} » : « attend » doit être vrai ou faux.")
        if m.get("glossaire") is not None:
            probleme = erreur_glossaire(m["glossaire"])
            if probleme:
                erreurs.append(f"{nom} : « discussion » : le message « {i} » : {probleme}")
        if m.get("questions") is not None:
            probleme = erreur_questions(m["questions"])
            if probleme:
                erreurs.append(f"{nom} : « discussion » : le message « {i} » : {probleme}")


def _verifier_cahier_methode(f, nom, erreurs):
    c = f.get("cahier")
    if c is not None:
        if (not _est_dict(c) or not _liste_de_textes(c.get("maquette")) or not isinstance(c.get("etapes"), list)
                or not all(isinstance(x, str) for x in c["etapes"]) or not _texte_ou_nul(c.get("valide_le"))):
            erreurs.append(f"{nom} : « cahier » doit avoir une « maquette » (liste de chemins), des « etapes » "
                           "(liste de textes) et, si présent, un « valide_le » texte.")
    m = f.get("methode")
    if m is not None:
        version = m.get("version") if _est_dict(m) else None
        if (not _est_dict(m) or isinstance(version, bool) or not isinstance(version, int) or version < 1
                or not _chemin_ou_lien(m) or not _texte_ou_nul(m.get("validee_le"))):
            erreurs.append(f"{nom} : « methode » doit avoir une « version » (entier ≥ 1), un seul de « lien » "
                           "(https, http ou claude) ou « chemin », et, si présent, un « validee_le » texte.")


def _verifier_decision(d, genres, nom, ids_decisions, erreurs):
    i = d.get("id")
    if not _texte_plein(i):
        erreurs.append(f"{nom} : « id » est obligatoire (texte non vide).")
    elif i in ids_decisions:
        erreurs.append(f"{nom} : identifiant de décision en double « {i} » (unique dans tout le relevé).")
    else:
        ids_decisions.add(i)
    if d.get("genre") not in genres:
        erreurs.append(f"{nom} : la décision « {i} » a un « genre » inconnu « {d.get('genre')} » "
                       f"({', '.join(genres)}).")
    if not _texte(d.get("texte")):
        erreurs.append(f"{nom} : la décision « {i} » doit avoir un « texte ».")


def _verifier_decisions_projet(r, cles_agents, erreurs, ids_decisions):
    for d in _liste_facultative(r.get("decisions_projet"), "« decisions_projet »", erreurs):
        nom = "« decisions_projet »"
        _verifier_decision(d, DECISIONS_PROJET, nom, ids_decisions, erreurs)
        i = d.get("id")
        if d.get("genre") == "confirmer_genre":
            if not _genre_valide(d.get("propose")):
                erreurs.append(f"{nom} : la décision « {i} » : « propose » est obligatoire "
                               "(identifiant de genre : minuscules, chiffres et tirets, 40 au plus).")
            connus = d.get("genres_connus")
            if not isinstance(connus, list) or not all(_genre_valide(g) for g in connus):
                erreurs.append(f"{nom} : la décision « {i} » : « genres_connus » est obligatoire "
                               "(liste d'identifiants de genre).")
        elif d.get("genre") == "session_cloud":
            if not _dans(d.get("agent"), cles_agents):
                erreurs.append(f"{nom} : la décision « {i} » : « agent » inconnu « {d.get('agent')} ».")
        elif d.get("genre") == "organisation":
            _verifier_organisation(d, nom, erreurs)


MODELES_ORGANISATION = ("Haiku", "Sonnet", "Opus")


def _bornes(v):
    return (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                        and x >= 0 for x in v) and v[0] <= v[1])


def _verifier_organisation(d, nom, erreurs):
    """Une décision `organisation` : l'organisation complète après changement (contrôle de forme ; le contenu est
    contrôlé en détail par l'outil de l'orchestrateur, qui l'a posée)."""
    i, o = d.get("id"), d.get("organisation")
    nom = f"{nom} : la décision « {i} » : « organisation »"
    if not isinstance(o, dict):
        erreurs.append(f"{nom} est obligatoire (objet).")
        return
    for champ in ("services", "flux", "agents"):
        if not isinstance(o.get(champ), list) or not all(isinstance(x, dict) for x in o[champ]):
            erreurs.append(f"{nom} : « {champ} » doit être une liste d'objets.")
    if not isinstance(o.get("briefs"), dict):
        erreurs.append(f"{nom} : « briefs » doit être un objet.")
    cout = o.get("cout")
    if (not isinstance(cout, dict) or not _bornes(cout.get("tokens"))
            or (cout.get("euros") is not None and not _bornes(cout.get("euros")))):
        erreurs.append(f"{nom} : « cout » doit porter « tokens » [a, b] et « euros » [a, b] ou null (a ≤ b).")
    for a in o.get("agents") if isinstance(o.get("agents"), list) else []:
        if a.get("modele") not in MODELES_ORGANISATION:
            erreurs.append(f"{nom} : le modèle de l'agent « {a.get('cle')} » doit être Haiku, Sonnet ou Opus "
                           "(Fable n'est jamais choisi par un outil).")


def _verifier_lecons_v4(r, titulaires, erreurs):
    ensembles = [("« lecons »", r.get("lecons"))]
    ensembles += [(f"Titulaire « {t.get('cle')} » : « lecons »", t.get("lecons")) for t in titulaires]
    for nom, liste in ensembles:
        for le in _liste_facultative(liste, nom, erreurs):
            i = le.get("id")
            etage = le.get("etage_propose", "projet")
            if etage is not None and etage not in ETAGES:
                erreurs.append(f"{nom} : la leçon « {i} » : « etage_propose » inconnu « {etage} » "
                               "(projet, genre ou skill).")
            elif etage in ("genre", "skill") and not _texte_plein(le.get("texte_general")):
                erreurs.append(f"{nom} : la leçon « {i} » : « texte_general » est obligatoire "
                               "(texte non vide) quand l'étage est genre ou skill.")
            if le.get("texte_general") is not None and not _texte(le["texte_general"]):
                erreurs.append(f"{nom} : la leçon « {i} » : « texte_general » doit être un texte.")
            roles = le.get("roles")
            if roles is not None and (not _liste_de_textes(roles) or not roles):
                erreurs.append(f"{nom} : la leçon « {i} » : « roles » doit être une liste de textes non vide.")


def _verifier_v4(r, titulaires, taches, cles, erreurs):
    """Champs facultatifs de la version 4 (ignorés en version inférieure)."""
    agents = _agents_connus(titulaires, cles)
    if r.get("genre") is not None and not _genre_valide(r["genre"]):
        erreurs.append("« genre » doit être un identifiant de genre (minuscules, chiffres et tirets, "
                       "40 caractères au plus) ou nul.")
    if r.get("livrable") is not None and not _livrable_ok(r["livrable"]):
        erreurs.append("« livrable » doit avoir un « libelle », une « date » et un seul de « lien » "
                       "(https, http ou claude) ou « chemin ».")
    m = r.get("agents_locaux_max")
    if m is not None and (isinstance(m, bool) or not isinstance(m, int) or m < 1):
        erreurs.append("« agents_locaux_max » doit être un entier d'au moins 1 ou nul.")
    ids_decisions = set()
    ids_fonc = _verifier_fonctionnalites(r, agents, erreurs, ids_decisions)
    _verifier_decisions_projet(r, agents, erreurs, ids_decisions)
    for t in taches:
        i = t.get("id")
        if t.get("fonctionnalite") is not None and not _dans(t["fonctionnalite"], ids_fonc):
            erreurs.append(f"Tâche « {i} » : « fonctionnalite » inconnue « {t['fonctionnalite']} ».")
        for champ in ("element", "modele_depart"):
            if not _texte_ou_nul(t.get(champ)):
                erreurs.append(f"Tâche « {i} » : « {champ} » doit être un texte.")
        m = t.get("montee")
        if m is not None and (not _est_dict(m) or not all(_texte_plein(m.get(c)) for c in ("de", "a", "raison"))):
            erreurs.append(f"Tâche « {i} » : « montee » doit avoir « de », « a » et « raison » (textes non vides).")
        lot = t.get("lot")
        if lot is not None and (not _est_dict(lot) or not _texte_plein(lot.get("id")) or isinstance(lot.get("rang"), bool)
                                or not isinstance(lot.get("rang"), int) or lot["rang"] < 1):
            erreurs.append(f"Tâche « {i} » : « lot » doit avoir « id » (texte non vide) et « rang » (entier d'au moins 1).")
        n = t.get("lignes")
        if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 0):
            erreurs.append(f"Tâche « {i} » : « lignes » doit être un entier positif ou nul (lignes produites).")
    _verifier_lecons_v4(r, titulaires, erreurs)
    if r.get("partenaires") is not None:
        _verifier_partenaires(r["partenaires"], erreurs)


ETATS_CONNEXION = ("connecte", "declare", "non_connecte")


def _date_iso(v):
    """Une date AAAA-MM-JJ, avec ou sans heure."""
    if not isinstance(v, str):
        return False
    try:
        datetime.datetime.fromisoformat(v)
    except ValueError:
        return False
    return True


def _nombre_positif(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and v == v and 0 <= v < float("inf")


def _verifier_partenaires(p, erreurs):
    """`partenaires` (version 4, facultatif) : l'espace partenaire. Le catalogue réduit aux champs affichés,
    l'état des connexions (jamais une valeur de clé), les conseils du projet. Les identifiants de l'état et des
    conseils doivent être ceux du catalogue reçu."""
    nom = "« partenaires »"
    if not _est_dict(p):
        erreurs.append(f"{nom} doit être un objet.")
        return
    cats = p.get("categories")
    if not _est_dict(cats) or not all(isinstance(v, list) and all(_est_dict(x) for x in v) for v in cats.values()):
        erreurs.append(f"{nom} : « categories » doit être un objet de listes de partenaires.")
        return
    ids = set()
    for liste in cats.values():
        for x in liste:
            i = x.get("id")
            if not _texte_plein(i) or not _texte_plein(x.get("nom")):
                erreurs.append(f"{nom} : chaque partenaire a un « id » et un « nom » (textes non vides).")
            elif i in ids:
                erreurs.append(f"{nom} : le partenaire « {i} » est en double.")
            else:
                ids.add(i)
            if x.get("verifie_le") is not None and not _date_iso(x["verifie_le"]):
                erreurs.append(f"{nom} : « {i} » : « verifie_le » n'est pas une date.")
            if x.get("description") is not None and not (_texte(x["description"]) and x["description"].strip()):
                erreurs.append(f"{nom} : « {i} » : « description » doit être nulle ou un texte non vide.")
            po = x.get("popularite")
            if po is not None and not (_est_dict(po) and not isinstance(po.get("niveau"), bool) and isinstance(po.get("niveau"), int)
                                       and 1 <= po["niveau"] <= 5 and _texte(po.get("base")) and _date_iso(po.get("date"))):
                erreurs.append(f"{nom} : « {i} » : « popularite » doit être nulle ou {{niveau 1 à 5, base, date}}.")
    etat = p.get("etat", {})
    if not _est_dict(etat):
        erreurs.append(f"{nom} : « etat » doit être un objet.")
        etat = {}
    for section in ("connexions", "quotas", "limites", "regles"):
        s = etat.get(section, {})
        if not _est_dict(s):
            erreurs.append(f"{nom} : « etat.{section} » doit être un objet.")
            continue
        for i, v in s.items():
            q = f"{nom} : « etat.{section} » « {i} »"
            if i not in ids:
                erreurs.append(f"{q} : partenaire inconnu du catalogue.")
            elif section == "regles":
                _verifier_regles(v, q, erreurs)
            elif not _est_dict(v):
                erreurs.append(f"{q} : doit être un objet.")
            elif section == "connexions":
                if v.get("etat") not in ETATS_CONNEXION:
                    erreurs.append(f"{q} : « etat » doit valoir connecte, declare ou non_connecte.")
                for c in ("source", "abonnement"):
                    if not _texte_ou_nul(v.get(c)):
                        erreurs.append(f"{q} : « {c} » doit être un texte.")
                if v.get("vu_le") is not None and not _date_iso(v["vu_le"]):
                    erreurs.append(f"{q} : « vu_le » n'est pas une date.")
            elif section == "quotas":
                if v.get("reste") is not None and not _nombre_positif(v["reste"]):
                    erreurs.append(f"{q} : « reste » doit être un nombre positif.")
                if not _texte_ou_nul(v.get("unite")):
                    erreurs.append(f"{q} : « unite » doit être un texte.")
                if "illimite" in v and not isinstance(v["illimite"], bool):
                    erreurs.append(f"{q} : « illimite » doit être vrai ou faux.")
                if v.get("lu_le") is not None and not _date_iso(v["lu_le"]):
                    erreurs.append(f"{q} : « lu_le » n'est pas une date.")
            else:
                if not _texte(v.get("raison")):
                    erreurs.append(f"{q} : « raison » doit être un texte.")
                if v.get("depuis") is not None and not _date_iso(v["depuis"]):
                    erreurs.append(f"{q} : « depuis » n'est pas une date.")
    conseils = p.get("conseils", {})
    if not _est_dict(conseils) or not all(isinstance(v, list) and all(_est_dict(x) for x in v) for v in conseils.values()):
        erreurs.append(f"{nom} : « conseils » doit être un objet de listes de partenaires conseillés.")
    else:
        for besoin, liste in conseils.items():
            for x in liste:
                if x.get("id") not in ids:
                    erreurs.append(f"{nom} : conseil « {besoin} » : partenaire inconnu « {x.get('id')} ».")
                if not _texte_ou_nul(x.get("raison")):
                    erreurs.append(f"{nom} : conseil « {besoin} » : « raison » doit être un texte.")
    if p.get("maj_catalogue") is not None and not _date_iso(p["maj_catalogue"]):
        erreurs.append(f"{nom} : « maj_catalogue » n'est pas une date.")
    c = p.get("cout_maj")
    if c is not None and (not _est_dict(c) or (c.get("euros") is not None and not _nombre_positif(c["euros"]))
                          or not _texte_ou_nul(c.get("texte"))):
        erreurs.append(f"{nom} : « cout_maj » doit avoir « euros » (nombre positif ou nul) et « texte ».")


def _verifier_regles(regles, q, erreurs):
    if not isinstance(regles, list) or not all(_est_dict(r) for r in regles):
        erreurs.append(f"{q} : doit être une liste de règles.")
        return
    vus = set()
    for r in regles:
        if not _texte_plein(r.get("id")) or not _texte_plein(r.get("texte")):
            erreurs.append(f"{q} : chaque règle a un « id » et un « texte » (textes non vides).")
        elif r["id"] in vus:
            erreurs.append(f"{q} : la règle « {r['id']} » est en double.")
        else:
            vus.add(r["id"])
        for d in ("cree_le", "modifie_le"):
            if r.get(d) is not None and not _date_iso(r[d]):
                erreurs.append(f"{q} : « {d} » n'est pas une date.")


CHAMPS_V4_RACINE = ("genre", "livrable", "fonctionnalites", "decisions_projet", "agents_locaux_max")
CHAMPS_V4_TACHE = ("fonctionnalite", "element", "modele_depart", "montee", "lot")


def _normaliser_v4(n):
    v4 = _version(n) >= 4
    for c in CHAMPS_V4_RACINE:
        if not v4:
            n.pop(c, None)
        elif c in ("fonctionnalites", "decisions_projet"):
            n[c] = n[c] if isinstance(n.get(c), list) else []
        else:
            n.setdefault(c, None)
    if v4 and _est_dict(n.get("partenaires")):
        pa = n["partenaires"]
        etat = pa["etat"] = pa["etat"] if _est_dict(pa.get("etat")) else {}
        for section in ("connexions", "quotas", "limites", "regles"):
            etat[section] = etat[section] if _est_dict(etat.get(section)) else {}
        pa["conseils"] = pa["conseils"] if _est_dict(pa.get("conseils")) else {}
        pa.setdefault("maj_catalogue", None)
        pa.setdefault("cout_maj", None)
    else:
        n.pop("partenaires", None)
    for f in n.get("fonctionnalites") or []:
        for c in ("discussion", "decisions", "documents"):
            f[c] = f[c] if isinstance(f.get(c), list) else []
        f["attend_reponse"] = f.get("attend_reponse") is True
        f["catalogue"] = f.get("catalogue") is True
        for c in ("cahier", "methode", "livrable", "agent_cadrage"):
            f.setdefault(c, None)
    for t in n["taches"]:
        for c in CHAMPS_V4_TACHE:
            if v4:
                t.setdefault(c, None)
            else:
                t.pop(c, None)
    for liste in [n.get("lecons")] + [t.get("lecons") for t in n["titulaires"]]:
        for le in liste if isinstance(liste, list) else []:
            if v4:
                if le.get("etage_propose") is None:
                    le["etage_propose"] = "projet"
                le.setdefault("texte_general", None)
                if not isinstance(le.get("roles"), list):
                    le["roles"] = ["tous"]
            else:
                for c in ("etage_propose", "texte_general", "roles"):
                    le.pop(c, None)


PERIODES_KPI = ("aujourdhui", "7j", "30j")


def _valeur_kpi(v):
    """Un nombre fini (pas un booléen) ou un texte."""
    return isinstance(v, str) or (isinstance(v, (int, float)) and not isinstance(v, bool)
                                  and v == v and abs(v) != float("inf"))


def _verifier_kpi(services, erreurs):
    """`kpi` par service (version 3) : une liste ouverte, les `id` ne sont uniques que dans leur service."""
    for sv in services:
        if sv.get("kpi") is None:
            continue
        nom_liste = f"Service « {sv.get('id')} » : « kpi »"
        vus = set()
        for k in _liste_facultative(sv["kpi"], nom_liste, erreurs):
            i = k.get("id")
            if not _texte_plein(i):
                erreurs.append(f"{nom_liste} : chaque KPI a un « id » (texte non vide).")
            elif i in vus:
                erreurs.append(f"{nom_liste} : identifiant de KPI en double « {i} ».")
            else:
                vus.add(i)
            nom = f"{nom_liste} : le KPI « {i} »"
            if not _texte_plein(k.get("nom")):
                erreurs.append(f"{nom} doit avoir un « nom » (texte non vide).")
            if not _valeur_kpi(k.get("valeur")):
                erreurs.append(f"{nom} : « valeur » doit être un nombre ou un texte.")
            for champ in ("unite", "evolution", "texte"):
                if not _texte_ou_nul(k.get(champ)):
                    erreurs.append(f"{nom} : « {champ} » doit être un texte.")
            if k.get("alerte") is not None and not isinstance(k["alerte"], bool):
                erreurs.append(f"{nom} : « alerte » doit être vrai ou faux.")
            p = k.get("periodes")
            if p is None:
                continue
            if not _est_dict(p):
                erreurs.append(f"{nom} : « periodes » doit être un objet (aujourdhui, 7j, 30j).")
                continue
            for cle, v in p.items():
                if cle not in PERIODES_KPI:
                    erreurs.append(f"{nom} : période inconnue « {cle} » (aujourdhui, 7j ou 30j).")
                elif not _valeur_kpi(v):
                    erreurs.append(f"{nom} : « periodes.{cle} » doit être un nombre ou un texte.")


AUTEURS = ("directeur", "service", "utilisateur")
TYPES_CIBLE = ("kpi", "connaissance", "source")


def _agents_connus(titulaires, cles):
    agents = set(cles)
    if not any(t.get("chef") is True for t in titulaires):
        agents.add("chef")  # le chef que la normalisation ajoute
    return agents


def _texte_plein(v):
    return isinstance(v, str) and bool(v)


def _verifier_connaissances(r, titulaires, cles, erreurs):
    """`connaissances` par titulaire et `challenges` (version 3). Les identifiants des connaissances,
    des challenges et des solutions sont uniques dans tout le relevé (une leçon peut partager l'id
    d'une connaissance : la connaissance l'emporte)."""
    agents = _agents_connus(titulaires, cles)
    vus = set()
    for ti in titulaires:
        cle = ti.get("cle")
        nom = f"Titulaire « {cle} » : « connaissances »"
        if "connaissances" not in ti or ti["connaissances"] is None:
            continue
        for c in _liste_facultative(ti["connaissances"], nom, erreurs):
            i = c.get("id")
            if not _texte_plein(i):
                erreurs.append(f"{nom} : chaque connaissance a un « id » (texte non vide).")
            elif i in vus:
                erreurs.append(f"{nom} : identifiant de connaissance en double « {i} ».")
            else:
                vus.add(i)
            if not _texte(c.get("texte")):
                erreurs.append(f"{nom} : la connaissance « {i} » doit avoir un « texte ».")
            for champ in ("date", "origine"):
                if not _texte_ou_nul(c.get(champ)):
                    erreurs.append(f"{nom} : la connaissance « {i} » : « {champ} » doit être un texte.")
            ad = c.get("appris_de")
            if ad is None:
                continue
            for a in _liste_facultative(ad, f"{nom} : la connaissance « {i} » : « appris_de »", erreurs):
                if not _dans(a.get("agent"), agents):
                    erreurs.append(f"{nom} : la connaissance « {i} » : « appris_de » cite un agent inconnu "
                                   f"« {a.get('agent')} ».")
                for champ in ("tache", "retour"):
                    if not _texte_ou_nul(a.get(champ)):
                        erreurs.append(f"{nom} : la connaissance « {i} » : « appris_de » : « {champ} » "
                                       "doit être un texte.")
    if r.get("challenges") is None:
        return
    vus_ch, vus_sol = set(), set()
    for ch in _liste_facultative(r["challenges"], "« challenges »", erreurs):
        i = ch.get("id")
        nom = f"« challenges » : le challenge « {i} »"
        if not _texte_plein(i):
            erreurs.append("« challenges » : chaque challenge a un « id » (texte non vide).")
        elif i in vus_ch:
            erreurs.append(f"« challenges » : identifiant de challenge en double « {i} ».")
        else:
            vus_ch.add(i)
        cible = ch.get("cible")
        if not _est_dict(cible) or not _texte_plein(cible.get("id")):
            erreurs.append(f"{nom} : « cible » doit être un objet avec un « type » et un « id » (texte non vide).")
        elif cible.get("type") not in TYPES_CIBLE:
            erreurs.append(f"{nom} : type de « cible » inconnu « {cible.get('type')} » "
                           "(kpi, connaissance ou source).")
        if not _texte(ch.get("texte")):
            erreurs.append(f"{nom} : « texte » est obligatoire (texte).")
        if not _texte_ou_nul(ch.get("date")):
            erreurs.append(f"{nom} : « date » doit être un texte.")
        if ch.get("solutions") is None:
            continue
        for so in _liste_facultative(ch["solutions"], f"{nom} : « solutions »", erreurs):
            j = so.get("id")
            if not _texte_plein(j):
                erreurs.append(f"{nom} : chaque solution a un « id » (texte non vide).")
            elif j in vus_sol:
                erreurs.append(f"{nom} : identifiant de solution en double « {j} » (dans tous les challenges).")
            else:
                vus_sol.add(j)
            if not _texte(so.get("texte")):
                erreurs.append(f"{nom} : la solution « {j} » doit avoir un « texte ».")
            if so.get("auteur") not in AUTEURS:
                erreurs.append(f"{nom} : la solution « {j} » a un « auteur » inconnu « {so.get('auteur')} » "
                               "(directeur, service ou utilisateur).")
            if not _texte_ou_nul(so.get("etat")):
                erreurs.append(f"{nom} : la solution « {j} » : « etat » doit être un texte.")


def _texte_ou_nul(v):
    return v is None or isinstance(v, str)


def _entier_positif(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _verifier_facultatifs(r, services, colonnes, titulaires, erreurs):
    """Les champs facultatifs, s'ils sont là, doivent avoir le bon type : la page s'y fie."""
    factory = r.get("factory")
    if _est_dict(factory) and not _texte_ou_nul(factory.get("depuis")):
        erreurs.append("« factory.depuis » doit être une date (texte).")
    for nom, elements in (("Service", services), ("Colonne", colonnes)):
        for el in elements:
            if not isinstance(el.get("nom"), str):
                erreurs.append(f"{nom} « {el.get('id')} » : « nom » est obligatoire (texte).")
    for t in titulaires:
        cle = t.get("cle")
        if "modele" in t and not isinstance(t["modele"], str):
            erreurs.append(f"Titulaire « {cle} » : « modele » doit être un texte.")
        for champ in ("permanent", "chef"):
            if champ in t and not isinstance(t[champ], bool):
                erreurs.append(f"Titulaire « {cle} » : « {champ} » doit être vrai ou faux.")
        f = t.get("fraicheur_min")
        if f is not None and (isinstance(f, bool) or not isinstance(f, (int, float)) or f <= 0):
            erreurs.append(f"Titulaire « {cle} » : « fraicheur_min » doit être un nombre de minutes.")
    if "decisions" in r and not _entier_positif(r["decisions"]):
        erreurs.append("« decisions » doit être un nombre entier positif ou nul.")
    if "file" not in r:
        return
    file = r["file"]
    if not _est_dict(file):
        erreurs.append("« file » doit être un objet.")
        return
    if "reste" in file and not _entier_positif(file["reste"]):
        erreurs.append("« file.reste » doit être un nombre entier positif ou nul.")
    visibles = file.get("visibles", [])
    if not isinstance(visibles, list):
        erreurs.append("« file.visibles » doit être une liste.")
        return
    for k, q in enumerate(visibles):
        if not _element_de_file(q):
            erreurs.append(f"« file.visibles » : l'élément {k + 1} doit avoir un « id » et un « titre » (textes).")


def _element_de_file(q):
    return _est_dict(q) and isinstance(q.get("id"), str) and bool(q.get("id")) and _texte_ou_nul(q.get("titre"))


def _verifier_file_v2(r, taches, erreurs):
    """`file.suite` (les éléments après les visibles) et l'unicité des identifiants de la file et des tâches."""
    file = r.get("file")
    if not _est_dict(file):
        return
    suite = file.get("suite")
    if suite is None:
        suite = []
    elif not isinstance(suite, list):
        erreurs.append("« file.suite » doit être une liste.")
        suite = []
    if len(suite) > MAX_SUITE:
        erreurs.append(f"« file.suite » : au plus {MAX_SUITE} éléments (il y en a {len(suite)}).")
    for k, q in enumerate(suite):
        if not _element_de_file(q):
            erreurs.append(f"« file.suite » : l'élément {k + 1} doit avoir un « id » et un « titre » (textes).")
    visibles = file.get("visibles")
    elements = (visibles if isinstance(visibles, list) else []) + suite
    vus = {t["id"] for t in taches if isinstance(t.get("id"), str)}
    for q in elements:
        if _element_de_file(q):
            if q["id"] in vus:
                erreurs.append(f"File : identifiant en double « {q['id']} » (entre visibles, suite et tâches).")
            vus.add(q["id"])


def _liste_facultative(v, champ, erreurs):
    """La liste de dicts d'un champ facultatif, ou [] (avec erreur) si le type est faux."""
    if v is None:
        return []
    if not isinstance(v, list):
        erreurs.append(f"{champ} doit être une liste.")
        return []
    ok = []
    for k, el in enumerate(v):
        if _est_dict(el):
            ok.append(el)
        else:
            erreurs.append(f"{champ} : l'élément {k + 1} doit être un objet.")
    return ok


def _texte(v):
    return isinstance(v, str)


def _verifier_v2(r, titulaires, taches, cles, erreurs):
    """Champs facultatifs de la version 2 (ignorés en version 1)."""
    _verifier_file_v2(r, taches, erreurs)
    for c in r.get("colonnes") or []:
        if _est_dict(c) and c.get("terminee") is not None and not isinstance(c["terminee"], bool):
            erreurs.append(f"Colonne « {c.get('id')} » : « terminee » doit être vrai ou faux.")
    vus = set()
    for a in _liste_facultative(r.get("actions"), "« actions »", erreurs):
        i = a.get("id")
        if not _texte(i) or not i:
            erreurs.append("« actions » : « id » est obligatoire (texte non vide).")
        elif i in vus:
            erreurs.append(f"« actions » : identifiant en double « {i} ».")
        if _texte(i):
            vus.add(i)
        if not _texte(a.get("libelle")):
            erreurs.append(f"« actions » : le bouton « {i} » doit avoir un « libelle » (texte).")
        if a.get("lien") is not None and not lien_valide(a["lien"]):
            erreurs.append(f"« actions » : le bouton « {i} » a un « lien » refusé (https, http ou claude).")
        if a.get("confirmer") is not None and not _texte(a["confirmer"]):
            erreurs.append(f"« actions » : le bouton « {i} » : « confirmer » doit être un texte.")
        if a.get("actif") is not None and not isinstance(a["actif"], bool):
            erreurs.append(f"« actions » : le bouton « {i} » : « actif » doit être vrai ou faux.")
    types = _liste_facultative(r.get("types"), "« types »", erreurs)
    ids_types = set()
    for t in types:
        if not _texte(t.get("id")) or not t.get("id") or not _texte(t.get("nom")):
            erreurs.append("« types » : chaque type a un « id » (non vide) et un « nom » (textes).")
        else:
            ids_types.add(t["id"])
    vus = set()
    for le in _liste_facultative(r.get("lecons"), "« lecons »", erreurs):
        i = le.get("id")
        if not _texte(i) or not i:
            erreurs.append("« lecons » : « id » est obligatoire (texte non vide).")
        elif i in vus:
            erreurs.append(f"« lecons » : identifiant en double « {i} ».")
        if _texte(i):
            vus.add(i)
        if not _dans(le.get("agent"), cles):
            erreurs.append(f"« lecons » : la leçon « {i} » vient d'un agent inconnu « {le.get('agent')} ».")
        if not _texte(le.get("texte")):
            erreurs.append(f"« lecons » : la leçon « {i} » doit avoir un « texte ».")
        for champ in ("tache", "date"):
            if not _texte_ou_nul(le.get(champ)):
                erreurs.append(f"« lecons » : la leçon « {i} » : « {champ} » doit être un texte.")
        if le.get("verdict_demande") not in (None, "valider", "invalider"):
            erreurs.append(f"« lecons » : la leçon « {i} » : « verdict_demande » doit valoir "
                           "« valider » ou « invalider ».")
    for ti in titulaires:
        cle = ti.get("cle")
        for champ in ("prenom", "specialite"):
            if ti.get(champ) is not None and not _texte(ti[champ]):
                erreurs.append(f"Titulaire « {cle} » : « {champ} » doit être un texte.")
        for le in _liste_facultative(ti.get("lecons"), f"Titulaire « {cle} » : « lecons »", erreurs):
            if not _texte(le.get("id")) or not _texte(le.get("texte")) \
                    or le.get("etat") not in ("à valider", "validée"):
                erreurs.append(f"Titulaire « {cle} » : « lecons » : chaque leçon a « id », « texte » "
                               "et « etat » (« à valider » ou « validée »).")
    for t in taches:
        i = t.get("id")
        if t.get("type") is not None:
            if not _texte(t["type"]):
                erreurs.append(f"Tâche « {i} » : « type » doit être un texte.")
            elif types and t["type"] not in ids_types:
                erreurs.append(f"Tâche « {i} » : type inconnu « {t['type']} ».")
        for champ in ("journal", "retours"):
            for e in _liste_facultative(t.get(champ), f"Tâche « {i} » : « {champ} »", erreurs):
                if not _texte(e.get("t")) or not _texte(e.get("texte")):
                    erreurs.append(f"Tâche « {i} » : « {champ} » : chaque élément a « t » et « texte » (textes).")
                if champ == "retours" and not _texte_ou_nul(e.get("reponse")):
                    erreurs.append(f"Tâche « {i} » : « retours » : « reponse » doit être un texte.")
                if champ == "retours" and not _texte_ou_nul(e.get("etat")):
                    erreurs.append(f"Tâche « {i} » : « retours » : « etat » doit être un texte.")
        for e in _liste_facultative(t.get("notes"), f"Tâche « {i} » : « notes »", erreurs):
            if not (_texte(e.get("libelle")) and e.get("libelle")) or not (_texte(e.get("texte")) and e.get("texte")):
                erreurs.append(f"Tâche « {i} » : « notes » : chaque note a un « libelle » et un « texte » "
                               "(textes non vides).")
        images = _liste_facultative(t.get("images"), f"Tâche « {i} » : « images »", erreurs)
        if len(images) > MAX_IMAGES:
            erreurs.append(f"Tâche « {i} » : « images » : au plus {MAX_IMAGES} images.")
        for e in images:
            if not _texte(e.get("chemin")) or not e.get("chemin") or not _texte_ou_nul(e.get("legende")):
                erreurs.append(f"Tâche « {i} » : « images » : chaque image a un « chemin » "
                               "(et une « legende » en texte).")
        for e in _liste_facultative(t.get("liens"), f"Tâche « {i} » : « liens »", erreurs):
            if not _texte(e.get("libelle")) or not lien_valide(e.get("url")):
                erreurs.append(f"Tâche « {i} » : « liens » : chaque lien a un « libelle » et une « url » "
                               "valide (https, http ou claude).")
        if not _texte_ou_nul(t.get("bloquee")):
            erreurs.append(f"Tâche « {i} » : « bloquee » doit être un texte.")


CHAMPS_V2_RACINE = ("actions", "types", "lecons")
CHAMPS_V2_TACHE = ("type", "journal", "images", "liens", "retours", "bloquee", "notes")
CHAMPS_V2_TITULAIRE = ("prenom", "specialite", "lecons")


def normaliser(r):
    """Applique les valeurs par défaut. Ne modifie pas l'argument."""
    n = copy.deepcopy(r)
    v2 = _version(n) >= 2
    if _version(n) >= 3:
        n["usage"] = [_usage_normalise(u) for u in n["usage"]] if isinstance(n.get("usage"), list) else []
    else:
        n.pop("usage", None)
    _normaliser_connaissances(n, _version(n) >= 3)
    for sv in n["services"]:
        if _version(n) >= 3 and isinstance(sv.get("kpi"), list):
            for k in sv["kpi"]:
                for champ in ("unite", "evolution", "texte", "periodes"):
                    k.setdefault(champ, None)
                k["alerte"] = k.get("alerte") is True
        else:
            sv.pop("kpi", None)
    for c in CHAMPS_V2_RACINE:
        if v2:
            n[c] = n[c] if isinstance(n.get(c), list) else []
        else:
            n.pop(c, None)
    for c in n["colonnes"]:
        if v2:
            c["terminee"] = c.get("terminee") is True
        else:
            c.pop("terminee", None)
    if not _est_dict(n.get("file")):
        n["file"] = {}
    n["file"].setdefault("visibles", [])
    n["file"].setdefault("reste", 0)
    if v2:
        n["file"]["suite"] = n["file"]["suite"] if isinstance(n["file"].get("suite"), list) else []
    else:
        n["file"].pop("suite", None)
    n.setdefault("decisions", 0)
    for t in n["taches"]:
        t.setdefault("titulaire", None)
        t.setdefault("postit", True)
        t.setdefault("etape", "")
        t.setdefault("maj", None)
        for c in CHAMPS_V2_TACHE:
            if not v2:
                t.pop(c, None)
            elif c in ("type", "bloquee"):
                t.setdefault(c, None)
            else:
                t[c] = t[c] if isinstance(t.get(c), list) else []
    for t in n["titulaires"]:
        if not v2:
            for c in CHAMPS_V2_TITULAIRE:
                t.pop(c, None)
        t.setdefault("modele", "?")
        t.setdefault("permanent", False)
        t.setdefault("chef", False)
    _normaliser_v4(n)
    if not any(t["chef"] for t in n["titulaires"]):
        n["titulaires"].append({"cle": "chef", "lieu": "local", "chef": True,
                                "permanent": True, "modele": "?"})
    return n


def _normaliser_connaissances(n, v3):
    """Une liste absente reste absente (elle masque l'onglet) ; une connaissance ou un challenge
    reçoit ses listes par défaut."""
    if v3 and isinstance(n.get("challenges"), list):
        for ch in n["challenges"]:
            ch["solutions"] = ch["solutions"] if isinstance(ch.get("solutions"), list) else []
            ch.setdefault("date", None)
            for so in ch["solutions"]:
                so.setdefault("etat", None)
    else:
        n.pop("challenges", None)
    for t in n["titulaires"]:
        if v3 and isinstance(t.get("connaissances"), list):
            for c in t["connaissances"]:
                c["appris_de"] = c["appris_de"] if isinstance(c.get("appris_de"), list) else []
                for champ in ("date", "origine"):
                    c.setdefault(champ, None)
        else:
            t.pop("connaissances", None)


def _usage_normalise(u):
    u.setdefault("tache", None)
    u.setdefault("agent", None)
    u.setdefault("etape", None)
    for champ in ("cache_lecture", "cache_ecriture"):
        if u.get(champ) is None:
            u[champ] = 0
    return u


def _tuer_arbre(p):
    """Tue la commande et tous ses descendants (ils peuvent garder sa sortie ouverte)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                           capture_output=True, timeout=5)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


def developper(arg):
    """Un argument qui commence par « ~/ » ou « ~ » + antislash est développé (dossier de l'utilisateur) ; les autres restent tels quels."""
    if isinstance(arg, str) and arg[:2] in ("~/", "~\\"):
        return os.path.expanduser(arg)
    return arg


PYTHONS = ("python", "python3")


def commande_python(cmd):
    """`python` ou `python3` en tête d'une commande désigne le Python qui fait tourner le bureau : le mot peut viser un
    autre Python sur la machine (une version trop ancienne, le raccourci du Microsoft Store). Le reste est inchangé."""
    cmd = list(cmd)
    if cmd and cmd[0] in PYTHONS and sys.executable:
        cmd[0] = sys.executable
    return cmd


def _executer(cmd, cwd, entree=None):
    """(code, sortie, erreurs) ; lève TimeoutExpired si la commande ou un de ses descendants
    tient au-delà de DELAI_COMMANDE_S. Ne bloque jamais plus longtemps que ce délai (+ quelques s).
    `entree` (octets) est écrit sur l'entrée standard de la commande ; sans lui, l'entrée est fermée."""
    cmd = commande_python(developper(a) for a in cmd)
    delai = DELAI_COMMANDE_S
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
               else {"start_new_session": True})
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL if entree is None else subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, **options)
    if entree is not None:
        def ecrire():  # dans un fil : un tube plein (commande qui ne lit pas) ne doit pas passer outre le délai
            try:
                p.stdin.write(entree)
                p.stdin.close()
            except (OSError, ValueError):  # la commande n'a pas lu son entrée et s'est déjà fermée
                pass
        threading.Thread(target=ecrire, daemon=True).start()
    lu = {}

    def lire(nom, flux):
        try:
            lu[nom] = flux.read()
        except (OSError, ValueError):
            lu[nom] = b""

    fils = [threading.Thread(target=lire, args=(n, f), daemon=True)
            for n, f in (("sortie", p.stdout), ("erreurs", p.stderr))]
    for f in fils:
        f.start()
    fin = time.monotonic() + delai
    try:
        p.wait(timeout=delai)
        for f in fils:
            f.join(max(0.0, fin - time.monotonic()))
        if any(f.is_alive() for f in fils):  # un descendant tient encore la sortie
            raise subprocess.TimeoutExpired(cmd, delai)
    except subprocess.TimeoutExpired:
        _tuer_arbre(p)
        raise
    finally:
        # Les tubes sont fermés dès que leur lecteur a fini ; fermer un tube encore lu par un fil bloquerait.
        for f, flux in zip(fils, (p.stdout, p.stderr)):
            if not f.is_alive():
                flux.close()
    return p.returncode, lu.get("sortie", b""), lu.get("erreurs", b"")


def _lire_texte(regl, source):
    base = Path(regl.get("dossier") or ".")
    if "fichier" in source:
        return (base / source["fichier"]).read_text(encoding="utf-8-sig")
    cmd = source["commande"]
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
        raise ValueError("« commande » doit être une liste de textes.")
    cwd = base / source.get("dossier", ".")
    code, sortie, erreurs = _executer(cmd, str(cwd))
    if code != 0:
        detail = erreurs.decode("utf-8", "replace").strip()[:200]
        raise ValueError(f"La commande du relevé a échoué (code {code}). {detail}".strip())
    return sortie.decode("utf-8-sig")


def obtenir(regl):
    """(relevé normalisé, None) ou (None, message). Ne lève jamais."""
    try:
        source = regl.get("releve") or {}
        if not _est_dict(source) or not ("fichier" in source or "commande" in source):
            return None, "Aucun relevé configuré : ajoutez « releve » aux réglages (voir docs/releve.md)."
        try:
            texte = _lire_texte(regl, source)
        except subprocess.TimeoutExpired:
            return None, f"La commande du relevé a dépassé {DELAI_COMMANDE_S} s."
        except FileNotFoundError as e:
            return None, f"Relevé introuvable : {e.filename or e}"
        except (OSError, ValueError) as e:
            return None, f"Relevé illisible : {e}"
        try:
            donnees = json.loads(texte)
        except ValueError as e:
            return None, f"Relevé illisible (JSON incomplet ou invalide) : {e}"
        erreurs = valider(donnees)
        if erreurs:
            return None, "Relevé invalide : " + " ".join(erreurs[:5])
        return normaliser(donnees), None
    except Exception as e:  # jamais d'exception vers l'appelant
        return None, f"Relevé inutilisable : {e}"
