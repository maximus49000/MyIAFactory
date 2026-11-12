"""Les routes de « Nouveau projet… » en deux fenêtres : les brouillons de l'échange avec le chef.

Chaque fonction rend `(code HTTP, objet JSON)`. Le bureau (`srv`) porte ce qui s'injecte dans les essais :
`dossier_creations` et `commun_creations` (où sont les brouillons et les usages abandonnés), `appeler_jugement`,
`verifier_environnement`, `executer_outil`, `prix_de_modele`, `executer_git`, `executer_gh`. Un tour d'échange
s'exécute en arrière-plan (`definition.lancer_tour`) : la route répond tout de suite, la page relit le brouillon.
Rien n'est écrit hors du brouillon avant `valider`.
"""
import os
import threading
from datetime import datetime

from . import reglages

LONGUEUR_DESCRIPTION = 4000
LONGUEUR_REPONSES = 40
SANS_BUREAU = ("Ce bureau n'est pas lancé sur le fichier du bureau commun : on ne peut pas y créer de projet.")
_EN_CREATION = set()          # les brouillons dont la validation tourne (deux clics : une seule création)
_VERROU = threading.Lock()


def _outils(srv):
    from installation import brouillons, definition, estimation
    return brouillons, definition, estimation


def _prix(srv):
    """Le prix d'un modèle, lu une fois par modèle et par appel de route (le fichier des prix n'est pas relu cent fois)."""
    from installation import estimation
    source = srv.prix_de_modele or (lambda m: estimation.prix_de_modele(srv.fichier_bureau, m))
    memo = {}

    def prix_de(modele):
        if modele not in memo:
            memo[modele] = source(modele)
        return memo[modele]
    return prix_de


def _vue(srv, b):
    _, definition, _ = _outils(srv)
    return definition.vue(b, _prix(srv))


def _couche(srv):
    from moteur import appel
    try:
        return appel.choisir_couche(reglages.lire_bureau(srv.fichier_bureau), os.environ)[0]
    except (reglages.ReglagesInvalides, OSError):
        return "claude"


def _garde(srv):
    return None if srv.fichier_bureau is not None else (409, {"erreur": SANS_BUREAU})


def _texte(corps, cle, obligatoire=False):
    """(valeur, message) : un texte (ou absent)."""
    v = corps.get(cle)
    if v is None and not obligatoire:
        return None, None
    if not isinstance(v, str):
        return None, f"« {cle} » est obligatoire." if obligatoire else f"« {cle} » doit être un texte."
    return v, None


def _brouillon_de(srv, corps):
    brouillons, _, _ = _outils(srv)
    from installation.dossier import Echec
    id_, erreur = _texte(corps, "id", True)
    if erreur:
        raise Echec(erreur)
    return brouillons.lire(id_, dossier=srv.dossier_creations)


def _erreur(e):
    """Le code d'un refus de l'installation : un tour déjà en cours est un conflit, le reste une demande à corriger."""
    from installation import brouillons
    return (409 if isinstance(e, brouillons.TourEnCours) else 400), {"erreur": str(e)}


# --- GET.

def liste(srv, id_=None):
    """`GET /api/creations` : les brouillons et le coût des échanges abandonnés ; avec `?id=` : un brouillon (la page
    le relit pendant un tour)."""
    if (refus := _garde(srv)) is not None:
        return refus
    brouillons, definition, _ = _outils(srv)
    from installation.dossier import Echec
    prix_de = _prix(srv)
    if id_ is not None:
        try:
            return 200, {"brouillon": definition.vue(brouillons.lire(id_, dossier=srv.dossier_creations), prix_de)}
        except Echec as e:
            return 404, {"erreur": str(e)}
    try:
        brouillons.purger(maintenant=datetime.now(), dossier=srv.dossier_creations, commun=srv.commun_creations)
    except OSError:
        pass
    lignes = []
    for x in brouillons.lister(dossier=srv.dossier_creations):
        try:
            usages = brouillons.lire(x["id"], dossier=srv.dossier_creations).get("usages") or []
        except Echec:
            continue
        c = definition.cout_echange(usages, prix_de)
        lignes.append(dict(x, euros=c["euros"], **({"co2": c["co2"]} if c.get("co2") else {})))
    abandonnes = definition.cout_echange(brouillons.usages_abandonnes(commun=srv.commun_creations), prix_de)
    return 200, {"brouillons": lignes,
                 "abandonnes": {"euros": abandonnes["euros"], "tokens": abandonnes["tokens"],
                                **({"co2": abandonnes["co2"]} if abandonnes.get("co2") else {})}}


