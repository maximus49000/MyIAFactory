"""Le relevé : valider, normaliser, obtenir (fichier ou commande)."""
import copy
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

MAX_SERVICES = 8
MAX_IMAGES = 40
SCHEMAS_LIENS = ("https", "http", "claude")
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


def lien_valide(url):
    """Schéma https, http ou claude ; ni espace ni caractère de contrôle."""
    if not isinstance(url, str) or not url:
        return False
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return False
    schema, sep, reste = url.partition(":")
    return bool(sep) and schema.lower() in SCHEMAS_LIENS and len(reste) > 0


def valider(r):
    """Messages d'erreur en français ; liste vide si le relevé est valide."""
    if not _est_dict(r):
        return ["Le relevé doit être un objet JSON."]
    erreurs = []
    if r.get("version") not in (1, 2) or isinstance(r.get("version"), bool):
        erreurs.append("« version » doit valoir 1 ou 2.")
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
    if r.get("version") == 2:
        _verifier_v2(r, titulaires, taches, cles, erreurs)
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


def _liste_facultative(v, champ, erreurs):
    """La liste de dicts d'un champ facultatif, ou [] (avec erreur) si le type est faux."""
    if v is None:
        return []
    if not isinstance(v, list):
        erreurs.append(f"{champ} doit être une liste.")
        return []
    ok = []
    for k, el in enumerate(v):
        if _est_dict(el):
            ok.append(el)
        else:
            erreurs.append(f"{champ} : l'élément {k + 1} doit être un objet.")
    return ok


def _texte(v):
    return isinstance(v, str)


def _verifier_v2(r, titulaires, taches, cles, erreurs):
    """Champs facultatifs de la version 2 (ignorés en version 1)."""
    vus = set()
    for a in _liste_facultative(r.get("actions"), "« actions »", erreurs):
        i = a.get("id")
        if not _texte(i) or not i:
            erreurs.append("« actions » : « id » est obligatoire (texte non vide).")
        elif i in vus:
            erreurs.append(f"« actions » : identifiant en double « {i} ».")
        vus.add(i)
        if not _texte(a.get("libelle")):
            erreurs.append(f"« actions » : le bouton « {i} » doit avoir un « libelle » (texte).")
        if "lien" in a and not lien_valide(a["lien"]):
            erreurs.append(f"« actions » : le bouton « {i} » a un « lien » refusé (https, http ou claude).")
        if "confirmer" in a and not _texte(a["confirmer"]):
            erreurs.append(f"« actions » : le bouton « {i} » : « confirmer » doit être un texte.")
        if "actif" in a and not isinstance(a["actif"], bool):
            erreurs.append(f"« actions » : le bouton « {i} » : « actif » doit être vrai ou faux.")
    types = _liste_facultative(r.get("types"), "« types »", erreurs)
    ids_types = set()
    for t in types:
        if not _texte(t.get("id")) or not t.get("id") or not _texte(t.get("nom")):
            erreurs.append("« types » : chaque type a un « id » (non vide) et un « nom » (textes).")
        else:
            ids_types.add(t["id"])
    vus = set()
    for le in _liste_facultative(r.get("lecons"), "« lecons »", erreurs):
        i = le.get("id")
        if not _texte(i) or not i:
            erreurs.append("« lecons » : « id » est obligatoire (texte non vide).")
        elif i in vus:
            erreurs.append(f"« lecons » : identifiant en double « {i} ».")
        vus.add(i)
        if le.get("agent") not in cles:
            erreurs.append(f"« lecons » : la leçon « {i} » vient d'un agent inconnu « {le.get('agent')} ».")
        if not _texte(le.get("texte")):
            erreurs.append(f"« lecons » : la leçon « {i} » doit avoir un « texte ».")
        for champ in ("tache", "date"):
            if not _texte_ou_nul(le.get(champ)):
                erreurs.append(f"« lecons » : la leçon « {i} » : « {champ} » doit être un texte.")
        if le.get("verdict_demande") not in (None, "valider", "invalider"):
            erreurs.append(f"« lecons » : la leçon « {i} » : « verdict_demande » doit valoir "
                           "« valider » ou « invalider ».")
    for ti in titulaires:
        cle = ti.get("cle")
        for champ in ("prenom", "specialite"):
            if champ in ti and not _texte(ti[champ]):
                erreurs.append(f"Titulaire « {cle} » : « {champ} » doit être un texte.")
        for le in _liste_facultative(ti.get("lecons"), f"Titulaire « {cle} » : « lecons »", erreurs):
            if not _texte(le.get("id")) or not _texte(le.get("texte")) \
                    or le.get("etat") not in ("à valider", "validée"):
                erreurs.append(f"Titulaire « {cle} » : « lecons » : chaque leçon a « id », « texte » "
                               "et « etat » (« à valider » ou « validée »).")
    for t in taches:
        i = t.get("id")
        if t.get("type") is not None:
            if not _texte(t["type"]):
                erreurs.append(f"Tâche « {i} » : « type » doit être un texte.")
            elif types and t["type"] not in ids_types:
                erreurs.append(f"Tâche « {i} » : type inconnu « {t['type']} ».")
        for champ in ("journal", "retours"):
            for e in _liste_facultative(t.get(champ), f"Tâche « {i} » : « {champ} »", erreurs):
                if not _texte(e.get("t")) or not _texte(e.get("texte")):
                    erreurs.append(f"Tâche « {i} » : « {champ} » : chaque élément a « t » et « texte » (textes).")
                if champ == "retours" and not _texte_ou_nul(e.get("reponse")):
                    erreurs.append(f"Tâche « {i} » : « retours » : « reponse » doit être un texte.")
        images = _liste_facultative(t.get("images"), f"Tâche « {i} » : « images »", erreurs)
        if len(images) > MAX_IMAGES:
            erreurs.append(f"Tâche « {i} » : « images » : au plus {MAX_IMAGES} images.")
        for e in images:
            if not _texte(e.get("chemin")) or not e.get("chemin") or not _texte_ou_nul(e.get("legende")):
                erreurs.append(f"Tâche « {i} » : « images » : chaque image a un « chemin » "
                               "(et une « legende » en texte).")
        for e in _liste_facultative(t.get("liens"), f"Tâche « {i} » : « liens »", erreurs):
            if not _texte(e.get("libelle")) or not lien_valide(e.get("url")):
                erreurs.append(f"Tâche « {i} » : « liens » : chaque lien a un « libelle » et une « url » "
                               "valide (https, http ou claude).")
        if not _texte_ou_nul(t.get("bloquee")):
            erreurs.append(f"Tâche « {i} » : « bloquee » doit être un texte.")


CHAMPS_V2_RACINE = ("actions", "types", "lecons")
CHAMPS_V2_TACHE = ("type", "journal", "images", "liens", "retours", "bloquee")
CHAMPS_V2_TITULAIRE = ("prenom", "specialite", "lecons")


def normaliser(r):
    """Applique les valeurs par défaut. Ne modifie pas l'argument."""
    n = copy.deepcopy(r)
    v2 = n.get("version") == 2
    for c in CHAMPS_V2_RACINE:
        if v2:
            n[c] = n[c] if isinstance(n.get(c), list) else []
        else:
            n.pop(c, None)
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
        for c in CHAMPS_V2_TACHE:
            if not v2:
                t.pop(c, None)
            elif c in ("type", "bloquee"):
                t.setdefault(c, None)
            else:
                t[c] = t[c] if isinstance(t.get(c), list) else []
    for t in n["titulaires"]:
        if not v2:
            for c in CHAMPS_V2_TITULAIRE:
                t.pop(c, None)
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
