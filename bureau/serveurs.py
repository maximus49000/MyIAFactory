"""Les serveurs distants et leurs capacités vus du bureau : lecture des fichiers, tâches de fond (sonde, installation).

Colle mince au-dessus de `outils/serveur_*.py`. Les lectures ne se connectent jamais à un serveur (elles relisent
`serveurs.json` et `serveurs-etat.json`) ; la sonde et l'installation tournent dans un fil, un seul à la fois, et ne font
jamais tomber le bureau. Aucun message d'erreur d'un fil n'est montré sans masquage des secrets connus.
"""
import json
import math
import re
import sys
import threading
import time
from pathlib import Path

from . import plateforme as modplateforme
from .deport_types import SERVIES_AU_SERVEUR

DOSSIER = None   # None : voir `dossier()` ; remplacé dans les essais
MAX_ACTIONS = 20
STATUTS_PRESENTS = ("presente", "fait")
LIBELLES_STATUTS = {"presente": "présente", "fait": "faite", "absente": "absente", "inconnue": "inconnue", "bloque": "bloquée",
                    "a_faire": "à faire", "en_cours": "en cours"}
_ROUTE = re.compile(r"/api/serveurs(?:/([^/]+)/(sonder|apercu|installer))?")
DELAI_APERCU_S = 150
MAX_APERCUS = 2
AGE_MAX_CHARGE_S = 900   # une charge sondée il y a plus longtemps est ignorée
HORLOGE = time.time
LIGNE_CLE_MAX = 4096
_ROUTE_TACHE = re.compile(r"/api/serveurs/taches/([^/]+)/arreter")
MAX_TACHES = 100         # tâches rendues par `GET /api/serveurs/taches`
TEXTE_MAX = 80           # un texte de l'index (projet, serveur) rendu au plus à cette longueur
ERREUR_MAX = 300         # un message d'arrêt rendu au plus à cette longueur
CAPTURES_MAX = 9999
LIBELLES_ETATS_TACHE = {"en_attente": "en attente", "en_cours": "en cours", "terminee": "terminée", "echouee": "échouée",
                        "arretee": "arrêtée"}
ROUTES_MIGRATION = {"/api/serveurs/migration/apercu": "migration_apercu", "/api/serveurs/migration/confirmer": "migration_confirmer"}


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


def _migration():
    _modules()
    import serveur_migration
    return serveur_migration


def _recommandation():
    _modules()
    import serveur_recommandation
    return serveur_recommandation


def _tache():
    """Le moteur des tâches d'émulation (`serveur_tache`) : l'index local et l'arrêt ; l'import ne se connecte à rien."""
    _modules()
    import serveur_tache
    return serveur_tache


def _tache_cli():
    _modules()
    import serveur_tache_cli
    return serveur_tache_cli


def dossier():
    """`DOSSIER`, sinon le dossier de la plateforme (`MYIAFACTORY_PLATEFORME` dans les essais), sinon le dossier des secrets."""
    return Path(DOSSIER) if DOSSIER else modplateforme.dossier()


def declare(d=None):
    """Vrai si au moins un serveur est déclaré (`serveurs.json` : les fichiers seulement, aucune connexion) ; faux au
    moindre ennui."""
    try:
        return bool(_modules()[4].lire(dossier() if d is None else d))
    except Exception:
        return False


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


