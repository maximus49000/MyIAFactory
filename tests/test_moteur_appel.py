"""La couche d'appel du moteur : `claude -p` dépouillé, l'API Messages en option. Aucun appel réel."""
import json
import os
import unittest

from moteur import appel

CLE = "sk-test-123"


def sortie_claude(texte='{"ok": true}', session="s1", modeles=None, erreur=False):
    modeles = modeles or {"claude-haiku-5-5": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 100,
                                               "cacheCreationInputTokens": 7, "costUSD": 0.001}}
    return json.dumps({"type": "result", "is_error": erreur, "result": texte, "session_id": session,
                       "total_cost_usd": 0.001, "modelUsage": modeles}).encode()


SORTIE_OK = sortie_claude()


class Vu:
    """Un exécuteur `claude` qui garde ce qu'il a reçu."""

    def __init__(self, sortie=SORTIE_OK, code=0):
        self.sortie, self.code, self.appels = sortie, code, []

    def __call__(self, argv, entree, env, cwd, delai):
        consigne = None
        if "--system-prompt-file" in argv:
            with open(argv[argv.index("--system-prompt-file") + 1], encoding="utf-8") as f:
                consigne = f.read()
        if "--append-system-prompt-file" in argv:
            with open(argv[argv.index("--append-system-prompt-file") + 1], encoding="utf-8") as f:
                consigne = f.read()
        self.appels.append({"argv": argv, "entree": entree, "env": env, "cwd": cwd, "delai": delai,
                            "consigne": consigne})
        return self.code, self.sortie


