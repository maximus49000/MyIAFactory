"""Les outils génériques de l'orchestrateur, en ligne de commande.

    py -3.12 orchestrateur/outil.py --factory <fichier de factory> <commande> [arguments]

L'entrée est du JSON sur l'entrée standard (quand la commande en prend), la sortie du JSON sur la sortie
standard. Codes de sortie : 0 fait, 1 refusé (`{"erreur": texte}`), 2 appel invalide. Le contrat de chaque commande
est dans `interface.md` ; `lancer <commande>` lance la commande déclarée par le projet, sinon la générique.
"""
import argparse
import base64
import binascii
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bureau import releve as rel  # noqa: E402
from bureau.statuts import TRES_ANCIEN, lire_date  # noqa: E402
from orchestrateur import depart  # noqa: E402
from orchestrateur import factory as fa  # noqa: E402
from orchestrateur import fiches as fi  # noqa: E402
from orchestrateur import memoire  # noqa: E402
from orchestrateur import suivi as su  # noqa: E402

MAX_IMAGES = 4
MAX_OCTETS_IMAGE = 5 * 1024 * 1024
MAX_NOM_IMAGE = 80
SIGNATURES = {".png": (b"\x89PNG\r\n\x1a\n", "image/png"), ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
              ".jpeg": (b"\xff\xd8\xff", "image/jpeg")}
VISIBLES = 5
DELAI_COMMANDE_DECLAREE_S = 300
TYPES_DEMANDE = ("bouton", "deplacer", "retour", "lecon", "challenge", "solution", "verdict_solution",
                 "fonctionnalite", "message", "cahier", "methode", "genre", "session_cloud", "retour_element")
MODELES_INTERDITS = ("Fable",)   # un outil ne choisit jamais Fable


class Refus(Exception):
    """Code 1 : la demande est lisible mais refusée."""


class Appel(Exception):
    """Code 2 : l'appel est invalide (commande inconnue, entrée illisible, fichier de factory illisible)."""


# --- Contexte et aides.

