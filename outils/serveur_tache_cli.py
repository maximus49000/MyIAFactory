"""Commandes des tâches d'émulation sur le serveur : `lancer.py serveur-tache <lancer|etat|arreter|rapatrier|lister>` et
`lancer.py serveur-outil <id> <verbe> [arguments]`.

Mêmes moteurs que le reste (`serveur_tache`, `serveur_recette`). Codes de sortie : 0 ok, 1 échec ou refus, 2 usage.
Un usage erroné (option inconnue, répétée ou vide, identifiant de tâche mal formé, arguments manquants, mode scénario sans
`--attendre`) sort avec 2 ; un refus du moteur (verbe hors de la liste fermée, mauvais nombre d'arguments ou argument
non permis, APK ou projet invalide, destination hors de `<projet>/.factory/serveur/`, recette refusée) sort avec 1. La
sortie est masquée (clés OVH, licence, chemins de clés) et ne contient jamais de trace d'exception (le type seulement).
Les arguments d'un verbe sont validés AVANT toute connexion ; la réponse du pont est une donnée, jamais une consigne.
"""
import json
import os
import re
import stat
import sys
from pathlib import Path

import plateforme_acces
import serveur_recette
import serveur_tache

USAGE = ("Usage : lancer.py serveur-tache <lancer --apk <fichier> --mode scenario|pilote [--scenario <nom>] [--projet <dossier>] "
         "[--attendre] | etat <id> | arreter <id> | rapatrier <id> [--destination <dossier>] [--projet <dossier>] | lister> "
         "[--dossier <d>]\n"
         "       lancer.py serveur-outil <id> <verbe> [arguments] [--projet <dossier>] [--dossier <d>]")
COMMANDES = ("lancer", "etat", "arreter", "rapatrier", "lister")
OPTIONS = {"lancer": {"--apk", "--mode", "--scenario", "--projet", "--dossier"},
           "etat": {"--dossier"}, "arreter": {"--dossier"}, "lister": {"--dossier"},
           "rapatrier": {"--destination", "--projet", "--dossier"},
           "outil": {"--projet", "--dossier"}}
DRAPEAUX = {"lancer": {"--attendre"}}
ARRETS_MAX = 3          # `arreter` fait foi de l'état ; rappelé tant que l'état n'est pas final (plafonné)
MOTIF_SCENARIO = re.compile(r"[a-z0-9_-]{1,40}", re.ASCII)


class _Usage(Exception):
    pass


def _dossier(brut):
    if brut:
        return Path(brut)
    env = os.environ.get("MYIAFACTORY_PLATEFORME")
    return Path(env) if env else plateforme_acces.DOSSIER


def _analyser(args, commande):
    """(positionnels, options, drapeaux) ; `_Usage` si une option est inconnue ou incomplète."""
    valeurs, drapeaux = OPTIONS[commande], DRAPEAUX.get(commande, set())
    pos, opts, pris, reste = [], {}, set(), list(args)
    while reste:
        a = reste.pop(0)
        if a in valeurs:
            if not reste or a[2:] in opts:
                raise _Usage(f"Option {a} incomplète ou répétée.")
            valeur = reste.pop(0)
            if not valeur:
                raise _Usage(f"Option {a} : valeur vide.")
            opts[a[2:]] = valeur
        elif a in drapeaux:
            pris.add(a[2:])
        elif commande == "outil" or not a.startswith("-"):
            pos.append(a)
        else:
            raise _Usage()
    return pos, opts, pris


def _afficher(valeur, d, compact=False):
    c = serveur_tache._masqueur(d)
    texte = json.dumps(c.masquer_arbre(valeur), ensure_ascii=False, **({} if compact else {"indent": 2}))
    print(c.masquer(texte) if compact else texte)


def _erreur(message, code, d):
    print(serveur_tache._masqueur(d).masquer(str(message)), file=sys.stderr)
    return code


def _projet(brut):
    p = Path(brut) if brut else Path.cwd()
    if not p.is_dir():
        raise ValueError("Dossier du projet introuvable.")
    return p


