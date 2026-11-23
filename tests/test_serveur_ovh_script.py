"""Script de mise en place du serveur (`serveur_ovh/mise_en_place.sh`) : lancé avec le bash du poste, en `--simuler`."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent / "serveur_ovh"
SCRIPT = RACINE / "mise_en_place.sh"
ETAPES = ("durcissement", "docker", "images", "licence", "etat")
NOUVELLES = ("android_build", "android_emulateur", "unity_cli")
CLES = {"etape", "statut", "detail", "versions", "disque_libre_go"}


CURL_FACTICE = r'''out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; -*) shift;; *) url="$1"; shift;; esac; done
case "$url" in *mozilla*) m="$CLE_MOZILLA";; *) m="$CLE_UNITY";; esac
case "$m" in
  ok) printf 'CLE-VALIDE %s\n' "$url" > "$out";;
  vide) : > "$out";;
  tronque) printf 'CLE-PART' > "$out"; exit 18;;
  http) exit 22;;
  invalide) printf '<html>erreur</html>\n' > "$out";;
esac'''
GPG_FACTICE = r'''mode=""; out=""; entree=""; gh=""
while [ $# -gt 0 ]; do case "$1" in --dearmor) mode=d; shift;; --show-keys) mode=s; shift;; -o) out="$2"; shift 2;; --homedir) gh="$2"; shift 2;; --*) shift;; *) entree="$1"; shift;; esac; done
# sans --homedir temporaire existant, le vrai gpg créerait ~/.gnupg : le faux refuse
[ -n "$gh" ] && [ -d "$gh" ] || exit 9
: > "$gh/trustdb.gpg"
case "$mode" in
  d) grep -q CLE-VALIDE "$entree" || exit 2; printf 'TROUSSEAU\n' > "$out";;
  s) grep -q -e CLE-VALIDE -e TROUSSEAU "$entree" || exit 2;;
esac'''

def lancer(etape, simuler=True, entree="", env=None):
    args = ["bash", SCRIPT.as_posix(), "--etape", etape] + (["--simuler"] if simuler else [])
    e = dict(os.environ, **(env or {}))
    return subprocess.run(args, input=entree, capture_output=True, text=True, env=e, timeout=60)


POLITIQUE_MOZILLA = """firefox:
  Installed: 130.0
  Candidate: 130.0
  Version table:
 *** 130.0 1000
       1000 https://packages.mozilla.org/apt mozilla/main amd64 Packages
        100 /var/lib/dpkg/status
     1:1snap1 500
        500 http://archive.ubuntu.com/ubuntu noble/main amd64 Packages"""
