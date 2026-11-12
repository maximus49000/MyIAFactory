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
import base64
import json
import re
import time
from pathlib import Path

from installation import estimation
from moteur import agents, cloud, environnement, rapport
from moteur.jugement import ACTIONS_CONSEIL, COMMANDES_INTERDITES_AU_CONSEIL  # noqa: F401
from orchestrateur.memoire import normaliser_mot
from orchestrateur import depart as dep
from orchestrateur import factory as fa
from orchestrateur import fiches as fi
from orchestrateur import outil
from orchestrateur import suivi as su
from orchestrateur import workflows as wf

CLOUD_RELIRE_S = 300
ROLE_CADRAGE = "cadrage"
ROLE_RELECTURE = "relecteur"
MOTS_DE_QUALITE = ("qualit", "test", "controle", "verif", "recette")   # le début des mots d'une équipe de qualité
CHEF = "chef"                       # l'auteur des messages du moteur dans la discussion
ELEMENTS_EN_COURS_MAX = 2           # « deux éléments au plus en cours » en série
RELECTEURS_PREMIER_TOUR = 2
ETAPES_DE_FLUX = "flux:"
ETAPES_DE_VALIDATION = "validation:"   # l'étape d'une tâche « Validation du Directeur » (jamais lancée par le moteur)
GENRE_VALIDATION = "valider_etape"     # la décision de projet posée quand un élément attend le Directeur
VALIDER = "valider"
RENVOYER = "renvoyer"
COMPTE_RENDU_MAX = 2000
FICHIERS_MAX = 20
ETAPES_SOLO = ("cadrage", "prototype", "relecture")   # jamais regroupées en lot
ETAPES_DU_MOTEUR = ("cadrage", "prototype", "relecture", "correction", "retour", "demande", "environnement")
ROLE_ENVIRONNEMENT = "environnement"      # l'agent qui installe les outils du poste
REGLES_D_INSTALLATION = ("Bash(winget:*)",)   # ce que reçoit l'installateur recruté au clic (winget, en portée utilisateur)
CONTINUER_SANS = "continuer"
C_EST_FAIT = "fait"
FORCER = "forcer"      # « Forcer : c'est installé » : le Directeur affirme que l'outil est là, sans qu'on l'ait trouvé
ATTENDRE = "Attendre encore"
RELANCER = "Relancer l'agent"
ABANDONNER = "Abandonner la tâche"
CONTINUER = "Continuer avec le workflow actuel"
JE_PRECISE = "Je précise"
DECISIONS_DU_PARCOURS = ("genre_fonctionnalite", "environnement")   # celles de la fonctionnalité qui retiennent son cadrage
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

    def __init__(self, factory, couche="claude", *, feu_vert=None, cloud_max=3, prerequis=None,
                 verifier_environnement=None, bureau=None):
        self.factory = Path(factory)
        self.couche = couche
        self._feu_vert = feu_vert
        self.cloud_max = cloud_max        # sessions cloud en même temps (réglage `agents_cloud_max`)
        self._prerequis = prerequis       # remplace `cloud.prerequis` (essais) : rien -> raison | None
        self._cloud_raison = (None, 0.0)
        # ce que le poste a déjà (outils.py de l'environnement) ; les essais le remplacent
        self.verifier_environnement = verifier_environnement or environnement.verifier
        self.bureau = bureau              # le fichier du bureau : les mesures d'usage par genre servent à l'estimation
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


def _flux(projet, fid=None):
    """Les étapes du workflow de la fonctionnalité `fid` (le principal sans fonctionnalité, ou si elle n'a pas le sien) ;
    vide si le projet n'a aucun workflow."""
    fonc = None
    if fid:
        try:
            fonc = _fonc(projet, fid)
        except Refus:
            fonc = None
    w = wf.de_la_fonctionnalite(_factory(projet), fonc)
    return w["flux"] if w else []


def _production(projet, fid=None):
    """Les étapes du workflow de la fonctionnalité que le moteur enchaîne pour un élément (la relecture croisée tient
    lieu de l'étape du relecteur)."""
    flux = _flux(projet, fid)
    return [s for s in flux if s.get("role") != ROLE_RELECTURE] or flux


def _role_cadrage(projet, fid=None):
    """Le rôle qui cadre : `cadrage` si un agent l'a ; sinon celui d'un agent du service Métier ; sinon celui de la
    première étape de production du workflow de la fonctionnalité (un projet sans agent dédié : le spécialiste cadre
    lui-même)."""
    agents = _etat(projet)["agents"]
    if any(a["role"] == ROLE_CADRAGE for a in agents):
        return ROLE_CADRAGE
    metier = next((a["role"] for a in agents if a.get("service") == "metier"), None)
    return metier or _role_production(projet, fid, agents)


def _role_production(projet, fid=None, agents=None):
    """Le rôle de la première étape de production du workflow ; sans workflow, celui de cadrage."""
    production = wf.etapes_d_agent(_production(projet, fid))
    if production:
        return production[0]["role"]
    return next((a["role"] for a in agents if a["role"] != ROLE_RELECTURE), ROLE_CADRAGE) if agents else ROLE_CADRAGE


def _colonne_du_role(projet, role, fid=None):
    flux = _flux(projet, fid)
    if not flux:
        return "cadrage"
    return next((s["id"] for s in flux if s.get("role") == role), flux[-1]["id"])


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
         "colonne": colonne or _colonne_du_role(projet, role, fid), **plus}
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


def _sur_message(projet, demande, etat):
    fid = demande["fonctionnalite"]
    f = _fonc(projet, fid)
    accord = _m(etat, "accords").get(fid)
    if accord is not None and f["etape"] in ("cadrage", "cahier", "prototype", "serie"):
        return _reponse_a_une_question(projet, etat, demande, f, accord)
    if f["etape"] == "cadrage" and fid in _m(etat, "proposition_ratee"):
        return _reponse_proposition_ratee(projet, etat, demande, fid)
    if f["etape"] == "cadrage" and _en_parcours(projet, etat, fid):
        _terminer(projet, {"demande": demande["id"]}, "C'est noté. Répondez d'abord à la question posée dans les "
                                                      "décisions : le cadrage commencera ensuite.")
        return []
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
                   "flux": [{"id": s["id"], "nom": s["nom"], "role": s["role"]}
                            for s in wf.etapes_d_agent(_production(projet, fid))],
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
    return [{"fonctionnalite": f["id"], "nom": f["nom"], "version": f["methode"].get("version"),
             "flux": [s["id"] for s in wf.etapes_d_agent(_flux(projet, f["id"]))]}
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
                   "flux": [{"id": s["id"], "role": s["role"]}
                           for s in wf.etapes_d_agent(_production(projet, fid))],
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


# --- Le parcours d'une nouvelle fonctionnalité : classer le genre, proposer son workflow, recruter (conception, section 5).

def _genres_du_projet(fac):
    """Les genres déjà employés dans le projet : le sien et ceux de ses workflows."""
    ids = []
    for g in [fac["genre"]] + [w.get("genre") for w in wf.tous(fac)]:
        if g and g not in ids:
            ids.append(g)
    return ids


def _genre_du_projet(fac):
    genres = _genres_du_projet(fac)
    return genres[0] if genres else None


def _demande_de(f):
    """Le texte et les images de la demande d'origine : le premier message de l'utilisateur."""
    m = next((m for m in f.get("discussion") or [] if m["auteur"] == "utilisateur"), None)
    return {"texte": (m or {}).get("texte") or f.get("nom") or "", "images": list((m or {}).get("images") or [])}


def _en_parcours(projet, etat, fid):
    """Vrai si la fonctionnalité attend encore une réponse du Directeur sur son genre ou son workflow, ou la mise en
    place de l'environnement : le cadrage ne démarre pas avant."""
    court = _etat(projet)
    f = next((x for x in court["fonctionnalites"] if x["id"] == fid), None)
    if f is None:
        return False
    if any(d["genre"] in DECISIONS_DU_PARCOURS for d in f["decisions"]):
        return True
    if any(d["portee"] == "projet" and d["genre"] in ("organisation", "confirmer_genre") and d.get("fonctionnalite") == fid
           for d in court["decisions"]):
        return True
    if fid in _m(etat, "proposition_ratee"):
        return True
    return any(t.get("fonctionnalite") == fid and t.get("etape") == "environnement" and t["colonne"] != "fait"
               and not t.get("bloquee") for t in court["taches"])


def _genre_deja_propose(projet):
    """La décision `confirmer_genre` du projet déjà posée, s'il y en a une."""
    return next((d for d in _etat(projet)["decisions"] if d["portee"] == "projet" and d["genre"] == "confirmer_genre"),
                None)


def genre_a_proposer(projet, etat):
    """Au premier passage du moteur sur un projet sans genre qui a une description (créé au bureau) : le classement de
    sa description, pour proposer son genre sans attendre une première demande. Rien si le genre est déjà proposé, ou
    si le projet a déjà une fonctionnalité (sa demande suit son parcours : créée depuis une demande déplacée, elle porte
    le genre choisi par le Directeur)."""
    fac = _factory(projet)
    if _genres_du_projet(fac) or not fac["description"] or _genre_deja_propose(projet) \
            or _etat(projet)["fonctionnalites"]:
        return []
    return [a_juger("classer_genre", _dossier_classer(projet, fac, {"texte": fac["description"], "images": []}),
                    {"sans_genre": True})]


def _classer(projet, etat, fid, suite):
    """L'appel qui classe la demande (Haiku). Un projet sans genre classe sa description ; la fonctionnalité attend la
    réponse (`confirmer_genre`). Si ce genre est déjà proposé, la décision porte désormais la fonctionnalité (pas de
    second classement)."""
    fac = _factory(projet)
    f = _fonc(projet, fid)
    demande = _demande_de(f)
    sans_genre = not _genres_du_projet(fac)
    if sans_genre:
        d = _genre_deja_propose(projet)
        if d is not None and not d.get("fonctionnalite"):
            lancer(projet, "decision", {"action": "lever", "id": d["id"]})
            lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": "confirmer_genre",
                                        "texte": d["texte"], "propose": d["propose"],
                                        "genres_connus": d.get("genres_connus") or [], "fonctionnalite": fid,
                                        **({"description": d["description"]} if d.get("description") else {})})
            _dire(projet, fid, d["texte"])
            _terminer(projet, suite, "Le projet n'a pas encore de genre : confirmez celui que je vous propose.")
            return []
        suite = {**suite, "sans_genre": True}
        demande = {"texte": fac["description"] or demande["texte"], "images": []}
    return [a_juger("classer_genre", _dossier_classer(projet, fac, demande), suite)]


