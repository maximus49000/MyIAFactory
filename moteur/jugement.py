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
- `conseil` : `evenement`, `etat` court de la fonctionnalité, `consignes_propres`, `commandes` permises ;
- `classer_genre` : `demande` (texte, images ; ou la description d'un projet créé sans genre), `projet` (nom,
  description), `genres_du_projet` ([{id, domaine, livrable, outils}], ceux de ses workflows), `genres_connus`
  (`memoire.genres` de la skill), `mots_interdits` du projet ;
- `proposer_organisation` : `demande`, `genre`, `projet` (nom, description), `services` ([{id, nom}]), `agents`
  ([{cle, role, modele, specialite}]), `regles_projet` (les textes des règles du projet, absent sans règle), `workflows_du_genre` ([{id, flux}], le plus récent d'abord), `fonctionnalite`
  (son id : le moteur préfixe chaque `etape` par `<id>-`), `refus` (texte du Directeur ou null) ;
- `definir_workflow` (appelé par le bureau, avant que le projet n'existe) : `projet` (nom, description, facturation,
  github), `genres_connus`, `mots_interdits` (le nom du projet en fait partie), `services` ([{id, nom}], la facturation
  si elle est demandée), `echange` ([{auteur: chef, message, questions} | {auteur: utilisateur, reponses: [{question,
  texte}]}]), `tours_de_questions`, `tours_max`, `proposer_maintenant`, `proposition_precedente`, `correction`.

Une étape de flux peut être une validation du Directeur, `{etape, nom, validation: true, raison?}` : ni rôle ni
service, ni première, ni dernière, ni deux de suite.

La validation de `classer_genre`, `proposer_organisation` et `definir_workflow` lit le dossier (genres connus, mots
interdits, agents et services du projet, tours de questions) : la réponse ne peut citer que ce qui existe, ou le
proposer.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from moteur import appel
from orchestrateur.factory import MOTIF_GENRE, MOTIF_ID, RESERVES
from orchestrateur.memoire import mots_trouves, normaliser_mot
from orchestrateur.outil import COMMANDES, COMMANDES_DU_BUREAU

DOSSIER_CONSIGNES = Path(__file__).resolve().parent / "consignes"
TYPES = {"decouper": "sonnet", "traduire_retour": "haiku", "ecrire_methode": "sonnet", "apres_refus": "haiku",
         "conseil": "haiku", "classer_genre": "haiku", "proposer_organisation": "sonnet", "definir_workflow": "sonnet"}
LIBELLES = {"decouper": "découper la fonctionnalité en éléments", "traduire_retour": "comprendre votre retour",
            "ecrire_methode": "écrire la méthode", "apres_refus": "décider de la suite après un refus",
            "conseil": "choisir quoi faire de cette demande", "classer_genre": "classer le genre de cette demande",
            "proposer_organisation": "proposer le workflow de cette fonctionnalité",
            "definir_workflow": "définir le workflow du projet"}
# L'échange de la création d'un projet (`definir_workflow`) : au plus 4 tours de questions, puis une proposition.
TOURS_MAX_DEFINITION = 4
QUESTIONS_PAR_TOUR_MAX = 5
CHOIX_PAR_QUESTION_MAX = 6
LONGUEUR_CHOIX = 80               # une réponse proposée tient sur un bouton
LONGUEUR_ID_QUESTION = 40
FONCTIONNALITE_TYPE = "f999"      # les étapes du workflow de création doivent tenir une fois préfixées par `f999-`
MOTIF_VERSION = re.compile(r"^\d+(?:\.\d+)*\Z")
LONGUEUR_VERSION = 20
OBJECTIF_MAX = 300                # l'objectif d'un élément du découpage : une phrase, rappelée à sa validation
ACTIONS_CONSEIL = ("repondre", "transmettre_agent", "poser_decision", "lancer", "rien")
COMMANDES_INTERDITES_AU_CONSEIL = frozenset(COMMANDES_DU_BUREAU) | {"lecon", "genre", "fiche", "regles"}
SUITES_APRES_REFUS = ("corriger", "methode_a_revoir", "bloquer")
VERDICTS_GENRE = ("meme", "proche", "autre", "incertain")
LONGUEUR_ELARGISSEMENT = 300      # la description d'un genre élargie à une demande, rendue par le classement
LONGUEUR_INTITULE = 60           # le nom court d'une fonctionnalité, rendu par le classement de la demande
MODELES_AGENT = ("Haiku", "Sonnet", "Opus")   # jamais Fable : il n'est que suggéré (`fable_suggere`)
LONGUEUR_JUSTIFICATION = 160      # la justification du modèle nécessaire d'une étape : une ligne courte
# Ce que dit le nom d'une étape qui remet le livrable (comparé sans accents ni casse).
MOTS_DE_LIVRAISON = ("livr", "remis", "remet", "remise", "publi", "depos", "depot", "export", "envoi", "deploi",
                     "mise en ligne")
MOTIF_EXECUTABLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")   # un nom à chercher dans le PATH, rien d'autre
MOTIF_REGLE_OUTIL = re.compile(r"^(Bash|PowerShell)\([A-Za-z0-9][A-Za-z0-9._-]*(:\*| [^()\r\n*]+)\)\Z")
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
                  else valider(type_, objet, dossier))
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


