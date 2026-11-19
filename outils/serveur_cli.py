"""Ligne de commande générique des serveurs distants : `lancer.py plateforme serveurs <commande> ...`.

Mêmes moteurs que le bureau (`serveur_modele`, `serveur_etat`, `serveur_installation`). Codes de sortie : 0 ok, 1 échec ou
bloqué, 2 usage. La sortie est masquée (clés OVH, licence, chemins de clés) ; `cle` n'affiche que la ligne PUBLIQUE.
`installer` n'agit que si `--accord` figure sur la ligne de commande ; sinon il affiche l'aperçu et sort avec le code 1.
"""
import json
import os
import re
import sys
from pathlib import Path

import plateforme
import plateforme_acces
import serveur_capacites
import serveur_etat
import serveur_installation
import serveur_modele

USAGE = ("Usage : lancer.py plateforme serveurs <declarer <nom> <hote> <utilisateur> [--fournisseur ovh] | lister | cle <id> | "
         "sonder <id> | apercu <id> <action>... | installer <id> <action>... [--accord]> [--dossier <d>]")
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
MAX_ACTIONS = 20
COMMANDES = ("declarer", "lister", "cle", "sonder", "apercu", "installer")


def _dossier(brut):
    if brut:
        return Path(brut)
    env = os.environ.get("MYIAFACTORY_PLATEFORME")
    return Path(env) if env else plateforme_acces.DOSSIER


def _masquer_texte(texte, d, serveurs=()):
    c = plateforme._Contexte(d, False, None, None, None)
    c.preparer_secrets()
    c.secrets += [str(s.cle) for s in serveurs if len(str(s.cle)) >= 8]
    return c.masquer(str(texte))


def _sortie(valeur, d, serveurs=()):
    """JSON indenté ; chaque texte est masqué avant la sérialisation."""
    c = plateforme._Contexte(d, False, None, None, None)
    c.preparer_secrets()
    c.secrets += [str(s.cle) for s in serveurs if len(str(s.cle)) >= 8]
    return c.masquer(json.dumps(c.masquer_arbre(valeur), ensure_ascii=False, indent=2))


def _erreur(message, code, d, serveurs=()):
    print(_masquer_texte(message, d, serveurs), file=sys.stderr)
    return code


def _analyser(args):
    """(positionnels, options) ; `None` si une option est inconnue ou incomplète."""
    pos, opts, reste = [], {"accord": False, "fournisseur": None, "dossier": None}, list(args)
    while reste:
        a = reste.pop(0)
        if a == "--accord":
            opts["accord"] = True
        elif a in ("--fournisseur", "--dossier") and reste:
            opts[a[2:]] = reste.pop(0)
        elif a.startswith("-"):
            return None
        else:
            pos.append(a)
    return pos, opts


def _capacites(etat_serveur):
    brut = etat_serveur.get("capacites") if isinstance(etat_serveur, dict) else None
    brut = brut if isinstance(brut, dict) else {}
    return {i: (brut[i]["statut"] if isinstance(brut.get(i), dict) and isinstance(brut[i].get("statut"), str) else "inconnue")
            for i in serveur_capacites.CATALOGUE}


def _fiche(s, etat):
    inst = etat.get(s.id, {}).get("installation") if isinstance(etat.get(s.id), dict) else None
    return {"id": s.id, "nom": s.nom, "hote": s.hote, "utilisateur": s.utilisateur, "fournisseur": s.fournisseur,
            "capacites": _capacites(etat.get(s.id, {})),
            "installation_en_cours": isinstance(inst, dict) and inst.get("en_cours") is True}


def _ligne(d, serveur, runner):
    return serveur_modele.ligne_cle_publique(d, serveur, **({"runner": runner} if runner else {}))


def _declarer(pos, opts, d, runner):
    if len(pos) != 3:
        return _erreur(USAGE, 2, d)
    champs = {"nom": pos[0], "hote": pos[1], "utilisateur": pos[2], "fournisseur": opts["fournisseur"]}   # rien d'autre
    try:
        serveur = serveur_modele.ajouter(champs, d)
    except ValueError as e:
        return _erreur(str(e), 1, d)
    fiche, code = _fiche(serveur, {}), 0
    try:
        fiche["ligne_cle_publique"] = _ligne(d, serveur, runner)
    except Exception:
        fiche["avertissement"] = "Le serveur est déclaré, mais la clé SSH n'a pas pu être créée : lancez la commande cle."
        code = 1
    print(_sortie({"serveur": fiche}, d, [serveur]))
    return code


