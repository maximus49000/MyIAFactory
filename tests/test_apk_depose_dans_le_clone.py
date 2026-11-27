"""Une vérification qui porte sur un APK déjà construit le trouve DANS SON CLONE (FM_Stats a24, t314 : « les livrables rapatriés ne
sont pas déposés dans le clone du testeur ») : la demande, l'envoi, l'entrée du conteneur, la boucle, la consigne."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests import test_moteur_registre_apk as reg
from tests import test_serveur_agent as tsa

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_agent as sa  # noqa: E402

ENTREE_AGENT = RACINE / "serveur_ovh" / "images" / "agent" / "entree-agent.py"
DEPOT = "android_app/build/app/outputs/flutter-apk/app-client-release.apk"


def charger_entree():
    spec = importlib.util.spec_from_file_location("entree_agent_depot", ENTREE_AGENT)
    ea = importlib.util.module_from_spec(spec)
    avant, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(ea)
    finally:
        sys.dont_write_bytecode = avant
    return ea


class Demande(unittest.TestCase):
    def valide(self, **plus):
        return sa.valider_demande_agent({**tsa.brut(), "id": tsa.ID1, **plus})

    def test_apk_depot_valide_ou_refuse(self):
        self.assertEqual(self.valide(apk_depot=DEPOT).apk_depot, DEPOT)
        self.assertIsNone(self.valide().apk_depot)
        for mauvais in ("../x.apk", "/etc/x.apk", ".git/x.apk", "a/.cache/x.apk", "x.txt", "a//b.apk", "", 3, "a b.apk", "a/../b.apk"):
            with self.subTest(mauvais), self.assertRaises(ValueError):
                self.valide(apk_depot=mauvais)

    def test_la_demande_dit_apk_depot_seulement_quand_il_y_en_a_un(self):
        self.assertNotIn("apk_depot", sa._demande_dict(self.valide()))
        self.assertEqual(sa._demande_dict(self.valide(apk_depot=DEPOT))["apk_depot"], DEPOT)


class Envoi(tsa.Base):
    """L'APK part dans entree/app.apk même hors du mode pilote, quand la demande annonce un emplacement."""

    def test_l_apk_part_avec_la_demande_en_mode_seul(self):
        self.lancer(self.demande(apk_depot=DEPOT), apk=tsa.APK)
        self.assertEqual(self.srv.entrees[tsa.ID1]["entree/app.apk"], tsa.APK)
        self.assertEqual(json.loads(self.srv.entrees[tsa.ID1]["entree/demande.json"])["apk_depot"], DEPOT)

    def test_sans_apk_depot_rien_ne_part(self):
        self.lancer(apk=tsa.APK)
        self.assertNotIn("entree/app.apk", self.srv.entrees[tsa.ID1])
        self.assertNotIn("apk_depot", json.loads(self.srv.entrees[tsa.ID1]["entree/demande.json"]))

    def test_apk_depot_sans_apk_valide_est_refuse(self):
        from tests.test_serveur_agent import st
        for apk in (None, b"", "texte"):
            with self.assertRaises(st.RefusLancement):
                self.lancer(self.demande(apk_depot=DEPOT), apk=apk)
        self.assertEqual(self.srv.appels, [])