def valider(type_, objet, dossier=None):
    """`dossier` : celui envoyé au jugement ; `classer_genre` et `proposer_organisation` le lisent."""
    if not isinstance(objet, dict):
        return "La réponse doit être un objet JSON."
    if type_ in _VALIDEURS_AVEC_DOSSIER:
        return _VALIDEURS_AVEC_DOSSIER[type_](objet, dossier if isinstance(dossier, dict) else {})
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
        if "validations" in e and not (isinstance(e["validations"], list) and all(_texte(x) for x in e["validations"])):
            return (f"« validations » de « {e['id']} » : la liste des « id » des étapes de validation qui le concernent "
                    "(vide si aucune).")
        if "objectif" in e and not (_texte(e["objectif"]) and len(e["objectif"]) <= OBJECTIF_MAX):
            return f"« objectif » de « {e['id']} » : une phrase de {OBJECTIF_MAX} caractères au plus."
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


def _ligne(v):
    return _texte(v) and "\n" not in v and "\r" not in v


def _ids_genres(liste):
    """Les identifiants d'une liste de genres du dossier ([{id, …}] ou [id])."""
    ids = []
    for g in liste if isinstance(liste, list) else []:
        i = g.get("id") if isinstance(g, dict) else g
        if isinstance(i, str) and i not in ids:
            ids.append(i)
    return ids


def _valider_classer_genre(o, d):
    verdict, genre, nouveau = o.get("verdict"), o.get("genre"), o.get("nouveau")
    if verdict not in VERDICTS_GENRE:
        return f"« verdict » doit être l'un de : {', '.join(VERDICTS_GENRE)}."
    if not _texte(o.get("raison")):
        return "« raison » (une phrase pour l'utilisateur) est obligatoire."
    intitule = o.get("intitule")
    if intitule is not None and not (_ligne(intitule) and len(intitule.strip()) <= LONGUEUR_INTITULE):
        return f"« intitule » est null ou un nom court de la fonctionnalité sur une ligne ({LONGUEUR_INTITULE} caractères au plus)."
    if o.get("coherente") is not None and not isinstance(o["coherente"], bool):
        return "« coherente » est vrai, faux ou null (la demande a-t-elle sa place dans ce projet ?)."
    elargissement = o.get("elargissement")
    if elargissement is not None:
        if not (_ligne(elargissement) and len(elargissement.strip()) <= LONGUEUR_ELARGISSEMENT):
            return (f"« elargissement » est null ou la description du genre du projet élargie à cette demande, sur une "
                    f"ligne ({LONGUEUR_ELARGISSEMENT} caractères au plus).")
        if mots_trouves(elargissement, d.get("mots_interdits") or []):
            return "« elargissement » contient un mot interdit du projet : un genre est public, décris-le sans nom propre."
    du_projet = _ids_genres(d.get("genres_du_projet"))
    connus = du_projet + [g for g in _ids_genres(d.get("genres_connus")) if g not in du_projet]
    if genre is not None and genre not in connus:
        return (f"« genre » doit être l'id d'un genre du dossier ({', '.join(connus) or 'aucun'}) ou null, pas "
                f"« {genre} » ; un genre qui n'existe pas encore va dans « nouveau ».")
    if nouveau is not None:
        if verdict in ("meme", "proche"):
            return f"« nouveau » vaut null quand le verdict est {verdict}."
        if not (isinstance(nouveau, dict) and isinstance(nouveau.get("id"), str) and MOTIF_GENRE.match(nouveau["id"])
                and _ligne(nouveau.get("description"))):
            return ("« nouveau » est null ou {id (minuscules, chiffres, tirets, 40 caractères au plus), "
                    "description (une ligne)}.")
        if nouveau["id"] in connus:
            return f"Le genre « {nouveau['id']} » existe déjà : mets-le dans « genre » et « nouveau » à null."
        interdits = mots_trouves(f"{nouveau['id']} {nouveau['description']}", d.get("mots_interdits") or [])
        if interdits:
            return (f"« nouveau » contient un mot interdit du projet ({', '.join(interdits)}) : un genre est public, "
                    "décris-le sans nom propre.")
        if genre is not None:
            return "Donne soit « genre » (un genre connu), soit « nouveau », pas les deux."
    if verdict == "meme" and genre not in du_projet:
        return "Le verdict meme exige dans « genre » l'id d'un genre du projet (« genres_du_projet »)."
    if verdict == "proche" and genre is None:
        return "Le verdict proche exige dans « genre » l'id d'un genre connu."
    if verdict == "autre" and genre is None and nouveau is None:
        return "Le verdict autre exige « genre » (un genre connu) ou « nouveau »."
    return None


