"""Le contrôle d'une proposition d'installation (version 1), avant tout enregistrement ou écriture.

    {"version": 1, "projet": chemin absolu, "cas": "vide" | "existant", "nom", "comprehension",
     "genre": id | null, "genre_nouveau": {"description"}?, "mots_interdits": [textes], "modele_orchestrateur",
     "charge_max", "agents_locaux_max", "cloud", "facturation", "supports": ["ordinateur" | "mobile"],
     "acces": {"tailscale": bool, "reseau_local": bool}, "services": [{id, nom}],
     "flux": [{id, nom, role, service, justification}],
     "agents": [{cle, prenom?, role, service, modele, lieu, specialite?, texte, environnement?: [textes]}],
     "briefs": {role: texte}, "consignes": texte, "controles": [textes], "estimation": objet de `estimer`,
     "moteur"?: {"couche": "claude" | "api", "ecart_estime": texte},
     "partenaires_conseilles"?: {besoin: [{"id" (actif du catalogue), "raison" (une phrase)}]}}

Nouveau format (agents polyvalents) : `metiers` `[{role, service, modele?, lieu?, specialite?, outils?, brief}]` (un par
rôle du flux) et `agents` `{"locaux": n, "cloud": m}` (le nombre d'agents, qui sont les places du projet) remplacent
`agents` (liste de fiches) et `briefs`. L'ancien format reste accepté.

`partenaires_conseilles` est facultatif (rien n'est obligatoire) ; la mise en place l'écrit dans `.factory/partenaires.json`.

`moteur` est facultatif (défaut : `claude`). `couche` dit par où passent les décisions de l'orchestrateur : `claude`
(`claude -p`, l'abonnement) ou `api` (l'API Messages d'Anthropic, **facturée à part**). L'API n'est jamais choisie
d'office ; la clé (`ANTHROPIC_API_KEY`) n'est jamais demandée dans la discussion : l'utilisateur la met lui-même dans son
environnement, et sans elle le moteur reste sur `claude -p`. `ecart_estime` : l'écart de coût dit à l'utilisateur.
"""
from pathlib import Path

from orchestrateur.factory import LIEUX_D_ETAPE, MOTIF_GENRE, MOTIF_ID, RESERVES
from orchestrateur.fiches import ACCORD_FABLE

MODELES = ("Haiku", "Sonnet", "Opus")
FABLE = "Fable n'est jamais choisi par l'installation."
SERVICE_FACTURATION = "facturation"
SUPPORTS = ("ordinateur", "mobile")
ACCES = ("tailscale", "reseau_local")
COUCHES = ("claude", "api")
QUESTION_API = ("Utiliser une clé API Anthropic pour les décisions de l'orchestrateur ? Elle est facturée à part de "
                "votre abonnement ; écart estimé : {ecart}")
ECART_API_PAR_DEFAUT = ("environ 0,05 $ de décisions par fonctionnalité, facturés à part de l'abonnement (sans la clé, "
                        "ces décisions passent par votre abonnement, sans frais en plus)")


def question_api(ecart=None):
    """La question du paramétrage sur la couche d'appel des décisions (défaut : non, l'abonnement)."""
    return QUESTION_API.format(ecart=ecart or ECART_API_PAR_DEFAUT)


def _verifier_moteur(m):
    if m is None:
        return []
    if not (isinstance(m, dict) and m.get("couche") in COUCHES and _ligne(m.get("ecart_estime"))):
        return ["« moteur » doit être {couche: claude ou api, ecart_estime: un texte d'une ligne}."]
    return []


def _texte(v):
    return isinstance(v, str) and v.strip() != "" and "\x00" not in v


def _ligne(v):
    """Un texte non vide sur une seule ligne (il entre dans un en-tête ou une ligne de registre)."""
    return _texte(v) and "\n" not in v and "\r" not in v


def _entier(v, bas, haut):
    return type(v) is int and bas <= v <= haut


def _modele(v, ou, accord=None):
    """Fable n'est accepté que pour un agent dont la fiche porte l'accord du Directeur (`accord`) ; jamais pour
    l'orchestrateur."""
    if isinstance(v, str) and v.strip().lower() == "fable":
        if v == "Fable" and isinstance(accord, str) and ACCORD_FABLE.match(accord):
            return []
        return [f"{ou} : {FABLE}"]
    if v not in MODELES:
        return [f"{ou} : le modèle doit valoir Haiku, Sonnet ou Opus."]
    return []


LIEUX_METIER = ("local", "cloud", "indifférent")


def est_polyvalente(agents, metiers=None):
    """Vrai pour une organisation du nouveau format : `agents` est `{locaux, cloud}` (ou absent, avec des `metiers`)."""
    return isinstance(agents, dict) or (agents is None and metiers is not None)


