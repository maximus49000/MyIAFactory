"""Lancer un agent de production sans fenêtre : un `claude -p` avec ses outils, dans le dossier du projet.

`executer_agent` est synchrone (la boucle le met dans un fil). Le message est celui que rend `lancer depart`, suivi de
la matière de la tâche. L'agent rend un rapport structuré (`rapport.lire`) ; sans rapport lisible (sortie libre, coupée,
code d'erreur, délai), il est relancé une fois, puis l'`Execution` porte l'`erreur` (la tâche passe bloquée). Ce que
chaque appel a coûté est gardé, réussi ou non : la boucle note chaque usage. Jamais le mode qui contourne les
autorisations. Fable : seulement pour un agent dont la fiche porte l'accord du Directeur (`fiches.fable_accorde`), pour
cet agent seulement ; jamais choisi par le moteur (montée de modèle, jugements).
"""
from moteur import appel, rapport
from orchestrateur import fiches

OUTILS_PAR_DEFAUT = fiches.OUTILS_PAR_DEFAUT
DELAI_AGENT_S = 1800
ESSAIS = 2
CONSIGNE_AGENT = ("Tu es un agent de production d'un projet. Ton message de départ dit qui tu es, ce que tu dois faire "
                  "et comment rendre compte. Travaille dans le dossier du projet avec les seuls outils qui te sont "
                  "ouverts. Personne ne peut approuver une commande pendant que tu travailles : écris chaque fichier "
                  "(scripts compris) avec l'outil Write, jamais par le shell (`cat >`, `<<EOF`, `echo >`), puis "
                  "lance tes scripts par `python <chemin>.py` ; une commande refusée, reformule-la ainsi. Un outil "
                  "qui reste refusé n'est pas une raison de chercher à le contourner : dis-le dans ton rapport "
                  "(statut outil_refuse). Chaque image que tu rends porte sa légende, une phrase qui dit à quoi elle "
                  "correspond. Un avis ou un accord de l'utilisateur se demande en `message.questions` à choix avec "
                  "`attend: true`, jamais en simple phrase. Avant une action qui ouvre une fenêtre sur le poste "
                  "(pare-feu, UAC, pilote, débogage USB), dis dans `message.texte` laquelle, pourquoi et quoi "
                  "choisir, avec `attend: true`, et n'agis qu'après la réponse ; ne réponds jamais à ces fenêtres "
                  "à sa place ; une commande bloquée par une fenêtre se dit dans ton rapport. Termine par le bloc ```json demandé.")
USAGE_VIDE = {"modele": "", "entree": 0, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0}


class Execution:
    """Le résultat d'un agent : `rapport` (lu) ou `erreur` (jamais les deux), `usages` (un par modèle, tous les appels
    cumulés), `usage` (le principal), `tache` et `lot` (ce que l'agent servait)."""

    def __init__(self, tache, agent, lot=None, rapport=None, usages=None, erreur=None, estime=None, modele=None,
                 session=None, refus=None):
        self.tache, self.agent, self.lot, self.rapport, self.erreur = tache, agent, lot, rapport, erreur
        self.estime = estime      # un agent cloud : le total de tokens qu'il déclare (une estimation, pas une mesure)
        self.modele = modele      # le modèle demandé (« haiku », « sonnet », « opus »)
        self.session = session    # la session `claude -p` (local) : une question de l'utilisateur la reprend
        self.refus = refus or []  # les gestes que la permission lui a refusés : [{outil, commande?}] (voir `appel`)
        self.reponse = None       # une réponse aux questions de l'utilisateur : `{fonctionnalite, questions}`
        self.usages = usages or []
        self.usage = self.usages[0] if self.usages else dict(USAGE_VIDE)

    def __repr__(self):
        return f"Execution({self.tache!r}, {self.agent!r}, erreur={self.erreur!r})"


def cumuler(usages):
    """Additionne les usages par modèle (l'ordre de première apparition est gardé)."""
    par_modele = {}
    for u in usages:
        t = par_modele.setdefault(u["modele"], {**USAGE_VIDE, "modele": u["modele"]})
        for c in ("entree", "sortie", "cache_lecture", "cache_ecriture"):
            t[c] += u[c]
        if u.get("abonnement") and "abonnement" not in t:   # l'instantané du début du premier appel est gardé
            t["abonnement"] = u["abonnement"]
    return list(par_modele.values())


def executer_agent(depart, matiere, *, agent, modele, dossier_projet, appeler=appel.appeler, tache=None, lot=None,
                   delai_s=DELAI_AGENT_S, executeur=None, reprendre=None):
    """Lance l'agent (`agent` : sa fiche) sur `modele` (« haiku », « sonnet » ou « opus », casse libre).
    `executeur` : celui d'un agent détaché (`moteur.detache.Registre.executeur`) ; `reprendre` : la session à
    poursuivre (une réponse aux questions de l'utilisateur)."""
    cle = agent["cle"]
    m = (modele or "").strip().lower()
    fable = m == "fable" and fiches.fable_accorde(agent)
    if not fable and ("fable" in m or m not in appel.MODELES):
        return Execution(tache, cle, lot, erreur=("Le moteur ne choisit jamais Fable (sauf accord du Directeur sur "
                                                  "la fiche de l'agent)." if "fable" in m
                                                  else f"Modèle inconnu : {modele}."))
    message = depart.rstrip() + ("\n\n" + matiere.strip() if matiere and matiere.strip() else "") + "\n"
    usages, erreur = [], "aucun essai"
    for _ in range(ESSAIS):
        try:
            plus = {"fable_accorde": True} if fable else {}
            if executeur is not None:
                plus["executer"] = executeur
            if reprendre:
                plus["reprendre"] = reprendre
            r = appeler(CONSIGNE_AGENT, message, m, couche="claude", outils=fiches.outils(agent),
                        dossier_travail=str(dossier_projet), delai_s=delai_s, **plus)
        except appel.ErreurAppel as e:
            usages += e.usages
            erreur = f"l'appel a échoué : {e.raison}"
            continue
        usages += r.usages
        try:
            lu = rapport.lire(r.texte)
        except rapport.RapportIllisible as e:
            erreur = f"rapport illisible : {e}"
            continue
        return Execution(tache, cle, lot, rapport=lu, usages=cumuler(usages), session=getattr(r, "session", None),
                         refus=getattr(r, "refus", None))
    return Execution(tache, cle, lot, usages=cumuler(usages),
                     erreur=f"{erreur} (deux essais sans rapport utilisable)")
