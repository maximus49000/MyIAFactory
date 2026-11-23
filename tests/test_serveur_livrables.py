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
import time
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_livrables as sl  # noqa: E402
import serveur_tache as st  # noqa: E402

ID = "t20261120-101500-aaaa"
APK_REL = "android_app/build/app/outputs/flutter-apk/app-release.apk"
APK = b"PK\x03\x04" + bytes(range(256)) * 40 + b"\r\n\n\r\x00" * 10
JETON = "jeton-factice-de-test-0123456789abcdef"
BASH = shutil.which("bash")


class FauxSsh:
    """Exécute le script reçu sur l'entrée standard avec le bash du poste, HOME = le faux ~ du serveur. Garde chaque
    script (on vérifie ce qui part au serveur) ; `alterer` : change les octets d'un envoi (transfert abîmé)."""

    def __init__(self, maison):
        self.maison = maison
        self.scripts = []
        self.alterer = None

    def _bash(self, entree):
        script = entree.decode("utf-8")
        self.scripts.append(script)
        env = {**os.environ, "HOME": str(self.maison), "LC_ALL": "C"}
        r = subprocess.run([BASH, "-s"], input=entree, capture_output=True, env=env, timeout=120)
        return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace")

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        assert commande == "bash -s"
        code, sortie, erreur = self._bash(stdin.encode("utf-8"))
        return code, sortie.decode("utf-8", "replace"), erreur

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, runner=None):
        assert commande == "bash -s"
        code, sortie, erreur = self._bash(entree)
        if self.alterer is not None and entree.startswith(b"# tache:livrables_envoi"):
            sortie = self.alterer(sortie)
        return code, sortie, erreur


