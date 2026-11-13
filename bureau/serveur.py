"""Serveur local : la page, l'état, la charge, le conseil, le réglage de charge et la facturation."""
import argparse
import hashlib
import html
import http.client
import json
import mimetypes
import os
import re
import shutil
import threading
import time
from datetime import datetime
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import abonnement as modabonnement
from . import acces, attente, catalogue, charge, conso, cout, creations, demandes, demarrage, equipe, etat, kpi, lancement as lancement_, prix, reglages
from . import fichiers_joints, releve, statuts
from . import semaines as modsemaines
from . import sujets as modsujets
from .usage import HistoriqueUsage
from moteur import detache

WEB = Path(__file__).resolve().parent / "web"
DELAI_ETAT_S = 2.0
PAS_SONDE_S = 5
PAS_HISTORIQUE_S = 60
PAS_PRIX_S = 3600  # le fil des prix se réveille toutes les heures ; il ne lit les sources qu'une fois par jour
ATTENTE_PREMIERS_PRIX_S = 25
MAX_CORPS_DEMANDE = 60 * 1024 * 1024  # 40 Mo de fichiers joints en base64 (voir `fichiers_joints`), plus le texte
MAX_CORPS_REGLAGES = 4096
MAX_CORPS_CREATIONS = 64 * 1024   # la description et les réponses de l'échange avec le chef
ROUTES_CREATIONS = {f"/api/creations/{n}": n for n in ("infos", "tour", "valider", "supprimer")}
MAX_LOT = 50 # leçons au plus dans un « Tout valider »
DEMARRAGE_S = 90  # après « Lancer l'orchestrateur », un second clic ne relance rien pendant 90 s
GARDE_DOUBLON_S = 10  # une même fonctionnalité ou un même message envoyé deux fois de suite : une seule demande
GARDE_CHALLENGE_S = 120  # un challenge envoyé mais pas encore au relevé : pas de second envoi sur sa cible
TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".glb": "model/gltf-binary", ".svg": "image/svg+xml",
         ".webmanifest": "application/manifest+json; charset=utf-8", ".png": "image/png"}
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
IMAGE_MAX_OCTETS = 20 * 1024 * 1024
LANCEMENT = Path("~/MyIAFactory/lancement.json")  # le drapeau du premier lancement, hors de tout dépôt
ROUTES_PROJET = ("/api/couts", "/api/document", "/api/methode", "/api/etat", "/api/charge", "/api/conseil", "/api/facturation", "/api/kpi", "/api/image",
                 "/api/catalogue", "/api/livrable", "/api/telecharger")
# La fenêtre de validation : le téléchargement d'un livrable (toujours en pièce jointe) et le relais vers le site en cours.
# Les décisions qui n'ont qu'une réponse (valider une étape, élargir un genre) : une deuxième réponse est refusée (409)
# pendant ce délai, le temps que le moteur traite la première et que le relevé la retire.
REPONSES_UNE_FOIS = ("valider_etape", "elargir_genre", "outil_agent", "accord_agent", "serie_arretee", "faire_chez_partenaire",
                     "fable_tache", "decoupage_lieux")
GARDE_REPONSE_S = 600
TELECHARGEMENT_MAX_OCTETS =500 * 1024 * 1024   # un apk ou un installeur ; au-delà : 413
LECTURE_TEXTE = (".md", ".txt")           # lus dans la page (`/api/telecharger?lecture=1`), en texte brut isolé
LECTURE_TEXTE_MAX_OCTETS = 512 * 1024    # au-delà : 413, le téléchargement reste
TELECHARGEABLES = {ext: (type_, True) for ext, type_ in releve.TELECHARGEABLES.items()}
# Les fichiers joints à une discussion (gif, webp, json en plus) : pièce jointe, sauf ce que la page lit en ligne.
TELECHARGEABLES_JOINTS = {**{ext: (t[0], True) for ext, t in fichiers_joints.TYPES.items()}, **TELECHARGEABLES}
LECTURE_MEDIAS = tuple(e for e in fichiers_joints.EXTENSIONS_EN_LIGNE if e not in LECTURE_TEXTE)   # image animée, vidéo, son
APERCU = "/apercu/"                     # /apercu/<projet>/<décision>/<chemin> -> http://127.0.0.1:<port>/<chemin>
APERCU_FIN = "fin-"                     # /apercu/<projet>/fin-<fonctionnalité>/… : le site d'une fonctionnalité terminée
APERCU_DELAI_S = 20
APERCU_MAX_CORPS = 10 * 1024 * 1024     # un formulaire envoyé au site
APERCU_MAX_REPONSE = 200 * 1024 * 1024
APERCU_METHODES = ("GET", "HEAD", "POST")
# En-têtes transmis : rien qui identifie le bureau (ni cookie, ni Origin, ni X-Bureau), pas de compression (le
# relais ne décode rien) ; du site, rien qui pose un cookie ou une politique sur l'origine du bureau.
APERCU_ENTETES_REQUETE = ("Accept", "Accept-Language", "Content-Type", "User-Agent", "If-None-Match",
                          "If-Modified-Since", "Range")
APERCU_ENTETES_REPONSE = ("content-type", "content-length", "content-range", "accept-ranges", "last-modified", "etag",
                          "content-disposition", "content-language", "location")
# Le dernier livrable : extensions servies, type, et s'il part en pièce jointe. `.html` et `.txt` sont servis
# en bac à sable (aucun script, aucune requête au nom du bureau).
LIVRABLES = {".png": ("image/png", False), ".jpg": ("image/jpeg", False), ".jpeg": ("image/jpeg", False),
             ".pdf": ("application/pdf", False), ".zip": ("application/zip", True),
             ".glb": ("model/gltf-binary", True), ".html": ("text/html; charset=utf-8", False),
             ".txt": ("text/plain; charset=utf-8", False)}
BAC_A_SABLE = (".html", ".txt")
# Les documents d'une fonctionnalité : ceux d'un livrable, plus les textes et le SVG produits par les agents. Tout ce qui
# pourrait contenir un script est servi en bac à sable (un SVG ouvert seul exécuterait le sien sans cela).
DOCUMENTS = {**LIVRABLES, ".md": ("text/plain; charset=utf-8", False), ".json": ("text/plain; charset=utf-8", False),
             ".csv": ("text/plain; charset=utf-8", False), ".svg": ("image/svg+xml", False)}
BAC_A_SABLE_DOCUMENTS = BAC_A_SABLE + (".md", ".json", ".csv", ".svg")
METHODES = {".md": ("text/plain; charset=utf-8", False), ".txt": ("text/plain; charset=utf-8", False)}
# Le bureau ouvert au téléphone : le cookie posé par l'association, la page servie sans lui.
COOKIE_ACCES = "myiafactory_acces"
DUREE_COOKIE_S = 31536000
NOMS_ACCES = {"tailscale": "Tailscale", "reseau_local": "Wi-Fi de la maison (non chiffré)"}
PAGE_401 = ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            "content=\"width=device-width, initial-scale=1\"><title>Le bureau vivant</title></head><body "
            "style=\"font-family:sans-serif;padding:2em;text-align:center\"><h1>Accès protégé</h1><p>Scannez le QR "
            "code affiché sur l'ordinateur (« Associer un téléphone »).</p></body></html>").encode("utf-8")
# Le lien du QR code montre un bouton ; seul le bouton (un POST depuis cette page) consomme le code. Un aperçu du lien
# (appareil photo, messagerie) ne le gâche pas, et le cookie `SameSite=Strict` revient bien à la redirection.
PAGE_ASSOCIER = ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
                 "content=\"width=device-width, initial-scale=1\"><title>Le bureau vivant</title></head><body "
                 "style=\"font-family:sans-serif;padding:2em;text-align:center\"><h1>Associer ce téléphone</h1>"
                 "<p>Ce téléphone pourra ouvrir le bureau sans nouveau code.</p>"
                 "<form method=\"post\" action=\"/associer\"><input type=\"hidden\" name=\"code\" value=\"{code}\">"
                 "<button type=\"submit\" style=\"font-size:1.2em;padding:.7em 1.4em;border-radius:999px\">"
                 "Associer ce téléphone</button></form></body></html>")


def _sous(chemin, dossier):
    try:
        chemin.relative_to(dossier)
        return True
    except ValueError:
        return False


def images_declarees(regl):
    """Vrai si les réglages déclarent au moins une racine d'images (sinon les tâches n'ont pas de vignettes)."""
    conf = regl.get("images")
    racines = conf.get("racines") if isinstance(conf, dict) else None
    return isinstance(racines, list) and any(isinstance(r, str) and r for r in racines)


def _location_relayee(valeur, hote, port, prefixe):
    """La redirection d'un site relayé, ramenée sous le préfixe du relais : une URL absolue vers le site lui-même, ou un
    chemin depuis sa racine. Tout le reste (relatif, autre site) passe tel quel."""
    try:
        morceaux = urlsplit(valeur)
        cible_port = morceaux.port
    except ValueError:
        return valeur
    if (morceaux.scheme == "http" and (morceaux.hostname or "").lower() in releve.HOTES_LOCAUX
            and cible_port == port):
        return prefixe + (morceaux.path or "/") + (f"?{morceaux.query}" if morceaux.query else "")
    if not morceaux.scheme and not morceaux.netloc and valeur.startswith("/"):
        return prefixe + valeur
    return valeur


