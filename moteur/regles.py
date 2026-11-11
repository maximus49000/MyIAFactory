"""La table de règles du moteur : ce que fait le moteur de chaque demande, de chaque retour d'agent, de chaque étape.

Elle traduit `orchestrateur/consignes.md` (et la section 4.2 de la conception) ligne à ligne : une fonction `_sur_<type>`
par type de demande. Le moteur n'écrit dans un projet **que** par `lancer <commande>` (`orchestrateur.outil.executer`).

Les fonctions publiques **exécutent** leurs commandes tout de suite et ne rendent que ce qui reste à faire de façon
asynchrone, des `Action` :
- `("lancer", nom, entree)` : une commande à passer à `lancer` ;
- `("juger", type_, dossier, suite)` : un appel de jugement (`moteur.jugement`) ; sa décision revient par
  `appliquer_jugement(projet, type_, decision, suite)` ;
- `("agent", agent, taches, matiere)` : le départ d'un agent (`lancer depart` puis `moteur.agents`) ; son rapport revient
  par `traiter_retour`. Le modèle et le détail du départ sont dans `etat["departs"][taches[0]]`.

Chaque demande finit par `demande-traitee` : tout de suite, ou à la fin de son jugement ou de son agent (`suite` porte
alors son identifiant). Un refus de l'outil ne reste jamais silencieux : il devient la `reponse` de la demande.

`etat` est la mémoire du moteur pour un projet (un dict, créé par `nouvel_etat`) : départs en cours, éléments de la
série, contrôles refusés. Elle se reconstruit en partie depuis le suivi après un arrêt (tâche orpheline relancée une
fois, éléments repris) ; ce qui s'y perd est dit dans la passation.
"""
import re
import time
from pathlib import Path

from moteur import agents, cloud, rapport
from moteur.jugement import ACTIONS_CONSEIL, COMMANDES_INTERDITES_AU_CONSEIL  # noqa: F401
from orchestrateur import depart as dep
from orchestrateur import factory as fa
from orchestrateur import outil
from orchestrateur import suivi as su

CLOUD_RELIRE_S = 300
ROLE_CADRAGE = "cadrage"
ROLE_RELECTURE = "relecteur"
CHEF = "chef"                       # l'auteur des messages du moteur dans la discussion
ELEMENTS_EN_COURS_MAX = 2           # « deux éléments au plus en cours » en série
RELECTEURS_PREMIER_TOUR = 2
ETAPES_DE_FLUX = "flux:"
ETAPES_SOLO = ("cadrage", "prototype", "relecture")   # jamais regroupées en lot
ETAPES_DU_MOTEUR = ("cadrage", "prototype", "relecture", "correction", "retour", "demande")
ATTENDRE = "Attendre encore"
RELANCER = "Relancer l'agent"
ABANDONNER = "Abandonner la tâche"
ACCEPTE = "J'accepte"
REFUSE = "Je refuse"
FAIT = "C'est fait, relancez l'agent"
ECARTE = "Laissez cette tâche de côté"
_REPRISE = re.compile(r"\(méthode de (\S+), version (\d+)\)")
_ELEMENT = re.compile(r"\(élément (\S+)\)")


class Refus(Exception):
    """L'outil a refusé la commande (code 1) : le message est pour l'utilisateur."""


class ErreurMoteur(Exception):
    """Appel invalide (code 2) : le moteur lui-même s'est trompé, ou le projet est illisible."""


class Projet:
    """Un projet tenu par le moteur : son fichier de factory et la couche d'appel des jugements.
    `feu_vert` (rien -> bool) remplace la mesure de charge (essais)."""

    def __init__(self, factory, couche="claude", *, feu_vert=None, cloud_max=3, prerequis=None):
        self.factory = Path(factory)
        self.couche = couche
        self._feu_vert = feu_vert
        self.cloud_max = cloud_max        # sessions cloud en même temps (réglage `agents_cloud_max`)
        self._prerequis = prerequis       # remplace `cloud.prerequis` (essais) : rien -> raison | None
        self._cloud_raison = (None, 0.0)
        self.ligne_a_dire = None     # dite une seule fois au bureau, dans la réponse de la première demande traitée
        base = self.factory.resolve().parent
        self.dossier = base.parent if base.name == ".factory" else base

    @property
    def nom(self):
        return self.dossier.name

    def cloud_raison(self):
        """Pourquoi le cloud n'est pas possible (le projet n'est pas sur GitHub, `claude` manque), ou `None`. Relu au
        plus toutes les 5 minutes."""
        raison, quand = self._cloud_raison
        if quand and time.monotonic() - quand < CLOUD_RELIRE_S:
            return raison
        raison = self._prerequis() if self._prerequis else cloud.prerequis(self.dossier)
        self._cloud_raison = (raison, time.monotonic())
        return raison

    def feu_vert(self):
        if self._feu_vert is not None:
            return bool(self._feu_vert())
        try:
            return bool(lancer(self, "charge").get("feu_vert"))
        except Refus:
            return True    # une mesure impossible ne bloque pas le travail (elle est dite par l'outil)


def lancer(projet, nom, entree=None):
    """`lancer <nom>` : l'objet rendu. Lève `Refus` (code 1) ou `ErreurMoteur` (code 2)."""
    code, objet = outil.executer(str(projet.factory), ["lancer", nom], entree)
    if code == 0:
        return objet
    message = objet.get("erreur") if isinstance(objet, dict) else str(objet)
    raise (Refus if code == 1 else ErreurMoteur)(f"{nom} : {message}")


def a_lancer(nom, entree=None):
    return ("lancer", nom, entree)


def a_juger(type_, dossier, suite):
    return ("juger", type_, dossier, suite)


def a_agent(agent, taches, matiere):
    return ("agent", agent, list(taches), matiere)


def nouvel_etat():
    return {"departs": {}, "en_cours": set(), "relancees": set(), "elements": {}, "controles_echoues": {},
            "depend_de": {}, "prototype": {}, "liees": {}, "accords": {}, "a_lancer": [], "cloud": {}}


def _m(etat, cle, genre=dict):
    return etat.setdefault(cle, genre())


# --- Lectures (jamais d'écriture).

def _etat(projet):
    return lancer(projet, "etat")


def _fonc(projet, fid):
    return lancer(projet, "detail", {"fonctionnalite": fid})


def _tache(projet, tid):
    return lancer(projet, "detail", {"tache": tid})


def _factory(projet):
    try:
        return fa.lire(projet.factory)
    except fa.FactoryInvalide as e:
        raise ErreurMoteur(str(e))


def _production(projet):
    """Les étapes du flux que le moteur enchaîne pour un élément (la relecture croisée tient lieu de l'étape du
    relecteur)."""
    flux = _factory(projet)["flux"]
    return [s for s in flux if s["role"] != ROLE_RELECTURE] or flux


def _role_cadrage(projet):
    """Le rôle qui cadre : `cadrage` si un agent l'a ; sinon celui d'un agent du service Métier ; sinon celui de la
    première étape de production (un projet sans agent dédié : le spécialiste cadre lui-même)."""
    agents = _etat(projet)["agents"]
    if any(a["role"] == ROLE_CADRAGE for a in agents):
        return ROLE_CADRAGE
    metier = next((a["role"] for a in agents if a.get("service") == "metier"), None)
    return metier or _production(projet)[0]["role"]


def _colonne_du_role(projet, role):
    flux = _factory(projet)["flux"]
    return next((s["id"] for s in flux if s["role"] == role), flux[-1]["id"])


def _texte_discussion(f, derniers=20):
    return "\n".join(f"- {m['auteur']} : {m['texte']}" for m in (f.get("discussion") or [])[-derniers:]) or "(vide)"


def _consignes_propres(projet):
    chemin = _factory(projet)["consignes"]
    try:
        return Path(chemin).read_text(encoding="utf-8-sig")[:6000] if chemin else ""
    except OSError:
        return ""


# --- Aides d'écriture.

