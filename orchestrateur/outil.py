"""Les outils génériques de l'orchestrateur, en ligne de commande.

    py -3.12 orchestrateur/outil.py --factory <fichier de factory> <commande> [arguments]

L'entrée est du JSON sur l'entrée standard (quand la commande en prend), la sortie du JSON sur la sortie
standard. Codes de sortie : 0 fait, 1 refusé (`{"erreur": texte}`), 2 appel invalide. Le contrat de chaque commande
est dans `interface.md` ; `lancer <commande>` lance la commande déclarée par le projet, sinon la générique.
"""
import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bureau import releve as rel  # noqa: E402
from bureau.statuts import TRES_ANCIEN, lire_date  # noqa: E402
from orchestrateur import depart  # noqa: E402
from orchestrateur import factory as fa  # noqa: E402
from orchestrateur import fiches as fi  # noqa: E402
from orchestrateur import guetteur  # noqa: E402
from orchestrateur import transcriptions  # noqa: E402
from orchestrateur import lots  # noqa: E402
from orchestrateur import memoire  # noqa: E402
from orchestrateur import suivi as su  # noqa: E402
from partenaires import catalogue as pcat  # noqa: E402
from partenaires import choix as pchoix  # noqa: E402
from partenaires import detection as pdet  # noqa: E402
from partenaires import etat as petat  # noqa: E402
from partenaires import quota as pquota  # noqa: E402

MAX_IMAGES = 4
MAX_OCTETS_IMAGE = 5 * 1024 * 1024
MAX_NOM_IMAGE = 80
SIGNATURES = {".png": (b"\x89PNG\r\n\x1a\n", "image/png"), ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
              ".jpeg": (b"\xff\xd8\xff", "image/jpeg")}
VISIBLES = 5
DELAI_COMMANDE_DECLAREE_S = 300
TYPES_DEMANDE = ("bouton", "deplacer", "retour", "lecon", "challenge", "solution", "verdict_solution",
                 "fonctionnalite", "message", "cahier", "methode", "genre", "session_cloud", "retour_element",
                 "organisation", "partenaire_regle", "partenaires_actualiser", "partenaires_maj")
AGENT_ORCHESTRATEUR = "orchestrateur"   # les appels de jugement du moteur : connu de chaque projet, sans fiche
MODELES_INTERDITS = ("Fable",)   # un outil ne choisit jamais Fable


def _interdit(modele):
    """Un modèle qu'aucun outil ne choisit, quelle que soit la casse."""
    return isinstance(modele, str) and modele.strip().lower() in {m.lower() for m in MODELES_INTERDITS}


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


IMAGES_MONTREES = (".png", ".jpg", ".jpeg")   # ce que le bureau sert ; le reste n'apparaîtrait pas


def images_montrables(chemins, cle):
    """Refuse tout de suite une image que le bureau ne montrerait pas (SVG, WebP…), avec la marche à suivre."""
    for c in chemins:
        if Path(c).suffix.lower() not in IMAGES_MONTREES:
            raise Refus(f"« {cle} » : « {c} » n'est pas une image PNG ou JPEG, et le bureau ne montre que celles-là. "
                        "Convertissez-la en PNG (par exemple une capture de son rendu), puis donnez ce chemin.")
    return chemins


ORIGINE_DOCUMENT = ("agent", "etape", "tache", "element", "sous_tache")


def ranger_documents(donnees, f, chemins, titre=None, **origine):
    """Range des fichiers produits pour la fonctionnalité dans ses documents, avec leur origine (agent, étape, tâche,
    élément, sous-tâche) et la date. Un chemin déjà rangé n'est pas doublé : son titre et son origine sont complétés."""
    documents = f.setdefault("documents", [])
    for c in chemins or []:
        d = next((x for x in documents if x["chemin"] == c), None)
        if d is None:
            d = {"id": f"doc{su.suivant(donnees, 'doc')}", "chemin": c, "titre": titre or Path(c).name,
                 "date": su.maintenant()}
            documents.append(d)
        elif titre:
            d["titre"] = titre
        for cle in ORIGINE_DOCUMENT:
            if origine.get(cle):
                d[cle] = origine[cle]
    return documents


def _cle_mot(mot):
    return " ".join(memoire.normaliser_mot(mot).split())


def fusionner_glossaire(ctx, donnees, f, entrees, auteur):
    """Ajoute des mots au glossaire de la fonctionnalité (un mot déjà défini prend la nouvelle définition, à la fin),
    puis réécrit son fichier `glossaire.md`, rangé dans ses documents."""
    glossaire = f.setdefault("glossaire", [])
    for g in entrees:
        cle = _cle_mot(g["mot"])
        glossaire[:] = [x for x in glossaire if _cle_mot(x["mot"]) != cle]
        glossaire.append({"mot": g["mot"].strip(), "definition": g["definition"].strip(),
                          **({"ajoute_par": auteur} if auteur else {}), "date": su.maintenant()})
    chemin = Path(ctx.f["pieces"]) / f["id"] / "glossaire.md"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    lignes = [f"# Glossaire : {f['nom']}", "",
              "Les mots spécialisés de la fonctionnalité, définis par les agents (le plus récent fait foi).", ""]
    for g in sorted(glossaire, key=lambda x: _cle_mot(x["mot"])):
        lignes.append(f"- **{g['mot']}** : {g['definition']}")
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    try:
        relatif = chemin.resolve().relative_to(ctx.f["base"]).as_posix()
    except ValueError:
        return
    ranger_documents(donnees, f, [relatif], "Glossaire")


def _glossaire_entree(e, auteur):
    g = e.get("glossaire")
    if g is None:
        return None
    if auteur == "utilisateur":
        raise Refus("Seul un agent définit des mots.")
    probleme = rel.erreur_glossaire(g)
    if probleme:
        raise Refus(probleme)
    return g


def documents_complets(f, taches):
    """Les documents rangés, plus ceux qu'un suivi plus ancien n'avait pas rangés : images de la discussion,
    maquettes du cahier, captures des tâches de la fonctionnalité (même origine que s'ils l'avaient été)."""
    documents = [dict(d) for d in f.get("documents") or []]
    connus = {d["chemin"] for d in documents}

    def ajouter(c, **origine):
        if c not in connus:
            connus.add(c)
            documents.append({"chemin": c, "titre": Path(c).name, **{k: v for k, v in origine.items() if v}})
    # Les origines les plus précises d'abord : le cahier, puis les captures des tâches, puis la discussion.
    for c in (f.get("cahier") or {}).get("maquette") or []:
        ajouter(c, agent=f.get("agent_cadrage"), etape="cahier")
    for t in taches:
        if t.get("fonctionnalite") == f["id"]:
            for c in t.get("captures") or []:
                ajouter(c, agent=t.get("agent"), tache=t["id"], element=t.get("element"), etape=t.get("colonne"),
                        date=t.get("maj"))
    def fin(v):   # une date sans heure (« le 10 novembre ») vaut jusqu'à la fin de ce jour-là
        return rel.lire_date(v + "T23:59:59" if isinstance(v, str) and len(v.strip()) == 10 else v)
    cahier_valide = fin((f.get("cahier") or {}).get("valide_le"))
    methode_validee = fin((f.get("methode") or {}).get("validee_le"))

    def etape_au(t):   # l'étape où en était la fonctionnalité quand le message est parti
        quand = rel.lire_date(t)
        if quand == rel.TRES_ANCIEN:
            return f["etape"]
        if methode_validee != rel.TRES_ANCIEN and quand > methode_validee:
            return "serie"
        if cahier_valide != rel.TRES_ANCIEN:
            return "prototype" if quand > cahier_valide else "cadrage"
        return f["etape"]
    for m in f["discussion"]:
        for c in m.get("images") or []:
            ajouter(c, agent=m["auteur"], date=m.get("t"), etape=etape_au(m.get("t")))
    return documents


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
    cible = e.get("tache")
    if genre == "deplacer" and isinstance(cible, str) and (cible == "orchestration" or cible.startswith("cadrage:")):
        # Ces deux tâches ne sont montrées qu'au relevé (le chef qui orchestre, un cadrage en cours) : rien à déplacer.
        raise Refus("Cette tâche suit l'orchestrateur et ne se déplace pas.")
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
            ranger_documents(s, f, images, agent="utilisateur", etape=f["etape"])
            demande["fonctionnalite"] = f["id"]
            if images:
                demande["images"] = images
        elif genre == "message":
            f = _fonc(s, e.get("fonctionnalite"))
            images = ranger_images(ctx, e["images"], f["id"]) if e.get("images") else []
            su.ajouter_message(s, f, "utilisateur", texte(e, "texte"), images, demande["t"])
            ranger_documents(s, f, images, agent="utilisateur", etape=f["etape"])
            if images:
                demande["images"] = images
        elif genre == "challenge" and isinstance(e.get("cible"), dict) and e["cible"].get("type") == "lecon":
            # Challenger une leçon ouvre une tâche : la discussion y a lieu (ce texte, puis les réponses et retours).
            lecon = next((x for x in s["lecons"] if x["id"] == e["cible"].get("id")), None)
            if lecon is None:
                raise Refus(f"Leçon inconnue : {e['cible'].get('id')}")
            t = {"id": f"t{su.suivant(s, 't')}", "titre": f"Challenge de la leçon {lecon['id']}", "fonctionnalite": None,
                 "element": None, "role": None, "colonne": ctx.f["flux"][0]["id"], "agent": None, "etape": "Discussion",
                 "modele_depart": None, "montee": None, "journal": [{"t": demande["t"], "texte": "Leçon : " + lecon["texte"]}],
                 "bloquee": None, "active": True, "captures": [], "maj": demande["t"]}
            s["taches"].append(t)
            demande["tache"] = t["id"]
        elif genre == "bouton" and e.get("id") in ("pause", "reprendre"):
            s["factory"] = {"etat": "en pause" if e["id"] == "pause" else "en marche", "depuis": demande["t"]}
            demande["statut"] = "traitée"   # l'effet est le changement d'état lui-même
        s["demandes"].append(demande)
    ligne = {k: v for k, v in demande.items() if k != "donnees"}
    with open(ctx.f["suivi"].with_name("demandes.jsonl"), "a", encoding="utf-8") as j:
        j.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return {"ok": True, "id": demande["id"]}