class Entree(unittest.TestCase):
    """`entree-agent.py` : l'APK est copié de /entree/app.apk dans le clone, sans lien ni sortie du dépôt."""

    def setUp(self):
        self.ea = charger_entree()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.entree, self.depot = self.tmp / "entree", self.tmp / "projet"
        self.entree.mkdir()
        self.depot.mkdir()
        (self.entree / "app.apk").write_bytes(b"APK-OCTETS")
        self.c = {"entree": str(self.entree)}

    def deposer(self, chemin=DEPOT):
        self.ea.deposer_l_apk(self.c, {"apk_depot": chemin}, str(self.depot))

    def test_l_apk_est_depose_a_l_emplacement_annonce(self):
        self.deposer()
        cible = self.depot / DEPOT
        self.assertEqual(cible.read_bytes(), b"APK-OCTETS")
        self.assertEqual(cible.stat().st_mode & 0o777, 0o644)

    def test_sans_apk_depot_rien_n_est_fait(self):
        self.ea.deposer_l_apk(self.c, {"apk_depot": None}, str(self.depot))
        self.assertEqual(list(self.depot.iterdir()), [])

    def test_un_dossier_du_chemin_qui_est_un_lien_est_refuse(self):
        dehors = self.tmp / "dehors"
        dehors.mkdir()
        (self.depot / "android_app").symlink_to(dehors)
        with self.assertRaises(self.ea.Refus):
            self.deposer()
        self.assertEqual(list(dehors.iterdir()), [])

    def test_une_cible_qui_est_un_lien_est_refusee(self):
        (self.depot / "android_app" / "build").mkdir(parents=True)
        victime = self.tmp / "victime.apk"
        victime.write_bytes(b"x")
        (self.depot / "android_app" / "build" / "a.apk").symlink_to(victime)
        with self.assertRaises(self.ea.Refus):
            self.deposer("android_app/build/a.apk")
        self.assertEqual(victime.read_bytes(), b"x")

    def test_app_apk_absent_ou_lien_refuse(self):
        (self.entree / "app.apk").unlink()
        with self.assertRaises(self.ea.Refus):
            self.deposer()

    def test_la_demande_du_conteneur_valide_apk_depot(self):
        base = {"tache": "t1", "branche": "main", "base": "a" * 40}
        self.assertEqual(self.ea.valider_demande({**base, "apk_depot": DEPOT})["apk_depot"], DEPOT)
        self.assertIsNone(self.ea.valider_demande(base)["apk_depot"])
        for mauvais in ("../x.apk", ".git/x.apk", "x.txt", 3):
            with self.assertRaises(self.ea.Refus):
                self.ea.valider_demande({**base, "apk_depot": mauvais})


class DansLaBoucle(reg.Depot):
    def tache(self, titre="Vérification de l'APK Client", role="testeur"):
        tid = self.ok("tache", entree={"titre": titre, "fonctionnalite": "f1", "role": role, "etape": "flux:essai",
                                       "colonne": "essai", "active": False})["id"]
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    def test_une_verification_avec_un_apk_existant_le_recoit_a_deposer(self):
        from moteur import regles
        self.construire()
        chemin, rel = regles.apk_a_deposer(self.projet, self.tache())
        self.assertEqual(rel, reg.CLIENT)
        self.assertEqual(Path(chemin), self.d / reg.CLIENT)
        (texte,) = regles._consigne_de_l_apk_existant(self.projet, self.tache())
        self.assertIn("déposé à cet emplacement de ton clone", texte)
        self.assertNotIn("Construis-le", texte)                       # aucune demande de construction

    def test_sans_apk_correspondant_rien_n_est_depose_et_la_consigne_demande_une_construction(self):
        from moteur import regles
        self.construire()
        self.ecrire(f"{reg.APP}/lib/main.dart", "void main() { nouveau(); }\n")
        self.valider("code")
        self.assertIsNone(regles.apk_a_deposer(self.projet, self.tache()))
        (texte,) = regles._consigne_de_l_apk_existant(self.projet, self.tache("Vérification de l'APK Client"))
        self.assertIn("Construis-le UNE fois", texte)

    def test_un_autre_metier_ne_recoit_rien_et_un_apk_perime_non_plus(self):
        from moteur import regles
        self.construire()
        self.assertIsNone(regles.apk_a_deposer(self.projet, self.tache(role="dev")))

    def test_un_apk_dont_le_chemin_est_refuse_n_est_pas_depose(self):
        from moteur import regles
        self.ecrire(f"{reg.APP}/.cache/app-client-release.apk", "APK")
        from moteur import registre_apk
        registre_apk.enregistrer(str(self.d), f"{reg.APP}/.cache/app-client-release.apk")
        self.assertIsNone(regles.apk_a_deposer(self.projet, self.tache()))


if __name__ == "__main__":
    unittest.main()
