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
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from installation import estimation
from moteur import accord_outil, agents, cloud, detache, environnement, rapport
from moteur.jugement import ACTIONS_CONSEIL, COMMANDES_INTERDITES_AU_CONSEIL  # noqa: F401
from bureau import fichiers_joints
from bureau import releve as rel
from bureau import reglages as reglages_du_bureau
from orchestrateur.memoire import normaliser_mot
from orchestrateur import depart as dep
from orchestrateur import factory as fa
from orchestrateur import fiches as fi
from orchestrateur import metiers
from orchestrateur import modele_necessaire as mn
from orchestrateur import outil
from orchestrateur import regles_projet as rp
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
ETAPE_INSTALLATION = "environnement"      # l'étape de la tâche d'installation, prioritaire sur tout le bureau
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
_MESURE = re.compile(r"charge (\d+) % \(max (\d+) %\)")     # la ligne de `lancer charge` : « attendre : charge 90 % (max 70 %) »


class Refus(Exception):
    """L'outil a refusé la commande (code 1) : le message est pour l'utilisateur."""


class ErreurMoteur(Exception):
    """Appel invalide (code 2) : le moteur lui-même s'est trompé, ou le projet est illisible."""


class Projet:
    """Un projet tenu par le moteur : son fichier de factory et la couche d'appel des jugements.
    `feu_vert` (rien -> bool) ou `mesure` (rien -> {feu_vert, charge, plafond}) remplace la mesure de charge (essais).

    Deux réglages que le moteur pose à chaque passage : `pause_globale` (le texte de la pause d'une installation
    prioritaire, dans un projet ou un autre : aucun agent neuf ne part) et `installations_a_part` (les tâches
    d'installation ne passent plus par le départ ordinaire, le moteur les lance lui-même, sans condition de charge)."""

    def __init__(self, factory, couche="claude", *, feu_vert=None, cloud_max=3, prerequis=None,
                 verifier_environnement=None, bureau=None, mesure=None):
        self.factory = Path(factory)
        self.couche = couche
        self._feu_vert = feu_vert
        self._mesure = mesure
        self.pause_globale = None
        self.mesure_commune = None        # posée par le moteur : projet -> mesure (une seule par tour pour tout le bureau)
        self.installations_a_part = False
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

    def charge(self):
        """La charge du poste contre le plafond du projet : `{feu_vert, charge, plafond}` (les deux nombres sont `None`
        quand la mesure ne les donne pas)."""
        if self._feu_vert is not None:
            return {"feu_vert": bool(self._feu_vert()), "charge": None, "plafond": None}
        if self._mesure is not None:
            return self._mesure()
        if self.mesure_commune is not None:      # une seule mesure par tour du moteur, pour tous les projets
            return self.mesure_commune(self)
        return self.mesurer()

    def plafond_charge(self):
        """Le plafond de charge de CE projet (`charge_max` de ses réglages), ou `None` s'il n'est pas lisible."""
        try:
            reglages = fa.lire(self.factory)["reglages"]
            if reglages is None:
                return None
            valeur = reglages_du_bureau.charger(reglages)["charge_max"]
        except Exception:
            return None
        return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else None

    def mesurer(self):
        """La vraie mesure : un sous-processus `lancer.py charge` (≈ 5 s)."""
        try:
            r = lancer(self, "charge")
        except Refus:
            return {"feu_vert": True, "charge": None, "plafond": None}   # une mesure impossible ne bloque pas le travail
        m = _MESURE.search(str(r.get("texte") or ""))
        return {"feu_vert": bool(r.get("feu_vert")), "charge": int(m.group(1)) if m else None,
                "plafond": int(m.group(2)) if m else None}

    def feu_vert(self):
        return bool(self.charge()["feu_vert"])


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
    if any(a["role"] == ROLE_CADRAGE for a in agents) or _metier_tenu(projet, agents, ROLE_CADRAGE):
        return ROLE_CADRAGE
    metier = next((a["role"] for a in agents if a.get("service") == "metier"), None)
    return metier or _role_production(projet, fid, agents)


def _role_production(projet, fid=None, agents=None):
    """Le rôle de la première étape de production du workflow ; sans workflow, celui de cadrage."""
    production = wf.etapes_d_agent(_production(projet, fid))
    if production:
        return production[0]["role"]
    return next((a["role"] for a in agents if a["role"] and a["role"] != ROLE_RELECTURE), ROLE_CADRAGE) \
        if agents else ROLE_CADRAGE


def _metier_tenu(projet, agents, role):
    """Vrai si un agent polyvalent peut tenir le métier : le projet a des agents polyvalents et le métier a son brief."""
    return any(_polyvalent(a) for a in agents) and _metier(projet, role) is not None


def _colonne_du_role(projet, role, fid=None):
    flux = _flux(projet, fid)
    if not flux:
        return "cadrage"
    return next((s["id"] for s in flux if s.get("role") == role), flux[-1]["id"])


def _chemin_pour_agent(projet, chemin):
    """Un chemin du suivi (compté depuis le dossier de la factory) compté depuis le dossier du projet, là où travaille l'agent."""
    try:
        base = Path(fa.lire(projet.factory)["base"]).resolve()
        return (base / chemin).resolve().relative_to(projet.dossier.resolve()).as_posix()
    except (fa.FactoryInvalide, ValueError, OSError):
        return chemin


def _texte_discussion(f, derniers=20, projet=None):
    """La discussion en texte pour l'agent ; sous un message, ses fichiers joints (chemin, type, taille) et, une fois, la
    consigne de les lire. Avec `projet`, les chemins sont comptés depuis le dossier du projet."""
    lignes, joints = [], False
    for m in (f.get("discussion") or [])[-derniers:]:
        lignes.append(f"- {m['auteur']} : {m['texte']}")
        fichiers = [{**x, "chemin": _chemin_pour_agent(projet, x["chemin"]) if projet else x["chemin"]}
                    for x in m.get("fichiers") or [] if isinstance(x, dict) and "chemin" in x]
        for ligne in fichiers_joints.lignes_pour_agent(fichiers):
            lignes.append(ligne)
            joints = True
    if joints:
        lignes.append(fichiers_joints.CONSIGNE_LECTURE)
    return "\n".join(lignes) or "(vide)"


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


def prenom_de(projet, cle):
    """Le prénom de l'agent (sa fiche), sinon sa clé."""
    try:
        fiche = fi.trouver(fi.lire_toutes(_factory(projet)["fiches"]), cle)
    except (OSError, fi.FicheInvalide, ErreurMoteur):
        fiche = None
    return (fiche or {}).get("prenom") or cle


def agent_au_travail(projet, etat, fid):
    """`(tâche, agent)` : l'agent local en plein travail sur une tâche active de la fonctionnalité, ou `None`."""
    en_cours = _m(etat, "en_cours", set)
    if not en_cours:
        return None
    court = _etat(projet)
    for t in court["taches"]:
        if (t.get("fonctionnalite") == fid and t.get("active") and t.get("agent") and t["id"] in en_cours
                and not fiche_cloud(court, t["agent"])):
            return t["id"], t["agent"]
    return None


def texte_question_transmise(prenom):
    return f"Question transmise à {prenom} : il répondra à la fin de sa tâche en cours."


def _transmettre_a_l_agent(projet, demande, fid, tid, agent):
    """Un message de l'utilisateur pendant qu'un agent travaille : il lui est transmis (pas de tâche « Retour ») ; le
    moteur le lui donne à la fin de sa tâche (`boucle.Moteur._transmettre_les_questions`)."""
    texte = " ".join(str(demande.get("texte") or "").split())
    n = len(demande.get("images") or [])
    if n:
        texte += f" (avec {n} image{'s' if n > 1 else ''}, visible{'s' if n > 1 else ''} dans la discussion)"
    joints = [{**x, "chemin": _chemin_pour_agent(projet, x["chemin"])} for x in demande.get("fichiers") or []
              if isinstance(x, dict) and "chemin" in x]
    if joints:      # tu peux les lire : chemin, type, taille de chacun
        texte += (" Fichiers joints (à lire si utile) :\n" + "\n".join(fichiers_joints.lignes_pour_agent(joints)) + "\n"
                  + fichiers_joints.CONSIGNE_LECTURE)
    detache.ajouter_question(projet.factory.parent, tid, texte or "(message sans texte)")
    dit = texte_question_transmise(prenom_de(projet, agent))
    _dire(projet, fid, dit)
    _terminer(projet, {"demande": demande["id"]}, dit)
    return []


def _sur_message(projet, demande, etat):
    fid = demande["fonctionnalite"]
    f = _fonc(projet, fid)
    accord = _m(etat, "accords").get(fid)
    if accord is not None and f["etape"] in ("cadrage", "cahier", "prototype", "serie"):
        return _reponse_a_une_question(projet, etat, demande, f, accord)
    travail = agent_au_travail(projet, etat, fid)
    if travail is not None:
        return _transmettre_a_l_agent(projet, demande, fid, *travail)
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
        if (f.get("cahier") or {}).get("partenaires") is not None:     # décidés au cadrage : le cahier validé les garde
            cahier["partenaires"] = f["cahier"]["partenaires"]
        cahier["valide_le"] = su.maintenant()
        lancer(projet, "fonctionnalite", {"id": fid, "cahier": cahier, "etape": "decoupage"})
        _lever(projet, f, "valider_cahier")
        dossier = {"fonctionnalite": {"nom": f["nom"], "cahier": {"maquette": cahier.get("maquette"),
                                                                    "etapes": cahier.get("etapes")}},
                   "flux": [{"id": s["id"], "nom": s["nom"], "validation": True} if wf.est_validation(s)
                            else {"id": s["id"], "nom": s["nom"], "role": s["role"]}
                            for s in _production(projet, fid)],
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
        correction = (demande.get("texte") or "").strip()
        if correction:      # la correction écrite dans la fenêtre de la méthode : l'agent reprend avec elle
            try:
                return _retoucher_prototype(projet, etat, fid, "Correction de la méthode demandée par l'utilisateur : "
                                            + correction)
            except Refus:
                _dire(projet, fid, "Correction de la méthode demandée : " + correction, attend=False)
                return []
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
    return traiter_lecons(projet, [demande], etat)


def traiter_lecons(projet, demandes, etat):
    """Les verdicts sur des leçons, pris ensemble : un seul appel `lecon appliquer` avec `lot`, donc une seule mise à
    jour du dépôt de la skill et un seul push ; chaque demande reçoit le résultat de sa leçon. Une leçon validée dont
    l'écriture n'a pas abouti est dite « retenue » : elle quitte la liste à valider et le moteur la réécrit seul."""
    lot = []
    for d in demandes:
        x = {"id": d["cible"], "verdict": d["verdict"]}
        if d.get("etage"):
            x["etage"] = d["etage"]
        lot.append(x)
    try:
        resultats = {x["id"]: x for x in lancer(projet, "lecon", {"action": "appliquer", "lot": lot})["resultats"]}
    except Refus as e:
        for d in demandes:
            _terminer(projet, {"demande": d["id"]}, f"Je n'ai pas pu le faire : {e}")
        return []
    for d in demandes:
        x = resultats.get(d["cible"]) or {}
        if not x.get("ok"):
            reponse = f"Je n'ai pas pu le faire : {x.get('refus') or 'leçon inconnue'}"
        elif d["verdict"] != "valider":
            reponse = "La leçon est écartée."
        elif x.get("en_attente"):
            reponse = ("La leçon est retenue, mais son écriture dans la mémoire de la skill est en attente : "
                       f"{x.get('raison')} Je réessaie seul.")
        else:
            reponse = "La leçon est retenue."
        _terminer(projet, {"demande": d["id"]}, reponse)
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


LONGUEUR_DEMARRAGE = 80          # au-delà, ce n'est plus une simple intention de démarrer
_VERBES_DE_DEMARRAGE = (r"(?:demarr\w*|commenc\w*|lanc\w*|continu\w*|reprend\w*|reprenn\w*|debut\w*)")
_COMPLEMENTS_DE_DEMARRAGE = (r"(?:le|la|l|les|ce|cette|mon|ma|notre|du|de|d|des|tout|ca|cela|projet|jeu|developpement|"
                             r"dev|travail|production|creation|realisation|construction|app|application|maintenant|"
                             r"alors|enfin|donc|ok|bon|allez|svp|stp|s|il|te|vous|plait)")
INTENTION_DE_DEMARRAGE = re.compile(
    rf"(?:(?:ok|bon|allez|alors|et)\s+)*(?:(?:on|nous|je|tu|vous)\s+)?(?:(?:peut|veux|voudrais|va|vais)\s+)?"
    rf"{_VERBES_DE_DEMARRAGE}(?:\s+{_COMPLEMENTS_DE_DEMARRAGE})*"
    r"|(?:ok\s+|bon\s+|allez\s+)?(?:go|gogo|start|c\s+est\s+parti|allons\s+y|on\s+y\s+va|on\s+s\s+y\s+met|let\s+s\s+go)"
    r"(?:\s+(?:le|projet|maintenant|svp|stp|s\s+il\s+te\s+plait))*")


def est_intention_de_demarrage(texte):
    """Vrai si la demande n'est qu'une intention de lancer, commencer ou continuer le projet (« démarrer le projet »,
    « on commence », « go »), sans aucune fonctionnalité nommée : courte, et composée de ces seuls mots."""
    brut = unicodedata.normalize("NFKD", str(texte or "").lower())
    brut = "".join(c for c in brut if not unicodedata.combining(c))
    brut = " ".join(re.sub(r"[^a-z0-9]+", " ", brut).split())
    return bool(brut) and len(str(texte).strip()) <= LONGUEUR_DEMARRAGE and INTENTION_DE_DEMARRAGE.fullmatch(brut) is not None


def _demarrage_du_projet(projet, etat, fid, suite):
    """Garde-fou sans appel IA : la demande d'un projet qui a une description et un workflow de création n'est qu'une
    intention de démarrer. Elle vise le projet tel que décrit : genre du projet, workflow de création, cadrage. `None`
    si la demande n'est pas de cette sorte."""
    fac = _factory(projet)
    demande = _demande_de(_fonc(projet, fid))
    genre = _genre_du_projet(fac)
    creation = wf.de_creation(fac, genre) if genre else None
    if (creation is None or not str(fac.get("description") or "").strip() or demande["images"]
            or not est_intention_de_demarrage(demande["texte"])):
        return None
    lancer(projet, "fonctionnalite", {"id": fid, "genre": genre})
    _nommer(projet, fid, " ".join(str(fac.get("nom") or "").split()) or _resume_de_la_demande(fac["description"]))
    return _suivre_le_workflow_de_creation(projet, etat, fid, suite, creation)


def _classer(projet, etat, fid, suite):
    """L'appel qui classe la demande (Haiku). Un projet sans genre classe sa description ; la fonctionnalité attend la
    réponse (`confirmer_genre`). Si ce genre est déjà proposé, la décision porte désormais la fonctionnalité (pas de
    second classement). Une simple intention de démarrer le projet n'est pas classée : voir `_demarrage_du_projet`."""
    fac = _factory(projet)
    f = _fonc(projet, fid)
    demarrage = _demarrage_du_projet(projet, etat, fid, suite)
    if demarrage is not None:
        return demarrage
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
                force_elargir=False, a_lever=None):
    """La fonctionnalité reste dans ce projet avec le genre `genre` (connu, ou nouveau avec sa description), puis son
    workflow est proposé. Refus si un genre nouveau n'a pas de description (rien n'est alors changé). `decision` : la
    question à lever, dont dépend l'élargissement ; `a_lever`, si elle est donnée sans `decision`, est levée seule."""
    fac = _factory(projet)
    nouveau = nouveau or {}
    if genre not in connus and genre not in _genres_du_projet(fac):
        description = description or (nouveau.get("description") if nouveau.get("id") == genre else None)
        if not description:
            raise Refus(f"« {genre} » est un nouveau genre : il a besoin d'une description")
        suite = {**suite, "genre_nouveau": {"description": description}}
    levee = decision if decision is not None else a_lever
    if levee is not None:
        lancer(projet, "decision", {"action": "lever", "id": levee["id"]})
    lancer(projet, "fonctionnalite", {"id": fid, "genre": genre})
    if decision is not None and (force_elargir or _gardee_hors_piste(decision, genre)):
        _proposer_elargissement(projet, fid, genre,
                                decision.get("elargissement") if genre == _genre_du_projet(fac) else None)
    creation = wf.de_creation(fac, genre)
    if creation is not None and genre == _genre_du_projet(fac):    # le genre du projet : son workflow de création
        return _suivre_le_workflow_de_creation(projet, etat, fid, suite, creation)
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
    # « Démarrer le projet » ne décrit aucun travail qui sorte du genre : rien à élargir, ni à proposer de nouveau
    sans_elargir = est_intention_de_demarrage(_demande_de(f)["texte"]) and genre == _genre_du_projet(fac)
    return _garder_ici(projet, etat, fid, suite, genre, d.get("genres_connus") or [], d.get("nouveau"),
                       demande.get("description"), None if sans_elargir else d, force_elargir=choix == "meme",
                       a_lever=d)


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
    regles = [x["texte"] for x in rp.lire(fac)]
    if regles:      # ce que le Directeur a retenu pour ce projet : le workflow proposé les respecte
        dossier["regles_projet"] = regles
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
    flux = [{"id": f"{fid}-{x['etape']}", "nom": x["nom"], **(
                {"validation": True, **({"raison": x["raison"]} if isinstance(x.get("raison"), str) and x["raison"].strip()
                                        else {})} if wf.est_validation(x)
                else {"role": x["role"], "service": x["service"],
                      **{c: x[c] for c in ("modele", "justification") if c in x}})}
            for x in o["flux"]]
    # Les nouveaux agents ont le plafond Opus ; les modèles justifiés vont sur les étapes (conception
    # 2026-11-12-modele-par-tache-design.md).
    flux, nouveaux = mn.modeles_sur_les_etapes(flux, [dict(a, lieu="local") for a in o["agents"]])
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


