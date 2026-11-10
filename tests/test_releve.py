import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bureau import releve

RACINE = Path(__file__).resolve().parent.parent

BASE = {"version": 1, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}]}


class TestValider(unittest.TestCase):
    def test_base_valide(self):
        self.assertEqual(releve.valider(BASE), [])

    def test_erreurs(self):
        cas = [("colonne inconnue", lambda r: r["taches"][0].update(colonne="z")),
               ("titulaire inconnu", lambda r: r["taches"][0].update(titulaire="x")),
               ("etat factory", lambda r: r["factory"].update(etat="arrêt")),
               ("lieu", lambda r: r["titulaires"][0].update(lieu="lune")),
               ("service inconnu", lambda r: r["titulaires"][0].update(service="rh")),
               ("doublon", lambda r: r["taches"].append(dict(r["taches"][0]))),
               ("9 services", lambda r: r.update(services=[{"id": str(i), "nom": "S"} for i in range(9)])),
               ("deux chefs", lambda r: r["titulaires"].extend([{"cle": "c1", "lieu": "local", "chef": True}, {"cle": "c2", "lieu": "local", "chef": True}])),
               ("champ manquant", lambda r: r.pop("colonnes")),
               # Champs facultatifs de mauvais type : la page s'y casserait.
               ("file pas un objet", lambda r: r.update(file=[])),
               ("file.visibles pas une liste", lambda r: r.update(file={"visibles": 3})),
               ("file.visibles avec null", lambda r: r.update(file={"visibles": [None]})),
               ("file.visibles sans id", lambda r: r.update(file={"visibles": [{"titre": "T"}]})),
               ("file.visibles titre", lambda r: r.update(file={"visibles": [{"id": "q", "titre": 3}]})),
               ("file.reste texte", lambda r: r.update(file={"reste": "beaucoup"})),
               ("file.reste négatif", lambda r: r.update(file={"reste": -1})),
               ("decisions texte", lambda r: r.update(decisions="2")),
               ("decisions booléen", lambda r: r.update(decisions=True)),
               ("postit texte", lambda r: r["taches"][0].update(postit="oui")),
               ("etape nombre", lambda r: r["taches"][0].update(etape=3)),
               ("maj nombre", lambda r: r["taches"][0].update(maj=20261110)),
               ("nom de service", lambda r: r["services"][0].update(nom=None)),
               ("nom de colonne", lambda r: r["colonnes"][0].update(nom=["A"])),
               ("modele", lambda r: r["titulaires"][0].update(modele={"x": 1})),
               ("permanent", lambda r: r["titulaires"][0].update(permanent="oui")),
               ("fraicheur_min", lambda r: r["titulaires"][0].update(fraicheur_min="30")),
               ("factory.depuis", lambda r: r["factory"].update(depuis=3))]
        for nom, casser in cas:
            r = copy.deepcopy(BASE)
            casser(r)
            self.assertTrue(releve.valider(r), nom)

    def test_champs_facultatifs_bien_formes(self):
        r = copy.deepcopy(BASE)
        r["factory"]["depuis"] = "2026-11-10T09:00:00"
        r["file"] = {"visibles": [{"id": "q1", "titre": "Q"}], "reste": 4}
        r["decisions"] = 2
        r["taches"][0].update(postit=False, etape=None, maj=None)
        r["titulaires"][0].update(modele="Sonnet", permanent=True, fraicheur_min=12.5)
        self.assertEqual(releve.valider(r), [])

    def test_valider_ne_plante_pas_sur_n_importe_quoi(self):
        for r in (None, [], "x", {"taches": 3}, {"version": 1, "taches": [None]}):
            self.assertTrue(releve.valider(r))


class TestNormaliser(unittest.TestCase):
    def test_normaliser_ajoute_chef_et_defauts(self):
        n = releve.normaliser(BASE)
        self.assertIn("chef", [t["cle"] for t in n["titulaires"]])
        self.assertEqual((n["taches"][0]["postit"], n["file"], n["decisions"]),
                         (True, {"visibles": [], "reste": 0}, 0))
        self.assertEqual(n["titulaires"][0]["modele"], "?")
        self.assertNotIn("file", BASE)
        self.assertEqual(len(BASE["titulaires"]), 1)