def _dossier_classer(projet, fac, demande):
    connus = lancer(projet, "genre", {"action": "lister"})["genres"]
    par_id = {g["id"]: g for g in connus}
    du_projet = [par_id.get(i) or {"id": i, "domaine": None, "livrable": None, "outils": None}
                 for i in _genres_du_projet(fac)]
    return {"demande": demande, "projet": {"nom": fac["nom"], "description": fac["description"]},
            "genres_du_projet": du_projet, "genres_connus": connus, "mots_interdits": fac["mots_interdits"]}


MOTS_DE_LIAISON = ("de", "du", "des", "la", "le", "les", "un", "une", "d", "l", "et", "ou", "à", "a", "au", "aux", "pour",
                   "avec", "sur", "en", "dans", "qui", "que")
LONGUEUR_NOM = 60
BORD_DE_PHRASE = r"(?<=[.!?])\s|\n"            # la fin d'une phrase, ou d'une ligne
BORDS_DE_MOT = r"^\W+|\W+$"                    # la ponctuation d'un mot (« d' » donne « d »)
PONCTUATION_DE_NOM = " ,;:.!?-–—…'\"("


def _resume_de_la_demande(texte):
    """Un nom court et propre tiré du texte d'une demande : sa première phrase, coupée aux mots, sans ponctuation ni mot
    de liaison à la fin."""
    phrase = re.split(BORD_DE_PHRASE, str(texte or "").strip(), maxsplit=1)[0]
    phrase = " ".join(phrase.split())
    if len(phrase) > LONGUEUR_NOM:
        coupee = phrase[:LONGUEUR_NOM + 1]
        phrase = coupee[:coupee.rfind(" ")] if " " in coupee else phrase[:LONGUEUR_NOM]
    mots = phrase.split(" ")
    while len(mots) > 1 and re.sub(BORDS_DE_MOT, "", mots[-1]).lower() in MOTS_DE_LIAISON:
        mots.pop()
    nom = " ".join(mots).strip(PONCTUATION_DE_NOM)
    return nom[:1].upper() + nom[1:] if nom else "Nouvelle fonctionnalité"


def _nommer(projet, fid, intitule=None):
    """Le nom provisoire d'une nouvelle fonctionnalité est le début brut de la demande : il est remplacé par l'intitulé
    du classement, sinon par un résumé de la demande. Un nom déjà changé (par le cadrage, le Directeur) est gardé."""
    f = _fonc(projet, fid)
    texte = " ".join(_demande_de(f)["texte"].split())
    nom = " ".join((f.get("nom") or "").split())
    provisoire = not nom or texte.startswith(nom) or nom == _resume_de_la_demande(texte)
    propre = (intitule or "").strip().rstrip(" .") or _resume_de_la_demande(texte)
    if provisoire and propre and propre != f.get("nom"):
        lancer(projet, "fonctionnalite", {"id": fid, "nom": propre})


def _sur_fonctionnalite(projet, demande, etat):
    fid = demande["fonctionnalite"]
    suite = {"demande": demande["id"], "fonctionnalite": fid}
    _nommer(projet, fid)
    if demande.get("genre"):      # recréée depuis un autre projet : son genre est déjà connu
        lancer(projet, "fonctionnalite", {"id": fid, "genre": demande["genre"]})
        connus = [g["id"] for g in lancer(projet, "genre", {"action": "lister"})["genres"]]
        if demande["genre"] not in connus and demande.get("description"):
            suite["genre_nouveau"] = {"description": demande["description"]}
        creation = wf.de_creation(_factory(projet), demande["genre"])
        if creation is not None:      # ce projet a déjà le workflow de ce genre, validé à sa création
            return _suivre_le_workflow_de_creation(projet, etat, fid, suite, creation)
        return _proposer(projet, etat, fid, suite)
    return _classer(projet, etat, fid, suite)


def _apres_classer_genre(projet, o, ctx, etat):
    fid = ctx.get("fonctionnalite")    # absente : le genre d'un projet créé au bureau, proposé au premier passage
    fac = _factory(projet)
    nouveau, piste = o.get("nouveau"), o.get("genre") or (o.get("nouveau") or {}).get("id")
    verdict, raison = o["verdict"], o["raison"]
    connus = [g["id"] for g in lancer(projet, "genre", {"action": "lister"})["genres"]]
    if fid and not ctx.get("sans_genre") and o.get("intitule"):
        _nommer(projet, fid, o["intitule"])
    if ctx.get("sans_genre"):
        if not piste:        # aucune piste : on continue sans genre, la proposition de workflow en dira plus
            if not fid:
                return []
            _terminer(projet, ctx, "Je n'ai pas pu deviner le genre du projet ; je propose un workflow quand même.")
            return _proposer(projet, etat, fid, {"fonctionnalite": fid})
        texte = (f"Le projet n'a pas encore de genre. D'après sa description, je propose « {piste} » "
                 f"({((nouveau or {}).get('description') or 'un genre déjà connu').strip().rstrip('.')}). {raison} "
                 "Le confirmer, ou en "
                 "choisir un autre ?")
        entree = {"action": "poser", "portee": "projet", "genre": "confirmer_genre", "texte": texte, "propose": piste,
                  "genres_connus": connus}
        if nouveau and piste == nouveau["id"]:      # la phrase du genre nouveau est déjà rédigée : il n'y a qu'à valider
            entree["description"] = nouveau["description"]
        if fid:
            entree["fonctionnalite"] = fid
        lancer(projet, "decision", entree)
        if fid:
            _dire(projet, fid, texte)
        _terminer(projet, ctx, "Le projet n'a pas encore de genre : je vous en propose un.")
        return []
    coherente = o.get("coherente")
    du_projet = _genre_du_projet(fac) or "aucun"
    propose = piste or _genre_du_projet(fac) or "a-preciser"
    if coherente is False:     # illogique pour ce projet : on prévient avant de continuer, quel que soit le genre
        texte = (f"Cette demande ne semble pas cohérente avec le projet « {fac['nom']} » ({raison.strip().rstrip('.')}). "
                 "La faire dans un nouveau projet, ou dans ce projet quand même ?")
        return _poser_genre_fonctionnalite(projet, ctx, fid, texte, propose, nouveau, connus,
                                           incertain=verdict in ("meme", "proche", "incertain"),
                                           elargissement=o.get("elargissement"))
    if verdict in ("meme", "proche"):
        lancer(projet, "fonctionnalite", {"id": fid, "genre": o["genre"]})
        creation = wf.de_creation(fac, o["genre"]) if verdict == "meme" else None
        if creation is not None:      # le genre du projet : le workflow validé à la création, sans nouvelle proposition
            return _suivre_le_workflow_de_creation(projet, etat, fid, ctx, creation)
        if verdict == "proche":
            _dire(projet, fid, f"Cette demande est proche du genre « {o['genre']} » : elle y est rattachée. {raison}")
        return _proposer(projet, etat, fid, ctx)
    if verdict == "autre" and coherente is True:     # cohérente : on part sur le fonctionnel, dans ce projet
        _dire(projet, fid, f"Cette demande est d'un autre genre (« {propose} »), mais elle a sa place dans ce projet : "
                           f"je propose un workflow dédié. {raison}")
        return _garder_ici(projet, etat, fid, dict(ctx), propose, connus, nouveau)
    if verdict == "autre":
        texte = (f"Cette demande n'est pas du genre du projet ({du_projet}) : elle relève plutôt de « {propose} ». "
                 f"{raison} La faire dans un nouveau projet, ou dans ce projet ?")
    else:
        texte = (f"Je ne suis pas sûr du genre de cette demande (le projet est de genre {du_projet}). {raison} "
                 "Est-ce le même genre, ou faut-il un autre projet ?")
    return _poser_genre_fonctionnalite(projet, ctx, fid, texte, propose, nouveau, connus, incertain=verdict == "incertain",
                                       elargissement=o.get("elargissement"))


