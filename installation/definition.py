"""L'échange avec le chef avant la création d'un projet : les tours, la proposition calculée, puis la création.

Le chef (jugement `definir_workflow`, Sonnet) pose au plus 4 tours de questions, puis propose un workflow de genre avec
ses agents, ses services et son poste. L'utilisateur peut corriger la proposition (chaque correction est un appel de
plus, hors des 4 tours). Rien n'est écrit dans un projet ni sur le disque, hors le brouillon, avant `valider`.

Un tour dure 30 à 60 secondes : `lancer_tour` marque le brouillon « en cours », répond tout de suite et fait l'appel dans
un fil ; le résultat (ou l'erreur) est écrit dans le brouillon, que la page relit. Un second envoi pendant le tour est
refusé (`brouillons.TourEnCours`). Le calcul d'un tour, lui, est une fonction pure (`tour`).
"""
import copy
import threading
from datetime import datetime

from installation import brouillons, estimation, mise_en_place as mep
from installation.dossier import Echec
from moteur import appel, environnement, jugement

TOURS_MAX = jugement.TOURS_MAX_DEFINITION
LONGUEUR_REPONSE = 2000
LONGUEUR_CORRECTION = 2000
INTERROMPU = ("Le tour précédent a été interrompu (le bureau a été relancé pendant l'appel). Renvoyez-le : "
              "vos réponses sont gardées.")
_FILS = {}      # id du brouillon -> son fil d'arrière-plan (pour les essais)


# --- Le dossier du chef.

def _iso(t):
    return (t or datetime.now()).isoformat(timespec="seconds")


def mots_interdits(infos):
    """Ceux des informations, plus le nom du projet (dès la première fenêtre)."""
    mots = [m.strip() for m in infos.get("mots_interdits") or [] if isinstance(m, str) and m.strip()]
    nom = (infos.get("nom") or "").strip()
    if nom and nom.lower() not in {m.lower() for m in mots}:
        mots.append(nom)
    return mots


def dossier_du_tour(b, *, genres_connus, correction=None, proposer_maintenant=False):
    """Le dossier de `definir_workflow` pour ce brouillon."""
    infos = b["infos"]
    return {"projet": {"nom": infos.get("nom"), "description": infos.get("description"),
                       "facturation": bool(infos.get("facturation")), "github": bool(infos.get("github"))},
            "genres_connus": list(genres_connus), "mots_interdits": mots_interdits(infos),
            "services": [dict(mep.SERVICE_FACTURATION)] if infos.get("facturation") else [],
            "echange": copy.deepcopy(b["echange"]), "tours_de_questions": b["tours"], "tours_max": TOURS_MAX,
            "proposer_maintenant": bool(proposer_maintenant) or b["tours"] >= TOURS_MAX,
            "proposition_precedente": copy.deepcopy(b.get("objet")) if correction else None,
            "correction": correction or None}


def questions_ouvertes(b):
    """Les questions du chef qui attendent une réponse (la dernière entrée de l'échange est la sienne)."""
    dernier = b["echange"][-1] if b["echange"] else None
    if isinstance(dernier, dict) and dernier.get("auteur") == "chef":
        return [q for q in dernier.get("questions") or [] if isinstance(q, dict)]
    return []


def ajouter_reponses(b, reponses):
    """Le brouillon avec les réponses de l'utilisateur ajoutées à l'échange (`[{"question", "texte"}]`, une par
    question ouverte, texte libre ou choix). `Echec` si une réponse ne vise pas une question ouverte."""
    ouvertes = {q["id"] for q in questions_ouvertes(b)}
    if not ouvertes:
        raise Echec("Le chef n'a pas de question en attente.")
    if not isinstance(reponses, list) or not reponses:
        raise Echec("Répondez à au moins une question.")
    vues, propres = set(), []
    for r in reponses:
        if not isinstance(r, dict) or r.get("question") not in ouvertes:
            raise Echec("Une réponse ne correspond à aucune question du chef.")
        texte = r.get("texte")
        if not isinstance(texte, str) or not texte.strip() or len(texte) > LONGUEUR_REPONSE:
            raise Echec(f"Une réponse est vide ou trop longue ({LONGUEUR_REPONSE} caractères au plus).")
        if r["question"] in vues:
            raise Echec("Une question a deux réponses.")
        vues.add(r["question"])
        propres.append({"question": r["question"], "texte": texte.strip()})
    b = copy.deepcopy(b)
    b["echange"].append({"auteur": "utilisateur", "reponses": propres})
    return b


