"""La mise en place d'une proposition validée, l'inscription au bureau commun, la réparation, l'organisation.

Rien n'est écrit dans le projet avant `appliquer`. La configuration est écrite d'abord dans `.factory.tmp/`, puis
renommée en `.factory/` : un échec ne laisse ni dossier à moitié écrit, ni `.gitignore` ni bureau changés.
Dans les fichiers versionnés, la skill s'écrit `~/MyIAFactory/skill/...`, jamais en absolu.
"""
import json
import os
import shutil
import tempfile
from pathlib import Path

from bureau import reglages as regl
from installation import dossier, proposition
from installation.dossier import PREFIXE_SKILL, Echec
from orchestrateur import factory as fa
from orchestrateur import fiches, memoire
from orchestrateur import verifier_interface as vi

RACINE = Path(__file__).resolve().parent.parent
OUTIL = PREFIXE_SKILL + "/orchestrateur/outil.py"
DOSSIERS = ("pieces", "captures", "livrables", "methodes", "documents")
BLOC_GITIGNORE = ("# MyIAFactory : fichiers propres à la machine", ".factory/equipe.json", ".factory/*-historique.jsonl")
ANCIENNES_REGLES = (".factory/", ".factory", "/.factory/", "/.factory")
PORT = 8770
SERVICE_FACTURATION = {"id": "facturation", "nom": "Facturation"}


# --- Écritures sûres.

