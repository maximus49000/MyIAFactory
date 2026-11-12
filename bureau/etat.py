"""L'état servi à la page : relevé + équipe + horloge."""
import copy

from . import empreinte as modempreinte
from . import kpi as modkpi
from . import releve as modreleve
from . import statuts


def dossier(r):
    """Ce que le relevé fournit au dossier d'un service (version 3) ; un onglet absent est masqué."""
    if r.get("version", 1) < 3:
        return {"facturation": False, "kpi": False, "connaissances": False}
    return {
        # Des usages, ou une pièce « facturation » (le projet veut voir ses coûts, même avant le premier usage).
        "facturation": bool(r.get("usage")) or any(s.get("id") == "facturation" for s in r["services"]),
        "kpi": any(isinstance(x.get("kpi"), list) for x in r["services"]),
        "connaissances": (isinstance(r.get("challenges"), list)
                          or any(isinstance(t.get("connaissances"), list) or _lecons_validees(t)
                                 for t in r["titulaires"])),
    }


def _lecons_validees(titulaire):
    return [le for le in titulaire.get("lecons") or [] if le.get("etat") == "validée"]


def _connaissances(ti, ids_connaissances):
    """Connaissances du relevé + leçons validées du titulaire (une connaissance l'emporte sur une leçon
    de même id, où qu'elle soit)."""
    sortie = []
    for c in ti.get("connaissances") or []:
        appris = [dict(a) for a in c.get("appris_de") or []]
        sortie.append({"id": c["id"], "texte": c["texte"], "date": c.get("date"), "origine": c.get("origine"),
                       "appris_de": appris, "partagee": bool(appris), "lecon": False,
                       "probleme_revenu": False})
    for le in _lecons_validees(ti):
        if le["id"] not in ids_connaissances:
            sortie.append({"id": le["id"], "texte": le["texte"], "date": le.get("date"),
                           "origine": le.get("tache"), "appris_de": [], "partagee": False, "lecon": True,
                           "probleme_revenu": False})
    return sortie


def _fraicheur(titulaire, defaut):
    v = titulaire.get("fraicheur_min")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return v
    return defaut


def _marquer_problemes_revenus(savoir, r, depuis):
    """Une connaissance dont l'origine est un challenge sur un KPI du projet est marquée quand ce KPI est
    de nouveau en alerte depuis une date postérieure à la sienne. C'est le même objet que dans
    `agents[].connaissances`."""
    ids_services = {s["id"] for s in r["services"]}
    kpi_du_challenge = {}
    for ch in r.get("challenges") or []:
        cible = modkpi.cible_kpi((ch.get("cible") or {}).get("id"), ids_services)             if (ch.get("cible") or {}).get("type") == "kpi" else None
        if cible:
            kpi_du_challenge[ch["id"]] = cible
    for titulaire in savoir:
        for c in titulaire["connaissances"]:
            cible = kpi_du_challenge.get(c.get("origine")) if isinstance(c.get("origine"), str) else None
            if cible:
                c["probleme_revenu"] = modkpi.probleme_revenu(c.get("date"), depuis.get(cible))


ETAPES_DISCUSSION = ("cadrage", "prototype")   # les étapes où l'agent attend les réponses de l'utilisateur


def attend_utilisateur(f):
    """La discussion attend l'utilisateur : le dernier message est d'un agent, la fonctionnalité est en cadrage ou en
    prototype, et aucune décision ne l'attend déjà (elle serait comptée à part)."""
    discussion = f.get("discussion") or []
    if f.get("etape") not in ETAPES_DISCUSSION or not discussion or f.get("decisions"):
        return False
    return message_attend(discussion[-1])


def message_attend(m):
    """Un message d'agent attend une réponse : il pose des questions à choix, ou le dit (`attend`), ou, sans le dire,
    contient une question. Un compte rendu (sans question, ou `attend: false`) n'attend rien."""
    if m.get("auteur") == "utilisateur":
        return False
    if m.get("questions"):
        return True
    if isinstance(m.get("attend"), bool):
        return m["attend"]
    return "?" in str(m.get("texte") or "")