def reafficher_les_outils_manquants(projet, etat):
    """Un outil que l'environnement noté du projet dit à installer ne doit jamais disparaître de l'écran : revérifié en
    code, s'il manque toujours et qu'aucune décision d'environnement n'est ouverte (du projet ou d'une fonctionnalité) ni
    aucune tâche d'installation en attente ou en cours pour lui, la décision « Environnement du poste à compléter » est
    (re)posée pour le projet, avec ses champs (objectif, lien, étapes, autonome). Rend vrai si elle l'a été. Appelée au
    démarrage du moteur et après toute fin d'installation : jamais de doublon."""
    notes = [x for x in _factory(projet).get("environnement") or [] if isinstance(x, dict) and x.get("etat") != "en_place"]
    if not notes:
        return False
    court = _etat(projet)
    if (any(d["portee"] == "projet" and d["genre"] == "environnement" for d in court["decisions"])
            or any(d["genre"] == "environnement" for f in court["fonctionnalites"] for d in f["decisions"])):
        return False
    couverts, tout = set(), False
    for t in court["taches"]:
        if t.get("etape") == ETAPE_INSTALLATION and t["colonne"] != "fait" and not t.get("bloquee"):
            noms = outils_de_la_tache(projet, t["id"])
            couverts.update(noms)
            tout = tout or not noms
    if tout:
        return False
    verifies = _verifier_poste(projet, notes)
    lancer(projet, "organisation", {"action": "environnement", "outils": verifies})
    manquants = [x for x in environnement.a_installer(verifies) if x["outil"] not in couverts]
    if not manquants:
        return False
    return _poser_la_decision_du_poste(projet, "projet", [], manquants, _texte_des_manquants(manquants))


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
    from moteur import cloud
    agent, lue = d["agent"], cloud.lire_session(demande["session"])
    lancer(projet, "session", {"agent": agent, "session": lue["adresse"] if lue else demande["session"]})
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    suivie = None
    if lue:
        _m(etat, "sessions_cloud")[agent] = lue["session"]    # les tâches suivantes de l'agent y seront envoyées
        suivie = next((t for t in court["taches"] if t["id"] == d.get("tache") and t["colonne"] != "fait"), None)
    attend_amont = suivie is not None and not _amont_pret(projet, etat, suivie, court)
    if attend_amont:
        # l'amont attend une validation du Directeur : la tâche n'est pas relevée maintenant ; elle repart par le départ
        # ordinaire (vers la session inscrite de l'agent) une fois l'amont prêt
        lancer(projet, "tache", {"id": suivie["id"], "bloquee": None, "lot": None, "journal": [
            "Session cloud inscrite par le Directeur ; la tâche attend une validation en amont avant de partir."]})
        if suivie["id"] not in _m(etat, "a_lancer", list):
            etat["a_lancer"].append(suivie["id"])
        suivie = None
    if suivie is not None:
        # La session créée à la main porte le départ de cette tâche : le moteur la relève, sans en lancer d'autre.
        tid = suivie["id"]
        fiche = next((a for a in court["agents"] if a["cle"] == agent), {})
        modele = str(d.get("modele") or fiche.get("modele") or "sonnet").lower()
        lancer(projet, "tache", {"id": tid, "bloquee": None, "active": True, "agent": agent, "journal": [
            f"Session cloud {lue['session']} ({modele}) : {lue['adresse']}",
            "Session créée par le Directeur : le moteur la relève."]})
        etat["departs"][tid] = {"agent": agent, "taches": [tid], "matiere": "", "modele": modele, "lot": None,
                                "suite": None}
        etat["en_cours"].add(tid)
        _m(etat, "relancees", set).discard(tid)
        _m(etat, "cloud")[tid] = {"session": lue["session"], "adresse": lue["adresse"], "depuis": None,
                                  "taches": [tid], "agent": agent, "modele": modele, "lot": None,
                                  "muette_dite": False, "vu": None}
    # Les autres tâches de cet agent bloquées faute de session cloud repartent : le moteur relance lui-même la session
    # (ou, s'il ne le peut pas, les envoie à la session inscrite).
    reprises = [t for t in court["taches"] if t.get("agent") == agent and t["colonne"] != "fait"
                and ERREUR_CLOUD in str(t.get("bloquee") or "") and t is not suivie
                and not (attend_amont and t["id"] == d.get("tache"))]
    for t in reprises:
        # sortie de son lot (une tâche en lot ne repart jamais seule) et remise dans les départs à faire
        lancer(projet, "tache", {"id": t["id"], "bloquee": None, "lot": None,
                                 "journal": ["Session cloud créée par le Directeur : nouvel essai."]})
        _m(etat, "relancees", set).discard(t["id"])
        if t["id"] not in _m(etat, "a_lancer", list):
            etat["a_lancer"].append(t["id"])
    projet._cloud_raison = (None, 0.0)
    _terminer(projet, {"demande": demande["id"]}, "La session est inscrite."
              + (f" La tâche « {suivie['titre']} » y est relevée." if suivie is not None else "")
              + (f" {len(reprises)} tâche(s) bloquée(s) repartent." if reprises else "")
              + (" La tâche attend une validation en amont." if attend_amont else ""))
    return _demarrer_en_attente(projet, etat, None) if reprises or attend_amont else []


def _tache_a_reprendre(t):
    """Vrai si un retour sur cette tâche la reprend : bloquée, ou arrêtée (commencée, plus active) sans être faite. Pas
    les validations du Directeur, qui ne sont pas le travail d'un agent."""
    if t["colonne"] == "fait" or str(t.get("etape") or "").startswith("validation"):
        return False
    return bool(t.get("bloquee")) or (not t["active"] and bool(t.get("debut")))


TACHE_DU_CHEF = "orchestration"     # la tâche que le relevé montre au Chef (pas une vraie tâche du suivi)


def _question_au_chef(projet, demande, etat):
    """Un message au Chef (un retour sur sa tâche « Orchestration ») : il répond d'après l'état de tout le projet ; la
    réponse s'affiche au bureau, sous la question (panneau du Chef et espace de direction)."""
    court = _etat(projet)
    prenoms = {a["cle"]: prenom_de(projet, a["cle"]) for a in court["agents"]}
    taches = [{"id": t["id"], "titre": t["titre"], "colonne": t["colonne"], "agent": prenoms.get(t.get("agent")),
               "active": t.get("active"), "bloquee": t.get("bloquee"), "debut": t.get("debut"),
               "dernier_journal": str(t.get("dernier_journal") or "")[:200]}
              for t in court["taches"] if t["colonne"] != "fait"][:40]
    dossier = {"evenement": {"type": "question_chef", "texte": demande.get("texte")},
               "etat": {"projet": court["projet"], "pause": court["pause"],
                        "fonctionnalites": [{k: f.get(k) for k in ("id", "nom", "etape")} for f in court["fonctionnalites"]],
                        "decisions": [{k: d.get(k) for k in ("id", "genre", "texte")} for d in court["decisions"]][:20],
                        "taches": taches,
                        "en_cours": sorted(_m(etat, "en_cours", set))},
               "consignes_propres": _consignes_propres(projet),
               "commandes": sorted(c for c in outil.COMMANDES if c not in COMMANDES_INTERDITES_AU_CONSEIL)}
    return [a_juger("conseil", dossier, {"demande": demande.get("id"), "fonctionnalite": None})]


def _sur_retour(projet, demande, etat):
    if demande.get("tache") == TACHE_DU_CHEF:
        return _question_au_chef(projet, demande, etat)
    t = _tache(projet, demande["tache"])
    fid = t.get("fonctionnalite")
    travail = agent_au_travail(projet, etat, fid) if fid else None
    if travail is not None and travail[0] == t["id"]:      # l'agent est en plein travail sur cette tâche
        return _transmettre_a_l_agent(projet, demande, fid, *travail)
    if _validation_bloquee(t) and fid and t.get("element"):
        return _refaire_avant_la_validation(projet, demande, etat, t)
    if _tache_a_reprendre(t) and t["id"] not in _m(etat, "en_cours"):
        # le retour reprend CETTE tâche (même agent, même élément) : débloquée aussitôt, pas de tâche « Retour » à part
        texte = " ".join(str(demande["texte"]).split())
        _terminer(projet, {"demande": demande["id"]}, "Je reprends la tâche bloquée avec votre consigne.")
        return _reprendre_la_tache(projet, etat, t["id"], fid,
                                   "Consigne de l'utilisateur pour la reprise de cette tâche : " + demande["texte"],
                                   "Reprise sur votre retour : " + texte)
    _creer_tache(projet, "Retour : " + t["titre"], t.get("fonctionnalite"), t.get("role") or _role_production(projet, t.get("fonctionnalite")),
                       "retour", element=t.get("element"), journal=["Retour de l'utilisateur : " + demande["texte"]])
    _terminer(projet, {"demande": demande["id"]}, "J'ai confié votre retour à un agent.")
    return _demarrer_en_attente(projet, etat, t.get("fonctionnalite"))


def _validation_bloquee(t):
    return t["colonne"] != "fait" and bool(t.get("bloquee")) and str(t.get("etape") or "").startswith(
        ETAPES_DE_VALIDATION)


def _refaire_avant_la_validation(projet, demande, etat, t):
    """Un retour sur une validation bloquée (rien à vérifier, consigne manquante…) : comme un renvoi, l'étape d'avant
    est refaite avec le texte du Directeur, et la validation sera reposée ensuite. Tout se règle depuis le bureau."""
    fid, eid = t["fonctionnalite"], t["element"]
    reprendre_la_serie(projet, etat, fid)
    v = _m(etat, "elements").get(f"{fid}/{eid}")
    production = _production(projet, fid)
    rang = next((k for k, s in enumerate(production) if ETAPES_DE_VALIDATION + s["id"] == t["etape"]), None)
    avant = None if rang is None else next((k for k in range(rang - 1, -1, -1)
                                            if not wf.est_validation(production[k])), None)
    if v is None or avant is None:
        raise Refus("l'étape à refaire avant cette validation n'est plus dans le workflow")
    texte = " ".join(str(demande["texte"]).split())
    lancer(projet, "tache", {"id": t["id"], "colonne": "fait", "active": False, "bloquee": None,
                             "journal": [f"Renvoyé : {texte}"]})
    v.pop("rien_a_verifier", None)
    v.update(phase="flux", pas=avant)
    _tache_de_flux(projet, etat, v, journal=[f"Remarque du Directeur : {texte}"])
    _dire(projet, fid, f"« {v['element']['nom']} » : l'étape « {production[avant]['nom']} » est refaite avec votre "
                       "retour, puis la validation sera reposée.")
    _terminer(projet, {"demande": demande["id"]}, "L'étape précédente est refaite avec votre retour ; la validation "
                                                  "sera reposée ensuite.")
    return _demarrer_en_attente(projet, etat, fid)


