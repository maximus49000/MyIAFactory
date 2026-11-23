"""Réglages d'un projet : lecture et écriture."""
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from .deport import LIEUX_PAR_DEFAUT, valider_lieux
from .deport_types import catalogue_union
from .registre import REGISTRE
from .releve import MOTIF_GENRE  # un id de projet suit le même motif qu'un genre
# Le verrou d'écriture d'un fichier partagé vit dans `verrou_fichier` (compatible Python 3.9 : le lanceur des agents
# l'importe aussi pour le sceau des tests) ; ses réglages d'attente s'y trouvent (`VERROU_ATTENTE_S`, `VERROU_PERIME_S`).
from .verrou_fichier import verrou_fichier as _verrou_fichier

DEFAUTS = {"port": 8770, "charge_max": 75, "fraicheur_min": 30, "releve": {}, "prix_automatiques": True,
           "moteur": {"couche": "claude"}, "agents_cloud_max": 3,
           # Vrai quand le Directeur a accordé le dossier du projet pour les sessions cloud : le moteur répond alors
           # lui-même « Yes, I trust this folder » à Claude Code (jamais sans cet accord).
           "cloud_dossier_approuve": False,
           # Vrai quand le Directeur laisse le moteur valider lui-même les leçons proposées, au niveau qu'elles proposent.
           "lecons_auto": False,
           # Vrai (par défaut) : le Chef analyse chaque blocage d'une tâche avant le Directeur (« Analyse intelligente
           # des blocages ») ; faux, le moteur fait comme avant, sans aucun appel de ce jugement.
           "analyse_blocages": True,
           # Vrai : la livraison (la construction de l'apk, 8 à 14 min) ne part pas toute seule quand les éléments sont
           # conformes ; elle attend « Livrer maintenant » (essai de coûts du 2026-11-19). Faux : comme avant.
           "livraison_sur_demande": False,
           # Vrai : chaque livrable téléchargeable terminé (apk, zip…) est publié en release GitHub privée du projet
           # (`installation.publication`) ; le projet doit être sur GitHub. Faux (par défaut) : rien n'est publié seul.
           "livraison_github": False,
           # Vrai : une évolution moyenne (cahier validé ensuite) n'a plus de session de tests et de revue à part ; la
           # programmation relit et teste elle-même (essai de coûts du 2026-11-19 : 0,12 à 0,17 € et 3 à 7 min de moins,
           # mais plus de regard neuf). Faux : comme avant.
           "une_session_moyenne": False,
           # Exécution déportée : lieu de chaque action (poste, github, serveur), commande de remplacement éventuelle
           # par action, heure de la campagne de charge. Les clés absentes valent ces défauts.
           "deport": {"lieux": dict(LIEUX_PAR_DEFAUT), "commandes": {}, "charge_heure": "03:00"}}
_HEURE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
COUCHES_MOTEUR = ("claude", "api")   # `claude -p` (l'abonnement) ou l'API Messages (clé facturée à part)
AGENTS_CLOUD_MAX = (1, 16)
AGENTS_ABONNEMENT_MAX = (1, 32)   # le plafond des tâches d'agent actives sur l'abonnement, tous projets et tous lieux


class ReglagesInvalides(Exception):
    pass


def charger(chemin):
    chemin = Path(chemin)
    r = json.loads(json.dumps(DEFAUTS))
    if chemin.exists():
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
        if not isinstance(donnees, dict):
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : un objet JSON est attendu")
        r.update(donnees)
    _verifier_moteur(r)
    r["dossier"] = str(chemin.parent)
    return r


def _verifier_moteur(r):
    """Les réglages du moteur : `moteur.couche` vaut claude ou api ; `agents_cloud_max` va de 1 à 16."""
    m = r.get("moteur")
    if not isinstance(m, dict) or m.get("couche", "claude") not in COUCHES_MOTEUR:
        raise ReglagesInvalides("Réglages : « moteur.couche » doit valoir « claude » ou « api ».")
    n = r.get("agents_cloud_max")
    if type(n) is not int or not AGENTS_CLOUD_MAX[0] <= n <= AGENTS_CLOUD_MAX[1]:
        raise ReglagesInvalides("Réglages : « agents_cloud_max » doit être un entier de 1 à 16.")
    if type(r.get("cloud_dossier_approuve")) is not bool:
        raise ReglagesInvalides("Réglages : « cloud_dossier_approuve » doit valoir true ou false.")
    if type(r.get("lecons_auto")) is not bool:
        raise ReglagesInvalides("Réglages : « lecons_auto » doit valoir true ou false.")
    if type(r.get("analyse_blocages")) is not bool:
        raise ReglagesInvalides("Réglages : « analyse_blocages » doit valoir true ou false.")
    if type(r.get("livraison_sur_demande")) is not bool:
        raise ReglagesInvalides("Réglages : « livraison_sur_demande » doit valoir true ou false.")
    if type(r.get("livraison_github")) is not bool:
        raise ReglagesInvalides("Réglages : « livraison_github » doit valoir true ou false.")
    if type(r.get("une_session_moyenne")) is not bool:
        raise ReglagesInvalides("Réglages : « une_session_moyenne » doit valoir true ou false.")
    r["deport"] = normaliser_deport(r.get("deport"), "Réglages")


