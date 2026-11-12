"""Les demandes : ce que la page demande au projet. Le bureau ne fait que les vérifier et les remettre."""
import base64
import binascii
import json
import subprocess
from datetime import datetime
from pathlib import Path

from moteur import cloud

from . import releve

MAX_RETOUR = 3500
MAX_TEXTE = MAX_RETOUR
CHAMPS = {"bouton": ("id",), "deplacer": ("tache", "colonne"),
          "retour": ("tache", "texte"), "lecon": ("id", "verdict"),
          "challenge": ("cible",), "solution": ("challenge", "texte"),
          "verdict_solution": ("challenge", "solution", "verdict"),
          "fonctionnalite": ("texte",), "message": ("fonctionnalite", "texte"),
          "cahier": ("fonctionnalite", "verdict"), "methode": ("fonctionnalite", "verdict"),
          "genre": ("decision", "genre"), "session_cloud": ("decision", "session"),
          "retour_element": ("fonctionnalite", "element", "texte"),
          "organisation": ("decision", "verdict"), "genre_fonctionnalite": ("decision", "fonctionnalite", "choix"),
          "environnement": ("decision", "verdict"), "elargir_genre": ("decision", "verdict"),
          "valider_etape": ("decision", "verdict"), "outil_agent": ("decision", "verdict"), "accord_agent": ("decision", "verdict"),
          "partenaire_regle": ("partenaire", "operation"), "partenaires_actualiser": (),
          "partenaires_maj": ("confirme",), "installer_outil": ("decision", "outil"),
          "parallelisme": ("agents_locaux_max", "agents_cloud_max"),
          "recruter": ("mode", "agents"), "depot_git": ("confirme",)}
AGENTS_LOCAUX = (1, 16)      # les bornes de la factory (`orchestrateur/factory.py`)
AGENTS_CLOUD = (0, 16)
FACULTATIFS = {"partenaire_regle": ("id", "texte"), "challenge": ("texte", "solution"), "fonctionnalite": ("images",), "message": ("images",),
               "cahier": ("texte",), "methode": ("texte",), "genre": ("description",), "lecon": ("etage",),
               "organisation": ("texte", "fable", "installer"), "valider_etape": ("texte", "reponses"), "accord_agent": ("texte",), "environnement": ("fonctionnalite", "outil"),
               "installer_outil": ("fonctionnalite",), "elargir_genre": ("description",), "genre_fonctionnalite": ("genre", "description", "projet_cree")}
DEMANDES_V4 = ("fonctionnalite", "message", "cahier", "methode", "genre", "session_cloud", "retour_element",
               "organisation", "genre_fonctionnalite", "environnement", "elargir_genre", "valider_etape", "installer_outil",
               "parallelisme", "recruter", "depot_git", "outil_agent", "accord_agent")
VERDICTS_OUTIL = ("autoriser", "refuser", "relancer")     # « relancer » : la fiche a été complétée à la main
DEMANDES_PARTENAIRES = ("partenaire_regle", "partenaires_actualiser", "partenaires_maj")
MAX_REGLE = 500
OPERATIONS_REGLE = ("ajouter", "modifier", "supprimer")
MAX_IMAGES = releve.MAX_IMAGES_MESSAGE
MAX_OCTETS_IMAGE = 5 * 1024 * 1024
MAX_NOM_IMAGE = 80
MAX_SESSION = 200
SIGNATURES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
TYPES_CIBLE = ("kpi", "connaissance", "source", "lecon")   # « lecon » : version 4


