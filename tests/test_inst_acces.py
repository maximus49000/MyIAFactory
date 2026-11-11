"""Les adresses du bureau ouvert au téléphone : Tailscale et le réseau local privé. Rien ne sort sur le réseau."""
import subprocess
import unittest

from installation import acces


class FausseSocket:
    def __init__(self, adresse):
        self.adresse = adresse

    def __call__(self, *args):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def connect(self, cible):
        self.cible = cible

    def getsockname(self):
        return (self.adresse, 50000)


class TestAcces(unittest.TestCase):
    def test_tailscale_absent_none(self):
        def absent(*a, **k):
            raise FileNotFoundError("tailscale")
        self.assertIsNone(acces.adresse_tailscale(executer=absent))

        def delai(*a, **k):
            raise subprocess.TimeoutExpired("tailscale", 5)
        self.assertIsNone(acces.adresse_tailscale(executer=delai))
        self.assertIsNone(acces.adresse_tailscale(
            executer=lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="arrêté")))
        self.assertIsNone(acces.adresse_tailscale(
            executer=lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="pas une adresse\n", stderr="")))

    def test_tailscale_premiere_ligne(self):
        vu = {}

        def ok(cmd, **k):
            vu.update(cmd=cmd, **k)
            return subprocess.CompletedProcess(cmd, 0, stdout="100.101.102.103\nfd7a::1\n", stderr="")
        self.assertEqual(acces.adresse_tailscale(executer=ok), "100.101.102.103")
        self.assertEqual(vu["cmd"], ["tailscale", "ip", "-4"])
        self.assertEqual(vu["timeout"], 5)

    def test_tailscale_hors_de_sa_plage_refusee(self):
        # 0.0.0.0 ouvrirait un écouteur sur toutes les interfaces : seule la plage de Tailscale est acceptée
        for sortie in ("0.0.0.0\n", "192.168.1.5\n", "100.128.0.1\n"):
            rendu = lambda *a, s=sortie, **k: subprocess.CompletedProcess(a, 0, stdout=s, stderr="")
            self.assertIsNone(acces.adresse_tailscale(executer=rendu), sortie)

    def test_adresse_reseau_local_privee(self):
        for a in ("192.168.1.20", "10.0.0.5", "172.16.3.4", "172.31.255.1"):
            self.assertEqual(acces.adresse_reseau_local(fabrique=FausseSocket(a)), a)

    def test_adresse_reseau_local_publique_refusee(self):
        for a in ("8.8.8.8", "172.32.0.1", "127.0.0.1", "100.64.0.7", "169.254.1.1", "0.0.0.0"):
            self.assertIsNone(acces.adresse_reseau_local(fabrique=FausseSocket(a)), a)

    def test_adresse_reseau_local_sans_reseau(self):
        class Panne(FausseSocket):
            def connect(self, cible):
                raise OSError("réseau injoignable")
        self.assertIsNone(acces.adresse_reseau_local(fabrique=Panne("192.168.1.2")))


if __name__ == "__main__":
    unittest.main()
