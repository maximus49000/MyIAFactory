"""Les prix des modèles et le taux dollar-euro : lecture des sources, table datée, mise à jour.

Deux sources publiques, dont l'adresse est une constante du code (jamais un réglage) :
- la liste de prix de la communauté LiteLLM (dollars par token) ;
- le taux de référence quotidien de la BCE (dollars pour un euro).

Chaque lecture réussie ajoute une ligne datée à `prix-historique.jsonl`. Le prix qui compte pour un
usage est le dernier enregistré à sa date ou avant : un prix qui change ne bouge jamais un coût passé.
Après la première ligne, une ligne ne garde que les modèles dont le prix a changé.
"""
import json
import math
import os
import ssl
import threading
import urllib.error
import urllib.request
from datetime import date as Date
from pathlib import Path
from urllib.parse import urlsplit

URL_PRIX = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
URL_TAUX = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
DELAI_S = 10
MAX_OCTETS = 5 * 1024 * 1024
FACTEUR_ABSURDE = 10
MAX_NOM = 200
MAX_NOTE = 600
CHAMPS = ("entree", "sortie", "cache_lecture", "cache_ecriture")
CHAMPS_SOURCE = {"entree": "input_cost_per_token", "sortie": "output_cost_per_token",
                 "cache_lecture": "cache_read_input_token_cost",
                 "cache_ecriture": "cache_creation_input_token_cost"}


