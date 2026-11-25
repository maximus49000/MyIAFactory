"""Script hôte du service permanent (`serveur_ovh/services/service.py`).

Le script est importé tel quel et conduit par un FAUX hôte (`FauxHote`) : un faux `docker` (conteneurs, images, journaux)
et un faux `ufw` (règles) tenus en mémoire, une fausse sonde HTTP. Aucun vrai conteneur, aucun pare-feu, aucun serveur.
Le dossier `~/services` est un dossier jetable (`racine`)."""
import importlib.util
import io
import json
import os
import re
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "serveur_ovh" / "services" / "service.py"
COMMIT = "a" * 40
COMMIT_B = "b" * 40
SECRET = "valeur-du-secret-tres-privee-42"


def charger():
    spec = importlib.util.spec_from_file_location("service_hote", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = charger()

DECLARATION = {"nom": "donnees-fm", "dockerfile": "serveur/Dockerfile", "port_interne": 8080, "sante": "/sante",
               "donnees": "/data", "variables": ["NIVEAU_JOURNAL"], "secrets": ["CLE_API"]}


class FauxHote:
    """Faux docker/ufw/sudo. `sante_ok(image)` : la nouvelle image répond-elle à /sante ? `protege(image)` : exige-t-elle
    le jeton (401 sans) ? Chaque appel est noté dans `appels`."""

    def __init__(self):
        self.appels = []
        self.conteneurs = {}      # nom -> {"image", "en_marche", "argv"}
        self.images = set()
        self.regles = []          # "18000/tcp"
        self.journaux = {}        # nom -> texte
        self.images_malades = set()
        self.images_ouvertes = set()
        self.echec_construction = False

    def lancer(self, argv, delai=60, entree=None):
        self.appels.append(list(argv))
        assert argv[:2] == ["sudo", "-n"], argv
        outil, args = argv[2], argv[3:]
        if outil == "ufw":
            if args[:1] == ["allow"]:
                if args[1] not in self.regles:
                    self.regles.append(args[1])
                return 0, "Rule added", ""
            if args[:2] == ["delete", "allow"]:
                if args[2] in self.regles:
                    self.regles.remove(args[2])
                return 0, "Rule deleted", ""
            return 2, "", "ufw inconnu"
        assert outil == "docker", argv
        verbe = args[0]
        nom = args[-1]
        if verbe == "build":
            if self.echec_construction:
                return 1, "", "build échoué"
            self.images.add(args[args.index("-t") + 1])
            return 0, "", ""
        if verbe == "pull":
            self.images.add(nom)
            return 0, "", ""
        if verbe == "tag":
            self.images.add(args[2])
            return 0, "", ""
        if verbe == "inspect":
            if nom not in self.conteneurs:
                return 1, "", "Error: No such object: " + nom
            c = self.conteneurs[nom]
            return 0, ("true" if c["en_marche"] else "false") + " " + c["image"], ""
        if verbe == "run":
            n = args[args.index("--name") + 1]
            if n in self.conteneurs:
                return 125, "", "Conflict"
            self.conteneurs[n] = {"image": args[-1], "en_marche": True, "argv": list(args)}
            return 0, "abc123", ""
        if verbe == "rename":
            self.conteneurs[args[2]] = self.conteneurs.pop(args[1])
            return 0, "", ""
        if verbe == "stop":
            if nom in self.conteneurs:
                self.conteneurs[nom]["en_marche"] = False
            return 0, "", ""
        if verbe in ("start", "restart"):
            if nom not in self.conteneurs:
                return 1, "", "No such container"
            self.conteneurs[nom]["en_marche"] = True
            return 0, "", ""
        if verbe == "rm":
            self.conteneurs.pop(nom, None)
            return 0, "", ""
        if verbe == "rmi":
            self.images.discard(nom)
            return 0, "", ""
        if verbe == "logs":
            return 0, self.journaux.get(nom, ""), ""
        return 0, "", ""

    def http(self, url, jeton=None, delai=3):
        port = int(re.search(r":(\d+)/", url).group(1))
        actif = [c for c in self.conteneurs.values() if c["en_marche"] and f"{port}:" in " ".join(c["argv"])]
        if not actif:
            return None
        image = actif[0]["image"]
        if url.endswith("/sante"):
            return 503 if image in self.images_malades else 200
        if image in self.images_ouvertes:
            return 200
        return 200 if jeton else 401

    def dormir(self, _s):
        pass


def _tar(fichiers, liens=()):
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for nom, donnees in fichiers.items():
            info = tarfile.TarInfo(nom)
            info.size = len(donnees)
            tar.addfile(info, io.BytesIO(donnees))
        for nom, cible in liens:
            info = tarfile.TarInfo(nom)
            info.type, info.linkname = tarfile.SYMTYPE, cible
            tar.addfile(info)
    return tampon.getvalue()


def _sources(declaration=None):
    d = DECLARATION if declaration is None else declaration
    return _tar({".factory/service.json": json.dumps(d).encode(), "serveur/Dockerfile": b"FROM python:3.12-slim\n",
                 "serveur/app.py": b"print('ok')\n"})


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.racine = Path(self._t.name) / "services"
        self.hote = FauxHote()

    def tearDown(self):
        self._t.cleanup()

    def appeler(self, *argv, entree=b"", hote=None, uid=1000):
        sortie = io.StringIO()
        code = S.main(list(argv), entree=io.BytesIO(entree), sortie=sortie, hote=hote or self.hote, racine=self.racine,
                      uid=uid, gid=uid)
        texte = sortie.getvalue()
        lignes = [l for l in texte.splitlines() if l.strip()]
        self.assertEqual(len(lignes), 1, texte)          # UN SEUL objet JSON en sortie
        return code, json.loads(lignes[0]), texte

    def preparer(self, projet="fm-stats", commit=COMMIT, sources=None, secrets=None):
        code, rep, _ = self.appeler("recevoir", projet, commit, entree=sources or _sources())
        self.assertEqual(code, 0, rep)
        code, rep, _ = self.appeler("poser-secrets", projet,
                                    entree=json.dumps(secrets if secrets is not None else {"CLE_API": SECRET}).encode())
        self.assertEqual(code, 0, rep)
        return rep


class TestDeclaration(unittest.TestCase):
    def ok(self, **plus):
        d = dict(DECLARATION, **plus)
        return S.valider_declaration(json.dumps(d).encode())

    def refus(self, brut):
        with self.assertRaises(S.Refus):
            S.valider_declaration(brut if isinstance(brut, bytes) else json.dumps(brut).encode())

    def test_declaration_valide(self):
        d = self.ok()
        self.assertEqual(d["port_interne"], 8080)
        self.assertEqual(d["secrets"], ["CLE_API"])

    def test_image_epinglee_par_empreinte(self):
        d = dict(DECLARATION)
        del d["dockerfile"]
        d["image"] = "ghcr.io/exemple/service@sha256:" + "0" * 64
        self.assertEqual(S.valider_declaration(json.dumps(d).encode())["image"], d["image"])

    def test_motifs_hostiles_refuses(self):
        hostiles = [
            dict(DECLARATION, nom="../etc"), dict(DECLARATION, nom="A" * 5), dict(DECLARATION, nom="x" * 60),
            dict(DECLARATION, nom="a; rm -rf /"),
            dict(DECLARATION, dockerfile="../Dockerfile"), dict(DECLARATION, dockerfile="/etc/passwd"),
            dict(DECLARATION, dockerfile="C:/x"), dict(DECLARATION, dockerfile="a\\b"),
            dict(DECLARATION, dockerfile=".git/hooks/x"), dict(DECLARATION, dockerfile="a/$(id)"),
            dict(DECLARATION, port_interne=80), dict(DECLARATION, port_interne=70000), dict(DECLARATION, port_interne="8080"),
            dict(DECLARATION, port_interne=True),
            dict(DECLARATION, sante="sante"), dict(DECLARATION, sante="/a b"), dict(DECLARATION, sante="/../x"),
            dict(DECLARATION, donnees="/"), dict(DECLARATION, donnees="/etc"),
            dict(DECLARATION, variables=["PATH"]), dict(DECLARATION, variables=["LD_PRELOAD"]),
            dict(DECLARATION, variables=["SERVICE_JETON"]), dict(DECLARATION, variables=["minuscule"]),
            dict(DECLARATION, variables=["A"] * 2), dict(DECLARATION, variables="NIVEAU"),
            dict(DECLARATION, variables=[f"V{i}" for i in range(40)]),
            dict(DECLARATION, secrets=["NIVEAU_JOURNAL"]),                 # même nom qu'une variable
            dict(DECLARATION, secrets=["MYIAFACTORY_X"]),
            dict(DECLARATION, privilegie=True),                            # clé inconnue
            dict(DECLARATION, image="ubuntu:latest"),                      # deux sources
            {k: v for k, v in DECLARATION.items() if k != "dockerfile"},   # aucune source
            ["liste"], "texte", None,
        ]
        image_flottante = dict(DECLARATION)
        del image_flottante["dockerfile"]
        image_flottante["image"] = "ubuntu:latest"
        hostiles.append(image_flottante)
        for d in hostiles:
            with self.subTest(d=d):
                self.refus(d)

    def test_json_douteux_refuse(self):
        self.refus(b'{"nom": "a", "nom": "b"}')                         # clé dupliquée
        self.refus(b"\xff\xfe{}")
        self.refus(b"{" * 5000)
        self.refus(b" " * (S.DECLARATION_MAX + 1))


class TestRecevoir(Base):
    def test_archive_piegee_refusee(self):
        for tar in (_tar({"../x": b"a"}), _tar({"/abs": b"a"}), _tar({"a": b"b"}, liens=[("lien", "/etc/passwd")]),
                    _tar({".factory/service.json": b"{}"}, liens=[(".factory/x", "../../..")]), b"pas une archive"):
            with self.subTest(tar=tar[:20]):
                code, rep, _ = self.appeler("recevoir", "fm-stats", COMMIT, entree=tar)
                self.assertEqual(code, 2, rep)
                self.assertFalse((self.racine / "fm-stats" / "sources" / COMMIT).exists())

    def test_arguments_hostiles(self):
        for argv in (["recevoir", "../x", COMMIT], ["recevoir", "fm-stats", "HEAD"], ["deployer", "fm stats", COMMIT],
                     ["etat", "-rf"], ["journal", "fm-stats", "--lignes", "5000"], ["inconnue", "fm-stats"]):
            with self.subTest(argv=argv):
                code, rep, _ = self.appeler(*argv)
                self.assertEqual(code, 2, rep)
        self.assertEqual(self.hote.appels, [])


class TestDeploiement(Base):
    def test_premier_deploiement_durci(self):
        self.preparer()
        code, rep, texte = self.appeler("deployer", "fm-stats", COMMIT)
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["statut"], "ok")
        port = rep["port"]
        self.assertTrue(S.PORT_MIN <= port <= S.PORT_MAX)
        c = self.hote.conteneurs["svc-fm-stats"]
        argv = c["argv"]
        joint = " ".join(argv)
        for attendu in ("--restart unless-stopped", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                        "--user 1000:1000", "--pids-limit", "--memory", "--memory-swap", "--cpus",
                        f"{port}:8080", "/data:rw", "--tmpfs /tmp"):
            self.assertIn(attendu, joint)
        self.assertNotIn("--privileged", joint)
        self.assertNotIn("docker.sock", joint)
        self.assertEqual(self.hote.regles, [f"{port}/tcp"])
        self.assertNotIn(SECRET, texte)
        etat = json.loads((self.racine / "fm-stats" / "etat.json").read_text("utf-8"))
        self.assertEqual(etat["commit"], COMMIT)
        self.assertEqual(etat["port"], port)
        self.assertNotIn(SECRET, json.dumps(etat))
        jeton = (self.racine / "fm-stats" / "jeton").read_text("utf-8").strip()
        self.assertGreaterEqual(len(jeton), 40)
        self.assertNotIn(jeton, texte)
        self.assertNotIn(jeton, json.dumps(etat))
        env = (self.racine / "fm-stats" / "env").read_text("utf-8")
        self.assertIn("CLE_API=" + SECRET, env)
        self.assertIn("SERVICE_JETON=" + jeton, env)
        self.assertNotIn(SECRET, " ".join(" ".join(a) for a in self.hote.appels))   # jamais en argument
        if os.name == "posix":
            for f in ("jeton", "env", "secrets.json"):
                self.assertEqual((self.racine / "fm-stats" / f).stat().st_mode & 0o777, 0o600)

    def test_refus_sous_root(self):
        self.preparer()
        code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT, uid=0)
        self.assertEqual(code, 2, rep)
        self.assertNotIn("svc-fm-stats", self.hote.conteneurs)

    def test_secret_absent_refuse_avant_tout(self):
        self.preparer(secrets={})
        code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT)
        self.assertEqual(code, 2, rep)
        self.assertIn("CLE_API", rep["detail"])
        self.assertEqual(self.hote.appels, [])

    def test_secret_non_declare_refuse(self):
        self.appeler("recevoir", "fm-stats", COMMIT, entree=_sources())
        code, rep, _ = self.appeler("poser-secrets", "fm-stats", entree=json.dumps({"x y": "1"}).encode())
        self.assertEqual(code, 2, rep)
        code, rep, _ = self.appeler("poser-secrets", "fm-stats", entree=json.dumps({"CLE_API": "a\nb"}).encode())
        self.assertEqual(code, 2, rep)
        self.assertNotIn("a\nb", json.dumps(rep))

    def test_poser_secrets_ne_rend_que_les_noms(self):
        rep = self.preparer()
        self.assertEqual(rep["secrets"], ["CLE_API"])
        self.assertNotIn(SECRET, json.dumps(rep))

    def test_retour_arriere_si_sante_echoue(self):
        self.preparer()
        self.assertEqual(self.appeler("deployer", "fm-stats", COMMIT)[0], 0)
        ancienne = self.hote.conteneurs["svc-fm-stats"]["image"]
        regles = list(self.hote.regles)
        self.appeler("recevoir", "fm-stats", COMMIT_B, entree=_sources())
        nouvelle = S.nom_image("fm-stats", COMMIT_B)
        self.hote.images_malades.add(nouvelle)
        code, rep, texte = self.appeler("deployer", "fm-stats", COMMIT_B)
        self.assertEqual(code, 1, rep)
        self.assertEqual(rep["statut"], "retour_arriere")
        self.assertEqual(self.hote.conteneurs["svc-fm-stats"]["image"], ancienne)
        self.assertTrue(self.hote.conteneurs["svc-fm-stats"]["en_marche"])
        self.assertNotIn("svc-fm-stats-ancien", self.hote.conteneurs)
        self.assertEqual(self.hote.regles, regles)
        etat = json.loads((self.racine / "fm-stats" / "etat.json").read_text("utf-8"))
        self.assertEqual(etat["commit"], COMMIT)
        self.assertEqual(etat["dernier_deploiement"]["statut"], "retour_arriere")
        self.assertEqual(etat["dernier_deploiement"]["commit"], COMMIT_B)

    def test_retour_arriere_si_le_jeton_n_est_pas_exige(self):
        self.preparer()
        self.appeler("deployer", "fm-stats", COMMIT)
        self.appeler("recevoir", "fm-stats", COMMIT_B, entree=_sources())
        self.hote.images_ouvertes.add(S.nom_image("fm-stats", COMMIT_B))
        code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT_B)
        self.assertEqual(code, 1, rep)
        self.assertEqual(rep["statut"], "retour_arriere")
        self.assertIn("jeton", rep["detail"])

    def test_premier_deploiement_malade_n_ouvre_rien(self):
        self.preparer()
        self.hote.images_malades.add(S.nom_image("fm-stats", COMMIT))
        code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT)
        self.assertEqual(code, 1, rep)
        self.assertEqual(rep["statut"], "echec")
        self.assertEqual(self.hote.regles, [])
        self.assertNotIn("svc-fm-stats", self.hote.conteneurs)

    def test_construction_echouee_ne_touche_pas_l_ancien(self):
        self.preparer()
        self.appeler("deployer", "fm-stats", COMMIT)
        self.appeler("recevoir", "fm-stats", COMMIT_B, entree=_sources())
        self.hote.echec_construction = True
        code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT_B)
        self.assertEqual(code, 1, rep)
        self.assertTrue(self.hote.conteneurs["svc-fm-stats"]["en_marche"])

    def test_idempotent(self):
        self.preparer()
        _, r1, _ = self.appeler("deployer", "fm-stats", COMMIT)
        _, r2, _ = self.appeler("deployer", "fm-stats", COMMIT)
        self.assertEqual(r1["port"], r2["port"])
        self.assertEqual(len(self.hote.regles), 1)
        self.assertEqual(list(self.hote.conteneurs), ["svc-fm-stats"])

    def test_reprise_apres_un_deploiement_interrompu(self):
        """Un `-ancien` laissé seul (coupure au milieu de la bascule) redevient le service avant tout."""
        self.preparer()
        self.appeler("deployer", "fm-stats", COMMIT)
        self.hote.conteneurs["svc-fm-stats-ancien"] = self.hote.conteneurs.pop("svc-fm-stats")
        self.hote.conteneurs["svc-fm-stats-ancien"]["en_marche"] = False
        self.appeler("recevoir", "fm-stats", COMMIT_B, entree=_sources())
        self.hote.images_malades.add(S.nom_image("fm-stats", COMMIT_B))
        code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT_B)
        self.assertEqual(rep["statut"], "retour_arriere")
        self.assertEqual(self.hote.conteneurs["svc-fm-stats"]["image"], S.nom_image("fm-stats", COMMIT))
        self.assertTrue(self.hote.conteneurs["svc-fm-stats"]["en_marche"])

    def test_un_seul_deploiement_a_la_fois(self):
        self.preparer()
        with S.Verrou(self.racine / "fm-stats" / ".deploiement"):
            code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT)
        self.assertEqual(code, 75, rep)
        self.assertEqual(rep["statut"], "occupe")
        self.assertEqual(self.hote.appels, [])

    def test_sources_absentes(self):
        code, rep, _ = self.appeler("deployer", "fm-stats", COMMIT)
        self.assertEqual(code, 2, rep)

    def test_simulation_n_execute_rien_et_n_ecrit_rien(self):
        self.preparer()
        avant = sorted(p.name for p in (self.racine / "fm-stats").iterdir())
        code, rep, texte = self.appeler("deployer", "fm-stats", COMMIT, "--simuler")
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["statut"], "simule")
        self.assertEqual(self.hote.appels, [])
        self.assertTrue(any(c[:3] == ["sudo", "-n", "docker"] and "run" in c for c in rep["commandes"]))
        self.assertNotIn(SECRET, texte)
        self.assertEqual(sorted(p.name for p in (self.racine / "fm-stats").iterdir()), avant)

    def test_ports_distincts_et_plage_pleine(self):
        self.preparer("projet-a")
        self.preparer("projet-b")
        _, a, _ = self.appeler("deployer", "projet-a", COMMIT)
        _, b, _ = self.appeler("deployer", "projet-b", COMMIT)
        self.assertNotEqual(a["port"], b["port"])
        ports = {f"p{i}": S.PORT_MIN + i for i in range(S.PORT_MAX - S.PORT_MIN + 1)}
        (self.racine / "ports.json").write_text(json.dumps(ports), "utf-8")
        self.preparer("projet-c")
        code, rep, _ = self.appeler("deployer", "projet-c", COMMIT)
        self.assertEqual(code, 1, rep)
        self.assertIn("plage", rep["detail"])

    def test_variables_passees_et_validees(self):
        self.preparer()
        code, rep, _ = self.appeler("poser-variables", "fm-stats", entree=b'{"NIVEAU_JOURNAL": "info"}')
        self.assertEqual(code, 0, rep)
        self.appeler("deployer", "fm-stats", COMMIT)
        self.assertIn("NIVEAU_JOURNAL=info", (self.racine / "fm-stats" / "env").read_text("utf-8"))