def _ecrire(chemin, texte):
    """Écriture atomique d'un texte UTF-8 (fins de ligne « \\n »)."""
    chemin = Path(chemin)
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(texte)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _ecrire_json(chemin, d):
    _ecrire(chemin, json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def _remettre(chemin, contenu):
    """Remet un fichier tel qu'il était (`None` : il n'existait pas)."""
    chemin = Path(chemin)
    if contenu is None:
        chemin.unlink(missing_ok=True)
    else:
        chemin.write_bytes(contenu)


def _lire_octets(chemin):
    chemin = Path(chemin)
    return chemin.read_bytes() if chemin.is_file() else None


# --- Le .gitignore du projet.

def regler_gitignore(projet):
    """Retire l'ancienne règle `.factory/` et ajoute une fois le bloc des fichiers propres à la machine.
    Rend vrai si le fichier a changé."""
    chemin = Path(projet) / ".gitignore"
    texte = chemin.read_text(encoding="utf-8-sig") if chemin.is_file() else ""
    fin = "\r\n" if "\r\n" in texte else "\n"
    lignes = texte.splitlines()
    gardees = [x for x in lignes if x.strip() not in ANCIENNES_REGLES]
    presentes = {x.strip() for x in gardees}
    manquantes = [x for x in BLOC_GITIGNORE[1:] if x not in presentes]
    if manquantes:
        if BLOC_GITIGNORE[0] in presentes:
            gardees += manquantes
        else:
            if gardees and gardees[-1].strip():
                gardees.append("")
            gardees += BLOC_GITIGNORE
    if gardees == lignes and texte.endswith("\n"):
        return False
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(fin.join(gardees) + fin)
    return True


# --- Le bureau commun.

def _lire_bureau_brut(bureau_json):
    """Le contenu du fichier de bureau, ou None s'il n'existe pas ; `Echec` s'il est illisible."""
    bureau_json = Path(bureau_json)
    if not bureau_json.exists():
        return None
    try:
        d = json.loads(bureau_json.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise Echec(f"Le fichier du bureau ({bureau_json}) est illisible ; il n'a pas été modifié. {e}")
    if not isinstance(d, dict) or not isinstance(d.get("projets"), list):
        raise Echec(f"Le fichier du bureau ({bureau_json}) est illisible (« projets » doit être une liste) ; "
                    "il n'a pas été modifié.")
    return d


def _inscrit(donnees, bureau_json, reglages):
    for p in donnees["projets"]:
        c = p.get("chemin") if isinstance(p, dict) else p
        if isinstance(c, str) and c.strip() and (Path(bureau_json).parent / c).resolve() == Path(reglages).resolve():
            return True
    return False


def _controler_bureau(bureau_json, reglages):
    """Les refus de `inscrire`, sans rien écrire : à passer avant toute écriture."""
    d = _lire_bureau_brut(bureau_json)
    if d is not None and not _inscrit(d, bureau_json, reglages) and len(d["projets"]) >= regl.MAX_PROJETS:
        raise Echec(f"Le bureau suit déjà {regl.MAX_PROJETS} projets.")
    return d


def inscrire(bureau_json, reglages, id_=None):
    """Ajoute le projet (ses réglages, en chemin absolu) au fichier de bureau, créé s'il n'existe pas.
    Rend faux s'il y était déjà."""
    bureau_json, reglages = Path(bureau_json), Path(reglages).resolve()
    d = _controler_bureau(bureau_json, reglages)
    if d is None:
        d = {"port": PORT, "projets": []}
    elif _inscrit(d, bureau_json, reglages):
        return False
    entree = {"chemin": str(reglages)}
    if id_ is not None:
        entree["id"] = id_
    d["projets"].append(entree)
    avant = _lire_octets(bureau_json)
    bureau_json.parent.mkdir(parents=True, exist_ok=True)
    _ecrire_json(bureau_json, d)
    try:
        regl.lire_bureau(bureau_json)
    except regl.ReglagesInvalides as e:
        _remettre(bureau_json, avant)
        raise Echec(f"Le fichier du bureau ne se relit pas après l'ajout ; il est remis tel qu'il était. {e}")
    return True


# --- L'organisation : services, flux, fiches, briefs.

def _fiche(a, chemin):
    return {"cle": a["cle"], "prenom": a.get("prenom"), "role": a["role"], "service": a["service"],
            "modele": a["modele"], "lieu": a["lieu"], "session": None, "specialite": a.get("specialite"),
            "texte": a["texte"].strip(), "lecons": [], "chemin": chemin}


def ecrire_organisation(factory_json, services, flux, agents, briefs):
    """Réécrit `services` et `flux` du fichier de factory (le reste est gardé) et écrit les fiches et les briefs
    nouveaux (un brief existant est gardé). Contrôlé comme une proposition ; un refus n'écrit rien."""
    factory_json = Path(factory_json)
    try:
        f = fa.lire(factory_json)
        existantes = fiches.lire_toutes(f["fiches"])
        brut = factory_json.read_text(encoding="utf-8-sig")
    except (fa.FactoryInvalide, fiches.FicheInvalide, OSError) as e:
        raise Echec(f"Organisation refusée : {e}")
    dossier_briefs = f["fiches"] / "briefs"
    briefs_existants = {c.stem for c in dossier_briefs.glob("*.md")} if dossier_briefs.is_dir() else set()
    erreurs = proposition.verifier_organisation(
        services, flux, agents, briefs, cloud=True, roles_deja_pourvus={x["role"] for x in existantes},
        cles_prises={x["cle"] for x in existantes}, briefs_existants=briefs_existants)
    if not erreurs:
        erreurs += [f"Agent « {a['cle']} » : le fichier de sa fiche existe déjà." for a in agents
                    if (f["fiches"] / f"{a['cle']}.md").exists()]
    if erreurs:
        raise Echec("Organisation refusée : " + " ; ".join(erreurs))
    d = json.loads(brut)
    d["services"] = [{"id": s["id"], "nom": s["nom"]} for s in services]
    d["flux"] = [{c: e[c] for c in ("id", "nom", "role", "service")} for e in flux]
    crees, factory_ecrite = [], False
    try:
        dossier_briefs.mkdir(parents=True, exist_ok=True)
        for a in agents:
            chemin = f["fiches"] / f"{a['cle']}.md"
            crees.append(chemin)
            fiches.ecrire_fiche(_fiche(a, chemin))
        for role, texte in briefs.items():
            chemin = dossier_briefs / f"{role}.md"
            if role in briefs_existants:
                continue
            crees.append(chemin)
            _ecrire(chemin, texte.strip() + "\n")
        factory_ecrite = True
        _ecrire_json(factory_json, d)
        fa.lire(factory_json)
    except BaseException:
        for c in crees:
            c.unlink(missing_ok=True)
        if factory_ecrite:
            _ecrire(factory_json, brut)
        raise


# --- La mise en place.

def _modele_reglages():
    return json.loads((RACINE / "exemples" / "projet-neuf" / "reglages.json").read_text(encoding="utf-8-sig"))


def _commande(*fin):
    return ["python", OUTIL, "--factory", "factory.json", "lancer", *fin]


def _ecrire_configuration(base, p, genre, maintenant):
    """Écrit toute la configuration du projet dans le dossier `base` (qui n'existe pas encore)."""
    base.mkdir()
    services = [dict(s) for s in p["services"]] + ([dict(SERVICE_FACTURATION)] if p["facturation"] else [])
    factory = {
        "nom": p["nom"], "skill": PREFIXE_SKILL, "genre": genre, "mots_interdits": list(p["mots_interdits"]),
        "fiches": "fiches", "controles": "controles.md", "consignes": "consignes-projet.md",
        "reglages": "reglages.json", "services": services,
        "flux": [{c: e[c] for c in ("id", "nom", "role", "service")} for e in p["flux"]],
        "seuil_methode": 3, "catalogues": {"*": {"commande": _commande("catalogue", "{fonctionnalite}")}},
        "commandes": {}, "modele_orchestrateur": p["modele_orchestrateur"],
        "agents_locaux_max": p["agents_locaux_max"],
    }
    _ecrire_json(base / "factory.json", factory)
    ecrire_organisation(base / "factory.json", services, p["flux"], p["agents"], p["briefs"])
    modele = _modele_reglages()
    reglages = {"releve": {"commande": _commande("releve")}, "actions": {"commande": _commande("actions")},
                "images": modele["images"], "orchestrateur": "factory.json", "livrables": modele["livrables"],
                "documents": modele["documents"], "alias_modeles": modele["alias_modeles"],
                "charge_max": p["charge_max"], "prix_automatiques": p["facturation"]}
    _ecrire_json(base / "reglages.json", reglages)
    _ecrire(base / "consignes-projet.md", p["consignes"].strip() + "\n")
    registre = (RACINE / "orchestrateur" / "modeles" / "registre-controles.md").read_text(encoding="utf-8-sig")
    jour = str(maintenant)[:10]
    lignes = [f"- C{n} · {jour} · installation : {' '.join(c.split())}" for n, c in enumerate(p["controles"], 1)]
    _ecrire(base / "controles.md", registre.rstrip("\n") + "\n" + ("\n" + "\n".join(lignes) + "\n" if lignes else ""))
    for d in DOSSIERS:
        (base / d).mkdir()


def verifier(factory_json):
    """Les lignes du vérificateur d'interface (sans `--complet`) et vrai s'il n'y a aucun écart."""
    chemin = Path(factory_json).resolve()
    lignes = []
    for libelle, fonction in vi.verifier_lecture(chemin, vi._etat(chemin)):
        try:
            fonction()
            lignes.append(f"ok {libelle}")
        except vi.Ignore as e:
            lignes.append(f"ignoré {libelle} : {e}")
        except vi.Ecart as e:
            lignes.append(f"ÉCART {libelle} : {e}")
        except (KeyError, IndexError, TypeError) as e:
            lignes.append(f"ÉCART {libelle} : sortie inattendue ({type(e).__name__} {e})")
    return lignes, not any(x.startswith("ÉCART") for x in lignes)


def message_orchestrateur(factory_json):
    return (f"Tu es l'orchestrateur du projet dont le fichier de factory est `{factory_json}`. Lis "
            f"`{PREFIXE_SKILL}/orchestrateur/consignes.md`, puis les consignes propres du projet, et commence la "
            "boucle de réveil.")


def appliquer(p, maintenant, git=memoire.executer_git):
    """Écrit la configuration d'une proposition validée, règle le `.gitignore`, inscrit le projet au bureau commun,
    puis vérifie. `Echec` si la proposition est invalide ou le projet déjà installé."""
    erreurs = proposition.verifier(p)
    if erreurs:
        raise Echec("Proposition refusée : " + " ; ".join(erreurs))
    projet = Path(p["projet"])
    if not projet.is_dir():
        raise Echec(f"Le dossier du projet n'existe pas : {projet}")
    fd, tmp = projet / ".factory", projet / ".factory.tmp"
    if (fd / "factory.json").exists():
        raise Echec("Déjà installé : lancez la réparation.")
    if fd.exists():
        raise Echec("Le projet a déjà un dossier .factory sans fichier de factory : c'est une configuration faite à "
                    "la main ; voir docs/orchestrateur.md pour la passer sur l'orchestrateur générique.")
    bureau_json = dossier.bureau()
    bureau_avant = _controler_bureau(bureau_json, fd / "reglages.json")
    genre, genre_raison = p["genre"], None
    memoire_skill = dossier.skill() / "orchestrateur" / "memoire"
    connus = {g["id"] for g in memoire.genres(memoire_skill)}
    a_creer = genre is not None and genre not in connus and "genre_nouveau" in p
    if genre is not None and genre not in connus and not a_creer:
        raise Echec(f"Genre inconnu « {genre} » : choisir un genre connu ou décrire un nouveau genre.")
    gitignore = projet / ".gitignore"
    gitignore_avant, octets_bureau = _lire_octets(gitignore), _lire_octets(bureau_json)
    renomme = False
    try:
        if tmp.exists():
            shutil.rmtree(tmp)   # reste d'une mise en place interrompue
        _ecrire_configuration(tmp, p, None if a_creer else genre, maintenant)
        tmp.rename(fd)
        renomme = True
        regler_gitignore(projet)
        ajoute = inscrire(bureau_json, fd / "reglages.json")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        if renomme:
            shutil.rmtree(fd, ignore_errors=True)
        if _lire_octets(gitignore) != gitignore_avant:
            _remettre(gitignore, gitignore_avant)
        if _lire_octets(bureau_json) != octets_bureau:
            _remettre(bureau_json, octets_bureau)
        raise
    factory_json = fd / "factory.json"
    if a_creer:   # en dernier : il publie dans la mémoire de la skill, hors du projet
        ok, message = memoire.creer_genre(memoire_skill, genre, p["genre_nouveau"]["description"],
                                          p["mots_interdits"], git=git)
        if ok:
            fa.ecrire_genre(factory_json, genre)
        else:
            genre_raison = f"Le genre « {genre} » n'a pas pu être créé ; l'orchestrateur le reproposera. {message}"
    ecrits = [str(c) for c in sorted(fd.rglob("*")) if c.is_file()] + [str(gitignore), str(bureau_json)]
    lignes, pret = verifier(factory_json)
    return {"ecrits": ecrits, "bureau": str(bureau_json), "relancer_bureau": ajoute and bureau_avant is not None,
            "agents_cloud": [{"cle": a["cle"], "role": a["role"], "modele": a["modele"],
                              "environnement": list(a.get("environnement") or [])}
                             for a in p["agents"] if a["lieu"] == "cloud"],
            "message_orchestrateur": message_orchestrateur(factory_json), "genre_raison": genre_raison,
            "verification": lignes, "pret": pret}


# --- La réparation.

def _remplacer_outil(commande):
    """Remplace dans une liste d'arguments tout chemin qui finit par `orchestrateur/outil.py`. Rend le nombre."""
    n = 0
    for i, a in enumerate(commande):
        if isinstance(a, str) and a.replace("\\", "/").endswith("orchestrateur/outil.py") and a != OUTIL:
            commande[i] = OUTIL
            n += 1
    return n


def _dans(chemin, dossier_):
    try:
        Path(chemin).resolve().relative_to(Path(dossier_).resolve())
        return True
    except ValueError:
        return False


def reparer(projet, calibrage):
    """Vérifie et répare une installation : chemins vers le dossier stable, limite d'agents locaux, `.gitignore`,
    dossiers manquants, inscription au bureau commun. Les adaptateurs (`commandes`) ne sont jamais touchés."""
    projet = Path(projet).resolve()
    factory_json = projet / ".factory" / "factory.json"
    if not factory_json.is_file():
        raise Echec("Aucune installation à réparer dans ce dossier (.factory/factory.json absent).")
    try:
        f = fa.lire(factory_json)
        d = json.loads(factory_json.read_text(encoding="utf-8-sig"))
    except (fa.FactoryInvalide, OSError, ValueError) as e:
        raise Echec(f"Le fichier de factory est illisible ; rien n'a été réparé. {e}")
    reglages = f["reglages"] if f["reglages"] and f["reglages"].is_file() else None
    regl_brut = None
    if reglages is not None:
        try:
            regl_brut = json.loads(reglages.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            raise Echec(f"Les réglages du projet sont illisibles ; rien n'a été réparé. {e}")
        if not isinstance(regl_brut, dict):
            raise Echec("Les réglages du projet sont illisibles (un objet JSON est attendu) ; rien n'a été réparé.")
        bureau_avant = _controler_bureau(dossier.bureau(), reglages)
    corrections = []
    change = False
    if d.get("skill") != PREFIXE_SKILL:
        corrections.append(f"Fichier de factory : skill « {d.get('skill')} » → « {PREFIXE_SKILL} ».")
        d["skill"], change = PREFIXE_SKILL, True
    for nom, cat in (d.get("catalogues") or {}).items():
        if isinstance(cat, dict) and isinstance(cat.get("commande"), list) and _remplacer_outil(cat["commande"]):
            corrections.append(f"Catalogue « {nom} » : outil.py → « {OUTIL} ».")
            change = True
    if "agents_locaux_max" not in d:
        d["agents_locaux_max"] = calibrage["agents_locaux_max"]
        corrections.append(f"Fichier de factory : agents_locaux_max = {calibrage['agents_locaux_max']} (calibrage).")
        change = True
    if change:
        _ecrire_json(factory_json, d)
    if regl_brut is not None:
        change = False
        for cle, v in regl_brut.items():
            if isinstance(v, dict) and isinstance(v.get("commande"), list) and _remplacer_outil(v["commande"]):
                corrections.append(f"Réglages : commande « {cle} » : outil.py → « {OUTIL} ».")
                change = True
        if change:
            _ecrire_json(reglages, regl_brut)
    if regler_gitignore(projet):
        corrections.append(".gitignore : la configuration est versionnée, seuls les fichiers propres à la machine "
                           "sont ignorés.")
    a_creer = [f["fiches"], f["pieces"]]
    if regl_brut is not None:
        for cle in ("images", "livrables", "documents"):
            racines = (regl_brut.get(cle) or {}).get("racines") if isinstance(regl_brut.get(cle), dict) else None
            for r in racines if isinstance(racines, list) else []:
                if isinstance(r, str) and r.strip():
                    a_creer.append(reglages.parent / r)
    for c in dict.fromkeys(Path(x).resolve() for x in a_creer):
        if not c.exists() and _dans(c, projet):
            c.mkdir(parents=True)
            corrections.append(f"Dossier créé : {c.relative_to(projet).as_posix()}.")
    relancer = False
    if reglages is not None and inscrire(dossier.bureau(), reglages):
        corrections.append(f"Projet inscrit au bureau commun ({dossier.bureau()}).")
        relancer = bureau_avant is not None
    lignes, pret = verifier(factory_json)
    return {"corrections": corrections, "verification": lignes, "pret": pret, "relancer_bureau": relancer}