def _presence(ctx):
    return ctx.f["suivi"].with_name("presence.json")


# Les commandes que le bureau lance lui-même (réglages `releve`, `actions`, `catalogues`, mesure de charge) : elles ne
# disent rien de la présence de l'orchestrateur. `guetter` note la sienne.
COMMANDES_DU_BUREAU = ("releve", "actions", "charge", "catalogue", "guetter")


def noter_presence(ctx):
    try:
        guetteur.ecrire_presence(_presence(ctx), datetime.now().astimezone())
    except OSError:
        pass   # la présence est une aide : jamais une raison d'échouer


def cmd_guetter(ctx, e):
    """Le moniteur de l'orchestrateur : ne rend jamais la main (il vit avec la conversation)."""
    guetteur.guetter(ctx.f["suivi"].with_name("demandes.jsonl"), _presence(ctx))
    return {}


def cmd_reveil(ctx, e):
    with ctx.suivi.transaction() as s:
        s["reveil"] = su.maintenant()
        reveil = s["reveil"]
    try:
        noter_gestion(ctx)   # la facturation compte aussi l'orchestrateur
    except (OSError, ValueError):
        pass
    return {"reveil": reveil}


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


def _fonc_compacte(f):
    """Une fonctionnalité en quelques lignes : de quoi décider du prochain geste, sans relire la discussion entière."""
    d = f["discussion"]
    dernier = d[-1] if d else None
    cahier, methode = f.get("cahier"), f.get("methode")
    return {
        "id": f["id"], "nom": f["nom"], "etape": f["etape"], "agent_cadrage": f["agent_cadrage"],
        "attend_reponse": f["attend_reponse"], "catalogue": f["catalogue"], "decisions": f["decisions"],
        "cahier": {"maquette": len(cahier.get("maquette") or []), "etapes": len(cahier.get("etapes") or []),
                   "valide_le": cahier.get("valide_le")} if cahier else None,
        "methode": {k: methode.get(k) for k in ("version", "validee_le")} if methode else None,
        "livrable": f.get("livrable"), "file": len(f["file"]), "messages": len(d),
        "dernier_message": {"id": dernier["id"], "auteur": dernier["auteur"], "t": dernier.get("t"),
                            "texte": dernier["texte"][:300]} if dernier else None,
        "documents": len(f.get("documents") or []), "glossaire": len(f.get("glossaire") or []),
    }


def _tache_compacte(t):
    sortie = {k: v for k, v in t.items() if k not in ("journal", "captures")}
    sortie["journal"] = len(t["journal"])
    sortie["dernier_journal"] = t["journal"][-1]["texte"] if t["journal"] else None
    sortie["captures"] = len(t.get("captures") or [])
    return sortie


def cmd_etat(ctx, e):
    """L'instantané que l'orchestrateur relit à chaque réveil : court (les listes longues sont comptées) ; le détail
    d'une fonctionnalité, d'une tâche ou des leçons se demande à `detail`."""
    s, fiches = ctx.suivi.lire(), ctx.fiches()
    decisions = [{**d, "portee": f["id"]} for f in s["fonctionnalites"] for d in f["decisions"]]
    decisions += [{**d, "portee": "projet"} for d in s["decisions_projet"]]
    en_cours = [t for t in s["taches"] if t["active"] or t["colonne"] != "fait"]
    return {
        "projet": ctx.f["nom"], "genre": ctx.f["genre"], "pause": s["factory"]["etat"] == "en pause",
        "reveil": s["reveil"], "seuil_methode": ctx.f["seuil_methode"],
        "fonctionnalites": [_fonc_compacte(f) for f in s["fonctionnalites"]],
        "taches": [_tache_compacte(t) for t in en_cours], "taches_faites": len(s["taches"]) - len(en_cours),
        "file": {f["id"]: len(f["file"]) for f in s["fonctionnalites"] if f["file"]},
        "decisions": decisions,
        "lecons": [{"id": x["id"], "agent": x.get("agent"), "etage_propose": x.get("etage_propose")}
                   for x in s["lecons"] if x["etat"] == "à valider"],
        "agents": _agents(ctx, s, fiches),
        "consignes": empreinte_consignes(ctx.f),
    }


def cmd_detail(ctx, e):
    """Le détail que `etat` ne donne pas : une fonctionnalité entière (discussion, cahier, file, documents, glossaire),
    une tâche entière (journal, captures), ou les leçons à valider avec leur texte."""
    s = ctx.suivi.lire()
    if e.get("fonctionnalite") is not None:
        return _resume_fonc(_fonc(s, e["fonctionnalite"])) | {"file": list(_fonc(s, e["fonctionnalite"])["file"])}
    if e.get("tache") is not None:
        t = su.tache(s, e["tache"])
        if t is None:
            raise Refus(f"Tâche inconnue : {e['tache']}")
        return dict(t)
    if e.get("lecons") is True:
        return {"lecons": [x for x in s["lecons"] if x["etat"] == "à valider"]}
    raise Refus("Demandez « fonctionnalite », « tache » ou « lecons » (vrai).")


def empreinte_consignes(f):
    """Une empreinte courte des consignes génériques, de l'interface et des consignes propres du projet : quand elle
    change, l'orchestrateur relit ces textes (la skill a pu évoluer pendant qu'il tournait)."""
    h = hashlib.sha256()
    for chemin in (f["skill"] / "orchestrateur" / "consignes.md", f["skill"] / "orchestrateur" / "interface.md",
                   f["consignes"]):
        try:
            h.update(Path(chemin).read_bytes() if chemin else b"")
        except OSError:
            h.update(b"(absent)")
        h.update(b"\x00")
    return h.hexdigest()[:12]


def _verifier_cahier(c):
    if (not isinstance(c, dict) or not isinstance(c.get("maquette"), list)
            or not all(isinstance(x, str) and x for x in c["maquette"])
            or not isinstance(c.get("etapes"), list) or not all(isinstance(x, str) for x in c["etapes"])):
        raise Refus("« cahier » doit avoir une « maquette » (liste de chemins) et des « etapes » (liste de textes).")
    images_montrables(c["maquette"], "cahier.maquette")
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


CAHIERS_GARDES = 20