V2 = {**copy.deepcopy(BASE), "version": 2}


def v2(**champs):
    r = copy.deepcopy(V2)
    r.update(champs)
    return r


class TestVersion2(unittest.TestCase):
    def test_version_2_minimale_valide(self):
        self.assertEqual(releve.valider(V2), [])

    def test_version_3_refusee(self):
        self.assertTrue(releve.valider({**BASE, "version": 3}))

    def test_neuf_services_refuses(self):
        def avec(n):
            return v2(services=[{"id": str(i), "nom": "S"} for i in range(n)], titulaires=[], taches=[])
        self.assertEqual(releve.valider(avec(8)), [])
        self.assertTrue(any("8" in m for m in releve.valider(avec(9))))

    def test_lien_javascript_refuse(self):
        r = v2(actions=[{"id": "a", "libelle": "A", "lien": "javascript:alert(1)"}])
        self.assertTrue(any("actions" in m for m in releve.valider(r)))

    def test_lien_claude_accepte(self):
        r = v2(actions=[{"id": "a", "libelle": "A", "lien": "claude://claude.ai/code/x"}])
        self.assertEqual(releve.valider(r), [])
        self.assertTrue(releve.lien_valide("https://exemple.org/x"))
        self.assertTrue(releve.lien_valide("http://exemple.org/x"))
        for mauvais in ("javascript:x", "file:///x", "https://a b", "https://a\n.b", "", None, 3, "//x"):
            self.assertFalse(releve.lien_valide(mauvais), mauvais)

    def test_journal_pas_liste(self):
        r = v2()
        r["taches"][0]["journal"] = "texte"
        self.assertTrue(any("journal" in m for m in releve.valider(r)))

    def test_lien_de_tache_javascript(self):
        r = v2()
        r["taches"][0]["liens"] = [{"libelle": "x", "url": "javascript:alert(1)"}]
        self.assertTrue(any("liens" in m for m in releve.valider(r)))

    def test_lecon_agent_inconnu(self):
        r = v2(lecons=[{"id": "l1", "agent": "inconnu", "texte": "t"}])
        self.assertTrue(any("l1" in m for m in releve.valider(r)))
        r = v2(lecons=[{"id": "l1", "agent": "d1", "texte": "t", "verdict_demande": "valider"}])
        self.assertEqual(releve.valider(r), [])
        r = v2(lecons=[{"id": "l1", "agent": "d1", "texte": "t", "verdict_demande": "peut-etre"}])
        self.assertTrue(releve.valider(r))

    def test_quarante_et_une_images(self):
        r = v2()
        r["taches"][0]["images"] = [{"chemin": f"{i}.png"} for i in range(40)]
        self.assertEqual(releve.valider(r), [])
        r["taches"][0]["images"].append({"chemin": "41.png"})
        self.assertTrue(any("images" in m for m in releve.valider(r)))

    def test_type_inconnu(self):
        r = v2(types=[{"id": "bug", "nom": "Bug"}])
        r["taches"][0]["type"] = "autre"
        self.assertTrue(any("type" in m for m in releve.valider(r)))
        r["taches"][0]["type"] = "bug"
        self.assertEqual(releve.valider(r), [])

    def test_titulaire_et_retours(self):
        r = v2()
        r["titulaires"][0].update(prenom="Zoé", specialite="Tests",
                                  lecons=[{"id": "x", "texte": "t", "etat": "validée"}])
        r["taches"][0].update(retours=[{"t": "2026-11-10T10:00:00", "texte": "r", "reponse": "ok"}],
                              bloquee="attend", journal=[{"t": "x", "texte": "y"}])
        self.assertEqual(releve.valider(r), [])
        r["titulaires"][0]["lecons"][0]["etat"] = "autre"
        self.assertTrue(releve.valider(r))

    def test_valeurs_non_hachables_refusees_sans_exception(self):
        mauvais = [v2(actions=[{"id": [], "libelle": "A"}]), v2(actions=[{"id": {}, "libelle": "A"}]),
                   v2(lecons=[{"id": [], "agent": "d1", "texte": "t"}]),
                   v2(lecons=[{"id": "l", "agent": [], "texte": "t"}])]
        for champ, valeur in (("colonne", []), ("titulaire", []), ("colonne", {})):
            r = v2()
            r["taches"][0][champ] = valeur
            mauvais.append(r)
        r = v2()
        r["titulaires"][0]["service"] = []
        mauvais.append(r)
        for r in mauvais:
            self.assertTrue(releve.valider(r))

    def test_actions_mal_formees(self):
        for actions in ("x", [3], [{"id": "", "libelle": "A"}],
                        [{"id": "a", "libelle": "A"}, {"id": "a", "libelle": "B"}],
                        [{"id": "a", "libelle": "A", "actif": "oui"}],
                        [{"id": "a", "libelle": 3}], [{"id": "a", "libelle": "A", "confirmer": 3}]):
            self.assertTrue(releve.valider(v2(actions=actions)), actions)

    def test_version_1_ignore_les_ajouts(self):
        r = copy.deepcopy(BASE)
        r["actions"] = "n'importe quoi"
        r["taches"][0]["journal"] = 3
        self.assertEqual(releve.valider(r), [])
        n = releve.normaliser(r)
        self.assertNotIn("actions", n)
        self.assertNotIn("journal", n["taches"][0])
        self.assertNotIn("bloquee", n["taches"][0])

    def test_normaliser_v2_defauts(self):
        n = releve.normaliser(V2)
        self.assertEqual((n["actions"], n["types"], n["lecons"]), ([], [], []))
        t = n["taches"][0]
        self.assertEqual((t["journal"], t["images"], t["liens"], t["retours"], t["type"], t["bloquee"]),
                         ([], [], [], [], None, None))