def normaliser_deport(v, contexte="Réglages", catalogue=None):
    """Valide la clé `deport` et la rend complète : lieux manquants au défaut (poste), commandes vides, charge 03:00.
    Lieux et commandes sont validés contre le catalogue d'actions du projet ; sans catalogue (réglage du bureau, qui
    n'a pas de projet), toute action connue d'un type quelconque est admise et seuls les noms inconnus sont refusés.
    Lève ReglagesInvalides (message en français) si une valeur est mauvaise."""
    if catalogue is None:
        catalogue = catalogue_union()
    if not isinstance(v, dict):
        raise ReglagesInvalides(f"{contexte} : « deport » doit être un objet {{lieux, commandes, charge_heure}}.")
    lieux = v.get("lieux", {})
    try:
        lieux = valider_lieux(lieux, catalogue=catalogue)
    except ValueError as e:
        raise ReglagesInvalides(f"{contexte} : « deport.lieux » : {e}")
    commandes = v.get("commandes", {})
    if not isinstance(commandes, dict) or not all(isinstance(c, str) for c in commandes.values()):
        raise ReglagesInvalides(f"{contexte} : « deport.commandes » doit associer une action connue à une "
                                "commande (texte).")
    for k in commandes:
        if k not in catalogue:
            raise ReglagesInvalides(f"{contexte} : « deport.commandes » : l'action « {k} » n'existe pas pour ce "
                                    "type de projet." if k in catalogue_union() else
                                    f"{contexte} : « deport.commandes » doit associer une action connue à une "
                                    "commande (texte).")
    heure = v.get("charge_heure", DEFAUTS["deport"]["charge_heure"])
    if not isinstance(heure, str) or not _HEURE.match(heure):
        raise ReglagesInvalides(f"{contexte} : « deport.charge_heure » doit être une heure HH:MM (00:00 à 23:59).")
    return {"lieux": {**LIEUX_PAR_DEFAUT, **lieux}, "commandes": dict(commandes), "charge_heure": heure}


MAX_PROJETS = 12


def _id_par_defaut(chemin):
    """Le nom du dossier des réglages (son parent pour `.factory`), ramené à `[a-z0-9-]`."""
    dossier = chemin.parent
    if dossier.name == ".factory":
        dossier = dossier.parent
    texte = unicodedata.normalize("NFKD", dossier.name).encode("ascii", "ignore").decode("ascii").lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")
    return texte[:40].rstrip("-") or "projet"


