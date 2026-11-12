"""Recruter des agents depuis le bureau (conception `2026-11-12-recrutement-design.md`). Fonctions pures, sans IA.

- `depot(dossier)` : le projet est-il un dépôt git, sur GitHub ? Lu dans `.git/config`, sans lancer git.
- `roles_du_projet`, `travail_par_role`, `proposer` : la répartition automatique, déterministe et expliquée.
- `fiches_a_recruter` : les fiches à écrire pour une demande `recruter`, vérifiée contre les fiches et les places.
"""
import re
from pathlib import Path

from bureau.equipe import PRENOMS
from orchestrateur import workflows as wf

MODELES = ("Haiku", "Sonnet", "Opus")     # Fable : seulement avec l'accord du Directeur (case cochée), jamais en auto
MODELE_PAR_DEFAUT = "Sonnet"
MAX_PAR_DEMANDE = 16
HORS_PLACES = ("chef",)                   # le chef d'atelier ne tient pas de place
ROLE_RELECTURE = "relecteur"              # comme `moteur.regles` : la relecture croisée tient lieu de son étape
ETAPES_DE_FLUX, ETAPES_DE_VALIDATION = "flux:", "validation:"
_ROLE_SUR = re.compile(r"^[A-Za-z0-9_-]+\Z")
_SECTION = re.compile(r'^\s*\[\s*remote\s+"origin"\s*\]\s*$')


class RecrutementRefuse(Exception):
    pass


# --- Le dépôt du projet.

def _config_git(dossier):
    g = Path(dossier) / ".git"
    if g.is_dir():
        return g / "config"
    if g.is_file():      # un dossier de travail rattaché : « gitdir: <chemin> »
        m = re.match(r"\s*gitdir:\s*(.+?)\s*$", g.read_text(encoding="utf-8", errors="replace"))
        if m:
            interne = Path(m.group(1))
            interne = interne if interne.is_absolute() else Path(dossier) / interne
            commun = interne / "commondir"
            if commun.is_file():
                interne = interne / commun.read_text(encoding="utf-8", errors="replace").strip()
            return interne / "config"
    return None


def adresse_web(url):
    """`git@github.com:moi/jeu.git` ou `https://github.com/moi/jeu.git` → `https://github.com/moi/jeu` ; sinon tel quel."""
    u = (url or "").strip()
    m = re.match(r"^(?:git@|ssh://git@)github\.com[:/](.+?)(?:\.git)?/?$", u) or \
        re.match(r"^https?://(?:[^@/]+@)?github\.com/(.+?)(?:\.git)?/?$", u)
    return f"https://github.com/{m.group(1)}" if m else u


def depot(dossier):
    """`{git, github, origine, url}` : `.git` présent, origine sur github.com, l'adresse de l'origine, celle à ouvrir."""
    config = _config_git(dossier)
    if config is None:
        return {"git": False, "github": False, "origine": None, "url": None}
    origine, dans = None, False
    try:
        lignes = config.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lignes = []
    for ligne in lignes:
        if ligne.strip().startswith("["):
            dans = bool(_SECTION.match(ligne))
            continue
        m = re.match(r"^\s*url\s*=\s*(.+?)\s*$", ligne)
        if dans and m:
            origine = m.group(1)
            break
    github = bool(origine) and "github.com" in origine
    return {"git": True, "github": github, "origine": origine, "url": adresse_web(origine) if github else None}


def raison_sans_cloud(d):
    """Pourquoi un agent cloud ne peut pas être recruté (le dépôt), ou `None`."""
    if d["github"]:
        return None
    if not d["git"]:
        return "Le projet n'est pas un dépôt git : un agent cloud travaille sur le dépôt GitHub du projet."
    if d["origine"]:
        return ("L'origine du dépôt n'est pas sur GitHub : un agent cloud travaille sur un dépôt GitHub (changez "
                "l'origine vous-même, rien n'est remplacé automatiquement).")
    return "Le dépôt git du projet n'a pas d'origine GitHub : un agent cloud travaille sur le dépôt GitHub du projet."


