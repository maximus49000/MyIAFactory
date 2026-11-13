"""Le lieu des étapes d'un projet et leur découpage (conception `2026-11-13-etapes-locales-design.md`).

Une étape d'agent porte un `lieu` facultatif : `local` (elle exige les logiciels du poste) ou `indifférent` (cloud
possible). Une étape mixte se découpe en deux étapes consécutives, même rôle, même service : `<id>` garde la partie
« code » (`lieu: indifférent`, nom « <nom> : code »), `<id>-local` fait la partie locale (`lieu: local`, nom « <nom> : mise
en place et tests »). Garder l'identifiant de la première partie laisse valides les tâches et les éléments en cours.

Une proposition de découpage (le jugement `decouper_lieux`) est vérifiée strictement avant toute écriture
(`verifier_proposition`) : c'est le filet de sécurité d'un projet en production. Elle est appliquée à chaque workflow
du projet par identifiant d'étape (`appliquer`), rejouable sans effet, sans toucher aucune tâche. Fonctions pures, sauf
`ecrire_au_projet` qui écrit le fichier de factory.
"""
import json
import os
import tempfile
from pathlib import Path

from orchestrateur import factory as fa
from orchestrateur import workflows as wf
from orchestrateur.memoire import normaliser_mot

SUFFIXE_LOCAL = "-local"
LIEUX = wf.LIEUX_D_ETAPE
_HORS_COMPARAISON = ("nom", "lieu")      # ce qu'une proposition peut changer à une étape découpée


# Ce que la partie locale d'une étape découpée dit à son agent (au journal de sa tâche, en tête) : le code est déjà écrit.
CONSIGNE_PARTIE_LOCALE = (
    "Partie locale d'une étape découpée : le code est déjà écrit par l'étape précédente et fusionné dans le dépôt. "
    "Tu ne le réécris pas : tu récupères le dépôt à jour, tu compiles, tu testes (au premier plan, sur le poste), tu "
    "captures ce qu'il faut montrer et tu rends ce que la validation suivante attend (captures, apk, mode opératoire). "
    "Ne corrige que ce qui empêche de compiler ou de tester, et dis-le.")


def est_partie_locale(flux, etape):
    """Vrai pour la partie locale d'une étape découpée : `<id>-local`, juste après `<id>` dans le flux."""
    if not isinstance(etape, dict) or not str(etape.get("id") or "").endswith(SUFFIXE_LOCAL):
        return False
    ids = [e.get("id") for e in flux]
    k = ids.index(etape["id"]) if etape["id"] in ids else -1
    return k > 0 and ids[k - 1] == etape["id"][:-len(SUFFIXE_LOCAL)]


def _ligne(v):
    return isinstance(v, str) and v.strip() != "" and "\n" not in v and "\r" not in v


def _sans(e, cles):
    return {k: v for k, v in wf.etape_ecrite(e).items() if k not in cles}


def _forme(e):
    """Message d'erreur sur la forme d'une étape proposée (avant toute comparaison), ou `None`."""
    if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not fa.MOTIF_ID.match(e["id"]):
        return "chaque étape est un objet {id, nom, …} dont l'« id » est court (minuscules, chiffres, tirets)."
    if "lieu" in e and (wf.est_validation(e) or e["lieu"] not in LIEUX):
        return (f"l'étape « {e['id']} » : « lieu » vaut local ou indifférent, jamais sur une validation du "
                "Directeur.")
    if not _ligne(e.get("nom")):
        return f"l'étape « {e['id']} » : un « nom » sur une ligne est attendu."
    if not wf.est_validation(e) and not all(isinstance(e.get(c), str) and e[c] for c in ("role", "service")):
        return f"l'étape « {e['id']} » : « role » et « service » sont attendus."
    return None