class TestGestion(Base):
    def setUp(self):
        super().setUp()
        self.preparer()
        _, rep, _ = self.appeler("deployer", "fm-stats", COMMIT)
        self.port = rep["port"]
        self.jeton = (self.racine / "fm-stats" / "jeton").read_text("utf-8").strip()

    def test_la_presence_d_un_secret_se_dit_avant_le_premier_deploiement(self):
        """Essai réel (2026-11-25) : la clé posée avant le déploiement restait « absente » au bureau."""
        code, rep, _ = self.appeler("poser-secrets", "jamais-deploye", entree=json.dumps({"CLE_API": SECRET}).encode())
        self.assertEqual(code, 0, rep)
        code, rep, texte = self.appeler("etat", "jamais-deploye")
        self.assertEqual((code, rep["etat"]), (0, "absent"))
        self.assertEqual(rep["secrets"], {"CLE_API": True})
        self.assertNotIn(SECRET, texte)

    def test_etat_sans_secret(self):
        code, rep, texte = self.appeler("etat", "fm-stats")
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["etat"], "actif")
        self.assertEqual(rep["port"], self.port)
        self.assertTrue(rep["sante_ok"])
        self.assertEqual(rep["secrets"], {"CLE_API": True})       # présence seule, jamais la valeur
        self.assertNotIn(self.jeton, texte)
        self.assertNotIn(SECRET, texte)

    def test_journal_masque_et_borne(self):
        lignes = [f"ligne {i}" for i in range(300)] + [f"connexion avec {SECRET}", f"Bearer {self.jeton}", "x" * 2000]
        self.hote.journaux["svc-fm-stats"] = "\n".join(lignes)
        code, rep, texte = self.appeler("journal", "fm-stats")
        self.assertEqual(code, 0, rep)
        self.assertNotIn(SECRET, texte)
        self.assertNotIn(self.jeton, texte)
        self.assertIn("***", texte)
        self.assertLessEqual(len(rep["lignes"]), 200)
        self.assertTrue(all(len(l) <= S.LIGNE_MAX for l in rep["lignes"]))
        logs = [a for a in self.hote.appels if "logs" in a][-1]
        self.assertIn("200", logs)

    def test_arreter_retire_la_seule_regle(self):
        self.hote.regles.append("22/tcp")
        code, rep, _ = self.appeler("arreter", "fm-stats")
        self.assertEqual(code, 0, rep)
        self.assertEqual(self.hote.regles, ["22/tcp"])
        self.assertFalse(self.hote.conteneurs["svc-fm-stats"]["en_marche"])
        _, rep, _ = self.appeler("etat", "fm-stats")
        self.assertEqual(rep["etat"], "arrete")

    def test_redemarrer_rouvre(self):
        self.appeler("arreter", "fm-stats")
        code, rep, _ = self.appeler("redemarrer", "fm-stats")
        self.assertEqual(code, 0, rep)
        self.assertTrue(self.hote.conteneurs["svc-fm-stats"]["en_marche"])
        self.assertEqual(self.hote.regles, [f"{self.port}/tcp"])

    def test_supprimer_garde_les_donnees_et_libere_le_port(self):
        donnees = self.racine / "fm-stats" / "data"
        (donnees / "base.db").write_bytes(b"x")
        code, rep, _ = self.appeler("supprimer", "fm-stats")
        self.assertEqual(code, 0, rep)
        self.assertNotIn("svc-fm-stats", self.hote.conteneurs)
        self.assertEqual(self.hote.regles, [])
        self.assertTrue((donnees / "base.db").exists())
        self.assertNotIn("fm-stats", json.loads((self.racine / "ports.json").read_text("utf-8")))
        self.assertFalse((self.racine / "fm-stats" / "jeton").exists())

    def test_jeton_seule_commande_qui_le_rend(self):
        code, rep, _ = self.appeler("jeton", "fm-stats")
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["jeton"], self.jeton)

    def test_mettre_a_jour_est_un_deploiement(self):
        self.appeler("recevoir", "fm-stats", COMMIT_B, entree=_sources())
        code, rep, _ = self.appeler("mettre-a-jour", "fm-stats", COMMIT_B)
        self.assertEqual(code, 0, rep)
        self.assertEqual(self.hote.conteneurs["svc-fm-stats"]["image"], S.nom_image("fm-stats", COMMIT_B))

    def test_jamais_de_regle_hors_plage(self):
        (self.racine / "ports.json").write_text(json.dumps({"fm-stats": 22}), "utf-8")
        code, rep, _ = self.appeler("arreter", "fm-stats")
        self.assertNotIn(["sudo", "-n", "ufw", "delete", "allow", "22/tcp"], self.hote.appels)


if __name__ == "__main__":
    unittest.main()
