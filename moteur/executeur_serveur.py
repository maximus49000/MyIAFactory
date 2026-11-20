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
import threading
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
RAISON_SANS_ETAT = "Aucun état"     # serveur_tache.etat : dossier présent mais pas (encore) d'etat.json
ESSAIS_RECUPERATION = 5             # rapatriement : nouvel essai après une panne passagère (SSH, état illisible, fetch)
GRACE_SANS_ETAT_S = 300             # sans etat.json si longtemps : la tâche n'a jamais démarré (échec final)
LANCEMENT_PERDU_S = 300             # réponse du lancement perdue et serveur muet si longtemps : échec, arrêt relayé plus tard
# Refus de `serveur_agent.recuperer` qui peuvent venir d'une panne passagère (transfert coupé, dépôt verrouillé) : nouvel
# essai. Tout autre refus (paquet ou fin.json suspects, branche extraite) est définitif.
TRANSITOIRES = ("Rapatriement de", "Paquet Git abîmé", "Branche non récupérée", "Branche récupérée inattendue")

# Un seul exécuteur à la fois par (projet, tâche) dans ce processus (le moteur n'en lance qu'un ; ce verrou ne coûte rien).
_VERROUS = {}
_VERROU_VERROUS = threading.Lock()


def _verrou(cle):
    with _VERROU_VERROUS:
        return _VERROUS.setdefault(cle, threading.Lock())


class EcheanceServeur(TimeoutError):
    """La durée maximale de l'agent serveur est atteinte : le travail rapatrié est gardé, `agents` ne relance pas.
    `usages` : ce que le flux rapatrié a coûté (compté par `appel`)."""

    def __init__(self, usages=None):
        super().__init__(ECHEANCE)
        self.usages = usages or []