# --- Le coût de l'échange.

def cout_echange(usages, prix_de):
    """{"tokens": int, "euros": float | None} : compteur par compteur ; `None` si le prix d'un modèle est inconnu."""
    usages = [u for u in usages if isinstance(u, dict)]
    tokens = sum(estimation._total(u) for u in usages)
    euros = 0.0
    for u in usages:
        prix = prix_de(u.get("modele"))
        if not prix or not prix.get("entree") or not prix.get("sortie"):
            return {"tokens": tokens, "euros": None}
        euros += estimation._euros_usage(u, prix)
    return {"tokens": tokens, "euros": round(euros, 4)}


# --- La proposition.

def _milliers(n):
    return f"{int(n):,}".replace(",", " ")


def _euros(v):
    return f"{v:.2f}".replace(".", ",")


def proposition_calculee(o, infos, *, verifier_environnement=environnement.verifier, prix_de=lambda modele: None,
                         usages_du_genre=()):
    """La proposition du chef (`o`, déjà validée) complétée en code : le workflow `w-<genre>`, les services et les
    agents à créer (avec l'agent qui installe le poste s'il manque des outils), le poste vérifié, le coût d'un
    élément, et le texte qui l'explique."""
    nouveau = o.get("nouveau")
    genre = {"id": o["genre"], "nouveau": False} if o.get("genre") else \
        {"id": nouveau["id"], "nouveau": True, "description": nouveau["description"]}
    flux = [{"id": x["etape"], "nom": x["nom"], "validation": True} if x.get("validation") is True else
            {"id": x["etape"], "nom": x["nom"], "role": x["role"], "service": x["service"]} for x in o["flux"]]
    raisons = {x["etape"]: x["raison"] for x in o["flux"] if x.get("raison")}
    services = ([dict(mep.SERVICE_FACTURATION)] if infos.get("facturation") else []) + \
        [{"id": s["id"], "nom": s["nom"]} for s in o["services"]]
    agents = [dict(a, lieu="local") for a in o["agents"]]
    briefs = dict(o["briefs"])
    poste = verifier_environnement(list(o.get("environnement") or [])) if o.get("environnement") else []
    regles = list(o.get("outils_installation") or [])
    installateur = None
    if environnement.a_installer(poste):
        agent, brief = environnement.agent_d_installation([], agents, flux, services, regles)
        if agent:
            agents.append(agent)
            briefs[agent["role"]] = brief
            installateur = agent["cle"]
    estime = estimation.estimer(
        flux, [dict(a, modele="Opus" if a["modele"] == "Fable" else a["modele"]) for a in agents],
        list(usages_du_genre), prix_de)
    cout = {"tokens": estime["tokens"], "euros": estime["euros"]}
    p = {"message": o["message"].strip(), "genre": genre, "workflow": {"id": f"w-{genre['id']}", "genre": genre["id"],
                                                                         "flux": flux},
         "raisons": raisons, "services": services, "agents": agents, "briefs": briefs, "livrable": o["livrable"].strip(),
         "environnement": poste, "outils_installation": regles, "installateur": installateur, "cout": cout}
    p["texte"] = texte_de_la_proposition(p)
    return p