def agents_pour_estimer(metiers):
    """Les agents que l'estimation d'un coût attend (`{role, modele}`) pour des métiers : le modèle par défaut du
    métier (Sonnet sinon), sans plafond (un agent polyvalent n'en a pas)."""
    return [{"role": m["role"], "modele": m.get("modele") or "Sonnet", "sans_plafond": True}
            for m in metiers if isinstance(m, dict) and isinstance(m.get("role"), str)]


def verifier_metiers(metiers, ids_services, roles_du_flux, briefs_existants=(), cloud=True):
    """Les erreurs des `metiers` d'une organisation polyvalente : un métier par rôle du flux (ou un brief déjà là)."""
    if not isinstance(metiers, list) or not all(isinstance(m, dict) for m in metiers):
        return ["« metiers » doit être une liste de {role, service, modele?, lieu?, specialite?, outils?, brief}."]
    e, roles = [], []
    for m in metiers:
        r = m.get("role")
        if not (isinstance(r, str) and MOTIF_ID.match(r)):
            e.append(f"Métier refusé {r!r} : un « role » (minuscules, chiffres, tirets, 40 caractères au plus).")
            continue
        if r in roles:
            e.append(f"Métier « {r} » en double.")
        roles.append(r)
        if m.get("service") not in ids_services:
            e.append(f"Métier « {r} » : service inconnu « {m.get('service')} ».")
        if m.get("modele") is not None and m["modele"] not in MODELES:
            e.append(f"Métier « {r} » : le modèle par défaut doit valoir Haiku, Sonnet ou Opus (Fable ne se demande "
                     "que tâche par tâche, avec l'accord du Directeur).")
        lieu = m.get("lieu", "indifférent")
        if lieu not in LIEUX_METIER:
            e.append(f"Métier « {r} » : le lieu doit valoir local, cloud ou indifférent.")
        elif lieu == "cloud" and not cloud:
            e.append(f"Métier « {r} » : cloud refusé, la proposition est en local seulement.")
        for champ in ("specialite", "outils"):
            if m.get(champ) is not None and not _ligne(m[champ]):
                e.append(f"Métier « {r} » : « {champ} » doit tenir sur une ligne.")
        if not _texte(m.get("brief")):
            e.append(f"Métier « {r} » : le « brief » (la consigne du spécialiste) est vide.")
    for r in roles_du_flux:
        if r not in roles and r not in briefs_existants:
            e.append(f"Aucun métier pour le rôle « {r} ».")
    return e


def verifier_equipe(agents, cloud=True):
    """Les erreurs du nombre d'agents `{locaux: 1 à 16, cloud: 0 à 16}` d'une organisation polyvalente."""
    if not (isinstance(agents, dict) and set(agents) == {"locaux", "cloud"}):
        return ["« agents » doit valoir {\"locaux\": n, \"cloud\": m} (le nombre d'agents)."]
    e = []
    if not _entier(agents["locaux"], 1, 16):
        e.append("« agents.locaux » doit être un entier de 1 à 16.")
    if not _entier(agents["cloud"], 0, 16):
        e.append("« agents.cloud » doit être un entier de 0 à 16.")
    elif agents["cloud"] and not cloud:
        e.append("« agents.cloud » : cloud refusé, la proposition est en local seulement.")
    return e


