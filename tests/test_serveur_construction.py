"""Variables de construction d'un APK au serveur (adresse et jeton du service intégrés à l'APK Client) : le réglage du projet,
la résolution au poste, le fichier d'entrée `entree/construction.env` (0600) et son chemin jusqu'à l'agent.

Essai réel FM_Stats (2026-11-27) : l'APK Client construit n'avait pas l'adresse du service (la construction ne passait aucun
`--dart-define`). Toutes les valeurs de ces tests sont FACTICES (`service.exemple`, `jeton-factice-…`) : aucune valeur réelle
dans le dépôt."""
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_construction as sc  # noqa: E402
import serveur_service  # noqa: E402
from bureau import reglages  # noqa: E402
from moteur import executeur_serveur  # noqa: E402

ADRESSE = "https://service.exemple:8443"
JETON = "jeton-factice-" + "0123456789" * 3            # 44 caractères [A-Za-z0-9_-]
VARIABLES = {"client": {"SERVEUR_URL": "service.adresse", "SERVEUR_JETON": "service.jeton"}}


class AvecPostefactice(unittest.TestCase):
    """Un poste factice : un dossier de projet et un coffre/cache de service (adresse et jeton factices)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.projet = self.t / "Mon Projet"
        (self.projet / ".factory").mkdir(parents=True)
        self.poste = self.t / "poste"
        self.poste.mkdir()
        self.ident = serveur_service.identifiant(self.projet)

    def adresse(self, valeur=ADRESSE):
        cache = serveur_service.lire_cache(self.poste)
        cache[self.ident] = {"adresse": valeur}
        (self.poste / serveur_service.CACHE).write_text(json.dumps(cache), encoding="utf-8")

    def jeton(self, valeur=JETON):
        chemin = serveur_service._coffre(self.poste, self.ident)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(valeur + "\n", encoding="utf-8")

    def reglages(self, variables):
        (self.projet / ".factory" / "reglages.json").write_text(json.dumps({"variables_construction": variables}),
                                                                encoding="utf-8")


class TestReglage(unittest.TestCase):
    def test_une_forme_valide_est_acceptee(self):
        v = {"client": {"SERVEUR_URL": "service.adresse", "SERVEUR_JETON": "service.jeton", "NIVEAU": "valeur:3"},
             "*": {"MODE": "valeur:test"}}
        self.assertEqual(reglages.normaliser_variables_construction(v), v)
        self.assertEqual(reglages.normaliser_variables_construction({}), {})

    def test_une_forme_hostile_est_refusee(self):
        for mauvais in ("x", [], {"Client": {}}, {"client": []}, {"client": {"serveur_url": "service.adresse"}},
                        {"client": {"A": "secret-en-clair"}}, {"client": {"A": "valeur:avec espace"}},
                        {"client": {"A": "valeur:a'b"}}, {"client": {"A": "valeur:a\\b"}}, {"client": {"A": 3}},
                        {"client": {f"V{i}": "service.adresse" for i in range(17)}}):
            with self.subTest(mauvais=str(mauvais)[:50]):
                with self.assertRaises(reglages.ReglagesInvalides):
                    reglages.normaliser_variables_construction(mauvais)

    def test_le_defaut_est_aucune_variable(self):
        self.assertEqual(reglages.DEFAUTS["variables_construction"], {})


class TestResolution(AvecPostefactice):
    def test_les_sources_sont_resolues_au_poste(self):
        self.adresse()
        self.jeton()
        r = sc.resoudre(self.projet, VARIABLES, self.poste)
        self.assertEqual(r, {"client": {"SERVEUR_URL": ADRESSE, "SERVEUR_JETON": JETON}})
        self.assertEqual(sc.valeurs_secretes(VARIABLES, r), [JETON])        # l'adresse n'est pas un secret

    def test_le_fichier_d_entree_a_une_ligne_par_variable(self):
        contenu = sc.contenu_entree({"client": {"SERVEUR_URL": ADRESSE, "SERVEUR_JETON": JETON}})
        self.assertEqual(contenu.decode(), f"client SERVEUR_JETON {JETON}\nclient SERVEUR_URL {ADRESSE}\n")
        self.assertEqual(sc.contenu_entree({}), b"")

    def test_un_litteral_est_repris_tel_quel(self):
        r = sc.resoudre(self.projet, {"*": {"MODE": "valeur:test"}}, self.poste)
        self.assertEqual(r, {"*": {"MODE": "test"}})

    def test_une_adresse_absente_dit_quoi_regler_sans_valeur(self):
        self.jeton()
        with self.assertRaises(sc.ConstructionRefusee) as e:
            sc.resoudre(self.projet, VARIABLES, self.poste)
        self.assertIn("adresse du service introuvable", str(e.exception))
        self.assertIn("SERVEUR_URL", str(e.exception))
        self.assertNotIn(JETON, str(e.exception))

    def test_un_jeton_absent_dit_quoi_regler(self):
        self.adresse()
        with self.assertRaises(sc.ConstructionRefusee) as e:
            sc.resoudre(self.projet, VARIABLES, self.poste)
        self.assertIn("jeton du service introuvable", str(e.exception))

    def test_aucune_valeur_dans_un_message_d_erreur(self):
        self.adresse()
        self.jeton()
        for variables in ({"client": {"A": "valeur:inconnu espace"}},):
            with self.assertRaises(sc.ConstructionRefusee):
                sc.resoudre(self.projet, variables, self.poste)
        with self.assertRaises(sc.ConstructionRefusee) as e:
            sc.contenu_entree({"client": {"SERVEUR_JETON": "valeur avec espace " + JETON}})
        self.assertNotIn(JETON, str(e.exception))

    def test_une_valeur_hostile_ne_peut_pas_entrer_dans_le_fichier(self):
        for valeur in ("a b", "a\nb", "a'b", "a`b", "a$b", "a\\b", "", "x" * 513):
            with self.subTest(valeur=valeur[:20]):
                with self.assertRaises(sc.ConstructionRefusee):
                    sc.contenu_entree({"client": {"NOM": valeur}})
        with self.assertRaises(sc.ConstructionRefusee):
            sc.contenu_entree({"client": {f"V{i}": "1" for i in range(17)}})


class TestMoteur(AvecPostefactice):
    def test_un_projet_sans_variables_n_envoie_rien(self):
        self.assertEqual(executeur_serveur._construction_du_projet(self.projet, self.poste), b"")
        self.reglages({})
        self.assertEqual(executeur_serveur._construction_du_projet(self.projet, self.poste), b"")

    def test_le_reglage_du_projet_donne_le_fichier_d_entree(self):
        self.adresse()
        self.jeton()
        self.reglages(VARIABLES)
        octets = executeur_serveur._construction_du_projet(self.projet, self.poste)
        self.assertEqual(octets.decode(), f"client SERVEUR_JETON {JETON}\nclient SERVEUR_URL {ADRESSE}\n")

    def test_une_source_manquante_refuse_avant_tout_envoi(self):
        self.reglages(VARIABLES)                      # ni adresse ni jeton
        with self.assertRaises(sc.ConstructionRefusee):
            executeur_serveur._construction_du_projet(self.projet, self.poste)

    def test_un_reglage_illisible_vaut_aucune_variable(self):
        (self.projet / ".factory" / "reglages.json").write_text("{pas du json", encoding="utf-8")
        self.assertEqual(executeur_serveur._construction_du_projet(self.projet, self.poste), b"")


class TestEnvoi(unittest.TestCase):
    """Le fichier part dans l'archive d'entrée en 0600, jamais dans demande.json ni dans une commande."""

    def test_le_fichier_est_un_membre_0600_et_jamais_dans_demande_json(self):
        from tests.test_serveur_agent import Base, ID1
        outer = self

        class Cas(Base):
            def runTest(self):
                contenu = sc.contenu_entree({"client": {"SERVEUR_URL": ADRESSE, "SERVEUR_JETON": JETON}})
                self.lancer(construction=contenu)
                e = self.srv.entrees[ID1]
                outer.assertEqual(e["entree/construction.env"], contenu)
                outer.assertNotIn(JETON.encode(), e["entree/demande.json"])
                outer.assertNotIn(ADRESSE.encode(), e["entree/demande.json"])
                for _nom, script, _entree, _delai in self.srv.appels:
                    outer.assertNotIn(JETON, script)           # jamais dans une commande
                preparer = self.srv.ops("preparer_agent")[0][1]
                outer.assertIn("construction.env", preparer)    # l'enveloppe le déplace avec les autres entrées

        cas = Cas()
        cas.setUp()
        try:
            cas.runTest()
        finally:
            cas.tearDown()

    def test_sans_variables_l_archive_est_inchangee(self):
        from tests.test_serveur_agent import Base, ID1

        class Cas(Base):
            def runTest(self):
                self.lancer()
                e = self.srv.entrees[ID1]
                assert "entree/construction.env" not in e, sorted(e)

        cas = Cas()
        cas.setUp()
        try:
            cas.runTest()
        finally:
            cas.tearDown()

    def test_le_membre_est_en_0600(self):
        import serveur_agent as sa
        archive = io.BytesIO()
        sa._archive_fichier([("entree/construction.env", b"x\n", 0o600)], archive)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tar:
            (membre,) = tar.getmembers()
            self.assertEqual(membre.mode & 0o777, 0o600)


class TestScriptsDuServeur(unittest.TestCase):
    def test_le_fichier_n_est_jamais_laisse_sur_le_serveur(self):
        """À la fin de la tâche (conclure) et à l'abandon, le fichier de variables est supprimé du serveur."""
        agent = (RACINE / "serveur_ovh" / "taches" / "lancer_agent.sh").read_text(encoding="utf-8")
        self.assertIn('rm -f -- "$DOSSIER/entree/construction.env"', agent)
        import serveur_agent as sa
        self.assertIn("entree/construction.env", sa._ABANDON_AGENT)


if __name__ == "__main__":
    unittest.main()
