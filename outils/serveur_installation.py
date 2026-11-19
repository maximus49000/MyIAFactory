"""Installation à la demande des capacités d'un serveur distant : aperçu en lecture seule, puis installation sur accord.

Le moteur travaille sur un serveur dont le système est déjà installé et joignable ; il ne touche jamais au système
d'exploitation. Chaque capacité manquante est installée par l'étape distante que le catalogue lui associe (script
`mise_en_place.sh`, déposé dans le dossier privé du serveur). Les capacités non installables ne sont jamais lancées.

Garanties : aucune écriture sans `accord is True` ; une seule installation à la fois (verrou pid) ; l'état réel est
relu par sonde au début et à la fin (jamais l'état en cache) ; une panne de réseau donne « inconnue », jamais
« absente » ; l'état `serveurs-etat.json` ne contient aucun secret. Tout passe par `ssh` (injectable).
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import plateforme_acces
import plateforme_ssh
import serveur_etat
from plateforme import RACINE_SERVEUR, SCRIPT_DISTANT, pid_vivant
from serveur_capacites import CATALOGUE, bloquees, manquantes_pour
from serveur_modele import ecrire_atomique

ETAT = "serveurs-etat.json"
VERROU = "serveurs-installation.lock"
VERROU_JEUNE_S = 30
DELAI_DEFAUT_S = 600
DELAIS_ETAPE_S = {"docker": 1200, "durcissement": 900, "android_build": 1800, "android_emulateur": 1800, "unity_cli": 300}
LONGUEUR_MAX = 200
STATUTS_ETAPE = ("fait", "a_faire", "bloque")


class ErreurInstallation(Exception):
    """Refus d'installer (accès, accord, verrou) : message français et `geste` (ce que l'utilisateur peut faire)."""

    def __init__(self, message, geste=""):
        super().__init__(message)
        self.geste = geste


def _maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texte(valeur, serveur):
    """Texte sans secret (chemin de clé masqué), sur une ligne, tronqué."""
    brut = " ".join(str(valeur or "").split())
    return plateforme_acces.masquer(brut, [str(getattr(serveur, "cle", "") or "")])[:LONGUEUR_MAX]


# ---------------------------------------------------------------- état

def lire_etat(dossier=plateforme_acces.DOSSIER):
    """Contenu de `serveurs-etat.json` ; dictionnaire vide si absent, abîmé ou de forme inattendue. Jamais d'exception."""
    try:
        donnees = json.loads((Path(dossier) / ETAT).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in donnees.items() if isinstance(v, dict)} if isinstance(donnees, dict) else {}


INTERROMPUE = "Installation interrompue : relancez ou vérifiez."
_VERROU_PROCESSUS = threading.Lock()        # une seule installation à la fois dans CE processus (le fichier ne suffit pas)


def installation_en_cours(dossier=plateforme_acces.DOSSIER, vivant=pid_vivant):
    """Une installation tourne-t-elle ? Verrou tenu par un processus vivant (ou par ce processus, tant que son verrou
    interne est pris), ou fichier verrou vide récent."""
    chemin = Path(dossier) / VERROU
    return chemin.exists() and _verrou_tenu(chemin, vivant, _VERROU_PROCESSUS.locked())


def _degrader(caps):
    """Copie de `caps` où chaque capacité restée « en_cours » est devenue « inconnue » (installation interrompue)."""
    return {i: (_entree("inconnue", INTERROMPUE, "Relancez l'installation ou lancez un aperçu pour constater l'état.")
                if c.get("statut") == "en_cours" else c) for i, c in caps.items()}


def lire_etat_vivant(dossier=plateforme_acces.DOSSIER, vivant=pid_vivant):
    """Comme `lire_etat`, mais sans installation vivante les « en_cours » périmés (fenêtre fermée en cours de route)
    sont présentés « inconnue ». Ne modifie aucun fichier. Jamais d'exception."""
    etat = lire_etat(dossier)
    try:
        if installation_en_cours(dossier, vivant):
            return etat
    except Exception:
        pass
    sortie = {}
    for sid, e in etat.items():
        caps = e.get("capacites")
        inst = e.get("installation")
        sortie[sid] = {**e,
                       "capacites": _degrader(caps) if isinstance(caps, dict) else caps,
                       "installation": {**inst, "en_cours": False} if isinstance(inst, dict) else inst}
    return sortie


