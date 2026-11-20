"""L'exécuteur distant d'un agent (`moteur/executeur_serveur.py`) : la traduction de l'argv de `claude -p`, la liste blanche
`DRAPEAUX` (miroir de l'entrée du conteneur), le lancement, le rattachement, la reprise, l'arrêt et l'échéance. Faux
`serveur_agent` (fonctions remplacées), index réel dans un dossier jetable, sommeil et horloge injectés : jamais un vrai
serveur ni le vrai ~/MyIAFactory."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_agent as sa  # noqa: E402
import serveur_tache as st  # noqa: E402

from bureau import abonnement  # noqa: E402
from moteur import agents, appel, detache  # noqa: E402
from moteur import executeur_serveur as es  # noqa: E402
from orchestrateur import fiches  # noqa: E402

ENTREE_AGENT = RACINE / "serveur_ovh" / "images" / "agent" / "entree-agent.py"
ID1 = "t20261120-101500-aaaa"
ID2 = "t20261120-111500-bbbb"
BASE = "a" * 40
TETE = "b" * 40
SESSION = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
TACHE = "ajout-bouton"
OUTILS = list(fiches.OUTILS_PAR_DEFAUT)


def evenement():
    return {"type": "rate_limit_event", "rate_limit_info": {
        "status": "allowed", "rateLimitType": "five_hour", "utilization": 0.25, "resetsAt": 1794485400,
        "unifiedWindows": {"five_hour": {"utilization": 0.25, "resetsAt": 1794485400, "status": "allowed"},
                           "seven_day": {"utilization": 0.43, "resetsAt": 1794639600, "status": "allowed"}}}}


def resultat(texte="fini", session=SESSION):
    return {"type": "result", "subtype": "success", "is_error": False, "result": texte, "session_id": session,
            "total_cost_usd": 0.01,
            "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 100,
                                                 "cacheCreationInputTokens": 7}}}


def flux(*objets):
    return ("\n".join(json.dumps(o) for o in objets) + "\n").encode()


FLUX = flux({"type": "system"}, evenement(), resultat())


class FauxServeurAgent:
    """Remplace preparer_paquet, lancer_agent, recuperer (serveur_agent) et etat, arreter (serveur_tache)."""

    def __init__(self, dossier, etats=("terminee",), fin=None, flux_=FLUX, branche=None, statut="ok", raison=""):
        self.dossier = dossier
        self.etats = list(etats)
        self.fin = {"code": 0, "commits": 0, "branche": None, "base": BASE} if fin is None else fin
        self.flux = flux_
        self.branche = branche
        self.statut, self.raison = statut, raison
        self.lancements, self.recuperations, self.sondes, self.arrets, self.paquets = [], [], [], [], []
        self.ident = ID2

    def preparer_paquet(self, projet, git=None):
        self.paquets.append(projet)
        return b"PAQUET-GIT", "main", BASE

    def lancer_agent(self, demande, paquet, argv, consigne, message, apk=None, dossier=None, ssh=None,
                     attente_max_s=600, dormir=None, projet=None, git=None):
        self.lancements.append({"demande": demande, "paquet": paquet, "argv": argv, "consigne": consigne,
                                "message": message, "dossier": dossier, "projet": projet})
        st.Index(dossier).enregistrer(self.ident, {
            "type": "agent", "etat": "en_cours", "serveur_id": "ovh1", "mode": demande["mode"],
            "projet": demande["projet"], "tache": demande["tache"], "session": None, "branche": demande["branche"],
            "base": demande["base"], "reprend": demande.get("reprend"), "limites": demande["limites"]})
        return {"id": self.ident, "etat": "en_cours", "serveur_id": "ovh1"}

    def etat(self, ident, dossier=None, ssh=None):
        self.sondes.append(ident)
        e = self.etats.pop(0) if len(self.etats) > 1 else self.etats[0]
        if e == "inconnu":
            return {"id": ident, "etat": "inconnu", "raison": "Serveur injoignable ou délai dépassé : ssh"}
        lu = {"id": ident, "etat": e, "statut": self.statut if e in st.FINAUX else None, "raison": self.raison,
              "serveur_id": "ovh1"}
        st._noter(dossier, ident, {"etat": e, "statut": lu["statut"], "raison": self.raison})
        return lu

    def recuperer(self, ident, projet, dossier=None, ssh=None, git=None):
        self.recuperations.append((ident, projet))
        return {"flux": self.flux, "fin": dict(self.fin), "branche": self.branche, "etat": "terminee", "raison": ""}

    def arreter(self, ident, dossier=None, ssh=None, fin=False):
        self.arrets.append(ident)
        st._noter(dossier, ident, {"etat": "arretee"})
        return {"id": ident, "etat": "arretee", "raison": "Arrêt demandé (fichier arret)"}

    def remplacer(self, test):
        for module, nom in ((sa, "preparer_paquet"), (sa, "lancer_agent"), (sa, "recuperer"), (st, "etat"),
                            (st, "arreter")):
            p = mock.patch.object(module, nom, getattr(self, nom))
            p.start()
            test.addCleanup(p.stop)


def faux_git_sans_branche(projet, args, max_octets=None):
    return 1, b"", ""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.dossier = self.tmp / "plateforme"
        self.dossier.mkdir()
        self.projet = self.tmp / "projet"
        self.projet.mkdir()
        abonnement.DOSSIER = self.tmp / "commun"      # jamais le vrai dossier commun
        self.addCleanup(setattr, abonnement, "DOSSIER", None)
        self.sommes = []
        self.t = 1000.0

    def dormir(self, s):
        self.sommes.append(s)
        self.t += s

    def executeur(self, git=faux_git_sans_branche, **plus):
        return es.ExecuteurServeur(self.projet, TACHE, "seul", {"projet": "demo", **plus}, dossier=self.dossier,
                                   ssh=object(), dormir=self.dormir, pas_s=15, horloge=lambda: self.t, git=git)

    def faux(self, **kw):
        f = FauxServeurAgent(self.dossier, **kw)
        f.remplacer(self)
        return f


class Argv(unittest.TestCase):
    def test_argv_distant_traduit_et_refuse_l_inconnu(self):
        argv = appel._argv("C:/Users/x/claude.exe", "sonnet", "C:/Temp/moteur-1/consigne.md", OUTILS, None)
        distant, consigne = es.argv_distant(argv)
        self.assertEqual(distant[0], "claude")
        self.assertEqual(consigne, "C:/Temp/moteur-1/consigne.md")
        self.assertIn("/entree/consigne.md", distant)
        self.assertNotIn("C:/Temp/moteur-1/consigne.md", distant)
        self.assertEqual(distant[1:], [("/entree/consigne.md" if a == consigne else a) for a in argv[1:]])
        sans_outils = appel._argv("claude", "haiku", "/tmp/c.md", [], None)
        d2, c2 = es.argv_distant(sans_outils)
        self.assertEqual(c2, "/tmp/c.md")
        self.assertEqual(d2[d2.index("--system-prompt-file") + 1], "/entree/consigne.md")
        for mauvais in (argv + ["--dangerously-skip-permissions"], argv + ["bonjour"], argv + ["-p"],
                        argv + ["--resume", "pas-une-session"], argv + ["--add-dir", "C:/"],
                        [*argv[:6], "claude-x; rm -rf /", *argv[7:]], argv + ["--resume"],
                        argv + ["--settings", "{}"], [argv[0], "--model", "--verbose"]):
            with self.assertRaises(ValueError, msg=mauvais):
                es.argv_distant(mauvais)
        with self.assertRaises(ValueError):          # aucune consigne : rien à envoyer
            es.argv_distant(["claude", "-p", "--output-format", "stream-json"])

    def test_drapeaux_concordent_avec_appel_argv(self):
        vus = set()
        for modele in appel.MODELES:
            for outils in ([], OUTILS, ["Read", "Bash(git log:*)"]):
                for reprendre in (None, SESSION):
                    argv = appel._argv("C:/claude.exe", modele, "C:/t/consigne.md", outils, reprendre)
                    distant, _c = es.argv_distant(argv)       # aucune option produite par _argv n'est refusée
                    vus |= {a for a in distant[1:] if a.startswith("-")}
                    self.assertTrue({a for a in argv[1:] if a.startswith("-")} <= set(es.DRAPEAUX))
        self.assertEqual(vus, set(es.DRAPEAUX))                # et aucun drapeau inutile dans la liste blanche
        for identifiant in appel.MODELES_API.values():
            self.assertRegex(identifiant, "^(?:" + es.DRAPEAUX["--model"] + r")\Z")

    def test_drapeaux_concordent_avec_entree_agent(self):
        spec = importlib.util.spec_from_file_location("entree_agent_concordance", ENTREE_AGENT)
        ea = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ea)
        self.assertEqual(es.DRAPEAUX, ea.DRAPEAUX)
        self.assertEqual(list(es.DRAPEAUX), list(ea.DRAPEAUX))
        self.assertEqual(tuple(es.OBLIGATOIRES), tuple(ea.OBLIGATOIRES))
        # et ce que l'exécuteur produit passe la validation de l'entrée du conteneur
        for outils in ([], OUTILS):
            for reprendre in (None, SESSION):
                distant, _c = es.argv_distant(appel._argv("C:/claude.exe", "opus", "C:/t/c.md", outils, reprendre))
                self.assertEqual(ea.valider_argv(distant), distant[1:])


class Appel(Base):
    def test_appeler_avec_l_executeur_rend_rapport_et_usages(self):
        f = self.faux(branche=f"agent/{TACHE}",
                      fin={"code": 0, "commits": 2, "branche": f"agent/{TACHE}", "base": BASE},
                      etats=("en_cours", "terminee"))
        ex = self.executeur()
        self.assertTrue(ex.noter_abonnement)
        r = appel.appeler("La consigne.", "Le message.", "sonnet", executer=ex, outils=OUTILS,
                          dossier_travail=str(self.projet), delai_s=2400)
        self.assertIsInstance(r, appel.Reponse)
        self.assertEqual(r.texte, "fini")
        self.assertEqual(r.session, SESSION)
        self.assertEqual(r.usage["modele"], "claude-sonnet-5-5")
        self.assertEqual(r.usage["entree"], 10)
        self.assertEqual(r.abonnement["seven_day"]["pourcent"], 43.0)
        self.assertTrue(any((self.tmp / "commun").rglob("*")))      # abonnement.noter : dans le dossier jetable
        lance = f.lancements[0]
        self.assertEqual(lance["consigne"], "La consigne.".encode())
        self.assertEqual(lance["message"], "Le message.".encode())
        self.assertEqual(lance["argv"][0], "claude")
        self.assertIn("/entree/consigne.md", lance["argv"])
        self.assertEqual(lance["projet"], self.projet)
        d = lance["demande"]
        self.assertEqual((d["projet"], d["tache"], d["mode"], d["base"], d["branche"], d.get("reprend")),
                         ("demo", TACHE, "seul", BASE, "main", None))
        self.assertEqual(d["limites"]["duree_s"], 2400)
        self.assertEqual(d["modele"], "claude-sonnet-5-5")
        self.assertEqual(st.Index(self.dossier).lire()[ID2]["session"], SESSION)    # noté après lecture du flux
        self.assertEqual(ex.branche, f"agent/{TACHE}")
        self.assertEqual(ex.ident, ID2)
        self.assertEqual(f.recuperations, [(ID2, self.projet)])
        self.assertEqual(self.sommes, [15])

    def test_duree_jamais_au_dessus_du_defaut_et_egale_au_delai(self):
        f = self.faux()
        (self.tmp / "c.md").write_text("c", encoding="utf-8")
        argv = appel._argv("claude", "sonnet", str(self.tmp / "c.md"), OUTILS, None)
        self.executeur()(argv, b"m", {}, None, 300)
        self.assertEqual(f.lancements[0]["demande"]["limites"]["duree_s"], 300)
        f.ident = "t20261120-121500-dddd"
        self.executeur()(argv, b"m", {}, None, 99999)
        self.assertEqual(f.lancements[1]["demande"]["limites"]["duree_s"], sa.LIMITES_AGENT["duree_s"])

    def test_echec_rend_code_1_et_la_raison(self):
        self.faux(etats=("echouee",), statut="erreur", raison="Secret de l'abonnement trouvé : rien rapatrié.")
        (self.tmp / "c.md").write_text("c", encoding="utf-8")
        code, sortie = self.executeur()(appel._argv("claude", "sonnet", str(self.tmp / "c.md"), OUTILS, None), b"m",
                                        {}, None, 600)
        self.assertEqual(code, 1)
        self.assertIn("Secret de l'abonnement trouvé", sortie.decode("utf-8"))

    def test_refus_de_lancement_rend_code_1(self):
        f = self.faux()

        def refuser(*a, **k):
            raise st.RefusLancement("La branche agent/ajout-bouton existe déjà dans le projet.")
        f.lancer_agent = refuser
        with mock.patch.object(sa, "lancer_agent", refuser):
            with self.assertRaises(appel.ErreurAppel) as e:
                appel.appeler("c", "m", "sonnet", executer=self.executeur(), outils=OUTILS, delai_s=600)
        self.assertIn("existe déjà", e.exception.raison)

    def test_rattache_une_tache_en_cours_sans_relancer(self):
        f = self.faux(etats=("en_cours", "en_cours", "terminee"))
        st.Index(self.dossier).enregistrer(ID1, {"type": "agent", "etat": "en_cours", "serveur_id": "ovh1",
                                                 "mode": "seul", "projet": "demo", "tache": TACHE, "session": None,
                                                 "branche": "main", "base": BASE})
        st.Index(self.dossier).enregistrer("t20261120-090000-cccc", {"type": "agent", "etat": "en_cours",
                                                                     "projet": "autre", "tache": TACHE, "base": BASE})
        r = appel.appeler("c", "m", "sonnet", executer=self.executeur(), outils=OUTILS, delai_s=600)
        self.assertEqual(r.texte, "fini")
        self.assertEqual(f.lancements, [])
        self.assertEqual(f.paquets, [])
        self.assertEqual(f.recuperations, [(ID1, self.projet)])
        self.assertEqual(set(f.sondes), {ID1})
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["session"], SESSION)

    def test_reprise_retrouve_la_tache_par_la_session(self):
        f = self.faux()
        st.Index(self.dossier).enregistrer(ID1, {"type": "agent", "etat": "terminee", "serveur_id": "ovh1",
                                                 "mode": "seul", "projet": "demo", "tache": TACHE, "session": SESSION,
                                                 "branche": "dev", "base": BASE})
        appel.appeler("c", "m", "sonnet", executer=self.executeur(), outils=OUTILS, reprendre=SESSION, delai_s=600)
        d = f.lancements[0]["demande"]
        self.assertEqual(d["reprend"], ID1)
        self.assertEqual((d["base"], d["branche"]), (BASE, "dev"))      # sans branche locale : la base d'avant
        self.assertEqual(f.lancements[0]["argv"][-2:], ["--resume", SESSION])

        def git_avec_branche(projet, args, max_octets=None):
            if args[:1] == ["rev-parse"] and any(a.startswith(f"refs/heads/agent/{TACHE}") for a in args):
                return 0, (TETE + "\n").encode(), ""
            return 1, b"", ""
        f.ident = "t20261120-121500-dddd"
        appel.appeler("c", "m", "sonnet", executer=self.executeur(git=git_avec_branche), outils=OUTILS,
                      reprendre=SESSION, delai_s=600)
        d = f.lancements[1]["demande"]
        self.assertEqual((d["reprend"], d["base"]), (ID2, TETE))   # la dernière tâche de la session ; base = la branche rapatriée

    def test_reprise_d_une_session_inconnue_est_une_erreur(self):
        f = self.faux()
        with self.assertRaises(appel.ErreurAppel) as e:
            appel.appeler("c", "m", "sonnet", executer=self.executeur(), outils=OUTILS, reprendre=SESSION, delai_s=600)
        self.assertEqual(f.lancements, [])
        self.assertIn("session", e.exception.raison)

    def test_arret_donne_arret_utilisateur(self):
        f = self.faux(etats=("en_cours", "arretee"), raison="Arrêt demandé (fichier arret)")
        ex = self.executeur()
        r = agents.executer_agent("Départ.", "Matière.", agent={"cle": "dev1"}, modele="sonnet",
                                  dossier_projet=self.projet, executeur=ex)
        self.assertTrue(getattr(r, "arrete", False))
        self.assertIn(detache.ARRET, r.erreur)
        self.assertEqual(len(f.lancements), 1)                     # aucun second essai

    def test_arreter_relaie_serveur_tache(self):
        f = self.faux(etats=("en_cours",))
        ex = self.executeur()
        self.assertEqual(ex.arreter()["etat"], "inconnu")          # rien de lancé : rien à arrêter
        st.Index(self.dossier).enregistrer(ID1, {"type": "agent", "etat": "en_cours", "projet": "demo",
                                                 "tache": TACHE, "base": BASE})
        self.assertEqual(ex.arreter()["etat"], "arretee")          # la tâche active de (projet, tâche)
        self.assertEqual(f.arrets, [ID1])

    def test_echeance_donne_une_erreur_d_appel(self):
        f = self.faux(etats=("terminee",), statut="limite", branche=f"agent/{TACHE}",
                      fin={"code": 1, "commits": 1, "branche": f"agent/{TACHE}", "base": BASE, "echeance": True})
        ex = self.executeur()
        with self.assertRaises(appel.ErreurAppel) as e:
            appel.appeler("c", "m", "sonnet", executer=ex, outils=OUTILS, delai_s=600)
        self.assertEqual(e.exception.raison, es.ECHEANCE)
        self.assertEqual(es.ECHEANCE, "durée maximale de l'agent serveur atteinte")
        self.assertEqual(ex.branche, f"agent/{TACHE}")            # les commits rapatriés sont gardés
        self.assertFalse(appel.est_une_panne(e.exception.raison))
        # échéance du suivi (le serveur ne finit jamais) : arrêt demandé puis la même erreur
        f2 = self.faux(etats=("en_cours",))
        f2.ident = "t20261120-121500-dddd"
        with self.assertRaises(appel.ErreurAppel) as e:
            appel.appeler("c", "m", "sonnet", executer=self.executeur(), outils=OUTILS, delai_s=600)
        self.assertEqual(e.exception.raison, es.ECHEANCE)
        self.assertEqual(f2.arrets, ["t20261120-121500-dddd"])
        self.assertGreaterEqual(self.t - 1000.0, 600 + 120)
        self.assertEqual(f2.recuperations, [])

    def test_serveur_injoignable_pendant_le_suivi_continue_de_sonder(self):
        f = self.faux(etats=("inconnu", "en_cours", "inconnu", "inconnu", "terminee"))
        r = appel.appeler("c", "m", "sonnet", executer=self.executeur(), outils=OUTILS, delai_s=600)
        self.assertEqual(r.texte, "fini")
        self.assertEqual(len(f.sondes), 5)
        self.assertEqual(self.sommes, [15, 15, 15, 15])
        self.assertEqual(f.arrets, [])

    def test_env_du_poste_jamais_transmis(self):
        f = self.faux()
        consigne = self.tmp / "moteur-xyz" / "consigne.md"
        consigne.parent.mkdir()
        consigne.write_text("Consigne.", encoding="utf-8")
        argv = appel._argv("C:/Users/poste/AppData/claude.exe", "sonnet", str(consigne), OUTILS, None)
        env = {"ANTHROPIC_API_KEY": "sk-ant-SECRET-DU-POSTE", "PATH": "C:/chemin/du/poste",
               "CLAUDE_CODE_OAUTH_TOKEN": "JETON-DU-POSTE"}
        code, sortie = self.executeur()(argv, b"Message.", env, "C:/dossier/de/travail/du/poste", 600)
        self.assertEqual(code, 0)
        transmis = json.dumps({k: (v.decode("utf-8") if isinstance(v, bytes) else v)
                               for k, v in f.lancements[0].items() if k not in ("dossier", "projet")},
                              ensure_ascii=False, default=str)
        for interdit in ("SECRET-DU-POSTE", "JETON-DU-POSTE", "chemin/du/poste", "dossier/de/travail",
                         "AppData", str(consigne), "moteur-xyz"):
            self.assertNotIn(interdit, transmis)
        self.assertEqual(f.lancements[0]["consigne"], b"Consigne.")


if __name__ == "__main__":
    unittest.main()
