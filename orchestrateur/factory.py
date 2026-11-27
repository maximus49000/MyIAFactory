"""Le fichier de factory d'un projet : lecture, contrôle, normalisation.

Un fichier JSON versionné dans le dépôt du projet. Tous les chemins qu'il contient sont relatifs à lui.
"""
import copy
import json
import os
import re
import tempfile
import time
from pathlib import Path

MOTIF_GENRE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")
MOTIF_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")
RESERVES = ("cadrage", "fait")   # colonnes que l'orchestrateur ajoute lui-même
CLES = ("nom", "skill", "genre", "mots_interdits", "fiches", "controles", "consignes", "reglages", "services",
        "flux", "workflows", "description", "seuil_methode", "catalogues", "sessions", "suivi", "pieces", "commandes", "memoire",
        "modele_orchestrateur", "agents_locaux_max", "agents_cloud_max", "agents_serveur_max", "ordre_lieux",
        "ordre_lieux_par_metier", "environnement", "apk_ignore", "apk_adresse_integree", "liens_publics")
AGENTS_LOCAUX = (1, 16)     # les places locales d'un projet (2 par défaut)
AGENTS_CLOUD = (0, 16)      # les places cloud d'un projet (0 par défaut ; absent : voir `depart.places_cloud`)
AGENTS_SERVEUR = (0, 4)     # les places serveur d'un projet (0 par défaut)
MAX_ORDRES_PAR_METIER = 50   # au plus 50 rôles ont leur propre ordre de lieux
LIEUX_D_AGENT = ("serveur", "local", "cloud")   # l'ordre des lieux d'un projet en est une permutation non vide
MODELES_ORCHESTRATEUR = ("Haiku", "Sonnet", "Opus")   # jamais Fable ; Sonnet par défaut
# Le modèle nécessaire d'une étape. Fable n'y est qu'une proposition : la tâche ne part sur Fable qu'avec l'accord du
# Directeur, demandé avant son départ (décision `fable_tache`) ; sans accord, Opus.
MODELES_D_ETAPE = ("Haiku", "Sonnet", "Opus", "Fable")
# Le lieu d'une étape d'agent : `local` (exige le poste) ou `indifférent` (cloud possible) ; absent : celui du métier.
LIEUX_D_ETAPE = ("local", "indifférent", "cloud")
# Le regroupement d'une étape d'agent : `parallele` (par défaut) ou `regroupe` (un seul agent enchaîne ses tâches).
REGROUPEMENTS_D_ETAPE = ("parallele", "regroupe")


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
        if "lieu" in e and (e.get("validation") is True or e["lieu"] not in LIEUX_D_ETAPE):
            raise FactoryInvalide(f"Factory : « {nom} » : l'étape « {e['id']} » : « lieu » vaut "
                                  f"{' ou '.join(LIEUX_D_ETAPE)}, jamais sur une étape de validation.")
        if "regroupement" in e and (e.get("validation") is True or e["regroupement"] not in REGROUPEMENTS_D_ETAPE):
            raise FactoryInvalide(f"Factory : « {nom} » : l'étape « {e['id']} » : « regroupement » vaut "
                                  f"{' ou '.join(REGROUPEMENTS_D_ETAPE)}, jamais sur une étape de validation.")
        if not MOTIF_ID.match(e["id"]) or e["id"] in RESERVES:
            raise FactoryInvalide(f"Factory : « {nom} » : identifiant d'étape refusé « {e['id']} » "
                                  f"(minuscules, chiffres et tirets ; ni « cadrage » ni « fait »).")
        if e["id"] in vus:
            raise FactoryInvalide(f"Factory : « {nom} » : identifiant d'étape en double « {e['id']} ».")
        vus.add(e["id"])
        if e.get("validation") is not True and e["service"] not in ids_services:
            raise FactoryInvalide(f"Factory : « {nom} » : l'étape « {e['id']} » nomme un service inconnu "
                                  f"« {e['service']} ».")
        # le modèle nécessaire de l'étape (facultatif : sinon déduit de sa nature) ; Fable : une proposition seulement
        if "modele" in e and e["modele"] not in MODELES_D_ETAPE or (
                "justification" in e and "modele" in e and not isinstance(e["justification"], str)):
            raise FactoryInvalide(f"Factory : « {nom} » : l'étape « {e['id']} » : « modele » vaut "
                                  f"{', '.join(MODELES_D_ETAPE)} (Fable sur l'accord du Directeur), avec sa "
                                  "« justification » en texte.")
    est_val = [isinstance(e, dict) and e.get("validation") is True for e in flux]
    if est_val and est_val[0]:
        raise FactoryInvalide(f"Factory : « {nom} » : une étape de validation ne peut pas être la première.")
    if est_val and est_val[-1]:
        raise FactoryInvalide(f"Factory : « {nom} » : une étape de validation ne peut pas être la dernière.")
    if any(a and b for a, b in zip(est_val, est_val[1:])):
        raise FactoryInvalide(f"Factory : « {nom} » : deux étapes de validation de suite sont refusées.")


