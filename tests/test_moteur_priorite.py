"""L'installation d'un outil est prioritaire sur tout le bureau (pause globale, départ sans condition de charge, une à la
fois), l'attente de charge est dite au bureau, et un outil manquant revient à l'écran. Aucun appel réel, rien d'installé."""
import json
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import attente
from moteur import agents, boucle, environnement, rapport, regles
from orchestrateur import fiches
from tests.orch_aide import factory_minimale
from tests.test_moteur_boucle import USAGE, Agents, Appels

JDK = {"outil": "JDK 21", "pour": "dev", "executables": ["java", "javac"],
       "installation": "winget install EclipseAdoptium.Temurin.21.JDK", "autonome": True,
       "telechargement": "https://adoptium.net/temurin/releases/", "objectif": "Compiler le jeu.",
       "etapes": ["Ouvrir la page.", "Installer."], "etat": "a_installer"}
GODOT = {"outil": "Godot Engine", "pour": "dev", "executables": ["godot"], "installation": "winget install Godot",
         "autonome": True, "etat": "a_installer"}


class Bureau(unittest.TestCase):
    """Deux projets (a, b) dans un bureau commun ; un faux poste (`self.poste` : outil -> en place ?) et une fausse charge."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.racine = Path(self._t.name)
        self.poste, self.charge = {}, {"a": True, "b": True}
        self.mesure = {"a": None, "b": None}
        self.agents, self.appels = Agents(), Appels()
        self.projets = {n: self.projet(n) for n in ("a", "b")}

    def projet(self, nom, outils=()):
        dossier = self.racine / nom / ".factory"
        chemin = factory_minimale(dossier, environnement=[dict(o) for o in outils])
        if not (dossier / "fiches" / "env-1.md").exists():       # un projet refait garde son installateur
            fiches.ecrire_fiche(self.installateur(dossier))
        (dossier / "fiches" / "briefs").mkdir(parents=True, exist_ok=True)
        (dossier / "fiches" / "briefs" / "environnement.md").write_text("Brief de l'installateur.", encoding="utf-8")

        def verifier(liste):
            return [dict(environnement.avec_aide(o), etat="en_place" if self.poste.get(o["outil"]) else "a_installer")
                    for o in liste]

        return regles.Projet(chemin, feu_vert=lambda: self.charge[nom], verifier_environnement=verifier)

    @staticmethod
    def installateur(dossier):
        from installation import mise_en_place
        agent, _ = environnement.agent_d_installation(
            fiches.lire_toutes(dossier / "fiches"), [], [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}],
            [{"id": "dev", "nom": "Dev"}])
        return mise_en_place._fiche(agent, dossier / "fiches" / f"{agent['cle']}.md")

    def moteur(self, **kw):
        kw.setdefault("synchrone", True)
        return boucle.Moteur(list(self.projets.values()), appeler=self.appels, executer_agent=self.agents,
                             commit=lambda d, m: None, **kw)

    def tache(self, nom, **champs):
        p = self.projets[nom]
        return regles.lancer(p, "tache", {"titre": "T", "colonne": "cadrage", "active": False, **champs})["id"]

    def installation(self, nom, outils=(JDK,)):
        return self.tache(nom, **environnement.tache_d_installation_du_projet([dict(o) for o in outils]))

    def correction(self, nom):
        return self.tache(nom, titre="Corriger", etape="correction", role="dev")

    def etat_de(self, nom):
        return regles.lancer(self.projets[nom], "etat")

    def colonne(self, nom, tid):
        return regles.lancer(self.projets[nom], "detail", {"tache": tid})

    def lances(self):
        """(agent, « projet:tâche ») de chaque départ, dans l'ordre (les numéros de tâche se répètent d'un projet à l'autre)."""
        return [(x["agent"], f"{Path(x['dossier']).name}:{x['tache']}") for x in self.agents.lances]


class Bloque(Agents):
    """Un faux agent qui travaille tant qu'on ne le libère pas : une installation « en cours »."""

    def __init__(self):
        super().__init__()
        self.liberes = {}

    def __call__(self, depart, matiere, **kw):
        porte = self.liberes.setdefault(kw["tache"] + "@" + Path(kw["dossier_projet"]).name, threading.Event())
        self.lances.append({"agent": kw["agent"]["cle"], "tache": kw["tache"], "dossier": kw["dossier_projet"]})
        porte.wait(10)
        return agents.Execution(kw["tache"], kw["agent"]["cle"], kw.get("lot"), rapport=rapport.lire(self.rapport),
                                usages=[dict(USAGE)])

    def liberer(self, projet, tache):
        self.liberes.setdefault(tache + "@" + projet, threading.Event()).set()


