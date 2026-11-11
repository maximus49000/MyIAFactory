"""Tâche 18 : le catalogue des partenaires."""
import copy
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from partenaires import catalogue

RACINE = Path(__file__).resolve().parent.parent


class TestCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = catalogue.lire()

    def entree(self, id_):
        return next(p for p in self.d["partenaires"] if p["id"] == id_)

    def test_catalogue_livre_valide(self):
        self.assertEqual(catalogue.verifier(self.d), [])
        self.assertEqual(self.d["version"], 1)
        self.assertGreater(len(self.d["partenaires"]), 100)

    def test_ids_uniques(self):
        ids = [p["id"] for p in self.d["partenaires"]]
        self.assertEqual(len(ids), len(set(ids)))
        d = copy.deepcopy(self.d)
        d["partenaires"].append(copy.deepcopy(d["partenaires"][0]))
        self.assertTrue(any("en double" in e for e in catalogue.verifier(d)))

    def test_url_https(self):
        d = copy.deepcopy(self.d)
        d["partenaires"][0]["inscription"] = "http://exemple.org/inscription"
        self.assertTrue(any("https://" in e for e in catalogue.verifier(d)))
        d = copy.deepcopy(self.d)
        d["partenaires"][0]["connexions"] = [{"type": "api", "url": "javascript:alert(1)"}]
        self.assertTrue(any("https://" in e for e in catalogue.verifier(d)))
        # une URL absente reste null, jamais inventée
        d = copy.deepcopy(self.d)
        d["partenaires"][0]["inscription"] = None
        self.assertEqual(catalogue.verifier(d), [])

    def test_tarif_inconnu_refuse(self):
        d = copy.deepcopy(self.d)
        d["partenaires"][0]["plans"] = [{"nom": "X", "prix": 1, "devise": "USD", "periode": "mois",
                                         "quota": None, "tarif": "gratos"}]
        self.assertTrue(any("tarif" in e for e in catalogue.verifier(d)))
        d = copy.deepcopy(self.d)
        d["partenaires"][0]["categorie"] = "autre"
        self.assertTrue(any("catégorie" in e for e in catalogue.verifier(d)))
        d = copy.deepcopy(self.d)
        d["partenaires"][0]["verifie_le"] = "2026-13-45"
        self.assertTrue(any("date" in e for e in catalogue.verifier(d)))
        d = copy.deepcopy(self.d)
        d["partenaires"][0]["quota_lisible"] = "non"
        d["partenaires"][0]["lecteur"] = "elevenlabs"
        self.assertTrue(any("lecteur" in e for e in catalogue.verifier(d)))

    def test_fermes_marques(self):
        for i in ("lmnt", "playht", "sora", "tome"):
            self.assertEqual(self.entree(i)["statut"], "ferme", i)
        for i in ("midjourney", "suno", "udio", "mixamo"):
            self.assertEqual(self.entree(i)["statut"], "sans_api", i)

    def test_au_moins_une_entree_par_categorie(self):
        par = catalogue.par_categorie(self.d)
        self.assertEqual(tuple(par), catalogue.CATEGORIES)
        for c in catalogue.CATEGORIES:
            self.assertTrue(par[c], c)

    def test_actifs_d_abord(self):
        for liste in catalogue.par_categorie(self.d).values():
            statuts = [p["statut"] for p in liste]
            premier_autre = next((i for i, s in enumerate(statuts) if s != "actif"), len(statuts))
            self.assertNotIn("actif", statuts[premier_autre:])

    def test_amorce_de_la_recherche(self):
        """Les partenaires phares de la recherche y sont, datés du jour de la recherche, avec leur lecteur de quota."""
        for i in ("elevenlabs", "meshy", "tripo", "autosprite", "runway", "deepl", "vercel", "github", "poly-haven"):
            self.assertEqual(self.entree(i)["verifie_le"], "2026-11-11", i)
        self.assertEqual(self.entree("elevenlabs")["lecteur"], "elevenlabs")
        self.assertTrue(self.entree("poly-haven")["illimite"])
        self.assertEqual(self.entree("tripo")["quota_lisible"], "inconnu")
        lecteurs = {p["lecteur"] for p in self.d["partenaires"] if p.get("lecteur")}
        self.assertEqual(lecteurs, {"elevenlabs", "bfl", "stability", "leonardo", "meshy", "removebg", "deepl", "kiri"})

    def test_fiabilite_officielle_ou_tierce(self):
        for p in self.d["partenaires"]:
            self.assertIn(p["fiabilite"], ("officielle", "tiers"))
        self.assertEqual(self.entree("elevenlabs")["fiabilite"], "officielle")
        self.assertEqual(self.entree("kling")["fiabilite"], "tiers")

    def test_commande_mcp_sans_cle(self):
        """Une commande de connexion MCP est celle de la doc (nom et adresse) : aucune clé n'y figure."""
        for p in self.d["partenaires"]:
            for c in p["connexions"]:
                cmd = c.get("commande")
                if cmd:
                    self.assertTrue(cmd.startswith("claude mcp add"), p["id"])
                    self.assertNotRegex(cmd, r"(?i)(authorization|bearer|api[_-]?key=|token=)", p["id"])

    def test_popularite_facultative(self):
        """`popularite` : null tant qu'elle n'est pas mesurée, sinon {niveau 1 à 5, base, date}."""
        self.assertTrue(all(p.get("popularite") is None for p in self.d["partenaires"]))
        bonne = {"niveau": 4, "base": "Étoiles GitHub du SDK, téléchargements npm", "date": "2026-11-12"}
        for valeur, attendu_ok in ((bonne, True), (None, True), ({**bonne, "niveau": 0}, False), ({**bonne, "niveau": 6}, False),
                                   ({**bonne, "niveau": 3.5}, False), ({**bonne, "niveau": True}, False),
                                   ({**bonne, "date": "2026-13-01"}, False), ({**bonne, "base": ""}, False),
                                   ({**bonne, "base": 3}, False), ({"niveau": 3, "base": "x"}, False), ("beaucoup", False)):
            d = copy.deepcopy(self.d)
            d["partenaires"][0]["popularite"] = valeur
            self.assertEqual(catalogue.verifier(d) == [], attendu_ok, valeur)
        d = copy.deepcopy(self.d)   # un catalogue plus ancien, sans le champ, reste valide
        del d["partenaires"][0]["popularite"]
        self.assertEqual(catalogue.verifier(d), [])

    def test_nouvelle_entree_et_sous_categorie_acceptees(self):
        d = copy.deepcopy(self.d)
        neuf = copy.deepcopy(d["partenaires"][0])
        neuf.update(id="nouveau-hub", nom="Nouveau hub", sous_categorie="hub-de-connecteurs", popularite=None)
        d["partenaires"].append(neuf)
        self.assertEqual(catalogue.verifier(d), [])

    def test_fichier_a_jour_avec_son_format(self):
        brut = (RACINE / "partenaires" / "catalogue.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(brut), self.d)

    def test_lire_chemin_donne(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "c.json"
            f.write_text(json.dumps({"version": 1, "partenaires": []}), encoding="utf-8")
            self.assertEqual(catalogue.lire(f)["partenaires"], [])

    def test_aucun_mot_prive(self):
        """Aucun mot d'un fichier tenu hors du dépôt (MYIAFACTORY_MOTS) ne figure dans le catalogue ; passe sans lui."""
        chemin = os.environ.get("MYIAFACTORY_MOTS")
        if not chemin or not Path(chemin).is_file():
            return
        mots = [m.strip().lower() for m in Path(chemin).read_text(encoding="utf-8-sig").splitlines() if m.strip()]
        texte = (RACINE / "partenaires" / "catalogue.json").read_text(encoding="utf-8").lower()
        for m in mots:
            self.assertNotIn(m, texte)


if __name__ == "__main__":
    unittest.main()
