"""Construire le scénario d'un essai réel, à partir de son suivi, du journal de ses demandes et des transcriptions de
ses sous-agents. Le scénario **n'est jamais écrit dans le dépôt** : il contient le projet de l'essai (`ErreurBanc`).

Ce qu'il reprend :
- `gestes` : chaque demande du bureau rejouable (`demandes.jsonl`), dans l'ordre ; la première part tout de suite, les
  autres quand le moteur attend l'utilisateur. Les identifiants de fonctionnalité sont renumérotés (`f1`, `f2`…) comme
  le fera le moteur. L'orchestrateur actuel posait certaines décisions en question dans la discussion : une réponse
  « … → Valider la méthode … » devient le geste `methode` (`valider`) que le bureau envoie au moteur. Un `retour` sur une
  tâche est écarté : l'identifiant d'une tâche de l'essai ne désigne rien dans le moteur ; une image jointe est reprise en base64 si son fichier existe encore, sinon elle est laissée de côté ;
- `rapports` : le texte final de chaque sous-agent (ce qu'il a rendu par `SubagentHandback`, sinon sa dernière
  réponse) et son usage exact, rangés par (étape, rôle, rang), dans l'ordre de leur départ. La tâche se retrouve dans
  son message de départ, complété du fichier `depart_*.md` qu'il cite : « - Tâche : <titre> (<id>) », sinon le premier
  identifiant de tâche connu (« tâche t2 », la liste d'un lot : le lot est rangé sous sa première tâche), sinon, si le
  message parle de l'agent de cadrage, la tâche de cadrage. Le rôle est celui que le départ donne (« Rôle : … »,
  « Tu es le … »), sinon celui de la tâche (une tâche passée dans le flux a pris le rôle de l'étape suivante). L'étape :
  tâche de cadrage → `cadrage` (rôle `cadrage`, comme le moteur) ; rôle `relecteur` → `relecture` ; titre commençant
  par « Correction » ou « Retour » → `correction` ; élément de rang 0 au rôle de la première étape → `prototype` ;
  sinon `flux:<étape du flux de son rôle>`. Une réponse en JSON (`texte`, `questions`, `glossaire`, `maquette`,
  `etapes`) devient le message et le cahier du rapport. Sans relecteur dans l'essai, un rapport de la dernière étape
  du flux (le contrôle, qui en tient lieu dans le moteur) reçoit un verdict par élément qu'il couvre : non conforme si
  une ligne qui cite l'élément parle d'un échec (FAIL, non conforme, refusé). Un rapport de relecture dont le texte parle d'un défaut devient
  un verdict non conforme (ses puces en points) : c'est une heuristique, pas une lecture fine ;
- `projet` : les services, le flux, les fiches et les briefs de l'essai ;
- `attendu` : ce que le suivi montre d'obtenu (cahier validé, méthode, éléments faits, corrections, leçons).
"""
import base64
import json
import re
import unicodedata
from pathlib import Path

from banc.scenario import RACINE, Scenario
from orchestrateur import factory as fa
from orchestrateur import suivi as su
from orchestrateur import transcriptions

REJOUABLES = ("fonctionnalite", "message", "cahier", "methode", "genre", "organisation", "lecon")
_VALIDER_METHODE = re.compile(r"→\s*valider la méthode", re.I)
ROLE_RELECTURE = "relecteur"
_TACHE = re.compile(r"- Tâche : .*?\((t\d+)\)")
_TACHE_LIBRE = re.compile(r"\b(t\d+)\b")
_DEPART = re.compile(r"(?:[A-Za-z]:)?[^\s«»\"'`(]*?depart_[\w-]+\.md")
_CADRAGE = re.compile(r"agent de cadrage", re.I)
_ROLE = re.compile(r"^Rôle : *(\S.*?) *$", re.M)
_TU_ES = re.compile(r"tu es (?:le |la |l')([\w-]+)")
ROLE_CADRAGE = "cadrage"
RENDU = "SubagentHandback"
_DEFAUT = re.compile(r"refus|défaut|a corriger|à corriger|non conforme|problème", re.I)
_PUCE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")
_ECHEC = re.compile(r"\bFAIL\b|non conforme|refusé", re.I)
MAX_POINTS = 5
MAX_POINT = 300
MAX_TEXTE = 4000


class ErreurBanc(Exception):
    """Une opération du banc refusée (chemin, donnée manquante)."""


def refuser_dans_le_depot(chemin):
    """Les données d'un essai réel restent hors du dépôt public."""
    c = Path(chemin).expanduser().resolve()
    if c == RACINE or RACINE in c.parents:
        raise ErreurBanc(f"« {chemin} » est dans le dépôt : les données d'un essai réel restent hors du dépôt "
                         "(par exemple sous ~/MyIAFactory/bancs/).")
    return c


