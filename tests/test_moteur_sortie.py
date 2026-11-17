"""Le journal du moteur redirigé vers un fichier (cp1252 sous Windows) : un caractère hors de la page de code ne doit
jamais l'arrêter (essai réel : « → » dans une ligne du journal, UnicodeEncodeError, toute la factory à l'arrêt)."""
import io
import unittest

from moteur.__main__ import sortie_sure


class SortieSure(unittest.TestCase):
    def test_un_fichier_cp1252_passe_en_utf8(self):
        brut = io.BytesIO()
        flux = io.TextIOWrapper(brut, encoding="cp1252", newline="\n")
        sortie_sure(flux)
        print("t26 → agent-1 : leçon validée", file=flux, flush=True)
        self.assertEqual(brut.getvalue().decode("utf-8"), "t26 → agent-1 : leçon validée\n")

    def test_un_flux_sans_reconfigure_est_laisse_tel_quel(self):
        flux = io.StringIO()
        sortie_sure(flux)
        print("→", file=flux)
        self.assertEqual(flux.getvalue(), "→\n")


if __name__ == "__main__":
    unittest.main()