class ClaudeP(unittest.TestCase):
    def test_claude_p_rend_texte_et_usage(self):
        r = appel.appeler("consigne", "dossier", "haiku", executer=lambda *a: (0, SORTIE_OK))
        self.assertEqual(r.texte, '{"ok": true}')
        self.assertEqual(r.usage, {"modele": "claude-haiku-5-5", "entree": 10, "sortie": 5, "cache_lecture": 100,
                                   "cache_ecriture": 7})
        self.assertEqual(r.usages, [r.usage])
        self.assertEqual(r.session, "s1")

    def test_consigne_et_dossier_passent_par_l_entree_pas_par_argv(self):
        vu = Vu()
        appel.appeler("CONSIGNE", "DOSSIER", "haiku", executer=vu)
        argv = " ".join(vu.appels[0]["argv"])
        self.assertNotIn("DOSSIER", argv)
        self.assertNotIn("CONSIGNE", argv)
        self.assertIn(b"DOSSIER", vu.appels[0]["entree"])
        self.assertEqual(vu.appels[0]["consigne"], "CONSIGNE")

    def test_commande_depouillee_sans_outils(self):
        vu = Vu()
        appel.appeler("c", "d", "sonnet", executer=vu)
        argv = vu.appels[0]["argv"]
        self.assertEqual(argv[1:2], ["-p"])
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
        for option in ("--system-prompt-file", "--strict-mcp-config", "--disable-slash-commands",
                       "--no-session-persistence"):
            self.assertIn(option, argv)

    def test_fichier_de_consigne_efface_apres_l_appel(self):
        vu = Vu()
        appel.appeler("c", "d", "haiku", executer=vu)
        argv = vu.appels[0]["argv"]
        self.assertFalse(os.path.exists(argv[argv.index("--system-prompt-file") + 1]))

    def test_jugement_dans_un_dossier_vide_par_defaut(self):
        vu = Vu()
        appel.appeler("c", "d", "haiku", executer=vu)
        cwd = vu.appels[0]["cwd"]
        self.assertIsNotNone(cwd)
        self.assertFalse(os.path.exists(cwd))   # un dossier temporaire, effacé après l'appel

    def test_outils_et_dossier_de_travail_d_un_agent(self):
        vu = Vu()
        appel.appeler("DEPART", "MATIERE", "sonnet", executer=vu, outils=["Read", "Edit", "Bash(py:*)"],
                      dossier_travail="C:/projet")
        a = vu.appels[0]
        argv = a["argv"]
        self.assertEqual(a["cwd"], "C:/projet")
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Edit,Bash")
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Read,Edit,Bash(py:*)")
        self.assertEqual(argv[argv.index("--permission-prompts") + 1], "none")
        self.assertIn("--append-system-prompt-file", argv)   # l'agent garde le prompt de Claude Code
        self.assertNotIn("--system-prompt-file", argv)
        self.assertNotIn("--no-session-persistence", argv)   # une session d'agent se reprend
        self.assertEqual(a["consigne"], "DEPART")
        self.assertIn(b"MATIERE", a["entree"])

    def test_jamais_de_contournement_des_autorisations(self):
        vu = Vu()
        appel.appeler("c", "d", "sonnet", executer=vu, outils=["Read"], dossier_travail=".")
        appel.appeler("c", "d", "haiku", executer=vu)
        for a in vu.appels:
            texte = " ".join(a["argv"]).lower()
            self.assertNotIn("dangerously", texte)
            self.assertNotIn("bypass", texte)

    def test_reprendre_une_session(self):
        vu = Vu()
        appel.appeler("c", "d", "sonnet", executer=vu, outils=["Read"], dossier_travail=".", reprendre="s-42")
        argv = vu.appels[0]["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], "s-42")

    def test_delai_transmis(self):
        vu = Vu()
        appel.appeler("c", "d", "haiku", executer=vu, delai_s=42)
        self.assertEqual(vu.appels[0]["delai"], 42)

    def test_cle_api_retiree_de_l_environnement_de_claude(self):
        vu = Vu()
        ancien = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = CLE
        try:
            appel.appeler("c", "d", "haiku", executer=vu)
        finally:
            if ancien is None:
                del os.environ["ANTHROPIC_API_KEY"]
            else:
                os.environ["ANTHROPIC_API_KEY"] = ancien
        self.assertNotIn("ANTHROPIC_API_KEY", vu.appels[0]["env"])   # claude -p reste sur l'abonnement

    def test_fable_refuse_avant_appel(self):
        for modele in ("fable", "Fable", "claude-fable-5-2"):
            with self.assertRaises(appel.ErreurAppel):
                appel.appeler("c", "d", modele, executer=lambda *a: self.fail("appelé"))
            with self.assertRaises(appel.ErreurAppel):
                appel.appeler("c", "d", modele, couche="api", executer=lambda *a: self.fail("appelé"))

    def test_modele_inconnu_refuse(self):
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "gpt", executer=lambda *a: self.fail("appelé"))

    def test_code_non_nul_leve(self):
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "haiku", executer=lambda *a: (1, b"boom"))

    def test_sortie_illisible_leve(self):
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "haiku", executer=lambda *a: (0, b"pas du json"))

    def test_erreur_signalee_leve_avec_son_usage(self):
        with self.assertRaises(appel.ErreurAppel) as e:
            appel.appeler("c", "d", "haiku", executer=lambda *a: (0, sortie_claude(texte="trop long", erreur=True)))
        self.assertEqual(e.exception.usages[0]["entree"], 10)   # l'appel raté a quand même coûté

    def test_delai_depasse_leve(self):
        def ex(*a):
            raise TimeoutError
        with self.assertRaises(appel.ErreurAppel) as e:
            appel.appeler("c", "d", "haiku", executer=ex)
        self.assertIn("délai", e.exception.raison)

    def test_plusieurs_modeles_le_principal_d_abord(self):
        modeles = {"claude-haiku-5-5": {"inputTokens": 50, "outputTokens": 2, "cacheReadInputTokens": 0,
                                        "cacheCreationInputTokens": 0},
                   "claude-sonnet-5-5": {"inputTokens": 3, "outputTokens": 400, "cacheReadInputTokens": 9000,
                                         "cacheCreationInputTokens": 2000}}
        r = appel.appeler("c", "d", "sonnet", executer=lambda *a: (0, sortie_claude(modeles=modeles)))
        self.assertEqual(r.usage["modele"], "claude-sonnet-5-5")
        self.assertEqual([u["modele"] for u in r.usages], ["claude-sonnet-5-5", "claude-haiku-5-5"])

    def test_trouver_claude_dans_le_path(self):
        self.assertEqual(appel.trouver_claude(which=lambda nom: "/bin/claude", environ={}), "/bin/claude")

    def test_trouver_claude_installe_par_l_application(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "Claude", "claude-code", "2.1.0", "abc", "claude.exe")
            os.makedirs(os.path.dirname(exe))
            open(exe, "wb").close()
            self.assertEqual(appel.trouver_claude(which=lambda nom: None, environ={"APPDATA": d}), exe)
            self.assertIsNone(appel.trouver_claude(which=lambda nom: None, environ={}))


