"""Livrables d'un agent serveur rapatriés au poste (`outils/serveur_livrables.py`) : faux SSH qui exécute les scripts figés
avec le bash du poste sur un faux ~ (dossier jetable : ~/taches/<id>/travail/projet), vrai dépôt git jetable au poste ;
jamais un vrai serveur, jamais une vraie clé (les « clés » sont des octets factices)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_livrables as sl  # noqa: E402
import serveur_tache as st  # noqa: E402

ID = "t20261120-101500-aaaa"
D = "android_app/build/app/outputs/flutter-apk"
APK_REL = f"{D}/app-release.apk"
APK = b"PK\x03\x04" + bytes(range(256)) * 40 + b"\r\n\n\r\x00" * 10
JETON = "jeton-factice-de-test-0123456789abcdef"
BASH = shutil.which("bash")


def lien(test, cible, nom, dur=False, dossier=False):
    """Crée un lien ; le test est sauté si le système le refuse (Windows sans droit : WinError 1314)."""
    try:
        if dur:
            os.link(cible, nom)
        else:
            os.symlink(cible, nom, target_is_directory=dossier)
    except (OSError, NotImplementedError) as e:
        test.skipTest(f"liens refusés par le système : {e}")


class FauxSsh:
    """Exécute le script reçu sur l'entrée standard avec le bash du poste, HOME = le faux ~ du serveur. Garde chaque
    script et son délai ; `alterer` : change les octets d'un envoi (transfert abîmé)."""

    def __init__(self, maison):
        self.maison = maison
        self.scripts, self.delais = [], []
        self.alterer = None

    def _bash(self, entree, delai):
        script = entree.decode("utf-8")
        self.scripts.append(script)
        self.delais.append((script.split("\n", 1)[0], delai))
        env = {**os.environ, "HOME": str(self.maison), "LC_ALL": "C"}
        r = subprocess.run([BASH, "-s"], input=entree, capture_output=True, env=env, timeout=120)
        return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace")

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        assert commande == "bash -s"
        code, sortie, erreur = self._bash(stdin.encode("utf-8"), delai)
        return code, sortie.decode("utf-8", "replace"), erreur

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, runner=None):
        assert commande == "bash -s"
        code, sortie, erreur = self._bash(entree, delai)
        if self.alterer is not None and entree.startswith(b"# tache:livrables_envoi"):
            sortie = self.alterer(sortie)
        return code, sortie, erreur


def git(projet, *args):
    return subprocess.run(["git", "-C", str(projet), "-c", "user.name=T", "-c", "user.email=t@exemple.net", *args],
                          capture_output=True, text=True)