def _fiches_capacites(etat_serveur):
    """{capacité: {statut, detail, geste}} d'après l'état lu : ce que le moteur a constaté ou fait (statut `bloque`,
    `a_faire`, `en_cours`, `fait`, `presente`, `absente`, `inconnue`) avec sa raison et le geste proposé."""
    catalogue = _modules()[1].CATALOGUE
    brut = etat_serveur.get("capacites") if isinstance(etat_serveur, dict) else None
    brut = brut if isinstance(brut, dict) else {}
    sortie = {}
    for i in catalogue:
        e = brut.get(i)
        e = e if isinstance(e, dict) else {}
        sortie[i] = {"statut": _statut(e), **{k: e[k] if isinstance(e.get(k), str) else "" for k in ("detail", "geste")}}
    return sortie


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

    def __init__(self, ssh=None, installer=None, runner=None, tache=None):
        self._ssh, self._installer, self._runner, self._tache = ssh, installer, runner, tache
        self._verrou = threading.Lock()
        self._fil = None
        self._cible = None          # (genre, id du serveur) de la tâche en cours
        self.erreurs = {}           # id du serveur -> message de la dernière tâche interrompue
        self.erreurs_taches = {}    # id de la tâche d'émulation -> message de son dernier arrêt non confirmé
        self._places_apercu = threading.BoundedSemaphore(MAX_APERCUS)
        self._migrations = 0        # migrations (aperçu, confirmation) dont le fil tourne encore

    def _options_ssh(self):
        return {} if self._ssh is None else {"ssh": self._ssh}

    def en_cours(self, genre=None, serveur_id=None):
        with self._verrou:
            if self._migrations and genre is None:      # une migration (aperçu ou confirmation) tourne : tout est occupé
                return True
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

    def lancer_tache(self, ident, travail):
        """Comme `lancer`, pour l'arrêt d'une tâche d'émulation : même fil unique, l'erreur est rangée sous l'id de la tâche."""
        with self._verrou:
            if self._migrations or (self._fil is not None and self._fil.is_alive()):
                return False
            self.erreurs_taches.pop(ident, None)     # l'erreur de l'arrêt précédent ne survit pas à un nouvel appel
            self._cible = ("arreter_tache", ident)
            self._fil = threading.Thread(target=self._courir_tache, args=(ident, travail), daemon=True)
            self._fil.start()
            return True

    def _courir_tache(self, ident, travail):
        try:
            erreur = travail()
        except BaseException as e:   # le type seulement : jamais un message qui pourrait citer un secret
            erreur = f"Arrêt interrompu ({type(e).__name__}) ; l'état affiché est le dernier connu."
            print(erreur, file=sys.stderr)
        if erreur:
            self.erreurs_taches[ident] = str(erreur)

    def arreter_tache(self, ident, d):
        """Demande l'arrêt de la tâche `ident` (déjà validée et connue de l'index) dans le fil de fond : `arreter` fait foi de
        l'état, rappelé tant qu'il n'est pas final (3 fois au plus). Faux si une autre opération tourne."""
        moteur = self._tache or _tache()
        options = self._options_ssh()

        def travail():
            # Le même arrêt que la commande serveur-tache, sans réessayer un état « inconnu » (serveur muet : jusqu'à
            # 150 s par appel) : le fil unique du bureau n'est pas tenu des minutes, la raison est affichée.
            r = _tache_cli()._terminer(moteur, ident, False, d, options, reessayer_inconnu=False)
            if isinstance(r, dict) and r.get("etat") in moteur.FINAUX:
                return None
            r = r if isinstance(r, dict) else {}
            etat = LIBELLES_ETATS_TACHE.get(r.get("etat"), "inconnu")
            raison = " ".join(str(r.get("raison") or "").split())[:200]
            return f"L'arrêt n'est pas confirmé (état : {etat})." + (f" {raison}" if raison else "")
        return self.lancer_tache(ident, travail)

    # -- les tâches ---------------------------------------------------------
    def sonder(self, serveur, d):
        _, _, etat_mod, inst, _ = _modules()[:5]

        def travail():
            etat = etat_mod.sonder(serveur, **self._options_ssh())
            joint = not all(s == "inconnue" for s in etat.values())
            charge = etat_mod.charge(serveur, **self._options_ssh()) if joint else None     # lecture seule, hors verrou
            inst.enregistrer_sonde(d, serveur, etat, charge=charge)
            if not joint:
                return "Serveur injoignable : l'état de ses capacités est inconnu."
            return None
        return self.lancer("sonder", serveur, travail)

    def installer(self, serveur, actions, d):
        installer = self._installer or _modules()[3].installer

        def travail():
            r = installer(serveur, actions, True, dossier=d, **self._options_ssh())
            return r.get("erreur") if isinstance(r, dict) else None
        return self.lancer("installer", serveur, travail)

    def _borne(self, fonction, delai=None):
        """Exécute `fonction()` dans un fil borné dans le temps : `None` si le délai est dépassé, l'exception remonte.
        `Occupe` si deux opérations de ce genre tournent déjà (un fil dépassé garde sa place jusqu'à sa fin)."""
        delai = DELAI_APERCU_S if delai is None else delai
        sortie = {}
        if not self._places_apercu.acquire(blocking=False):
            raise Occupe()

        def courir():
            try:
                sortie["r"] = fonction()
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

    def apercu(self, serveur, actions, d, delai=None):
        """L'aperçu (lecture SSH seulement), borné dans le temps : `None` si le délai est dépassé. `ErreurInstallation` remonte.
        `Occupe` si deux aperçus tournent déjà."""
        return self._borne(lambda: _modules()[3].apercu(serveur, actions, dossier=d, **self._options_ssh()), delai)

    def migration(self, travail, delai=None):
        """Un travail de migration (sondes en lecture seule, ou confirmation), borné comme l'aperçu. Il compte comme une tâche
        en cours (`en_cours()`) jusqu'à la fin RÉELLE de son fil, même si l'appelant a abandonné l'attente (504)."""
        etat = {"demarre": False}
        with self._verrou:
            self._migrations += 1

        def suivi():
            etat["demarre"] = True
            try:
                return travail()
            finally:
                with self._verrou:
                    self._migrations -= 1
        try:
            return self._borne(suivi, delai)
        except BaseException:
            if not etat["demarre"]:            # refusé (Occupe) ou fil jamais parti : rien ne décomptera
                with self._verrou:
                    self._migrations -= 1
            raise

    def attendre_migration(self, delai=10):
        """Attend (essais) la fin des migrations en fond."""
        fin = time.time() + delai
        while time.time() < fin and self._migrations:
            time.sleep(0.01)


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
        fiche = _decrire(s, _fiches_capacites(e), bool(en_cours), _ligne_cle_existante(d, s))
        fiche["sonde_en_cours"] = bool(travaux.en_cours("sonder", s.id))
        if travaux.erreurs.get(s.id):
            fiche["erreur"] = _masquer(travaux.erreurs[s.id], secrets)
        sortie.append(fiche)
    return _masquer({"serveurs": sortie, "rejets": list(rejets)}, secrets)