@unittest.skipUnless(BASH, "bash introuvable")
class Livrables(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
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
        (self.projet / ".gitignore").write_text("/android_app/build/\n/sortie/\n", encoding="utf-8")
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
               "C:/x.apk": "lecteur", "~/x.apk": "absolu", "lib/app.so": "extension",
               "a b.apk": "caractères", "con/x.apk": "réservé", "": "vide"}
        r = self.rapatrier(list(cas))
        for chemin, morceau in cas.items():
            self.assertRefus(self.un(r, chemin), morceau)
        self.assertEqual(self.ssh.scripts, [])

    def test_cles_et_maison_jamais_rapatriees_ni_demandees(self):
        for rel in ("debug.keystore", "upload.jks", "cle.pem", "id.key", "maison/.android/debug.keystore",
                    "maison/app.apk", "android-signature/app.apk", ".android/app.apk", ".git/x.zip"):
            self.serveur(rel, b"CLE-FACTICE")
        exclus = ["debug.keystore", "upload.jks", "cle.pem", "id.key", "maison/.android/debug.keystore",
                  "maison/app.apk", "android-signature/app.apk", ".android/app.apk", ".git/x.zip"]
        r = self.rapatrier(exclus)
        self.assertTrue(all(x["statut"] == "refuse" for x in r))
        self.assertRefus(self.un(r, "debug.keystore"), "clé")
        self.assertRefus(self.un(r, "maison/app.apk"), "exclu")
        self.assertEqual(self.ssh.scripts, [])
        self.assertFalse(any(p.is_file() for p in self.projet.rglob("*") if ".git" not in p.parts
                             and p.name != ".gitignore"))

    def test_lien_sur_le_serveur_refuse(self):
        (self.projet / ".gitignore").write_text("/sortie/\n/lie/\n", encoding="utf-8")
        cle = self.maison / "android-signature" / "debug.keystore"
        cle.parent.mkdir(parents=True)
        cle.write_bytes(b"CLE-FACTICE")
        (self.travail / "sortie").mkdir()
        os.symlink(cle, self.travail / "sortie" / "lien.apk")                    # lien symbolique vers la clé
        os.symlink(self.maison / "android-signature", self.travail / "lie")      # dossier lié
        self.serveur("dur/source.zip", b"Z")
        os.link(self.travail / "dur" / "source.zip", self.travail / "sortie" / "dur.zip")   # lien dur
        r = self.rapatrier(["sortie/lien.apk", "lie/debug.apk", "sortie/dur.zip"])
        for c in ("sortie/lien.apk", "lie/debug.apk", "sortie/dur.zip"):
            self.assertRefus(self.un(r, c), "lien")
        self.assertFalse((self.projet / "sortie" / "lien.apk").exists())

    def test_trop_gros_et_total_depasse(self):
        self.serveur("sortie/gros.zip", b"x" * 2000)
        r = self.rapatrier(["sortie/gros.zip"], max_octets=1000)
        self.assertRefus(r[0], "trop gros")
        for i in range(3):
            self.serveur(f"sortie/p{i}.zip", b"y" * 600)
        r = self.rapatrier([f"sortie/p{i}.zip" for i in range(3)], max_octets=1000, max_total=1300)
        self.assertEqual([x["statut"] for x in r], ["rapatrie", "rapatrie", "refuse"])
        self.assertRefus(r[2], "total")

    def test_neuf_fichiers_le_neuvieme_refuse(self):
        chemins = []
        for i in range(9):
            self.serveur(f"sortie/f{i}.zip", bytes([i]) * 10)
            chemins.append(f"sortie/f{i}.zip")
        r = self.rapatrier(chemins)
        self.assertEqual(sum(x["statut"] == "rapatrie" for x in r), 8)
        self.assertRefus(self.un(r, "sortie/f8.zip"), "au plus 8")
        self.assertFalse((self.projet / "sortie" / "f8.zip").exists())

    def test_sha_qui_ne_correspond_pas_jete(self):
        self.serveur(APK_REL, APK)
        self.ssh.alterer = lambda b: b[:-1] + bytes([b[-1] ^ 1])
        r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "SHA-256")
        dossier = (self.projet / APK_REL).parent
        self.assertEqual(list(dossier.iterdir()), [])                 # ni le fichier ni son temporaire

    def test_fichier_existant_plus_recent_garde_plus_ancien_remplace(self):
        self.serveur(APK_REL, APK)
        cible = self.projet / APK_REL
        cible.parent.mkdir(parents=True)
        cible.write_bytes(b"APK-LOCAL")
        r = self.rapatrier([APK_REL])                                # plus récent que la tâche : gardé
        self.assertRefus(r[0], "plus récent")
        self.assertEqual(cible.read_bytes(), b"APK-LOCAL")
        os.utime(cible, (self.debut - 3600, self.debut - 3600))      # plus ancien que la tâche, sous build/ : remplacé
        r = self.rapatrier([APK_REL])
        self.assertEqual(r[0]["statut"], "rapatrie")
        self.assertEqual(cible.read_bytes(), APK)
        self.assertRefus(self.rapatrier([APK_REL], debut=None)[0], "plus récent")   # date de la tâche inconnue

    def test_fichier_existant_hors_build_jamais_ecrase(self):
        (self.projet / ".gitignore").write_text("*.zip\n", encoding="utf-8")
        self.serveur("livrables/jeu.zip", b"NOUVEAU")
        cible = self.projet / "livrables" / "jeu.zip"
        cible.parent.mkdir()
        cible.write_bytes(b"ANCIEN")
        os.utime(cible, (self.debut - 3600, self.debut - 3600))
        self.assertRefus(self.rapatrier(["livrables/jeu.zip"])[0], "hors d'un dossier de build")
        self.assertEqual(cible.read_bytes(), b"ANCIEN")

    def test_destination_non_ignoree_par_git_refusee(self):
        self.serveur("livrables/jeu.zip", b"Z")
        self.assertRefus(self.rapatrier(["livrables/jeu.zip"])[0], "ignoré par git")
        self.assertFalse((self.projet / "livrables").exists())

    def test_lien_dans_le_projet_du_poste_refuse(self):
        self.serveur(APK_REL, APK)
        ailleurs = Path(self._tmp.name) / "ailleurs"
        ailleurs.mkdir()
        os.symlink(ailleurs, self.projet / "android_app", target_is_directory=True)
        self.assertRefus(self.rapatrier([APK_REL])[0], "lien")
        self.assertEqual(list(ailleurs.iterdir()), [])

    def test_fichier_qui_contient_le_jeton_jamais_rapatrie(self):
        (self.maison / "agent-identifiants").mkdir()
        (self.maison / "agent-identifiants" / "jeton").write_text(JETON + "\n", encoding="utf-8")
        self.serveur(APK_REL, b"PK" + JETON.encode() + b"fin")
        self.serveur("sortie/propre.zip", b"PROPRE")
        r = self.rapatrier([APK_REL, "sortie/propre.zip"])
        self.assertRefus(self.un(r, APK_REL), "secret")
        self.assertEqual(self.un(r, "sortie/propre.zip")["statut"], "rapatrie")
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
        faux = (f"ok 10 {'0' * 64} sortie/autre.apk\nok abc {'0' * 64} {APK_REL}\n")
        with mock.patch.object(st, "_bash", return_value=(0, faux, "")):
            r = self.rapatrier([APK_REL])
        self.assertRefus(r[0], "invalide")
        self.assertFalse((self.projet / "sortie").exists())


if __name__ == "__main__":
    unittest.main()