def construire(r, eq, maintenant, fraicheur_min, alertes=None):
    """`alertes` : l'historique des alertes (`kpi.HistoriqueAlertes`). Sans lui, aucune connaissance n'est
    marquée « problème revenu » et rien n'est noté."""
    en_pause = r["factory"].get("etat") == "en pause"
    taches_de = {}
    for t in r["taches"]:
        taches_de.setdefault(t.get("titulaire"), []).append(t)

    agents = []
    presents = set()
    for ti in r["titulaires"]:
        cle = ti["cle"]
        siennes = taches_de.get(cle, [])
        if not statuts.present(ti, siennes, maintenant):
            continue
        presents.add(cle)
        st = statuts.statut(siennes, maintenant, _fraicheur(ti, fraicheur_min), en_pause)
        fiche = eq.agent(cle, chef=bool(ti.get("chef")), prenom=ti.get("prenom") or None)
        agents.append({
            "id": cle,
            "prenom": fiche["prenom"],
            "service": None if ti.get("chef") else ti.get("service"),
            "lieu": ti["lieu"],
            "modele": fiche.get("modele") or ti.get("modele") or "?",
            "couleur": fiche["couleur"],
            "chef": bool(ti.get("chef")),
            "statut": st["statut"],
            "bulle": st["bulle"],
            "taches": [x["id"] for x in siennes if x.get("active")],
            "specialite": ti.get("specialite") or None,
            "lecons": list(ti.get("lecons") or []),
        })

    fiches = {a["id"]: a for a in agents}
    services = {ti["cle"]: (None if ti.get("chef") else ti.get("service")) for ti in r["titulaires"]}
    prenoms = {ti["cle"]: ti.get("prenom") or ti["cle"] for ti in r["titulaires"]}
    prenoms.update({k: a["prenom"] for k, a in fiches.items()})
    titres = {t["id"]: t["titre"] for t in r["taches"]}
    ids_connaissances = {c["id"] for ti in r["titulaires"] for c in ti.get("connaissances") or []}
    savoir = []
    for ti in r["titulaires"]:
        cle = ti["cle"]
        siennes = _connaissances(ti, ids_connaissances)
        if cle in fiches:
            fiches[cle]["connaissances"] = siennes
        elif not siennes:
            continue  # parti sans rien laisser : rien à montrer
        else:
            prenoms[cle] = eq.agent(cle, chef=bool(ti.get("chef")), prenom=ti.get("prenom") or None)["prenom"]
        savoir.append({"agent": cle, "prenom": prenoms[cle], "service": services[cle], "present": cle in fiches,
                       "connaissances": siennes})
    for titulaire in savoir:  # qui a fourni chaque connaissance partagée : prénom, service, titre de la tâche
        for c in titulaire["connaissances"]:
            for a in c["appris_de"]:
                a.update(prenom=prenoms.get(a.get("agent"), a.get("agent")),
                         service=services.get(a.get("agent")), titre=titres.get(a.get("tache")))

    if alertes is not None and r.get("version", 1) >= 3:
        try:
            en_cours = modkpi.suivre_alertes(r, alertes, maintenant)
        except OSError:  # historique des alertes non inscriptible : la marque manque, la scène reste
            en_cours = {}
        _marquer_problemes_revenus(savoir, r, en_cours)

    taches = [{
        "id": t["id"], "titre": t["titre"], "colonne": t["colonne"],
        "agent": t.get("titulaire") if t.get("titulaire") in presents else None,
        "etape": t.get("etape") or "", "maj": t.get("maj"), "postit": t.get("postit", True),
        "active": bool(t.get("active")), "type": t.get("type"),
        "journal": sorted(t.get("journal") or [], key=lambda j: j["t"], reverse=True),
        "images": t.get("images") or [], "liens": t.get("liens") or [],
        "retours": t.get("retours") or [], "notes": t.get("notes") or [], "bloquee": t.get("bloquee") or None,
    } for t in r["taches"]]

    lecons = r.get("lecons") or []
    retours = sum(1 for t in r["taches"] for x in t.get("retours") or []
                  if not (x.get("reponse") or "").strip())
    bloquees = sum(1 for t in r["taches"] if (t.get("bloquee") or "").strip())
    a_juger = sum(1 for le in lecons if not le.get("verdict_demande"))   # un verdict envoyé ne compte plus
    directeur = {"lecons": a_juger, "retours": retours, "bloquees": bloquees,
                 "total": a_juger + retours + bloquees + r["decisions"]}
    v4 = r.get("version", 1) >= 4
    if v4:
        # Une fonctionnalité partie dans un autre projet ne réclame plus rien ici.
        presentes = [f for f in r["fonctionnalites"] if f.get("etape") != "deplacee"]
        directeur["fonctionnalites"] = sum(len(f["decisions"]) for f in presentes)
        directeur["projet"] = len(r["decisions_projet"])
        directeur["reponses"] = sum(1 for f in presentes if attend_utilisateur(f))
        directeur["total"] += directeur["fonctionnalites"] + directeur["projet"] + directeur["reponses"]
        for t, brut in zip(taches, r["taches"]):
            for c in ("fonctionnalite", "element", "modele_depart", "montee", "lot"):
                t[c] = brut.get(c)

    e = {
        "version": r["version"],
        "horodatage": maintenant.isoformat(),
        "projet": r["projet"],
        "erreur": None,
        "factory": statuts.factory(r["factory"], r["taches"], maintenant, fraicheur_min),
        "services": r["services"],
        "colonnes": r["colonnes"],
        "file": r["file"],
        "decisions": r["decisions"],
        "actions": list(r.get("actions") or []),
        "types": list(r.get("types") or []),
        "lecons": list(lecons),
        "directeur": directeur,
        "agents": agents,
        "taches": taches,
        "dossier": dossier(r),
        "challenges": list(r.get("challenges") or []),
        "savoir": savoir,
    }
    if v4:
        e["genre"] = r["genre"]
        e["agents_locaux_max"] = r["agents_locaux_max"]
        e["livrable"] = r["livrable"]
        e["decisions_projet"] = [_avec_empreinte(d) for d in r["decisions_projet"]]
        e["fonctionnalites"] = [_fonctionnalite(f, prenoms, services) for f in r["fonctionnalites"]]
        e["orchestrateur_actif"] = any(a["chef"] and a["statut"] == "travail" for a in agents)
        if isinstance(r.get("orchestrateur_present"), bool):   # absent : l'adaptateur ne le dit pas, rien n'est bloqué
            e["orchestrateur_present"] = r["orchestrateur_present"]
        if r.get("partenaires") is not None:   # l'espace partenaire : rendu tel quel (aucune valeur de clé n'y est)
            e["partenaires"] = copy.deepcopy(r["partenaires"])
    return e


