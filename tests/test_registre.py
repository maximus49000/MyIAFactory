import unittest

from bureau import registre
from bureau.deport_types import CATALOGUES
from bureau.registre import Reglage, lieux_effectifs, valeur_effective

ANDROID = CATALOGUES["application-mobile-android"]
RECETTE = "recette-emulateur"


def reglage(**kw):
    base = dict(id="lecons_auto", section="s", libelle="l", aide="a", forme="booleen",
                niveaux=registre.NIVEAUX, defaut=None, cle="lecons_auto")
    base.update(kw)
    return Reglage(**base)


def bureau(global_=None, type_=None, genre="android", lieux_global=None, lieux_type=None):
    b = {"reglages": global_ or {}, "deport": {"lieux": lieux_global or {}},
         "types": {genre: {"reglages": type_ or {}, "deport": {"lieux": lieux_type or {}}}}}
    return b


class TestValeurEffective(unittest.TestCase):
    def test_projet_l_emporte_sur_type_et_global(self):
        b = bureau({"lecons_auto": False}, {"lecons_auto": False})
        self.assertEqual(valeur_effective(reglage(), {"lecons_auto": True}, b, "android"), (True, "projet"))

    def test_type_l_emporte_sur_global(self):
        b = bureau({"lecons_auto": False}, {"lecons_auto": True})
        self.assertEqual(valeur_effective(reglage(), {}, b, "android"), (True, "type:android"))

    def test_global_puis_defaut(self):
        r = reglage(defaut=False)
        self.assertEqual(valeur_effective(r, {}, bureau({"lecons_auto": True}), "android"), (True, "global"))
        self.assertEqual(valeur_effective(r, {}, bureau(), "android"), (False, "defaut"))

    def test_niveau_non_permis_ignore(self):
        r = reglage(niveaux=("projet",), defaut=False)
        b = bureau({"lecons_auto": True}, {"lecons_auto": True})
        self.assertEqual(valeur_effective(r, {}, b, "android"), (False, "defaut"))

    def test_sans_genre_saute_le_type(self):
        b = bureau(type_={"lecons_auto": True})
        self.assertEqual(valeur_effective(reglage(defaut=False), {}, b, None), (False, "defaut"))


class TestLieuxEffectifs(unittest.TestCase):
    def test_lieux_cascade(self):
        b = bureau(lieux_global={"tests": "github"}, lieux_type={"tests": "serveur"})
        self.assertEqual(lieux_effectifs(ANDROID, {}, b, "android")["tests"], ("serveur", "type:android"))
        projet = {"deport": {"lieux": {"tests": "poste"}}}
        self.assertEqual(lieux_effectifs(ANDROID, projet, b, "android")["tests"], ("poste", "projet"))
        self.assertEqual(lieux_effectifs(ANDROID, {}, b, None)["tests"], ("github", "global"))
        self.assertEqual(lieux_effectifs(ANDROID, {}, bureau(), "android")["tests"], ("poste", "defaut"))

    def test_recette_emulateur_projet_seul(self):
        b = bureau(lieux_global={RECETTE: "serveur"}, lieux_type={RECETTE: "serveur"})
        self.assertEqual(lieux_effectifs(ANDROID, {}, b, "android")[RECETTE], (None, "defaut"))
        projet = {"deport": {"lieux": {RECETTE: "serveur"}}}
        self.assertEqual(lieux_effectifs(ANDROID, projet, b, "android")[RECETTE], ("serveur", "projet"))

    def test_valeur_inconnue_est_ignoree(self):
        b = bureau(lieux_global={"tests": "github"}, lieux_type={"tests": "mars"})
        self.assertEqual(lieux_effectifs(ANDROID, {}, b, "android")["tests"], ("github", "global"))


if __name__ == "__main__":
    unittest.main()