def verifier_organisation(services, flux, agents, briefs, cloud=True, roles_deja_pourvus=(), cles_prises=(),
                          briefs_existants=(), metiers=None, equipe_en_place=False):
    """Les erreurs de la partie organisation (services, flux, agents, briefs). Les trois derniers paramètres servent
    quand l'organisation s'ajoute à un projet déjà installé : rôles déjà tenus, clés de fiches et briefs existants.
    Nouveau format (agents polyvalents) : `agents` vaut `{locaux, cloud}` et `metiers` porte un métier par rôle du
    flux (`briefs` n'existe plus) ; `equipe_en_place` : le projet a déjà son équipe, `agents` peut alors manquer."""
    e = []
    if not isinstance(services, list) or not all(isinstance(s, dict) for s in services):
        return ["« services » doit être une liste de {id, nom}."]
    ids_services = []
    for s in services:
        if not (isinstance(s.get("id"), str) and MOTIF_ID.match(s["id"])) or not _ligne(s.get("nom")):
            e.append(f"Service refusé {s.get('id')!r} : un « id » (minuscules, chiffres, tirets) et un « nom ».")
        elif s["id"] in ids_services:
            e.append(f"Service en double « {s['id']} ».")
        else:
            ids_services.append(s["id"])
    if not isinstance(flux, list) or not flux or not all(isinstance(x, dict) for x in flux):
        return e + ["« flux » doit lister au moins une étape {id, nom, role, service, justification}."]
    vus, roles_du_flux = set(), []
    for k, x in enumerate(flux):
        i = x.get("id")
        if not (isinstance(i, str) and MOTIF_ID.match(i)) or i in RESERVES:
            e.append(f"Étape refusée {i!r} : minuscules, chiffres et tirets ; ni « cadrage » ni « fait ».")
            continue
        if i in vus:
            e.append(f"Étape en double « {i} ».")
        vus.add(i)
        if not _ligne(x.get("nom")):
            e.append(f"Étape « {i} » : un « nom » est attendu.")
        if "lieu" in x and (x.get("validation") is True or x["lieu"] not in LIEUX_D_ETAPE):
            e.append(f"Étape « {i} » : « lieu » vaut local ou indifférent, jamais sur une validation du Directeur.")
        if x.get("validation") is True:   # une validation du Directeur : ni rôle, ni service, ni agent
            if "role" in x or "service" in x:
                e.append(f"Étape « {i} » : une validation du Directeur n'a ni rôle ni service.")
            if k == 0:
                e.append(f"Étape « {i} » : une validation du Directeur ne peut pas être la première étape.")
            if k == len(flux) - 1:
                e.append(f"Étape « {i} » : une validation du Directeur ne peut pas être la dernière étape.")
            if k and isinstance(flux[k - 1], dict) and flux[k - 1].get("validation") is True:
                e.append(f"Étape « {i} » : deux validations du Directeur de suite sont refusées.")
            if "justification" in x and not _texte(x.get("justification")):
                e.append(f"Étape « {i} » : la justification est vide.")
            continue
        if not (isinstance(x.get("role"), str) and MOTIF_ID.match(x["role"])):
            e.append(f"Étape « {i} » : un « role » (minuscules, chiffres, tirets) est attendu.")
        elif x["role"] not in roles_du_flux:
            roles_du_flux.append(x["role"])
        if x.get("service") not in ids_services:
            e.append(f"Étape « {i} » : service inconnu « {x.get('service')} ».")
        if "justification" in x and not _texte(x.get("justification")):
            e.append(f"Étape « {i} » : la justification est vide.")
    if est_polyvalente(agents, metiers):
        e += verifier_metiers(metiers, ids_services, roles_du_flux, briefs_existants, cloud)
        if agents is not None or not equipe_en_place:
            e += verifier_equipe(agents, cloud)
        return e
    if not isinstance(agents, list) or not all(isinstance(a, dict) for a in agents):
        return e + ["« agents » doit être une liste de fiches."]
    cles, roles = set(cles_prises), set(roles_deja_pourvus)
    for a in agents:
        c = a.get("cle")
        if not (isinstance(c, str) and MOTIF_ID.match(c)):
            e.append(f"Agent refusé {c!r} : une « cle » (minuscules, chiffres, tirets, 40 caractères au plus).")
            continue
        if c in cles:
            e.append(f"Agent « {c} » : clé déjà prise.")
        cles.add(c)
        if not (isinstance(a.get("role"), str) and MOTIF_ID.match(a["role"])):
            e.append(f"Agent « {c} » : un « role » (minuscules, chiffres, tirets) est attendu.")
        else:
            roles.add(a["role"])
        if a.get("service") not in ids_services:
            e.append(f"Agent « {c} » : service inconnu « {a.get('service')} ».")
        e += _modele(a.get("modele"), f"Agent « {c} »", a.get("fable"))
        if a.get("lieu") not in ("local", "cloud"):
            e.append(f"Agent « {c} » : le lieu doit valoir local ou cloud.")
        elif a["lieu"] == "cloud" and not cloud:
            e.append(f"Agent « {c} » : cloud refusé, la proposition est en local seulement.")
        for champ in ("prenom", "specialite"):
            if a.get(champ) is not None and not _ligne(a[champ]):
                e.append(f"Agent « {c} » : « {champ} » doit tenir sur une ligne.")
        if not _texte(a.get("texte")):
            e.append(f"Agent « {c} » : le « texte » de sa fiche est vide.")
        env = a.get("environnement", [])
        if not isinstance(env, list) or not all(_ligne(v) for v in env):
            e.append(f"Agent « {c} » : « environnement » doit être une liste de textes.")
    for r in roles_du_flux:
        if r not in roles:
            e.append(f"Aucun agent pour le rôle « {r} ».")
    if not isinstance(briefs, dict) or not all(isinstance(k, str) and MOTIF_ID.match(k) and _texte(v)
                                               for k, v in briefs.items()):
        return e + ["« briefs » doit associer à chaque rôle (minuscules, chiffres, tirets) un texte."]
    for r in roles_du_flux:
        if r not in briefs and r not in briefs_existants:
            e.append(f"Aucun brief pour le rôle « {r} ».")
    return e