def _avec_empreinte(d):
    """La décision, copiée ; une organisation proposée y gagne l'empreinte estimée de son coût : ses tokens [bas, haut]
    répartis à parts égales entre les étapes (le modèle de l'agent de chaque rôle), un cinquième en sortie. Rien si un
    modèle n'a pas de valeur (jamais de chiffre inventé). Le relevé lu n'est pas modifié."""
    d = dict(d)
    o = d.get("organisation")
    if d.get("genre") != "organisation" or not isinstance(o, dict) or not isinstance(o.get("cout"), dict):
        return d
    modele_du_role = {}
    for a in o.get("agents") or []:
        if isinstance(a, dict):
            modele_du_role.setdefault(a.get("role"), a.get("modele"))
    modeles = [modele_du_role.get(e.get("role")) for e in o.get("flux") or []
               if isinstance(e, dict) and e.get("validation") is not True]
    co2 = modempreinte.plage(o["cout"].get("tokens"), modeles)
    if co2:
        d["organisation"] = dict(o, cout=dict(o["cout"], co2={k: round(v, 4) if isinstance(v, float) else v
                                                              for k, v in co2.items()}))
    return d


def _fonctionnalite(f, prenoms, services):
    """Copie d'une fonctionnalité ; chaque message reçoit le prénom et le service de son auteur
    (`None` pour l'utilisateur)."""
    sortie = copy.deepcopy(f)
    for m in sortie["discussion"]:
        auteur = m.get("auteur")
        m["prenom"] = None if auteur == "utilisateur" else prenoms.get(auteur, auteur)
        m["service"] = None if auteur == "utilisateur" else services.get(auteur)
    return sortie


def erreur(message, maintenant):
    return {
        "version": 1, "horodatage": maintenant.isoformat(), "projet": "", "erreur": message,
        "factory": {"etat": "inconnu", "depuis": None, "derniere_activite": None, "inactive": False},
        "services": [], "colonnes": [], "file": {"visibles": [], "suite": [], "reste": 0}, "decisions": 0,
        "actions": [], "types": [], "lecons": [],
        "directeur": {"lecons": 0, "retours": 0, "bloquees": 0, "total": 0},
        "agents": [], "taches": [],
        "dossier": {"facturation": False, "kpi": False, "connaissances": False},
        "challenges": [], "savoir": [],
    }


def agents_locaux_au_travail(e):
    return sum(1 for a in e["agents"]
               if a["lieu"] == "local" and a["statut"] == "travail" and not a["chef"])


def lire_avec_releve(regl, eq, maintenant, alertes=None):
    """(état, relevé normalisé valide ou None)."""
    r, message = modreleve.obtenir(regl)
    if r is None:
        return erreur(message, maintenant), None
    try:
        return construire(r, eq, maintenant, regl.get("fraicheur_min", 30), alertes), r
    except Exception as e:  # un relevé inattendu ne doit jamais faire tomber le serveur
        return erreur(f"Relevé inutilisable : {e}", maintenant), None


def lire(regl, eq, maintenant):
    return lire_avec_releve(regl, eq, maintenant)[0]