def _sur_retour_element(projet, demande, etat):
    fid = demande["fonctionnalite"]
    role = _role_production(projet, fid)
    reprendre_la_serie(projet, etat, fid)
    tid = _creer_tache(projet, f"{TITRE_RETOUR_ELEMENT} {demande['element']}", fid, role, "retour",
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
        # `actions` met l'identifiant de la demande dans `id` et celui de la règle visée dans `cible`
        if demande.get("cible"):
            e["id"] = demande["cible"]
        if demande.get("texte"):
            e["texte"] = demande["texte"]
        lancer(projet, "partenaires", e)
        reponse = "La règle est notée."
    elif genre == "partenaire_inscrit":     # « Je suis inscrit » / « Je ne suis plus inscrit » : le fait, jamais un identifiant
        e = {"action": "inscrire", "partenaire": demande["partenaire"], "inscrit": demande["inscrit"]}
        if demande.get("note"):
            e["note"] = demande["note"]
        try:
            lancer(projet, "partenaires", e)
        except Refus as ex:
            _terminer(projet, {"demande": demande["id"]}, f"L'inscription n'a pas été notée : {ex}")
            return []
        reponse = "C'est noté : vous êtes inscrit." if demande["inscrit"] else "C'est noté : vous n'êtes plus inscrit."
    elif genre == "partenaires_actualiser":
        r = lancer(projet, "partenaires", {"action": "quota", "force": True})
        reponse = f"Quotas relus ({len(r.get('lus') or [])} partenaire(s))."
    else:
        r = lancer(projet, "partenaires", {"action": "a_refaire"})
        reponse = (f"{len(r.get('ids') or [])} fiche(s) sont à revérifier, mais le moteur ne sait pas encore lancer "
                   "cette recherche : rien n'a été modifié.")
    _terminer(projet, {"demande": demande["id"]}, reponse)
    return []


def _sur_regle_projet(projet, demande, etat):
    """Une règle du projet ajoutée, modifiée ou supprimée depuis le bureau de direction (`lancer regles`)."""
    e = {"action": demande["operation"]}
    if demande.get("cible"):          # l'`id` de la règle visée : la demande a gardé le sien, l'ancien est devenu `cible`
        e["id"] = demande["cible"]
    if demande.get("texte"):
        e["texte"] = demande["texte"]
    try:
        lancer(projet, "regles", e)
    except Refus as ex:
        _terminer(projet, {"demande": demande["id"]}, f"La règle n'a pas été notée : {ex}")
        return []
    _terminer(projet, {"demande": demande["id"]},
              {"ajouter": "La règle est notée.", "modifier": "La règle est modifiée.",
               "supprimer": "La règle est supprimée."}[demande["operation"]])
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
    v["dernier_rapport"] = {"compte_rendu": d.get("compte_rendu") or "", "fichiers": list(d.get("fichiers") or []),
                            "points": list(d.get("points") or []), "acces": d.get("acces"),
                            **{c: d[c] for c in ("doit_marcher", "pas_encore", "conclusion", "nature",
                                                 "mode_operatoire") if c in d}}
    return v


def _remarque_des_reponses(d, demande):
    """La fenêtre de validation : `(verdict, remarque)` tirés des réponses point par point. Les points doivent être
    exactement ceux de la décision (un seul, « L'élément correspond à l'objectif », pour une décision d'avant) ; le
    verdict de la demande doit en découler. Tous OK : la remarque est le texte libre (une note, peut-être vide) ; sinon
    la remarque structurée : les points à revoir, puis le texte libre."""
    reponses, texte = demande.get("reponses"), " ".join(str(demande.get("texte") or "").split())
    probleme = outil.erreur_reponses(reponses, demande.get("verdict"))
    if probleme:
        raise Refus(probleme)
    if sorted(x["point"].strip() for x in reponses) != sorted(rel.points_de_decision(d)):
        raise Refus("les réponses ne portent pas sur les points de cette validation : rouvrez-la")
    refuses = [x["point"].strip() for x in reponses if not x["ok"]]
    if not refuses:
        return VALIDER, texte
    return RENVOYER, f"points à revoir : {' ; '.join(refuses)}." + (f" {texte}" if texte else "")


def _sur_valider_etape(projet, demande, etat):
    """La réponse du Directeur à « cet élément attend votre validation » : valider fait passer l'élément à l'étape
    suivante (le texte libre, s'il y en a, est noté et joint à la tâche suivante) ; renvoyer lui fait refaire l'étape
    précédente, puis revenir ici. Depuis la fenêtre de validation, la demande porte une réponse par point
    (`reponses`) ; sans elle (une page d'avant), renvoyer exige une remarque."""
    d = next((x for x in _etat(projet)["decisions"]
              if x["id"] == demande["decision"] and x["genre"] == GENRE_VALIDATION), None)
    if d is None:
        raise Refus("cette validation n'existe plus")
    verdict, remarque = demande.get("verdict"), (demande.get("texte") or "").strip()
    if verdict not in (VALIDER, RENVOYER):
        raise Refus(f"réponse inconnue : {verdict}")
    if "reponses" in demande:
        verdict, remarque = _remarque_des_reponses(d, demande)
    elif verdict == RENVOYER and not remarque:
        raise Refus("pour renvoyer l'élément, dites ce qu'il faut changer (une remarque est obligatoire)")
    fid, element = d["fonctionnalite"], d["element"]
    v = _element_en_validation(projet, etat, d)
    if v is None:
        raise Refus("l'étape de validation n'est plus dans le workflow de cette fonctionnalité")
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    if d.get("tache"):
        journal = (("Validé." + (f" Note du Directeur : {remarque}" if remarque else "")) if verdict == VALIDER
                   else f"Renvoyé : {remarque}")
        lancer(projet, "tache", {"id": d["tache"], "colonne": "fait", "active": False, "journal": [journal]})
    v["phase"] = "flux"
    if verdict == VALIDER:
        if remarque:      # hors du champ de la validation : transmis à l'agent de l'étape suivante
            v["journal_suivant"] = [f"Note du Directeur à la validation « {element['nom']} » : {remarque}"]
        _dire(projet, fid, f"« {element['nom']} » est validé : l'élément continue."
                           + (f" Votre note : {remarque}" if remarque else ""))
        _terminer(projet, {"demande": demande["id"]}, "C'est validé : l'élément continue.")
        return _apres_flux(projet, etat, v) + _demarrer_en_attente(projet, etat, fid)
    v["pas"] -= 1
    _tache_de_flux(projet, etat, v, journal=[f"Remarque du Directeur : {remarque}"])
    _dire(projet, fid, f"« {element['nom']} » est renvoyé : l'étape précédente est refaite.")
    _terminer(projet, {"demande": demande["id"]}, "C'est renvoyé : l'étape précédente est refaite avec votre remarque.")
    return _demarrer_en_attente(projet, etat, fid)


def _sur_parallelisme(projet, demande, etat):
    """Les places du projet, réglées depuis l'onglet Facturation : écrites par l'outil (qui les vérifie de nouveau),
    puis ce qui peut partir part."""
    r = lancer(projet, "parallelisme", {"agents_locaux_max": demande.get("agents_locaux_max"),
                                        "agents_cloud_max": demande.get("agents_cloud_max")})
    locaux, nuage = r["agents_locaux_max"], r["agents_cloud_max"]
    equipe = []
    if r.get("crees"):
        equipe.append(f"{len(r['crees'])} {'agents ajoutés' if len(r['crees']) > 1 else 'agent ajouté'}")
    if r.get("retires"):
        equipe.append(f"{len(r['retires'])} {'agents retirés' if len(r['retires']) > 1 else 'agent retiré'}")
    if r.get("retraits_prevus"):
        equipe.append(f"{len(r['retraits_prevus'])} {'agents partiront' if len(r['retraits_prevus']) > 1 else 'agent partira'}"
                      f" à la fin de {'leur tâche' if len(r['retraits_prevus']) > 1 else 'sa tâche'}")
    _terminer(projet, {"demande": demande["id"]},
              f"C'est noté : au plus {locaux} {'agents locaux' if locaux > 1 else 'agent local'} et {nuage} "
              f"{'agents cloud' if nuage > 1 else 'agent cloud'} travaillent en même temps sur ce projet."
              + (f" Équipe : {', '.join(equipe)}." if equipe else ""))
    return _demarrer_en_attente(projet, etat, None)


def _sur_recruter(projet, demande, etat):
    """Des agents recrutés depuis « Parallélisme du projet » (manuel ou répartition automatique confirmée) : les fiches
    sont écrites par l'outil, qui vérifie de nouveau rôles, modèles, dépôt GitHub et places ; puis ce qui peut partir
    part (un agent cloud prend une tâche au départ suivant : le moteur lance sa session)."""
    r = lancer(projet, "recruter", {"mode": demande.get("mode"), "agents": demande.get("agents"),
                                    **({"lieu": demande["lieu"]} if "lieu" in demande else {})})
    noms = ", ".join(f"{a['prenom']} ({a['role']}, {a['modele']}, {a['lieu']})" for a in r["agents"])
    cloud = any(a["lieu"] == "cloud" for a in r["agents"])
    _terminer(projet, {"demande": demande["id"]},
              f"Recruté{'s' if len(r['agents']) > 1 else ''} : {noms}."
              + (" Le moteur lancera la session cloud au départ de sa première tâche." if cloud else ""))
    projet._cloud_raison = (None, 0.0)       # le dépôt a pu changer : relu au prochain choix d'agent
    return _demarrer_en_attente(projet, etat, None)


def _sur_depot_git(projet, demande, etat):
    """Le clic « Créer le dépôt Git » : dépôt local si besoin, dépôt GitHub privé et poussée (`lancer depot`)."""
    r = lancer(projet, "depot", {"action": "creer", "confirme": True})
    _terminer(projet, {"demande": demande["id"]}, r["texte"])
    projet._cloud_raison = (None, 0.0)
    return []


_SUR = {"fonctionnalite": _sur_fonctionnalite, "parallelisme": _sur_parallelisme, "recruter": _sur_recruter,
        "depot_git": _sur_depot_git, "message": _sur_message, "cahier": _sur_cahier, "methode": _sur_methode,
        "lecon": _sur_lecon, "genre": _sur_genre, "organisation": _sur_organisation,
        "genre_fonctionnalite": _sur_genre_fonctionnalite, "environnement": _sur_environnement,
        "installer_outil": _sur_installer_outil,
        "elargir_genre": _sur_elargir_genre,
        "session_cloud": _sur_session_cloud, "retour": _sur_retour, "retour_element": _sur_retour_element,
        "deplacer": _sur_deplacer, "bouton": _sur_bouton, "partenaire_regle": _sur_partenaires,
        "partenaire_inscrit": _sur_partenaires,
        "partenaires_actualiser": _sur_partenaires, "valider_etape": _sur_valider_etape, "partenaires_maj": _sur_partenaires, "challenge": _sur_challenge,
        "regle_projet": _sur_regle_projet}


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
    fiche = next((a for a in court["agents"] if a["cle"] == agent), {})
    # Le cadrage tourne sur le modèle de la fiche de son agent. La première analyse du besoin ne monte plus au-dessus
    # d'une fiche Haiku : le modèle de la fiche est un plafond, jamais dépassé (conception 2026-11-12-modele-par-tache).
    montee = None
    if tache is None:
        tid = lancer(projet, "tache", {"titre": f"Cadrage : {f['nom']}", "fonctionnalite": fid,
                                       "role": fiche.get("role") or (_role_cadrage(projet, fid) if fiche
                                                                     else ROLE_CADRAGE),
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
    """L'élément du prototype : la mémoire du moteur, sinon (moteur redémarré) la dernière tâche de prototype de la
    fonctionnalité, faite comprise (l'état court ne montre que les tâches ouvertes)."""
    e = _m(etat, "prototype").get(f["id"])
    if e is None:
        detail = lancer(projet, "detail", {"fonctionnalite": f["id"], "taches": True})
        t = next((t for t in reversed(detail.get("taches") or []) if str(t.get("etape")) == "prototype"
                  and t.get("element")), None)
        if t:
            nom = ((detail.get("elements") or {}).get(t["element"]) or {}).get("nom") or t["element"]
            e = {"id": t["element"], "nom": nom}
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


def _reponse_de_l_agent_en_route(projet, fid):
    """Une réponse de l'agent aux questions de l'utilisateur (`<tache>.reponse`, détachée) est en route pour `fid`."""
    try:
        for f in sorted(detache.dossier(projet.factory.parent).glob("*.json")):
            if f.name.endswith(".questions.json"):
                continue
            try:
                info = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(info, dict) and info.get("genre") == "reponse" and info.get("fonctionnalite") == fid:
                return True
    except OSError:
        pass
    return False


MARQUE_REPRISE = "Reprise du message"


def _rejouer_le_retour(projet, etat, fid):
    """Le garde-fou du prototype : le dernier mot de la discussion est celui de l'utilisateur, et rien ne le traite (ni
    demande en cours, ni tâche ouverte, ni agent au travail ou en train de répondre, ni décision) : sa réponse s'est
    perdue (moteur redémarré, relance refusée). Elle est rejouée, une fois (la tâche de reprise porte le numéro du message,
    ce qui tient après un redémarrage) ; si l'agent n'a rien répondu après cela, c'est dit dans la discussion."""
    f = _fonc(projet, fid)
    discussion = f.get("discussion") or []
    if not discussion or discussion[-1]["auteur"] != "utilisateur" or f.get("decisions"):
        return []
    if any(d.get("fonctionnalite") == fid for d in lancer(projet, "demandes")["demandes"]):
        return []
    siennes = [t for t in _etat(projet)["taches"] if t.get("fonctionnalite") == fid]
    if any(t["colonne"] != "fait" or t["id"] in etat["en_cours"] for t in siennes)             or _reponse_de_l_agent_en_route(projet, fid):
        return []
    message = discussion[-1]
    marque = f"{MARQUE_REPRISE} {message['id']} "
    toutes = lancer(projet, "detail", {"fonctionnalite": fid, "taches": True}).get("taches") or []
    if any(marque in j["texte"] for t in toutes if str(t.get("etape")) == "prototype"
           for j in _tache(projet, t["id"]).get("journal") or []):
        _dire(projet, fid, "Votre dernier message a été redonné à l'agent du prototype, mais il n'a pas répondu : écrivez-moi "
                           "de nouveau, ou demandez un retour sur sa dernière tâche.")
        return []
    if _element_du_prototype(projet, etat, f) is None:
        _dire(projet, fid, "Je ne sais pas quel élément sert de prototype : votre dernier message n'a pas pu être donné à "
                           "l'agent. Dites-moi l'élément concerné.")
        return []
    texte = str(message.get("texte") or "").strip() or "(message sans texte)"
    return _retoucher_prototype(projet, etat, fid, f"{marque}de l'utilisateur, resté sans suite :\n{texte}")


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
    if REFUSE in texte:       # « … → Je refuse » suivi d'une consigne : l'agent reprend sans l'action refusée
        consigne = texte.split(REFUSE, 1)[1].strip(" \t\n:—–-")
        actions = _reprise_apres_accord(projet, etat, tid, f["id"], accord["quoi"], False, consigne)
        _terminer(projet, {"demande": demande["id"]}, "C'est noté : l'agent reprend sa tâche sans cette action.")
        return actions
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
    # (la session cloud à créer à la main n'en est pas une : le moteur réessaie lui-même de la créer)
    attendues = {d.get("tache") for d in court.get("decisions") or []
                 if d.get("tache") and d.get("genre") != "session_cloud"} \
        | {a.get("tache") for a in _m(etat, "accords").values() if isinstance(a, dict)}
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
        # Une étape du flux déjà commencée, ni active ni bloquée, ni suivie par le moteur : débloquée (à la main, une
        # session cloud inscrite) ou laissée par un moteur relancé ; elle repart aussi, sinon elle ne repartirait jamais.
        # Jamais une tâche qui attend une décision (un accord, un outil…) : elle repart à la réponse du Directeur.
        reprise = bool(t.get("debut")) and etape.startswith(ETAPES_DE_FLUX) and t["id"] not in attendues
        if explicite or reprise or (not t.get("debut") and (etape.startswith(ETAPES_DE_FLUX)
                                                            or etape in ETAPES_DU_MOTEUR)):
            attente.append(t)
    attente.sort(key=lambda t: (t.get("etape") != "correction", t["id"]))
    return attente


# --- Les places d'agents et les validations-barrières (conception 2026-11-12-parallelisme-design.md).

def _places(projet, court, fac=None):
    """Les places du projet : `{locaux, cloud}` libres (le maximum moins les tâches actives tenues par un agent de ce
    lieu) et `total` (les deux maximums). Les places cloud effectives : voir `depart.places_cloud`."""
    fac = fac or _factory(projet)
    lieux = {a["cle"]: a["lieu"] for a in court["agents"]}
    actifs = [lieux[t["agent"]] for t in court["taches"] if t["active"] and t.get("agent") in lieux]
    cloud_max = dep.places_cloud(fac.get("agents_cloud_max"), projet.cloud_max, "cloud" in lieux.values())
    return {"locaux": max(0, fac["agents_locaux_max"] - actifs.count("local")),
            "cloud": max(0, cloud_max - actifs.count("cloud")), "total": fac["agents_locaux_max"] + cloud_max}


def _concerne(element, etape_id):
    """Vrai si l'étape de validation concerne l'élément : `validations` du découpage, absent = toutes (comportement
    d'avant)."""
    v = (element or {}).get("validations")
    return True if not isinstance(v, list) else etape_id in v


def _rang_de_tache(t, rangs):
    """Le rang (dans la production) d'une tâche de flux ou de validation, `None` pour une autre tâche."""
    etape = str(t.get("etape") or "")
    for prefixe in (ETAPES_DE_FLUX, ETAPES_DE_VALIDATION):
        if etape.startswith(prefixe):
            return rangs.get(etape[len(prefixe):], len(rangs))     # une étape disparue du workflow : après tout
    return None


def _barrieres(projet, court, fac=None):
    """Par fonctionnalité en série dont le workflow a des validations : `{fid: {"production", "ouvertes": {rang: nom},
    "premiere": rang | None}}` (les barrières pas encore franchies) et l'ensemble `retenues` des tâches de flux
    situées après l'une d'elles. Une barrière (étape de validation de rang k) est franchie quand aucun élément
    qu'elle concerne n'est encore dans la file, avant k ou à k (en attente du Directeur) ; un élément bloqué ne retient
    rien. Lu dans le suivi : juste après un redémarrage du moteur."""
    fac = fac or _factory(projet)
    sortie, retenues = {}, set()
    for fc in court["fonctionnalites"]:
        if fc["etape"] != "serie":
            continue
        w = wf.de_la_fonctionnalite(fac, fc)
        flux = w["flux"] if w else []
        production = [s for s in flux if s.get("role") != ROLE_RELECTURE] or flux
        validations = [k for k, s in enumerate(production) if wf.est_validation(s)]
        if not validations:
            continue
        f = _fonc(projet, fc["id"])
        rangs = {s["id"]: k for k, s in enumerate(production)}
        connus = dict(f.get("elements") or {})
        dans_la_file = {q["id"]: q for q in f.get("file") or []}
        taches = [t for t in court["taches"] if t.get("fonctionnalite") == fc["id"]]
        position = {}       # élément -> rang de sa dernière tâche de flux ou de validation (None : bloqué ou sans rang)
        for t in taches:
            r = _rang_de_tache(t, rangs)
            if t.get("element") and r is not None:
                attend = str(t.get("etape")).startswith(ETAPES_DE_VALIDATION) and t["colonne"] != "fait"
                position[t["element"]] = (r, attend, bool(t.get("bloquee")) and t["colonne"] != "fait")
        ouvertes = {}
        for k in validations:
            sid = production[k]["id"]
            for eid in set(connus) | set(dans_la_file):
                element = dans_la_file.get(eid) or connus.get(eid)
                if not _concerne(element, sid):
                    continue
                if eid in dans_la_file:
                    ouvertes[k] = production[k]["nom"]
                    break
                p = position.get(eid)
                if p is None or p[2]:        # le prototype (sans tâche de flux), ou bloqué : ne retient rien
                    continue
                r, attend, _ = p
                if r < k or (r == k and attend):
                    ouvertes[k] = production[k]["nom"]
                    break
        premiere = min(ouvertes) if ouvertes else None
        sortie[fc["id"]] = {"production": production, "ouvertes": ouvertes, "premiere": premiere, "rangs": rangs}
        if premiere is not None:
            for t in taches:
                r = _rang_de_tache(t, rangs)
                if r is not None and str(t.get("etape")).startswith(ETAPES_DE_FLUX) and r > premiere:
                    retenues.add(t["id"])
    return sortie, retenues


def _avant_une_validation(t, barrieres):
    """Vrai pour une tâche qui mène à une validation du Directeur pas encore faite : le cadrage (le cahier), le
    prototype (la méthode), une étape de flux avant une barrière pas encore franchie."""
    etape = str(t.get("etape") or "")
    if etape in ("cadrage", "prototype"):
        return True
    b = barrieres.get(t.get("fonctionnalite"))
    if not b or b["premiere"] is None:
        return False
    r = _rang_de_tache(t, b["rangs"])
    return r is not None and r < b["premiere"]


def _amont_pret(projet, etat, tache, court=None, barrieres=None, cache=None):
    """Vrai seulement si rien n'attend en amont de la tâche : ses dépendances (`depend_de`) sont faites ; pour une étape
    du flux d'un élément, les étapes d'avant de cet élément sont faites (une tâche bloquée ne retient rien, comme dans
    `_barrieres`), aucune validation du Directeur (tâche `validation:*` ou décision `valider_etape`) n'est ouverte en
    amont, et les barrières de la fonctionnalité sont levées. Appelé par tous les chemins de départ (lot, `a_lancer`,
    retour, reprise après redémarrage, session cloud) : une place libre ne suffit pas. `barrieres` : ce que rend
    `_barrieres` (relu sinon) ; `cache` : un dict gardé d'un appel à l'autre (les rangs du workflow par fonctionnalité)."""
    court = court if court is not None else _etat(projet)
    sortie, retenues = barrieres if barrieres is not None else _barrieres(projet, court)
    if tache["id"] in retenues:
        return False
    ouvertes = {t["id"] for t in court["taches"]}      # l'état court ne porte que les tâches pas encore faites
    if any(d in ouvertes and d != tache["id"] for d in tache.get("depend_de") or []):
        return False
    fid, eid = tache.get("fonctionnalite"), tache.get("element")
    if not (str(tache.get("etape") or "").startswith(ETAPES_DE_FLUX) and fid and eid):
        return True
    cache = cache if cache is not None else {}
    if fid not in cache:
        cache[fid] = (sortie.get(fid) or {}).get("rangs") or {s["id"]: k for k, s in enumerate(_production(projet, fid))}
    rangs = cache[fid]
    rang = _rang_de_tache(tache, rangs)
    for t in court["taches"]:
        if (t["id"] == tache["id"] or t.get("fonctionnalite") != fid or t.get("element") != eid
                or t["colonne"] == "fait" or t.get("bloquee")):
            continue
        r = _rang_de_tache(t, rangs)
        if r is not None and r < rang:
            return False      # une étape d'avant de l'élément, ou sa validation, n'est pas faite
    for d in court.get("decisions") or []:
        if (d.get("genre") == GENRE_VALIDATION and d.get("fonctionnalite") == fid
                and (d.get("element") or {}).get("id") == eid and rangs.get(d.get("etape"), len(rangs)) < rang):
            return False      # le Directeur n'a pas encore validé une étape d'avant
    return True


def _polyvalent(agent):
    """Vrai pour un agent polyvalent (sa fiche n'a pas de rôle) : il prend n'importe quelle tâche."""
    return isinstance(agent, dict) and not agent.get("role")


def _metier(projet, role):
    """Le métier (`briefs/<role>.md`, voir `orchestrateur.metiers`), ou `None` (pas de brief, brief illisible)."""
    if not isinstance(role, str) or not dep._ROLE_SUR.match(role):
        return None
    try:
        return metiers.lire_metier(Path(_factory(projet)["fiches"]) / "briefs", role)
    except (metiers.MetierInvalide, OSError):
        return None


def _lieu_reserve(projet, court, role):
    """`local` ou `cloud` quand le métier du rôle impose son lieu (`Lieu :` de son brief), dans un projet qui a des agents
    polyvalents ; `None` sinon (un projet à l'ancienne choisit comme avant)."""
    if not any(_polyvalent(a) for a in court["agents"]):
        return None
    m = _metier(projet, role)
    return m["lieu"] if m and m["lieu"] in ("local", "cloud") else None


def _validation_en_attente(projet, court):
    """Le nom de la première validation qui attend le Directeur (étape de validation d'un élément, cahier, méthode),
    ou `None`."""
    for d in court.get("decisions") or []:
        if d.get("genre") == GENRE_VALIDATION:
            etape = next((s for s in _production(projet, d.get("fonctionnalite")) if s["id"] == d.get("etape")), None)
            return (etape or {}).get("nom") or "Validation du Directeur"
    for f in court["fonctionnalites"]:
        genres = {d["genre"] for d in f.get("decisions") or []}
        if "valider_cahier" in genres:
            return f"Validation du cahier des charges de « {f['nom']} »"
        if "valider_methode" in genres:
            return f"Validation de la méthode de « {f['nom']} »"
    return None


def texte_des_places_libres(n, validation):
    """« 2 places libres : en attente de votre validation « … » »."""
    s = "s" if n > 1 else ""
    return f"{n} place{s} libre{s} : en attente de votre validation « {validation} »"


def _noter_les_places_libres(projet, etat):
    """Des places libres sans tâche permise alors qu'une validation attend le Directeur : noté pour le bureau
    (`etat["attente_validation"]`), refait à chaque passage."""
    court = _etat(projet)
    validation = _validation_en_attente(projet, court)
    if validation is None:
        return
    fac = _factory(projet)
    barrieres, cache = _barrieres(projet, court, fac), {}
    pretes = [t for t in _attente(court, None, etat) if t.get("etape") != ETAPE_INSTALLATION
              and _amont_pret(projet, etat, t, court, barrieres, cache)]
    if pretes:
        return
    places = _places(projet, court, fac)
    libres = (places["locaux"] if projet.charge()["feu_vert"] else 0) + places["cloud"]
    if libres > 0:
        etat["attente_validation"] = {"texte": texte_des_places_libres(libres, validation), "places": libres,
                                      "validation": validation}


def _demarrer_en_attente(projet, etat, fid):
    """Lance ce qui peut l'être : aucune étape en pause, aucune tâche après une validation pas encore faite, une place
    libre (locale sous la charge, ou cloud), un agent libre ; les tâches qui mènent à une validation d'abord. Rend les
    actions agent."""
    court = _etat(projet)
    if any(a.get("retrait_prevu") for a in court["agents"]):
        # des places baissées pendant qu'un agent travaillait : il est retiré dès que sa tâche est finie
        if lancer(projet, "equipe")["retires"]:
            court = _etat(projet)
    if court["pause"] or projet.pause_globale:      # la pause d'une installation prioritaire : aucun agent neuf ne part
        return []
    attente = _attente(court, fid, etat)
    if projet.installations_a_part:      # le moteur lance lui-même les installations, avant tout le reste
        attente = [t for t in attente if t.get("etape") != ETAPE_INSTALLATION]
    if not attente:
        return []
    panne = _panne_en_cours(etat)
    if panne:      # le service Claude est indisponible : rien ne part avant le prochain essai (dit au bureau)
        etat["attente_charge"] = {"texte": panne["texte"], "taches": [t["id"] for t in attente], "charge": None,
                                  "plafond": None}
        return []
    fac = _factory(projet)
    barrieres, retenues = _barrieres(projet, court, fac)
    cache = {}
    attente = [t for t in attente if _amont_pret(projet, etat, t, court, (barrieres, retenues), cache)]
    if not attente:
        return []
    places = _places(projet, court, fac)
    mesure = projet.charge()
    if not mesure["feu_vert"]:
        etat["attente_charge"] = {"texte": texte_d_attente_de_charge(mesure), "charge": mesure["charge"],
                                  "plafond": mesure["plafond"], "taches": [t["id"] for t in attente]}
        places["locaux"] = 0        # un agent cloud ne compte pas dans la charge du poste
        if not places["cloud"]:
            return []
    actions, solos, en_flux = [], [], []
    for t in attente:
        # une étape déjà commencée (reprise) n'est jamais remise en lot : elle part seule
        (en_flux if str(t.get("etape")).startswith(ETAPES_DE_FLUX) and t["id"] not in etat["a_lancer"]
         and not t.get("debut") else solos).append(t)
    lots = []
    if en_flux:
        r = lancer(projet, "lots", {"taches": [t["id"] for t in en_flux]})
        lots = [{"ids": x["taches"], "modele": x["modele"], "lot": x["lot"]} for x in r["lots"]]
    par_id = {t["id"]: t for t in attente}
    for t in solos:      # une correction, un retour… : le modèle de l'étape de son rôle ; un cadrage : celui de la fiche
        lots.append({"ids": [t["id"]], "modele": _modele_necessaire(projet, court, t), "lot": None})
    # une tâche qui demande Fable part seule : l'accord du Directeur se donne tâche par tâche
    lots = [x for lot in lots for x in ([{"ids": [i], "modele": lot["modele"], "lot": None} for i in lot["ids"]]
                                        if len(lot["ids"]) > 1 and mn.rang(lot["modele"]) >= mn.rang(mn.FABLE)
                                        else [lot])]
    polyvalents = any(_polyvalent(a) for a in court["agents"])
    # les tâches qui mènent à une validation du Directeur d'abord (l'ordre d'avant, sinon)
    lots.sort(key=lambda lot: min(0 if _avant_une_validation(par_id[i], barrieres) else 1 for i in lot["ids"]))
    for lot in lots:
        if not places["locaux"] and not places["cloud"]:
            break
        premiere = par_id[lot["ids"][0]]
        # le lieu que les métiers du lot imposent (projet polyvalent seulement : `Lieu : local` d'un brief)
        reserves = {_lieu_reserve(projet, court, par_id[i].get("role")) for i in lot["ids"]}
        local_ok = places["locaux"] > 0 and "cloud" not in reserves
        cloud_ok = places["cloud"] > 0 and "local" not in reserves
        if polyvalents and mn.rang(_modele_voulu(projet, court, premiere, lot["modele"])) >= mn.rang(mn.FABLE):
            accord = premiere.get("fable_accordee")
            if accord is None:       # la décision au bureau de direction, avant tout départ ; la tâche attend
                _demander_fable(projet, court, premiere)
                continue
            if accord is True:       # le cloud ne fait jamais tourner Fable : une place locale
                cloud_ok = False
        voulu = premiere.get("agent") if premiere.get("etape") == "cadrage" or premiere["id"] in etat["a_lancer"] \
            else None
        ancien = next((a for a in court["agents"] if a["cle"] == premiere.get("agent")), None)
        if voulu is None and ancien is not None and _polyvalent(ancien) and premiere.get("debut"):
            voulu = ancien["cle"]      # une tâche reprise revient de préférence au même agent polyvalent
        agent = None
        if voulu is not None:
            libre = next((a for a in court["agents"] if a["cle"] == voulu), {})
            if libre.get("libre", False) and (cloud_ok if libre.get("lieu") == "cloud" else local_ok):
                agent = voulu
            elif not (libre and _polyvalent(libre) and premiere.get("etape") != "cadrage"):
                continue       # un spécialiste à l'ancienne, ou l'agent attitré du cadrage : la tâche l'attend
        if agent is None:      # (un agent polyvalent occupé : n'importe quel autre agent libre la reprend)
            agent = _choisir_agent(projet, etat, court, premiere, lot["modele"], local_ok=local_ok, cloud_ok=cloud_ok)
            if agent is None:
                continue
        lieu = next((a["lieu"] for a in court["agents"] if a["cle"] == agent), "local")
        places["cloud" if lieu == "cloud" else "locaux"] -= 1
        actions.append(_partir(projet, etat, court, agent, lot["ids"], lot["lot"], par_id, modele_voulu=lot["modele"]))
        court = _etat(projet)    # l'agent est pris : le prochain lot voit l'état à jour
    return actions


def texte_d_attente_de_charge(mesure):
    """« En attente : charge 90 % (plafond 70 %) » : ce que le bureau montre d'une tâche prête que la charge retient."""
    if mesure.get("charge") is None or mesure.get("plafond") is None:
        return "En attente : la charge de l'ordinateur dépasse le plafond du projet"
    return f"En attente : charge {mesure['charge']} % (plafond {mesure['plafond']} %)"


# --- Les installations d'outils : prioritaires sur tout le bureau (le moteur les lance, voir `boucle.Moteur`).

def installations_pretes(projet, etat):
    """Les tâches d'installation du projet prêtes à partir (même règle que le départ ordinaire : ni active, ni faite, ni
    bloquée, pas déjà prise), sans l'attente d'un agent libre. Rien si le projet est en pause à la main (le Directeur
    l'a voulu : son installation attend la reprise, et ne retient pas les autres projets) ou s'il n'a aucun agent
    d'installation (rien ne pourrait partir : la pause ne durerait pas moins que toujours)."""
    court = _etat(projet)
    if court["pause"] or not any(a["role"] == ROLE_ENVIRONNEMENT or _polyvalent(a) for a in court["agents"]):
        return []
    return [t for t in _attente(court, None, etat) if t.get("etape") == ETAPE_INSTALLATION]


def installations_en_cours(projet, etat):
    """Les tâches d'installation du projet dont l'agent travaille (celles que ce moteur a lancées)."""
    en_cours = _m(etat, "en_cours")
    return [t for t in _etat(projet)["taches"] if t.get("etape") == ETAPE_INSTALLATION and t["id"] in en_cours]


def outils_de_la_tache(projet, tid):
    """Les noms des outils qu'une tâche d'installation doit installer (lus dans ses consignes)."""
    return environnement.outils_du_journal([j["texte"] for j in _tache(projet, tid).get("journal") or []])


def demarrer_installation(projet, etat, tid):
    """Lance la tâche d'installation `tid` tout de suite, sans condition de charge ni de plafond. Rend les actions
    agent ([] si elle n'est plus prête ou si l'agent d'installation n'est pas libre)."""
    court = _etat(projet)
    t = next((x for x in installations_pretes(projet, etat) if x["id"] == tid), None)
    if t is None or not _amont_pret(projet, etat, t, court):
        return []
    if tid in _m(etat, "a_lancer", list):
        agent = t.get("agent")
        if not next((a for a in court["agents"] if a["cle"] == agent), {}).get("libre", False):
            return []
    else:
        agent = _choisir_agent(projet, etat, court, t, None)
        if agent is None:
            return []
    return [_partir(projet, etat, court, agent, [tid], None, {tid: t})]


def _choisir_agent(projet, etat, court, tache, modele, local_ok=True, cloud_ok=None):
    """L'agent qui prend la tâche de modèle nécessaire `modele` : un agent local libre dont le plafond (le modèle de sa
    fiche) suffit, le plus petit d'abord (s'il reste une place locale) ; sinon, en renfort, un agent cloud libre au
    plafond suffisant (s'il reste une place cloud, voir `agents_cloud_max`, et si le projet est sur GitHub) ; sinon, si
    le cloud est impossible, l'agent local équivalent (un autre du même rôle, la tâche ramenée à son plafond), en le
    disant au bureau. `cloud_ok` absent : les places cloud du projet sont recomptées."""
    role = tache.get("role")
    if local_ok:
        local = lancer(projet, "agent-libre", {"role": role, "lieu": "local", **({"modele": modele} if modele else {})})
        if local["agent"]:
            return local["agent"]
    clouds = {a["cle"] for a in court["agents"] if a["lieu"] == "cloud"}
    # Le modèle de la fiche est un plafond (local comme cloud) : l'agent prend une tâche de ce modèle ou d'un modèle
    # moindre, et la fait tourner sur le modèle de la tâche (voir `_partir`) ; jamais une tâche d'un modèle au-dessus.
    # Le plus petit plafond suffisant d'abord.
    candidats = [a for a in mn.possibles(court["agents"], role, modele) if a["lieu"] == "cloud" and a["libre"]]
    if not clouds or not candidats or _lieu_reserve(projet, court, role) == "local":
        return None
    raison = projet.cloud_raison()
    if raison is None:
        if cloud_ok is None:
            cloud_ok = _places(projet, court)["cloud"] > 0
        return candidats[0]["cle"] if cloud_ok else None
    if not local_ok:
        return None
    equivalent = lancer(projet, "agent-libre", {"role": role, "lieu": "local"})["agent"]
    dits = _m(etat, "cloud_dit", set)
    if equivalent and (tache.get("fonctionnalite"), role) not in dits and tache.get("fonctionnalite"):
        dits.add((tache["fonctionnalite"], role))
        _dire(projet, tache["fonctionnalite"], f"Les agents cloud ne sont pas disponibles ({raison}) : "
                                               f"l'agent local {equivalent} prend la tâche « {tache['titre']} ».")
    return equivalent


ORDRE_DES_MODELES = mn.ORDRE
rang_modele = mn.rang     # Haiku < Sonnet < Opus < Fable ; un nom inconnu compte comme Sonnet


def _modele_necessaire(projet, court, t):
    """Le modèle nécessaire de la tâche (`modele_necessaire.de_la_tache`, montée comprise), ou `None` : celui de la
    fiche de l'agent (cadrage, prototype, installation)."""
    m = mn.de_la_tache(_factory(projet), t, court["agents"], court.get("fonctionnalites") or [])
    return m["modele"] if m else None


def _modele_voulu(projet, court, t, modele_voulu=None):
    """Le modèle que demande la tâche pour un agent polyvalent, sans plafond : sa montée, sinon le modèle voulu (celui du
    lot), sinon son modèle nécessaire (étape, nature), sinon le modèle par défaut de son métier, sinon Sonnet. Peut valoir
    Fable : une demande, que `_modele_de_depart` ne laisse partir qu'avec l'accord du Directeur."""
    voulu = ((t.get("montee") or {}).get("a") or modele_voulu or _modele_necessaire(projet, court, t)
             or (_metier(projet, t.get("role")) or {}).get("modele") or "Sonnet")
    return mn.nom(voulu)


GENRE_FABLE = "fable_tache"           # la décision de projet : « cette tâche demande Fable : l'autoriser ? »
AUTORISER_FABLE, REFUSER_FABLE = "autoriser", "refuser"


def _demander_fable(projet, court, t):
    """Pose (une fois par tâche) la décision `fable_tache` au bureau de direction, avec la raison (la justification de
    l'étape ou la montée). La tâche attend la réponse ; les autres continuent."""
    if any(d.get("genre") == GENRE_FABLE and d.get("tache") == t["id"] for d in court.get("decisions") or []):
        return
    m = mn.de_la_tache(_factory(projet), t, court["agents"], court.get("fonctionnalites") or [])
    raison = (m or {}).get("raison") or "le modèle demandé pour cette tâche"
    lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": GENRE_FABLE, "tache": t["id"],
                                "raison": raison[:300],
                                "texte": f"La tâche « {t['titre']} » demande Fable : l'autoriser ? Sans votre accord, "
                                         "elle part sur Opus."})


def _sur_fable_tache(projet, demande, etat):
    """La réponse du Directeur à « cette tâche demande Fable » : `autoriser` (la tâche part sur Fable, accord noté pour
    elle seule) ou `refuser` (elle part sur Opus)."""
    d = next((x for x in _etat(projet)["decisions"] if x["id"] == demande.get("decision") and x["genre"] == GENRE_FABLE),
             None)
    if d is None:
        raise Refus("cette question n'existe plus")
    verdict = demande.get("verdict")
    if verdict not in (AUTORISER_FABLE, REFUSER_FABLE):
        raise Refus(f"réponse inconnue : {verdict}")
    accord = verdict == AUTORISER_FABLE
    t = _tache(projet, d["tache"])
    lancer(projet, "tache", {"id": t["id"], "fable_accordee": accord, "journal": [
        "Fable accordé par le Directeur pour cette tâche." if accord else "Fable refusé par le Directeur : Opus."]})
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    _terminer(projet, {"demande": demande.get("id")}, f"« {t['titre']} » part sur Fable." if accord
              else f"« {t['titre']} » part sur Opus.")
    return _demarrer_en_attente(projet, etat, t.get("fonctionnalite"))


_SUR[GENRE_FABLE] = _sur_fable_tache


def _modele_de_depart(projet, court, agent, t, modele_voulu=None):
    """Le modèle sur lequel l'agent fait tourner la tâche `t` : sa montée, sinon le modèle voulu (celui du lot), sinon
    son modèle nécessaire, sinon celui de la fiche ; jamais au-dessus du modèle de la fiche, qui est le plafond de
    l'agent, local comme cloud."""
    fiche = next(a for a in court["agents"] if a["cle"] == agent)
    if _polyvalent(fiche):      # un agent polyvalent n'a pas de plafond : le modèle de la tâche
        voulu = _modele_voulu(projet, court, t, modele_voulu)
        if mn.rang(voulu) >= mn.rang(mn.FABLE) and t.get("fable_accordee") is not True:
            return "Opus"       # jamais Fable sans l'accord du Directeur pour cette tâche
        return voulu
    voulu = ((t.get("montee") or {}).get("a") or modele_voulu or _modele_necessaire(projet, court, t)
             or fiche["modele"])
    return mn.plafonne(voulu, fiche["modele"])


def _partir(projet, etat, court, agent, ids, lot, par_id, modele_voulu=None):
    # Une tâche tourne sur le modèle qu'elle demande (celui du lot, ou sa montée), jamais au-dessus du plafond de l'agent.
    modele = _modele_de_depart(projet, court, agent, par_id[ids[0]], modele_voulu)
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
    if (_m(etat, "cloud").get(ids[0]) or {}).get("agent") not in (None, agent):
        etat["cloud"].pop(ids[0])      # reprise par un autre agent : la session de l'ancien n'est pas la sienne
    etat["departs"][ids[0]] = {"agent": agent, "taches": list(ids), "matiere": matiere, "modele": modele, "lot": lot,
                               "suite": supp}
    if mn.rang(modele) >= mn.rang(mn.FABLE) and par_id[ids[0]].get("fable_accordee") is True:
        etat["departs"][ids[0]]["fable_accorde"] = True     # l'accord du Directeur pour cette tâche (voir `boucle`)
    etat["en_cours"].add(ids[0])
    return a_agent(agent, ids, matiere)


CONSIGNE_AVANT_VALIDATION = (
    "Après toi, le Directeur valide cet élément dans sa fenêtre de validation. Donne-lui de quoi vérifier : des "
    "captures légendées, le livrable lui-même dans `fichiers` (apk, zip, pdf, exe…) ou, pour un site, "
    '`acces`: {"url": "http://127.0.0.1:<port>/", "description": "…"} (laisse le serveur tourner). Rends aussi '
    f'`points_a_verifier` : 3 à {rel.MAX_POINTS} phrases de {rel.MAX_POINT} caractères au plus, chacune vérifiable '
    "par lui en regardant ou en essayant (pas de jargon), tirées du cahier. Dans un lot : dans le compte rendu de "
    "l'élément (`comptes_rendus`). "
    "Dis aussi, en trois champs courts, ce que le Directeur doit juger (sans eux, la demande n'est pas posée) : "
    f"`doit_marcher` (1 à 3 phrases, {rel.MAX_DOIT_MARCHER} caractères au plus : ce qui doit fonctionner pour valider, "
    'ex. « l\'apk s\'installe, s\'ouvre en portrait et affiche le menu »), '
    f"`pas_encore` ({rel.MAX_PAS_ENCORE} caractères au plus : ce qui n'est pas encore attendu à ce stade, ex. « le jeu "
    "ne répond pas encore : combat, carte et magasin viennent avec les éléments suivants » ; vide si tout est attendu) "
    f"et `conclusion` (une phrase, {rel.MAX_CONCLUSION} caractères au plus, ex. « Validez si l'application s'ouvre "
    "correctement, même si rien n'est encore jouable. »). Ne lui fais pas valider ce qui viendra plus tard. "
    "Déclare aussi la `nature` de ce que tu lui fais valider et ne joins que les preuves qui conviennent : "
    "`en_jeu` (à essayer dans le livrable : apk, exe, site) → le livrable (ou le lien d'accès) ET `mode_operatoire`, "
    f"{rel.MIN_ETAPES_MODE} à {rel.MAX_ETAPES_MODE} étapes courtes ({rel.MAX_ETAPE_MODE} caractères au plus : "
    "installer, lancer, quoi faire, quoi observer) ; `visuel` (images, sprites) → les images légendées (et les sons "
    "s'il y en a), jamais l'apk ; `son` (bruitages, musique) → les fichiers audio mp3, ogg, wav ou flac dans `fichiers`, "
    "jamais l'apk ; `mecanique` (règles, équilibrage) → un document explicatif md ou pdf, et si utile des schémas, jamais "
    "l'apk (sauf si déjà jouable : alors `en_jeu`) ; `autre` → de quoi juger, expliqué. Le Directeur n'installe un apk "
    "que pour ce qui est en jeu ; tes points à vérifier suivent cette nature. Ne teste jamais l'apk sur un appareil "
    "physique de l'utilisateur : c'est lui qui l'installe, par cette fenêtre.")


MODES_DU_CADRAGE = {"direct": "connecté (les agents l'appellent directement)",
                    "inscrit": "inscrit (l'utilisateur fait la génération sur son site, avec le prompt préparé)"}


def _partenaires_au_cadrage(projet):
    """Le cadrage décide si la fonctionnalité utilise un partenaire : les partenaires de l'utilisateur (connectés ou inscrits)
    et la consigne de lui poser la question, puis d'inscrire sa réponse dans le cahier. Vide sans partenaire (rien à demander)."""
    try:
        dispo = lancer(projet, "partenaires", {"action": "disponibles"})["partenaires"]
    except (Refus, OSError, ValueError, KeyError):
        return ""
    if not dispo:
        return ""
    lignes = ["## Partenaires de l'utilisateur", "Il les a connectés ou y a un compte ; propose-les quand un besoin du cahier "
              "(génération 3D, images, voix…) leur correspond :"]
    for p in dispo:
        lignes.append(f"- {p['id']} ({p['nom']}, {p.get('sous_categorie') or p.get('categorie')}) : "
                      + " ; ".join(MODES_DU_CADRAGE[m] for m in p["modes"]))
    lignes.append("Pour chaque partenaire dont un besoin relève, pose la question dans ta série de questions, à choix : "
                  "« Utiliser <Nom> (connecté : appelé directement par les agents) » ou « Utiliser <Nom> (inscrit : vous ferez "
                  "la génération sur son site avec le prompt préparé) » selon ses modes, et « Ne pas utiliser de partenaire ». "
                  'Inscris sa réponse dans le cahier : `"partenaires": [{"id": "<id>", "mode": "direct" | "inscrit" | "aucun"}]`, '
                  "un par partenaire concerné ; les étapes suivantes s'y conforment. Aucun besoin ne leur correspond : ne pose "
                  "pas la question et ne mets pas `partenaires`.")
    return "\n".join(lignes)


def _matiere(projet, etat, t):
    """Ce que l'agent doit savoir de la tâche, en plus de son message de départ (la discussion, les retours, l'élément)."""
    etape, fid = str(t.get("etape") or ""), t.get("fonctionnalite")
    f = _fonc(projet, fid) if fid else None
    complet = _tache(projet, t["id"])
    consignes = "\n".join(f"- {j['texte']}" for j in complet.get("journal") or [])
    parties = [f"## Matière de la tâche {t['id']} ({t['titre']})"]
    if etape == "cadrage":
        description = " ".join(str(_factory(projet).get("description") or "").split())
        if description:      # la référence d'une fonctionnalité : la description du projet, plus la demande
            parties += ["Description du projet (la référence du cadrage, avec la demande de l'utilisateur) :", description]
            if est_intention_de_demarrage(_demande_de(f)["texte"]):
                parties.append("La demande ne décrit pas de fonctionnalité, elle demande de démarrer le projet : le "
                               "cadrage porte sur la description du projet.")
        parties += ["Discussion avec l'utilisateur :", _texte_discussion(f, projet=projet),
                    "Réponds-lui par ton rapport : des questions courtes, avec des choix quand c'est possible "
                    "(`message.questions`, `attend: true`). Une question a exactement cette forme : "
                    '`{"texte": "…", "choix": ["…", "…"], "multiple": false}` (`texte` et non `question` ; 2 choix au '
                    "moins ; `multiple: true` quand plusieurs choix vont ensemble). Dès ta première réponse, donne un `nom` court à la "
                    "fonctionnalité. **Une seule série de questions** : dès que l'utilisateur y a répondu, écris le "
                    "cahier des charges sans reposer de questions (ce qui reste ouvert, choisis-le toi-même et dis-le "
                    "dans ton message). Le cahier : une maquette (images PNG ou JPEG que tu fabriques, écrites dans "
                    f"`{_dossier_des_pieces(projet)}/{fid}/`) et la liste des étapes à réaliser, dans l'ordre : "
                    'rends `"cahier": {"maquette": [{"chemin": "…", "legende": "…"}], "etapes": [textes]}` : chaque '
                    "maquette a sa légende, une phrase (160 caractères au plus) qui dit à quoi elle correspond (écran, "
                    "élément, moment du jeu…), affichée sous l'image. Une correction demandée par "
                    "l'utilisateur : refais la maquette et rends le cahier corrigé."]
        partenaires = _partenaires_au_cadrage(projet)
        if partenaires:
            parties.append(partenaires)
    elif etape == "prototype":
        parties += [f"Élément du prototype : {t.get('element')}", "Cahier : " + str((f or {}).get("cahier")),
                    "Discussion récente :", _texte_discussion(f, 8, projet),
                    "Montre tes images dans `message.images` (chacune avec sa légende : "
                    '`{"chemin": "…", "legende": "…"}`), avec `attend: true` pour recueillir le retour de '
                    'l\'utilisateur, toujours par des questions à choix (`message.questions`, par ex. « Le style vous '
                    'convient-il ? » → « Oui, on continue » / « À corriger (précisez) »). Quand la méthode te semble prête, résume-la dans ton message et rends '
                    '`"methode_prete": true`.']
    elif etape.startswith(ETAPES_DE_FLUX):
        methode = (f or {}).get("methode") or {}
        parties += [f"Élément : {t.get('element')}", f"Étape du flux : {etape[len(ETAPES_DE_FLUX):]}",
                    "Méthode validée : " + str(methode.get("chemin") or methode.get("lien") or "(voir ton brief)"),
                    "Registre des contrôles : relis-le avant de rendre l'élément."]
        production = _production(projet, fid)
        rang = next((k for k, x in enumerate(production) if etape == ETAPES_DE_FLUX + x["id"]), None)
        if (rang is not None and rang + 1 < len(production) and wf.est_validation(production[rang + 1])
                and _concerne(((f or {}).get("elements") or {}).get(t.get("element")), production[rang + 1]["id"])):
            parties.append(CONSIGNE_AVANT_VALIDATION)
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


def _dossier_des_pieces(projet):
    """Le dossier `pieces` compté depuis le dossier du projet (là où travaille l'agent), par exemple `.factory/pieces`."""
    try:
        pieces = outil.racines_servies(fa.lire(projet.factory))[2]
    except fa.FactoryInvalide:
        pieces = projet.factory.resolve().parent / "pieces"
    try:
        return pieces.relative_to(projet.dossier.resolve()).as_posix()
    except ValueError:
        return pieces.as_posix()


def _image_rangee(projet, chemin, fid):
    """Une image citée par un agent, rangée là où le bureau la sert : voir `outil.image_rangee`, le point unique (l'outil
    applique la même règle quand l'agent l'appelle lui-même)."""
    try:
        return outil.image_rangee(fa.lire(projet.factory), projet.dossier, chemin, fid)
    except fa.FactoryInvalide:
        return chemin


def _chemins_du_projet(projet, r, fid=None):
    """Le rapport, ses chemins (images du message, maquette du cahier, fichiers) comptés depuis la factory. Les images
    qui n'étaient pas sous une racine d'images sont copiées sous `pieces/<fid>/` (voir `_image_rangee`)."""
    r = dict(r)

    def image(x):    # un chemin, ou {chemin, legende} : la légende reste avec son image
        if isinstance(x, dict):
            return {**x, "chemin": image(x.get("chemin"))}
        return _image_rangee(projet, _chemin_du_projet(projet, x), fid)
    if isinstance(r.get("message"), dict) and isinstance(r["message"].get("images"), list):
        r["message"] = {**r["message"], "images": [image(x) for x in r["message"]["images"]]}
    if isinstance(r.get("cahier"), dict) and isinstance(r["cahier"].get("maquette"), list):
        r["cahier"] = {**r["cahier"], "maquette": [image(x) for x in r["cahier"]["maquette"]]}
    r["fichiers"] = [{**f, "chemin": image(f.get("chemin"))} for f in r.get("fichiers") or []]   # une image est rangée, le reste suit
    if isinstance(r.get("comptes_rendus"), list):
        r["comptes_rendus"] = [{**c, "images": [image(x) for x in c["images"]]} if isinstance(c.get("images"), list)
                               else c for c in r["comptes_rendus"]]
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
    etat.pop("panne", None)      # un agent a rendu son rapport : le service répond de nouveau
    fid, du_lot = None, {}
    for tid in taches:
        t = _tache(projet, tid)
        fid = fid or t.get("fonctionnalite")
        du_lot[tid] = t.get("element")
    if fid:     # le moteur relancé pendant le travail de l'agent : les éléments du lot sont repris avant son rapport
        reprendre_la_serie(projet, etat, fid)
    r = _chemins_du_projet(projet, r, fid)
    r["_du_lot"] = du_lot      # tâche -> élément : le compte rendu de chaque élément est pris à part (`_retenir_le_rapport`)
    liee = _m(etat, "liees").pop(taches[0], None)
    reponse = ((r.get("message") or {}).get("texte")) or "C'est fait."
    if r["statut"] in ("accord_requis", "outil_refuse"):
        return _agent_arrete(projet, etat, execution, depart, r, fid)
    if r["statut"] == "a_faire_chez_partenaire":
        return _chez_partenaire_demande(projet, etat, execution, depart, r, fid, liee)
    if r["statut"] == "echec":
        _bloquer_taches(projet, taches, "L'agent n'a pas pu finir : " + reponse[:300])
        _terminer(projet, {"demande": liee}, "L'agent n'a pas pu finir : " + reponse[:300])
        return _apres_echec_d_installation(projet, etat, taches, "L'installation a échoué : " + reponse[:200])
    t0 = _tache(projet, taches[0])
    message_refuse = None
    if isinstance(r.get("cahier"), dict) and r["cahier"].get("partenaires"):
        try:      # les partenaires décidés au cadrage : connus, connecté pour « direct », inscrit pour « inscrit »
            lancer(projet, "partenaires", {"action": "verifier_cadrage", "partenaires": r["cahier"]["partenaires"]})
        except Refus as e:
            message_refuse = str(e)      # avant tout : rien du rapport n'est appliqué, l'agent le rend de nouveau
    for commande, entree in ([] if message_refuse else rapport.commandes(
            r, fonctionnalite=fid, tache=taches[0], agent=execution.agent, etape=str(t0.get("etape") or ""))):
        try:
            lancer(projet, commande, entree)
        except Refus as e:
            lancer(projet, "tache", {"id": taches[0], "journal": [f"{JOURNAL_REFUS} ({commande}) : {e}"]})
            if commande == "message":     # la réponse de l'agent est perdue : il la rend de nouveau, ou la tâche est bloquée
                message_refuse = str(e)
                break
    refus = _m(etat, "refus_relances", set)
    if message_refuse:
        if liee:
            _m(etat, "liees")[taches[0]] = liee
        return _message_refuse(projet, etat, execution, depart, r, message_refuse)
    refus.discard(taches[0])
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


JOURNAL_REFUS = "Refusé par l'outil"
FORME_DES_QUESTIONS = '{"texte": "…", "choix": ["…", "…"], "multiple": false}'


def _supplement_de_refus(raison, message=None):
    s = f"Ta réponse a été refusée : {raison} Rends-la au bon format, sans refaire le travail."
    if message:
        s += ("\n\nTon message refusé, à reprendre tel quel une fois corrigé :\n```json\n"
              + json.dumps(message, ensure_ascii=False)[:4000] + "\n```")
    if "questions" in raison:
        s += f"\nUne question : `{FORME_DES_QUESTIONS}`."
    return s


def _relancer_apres_refus(projet, etat, depart, raison, message=None):
    """Le même agent, sur la même tâche, avec la raison du refus. Sa session n'est pas reprise (le départ la rejoue en
    entier) : son message refusé est redonné dans la matière, il n'a rien à refaire."""
    tid = depart["taches"][0]
    _m(etat, "refus_relances", set).add(tid)
    matiere = (depart.get("matiere") or "").rstrip() + "\n\n" + _supplement_de_refus(raison, message)
    lancer(projet, "tache", {"id": tid, "active": True,
                             "journal": ["Réponse refusée par l'outil : l'agent la rend de nouveau."]})
    etat["departs"][tid] = {**depart, "matiere": matiere}
    etat["en_cours"].add(tid)
    return [a_agent(depart["agent"], depart["taches"], matiere)]


def _message_refuse(projet, etat, execution, depart, r, raison):
    """Le message d'un agent refusé par l'outil : l'agent le rend de nouveau une fois, puis la tâche est bloquée."""
    tid = depart["taches"][0]
    if tid not in _m(etat, "refus_relances", set):
        return _relancer_apres_refus(projet, etat, depart, raison, r.get("message"))
    _m(etat, "refus_relances", set).discard(tid)
    raison = f"La réponse de l'agent a été refusée par l'outil deux fois : {raison}"
    _bloquer_taches(projet, depart["taches"], raison)
    t = _tache(projet, tid)
    if t.get("fonctionnalite"):
        _dire(projet, t["fonctionnalite"], f"La tâche « {t['titre']} » est bloquée : {raison}")
    _terminer(projet, {"demande": _m(etat, "liees").pop(tid, None)}, raison)
    return _apres_echec_d_installation(projet, etat, depart["taches"], raison)


ATTENTES_PANNE_S = (120, 300, 600, 900)     # 2, 5, 10 puis 15 min entre deux essais tant que la panne dure


def _panne_en_cours(etat, maintenant=None):
    """La panne du service Claude qui retient les départs (`{jusqu_a, texte, n}`), ou `None` si l'essai suivant est dû."""
    p = etat.get("panne")
    return p if p and (time.time() if maintenant is None else maintenant) < p["jusqu_a"] else None


def _service_en_panne(projet, etat, execution, depart, maintenant=None):
    """Le service Claude était indisponible : la tâche n'a pas échoué. Elle reste prête au travail (aucun essai compté,
    jamais bloquée) et plus rien ne part avant le prochain essai, de plus en plus espacé tant que la panne dure."""
    maintenant = time.time() if maintenant is None else maintenant
    n = (etat.get("panne") or {}).get("n", 0)
    jusqu_a = maintenant + ATTENTES_PANNE_S[min(n, len(ATTENTES_PANNE_S) - 1)]
    raison = str(execution.erreur or "").replace("l'appel a échoué : ", "")[:160]
    texte = (f"Service Claude indisponible ({raison}) : nouvel essai à "
             f"{datetime.fromtimestamp(jusqu_a).strftime('%H h %M')}.")
    etat["panne"] = {"jusqu_a": jusqu_a, "texte": texte, "n": n + 1}
    for tid in depart["taches"]:
        lancer(projet, "tache", {"id": tid, "active": False, "journal": [texte]})
        if tid not in _m(etat, "a_lancer", list):
            etat["a_lancer"].append(tid)
    return []


def _agent_en_echec(projet, etat, execution, depart):
    """Un agent sans rapport : relancé une fois, puis tâche bloquée avec la raison au journal. Une panne du service
    Claude n'est pas un échec : voir `_service_en_panne`."""
    if getattr(execution, "panne", False):
        return _service_en_panne(projet, etat, execution, depart)
    etat.pop("panne", None)
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
    if str(execution.erreur or "").startswith(ERREUR_CLOUD):
        _session_a_creer(projet, depart["agent"], str(execution.erreur)[len(ERREUR_CLOUD):].strip(" :"), tid,
                         session=_m(etat, "sessions_cloud").get(depart["agent"]))
    return _apres_echec_d_installation(projet, etat, depart["taches"], raison)


ERREUR_CLOUD = "session cloud"       # le début de l'erreur d'un départ cloud (`boucle._partir_cloud`)


ADRESSE_CODE = "https://claude.ai/code"


def texte_session_a_creer(fiche, raison, url, *, avec_depart=False, session_ouverte=False):
    """La démarche de la décision « Sessions cloud à créer », quand le moteur n'a pas pu lancer la session lui-même.
    `avec_depart` : la décision porte le message de départ à coller (la démarche simplifiée) ; `session_ouverte` : le
    lien est celui de la session déjà inscrite pour l'agent."""
    nom = fiche.get("prenom") or fiche["cle"]
    depot = url or "le dépôt GitHub du projet"
    if avec_depart and session_ouverte:
        return (f"Le moteur n'a pas pu envoyer sa tâche suivante à la session cloud de {nom} ({fiche['role']}, "
                f"{fiche['modele']}) : {raison}. Envoyez-la vous-même : 1. ouvrez la session de {nom} (lien ci-dessous) "
                f"ou créez-en une nouvelle sur claude.ai/code, dépôt {depot}, modèle {fiche['modele']} ; 2. collez le "
                "message de départ ci-dessous et envoyez-le ; 3. collez ici l'adresse (ou l'identifiant) de la session "
                "et cliquez « C'est fait » : le moteur la relève.")
    if avec_depart:
        return (f"Le moteur n'a pas pu lancer la session cloud de {nom} ({fiche['role']}, {fiche['modele']}) : {raison}. "
                f"Créez-la vous-même : 1. ouvrez claude.ai/code ; 2. choisissez le dépôt {depot} et le modèle "
                f"{fiche['modele']} ; 3. collez le message de départ ci-dessous et envoyez-le ; 4. collez ici l'adresse "
                "(ou l'identifiant) de la session créée et cliquez « C'est fait » : le moteur la relève et lui envoie "
                "les tâches suivantes de cet agent.")
    return (f"Le moteur n'a pas pu lancer la session cloud de {nom} ({fiche['role']}, {fiche['modele']}) : {raison}. "
            "Démarche : 1. vérifiez que la commande claude est installée et connectée à votre compte (lancez « claude », "
            "puis /login) ; 2. sur claude.ai/code, connectez GitHub et donnez à Claude l'accès à "
            f"{depot} ; 3. créez-y une session sur ce dépôt, modèle {fiche['modele']}, pour vérifier qu'elle démarre ; "
            "4. donnez son nom ici et cliquez « C'est fait » : les tâches bloquées de cet agent repartent, et le moteur "
            "relance lui-même ses sessions.")


def _session_a_creer(projet, cle, raison, tache=None, session=None):
    """Pose (une fois par agent) la décision `session_cloud` avec la démarche ; avec `tache`, la démarche simplifiée :
    le lien claude.ai/code (celui de la session déjà inscrite pour l'agent, s'il y en a une), le dépôt et le message de
    départ complet de cette tâche, à coller dans la session."""
    court = _etat(projet)
    if any(d.get("genre") == "session_cloud" and d.get("agent") == cle for d in court.get("decisions") or []):
        return
    fiche = next((a for a in court["agents"] if a["cle"] == cle), None)
    if fiche is None:
        return
    try:
        from orchestrateur import recrutement
        url = recrutement.depot(projet.dossier)["url"]
        fiche = dict(fiche, prenom=next((x.get("prenom") for x in fi.lire_toutes(_factory(projet)["fiches"])
                                         if x["cle"] == cle), None))
    except (OSError, fi.FicheInvalide):
        url = None
    if _polyvalent(fiche):      # un agent polyvalent : le modèle de la tâche (sinon Sonnet), un seul compte de session
        t = next((x for x in court["taches"] if x["id"] == tache), None) if tache else None
        fiche = dict(fiche, role="agent polyvalent",
                     modele=_modele_de_depart(projet, court, cle, t) if t is not None else "Sonnet")
    plus = {}
    if tache:
        try:
            message = lancer(projet, "depart", {"agent": cle, "tache": tache})["message"]
        except (Refus, ErreurMoteur):
            message = None
        from moteur import cloud
        inscrite = cloud.lire_session(session or fiche.get("session") or "")
        if message and len(message) <= LONGUEUR_MAX_DEPART:
            plus = {"tache": tache, "depart": message, "lien": inscrite["adresse"] if inscrite else ADRESSE_CODE,
                    "modele": fiche["modele"]}
            if url and url.startswith("https://"):
                plus["depot"] = url
    lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": "session_cloud", "agent": cle,
                                "texte": texte_session_a_creer(fiche, raison or "raison inconnue", url,
                                                               avec_depart=bool(plus),
                                                               session_ouverte=bool(plus) and plus["lien"] != ADRESSE_CODE),
                                **plus})


