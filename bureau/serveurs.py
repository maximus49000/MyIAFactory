"""Les serveurs distants et leurs capacités vus du bureau : lecture des fichiers, tâches de fond (sonde, installation).

Colle mince au-dessus de `outils/serveur_*.py`. Les lectures ne se connectent jamais à un serveur (elles relisent
`serveurs.json` et `serveurs-etat.json`) ; la sonde et l'installation tournent dans un fil, un seul à la fois, et ne font
jamais tomber le bureau. Aucun message d'erreur d'un fil n'est montré sans masquage des secrets connus.
"""
import json
import re
import sys
import threading
from pathlib import Path

from . import plateforme as modplateforme

DOSSIER = None   # None : voir `dossier()` ; remplacé dans les essais
MAX_ACTIONS = 20
STATUTS_PRESENTS = ("presente", "fait")
_ROUTE = re.compile(r"/api/serveurs(?:/([^/]+)/(sonder|apercu|installer))?")
DELAI_APERCU_S = 150
MAX_APERCUS = 2
LIGNE_CLE_MAX = 4096


class Occupe(Exception):
    """Trop d'aperçus en même temps."""


def _sans_doublon(paires):
    objet = {}
    for k, v in paires:
        if k in objet:
            raise ValueError("clé dupliquée")
        objet[k] = v
    return objet


def lire_json(octets):
    """Le JSON d'un corps de demande ; `ValueError` s'il est illisible ou répète une clé (à n'importe quel niveau)."""
    return json.loads(octets.decode("utf-8"), object_pairs_hook=_sans_doublon)


def _modules():
    """Les modules de `outils` (à plat : le dossier doit être sur le chemin)."""
    modplateforme._modules()
    import plateforme_acces
    import serveur_capacites
    import serveur_etat
    import serveur_installation
    import serveur_modele
    return plateforme_acces, serveur_capacites, serveur_etat, serveur_installation, serveur_modele


def _recommandation():
    _modules()
    import serveur_recommandation
    return serveur_recommandation


def dossier():
    """`DOSSIER`, sinon le dossier de la plateforme (`MYIAFACTORY_PLATEFORME` dans les essais), sinon le dossier des secrets."""
    return Path(DOSSIER) if DOSSIER else modplateforme.dossier()


def _secrets(d, serveurs):
    acces = _modules()[0]
    chemins = [str(s.cle) for s in serveurs if len(str(getattr(s, "cle", "") or "")) >= 8]   # un chemin, pas une lettre
    return modplateforme._secrets(d, acces) + chemins


def _masquer(valeur, secrets):
    acces = _modules()[0]
    return modplateforme._masquer(valeur, secrets, acces)


def _statut(entree):
    return entree.get("statut") if isinstance(entree, dict) and isinstance(entree.get("statut"), str) else "inconnue"


def _capacites(etat_serveur):
    """{capacité: statut} d'après l'état lu ; toute capacité du catalogue jamais constatée est « inconnue »."""
    catalogue = _modules()[1].CATALOGUE
    brut = etat_serveur.get("capacites") if isinstance(etat_serveur, dict) else None
    brut = brut if isinstance(brut, dict) else {}
    return {i: _statut(brut.get(i)) for i in catalogue}


def _ligne_cle_existante(d, serveur):
    """La ligne publique si la clé dédiée existe déjà (jamais de génération) ; sinon None."""
    try:
        publique = Path(str(Path(d) / serveur.cle) + ".pub")
        with open(publique, "rb") as f:
            return f.read(LIGNE_CLE_MAX).decode("utf-8", "replace").strip() or None
    except OSError:
        return None


def _decrire(serveur, capacites, en_cours, ligne):
    return {"id": serveur.id, "nom": serveur.nom, "hote": serveur.hote, "utilisateur": serveur.utilisateur,
            "fournisseur": serveur.fournisseur, "capacites": capacites, "installation_en_cours": en_cours,
            "ligne_cle_publique": ligne}