class Projet:
    """Tout ce que le bureau tient pour un fichier de réglages : équipe, historiques, prix, état, demandes."""

    def __init__(self, id_, chemin_reglages, ouvrir=None, demarrer=None):
        self.id = id_
        self.demarrer = demarrer or demarrage.demarrer   # « Lancer l'orchestrateur » ; remplacé dans les tests
        self._lance_a = None   # heure (monotone) du dernier lancement de l'orchestrateur
        self.envoyer = demandes.envoyer   # la commande d'actions du projet ; remplacée dans les tests
        self.chemin_reglages = Path(chemin_reglages)
        dossier = self.chemin_reglages.parent
        self.equipe = equipe.Equipe(dossier / "equipe.json")
        self.historique = charge.Historique(dossier / "charge-historique.jsonl")
        self.usage = HistoriqueUsage(dossier / "usage-historique.jsonl")
        self.alertes = kpi.HistoriqueAlertes(dossier / "alertes-historique.jsonl")
        self.table_prix = prix.TablePrix(dossier / "prix-historique.jsonl")
        self.ouvrir = ouvrir or prix.ouvrir_url  # la seule porte vers Internet ; remplacée dans les tests
        self.etat_prix = None  # résultat de la dernière mise à jour des prix
        self._premiers_prix = threading.Event()
        self._usage_integre = None
        self._usage_connu = bool(self.usage.lire())
        self._verrou = threading.Lock()
        self._cache_etat = (0.0, None)
        self.dernier_releve = None  # dernier relevé normalisé valide (sert à vérifier les demandes)
        self._verrou_demandes = threading.Lock()
        self._verrou_vus = threading.Lock()
        self._derniere_creation = None  # (empreinte, heure monotone) de la dernière fonctionnalité ou du dernier message
        self._challenges_envoyes = {}  # (type, id) de la cible -> heure d'envoi (monotone)
        self._reponses_envoyees = {}   # (type, décision) répondue -> heure d'envoi (monotone) : une seule réponse
        self._arret = threading.Event()
        self._fil_prix = None
        regl, err = self.reglages()
        if err is None and regl.get("prix_automatiques") is not False:
            self._fil_prix = threading.Thread(target=self._boucle_prix, daemon=True)
            self._fil_prix.start()
        else:
            self._premiers_prix.set()

    # -- réglages ---------------------------------------------------------
    def reglages(self):
        try:
            return reglages.charger(self.chemin_reglages), None
        except reglages.ReglagesInvalides as e:
            d = dict(reglages.DEFAUTS)
            d["dossier"] = str(self.chemin_reglages.parent)
            return d, str(e)

    # -- état -------------------------------------------------------------
    def etat(self, bloquant=False):
        t, e = self._cache_etat
        if e is not None and time.monotonic() - t < DELAI_ETAT_S:
            return e
        # Une seule lecture du relevé à la fois. Pendant qu'elle dure (une commande peut prendre
        # jusqu'à 10 s), les autres demandes reçoivent le dernier état au lieu d'attendre
        # (sauf `bloquant` : une demande doit être vérifiée contre le relevé frais).
        if not self._verrou.acquire(blocking=bloquant or e is None):
            return e
        try:
            t, e = self._cache_etat
            if e is not None and time.monotonic() - t < DELAI_ETAT_S:
                return e
            regl, err = self.reglages()
            maintenant = datetime.now().astimezone()
            if err:
                e, r = etat.erreur(err, maintenant), None
            else:
                e, r = etat.lire_avec_releve(regl, self.equipe, maintenant, self.alertes)
            if r is not None:
                self.dernier_releve = r
                self._integrer_usage(r)
            if e.get("version", 1) >= 3 and self._usage_connu:
                e["dossier"]["facturation"] = True
                e["dossier"]["kpi"] = True  # le coût moyen par tâche se calcule dès qu'il y a des usages
            e["agir"] = demandes.commande_declaree(regl)
            e["lecons_auto"] = regl.get("lecons_auto") is True      # la case « Valider les leçons automatiquement »
            if e.get("orchestrateur_present") is False:   # aucun orchestrateur en cours : les gestes attendent
                e["orchestrateur_absent"], e["agir"] = True, False
            # Ce que le moteur dit retenir ce projet (la charge) : sur la carte de chaque tâche retenue et dans la barre.
            retenu = attente.attente_charge(self.chemin_reglages.parent)
            e["attente_charge"] = retenu
            if retenu:
                for t in e["taches"]:
                    if t["id"] in retenu["taches"]:
                        t["attente"] = retenu["texte"]
            # Des places d'agents libres que rien ne peut prendre avant une validation du Directeur : dit dans la barre.
            e["attente_validation"] = attente.attente_places(self.chemin_reglages.parent)
            # Pourquoi chaque tâche prête ne part pas : sa raison sur sa carte et sa fiche, le résumé dans la barre.
            raisons = attente.attente_taches(self.chemin_reglages.parent)
            e["attentes"] = None
            if raisons:
                e["attentes"] = {k: raisons[k] for k in ("texte", "total", "familles")}
                for t in e["taches"]:
                    if t["id"] in raisons["taches"]:
                        t["attente_raison"] = raisons["taches"][t["id"]]
            # Les agents locaux au travail (détachés du moteur) : depuis quand, et leur dernière action.
            detache.ajouter_au_travail(e.get("taches") or [], self.chemin_reglages.parent)
            statuts.agents_au_travail(e.get("agents") or [], e.get("taches") or [])
            statuts.activite_des_agents(e.get("factory"), e.get("taches") or [], maintenant)
            if not err:
                self._cout_en_cours(e.get("taches") or [], regl)
            e["images_ok"] = images_declarees(regl)
            e["echanges_vus"] = self.echanges_vus()      # les échanges avec le Chef masqués de la direction (« Vu »)
            e["abonnement"] = self._abonnement(regl)
            self._cache_etat = (time.monotonic(), e)
            return e
        finally:
            self._verrou.release()

    def _abonnement(self, regl):
        """Les jauges d'abonnement et le taux de la part estimée (voir bureau/abonnement.py) ; rien si la couche est l'API."""
        try:
            couche = (regl.get("moteur") or {}).get("couche") or "claude"
            return modabonnement.pour_la_page(euros_par_dollar=self.table_prix.dernier_taux(), couche=couche)
        except Exception:   # les jauges ne font jamais tomber l'état
            return None

    # -- facturation ------------------------------------------------------
    def _integrer_usage(self, r):
        """Range les usages d'un relevé valide dans l'historique (sans jamais faire tomber l'état)."""
        if r.get("version", 1) < 3 or not r.get("usage") or r["usage"] == self._usage_integre:
            return
        try:
            self.usage.integrer(r)
            self._usage_integre = r["usage"]
            self._usage_connu = True
        except Exception:
            pass

    def _boucle_prix(self):
        """Au démarrage puis toutes les heures ; `actualiser` ne lit les sources qu'une fois par jour."""
        while True:
            try:
                regl, err = self.reglages()
                if err is None and regl.get("prix_automatiques") is not False:
                    aujourdhui = datetime.now().astimezone().date().isoformat()
                    self.etat_prix = prix.actualiser(self.table_prix, self.ouvrir, aujourdhui)
            except Exception:
                pass  # les prix ne doivent jamais faire tomber le serveur
            self._premiers_prix.set()
            if self._arret.wait(PAS_PRIX_S):
                return

    def facturation(self, periode):
        """(code HTTP, objet JSON)."""
        if periode not in cout.PERIODES:
            return 400, {"erreur": f"Période inconnue : « {periode} » (aujourdhui, 7j ou 30j)."}
        e = self.etat()
        r = self.dernier_releve
        if e.get("erreur") or r is None or r.get("version", 1) < 3 or not e["dossier"]["facturation"]:
            return 200, {"disponible": False}
        regl, _ = self.reglages()
        f = self._calculer(r, regl, periode)
        if regl.get("prix_automatiques") is False:
            message = ("Prix automatiques coupés (réglage « prix_automatiques ») : aucune lecture ; seuls comptent "
                       "les prix déjà enregistrés et ceux donnés à la main.")
        elif self.etat_prix is None:
            message = "Prix en cours de lecture."
        else:
            message = None if self.etat_prix["ok"] else self.etat_prix["message"]
        return 200, {**f, "disponible": True, "periode": periode, "maj": self.table_prix.derniere_maj(),
                     "message": message}

    def _cout_en_cours(self, taches, regl):
        """Le coût d'une tâche dont l'agent local travaille encore (`travail.cout`, `{total, sans_prix, tokens}`),
        d'après ce qu'il a consommé jusqu'ici ; il évolue à chaque relecture. Ne fait jamais tomber l'état."""
        maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
        for t in taches:
            tr = t.get("travail")
            if not isinstance(tr, dict):
                continue
            conso = tr.pop("conso", None)
            if not conso:
                continue
            try:
                tr["cout"] = cout.cout_des_usages(
                    conso, lambda m, d: prix.prix_effectif(self.table_prix, regl, m, d), maintenant)
            except Exception:      # le coût en cours est une aide : jamais une raison d'échouer
                pass

    def couts_taches(self):
        """(code HTTP, objet JSON) : le coût de chaque tâche du projet (`{disponible, taches: {id: {total, …}}}`)."""
        e = self.etat()
        r = self.dernier_releve
        if e.get("erreur") or r is None or r.get("version", 1) < 4:
            return 200, {"disponible": False}
        regl, _ = self.reglages()
        self._premiers_prix.wait(ATTENTE_PREMIERS_PRIX_S)
        return 200, {"disponible": True, "taches": cout.couts_taches(
            self.usage.lire(), lambda m, d: prix.prix_effectif(self.table_prix, regl, m, d), r)}

    def couts(self, fonctionnalite):
        """(code HTTP, objet JSON) : le coût de chaque tâche d'une fonctionnalité, depuis toujours."""
        e = self.etat()
        r = self.dernier_releve
        if e.get("erreur") or r is None or r.get("version", 1) < 4:
            return 200, {"disponible": False}
        regl, _ = self.reglages()
        self._premiers_prix.wait(ATTENTE_PREMIERS_PRIX_S)

        def prix_de(modele, date_iso):
            return prix.prix_effectif(self.table_prix, regl, modele, date_iso)
        return 200, {**cout.couts_fonctionnalite(self.usage.lire(), prix_de, r, fonctionnalite), "disponible": True}

    def kpi(self, periode):
        """(code HTTP, objet JSON) : les KPI du projet et ceux que le bureau calcule, par service."""
        if periode not in cout.PERIODES:
            return 400, {"erreur": f"Période inconnue : « {periode} » (aujourdhui, 7j ou 30j)."}
        e = self.etat()
        r = self.dernier_releve
        if e.get("erreur") or r is None or r.get("version", 1) < 3 or not e["dossier"]["kpi"]:
            return 200, {"disponible": False}
        regl, _ = self.reglages()
        usages_cout = self._calculer(r, regl, periode) if self._usage_connu else None
        return 200, {"disponible": True, "periode": periode,
                     "services": kpi.tous(r, usages_cout, periode, datetime.now().astimezone())}

    def _calculer(self, r, regl, periode, usages=None):
        # Le premier jour, les prix sont lus avant de calculer (sans attendre indéfiniment).
        self._premiers_prix.wait(ATTENTE_PREMIERS_PRIX_S)

        def prix_de(modele, date_iso):
            return prix.prix_effectif(self.table_prix, regl, modele, date_iso)

        if usages is None:
            usages = self.usage.lire()
        return cout.facturation(usages, prix_de, r, periode, datetime.now().astimezone(), self.table_prix.taux_a)

    def cibles_calculees(self, r, regl):
        """Les cibles que le bureau recalcule (id -> constat en clair) : les sources d'amélioration et les
        KPI calculés, sur les trois périodes (une cible présente sur l'une suffit)."""
        cibles = {}
        if r.get("version", 1) < 3:
            return cibles
        avec_usage = bool(r.get("usage")) or self._usage_connu
        usages = self.usage.lire() if avec_usage else []
        maintenant = datetime.now().astimezone()
        for periode in cout.PERIODES:
            f = self._calculer(r, regl, periode, usages) if avec_usage else None
            for source in (f["sources"] if f else []):
                cibles.setdefault(source["id"], source["texte"])
            for i, constat in kpi.constats(r, f, periode, maintenant).items():
                cibles.setdefault(i, constat)
        return cibles

    # -- demandes ---------------------------------------------------------
    def demande(self, demande):
        """(code HTTP, objet JSON). Les demandes passent une à une ; chacune est vérifiée contre le
        dernier relevé, relu juste avant (une demande précédente a pu le changer)."""
        if isinstance(demande, dict) and demande.get("type") == "lecons":
            return self._lot_lecons(demande)
        demande = demandes.nettoyer(demande)
        with self._verrou_demandes:
            empreinte = self._empreinte_creation(demande)
            if empreinte is not None and self._derniere_creation is not None:
                avant, quand = self._derniere_creation
                if avant == empreinte and time.monotonic() - quand < GARDE_DOUBLON_S:
                    return 200, {"ok": True, "doublon": True}
            self.etat(bloquant=True)  # relit le relevé s'il est périmé, en attendant une lecture en cours
            r = self.dernier_releve
            if r is None:
                return 409, {"erreur": "Relevé indisponible."}
            if r.get("orchestrateur_present") is False:
                return 409, {"erreur": "L'orchestrateur n'est pas lancé : lancez-le depuis le bureau, puis recommencez."}
            regl, _ = self.reglages()
            cibles = {}
            cible = demande.get("cible") if isinstance(demande, dict) and demande.get("type") == "challenge" else None
            if isinstance(cible, dict) and cible.get("type") in ("kpi", "source"):  # seules à recalculer
                cibles = self.cibles_calculees(r, regl)
            elements = None
            if isinstance(demande, dict) and demande.get("type") == "retour_element":
                elements = catalogue.ids(regl, demande.get("fonctionnalite"))  # None : catalogue illisible
            une_fois = (demande.get("type"), demande.get("decision")) if isinstance(demande, dict) \
                and demande.get("type") in REPONSES_UNE_FOIS and isinstance(demande.get("decision"), str) else None
            if une_fois is not None:       # une décision n'a qu'une réponse : ni double traitement ni double renvoi
                reponse = self._reponses_envoyees.get(une_fois)
                if reponse is not None and time.monotonic() - reponse < GARDE_REPONSE_S:
                    return 409, {"erreur": "Cette décision a déjà reçu une réponse : le moteur la traite, elle disparaîtra "
                                           "de la liste dès qu'il aura fini."}
            message = demandes.verifier(demande, r, cibles, elements)
            if message:
                return 400, {"erreur": message}
            cle = None
            if demande["type"] == "challenge":
                cle = (demande["cible"]["type"], demande["cible"]["id"])
                envoye = self._challenges_envoyes.get(cle)
                if envoye is not None and time.monotonic() - envoye < GARDE_CHALLENGE_S:
                    return 400, {"erreur": "Challenge déjà demandé : il apparaîtra au prochain relevé."}
                constat = cibles.get(cle[1])
                if constat:  # le bureau écrit lui-même le constat de ce qu'il a calculé
                    demande["texte"] = constat + (f"\n\n{demande['texte']}" if demande.get("texte") else "")
            ok, message = self.envoyer(regl, demande)
            if ok:
                attente.reveiller(self.chemin_reglages.parent)   # le moteur traite la demande tout de suite
            if ok and une_fois is not None:
                self._reponses_envoyees[une_fois] = time.monotonic()
            if ok and cle:
                self._challenges_envoyes[cle] = time.monotonic()
            if ok and empreinte is not None:
                self._derniere_creation = (empreinte, time.monotonic())
            self._cache_etat = (0.0, self._cache_etat[1])  # relire le relevé tout de suite
        if not ok:
            return 502, {"erreur": message}
        return 200, {"ok": True}

    def _lot_lecons(self, lot):
        """« Tout valider » / « Tout invalider » (essai réel) : une seule requête ; le serveur vérifie et envoie
        chaque verdict contre un même relevé, jusqu'au bout même si la page a été fermée entre-temps."""
        verdict, items = lot.get("verdict"), lot.get("lecons")
        if (verdict not in ("valider", "invalider") or not isinstance(items, list) or not 1 <= len(items) <= MAX_LOT
                or not all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in items)):
            return 400, {"erreur": f"Lot de leçons invalide (verdict valider ou invalider, 1 à {MAX_LOT} leçons)."}
        with self._verrou_demandes:
            self.etat(bloquant=True)
            r = self.dernier_releve
            if r is None:
                return 409, {"erreur": "Relevé indisponible."}
            if r.get("orchestrateur_present") is False:
                return 409, {"erreur": "L'orchestrateur n'est pas lancé : lancez-le depuis le bureau, puis recommencez."}
            regl, _ = self.reglages()
            envoyees, refusees = 0, []
            for x in items:
                d = {"type": "lecon", "id": x["id"], "verdict": verdict}
                if x.get("etage") is not None:
                    d["etage"] = x["etage"]
                d = demandes.nettoyer(d)
                message = demandes.verifier(d, r, {}, None)
                if not message:
                    ok, message = self.envoyer(regl, d)
                    if ok:
                        envoyees += 1
                        attente.reveiller(self.chemin_reglages.parent)
                        continue
                refusees.append({"id": x["id"], "erreur": message})
            self._cache_etat = (0.0, self._cache_etat[1])   # les verdicts paraissent au prochain relevé
        return 200, {"ok": True, "envoyees": envoyees, "refusees": refusees}

    # -- échanges avec le Chef marqués « Vu » (masqués de l'espace de direction, gardés dans le panneau du Chef) ----
    FICHIER_VUS = "echanges-vus.json"
    MAX_VUS = 500

    def echanges_vus(self):
        try:
            vus = json.loads((self.chemin_reglages.parent / self.FICHIER_VUS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [x for x in vus if isinstance(x, str)] if isinstance(vus, list) else []

    def marquer_echange_vu(self, t):
        """`t` : la date de la question (son identifiant dans le relevé). Rend `(code, objet)`."""
        if not isinstance(t, str) or not t.strip() or len(t) > 64:
            return 400, {"erreur": "« t » : la date de l'échange est obligatoire."}
        with self._verrou_vus:
            vus = self.echanges_vus()
            if t not in vus:
                vus = (vus + [t])[-self.MAX_VUS:]
                chemin = self.chemin_reglages.parent / self.FICHIER_VUS
                provisoire = chemin.with_suffix(".tmp")
                provisoire.write_text(json.dumps(vus, ensure_ascii=False), encoding="utf-8")
                os.replace(provisoire, chemin)
        self._cache_etat = (0.0, self._cache_etat[1])     # relire au prochain état
        return 200, {"ok": True}

    def lancer_orchestrateur(self):
        """(code HTTP, objet JSON). Refusé s'il tourne déjà ; un second clic pendant le démarrage ne relance rien."""
        self.etat(bloquant=True)
        r = self.dernier_releve
        if r is not None and r.get("orchestrateur_present") is True:
            return 409, {"erreur": "L'orchestrateur est déjà en cours."}
        if self._lance_a is not None and time.monotonic() - self._lance_a < DEMARRAGE_S:
            return 200, {"ok": True, "message": "L'orchestrateur démarre : il apparaîtra d'ici une minute."}
        resultat = self.demarrer(self.chemin_reglages)
        if resultat.get("ok"):
            self._lance_a = time.monotonic()
        return 200, resultat

    @staticmethod
    def _empreinte_creation(demande):
        """Empreinte d'une demande `fonctionnalite` ou `message` (sans l'heure) ; `None` pour les autres."""
        if not isinstance(demande, dict) or demande.get("type") not in ("fonctionnalite", "message"):
            return None
        brut = json.dumps(demande, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(brut).hexdigest()

    # -- charge -----------------------------------------------------------
    def charge(self, mesure, cpu_lisse):
        """La charge de la machine (une seule sonde pour tout le bureau), lue contre le maximum de ce projet."""
        regl, _ = self.reglages()
        mach = charge.machine()
        base = {"max": regl["charge_max"], "coeurs": mach["coeurs"],
                "memoire_totale_go": mach["memoire_totale_go"]}
        m = mesure
        if m is None:
            return {**base, "disponible": False, "cpu": None, "memoire": None, "charge": None, "feu_vert": True}
        cpu = cpu_lisse if cpu_lisse else m["cpu"]
        valeur = charge.affichee(cpu, m["memoire"])
        return {**base, "disponible": True, "cpu": round(cpu, 1), "memoire": round(m["memoire"], 1),
                "charge": valeur, "feu_vert": charge.feu_vert(valeur, regl["charge_max"])}

    def conseil(self):
        return charge.conseiller(self.historique.lire(), charge.machine())

    def livrable(self, fonctionnalite=None):
        """Le fichier du dernier livrable (du projet, ou de la fonctionnalité) s'il peut être servi, sinon `None`.
        Il doit être dans une des racines `livrables.racines` (relatives aux réglages) et d'une extension
        de `LIVRABLES`."""
        self.etat()
        r = self.dernier_releve
        if r is None or r.get("version", 1) < 4:
            return None
        if fonctionnalite is None:
            liv = r.get("livrable")
        else:
            f = next((f for f in r["fonctionnalites"] if f["id"] == fonctionnalite), None)
            liv = f.get("livrable") if f else None
        brut = liv.get("chemin") if isinstance(liv, dict) else None
        if (not isinstance(brut, str) or not brut or "\x00" in brut or Path(brut).is_absolute()
                or brut[0] in "/\\" or Path(brut).suffix.lower() not in LIVRABLES):
            return None
        regl, _ = self.reglages()
        conf = regl.get("livrables")
        racines = conf.get("racines") if isinstance(conf, dict) else None
        if not isinstance(racines, list):
            return None
        base = Path(regl["dossier"])
        try:
            cible = (base / brut).resolve()
            if cible.suffix.lower() not in LIVRABLES or not cible.is_file():  # un lien peut viser autre chose
                return None
            for racine in racines:
                if isinstance(racine, str) and racine:
                    try:
                        cible.relative_to((base / racine).resolve())
                        return cible
                    except ValueError:
                        continue
        except (OSError, ValueError):
            pass
        return None

    def methode(self, fonctionnalite):
        """Le fichier de la méthode d'une fonctionnalité (`methode.chemin`), s'il peut être servi : `.md` ou `.txt`, dans
        une des racines `documents` (ou `livrables`) des réglages. Le panneau l'écrit en entier."""
        self.etat()
        r = self.dernier_releve
        if r is None or r.get("version", 1) < 4:
            return None
        f = next((f for f in r["fonctionnalites"] if f["id"] == fonctionnalite), None)
        brut = ((f or {}).get("methode") or {}).get("chemin")
        if (not isinstance(brut, str) or not brut or "\x00" in brut or Path(brut).is_absolute() or brut[0] in "/\\"
                or Path(brut).suffix.lower() not in METHODES):
            return None
        regl, _ = self.reglages()
        racines = []
        for cle in ("documents", "livrables"):
            conf = regl.get(cle)
            if isinstance(conf, dict) and isinstance(conf.get("racines"), list):
                racines += [x for x in conf["racines"] if isinstance(x, str) and x]
        base = Path(regl["dossier"])
        try:
            cible = (base / brut).resolve()
            if not cible.is_file():
                return None
            for racine in racines:
                try:
                    cible.relative_to((base / racine).resolve())
                    return cible
                except ValueError:
                    continue
        except (OSError, ValueError):
            pass
        return None

    def document(self, fonctionnalite, brut):
        """Le fichier d'un document de la fonctionnalité s'il peut être servi, sinon `None` : listé par le relevé
        (`documents` de la fonctionnalité), dans une des racines `documents.racines` des réglages, d'une extension
        de `DOCUMENTS`."""
        self.etat()
        r = self.dernier_releve
        if r is None or r.get("version", 1) < 4 or not isinstance(brut, str):
            return None
        f = next((f for f in r["fonctionnalites"] if f["id"] == fonctionnalite), None)
        if f is None or not any(isinstance(d, dict) and d.get("chemin") == brut for d in f.get("documents") or []):
            return None
        if (not brut or "\x00" in brut or Path(brut).is_absolute() or brut[0] in "/\\"
                or Path(brut).suffix.lower() not in DOCUMENTS):
            return None
        regl, _ = self.reglages()
        conf = regl.get("documents")
        racines = conf.get("racines") if isinstance(conf, dict) else None
        if not isinstance(racines, list):
            return None
        base = Path(regl["dossier"])
        try:
            cible = (base / brut).resolve()
            if cible.suffix.lower() not in DOCUMENTS or not cible.is_file():
                return None
            for racine in racines:
                if isinstance(racine, str) and racine:
                    try:
                        cible.relative_to((base / racine).resolve())
                        return cible
                    except ValueError:
                        continue
        except (OSError, ValueError):
            pass
        return None

    def telechargeable(self, fonctionnalite, brut):
        """Le fichier à télécharger (fenêtre de validation, partie « Livrables »), sinon `None`. Il doit avoir une
        extension de `releve.TELECHARGEABLES`, être un fichier ordinaire DANS le projet (lien résolu ; jamais dans `.git`),
        et être soit sous une racine `livrables` ou `documents` des réglages, soit déclaré pour cette fonctionnalité :
        document `livrable`, ou fichier d'une décision `valider_etape`. Chemin relatif, sans `..` ni lecteur. Cherché
        depuis le dossier des réglages, puis (réglages dans `.factory`) depuis le dossier du projet."""
        self.etat()
        r = self.dernier_releve
        if r is None or r.get("version", 1) < 4 or not isinstance(brut, str) or not isinstance(fonctionnalite, str):
            return None
        f = next((x for x in r["fonctionnalites"] if x.get("id") == fonctionnalite), None)
        p = Path(brut.replace("\\", "/"))
        if (f is None or not brut or "\x00" in brut or brut[0] in "/\\" or p.is_absolute() or p.drive or p.anchor
                or ".." in p.parts or releve.extension(brut) not in TELECHARGEABLES_JOINTS):
            return None
        # Les fichiers joints à la discussion de cette fonctionnalité (liste blanche de `fichiers_joints`).
        joints = {x.get("chemin") for m in f.get("discussion") or [] if isinstance(m, dict)
                  for x in m.get("fichiers") or [] if isinstance(x, dict)
                  and releve.extension(x.get("chemin")) in fichiers_joints.TYPES}
        if releve.extension(brut) not in releve.TELECHARGEABLES and brut not in joints:
            return None
        declares = {d.get("chemin") for d in f.get("documents") or [] if isinstance(d, dict) and d.get("livrable") is True}
        declares |= joints
        declares |= {x.get("chemin") for d in r.get("decisions_projet") or []
                     if isinstance(d, dict) and d.get("genre") == "valider_etape" and d.get("fonctionnalite") == fonctionnalite
                     for x in d.get("fichiers") or [] if isinstance(x, dict)}
        regl, _ = self.reglages()
        try:
            base = Path(regl["dossier"]).resolve()
            projet = base.parent if base.name == ".factory" else base
            racines = []
            for cle in ("livrables", "documents"):
                conf = regl.get(cle)
                if isinstance(conf, dict) and isinstance(conf.get("racines"), list):
                    racines += [(base / x).resolve() for x in conf["racines"] if isinstance(x, str) and x]
            for candidat in [base / p] + ([projet / p] if projet != base else []):
                cible = candidat.resolve()
                if not cible.is_file() or not _sous(cible, projet):
                    continue
                if ".git" in [x.lower() for x in cible.relative_to(projet).parts]:
                    continue
                ext = releve.extension(cible.name)
                if ext not in releve.TELECHARGEABLES and not (brut in joints and ext in TELECHARGEABLES_JOINTS):
                    continue                                                   # un lien peut viser autre chose
                if brut in declares or any(_sous(cible, x) for x in racines):
                    return cible
        except (OSError, ValueError, KeyError):
            pass
        return None

    def apercu(self, decision):
        """`(hôte, port)` du site en cours qu'une décision `valider_etape` encore posée déclare (`acces`), seulement s'il
        est sur l'ordinateur (http, 127.0.0.1, localhost ou ::1, port explicite) ; sinon `None`."""
        self.etat()
        r = self.dernier_releve
        if r is None or r.get("version", 1) < 4:
            return None
        d = next((x for x in r.get("decisions_projet") or [] if isinstance(x, dict) and x.get("id") == decision
                  and x.get("genre") == "valider_etape"), None)
        if d is None and isinstance(decision, str) and decision.startswith(APERCU_FIN):
            # l'avis « Fonctionnalité terminée » : le lien d'accès noté à la fin de la fonctionnalité
            f = next((x for x in r.get("fonctionnalites") or [] if isinstance(x, dict)
                      and x.get("id") == decision[len(APERCU_FIN):]), None)
            d = (f or {}).get("fin") if isinstance((f or {}).get("fin"), dict) else None
        lien = (d or {}).get("acces")
        return releve.acces_local(lien.get("url")) if isinstance(lien, dict) else None

    def resume(self):
        """La ligne du projet dans `/api/projets`. Sert le dernier état connu, même périmé, et le relit en
        arrière-plan : un relevé lent ne retarde pas la liste (sauf la toute première fois)."""
        t, e = self._cache_etat
        if e is None:
            e = self.etat()
        elif time.monotonic() - t >= DELAI_ETAT_S and not self._verrou.locked():
            threading.Thread(target=self.etat, daemon=True).start()
        return {"id": self.id, "nom": e.get("projet") or self.id,
                "attente": e.get("directeur", {}).get("total", 0), "erreur": e.get("erreur") or None}

    def pour_creation(self):
        """Ce que le formulaire « Nouveau projet » reprend de ce projet : ses mots interdits et sa facturation."""
        try:
            from orchestrateur import factory as fa
            f = fa.lire(self._chemin_factory())
        except Exception:
            return {"mots_interdits": [], "facturation": False}
        return {"mots_interdits": f["mots_interdits"],
                "facturation": any(x.get("id") == "facturation" for x in f["services"])}

    def _chemin_factory(self):
        regl, _ = self.reglages()
        return self.chemin_reglages.parent / (regl.get("orchestrateur") or "factory.json")

    def fermer(self):
        self._arret.set()
        if self._fil_prix is not None:
            self._fil_prix.join(5)  # qu'il n'écrive plus dans le dossier une fois le serveur fermé


class Bureau(ThreadingHTTPServer):
    """Le serveur : un ou plusieurs projets, une seule sonde de charge (la charge est celle de la machine).
    Il écoute sur 127.0.0.1 ; les écouteurs distants (`ouvrir_distants`) servent le même bureau, avec code d'accès."""
    daemon_threads = True
    distant = False

    def __init__(self, adresse, projets, ouvrir=None, multi=True, lancement=None, demarrer=None, fichier_bureau=None):
        super().__init__(adresse, Handler)
        # Le fichier du bureau commun, relu quand il change : un projet inscrit pendant que le bureau tourne y paraît
        # sans redémarrage (essai réel).
        self.fichier_bureau = Path(fichier_bureau) if fichier_bureau else None
        self.projets_vus_a = self._date_fichier_bureau()
        self._ouvrir, self._demarrer = ouvrir, demarrer
        self.executer_git = self.executer_gh = None   # remplacés dans les tests : jamais de git ni de gh réels
        # La création en deux fenêtres (`creations.py`) : tout ce qui s'injecte dans les essais (jamais de vrai modèle,
        # jamais le dossier des brouillons de l'utilisateur).
        self.dossier_creations = self.commun_creations = None
        self.appeler_jugement = self.verifier_environnement = self.executer_outil = self.prix_de_modele = None
        self._verrou_projets = threading.Lock()
        self.multi = multi
        self.lancement = lancement_.Drapeau(lancement)   # le premier lancement a-t-il été proposé ?
        self.cles = None
        self.ecouteurs = []
        self.distants = []    # [{"genre", "url"}]
        self.annonces = []    # ce que le terminal dit au lancement
        self.projets = {id_: Projet(id_, chemin, ouvrir=ouvrir, demarrer=demarrer) for id_, chemin in projets}
        self.sonde = charge.Sonde()
        # la consommation du forfait Claude Code (le rond du bandeau, source unique des jauges), avec repli sur le dernier
        # appel du moteur, versement à l'historique d'abonnement et part estimée des coûts
        self.conso = conso.Conso(memoire=True, part=self._part_abonnement, renouveler=conso.renouveler_connexion)
        self.lisseur = charge.Lisseur(60)
        self.mesure = None  # dernière lecture brute de la sonde
        self._dernier_historique = 0.0
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._boucle_sonde, daemon=True)
        self._fil.start()

    def _date_fichier_bureau(self):
        try:
            return self.fichier_bureau.stat().st_mtime_ns if self.fichier_bureau else None
        except OSError:
            return None

    def actualiser_projets(self):
        """Ajoute les projets inscrits depuis le lancement. Un fichier illisible ne retire rien."""
        date = self._date_fichier_bureau()
        if date is None or date == self.projets_vus_a:
            return
        with self._verrou_projets:
            if date == self.projets_vus_a:
                return
            self.projets_vus_a = date
            try:
                conf = reglages.lire_bureau(self.fichier_bureau)
            except reglages.ReglagesInvalides:
                return
            for p in conf["projets"]:
                if p["id"] not in self.projets:
                    self.projets[p["id"]] = Projet(p["id"], p["chemin"], ouvrir=self._ouvrir, demarrer=self._demarrer)

    def etat_du_projet(self, projet):
        """L'état servi à la page : celui du projet, plus la pause globale du bureau (une installation d'outil, dans
        n'importe quel projet, retient tous les départs) : `pause_installation` vaut `{texte, projet, outils}` ou `None`."""
        e = projet.etat()
        return {**e, "pause_installation": attente.pause_installation(self.fichier_bureau)}

    def projet(self, id_=None):
        """Le projet d'id donné ; `None` → le premier ; inconnu → `None`."""
        self.actualiser_projets()
        if id_ is None:
            return next(iter(self.projets.values()))
        return self.projets.get(id_)

    def _part_abonnement(self):
        """Le taux de la part estimée, lu avec le premier projet (le taux dollar-euro et la couche sont ceux de ses réglages)."""
        p = self.projet()
        return p._abonnement(p.reglages()[0])

    # -- les semaines du forfait et les sujets qui les ont consommées (tous les projets du bureau) --
    def liste_semaines(self):
        """Les semaines archivées (la plus récente d'abord). Au premier appel, l'archive est amorcée avec l'historique."""
        racine, maintenant = modabonnement.racine(), time.time()
        if not modsemaines.existe(racine):
            modsemaines.importer(modabonnement.lire_historique(), racine)
        return {"semaines": modsemaines.lister(racine, maintenant), "maintenant": int(maintenant)}

    def serie_semaine(self, identifiant):
        s = modsemaines.lire(modabonnement.racine(), identifiant, time.time())
        return (200, s) if s is not None else (404, {"erreur": "Semaine inconnue."})

    def sujets_semaine(self, identifiant):
        """(code, objet) : l'arbre des sujets ayant utilisé Claude pendant la semaine, projets du bureau et échanges de
        création confondus (voir `sujets.py`)."""
        s = modsemaines.lire(modabonnement.racine(), identifiant, time.time())
        if s is None:
            return 404, {"erreur": "Semaine inconnue."}
        debut, fin = s["debut"], s["remise"]
        lignes = []
        self.actualiser_projets()
        for p in list(self.projets.values()):
            try:
                p.etat()
                regl, _ = p.reglages()
                p._premiers_prix.wait(ATTENTE_PREMIERS_PRIX_S)
                r = p.dernier_releve or {}
                lignes += modsujets.lignes_projet(
                    p.id, r.get("projet") if isinstance(r.get("projet"), str) and r.get("projet") else p.id,
                    p.usage.lire(), r, lambda m, d, p=p, regl=regl: prix.prix_effectif(p.table_prix, regl, m, d),
                    debut, fin)
            except Exception:   # un projet en panne n'empêche pas de compter les autres
                continue
        try:
            lignes += creations.lignes_sujets(self, debut, fin)
        except Exception:
            pass
        return 200, {"semaine": identifiant, "debut": debut, "remise": fin, **modsujets.arbre(lignes)}

    def _boucle_sonde(self):
        try:
            self.mesure = self.sonde.lire()  # première lecture : sert de repère
        except Exception:
            self.mesure = None
        attente = 1
        while not self._arret.wait(attente):
            attente = PAS_SONDE_S
            try:
                m = self.sonde.lire()
                if m is None:
                    continue
                t = time.time()
                self._ranger_mesure(t, m, historique=t - self._dernier_historique >= PAS_HISTORIQUE_S)
            except Exception:
                pass  # la mesure ne doit jamais faire tomber le serveur

    def _ranger_mesure(self, t, m, historique):
        """Une mesure de la machine : lissée une fois, notée dans l'historique de charge de chaque projet."""
        self.mesure = m
        self.lisseur.ajouter(t, m["cpu"])
        if not historique:
            return
        self._dernier_historique = t
        valeur = charge.affichee(self.lisseur.moyenne(), m["memoire"])
        for p in self.projets.values():
            try:
                p.historique.noter(t, valeur, etat.agents_locaux_au_travail(p.etat()))
            except Exception:
                pass  # un projet en panne n'empêche pas de noter les autres

    def charge(self, projet):
        return projet.charge(self.mesure, self.lisseur.moyenne())

    def liste(self):
        """Tous les projets, lus en parallèle : un projet lent ne fait pas attendre les autres."""
        self.actualiser_projets()
        projets = list(self.projets.values())
        lignes = [None] * len(projets)

        def lire(i, p):
            try:
                lignes[i] = p.resume()
            except Exception as e:  # jamais une liste incomplète
                lignes[i] = {"id": p.id, "nom": p.id, "attente": 0, "erreur": f"{e}"[:200]}

        fils = [threading.Thread(target=lire, args=(i, p), daemon=True) for i, p in enumerate(projets)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        if not self.multi:   # un seul projet, sans fichier de bureau commun : on n'y crée pas de projet
            return {"multi": False, "projets": lignes}
        for ligne, p in zip(lignes, projets):
            ligne.update(p.pour_creation())
        return {"multi": True, "projets": lignes, "parents": self.parents_suggeres()}

    def parents_suggeres(self):
        """Les dossiers où l'on range déjà des projets (le parent du dossier de chaque projet inscrit), sans doublon."""
        vus = []
        for p in list(self.projets.values()):
            dossier = p.chemin_reglages.resolve().parent
            if dossier.name == ".factory":
                dossier = dossier.parent
            parent = str(dossier.parent)
            if parent not in vus and dossier.parent.is_dir():
                vus.append(parent)
        return vus

    def creer_projet(self, corps):
        """(code HTTP, objet JSON) de `POST /api/projets/creer`. Le projet est créé vide et inscrit au bureau commun ;
        depuis une décision, la demande « nouveau projet » est déposée dans le projet d'origine, dont le moteur déplace
        la fonctionnalité (le bureau ne recrée rien lui-même)."""
        from installation import creation
        from installation.dossier import Echec
        if not isinstance(corps, dict):
            return 400, {"erreur": "Demande illisible."}
        if self.fichier_bureau is None:
            return 409, {"erreur": "Ce bureau n'est pas lancé sur le fichier du bureau commun : on ne peut pas y créer "
                                   "de projet."}
        for cle, type_ in (("parent", str), ("nom", str)):
            if not isinstance(corps.get(cle), type_):
                return 400, {"erreur": f"« {cle} » est obligatoire."}
        mots = corps.get("mots_interdits", [])
        if not isinstance(mots, list) or not all(isinstance(m, str) for m in mots):
            return 400, {"erreur": "« mots_interdits » doit être une liste de textes."}
        for cle in ("facturation", "github"):
            if not isinstance(corps.get(cle, False), bool):
                return 400, {"erreur": f"« {cle} » doit valoir vrai ou faux."}
        for cle in ("description", "genre", "genre_description", "origine", "decision", "fonctionnalite"):
            if corps.get(cle) is not None and not isinstance(corps[cle], str):
                return 400, {"erreur": f"« {cle} » doit être un texte."}
        origine = None
        if corps.get("origine"):
            origine = self.projet(corps["origine"])
            if origine is None:
                return 404, {"erreur": "Projet inconnu."}
        depuis_decision = bool(corps.get("decision") or corps.get("fonctionnalite"))
        if depuis_decision and (origine is None or not (corps.get("decision") and corps.get("fonctionnalite"))):
            return 400, {"erreur": "Une création depuis une décision donne le projet, la décision et la fonctionnalité."}
        genre, description = corps.get("genre") or None, (corps.get("description") or "").strip() or None
        nouveau = (corps.get("genre_description") or "").strip() or None
        demande = None
        if depuis_decision:
            demande = {"type": "genre_fonctionnalite", "decision": corps["decision"],
                       "fonctionnalite": corps["fonctionnalite"], "choix": "nouveau_projet"}
            if genre:
                demande["genre"] = genre
            if nouveau:
                demande["description"] = nouveau
            # La demande est vérifiée avant toute création : un refus ne laisse pas un projet orphelin.
            origine.etat(bloquant=True)
            r = origine.dernier_releve
            if r is None:
                return 409, {"erreur": "Relevé indisponible."}
            if r.get("orchestrateur_present") is False:
                return 409, {"erreur": "L'orchestrateur n'est pas lancé : lancez-le depuis le bureau, puis recommencez."}
            message = demandes.verifier(demandes.nettoyer(dict(demande, projet_cree="(à créer)")), r, {}, None)
            if message:
                return 400, {"erreur": message}
        genre_projet = genre if genre and not nouveau and genre in self._genres_connus() else None
        try:
            fait = creation.creer_projet(
                corps["parent"], corps["nom"], origine=origine.chemin_reglages if origine else None,
                mots_interdits=mots, facturation=corps.get("facturation", False), github=corps.get("github", False),
                description=description or nouveau, genre=genre_projet, bureau_json=self.fichier_bureau,
                **({"git": self.executer_git} if self.executer_git else {}),
                **({"gh": self.executer_gh} if self.executer_gh else {}))
        except Echec as e:
            return 400, {"erreur": str(e)}
        except Exception as e:   # jamais une connexion coupée sans réponse lisible
            return 500, {"erreur": f"Erreur du bureau : {e}"[:200]}
        self.projets_vus_a = None
        self.actualiser_projets()
        sortie = {"ok": True, "projet": fait["id"], "github": fait["github"], "message": self._message_creation(fait)}
        if demande is not None:
            demande["projet_cree"] = str(fait["reglages"])
            try:
                code, objet = origine.demande(demande)
            except Exception as e:
                code, objet = 500, {"erreur": str(e)}
            if code != 200:
                sortie["message"] += (" La demande n'a pas pu être déplacée dans ce projet (" + str(objet.get("erreur"))
                                      + ") : refaites « Nouveau projet » depuis la décision, ou gardez-la ici.")
                sortie["demande_deposee"] = False
            else:
                sortie["demande_deposee"] = True
        return 200, sortie

    def _genres_connus(self):
        from orchestrateur import memoire
        try:
            from installation import dossier as dossier_inst
            return {g["id"] for g in memoire.genres(dossier_inst.skill() / "orchestrateur" / "memoire")}
        except Exception:
            return set()

    def _genres_pour_le_chef(self):
        """Les genres de la mémoire de la skill, tels que le chef les lit : [{id, domaine, livrable, outils}]."""
        from orchestrateur import memoire
        try:
            from installation import dossier as dossier_inst
            return list(memoire.genres(dossier_inst.skill() / "orchestrateur" / "memoire"))
        except Exception:
            return []

    @staticmethod
    def _message_creation(fait):
        message = f"Le projet est créé dans {fait['projet']}."
        if fait["github"] not in ("fait", "non demandé"):
            message += " " + fait["github"]
        elif fait["github"] == "fait":
            message += " Son dépôt GitHub privé est créé."
        return message

    REESSAI_ADRESSE_S = 30

    def ouvrir_distants(self, ouverts, adresses, cles, port_distant=None):
        """Un écouteur par accès ouvert dont l'adresse est trouvée (même port que 127.0.0.1, sauf `port_distant`).
        Une adresse introuvable est dite, puis recherchée de nouveau en arrière-plan toutes les 30 s : l'accès s'ouvre
        dès qu'elle revient (essai réel : Tailscale indisponible un instant au redémarrage, le téléphone ne joignait
        plus le bureau)."""
        self.cles = cles
        cles.cle()   # créée maintenant plutôt qu'à la première requête
        trouvees = adresses()
        manquants = []
        for genre in reglages.ACCES:
            if not ouverts.get(genre):
                continue
            ip = trouvees.get(genre)
            if not ip:
                self.annonces.append(f"{NOMS_ACCES[genre]} : adresse introuvable pour l'instant ; nouvel essai toutes "
                                     f"les {self.REESSAI_ADRESSE_S} s.")
                manquants.append(genre)
                continue
            self._ouvrir_un_acces(genre, ip, port_distant)
        if manquants:
            threading.Thread(target=self._reessayer_les_adresses, args=(manquants, adresses, port_distant),
                             daemon=True).start()

    def _ouvrir_un_acces(self, genre, ip, port_distant=None):
        nom = NOMS_ACCES[genre]
        port = self.server_address[1] if port_distant is None else port_distant
        try:
            e = Ecouteur((ip, port), self, genre)
        except OSError as err:
            self.annonces.append(f"{nom} : impossible d'écouter sur {ip}:{port} ({err}) ; accès ignoré.")
            return False
        threading.Thread(target=e.serve_forever, daemon=True).start()
        url = f"http://{e.hote}"
        self.ecouteurs.append(e)
        self.distants.append({"genre": genre, "url": url})
        self.annonces.append(f"{nom} : {url} (code d'accès exigé ; associez le téléphone depuis la page de "
                             "l'ordinateur)")
        return True

    def _reessayer_les_adresses(self, manquants, adresses, port_distant=None, attendre=None):
        attendre = attendre or (lambda: time.sleep(self.REESSAI_ADRESSE_S))
        while manquants and not getattr(self, "_arrete", False):
            attendre()
            try:
                trouvees = adresses()
            except Exception:       # une recherche ratée : on réessaiera
                continue
            for genre in list(manquants):
                if trouvees.get(genre) and self._ouvrir_un_acces(genre, trouvees[genre], port_distant):
                    manquants.remove(genre)

    def infos_acces(self):
        """Pour la page de l'ordinateur : les adresses ouvertes et un code d'association neuf."""
        if not self.distants:
            return {"adresses": [], "code": None, "expire": None}
        code = self.cles.code_association()
        expire = datetime.fromtimestamp(self.cles.expiration(code)).isoformat(timespec="seconds")
        return {"adresses": [dict(d) for d in self.distants], "code": code, "expire": expire}

    def shutdown(self):
        self._arrete = True
        for e in self.ecouteurs:
            e.shutdown()
        super().shutdown()

    def server_close(self):
        for e in self.ecouteurs:
            e.shutdown()
            e.server_close()
        self._arret.set()
        for p in self.projets.values():
            p.fermer()
        super().server_close()


class Ecouteur(ThreadingHTTPServer):
    """Un écouteur distant (adresse Tailscale ou du réseau local) : il sert le même bureau, avec code d'accès."""
    daemon_threads = True
    distant = True

    def __init__(self, adresse, bureau, genre):
        self.bureau = bureau
        self.genre = genre
        super().__init__(adresse, Handler)
        self.hote = f"{adresse[0]}:{self.server_address[1]}"

    def __getattr__(self, nom):   # projet(), liste(), charge(), projets, multi, cles : ceux du bureau
        if nom == "bureau":
            raise AttributeError(nom)
        return getattr(self.bureau, nom)


class Handler(BaseHTTPRequestHandler):
    server_version = "Bureau"

    def log_message(self, *args):
        pass

    # -- réponses ---------------------------------------------------------
    def _envoyer(self, code, corps, type_="application/json; charset=utf-8", cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _json(self, code, objet):
        self._envoyer(code, json.dumps(objet, ensure_ascii=False).encode("utf-8"))

    # -- écouteur distant ---------------------------------------------------
    def _cookie(self):
        try:
            morceau = SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE_ACCES)
        except CookieError:
            return None
        return morceau.value if morceau is not None else None

    def _refus_401(self):
        self._envoyer(401, PAGE_401, "text/html; charset=utf-8")

    def _page_associer(self, requete):
        """Le lien du QR code : une page avec un bouton, sans consommer le code."""
        codes = parse_qs(requete, keep_blank_values=True).get("code", [])
        if len(codes) != 1 or not self.server.cles.en_attente(codes[0]):
            return self._refus_401()
        self._envoyer(200, PAGE_ASSOCIER.format(code=html.escape(codes[0].upper(), quote=True)).encode("utf-8"),
                      "text/html; charset=utf-8")

    def _associer(self):
        """Le bouton de la page : échange le code contre le cookie d'accès."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        corps = self.rfile.read(n).decode("utf-8", "replace") if 0 < n <= 200 else ""
        codes = parse_qs(corps, keep_blank_values=True).get("code", [])
        cle = self.server.cles.echanger(codes[0]) if len(codes) == 1 else None
        if cle is None:
            return self._refus_401()
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", f"{COOKIE_ACCES}={cle}; HttpOnly; SameSite=Strict; Path=/; "
                                       f"Max-Age={DUREE_COOKIE_S}")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _garde_distant(self, post=False):
        """Sur un écouteur distant : l'hôte servi, le cookie d'accès, et l'origine d'un POST. Rend vrai si la
        requête a reçu sa réponse (un refus, ou l'association)."""
        if self.headers.get("Host", "") != self.server.hote:
            self._json(403, {"erreur": "Hôte refusé."})
            return True
        morceaux = urlsplit(self.path)
        if not post and morceaux.path == "/associer":
            self._page_associer(morceaux.query)
            return True
        if post and morceaux.path == "/associer":
            if self.headers.get("Origin") != f"http://{self.server.hote}":
                self._json(403, {"erreur": "Origine refusée."})
            else:
                self._associer()
            return True
        if not self.server.cles.valide(self._cookie()):
            self._refus_401()
            return True
        if post and self.headers.get("Origin") != f"http://{self.server.hote}":
            self._json(403, {"erreur": "Origine refusée."})
            return True
        if morceaux.path.startswith("/api/acces"):   # le code et la révocation : depuis l'ordinateur seulement
            self._json(404, {"erreur": "Introuvable."})
            return True
        return False

    def _hote_ok(self):
        # protège contre les pages tierces qui viseraient le serveur local (DNS rebinding)
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _projet(self, requete):
        """Le projet visé par `?projet=` (absent → le premier) ; `None` s'il est inconnu."""
        valeurs = parse_qs(requete, keep_blank_values=True).get("projet")
        if valeurs is None:
            return self.server.projet()
        if len(valeurs) != 1:
            return None
        return self.server.projet(valeurs[0]) if valeurs[0] else None

    # -- GET --------------------------------------------------------------
    def do_GET(self):
        if self.server.distant:
            if self._garde_distant():
                return
        elif not self._hote_ok():
            return self._json(403, {"erreur": "Hôte refusé."})
        morceaux = urlsplit(self.path)
        chemin = morceaux.path
        if chemin.startswith(APERCU):
            return self._apercu(morceaux)
        if chemin == "/api/projets":
            return self._json(200, self.server.liste())
        if chemin == "/api/acces":   # jamais atteint depuis un écouteur distant
            return self._json(200, self.server.infos_acces())
        if chemin == "/api/lancement":
            return self._json(200, {"vu": self.server.lancement.vu()})
        if chemin == "/api/creations":
            ids = parse_qs(morceaux.query, keep_blank_values=True).get("id")
            if ids is not None and len(ids) != 1:
                return self._json(404, {"erreur": "Ce brouillon n'existe pas."})
            return self._json(*creations.liste(self.server, ids[0] if ids else None))
        if chemin == "/api/conso":
            return self._json(200, self.server.conso.lire())
        if chemin in ("/api/semaines", "/api/semaine", "/api/sujets"):   # tous les projets du bureau : pas de `?projet=`
            q = parse_qs(morceaux.query, keep_blank_values=True)
            cle = "semaine" if chemin == "/api/sujets" else "id"
            ids = q.get(cle, [])
            if chemin == "/api/semaines":
                return self._json(200, self.server.liste_semaines())
            if len(ids) != 1:
                return self._json(404, {"erreur": "Aucune semaine demandée."})
            return self._json(*(self.server.sujets_semaine(ids[0]) if chemin == "/api/sujets"
                                else self.server.serie_semaine(ids[0])))
        if chemin not in ROUTES_PROJET:
            return self._statique(chemin)
        projet = self._projet(morceaux.query)
        if projet is None:
            return self._json(404, {"erreur": "Projet inconnu."})
        if chemin == "/api/image":
            return self._image(projet, morceaux.query)
        if chemin == "/api/telecharger":
            return self._telecharger(projet, morceaux.query)
        if chemin == "/api/etat":
            return self._json(200, self.server.etat_du_projet(projet))
        if chemin == "/api/charge":
            return self._json(200, self.server.charge(projet))
        if chemin == "/api/conseil":
            return self._json(200, projet.conseil())
        if chemin == "/api/couts":
            if parse_qs(morceaux.query).get("taches") == ["tout"]:     # le coût de chaque tâche du projet
                return self._json(*projet.couts_taches())
            fonc = parse_qs(morceaux.query, keep_blank_values=True).get("fonctionnalite", [])
            if len(fonc) != 1:
                return self._json(404, {"erreur": "Aucune fonctionnalité demandée."})
            return self._json(*projet.couts(fonc[0]))
        if chemin == "/api/methode":
            fonc = parse_qs(morceaux.query, keep_blank_values=True).get("fonctionnalite", [])
            if len(fonc) != 1:
                return self._json(404, {"erreur": "Aucune fonctionnalité demandée."})
            return self._livrable(projet.methode(fonc[0]), METHODES, (".md", ".txt"))
        if chemin == "/api/document":
            q = parse_qs(morceaux.query, keep_blank_values=True)
            fonc, doc = q.get("fonctionnalite", []), q.get("chemin", [])
            if len(fonc) != 1 or len(doc) != 1:
                return self._json(404, {"erreur": "Introuvable."})
            return self._livrable(projet.document(fonc[0], doc[0]), DOCUMENTS, BAC_A_SABLE_DOCUMENTS)
        if chemin in ("/api/catalogue", "/api/livrable"):
            valeurs = parse_qs(morceaux.query, keep_blank_values=True).get("fonctionnalite")
            if valeurs is not None and len(valeurs) != 1:
                return self._json(404, {"erreur": "Introuvable."})
            fonctionnalite = valeurs[0] if valeurs else None
            if chemin == "/api/livrable":
                return self._livrable(projet.livrable(fonctionnalite))
            if fonctionnalite is None:
                return self._json(404, {"erreur": "Aucune fonctionnalité demandée."})
            regl, _ = projet.reglages()
            return self._json(*catalogue.lire(regl, fonctionnalite))
        periodes = parse_qs(morceaux.query, keep_blank_values=True).get("periode", ["7j"])
        periode = periodes[0] if len(periodes) == 1 else None
        code, objet = projet.facturation(periode) if chemin == "/api/facturation" else projet.kpi(periode)
        return self._json(code, objet)

    do_HEAD = do_GET

    def _image(self, projet, requete):
        """Sert une image du projet, seulement depuis les racines déclarées (`images.racines`)."""
        # Jamais en cache : l'image peut être en cours de copie vers sa racine, la page la redemande.
        introuvable = lambda: self._envoyer(  # noqa: E731
            404, json.dumps({"erreur": "Introuvable."}).encode("utf-8"), cache="no-store")
        valeurs = parse_qs(requete, keep_blank_values=True).get("chemin", [])
        if len(valeurs) != 1:
            return introuvable()
        brut = valeurs[0]
        if (not brut or chr(0) in brut or Path(brut).is_absolute() or brut[0] in "/\\"
                or Path(brut).suffix.lower() not in IMAGES):
            return introuvable()
        regl, _ = projet.reglages()
        conf = regl.get("images")
        racines = conf.get("racines") if isinstance(conf, dict) else None
        if not isinstance(racines, list):
            return introuvable()
        base = Path(regl["dossier"])
        try:
            cible = (base / brut).resolve()
            for racine in racines:
                if not isinstance(racine, str) or not racine:
                    continue
                try:
                    cible.relative_to((base / racine).resolve())
                except ValueError:
                    continue
                type_ = IMAGES.get(cible.suffix.lower())  # la cible d'un lien symbolique peut n'être pas une image
                if type_ and cible.is_file() and cible.stat().st_size <= IMAGE_MAX_OCTETS:
                    return self._envoyer(200, cible.read_bytes(), type_, cache="max-age=300")
            trouvee = self._image_du_projet(base, brut)
            if trouvee is not None:
                return self._envoyer(200, trouvee[0], trouvee[1], cache="max-age=300")
        except (OSError, ValueError):
            pass
        return introuvable()

    @staticmethod
    def _image_du_projet(base, brut):
        """Le filet : une image citée par un agent depuis la racine du PROJET (le parent de `.factory`, quand les
        réglages sont dans un dossier `.factory`) et jamais rangée sous une racine. `(octets, type)` ou `None`. Refus :
        « .. », chemin qui sort du projet (lien compris), extension hors PNG/JPEG, contenu qui n'en est pas un, fichier
        dans `.factory` lui-même (seules ses racines déclarées s'y servent) ou dans `.git`."""
        if base.name != ".factory" or ".." in Path(brut.replace("\\", "/")).parts:
            return None
        projet = base.parent.resolve()
        cible = (projet / brut).resolve()
        type_ = IMAGES.get(cible.suffix.lower())
        try:
            interne = cible.relative_to(projet).parts
        except ValueError:
            return None
        if (not type_ or not interne or interne[0].lower() in (".factory", ".git") or not cible.is_file()
                or cible.stat().st_size > IMAGE_MAX_OCTETS):
            return None
        octets = cible.read_bytes()
        signature = b"\x89PNG\r\n\x1a\n" if type_ == "image/png" else b"\xff\xd8\xff"
        return (octets, type_) if octets.startswith(signature) else None

    def _tranche(self, taille):
        """La tranche `(début, fin)` demandée par `Range: bytes=a-b` (une seule), `None` si l'en-tête est absent ou
        illisible (le fichier entier est alors envoyé), `"hors"` si elle est hors du fichier."""
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if not m or (m.group(1) == "" and m.group(2) == ""):
            return None
        if m.group(1) == "":                       # les n derniers octets
            n = int(m.group(2))
            return "hors" if n == 0 or taille == 0 else (max(taille - n, 0), taille - 1)
        debut = int(m.group(1))
        fin = min(int(m.group(2)), taille - 1) if m.group(2) else taille - 1
        return "hors" if debut >= taille or fin < debut else (debut, fin)

    def _livrable(self, cible, types=LIVRABLES, bac_a_sable=BAC_A_SABLE, par_tranches=False):
        """Envoie le fichier par morceaux (un livrable peut être gros) avec les en-têtes de son extension. Avec
        `par_tranches` (la lecture d'un son dans la page), `Range` est honoré : le téléphone ne lit pas sans cela."""
        if cible is None:
            return self._json(404, {"erreur": "Introuvable."})
        ext = cible.suffix.lower()
        type_, piece_jointe = types[ext]
        try:
            f = open(cible, "rb")
        except OSError:
            return self._json(404, {"erreur": "Introuvable."})
        with f:
            taille = os.fstat(f.fileno()).st_size
            tranche = self._tranche(taille) if par_tranches else None
            if tranche == "hors":
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{taille}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200 if tranche is None else 206)
            self.send_header("Content-Type", type_)
            if par_tranches:
                self.send_header("Accept-Ranges", "bytes")
            if tranche is not None:
                self.send_header("Content-Range", f"bytes {tranche[0]}-{tranche[1]}/{taille}")
                self.send_header("Content-Length", str(tranche[1] - tranche[0] + 1))
            else:
                self.send_header("Content-Length", str(taille))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if ext in bac_a_sable:
                self.send_header("Content-Security-Policy", "sandbox")
            if piece_jointe:
                ascii_ = "".join(c if c.isascii() and (c.isalnum() or c in "._-") else "_" for c in cible.name)
                self.send_header("Content-Disposition",
                                 f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(cible.name)}")
            self.end_headers()
            if self.command != "HEAD":
                if tranche is None:
                    shutil.copyfileobj(f, self.wfile, 1024 * 1024)
                else:
                    f.seek(tranche[0])
                    reste = tranche[1] - tranche[0] + 1
                    while reste > 0:
                        morceau = f.read(min(reste, 1024 * 1024))
                        if not morceau:
                            break
                        self.wfile.write(morceau)
                        reste -= len(morceau)

    def _telecharger(self, projet, requete):
        """Un livrable à télécharger (voir `Projet.telechargeable`), toujours en pièce jointe, 500 Mo au plus."""
        q = parse_qs(requete, keep_blank_values=True)
        fonc, chemins = q.get("fonctionnalite", []), q.get("chemin", [])
        if len(fonc) != 1 or len(chemins) != 1:
            return self._json(404, {"erreur": "Introuvable."})
        cible = projet.telechargeable(fonc[0], chemins[0])
        if cible is None:
            return self._json(404, {"erreur": "Introuvable."})
        try:
            if cible.stat().st_size > TELECHARGEMENT_MAX_OCTETS:
                return self._json(413, {"erreur": f"Fichier trop gros pour le bureau (plus de "
                                                  f"{TELECHARGEMENT_MAX_OCTETS // (1024 * 1024)} Mo)."})
        except OSError:
            return self._json(404, {"erreur": "Introuvable."})
        type_, piece_jointe = TELECHARGEABLES_JOINTS[releve.extension(cible.name)]
        if q.get("lecture") == ["1"] and cible.suffix.lower() in LECTURE_TEXTE:    # un .md se lit dans la page
            try:
                if cible.stat().st_size > LECTURE_TEXTE_MAX_OCTETS:
                    return self._json(413, {"erreur": "Document trop long pour être lu dans la page : téléchargez-le."})
            except OSError:
                return self._json(404, {"erreur": "Introuvable."})
            return self._livrable(cible, {cible.suffix.lower(): ("text/plain; charset=utf-8", False)}, (".md", ".txt"))
        lecture = q.get("lecture") == ["1"] and releve.extension(cible.name) in LECTURE_MEDIAS   # lu dans la page, rien d'autre
        return self._livrable(cible, {cible.suffix.lower(): (type_, piece_jointe and not lecture)}, (".html",),
                              par_tranches=lecture)

    # -- le relais vers le site en cours (fenêtre de validation) -----------
    def _ports_du_bureau(self):
        b = self.server.bureau if getattr(self.server, "distant", False) else self.server
        return {b.server_address[1]} | {e.server_address[1] for e in getattr(b, "ecouteurs", [])}

    def _apercu(self, morceaux):
        """`/apercu/<projet>/<décision>/<chemin>` : relaie GET, HEAD et POST vers le site qu'une décision `valider_etape`
        déclare sur l'ordinateur (`Projet.apercu`). Même garde que tout le bureau (code d'accès au téléphone). Pas de
        WebSocket (501), pas de cookie dans un sens ni dans l'autre, `Location` réécrite sous le préfixe."""
        if self.command not in APERCU_METHODES:
            self._vider_corps()
            return self._json(405, {"erreur": "Méthode non relayée."})
        morceaux_chemin = morceaux.path.split("/", 4)        # ['', 'apercu', projet, décision, reste]
        if len(morceaux_chemin) < 4 or not morceaux_chemin[2] or not morceaux_chemin[3]:
            self._vider_corps()
            return self._json(404, {"erreur": "Introuvable."})
        id_ = unquote(morceaux_chemin[2])
        projet = self.server.projet(None if id_ == "-" else id_)       # « - » : le projet d'un bureau à un seul projet
        cible = projet.apercu(unquote(morceaux_chemin[3])) if projet is not None else None
        if cible is None or cible[1] in self._ports_du_bureau():
            self._vider_corps()
            return self._json(404, {"erreur": "Aucun site à relayer pour cette validation."})
        prefixe = f"{APERCU}{morceaux_chemin[2]}/{morceaux_chemin[3]}"
        if len(morceaux_chemin) == 4:       # sans « / » final : les liens relatifs du site partiraient du mauvais dossier
            self._vider_corps()
            self.send_response(308)
            self.send_header("Location", prefixe + "/" + (f"?{morceaux.query}" if morceaux.query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        if self.headers.get("Upgrade"):
            self._vider_corps()
            return self._json(501, {"erreur": "Le relais du bureau ne transmet pas les WebSocket (rechargement à chaud)."})
        corps = None
        if self.command == "POST":
            if self.headers.get("Transfer-Encoding"):
                return self._json(411, {"erreur": "Longueur du corps requise."})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if not 0 <= n <= APERCU_MAX_CORPS:
                return self._json(413, {"erreur": "Corps trop gros pour le relais."})
            corps = self.rfile.read(n)
        hote, port = cible
        entetes = {k: self.headers[k] for k in APERCU_ENTETES_REQUETE if self.headers.get(k)}
        entetes["Host"] = f"[{hote}]:{port}" if ":" in hote else f"{hote}:{port}"
        entetes["Accept-Encoding"] = "identity"
        chemin = "/" + morceaux_chemin[4] + (f"?{morceaux.query}" if morceaux.query else "")
        connexion = http.client.HTTPConnection(hote, port, timeout=APERCU_DELAI_S)
        try:
            connexion.request(self.command, chemin, body=corps, headers=entetes)
            reponse = connexion.getresponse()
        except (OSError, http.client.HTTPException):
            connexion.close()
            return self._json(502, {"erreur": f"Le site ne répond pas sur le port {port} de l'ordinateur : est-il "
                                              "lancé ?"})
        try:
            self.send_response(reponse.status)
            for nom, valeur in reponse.getheaders():
                if nom.lower() not in APERCU_ENTETES_REPONSE:
                    continue
                if nom.lower() == "location":
                    valeur = _location_relayee(valeur, hote, port, prefixe)
                self.send_header(nom, valeur)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command == "HEAD":
                return None
            reste = APERCU_MAX_REPONSE
            while reste > 0:
                bloc = reponse.read(min(64 * 1024, reste))
                if not bloc:
                    break
                self.wfile.write(bloc)
                reste -= len(bloc)
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connexion.close()
        return None

    def _statique(self, chemin):
        brut = unquote(chemin)
        if "\x00" in brut or "\\" in brut:
            return self._json(404, {"erreur": "Introuvable."})
        if brut.endswith("/"):
            brut += "index.html"
        try:
            racine = WEB.resolve()
            cible = (racine / brut.lstrip("/")).resolve()
            cible.relative_to(racine)
        except (ValueError, OSError):
            return self._json(404, {"erreur": "Introuvable."})
        if not cible.is_file():
            return self._json(404, {"erreur": "Introuvable."})
        type_ = TYPES.get(cible.suffix.lower()) or mimetypes.guess_type(cible.name)[0] or "application/octet-stream"
        self._envoyer(200, cible.read_bytes(), type_)

    # -- POST -------------------------------------------------------------
    def _vider_corps(self):
        """Lit (et jette) un petit corps non consommé, pour que le refus arrive proprement."""
        try:
            self.rfile.read(min(max(int(self.headers.get("Content-Length", "0")), 0), 8192))
        except (ValueError, OSError):
            pass

    def do_POST(self):
        if self.server.distant:
            if self._garde_distant(post=True):
                self._vider_corps()
                return
        elif not self._hote_ok():
            self._vider_corps()
            return self._json(403, {"erreur": "Hôte refusé."})
        morceaux = urlsplit(self.path)
        chemin = morceaux.path
        if chemin.startswith(APERCU):
            return self._apercu(morceaux)
        if chemin == "/api/acces/revoquer":   # jamais atteint depuis un écouteur distant
            self._vider_corps()
            if self.headers.get("X-Bureau") != "1":
                return self._json(403, {"erreur": "En-têtes requis manquants."})
            if self.server.cles is None:
                return self._json(404, {"erreur": "Le bureau n'est ouvert à aucun téléphone."})
            self.server.cles.revoquer()
            return self._json(200, {"ok": True})
        if chemin == "/api/lancement":   # le premier lancement a été proposé : il ne le sera plus
            self._vider_corps()
            if self.headers.get("X-Bureau") != "1":
                return self._json(403, {"erreur": "En-têtes requis manquants."})
            self.server.lancement.marquer()
            return self._json(200, {"vu": True})
        if chemin == "/api/orchestrateur/lancer":
            self._vider_corps()
            if self.headers.get("X-Bureau") != "1":
                return self._json(403, {"erreur": "En-têtes requis manquants."})
            projet = self._projet(morceaux.query)
            if projet is None:
                return self._json(404, {"erreur": "Projet inconnu."})
            return self._json(*projet.lancer_orchestrateur())
        if chemin == "/api/echanges/vu":
            if (self.headers.get("X-Bureau") != "1"
                    or not self.headers.get("Content-Type", "").lower().startswith("application/json")):
                self._vider_corps()
                return self._json(403, {"erreur": "En-têtes requis manquants."})
            projet = self._projet(morceaux.query)
            try:
                longueur = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                longueur = -1
            if projet is None or not 0 < longueur <= 1024:
                self._vider_corps()
                return self._json(404 if projet is None else 400,
                                  {"erreur": "Projet inconnu." if projet is None else "Corps de requête invalide."})
            try:
                corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                return self._json(400, {"erreur": "Demande illisible."})
            return self._json(*projet.marquer_echange_vu(corps.get("t") if isinstance(corps, dict) else None))
        if chemin == "/api/projets/creer":
            if (self.headers.get("X-Bureau") != "1"
                    or not self.headers.get("Content-Type", "").lower().startswith("application/json")):
                self._vider_corps()
                return self._json(403, {"erreur": "En-têtes requis manquants."})
            try:
                longueur = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                longueur = -1
            if not 0 < longueur <= MAX_CORPS_REGLAGES * 4:
                return self._json(400, {"erreur": "Corps de requête invalide."})
            try:
                corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                return self._json(400, {"erreur": "Demande illisible."})
            return self._json(*self.server.creer_projet(corps))
        if chemin in ROUTES_CREATIONS:
            if (self.headers.get("X-Bureau") != "1"
                    or not self.headers.get("Content-Type", "").lower().startswith("application/json")):
                self._vider_corps()
                return self._json(403, {"erreur": "En-têtes requis manquants."})
            try:
                longueur = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                longueur = -1
            if not 0 < longueur <= MAX_CORPS_CREATIONS:
                return self._json(400, {"erreur": "Corps de requête invalide."})
            try:
                corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                return self._json(400, {"erreur": "Demande illisible."})
            if not isinstance(corps, dict):
                return self._json(400, {"erreur": "Demande illisible."})
            return self._json(*getattr(creations, ROUTES_CREATIONS[chemin])(self.server, corps))
        if chemin not in ("/api/reglages", "/api/demande"):
            return self._json(404, {"erreur": "Introuvable."})
        projet = self._projet(morceaux.query)
        if projet is None:
            self._vider_corps()
            return self._json(404, {"erreur": "Projet inconnu."})
        if (self.headers.get("X-Bureau") != "1"
                or not self.headers.get("Content-Type", "").lower().startswith("application/json")):
            self._vider_corps()
            return self._json(403, {"erreur": "En-têtes requis manquants."})
        try:
            longueur = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            longueur = -1
        if not 0 < longueur <= (MAX_CORPS_DEMANDE if chemin == "/api/demande" else MAX_CORPS_REGLAGES):
            return self._json(400, {"erreur": "Corps de requête invalide."})
        if chemin == "/api/demande":
            try:
                demande = json.loads(self.rfile.read(longueur).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                return self._json(400, {"erreur": "Demande illisible."})
            try:
                code, objet = projet.demande(demande)
            except Exception as e:  # jamais une connexion coupée sans réponse lisible
                code, objet = 500, {"erreur": f"Erreur du bureau : {e}"[:200]}
            return self._json(code, objet)
        try:
            corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
            if isinstance(corps, dict) and "lecons_auto" in corps and "charge_max" not in corps:
                nouveau = reglages.fixer_lecons_auto(projet.chemin_reglages, corps["lecons_auto"])
            else:
                if not isinstance(corps, dict) or "charge_max" not in corps:
                    raise ValueError("Le corps doit contenir « charge_max » ou « lecons_auto ».")
                nouveau = reglages.fixer_charge_max(projet.chemin_reglages, corps["charge_max"])
        except (ValueError, UnicodeDecodeError, RecursionError, reglages.ReglagesInvalides) as e:
            return self._json(400, {"erreur": str(e)})
        nouveau.pop("dossier", None)
        projet._cache_etat = (0.0, projet._cache_etat[1])   # le prochain état relit le réglage
        self._json(200, nouveau)


def creer(chemin_reglages=None, port=None, ouvrir=None, bureau=None, adresses=None, port_distant=None, cles=None,
          lancement=None, demarrer=None):
    """Un bureau sur un fichier de réglages (un projet d'id `projet`, sans sélecteur) ou sur un fichier de
    bureau (`bureau`, plusieurs projets). `ouvrir(url) -> str` remplace la lecture des sources de prix
    (les tests n'utilisent jamais Internet). Seul un fichier de bureau dont `acces` ouvre quelque chose ouvre des
    écouteurs distants : `adresses() -> {"tailscale", "reseau_local"}`, `cles` (par défaut
    `~/MyIAFactory/acces.json`) et `port_distant` (par défaut le même port) servent aux tests. `lancement` : le
    fichier du drapeau du premier lancement (`None` : en mémoire seulement ; `main` donne `~/MyIAFactory/lancement.json`)."""
    if (bureau is None) == (chemin_reglages is None):
        raise ValueError("Donner soit un fichier de réglages, soit un fichier de bureau.")
    if bureau is not None:
        conf = reglages.lire_bureau(bureau)
        projets = [(p["id"], p["chemin"]) for p in conf["projets"]]
        srv = Bureau(("127.0.0.1", conf["port"] if port is None else port), projets, ouvrir=ouvrir, multi=True,
                     lancement=lancement, demarrer=demarrer, fichier_bureau=bureau)
        if any(conf["acces"].values()):
            try:
                if adresses is None:
                    from installation.acces import adresses
                if cles is None:
                    cles = acces.Cles(Path("~/MyIAFactory/acces.json").expanduser())
                srv.ouvrir_distants(conf["acces"], adresses, cles, port_distant)
            except BaseException:
                srv.server_close()
                raise
        return srv
    if port is None:
        port = reglages.charger(chemin_reglages)["port"]
    return Bureau(("127.0.0.1", port), [("projet", Path(chemin_reglages))], ouvrir=ouvrir, multi=False,
                  lancement=lancement, demarrer=demarrer)


def _commande_charge(chemin):
    if not charge.WINDOWS:
        print("mesure indisponible, on laisse passer")
        return 0
    regl = reglages.charger(chemin)
    sonde = charge.Sonde()
    sonde.lire()
    time.sleep(5)
    m = sonde.lire()
    if m is None:
        print("mesure indisponible, on laisse passer")
        return 0
    valeur = charge.affichee(m["cpu"], m["memoire"])
    maximum = regl["charge_max"]
    if charge.feu_vert(valeur, maximum):
        print(f"ok : charge {valeur} % (max {maximum} %)")
        return 0
    print(f"attendre : charge {valeur} % (max {maximum} %)")
    return 1


def main(argv):
    p = argparse.ArgumentParser(prog="lancer.py", description="Le bureau vivant.")
    sous = p.add_subparsers(dest="commande", required=True)
    s = sous.add_parser("serveur", help="lance le serveur local")
    choix = s.add_mutually_exclusive_group(required=True)
    choix.add_argument("--reglages", help="chemin du fichier de réglages d'un projet (un seul projet)")
    choix.add_argument("--bureau", help="chemin du fichier du bureau, qui liste les réglages de plusieurs projets")
    s = sous.add_parser("charge", help="dit si la charge permet de lancer une étape locale")
    s.add_argument("--reglages", required=True, help="chemin du fichier de réglages du projet")
    args = p.parse_args(argv)
    try:
        if args.commande == "charge":
            return _commande_charge(Path(args.reglages))
        if getattr(args, "bureau", None):
            srv = creer(bureau=Path(args.bureau), lancement=LANCEMENT.expanduser())
        else:
            srv = creer(Path(args.reglages), lancement=LANCEMENT.expanduser())
    except reglages.ReglagesInvalides as e:
        print(e)
        return 2
    except OSError as e:
        print(f"Impossible de démarrer le serveur : {e}")
        return 2
    print(f"Le bureau est ouvert sur http://127.0.0.1:{srv.server_address[1]}/ (Ctrl+C pour arrêter)")
    for ligne in srv.annonces:
        print(ligne)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