def _dit_le_livrable(nom, livrable):
    """Le nom de la dernière étape dit qu'elle remet le livrable : un mot de livraison, ou un mot du livrable."""
    n = normaliser_mot(nom)
    if any(m in n for m in MOTS_DE_LIVRAISON):
        return True
    mots = {m for m in re.findall(r"[a-z0-9]+", normaliser_mot(livrable)) if len(m) >= 3}
    return any(m in mots for m in re.findall(r"[a-z0-9]+", n))


def _valider_proposer_organisation(o, d):
    services_projet = [s.get("id") for s in d.get("services") or [] if isinstance(s, dict)]
    agents_projet = [a for a in d.get("agents") or [] if isinstance(a, dict)]
    fonc = d.get("fonctionnalite") if isinstance(d.get("fonctionnalite"), str) else ""
    services = o.get("services")
    if not isinstance(services, list) or not all(isinstance(s, dict) for s in services):
        return "« services » est la liste des nouveaux services {id, nom} (vide s'il n'en faut pas)."
    nouveaux_services = []
    for s in services:
        if not (isinstance(s.get("id"), str) and MOTIF_ID.match(s["id"])) or not _ligne(s.get("nom")):
            return f"Service {s.get('id')!r} : un « id » (minuscules, chiffres, tirets) et un « nom »."
        if s["id"] in services_projet:
            return f"Le service « {s['id']} » existe déjà au projet : ne propose que les nouveaux."
        if s["id"] in nouveaux_services:
            return f"Service « {s['id']} » en double."
        nouveaux_services.append(s["id"])
    tous_services = services_projet + nouveaux_services
    flux = o.get("flux")
    if not isinstance(flux, list) or not flux or not all(isinstance(x, dict) for x in flux):
        return "« flux » doit lister les étapes {etape, nom, role, service}, de la demande au livrable remis."
    etapes, noms, roles_du_flux = [], [], []      # étapes d'agent seulement (les validations n'ont ni rôle ni outil)
    deja = []
    for k, x in enumerate(flux):
        e = x.get("etape")
        if not (isinstance(e, str) and MOTIF_ID.match(e) and MOTIF_ID.match(f"{fonc}-{e}" if fonc else e)) \
                or e in RESERVES:
            return (f"Étape {e!r} : un id court (minuscules, chiffres, tirets), ni « cadrage » ni « fait » ; le "
                    "moteur le préfixe par l'id de la fonctionnalité (40 caractères au plus en tout).")
        if e in deja:
            return f"Étape « {e} » en double."
        deja.append(e)
        if not _ligne(x.get("nom")):
            return f"Étape « {e} » : un « nom » est attendu."
        if x.get("raison") is not None and not _ligne(x["raison"]):
            return f"Étape « {e} » : la « raison » tient sur une ligne."
        if "validation" in x and x["validation"] is not True:
            return f"Étape « {e} » : « validation » vaut true (une validation du Directeur), sinon ne la mets pas."
        if x.get("validation") is True:
            if x.get("role") is not None or x.get("service") is not None or "modele" in x:
                return f"Étape « {e} » : une validation du Directeur n'a ni « role », ni « service », ni « modele »."
            if k == 0:
                return f"Étape « {e} » : une validation du Directeur ne peut pas être la première étape."
            if k == len(flux) - 1:
                return (f"Étape « {e} » : une validation du Directeur ne peut pas être la dernière étape ; la "
                        "dernière remet le livrable.")
            if flux[k - 1].get("validation") is True:
                return f"Étape « {e} » : pas deux validations du Directeur de suite."
            continue
        etapes.append(e)
        noms.append(x["nom"])
        if not (isinstance(x.get("role"), str) and MOTIF_ID.match(x["role"])):
            return f"Étape « {e} » : un « role » (minuscules, chiffres, tirets) est attendu."
        if x["role"] not in roles_du_flux:
            roles_du_flux.append(x["role"])
        if x.get("service") not in tous_services:
            return f"Étape « {e} » : service « {x.get('service')} » ni au projet ni proposé dans « services »."
        if "modele" in x:      # le modèle que demande le travail de l'étape (facultatif : sinon déduit de sa nature)
            if isinstance(x["modele"], str) and "fable" in x["modele"].lower():
                return f"Étape « {e} » : jamais Fable comme modèle d'étape ; au plus Opus."
            if x["modele"] not in MODELES_AGENT:
                return f"Étape « {e} » : « modele » doit valoir {', '.join(MODELES_AGENT)}."
            if not (_ligne(x.get("justification")) and len(x["justification"]) <= LONGUEUR_JUSTIFICATION):
                return (f"Étape « {e} » : « justification » du modèle, une ligne de {LONGUEUR_JUSTIFICATION} "
                        "caractères au plus.")
    if not _texte(o.get("livrable")):
        return "« livrable » (ce qui est remis à l'utilisateur à la fin) est obligatoire."
    if not _dit_le_livrable(flux[-1]["nom"], o["livrable"]):
        return (f"La dernière étape (« {flux[-1]['nom']} ») doit produire ou remettre le livrable, et son nom doit le "
                "dire (par exemple « Livraison de … ») : le workflow va de la demande au livrable remis.")
    agents = o.get("agents")
    if not isinstance(agents, list) or not all(isinstance(a, dict) for a in agents):
        return "« agents » est la liste des nouveaux agents (vide s'il n'en faut pas)."
    cles = [a.get("cle") for a in agents_projet]
    roles = {a.get("role") for a in agents_projet}
    roles_nouveaux = []
    for a in agents:
        c = a.get("cle")
        if not (isinstance(c, str) and MOTIF_ID.match(c)):
            return f"Agent {c!r} : une « cle » (minuscules, chiffres, tirets, 40 caractères au plus)."
        if c in cles:
            return f"Agent « {c} » : clé déjà prise."
        cles.append(c)
        # Un agent proposé est recruté avec le plafond Opus (les modèles justifiés vont sur les étapes) : son
        # « modele » est facultatif, mais jamais Fable ni un nom inconnu.
        if isinstance(a.get("modele"), str) and "fable" in a["modele"].lower():
            return (f"Agent « {c} » : jamais Fable comme modèle ; mets Opus et « fable_suggere »: true si Fable "
                    "serait vraiment utile (le Directeur décidera).")
        if "modele" in a and a["modele"] not in MODELES_AGENT:
            return f"Agent « {c} » : « modele » doit valoir {', '.join(MODELES_AGENT)}."
        if not (isinstance(a.get("role"), str) and MOTIF_ID.match(a["role"])):
            return f"Agent « {c} » : un « role » (minuscules, chiffres, tirets) est attendu."
        roles.add(a["role"])
        if a["role"] not in roles_nouveaux:
            roles_nouveaux.append(a["role"])
        if a.get("service") not in tous_services:
            return f"Agent « {c} » : service « {a.get('service')} » ni au projet ni proposé."
        if "justification" in a and not _ligne(a["justification"]):
            return f"Agent « {c} » : « justification » en une ligne."
        if not _texte(a.get("texte")):
            return f"Agent « {c} » : le « texte » de sa fiche est vide."
        if a.get("prenom") is not None and not _ligne(a["prenom"]):
            return f"Agent « {c} » : « prenom » tient sur une ligne."
        if "fable_suggere" in a and not isinstance(a["fable_suggere"], bool):
            return f"Agent « {c} » : « fable_suggere » vaut true ou false."
    for r in roles_du_flux:
        if r not in roles:
            return f"Aucun agent pour le rôle « {r} » : propose-en un, ou confie l'étape à un rôle du projet."
    briefs = o.get("briefs")
    if not isinstance(briefs, dict) or not all(isinstance(k, str) and _texte(v) for k, v in briefs.items()):
        return "« briefs » associe à chaque nouveau rôle un texte."
    for r in roles_nouveaux:
        if r not in briefs:
            return f"Aucun brief pour le nouveau rôle « {r} »."
    env = o.get("environnement")
    if not isinstance(env, list) or not all(isinstance(x, dict) for x in env):
        return "« environnement » est la liste des outils du poste {outil, pour, executables, installation} (vide si rien)."
    for x in env:
        if not _ligne(x.get("outil")):
            return "Chaque outil de « environnement » a un nom (« outil »)."
        if x.get("pour") not in etapes and x.get("pour") not in noms:
            return f"Outil « {x['outil']} » : « pour » est l'« etape » du flux qui s'en sert."
        ex = x.get("executables")
        if not isinstance(ex, list) or not ex or not all(isinstance(v, str) and MOTIF_EXECUTABLE.match(v) for v in ex):
            return (f"Outil « {x['outil']} » : « executables » liste les noms de programmes à chercher (par exemple "
                    "« java »), sans chemin ni option.")
        if not _texte(x.get("installation")):
            return f"Outil « {x['outil']} » : « installation » dit comment l'installer sur Windows."
        v = x.get("version_min")
        if v is not None and not (isinstance(v, str) and MOTIF_VERSION.match(v) and len(v) <= LONGUEUR_VERSION):
            return (f"Outil « {x['outil']} » : « version_min » est null ou la version minimale en chiffres et points "
                    "(« 17 », « 8.7 »).")
        erreur = _aide_d_installation(x)
        if erreur:
            return erreur
    regles = o.get("outils_installation")
    if not isinstance(regles, list) or not all(isinstance(r, str) and MOTIF_REGLE_OUTIL.match(r) for r in regles):
        return ("« outils_installation » liste des règles d'outils précises, par exemple « Bash(winget:*) » ; ni "
                "« Bash » seul ni « Bash(*) ».")
    return None