LONGUEUR_MAX_DEPART = 24000      # comme `cloud.LONGUEUR_MAX_DEPART`


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
    if r["statut"] == "outil_refuse":
        return _outil_refuse(projet, etat, execution, depart, r, fid or t.get("fonctionnalite"))
    return _accord_demande(projet, etat, execution, depart, r, fid, t)


GENRE_ACCORD = "accord_agent"       # la décision de projet « Demandes d'accord des agents » (bureau de direction)
REGLE_APPAREIL = ("Règle du projet : tests automatiques sur émulateur (machine virtuelle), validation de version par la "
                  "fenêtre de validation. Jamais d'installation ni de test sur votre téléphone.")
CONSIGNE_APPAREIL = ("Pas de test sur appareil : émulateur pour les tests automatiques, fenêtre de validation pour la "
                     "version. Continue ta tâche sans ce test.")
REGLE_PROJET_APPAREIL = ("Pas d'installation ni de test sur un appareil physique : tests automatiques sur émulateur, "
                         "validation de version par la fenêtre de validation.")
MOTIFS_APPAREIL = re.compile(r"adb\s+(install|devices|push|shell)|d[ée]bogage\s+usb|usb\s+debugging|"
                             r"t[ée]l[ée]phone\s+branch[ée]|appareil\s+(physique|branch[ée])|device\s+connect",
                             re.IGNORECASE)