class Travaux:
    """Une tâche de fond à la fois (sonde ou installation), tous serveurs confondus : `lancer` rend faux si une tourne déjà.

    `ssh`, `installer` et `runner` s'injectent dans les essais (jamais de vraie connexion ni de vrai `ssh-keygen`)."""

    def __init__(self, ssh=None, installer=None, runner=None):
        self._ssh, self._installer, self._runner = ssh, installer, runner
        self._verrou = threading.Lock()
        self._fil = None
        self._cible = None          # (genre, id du serveur) de la tâche en cours
        self.erreurs = {}           # id du serveur -> message de la dernière tâche interrompue
        self._places_apercu = threading.BoundedSemaphore(MAX_APERCUS)

    def _options_ssh(self):
        return {} if self._ssh is None else {"ssh": self._ssh}

    def en_cours(self, genre=None, serveur_id=None):
        with self._verrou:
            if self._fil is None or not self._fil.is_alive() or self._cible is None:
                return False
            return (genre in (None, self._cible[0])) and (serveur_id in (None, self._cible[1]))

    def attendre(self, delai=10):
        fil = self._fil
        if fil is not None:
            fil.join(delai)

    def lancer(self, genre, serveur, travail):
        with self._verrou:
            if self._fil is not None and self._fil.is_alive():
                return False
            self.erreurs.pop(serveur.id, None)   # l'erreur de la tâche précédente ne survit pas à une nouvelle
            self._cible = (genre, serveur.id)
            self._fil = threading.Thread(target=self._courir, args=(serveur, travail), daemon=True)
            self._fil.start()
            return True

    def _courir(self, serveur, travail):
        ErreurInstallation = _modules()[3].ErreurInstallation
        try:
            erreur = travail()
        except ErreurInstallation as e:
            erreur = f"{e} {e.geste}".strip()
        except BaseException as e:   # jamais un fil qui meurt avec un message qui pourrait citer un secret
            erreur = f"Opération interrompue ({type(e).__name__}) ; l'état affiché est le dernier connu."
            print(erreur, file=sys.stderr)
        if erreur:
            self.erreurs[serveur.id] = str(erreur)

    # -- les tâches ---------------------------------------------------------
    def sonder(self, serveur, d):
        _, _, etat_mod, inst, _ = _modules()[:5]

        def travail():
            etat = etat_mod.sonder(serveur, **self._options_ssh())
            inst.enregistrer_sonde(d, serveur, etat)
            if all(s == "inconnue" for s in etat.values()):
                return "Serveur injoignable : l'état de ses capacités est inconnu."
            return None
        return self.lancer("sonder", serveur, travail)

    def installer(self, serveur, actions, d):
        installer = self._installer or _modules()[3].installer

        def travail():
            r = installer(serveur, actions, True, dossier=d, **self._options_ssh())
            return r.get("erreur") if isinstance(r, dict) else None
        return self.lancer("installer", serveur, travail)

    def apercu(self, serveur, actions, d, delai=None):
        """L'aperçu (lecture SSH seulement), borné dans le temps : `None` si le délai est dépassé. `ErreurInstallation` remonte.
        `Occupe` si deux aperçus tournent déjà (un fil dépassé garde sa place jusqu'à sa fin)."""
        delai = DELAI_APERCU_S if delai is None else delai
        sortie = {}
        if not self._places_apercu.acquire(blocking=False):
            raise Occupe()

        def courir():
            try:
                sortie["r"] = _modules()[3].apercu(serveur, actions, dossier=d, **self._options_ssh())
            except BaseException as e:
                sortie["e"] = e
            finally:
                self._places_apercu.release()
        fil = threading.Thread(target=courir, daemon=True)
        try:
            fil.start()
        except BaseException:
            self._places_apercu.release()
            raise
        fil.join(delai)
        if fil.is_alive():
            return None
        if "e" in sortie:
            raise sortie["e"]
        return sortie["r"]


# ---------------------------------------------------------------- lectures (fichiers seulement)

def lire(travaux, d=None):
    """`{"serveurs": [...], "rejets": [...]}` ; jamais de connexion, jamais d'exception, aucun secret."""
    modeles, installation = _modules()[4], _modules()[3]
    d = Path(d) if d else dossier()
    serveurs, rejets = modeles.lire_avec_rejets(d)
    etat = installation.lire_etat_vivant(d)
    secrets = _secrets(d, serveurs)
    connus = {s.id for s in serveurs}
    for ident in [i for i in list(travaux.erreurs) if i not in connus]:
        travaux.erreurs.pop(ident, None)      # un serveur qui n'est plus déclaré ne garde pas d'erreur
    sortie = []
    for s in serveurs:
        e = etat.get(s.id, {})
        inst = e.get("installation") if isinstance(e, dict) else None
        en_cours = (isinstance(inst, dict) and inst.get("en_cours") is True) or travaux.en_cours("installer", s.id)
        fiche = _decrire(s, _capacites(e), bool(en_cours), _ligne_cle_existante(d, s))
        if travaux.erreurs.get(s.id):
            fiche["erreur"] = _masquer(travaux.erreurs[s.id], secrets)
        sortie.append(fiche)
    return _masquer({"serveurs": sortie, "rejets": list(rejets)}, secrets)