def _ecrire_etat(dossier, serveur_id, capacites, en_cours, debut):
    tout = lire_etat(dossier)
    tout[serveur_id] = {"capacites": capacites, "installation": {"en_cours": en_cours, "debut": debut}}
    Path(dossier).mkdir(parents=True, exist_ok=True)
    ecrire_atomique(Path(dossier) / ETAT, json.dumps(tout, ensure_ascii=False, indent=2) + "\n")


def _entree(statut, detail="", geste=""):
    return {"statut": statut, "detail": detail, "geste": geste, "maj": _maintenant()}


# ---------------------------------------------------------------- aperçu

def apercu(serveur, actions, ssh=plateforme_ssh, dossier=plateforme_acces.DOSSIER):
    """Ce qu'il faudrait installer pour `actions`, sans rien modifier (lecture SSH seulement, aucun fichier écrit).

    `taille_go` et `duree_min` ne comptent que les capacités installables. Serveur injoignable ou état illisible :
    `{"erreur", "etat"}` avec toutes les capacités « inconnue », et rien n'est calculé comme manquant."""
    inconnu = {i: serveur_etat.INCONNUE for i in CATALOGUE}
    try:
        requises = manquantes_pour(actions, set())      # fermeture des actions
    except ValueError as e:
        raise ErreurInstallation(str(e), "Choisissez des actions connues.") from e
    refus = serveur_etat.refus_acces(serveur, ssh=ssh)
    if refus:
        return {"erreur": _texte(refus, serveur), "etat": inconnu}
    etat = serveur_etat.sonder(serveur, ssh=ssh)
    illisibles = [i for i in requises if etat.get(i) != serveur_etat.PRESENTE and etat.get(i) != serveur_etat.ABSENTE]
    if illisibles:
        return {"erreur": "État du serveur illisible ou serveur injoignable : " + ", ".join(illisibles) + ".",
                "etat": {**inconnu, **etat}}
    installees = {i for i, s in etat.items() if s == serveur_etat.PRESENTE}
    manquantes = manquantes_pour(actions, installees)
    installables = [CATALOGUE[i] for i in manquantes if CATALOGUE[i].installable]
    return {"manquantes": manquantes,
            "taille_go": float(sum(c.taille_go for c in installables)),
            "duree_min": int(sum(c.duree_min for c in installables)),
            "bloquees": bloquees(manquantes),
            "etat": etat}


# ---------------------------------------------------------------- verrou

def _verrou_tenu(chemin, vivant, soi_tenu=False):
    """Pid d'un autre processus vivant, ou fichier vide/illisible trop récent pour être périmé (il est créé puis rempli).
    Notre propre pid : tenu seulement si `soi_tenu` (une installation de ce processus est en cours)."""
    try:
        autre = json.loads(chemin.read_text(encoding="utf-8")).get("pid")
    except (OSError, ValueError, AttributeError):
        autre = None
    if isinstance(autre, int):
        return soi_tenu if autre == os.getpid() else bool(vivant(autre))
    try:
        return time.time() - chemin.stat().st_mtime < VERROU_JEUNE_S
    except OSError:
        return False


def _prendre_verrou(dossier, vivant):
    chemin = Path(dossier) / VERROU
    Path(dossier).mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            with open(chemin, "x", encoding="utf-8") as f:
                f.write(json.dumps({"pid": os.getpid()}))
            return chemin
        except FileExistsError:
            if _verrou_tenu(chemin, vivant):
                return None
            try:
                chemin.unlink()
            except OSError:
                return None
    return None


# ---------------------------------------------------------------- étapes distantes