def _archiver_cahier(f, nouveau):
    """Un cahier corrigé (maquette ou étapes changées) remplace l'ancien, qui passe dans `cahiers_precedents` ;
    le même cahier renvoyé avec `valide_le` n'en crée pas."""
    ancien = f.get("cahier")
    if not ancien or (nouveau and (nouveau["maquette"], nouveau["etapes"]) == (ancien["maquette"], ancien["etapes"])):
        return
    gardes = f.setdefault("cahiers_precedents", [])
    gardes.append({**ancien, "remplace_le": su.maintenant()})
    del gardes[:-CAHIERS_GARDES]


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
                if cle == "cahier":
                    _archiver_cahier(f, e[cle])
                f[cle] = e[cle]
        if e.get("cahier"):
            ranger_documents(s, f, e["cahier"]["maquette"], agent=f["agent_cadrage"], etape="cahier")
        if "catalogue" in e:
            if not isinstance(e["catalogue"], bool):
                raise Refus("« catalogue » doit être vrai ou faux.")
            f["catalogue"] = e["catalogue"]
        glossaire = _glossaire_entree(e, None)
        if glossaire:
            fusionner_glossaire(ctx, s, f, glossaire, None)
        f["maj"] = su.maintenant()
        return _resume_fonc(f)


def cmd_message(ctx, e):
    auteur = texte(e, "auteur")
    if auteur != "utilisateur" and auteur not in ctx.cles_agents():
        raise Refus(f"Auteur inconnu : {auteur} (utilisateur ou un agent).")
    images = e.get("images")
    if images is not None:
        images_montrables(liste_de_textes(e, "images"), "images")
        if len(images) > MAX_IMAGES:
            raise Refus(f"Au plus {MAX_IMAGES} images par message.")
    questions = e.get("questions")
    if questions is not None:   # des questions à choix : le bureau montre un bouton par choix
        if auteur == "utilisateur":
            raise Refus("Seul un agent pose des questions à choix.")
        probleme = rel.erreur_questions(questions)
        if probleme:
            raise Refus(probleme)
        questions = [{"texte": q["texte"], "choix": list(q["choix"]), **({"multiple": True} if q.get("multiple") else {})}
                     for q in questions]
    glossaire = _glossaire_entree(e, auteur)
    attend = e.get("attend")
    if attend is not None and not isinstance(attend, bool):
        raise Refus("« attend » doit être vrai (le message demande une réponse) ou faux (un compte rendu).")
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        m = su.ajouter_message(s, f, auteur, texte(e, "texte", vide_ok=True), images)
        if glossaire:
            m["glossaire"] = [{"mot": g["mot"].strip(), "definition": g["definition"].strip()} for g in glossaire]
            fusionner_glossaire(ctx, s, f, glossaire, auteur)
        if questions:
            m["questions"] = questions
        if attend is not None:
            m["attend"] = attend
        ranger_documents(s, f, images, agent=auteur, etape=f["etape"])
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
            elif genre == "organisation":
                d["organisation"] = _organisation_decidee(ctx, e.get("organisation"))
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


def _bornes_valides(v):
    return (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                        and x >= 0 for x in v) and v[0] <= v[1])


def _controle_organisation(ctx, o):
    """Les erreurs (liste de textes) d'une organisation `{services, flux, agents, briefs}` face au projet actuel."""
    from installation import proposition   # chargé à la demande : l'orchestrateur n'en dépend pas ailleurs
    try:
        existantes = fi.lire_toutes(ctx.f["fiches"])
    except fi.FicheInvalide as ex:
        return [f"Fiches illisibles : {ex}"]
    dossier_briefs = ctx.f["fiches"] / "briefs"
    briefs_existants = {c.stem for c in dossier_briefs.glob("*.md")} if dossier_briefs.is_dir() else set()
    for a in o.get("agents") if isinstance(o.get("agents"), list) else []:
        if isinstance(a, dict) and _interdit(a.get("modele")):
            return ["Fable n'est jamais choisi par un outil (seulement sur demande expresse)."]
    gardes = {x.get("id") for x in o.get("services") if isinstance(x, dict)} if isinstance(o.get("services"), list) else None
    if gardes is not None:
        occupes = sorted({x["service"] for x in existantes if x.get("service") and x["service"] not in gardes})
        if occupes:
            return [f"Un service qui a encore des agents n'est jamais retiré : {', '.join(occupes)}."]
    return proposition.verifier_organisation(
        o.get("services"), o.get("flux"), o.get("agents"), o.get("briefs"), cloud=True,
        roles_deja_pourvus={x["role"] for x in existantes}, cles_prises={x["cle"] for x in existantes},
        briefs_existants=briefs_existants)


def _organisation_decidee(ctx, o):
    """L'organisation d'une décision, contrôlée comme une proposition ; `Refus` sinon."""
    if not isinstance(o, dict):
        raise Refus("« organisation » demande {services, flux, agents, briefs, cout}.")
    erreurs = _controle_organisation(ctx, o)
    cout = o.get("cout")
    if not isinstance(cout, dict) or not _bornes_valides(cout.get("tokens")) or (
            cout.get("euros") is not None and not _bornes_valides(cout.get("euros"))):
        erreurs.append("« cout » demande « tokens » [a, b] et « euros » [a, b] ou null (a ≤ b).")
    if erreurs:
        raise Refus("Organisation refusée : " + " ; ".join(erreurs))
    return {"services": [dict(x) for x in o["services"]], "flux": [dict(x) for x in o["flux"]],
            "agents": [dict(x) for x in o["agents"]], "briefs": dict(o["briefs"]),
            "cout": {"tokens": list(cout["tokens"]), "euros": None if cout.get("euros") is None
                     else list(cout["euros"])}}


def cmd_organisation(ctx, e):
    """Applique une décision `organisation` acceptée : services, flux, fiches et briefs, puis lève la décision."""
    from installation.dossier import Echec
    from installation import mise_en_place
    if e.get("action") != "appliquer":
        raise Refus("« action » doit valoir appliquer.")
    i = texte(e, "decision")
    with ctx.suivi.transaction() as s:
        d = next((x for x in s["decisions_projet"] if x["id"] == i and x.get("genre") == "organisation"), None)
        if d is None:
            raise Refus(f"Décision d'organisation inconnue : {i}")
        o = d["organisation"]
        try:
            mise_en_place.ecrire_organisation(ctx.f["chemin"], o["services"], o["flux"], o["agents"], o["briefs"])
        except Echec as ex:
            raise Refus(str(ex))
        s["decisions_projet"].remove(d)
    return {"ok": True, "services": o["services"], "flux": o["flux"]}


def genres_connus(ctx):
    try:
        return [g["id"] for g in memoire.genres(ctx.f["memoire"])]
    except OSError:
        return []


def _dependances(s, t, valeur):
    """Les tâches dont `t` dépend : des identifiants de tâches connues, sans cycle."""
    if not isinstance(valeur, list) or not all(isinstance(x, str) and x for x in valeur):
        raise Refus("« depend_de » doit être une liste d'identifiants de tâches.")
    voisines = {x["id"]: x.get("depend_de") or [] for x in s["taches"]}
    for d in valeur:
        if d not in voisines:
            raise Refus(f"« depend_de » : tâche inconnue « {d} ».")
        if d == t["id"]:
            raise Refus(f"« depend_de » : la tâche {d} ne peut pas dépendre d'elle-même.")
    voisines[t["id"]] = list(dict.fromkeys(valeur))
    vus, pile = set(), list(voisines[t["id"]])
    while pile:   # une dépendance qui ramène à `t` forme un cycle
        courant = pile.pop()
        if courant == t["id"]:
            raise Refus(f"« depend_de » : cycle de dépendances qui passe par la tâche {t['id']}.")
        if courant not in vus:
            vus.add(courant)
            pile += voisines.get(courant, [])
    return voisines[t["id"]]


def _lot_de_tache(valeur):
    if valeur is None:
        return None
    if (not isinstance(valeur, dict) or not isinstance(valeur.get("id"), str) or not valeur["id"].strip()
            or isinstance(valeur.get("rang"), bool) or not isinstance(valeur.get("rang"), int) or valeur["rang"] < 1):
        raise Refus("« lot » doit valoir {\"id\": texte, \"rang\": entier d'au moins 1} ou null.")
    return {"id": valeur["id"], "rang": valeur["rang"]}