def _arret(usages=None):
    e = detache.ArretDemande()
    e.usages = usages or []
    return e


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
    `limites`). Après un appel : `ident` (la tâche serveur), `branche` (la dernière branche rapatriée ou None), `flux` (le
    dernier flux rapatrié), `avertissement`.

    Un seul exécuteur par (projet, tâche) est supposé (le moteur n'en lance qu'un) ; un verrou de processus le garantit
    aussi ici. Ce qui reste d'un appel à l'autre vit dans l'index (fiche de la tâche) : rattachement d'une tâche non finale,
    rapatriement interrompu repris (`rapatriement: en_attente`, jamais une seconde tâche après `terminee`), arrêt à relayer
    quand le serveur répond de nouveau (`arret_demande`), tâche abandonnée faute de place arrêtée une fois."""

    noter_abonnement = True          # l'instantané d'abonnement du flux est noté par `appel` (compté dans l'abonnement)

    def __init__(self, projet, tache, mode, demande_base, dossier=None, ssh=None, dormir=time.sleep, pas_s=15,
                 horloge=time.monotonic, git=None, attente_max_s=600, apk=None):
        self.projet = Path(projet)
        self.apk = apk                   # mode pilote : l'APK déposé sur le serveur (`serveur_agent.lancer_agent`)
        self.tache = tache
        self.mode = mode
        self.demande_base = dict(demande_base or {})
        self.nom_projet = self.demande_base.get("projet") or self.projet.name
        self._dossier, self._ssh, self._git = dossier, ssh, git
        self._dormir, self._horloge, self.pas_s = dormir, horloge, pas_s
        self.attente_max_s = attente_max_s
        self.ident = None
        self.branche = None
        self.flux = b""
        self.avertissement = None
        self._arret = False              # arrêt demandé (bouton du bureau) : vaut pour l'appel en cours ou le suivant
        self._arret_lu = None            # la réponse de serveur_tache.arreter à cette demande
        self._echec_precedent = None     # l'erreur de l'appel précédent (gardée si le nouvel essai est refusé)

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

    def _noter(self, st, ident, champs):
        st._noter(self.dossier, ident, champs)

    def _active(self, st):
        """L'identifiant de la tâche non finale de l'index pour (projet, tâche), la plus récente ; None sinon. Jamais une
        tâche dont l'arrêt est à relayer. Une tâche abandonnée faute de place (elle ne démarrera jamais) est arrêtée, une
        seule fois (fiche marquée `abandon_traite` dès que le serveur a répondu)."""
        trouve = None
        for i, f in self._fiches(st):
            if not self._de_la_tache(f) or f.get("etat") not in ACTIFS or f.get("arret_demande") is True:
                continue
            if f.get("abandonnee") is True:
                if f.get("abandon_traite") is not True:
                    lu = st.arreter(i, self.dossier, self.ssh)
                    if lu.get("etat") != "inconnu":
                        self._noter(st, i, {"abandon_traite": True})
                continue
            trouve = i
        return trouve

    def _relayer_arrets(self, st):
        """Arrêts demandés quand le serveur ne répondait pas : redemandés, une fois réussis notés `arret_relaye`."""
        for i, f in self._fiches(st):
            if self._de_la_tache(f) and f.get("arret_demande") is True and f.get("arret_relaye") is not True:
                lu = st.arreter(i, self.dossier, self.ssh)
                if lu.get("etat") in st.FINAUX:
                    self._noter(st, i, {"arret_relaye": True})

    def _rapatriement_en_attente(self, st):
        trouve = None
        for i, f in self._fiches(st):
            if (self._de_la_tache(f) and f.get("rapatriement") == "en_attente"
                    and f.get("etat") in ("terminee", "arretee")):
                trouve = (i, f)
        return trouve

    def _tache_de_session(self, st, session):
        trouve = None
        for i, f in self._fiches(st):
            if f.get("type") == "agent" and f.get("projet") == self.nom_projet and f.get("session") == session:
                trouve = (i, f)
        return trouve

    def _git_(self, sa):
        return self._git or sa._git

    def _tete_locale(self, sa):
        """Le commit de la branche locale `agent/<tâche>` (rapatriée par une tâche précédente), ou None."""
        code, sortie, _e = self._git_(sa)(self.projet, ["rev-parse", "--verify", "-q",
                                                        f"refs/heads/agent/{self.tache}^{{commit}}"])
        tete = sortie.decode("ascii", "replace").strip() if isinstance(sortie, bytes) else ""
        return tete if code == 0 and MOTIF_BASE.fullmatch(tete) else None

    def _ancetre(self, sa, a, b):
        code, _o, _e = self._git_(sa)(self.projet, ["merge-base", "--is-ancestor", a, b])
        return code == 0

    # ------------------------------------------------------------------ appel
    def __call__(self, argv, entree, env, cwd, delai_s):
        """`(code, flux)` comme `appel._executer_claude`. `env` et `cwd` du poste sont ignorés (jamais transmis)."""
        sa, st = _modules()
        with _verrou((self.nom_projet, str(self.tache).lower())):
            try:
                code, sortie = self._appeler(sa, st, argv, entree, delai_s)
            finally:
                # la demande d'arrêt valait pour cet appel (ou, faite entre deux appels, pour celui-ci) : consommée
                self._arret, self._arret_lu = False, None
        self._echec_precedent = appel._extrait(sortie) if code != 0 else None
        return code, sortie

    def _appeler(self, sa, st, argv, entree, delai_s):
        self.ident = None
        try:
            distant, chemin_consigne = argv_distant(argv)
        except ValueError as e:
            return 1, str(e).encode("utf-8")
        consigne = Path(chemin_consigne).read_bytes()
        delai = max(1, int(delai_s))
        self._relayer_arrets(st)
        self._verifier_arret(sa, st, None)
        attente = self._rapatriement_en_attente(st)
        if attente is not None:          # une tâche finie dont le rapatriement a échoué : repris, jamais relancée
            ident, fiche = attente
            self.ident = ident
            return self._conclure(sa, st, ident, {"etat": fiche.get("etat"), "statut": fiche.get("statut"),
                                                  "raison": fiche.get("raison") or ""})
        ident, incertain = self._active(st), False
        if ident is None:
            try:
                ident, echec, incertain = self._lancer(sa, st, distant, consigne, entree, delai)
            except ValueError as e:                     # RefusLancement : rien n'est parti
                message = str(e)
                if self._echec_precedent:
                    message = f"Premier essai : {self._echec_precedent} ; nouvel essai refusé : {message}"
                return 1, message.encode("utf-8")
            if echec is not None:
                return echec
        self.ident = ident
        lu, cause = self._suivre(sa, st, ident, delai, incertain)
        return self._conclure(sa, st, ident, lu, cause)

    def _lancer(self, sa, st, distant, consigne, entree, delai):
        """`(ident, None, incertain)` si la tâche est lancée (à suivre ; `incertain` : réponse du lancement perdue),
        `(None, (code, sortie), False)` si elle n'a pas pu l'être."""
        paquet, branche, base = sa.preparer_paquet(self.projet, git=self._git_(sa))
        self._verifier_arret(sa, st, None)
        reprend = None
        session = _valeur(distant, "--resume")
        if session:
            precedente = self._tache_de_session(st, session)
            if precedente is None:
                return None, (1, ("Reprise impossible : aucune tâche d'agent serveur de cette session dans l'index "
                                  f"({session}).").encode("utf-8")), False
            reprend, fiche = precedente
            branche = fiche.get("branche") if isinstance(fiche.get("branche"), str) else branche
            base = fiche.get("base")
            if not isinstance(base, str) or not MOTIF_BASE.fullmatch(base):
                return None, (1, "Reprise impossible : base de la tâche précédente inconnue.".encode("utf-8")), False
            tete = self._tete_locale(sa)       # la branche rapatriée, seulement si elle descend de la base d'avant
            if tete and self._ancetre(sa, base, tete):
                base = tete
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
                              git=self._git_(sa), **({"apk": self.apk} if self.apk else {}))
        self.avertissement = res.get("avertissement")
        ident, etat = res.get("id"), res.get("etat")
        erreur = res.get("erreur") or res.get("raison") or ""
        if not isinstance(ident, str) or not st.MOTIF_ID.fullmatch(ident):
            return None, (1, (erreur or "Lancement de l'agent serveur impossible.").encode("utf-8")), False
        self.ident = ident
        self._verifier_arret(sa, st, ident)            # arrêt demandé pendant le paquet ou l'envoi
        if etat == "echouee":
            return None, (1, (erreur or "Lancement de l'agent serveur en échec.").encode("utf-8")), False
        if etat == "arretee":
            raise _arret()
        if etat == "en_attente" and (st.Index(self.dossier).lire().get(ident) or {}).get("abandonnee") is True:
            lu = st.arreter(ident, self.dossier, self.ssh)   # jamais démarrée : rien ne reste en file sur le serveur
            if lu.get("etat") != "inconnu":
                self._noter(st, ident, {"abandon_traite": True})
            return None, (1, (erreur or "Aucune place d'agent libre sur le serveur.").encode("utf-8")), False
        return ident, None, etat != "en_cours"

    # ------------------------------------------------------------------ suivi
    def _suivre(self, sa, st, ident, delai, incertain):
        """`(état final, cause)` : sonde l'état toutes les `pas_s`. Serveur injoignable : le suivi continue. Sans état sur
        le serveur pendant `GRACE_SANS_ETAT_S` : échec final (index `echouee`). Réponse du lancement perdue et serveur muet
        pendant `LANCEMENT_PERDU_S` : échec (arrêt relayé plus tard). Au-delà de `delai + 120` s : serveur muet tout du long
        -> échec qui le dit ; sinon arrêt, puis le travail est rapatrié (cause « echeance »)."""
        debut = self._horloge()
        limite = debut + delai + MARGE_SUIVI_S
        sans_etat_depuis, joint = None, False
        while True:
            self._verifier_arret(sa, st, ident)
            lu = st.etat(ident, self.dossier, self.ssh)
            etat, raison = lu.get("etat"), str(lu.get("raison") or "")
            maintenant = self._horloge()
            if etat in st.FINAUX:
                return lu, None
            if etat == "inconnu" and raison.startswith(RAISON_SANS_ETAT):
                joint = True
                sans_etat_depuis = maintenant if sans_etat_depuis is None else sans_etat_depuis
                if maintenant - sans_etat_depuis >= GRACE_SANS_ETAT_S:
                    raison = (f"Aucun état de la tâche sur le serveur depuis {int(maintenant - sans_etat_depuis)} s : "
                              "l'agent n'a jamais démarré (tâche marquée en échec).")
                    self._noter(st, ident, {"etat": "echouee", "statut": "erreur", "fin": st._maintenant_iso(),
                                            "raison": raison})
                    return {"etat": "echouee", "raison": raison}, None
            elif etat == "inconnu":
                if incertain and not joint and maintenant - debut >= LANCEMENT_PERDU_S:
                    raison = (f"Réponse du lancement perdue et serveur injoignable depuis {int(maintenant - debut)} s : "
                              "tâche marquée en échec ; son arrêt sera demandé dès que le serveur répondra.")
                    self._noter(st, ident, {"etat": "echouee", "statut": "erreur", "fin": st._maintenant_iso(),
                                            "raison": raison, "arret_demande": True})
                    return {"etat": "echouee", "raison": raison}, None
            else:
                joint, sans_etat_depuis = True, None
            if maintenant >= limite:
                if not joint:
                    raison = (f"Serveur injoignable pendant toute l'attente de l'agent serveur ({int(maintenant - debut)}"
                              " s) : son arrêt sera demandé dès que le serveur répondra.")
                    self._noter(st, ident, {"arret_demande": True})
                    return {"etat": "echouee", "raison": raison}, None
                fin = st.arreter(ident, self.dossier, self.ssh)
                if fin.get("etat") in st.FINAUX:
                    return fin, "echeance"
                self._noter(st, ident, {"arret_demande": True})
                raise EcheanceServeur()
            self._dormir(self.pas_s)

    def _verifier_arret(self, sa, st, ident):
        """Arrêt demandé : `ArretDemande`. La tâche (si elle existe) est arrêtée ; finie, son travail est rapatrié ; serveur
        muet, l'arrêt est noté pour être relayé plus tard (`arret_demande`)."""
        if not self._arret:
            return
        if ident is None:
            raise _arret()
        lu = self._arret_lu if (self._arret_lu or {}).get("id") == ident else None
        if lu is None:
            lu = st.arreter(ident, self.dossier, self.ssh)
        if lu.get("etat") not in st.FINAUX:
            self._noter(st, ident, {"arret_demande": True})
            raise _arret()
        usages = []
        if lu.get("etat") in ("terminee", "arretee"):
            statut, r = self._rapatrier(sa, st, ident)
            if statut == "ok":
                usages = self._garder(st, ident, r)
        raise _arret(usages)

    # ------------------------------------------------------------------ fin
    def _rapatrier(self, sa, st, ident):
        """`("ok", résultat)` ; `("transitoire", message)` après `ESSAIS_RECUPERATION` pannes passagères (la fiche reste
        `rapatriement: en_attente` : le prochain appel reprend le rapatriement) ; `("refus", message)` si définitif."""
        self._noter(st, ident, {"rapatriement": "en_attente"})
        message = ""
        for essai in range(ESSAIS_RECUPERATION):
            if essai:
                self._dormir(self.pas_s)
            try:
                r = sa.recuperer(ident, self.projet, dossier=self.dossier, ssh=self.ssh, git=self._git_(sa))
            except ValueError as e:                    # RefusRecuperation
                message = str(e)
                if not message.startswith(TRANSITOIRES):
                    self._noter(st, ident, {"rapatriement": "refuse"})
                    return "refus", message
                continue
            except OSError as e:
                message = f"{type(e).__name__} : {e}"
                continue
            if r.get("etat") not in ("terminee", "arretee"):
                message = str(r.get("raison") or "état de la tâche illisible")
                continue
            self._noter(st, ident, {"rapatriement": "fait"})
            return "ok", r
        return "transitoire", (f"Rapatriement du travail de l'agent serveur impossible pour l'instant ({message}) : il "
                               "sera repris au prochain essai, sans relancer l'agent.")

    def _garder(self, st, ident, r):
        """Garde la branche et le flux rapatriés, note la session ; rend les usages lisibles du flux."""
        if r.get("branche"):
            self.branche = r["branche"]
        self.flux = r.get("flux") or b""
        resultat, evenements = appel._lire_flux(self.flux)
        if resultat is None:
            return []
        session = resultat.get("session_id")
        if isinstance(session, str) and MOTIF_SESSION.fullmatch(session):
            self._noter(st, ident, {"session": session})
        return appel._usages_de(resultat, appel.abonnement.instantane_depuis(evenements, time.time()))

    def _conclure(self, sa, st, ident, lu, cause=None):
        etat = lu.get("etat")
        raison = str(lu.get("raison") or "")
        if etat == "echouee":            # rien n'est rapatrié (un secret trouvé vide la sortie)
            return 1, (raison or "L'agent serveur a échoué.").encode("utf-8")
        statut, r = self._rapatrier(sa, st, ident)
        if statut != "ok":
            if cause == "echeance":
                raise EcheanceServeur()
            if etat == "arretee":
                raise _arret()
            return 1, r.encode("utf-8")
        usages = self._garder(st, ident, r)
        if cause == "echeance":
            raise EcheanceServeur(usages)
        if etat == "arretee":
            raise _arret(usages)
        fin = r.get("fin") if isinstance(r.get("fin"), dict) else {}
        if fin.get("echeance") is True or (lu.get("statut") == "limite" and RAISON_DUREE in raison):
            raise EcheanceServeur(usages)
        code = fin.get("code") if isinstance(fin.get("code"), int) and not isinstance(fin.get("code"), bool) else 1
        if not self.flux:
            return code or 1, (raison or "Aucun flux rapatrié de l'agent serveur.").encode("utf-8")
        return code, self.flux

    # ------------------------------------------------------------------ arrêt
    def arreter(self):
        """Arrête l'agent : l'appel en cours (ou le suivant) finit par `ArretDemande`, même serveur injoignable. La tâche
        serveur (celle lancée ou rattachée, sinon la tâche active de l'index pour (projet, tâche)) est arrêtée par
        `serveur_tache.arreter` ; serveur muet, l'arrêt est noté pour être relayé plus tard. Jamais d'exception."""
        self._arret = True
        try:
            _sa, st = _modules()
            ident = self.ident or self._active(st)
            if not ident:
                return {"id": None, "etat": "inconnu", "raison": "Aucune tâche d'agent serveur à arrêter."}
            lu = st.arreter(ident, self.dossier, self.ssh)
            self._arret_lu = {**lu, "id": ident}
            if lu.get("etat") not in st.FINAUX:
                self._noter(st, ident, {"arret_demande": True})
            return lu
        except Exception as e:  # noqa: BLE001 - l'arrêt du bureau ne lève jamais
            return {"id": self.ident, "etat": "inconnu", "raison": f"Arrêt impossible ({type(e).__name__})."}