POLITIQUE_SNAP = """firefox:
  Installed: 1:1snap1
  Candidate: 1:1snap1
  Version table:
     130.0 1000
       1000 https://packages.mozilla.org/apt mozilla/main amd64 Packages
 *** 1:1snap1 500
        500 http://archive.ubuntu.com/ubuntu noble/main amd64 Packages
        100 /var/lib/dpkg/status"""


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestScriptSimule(unittest.TestCase):
    def test_chaque_etape_rend_un_json_valide(self):
        for etape in ETAPES:
            with self.subTest(etape=etape):
                r = lancer(etape, env={"DISQUE_LIBRE_GO": "500"})
                self.assertEqual(r.returncode, 0, r.stderr)
                lignes = [x for x in r.stdout.splitlines() if x.strip()]
                self.assertEqual(len(lignes), 1, r.stdout)
                d = json.loads(lignes[0])
                self.assertEqual(set(d), CLES)
                self.assertEqual(d["etape"], etape)
                self.assertIn(d["statut"], ("fait", "a_faire", "bloque"))
                self.assertIsInstance(d["detail"], str)
                self.assertIsInstance(d["versions"], dict)
                self.assertEqual(d["disque_libre_go"], 500)

    def test_simuler_ne_modifie_rien(self):
        # De faux apt/docker/ufw/systemctl... dans le PATH enregistrent tout appel : il ne doit y en avoir aucun.
        with tempfile.TemporaryDirectory() as t:
            journal = Path(t) / "appels.txt"
            for nom in ("apt-get", "apt", "docker", "ufw", "systemctl", "sshd", "curl", "sudo"):
                f = Path(t) / nom
                f.write_text(f'#!/bin/sh\necho "{nom} $@" >> "{journal.as_posix()}"\n', newline="\n")
                f.chmod(0o755)
            for etape in ETAPES:
                r = lancer(etape, env={"DISQUE_LIBRE_GO": "500", "PATH": Path(t).as_posix() + os.pathsep + os.environ["PATH"]})
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("simul", json.loads(r.stdout.strip().splitlines()[-1])["detail"].lower())
            self.assertFalse(journal.exists(), journal.read_text() if journal.exists() else "")

    def test_images_refuse_si_disque_presque_plein(self):
        r = lancer("images", env={"DISQUE_LIBRE_GO": "5"})
        d = json.loads(r.stdout)
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("disque", d["detail"].lower())
        self.assertEqual(d["disque_libre_go"], 5)

    def test_licence_absente_n_est_pas_une_erreur(self):
        r = lancer("licence", simuler=True, entree="", env={"DISQUE_LIBRE_GO": "500"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["statut"], "a_faire")

    def test_licence_jamais_reaffichee(self):
        secret = "SECRET-ULF-<xml>-12345"
        r = lancer("licence", simuler=True, entree=secret, env={"DISQUE_LIBRE_GO": "500"})
        self.assertNotIn(secret, r.stdout + r.stderr)

    def test_autres_etapes_tournent_stdin_ferme(self):
        for etape in ("durcissement", "docker", "images", "etat"):
            with self.subTest(etape=etape):
                args = ["bash", SCRIPT.as_posix(), "--etape", etape, "--simuler"]
                r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   env=dict(os.environ, DISQUE_LIBRE_GO="500"), timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr)
                json.loads(r.stdout)

    def test_autres_etapes_ne_lisent_pas_stdin(self):
        # Seules licence et bureau_distant lisent stdin : une commande lancée par les autres ne doit rien en consommer.
        for etape in ("durcissement", "docker", "images", "etat"):
            with self.subTest(etape=etape):
                r = lancer(etape, entree="ligne-pour-personne\n", env={"DISQUE_LIBRE_GO": "500"})
                self.assertEqual(r.returncode, 0, r.stderr)
                json.loads(r.stdout)

    # --- Étape bureau_distant ---------------------------------------------------

    MDP = "Un-Mot-De-Passe-Long-42"

    def _bureau(self, mdp, simuler=False, ecoute="127.0.0.1:3389", ufw="Status: active\n22/tcp LIMIT Anywhere", ssh_mdp="no",
                sshd_sortie=None, utilisateur="ubuntu", ini=None, politique=None, firefox_reel="/usr/lib/firefox/firefox", maj_ok=True,
                cle_mozilla="ok", cle_unity="ok", apt_avant=None, install_ok=True):
        """Lance bureau_distant avec de faux binaires ; rend (JSON, journal des appels, mot de passe reçu par chpasswd, dossier home)."""
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            journal, recu = t / "appels.txt", t / "chpasswd.txt"
            faux = t / "bin"
            faux.mkdir()
            home = t / "home"
            home.mkdir()
            corps = {
                "sudo": (f'echo "sudo $@" >> "{journal.as_posix()}"\n'
                         'while case "$1" in *=*) true;; *) false;; esac; do shift; done\n'
                         'if [ "$1" = env ]; then shift; while case "$1" in *=*) true;; *) false;; esac; do shift; done; fi\n'
                         f'case "$1" in chpasswd) cat > "{recu.as_posix()}";; ufw|sshd|apt-get|curl|gpg|mv|rm|chmod|tee|install|mktemp) "$@";; *) exit 0;; esac'),
                "ss": f'echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"\n'
                      f'echo "LISTEN 0 4096 {ecoute} 0.0.0.0:*"\necho "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*"',
                "ufw": f'echo "ufw $@" >> "{journal.as_posix()}"\ncat <<"EOT"\n{ufw}\nEOT',
                "sshd": "cat <<'EOT'\n" + (f"passwordauthentication {ssh_mdp}\nkbdinteractiveauthentication no" if sshd_sortie is None else sshd_sortie) + "\nEOT",
                "unityhub": "exit 0",
                "startxfce4": "exit 0",
                "id": f'[ "$1" = -un ] && echo {utilisateur} || echo "ubuntu ssl-cert"',
                "firefox": "exit 0",
                "readlink": f'echo "{firefox_reel}"',
                "apt-cache": "cat <<'EOT'\n" + (politique if politique is not None else POLITIQUE_MOZILLA) + "\nEOT",
            }
            corps["curl"] = CURL_FACTICE
            corps["gpg"] = GPG_FACTICE
            corps["apt-get"] = ('[ "$1" = update ] && [ "%s" = non ] && exit 1\n' % ("oui" if maj_ok else "non")
                                + '[ "$1" = install ] && [ "%s" = non ] && case "$*" in *xrdp*) exit 1;; esac\nexit 0' % ("oui" if install_ok else "non"))
            for nom in ("apt-get", "systemctl", "usermod", "chpasswd"):
                corps.setdefault(nom, "exit 0")
            for nom, texte in corps.items():
                if nom not in ("sudo", "ufw", "sshd", "apt-cache"):
                    texte = f'echo "{nom} $@" >> "{journal.as_posix()}"\n' + texte
                (faux / nom).write_text("#!/bin/sh\n" + texte + "\n", newline="\n")
                (faux / nom).chmod(0o755)
            (t / "tmp").mkdir()
            envs = dict(APT_RACINE=(t / "apt").as_posix(), CLE_MOZILLA=cle_mozilla, CLE_UNITY=cle_unity, TMPDIR=(t / "tmp").as_posix())
            for dossier_apt in ("sources.list.d", "preferences.d"):
                (t / "apt" / dossier_apt).mkdir(parents=True)
            for rel, contenu in (apt_avant or {}).items():
                (t / "apt" / rel).parent.mkdir(parents=True, exist_ok=True)
                (t / "apt" / rel).write_text(contenu, newline="\n")
            if ini is not None:
                (t / "xrdp.ini").write_text(ini, newline="\n")
                envs["XRDP_INI"] = (t / "xrdp.ini").as_posix()
            args = ["bash", SCRIPT.as_posix(), "--etape", "bureau_distant"] + (["--simuler"] if simuler else [])
            r = subprocess.run(args, input=mdp, capture_output=True, text=True, encoding="utf-8", timeout=60,
                               env=dict(os.environ, HOME=home.as_posix(), DISQUE_LIBRE_GO="500", BUREAU_ATTENTE_S="0", **envs,
                                        PATH=faux.as_posix() + os.pathsep + os.environ["PATH"]))
            appels = journal.read_text() if journal.exists() else ""
            self.tmp_restant = [x.name for x in (t / "tmp").iterdir()]   # dossiers gpg temporaires oubliés
            self.apt = {x.relative_to(t / "apt").as_posix(): x.read_text() for x in (t / "apt").rglob("*") if x.is_file()}
            autostart = home / ".config" / "autostart" / "unityhub.desktop"
            return (json.loads(r.stdout), appels, recu.read_text() if recu.exists() else "", r,
                    autostart.read_text() if autostart.exists() else None,
                    (home / ".xsession").read_text() if (home / ".xsession").exists() else None)

    def test_bureau_distant_rend_un_json_valide_en_simulation(self):
        d, appels, _, r, _, _ = self._bureau(self.MDP + "\n", simuler=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len([x for x in r.stdout.splitlines() if x.strip()]), 1, r.stdout)
        self.assertEqual(set(d), CLES)
        self.assertEqual(d["etape"], "bureau_distant")
        self.assertIn(d["statut"], ("fait", "a_faire", "bloque"))
        self.assertIn("simul", d["detail"].lower())
        self.assertEqual(appels, "")

    def test_bureau_distant_sans_mot_de_passe_est_a_faire(self):
        for entree in ("", "\n"):
            with self.subTest(entree=entree):
                d, appels, recu, _, _, _ = self._bureau(entree)
                self.assertEqual(d["statut"], "a_faire")
                self.assertEqual(appels, "")
                self.assertEqual(recu, "")

    def test_bureau_distant_refuse_un_mot_de_passe_trop_court(self):
        court = "a1B2c3D4e5F6g7H"
        self.assertEqual(len(court), 15)
        d, appels, recu, r, _, _ = self._bureau(court + "\n")
        self.assertEqual(d["statut"], "bloque")
        self.assertNotIn(court, r.stdout + r.stderr)
        self.assertEqual(appels, "")
        self.assertEqual(recu, "")
        seize = court + "x"
        d, _, _, _, _, _ = self._bureau(seize + "\n")
        self.assertEqual(d["statut"], "fait")

    def test_bureau_distant_mot_de_passe_jamais_en_argument_ni_dans_la_sortie(self):
        d, appels, recu, r, autostart, xsession = self._bureau(self.MDP + "\n")
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertEqual(recu, "ubuntu:" + self.MDP + "\n")     # il passe par le tube de chpasswd, et seulement là
        self.assertIn("sudo chpasswd", appels)
        self.assertNotIn(self.MDP, appels)
        self.assertNotIn(self.MDP, r.stdout + r.stderr)
        self.assertNotIn(self.MDP, autostart + xsession)
        self.assertIn("Session graphique prête", d["detail"])

    def test_bureau_distant_xrdp_ecoute_seulement_en_loopback(self):
        for adresse in ("0.0.0.0:3389", "*:3389", "[::]:3389"):
            with self.subTest(adresse=adresse):
                d, _, _, _, _, _ = self._bureau(self.MDP + "\n", ecoute=adresse)
                self.assertEqual(d["statut"], "bloque")
                self.assertIn("3389", d["detail"])
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", ecoute="127.0.0.1:3389")
        self.assertEqual(d["statut"], "fait")

    def test_bureau_distant_ne_touche_pas_ufw(self):
        _, appels, _, _, _, _ = self._bureau(self.MDP + "\n")
        ufw = [x for x in appels.splitlines() if re.match(r"(sudo )?ufw\b", x)]
        self.assertTrue(ufw, appels)
        for x in ufw:
            self.assertRegex(x, r"^(sudo )?ufw status$", x)
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", ufw="Status: active\n3389/tcp ALLOW Anywhere")
        self.assertEqual(d["statut"], "bloque")

    def test_bureau_distant_autostart_unityhub(self):
        d, _, _, _, autostart, xsession = self._bureau(self.MDP + "\n")
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertRegex(autostart, r"(?m)^Exec=.*\bunityhub\b")
        self.assertIn("[Desktop Entry]", autostart)
        self.assertEqual(xsession, "startxfce4\n")

    def test_bureau_distant_refuse_si_connexion_ssh_par_mot_de_passe_ouverte(self):
        d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", ssh_mdp="yes")
        self.assertEqual(d["statut"], "bloque")
        self.assertEqual(recu, "")
        self.assertNotIn("apt-get", appels)

    def test_bureau_distant_redemarre_xrdp_meme_si_le_ini_est_deja_bon(self):
        # Une exécution précédente a pu écrire le ini puis mourir : le service garde alors l'ancienne écoute.
        d, appels, _, _, _, _ = self._bureau(self.MDP + "\n", ini="[Globals]\nport=tcp://127.0.0.1:3389\n")
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertIn("systemctl restart xrdp", appels)
        self.assertNotIn("sed", appels)

    def test_bureau_distant_ne_fixe_le_mot_de_passe_qu_apres_toutes_les_preuves(self):
        for nom, args in (("ecoute", dict(ecoute="0.0.0.0:3389")),
                          ("ufw", dict(ufw="Status: active\n3389/tcp ALLOW Anywhere")),
                          ("firefox snap", dict(politique=POLITIQUE_SNAP)),
                          ("firefox lien snap", dict(firefox_reel="/usr/bin/snap"))):
            with self.subTest(preuve=nom):
                d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", **args)
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertNotIn("chpasswd", appels)
                self.assertEqual(recu, "")
        _, appels, recu, _, _, _ = self._bureau(self.MDP + "\n")
        self.assertEqual(recu, "ubuntu:" + self.MDP + "\n")

    def test_bureau_distant_exige_ssh_sans_mot_de_passe_explicite(self):
        for nom, sortie in (("vide", ""), ("kbdinteractive yes", "passwordauthentication no\nkbdinteractiveauthentication yes"),
                            ("kbdinteractive absent", "passwordauthentication no")):
            with self.subTest(sortie=nom):
                d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", sshd_sortie=sortie)
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertIn("Rien n'a été modifié", d["detail"])
                self.assertNotIn("apt-get", appels)
                self.assertEqual(recu, "")
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", sshd_sortie="passwordauthentication no\nkbdinteractiveauthentication no")
        self.assertEqual(d["statut"], "fait", d["detail"])

    def test_bureau_distant_refuse_root(self):
        d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", utilisateur="root")
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("root", d["detail"])
        self.assertEqual(recu, "")
        self.assertNotIn("apt-get", appels)

    LISTES = ("sources.list.d/mozilla.list", "sources.list.d/unityhub.list")

    def test_bureau_distant_cles_valides_installees_sans_temporaire(self):
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n")
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertIn("CLE-VALIDE", self.apt["keyrings/packages.mozilla.org.asc"])
        self.assertEqual(self.apt["keyrings/unityhub.gpg"], "TROUSSEAU\n")
        for liste in self.LISTES:
            self.assertIn(liste, self.apt)
        self.assertEqual([x for x in self.apt if x.endswith((".tmp", ".brut"))], [])

    def test_bureau_distant_rafraichit_les_cles_a_chaque_execution(self):
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", apt_avant={"keyrings/packages.mozilla.org.asc": "ANCIENNE",
                                                                  "keyrings/unityhub.gpg": "ANCIENNE"})
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertIn("CLE-VALIDE", self.apt["keyrings/packages.mozilla.org.asc"])
        self.assertEqual(self.apt["keyrings/unityhub.gpg"], "TROUSSEAU\n")

    def test_bureau_distant_cle_defectueuse_bloque_sans_remplacer_la_cle_et_retire_les_listes(self):
        for cle in ("mozilla", "unity"):
            for defaut in ("vide", "tronque", "http", "invalide"):
                with self.subTest(cle=cle, defaut=defaut):
                    avant = {"keyrings/packages.mozilla.org.asc": "ANCIENNE-M", "keyrings/unityhub.gpg": "ANCIENNE-U",
                             **{liste: "deb ancien\n" for liste in self.LISTES}}
                    d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", apt_avant=avant, **{"cle_" + cle: defaut})
                    self.assertEqual(d["statut"], "bloque", d["detail"])
                    self.assertIn("Clé du dépôt", d["detail"])
                    fichier = "keyrings/packages.mozilla.org.asc" if cle == "mozilla" else "keyrings/unityhub.gpg"
                    self.assertEqual(self.apt[fichier], "ANCIENNE-M" if cle == "mozilla" else "ANCIENNE-U")
                    # Mozilla en échec : les deux clés anciennes sont invalides, les deux listes partent. Unity Hub en échec :
                    # la clé Mozilla, rafraîchie et valide, garde sa liste ; seule la liste Unity Hub (clé invalide) part.
                    for liste in self.LISTES:
                        if cle == "unity" and liste == self.LISTES[0]:
                            self.assertEqual(self.apt[liste], "deb ancien\n")
                        else:
                            self.assertNotIn(liste, self.apt)
                    self.assertEqual([x for x in self.apt if x.endswith((".tmp", ".brut"))], [])
                    self.assertEqual(recu, "")
                    self.assertNotIn("firefox unityhub", appels)
                    for interdit in ("systemctl restart xrdp", "usermod", "chpasswd"):
                        self.assertNotIn(interdit, appels)

    def test_bureau_distant_cle_valide_et_liste_existantes_survivent_a_un_echec_de_telechargement(self):
        for cle in ("mozilla", "unity"):
            for defaut in ("vide", "tronque", "http", "invalide"):
                with self.subTest(cle=cle, defaut=defaut):
                    avant = {"keyrings/packages.mozilla.org.asc": "CLE-VALIDE M ancienne\n", "keyrings/unityhub.gpg": "TROUSSEAU\n",
                             "sources.list.d/mozilla.list": "deb M\n", "sources.list.d/unityhub.list": "deb U\n",
                             "preferences.d/mozilla": "pin\n"}
                    d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", apt_avant=avant, **{"cle_" + cle: defaut})
                    self.assertEqual(d["statut"], "bloque", d["detail"])
                    self.assertIn("conservée", d["detail"])
                    # la clé en échec garde son ancienne valeur ; la clé téléchargée avec succès est rafraîchie
                    rafraichie = "keyrings/unityhub.gpg" if cle == "mozilla" else "keyrings/packages.mozilla.org.asc"
                    for rel, contenu in avant.items():
                        if rel != rafraichie:
                            self.assertEqual(self.apt[rel], contenu, rel)
                    self.assertEqual([x for x in self.apt if x.endswith((".tmp", ".brut"))], [])
                    self.assertEqual(recu, "")
                    self.assertNotIn("firefox unityhub", appels)

    def test_bureau_distant_ne_retire_que_la_liste_dont_la_cle_manque_ou_est_invalide(self):
        # clé Mozilla absente + liste présente : retirée ; clé Unity Hub valide + liste présente : gardée
        avant = {"keyrings/unityhub.gpg": "TROUSSEAU\n", "sources.list.d/mozilla.list": "deb M\n", "sources.list.d/unityhub.list": "deb U\n"}
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", apt_avant=avant, cle_mozilla="http")
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertNotIn("sources.list.d/mozilla.list", self.apt)
        self.assertEqual(self.apt["sources.list.d/unityhub.list"], "deb U\n")
        self.assertNotIn("keyrings/packages.mozilla.org.asc", self.apt)
        # clé Mozilla présente mais invalide + liste présente : liste retirée
        avant = {"keyrings/packages.mozilla.org.asc": "<html>", "sources.list.d/mozilla.list": "deb M\n"}
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", apt_avant=avant, cle_mozilla="vide")
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertNotIn("sources.list.d/mozilla.list", self.apt)
        self.assertEqual([x for x in self.apt if x.endswith((".tmp", ".brut"))], [])

    def test_bureau_distant_gpg_utilise_un_homedir_temporaire_supprime(self):
        for cle_unity in ("ok", "invalide"):
            with self.subTest(cle_unity=cle_unity):
                d, appels, _, _, _, _ = self._bureau(self.MDP + "\n", cle_unity=cle_unity)
                gpgs = [x for x in appels.splitlines() if x.startswith("gpg ")]
                self.assertTrue(gpgs, appels)
                for x in gpgs:
                    self.assertRegex(x, r"--homedir \S+/tmp/tmp\.", x)   # créé par mktemp sous le TMPDIR du test
                self.assertEqual(self.tmp_restant, [])                   # et tous supprimés (vrai aussi sous Windows)

    def test_bureau_distant_echec_de_l_installation_arrete_xrdp(self):
        d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", install_ok=False)
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertIn("Installation de XFCE", d["detail"])
        self.assertEqual(self._systemctl(appels)[-1], "sudo systemctl stop xrdp", appels)
        self.assertNotIn("chpasswd", appels)
        self.assertEqual(recu, "")

    def test_bureau_distant_cle_en_echec_premiere_execution_ne_pretend_pas_conserver(self):
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", cle_mozilla="http")
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertIn("Clé du dépôt Mozilla", d["detail"])
        self.assertNotIn("précédente", d["detail"])
        self.assertNotIn("conservée", d["detail"])
        self.assertIn("aucun dépôt", d["detail"])
        self.assertEqual([x for x in self.apt if x.startswith("sources.list.d/")], [])

    def test_bureau_distant_cle_en_echec_avec_liste_retiree_le_dit(self):
        d, _, _, _, _, _ = self._bureau(self.MDP + "\n", apt_avant={"sources.list.d/mozilla.list": "deb M\n"}, cle_mozilla="http")
        self.assertIn("retiré", d["detail"])
        self.assertNotIn("précédente", d["detail"])

    @staticmethod
    def _systemctl(appels):
        return [x for x in appels.splitlines() if x.startswith("sudo systemctl ")]

    def test_bureau_distant_arrete_xrdp_juste_apres_l_installation(self):
        _, appels, _, _, _, _ = self._bureau(self.MDP + "\n")
        lignes = appels.splitlines()
        i = next(n for n, x in enumerate(lignes) if x.startswith("apt-get install -y ca-certificates"))
        suite = [x for x in lignes[i + 1:] if x.startswith(("sudo systemctl", "curl", "sudo usermod", "gpg"))]
        self.assertEqual(suite[0], "sudo systemctl stop xrdp", suite)

    def test_bureau_distant_bloque_apres_installation_laisse_xrdp_arrete(self):
        cas = (("cle mozilla", dict(cle_mozilla="http")), ("cle unity", dict(cle_unity="vide")), ("index apt", dict(maj_ok=False)),
               ("ecoute ailleurs", dict(ecoute="0.0.0.0:3389")), ("aucune ecoute", dict(ecoute="")))
        for nom, args in cas:
            with self.subTest(cas=nom):
                d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n", **args)
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertEqual(self._systemctl(appels)[-1], "sudo systemctl stop xrdp", appels)
                self.assertEqual(recu, "")

    def test_bureau_distant_succes_finit_avec_xrdp_demarre_et_mot_de_passe_en_dernier(self):
        d, appels, recu, _, _, _ = self._bureau(self.MDP + "\n")
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertEqual(self._systemctl(appels)[-1], "sudo systemctl restart xrdp", appels)
        self.assertTrue(appels.splitlines()[-1].startswith("sudo chpasswd"), appels)
        self.assertEqual(recu, "ubuntu:" + self.MDP + "\n")

    def test_bureau_distant_bloque_si_les_index_apt_echouent(self):
        d, _, recu, _, _, _ = self._bureau(self.MDP + "\n", maj_ok=False)
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertEqual(recu, "")

    def _durcir_avec_faux(self, cles, ssh_ok):
        """Lance l'étape durcissement (réelle) avec de faux binaires ; rend (JSON, journal des appels)."""
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            journal = t / "appels.txt"
            faux = t / "bin"
            faux.mkdir()
            corps = {
                "sudo": 'exec "$@"',
                "ssh": "exit 0" if ssh_ok else "exit 255",
                "ssh-keygen": 'while [ $# -gt 0 ]; do [ "$1" = -f ] && f="$2"; shift; done; echo cle > "$f"; echo pub > "$f.pub"',
            }
            for nom in ("apt-get", "dpkg-reconfigure", "ufw", "sshd", "systemctl", "tee", "ssh", "ssh-keygen", "sudo"):
                texte = f'#!/bin/sh\necho "{nom} $@" >> "{journal.as_posix()}"\n' + corps.get(nom, "") + "\n"
                if nom == "sudo":
                    texte = '#!/bin/sh\nwhile case "$1" in *=*) true;; *) false;; esac; do shift; done\nexec "$@"\n'
                (faux / nom).write_text(texte, newline="\n")
                (faux / nom).chmod(0o755)
            home = t / "home"
            (home / ".ssh").mkdir(parents=True)
            (home / ".ssh" / "authorized_keys").write_text(cles, newline="\n")
            r = subprocess.run(["bash", SCRIPT.as_posix(), "--etape", "durcissement"], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="utf-8", timeout=60,
                               env=dict(os.environ, HOME=home.as_posix(), PATH=faux.as_posix() + os.pathsep + os.environ["PATH"]))
            appels = journal.read_text() if journal.exists() else ""
            return json.loads(r.stdout), appels

    def _aucun_appel_sensible(self, appels):
        for interdit in ("ufw ", "sshd ", "systemctl", "tee"):
            # `sshd -T` et `ufw status` sont des lectures du constat initial, pas des modifications.
            self.assertFalse([x for x in appels.splitlines()
                              if x.startswith(interdit) and not x.startswith(("sshd -T", "ufw status"))], appels)

    def test_durcissement_bloque_sans_autre_cle(self):
        d, appels = self._durcir_avec_faux("", ssh_ok=True)
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("clé dédiée", d["detail"])
        self._aucun_appel_sensible(appels)

    def test_durcissement_bloque_si_seconde_session_echoue(self):
        d, appels = self._durcir_avec_faux("ssh-ed25519 AAAAautre directeur\n", ssh_ok=False)
        self.assertEqual(d["statut"], "bloque")
        self._aucun_appel_sensible(appels)

    def test_etape_inconnue_refusee(self):
        r = lancer("nimportequoi")
        self.assertNotEqual(r.returncode, 0)

    def test_etape_sans_valeur_sort_en_erreur_sans_boucler(self):
        for args in (["--etape"], ["--simuler", "--etape"]):
            with self.subTest(args=args):
                r = subprocess.run(["bash", SCRIPT.as_posix()] + args, stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, encoding="utf-8", timeout=10)   # une boucle sans fin lèverait TimeoutExpired
                self.assertEqual(r.returncode, 2)
                self.assertIn("valeur", r.stderr)

    def _etat_avec_faux(self, images_absentes=(), volumes_ok=True, ufw_francais=False):
        """Lance l'étape etat (réelle) avec de faux binaires : serveur durci, Docker présent, images au choix."""
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            faux = t / "bin"
            faux.mkdir()
            absentes = " ".join(f'*"{i}"*) exit 1;;' for i in images_absentes)
            corps = {
                "sudo": 'while case "$1" in *=*) true;; *) false;; esac; do shift; done\nexec "$@"',
                "sshd": 'echo "passwordauthentication no"',
                # un serveur en français répond « État : actif » sauf si l'appelant force LC_ALL=C
                "ufw": ('if [ "$LC_ALL" = C ] || [ -z "%s" ]; then echo "Status: active"; else echo "État : actif"; fi'
                        % ("oui" if ufw_francais else "")),
                "dpkg": "exit 0",
                "docker": ('case "$1 $2" in "image inspect") case "$*" in ' + absentes + ' esac;; '
                           f'"volume inspect") exit {0 if volumes_ok else 1};; esac\nexit 0'),
            }
            for nom, texte in corps.items():
                (faux / nom).write_text("#!/bin/sh\n" + texte + "\n", newline="\n")
                (faux / nom).chmod(0o755)
            r = subprocess.run(["bash", SCRIPT.as_posix(), "--etape", "etat"], stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, encoding="utf-8", timeout=60, env=dict(os.environ, DISQUE_LIBRE_GO="500",
                               PATH=faux.as_posix() + os.pathsep + os.environ["PATH"]))
            return json.loads(r.stdout)

    def test_etat_lit_ufw_en_langue_c_meme_sur_un_serveur_francais(self):
        self.assertEqual(self._etat_avec_faux(ufw_francais=True)["statut"], "fait")

    def test_aucun_ufw_status_du_script_sans_langue_c(self):
        for ligne in SCRIPT.read_text(encoding="utf-8").splitlines():
            if "ufw status" in ligne and not ligne.lstrip().startswith("#"):
                self.assertIn("sudo env LC_ALL=C ufw status", ligne)

    def test_etat_exige_les_trois_images(self):
        self.assertEqual(self._etat_avec_faux()["statut"], "fait")
        for absente in ("unityci/editor", "myiafactory/android", "myiafactory/agent"):
            with self.subTest(absente=absente):
                d = self._etat_avec_faux(images_absentes=(absente,))
                self.assertEqual(d["statut"], "a_faire")
                self.assertIn("images", d["detail"])