def cmd_tache(ctx, e):
    cles, colonnes = ctx.cles_agents(), ctx.colonnes()
    i = e.get("id")
    with ctx.suivi.transaction() as s:
        if i is None:
            t = {"id": f"t{su.suivant(s, 't')}", "titre": texte(e, "titre"), "fonctionnalite": None, "element": None,
                 "role": None, "colonne": ctx.f["flux"][0]["id"], "agent": None, "etape": "", "modele_depart": None,
                 "montee": None, "journal": [], "bloquee": None, "active": True, "captures": [], "maj": None,
                 "depend_de": [], "lot": None, "debut": None, "fin": None}
            s["taches"].append(t)
            etait_active = False   # une tâche neuve part de « pas encore partie » : le début est noté si elle est active
        else:
            t = su.tache(s, i)
            if t is None:
                raise Refus(f"Tâche inconnue : {i}")
            etait_active = bool(t["active"])
            if "titre" in e:
                t["titre"] = texte(e, "titre")
        if "fonctionnalite" in e:
            if e["fonctionnalite"] is not None:
                _fonc(s, e["fonctionnalite"])
            t["fonctionnalite"] = e["fonctionnalite"]
        for cle in ("element", "role", "modele_depart", "bloquee"):
            if cle in e:
                t[cle] = texte(e, cle, obligatoire=False)
        if _interdit(t["modele_depart"]):
            raise Refus("Fable n'est jamais choisi par un outil (seulement sur demande expresse).")
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
                if _interdit(m["a"]) or _interdit(m["de"]):
                    raise Refus("Fable n'est jamais choisi par un outil (seulement sur demande expresse).")
                if m["de"] in depart.ECHELLE and m["a"] != depart.monter(m["de"]):
                    raise Refus(f"Une montée va d'un cran au plus : de {m['de']}, c'est {depart.monter(m['de'])}.")
                m = {c: m[c] for c in ("de", "a", "raison")}
            t["montee"] = m
            if m and not t["modele_depart"]:
                t["modele_depart"] = m["de"]
        if "depend_de" in e:
            t["depend_de"] = _dependances(s, t, e["depend_de"])
        if "lot" in e:
            t["lot"] = _lot_de_tache(e["lot"])
        if "partenaires" in e:   # les partenaires que la tâche appelle : le départ donne leurs règles
            ids = liste_de_textes(e, "partenaires")
            connus = {x["id"] for x in _catalogue(ctx)["partenaires"]}
            inconnus = [x for x in ids if x not in connus]
            if inconnus:
                raise Refus(f"Partenaire inconnu du catalogue : {inconnus[0]}")
            t["partenaires"] = list(dict.fromkeys(ids))
        if t["active"] and not etait_active:   # le passage à « active » ouvre la durée que le coût d'un lot répartit
            t["debut"], t["fin"] = su.maintenant(), None
        elif etait_active and not t["active"]:
            t["fin"] = su.maintenant()
        if "lignes" in e:   # les lignes produites par la tâche (son total, remplacé à chaque fois)
            t["lignes"] = _entier(e, "lignes") if e["lignes"] is not None else None
        if "captures" in e:
            t["captures"] = images_montrables(liste_de_textes(e, "captures"), "captures")
        if "journal" in e:
            ajouts = [e["journal"]] if isinstance(e["journal"], str) else e["journal"]
            if not isinstance(ajouts, list) or not all(isinstance(x, str) and x for x in ajouts):
                raise Refus("« journal » doit être un texte ou une liste de textes.")
            t["journal"] += [{"t": su.maintenant(), "texte": x} for x in ajouts]
        if t["agent"] and t["active"]:
            autre = next((x for x in s["taches"] if x is not t and x["active"] and x["agent"] == t["agent"]), None)
            if autre:
                raise Refus(f"L'agent {t['agent']} tient déjà la tâche {autre['id']} (une tâche à la fois).")
        if e.get("captures") and t["fonctionnalite"]:   # les captures vont aussi dans les documents de la fonctionnalité
            ranger_documents(s, _fonc(s, t["fonctionnalite"]), t["captures"], agent=t["agent"], tache=t["id"],
                             element=t["element"], etape=t["colonne"])
        t["maj"] = su.maintenant()
        return dict(t)


def cmd_document(ctx, e):
    """Inscrit un fichier produit pour une fonctionnalité dans ses documents, avec son origine."""
    chemin = texte(e, "chemin")
    if "\x00" in chemin or Path(chemin).is_absolute() or chemin[0] in "/\\":
        raise Refus("« chemin » doit être relatif au fichier de factory.")
    origine = {cle: texte(e, cle, obligatoire=False) for cle in ORIGINE_DOCUMENT}
    livrable = e.get("livrable")
    if livrable is not None and not isinstance(livrable, bool):
        raise Refus("« livrable » doit être vrai ou faux.")
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        documents = ranger_documents(s, f, [chemin], texte(e, "titre"), **origine)
        d = next(x for x in documents if x["chemin"] == chemin)
        remplace = texte(e, "remplace", obligatoire=False)
        if remplace is not None:   # une nouvelle version : l'ancienne reste dans l'historique
            if remplace == chemin or not any(x["chemin"] == remplace for x in documents):
                raise Refus(f"« remplace » doit être le chemin d'un autre document de la fonctionnalité : {remplace}")
            d["remplace"] = remplace
        if livrable:   # le livrable final de son élément (ce que l'utilisateur valide ou fait reprendre)
            d["livrable"] = True
        elif livrable is False:
            d.pop("livrable", None)
        f["maj"] = su.maintenant()
        return {"id": next(d["id"] for d in documents if d["chemin"] == chemin)}


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
        voulu = texte(e, "element", obligatoire=False)
        if voulu is None:   # l'élément suivant
            return {"element": f["file"].pop(0) if f["file"] else None}
        rang = next((i for i, q in enumerate(f["file"]) if q["id"] == voulu), None)   # un élément précis
        if rang is None:
            raise Refus(f"Élément absent de la file : {voulu}")
        return {"element": f["file"].pop(rang)}


USAGES_AU_RELEVE = 2000   # le relevé ne porte que les plus récents : le bureau garde l'historique


def _entier(e, cle, defaut=None):
    v = e.get(cle, defaut)
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise Refus(f"« {cle} » doit être un entier positif ou nul.")
    return v


def _taches_du_lot(s, lot):
    """Les tâches suivies d'un lot, par rang."""
    return sorted((t for t in s["taches"] if isinstance(t.get("lot"), dict) and t["lot"].get("id") == lot),
                  key=lambda t: t["lot"]["rang"])


def _nouvelle_ligne_d_usage(s, t, lot, modele, agent, compteurs, estime, etape, **extra):
    u = {"id": f"u{su.suivant(s, 'u')}", "t": su.maintenant(), "agent": agent or t.get("agent"), "tache": t["id"],
         "modele": modele, **compteurs, "estime": estime, "lot": lot, **extra}
    if etape:
        u["etape"] = etape
    return u


def _usage_d_un_lot(s, usages, lot, modele, agent, total, estime, etape):
    """Le total d'un lot réparti entre ses tâches : une ligne d'usage par tâche, dont la somme vaut le total."""
    taches = _taches_du_lot(s, lot)
    if not taches:
        raise Refus(f"Lot inconnu : {lot} (aucune tâche suivie n'en porte l'identifiant).")
    if any(u.get("lot") == lot for u in usages):
        raise Refus(f"L'usage du lot {lot} est déjà noté.")
    parts = lots.repartir(total, [{"id": t["id"], "debut": t.get("debut"), "fin": t.get("fin")} for t in taches])
    mode = lots.mode_repartition(taches)
    lignes = [_nouvelle_ligne_d_usage(s, t, lot, modele, agent, parts[t["id"]], estime, etape, reparti=mode)
              for t in taches]
    usages.extend(lignes)
    return {"ids": [u["id"] for u in lignes], "reparti": mode}


def _usage_cumule_d_un_lot(s, usages, lot, cumul, tache, modele, agent, compteurs, estime, etape):
    """Un cumul relevé à la fin d'une tâche d'un lot : la ligne de la tâche est l'écart avec le cumul précédent."""
    if tache is None:
        raise Refus("Un cumul de lot demande aussi la « tache » qui vient de finir.")
    t = su.tache(s, tache)
    if not isinstance(t.get("lot"), dict) or t["lot"].get("id") != lot:
        raise Refus(f"La tâche {tache} n'est pas dans le lot {lot}.")
    cumuls = s.setdefault("usage_cumuls", {})
    avant = cumuls.get(cumul) or dict.fromkeys(compteurs, 0)
    ecart = {c: compteurs[c] - avant.get(c, 0) for c in compteurs}
    if any(v < 0 for v in ecart.values()):
        raise Refus(f"Le cumul « {cumul} » recule : les compteurs ne peuvent que croître.")
    cumuls[cumul] = dict(compteurs)
    u = _nouvelle_ligne_d_usage(s, t, lot, modele, agent, ecart, estime, etape)
    usages.append(u)
    return {"id": u["id"]}