def nom_de_depot(nom):
    """Le nom du dépôt GitHub tiré du nom du projet : lettres, chiffres, `.`, `_`, `-` (le reste devient `-`)."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (nom or "").strip()).strip("-.") or "projet"
    return s[:100]


# --- Les rôles, le travail, la répartition.

def _sans_chef(fiches):
    return [x for x in fiches if x["role"] not in HORS_PLACES]


def modele_du_role(fiches_du_role):
    """(modèle, raison) : celui de la première fiche du rôle (Fable → Opus : un outil ne choisit jamais Fable)."""
    if not fiches_du_role:
        return MODELE_PAR_DEFAUT, f"aucun agent de ce rôle : {MODELE_PAR_DEFAUT} par défaut"
    x = fiches_du_role[0]
    nom = x.get("prenom") or x["cle"]
    if x["modele"] in MODELES:
        return x["modele"], f"celui de {nom}, du même rôle"
    return "Opus", f"{nom} est sur {x['modele']}, accordé à lui seul : Opus"


def roles_du_projet(f, fiches):
    """Les rôles des étapes d'agent des workflows du projet, dans leur ordre : `{role, nom, service, modele,
    raison_modele, agents, cloud}` (agents = fiches du rôle, cloud = celles qui sont cloud)."""
    vus = {}
    for w in wf.tous(f):
        for e in wf.etapes_d_agent(w["flux"]):
            r = e.get("role")
            if r and r not in vus and r not in HORS_PLACES:
                vus[r] = {"role": r, "nom": e.get("nom") or r, "service": e.get("service")}
    for r in vus.values():
        siennes = [x for x in fiches if x["role"] == r["role"]]
        r["modele"], r["raison_modele"] = modele_du_role(siennes)
        r["agents"] = len(siennes)
        r["cloud"] = sum(1 for x in siennes if x["lieu"] == "cloud")
    return list(vus.values())


def _concerne(element, etape_id):
    v = (element or {}).get("validations")
    return True if not isinstance(v, list) else etape_id in v


def _rang(t, rangs):
    etape = str(t.get("etape") or "")
    for prefixe in (ETAPES_DE_FLUX, ETAPES_DE_VALIDATION):
        if etape.startswith(prefixe):
            return rangs.get(etape[len(prefixe):], len(rangs))
    return None


def _retenues(f, fonc, taches):
    """Les tâches de flux de la fonctionnalité retenues par une validation-barrière pas encore franchie (même règle
    que `moteur.regles._barrieres` : un élément concerné encore dans la file, avant la validation ou dessus)."""
    w = wf.de_la_fonctionnalite(f, fonc)
    flux = w["flux"] if w else []
    production = [s for s in flux if s.get("role") != ROLE_RELECTURE] or flux
    validations = [k for k, s in enumerate(production) if wf.est_validation(s)]
    if not validations:
        return set(), production
    rangs = {s["id"]: k for k, s in enumerate(production)}
    connus = dict(fonc.get("elements") or {})
    file = {q["id"]: q for q in fonc.get("file") or [] if isinstance(q, dict) and q.get("id")}
    premiere = None
    for k in validations:
        sid = production[k]["id"]
        if any(_concerne(q, sid) for q in file.values()):
            premiere = k
            break
        for t in taches:
            r = _rang(t, rangs)
            if (r is None or not t.get("element") or t["colonne"] == "fait" or t.get("bloquee")
                    or not _concerne(file.get(t["element"]) or connus.get(t["element"]), sid)):
                continue
            if r < k or (r == k and str(t.get("etape")).startswith(ETAPES_DE_VALIDATION)):
                premiere = k
                break
        if premiere is not None:
            break
    if premiere is None:
        return set(), production
    return {t["id"] for t in taches if str(t.get("etape") or "").startswith(ETAPES_DE_FLUX)
            and (_rang(t, rangs) or 0) > premiere}, production


def travail_par_role(f, s):
    """`{rôle: nombre}` : les tâches prêtes (ni faites, ni actives, ni bloquées, ni retenues par une validation) et,
    pour chaque élément encore dans la file, chaque étape d'agent qu'il passera avant la première validation."""
    compte = {}
    retenues = set()
    for fonc in s.get("fonctionnalites") or []:
        if fonc.get("etape") in wf.ETAPES_CACHANT_LES_COLONNES:
            continue
        taches = [t for t in s.get("taches") or [] if t.get("fonctionnalite") == fonc["id"]]
        r, production = _retenues(f, fonc, taches)
        retenues |= r
        avant = []
        for e in production:
            if wf.est_validation(e):
                break
            avant.append(e)
        for _ in fonc.get("file") or []:
            for e in avant:
                if e.get("role"):
                    compte[e["role"]] = compte.get(e["role"], 0) + 1
    for t in s.get("taches") or []:
        if (t.get("colonne") == "fait" or t.get("active") or t.get("bloquee") or not t.get("role")
                or t["id"] in retenues):
            continue
        compte[t["role"]] = compte.get(t["role"], 0) + 1
    return compte


def places_libres(f, fiches, places_cloud):
    """`{cloud, locaux}` : les places sans agent recruté (cloud : `agents_cloud_max` effectif − agents cloud ; locaux :
    `agents_locaux_max` − agents locaux, hors chef)."""
    agents = _sans_chef(fiches)
    return {"cloud": max(0, places_cloud - sum(1 for x in agents if x["lieu"] == "cloud")),
            "locaux": max(0, f["agents_locaux_max"] - sum(1 for x in agents if x["lieu"] == "local"))}


def _pluriel(n, mot):
    return f"{n} {mot}{'s' if n > 1 else ''}"


def proposer(f, s, fiches, places_cloud, github, maximum=MAX_PAR_DEMANDE):
    """La répartition automatique, une recrue à la fois (les N premières valent pour « Recruter N agents ») :
    `{propositions: [{role, modele, lieu, raison}], places, notes}`."""
    roles = roles_du_projet(f, fiches)
    ordre = [r["role"] for r in roles]
    par_role = {r["role"]: r for r in roles}
    travail = travail_par_role(f, s)
    places = places_libres(f, fiches, places_cloud)
    cloud, locaux = places["cloud"] if github else 0, places["locaux"]
    recrues = {r: 0 for r in ordre}
    propositions, notes = [], []
    while len(propositions) < maximum:
        manque = {r: travail.get(r, 0) - par_role[r]["agents"] - recrues[r] for r in ordre}
        candidats = [r for r in ordre if manque[r] > 0]
        if not candidats:
            if not propositions:
                notes.append("Aucun rôle n'a plus de travail prêt ou en file que d'agents : rien à recruter.")
            break
        if cloud > 0:
            lieu, cloud = "cloud", cloud - 1
            raison_lieu = f"cloud : place cloud libre (encore {cloud})"
        elif locaux > 0:
            lieu, locaux = "local", locaux - 1
            raison_lieu = (f"local : {'projet pas sur GitHub' if not github else 'plus de place cloud'}, place locale "
                           f"libre (encore {locaux})")
        else:
            notes.append("Plus de place libre : augmentez « Agents locaux en même temps » ou « Agents cloud en même "
                         "temps » (le cloud demande aussi un projet sur GitHub).")
            break
        r = max(candidats, key=lambda x: (manque[x], -ordre.index(x)))
        info = par_role[r]
        propositions.append({
            "role": r, "modele": info["modele"], "lieu": lieu,
            "raison": (f"{info['nom']} : {_pluriel(travail.get(r, 0), 'tâche')} prête(s) ou en file pour "
                       f"{_pluriel(info['agents'] + recrues[r], 'agent')} ; modèle {info['modele']} "
                       f"({info['raison_modele']}) ; {raison_lieu}")})
        recrues[r] += 1
    return {"propositions": propositions, "places": places, "notes": notes, "travail": travail}


# --- Les fiches des recrues.

def _cle_libre(role, prises, dossier):
    n = 1
    while f"{role}-{n}" in prises or (Path(dossier) / f"{role}-{n}.md").exists():
        n += 1
    return f"{role}-{n}"


def _prenom_libre(pris):
    for p in PRENOMS:
        if p not in pris:
            return p
    n = len(PRENOMS) + 1
    while f"Agent {n}" in pris:
        n += 1
    return f"Agent {n}"


def fiches_a_recruter(f, fiches, mode, agents, places_cloud, depot_, jour):
    """Les fiches à écrire (dicts de `fiches.ecrire_fiche`), ou `RecrutementRefuse` avec la raison. `mode` : `manuel`
    (un agent ; les places locales ne le limitent pas) ou `auto` (1 à 16 ; jamais au-delà des places libres)."""
    if mode not in ("manuel", "auto"):
        raise RecrutementRefuse("« mode » vaut manuel ou auto.")
    if not isinstance(agents, list) or not 1 <= len(agents) <= (1 if mode == "manuel" else MAX_PAR_DEMANDE):
        raise RecrutementRefuse("« agents » : un agent en manuel, de 1 à 16 en auto.")
    roles = {r["role"]: r for r in roles_du_projet(f, fiches)}
    briefs = Path(f["fiches"]) / "briefs"
    for a in agents:
        if not isinstance(a, dict) or not isinstance(a.get("role"), str) or a["role"] not in roles:
            raise RecrutementRefuse("Chaque agent a un « role » du workflow du projet : "
                                    + ", ".join(roles) + "." if roles else "Le projet n'a encore aucun workflow.")
        if not _ROLE_SUR.match(a["role"]) or not (briefs / f"{a['role']}.md").is_file():
            raise RecrutementRefuse(f"Le rôle « {a['role']} » n'a pas de brief (briefs/{a['role']}.md) : recrutez-le "
                                    "par une organisation.")
        fable = a.get("fable", False)
        if not isinstance(fable, bool):
            raise RecrutementRefuse("« fable » vaut vrai ou faux (la case d'accord du Directeur).")
        if a.get("modele") == "Fable":
            if not fable or mode != "manuel":
                raise RecrutementRefuse("Fable demande l'accord du Directeur (case cochée), en recrutement manuel.")
        elif a.get("modele") not in MODELES:
            raise RecrutementRefuse("« modele » vaut Haiku, Sonnet ou Opus.")
        if a.get("lieu") not in ("local", "cloud"):
            raise RecrutementRefuse("« lieu » vaut local ou cloud.")
    places = places_libres(f, fiches, places_cloud)
    n_cloud = sum(1 for a in agents if a["lieu"] == "cloud")
    n_locaux = len(agents) - n_cloud
    if n_cloud:
        raison = raison_sans_cloud(depot_)
        if raison:
            raise RecrutementRefuse(raison + " Créez d'abord le dépôt (« Créer le dépôt Git »).")
        if n_cloud > places["cloud"]:
            raise RecrutementRefuse(f"{_pluriel(places['cloud'], 'place')} cloud sans agent : augmentez « Agents "
                                    "cloud en même temps » avant de recruter un agent cloud de plus.")
    if mode == "auto" and n_locaux > places["locaux"]:
        raise RecrutementRefuse(f"{_pluriel(places['locaux'], 'place')} locale(s) sans agent : la répartition "
                                "automatique ne dépasse jamais les places.")
    prises = {x["cle"] for x in fiches}
    prenoms = {x.get("prenom") for x in fiches if x.get("prenom")}
    sortie = []
    for a in agents:
        role = roles[a["role"]]
        soeur = next((x for x in fiches if x["role"] == a["role"]), None)
        cle = _cle_libre(a["role"], prises, f["fiches"])
        prenom = _prenom_libre(prenoms)
        prises.add(cle)
        prenoms.add(prenom)
        texte = (soeur or {}).get("texte") or (f"Agent « {role['nom']} » recruté depuis le bureau : suit le brief du "
                                               f"rôle « {a['role']} ».")
        sortie.append({"cle": cle, "prenom": prenom, "role": a["role"],
                       "service": (soeur or {}).get("service") or role["service"], "modele": a["modele"],
                       "lieu": a["lieu"], "session": None, "specialite": (soeur or {}).get("specialite"),
                       "outils": (soeur or {}).get("outils"),
                       "fable": f"accordé par le Directeur le {jour}" if a["modele"] == "Fable" else None,
                       "texte": texte, "lecons": [], "chemin": Path(f["fiches"]) / f"{cle}.md"})
    return sortie