def _suivre_le_workflow_de_creation(projet, etat, fid, ctx, creation):
    """La demande est du genre du projet : elle reprend le workflow défini à la création (une copie `w-<fid>`), sans
    proposition ni validation de workflow, et le cadrage démarre."""
    lancer(projet, "organisation", {"action": "reprendre", "fonctionnalite": fid, "workflow": creation["id"]})
    _dire(projet, fid, "Cette demande suit le workflow du projet.")
    _terminer(projet, ctx, "Cette demande suit le workflow du projet : le cadrage commence.")
    return _repondre_cadrage(projet, etat, fid)


def _poser_genre_fonctionnalite(projet, ctx, fid, texte, propose, nouveau, connus, incertain, elargissement=None):
    """La question « nouveau projet, ou ce projet ? » : rien ne démarre avant la réponse."""
    entree = {"action": "poser", "portee": fid, "genre": "genre_fonctionnalite", "texte": texte, "propose": propose,
              "incertain": incertain, "genres_connus": connus}
    if nouveau:
        entree["nouveau"] = {"id": nouveau["id"], "description": nouveau["description"]}
    if elargissement:      # la description du genre du projet, élargie à cette demande, si on la garde dans ce genre
        entree["elargissement"] = elargissement
    lancer(projet, "decision", entree)
    _dire(projet, fid, texte)
    _terminer(projet, ctx, "Cette demande ne semble pas être du genre du projet : dites où la faire.")
    return []


def _garder_ici(projet, etat, fid, suite, genre, connus, nouveau, description=None, decision=None,
                force_elargir=False):
    """La fonctionnalité reste dans ce projet avec le genre `genre` (connu, ou nouveau avec sa description), puis son
    workflow est proposé. Refus si un genre nouveau n'a pas de description (rien n'est alors changé)."""
    fac = _factory(projet)
    nouveau = nouveau or {}
    if genre not in connus and genre not in _genres_du_projet(fac):
        description = description or (nouveau.get("description") if nouveau.get("id") == genre else None)
        if not description:
            raise Refus(f"« {genre} » est un nouveau genre : il a besoin d'une description")
        suite = {**suite, "genre_nouveau": {"description": description}}
    if decision is not None:
        lancer(projet, "decision", {"action": "lever", "id": decision["id"]})
    lancer(projet, "fonctionnalite", {"id": fid, "genre": genre})
    if decision is not None and (force_elargir or _gardee_hors_piste(decision, genre)):
        _proposer_elargissement(projet, fid, genre,
                                decision.get("elargissement") if genre == _genre_du_projet(fac) else None)
    return _proposer(projet, etat, fid, suite)


def _gardee_hors_piste(decision, genre):
    """Vrai si la demande, jugée d'un autre genre (ou illogique pour le projet), est gardée dans un genre existant qui
    n'était pas la piste du moteur : la description de ce genre doit alors couvrir ce nouveau travail."""
    return genre in (decision.get("genres_connus") or []) and genre != decision.get("propose")


def _proposer_elargissement(projet, fid, genre, phrase):
    """Au Directeur, sans bloquer la fonctionnalité : élargir la description du genre gardé (ancienne et nouvelle
    description, la nouvelle pré-remplie). La phrase vient du classement ; sinon, une phrase déterministe."""
    ancienne = next((g.get("domaine") for g in lancer(projet, "genre", {"action": "lister"})["genres"]
                     if g["id"] == genre), None)
    ancienne = " ".join(str(ancienne or "").split())
    if not ancienne or ancienne.lower().startswith("à préciser"):
        return
    nom = " ".join(str(_fonc(projet, fid).get("nom") or "").split()).rstrip(" .")
    nouvelle = " ".join((phrase or "").split()) or (
        f"{ancienne.rstrip(' .')}, et aussi {nom[:1].lower() + nom[1:]}" if nom else "")
    if not nouvelle or nouvelle == ancienne:
        return
    lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": "elargir_genre", "cible": genre,
                                "ancienne": ancienne, "propose": nouvelle, "fonctionnalite": fid,
                                "texte": f"Le genre « {genre} » garde cette fonctionnalité, qui sort un peu de sa "
                                         f"description. Élargir la description en « {nouvelle} » ?"})
    _dire(projet, fid, f"Le genre « {genre} » est gardé ; je propose d'en élargir la description : « {nouvelle} » "
                       "(à valider au bureau de direction, sans attendre).")


def _decision_de(f, i, genre):
    return next((d for d in f.get("decisions") or [] if d["id"] == i and d["genre"] == genre), None)


def _sur_genre_fonctionnalite(projet, demande, etat):
    """La réponse à « cette demande n'est pas du genre du projet » : ici, même genre, ou nouveau projet."""
    fid, choix = demande["fonctionnalite"], demande["choix"]
    f = _fonc(projet, fid)
    d = _decision_de(f, demande["decision"], "genre_fonctionnalite")
    if d is None:
        raise Refus("cette question n'existe plus")
    suite = {"demande": demande["id"], "fonctionnalite": fid}
    fac = _factory(projet)
    if choix == "nouveau_projet":
        return _vers_un_nouveau_projet(projet, demande, f, d)
    if choix == "meme":
        genre = _genre_du_projet(fac)
        if genre is None:
            raise Refus("le projet n'a pas de genre : choisissez « Dans ce projet »")
    elif choix == "ici":
        genre = demande.get("genre") or d["propose"]
    else:
        raise Refus(f"choix inconnu : {choix}")
    return _garder_ici(projet, etat, fid, suite, genre, d.get("genres_connus") or [], d.get("nouveau"),
                       demande.get("description"), d, force_elargir=choix == "meme")


def _factory_du_projet_cree(chemin_reglages):
    """Le fichier de factory du projet créé au bureau, d'après ses réglages (`orchestrateur`, sinon `factory.json`)."""
    reglages = Path(chemin_reglages)
    if not reglages.is_file():
        raise Refus(f"le nouveau projet est introuvable ({chemin_reglages})")
    nom = "factory.json"
    try:
        lus = json.loads(reglages.read_text(encoding="utf-8-sig"))
        if isinstance(lus, dict) and isinstance(lus.get("orchestrateur"), str) and lus["orchestrateur"].strip():
            nom = lus["orchestrateur"]
    except (OSError, ValueError):
        pass
    factory = (reglages.parent / nom).resolve()
    if not factory.is_file():
        raise Refus(f"le nouveau projet n'a pas de fichier de factory ({factory})")
    try:
        fa.lire(factory)
    except fa.FactoryInvalide as e:
        raise Refus(f"le nouveau projet est illisible : {e}")
    return factory


def _images_a_recreer(projet, f):
    """Les images de la demande d'origine, relues sur le disque pour être recréées dans l'autre projet."""
    sortie = []
    for chemin in _demande_de(f)["images"]:
        p = projet.factory.resolve().parent / chemin
        type_ = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(p.suffix.lower())
        try:
            if type_ and p.is_file():
                sortie.append({"nom": p.name, "type": type_, "donnees": base64.b64encode(p.read_bytes()).decode()})
        except OSError:
            continue
    return sortie


def _vers_un_nouveau_projet(projet, demande, f, d):
    """La demande d'origine est recréée dans le nouveau projet (par sa commande `actions`), puis la fonctionnalité passe
    à `deplacee` ici. Un projet injoignable : rien ne bouge, la décision reste (« Dans ce projet » reste possible)."""
    fid = f["id"]
    try:
        if not isinstance(demande.get("projet_cree"), str) or not demande["projet_cree"].strip():
            raise Refus("le nouveau projet n'est pas indiqué")
        factory = _factory_du_projet_cree(demande["projet_cree"])
        nom = fa.lire(factory)["nom"]
        origine = _demande_de(f)
        entree = {"type": "fonctionnalite", "texte": origine["texte"], "t": su.maintenant()}
        genre = demande.get("genre") or d.get("propose")
        if genre:
            entree["genre"] = genre
            nouveau = d.get("nouveau") or {}
            description = demande.get("description") or (nouveau.get("description") if nouveau.get("id") == genre else None)
            if description:
                entree["description"] = description
        images = _images_a_recreer(projet, f)
        if images:
            entree["images"] = images
        code, objet = outil.executer(str(factory), ["lancer", "actions"], entree)
        if code != 0:
            raise Refus(str(objet.get("erreur") if isinstance(objet, dict) else objet))
    except Refus as e:
        _terminer(projet, {"demande": demande["id"]}, f"Je n'ai pas pu créer la demande dans le nouveau projet ({e}). "
                                                      "Vous pouvez la garder dans ce projet : « Dans ce projet ».")
        return []
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    lancer(projet, "fonctionnalite", {"id": fid, "etape": "deplacee", "deplacee_vers": nom})
    _dire(projet, fid, f"Partie dans le projet {nom}")
    _terminer(projet, {"demande": demande["id"]}, f"Votre demande est partie dans le projet « {nom} ».")
    return []