def cmd_usage(ctx, e):
    """Note les tokens d'une exécution d'agent (pour la facturation du bureau). Les compteurs d'un même `id` sont des
    cumuls : republier l'`id` avec des nombres plus grands, tant que l'exécution continue. Quand seul un `total` est
    connu (un sous-agent ne donne que lui), il compte comme des tokens d'entrée : le coût est alors une estimation basse."""
    agent, tache = e.get("agent"), e.get("tache")
    if agent is not None and agent != AGENT_ORCHESTRATEUR and agent not in ctx.cles_agents():
        raise Refus(f"Agent inconnu : {agent}")
    if "agent_id" in e:   # les compteurs exacts du sous-agent, lus dans sa transcription locale
        e = {**e, **_compteurs_du_sous_agent(e["agent_id"])}
    modele = texte(e, "modele")
    if ("total" in e) == ("entree" in e or "sortie" in e):
        raise Refus("Donnez soit « entree » et « sortie », soit « total » (quand seul le total est connu).")
    if "total" in e:
        entree, sortie = _entier(e, "total"), 0
    else:
        entree, sortie = _entier(e, "entree"), _entier(e, "sortie")
    caches = {c: _entier(e, c, 0) for c in ("cache_lecture", "cache_ecriture")}
    lot = e.get("lot")
    if lot is not None and (not isinstance(lot, str) or not lot.strip()):
        raise Refus("« lot » doit être l'identifiant d'un lot (texte).")
    with ctx.suivi.transaction() as s:
        if tache is not None and su.tache(s, tache) is None:
            raise Refus(f"Tâche inconnue : {tache}")
        usages = s.setdefault("usage", [])
        compteurs = {"entree": entree, "sortie": sortie, **caches}
        if lot is not None and tache is None:
            return _usage_d_un_lot(s, usages, lot, modele, agent, compteurs, "total" in e, texte(e, "etape", obligatoire=False))
        if lot is not None and e.get("id") is not None:
            return _usage_cumule_d_un_lot(s, usages, lot, e["id"], tache, modele, agent, compteurs, "total" in e,
                                          texte(e, "etape", obligatoire=False))
        if e.get("id") is not None:
            u = next((x for x in usages if x["id"] == e["id"]), None)
            if u is None or u.get("genre") == "partenaire":
                raise Refus(f"Usage inconnu : {e['id']}")
        else:
            u = {"id": f"u{su.suivant(s, 'u')}", "t": su.maintenant()}
            usages.append(u)
        u.update({"agent": agent, "tache": tache, "modele": modele, "entree": entree, "sortie": sortie, **caches,
                  "estime": "total" in e})
        if lot is not None:
            u["lot"] = lot
        etape = texte(e, "etape", obligatoire=False)
        if etape:
            u["etape"] = etape
        return {"id": u["id"]}


def _compteurs_du_sous_agent(agent_id):
    f = transcriptions.sous_agent(agent_id)
    if f is None:
        raise Refus(f"Transcription du sous-agent « {agent_id} » introuvable : donnez « total » (estimation).")
    par_modele = transcriptions.compter(f)
    if not par_modele:
        raise Refus(f"La transcription du sous-agent « {agent_id} » ne porte aucun usage : donnez « total ».")
    modele = max(par_modele, key=lambda m: sum(par_modele[m].values()))   # un sous-agent tourne sur un modèle
    somme = {c: sum(x[c] for x in par_modele.values()) for c in ("entree", "sortie", "cache_lecture", "cache_ecriture")}
    return {"modele": modele, **somme}


def noter_gestion(ctx):
    """Les tokens de la conversation orchestratrice (la « gestion »), lus dans ses transcriptions locales : une ligne
    d'usage cumulée par conversation et par modèle, sans tâche (la Direction de la facturation)."""
    projet = ctx.f["chemin"].parent.parent if ctx.f["chemin"].parent.name == ".factory" else ctx.f["chemin"].parent
    fichiers = transcriptions.orchestrations(projet, ctx.f["chemin"])
    if not fichiers:
        return
    lignes = {}
    for f in fichiers:
        for modele, c in transcriptions.compter(f).items():
            lignes[f"g-{f.stem[:8]}-{re.sub(r'[^a-z0-9]', '', modele.lower())[-12:]}"] = (modele, c)
    with ctx.suivi.transaction() as s:
        usages = s.setdefault("usage", [])
        for uid, (modele, c) in lignes.items():
            u = next((x for x in usages if x["id"] == uid), None)
            if u is not None and all(u.get(k) == v for k, v in c.items()):
                continue
            if u is not None:
                usages.remove(u)   # remise en fin de liste : le relevé ne montre que les derniers usages
            else:
                u = {"id": uid, "t": su.maintenant()}
            u.update({"agent": ctx.chef(), "tache": None, "modele": modele, **c, "estime": False, "etape": "gestion"})
            usages.append(u)


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
        titulaires.append({"cle": "chef", "chef": True, "lieu": "local", "modele": ctx.f["modele_orchestrateur"],
                           "permanent": True})
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
        if d["type"] in ("retour", "challenge") and isinstance(d.get("tache"), str):   # un challenge ouvre sa tâche
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
             "modele_depart": t["modele_depart"], "montee": t["montee"], "bloquee": t["bloquee"],
             "lot": dict(t["lot"]) if isinstance(t.get("lot"), dict) else None}
        if t.get("lignes") is not None:
            v["lignes"] = t["lignes"]
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
        if f.get("cahiers_precedents"):
            v["cahiers_precedents"] = [{**c, "maquette": [chemin(x) for x in c["maquette"]]}
                                       for c in f["cahiers_precedents"]]
        if f["methode"] and f["methode"].get("chemin"):
            v["methode"] = {**f["methode"], "chemin": chemin(f["methode"]["chemin"])}
        if f["livrable"] and f["livrable"].get("chemin"):
            v["livrable"] = {**f["livrable"], "chemin": chemin(f["livrable"]["chemin"])}
        v["documents"] = [{**d, "chemin": chemin(d["chemin"])} for d in documents_complets(f, s["taches"])]
        if f.get("glossaire"):
            v["glossaire"] = [dict(g) for g in f["glossaire"]]
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
        for d in s["demandes"]:   # la discussion ouverte sur cette leçon (un challenge), s'il y en a une
            if d["type"] == "challenge" and isinstance(d.get("cible"), dict) and d["cible"].get("id") == x["id"]:
                le["challenge_tache"] = d.get("tache")
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
         "decisions_projet": [dict(d) for d in s["decisions_projet"]],
         "agents_locaux_max": ctx.f["agents_locaux_max"],
         "orchestrateur_present": guetteur.present(_presence(ctx), datetime.now().astimezone())}
    # La facturation : les usages récents, au format du bureau (une tâche ou un agent disparu devient « hors tâche »).
    ids_taches, cles_titulaires = {t["id"] for t in taches}, {t["cle"] for t in titulaires}
    r["usage"] = [_usage_au_releve(u, ids_taches, cles_titulaires) if u.get("genre") == "partenaire" else
                  {"id": u["id"], "tache": u["tache"] if u.get("tache") in ids_taches else None,
                   "agent": u["agent"] if u.get("agent") in cles_titulaires else None, "modele": u["modele"],
                   "t": u["t"], "entree": u["entree"], "sortie": u["sortie"],
                   "cache_lecture": u.get("cache_lecture", 0), "cache_ecriture": u.get("cache_ecriture", 0),
                   **({"etape": u["etape"]} if u.get("etape") else {}),
                   **({"lot": u["lot"]} if u.get("lot") else {}),
                   **({"reparti": u["reparti"]} if u.get("reparti") else {})}
                  for u in (s.get("usage") or [])[-USAGES_AU_RELEVE:]]
    partenaires = _releve_partenaires(ctx)
    if partenaires is not None:
        r["partenaires"] = partenaires
    return r


def _usage_au_releve(u, ids_taches, cles):
    """Une ligne d'usage d'un partenaire, au format du bureau (aucune clé : il n'y en a jamais dans le suivi)."""
    return {"id": u["id"], "genre": "partenaire", "partenaire": u["partenaire"], "t": u["t"],
            "tache": u["tache"] if u.get("tache") in ids_taches else None,
            "agent": u["agent"] if u.get("agent") in cles else None,
            "quantite": u["quantite"], "unite": u["unite"], "cout": u.get("cout"), "devise": u.get("devise"),
            "estime": bool(u.get("estime"))}


# --- Les partenaires : connexions, quotas, règles, choix, usage. Jamais une valeur de clé dans une sortie ou un fichier.

