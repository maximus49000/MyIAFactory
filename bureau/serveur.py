"""Serveur local : la page, l'état, la charge, le conseil, le réglage de charge et la facturation."""
import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import threading
import time
from datetime import datetime
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import acces, catalogue, charge, cout, demandes, equipe, etat, kpi, prix, reglages
from .usage import HistoriqueUsage

WEB = Path(__file__).resolve().parent / "web"
DELAI_ETAT_S = 2.0
PAS_SONDE_S = 5
PAS_HISTORIQUE_S = 60
PAS_PRIX_S = 3600  # le fil des prix se réveille toutes les heures ; il ne lit les sources qu'une fois par jour
ATTENTE_PREMIERS_PRIX_S = 25
MAX_CORPS_DEMANDE = 28 * 1024 * 1024  # 4 images de 5 Mo en base64, plus le texte
MAX_CORPS_REGLAGES = 4096
GARDE_DOUBLON_S = 10  # une même fonctionnalité ou un même message envoyé deux fois de suite : une seule demande
GARDE_CHALLENGE_S = 120  # un challenge envoyé mais pas encore au relevé : pas de second envoi sur sa cible
TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".glb": "model/gltf-binary", ".svg": "image/svg+xml",
         ".webmanifest": "application/manifest+json; charset=utf-8", ".png": "image/png"}
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
IMAGE_MAX_OCTETS = 20 * 1024 * 1024
ROUTES_PROJET = ("/api/couts", "/api/document", "/api/methode", "/api/etat", "/api/charge", "/api/conseil", "/api/facturation", "/api/kpi", "/api/image",
                 "/api/catalogue", "/api/livrable")
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


def images_declarees(regl):
    """Vrai si les réglages déclarent au moins une racine d'images (sinon les tâches n'ont pas de vignettes)."""
    conf = regl.get("images")
    racines = conf.get("racines") if isinstance(conf, dict) else None
    return isinstance(racines, list) and any(isinstance(r, str) and r for r in racines)


class Projet:
    """Tout ce que le bureau tient pour un fichier de réglages : équipe, historiques, prix, état, demandes."""

    def __init__(self, id_, chemin_reglages, ouvrir=None):
        self.id = id_
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
        self._derniere_creation = None  # (empreinte, heure monotone) de la dernière fonctionnalité ou du dernier message
        self._challenges_envoyes = {}  # (type, id) de la cible -> heure d'envoi (monotone)
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
            e["images_ok"] = images_declarees(regl)
            self._cache_etat = (time.monotonic(), e)
            return e
        finally:
            self._verrou.release()

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
        return cout.facturation(usages, prix_de, r, periode, datetime.now().astimezone())

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
            regl, _ = self.reglages()
            cibles = {}
            cible = demande.get("cible") if isinstance(demande, dict) and demande.get("type") == "challenge" else None
            if isinstance(cible, dict) and cible.get("type") in ("kpi", "source"):  # seules à recalculer
                cibles = self.cibles_calculees(r, regl)
            elements = None
            if isinstance(demande, dict) and demande.get("type") == "retour_element":
                elements = catalogue.ids(regl, demande.get("fonctionnalite"))  # None : catalogue illisible
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
            ok, message = demandes.envoyer(regl, demande)
            if ok and cle:
                self._challenges_envoyes[cle] = time.monotonic()
            if ok and empreinte is not None:
                self._derniere_creation = (empreinte, time.monotonic())
            self._cache_etat = (0.0, self._cache_etat[1])  # relire le relevé tout de suite
        if not ok:
            return 502, {"erreur": message}
        return 200, {"ok": True}

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

    def fermer(self):
        self._arret.set()
        if self._fil_prix is not None:
            self._fil_prix.join(5)  # qu'il n'écrive plus dans le dossier une fois le serveur fermé


