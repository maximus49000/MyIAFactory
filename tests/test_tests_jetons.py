"""Places pondérées par la mémoire (tâche 14e) : les jetons de l'enveloppe (`lancer_tests.sh`, `~/taches/.jeton-tests-1..20`,
14e argument `budget_unites`), les limites par profil et le budget du serveur côté poste (`tests_serveur.limites_de`,
`budget_unites_de`, `serveur_modele.budget_tests_mo`), les paliers mixtes (`tests_mesure_places --mixte`).

L'enveloppe tourne avec le banc de `test_serveur_tests_enveloppe` : bash du poste, faux `docker`, `sudo`, `timeout`, `df`,
`flock` (un verrou par fichier `<fichier>.tenu`, libre si le processus qui le tient n'existe plus), HOME temporaire."""
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import serveur_modele  # noqa: E402
import tests_mesure_places as mp  # noqa: E402
import tests_profil  # noqa: E402
import tests_serveur  # noqa: E402
from tests import test_serveur_tests_enveloppe as E  # noqa: E402
from tests import test_tests_serveur as TS  # noqa: E402

# Le banc de l'enveloppe, emprunté tel quel (sans hériter de ses tests).
_BANC = ("setUpClass", "tearDownClass", "setUp", "deposer", "etat", "demarrer", "ecrire", "finir", "lancer", "attendre",
         "lire_err", "journal", "arbre", "verrous", "verifier_fin")
RAPIDE = {"ENVELOPPE_SONDE_S": "0.1"}
ID_A, ID_B = E.ID, E.ID_B       # ID_A : celui que `setUp` du banc dépose déjà
SUITE_ARGS = ("2", "4", "8192", "1800", "projet-a", "-")