def texte_de_la_proposition(p):
    """La proposition expliquée à l'utilisateur : genre, étapes, validations, équipe, poste, coût."""
    g = p["genre"]
    lignes = [p["message"], "",
              (f"Genre : « {g['id']} » (nouveau : {g['description']})." if g["nouveau"]
               else f"Genre : « {g['id']} » (déjà connu).")]
    lignes.append("Étapes, de la demande au livrable :")
    roles = {x["id"]: x for x in p["workflow"]["flux"]}
    for k, e in enumerate(p["workflow"]["flux"], 1):
        qui = "validation du Directeur : vous regardez et vous décidez" if e.get("validation") else \
            f"{e['role']}, service {_nom_du_service(p, e['service'])}"
        raison = p["raisons"].get(e["id"])
        lignes.append(f"{k}. {e['nom']} ({qui})" + (f" : {raison}" if raison else ""))
    lignes.append(f"Livrable : {p['livrable'].rstrip('.')}.")
    if p["agents"]:
        lignes.append("Équipe à recruter :")
        for a in p["agents"]:
            lignes.append(f"- {a.get('prenom') or a['cle']}, {a['role']}, {a['modele']}"
                          + (f" : {a['justification']}" if a.get("justification") else ""))
    en_place = [_outil_en_place(x) for x in p["environnement"] if x.get("etat") == "en_place"]
    manque = [f"{x['outil']} ({x['raison']})" if x.get("raison") else x["outil"]
              for x in p["environnement"] if x.get("etat") != "en_place"]
    if en_place:
        lignes.append("Déjà en place sur le poste : " + ", ".join(en_place) + ".")
    if manque:
        lignes.append("À installer : " + ", ".join(manque) + ".")
    c = p["cout"]
    lignes.append("Coût estimé d'un élément passé par ce workflow : " + f"{_milliers(c['tokens'][0])} à "
                  f"{_milliers(c['tokens'][1])} tokens" + (f", soit {_euros(c['euros'][0])} à {_euros(c['euros'][1])} €."
                                                            if c["euros"] else " (prix inconnu)."))
    return "\n".join(lignes)


def _nom_du_service(p, id_):
    return next((s["nom"] for s in p["services"] if s["id"] == id_), id_)


def _outil_en_place(x):
    return f"{x['outil']} ({x['version']})" if x.get("version") else x["outil"]


# --- Un tour.

def tour(b, *, reponses=None, correction=None, proposer_maintenant=False, genres_connus, couche,
         appeler=appel.appeler, verifier_environnement=environnement.verifier, prix_de=lambda modele: None,
         usages_du_genre=(), maintenant=None):
    """Le brouillon mis à jour par un appel du chef (non écrit). Les `reponses` sont ajoutées à l'échange avant l'appel.
    Tous les usages sont gardés. Questions : le message du chef, un tour de plus. Proposition : calculée, jamais comptée
    dans les 4 tours (une correction est un appel de plus). Jugement raté : `erreur` dit pourquoi, `tours` et
    `proposition` ne bougent pas, et la demande est gardée pour être renvoyée."""
    if reponses is not None:
        b = ajouter_reponses(b, reponses)
    b = copy.deepcopy(b)
    d = jugement.juger("definir_workflow", dossier_du_tour(b, genres_connus=genres_connus, correction=correction,
                                                           proposer_maintenant=proposer_maintenant),
                       couche=couche, appeler=appeler)
    b["usages"] = list(b["usages"]) + [dict(u, t=_iso(maintenant)) for u in d.usages]
    demande = {k: v for k, v in (("correction", correction), ("proposer_maintenant", proposer_maintenant or None)) if v}
    if d.question is not None:
        b["erreur"], b["demande_ratee"] = d.question, demande or None
        return b
    b["erreur"], b["demande_ratee"] = None, None
    o = d.objet
    if correction:
        b["echange"].append({"auteur": "utilisateur", "correction": correction})
    if o["type"] == "questions":
        b["echange"].append({"auteur": "chef", "message": o["message"].strip(), "questions": o["questions"]})
        b["tours"] += 1
        return b
    b["echange"].append({"auteur": "chef", "message": o["message"].strip()})
    b["objet"] = o
    b["proposition"] = proposition_calculee(o, b["infos"], verifier_environnement=verifier_environnement,
                                            prix_de=prix_de, usages_du_genre=usages_du_genre)
    return b


# --- Le tour en arrière-plan.

