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

from bureau import fichiers_joints as fj  # noqa: E402
from bureau import releve as rel  # noqa: E402
from bureau.statuts import TRES_ANCIEN, lire_date  # noqa: E402
from orchestrateur import depart  # noqa: E402
from orchestrateur import factory as fa  # noqa: E402
from orchestrateur import fiches as fi  # noqa: E402
from orchestrateur import guetteur  # noqa: E402
from orchestrateur import transcriptions  # noqa: E402
from orchestrateur import lots  # noqa: E402
from orchestrateur import memoire  # noqa: E402
from orchestrateur import metiers  # noqa: E402
from orchestrateur import modele_necessaire as mn  # noqa: E402
from orchestrateur import recrutement as rc  # noqa: E402
from orchestrateur import regles_projet as rp  # noqa: E402
from orchestrateur import suivi as su  # noqa: E402
from orchestrateur import workflows as wf  # noqa: E402
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
                 "organisation", "genre_fonctionnalite", "environnement", "elargir_genre", "valider_etape", "partenaire_regle", "partenaire_inscrit", "faire_chez_partenaire", "partenaires_actualiser",
                 "partenaires_maj", "installer_outil", "parallelisme", "recruter", "depot_git", "outil_agent", "accord_agent", "regle_projet",
                 "serie_arretee", "fin_vue", "fable_tache", "passer_polyvalent")
AGENT_ORCHESTRATEUR = "orchestrateur"   # les appels de jugement du moteur : connu de chaque projet, sans fiche
MODELES_INTERDITS = ("Fable",)   # un outil ne choisit jamais Fable


def _interdit(modele):
    """Un modèle qu'aucun outil ne choisit, quelle que soit la casse."""
    return isinstance(modele, str) and modele.strip().lower() in {m.lower() for m in MODELES_INTERDITS}


