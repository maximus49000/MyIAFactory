"""L'exécuteur distant d'un agent de production (tranche B) : `executer_agent` ordinaire dont `claude -p` tourne sur le serveur.

`ExecuteurServeur` a la signature de `appel._executer_claude` (`(argv, entree, env, cwd, delai_s) -> (code, sortie)`) : au lieu de
lancer `claude -p` sur le poste, il envoie le paquet Git du projet, la consigne et le message (`serveur_agent.lancer_agent`),
sonde l'état de la tâche jusqu'à sa fin, puis rapatrie le flux `stream-json` et la branche `agent/<tâche>`
(`serveur_agent.recuperer`). Rapport, usages, abonnement, reprise (`--resume`) et arrêt passent donc par le chemin existant
d'`appel` et d'`agents`.

L'environnement et le dossier de travail du poste ne partent JAMAIS : seuls l'argv (traduit et revérifié par `DRAPEAUX`), la
consigne, le message et le paquet Git sont envoyés. Tout ce que le serveur renvoie est une donnée non fiable (revalidée par
`serveur_agent`, puis par `appel` qui lit le flux).
"""
import re
import sys
import time
from pathlib import Path

from moteur import appel, detache

_OUTILS = str(Path(__file__).resolve().parent.parent / "outils")

# Liste blanche des options de `claude` produites par `appel._argv` (miroir exact de serveur_ovh/images/agent/entree-agent.py,
# décision R2 ; test de concordance) : nom -> None (option sans valeur) ou motif que la valeur suivante doit vérifier EN ENTIER
# (re.fullmatch). Une valeur ne commence jamais par « - ».
DRAPEAUX = {
    "-p": None,
    "--output-format": r"stream-json",
    "--verbose": None,
    "--model": r"claude-[a-z0-9][a-z0-9.-]{0,62}|fable",
    "--tools": r"|[A-Za-z][A-Za-z0-9_]{0,63}(?:,[A-Za-z][A-Za-z0-9_]{0,63}){0,63}",
    # règles « Nom » ou « Nom(motif sans parenthèse) », séparées par « , » ou une espace, 64 au plus, 8 Ko au plus
    "--allowedTools": r"(?=[\s\S]{1,8192}\Z)"
                      r"[A-Za-z][A-Za-z0-9_]{0,63}(?:\([^()\x00-\x1f\x7f]*\))?"
                      r"(?:[, ][A-Za-z][A-Za-z0-9_]{0,63}(?:\([^()\x00-\x1f\x7f]*\))?){0,63}",
    "--permission-prompts": r"none",
    "--append-system-prompt-file": r"/entree/consigne\.md",
    "--system-prompt-file": r"/entree/consigne\.md",
    "--strict-mcp-config": None,
    "--setting-sources": r"",
    "--disable-slash-commands": None,
    "--resume": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "--no-session-persistence": None,
}
OBLIGATOIRES = ("-p", "--output-format")
OPTIONS_CONSIGNE = ("--append-system-prompt-file", "--system-prompt-file")
CONSIGNE_DISTANTE = "/entree/consigne.md"
ECHEANCE = "durée maximale de l'agent serveur atteinte"
MARGE_SUIVI_S = 120                 # le suivi attend delai_s + 120 s (le veilleur du serveur conclut avant)
ACTIFS = ("en_attente", "en_cours")
MOTIF_SESSION = re.compile(DRAPEAUX["--resume"], re.ASCII)
MOTIF_BASE = re.compile(r"[0-9a-f]{40}", re.ASCII)
RAISON_DUREE = "Durée maximale"     # raison du veilleur à l'échéance de duree_s (serveur_ovh/taches/lancer_agent.sh)


def _modules():
    """`serveur_agent` et `serveur_tache` (modules à plat du dossier `outils`)."""
    if _OUTILS not in sys.path:
        sys.path.append(_OUTILS)
    import serveur_agent
    import serveur_tache
    return serveur_agent, serveur_tache