def _terminer(projet, suite, reponse):
    """Marque la demande de `suite` traitée (si elle y est) ; une demande déjà traitée n'est pas rejouée."""
    i = (suite or {}).get("demande")
    if not i:
        return
    ligne = getattr(projet, "ligne_a_dire", None)
    try:
        lancer(projet, "demande-traitee", {"id": i, "reponse": f"{reponse} {ligne}".strip() if ligne else reponse})
        if ligne:
            projet.ligne_a_dire = None
    except Refus:
        pass


def _dire(projet, fid, texte, *, attend=False, questions=None):
    """Un message du moteur dans la discussion (il parle en `chef`)."""
    e = {"fonctionnalite": fid, "auteur": CHEF, "texte": texte, "attend": attend}
    if questions:
        e["questions"] = questions
    lancer(projet, "message", e)


def _question(projet, fid, texte, choix, suite=None):
    """Une question au Directeur : un message à choix dans la discussion de la fonctionnalité (sans fonctionnalité, la
    réponse de la demande)."""
    if fid:
        _dire(projet, fid, texte, attend=True, questions=[{"texte": texte, "choix": choix}])
    _terminer(projet, suite, texte)


def _lever(projet, f, genre):
    for d in f.get("decisions") or []:
        if d["genre"] == genre:
            lancer(projet, "decision", {"action": "lever", "id": d["id"]})


def _a_decision(f, genre):
    return any(d["genre"] == genre for d in f.get("decisions") or [])


def _poser(projet, fid, genre, texte):
    lancer(projet, "decision", {"action": "poser", "portee": fid, "genre": genre, "texte": texte})


def _creer_tache(projet, titre, fid, role, etape, *, element=None, journal=None, colonne=None, **plus):
    e = {"titre": titre, "fonctionnalite": fid, "role": role, "etape": etape, "active": False,
         "colonne": colonne or _colonne_du_role(projet, role), **plus}
    if element:
        e["element"] = element
    if journal:
        e["journal"] = journal
    return lancer(projet, "tache", e)["id"]


# --- Les demandes du bureau.

def traiter_demande(projet, demande, etat):
    """Traite une demande « en attente ». Rend les actions asynchrones qui restent (jugement, départ d'agent)."""
    fonction = _SUR.get(demande.get("type"), _sur_inconnu)
    try:
        return fonction(projet, demande, etat)
    except Refus as e:
        _terminer(projet, {"demande": demande["id"]}, f"Je n'ai pas pu le faire : {e}")
        return []


def _sur_inconnu(projet, demande, etat):
    """Tout ce que la table ne couvre pas : l'appel de conseil."""
    return [_conseil(projet, etat, demande, demande.get("fonctionnalite"))]


def _conseil(projet, etat, evenement, fid, **plus):
    court = _etat(projet)
    fonc = next((f for f in court["fonctionnalites"] if f["id"] == fid), None)
    dossier = {"evenement": {k: v for k, v in evenement.items() if k not in ("images", "donnees")},
               "etat": {"projet": court["projet"], "pause": court["pause"], "fonctionnalite": fonc,
                        "decisions": [d for d in court["decisions"] if d["portee"] in (fid, "projet")],
                        "taches": [{k: t.get(k) for k in ("id", "titre", "colonne", "agent", "active", "bloquee")}
                                   for t in court["taches"] if t.get("fonctionnalite") == fid][:20]},
               "consignes_propres": _consignes_propres(projet),
               "commandes": sorted(c for c in outil.COMMANDES if c not in COMMANDES_INTERDITES_AU_CONSEIL)}
    dossier.update(plus)
    return a_juger("conseil", dossier, {"demande": evenement.get("id"), "fonctionnalite": fid})


def _sur_fonctionnalite(projet, demande, etat):
    fid = demande["fonctionnalite"]
    _terminer(projet, {"demande": demande["id"]}, "Je cherche l'agent qui va cadrer votre demande.")
    return _repondre_cadrage(projet, etat, fid)


def _sur_message(projet, demande, etat):
    fid = demande["fonctionnalite"]
    f = _fonc(projet, fid)
    accord = _m(etat, "accords").get(fid)
    if accord is not None and f["etape"] in ("cadrage", "cahier", "prototype", "serie"):
        return _reponse_a_une_question(projet, etat, demande, f, accord)
    if f["etape"] in ("cadrage", "cahier"):
        _terminer(projet, {"demande": demande["id"]}, "C'est noté, l'agent de cadrage vous répond.")
        return _repondre_cadrage(projet, etat, fid)
    if f["etape"] == "prototype":
        dossier = {"message": {"texte": demande.get("texte"), "images": demande.get("images") or []},
                   "element": _element_du_prototype(projet, etat, f),
                   "dernier_tour": next((m["texte"] for m in reversed(f["discussion"]) if m["auteur"] != "utilisateur"),
                                        ""),
                   "cahier": f.get("cahier")}
        return [a_juger("traduire_retour", dossier, {"demande": demande["id"], "fonctionnalite": fid})]
    return [_conseil(projet, etat, demande, fid)]


def _sur_cahier(projet, demande, etat):
    fid = demande["fonctionnalite"]
    f = _fonc(projet, fid)
    if demande.get("verdict") == "valider":
        cahier = {k: (f.get("cahier") or {}).get(k) for k in ("maquette", "etapes")}
        cahier["valide_le"] = su.maintenant()
        lancer(projet, "fonctionnalite", {"id": fid, "cahier": cahier, "etape": "decoupage"})
        _lever(projet, f, "valider_cahier")
        dossier = {"fonctionnalite": {"nom": f["nom"], "cahier": {"maquette": cahier.get("maquette"),
                                                                    "etapes": cahier.get("etapes")}},
                   "flux": [{"id": s["id"], "nom": s["nom"], "role": s["role"]} for s in _production(projet)],
                   "methodes_validees": _methodes_validees(projet, fid),
                   "consignes_propres": _consignes_propres(projet)}
        return [a_juger("decouper", dossier, {"demande": demande["id"], "fonctionnalite": fid})]
    # corriger : la discussion se rouvre, le cahier sera réécrit d'après le texte
    _lever(projet, f, "valider_cahier")
    lancer(projet, "fonctionnalite", {"id": fid, "etape": "cadrage"})
    lancer(projet, "message", {"fonctionnalite": fid, "auteur": "utilisateur",
                               "texte": "Correction du cahier des charges : " + (demande.get("texte") or "")})
    _terminer(projet, {"demande": demande["id"]}, "Le cahier est rouvert : l'agent de cadrage le reprend.")
    return _repondre_cadrage(projet, etat, fid)


def _methodes_validees(projet, fid):
    court = _etat(projet)
    flux = [s["id"] for s in _factory(projet)["flux"]]
    return [{"fonctionnalite": f["id"], "nom": f["nom"], "version": f["methode"].get("version"), "flux": flux}
            for f in court["fonctionnalites"] if f["id"] != fid and f.get("methode") and f["methode"].get("validee_le")]


