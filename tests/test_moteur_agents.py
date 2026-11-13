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

    def test_cumul_garde_le_premier_instantane_d_abonnement(self):
        a = {"five_hour": {"pourcent": 10.0, "remise": 5}, "t": 1}
        b = {"five_hour": {"pourcent": 12.0, "remise": 5}, "t": 2}
        [u] = agents.cumuler([dict(usage(1, 1), abonnement=a), dict(usage(2, 2), abonnement=b)])
        self.assertEqual((u["entree"], u["abonnement"]), (3, a))
        self.assertNotIn("abonnement", agents.cumuler([usage()])[0])

    def test_outils_de_la_fiche_passent_a_l_appel(self):
        a = Appels(sortie_ok(), sortie_ok())
        lancer(a)
        self.assertEqual(a.recus[0]["outils"], fiches.OUTILS_PAR_DEFAUT)
        self.assertEqual(agents.OUTILS_PAR_DEFAUT, fiches.OUTILS_PAR_DEFAUT)
        lancer(a, fiche={**FICHE, "outils": "Read, Bash(py:*), Bash(git log:*)"})
        self.assertEqual(a.recus[1]["outils"], ["Read", "Bash(py:*)", "Bash(git log:*)"])

    def test_la_consigne_dit_d_ecrire_les_fichiers_avec_write(self):
        """Au passage en vrai, les agents écrivaient leurs scripts par `cat > … <<EOF` : refusé sans approbation possible,
        rien n'était produit. Ceux qui passaient par Write puis `python script.py` réussissaient."""
        a = Appels(sortie_ok())
        lancer(a)
        self.assertIn("outil Write", a.recus[0]["consigne"])
        self.assertIn("python <chemin>.py", a.recus[0]["consigne"])
        self.assertIn("Bash(python:*)", fiches.OUTILS_PAR_DEFAUT)

    def test_jamais_de_contournement_des_autorisations(self):
        a = Appels(sortie_ok())
        lancer(a)
        argv = appel._argv("claude", "sonnet", "consigne.md", a.recus[0]["outils"], None)
        texte = " ".join(argv).lower() + json.dumps({k: str(v) for k, v in a.recus[0].items()
                                                     if k != "dossier"}).lower()
        for mot in ("dangerously", "bypass"):
            self.assertNotIn(mot, texte)
        self.assertIn("--permission-prompts", argv)

    def test_sans_rapport_le_second_essai_reprend_la_session(self):
        """Essai réel : l'agent finissait en « attendant » des tests en arrière-plan ; le second essai reprend sa session
        avec la consigne de rendre le rapport, au lieu de tout refaire."""
        a = Appels(appel.Reponse("Les tests tournent en arrière-plan. J'attends leur fin.", [usage()], session="s-1"),
                   appel.Reponse('Fait.\n```json\n{"statut": "fait", "message": {"texte": "Tests verts."}}\n```',
                                 [usage()], session="s-1"))
        e = lancer(a)
        self.assertIsNotNone(e.rapport)
        self.assertNotIn("reprendre", a.recus[0])
        self.assertEqual(a.recus[1]["reprendre"], "s-1")
        self.assertIn("premier plan", a.recus[1]["dossier"])
        self.assertIn("premier plan", agents.CONSIGNE_AGENT)

    def test_une_commande_de_test_se_borne_et_ecrit_au_fil_de_l_eau(self):
        """Essai réel : des tests Godot figés (erreur de syntaxe), sans délai ni sortie, ont tenu l'agent 25 minutes."""
        self.assertIn("se borne par un délai", agents.CONSIGNE_AGENT)
        self.assertIn("au fil de l'eau", agents.CONSIGNE_AGENT)
        self.assertLess(len(agents.CONSIGNE_AGENT), 1500)

    def test_commandes_longues_au_premier_plan(self):
        self.assertEqual(appel.ENV_COMMANDES_LONGUES["BASH_DEFAULT_TIMEOUT_MS"], "1800000")

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

    def test_panne_du_service_un_seul_essai(self):
        """Essai réel : « Failed to authenticate. API Error: 403 … Cloudflare » ; inutile de réessayer tout de suite."""
        a = Appels(appel.ErreurAppel("claude signale une erreur (success) : Failed to authenticate. API Error: 403 "
                                     "Attention Required! | Cloudflare"), sortie_ok())
        e = lancer(a)
        self.assertTrue(e.panne)
        self.assertIsNone(e.rapport)
        self.assertEqual(len(a.recus), 1)

    def test_une_vraie_erreur_n_est_pas_une_panne(self):
        self.assertFalse(appel.est_une_panne("délai dépassé (1800 s)"))
        self.assertFalse(appel.est_une_panne("rapport illisible : pas de bloc json"))
        self.assertTrue(appel.est_une_panne("API Error: 529 Overloaded"))
        self.assertTrue(appel.est_une_panne("API Error: 503 Service Unavailable"))

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