def lignes_sujets(srv, debut, fin):
    """Les usages des échanges de création (brouillons vivants, puis abandonnés) datés dans [debut, fin], placés dans
    l'arbre des sujets (voir `sujets.py`). Rien sans fichier de bureau commun."""
    from . import sujets
    if srv.fichier_bureau is None:
        return []
    brouillons, _, estimation = _outils(srv)
    prix_de = _prix(srv)

    def euros_de(u):
        p = prix_de(u.get("modele"))
        return estimation._euros_usage(u, p) if p and p.get("entree") and p.get("sortie") else None

    lignes = []
    for x in brouillons.lister(dossier=srv.dossier_creations):
        try:
            usages = brouillons.lire(x["id"], dossier=srv.dossier_creations).get("usages") or []
        except Exception:
            continue
        lignes += sujets.lignes_creation(x["id"], x["nom"] or "Projet en création", usages, euros_de, debut, fin)
    lignes += sujets.lignes_creation("abandonnes", "Échanges abandonnés",
                                     brouillons.usages_abandonnes(commun=srv.commun_creations), euros_de, debut, fin)
    return lignes


# --- POST.

def infos(srv, corps):
    """`POST /api/creations/infos` : la première fenêtre, validée. Crée le brouillon, ou change les informations de
    celui de `id` (échange gardé). Rien d'autre n'est écrit."""
    if (refus := _garde(srv)) is not None:
        return refus
    brouillons, definition, _ = _outils(srv)
    from installation import creation
    from installation.dossier import Echec
    for cle in ("parent", "nom", "description"):
        _, erreur = _texte(corps, cle, True)
        if erreur:
            return 400, {"erreur": erreur}
    mots = corps.get("mots_interdits", [])
    if not isinstance(mots, list) or not all(isinstance(m, str) for m in mots):
        return 400, {"erreur": "« mots_interdits » doit être une liste de textes."}
    for cle in ("facturation", "github"):
        if not isinstance(corps.get(cle, False), bool):
            return 400, {"erreur": f"« {cle} » doit valoir vrai ou faux."}
    description = corps["description"].strip()
    if not description:
        return 400, {"erreur": "Décrivez le projet : la description est obligatoire, c'est la base de l'échange avec le chef."}
    if len(description) > LONGUEUR_DESCRIPTION:
        return 400, {"erreur": f"La description est trop longue ({LONGUEUR_DESCRIPTION} caractères au plus)."}
    if corps.get("id") is not None and not isinstance(corps["id"], str):
        return 400, {"erreur": "« id » doit être un texte."}
    try:
        nom = creation.verifier_nom(corps["nom"])
        nouvelles = {"parent": corps["parent"], "nom": nom, "mots_interdits": [m.strip() for m in mots if m.strip()],
                     "facturation": bool(corps.get("facturation", False)), "github": bool(corps.get("github", False)),
                     "description": description}
        definition._verifier_les_infos(nouvelles, srv.fichier_bureau)
        with brouillons._VERROU:
            if corps.get("id") is None:
                b = brouillons.creer(nouvelles, dossier=srv.dossier_creations)
            else:
                b = brouillons.lire(corps["id"], dossier=srv.dossier_creations)
                if brouillons.etat_du_tour(b) == "en_cours":
                    raise brouillons.TourEnCours("Un tour est en cours : attendez la réponse du chef avant de changer "
                                                 "les informations.")
                if b["echange"] and bool(b["infos"].get("facturation")) != nouvelles["facturation"]:
                    raise Echec("La facturation ne se change plus une fois l'échange commencé : le chef a déjà "
                                "organisé le projet avec ou sans elle.")
                b["infos"] = nouvelles
                brouillons.ecrire(b, dossier=srv.dossier_creations)
    except Echec as e:
        return _erreur(e)
    return 200, {"brouillon": _vue(srv, b)}