def _sur_methode(projet, demande, etat):
    fid, verdict = demande["fonctionnalite"], demande.get("verdict")
    f = _fonc(projet, fid)
    suite = {"demande": demande["id"], "fonctionnalite": fid}
    if (verdict in ("valider", "adapter") and f["etape"] in ("cadrage", "cahier", "decoupage")
            and not any(_a_decision(f, g) for g in ("valider_methode", "reprendre_methode", "methode_a_revoir"))):
        # rien n'a été mis au point : écrire une méthode maintenant, ce serait l'inventer (vu au passage en vrai)
        _terminer(projet, {"demande": demande["id"]}, "Il n'y a pas encore de méthode à valider : elle se met au point "
                                                      "pendant le prototype, après le cahier des charges.")
        return []
    if verdict in ("valider", "adapter"):
        dossier = {"fonctionnalite": {"id": fid, "nom": f["nom"]}, "cahier": f.get("cahier"),
                   "flux": [{"id": s["id"], "role": s["role"]} for s in _production(projet)],
                   "prototype": {"discussion": f["discussion"][-30:],
                                 "element": _element_du_prototype(projet, etat, f)},
                   "controles": _controles_du_registre(projet)}
        if verdict == "adapter":
            source = _reprise_proposee(f)
            dossier["adaptation"] = demande.get("texte")
            dossier["methode_reprise"] = _fonc(projet, source[0]).get("methode") if source else None
        return [a_juger("ecrire_methode", dossier, {**suite, "adaptee": verdict == "adapter"})]
    if verdict == "reprendre":
        source = _reprise_proposee(f)
        if source is None:
            raise Refus("la méthode à reprendre n'est plus lisible dans la décision")
        m = _fonc(projet, source[0]).get("methode") or {}
        lancer(projet, "fonctionnalite", {"id": fid, "etape": "serie", "methode": {
            "version": 1, **{k: m[k] for k in ("chemin", "lien") if m.get(k)}, "validee_le": su.maintenant()}})
        _lever(projet, f, "reprendre_methode")
        _prototype_fait(projet, etat, f)
        _terminer(projet, suite, "La méthode est reprise : la série commence.")
        return []
    if verdict == "revoir":
        texte = next((d["texte"] for d in f["decisions"] if d["genre"] == "methode_a_revoir"), None)
        for genre in ("valider_methode", "methode_a_revoir", "reprendre_methode"):
            _lever(projet, f, genre)
        lancer(projet, "fonctionnalite", {"id": fid, "etape": "prototype"})
        element = _ELEMENT.search(texte or "")
        _terminer(projet, suite, "Nous reprenons la mise au point.")
        if element:
            return _retoucher_prototype(projet, etat, fid, "Revois la méthode sur cet élément : " + texte,
                                        element_id=element.group(1))
        _dire(projet, fid, "Nous reprenons la mise au point : dites-moi ce qu'il faut changer.", attend=True)
        return []
    if verdict == "garder":
        texte = next((d["texte"] for d in f["decisions"] if d["genre"] == "methode_a_revoir"), "")
        element = _ELEMENT.search(texte)
        _lever(projet, f, "methode_a_revoir")
        if element:
            _bloquer_element(projet, etat, fid, element.group(1), "méthode gardée malgré les refus (choix de l'utilisateur)")
        _terminer(projet, suite, "C'est noté : l'élément reste bloqué, la méthode ne change pas.")
        return []
    raise Refus(f"verdict de méthode inconnu : {verdict}")


def _reprise_proposee(f):
    texte = next((d["texte"] for d in f.get("decisions") or [] if d["genre"] == "reprendre_methode"), "")
    m = _REPRISE.search(texte)
    return (m.group(1), int(m.group(2))) if m else None


def _controles_du_registre(projet):
    try:
        return _factory(projet)["controles"].read_text(encoding="utf-8-sig").splitlines()[-60:]
    except OSError:
        return []


def _sur_lecon(projet, demande, etat):
    e = {"action": "appliquer", "id": demande["cible"], "verdict": demande["verdict"]}
    if demande.get("etage"):
        e["etage"] = demande["etage"]
    lancer(projet, "lecon", e)
    _terminer(projet, {"demande": demande["id"]},
              "La leçon est retenue." if demande["verdict"] == "valider" else "La leçon est écartée.")
    return []


def _sur_genre(projet, demande, etat):
    e = {"action": "fixer", "genre": demande["genre"]}
    if demande.get("description"):
        e["description"] = demande["description"]
    lancer(projet, "genre", e)
    court = _etat(projet)
    for d in court["decisions"]:
        if d["id"] == demande["decision"]:
            lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    _terminer(projet, {"demande": demande["id"]}, f"Le genre du projet est « {demande['genre']} ».")
    return []


def _sur_organisation(projet, demande, etat):
    if demande["verdict"] == "accepter":
        lancer(projet, "organisation", {"action": "appliquer", "decision": demande["decision"]})
        reponse = "La nouvelle organisation est en place."
    else:
        lancer(projet, "decision", {"action": "lever", "id": demande["decision"]})
        reponse = "C'est noté : l'organisation ne change pas."
    _terminer(projet, {"demande": demande["id"]}, reponse)
    return []


def _sur_session_cloud(projet, demande, etat):
    court = _etat(projet)
    d = next((x for x in court["decisions"] if x["id"] == demande["decision"]), None)
    if d is None or not d.get("agent"):
        raise Refus("la décision de cette session n'existe plus")
    lancer(projet, "session", {"agent": d["agent"], "session": demande["session"]})
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    _terminer(projet, {"demande": demande["id"]}, "La session est inscrite.")
    return []


def _sur_retour(projet, demande, etat):
    t = _tache(projet, demande["tache"])
    _creer_tache(projet, "Retour : " + t["titre"], t.get("fonctionnalite"), t.get("role") or _production(projet)[0]["role"],
                       "retour", element=t.get("element"), journal=["Retour de l'utilisateur : " + demande["texte"]])
    _terminer(projet, {"demande": demande["id"]}, "J'ai confié votre retour à un agent.")
    return _demarrer_en_attente(projet, etat, t.get("fonctionnalite"))


def _sur_retour_element(projet, demande, etat):
    fid = demande["fonctionnalite"]
    role = _production(projet)[0]["role"]
    tid = _creer_tache(projet, f"Retour sur l'élément {demande['element']}", fid, role, "retour",
                       element=demande["element"], journal=["Retour de l'utilisateur : " + demande["texte"]])
    v = _m(etat, "elements").get(f"{fid}/{demande['element']}")
    if v is not None and v["phase"] == "fait":   # la correction passe par la relecture croisée comme les autres
        v.update(phase="correction", tour=0, corrections=0, points=[])
        v["taches"].append(tid)
    _terminer(projet, {"demande": demande["id"]}, "Une correction de cet élément est lancée.")
    return _demarrer_en_attente(projet, etat, fid)


def _sur_deplacer(projet, demande, etat):
    cible = demande["tache"]
    if "/" in cible:   # un élément de la file : <fonctionnalité>/<élément>
        fid, eid = cible.split("/", 1)
        r = lancer(projet, "file-prendre", {"fonctionnalite": fid, "element": eid})["element"]
        lancer(projet, "tache", {"titre": r["nom"], "fonctionnalite": fid, "element": r["id"],
                                 "colonne": demande["colonne"], "active": False})
    else:
        lancer(projet, "tache", {"id": cible, "colonne": demande["colonne"]})
    _terminer(projet, {"demande": demande["id"]}, "C'est déplacé.")
    return []


def _sur_bouton(projet, demande, etat):
    return [_conseil(projet, etat, demande, None)]


def _sur_partenaires(projet, demande, etat):
    genre = demande["type"]
    if genre == "partenaire_regle":
        e = {"action": "regle", "partenaire": demande["partenaire"], "operation": demande["operation"]}
        for cle in ("id", "texte"):
            if demande.get(cle):
                e[cle] = demande[cle]
        lancer(projet, "partenaires", e)
        reponse = "La règle est notée."
    elif genre == "partenaires_actualiser":
        r = lancer(projet, "partenaires", {"action": "quota", "force": True})
        reponse = f"Quotas relus ({len(r.get('lus') or [])} partenaire(s))."
    else:
        r = lancer(projet, "partenaires", {"action": "a_refaire"})
        reponse = (f"{len(r.get('ids') or [])} fiche(s) sont à revérifier, mais le moteur ne sait pas encore lancer "
                   "cette recherche : rien n'a été modifié.")
    _terminer(projet, {"demande": demande["id"]}, reponse)
    return []


def _sur_challenge(projet, demande, etat):
    cible = demande.get("cible")
    if not (isinstance(cible, dict) and cible.get("type") == "lecon" and demande.get("tache")):
        return [_conseil(projet, etat, demande, None)]
    detail = lancer(projet, "detail", {"lecons": True})
    lecon = next((x for x in detail["lecons"] if x["id"] == cible.get("id")), None)
    agent = (lecon or {}).get("agent")
    if lecon is None or agent is None:
        raise Refus("la leçon contestée n'est plus à valider")
    tid = demande["tache"]
    lancer(projet, "tache", {"id": tid, "agent": agent, "journal": [
        "Leçon contestée : " + lecon["texte"], "Texte de l'utilisateur : " + (demande.get("texte") or "")]})
    _m(etat, "liees")[tid] = demande["id"]
    _m(etat, "a_lancer", list).append(tid)
    return _demarrer_en_attente(projet, etat, None)