ACCORD = "accordé par le Directeur le 2026-11-12"
FICHE_FABLE = {"cle": "archi-1", "role": "archi", "modele": "Fable", "lieu": "local", "outils": None, "fable": ACCORD}


class FableSurAccord(unittest.TestCase):
    """Fable : jamais choisi par le moteur ; un agent n'y va que si sa fiche porte l'accord du Directeur."""

    def test_fable_refuse_sans_accord(self):
        a = Appels()
        for fiche in (FICHE, {**FICHE_FABLE, "fable": None}, {**FICHE, "fable": ACCORD},   # Opus avec une ligne d'accord
                      {**FICHE_FABLE, "fable": "accordé par moi"}):
            e = lancer(a, fiche=fiche, modele="fable")
            self.assertIn("Fable", e.erreur, fiche)
        self.assertEqual(a.recus, [])
        for modele in ("claude-fable-5-2", "fable-plus"):     # seul « fable » est un modèle
            self.assertIn("Fable", lancer(a, fiche=FICHE_FABLE, modele=modele).erreur)
        self.assertEqual(a.recus, [])

    def test_fable_permis_avec_accord_pour_cet_agent_seulement(self):
        a = Appels(sortie_ok(modele="claude-fable-5-2"))
        e = lancer(a, fiche=FICHE_FABLE, modele="Fable")
        self.assertIsNone(e.erreur)
        self.assertEqual((a.recus[0]["modele"], a.recus[0]["fable_accorde"]), ("fable", True))
        self.assertTrue(fiches.fable_accorde(FICHE_FABLE))
        # un autre agent, sans l'accord, ne profite pas de celui-ci
        autre = lancer(a, fiche={**FICHE, "cle": "dev-2"}, modele="fable")
        self.assertIn("Fable", autre.erreur)
        self.assertEqual(len(a.recus), 1)
        # et un agent sans accord n'obtient pas l'indicateur sur ses autres modèles
        b = Appels(sortie_ok())
        lancer(b)
        self.assertNotIn("fable_accorde", b.recus[0])

    def test_jugement_jamais_fable(self):
        from moteur import jugement
        for modele in ("fable", "Fable"):
            with self.assertRaises(appel.ErreurAppel):
                jugement.juger("conseil", {}, couche="claude", appeler=lambda *a, **k: self.fail("appelé"),
                               modele=modele)
        for kw in ({}, {"fable_accorde": True}):     # même avec l'indicateur, un appel sans outils (jugement) refuse
            with self.assertRaises(appel.ErreurAppel):
                appel.appeler("c", "d", "fable", couche="claude", **kw)
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "fable", couche="api", outils=["Read"], fable_accorde=True)
        self.assertEqual(appel._verifier_modele("fable", True), "fable")
        with self.assertRaises(appel.ErreurAppel):
            appel._verifier_modele("fable", False)

    def test_montee_ne_va_jamais_a_fable(self):
        from orchestrateur import depart
        for modele in ("Haiku", "Sonnet", "Opus", "Fable"):
            self.assertNotEqual(depart.monter(modele), "Fable" if modele != "Fable" else "")
        self.assertNotIn("Fable", depart.ECHELLE)
        self.assertEqual(depart.monter("Opus"), "Opus")

    def test_fiche_fable_lue_ecrite_et_refusee_sans_accord(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.md"
            p.write_text("Clé : x\nRôle : archi\nModèle : Fable\nLieu : local\nFable : " + ACCORD + "\n\nTexte.\n",
                         encoding="utf-8")
            f = fiches.lire_fiche(p)
            self.assertTrue(fiches.fable_accorde(f))
            fiches.ecrire_fiche(f)
            self.assertEqual(fiches.lire_fiche(p)["fable"], ACCORD)
            for entete in ("", "Fable : accordé par quelqu'un\n"):     # Fable sans accord, ou accord mal écrit
                p.write_text("Clé : x\nRôle : archi\nModèle : Fable\nLieu : local\n" + entete + "\nTexte.\n",
                             encoding="utf-8")
                with self.assertRaises(fiches.FicheInvalide):
                    fiches.lire_fiche(p)
            p.write_text("Clé : x\nRôle : archi\nModèle : Opus\nLieu : local\nFable : " + ACCORD + "\n\nT.\n",
                         encoding="utf-8")
            self.assertFalse(fiches.fable_accorde(fiches.lire_fiche(p)))    # l'accord ne suffit pas : il faut la fiche sur Fable


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