CHAMPS_AFFICHES = ("id", "nom", "categorie", "sous_categorie", "description", "site", "inscription", "connexions",
                   "plans", "gratuit", "quota_lisible", "illimite", "statut", "fiabilite", "verifie_le", "popularite")
RAISON_RELEVE = "quota épuisé (relevé)"
QUOTA_TOUTES_LES_S = 3600   # au plus une lecture par heure et par partenaire, sauf `force`
TOKENS_PAR_FICHE = 20_000   # revérifier une fiche : deux pages lues et la fiche réécrite, sur Sonnet
PART_SORTIE_FICHE = 0.2
_DEVISE = re.compile(r"^[A-Z]{3}\Z")
GIT = memoire.executer_git   # remplacé par les tests


def _projet(ctx):
    """Le dossier du projet : celui qui contient `.factory/`, sinon celui du fichier de factory."""
    base = Path(ctx.f["base"])
    return base.parent if base.name == ".factory" else base


def _chemin_catalogue(ctx):
    return Path(ctx.f["skill"]) / "partenaires" / "catalogue.json"


def _catalogue(ctx):
    """Le catalogue de la skill du projet (celui que « Mettre à jour les offres » réécrit), sinon celui du paquet."""
    chemin = _chemin_catalogue(ctx)
    try:
        return pcat.lire(chemin if chemin.is_file() else None)
    except (OSError, ValueError) as ex:
        raise Refus(f"Catalogue des partenaires illisible : {ex}")


def _etat_partenaires():
    return petat.Etat()


def _lire_conseils(ctx, strict=False):
    """Les conseils du projet. Illisibles : un refus si `strict` (lecture demandée), sinon aucun conseil (le choix passe
    alors au catalogue, rien ne bloque)."""
    chemin = petat.chemin_conseils(ctx.f["base"])
    try:
        d = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"besoins": {}}
    except (OSError, ValueError) as ex:
        if strict:
            raise Refus(f"Conseils des partenaires illisibles ({chemin.name}) : {ex}")
        return {"besoins": {}}
    b = d.get("besoins") if isinstance(d, dict) else None
    return {"besoins": b if isinstance(b, dict) else {}}


def ecrire_json_atomique(chemin, objet):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(objet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, chemin)


def _partenaire(e, par_id, cle="partenaire"):
    i = texte(e, cle)
    if i not in par_id:
        raise Refus(f"Partenaire inconnu du catalogue : {i}")
    return i


def _nombre(e, cle, obligatoire=True):
    v = e.get(cle)
    if v is None and not obligatoire:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v < 0 or v == float("inf"):
        raise Refus(f"« {cle} » doit être un nombre positif ou nul.")
    return v


def _p_detecter(ctx, e, cat, par_id):
    return {"connexions": pdet.mettre_a_jour(_projet(ctx), cat, _etat_partenaires())}


def _p_confirmer(ctx, e, cat, par_id):
    ids = liste_de_textes(e, "ids")
    for i in ids:
        if i not in par_id:
            raise Refus(f"Partenaire inconnu du catalogue : {i}")
    source = texte(e, "source", obligatoire=False)
    retirer = e.get("retirer") is True
    quand = su.maintenant()
    with _etat_partenaires().transaction() as d:
        for i in ids:
            c = d["connexions"].setdefault(i, {})
            c.update(etat="non_connecte" if retirer else "connecte", vu_le=quand,
                     source=source or c.get("source") or "outils vus par l'orchestrateur")
    return {"ok": True, "ids": ids}


def _p_quota(ctx, e, cat, par_id):
    """Relève les quotas lisibles (au plus une fois par heure et par partenaire, sauf `force`)."""
    import datetime
    force = e.get("force") is True
    d = _etat_partenaires().lire()
    if "ids" in e:
        ids = liste_de_textes(e, "ids")
        for i in ids:
            if i not in par_id:
                raise Refus(f"Partenaire inconnu du catalogue : {i}")
    else:
        ids = [i for i, c in d["connexions"].items() if c.get("etat") in ("connecte", "declare") and i in par_id]
    instant = datetime.datetime.now().astimezone()
    lus, sautes, rates, a_noter = [], [], [], {}
    for i in ids:
        lien = pquota.lecteur_de(i)   # le lecteur et ses variables sont figés dans l'outil, jamais lus du catalogue
        if not lien:
            sautes.append({"id": i, "raison": "quota non lisible par l'API"})
            continue
        derniere = d["lectures"].get(i)
        if not force and derniere and lire_date(derniere) != TRES_ANCIEN and \
                (instant - lire_date(derniere)).total_seconds() < QUOTA_TOUTES_LES_S:
            sautes.append({"id": i, "raison": "déjà lu il y a moins d'une heure"})
            continue
        cle = pdet.cle_des_variables(lien[1], _projet(ctx))   # pour cet appel seulement
        if not cle:
            sautes.append({"id": i, "raison": f"aucune clé ({' ou '.join(lien[1])} : environnement ou .env du projet)"})
            continue
        res = pquota.lire(lien[0], cle)
        del cle
        a_noter[i] = res
        (lus if res is not None else rates).append(i)
    if a_noter:
        quand = su.maintenant()
        with _etat_partenaires().transaction() as d:
            for i, res in a_noter.items():
                d["lectures"][i] = quand
                if res is None:
                    continue
                d["quotas"][i] = {**{k: res[k] for k in ("reste", "unite", "illimite") if k in res}, "lu_le": quand}
                if res.get("abonnement") and i in d["connexions"]:
                    d["connexions"][i]["abonnement"] = res["abonnement"]
                posee = (d["limites"].get(i) or {}).get("raison") == RAISON_RELEVE
                if (res.get("illimite") or (res.get("reste") or 0) > 0) and posee:
                    d["limites"].pop(i)   # seule une limite posée par un relevé est levée par un relevé
                elif res.get("reste") == 0:
                    d["limites"][i] = {"depuis": quand, "raison": RAISON_RELEVE}
    return {"lus": lus, "rates": rates, "sautes": sautes}


def _p_choisir(ctx, e, cat, par_id):
    besoin = texte(e, "besoin")
    conseils = [x.get("id") for x in _lire_conseils(ctx)["besoins"].get(besoin) or [] if isinstance(x, dict)]
    try:
        d = _etat_partenaires().lire()
    except petat.EtatIllisible as ex:   # rien ne bloque : aucun partenaire, le mode manuel prend le relais
        return {"partenaires": [], "meilleur_non_connecte": None, "avertissement": str(ex)}
    r = pchoix.ordonner(besoin, conseils, cat, d)
    for x in r["partenaires"]:
        x["nom"] = par_id[x["id"]]["nom"]
    return r


def _p_usage(ctx, e, cat, par_id):
    i = _partenaire(e, par_id)
    quantite, unite = _nombre(e, "quantite"), texte(e, "unite")
    cout = _nombre(e, "cout", obligatoire=False)
    devise = e.get("devise")
    if cout is not None and not (isinstance(devise, str) and _DEVISE.match(devise)):
        raise Refus("Un « cout » a sa « devise » (code à trois lettres : USD, EUR…).")
    if "estime" in e and not isinstance(e["estime"], bool):
        raise Refus("« estime » doit être vrai ou faux.")
    agent, tache = e.get("agent"), e.get("tache")
    if agent is not None and agent not in ctx.cles_agents():
        raise Refus(f"Agent inconnu : {agent}")
    with ctx.suivi.transaction() as s:
        if tache is not None and su.tache(s, tache) is None:
            raise Refus(f"Tâche inconnue : {tache}")
        u = {"id": f"u{su.suivant(s, 'u')}", "genre": "partenaire", "t": su.maintenant(), "partenaire": i,
             "tache": tache, "agent": agent, "quantite": quantite, "unite": unite, "cout": cout,
             "devise": devise if cout is not None else None, "estime": e.get("estime") is True}
        s.setdefault("usage", []).append(u)
    return {"id": u["id"]}


def _p_limite(ctx, e, cat, par_id):
    i, raison = _partenaire(e, par_id), texte(e, "raison")
    with _etat_partenaires().transaction() as d:
        d["limites"][i] = {"depuis": su.maintenant(), "raison": raison[:200]}
    return {"ok": True}


def _p_regle(ctx, e, cat, par_id):
    i = _partenaire(e, par_id)
    with _etat_partenaires().transaction() as d:
        try:
            r = petat.regle(d, i, e.get("operation"), e.get("id"), e.get("texte"))
        except ValueError as ex:
            raise Refus(str(ex))
    return {"regle": r}