def nettoyer(demande):
    """La demande réduite à ses champs connus (rien d'autre n'est transmis au projet)."""
    if not isinstance(demande, dict) or not isinstance(demande.get("type"), str) or demande["type"] not in CHAMPS:
        return demande
    genre = demande["type"]
    d = {k: demande[k] for k in ("type",) + CHAMPS[genre] + FACULTATIFS.get(genre, ()) if k in demande}
    if isinstance(d.get("cible"), dict):
        d["cible"] = {k: d["cible"][k] for k in ("type", "id") if k in d["cible"]}
    if genre == "valider_etape" and isinstance(d.get("reponses"), list):   # rien d'autre que le point et la réponse
        d["reponses"] = [{k: x[k] for k in ("point", "ok") if k in x} if isinstance(x, dict) else x
                         for x in d["reponses"]]
    if genre == "recruter" and isinstance(d.get("agents"), list):   # rien d'autre que le rôle, le modèle, le lieu
        d["agents"] = [{k: a[k] for k in ("role", "modele", "lieu", "fable") if k in a} if isinstance(a, dict) else a
                       for a in d["agents"]]
    if isinstance(d.get("images"), list):  # rien d'autre que le nom, le type et les données n'est transmis
        d["images"] = [{k: i[k] for k in ("nom", "type", "donnees") if k in i} if isinstance(i, dict) else i
                       for i in d["images"]]
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


def verifier_images(images):
    """Message d'erreur (français) ou None. Au plus 4 images, 5 Mo chacune une fois décodées,
    `{nom, type, donnees}` : `.png`, `.jpg` ou `.jpeg`, contenu vérifié par sa signature."""
    if not isinstance(images, list):
        return "« images » doit être une liste."
    if len(images) > MAX_IMAGES:
        return f"Au plus {MAX_IMAGES} images par demande."
    for k, im in enumerate(images, 1):
        quoi = f"Image {k}"
        if not isinstance(im, dict):
            return f"{quoi} : doit être un objet {{nom, type, donnees}}."
        nom, type_, donnees = im.get("nom"), im.get("type"), im.get("donnees")
        if (not isinstance(nom, str) or not nom or len(nom) > MAX_NOM_IMAGE or ".." in nom
                or any(c in nom for c in "/\\:") or any(ord(c) < 32 or ord(c) == 127 for c in nom)):
            return f"{quoi} : nom de fichier refusé (sans séparateur ni « .. », {MAX_NOM_IMAGE} caractères au plus)."
        extension = "." + nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
        if extension not in EXTENSIONS:
            return f"{quoi} : seules les images .png, .jpg et .jpeg sont acceptées."
        if type_ not in SIGNATURES or EXTENSIONS[extension] != type_:
            return f"{quoi} : type refusé (image/png pour .png, image/jpeg pour .jpg et .jpeg)."
        if not isinstance(donnees, str):
            return f"{quoi} : « donnees » doit être du texte base64."
        if len(donnees) > MAX_OCTETS_IMAGE * 4 // 3 + 4:
            return f"{quoi} : dépasse {MAX_OCTETS_IMAGE // (1024 * 1024)} Mo."
        try:
            octets = base64.b64decode(donnees, validate=True)
        except (binascii.Error, ValueError):
            return f"{quoi} : « donnees » n'est pas du base64 valide."
        if len(octets) > MAX_OCTETS_IMAGE:
            return f"{quoi} : dépasse {MAX_OCTETS_IMAGE // (1024 * 1024)} Mo."
        if not octets.startswith(SIGNATURES[type_]):
            return f"{quoi} : le contenu n'est pas une image {type_.split('/')[1].upper()}."
    return None


def verifier(demande, r, cibles_calculees=frozenset(), elements=None):
    """Message d'erreur (français) ou None. `r` : le dernier relevé normalisé valide.
    `cibles_calculees` : les identifiants des cibles que le bureau recalcule (KPI calculés, sources
    d'amélioration) ; un dict (id -> constat) convient aussi. `elements` : l'ensemble des identifiants
    du catalogue (pour `retour_element`), ou `None` si le catalogue n'est pas lisible."""
    if not isinstance(demande, dict):
        return "La demande doit être un objet."
    genre = demande.get("type")
    if not isinstance(genre, str) or genre not in CHAMPS:
        return "Type de demande inconnu."
    if genre in ("challenge", "solution", "verdict_solution"):
        return _verifier_challenge(demande, r, cibles_calculees)
    if genre in DEMANDES_PARTENAIRES:
        return _verifier_partenaires(demande, r)
    if r.get("version", 1) < 4 and (genre in DEMANDES_V4 or (genre == "lecon" and "etage" in demande)):
        return "Le relevé de ce projet ne gère pas cette demande (version 4)."
    if genre == "parallelisme":       # des nombres, pas des textes
        return _verifier_parallelisme(demande)
    if genre == "recruter":
        return _verifier_recrutement(demande, r)
    if genre == "depot_git":
        return _verifier_depot(demande, r)
    for champ in CHAMPS[genre]:
        if not isinstance(demande.get(champ), str):
            return f"« {champ} » est obligatoire (texte)."
    if genre in DEMANDES_V4:
        return _verifier_v4(demande, r, elements)
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
        if "etage" in demande:
            return _verifier_etage(demande, r)
    return None