def _nombre(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _positif(x):
    return _nombre(x) and x > 0


def _jour(texte):
    """« AAAA-MM-JJ » tiré d'une date ISO, ou None si illisible."""
    if not isinstance(texte, str) or len(texte) < 10:
        return None
    try:
        return Date.fromisoformat(texte[:10]).isoformat()
    except ValueError:
        return None


# --- Lecture des sources -------------------------------------------------------------------------

def lire_prix(texte_json):
    """{modèle: {entree, sortie, cache_lecture, cache_ecriture}} en dollars par million de tokens.

    Les entrées illisibles sont ignorées ; lève ValueError si rien n'est lisible."""
    try:
        donnees = json.loads(texte_json)
    except (ValueError, TypeError) as e:
        raise ValueError(f"liste de prix illisible ({e})")
    if not isinstance(donnees, dict):
        raise ValueError("liste de prix illisible (un objet JSON est attendu)")
    out = {}
    for nom, v in donnees.items():
        if not isinstance(nom, str) or not nom or len(nom) > MAX_NOM or not isinstance(v, dict):
            continue
        brut = {c: v.get(s) for c, s in CHAMPS_SOURCE.items()}
        if not (_nombre(brut["entree"]) and _nombre(brut["sortie"])):
            continue
        out[nom] = {c: (round(x * 1_000_000, 6) if _nombre(x) else None) for c, x in brut.items()}
    if not out:
        raise ValueError("aucun prix lisible dans la liste")
    return out


def lire_taux(texte_xml):
    """(date ISO, euros pour un dollar) d'après le flux quotidien de la BCE. Lève ValueError."""
    import xml.etree.ElementTree as ET
    if not isinstance(texte_xml, str) or "<!DOCTYPE" in texte_xml or "<!ENTITY" in texte_xml:
        raise ValueError("taux illisible (document refusé)")
    try:
        racine = ET.fromstring(texte_xml)
    except ET.ParseError as e:
        raise ValueError(f"taux illisible ({e})")
    for jour in racine.iter():
        if not jour.tag.endswith("Cube") or "time" not in jour.attrib:
            continue
        for c in jour:
            if c.attrib.get("currency") == "USD":
                try:
                    dollars = float(c.attrib.get("rate", ""))
                except ValueError:
                    raise ValueError("taux illisible (valeur du dollar)")
                if not _positif(dollars) or _jour(jour.attrib["time"]) is None:
                    raise ValueError("taux illisible (valeur ou date du dollar)")
                return _jour(jour.attrib["time"]), 1 / dollars
    raise ValueError("taux illisible (pas de cours du dollar)")


class _RedirectionHttps(urllib.request.HTTPRedirectHandler):
    """Une redirection ne peut pas faire sortir la requête du https."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise urllib.error.HTTPError(newurl, code, "redirection refusée (https seulement)", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ouvrir_url(url):
    """Le texte d'une des deux sources. N'ouvre jamais une autre adresse. Lève en cas d'échec."""
    if url not in (URL_PRIX, URL_TAUX) or urlsplit(url).scheme != "https":
        raise ValueError("adresse refusée")
    ouvreur = urllib.request.build_opener(_RedirectionHttps())
    try:
        with ouvreur.open(url, timeout=DELAI_S) as reponse:
            octets = reponse.read(MAX_OCTETS + 1)
    except (ssl.SSLCertVerificationError, urllib.error.URLError) as e:
        if isinstance(e, ssl.SSLCertVerificationError) or isinstance(getattr(e, "reason", None),
                                                                     ssl.SSLCertVerificationError):
            hote = urlsplit(url).hostname
            raise ValueError(f"certificat de {hote} non reconnu par cet ordinateur (sous Windows, ouvrir "
                             f"une fois {url} dans Edge suffit en général à installer son autorité)") from e
        raise
    if len(octets) > MAX_OCTETS:
        raise ValueError(f"réponse trop grande (plus de {MAX_OCTETS // (1024 * 1024)} Mo)")
    return octets.decode("utf-8-sig", "replace")


# --- La table datée ------------------------------------------------------------------------------

def _entree_valide(e):
    return (isinstance(e, dict) and _positif(e.get("entree")) and _positif(e.get("sortie"))
            and all(e.get(c) is None or _positif(e.get(c)) for c in ("cache_lecture", "cache_ecriture")))


def _ligne_valide(d):
    if not isinstance(d, dict) or not isinstance(d.get("date"), str) or _jour(d["date"]) != d["date"]:
        return None
    modeles = d.get("modeles")
    if not isinstance(modeles, dict):
        return None
    taux = d.get("taux")
    note = d.get("note")
    return {"date": d["date"], "taux": taux if _positif(taux) else None,
            "modeles": {n: {c: e.get(c) for c in CHAMPS} for n, e in modeles.items()
                        if isinstance(n, str) and _entree_valide(e)},
            "note": note[:MAX_NOTE] if isinstance(note, str) and note else None}


class TablePrix:
    """Les prix lus, ligne par ligne : {date, taux (euros pour un dollar), modeles (dollars/million)}."""

    def __init__(self, chemin):
        self.chemin = Path(chemin)
        self._verrou = threading.RLock()
        self._lignes = None
        self._memo = {}

    def _charger(self):
        if self._lignes is None:
            lignes = []
            try:
                texte = self.chemin.read_text(encoding="utf-8", errors="replace")
            except OSError:
                texte = ""
            for brut in texte.splitlines():
                try:
                    ligne = _ligne_valide(json.loads(brut))
                except ValueError:
                    continue
                if ligne:
                    lignes.append(ligne)
            self._lignes = lignes
        return self._lignes

    def etat(self):
        """{modèle: dernier prix connu en dollars par million}."""
        with self._verrou:
            courant = {}
            for ligne in self._charger():
                courant.update(ligne["modeles"])
            return courant

    def dernier_taux(self):
        with self._verrou:
            return next((x["taux"] for x in reversed(self._charger()) if x["taux"]), None)

    def derniere_maj(self):
        """Date de la dernière lecture réussie des prix des modèles, ou None."""
        with self._verrou:
            lignes = self._charger()
            return lignes[-1]["date"] if lignes else None

    def complet_le(self, jour):
        """Vrai si, ce jour-là, les prix et le taux ont tous deux été lus."""
        with self._verrou:
            du_jour = [x for x in self._charger() if x["date"] == jour]
            return bool(du_jour) and any(x["taux"] for x in du_jour)

    def note_du(self, jour):
        """Ce que la dernière lecture de ce jour a dû rejeter (texte), ou None."""
        with self._verrou:
            du_jour = [x for x in self._charger() if x["date"] == jour]
            return du_jour[-1]["note"] if du_jour else None

    def ajouter(self, date_iso, modeles, taux, note=None):
        """Ajoute une lecture : seuls les modèles dont le prix a changé sont écrits. `note` : ce que
        cette lecture a rejeté, gardé pour le redire tant qu'aucune lecture ne l'a remplacée."""
        jour = _jour(date_iso)
        if jour is None:
            raise ValueError("date illisible")
        with self._verrou:
            courant = self.etat()
            change = {n: {c: e.get(c) for c in CHAMPS} for n, e in modeles.items()
                      if _entree_valide(e) and courant.get(n) != {c: e.get(c) for c in CHAMPS}}
            ligne = {"date": jour, "taux": taux if _positif(taux) else None, "modeles": change,
                     "note": note[:MAX_NOTE] if isinstance(note, str) and note else None}
            lignes = self._charger() + [ligne]
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.chemin.with_name(self.chemin.name + ".tmp")
            tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes), encoding="utf-8")
            os.replace(tmp, self.chemin)
            self._lignes = lignes
            self._memo = {}

    def prix_a(self, modele, date_iso):
        """(prix en euros par million | None, date du prix, ancien).

        Dernier prix enregistré à la date ou avant ; avant le premier prix, le premier, avec ancien=True."""
        jour = _jour(date_iso) or ""
        with self._verrou:
            cle = (modele, jour)
            if cle not in self._memo:
                self._memo[cle] = self._prix_a(modele, jour)
            return self._memo[cle]

    def _prix_a(self, modele, jour):
        lignes = self._charger()
        if not lignes:
            return None, None, False
        avant = [x for x in lignes if x["date"] <= jour]
        date_etat = avant[-1]["date"] if avant else None
        ancien = False
        entree = next((x["modeles"][modele] for x in reversed(avant) if modele in x["modeles"]), None)
        if entree is None:
            premiere = next((x for x in lignes if modele in x["modeles"]), None)
            if premiere is None:
                return None, date_etat, False
            entree, date_etat, ancien = premiere["modeles"][modele], premiere["date"], True
        taux = next((x["taux"] for x in reversed(avant) if x["taux"]), None)
        if taux is None:
            premiere = next((x for x in lignes if x["taux"]), None)
            if premiere is None:
                return None, date_etat, ancien
            taux, ancien = premiere["taux"], True
            date_etat = max(date_etat or "", premiere["date"])
        return {c: (entree[c] * taux if entree.get(c) is not None else None) for c in CHAMPS}, date_etat, ancien