def _vise_un_appareil(*textes):
    """La demande d'accord vise une installation ou un test sur un appareil physique de l'utilisateur."""
    return any(MOTIFS_APPAREIL.search(t) for t in textes if isinstance(t, str))


def _choix_de_l_agent(r):
    """Les choix que l'agent a proposés avec sa demande (la première question à choix de son message) : 6 au plus,
    120 caractères chacun, sans doublon."""
    for q in (r.get("message") or {}).get("questions") or []:
        if isinstance(q, dict) and isinstance(q.get("choix"), list):
            vus = []
            for c in q["choix"]:
                if isinstance(c, str) and c.strip() and c.strip()[:120] not in vus:
                    vus.append(c.strip()[:120])
            if vus:
                return vus[:6]
    return []


def _accord_demande(projet, etat, execution, depart, r, fid, t):
    """Une demande d'accord d'un agent : une décision au bureau de direction (agent, tâche, quoi, pourquoi, ce que ça
    implique, rappel de la règle d'un appareil physique), pas seulement une question dans la discussion."""
    tid, cle = depart["taches"][0], execution.agent
    a = r["accord"]
    prenom = prenom_de(projet, cle)
    quoi = f"{a['quoi']} (chez {a['partenaire']}, {a['cout']})"
    message = (r.get("message") or {}).get("texte") or ""
    pourquoi = a.get("pourquoi") if isinstance(a.get("pourquoi"), str) and a["pourquoi"].strip() else message
    implique = a.get("implique") if isinstance(a.get("implique"), str) and a["implique"].strip() else ""
    appareil = _vise_un_appareil(a["quoi"], pourquoi, implique, message)
    texte = f"{prenom} ({cle}) demande votre accord, tâche « {t['titre']} » : {a['quoi']}."
    lancer(projet, "tache", {"id": tid, "active": False, "journal": [f"L'agent {cle} demande votre accord : {quoi}."]})
    _liberer_le_lot(projet, depart)
    champs = {"agent": cle, "tache": tid, "quoi": a["quoi"][:600], "partenaire": a["partenaire"][:200],
              "cout": a["cout"][:200]}
    if pourquoi.strip():
        champs["pourquoi"] = pourquoi.strip()[:800]
    if implique.strip():
        champs["implique"] = implique.strip()[:800]
    regles = rp.lire(_factory(projet))
    choix = _choix_de_l_agent(r)
    if choix:      # l'agent a proposé des choix : le bureau les montre comme boutons
        champs["choix"] = choix
    if appareil:
        champs["appareil"] = True
        champs["regle"] = REGLE_APPAREIL
        if not any(x["texte"].casefold() == REGLE_PROJET_APPAREIL.casefold() for x in regles):
            champs["regle_proposee"] = REGLE_PROJET_APPAREIL      # la case « Retenir comme règle du projet », cochée
    touchees = rp.touchees(regles, a["quoi"], pourquoi, implique, message)
    if touchees:      # un rappel : le Directeur statue toujours, rien n'est refusé d'office
        champs["regles_touchees"] = [{"id": x["id"], "texte": x["texte"]} for x in touchees]
    lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": GENRE_ACCORD, "texte": texte, **champs})
    fid = fid or t.get("fonctionnalite")
    if fid:
        for commande, entree in rapport.commandes(r, fonctionnalite=fid, tache=tid, agent=cle, etape=""):
            try:
                lancer(projet, commande, entree)
            except Refus as e:
                lancer(projet, "tache", {"id": tid, "journal": [f"{JOURNAL_REFUS} ({commande}) : {e}"]})
        _dire(projet, fid, f"{prenom} demande votre accord : la décision est au bureau de direction.")
    return []


def _reprise_apres_accord(projet, etat, tid, fid, quoi, accepte, consigne=""):
    """L'agent reprend la même tâche : avec l'accord, ou, refusé, sans l'action refusée mais avec la consigne du
    Directeur (la tâche n'est pas mise de côté)."""
    if accepte:
        return _reprendre_la_tache(projet, etat, tid, fid, f"L'utilisateur a donné son accord pour : {quoi}. Tu peux le faire.",
                                   f"Accord de l'utilisateur : {quoi}")
    supplement = (f"L'utilisateur refuse : {quoi}. Ne le fais pas : continue ta tâche sans cette action (dis dans ton "
                  "résultat qu'elle n'est pas faite).")
    if consigne:
        supplement += f" Sa consigne : {consigne}"
    return _reprendre_la_tache(projet, etat, tid, fid, supplement,
                               f"Accord refusé par l'utilisateur : {quoi}" + (f" — consigne : {consigne}" if consigne else ""))