_CACHE = {}
_CACHE_MAX = 64
# Une date de modification plus proche que cela de l'heure courante ne prouve pas que le fichier n'a pas changé : deux
# écritures de même taille dans le même grain d'horloge du système de fichiers (quelques millisecondes sous Linux,
# jusqu'à 2 s sur FAT) gardent la même date. Règle des dates « douteuses » de git.
DOUTE_DATE_NS = 2_000_000_000


def _octets(chemin):
    try:
        with open(chemin, "rb") as f:
            return f.read()
    except OSError:
        return None


def lire(chemin):
    """Le fichier de factory, contrôlé : un dict dont les chemins sont des `Path` absolus.

    Le résultat est gardé tant que le fichier ne change pas : le moteur, le bureau et l'outil le relisent des centaines
    de fois par tour, et chaque lecture résolvait sept chemins sur le disque (mesure : 13 428 lectures pour 54 tests, un
    tiers de leur durée). La clé porte le chemin, le volume, l'inode, la taille, les dates de modification et de
    changement, et le dossier de l'utilisateur (dont dépendent les chemins en « ~/ »). Une entrée gardée alors que la date
    du fichier était douteuse (`DOUTE_DATE_NS`) n'est rendue qu'après comparaison des octets du fichier (un petit
    fichier : lecture brève, sans résolution de chemins) ; elle devient sûre dès qu'elle est confirmée hors du doute.
    Chaque appel reçoit sa propre copie."""
    try:
        st = os.stat(chemin)
        cle = (os.path.abspath(chemin), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns,
               os.path.expanduser("~"))
    except OSError:
        return _lire(chemin)   # illisible : `_lire` le dit
    douteux = abs(time.time_ns() - st.st_mtime_ns) < DOUTE_DATE_NS   # toute écriture rend la date récente
    entree = _CACHE.get(cle)
    if entree is not None:
        r, octets = entree
        if octets is None:
            return copy.deepcopy(r)
        if _octets(chemin) == octets:
            if not douteux:
                _CACHE[cle] = (r, None)   # confirmé hors du doute : toute écriture suivante changera la date
            return copy.deepcopy(r)
    avant = _octets(chemin) if douteux else None
    r = _lire(chemin)
    if douteux and (avant is None or _octets(chemin) != avant):
        return r   # le fichier a bougé pendant la lecture : rien n'est gardé
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[cle] = (copy.deepcopy(r), avant)
    return r


