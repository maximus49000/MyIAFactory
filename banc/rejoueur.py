"""Le rejoueur d'agents : rend, à la place d'un vrai `claude -p`, le rapport réel que l'agent avait rendu dans l'essai.

Il a la signature de `moteur.agents.executer_agent`. Pour chaque départ il cherche le rapport rangé sous
(étape, rôle, rang de l'élément) ; plusieurs rapports de même clé sont rendus dans l'ordre. Sans rapport, il rend un
rapport « rien à rejouer » qui fait finir la tâche et note un **écart** (`ecarts`) : le moteur a découpé autrement ou
demandé un tour de plus, ce n'est pas un échec en soi.

Les fichiers du rapport sont écrits dans le dossier du projet du banc (jamais ailleurs : un chemin absolu ou qui
remonte est refusé et noté en écart), comme l'aurait fait l'agent.
"""
import base64
import binascii
import json
from collections import defaultdict, deque
from pathlib import Path

from moteur import agents, rapport, regles

RIEN_A_REJOUER = "Rien à rejouer : le moteur a demandé un tour que l'essai de référence n'avait pas."


class Rejoueur:
    """`decrire(tache) -> {"etape", "role", "element", "elements"?}` : ce que la tâche est (le banc le lit dans le
    suivi) ; `elements` : ceux de son lot, dans l'ordre du lot."""

    def __init__(self, scenario, decrire):
        self.decrire = decrire
        self.ecarts = []
        self.rangs = {}      # élément -> rang, dans l'ordre où le moteur les rencontre (le prototype d'abord)
        self.file = defaultdict(deque)
        for r in scenario.rapports:
            self.file[(r["etape"], r["role"], r["rang"])].append(r)
        self.rendus = []     # (clé, tâche) de chaque rapport rendu, pour le rapport du banc

    def rang(self, element):
        if element is None:
            return 0
        return self.rangs.setdefault(element, len(self.rangs))

    def __call__(self, depart, matiere, *, agent, modele, dossier_projet, tache=None, lot=None, **plus):
        t = self.decrire(tache)
        etape = t.get("etape") or ""
        self.rang(t.get("element"))
        for e in t.get("elements") or []:     # un lot : chacun de ses éléments prend son rang, dans l'ordre du lot
            self.rang(e)
        if etape == "cadrage":    # le scénario range le cadrage sous le rôle `cadrage`, quel que soit l'agent qui cadre
            cle = (etape, regles.ROLE_CADRAGE, 0)
        else:
            cle = (etape, t.get("role") or agent["role"], self.rang(t.get("element")))
        suivant = self.file[cle].popleft() if self.file[cle] else None
        if suivant is None:
            self.ecarts.append(f"Aucun rapport à rejouer pour {cle[0]} / {cle[1]} / rang {cle[2]} (tâche {tache}).")
            texte = rapport.lire('```json\n{"statut": "fait", "message": {"texte": "' + RIEN_A_REJOUER + '"}}\n```')
            return agents.Execution(tache, agent["cle"], lot, rapport=texte, usages=[], modele=modele)
        self.rendus.append((cle, tache))
        fichiers = [{"chemin": f["chemin"], "titre": Path(f["chemin"]).name} for f in suivant.get("fichiers") or []]
        for f in suivant.get("fichiers") or []:
            self._ecrire(Path(dossier_projet), f)
        brut = dict(suivant.get("rapport") or {"statut": "fait", "message": {"texte": suivant["texte"]}})
        if brut.get("verdicts"):
            # un verdict de l'essai désigne son élément par le rang : l'élément du moteur de même rang le remplace
            par_rang = {r: e for e, r in self.rangs.items()}
            brut["verdicts"] = [{**{k: x for k, x in v.items() if k != "rang"},
                                 "element": par_rang.get(v.get("rang"), v.get("element"))} for v in brut["verdicts"]]
        if fichiers and not brut.get("fichiers"):
            brut["fichiers"] = fichiers
        lu = rapport.lire("```json\n" + json.dumps(brut, ensure_ascii=False) + "\n```")
        return agents.Execution(tache, agent["cle"], lot, rapport=lu, usages=[dict(suivant["usage"])], modele=modele)

    def _ecrire(self, dossier, f):
        chemin = Path(f["chemin"])
        if chemin.is_absolute() or ".." in chemin.parts:
            self.ecarts.append(f"Fichier refusé (chemin hors du projet) : {f['chemin']}")
            return
        try:
            octets = base64.b64decode(f["contenu_base64"], validate=True)
        except (binascii.Error, ValueError):
            self.ecarts.append(f"Fichier illisible (base64) : {f['chemin']}")
            return
        cible = dossier / chemin
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(octets)