def _retenir_la_regle(projet, d, demande, verdict, consigne):
    """La case « Retenir comme règle du projet » : le texte de la réponse devient une règle du projet (origine : la
    décision et l'agent). Un refus de la règle (liste pleine, texte invalide) est dit dans le journal de la tâche ; la
    réponse à l'agent n'en dépend pas."""
    texte = (demande.get("regle") or "").strip()
    if not texte:
        return
    try:
        lancer(projet, "regles", {"action": "ajouter", "texte": texte, "origine": {"decision": d["id"], "agent": d["agent"]}})
    except Refus as e:
        lancer(projet, "tache", {"id": d["tache"], "journal": [f"La règle du projet n'a pas été notée : {e}"]})


def _sur_accord_agent(projet, demande, etat):
    """La réponse du Directeur à une demande d'accord : accepter ou refuser (avec une consigne facultative)."""
    d = next((x for x in _etat(projet)["decisions"] if x["id"] == demande["decision"] and x["genre"] == GENRE_ACCORD), None)
    if d is None:
        raise Refus("cette demande n'existe plus")
    tid, verdict = d["tache"], demande["verdict"]
    if verdict not in ("accepter", "refuser", "choisir"):
        raise Refus(f"réponse inconnue : {verdict}")
    choix = demande.get("choix")
    if verdict == "choisir" and choix not in (d.get("choix") or []):
        raise Refus("ce choix n'est pas l'un de ceux que l'agent a proposés")
    t = _tache(projet, tid)
    consigne = (demande.get("texte") or "").strip()
    if verdict == "refuser" and not consigne and d.get("appareil"):
        consigne = CONSIGNE_APPAREIL
    prenom = prenom_de(projet, d["agent"])
    _retenir_la_regle(projet, d, demande, verdict, consigne)
    if verdict == "choisir":     # la réponse transmise à l'agent est le choix retenu (et la consigne)
        supplement = f"Sur ta demande ({d['quoi']}), l'utilisateur a choisi : « {choix} »." + (f" Sa consigne : {consigne}" if consigne else "")
        actions = _reprendre_la_tache(projet, etat, tid, t.get("fonctionnalite"), supplement,
                                      f"Choix de l'utilisateur : {choix}" + (f" — consigne : {consigne}" if consigne else ""))
    else:
        actions = _reprise_apres_accord(projet, etat, tid, t.get("fonctionnalite"), d["quoi"], verdict == "accepter", consigne)
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    _terminer(projet, {"demande": demande["id"]},
              f"{prenom} reprend sa tâche avec votre accord." if verdict == "accepter"
              else f"{prenom} reprend sa tâche selon votre choix." if verdict == "choisir"
              else f"{prenom} reprend sa tâche sans cette action.")
    return actions


_SUR[GENRE_ACCORD] = _sur_accord_agent


# --- Un partenaire où l'utilisateur est inscrit (hors liaison directe) : l'agent prépare, l'utilisateur fait.

GENRE_CHEZ = "faire_chez_partenaire"      # la décision de projet « À faire chez <partenaire> » (bureau de direction)


def _chez_partenaire_demande(projet, etat, execution, depart, r, fid, liee):
    """Un agent a préparé ce que l'utilisateur fait chez un partenaire (prompt, réglages, mode opératoire, ce qu'il doit
    rapporter) : une décision « À faire chez … » au bureau de direction. L'agent reprend la même tâche sur le retour (le
    résultat joint, ou « Fait »). L'outil juge la demande (partenaire connu, plafond du prompt, réglages) : refusée, l'agent
    la rend une fois de nouveau, puis la tâche est bloquée."""
    tid, cle = depart["taches"][0], execution.agent
    c = r["chez_partenaire"]
    t = _tache(projet, tid)
    prenom = prenom_de(projet, cle)
    champs = {k: c[k] for k in ("partenaire", "quoi", "prompt", "reglages", "mode_operatoire", "a_rapporter", "elements") if k in c}
    try:
        decision = lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": GENRE_CHEZ,
                                               "texte": "À faire chez un partenaire", "agent": cle, "tache": tid, **champs})
    except Refus as e:
        if liee:
            _m(etat, "liees")[tid] = liee
        return _message_refuse(projet, etat, execution, depart, {"message": c}, str(e))
    _m(etat, "refus_relances", set).discard(tid)
    d = next((x for x in _etat(projet)["decisions"] if x["id"] == decision["id"]), {})
    nom = d.get("nom_partenaire") or c["partenaire"]
    lancer(projet, "tache", {"id": tid, "active": False, "journal": [f"{prenom} ({cle}) a préparé ce qu'il y a à faire chez {nom} : "
                                                                     f"{c['quoi'][:200]}."]})
    _liberer_le_lot(projet, depart)
    if fid:
        for commande, entree in rapport.commandes(r, fonctionnalite=fid, tache=tid, agent=cle, etape=""):
            try:
                lancer(projet, commande, entree)
            except Refus as e:
                lancer(projet, "tache", {"id": tid, "journal": [f"{JOURNAL_REFUS} ({commande}) : {e}"]})
        _dire(projet, fid, f"{prenom} a préparé une génération à faire chez {nom} : « À faire chez {nom} » est au bureau de "
                           "direction (prompt prêt à copier, réglages et mode opératoire).")
    _terminer(projet, {"demande": liee}, f"{prenom} a préparé ce que vous avez à faire chez {nom} : c'est au bureau de direction.")
    return []


def _sur_faire_chez_partenaire(projet, demande, etat):
    """Le retour de « À faire chez … » : « fait » (le résultat joint et/ou un texte) ou « impossible » (ce qui a bloqué).
    L'agent reprend la même tâche avec ce que l'utilisateur rapporte."""
    from bureau import fichiers_joints as fj
    d = next((x for x in _etat(projet)["decisions"] if x["id"] == demande["decision"] and x["genre"] == GENRE_CHEZ), None)
    if d is None:
        raise Refus("cette demande n'existe plus")
    verdict = demande["verdict"]
    if verdict not in ("fait", "impossible"):
        raise Refus(f"réponse inconnue : {verdict}")
    tid = d["tache"]
    t = _tache(projet, tid)
    prenom, nom = prenom_de(projet, d["agent"]), d.get("nom_partenaire") or d["partenaire"]
    dit = (demande.get("texte") or "").strip()
    if verdict == "fait":
        fichiers = [{**x, "chemin": _chemin_pour_agent(projet, x["chemin"])} for x in demande.get("fichiers") or []
                    if isinstance(x, dict) and "chemin" in x]
        supplement = f"L'utilisateur a fait ce que tu as préparé chez {nom} ({d['quoi']})."
        if dit:
            supplement += f" Il dit : {dit}"
        if fichiers:      # ce qu'il rapporte : chemin, type, taille de chacun
            supplement += (" Fichiers rapportés :\n" + "\n".join(fj.lignes_pour_agent(fichiers)) + "\n" + fj.CONSIGNE_LECTURE
                           + f" Attendu : {d['a_rapporter']['description']}"
                           + (f" (nom attendu : {d['a_rapporter']['nom']})" if d["a_rapporter"].get("nom") else "") + ".")
        else:
            supplement += (" Il n'a joint aucun fichier : ce qu'il dit fait foi (il a pu déposer le résultat dans le dossier "
                           "du projet) ; s'il te manque quelque chose, redemande-le-lui.")
        journal = f"Fait chez {nom} par l'utilisateur" + (f" ({len(fichiers)} fichier(s) rapporté(s))" if fichiers else "")
        reponse = f"{prenom} reprend sa tâche avec ce que vous avez rapporté de chez {nom}."
    else:
        supplement = (f"L'utilisateur n'a pas pu le faire chez {nom} ({d['quoi']}) : {dit} Continue sans (dis dans ton résultat "
                      "que ce n'est pas fait) ou propose-lui une autre voie.")
        journal = f"Pas faisable chez {nom} : {dit[:200]}"
        reponse = f"{prenom} reprend sa tâche sans ce que vous deviez faire chez {nom}."
    actions = _reprendre_la_tache(projet, etat, tid, t.get("fonctionnalite"), supplement, journal)
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    _terminer(projet, {"demande": demande["id"]}, reponse)
    return actions


_SUR[GENRE_CHEZ] = _sur_faire_chez_partenaire


def _liberer_le_lot(projet, depart):
    for autre in depart["taches"][1:]:    # le reste du lot n'a pas été fait : il repart seul plus tard
        if _tache(projet, autre)["colonne"] != "fait":
            lancer(projet, "tache", {"id": autre, "lot": None})


# --- Un agent arrêté faute d'outil : voir `moteur.accord_outil`.

GENRE_OUTIL = "outil_agent"           # la décision de projet posée quand le moteur ne peut pas ouvrir l'outil seul
AUTORISER, REFUSER_OUTIL, RELANCER_OUTIL = "autoriser", "refuser", "relancer"
ARRET_OUTIL = re.compile(r"a besoin de l'outil (.+?), que sa fiche ne lui ouvre pas")   # la ligne de journal de l'arrêt
OUVERT_A = "Outil ouvert à "          # la ligne de journal d'un outil ouvert (par le moteur ou sur accord du Directeur)
REPRISE_OUTIL = "Le moteur a repris : l'outil"


def _fiche_de(projet, cle):
    try:
        return fi.trouver(fi.lire_toutes(_factory(projet)["fiches"]), cle)
    except (OSError, fi.FicheInvalide):
        return None


def _outil_deja_ouvert(projet, tid, regle):
    """Le moteur (ou le Directeur) a déjà ouvert cette règle pour cette tâche : un second refus du même programme n'est
    plus ouvert tout seul, il revient au Directeur."""
    return any(j["texte"].startswith(OUVERT_A) and regle in j["texte"] for j in _tache(projet, tid).get("journal") or [])


def _outil_refuse(projet, etat, execution, depart, r, fid):
    """L'agent s'arrête faute d'un outil que sa fiche ne lui ouvre pas. Un programme du shell connu du projet est ouvert
    tout de suite à cet agent (une fois par tâche) et la tâche repart ; sinon, une décision au bureau de direction."""
    tid, cle = depart["taches"][0], execution.agent
    outil = (r.get("outil") or "").strip()
    fiche = _fiche_de(projet, cle)
    prenom = (fiche or {}).get("prenom") or cle
    lieu = (fiche or {}).get("lieu", "local")
    programme = commande = None
    if outil.split("(")[0].strip() == "Bash" and fiche is not None:
        commandes = [x["commande"] for x in execution.refus if x.get("outil") == "Bash" and x.get("commande")]
        programme, commande = accord_outil.programme_refuse(commandes, fi.outils(fiche))
    regle = fi.regle_bash(programme) if programme else None
    quoi = regle or outil
    montree = accord_outil.montrer(commande)
    texte = f"L'agent {cle} a besoin de l'outil {quoi}, que sa fiche ne lui ouvre pas."
    if montree:
        texte += f" Commande refusée : « {montree} »."
    lancer(projet, "tache", {"id": tid, "active": False, "journal": [texte]})
    _liberer_le_lot(projet, depart)
    origine = accord_outil.origine(programme, _factory(projet).get("environnement")) if programme else None
    if origine and lieu == "local" and not _outil_deja_ouvert(projet, tid, regle):
        lancer(projet, "fiche", {"action": "ouvrir_outil", "cle": cle, "outil": regle})
        return _reprendre_la_tache(projet, etat, tid, fid, f"{regle} est maintenant ouvert dans ta fiche : relance ta commande.",
                                   f"{OUVERT_A}{prenom} : {regle} (programme {origine})")
    t = _tache(projet, tid)
    qui = f"{prenom} ({cle})"
    if programme:
        consigne = (f"{qui} est arrêté : il lui faut le programme « {programme} » (règle {regle}), que sa fiche ne lui "
                    "ouvre pas" + (" ; ce programme n'est pas déclaré dans l'environnement du projet" if not origine else "")
                    + (" ; c'est un agent cloud, sa session garde ses propres réglages" if lieu == "cloud" else "") + ".")
    else:
        consigne = (f"{qui} est arrêté : il lui faut l'outil « {outil} », que sa fiche ne lui ouvre pas. Ouvrez-le "
                    "vous-même à la ligne « Outils : » de sa fiche, puis relancez l'agent.")
    lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": GENRE_OUTIL, "agent": cle, "tache": tid,
                                "outil": quoi[:100], **({"programme": programme} if programme else {}),
                                **({"commande": montree} if montree else {}),
                                "texte": consigne + f" Tâche : « {t['titre']} »."})
    if fid:
        for commande, entree in rapport.commandes(r, fonctionnalite=fid, tache=tid, agent=cle, etape=""):
            try:
                lancer(projet, commande, entree)      # ce que l'agent dit de son arrêt, dans la discussion
            except Refus as e:
                lancer(projet, "tache", {"id": tid, "journal": [f"{JOURNAL_REFUS} ({commande}) : {e}"]})
        _dire(projet, fid, f"{qui} est arrêté faute d'un outil : la décision est au bureau de direction.")
    return []


def _reprendre_la_tache(projet, etat, tid, fid, supplement, journal):
    """La même tâche repart avec le même agent : débloquée, sortie de son lot, remise dans les départs à faire."""
    lancer(projet, "tache", {"id": tid, "bloquee": None, "lot": None, "journal": [journal]})
    if tid not in _m(etat, "a_lancer", list):
        etat["a_lancer"].append(tid)
    _m(etat, "supplements")[tid] = supplement
    return _demarrer_en_attente(projet, etat, fid)


def _sur_outil_agent(projet, demande, etat):
    """La réponse du Directeur à « cet agent a besoin d'un outil » : autoriser le programme (ouvert à cet agent, la
    tâche repart), refuser (la tâche est bloquée avec la raison) ou, la fiche ayant été complétée à la main, relancer."""
    d = next((x for x in _etat(projet)["decisions"] if x["id"] == demande["decision"] and x["genre"] == GENRE_OUTIL), None)
    if d is None:
        raise Refus("cette question n'existe plus")
    tid, cle, verdict = d["tache"], d["agent"], demande["verdict"]
    t = _tache(projet, tid)
    fid = t.get("fonctionnalite")
    prenom = prenom_de(projet, cle)
    if verdict == AUTORISER:
        if not d.get("programme"):
            raise Refus("cette décision ne nomme pas de programme à autoriser")
        regle = fi.regle_bash(d["programme"])
        lancer(projet, "fiche", {"action": "ouvrir_outil", "cle": cle, "outil": regle})
        actions = _reprendre_la_tache(projet, etat, tid, fid, f"{regle} est maintenant ouvert dans ta fiche : relance ta commande.",
                                      f"{OUVERT_A}{prenom} : {regle} (autorisé par le Directeur)")
        reponse = f"{regle} est ouvert à {prenom} ; sa tâche repart."
    elif verdict == RELANCER_OUTIL:
        actions = _reprendre_la_tache(projet, etat, tid, fid, f"L'outil {d['outil']} est maintenant ouvert dans ta fiche.",
                                      f"{REPRISE_OUTIL} {d['outil']} est ouvert dans la fiche, sur demande du Directeur : nouvel essai.")
        reponse = f"La tâche de {prenom} repart."
    elif verdict == REFUSER_OUTIL:
        raison = f"L'outil {d['outil']} a été refusé à {prenom} par le Directeur."
        _bloquer_taches(projet, [tid], raison)
        if fid:
            _dire(projet, fid, f"La tâche « {t['titre']} » est bloquée : {raison}")
        actions, reponse = [], raison
    else:
        raise Refus(f"réponse inconnue : {verdict}")
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    _terminer(projet, {"demande": demande["id"]}, reponse)
    return actions


_SUR[GENRE_OUTIL] = _sur_outil_agent


def reprendre_les_taches_sans_outil(projet, etat):
    """Au démarrage du moteur : une tâche arrêtée faute d'outil (inactive, agent attribué, ni faite ni bloquée, dernière
    ligne du journal = l'arrêt) dont la fiche ouvre maintenant l'outil repart, une fois. L'outil est ouvert quand la
    règle nommée par l'arrêt est dans la fiche ou, si l'arrêt ne la nomme pas (« Bash »), quand la fiche a été
    modifiée depuis. Rien tant qu'une décision attend le Directeur pour cette tâche."""
    court = _etat(projet)
    if court["pause"]:
        return []
    attendues = {d.get("tache") for d in court["decisions"] if d["genre"] == GENRE_OUTIL}
    deja, actions = _m(etat, "reprises_outil", set), []
    for t in court["taches"]:
        if (t["active"] or not t.get("agent") or t["colonne"] == "fait" or t.get("bloquee") or t["id"] in deja
                or t["id"] in attendues or t["id"] in etat["en_cours"] or fiche_cloud(court, t["agent"])):
            continue
        journal = _tache(projet, t["id"]).get("journal") or []
        m = ARRET_OUTIL.search(journal[-1]["texte"]) if journal else None
        fiche = _fiche_de(projet, t["agent"])
        if m is None or fiche is None or not _fiche_ouvre(fiche, m.group(1), journal[-1]["t"]):
            continue
        if any(j["texte"].startswith(f"{REPRISE_OUTIL} {m.group(1)}") for j in journal):
            continue      # déjà repris pour cet outil : le second arrêt revient au Directeur
        deja.add(t["id"])
        actions += _reprendre_la_tache(projet, etat, t["id"], t.get("fonctionnalite"),
                                       f"L'outil {m.group(1)} est maintenant ouvert dans ta fiche.",
                                       f"{REPRISE_OUTIL} {m.group(1)} est ouvert dans la fiche, nouvel essai.")
    return actions


def _fiche_ouvre(fiche, outil, depuis):
    """La fiche ouvre l'outil de l'arrêt : sa règle y est ; ou, l'arrêt ne nommant que « Bash », la fiche a changé depuis
    (la ligne « Outils : » complétée à la main)."""
    if outil in fi.outils(fiche):
        return True
    if outil != "Bash":
        return False
    try:
        arret = datetime.fromisoformat(depuis).timestamp()
        return Path(fiche["chemin"]).stat().st_mtime > arret
    except (ValueError, OSError):
        return False


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
        cahier = {"maquette": r["cahier"]["maquette"], "etapes": r["cahier"]["etapes"]}
        if "partenaires" in r["cahier"]:      # les partenaires décidés au cadrage (la réponse de l'utilisateur)
            cahier["partenaires"] = r["cahier"]["partenaires"]
        lancer(projet, "fonctionnalite", {"id": fid, "cahier": cahier, "etape": "cahier"})
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
    if wf.est_validation(s) and not _concerne(v["element"], s["id"]) and v["pas"] + 1 < len(pas):
        # l'élément n'est pas concerné : il passe sans arrêt, mais l'étape suivante attend la barrière (voir `_barrieres`)
        v["pas"] += 1
        return _tache_de_flux(projet, etat, v, journal)
    if wf.est_validation(s):
        return _attendre_le_directeur(projet, etat, v, s)
    journal = list(journal or []) + v.pop("journal_suivant", [])     # la note du Directeur jointe à sa validation
    tid = _creer_tache(projet, f"{s['nom']} : {v['element']['nom']}", v["fid"], s["role"], ETAPES_DE_FLUX + s["id"],
                       element=v["element"]["id"], colonne=s["id"], journal=journal or None)
    v["taches"].append(tid)
    return tid