class Priorite(Bureau):
    def test_installation_prete_met_tous_les_projets_en_pause_et_part_malgre_la_charge(self):
        self.charge["a"] = False        # la charge retiendrait n'importe quelle autre tâche de a
        ti = self.installation("a")
        self.correction("b")            # b : charge au vert, une tâche prête
        m = self.moteur()
        m.tour()
        self.assertEqual(self.lances(), [("env-1", f"a:{ti}")])    # l'installation part, sans feu vert ni plafond
        self.assertEqual(self.projets["b"].pause_globale, "Pause : installation de JDK 21 (a)")
        self.assertEqual(m.pause_installation["projet"], "a")      # rien n'est parti dans b, malgré sa charge au vert

    def test_la_pause_se_leve_toute_seule_a_la_fin_et_le_travail_repart(self):
        ti = self.installation("a")
        tb = self.correction("b")
        m = self.moteur()
        self.poste["JDK 21"] = True
        m.tour()                                       # l'installation part et rend son rapport dans ce passage
        self.assertEqual(self.colonne("a", ti)["colonne"], "fait")
        self.assertEqual(self.lances(), [("env-1", f"a:{ti}")])
        m.tour()                                       # plus rien à installer : la pause est levée
        self.assertIsNone(m.pause_installation)
        self.assertIsNone(self.projets["b"].pause_globale)
        self.assertEqual(self.lances(), [("env-1", f"a:{ti}"), ("dev-1", f"b:{tb}")])

    def test_pendant_l_installation_rien_ne_part_et_les_agents_au_travail_finissent(self):
        """Un agent déjà parti finit et son rapport est appliqué ; les demandes du bureau sont traitées ; rien de neuf ne part."""
        self.agents = Bloque()
        tb = self.correction("b")
        m = self.moteur(synchrone=False)
        m.tour()                                       # b : dev-1 part, il travaille
        self.assertEqual(self.lances(), [("dev-1", f"b:{tb}")])
        ta = self.installation("a")
        autre = self.correction("b")                   # une deuxième tâche prête dans b
        code, demande = _action(self.projets["b"], {"type": "fonctionnalite", "texte": "Un badge pour le chat"})
        self.assertEqual(code, 0, demande)
        m.tour()                                       # l'installation prête : elle part, la pause tombe sur b
        self.assertEqual(self.lances()[1], ("env-1", f"a:{ta}"))
        m.tour()
        self.assertEqual(len(self.lances()), 2)        # la deuxième tâche de b attend la fin de l'installation
        self.assertIn(demande["id"], m.etats[str(self.projets["b"].factory)]["prises"])     # la demande a été prise
        self.agents.liberer("b", tb)                   # l'agent déjà au travail finit : son rapport est appliqué
        self._attendre(lambda: self._fait(m, "b", tb))
        self.assertEqual(len(self.lances()), 2, self.lances())        # et rien de neuf n'est parti pour autant
        self.assertNotIn(("dev-1", f"b:{autre}"), self.lances())

    def test_une_seule_installation_a_la_fois_dans_l_ordre_d_arrivee(self):
        self.agents = Bloque()
        ta = self.installation("a")
        m = self.moteur(synchrone=False)
        m.tour()
        self.assertEqual(self.lances(), [("env-1", f"a:{ta}")])
        tb = self.installation("b", outils=(GODOT,))
        m.tour()
        self.assertEqual(self.lances(), [("env-1", f"a:{ta}")])      # b attend la fin de celle de a
        self.assertEqual(self.projets["b"].pause_globale, "Pause : installation de JDK 21 (a)")
        self.assertEqual([t for _, t in m.file_installations], [tb])
        self.poste.update({"JDK 21": True, "Godot Engine": True})
        self.agents.liberer("a", ta)
        self._attendre(lambda: self._fait(m, "a", ta))
        m.tour()                                                     # l'installation de a est finie : celle de b part
        self.assertEqual(self.lances()[-1], ("env-1", f"b:{tb}"))
        self.assertEqual(self.projets["a"].pause_globale, "Pause : installation de Godot Engine (b)")
        self.agents.liberer("b", tb)
        self._attendre(lambda: self._fait(m, "b", tb))
        m.tour()
        m.tour()
        self.assertIsNone(m.pause_installation)

    def _fait(self, m, nom, tid):
        m.tour()
        return self.colonne(nom, tid)["colonne"] == "fait"

    def _attendre(self, condition):
        import time
        fin = time.time() + 10
        while time.time() < fin:
            if condition():
                return
            time.sleep(0.05)
        self.fail("l'agent n'a pas fini")

    def test_pause_manuelle_du_projet_garde_son_installation_et_ne_retient_personne(self):
        """Choix : le Directeur a mis ce projet en pause, son installation attend la reprise et ne retient pas les autres."""
        self.installation("a")
        tb = self.correction("b")
        code, objet = _action(self.projets["a"], {"type": "bouton", "id": "pause"})
        self.assertEqual(code, 0, objet)
        m = self.moteur()
        m.tour()
        self.assertEqual(self.lances(), [("dev-1", f"b:{tb}")])    # b travaille ; l'installation de a attend sa reprise
        self.assertIsNone(m.pause_installation)

    def test_installation_sans_agent_d_installation_ne_met_rien_en_pause(self):
        self.installation("a")
        (self.racine / "a" / ".factory" / "fiches" / "env-1.md").unlink()
        tb = self.correction("b")
        m = self.moteur()
        m.tour()
        self.assertEqual(self.lances(), [("dev-1", f"b:{tb}")])
        self.assertIsNone(m.pause_installation)

    def test_fin_avec_outil_toujours_absent_leve_la_pause_et_pose_la_decision(self):
        self.projets["a"] = self.projet("a", [JDK])      # le projet note JDK 21 comme outil à installer
        ti = self.installation("a")
        m = self.moteur()
        m.tour()                                       # l'outil n'est pas en place à la fin : la décision revient
        self.assertEqual(self.colonne("a", ti)["colonne"], "fait")
        (d,) = [x for x in self.etat_de("a")["decisions"] if x["genre"] == "environnement"]
        self.assertEqual(d["portee"], "projet")
        m.tour()
        self.assertIsNone(m.pause_installation)

    def test_pause_ecrite_pour_le_bureau_puis_effacee(self):
        self.agents = Bloque()
        bureau = self.racine / "bureau.json"
        bureau.write_text(json.dumps({"projets": [str(self.racine / n / ".factory" / "reglages.json") for n in "ab"]}),
                          encoding="utf-8")
        ta = self.installation("a")
        m = self.moteur(bureau=bureau, synchrone=False)
        m.tour()
        lu = attente.pause_installation(bureau)
        self.assertEqual((lu["texte"], lu["projet"], lu["outils"]), ("Pause : installation de JDK 21 (a)", "a", ["JDK 21"]))
        self.poste["JDK 21"] = True
        self.agents.liberer("a", ta)
        self._attendre(lambda: self._fait(m, "a", ta))
        m.tour()
        self.assertIsNone(attente.pause_installation(bureau))
        self.assertFalse(attente.chemin_pause(bureau).exists())