_SUR = {"fonctionnalite": _sur_fonctionnalite, "message": _sur_message, "cahier": _sur_cahier, "methode": _sur_methode,
        "lecon": _sur_lecon, "genre": _sur_genre, "organisation": _sur_organisation,
        "session_cloud": _sur_session_cloud, "retour": _sur_retour, "retour_element": _sur_retour_element,
        "deplacer": _sur_deplacer, "bouton": _sur_bouton, "partenaire_regle": _sur_partenaires,
        "partenaires_actualiser": _sur_partenaires, "partenaires_maj": _sur_partenaires, "challenge": _sur_challenge}


# --- Le cadrage et le prototype.

def _repondre_cadrage(projet, etat, fid, consigne=None):
    """Prépare la réponse de l'agent de cadrage (sa tâche, persistante) et la lance si l'agent est libre."""
    f = _fonc(projet, fid)
    court = _etat(projet)
    agent = f.get("agent_cadrage")
    if agent is None:
        agent = lancer(projet, "agent-libre", {"role": _role_cadrage(projet), "lieu": "local"})["agent"]
        if agent is None:
            return []     # `avancer` réessaie tant que la fonctionnalité attend une réponse
        lancer(projet, "fonctionnalite", {"id": fid, "agent_cadrage": agent})
    tache = next((t for t in court["taches"] if t.get("fonctionnalite") == fid and t.get("etape") == "cadrage"
                  and t["colonne"] != "fait"), None)
    premiere = not any(m["auteur"] == agent for m in f["discussion"])
    fiche = next((a for a in court["agents"] if a["cle"] == agent), {})
    montee = ({"de": "Haiku", "a": dep.monter("Haiku"), "raison": "première analyse du besoin"}
              if premiere and fiche.get("modele") == "Haiku" else None)
    if tache is None:
        tid = lancer(projet, "tache", {"titre": f"Cadrage : {f['nom']}", "fonctionnalite": fid,
                                       "role": fiche.get("role") or ROLE_CADRAGE,
                                       "colonne": "cadrage", "agent": agent, "etape": "cadrage", "active": False,
                                       "montee": montee})["id"]
    else:
        tid = tache["id"]
        if tid in _m(etat, "en_cours") or tache["active"]:
            return []     # il répond déjà
        if tid in _m(etat, "a_lancer", list):
            return _demarrer_en_attente(projet, etat, fid)    # déjà prêt à partir : on attend un agent libre
        lancer(projet, "tache", {"id": tid, "agent": agent, "montee": montee, "titre": f"Cadrage : {f['nom']}"})
    if consigne:
        lancer(projet, "tache", {"id": tid, "journal": [consigne]})
    if tid not in _m(etat, "a_lancer", list):
        etat["a_lancer"].append(tid)
    return _demarrer_en_attente(projet, etat, fid)


def _element_du_prototype(projet, etat, f):
    e = _m(etat, "prototype").get(f["id"])
    if e is None:
        court = _etat(projet)
        t = next((t for t in reversed(court["taches"]) if t.get("fonctionnalite") == f["id"]
                  and str(t.get("etape")) == "prototype" and t.get("element")), None)
        e = {"id": t["element"], "nom": t["element"]} if t else None
    return e


def _retoucher_prototype(projet, etat, fid, consigne, element_id=None):
    f = _fonc(projet, fid)
    element = _element_du_prototype(projet, etat, f)
    if element_id:
        element = next((x for x in f["file"] if x["id"] == element_id), {"id": element_id, "nom": element_id})
    if element is None:
        raise Refus("je ne sais pas quel élément sert de prototype")
    _m(etat, "prototype")[fid] = element
    role = _production(projet)[0]["role"]
    _creer_tache(projet, f"Prototype : {element['nom']}", fid, role, "prototype", element=element["id"],
                 journal=[consigne])
    return _demarrer_en_attente(projet, etat, fid)


def _prototype_fait(projet, etat, f):
    """L'élément du prototype est fait (sa méthode est validée) : la série ne le reprend pas."""
    e = _element_du_prototype(projet, etat, f)
    if e:
        _m(etat, "elements")[f"{f['id']}/{e['id']}"] = {"fid": f["id"], "element": e, "phase": "fait", "pas": 0,
                                                        "tour": 0, "corrections": 0, "taches": []}


def _reponse_a_une_question(projet, etat, demande, f, accord):
    """L'utilisateur répond à une question du moteur (accord, outil refusé) : relancer l'agent ou laisser la tâche."""
    texte = demande.get("texte") or ""
    del etat["accords"][f["id"]]
    tid = accord["tache"]
    if accord.get("muette"):
        return _reponse_session_muette(projet, etat, demande, f, tid, texte)
    if ACCEPTE in texte or FAIT in texte:
        lancer(projet, "tache", {"id": tid, "bloquee": None, "journal": ["Accord de l'utilisateur : "
                                                                         + accord["quoi"]]})
        _m(etat, "a_lancer", list).append(tid)
        _m(etat, "supplements")[tid] = accord["supplement"]
        _terminer(projet, {"demande": demande["id"]}, "Merci, l'agent reprend sa tâche.")
        return _demarrer_en_attente(projet, etat, f["id"])
    lancer(projet, "tache", {"id": tid, "bloquee": "mise de côté sur décision de l'utilisateur", "active": False})
    _terminer(projet, {"demande": demande["id"]}, "C'est noté : cette tâche est mise de côté.")
    return []


def question_session_muette(projet, etat, tid, adresse):
    """Une session cloud sans rapport depuis trop longtemps : la décision revient au Directeur."""
    t = _tache(projet, tid)
    fid = t.get("fonctionnalite")
    texte = (f"La session cloud de la tâche « {t['titre']} » n'a rendu aucun rapport depuis deux heures"
             + (f" ({adresse})." if adresse else "."))
    lancer(projet, "tache", {"id": tid, "journal": [texte]})
    if fid:
        _m(etat, "accords")[fid] = {"tache": tid, "quoi": texte, "supplement": None, "muette": True}
        _question(projet, fid, texte + " Que faire ?", [ATTENDRE, RELANCER, ABANDONNER])


def _reponse_session_muette(projet, etat, demande, f, tid, texte):
    info = _m(etat, "cloud").get(tid)
    if ATTENDRE in texte:
        if info is not None:
            info["depuis"] = None          # la boucle repart de l'heure du moment
            info["muette_dite"] = False
        _terminer(projet, {"demande": demande["id"]}, "D'accord, j'attends encore.")
        return []
    if RELANCER in texte:
        etat["cloud"].pop(tid, None)
        etat["en_cours"].discard(tid)
        lancer(projet, "tache", {"id": tid, "active": False, "journal": ["Relancée sur décision de l'utilisateur."]})
        _m(etat, "a_lancer", list).append(tid)
        _terminer(projet, {"demande": demande["id"]}, "Je relance l'agent dans une nouvelle session.")
        return _demarrer_en_attente(projet, etat, f["id"])
    etat.get("cloud", {}).pop(tid, None)
    etat["en_cours"].discard(tid)
    lancer(projet, "tache", {"id": tid, "bloquee": "abandonnée sur décision de l'utilisateur", "active": False})
    _terminer(projet, {"demande": demande["id"]}, "C'est noté : la tâche est abandonnée.")
    return []


# --- Départs : choisir l'agent, regrouper en lots, partir.

def _attente(court, fid, etat):
    """Les tâches du moteur qui n'ont pas encore démarré : pas actives, pas faites, jamais prises (hors cadrage, relancé
    par `a_lancer`)."""
    a_lancer = _m(etat, "a_lancer", list)
    attente = []
    for t in court["taches"]:
        if fid and t.get("fonctionnalite") != fid:
            continue
        if t["active"] or t["colonne"] == "fait" or t.get("bloquee") or isinstance(t.get("lot"), dict):
            continue
        if t["id"] in _m(etat, "en_cours"):
            continue
        etape = str(t.get("etape") or "")
        explicite = t["id"] in a_lancer
        if explicite or (not t.get("debut") and (etape.startswith(ETAPES_DE_FLUX) or etape in ETAPES_DU_MOTEUR)):
            attente.append(t)
    attente.sort(key=lambda t: (t.get("etape") != "correction", t["id"]))
    return attente