def ids_partenaires(r):
    """Les identifiants des partenaires du catalogue que porte le relevé (vide sans espace partenaire)."""
    p = r.get("partenaires")
    if not isinstance(p, dict):
        return set()
    return {x["id"] for liste in (p.get("categories") or {}).values() for x in liste}


def _verifier_partenaires(demande, r):
    """Les demandes de l'espace partenaire (relevé version 4 avec `partenaires`). Le bureau n'agit pas : il les remet."""
    genre = demande["type"]
    if r.get("version", 1) < 4 or not isinstance(r.get("partenaires"), dict):
        return "Le relevé de ce projet n'a pas d'espace partenaire (version 4)."
    if genre == "partenaires_actualiser":
        return None
    if genre == "partenaires_maj":
        return None if demande.get("confirme") is True else "La mise à jour des offres demande une confirmation."
    i, operation = demande.get("partenaire"), demande.get("operation")
    if not isinstance(i, str) or i not in ids_partenaires(r):
        return "Partenaire inconnu."
    if not isinstance(operation, str) or operation not in OPERATIONS_REGLE:
        return "Opération inconnue (ajouter, modifier ou supprimer)."
    if operation != "ajouter":
        regles = ((r["partenaires"].get("etat") or {}).get("regles") or {}).get(i) or []
        if not isinstance(demande.get("id"), str) or demande["id"] not in {x.get("id") for x in regles}:
            return "Règle inconnue."
    if operation == "supprimer":
        return None
    texte = demande.get("texte")
    if not isinstance(texte, str) or not texte.strip():
        return "« texte » est obligatoire pour une règle."
    if len(texte) > MAX_REGLE:
        return f"La règle dépasse {MAX_REGLE} caractères."
    return None


def _verifier_etage(demande, r):
    etage = demande["etage"]
    if not isinstance(etage, str) or etage not in releve.ETAGES:
        return "Étage inconnu (projet, genre ou skill)."
    lecon = next(le for le in r.get("lecons", []) if le["id"] == demande["id"])
    if etage != "projet" and not (lecon.get("texte_general") or "").strip():
        return "Cette leçon n'a pas de texte général : elle ne peut rester qu'au projet."
    return None


def _fonctionnalite(r, i):
    return next((f for f in r.get("fonctionnalites", []) if f["id"] == i), None)


def _decision(decisions, i, genre):
    return next((d for d in decisions if d["id"] == i and d["genre"] == genre), None)


def _a_decision(f, genre):
    return any(d["genre"] == genre for d in f["decisions"])


def _verifier_parallelisme(demande):
    """Les places du projet : `agents_locaux_max` de 1 à 16, `agents_cloud_max` de 0 à 16 (entiers)."""
    for champ, (bas, haut) in (("agents_locaux_max", AGENTS_LOCAUX), ("agents_cloud_max", AGENTS_CLOUD)):
        v = demande.get(champ)
        if isinstance(v, bool) or not isinstance(v, int) or not bas <= v <= haut:
            return f"« {champ} » doit être un entier de {bas} à {haut}."
    return None


MODELES_RECRUE = ("Haiku", "Sonnet", "Opus")


