"""Les appels de jugement : un appel d'IA court, à contexte neuf, qui rend une décision structurée.

Chaque type a sa consigne (`moteur/consignes/<type>.md`) et son modèle (`TYPES`). Le moteur prépare un **dossier** borné
(un dict, jamais son historique), sérialisé une fois en JSON comme message ; la réponse est un objet JSON validé
(`valider`) avant toute action. Une réponse invalide (ou un appel raté) est redemandée une fois avec l'erreur
(`CLE_ERREUR` ajoutée au dossier) ; un second échec devient une **question au Directeur** (`Decision.question`).

Dossiers attendus (préparés par la table de règles) :
- `decouper` : `fonctionnalite` (nom, cahier : maquette, étapes), `flux`, `methodes_validees` (fonctionnalité,
  version, élément, flux, résumé), `consignes_propres` ;
- `traduire_retour` : `message` (texte, images), `element`, `dernier_tour` (ce que l'agent a montré), `cahier` ;
- `ecrire_methode` : `fonctionnalite`, `cahier`, `flux` (rôles), `prototype` (discussion du prototype, retours,
  rapports), `controles` déjà au registre ;
- `apres_refus` : `element`, `refus` (contrôle ou verdicts de relecture), `tours`, `seuil_methode`, `methode` ;
- `conseil` : `evenement`, `etat` court de la fonctionnalité, `consignes_propres`, `commandes` permises.
"""
import json
import re
from pathlib import Path

from moteur import appel
from orchestrateur.outil import COMMANDES, COMMANDES_DU_BUREAU

DOSSIER_CONSIGNES = Path(__file__).resolve().parent / "consignes"
TYPES = {"decouper": "sonnet", "traduire_retour": "haiku", "ecrire_methode": "sonnet", "apres_refus": "haiku",
         "conseil": "haiku"}
LIBELLES = {"decouper": "découper la fonctionnalité en éléments", "traduire_retour": "comprendre votre retour",
            "ecrire_methode": "écrire la méthode", "apres_refus": "décider de la suite après un refus",
            "conseil": "choisir quoi faire de cette demande"}
ACTIONS_CONSEIL = ("repondre", "transmettre_agent", "poser_decision", "lancer", "rien")
COMMANDES_INTERDITES_AU_CONSEIL = frozenset(COMMANDES_DU_BUREAU) | {"lecon", "genre"}
SUITES_APRES_REFUS = ("corriger", "methode_a_revoir", "bloquer")
CLE_ERREUR = "erreur_de_ta_reponse_precedente"


class Decision:
    """Exactement un de `objet` (la réponse validée) et `question` (à poser au Directeur) est non nul ; `usages`
    garde l'usage de chaque appel, réussi ou non."""

    def __init__(self, objet=None, usages=None, question=None):
        if (objet is None) == (question is None):
            raise ValueError("Une décision porte soit un objet, soit une question.")
        self.objet, self.usages, self.question = objet, usages or [], question

    def __repr__(self):
        return f"Decision(objet={self.objet!r}, question={self.question!r}, usages={len(self.usages)})"


def consigne(type_):
    return (DOSSIER_CONSIGNES / f"{type_}.md").read_text(encoding="utf-8")


def _texte_du_dossier(dossier):
    return json.dumps(dossier, ensure_ascii=False, indent=1)


def juger(type_, dossier, *, couche, appeler=appel.appeler, modele=None):
    """Un jugement : au plus deux appels ; rend une `Decision`."""
    if type_ not in TYPES:
        raise ValueError(f"Type de jugement inconnu : {type_}")
    m = modele or TYPES[type_]
    if "fable" in str(m).lower():
        raise appel.ErreurAppel("Le moteur ne choisit jamais Fable.")
    texte_consigne = consigne(type_)
    usages, erreur = [], None
    for essai in range(2):
        envoye = dossier if erreur is None else {**dossier, CLE_ERREUR: erreur}
        try:
            r = appeler(texte_consigne, _texte_du_dossier(envoye), m, couche=couche)
        except appel.ErreurAppel as e:
            usages += e.usages
            erreur = f"L'appel a échoué : {e.raison}"
            continue
        usages += r.usages
        objet = extraire_json(r.texte)
        erreur = ("Ta réponse ne contient pas d'objet JSON lisible." if objet is None
                  else valider(type_, objet))
        if erreur is None:
            return Decision(objet=objet, usages=usages)
    return Decision(usages=usages, question=(
        f"Je n'ai pas réussi à {LIBELLES[type_]} : deux essais sans réponse utilisable (dernière erreur : {erreur}). "
        "Pouvez-vous préciser ce qu'il faut faire, ou relancer ?"))


# --- Lire la réponse.

_BLOC = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)```", re.DOTALL)


def _objet(texte):
    try:
        v = json.loads(texte)
    except (json.JSONDecodeError, TypeError):
        return None
    return v if isinstance(v, dict) else None


def extraire_json(texte):
    """L'objet JSON d'une réponse : le dernier bloc ```json lisible, sinon le texte entier, sinon ce qui va de la
    première accolade à la dernière. `None` si rien n'est lisible."""
    texte = texte or ""
    for bloc in reversed(_BLOC.findall(texte)):
        v = _objet(bloc.strip())
        if v is not None:
            return v
    v = _objet(texte.strip())
    if v is not None:
        return v
    debut, fin = texte.find("{"), texte.rfind("}")
    return _objet(texte[debut:fin + 1]) if 0 <= debut < fin else None