@unittest.skipUnless(E.shutil.which("bash"), "bash absent")
class TestJetons(unittest.TestCase):
    locals().update({nom: E.TestEnveloppeTests.__dict__[nom] for nom in _BANC})

    def jetons(self):
        """Les jetons tenus par un processus VIVANT (le faux `flock` laisse le fichier d'un processus tué net : le vrai verrou
        meurt avec lui)."""
        taches = self.home / "taches"
        fichiers = {}
        for p in taches.glob(".jeton-tests-*.tenu") if taches.exists() else ():
            try:
                pid = p.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if pid.isdigit():
                fichiers[p.name] = pid
        if not fichiers:
            return []
        r = subprocess.run(["bash", "-c", 'for p in "$@"; do kill -0 "$p" 2>/dev/null && echo "$p"; done', "x",
                            *sorted(set(fichiers.values()))], capture_output=True, text=True)
        vivants = set(r.stdout.split())
        return sorted(n for n, pid in fichiers.items() if pid in vivants)

    vivants = jetons

    def tenir(self, numeros):
        """Un processus qui tient ces jetons (verrou comme celui de l'enveloppe) jusqu'à la fermeture de son entrée."""
        (self.home / "taches").mkdir(exist_ok=True)
        corps = "".join(f'exec {{f}}>> "$HOME/taches/.jeton-tests-{k}"; flock -n "$f" || exit 1; ' for k in numeros)
        p = subprocess.Popen(["bash", "-c", corps + "echo pret; read x"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             env=self.env)
        self.assertEqual(p.stdout.readline().strip(), b"pret")
        self.addCleanup(self.lacher, p)
        return p

    def jetons_stables(self, attendus, delai=30):
        """Attend que le nombre de jetons tenus ait pour PLANCHER `attendus` sur huit relevés rapprochés : le faux `flock`
        laisse un fichier le temps d'un essai (l'enveloppe essaie les jetons libres avant de choisir) et le nombre monte alors
        au-dessus ; le plancher est ce qui reste tenu. Le vrai verrou n'a pas de trace."""
        fin = time.time() + delai
        while time.time() < fin:
            releves = []
            for _ in range(8):
                releves.append(len(self.jetons()))
                time.sleep(0.05)
            if min(releves) == attendus:
                return
            time.sleep(0.1)
        self.fail(f"{len(self.jetons())} jetons tenus au lieu de {attendus}")

    @staticmethod
    def lacher(p):
        for f in (p.stdin, p.stdout):
            try:
                f.close()
            except OSError:
                pass
        p.wait(timeout=10)

    def lance(self, memoire, *plus, ident=ID_A, env=None, places="2"):
        """Une enveloppe de poids donné ; `plus` = les arguments facultatifs (8e à 14e), à partir du 8e."""
        return self.demarrer(places, "4", str(memoire), "1800", "projet-a", "-", *plus, ident=ident,
                             env=dict(RAPIDE, **(env or {})))

    def run_ecrit(self, lancement, ident):
        return (lancement.etat / f"run-tests-{ident}.txt").exists()

    # ---------------------------------------------------------------- poids

    def test_poids(self):
        for i, (memoire, poids) in enumerate(((8192, 4), (10240, 5), (4096, 2), (6145, 4)), 20):
            ident_ = E.ident(i)
            self.deposer(ident_)
            with self.subTest(memoire=memoire):
                a = self.lance(memoire, ident=ident_, env={"FAUX_ATTENDRE": "1"})
                self.attendre(lambda: self.run_ecrit(a, ident_))
                self.assertEqual(len(self.jetons()), poids)
                a.p.stdin.close()
                code, _, err = self.finir(a, fermer_apres=False, delai=20)
                self.assertEqual(code, 130, err)
                self.verifier_fin(err, 130, refus=True, ident=ident_)

    def test_seul_le_premier_prend_des_jetons(self):
        externes = self.tenir(range(1, 13))                            # 12 sur 16 : il en reste 4
        a = self.lance(16384)                                          # 8 jetons : en prend 4 puis attend
        self.attendre(lambda: "#attente 1 1 0" in self.lire_err(a))
        self.jetons_stables(16)
        self.deposer(ID_B)
        b = self.lance(4096, ident=ID_B)                               # 2 jetons : second ticket, n'en tient aucun
        self.attendre(lambda: "#attente 2 2 0" in self.lire_err(b))
        self.jetons_stables(16)                                        # 12 + les 4 du premier, pas un de plus
        self.assertFalse((self.t / "ordre").exists())
        externes.stdin.close()
        externes.wait(timeout=10)
        code_a, _, err_a = self.finir(a)
        code_b, _, err_b = self.finir(b)
        self.assertEqual((code_a, code_b), (0, 0), err_a + err_b)
        self.assertEqual((self.t / "ordre").read_text(encoding="utf-8").split(), [f"tests-{ID_A}", f"tests-{ID_B}"])
        self.verifier_fin(err_a, 0, refus=False, ident=ID_A)
        self.verifier_fin(err_b, 0, refus=False, ident=ID_B)

    def test_budget_respecte(self):
        quatre = [self.tenir(range(1 + 4 * i, 5 + 4 * i)) for i in range(4)]     # 2 x 4 + 2 x 4 = 16 jetons
        a = self.lance(8192)                                                     # la cinquième
        self.attendre(lambda: "#attente 1 1 0" in self.lire_err(a))
        for _ in range(8):                                                       # jamais de départ tant que le budget est plein
            self.assertFalse(self.run_ecrit(a, ID_A))
            time.sleep(0.1)
        self.jetons_stables(16)                                                  # elle n'en a pas pris un de plus
        self.assertFalse([x for x in self.journal.splitlines() if x.startswith("docker run")])
        quatre[0].stdin.close()                                                  # une campagne finit : ses 4 jetons reviennent
        quatre[0].wait(timeout=10)
        code, _, err = self.finir(a)
        self.assertEqual(code, 0, err)
        self.assertEqual(len([x for x in self.journal.splitlines() if x.startswith("docker run")]), 1)
        for p in quatre[1:]:
            self.lacher(p)
        self.verifier_fin(err, 0, refus=False, ident=ID_A, efface=False)
        self.assertEqual(self.vivants(), [])                                     # tous les jetons sont rendus

    def test_budget_reglable_par_le_14e_argument(self):
        self.tenir(range(1, 7))                                        # 6 tenus, budget 8 : il en reste 2 pour un poids de 4
        a = self.lance(8192, "10", "myiafactory/tests", "python", "-", "refuse", "40", "8")
        self.attendre(lambda: "#attente 1 1 0" in self.lire_err(a))
        self.jetons_stables(8)                                         # 6 + 2 : jamais plus que 8
        self.assertFalse(self.run_ecrit(a, ID_A))
        a.p.stdin.close()
        code, _, err = self.finir(a, fermer_apres=False, delai=20)
        self.assertEqual(code, 130, err)
        self.jetons_stables(6)                                         # ceux des autres seulement

    def test_arguments_hors_motif_refuses_sans_effet(self):
        self.deposer(ID_B)
        (self.home / "tests" / ID_B / "travail").mkdir()
        avant = self.arbre()
        base = ("10", "myiafactory/tests", "python", "-", "refuse", "40")
        cas = [("8192",) + base + (b,) for b in ("3", "21", "08", "x", "", "4.0", "-5", "100")]
        cas.append(("20480",) + base + ("8",))                         # 10 jetons pour un budget de 8 : attendrait toujours
        lances = [(c, self.demarrer("2", "4", c[0], "1800", "projet-a", "-", *c[1:], ident=ident_, env=RAPIDE))
                  for c, ident_ in zip(cas, (E.ident(10 + i) for i in range(len(cas))))]
        for c, lancement in lances:
            with self.subTest(argument=c[-1], memoire=c[0]):
                code, _, err = self.finir(lancement)
                self.assertEqual(code, 2, err)
                self.verifier_fin(err, 2, refus=True, efface=False, ident=lancement.ident)
        self.assertEqual([x for x in self.arbre() if ID_B in x[0]], [x for x in avant if ID_B in x[0]])
        self.assertEqual(self.jetons(), [])
        self.assertNotIn("docker", self.journal)

    def test_jetons_rendus_a_la_fin_et_a_la_laisse(self):
        a = self.lance(8192)                                           # fin normale
        code, _, err = self.finir(a)
        self.assertEqual(code, 0, err)
        self.verifier_fin(err, 0, refus=False)
        self.assertEqual(self.jetons(), [])
        self.deposer(ID_B)
        b = self.lance(8192, ident=ID_B, env={"FAUX_ATTENDRE": "1"})   # laisse coupée en pleine campagne
        self.attendre(lambda: self.run_ecrit(b, ID_B))
        self.assertEqual(len(self.jetons()), 4)
        b.p.stdin.close()
        code, _, err = self.finir(b, fermer_apres=False, delai=20)
        self.assertEqual(code, 130, err)
        self.verifier_fin(err, 130, refus=True, ident=ID_B)
        self.assertEqual(self.jetons(), [])
        self.deposer(ID_A)
        externes = self.tenir(range(1, 15))                            # laisse coupée PENDANT l'attente de jetons : rendus aussi
        c = self.lance(8192)
        self.attendre(lambda: "#attente 1 1 0" in self.lire_err(c))
        self.jetons_stables(16)
        c.p.stdin.close()
        code, _, err = self.finir(c, fermer_apres=False, delai=20)
        self.assertEqual(code, 130, err)
        self.jetons_stables(14)                                        # les siens sont revenus, pas ceux des autres
        externes.stdin.close()

    def test_sans_argument_comme_t4(self):
        for args in (SUITE_ARGS, SUITE_ARGS + ("10",), SUITE_ARGS + ("10", "myiafactory/tests", "python")):
            with self.subTest(arguments=len(args)):
                self.deposer(ID_A) if not (self.home / "tests" / ID_A).exists() else None
                code, _, err = self.lancer(*args, env=RAPIDE)
                self.assertEqual(code, 0, err)
                self.verifier_fin(err, 0, refus=False)
                self.assertFalse([x for x in err if x.startswith("#attente")], err)        # libre : aucune attente
                self.assertEqual(self.jetons(), [])
        run = (self.t / "etat" / ID_A).glob(f"run-tests-{ID_A}.txt")
        texte = next(run).read_text(encoding="utf-8").split("\n")
        self.assertIn("8192m", texte)                                  # le conteneur d'avant, à l'identique

    # ---------------------------------------------------------------- côté poste

    def test_limites_bornees(self):
        profil = tests_profil.Profil(familles=("python",), ressources={"cpus": 4, "memoire_mo": 8192, "duree_s": 1800})
        self.assertEqual(tests_serveur.limites_de(profil), {"cpus": 4, "memoire_mo": 8192, "duree_s": 1800})
        gradle = tests_profil.Profil(familles=("gradle-jvm",), ressources=tests_profil.ressources_par_defaut("gradle-jvm"))
        self.assertEqual(tests_serveur.limites_de(gradle)["duree_s"], 2700)
        self.assertEqual(tests_serveur.limites_de(profil, {"memoire_mo": 16384, "cpus": 8, "duree_s": 3600}),
                         {"cpus": 8, "memoire_mo": 16384, "duree_s": 3600})
        for forces, mot in (({"memoire_mo": 20000}, "memoire_mo"), ({"cpus": 9}, "cpus"), ({"duree_s": 3601}, "duree_s")):
            with self.subTest(forces=forces), self.assertRaises(tests_serveur.Repli) as c:
                tests_serveur.limites_de(profil, forces)
            self.assertIn(mot, c.exception.raison)
            self.assertIn("décision du Directeur requise", c.exception.raison)
        trop = tests_profil.Profil(familles=("python",), ressources={"cpus": 4, "memoire_mo": 20000, "duree_s": 1800})
        with self.assertRaises(tests_serveur.Repli):
            tests_serveur.limites_de(trop)
        for invalide in (True, "9", 0, -1, None, 2.5):                  # jamais prises : les limites du profil restent
            self.assertEqual(tests_serveur.limites_de(profil, {"memoire_mo": invalide}), tests_serveur.LIMITES)
        self.assertEqual(tests_serveur.limites_de(tests_profil.Profil()), tests_serveur.LIMITES)

    def test_budget_du_serveur(self):
        self.assertEqual(serveur_modele.budget_tests_valide(8192), 8192)
        self.assertEqual(serveur_modele.budget_tests_valide(40960), 40960)
        for mauvais in (8191, 40961, True, "16384", None, 1.5):
            self.assertIsNone(serveur_modele.budget_tests_valide(mauvais))
        base = {"hote": "h.example", "utilisateur": "u", "cle": "k"}
        self.assertEqual(serveur_modele.valider({**base, "budget_tests_mo": 24576}).budget_tests_mo, 24576)
        hors = serveur_modele.valider({**base, "budget_tests_mo": 99999})
        self.assertIsNone(hors.budget_tests_mo)                                     # défaut, et la raison est dite
        self.assertIn("hors bornes", serveur_modele.raison_budget({**base, "budget_tests_mo": 99999}))
        self.assertIsNone(serveur_modele.raison_budget({**base, "budget_tests_mo": 8192}))
        self.assertIsNone(serveur_modele.raison_budget(base))
        self.assertNotIn("budget_tests_mo", serveur_modele._en_dict(hors))          # non réglé : absent du fichier
        self.assertEqual(serveur_modele._en_dict(serveur_modele.valider({**base, "budget_tests_mo": 8192}))["budget_tests_mo"],
                         8192)
        for mo, unites in ((None, 16), (8192, 4), (24576, 12), (32768, 16), (40960, 20), (8300, 4)):
            self.assertEqual(tests_serveur.budget_unites_de(SimpleNamespace(budget_tests_mo=mo)), unites)
        self.assertEqual(tests_serveur.budget_unites_de(SimpleNamespace()), 16)


class TestCommandeDistante(TS.Base):
    def ligne(self, serveur=None, **k):
        ssh = TS.FauxSsh()
        self.assertEqual(self.lancer(ssh, **k), 0)
        return ssh.appels_flux[0]["commande"]

    def test_budget_absent_ou_par_defaut_ne_change_pas_la_ligne(self):
        debut = f"\"{tests_serveur.ENVELOPPE_DISTANTE}\" {TS.ID} {tests_serveur.PLACES_DEFAUT} 4 8192 1800 projet-a -"
        self.assertEqual(self.ligne(), debut)
        pareil = SimpleNamespace(**vars(TS.SERVEUR), budget_tests_mo=32768)
        self.assertEqual(self.ligne(choisir=lambda d, requises: pareil), debut)

    def test_budget_du_serveur_est_le_14e_argument(self):
        serveur = SimpleNamespace(**vars(TS.SERVEUR), budget_tests_mo=24576)
        ligne = self.ligne(choisir=lambda d, requises: serveur)
        self.assertTrue(ligne.endswith(" projet-a - 10 myiafactory/tests python - refuse 40 12"), ligne)

    def test_limites_du_profil_dans_la_ligne(self):
        profil = tests_profil.Profil(familles=("python",), ressources={"cpus": 2, "memoire_mo": 10240, "duree_s": 2700})
        ligne = self.ligne(analyse=lambda racine, **o: profil, ressources_forcees=lambda racine: {})
        self.assertTrue(ligne.endswith(" 2 10240 2700 projet-a -"), ligne)
        ligne = self.ligne(analyse=lambda racine, **o: profil, ressources_forcees=lambda racine: {"memoire_mo": 12288})
        self.assertTrue(ligne.endswith(" 2 12288 2700 projet-a -"), ligne)

    def test_limites_hors_bornes_refusees_avant_toute_connexion(self):
        ssh = TS.FauxSsh()
        code = self.lancer(ssh, forcer=True, ressources_forcees=lambda racine: {"memoire_mo": 20000})
        self.assertEqual(code, 4)
        self.assertTrue(self.dit("décision du Directeur requise"))
        self.assertEqual((ssh.appels_octets, ssh.appels_flux), ([], []))
        self.assertEqual(self.poste.appels, [])


class TestPaliersMixtes(unittest.TestCase):
    def test_lire_mixte(self):
        self.assertEqual(mp.lire_mixte("gradle:2,python:2"), [("gradle", 2), ("python", 2)])
        self.assertEqual(mp.lire_mixte("python:1"), [("python", 1)])
        for mauvais in ("", "gradle", "gradle:0", "gradle:5", "gradle:2,python:3", "cobol:1", "gradle:x", "python:1,"):
            with self.subTest(mauvais=mauvais), self.assertRaises(ValueError):
                mp.lire_mixte(mauvais)

    def test_mesurer_mixte_lance_tout_en_meme_temps(self):
        vus = []
        mesures = mp.mesurer_mixte([("gradle", 2), ("python", 2)], lambda famille: vus.append(famille) or 0)
        self.assertEqual(sorted(vus), ["gradle", "gradle", "python", "python"])
        self.assertEqual({f: len(m["durees"]) for f, m in mesures.items()}, {"gradle": 2, "python": 2})
        self.assertEqual(mesures["gradle"]["codes"], [0, 0])


if __name__ == "__main__":
    unittest.main()