class Bureau(ThreadingHTTPServer):
    """Le serveur : un ou plusieurs projets, une seule sonde de charge (la charge est celle de la machine).
    Il écoute sur 127.0.0.1 ; les écouteurs distants (`ouvrir_distants`) servent le même bureau, avec code d'accès."""
    daemon_threads = True
    distant = False

    def __init__(self, adresse, projets, ouvrir=None, multi=True):
        super().__init__(adresse, Handler)
        self.multi = multi
        self.cles = None
        self.ecouteurs = []
        self.distants = []    # [{"genre", "url"}]
        self.annonces = []    # ce que le terminal dit au lancement
        self.projets = {id_: Projet(id_, chemin, ouvrir=ouvrir) for id_, chemin in projets}
        self.sonde = charge.Sonde()
        self.lisseur = charge.Lisseur(60)
        self.mesure = None  # dernière lecture brute de la sonde
        self._dernier_historique = 0.0
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._boucle_sonde, daemon=True)
        self._fil.start()

    def projet(self, id_=None):
        """Le projet d'id donné ; `None` → le premier ; inconnu → `None`."""
        if id_ is None:
            return next(iter(self.projets.values()))
        return self.projets.get(id_)

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
        return {"multi": self.multi, "projets": lignes}

    def ouvrir_distants(self, ouverts, adresses, cles, port_distant=None):
        """Un écouteur par accès ouvert dont l'adresse est trouvée (même port que 127.0.0.1, sauf `port_distant`).
        Une adresse introuvable est dite et ignorée."""
        self.cles = cles
        cles.cle()   # créée maintenant plutôt qu'à la première requête
        trouvees = adresses()
        for genre in reglages.ACCES:
            if not ouverts.get(genre):
                continue
            ip = trouvees.get(genre)
            nom = NOMS_ACCES[genre]
            if not ip:
                self.annonces.append(f"{nom} : adresse introuvable, cet accès est ignoré.")
                continue
            port = self.server_address[1] if port_distant is None else port_distant
            try:
                e = Ecouteur((ip, port), self, genre)
            except OSError as err:
                self.annonces.append(f"{nom} : impossible d'écouter sur {ip}:{port} ({err}) ; accès ignoré.")
                continue
            threading.Thread(target=e.serve_forever, daemon=True).start()
            url = f"http://{e.hote}"
            self.ecouteurs.append(e)
            self.distants.append({"genre": genre, "url": url})
            self.annonces.append(f"{nom} : {url} (code d'accès exigé ; associez le téléphone depuis la page de "
                                 "l'ordinateur)")

    def infos_acces(self):
        """Pour la page de l'ordinateur : les adresses ouvertes et un code d'association neuf."""
        if not self.distants:
            return {"adresses": [], "code": None, "expire": None}
        code = self.cles.code_association()
        expire = datetime.fromtimestamp(self.cles.expiration(code)).isoformat(timespec="seconds")
        return {"adresses": [dict(d) for d in self.distants], "code": code, "expire": expire}

    def shutdown(self):
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

    def _associer(self, requete):
        codes = parse_qs(requete, keep_blank_values=True).get("code", [])
        cle = self.server.cles.echanger(codes[0]) if len(codes) == 1 else None
        if cle is None:
            return self._refus_401()
        self.send_response(302)
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
            self._associer(morceaux.query)
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
        if chemin == "/api/projets":
            return self._json(200, self.server.liste())
        if chemin == "/api/acces":   # jamais atteint depuis un écouteur distant
            return self._json(200, self.server.infos_acces())
        if chemin not in ROUTES_PROJET:
            return self._statique(chemin)
        projet = self._projet(morceaux.query)
        if projet is None:
            return self._json(404, {"erreur": "Projet inconnu."})
        if chemin == "/api/image":
            return self._image(projet, morceaux.query)
        if chemin == "/api/etat":
            return self._json(200, projet.etat())
        if chemin == "/api/charge":
            return self._json(200, self.server.charge(projet))
        if chemin == "/api/conseil":
            return self._json(200, projet.conseil())
        if chemin == "/api/couts":
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
        introuvable = lambda: self._json(404, {"erreur": "Introuvable."})  # noqa: E731
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
        except (OSError, ValueError):
            pass
        return introuvable()

    def _livrable(self, cible, types=LIVRABLES, bac_a_sable=BAC_A_SABLE):
        """Envoie le fichier par morceaux (un livrable peut être gros) avec les en-têtes de son extension."""
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
            self.send_response(200)
            self.send_header("Content-Type", type_)
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
                shutil.copyfileobj(f, self.wfile, 1024 * 1024)

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
        if chemin == "/api/acces/revoquer":   # jamais atteint depuis un écouteur distant
            self._vider_corps()
            if self.headers.get("X-Bureau") != "1":
                return self._json(403, {"erreur": "En-têtes requis manquants."})
            if self.server.cles is None:
                return self._json(404, {"erreur": "Le bureau n'est ouvert à aucun téléphone."})
            self.server.cles.revoquer()
            return self._json(200, {"ok": True})
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
            if not isinstance(corps, dict) or "charge_max" not in corps:
                raise ValueError("Le corps doit contenir « charge_max ».")
            nouveau = reglages.fixer_charge_max(projet.chemin_reglages, corps["charge_max"])
        except (ValueError, UnicodeDecodeError, RecursionError, reglages.ReglagesInvalides) as e:
            return self._json(400, {"erreur": str(e)})
        nouveau.pop("dossier", None)
        self._json(200, nouveau)


def creer(chemin_reglages=None, port=None, ouvrir=None, bureau=None, adresses=None, port_distant=None, cles=None):
    """Un bureau sur un fichier de réglages (un projet d'id `projet`, sans sélecteur) ou sur un fichier de
    bureau (`bureau`, plusieurs projets). `ouvrir(url) -> str` remplace la lecture des sources de prix
    (les tests n'utilisent jamais Internet). Seul un fichier de bureau dont `acces` ouvre quelque chose ouvre des
    écouteurs distants : `adresses() -> {"tailscale", "reseau_local"}`, `cles` (par défaut
    `~/MyIAFactory/acces.json`) et `port_distant` (par défaut le même port) servent aux tests."""
    if (bureau is None) == (chemin_reglages is None):
        raise ValueError("Donner soit un fichier de réglages, soit un fichier de bureau.")
    if bureau is not None:
        conf = reglages.lire_bureau(bureau)
        projets = [(p["id"], p["chemin"]) for p in conf["projets"]]
        srv = Bureau(("127.0.0.1", conf["port"] if port is None else port), projets, ouvrir=ouvrir, multi=True)
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
    return Bureau(("127.0.0.1", port), [("projet", Path(chemin_reglages))], ouvrir=ouvrir, multi=False)


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
            srv = creer(bureau=Path(args.bureau))
        else:
            srv = creer(Path(args.reglages))
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