def verifier_proposition(flux, propose):
    """Rend l'erreur (un texte) d'une proposition de découpage du `flux`, ou `None` si elle est acceptable. Chaque étape
    existante garde son `id`, son ordre, son rôle, son service, son modèle et sa nature (validation ou non) ; une étape
    gardée telle quelle garde aussi son nom. Seuls changent : le `lieu` des étapes d'agent, et le découpage d'une étape
    `<id>` (nom « … : code » libre, `lieu: indifférent`) par l'insertion, juste après elle, de `<id>-local` (même rôle,
    même service, `lieu: local`). Une étape qui a déjà sa partie locale, ou qui en est une, n'est jamais redécoupée."""
    if not isinstance(propose, list) or not propose:
        return "La proposition doit être la liste des étapes du workflow, dans l'ordre."
    for e in propose:
        erreur = _forme(e)
        if erreur:
            return f"Proposition refusée : {erreur}"
    ids = [e["id"] for e in propose]
    if len(ids) != len(set(ids)):
        double = next(i for i in ids if ids.count(i) > 1)
        return f"Proposition refusée : l'étape « {double} » est en double."
    existants = {e["id"]: e for e in flux}
    gardees = [i for i in ids if i in existants]
    if gardees != [e["id"] for e in flux]:
        manquantes = [e["id"] for e in flux if e["id"] not in ids]
        if manquantes:
            return (f"Proposition refusée : l'étape « {manquantes[0]} » est supprimée ou renommée ; chaque étape "
                    "existante est gardée, avec son identifiant.")
        return "Proposition refusée : l'ordre des étapes existantes a changé ; il est gardé."
    for k, e in enumerate(propose):
        if e["id"] in existants:
            continue
        # une étape neuve : seulement la partie locale de l'étape qui la précède
        avant = propose[k - 1] if k else None
        if avant is None or e["id"] != f"{avant['id']}{SUFFIXE_LOCAL}" or avant["id"] not in existants:
            return (f"Proposition refusée : l'étape « {e['id']} » n'existe pas ; seule « <id>-local » peut être "
                    "ajoutée, juste après l'étape « <id> » qu'elle découpe.")
        base = existants[avant["id"]]
        if wf.est_validation(base):
            return f"Proposition refusée : la validation « {base['id']} » ne se découpe pas."
        if base["id"].endswith(SUFFIXE_LOCAL) and base["id"][:-len(SUFFIXE_LOCAL)] in existants:
            return f"Proposition refusée : « {base['id']} » est déjà une partie locale ; elle ne se redécoupe pas."
        if wf.est_validation(e) or e.get("lieu") != wf.LIEU_LOCAL:
            return f"Proposition refusée : « {e['id']} » est la partie locale : « lieu »: « local »."
        if (e["role"], e["service"]) != (base["role"], base["service"]):
            return (f"Proposition refusée : « {e['id']} » garde le rôle et le service de « {base['id']} » "
                    f"({base['role']}, {base['service']}).")
        if "modele" in e and e["modele"] not in wf.MODELES_D_ETAPE:
            return f"Proposition refusée : « {e['id']} » : « modele » vaut {', '.join(wf.MODELES_D_ETAPE)}."
        if avant.get("lieu") != wf.LIEU_INDIFFERENT:
            return (f"Proposition refusée : la partie code « {avant['id']} » porte « lieu »: « indifférent » (elle "
                    "part dans le cloud si une place s'y libère).")
    decoupees = {propose[k - 1]["id"] for k, e in enumerate(propose) if e["id"] not in existants}
    for e in propose:
        if e["id"] not in existants:
            continue
        orig = existants[e["id"]]
        if wf.est_validation(orig) != wf.est_validation(e):
            return f"Proposition refusée : l'étape « {e['id']} » change de nature (validation ou non)."
        hors = _HORS_COMPARAISON if e["id"] in decoupees else ("lieu",)
        if _sans(orig, hors) != _sans(e, hors):
            quoi = "son rôle, son service ou son modèle" if e["id"] in decoupees else \
                "son nom, son rôle, son service ou son modèle"
            return f"Proposition refusée : l'étape « {e['id']} » change ({quoi}) ; seul son « lieu » change."
    return None