def _proposer(projet, etat, fid, suite, refus=None):
    """L'appel qui propose le workflow de la fonctionnalité (Sonnet) : toujours un workflow par fonctionnalité."""
    fac = _factory(projet)
    f = _fonc(projet, fid)
    genre = f.get("genre") or _genre_du_projet(fac)
    try:
        fiches_ = fi.lire_toutes(fac["fiches"])
    except (fi.FicheInvalide, OSError):
        fiches_ = []
    anterieurs = []
    for w in reversed(wf.tous(fac)):        # le plus récent d'abord ; les ids sont donnés sans le préfixe de leur fonctionnalité
        if genre and w.get("genre") == genre:
            prefixe = f"{w['fonctionnalite']}-" if w.get("fonctionnalite") else ""
            anterieurs.append({"id": w["id"], "flux": [
                {"etape": e["id"][len(prefixe):] if prefixe and e["id"].startswith(prefixe) else e["id"],
                 "nom": e["nom"], **{c: v for c, v in wf.etape_ecrite(e).items() if c not in ("id", "nom")}}
                for e in w["flux"]]})
    dossier = {"demande": _demande_de(f), "genre": genre, "projet": {"nom": fac["nom"], "description": fac["description"]},
               "services": [{"id": s["id"], "nom": s["nom"]} for s in fac["services"]],
               "agents": [{"cle": a["cle"], "role": a["role"], "modele": a["modele"], "specialite": a.get("specialite")}
                          for a in fiches_],
               "workflows_du_genre": anterieurs, "fonctionnalite": fid, "refus": refus}
    return [a_juger("proposer_organisation", dossier, {k: v for k, v in suite.items() if k != "sans_genre"})]


def _cout(projet, flux, agents, genre):
    """Le coût estimé du workflow, calculé en code (jamais par l'IA) : une fourchette de tokens."""
    usages = []
    if getattr(projet, "bureau", None):
        try:
            usages = estimation.usages_du_genre(projet.bureau, genre)
        except Exception:      # une estimation d'après les mesures est une aide : jamais une raison d'échouer
            usages = []
    agents = [dict(a, modele="Opus" if a["modele"] == "Fable" else a["modele"]) for a in agents]   # Fable : tarif d'Opus
    bureau = getattr(projet, "bureau", None)
    e = estimation.estimer(flux, agents, usages, lambda modele: estimation.prix_de_modele(bureau, modele))
    return {"tokens": e["tokens"], "euros": e["euros"]}


def _apres_proposer_organisation(projet, o, ctx, etat):
    fid = ctx["fonctionnalite"]
    fac = _factory(projet)
    f = _fonc(projet, fid)
    genre = f.get("genre") or _genre_du_projet(fac)
    flux = [{"id": f"{fid}-{x['etape']}", "nom": x["nom"], **({"validation": True} if wf.est_validation(x)
                                                              else {"role": x["role"], "service": x["service"]})}
            for x in o["flux"]]
    nouveaux = [dict(a, lieu="local") for a in o["agents"]]
    services = [{"id": s["id"], "nom": s["nom"]} for s in fac["services"]] + [dict(s) for s in o["services"]]
    existants = [{"role": a["role"], "modele": a["modele"]} for a in _etat(projet)["agents"]]
    try:
        cout = _cout(projet, flux, nouveaux + existants, genre)
        w = {"id": f"w-{fid}", "genre": genre, "flux": [dict(x) for x in flux]}
        if ctx.get("genre_nouveau"):
            w["genre_nouveau"] = ctx["genre_nouveau"]
        poste = _verifier_poste(projet, o["environnement"])
        briefs = dict(o["briefs"])
        if environnement.autonomes_a_installer(poste):       # un agent pour installer ce qu'il peut installer seul
            installateur, brief = _agent_d_installation(projet, nouveaux, flux)
            if installateur:
                nouveaux.append(installateur)
                briefs[ROLE_ENVIRONNEMENT] = brief
        organisation = {"services": services, "flux": flux, "agents": nouveaux, "briefs": briefs,
                        "cout": cout, "fonctionnalite": fid, "workflow": w, "livrable": o["livrable"],
                        "environnement": poste, "outils_installation": list(o["outils_installation"])}
        etapes = " puis ".join(x["nom"] for x in flux)
        livrable = o["livrable"].strip().rstrip(".")
        texte = (f"Voici le workflow que je propose pour « {f['nom']} » : {etapes}. Livrable : {livrable}. "
                 + (f"Agents à recruter : {', '.join(a.get('prenom') or a['cle'] for a in nouveaux)}. " if nouveaux
                    else "Aucun agent à recruter : ceux du projet suffisent. ")
                 + (f"Services à créer : {', '.join(s['nom'] for s in o['services'])}. " if o["services"] else "")
                 + _texte_du_poste(poste))
        lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": "organisation",
                                    "texte": texte.strip(), "organisation": organisation})
    except (Refus, ValueError) as e:
        return _proposition_ratee(projet, etat, ctx, f"Je n'ai pas pu mettre en place la proposition de workflow ({e}). "
                                                     "Que faire ?")
    _dire(projet, fid, texte.strip() + " Dites si vous l'acceptez.")
    _terminer(projet, ctx, "Je vous propose un workflow pour cette demande : à vous de le valider.")
    return []


def _proposition_ratee(projet, etat, ctx, texte):
    """Aucune proposition utilisable : une question au Directeur, avec l'issue qui laisse avancer (le workflow actuel)."""
    fid = ctx["fonctionnalite"]
    _m(etat, "proposition_ratee")[fid] = {k: v for k, v in ctx.items() if k != "demande"}
    _question(projet, fid, texte, [CONTINUER, JE_PRECISE], ctx)
    return []


def _reponse_proposition_ratee(projet, etat, demande, fid):
    """La réponse à « je n'ai pas pu proposer de workflow » : continuer avec celui qui existe, ou un texte qui guide une
    nouvelle proposition."""
    ctx = etat["proposition_ratee"].pop(fid)
    texte = (demande.get("texte") or "").strip()
    suite = {**ctx, "demande": demande["id"], "fonctionnalite": fid}
    if texte == JE_PRECISE:
        etat["proposition_ratee"][fid] = ctx
        _terminer(projet, suite, "Dites-moi en une phrase ce que le workflow doit contenir.")
        return []
    if CONTINUER in texte or not texte:
        _reprendre_un_workflow(projet, etat, fid, suite)
        _terminer(projet, suite, "C'est noté : je continue avec le workflow actuel ; le cadrage commence.")
        return _repondre_cadrage(projet, etat, fid)
    return _proposer(projet, etat, fid, suite, refus=texte)


def _classer_rate(projet, etat, fid, ctx):
    """Le genre n'a pas pu être classé (deux essais) : la fonctionnalité prend le genre du projet et le cadrage démarre."""
    genre = _genre_du_projet(_factory(projet))
    if genre:
        lancer(projet, "fonctionnalite", {"id": fid, "genre": genre})
        creation = wf.de_creation(_factory(projet), genre)
        if creation is not None:
            lancer(projet, "organisation", {"action": "reprendre", "fonctionnalite": fid, "workflow": creation["id"]})
    _dire(projet, fid, "Je n'ai pas réussi à classer le genre de cette demande"
                       + (f" : je la traite avec le genre du projet (« {genre} »)." if genre else "."))
    _terminer(projet, ctx, "Le genre de la demande n'a pas pu être classé : je la traite avec celui du projet.")
    return _repondre_cadrage(projet, etat, fid)


def _workflow_de_repli(projet, fid):
    """Le workflow qu'une fonctionnalité reprend sans proposition : le plus récent du même genre, sinon le principal ;
    `None` si le projet n'a aucun workflow."""
    fac = _factory(projet)
    f = _fonc(projet, fid)
    genre = f.get("genre") or _genre_du_projet(fac)
    ws = [w for w in wf.tous(fac) if w["id"] != f.get("workflow")]
    memes = [w for w in reversed(ws) if genre and w.get("genre") == genre and w["id"] != wf.PRINCIPAL]
    if memes:
        return memes[0]
    return next((w for w in ws if w["id"] == wf.PRINCIPAL), None)


def _reprendre_un_workflow(projet, etat, fid, ctx):
    """Sans proposition acceptée : la fonctionnalité suit le workflow le plus récent de son genre, sinon le principal, et
    le cadrage démarre. `False` si le projet n'a aucun workflow (rien n'est fait)."""
    w = _workflow_de_repli(projet, fid)
    if w is None:
        return False
    f = _fonc(projet, fid)
    if w.get("fonctionnalite") is None and w["id"] != wf.PRINCIPAL:    # un workflow de genre : on en prend une copie
        lancer(projet, "organisation", {"action": "reprendre", "fonctionnalite": fid, "workflow": w["id"]})
    else:
        entree = {"id": fid, "workflow": w["id"]}
        if not f.get("genre") and w.get("genre"):
            entree["genre"] = w["genre"]
        lancer(projet, "fonctionnalite", entree)
    _dire(projet, fid, "Je garde le workflow existant "
                       + ("du même genre." if w["id"] != wf.PRINCIPAL else "du projet."))
    return True


