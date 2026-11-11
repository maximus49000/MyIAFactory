"""L'agent seul : ce que ferait un néophyte, sans la skill, le bureau ni partenaire.

Une seule conversation `claude -p` (Sonnet 5.5, les outils par défaut de Claude Code, dans une copie vide du projet),
reprise à chaque geste de l'utilisateur de l'essai. Chaque réponse qui attend l'utilisateur (elle se termine par une
question) compte comme une question posée ; le geste suivant du scénario lui est alors donné, comme dans l'essai.
Les appels sont ceux de `moteur.appel` (injectable : aucun appel réel dans les tests).
"""
from moteur import appel
from moteur.agents import OUTILS_PAR_DEFAUT, cumuler

MODELE = "sonnet"
CONSIGNE = ("Tu aides une personne à construire ce qu'elle te demande, dans le dossier de travail. Réponds en "
            "français, simplement. Si tu as besoin d'une précision, pose ta question et attends la réponse.")
VALIDER_LE_CAHIER = "Le cahier des charges me convient, continue."
VALIDER_LA_METHODE = "La méthode me convient, continue avec tous les éléments restants."


def texte_du_geste(demande):
    """Ce que dirait l'utilisateur à cet agent pour ce geste du bureau, ou `None` (un geste qui n'a pas de sens ici)."""
    genre, verdict = demande.get("type"), demande.get("verdict")
    if genre in ("fonctionnalite", "message", "retour", "retour_element"):
        return demande.get("texte")
    if genre == "cahier":
        return demande.get("texte") if verdict == "corriger" else VALIDER_LE_CAHIER
    if genre == "methode":
        return {"valider": VALIDER_LA_METHODE, "reprendre": VALIDER_LA_METHODE}.get(verdict) or demande.get("texte")
    return None


def pose_une_question(texte):
    """Vrai si la réponse attend l'utilisateur : une de ses lignes se termine par un point d'interrogation. Une liste de
    questions finit souvent par « Dites-moi … », sans point d'interrogation : ne regarder que la dernière ligne manquait
    ces questions au passage en vrai."""
    lignes = [x.strip() for x in (texte or "").strip().splitlines() if x.strip()]
    return any(x.rstrip("*_ \"»)").endswith("?") for x in lignes)


def contexte_du_projet(scenario):
    """Ce que l'utilisateur dirait de son projet en commençant : ce que savent les agents du moteur (le nom du projet et
    la description de chaque fiche, sans ses en-têtes ni ses leçons). Sans lui, l'agent seul a compris « badges à
    imprimer » là où le projet faisait des badges Twitch."""
    parties = [f"Mon projet : {scenario.projet['factory'].get('nom') or 'sans nom'}."]
    for texte in (scenario.projet.get("fiches") or {}).values():
        corps = texte.split("## Leçons")[0].split("\n\n", 1)
        if len(corps) == 2 and corps[1].strip():
            parties.append(corps[1].strip())
    return "\n\n".join(parties)


def agent_seul(scenario, dossier_vide, *, appeler=appel.appeler, couche="claude", max_appels=60):
    """Rend `{"appels", "usages", "questions", "reponses", "erreur"}`."""
    session, usages, reponses, questions, appels, erreur = None, [], [], 0, 0, None
    for geste in scenario.gestes:
        texte = texte_du_geste(geste["demande"])
        if not texte or appels >= max_appels:
            continue
        if appels == 0:
            texte = contexte_du_projet(scenario) + "\n\n" + texte
        try:
            r = appeler(CONSIGNE, texte, MODELE, couche=couche, outils=list(OUTILS_PAR_DEFAUT),
                        dossier_travail=str(dossier_vide), reprendre=session)
        except appel.ErreurAppel as e:
            usages += e.usages
            erreur = e.raison
            break
        appels += 1
        usages += r.usages
        session = r.session or session
        reponses.append(r.texte)
        if pose_une_question(r.texte):
            questions += 1
    return {"appels": appels, "usages": cumuler(usages), "questions": questions, "reponses": reponses, "erreur": erreur}
