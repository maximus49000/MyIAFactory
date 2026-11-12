"""Le vérificateur d'interface : lance chaque commande de l'interface par `lancer` et contrôle sa sortie.

    py -3.12 orchestrateur/verifier_interface.py --factory <fichier de factory> [--complet]

Sans `--complet`, seules les commandes qui ne changent rien sont lancées. Avec `--complet`, toutes le sont : à ne
faire que sur une **copie** du projet (il refuse si le dossier du fichier de factory est dans un dépôt git et n'est
pas marqué par un fichier `.copie-de-verification`).

Une ligne par commande : `ok <commande>`, `ÉCART <commande> : <l'écart>` ou `ignoré <commande> : <pourquoi>`.
Code de sortie : 0 tout est conforme, 1 au moins un écart, 2 appel invalide ou refus d'usage.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bureau import releve as rel  # noqa: E402
from orchestrateur import factory as fa  # noqa: E402
from orchestrateur import workflows as wf  # noqa: E402

OUTIL = Path(__file__).resolve().parent / "outil.py"
MARQUE = ".copie-de-verification"
DELAI_S = 360


class Ecart(Exception):
    pass


def lancer(chemin, commande, entree=None, args=()):
    """(code, objet) en lançant `outil.py lancer <commande>` comme le fait un orchestrateur."""
    corps = None if entree is None else json.dumps(entree, ensure_ascii=False).encode("utf-8")
    try:
        p = subprocess.run([sys.executable, str(OUTIL), "--factory", str(chemin), "lancer", commande, *args],
                           input=corps, stdin=None if corps is not None else subprocess.DEVNULL,
                           capture_output=True, timeout=DELAI_S,
                           env={**os.environ, "MYIAFACTORY_VERIFICATION": "1"})   # pas une présence d'orchestrateur
    except subprocess.TimeoutExpired:
        raise Ecart(f"plus de {DELAI_S} s sans réponse")
    sortie = p.stdout.decode("utf-8", "replace").strip()
    try:
        objet = json.loads(sortie) if sortie else None
    except ValueError:
        objet = sortie
    return p.returncode, objet


def _forme(objet, champs, nom="la sortie"):
    """Contrôle les champs d'un objet : `{nom: type | (types…) | None pour « n'importe quoi »}`."""
    if not isinstance(objet, dict):
        raise Ecart(f"{nom} doit être un objet JSON (reçu : {type(objet).__name__})")
    for cle, types in champs.items():
        if cle not in objet:
            raise Ecart(f"champ « {cle} » absent")
        if types is not None and not isinstance(objet[cle], types):
            raise Ecart(f"champ « {cle} » : mauvais type ({type(objet[cle]).__name__})")
    return objet


def _ok(chemin, commande, entree=None, champs=None, args=(), apres=None):
    code, objet = lancer(chemin, commande, entree, args)
    if code != 0:
        raise Ecart(f"code {code} au lieu de 0" + (f" ({objet.get('erreur')})" if isinstance(objet, dict) and objet.get("erreur")
                                                  else f" ({str(objet)[:80]})" if objet else ""))
    if champs is not None:
        _forme(objet, champs)
    if apres:
        apres(objet)
    return objet


def _refus(chemin, commande, entree, args=()):
    """Une entrée que la commande doit refuser : code 1 et un message (`{"erreur"}`, ou du texte pour `actions`)."""
    code, objet = lancer(chemin, commande, entree, args)
    if code != 1:
        raise Ecart(f"code {code} au lieu de 1 pour une entrée à refuser")
    message = objet.get("erreur") if isinstance(objet, dict) else objet
    if not isinstance(message, str) or not message.strip():
        raise Ecart("un refus doit s'accompagner d'un message (« erreur »)")


def _releve_v4(objet):
    erreurs = rel.valider(objet)
    if erreurs:
        raise Ecart("relevé invalide : " + erreurs[0])
    if objet.get("version") != 4:
        raise Ecart("« version » doit valoir 4")


def _liste_de_dicts(champ, *cles):
    def controle(objet):
        for x in objet[champ]:
            _forme(x, {c: None for c in cles}, f"un élément de « {champ} »")
    return controle


# --- Les commandes qui ne changent rien.

def verifier_lecture(chemin, etat):
    """Rend [(libellé, fonction)] ; chaque fonction lève `Ecart` ou `Ignore`."""
    agents, taches, fonctionnalites = etat["agents"], etat["taches"], etat["fonctionnalites"]

    def releve():
        _ok(chemin, "releve", apres=_releve_v4)

    def etat_():
        _ok(chemin, "etat", champs={"genre": None, "fonctionnalites": list, "taches": list, "decisions": list,
                                    "lecons": list, "agents": list, "file": dict},
            apres=_liste_de_dicts("agents", "cle", "role", "service", "modele", "lieu", "libre"))

    def demandes():
        _ok(chemin, "demandes", champs={"demandes": list})

    def memoire():
        if not agents:
            raise Ignore("aucun agent dans le suivi")
        _ok(chemin, "memoire", {"role": agents[0]["role"]}, {"skill": list, "genre": list})
        _refus(chemin, "memoire", {})

    def genre():
        _ok(chemin, "genre", {"action": "lister"}, {"genre": None, "genres": list},
            apres=_liste_de_dicts("genres", "id"))

    def agent_libre():
        if not agents:
            raise Ignore("aucun agent dans le suivi")
        _ok(chemin, "agent-libre", {"role": agents[0]["role"]}, {"agent": None, "raison": str})
        _refus(chemin, "agent-libre", {})

    def depart_():
        if not agents or not taches:
            raise Ignore("il faut un agent et une tâche dans le suivi")
        _ok(chemin, "depart", {"agent": agents[0]["cle"], "tache": taches[0]["id"]}, {"message": str},
            apres=lambda o: o["message"].strip() or (_ for _ in ()).throw(Ecart("« message » est vide")))
        _refus(chemin, "depart", {"agent": "inconnu-verification", "tache": "inconnue-verification"})

    def lots():
        _ok(chemin, "lots", {}, {"lots": list, "tailles": dict, "ecartees": list},
            apres=_liste_de_dicts("lots", "lot", "modele", "lieu", "taches"))
        _refus(chemin, "lots", {"taches": ["inconnue-verification"]})

    def catalogue():
        if not fonctionnalites:
            raise Ignore("aucune fonctionnalité dans le suivi")
        _ok(chemin, "catalogue", {"fonctionnalite": fonctionnalites[0]["id"]}, {"elements": list},
            apres=_liste_de_dicts("elements", "id", "nom"))
        _refus(chemin, "catalogue", {"fonctionnalite": "inconnue-verification"})

    return [("releve", releve), ("etat", etat_), ("demandes", demandes), ("memoire", memoire),
            ("genre lister", genre), ("agent-libre", agent_libre), ("depart", depart_), ("lots", lots),
            ("catalogue", catalogue)]


class Ignore(Exception):
    pass


# --- Les commandes qui changent quelque chose : un petit scénario, sur une copie.

def verifier_complet(chemin, etat):
    agents = etat["agents"]
    pris = {}

    def actions():
        _ok(chemin, "actions", {"type": "fonctionnalite", "texte": "Vérification de l'interface",
                                "t": "2026-11-10T10:00:00+01:00"}, {"ok": None, "id": str},
            apres=lambda o: pris.update(demande=o["id"]))
        _refus(chemin, "actions", {"type": "type-inconnu-verification"})
        lu = lancer(chemin, "etat")[1]
        pris["fonc"] = lu["fonctionnalites"][-1]["id"]

    def reveil():
        _ok(chemin, "reveil", champs={"reveil": str})

    def demande_traitee():
        _ok(chemin, "demande-traitee", {"id": pris["demande"], "reponse": "Vu"}, {"ok": None})
        _refus(chemin, "demande-traitee", {"id": "inconnue-verification"})

    def fonctionnalite():
        _ok(chemin, "fonctionnalite", {"id": pris["fonc"], "nom": "Vérification"}, {"id": str})
        _refus(chemin, "fonctionnalite", {"id": "inconnue-verification"})

    def message():
        auteur = agents[0]["cle"] if agents else "utilisateur"
        _ok(chemin, "message", {"fonctionnalite": pris["fonc"], "auteur": auteur, "texte": "Réponse de vérification"},
            {"id": str})
        _refus(chemin, "message", {"fonctionnalite": "inconnue-verification", "auteur": auteur, "texte": "x"})

    def decision():
        d = _ok(chemin, "decision", {"action": "poser", "portee": pris["fonc"], "genre": "valider_cahier",
                                     "texte": "Vérification"}, {"id": str})
        _ok(chemin, "decision", {"action": "lever", "id": d["id"]}, {"ok": None})
        _refus(chemin, "decision", {"action": "lever", "id": "inconnue-verification"})

    def tache():
        t = _ok(chemin, "tache", {"titre": "Tâche de vérification", "fonctionnalite": pris["fonc"],
                                  "element": "verif-1"}, {"id": str, "titre": str})
        pris["tache"] = t["id"]
        _ok(chemin, "tache", {"id": t["id"], "journal": "Vérifié", "active": False}, {"id": str})
        _refus(chemin, "tache", {"id": "inconnue-verification", "etape": "x"})

    def file():
        _ok(chemin, "file", {"fonctionnalite": pris["fonc"],
                             "elements": [{"id": "verif-1", "nom": "Élément 1"}, {"id": "verif-2", "nom": "Élément 2"}]},
            {"elements": int})
        _refus(chemin, "file", {"fonctionnalite": "inconnue-verification", "elements": []})

    def file_prendre():
        o = _ok(chemin, "file-prendre", {"fonctionnalite": pris["fonc"]}, {"element": None})
        if not isinstance(o["element"], dict) or o["element"].get("id") != "verif-1":
            raise Ecart("« element » doit être le premier élément de la file")
        _refus(chemin, "file-prendre", {"fonctionnalite": "inconnue-verification"})

    def session():
        if not agents:
            raise Ignore("aucun agent dans le suivi")
        _ok(chemin, "session", {"agent": agents[0]["cle"], "session": "Session de vérification"}, {"ok": None})
        _refus(chemin, "session", {"agent": "inconnu-verification", "session": "x"})

    def lecon():
        if not agents:
            raise Ignore("aucun agent dans le suivi")
        n = _ok(chemin, "lecon", {"action": "noter", "agent": agents[0]["cle"], "texte": "Leçon de vérification",
                                  "etage_propose": "projet", "roles": ["tous"]}, {"id": str})
        _ok(chemin, "lecon", {"action": "appliquer", "id": n["id"], "verdict": "invalider"}, {"ok": None})
        _refus(chemin, "lecon", {"action": "appliquer", "id": "inconnue-verification", "verdict": "valider"})

    def controle():
        _ok(chemin, "controle", {"texte": "Contrôle de vérification", "origine": "verifier_interface"},
            {"numero": int})

    def charge():
        _ok(chemin, "charge", champs={"feu_vert": bool, "texte": str})

    def genre_fixer():
        courant = etat.get("genre")
        if not courant:
            raise Ignore("le projet n'a pas de genre : « genre fixer » n'est pas essayé")
        _ok(chemin, "genre", {"action": "fixer", "genre": courant}, {"genre": str})

    def organisation():
        f = fa.lire(chemin)
        nouveau = "verification-organisation"
        if any(x["id"] == nouveau for x in f["services"]):
            raise Ignore("le scénario a déjà été joué sur cette copie")
        o = {"services": [{"id": x["id"], "nom": x["nom"]} for x in f["services"]] + [{"id": nouveau, "nom": "Vérification"}],
             "flux": [wf.etape_ecrite(x) for x in f["flux"]]
                     + [{"id": nouveau, "nom": "Vérification", "role": nouveau, "service": nouveau}],
             "agents": [{"cle": nouveau + "-1", "role": nouveau, "service": nouveau, "modele": "Haiku", "lieu": "local",
                         "texte": "Agent de vérification."}],
             "briefs": {nouveau: "# Brief de vérification"}, "cout": {"tokens": [1, 2], "euros": None}}
        _refus(chemin, "organisation", {"action": "appliquer", "decision": "inconnue-verification"})
        code, objet = lancer(chemin, "decision", {"action": "poser", "portee": "projet", "genre": "organisation",
                                                  "texte": "Vérification", "organisation": o})
        if code == 1:   # l'organisation actuelle du projet ne passe pas son propre contrôle (rôle sans agent ou brief)
            raise Ignore("l'organisation actuelle ne passe pas le contrôle : " + str(objet.get("erreur"))[:100])
        if code != 0:
            raise Ecart(f"code {code} au lieu de 0 pour poser une décision d'organisation")
        _ok(chemin, "organisation", {"action": "appliquer", "decision": objet["id"]},
            {"ok": None, "services": list, "flux": list})
        if any(d.get("genre") == "organisation" for d in lancer(chemin, "etat")[1].get("decisions", [])):
            raise Ecart("la décision n'est pas levée après « appliquer »")

    return [("actions", actions), ("reveil", reveil), ("demande-traitee", demande_traitee),
            ("fonctionnalite", fonctionnalite), ("message", message), ("decision", decision), ("tache", tache),
            ("file", file), ("file-prendre", file_prendre), ("session", session), ("lecon", lecon),
            ("controle", controle), ("charge", charge), ("genre fixer", genre_fixer),
            ("organisation", organisation)]


def _dans_un_depot_git(dossier):
    try:
        p = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(dossier), capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0 and p.stdout.strip() == b"true"


def main(argv=None):
    p = argparse.ArgumentParser(prog="verifier_interface.py", description="Contrôle les commandes de l'interface.")
    p.add_argument("--factory", required=True, help="le fichier de factory du projet")
    p.add_argument("--complet", action="store_true",
                   help="lance aussi les commandes qui changent quelque chose (sur une copie du projet seulement)")
    a = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        f = fa.lire(a.factory)
    except fa.FactoryInvalide as e:
        print(f"Fichier de factory illisible : {e}")
        return 2
    if a.complet and _dans_un_depot_git(f["base"]) and not (f["base"] / MARQUE).exists():
        print(f"Refusé : --complet change le suivi, les fiches et les mémoires ; ce dossier est dans un dépôt git. "
              f"Lancer sur une copie du projet, marquée par un fichier « {MARQUE} » dans le dossier du fichier de factory.")
        return 2
    chemin = f["chemin"]
    ecarts = 0
    if a.complet:   # d'abord le scénario : il crée de quoi essayer ensuite le départ et le catalogue
        for libelle, fonction in verifier_complet(chemin, _etat(chemin)):
            ecarts += _jouer(libelle, fonction)
    for libelle, fonction in verifier_lecture(chemin, _etat(chemin)):
        ecarts += _jouer(libelle, fonction)
    return 1 if ecarts else 0


def _etat(chemin):
    """L'état du suivi (pour choisir de quoi essayer) ; vide si la commande `etat` est elle-même en défaut."""
    vide = {"agents": [], "taches": [], "fonctionnalites": [], "genre": None}
    try:
        code, etat = lancer(chemin, "etat")
    except Ecart:
        return vide
    if code != 0 or not isinstance(etat, dict) or not all(isinstance(etat.get(c), list)
                                                          for c in ("agents", "taches", "fonctionnalites")):
        return vide
    return etat


def _jouer(libelle, fonction):
    try:
        fonction()
    except Ecart as e:
        print(f"ÉCART {libelle} : {e}")
        return 1
    except Ignore as e:
        print(f"ignoré {libelle} : {e}")
        return 0
    except (KeyError, IndexError, TypeError) as e:
        print(f"ÉCART {libelle} : sortie inattendue ({type(e).__name__} {e})")
        return 1
    print(f"ok {libelle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