def _verifier_poste(projet, outils):
    """Les outils du poste, chacun marqué `en_place` ou `a_installer` (vérifié en code, jamais par l'IA). Un outil que le
    Directeur a déclaré installé reste `en_place` (`declare`, avec sa note) : il n'est pas revérifié."""
    if not outils:
        return []
    declares = {x.get("outil"): x for x in _factory(projet).get("environnement") or []
                if isinstance(x, dict) and x.get("declare") is True and x.get("etat") == "en_place"}
    a_verifier = [o for o in outils if o.get("outil") not in declares]
    verifies = iter(projet.verifier_environnement(a_verifier) if a_verifier else [])
    return [dict(o, etat="en_place", declare=True, note=declares[o["outil"]].get("note") or environnement.NOTE_DECLARE)
            if o.get("outil") in declares else next(verifies) for o in outils]


def _agent_d_installation(projet, nouveaux, flux, regles=None):
    """L'agent qui installe les outils du poste : sa fiche ouvre les outils d'installation (ajoutés à l'acceptation).
    Rien si un agent du rôle existe déjà (il reçoit alors les nouvelles règles) ; sinon une fiche et un brief. Son
    service : celui de la première étape du workflow (pas le premier du projet, souvent la facturation)."""
    fac = _factory(projet)
    try:
        fiches_ = fi.lire_toutes(fac["fiches"])
    except (fi.FicheInvalide, OSError):
        fiches_ = []
    return environnement.agent_d_installation(fiches_, nouveaux, flux, fac["services"], regles)


def _sur_organisation(projet, demande, etat):
    court = _etat(projet)
    d = next((x for x in court["decisions"] if x["id"] == demande["decision"] and x["genre"] == "organisation"), None)
    org = (d or {}).get("organisation") or {}
    if org.get("workflow"):
        return _sur_organisation_de_fonctionnalite(projet, demande, etat, d, org)
    if demande["verdict"] == "accepter":
        lancer(projet, "organisation", {"action": "appliquer", "decision": demande["decision"]})
        reponse = "La nouvelle organisation est en place."
    else:
        lancer(projet, "decision", {"action": "lever", "id": demande["decision"]})
        reponse = "C'est noté : l'organisation ne change pas."
    _terminer(projet, {"demande": demande["id"]}, reponse)
    return []


def _sur_organisation_de_fonctionnalite(projet, demande, etat, d, org):
    """L'utilisateur répond à la proposition de workflow d'une fonctionnalité."""
    fid, verdict = org["fonctionnalite"], demande["verdict"]
    suite = {"demande": demande["id"], "fonctionnalite": fid}
    if (org["workflow"].get("genre_nouveau")):
        suite["genre_nouveau"] = org["workflow"]["genre_nouveau"]
    if verdict == "accepter":
        entree = {"action": "appliquer", "decision": d["id"]}
        if demande.get("fable"):
            entree["fable"] = demande["fable"]
        r = lancer(projet, "organisation", entree)
        _dire(projet, fid, "Le workflow est en place" + (" ; " + r["genre_raison"] if r.get("genre_raison") else "."))
        actions = _apres_mise_en_place(projet, etat, fid, org, demande.get("installer") or [])
        _terminer(projet, suite, "Le workflow est en place.")
        return actions
    if verdict == "abandonner":
        lancer(projet, "decision", {"action": "lever", "id": d["id"]})
        lancer(projet, "fonctionnalite", {"id": fid, "etape": "deplacee", "deplacee_vers": "(demande abandonnée)"})
        _dire(projet, fid, "Demande abandonnée.")
        _terminer(projet, suite, "C'est noté : la demande est abandonnée.")
        return []
    texte = (demande.get("texte") or "").strip()
    if texte:
        lancer(projet, "decision", {"action": "lever", "id": d["id"]})
        return _proposer(projet, etat, fid, suite, refus=texte)
    if _workflow_de_repli(projet, fid) is None:
        _terminer(projet, suite, "Ce projet n'a encore aucun workflow : dites ce qu'il faut changer à la proposition "
                                 "(refuser avec un texte), ou abandonnez la demande.")
        return []
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    _reprendre_un_workflow(projet, etat, fid, suite)
    _terminer(projet, suite, "C'est noté : je garde un workflow existant ; le cadrage commence.")
    return _repondre_cadrage(projet, etat, fid)


def _texte_du_poste(poste):
    """Ce que le Directeur lit des outils du poste : ce qui est déjà en place, ce qui sera installé."""
    if not poste:
        return ""
    en_place = [x["outil"] for x in poste if x.get("etat") == "en_place"]
    manque = [f"{x['outil']} ({x['raison']})" if x.get("raison") else x["outil"] for x in poste if x.get("etat") != "en_place"]
    return ((f"Déjà en place sur le poste : {', '.join(en_place)}. " if en_place else "")
            + (f"À installer : {', '.join(manque)}. " if manque else ""))


def _apres_mise_en_place(projet, etat, fid, org, choisis=()):
    """Le workflow est en place. Rien ne manque : le cadrage démarre. Des outils manquent : l'utilisateur a pu choisir
    (`choisis`, les noms) d'en faire installer en autonomie ; ceux-là, et eux seuls (s'ils sont `autonome`), vont dans une
    tâche « Mise en place de l'environnement » qui ouvre le workflow, le cadrage vient après sa fin. Sans choix, jamais
    d'installation d'elle-même : une décision `environnement` donne pour chaque outil le lien officiel, le mode
    opératoire et, s'il peut l'être, le bouton qui l'installe en autonomie."""
    manquants = environnement.a_installer(org.get("environnement") or [])
    if not manquants:
        return _repondre_cadrage(projet, etat, fid)
    voulus = [x for x in environnement.autonomes_a_installer(manquants) if x["outil"] in choisis]
    if not voulus:
        return _poste_pret_ou_decision(projet, etat, fid)
    if not _assurer_l_installateur(projet, fid):
        return _poste_pret_ou_decision(projet, etat, fid, intro="Je n'ai pas pu recruter l'agent qui installe les outils.")
    _creer_tache(projet, environnement.TITRE_INSTALLATION, fid, ROLE_ENVIRONNEMENT, "environnement",
                 colonne=org["workflow"]["flux"][0]["id"], journal=environnement.journal_d_installation(voulus))
    _dire(projet, fid, "Avant le cadrage, j'installe en autonomie : " + ", ".join(x["outil"] for x in voulus) + ".")
    return _demarrer_en_attente(projet, etat, fid)


def _assurer_l_installateur(projet, fid):
    """L'agent qui installe les outils existe-t-il (le recruter sinon, dans le service de la première étape d'agent du
    workflow de la fonctionnalité) ? Faux si le recrutement a été refusé."""
    fac = _factory(projet)
    try:
        if any(a["role"] == ROLE_ENVIRONNEMENT for a in fi.lire_toutes(fac["fiches"])):
            return True
    except (fi.FicheInvalide, OSError):
        return False
    agent, brief = _agent_d_installation(projet, [], _flux(projet, fid), REGLES_D_INSTALLATION)
    if agent is None:
        return False
    try:
        lancer(projet, "organisation", {"action": "installateur", "agent": agent, "brief": brief})
    except Refus:
        return False
    return True


def _verifier_le_poste(projet, fid):
    """Revérifie les outils encore à installer, note le résultat dans les réglages, rend ceux qui manquent."""
    a_refaire = [x for x in _factory(projet)["environnement"] if x.get("etat") != "en_place"]
    verifies = _verifier_poste(projet, a_refaire)
    if verifies:
        lancer(projet, "organisation", {"action": "environnement", "outils": verifies})
    return environnement.a_installer(verifies)


def _poste_pret_ou_decision(projet, etat, fid, intro=None, tache=None):
    """Après l'installation (ou son échec) : tout est en place, le cadrage démarre ; sinon une décision au Directeur dit ce
    qui manque et comment l'installer à la main (« C'est fait » revérifie, « Continuer sans » laisse avancer). Sans
    fonctionnalité (l'installation portée par le projet, à sa création), la décision est celle du projet et aucun cadrage
    n'est retenu ni démarré."""
    manquants = _verifier_le_poste(projet, fid)
    if fid is None:
        return _poste_du_projet(projet, manquants, intro, tache)
    f = _fonc(projet, fid)
    if not manquants:
        for d in f.get("decisions") or []:
            if d["genre"] == "environnement":
                lancer(projet, "decision", {"action": "lever", "id": d["id"]})
        _dire(projet, fid, "Le poste est prêt : le cadrage commence.")
        return _repondre_cadrage(projet, etat, fid)
    texte = _texte_des_manquants(manquants, intro)
    ancienne = [d for d in f.get("decisions") or [] if d["genre"] == "environnement"]
    if _poser_la_decision_du_poste(projet, fid, ancienne, manquants, texte):
        _dire(projet, fid, texte)
    return []


def _poser_la_decision_du_poste(projet, portee, anciennes, manquants, texte):
    """Pose la décision `environnement` (de la fonctionnalité `portee`, ou du projet si `portee` vaut `"projet"`) avec
    les outils qui manquent. Une décision déjà posée pour les mêmes outils reste ; pour d'autres, elle est remplacée
    (un outil installé entre-temps disparaît de la liste). Vrai si une décision neuve a été posée."""
    noms = [x["outil"] for x in manquants]
    if any([x.get("outil") for x in d.get("environnement") or []] == noms for d in anciennes):
        return False
    for d in anciennes:
        lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    lancer(projet, "decision", {"action": "poser", "portee": portee, "genre": "environnement", "texte": texte,
                                "environnement": [dict(x) for x in manquants]})
    return True


