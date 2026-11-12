"""Le brouillon de l'échange avec le chef : créé avant le projet, dans ~/MyIAFactory/creations (HOME est temporaire)."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from installation import brouillons, dossier
from installation.dossier import Echec
from tests.inst_aide import AvecMaison

INFOS = {"parent": "C:/x", "nom": "Casse-briques", "mots_interdits": ["secretcorp"], "facturation": False,
         "github": False, "description": "Un jeu de casse-briques."}
T0 = datetime(2026, 11, 1, 10, 0)


class Base(AvecMaison):
    def setUp(self):
        super().setUp()
        self.d = self.base / "creations"
        self.commun = self.base / "usage-creations.jsonl"

    def creer(self, **kw):
        return brouillons.creer(dict(INFOS, **kw), dossier=self.d, maintenant=T0)


class TestBrouillons(Base):
    def test_creer_lire_ecrire(self):
        b = self.creer()
        self.assertRegex(b["id"], brouillons.MOTIF_ID.pattern)
        self.assertEqual((b["echange"], b["tours"], b["proposition"], b["usages"], b["erreur"], b["en_cours"]),
                         ([], 0, None, [], None, None))
        b["tours"] = 2
        brouillons.ecrire(b, dossier=self.d, maintenant=T0 + timedelta(hours=1))
        lu = brouillons.lire(b["id"], dossier=self.d)
        self.assertEqual((lu["tours"], lu["infos"]["nom"]), (2, "Casse-briques"))
        self.assertGreater(lu["maj"], lu["cree"])
        self.assertEqual([p.name for p in self.d.iterdir()], [f"{b['id']}.json"])   # pas de reste d'écriture

    def test_dossier_par_defaut_sous_la_racine(self):
        b = brouillons.creer(dict(INFOS))
        self.assertTrue((dossier.racine() / "creations" / f"{b['id']}.json").is_file())

    def test_id_refuse_jamais_un_chemin(self):
        for mauvais in ("../x", "c123", str(self.base / "x"), "c0123456789ab\n", "C0123456789AB", "", None, 3):
            with self.assertRaises(Echec, msg=repr(mauvais)):
                brouillons.lire(mauvais, dossier=self.d)
        with self.assertRaises(Echec):
            brouillons.ecrire({"id": "../x"}, dossier=self.d)
        with self.assertRaises(Echec):
            brouillons.abandonner("../x", dossier=self.d, commun=self.commun)

    def test_introuvable_et_illisible(self):
        with self.assertRaises(Echec):
            brouillons.lire("c0123456789a", dossier=self.d)
        self.d.mkdir()
        (self.d / "c0123456789a.json").write_text("{pas du json", encoding="utf-8")
        with self.assertRaises(Echec):
            brouillons.lire("c0123456789a", dossier=self.d)

    def test_lister_plus_recent_d_abord_illisible_ignore(self):
        a = self.creer(nom="Ancien")
        b = self.creer(nom="Recent")
        b["proposition"] = {"x": 1}
        b["tours"] = 3
        brouillons.ecrire(b, dossier=self.d, maintenant=T0 + timedelta(days=1))
        (self.d / "c0123456789a.json").write_text("n'importe quoi", encoding="utf-8")
        (self.d / "autre.txt").write_text("x", encoding="utf-8")
        liste = brouillons.lister(dossier=self.d)
        self.assertEqual([x["nom"] for x in liste], ["Recent", "Ancien"])
        self.assertEqual((liste[0]["etat"], liste[0]["tours"], liste[1]["etat"]), ("proposition", 3, "questions"))
        self.assertEqual(brouillons.lister(dossier=self.base / "rien"), [])
        self.assertEqual(a["id"], liste[1]["id"])

    def test_abandonner_garde_les_usages(self):
        b = self.creer()
        b["usages"] = [{"modele": "sonnet", "entree": 2, "sortie": 10, "cache_lecture": 0, "cache_ecriture": 5,
                        "t": "2026-11-01T10:00:00"}]
        brouillons.ecrire(b, dossier=self.d, maintenant=T0)
        brouillons.abandonner(b["id"], dossier=self.d, commun=self.commun)
        self.assertFalse((self.d / f"{b['id']}.json").exists())
        self.assertEqual(brouillons.usages_abandonnes(commun=self.commun), b["usages"])
        c = self.creer(nom="Autre")
        brouillons.abandonner(c["id"], dossier=self.d, commun=self.commun)   # sans usage : rien d'ajouté
        self.assertEqual(len(brouillons.usages_abandonnes(commun=self.commun)), 1)
        self.assertEqual(brouillons.usages_abandonnes(commun=self.base / "absent.jsonl"), [])

    def test_retirer_ne_garde_rien(self):
        b = self.creer()
        b["usages"] = [{"modele": "sonnet", "entree": 1, "sortie": 1, "cache_lecture": 0, "cache_ecriture": 0}]
        brouillons.ecrire(b, dossier=self.d, maintenant=T0)
        brouillons.retirer(b["id"], dossier=self.d)
        self.assertFalse((self.d / f"{b['id']}.json").exists())
        brouillons.retirer(b["id"], dossier=self.d)   # déjà parti : sans erreur

    def test_purge_apres_30_jours(self):
        vieux, recent = self.creer(nom="Vieux"), self.creer(nom="Recent")
        vieux["usages"] = [{"modele": "sonnet", "entree": 1, "sortie": 1, "cache_lecture": 0, "cache_ecriture": 0}]
        brouillons.ecrire(vieux, dossier=self.d, maintenant=T0)
        brouillons.ecrire(recent, dossier=self.d, maintenant=T0 + timedelta(days=25))
        purges = brouillons.purger(maintenant=T0 + timedelta(days=31), dossier=self.d, commun=self.commun)
        self.assertEqual(purges, [vieux["id"]])
        self.assertEqual([x["nom"] for x in brouillons.lister(dossier=self.d)], ["Recent"])
        self.assertEqual(len(brouillons.usages_abandonnes(commun=self.commun)), 1)
        self.assertEqual(brouillons.purger(maintenant=T0 + timedelta(days=31), dossier=self.d, commun=self.commun), [])

    def test_brouillon_sans_cle(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-secret-1234"}):
            b = self.creer()
            b["usages"] = [{"modele": "sonnet", "entree": 1, "sortie": 1, "cache_lecture": 0, "cache_ecriture": 0}]
            brouillons.ecrire(b, dossier=self.d, maintenant=T0)
        contenu = (self.d / f"{b['id']}.json").read_text(encoding="utf-8")
        self.assertNotIn("sk-ant", contenu)
        self.assertNotIn("ANTHROPIC", contenu)

    def test_infos_sans_cle_refusees(self):
        with self.assertRaises(Echec):
            brouillons.creer(dict(INFOS, cle_api="sk-ant-xxx"), dossier=self.d)


class TestTourEnCours(Base):
    def setUp(self):
        super().setUp()
        brouillons._VIVANTS.clear()
        self.addCleanup(brouillons._VIVANTS.clear)

    def test_un_seul_tour_a_la_fois(self):
        b = self.creer()
        brouillons.commencer_tour(b["id"], {"correction": None}, dossier=self.d, maintenant=T0)
        self.assertEqual(brouillons.etat_du_tour(brouillons.lire(b["id"], dossier=self.d)), "en_cours")
        with self.assertRaises(brouillons.TourEnCours):
            brouillons.commencer_tour(b["id"], {}, dossier=self.d, maintenant=T0)
        brouillons.finir_tour(b["id"], dossier=self.d)
        self.assertEqual(brouillons.etat_du_tour(brouillons.lire(b["id"], dossier=self.d)), "libre")

    def test_tour_interrompu_repris(self):
        b = self.creer()
        brouillons.commencer_tour(b["id"], {"correction": "plus court"}, dossier=self.d, maintenant=T0)
        brouillons._VIVANTS.clear()    # le bureau a été relancé : rien ne tourne plus
        lu = brouillons.lire(b["id"], dossier=self.d)
        self.assertEqual(brouillons.etat_du_tour(lu), "interrompu")
        r = brouillons.commencer_tour(b["id"], {}, dossier=self.d, maintenant=T0)   # pas bloqué pour toujours
        self.assertEqual(r["en_cours"]["correction"], "plus court")   # la demande interrompue est reprise
        self.assertEqual(brouillons.etat_du_tour(r), "en_cours")

    def test_abandon_refuse_pendant_un_tour(self):
        b = self.creer()
        brouillons.commencer_tour(b["id"], {}, dossier=self.d, maintenant=T0)
        with self.assertRaises(brouillons.TourEnCours):
            brouillons.abandonner(b["id"], dossier=self.d, commun=self.commun)
        brouillons.finir_tour(b["id"], dossier=self.d)
        brouillons.abandonner(b["id"], dossier=self.d, commun=self.commun)

    def test_purge_ignore_un_tour_en_cours(self):
        b = self.creer()
        brouillons.commencer_tour(b["id"], {}, dossier=self.d, maintenant=T0)
        self.assertEqual(brouillons.purger(maintenant=T0 + timedelta(days=60), dossier=self.d, commun=self.commun), [])