ETAPES_MIN, ETAPES_MAX, LONGUEUR_ETAPE, LONGUEUR_URL, LONGUEUR_OBJECTIF = 2, 8, 200, 300, 250


def _url_officielle(v):
    """Une adresse https sans espace ni identifiant embarqué (`https://hote/chemin`)."""
    if not (isinstance(v, str) and len(v) <= LONGUEUR_URL and v.isprintable() and " " not in v):
        return False
    p = urlsplit(v)
    return p.scheme == "https" and bool(p.hostname) and "@" not in p.netloc


def _aide_d_installation(x):
    """Message d'erreur sur les trois champs d'aide d'un outil (`telechargement`, `etapes`, `autonome`), ou `None` ;
    absents, ils sont acceptés (anciens résultats)."""
    nom = x["outil"]
    if x.get("telechargement") is not None and not _url_officielle(x["telechargement"]):
        return (f"Outil « {nom} » : « telechargement » est l'adresse https de la page de téléchargement officielle de "
                "l'éditeur, ou null si tu ne la connais pas avec certitude (n'invente jamais d'adresse).")
    if "etapes" in x:
        e = x["etapes"]
        if not (isinstance(e, list) and ETAPES_MIN <= len(e) <= ETAPES_MAX
                and all(_ligne(v) and len(v) <= LONGUEUR_ETAPE for v in e)):
            return (f"Outil « {nom} » : « etapes » est le mode opératoire sous Windows, {ETAPES_MIN} à {ETAPES_MAX} "
                    f"lignes courtes ({LONGUEUR_ETAPE} caractères au plus), dans l'ordre, jusqu'à la vérification.")
    if x.get("objectif") is not None and not (_ligne(x["objectif"]) and len(x["objectif"]) <= LONGUEUR_OBJECTIF):
        return (f"Outil « {nom} » : « objectif » est une phrase concrète sur ce que l'outil fera dans ce projet et à "
                f"quelle étape ({LONGUEUR_OBJECTIF} caractères au plus).")
    if "autonome" in x and not isinstance(x["autonome"], bool):
        return f"Outil « {nom} » : « autonome » vaut true ou false."
    return None