def _texte_des_manquants(manquants, intro=None):
    return environnement.texte_des_manquants(manquants, intro)


def _decisions_d_environnement_du_projet(projet):
    return [d for d in _etat(projet)["decisions"] if d["portee"] == "projet" and d["genre"] == "environnement"]


def _poste_du_projet(projet, manquants, intro, tache):
    """La fin de l'installation portée par le projet : une ligne au journal de la tâche si tout est là, sinon la décision
    de projet `environnement` (une seule)."""
    if not manquants:
        for d in _decisions_d_environnement_du_projet(projet):
            lancer(projet, "decision", {"action": "lever", "id": d["id"]})
        if tache:
            lancer(projet, "tache", {"id": tache, "journal": ["Le poste est prêt : tous les outils sont en place."]})
        return []
    _poser_la_decision_du_poste(projet, "projet", _decisions_d_environnement_du_projet(projet), manquants,
                                _texte_des_manquants(manquants, intro))
    return []


def _verifier_la_decision(projet, d):
    """Revérifie, en code, **chaque outil de la décision** (pas ceux que les réglages du projet croient à installer : ils
    peuvent ne pas les connaître, ou les croire en place). Un outil d'une ancienne décision sans exécutables reprend
    ceux des réglages, s'ils le connaissent. Le résultat est noté dans les réglages du projet et dans la décision (état,
    ce qui a été cherché, version trouvée, heure). Rend les outils vérifiés."""
    connus = {x.get("outil"): x for x in _factory(projet).get("environnement") or [] if isinstance(x, dict)}
    outils = []
    for x in d.get("environnement") or []:
        x = {k: v for k, v in x.items() if k not in ("en_cours", "verification")}
        for cle in ("executables", "version_min"):
            if not x.get(cle) and (connus.get(x.get("outil")) or {}).get(cle):
                x[cle] = connus[x["outil"]][cle]
        outils.append(x)
    verifies = _verifier_poste(projet, outils)
    if verifies:
        lancer(projet, "organisation", {"action": "environnement", "outils": verifies})
        lancer(projet, "decision", {"action": "verifier", "id": d["id"],
                                    "outils": [dict(o, verification=environnement.constat(o)) for o in verifies]})
    return verifies


def _constats_en_clair(verifies):
    return " ; ".join(environnement.texte_du_constat(o["outil"], environnement.constat(o))
                      for o in environnement.a_installer(verifies))


def _forcer(projet, d, nom):
    """L'outil `nom` (ou tous ceux qui ne sont pas trouvés) que le Directeur affirme installés : noté « déclaré installé
    par le Directeur (non vérifié) » dans les réglages du projet et dans la décision. Rend (déclarés, restants)."""
    cibles = [x for x in d.get("environnement") or [] if x.get("etat") != "en_place" and (nom is None or x.get("outil") == nom)]
    if not cibles:
        raise Refus(f"« {nom} » n'est pas à forcer : absent de cette liste ou déjà trouvé." if nom
                    else "rien à forcer : tous les outils sont déjà trouvés.")
    declares = [environnement.declare(x) for x in cibles]
    lancer(projet, "organisation", {"action": "environnement", "outils": declares})
    lancer(projet, "decision", {"action": "verifier", "id": d["id"], "outils": declares})
    noms = {x["outil"] for x in cibles}
    restants = [x for x in d.get("environnement") or [] if x.get("etat") != "en_place" and x.get("outil") not in noms]
    return declares, restants


def _sur_environnement(projet, demande, etat):
    """La réponse à « il manque des outils sur le poste » (de la fonctionnalité, ou du projet sans `fonctionnalite`) :
    « C'est fait » revérifie chaque outil de la décision (la décision reste, outil par outil « trouvé » ou « non trouvé »,
    tant qu'un seul manque), « Forcer » déclare installés un outil (`outil`) ou tous ceux qui ne sont pas trouvés,
    « Continuer sans » laisse avancer."""
    fid = demande.get("fonctionnalite")
    if fid is None:
        d = next((x for x in _decisions_d_environnement_du_projet(projet) if x["id"] == demande["decision"]), None)
    else:
        d = _decision_de(_fonc(projet, fid), demande["decision"], "environnement")
    if d is None:
        raise Refus("cette question n'existe plus")
    suite = {"demande": demande["id"], **({"fonctionnalite": fid} if fid else {})}

    def finir(dit_projet, dit_fonctionnalite):
        """La décision est levée : le cadrage de la fonctionnalité commence, rien ne démarre pour le projet."""
        lancer(projet, "decision", {"action": "lever", "id": d["id"]})
        if fid is None:
            _terminer(projet, suite, dit_projet)
            return []
        _dire(projet, fid, "Le poste est prêt : le cadrage commence.")
        _terminer(projet, suite, dit_fonctionnalite)
        return _repondre_cadrage(projet, etat, fid)

    if demande["verdict"] == CONTINUER_SANS:
        lancer(projet, "decision", {"action": "lever", "id": d["id"]})
        if fid is None:
            _terminer(projet, suite, "C'est noté : le projet continue sans ces outils.")
            return []
        _dire(projet, fid, "Je continue sans ces outils : les étapes qui en ont besoin le diront.")
        _terminer(projet, suite, "C'est noté : le cadrage commence sans ces outils.")
        return _repondre_cadrage(projet, etat, fid)
    if demande["verdict"] == FORCER:
        declares, restants = _forcer(projet, d, demande.get("outil"))
        noms = ", ".join(x["outil"] for x in declares)
        if fid:
            _dire(projet, fid, f"{noms} : {environnement.NOTE_DECLARE}. Les étapes qui en ont besoin le sauront.")
        if not restants:
            return finir(f"C'est noté : {noms} {'est' if len(declares) == 1 else 'sont'} {environnement.NOTE_DECLARE}.",
                         f"C'est noté : {noms} {'est' if len(declares) == 1 else 'sont'} {environnement.NOTE_DECLARE}. "
                         "Le cadrage commence.")
        _terminer(projet, suite, f"C'est noté : {noms} ({environnement.NOTE_DECLARE}). Il reste : "
                                 + ", ".join(x["outil"] for x in restants) + ".")
        return []
    if demande["verdict"] != C_EST_FAIT:
        raise Refus(f"réponse inconnue : {demande['verdict']}")
    verifies = _verifier_la_decision(projet, d)
    manquants = environnement.a_installer(verifies)
    if manquants:
        _terminer(projet, suite, "Il manque encore : " + ", ".join(x["outil"] for x in manquants) + ". "
                  + _constats_en_clair(verifies) + ".")
        return []
    return finir("Merci, les outils sont en place.", "Merci, les outils sont en place : le cadrage commence.")


def _sur_installer_outil(projet, demande, etat):
    """Le clic « Installer en autonomie » d'un outil de la décision `environnement` : seul un outil `autonome`, encore
    absent du poste (revérifié en code), sans tâche d'installation en cours, reçoit sa tâche ; l'agent d'installation est
    recruté s'il n'existe pas. Jamais deux tâches pour le même outil. La décision reste : la fin de la tâche revérifie."""
    fid = demande.get("fonctionnalite")
    if fid is None:
        d = next((x for x in _decisions_d_environnement_du_projet(projet) if x["id"] == demande["decision"]), None)
    else:
        d = _decision_de(_fonc(projet, fid), demande["decision"], "environnement")
    if d is None:
        raise Refus("cette question n'existe plus")
    nom = demande["outil"]
    x = next((o for o in d.get("environnement") or [] if o.get("outil") == nom), None)
    if x is None:
        raise Refus(f"« {nom} » n'est pas dans cette liste")
    suite = {"demande": demande["id"]}
    if x.get("autonome") is not True:
        raise Refus(f"« {nom} » ne s'installe pas en autonomie : voir le lien et le mode opératoire")
    verifie = _verifier_poste(projet, [x])[0]
    if verifie.get("etat") == "en_place":
        _terminer(projet, suite, f"« {nom} » est déjà en place : rien à installer.")
        return _poste_pret_ou_decision(projet, etat, fid)
    if any(environnement.installe_par([j["texte"] for j in lancer(projet, "detail", {"tache": t["id"]})["journal"]], nom)
           for t in _etat(projet)["taches"]
           if t.get("etape") == "environnement" and t["colonne"] != "fait" and not t.get("bloquee")):
        raise Refus(f"l'installation de « {nom} » est déjà en cours")
    if not _assurer_l_installateur(projet, fid):
        raise Refus("je n'ai pas pu recruter l'agent qui installe les outils")
    _creer_tache(projet, environnement.TITRE_INSTALLATION, fid, ROLE_ENVIRONNEMENT, "environnement",
                 colonne=None if fid else "cadrage", journal=environnement.journal_d_installation([verifie]))
    if fid:
        _dire(projet, fid, f"J'installe « {nom} » en autonomie.")
    _terminer(projet, suite, f"L'installation de « {nom} » est lancée.")
    return _demarrer_en_attente(projet, etat, fid)


