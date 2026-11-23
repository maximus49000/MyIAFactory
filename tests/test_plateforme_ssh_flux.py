"""Session SSH en flux avec laisse (`plateforme_ssh.executer_en_flux`). Faux `popen` : aucune connexion, aucun ssh."""
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import campagne  # noqa: E402
import plateforme_ssh  # noqa: E402

HOTE = "203.0.113.7"
COMMANDE = "~/myiafactory/serveur_ovh/taches/lancer_tests.sh t20261123-101010-abcd 2 4 8192 1800 p -"
LIGNE = b'["python3","-m","unittest"]'


class FauxFlux:
    """Sortie de ssh : morceaux rendus un par un (un morceau peut être une fonction qui le produit), puis fin de fichier.
    `bloquer` : la fin de fichier n'arrive qu'une fois l'évènement posé (ssh tué)."""

    def __init__(self, morceaux=(), bloquer=None, avant_fin=None):
        self.morceaux = list(morceaux)
        self.bloquer = bloquer
        self.avant_fin = avant_fin

    def read1(self, n):
        if self.morceaux:
            m = self.morceaux.pop(0)
            return m() if callable(m) else m
        if self.avant_fin is not None:
            self.avant_fin()
            self.avant_fin = None
        if self.bloquer is not None:
            self.bloquer.wait(5)
        return b""


class FauxEntree:
    def __init__(self, echec=None):
        self.ecrit = b""
        self.closed = False
        self.echec = echec

    def write(self, b):
        if self.echec is not None:
            raise self.echec
        if self.closed:
            raise ValueError("fermée")
        self.ecrit += b
        return len(b)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FauxProcessus:
    def __init__(self, sortie=(), erreur=(), code=0, bloquer=False, tenace=False, echec_ecriture=None):
        self.tue = threading.Event()
        bloc = self.tue if bloquer else None
        self.stdin = FauxEntree(echec_ecriture)
        self.stdout = FauxFlux(sortie, bloquer=bloc)
        self.stderr = FauxFlux(erreur, bloquer=bloc)
        self.code = code
        self.returncode = None
        self.tenace = tenace       # ignore terminate()
        self.termine = False
        self.kill_appele = False

    def wait(self, timeout=None):
        if self.tenace and not self.kill_appele:
            raise subprocess.TimeoutExpired("ssh", timeout)
        self.returncode = self.code
        return self.code

    def poll(self):
        return self.returncode

    def terminate(self):
        self.termine = True
        if not self.tenace:
            self.tue.set()

    def kill(self):
        self.kill_appele = True
        self.code = 1                # comme Windows après TerminateProcess
        self.tue.set()


class FauxPopen:
    def __init__(self, processus=None, echec=None):
        self.processus = processus or FauxProcessus()
        self.echec = echec
        self.appels = []

    def __call__(self, args, **kw):
        self.appels.append((list(args), kw))
        if self.echec is not None:
            raise self.echec
        return self.processus


class Sortie:
    def __init__(self):
        self.morceaux = []

    def write(self, b):
        self.morceaux.append(bytes(b))

    def flush(self):
        pass

    @property
    def tout(self):
        return b"".join(self.morceaux)


def lancer(processus, **kw):
    popen = FauxPopen(processus)
    sortie = kw.pop("sortie", Sortie())
    r = plateforme_ssh.executer_en_flux(HOTE, COMMANDE, Path("cle"), LIGNE, sortie, popen=popen, **kw)
    return r, sortie, popen