def _entier(v, defaut=0):
    return v if isinstance(v, int) and not isinstance(v, bool) else defaut


def _valider_questions(o, d):
    tours = _entier(d.get("tours_de_questions"))
    tours_max = min(_entier(d.get("tours_max"), TOURS_MAX_DEFINITION), TOURS_MAX_DEFINITION)
    if _texte(d.get("correction")):
        return ("L'utilisateur demande une correction de ta proposition : rends la proposition corrigée "
                "(« type » : « proposition »), sans nouvelle question.")
    if d.get("proposer_maintenant") is True:
        return "L'utilisateur veut la proposition maintenant : rends une proposition (« type » : « proposition »)."
    if tours >= tours_max:
        return (f"Les {tours_max} tours de questions sont faits : rends une proposition (« type » : « proposition ») "
                "avec ce que tu sais.")
    if not _texte(o.get("message")):
        return "« message » (ce que tu dis à l'utilisateur avant tes questions) est obligatoire."
    questions = o.get("questions")
    if not isinstance(questions, list) or not 1 <= len(questions) <= QUESTIONS_PAR_TOUR_MAX:
        return f"« questions » liste de 1 à {QUESTIONS_PAR_TOUR_MAX} questions {{id, texte, choix}}."
    ids = []
    for q in questions:
        if not isinstance(q, dict) or not (_ligne(q.get("id")) and len(q["id"]) <= LONGUEUR_ID_QUESTION) \
                or not _texte(q.get("texte")):
            return "Chaque question a un « id » court et un « texte »."
        if q["id"] in ids:
            return f"La question « {q['id']} » est en double."
        ids.append(q["id"])
        choix = q.get("choix")
        if not isinstance(choix, list) or len(choix) > CHOIX_PAR_QUESTION_MAX or not all(
                _ligne(c) and len(c) <= LONGUEUR_CHOIX for c in choix):
            return (f"Question « {q['id']} » : « choix » liste de 0 à {CHOIX_PAR_QUESTION_MAX} réponses courtes "
                    f"({LONGUEUR_CHOIX} caractères au plus), vide si la réponse est libre.")
        if "multiple" in q and not isinstance(q["multiple"], bool):
            return f"Question « {q['id']} » : « multiple » vaut true (plusieurs choix possibles) ou false."
    return None