def _lieu(d, serveurs, etat, action):
    """Le serveur peut-il faire `action` ? D'après l'état lu seulement ; jamais permis sans capacité constatée présente."""
    capacites = _modules()[1]
    try:
        requises = capacites.manquantes_pour([action], set())
    except ValueError:
        return {"permis": False, "manque": [], "raison": f"Action inconnue : « {action} »."}
    if not serveurs:
        return {"permis": False, "manque": [], "raison": "Aucun serveur déclaré."}
    meilleur = None
    muet = None     # serveur jamais sondé ou injoignable : aucune action, même sans capacité requise, n'y est permise
    for s in serveurs:
        caps = _capacites(etat.get(s.id, {}))
        manque = [i for i in requises if caps.get(i) not in STATUTS_PRESENTS]
        if not manque:
            if all(v == "inconnue" for v in caps.values()):
                muet = muet or s
                continue
            return {"permis": True, "manque": [], "raison": "", "serveur_id": s.id}
        if meilleur is None or len(manque) < len(meilleur[1]):
            meilleur = (s, manque, caps)
    if meilleur is None:
        return {"permis": False, "manque": [], "serveur_id": muet.id, "raison": "Serveur jamais sondé ou injoignable"}
    s, manque, caps = meilleur
    morceaux = []
    for i in manque:
        cap = capacites.CATALOGUE[i]
        note = f"{caps.get(i)}" + ("" if cap.installable else ", non installable automatiquement")
        morceaux.append(f"{i} ({note})")
    return {"permis": False, "manque": manque, "serveur_id": s.id,
            "raison": f"Capacités manquantes sur « {s.nom} » : " + ", ".join(morceaux) + "."}


def _nombre_01(valeur):
    return min(1.0, max(0.0, float(valeur))) if isinstance(valeur, (int, float)) and not isinstance(valeur, bool) else None


def _charge_serveur(etat, serveur_id):
    """La charge (0 à 1) que la sonde a rangée dans l'état du serveur, ou None si elle n'y est pas ou est illisible."""
    brut = etat.get(serveur_id, {}).get("charge") if isinstance(etat.get(serveur_id), dict) else None
    if not isinstance(brut, dict):
        return None
    par_coeur, libre = _nombre_01(brut.get("charge_par_coeur")), _nombre_01(brut.get("memoire_libre_ratio"))
    mesures = [m for m in (par_coeur, None if libre is None else 1.0 - libre) if m is not None]
    return max(mesures) if mesures else None


def mesures_pour(action, serveurs, etat, serveur_id=None):
    """Les mesures dont dispose la recommandation. SEUL point de branchement des durées par lieu, de la charge du poste et du
    quota GitHub (consommation du bureau) : tant qu'ils ne sont pas câblés ils valent None et la recommandation retombe sur
    les règles. Ne lit que l'état déjà lu : jamais de réseau."""
    joignable = any(not all(v == "inconnue" for v in _capacites(etat.get(s.id, {})).values()) for s in serveurs)
    return _recommandation().Mesures(duree_min={}, charge_poste=None, quota_github_restant=None, serveur_joignable=joignable,
                                     charge_serveur=_charge_serveur(etat, serveur_id) if serveur_id else None)


def _conseil(d, serveurs, etat, action):
    """{lieu: fiche} : la fiche du serveur garde les champs de `_lieu` ; chaque lieu gagne `niveau` et `fondee_sur`."""
    serveur = _lieu(d, serveurs, etat, action)
    connue = not serveur.get("raison", "").startswith("Action inconnue")
    permis = {"poste": connue, "github": connue, "serveur": serveur["permis"] is True}   # poste et github : pas encore modélisés
    conseil = _recommandation().recommander(action, permis, mesures_pour(action, serveurs, etat, serveur.get("serveur_id")))
    sortie = {}
    for lieu, c in conseil.items():
        fiche = dict(serveur) if lieu == "serveur" else {"permis": permis[lieu], "raison": ""}
        fiche["niveau"], fiche["fondee_sur"] = c["niveau"], c["fondee_sur"]
        if not fiche.get("raison"):
            fiche["raison"] = c["raison"]
        sortie[lieu] = fiche
    return sortie