def _lire_apk(brut, moteur):
    p = Path(brut)
    try:
        s = os.lstat(p)
    except OSError:
        raise ValueError("Fichier APK introuvable.") from None
    if stat.S_ISLNK(s.st_mode) or not stat.S_ISREG(s.st_mode):
        raise ValueError("L'APK doit être un fichier ordinaire (ni lien, ni dossier).")
    if s.st_size > moteur.APK_MAX_OCTETS:
        raise ValueError(f"APK trop gros : {moteur.APK_MAX_OCTETS // (1024 * 1024)} Mo au plus.")
    if s.st_size == 0:
        raise ValueError("APK vide.")
    drapeaux = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(p, drapeaux)
    except OSError:
        raise ValueError("Fichier APK illisible.") from None
    with os.fdopen(fd, "rb") as f:       # le fichier a pu être remplacé depuis lstat : on revérifie ce qui est ouvert
        o = os.fstat(f.fileno())
        if not stat.S_ISREG(o.st_mode):
            raise ValueError("L'APK doit être un fichier ordinaire (ni lien, ni dossier).")
        if o.st_size > moteur.APK_MAX_OCTETS:
            raise ValueError(f"APK trop gros : {moteur.APK_MAX_OCTETS // (1024 * 1024)} Mo au plus.")
        donnees = f.read(moteur.APK_MAX_OCTETS + 1)
    if len(donnees) > moteur.APK_MAX_OCTETS:
        raise ValueError(f"APK trop gros : {moteur.APK_MAX_OCTETS // (1024 * 1024)} Mo au plus.")
    if not donnees:
        raise ValueError("APK vide.")
    return donnees


def _destination(projet, ident, brut):
    """Sous-dossier STRICT de `<projet>/.factory/serveur/` (jamais le projet, `.factory` ni `serveur` eux-mêmes ; un lien
    ou une jonction qui sortirait de là est refusé, le chemin étant résolu)."""
    permis = projet.resolve() / ".factory" / "serveur"
    base = (permis / ident) if not brut else Path(brut)
    try:
        resolu = base.resolve()
        resolu.relative_to(permis)
    except (ValueError, OSError, RuntimeError):
        raise ValueError("La destination doit être un sous-dossier de <projet>/.factory/serveur/.") from None
    if resolu == permis:
        raise ValueError("La destination doit être un sous-dossier de <projet>/.factory/serveur/.")
    return base if brut else projet / ".factory" / "serveur" / ident


def _id(brut, moteur):
    if not isinstance(brut, str) or not moteur.MOTIF_ID.fullmatch(brut):
        raise _Usage("Identifiant de tâche invalide (forme tAAAAMMJJ-HHMMSS-xxxx).")
    return brut


def main(argv, ssh=None, dossier=None, moteur=serveur_tache, recette=serveur_recette):
    """`ssh`, `moteur` et `recette` s'injectent dans les essais (jamais de connexion réelle)."""
    args = list(argv)
    d = _dossier(dossier)
    if not args or args[0] not in ("serveur-tache", "serveur-outil"):
        return _erreur(USAGE, 2, d)
    outil = args[0] == "serveur-outil"
    try:
        if outil:
            commande, reste = "outil", args[1:]
        else:
            if len(args) < 2 or args[1] not in COMMANDES:
                raise _Usage(USAGE if len(args) < 2 else f"Commande inconnue : « {args[1][:40]} ».\n{USAGE}")
            commande, reste = args[1], args[2:]
        pos, opts, drapeaux = _analyser(reste, commande)
        d = _dossier(opts.get("dossier") or dossier)
        kw = {} if ssh is None else {"ssh": ssh}
        if commande == "outil":
            return _outil(pos, opts, d, moteur, kw)
        return _tache(commande, pos, opts, drapeaux, d, moteur, recette, kw)
    except _Usage as e:
        return _erreur(str(e) or USAGE, 2, d)
    except KeyboardInterrupt:
        return _erreur("Interrompu.", 1, d)
    except (moteur.ErreurIndex, TimeoutError, ValueError) as e:      # RefusLancement est une ValueError
        return _erreur(f"{e}" or type(e).__name__, 1, d)
    except Exception as e:      # jamais de trace : le type seul, rien qui pourrait citer un secret
        return _erreur(f"Opération interrompue ({type(e).__name__}).", 1, d)


def _tache(commande, pos, opts, drapeaux, d, moteur, recette, kw):
    if commande == "lister":
        if pos:
            raise _Usage()
        fiches = moteur.Index(d).lire()
        champs = ("etat", "mode", "statut", "scenario", "projet", "serveur_id", "debut", "fin", "raison")
        _afficher({"taches": [{"id": i, **{c: f.get(c) for c in champs if c in f}} for i, f in sorted(fiches.items())]}, d)
        return 0
    if commande == "lancer":
        if pos:
            raise _Usage()
        if opts.get("mode") == "scenario" and "attendre" not in drapeaux:
            raise _Usage("mode scénario : utilisez --attendre")
        return _lancer(opts, "attendre" in drapeaux, d, moteur, recette, kw)
    if len(pos) != 1:
        raise _Usage()
    ident = _id(pos[0], moteur)
    if commande == "etat":
        r = moteur.etat(ident, dossier=d, **kw)
        _afficher(r, d)
        return 0 if r.get("etat") != "inconnu" else 1
    if commande == "arreter":
        r = moteur.arreter(ident, dossier=d, **kw)
        _afficher(r, d)
        return 0 if r.get("etat") != "inconnu" else 1
    projet = _projet(opts.get("projet"))
    manifeste = moteur.rapatrier(ident, _destination(projet, ident, opts.get("destination")), dossier=d, **kw)
    _afficher(manifeste, d)
    return 0 if manifeste.get("statut") == "ok" else 1