def _analyser(sortie):
    for ligne in reversed((sortie or "").strip().splitlines()):
        if ligne.lstrip().startswith("{"):
            try:
                d = json.loads(ligne)
                return d if isinstance(d, dict) else None
            except ValueError:
                return None
    return None


def _deposer_script(serveur, ssh):
    """Dépose le script dans le dossier privé du serveur (0700, jamais /tmp). (statut, détail) ; None si réussi."""
    texte = (RACINE_SERVEUR / "mise_en_place.sh").read_bytes().decode("utf-8")   # octets du dépôt, fins de ligne intactes
    commande = f'install -d -m 700 "$HOME/myiafactory" && umask 077 && cat > "{SCRIPT_DISTANT}" && chmod 700 "{SCRIPT_DISTANT}"'
    code, _o, erreur = ssh.executer(serveur_etat.cible(serveur), commande, serveur.cle, stdin=texte, delai=60)
    if code == 0:
        return None
    return ("inconnue" if code in (255, 124) else "bloque",
            f"Dépôt du script sur le serveur impossible : {_texte(erreur, serveur)}")


def _lancer_etape(serveur, ssh, etape):
    """(statut, détail) d'une étape distante : l'unique objet JSON de sa sortie ; « inconnue » si la connexion tombe."""
    delai = DELAIS_ETAPE_S.get(etape, DELAI_DEFAUT_S)
    code, sortie, erreur = ssh.executer(serveur_etat.cible(serveur), f'bash "{SCRIPT_DISTANT}" --etape {etape}',
                                        serveur.cle, delai=delai)
    d = _analyser(sortie)
    if not d or d.get("statut") not in STATUTS_ETAPE:
        if code == 124:
            return "inconnue", ("Délai dépassé : l'étape peut encore tourner sur le serveur, attendez avant de relancer "
                                f"({etape}).")
        if code == 255:
            return "inconnue", f"Serveur injoignable pendant l'étape {etape} : {_texte(erreur, serveur)}"
        return "bloque", f"Réponse illisible du serveur (code {code}) : {_texte(erreur, serveur)}"
    return d["statut"], _texte(d.get("detail", ""), serveur)


# ---------------------------------------------------------------- installation

GESTE_ETAPE = "Lisez le détail, corrigez le point indiqué puis relancez l'installation."


def installer(serveur, actions, accord, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, dormir=time.sleep,
              vivant=pid_vivant):
    """Installe les capacités manquantes pour `actions`, dans l'ordre, après accord explicite (`accord is True`).

    Renvoie `{"capacites": {id: {statut, detail, geste, maj}}, "ok": bool, "erreur": str | None}`.
    `ErreurInstallation` pour un refus (accord, accès, installation déjà en cours), sans rien avoir modifié.
    `dormir` n'est pas utilisé : paramètre réservé aux tests et conservé pour la parité avec les autres moteurs."""
    if accord is not True:
        raise ErreurInstallation("Installation refusée : l'accord n'a pas été donné.",
                                 "Validez l'aperçu (taille, durée) pour donner votre accord.")
    try:
        requises = manquantes_pour(actions, set())
    except ValueError as e:
        raise ErreurInstallation(str(e), "Choisissez des actions connues.") from e
    deja = ErreurInstallation("Une installation est déjà en cours sur ce poste.",
                              "Attendez sa fin (ou son abandon) puis relancez.")
    if not _VERROU_PROCESSUS.acquire(blocking=False):       # même processus : double clic, deuxième fil
        raise deja
    try:
        refus = serveur_etat.refus_acces(serveur, ssh=ssh)
        if refus:
            raise ErreurInstallation(_texte(refus, serveur), "Corrigez l'accès au serveur puis relancez.")
        try:
            verrou = _prendre_verrou(dossier, vivant)
        except OSError as e:
            raise ErreurInstallation(f"Dossier de l'installation inutilisable : {_texte(e, serveur)}",
                                     "Vérifiez les droits d'écriture du dossier de configuration.") from e
        if verrou is None:
            raise deja
        debut = _maintenant()
        caps = {}
        try:
            try:
                return _derouler(serveur, requises, actions, ssh, dossier, caps, debut)
            finally:
                caps.update(_degrader(caps))                # aucune capacité ne reste « en_cours » (interruption comprise)
                _ecrire_etat(dossier, serveur.id, caps, False, debut)
        finally:
            try:
                verrou.unlink()
            except OSError:
                pass
    finally:
        _VERROU_PROCESSUS.release()


