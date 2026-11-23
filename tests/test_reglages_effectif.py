"""Les valeurs effectives des réglages (projet > type > global > défaut) que lisent le moteur et l'état du bureau."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bureau import reglages

ANDROID = "application-mobile-android"


def bureau_avec(fichier_reglages, **cles):
    """Un fichier du bureau à côté de `fichier_reglages` (son seul projet), avec les clés données (`reglages`,
    `types`…). Rend son chemin."""
    fichier_reglages = Path(fichier_reglages)
    if not fichier_reglages.exists():
        fichier_reglages.write_text("{}", encoding="utf-8")
    b = fichier_reglages.parent / "bureau-essai.json"
    b.write_text(json.dumps({"projets": [fichier_reglages.name], **cles}), encoding="utf-8")
    return b


class Effectif(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.regl = self.tmp / "reglages.json"
        self.regl.write_text("{}", encoding="utf-8")

    def projet(self, **cles):
        self.regl.write_text(json.dumps(cles), encoding="utf-8")

    def en_android(self):
        (self.tmp / "factory.json").write_text(json.dumps({"genre": ANDROID}), encoding="utf-8")

    def effectif(self, **cles):
        return reglages.charger_effectif(self.regl, bureau_avec(self.regl, **cles))

    def test_le_global_agit_sans_valeur_du_projet(self):
        self.assertIs(self.effectif(reglages={"lecons_auto": True})["lecons_auto"], True)

    def test_le_projet_l_emporte_sur_le_global(self):
        self.projet(lecons_auto=False)
        self.assertIs(self.effectif(reglages={"lecons_auto": True})["lecons_auto"], False)

    def test_le_type_l_emporte_sur_le_global(self):
        self.en_android()
        r = self.effectif(reglages={"une_session_moyenne": False, "analyse_blocages": True},
                          types={ANDROID: {"reglages": {"une_session_moyenne": True, "analyse_blocages": False}}})
        self.assertEqual((r["une_session_moyenne"], r["analyse_blocages"]), (True, False))

    def test_le_type_d_un_autre_genre_n_agit_pas(self):
        r = self.effectif(types={ANDROID: {"reglages": {"livraison_sur_demande": True}}})
        self.assertIs(r["livraison_sur_demande"], False)        # projet générique : pas de niveau type

    def test_le_projet_l_emporte_sur_le_type(self):
        self.en_android()
        self.projet(livraison_sur_demande=False)
        r = self.effectif(reglages={"livraison_sur_demande": True},
                          types={ANDROID: {"reglages": {"livraison_sur_demande": True}}})
        self.assertIs(r["livraison_sur_demande"], False)

    def test_sans_fichier_du_bureau_comportement_inchange(self):
        self.projet(lecons_auto=True, charge_max=60)
        self.assertEqual(reglages.charger_effectif(self.regl), reglages.charger(self.regl))
        self.assertEqual(reglages.charger_effectif(self.regl, None), reglages.charger(self.regl))

    def test_fichier_du_bureau_illisible_le_projet_seul(self):
        self.projet(livraison_sur_demande=True)
        attendu = reglages.charger(self.regl)
        abime = self.tmp / "abime.json"
        abime.write_text("{pas du json", encoding="utf-8")
        sans_projets = self.tmp / "sans-projets.json"
        sans_projets.write_text(json.dumps({"reglages": {"lecons_auto": True}}), encoding="utf-8")
        for bureau in (abime, self.tmp / "absent.json", sans_projets, object()):
            self.assertEqual(reglages.charger_effectif(self.regl, bureau), attendu, bureau)

    def test_des_reglages_du_projet_illisibles_levent_comme_avant(self):
        self.regl.write_text("{abime", encoding="utf-8")
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.charger_effectif(self.regl, bureau_avec(self.tmp / "autre.json"))

    def test_les_accords_du_projet_ne_s_heritent_jamais(self):
        """`cloud_dossier_approuve` et `livraison_github` posés à la main au global ou au type n'agissent pas."""
        self.en_android()
        haut = {"cloud_dossier_approuve": True, "livraison_github": True}
        r = self.effectif(reglages=haut, types={ANDROID: {"reglages": haut}})
        self.assertEqual((r["cloud_dossier_approuve"], r["livraison_github"]), (False, False))
        self.projet(cloud_dossier_approuve=True, livraison_github=True)
        r = self.effectif(reglages={"cloud_dossier_approuve": False, "livraison_github": False})
        self.assertEqual((r["cloud_dossier_approuve"], r["livraison_github"]), (True, True))

    def test_une_valeur_qui_n_est_pas_un_booleen_est_ignoree_et_dite(self):
        self.en_android()
        cles = {"reglages": {"lecons_auto": "oui", "analyse_blocages": "non", "livraison_sur_demande": None},
                "types": {ANDROID: {"reglages": {"une_session_moyenne": 1}}}}
        r = self.effectif(**cles)
        self.assertEqual((r["lecons_auto"], r["analyse_blocages"], r["livraison_sur_demande"],
                          r["une_session_moyenne"]), (False, True, False, False))     # les défauts
        lu = reglages.lire_bureau(bureau_avec(self.regl, **cles))
        self.assertEqual(lu["reglages"], {})
        self.assertEqual(lu["types"][ANDROID]["reglages"], {})
        self.assertEqual(len(lu["ignores"]), 4)
        self.assertTrue(any("lecons_auto" in x and "ignor" in x for x in lu["ignores"]))
        self.assertTrue(any("une_session_moyenne" in x and "types." + ANDROID in x for x in lu["ignores"]))

    def test_une_mauvaise_valeur_globale_laisse_le_type_agir(self):
        self.en_android()
        r = self.effectif(reglages={"lecons_auto": True}, types={ANDROID: {"reglages": {"lecons_auto": "non"}}})
        self.assertIs(r["lecons_auto"], True)


if __name__ == "__main__":
    unittest.main()