def lieux(actions_brutes, d=None):
    """(code, objet) de `GET /api/serveurs/lieux?actions=a,b` : `{action: {lieu: {permis, raison, niveau, fondee_sur}}}`.

    Le conseil (`niveau`) n'est qu'un avis : rien n'est jamais déplacé automatiquement."""
    d = Path(d) if d else dossier()
    actions = []
    for a in (actions_brutes or "").split(","):
        a = a.strip()
        if a and a not in actions:
            actions.append(a)
    if not actions or len(actions) > MAX_ACTIONS or any(len(a) > 40 for a in actions):
        return 400, {"erreur": "Indiquez entre 1 et 20 actions séparées par des virgules."}
    serveurs, _ = _modules()[4].lire_avec_rejets(d)
    etat = _modules()[3].lire_etat_vivant(d)
    return 200, _masquer({a: _conseil(d, serveurs, etat, a) for a in actions}, _secrets(d, serveurs))


# ---------------------------------------------------------------- routes POST

def route_post(chemin):
    """`("declarer", None)` ou `(action, id)` pour un chemin de ces routes ; `None` sinon."""
    m = _ROUTE.fullmatch(chemin)
    if not m:
        return None
    return (m.group(2), m.group(1)) if m.group(1) else ("declarer", None)


def taille_max(cible):
    return 2048 if cible[0] == "declarer" else 1024


def _actions(corps):
    """La liste d'actions du corps, ou `None` si elle est invalide."""
    a = corps.get("actions")
    if not isinstance(a, list) or not a or len(a) > MAX_ACTIONS or not all(isinstance(x, str) and len(x) <= 40 for x in a):
        return None
    return a


def poster(travaux, cible, corps, d=None):
    """(code, objet) d'une demande POST déjà contrôlée (en-têtes, taille, JSON objet)."""
    d = Path(d) if d else dossier()
    genre, ident = cible
    plateforme_acces, capacites, _etat, installation, modeles = _modules()
    if genre == "declarer":
        champs = {k: corps.get(k) for k in ("nom", "hote", "utilisateur", "fournisseur")}   # rien d'autre n'est pris
        try:
            serveur = modeles.ajouter(champs, d)
        except ValueError as e:
            return 400, {"erreur": _masquer(str(e), _secrets(d, []))}
        try:
            ligne = modeles.ligne_cle_publique(d, serveur, **({"runner": travaux._runner} if travaux._runner else {}))
            avertissement = None
        except Exception:
            ligne, avertissement = None, "Le serveur est déclaré, mais la clé SSH n'a pas pu être créée : relancez la déclaration."
        fiche = _decrire(serveur, _capacites({}), False, ligne)
        if avertissement:
            fiche["avertissement"] = avertissement
        return 201, _masquer({"serveur": fiche}, _secrets(d, [serveur]))
    serveurs, _ = modeles.lire_avec_rejets(d)
    serveur = next((s for s in serveurs if s.id == ident), None)    # l'identifiant ne sert qu'à retrouver un serveur connu
    if serveur is None:
        return 404, {"erreur": "Serveur inconnu."}
    if genre == "sonder":
        if travaux.en_cours() or installation.installation_en_cours(d):
            return 409, {"erreur": "Une opération est déjà en cours."}
        if not travaux.sonder(serveur, d):
            return 409, {"erreur": "Une opération est déjà en cours."}
        return 202, {"demarre": True}
    actions = _actions(corps)
    if actions is None:
        return 400, {"erreur": "Indiquez les actions voulues (liste de noms, 20 au plus)."}
    try:
        capacites.manquantes_pour(actions, set())
    except ValueError as e:
        return 400, {"erreur": str(e)}
    if genre == "apercu":
        try:
            resultat = travaux.apercu(serveur, actions, d)
        except Occupe:
            return 409, {"erreur": "Deux aperçus sont déjà en cours : réessayez dans un instant."}
        except installation.ErreurInstallation as e:
            return 400, {"erreur": _masquer(str(e), _secrets(d, [serveur]))}
        except Exception as e:
            print(f"Aperçu interrompu ({type(e).__name__}).", file=sys.stderr)
            return 500, {"erreur": "L'aperçu a échoué : réessayez."}
        if resultat is None:
            return 504, {"erreur": "L'aperçu prend trop de temps : réessayez."}
        return 200, _masquer(resultat, _secrets(d, [serveur]))
    # installer : l'accord est vérifié ICI, avant tout fil de fond
    if corps.get("accord") is not True:
        return 400, {"erreur": "Installation refusée : l'accord n'a pas été donné."}
    if travaux.en_cours() or installation.installation_en_cours(d):
        return 409, {"erreur": "Une installation est déjà en cours."}
    if not travaux.installer(serveur, actions, d):
        return 409, {"erreur": "Une installation est déjà en cours."}
    return 202, {"demarre": True}
