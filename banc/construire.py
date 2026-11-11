"""Construire le scénario d'un essai réel, à partir de son suivi, du journal de ses demandes et des transcriptions de
ses sous-agents. Le scénario **n'est jamais écrit dans le dépôt** : il contient le projet de l'essai (`ErreurBanc`).

Ce qu'il reprend :
- `gestes` : chaque demande du bureau rejouable (`demandes.jsonl`), dans l'ordre ; la première part tout de suite, les
  autres quand le moteur attend l'utilisateur. Les identifiants de fonctionnalité sont renumérotés (`f1`, `f2`…) comme
  le fera le moteur ; une image jointe est reprise en base64 si son fichier existe encore, sinon elle est laissée de côté ;
- `rapports` : le texte final de chaque sous-agent (sa dernière réponse) et son usage exact, rangés par (étape, rôle,
  rang). La tâche se retrouve dans son message de départ (« - Tâche : <titre> (<id>) »), l'étape se déduit de la
  tâche : colonne `cadrage` → `cadrage` ; rôle `relecteur` → `relecture` ; titre commençant par « Correction » ou
  « Retour » → `correction` ; élément de rang 0 → `prototype` ; sinon `flux:<étape du flux de son rôle>`. Un rapport de relecture dont le
  texte parle d'un défaut devient un verdict non conforme (ses puces en points) : c'est une heuristique, pas une lecture
  fine ;
- `projet` : les services, le flux, les fiches et les briefs de l'essai ;
- `attendu` : ce que le suivi montre d'obtenu (cahier validé, méthode, éléments faits, corrections, leçons).
"""
import base64
import json
import re
from pathlib import Path

from banc.scenario import RACINE, Scenario
from orchestrateur import factory as fa
from orchestrateur import suivi as su
from orchestrateur import transcriptions

REJOUABLES = ("fonctionnalite", "message", "cahier", "methode", "genre", "organisation", "lecon", "retour")
ROLE_RELECTURE = "relecteur"
_TACHE = re.compile(r"- Tâche : .*?\((t\d+)\)")
_DEFAUT = re.compile(r"refus|défaut|a corriger|à corriger|non conforme|problème", re.I)
_PUCE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")
MAX_POINTS = 5
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


def _etape(t, rang, flux):
    """L'étape du scénario d'une tâche. Une tâche faite est dans la colonne « fait » : son étape de flux se retrouve par
    son rôle (la première étape du flux qui a ce rôle)."""
    titre = (t.get("titre") or "").lower()
    if t.get("colonne") == "cadrage" or titre.startswith("cadrage"):
        return "cadrage"
    if t.get("role") == ROLE_RELECTURE:
        return "relecture"
    if titre.startswith(("correction", "retour")):
        return "correction"
    if rang == 0 and t.get("element") is not None:
        return "prototype"
    etape = next((s["id"] for s in flux if s["role"] == t.get("role")), None)
    return f"flux:{etape or flux[0]['id']}"


def _usage_principal(fichier):
    par_modele = transcriptions.compter(fichier)
    if not par_modele:
        return {"modele": "inconnu", "entree": 0, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0}
    modele = max(par_modele, key=lambda m: sum(par_modele[m].values()))
    return {"modele": modele, **par_modele[modele]}


def _rapport_structure(etape, element, texte):
    brut = {"statut": "fait", "message": {"texte": texte[:MAX_TEXTE], "attend": etape in ("cadrage", "prototype")}}
    if etape == "relecture" and element is not None:
        points = [m.group(1) for ligne in texte.splitlines() if (m := _PUCE.match(ligne))][:MAX_POINTS]
        refus = bool(_DEFAUT.search(texte)) and bool(points)
        brut["verdicts"] = [{"element": element, "conforme": not refus, "points": points if refus else []}]
    return brut


def _rapports(factory, suivi, dossier_transcriptions):
    taches, rangs, rapports = {t["id"]: t for t in suivi["taches"]}, _rangs(suivi), []
    for fichier in sorted(Path(dossier_transcriptions).glob("**/subagents/agent-*.jsonl")):
        lignes = _lignes_json(fichier)
        premier = next((_texte_du_message(d.get("message")) for d in lignes if d.get("type") == "user"), "")
        m = _TACHE.search(premier)
        t = taches.get(m.group(1)) if m else None
        final = next((_texte_du_message(d.get("message")) for d in reversed(lignes) if d.get("type") == "assistant"
                      and _texte_du_message(d.get("message")).strip()), "")
        if t is None or not final.strip():
            continue
        rang = rangs.get(t["id"], 0)
        etape = _etape(t, rang, factory["flux"])
        rapports.append({"etape": etape, "role": t.get("role") or "", "rang": rang, "texte": final[:MAX_TEXTE],
                         "fichiers": [], "usage": _usage_principal(fichier),
                         "rapport": _rapport_structure(etape, t.get("element"), final), "_ordre": t["id"]})
    rapports = [r for r in rapports if r["role"]]
    rapports.sort(key=lambda r: int(re.sub(r"\D", "", r.pop("_ordre")) or 0))
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
