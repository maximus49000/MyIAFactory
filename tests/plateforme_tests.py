"""Marqueurs de plateforme des tests : une raison toujours vraie et dite, jamais un ignoré muet.

- `windows_seulement(raison)` : le test ne vaut que sous Windows (registre, PowerShell, chemins `C:\\`…), définitif ;
- `linux_seulement(raison)` : le test ne vaut que sous Linux (bash, docker, systemd…), définitif ;
- `pas_encore_linux(raison)` : provisoire, le test passe sous Windows mais n'est pas encore hermétique sous Linux ;
- `module_pas_encore_linux(raison)` : idem pour un module entier, à appeler dans `setUpModule()`.

Compatible Python 3.9.
"""
import sys
import unittest

WINDOWS = sys.platform == "win32"


def _raison(texte):
    if not isinstance(texte, str) or not texte.strip():
        raise ValueError("une raison vraie et dite est obligatoire")
    return texte.strip()


def windows_seulement(raison):
    return unittest.skipUnless(WINDOWS, "Windows seulement : " + _raison(raison))


def linux_seulement(raison):
    return unittest.skipUnless(sys.platform.startswith("linux"), "Linux seulement : " + _raison(raison))


def pas_encore_linux(raison):
    return unittest.skipUnless(WINDOWS, "À rendre hermétique : " + _raison(raison))


def module_pas_encore_linux(raison):
    texte = _raison(raison)
    if not WINDOWS:
        raise unittest.SkipTest("À rendre hermétique : " + texte)