def _texte_index(valeur, secrets, borne=TEXTE_MAX):
    """Un texte de l'index : masqué PUIS borné (jamais l'inverse : une coupe ne doit pas laisser un bout de secret)."""
    if not isinstance(valeur, str):
        return ""
    return _masquer(valeur, secrets)[:borne]


def _fiche_tache(ident, fiche, secrets, tache, maintenant):
    etat = fiche.get("etat") if fiche.get("etat") in tache.ETATS else "inconnu"
    debut = fiche.get("debut") if isinstance(fiche.get("debut"), str) and tache.MOTIF_ISO.fullmatch(fiche["debut"]) else None
    fin = fiche.get("fin") if isinstance(fiche.get("fin"), str) and tache.MOTIF_ISO.fullmatch(fiche["fin"]) else None
    duree = None
    if debut is not None:
        t0 = tache._epoch(debut)
        t1 = tache._epoch(fin) if fin is not None else (maintenant if etat == "en_cours" else None)
        if t0 is not None and t1 is not None and t1 >= t0:
            duree = int(t1 - t0)
    captures = fiche.get("captures_prises")
    captures = min(captures, CAPTURES_MAX) if isinstance(captures, int) and not isinstance(captures, bool) and captures > 0 else 0
    return {"id": ident, "etat": etat, "mode": fiche.get("mode") if fiche.get("mode") in tache.MODES else None,
            "projet": _texte_index(fiche.get("projet"), secrets), "serveur_id": _texte_index(fiche.get("serveur_id"), secrets),
            "debut": debut, "duree_s": duree, "captures": captures,
            "statut": fiche.get("statut") if fiche.get("statut") in tache.STATUTS_RAPPORT else None}