# --- La mise à jour ------------------------------------------------------------------------------

def _absurde(ancien, nouveau):
    """Négatif, nul, ou plus d'un facteur 10 d'écart avec le précédent."""
    if not _positif(nouveau):
        return True
    return nouveau > ancien * FACTEUR_ABSURDE or nouveau * FACTEUR_ABSURDE < ancien


def _court(e):
    return str(e).strip()[:200] or e.__class__.__name__


def actualiser(table, ouvrir, aujourdhui_iso):
    """Lit les deux sources au plus une fois par jour. {"ok": bool, "message": str}. Ne lève jamais.

    Une source injoignable ou illisible, ou une valeur absurde : le dernier prix connu est gardé, et dit."""
    jour = _jour(aujourdhui_iso)
    if jour is None:
        return {"ok": False, "message": "Date du jour illisible : prix non mis à jour."}
    try:
        if table.complet_le(jour):
            note = table.note_du(jour)  # la lecture du jour a rejeté une valeur : cela reste vrai et dit
            if note:
                return {"ok": False, "message": f"Prix du {jour} ; {note}."}
            return {"ok": True, "message": f"Prix du {jour}."}
        precedente = table.derniere_maj()
        depuis = f"Prix du {precedente}" if precedente else "Aucun prix enregistré"
        try:
            lus = lire_prix(ouvrir(URL_PRIX))
        except Exception as e:
            return {"ok": False, "message": f"{depuis}, mise à jour impossible : {_court(e)}."}
        erreurs = []
        taux = None
        try:
            _, taux = lire_taux(ouvrir(URL_TAUX))
            avant = table.dernier_taux()
            if avant and _absurde(avant, taux):
                taux = None
                erreurs.append("taux dollar-euro gardé (valeur absurde dans la source)")
        except Exception as e:
            erreurs.append(f"taux dollar-euro, mise à jour impossible : {_court(e)}")
        courant = table.etat()
        gardes, rejetes = {}, []
        for nom, e in lus.items():
            ancien = courant.get(nom)
            nouveau = dict(e)
            for c in ("cache_lecture", "cache_ecriture"):
                if nouveau[c] is not None and nouveau[c] <= 0:
                    nouveau[c] = None
            if ancien is None:
                if _positif(nouveau["entree"]) and _positif(nouveau["sortie"]):
                    gardes[nom] = nouveau  # un modèle neuf gratuit ou faux est ignoré : « prix inconnu »
                continue
            if any(_absurde(ancien[c], e[c]) for c in CHAMPS
                   if ancien.get(c) is not None and (c in ("entree", "sortie") or e[c] is not None)):
                rejetes.append(nom)
                continue
            gardes[nom] = nouveau
        note = None
        if rejetes:
            noms = ", ".join(sorted(rejetes)[:5]) + ("…" if len(rejetes) > 5 else "")
            note = (f"valeur absurde dans la source pour {len(rejetes)} modèle(s) ({noms}) : "
                    "dernier prix gardé")
            erreurs.append(note)
        table.ajouter(jour, gardes, taux, note)
        if erreurs:
            return {"ok": False, "message": f"Prix du {jour} ; " + " ; ".join(erreurs) + "."}
        return {"ok": True, "message": f"Prix du {jour}."}
    except Exception as e:  # jamais d'exception vers le serveur
        return {"ok": False, "message": f"Mise à jour des prix impossible : {_court(e)}."}