def _action(projet, entree):
    from orchestrateur import outil
    return outil.executer(str(projet.factory), ["actions"], entree)


class AttenteDeCharge(Bureau):
    def test_tache_retenue_par_la_charge_est_dite_au_bureau(self):
        self.projets["a"] = regles.Projet(self.projets["a"].factory,
                                          mesure=lambda: {"feu_vert": False, "charge": 90, "plafond": 70})
        t = self.correction("a")
        m = self.moteur()
        m.tour()
        self.assertEqual(self.lances(), [])
        lu = attente.attente_charge(self.racine / "a" / ".factory")
        self.assertEqual(lu["texte"], "En attente : charge 90 % (plafond 70 %)")
        self.assertEqual((lu["taches"], lu["charge"], lu["plafond"]), ([t], 90, 70))
        self.assertIsNone(attente.attente_charge(self.racine / "b" / ".factory"))

    def test_mise_a_jour_a_chaque_passage_puis_effacee_au_depart(self):
        mesure = {"feu_vert": False, "charge": 90, "plafond": 70}
        self.projets["a"] = regles.Projet(self.projets["a"].factory, mesure=lambda: dict(mesure))
        self.correction("a")
        m = self.moteur()
        m.tour()
        mesure.update(charge=84)
        m.tour()
        self.assertEqual(attente.attente_charge(self.racine / "a" / ".factory")["texte"],
                         "En attente : charge 84 % (plafond 70 %)")
        mesure.update(feu_vert=True, charge=50)
        m.tour()
        self.assertEqual(len(self.lances()), 1)
        self.assertIsNone(attente.attente_charge(self.racine / "a" / ".factory"))

    def test_places_libres_en_attente_d_une_validation_dites_au_bureau(self):
        from unittest import mock
        texte = regles.texte_des_places_libres(2, "Validation de la direction artistique")
        self.assertEqual(texte, "2 places libres : en attente de votre validation « Validation de la direction artistique »")
        self.assertEqual(regles.texte_des_places_libres(1, "X"), "1 place libre : en attente de votre validation « X »")
        noter = lambda projet, etat: etat.update(attente_validation={"texte": texte, "places": 2})   # noqa: E731
        m = self.moteur()
        with mock.patch.object(regles, "_noter_les_places_libres", side_effect=noter):
            m.tour()
        self.assertEqual(attente.attente_places(self.racine / "a" / ".factory")["texte"], texte)
        m.tour()        # plus rien n'attend : le fichier est effacé
        self.assertIsNone(attente.attente_places(self.racine / "a" / ".factory"))

    def test_charge_lue_de_la_ligne_de_l_outil(self):
        p = self.projets["a"]
        self.assertEqual(regles._MESURE.search("attendre : charge 90 % (max 70 %)").groups(), ("90", "70"))
        self.assertEqual(regles.texte_d_attente_de_charge({"charge": None, "plafond": None}),
                         "En attente : la charge de l'ordinateur dépasse le plafond du projet")
        self.assertEqual(p.charge(), {"feu_vert": True, "charge": None, "plafond": None})