def _valider_definir_workflow(o, d):
    type_ = o.get("type")
    if type_ == "questions":
        return _valider_questions(o, d)
    if type_ != "proposition":
        return "« type » vaut questions ou proposition."
    if not _texte(o.get("message")):
        return "« message » (le workflow expliqué à l'utilisateur) est obligatoire."
    connus = _ids_genres(d.get("genres_connus"))
    genre, nouveau = o.get("genre"), o.get("nouveau")
    if (genre is None) == (nouveau is None):
        return "Donne soit « genre » (un genre connu), soit « nouveau » (un genre à créer), pas les deux ni aucun."
    if genre is not None and genre not in connus:
        return (f"« genre » doit être l'id d'un genre connu ({', '.join(connus) or 'aucun'}) ou null, pas « {genre} » ; "
                "un genre qui n'existe pas encore va dans « nouveau ».")
    if nouveau is not None:
        if not (isinstance(nouveau, dict) and isinstance(nouveau.get("id"), str) and MOTIF_GENRE.match(nouveau["id"])
                and _ligne(nouveau.get("description"))):
            return ("« nouveau » est null ou {id (minuscules, chiffres, tirets, 40 caractères au plus), "
                    "description (une ligne)}.")
        if nouveau["id"] in connus:
            return f"Le genre « {nouveau['id']} » existe déjà : mets-le dans « genre » et « nouveau » à null."
        projet = d.get("projet") if isinstance(d.get("projet"), dict) else {}
        mots = list(d.get("mots_interdits") or []) + ([projet["nom"]] if _texte(projet.get("nom")) else [])
        interdits = mots_trouves(f"{nouveau['id']} {nouveau['description']}", mots)
        if interdits:
            return (f"« nouveau » contient un mot interdit ({', '.join(interdits)}) : un genre est public, décris-le "
                    "sans nom propre ni nom du projet.")
    flux = o.get("flux")
    if isinstance(flux, list):
        for x in flux:
            if isinstance(x, dict) and not _ligne(x.get("raison")):
                return f"Étape {x.get('etape')!r} : sa « raison » d'être, en une ligne, est obligatoire."
    services = [s for s in d.get("services") or [] if isinstance(s, dict)]
    return _valider_proposer_organisation(o, {"services": services, "agents": [],
                                              "fonctionnalite": FONCTIONNALITE_TYPE})


_VALIDEURS ={"decouper": _valider_decouper, "traduire_retour": _valider_traduire_retour,
              "ecrire_methode": _valider_ecrire_methode, "apres_refus": _valider_apres_refus,
              "conseil": _valider_conseil}
_VALIDEURS_AVEC_DOSSIER = {"classer_genre": _valider_classer_genre,
                           "proposer_organisation": _valider_proposer_organisation,
                           "definir_workflow": _valider_definir_workflow}