# --- Le prix qui compte, réglages compris --------------------------------------------------------

def _correction(prix_regl, nom, jour):
    """La correction à la main la plus récente datée du jour ou avant, ou None."""
    if not isinstance(prix_regl, dict):
        return None
    v = prix_regl.get(nom)
    candidates = v if isinstance(v, list) else [v]
    meilleure = None
    for c in candidates:
        if not (isinstance(c, dict) and _positif(c.get("entree")) and _positif(c.get("sortie"))):
            continue
        d = _jour(c.get("date"))
        if d is None or d > jour:
            continue
        if meilleure is None or d >= meilleure[1]:
            meilleure = (c, d)
    if meilleure is None:
        return None
    c, d = meilleure
    return {k: (c.get(k) if _positif(c.get(k)) else None) for k in CHAMPS}, d, False


def prix_effectif(table, regl, modele, date_iso):
    """(prix en euros par million | None, date du prix, ancien) pour un modèle du relevé.

    La correction à la main (réglage `prix`) passe avant l'automatique à partir de sa date ;
    `alias_modeles` rapproche le nom du relevé de celui de la liste de prix."""
    regl = regl if isinstance(regl, dict) else {}
    jour = _jour(date_iso) or ""
    alias = regl.get("alias_modeles")
    nom = modele
    if isinstance(alias, dict) and isinstance(alias.get(modele), str) and alias.get(modele):
        nom = alias[modele]
    for n in (modele, nom):
        corr = _correction(regl.get("prix"), n, jour)
        if corr:
            return corr
    return table.prix_a(nom, jour)