def _attendre_le_directeur(projet, etat, v, s):
    """L'élément arrive à une étape de validation : une tâche sans agent et une décision de projet, avec le compte rendu
    et les fichiers de l'étape précédente, ses points à vérifier et son lien d'accès. Rien ne part tant que le Directeur
    n'a pas répondu. Jamais rien à valider : sans image, sans livrable téléchargeable et sans lien d'accès, la décision
    n'est pas posée (voir `_rien_a_verifier`)."""
    precedent = v.get("dernier_rapport") or {}
    nature = precedent.get("nature") if rel.nature_ok(precedent.get("nature")) else None
    if nature in ("visuel", "son", "mecanique"):      # jamais l'apk pour juger un visuel, un son ou une mécanique
        precedent = {**precedent, "fichiers": [x for x in precedent.get("fichiers") or []
                                               if not rel.est_executable(x.get("chemin"))]}
    if not rel.texte_dit_ok(precedent.get("doit_marcher"), rel.MAX_DOIT_MARCHER):
        # Après un renvoi, ce qui doit marcher est connu : les points que le Directeur a demandé de revoir (essai réel :
        # l'agent, jugeant la correction déjà faite ailleurs, ne le disait pas, deux fois, et la validation restait bloquée).
        renvoi = _remarque_du_renvoi(projet, v)
        if renvoi:
            precedent = {**precedent, "doit_marcher": renvoi}
        elif v.get("rien_a_verifier") and _de_quoi_verifier(projet, precedent):
            # Second essai toujours muet, mais il y a de quoi vérifier : la validation est posée avec l'objectif de
            # l'étape comme consigne, plutôt que bloquée (essai réel : trois validations arrêtées, l'agent jugeant
            # qu'il n'y avait « rien à modifier »). Le Directeur juge, et renvoie s'il le faut.
            precedent = {**precedent, "doit_marcher": _doit_marcher_derive(_objectif_de(projet, v, s))}
    manques = ([] if _de_quoi_verifier(projet, precedent) else ["rien"]) \
        + ([] if rel.texte_dit_ok(precedent.get("doit_marcher"), rel.MAX_DOIT_MARCHER) else ["doit_marcher"]) \
        + _manques_de_nature(projet, nature, precedent)
    if v.pop("rapport_du_suivi", False):
        # le rapport a été perdu pendant l'arrêt du moteur (relu dans le suivi) : la validation est posée avec ce qu'il y
        # a à vérifier, l'étape n'est refaite que s'il n'y a rien du tout
        manques = [m for m in manques if m == "rien"]
    if manques:
        return _rien_a_verifier(projet, etat, v, s, manques)
    v.pop("rien_a_verifier", None)
    v["phase"] = "validation"
    element = v["element"]
    tid = lancer(projet, "tache", {"titre": f"Validation du Directeur : {element['nom']}", "fonctionnalite": v["fid"],
                                   "etape": ETAPES_DE_VALIDATION + s["id"], "active": False, "colonne": s["id"],
                                   "element": element["id"]})["id"]
    v["taches"].append(tid)
    a_valider = s["nom"] + (f" — {s['raison'].strip()}" if isinstance(s.get("raison"), str) and s["raison"].strip()
                            else "")
    objectif = _objectif_de(projet, v, s)[:OBJECTIF_MAX]
    entree = {"action": "poser", "portee": "projet", "genre": GENRE_VALIDATION, "fonctionnalite": v["fid"],
              "texte": f"L'élément « {element['nom']} » attend votre validation : « {s['nom']} ».",
              "element": {"id": element["id"], "nom": element["nom"]}, "etape": s["id"], "tache": tid,
              "objectif": objectif, "a_valider": a_valider[:OBJECTIF_MAX],
              "compte_rendu": precedent.get("compte_rendu") or "", "fichiers": list(precedent.get("fichiers") or []),
              "points": precedent.get("points") or _points_derives(objectif, precedent)}
    if precedent.get("acces"):
        entree["acces"] = precedent["acces"]
    if nature:
        entree["nature"] = nature
        if nature == "en_jeu":
            entree["mode_operatoire"] = list(precedent["mode_operatoire"])
    for c in ("doit_marcher", "pas_encore", "conclusion"):
        if isinstance(precedent.get(c), str) and (precedent[c].strip() or c == "pas_encore"):
            entree[c] = precedent[c]
    lancer(projet, "decision", entree)
    return tid


def _remarque_du_renvoi(projet, v):
    """« Les points renvoyés sont corrigés : … » d'après la dernière « Remarque du Directeur » portée par une étape du
    flux de l'élément (son renvoi), ou `None`."""
    for tid in reversed(v.get("taches") or []):
        t = _tache(projet, tid)
        if not str(t.get("etape") or "").startswith(ETAPES_DE_FLUX):
            continue
        for j in reversed(t.get("journal") or []):
            texte = str(j.get("texte") or "")
            if texte.startswith("Remarque du Directeur"):
                points = texte.split(":", 1)[1].strip()
                if points.lower().startswith("points à revoir"):
                    points = points.split(":", 1)[1].strip() if ":" in points else ""
                if points:
                    phrase = "Les points renvoyés sont corrigés : " + points
                    return phrase if len(phrase) <= rel.MAX_DOIT_MARCHER else phrase[:rel.MAX_DOIT_MARCHER - 1] + "…"
    return None


def _doit_marcher_derive(objectif):
    """Ce qui doit marcher quand l'agent ne l'a pas dit, tiré de l'objectif de l'étape (sans appel d'IA)."""
    debut = "L'agent ne l'a pas précisé : le résultat doit correspondre à l'objectif de l'étape. "
    objectif = " ".join(str(objectif or "").split()) or "ce que l'étape devait produire."
    phrase = debut + objectif
    return phrase if len(phrase) <= rel.MAX_DOIT_MARCHER else phrase[:rel.MAX_DOIT_MARCHER - 1] + "…"


OBJECTIF_MAX = 600
CONSIGNE_DE_QUOI_VERIFIER = (
    "Rien à valider : ton rapport n'a donné au Directeur ni image, ni livrable téléchargeable, ni lien d'accès. "
    "Refais l'étape en rendant de quoi vérifier : des captures PNG ou JPEG légendées (`message.images`), le "
    "livrable lui-même dans `fichiers` (apk, zip, pdf, exe… avec son `element`), ou, pour un site qui tourne, "
    "`acces` : {\"url\": \"http://127.0.0.1:<port>/\", \"description\": \"…\"} (le serveur laissé en marche).")


def _de_quoi_verifier(projet, precedent):
    """Vrai si le Directeur aura de quoi vérifier : un lien d'accès, ou une image ou un livrable téléchargeable qui
    existent dans le projet."""
    return rel.acces_ok(precedent.get("acces")) or _fichier_existe(
        projet, precedent, lambda c: rel.est_image(c) or rel.est_telechargeable(c))


def _fichier_existe(projet, precedent, convient):
    """Vrai si un fichier du rapport, dont le chemin `convient`, existe dans le projet."""
    try:
        f = fa.lire(projet.factory)
    except fa.FactoryInvalide:
        return False
    return any(convient(x.get("chemin")) and outil.fichier_du_projet(f, projet.dossier, x.get("chemin")) is not None
               for x in precedent.get("fichiers") or [])


def _manques_de_nature(projet, nature, precedent):
    """Ce que la nature déclarée de la validation exige et que le rapport n'a pas donné : en jeu, un livrable à essayer
    (ou un lien d'accès) et son mode opératoire ; un visuel, une image (plus les sons) ; un son, un fichier audio ;
    une mécanique, un document explicatif. Sans nature (ou `autre`), rien de plus."""
    if nature == "en_jeu":
        return ([] if rel.acces_ok(precedent.get("acces")) or _fichier_existe(projet, precedent, rel.est_executable)
                else ["livrable"]) + ([] if rel.mode_operatoire_ok(precedent.get("mode_operatoire")) else ["mode_operatoire"])
    if nature == "visuel":
        return [] if _fichier_existe(projet, precedent, rel.est_image) else ["image"]
    if nature == "son":
        return [] if _fichier_existe(projet, precedent, rel.est_son) else ["son"]
    if nature == "mecanique":
        return [] if _fichier_existe(projet, precedent, rel.est_document) else ["document"]
    return []


CONSIGNES_DE_NATURE = {
    "livrable": "Validation en jeu sans livrable : joins le livrable à essayer dans `fichiers` (apk, exe, zip… avec son "
                "`element`) ou, pour un site qui tourne, `acces` (le serveur laissé en marche).",
    "mode_operatoire": f"Validation en jeu sans mode opératoire : rends `mode_operatoire`, {rel.MIN_ETAPES_MODE} à "
                       f"{rel.MAX_ETAPES_MODE} étapes courtes ({rel.MAX_ETAPE_MODE} caractères au plus chacune) pour "
                       "l'utilisateur : installer, lancer, quoi faire, quoi observer.",
    "image": "Validation visuelle sans image : joins les images concernées (captures PNG ou JPEG légendées, "
             "`message.images`), jamais l'apk.",
    "son": "Validation d'un son sans fichier audio : joins le son à écouter dans `fichiers` (mp3, ogg, wav ou flac, "
           "avec son `element`), jamais l'apk.",
    "document": "Validation d'une mécanique sans document explicatif : écris un document (md ou pdf) qui explique la "
                "mécanique, joins-le dans `fichiers` (avec, si utile, images ou schémas), jamais l'apk (sauf si la "
                "mécanique est déjà jouable : alors `nature: en_jeu`).",
}
QUOI_MANQUE = {"rien": "sans rien à vérifier", "doit_marcher": "sans dire ce qui doit marcher",
               "livrable": "sans livrable à essayer", "mode_operatoire": "sans mode opératoire",
               "image": "sans image", "son": "sans son", "document": "sans document explicatif"}


CONSIGNE_DOIT_MARCHER = (
    "Validation sans consigne : ton rapport n'a pas dit au Directeur ce qu'il doit juger. Refais l'étape en rendant "
    f"`doit_marcher` (1 à 3 phrases, {rel.MAX_DOIT_MARCHER} caractères au plus : ce qui doit fonctionner pour valider), "
    f"`pas_encore` ({rel.MAX_PAS_ENCORE} caractères au plus, vide si tout est attendu : ce qui n'est pas encore attendu à "
    f"ce stade) et `conclusion` (une phrase, {rel.MAX_CONCLUSION} caractères au plus : « Validez si… »). Dans un lot : "
    "dans le compte rendu de l'élément (`comptes_rendus`).")


def _rien_a_verifier(projet, etat, v, s, manques=("rien",)):
    """L'élément arrive à la validation sans rien à montrer (`rien`) ou sans dire ce qui doit marcher (`doit_marcher`) :
    l'étape précédente est relancée une fois avec la consigne (un seul compteur pour les deux) ; au second échec, la
    tâche de validation est bloquée avec la raison (l'élément est laissé de côté, il ne retient plus la barrière)."""
    production = _production(projet, v["fid"])
    avant = next((k for k in range(v["pas"] - 1, -1, -1) if not wf.est_validation(production[k])), None)
    if not v.get("rien_a_verifier") and avant is not None:
        v["rien_a_verifier"] = 1
        v["pas"] = avant
        quoi = " et ".join(QUOI_MANQUE[m] for m in manques)
        _dire(projet, v["fid"], f"« {v['element']['nom']} » arrive à « {s['nom']} » {quoi} : l'étape "
                                f"« {production[avant]['nom']} » est refaite.")
        consignes = {"rien": CONSIGNE_DE_QUOI_VERIFIER, "doit_marcher": CONSIGNE_DOIT_MARCHER, **CONSIGNES_DE_NATURE}
        return _tache_de_flux(projet, etat, v, journal=[consignes[m] for m in manques])
    v.pop("rien_a_verifier", None)
    v["phase"] = "bloque"
    element = v["element"]
    raisons = []
    if "rien" in manques:
        raisons.append("Rien à valider : l'étape précédente n'a rendu ni image, ni livrable téléchargeable, ni lien "
                       "d'accès (deux fois).")
    if "doit_marcher" in manques:
        raisons.append("Validation sans consigne : l'étape précédente n'a pas dit ce qui doit marcher "
                       "(`doit_marcher`, deux fois).")
    for m in manques:
        if m in CONSIGNES_DE_NATURE:
            raisons.append(f"Validation incomplète : l'étape précédente est restée {QUOI_MANQUE[m]} (deux fois).")
    raisons.append("Écrivez un retour sur cette tâche (ce qu'il faut rendre) : l'étape précédente sera refaite avec, "
                   "puis la validation reposée.")
    raison = " ".join(raisons)
    tid = lancer(projet, "tache", {"titre": f"Validation du Directeur : {element['nom']}", "fonctionnalite": v["fid"],
                                   "etape": ETAPES_DE_VALIDATION + s["id"], "active": False, "colonne": s["id"],
                                   "element": element["id"]})["id"]
    v["taches"].append(tid)
    _bloquer_taches(projet, [tid], raison)
    _dire(projet, v["fid"], f"« {element['nom']} » est arrêté avant « {s['nom']} » : {raison}")
    return tid


def _points_derives(objectif, precedent):
    """Les points à vérifier quand l'agent n'en a pas rendu : tirés de l'objectif et de ce qu'il y a à vérifier, sans
    appel d'IA (chacun tient en 160 caractères)."""
    debut = "Le résultat correspond à l'objectif : "
    reste = rel.MAX_POINT - len(debut)
    objectif = " ".join(str(objectif or "").split())
    points = [debut + (objectif if len(objectif) <= reste else objectif[:reste - 1].rstrip() + "…")
              if objectif else rel.POINT_PAR_DEFAUT]
    fichiers = [x.get("chemin") for x in precedent.get("fichiers") or []]
    if any(rel.est_telechargeable(c) for c in fichiers):
        points.append("Le livrable se télécharge, s'installe et s'ouvre sans erreur")
    if precedent.get("acces"):
        points.append("Le site s'ouvre depuis le lien d'accès et répond sans erreur")
    if any(rel.est_image(c) for c in fichiers):
        points.append("Les images montrent ce qui est attendu, sans défaut visible")
    return points


def _objectif_de(projet, v, s):
    """Ce que l'élément devait produire, en une ou deux phrases, sans appel d'IA : l'`objectif` du découpage s'il est
    donné ; sinon son nom (et son groupe), l'étape qui précède la validation et la dernière consigne de sa tâche (une
    remarque du Directeur, par exemple)."""
    element = v["element"]
    if isinstance(element.get("objectif"), str) and element["objectif"].strip():
        return " ".join(element["objectif"].split())
    production = _production(projet, v["fid"])
    rang = next((k for k, x in enumerate(production) if x["id"] == s["id"]), 0)
    avant = next((production[k] for k in range(rang - 1, -1, -1) if not wf.est_validation(production[k])), None)
    groupe = f" ({element['groupe']})" if isinstance(element.get("groupe"), str) and element["groupe"].strip() else ""
    texte = f"Produire « {element['nom']} »{groupe}"
    texte += f", jusqu'à l'étape « {avant['nom']} »." if avant else "."
    precedente = next((t for t in reversed(v.get("taches") or [])
                       if str(_tache(projet, t).get("etape") or "").startswith(ETAPES_DE_FLUX)), None)
    if precedente:
        consignes = [j["texte"] for j in _tache(projet, precedente).get("journal") or []
                     if str(j.get("texte") or "").startswith("Remarque du Directeur")]
        if consignes:
            texte += f" {consignes[-1].strip()}"
    return texte


def _retenir_le_rapport(v, r):
    """Le compte rendu (2000 caractères au plus) et les fichiers du dernier rapport pour cet élément : ce que le Directeur
    voit à la validation suivante."""
    if r is None:
        return
    v.pop("rapport_du_suivi", None)      # un vrai rapport : la validation suivante exige tout ce qu'elle exige
    element = v["element"]
    eid = element["id"]
    du_lot = r.get("_du_lot") or {}
    autres = {e for e in du_lot.values() if e and e != eid}       # les autres éléments du même lot
    message = r.get("message") or {}
    propre = next((c for c in r.get("comptes_rendus") or [] if c.get("element") == eid), None)
    if propre is not None:
        texte, images = str(propre.get("texte") or "").strip(), list(propre.get("images") or [])
    else:
        texte = str(message.get("texte") or "").strip()
        images = list(message.get("images") or [])
        if autres:      # un lot à plusieurs éléments sans compte rendu par élément : ce qui nomme celui-ci
            mes_taches = [t for t, e in du_lot.items() if e == eid]
            texte = _passages_de(texte, [eid, element.get("nom")] + mes_taches)
            images = [x for x in images if _nomme(_texte_d_image(x), [eid, element.get("nom")] + mes_taches)]
    fichiers = [{"chemin": f["chemin"], "titre": f["titre"]} for f in r.get("fichiers") or []
                if f.get("element") == eid or (f.get("element") is None and not autres)]
    for x in images:
        chemin = x.get("chemin") if isinstance(x, dict) else x
        if isinstance(chemin, str) and chemin.strip() and all(f["chemin"] != chemin for f in fichiers):
            titre = (x.get("legende") if isinstance(x, dict) else None) or chemin.replace("\\", "/").rsplit("/", 1)[-1]
            fichiers.append({"chemin": chemin, "titre": titre})
    # Les points à vérifier et le lien d'accès : ceux du compte rendu de l'élément, sinon ceux du rapport (un site qui
    # tourne sert tous les éléments d'un lot).
    points = (propre or {}).get("points_a_verifier") or r.get("points_a_verifier") or []
    acces = (propre or {}).get("acces") or r.get("acces")
    # Ce que dit la validation : celui du compte rendu de l'élément s'il dit `doit_marcher`, sinon celui du rapport.
    dit = propre if (propre or {}).get("doit_marcher") else r
    # La nature et le mode opératoire vont ensemble : ceux du compte rendu de l'élément s'il déclare sa nature.
    nat = propre if (propre or {}).get("nature") else r
    v["dernier_rapport"] = {"compte_rendu": texte[:COMPTE_RENDU_MAX], "fichiers": fichiers[:FICHIERS_MAX],
                            "points": list(points)[:rel.MAX_POINTS], "acces": acces,
                            **{c: dit[c] for c in ("doit_marcher", "pas_encore", "conclusion") if c in dit},
                            **{c: nat[c] for c in ("nature", "mode_operatoire") if c in nat}}


def _texte_d_image(x):
    return " ".join(str(x.get(c) or "") for c in ("chemin", "legende")) if isinstance(x, dict) else str(x)


def _nomme(texte, mots):
    """Vrai si `texte` nomme l'un des `mots` (un identifiant ou un nom, en mot entier, casse et accents ignorés)."""
    propre = normaliser_mot(texte)
    for m in mots:
        m = normaliser_mot(str(m or "")).strip()
        if m and re.search(r"(?<![a-z0-9])" + re.escape(m) + r"(?![a-z0-9])", propre):
            return True
    return False


def _passages_de(texte, mots):
    """Les paragraphes (ou, à défaut, les lignes) de `texte` qui nomment l'élément ; vide si aucun ne le nomme (le
    texte d'un lot ne passe jamais pour celui d'un seul élément)."""
    blocs = [b for b in re.split(r"\n\s*\n", texte) if b.strip()]
    lignes = len(blocs) <= 1
    if lignes:
        blocs = [b for b in texte.splitlines() if b.strip()]
    # Les lignes retenues restent des lignes (un tableau Markdown ne se coupe pas), les paragraphes restent des paragraphes.
    return ("\n" if lignes else "\n\n").join(b.strip() for b in blocs if _nomme(b, mots))