def _p_conseils(ctx, e, cat, par_id):
    if "besoins" not in e:
        return _lire_conseils(ctx, strict=True)
    erreurs = pcat.verifier_conseils(e["besoins"], par_id)
    if erreurs:
        raise Refus(" ".join(erreurs[:5]))
    propre = {b: [{"id": x["id"], "raison": x["raison"].strip()} for x in liste] for b, liste in e["besoins"].items()}
    ecrire_json_atomique(petat.chemin_conseils(ctx.f["base"]), {"besoins": propre})
    return {"besoins": propre}


def _prix_sonnet(ctx):
    """Le prix de Sonnet en euros par million (entrée, sortie) d'après les prix enregistrés du bureau, ou None."""
    if not ctx.f["reglages"]:
        return None
    try:
        from bureau import prix
        regl = json.loads(Path(ctx.f["reglages"]).read_text(encoding="utf-8-sig"))
        table = prix.TablePrix(Path(ctx.f["reglages"]).parent / "prix-historique.jsonl")
        p = prix.prix_effectif(table, regl, "Sonnet", su.maintenant())[0]
    except Exception:   # noqa: BLE001 — un coût inconnu est dit « inconnu », jamais inventé
        return None
    return p if p and p.get("entree") is not None and p.get("sortie") is not None else None


def cout_maj(ctx, cat):
    """Le coût estimé de « Mettre à jour les offres » : les fiches à refaire, en lots sur Sonnet."""
    import datetime
    ids = pcat.a_refaire(cat, datetime.date.today())
    tokens = len(ids) * TOKENS_PAR_FICHE
    if not ids:
        return {"euros": 0, "texte": "Aucune fiche à revérifier : toutes l'ont été depuis moins de "
                                     f"{pcat.AGE_A_REFAIRE_J} jours."}
    p = _prix_sonnet(ctx)
    euros = None if p is None else round(tokens * ((1 - PART_SORTIE_FICHE) * p["entree"] + PART_SORTIE_FICHE * p["sortie"])
                                         / 1_000_000, 2)
    return {"euros": euros, "texte": f"{len(ids)} fiches à revérifier sur les sites des partenaires, en lots sur Sonnet "
                                     f"(environ {tokens:,} tokens).".replace(",", " ")}


def _p_a_refaire(ctx, e, cat, par_id):
    import datetime
    return {"ids": pcat.a_refaire(cat, datetime.date.today()), "cout": cout_maj(ctx, cat)}


def _p_offres(ctx, e, cat, par_id):
    """Réécrit des fiches du catalogue de la skill (après la recherche), contrôle, commit et push comme une leçon."""
    nouvelles = e.get("partenaires")
    if not isinstance(nouvelles, list) or not nouvelles or not all(isinstance(x, dict) for x in nouvelles):
        raise Refus("« partenaires » doit être une liste non vide de fiches complètes du catalogue.")
    par_nouvel_id = {x.get("id"): x for x in nouvelles}
    neuf = {**cat, "partenaires": [par_nouvel_id.pop(p["id"], p) for p in cat["partenaires"]] + list(par_nouvel_id.values())}
    erreurs = pcat.verifier(neuf)
    if erreurs:
        raise Refus("Catalogue refusé : " + " ; ".join(erreurs[:5]))
    texte_neuf = json.dumps(neuf, ensure_ascii=False, indent=2) + "\n"
    chemin = _chemin_catalogue(ctx)
    ok, message = memoire._ecrire_et_pousser(
        ctx.f["skill"], chemin, lambda _avant: texte_neuf, ctx.f["mots_interdits"],
        json.dumps(nouvelles, ensure_ascii=False), f"Partenaires : {len(nouvelles)} fiche(s) mise(s) à jour", GIT)
    message = (message.replace("Leçon ajoutée", "Catalogue mis à jour").replace("elle n'est pas publiée", "il n'est pas publié")
               .replace("le fichier de mémoire", "le catalogue").replace("réécrire la leçon", "réécrire les fiches"))
    if not ok:
        raise Refus(message)
    return {"ok": True, "message": message, "ids": [x["id"] for x in nouvelles]}


ACTIONS_PARTENAIRES = {"detecter": _p_detecter, "confirmer": _p_confirmer, "quota": _p_quota, "choisir": _p_choisir,
                       "usage": _p_usage, "limite": _p_limite, "regle": _p_regle, "conseils": _p_conseils,
                       "a_refaire": _p_a_refaire, "offres": _p_offres}


def cmd_partenaires(ctx, e):
    action = e.get("action")
    if action not in ACTIONS_PARTENAIRES:
        raise Refus("« action » doit valoir " + ", ".join(ACTIONS_PARTENAIRES) + ".")
    cat = _catalogue(ctx)
    par_id = {p["id"]: p for p in cat["partenaires"]}
    try:
        return ACTIONS_PARTENAIRES[action](ctx, e, cat, par_id)
    except su.SuiviOccupe:
        raise
    except petat.EtatIllisible as ex:
        raise Refus(str(ex))
    except OSError as ex:
        raise Refus(f"Fichier des partenaires inaccessible : {ex}"[:300])


def regles_des_partenaires(ctx, ids):
    """[(nom, [textes])] des partenaires d'une tâche, leurs règles mot pour mot (une liste vide : aucune règle)."""
    if not ids:
        return []
    try:
        cat = _catalogue(ctx)
        d = _etat_partenaires().lire()
    except (Refus, OSError, ValueError):
        return []
    noms = {p["id"]: p["nom"] for p in cat["partenaires"]}
    return [(noms.get(i, i), [r["texte"] for r in d["regles"].get(i) or [] if isinstance(r, dict) and r.get("texte")])
            for i in ids]


def _releve_partenaires(ctx):
    """Le champ `partenaires` du relevé : le catalogue réduit aux champs affichés, l'état (sans clé), les conseils."""
    try:
        cat = _catalogue(ctx)
        conseils = _lire_conseils(ctx)["besoins"]
    except Refus:
        return None
    try:
        d = _etat_partenaires().lire()
    except (OSError, ValueError):   # illisible : rien d'affiché comme connu (ni la règle de départ déjà retirée)
        d = {s: {} for s in petat.SECTIONS}
    ids = {p["id"] for p in cat["partenaires"]}
    categories = {c: [{k: p[k] for k in CHAMPS_AFFICHES if k in p} for p in liste]
                  for c, liste in pcat.par_categorie(cat).items() if liste}
    etat = {s: {i: v for i, v in d[s].items() if i in ids} for s in ("connexions", "quotas", "limites", "regles")}
    etat["limites"] = {i: v for i, v in etat["limites"].items() if petat.limite_active(v)}
    etat["connexions"] = {i: {k: v[k] for k in ("etat", "source", "abonnement", "vu_le") if k in v}
                          for i, v in etat["connexions"].items() if v.get("etat") in petat.ETATS}
    dates = [p["verifie_le"] for p in cat["partenaires"] if isinstance(p.get("verifie_le"), str)]
    return {"categories": categories, "etat": etat,
            "conseils": {b: [{"id": x["id"], "raison": x.get("raison")} for x in liste
                             if isinstance(x, dict) and x.get("id") in ids]
                         for b, liste in conseils.items() if isinstance(liste, list)},
            "maj_catalogue": max(dates) if dates else None, "cout_maj": cout_maj(ctx, cat)}


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
    role, modele, lieu = texte(e, "role"), texte(e, "modele", obligatoire=False), texte(e, "lieu", obligatoire=False)
    fiches_ = _fiches_avec_sessions(ctx)
    cle, raison = depart.agent_libre(fiches_, ctx.suivi.lire()["taches"], role, modele, lieu,
                                     ctx.f["agents_locaux_max"])
    sortie = {"agent": cle, "raison": raison}
    if cle is None and lieu == "cloud":   # la fiche qui attend sa session : la clé de la décision session_cloud
        sortie["sans_session"] = depart.sans_session(fiches_, role, modele)
    return sortie


def _sans_doublon(elements):
    vus, sortie = set(), []
    for x in elements:
        cle = json.dumps(x, sort_keys=True, ensure_ascii=False)
        if cle not in vus:
            vus.add(cle)
            sortie.append(x)
    return sortie