def _verifier_recrutement(demande, r):
    """`recruter` contre le relevé : rôles du projet, modèle (Fable seulement avec la case d'accord, en manuel), lieu ;
    cloud seulement sur un projet GitHub et dans les places cloud sans agent ; auto jamais au-delà des places."""
    rec = r.get("recrutement")
    if not isinstance(rec, dict):
        return "Le relevé de ce projet ne permet pas encore de recruter (mettez à jour l'orchestrateur)."
    mode, agents = demande.get("mode"), demande.get("agents")
    if mode not in ("manuel", "auto"):
        return "« mode » vaut manuel ou auto."
    if not isinstance(agents, list) or not 1 <= len(agents) <= (1 if mode == "manuel" else 16):
        return "« agents » : un agent en manuel, de 1 à 16 en auto."
    roles = {x.get("role") for x in rec.get("roles") or [] if isinstance(x, dict)}
    for a in agents:
        if not isinstance(a, dict) or a.get("role") not in roles:
            return "Chaque agent a un « role » du workflow du projet."
        if "fable" in a and not isinstance(a["fable"], bool):
            return "« fable » vaut vrai ou faux."
        if a.get("modele") == "Fable":
            if a.get("fable") is not True or mode != "manuel":
                return "Fable demande votre accord (la case « J'accorde Fable »), en recrutement manuel."
        elif a.get("modele") not in MODELES_RECRUE:
            return "« modele » vaut Haiku, Sonnet ou Opus."
        if a.get("lieu") not in ("local", "cloud"):
            return "« lieu » vaut local ou cloud."
    places = rec.get("places") or {}
    n_cloud = sum(1 for a in agents if a["lieu"] == "cloud")
    if n_cloud and not (rec.get("depot") or {}).get("github"):
        return (rec.get("cloud_impossible") or "Le projet n'est pas sur GitHub.") + " Créez d'abord le dépôt Git."
    if n_cloud > places.get("cloud", 0):
        return "Pas assez de places cloud sans agent : augmentez « Agents cloud en même temps »."
    if mode == "auto" and len(agents) - n_cloud > places.get("locaux", 0):
        return "Pas assez de places locales sans agent : la répartition automatique ne les dépasse jamais."
    return None


def _verifier_depot(demande, r):
    """`depot_git` : le clic « Créer le dépôt Git » (`confirme` vrai) sur un projet qui n'est pas encore sur GitHub."""
    if demande.get("confirme") is not True:
        return "« confirme » doit être vrai : le dépôt n'est créé que sur votre clic."
    depot = (r.get("recrutement") or {}).get("depot")
    if not isinstance(depot, dict):
        return "Le relevé de ce projet ne permet pas encore de créer le dépôt (mettez à jour l'orchestrateur)."
    if depot.get("github"):
        return "Le projet est déjà sur GitHub."
    if not depot.get("creable"):
        return "Le dépôt a déjà une origine qui n'est pas sur GitHub : changez-la vous-même."
    return None