def lire_bureau(chemin):
    """Le fichier du bureau : `{"port"?: 8770, "projets": [chemin | {"chemin", "id"?}]}` (1 à 12 projets,
    chemins relatifs à ce fichier). Rend `{"port": int, "projets": [{"id", "chemin": Path}]}`."""
    chemin = Path(chemin)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as e:
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : {e}")
    if not isinstance(donnees, dict):
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : un objet JSON est attendu")
    port = donnees.get("port", DEFAUTS["port"])
    if type(port) is not int or not 0 <= port <= 65535:
        raise ReglagesInvalides("Fichier du bureau : « port » doit être un entier entre 0 et 65535.")
    projets = donnees.get("projets")
    if not isinstance(projets, list) or not 1 <= len(projets) <= MAX_PROJETS:
        raise ReglagesInvalides(f"Fichier du bureau : « projets » doit lister de 1 à {MAX_PROJETS} "
                                "fichiers de réglages.")
    entrees = []
    for i, p in enumerate(projets):
        id_ = None
        if isinstance(p, dict):
            id_ = p.get("id")
            p = p.get("chemin")
            if id_ is not None and (not isinstance(id_, str) or not MOTIF_GENRE.match(id_)):
                raise ReglagesInvalides(f"Fichier du bureau : projets[{i}].id invalide (lettres minuscules, "
                                        "chiffres et tirets, 40 caractères au plus).")
        if not isinstance(p, str) or not p.strip() or "\x00" in p:
            raise ReglagesInvalides(f"Fichier du bureau : projets[{i}] doit donner le chemin d'un fichier "
                                    "de réglages.")
        c = chemin.parent / p
        if not c.is_file():  # une faute de frappe ne doit pas créer un projet fantôme
            raise ReglagesInvalides(f"Fichier du bureau : projets[{i}] : fichier de réglages introuvable ({c}).")
        entrees.append((id_, c))
    dossiers = [c.resolve().parent for _, c in entrees]
    if len(dossiers) != len(set(dossiers)):  # le bureau écrit ses historiques à côté des réglages
        raise ReglagesInvalides("Fichier du bureau : deux projets ont leurs réglages dans le même dossier.")
    donnes = [i for i, _ in entrees if i is not None]
    if len(donnes) != len(set(donnes)):
        raise ReglagesInvalides("Fichier du bureau : deux projets portent le même id.")
    pris = set(donnes)
    sortie = []
    for id_, c in entrees:
        if id_ is None:
            base = _id_par_defaut(c)
            id_, n = base, 1
            while id_ in pris:
                n += 1
                suffixe = f"-{n}"
                id_ = base[:40 - len(suffixe)].rstrip("-") + suffixe
            pris.add(id_)
        sortie.append({"id": id_, "chemin": c})
    plafond = donnees.get("agents_abonnement_max")
    if "agents_abonnement_max" in donnees and (type(plafond) is not int or not
                                                AGENTS_ABONNEMENT_MAX[0] <= plafond <= AGENTS_ABONNEMENT_MAX[1]):
        raise ReglagesInvalides("Fichier du bureau : « agents_abonnement_max » doit être un entier de 1 à 32 (ou absent).")
    deport = normaliser_deport(donnees.get("deport", {}), "Fichier du bureau")
    # les niveaux de la page Réglages se lisent avec tolérance (conception, risques : valeur inconnue = défaut) : une
    # clé écrite à la main ou par une version plus récente est écartée et dite, jamais un bureau ou un moteur arrêté
    ignores = []
    return {"port": port, "projets": sortie, "acces": lire_acces(donnees.get("acces", {})),
            "agents_abonnement_max": plafond,
            "moteur": lire_moteur_du_bureau(donnees.get("moteur", {})),
            "deport": deport,
            # les lieux tels qu'écrits dans le fichier, sans les défauts : ce que la résolution à trois niveaux lit
            "deport_lieux_explicites": dict(donnees.get("deport", {}).get("lieux", {})),
            "reglages": _lire_reglages_du_niveau(donnees.get("reglages"), "reglages", ignores),
            "types": _lire_types_du_bureau(donnees.get("types"), ignores),
            "ignores": ignores}


def _lire_reglages_du_niveau(v, nom, ignores):
    """Les réglages posés à un niveau (global ou type) : `{id: valeur}` ; un id absent du registre est écarté, et
    dit dans `ignores` (les écrivains, eux, le refusent)."""
    if v is None:
        return {}
    if not isinstance(v, dict):
        ignores.append(f"Fichier du bureau : « {nom} » ignoré : un objet {{réglage: valeur}} est attendu.")
        return {}
    connus = {r.id for r in REGISTRE}
    for id_ in v:
        if id_ not in connus:
            ignores.append(f"Fichier du bureau : « {nom} » : le réglage inconnu « {id_} » est ignoré.")
    return {k: x for k, x in v.items() if k in connus}


def _lire_types_du_bureau(v, ignores):
    """`types` : `{genre: {"reglages": {...}, "deport": {"lieux": {...}}}}`. Un genre, un niveau ou un lieu abîmé est
    écarté (dit dans `ignores`) ; le reste est gardé. Les lieux gardés sont ceux que le bureau accepte."""
    if v is None:
        return {}
    if not isinstance(v, dict):
        ignores.append("Fichier du bureau : « types » ignoré : un objet {genre: réglages} est attendu.")
        return {}
    sortie = {}
    for genre, niveau in v.items():
        if not MOTIF_GENRE.match(genre):
            ignores.append(f"Fichier du bureau : « types » : genre « {genre} » invalide (lettres minuscules, "
                           "chiffres et tirets), ignoré.")
            continue
        if not isinstance(niveau, dict):
            ignores.append(f"Fichier du bureau : « types.{genre} » ignoré : un objet est attendu.")
            continue
        entree = dict(niveau)
        entree["reglages"] = _lire_reglages_du_niveau(niveau.get("reglages"), f"types.{genre}.reglages", ignores)
        if "deport" in niveau:
            d = niveau["deport"]
            if not isinstance(d, dict):
                ignores.append(f"Fichier du bureau : « types.{genre}.deport » ignoré : un objet est attendu.")
                del entree["deport"]
            else:
                lieux = d.get("lieux", {})
                if not isinstance(lieux, dict):
                    ignores.append(f"Fichier du bureau : « types.{genre}.deport.lieux » ignoré : un objet "
                                   "{action: lieu} est attendu.")
                    lieux = {}
                gardes = {}
                for action, lieu in lieux.items():
                    try:
                        valider_lieux({action: lieu}, catalogue=catalogue_union())
                    except ValueError as e:
                        ignores.append(f"Fichier du bureau : « types.{genre}.deport.lieux » : {e} Ignoré.")
                        continue
                    gardes[action] = lieu
                entree["deport"] = {**d, "lieux": gardes}
        sortie[genre] = entree
    return sortie