def _sur_genre(projet, demande, etat):
    court = _etat(projet)
    d = next((x for x in court["decisions"] if x["id"] == demande["decision"]), None)
    e = {"action": "fixer", "genre": demande["genre"]}
    description = demande.get("description") or (
        (d or {}).get("description") if demande["genre"] == (d or {}).get("propose") else None)
    if description:      # la phrase de l'utilisateur, sinon celle qui était proposée
        e["description"] = description
    lancer(projet, "genre", e)
    for x in court["decisions"]:
        if x["id"] == demande["decision"]:
            lancer(projet, "decision", {"action": "lever", "id": x["id"]})
    _terminer(projet, {"demande": demande["id"]}, f"Le genre du projet est « {demande['genre']} ».")
    fid = (d or {}).get("fonctionnalite")
    if fid:      # une fonctionnalité attendait ce genre : elle poursuit son parcours
        lancer(projet, "fonctionnalite", {"id": fid, "genre": demande["genre"]})
        return _proposer(projet, etat, fid, {"fonctionnalite": fid})
    return []


def _sur_elargir_genre(projet, demande, etat):
    """La réponse du Directeur à « élargir la description de ce genre ? » : valider (éventuellement corrigée) ou refuser.
    Dans les deux cas la fonctionnalité continue dans son genre."""
    d = next((x for x in _etat(projet)["decisions"] if x["id"] == demande["decision"] and x["genre"] == "elargir_genre"),
             None)
    if d is None:
        raise Refus("cette question n'existe plus")
    if demande["verdict"] == "valider":
        description = (demande.get("description") or "").strip() or d["propose"]
        lancer(projet, "genre", {"action": "decrire", "genre": d["cible"], "description": description})
        reponse = f"La description du genre « {d['cible']} » est élargie : {description}"
    elif demande["verdict"] == "refuser":
        reponse = f"La description du genre « {d['cible']} » ne change pas."
    else:
        raise Refus(f"réponse inconnue : {demande['verdict']}")
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
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
    _creer_tache(projet, "Retour : " + t["titre"], t.get("fonctionnalite"), t.get("role") or _role_production(projet, t.get("fonctionnalite")),
                       "retour", element=t.get("element"), journal=["Retour de l'utilisateur : " + demande["texte"]])
    _terminer(projet, {"demande": demande["id"]}, "J'ai confié votre retour à un agent.")
    return _demarrer_en_attente(projet, etat, t.get("fonctionnalite"))


def _sur_retour_element(projet, demande, etat):
    fid = demande["fonctionnalite"]
    role = _role_production(projet, fid)
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


def _element_en_validation(projet, etat, d):
    """L'état de l'élément que la décision `valider_etape` attend ; reconstruit depuis la décision quand le moteur a été
    relancé (sa mémoire était perdue). `None` si l'étape n'est plus dans le workflow."""
    fid, element = d["fonctionnalite"], d["element"]
    cle = f"{fid}/{element['id']}"
    v = _m(etat, "elements").get(cle)
    if v is not None and v["phase"] == "validation":
        return v
    rang = next((k for k, s in enumerate(_production(projet, fid)) if s["id"] == d["etape"]), None)
    if rang is None:
        return None
    v = _etat_element(etat, fid, element)
    v.update(phase="validation", pas=rang, taches=[d["tache"]] if d.get("tache") else [])
    v["dernier_rapport"] = {"compte_rendu": d.get("compte_rendu") or "", "fichiers": list(d.get("fichiers") or [])}
    return v


def _sur_valider_etape(projet, demande, etat):
    """La réponse du Directeur à « cet élément attend votre validation » : valider fait passer l'élément à l'étape
    suivante ; renvoyer (avec une remarque obligatoire) lui fait refaire l'étape précédente, puis revenir ici."""
    d = next((x for x in _etat(projet)["decisions"]
              if x["id"] == demande["decision"] and x["genre"] == GENRE_VALIDATION), None)
    if d is None:
        raise Refus("cette validation n'existe plus")
    verdict, remarque = demande.get("verdict"), (demande.get("texte") or "").strip()
    if verdict not in (VALIDER, RENVOYER):
        raise Refus(f"réponse inconnue : {verdict}")
    if verdict == RENVOYER and not remarque:
        raise Refus("pour renvoyer l'élément, dites ce qu'il faut changer (une remarque est obligatoire)")
    fid, element = d["fonctionnalite"], d["element"]
    v = _element_en_validation(projet, etat, d)
    if v is None:
        raise Refus("l'étape de validation n'est plus dans le workflow de cette fonctionnalité")
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    if d.get("tache"):
        journal = "Validé." if verdict == VALIDER else f"Renvoyé : {remarque}"
        lancer(projet, "tache", {"id": d["tache"], "colonne": "fait", "active": False, "journal": [journal]})
    v["phase"] = "flux"
    if verdict == VALIDER:
        _dire(projet, fid, f"« {element['nom']} » est validé : l'élément continue.")
        _terminer(projet, {"demande": demande["id"]}, "C'est validé : l'élément continue.")
        return _apres_flux(projet, etat, v) + _demarrer_en_attente(projet, etat, fid)
    v["pas"] -= 1
    _tache_de_flux(projet, etat, v, journal=[f"Remarque du Directeur : {remarque}"])
    _dire(projet, fid, f"« {element['nom']} » est renvoyé : l'étape précédente est refaite.")
    _terminer(projet, {"demande": demande["id"]}, "C'est renvoyé : l'étape précédente est refaite avec votre remarque.")
    return _demarrer_en_attente(projet, etat, fid)


_SUR = {"fonctionnalite": _sur_fonctionnalite, "message": _sur_message, "cahier": _sur_cahier, "methode": _sur_methode,
        "lecon": _sur_lecon, "genre": _sur_genre, "organisation": _sur_organisation,
        "genre_fonctionnalite": _sur_genre_fonctionnalite, "environnement": _sur_environnement,
        "installer_outil": _sur_installer_outil,
        "elargir_genre": _sur_elargir_genre,
        "session_cloud": _sur_session_cloud, "retour": _sur_retour, "retour_element": _sur_retour_element,
        "deplacer": _sur_deplacer, "bouton": _sur_bouton, "partenaire_regle": _sur_partenaires,
        "partenaires_actualiser": _sur_partenaires, "valider_etape": _sur_valider_etape, "partenaires_maj": _sur_partenaires, "challenge": _sur_challenge}


# --- Le cadrage et le prototype.

def _repondre_cadrage(projet, etat, fid, consigne=None):
    """Prépare la réponse de l'agent de cadrage (sa tâche, persistante) et la lance si l'agent est libre."""
    if _en_parcours(projet, etat, fid):
        return []      # le genre ou le workflow de la fonctionnalité attend encore une réponse
    f = _fonc(projet, fid)
    court = _etat(projet)
    agent = f.get("agent_cadrage")
    if agent is None:
        agent = lancer(projet, "agent-libre", {"role": _role_cadrage(projet, fid), "lieu": "local"})["agent"]
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
    role = _role_production(projet, fid)
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
                    "(`message.questions`, `attend: true`; `multiple: true` quand plusieurs choix vont ensemble). Dès ta première réponse, donne un `nom` court à la "
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
        production = _production(projet, fid)
        if (production and len(production) > 1 and _sans_relecteur(projet)
                and etape == ETAPES_DE_FLUX + production[_etape_de_relecture(projet, fid)]["id"]):
            parties.append("Tu es le dernier regard sur l'élément. Rends un `verdicts` : "
                           '`[{"element": <id>, "conforme": vrai|faux, "points": [chaque défaut trouvé, un texte]}]`, '
                           "un par élément. Un défaut devient un contrôle : sois précis.")
    elif etape == "relecture":
        parties += [f"Élément à relire : {t.get('element')}",
                    "Relis l'élément avec un regard neuf. Rends un `verdicts` : "
                    '`[{"element": <id>, "conforme": vrai|faux, "points": [chaque défaut trouvé, un texte]}]`. '
                    "Un défaut devient un contrôle : sois précis."]
    elif etape == "environnement":
        parties += ["Installe les outils du poste listés dans les consignes ci-dessous, un par un, puis vérifie chacun "
                    "(son chemin et sa version). Dans ton message, dis pour chaque outil : en place (chemin, version) ou "
                    "pas installé (pourquoi, et comment l'installer à la main). Si une installation échoue, n'insiste "
                    "pas : rends `statut: fait` avec ce constat."]
    elif etape in ("correction", "retour", "demande", "challenge"):
        parties.append(f"Élément : {t.get('element') or '(aucun)'}")
    if consignes:
        parties += ["Consignes :", consignes]
    return "\n".join(parties)


# --- Le retour d'un agent.

def _chemin_du_projet(projet, chemin):
    """Un chemin rendu par un agent, compté depuis le dossier de la factory (là où comptent le suivi et le bureau).
    L'agent travaille dans le dossier du projet, le parent de `.factory` : il écrit `.factory/pieces/a.png`, ou un
    chemin absolu. Un chemin hors de la factory est gardé tel quel."""
    if not isinstance(chemin, str) or not chemin.strip():
        return chemin
    p = Path(chemin.replace("\\", "/"))
    try:
        return (p if p.is_absolute() else projet.dossier / p).resolve().relative_to(
            projet.factory.resolve().parent).as_posix()
    except ValueError:
        return chemin