def _verifier_v4(demande, r, elements):
    genre = demande["type"]
    if genre in ("fonctionnalite", "message") and "images" in demande:
        message = verifier_images(demande["images"])
        if message:
            return message
    for champ in ("texte", "description", "projet_cree"):
        if (champ in demande and genre in ("cahier", "methode", "genre", "organisation", "genre_fonctionnalite",
                                           "elargir_genre", "valider_etape")
                and not isinstance(demande[champ], str)):
            return f"« {champ} » doit être un texte."
    if genre == "fonctionnalite":
        return _texte_libre(demande["texte"], "texte")
    if genre == "genre":
        return _verifier_genre(demande, r)
    if genre == "session_cloud":
        d = _decision(r.get("decisions_projet", []), demande["decision"], "session_cloud")
        if d is None:
            return "Décision inconnue."
        if not demande["session"].strip():
            return "Le nom de la session est vide."
        if len(demande["session"]) > MAX_SESSION:
            return f"Le nom de la session dépasse {MAX_SESSION} caractères."
        if d.get("tache") and cloud.lire_session(demande["session"]) is None:   # la démarche simplifiée
            return ("Collez l'adresse de la session (https://claude.ai/code/…) ou son identifiant (session_…).")
        return None
    if genre == "genre_fonctionnalite":
        return _verifier_genre_fonctionnalite(demande, r)
    if genre == "elargir_genre":
        if _decision(r.get("decisions_projet", []), demande["decision"], "elargir_genre") is None:
            return "Décision inconnue."
        if demande["verdict"] not in ("valider", "refuser"):
            return "Réponse inconnue (valider ou refuser)."
        if demande.get("description") and len(demande["description"]) > MAX_TEXTE:
            return f"« description » dépasse {MAX_TEXTE} caractères."
        return None
    if genre == "outil_agent":
        d = _decision(r.get("decisions_projet", []), demande["decision"], "outil_agent")
        if d is None:
            return "Décision inconnue."
        if demande["verdict"] not in VERDICTS_OUTIL:
            return f"Réponse inconnue ({', '.join(VERDICTS_OUTIL)})."
        if demande["verdict"] == "autoriser" and not d.get("programme"):
            return "Cette décision ne nomme pas de programme à autoriser."
        return None
    if genre == "accord_agent":
        if _decision(r.get("decisions_projet", []), demande["decision"], "accord_agent") is None:
            return "Décision inconnue."
        if demande["verdict"] not in ("accepter", "refuser"):
            return "Réponse inconnue (accepter ou refuser)."
        if len(demande.get("texte") or "") > MAX_TEXTE:
            return f"« texte » dépasse {MAX_TEXTE} caractères."
        return None
    if genre == "valider_etape":
        d = _decision(r.get("decisions_projet", []), demande["decision"], "valider_etape")
        if d is None:
            return "Décision inconnue."
        if demande["verdict"] not in ("valider", "renvoyer"):
            return "Réponse inconnue (valider ou renvoyer)."
        remarque = demande.get("texte")
        if "reponses" in demande:      # la fenêtre de validation : une réponse par point, le texte libre facultatif
            return _verifier_reponses(demande, d)
        if demande["verdict"] == "renvoyer":
            if remarque is None or not isinstance(remarque, str) or not remarque.strip():
                return "Pour renvoyer l'élément, dites ce qu'il faut changer (une remarque est obligatoire)."
            return _texte_libre(remarque, "texte")
        if remarque is not None and len(remarque) > MAX_TEXTE:
            return f"« texte » dépasse {MAX_TEXTE} caractères."
        return None
    if genre == "environnement":
        if demande.get("fonctionnalite") is None:      # l'installation portée par le projet : décision de projet
            decisions = r.get("decisions_projet", [])
        else:
            f = _fonctionnalite(r, demande["fonctionnalite"])
            if f is None:
                return "Fonctionnalité inconnue."
            decisions = f["decisions"]
        d = _decision(decisions, demande["decision"], "environnement")
        if d is None:
            return "Décision inconnue."
        if demande["verdict"] not in ("fait", "continuer", "forcer"):
            return "Réponse inconnue (fait, continuer ou forcer)."
        if "outil" in demande and demande["verdict"] != "forcer":
            return "« outil » ne va qu'avec « forcer »."
        if demande["verdict"] == "forcer":
            outils = [o for o in d.get("environnement") or [] if isinstance(o, dict) and o.get("etat") != "en_place"]
            if "outil" in demande:
                if not isinstance(demande["outil"], str) or not any(o.get("outil") == demande["outil"] for o in outils):
                    return "Cet outil n'est pas dans la liste de ceux qui ne sont pas trouvés."
            elif not outils:
                return "Tous les outils sont déjà trouvés : rien à forcer."
        return None
    if genre == "installer_outil":
        return _verifier_installer_outil(demande, r)
    if genre == "organisation":
        d = _decision(r.get("decisions_projet", []), demande["decision"], "organisation")
        if d is None:
            return "Décision inconnue."
        if demande["verdict"] not in ("accepter", "refuser", "abandonner"):
            return "Verdict inconnu (accepter, refuser ou abandonner)."
        if demande["verdict"] == "abandonner" and not (d.get("organisation") or {}).get("workflow"):
            return "On n'abandonne que la proposition de workflow d'une demande."
        if "texte" in demande:
            message = _texte_libre(demande["texte"], "texte")
            if message:
                return message
        if "fable" in demande:
            proposes = {a.get("cle") for a in (d.get("organisation") or {}).get("agents") or []
                        if a.get("fable_suggere") is True}
            fable = demande["fable"]
            if not isinstance(fable, list) or not all(isinstance(c, str) for c in fable):
                return "« fable » doit être la liste des clés d'agents."
            if demande["verdict"] != "accepter" and fable:
                return "Fable ne se coche qu'avec l'acceptation."
            if any(c not in proposes for c in fable):
                return "Fable n'a pas été suggéré pour cet agent."
        if "installer" in demande:
            installer = demande["installer"]
            if not isinstance(installer, list) or not all(isinstance(c, str) and c.strip() for c in installer):
                return "« installer » doit être la liste des noms d'outils à installer en autonomie."
            if demande["verdict"] != "accepter" and installer:
                return "L'installation en autonomie ne se choisit qu'avec l'acceptation."
            autonomes = {x.get("outil") for x in (d.get("organisation") or {}).get("environnement") or []
                         if isinstance(x, dict) and x.get("autonome") is True and x.get("etat") != "en_place"}
            if any(c not in autonomes for c in installer):
                return "Cet outil ne s'installe pas en autonomie (ou il est déjà en place)."
        return None
    f = _fonctionnalite(r, demande["fonctionnalite"])
    if f is None:
        return "Fonctionnalité inconnue."
    if genre == "message":
        return _texte_libre(demande["texte"], "texte")
    if genre == "retour_element":
        if not f.get("catalogue"):
            return "Cette fonctionnalité n'a pas de catalogue."
        if elements is None:
            return "Catalogue indisponible."
        if demande["element"] not in elements:
            return "Élément inconnu."
        return _texte_libre(demande["texte"], "texte")
    verdict = demande["verdict"]
    texte = demande.get("texte")
    if texte is not None and len(texte) > MAX_TEXTE:
        return f"« texte » dépasse {MAX_TEXTE} caractères."
    if genre == "cahier":
        if verdict == "valider":
            return None if _a_decision(f, "valider_cahier") else "Aucun cahier des charges à valider."
        if verdict == "corriger":
            return _texte_libre(texte, "texte") if texte is not None else "« texte » est obligatoire pour corriger."
        return "Verdict inconnu (valider ou corriger)."
    if verdict == "valider":  # méthode
        return None if _a_decision(f, "valider_methode") else "Aucune méthode à valider."
    if verdict == "garder":
        return None if _a_decision(f, "methode_a_revoir") else "Aucune question « méthode à revoir ? » en attente."
    if verdict == "revoir":
        if f["etape"] in ("methode", "serie") or _a_decision(f, "methode_a_revoir") or _a_decision(f, "reprendre_methode"):
            return None
        return "Cette fonctionnalité n'a pas encore de méthode à revoir."
    if verdict in ("reprendre", "adapter"):   # une méthode déjà validée ailleurs, proposée d'emblée
        if not _a_decision(f, "reprendre_methode"):
            return "Aucune méthode existante n'est proposée pour cette fonctionnalité."
        if verdict == "adapter":
            return _texte_libre(texte, "texte") if texte is not None else "« texte » est obligatoire pour adapter."
        return None
    return "Verdict inconnu (valider, revoir, garder, reprendre ou adapter)."