def lire_taches(travaux, d=None):
    """`{"taches": [...]}` : les 100 tâches les plus récentes de l'index LOCAL (`taches.json`) ; jamais de connexion, jamais
    d'exception, aucun secret. Une fiche de forme inattendue est tolérée ; une clé qui n'est pas un identifiant de tâche est ignorée."""
    d = Path(d) if d else dossier()
    tache = _tache()
    try:
        serveurs, _ = _modules()[4].lire_avec_rejets(d)
    except Exception:
        serveurs = []
    secrets = _secrets(d, serveurs)
    fiches = {i: f for i, f in tache.Index(d).lire().items() if isinstance(i, str) and tache.MOTIF_ID.fullmatch(i)}
    for ident in [i for i in list(travaux.erreurs_taches) if i not in fiches]:
        travaux.erreurs_taches.pop(ident, None)      # une tâche disparue de l'index ne garde pas d'erreur
    maintenant = HORLOGE()
    sortie = []
    for ident in sorted(fiches, reverse=True)[:MAX_TACHES]:       # tAAAAMMJJ-HHMMSS-xxxx : l'ordre des identifiants est celui du temps
        fiche = _fiche_tache(ident, fiches[ident], secrets, tache, maintenant)
        if travaux.en_cours("arreter_tache", ident):
            fiche["arret_en_cours"] = True       # l'écran grise « Arrêter » tant que l'arrêt demandé n'est pas fini
        if travaux.erreurs_taches.get(ident):
            fiche["erreur"] = _texte_index(travaux.erreurs_taches[ident], secrets, ERREUR_MAX)
        sortie.append(fiche)
    return {"taches": sortie}


def _proposition_publique(proposition):
    s = proposition["serveur"]
    return {"serveur": {"nom": s.nom, "hote": s.hote, "utilisateur": s.utilisateur, "fournisseur": s.fournisseur},
            "source": list(proposition["source"])}


def lire_migration(d=None):
    """`{"proposition": {...} | None}` d'après les fichiers seulement : jamais de connexion, aucun secret, aucune écriture."""
    d = Path(d) if d else dossier()
    try:
        proposition = _migration().detecter(d)
    except Exception:
        proposition = None
    return _masquer({"proposition": _proposition_publique(proposition) if proposition else None}, _secrets(d, []))


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
        note = LIBELLES_STATUTS.get(caps.get(i), "inconnue") + ("" if cap.installable else ", non installable automatiquement")
        morceaux.append(f"{i} ({note})")
    return {"permis": False, "manque": manque, "serveur_id": s.id,
            "raison": f"Capacités manquantes sur « {s.nom} » : " + ", ".join(morceaux) + "."}


def _nombre_01(valeur):
    """Un nombre de l'état ramené dans 0..1 ; None s'il n'est pas un nombre fini (NaN, infini, booléen, texte)."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    try:
        v = float(valeur)
    except OverflowError:
        return None
    return min(1.0, max(0.0, v)) if math.isfinite(v) else None


def _charge_serveur(etat, serveur_id, maintenant):
    """La charge (0 à 1) que la sonde a rangée dans l'état du serveur, ou None si elle n'y est pas ou est illisible."""
    brut = etat.get(serveur_id, {}).get("charge") if isinstance(etat.get(serveur_id), dict) else None
    if not isinstance(brut, dict):
        return None
    maj = brut.get("maj")
    if isinstance(maj, bool) or not isinstance(maj, (int, float)) or not math.isfinite(maj):
        return None
    if not -60 <= maintenant - maj <= AGE_MAX_CHARGE_S:         # trop vieille (ou datée du futur) : ignorée
        return None
    par_coeur, libre = _nombre_01(brut.get("charge_par_coeur")), _nombre_01(brut.get("memoire_libre_ratio"))
    mesures = [m for m in (par_coeur, None if libre is None else 1.0 - libre) if m is not None]
    return max(mesures) if mesures else None


def mesures_pour(action, serveurs, etat, serveur_id=None):
    """Les mesures dont dispose la recommandation. SEUL point de branchement des durées par lieu, de la charge du poste et du
    quota GitHub (consommation du bureau) : tant qu'ils ne sont pas câblés ils valent None et la recommandation retombe sur
    les règles. Ne lit que l'état déjà lu : jamais de réseau."""
    choisis = [s for s in serveurs if s.id == serveur_id]       # le serveur retenu pour l'action, pas « un serveur quelconque »
    joignable = any(not all(v == "inconnue" for v in _capacites(etat.get(s.id, {})).values()) for s in choisis)
    return _recommandation().Mesures(duree_min={}, charge_poste=None, quota_github_restant=None, serveur_joignable=joignable,
                                     charge_serveur=_charge_serveur(etat, serveur_id, HORLOGE()) if serveur_id else None)