def _transformations(propose):
    """{id: (étape proposée, partie locale proposée ou None)} d'une proposition déjà vérifiée."""
    sortie = {}
    for k, e in enumerate(propose):
        suivante = propose[k + 1] if k + 1 < len(propose) else None
        local = suivante if suivante is not None and suivante["id"] == f"{e['id']}{SUFFIXE_LOCAL}" else None
        sortie[e["id"]] = (e, local)
    return sortie


def appliquer(flux, propose, prefixe=""):
    """Le `flux` découpé selon `propose` (une proposition vérifiée sur le flux de référence, aux identifiants sans
    préfixe) : chaque étape `<prefixe><id>` reçoit le `lieu` proposé (retiré si la proposition n'en a pas) ; une étape
    découpée reçoit le nom de sa partie code et, juste après, sa partie locale `<prefixe><id>-local` — sauf si elle l'a
    déjà (jamais redécoupée). Une étape que la proposition ne cite pas est gardée telle quelle. Rien n'est modifié en
    place ; rejouable sans effet."""
    trans = _transformations(propose)
    ids = {e.get("id") for e in flux}
    sortie = []
    for e in flux:
        e = dict(e)
        base = e["id"][len(prefixe):] if prefixe and e["id"].startswith(prefixe) else (None if prefixe else e["id"])
        t = trans.get(base) if base is not None else None
        if t is None or wf.est_validation(e):
            sortie.append(e)
            continue
        code, local = t
        if code.get("lieu") in LIEUX:
            e["lieu"] = code["lieu"]
        else:
            e.pop("lieu", None)
        sortie.append(e)
        soeur = f"{e['id']}{SUFFIXE_LOCAL}"
        if local is None or soeur in ids:
            continue
        e["nom"] = code["nom"]
        nouvelle = {"id": soeur, "nom": local["nom"], "role": e["role"], "service": e["service"], "lieu": wf.LIEU_LOCAL}
        if local.get("modele") in wf.MODELES_D_ETAPE:
            nouvelle["modele"] = local["modele"]
            if _ligne(local.get("justification")):
                nouvelle["justification"] = local["justification"].strip()
        sortie.append(nouvelle)
    return sortie


def flux_de_reference(f):
    """Le flux que le jugement découpe : les étapes du principal et des workflows de genre (sans fonctionnalité), puis
    celles des workflows de fonctionnalité, sans leur préfixe `<fid>-`, quand leur identifiant n'y est pas déjà (dans
    l'ordre, sans doublon)."""
    sortie, vus = [], set()
    ws = wf.tous(f)
    for w in [x for x in ws if not x.get("fonctionnalite")] + [x for x in ws if x.get("fonctionnalite")]:
        prefixe = f"{w['fonctionnalite']}-" if w.get("fonctionnalite") else ""
        for e in w["flux"]:
            base = e["id"][len(prefixe):] if prefixe and e["id"].startswith(prefixe) else e["id"]
            if base not in vus:
                vus.add(base)
                sortie.append(dict(wf.etape_ecrite(e), id=base))
    return sortie


def _prefixe(w):
    return f"{w['fonctionnalite']}-" if w.get("fonctionnalite") else ""


def etapes_locales_suggerees(flux, environnement):
    """Les identifiants des étapes d'agent du `flux` qu'un outil de l'environnement du projet cite : son `pour` (l'id
    ou le nom de l'étape), ou son `objectif` qui nomme l'étape (son id ou son nom, sans casse ni accents)."""
    sortie = set()
    for o in environnement or []:
        if not isinstance(o, dict):
            continue
        pour = normaliser_mot(o.get("pour") or "")
        objectif = f" {normaliser_mot(o.get('objectif') or '')} "
        for e in wf.etapes_d_agent(flux):
            noms = {normaliser_mot(e["id"]), normaliser_mot(e.get("nom") or "")} - {""}
            if pour in noms or any(f" {n} " in objectif for n in noms):
                sortie.add(e["id"])
    return sortie