def lire_moteur_du_bureau(v):
    """La couche des appels faits avant qu'un projet n'existe (l'échange de la création) : `{"couche": claude | api}`,
    `claude` par défaut ; une clé absente vaut le défaut."""
    if not isinstance(v, dict) or v.get("couche", "claude") not in COUCHES_MOTEUR:
        raise ReglagesInvalides("Fichier du bureau : « moteur.couche » doit valoir « claude » ou « api ».")
    return {"couche": v.get("couche", "claude")}


ACCES = ("tailscale", "reseau_local")


def lire_acces(v):
    """Les accès distants du bureau : `{"tailscale": bool, "reseau_local": bool}` (une clé absente vaut faux)."""
    if not isinstance(v, dict) or not all(k in ACCES and isinstance(x, bool) for k, x in v.items()):
        raise ReglagesInvalides("Fichier du bureau : « acces » doit valoir {\"tailscale\": vrai ou faux, "
                                "\"reseau_local\": vrai ou faux}.")
    return {k: v.get(k, False) for k in ACCES}


def fixer_charge_max(chemin, valeur):
    if type(valeur) is not int or not 30 <= valeur <= 95:
        raise ValueError("La charge maximum doit être un entier entre 30 et 95.")
    return _ecrire_cle(chemin, "charge_max", valeur)


def fixer_lecons_auto(chemin, valeur):
    """Note si le moteur valide lui-même les leçons proposées (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« lecons_auto » doit valoir true ou false.")
    return _ecrire_cle(chemin, "lecons_auto", valeur)


def fixer_deport(chemin, deport, catalogue=None):
    """Note le déport du projet (lieux, commandes, heure de charge) : validé avant d'écrire, ReglagesInvalides sinon.
    Seuls les lieux explicitement donnés sont écrits (jamais ceux complétés par défaut : le projet hérite du bureau
    pour les autres). `catalogue` : les actions du type du projet. Rend les réglages rechargés."""
    complet = normaliser_deport(deport, "Réglages", catalogue)
    explicites = {a: complet["lieux"][a] for a in deport.get("lieux", {})}
    return _ecrire_cle(chemin, "deport", {**complet, "lieux": explicites})




def fixer_agents_abonnement_max(chemin, valeur):
    """Note, dans le fichier du bureau, le plafond des agents actifs sur l'abonnement (entier de 1 à 32 ; `None` : plus de
    plafond, la clé disparaît). Le reste du fichier est gardé (relu SOUS VERROU : une autre écriture du fichier du bureau
    n'est jamais perdue). Rend la valeur écrite."""
    if valeur is not None and (type(valeur) is not int or not AGENTS_ABONNEMENT_MAX[0] <= valeur <= AGENTS_ABONNEMENT_MAX[1]):
        raise ValueError("« agents_abonnement_max » doit être un entier de 1 à 32 (ou nul : aucun plafond).")
    def poser(donnees):
        if valeur is None:
            donnees.pop("agents_abonnement_max", None)
        else:
            donnees["agents_abonnement_max"] = valeur
        return valeur
    return _modifier_bureau(chemin, poser)


def _modifier_bureau(chemin, fonction):
    """Réécrit le fichier du bureau : sous verrou, relit le contenu, le passe à `fonction(donnees)` (qui le modifie sur
    place et rend la valeur de retour), puis écrit de façon atomique. Rend ce que rend `fonction`."""
    chemin = Path(chemin)
    try:
        with _verrou_fichier(chemin):
            try:
                donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError) as e:
                raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : {e}")
            if not isinstance(donnees, dict):
                raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : un objet JSON est attendu")
            retour = fonction(donnees)
            _ecrire_fichier(chemin, donnees)
            return retour
    except TimeoutError as e:
        raise ReglagesInvalides(str(e)) from None