def _lignes_json(chemin):
    sortie = []
    try:
        with open(chemin, encoding="utf-8", errors="replace") as f:
            for brut in f:
                try:
                    d = json.loads(brut)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    sortie.append(d)
    except OSError:
        pass
    return sortie


def _texte_du_message(m):
    c = m.get("content") if isinstance(m, dict) else None
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _gestes(factory, suivi):
    ids, gestes = {}, []
    for d in _lignes_json(factory["suivi"].with_name("demandes.jsonl")):
        if d.get("type") not in REJOUABLES:
            continue
        e = {k: v for k, v in d.items() if k not in ("id", "statut", "reponse", "t", "images", "donnees")}
        if d["type"] == "fonctionnalite":
            ids[d.get("fonctionnalite")] = f"f{len(ids) + 1}"
            e.pop("fonctionnalite", None)
        elif e.get("fonctionnalite") is not None:
            e["fonctionnalite"] = ids.get(e["fonctionnalite"], e["fonctionnalite"])
        if "cible" in e:
            e["id"] = e.pop("cible")
        if e["type"] == "message" and _VALIDER_METHODE.search(e.get("texte") or "") and e.get("fonctionnalite"):
            e = {"type": "methode", "fonctionnalite": e["fonctionnalite"], "verdict": "valider"}
        images = []
        for chemin in d.get("images") or []:
            fichier = factory["base"] / str(chemin)
            if isinstance(chemin, str) and fichier.is_file():
                nom = fichier.name
                images.append({"nom": nom, "type": "image/png" if nom.lower().endswith(".png") else "image/jpeg",
                               "donnees": base64.b64encode(fichier.read_bytes()).decode()})
        if images:
            e["images"] = images
        gestes.append({"apres": "immediat" if not gestes else "attente_utilisateur", "demande": e})
    return gestes


def _rangs(suivi):
    """{tâche: rang de son élément dans sa fonctionnalité} : l'ordre où les éléments paraissent dans les tâches."""
    rangs, vus = {}, {}
    for t in sorted(suivi["taches"], key=lambda t: int(re.sub(r"\D", "", t["id"]) or 0)):
        if t.get("element") is None:
            rangs[t["id"]] = 0
            continue
        ordre = vus.setdefault(t.get("fonctionnalite"), {})
        rangs[t["id"]] = ordre.setdefault(t["element"], len(ordre))
    return rangs


def _est_cadrage(t):
    return t.get("colonne") == "cadrage" or t.get("etape") == "cadrage" or (t.get("titre") or "").lower().startswith(
        "cadrage")


def _etape(t, rang, flux, role=None):
    """L'étape du scénario d'une tâche, faite par `role` (défaut : le rôle de la tâche). Une tâche faite est dans la
    colonne « fait » : son étape de flux se retrouve par le rôle (la première étape du flux qui a ce rôle)."""
    role = role or t.get("role")
    titre = (t.get("titre") or "").lower()
    if _est_cadrage(t):
        return "cadrage"
    if role == ROLE_RELECTURE:
        return "relecture"
    if titre.startswith(("correction", "retour")):
        return "correction"
    production = [s for s in flux if s["role"] != ROLE_RELECTURE] or flux
    if rang == 0 and t.get("element") is not None and role == production[0]["role"]:
        return "prototype"
    etape = next((s["id"] for s in flux if s["role"] == role), None)
    return f"flux:{etape or flux[0]['id']}"


def _sans_accents(texte):
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()


def _final(lignes):
    """Ce que le sous-agent a rendu : le message de son dernier `SubagentHandback`, sinon son dernier texte."""
    for d in reversed(lignes):
        if d.get("type") != "assistant":
            continue
        c = (d.get("message") or {}).get("content")
        for b in reversed(c if isinstance(c, list) else []):
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == RENDU:
                texte = (b.get("input") or {}).get("message")
                if isinstance(texte, str) and texte.strip():
                    return texte
    return next((_texte_du_message(d.get("message")) for d in reversed(lignes) if d.get("type") == "assistant"
                 and _texte_du_message(d.get("message")).strip()), "")


def _depart_complet(premier, factory):
    """Le message de départ, suivi du contenu des fichiers `depart_*.md` qu'il cite (quand ils existent encore)."""
    textes = [premier]
    for m in _DEPART.finditer(premier):
        nom = Path(m.group(0).replace("\\", "/"))
        for chemin in (nom, Path(factory["pieces"]) / nom.name, Path(factory["base"]) / nom.name):
            try:
                if chemin.is_file():
                    textes.append(chemin.read_text(encoding="utf-8-sig"))
                    break
            except OSError:
                continue
    return "\n".join(textes)