def _demarrer_en_attente(projet, etat, fid):
    """Lance ce qui peut l'être : aucune étape en pause, feu vert de la charge, un agent libre. Rend les actions agent."""
    court = _etat(projet)
    if court["pause"]:
        return []
    attente = _attente(court, fid, etat)
    if not attente or not projet.feu_vert():
        return []
    actions, solos, en_flux = [], [], []
    for t in attente:
        (en_flux if str(t.get("etape")).startswith(ETAPES_DE_FLUX) and t["id"] not in etat["a_lancer"]
         else solos).append(t)
    lots = []
    if en_flux:
        r = lancer(projet, "lots", {"taches": [t["id"] for t in en_flux]})
        lots = [{"ids": x["taches"], "modele": x["modele"], "lot": x["lot"]} for x in r["lots"]]
    par_id = {t["id"]: t for t in attente}
    for t in solos:
        lots.append({"ids": [t["id"]], "modele": None, "lot": None})
    for lot in lots:
        premiere = par_id[lot["ids"][0]]
        agent = premiere.get("agent") if premiere.get("etape") == "cadrage" or premiere["id"] in etat["a_lancer"] \
            else None
        if agent is not None:
            libre = next((a for a in court["agents"] if a["cle"] == agent), {})
            if not libre.get("libre", False):
                continue
        else:
            agent = _choisir_agent(projet, etat, court, premiere, lot["modele"])
            if agent is None:
                continue
        actions.append(_partir(projet, etat, court, agent, lot["ids"], lot["lot"], par_id))
        court = _etat(projet)    # l'agent est pris : le prochain lot voit l'état à jour
    return actions


def _choisir_agent(projet, etat, court, tache, modele):
    """L'agent qui prend la tâche : un agent local libre du modèle voulu ; sinon, en renfort, un agent cloud libre (dans
    la limite de `agents_cloud_max`, si le projet est sur GitHub) ; sinon, si le cloud est impossible, l'agent local
    équivalent (un autre modèle du même rôle), en le disant au bureau."""
    role = tache.get("role")
    local = lancer(projet, "agent-libre", {"role": role, "lieu": "local", **({"modele": modele} if modele else {})})
    if local["agent"]:
        return local["agent"]
    clouds = {a["cle"] for a in court["agents"] if a["lieu"] == "cloud"}
    candidats = [a for a in court["agents"] if a["lieu"] == "cloud" and a["role"] == role and a["libre"]
                 and (not modele or a["modele"] == modele)]
    if not clouds or not candidats:
        return None
    raison = projet.cloud_raison()
    if raison is None:
        actifs = sum(1 for t in court["taches"] if t["active"] and t.get("agent") in clouds)
        return candidats[0]["cle"] if actifs < projet.cloud_max else None
    equivalent = lancer(projet, "agent-libre", {"role": role, "lieu": "local"})["agent"]
    dits = _m(etat, "cloud_dit", set)
    if equivalent and (tache.get("fonctionnalite"), role) not in dits and tache.get("fonctionnalite"):
        dits.add((tache["fonctionnalite"], role))
        _dire(projet, tache["fonctionnalite"], f"Les agents cloud ne sont pas disponibles ({raison}) : "
                                               f"l'agent local {equivalent} prend la tâche « {tache['titre']} ».")
    return equivalent


def _partir(projet, etat, court, agent, ids, lot, par_id):
    fiche = next(a for a in court["agents"] if a["cle"] == agent)
    premiere = par_id[ids[0]]
    montee = premiere.get("montee")
    modele = (montee or {}).get("a") or fiche["modele"]
    if len(ids) > 1:
        for rang, i in enumerate(ids, 1):
            lancer(projet, "tache", {"id": i, "lot": {"id": lot, "rang": rang}})
    lancer(projet, "tache", {"id": ids[0], "agent": agent, "active": True})
    matiere = "\n\n".join(_matiere(projet, etat, par_id[i]) for i in ids)
    supp = _m(etat, "supplements").pop(ids[0], None)
    if supp:
        matiere += "\n\n" + supp
    if ids[0] in etat["a_lancer"]:
        etat["a_lancer"].remove(ids[0])
    etat["departs"][ids[0]] = {"agent": agent, "taches": list(ids), "matiere": matiere, "modele": modele, "lot": lot,
                               "suite": supp}
    etat["en_cours"].add(ids[0])
    return a_agent(agent, ids, matiere)


def _matiere(projet, etat, t):
    """Ce que l'agent doit savoir de la tâche, en plus de son message de départ (la discussion, les retours, l'élément)."""
    etape, fid = str(t.get("etape") or ""), t.get("fonctionnalite")
    f = _fonc(projet, fid) if fid else None
    complet = _tache(projet, t["id"])
    consignes = "\n".join(f"- {j['texte']}" for j in complet.get("journal") or [])
    parties = [f"## Matière de la tâche {t['id']} ({t['titre']})"]
    if etape == "cadrage":
        parties += ["Discussion avec l'utilisateur :", _texte_discussion(f),
                    "Réponds-lui par ton rapport : des questions courtes, avec des choix quand c'est possible "
                    "(`message.questions`, `attend: true`). Dès ta première réponse, donne un `nom` court à la "
                    "fonctionnalité. **Une seule série de questions** : dès que l'utilisateur y a répondu, écris le "
                    "cahier des charges sans reposer de questions (ce qui reste ouvert, choisis-le toi-même et dis-le "
                    "dans ton message). Le cahier : une maquette (images PNG ou JPEG que tu fabriques, sous une racine "
                    "d'images du projet) et la liste des étapes à réaliser, dans l'ordre : "
                    'rends `"cahier": {"maquette": [chemins], "etapes": [textes]}`. Une correction demandée par '
                    "l'utilisateur : refais la maquette et rends le cahier corrigé."]
    elif etape == "prototype":
        parties += [f"Élément du prototype : {t.get('element')}", "Cahier : " + str((f or {}).get("cahier")),
                    "Discussion récente :", _texte_discussion(f, 8),
                    "Montre tes images dans `message.images`, avec `attend: true` pour recueillir le retour de "
                    'l\'utilisateur. Quand la méthode te semble prête, résume-la dans ton message et rends '
                    '`"methode_prete": true`.']
    elif etape.startswith(ETAPES_DE_FLUX):
        methode = (f or {}).get("methode") or {}
        parties += [f"Élément : {t.get('element')}", f"Étape du flux : {etape[len(ETAPES_DE_FLUX):]}",
                    "Méthode validée : " + str(methode.get("chemin") or methode.get("lien") or "(voir ton brief)"),
                    "Registre des contrôles : relis-le avant de rendre l'élément."]
        derniere = _production(projet)[-1]
        if etape == ETAPES_DE_FLUX + derniere["id"] and len(_production(projet)) > 1 and _sans_relecteur(projet):
            parties.append("Tu es le dernier regard sur l'élément. Rends un `verdicts` : "
                           '`[{"element": <id>, "conforme": vrai|faux, "points": [chaque défaut trouvé, un texte]}]`, '
                           "un par élément. Un défaut devient un contrôle : sois précis.")
    elif etape == "relecture":
        parties += [f"Élément à relire : {t.get('element')}",
                    "Relis l'élément avec un regard neuf. Rends un `verdicts` : "
                    '`[{"element": <id>, "conforme": vrai|faux, "points": [chaque défaut trouvé, un texte]}]`. '
                    "Un défaut devient un contrôle : sois précis."]
    elif etape in ("correction", "retour", "demande", "challenge"):
        parties.append(f"Élément : {t.get('element') or '(aucun)'}")
    if consignes:
        parties += ["Consignes :", consignes]
    return "\n".join(parties)


# --- Le retour d'un agent.