def _sans_relecteur(projet):
    """Aucun agent relecteur : une étape du flux (un contrôle, des tests, le plus souvent) tient lieu de relecture."""
    agents = _etat(projet)["agents"]
    return not (any(a["role"] == ROLE_RELECTURE for a in agents) or _metier_tenu(projet, agents, ROLE_RELECTURE))


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
    barrieres, cache = None, {}
    for t in court["taches"]:
        etape = str(t.get("etape") or "")
        if (not t.get("agent") or t["id"] in etat["en_cours"] or t["id"] in relancees
                or not (etape.startswith(ETAPES_DE_FLUX) or etape in ETAPES_DU_MOTEUR)):
            continue
        if fiche_cloud(court, t["agent"]):
            continue      # sa session cloud vit encore : la boucle la retrouve et la relève
        refus = None
        if not t["active"]:
            refus = _refus_sans_suite(projet, t)      # un message refusé par l'outil, perdu, la tâche muette
            if not refus:
                continue
        barrieres = barrieres or _barrieres(projet, court)
        if not _amont_pret(projet, etat, t, court, barrieres, cache):
            # l'amont attend le Directeur : la tâche ne repart pas ; rendue inactive, elle repartira par le départ
            # ordinaire une fois l'amont prêt (et son agent n'est plus tenu)
            if t["active"]:
                lancer(projet, "tache", {"id": t["id"], "active": False, "journal": [
                    "Le moteur a repris : l'agent avait disparu ; la tâche attend une validation en amont."]})
            continue
        relancees.add(t["id"])
        ids = [t["id"]]
        if isinstance(t.get("lot"), dict):
            reste = [x for x in court["taches"] if isinstance(x.get("lot"), dict) and x["lot"]["id"] == t["lot"]["id"]
                     and x["lot"]["rang"] > t["lot"]["rang"] and x["colonne"] != "fait"]
            ids += [x["id"] for x in sorted(reste, key=lambda x: x["lot"]["rang"])]
        par_id = {x["id"]: x for x in court["taches"]}
        modele = _modele_de_depart(projet, court, t["agent"], t)
        matiere = (chr(10) * 2).join(_matiere(projet, etat, par_id[i]) for i in ids)
        depart = {"agent": t["agent"], "taches": ids, "matiere": matiere, "modele": modele,
                  "lot": (t.get("lot") or {}).get("id")}
        if refus:
            actions += _relancer_apres_refus(projet, etat, depart, refus)
            continue
        lancer(projet, "tache", {"id": t["id"], "journal": ["Le moteur a repris : l'agent avait disparu, nouvel essai."]})
        etat["departs"][ids[0]] = depart
        etat["en_cours"].add(ids[0])
        actions.append(a_agent(t["agent"], ids, matiere))
    return actions


def _refus_sans_suite(projet, t):
    """La raison du dernier refus de l'outil sur le message d'un agent, quand la tâche attend toujours (inactive, agent
    attribué, ni faite ni bloquée) et que l'agent n'a rien dit depuis. `None` sinon."""
    if t["colonne"] == "fait" or t.get("bloquee"):
        return None
    refus = [j for j in _tache(projet, t["id"]).get("journal") or [] if j["texte"].startswith(f"{JOURNAL_REFUS} (message)")]
    if not refus or not t.get("fonctionnalite"):
        return None
    dernier = max(refus, key=lambda j: j["t"])
    depuis = [m for m in _fonc(projet, t["fonctionnalite"]).get("discussion") or []
              if m["auteur"] == t["agent"] and m["t"] >= dernier["t"]]
    if depuis:
        return None
    return dernier["texte"].split(" : ", 1)[-1]


def avancer(projet, etat):
    """Ce que le parcours demande à chaque étape : rien en pause (les demandes, elles, sont traitées). Ce que la charge
    retient est noté dans `etat["attente_charge"]`, refait à chaque passage."""
    court = _etat(projet)
    etat.pop("attente_charge", None)
    etat.pop("attente_validation", None)
    if court["pause"]:
        return []
    actions = []
    for f in court["fonctionnalites"]:
        if f["etape"] in ("cadrage", "cahier") and f["attend_reponse"]:
            actions += _repondre_cadrage(projet, etat, f["id"])
        elif f["etape"] == "prototype" and f["attend_reponse"]:
            actions += _rejouer_le_retour(projet, etat, f["id"])
        elif f["etape"] == "serie":
            actions += _avancer_serie(projet, etat, f["id"])
    actions += _demarrer_en_attente(projet, etat, None)
    if not projet.pause_globale:
        _noter_les_places_libres(projet, etat)
    return actions


def _avancer_serie(projet, etat, fid):
    """Les éléments de la série : au plus deux en cours, dans l'ordre de la file et selon leurs dépendances ; la
    fonctionnalité est terminée quand la file est vide et que tous les éléments sont faits ou laissés de côté."""
    f = _fonc(projet, fid)
    revoir = _a_decision(f, "methode_a_revoir")
    elements = _m(etat, "elements")
    for d in _etat(projet)["decisions"]:     # le moteur relancé : les éléments qui attendent le Directeur reviennent
        if d["portee"] == "projet" and d["genre"] == GENRE_VALIDATION and d.get("fonctionnalite") == fid:
            _element_en_validation(projet, etat, d)
    if not revoir:      # le moteur relancé : les autres éléments repartent de là où le suivi les montre
        reprendre_la_serie(projet, etat, fid)
    mine = [v for v in elements.values() if v["fid"] == fid]
    if not revoir:
        for v in mine:
            if v["phase"] == "attente_methode":   # la méthode a été revue : l'élément repart de son premier pas
                v.update(phase="flux", pas=0, corrections=0, tour=0, taches=[], points=[])
                _tache_de_flux(projet, etat, v)
        court = _etat(projet)
        fac = _factory(projet)
        _, retenues = _barrieres(projet, court, fac)
        # Au travail : ni en attente du Directeur, ni retenu par une barrière (sinon l'élément suivant, qui doit lui-même
        # arriver à la validation, ne partirait jamais). Autant d'éléments que de places, deux au moins.
        vivants = sum(1 for v in mine if v["phase"] in ("flux", "relecture", "correction")
                      and not (v["taches"] and v["taches"][-1] in retenues))
        plafond = max(ELEMENTS_EN_COURS_MAX, _places(projet, court, fac)["total"])
        fait = {v["element"]["id"] for v in mine if v["phase"] == "fait"}
        deps = _m(etat, "depend_de").get(fid, {})
        while vivants < plafond:
            file = _fonc(projet, fid)["file"]
            ids = {q["id"] for q in file}
            choisi = next((q for q in file if all(d in fait or d not in ids for d in deps.get(q["id"], []))), None)
            if choisi is None:
                break
            element = lancer(projet, "file-prendre", {"fonctionnalite": fid, "element": choisi["id"]})["element"]
            _tache_de_flux(projet, etat, _etat_element(etat, fid, element))
            vivants += 1
        mine = [v for v in elements.values() if v["fid"] == fid]
        ouvertes = any(t.get("fonctionnalite") == fid and t["colonne"] != "fait" and not t.get("bloquee")
                       for t in _etat(projet)["taches"])
        if (not _fonc(projet, fid)["file"] and mine and all(v["phase"] in ("fait", "bloque") for v in mine)
                and not ouvertes and not _m(etat, "serie_perdue").get(fid)):
            bloques = [v["element"]["nom"] for v in mine if v["phase"] == "bloque"]
            _fin_de_fonctionnalite(projet, etat, fid, bloques)
            _dire(projet, fid, "La série est terminée." + (f" Éléments laissés de côté : {', '.join(bloques)}."
                                                           if bloques else ""))
            return []
    _signaler_une_serie_muette(projet, etat, fid)
    return []


# --- La série reprise depuis le suivi : la mémoire du moteur (`etat["elements"]`) est perdue à chaque redémarrage, et
# les agents détachés finissent pendant qu'il est arrêté. Chaque élément repart de là où ses tâches le montrent.

TITRE_RETOUR_ELEMENT = "Retour sur l'élément"      # le titre de la correction d'un élément fini (`_sur_retour_element`)
SERIE_ARRETEE = "serie_arretee"                    # la décision de projet : une série qui ne progresse plus
RELANCER_SERIE = "relancer"


def _numero(tid):
    n = re.sub(r"\D", "", str(tid))
    return int(n) if n else 0


def _pas_de_serie(t):
    """Vrai si la tâche est un pas de la série de son élément : une étape du flux ou une validation, une correction, une
    relecture, ou la correction d'un élément fini. Un retour sur une tâche (« Retour : … ») ou une demande n'en est pas un :
    il ne dit pas où en est l'élément."""
    e = str(t.get("etape") or "")
    return (e.startswith((ETAPES_DE_FLUX, ETAPES_DE_VALIDATION)) or e in ("correction", "relecture")
            or (e == "retour" and str(t.get("titre") or "").startswith(TITRE_RETOUR_ELEMENT)))


def reprendre_la_serie(projet, etat, fid):
    """Les éléments de la fonctionnalité en série que la mémoire du moteur ne connaît pas (il a été relancé) : chacun est
    reconstruit depuis ses tâches et repart de là où il en est, sans rien refaire. Une étape faite dont la suite n'a
    jamais été créée (le rapport est arrivé pendant l'arrêt) est suivie maintenant. Un élément qui ne peut pas repartir
    est noté dans `etat["serie_perdue"]` (dit au bureau par `_signaler_une_serie_muette`)."""
    f = lancer(projet, "detail", {"fonctionnalite": fid, "taches": True})
    if f.get("etape") != "serie":
        return
    elements, perdus = _m(etat, "elements"), _m(etat, "serie_perdue").setdefault(fid, {})
    dans_la_file = {q["id"] for q in f.get("file") or []}
    a_reprendre = [eid for eid in f.get("elements") or {} if f"{fid}/{eid}" not in elements and eid not in dans_la_file]
    if not a_reprendre:
        return
    par_element = {}
    for t in f.get("taches") or []:
        if t.get("element"):
            par_element.setdefault(t["element"], []).append(t)
    for eid in a_reprendre:
        if eid not in par_element:
            continue      # jamais commencé (un ancien découpage) : rien à reprendre
        connu = f["elements"][eid]
        element = {"id": eid, **(connu if isinstance(connu, dict) else {})}
        element.setdefault("nom", eid)
        raison = _reprendre_l_element(projet, etat, f, element, sorted(par_element[eid], key=lambda t: _numero(t["id"])))
        if raison:
            perdus[eid] = f"« {element['nom']} » : {raison}"
        else:
            perdus.pop(eid, None)


def _reprendre_l_element(projet, etat, f, element, taches):
    """L'état d'un élément d'après ses tâches (dans l'ordre de création) ; la suite d'une étape faite est lancée. Rend la
    raison pour laquelle il ne peut pas repartir, ou `None`."""
    fid = f["id"]
    rangs = {s["id"]: k for k, s in enumerate(_production(projet, fid))}
    pas = [t for t in taches if _pas_de_serie(t)]
    if not pas:
        if any(str(t.get("etape")) == "prototype" for t in taches) or all(t["colonne"] == "fait" for t in taches):
            _etat_element(etat, fid, element)["phase"] = "fait"     # l'élément du prototype, fait avec la méthode
        return None       # sinon une tâche à part, encore ouverte : il sera repris quand elle sera faite
    etapes = [str(t["etape"]).split(":", 1)[1] for t in pas
              if str(t["etape"]).startswith((ETAPES_DE_FLUX, ETAPES_DE_VALIDATION))]
    if etapes and etapes[-1] not in rangs:
        return f"son étape « {etapes[-1]} » n'est plus dans le workflow de la fonctionnalité"
    v = _etat_element(etat, fid, element)
    v.update(taches=[t["id"] for t in pas], pas=rangs[etapes[-1]] if etapes else 0)
    dernier = pas[-1]
    etape, ouverte = str(dernier["etape"]), dernier["colonne"] != "fait"
    texte = str(dernier.get("dernier_journal") or "")
    if etape.startswith(ETAPES_DE_FLUX):
        v["phase"] = "flux"
        if not ouverte:      # faite, sa suite jamais créée : elle l'est maintenant (le rapport, relu dans le suivi)
            _rapport_du_suivi(projet, etat, v, dernier, f)
            _apres_flux(projet, etat, v)
    elif etape.startswith(ETAPES_DE_VALIDATION):
        if ouverte:
            v["phase"] = "bloque" if dernier.get("bloquee") else "validation"
        elif texte.startswith("Renvoyé"):
            v.update(phase="flux", pas=v["pas"] - 1)
            remarque = texte.split(":", 1)[-1].strip() if ":" in texte else texte
            _tache_de_flux(projet, etat, v, journal=[f"Remarque du Directeur : {remarque}"])
        else:
            v["phase"] = "flux"
            note = texte.split("Note du Directeur :", 1)[1].strip() if "Note du Directeur :" in texte else ""
            if note:
                v["journal_suivant"] = [f"Note du Directeur à la validation « {element['nom']} » : {note}"]
            _apres_flux(projet, etat, v)
    elif etape == "relecture":
        suite = []
        for t in reversed(pas):
            if str(t["etape"]) != "relecture":
                break
            suite.append(t)
        faites = [t for t in suite if t["colonne"] == "fait"]
        v.update(phase="relecture", attendus=len(suite) if ouverte else 1, rapports=[[] for _ in faites])
        if not ouverte:      # les verdicts sont perdus : rien n'a été refusé que l'on sache
            v["rapports"] = [[]]
            _conclure_relecture(projet, etat, v)
    else:       # une correction (ou la correction d'un élément fini)
        v.update(phase="correction", corrections=1)
        if not ouverte:
            _lancer_relecture(projet, etat, v)
    return None


def _rapport_du_suivi(projet, etat, v, t, f):
    """Le rapport d'une étape faite pendant l'arrêt du moteur, relu dans le suivi : le compte rendu (le journal de la
    tâche, celui de la tête du lot pour ses autres tâches) et les fichiers rangés pour l'élément à cette étape. Marqué
    `rapport_du_suivi` : la validation qui suit est posée avec ce qu'il y a à vérifier (rien n'est refait pour ce que
    le rapport perdu disait en plus)."""
    eid = v["element"]["id"]
    texte = str(t.get("dernier_journal") or "")
    lot = t.get("lot") if isinstance(t.get("lot"), dict) else None
    if lot and lot.get("rang", 1) > 1:
        tete = next((x for x in f.get("taches") or [] if isinstance(x.get("lot"), dict)
                     and x["lot"].get("id") == lot.get("id") and x["lot"].get("rang") == 1), None)
        texte = str((tete or {}).get("dernier_journal") or texte)
    if texte.startswith(("Le moteur a repris", JOURNAL_REFUS, "Reprise sur")) or texte == "Terminé.":
        texte = ""
    fichiers = []
    for d in f.get("documents") or []:
        if (d.get("element") == eid and d.get("etape") == t["etape"]) or (d.get("tache") == t["id"] and not d.get("element")):
            if all(x["chemin"] != d["chemin"] for x in fichiers):
                fichiers.append({"chemin": d["chemin"], "titre": d.get("titre") or d["chemin"].rsplit("/", 1)[-1]})
    v["dernier_rapport"] = {"compte_rendu": texte[:COMPTE_RENDU_MAX], "fichiers": fichiers[-FICHIERS_MAX:], "points": [],
                            "acces": None}
    v["rapport_du_suivi"] = True


def _signaler_une_serie_muette(projet, etat, fid):
    """Le garde-fou : une fonctionnalité en série sans aucune tâche ouverte, ni décision, ni agent au travail ne progresse
    plus ; elle est dite au bureau de direction (décision `serie_arretee`), jamais laissée muette."""
    f = _fonc(projet, fid)
    if f.get("etape") != "serie":
        return
    court = _etat(projet)
    if any(d["genre"] == SERIE_ARRETEE and d.get("fonctionnalite") == fid for d in court["decisions"]):
        return        # déjà dite
    raisons = list(_m(etat, "serie_perdue").get(fid, {}).values())
    siennes = [t for t in court["taches"] if t.get("fonctionnalite") == fid]
    # un élément qui ne peut pas repartir est dit tout de suite, même si d'autres avancent ; sinon, seulement quand
    # plus rien ne bouge (ni tâche ouverte, ni décision, ni agent au travail)
    if not raisons and (f.get("decisions") or any(t["colonne"] != "fait" for t in siennes)
                        or any(t["id"] in etat["en_cours"] for t in siennes)
                        or any(d["portee"] == "projet" and d.get("fonctionnalite") == fid for d in court["decisions"])):
        return
    occupes = {t.get("element") for t in siennes if t["colonne"] != "fait"}
    for v in _m(etat, "elements").values():
        if v["fid"] == fid and v["phase"] not in ("fait", "bloque") and v["element"]["id"] not in occupes:
            raisons.append(f"« {v['element']['nom']} » attend sans aucune tâche ({v['phase']})")
    if f.get("file") and not occupes:
        raisons.append(f"{len(f['file'])} élément(s) restent dans la file sans pouvoir partir (dépendances)")
    if not raisons:
        raisons.append("aucun élément n'est en cours et la série n'est pas finie")
    texte = (f"La série de « {f['nom']} » ne progresse plus : " + " ; ".join(raisons)
             + ". « Relancer la série » la relit depuis le suivi ; sinon, envoyez un retour sur la tâche concernée.")
    lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": SERIE_ARRETEE, "fonctionnalite": fid,
                                "texte": texte[:2000]})


def _sur_serie_arretee(projet, demande, etat):
    """« Relancer la série » : la décision est levée et la série est relue depuis le suivi au passage suivant."""
    d = next((x for x in _etat(projet)["decisions"] if x["id"] == demande.get("decision")
              and x["genre"] == SERIE_ARRETEE), None)
    if d is None:
        raise Refus("cette décision n'existe plus")
    if demande.get("verdict") != RELANCER_SERIE:
        raise Refus(f"réponse inconnue : {demande.get('verdict')}")
    fid = d["fonctionnalite"]
    lancer(projet, "decision", {"action": "lever", "id": d["id"]})
    elements = _m(etat, "elements")
    for cle in [c for c, v in elements.items() if v["fid"] == fid and v["phase"] not in ("fait", "bloque")]:
        del elements[cle]
    _m(etat, "serie_perdue").pop(fid, None)
    _terminer(projet, {"demande": demande["id"]}, "La série est relue depuis le suivi : chaque élément repart de là où "
                                                  "il en est.")
    return []


# --- La fin d'une fonctionnalité : annoncée au Directeur (« Fonctionnalités terminées »), avec ses liens d'accès.

LIVRABLES_A_LA_FIN = 10


def _fin_de_fonctionnalite(projet, etat, fid, bloques=()):
    """L'étape passe à « terminee » et la fin est notée pour le bureau de direction (`fin`, non bloquante, fermée par
    « Vu ») : les livrables déclarés de la fonctionnalité (téléchargeables), le dernier lien d'accès d'un site rendu par
    ses éléments, les éléments laissés de côté. Le coût se lit au bureau (`/api/couts`)."""
    f = _fonc(projet, fid)
    livrables = []
    for d in reversed(f.get("documents") or []):
        if d.get("livrable") is True and all(x["chemin"] != d["chemin"] for x in livrables):
            livrables.append({"chemin": d["chemin"], "titre": d.get("titre") or d["chemin"].rsplit("/", 1)[-1]})
    acces = None
    for v in _m(etat, "elements").values():
        a = (v.get("dernier_rapport") or {}).get("acces") if v["fid"] == fid else None
        if a and rel.acces_ok(a):
            acces = a
    fin = {"livrables": list(reversed(livrables[:LIVRABLES_A_LA_FIN]))}
    if acces:
        fin["acces"] = {k: acces[k] for k in ("url", "description") if acces.get(k)}
    if bloques:
        fin["laisses"] = list(bloques)
    lancer(projet, "fonctionnalite", {"id": fid, "etape": "terminee", "fin": fin})


def _sur_fin_vue(projet, demande, etat):
    """« Vu » sur l'avis de fin d'une fonctionnalité : l'avis se ferme, la fonctionnalité reste terminée."""
    lancer(projet, "fonctionnalite", {"id": demande["fonctionnalite"], "fin_vue": True})
    _terminer(projet, {"demande": demande["id"]}, "C'est noté.")
    return []


_SUR[SERIE_ARRETEE] = _sur_serie_arretee
_SUR["fin_vue"] = _sur_fin_vue


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
    connues = {s["id"] for s in _production(projet, fid) if wf.est_validation(s)}
    elements = []
    for x in o["elements"]:       # les validations qui le concernent : seulement des étapes de validation du flux
        x = dict(x)
        if "validations" in x:
            x["validations"] = [v for v in x["validations"] if v in connues]
        elements.append(x)
    lancer(projet, "file", {"fonctionnalite": fid, "elements": elements})
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
    actions = _retoucher_prototype(projet, etat, fid, o["consigne"])     # d'abord : un refus ne dit pas « transmis »
    _terminer(projet, ctx, "J'ai transmis votre retour à l'agent du prototype.")
    return actions


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
    reprendre_la_serie(projet, etat, fid)
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
