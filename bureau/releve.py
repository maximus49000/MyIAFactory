"""Le relevé : valider, normaliser, obtenir (fichier ou commande)."""
import copy
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

MAX_SERVICES = 6
DELAI_COMMANDE_S = 10


def _est_dict(x):
    return isinstance(x, dict)


def _liste_de_dicts(r, cle, erreurs):
    v = r.get(cle)
    if not isinstance(v, list):
        erreurs.append(f"« {cle} » est obligatoire et doit être une liste.")
        return []
    ok = []
    for i, el in enumerate(v):
        if _est_dict(el):
            ok.append(el)
        else:
            erreurs.append(f"« {cle} » : l'élément {i + 1} doit être un objet.")
    return ok


def _doublons(elements, cle, nom, erreurs):
    vus = set()
    for el in elements:
        v = el.get(cle)
        if not isinstance(v, str) or not v:
            erreurs.append(f"{nom} : « {cle} » est obligatoire (texte non vide).")
            continue
        if v in vus:
            erreurs.append(f"{nom} : identifiant en double « {v} ».")
        vus.add(v)
    return vus


def valider(r):
    """Messages d'erreur en français ; liste vide si le relevé est valide."""
    if not _est_dict(r):
        return ["Le relevé doit être un objet JSON."]
    erreurs = []
    if r.get("version") != 1:
        erreurs.append("« version » doit valoir 1.")
    if not isinstance(r.get("projet"), str) or not r.get("projet"):
        erreurs.append("« projet » est obligatoire (texte non vide).")
    factory = r.get("factory")
    if not _est_dict(factory) or factory.get("etat") not in ("en marche", "en pause"):
        erreurs.append("« factory.etat » doit valoir « en marche » ou « en pause ».")
    services = _liste_de_dicts(r, "services", erreurs)
    colonnes = _liste_de_dicts(r, "colonnes", erreurs)
    titulaires = _liste_de_dicts(r, "titulaires", erreurs)
    taches = _liste_de_dicts(r, "taches", erreurs)
    if len(services) > MAX_SERVICES:
        erreurs.append(f"Au plus {MAX_SERVICES} services (il y en a {len(services)}).")
    ids_services = _doublons(services, "id", "Services", erreurs)
    ids_colonnes = _doublons(colonnes, "id", "Colonnes", erreurs)
    cles = _doublons(titulaires, "cle", "Titulaires", erreurs)
    _doublons(taches, "id", "Tâches", erreurs)
    chefs = 0
    for t in titulaires:
        cle = t.get("cle")
        if t.get("lieu") not in ("local", "cloud"):
            erreurs.append(f"Titulaire « {cle} » : « lieu » doit valoir « local » ou « cloud ».")
        if t.get("chef") is True:
            chefs += 1
        elif t.get("service") not in ids_services:
            erreurs.append(f"Titulaire « {cle} » : service inconnu « {t.get('service')} ».")
    if chefs > 1:
        erreurs.append("Un seul titulaire peut avoir « chef » à vrai.")
    for t in taches:
        i = t.get("id")
        if t.get("colonne") not in ids_colonnes:
            erreurs.append(f"Tâche « {i} » : colonne inconnue « {t.get('colonne')} ».")
        if not isinstance(t.get("titre"), str):
            erreurs.append(f"Tâche « {i} » : « titre » est obligatoire.")
        if not isinstance(t.get("active"), bool):
            erreurs.append(f"Tâche « {i} » : « active » doit être vrai ou faux.")
        if t.get("titulaire") is not None and t.get("titulaire") not in cles:
            erreurs.append(f"Tâche « {i} » : titulaire inconnu « {t.get('titulaire')} ».")
        if "postit" in t and not isinstance(t["postit"], bool):
            erreurs.append(f"Tâche « {i} » : « postit » doit être vrai ou faux.")
        for champ in ("etape", "maj"):
            if not _texte_ou_nul(t.get(champ)):
                erreurs.append(f"Tâche « {i} » : « {champ} » doit être un texte.")
    _verifier_facultatifs(r, services, colonnes, titulaires, erreurs)
    return erreurs


def _texte_ou_nul(v):
    return v is None or isinstance(v, str)


