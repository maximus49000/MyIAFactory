"""Script de mise en place du serveur (`serveur_ovh/mise_en_place.sh`) : lancé avec le bash du poste, en `--simuler`."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent / "serveur_ovh"
SCRIPT = RACINE / "mise_en_place.sh"
ETAPES = ("durcissement", "docker", "images", "licence", "etat")
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
GPG_FACTICE = r'''mode=""; out=""; entree=""
while [ $# -gt 0 ]; do case "$1" in --dearmor) mode=d; shift;; --show-keys) mode=s; shift;; -o) out="$2"; shift 2;; --*) shift;; *) entree="$1"; shift;; esac; done
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
                cle_mozilla="ok", cle_unity="ok", apt_avant=None):
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
                         f'case "$1" in chpasswd) cat > "{recu.as_posix()}";; ufw|sshd|apt-get|curl|gpg|mv|rm|chmod|tee|install) "$@";; *) exit 0;; esac'),
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
            corps["apt-get"] = '[ "$1" = update ] && [ "%s" = non ] && exit 1\nexit 0' % ("oui" if maj_ok else "non")
            for nom in ("apt-get", "systemctl", "usermod", "chpasswd"):
                corps.setdefault(nom, "exit 0")
            for nom, texte in corps.items():
                if nom not in ("sudo", "ufw", "sshd", "apt-cache"):
                    texte = f'echo "{nom} $@" >> "{journal.as_posix()}"\n' + texte
                (faux / nom).write_text("#!/bin/sh\n" + texte + "\n", newline="\n")
                (faux / nom).chmod(0o755)
            envs = dict(APT_RACINE=(t / "apt").as_posix(), CLE_MOZILLA=cle_mozilla, CLE_UNITY=cle_unity)
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
                    for liste in self.LISTES:
                        self.assertNotIn(liste, self.apt)
                    self.assertEqual([x for x in self.apt if x.endswith((".tmp", ".brut"))], [])
                    self.assertEqual(recu, "")
                    self.assertNotIn("firefox unityhub", appels)

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

    def _etat_avec_faux(self, images_absentes=(), volumes_ok=True):
        """Lance l'étape etat (réelle) avec de faux binaires : serveur durci, Docker présent, images au choix."""
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            faux = t / "bin"
            faux.mkdir()
            absentes = " ".join(f'*"{i}"*) exit 1;;' for i in images_absentes)
            corps = {
                "sudo": 'while case "$1" in *=*) true;; *) false;; esac; do shift; done\nexec "$@"',
                "sshd": 'echo "passwordauthentication no"',
                "ufw": 'echo "Status: active"',
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

    def test_etat_exige_les_trois_images(self):
        self.assertEqual(self._etat_avec_faux()["statut"], "fait")
        for absente in ("unityci/editor", "myiafactory/android", "myiafactory/agent"):
            with self.subTest(absente=absente):
                d = self._etat_avec_faux(images_absentes=(absente,))
                self.assertEqual(d["statut"], "a_faire")
                self.assertIn("images", d["detail"])


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
        self.assertIn('if [ "$ETAPE" != "licence" ] && [ "$ETAPE" != "bureau_distant" ]; then\n  exec </dev/null', self.texte)
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
        self.assertEqual(self.texte.count("--build-arg"), 8)

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
        for image in ("android", "agent"):
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
        dockerfiles = [RACINE / "images/android/Dockerfile", RACINE / "images/agent/Dockerfile"]
        for f in [RACINE / "versions.json", SCRIPT] + dockerfiles:
            # Aucune étiquette flottante ; le nom de fichier du téléchargement Google (`..._latest.zip`) n'est pas une étiquette.
            self.assertNotRegex(f.read_text(encoding="utf-8").lower(), r"[:=\"' ]latest\b(?!\.zip)", f.name)
        for d in dockerfiles:
            origines = [x for x in d.read_text(encoding="utf-8").splitlines() if x.startswith("FROM")]
            self.assertTrue(origines, d)
            for ligne in origines:
                self.assertRegex(ligne, r"FROM \S+:\S+", ligne)
        self.assertIn(versions["unity_gameci"], self.texte)

    def test_fins_de_ligne_lf(self):
        self.assertNotIn(b"\r", SCRIPT.read_bytes())


if __name__ == "__main__":
    unittest.main()