def _lire(chemin):
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
    apk_ignore = d.get("apk_ignore")
    if apk_ignore is not None and not (isinstance(apk_ignore, list) and all(_texte(x) for x in apk_ignore)):
        raise FactoryInvalide("Factory : « apk_ignore » doit être une liste de motifs de chemins (textes non vides).")
    adresse_integree = d.get("apk_adresse_integree")
    if adresse_integree is not None and not isinstance(adresse_integree, bool):
        raise FactoryInvalide("Factory : « apk_adresse_integree » doit valoir true ou false.")
    liens_publics = d.get("liens_publics")
    if liens_publics is not None and not (
            isinstance(liens_publics, list) and len(liens_publics) <= 8 and all(
                isinstance(x, dict) and _texte(x.get("libelle")) and len(x["libelle"]) <= 120 and isinstance(x.get("chemin"), str)
                and re.fullmatch(r"/[A-Za-z0-9_./~%?=&+-]{0,200}", x["chemin"]) and ".." not in x["chemin"] for x in liens_publics)):
        raise FactoryInvalide("Factory : « liens_publics » est une liste de 8 au plus de {libelle, chemin} : un chemin du "
                              "service public commençant par « / » (jamais une adresse complète ni un jeton).")
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
    serveur = d.get("agents_serveur_max", 0)
    if not _entier_borne(serveur, AGENTS_SERVEUR):
        raise FactoryInvalide("Factory : « agents_serveur_max » doit être un entier de 0 à 4 (0 par défaut).")
    ordre = d.get("ordre_lieux", list(LIEUX_D_AGENT))
    if not _ordre_valide(ordre):
        raise FactoryInvalide("Factory : « ordre_lieux » doit lister, sans doublon, au moins un lieu parmi "
                              "local, serveur, cloud (serveur, local, cloud par défaut).")
    par_metier = d.get("ordre_lieux_par_metier", {})
    if (not isinstance(par_metier, dict) or len(par_metier) > MAX_ORDRES_PAR_METIER
            or not all(_texte(r) and _ordre_valide(o) for r, o in par_metier.items())
            or len({r.strip() for r in par_metier}) != len(par_metier)):
        raise FactoryInvalide("Factory : « ordre_lieux_par_metier » doit associer à un rôle un ordre de lieux "
                              "(local, serveur, cloud, sans doublon).")
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
                       "flux": [dict(e) for e in w["flux"]],
                       **({"nature": w["nature"]} if w.get("nature") in ("correction", "fonctionnalite") else {})}
                      for w in workflows],
        "description": description, "seuil_methode": seuil,
        **({"apk_ignore": list(apk_ignore)} if apk_ignore is not None else {}),
        **({"apk_adresse_integree": adresse_integree} if adresse_integree is not None else {}),
        **({"liens_publics": [dict(x) for x in liens_publics]} if liens_publics is not None else {}),
        "catalogues": catalogues, "sessions": chem("sessions", "sessions.json"),
        "suivi": chem("suivi", "suivi.json"), "pieces": chem("pieces", "pieces"),
        "commandes": {k: list(v) for k, v in commandes.items()},
        "memoire": chem("memoire", str(Path(skill) / "orchestrateur" / "memoire")),
        "modele_orchestrateur": modele, "agents_locaux_max": locaux, "agents_cloud_max": cloud,
        "agents_serveur_max": serveur, "ordre_lieux": list(ordre),
        "ordre_lieux_par_metier": {r.strip(): list(o) for r, o in par_metier.items()},
        "environnement": [dict(x) for x in environnement],
    }


def _ordre_valide(v):
    """Une liste non vide de lieux d'agent, sans doublon."""
    return isinstance(v, list) and bool(v) and all(isinstance(x, str) and x in LIEUX_D_AGENT for x in v) and len(set(v)) == len(v)


def _entier_borne(v, bornes):
    return isinstance(v, int) and not isinstance(v, bool) and bornes[0] <= v <= bornes[1]


def ecrire_genre(chemin, genre):
    """Note le genre dans le fichier de factory (le reste du fichier est gardé tel quel)."""
    _ecrire_cles(chemin, {"genre": genre})


def ecrire_parallelisme(chemin, locaux, cloud, serveur=None, ordre=None, par_metier=None):
    """Note les places du projet (`agents_locaux_max` 1 à 16, `agents_cloud_max` 0 à 16) ; le reste est gardé. Facultatifs,
    écrits seulement s'ils sont donnés : `serveur` (`agents_serveur_max`, 0 à 4), `ordre` (`ordre_lieux`) et `par_metier`
    (`ordre_lieux_par_metier`, clés nettoyées ; `{}` le vide), contrôlés comme `lire` : rien n'est écrit si l'un est refusé."""
    if not _entier_borne(locaux, AGENTS_LOCAUX):
        raise FactoryInvalide("« agents_locaux_max » doit être un entier de 1 à 16.")
    if not _entier_borne(cloud, AGENTS_CLOUD):
        raise FactoryInvalide("« agents_cloud_max » doit être un entier de 0 à 16.")
    cles = {"agents_locaux_max": locaux, "agents_cloud_max": cloud}
    if serveur is not None:
        if not _entier_borne(serveur, AGENTS_SERVEUR):
            raise FactoryInvalide("« agents_serveur_max » doit être un entier de 0 à 4.")
        cles["agents_serveur_max"] = serveur
    if ordre is not None:
        if not _ordre_valide(ordre):
            raise FactoryInvalide("« ordre_lieux » doit lister, sans doublon, au moins un lieu parmi local, serveur, cloud.")
        cles["ordre_lieux"] = list(ordre)
    if par_metier is not None:
        if (not isinstance(par_metier, dict) or len(par_metier) > MAX_ORDRES_PAR_METIER
                or not all(_texte(r) and _ordre_valide(o) for r, o in par_metier.items())
                or len({r.strip() for r in par_metier}) != len(par_metier)):
            raise FactoryInvalide("« ordre_lieux_par_metier » doit associer à un rôle un ordre de lieux "
                                  "(local, serveur, cloud, sans doublon).")
        cles["ordre_lieux_par_metier"] = {r.strip(): list(o) for r, o in par_metier.items()}
    _ecrire_cles(chemin, cles)


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
