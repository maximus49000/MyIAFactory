"""La commande `partenaires` de l'outil : connexions, quotas, choix, règles, usage, relevé. Aucune clé ne sort jamais."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from bureau import cout, releve
from bureau.usage import HistoriqueUsage
from orchestrateur import outil
from partenaires import etat as petat
from partenaires import quota
from tests.orch_aide import RACINE, factory_minimale

CLE = "CLE-SECRETE-RECONNAISSABLE-1234"


class AvecPartenaires(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.racine = Path(t.name)
        self.maison = self.racine / "maison"
        self.maison.mkdir()
        self.projet = self.racine / "projet"
        self.projet.mkdir()
        self.factory = factory_minimale(self.projet)
        p = mock.patch.dict(os.environ, {"HOME": str(self.maison), "USERPROFILE": str(self.maison)})
        p.start()
        self.addCleanup(p.stop)
        for v in ("ELEVENLABS_API_KEY", "DEEPL_API_KEY", "DEEPL_AUTH_KEY"):
            os.environ.pop(v, None)
        self.appels = []

        def ouvrir(url, entetes):
            self.appels.append(url)
            if "elevenlabs" in url:
                return {"character_count": 1000, "character_limit": 10000, "tier": "free"}
            raise OSError("hors ligne")
        q = mock.patch.object(quota, "_ouvrir", ouvrir)
        q.start()
        self.addCleanup(q.stop)

    def p(self, entree):
        code, objet = outil.executer(self.factory, ["partenaires"], entree)
        self.assertEqual(code, 0, objet)
        return objet

    def refus(self, entree):
        code, objet = outil.executer(self.factory, ["partenaires"], entree)
        self.assertEqual(code, 1, objet)
        return objet["erreur"]

    def run_outil(self, *argv, entree=None):
        code, objet = outil.executer(self.factory, list(argv), entree)
        self.assertEqual(code, 0, objet)
        return objet

    def tache(self, **x):
        return self.run_outil("tache", entree={"titre": "Voix du héros", **x})["id"]


class TestPartenairesOutil(AvecPartenaires):
    def test_cle_jamais_ecrite(self):
        os.environ["ELEVENLABS_API_KEY"] = CLE
        (self.projet / ".env").write_text(f"export DEEPL_API_KEY=\"{CLE}\"\n", encoding="utf-8")
        sorties = [self.p({"action": "detecter"})]
        self.assertEqual(sorties[0]["connexions"]["elevenlabs"]["etat"], "declare")
        sorties.append(self.p({"action": "confirmer", "ids": ["elevenlabs"]}))
        sorties.append(self.p({"action": "quota"}))
        self.assertIn("elevenlabs", sorties[-1]["lus"])
        t = self.tache()
        sorties.append(self.p({"action": "usage", "partenaire": "elevenlabs", "tache": t, "quantite": 1200,
                               "unite": "caractères", "cout": 0.3, "devise": "USD"}))
        r = outil.construire_releve(outil.Contexte(self.factory))
        sorties.append(r)
        for s in sorties:
            self.assertNotIn(CLE, json.dumps(s, ensure_ascii=False))
        for f in self.racine.rglob("*"):
            if f.is_file() and f.name != ".env":
                self.assertNotIn(CLE, f.read_text(encoding="utf-8", errors="replace"), f)
        self.assertEqual(r["partenaires"]["etat"]["quotas"]["elevenlabs"]["reste"], 9000)
        self.assertEqual(r["partenaires"]["etat"]["connexions"]["elevenlabs"]["abonnement"], "free")

    def test_quota_une_fois_par_heure(self):
        os.environ["ELEVENLABS_API_KEY"] = CLE
        self.p({"action": "confirmer", "ids": ["elevenlabs", "tripo"]})
        r = self.p({"action": "quota"})
        self.assertEqual(r["lus"], ["elevenlabs"])
        self.assertEqual(r["sautes"], [{"id": "tripo", "raison": "quota non lisible par l'API"}])
        r = self.p({"action": "quota", "ids": ["elevenlabs"]})
        self.assertEqual(r["lus"], [])
        self.assertIn("moins d'une heure", r["sautes"][0]["raison"])
        r = self.p({"action": "quota", "ids": ["elevenlabs"], "force": True})
        self.assertEqual(r["lus"], ["elevenlabs"])
        self.assertEqual(len(self.appels), 2)
        del os.environ["ELEVENLABS_API_KEY"]
        r = self.p({"action": "quota", "ids": ["elevenlabs"], "force": True})
        self.assertIn("aucune clé", r["sautes"][0]["raison"])

    def test_confirmer_choisir_limite(self):
        self.p({"action": "conseils", "besoins": {"voix": [{"id": "elevenlabs", "raison": "Voix naturelles."},
                                                           {"id": "cartesia", "raison": "Secours rapide."}]}})
        self.assertTrue((self.projet / "partenaires.json").is_file())   # à côté du fichier de factory
        r = self.p({"action": "choisir", "besoin": "voix"})
        self.assertEqual(r, {"partenaires": [], "meilleur_non_connecte": "elevenlabs"})
        self.p({"action": "confirmer", "ids": ["cartesia"], "source": "déclaré par l'utilisateur"})
        r = self.p({"action": "choisir", "besoin": "voix"})
        self.assertEqual([x["id"] for x in r["partenaires"]], ["cartesia"])
        self.assertEqual(r["meilleur_non_connecte"], "elevenlabs")
        self.p({"action": "limite", "partenaire": "cartesia", "raison": "402 paiement requis"})
        self.assertEqual(self.p({"action": "choisir", "besoin": "voix"})["partenaires"], [])
        self.assertIn("inconnu", self.refus({"action": "confirmer", "ids": ["inexistant"]}))
        self.assertIn("action", self.refus({"action": "pirater"}))

    def test_fichier_corrompu_ne_bloque_pas(self):
        chemin = self.maison / "MyIAFactory" / "partenaires.json"
        chemin.parent.mkdir(parents=True)
        chemin.write_text('{"connexions": {"x": "connecte", "elevenlabs": {"etat": "connecte"}}, "regles": {"tripo": 3}}',
                          encoding="utf-8")
        r = outil.construire_releve(outil.Contexte(self.factory))
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(list(r["partenaires"]["etat"]["connexions"]), ["elevenlabs"])
        chemin.write_text('{"connexions": {', encoding="utf-8")   # tronqué
        r = outil.construire_releve(outil.Contexte(self.factory))
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(r["partenaires"]["etat"]["regles"], {})   # la règle de départ ne revient pas
        self.assertEqual(self.p({"action": "choisir", "besoin": "voix"})["partenaires"], [])
        self.assertIn("illisible", self.refus({"action": "detecter"}))
        (self.projet / "partenaires.json").write_text("{pas du json", encoding="utf-8")   # conseils illisibles
        self.assertIn("illisibles", self.refus({"action": "conseils"}))

    def test_limite_de_l_agent_tenue_malgre_un_reste(self):
        os.environ["ELEVENLABS_API_KEY"] = CLE
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        self.p({"action": "limite", "partenaire": "elevenlabs", "raison": "402 paiement requis"})
        self.p({"action": "quota", "force": True})   # reste 9000
        self.assertIn("elevenlabs", petat.Etat().lire()["limites"])

    def test_conseils_controles(self):
        e = self.refus({"action": "conseils", "besoins": {"voix": [{"id": "lmnt", "raison": "x"}]}})
        self.assertIn("inactif", e)   # fermé : jamais conseillé
        self.refus({"action": "conseils", "besoins": {"Voix !": []}})
        self.assertEqual(self.p({"action": "conseils"}), {"besoins": {}})

    def test_regles_par_l_outil(self):
        r = self.p({"action": "regle", "partenaire": "tripo", "operation": "ajouter", "texte": "Format GLB."})
        self.assertEqual(r["regle"]["id"], "r2")   # r1 : la règle de départ proposée
        self.refus({"action": "regle", "partenaire": "tripo", "operation": "modifier", "id": "r9", "texte": "x"})
        self.refus({"action": "regle", "partenaire": "tripo", "operation": "ajouter", "texte": "x" * 501})
        self.p({"action": "regle", "partenaire": "tripo", "operation": "supprimer", "id": "r1"})
        regles = petat.Etat().lire()["regles"]["tripo"]
        self.assertEqual([x["texte"] for x in regles], ["Format GLB."])

    def test_depart_porte_les_regles(self):
        self.p({"action": "regle", "partenaire": "elevenlabs", "operation": "ajouter", "texte": "Voix « calme », 0,9×."})
        t = self.tache(role="dev", partenaires=["elevenlabs", "tripo"])
        m = self.run_outil("depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertIn("## Règles de tes partenaires", m)
        self.assertIn("### ElevenLabs\n- Voix « calme », 0,9×.", m)
        self.assertIn("### Tripo\n- " + petat.REGLE_TRIPO, m)
        self.assertIn('"action": "usage"', m)
        lot = self.run_outil("depart", entree={"agent": "dev-1", "taches": [t]})["message"]
        self.assertIn("Voix « calme », 0,9×.", lot)
        sans = self.tache(role="dev")
        self.assertNotIn("Règles de tes partenaires", self.run_outil("depart", entree={"agent": "dev-1", "tache": sans})["message"])
        code, objet = outil.executer(self.factory, ["tache"], {"id": t, "partenaires": ["inexistant"]})
        self.assertEqual(code, 1, objet)

    def test_inscrire_le_fait_seulement(self):
        r = self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True, "note": "compte gratuit, offre Pro"})
        self.assertEqual((r["inscrit"], r["inscription"]["note"]), (True, "compte gratuit, offre Pro"))
        self.assertEqual(list(petat.Etat().lire()["inscriptions"]), ["tripo"])
        self.assertIn("inscrit", self.refus({"action": "inscrire", "partenaire": "tripo", "inscrit": "oui"}))
        self.assertIn("inconnu", self.refus({"action": "inscrire", "partenaire": "inexistant", "inscrit": True}))
        self.assertIn("mot de passe", self.refus({"action": "inscrire", "partenaire": "tripo", "inscrit": True,
                                                  "note": "mot de passe : hunter2"}))
        self.assertIn("fermé", self.refus({"action": "inscrire", "partenaire": "lmnt", "inscrit": True}))
        self.assertEqual(list(petat.Etat().lire()["inscriptions"]), ["tripo"])   # les refus n'ont rien changé
        r = outil.construire_releve(outil.Contexte(self.factory))
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(list(r["partenaires"]["etat"]["inscriptions"]), ["tripo"])
        self.assertIn("depuis", r["partenaires"]["etat"]["inscriptions"]["tripo"])
        self.assertIn("inscriptions", releve.normaliser(r)["partenaires"]["etat"])
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": False})
        self.assertEqual(petat.Etat().lire()["inscriptions"], {})

    def test_choisir_dit_les_inscrits(self):
        self.p({"action": "conseils", "besoins": {"3d": [{"id": "tripo", "raison": "Modèles 3D."}]}})
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True})
        r = self.p({"action": "choisir", "besoin": "3d"})
        self.assertEqual(r["partenaires"], [])
        self.assertEqual(r["inscrits"][0]["id"], "tripo")
        self.assertEqual(r["inscrits"][0]["nom"], "Tripo")
        self.assertTrue(r["inscrits"][0]["site"].startswith("https://"))

    def test_releve_v4_partenaires(self):
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        self.p({"action": "conseils", "besoins": {"voix": [{"id": "elevenlabs", "raison": "Voix naturelles."}]}})
        self.p({"action": "limite", "partenaire": "elevenlabs", "raison": "quota épuisé"})
        r = outil.construire_releve(outil.Contexte(self.factory))
        self.assertEqual(releve.valider(r), [])
        pa = r["partenaires"]
        self.assertEqual(sum(len(v) for v in pa["categories"].values()), 379)
        carte = next(x for x in pa["categories"]["voix-audio"] if x["id"] == "elevenlabs")
        self.assertNotIn("lecteur", carte)
        self.assertEqual(pa["etat"]["connexions"]["elevenlabs"]["etat"], "connecte")
        self.assertIn("elevenlabs", pa["etat"]["limites"])
        self.assertIn("tripo", pa["etat"]["regles"])
        self.assertEqual(pa["conseils"], {"voix": [{"id": "elevenlabs", "raison": "Voix naturelles."}]})
        self.assertEqual(pa["maj_catalogue"], "2026-11-11")
        self.assertIn("fiches à revérifier", pa["cout_maj"]["texte"])
        self.assertIsNone(pa["cout_maj"]["euros"])   # aucun prix enregistré : inconnu, jamais inventé
        n = releve.normaliser(r)
        self.assertIn("partenaires", n)

    def test_usage_partenaire_facture_par_tache(self):
        t1, t2 = self.tache(), self.tache()
        self.p({"action": "usage", "partenaire": "elevenlabs", "tache": t1, "quantite": 1000, "unite": "caractères",
                "cout": 2.0, "devise": "USD"})
        self.p({"action": "usage", "partenaire": "elevenlabs", "tache": t2, "quantite": 500, "unite": "caractères",
                "cout": 1.0, "devise": "EUR", "estime": True})
        self.p({"action": "usage", "partenaire": "tripo", "tache": t1, "quantite": 1, "unite": "modèle"})
        self.run_outil("usage", entree={"modele": "Sonnet", "tache": t1, "entree": 1000, "sortie": 100})
        r = outil.construire_releve(outil.Contexte(self.factory))
        self.assertEqual(releve.valider(r), [])
        lignes = [u for u in r["usage"] if u.get("genre") == "partenaire"]
        self.assertEqual(len(lignes), 3)
        h = HistoriqueUsage(self.racine / "h.jsonl")
        h.integrer(releve.normaliser(r))
        usages = h.lire()
        self.assertEqual(len(usages), 4)

        def prix_de(modele, date_iso):
            return {"entree": 3.0, "sortie": 15.0, "cache_lecture": None, "cache_ecriture": None}, "2026-11-11", False

        f = cout.facturation(usages, prix_de, r, "7j", datetime.now(timezone.utc), lambda d: (0.9, "2026-11-11"))
        el = f["partenaires"]["elevenlabs"]
        self.assertEqual(el["nom"], "ElevenLabs")
        self.assertAlmostEqual(el["total"], 2.8)
        self.assertEqual(el["origine"], [{"montant": 1.0, "devise": "EUR"}, {"montant": 2.0, "devise": "USD"}])
        self.assertTrue(el["estime"])
        self.assertEqual(el["taches"], {t1: 1.8, t2: 1.0})
        self.assertGreater(f["total"], 0)   # les tokens restent comptés à part

    def test_cout_absent_non_chiffre(self):
        t = self.tache()
        self.p({"action": "usage", "partenaire": "tripo", "tache": t, "quantite": 3, "unite": "modèles"})
        self.p({"action": "usage", "partenaire": "meshy", "tache": t, "quantite": 1, "unite": "modèle", "cout": 4,
                "devise": "USD"})
        self.assertIn("devise", self.refus({"action": "usage", "partenaire": "tripo", "quantite": 1, "unite": "x",
                                            "cout": 1}))
        r = releve.normaliser(outil.construire_releve(outil.Contexte(self.factory)))
        h = HistoriqueUsage(self.racine / "h.jsonl")
        h.integrer(r)
        f = cout.facturation(h.lire(), lambda m, d: (None, None, False), r, "7j", datetime.now(timezone.utc),
                             lambda d: (None, None))   # aucun taux lu : le dollar n'est pas converti
        self.assertEqual(f["partenaires"]["tripo"]["total"], 0)
        self.assertEqual(f["partenaires"]["tripo"]["non_chiffre"], 1)
        self.assertEqual(f["partenaires"]["meshy"]["non_chiffre"], 1)
        self.assertEqual(f["partenaires"]["meshy"]["origine"], [{"montant": 4, "devise": "USD"}])

    def test_usage_partenaire_jamais_repris_comme_tokens(self):
        u = self.p({"action": "usage", "partenaire": "tripo", "quantite": 1, "unite": "modèle"})["id"]
        code, objet = outil.executer(self.factory, ["usage"], {"id": u, "modele": "Sonnet", "entree": 1, "sortie": 1})
        self.assertEqual(code, 1, objet)


class TestOffres(AvecPartenaires):
    def setUp(self):
        super().setUp()
        self.skill = self.racine / "skill"
        (self.skill / "partenaires").mkdir(parents=True)
        shutil.copy(RACINE / "partenaires" / "catalogue.json", self.skill / "partenaires" / "catalogue.json")
        self.factory = factory_minimale(self.projet, skill=str(self.skill), mots_interdits=["Zorglub"])
        self.git = []
        g = mock.patch.object(outil, "GIT", lambda args, cwd: (self.git.append(args[0]), (0, ""))[1])
        g.start()
        self.addCleanup(g.stop)

    def fiche(self, **x):
        cat = json.loads((self.skill / "partenaires" / "catalogue.json").read_text(encoding="utf-8"))
        return {**next(p for p in cat["partenaires"] if p["id"] == "tripo"), "verifie_le": "2026-12-01", **x}

    def test_a_refaire_et_offres(self):
        r = self.p({"action": "a_refaire"})
        self.assertIn("ids", r)
        self.assertIn("texte", r["cout"])
        o = self.p({"action": "offres", "partenaires": [self.fiche(gratuit="20 crédits")]})
        self.assertEqual(o["ids"], ["tripo"])
        self.assertEqual(self.git, ["status", "status", "fetch", "rev-list", "add", "commit", "push"])   # sans pull : rien de neuf
        cat = json.loads((self.skill / "partenaires" / "catalogue.json").read_text(encoding="utf-8"))
        tripo = next(p for p in cat["partenaires"] if p["id"] == "tripo")
        self.assertEqual((tripo["gratuit"], tripo["verifie_le"]), ("20 crédits", "2026-12-01"))
        self.assertEqual(len(cat["partenaires"]), 379)

    def test_offres_refusees(self):
        avant = (self.skill / "partenaires" / "catalogue.json").read_text(encoding="utf-8")
        self.assertIn("refusé", self.refus({"action": "offres", "partenaires": [self.fiche(site="http://x.example")]}))
        self.assertIn("mot interdit", self.refus({"action": "offres", "partenaires": [self.fiche(description="Pour Zorglub.")]}))
        self.assertEqual((self.skill / "partenaires" / "catalogue.json").read_text(encoding="utf-8"), avant)


if __name__ == "__main__":
    unittest.main()