class Contexte:
    def __init__(self, chemin_factory):
        try:
            self.f = fa.lire(chemin_factory)
        except fa.FactoryInvalide as e:
            raise Appel(str(e))
        self.suivi = su.Suivi(self.f["suivi"])

    def fiches(self):
        try:
            return fi.lire_toutes(self.f["fiches"])
        except (fi.FicheInvalide, OSError) as e:
            raise Refus(f"Fiches illisibles : {e}")

    def chef(self, fiches=None):
        """La clé du chef : la fiche de rôle « chef » si le projet en a une, sinon « chef »."""
        for x in fiches if fiches is not None else self.fiches():
            if x["role"] == "chef":
                return x["cle"]
        return "chef"

    def cles_agents(self):
        return {x["cle"] for x in self.fiches()} | {"chef"}

    def colonnes(self):
        return ["cadrage"] + [e["id"] for e in self.f["flux"]] + ["fait"]

    def sessions(self):
        try:
            d = json.loads(self.f["sessions"].read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(d, dict) else {}

    def chemin_relatif(self, chemin):
        """Un chemin relatif au fichier de factory, vu depuis le dossier des réglages (ce que le bureau attend)."""
        absolu = os.path.join(str(self.f["base"]), str(chemin))
        reference = self.f["reglages"].parent if self.f["reglages"] else self.f["base"]
        try:
            return Path(os.path.relpath(absolu, str(reference))).as_posix()
        except ValueError:   # un autre disque
            return str(chemin).replace("\\", "/")


def texte(e, cle, obligatoire=True, vide_ok=False):
    v = e.get(cle)
    if v is None and not obligatoire:
        return None
    if not isinstance(v, str) or (not vide_ok and not v.strip()):
        raise Refus(f"« {cle} » est obligatoire (texte)." if obligatoire else f"« {cle} » doit être un texte.")
    return v


def liste_de_textes(e, cle):
    v = e.get(cle)
    if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
        raise Refus(f"« {cle} » doit être une liste de textes non vides.")
    return v


def _fonc(donnees, i):
    f = su.fonctionnalite(donnees, i) if isinstance(i, str) else None
    if f is None:
        raise Refus(f"Fonctionnalité inconnue : {i}")
    return f


def _date_valide(t):
    return isinstance(t, str) and lire_date(t) != TRES_ANCIEN


def _resume_fonc(f):
    return {k: f[k] for k in f if k not in ("file", "elements", "maj")}


# --- Les images jointes d'une demande : décodées et rangées sous `pieces/`.

def ranger_images(ctx, images, sous_dossier):
    """Écrit les images (base64) et rend leurs chemins, relatifs au fichier de factory."""
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise Refus(f"Au plus {MAX_IMAGES} images par demande.")
    chemins, horodatage = [], su.maintenant()[:19].replace("-", "").replace(":", "").replace("T", "-")
    for k, image in enumerate(images, 1):
        nom = image.get("nom") if isinstance(image, dict) else None
        if (not isinstance(nom, str) or not nom or len(nom) > MAX_NOM_IMAGE or ".." in nom
                or any(c in nom for c in "/\\:") or any(ord(c) < 32 for c in nom)):
            raise Refus(f"Image {k} : nom refusé (sans séparateur ni « .. », {MAX_NOM_IMAGE} caractères au plus).")
        signature = SIGNATURES.get(Path(nom).suffix.lower())
        if signature is None:
            raise Refus(f"Image « {nom} » : seuls .png, .jpg et .jpeg sont acceptés.")
        if image.get("type") != signature[1]:
            raise Refus(f"Image « {nom} » : type refusé (image/png pour .png, image/jpeg pour .jpg et .jpeg).")
        try:
            octets = base64.b64decode(image.get("donnees") or "", validate=True)
        except (binascii.Error, ValueError, TypeError):
            raise Refus(f"Image « {nom} » : contenu illisible (base64 invalide).")
        if not octets.startswith(signature[0]):
            raise Refus(f"Image « {nom} » : le contenu n'est pas du {signature[1].split('/')[1].upper()}.")
        if len(octets) > MAX_OCTETS_IMAGE:
            raise Refus(f"Image « {nom} » : plus de 5 Mo.")
        dossier = ctx.f["pieces"] / sous_dossier
        dossier.mkdir(parents=True, exist_ok=True)
        cible, n = dossier / f"{horodatage}-{nom}", 1
        while cible.exists():
            n += 1
            cible = dossier / f"{horodatage}-{n}-{nom}"
        cible.write_bytes(octets)
        chemins.append(Path(os.path.relpath(cible, ctx.f["base"])).as_posix())
    return chemins


# --- Les commandes. Chacune : (ctx, entrée) -> objet ; Refus ou Appel en cas de problème.

def cmd_releve(ctx, e):
    return construire_releve(ctx)


def cmd_charge(ctx, e):
    if ctx.f["reglages"] is None:
        raise Refus("Le fichier de factory n'indique pas les réglages du bureau (« reglages »).")
    lanceur = ctx.f["skill"] / "lancer.py"
    try:
        p = subprocess.run([sys.executable, str(lanceur), "charge", "--reglages", str(ctx.f["reglages"])],
                           capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Refus(f"La mesure de charge n'a pas pu être lancée : {ex}")
    ligne = (p.stdout.decode("utf-8", "replace").strip().splitlines() or [""])[0]
    if p.returncode not in (0, 1):
        raise Refus(ligne or f"La mesure de charge a échoué (code {p.returncode}).")
    return {"feu_vert": p.returncode == 0, "texte": ligne}


def _empreinte_demande(d):
    return {k: v for k, v in d.items() if k not in ("id", "statut", "reponse")}


def cmd_actions(ctx, e):
    """Une demande du bureau : elle devient une ligne « en attente » du suivi et du journal."""
    genre = e.get("type")
    if genre not in TYPES_DEMANDE:
        raise Refus(f"Demande inconnue : {genre}")
    with ctx.suivi.transaction() as s:
        demande = {k: v for k, v in e.items() if k != "images"}
        demande["t"] = e["t"] if _date_valide(e.get("t")) else su.maintenant()
        if "id" in demande:   # l'id d'un bouton ou d'une leçon visée ne doit pas écraser celui de la demande
            demande["cible"] = demande.pop("id")
        demande["id"] = f"r{su.suivant(s, 'r')}"
        demande["statut"], demande["reponse"] = "en attente", None
        if genre == "fonctionnalite":
            f = su.nouvelle_fonctionnalite(s, texte(e, "texte")[:40])
            images = ranger_images(ctx, e["images"], f["id"]) if e.get("images") else []
            su.ajouter_message(s, f, "utilisateur", e["texte"], images, demande["t"])
            demande["fonctionnalite"] = f["id"]
            if images:
                demande["images"] = images
        elif genre == "message":
            f = _fonc(s, e.get("fonctionnalite"))
            images = ranger_images(ctx, e["images"], f["id"]) if e.get("images") else []
            su.ajouter_message(s, f, "utilisateur", texte(e, "texte"), images, demande["t"])
            if images:
                demande["images"] = images
        elif genre == "bouton" and e.get("id") in ("pause", "reprendre"):
            s["factory"] = {"etat": "en pause" if e["id"] == "pause" else "en marche", "depuis": demande["t"]}
            demande["statut"] = "traitée"   # l'effet est le changement d'état lui-même
        s["demandes"].append(demande)
    ligne = {k: v for k, v in demande.items() if k != "donnees"}
    with open(ctx.f["suivi"].with_name("demandes.jsonl"), "a", encoding="utf-8") as j:
        j.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return {"ok": True, "id": demande["id"]}


def cmd_reveil(ctx, e):
    with ctx.suivi.transaction() as s:
        s["reveil"] = su.maintenant()
        return {"reveil": s["reveil"]}


def cmd_demandes(ctx, e):
    return {"demandes": [d for d in ctx.suivi.lire()["demandes"] if d["statut"] == "en attente"]}


def cmd_demande_traitee(ctx, e):
    i = texte(e, "id")
    with ctx.suivi.transaction() as s:
        d = next((x for x in s["demandes"] if x["id"] == i), None)
        if d is None:
            raise Refus(f"Demande inconnue : {i}")
        if d["statut"] != "en attente":
            raise Refus(f"La demande {i} est déjà traitée.")
        d["statut"] = "traitée"
        d["reponse"] = texte(e, "reponse", obligatoire=False, vide_ok=True)
    return {"ok": True}


def _agents(ctx, s, fiches):
    sessions, occupes = ctx.sessions(), {t["agent"] for t in s["taches"] if t.get("active") and t.get("agent")}
    sortie = []
    for x in fiches:
        sortie.append({"cle": x["cle"], "role": x["role"], "service": x["service"], "modele": x["modele"],
                       "lieu": x["lieu"], "session": sessions.get(x["cle"]) or x["session"],
                       "libre": x["cle"] not in occupes})
    return sortie


def cmd_etat(ctx, e):
    s, fiches = ctx.suivi.lire(), ctx.fiches()
    decisions = [{**d, "portee": f["id"]} for f in s["fonctionnalites"] for d in f["decisions"]]
    decisions += [{**d, "portee": "projet"} for d in s["decisions_projet"]]
    return {
        "projet": ctx.f["nom"], "genre": ctx.f["genre"], "pause": s["factory"]["etat"] == "en pause",
        "reveil": s["reveil"], "seuil_methode": ctx.f["seuil_methode"],
        "fonctionnalites": [{**_resume_fonc(f), "file": len(f["file"])} for f in s["fonctionnalites"]],
        "taches": s["taches"], "file": {f["id"]: f["file"] for f in s["fonctionnalites"] if f["file"]},
        "decisions": decisions, "lecons": [x for x in s["lecons"] if x["etat"] == "à valider"],
        "agents": _agents(ctx, s, fiches),
    }


def _verifier_cahier(c):
    if (not isinstance(c, dict) or not isinstance(c.get("maquette"), list)
            or not all(isinstance(x, str) and x for x in c["maquette"])
            or not isinstance(c.get("etapes"), list) or not all(isinstance(x, str) for x in c["etapes"])):
        raise Refus("« cahier » doit avoir une « maquette » (liste de chemins) et des « etapes » (liste de textes).")
    if c.get("valide_le") is not None and not isinstance(c["valide_le"], str):
        raise Refus("« cahier.valide_le » doit être un texte.")


def _verifier_methode(m):
    ok = (isinstance(m, dict) and isinstance(m.get("version"), int) and not isinstance(m["version"], bool)
          and m["version"] >= 1 and (m.get("lien") is None) != (m.get("chemin") is None))
    if ok and m.get("lien") is not None:
        ok = rel.lien_valide(m["lien"])
    elif ok:
        ok = isinstance(m["chemin"], str) and bool(m["chemin"])
    if not ok:
        raise Refus("« methode » doit avoir une « version » (entier ≥ 1) et un seul de « lien » "
                    "(https, http ou claude) ou « chemin ».")


def _verifier_livrable(v):
    ok = isinstance(v, dict) and isinstance(v.get("libelle"), str) and v["libelle"] and (
        v.get("date") is None or isinstance(v["date"], str))
    if ok:
        ok = (v.get("lien") is None) != (v.get("chemin") is None)
    if ok and v.get("lien") is not None:
        ok = rel.lien_valide(v["lien"])
    elif ok:
        ok = isinstance(v["chemin"], str) and bool(v["chemin"])
    if not ok:
        raise Refus("« livrable » doit avoir un « libelle », une « date » et un seul de « lien » ou « chemin ».")


def cmd_fonctionnalite(ctx, e):
    i = texte(e, "id")
    cles = ctx.cles_agents()
    with ctx.suivi.transaction() as s:
        f = _fonc(s, i)
        if "nom" in e:
            f["nom"] = texte(e, "nom")
        if "etape" in e:
            if e["etape"] not in rel.ETAPES:
                raise Refus(f"Étape inconnue « {e['etape']} » ({', '.join(rel.ETAPES)}).")
            f["etape"] = e["etape"]
        if "agent_cadrage" in e:
            if e["agent_cadrage"] is not None and e["agent_cadrage"] not in cles:
                raise Refus(f"Agent de cadrage inconnu : {e['agent_cadrage']}")
            f["agent_cadrage"] = e["agent_cadrage"]
        for cle, controle in (("cahier", _verifier_cahier), ("methode", _verifier_methode),
                              ("livrable", _verifier_livrable)):
            if cle in e:
                if e[cle] is not None:
                    controle(e[cle])
                f[cle] = e[cle]
        if "catalogue" in e:
            if not isinstance(e["catalogue"], bool):
                raise Refus("« catalogue » doit être vrai ou faux.")
            f["catalogue"] = e["catalogue"]
        f["maj"] = su.maintenant()
        return _resume_fonc(f)


def cmd_message(ctx, e):
    auteur = texte(e, "auteur")
    if auteur != "utilisateur" and auteur not in ctx.cles_agents():
        raise Refus(f"Auteur inconnu : {auteur} (utilisateur ou un agent).")
    images = e.get("images")
    if images is not None:
        liste_de_textes(e, "images")
        if len(images) > MAX_IMAGES:
            raise Refus(f"Au plus {MAX_IMAGES} images par message.")
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        m = su.ajouter_message(s, f, auteur, texte(e, "texte", vide_ok=True), images)
    return {"id": m["id"]}


def cmd_decision(ctx, e):
    action = e.get("action")
    with ctx.suivi.transaction() as s:
        if action == "lever":
            i = texte(e, "id")
            for liste in [f["decisions"] for f in s["fonctionnalites"]] + [s["decisions_projet"]]:
                for d in liste:
                    if d["id"] == i:
                        liste.remove(d)
                        return {"ok": True}
            raise Refus(f"Décision inconnue : {i}")
        if action != "poser":
            raise Refus("« action » doit valoir poser ou lever.")
        portee, genre, contenu = texte(e, "portee"), texte(e, "genre"), texte(e, "texte", vide_ok=True)
        if portee == "projet":
            if genre not in rel.DECISIONS_PROJET:
                raise Refus(f"Décision du projet : genre inconnu « {genre} » ({', '.join(rel.DECISIONS_PROJET)}).")
            d = {"genre": genre, "texte": contenu}
            if genre == "confirmer_genre":
                connus = e.get("genres_connus", genres_connus(ctx))
                if (not isinstance(e.get("propose"), str) or not fa.MOTIF_GENRE.match(e["propose"])
                        or not isinstance(connus, list) or not all(isinstance(g, str) and fa.MOTIF_GENRE.match(g)
                                                                   for g in connus)):
                    raise Refus("« confirmer_genre » demande « propose » et « genres_connus » (identifiants de genre).")
                d.update(propose=e["propose"], genres_connus=connus)
            else:
                if e.get("agent") not in ctx.cles_agents():
                    raise Refus(f"« session_cloud » : agent inconnu « {e.get('agent')} ».")
                d["agent"] = e["agent"]
            liste = s["decisions_projet"]
        else:
            if genre not in rel.DECISIONS_FONCTIONNALITE:
                raise Refus(f"Décision d'une fonctionnalité : genre inconnu « {genre} » "
                            f"({', '.join(rel.DECISIONS_FONCTIONNALITE)}).")
            d = {"genre": genre, "texte": contenu}
            liste = _fonc(s, portee)["decisions"]
        existante = next((x for x in liste if {k: v for k, v in x.items() if k != "id"} == d), None)
        if existante:   # poser deux fois la même décision n'en crée qu'une
            return {"id": existante["id"]}
        d = {"id": f"d{su.suivant(s, 'd')}", **d}
        liste.append(d)
        return {"id": d["id"]}


def genres_connus(ctx):
    try:
        return [g["id"] for g in memoire.genres(ctx.f["memoire"])]
    except OSError:
        return []


def cmd_tache(ctx, e):
    cles, colonnes = ctx.cles_agents(), ctx.colonnes()
    i = e.get("id")
    with ctx.suivi.transaction() as s:
        if i is None:
            t = {"id": f"t{su.suivant(s, 't')}", "titre": texte(e, "titre"), "fonctionnalite": None, "element": None,
                 "role": None, "colonne": ctx.f["flux"][0]["id"], "agent": None, "etape": "", "modele_depart": None,
                 "montee": None, "journal": [], "bloquee": None, "active": True, "captures": [], "maj": None}
            s["taches"].append(t)
        else:
            t = su.tache(s, i)
            if t is None:
                raise Refus(f"Tâche inconnue : {i}")
            if "titre" in e:
                t["titre"] = texte(e, "titre")
        if "fonctionnalite" in e:
            if e["fonctionnalite"] is not None:
                _fonc(s, e["fonctionnalite"])
            t["fonctionnalite"] = e["fonctionnalite"]
        for cle in ("element", "role", "modele_depart", "bloquee"):
            if cle in e:
                t[cle] = texte(e, cle, obligatoire=False)
        if "etape" in e:
            t["etape"] = texte(e, "etape", vide_ok=True)
        if "colonne" in e:
            if e["colonne"] not in colonnes:
                raise Refus(f"Colonne inconnue « {e['colonne']} » ({', '.join(colonnes)}).")
            t["colonne"] = e["colonne"]
            if e["colonne"] == "fait" and "active" not in e:
                t["active"] = False
        if "agent" in e:
            if e["agent"] is not None and e["agent"] not in cles:
                raise Refus(f"Agent inconnu : {e['agent']}")
            t["agent"] = e["agent"]
        if "active" in e:
            if not isinstance(e["active"], bool):
                raise Refus("« active » doit être vrai ou faux.")
            t["active"] = e["active"]
        if "montee" in e:
            m = e["montee"]
            if m is not None:
                if not isinstance(m, dict) or not all(isinstance(m.get(c), str) and m[c].strip()
                                                      for c in ("de", "a", "raison")):
                    raise Refus("« montee » doit avoir « de », « a » et « raison » (textes non vides).")
                if m["a"] in MODELES_INTERDITS or m["de"] in MODELES_INTERDITS:
                    raise Refus("Fable n'est jamais choisi par un outil (seulement sur demande expresse).")
                m = {c: m[c] for c in ("de", "a", "raison")}
            t["montee"] = m
            if m and not t["modele_depart"]:
                t["modele_depart"] = m["de"]
        if "captures" in e:
            t["captures"] = liste_de_textes(e, "captures")
        if "journal" in e:
            ajouts = [e["journal"]] if isinstance(e["journal"], str) else e["journal"]
            if not isinstance(ajouts, list) or not all(isinstance(x, str) and x for x in ajouts):
                raise Refus("« journal » doit être un texte ou une liste de textes.")
            t["journal"] += [{"t": su.maintenant(), "texte": x} for x in ajouts]
        if t["agent"] and t["active"]:
            autre = next((x for x in s["taches"] if x is not t and x["active"] and x["agent"] == t["agent"]), None)
            if autre:
                raise Refus(f"L'agent {t['agent']} tient déjà la tâche {autre['id']} (une tâche à la fois).")
        t["maj"] = su.maintenant()
        return dict(t)


def cmd_file(ctx, e):
    elements = e.get("elements")
    if not isinstance(elements, list):
        raise Refus("« elements » doit être une liste de {id, nom, groupe?}.")
    vus, propres = set(), []
    for q in elements:
        if not isinstance(q, dict) or not isinstance(q.get("id"), str) or not q["id"] \
                or not isinstance(q.get("nom"), str) or (q.get("groupe") is not None and not isinstance(q["groupe"], str)):
            raise Refus("Chaque élément de la file a un « id » et un « nom » (textes), et au plus un « groupe ».")
        if q["id"] in vus:
            raise Refus(f"File : identifiant d'élément en double « {q['id']} ».")
        vus.add(q["id"])
        propres.append({k: q[k] for k in ("id", "nom", "groupe") if q.get(k) is not None})
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        f["file"] = propres
        for q in propres:
            f["elements"][q["id"]] = {k: q[k] for k in ("nom", "groupe") if k in q}
        f["maj"] = su.maintenant()
        return {"elements": len(propres)}


def cmd_file_prendre(ctx, e):
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        element = f["file"].pop(0) if f["file"] else None
        return {"element": element}


def cmd_session(ctx, e):
    agent, session = texte(e, "agent"), texte(e, "session")
    if agent not in ctx.cles_agents():
        raise Refus(f"Agent inconnu : {agent}")
    with ctx.suivi.transaction():   # le même verrou : l'orchestrateur et la commande d'actions écrivent ensemble
        table = ctx.sessions()
        table[agent] = session
        chemin = ctx.f["sessions"]
        tmp = chemin.with_name(chemin.name + ".tmp")
        tmp.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, chemin)
    return {"ok": True}


def cmd_catalogue(ctx, e):
    """Le catalogue générique d'une fonctionnalité (format de `bureau/catalogue.py`)."""
    s = ctx.suivi.lire()
    f = _fonc(s, e.get("fonctionnalite"))
    version = (f.get("methode") or {}).get("version")
    ordre = list(f["elements"]) + [q["id"] for q in f["file"] if q["id"] not in f["elements"]]
    elements = []
    for eid in ordre:
        info = f["elements"].get(eid) or next((q for q in f["file"] if q["id"] == eid), {})
        taches = [t for t in s["taches"] if t.get("fonctionnalite") == f["id"] and t.get("element") == eid]
        fait = next((t for t in reversed(taches) if t["colonne"] == "fait"), None)
        etat = "fait" if fait else "en_cours" if taches else "a_faire"
        el = {"id": eid, "nom": info.get("nom") or eid, "etat": etat}
        if info.get("groupe"):
            el["groupe"] = info["groupe"]
        captures = [c for t in taches for c in t.get("captures") or []] if fait else []
        if captures:
            el["captures"] = [{"chemin": ctx.chemin_relatif(c), **({"passe": version} if version else {})}
                              for c in captures]
        if fait and version:
            el["passes"] = [version]
        retours = [{"t": d["t"], "texte": d["texte"], "etat": "traité" if d["statut"] == "traitée" else "en attente",
                    **({"reponse": d["reponse"]} if d.get("reponse") else {})}
                   for d in s["demandes"] if d["type"] == "retour_element" and d.get("fonctionnalite") == f["id"]
                   and d.get("element") == eid]
        if retours:
            el["retours"] = retours
        elements.append(el)
    groupes = list(dict.fromkeys(el["groupe"] for el in elements if el.get("groupe")))
    sortie = {"elements": elements}
    if groupes:
        sortie["groupes"] = [{"id": g, "nom": g} for g in groupes]
    if version:
        sortie["passes"] = [{"numero": version}]
    return sortie


# --- Le relevé version 4, tiré du suivi et des fiches.

def construire_releve(ctx):
    s, fiches = ctx.suivi.lire(), ctx.fiches()
    chef = ctx.chef(fiches)
    chemin = ctx.chemin_relatif
    titulaires = []
    en_attente = {d["id"]: d for d in s["demandes"] if d["type"] == "lecon" and d["statut"] == "en attente"}
    meta = {x["id"]: x for x in s["lecons"]}
    if not any(x["role"] == "chef" for x in fiches):
        titulaires.append({"cle": "chef", "chef": True, "lieu": "local", "modele": "Opus", "permanent": True})
    sessions = ctx.sessions()
    for x in fiches:
        t = {"cle": x["cle"], "lieu": x["lieu"], "modele": x["modele"], "permanent": True, "prenom": x["prenom"],
             "specialite": x["specialite"],
             "lecons": [{"id": le["id"], "texte": le["texte"], "etat": le["etat"],
                         **({k: meta[le["id"]][k] for k in ("etage_propose", "texte_general", "roles")
                             if meta.get(le["id"], {}).get(k) is not None} if le["etat"] == "à valider" else {})}
                        for le in x["lecons"]]}
        if x["role"] == "chef":
            t["chef"] = True
        else:
            t["service"] = x["service"]
        if sessions.get(x["cle"]) or x["session"]:
            t["session"] = sessions.get(x["cle"]) or x["session"]
        titulaires.append(t)
    cles = {t["cle"] for t in titulaires}

    retours = {}
    for d in s["demandes"]:
        if d["type"] == "retour" and isinstance(d.get("tache"), str):
            r = {"t": d["t"], "texte": d.get("texte") or ""}
            if d.get("reponse"):
                r["reponse"] = d["reponse"]
            retours.setdefault(d["tache"], []).append(r)
    taches = [{"id": "orchestration", "titre": "Orchestration", "colonne": "cadrage", "active": True,
               "titulaire": chef, "etape": "", "maj": s["reveil"], "postit": False}]
    # Une fonctionnalité en cadrage sans vraie tâche de cadrage (l'orchestrateur en crée une pour `depart`) en
    # reçoit une, pour que son agent de cadrage se voie au travail.
    avec_tache = {t["fonctionnalite"] for t in s["taches"] if t.get("active") and t["colonne"] == "cadrage"}
    for f in s["fonctionnalites"]:
        if f["etape"] == "cadrage" and f["agent_cadrage"] in cles and f["id"] not in avec_tache:
            taches.append({"id": f"cadrage:{f['id']}", "titre": f"Cadrage : {f['nom']}", "colonne": "cadrage",
                           "active": True, "titulaire": f["agent_cadrage"], "etape": "", "maj": f["maj"]})
    for t in s["taches"]:
        v = {"id": t["id"], "titre": t["titre"], "colonne": t["colonne"], "active": t["active"],
             "titulaire": t["agent"] if t["agent"] in cles else None, "etape": t["etape"] or "", "maj": t["maj"],
             "journal": list(t["journal"]), "fonctionnalite": t["fonctionnalite"], "element": t["element"],
             "modele_depart": t["modele_depart"], "montee": t["montee"], "bloquee": t["bloquee"]}
        if t.get("captures"):
            v["images"] = [{"chemin": chemin(c)} for c in t["captures"]]
        if t["id"] in retours:
            v["retours"] = retours[t["id"]]
        taches.append(v)

    elements_file = [{"id": f"{f['id']}/{q['id']}", "titre": q["nom"]} for f in s["fonctionnalites"] for q in f["file"]]
    fonctionnalites = []
    for f in s["fonctionnalites"]:
        v = {"id": f["id"], "nom": f["nom"], "etape": f["etape"], "agent_cadrage": f["agent_cadrage"],
             "attend_reponse": f["attend_reponse"], "discussion": [], "decisions": [dict(d) for d in f["decisions"]],
             "catalogue": bool(f["catalogue"] or f["id"] in ctx.f["catalogues"]),
             "cahier": f["cahier"], "methode": f["methode"], "livrable": f["livrable"]}
        for m in f["discussion"]:
            m = dict(m)
            if m.get("images"):
                m["images"] = [chemin(c) for c in m["images"]]
            v["discussion"].append(m)
        if f["cahier"]:
            v["cahier"] = {**f["cahier"], "maquette": [chemin(c) for c in f["cahier"]["maquette"]]}
        if f["methode"] and f["methode"].get("chemin"):
            v["methode"] = {**f["methode"], "chemin": chemin(f["methode"]["chemin"])}
        if f["livrable"] and f["livrable"].get("chemin"):
            v["livrable"] = {**f["livrable"], "chemin": chemin(f["livrable"]["chemin"])}
        fonctionnalites.append(v)

    lecons = []
    for x in s["lecons"]:
        if x["etat"] != "à valider":
            continue
        le = {"id": x["id"], "agent": x["agent"] if x["agent"] in cles else chef, "texte": x["texte"],
              "date": x["date"], "etage_propose": x["etage_propose"], "roles": x["roles"]}
        if x.get("tache"):
            le["tache"] = x["tache"]
        if x.get("texte_general"):
            le["texte_general"] = x["texte_general"]
        for d in en_attente.values():
            if d.get("cible") == x["id"]:
                le["verdict_demande"] = d.get("verdict")
        lecons.append(le)

    en_pause = s["factory"]["etat"] == "en pause"
    r = {"version": 4, "projet": ctx.f["nom"], "factory": dict(s["factory"]),
         "services": [dict(x) for x in ctx.f["services"]],
         "colonnes": [{"id": "cadrage", "nom": "Cadrage"}] + [{"id": e["id"], "nom": e["nom"]} for e in ctx.f["flux"]]
                     + [{"id": "fait", "nom": "Fait", "terminee": True}],
         "titulaires": titulaires, "taches": taches,
         "file": {"visibles": elements_file[:VISIBLES], "suite": elements_file[VISIBLES:VISIBLES + rel.MAX_SUITE],
                  "reste": max(0, len(elements_file) - VISIBLES)},
         "decisions": 0, "lecons": lecons,
         "actions": [{"id": "reprendre", "libelle": "Reprendre"} if en_pause else
                     {"id": "pause", "libelle": "Pause", "confirmer": "Mettre la factory en pause ?"}],
         "genre": ctx.f["genre"], "livrable": s["livrable"], "fonctionnalites": fonctionnalites,
         "decisions_projet": [dict(d) for d in s["decisions_projet"]]}
    return r


# --- La mémoire, les genres, les leçons, le registre des contrôles.

def cmd_memoire(ctx, e):
    role = texte(e, "role")
    lecons = memoire.lire(ctx.f["memoire"], ctx.f["genre"], role)
    return {"genre_id": ctx.f["genre"], "skill": lecons["skill"], "genre": lecons["genre"]}


def cmd_genre(ctx, e):
    action = e.get("action")
    if action == "lister":
        return {"genre": ctx.f["genre"], "genres": memoire.genres(ctx.f["memoire"])}
    if action != "fixer":
        raise Refus("« action » doit valoir lister ou fixer.")
    genre = texte(e, "genre")
    if not fa.MOTIF_GENRE.match(genre):
        raise Refus("Identifiant de genre refusé (minuscules, chiffres et tirets, 40 caractères au plus).")
    cree = genre not in {g["id"] for g in memoire.genres(ctx.f["memoire"])}
    if cree:   # un nouveau genre : son fichier de mémoire, avec sa description, avant de le noter au projet
        ok, message = memoire.creer_genre(ctx.f["memoire"], genre, e.get("description"), ctx.f["mots_interdits"])
        if not ok:
            raise Refus(message)
    fa.ecrire_genre(ctx.f["chemin"], genre)
    return {"genre": genre, "cree": cree}


def _ligne_fiche(texte_lecon):
    return " ".join(texte_lecon.split())


def cmd_lecon(ctx, e):
    action = e.get("action")
    if action == "noter":
        return _noter_lecon(ctx, e)
    if action == "appliquer":
        return _appliquer_lecon(ctx, e)
    raise Refus("« action » doit valoir noter ou appliquer.")


def _noter_lecon(ctx, e):
    agent, contenu = texte(e, "agent"), texte(e, "texte")
    if agent not in ctx.cles_agents():
        raise Refus(f"Agent inconnu : {agent}")
    etage = e.get("etage_propose", "projet")
    if etage not in rel.ETAGES:
        raise Refus(f"Étage inconnu « {etage} » ({', '.join(rel.ETAGES)}).")
    general = texte(e, "texte_general", obligatoire=False)
    if etage != "projet" and not (general and general.strip()):
        raise Refus("Une leçon d'étage genre ou skill demande « texte_general » : le texte réécrit en termes "
                    "généraux, sans nom de projet, de lieu, de fichier ni de personne.")
    roles = e.get("roles", ["tous"])
    if not isinstance(roles, list) or not roles or not all(isinstance(r, str) and r.strip() for r in roles):
        raise Refus("« roles » doit être une liste de textes non vide (ou « tous »).")
    tache = texte(e, "tache", obligatoire=False)
    fiche_agent = fi.trouver(ctx.fiches(), agent)
    with ctx.suivi.transaction() as s:
        pris = {x["id"] for x in s["lecons"]} | {x["id"] for x in (fiche_agent["lecons"] if fiche_agent else [])}
        while True:
            i = f"{agent}:L{su.suivant(s, 'l')}"
            if i not in pris:
                break
        s["lecons"].append({"id": i, "agent": agent, "tache": tache, "date": su.maintenant()[:10], "texte": contenu,
                            "etat": "à valider", "etage_propose": etage, "texte_general": general, "roles": roles})
        if fiche_agent:
            fiche_agent["lecons"].append({"etat": "à valider", "id": i, "texte": _ligne_fiche(contenu)})
            fi.ecrire_fiche(fiche_agent)
    return {"id": i}


def _appliquer_lecon(ctx, e):
    i, verdict = texte(e, "id"), e.get("verdict")
    if verdict not in ("valider", "invalider"):
        raise Refus("« verdict » doit valoir valider ou invalider.")
    s = ctx.suivi.lire()
    lecon = next((x for x in s["lecons"] if x["id"] == i and x["etat"] == "à valider"), None)
    if lecon is None:
        raise Refus(f"Leçon inconnue ou déjà traitée : {i}")
    etage = e.get("etage") or lecon["etage_propose"]
    if etage not in rel.ETAGES:
        raise Refus(f"Étage inconnu « {etage} » ({', '.join(rel.ETAGES)}).")
    if verdict == "valider" and etage != "projet":
        if not (lecon.get("texte_general") or "").strip():
            raise Refus("Cette leçon n'a pas de texte général : elle ne peut aller qu'à l'étage projet.")
        general = lecon["texte_general"].strip()
        titre = general.split(".")[0].strip()[:60] or general[:60]
        ok, message = memoire.ajouter(ctx.f["memoire"], etage, ctx.f["genre"],
                                      {"titre": titre, "texte": general, "roles": lecon.get("roles") or ["tous"]},
                                      ctx.f["mots_interdits"])
        if not ok:   # la leçon reste « à valider » : rien n'a changé
            raise Refus(message)
    fiche_agent = fi.trouver(ctx.fiches(), lecon["agent"])
    with ctx.suivi.transaction() as s2:
        courante = next((x for x in s2["lecons"] if x["id"] == i and x["etat"] == "à valider"), None)
        if courante is None:
            raise Refus(f"La leçon {i} vient d'être traitée.")
        if verdict == "valider":
            courante["etat"], courante["etage_applique"] = "validée", etage
        else:
            s2["lecons"].remove(courante)
        if fiche_agent:
            if verdict == "valider":
                for x in fiche_agent["lecons"]:
                    if x["id"] == i:
                        x["etat"] = "validée"
            else:
                fiche_agent["lecons"] = [x for x in fiche_agent["lecons"] if x["id"] != i]
            fi.ecrire_fiche(fiche_agent)
    return {"ok": True, "etage": etage if verdict == "valider" else None}


def cmd_controle(ctx, e):
    contenu, origine = texte(e, "texte"), texte(e, "origine")
    with ctx.suivi.transaction():   # le même verrou que le suivi
        chemin = ctx.f["controles"]
        actuel = chemin.read_text(encoding="utf-8-sig") if chemin.is_file() else "# Registre des contrôles\n"
        n = max([int(m) for m in re.findall(r"^- C(\d+) · ", actuel, re.M)] or [0]) + 1
        ligne = f"- C{n} · {su.maintenant()[:10]} · {_ligne_fiche(origine)} : {_ligne_fiche(contenu)}"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(actuel.rstrip("\n") + "\n" + ("\n" if n == 1 else "") + ligne + "\n", encoding="utf-8", newline="\n")
    return {"numero": n}


# --- Le départ d'un agent.

def _fiches_avec_sessions(ctx):
    """Les fiches, la session de la table des sessions attitrées l'emportant sur celle de la fiche."""
    sessions = ctx.sessions()
    return [{**x, "session": sessions.get(x["cle"]) or x["session"]} for x in ctx.fiches()]


def cmd_agent_libre(ctx, e):
    role = texte(e, "role")
    cle, raison = depart.agent_libre(_fiches_avec_sessions(ctx), ctx.suivi.lire()["taches"], role,
                                     texte(e, "modele", obligatoire=False), texte(e, "lieu", obligatoire=False))
    return {"agent": cle, "raison": raison}


def cmd_depart(ctx, e):
    cle, i = texte(e, "agent"), texte(e, "tache")
    fiche_agent = fi.trouver(_fiches_avec_sessions(ctx), cle)
    if fiche_agent is None:
        raise Refus(f"Agent inconnu : {cle}")
    tache_suivie = su.tache(ctx.suivi.lire(), i)
    if tache_suivie is None:
        raise Refus(f"Tâche inconnue : {i}")
    lecons = memoire.lire(ctx.f["memoire"], ctx.f["genre"], fiche_agent["role"])
    return {"message": depart.message(ctx.f, fiche_agent, tache_suivie, depart.brief(ctx.f, fiche_agent["role"]), lecons)}


COMMANDES = {
    "releve": (cmd_releve, "aucune"), "charge": (cmd_charge, "aucune"), "actions": (cmd_actions, "obligatoire"),
    "reveil": (cmd_reveil, "aucune"), "demandes": (cmd_demandes, "aucune"),
    "demande-traitee": (cmd_demande_traitee, "obligatoire"), "etat": (cmd_etat, "aucune"),
    "fonctionnalite": (cmd_fonctionnalite, "obligatoire"), "message": (cmd_message, "obligatoire"),
    "decision": (cmd_decision, "obligatoire"), "tache": (cmd_tache, "obligatoire"), "file": (cmd_file, "obligatoire"),
    "file-prendre": (cmd_file_prendre, "obligatoire"), "session": (cmd_session, "obligatoire"),
    "catalogue": (cmd_catalogue, "obligatoire"), "memoire": (cmd_memoire, "obligatoire"),
    "genre": (cmd_genre, "obligatoire"), "lecon": (cmd_lecon, "obligatoire"), "controle": (cmd_controle, "obligatoire"),
    "agent-libre": (cmd_agent_libre, "obligatoire"), "depart": (cmd_depart, "obligatoire"),
}


# --- Exécution : en processus, ou par la commande déclarée du projet (`lancer`).

def lancer_declaree(ctx, nom, entree, extra):
    argv = ctx.f["commandes"][nom] + list(extra)
    corps = None if entree is None else json.dumps(entree, ensure_ascii=False).encode("utf-8")
    env = {**os.environ, "MYIAFACTORY_FACTORY": str(ctx.f["chemin"]), "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run(argv, cwd=str(ctx.f["base"]), input=corps, capture_output=True, env=env,
                           timeout=DELAI_COMMANDE_DECLAREE_S)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Refus(f"La commande déclarée « {nom} » n'a pas pu s'exécuter : {ex}"[:300])
    sortie = p.stdout.decode("utf-8", "replace").strip()
    try:
        objet = json.loads(sortie) if sortie else None
    except ValueError:
        objet = sortie
    return p.returncode, objet


def executer(chemin_factory, argv, entree=None):
    """(code, objet) : l'exécution d'une commande, comme `main` mais sans entrée-sortie standard."""
    try:
        ctx = Contexte(chemin_factory)
        if not argv:
            raise Appel("Aucune commande donnée.")
        nom, extra = argv[0], list(argv[1:])
        declaree = False
        if nom == "lancer":
            if not extra or extra[0] not in COMMANDES:
                raise Appel("« lancer » demande le nom d'une commande connue : " + ", ".join(sorted(COMMANDES)) + ".")
            nom, extra, declaree = extra[0], extra[1:], extra[0] in ctx.f["commandes"]
        if nom not in COMMANDES:
            raise Appel(f"Commande inconnue : {nom}.")
        fonction, mode = COMMANDES[nom]
        if nom == "catalogue" and extra and entree is None:   # `catalogue <fonctionnalité>`, pour une commande du bureau
            entree = {"fonctionnalite": extra[0]}
        if mode == "obligatoire" and entree is None and not declaree:
            raise Appel(f"La commande « {nom} » demande une entrée JSON sur l'entrée standard.")
        if entree is not None and not isinstance(entree, dict):
            raise Appel("L'entrée doit être un objet JSON.")
        if declaree:
            return lancer_declaree(ctx, nom, entree, extra)
        return 0, fonction(ctx, entree or {})
    except Refus as ex:
        return 1, (str(ex) if argv[:1] == ["actions"] or argv[:2] == ["lancer", "actions"] else {"erreur": str(ex)})
    except su.SuiviOccupe as ex:
        return 1, {"erreur": str(ex)}
    except Appel as ex:
        return 2, {"erreur": str(ex)}


class _Analyseur(argparse.ArgumentParser):
    def error(self, message):
        sortir(2, {"erreur": f"Appel invalide : {message}"})


def sortir(code, objet):
    octets = (objet if isinstance(objet, str) else json.dumps(objet, ensure_ascii=False)) + "\n"
    sys.stdout.buffer.write(octets.encode("utf-8"))
    sys.stdout.flush()
    raise SystemExit(code)


def main(argv=None):
    p = _Analyseur(prog="outil.py", description="Outils génériques de l'orchestrateur.")
    p.add_argument("--factory", required=True, help="le fichier de factory du projet")
    p.add_argument("commande", help="releve, etat, actions… ou lancer <commande>")
    p.add_argument("args", nargs="*")
    a = p.parse_args(argv)
    entree = None
    nom = a.args[0] if a.commande == "lancer" and a.args else a.commande
    prend_une_entree = nom in COMMANDES and COMMANDES[nom][1] != "aucune"   # sinon on ne lit jamais l'entrée
    if prend_une_entree and not sys.stdin.isatty():
        brut = sys.stdin.buffer.read()
        if brut.strip():
            try:
                entree = json.loads(brut.decode("utf-8-sig"))
            except ValueError as ex:
                sortir(2, {"erreur": f"Entrée illisible (JSON attendu) : {ex}"})
    code, objet = executer(a.factory, [a.commande, *a.args], entree)
    sortir(code, objet if objet is not None else {})


if __name__ == "__main__":
    main()