def _entier_positif(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _verifier_facultatifs(r, services, colonnes, titulaires, erreurs):
    """Les champs facultatifs, s'ils sont là, doivent avoir le bon type : la page s'y fie."""
    factory = r.get("factory")
    if _est_dict(factory) and not _texte_ou_nul(factory.get("depuis")):
        erreurs.append("« factory.depuis » doit être une date (texte).")
    for nom, elements in (("Service", services), ("Colonne", colonnes)):
        for el in elements:
            if not isinstance(el.get("nom"), str):
                erreurs.append(f"{nom} « {el.get('id')} » : « nom » est obligatoire (texte).")
    for t in titulaires:
        cle = t.get("cle")
        if "modele" in t and not isinstance(t["modele"], str):
            erreurs.append(f"Titulaire « {cle} » : « modele » doit être un texte.")
        for champ in ("permanent", "chef"):
            if champ in t and not isinstance(t[champ], bool):
                erreurs.append(f"Titulaire « {cle} » : « {champ} » doit être vrai ou faux.")
        f = t.get("fraicheur_min")
        if f is not None and (isinstance(f, bool) or not isinstance(f, (int, float)) or f <= 0):
            erreurs.append(f"Titulaire « {cle} » : « fraicheur_min » doit être un nombre de minutes.")
    if "decisions" in r and not _entier_positif(r["decisions"]):
        erreurs.append("« decisions » doit être un nombre entier positif ou nul.")
    if "file" not in r:
        return
    file = r["file"]
    if not _est_dict(file):
        erreurs.append("« file » doit être un objet.")
        return
    if "reste" in file and not _entier_positif(file["reste"]):
        erreurs.append("« file.reste » doit être un nombre entier positif ou nul.")
    visibles = file.get("visibles", [])
    if not isinstance(visibles, list):
        erreurs.append("« file.visibles » doit être une liste.")
        return
    for k, q in enumerate(visibles):
        if not _est_dict(q) or not isinstance(q.get("id"), str) or not q.get("id") \
                or not _texte_ou_nul(q.get("titre")):
            erreurs.append(f"« file.visibles » : l'élément {k + 1} doit avoir un « id » et un « titre » (textes).")


def normaliser(r):
    """Applique les valeurs par défaut. Ne modifie pas l'argument."""
    n = copy.deepcopy(r)
    if not _est_dict(n.get("file")):
        n["file"] = {}
    n["file"].setdefault("visibles", [])
    n["file"].setdefault("reste", 0)
    n.setdefault("decisions", 0)
    for t in n["taches"]:
        t.setdefault("titulaire", None)
        t.setdefault("postit", True)
        t.setdefault("etape", "")
        t.setdefault("maj", None)
    for t in n["titulaires"]:
        t.setdefault("modele", "?")
        t.setdefault("permanent", False)
        t.setdefault("chef", False)
    if not any(t["chef"] for t in n["titulaires"]):
        n["titulaires"].append({"cle": "chef", "lieu": "local", "chef": True,
                                "permanent": True, "modele": "?"})
    return n


def _tuer_arbre(p):
    """Tue la commande et tous ses descendants (ils peuvent garder sa sortie ouverte)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                           capture_output=True, timeout=5)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


def _executer(cmd, cwd):
    """(code, sortie, erreurs) ; lève TimeoutExpired si la commande ou un de ses descendants
    tient au-delà de DELAI_COMMANDE_S. Ne bloque jamais plus longtemps que ce délai (+ quelques s)."""
    delai = DELAI_COMMANDE_S
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
               else {"start_new_session": True})
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, shell=False, **options)
    lu = {}

    def lire(nom, flux):
        try:
            lu[nom] = flux.read()
        except (OSError, ValueError):
            lu[nom] = b""

    fils = [threading.Thread(target=lire, args=(n, f), daemon=True)
            for n, f in (("sortie", p.stdout), ("erreurs", p.stderr))]
    for f in fils:
        f.start()
    fin = time.monotonic() + delai
    try:
        p.wait(timeout=delai)
        for f in fils:
            f.join(max(0.0, fin - time.monotonic()))
        if any(f.is_alive() for f in fils):  # un descendant tient encore la sortie
            raise subprocess.TimeoutExpired(cmd, delai)
    except subprocess.TimeoutExpired:
        _tuer_arbre(p)
        raise
    return p.returncode, lu.get("sortie", b""), lu.get("erreurs", b"")


def _lire_texte(regl, source):
    base = Path(regl.get("dossier") or ".")
    if "fichier" in source:
        return (base / source["fichier"]).read_text(encoding="utf-8-sig")
    cmd = source["commande"]
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
        raise ValueError("« commande » doit être une liste de textes.")
    cwd = base / source.get("dossier", ".")
    code, sortie, erreurs = _executer(cmd, str(cwd))
    if code != 0:
        detail = erreurs.decode("utf-8", "replace").strip()[:200]
        raise ValueError(f"La commande du relevé a échoué (code {code}). {detail}".strip())
    return sortie.decode("utf-8-sig")


def obtenir(regl):
    """(relevé normalisé, None) ou (None, message). Ne lève jamais."""
    try:
        source = regl.get("releve") or {}
        if not _est_dict(source) or not ("fichier" in source or "commande" in source):
            return None, "Aucun relevé configuré : ajoutez « releve » aux réglages (voir docs/releve.md)."
        try:
            texte = _lire_texte(regl, source)
        except subprocess.TimeoutExpired:
            return None, f"La commande du relevé a dépassé {DELAI_COMMANDE_S} s."
        except FileNotFoundError as e:
            return None, f"Relevé introuvable : {e.filename or e}"
        except (OSError, ValueError) as e:
            return None, f"Relevé illisible : {e}"
        try:
            donnees = json.loads(texte)
        except ValueError as e:
            return None, f"Relevé illisible (JSON incomplet ou invalide) : {e}"
        erreurs = valider(donnees)
        if erreurs:
            return None, "Relevé invalide : " + " ".join(erreurs[:5])
        return normaliser(donnees), None
    except Exception as e:  # jamais d'exception vers l'appelant
        return None, f"Relevé inutilisable : {e}"
