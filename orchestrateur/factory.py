"""Le fichier de factory d'un projet : lecture, contrôle, normalisation.

Un fichier JSON versionné dans le dépôt du projet. Tous les chemins qu'il contient sont relatifs à lui.
"""
import json
import os
import re
import tempfile
from pathlib import Path

MOTIF_GENRE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")
MOTIF_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")
RESERVES = ("cadrage", "fait")   # colonnes que l'orchestrateur ajoute lui-même
CLES = ("nom", "skill", "genre", "mots_interdits", "fiches", "controles", "consignes", "reglages", "services",
        "flux", "workflows", "description", "seuil_methode", "catalogues", "sessions", "suivi", "pieces", "commandes", "memoire",
        "modele_orchestrateur", "agents_locaux_max", "agents_cloud_max", "environnement")
AGENTS_LOCAUX = (1, 16)     # les places locales d'un projet (2 par défaut)
AGENTS_CLOUD = (0, 16)      # les places cloud d'un projet (0 par défaut ; absent : voir `depart.places_cloud`)
MODELES_ORCHESTRATEUR = ("Haiku", "Sonnet", "Opus")   # jamais Fable ; Sonnet par défaut


class FactoryInvalide(Exception):
    pass


def _texte(v):
    return isinstance(v, str) and v.strip() != "" and "\x00" not in v


def _nom_du_projet(base):
    dossier = base.parent if base.name == ".factory" else base
    return dossier.name or "projet"


def _controler_flux(flux, nom, ids_services, vus):
    """Contrôle les étapes `{id, nom, role, service}` d'un flux, ou `{id, nom, validation: true}` (validation du
    Directeur, ni première, ni dernière, ni deux de suite) ; `vus` : les identifiants déjà pris dans le projet."""
    for e in flux:
        if isinstance(e, dict) and e.get("validation") is True:
            if not all(_texte(e.get(c)) for c in ("id", "nom")) or "role" in e or "service" in e:
                raise FactoryInvalide(f"Factory : « {nom} » : une étape de validation a un « id » et un « nom » "
                                      "(textes non vides), sans « role » ni « service ».")
        elif not isinstance(e, dict) or not all(_texte(e.get(c)) for c in ("id", "nom", "role", "service")):
            raise FactoryInvalide(f"Factory : « {nom} » : chaque étape a un « id », un « nom », un « role » "
                                  "et un « service » (textes non vides).")
        if not MOTIF_ID.match(e["id"]) or e["id"] in RESERVES:
            raise FactoryInvalide(f"Factory : « {nom} » : identifiant d'étape refusé « {e['id']} » "
                                  f"(minuscules, chiffres et tirets ; ni « cadrage » ni « fait »).")
        if e["id"] in vus:
            raise FactoryInvalide(f"Factory : « {nom} » : identifiant d'étape en double « {e['id']} ».")
        vus.add(e["id"])
        if e.get("validation") is not True and e["service"] not in ids_services:
            raise FactoryInvalide(f"Factory : « {nom} » : l'étape « {e['id']} » nomme un service inconnu "
                                  f"« {e['service']} ».")
    est_val = [isinstance(e, dict) and e.get("validation") is True for e in flux]
    if est_val and est_val[0]:
        raise FactoryInvalide(f"Factory : « {nom} » : une étape de validation ne peut pas être la première.")
    if est_val and est_val[-1]:
        raise FactoryInvalide(f"Factory : « {nom} » : une étape de validation ne peut pas être la dernière.")
    if any(a and b for a, b in zip(est_val, est_val[1:])):
        raise FactoryInvalide(f"Factory : « {nom} » : deux étapes de validation de suite sont refusées.")


