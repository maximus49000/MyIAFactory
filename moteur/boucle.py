"""La boucle du moteur : un passage (`tour`) toutes les 2 s, pour chaque projet du bureau.

Un passage, par projet, dans cet ordre (conception, section 4.1) :
1. la présence (`presence.json`, comme `lancer guetter`) ; au premier passage : les partenaires (`detecter`) et les
   tâches orphelines (active, mais plus d'agent) relancées une fois, tâches arrêtées faute d'outil que la fiche ouvre
   maintenant relancées une fois ;
2. les demandes du bureau, les messages de discussion d'abord, chacune une seule fois ;
3. les retours des agents terminés : usage noté, rapport appliqué, commit et push ;
4. `avancer` : ce que dit le parcours à chaque étape (rien en pause : les demandes, elles, sont toujours traitées) ;
5. les quotas des partenaires (l'outil ne relit qu'une fois par heure chacun).

Tout passe par `regles` donc par `lancer`. Un appel de jugement est synchrone ; un agent est attendu dans un fil (un par
exécution) et rend son `Execution` dans une file lue au passage suivant. Un agent local tourne dans un processus détaché
du moteur (`moteur.detache`) : relancer le moteur ne l'interrompt pas, le moteur suivant le retrouve et l'attend. Chaque appel, de jugement ou d'agent, est noté
par `lancer usage` (le coût de l'orchestration reste ainsi à part de la production). Une erreur n'arrête jamais la
boucle : elle est dite au bureau (réponse de la demande, journal de la tâche) ou, à défaut, gardée dans `journal`.
"""
import json
import os
import queue
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from bureau import attente
from bureau import reglages as reglages_bureau
from moteur import agents, appel, cloud, detache, figes, git_sur, jugement, regles
from orchestrateur import factory as fa
from orchestrateur import fiches as fi
from orchestrateur import guetteur

PAS_S = 2
REVEIL_VERIFIE_S = 0.2           # pendant l'attente, le fichier de réveil de chaque projet est regardé cinq fois par seconde
QUOTA_TOUS_LES_S = 60
CLOUD_TOUS_LES_S = 60            # le dépôt est relevé toutes les minutes
CLOUD_MUETTE_S = 2 * 3600        # une session sans rapport au bout de deux heures : la décision revient au Directeur
BUREAU_PAR_DEFAUT = "~/MyIAFactory/bureau.json"
AGENT_ORCHESTRATEUR = "orchestrateur"
ETAPE_ORCHESTRATION = "orchestration"
DELAI_GIT_S = 60
ESSAIS_INSTALLATION = 3          # un départ d'installation qui échoue ainsi trois fois est laissé : il ne retient pas le bureau
ECRITURE_LECONS_TOUS_LES_S = 300  # une leçon validée mais pas encore écrite dans la mémoire de la skill est réessayée ainsi
REECRIRE_TOUS_LES_S = 20        # un fichier pour le bureau (pause, attente de charge) est réécrit au moins toutes les 20 s
OUTILS_DE_REPONSE = "Read, Grep, Glob"   # l'agent qui répond à une question lit, il ne modifie rien


def texte_des_questions(questions):
    """Les questions de l'utilisateur posées pendant la tâche, pour la matière de l'agent."""
    return ("Pendant que tu travaillais, l'utilisateur t'a écrit dans la discussion :\n"
            + "\n".join(f"- « {q} »" for q in questions)
            + "\nRéponds-lui dans `message.texte` de ton rapport, en plus de ton compte rendu.")


def depart_de_reponse(tache, questions, session, rendu=None):
    """Le message de l'agent qui répond, sa tâche finie : sa session reprise, sinon de quoi se souvenir."""
    parties = [f"Ta tâche {tache} est terminée. Pendant que tu y travaillais, l'utilisateur t'a écrit dans la "
               "discussion :", "\n".join(f"- « {q} »" for q in questions)]
    if not session and rendu:
        parties.append("Ton compte rendu de la tâche : " + " ".join(str(rendu).split())[:1500])
    parties.append("Réponds-lui maintenant, en quelques phrases, à partir de ce que tu as fait : ne refais rien et ne "
                   "modifie aucun fichier. Termine par le bloc ```json "
                   '{"statut": "fait", "message": {"texte": "ta réponse", "attend": false}}.')
    return "\n\n".join(parties)