def _action_connue(action):
    try:
        _modules()[1].manquantes_pour([action], set())
    except ValueError:
        return False
    return True


def _conseil(d, serveurs, etat, action):
    """{lieu: fiche} : la fiche du serveur garde les champs de `_lieu` ; chaque lieu gagne `niveau` et `fondee_sur`."""
    serveur = _lieu(d, serveurs, etat, action)
    connue = _action_connue(action)
    ailleurs = connue and action not in SERVIES_AU_SERVEUR          # une action servie au serveur seulement (recette)
    permis = {"poste": ailleurs, "github": ailleurs, "serveur": serveur["permis"] is True}   # poste et github : pas encore modélisés
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
    if chemin in ROUTES_MIGRATION:
        return ROUTES_MIGRATION[chemin], None
    t = _ROUTE_TACHE.fullmatch(chemin)
    if t:
        return "tache_arreter", t.group(1)
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


MSG_ARRET_EN_COURS = "Un arrêt de tâche d'émulation est en cours : réessayez à sa fin."


def poster(travaux, cible, corps, d=None):
    """(code, objet) d'une demande POST déjà contrôlée (en-têtes, taille, JSON objet)."""
    d = Path(d) if d else dossier()
    genre, ident = cible
    plateforme_acces, capacites, _etat, installation, modeles = _modules()
    if genre in ("migration_apercu", "migration_confirmer"):
        return _poster_migration(travaux, genre, corps, d)
    if genre == "tache_arreter":
        return _poster_tache(travaux, ident, d)

    def occupe(message):
        """409 : un arrêt de tâche qui tient le fil de fond est nommé comme tel (pas « une installation »)."""
        return 409, {"erreur": MSG_ARRET_EN_COURS if travaux.en_cours("arreter_tache") else message}
    if genre == "declarer":
        if travaux.en_cours() or installation.installation_en_cours(d):     # une sonde, une installation ou une migration tourne
            return occupe("Une opération est en cours : déclarez le serveur à sa fin.")
        champs = {k: corps.get(k) for k in ("nom", "hote", "utilisateur", "fournisseur")}   # rien d'autre n'est pris
        try:           # l'identifiant « migration » est réservé : `valider` le refuse avec un message clair (400)
            serveur = modeles.ajouter(champs, d)
        except ValueError as e:
            return 400, {"erreur": _masquer(str(e), _secrets(d, []))}
        try:
            ligne = modeles.ligne_cle_publique(d, serveur, **({"runner": travaux._runner} if travaux._runner else {}))
            avertissement = None
        except Exception:
            ligne, avertissement = None, "Le serveur est déclaré, mais la clé SSH n'a pas pu être créée : relancez la déclaration."
        fiche = _decrire(serveur, _fiches_capacites({}), False, ligne)
        if avertissement:
            fiche["avertissement"] = avertissement
        return 201, _masquer({"serveur": fiche}, _secrets(d, [serveur]))
    serveurs, _ = modeles.lire_avec_rejets(d)
    serveur = next((s for s in serveurs if s.id == ident), None)    # l'identifiant ne sert qu'à retrouver un serveur connu
    if serveur is None:
        return 404, {"erreur": "Serveur inconnu."}
    if genre == "sonder":
        if travaux.en_cours() or installation.installation_en_cours(d):
            return occupe("Une opération est déjà en cours.")
        if not travaux.sonder(serveur, d):
            return occupe("Une opération est déjà en cours.")
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
        return occupe("Une installation est déjà en cours.")
    if installation.plateforme_en_cours(d):
        return 409, {"erreur": "L'installation de la plateforme OVH est en cours : attendez sa fin avant d'installer sur ce serveur."}
    if not travaux.installer(serveur, actions, d):
        return occupe("Une installation est déjà en cours.")
    return 202, {"demarre": True}


