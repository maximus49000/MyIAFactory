"""Serveur local : la page, l'état, la charge, le conseil et le réglage de charge."""
import argparse
import json
import mimetypes
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import charge, equipe, etat, reglages

WEB = Path(__file__).resolve().parent / "web"
DELAI_ETAT_S = 2.0
PAS_SONDE_S = 5
PAS_HISTORIQUE_S = 60
TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".glb": "model/gltf-binary", ".svg": "image/svg+xml"}


class Bureau(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, adresse, chemin_reglages):
        super().__init__(adresse, Handler)
        self.chemin_reglages = Path(chemin_reglages)
        dossier = self.chemin_reglages.parent
        self.equipe = equipe.Equipe(dossier / "equipe.json")
        self.historique = charge.Historique(dossier / "charge-historique.jsonl")
        self.sonde = charge.Sonde()
        self.lisseur = charge.Lisseur(60)
        self.mesure = None  # dernière lecture brute de la sonde
        self._verrou = threading.Lock()
        self._cache_etat = (0.0, None)
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._boucle_sonde, daemon=True)
        self._fil.start()

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
        with self._verrou:
            t, e = self._cache_etat
            if e is not None and time.monotonic() - t < DELAI_ETAT_S:
                return e
            regl, err = self.reglages()
            maintenant = datetime.now().astimezone()
            e = etat.erreur(err, maintenant) if err else etat.lire(regl, self.equipe, maintenant)
            self._cache_etat = (time.monotonic(), e)
            return e

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
    def _envoyer(self, code, corps, type_="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
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
        chemin = urlsplit(self.path).path
        if chemin == "/api/etat":
            return self._json(200, self.server.etat())
        if chemin == "/api/charge":
            return self._json(200, self.server.charge())
        if chemin == "/api/conseil":
            return self._json(200, self.server.conseil())
        self._statique(chemin)

    do_HEAD = do_GET

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
    def do_POST(self):
        if not self._hote_ok():
            return self._json(403, {"erreur": "Hôte refusé."})
        if urlsplit(self.path).path != "/api/reglages":
            return self._json(404, {"erreur": "Introuvable."})
        if (self.headers.get("X-Bureau") != "1"
                or not self.headers.get("Content-Type", "").lower().startswith("application/json")):
            return self._json(403, {"erreur": "En-têtes requis manquants."})
        try:
            longueur = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            longueur = -1
        if not 0 < longueur <= 4096:
            return self._json(400, {"erreur": "Corps de requête invalide."})
        try:
            corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
            if not isinstance(corps, dict) or "charge_max" not in corps:
                raise ValueError("Le corps doit contenir « charge_max ».")
            nouveau = reglages.fixer_charge_max(self.server.chemin_reglages, corps["charge_max"])
        except (ValueError, UnicodeDecodeError, reglages.ReglagesInvalides) as e:
            return self._json(400, {"erreur": str(e)})
        nouveau.pop("dossier", None)
        self._json(200, nouveau)


def creer(chemin_reglages, port=None):
    if port is None:
        port = reglages.charger(chemin_reglages)["port"]
    return Bureau(("127.0.0.1", port), chemin_reglages)


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