class TestFlux(unittest.TestCase):
    def test_relaie_et_rend_le_code(self):
        r, sortie, _ = lancer(FauxProcessus([b"abc"], [b"#fin 1 10 20 3\n"], code=1))
        self.assertEqual(sortie.tout, b"abc")
        self.assertEqual(r["code"], 1)
        self.assertEqual(r["fin_serveur"], (1, 10, 20, 3))
        self.assertEqual(r["octets"], 3)
        self.assertEqual(r["fin"], "abc")
        self.assertEqual(r["raison"], "fin")

    def test_fin_lue_seulement_en_derniere_ligne_d_erreur(self):
        self.assertIsNone(lancer(FauxProcessus([], [b"#fin 0 1 2 0\nautre\n"], code=1))[0]["fin_serveur"])
        hostiles = [
            b"| #fin 0 1 2 0\n",                 # sortie d'erreur du conteneur (préfixée par l'enveloppe)
            b" #fin 0 1 2 0\n", b"#fin 0 1 2 0 x\n", b"#fin 0 1 2\n", b"#fin 0 1 2 0 5\n", b"#fin 999 1 2 3\n",
            b"#fin -1 1 2 3\n", b"#fin 0 1 2 0",  # sans retour final : session coupée au milieu de la ligne
            b"x" * 10000 + b"#fin 0 1 2 0\n",    # ligne démesurée qui finit par une fausse marque
            b"#fin 0 1 2 0\nConnection to h closed by remote host.\n",
            b"#fin\t0 1 2 0\n", b"#FIN 0 1 2 0\n", "#fin ٠ 1 2 0\n".encode("utf-8"),
        ]
        for erreur in hostiles:
            with self.subTest(erreur=erreur[:40]):
                r, _, _ = lancer(FauxProcessus([], [erreur], code=1))
                self.assertIsNone(r["fin_serveur"])
                self.assertEqual(r["code"], 1)
        # La sortie standard (celle des tests) n'est jamais lue comme une marque.
        r, _, _ = lancer(FauxProcessus([b"#fin 0 1 2 0\n"], [], code=1))
        self.assertEqual((r["fin_serveur"], r["code"]), (None, 1))
        # Vraies marques : lignes vides après, retour Windows, marque coupée en deux morceaux de lecture.
        for erreur in ([b"#fin 0 1 2 0\n\n"], [b"#fin 0 1 2 0\r\n"], [b"| #fin 0 9 9 9\n#fin 3 1", b"0 20 0\n"]):
            with self.subTest(vraie=erreur):
                r, _, _ = lancer(FauxProcessus([], erreur, code=0))
                self.assertIsNotNone(r["fin_serveur"])

    def test_attente_signalee(self):
        vues = []
        lancer(FauxProcessus([], [b"#attente 2 3\n#fin 0 1 2 0\n"]), sur_attente=lambda r, t: vues.append((r, t)))
        self.assertEqual(vues, [(2, 3)])
        vues.clear()
        lancer(FauxProcessus([], [b"#attente 1 1 4\n", b"#attente 9\n"]), sur_attente=lambda r, t: vues.append((r, t)))
        self.assertEqual(vues, [(1, 1)])          # jetons libres (tâche 14e) tolérés, ligne incomplète ignorée

        def casse(r, t):
            raise RuntimeError("affichage cassé")
        r, _, _ = lancer(FauxProcessus([], [b"#attente 1 2\n", b"#fin 0 1 2 0\n"]), sur_attente=casse)
        self.assertEqual(r["fin_serveur"], (0, 1, 2, 0))   # la lecture de la sortie d'erreur continue

    def test_laisse_ouverte_jusqu_a_la_fin(self):
        p = FauxProcessus([b"a", b"b"], [b"#fin 0 1 2 0\n"])
        vu = []
        p.stdout.avant_fin = lambda: vu.append((p.stdin.closed, p.stdin.ecrit))
        lancer(p)
        self.assertEqual(vu, [(False, LIGNE + b"\n")])   # entrée encore ouverte à la fin de la sortie standard
        self.assertTrue(p.stdin.closed)                  # puis fermée
        self.assertEqual(p.stdin.ecrit, LIGNE + b"\n")   # rien d'autre n'a été écrit sur la laisse
        p2 = FauxProcessus([], [b"#fin 0 1 2 0\n"])
        lancer(p2)                                       # une ligne déjà terminée n'est pas doublée
        self.assertEqual(p2.stdin.ecrit, LIGNE + b"\n")

    def test_interruption_ferme_la_laisse(self):
        p = FauxProcessus([b"a"], [], bloquer=True)
        with mock.patch.object(campagne, "relayer", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                lancer(p)
        self.assertTrue(p.stdin.closed)
        self.assertTrue(p.termine)

    def test_interruption_tue_si_terminate_ne_suffit_pas(self):
        p = FauxProcessus([b"a"], [], bloquer=True, tenace=True)
        with mock.patch.object(campagne, "relayer", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                lancer(p)
        self.assertTrue(p.termine)
        self.assertTrue(p.kill_appele)

    def test_hote_invalide(self):
        popen = FauxPopen()
        cas = [("-oProxyCommand=x", COMMANDE, LIGNE), ("", COMMANDE, LIGNE), (HOTE, "a\nb", LIGNE),
               (HOTE, "", LIGNE), (HOTE, COMMANDE, b"a\nb"), (HOTE, COMMANDE, b""), (HOTE, COMMANDE, b"x" * 4097),
               (HOTE, COMMANDE, "texte"), (HOTE, COMMANDE, b"a\0b")]
        for hote, commande, ligne in cas:
            with self.subTest(hote=hote, commande=commande, ligne=ligne[:20]):
                with self.assertRaises(ValueError):
                    plateforme_ssh.executer_en_flux(hote, commande, Path("cle"), ligne, Sortie(), popen=popen)
        self.assertEqual(popen.appels, [])

    def test_options_ssh(self):
        _, _, popen = lancer(FauxProcessus([], [b"#fin 0 1 2 0\n"]), delai_connexion=300)
        args, kw = popen.appels[0]
        for option in ("BatchMode=yes", "StrictHostKeyChecking=accept-new", "PasswordAuthentication=no",
                       "ConnectTimeout=30", "ServerAliveInterval=15", "ServerAliveCountMax=4"):
            self.assertIn(option, args)
        self.assertNotIn("StrictHostKeyChecking=no", args)
        self.assertEqual(args[args.index("-i") + 1], str(Path("cle")))
        self.assertEqual(args[-3:], ["--", HOTE, COMMANDE])
        self.assertNotIn(LIGNE.decode(), " ".join(args))   # la commande des tests passe par l'entrée, jamais en argument
        self.assertEqual((kw["stdin"], kw["stdout"], kw["stderr"]), (subprocess.PIPE,) * 3)

    def test_ssh_introuvable(self):
        with self.assertRaises(plateforme_ssh.ErreurSsh):
            plateforme_ssh.executer_en_flux(HOTE, COMMANDE, Path("cle"), LIGNE, Sortie(),
                                            popen=FauxPopen(echec=FileNotFoundError()))

    def test_flux_en_direct_et_dans_l_ordre(self):
        sortie = Sortie()

        def deuxieme():
            self.assertEqual(sortie.tout, b"un ")    # le premier morceau est déjà affiché avant que le second arrive
            return b"deux"
        r, _, _ = lancer(FauxProcessus([b"un ", deuxieme, b" trois"], [b"#fin 0 1 2 0\n"]), sortie=sortie)
        self.assertEqual(sortie.morceaux, [b"un ", b"deux", b" trois"])
        self.assertEqual(r["octets"], 13)

    def test_sortie_d_erreur_montree_sans_marques(self):
        erreur = Sortie()
        r, _, _ = lancer(FauxProcessus([], [b"#attente 1 2\n| Ran 3 tests\n| ", b"OK\nlancer_tests : x\n#fin 0 1 2 0\n"]),
                         sortie_erreur=erreur)
        self.assertEqual(erreur.tout, b"| Ran 3 tests\n| OK\nlancer_tests : x\n")
        self.assertIn("| OK", r["erreur"])
        self.assertNotIn("#fin", r["erreur"])
        self.assertNotIn("#attente", r["erreur"])

    def test_grandes_sorties_bornees(self):
        bloc = b"y" * 65536
        r, sortie, _ = lancer(FauxProcessus([bloc] * 32, [b"| " + b"z" * 1000 + b"\n"] * 2000 +
                                            [b"w" * (1 << 20), b"\n#fin 1 1 2 0\n"], code=1), sortie=Sortie())
        self.assertEqual(r["octets"], 32 * 65536)
        self.assertEqual(len(sortie.tout), 32 * 65536)       # tout est relayé, rien n'est gardé
        self.assertLessEqual(len(r["fin"]), 4096)
        self.assertLessEqual(len(r["erreur"].encode("utf-8")), 65536)
        self.assertEqual(r["fin_serveur"], (1, 1, 2, 0))

    def test_codes_et_raisons(self):
        r, _, _ = lancer(FauxProcessus([], [b"ssh: connect to host h port 22: Connection timed out\n"], code=255))
        self.assertEqual((r["code"], r["fin_serveur"], r["raison"]), (255, None, "connexion"))
        self.assertIn("timed out", r["erreur"])
        r, _, _ = lancer(FauxProcessus([b"moitie"], [], code=255))
        self.assertEqual((r["code"], r["raison"]), (255, "perdue"))
        r, _, _ = lancer(FauxProcessus([], [b"#attente 1 1\n"], code=255))
        self.assertEqual(r["raison"], "perdue")
        for code in (2, 70, 76, 77, 130):
            with self.subTest(code=code):
                r, _, _ = lancer(FauxProcessus([], [b"lancer_tests : refus\n#fin %d 1 1 0\n" % code], code=code))
                self.assertEqual((r["code"], r["raison"], r["code_ssh"]), (code, "fin", code))
        # La marque de l'enveloppe fait foi : la session a pu tomber après elle (ssh rend 255).
        r, _, _ = lancer(FauxProcessus([], [b"#fin 1 1 2 0\n"], code=255))
        self.assertEqual((r["code"], r["code_ssh"], r["fin_serveur"]), (1, 255, (1, 1, 2, 0)))

    def test_ecriture_impossible(self):
        p = FauxProcessus([], [b"ssh: Could not resolve hostname\n"], code=255, echec_ecriture=BrokenPipeError())
        r, _, _ = lancer(p)
        self.assertEqual((r["code"], r["raison"]), (255, "connexion"))

    def test_delai_total_coupe(self):
        p = FauxProcessus([b"debut"], [], bloquer=True)
        t0 = time.monotonic()
        r, _, _ = lancer(p, delai_total=0.05)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertEqual((r["code"], r["raison"], r["fin_serveur"]), (124, "delai", None))
        self.assertTrue(p.kill_appele)
        self.assertTrue(p.stdin.closed)

    def test_silence_coupe(self):
        p = FauxProcessus([], [], bloquer=True)
        r, _, _ = lancer(p, delai_silence=0.05)
        self.assertEqual((r["code"], r["raison"]), (124, "silence"))
        self.assertTrue(p.kill_appele)


if __name__ == "__main__":
    unittest.main()