def _poster_tache(travaux, ident, d):
    """Arrêt d'une tâche d'émulation : l'identifiant suit le motif des tâches ET se retrouve dans l'index local ; il ne sert
    jamais à construire un chemin. Le corps de la demande est ignoré."""
    tache = _tache()
    if not isinstance(ident, str) or not tache.MOTIF_ID.fullmatch(ident):
        return 404, {"erreur": "Tâche inconnue."}
    fiche = tache.Index(d).lire().get(ident)
    if not isinstance(fiche, dict):
        return 404, {"erreur": "Tâche inconnue."}
    if fiche.get("etat") in tache.FINAUX:
        return 409, {"erreur": "Cette tâche est déjà terminée."}
    if travaux.en_cours() or not travaux.arreter_tache(ident, d):
        return 409, {"erreur": "Une opération est déjà en cours : réessayez dans un instant."}
    return 202, {"demarre": True}


def _poster_migration(travaux, genre, corps, d):
    """Aperçu (sondes en lecture seule) et confirmation de la migration du serveur OVH existant."""
    migration = _migration()
    installation = _modules()[3]
    masque = _secrets(d, [])
    if genre == "migration_confirmer" and corps.get("accord") is not True:     # avant toute sonde, tout fil, toute écriture
        return 400, {"erreur": "Migration refusée : l'accord n'a pas été donné."}
    proposition = migration.detecter(d)
    if proposition is None:
        if genre == "migration_confirmer" and _modules()[4].lire_avec_rejets(d) != ([], []):
            return 409, {"erreur": "Un serveur est déjà déclaré : la migration n'a rien changé."}
        return 404, {"erreur": "Aucun serveur OVH à migrer."}
    options = travaux._options_ssh()
    if genre == "migration_apercu":
        travail = lambda: migration.apercu(proposition, **options)  # noqa: E731
    else:
        if travaux.en_cours() or installation.installation_en_cours(d):
            return 409, {"erreur": "Une opération est déjà en cours : réessayez à sa fin."}
        travail = lambda: migration.confirmer(proposition, True, d, **options)  # noqa: E731
    try:
        resultat = travaux.migration(travail)
    except Occupe:
        return 409, {"erreur": "Des sondes de migration sont déjà en cours : réessayez dans un instant."}
    except migration.ErreurMigration as e:
        return {"accord": 400, "illisible": 400, "deja": 409, "occupe": 409}.get(e.code, 400), {"erreur": _masquer(str(e), masque)}
    except Exception as e:
        print(f"Migration interrompue ({type(e).__name__}).", file=sys.stderr)
        return 500, {"erreur": "La migration a échoué : rien n'a été modifié ou relisez la liste des serveurs, puis réessayez."}
    if resultat is None:
        return 504, {"erreur": "La migration prend trop de temps : relisez la liste des serveurs avant de réessayer."}
    if genre == "migration_apercu":
        s = resultat["serveur"]
        return 200, _masquer({"serveur": {"nom": s.nom, "hote": s.hote, "utilisateur": s.utilisateur, "fournisseur": s.fournisseur},
                              "source": resultat["source"], "capacites": resultat["capacites"],
                              "joignable": resultat["joignable"]}, masque)
    etat = installation.lire_etat_vivant(d).get(resultat.id, {})
    fiche = _decrire(resultat, _fiches_capacites(etat), False, _ligne_cle_existante(d, resultat))
    return 200, _masquer({"serveur": fiche}, _secrets(d, [resultat]))