def _fable_accorde_pour(ctx, t):
    """Fable est permis comme modèle de départ d'une tâche seulement si le Directeur l'a accordé pour cette tâche
    (`fable_accordee`, projet aux agents polyvalents), ou si son agent (à défaut, un agent de son rôle) a une fiche qui
    porte l'accord du Directeur."""
    if t.get("fable_accordee") is True:
        return True
    fiches_ = ctx.fiches()
    if t.get("agent"):
        return fi.fable_accorde(fi.trouver(fiches_, t["agent"]))
    return any(fi.fable_accorde(x) for x in fiches_ if x["role"] and x["role"] == t.get("role"))


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
        return ["cadrage"] + wf.ids_etapes(self.f) + ["fait"]

    def premiere_colonne(self, fonc=None):
        """La première étape du workflow de la fonctionnalité (« cadrage » si le projet n'a aucun workflow)."""
        return wf.premiere_etape(self.f, fonc) or "cadrage"

    def sessions(self):
        try:
            d = json.loads(self.f["sessions"].read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(d, dict) else {}

    def image_rangee(self, image, fid, servie="images"):
        """Une image rendue par un agent (chemin ou `{chemin, legende}`), rangée là où le bureau la sert (voir
        `image_rangee`) : le seul point par où passent les images d'un agent, quel que soit le champ."""
        return image_d_agent_rangee(self.f, self.f["base"].parent, image, fid, servie)

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


def liste_d_images(valeur, cle):
    """Les images rendues par un agent : chacune est un chemin (ancienne forme) ou `{chemin, legende?}`, la légende
    étant une phrase de 160 caractères au plus. Rend la liste normalisée : un chemin seul reste un texte, une image
    légendée un objet `{chemin, legende}`."""
    if not isinstance(valeur, list):
        raise Refus(f"« {cle} » doit être une liste d'images.")
    sortie = []
    for x in valeur:
        if not rel.image_legendee_ok(x):
            raise Refus(f"« {cle} » : chaque image est un chemin (texte non vide) ou {{\"chemin\": \"…\", \"legende\": "
                        f"\"…\"}} ; la « legende » est une phrase de {rel.MAX_LEGENDE} caractères au plus.")
        legende = rel.legende_d_image(x)
        sortie.append({"chemin": x["chemin"], "legende": legende.strip()} if legende else rel.chemin_d_image(x))
    return sortie


def chemins_d_images(images):
    return [rel.chemin_d_image(x) for x in images or []]


def images_montrables(chemins, cle):
    """Refuse tout de suite une image que le bureau ne montrerait pas (SVG, WebP…), avec la marche à suivre."""
    for c in chemins:
        if Path(c).suffix.lower() not in IMAGES_MONTREES:
            raise Refus(f"« {cle} » : « {c} » n'est pas une image PNG ou JPEG, et le bureau ne montre que celles-là. "
                        "Convertissez-la en PNG (par exemple une capture de son rendu), puis donnez ce chemin.")
    return chemins


IMAGE_RANGEE_MAX_OCTETS = 20 * 1024 * 1024     # ce que le bureau accepte de servir
RACINES_PAR_DEFAUT = {"images": ["pieces", "captures"], "livrables": ["livrables"]}


def racines_servies(f, cle="images"):
    """(dossier des réglages, racines résolues de `cle` (`images` ou `livrables`) dans les réglages, dossier `pieces`) :
    ce que le bureau sert pour ce genre de fichier. `f` est le fichier de factory lu par `factory.lire`."""
    base, racines = f["base"], list(RACINES_PAR_DEFAUT[cle])
    try:
        if f["reglages"]:
            base = Path(f["reglages"]).resolve().parent
            conf = json.loads(Path(f["reglages"]).read_text(encoding="utf-8-sig")).get(cle)
            if isinstance(conf, dict) and isinstance(conf.get("racines"), list):
                racines = [x for x in conf["racines"] if isinstance(x, str) and x]
    except (OSError, ValueError, AttributeError):
        pass
    return base, [(base / x).resolve() for x in racines], Path(f["pieces"] or base / "pieces").resolve()


def _sous(chemin, dossier):
    try:
        chemin.relative_to(dossier)
        return True
    except ValueError:
        return False


def image_rangee(f, dossier_projet, chemin, fid, servie="images"):
    """LE point où une image citée par un agent est rangée là où le bureau la sert (`f` : le fichier de factory lu,
    `dossier_projet` : le parent de `.factory`, où travaille l'agent). Une image PNG ou JPEG (extension et début du
    contenu vérifiés, 20 Mo au plus) qui existe dans le dossier du projet est rendue comptée depuis le fichier de
    factory ; si elle n'est pas sous une racine de `servie` (`images` : `pieces/<fid>/` ; `livrables` : la première
    racine de livrables, `<fid>/`), elle y est COPIÉE (jamais déplacée, jamais écrasée : suffixe -2, -3 ; la même
    image déjà rangée n'est pas doublée). Absente, hors du projet, lien sortant ou pas une image : le chemin est
    gardé tel quel et rien n'est copié."""
    if (not isinstance(fid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", fid) or not isinstance(chemin, str)
            or not chemin.strip() or "\x00" in chemin):
        return chemin
    p = Path(chemin.replace("\\", "/"))
    signature = SIGNATURES.get(p.suffix.lower())
    if signature is None:
        return chemin
    base, racines, pieces = racines_servies(f, servie)
    projet = Path(dossier_projet).resolve()
    try:
        candidats = [p] if p.is_absolute() else [f["base"] / p, base / p, projet / p]
        source = next((c.resolve() for c in candidats if c.is_file()), None)
        if source is None or not _sous(source, projet) or source.stat().st_size > IMAGE_RANGEE_MAX_OCTETS:
            return chemin
        octets = source.read_bytes()
        if not octets.startswith(signature[0]):
            return chemin
        cible = source
        if not any(_sous(source, r) for r in racines):
            dossier = (racines[0] if servie == "livrables" and racines else pieces) / fid
            dossier.mkdir(parents=True, exist_ok=True)
            cible, n = dossier / source.name, 1
            while cible.exists() and cible.read_bytes() != octets:
                n += 1
                cible = dossier / f"{source.stem}-{n}{source.suffix}"
            if not cible.exists():
                cible.write_bytes(octets)
        return Path(os.path.relpath(cible, f["base"])).as_posix()
    except OSError:
        return chemin


def image_d_agent_rangee(f, dossier_projet, image, fid, servie="images"):
    """Une image `chemin` ou `{chemin, legende}` passée par `image_rangee` ; la légende reste avec son image."""
    if isinstance(image, dict):
        return {**image, "chemin": image_rangee(f, dossier_projet, image.get("chemin"), fid, servie)}
    return image_rangee(f, dossier_projet, image, fid, servie)


ORIGINE_DOCUMENT = ("agent", "etape", "tache", "element", "sous_tache")


def ranger_documents(donnees, f, chemins, titre=None, **origine):
    """Range des fichiers produits pour la fonctionnalité dans ses documents, avec leur origine (agent, étape, tâche,
    élément, sous-tâche) et la date. Un chemin déjà rangé n'est pas doublé : son titre et son origine sont complétés.
    Une image peut être `{chemin, legende}` : sa légende tient lieu de titre tant que le document n'a que son nom de fichier."""
    documents = f.setdefault("documents", [])
    for image in chemins or []:
        c, legende = rel.chemin_d_image(image), rel.legende_d_image(image)
        d = next((x for x in documents if x["chemin"] == c), None)
        if d is None:
            d = {"id": f"doc{su.suivant(donnees, 'doc')}", "chemin": c, "titre": titre or legende or Path(c).name,
                 "date": su.maintenant()}
            documents.append(d)
        elif titre:
            d["titre"] = titre
        elif legende and d.get("titre") == Path(c).name:
            d["titre"] = legende
        for cle in ORIGINE_DOCUMENT:
            if origine.get(cle):
                d[cle] = origine[cle]
    return documents


def _chemin_ou_image(x, chemin):
    """Une image d'agent au relevé : son chemin compté depuis les réglages, avec sa légende si elle en a une."""
    legende = rel.legende_d_image(x)
    return {"chemin": chemin(rel.chemin_d_image(x)), "legende": legende} if legende else chemin(rel.chemin_d_image(x))


def _image_au_releve(x, chemin):
    """Une image de tâche au relevé : toujours `{chemin, legende?}`."""
    legende = rel.legende_d_image(x)
    return {"chemin": chemin(rel.chemin_d_image(x)), **({"legende": legende} if legende else {})}


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

    def ajouter(image, **origine):
        c = rel.chemin_d_image(image)
        if c not in connus:
            connus.add(c)
            documents.append({"chemin": c, "titre": rel.legende_d_image(image) or Path(c).name,
                              **{k: v for k, v in origine.items() if v}})
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


def ranger_fichiers(ctx, fichiers, sous_dossier, deja=0):
    """Écrit les fichiers joints (base64) sous `pieces/<sous_dossier>/` et rend `[{chemin, nom, type, taille}]` (chemin relatif au
    fichier de factory). Mêmes règles que le bureau (`bureau.fichiers_joints`) : liste blanche d'extensions, signature du contenu,
    plafonds ; le nom de fichier rangé est un nom sûr, le nom d'origine reste dans `nom`. Rien n'est ouvert ni décompressé."""
    probleme = fj.verifier(fichiers, deja, deja)   # `deja` : les images d'avant (champ `images`), toutes PNG ou JPEG
    if probleme:
        raise Refus(probleme)
    horodatage = su.maintenant()[:19].replace("-", "").replace(":", "").replace("T", "-")
    dossier = ctx.f["pieces"] / sous_dossier
    sortie = []
    for f in fichiers:
        octets, _ = fj.verifier_un(f, "Fichier")
        dossier.mkdir(parents=True, exist_ok=True)
        sur = fj.nom_sur(f["nom"])
        cible, n = dossier / f"{horodatage}-{sur}", 1
        while cible.exists():
            n += 1
            cible = dossier / f"{horodatage}-{n}-{sur}"
        cible.write_bytes(octets)
        sortie.append({"chemin": Path(os.path.relpath(cible, ctx.f["base"])).as_posix(), "nom": f["nom"],
                       "type": fj.type_de(f["nom"]), "taille": len(octets)})
    return sortie


def _pieces_jointes(ctx, e, sous_dossier):
    """`(images, fichiers)` d'une demande : les chemins des images PNG ou JPEG (champ `images` d'avant, plus celles du champ
    `fichiers`) et la liste `{chemin, nom, type, taille}` de tout ce que le champ `fichiers` joint."""
    images = ranger_images(ctx, e["images"], sous_dossier) if e.get("images") else []
    fichiers = ranger_fichiers(ctx, e["fichiers"], sous_dossier, len(images)) if e.get("fichiers") else []
    return images + [x["chemin"] for x in fichiers if rel.est_image(x["chemin"])], fichiers


# --- Les commandes. Chacune : (ctx, entrée) -> objet ; Refus ou Appel en cas de problème.

def cmd_releve(ctx, e):
    return construire_releve(ctx)


def cmd_charge(ctx, e):
    if ctx.f["reglages"] is None:
        raise Refus("Le fichier de factory n'indique pas les réglages du bureau (« reglages »).")
    lanceur = ctx.f["skill"] / "lancer.py"
    try:
        p = subprocess.run([sys.executable, str(lanceur), "charge", "--reglages", str(ctx.f["reglages"])],
                           capture_output=True, timeout=120, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # jamais de fenêtre noire
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Refus(f"La mesure de charge n'a pas pu être lancée : {ex}")
    ligne = (p.stdout.decode("utf-8", "replace").strip().splitlines() or [""])[0]
    if p.returncode not in (0, 1):
        raise Refus(ligne or f"La mesure de charge a échoué (code {p.returncode}).")
    return {"feu_vert": p.returncode == 0, "texte": ligne}


def _empreinte_demande(d):
    return {k: v for k, v in d.items() if k not in ("id", "statut", "reponse")}


def erreur_reponses(reponses, verdict):
    """Les réponses de la fenêtre de validation : `[{point, ok}]`, un point au plus une fois, 1 à 8 ; le verdict en
    découle (tous OK : « valider », sinon « renvoyer »). Le message d'erreur, ou `None`."""
    if (not isinstance(reponses, list) or not 1 <= len(reponses) <= rel.MAX_POINTS
            or not all(isinstance(x, dict) and set(x) == {"point", "ok"} and rel.point_ok(x["point"])
                       and isinstance(x["ok"], bool) for x in reponses)
            or len({x["point"].strip() for x in reponses}) != len(reponses)):
        return (f"« reponses » : une réponse {{point, ok (vrai ou faux)}} par point à vérifier, {rel.MAX_POINTS} au "
                "plus.")
    attendu = "valider" if all(x["ok"] for x in reponses) else "renvoyer"
    if verdict != attendu:
        return f"Le verdict doit être « {attendu} » : il découle des réponses point par point."
    return None


def cmd_actions(ctx, e):
    """Une demande du bureau : elle devient une ligne « en attente » du suivi et du journal."""
    genre = e.get("type")
    if genre not in TYPES_DEMANDE:
        raise Refus(f"Demande inconnue : {genre}")
    cible = e.get("tache")
    if genre == "deplacer" and isinstance(cible, str) and (cible == "orchestration" or cible.startswith("cadrage:")):
        # Ces deux tâches ne sont montrées qu'au relevé (le chef qui orchestre, un cadrage en cours) : rien à déplacer.
        raise Refus("Cette tâche suit l'orchestrateur et ne se déplace pas.")
    if genre == "valider_etape" and "reponses" in e:     # la fenêtre de validation : une réponse par point
        probleme = erreur_reponses(e["reponses"], e.get("verdict"))
        if probleme:
            raise Refus(probleme)
    with ctx.suivi.transaction() as s:
        demande = {k: v for k, v in e.items() if k not in ("images", "fichiers")}
        demande["t"] = e["t"] if _date_valide(e.get("t")) else su.maintenant()
        if "id" in demande:   # l'id d'un bouton ou d'une leçon visée ne doit pas écraser celui de la demande
            demande["cible"] = demande.pop("id")
        demande["id"] = f"r{su.suivant(s, 'r')}"
        demande["statut"], demande["reponse"] = "en attente", None
        if genre == "fonctionnalite":
            f = su.nouvelle_fonctionnalite(s, texte(e, "texte")[:40])
            images, fichiers = _pieces_jointes(ctx, e, f["id"])
            su.ajouter_message(s, f, "utilisateur", e["texte"], images, demande["t"], fichiers)
            ranger_documents(s, f, images, agent="utilisateur", etape=f["etape"])
            demande["fonctionnalite"] = f["id"]
            if images:
                demande["images"] = images
            if fichiers:
                demande["fichiers"] = fichiers
        elif genre == "message":
            f = _fonc(s, e.get("fonctionnalite"))
            images, fichiers = _pieces_jointes(ctx, e, f["id"])
            su.ajouter_message(s, f, "utilisateur", texte(e, "texte"), images, demande["t"], fichiers)
            ranger_documents(s, f, images, agent="utilisateur", etape=f["etape"])
            if images:
                demande["images"] = images
            if fichiers:
                demande["fichiers"] = fichiers
        elif genre == "faire_chez_partenaire":      # le retour de « À faire chez … » : le résultat rangé comme une pièce jointe
            d = next((x for x in s["decisions_projet"] if x["id"] == e.get("decision") and x.get("genre") == genre), None)
            if d is None:
                raise Refus(f"Décision inconnue : {e.get('decision')}")
            if e.get("fichiers"):
                demande["fichiers"] = ranger_fichiers(ctx, e["fichiers"], f"partenaires/{d['id']}")
        elif genre == "challenge" and isinstance(e.get("cible"), dict) and e["cible"].get("type") == "lecon":
            # Challenger une leçon ouvre une tâche : la discussion y a lieu (ce texte, puis les réponses et retours).
            lecon = next((x for x in s["lecons"] if x["id"] == e["cible"].get("id")), None)
            if lecon is None:
                raise Refus(f"Leçon inconnue : {e['cible'].get('id')}")
            t = {"id": f"t{su.suivant(s, 't')}", "titre": f"Challenge de la leçon {lecon['id']}", "fonctionnalite": None,
                 "element": None, "role": None, "colonne": ctx.premiere_colonne(), "agent": None, "etape": "Discussion",
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
        retrait = bool(x.get("retrait_prevu"))     # l'équipe a perdu sa place : il finit sa tâche, rien d'autre
        sortie.append({"cle": x["cle"], "role": x["role"], "service": x["service"], "modele": x["modele"],
                       "lieu": x["lieu"], "session": sessions.get(x["cle"]) or x["session"],
                       "libre": x["cle"] not in occupes and not retrait, **({"retrait_prevu": True} if retrait else {})})
    return sortie


def _fonc_compacte(f):
    """Une fonctionnalité en quelques lignes : de quoi décider du prochain geste, sans relire la discussion entière."""
    d = f["discussion"]
    dernier = d[-1] if d else None
    cahier, methode = f.get("cahier"), f.get("methode")
    return {
        "id": f["id"], "nom": f["nom"], "etape": f["etape"], "genre": f.get("genre"), "workflow": f.get("workflow"),
        "deplacee_vers": f.get("deplacee_vers"), "agent_cadrage": f["agent_cadrage"],
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
        f = _fonc(s, e["fonctionnalite"])
        sortie = _resume_fonc(f) | {"file": list(f["file"]), "elements": dict(f.get("elements") or {})}
        if e.get("taches") is True:      # toutes ses tâches, faites comprises (le moteur relancé reprend sa série)
            sortie["taches"] = [_tache_compacte(t) for t in s["taches"] if t.get("fonctionnalite") == f["id"]]
        return sortie
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
            or not isinstance(c.get("etapes"), list) or not all(isinstance(x, str) for x in c["etapes"])):
        raise Refus("« cahier » doit avoir une « maquette » (liste de chemins, ou de {chemin, legende}) et des "
                    "« etapes » (liste de textes).")
    if "partenaires" in c and not rel.partenaires_cahier_ok(c["partenaires"]):
        raise Refus("« cahier.partenaires » est une liste de {id, mode} (mode : direct, inscrit ou aucun), un partenaire au "
                    "plus une fois.")
    c["maquette"] = liste_d_images(c["maquette"], "cahier.maquette")
    images_montrables(chemins_d_images(c["maquette"]), "cahier.maquette")
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
    if not ancien or (nouveau and (chemins_d_images(nouveau["maquette"]), nouveau["etapes"])
                      == (chemins_d_images(ancien["maquette"]), ancien["etapes"])):   # une légende seule n'est pas une version
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
        if "genre" in e:
            if e["genre"] is not None and not (isinstance(e["genre"], str) and fa.MOTIF_GENRE.match(e["genre"])):
                raise Refus("« genre » doit être nul ou un identifiant de genre "
                            "(minuscules, chiffres et tirets, 40 caractères au plus).")
            f["genre"] = e["genre"]
        if "workflow" in e:
            connus = [w["id"] for w in wf.tous(ctx.f)]
            if e["workflow"] is not None and e["workflow"] not in connus:
                raise Refus(f"Workflow inconnu « {e['workflow']} » ({', '.join(connus) or 'aucun'}).")
            f["workflow"] = e["workflow"]
        if "deplacee_vers" in e:   # le nom du projet où la fonctionnalité est partie (étape « deplacee »)
            f["deplacee_vers"] = texte(e, "deplacee_vers", obligatoire=False)
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
                        if e[cle].get("partenaires"):
                            verifier_partenaires_cadrage(ctx, e[cle]["partenaires"])
                        e[cle]["maquette"] = [ctx.image_rangee(x, f["id"]) for x in e[cle]["maquette"]]
                    elif cle == "livrable" and e[cle].get("chemin"):
                        e[cle]["chemin"] = ctx.image_rangee(e[cle]["chemin"], f["id"], "livrables")
                if cle == "cahier":
                    _archiver_cahier(f, e[cle])
                f[cle] = e[cle]
        if e.get("cahier"):
            ranger_documents(s, f, e["cahier"]["maquette"], agent=f["agent_cadrage"], etape="cahier")
        if "catalogue" in e:
            if not isinstance(e["catalogue"], bool):
                raise Refus("« catalogue » doit être vrai ou faux.")
            f["catalogue"] = e["catalogue"]
        if "fin" in e:       # la fin de la fonctionnalité, annoncée au bureau de direction
            f["fin"] = {**_fin_verifiee(e["fin"]), "date": su.maintenant(), "vu": False}
        if e.get("fin_vue") is True:    # « Vu » : l'avis de fin se ferme
            if not isinstance(f.get("fin"), dict):
                raise Refus("Cette fonctionnalité n'a pas d'avis de fin.")
            f["fin"]["vu"] = True
        glossaire = _glossaire_entree(e, None)
        if glossaire:
            fusionner_glossaire(ctx, s, f, glossaire, None)
        f["maj"] = su.maintenant()
        return _resume_fonc(f)


MAX_LIVRABLES_FIN = 10


def _fin_verifiee(fin):
    """La fin d'une fonctionnalité : `livrables` [{chemin, titre}] (10 au plus), `acces` {url http(s), description?}
    facultatif, `laisses` (les noms des éléments laissés de côté) facultatif."""
    if not isinstance(fin, dict):
        raise Refus("« fin » est un objet {livrables, acces?, laisses?}.")
    livrables = fin.get("livrables", [])
    if (not isinstance(livrables, list) or len(livrables) > MAX_LIVRABLES_FIN
            or not all(isinstance(x, dict) and isinstance(x.get("chemin"), str) and x["chemin"].strip()
                       and "\x00" not in x["chemin"] and isinstance(x.get("titre"), str) and x["titre"].strip()
                       for x in livrables)):
        raise Refus(f"« fin.livrables » : au plus {MAX_LIVRABLES_FIN} fichiers {{chemin, titre}}.")
    sortie = {"livrables": [{"chemin": x["chemin"].strip(), "titre": x["titre"].strip()[:200]} for x in livrables]}
    if fin.get("acces") is not None:
        if not rel.acces_ok(fin["acces"]):
            raise Refus("« fin.acces » est {url (http ou https), description? (200 caractères au plus)}.")
        sortie["acces"] = {k: v for k, v in fin["acces"].items() if k in ("url", "description") and v is not None}
    if fin.get("laisses") is not None:
        if not isinstance(fin["laisses"], list) or not all(isinstance(x, str) for x in fin["laisses"]):
            raise Refus("« fin.laisses » est une liste de noms d'éléments.")
        sortie["laisses"] = [x[:200] for x in fin["laisses"][:50]]
    return sortie


def cmd_message(ctx, e):
    auteur = texte(e, "auteur")
    if auteur != "utilisateur" and auteur not in ctx.cles_agents():
        raise Refus(f"Auteur inconnu : {auteur} (utilisateur ou un agent).")
    images = e.get("images")
    if images is not None:
        images = liste_d_images(images, "images")
        images_montrables(chemins_d_images(images), "images")
        if len(images) > MAX_IMAGES:
            raise Refus(f"Au plus {MAX_IMAGES} images par message.")
        if e.get("auteur") != "utilisateur":
            images = [ctx.image_rangee(x, e.get("fonctionnalite")) for x in images]
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
        if action == "verifier":
            return _noter_verification(s, e)
        if action == "completer":
            return _completer_validation(s, e)
        if action != "poser":
            raise Refus("« action » doit valoir poser, lever, verifier ou completer.")
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
                if e.get("description") is not None:      # la phrase proposée pour un genre nouveau
                    d["description"] = _phrase(e, "description")
                if e.get("fonctionnalite") is not None:   # la fonctionnalité qui attend le genre du projet
                    _fonc(s, e["fonctionnalite"])
                    d["fonctionnalite"] = e["fonctionnalite"]
            elif genre == "organisation":
                d["organisation"] = _organisation_decidee(ctx, e.get("organisation"))
            elif genre == "elargir_genre":
                if not isinstance(e.get("cible"), str) or not fa.MOTIF_GENRE.match(e["cible"]):
                    raise Refus("« elargir_genre » demande « cible » (identifiant du genre à décrire).")
                d.update(cible=e["cible"], ancienne=_phrase(e, "ancienne"), propose=_phrase(e, "propose"))
                if e.get("fonctionnalite") is not None:
                    _fonc(s, e["fonctionnalite"])
                    d["fonctionnalite"] = e["fonctionnalite"]
            elif genre == "valider_etape":
                d.update(_validation_decidee(ctx, s, e))
            elif genre == "environnement":      # l'installation portée par le projet (sans fonctionnalité)
                d["environnement"] = _outils_qui_manquent(e)
            elif genre == "outil_agent":
                d.update(_outil_a_ouvrir(ctx, s, e))
            elif genre == "accord_agent":
                d.update(_accord_a_donner(ctx, s, e))
            elif genre == "faire_chez_partenaire":      # l'utilisateur fait la génération chez le partenaire où il est inscrit
                d.update(_chez_partenaire_a_faire(ctx, s, e))
            elif genre == "serie_arretee":      # une série qui ne progresse plus : dite au Directeur
                _fonc(s, e.get("fonctionnalite"))
                d["fonctionnalite"] = e["fonctionnalite"]
            elif genre == "fable_tache":        # « cette tâche demande Fable : l'autoriser ? » (sans accord : Opus)
                if su.tache(s, e.get("tache")) is None:
                    raise Refus(f"« fable_tache » : tâche inconnue « {e.get('tache')} ».")
                d.update(tache=e["tache"], raison=texte(e, "raison")[:300])
            else:
                if e.get("agent") not in ctx.cles_agents():
                    raise Refus(f"« session_cloud » : agent inconnu « {e.get('agent')} ».")
                d["agent"] = e["agent"]
                d.update(_session_a_creer(s, e))
            liste = s["decisions_projet"]
        else:
            if genre not in rel.DECISIONS_FONCTIONNALITE:
                raise Refus(f"Décision d'une fonctionnalité : genre inconnu « {genre} » "
                            f"({', '.join(rel.DECISIONS_FONCTIONNALITE)}).")
            d = {"genre": genre, "texte": contenu}
            if genre == "genre_fonctionnalite":
                d.update(_genre_fonctionnalite_decide(ctx, e))
            elif genre == "environnement":
                d["environnement"] = _outils_qui_manquent(e)
            liste = _fonc(s, portee)["decisions"]
        existante = next((x for x in liste if {k: v for k, v in x.items() if k != "id"} == d), None)
        if existante:   # poser deux fois la même décision n'en crée qu'une
            return {"id": existante["id"]}
        d = {"id": f"d{su.suivant(s, 'd')}", **d}
        liste.append(d)
        return {"id": d["id"]}


def _session_a_creer(s, e):
    """La démarche manuelle d'une décision `session_cloud` (facultative) : `tache` (connue) dont le `depart` (le message
    de départ complet) est à coller dans une session créée sur `lien` (claude.ai/code), sur le dépôt `depot`, au
    `modele` de l'agent."""
    d = {}
    if e.get("tache") is not None:
        if su.tache(s, e["tache"]) is None:
            raise Refus(f"« session_cloud » : tâche inconnue « {e['tache']} ».")
        d["tache"] = e["tache"]
    for champ, maxi in (("depart", 24000), ("modele", 40)):
        if e.get(champ) is not None:
            if not isinstance(e[champ], str) or not e[champ].strip() or len(e[champ]) > maxi:
                raise Refus(f"« session_cloud » : « {champ} » est un texte de {maxi} caractères au plus.")
            d[champ] = e[champ]
    for champ in ("lien", "depot"):
        if e.get(champ) is not None:
            if not isinstance(e[champ], str) or not e[champ].startswith("https://") or len(e[champ]) > 500:
                raise Refus(f"« session_cloud » : « {champ} » est une adresse https.")
            d[champ] = e[champ]
    return d


def _noter_verification(s, e):
    """`{"action": "verifier", "id": décision, "outils": [{outil, etat, verification, …}]}` : note, dans une décision
    `environnement`, le résultat de la dernière vérification de chaque outil nommé (`etat`, `verification` {trouve, cherche,
    introuvables, version_demandee, version_trouvee}, `chemin`, `version`, `raison`, `declare`, `note`) et l'heure
    (`verifie_le`). Les outils non nommés sont gardés tels quels ; un outil absent de la liste est refusé."""
    i, outils = texte(e, "id"), e.get("outils")
    if (not isinstance(outils, list) or not outils
            or not all(isinstance(x, dict) and isinstance(x.get("outil"), str) and x.get("etat") in ("en_place", "a_installer")
                       for x in outils)):
        raise Refus("« outils » est la liste des outils vérifiés {outil, etat: en_place | a_installer, verification?, …}.")
    for liste in [f["decisions"] for f in s["fonctionnalites"]] + [s["decisions_projet"]]:
        for d in liste:
            if d["id"] != i:
                continue
            if d.get("genre") != "environnement":
                raise Refus(f"La décision {i} n'est pas une décision « environnement ».")
            par_nom = {x["outil"]: x for x in outils}
            inconnus = [n for n in par_nom if n not in {o.get("outil") for o in d.get("environnement") or []}]
            if inconnus:
                raise Refus(f"« {inconnus[0]} » n'est pas dans cette décision.")
            neuf = []
            for o in d["environnement"]:
                if o.get("outil") in par_nom:
                    gardes = {k: v for k, v in o.items() if k not in ("verification", "raison", "refuses", "introuvables",
                                                                      "chemin", "version", "declare", "note")}
                    o = {**gardes, **{k: v for k, v in par_nom[o["outil"]].items()
                                      if k in ("etat", "verification", "raison", "refuses", "introuvables", "chemin",
                                               "version", "declare", "note")}}
                neuf.append(o)
            d["environnement"], d["verifie_le"] = neuf, su.maintenant()
            return {"ok": True}
    raise Refus(f"Décision inconnue : {i}")


def _outil_a_ouvrir(ctx, s, e):
    """Les champs de la décision `outil_agent` : l'agent arrêté faute d'outil, sa tâche, l'outil que sa fiche ne lui ouvre
    pas, et, si le moteur a pu le tirer de la commande refusée, le `programme` à ouvrir et la `commande` (coupée)."""
    if e.get("agent") not in ctx.cles_agents():
        raise Refus(f"« outil_agent » : agent inconnu « {e.get('agent')} ».")
    tache = texte(e, "tache")
    if su.tache(s, tache) is None:
        raise Refus(f"« outil_agent » : tâche inconnue « {tache} ».")
    d = {"agent": e["agent"], "tache": tache, "outil": _phrase_courte(e, "outil", 100)}
    if e.get("programme") is not None:
        if not isinstance(e["programme"], str) or not fi.MOTIF_PROGRAMME.match(e["programme"]):
            raise Refus("« programme » est un nom de programme (lettres, chiffres, point, tiret).")
        d["programme"] = e["programme"]
    if e.get("commande") is not None:
        d["commande"] = _phrase_courte(e, "commande", 300)
    return d


def _accord_a_donner(ctx, s, e):
    """Les champs de la décision `accord_agent` : l'agent arrêté, sa tâche, `quoi` (ce qu'il veut faire), et facultatifs
    `partenaire`, `cout`, `pourquoi`, `implique` (fenêtres, branchement, coût), `regle` (rappel d'une règle du projet) et
    `appareil` (vrai : une installation ou un test sur l'appareil physique de l'utilisateur)."""
    if e.get("agent") not in ctx.cles_agents():
        raise Refus(f"« accord_agent » : agent inconnu « {e.get('agent')} ».")
    tache = texte(e, "tache")
    if su.tache(s, tache) is None:
        raise Refus(f"« accord_agent » : tâche inconnue « {tache} ».")
    d = {"agent": e["agent"], "tache": tache, "quoi": _phrase_courte(e, "quoi", 600)}
    for cle, maximum in (("partenaire", 200), ("cout", 200), ("pourquoi", 800), ("implique", 800), ("regle", 400)):
        if e.get(cle) is not None:
            d[cle] = _phrase_courte(e, cle, maximum)
    if e.get("choix") is not None:      # les choix proposés par l'agent : des boutons au bureau
        c = e["choix"]
        if not isinstance(c, list) or not 1 <= len(c) <= 6 or not all(isinstance(x, str) and x.strip() and len(x) <= 120 for x in c):
            raise Refus("« choix » est une liste de 1 à 6 textes de 120 caractères au plus.")
        d["choix"] = c
    if e.get("regle_proposee") is not None:      # la règle que la case « Retenir comme règle du projet » propose
        d["regle_proposee"] = _phrase_courte(e, "regle_proposee", rp.MAX_TEXTE)
    touchees = e.get("regles_touchees")
    if touchees is not None:     # les règles du projet que la demande touche : [{id, texte}]
        if (not isinstance(touchees, list) or len(touchees) > rp.MAX_TOUCHEES
                or not all(isinstance(x, dict) and isinstance(x.get("id"), str) and isinstance(x.get("texte"), str)
                           and x["texte"].strip() and len(x["texte"]) <= rp.MAX_TEXTE for x in touchees)):
            raise Refus(f"« regles_touchees » est une liste de {rp.MAX_TOUCHEES} règles {{id, texte}} au plus.")
        d["regles_touchees"] = [{"id": x["id"], "texte": x["texte"]} for x in touchees]
    if e.get("appareil") is not None:
        if not isinstance(e["appareil"], bool):
            raise Refus("« appareil » est vrai ou faux.")
        d["appareil"] = e["appareil"]
    return d


PROMPT_PARTENAIRE_MAX = 4000   # le plafond général ; certains partenaires en ont un plus bas (`partenaires.etat.PROMPT_MAX`)
MAX_REGLAGES, MAX_ETAPES_CHEZ, MAX_ELEMENTS_CHEZ = 12, 10, 12


def _liste_chez(e, cle, maximum, longueur, minimum=0):
    v = e.get(cle, [])
    if (not isinstance(v, list) or not minimum <= len(v) <= maximum
            or not all(isinstance(x, str) and x.strip() and len(x) <= longueur for x in v)):
        raise Refus(f"« {cle} » est une liste de {minimum} à {maximum} textes de {longueur} caractères au plus.")
    return [x.strip() for x in v]


def _chez_partenaire_a_faire(ctx, s, e):
    """Les champs de la décision `faire_chez_partenaire` (« À faire chez <partenaire> ») : un agent prépare ce que l'utilisateur
    fait lui-même sur le site d'un partenaire où il est inscrit, sans liaison directe. `agent`, `tache`, `partenaire` (du
    catalogue), `quoi`, `prompt` (prêt à copier ; le plafond du partenaire est tenu : 1 000 caractères chez Tripo),
    `reglages` (chacun des réglages du partenaire ; obligatoires chez Tripo), `mode_operatoire` (où cliquer), `a_rapporter`
    `{description, nom?}`, `elements` (ce que groupe le prompt). Une génération à la fois chez un partenaire : une demande
    posée alors qu'une autre attend vient `apres` elle. Le site vient du catalogue, jamais de l'agent."""
    if e.get("agent") not in ctx.cles_agents():
        raise Refus(f"« faire_chez_partenaire » : agent inconnu « {e.get('agent')} ».")
    tache = texte(e, "tache")
    if su.tache(s, tache) is None:
        raise Refus(f"« faire_chez_partenaire » : tâche inconnue « {tache} ».")
    par_id = {p["id"]: p for p in _catalogue(ctx)["partenaires"]}
    i = _partenaire(e, par_id)
    p = par_id[i]
    if p.get("statut") == "ferme":
        raise Refus(f"{p['nom']} est fermé : choisis un autre partenaire ou une autre voie.")
    prompt = _phrase_courte(e, "prompt", PROMPT_PARTENAIRE_MAX).strip()
    plafond = petat.PROMPT_MAX.get(i)
    if plafond and len(prompt) > plafond:
        raise Refus(f"Le prompt pour {p['nom']} tient en {plafond} caractères au plus (le tien en a {len(prompt)}) : "
                    "raccourcis-le, ou groupe moins d'éléments.")
    reglages = _liste_chez(e, "reglages", MAX_REGLAGES, 200, 1 if i in petat.REGLAGES_OBLIGATOIRES else 0)
    a_rapporter = e.get("a_rapporter")
    if (not isinstance(a_rapporter, dict) or not isinstance(a_rapporter.get("description"), str)
            or not a_rapporter["description"].strip() or len(a_rapporter["description"]) > 300
            or (a_rapporter.get("nom") is not None and not (isinstance(a_rapporter["nom"], str)
                                                            and a_rapporter["nom"].strip() and len(a_rapporter["nom"]) <= 80))):
        raise Refus("« a_rapporter » est {description (300 caractères au plus), nom? (80 au plus)} : ce que l'utilisateur "
                    "rapporte, et le nom attendu.")
    quoi = _phrase_courte(e, "quoi", 600).strip()
    d = {"texte": f"À faire chez {p['nom']} : {quoi}"[:200], "agent": e["agent"], "tache": tache, "partenaire": i,
         "nom_partenaire": p["nom"], "quoi": quoi, "prompt": prompt, "reglages": reglages,
         "mode_operatoire": _liste_chez(e, "mode_operatoire", MAX_ETAPES_CHEZ, 300, 1),
         "a_rapporter": {k: a_rapporter[k].strip() for k in ("description", "nom") if a_rapporter.get(k)}}
    if e.get("elements") is not None:
        d["elements"] = _liste_chez(e, "elements", MAX_ELEMENTS_CHEZ, 80)
    if isinstance(p.get("site"), str) and p["site"].startswith("https://"):
        d["site"] = p["site"]
    attente = [x for x in s["decisions_projet"] if x.get("genre") == "faire_chez_partenaire" and x.get("partenaire") == i]
    deja = next((x for x in attente if {k: v for k, v in x.items() if k not in ("id", "apres", "genre")} == d), None)
    if deja is not None:        # la même demande reposée : la même décision (avec sa place dans la file)
        if "apres" in deja:
            d["apres"] = deja["apres"]
    elif attente:
        d["apres"] = attente[-1]["id"]      # une génération à la fois chez ce partenaire
    return d


def _phrase_courte(e, cle, maximum):
    v = texte(e, cle)
    if len(v) > maximum:
        raise Refus(f"« {cle} » est un texte de {maximum} caractères au plus.")
    return v


def _outils_qui_manquent(e):
    """La liste des outils d'une décision `environnement` : `[{outil, installation, …}]`, jamais vide."""
    outils = e.get("environnement")
    if (not isinstance(outils, list) or not outils
            or not all(isinstance(x, dict) and isinstance(x.get("outil"), str) and x["outil"].strip()
                       for x in outils)):
        raise Refus("« environnement » demande la liste des outils qui manquent ({outil, installation, …}).")
    return [dict(x) for x in outils]


def _dit_de_la_validation(e, cle_points="points"):
    """Ce que dit une demande de validation, validé comme à la pose : `doit_marcher`, `pas_encore` (peut être vide),
    `conclusion` et les points à vérifier (sous `cle_points`, ou `points_a_verifier` à la complétion). Rien d'autre."""
    plus = {}
    for c, m, vide in rel.CHAMPS_DIT:
        v = e.get(c)
        if v is not None:
            if not rel.texte_dit_ok(v, m, vide):
                raise Refus(f"« {c} » est un texte de {m} caractères au plus{'' if vide else ', non vide'}.")
            plus[c] = " ".join(v.split())
    points = e.get(cle_points) if e.get(cle_points) is not None else e.get("points_a_verifier")
    if points is not None:
        if not rel.points_ok(points):
            raise Refus(f"« points » : 1 à {rel.MAX_POINTS} phrases différentes de {rel.MAX_POINT} caractères au plus.")
        plus["points"] = [p.strip() for p in points]
    if e.get("nature") is not None:      # ce que le Directeur valide : en_jeu, visuel, son, mecanique ou autre
        if not rel.nature_ok(e["nature"]):
            raise Refus(f"« nature » vaut {', '.join(rel.NATURES)}.")
        plus["nature"] = e["nature"]
    if e.get("mode_operatoire") is not None:      # les étapes à suivre pour essayer le livrable en jeu
        if not rel.mode_operatoire_ok(e["mode_operatoire"]):
            raise Refus(f"« mode_operatoire » : {rel.MIN_ETAPES_MODE} à {rel.MAX_ETAPES_MODE} étapes courtes "
                        f"({rel.MAX_ETAPE_MODE} caractères au plus chacune).")
        plus["mode_operatoire"] = rel.mode_operatoire_propre(e["mode_operatoire"])
    return plus


def _completer_validation(s, e):
    """`{"action": "completer", "id": décision, "doit_marcher"?, "pas_encore"?, "conclusion"?, "points_a_verifier"?,
    "nature"?, "mode_operatoire"?, "fichiers"?}` :
    complète une décision `valider_etape` encore posée avec ce que dit une validation (les mêmes contrôles qu'à la pose).
    Ne touche à rien d'autre ; refuse une décision levée ou d'un autre genre."""
    i = texte(e, "id")
    plus = _dit_de_la_validation(e)
    if "fichiers" in e:      # ce qu'il y a à vérifier, remplacé (ex. les images d'un style au lieu d'un apk)
        fichiers = e["fichiers"]
        if (not isinstance(fichiers, list) or not fichiers
                or not all(isinstance(x, dict) and isinstance(x.get("chemin"), str) and x["chemin"].strip()
                           and isinstance(x.get("titre"), str) and x["titre"].strip() and len(x["titre"]) <= 200
                           for x in fichiers)):
            raise Refus("« fichiers » est une liste non vide de {chemin, titre}.")
        plus["fichiers"] = [{"chemin": x["chemin"].strip(), "titre": x["titre"].strip()} for x in fichiers]
    if not plus:
        raise Refus("« completer » demande au moins « doit_marcher », « pas_encore », « conclusion », "
                    "« points_a_verifier », « nature », « mode_operatoire » ou « fichiers ».")
    for d in s["decisions_projet"] + [x for f in s["fonctionnalites"] for x in f["decisions"]]:
        if d["id"] == i:
            if d.get("genre") != "valider_etape":
                raise Refus(f"La décision {i} n'est pas une décision « valider_etape ».")
            d.update(plus)
            return {"ok": True}
    raise Refus(f"Décision inconnue : {i} (levée ou jamais posée).")


def _validation_decidee(ctx, s, e):
    """Les champs de la décision `valider_etape` : l'élément qui attend le Directeur, l'étape de validation, la tâche qui
    la porte, le compte rendu de l'étape précédente et ses fichiers."""
    fid = e.get("fonctionnalite")
    _fonc(s, fid)
    element = e.get("element")
    if not (isinstance(element, dict) and isinstance(element.get("id"), str) and element["id"].strip()
            and isinstance(element.get("nom"), str) and element["nom"].strip()):
        raise Refus("« valider_etape » demande « element » {id, nom}.")
    if e.get("etape") not in ctx.colonnes():
        raise Refus(f"« valider_etape » : étape inconnue « {e.get('etape')} ».")
    tache = texte(e, "tache")
    if su.tache(s, tache) is None:
        raise Refus(f"« valider_etape » : tâche inconnue « {tache} ».")
    compte_rendu = e.get("compte_rendu", "")
    fichiers = e.get("fichiers", [])
    if not isinstance(compte_rendu, str) or len(compte_rendu) > 2000:
        raise Refus("« compte_rendu » est un texte de 2000 caractères au plus.")
    if (not isinstance(fichiers, list) or not all(isinstance(x, dict) and isinstance(x.get("chemin"), str)
                                                  and x["chemin"].strip() and isinstance(x.get("titre"), str)
                                                  and x["titre"].strip() for x in fichiers)):
        raise Refus("« fichiers » est une liste de {chemin, titre}.")
    plus = {}
    for cle in ("objectif", "a_valider"):     # ce que l'élément devait produire, ce qu'il y a à valider (une phrase)
        v = e.get(cle)
        if v is not None:
            if not isinstance(v, str) or len(v) > 600:
                raise Refus(f"« {cle} » est un texte de 600 caractères au plus.")
            plus[cle] = v
    plus.update(_dit_de_la_validation(e))     # les points à vérifier et les trois choses que dit la validation
    if e.get("acces") is not None:        # le lien d'accès d'un site qui tourne
        if not rel.acces_ok(e["acces"]):
            raise Refus("« acces » est {url (http ou https), description? (200 caractères au plus)}.")
        plus["acces"] = {k: v for k, v in e["acces"].items() if v is not None}
    return {"fonctionnalite": fid, "element": {"id": element["id"], "nom": element["nom"]}, "etape": e["etape"],
            "tache": tache, "compte_rendu": compte_rendu, **plus,
            "fichiers": [_fichier_a_valider(ctx, x, fid) for x in fichiers]}


def _fichier_a_valider(ctx, x, fid):
    """Un fichier de la décision `valider_etape` : une image est rangée là où le bureau la sert ; un livrable
    téléchargeable trouvé dans le projet reçoit sa `taille` (octets) et sa `date` (modification), et son chemin compté
    depuis la factory (ou, hors de `.factory`, depuis le dossier du projet), ce que la route de téléchargement attend."""
    chemin = x["chemin"]
    if rel.est_image(chemin):
        return {"chemin": ctx.image_rangee(chemin, fid), "titre": x["titre"]}
    sortie = {"chemin": chemin, "titre": x["titre"]}
    if rel.est_telechargeable(chemin):
        base = Path(ctx.f["base"]).resolve()
        projet = base.parent if base.name == ".factory" else base     # comme le moteur et le bureau
        trouve = fichier_du_projet(ctx.f, projet, chemin)
        if trouve is not None:
            sortie["chemin"] = (trouve.relative_to(base) if _sous(trouve, base) else trouve.relative_to(projet)).as_posix()
            stat = trouve.stat()
            sortie["taille"] = stat.st_size
            sortie["date"] = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
    return sortie


def fichier_du_projet(f, dossier_projet, chemin):
    """Le fichier (résolu) que cite un agent, s'il existe DANS le dossier du projet : cherché depuis la factory, les
    réglages, puis le dossier du projet (comme `image_rangee`). `None` sinon : absent, hors du projet (lien compris),
    « .. », caractère nul ou dans `.git`."""
    if not isinstance(chemin, str) or not chemin.strip() or "\x00" in chemin:
        return None
    p = Path(chemin.replace("\\", "/"))
    if ".." in p.parts:
        return None
    projet = Path(dossier_projet).resolve()
    base = racines_servies(f)[0]
    try:
        for c in ([p] if p.is_absolute() else [f["base"] / p, base / p, projet / p]):
            r = c.resolve()
            if r.is_file() and _sous(r, projet) and ".git" not in r.relative_to(projet).parts:
                return r
    except (OSError, ValueError):
        return None
    return None


def _phrase(e, cle):
    v = e.get(cle)
    if not isinstance(v, str) or not v.strip():
        raise Refus(f"« {cle} » demande un texte.")
    return " ".join(v.split())


def _genre_fonctionnalite_decide(ctx, e):
    """Les champs de la décision `genre_fonctionnalite` : le genre proposé, le nouveau genre éventuel (`{id,
    description}`), si le moteur hésite, et les genres connus entre lesquels choisir."""
    connus = e.get("genres_connus", genres_connus(ctx))
    nouveau = e.get("nouveau")
    if (not isinstance(e.get("propose"), str) or not fa.MOTIF_GENRE.match(e["propose"])
            or not isinstance(connus, list) or not all(isinstance(g, str) and fa.MOTIF_GENRE.match(g) for g in connus)
            or not isinstance(e.get("incertain", False), bool)):
        raise Refus("« genre_fonctionnalite » demande « propose » et « genres_connus » (identifiants de genre) "
                    "et « incertain » (vrai ou faux).")
    sortie = {"propose": e["propose"], "genres_connus": list(connus), "incertain": bool(e.get("incertain", False))}
    if e.get("elargissement") is not None:      # la description du genre du projet, élargie à cette demande
        sortie["elargissement"] = _phrase(e, "elargissement")
    if nouveau is not None:
        if (not isinstance(nouveau, dict) or not isinstance(nouveau.get("id"), str)
                or not fa.MOTIF_GENRE.match(nouveau["id"]) or not isinstance(nouveau.get("description"), str)
                or not nouveau["description"].strip()):
            raise Refus("« nouveau » demande {id (identifiant de genre), description}.")
        sortie["nouveau"] = {"id": nouveau["id"], "description": nouveau["description"].strip()}
    return sortie


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
    equipe = [x for x in existantes if x["role"] != "chef"]
    if proposition.est_polyvalente(o.get("agents"), o.get("metiers")):      # le nouveau format : des métiers
        erreurs = proposition.verifier_organisation(
            o.get("services"), o.get("flux"), o.get("agents"), None, cloud=True, briefs_existants=briefs_existants,
            metiers=o.get("metiers"), equipe_en_place=bool(equipe))
        if any(x["role"] for x in equipe):
            erreurs.append("Ce projet a encore des agents par rôle : proposez des agents et des briefs à l'ancienne "
                           "(ou passez d'abord aux agents polyvalents).")
        return erreurs
    erreurs = proposition.verifier_organisation(
        o.get("services"), o.get("flux"), o.get("agents"), o.get("briefs"), cloud=True,
        roles_deja_pourvus={x["role"] for x in existantes}, cles_prises={x["cle"] for x in existantes},
        briefs_existants=briefs_existants)
    if o.get("agents") and any(fi.est_polyvalente(x) for x in equipe):
        erreurs.append("Ce projet a des agents polyvalents : proposez des métiers, pas des agents par rôle.")
    return erreurs


def proposition_polyvalente(o):
    """Vrai pour une organisation du nouveau format (des `metiers`, et le nombre d'agents)."""
    from installation import proposition
    return proposition.est_polyvalente(o.get("agents"), o.get("metiers"))


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
    decidee = {"services": [dict(x) for x in o["services"]], "flux": [dict(x) for x in o["flux"]],
               "cout": {"tokens": list(cout["tokens"]), "euros": None if cout.get("euros") is None
                        else list(cout["euros"])}}
    if proposition_polyvalente(o):
        decidee["metiers"] = [dict(x) for x in o["metiers"]]
        if o.get("agents") is not None:
            decidee["agents"] = dict(o["agents"])
    else:
        decidee.update(agents=[dict(x) for x in o["agents"]], briefs=dict(o["briefs"]))
    if "workflow" in o or "fonctionnalite" in o:
        decidee.update(_workflow_decide(ctx, o))
    return decidee


def _workflow_decide(ctx, o):
    """Ce qu'une décision `organisation` porte de plus quand elle propose le workflow d'une fonctionnalité : la
    fonctionnalité, son workflow `{id, genre, flux, genre_nouveau?}` (le flux est celui de l'organisation), le livrable,
    l'environnement du poste et les règles d'outils d'installation."""
    fid, w = o.get("fonctionnalite"), o.get("workflow")
    if not isinstance(fid, str) or su.fonctionnalite(ctx.suivi.lire(), fid) is None:
        raise Refus(f"Organisation refusée : fonctionnalité inconnue « {fid} ».")
    if not isinstance(w, dict) or not isinstance(w.get("id"), str) or not fa.MOTIF_ID.match(w["id"]):
        raise Refus("Organisation refusée : « workflow » demande {id, genre, flux}.")
    if w["id"] in {x["id"] for x in wf.tous(ctx.f)}:
        raise Refus(f"Organisation refusée : le workflow « {w['id']} » existe déjà.")
    if w.get("genre") is not None and not (isinstance(w["genre"], str) and fa.MOTIF_GENRE.match(w["genre"])):
        raise Refus("Organisation refusée : le genre du workflow est nul ou un identifiant de genre.")
    if w.get("flux") != o["flux"]:
        raise Refus("Organisation refusée : le flux du workflow est celui de l'organisation.")
    pris = set(wf.ids_etapes(ctx.f))
    doubles = [x["id"] for x in o["flux"] if x["id"] in pris]
    if doubles:
        raise Refus(f"Organisation refusée : étape déjà prise dans le projet : {', '.join(doubles)}.")
    workflow = {"id": w["id"], "genre": w.get("genre"), "flux": [dict(x) for x in w["flux"]]}
    nouveau = w.get("genre_nouveau")
    if nouveau is not None:
        if not (isinstance(nouveau, dict) and isinstance(nouveau.get("description"), str) and nouveau["description"].strip()):
            raise Refus("Organisation refusée : « genre_nouveau » demande une « description ».")
        workflow["genre_nouveau"] = {"description": nouveau["description"].strip()}
    env, regles = o.get("environnement", []), o.get("outils_installation", [])
    if not isinstance(env, list) or not all(isinstance(x, dict) for x in env):
        raise Refus("Organisation refusée : « environnement » est une liste d'outils.")
    if not isinstance(regles, list) or not all(isinstance(x, str) and x.strip() for x in regles):
        raise Refus("Organisation refusée : « outils_installation » est une liste de règles d'outils.")
    for a in o["agents"] if isinstance(o.get("agents"), list) else []:
        if "fable_suggere" in a and not isinstance(a["fable_suggere"], bool):
            raise Refus(f"Organisation refusée : « fable_suggere » de l'agent « {a.get('cle')} » vaut vrai ou faux.")
    livrable = o.get("livrable")
    if livrable is not None and not isinstance(livrable, str):
        raise Refus("Organisation refusée : « livrable » est un texte.")
    return {"fonctionnalite": fid, "workflow": workflow, "livrable": livrable,
            "environnement": [dict(x) for x in env], "outils_installation": list(regles)}


def _ouvrir_les_outils_d_installation(ctx, regles):
    """Les règles d'outils proposées avec le workflow (et validées avec lui) s'ajoutent à la ligne « Outils : » de la
    fiche de l'agent d'environnement, celui qui installe ce qui manque ; rien ne s'ouvre à un autre agent."""
    agent = next((a for a in ctx.fiches() if a["role"] == "environnement"), None)
    if agent is None:      # un projet d'agents polyvalents : les règles vont au métier « environnement »
        try:
            metier = metiers.lire_metier(ctx.f["fiches"] / "briefs", "environnement")
        except (metiers.MetierInvalide, OSError):
            return
        if metier is not None:
            actuelles = fi.outils({"outils": metier["outils"]})
            metier["outils"] = ", ".join(actuelles + [r for r in dict.fromkeys(regles) if r not in actuelles])
            metiers.ecrire_metier(metier)
        return
    actuelles = fi.outils(agent)
    agent["outils"] = ", ".join(actuelles + [r for r in dict.fromkeys(regles) if r not in actuelles])
    fi.ecrire_fiche(agent)


def _noter_environnement(ctx, e):
    """`{"action": "environnement", "outils": [{outil, etat, chemin?, version?, …}]}` : note l'état des outils du poste
    dans le fichier de factory (un outil de même nom est remplacé, les autres sont gardés)."""
    from installation import mise_en_place
    outils = e.get("outils")
    if (not isinstance(outils, list) or not outils
            or not all(isinstance(x, dict) and isinstance(x.get("outil"), str) and x["outil"].strip()
                       and x.get("etat") in ("en_place", "a_installer") for x in outils)):
        raise Refus("« outils » est la liste des outils du poste {outil, etat: en_place | a_installer, …}.")
    with ctx.suivi.transaction():   # le même verrou que le suivi : un seul écrivain du fichier de factory
        brut = json.loads(ctx.f["chemin"].read_text(encoding="utf-8-sig"))
        brut["environnement"] = mise_en_place.fusionner_environnement(brut.get("environnement"), outils)
        mise_en_place._ecrire_json(ctx.f["chemin"], brut)
    return {"ok": True, "environnement": brut["environnement"]}


def _recruter_l_installateur(ctx, e):
    """`{"action": "installateur", "agent": {cle, role: environnement, service, modele, lieu, texte, outils?}, "brief"}` :
    recrute l'agent qui installe les outils du poste quand le projet n'en a pas (rien à faire s'il existe). Seul ce rôle
    peut être recruté ainsi, jamais sur Fable."""
    from installation.dossier import Echec
    from installation import mise_en_place
    a, brief = e.get("agent"), e.get("brief")
    if not (isinstance(a, dict) and a.get("role") == "environnement" and isinstance(brief, str) and brief.strip()
            and all(isinstance(a.get(c), str) and a[c].strip() for c in ("cle", "service", "modele", "texte"))
            and a.get("lieu") in ("local", "cloud")):
        raise Refus("« installateur » demande « agent » (rôle environnement : cle, service, modele, lieu, texte) et « brief ».")
    if _interdit(a["modele"]):
        raise Refus("Fable n'est jamais choisi par un outil.")
    if any(x["role"] == "environnement" for x in ctx.fiches()):
        return {"ok": True, "deja": True}
    if any(fi.est_polyvalente(x) for x in ctx.fiches()):      # agents polyvalents : un métier, pas un agent de plus
        chemin = ctx.f["fiches"] / "briefs" / "environnement.md"
        if chemin.exists():
            return {"ok": True, "deja": True}
        metiers.ecrire_metier({"role": "environnement", "service": a["service"], "modele": a["modele"],
                               "lieu": "indifférent", "specialite": a.get("specialite"), "outils": a.get("outils"),
                               "texte": brief.strip(), "lecons": [], "chemin": chemin})
        return {"ok": True, "deja": False, "metier": "environnement"}
    try:
        mise_en_place.ajouter_agent(ctx.f["chemin"], a, brief)
    except Echec as ex:
        raise Refus(str(ex))
    return {"ok": True, "deja": False, "agent": a["cle"]}


def _reprendre_le_workflow_de_creation(ctx, e):
    """`{"action": "reprendre", "fonctionnalite", "workflow"}` : la fonctionnalité suit le workflow de genre du projet
    (défini à la création) : sa copie `w-<fid>` est ajoutée sans service, agent ni brief nouveau, sans décision."""
    from installation.dossier import Echec
    from installation import mise_en_place
    fid, voulu = texte(e, "fonctionnalite"), texte(e, "workflow")
    with ctx.suivi.transaction() as s:
        fonc = su.fonctionnalite(s, fid)
        if fonc is None:
            raise Refus(f"Fonctionnalité inconnue : {fid}")
        if fonc.get("workflow"):
            raise Refus(f"La fonctionnalité {fid} a déjà un workflow ({fonc['workflow']}).")
        w = next((x for x in wf.tous(ctx.f) if x["id"] == voulu and x["fonctionnalite"] is None
                  and x["id"] != wf.PRINCIPAL), None)
        if w is None:
            raise Refus(f"« {voulu} » n'est pas un workflow de genre du projet.")
        copie = wf.copie_pour(w, fid)
        try:
            mise_en_place.ecrire_organisation(
                ctx.f["chemin"], [dict(x) for x in ctx.f["services"]], copie["flux"], [], {}, workflow=copie)
        except Echec as ex:
            raise Refus(str(ex))
        fonc["genre"], fonc["workflow"], fonc["maj"] = copie["genre"], copie["id"], su.maintenant()
    return {"ok": True, "workflow": copie["id"]}


def cmd_organisation(ctx, e):
    """Applique une décision `organisation` acceptée : services, flux (ou workflow d'une fonctionnalité), fiches et
    briefs, puis lève la décision. `fable` : les clés des agents que le Directeur a cochés pour Fable (parmi ceux dont la
    proposition le suggérait) ; leur fiche porte alors l'accord."""
    from installation.dossier import Echec
    from installation import mise_en_place
    if e.get("action") == "environnement":
        return _noter_environnement(ctx, e)
    if e.get("action") == "reprendre":
        return _reprendre_le_workflow_de_creation(ctx, e)
    if e.get("action") == "installateur":
        return _recruter_l_installateur(ctx, e)
    if e.get("action") != "appliquer":
        raise Refus("« action » doit valoir appliquer (ou environnement, reprendre ou installateur).")
    i = texte(e, "decision")
    fable = e.get("fable", [])
    if not isinstance(fable, list) or not all(isinstance(x, str) and x for x in fable):
        raise Refus("« fable » est la liste des clés d'agents que le Directeur autorise sur Fable.")
    genre_a_creer = None
    with ctx.suivi.transaction() as s:
        d = next((x for x in s["decisions_projet"] if x["id"] == i and x.get("genre") == "organisation"), None)
        if d is None:
            raise Refus(f"Décision d'organisation inconnue : {i}")
        o = d["organisation"]
        if proposition_polyvalente(o):
            if fable:
                raise Refus("Fable ne se coche plus par agent : il se demande tâche par tâche, avec l'accord du Directeur.")
            agents, briefs, metiers_ = o.get("agents"), {}, o.get("metiers")
        else:
            try:
                agents = fi.accorder_fable(o["agents"], fable, su.maintenant()[:10])
            except ValueError as ex:
                raise Refus(str(ex))
            briefs, metiers_ = o["briefs"], None
        w = o.get("workflow")
        try:
            mise_en_place.ecrire_organisation(
                ctx.f["chemin"], o["services"], o["flux"], agents, briefs,
                workflow={**w, "fonctionnalite": o.get("fonctionnalite")} if w else None,
                environnement=o.get("environnement") if w and o.get("environnement") else None, metiers=metiers_)
        except Echec as ex:
            raise Refus(str(ex))
        if w and o.get("outils_installation") and any(x.get("etat") != "en_place" for x in o.get("environnement") or []):
            _ouvrir_les_outils_d_installation(ctx, o["outils_installation"])
        if w:
            fonc = su.fonctionnalite(s, o["fonctionnalite"])
            if fonc is not None:
                fonc["genre"], fonc["workflow"], fonc["maj"] = w.get("genre"), w["id"], su.maintenant()
            if w.get("genre_nouveau") and w.get("genre"):
                genre_a_creer = (w["genre"], w["genre_nouveau"]["description"])
        s["decisions_projet"].remove(d)
    sortie = {"ok": True, "services": o["services"], "flux": o["flux"]}
    if w:
        sortie.update(workflow=w["id"], fonctionnalite=o["fonctionnalite"], genre=w.get("genre"))
    if genre_a_creer and genre_a_creer[0] not in genres_connus(ctx):   # en dernier : il publie dans la mémoire de la skill
        ok, message = memoire.creer_genre(ctx.f["memoire"], genre_a_creer[0], genre_a_creer[1],
                                          ctx.f["mots_interdits"], git=GIT)
        sortie["genre_cree"] = ok
        if not ok:
            sortie["genre_raison"] = f"le genre « {genre_a_creer[0]} » n'a pas pu être créé : {message}"
    return sortie


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
                 "role": None, "colonne": None, "agent": None, "etape": "", "modele_depart": None,
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
        if t["colonne"] is None:   # une tâche neuve part de la première étape du workflow de sa fonctionnalité
            t["colonne"] = ctx.premiere_colonne(su.fonctionnalite(s, t["fonctionnalite"]) if t["fonctionnalite"] else None)
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
        if "fable_accordee" in e:   # la réponse du Directeur à « cette tâche demande Fable » : vrai, faux (Opus) ou rien
            if e["fable_accordee"] not in (True, False, None):
                raise Refus("« fable_accordee » vaut vrai, faux ou rien.")
            t["fable_accordee"] = e["fable_accordee"]
        if _interdit(t["modele_depart"]) and not _fable_accorde_pour(ctx, t):
            raise Refus("Fable n'est jamais choisi par un outil (seulement sur une fiche qui porte l'accord du "
                        "Directeur).")
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
                # un projet aux agents polyvalents peut monter d'Opus à Fable : une demande au Directeur, avant le départ
                vers_fable = (m["de"] == "Opus" and m["a"] == mn.FABLE
                              and any(fi.est_polyvalente(x) for x in ctx.fiches()))
                if (_interdit(m["a"]) and not vers_fable) or _interdit(m["de"]):
                    raise Refus("Fable n'est jamais choisi par un outil (seulement sur demande expresse).")
                if m["de"] in depart.ECHELLE and m["a"] != depart.monter(m["de"], fable=vers_fable):
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
            t["captures"] = liste_d_images(e["captures"], "captures")
            images_montrables(chemins_d_images(t["captures"]), "captures")
            t["captures"] = [ctx.image_rangee(x, t["fonctionnalite"]) for x in t["captures"]]
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
    chemin = original = texte(e, "chemin")
    if "\x00" not in chemin:
        chemin = ctx.image_rangee(chemin, e.get("fonctionnalite"))   # une image hors des racines est copiée dans les pièces
    if "\x00" in chemin or Path(chemin).is_absolute() or chemin[0] in "/\\":
        raise Refus("« chemin » doit être relatif au fichier de factory.")
    origine = {cle: texte(e, cle, obligatoire=False) for cle in ORIGINE_DOCUMENT}
    livrable = e.get("livrable")
    if livrable is not None and not isinstance(livrable, bool):
        raise Refus("« livrable » doit être vrai ou faux.")
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        if chemin != original:   # le même document, rangé : l'ancienne entrée prend le nouveau chemin (ou disparaît si déjà là)
            ancien = next((x for x in f.get("documents") or [] if x["chemin"] == original), None)
            if ancien is not None:
                cible = next((x for x in f["documents"] if x["chemin"] == chemin), None)
                if cible is not None:   # déjà inscrit sous le nouveau chemin : il garde ce que l'ancien disait de plus
                    for cle in (*ORIGINE_DOCUMENT, "livrable"):
                        if ancien.get(cle) and not cible.get(cle):
                            cible[cle] = ancien[cle]
                    f["documents"].remove(ancien)
                else:
                    ancien["chemin"] = chemin
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


def _relatif_a_la_base(ctx, chemin):
    try:
        return chemin.resolve().relative_to(ctx.f["base"]).as_posix()
    except ValueError:
        return str(chemin)


def cmd_ecrire(ctx, e):
    """Écrit un texte Markdown du projet : le document d'une fonctionnalité (sous ses pièces, rangé dans ses documents)
    ou le brief d'un rôle (`<fiches>/briefs/<rôle>.md` : un brief existant est gardé, le nouveau texte y est ajouté).
    C'est par là que le moteur écrit une méthode : aucun autre chemin, aucun fichier hors de ces deux dossiers."""
    contenu = texte(e, "texte")
    if "brief" in e:
        role = texte(e, "brief")
        if not depart._ROLE_SUR.match(role):
            raise Refus("« brief » doit être un nom de rôle (lettres, chiffres, - et _).")
        chemin = Path(ctx.f["fiches"]) / "briefs" / f"{role}.md"
        actuel = chemin.read_text(encoding="utf-8-sig").rstrip() if chemin.is_file() else ""
        if contenu.strip() in actuel:   # déjà là : écrire deux fois ne change rien
            return {"chemin": _relatif_a_la_base(ctx, chemin)}
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text((actuel + "\n\n" if actuel else "") + contenu.strip() + "\n", encoding="utf-8",
                          newline="\n")
        return {"chemin": _relatif_a_la_base(ctx, chemin)}
    nom = texte(e, "nom")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.md", nom) or ".." in nom:
        raise Refus("« nom » doit être un nom de fichier .md (lettres, chiffres, - _ .).")
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        chemin = Path(ctx.f["pieces"]) / f["id"] / nom
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu.strip() + "\n", encoding="utf-8", newline="\n")
        relatif = _relatif_a_la_base(ctx, chemin)
        if e.get("titre"):
            ranger_documents(s, f, [relatif], texte(e, "titre"), **{k: texte(e, k, obligatoire=False)
                                                                     for k in ORIGINE_DOCUMENT})
        f["maj"] = su.maintenant()
    return {"chemin": relatif}


# Un élément de la file : `objectif` (ce qu'il doit produire, rappelé à sa validation) et `validations` (les étapes de
# validation du Directeur qui le concernent ; absent : toutes) viennent du découpage.
CHAMPS_ELEMENT = ("id", "nom", "groupe", "objectif", "validations")


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
        if q.get("objectif") is not None and (not isinstance(q["objectif"], str) or len(q["objectif"]) > 300):
            raise Refus(f"File : « objectif » de « {q['id']} » : un texte de 300 caractères au plus.")
        if q.get("validations") is not None and not (isinstance(q["validations"], list)
                                                     and all(isinstance(v, str) and v for v in q["validations"])):
            raise Refus(f"File : « validations » de « {q['id']} » : une liste d'identifiants d'étapes.")
        vus.add(q["id"])
        propres.append({k: q[k] for k in CHAMPS_ELEMENT if q.get(k) is not None})
    with ctx.suivi.transaction() as s:
        f = _fonc(s, e.get("fonctionnalite"))
        f["file"] = propres
        for q in propres:
            f["elements"][q["id"]] = {k: q[k] for k in CHAMPS_ELEMENT[1:] if k in q}
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


def _abonnement_de(e):
    """L'instantané d'abonnement noté avec un usage (facultatif) : bien formé, ou ignoré (jamais un refus)."""
    ab = e.get("abonnement")
    if not isinstance(ab, dict):
        return None

    def nombre(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")

    sortie = {}
    for nom in ("five_hour", "seven_day"):
        f = ab.get(nom)
        if (isinstance(f, dict) and nombre(f.get("pourcent")) and 0 <= f["pourcent"] <= 100
                and nombre(f.get("remise")) and f["remise"] > 0):
            sortie[nom] = {"pourcent": round(float(f["pourcent"]), 1), "remise": int(f["remise"])}
    if not sortie or not nombre(ab.get("t")) or ab["t"] <= 0:
        return None
    sortie["t"] = int(ab["t"])
    return sortie


def _poser_abonnement(usages, ids, ab):
    """L'instantané de l'appel suit les lignes d'usage nées de cet appel (le premier vu est gardé)."""
    if ab:
        for u in usages:
            if u["id"] in ids:
                u.setdefault("abonnement", ab)


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
            r = _usage_d_un_lot(s, usages, lot, modele, agent, compteurs, "total" in e, texte(e, "etape", obligatoire=False))
            _noter_genres_des_usages(ctx, s, usages, r["ids"])
            _poser_abonnement(usages, r["ids"], _abonnement_de(e))
            return r
        if lot is not None and e.get("id") is not None:
            r = _usage_cumule_d_un_lot(s, usages, lot, e["id"], tache, modele, agent, compteurs, "total" in e,
                                       texte(e, "etape", obligatoire=False))
            _noter_genres_des_usages(ctx, s, usages, [r["id"]])
            _poser_abonnement(usages, [r["id"]], _abonnement_de(e))
            return r
        if e.get("id") is not None:
            u = next((x for x in usages if x["id"] == e["id"]), None)
            if u is None or u.get("genre") == "partenaire":
                raise Refus(f"Usage inconnu : {e['id']}")
        else:
            u = {"id": f"u{su.suivant(s, 'u')}", "t": su.maintenant()}
            usages.append(u)
        u.update({"agent": agent, "tache": tache, "modele": modele, "entree": entree, "sortie": sortie, **caches,
                  "estime": "total" in e})
        _noter_genre_de_l_usage(ctx, s, u, su.tache(s, tache) if tache else None)
        _poser_abonnement(usages, [u["id"]], _abonnement_de(e))
        if lot is not None:
            u["lot"] = lot
        etape = texte(e, "etape", obligatoire=False)
        if etape:
            u["etape"] = etape
        return {"id": u["id"]}


def _noter_genre_de_l_usage(ctx, s, u, t):
    """Le genre de la fonctionnalité de la tâche, noté sur l'usage (clé `genre_fonctionnalite` : le champ `genre` d'un
    usage est réservé aux partenaires). Sans genre connu, rien n'est noté."""
    genre = genre_de_tache(ctx, s, t)
    if genre:
        u["genre_fonctionnalite"] = genre
    else:
        u.pop("genre_fonctionnalite", None)


def _noter_genres_des_usages(ctx, s, usages, ids):
    for u in usages:
        if u["id"] in ids:
            _noter_genre_de_l_usage(ctx, s, u, su.tache(s, u["tache"]) if u.get("tache") else None)


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
            el["captures"] = [{"chemin": ctx.chemin_relatif(rel.chemin_d_image(c)),
                               **({"legende": rel.legende_d_image(c)} if rel.legende_d_image(c) else {}),
                               **({"passe": version} if version else {})} for c in captures]
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
    poly = rc.a_des_polyvalents(fiches)
    services_du_projet = {sv["id"] for sv in ctx.f["services"]}
    briefs = _briefs_du_releve(ctx) if poly else {}

    def service_de(t):      # un agent polyvalent n'a pas de service : celui de l'étape de sa tâche, sinon de son métier
        e = mn.etape_de_la_tache(ctx.f, t, s["fonctionnalites"])
        sv = (e or {}).get("service") or (briefs.get(t.get("role")) or {}).get("service")
        return sv if sv in services_du_projet else None

    en_cours = {}
    for t in s["taches"]:
        if poly and t["active"] and t["agent"] and t["colonne"] != "fait":
            en_cours.setdefault(t["agent"], service_de(t))
    for x in fiches:
        t = {"cle": x["cle"], "lieu": x["lieu"], "permanent": True, "prenom": x["prenom"],
             "specialite": x["specialite"],
             "lecons": [{"id": le["id"], "texte": le["texte"], "etat": le["etat"],
                         **({k: meta[le["id"]][k] for k in ("etage_propose", "texte_general", "roles")
                             if meta.get(le["id"], {}).get(k) is not None} if le["etat"] == "à valider" else {})}
                        for le in x["lecons"]]}
        if x["modele"] is not None:      # un agent polyvalent n'a pas de modèle : celui de sa tâche
            t["modele"] = x["modele"]
        if x["role"] == "chef":
            t["chef"] = True
        elif fi.est_polyvalente(x):      # ni service ni modèle : ceux de la tâche qu'il tient
            t["polyvalent"] = True
            t["service"] = en_cours.get(x["cle"])
            if x.get("retrait_prevu"):
                t["retrait_prevu"] = True
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
    if retours.get("orchestration"):      # les questions posées au Chef et ses réponses (panneau du Chef, direction)
        taches[0]["retours"] = retours["orchestration"]
    # Une fonctionnalité en cadrage sans vraie tâche de cadrage (l'orchestrateur en crée une pour `depart`) en
    # reçoit une, pour que son agent de cadrage se voie au travail.
    avec_tache = {t["fonctionnalite"] for t in s["taches"] if t.get("active") and t["colonne"] == "cadrage"}
    for f in s["fonctionnalites"]:
        if f["etape"] == "cadrage" and f["agent_cadrage"] in cles and f["id"] not in avec_tache:
            taches.append({"id": f"cadrage:{f['id']}", "titre": f"Cadrage : {f['nom']}", "colonne": "cadrage",
                           "active": True, "titulaire": f["agent_cadrage"], "etape": "", "maj": f["maj"]})
    colonnes = _colonnes_du_releve(ctx, s["fonctionnalites"])
    visibles = {c["id"] for c in colonnes}
    for t in s["taches"]:
        # La colonne d'une fonctionnalité finie ou partie ailleurs n'est plus au tableau : sa tâche est rangée à « fait ».
        v = {"id": t["id"], "titre": t["titre"], "colonne": t["colonne"] if t["colonne"] in visibles else "fait",
             "active": t["active"],
             "titulaire": t["agent"] if t["agent"] in cles else None, "etape": t["etape"] or "", "maj": t["maj"],
             "journal": list(t["journal"]), "fonctionnalite": t["fonctionnalite"], "element": t["element"],
             "modele_depart": t["modele_depart"], "montee": t["montee"], "bloquee": t["bloquee"],
             "lot": dict(t["lot"]) if isinstance(t.get("lot"), dict) else None,
             "modele_necessaire": mn.de_la_tache(ctx.f, t, fiches, s["fonctionnalites"]),
             "debut": t.get("debut"), "fin": t.get("fin")}      # le temps de la tâche (vue d'un agent, d'un service)
        if poly:      # le service de la tâche (étape, sinon métier) : la pièce où son agent s'assoit
            v["service"] = service_de(t)
        resume = resume_de_tache(t, s["fonctionnalites"])
        if resume:
            v["resume"] = resume
        if t.get("lignes") is not None:
            v["lignes"] = t["lignes"]
        if t.get("captures"):
            v["images"] = [_image_au_releve(c, chemin) for c in t["captures"]]
        if t["id"] in retours:
            v["retours"] = retours[t["id"]]
        taches.append(v)

    elements_file = [{"id": f"{f['id']}/{q['id']}", "titre": q["nom"]} for f in s["fonctionnalites"] for q in f["file"]]
    fonctionnalites = []
    for f in s["fonctionnalites"]:
        v = {"id": f["id"], "nom": f["nom"], "etape": f["etape"],
             "agent_cadrage": f["agent_cadrage"] if f["agent_cadrage"] in cles else None,    # un agent retiré : plus d'agent
             "attend_reponse": f["attend_reponse"], "discussion": [],
             "decisions": [_decision_au_releve(d, s) for d in f["decisions"]],
             "catalogue": bool(f["catalogue"] or f["id"] in ctx.f["catalogues"]),
             "cahier": f["cahier"], "methode": f["methode"], "livrable": f["livrable"]}
        for cle in ("genre", "workflow", "deplacee_vers"):   # facultatifs : absents d'un projet qui n'en a pas l'usage
            if f.get(cle):
                v[cle] = f[cle]
        w = wf.de_la_fonctionnalite(ctx.f, f) if f.get("workflow") else None
        if w:   # ses étapes, pour nommer les documents d'une fonctionnalité dont les colonnes ont quitté le tableau
            v["workflow_etapes"] = [{"id": x["id"], "nom": x["nom"]} for x in w["flux"]]
        for m in f["discussion"]:
            m = dict(m)
            if m.get("images"):
                m["images"] = [_chemin_ou_image(c, chemin) for c in m["images"]]
            if m.get("fichiers"):
                m["fichiers"] = [{**x, "chemin": chemin(x["chemin"])} for x in m["fichiers"]]
            v["discussion"].append(m)
        if f["cahier"]:
            v["cahier"] = {**f["cahier"], "maquette": [_chemin_ou_image(c, chemin) for c in f["cahier"]["maquette"]]}
        if f.get("cahiers_precedents"):
            v["cahiers_precedents"] = [{**c, "maquette": [_chemin_ou_image(x, chemin) for x in c["maquette"]]}
                                       for c in f["cahiers_precedents"]]
        if f["methode"] and f["methode"].get("chemin"):
            v["methode"] = {**f["methode"], "chemin": chemin(f["methode"]["chemin"])}
        if f["livrable"] and f["livrable"].get("chemin"):
            v["livrable"] = {**f["livrable"], "chemin": chemin(f["livrable"]["chemin"])}
        v["documents"] = [{**d, "chemin": chemin(d["chemin"])} for d in documents_complets(f, s["taches"])]
        if isinstance(f.get("fin"), dict):     # l'avis de fin (« Fonctionnalités terminées » au bureau de direction)
            v["fin"] = {**f["fin"], "livrables": [{**x, "chemin": chemin(x["chemin"])}
                                                  for x in f["fin"].get("livrables") or []]}
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
        if isinstance(x.get("refus"), dict) and x["refus"].get("raison"):   # le dernier refus d'écrire, dit sur la leçon
            le["refus"] = x["refus"]["raison"]
        for d in en_attente.values():
            if d.get("cible") == x["id"]:
                le["verdict_demande"] = d.get("verdict")
        for d in s["demandes"]:   # la discussion ouverte sur cette leçon (un challenge), s'il y en a une
            if d["type"] == "challenge" and isinstance(d.get("cible"), dict) and d["cible"].get("id") == x["id"]:
                le["challenge_tache"] = d.get("tache")
        lecons.append(le)

    # Validées, mais pas encore écrites dans la mémoire de la skill : elles ont quitté la liste « à valider ».
    lecons_en_attente = [{"id": x["id"], "agent": x["agent"] if x["agent"] in cles else chef, "texte": x["texte"],
                          "etage": x.get("etage_applique") or x.get("etage_propose") or "projet",
                          "raison": x["ecriture"].get("raison") or "", "depuis": x["ecriture"].get("depuis"),
                          "essais": x["ecriture"].get("essais", 1)}
                         for x in s["lecons"] if x["etat"] == "validée" and isinstance(x.get("ecriture"), dict)]

    en_pause = s["factory"]["etat"] == "en pause"
    r = {"version": 4, "projet": ctx.f["nom"], "factory": dict(s["factory"]),
         "services": [dict(x) for x in ctx.f["services"]],
         "colonnes": colonnes,
         "titulaires": titulaires, "taches": taches,
         "file": {"visibles": elements_file[:VISIBLES], "suite": elements_file[VISIBLES:VISIBLES + rel.MAX_SUITE],
                  "reste": max(0, len(elements_file) - VISIBLES)},
         "decisions": 0, "lecons": lecons, "lecons_en_attente": lecons_en_attente,
         "actions": [{"id": "reprendre", "libelle": "Reprendre"} if en_pause else
                     {"id": "pause", "libelle": "Pause", "confirmer": "Mettre la factory en pause ?"}],
         "genre": ctx.f["genre"], "livrable": s["livrable"], "fonctionnalites": fonctionnalites,
         "decisions_projet": [_decision_au_releve(d, s) for d in s["decisions_projet"]],
         "agents_locaux_max": ctx.f["agents_locaux_max"], "agents_cloud_max": places_cloud_du_projet(ctx),
         "orchestrateur_present": guetteur.present(_presence(ctx), datetime.now().astimezone()),
         "regles_projet": rp.lire(ctx.f),
         "recrutement": releve_recrutement(ctx, s, fiches)}
    # La facturation : les usages récents, au format du bureau (une tâche ou un agent disparu devient « hors tâche »).
    ids_taches, cles_titulaires = {t["id"] for t in taches}, {t["cle"] for t in titulaires}
    r["usage"] = [_usage_au_releve(u, ids_taches, cles_titulaires) if u.get("genre") == "partenaire" else
                  {"id": u["id"], "tache": u["tache"] if u.get("tache") in ids_taches else None,
                   "agent": u["agent"] if u.get("agent") in cles_titulaires else None, "modele": u["modele"],
                   "t": u["t"], "entree": u["entree"], "sortie": u["sortie"],
                   "cache_lecture": u.get("cache_lecture", 0), "cache_ecriture": u.get("cache_ecriture", 0),
                   **({"etape": u["etape"]} if u.get("etape") else {}),
                   **({"genre_fonctionnalite": u["genre_fonctionnalite"]} if u.get("genre_fonctionnalite") else {}),
                   **({"lot": u["lot"]} if u.get("lot") else {}),
                   **({"reparti": u["reparti"]} if u.get("reparti") else {}),
                   **({"abonnement": u["abonnement"]} if u.get("abonnement") else {})}
                  for u in (s.get("usage") or [])[-USAGES_AU_RELEVE:]]
    partenaires = _releve_partenaires(ctx)
    if partenaires is not None:
        r["partenaires"] = partenaires
    if poly:      # les leçons se lisent par métier (elles ne sont plus dans la fiche d'un agent)
        r["metiers"] = [{"role": m["role"], "service": m["service"] if m["service"] in services_du_projet else None,
                         "modele": m["modele"], "specialite": m["specialite"],
                         "lecons": [dict(le) for le in m["lecons"]]}
                        for m in briefs.values() if m["service"] or m["lecons"]]
    return r


def _briefs_du_releve(ctx):
    """{role: métier} des briefs lisibles du projet ; un brief illisible n'arrête pas le relevé."""
    dossier = Path(ctx.f["fiches"]) / "briefs"
    sortie = {}
    for c in sorted(dossier.glob("*.md")) if dossier.is_dir() else []:
        try:
            m = metiers.lire_metier(dossier, c.stem)
        except (metiers.MetierInvalide, OSError, ValueError):
            continue
        if m:
            sortie[c.stem] = m
    return sortie


def _decision_au_releve(d, s):
    """Une décision telle que le bureau la lit : celle de l'environnement marque `en_cours` chaque outil qu'une tâche
    d'installation pas encore finie couvre (le bouton « Installer en autonomie » n'est plus offert)."""
    d = dict(d)
    if d.get("genre") == "environnement" and isinstance(d.get("environnement"), list):
        en_cours = [t for t in s["taches"] if t.get("etape") == "environnement" and t["colonne"] != "fait"
                    and not t.get("bloquee")]
        d["environnement"] = [dict(x, en_cours=True) if any(str(j["texte"]).startswith(f"- {x.get('outil')} (")
                                                  for t in en_cours for j in t["journal"])
                              else dict(x) for x in d["environnement"]]
    return d


def _colonnes_du_releve(ctx, fonctionnalites):
    """Les colonnes du tableau, chacune avec son genre (s'il y en a un) ; l'identifiant du workflow n'est donné que
    quand le projet en a plusieurs (un projet sans `workflows` garde son relevé d'avant)."""
    colonnes = wf.colonnes(ctx.f, fonctionnalites)
    for c in colonnes:
        if c.get("genre") is None:
            c.pop("genre", None)
        if not ctx.f["workflows"]:
            c.pop("workflow", None)
    return colonnes


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
    for x in r["partenaires"] + r.get("inscrits", []):
        x["nom"] = par_id[x["id"]]["nom"]
    for x in r.get("inscrits", []):
        x["site"] = par_id[x["id"]].get("site")      # là où l'utilisateur fait la génération
    return r


def _p_inscrire(ctx, e, cat, par_id):
    """« Je suis inscrit » / « Je ne suis plus inscrit » : l'utilisateur a (ou n'a plus) un compte chez ce partenaire, hors
    liaison directe. Seulement le fait, la date et une note facultative (nom du compte, offre) : jamais un identifiant ni
    un mot de passe."""
    i = _partenaire(e, par_id)
    inscrit = e.get("inscrit")
    if not isinstance(inscrit, bool):
        raise Refus("« inscrit » doit être vrai ou faux.")
    if inscrit and par_id[i].get("statut") == "ferme":
        raise Refus(f"{par_id[i]['nom']} est fermé : on ne s'y inscrit plus.")
    with _etat_partenaires().transaction() as d:
        try:
            ligne = petat.inscrire(d, i, inscrit, e.get("note"))
        except ValueError as ex:
            raise Refus(str(ex))
    return {"ok": True, "partenaire": i, "inscrit": inscrit, **({"inscription": ligne} if ligne else {})}


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


def _etat_partenaires_lisible():
    """L'état des partenaires, ou un état vide s'il est illisible : rien ne bloque sans partenaire."""
    try:
        return _etat_partenaires().lire()
    except (petat.EtatIllisible, OSError):
        return petat.vide()


def verifier_partenaires_cadrage(ctx, liste):
    """Les partenaires décidés au cadrage (`cahier.partenaires`, `[{id, mode}]`) contre le catalogue et l'état : un partenaire
    du catalogue ; `direct` seulement s'il est connecté, `inscrit` seulement si l'utilisateur a dit l'être. Refus sinon."""
    par_id = {p["id"]: p for p in _catalogue(ctx)["partenaires"]}
    d = _etat_partenaires_lisible()
    for x in liste:
        i, mode = x["id"], x["mode"]
        if i not in par_id:
            raise Refus(f"Partenaire inconnu du catalogue : {i}")
        if mode == "direct" and (d["connexions"].get(i) or {}).get("etat") != "connecte":
            raise Refus(f"{par_id[i]['nom']} n'est pas connecté : le mode « direct » ne s'y applique pas (« inscrit » s'il a "
                        "un compte, ou « aucun »).")
        if mode == "inscrit" and i not in (d.get("inscriptions") or {}):
            raise Refus(f"L'utilisateur n'a pas dit être inscrit chez {par_id[i]['nom']} : le mode « inscrit » ne s'y applique "
                        "pas (« aucun » si on n'utilise pas ce partenaire).")


def _p_verifier_cadrage(ctx, e, cat, par_id):
    liste = e.get("partenaires")
    if not rel.partenaires_cahier_ok(liste):
        raise Refus("« partenaires » est une liste de {id, mode} (mode : direct, inscrit ou aucun), un partenaire au plus une fois.")
    verifier_partenaires_cadrage(ctx, liste)
    return {"ok": True}


def _p_disponibles(ctx, e, cat, par_id):
    """Les partenaires que le cadrage peut proposer à l'utilisateur : ceux qu'il a connectés (`direct`) et ceux où il est
    inscrit (`inscrit`), avec de quoi les reconnaître (catégorie, à quoi ils servent). Jamais un fermé."""
    d = _etat_partenaires_lisible()
    sortie = []
    for p in cat["partenaires"]:
        i = p["id"]
        modes = ([] if (d["connexions"].get(i) or {}).get("etat") != "connecte" or p.get("statut") != "actif" else ["direct"])             + (["inscrit"] if i in (d.get("inscriptions") or {}) and p.get("statut") != "ferme" else [])
        if modes:
            sortie.append({"id": i, "nom": p["nom"], "categorie": p.get("categorie"), "sous_categorie": p.get("sous_categorie"),
                           "description": p.get("description"), "modes": modes})
    return {"partenaires": sortie}


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
                       "usage": _p_usage, "limite": _p_limite, "regle": _p_regle, "inscrire": _p_inscrire, "disponibles": _p_disponibles, "verifier_cadrage": _p_verifier_cadrage, "conseils": _p_conseils,
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


def partenaires_du_depart(ctx, s, taches):
    """Les partenaires du départ d'un agent, d'après ses tâches : `(directs, inscrits, ecartes)`. Ceux que la tâche porte
    (`partenaires`) et ceux que le cadrage a décidés (`cahier.partenaires` de sa fonctionnalité). Un partenaire écarté au
    cadrage (`aucun`) n'est ni appelé ni préparé ; `inscrit` (décidé, ou, sans décision, un compte sans liaison directe) :
    l'agent prépare ce que l'utilisateur fait, il n'appelle pas. `directs` : `[(nom, [règles])]` ; `inscrits` : `[{nom, site,
    note, regles, prompt_max, reglages}]` ; `ecartes` : les noms."""
    ids, decides = [], {}
    for t in taches:
        ids += t.get("partenaires") or []
        fonc = su.fonctionnalite(s, t["fonctionnalite"]) if t.get("fonctionnalite") else None
        for x in ((fonc or {}).get("cahier") or {}).get("partenaires") or []:
            decides[x["id"]] = x["mode"]
    ids = list(dict.fromkeys(ids + [i for i, m in decides.items() if m != "aucun"]))
    ecartes = [i for i, m in decides.items() if m == "aucun"]
    if not ids and not ecartes:
        return [], [], []
    try:
        cat = {p["id"]: p for p in _catalogue(ctx)["partenaires"]}
        etat = _etat_partenaires().lire()
    except (Refus, OSError, ValueError):
        return regles_des_partenaires(ctx, [i for i in ids if i not in ecartes]), [], []
    directs, inscrits = [], []
    for i in ids:
        if i in ecartes:
            continue
        mode = decides.get(i) or ("inscrit" if petat.est_inscrit(etat, i) else "direct")
        if mode != "inscrit":
            directs.append(i)
        elif i in cat:
            inscrits.append({"nom": cat[i]["nom"], "site": cat[i].get("site"), "note": (etat["inscriptions"].get(i) or {}).get("note"),
                             "regles": [r["texte"] for r in etat["regles"].get(i) or [] if isinstance(r, dict) and r.get("texte")],
                             "prompt_max": petat.PROMPT_MAX.get(i), "reglages": i in petat.REGLAGES_OBLIGATOIRES})
    return regles_des_partenaires(ctx, directs), inscrits, [cat[i]["nom"] for i in ecartes if i in cat]


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
    etat = {s: {i: v for i, v in d.get(s, {}).items() if i in ids}
            for s in ("connexions", "quotas", "limites", "regles", "inscriptions")}
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
    if action == "decrire":    # élargir la description d'un genre existant (après l'accord du Directeur)
        genre = texte(e, "genre")
        if genre not in {g["id"] for g in memoire.genres(ctx.f["memoire"])}:
            raise Refus(f"Genre inconnu : « {genre} ».")
        ok, message = memoire.decrire_genre(ctx.f["memoire"], genre, e.get("description"), ctx.f["mots_interdits"], git=GIT)
        if not ok:
            raise Refus(message)
        return {"genre": genre, "message": message}
    if action != "fixer":
        raise Refus("« action » doit valoir lister, fixer ou decrire.")
    genre = texte(e, "genre")
    if not fa.MOTIF_GENRE.match(genre):
        raise Refus("Identifiant de genre refusé (minuscules, chiffres et tirets, 40 caractères au plus).")
    cree = genre not in {g["id"] for g in memoire.genres(ctx.f["memoire"])}
    if cree:   # un nouveau genre : son fichier de mémoire, avec sa description, avant de le noter au projet
        ok, message = memoire.creer_genre(ctx.f["memoire"], genre, e.get("description"), ctx.f["mots_interdits"], git=GIT)
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
    if action == "reessayer":
        return _reessayer_ecritures(ctx)
    raise Refus("« action » doit valoir noter, appliquer ou reessayer.")


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
    polyvalent = fiche_agent is not None and fi.est_polyvalente(fiche_agent)
    metier_role = None
    if polyvalent:   # la leçon appartient au métier de la tâche, pas à l'agent
        t = su.tache(ctx.suivi.lire(), tache) if tache else None
        metier_role = (t or {}).get("role")
        if not metier_role or not depart._ROLE_SUR.match(metier_role):
            raise Refus("Un agent polyvalent note sa leçon avec « tache » : l'identifiant d'une tâche qui a un métier "
                        "(rôle), car la leçon est celle de ce métier.")
    prefixe = metier_role or agent
    with ctx.suivi.transaction() as s:
        pris = {x["id"] for x in s["lecons"]} | {x["id"] for x in (fiche_agent["lecons"] if fiche_agent else [])}
        if metier_role:
            m = _lire_metier(ctx, metier_role)
            pris |= {x["id"] for x in (m["lecons"] if m else [])}
        while True:
            i = f"{prefixe}:L{su.suivant(s, 'l')}"
            if i not in pris:
                break
        nouvelle = {"id": i, "agent": agent, "tache": tache, "date": su.maintenant()[:10], "texte": contenu,
                    "etat": "à valider", "etage_propose": etage, "texte_general": general, "roles": roles}
        if metier_role:
            nouvelle["metier"] = metier_role
        s["lecons"].append(nouvelle)
        if metier_role:
            _noter_dans_le_metier(ctx, metier_role, i, contenu)
        elif fiche_agent:
            fiche_agent["lecons"].append({"etat": "à valider", "id": i, "texte": _ligne_fiche(contenu)})
            fi.ecrire_fiche(fiche_agent)
    return {"id": i}


def _lire_metier(ctx, role):
    try:
        return metiers.lire_metier(Path(ctx.f["fiches"]) / "briefs", role)
    except metiers.MetierInvalide as ex:
        raise Refus(str(ex))


def _metier_de(ctx, role):
    """Le métier du rôle d'une tâche ; un métier vide (sans brief ni leçons) si le rôle n'a pas de brief ou est absent."""
    m = _lire_metier(ctx, role) if isinstance(role, str) and depart._ROLE_SUR.match(role) else None
    return m or {"role": role or "(sans métier)", "service": None, "modele": None, "lieu": "indifférent",
                 "specialite": None, "outils": None, "texte": "", "lecons": [], "chemin": None}


def _noter_dans_le_metier(ctx, role, ident, contenu):
    """Une leçon « à valider » dans le brief du métier (rien si le brief n'existe pas encore : la validation le crée)."""
    m = _lire_metier(ctx, role)
    if m is not None and metiers.ajouter_lecon(m, {"id": ident, "etat": "à valider", "texte": _ligne_fiche(contenu)}):
        metiers.ecrire_metier(m)


def _verdict_dans_le_metier(ctx, role, lecon, verdict):
    """Le verdict du Directeur sur une leçon, répercuté dans le brief du métier : validée (le brief est créé si besoin) ou
    retirée."""
    m = _lire_metier(ctx, role)
    ligne = _ligne_fiche(lecon["texte"])
    if verdict == "valider":
        if m is None:
            dossier = Path(ctx.f["fiches"]) / "briefs"
            m = {"role": role, "service": None, "modele": None, "lieu": "indifférent", "specialite": None,
                 "outils": None, "texte": "", "lecons": [], "chemin": dossier / f"{role}.md"}
        propre = next((y for y in m["lecons"] if y["id"] == lecon["id"]), None)
        if propre is not None:
            propre["etat"] = "validée"
        else:
            ancienne = next((y for y in m["lecons"] if y["texte"].strip() == ligne), None)
            if ancienne is not None:
                ancienne["etat"] = "validée"   # le même texte, déjà là : il devient la règle
            else:
                metiers.ajouter_lecon(m, {"id": lecon["id"], "etat": "validée", "texte": ligne})
    elif m is not None:
        m["lecons"] = [y for y in m["lecons"] if y["id"] != lecon["id"]]
    else:
        return
    metiers.ecrire_metier(m)


def _metier_de_la_lecon(ctx, s, lecon, fiche_agent):
    """Le métier où va une leçon validée, ou `None` (la fiche de l'agent, à l'ancienne, la garde). Une leçon d'agent
    polyvalent porte son métier. Une leçon à l'ancien id (`<agent>:L<n>`) dont la fiche a été reprise (ou n'existe plus) va
    au métier noté sur la leçon, sinon au rôle que dit le préfixe de l'id s'il a un brief, sinon au rôle de sa tâche."""
    if lecon.get("metier"):
        return lecon["metier"]
    if fiche_agent is not None and not fi.est_polyvalente(fiche_agent):
        return None
    dossier = Path(ctx.f["fiches"]) / "briefs"
    for role in (lecon.get("role"), lecon["id"].split(":", 1)[0]):
        if isinstance(role, str) and depart._ROLE_SUR.match(role) and (dossier / f"{role}.md").is_file():
            return role
    t = su.tache(s, lecon["tache"]) if lecon.get("tache") else None
    role = (t or {}).get("role")
    return role if isinstance(role, str) and depart._ROLE_SUR.match(role) else None


def genre_de_tache(ctx, s, t):
    """Le genre de la fonctionnalité de la tâche, sinon celui du projet."""
    fonc = su.fonctionnalite(s, t["fonctionnalite"]) if t and t.get("fonctionnalite") else None
    return wf.genre_de(ctx.f, fonc)


def _genre_de_la_lecon(ctx, s, lecon):
    """Le genre de la fonctionnalité où la leçon a été notée (sa tâche), sinon celui du projet."""
    return genre_de_tache(ctx, s, su.tache(s, lecon["tache"]) if lecon.get("tache") else None)


def _appliquer_lecon(ctx, e):
    """Le verdict de l'utilisateur sur une leçon ; `lot` (une liste de `{id, verdict, etage?}`) : plusieurs verdicts, le
    dépôt de la skill n'étant mis à jour et poussé qu'une fois. Un verdict seul refuse (code 1) ce qu'un lot rend en
    `refus` de la leçon."""
    lot = e.get("lot")
    if lot is None:
        items = [{"id": texte(e, "id"), "verdict": e.get("verdict"), "etage": e.get("etage")}]
    else:
        if not isinstance(lot, list) or not lot:
            raise Refus("« lot » doit être une liste non vide de verdicts.")
        items = []
        for x in lot:
            if not isinstance(x, dict) or not isinstance(x.get("id"), str) or not x["id"].strip():
                raise Refus("Chaque verdict du lot a un « id » (texte).")
            items.append({"id": x["id"], "verdict": x.get("verdict"), "etage": x.get("etage")})
    resultats = _appliquer_verdicts(ctx, items)
    if lot is not None:
        return {"resultats": resultats}
    r = resultats[0]
    if not r["ok"]:
        raise Refus(r["refus"])
    sortie = {"ok": True, "etage": r["etage"]}
    if r.get("en_attente"):
        sortie.update(en_attente=True, raison=r["raison"])
    return sortie


def _lecon_pour_la_memoire(lecon):
    general = lecon["texte_general"].strip()
    return {"titre": general.split(".")[0].strip()[:60] or general[:60], "texte": general,
            "roles": lecon.get("roles") or ["tous"]}


def _appliquer_verdicts(ctx, items):
    """Un résultat par verdict : `{id, ok, etage}` plus `refus` (la leçon reste « à valider », avec la raison), ou
    `en_attente` et `raison` (validée, mais son écriture dans la mémoire est à refaire : le moteur la réessaie)."""
    s = ctx.suivi.lire()
    resultats, ecritures, vus = [], [], set()
    for x in items:
        i, verdict = x["id"], x["verdict"]
        r = {"id": i, "ok": True, "etage": None}
        resultats.append(r)
        if verdict not in ("valider", "invalider"):
            r.update(ok=False, refus="« verdict » doit valoir valider ou invalider.")
            continue
        lecon = next((y for y in s["lecons"] if y["id"] == i and y["etat"] == "à valider"), None)
        if lecon is None or i in vus:
            r.update(ok=False, refus=f"Leçon inconnue ou déjà traitée : {i}")
            continue
        vus.add(i)
        etage = x.get("etage") or lecon["etage_propose"]
        if etage not in rel.ETAGES:
            r.update(ok=False, refus=f"Étage inconnu « {etage} » ({', '.join(rel.ETAGES)}).")
            continue
        r["etage"] = etage if verdict == "valider" else None
        r["_lecon"], r["_verdict"] = lecon, verdict
        if verdict == "valider" and etage != "projet":
            if not (lecon.get("texte_general") or "").strip():
                r.update(ok=False, refus="Cette leçon n'a pas de texte général : elle ne peut aller qu'à l'étage projet.")
                del r["_lecon"], r["_verdict"]
                continue
            ecritures.append((r, (etage, _genre_de_la_lecon(ctx, s, lecon), _lecon_pour_la_memoire(lecon))))
    if ecritures:   # une seule mise à jour du dépôt de la skill, un seul push, pour tout le lot
        ecrites = memoire.ecrire_lecons(ctx.f["memoire"], [p for _, p in ecritures], ctx.f["mots_interdits"], git=GIT)
        for (r, _), m in zip(ecritures, ecrites):
            r["_memoire"] = m
    fiches = ctx.fiches()
    with ctx.suivi.transaction() as s2:
        for r in resultats:
            lecon, verdict = r.pop("_lecon", None), r.pop("_verdict", None)
            m = r.pop("_memoire", None)
            if lecon is None:
                continue
            i = r["id"]
            courante = next((y for y in s2["lecons"] if y["id"] == i and y["etat"] == "à valider"), None)
            if courante is None:
                r.update(ok=False, refus=f"La leçon {i} vient d'être traitée.")
                continue
            if m is not None and not m.ok and not m.transitoire:   # refusée : elle reste « à valider », avec la raison
                courante["refus"] = {"raison": m.message, "t": su.maintenant()}
                r.update(ok=False, refus=m.message)
                continue
            fiche_agent = fi.trouver(fiches, lecon["agent"])
            metier_role = _metier_de_la_lecon(ctx, s2, lecon, fiche_agent)
            courante.pop("refus", None)
            if verdict == "valider":
                courante["etat"], courante["etage_applique"] = "validée", r["etage"]
                if m is not None and not (m.ok and m.publie):   # à écrire ou à pousser plus tard
                    maintenant = su.maintenant()
                    courante["ecriture"] = {"etat": "en attente", "raison": m.message, "depuis": maintenant,
                                            "essais": 1, "dernier_essai": maintenant, "commitee": m.commite}
                    r.update(en_attente=True, raison=m.message)
            else:
                s2["lecons"].remove(courante)
            if metier_role:
                _verdict_dans_le_metier(ctx, metier_role, lecon, verdict)
            elif fiche_agent:
                if verdict == "valider":
                    for y in fiche_agent["lecons"]:
                        if y["id"] == i:
                            y["etat"] = "validée"
                else:
                    fiche_agent["lecons"] = [y for y in fiche_agent["lecons"] if y["id"] != i]
                fi.ecrire_fiche(fiche_agent)
    return resultats


def _reessayer_ecritures(ctx):
    """Reprend les leçons validées dont l'écriture dans la mémoire de la skill n'a pas abouti : celles pas encore
    écrites le sont (une seule mise à jour du dépôt), celles seulement commitées en local sont poussées. Sans leçon en
    attente, le dépôt n'est pas touché."""
    s = ctx.suivi.lire()
    attente = [x for x in s["lecons"] if x["etat"] == "validée" and x.get("ecriture")]
    if not attente:
        return {"ecrites": 0, "en_attente": 0, "resultats": []}
    a_ecrire = [x for x in attente if not x["ecriture"].get("commitee")]
    deja = [x for x in attente if x["ecriture"].get("commitee")]
    issue = {}
    publication = None
    if a_ecrire:
        plans = [(x["etage_applique"], _genre_de_la_lecon(ctx, s, x), _lecon_pour_la_memoire(x)) for x in a_ecrire]
        for x, m in zip(a_ecrire, memoire.ecrire_lecons(ctx.f["memoire"], plans, ctx.f["mots_interdits"], git=GIT)):
            issue[x["id"]] = m
            if m.ok and m.commite:
                publication = publication or m
    if deja:
        pub = publication or memoire.republier(ctx.f["memoire"], git=GIT)
        for x in deja:
            issue[x["id"]] = pub
    ecrites = 0
    with ctx.suivi.transaction() as s2:
        for x in attente:
            courante = next((y for y in s2["lecons"] if y["id"] == x["id"] and y.get("ecriture")), None)
            m = issue[x["id"]]
            if courante is None:
                continue
            if m.ok and m.publie:
                del courante["ecriture"]
                ecrites += 1
            else:
                en = courante["ecriture"]
                en.update(raison=m.message, essais=en.get("essais", 1) + 1, dernier_essai=su.maintenant(),
                          commitee=bool(en.get("commitee") or m.commite))
        restantes = sum(1 for y in s2["lecons"] if y.get("ecriture"))
    return {"ecrites": ecrites, "en_attente": restantes,
            "resultats": [{"id": x["id"], "ok": issue[x["id"]].ok and issue[x["id"]].publie,
                           "raison": issue[x["id"]].message} for x in attente]}


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


def places_cloud_du_projet(ctx):
    """Les places cloud effectives (voir `depart.places_cloud`)."""
    return depart.places_cloud(ctx.f["agents_cloud_max"],
                               depart.ancienne_limite_cloud(ctx.f["reglages"]) if ctx.f["reglages"] else None,
                               any(x["lieu"] == "cloud" for x in ctx.fiches()))


def synchroniser_equipe(ctx, creer=True, cloud_aussi=True):
    """Ramène l'équipe d'un projet polyvalent aux places (voir `recrutement.ajuster_equipe`) : crée des fiches polyvalentes
    (prénom et clé libres), retire les agents libres en trop, marque (`Retrait : prévu`) ceux qui travaillent encore.
    Rend `{crees, retires, retraits_prevus}` (clés) ; rien pour un projet à l'ancienne ou mixte. Rejouable sans effet.
    `cloud_aussi` faux : aucun agent cloud n'est créé (la reprise d'un projet ne crée que des agents locaux)."""
    vide = {"crees": [], "retires": [], "retraits_prevus": []}
    with ctx.suivi.transaction() as suivi:     # un seul écrivain à la fois (l'outil, le moteur et le bureau)
        fiches_ = ctx.fiches()
        if rc.equipe_pure(fiches_) is None:
            return vide
        occupes = {t["agent"] for t in suivi["taches"] if t.get("active") and t.get("agent")}
        plan = rc.ajuster_equipe(fiches_, occupes, ctx.f["agents_locaux_max"], places_cloud_du_projet(ctx), creer)
        plan["creer"] = [lieu for lieu in plan["creer"] if cloud_aussi or lieu != "cloud"]
        par_cle = {x["cle"]: x for x in fiches_}
        for cle in plan["retirer"]:
            Path(par_cle[cle]["chemin"]).unlink(missing_ok=True)
        for cle in plan["marquer"]:
            if not par_cle[cle].get("retrait_prevu"):
                par_cle[cle]["retrait_prevu"] = True
                fi.ecrire_fiche(par_cle[cle])
        for cle in plan["demarquer"]:
            par_cle[cle]["retrait_prevu"] = False
            fi.ecrire_fiche(par_cle[cle])
        crees, prises, existantes = [], {x["cle"] for x in fiches_}, list(fiches_)
        try:
            for lieu in plan["creer"]:
                cle = rc.cle_d_agent_libre(prises, ctx.f["fiches"])
                nouvelle = fi.nouvelle_fiche(cle, rc.prenom_libre(existantes), lieu)
                nouvelle["chemin"] = Path(ctx.f["fiches"]) / f"{cle}.md"
                fi.ecrire_fiche(nouvelle)
                prises.add(cle)
                existantes.append(nouvelle)
                crees.append(cle)
        except BaseException:
            for cle in crees:
                (Path(ctx.f["fiches"]) / f"{cle}.md").unlink(missing_ok=True)
            raise
        fi.lire_toutes(ctx.f["fiches"])
    return {"crees": crees, "retires": list(plan["retirer"]), "retraits_prevus": list(plan["marquer"])}


def cmd_equipe(ctx, e):
    """Le moteur retire les agents dont le retrait était prévu et dont la tâche est finie (jamais d'agent neuf : seul un
    réglage des places en crée). Rend `{crees, retires, retraits_prevus}`."""
    return synchroniser_equipe(ctx, creer=False)


def cmd_polyvalents(ctx, e):
    """`{confirme: true}` : le clic « Passer aux agents polyvalents » du Directeur (jamais sans lui). Reprend le projet
    (voir `orchestrateur/reprise_polyvalents.py`) : un métier par rôle, les leçons regroupées par métier, l'équipe ramenée
    aux places, aucune tâche touchée ; rejouable sans effet. Rend le compte rendu `{metiers, lecons_regroupees, doublons,
    agents_gardes, agents_retires, retraits_prevus, agents_crees, deja, compte_rendu}`."""
    from orchestrateur import reprise_polyvalents
    if e.get("confirme") is not True:
        raise Refus("« polyvalents » demande confirme: vrai (le clic du Directeur).")
    try:
        return reprise_polyvalents.reprendre(ctx)
    except reprise_polyvalents.RepriseImpossible as ex:
        raise Refus(str(ex))


def cmd_parallelisme(ctx, e):
    """`{agents_locaux_max: 1 à 16, agents_cloud_max: 0 à 16}` : les places du projet, écrites dans la factory (le
    reste du fichier est gardé). Dans un projet d'agents polyvalents, l'équipe suit : un agent de plus par place
    ajoutée, un agent libre de moins par place retirée (un agent au travail finit sa tâche, voir `synchroniser_equipe`).
    Rend les valeurs écrites et, pour un projet polyvalent seulement, `{crees, retires, retraits_prevus}`."""
    locaux, cloud = e.get("agents_locaux_max"), e.get("agents_cloud_max")
    try:
        fa.ecrire_parallelisme(ctx.f["chemin"], locaux, cloud)
    except fa.FactoryInvalide as ex:
        raise Refus(str(ex))
    ctx.f = fa.lire(ctx.f["chemin"])     # les places qui viennent d'être écrites
    if rc.equipe_pure(ctx.fiches()) is None:      # un projet à l'ancienne (ou mixte) : la réponse d'avant, rien d'autre
        return {"agents_locaux_max": locaux, "agents_cloud_max": cloud}
    return {"agents_locaux_max": locaux, "agents_cloud_max": cloud, **synchroniser_equipe(ctx)}


# --- Le recrutement depuis le bureau (conception 2026-11-12-recrutement-design.md).

GH = None    # remplacé par les tests : (args, cwd) -> (code, sortie) ; None : le vrai `gh` (installation.creation)


def _fichier_depot(ctx):
    """Le dernier essai de « Créer le dépôt Git » : son résultat, montré au bureau."""
    return ctx.f["suivi"].with_name("depot-git.json")


MAX_RESUME_TACHE = 600       # le même plafond que le bureau (`bureau.releve.MAX_RESUME_TACHE`)
CONSIGNES_DU_JOURNAL = ("Remarque du Directeur", "Consigne de l'utilisateur", "Note du Directeur",
                        "Retour de l'utilisateur", "Reprise sur votre retour")


def resume_de_tache(t, fonctionnalites):
    """Ce que la tâche doit produire, en clair et sans appel d'IA, pour le Directeur : l'objectif de son élément (écrit
    au découpage), sinon la première entrée de son journal (la consigne qui l'a ouverte) ; puis la dernière consigne du
    Directeur, s'il y en a une. `None` si on ne sait rien de plus que le titre."""
    objectif = None
    f = next((x for x in fonctionnalites if x["id"] == t.get("fonctionnalite")), None)
    element = ((f or {}).get("elements") or {}).get(t.get("element")) if t.get("element") else None
    if isinstance(element, dict) and isinstance(element.get("objectif"), str) and element["objectif"].strip():
        objectif = " ".join(element["objectif"].split())
    journal = [str(j.get("texte") or "").strip() for j in t.get("journal") or [] if isinstance(j, dict)]
    journal = [j for j in journal if j]
    if objectif is None and journal and journal[0] != "Terminé.":
        objectif = " ".join(journal[0].split())
    # une relance par le bouton du bureau (« … (même consigne). ») n'est pas une consigne
    consigne = next((j for j in reversed(journal) if j.startswith(CONSIGNES_DU_JOURNAL) and "(même consigne)" not in j),
                    None)
    texte = " ".join(x for x in (objectif, None if consigne is None or consigne == objectif
                                 else "Dernière consigne : " + " ".join(consigne.split())) if x)
    if not texte:
        return None
    return texte if len(texte) <= MAX_RESUME_TACHE else texte[:MAX_RESUME_TACHE - 1] + "…"


def releve_recrutement(ctx, s, fiches):
    """Ce que la partie « Parallélisme du projet » montre pour recruter : les rôles, les places sans agent, le dépôt,
    la raison qui empêche le cloud et la répartition automatique proposée (voir `recrutement.proposer`)."""
    d = rc.depot(_projet(ctx))
    raison = rc.raison_sans_cloud(d)
    places_c = places_cloud_du_projet(ctx)
    reprise_possible = any(x["role"] and x["role"] != "chef" for x in fiches)     # des fiches à l'ancienne
    if rc.a_des_polyvalents(fiches):     # l'équipe suit les places : rien à recruter, ni rôle ni répartition
        return {"polyvalent": True, "reprise_possible": reprise_possible, "roles": [], "places": {"cloud": 0, "locaux": 0}, "propositions": [], "notes": [],
                "propositions_par_lieu": {"mieux": [], "cloud": [], "local": []},
                "notes_par_lieu": {"mieux": [], "cloud": [], "local": []},
                "depot": {"git": d["git"], "github": d["github"], "url": d["url"],
                          "creable": not d["github"] and not d["origine"]},
                "cloud_impossible": raison}
    p = rc.proposer(ctx.f, s, fiches, places_c, d["github"])
    par_lieu = {k: rc.proposer(ctx.f, s, fiches, places_c, d["github"], lieu=k) for k in ("cloud", "local")}
    try:
        essai = json.loads(_fichier_depot(ctx).read_text(encoding="utf-8"))
        essai = {k: essai[k] for k in ("t", "fait", "texte", "url") if k in essai} if isinstance(essai, dict) else None
    except (OSError, ValueError):
        essai = None
    roles = rc.roles_du_projet(ctx.f, fiches)
    return {"roles": [{k: r[k] for k in ("role", "nom", "modele", "agents", "cloud")} | {"travail": p["travail"].get(r["role"], 0)}
                      for r in roles],
            "places": p["places"], "propositions": p["propositions"], "notes": p["notes"],
            "propositions_par_lieu": {"mieux": p["propositions"], "cloud": par_lieu["cloud"]["propositions"],
                                      "local": par_lieu["local"]["propositions"]},
            "notes_par_lieu": {"mieux": p["notes"], "cloud": par_lieu["cloud"]["notes"],
                               "local": par_lieu["local"]["notes"]},
            "depot": {"git": d["git"], "github": d["github"], "url": d["url"],
                      "creable": not d["github"] and not d["origine"], **({"essai": essai} if essai else {})},
            "cloud_impossible": raison, "reprise_possible": reprise_possible}


def cmd_recruter(ctx, e):
    """`{mode: manuel | auto, agents: [{role, modele, lieu, fable?}], lieu?: mieux | cloud | local}` : écrit les fiches des recrues (tout ou rien) ;
    chaque recrue a le prénom libre suivant de l'équipe, le service, le texte et les outils d'une fiche du même rôle,
    et suit le brief du rôle. Cloud : projet sur GitHub et place cloud libre ; auto : jamais au-delà des places."""
    fiches_ = ctx.fiches()
    if rc.a_des_polyvalents(fiches_):
        raise Refus(rc.MESSAGE_EQUIPE_PAR_LES_PLACES)
    try:
        nouvelles = rc.fiches_a_recruter(ctx.f, fiches_, e.get("mode"), e.get("agents"), places_cloud_du_projet(ctx),
                                         rc.depot(_projet(ctx)), su.maintenant()[:10], e.get("lieu"))
    except rc.RecrutementRefuse as ex:
        raise Refus(str(ex))
    ecrites = []
    with ctx.suivi.transaction():     # un seul écrivain à la fois (l'outil et le bureau)
        try:
            for x in nouvelles:
                ecrites.append(x["chemin"])
                fi.ecrire_fiche(x)
            fi.lire_toutes(ctx.f["fiches"])
        except BaseException:
            for c in ecrites:
                Path(c).unlink(missing_ok=True)
            raise
    return {"ok": True, "agents": [{k: x[k] for k in ("cle", "prenom", "role", "modele", "lieu")} for x in nouvelles]}


def cmd_depot(ctx, e):
    """`{action: creer, confirme: true}` : le clic « Créer le dépôt Git » du Directeur (jamais sans lui). Dépôt git
    local si besoin, puis dépôt GitHub privé et poussée (`creation.depot_github`). Le résultat est noté pour le
    bureau et rendu `{fait, url, texte}`."""
    from installation import creation
    if e.get("action") != "creer" or e.get("confirme") is not True:
        raise Refus("« depot » demande action: creer et confirme: vrai (le clic du Directeur).")
    projet = _projet(ctx)
    r = creation.depot_github(projet, rc.nom_de_depot(ctx.f.get("nom") or projet.name), GIT, GH or creation.executer_gh)
    ecrire_json_atomique(_fichier_depot(ctx), {"t": su.maintenant(), **r})
    return r


def lieu_reserve(ctx, role, fiches_):
    """Le lieu que le métier `role` impose (`Lieu : local` ou `cloud` de son brief), seulement dans un projet qui a des
    agents polyvalents (un projet à l'ancienne choisit comme avant) ; `None` sinon, ou si le brief est illisible."""
    if not any(fi.est_polyvalente(x) for x in fiches_) or not isinstance(role, str) or not depart._ROLE_SUR.match(role):
        return None
    try:
        m = metiers.lire_metier(Path(ctx.f["fiches"]) / "briefs", role)
    except (metiers.MetierInvalide, OSError):
        return None
    return m["lieu"] if m and m["lieu"] in ("local", "cloud") else None


MODELE_SANS_METIER = "Sonnet"   # un agent polyvalent, une tâche sans modèle d'étape ni modèle de métier


def modele_du_metier(ctx, role):
    """Le modèle par défaut du métier (`Modèle : …` de son brief), sinon Sonnet."""
    try:
        m = metiers.lire_metier(Path(ctx.f["fiches"]) / "briefs", role) \
            if isinstance(role, str) and depart._ROLE_SUR.match(role) else None
    except (metiers.MetierInvalide, OSError):
        m = None
    return (m or {}).get("modele") or MODELE_SANS_METIER


def cmd_agent_libre(ctx, e):
    role, modele, lieu = texte(e, "role"), texte(e, "modele", obligatoire=False), texte(e, "lieu", obligatoire=False)
    fiches_ = _fiches_avec_sessions(ctx)
    cle, raison = depart.agent_libre(fiches_, ctx.suivi.lire()["taches"], role, modele, lieu,
                                     ctx.f["agents_locaux_max"], lieu_reserve=lieu_reserve(ctx, role, fiches_))
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
    polyvalent = fi.est_polyvalente(fiche_agent)
    roles = list(dict.fromkeys(t.get("role") or fiche_agent["role"] for t in taches))
    genres = list(dict.fromkeys(genre_de_tache(ctx, s, t) for t in taches))   # une tâche, le genre de sa fonctionnalité
    lecons_lot = {"skill": [], "genre": []}
    for g in genres:
        for role in roles:
            lues = memoire.lire(ctx.f["memoire"], g, role)
            for etage in lecons_lot:
                lecons_lot[etage] = _sans_doublon(lecons_lot[etage] + lues[etage])
    glossaire = []
    for t in taches:
        fonc = su.fonctionnalite(s, t["fonctionnalite"]) if t.get("fonctionnalite") else None
        glossaire = _sans_doublon(glossaire + list((fonc or {}).get("glossaire") or []))
    if polyvalent:   # un brief et des leçons par métier du lot
        metiers_ = [_metier_de(ctx, role) for role in roles]
        briefs = [(m["role"], m["texte"] or None) for m in metiers_]
    else:
        metiers_ = None
        briefs = [(role, depart.brief(ctx.f, role)) for role in roles]
    regles, inscrits, ecartes = partenaires_du_depart(ctx, s, taches)
    factory = {**ctx.f, "genre": ", ".join(g for g in genres if g) or None}
    return {"message": depart.message_lot(factory, fiche_agent, taches, briefs, lecons_lot, glossaire, regles,
                                          par_le_moteur=e.get("moteur", False), regles_projet=rp.lire(ctx.f),
                                          inscrits=inscrits, ecartes=ecartes, metiers_=metiers_)}


def cmd_depart(ctx, e):
    if not isinstance(e.get("moteur", False), bool):
        raise Refus("« moteur » est vrai ou faux.")
    if "taches" in e:
        return _depart_d_un_lot(ctx, e)
    cle, i = texte(e, "agent"), texte(e, "tache")
    fiche_agent = fi.trouver(_fiches_avec_sessions(ctx), cle)
    if fiche_agent is None:
        raise Refus(f"Agent inconnu : {cle}")
    tache_suivie = su.tache(ctx.suivi.lire(), i)
    if tache_suivie is None:
        raise Refus(f"Tâche inconnue : {i}")
    s = ctx.suivi.lire()
    fonc = su.fonctionnalite(s, tache_suivie.get("fonctionnalite")) if tache_suivie.get("fonctionnalite") else None
    genre = wf.genre_de(ctx.f, fonc)   # les leçons du genre de la fonctionnalité de la tâche
    metiers_ = None
    if fi.est_polyvalente(fiche_agent):   # spécialiste du métier de la tâche : son brief, ses leçons
        role = tache_suivie.get("role")
        metier = _metier_de(ctx, role)
        brief_du_role = metier["texte"] or None
        metiers_ = [metier]
    else:
        role = fiche_agent["role"]
        brief_du_role = depart.brief(ctx.f, role)
    lecons = memoire.lire(ctx.f["memoire"], genre, role)
    partenaires = partenaires_du_depart(ctx, s, [tache_suivie])
    return {"message": depart.message({**ctx.f, "genre": genre}, fiche_agent, tache_suivie, brief_du_role, lecons,
                                      (fonc or {}).get("glossaire") or [], partenaires[0],
                                      regles_projet=rp.lire(ctx.f), inscrits=partenaires[1], ecartes=partenaires[2],
                                      metiers_=metiers_)}


def cmd_regles(ctx, e):
    """Les règles du projet (`.factory/regles-projet.json`) : `lister`, `ajouter` (texte, origine?), `modifier` (id, texte),
    `supprimer` (id). Seul écrivain du fichier."""
    action = e.get("action")
    if action == "lister":
        return {"regles": rp.lire(ctx.f)}
    if action not in rp.OPERATIONS:
        raise Refus("« action » doit valoir lister, ajouter, modifier ou supprimer.")
    try:
        r, deja = rp.appliquer(ctx.f, action, e.get("id"), e.get("texte"), e.get("origine"))
    except ValueError as ex:
        raise Refus(str(ex))
    return {"regle": r, "deja": deja}


def _partie(t):
    """Une tâche déjà partie : active, faite, déjà prise un moment, ou notée dans un lot (le lot est noté juste avant
    son départ : refaire les lots ne le touche jamais)."""
    return bool(t["active"] or t["colonne"] == "fait" or t.get("debut") or isinstance(t.get("lot"), dict))


def _modele_et_lieu(ctx, s, fiches_, t):
    """(modèle, lieu) de la tâche. Une tâche d'une étape de workflow (ou qui refait le travail d'un rôle) : son modèle
    nécessaire (`modele_necessaire.de_la_tache`, montée comprise, ramené au plafond de son agent ou de l'équipe du
    rôle) et le lieu de l'agent qui la prendrait (le plus petit plafond suffisant). Sinon (cadrage, prototype…) : ceux
    de son agent, sinon de l'agent libre de son rôle (à défaut, d'une fiche du rôle)."""
    m = mn.de_la_tache(ctx.f, t, fiches_, s.get("fonctionnalites") or [])
    reserve = lieu_reserve(ctx, t.get("role"), fiches_)
    f = fi.trouver(fiches_, t["agent"]) if t.get("agent") else None
    if m is not None:
        if f and not fi.est_polyvalente(f):
            return mn.plafonne(m["modele"], f["modele"]), f["lieu"]
        possibles = mn.possibles(fiches_, t.get("role"), m["modele"])
        if f:     # un agent polyvalent : le modèle de la tâche, sans plafond
            return m["modele"], reserve or f["lieu"]
        return (m["modele"], possibles[0]["lieu"] if possibles[0]["role"] else reserve or possibles[0]["lieu"]) \
            if possibles else None
    if f and not fi.est_polyvalente(f):
        return f["modele"], f["lieu"]
    if f:     # un agent polyvalent sans modèle d'étape (cadrage, prototype…) : le modèle du métier, sinon Sonnet
        return modele_du_metier(ctx, t.get("role")), reserve or f["lieu"]
    candidates = [x for x in fiches_ if x["role"] and x["role"] == t.get("role")]
    voulues = [x for x in candidates if x["modele"] == t.get("modele_depart")]
    candidates = voulues or candidates
    if candidates:
        return candidates[0]["modele"], candidates[0]["lieu"]
    polyvalents = [x for x in fiches_ if fi.est_polyvalente(x)]
    if not polyvalents:
        return None
    return modele_du_metier(ctx, t.get("role")), reserve or polyvalents[0]["lieu"]


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
        ml = _modele_et_lieu(ctx, s, fiches_, t)
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


def cmd_fiche(ctx, e):
    """`{"action": "ouvrir_outil", "cle", "outil"}` : ajoute `outil` à la ligne « Outils : » de la fiche de l'agent `cle`
    (la ligne est créée avec les outils par défaut s'il n'y en avait pas). Seule une règle `Bash(<programme>:*)` s'ouvre
    ainsi, jamais `Bash` seul. Rend `{ok, deja, outils}` ; `deja` vrai si la fiche l'ouvrait déjà."""
    if e.get("action") != "ouvrir_outil":
        raise Refus("« action » doit valoir ouvrir_outil.")
    cle, regle = texte(e, "cle"), texte(e, "outil")
    fiche = fi.trouver(ctx.fiches(), cle)
    if fiche is None:
        raise Refus(f"Agent inconnu : {cle}")
    try:
        change = fi.ouvrir_outil(fiche, regle.strip())
    except ValueError as ex:
        raise Refus(str(ex))
    if change:
        fi.ecrire_fiche(fiche)
    return {"ok": True, "deja": not change, "outils": fi.outils(fiche)}


COMMANDES = {
    "fiche": (cmd_fiche, "obligatoire"), "releve": (cmd_releve, "aucune"), "charge": (cmd_charge, "aucune"), "actions": (cmd_actions, "obligatoire"),
    "reveil": (cmd_reveil, "aucune"), "demandes": (cmd_demandes, "aucune"), "guetter": (cmd_guetter, "aucune"),
    "demande-traitee": (cmd_demande_traitee, "obligatoire"), "etat": (cmd_etat, "aucune"),
    "fonctionnalite": (cmd_fonctionnalite, "obligatoire"), "message": (cmd_message, "obligatoire"),
    "decision": (cmd_decision, "obligatoire"), "tache": (cmd_tache, "obligatoire"), "file": (cmd_file, "obligatoire"),
    "file-prendre": (cmd_file_prendre, "obligatoire"), "session": (cmd_session, "obligatoire"),
    "catalogue": (cmd_catalogue, "obligatoire"), "memoire": (cmd_memoire, "obligatoire"),
    "genre": (cmd_genre, "obligatoire"), "lecon": (cmd_lecon, "obligatoire"), "controle": (cmd_controle, "obligatoire"),
    "agent-libre": (cmd_agent_libre, "obligatoire"), "depart": (cmd_depart, "obligatoire"),
    "organisation": (cmd_organisation, "obligatoire"), "lots": (cmd_lots, "obligatoire"), "detail": (cmd_detail, "obligatoire"), "document": (cmd_document, "obligatoire"), "ecrire": (cmd_ecrire, "obligatoire"), "usage": (cmd_usage, "obligatoire"),
    "partenaires": (cmd_partenaires, "obligatoire"), "parallelisme": (cmd_parallelisme, "obligatoire"),
    "recruter": (cmd_recruter, "obligatoire"), "equipe": (cmd_equipe, "aucune"),
    "polyvalents": (cmd_polyvalents, "obligatoire"), "depot": (cmd_depot, "obligatoire"), "regles": (cmd_regles, "obligatoire"),
}


# --- Exécution : en processus, ou par la commande déclarée du projet (`lancer`).

def lancer_declaree(ctx, nom, entree, extra):
    argv = [rel.developper(a) for a in ctx.f["commandes"][nom] + list(extra)]
    corps = None if entree is None else json.dumps(entree, ensure_ascii=False).encode("utf-8")
    env = {**os.environ, "MYIAFACTORY_FACTORY": str(ctx.f["chemin"]), "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run(argv, cwd=str(ctx.f["base"]), input=corps, capture_output=True, env=env,
                           timeout=DELAI_COMMANDE_DECLAREE_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