class OutilManquant(Bureau):
    def projet_avec_poste(self, outils):
        self.projets["a"] = self.projet("a", outils)
        return self.projets["a"]

    def decisions(self, nom="a"):
        return [d for d in self.etat_de(nom)["decisions"] if d["genre"] == "environnement"]

    def test_au_demarrage_un_outil_manquant_sans_decision_ni_tache_revient(self):
        self.projet_avec_poste([GODOT])
        m = self.moteur()
        m.tour()
        (d,) = self.decisions()
        self.assertEqual(d["portee"], "projet")
        (x,) = d["environnement"]
        self.assertEqual((x["outil"], x["autonome"], x["telechargement"] is None, x["etapes"] is not None),
                         ("Godot Engine", True, True, True))
        self.assertIn("Godot Engine", d["texte"])
        m.tour()
        m.tour()
        self.assertEqual(len(self.decisions()), 1)                  # pas de doublon

    def test_champs_d_aide_repris_dans_la_decision(self):
        self.projet_avec_poste([JDK])
        self.moteur().tour()
        (x,) = self.decisions()[0]["environnement"]
        self.assertEqual((x["objectif"], x["telechargement"], x["etapes"], x["autonome"]),
                         (JDK["objectif"], JDK["telechargement"], JDK["etapes"], True))

    def test_outil_revérifié_en_place_ne_revient_pas_et_est_note(self):
        self.projet_avec_poste([GODOT])
        self.poste["Godot Engine"] = True
        self.moteur().tour()
        self.assertEqual(self.decisions(), [])
        f = json.loads((self.racine / "a" / ".factory" / "factory.json").read_text(encoding="utf-8"))
        self.assertEqual(f["environnement"][0]["etat"], "en_place")

    def test_une_tache_d_installation_en_attente_ou_en_cours_evite_la_decision(self):
        p = self.projet_avec_poste([GODOT])
        regles.lancer(p, "tache", environnement.tache_d_installation_du_projet([dict(GODOT)]))
        _action(p, {"type": "bouton", "id": "pause"})        # prête, mais le projet est en pause à la main : elle attend
        m = self.moteur()
        m.tour()
        self.assertEqual(self.decisions(), [])
        _action(p, {"type": "bouton", "id": "reprendre"})
        self.agents = Bloque()                                # en cours : l'agent travaille encore
        m = self.moteur(synchrone=False)
        m.executer_agent = self.agents
        m.tour()
        self.assertEqual(self.lances(), [("env-1", "a:t1")])
        self.assertEqual(self.decisions(), [])
        self.agents.liberer("a", "t1")

    def test_une_decision_deja_ouverte_evite_le_doublon(self):
        p = self.projet_avec_poste([GODOT])
        regles.lancer(p, "decision", {"action": "poser", "portee": "projet", "genre": "environnement",
                                      "texte": "Il manque Godot Engine.", "environnement": [dict(GODOT)]})
        self.moteur().tour()
        self.assertEqual(len(self.decisions()), 1)

    def test_apres_la_fin_d_une_installation_les_autres_projets_sont_revus(self):
        self.projet_avec_poste([GODOT])
        ti = self.installation("b")
        self.projets["b"].verifier_environnement = lambda liste: [dict(o, etat="en_place") for o in liste]
        m = self.moteur()
        m.tour()                  # démarrage : a (Godot manque) pose sa décision ; b installe
        for d in self.decisions():
            regles.lancer(self.projets["a"], "decision", {"action": "lever", "id": d["id"]})
        self.assertEqual(self.decisions(), [])
        m.tour()                  # la pause de b se lève : a est revu, Godot manque toujours
        self.assertEqual(len(self.decisions()), 1)


if __name__ == "__main__":
    unittest.main()
