"""Serveur local : la page, l'état, la charge, le conseil, le réglage de charge et la facturation."""
import argparse
import json
import mimetypes
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import charge, cout, demandes, equipe, etat, prix, reglages
from .usage import HistoriqueUsage

WEB = Path(__file__).resolve().parent / "web"
DELAI_ETAT_S = 2.0
PAS_SONDE_S = 5
PAS_HISTORIQUE_S = 60
PAS_PRIX_S = 3600  # le fil des prix se réveille toutes les heures ; il ne lit les sources qu'une fois par jour
ATTENTE_PREMIERS_PRIX_S = 25
TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".glb": "model/gltf-binary", ".svg": "image/svg+xml"}
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
IMAGE_MAX_OCTETS = 20 * 1024 * 1024


def images_declarees(regl):
    """Vrai si les réglages déclarent au moins une racine d'images (sinon les tâches n'ont pas de vignettes)."""
    conf = regl.get("images")
    racines = conf.get("racines") if isinstance(conf, dict) else None
    return isinstance(racines, list) and any(isinstance(r, str) and r for r in racines)


class Bureau(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, adresse, chemin_reglages, ouvrir=None):
        super().__init__(adresse, Handler)
        self.chemin_reglages = Path(chemin_reglages)
        dossier = self.chemin_reglages.parent
        self.equipe = equipe.Equipe(dossier / "equipe.json")
        self.historique = charge.Historique(dossier / "charge-historique.jsonl")
        self.usage = HistoriqueUsage(dossier / "usage-historique.jsonl")
        self.table_prix = prix.TablePrix(dossier / "prix-historique.jsonl")
        self.ouvrir = ouvrir or prix.ouvrir_url  # la seule porte vers Internet ; remplacée dans les tests
        self.etat_prix = None  # résultat de la dernière mise à jour des prix
        self._premiers_prix = threading.Event()
        self._usage_integre = None
        self._usage_connu = bool(self.usage.lire())
        self.sonde = charge.Sonde()
        self.lisseur = charge.Lisseur(60)
        self.mesure = None  # dernière lecture brute de la sonde
        self._verrou = threading.Lock()
        self._cache_etat = (0.0, None)
        self.dernier_releve = None  # dernier relevé normalisé valide (sert à vérifier les demandes)
        self._verrou_demandes = threading.Lock()
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._boucle_sonde, daemon=True)
        self._fil.start()
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
    def etat(self):
        t, e = self._cache_etat
        if e is not None and time.monotonic() - t < DELAI_ETAT_S:
            return e
        # Une seule lecture du relevé à la fois. Pendant qu'elle dure (une commande peut prendre
        # jusqu'à 10 s), les autres demandes reçoivent le dernier état au lieu d'attendre.
        if not self._verrou.acquire(blocking=e is None):
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
                e, r = etat.lire_avec_releve(regl, self.equipe, maintenant)
            if r is not None:
                self.dernier_releve = r
                self._integrer_usage(r)
            if e.get("version", 1) >= 3 and self._usage_connu:
                e["dossier"]["facturation"] = True
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
        # Le premier jour, les prix sont lus avant de calculer (sans attendre indéfiniment).
        self._premiers_prix.wait(ATTENTE_PREMIERS_PRIX_S)
        regl, _ = self.reglages()

        def prix_de(modele, date_iso):
            return prix.prix_effectif(self.table_prix, regl, modele, date_iso)

        f = cout.facturation(self.usage.lire(), prix_de, r, periode, datetime.now().astimezone())
        if regl.get("prix_automatiques") is False:
            message = "Prix automatiques coupés (réglage « prix_automatiques ») : seules les corrections à la main comptent."
        elif self.etat_prix is None:
            message = "Prix en cours de lecture."
        else:
            message = None if self.etat_prix["ok"] else self.etat_prix["message"]
        return 200, {**f, "disponible": True, "periode": periode, "maj": self.table_prix.derniere_maj(),
                     "message": message}

    # -- demandes ---------------------------------------------------------
    def demande(self, demande):
        """(code HTTP, objet JSON). Les demandes passent une à une."""
        self.etat()  # rafraîchit le dernier relevé valide si l'état est périmé
        r = self.dernier_releve
        if r is None:
            return 409, {"erreur": "Relevé indisponible."}
        demande = demandes.nettoyer(demande)
        message = demandes.verifier(demande, r)
        if message:
            return 400, {"erreur": message}
        with self._verrou_demandes:
            regl, _ = self.reglages()
            ok, message = demandes.envoyer(regl, demande)
            self._cache_etat = (0.0, self._cache_etat[1])  # relire le relevé tout de suite
        if not ok:
            return 502, {"erreur": message}
        return 200, {"ok": True}

    # -- charge -----------------------------------------------------------
    def _boucle_sonde(self):
        dernier_historique = 0.0
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
                self.mesure = m
                self.lisseur.ajouter(t, m["cpu"])
                if t - dernier_historique >= PAS_HISTORIQUE_S:
                    dernier_historique = t
                    valeur = charge.affichee(self.lisseur.moyenne(), m["memoire"])
                    self.historique.noter(t, valeur, etat.agents_locaux_au_travail(self.etat()))
            except Exception:
                pass  # la mesure ne doit jamais faire tomber le serveur

    def charge(self):
        regl, _ = self.reglages()
        mach = charge.machine()
        base = {"max": regl["charge_max"], "coeurs": mach["coeurs"],
                "memoire_totale_go": mach["memoire_totale_go"]}
        m = self.mesure
        if m is None:
            return {**base, "disponible": False, "cpu": None, "memoire": None, "charge": None, "feu_vert": True}
        cpu = self.lisseur.moyenne() if self.lisseur.moyenne() else m["cpu"]
        valeur = charge.affichee(cpu, m["memoire"])
        return {**base, "disponible": True, "cpu": round(cpu, 1), "memoire": round(m["memoire"], 1),
                "charge": valeur, "feu_vert": charge.feu_vert(valeur, regl["charge_max"])}

    def conseil(self):
        return charge.conseiller(self.historique.lire(), charge.machine())

    def server_close(self):
        self._arret.set()
        super().server_close()


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

    def _hote_ok(self):
        # protège contre les pages tierces qui viseraient le serveur local (DNS rebinding)
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    # -- GET --------------------------------------------------------------
    def do_GET(self):
        if not self._hote_ok():
            return self._json(403, {"erreur": "Hôte refusé."})
        morceaux = urlsplit(self.path)
        chemin = morceaux.path
        if chemin == "/api/image":
            return self._image(morceaux.query)
        if chemin == "/api/etat":
            return self._json(200, self.server.etat())
        if chemin == "/api/charge":
            return self._json(200, self.server.charge())
        if chemin == "/api/conseil":
            return self._json(200, self.server.conseil())
        if chemin == "/api/facturation":
            periodes = parse_qs(morceaux.query, keep_blank_values=True).get("periode", ["7j"])
            code, objet = self.server.facturation(periodes[0] if len(periodes) == 1 else None)
            return self._json(code, objet)
        self._statique(chemin)

    do_HEAD = do_GET

    def _image(self, requete):
        """Sert une image du projet, seulement depuis les racines déclarées (`images.racines`)."""
        introuvable = lambda: self._json(404, {"erreur": "Introuvable."})  # noqa: E731
        valeurs = parse_qs(requete, keep_blank_values=True).get("chemin", [])
        if len(valeurs) != 1:
            return introuvable()
        brut = valeurs[0]
        if (not brut or chr(0) in brut or Path(brut).is_absolute() or brut[0] in "/\\"
                or Path(brut).suffix.lower() not in IMAGES):
            return introuvable()
        regl, _ = self.server.reglages()
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
        if not self._hote_ok():
            self._vider_corps()
            return self._json(403, {"erreur": "Hôte refusé."})
        chemin = urlsplit(self.path).path
        if chemin not in ("/api/reglages", "/api/demande"):
            return self._json(404, {"erreur": "Introuvable."})
        if (self.headers.get("X-Bureau") != "1"
                or not self.headers.get("Content-Type", "").lower().startswith("application/json")):
            self._vider_corps()
            return self._json(403, {"erreur": "En-têtes requis manquants."})
        try:
            longueur = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            longueur = -1
        if not 0 < longueur <= (16384 if chemin == "/api/demande" else 4096):
            return self._json(400, {"erreur": "Corps de requête invalide."})
        if chemin == "/api/demande":
            try:
                demande = json.loads(self.rfile.read(longueur).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                return self._json(400, {"erreur": "Demande illisible."})
            code, objet = self.server.demande(demande)
            return self._json(code, objet)
        try:
            corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
            if not isinstance(corps, dict) or "charge_max" not in corps:
                raise ValueError("Le corps doit contenir « charge_max ».")
            nouveau = reglages.fixer_charge_max(self.server.chemin_reglages, corps["charge_max"])
        except (ValueError, UnicodeDecodeError, RecursionError, reglages.ReglagesInvalides) as e:
            return self._json(400, {"erreur": str(e)})
        nouveau.pop("dossier", None)
        self._json(200, nouveau)


def creer(chemin_reglages, port=None, ouvrir=None):
    """`ouvrir(url) -> str` remplace la lecture des sources de prix (les tests n'utilisent jamais Internet)."""
    if port is None:
        port = reglages.charger(chemin_reglages)["port"]
    return Bureau(("127.0.0.1", port), chemin_reglages, ouvrir=ouvrir)


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
    for nom, aide in (("serveur", "lance le serveur local"),
                      ("charge", "dit si la charge permet de lancer une étape locale")):
        s = sous.add_parser(nom, help=aide)
        s.add_argument("--reglages", required=True, help="chemin du fichier de réglages du projet")
    args = p.parse_args(argv)
    chemin = Path(args.reglages)
    try:
        if args.commande == "charge":
            return _commande_charge(chemin)
        srv = creer(chemin)
    except reglages.ReglagesInvalides as e:
        print(e)
        return 2
    except OSError as e:
        print(f"Impossible de démarrer le serveur : {e}")
        return 2
    print(f"Le bureau est ouvert sur http://127.0.0.1:{srv.server_address[1]}/ (Ctrl+C pour arrêter)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