def tour(srv, corps):
    """`POST /api/creations/tour` : un tour de l'échange, lancé en arrière-plan ; rend le brouillon marqué en cours."""
    if (refus := _garde(srv)) is not None:
        return refus
    _, definition, _ = _outils(srv)
    from installation.dossier import Echec
    from moteur import appel, environnement
    reponses, correction = corps.get("reponses"), corps.get("correction")
    if reponses is not None and not (isinstance(reponses, list) and len(reponses) <= LONGUEUR_REPONSES
                                     and all(isinstance(r, dict) for r in reponses)):
        return 400, {"erreur": "« reponses » doit être une liste de réponses."}
    if correction is not None and not isinstance(correction, str):
        return 400, {"erreur": "« correction » doit être un texte."}
    if not isinstance(corps.get("proposer_maintenant", False), bool):
        return 400, {"erreur": "« proposer_maintenant » doit valoir vrai ou faux."}
    try:
        id_, erreur = _texte(corps, "id", True)
        if erreur:
            return 400, {"erreur": erreur}
        b = definition.lancer_tour(
            id_, reponses=reponses, correction=correction, proposer_maintenant=bool(corps.get("proposer_maintenant")),
            genres_connus=srv._genres_pour_le_chef(), couche=_couche(srv),
            appeler=srv.appeler_jugement or appel.appeler,
            verifier_environnement=srv.verifier_environnement or environnement.verifier, prix_de=_prix(srv),
            dossier=srv.dossier_creations)
    except Echec as e:
        return _erreur(e)
    except Exception as e:   # jamais une connexion coupée sans réponse lisible
        return 500, {"erreur": f"Erreur du bureau : {e}"[:200]}
    return 200, {"brouillon": _vue(srv, b)}


def valider(srv, corps):
    """`POST /api/creations/valider` : l'utilisateur valide la proposition, le projet est créé et inscrit."""
    if (refus := _garde(srv)) is not None:
        return refus
    brouillons, definition, _ = _outils(srv)
    from installation.dossier import Echec
    fable = corps.get("fable", [])
    if not isinstance(fable, list) or not all(isinstance(c, str) for c in fable):
        return 400, {"erreur": "« fable » doit être une liste de clés d'agents."}
    if not isinstance(corps.get("installer", False), bool):
        return 400, {"erreur": "« installer » doit valoir vrai ou faux."}
    genre_description, erreur = _texte(corps, "genre_description")
    if erreur:
        return 400, {"erreur": erreur}
    id_ = corps.get("id")
    with _VERROU:
        if id_ in _EN_CREATION:
            return 409, {"erreur": "La création de ce projet est déjà en cours."}
        _EN_CREATION.add(id_)
    try:
        b = _brouillon_de(srv, corps)
        options = {}
        if srv.executer_outil:
            options["executer"] = srv.executer_outil
        if srv.executer_git:
            options["git"] = srv.executer_git
        if srv.executer_gh:
            options["gh"] = srv.executer_gh
        fait = definition.valider(b, fable=fable, installer=bool(corps.get("installer")),
                                  genre_description=genre_description, bureau_json=srv.fichier_bureau,
                                  dossier=srv.dossier_creations, commun=srv.commun_creations, **options)
    except definition.InfosAChanger as e:
        return 409, {"erreur": str(e), "retour": "infos"}
    except Echec as e:
        return _erreur(e)
    except Exception as e:
        return 500, {"erreur": f"Erreur du bureau : {e}"[:200]}
    finally:
        with _VERROU:
            _EN_CREATION.discard(id_)
    srv.projets_vus_a = None
    srv.actualiser_projets()
    return 200, {"ok": True, "projet": fait["id"], "github": fait["github"], "message": fait["message"]}


def supprimer(srv, corps):
    """`POST /api/creations/supprimer` : le brouillon est abandonné ; ses usages restent comptés."""
    if (refus := _garde(srv)) is not None:
        return refus
    brouillons, _, _ = _outils(srv)
    from installation.dossier import Echec
    try:
        id_, erreur = _texte(corps, "id", True)
        if erreur:
            return 400, {"erreur": erreur}
        brouillons.abandonner(id_, dossier=srv.dossier_creations, commun=srv.commun_creations)
    except Echec as e:
        return _erreur(e)
    return 200, {"ok": True}