def _tache_du_depart(texte, taches):
    m = _TACHE.search(texte)
    if m and m.group(1) in taches:
        return taches[m.group(1)]
    for m in _TACHE_LIBRE.finditer(texte):
        if m.group(1) in taches:
            return taches[m.group(1)]
    if _CADRAGE.search(texte):
        return next((t for t in taches.values() if _est_cadrage(t)), None)
    return None


def _role_du_depart(texte, t, roles):
    m = _ROLE.search(texte)
    if m and m.group(1) in roles:
        return m.group(1)
    for m in _TU_ES.finditer(_sans_accents(texte)):
        if m.group(1) in roles:
            return m.group(1)
    return t.get("role") or ""


def _heure(lignes):
    return next((d["timestamp"] for d in lignes if isinstance(d.get("timestamp"), str)), "")


def _usage_principal(fichier):
    par_modele = transcriptions.compter(fichier)
    if not par_modele:
        return {"modele": "inconnu", "entree": 0, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0}
    modele = max(par_modele, key=lambda m: sum(par_modele[m].values()))
    return {"modele": modele, **par_modele[modele]}


def _element_cite(element):
    return re.compile(r"(?<![\w-])" + re.escape(element) + r"(?![\w-])")


def _verdicts_du_controle(texte, elements):
    """Les verdicts d'un rapport de contrôle (la dernière étape d'un flux sans relecteur) : un élément est non conforme
    si une ligne qui le cite parle d'un échec (FAIL, non conforme, refusé) ; ces lignes sont ses points."""
    verdicts = []
    for e in elements:
        cite = _element_cite(e)
        lignes = [x.strip()[:MAX_POINT] for x in texte.splitlines() if cite.search(x) and _ECHEC.search(x)]
        verdicts.append({"element": e, "conforme": not lignes, "points": lignes[:MAX_POINTS]})
    return verdicts


def _elements_du_depart(texte, taches, premiere):
    """Les éléments que couvre un départ : ceux des tâches qu'il cite (un lot), dans l'ordre, sinon celui de sa tâche."""
    vus = []
    for m in _TACHE_LIBRE.finditer(texte):
        e = (taches.get(m.group(1)) or {}).get("element")
        if e is not None and e not in vus:
            vus.append(e)
    return vus or ([premiere["element"]] if premiere.get("element") is not None else [])


def _rapport_structure(etape, element, texte):
    brut = {"statut": "fait", "message": {"texte": texte[:MAX_TEXTE], "attend": etape in ("cadrage", "prototype")}}
    try:
        objet = json.loads(texte.strip()) if texte.strip().startswith("{") else None
    except ValueError:
        objet = None
    if isinstance(objet, dict) and isinstance(objet.get("texte"), str) and objet["texte"].strip():
        brut["message"]["texte"] = objet["texte"][:MAX_TEXTE]
        for cle in ("questions", "glossaire"):
            if isinstance(objet.get(cle), list) and objet[cle]:
                brut["message"][cle] = objet[cle]
        maquette, etapes = objet.get("maquette"), objet.get("etapes")
        if (isinstance(maquette, list) and maquette and all(isinstance(x, str) and x.strip() for x in maquette)
                and isinstance(etapes, list) and etapes and all(isinstance(x, str) and x.strip() for x in etapes)):
            brut["cahier"] = {"maquette": maquette, "etapes": etapes}
    if etape == "relecture" and element is not None:
        points = [m.group(1) for ligne in texte.splitlines() if (m := _PUCE.match(ligne))][:MAX_POINTS]
        refus = bool(_DEFAUT.search(texte)) and bool(points)
        brut["verdicts"] = [{"element": element, "conforme": not refus, "points": points if refus else []}]
    return brut


def _avec_rangs(brut, rang_de):
    """Chaque verdict porte le rang de son élément : le rejoueur le rend à l'élément du moteur de même rang."""
    for v in brut.get("verdicts") or []:
        if v["element"] in rang_de:
            v["rang"] = rang_de[v["element"]]
    return brut