def fixer_niveau_bureau(chemin_bureau, chemin_cle, valeur):
    """Pose `valeur` au chemin imbriqué `chemin_cle` du fichier du bureau (ex. `("deport", "lieux", "tests")`,
    `("types", "android", "reglages", "lecons_auto")`) ; `None` supprime la clé et élague les objets laissés vides.
    Le fichier est relu sous verrou : le reste est gardé. Rend `valeur`."""
    chemin_cle = tuple(chemin_cle)
    if not chemin_cle:
        raise ValueError("Le chemin de la clé du bureau est vide.")

    def poser(donnees):
        if valeur is None:
            pile = [donnees]
            for c in chemin_cle[:-1]:
                suivant = pile[-1].get(c)
                if not isinstance(suivant, dict):
                    return None   # rien à effacer
                pile.append(suivant)
            if chemin_cle[-1] not in pile[-1]:
                return None
            del pile[-1][chemin_cle[-1]]
            for i in range(len(pile) - 1, 0, -1):   # élague les objets vidés, jamais la racine
                if pile[i]:
                    break
                del pile[i - 1][chemin_cle[i - 1]]
            return None
        courant = donnees
        for c in chemin_cle[:-1]:
            suivant = courant.setdefault(c, {})
            if not isinstance(suivant, dict):
                raise ReglagesInvalides(f"Fichier du bureau : « {c} » n'est pas un objet.")
            courant = suivant
        courant[chemin_cle[-1]] = valeur
        return valeur
    return _modifier_bureau(chemin_bureau, poser)


def effacer_cle(chemin_projet, cle):
    """Retire la clé à plat `cle` des réglages du projet (le projet retombe sur le type, le global ou le défaut).
    Écriture atomique ; rend les réglages rechargés."""
    chemin = Path(chemin_projet)
    if chemin.exists():
        try:
            with _verrou_fichier(chemin):
                try:
                    donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
                except (ValueError, OSError) as e:
                    raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
                if isinstance(donnees, dict) and cle in donnees:
                    del donnees[cle]
                    _ecrire_fichier(chemin, donnees)
        except TimeoutError as e:
            raise ReglagesInvalides(str(e)) from None
    return charger(chemin)


def fixer_analyse_blocages(chemin, valeur):
    """Note si le Chef analyse les blocages avant le Directeur (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« analyse_blocages » doit valoir true ou false.")
    return _ecrire_cle(chemin, "analyse_blocages", valeur)


def fixer_livraison_sur_demande(chemin, valeur):
    """Note si la livraison attend le clic « Livrer maintenant » (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« livraison_sur_demande » doit valoir true ou false.")
    return _ecrire_cle(chemin, "livraison_sur_demande", valeur)


def fixer_livraison_github(chemin, valeur):
    """Note si les livrables terminés sont publiés seuls en releases GitHub (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« livraison_github » doit valoir true ou false.")
    return _ecrire_cle(chemin, "livraison_github", valeur)


def fixer_une_session_moyenne(chemin, valeur):
    """Note si une évolution moyenne se fait en une seule session, sans tests ni revue à part (vrai ou faux)."""
    if type(valeur) is not bool:
        raise ValueError("« une_session_moyenne » doit valoir true ou false.")
    return _ecrire_cle(chemin, "une_session_moyenne", valeur)


def fixer_cloud_dossier_approuve(chemin, valeur):
    """Note si le Directeur accorde le dossier du projet pour les sessions cloud (vrai ou faux, rien d'autre)."""
    if type(valeur) is not bool:
        raise ValueError("« cloud_dossier_approuve » doit valoir true ou false.")
    return _ecrire_cle(chemin, "cloud_dossier_approuve", valeur)


def _ecrire_cle(chemin, cle, valeur):
    """Pose la clé à plat `cle` : relue et réécrite SOUS VERROU (une autre écriture du même fichier n'est pas perdue)."""
    chemin = Path(chemin)
    try:
        with _verrou_fichier(chemin):
            donnees = {}
            if chemin.exists():
                try:
                    donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
                except (ValueError, OSError) as e:
                    raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
            donnees[cle] = valeur
            _ecrire_fichier(chemin, donnees)
    except TimeoutError as e:
        raise ReglagesInvalides(str(e)) from None
    return charger(chemin)


def _ecrire_fichier(chemin, donnees):
    """Écriture atomique (fichier temporaire voisin puis remplacement)."""
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