def traiter_retour(projet, execution, etat):
    """Applique le rapport d'un agent terminé (ou sa panne). Rend les actions qui restent."""
    depart = _m(etat, "departs").get(execution.tache) or {"agent": execution.agent, "taches": [execution.tache],
                                                          "matiere": "", "lot": execution.lot}
    taches = depart["taches"]
    etat["en_cours"].discard(taches[0])
    r = execution.rapport
    if r is None:
        return _agent_en_echec(projet, etat, execution, depart)
    fid = None
    for tid in taches:
        t = _tache(projet, tid)
        fid = fid or t.get("fonctionnalite")
    liee = _m(etat, "liees").pop(taches[0], None)
    reponse = ((r.get("message") or {}).get("texte")) or "C'est fait."
    if r["statut"] in ("accord_requis", "outil_refuse"):
        return _agent_arrete(projet, etat, execution, depart, r, fid)
    if r["statut"] == "echec":
        _bloquer_taches(projet, taches, "L'agent n'a pas pu finir : " + reponse[:300])
        _terminer(projet, {"demande": liee}, "L'agent n'a pas pu finir : " + reponse[:300])
        return []
    t0 = _tache(projet, taches[0])
    for commande, entree in rapport.commandes(r, fonctionnalite=fid, tache=taches[0], agent=execution.agent,
                                              etape=str(t0.get("etape") or "")):
        try:
            lancer(projet, commande, entree)
        except Refus as e:
            lancer(projet, "tache", {"id": taches[0], "journal": [f"Refusé par l'outil ({commande}) : {e}"]})
    for retour in r.get("retours_factory") or []:
        lancer(projet, "controle", {"texte": retour, "origine": f"retour de {execution.agent}"})
    for tid in taches:
        t = _tache(projet, tid)
        if str(t.get("etape")) == "cadrage" and not r.get("cahier"):
            lancer(projet, "tache", {"id": tid, "active": False, "journal": [reponse[:300]]})   # il répondra encore
        elif t["colonne"] != "fait":
            e = {"id": tid, "colonne": "fait", "active": False, "journal": ["Terminé."]}
            if "lignes" in r and tid == taches[-1]:
                e["lignes"] = r["lignes"]
            if tid == taches[0] and r.get("message"):
                e["journal"] = [r["message"]["texte"][:500]] if r["message"].get("texte") else e["journal"]
            lancer(projet, "tache", e)
        elif t["active"]:
            lancer(projet, "tache", {"id": tid, "active": False})
    _terminer(projet, {"demande": liee}, reponse[:500])
    actions = []
    for tid in taches:
        actions += _suite_de_tache(projet, etat, _tache(projet, tid), execution, r)
    return actions + _demarrer_en_attente(projet, etat, fid)


def _agent_en_echec(projet, etat, execution, depart):
    """Un agent sans rapport : relancé une fois, puis tâche bloquée avec la raison au journal."""
    tid = depart["taches"][0]
    relancees = _m(etat, "relancees", set)
    if tid not in relancees:
        relancees.add(tid)
        lancer(projet, "tache", {"id": tid, "journal": [f"L'agent n'a pas rendu de rapport ({execution.erreur}) : "
                                                        "nouvel essai."]})
        etat["en_cours"].add(tid)
        return [a_agent(depart["agent"], depart["taches"], depart["matiere"])]
    raison = f"L'agent n'a pas rendu de rapport après deux essais : {execution.erreur}"
    _bloquer_taches(projet, depart["taches"], raison)
    t = _tache(projet, tid)
    if t.get("fonctionnalite"):
        _dire(projet, t["fonctionnalite"], f"La tâche « {t['titre']} » est bloquée : {raison}")
    _terminer(projet, {"demande": _m(etat, "liees").pop(tid, None)}, raison)
    return []


def _bloquer_taches(projet, taches, raison):
    for tid in taches:
        t = _tache(projet, tid)
        if t["colonne"] != "fait":
            lancer(projet, "tache", {"id": tid, "bloquee": raison[:300], "active": False, "journal": [raison[:500]]})


def _agent_arrete(projet, etat, execution, depart, r, fid):
    """L'agent s'arrête : il lui faut l'accord de l'utilisateur, ou un outil que sa fiche ne lui ouvre pas. Une question
    au Directeur ; l'agent reprend la même tâche sur la réponse."""
    tid = depart["taches"][0]
    t = _tache(projet, tid)
    if r["statut"] == "accord_requis":
        a = r["accord"]
        quoi = f"{a['quoi']} (chez {a['partenaire']}, {a['cout']})"
        texte = f"L'agent {execution.agent} demande votre accord : {quoi}."
        choix = [ACCEPTE, REFUSE]
        supplement = f"L'utilisateur a donné son accord pour : {quoi}. Tu peux le faire."
    else:
        quoi = f"l'outil {r['outil']}"
        texte = (f"L'agent {execution.agent} a besoin de {quoi}, que sa fiche ne lui ouvre pas. Pour le lui donner, "
                 "ajoutez-le à la ligne « Outils : » de sa fiche.")
        choix = [FAIT, ECARTE]
        supplement = f"{quoi.capitalize()} est maintenant ouvert dans ta fiche."
    lancer(projet, "tache", {"id": tid, "active": False, "journal": [texte]})
    for autre in depart["taches"][1:]:    # le reste du lot n'a pas été fait : il repart seul plus tard
        if _tache(projet, autre)["colonne"] != "fait":
            lancer(projet, "tache", {"id": autre, "lot": None})
    fid = fid or t.get("fonctionnalite")
    if fid:
        for commande, entree in rapport.commandes(r, fonctionnalite=fid, tache=tid, agent=execution.agent, etape=""):
            lancer(projet, commande, entree)
        _m(etat, "accords")[fid] = {"tache": tid, "quoi": quoi, "supplement": supplement}
        _question(projet, fid, texte, choix)
    return []


def _suite_de_tache(projet, etat, t, execution, r):
    """Ce que la fin d'une tâche déclenche, selon son étape."""
    etape, fid = str(t.get("etape") or ""), t.get("fonctionnalite")
    if etape == "cadrage":
        return _suite_cadrage(projet, etat, t, r)
    if etape == "prototype":
        return _suite_prototype(projet, etat, t, r)
    cle = f"{fid}/{t.get('element')}"
    v = _m(etat, "elements").get(cle)
    if v is None:
        return []
    if etape.startswith(ETAPES_DE_FLUX):
        return _apres_flux(projet, etat, v, r)
    if etape == "relecture":
        return _apres_relecture(projet, etat, v, execution.agent, r)
    if etape in ("correction", "retour") and v["phase"] == "correction":
        v["corrections"] += 1
        return _lancer_relecture(projet, etat, v)
    return []


def _suite_cadrage(projet, etat, t, r):
    fid = t["fonctionnalite"]
    if r.get("nom"):
        lancer(projet, "fonctionnalite", {"id": fid, "nom": r["nom"][:80]})
        lancer(projet, "tache", {"id": t["id"], "titre": f"Cadrage : {r['nom'][:80]}"})
    if r.get("cahier"):
        lancer(projet, "fonctionnalite", {"id": fid, "cahier": {"maquette": r["cahier"]["maquette"],
                                                                "etapes": r["cahier"]["etapes"]}, "etape": "cahier"})
        _poser(projet, fid, "valider_cahier", "Le cahier des charges est prêt : le valider, ou le faire corriger ?")
    return []


def _suite_prototype(projet, etat, t, r):
    if r.get("methode_prete"):
        f = _fonc(projet, t["fonctionnalite"])
        if not _a_decision(f, "valider_methode"):
            _poser(projet, f["id"], "valider_methode", "La méthode vous semble-t-elle prête ? La valider pour passer à "
                                                       "la série, ou continuer la mise au point.")
    return []


# --- La série : éléments, flux, relecture croisée.

def _etat_element(etat, fid, element):
    return _m(etat, "elements").setdefault(f"{fid}/{element['id']}", {
        "fid": fid, "element": element, "phase": "flux", "pas": 0, "tour": 0, "corrections": 0, "taches": [],
        "attendus": 0, "rapports": []})


def _tache_de_flux(projet, etat, v):
    pas = _production(projet)
    s = pas[v["pas"]]
    tid = _creer_tache(projet, f"{s['nom']} : {v['element']['nom']}", v["fid"], s["role"], ETAPES_DE_FLUX + s["id"],
                       element=v["element"]["id"], colonne=s["id"])
    v["taches"].append(tid)
    return tid