ZIP_CONTENU = b"ZIPFAKE\n"
NUMERO_RECENT = "13000000"


class Monde:
    """Faux serveur pour les étapes android_build / android_emulateur / unity_cli / docker : de faux binaires dans le PATH
    journalisent tous leurs appels ; rien n'atteint ni le réseau ni un vrai sudo. L'état (SDK, groupe kvm, paquets) persiste
    d'un lancement à l'autre dans le même Monde, pour tester l'idempotence."""

    def __init__(self, manifeste="ok", archive="ok", sha_manifeste=None, unity="ok", unzip_echec=False, jdk=True,
                 paquets_absents=False, kvm=True, kvm_membre=False, sdkmanager_echec=False, sdk_version="ok",
                 utilisateur="ubuntu", sdk_lent=False, licence_echec=False, mv_echec=False, canal_latest="channel-0",
                 alternatives="auto", licence_lente=False, alt_set_echec=False):
        self.opt = dict(CURL_MANIFESTE=manifeste, CURL_ZIP=archive, CURL_UNITY=unity, UNZIP_ECHEC="1" if unzip_echec else "",
                        SDKMANAGER_ECHEC="1" if sdkmanager_echec else "", SDK_VERSION_MODE=sdk_version,
                        FAUX_UTILISATEUR=utilisateur, SDKMANAGER_LENT="1" if sdk_lent else "",
                        SDKMANAGER_LICENCE_ECHEC="1" if licence_echec else "", MV_ECHEC="1" if mv_echec else "",
                        ALT_MODE=alternatives, ALT_SET_ECHEC="1" if alt_set_echec else "", SDKMANAGER_LICENCE_LENTE="1" if licence_lente else "",
                        PAQUETS_ABSENTS="1" if paquets_absents else "")
        self.canal_latest = canal_latest
        self.sha = sha_manifeste or hashlib.sha1(ZIP_CONTENU).hexdigest()
        self.jdk, self.kvm, self.kvm_membre = jdk, kvm, kvm_membre

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        t = self.t = Path(self._t.name)
        self.journal_fichier, self.stdin_fichier = t / "appels.txt", t / "stdin.txt"
        self.home, self.jvm, self.etat, self.faux = t / "home", t / "jvm", t / "etat", t / "bin"
        for d in (self.home, self.jvm, self.etat, self.faux, t / "tmp"):
            d.mkdir()
        self.sdk = self.home / "android-sdk"
        j, si, tp, e = self.journal_fichier.as_posix(), self.stdin_fichier.as_posix(), t.as_posix(), self.etat.as_posix()
        (t / "archive.zip").write_bytes(ZIP_CONTENU)
        (t / "manifeste.xml").write_text(
            # Un paquet alpha (canal beta) AVANT le stable, avec un N plus grand et plus de chiffres, et un cmdline-tools;17.0
            # stable de N plus grand : seul le paquet cmdline-tools;latest du canal stable doit être retenu.
            '<sdk:sdk-repository xmlns:sdk="x">\n'
            '<remotePackage path="cmdline-tools;19.0-alpha01"><channelRef ref="channel-1"/><archives>\n'
            f'<archive><complete><size>1</size><checksum type="sha1">{"a" * 40}</checksum>\n'
            '   <url>commandlinetools-linux-999999999_latest.zip</url></complete><host-os>linux</host-os></archive>\n'
            '</archives></remotePackage>\n'
            f'<remotePackage path="cmdline-tools;latest">\n<channelRef ref="{self.canal_latest}"/><archives>\n'
            f'<archive><complete><size>1</size><checksum type="sha1">{self.sha}</checksum>\n'
            f'   <url>commandlinetools-linux-{NUMERO_RECENT}_latest.zip</url></complete><host-os>linux</host-os></archive>\n'
            f'<archive><complete><size>1</size><checksum type="sha1">{"c" * 40}</checksum>\n'
            '   <url>commandlinetools-mac-99999999_latest.zip</url></complete><host-os>macosx</host-os></archive>\n'
            '</archives></remotePackage>\n'
            '<remotePackage path="cmdline-tools;17.0"><channelRef ref="channel-0"/><archives>\n'
            f'<archive><complete><size>1</size><checksum type="sha1">{"b" * 40}</checksum>\n'
            '   <url>commandlinetools-linux-20000000_latest.zip</url></complete><host-os>linux</host-os></archive>\n'
            '</archives></remotePackage></sdk:sdk-repository>\n', newline="\n")
        (t / "sdkmanager.fixe").write_text(
            '#!/bin/sh\n'
            f'echo "sdkmanager $@" >> "{j}"\necho "JAVA_HOME=$JAVA_HOME" >> "{j}"\n'
            'root=""; lic=""\n'
            'for a in "$@"; do case "$a" in --sdk_root=*) root="${a#--sdk_root=}";; --licenses) lic=1;; esac; done\n'
            'if [ "$1" = --version ]; then case "$SDK_VERSION_MODE" in\n'
            '  classfile) case "$JAVA_HOME" in *java-21*) echo 12.0; exit 0;; *) echo "java.lang.UnsupportedClassVersionError: class file version 65.0" >&2; exit 1;; esac;;\n'
            '  toujours) echo "java.lang.UnsupportedClassVersionError: class file version 65.0" >&2; exit 1;;\n'
            '  autre) echo "boom" >&2; exit 1;;\n'
            '  *) echo 12.0; exit 0;; esac; fi\n'
            'if [ -n "$lic" ]; then head -n 1 > /dev/null; [ -n "$SDKMANAGER_LICENCE_LENTE" ] && sleep 5; [ -n "$SDKMANAGER_LICENCE_ECHEC" ] && exit 1; exit 0; fi\n'
            f'cat >> "{si}"\n'
            '[ -n "$SDKMANAGER_LENT" ] && sleep 5\n'
            '[ -n "$SDKMANAGER_ECHEC" ] && exit 1\n'
            '[ -n "$SDKMANAGER_LICENCE_ECHEC" ] && exit 1\n'
            'for a in "$@"; do case "$a" in\n'
            '  platform-tools) mkdir -p "$root/platform-tools"; echo "#!/bin/sh" > "$root/platform-tools/adb"; chmod 755 "$root/platform-tools/adb";;\n'
            '  platforms\\;*) mkdir -p "$root/platforms/${a#platforms;}";;\n'
            '  build-tools\\;*) mkdir -p "$root/build-tools/${a#build-tools;}";;\n'
            '  emulator) mkdir -p "$root/emulator"; echo "#!/bin/sh" > "$root/emulator/emulator"; chmod 755 "$root/emulator/emulator";;\n'
            '  system-images\\;*) mkdir -p "$root/$(echo "$a" | tr ";" "/")";;\n'
            'esac; done\nexit 0\n', newline="\n")
        (t / "install.sh").write_text(
            '#!/bin/bash\n'
            f'echo "installeur-unity-execute SKIP=$UNITY_CLI_SKIP_SETUP" >> "{j}"\ncat >> "{si}"\n'
            'mkdir -p "$HOME/.local/bin"\n'
            "cat > \"$HOME/.local/bin/unity\" <<'EOT'\n#!/bin/sh\n"
            f'echo "unity $@" >> "{j}"\n'
            'case "$1" in --version) echo "unity 1.0";; esac\nEOT\n'
            'chmod 755 "$HOME/.local/bin/unity"\n', newline="\n")
        jdk_bin = f"{self.jvm.as_posix()}/java-17-openjdk-amd64/bin"
        jdk21_bin = f"{self.jvm.as_posix()}/java-21-openjdk-amd64/bin"
        corps = {
            "sudo": 'while case "$1" in *=*|-n) true;; *) false;; esac; do shift; done\nexec "$@"',
            "curl": ('out=""; url=""\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; --connect-timeout|--max-time) shift 2;; -*) shift;; *) url="$1"; shift;; esac; done\n'
                     'case "$url" in\n'
                     f'  */repository2-3.xml) case "$CURL_MANIFESTE" in http) exit 22;; vide) : > "$out";; sans) echo "<xml/>" > "$out";; *) cp "{tp}/manifeste.xml" "$out";; esac;;\n'
                     f'  */commandlinetools-linux-*) case "$CURL_ZIP" in http) exit 22;; vide) : > "$out";; tronque) printf "ZIPFA" > "$out"; exit 18;; corrompu) echo "ZIPFAKE-AUTRE" > "$out";; *) cp "{tp}/archive.zip" "$out";; esac;;\n'
                     f'  */install.sh) case "$CURL_UNITY" in http) exit 22;; vide) : > "$out";; sanshebang) echo "echo coucou" > "$out";; *) cp "{tp}/install.sh" "$out";; esac;;\n'
                     '  *) exit 22;;\nesac'),
            "unzip": ('[ -n "$UNZIP_ECHEC" ] && exit 1\nf=""; d=""\n'
                      'while [ $# -gt 0 ]; do case "$1" in -q) shift;; -d) d="$2"; shift 2;; *) f="$1"; shift;; esac; done\n'
                      'grep -q ZIPFAKE "$f" || exit 9\n'
                      f'mkdir -p "$d/cmdline-tools/bin" && cp "{tp}/sdkmanager.fixe" "$d/cmdline-tools/bin/sdkmanager" && chmod 755 "$d/cmdline-tools/bin/sdkmanager"'),
            "zip": "exit 0",
            "dpkg-query": (f'case "$*" in *openjdk-21*) [ -e "{e}/apt21" ] && echo installed && exit 0; exit 1;; esac\n'
                           f'[ -e "{e}/apt" ] && echo installed && exit 0\n[ "$PAQUETS_ABSENTS" = 1 ] && exit 1\necho installed'),
            "apt-get": (f'case "$*" in *install*) touch "{e}/apt"; case "$*" in *openjdk-17*) mkdir -p "{jdk_bin}"; '
                        f'echo "#!/bin/sh" > "{jdk_bin}/java"; echo "#!/bin/sh" > "{jdk_bin}/javac"; chmod 755 "{jdk_bin}/java" "{jdk_bin}/javac";; '
                        f'*openjdk-21*) touch "{e}/apt21"; mkdir -p "{jdk21_bin}"; '
                        f'echo "#!/bin/sh" > "{jdk21_bin}/java"; echo "#!/bin/sh" > "{jdk21_bin}/javac"; chmod 755 "{jdk21_bin}/java" "{jdk21_bin}/javac";; esac;; esac\nexit 0'),
            "update-alternatives": (f'if [ "$1" = --set ] && [ -n "$ALT_SET_ECHEC" ]; then exit 1; fi\n'
                                    # sortie en français (« Valeur : ») sauf si l'appelant force LC_ALL=C, comme un serveur français
                                    f'if [ "$1" = --query ]; then if [ "$LC_ALL" = C ]; then V="Value:"; else V="Valeur :"; fi; echo "Name: $2"; '
                                    f'if [ "$ALT_MODE" = autre ]; then echo "Status: manual"; echo "$V /opt/autre-jdk/bin/$2"; '
                                    f'elif [ -e "{e}/apt21" ]; then echo "Status: auto"; echo "$V {jdk21_bin}/$2"; '
                                    f'else echo "Status: auto"; echo "$V {jdk_bin}/$2"; fi; fi\nexit 0'),
            "usermod": f'touch "{e}/kvm"',
            "mv": 'case "$*" in *extrait*) [ -n "$MV_ECHEC" ] && exit 1;; esac\nexec /usr/bin/mv "$@"',
            "id": (f'case "$1" in -un) echo "${{FAUX_UTILISATEUR:-ubuntu}}";; '
                   f'-nG) if [ -e "{e}/kvm" ]; then echo "ubuntu kvm"; else echo ubuntu; fi;; esac'),
            "docker": "exit 0",
        }
        for nom, texte in corps.items():
            journalise = f'echo "{nom} $@" >> "{j}"\n' if nom not in ("id", "dpkg-query") else ""   # simples lectures : hors journal
            (self.faux / nom).write_text("#!/bin/sh\n" + journalise + texte + "\n", newline="\n")
            (self.faux / nom).chmod(0o755)
        if self.jdk:
            java = self.jvm / "java-17-openjdk-amd64" / "bin" / "java"
            java.parent.mkdir(parents=True)
            java.write_text("#!/bin/sh\n", newline="\n")
            java.chmod(0o755)
            (java.parent / "javac").write_text("#!/bin/sh\n", newline="\n")
            (java.parent / "javac").chmod(0o755)
        if self.kvm:
            (t / "kvm").write_text("", newline="\n")
        if self.kvm_membre:
            (self.etat / "kvm").write_text("", newline="\n")
        return self

    def __exit__(self, *a):
        self._t.cleanup()

    def installer_sdkmanager(self):
        """Une installation de cmdline-tools déjà valide (avec un marqueur pour constater qu'on n'y touche pas)."""
        d = self.sdk / "cmdline-tools" / "latest"
        (d / "bin").mkdir(parents=True)
        shutil.copy(self.t / "sdkmanager.fixe", d / "bin" / "sdkmanager")
        (d / "bin" / "sdkmanager").chmod(0o755)
        (d / "marqueur").write_text("ancienne", newline="\n")
        return d

    def lancer(self, etape, simuler=False, entree="", env=None):
        e = dict(os.environ, HOME=self.home.as_posix(), PATH=self.faux.as_posix() + os.pathsep + os.environ["PATH"],
                 TMPDIR=(self.t / "tmp").as_posix(), DISQUE_LIBRE_GO="500", JVM_RACINE=self.jvm.as_posix(),
                 KVM_PERIPH=(self.t / "kvm").as_posix(), UNITY_EDITEUR="", JAVA_HOME="", **self.opt)
        e.update(env or {})
        args = ["bash", SCRIPT.as_posix(), "--etape", etape] + (["--simuler"] if simuler else [])
        r = subprocess.run(args, input=entree, capture_output=True, text=True, encoding="utf-8", env=e, timeout=60)
        lignes = [x for x in r.stdout.splitlines() if x.strip()]
        assert len(lignes) == 1, (r.stdout, r.stderr)
        self.derniere = r
        return json.loads(lignes[0])

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def appels(self, prefixe):
        return [x for x in self.journal.splitlines() if x.startswith(prefixe)]

    def restes(self, dossier):
        return sorted(x.name for x in dossier.iterdir()) if dossier.exists() else []


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEtapesCapacites(unittest.TestCase):
    def test_nouvelles_etapes_json_valide_en_simulation(self):
        for etape in NOUVELLES + ("docker",):
            with self.subTest(etape=etape), Monde() as m:
                d = m.lancer(etape, simuler=True)
                self.assertEqual(m.derniere.returncode, 0, m.derniere.stderr)
                self.assertEqual(set(d), CLES)
                self.assertEqual(d["etape"], etape)
                self.assertEqual(d["statut"], "a_faire")
                self.assertIn("simul", d["detail"].lower())
                self.assertEqual(d["disque_libre_go"], 500)
                self.assertEqual(m.journal, "")                 # rien d'appelé : ni apt, ni curl, ni sudo
                self.assertEqual(list(m.home.iterdir()), [])

    # --- android_build ---------------------------------------------------------

    def test_android_build_fait_avec_le_jdk_d_unity_sans_rien_installer(self):
        with Monde(jdk=False) as m:
            for rel in ("platform-tools", "platforms/android-36", "build-tools/36.0.0"):
                (m.sdk / rel).mkdir(parents=True)
            adb = m.sdk / "platform-tools" / "adb"
            adb.write_text("#!/bin/sh\n", newline="\n")
            adb.chmod(0o755)
            java = m.home / "Unity/Hub/Editor/6000.0.1f1/Editor/Data/PlaybackEngines/AndroidPlayer/OpenJDK/bin/java"
            java.parent.mkdir(parents=True)
            java.write_text("#!/bin/sh\n", newline="\n")
            java.chmod(0o755)
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertIn("JDK d'Unity", d["detail"])
            self.assertEqual(m.appels("apt-get "), [])               # le JDK 17 d'apt n'est pas installé sans y être invité
            self.assertEqual(m.appels("curl "), [])
            self.assertEqual(m.appels("sdkmanager "), [])

    def test_android_build_installe_le_sdk_dedie(self):
        with Monde() as m:
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            for rel in ("platform-tools/adb", "platforms/android-36", "build-tools/36.0.0", "cmdline-tools/latest/bin/sdkmanager"):
                self.assertTrue((m.sdk / rel).exists(), rel)
            self.assertEqual(m.restes(m.sdk / "cmdline-tools"), ["latest"])
            curls = m.appels("curl ")
            self.assertEqual(len(curls), 2, curls)
            self.assertIn("-fsSL --connect-timeout 20 --max-time 60 https://dl.google.com/android/repository/repository2-3.xml -o ", curls[0])
            self.assertIn(f"-fsSL --connect-timeout 20 --max-time 1200 https://dl.google.com/android/repository/commandlinetools-linux-{NUMERO_RECENT}_latest.zip -o ", curls[1])
            sdkm = m.appels("sdkmanager ")
            self.assertTrue(any("--licenses" in x for x in sdkm), sdkm)
            installe = [x for x in sdkm if "--licenses" not in x and "--version" not in x]
            self.assertEqual(len(installe), 1, sdkm)
            self.assertRegex(installe[0], r"--sdk_root=\S*/home/android-sdk ")
            for paquet in ("platform-tools", "platforms;android-36", "build-tools;36.0.0"):
                self.assertIn(paquet, installe[0])
            self.assertIn(f"JAVA_HOME={(m.jvm / 'java-17-openjdk-amd64').as_posix()}", m.journal)
            self.assertEqual(m.appels("apt-get "), [])            # unzip, zip et JDK déjà présents : rien à installer

    def test_android_build_installe_unzip_zip_et_jdk17_s_ils_manquent(self):
        with Monde(paquets_absents=True, jdk=False) as m:
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            installs = [x for x in m.appels("apt-get ") if " install " in x]
            self.assertEqual(len(installs), 1, installs)
            for paquet in ("unzip", "zip", "openjdk-17-jdk-headless"):
                self.assertIn(paquet, installs[0])

    def test_android_build_manifest_introuvable_est_bloque(self):
        for defaut in ("http", "vide", "sans"):
            with self.subTest(manifeste=defaut), Monde(manifeste=defaut) as m:
                d = m.lancer("android_build")
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertIn("anifeste", d["detail"])
                self.assertEqual(len(m.appels("curl ")), 1)       # l'archive n'est jamais demandée
                self.assertEqual(m.restes(m.sdk / "cmdline-tools"), [])
                self.assertEqual(m.appels("sdkmanager "), [])

    def test_android_build_telechargement_tronque_est_bloque_sans_rien_laisser(self):
        for defaut, extra in (("tronque", {}), ("http", {}), ("vide", {}), ("ok", {"unzip_echec": True})):
            with self.subTest(archive=defaut, extra=extra), Monde(archive=defaut, **extra) as m:
                d = m.lancer("android_build")
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertEqual(m.restes(m.sdk / "cmdline-tools"), [])     # ni latest, ni temporaire
                self.assertEqual(m.appels("sdkmanager "), [])

    def test_android_build_verifie_le_sha1_du_manifest(self):
        for nom, args in (("manifeste faux", dict(sha_manifeste="0" * 40)), ("archive corrompue", dict(archive="corrompu"))):
            with self.subTest(cas=nom), Monde(**args) as m:
                d = m.lancer("android_build")
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertIn("SHA-1", d["detail"])
                self.assertEqual(m.restes(m.sdk / "cmdline-tools"), [])     # pas de mv en place, temporaire supprimé
                self.assertEqual(m.appels("unzip "), [])                    # jamais extraite
                self.assertEqual(m.appels("sdkmanager "), [])
                self.assertFalse((m.sdk / "platform-tools").exists())

    def test_android_build_ne_touche_pas_une_installation_valide(self):
        with Monde(manifeste="http") as m:
            ancienne = m.installer_sdkmanager()
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual((ancienne / "marqueur").read_text(), "ancienne")
            self.assertEqual(m.appels("curl "), [])

    def test_android_build_deuxieme_passage_ne_telecharge_rien(self):
        with Monde() as m:
            self.assertEqual(m.lancer("android_build")["statut"], "fait")
            avant = m.journal
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.journal, avant)                       # aucun nouvel appel : ni curl, ni apt, ni sdkmanager

    def test_android_build_choisit_l_archive_du_paquet_latest_stable(self):
        # le manifeste de test place avant lui un alpha (canal beta) et après lui un cmdline-tools;17.0 de N plus grands
        with Monde() as m:
            self.assertEqual(m.lancer("android_build")["statut"], "fait")
            self.assertIn(f"commandlinetools-linux-{NUMERO_RECENT}_latest.zip", m.appels("curl ")[1])
            self.assertNotIn("999999999", m.journal)
            self.assertNotIn("20000000", m.journal)
        with Monde(canal_latest="channel-1") as m:               # « latest » seulement en beta : aucune archive stable
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertEqual(len(m.appels("curl ")), 1)

    def test_android_build_remplace_un_latest_incomplet_en_le_gardant_de_cote(self):
        with Monde() as m:
            latest = m.sdk / "cmdline-tools" / "latest"
            (latest / "bin").mkdir(parents=True)
            (latest / "bin" / "sdkmanager").write_text("tronque", newline="\n")      # non exécutable
            (latest / "marqueur").write_text("ancienne", newline="\n")
            (latest / "bin" / "sdkmanager").chmod(0o644)
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertIn("JAVA_HOME", (latest / "bin" / "sdkmanager").read_text())   # le nouveau, pas le tronqué
            self.assertFalse((latest / "latest").exists())           # pas d'imbrication
            self.assertFalse((latest / "cmdline-tools").exists())
            anciens = [x for x in (m.sdk / "cmdline-tools").iterdir() if x.name.startswith("latest.ancien.")]
            self.assertEqual(len(anciens), 1)
            self.assertEqual((anciens[0] / "marqueur").read_text(), "ancienne")   # gardé, jamais supprimé

    def test_android_build_restaure_l_ancien_latest_si_la_mise_en_place_echoue(self):
        with Monde(mv_echec=True) as m:
            latest = m.sdk / "cmdline-tools" / "latest"
            latest.mkdir(parents=True)
            (latest / "marqueur").write_text("ancienne", newline="\n")
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertEqual((latest / "marqueur").read_text(), "ancienne")
            self.assertEqual(m.restes(m.sdk / "cmdline-tools"), ["latest"])
        with Monde(archive="http") as m:                          # téléchargement raté : le latest incomplet n'est pas touché
            latest = m.sdk / "cmdline-tools" / "latest"
            latest.mkdir(parents=True)
            (latest / "marqueur").write_text("ancienne", newline="\n")
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertEqual(m.restes(m.sdk / "cmdline-tools"), ["latest"])

    def test_android_build_retire_les_temporaires_perimes(self):
        with Monde() as m:
            vieux = m.sdk / "cmdline-tools" / ".telechargement.ABC123"
            vieux.mkdir(parents=True)
            (vieux / "archive.zip").write_text("reste", newline="\n")
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.restes(m.sdk / "cmdline-tools"), ["latest"])

    def test_android_build_refuse_root_et_disque_insuffisant(self):
        with Monde(utilisateur="root") as m:
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("root", d["detail"])
            self.assertEqual(m.journal, "")
            self.assertEqual(list(m.home.iterdir()), [])
        with Monde() as m:
            d = m.lancer("android_build", env={"DISQUE_LIBRE_GO": "14"})
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("isque", d["detail"])
            self.assertEqual(m.journal, "")
            self.assertEqual(m.lancer("android_build", env={"DISQUE_LIBRE_GO": "15"})["statut"], "fait")

    def test_android_build_utilise_le_jdk21_pour_sdkmanager_si_le_17_est_refuse(self):
        with Monde(sdk_version="classfile") as m:
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            installs = [x for x in m.appels("apt-get ") if " install " in x]
            self.assertEqual(len(installs), 1, installs)
            self.assertIn("openjdk-21-jdk-headless", installs[0])
            self.assertNotIn("openjdk-17", installs[0])               # le JDK 17 reste le JDK du projet, déjà là
            self.assertTrue(any("java-21-openjdk" in x for x in m.journal.splitlines() if x.startswith("JAVA_HOME=")))
            installe = [i for i, x in enumerate(m.journal.splitlines()) if x.startswith("sdkmanager --sdk_root=") and "--licenses" not in x]
            self.assertTrue(installe)
            self.assertIn("java-21-openjdk", m.journal.splitlines()[installe[0] + 1])   # JAVA_HOME de CET appel
            self.assertTrue((m.sdk / "platform-tools" / "adb").exists())

    def test_jdk21_installe_pour_sdkmanager_ne_devient_pas_le_jdk_par_defaut(self):
        with Monde(sdk_version="classfile") as m:             # alternatives en auto : l'installation du 21 les a fait passer au 21
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            sets = m.appels("update-alternatives --set")
            self.assertEqual(len(sets), 2, m.journal)
            self.assertRegex(sets[0], r"--set java \S*/java-17-openjdk-amd64/bin/java$")
            self.assertRegex(sets[1], r"--set javac \S*/java-17-openjdk-amd64/bin/javac$")
            self.assertIn("JDK 21", d["detail"])
            self.assertIn("sdkmanager", d["detail"])
            self.assertIn("JDK 17 reste", d["detail"])
        with Monde(sdk_version="classfile", alternatives="autre") as m:   # réglage du Directeur (ni 21 ni auto) : jamais touché
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.appels("update-alternatives --set"), [])
            self.assertIn("JDK 17 reste", d["detail"])
        with Monde() as m:                                    # pas de repli : aucune alternative lue ni changée, détail inchangé
            d = m.lancer("android_build")
            self.assertEqual(m.appels("update-alternatives"), [])
            self.assertNotIn("JDK 21", d["detail"])

    def test_echec_du_retablissement_du_jdk17_est_dit_dans_le_detail(self):
        with Monde(sdk_version="classfile", alt_set_echec=True) as m:
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "fait", d["detail"])                   # le SDK fonctionne
            self.assertIn("JDK 21 est resté le Java par défaut", d["detail"])
            self.assertIn("sudo update-alternatives --config java", d["detail"])
            self.assertNotIn("rétabli", d["detail"])

    def test_android_emulateur_apres_repli_jdk21_garde_aussi_le_17_par_defaut(self):
        with Monde(sdk_version="classfile") as m:
            m.installer_sdkmanager()                          # android_build déjà fait à la main, sdkmanager exige le 21
            (m.sdk / "platform-tools").mkdir()
            (m.sdk / "platform-tools" / "adb").write_text("#!/bin/sh\n", newline="\n")
            (m.sdk / "platform-tools" / "adb").chmod(0o755)
            (m.sdk / "platforms" / "android-36").mkdir(parents=True)
            (m.sdk / "build-tools" / "36.0.0").mkdir(parents=True)
            d = m.lancer("android_emulateur")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(len(m.appels("update-alternatives --set")), 2, m.journal)
            self.assertIn("JDK 17 reste", d["detail"])

    def test_licence_expiree_n_est_qu_un_avertissement_si_l_installation_reussit(self):
        with Monde(licence_lente=True) as m:
            d = m.lancer("android_build", env={"SDK_DELAI_LICENCE_S": "1"})
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertTrue((m.sdk / "platform-tools" / "adb").exists())

    def test_sdkmanager_inutilisable_dit_comment_reparer(self):
        with Monde(sdk_version="autre") as m:
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("supprimez ~/android-sdk/cmdline-tools/latest puis relancez", d["detail"])
            self.assertIn("rm -rf", d["detail"])
            self.assertTrue((m.sdk / "cmdline-tools" / "latest").exists())      # jamais supprimé automatiquement

    def test_android_build_bloque_si_aucun_jdk_ne_convient_a_sdkmanager(self):
        for mode, attendu in (("toujours", "JDK"), ("autre", "sdkmanager")):
            with self.subTest(mode=mode), Monde(sdk_version=mode) as m:
                d = m.lancer("android_build")
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertIn(attendu, d["detail"])
                self.assertFalse((m.sdk / "platform-tools").exists())
                if mode == "autre":                                   # autre erreur : pas d'installation de JDK à l'aveugle
                    self.assertEqual([x for x in m.appels("apt-get ") if " install " in x], [])

    def test_android_build_expire_proprement_et_distingue_les_licences(self):
        with Monde(sdk_lent=True) as m:
            d = m.lancer("android_build", env={"SDK_DELAI_S": "1"})
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("élai", d["detail"])
        with Monde(licence_echec=True) as m:
            d = m.lancer("android_build")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("icence", d["detail"])
            self.assertNotIn("Installation de platform-tools", d["detail"])

    def test_apt_des_nouvelles_etapes_attend_le_verrou_dpkg(self):
        with Monde(paquets_absents=True, jdk=False) as m:
            m.lancer("android_build")
            apts = m.appels("apt-get ")
            self.assertTrue(apts)
            for x in apts:
                self.assertIn("-o DPkg::Lock::Timeout=120", x)
        with Monde(paquets_absents=True) as m:
            m.lancer("docker")
            for x in m.appels("apt-get "):
                self.assertIn("-o DPkg::Lock::Timeout=120", x)

    # --- android_emulateur -----------------------------------------------------

    def test_android_emulateur_refuse_root_et_disque_insuffisant(self):
        with Monde() as m:
            m.lancer("android_build")
            avant = m.journal
            d = m.lancer("android_emulateur", env={"DISQUE_LIBRE_GO": "9"})
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("isque", d["detail"])
            self.assertEqual(m.journal, avant)
            m.opt["FAUX_UTILISATEUR"] = "root"
            d = m.lancer("android_emulateur")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("root", d["detail"])
            self.assertEqual(m.journal, avant)
            m.opt["FAUX_UTILISATEUR"] = "ubuntu"
            self.assertEqual(m.lancer("android_emulateur", env={"DISQUE_LIBRE_GO": "10"})["statut"], "fait")

    def test_android_emulateur_sans_android_build_est_a_faire(self):
        with Monde() as m:
            d = m.lancer("android_emulateur")
            self.assertEqual(d["statut"], "a_faire", d["detail"])
            self.assertIn("android-build", d["detail"])
            self.assertEqual(m.appels("sdkmanager "), [])
            self.assertEqual(m.appels("sudo "), [])

    def test_android_emulateur_exige_dev_kvm(self):
        with Monde(kvm=False) as m:
            self.assertEqual(m.lancer("android_build")["statut"], "fait")
            d = m.lancer("android_emulateur")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("KVM indisponible", d["detail"])
            self.assertEqual(m.appels("sudo usermod"), [])
            self.assertFalse((m.sdk / "emulator").exists())

    def test_android_emulateur_installe_et_ajoute_au_groupe_kvm(self):
        with Monde() as m:
            m.lancer("android_build")
            d = m.lancer("android_emulateur")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.appels("sudo usermod"), ["sudo usermod -aG kvm ubuntu"])
            self.assertIn("prochaine connexion SSH", d["detail"])
            self.assertTrue((m.sdk / "emulator" / "emulator").exists())
            self.assertTrue((m.sdk / "system-images" / "android-34" / "google_apis" / "x86_64").is_dir())
            self.assertTrue(any(" emulator " in x and "system-images;android-34;google_apis;x86_64" in x for x in m.appels("sdkmanager ")))
            avant = m.journal
            d = m.lancer("android_emulateur")                        # deuxième passage : rien à refaire
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.journal, avant)

    def test_android_emulateur_membre_du_groupe_kvm_ne_refait_pas_usermod(self):
        with Monde(kvm_membre=True) as m:
            m.lancer("android_build")
            d = m.lancer("android_emulateur")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.appels("sudo usermod"), [])
            self.assertNotIn("prochaine connexion", d["detail"])

    def test_android_emulateur_echec_sdkmanager_est_bloque(self):
        with Monde() as m:
            m.lancer("android_build")
            m.opt["SDKMANAGER_ECHEC"] = "1"
            d = m.lancer("android_emulateur")
            self.assertEqual(d["statut"], "bloque", d["detail"])

    # --- unity_cli -------------------------------------------------------------

    def test_unity_cli_installe_le_cli_sans_editeur(self):
        with Monde() as m:
            d = m.lancer("unity_cli")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertIn("installez un éditeur", d["detail"])
            self.assertIn("Unity Hub", d["detail"])
            self.assertTrue((m.home / ".local" / "bin" / "unity").exists())
            # le script officiel tourne SANS son étape finale (skills dans les clients d'agents, plugin) : UNITY_CLI_SKIP_SETUP=1
            self.assertEqual(m.appels("installeur-unity-execute"), ["installeur-unity-execute SKIP=1"])
            self.assertIn("profil", d["detail"])
            self.assertEqual(len(m.appels("curl -fsSL --connect-timeout 20 --max-time 60 https://unity.com/install.sh -o ")), 1, m.journal)
            self.assertEqual([x for x in m.restes(m.home / ".local" / "bin") if x.startswith(".")], [])   # temporaire supprimé
            self.assertEqual(m.appels("unity install"), [])          # jamais d'éditeur : CLI seulement
            avant = m.journal
            d = m.lancer("unity_cli")                                # idempotent : pas de nouveau téléchargement
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.appels("curl "), m.appels("curl ")[:1])
            self.assertEqual(m.journal.count("installeur-unity-execute"), 1)
            self.assertTrue(m.journal.startswith(avant))

    def test_unity_cli_exige_un_script_non_vide_avec_shebang(self):
        for defaut in ("vide", "sanshebang", "http"):
            with self.subTest(script=defaut), Monde(unity=defaut) as m:
                d = m.lancer("unity_cli")
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertEqual(m.appels("installeur-unity-execute"), [])   # jamais exécuté
                self.assertEqual(m.restes(m.home / ".local" / "bin"), [])
                self.assertFalse((m.home / ".local" / "bin" / "unity").exists())

    def test_unity_cli_n_execute_pas_un_script_non_verifie(self):
        with Monde(unity="sanshebang") as m:
            d = m.lancer("unity_cli")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertNotIn("coucou", m.derniere.stdout + m.derniere.stderr)

    def test_unity_cli_n_installe_jamais_d_editeur(self):
        with Monde() as m:
            d = m.lancer("unity_cli", env={"UNITY_EDITEUR": "6000.6.7f1"})      # l'ancienne variable est ignorée
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertNotIn("6000.6.7f1", d["detail"])
            self.assertEqual(m.appels("unity "), [x for x in m.appels("unity ") if x.startswith("unity --version")])

    def test_unity_cli_retire_ses_temporaires_perimes(self):
        with Monde() as m:
            bin_ = m.home / ".local" / "bin"
            bin_.mkdir(parents=True)
            (bin_ / ".installeur-unity.ABC123").write_text("reste d'une session tuée", newline="\n")
            d = m.lancer("unity_cli")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual([x for x in m.restes(bin_) if x.startswith(".")], [])

    def test_unity_cli_refuse_root_et_disque_insuffisant(self):
        with Monde(utilisateur="root") as m:
            d = m.lancer("unity_cli")
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("root", d["detail"])
            self.assertEqual(m.journal, "")
            self.assertEqual(list(m.home.iterdir()), [])
        with Monde() as m:
            d = m.lancer("unity_cli", env={"DISQUE_LIBRE_GO": "1"})
            self.assertEqual(d["statut"], "bloque", d["detail"])
            self.assertIn("isque", d["detail"])
            self.assertEqual(m.journal, "")
            d = m.lancer("unity_cli", env={"DISQUE_LIBRE_GO": "2"})
            self.assertEqual(d["statut"], "fait", d["detail"])

    # --- docker : unzip et zip ---------------------------------------------------

    def test_docker_installe_unzip_et_zip(self):
        with Monde(paquets_absents=True) as m:
            d = m.lancer("docker")
            self.assertEqual(d["statut"], "fait", d["detail"])
            installs = [x for x in m.appels("apt-get ") if " install " in x]
            self.assertEqual(len(installs), 1, installs)
            self.assertTrue(installs[0].endswith("unzip zip"), installs)
        with Monde() as m:                                           # déjà présents : idempotent
            d = m.lancer("docker")
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.appels("apt-get "), [])

    # --- stdin fermé -------------------------------------------------------------

    def test_nouvelles_etapes_gardent_stdin_ferme(self):
        with Monde() as m:
            for etape in ("android_build", "android_emulateur", "unity_cli", "docker"):
                d = m.lancer(etape, entree="ligne-secrete-12345\n")
                self.assertEqual(d["statut"], "fait", (etape, d["detail"]))
                self.assertNotIn("ligne-secrete", m.derniere.stdout + m.derniere.stderr)
            self.assertNotIn("ligne-secrete", m.journal)
            self.assertEqual(m.stdin_fichier.read_text() if m.stdin_fichier.exists() else "", "")


