"""La boucle du moteur : un passage (`tour`) toutes les 2 s, pour chaque projet du bureau.

Un passage, par projet, dans cet ordre (conception, section 4.1) :
1. la présence (`presence.json`, comme `lancer guetter`) ; au premier passage : les partenaires (`detecter`) et les
   tâches orphelines (active, mais plus d'agent) relancées une fois ;
2. les demandes du bureau, les messages de discussion d'abord, chacune une seule fois ;
3. les retours des agents terminés : usage noté, rapport appliqué, commit et push ;
4. `avancer` : ce que dit le parcours à chaque étape (rien en pause : les demandes, elles, sont toujours traitées) ;
5. les quotas des partenaires (l'outil ne relit qu'une fois par heure chacun).

Tout passe par `regles` donc par `lancer`. Un appel de jugement est synchrone ; un agent tourne dans un fil (un par
exécution) et rend son `Execution` dans une file lue au passage suivant. Chaque appel, de jugement ou d'agent, est noté
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
from moteur import agents, appel, cloud, jugement, regles
from orchestrateur import factory as fa
from orchestrateur import fiches as fi
from orchestrateur import guetteur

PAS_S = 2
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
    try:
        projet.cloud_max = reglages_bureau.charger(fichier)["agents_cloud_max"]
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

    def git(*args):
        return subprocess.run(["git", *args], cwd=str(dossier), capture_output=True, env=env, timeout=DELAI_GIT_S,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    try:
        git("add", "-A")
        if git("diff", "--cached", "--quiet").returncode == 0:
            return False
        if git("commit", "-m", message).returncode != 0:
            return False
        git("push")
        return True
    except (OSError, subprocess.SubprocessError):
        return False


class Moteur:
    """`projets` : les `regles.Projet` tenus ; `bureau` (facultatif) : le fichier du bureau, relu à chaque passage pour
    prendre les projets ajoutés. `executer_agent`, `commit` et `synchrone` (les agents tournent dans l'appel, pas dans
    un fil) sont là pour les essais."""

    def __init__(self, projets, *, appeler=appel.appeler, horloge=time.time, bureau=None, environ=None,
                 executer_agent=agents.executer_agent, commit=commit_et_push, synchrone=False, session_cloud=None):
        self.appeler, self.horloge, self.bureau, self.environ = appeler, horloge, bureau, environ
        self.executer_agent, self.commit, self.synchrone = executer_agent, commit, synchrone
        self.cloud = session_cloud or cloud      # le module (ou un faux) qui parle aux sessions cloud
        self.projets, self.etats, self.retours, self.journal = [], {}, queue.Queue(), []
        self.dernier_quota = {}
        self.file_installations = []       # (clé du projet, tâche) des installations prêtes, dans l'ordre d'arrivée
        self.pause_installation = None     # {texte, projet, outils} quand une installation retient tout le bureau
        self._installation_vue = False     # une installation était en cours ou attendue au passage d'avant
        self._ecrits = {}                  # fichier -> (contenu, heure) : un fichier inchangé n'est pas réécrit à chaque passage
        self._echecs_installation = {}
        for p in projets:
            self._ajouter(p)

    def _ajouter(self, projet):
        if getattr(projet, "bureau", None) is None:
            projet.bureau = self.bureau     # les mesures d'usage des projets du bureau servent à estimer un workflow
        projet.installations_a_part = True  # les installations sont lancées par `_installations`, avant tout le reste
        self.projets.append(projet)
        self.etats[str(projet.factory)] = regles.nouvel_etat()

    def _etat(self, projet):
        return self.etats[str(projet.factory)]

    def _noter(self, projet, texte):
        self.journal.append(f"{projet.nom} : {texte}")

    # --- Un passage.

    def tour(self):
        self._prendre_les_projets_ajoutes()
        self._installations()
        for projet in list(self.projets):
            try:
                self._tour_projet(projet)
            except Exception as e:      # une erreur d'un projet n'arrête ni la boucle ni les autres projets
                self._noter(projet, f"erreur au passage : {e}")

    def tourner(self, arret):
        while not arret.is_set():
            self.tour()
            arret.wait(PAS_S)

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
        self._ecritures_en_attente(projet, etat)
        self._relever_le_cloud(projet, etat)
        self._retours_des_agents(projet, etat)
        self._executer(projet, regles.avancer(projet, etat))
        self._dire_l_attente_de_charge(projet, etat)
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
        self._executer(projet, regles.orphelines(projet, etat))
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
        """Une tâche prête que la charge retient : le bureau le dit (carte de la tâche et barre), à chaque passage."""
        fichier = attente.chemin_charge(projet.factory.parent)
        a = etat.get("attente_charge")
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
        decision = jugement.juger(type_, dossier, couche=projet.couche, appeler=self.appeler)
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
        modele = (d.get("modele") or fiche["modele"]).lower()

        def travail():
            if fiche["lieu"] == "cloud":
                e = self._partir_cloud(projet, etat, depart, fiche, modele, taches, d)
                if e is None:
                    return
            else:
                e = self.executer_agent(depart, matiere, agent=fiche, modele=modele,
                                        dossier_projet=str(projet.dossier), tache=taches[0], lot=d.get("lot"))
            self.retours.put((projet, e))

        if self.synchrone:
            travail()
        else:
            threading.Thread(target=travail, name=f"agent-{cle}", daemon=True).start()

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
            lancee = self.cloud.lancer_session(depart, dossier_projet=str(projet.dossier), modele=modele)
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
        except (regles.Refus, regles.ErreurMoteur) as e:
            self._noter(projet, f"session cloud non notée : {e}")
        return None

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
        t = regles.lancer(projet, "detail", {"tache": e.tache})
        regles.lancer(projet, "tache", {"id": e.tache, "journal": [f"Fusion de la branche {e.branche} impossible : {raison}"]})
        if t.get("fonctionnalite"):
            regles._question(projet, t["fonctionnalite"],
                             f"La branche « {e.branche} » de l'agent {e.agent} n'a pas pu être fusionnée ({raison})"
                             + (f". Sa session : {e.adresse}." if e.adresse else ".")
                             + " Réglez le conflit dans le dépôt, puis dites-moi de continuer.",
                             ["C'est réglé, continuez", "Laissez cette branche de côté"])

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
            self._noter_usages(projet, e.usages, e.agent, None, tache=e.tache, lot=e.lot)
            if e.estime is not None:      # un agent cloud : son estimation, notée comme telle (`total`)
                self._noter_estimation(projet, e)
            try:
                actions = regles.traiter_retour(projet, e, etat)
            except (regles.Refus, regles.ErreurMoteur) as ex:
                self._noter(projet, f"retour de {e.agent} : {ex}")
                continue
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