def etapes_qui_exigent_le_poste(flux, environnement):
    """Les étapes d'agent du `flux` qui exigent les logiciels du poste : celles qu'un outil de l'environnement cite
    (voir `etapes_locales_suggerees`), sauf un outil que le cloud sait installer (`cloud: true`) ; une étape découpée
    passe l'exigence à sa partie `<id>-local`, et toute partie `-local` l'exige. Leur lieu est figé sur `local`."""
    outils = [o for o in environnement or [] if isinstance(o, dict) and o.get("cloud") is not True]
    ids = {e["id"] for e in wf.etapes_d_agent(flux)}
    sortie = set()
    for i in etapes_locales_suggerees(flux, outils):
        sortie.add(f"{i}{SUFFIXE_LOCAL}" if f"{i}{SUFFIXE_LOCAL}" in ids else i)
    sortie |= {i for i in ids if i.endswith(SUFFIXE_LOCAL)}
    return sortie


# --- L'écriture au projet : tous les workflows du fichier de factory, d'un coup, contrôlée avant de remplacer.

def _ecrire(chemin, transformer):
    """Applique `transformer(flux, prefixe) -> flux` au flux principal et à chaque workflow du fichier de factory brut
    (les autres clés sont gardées telles quelles), contrôle le résultat (`factory.lire`) puis remplace le fichier d'un
    coup. Rend vrai si quelque chose a changé (rien n'est écrit sinon)."""
    chemin = Path(chemin)
    brut = json.loads(chemin.read_text(encoding="utf-8-sig"))
    d = json.loads(json.dumps(brut))
    if isinstance(d.get("flux"), list):
        d["flux"] = transformer(d["flux"], "")
    for w in d.get("workflows") or []:
        if isinstance(w, dict) and isinstance(w.get("flux"), list):
            w["flux"] = transformer(w["flux"], _prefixe(w))
    if d == brut:
        return False
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fichier:
            json.dump(d, fichier, ensure_ascii=False, indent=2)
            fichier.write("\n")
        fa.lire(tmp)           # le fichier tel qu'il serait : refusé (FactoryInvalide) avant de remplacer quoi que ce soit
        os.replace(tmp, chemin)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return True


def decouper_au_projet(chemin, propose):
    """Applique une proposition (déjà vérifiée sur `flux_de_reference`) à tous les workflows du projet. Rend vrai si le
    fichier a changé."""
    return _ecrire(chemin, lambda flux, prefixe: appliquer(flux, propose, prefixe))


def regler_au_projet(chemin, etape, lieu):
    """Le `lieu` (`local`, `indifférent`, ou `None` : retiré, le métier décide) de l'étape `etape` dans tous les workflows
    qui l'ont (`etape`, ou `<fid>-<etape>` dans le workflow de la fonctionnalité `fid`). Rend vrai si le fichier a
    changé. `ValueError` si l'étape n'existe pas ou est une validation."""
    if lieu is not None and lieu not in LIEUX:
        raise ValueError("« lieu » vaut local, cloud, indifférent ou null.")
    trouvees = []

    def transformer(flux, prefixe):
        sortie = []
        for e in flux:
            if isinstance(e, dict) and e.get("id") in (etape, f"{prefixe}{etape}" if prefixe else etape):
                trouvees.append(e)
                if not wf.est_validation(e):
                    e = dict(e)
                    if lieu is None:
                        e.pop("lieu", None)
                    else:
                        e["lieu"] = lieu
            sortie.append(e)
        return sortie

    brut = json.loads(Path(chemin).read_text(encoding="utf-8-sig"))
    transformer(brut.get("flux") or [], "")
    for w in brut.get("workflows") or []:
        transformer(w.get("flux") or [], _prefixe(w))
    if not trouvees:
        raise ValueError(f"Étape inconnue : {etape}")
    if any(wf.est_validation(e) for e in trouvees):
        raise ValueError(f"« {etape} » est une validation du Directeur : elle n'a pas de lieu.")
    trouvees.clear()
    return _ecrire(chemin, transformer)