def _verifier_genre(demande, r):
    d = _decision(r.get("decisions_projet", []), demande["decision"], "confirmer_genre")
    if d is None:
        return "Décision inconnue."
    genre = demande["genre"]
    if not releve.MOTIF_GENRE.match(genre):
        return "Identifiant de genre refusé (minuscules, chiffres et tirets, 40 caractères au plus)."
    if genre not in (d.get("genres_connus") or []):
        propose = genre == d.get("propose") and (d.get("description") or "").strip()    # la phrase déjà rédigée
        if not propose and ("description" not in demande or not demande["description"].strip()):
            return "Un nouveau genre a besoin d'une description."
        if len(demande.get("description", "")) > MAX_TEXTE:
            return f"« description » dépasse {MAX_TEXTE} caractères."
    return None


def _verifier_installer_outil(demande, r):
    """« Installer en autonomie » : l'outil est dans la décision `environnement` (de la fonctionnalité, ou du projet
    sans `fonctionnalite`), encore à installer, sans installation en cours, et marqué `autonome`."""
    if demande.get("fonctionnalite") is None:
        decisions = r.get("decisions_projet", [])
    else:
        f = _fonctionnalite(r, demande["fonctionnalite"])
        if f is None:
            return "Fonctionnalité inconnue."
        decisions = f["decisions"]
    d = _decision(decisions, demande["decision"], "environnement")
    if d is None:
        return "Décision inconnue."
    if not isinstance(demande["outil"], str) or not demande["outil"].strip():
        return "« outil » doit être le nom d'un outil de la liste."
    x = next((o for o in d.get("environnement") or [] if isinstance(o, dict) and o.get("outil") == demande["outil"]), None)
    if x is None:
        return "Outil inconnu dans cette décision."
    if x.get("autonome") is not True:
        return "Cet outil ne s'installe pas en autonomie : suivez le lien et le mode opératoire."
    if x.get("en_cours") is True:
        return "L'installation de cet outil est déjà en cours."
    return None