def _derouler(serveur, requises, actions, ssh, dossier, caps, debut):
    def ecrire(en_cours=True):
        _ecrire_etat(dossier, serveur.id, caps, en_cours, debut)

    def resultat(erreur=None):
        return {"capacites": caps, "ok": erreur is None and all(
            caps[i]["statut"] in ("fait", "presente") for i in requises), "erreur": erreur}

    sondes = serveur_etat.sonder(serveur, ssh=ssh)             # état réel, jamais le cache
    if any(sondes.get(i) not in (serveur_etat.PRESENTE, serveur_etat.ABSENTE) for i in requises):
        for i in requises:
            caps[i] = _entree("inconnue", "Serveur injoignable ou état illisible : rien n'a été installé.",
                              "Vérifiez la connexion au serveur puis relancez.")
        return resultat("Serveur injoignable : rien n'a été installé.")
    presentes = {i for i, s in sondes.items() if s == serveur_etat.PRESENTE}
    a_faire = manquantes_pour(actions, presentes)
    for i in requises:
        caps[i] = _entree("presente", "Déjà présente.") if i in presentes else _entree("a_faire", "À installer.")
    ecrire()

    fait, erreur, arret = set(presentes), None, None            # arret : capacité qui interrompt toute la suite
    script_depose = False
    for i in a_faire:
        cap = CATALOGUE[i]
        if arret:
            caps[i] = _entree("a_faire", f"En attente de {arret}.", GESTE_ETAPE)
            continue
        attente = [d for d in cap.depend if d not in fait]
        if attente:
            caps[i] = _entree("a_faire", "En attente de " + ", ".join(attente) + ".", GESTE_ETAPE)
            continue
        if not cap.installable:
            caps[i] = _entree("bloque", _texte(f"Non installable automatiquement : {cap.raison_non_installable}", serveur),
                              _texte(cap.raison_non_installable, serveur))
            ecrire()
            continue
        caps[i] = _entree("en_cours", f"Installation de « {cap.libelle} » en cours.")
        ecrire()
        try:
            r = None if script_depose else _deposer_script(serveur, ssh)
            script_depose = script_depose or r is None
            statut, detail = r or _lancer_etape(serveur, ssh, cap.etape)
        except Exception as e:                                   # réseau, hôte invalide, fichier du script absent
            statut, detail = "inconnue", f"Étape interrompue : {_texte(e, serveur) or type(e).__name__}"
        if statut == "fait":
            fait.add(i)
            caps[i] = _entree("fait", detail)
        elif statut == "inconnue":
            caps[i] = _entree("inconnue", detail, "Vérifiez la connexion au serveur (et que l'étape ne tourne plus) puis relancez.")
            arret, erreur = i, f"Installation interrompue, serveur injoignable ou délai dépassé : {detail}"
        else:
            caps[i] = _entree(statut, detail, GESTE_ETAPE)
            arret = i
        ecrire()

    if erreur is None:                                           # relecture finale : la présence réelle fait foi
        finales = serveur_etat.sonder(serveur, ssh=ssh)
        for i in requises:
            if caps[i]["statut"] != "fait":
                continue
            if finales.get(i) == serveur_etat.ABSENTE:
                caps[i] = _entree("bloque", "L'étape s'est terminée mais la capacité n'est pas détectée sur le serveur.",
                                  GESTE_ETAPE)
            elif finales.get(i) != serveur_etat.PRESENTE:
                caps[i] = _entree("inconnue", "Présence non vérifiable après l'étape (serveur injoignable).",
                                  "Relancez un aperçu pour constater l'état.")
    return resultat(erreur)