def _sans_relecteur(projet):
    """Aucun agent relecteur : la dernière étape du flux (un contrôle, le plus souvent) tient lieu de relecture."""
    return not any(a["role"] == ROLE_RELECTURE for a in _etat(projet)["agents"])


def _apres_flux(projet, etat, v, r=None):
    v["pas"] += 1
    if v["pas"] < len(_production(projet)):
        _tache_de_flux(projet, etat, v)
        return []
    if _sans_relecteur(projet):
        # les verdicts de la dernière étape sur cet élément (un lot en porte pour chacun) ; aucun = conforme
        v["phase"], v["attendus"] = "relecture", 1
        v["rapports"] = [[x for x in (r or {}).get("verdicts") or [] if x["element"] == v["element"]["id"]]]
        return _conclure_relecture(projet, etat, v)
    v["phase"] = "relecture"
    return _lancer_relecture(projet, etat, v)


def _lancer_relecture(projet, etat, v):
    """Le premier tour : deux relecteurs à contexte neuf, qui ne se voient pas ; les tours suivants : un seul, qui ne
    vérifie que les points corrigés. Sans relecteur, la dernière étape du flux est refaite."""
    if _sans_relecteur(projet):
        v["phase"], v["pas"] = "flux", len(_production(projet)) - 1
        _tache_de_flux(projet, etat, v)
        return []
    v["phase"], v["rapports"] = "relecture", []
    v["attendus"] = RELECTEURS_PREMIER_TOUR if v["tour"] == 0 and v["corrections"] == 0 else 1
    colonne = _colonne_du_role(projet, ROLE_RELECTURE)
    for k in range(1, v["attendus"] + 1):
        journal = ([f"Tour {v['corrections'] + 1} : ne vérifie que ces points, et que la correction n'a rien cassé :"
                    + "".join(f"\n- {p}" for p in v.get("points") or [])] if v["corrections"] else None)
        v["taches"].append(_creer_tache(
            projet, f"Relecture{f' {k}' if v['attendus'] > 1 else ''} : {v['element']['nom']}", v["fid"],
            ROLE_RELECTURE, "relecture", element=v["element"]["id"], journal=journal, colonne=colonne))
    return []


def _apres_relecture(projet, etat, v, agent, r):
    v["rapports"].append(r.get("verdicts") or [])
    if len(v["rapports"]) < v["attendus"]:
        return []
    return _conclure_relecture(projet, etat, v)


def _conclure_relecture(projet, etat, v):
    points = []
    for verdicts in v["rapports"]:
        mine = [x for x in verdicts if x["element"] == v["element"]["id"]] or verdicts
        for x in mine:
            if not x["conforme"]:
                points += [p for p in (x.get("points") or ["(refus sans détail)"]) if p not in points]
    v["tour"] += 1
    if not points:
        return _element_fait(projet, etat, v)
    v["points"] = points
    for p in points:
        lancer(projet, "controle", {"texte": p, "origine": f"relecture de {v['element']['nom']}"})
    seuil = _factory(projet)["seuil_methode"]
    echoues = _m(etat, "controles_echoues")
    autre = None
    for p in points:
        cle = " ".join(p.lower().split())
        elements = echoues.setdefault(cle, set())
        elements.add(v["element"]["id"])
        if len(elements) > 1:
            autre = p
    if v["corrections"] >= seuil:
        return _methode_a_revoir(projet, etat, v, f"cet élément a déjà eu {v['corrections']} tours de corrections")
    if autre is not None:
        return _methode_a_revoir(projet, etat, v, f"le même contrôle échoue sur deux éléments : « {autre} »")
    dossier = {"element": v["element"], "refus": {"points": points, "verdicts": [x for vs in v["rapports"] for x in vs]},
               "tours": v["corrections"] + 1, "seuil_methode": seuil,
               "methode": (_fonc(projet, v["fid"]).get("methode") or {}).get("version")}
    return [a_juger("apres_refus", dossier, {"fonctionnalite": v["fid"], "element": v["element"]["id"]})]


def _element_fait(projet, etat, v):
    v["phase"] = "fait"
    f = _fonc(projet, v["fid"])
    if not f.get("catalogue"):
        lancer(projet, "fonctionnalite", {"id": v["fid"], "catalogue": True})
    return []


def _methode_a_revoir(projet, etat, v, raison):
    v["phase"] = "attente_methode"
    f = _fonc(projet, v["fid"])
    if not _a_decision(f, "methode_a_revoir"):
        _poser(projet, v["fid"], "methode_a_revoir",
               f"La méthode est peut-être à revoir : {raison}. La revoir, ou la garder et laisser l'élément "
               f"« {v['element']['nom']} » de côté ? (élément {v['element']['id']})")
    _dire(projet, v["fid"], f"L'élément « {v['element']['nom']} » n'avance plus : {raison}. Voulez-vous revoir la "
                            "méthode ? (Répondez avec les boutons de la décision.)", attend=True)
    return []


def _bloquer_element(projet, etat, fid, eid, raison):
    v = _m(etat, "elements").get(f"{fid}/{eid}")
    if v:
        v["phase"] = "bloque"
    court = _etat(projet)
    for t in court["taches"]:
        if t.get("fonctionnalite") == fid and t.get("element") == eid and t["colonne"] != "fait":
            lancer(projet, "tache", {"id": t["id"], "bloquee": raison, "active": False})


def fiche_cloud(court, cle):
    return any(a["cle"] == cle and a["lieu"] == "cloud" for a in court["agents"])


def orphelines(projet, etat):
    """À la reprise du moteur : une tâche active dont l'agent a disparu est relancée une fois (avec le reste de son lot).
    Une tâche relancée une fois n'est plus reprise."""
    court = _etat(projet)
    if court["pause"]:
        return []
    actions, relancees = [], _m(etat, "relancees", set)
    for t in court["taches"]:
        etape = str(t.get("etape") or "")
        if (not t["active"] or not t.get("agent") or t["id"] in etat["en_cours"] or t["id"] in relancees
                or not (etape.startswith(ETAPES_DE_FLUX) or etape in ETAPES_DU_MOTEUR)):
            continue
        if fiche_cloud(court, t["agent"]):
            continue      # sa session cloud vit encore : la boucle la retrouve et la relève
        relancees.add(t["id"])
        ids = [t["id"]]
        if isinstance(t.get("lot"), dict):
            reste = [x for x in court["taches"] if isinstance(x.get("lot"), dict) and x["lot"]["id"] == t["lot"]["id"]
                     and x["lot"]["rang"] > t["lot"]["rang"] and x["colonne"] != "fait"]
            ids += [x["id"] for x in sorted(reste, key=lambda x: x["lot"]["rang"])]
        par_id = {x["id"]: x for x in court["taches"]}
        fiche = next(a for a in court["agents"] if a["cle"] == t["agent"])
        modele = (t.get("montee") or {}).get("a") or fiche["modele"]
        matiere = (chr(10) * 2).join(_matiere(projet, etat, par_id[i]) for i in ids)
        lancer(projet, "tache", {"id": t["id"], "journal": ["Le moteur a repris : l'agent avait disparu, nouvel essai."]})
        etat["departs"][ids[0]] = {"agent": t["agent"], "taches": ids, "matiere": matiere, "modele": modele,
                                   "lot": (t.get("lot") or {}).get("id")}
        etat["en_cours"].add(ids[0])
        actions.append(a_agent(t["agent"], ids, matiere))
    return actions


def avancer(projet, etat):
    """Ce que le parcours demande à chaque étape : rien en pause (les demandes, elles, sont traitées)."""
    court = _etat(projet)
    if court["pause"]:
        return []
    actions = []
    for f in court["fonctionnalites"]:
        if f["etape"] in ("cadrage", "cahier") and f["attend_reponse"]:
            actions += _repondre_cadrage(projet, etat, f["id"])
        elif f["etape"] == "serie":
            actions += _avancer_serie(projet, etat, f["id"])
    return actions + _demarrer_en_attente(projet, etat, None)


