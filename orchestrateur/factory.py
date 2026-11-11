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
        "flux", "seuil_methode", "catalogues", "sessions", "suivi", "pieces", "commandes", "memoire",
        "modele_orchestrateur", "agents_locaux_max")
MODELES_ORCHESTRATEUR = ("Haiku", "Sonnet", "Opus")   # jamais Fable ; Sonnet par défaut


class FactoryInvalide(Exception):
    pass


def _texte(v):
    return isinstance(v, str) and v.strip() != "" and "\x00" not in v


def _nom_du_projet(base):
    dossier = base.parent if base.name == ".factory" else base
    return dossier.name or "projet"


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
    flux = d.get("flux")
    if not isinstance(flux, list) or not flux:
        raise FactoryInvalide("Factory : « flux » doit lister au moins une étape {id, nom, role, service}.")
    vus = set()
    for e in flux:
        if not isinstance(e, dict) or not all(_texte(e.get(c)) for c in ("id", "nom", "role", "service")):
            raise FactoryInvalide("Factory : « flux » : chaque étape a un « id », un « nom », un « role » "
                                  "et un « service » (textes non vides).")
        if not MOTIF_ID.match(e["id"]) or e["id"] in RESERVES:
            raise FactoryInvalide(f"Factory : « flux » : identifiant d'étape refusé « {e['id']} » "
                                  f"(minuscules, chiffres et tirets ; ni « cadrage » ni « fait »).")
        if e["id"] in vus:
            raise FactoryInvalide(f"Factory : « flux » : identifiant d'étape en double « {e['id']} ».")
        vus.add(e["id"])
        if e["service"] not in ids_services:
            raise FactoryInvalide(f"Factory : « flux » : l'étape « {e['id']} » nomme un service inconnu "
                                  f"« {e['service']} ».")
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
    nom = d.get("nom")
    if nom is not None and not _texte(nom):
        raise FactoryInvalide("Factory : « nom » doit être un texte non vide.")
    return {
        "chemin": chemin.resolve(), "base": base,
        "nom": nom or _nom_du_projet(base),
        "skill": skill, "genre": genre, "mots_interdits": list(mots),
        "fiches": chem("fiches", "fiches"), "controles": chem("controles", "controles.md"),
        "consignes": chem("consignes", facultatif=True), "reglages": chem("reglages", facultatif=True),
        "services": [dict(s) for s in services], "flux": [dict(e) for e in flux], "seuil_methode": seuil,
        "catalogues": catalogues, "sessions": chem("sessions", "sessions.json"),
        "suivi": chem("suivi", "suivi.json"), "pieces": chem("pieces", "pieces"),
        "commandes": {k: list(v) for k, v in commandes.items()},
        "memoire": chem("memoire", str(Path(skill) / "orchestrateur" / "memoire")),
        "modele_orchestrateur": modele, "agents_locaux_max": locaux,
    }


def ecrire_genre(chemin, genre):
    """Note le genre dans le fichier de factory (le reste du fichier est gardé tel quel)."""
    chemin = Path(chemin)
    d = json.loads(chemin.read_text(encoding="utf-8-sig"))
    d["genre"] = genre
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