def _verifier_genre_fonctionnalite(demande, r):
    """La réponse à « cette demande n'est pas du genre du projet » : ici, même genre (si le moteur hésitait), nouveau
    projet (avec le chemin des réglages du projet créé)."""
    f = _fonctionnalite(r, demande["fonctionnalite"])
    if f is None:
        return "Fonctionnalité inconnue."
    d = _decision(f["decisions"], demande["decision"], "genre_fonctionnalite")
    if d is None:
        return "Décision inconnue."
    choix = demande["choix"]
    if choix not in ("ici", "meme", "nouveau_projet"):
        return "Choix inconnu (ici, meme ou nouveau_projet)."
    if choix == "meme" and not d.get("incertain"):
        return "Le moteur n'hésite pas sur le genre de cette demande : choisissez « ici » ou « nouveau_projet »."
    if "genre" in demande:
        if not releve.MOTIF_GENRE.match(demande["genre"]):
            return "Identifiant de genre refusé (minuscules, chiffres et tirets, 40 caractères au plus)."
        connus = d.get("genres_connus") or []
        if demande["genre"] not in connus and not (demande.get("description") or "").strip() and not (
                (d.get("nouveau") or {}).get("id") == demande["genre"]):
            return "Un nouveau genre a besoin d'une description."
    if "description" in demande and len(demande["description"]) > MAX_TEXTE:
        return f"« description » dépasse {MAX_TEXTE} caractères."
    if choix == "nouveau_projet" and not (demande.get("projet_cree") or "").strip():
        return "Le nouveau projet n'est pas indiqué."
    return None


def _verifier_reponses(demande, d):
    """Les réponses de la fenêtre de validation : exactement une par point de la décision (un seul point pour une
    décision d'avant), chacune OK ou à revoir ; le verdict en découle ; le texte libre est facultatif."""
    reponses = demande["reponses"]
    if (not isinstance(reponses, list) or not all(isinstance(x, dict) and set(x) == {"point", "ok"}
                                                  and isinstance(x["point"], str) and isinstance(x["ok"], bool)
                                                  for x in reponses)):
        return "« reponses » : une réponse {point, ok} par point à vérifier."
    if sorted(x["point"].strip() for x in reponses) != sorted(releve.points_de_decision(d)):
        return "Répondez à chaque point à vérifier de cette validation (OK ou À revoir), et à eux seuls."
    attendu = "valider" if all(x["ok"] for x in reponses) else "renvoyer"
    if demande["verdict"] != attendu:
        return f"Le verdict doit être « {attendu} » : il découle des réponses point par point."
    texte = demande.get("texte")
    if texte is not None and len(texte) > MAX_TEXTE:
        return f"« texte » dépasse {MAX_TEXTE} caractères."
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
            return "Type de cible inconnu (kpi, connaissance, source ou lecon)."
        if cible["type"] == "lecon":   # une leçon, même à valider, se discute avant le verdict (version 4)
            if r.get("version", 1) < 4:
                return "Le relevé de ce projet ne permet pas de challenger une leçon (version 4)."
            if not isinstance(demande.get("texte"), str) or not demande["texte"].strip():
                return "Dites ce que vous contestez dans la leçon."
        for champ in ("texte", "solution"):
            if champ in demande:
                message = _texte_libre(demande[champ], champ)
                if message:
                    return message
        genre_cible, i = cible["type"], cible["id"]
        if genre_cible == "connaissance":
            connue = i in connaissances_du_releve(r)
        elif genre_cible == "lecon":
            connue = i in {le.get("id") for le in r.get("lecons") or []} | {
                le.get("id") for ti in r.get("titulaires", []) for le in ti.get("lecons") or []}
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