class TestObtenir(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def regl(self, source):
        return {"releve": source, "dossier": str(self.tmp)}

    def test_obtenir_fichier(self):
        (self.tmp / "r.json").write_text(json.dumps(BASE), encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_fichier_absent(self):
        r, err = releve.obtenir(self.regl({"fichier": "absent.json"}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_json_tronque(self):
        (self.tmp / "r.json").write_text('{"version": 1, "ta', encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_invalide(self):
        b = copy.deepcopy(BASE)
        b["taches"][0]["colonne"] = "zzz"
        (self.tmp / "r.json").write_text(json.dumps(b), encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(r)
        self.assertIn("zzz", err)

    def test_obtenir_commande(self):
        cmd = [sys.executable, "-c", "import json,sys; print(json.dumps(%r))" % BASE]
        r, err = releve.obtenir(self.regl({"commande": cmd, "dossier": "."}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_commande_en_echec(self):
        cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
        r, err = releve.obtenir(self.regl({"commande": cmd}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def _avec_delai_court(self):
        ancien = releve.DELAI_COMMANDE_S
        releve.DELAI_COMMANDE_S = 1
        self.addCleanup(setattr, releve, "DELAI_COMMANDE_S", ancien)

    def test_obtenir_commande_trop_longue(self):
        self._avec_delai_court()
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        debut = time.monotonic()
        r, err = releve.obtenir(self.regl({"commande": cmd}))
        self.assertIsNone(r)
        self.assertIn("dépassé", err)
        self.assertLess(time.monotonic() - debut, 6)

    def test_obtenir_commande_dont_un_descendant_garde_la_sortie(self):
        # La commande lance un sous-processus qui hérite de sa sortie et dort : le délai doit tenir.
        self._avec_delai_court()
        enfant = "import time; time.sleep(30)"
        parent = ("import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', %r]); "
                  "time.sleep(30)") % enfant
        debut = time.monotonic()
        r, err = releve.obtenir(self.regl({"commande": [sys.executable, "-c", parent]}))
        self.assertIsNone(r)
        self.assertIn("dépassé", err)
        self.assertLess(time.monotonic() - debut, 6)

    def test_obtenir_fichier_avec_bom(self):
        (self.tmp / "r.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(BASE).encode("utf-8"))
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_commande_introuvable(self):
        r, err = releve.obtenir(self.regl({"commande": ["commande-qui-n-existe-pas"]}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_sans_source(self):
        r, err = releve.obtenir(self.regl({}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_exemple_demo_valide(self):
        d = json.loads((RACINE / "exemples" / "demo" / "releve.json").read_text(encoding="utf-8"))
        self.assertEqual(releve.valider(d), [])


if __name__ == "__main__":
    unittest.main()