def lancer_tour(id_, *, reponses=None, correction=None, proposer_maintenant=False, genres_connus, couche,
                appeler=appel.appeler, verifier_environnement=environnement.verifier, prix_de=lambda modele: None,
                usages_du_genre=(), dossier=None, en_arriere=True, maintenant=None):
    """Prépare un tour et le lance, puis rend tout de suite le brouillon (écrit) marqué « en cours » : les réponses y
    sont déjà. Le résultat, ou l'erreur, y sera écrit à la fin (la page relit le brouillon). Sans `en_arriere`, le tour
    se fait avant de rendre (essais). `Echec` : demande impossible, rien n'est lancé ; `brouillons.TourEnCours` : un
    tour tourne déjà, rien n'est compté deux fois. Sans nouvelle demande, un tour interrompu ou raté est refait avec
    la sienne."""
    if isinstance(correction, str):
        correction = correction.strip() or None
        if correction and len(correction) > LONGUEUR_CORRECTION:
            raise Echec(f"La correction est trop longue ({LONGUEUR_CORRECTION} caractères au plus).")
    elif correction is not None:
        raise Echec("La correction est un texte.")
    with brouillons._VERROU:
        b = brouillons.lire(id_, dossier=dossier)
        if brouillons.etat_du_tour(b) == "en_cours":
            raise brouillons.TourEnCours()
        demande = {k: v for k, v in (("correction", correction), ("proposer_maintenant", bool(proposer_maintenant)))
                   if v}
        effective = (demande or dict(b.get("demande_ratee") or {})
                     or {k: v for k, v in (b.get("en_cours") or {}).items() if k != "depuis"})
        if b.get("proposition") and not effective.get("correction"):
            raise Echec("Une proposition est prête : validez-la, ou dites au chef ce qu'il faut corriger.")
        if effective.get("correction") and not b.get("proposition"):
            raise Echec("Il n'y a pas encore de proposition à corriger.")
        if reponses is not None:
            b = ajouter_reponses(b, reponses)
        elif questions_ouvertes(b) and not effective.get("proposer_maintenant"):
            raise Echec("Répondez aux questions du chef, ou demandez-lui sa proposition.")
        b["demande_ratee"] = None
        brouillons.ecrire(b, dossier=dossier, maintenant=maintenant)
        marque = brouillons.commencer_tour(id_, effective, dossier=dossier, maintenant=maintenant)
    reglages = dict(genres_connus=genres_connus, couche=couche, appeler=appeler,
                    verifier_environnement=verifier_environnement, prix_de=prix_de, usages_du_genre=usages_du_genre)
    if not en_arriere:
        _executer(id_, dossier, maintenant, reglages)
        return brouillons.lire(id_, dossier=dossier)
    fil = threading.Thread(target=_executer, args=(id_, dossier, maintenant, reglages), daemon=True,
                           name=f"tour-{id_}")
    _FILS[id_] = fil
    fil.start()
    return marque


def _executer(id_, dossier, maintenant, reglages):
    """Le corps du fil : l'appel, puis le brouillon écrit sans `en_cours` ; rien ne reste « en cours » quoi qu'il arrive."""
    resultat = None
    try:
        b = brouillons.lire(id_, dossier=dossier)
        demande = b.get("en_cours") or {}
        try:
            resultat = tour(b, correction=demande.get("correction"),
                            proposer_maintenant=bool(demande.get("proposer_maintenant")), maintenant=maintenant,
                            **reglages)
        except Exception as e:     # un échec imprévu ne laisse pas le brouillon bloqué, ni la page sans réponse
            resultat = copy.deepcopy(b)
            resultat["erreur"] = f"Le tour a échoué ({type(e).__name__}) : {e}"[:300]
            resultat["demande_ratee"] = {k: v for k, v in demande.items() if k != "depuis"} or None
    except Exception:
        resultat = None
    finally:
        brouillons.finir_tour(id_, resultat, dossier=dossier, maintenant=maintenant)
        _FILS.pop(id_, None)


def attendre(id_, delai_s=30):
    """Attend la fin du tour d'arrière-plan de ce brouillon (essais). Vrai si plus rien ne tourne."""
    fil = _FILS.get(id_)
    if fil is not None:
        fil.join(delai_s)
    return not (fil is not None and fil.is_alive())


# --- Ce que la page lit.

def vue(b, prix_de=lambda modele: None):
    """Le brouillon tel que la page le lit : {id, infos, echange, tours, tours_max, proposition, erreur, cout, tour,
    en_cours}. `tour` : `libre`, `en_cours` (un appel tourne : relire dans quelques secondes) ou `interrompu` (le
    bureau a été relancé pendant l'appel : le renvoyer suffit). L'`erreur` d'un tour interrompu le dit."""
    etat = brouillons.etat_du_tour(b)
    erreur = b.get("erreur")
    if etat == "interrompu" and not erreur:
        erreur = INTERROMPU
    return {"id": b["id"], "infos": b["infos"], "echange": b["echange"], "tours": b["tours"], "tours_max": TOURS_MAX,
            "proposition": b.get("proposition"), "erreur": None if etat == "en_cours" else erreur,
            "cout": cout_echange(b.get("usages") or [], prix_de), "tour": etat,
            "en_cours": b.get("en_cours") if etat == "en_cours" else None}
