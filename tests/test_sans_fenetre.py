"""Le bureau et le moteur tournent sans console : sous Windows, chaque programme qu'ils lancent sans
`CREATE_NO_WINDOW` ouvre une fenêtre noire. Toute commande lancée par le code du produit doit la masquer."""
import re
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIERS = ("bureau", "moteur", "orchestrateur", "installation", "banc")
PAR_DEFAUT = re.compile(r"=\s*subprocess\.(run|Popen)")   # exécuteur par défaut injectable : doit masquer la fenêtre
APPEL = re.compile(r"subprocess\.(run|Popen)\(")
# Lancés depuis une console (installation, outil en ligne de commande), ou masqués par un drapeau calculé ailleurs.
EXCEPTIONS = {
    ("installation", "dossier.py"),            # mklink, pendant l'installation, depuis Claude Code
    ("installation", "lanceur.py"),            # drapeaux calculés par `_drapeaux_windows`
    ("orchestrateur", "verifier_interface.py:38"),   # vérification lancée à la main depuis une console
    ("bureau", "processus.py:146"),            # `ps`, branche hors Windows : pas de console à masquer
}


def _appels():
    for d in DOSSIERS:
        for f in sorted((RACINE / d).rglob("*.py")):
            lignes = f.read_text(encoding="utf-8").splitlines()
            for i, ligne in enumerate(lignes):
                if APPEL.search(ligne) and not ligne.lstrip().startswith(("#", "def ")):
                    yield d, f, i + 1, "\n".join(lignes[i:i + 6])


class SansFenetre(unittest.TestCase):
    def test_chaque_commande_lancee_masque_sa_fenetre(self):
        manquants = []
        for d, f, n, appel in _appels():
            if (d, f.name) in EXCEPTIONS or (d, f"{f.name}:{n}") in EXCEPTIONS:
                continue
            if "CREATE_NO_WINDOW" not in appel and "creationflags=drapeaux" not in appel \
                    and "**options" not in appel and "creationflags=_sans_fenetre()" not in appel:
                manquants.append(f"{f.relative_to(RACINE)}:{n}")
        self.assertEqual(manquants, [], "commandes lancées sans CREATE_NO_WINDOW (fenêtre noire sous Windows)")


class ExecuteursParDefaut(unittest.TestCase):
    def test_ssh_masque_sa_fenetre_par_defaut(self):
        for f in ("plateforme_ssh.py",):
            texte = (RACINE / "outils" / f).read_text(encoding="utf-8")
            self.assertEqual(PAR_DEFAUT.findall(texte), [], f"{f} : exécuteur par défaut sans CREATE_NO_WINDOW")


if __name__ == "__main__":
    unittest.main()