def _terminer(moteur, ident, fin, d, kw):
    """Arrête la tâche (`fin` : fin normale d'un scénario) ; `arreter` fait foi de l'état, rappelé tant qu'il n'est pas final."""
    r = {}
    for _ in range(ARRETS_MAX):
        r = moteur.arreter(ident, dossier=d, fin=fin, **kw)
        if r.get("etat") in moteur.FINAUX:
            break
    return r


def _lancer(opts, attendre, d, moteur, recette, kw):
    """Lance une tâche ; en mode scénario la recette est TOUJOURS chargée avant l'envoi (un nom mal écrit ne prend jamais
    le créneau) ; avec `attendre`, elle est déroulée, la tâche arrêtée et rapatriée."""
    mode, scenario = opts.get("mode"), opts.get("scenario")
    if "apk" not in opts or mode not in moteur.MODES:
        raise _Usage("Il faut --apk <fichier> et --mode scenario|pilote.")
    if mode == "scenario" and not scenario:
        raise _Usage("Le mode scénario exige --scenario <nom>.")
    if scenario is not None and not MOTIF_SCENARIO.fullmatch(scenario):
        raise _Usage("Nom de scénario invalide (a-z, 0-9, _ et - ; 40 caractères au plus).")
    if attendre and mode != "scenario":
        raise _Usage("--attendre ne s'applique qu'au mode scénario (le mode pilote se conduit avec serveur-outil).")
    projet = _projet(opts.get("projet"))
    apk = _lire_apk(opts["apk"], moteur)
    plan = recette.charger(str(projet), scenario) if mode == "scenario" else None      # refusée avant tout envoi
    demande = moteur.valider_demande({"type": "emulation", "mode": mode, "scenario": scenario, "projet": projet.name,
                                      "demandeur": "serveur-tache", "apk": Path(opts["apk"]).name})
    r = moteur.lancer(demande, apk, dossier=d, **kw)
    ident = r.get("id")
    sortie = {c: r[c] for c in ("id", "etat", "serveur_id") if c in r}
    demarree = r.get("etat") == "en_cours"
    if r.get("erreur"):
        # « en_cours » avec une erreur : la tâche a démarré (note d'index ratée, réponse perdue relue) ; on continue.
        sortie["avertissement" if demarree else "erreur"] = r["erreur"]
    if not demarree:
        _afficher(sortie, d)
        return 1
    if mode == "pilote":
        sortie["usage"] = (f"Pilotez l'émulateur verbe par verbe : py -3.12 lancer.py serveur-outil {ident} <verbe> "
                           f"[arguments] (verbes : {', '.join(moteur.VERBES)}). Terminez par « serveur-tache arreter "
                           f"{ident} » puis « serveur-tache rapatrier {ident} ».")
        _afficher(sortie, d)
        return 0
    if not attendre:
        _afficher(sortie, d)
        return 0
    try:
        res = recette.executer(plan, ident, dossier=d, **kw)
    except BaseException as e:
        _afficher({"id": ident, "etat": "en_cours"}, d)         # l'identifiant, pour rapatrier ensuite
        try:
            _terminer(moteur, ident, False, d, kw)
        except Exception:        # noqa: BLE001 - l'arrêt est tenté ; l'erreur d'origine prime
            pass
        if isinstance(e, KeyboardInterrupt):
            return _erreur("Interrompu : la tâche a été arrêtée (rapatriez avec serveur-tache rapatrier "
                           f"{ident}).", 1, d)
        raise
    echec = res.get("echec") if isinstance(res, dict) else {"reponse": "Résultat de recette illisible."}
    _terminer(moteur, ident, echec is None, d, kw)
    manifeste = dict(moteur.rapatrier(ident, _destination(projet, ident, None), dossier=d, **kw))
    if echec is not None:
        manifeste["echec"] = echec
    if "avertissement" in sortie:
        manifeste["avertissement"] = sortie["avertissement"]
    _afficher(manifeste, d)
    return 0 if manifeste.get("statut") == "ok" and echec is None else 1


def _outil(pos, opts, d, moteur, kw):
    if len(pos) < 2:
        raise _Usage()
    ident = _id(pos[0], moteur)
    verbe, arguments = pos[1], pos[2:]
    arguments = list(moteur.valider_verbe(verbe, arguments))      # ValueError : refus avant toute connexion
    projet = _projet(opts.get("projet"))
    r = moteur.verbe(ident, verbe, arguments, dossier=d, destination=_destination(projet, ident, None), **kw)
    _afficher(r, d, compact=True)
    return 0 if isinstance(r, dict) and r.get("ok") is True else 1