def lire(chemin):
    """Le fichier de factory, contrôlé : un dict dont les chemins sont des `Path` absolus."""
    chemin = Path(chemin)
    try:
        d = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise FactoryInvalide(f"Fichier de factory illisible ({chemin}) : {e}")
    if not isinstance(d, dict):
        raise FactoryInvalide(f"Fichier de factory illisible ({chemin}) : un objet JSON est attendu.")
    base = chemin.resolve().parent

    def chem(cle, defaut=None, facultatif=False):
        v = d.get(cle)
        if v is None:
            if defaut is None:
                if facultatif:
                    return None
                raise FactoryInvalide(f"Factory : « {cle} » est obligatoire (chemin).")
            v = defaut
        if not _texte(v):
            raise FactoryInvalide(f"Factory : « {cle} » doit être un chemin (texte non vide).")
        if v[:2] in ("~/", "~\\"):   # le dossier de l'utilisateur ; « ~x » ou « a~b » restent relatifs
            return Path(os.path.expanduser(v)).resolve()
        return (base / v).resolve()

    skill = chem("skill")
    genre = d.get("genre")
    if genre is not None and not (isinstance(genre, str) and MOTIF_GENRE.match(genre)):
        raise FactoryInvalide("Factory : « genre » doit être nul ou un identifiant de genre "
                              "(minuscules, chiffres et tirets, 40 caractères au plus).")
    mots = d.get("mots_interdits", [])
    if not isinstance(mots, list) or not all(_texte(m) for m in mots):
        raise FactoryInvalide("Factory : « mots_interdits » doit être une liste de textes non vides.")
    services = d.get("services", [])
    if (not isinstance(services, list) or not all(isinstance(s, dict) and _texte(s.get("id")) and _texte(s.get("nom"))
                                                  for s in services)):
        raise FactoryInvalide("Factory : « services » doit être une liste de {id, nom}.")
    ids_services = [s["id"] for s in services]
    if len(ids_services) != len(set(ids_services)):
        raise FactoryInvalide("Factory : « services » : identifiant en double.")
    vus = set()   # les identifiants d'étape sont uniques dans tout le projet (flux et workflows)
    flux = d.get("flux")
    if flux is None:
        flux = []   # un projet créé sans workflow est valide : sa première demande en propose un
    if not isinstance(flux, list):
        raise FactoryInvalide("Factory : « flux » doit lister des étapes {id, nom, role, service} (ou rester vide).")
    _controler_flux(flux, "flux", ids_services, vus)
    workflows = d.get("workflows")
    if workflows is None:
        workflows = []
    if not isinstance(workflows, list):
        raise FactoryInvalide("Factory : « workflows » doit être une liste de {id, fonctionnalite, genre, flux}.")
    ids_workflows = {"principal"}
    for w in workflows:
        if not isinstance(w, dict) or not _texte(w.get("id")) or not MOTIF_ID.match(w["id"]):
            raise FactoryInvalide("Factory : « workflows » : chaque workflow a un « id » "
                                  "(minuscules, chiffres et tirets, 40 caractères au plus).")
        if w["id"] in ids_workflows:
            raise FactoryInvalide(f"Factory : « workflows » : identifiant de workflow en double ou réservé « {w['id']} ».")
        ids_workflows.add(w["id"])
        if w.get("fonctionnalite") is not None and not _texte(w["fonctionnalite"]):
            raise FactoryInvalide(f"Factory : le workflow « {w['id']} » : « fonctionnalite » est un identifiant ou nul.")
        if w.get("genre") is not None and not (isinstance(w["genre"], str) and MOTIF_GENRE.match(w["genre"])):
            raise FactoryInvalide(f"Factory : le workflow « {w['id']} » : « genre » doit être nul ou un identifiant "
                                  f"de genre.")
        if not isinstance(w.get("flux"), list):
            raise FactoryInvalide(f"Factory : le workflow « {w['id']} » : « flux » doit lister des étapes.")
        _controler_flux(w["flux"], f"workflows « {w['id']} »", ids_services, vus)
    description = d.get("description")
    if description is not None and not _texte(description):
        raise FactoryInvalide("Factory : « description » doit être un texte non vide.")
    seuil = d.get("seuil_methode", 3)
    if isinstance(seuil, bool) or not isinstance(seuil, int) or seuil < 1:
        raise FactoryInvalide("Factory : « seuil_methode » doit être un entier d'au moins 1.")
    catalogues = d.get("catalogues", {})
    if not isinstance(catalogues, dict) or not all(isinstance(v, dict) for v in catalogues.values()):
        raise FactoryInvalide("Factory : « catalogues » doit associer à chaque fonctionnalité {fichier | commande}.")
    commandes = d.get("commandes", {})
    if not isinstance(commandes, dict) or not all(
            isinstance(v, list) and v and all(_texte(a) for a in v) for v in commandes.values()):
        raise FactoryInvalide("Factory : « commandes » doit associer à chaque commande une liste d'arguments.")
    modele = d.get("modele_orchestrateur", "Sonnet")
    if modele not in MODELES_ORCHESTRATEUR:
        raise FactoryInvalide("Factory : « modele_orchestrateur » doit valoir Haiku, Sonnet ou Opus (Sonnet par défaut).")
    locaux = d.get("agents_locaux_max", 2)
    if isinstance(locaux, bool) or not isinstance(locaux, int) or not 1 <= locaux <= 16:
        raise FactoryInvalide("Factory : « agents_locaux_max » doit être un entier de 1 à 16 (2 par défaut).")
    cloud = d.get("agents_cloud_max")
    if cloud is not None and not _entier_borne(cloud, AGENTS_CLOUD):
        raise FactoryInvalide("Factory : « agents_cloud_max » doit être un entier de 0 à 16 (0 par défaut).")
    environnement = d.get("environnement", [])
    if not isinstance(environnement, list) or not all(isinstance(x, dict) and _texte(x.get("outil"))
                                                      for x in environnement):
        raise FactoryInvalide("Factory : « environnement » doit être une liste d'outils {outil, etat, chemin?, version?}.")
    nom = d.get("nom")
    if nom is not None and not _texte(nom):
        raise FactoryInvalide("Factory : « nom » doit être un texte non vide.")
    return {
        "chemin": chemin.resolve(), "base": base,
        "nom": nom or _nom_du_projet(base),
        "skill": skill, "genre": genre, "mots_interdits": list(mots),
        "fiches": chem("fiches", "fiches"), "controles": chem("controles", "controles.md"),
        "consignes": chem("consignes", facultatif=True), "reglages": chem("reglages", facultatif=True),
        "services": [dict(s) for s in services], "flux": [dict(e) for e in flux],
        "workflows": [{"id": w["id"], "fonctionnalite": w.get("fonctionnalite"), "genre": w.get("genre"),
                       "flux": [dict(e) for e in w["flux"]]} for w in workflows],
        "description": description, "seuil_methode": seuil,
        "catalogues": catalogues, "sessions": chem("sessions", "sessions.json"),
        "suivi": chem("suivi", "suivi.json"), "pieces": chem("pieces", "pieces"),
        "commandes": {k: list(v) for k, v in commandes.items()},
        "memoire": chem("memoire", str(Path(skill) / "orchestrateur" / "memoire")),
        "modele_orchestrateur": modele, "agents_locaux_max": locaux, "agents_cloud_max": cloud,
        "environnement": [dict(x) for x in environnement],
    }


def _entier_borne(v, bornes):
    return isinstance(v, int) and not isinstance(v, bool) and bornes[0] <= v <= bornes[1]


def ecrire_genre(chemin, genre):
    """Note le genre dans le fichier de factory (le reste du fichier est gardé tel quel)."""
    _ecrire_cles(chemin, {"genre": genre})


def ecrire_parallelisme(chemin, locaux, cloud):
    """Note les places du projet (`agents_locaux_max` 1 à 16, `agents_cloud_max` 0 à 16) ; le reste est gardé."""
    if not _entier_borne(locaux, AGENTS_LOCAUX):
        raise FactoryInvalide("« agents_locaux_max » doit être un entier de 1 à 16.")
    if not _entier_borne(cloud, AGENTS_CLOUD):
        raise FactoryInvalide("« agents_cloud_max » doit être un entier de 0 à 16.")
    _ecrire_cles(chemin, {"agents_locaux_max": locaux, "agents_cloud_max": cloud})


def _ecrire_cles(chemin, cles):
    chemin = Path(chemin)
    d = json.loads(chemin.read_text(encoding="utf-8-sig"))
    d.update(cles)
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