def _depart_d_un_lot(ctx, e):
    cle, ids = texte(e, "agent"), e.get("taches")
    if "tache" in e:
        raise Refus("Donnez « tache » ou « taches », pas les deux.")
    if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x for x in ids):
        raise Refus("« taches » doit être une liste non vide d'identifiants de tâches.")
    fiche_agent = fi.trouver(_fiches_avec_sessions(ctx), cle)
    if fiche_agent is None:
        raise Refus(f"Agent inconnu : {cle}")
    s = ctx.suivi.lire()
    taches = []
    for i in ids:
        t = su.tache(s, i)
        if t is None:
            raise Refus(f"Tâche inconnue : {i}")
        taches.append(t)
    roles = list(dict.fromkeys(t.get("role") or fiche_agent["role"] for t in taches))
    lecons_lot = {"skill": [], "genre": []}
    for role in roles:
        lues = memoire.lire(ctx.f["memoire"], ctx.f["genre"], role)
        for genre in lecons_lot:
            lecons_lot[genre] = _sans_doublon(lecons_lot[genre] + lues[genre])
    glossaire = []
    for t in taches:
        fonc = su.fonctionnalite(s, t["fonctionnalite"]) if t.get("fonctionnalite") else None
        glossaire = _sans_doublon(glossaire + list((fonc or {}).get("glossaire") or []))
    briefs = [(role, depart.brief(ctx.f, role)) for role in roles]
    ids_partenaires = list(dict.fromkeys(i for t in taches for i in t.get("partenaires") or []))
    return {"message": depart.message_lot(ctx.f, fiche_agent, taches, briefs, lecons_lot, glossaire,
                                          regles_des_partenaires(ctx, ids_partenaires))}


def cmd_depart(ctx, e):
    if "taches" in e:
        return _depart_d_un_lot(ctx, e)
    cle, i = texte(e, "agent"), texte(e, "tache")
    fiche_agent = fi.trouver(_fiches_avec_sessions(ctx), cle)
    if fiche_agent is None:
        raise Refus(f"Agent inconnu : {cle}")
    tache_suivie = su.tache(ctx.suivi.lire(), i)
    if tache_suivie is None:
        raise Refus(f"Tâche inconnue : {i}")
    lecons = memoire.lire(ctx.f["memoire"], ctx.f["genre"], fiche_agent["role"])
    fonc = su.fonctionnalite(ctx.suivi.lire(), tache_suivie.get("fonctionnalite")) if tache_suivie.get("fonctionnalite") else None
    return {"message": depart.message(ctx.f, fiche_agent, tache_suivie, depart.brief(ctx.f, fiche_agent["role"]), lecons,
                                      (fonc or {}).get("glossaire") or [],
                                      regles_des_partenaires(ctx, tache_suivie.get("partenaires") or []))}


def _partie(t):
    """Une tâche déjà partie : active, faite, déjà prise un moment, ou notée dans un lot (le lot est noté juste avant
    son départ : refaire les lots ne le touche jamais)."""
    return bool(t["active"] or t["colonne"] == "fait" or t.get("debut") or isinstance(t.get("lot"), dict))


def _modele_et_lieu(fiches_, t):
    """(modèle, lieu) de la tâche : ceux de son agent, sinon de l'agent libre de son rôle (à défaut, d'une fiche du rôle)."""
    if t.get("agent"):
        f = fi.trouver(fiches_, t["agent"])
        if f:
            return f["modele"], f["lieu"]
    candidates = [f for f in fiches_ if f["role"] == t.get("role")]
    voulues = [f for f in candidates if f["modele"] == t.get("modele_depart")]
    candidates = voulues or candidates
    return (candidates[0]["modele"], candidates[0]["lieu"]) if candidates else None


def cmd_lots(ctx, e):
    """Regroupe les tâches pas encore parties en lots (un modèle, un lieu), selon la taille conseillée de chaque modèle."""
    s = ctx.suivi.lire()
    fiches_ = _fiches_avec_sessions(ctx)
    if "taches" in e:
        ids = e["taches"]
        if not isinstance(ids, list) or not all(isinstance(x, str) and x for x in ids):
            raise Refus("« taches » doit être une liste d'identifiants de tâches.")
        for i in ids:
            t = su.tache(s, i)
            if t is None:
                raise Refus(f"Tâche inconnue : {i}")
            if _partie(t):
                raise Refus(f"La tâche {i} est déjà partie ou faite : elle n'est jamais remise en lot.")
        choisies = [t for t in s["taches"] if t["id"] in ids]
    else:
        choisies = [t for t in s["taches"] if not _partie(t)]
    entrees, ecartees = [], []
    for t in choisies:
        ml = _modele_et_lieu(fiches_, t)
        if ml is None:
            ecartees.append({"tache": t["id"], "raison": "aucun agent pour le rôle de la tâche" if t.get("role")
                             else "la tâche n'a pas de rôle"})
            continue
        entrees.append({"id": t["id"], "modele": ml[0], "lieu": ml[1], "role": t.get("role"),
                        "depend_de": list(t.get("depend_de") or [])})
    choisis = {t["id"] for t in choisies}
    par_id = {t["id"]: t for t in s["taches"]}
    for x in entrees:   # une dépendance faite est tenue ; une dépendance partie mais pas finie fait attendre la tâche
        x["depend_de"] = [d for d in x["depend_de"] if d in choisis or d not in par_id or par_id[d]["colonne"] != "fait"]
    retenues = {x["id"] for x in entrees}
    change = True
    while change:   # attendre une tâche en cours, ou une tâche qui attend elle-même, écarte la tâche
        change = False
        for x in list(entrees):
            attend = next((d for d in x["depend_de"] if d in par_id and d not in retenues), None)
            if attend is not None:
                entrees.remove(x)
                retenues.discard(x["id"])
                ecartees.append({"tache": x["id"], "raison": f"attend la fin de la tâche {attend}"})
                change = True
    rangs = {t["id"]: t["lot"]["rang"] for t in s["taches"] if isinstance(t.get("lot"), dict)}
    mesures = [{**u, "rang": rangs.get(u.get("tache"))} for u in s.get("usage") or []]
    tailles = {m: lots.taille_conseillee(mesures, m) for m in {x["modele"] for x in entrees}}
    numeros = [int(t["lot"]["id"][1:]) for t in s["taches"]
               if isinstance(t.get("lot"), dict) and re.fullmatch(r"L\d+", t["lot"].get("id") or "")]
    try:
        formes = lots.former(entrees, tailles, premier=max(numeros, default=0) + 1)
    except ValueError as ex:
        raise Refus(str(ex))
    return {"lots": formes, "tailles": tailles, "ecartees": ecartees}


COMMANDES = {
    "releve": (cmd_releve, "aucune"), "charge": (cmd_charge, "aucune"), "actions": (cmd_actions, "obligatoire"),
    "reveil": (cmd_reveil, "aucune"), "demandes": (cmd_demandes, "aucune"), "guetter": (cmd_guetter, "aucune"),
    "demande-traitee": (cmd_demande_traitee, "obligatoire"), "etat": (cmd_etat, "aucune"),
    "fonctionnalite": (cmd_fonctionnalite, "obligatoire"), "message": (cmd_message, "obligatoire"),
    "decision": (cmd_decision, "obligatoire"), "tache": (cmd_tache, "obligatoire"), "file": (cmd_file, "obligatoire"),
    "file-prendre": (cmd_file_prendre, "obligatoire"), "session": (cmd_session, "obligatoire"),
    "catalogue": (cmd_catalogue, "obligatoire"), "memoire": (cmd_memoire, "obligatoire"),
    "genre": (cmd_genre, "obligatoire"), "lecon": (cmd_lecon, "obligatoire"), "controle": (cmd_controle, "obligatoire"),
    "agent-libre": (cmd_agent_libre, "obligatoire"), "depart": (cmd_depart, "obligatoire"),
    "organisation": (cmd_organisation, "obligatoire"), "lots": (cmd_lots, "obligatoire"), "detail": (cmd_detail, "obligatoire"), "document": (cmd_document, "obligatoire"), "usage": (cmd_usage, "obligatoire"),
    "partenaires": (cmd_partenaires, "obligatoire"),
}


# --- Exécution : en processus, ou par la commande déclarée du projet (`lancer`).

def lancer_declaree(ctx, nom, entree, extra):
    argv = [rel.developper(a) for a in ctx.f["commandes"][nom] + list(extra)]
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
        if nom not in COMMANDES_DU_BUREAU and not os.environ.get("MYIAFACTORY_VERIFICATION"):
            # l'orchestrateur travaille : il est là (son moniteur a pu expirer) ; la vérification, elle, ne compte pas
            noter_presence(ctx)
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