def corps_api(texte='{"ok": true}'):
    return json.dumps({"id": "msg_1", "type": "message", "model": "claude-haiku-5-5", "stop_reason": "end_turn",
                       "content": [{"type": "text", "text": texte}],
                       "usage": {"input_tokens": 20, "output_tokens": 6, "cache_read_input_tokens": 0,
                                 "cache_creation_input_tokens": 0}}).encode()


class Api(unittest.TestCase):
    def setUp(self):
        self._ancien = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = CLE

    def tearDown(self):
        if self._ancien is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = self._ancien

    def test_api_rend_texte_et_usage_sans_cle_dans_les_erreurs(self):
        vu = {}

        def ex(url, corps, entetes):
            vu.update(url=url, corps=json.loads(corps), entetes=entetes)
            return 200, corps_api()
        r = appel.appeler("CONSIGNE", "DOSSIER", "haiku", couche="api", executer=ex)
        self.assertEqual(r.texte, '{"ok": true}')
        self.assertEqual(r.usage, {"modele": "claude-haiku-5-5", "entree": 20, "sortie": 6, "cache_lecture": 0,
                                   "cache_ecriture": 0})
        self.assertIsNone(r.session)
        self.assertEqual(vu["corps"]["model"], "claude-haiku-5-5")
        self.assertEqual(vu["corps"]["system"], "CONSIGNE")
        self.assertEqual(vu["corps"]["messages"], [{"role": "user", "content": "DOSSIER"}])
        self.assertEqual(vu["entetes"]["x-api-key"], CLE)
        self.assertTrue(vu["url"].startswith("https://api.anthropic.com/"))

        def refus(url, corps, entetes):
            return 401, json.dumps({"type": "error", "error": {"type": "authentication_error",
                                                               "message": "invalid x-api-key " + CLE}}).encode()
        with self.assertRaises(appel.ErreurAppel) as e:
            appel.appeler("c", "d", "haiku", couche="api", executer=refus)
        self.assertNotIn(CLE, e.exception.raison)
        self.assertNotIn(CLE, str(e.exception))
        self.assertIn("401", e.exception.raison)

    def test_api_modeles(self):
        for court, long in (("haiku", "claude-haiku-5-5"), ("sonnet", "claude-sonnet-5-5"),
                            ("opus", "claude-opus-5-5")):
            vu = {}

            def ex(url, corps, entetes):
                vu["modele"] = json.loads(corps)["model"]
                return 200, corps_api()
            appel.appeler("c", "d", court, couche="api", executer=ex)
            self.assertEqual(vu["modele"], long)

    def test_api_sans_cle_au_moment_de_l_appel_leve(self):
        del os.environ["ANTHROPIC_API_KEY"]
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "haiku", couche="api", executer=lambda *a: self.fail("appelé"))

    def test_api_refus_de_securite_leve(self):
        corps = json.loads(corps_api())
        corps["stop_reason"] = "refusal"
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "haiku", couche="api", executer=lambda *a: (200, json.dumps(corps).encode()))

    def test_couche_inconnue_refusee(self):
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "haiku", couche="autre", executer=lambda *a: self.fail("appelé"))


class ChoisirCouche(unittest.TestCase):
    def test_api_sans_cle_bascule_une_fois(self):
        self.assertEqual(appel.choisir_couche({"moteur": {"couche": "api"}}, {})[0], "claude")
        ligne = appel.choisir_couche({"moteur": {"couche": "api"}}, {})[1]
        self.assertIsNotNone(ligne)
        self.assertIn("ANTHROPIC_API_KEY", ligne)
        self.assertEqual(appel.choisir_couche({"moteur": {"couche": "api"}}, {"ANTHROPIC_API_KEY": "x"}), ("api", None))
        self.assertEqual(appel.choisir_couche({}, {"ANTHROPIC_API_KEY": "x"}), ("claude", None))
        self.assertEqual(appel.choisir_couche({"moteur": {"couche": "claude"}}, {}), ("claude", None))

    def test_cle_vide_comptee_absente(self):
        self.assertEqual(appel.choisir_couche({"moteur": {"couche": "api"}}, {"ANTHROPIC_API_KEY": " "})[0], "claude")

    def test_la_ligne_ne_contient_jamais_la_cle(self):
        ligne = appel.choisir_couche({"moteur": {"couche": "api"}}, {"ANTHROPIC_API_KEY": ""})[1]
        self.assertNotIn("sk-", ligne)


if __name__ == "__main__":
    unittest.main()