@unittest.skipUnless(BASH, "bash introuvable")
class Livrables(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = tmp = Path(self._tmp.name)
        self.dossier = tmp / "plateforme"
        self.dossier.mkdir()
        (self.dossier / "serveurs.json").write_text(json.dumps(
            [{"id": "ovh1", "nom": "ovh1", "hote": "ovh1.exemple.net", "utilisateur": "ubuntu",
              "cle": "C:/cles/factice-ovh1"}]), encoding="utf-8")
        st.Index(self.dossier).enregistrer(ID, {"type": "agent", "etat": "terminee", "serveur_id": "ovh1",
                                                "projet": "demo", "tache": "apk", "cree": "2026-11-20T10:15:00Z"})
        self.maison = tmp / "serveur"
        self.travail = self.maison / "taches" / ID / "travail" / "projet"
        self.travail.mkdir(parents=True)
        self.projet = tmp / "poste"
        self.projet.mkdir()
        subprocess.run(["git", "init", "-q", str(self.projet)], check=True)
        (self.projet / ".gitignore").write_text("/android_app/build/\n", encoding="utf-8")
        self.ssh = FauxSsh(self.maison)
        self.debut = time.time() - 60

    def serveur(self, rel, donnees):
        f = self.travail / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(donnees)
        return f

    def rapatrier(self, chemins, **plus):
        return sl.rapatrier(ID, self.projet, chemins, debut=plus.pop("debut", self.debut), dossier=self.dossier,
                            ssh=self.ssh, **plus)

    def un(self, resultats, chemin):
        return next(r for r in resultats if r["chemin"] == chemin)

    def assertRefus(self, resultat, morceau):
        self.assertEqual(resultat["statut"], "refuse", resultat)
        self.assertIn(morceau, resultat["raison"])

    def envois(self):
        return [s for s in self.ssh.scripts if s.startswith("# tache:livrables_envoi")]

    def test_apk_declare_revient_intact_et_la_ligne_le_dit(self):
        self.serveur(APK_REL, APK)
        r = self.rapatrier([APK_REL])
        self.assertEqual(r, [{"chemin": APK_REL, "statut": "rapatrie", "taille": len(APK),
                              "sha256": hashlib.sha256(APK).hexdigest()}])
        self.assertEqual((self.projet / APK_REL).read_bytes(), APK)
        self.assertEqual(sl.ligne(r[0]), f"Livrable rapatrié : {APK_REL} (10,1 Ko, "
                                         f"{hashlib.sha256(APK).hexdigest()[:16]})")
        restes = [p.name for p in (self.projet / APK_REL).parent.iterdir()]
        self.assertEqual(restes, ["app-release.apk"])               # aucun fichier temporaire laissé

    def test_declares_lit_les_fichiers_livrables_du_rapport(self):
        rapport = {"statut": "fait", "fichiers": [{"chemin": APK_REL, "titre": "APK", "livrable": True},
                                                  {"chemin": "notes.md", "titre": "n"},
                                                  {"chemin": APK_REL, "titre": "doublon", "livrable": True},
                                                  {"chemin": "x.zip", "titre": "x", "livrable": "oui"}]}
        self.assertEqual(sl.declares(rapport), [APK_REL])
        self.assertEqual(sl.declares({"fichiers": "rien"}), [])

    def test_chemins_suspects_refuses_sans_rien_demander_au_serveur(self):
        cas = {"../dehors.apk": "..", "android_app/../../x.apk": "..", "/etc/x.apk": "absolu",
               "C:/x.apk": "lecteur", "~/x.apk": "absolu", f"{D}/app.so": "extension",
               f"{D}/a b.apk": "caractères", "con/build/outputs/apk/x.apk": "réservé", "": "vide"}
        r = self.rapatrier(list(cas))
        for chemin, morceau in cas.items():
            self.assertRefus(self.un(r, chemin), morceau)
        self.assertEqual(self.ssh.scripts, [])

    def test_seuls_apk_aab_zip_et_seulement_sous_un_dossier_de_sortie_android(self):
        refuses = {"node_modules/electron/dist/electron.exe": "extension", "tools/bin/x.exe": "extension",
                   "target/release/app.exe": "extension", "dist/app.zip": "dossier de sortie",
                   f"{D}/app.exe": "extension", f"{D}/app.msi": "extension", f"{D}/app.jar": "extension",
                   f"{D}/app.dmg": "extension", f"{D}/notes.pdf": "extension",
                   "node_modules/x/build/outputs/apk/a.apk": "exclu", "venv/build/outputs/apk/a.apk": "exclu",
                   "vendor/build/outputs/apk/a.apk": "exclu", "lib/site-packages/build/outputs/apk/a.apk": "exclu",
                   "android_app/build/app/outputs/flutter-apk/sous/a.apk": "dossier de sortie",
                   "android_app/build/app/apk/a.apk": "dossier de sortie"}
        r = self.rapatrier(list(refuses))
        for chemin, morceau in refuses.items():
            self.assertRefus(self.un(r, chemin), morceau)
        self.assertEqual(self.ssh.scripts, [])
        for bon in (APK_REL, "app/build/outputs/apk/app.apk", "build/outputs/bundle/app.aab", f"{D}/sources.zip"):
            self.assertEqual(sl.valider_chemin(bon), (bon, None))
        self.assertEqual(sl.EXTENSIONS, frozenset({".apk", ".aab", ".zip"}))

    def test_cles_et_maison_jamais_rapatriees_ni_demandees(self):
        exclus = [f"{D}/debug.keystore", f"{D}/upload.jks", f"{D}/cle.pem", f"{D}/id.key",
                  "maison/.android/debug.keystore", "maison/build/outputs/apk/app.apk",
                  "android-signature/build/outputs/apk/app.apk", ".android/build/outputs/apk/app.apk",
                  ".git/build/outputs/apk/x.zip", ".factory/build/outputs/apk/x.zip"]
        for rel in exclus:
            self.serveur(rel, b"CLE-FACTICE")
        r = self.rapatrier(exclus)
        self.assertTrue(all(x["statut"] == "refuse" for x in r))
        self.assertRefus(self.un(r, f"{D}/debug.keystore"), "clé")
        self.assertRefus(self.un(r, "maison/build/outputs/apk/app.apk"), "exclu")
        self.assertEqual(self.ssh.scripts, [])
        self.assertFalse(any(p.is_file() for p in self.projet.rglob("*") if ".git" not in p.parts
                             and p.name != ".gitignore"))

    def test_lien_sur_le_serveur_refuse(self):
        cle = self.maison / "android-signature" / "debug.keystore"
        cle.parent.mkdir(parents=True)
        cle.write_bytes(b"CLE-FACTICE")
        (self.travail / D).mkdir(parents=True)
        lien(self, cle, self.travail / D / "lien.apk")                                     # lien symbolique
        (self.maison / "ailleurs" / "build" / "outputs" / "apk").mkdir(parents=True)
        (self.maison / "ailleurs" / "build" / "outputs" / "apk" / "x.apk").write_bytes(b"X")
        lien(self, self.maison / "ailleurs", self.travail / "lie", dossier=True)           # dossier lié
        self.serveur(f"{D}/source.zip", b"Z")
        lien(self, self.travail / D / "source.zip", self.travail / D / "dur.zip", dur=True)   # lien dur
        chemins = [f"{D}/lien.apk", "lie/build/outputs/apk/x.apk", f"{D}/dur.zip"]
        r = self.rapatrier(chemins)
        for c in chemins:
            self.assertRefus(self.un(r, c), "lien")
        self.assertFalse((self.projet / D / "lien.apk").exists())

    def test_travail_lie_refuse(self):
        """`travail` (ou `travail/projet`) remplacé par un lien : rien n'est lu."""
        vrai = self.tmp / "autre"
        (vrai / "projet" / D).mkdir(parents=True)
        (vrai / "projet" / APK_REL).write_bytes(APK)
        shutil.rmtree(self.travail.parent)
        lien(self, vrai, self.travail.parent, dossier=True)
        r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "dossier de travail")
        self.assertEqual(self.envois(), [])

    def test_scripts_lisent_un_seul_descripteur(self):
        for script in (sl._MANIFESTE, sl._ENVOI):
            self.assertIn('exec 3<"$f"', script)
            self.assertIn("/proc/self/fd/3", script)
            self.assertIn("<&3", script)

    def test_trop_gros_et_total_depasse(self):
        self.serveur(f"{D}/gros.zip", b"x" * 2000)
        r = self.rapatrier([f"{D}/gros.zip"], max_octets=1000)
        self.assertRefus(r[0], "trop gros")
        for i in range(3):
            self.serveur(f"{D}/p{i}.zip", b"y" * 600)
        r = self.rapatrier([f"{D}/p{i}.zip" for i in range(3)], max_octets=1000, max_total=1300)
        self.assertEqual([x["statut"] for x in r], ["rapatrie", "rapatrie", "refuse"])
        self.assertRefus(r[2], "total")

    def test_neuf_fichiers_le_neuvieme_refuse(self):
        chemins = []
        for i in range(9):
            self.serveur(f"{D}/f{i}.zip", bytes([i]) * 10)
            chemins.append(f"{D}/f{i}.zip")
        r = self.rapatrier(chemins)
        self.assertEqual(sum(x["statut"] == "rapatrie" for x in r), 8)
        self.assertRefus(self.un(r, f"{D}/f8.zip"), "au plus 8")
        self.assertFalse((self.projet / D / "f8.zip").exists())

    def test_sha_qui_ne_correspond_pas_jete_et_dossiers_crees_retires(self):
        self.serveur(APK_REL, APK)
        self.ssh.alterer = lambda b: b[:-1] + bytes([b[-1] ^ 1])
        r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "SHA-256")
        self.assertFalse((self.projet / "android_app").exists())      # ni fichier, ni temporaire, ni dossiers créés

    def test_espace_disque_insuffisant_refuse_avant_d_ecrire(self):
        self.serveur(APK_REL, APK)
        with mock.patch.object(sl.shutil, "disk_usage", return_value=(10 ** 12, 10 ** 12, 1024 ** 3)):
            r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "espace")
        self.assertEqual(self.envois(), [])
        self.assertFalse((self.projet / "android_app").exists())

    def test_fichier_existant_plus_recent_garde_plus_ancien_remplace(self):
        self.serveur(APK_REL, APK)
        cible = self.projet / APK_REL
        cible.parent.mkdir(parents=True)
        cible.write_bytes(b"APK-LOCAL")
        r = self.rapatrier([APK_REL])                                # plus récent que la tâche : gardé
        self.assertRefus(r[0], "plus récent")
        self.assertEqual(cible.read_bytes(), b"APK-LOCAL")
        os.utime(cible, (self.debut - 3600, self.debut - 3600))      # plus ancien que la tâche : remplacé
        r = self.rapatrier([APK_REL])
        self.assertEqual(r[0]["statut"], "rapatrie")
        self.assertEqual(cible.read_bytes(), APK)
        self.assertRefus(self.rapatrier([APK_REL], debut=None)[0], "plus récent")   # date de la tâche inconnue

    def test_livrable_exclu_localement_jamais_commite(self):
        """Même si .gitignore ne l'ignore plus : le chemin est écrit dans .git/info/exclude (une fois) ; `git add -A`
        ne l'ajoute pas."""
        (self.projet / ".gitignore").write_text("", encoding="utf-8")
        self.serveur(APK_REL, APK)
        self.assertEqual(self.rapatrier([APK_REL])[0]["statut"], "rapatrie")
        os.utime(self.projet / APK_REL, (self.debut - 3600, self.debut - 3600))
        self.assertEqual(self.rapatrier([APK_REL])[0]["statut"], "rapatrie")
        exclude = (self.projet / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
        self.assertEqual(exclude.count(f"/{APK_REL}"), 1)
        git(self.projet, "add", "-A")
        self.assertNotIn("app-release.apk", git(self.projet, "diff", "--cached", "--name-only").stdout)

    def test_fichier_suivi_par_git_jamais_remplace(self):
        (self.projet / ".gitignore").write_text("", encoding="utf-8")
        self.serveur(APK_REL, APK)
        cible = self.projet / APK_REL
        cible.parent.mkdir(parents=True)
        cible.write_bytes(b"SUIVI")
        git(self.projet, "add", "-A")
        git(self.projet, "commit", "-q", "-m", "x")
        os.utime(cible, (self.debut - 3600, self.debut - 3600))
        self.assertRefus(self.rapatrier([APK_REL])[0], "suivi par git")
        self.assertEqual(cible.read_bytes(), b"SUIVI")

    def test_lien_dans_le_projet_du_poste_refuse(self):
        self.serveur(APK_REL, APK)
        ailleurs = self.tmp / "ailleurs"
        ailleurs.mkdir()
        lien(self, ailleurs, self.projet / "android_app", dossier=True)
        self.assertRefus(self.rapatrier([APK_REL])[0], "lien")
        self.assertEqual(list(ailleurs.iterdir()), [])

    def test_fichier_qui_contient_le_jeton_jamais_rapatrie(self):
        (self.maison / "agent-identifiants").mkdir()
        (self.maison / "agent-identifiants" / "jeton").write_text(JETON + "\n", encoding="utf-8")
        self.serveur(APK_REL, b"PK" + JETON.encode() + b"fin")
        self.serveur(f"{D}/propre.zip", b"PROPRE")
        r = self.rapatrier([APK_REL, f"{D}/propre.zip"])
        self.assertRefus(self.un(r, APK_REL), "secret")
        self.assertEqual(self.un(r, f"{D}/propre.zip")["statut"], "rapatrie")
        self.assertFalse((self.projet / APK_REL).exists())

    def test_absent_et_serveur_injoignable_dits(self):
        r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "absent")
        with mock.patch.object(self.ssh, "executer", side_effect=OSError("coupé")):
            self.serveur(APK_REL, APK)
            r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "manifeste impossible")
        self.assertIn("Livrable non rapatrié : " + APK_REL, sl.ligne(r[0]))

    def test_manifeste_menteur_ignore(self):
        """Un serveur qui annonce un chemin non demandé ou une ligne mal formée : rien n'en est tiré."""
        self.serveur(APK_REL, APK)
        faux = (f"ok 10 {'0' * 64} {D}/autre.apk\nok abc {'0' * 64} {APK_REL}\n")
        with mock.patch.object(st, "_bash", return_value=(0, faux, "")):
            r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "invalide")
        self.assertFalse((self.projet / D / "autre.apk").exists())

    def test_chemin_brut_sans_caractere_de_controle_au_journal(self):
        r = self.rapatrier(["a\nb\r\x1b[31m.apk"])
        texte = sl.ligne(r[0])
        self.assertFalse(any(ord(c) < 32 or ord(c) == 127 for c in texte), repr(texte))

    def test_delais_proportionnels_et_manifeste_court(self):
        self.serveur(APK_REL, APK)
        self.rapatrier([APK_REL])
        delais = dict(self.ssh.delais)
        self.assertLessEqual(delais[f"# tache:livrables_manifeste {ID}"], 180)
        self.assertEqual(delais[f"# tache:livrables_envoi {ID}"], 60)          # 10 Ko : 0 s + 60 s
        self.assertEqual(sl._delai_envoi(300 * 1024 * 1024), 360)
        self.assertEqual(sl._delai_envoi(10 * 1024 ** 3), 1800)

    def test_arret_demande_avant_un_fichier(self):
        self.serveur(APK_REL, APK)
        self.serveur(f"{D}/b.zip", b"B")
        r = self.rapatrier([APK_REL, f"{D}/b.zip"], arret=lambda: True)
        self.assertTrue(all(x["statut"] == "refuse" and "arrêt demandé" in x["raison"] for x in r), r)
        self.assertEqual(self.envois(), [])

    def test_arret_demande_pendant_un_transfert_coupe(self):
        self.serveur(APK_REL, APK)
        demande = threading.Event()

        def vers(hote, commande, cle, destination, maximum, entree=None, delai=60, popen=subprocess.Popen):
            p = popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            threading.Timer(0.3, demande.set).start()
            p.communicate(timeout=50)
            return p.returncode, 0, ""
        self.ssh.executer_vers_fichier = vers
        debut = time.monotonic()
        r = self.rapatrier([APK_REL], arret=demande.is_set)
        self.assertLess(time.monotonic() - debut, 20)
        self.assertRefus(r[0], "arrêt demandé")
        self.assertFalse((self.projet / "android_app").exists())


if __name__ == "__main__":
    unittest.main()