def _avancer_serie(projet, etat, fid):
    """Les éléments de la série : au plus deux en cours, dans l'ordre de la file et selon leurs dépendances ; la
    fonctionnalité est terminée quand la file est vide et que tous les éléments sont faits ou laissés de côté."""
    f = _fonc(projet, fid)
    revoir = _a_decision(f, "methode_a_revoir")
    elements = _m(etat, "elements")
    mine = [v for v in elements.values() if v["fid"] == fid]
    if not revoir:
        for v in mine:
            if v["phase"] == "attente_methode":   # la méthode a été revue : l'élément repart de son premier pas
                v.update(phase="flux", pas=0, corrections=0, tour=0, taches=[], points=[])
                _tache_de_flux(projet, etat, v)
        vivants = sum(1 for v in mine if v["phase"] in ("flux", "relecture", "correction"))
        fait = {v["element"]["id"] for v in mine if v["phase"] == "fait"}
        deps = _m(etat, "depend_de").get(fid, {})
        while vivants < ELEMENTS_EN_COURS_MAX:
            file = _fonc(projet, fid)["file"]
            ids = {q["id"] for q in file}
            choisi = next((q for q in file if all(d in fait or d not in ids for d in deps.get(q["id"], []))), None)
            if choisi is None:
                break
            element = lancer(projet, "file-prendre", {"fonctionnalite": fid, "element": choisi["id"]})["element"]
            _tache_de_flux(projet, etat, _etat_element(etat, fid, element))
            vivants += 1
        mine = [v for v in elements.values() if v["fid"] == fid]
        if not _fonc(projet, fid)["file"] and mine and all(v["phase"] in ("fait", "bloque") for v in mine):
            bloques = [v["element"]["nom"] for v in mine if v["phase"] == "bloque"]
            lancer(projet, "fonctionnalite", {"id": fid, "etape": "terminee"})
            _dire(projet, fid, "La série est terminée." + (f" Éléments laissés de côté : {', '.join(bloques)}."
                                                           if bloques else ""))
    return []


# --- Les jugements : leur décision revient ici.

def appliquer_jugement(projet, type_, decision, contexte, etat=None):
    """La suite d'un jugement (`contexte` : la suite donnée avec l'action `juger`). Une décision sans objet (deux essais
    ratés) devient une question au Directeur."""
    etat = nouvel_etat() if etat is None else etat
    if decision.question is not None:
        _question(projet, contexte.get("fonctionnalite"), decision.question, ["Je précise", "Plus tard"], contexte)
        return []
    o = decision.objet
    return _APRES[type_](projet, o, contexte, etat)


def _apres_decouper(projet, o, ctx, etat):
    fid = ctx["fonctionnalite"]
    lancer(projet, "file", {"fonctionnalite": fid, "elements": o["elements"]})
    _m(etat, "depend_de")[fid] = o["depend_de"]
    _dire(projet, fid, o["message"])
    reprise = o.get("reprendre_methode")
    if reprise:
        r = reprise
        lancer(projet, "file-prendre", {"fonctionnalite": fid, "element": o["prototype"]})
        element = next(x for x in o["elements"] if x["id"] == o["prototype"])
        _m(etat, "prototype")[fid] = element
        _poser(projet, fid, "reprendre_methode",
               f"Une méthode déjà validée ressemble à celle-ci : {r['pourquoi']} (méthode de {r['fonctionnalite']}, "
               f"version {r['version']}). La reprendre, l'adapter, ou refaire un prototype ?")
        _terminer(projet, ctx, "Le cahier est découpé ; une méthode existante est proposée.")
        return []
    element = lancer(projet, "file-prendre", {"fonctionnalite": fid, "element": o["prototype"]})["element"]
    _m(etat, "prototype")[fid] = element
    lancer(projet, "fonctionnalite", {"id": fid, "etape": "prototype"})
    _terminer(projet, ctx, f"Le cahier est découpé en {len(o['elements'])} éléments ; on commence par le prototype "
                           f"de « {element['nom']} ».")
    return _retoucher_prototype(projet, etat, fid, f"Premier tour du prototype de l'élément « {element['nom']} » : "
                                                   "fais-le de bout en bout et montre ton travail.")


def _apres_traduire_retour(projet, o, ctx, etat):
    fid = ctx["fonctionnalite"]
    if o["validation"]:
        f = _fonc(projet, fid)
        if not _a_decision(f, "valider_methode"):
            _poser(projet, fid, "valider_methode", "Le prototype vous convient : valider la méthode pour passer à la "
                                                   "série ?")
        _dire(projet, fid, "Le prototype est validé : il reste à valider la méthode pour passer à la série.")
        _terminer(projet, ctx, "C'est noté : validez la méthode pour passer à la série.")
        return []
    _terminer(projet, ctx, "J'ai transmis votre retour à l'agent du prototype.")
    return _retoucher_prototype(projet, etat, fid, o["consigne"])


def _apres_ecrire_methode(projet, o, ctx, etat):
    fid = ctx["fonctionnalite"]
    f = _fonc(projet, fid)
    version = ((f.get("methode") or {}).get("version") or 0) + 1
    chemin = lancer(projet, "ecrire", {"fonctionnalite": fid, "nom": f"methode-v{version}.md",
                                       "texte": o["document"], "titre": f"Méthode (version {version})",
                                       "etape": "methode", "agent": CHEF})["chemin"]
    for role, brief in o["briefs"].items():
        lancer(projet, "ecrire", {"brief": role, "texte": f"## Méthode de « {f['nom']} » (version {version})\n{brief}"})
    for c in o["controles"]:
        lancer(projet, "controle", c)
    lancer(projet, "fonctionnalite", {"id": fid, "etape": "serie", "methode": {
        "version": version, "chemin": chemin, "validee_le": su.maintenant()}})
    _lever(projet, f, "valider_methode")
    _lever(projet, f, "reprendre_methode")
    _prototype_fait(projet, etat, f)
    _terminer(projet, ctx, f"La méthode (version {version}) est écrite : la série commence.")
    return []


def _apres_apres_refus(projet, o, ctx, etat):
    fid, eid = ctx["fonctionnalite"], ctx["element"]
    v = _m(etat, "elements").get(f"{fid}/{eid}")
    if o["suite"] == "corriger":
        role = _production(projet)[0]["role"]
        tid = _creer_tache(projet, f"Correction : {v['element']['nom'] if v else eid}", fid, role, "correction",
                           element=eid, journal=[o["consigne"]])
        if v:
            v["phase"] = "correction"
            v["taches"].append(tid)
        return _demarrer_en_attente(projet, etat, fid)
    if o["suite"] == "methode_a_revoir":
        if v:
            return _methode_a_revoir(projet, etat, v, o["raison"])
        return []
    _bloquer_element(projet, etat, fid, eid, o["raison"])
    _dire(projet, fid, f"L'élément « {eid} » est bloqué : {o['raison']}")
    return []


def _apres_conseil(projet, o, ctx, etat):
    fid, p, reponse = ctx.get("fonctionnalite"), o["parametres"], o.get("reponse") or ""
    action = o["action"]
    if action == "transmettre_agent":
        agents_ = _etat(projet)["agents"]
        voulu = p.get("agent")
        fiche = next((a for a in agents_ if a["cle"] == voulu), None) or next((a for a in agents_ if a["role"] == voulu), None)
        role = fiche["role"] if fiche else _production(projet)[0]["role"]
        tid = _creer_tache(projet, "Demande : " + p["consigne"][:60], fid, role, "demande", journal=[p["consigne"]])
        if fiche and fiche["cle"] == voulu:    # un agent précis : il garde sa tâche
            lancer(projet, "tache", {"id": tid, "agent": voulu})
            _m(etat, "a_lancer", list).append(tid)
        _m(etat, "liees")[tid] = ctx.get("demande")
        return _demarrer_en_attente(projet, etat, fid)
    if action == "poser_decision":
        _question(projet, fid, p["texte"], ["Oui", "Non"], ctx)
        return []
    if action == "lancer":
        lancer(projet, p["commande"], p.get("entree") or {})
    _terminer(projet, ctx, reponse or ("C'est fait." if action == "lancer" else "Rien à faire."))
    return []


_APRES = {"decouper": _apres_decouper, "traduire_retour": _apres_traduire_retour,
          "ecrire_methode": _apres_ecrire_methode, "apres_refus": _apres_apres_refus, "conseil": _apres_conseil}