def verifier_supports(supports, acces):
    """Le support de traitement (ordinateur, mobile) et les accès du téléphone qui vont avec."""
    if not (isinstance(supports, list) and supports and all(s in SUPPORTS for s in supports)
            and len(set(supports)) == len(supports)):
        return ["« supports » doit lister, sans double, « ordinateur » et/ou « mobile »."]
    if not (isinstance(acces, dict) and set(acces) == set(ACCES) and all(isinstance(v, bool) for v in acces.values())):
        return ["« acces » doit valoir {\"tailscale\": vrai ou faux, \"reseau_local\": vrai ou faux}."]
    if "mobile" in supports and not any(acces.values()):
        return ["« acces » : avec le mobile, ouvrir Tailscale (par défaut) ou le Wi-Fi de la maison."]
    if "mobile" not in supports and any(acces.values()):
        return ["« acces » : sans le mobile, aucun accès distant n'est ouvert."]
    return []


def verifier(p):
    """Les erreurs de la proposition ; une liste vide si elle est valide."""
    if not isinstance(p, dict):
        return ["La proposition doit être un objet JSON."]
    e = []
    if p.get("version") != 1:
        e.append("« version » doit valoir 1.")
    if not (_texte(p.get("projet")) and Path(p["projet"]).is_absolute()):
        e.append("« projet » doit être le chemin absolu du dossier du projet.")
    if p.get("cas") not in ("vide", "existant"):
        e.append("« cas » doit valoir vide ou existant.")
    for champ in ("nom",):
        if not _ligne(p.get(champ)):
            e.append(f"« {champ} » doit être un texte d'une ligne.")
    for champ in ("comprehension", "consignes"):
        if not _texte(p.get(champ)):
            e.append(f"« {champ} » doit être un texte non vide.")
    genre = p.get("genre")
    if genre is not None and not (isinstance(genre, str) and MOTIF_GENRE.match(genre)):
        e.append("« genre » doit être nul ou un identifiant de genre (minuscules, chiffres, tirets).")
    if "genre_nouveau" in p:
        gn = p["genre_nouveau"]
        if genre is None:
            e.append("« genre_nouveau » demande l'identifiant du nouveau genre dans « genre ».")
        if not (isinstance(gn, dict) and _texte(gn.get("description"))):
            e.append("« genre_nouveau » demande une « description ».")
    mots = p.get("mots_interdits")
    if not isinstance(mots, list) or not all(_ligne(m) for m in mots):
        e.append("« mots_interdits » doit être une liste de textes.")
    e += _modele(p.get("modele_orchestrateur"), "« modele_orchestrateur »")
    if not _entier(p.get("charge_max"), 30, 95):
        e.append("« charge_max » doit être un entier de 30 à 95.")
    if not _entier(p.get("agents_locaux_max"), 1, 16):
        e.append("« agents_locaux_max » doit être un entier de 1 à 16.")
    for champ in ("cloud", "facturation"):
        if not isinstance(p.get(champ), bool):
            e.append(f"« {champ} » doit valoir vrai ou faux.")
    e += verifier_supports(p.get("supports"), p.get("acces"))
    e += _verifier_moteur(p.get("moteur"))
    flux = p.get("flux")
    if isinstance(flux, list):
        for x in flux:
            if isinstance(x, dict) and "justification" not in x:   # une justification vide : verifier_organisation
                e.append(f"Étape « {x.get('id')} » : une justification en une phrase est attendue.")
    services = p.get("services")
    if isinstance(services, list) and any(isinstance(s, dict) and s.get("id") == SERVICE_FACTURATION for s in services):
        e.append("Le service « facturation » n'est pas déclaré à la main : la mise en place l'ajoute quand la "
                 "facturation est un objectif.")
    e += verifier_organisation(services, flux, p.get("agents"), p.get("briefs"), cloud=p.get("cloud") is True,
                               metiers=p.get("metiers"))
    if est_polyvalente(p.get("agents"), p.get("metiers")) and isinstance(p.get("agents"), dict)             and _entier(p["agents"].get("locaux"), 1, 16) and _entier(p.get("agents_locaux_max"), 1, 16)             and p["agents"]["locaux"] != p["agents_locaux_max"]:
        e.append("« agents_locaux_max » est le nombre d'agents locaux de « agents » : les deux valent la même chose.")
    controles = p.get("controles")
    if not isinstance(controles, list) or not all(_ligne(c) for c in controles):
        e.append("« controles » doit être une liste de textes d'une ligne.")
    if p.get("partenaires_conseilles") is not None:
        from partenaires import catalogue
        par_id = {x["id"]: x for x in catalogue.lire()["partenaires"]}
        e += ["« partenaires_conseilles » : " + x for x in catalogue.verifier_conseils(p["partenaires_conseilles"], par_id)]
    if not (isinstance(p.get("estimation"), dict) and "tokens" in p["estimation"]):
        e.append("« estimation » doit être le résultat de « estimer ».")
    return list(dict.fromkeys(e))
