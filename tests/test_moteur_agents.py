"""Lancer un agent : rapport, usage, outils, relance. Aucun appel réel à `claude`."""
import json
import tempfile
import unittest
from pathlib import Path

from moteur import agents, appel
from orchestrateur import fiches

FICHE = {"cle": "dev-1", "role": "dev", "modele": "Sonnet", "lieu": "local", "outils": None}
RAPPORT = {"statut": "fait", "message": {"texte": "Fait.", "attend": False}}


def usage(entree=10, sortie=5, modele="claude-sonnet-5-5"):
    return {"modele": modele, "entree": entree, "sortie": sortie, "cache_lecture": 0, "cache_ecriture": 0}


def sortie_ok(objet=RAPPORT, **kw):
    return appel.Reponse("Terminé.\n```json\n" + json.dumps(objet) + "\n```", [usage(**kw)])


class Appels:
    def __init__(self, *reponses):
        self.reponses, self.recus = list(reponses), []

    def __call__(self, consigne, dossier, modele, **options):
        self.recus.append({"consigne": consigne, "dossier": dossier, "modele": modele, **options})
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def lancer(a, fiche=FICHE, modele="sonnet", **kw):
    return agents.executer_agent("DEPART", "MATIERE", agent=fiche, modele=modele, dossier_projet="/projet",
                                 appeler=a, tache="t1", **kw)


class ExecuterAgent(unittest.TestCase):
    def test_agent_rend_son_rapport_et_son_usage(self):
        a = Appels(sortie_ok())
        e = lancer(a)
        self.assertIsNone(e.erreur)
        self.assertEqual(e.rapport["statut"], "fait")
        self.assertEqual(e.usage, usage())
        self.assertEqual((e.tache, e.agent), ("t1", "dev-1"))
        self.assertEqual(len(a.recus), 1)
        self.assertEqual(a.recus[0]["dossier"], "DEPART\n\nMATIERE\n")
        self.assertEqual(a.recus[0]["dossier_travail"], "/projet")
        self.assertEqual(a.recus[0]["couche"], "claude")

    def test_outils_de_la_fiche_passent_a_l_appel(self):
        a = Appels(sortie_ok(), sortie_ok())
        lancer(a)
        self.assertEqual(a.recus[0]["outils"], fiches.OUTILS_PAR_DEFAUT)
        self.assertEqual(agents.OUTILS_PAR_DEFAUT, fiches.OUTILS_PAR_DEFAUT)
        lancer(a, fiche={**FICHE, "outils": "Read, Bash(py:*), Bash(git log:*)"})
        self.assertEqual(a.recus[1]["outils"], ["Read", "Bash(py:*)", "Bash(git log:*)"])

    def test_jamais_de_contournement_des_autorisations(self):
        a = Appels(sortie_ok())
        lancer(a)
        argv = appel._argv("claude", "sonnet", "consigne.md", a.recus[0]["outils"], None)
        texte = " ".join(argv).lower() + json.dumps({k: str(v) for k, v in a.recus[0].items()
                                                     if k != "dossier"}).lower()
        for mot in ("dangerously", "bypass"):
            self.assertNotIn(mot, texte)
        self.assertIn("--permission-prompts", argv)

    def test_agent_sans_bloc_relance_puis_bloque(self):
        a = Appels(appel.Reponse("Je n'ai pas de bloc.", [usage(10, 5)]), appel.Reponse("Toujours pas.", [usage(20, 7)]))
        e = lancer(a)
        self.assertIsNone(e.rapport)
        self.assertIn("rapport illisible", e.erreur)
        self.assertEqual(len(a.recus), 2)
        self.assertEqual((e.usage["entree"], e.usage["sortie"]), (30, 12))

    def test_relance_une_fois_puis_reussit(self):
        a = Appels(appel.Reponse("Rien.", [usage()]), sortie_ok())
        e = lancer(a)
        self.assertIsNone(e.erreur)
        self.assertEqual(e.usage["entree"], 20)

    def test_usage_note_meme_en_echec(self):
        a = Appels(appel.ErreurAppel("délai dépassé (1800 s)", [usage(40, 0)]),
                   appel.ErreurAppel("code 1", [usage(2, 1)]))
        e = lancer(a)
        self.assertIsNone(e.rapport)
        self.assertIn("l'appel a échoué", e.erreur)
        self.assertEqual((e.usage["entree"], e.usage["sortie"]), (42, 1))

    def test_usages_par_modele_cumules(self):
        r = appel.Reponse('x\n```json\n{"statut": "fait"}\n```', [usage(10, 5), usage(3, 1, "claude-haiku-5-5")])
        e = lancer(Appels(r))
        self.assertEqual([u["modele"] for u in e.usages], ["claude-sonnet-5-5", "claude-haiku-5-5"])

    def test_fable_dans_la_fiche_refuse(self):
        a = Appels()
        for modele in ("Fable", "fable"):
            e = lancer(a, modele=modele)
            self.assertIn("Fable", e.erreur)
        self.assertEqual(a.recus, [])

    def test_accord_requis_n_est_pas_relance(self):
        r = {"statut": "accord_requis", "accord": {"quoi": "q", "partenaire": "p", "cout": "1 $"}}
        a = Appels(sortie_ok(r))
        e = lancer(a)
        self.assertEqual(e.rapport["statut"], "accord_requis")
        self.assertEqual(len(a.recus), 1)


class OutilsDeFiche(unittest.TestCase):
    def test_ligne_outils_lue_dans_la_fiche(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.md"
            p.write_text("Clé : x\nRôle : dev\nModèle : Haiku\nLieu : local\nOutils : Read, Bash(py:*)\n\nTexte.\n",
                         encoding="utf-8")
            f = fiches.lire_fiche(p)
            self.assertEqual(fiches.outils(f), ["Read", "Bash(py:*)"])
            fiches.ecrire_fiche(f)
            self.assertEqual(fiches.lire_fiche(p)["outils"], "Read, Bash(py:*)")
            p.write_text("Clé : x\nRôle : dev\nModèle : Haiku\nLieu : local\n\nTexte.\n", encoding="utf-8")
            self.assertEqual(fiches.outils(fiches.lire_fiche(p)), fiches.OUTILS_PAR_DEFAUT)


if __name__ == "__main__":
    unittest.main()