def _chemins_du_projet(projet, r):
    """Le rapport, ses chemins (images du message, maquette du cahier, fichiers) comptés depuis la factory."""
    r = dict(r)
    if isinstance(r.get("message"), dict) and isinstance(r["message"].get("images"), list):
        r["message"] = {**r["message"], "images": [_chemin_du_projet(projet, x) for x in r["message"]["images"]]}
    if isinstance(r.get("cahier"), dict) and isinstance(r["cahier"].get("maquette"), list):
        r["cahier"] = {**r["cahier"], "maquette": [_chemin_du_projet(projet, x) for x in r["cahier"]["maquette"]]}
    r["fichiers"] = [{**f, "chemin": _chemin_du_projet(projet, f.get("chemin"))} for f in r.get("fichiers") or []]
    return r


def traiter_retour(projet, execution, etat):
    """Applique le rapport d'un agent terminé (ou sa panne). Rend les actions qui restent."""
    depart = _m(etat, "departs").get(execution.tache) or {"agent": execution.agent, "taches": [execution.tache],
                                                          "matiere": "", "lot": execution.lot}
    taches = depart["taches"]
    etat["en_cours"].discard(taches[0])
    r = execution.rapport
    if r is None:
        return _agent_en_echec(projet, etat, execution, depart)
    r = _chemins_du_projet(projet, r)
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
        return _apres_echec_d_installation(projet, etat, taches, "L'installation a échoué : " + reponse[:200])
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
    return _apres_echec_d_installation(projet, etat, depart["taches"], raison)


def _apres_echec_d_installation(projet, etat, taches, raison):
    """Une installation qui échoue ne bloque pas la fonctionnalité : la décision au Directeur dit ce qui manque."""
    t = _tache(projet, taches[0])
    if str(t.get("etape")) != "environnement":
        return []
    return _poste_pret_ou_decision(projet, etat, t.get("fonctionnalite"), intro=raison, tache=t["id"])


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
    if etape == "environnement":
        return _poste_pret_ou_decision(projet, etat, fid, tache=t["id"])
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


def _tache_de_flux(projet, etat, v, journal=None):
    pas = _production(projet, v["fid"])
    s = pas[v["pas"]]
    if wf.est_validation(s):
        return _attendre_le_directeur(projet, v, s)
    tid = _creer_tache(projet, f"{s['nom']} : {v['element']['nom']}", v["fid"], s["role"], ETAPES_DE_FLUX + s["id"],
                       element=v["element"]["id"], colonne=s["id"], journal=journal)
    v["taches"].append(tid)
    return tid


def _attendre_le_directeur(projet, v, s):
    """L'élément arrive à une étape de validation : une tâche sans agent et une décision de projet, avec le compte rendu
    et les fichiers de l'étape précédente. Rien ne part tant que le Directeur n'a pas répondu."""
    v["phase"] = "validation"
    element = v["element"]
    tid = lancer(projet, "tache", {"titre": f"Validation du Directeur : {element['nom']}", "fonctionnalite": v["fid"],
                                   "etape": ETAPES_DE_VALIDATION + s["id"], "active": False, "colonne": s["id"],
                                   "element": element["id"]})["id"]
    v["taches"].append(tid)
    precedent = v.get("dernier_rapport") or {}
    entree = {"action": "poser", "portee": "projet", "genre": GENRE_VALIDATION, "fonctionnalite": v["fid"],
              "texte": f"L'élément « {element['nom']} » attend votre validation : « {s['nom']} ».",
              "element": {"id": element["id"], "nom": element["nom"]}, "etape": s["id"], "tache": tid,
              "compte_rendu": precedent.get("compte_rendu") or "", "fichiers": list(precedent.get("fichiers") or [])}
    lancer(projet, "decision", entree)
    return tid


def _retenir_le_rapport(v, r):
    """Le compte rendu (2000 caractères au plus) et les fichiers du dernier rapport pour cet élément : ce que le Directeur
    voit à la validation suivante."""
    if r is None:
        return
    eid = v["element"]["id"]
    texte = ((r.get("message") or {}).get("texte") or "").strip()
    fichiers = [{"chemin": f["chemin"], "titre": f["titre"]} for f in r.get("fichiers") or []
                if f.get("element") in (None, eid)]
    v["dernier_rapport"] = {"compte_rendu": texte[:COMPTE_RENDU_MAX], "fichiers": fichiers[:FICHIERS_MAX]}


def _sans_relecteur(projet):
    """Aucun agent relecteur : une étape du flux (un contrôle, des tests, le plus souvent) tient lieu de relecture."""
    return not any(a["role"] == ROLE_RELECTURE for a in _etat(projet)["agents"])


def _est_de_qualite(etape, services):
    """Vrai si l'étape est tenue par une équipe de qualité : son id, son nom, son rôle ou son service (id ou nom) parle de
    qualité, de tests, de contrôle ou de vérification."""
    mots = re.findall(r"[a-z0-9]+", normaliser_mot(" ".join(
        [str(etape.get(c) or "") for c in ("id", "nom", "role", "service")] + [services.get(etape.get("service"), "")])))
    return any(m == "qa" or m.startswith(MOTS_DE_QUALITE) for m in mots)


def _etape_de_relecture(projet, fid=None):
    """Sans relecteur, le rang (dans la production du workflow) de l'étape qui tient lieu de relecture : la dernière
    étape tenue par un service ou un rôle de qualité (les tests avant la livraison), à défaut la dernière du flux."""
    production = _production(projet, fid)
    services = {s["id"]: s["nom"] for s in _factory(projet)["services"]}
    for rang in range(len(production) - 1, -1, -1):
        if not wf.est_validation(production[rang]) and _est_de_qualite(production[rang], services):
            return rang
    return next((r for r in range(len(production) - 1, -1, -1) if not wf.est_validation(production[r])), 0)


def _apres_flux(projet, etat, v, r=None):
    _retenir_le_rapport(v, r)
    v["pas"] += 1
    sans = _sans_relecteur(projet)
    if sans and v["pas"] - 1 == _etape_de_relecture(projet, v["fid"]):
        # les verdicts de l'étape de qualité sur cet élément (un lot en porte pour chacun) ; aucun = conforme
        v["phase"], v["attendus"] = "relecture", 1
        v["rapports"] = [[x for x in (r or {}).get("verdicts") or [] if x["element"] == v["element"]["id"]]]
        return _conclure_relecture(projet, etat, v)
    if v["pas"] < len(_production(projet, v["fid"])):
        _tache_de_flux(projet, etat, v)
        return []
    if sans:       # la livraison, venue après un verdict favorable
        return _element_fait(projet, etat, v)
    v["phase"] = "relecture"
    return _lancer_relecture(projet, etat, v)


def _lancer_relecture(projet, etat, v):
    """Le premier tour : deux relecteurs à contexte neuf, qui ne se voient pas ; les tours suivants : un seul, qui ne
    vérifie que les points corrigés. Sans relecteur, l'étape de qualité du flux est refaite."""
    if _sans_relecteur(projet):
        v["phase"], v["pas"] = "flux", _etape_de_relecture(projet, v["fid"])
        _tache_de_flux(projet, etat, v)
        return []
    v["phase"], v["rapports"] = "relecture", []
    v["attendus"] = RELECTEURS_PREMIER_TOUR if v["tour"] == 0 and v["corrections"] == 0 else 1
    colonne = _colonne_du_role(projet, ROLE_RELECTURE, v["fid"])
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
        if _sans_relecteur(projet) and v["pas"] < len(_production(projet, v["fid"])):
            v["phase"] = "flux"        # verdict favorable : les étapes suivantes (la livraison) viennent maintenant
            _tache_de_flux(projet, etat, v)
            return []
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
    for d in _etat(projet)["decisions"]:     # le moteur relancé : les éléments qui attendent le Directeur reviennent
        if d["portee"] == "projet" and d["genre"] == GENRE_VALIDATION and d.get("fonctionnalite") == fid:
            _element_en_validation(projet, etat, d)
    mine = [v for v in elements.values() if v["fid"] == fid]
    if not revoir:
        for v in mine:
            if v["phase"] == "attente_methode":   # la méthode a été revue : l'élément repart de son premier pas
                v.update(phase="flux", pas=0, corrections=0, tour=0, taches=[], points=[])
                _tache_de_flux(projet, etat, v)
        vivants = sum(1 for v in mine if v["phase"] in ("flux", "relecture", "correction", "validation"))
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
        fid = contexte.get("fonctionnalite")
        if type_ == "classer_genre" and fid:
            return _classer_rate(projet, etat, fid, contexte)
        if type_ == "classer_genre":       # le genre d'un projet sans demande : il sera proposé à la première demande
            return []
        if type_ == "proposer_organisation" and fid:
            return _proposition_ratee(projet, etat, contexte, decision.question)
        _question(projet, fid, decision.question, ["Je précise", "Plus tard"], contexte)
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
        role = _role_production(projet, fid)
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
        role = fiche["role"] if fiche else _role_production(projet, fid)
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
          "ecrire_methode": _apres_ecrire_methode, "apres_refus": _apres_apres_refus, "conseil": _apres_conseil,
          "classer_genre": _apres_classer_genre, "proposer_organisation": _apres_proposer_organisation}
