"""Les demandes : ce que la page demande au projet. Le bureau ne fait que les vérifier et les remettre."""
import base64
import binascii
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
          "verdict_solution": ("challenge", "solution", "verdict"),
          "fonctionnalite": ("texte",), "message": ("fonctionnalite", "texte"),
          "cahier": ("fonctionnalite", "verdict"), "methode": ("fonctionnalite", "verdict"),
          "genre": ("decision", "genre"), "session_cloud": ("decision", "session"),
          "retour_element": ("fonctionnalite", "element", "texte"),
          "organisation": ("decision", "verdict"), "genre_fonctionnalite": ("decision", "fonctionnalite", "choix"),
          "environnement": ("decision", "fonctionnalite", "verdict"),
          "partenaire_regle": ("partenaire", "operation"), "partenaires_actualiser": (),
          "partenaires_maj": ("confirme",)}
FACULTATIFS = {"partenaire_regle": ("id", "texte"), "challenge": ("texte", "solution"), "fonctionnalite": ("images",), "message": ("images",),
               "cahier": ("texte",), "methode": ("texte",), "genre": ("description",), "lecon": ("etage",),
               "organisation": ("texte", "fable"), "genre_fonctionnalite": ("genre", "description", "projet_cree")}
DEMANDES_V4 = ("fonctionnalite", "message", "cahier", "methode", "genre", "session_cloud", "retour_element",
               "organisation", "genre_fonctionnalite", "environnement")
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


def _verifier_v4(demande, r, elements):
    genre = demande["type"]
    if genre in ("fonctionnalite", "message") and "images" in demande:
        message = verifier_images(demande["images"])
        if message:
            return message
    for champ in ("texte", "description", "projet_cree"):
        if (champ in demande and genre in ("cahier", "methode", "genre", "organisation", "genre_fonctionnalite")
                and not isinstance(demande[champ], str)):
            return f"« {champ} » doit être un texte."
    if genre == "fonctionnalite":
        return _texte_libre(demande["texte"], "texte")
    if genre == "genre":
        return _verifier_genre(demande, r)
    if genre == "session_cloud":
        if _decision(r.get("decisions_projet", []), demande["decision"], "session_cloud") is None:
            return "Décision inconnue."
        if not demande["session"].strip():
            return "Le nom de la session est vide."
        if len(demande["session"]) > MAX_SESSION:
            return f"Le nom de la session dépasse {MAX_SESSION} caractères."
        return None
    if genre == "genre_fonctionnalite":
        return _verifier_genre_fonctionnalite(demande, r)
    if genre == "environnement":
        f = _fonctionnalite(r, demande["fonctionnalite"])
        if f is None:
            return "Fonctionnalité inconnue."
        if _decision(f["decisions"], demande["decision"], "environnement") is None:
            return "Décision inconnue."
        return None if demande["verdict"] in ("fait", "continuer") else "Réponse inconnue (fait ou continuer)."
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
        if "description" not in demande or not demande["description"].strip():
            return "Un nouveau genre a besoin d'une description."
        if len(demande["description"]) > MAX_TEXTE:
            return f"« description » dépasse {MAX_TEXTE} caractères."
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
