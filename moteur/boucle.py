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
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from bureau import reglages as reglages_bureau
from moteur import agents, appel, jugement, regles
from orchestrateur import factory as fa
from orchestrateur import fiches as fi
from orchestrateur import guetteur

PAS_S = 2
QUOTA_TOUS_LES_S = 60
BUREAU_PAR_DEFAUT = "~/MyIAFactory/bureau.json"
AGENT_ORCHESTRATEUR = "orchestrateur"
ETAPE_ORCHESTRATION = "orchestration"
DELAI_GIT_S = 60


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
                 executer_agent=agents.executer_agent, commit=commit_et_push, synchrone=False):
        self.appeler, self.horloge, self.bureau, self.environ = appeler, horloge, bureau, environ
        self.executer_agent, self.commit, self.synchrone = executer_agent, commit, synchrone
        self.projets, self.etats, self.retours, self.journal = [], {}, queue.Queue(), []
        self.dernier_quota = {}
        for p in projets:
            self._ajouter(p)

    def _ajouter(self, projet):
        self.projets.append(projet)
        self.etats[str(projet.factory)] = regles.nouvel_etat()

    def _etat(self, projet):
        return self.etats[str(projet.factory)]

    def _noter(self, projet, texte):
        self.journal.append(f"{projet.nom} : {texte}")

    # --- Un passage.

    def tour(self):
        self._prendre_les_projets_ajoutes()
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
        self._retours_des_agents(projet, etat)
        self._executer(projet, regles.avancer(projet, etat))
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

    def _quota(self, projet):
        maintenant = self.horloge()
        if maintenant - self.dernier_quota.get(str(projet.factory), 0) < QUOTA_TOUS_LES_S:
            return
        self.dernier_quota[str(projet.factory)] = maintenant
        try:
            regles.lancer(projet, "partenaires", {"action": "quota"})
        except (regles.Refus, regles.ErreurMoteur):
            pass    # les partenaires sont facultatifs : rien ne bloque sans eux

    # --- Les demandes.

    def _demandes(self, projet, etat):
        prises = etat.setdefault("prises", set())
        en_attente = regles.lancer(projet, "demandes")["demandes"]
        en_attente.sort(key=lambda d: d.get("type") != "message")     # la discussion reste vivante : messages d'abord
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
                               else {"agent": cle, "taches": taches})["message"]
        d = etat["departs"].get(taches[0]) or {}
        fiche = fi.trouver(fi.lire_toutes(fa.lire(projet.factory)["fiches"]), cle)
        if fiche is None:
            raise regles.Refus(f"agent inconnu : {cle}")
        modele = (d.get("modele") or fiche["modele"]).lower()

        def travail():
            e = self.executer_agent(depart, matiere, agent=fiche, modele=modele, dossier_projet=str(projet.dossier),
                                    tache=taches[0], lot=d.get("lot"))
            self.retours.put((projet, e))

        if self.synchrone:
            travail()
        else:
            threading.Thread(target=travail, name=f"agent-{cle}", daemon=True).start()

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
            try:
                actions = regles.traiter_retour(projet, e, etat)
            except (regles.Refus, regles.ErreurMoteur) as ex:
                self._noter(projet, f"retour de {e.agent} : {ex}")
                continue
            self._executer(projet, actions)
            if e.rapport is not None:
                self.commit(projet.dossier, "Factory : " + self._produit(e))
        for x in garde:
            self.retours.put(x)

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