DOCKER_IMAGE = r'''echo "docker $*" >> "JOURNAL"
case "$1 $2" in
  "image inspect") [ -s "ETAT/etiquette" ] && { cat "ETAT/etiquette"; exit 0; }; exit 1 ;;
  "build "*) [ -n "${FAUX_BUILD_ECHEC:-}" ] && { i=1; while [ $i -le 30 ]; do echo "ligne-de-build-$i $HOME/secret-dossier"; i=$((i + 1)); done; printf 'avec-controle \001\033[31m\010fin\n'; exit 1; }
             prec=""; for a in "$@"; do [ "$prec" = --label ] && printf '%s' "${a#versions=}" > "ETAT/etiquette"; prec="$a"; last="$a"; done
             echo "contexte: $(ls "$last" | tr '\n' ' ')" >> "JOURNAL" ;;
esac
exit 0'''
MARQUEUR = Path(".myiafactory") / "emulateur-image.version"


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEtapeEmulateurImage(unittest.TestCase):
    def _monde(self, **kw):
        m = Monde(**kw).__enter__()
        self.addCleanup(m.__exit__)
        corps = DOCKER_IMAGE.replace("JOURNAL", m.journal_fichier.as_posix()).replace("ETAT", m.etat.as_posix())
        (m.faux / "docker").write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
        (m.faux / "docker").chmod(0o755)
        return m

    def _lancer(self, m, **env):
        return m.lancer("emulateur_image", env={"SERVEUR_OVH_DIR": RACINE.as_posix(), **env})

    def test_etape_emulateur_image_simulation_json_valide(self):
        m = self._monde()
        d = m.lancer("emulateur_image", simuler=True, env={"SERVEUR_OVH_DIR": RACINE.as_posix()})
        self.assertEqual(set(d), CLES)
        self.assertEqual((d["etape"], d["statut"]), ("emulateur_image", "a_faire"))
        self.assertIn("simul", d["detail"].lower())
        self.assertEqual(m.journal, "")
        self.assertEqual(list(m.home.iterdir()), [])
        self.assertIn("outils en ligne de commande Android", d["detail"])      # apportés par l'image, pas par l'hôte
        self.assertIn("16111833", d["detail"])
        self.assertIn("180 Mo", d["detail"])
        self.assertIn("SHA-1", d["detail"])

    def test_etape_emulateur_image_construit_puis_ecrit_le_marqueur(self):
        m = self._monde()
        d = self._lancer(m)
        self.assertEqual(d["statut"], "fait", d["detail"])
        builds = m.appels("docker build")
        self.assertEqual(len(builds), 1, m.journal)
        self.assertIn("--label versions=ubuntu=ubuntu:24.04;jdk=17;fichiers=", builds[0])
        self.assertIn("--build-arg UBUNTU_TAG=24.04", builds[0])
        self.assertIn("-t myiafactory/emulateur ", builds[0])
        contexte = m.appels("contexte:")[0]
        for f in ("Dockerfile", "entree-tache.sh", "pont.sh"):
            self.assertIn(f, contexte)
        etiquette = (m.etat / "etiquette").read_text()
        self.assertEqual((m.home / MARQUEUR).read_text().strip(), etiquette)
        sys.path.insert(0, str(RACINE.parent / "outils"))
        import serveur_installation
        self.assertEqual(etiquette, serveur_installation.empreinte_etape("emulateur_image"))   # même empreinte côté poste et côté serveur
        self.assertEqual(m.restes(m.home / ".myiafactory"), ["emulateur-image.version"])     # pas de fichier temporaire oublié
        self.assertNotIn("curl", m.journal)

    def test_etape_emulateur_image_idempotente(self):
        m = self._monde()
        self.assertEqual(self._lancer(m)["statut"], "fait")
        marqueur = (m.home / MARQUEUR).read_text()
        d = self._lancer(m)
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertEqual(len(m.appels("docker build")), 1, m.journal)                      # rien reconstruit
        self.assertEqual((m.home / MARQUEUR).read_text(), marqueur)
        (m.etat / "etiquette").write_text("ubuntu=autre", newline="\n")                    # image d'une autre version : reconstruite
        self.assertEqual(self._lancer(m)["statut"], "fait")
        self.assertEqual(len(m.appels("docker build")), 2, m.journal)

    def test_marqueur_retire_avant_la_reconstruction(self):
        m = self._monde()
        self.assertEqual(self._lancer(m)["statut"], "fait")
        self.assertTrue((m.home / MARQUEUR).exists())
        (m.etat / "etiquette").write_text("ubuntu=autre", newline="\n")                   # image périmée, reconstruction qui échoue
        d = self._lancer(m, FAUX_BUILD_ECHEC="1")
        self.assertEqual(d["statut"], "bloque")
        self.assertFalse((m.home / MARQUEUR).exists())                                     # la sonde ne ment pas sur une image périmée

    def test_empreinte_illisible_est_un_blocage_et_jamais_un_marqueur_vide(self):
        m = self._monde()
        (m.faux / "sha256sum").write_text("#!/bin/sh\ncat > /dev/null\necho\n", newline="\n")      # sha256sum défaillant : sortie vide
        (m.faux / "sha256sum").chmod(0o755)
        d = self._lancer(m)
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertIn("mpreinte", d["detail"])
        self.assertEqual(m.appels("docker build"), [])
        self.assertFalse((m.home / MARQUEUR).exists())

    def test_etape_emulateur_image_blocages(self):
        m = self._monde()
        d = self._lancer(m, DISQUE_LIBRE_GO="2")
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("isque", d["detail"])
        d = self._lancer(m, SERVEUR_OVH_DIR=(m.t / "vide").as_posix())
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("introuvable", d["detail"])
        self.assertIn("Relancez l'installation (elle redépose les fichiers)", d["detail"])
        d = self._lancer(m, FAUX_BUILD_ECHEC="1")
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertIn("ligne-de-build-30", d["detail"])                                    # fin du journal de construction...
        self.assertIn("avec-controle", d["detail"])                                        # (la ligne à caractères de contrôle est dans la fin)
        self.assertIn("ligne-de-build-12", d["detail"])
        self.assertNotIn("ligne-de-build-11 ", d["detail"])                                # ... les 20 dernières lignes seulement
        self.assertNotRegex(d["detail"], r"[\x00-\x08\x0b\x0c\x0e-\x1f]")                  # le JSON reste valide : aucun caractère de contrôle
        self.assertIn("~/secret-dossier", d["detail"])                                     # dossier personnel masqué
        self.assertFalse((m.home / MARQUEUR).exists())                                     # pas de marqueur sans image
        m.opt["FAUX_UTILISATEUR"] = "root"
        d = self._lancer(m)
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("root", d["detail"])