def argv_distant(argv):
    """`(argv pour le serveur, chemin local de la consigne)` : `argv[0]` devient `claude`, le fichier de consigne
    `/entree/consigne.md` ; chaque option passe par `DRAPEAUX` (valeur entière revérifiée). `ValueError` pour toute option
    hors liste, tout argument libre, tout doublon, toute valeur refusée, et sans exactement une consigne."""
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv invalide : une liste de textes est attendue.")
    distant, consigne, vues, i = ["claude"], None, set(), 1
    while i < len(argv):
        nom = argv[i]
        if nom not in DRAPEAUX:
            raise ValueError(f"Option refusée pour un agent serveur : {nom[:60]}")
        if nom in vues:
            raise ValueError(f"Option en double refusée pour un agent serveur : {nom}")
        vues.add(nom)
        motif = DRAPEAUX[nom]
        if motif is None:
            distant.append(nom)
            i += 1
            continue
        if i + 1 >= len(argv):
            raise ValueError(f"Valeur manquante pour {nom}.")
        valeur = argv[i + 1]
        if nom in OPTIONS_CONSIGNE:
            if not valeur or valeur.startswith("-"):
                raise ValueError(f"Fichier de consigne invalide pour {nom}.")
            consigne, valeur = valeur, CONSIGNE_DISTANTE
        if valeur.startswith("-") or not re.fullmatch(motif, valeur):
            raise ValueError(f"Valeur refusée pour {nom} (agent serveur).")
        distant += [nom, valeur]
        i += 2
    for nom in OBLIGATOIRES:
        if nom not in vues:
            raise ValueError(f"Option obligatoire absente : {nom}")
    if sum(nom in vues for nom in OPTIONS_CONSIGNE) != 1:
        raise ValueError("Une et une seule consigne (--system-prompt-file ou --append-system-prompt-file).")
    return distant, consigne


def _valeur(argv, nom):
    return argv[argv.index(nom) + 1] if nom in argv[:-1] else None