def _rapports(factory, suivi, dossier_transcriptions):
    taches, rangs, rapports = {t["id"]: t for t in suivi["taches"]}, _rangs(suivi), []
    roles = {s["role"] for s in factory["flux"]} | {t.get("role") for t in suivi["taches"] if t.get("role")}
    production = [s for s in factory["flux"] if s["role"] != ROLE_RELECTURE] or factory["flux"]
    sans_relecteur = ROLE_RELECTURE not in roles
    fichiers = [(f, _lignes_json(f)) for f in sorted(Path(dossier_transcriptions).glob("**/subagents/agent-*.jsonl"))]
    fichiers.sort(key=lambda x: _heure(x[1]))      # l'ordre des départs (le nom d'un fichier est un hasard)
    for fichier, lignes in fichiers:
        premier = next((_texte_du_message(d.get("message")) for d in lignes if d.get("type") == "user"), "")
        depart = _depart_complet(premier, factory)
        t = _tache_du_depart(depart, taches)
        final = _final(lignes)
        if t is None or not final.strip():
            continue
        rang = rangs.get(t["id"], 0)
        role = ROLE_CADRAGE if _est_cadrage(t) else _role_du_depart(depart, t, roles)
        etape = _etape(t, rang, factory["flux"], role)
        brut = _rapport_structure(etape, t.get("element"), final)
        if sans_relecteur and len(production) > 1 and etape == "flux:" + production[-1]["id"]:
            brut["verdicts"] = _verdicts_du_controle(final, _elements_du_depart(depart, taches, t))
        _avec_rangs(brut, {x["element"]: rangs[x["id"]] for x in taches.values()
                           if x.get("element") is not None and x.get("fonctionnalite") == t.get("fonctionnalite")})
        rapports.append({"etape": etape, "role": role, "rang": rang, "texte": final[:MAX_TEXTE],
                         "fichiers": [], "usage": _usage_principal(fichier), "rapport": brut, "_ordre": t["id"]})
    rapports = [r for r in rapports if r["role"]]
    rapports.sort(key=lambda r: int(re.sub(r"\D", "", r.pop("_ordre")) or 0))     # stable : départs dans l'ordre
    return rapports


def _attendu(suivi, gestes):
    attendu = []
    for f in suivi["fonctionnalites"]:
        corrections = sum(1 for g in gestes if g["demande"].get("type") == "cahier"
                          and g["demande"].get("verdict") == "corriger")
        if (f.get("cahier") or {}).get("valide_le"):
            attendu.append("Le cahier est validé" + (f" après {corrections} correction(s)" if corrections else ""))
        if (f.get("methode") or {}).get("validee_le"):
            attendu.append("La méthode est écrite et validée")
    faits = {(t.get("fonctionnalite"), t["element"]) for t in suivi["taches"]
             if t.get("element") and t["colonne"] == "fait" and not (t.get("titre") or "").lower().startswith("correction")}
    if faits:
        attendu.append(f"{len(faits)} élément(s) livré(s)")
    if any((t.get("titre") or "").lower().startswith("correction") for t in suivi["taches"]):
        attendu.append("Un élément refusé est corrigé")
    if suivi.get("lecons"):
        attendu.append(f"{len(suivi['lecons'])} leçon(s) notée(s)")
    return attendu


def construire(dossier_factory, transcriptions_, sortie):
    """Écrit `sortie` (un fichier `.json`, ou un dossier qui reçoit `scenario.json`) et rend son chemin. `dossier_factory` :
    le dossier du fichier de factory de l'essai (`.factory/`) ; `transcriptions_` : le dossier des transcriptions de
    la session orchestratrice (`~/.claude/projects/<dossier>/<session>/`)."""
    cible = refuser_dans_le_depot(sortie)
    chemin = Path(dossier_factory) / "factory.json"
    try:
        factory = fa.lire(chemin)
    except fa.FactoryInvalide as e:
        raise ErreurBanc(str(e))
    suivi = su.Suivi(factory["suivi"]).lire()
    gestes = _gestes(factory, suivi)
    if not gestes:
        raise ErreurBanc("Le journal des demandes de l'essai est vide ou introuvable (demandes.jsonl à côté du suivi).")
    fiches = {p.name: p.read_text(encoding="utf-8-sig") for p in sorted(Path(factory["fiches"]).glob("*.md"))}
    briefs_dossier = Path(factory["fiches"]) / "briefs"
    briefs = {p.stem: p.read_text(encoding="utf-8-sig") for p in sorted(briefs_dossier.glob("*.md"))} \
        if briefs_dossier.is_dir() else {}
    donnees = {
        "version": 1,
        "projet": {"factory": {"nom": factory["nom"], "services": factory["services"], "flux": factory["flux"],
                               "seuil_methode": factory["seuil_methode"],
                               "agents_locaux_max": factory["agents_locaux_max"]},
                   "fiches": fiches, "briefs": briefs, "reglages": {}},
        "gestes": gestes, "rapports": _rapports(factory, suivi, transcriptions_),
        "attendu": _attendu(suivi, gestes),
        "essai": {"questions": sum(1 for f in suivi["fonctionnalites"] for m in f["discussion"]
                                   if m["auteur"] != "utilisateur" and m.get("attend") is True)},
    }
    Scenario(donnees)     # le format est contrôlé avant d'écrire
    fichier = cible if cible.suffix == ".json" else cible / "scenario.json"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(donnees, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return fichier