def ouvrir_projet(fichier_reglages, environ=None):
    """Un `Projet` à partir du fichier de réglages du bureau : la factory est à côté (`factory.json`), la couche
    d'appel vient de `moteur.couche` (et de la clé dans l'environnement). La ligne à dire une fois au bureau (API
    demandée sans clé) est gardée dans `projet.ligne_a_dire`."""
    fichier = Path(fichier_reglages)
    try:
        r = json.loads(fichier.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        r = {}
    couche, ligne = appel.choisir_couche(r if isinstance(r, dict) else {}, os.environ if environ is None else environ)
    projet = regles.Projet(fichier.parent / "factory.json", couche)
    projet.ligne_a_dire = ligne
    projet.fichier_reglages = fichier
    try:
        lus = reglages_bureau.charger(fichier)
        projet.cloud_max = lus["agents_cloud_max"]
        projet.cloud_dossier_approuve = lus["cloud_dossier_approuve"]
        projet.lecons_auto = lus["lecons_auto"]
        projet.analyse_blocages = lus["analyse_blocages"]
    except reglages_bureau.ReglagesInvalides:
        pass
    return projet


def projets_du_bureau(bureau, environ=None):
    """Les projets du fichier du bureau (lu à chaque appel : un projet ajouté est pris sans redémarrer)."""
    return [ouvrir_projet(p["chemin"], environ) for p in reglages_bureau.lire_bureau(bureau)["projets"]]


def commit_et_push(dossier, message):
    """Commit (tout ce que le dossier du projet a de modifié) et push du dépôt du projet. Sans dépôt, ou sans rien de
    neuf, ne fait rien ; un push qui échoue n'est pas une erreur (la copie locale a le commit)."""
    dossier = Path(dossier)
    if not (dossier / ".git").exists():
        return False
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    class _Fait:
        def __init__(self, code):
            self.returncode = code

    def lancer(argv):
        p = subprocess.run(argv, cwd=str(dossier), capture_output=True, env=env, timeout=DELAI_GIT_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return p.returncode, (p.stdout or b"") + (p.stderr or b"")

    def git(*args):     # une à la fois par dépôt, réessayée si un autre git tient l'index (`git_sur`)
        return _Fait(git_sur.executer(lancer, dossier, ["git", *args])[0])

    try:
        with git_sur.verrou(dossier):
            cloud.etat_hors_du_depot(dossier)
            git("add", "-A")
            if git("diff", "--cached", "--quiet").returncode == 0:
                return False
            if git("commit", "-m", message).returncode != 0:
                return False
            cloud._pousser(None, dossier)
            return True
    except (OSError, subprocess.SubprocessError, cloud.ErreurCloud):
        return False


class Moteur:
    """`projets` : les `regles.Projet` tenus ; `bureau` (facultatif) : le fichier du bureau, relu à chaque passage pour
    prendre les projets ajoutés. `executer_agent`, `commit` et `synchrone` (les agents tournent dans l'appel, pas dans
    un fil) sont là pour les essais."""

    def __init__(self, projets, *, appeler=appel.appeler, horloge=time.time, bureau=None, environ=None,
                 executer_agent=agents.executer_agent, commit=commit_et_push, synchrone=False, session_cloud=None,
                 registre=None, surveillance=None):
        self.appeler, self.horloge, self.bureau, self.environ = appeler, horloge, bureau, environ
        # les commandes figées des agents locaux (`moteur.figes`) : une liste des processus par tour au plus
        self.surveillance = surveillance if surveillance is not None else figes.Surveillance()
        self._processus_du_tour, self._surveille = None, {}
        self.executer_agent, self.commit, self.synchrone = executer_agent, commit, synchrone
        self.cloud = session_cloud or cloud      # le module (ou un faux) qui parle aux sessions cloud
        self.registre_de = registre or detache.Registre    # dossier de la factory -> les agents détachés du projet
        self._registres = {}
        self.projets, self.etats, self.retours, self.journal = [], {}, queue.Queue(), []
        self.dernier_quota = {}
        self.file_installations = []       # (clé du projet, tâche) des installations prêtes, dans l'ordre d'arrivée
        self.pause_installation = None     # {texte, projet, outils} quand une installation retient tout le bureau
        self._installation_vue = False     # une installation était en cours ou attendue au passage d'avant
        self._ecrits = {}                  # fichier -> (contenu, heure) : un fichier inchangé n'est pas réécrit à chaque passage
        self._echecs_installation = {}
        self._mesure_tour = None           # la mesure de charge du tour en cours, partagée par tous les projets
        self.mesures_de_charge = 0         # combien de vraies mesures (sous-processus) ont été faites
        self.duree_dernier_tour_s = None
        self._reveils_vus = {}             # dossier du projet -> dernier horodatage du fichier de réveil traité
        for p in projets:
            self._ajouter(p)

    def _ajouter(self, projet):
        if getattr(projet, "bureau", None) is None:
            projet.bureau = self.bureau     # les mesures d'usage des projets du bureau servent à estimer un workflow
        projet.installations_a_part = True  # les installations sont lancées par `_installations`, avant tout le reste
        if getattr(projet, "mesure_commune", None) is None:
            projet.mesure_commune = self._mesure_du_tour    # une seule mesure de charge par tour pour tout le bureau
        self.projets.append(projet)
        self.etats[str(projet.factory)] = regles.nouvel_etat()

    def _etat(self, projet):
        return self.etats[str(projet.factory)]

    def _registre(self, projet):
        cle = str(projet.factory)
        if cle not in self._registres:
            self._registres[cle] = self.registre_de(projet.factory.parent)
        return self._registres[cle]

    def _noter(self, projet, texte):
        self.journal.append(f"{projet.nom} : {texte}")

    # --- Un passage.

    def tour(self):
        debut = time.monotonic()
        self._mesure_tour = None        # la charge du poste est mesurée au plus une fois par tour (si un projet la demande)
        self._processus_du_tour = None
        self._prendre_les_projets_ajoutes()
        self._installations()
        self._traiter_les_reveils()
        for projet in list(self.projets):
            self._traiter_les_reveils()
            try:
                self._tour_projet(projet)
            except Exception as e:      # une erreur d'un projet n'arrête ni la boucle ni les autres projets
                self._noter(projet, f"erreur au passage : {e}")
        self.duree_dernier_tour_s = time.monotonic() - debut

    def tourner(self, arret):
        while not arret.is_set():
            self.tour()
            self.attendre(arret)

    def attendre(self, arret, duree_s=PAS_S):
        """L'attente entre deux tours : tranches de `REVEIL_VERIFIE_S`, à chacune le fichier de réveil de chaque projet est
        regardé (le bureau le touche en posant une demande) ; les demandes des projets signalés sont traitées aussitôt."""
        fin = time.monotonic() + duree_s
        while not arret.is_set():
            reste = fin - time.monotonic()
            if reste <= 0:
                return
            arret.wait(min(reste, REVEIL_VERIFIE_S))
            self._traiter_les_reveils()

    # --- Une seule mesure de charge par tour.

    def _mesure_du_tour(self, projet):
        """La charge du poste, mesurée une fois (le premier projet qui la demande dans le tour) puis partagée ; chaque
        projet compare cette valeur à son propre plafond."""
        if self._mesure_tour is None:
            self._mesure_tour = projet.mesurer()
            self.mesures_de_charge += 1
        m = self._mesure_tour
        if m.get("charge") is None:         # mesure indisponible : la réponse de la mesure vaut pour tous
            return dict(m)
        plafond = projet.plafond_charge()
        if plafond is None:
            plafond = m.get("plafond")
        if plafond is None:
            return dict(m)
        return {"feu_vert": m["charge"] <= plafond, "charge": m["charge"], "plafond": plafond}

    # --- Le réveil : une demande posée par le bureau passe avant le reste du tour.

    def _projets_reveilles(self):
        """Les projets dont le fichier de réveil a changé depuis la dernière fois."""
        sortie = []
        for projet in list(self.projets):
            cle = str(projet.factory)
            date = attente.date_du_reveil(projet.factory.parent)
            if date is not None and date != self._reveils_vus.get(cle):
                self._reveils_vus[cle] = date
                sortie.append(projet)
        return sortie

    def _traiter_les_reveils(self):
        """Les demandes en attente des projets signalés, tout de suite (celles de ce projet seulement, puis le tour
        reprend). Une demande n'est jamais traitée deux fois (`prises`). Un projet pas encore démarré attend son premier
        passage, qui lit ses demandes de toute façon."""
        for projet in self._projets_reveilles():
            etat = self._etat(projet)
            if not etat.get("repris"):
                continue
            try:
                self._demandes(projet, etat)
            except Exception as e:
                self._noter(projet, f"demandes (réveil) : {e}")

    def _prendre_les_projets_ajoutes(self):
        if self.bureau is None:
            return
        try:
            connus = {str(p.factory) for p in self.projets}
            for projet in projets_du_bureau(self.bureau, self.environ):
                if str(projet.factory) not in connus:
                    self._ajouter(projet)
        except reglages_bureau.ReglagesInvalides as e:
            self.journal.append(f"bureau illisible : {e}")

    def _tour_projet(self, projet):
        etat = self._etat(projet)
        self._presence(projet)
        if not etat.get("repris"):
            etat["repris"] = True
            self._demarrage(projet, etat)
        self._demandes(projet, etat)
        self._valider_les_lecons(projet, etat)
        self._ecritures_en_attente(projet, etat)
        self._relever_le_cloud(projet, etat)
        self._traiter_les_reveils()
        self._retours_des_agents(projet, etat)
        self._surveiller_les_commandes(projet)
        self._traiter_les_reveils()
        self._executer(projet, regles.avancer(projet, etat))
        self._dire_l_attente_de_charge(projet, etat)
        self._traiter_les_reveils()
        self._quota(projet)

    def _presence(self, projet):
        suivi = fa.lire(projet.factory)["suivi"]
        try:
            guetteur.ecrire_presence(suivi.with_name("presence.json"), datetime.now().astimezone())
        except OSError:
            pass    # la présence est une aide : jamais une raison d'échouer

    def _demarrage(self, projet, etat):
        try:
            regles.lancer(projet, "partenaires", {"action": "detecter"})
        except (regles.Refus, regles.ErreurMoteur) as e:
            self._noter(projet, f"partenaires : {e}")
        # avant que les agents morts soient oubliés : leurs programmes laissés seront reconnus (`figes`)
        self._surveiller_les_commandes(projet)
        try:
            self._rattacher_les_agents(projet, etat)
        except (regles.Refus, regles.ErreurMoteur, OSError) as e:
            self._noter(projet, f"agents en cours : {e}")
        self._executer(projet, regles.orphelines(projet, etat))
        try:    # arrêtée faute d'outil, dont la fiche l'ouvre maintenant : la tâche repart, une fois
            self._executer(projet, regles.reprendre_les_taches_sans_outil(projet, etat))
        except (regles.Refus, regles.ErreurMoteur, OSError) as e:
            self._noter(projet, f"tâches sans outil : {e}")
        self._retrouver_les_sessions(projet, etat)
        try:    # un projet créé au bureau avec une description : son genre est proposé sans attendre une demande
            self._executer(projet, regles.genre_a_proposer(projet, etat))
        except (regles.Refus, regles.ErreurMoteur) as e:
            self._noter(projet, f"genre du projet : {e}")
        self._outils_manquants(projet, etat)

    def _outils_manquants(self, projet, etat):
        """Un outil à installer qui n'a plus rien à l'écran (ni décision, ni tâche) y revient."""
        try:
            if regles.reafficher_les_outils_manquants(projet, etat):
                self._noter(projet, "des outils manquent sur le poste : la décision « Environnement du poste à "
                                    "compléter » est reposée")
        except (regles.Refus, regles.ErreurMoteur) as e:
            self._noter(projet, f"outils manquants : {e}")

    def _valider_les_lecons(self, projet, etat):
        """Réglage `lecons_auto` (relu à chaque passage) : les leçons « à valider » sont validées d'elles-mêmes à l'étage
        qu'elles proposent, comme un « Valider » du Directeur (même appel `lecon appliquer`, en un seul lot). Une leçon
        que l'outil refuse reste « à valider » et n'est pas réessayée avant un redémarrage : rien n'est bloqué."""
        if projet.fichier_reglages is not None:
            try:
                projet.lecons_auto = reglages_bureau.charger(projet.fichier_reglages)["lecons_auto"]
            except reglages_bureau.ReglagesInvalides:
                pass        # des réglages illisibles ne changent pas le dernier état connu
        if not projet.lecons_auto:
            return
        essayees = etat.setdefault("lecons_auto_essayees", set())
        try:
            en_attente = regles.lancer(projet, "detail", {"lecons": True})["lecons"]
            lot = [{"id": x["id"], "verdict": "valider", "etage": x.get("etage_propose") or "projet"}
                   for x in en_attente if x["id"] not in essayees]
            if not lot:
                return
            essayees.update(x["id"] for x in lot)
            r = regles.lancer(projet, "lecon", {"action": "appliquer", "lot": lot})
        except (regles.Refus, regles.ErreurMoteur) as e:
            self._noter(projet, f"leçons automatiques : {e}")
            return
        faites = [x for x in r["resultats"] if x.get("ok")]
        if faites:
            self._noter(projet, f"{len(faites)} leçon(s) validée(s) automatiquement")
        for x in r["resultats"]:
            if not x.get("ok"):
                self._noter(projet, f"leçon {x['id']} laissée à valider : {x.get('refus')}")

    def _ecritures_en_attente(self, projet, etat):
        """Les leçons validées dont l'écriture dans la mémoire de la skill n'a pas abouti (dépôt occupé, push refusé) :
        réessayées toutes les 5 minutes, sans nouveau clic. L'outil ne touche pas au dépôt quand rien n'attend."""
        maintenant = self.horloge()
        if maintenant - etat.get("lecons_essayees", float("-inf")) < ECRITURE_LECONS_TOUS_LES_S:
            return
        etat["lecons_essayees"] = maintenant
        try:
            r = regles.lancer(projet, "lecon", {"action": "reessayer"})
        except (regles.Refus, regles.ErreurMoteur) as e:
            self._noter(projet, f"leçons en attente : {e}")
            return
        if r.get("ecrites"):
            self._noter(projet, f"{r['ecrites']} leçon(s) en attente enfin écrite(s) dans la mémoire de la skill")

    def _quota(self, projet):
        maintenant = self.horloge()
        if maintenant - self.dernier_quota.get(str(projet.factory), 0) < QUOTA_TOUS_LES_S:
            return
        self.dernier_quota[str(projet.factory)] = maintenant
        try:
            regles.lancer(projet, "partenaires", {"action": "quota"})
        except (regles.Refus, regles.ErreurMoteur):
            pass    # les partenaires sont facultatifs : rien ne bloque sans eux

    # --- Les installations d'outils : prioritaires sur tout le bureau.

    def _installations(self):
        """Dès qu'une installation d'outil est prête dans un projet : plus aucun agent neuf ne part nulle part (la pause
        globale, que chaque projet lit dans `pause_globale`), et elle part tout de suite, sans condition de charge ; une
        seule à la fois, dans l'ordre d'arrivée. Les agents déjà au travail finissent ; les jugements et les demandes
        continuent. La pause se lève d'elle-même quand plus aucune installation n'est prête ni en cours ; le poste est
        alors revérifié pour chaque projet (un outil qui manque encore revient dans une décision)."""
        pretes, en_cours = {}, None
        for projet in list(self.projets):
            cle, etat = str(projet.factory), self._etat(projet)
            try:
                for t in regles.installations_pretes(projet, etat):
                    if self._echecs_installation.get((cle, t["id"]), 0) < ESSAIS_INSTALLATION:
                        pretes[(cle, t["id"])] = projet
                vues = regles.installations_en_cours(projet, etat)
                if vues and en_cours is None:
                    en_cours = (projet, vues[0]["id"])
            except Exception as e:     # un projet illisible ne retient pas les autres
                self._noter(projet, f"installations : {e}")
        self.file_installations = ([x for x in self.file_installations if x in pretes]
                                   + [x for x in pretes if x not in self.file_installations])
        if en_cours is None and self.file_installations:
            cle, tid = self.file_installations[0]
            projet = pretes[(cle, tid)]
            try:
                actions = regles.demarrer_installation(projet, self._etat(projet), tid)
            except Exception as e:
                actions = []
                self._echecs_installation[(cle, tid)] = self._echecs_installation.get((cle, tid), 0) + 1
                self._noter(projet, f"installation {tid} : {e}")
            if actions:
                self.file_installations.pop(0)
                en_cours = (projet, tid)
                self._executer(projet, actions)
        self._poser_la_pause(pretes, en_cours)

    def _poser_la_pause(self, pretes, en_cours):
        """Le texte de la pause (l'installation en cours, sinon la première de la file) pour tous les projets, dans le
        fichier que lit le bureau ; levée, elle fait revérifier le poste partout."""
        cible = en_cours
        if cible is None and self.file_installations:
            cle, tid = self.file_installations[0]
            cible = (pretes[(cle, tid)], tid)
        texte = outils = None
        if cible is not None:
            projet, tid = cible
            try:
                outils = regles.outils_de_la_tache(projet, tid)
            except (regles.Refus, regles.ErreurMoteur):
                outils = []
            texte = f"Pause : installation de {', '.join(outils) or 'l’environnement du poste'} ({projet.nom})"
        for p in self.projets:
            p.pause_globale = texte
        if self.bureau is not None:
            fichier = attente.chemin_pause(self.bureau)
            if texte is None:
                self._effacer(fichier)
            else:
                self._ecrire(fichier, {"texte": texte, "projet": cible[0].nom, "outils": outils})
        vue = texte is not None
        if self._installation_vue and not vue:
            for projet in list(self.projets):
                self._outils_manquants(projet, self._etat(projet))
        self._installation_vue = vue
        self.pause_installation = None if texte is None else {"texte": texte, "projet": cible[0].nom, "outils": outils}

    def _dire_l_attente_de_charge(self, projet, etat):
        """Une tâche prête que la charge retient, des places libres qui attendent une validation du Directeur : le bureau
        le dit (carte de la tâche et barre), à chaque passage ; et pourquoi chaque tâche prête ne part pas."""
        for fichier, a in ((attente.chemin_charge(projet.factory.parent), etat.get("attente_charge")),
                           (attente.chemin_places(projet.factory.parent), etat.get("attente_validation")),
                           (attente.chemin_taches(projet.factory.parent), etat.get("attente_taches"))):
            if a:
                self._ecrire(fichier, a)
            else:
                self._effacer(fichier)

    def _ecrire(self, fichier, objet):
        """Écrit pour le bureau ; un contenu inchangé n'est réécrit que de temps en temps (il reste frais pour le bureau)."""
        contenu, maintenant = json.dumps(objet, sort_keys=True), self.horloge()
        avant = self._ecrits.get(str(fichier))
        if avant and avant[0] == contenu and maintenant - avant[1] < REECRIRE_TOUS_LES_S:
            return
        attente.ecrire(fichier, objet)
        self._ecrits[str(fichier)] = (contenu, maintenant)

    def _effacer(self, fichier):
        if self._ecrits.pop(str(fichier), None) is not None or Path(fichier).exists():
            attente.effacer(fichier)

    # --- Les demandes.

    def _demandes(self, projet, etat):
        prises = etat.setdefault("prises", set())
        en_attente = regles.lancer(projet, "demandes")["demandes"]
        en_attente.sort(key=lambda d: d.get("type") != "message")     # la discussion reste vivante : messages d'abord
        lecons = [d for d in en_attente if d.get("type") == "lecon" and d["id"] not in prises]
        if len(lecons) >= 2:     # « Valider toutes les leçons » : une seule synchronisation du dépôt de la skill
            prises.update(d["id"] for d in lecons)
            try:
                regles.traiter_lecons(projet, lecons, etat)
            except Exception as e:
                for d in lecons:
                    regles._terminer(projet, {"demande": d["id"]}, f"Le moteur a rencontré une erreur : {e}")
                self._noter(projet, f"leçons : {e}")
        for d in en_attente:
            if d["id"] in prises:
                continue
            prises.add(d["id"])
            try:
                actions = regles.traiter_demande(projet, d, etat)
            except Exception as e:
                regles._terminer(projet, {"demande": d["id"]}, f"Le moteur a rencontré une erreur : {e}")
                self._noter(projet, f"demande {d['id']} : {e}")
                continue
            self._executer(projet, actions)

    # --- Les actions asynchrones : jugements et départs d'agents.

    def _executer(self, projet, actions):
        file = list(actions)
        while file:
            action = file.pop(0)
            try:
                if action[0] == "lancer":
                    regles.lancer(projet, action[1], action[2])
                elif action[0] == "juger":
                    file += self._juger(projet, action)
                elif action[0] == "agent":
                    self._partir(projet, action)
            except (regles.Refus, regles.ErreurMoteur) as e:
                self._signaler(projet, action, e)

    def _signaler(self, projet, action, erreur):
        """Une action refusée par l'outil : visible au bureau quand on sait où (la demande qu'elle servait)."""
        self._noter(projet, f"{action[0]} : {erreur}")
        if action[0] == "juger":
            regles._terminer(projet, action[3], f"Je n'ai pas pu aller au bout : {erreur}")

    def _juger(self, projet, action):
        _, type_, dossier, suite = action
        # le modèle donné par la suite (l'analyse d'un blocage : celui de l'orchestrateur du projet), sinon celui du type
        decision = jugement.juger(type_, dossier, couche=projet.couche, appeler=self.appeler, modele=suite.get("modele"))
        self._noter_usages(projet, decision.usages, AGENT_ORCHESTRATEUR, ETAPE_ORCHESTRATION, tache=suite.get("tache"))
        return regles.appliquer_jugement(projet, type_, decision, suite, self._etat(projet))

    def _partir(self, projet, action):
        _, cle, taches, matiere = action
        etat = self._etat(projet)
        depart = regles.lancer(projet, "depart", {"agent": cle, "tache": taches[0]} if len(taches) == 1
                               else {"agent": cle, "taches": taches, "moteur": True})["message"]
        d = etat["departs"].get(taches[0]) or {}
        fiche = fi.trouver(fi.lire_toutes(fa.lire(projet.factory)["fiches"]), cle)
        if fiche is None:
            raise regles.Refus(f"agent inconnu : {cle}")
        modele = (d.get("modele") or fiche["modele"] or "Sonnet").lower()
        fiche = self._fiche_avec_accord(self._fiche_du_metier(projet, fiche, taches), modele, d.get("fable_accorde"))
        if fiche["lieu"] != "cloud":
            infos = {"genre": "tache", "tache": taches[0], "taches": list(taches), "agent": cle, "modele": modele,
                     "lot": d.get("lot"), "matiere": matiere,
                     **({"fable_accorde": True} if d.get("fable_accorde") else {})}
            self._lancer_local(projet, fiche, modele, taches[0], infos, depart, matiere, tache=taches[0],
                               lot=d.get("lot"))
            return

        def travail():
            e = self._partir_cloud(projet, etat, depart, fiche, modele, taches, d)
            if e is not None:
                self.retours.put((projet, e))

        if self.synchrone:
            travail()
        else:
            threading.Thread(target=travail, name=f"agent-{cle}", daemon=True).start()

    @staticmethod
    def _fiche_du_metier(projet, fiche, taches):
        """Un agent polyvalent est lancé avec ses outils plus ceux du métier de chaque tâche (`Outils :` du brief) :
        pour cette tâche, il est le spécialiste de ce métier. Une fiche à l'ancienne reste telle quelle."""
        if not regles._polyvalent(fiche):
            return fiche
        siens = fi.outils(fiche)
        outils = list(siens)
        for tid in taches:
            try:
                role = regles._tache(projet, tid).get("role")
            except (regles.Refus, regles.ErreurMoteur):
                continue
            m = regles._metier(projet, role)
            if m and m.get("outils"):
                outils += [o for o in fi.outils({"outils": m["outils"]}) if o not in outils]
        return {**fiche, "outils": ", ".join(outils)} if outils != siens else fiche

    @staticmethod
    def _fiche_avec_accord(fiche, modele, accord):
        """La fiche avec laquelle l'agent est lancé : un agent polyvalent sur Fable porte, pour ce départ seulement,
        l'accord que le Directeur a donné à la tâche (`fable_accorde` du départ) ; sans lui, `agents.executer_agent`
        refuse Fable."""
        if modele == "fable" and accord is True and not fi.fable_accorde(fiche):
            return {**fiche, "modele": "Fable", "fable": f"accordé par le Directeur le {time.strftime('%Y-%m-%d')}"}
        return fiche

    # --- Les agents locaux : détachés du moteur (`moteur.detache`), retrouvés quand il redémarre.

    def _lancer_local(self, projet, fiche, modele, cle_registre, infos, depart, matiere, *, tache, lot,
                      rattacher=False, reprendre=None, reponse=None):
        """L'agent local, dans son processus détaché (ou celui qui tourne déjà pour cette tâche) ; son `Execution`
        revient par la file `retours`. `reponse` : une réponse aux questions de l'utilisateur, pas une tâche."""
        executeur = self._registre(projet).executeur(cle_registre, infos, rattacher=rattacher)
        executeur.rattacher, executeur.registre = rattacher, self._registre(projet)
        plus = {"reprendre": reprendre} if reprendre else {}

        def travail():
            e = self.executer_agent(depart, matiere, agent=fiche, modele=modele, dossier_projet=str(projet.dossier),
                                    tache=tache, lot=lot, executeur=executeur, **plus)
            if reponse is not None:
                e.reponse = reponse
            self.retours.put((projet, e))

        if self.synchrone:
            travail()
        else:
            threading.Thread(target=travail, name=f"agent-{fiche['cle']}", daemon=True).start()

    def _surveiller_les_commandes(self, projet):
        """Toutes les `figes.SURVEILLER_TOUS_LES_S` : un programme lancé par un agent local du projet (ou laissé par
        lui) dont le temps processeur ne bouge plus depuis `figes.FIGE_MIN` minutes est arrêté ; la tâche le dit à son
        journal. Rien à faire sans agent noté ; une mesure impossible ne fait rien."""
        d = detache.dossier(projet.factory.parent)
        try:
            if not any(d.glob("*.json")) and not (d / figes.FICHIER_FAMILLES).exists():
                return
        except OSError:
            return
        cle, maintenant = str(projet.factory), time.monotonic()
        if maintenant - self._surveille.get(cle, float("-inf")) < figes.SURVEILLER_TOUS_LES_S:
            return
        self._surveille[cle] = maintenant
        if self._processus_du_tour is None:
            try:
                self._processus_du_tour = self.surveillance.lister() or {}
            except Exception:
                self._processus_du_tour = {}
        if not self._processus_du_tour:
            return
        for a in self.surveillance.passer(d, self._processus_du_tour):
            texte = figes.texte_journal(a)
            self._noter(projet, f"{a.get('tache')} : {texte}")
            if a.get("tache"):
                try:
                    regles.lancer(projet, "tache", {"id": a["tache"], "journal": [texte]})
                except (regles.Refus, regles.ErreurMoteur) as e:
                    self._noter(projet, f"commande figée ({a['tache']}) : {e}")

    def _rattacher_les_agents(self, projet, etat):
        """Au démarrage : les agents détachés laissés par le moteur d'avant. Vivant, il est attendu ; mort avec son
        résultat, ce résultat est lu ; mort sans résultat, il est oublié (la tâche, active, repart par `orphelines`)."""
        registre = self._registre(projet)
        entrees = registre.entrees()
        if not entrees:
            return
        fiches = fi.lire_toutes(fa.lire(projet.factory)["fiches"])
        for info in entrees:
            cle = info["cle"]
            issue = registre.issue(cle)
            fiche = fi.trouver(fiches, info.get("agent")) if info.get("agent") else None
            if issue == "mort" and info.get("genre") != "reponse" and registre.arret_demande(cle):
                # arrêté depuis le bureau pendant que le moteur était coupé : la tâche ne repart pas d'elle-même
                taches = [x for x in info.get("taches") or [info.get("tache") or cle] if isinstance(x, str)]
                try:
                    regles.arret_depuis_le_bureau(projet, etat, taches)
                except (regles.Refus, regles.ErreurMoteur) as e:
                    self._noter(projet, f"agent arrêté ({cle}) : {e}")
                registre.effacer(cle)
                continue
            if fiche is None or (issue not in ("vivant", "resultat") and info.get("genre") != "reponse"):
                registre.effacer(cle)
                continue
            tid = info.get("tache") or cle
            modele = (info.get("modele") or fiche["modele"] or "Sonnet").lower()
            fiche = self._fiche_avec_accord(fiche, modele, info.get("fable_accorde"))
            if info.get("genre") == "reponse":     # une réponse aux questions : attendue, ou redemandée
                questions = [q for q in info.get("questions") or [] if isinstance(q, str)]
                if issue not in ("vivant", "resultat"):
                    registre.effacer(cle)
                    if questions:
                        self._repondre(projet, etat, tid, fiche["cle"], questions, info.get("session"), modele=modele)
                    continue
                self._lancer_local(projet, self._fiche_de_reponse(fiche), modele, cle, info, "", "", tache=tid,
                                   lot=None, rattacher=True, reponse={"fonctionnalite": info.get("fonctionnalite"),
                                                                      "questions": questions, "cle": cle})
                continue
            taches = [x for x in info.get("taches") or [tid] if isinstance(x, str)] or [tid]
            etat["departs"][tid] = {"agent": fiche["cle"], "taches": taches, "matiere": info.get("matiere") or "",
                                    "modele": modele, "lot": info.get("lot"), "suite": None}
            etat["en_cours"].add(tid)
            try:
                regles.lancer(projet, "tache", {"id": tid, "journal": [
                    "Le moteur a repris : l'agent travaille encore, son résultat sera lu." if issue == "vivant"
                    else "Le moteur a repris : l'agent avait fini, son résultat est lu."]})
            except (regles.Refus, regles.ErreurMoteur) as e:
                self._noter(projet, f"agent repris ({tid}) : {e}")
            self._lancer_local(projet, fiche, modele, cle, info, "", info.get("matiere") or "", tache=tid,
                               lot=info.get("lot"), rattacher=True)

    @staticmethod
    def _fiche_de_reponse(fiche):
        """L'agent qui répond à une question ne travaille plus : il lit, il ne modifie rien."""
        return {**fiche, "outils": OUTILS_DE_REPONSE}

    def _transmettre_les_questions(self, projet, etat, e, actions):
        """Les questions posées pendant la tâche : dans la matière de la tâche si elle repart (nouvel essai, réponse
        refusée), sinon l'agent reprend sa session pour y répondre."""
        questions = detache.prendre_questions(projet.factory.parent, e.tache)
        if not questions:
            return actions
        bloc = texte_des_questions(questions)
        for i, a in enumerate(actions):
            if a[0] == "agent" and a[2] and a[2][0] == e.tache:
                matiere = (a[3] or "").rstrip() + "\n\n" + bloc
                actions[i] = (a[0], a[1], a[2], matiere)
                if e.tache in etat["departs"]:
                    etat["departs"][e.tache]["matiere"] = matiere
                return actions
        modele = (etat["departs"].get(e.tache) or {}).get("modele")
        self._repondre(projet, etat, e.tache, e.agent, questions, e.session, modele=modele,
                       rendu=((e.rapport or {}).get("message") or {}).get("texte"))
        return actions

    def _repondre(self, projet, etat, tid, agent, questions, session, *, modele=None, rendu=None):
        fiche = fi.trouver(fi.lire_toutes(fa.lire(projet.factory)["fiches"]), agent)
        fid = regles.lancer(projet, "detail", {"tache": tid}).get("fonctionnalite")
        if fiche is None or fiche["lieu"] == "cloud" or not fid:
            self._noter(projet, f"questions pour {agent} sans réponse possible : {' / '.join(questions)}")
            return
        modele = (modele or fiche["modele"] or "Sonnet").lower()
        if modele == "fable" and not fi.fable_accorde(fiche):
            modele = "opus"      # une réponse aux questions ne tourne jamais sur Fable sans l'accord de la fiche
        cle = f"{tid}.reponse"
        infos = {"genre": "reponse", "tache": tid, "agent": fiche["cle"], "modele": modele, "fonctionnalite": fid,
                 "questions": questions, "session": session}
        self._lancer_local(projet, self._fiche_de_reponse(fiche), modele, cle, infos,
                           depart_de_reponse(tid, questions, session, rendu), "", tache=tid, lot=None,
                           reprendre=session, reponse={"fonctionnalite": fid, "questions": questions, "cle": cle})

    def _poser_la_reponse(self, projet, e):
        """La réponse de l'agent aux questions de l'utilisateur, dans la discussion (sinon pourquoi elle manque)."""
        fid = e.reponse.get("fonctionnalite")
        texte = ((e.rapport or {}).get("message") or {}).get("texte") if e.rapport else None
        if not fid:
            return
        if isinstance(texte, str) and texte.strip():
            regles.lancer(projet, "message", {"fonctionnalite": fid, "auteur": e.agent, "texte": texte.strip()})
            return
        regles._dire(projet, fid, f"{regles.prenom_de(projet, e.agent)} n'a pas pu répondre à votre question "
                                  f"({e.erreur or 'réponse vide'}) : posez-la de nouveau si elle tient toujours.")

    # --- Les agents cloud : une session par départ, relevée par le dépôt.

    def _partir_cloud(self, projet, etat, depart, fiche, modele, taches, d):
        """Lance la session (ou envoie la suite à la même session). `None` si elle tourne ; sinon une `Execution` en
        échec, que `regles.traiter_retour` reprend (un nouvel essai, puis la tâche bloquée)."""
        tid = taches[0]
        info = etat["cloud"].get(tid)
        try:
            if info and info.get("session") and d.get("suite"):
                self.cloud.envoyer_suite(info["session"], d["suite"], dossier_projet=str(projet.dossier))
                info["depuis"] = self.horloge()
                return None
            self.commit(projet.dossier, f"Factory : départ de {fiche['cle']}")
            lancee = self._lancer_ou_envoyer(projet, etat, depart, fiche, modele)
        except cloud.ErreurCloud as e:
            return agents.Execution(tid, fiche["cle"], d.get("lot"), erreur=f"session cloud : {e.raison}", modele=modele)
        etat["cloud_releve"] = self.horloge()      # la première relève, une minute après le départ
        etat["cloud"][tid] = {"session": lancee["session"], "adresse": lancee["adresse"], "depuis": self.horloge(),
                              "taches": list(taches), "agent": fiche["cle"], "modele": modele, "lot": d.get("lot"),
                              "muette_dite": False, "vu": None}
        try:
            regles.lancer(projet, "tache", {"id": tid, "journal": [
                f"Session cloud {lancee['session']} ({modele})" + (f" : {lancee['adresse']}" if lancee["adresse"] else "")]})
            regles.lancer(projet, "session", {"agent": fiche["cle"], "session": lancee["adresse"] or lancee["session"]})
            # la démarche manuelle posée avant pour cet agent n'a plus lieu d'être : le moteur a créé la session
            for dec in regles.lancer(projet, "etat", {})["decisions"]:
                if dec.get("genre") == "session_cloud" and dec.get("agent") == fiche["cle"]:
                    regles.lancer(projet, "decision", {"action": "lever", "id": dec["id"]})
        except (regles.Refus, regles.ErreurMoteur) as e:
            self._noter(projet, f"session cloud non notée : {e}")
        return None

    def _lancer_ou_envoyer(self, projet, etat, depart, fiche, modele):
        """Une nouvelle session ; si le moteur ne peut pas la créer et que le Directeur a inscrit une session pour cet
        agent (la démarche manuelle), le départ est envoyé à cette session. Lève `ErreurCloud` si rien ne marche. Le
        réglage `cloud_dossier_approuve` est relu ici : la case cochée au bureau vaut sans redémarrer le moteur."""
        if getattr(projet, "fichier_reglages", None) is not None:
            try:
                projet.cloud_dossier_approuve = reglages_bureau.charger(projet.fichier_reglages)["cloud_dossier_approuve"]
            except reglages_bureau.ReglagesInvalides:
                pass        # des réglages illisibles ne changent pas le dernier état connu
        try:
            return self.cloud.lancer_session(depart, dossier_projet=str(projet.dossier), modele=modele,
                                             approuver_dossier=getattr(projet, "cloud_dossier_approuve", False))
        except cloud.ErreurCloud as e:
            session = etat.get("sessions_cloud", {}).get(fiche["cle"]) or self._session_inscrite(projet, fiche["cle"])
            if not session:
                raise
            try:
                self.cloud.envoyer_suite(session, depart, dossier_projet=str(projet.dossier))
            except cloud.ErreurCloud as e2:
                raise cloud.ErreurCloud(e.raison if e2.raison == e.raison
                                        else f"{e.raison} ; envoi à la session {session} : {e2.raison}")
            return {"session": session, "adresse": f"{cloud.ADRESSE_CODE}/{session}"}

    @staticmethod
    def _session_inscrite(projet, cle):
        """L'identifiant de la session inscrite pour l'agent (table des sessions), s'il a la forme d'une session."""
        try:
            agent = next((a for a in regles.lancer(projet, "etat")["agents"] if a["cle"] == cle), {})
        except (regles.Refus, regles.ErreurMoteur):
            return None
        lue = cloud.lire_session(agent.get("session") or "")
        return lue["session"] if lue else None

    def _relever_le_cloud(self, projet, etat):
        """Toutes les minutes : le dépôt est relevé ; un rapport trouvé est appliqué comme un rapport local, puis la
        branche est fusionnée. Une session muette trop longtemps : la décision revient au Directeur."""
        sessions = etat.get("cloud") or {}
        if not sessions:
            return
        maintenant = self.horloge()
        if maintenant - etat.get("cloud_releve", 0) < CLOUD_TOUS_LES_S:
            return
        etat["cloud_releve"] = maintenant
        for info in list(sessions.values()):
            if info.get("depuis") is None:
                info["depuis"] = maintenant
        try:
            trouves = self.cloud.chercher_rapports(str(projet.dossier), list(sessions))
        except cloud.ErreurCloud as e:
            self._noter(projet, f"relève du cloud : {e.raison}")
            trouves = {}
        for tid, (branche, r) in trouves.items():
            info = sessions[tid]
            marque = json.dumps(r, sort_keys=True)
            if info.get("vu") == marque:
                continue                  # déjà appliqué : le fichier reste sur la branche
            info["vu"] = marque
            if r["statut"] == "fait":
                del sessions[tid]
            e = agents.Execution(tid, info["agent"], info.get("lot"), rapport=r, estime=r.get("usage_estime"),
                                 modele=info["modele"])
            e.branche, e.adresse = branche, info.get("adresse")
            self.retours.put((projet, e))
        for tid, info in list(sessions.items()):
            if tid not in trouves and not info.get("muette_dite") and maintenant - info["depuis"] > CLOUD_MUETTE_S:
                info["muette_dite"] = True
                try:
                    regles.question_session_muette(projet, etat, tid, info.get("adresse"))
                except (regles.Refus, regles.ErreurMoteur) as ex:
                    self._noter(projet, f"session muette : {ex}")

    def _retrouver_les_sessions(self, projet, etat):
        """Au redémarrage du moteur : une tâche cloud active garde sa session (lue dans son journal), le moteur la relève
        de nouveau au lieu d'en lancer une autre."""
        court = regles.lancer(projet, "etat")
        for t in court["taches"]:
            if not (t["active"] and t.get("agent") and regles.fiche_cloud(court, t["agent"])) or t["id"] in etat["cloud"]:
                continue
            journal = regles.lancer(projet, "detail", {"tache": t["id"]}).get("journal") or []
            vu = next((m.group(1, 2) for j in reversed(journal)
                       if (m := re.match(r"Session cloud (\S+) \((\w+)\)", j["texte"]))), None)
            if vu:
                etat["cloud"][t["id"]] = {"session": vu[0], "adresse": None, "depuis": self.horloge(),
                                          "taches": [t["id"]], "agent": t["agent"], "modele": vu[1], "lot": None,
                                          "muette_dite": False, "vu": None}

    def _fusionner(self, projet, etat, e):
        """Après un rapport « fait » venu d'une branche `claude/…` : la fusionner. Un conflit devient une question au
        Directeur, avec la branche et l'adresse de la session."""
        raison = self.cloud.fusionner(str(projet.dossier), e.branche)
        if raison is None:
            return
        self._noter(projet, f"fusion de {e.branche} : {raison}")
        self._executer(projet, regles.fusion_impossible(projet, etat, e.tache, e.agent, e.branche, e.adresse, raison))

    def _retours_des_agents(self, projet, etat):
        garde = []
        while True:
            try:
                p, e = self.retours.get_nowait()
            except queue.Empty:
                break
            if p is not projet:
                garde.append((p, e))
                continue
            if getattr(e, "reponse", None) is not None:     # la réponse aux questions de l'utilisateur
                self._noter_usages(projet, e.usages, e.agent, None, tache=e.tache)
                try:
                    self._poser_la_reponse(projet, e)
                except (regles.Refus, regles.ErreurMoteur) as ex:
                    self._noter(projet, f"réponse de {e.agent} : {ex}")
                self._registre(projet).effacer(e.reponse.get("cle") or f"{e.tache}.reponse")
                continue
            self._noter_usages(projet, e.usages, e.agent, None, tache=e.tache, lot=e.lot)
            if e.estime is not None:      # un agent cloud : son estimation, notée comme telle (`total`)
                self._noter_estimation(projet, e)
            try:
                actions = regles.traiter_retour(projet, e, etat)
            except (regles.Refus, regles.ErreurMoteur) as ex:
                self._noter(projet, f"retour de {e.agent} : {ex}")
                continue
            finally:
                if e.estime is None:      # un agent local : son résultat est appliqué, ses fichiers sont oubliés
                    self._registre(projet).effacer(e.tache)
            try:
                actions = self._transmettre_les_questions(projet, etat, e, list(actions))
            except (regles.Refus, regles.ErreurMoteur, OSError) as ex:
                self._noter(projet, f"questions pour {e.agent} : {ex}")
            self._executer(projet, actions)
            if e.rapport is not None:
                self.commit(projet.dossier, "Factory : " + self._produit(e))
                if getattr(e, "branche", None) and e.rapport["statut"] == "fait":
                    self._fusionner(projet, etat, e)    # après le commit : l'arbre est propre
        for x in garde:
            self.retours.put(x)

    def _noter_estimation(self, projet, e):
        modele = appel.MODELES_API.get(e.modele or "", e.modele or "inconnu")
        try:
            regles.lancer(projet, "usage", {"modele": modele, "agent": e.agent, "tache": e.tache, "total": e.estime})
        except (regles.Refus, regles.ErreurMoteur) as ex:
            self._noter(projet, f"usage estimé non noté : {ex}")

    @staticmethod
    def _produit(e):
        texte = ((e.rapport or {}).get("message") or {}).get("texte") or f"tâche {e.tache} ({e.agent})"
        return " ".join(texte.split())[:70]

    # --- La facturation : chaque appel, réussi ou non.

    def _noter_usages(self, projet, usages, agent, etape, *, tache=None, lot=None):
        for u in usages:
            entree = {"modele": u["modele"], "agent": agent, "entree": u["entree"], "sortie": u["sortie"],
                      "cache_lecture": u["cache_lecture"], "cache_ecriture": u["cache_ecriture"]}
            if etape:
                entree["etape"] = etape
            if u.get("abonnement"):   # l'instantané d'abonnement lu au début de l'appel
                entree["abonnement"] = u["abonnement"]
            try:
                if lot:
                    try:
                        regles.lancer(projet, "usage", {**entree, "lot": lot})
                        continue
                    except regles.Refus:
                        pass    # un lot ne se note qu'une fois : le reste va sur la première tâche
                if tache:
                    entree["tache"] = tache
                regles.lancer(projet, "usage", entree)
            except (regles.Refus, regles.ErreurMoteur) as e:
                self._noter(projet, f"usage non noté : {e}")