class TestDockerfileEmulateur(unittest.TestCase):
    """L'image n'est jamais construite par un test : le Dockerfile et l'entrée sont seulement lus."""
    DOCKERFILE = RACINE / "images" / "emulateur" / "Dockerfile"
    ENTREE = RACINE / "images" / "emulateur" / "entree-tache.sh"

    def setUp(self):
        self.texte = self.DOCKERFILE.read_text(encoding="utf-8")
        self.code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))
        # étape finale (l'image livrée) : tout ce qui suit le DERNIER FROM
        self.finale = self.code[self.code.rindex("\nFROM "):]

    def test_l_image_apporte_ses_outils_en_ligne_de_commande_epingles_et_verifies(self):
        # Le SDK de l'hôte n'a pas de cmdline-tools : l'image apporte avdmanager, version épinglée de versions.json,
        # archive vérifiée (SHA-1 du manifeste officiel) dans une étape de construction séparée, rien de téléchargé dans
        # l'image livrée, aucun « curl | sh », aucune archive laissée.
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        # Épingle PROPRE à l'image de l'émulateur : 11076708 (12.0) ne lit pas le package.xml (XML v4) de l'image système
        # de l'hôte (« AVD not created », constaté sur le serveur) ; 16111833 (23.0) crée l'AVD sans avertissement.
        pin = versions["emulateur_cmdline_tools"]
        self.assertNotEqual(pin, "11076708")
        self.assertEqual(versions["android_cmdline_tools"], "11076708")       # l'image android garde la sienne
        self.assertRegex(self.code, rf"(?m)^ARG CMDLINE_TOOLS={pin}$")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertRegex(script, rf'(?m)^V_CMDLINE_TOOLS_EMULATEUR="{pin}"$')
        etape = script[script.index("etape_emulateur_image()"):script.index("# --- Unity CLI")]
        self.assertIn('--build-arg "CMDLINE_TOOLS=$V_CMDLINE_TOOLS_EMULATEUR"', etape)
        self.assertRegex(self.code, r"(?m)^FROM ubuntu:\$\{UBUNTU_TAG\} AS outils$")
        construction = self.code[:self.code.rindex("\nFROM ")]
        self.assertIn("https://dl.google.com/android/repository/repository2-3.xml", construction)
        self.assertIn("commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip", construction)
        self.assertIn("sha1sum", construction)
        self.assertRegex(construction, r'\[ "\$obtenu" = "\$attendu" \]')
        self.assertNotRegex(self.code, r"\|\s*(sh|bash)\b")
        self.assertIn("rm -rf /tmp/outils.zip", construction)
        self.assertRegex(self.finale, r"(?m)^COPY --from=outils /opt/sdk-tache /opt/sdk-tache$")
        self.assertNotRegex(self.finale, r"\b(curl|wget|unzip)\b")
        for lien in ("emulator", "platform-tools", "system-images", "platforms", "licenses"):
            self.assertIn(lien, self.finale)                                  # le reste du SDK : celui monté de l'hôte

    def test_la_construction_de_l_image_garde_le_reseau(self):
        script = SCRIPT.read_text(encoding="utf-8")
        etape = script[script.index("etape_emulateur_image()"):script.index("# --- Unity CLI")]
        ligne = [x for x in etape.splitlines() if "docker build" in x][0]
        self.assertNotIn("--network", ligne)

    def test_base_epinglee_comme_les_autres_images(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        tag = versions["base_ubuntu"].split(":")[1]
        self.assertRegex(self.texte, rf"(?m)^ARG UBUNTU_TAG={re.escape(tag)}$")
        self.assertRegex(self.texte, r"(?m)^FROM ubuntu:\$\{UBUNTU_TAG\}$")
        self.assertGreaterEqual(float(tag), 22.04)                      # bash >= 4.4 (tableaux vides sous set -u) : 5.1 depuis 22.04

    def test_outils_exiges_par_le_pont(self):
        # flock, setsid / timeout, stat, sleep / bash / ffmpeg : images tirées des vidéos (finfilm)
        for paquet in ("openjdk-17-jdk-headless", "util-linux", "coreutils", "bash", "ffmpeg"):
            self.assertRegex(self.finale, rf"\b{paquet}\b")
        self.assertNotRegex(self.finale, r"\b(curl|wget)\b")                 # l'image livrée ne télécharge rien

    def test_sans_identifiants_et_utilisateur_1000(self):
        for mot in ("credential", "token", "api_key", "secret", "password", ".ssh", ".claude", "ANTHROPIC"):
            self.assertNotIn(mot.lower(), self.code.lower())
        self.assertNotRegex(self.code, r"(?m)^VOLUME\b")
        self.assertRegex(self.code, r"(?m)^USER 1000:1000$")

    def test_pont_et_entree_copies_et_environnement_pose_par_l_image(self):
        self.assertRegex(self.code, r"(?m)^COPY pont\.sh /usr/local/bin/pont$")
        self.assertRegex(self.code, r"(?m)^COPY entree-tache\.sh /usr/local/bin/entree-tache$")
        self.assertRegex(self.code, r'(?m)^ENTRYPOINT \["/usr/local/bin/entree-tache"\]$')
        # ANDROID_USER_HOME : Java prend user.home dans /etc/passwd (/home/ubuntu, lecture seule), pas dans $HOME (constaté)
        for reglage in ("PONT_SORTIE=/sortie", "PONT_AVD=emul", "ANDROID_AVD_HOME=/avd", "HOME=/tmp", "ANDROID_USER_HOME=/tmp/.android",
                        "PONT_EMULATEUR=/opt/android-sdk/emulator/emulator", "PONT_ADB=/opt/android-sdk/platform-tools/adb"):
            self.assertIn(reglage, self.code)

    def test_adb_vient_du_sdk_monte_et_non_d_un_paquet(self):
        self.assertNotIn("android-tools-adb", self.code)
        apt = self.finale[self.finale.index("apt-get install"):self.finale.index("rm -rf")]
        self.assertNotRegex(apt, r"adb")

    def test_entree_cree_l_avd_emul_puis_attend(self):
        self.assertEqual(subprocess.run(["bash", "-n", self.ENTREE.as_posix()], capture_output=True).returncode, 0)
        texte = self.ENTREE.read_text(encoding="utf-8")
        self.assertNotIn("\r", texte)
        self.assertIn("/opt/sdk-tache/cmdline-tools/latest/bin/avdmanager", texte)    # celui de l'image
        self.assertNotIn("$SDK/cmdline-tools", texte)                                 # jamais celui du SDK monté
        self.assertIn("/opt/android-sdk", texte)
        self.assertIn("TACHE_IMAGE_SYSTEME", texte)                     # image système épinglée par l'enveloppe, pas « la première »
        self.assertIn("hw.ramSize=2048", texte)
        self.assertIn("disk.dataPartition.size=2G", texte)
        self.assertIn("x86_64", texte)
        self.assertNotRegex(texte, r"\beval\b")
        self.assertNotIn("docker", " ".join(x for x in texte.splitlines() if not x.lstrip().startswith("#")))


DOCKER_AGENT = DOCKER_IMAGE.replace(
    '  "image inspect")',
    '  "network inspect") [ -e "ETAT/reseau" ] && exit 0; exit 1 ;;\n'
    '  "network create") [ -n "${FAUX_RESEAU_ECHEC:-}" ] && exit 1; : > "ETAT/reseau"; exit 0 ;;\n'
    '  "image inspect")')
MARQUEUR_AGENT = Path(".myiafactory") / "agent-image.version"


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEtapeAgentImage(unittest.TestCase):
    def _monde(self, **kw):
        m = Monde(**kw).__enter__()
        self.addCleanup(m.__exit__)
        corps = DOCKER_AGENT.replace("JOURNAL", m.journal_fichier.as_posix()).replace("ETAT", m.etat.as_posix())
        (m.faux / "docker").write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
        (m.faux / "docker").chmod(0o755)
        return m

    def _lancer(self, m, **env):
        return m.lancer("agent_image", env={"SERVEUR_OVH_DIR": RACINE.as_posix(), **env})

    def test_etape_agent_image_simulation_json_valide(self):
        m = self._monde()
        d = m.lancer("agent_image", simuler=True, env={"SERVEUR_OVH_DIR": RACINE.as_posix()})
        self.assertEqual(set(d), CLES)
        self.assertEqual((d["etape"], d["statut"]), ("agent_image", "a_faire"))
        self.assertIn("simul", d["detail"].lower())
        self.assertIn("myiafactory/agent", d["detail"])
        self.assertIn("myiafactory-agents", d["detail"])
        self.assertEqual(m.journal, "")
        self.assertEqual(list(m.home.iterdir()), [])

    def test_etape_agent_image_construit_reseau_et_marqueur(self):
        m = self._monde()
        d = self._lancer(m)
        self.assertEqual(d["statut"], "fait", d["detail"])
        builds = m.appels("docker build")
        self.assertEqual(len(builds), 1, m.journal)
        self.assertIn("--label versions=ubuntu=ubuntu:24.04;node=22;claude_code=2.1.328;fichiers=", builds[0])
        self.assertIn("--build-arg UBUNTU_TAG=24.04", builds[0])
        self.assertIn("--build-arg NODE_MAJEUR=22", builds[0])
        self.assertIn("--build-arg CLAUDE_CODE=2.1.328", builds[0])
        self.assertIn("-t myiafactory/agent ", builds[0])
        self.assertNotIn("--network", builds[0])                                          # la construction a besoin du réseau
        contexte = m.appels("contexte:")[0]
        for f in ("Dockerfile", "entree-agent.py", "pont"):
            self.assertIn(f, contexte)
        self.assertEqual(len(m.appels("docker network create myiafactory-agents")), 1, m.journal)
        self.assertTrue((m.etat / "reseau").exists())
        etiquette = (m.etat / "etiquette").read_text()
        self.assertEqual((m.home / MARQUEUR_AGENT).read_text().strip(), etiquette)
        sys.path.insert(0, str(RACINE.parent / "outils"))
        import serveur_installation
        self.assertEqual(etiquette, serveur_installation.empreinte_etape("agent_image"))   # même empreinte côté poste et côté serveur
        self.assertEqual(m.restes(m.home / ".myiafactory"), ["agent-image.version"])
        self.assertNotIn("curl", m.journal)

    def test_etape_agent_image_idempotente(self):
        m = self._monde()
        self.assertEqual(self._lancer(m)["statut"], "fait")
        marqueur = (m.home / MARQUEUR_AGENT).read_text()
        d = self._lancer(m)
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertEqual(len(m.appels("docker build")), 1, m.journal)                      # rien reconstruit
        self.assertEqual(len(m.appels("docker network create")), 1, m.journal)             # réseau déjà là : pas recréé
        self.assertEqual((m.home / MARQUEUR_AGENT).read_text(), marqueur)
        (m.etat / "etiquette").write_text("ubuntu=autre", newline="\n")                    # image d'une autre version : reconstruite
        self.assertEqual(self._lancer(m)["statut"], "fait")
        self.assertEqual(len(m.appels("docker build")), 2, m.journal)

    def test_etape_agent_image_blocages(self):
        m = self._monde()
        d = self._lancer(m, DISQUE_LIBRE_GO="1")
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("isque", d["detail"])
        d = self._lancer(m, SERVEUR_OVH_DIR=(m.t / "vide").as_posix())
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("introuvable", d["detail"])
        d = self._lancer(m, FAUX_BUILD_ECHEC="1")
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertIn("ligne-de-build-30", d["detail"])
        self.assertFalse((m.home / MARQUEUR_AGENT).exists())                               # pas de marqueur sans image
        d = self._lancer(m, FAUX_RESEAU_ECHEC="1")
        self.assertEqual(d["statut"], "bloque", d["detail"])
        self.assertIn("myiafactory-agents", d["detail"])
        self.assertFalse((m.home / MARQUEUR_AGENT).exists())                               # pas de marqueur sans réseau
        m.opt["FAUX_UTILISATEUR"] = "root"
        d = self._lancer(m)
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("root", d["detail"])

    def test_fichiers_de_l_entree_et_du_pont_peuvent_manquer_sans_planter_l_empreinte(self):
        # les deux fichiers arrivent aux tâches 2 et 7 : l'étape tolère leur absence (le Dockerfile, lui, est exigé)
        m = self._monde()
        copie = m.t / "serveur_ovh"
        (copie / "images" / "agent").mkdir(parents=True)
        shutil.copyfile(RACINE / "images" / "agent" / "Dockerfile", copie / "images" / "agent" / "Dockerfile")
        d = self._lancer(m, SERVEUR_OVH_DIR=copie.as_posix())
        self.assertEqual(d["statut"], "fait", d["detail"])
        self.assertRegex((m.home / MARQUEUR_AGENT).read_text().strip(), r";fichiers=[0-9a-f]{16}$")


class TestDockerfileAgent(unittest.TestCase):
    """L'image n'est jamais construite par un test : le Dockerfile est seulement lu."""
    DOCKERFILE = RACINE / "images" / "agent" / "Dockerfile"

    def setUp(self):
        self.texte = self.DOCKERFILE.read_text(encoding="utf-8")
        self.code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))
        self.instructions = re.sub(r"\\\n\s*", " ", self.code).splitlines()

    def test_image_agent_sans_curl_ni_wget(self):
        self.assertNotRegex(self.code, r"\bwget\b")
        avec_curl = [x for x in self.instructions if re.search(r"\bcurl\b", x)]
        self.assertEqual(len(avec_curl), 1, avec_curl)                    # une seule couche s'en sert...
        couche = avec_curl[0]
        self.assertTrue(couche.startswith("RUN "), couche)
        purge = re.search(r"apt-get purge\b[^&]*\bcurl\b", couche)
        self.assertIsNotNone(purge, couche)                               # ... et la purge en fin de couche
        self.assertGreater(purge.start(), couche.rindex("curl -"))        # après le dernier appel à curl
        self.assertGreater(purge.start(), couche.index("install -y --no-install-recommends nodejs"))
        # aucune couche suivante ne le réinstalle
        suite = self.instructions[self.instructions.index(couche) + 1:]
        self.assertFalse([x for x in suite if re.search(r"\b(curl|wget)\b", x)], suite)

    def test_dockerfile_agent_suit_versions_json(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        self.assertRegex(self.texte, rf"(?m)^ARG UBUNTU_TAG={re.escape(versions['base_ubuntu'].split(':')[1])}$")
        self.assertRegex(self.texte, rf"(?m)^ARG NODE_MAJEUR={re.escape(versions['node'])}$")
        self.assertRegex(self.texte, rf"(?m)^ARG CLAUDE_CODE={re.escape(versions['claude_code'])}$")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertRegex(script, rf'(?m)^V_CLAUDE_CODE="{re.escape(versions["claude_code"])}"$')
        etape = script[script.index("etape_agent_image()"):script.index("# --- Unity CLI")]
        for arg in ('--build-arg "UBUNTU_TAG=${V_UBUNTU#ubuntu:}"', '--build-arg "NODE_MAJEUR=$V_NODE"', '--build-arg "CLAUDE_CODE=$V_CLAUDE_CODE"'):
            self.assertIn(arg, etape)

    def test_entree_et_pont_copies_en_lecture_seule_pour_root(self):
        self.assertRegex(self.code, r"(?m)^COPY entree-agent\.py /usr/local/bin/entree-agent$")
        self.assertRegex(self.code, r"(?m)^COPY pont /usr/local/bin/pont$")
        chmod = [x for x in self.instructions if "chown root:root" in x]
        self.assertEqual(len(chmod), 1)
        self.assertIn("/usr/local/bin/entree-agent", chmod[0])
        self.assertIn("/usr/local/bin/pont", chmod[0])
        self.assertRegex(chmod[0], r"chmod 0?555 ")                       # lecture et exécution seules : jamais d'écriture
        self.assertNotRegex(self.code, r"(?mi)^(USER|VOLUME)\b")          # l'agent tourne sous l'identifiant de l'hôte (--user)


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnregistrerJeton(unittest.TestCase):
    """Le jeton de test est inventé ; le script ne doit jamais l'afficher. Git bash : les droits ne tiennent qu'à la création
    (umask), ce que le script fait."""
    SCRIPT_JETON = RACINE / "taches" / "enregistrer_jeton.sh"
    JETON = "jeton-de-test-0123456789ABCDEF"

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.home = Path(self._t.name)

    def _lancer(self, entree):
        # octets : le mode texte de Windows changerait « \n » en « \r\n » avant le script
        r = subprocess.run(["bash", self.SCRIPT_JETON.as_posix()], input=entree.encode("utf-8"), capture_output=True,
                           env=dict(os.environ, HOME=self.home.as_posix()), timeout=60)
        r.stdout, r.stderr = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
        return r

    def _mode(self, chemin):
        return subprocess.run(["stat", "-c", "%a", chemin.as_posix()], capture_output=True, text=True).stdout.strip()

    def _droits_persistants(self):
        """Faux sous Git bash sur Windows : les droits y sont simulés par processus et ne se relisent pas d'un processus à l'autre.
        Sur un vrai système de fichiers (le serveur), on vérifie les droits ; sinon seul le texte du script les garantit."""
        sonde = self.home / "sonde-droits"
        subprocess.run(["bash", "-c", 'umask 077; mkdir "$1"', "x", sonde.as_posix()], capture_output=True, timeout=30)
        return self._mode(sonde) == "700"

    def test_la_syntaxe_est_valide_et_la_lecture_se_fait_sans_echo(self):
        self.assertEqual(subprocess.run(["bash", "-n", self.SCRIPT_JETON.as_posix()], capture_output=True).returncode, 0)
        texte = self.SCRIPT_JETON.read_text(encoding="utf-8")
        # les droits sont posés à la création (umask) puis contrôlés : jamais un instant lisible par d'autres
        self.assertLess(texte.index("umask 077"), texte.index("mkdir -p"))
        self.assertIn('droits "$dossier" 700', texte)
        self.assertIn('droits "$tmp" 600', texte)
        self.assertLess(texte.index('droits "$tmp" 600'), texte.index('mv -f "$tmp"'))      # droits réglés AVANT d'atteindre « jeton »
        self.assertNotIn("\r", texte)
        self.assertIn("read -rs", texte)
        self.assertNotRegex(texte, r"\bset -x\b|\becho\b[^\n]*\$\{?jeton")

    def test_enregistrer_jeton_droits_et_sans_echo(self):
        for entree in (self.JETON + "\n", self.JETON):                    # avec ou sans retour à la ligne final
            with self.subTest(entree=entree):
                r = self._lancer(entree)
                self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
                self.assertNotIn(self.JETON, r.stdout + r.stderr)
                dossier = self.home / "agent-identifiants"
                if self._droits_persistants():
                    self.assertEqual(self._mode(dossier), "700")
                    self.assertEqual(self._mode(dossier / "jeton"), "600")
                self.assertEqual((dossier / "jeton").read_text(encoding="utf-8").strip(), self.JETON)
                self.assertEqual(sorted(x.name for x in dossier.iterdir()), ["jeton"])   # pas de fichier temporaire oublié
        autre = "un-autre-jeton-de-test-9876543210"
        self.assertEqual(self._lancer(autre + "\n").returncode, 0)        # remplacement
        self.assertEqual((self.home / "agent-identifiants" / "jeton").read_text(encoding="utf-8").strip(), autre)

    def test_enregistrer_jeton_refuse_vide_ou_hostile(self):
        refuses = ["", "\n", "court", "a" * 19 + "\n", "a" * 401 + "\n", "a" * 20 + " b\n", "a" * 20 + ";rm -rf /\n",
                   "$(touch pirate)" + "a" * 20 + "\n", "a" * 20 + '"\n', "a" * 20 + "\r\n", "é" * 20 + "\n", "a" * 20 + "`id`\n"]
        for entree in refuses:
            with self.subTest(entree=entree[:30]):
                r = self._lancer(entree)
                self.assertEqual(r.returncode, 2, (r.stdout, r.stderr))
                if entree.strip():
                    self.assertNotIn(entree.strip(), r.stdout + r.stderr)  # jamais de renvoi de la valeur saisie
                self.assertFalse((self.home / "agent-identifiants" / "jeton").exists())
                self.assertFalse((self.home / "pirate").exists())
        self.assertEqual(self._lancer(self.JETON + "\n").returncode, 0)
        self.assertEqual(self._lancer("\n").returncode, 2)                # un refus ne détruit pas le jeton en place
        self.assertEqual((self.home / "agent-identifiants" / "jeton").read_text(encoding="utf-8").strip(), self.JETON)
        self.assertEqual(sorted(x.name for x in (self.home / "agent-identifiants").iterdir()), ["jeton"])


class TestTexteDuScript(unittest.TestCase):
    def setUp(self):
        self.texte = SCRIPT.read_text(encoding="utf-8")

    def test_durcissement_verifie_seconde_session_avant_pare_feu(self):
        code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))
        debut = code.index("etape_durcissement()")
        appel = code.index("verifier_seconde_session", debut)
        self.assertLess(appel, code.index("ufw --force enable", debut))
        self.assertLess(appel, code.index("PasswordAuthentication no", debut))
        self.assertIn("ufw limit 22", code)
        self.assertIn("unattended-upgrades", code)

    def test_ufw_regle_puis_verifiee_puis_activee_sans_ignorer_l_echec(self):
        code = self.texte[self.texte.index("etape_durcissement()"):]
        regle = code.index("sudo ufw limit 22")
        verif = code.index("sudo ufw show added")
        activer = code.index("sudo ufw --force enable")
        self.assertLess(regle, verif)
        self.assertLess(verif, activer)
        self.assertIn("|| repondre bloque", code[regle:verif])
        self.assertIn("|| repondre bloque", code[verif:activer])

    def test_stdin_lu_uniquement_par_la_licence_et_le_bureau_distant(self):
        self.assertIn('if [ "$ETAPE" != "licence" ] && [ "$ETAPE" != "bureau_distant" ] && [ "$ETAPE" != "unity_licence_etat" ]; then'
                      '\n  exec </dev/null', self.texte)
        # l'état de la licence Unity (tâche 14i) : UNE ligne bornée, aucun secret, puis stdin fermé
        etat_licence = self.texte[self.texte.index("etape_unity_licence_etat()"):]
        self.assertLess(etat_licence.index("read -r -n 64 ligne"), etat_licence.index("exec </dev/null"))
        self.assertIn("ssh -n ", self.texte)
        self.assertEqual(self.texte.count("$(cat)"), 1)
        self.assertLess(self.texte.index("etape_licence()"), self.texte.index("$(cat)"))
        # Le mot de passe de session : une seule lecture, dans l'étape bureau_distant ; jamais passé à une commande en argument.
        bureau = self.texte[self.texte.index("etape_bureau_distant()"):self.texte.index("etape_etat()")]
        self.assertEqual(self.texte.count("IFS= read -r"), 1)
        self.assertIn("IFS= read -r", bureau)
        code = "\n".join(x for x in bureau.splitlines() if not x.lstrip().startswith("#"))
        self.assertIn("| sudo chpasswd", code)
        for ligne in code.splitlines():
            if '"$mdp"' in ligne:
                self.assertTrue(ligne.lstrip().startswith(("printf", "mdp=", "IFS= read", "if [")), ligne)

    def test_bureau_distant_ne_modifie_ni_ufw_ni_sshd(self):
        bureau = self.texte[self.texte.index("etape_bureau_distant()"):self.texte.index("etape_etat()")]
        code = "\n".join(x for x in bureau.splitlines() if not x.lstrip().startswith("#"))
        self.assertNotRegex(code, r"ufw (allow|limit|enable|--force|delete|deny|reload|reset)")
        self.assertNotIn("PasswordAuthentication", code)
        self.assertNotIn("sshd_config", code)
        self.assertIn("127.0.0.1:3389", code)

    def test_licence_exige_une_preuve_et_ne_fait_pas_confiance_au_code_de_sortie(self):
        licence = self.texte[self.texte.index("etape_licence()"):self.texte.index("etape_etat()")]
        self.assertIn("-logFile -", licence)
        self.assertIn("|| true", licence)
        self.assertIn("grep -qiE", licence)
        self.assertIn("Unity_lic.ulf", licence)

    def test_unity_epingle_sur_la_version_du_projet_avec_module_android(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(versions["unity_gameci"], "unityci/editor:ubuntu-6000.6.7f1-android-4.0.0")

    def test_images_reconstruites_si_les_versions_changent(self):
        self.assertIn('--label "versions=$empreinte"', self.texte)
        self.assertIn('"$actuelle" != "$empreinte"', self.texte)
        self.assertEqual(self.texte.count("--build-arg"), 15)          # + CMDLINE_TOOLS de l'émulateur, + 3 d'agent_image, + 2 de tests_image

    def test_dockerfile_script_et_versions_json_concordent(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))

        def script(nom):
            m = re.search(rf'^{nom}="([^"]*)"', self.texte, re.M)
            self.assertIsNotNone(m, nom)
            return m.group(1)

        def arg(dockerfile, nom):
            m = re.search(rf"^ARG {nom}=(\S+)", (RACINE / "images" / dockerfile / "Dockerfile").read_text(encoding="utf-8"), re.M)
            self.assertIsNotNone(m, f"{dockerfile} {nom}")
            return m.group(1)

        self.assertEqual(script("V_UBUNTU"), versions["base_ubuntu"])
        self.assertEqual(script("V_BUILD_TOOLS"), versions["android_build_tools"])
        self.assertEqual(script("V_PLATEFORME"), versions["android_plateforme"])
        self.assertEqual(script("V_CMDLINE_TOOLS"), versions["android_cmdline_tools"])
        self.assertEqual(script("V_GRADLE"), versions["gradle"])
        self.assertEqual(script("V_NODE"), versions["node"])
        self.assertEqual(script("V_CLAUDE_CODE"), versions["claude_code"])
        tag = versions["base_ubuntu"].split(":")[1]
        for image in ("android", "agent", "emulateur"):
            self.assertEqual(arg(image, "UBUNTU_TAG"), tag)
        self.assertEqual(arg("android", "BUILD_TOOLS"), versions["android_build_tools"])
        self.assertEqual(arg("android", "PLATEFORME"), versions["android_plateforme"])
        self.assertEqual(arg("android", "CMDLINE_TOOLS"), versions["android_cmdline_tools"])
        self.assertEqual(arg("android", "GRADLE"), versions["gradle"])
        self.assertEqual(arg("agent", "NODE_MAJEUR"), versions["node"])
        self.assertEqual(arg("agent", "CLAUDE_CODE"), versions["claude_code"])

    def test_node_lts_22(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(versions["node"], "22")
        self.assertIn('V_NODE="22"', self.texte)

    def test_licence_non_lue_dans_argv(self):
        self.assertNotIn("--licence", self.texte)
        self.assertIn("cat", self.texte)
        self.assertIn("stdin", self.texte)

    def test_versions_epinglees(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        dockerfiles = [RACINE / "images/android/Dockerfile", RACINE / "images/agent/Dockerfile", RACINE / "images/emulateur/Dockerfile"]
        for f in [RACINE / "versions.json", SCRIPT] + dockerfiles:
            # Aucune étiquette flottante ; le nom de fichier du téléchargement Google (`..._latest.zip`) n'est pas une étiquette.
            self.assertNotRegex(f.read_text(encoding="utf-8").lower(), r"[:=\"' ]latest\b(?!\.zip)", f.name)
        for d in dockerfiles:
            origines = [x for x in d.read_text(encoding="utf-8").splitlines() if x.startswith("FROM")]
            self.assertTrue(origines, d)
            for ligne in origines:
                self.assertRegex(ligne, r"FROM \S+:\S+", ligne)
        self.assertIn(versions["unity_gameci"], self.texte)

    def test_sdk_android_script_et_versions_json_concordent(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        sdk = versions["android_sdk"]

        def script(nom):
            m = re.search(rf'^{nom}="([^"]*)"', self.texte, re.M)
            self.assertIsNotNone(m, nom)
            return m.group(1)

        self.assertEqual(script("V_SDK_PLATEFORME"), sdk["platform"])
        self.assertEqual(script("V_SDK_BUILD_TOOLS"), sdk["build_tools"])
        self.assertEqual(script("V_SDK_IMAGE_EMULATEUR"), sdk["emulator_image"])
        self.assertIn("unity.com/install.sh", versions["unity_cli"])

    def test_usage_et_dispatch_listent_les_nouvelles_etapes(self):
        usage = next(x for x in self.texte.splitlines() if x.startswith("# Usage"))
        for etape in NOUVELLES:
            self.assertIn(etape, usage)
            self.assertIn(f"  {etape}) etape_{etape} ;;", self.texte)

    def test_unity_cli_n_utilise_jamais_curl_pipe_bash(self):
        code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))
        self.assertNotRegex(code, r"\|\s*(sudo\s+)?(ba|z)?sh\b")
        unity = code[code.index("etape_unity_cli()"):code.index("etape_etat()")]
        self.assertIn('bash "$tmp"', unity)
        self.assertLess(unity.index("head -c 2"), unity.index('bash "$tmp"'))

    def test_unity_cli_sans_editeur_et_installeur_sans_etape_finale(self):
        self.assertNotIn("UNITY_EDITEUR", self.texte)
        self.assertNotIn("whoami", self.texte)
        self.assertIn('UNITY_CLI_SKIP_SETUP=1 bash "$tmp"', self.texte)

    def test_mv_sur_latest_est_sans_imbrication_et_apt_sans_dpkg_s(self):
        self.assertIn('mv -T "$travail/extrait/cmdline-tools" "$dest/latest"', self.texte)
        helper = self.texte[self.texte.index("assurer_paquets()"):self.texte.index("etape_docker()")]
        self.assertIn("dpkg-query -W -f='${db:Status-Status}'", helper)
        self.assertNotIn("dpkg -s", helper)
        self.assertIn("DPkg::Lock::Timeout=120", helper)

    def test_nouvelles_etapes_sans_set_e(self):
        code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))
        self.assertNotRegex(code, r"(?m)^\s*set -[a-z]*e")

    def test_fins_de_ligne_lf(self):
        self.assertNotIn(b"\r", SCRIPT.read_bytes())


if __name__ == "__main__":
    unittest.main()