class ExecuteurServeur:
    """L'exécuteur `executer=` d'`appel.appeler` pour un agent du lieu `serveur`.

    `projet` : le dossier du dépôt (paquet Git, branche rapatriée) ; `tache` : le nom de tâche (branche `agent/<tâche>`) ;
    `mode` : `seul` ou `pilote` ; `demande_base` : le reste de la demande (`projet` = nom du projet, `modele`, `places`,
    `limites`). Après un appel : `ident` (la tâche serveur), `branche` (la branche rapatriée ou None), `avertissement`."""

    noter_abonnement = True          # l'instantané d'abonnement du flux est noté par `appel` (compté dans l'abonnement)

    def __init__(self, projet, tache, mode, demande_base, dossier=None, ssh=None, dormir=time.sleep, pas_s=15,
                 horloge=time.monotonic, git=None, attente_max_s=600):
        self.projet = Path(projet)
        self.tache = tache
        self.mode = mode
        self.demande_base = dict(demande_base or {})
        self.nom_projet = self.demande_base.get("projet") or self.projet.name
        self._dossier, self._ssh, self._git = dossier, ssh, git
        self._dormir, self._horloge, self.pas_s = dormir, horloge, pas_s
        self.attente_max_s = attente_max_s
        self.ident = None
        self.branche = None
        self.avertissement = None

    # ------------------------------------------------------------------ accès
    @property
    def dossier(self):
        if self._dossier is None:
            from bureau import plateforme
            self._dossier = plateforme.dossier()
        return self._dossier

    @property
    def ssh(self):
        if self._ssh is None:
            if _OUTILS not in sys.path:
                sys.path.append(_OUTILS)
            import plateforme_ssh
            self._ssh = plateforme_ssh
        return self._ssh

    def _fiches(self, st):
        return sorted(st.Index(self.dossier).lire().items())

    def _de_la_tache(self, fiche):
        return (fiche.get("type") == "agent" and fiche.get("projet") == self.nom_projet
                and isinstance(fiche.get("tache"), str) and fiche["tache"].lower() == str(self.tache).lower())

    def _active(self, st):
        """L'identifiant de la tâche non finale de l'index pour (projet, tâche), la plus récente ; None sinon. Une tâche
        abandonnée faute de place (elle ne démarrera jamais) est arrêtée au passage."""
        trouve = None
        for i, f in self._fiches(st):
            if self._de_la_tache(f) and f.get("etat") in ACTIFS:
                if f.get("abandonnee") is True:
                    st.arreter(i, self.dossier, self.ssh)
                    continue
                trouve = i
        return trouve

    def _tache_de_session(self, st, session):
        trouve = None
        for i, f in self._fiches(st):
            if f.get("type") == "agent" and f.get("projet") == self.nom_projet and f.get("session") == session:
                trouve = (i, f)
        return trouve

    def _tete_locale(self, sa):
        """Le commit de la branche locale `agent/<tâche>` (rapatriée par une tâche précédente), ou None."""
        git = self._git or sa._git
        code, sortie, _e = git(self.projet, ["rev-parse", "--verify", "-q", f"refs/heads/agent/{self.tache}^{{commit}}"])
        tete = sortie.decode("ascii", "replace").strip() if isinstance(sortie, bytes) else ""
        return tete if code == 0 and MOTIF_BASE.fullmatch(tete) else None

    # ------------------------------------------------------------------ appel
    def __call__(self, argv, entree, env, cwd, delai_s):
        """`(code, flux)` comme `appel._executer_claude`. `env` et `cwd` du poste sont ignorés (jamais transmis)."""
        sa, st = _modules()
        try:
            distant, chemin_consigne = argv_distant(argv)
        except ValueError as e:
            return 1, str(e).encode("utf-8")
        consigne = Path(chemin_consigne).read_bytes()
        delai = max(1, int(delai_s))
        ident = self._active(st)
        if ident is None:
            try:
                ident, echec = self._lancer(sa, st, distant, consigne, entree, delai)
            except ValueError as e:                     # RefusLancement : rien n'est parti
                return 1, str(e).encode("utf-8")
            if echec is not None:
                return echec
        self.ident = ident
        lu = self._suivre(st, ident, delai)
        return self._conclure(sa, st, ident, lu)

    def _lancer(self, sa, st, distant, consigne, entree, delai):
        """`(ident, None)` si la tâche est lancée (à suivre), `(None, (code, sortie))` si elle n'a pas pu l'être."""
        paquet, branche, base = sa.preparer_paquet(self.projet, git=self._git or sa._git)
        reprend = None
        session = _valeur(distant, "--resume")
        if session:
            precedente = self._tache_de_session(st, session)
            if precedente is None:
                return None, (1, ("Reprise impossible : aucune tâche d'agent serveur de cette session dans l'index "
                                  f"({session}).").encode("utf-8"))
            reprend, fiche = precedente
            branche = fiche.get("branche") if isinstance(fiche.get("branche"), str) else branche
            base = self._tete_locale(sa) or fiche.get("base")
            if not isinstance(base, str) or not MOTIF_BASE.fullmatch(base):
                return None, (1, "Reprise impossible : base de la tâche précédente inconnue.".encode("utf-8"))
        limites = dict(self.demande_base.get("limites") or {})
        plafonds = [delai, sa.LIMITES_AGENT["duree_s"]]
        if isinstance(limites.get("duree_s"), int) and not isinstance(limites["duree_s"], bool):
            plafonds.append(limites["duree_s"])
        limites["duree_s"] = max(1, min(plafonds))
        demande = {**self.demande_base, "projet": self.nom_projet, "tache": self.tache, "mode": self.mode,
                   "branche": branche, "base": base, "limites": limites, "reprend": reprend}
        if not demande.get("modele"):
            demande["modele"] = _valeur(distant, "--model")
        res = sa.lancer_agent(demande, paquet, distant, consigne, entree, dossier=self.dossier, ssh=self.ssh,
                              attente_max_s=self.attente_max_s, dormir=self._dormir, projet=self.projet,
                              git=self._git or sa._git)
        self.avertissement = res.get("avertissement")
        ident, etat = res.get("id"), res.get("etat")
        erreur = res.get("erreur") or res.get("raison") or ""
        if not isinstance(ident, str) or not st.MOTIF_ID.fullmatch(ident):
            return None, (1, (erreur or "Lancement de l'agent serveur impossible.").encode("utf-8"))
        self.ident = ident
        if etat == "echouee":
            return None, (1, (erreur or "Lancement de l'agent serveur en échec.").encode("utf-8"))
        if etat == "arretee":
            raise detache.ArretDemande()
        if etat == "en_attente" and (st.Index(self.dossier).lire().get(ident) or {}).get("abandonnee") is True:
            st.arreter(ident, self.dossier, self.ssh)       # jamais démarrée : rien ne reste en file sur le serveur
            return None, (1, (erreur or "Aucune place d'agent libre sur le serveur.").encode("utf-8"))
        return ident, None

    def _suivre(self, st, ident, delai):
        """Sonde l'état toutes les `pas_s` jusqu'à un état final ; un serveur injoignable (« inconnu ») n'interrompt pas le
        suivi. Au-delà de `delai + 120` s : arrêt demandé, puis `TimeoutError(ECHEANCE)`."""
        limite = self._horloge() + delai + MARGE_SUIVI_S
        while True:
            lu = st.etat(ident, self.dossier, self.ssh)
            if lu.get("etat") in st.FINAUX:
                return lu
            if self._horloge() >= limite:
                self.arreter()
                raise TimeoutError(ECHEANCE)
            self._dormir(self.pas_s)

    def _conclure(self, sa, st, ident, lu):
        etat = lu.get("etat")
        raison = str(lu.get("raison") or "")
        if etat == "echouee":            # rien n'est rapatrié (un secret trouvé vide la sortie)
            return 1, (raison or "L'agent serveur a échoué.").encode("utf-8")
        try:
            r = sa.recuperer(ident, self.projet, dossier=self.dossier, ssh=self.ssh, git=self._git or sa._git)
        except ValueError as e:          # RefusRecuperation : fin.json, paquet ou branche refusés
            if etat == "arretee":
                raise detache.ArretDemande()
            return 1, str(e).encode("utf-8")
        self.branche = r.get("branche")
        flux = r.get("flux") or b""
        fin = r.get("fin") if isinstance(r.get("fin"), dict) else {}
        self._noter_session(st, ident, flux)
        if etat == "arretee":
            raise detache.ArretDemande()
        if fin.get("echeance") is True or (lu.get("statut") == "limite" and RAISON_DUREE in raison):
            raise TimeoutError(ECHEANCE)
        code = fin.get("code") if isinstance(fin.get("code"), int) and not isinstance(fin.get("code"), bool) else 1
        if not flux:
            return code or 1, (raison or "Aucun flux rapatrié de l'agent serveur.").encode("utf-8")
        return code, flux

    def _noter_session(self, st, ident, flux):
        """Note dans la fiche d'index la session de la ligne `result` du flux (une reprise la retrouve)."""
        resultat, _ev = appel._lire_flux(flux)
        session = (resultat or {}).get("session_id")
        if isinstance(session, str) and MOTIF_SESSION.fullmatch(session):
            st._noter(self.dossier, ident, {"session": session})

    # ------------------------------------------------------------------ arrêt
    def arreter(self):
        """Arrête la tâche serveur de cet agent (celle lancée ou rattachée, sinon la tâche active de l'index pour
        (projet, tâche)) : relaie `serveur_tache.arreter`. Jamais d'exception."""
        _sa, st = _modules()
        ident = self.ident or self._active(st)
        if not ident:
            return {"id": None, "etat": "inconnu", "raison": "Aucune tâche d'agent serveur à arrêter."}
        return st.arreter(ident, self.dossier, self.ssh)