# --- Valider la réponse : rend le message d'erreur (pour le second essai) ou None.

def _texte(v):
    return isinstance(v, str) and v.strip() != ""


def valider(type_, objet):
    if not isinstance(objet, dict):
        return "La réponse doit être un objet JSON."
    return _VALIDEURS[type_](objet)


def _valider_decouper(o):
    elements = o.get("elements")
    if not isinstance(elements, list) or not elements:
        return "« elements » doit être une liste non vide."
    ids = []
    for e in elements:
        if not isinstance(e, dict) or not all(_texte(e.get(c)) for c in ("id", "nom", "groupe")):
            return "Chaque élément doit avoir « id », « nom » et « groupe » (textes non vides)."
        if "/" in e["id"]:
            return f"L'identifiant « {e['id']} » ne doit pas contenir « / »."
        if e["id"] in ids:
            return f"L'identifiant « {e['id']} » est en double."
        ids.append(e["id"])
    if o.get("prototype") not in ids:
        return "« prototype » doit être l'« id » d'un des éléments."
    depend = o.get("depend_de")
    if not isinstance(depend, dict):
        return "« depend_de » doit être un objet {id: [id, …]} (vide s'il n'y a pas de dépendance)."
    for cle, liste in depend.items():
        if cle not in ids or not isinstance(liste, list) or any(x not in ids for x in liste):
            return f"« depend_de » ne doit citer que des « id » d'éléments ({cle})."
    reprise = o.get("reprendre_methode")
    if reprise is not None:
        if not (isinstance(reprise, dict) and _texte(reprise.get("fonctionnalite")) and _texte(reprise.get("pourquoi"))
                and isinstance(reprise.get("version"), int) and not isinstance(reprise.get("version"), bool)
                and reprise["version"] >= 1):
            return "« reprendre_methode » est null ou {fonctionnalite, version (entier ≥ 1), pourquoi}."
    if not _texte(o.get("message")):
        return "« message » (le découpage dit à l'utilisateur) est obligatoire."
    return None


def _valider_traduire_retour(o):
    if not isinstance(o.get("validation"), bool):
        return "« validation » doit être true ou false."
    c = o.get("consigne")
    if not o["validation"] and not _texte(c):
        return "« consigne » est obligatoire quand « validation » est false."
    if c is not None and not isinstance(c, str):
        return "« consigne » est un texte ou null."
    return None


def _valider_ecrire_methode(o):
    if not _texte(o.get("document")):
        return "« document » (la méthode en Markdown) est obligatoire."
    briefs = o.get("briefs")
    if not isinstance(briefs, dict) or not briefs or not all(_texte(k) and _texte(v) for k, v in briefs.items()):
        return "« briefs » doit donner un texte non vide pour chaque rôle."
    controles = o.get("controles")
    if not isinstance(controles, list) or not all(
            isinstance(c, dict) and _texte(c.get("texte")) and _texte(c.get("origine")) for c in controles):
        return "« controles » est une liste de {texte, origine} (textes non vides)."
    return None


def _valider_apres_refus(o):
    if o.get("suite") not in SUITES_APRES_REFUS:
        return f"« suite » doit être l'une de : {', '.join(SUITES_APRES_REFUS)}."
    c = o.get("consigne")
    if o["suite"] == "corriger" and not _texte(c):
        return "« consigne » est obligatoire quand « suite » vaut corriger."
    if c is not None and not isinstance(c, str):
        return "« consigne » est un texte ou null."
    if not _texte(o.get("raison")):
        return "« raison » est obligatoire."
    return None


def _valider_conseil(o):
    action, p = o.get("action"), o.get("parametres")
    if action not in ACTIONS_CONSEIL:
        return f"« action » doit être l'une de : {', '.join(ACTIONS_CONSEIL)}."
    if not isinstance(p, dict):
        return "« parametres » doit être un objet (vide si l'action n'en prend pas)."
    if not isinstance(o.get("reponse"), str):
        return "« reponse » doit être un texte."
    if action == "repondre" and not _texte(o["reponse"]):
        return "« reponse » est obligatoire pour l'action repondre."
    if action == "transmettre_agent" and not _texte(p.get("consigne")):
        return "transmettre_agent exige « parametres.consigne »."
    if action == "poser_decision" and not _texte(p.get("texte")):
        return "poser_decision exige « parametres.texte »."
    if action == "lancer":
        commande = p.get("commande")
        if commande not in COMMANDES:
            return f"lancer exige « parametres.commande », une commande connue (pas « {commande} »)."
        if commande in COMMANDES_INTERDITES_AU_CONSEIL:
            return f"La commande « {commande} » n'est pas permise au conseil."
        if not isinstance(p.get("entree", {}), dict):
            return "« parametres.entree » doit être un objet."
    return None


_VALIDEURS = {"decouper": _valider_decouper, "traduire_retour": _valider_traduire_retour,
              "ecrire_methode": _valider_ecrire_methode, "apres_refus": _valider_apres_refus,
              "conseil": _valider_conseil}