def _lister(d):
    serveurs, rejets = serveur_modele.lire_avec_rejets(d)
    etat = serveur_installation.lire_etat_vivant(d)
    print(_sortie({"serveurs": [_fiche(s, etat) for s in serveurs], "rejets": list(rejets)}, d, serveurs))
    return 0


def main(argv, ssh=None, runner=None, installer=None, dossier=None):
    """`ssh`, `runner` et `installer` s'injectent dans les essais (jamais de connexion réelle ni de vrai `ssh-keygen`)."""
    analyse = _analyser(argv)
    if analyse is None or not analyse[0]:
        return _erreur(USAGE, 2, _dossier(dossier))
    pos, opts = analyse
    d = _dossier(opts["dossier"] or dossier)
    commande, reste = pos[0], pos[1:]
    if commande not in COMMANDES:
        return _erreur(f"Commande inconnue : « {commande[:40]} ».\n{USAGE}", 2, d)
    if (opts["fournisseur"] and commande != "declarer") or (opts["accord"] and commande != "installer"):
        return _erreur(USAGE, 2, d)
    try:
        if commande == "declarer":
            return _declarer(reste, opts, d, runner)
        if commande == "lister":
            return _lister(d) if not reste else _erreur(USAGE, 2, d)
        seul = commande in ("cle", "sonder")
        if (seul and len(reste) != 1) or (not seul and len(reste) < 2) or len(reste) - 1 > MAX_ACTIONS:
            return _erreur(USAGE, 2, d)
        ident, actions = reste[0], reste[1:]
        if not SLUG.fullmatch(ident) or not all(SLUG.fullmatch(a) for a in actions):
            return _erreur("Identifiant ou action invalide : lettres minuscules, chiffres, « - » et « _ » seulement.", 2, d)
        serveurs, _ = serveur_modele.lire_avec_rejets(d)
        serveur = next((s for s in serveurs if s.id == ident), None)
        if serveur is None:
            return _erreur(f"Serveur inconnu : « {ident} ». Voir `plateforme serveurs lister`.", 1, d, serveurs)
        return _agir(commande, serveur, actions, opts, d, serveurs, ssh, runner, installer)
    except (serveur_installation.ErreurInstallation, ValueError, RuntimeError, OSError) as e:
        return _erreur(f"{e} {getattr(e, 'geste', '')}".strip() or type(e).__name__, 1, d)
    except Exception as e:      # jamais de trace : le type seul, rien qui pourrait citer un secret
        return _erreur(f"Opération interrompue ({type(e).__name__}).", 1, d)


def _agir(commande, serveur, actions, opts, d, serveurs, ssh, runner, installer):
    options = {} if ssh is None else {"ssh": ssh}
    if commande == "cle":
        print(_masquer_texte(_ligne(d, serveur, runner), d, serveurs))
        return 0
    if commande == "sonder":
        etat = serveur_etat.sonder(serveur, **options)
        joint = not all(s == "inconnue" for s in etat.values())
        charge = serveur_etat.charge(serveur, **options) if joint else None
        serveur_installation.enregistrer_sonde(d, serveur, etat, charge=charge)
        print(_sortie({"id": serveur.id, "capacites": etat, "joignable": joint}, d, serveurs))
        return 0 if joint else 1
    try:
        serveur_capacites.manquantes_pour(actions, set())
    except ValueError as e:
        return _erreur(str(e), 2, d, serveurs)
    resultat = serveur_installation.apercu(serveur, actions, dossier=d, **options)
    if commande == "apercu":
        print(_sortie(resultat, d, serveurs))
        return 1 if resultat.get("erreur") else 0
    if not opts["accord"]:      # aucun accord sur la ligne de commande : l'aperçu seulement, rien n'est installé
        print(_sortie({"apercu": resultat, "installe": False,
                       "message": "Rien n'a été installé : relancez avec --accord pour valider cet aperçu."}, d, serveurs))
        return 1
    r = (installer or serveur_installation.installer)(serveur, actions, True, dossier=d, **options)
    r = r if isinstance(r, dict) else {}
    ok = r.get("ok") is True and not r.get("erreur")
    print(_sortie({"id": serveur.id, "ok": ok, "erreur": r.get("erreur"), "capacites": r.get("capacites", {})}, d, serveurs))
    return 0 if ok else 1
