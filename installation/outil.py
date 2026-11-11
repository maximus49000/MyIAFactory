"""La ligne de commande de l'installation sur un projet.

    py -3.12 installation/outil.py preparer [--lier <chemin d'un clone de la skill>]
    py -3.12 installation/outil.py examiner <dossier>
    py -3.12 installation/outil.py calibrer
    py -3.12 installation/outil.py estimer        (entrée JSON : {"flux", "agents", "genre"})
    py -3.12 installation/outil.py proposer       (entrée JSON : la proposition)
    py -3.12 installation/outil.py appliquer <dossier>
    py -3.12 installation/outil.py reparer <dossier> [--tailscale] [--reseau-local]
    py -3.12 installation/outil.py acces          (les adresses du téléphone : Tailscale, réseau local)
    py -3.12 installation/outil.py bureau [--relancer]  (lance le bureau commun en arrière-plan)
    py -3.12 installation/outil.py orchestrateur <dossier>  (ouvre `claude` sur l'orchestrateur, dans une fenêtre)

Sortie JSON UTF-8. Codes : 0 fait, 1 refus (`{"erreur"}`), 2 appel invalide.
Rien n'est écrit dans le dossier du projet avant `appliquer`.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bureau import charge, prix, reglages  # noqa: E402
from installation import acces, calibrage, dossier, estimation, examen, lanceur, mise_en_place, proposition  # noqa: E402
from installation.dossier import Echec  # noqa: E402


class AppelInvalide(Exception):
    pass


def _projets_du_bureau():
    """Les dossiers des réglages des projets du bureau commun (rien s'il est absent ou illisible)."""
    try:
        return [p["chemin"] for p in reglages.lire_bureau(dossier.bureau())["projets"]]
    except (reglages.ReglagesInvalides, OSError):
        return []


def _historique():
    projets = _projets_du_bureau()
    return charge.Historique(projets[0].parent / "charge-historique.jsonl").lire() if projets else []


def _prix_de(modele):
    """Le prix d'un modèle en euros par token, d'après le premier projet du bureau commun qui le connaît."""
    jour = date.today().isoformat()
    for chemin in _projets_du_bureau():
        try:
            regl = reglages.charger(chemin)
        except reglages.ReglagesInvalides:
            continue
        p = prix.prix_effectif(prix.TablePrix(chemin.parent / "prix-historique.jsonl"), regl, modele, jour)[0]
        if p and p.get("entree") and p.get("sortie"):
            return {c: p[c] / 1_000_000 for c in ("entree", "sortie", "cache_lecture", "cache_ecriture")
                    if p.get(c) is not None}
    return None


def _estimer(flux, agents, genre):
    usages = estimation.usages_du_genre(dossier.bureau(), genre)
    try:
        return estimation.estimer(flux, agents, usages, _prix_de)
    except (KeyError, TypeError, AttributeError) as e:
        raise Echec(f"Estimation impossible : flux ou agents mal formés ({e}).")
    except ValueError as e:
        raise Echec(str(e))


def _id_dossier(projet):
    """Un nom de fichier stable pour un dossier : son nom ramené à [a-z0-9-] et une empreinte du chemin."""
    chemin = os.path.normcase(str(Path(projet).expanduser().resolve()))
    nom = unicodedata.normalize("NFKD", Path(chemin).name).encode("ascii", "ignore").decode("ascii").lower()
    nom = re.sub(r"[^a-z0-9]+", "-", nom).strip("-")[:40] or "projet"
    return f"{nom}-{hashlib.sha256(chemin.encode('utf-8')).hexdigest()[:10]}"


def _entree():
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        raise AppelInvalide(f"Entrée JSON illisible : {e}")


def _dossier(texte):
    d = Path(texte).expanduser()
    if not d.is_dir():
        raise Echec(f"Dossier introuvable : {d}")
    return d.resolve()


def cmd_preparer(a):
    return dossier.preparer(lier=a.lier)


def cmd_examiner(a):
    return examen.examiner(_dossier(a.dossier))


def cmd_calibrer(a):
    return calibrage.calibrer(charge.machine(), _historique())


def cmd_estimer(a):
    e = _entree()
    if not isinstance(e, dict):
        raise AppelInvalide("L'entrée doit être un objet {flux, agents, genre}.")
    return _estimer(e.get("flux"), e.get("agents"), e.get("genre"))


def cmd_proposer(a):
    p = _entree()
    erreurs = proposition.verifier(p)
    if erreurs:
        raise Echec("Proposition refusée.", erreurs)
    # L'estimation enregistrée est celle de l'outil, pas celle recopiée par la discussion.
    p["estimation"] = _estimer(p["flux"], p["agents"], p["genre"])
    chemin = dossier.propositions() / f"{_id_dossier(p['projet'])}.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    mise_en_place._ecrire_json(chemin, p)
    return {"proposition": str(chemin), "estimation": p["estimation"], "prerequis_cloud": _prerequis_cloud(p)}


def _prerequis_cloud(p):
    """Quand le cloud est choisi : pourquoi il n'est pas encore possible (le projet n'est pas sur GitHub, `claude` n'est
    pas installé), ou `None`. Ce n'est pas un refus : un projet vide peut créer son dépôt juste après ; sans eux, le moteur
    prend l'agent local équivalent et le dit au bureau."""
    if p.get("cloud") is not True:
        return None
    from moteur import cloud
    return cloud.prerequis(p["projet"])


def cmd_appliquer(a):
    projet = _dossier(a.dossier)
    chemin = dossier.propositions() / f"{_id_dossier(projet)}.json"
    if not chemin.is_file():
        raise Echec("Aucune proposition enregistrée pour ce dossier : lancez « proposer » d'abord.")
    try:
        p = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise Echec(f"La proposition enregistrée est illisible ({chemin}) : {e}")
    if not isinstance(p, dict) or os.path.normcase(str(Path(str(p.get("projet"))).resolve())) != os.path.normcase(str(projet)):
        raise Echec("La proposition enregistrée ne correspond pas à ce dossier : relancez « proposer ».")
    rendu = mise_en_place.appliquer(p, datetime.now())
    chemin.unlink(missing_ok=True)
    return rendu


def _acces_demandes(a):
    """Les accès du téléphone demandés à la réparation, ou None si aucun."""
    if not (a.tailscale or a.reseau_local):
        return None
    return {"tailscale": a.tailscale, "reseau_local": a.reseau_local}


def cmd_reparer(a):
    projet = _dossier(a.dossier)
    cal = calibrage.calibrer(charge.machine(), _historique())
    return {**mise_en_place.reparer(projet, cal, acces=_acces_demandes(a)), "calibrage": cal}


def cmd_acces(a):
    return acces.adresses()


SUGGESTIONS_PAR_BESOIN = 5


def _suggestion(p):
    connexions = sorted({c.get("type") for c in p.get("connexions") or [] if c.get("type")})
    return {"id": p["id"], "nom": p["nom"], "description": p.get("description"), "gratuit": p.get("gratuit"),
            "inscription": p.get("inscription") or p.get("site"), "connexions": connexions,
            "popularite": (p.get("popularite") or {}).get("niveau")}


def cmd_partenaires(a):
    """Détecte les partenaires déjà déclarés (la même chose que `lancer partenaires` `detecter`, sans fichier de
    factory) et, avec `--besoins`, propose les partenaires actifs les plus populaires de chaque besoin. N'écrit rien
    dans le projet (seulement le fichier des connexions de la machine, hors de tout dépôt)."""
    from partenaires import catalogue as pcat, detection, etat
    projet = _dossier(a.dossier)
    cat = pcat.lire()
    try:
        sortie = {"connexions": detection.mettre_a_jour(projet, cat, etat.Etat())}
    except (etat.EtatIllisible, OSError) as e:   # rien ne bloque l'installation : on le dit et on continue
        sortie = {"connexions": {}, "avertissement": str(e)}
    if not a.besoins:
        sortie["besoins"] = {c: sorted({p["sous_categorie"] for p in cat["partenaires"] if p["categorie"] == c})
                             for c in pcat.CATEGORIES}
        return sortie
    sortie["suggestions"] = {}
    for besoin in [b.strip() for b in a.besoins.split(",") if b.strip()]:
        actifs = [p for p in cat["partenaires"] if p.get("statut") == "actif"
                  and besoin in (p.get("sous_categorie"), p.get("categorie"))]
        actifs.sort(key=lambda p: -((p.get("popularite") or {}).get("niveau") or 0))   # tri stable : ordre du catalogue
        sortie["suggestions"][besoin] = [_suggestion(p) for p in actifs[:SUGGESTIONS_PAR_BESOIN]]
    return sortie


def cmd_bureau(a):
    return lanceur.lancer(relancer=a.relancer)


def cmd_orchestrateur(a):
    from bureau import demarrage
    r = demarrage.demarrer(_dossier(a.dossier) / ".factory" / "reglages.json")
    if not r["ok"] and "a_copier" not in r:
        raise Echec(r["message"])
    return r


def _analyseur():
    p = argparse.ArgumentParser(prog="installation/outil.py", description="L'installation de MyIAFactory sur un projet.")
    s = p.add_subparsers(dest="commande", required=True)
    x = s.add_parser("preparer", help="crée ou met à jour le dossier stable ~/MyIAFactory")
    x.add_argument("--lier", help="un clone existant de la skill vers lequel pointer")
    x.set_defaults(f=cmd_preparer)
    for nom, f, aide in (("examiner", cmd_examiner, "vide, existant ou déjà installé"),
                         ("appliquer", cmd_appliquer, "met en place la proposition enregistrée pour ce dossier"),
                         ("reparer", cmd_reparer, "vérifie et répare une installation"),
                         ("orchestrateur", cmd_orchestrateur, "ouvre `claude` sur l'orchestrateur, dans une fenêtre")):
        x = s.add_parser(nom, help=aide)
        x.add_argument("dossier")
        x.set_defaults(f=f)
        if nom == "reparer":
            x.add_argument("--tailscale", action="store_true", help="ouvre le bureau au téléphone par Tailscale")
            x.add_argument("--reseau-local", action="store_true", help="ouvre le bureau au Wi-Fi de la maison")
    x = s.add_parser("bureau", help="lance le bureau commun en arrière-plan (ou le relance)")
    x.add_argument("--relancer", action="store_true", help="arrête le bureau lancé par l'installation, puis le relance")
    x.set_defaults(f=cmd_bureau)
    x = s.add_parser("partenaires", help="partenaires déjà déclarés ; avec --besoins, ceux à proposer")
    x.add_argument("dossier")
    x.add_argument("--besoins", help="sous-catégories ou catégories du catalogue, séparées par des virgules")
    x.set_defaults(f=cmd_partenaires)
    for nom, f, aide in (("calibrer", cmd_calibrer, "charge maximum et agents locaux en parallèle"),
                         ("estimer", cmd_estimer, "coût d'un élément (entrée JSON {flux, agents, genre})"),
                         ("proposer", cmd_proposer, "contrôle et enregistre une proposition (entrée JSON)"),
                         ("acces", cmd_acces, "adresses Tailscale et réseau local de la machine")):
        s.add_parser(nom, help=aide).set_defaults(f=f)
    return p


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    a = _analyseur().parse_args(argv)   # appel invalide : argparse sort avec le code 2

    def ecrire(objet):
        print(json.dumps(objet, ensure_ascii=False, indent=1))

    try:
        ecrire(a.f(a))
        return 0
    except AppelInvalide as e:
        ecrire({"erreur": str(e)})
        return 2
    except Echec as e:
        sortie = {"erreur": str(e.args[0]) if e.args else "Refusé."}
        if len(e.args) > 1:
            sortie["erreurs"] = e.args[1]
        ecrire(sortie)
        return 1


if __name__ == "__main__":
    sys.exit(main())
