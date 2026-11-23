"""Pont d'actions de l'émulateur (`serveur_ovh/taches/pont.sh`) : lancé avec le bash du poste, `adb`, `emulator` et `sleep`
factices dans le PATH (ils journalisent leurs arguments). Les arguments passent par un fichier séparé par des octets nuls :
ils arrivent au pont octet pour octet (retours à la ligne, guillemets, `$(...)`), sans le découpage de la ligne de commande
Windows ni l'expansion de motifs du bash de Git."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "serveur_ovh" / "taches" / "pont.sh"
CLES = {"ok", "verbe", "detail"}
PAQUET = "com.exemple.app"

ADB_FACTICE = r'''echo "adb $*" >> "$FAUX_JOURNAL"
[ -n "${FAUX_EFFACER_ACTIVITE:-}" ] && rm -f "$PONT_SORTIE/.activite"
[ -n "${FAUX_ADB_ECHEC:-}" ] && exit 1
if [ -n "${FAUX_VERIF_FD9:-}" ] && [ -e /proc/self/fd/9 ]; then echo "adb a herite du verrou" >> "$FAUX_JOURNAL"; exit 1; fi
[ -n "${FAUX_ADB_LENT:-}" ] && exec /usr/bin/sleep "$FAUX_ADB_LENT"
case "$1" in
  exec-out) [ -n "${FAUX_CAPTURE_LENTE:-}" ] && /usr/bin/sleep "$FAUX_CAPTURE_LENTE"; printf '\211PNG\r\n\032\n'; head -c "${FAUX_PNG_OCTETS:-100}" /dev/zero ;;
  logcat) [ -n "${FAUX_LOGCAT:-}" ] && cat "$FAUX_LOGCAT" ;;
  install) echo Success ;;
  pull) if [ -n "${FAUX_MP4_FAUX:-}" ]; then printf 'PAS UNE VIDEO' > "$3"
        else printf '\000\000\000\030ftypisom' > "$3"; head -c "${FAUX_MP4_OCTETS:-200}" /dev/zero >> "$3"; fi ;;
  shell) case "$2 $3" in
           "getprop sys.boot_completed") echo 1 ;;
           "pm list") printf '%s\n' "${FAUX_PAQUETS-package:com.exemple.app}" ;;
           "monkey -p") echo "Events injected: 1" ;;
           # screenrecord : tourne jusqu'au SIGINT (pkill -2 côté appareil), comme le vrai
           "screenrecord --size") [ -n "${FAUX_FILM_MEURT:-}" ] && exit 1; [ -n "${FAUX_FILM_COURT:-}" ] && exit 0
                                  echo $$ > "$FAUX_FILM_PID"; exec /usr/bin/sleep 300 ;;
           "pkill -2") [ -f "$FAUX_FILM_PID" ] && kill "$(cat "$FAUX_FILM_PID")" 2>/dev/null; rm -f "$FAUX_FILM_PID" ;;
         esac ;;
esac
exit 0'''
# ffmpeg factice : écrit FAUX_IMAGES (3) images PNG selon le motif de sortie (dernier argument, « ...-%03d.png »).
FFMPEG_FACTICE = r'''echo "ffmpeg $*" >> "$FAUX_JOURNAL"
[ -n "${FAUX_FFMPEG_ECHEC:-}" ] && exit 1
sortie=""; for a in "$@"; do sortie="$a"; done
i=1; while [ "$i" -le "${FAUX_IMAGES:-3}" ]; do f=$(printf "$sortie" "$i"); printf '\211PNG\r\n\032\nimage' > "$f"; i=$((i + 1)); done
exit 0'''
# Resté vivant, il garde « emulator » dans sa ligne de commande (/proc/<pid>/cmdline), comme le vrai.
EMULATEUR_FACTICE = ('echo "emulator $*" >> "$FAUX_JOURNAL"\n'
                     'if [ -n "${FAUX_VERIF_FD9:-}" ] && [ -e /proc/self/fd/9 ]; then echo "emulator a herite du verrou" >> "$FAUX_JOURNAL"; fi\n'
                     '[ -n "${FAUX_EMU_MEURT:-}" ] && exit 0\n'
                     'exec -a emulator-factice /usr/bin/sleep 60')
SLEEP_FACTICE = 'echo "sleep $*" >> "$FAUX_JOURNAL"\nexit 0'
# Lit les arguments séparés par des octets nuls puis lance le pont avec exactement ces arguments.
PILOTE = 'mapfile -d "" -t A < "$1"; exec bash "$2" "${A[@]}"'
LIGNE_JOURNAL = re.compile(r"^\S+( .*)? \d+ms$")


def posix(chemin):
    """Chemin absolu tel que le voit bash (/c/... sous Git bash) : le pont refuse un PONT_SORTIE non absolu."""
    if shutil.which("cygpath"):
        return subprocess.run(["cygpath", "-u", str(chemin)], capture_output=True, text=True, check=True).stdout.strip()
    return Path(chemin).as_posix()


def bash(script, *args, env=None):
    return subprocess.run(["bash", "-c", script, "bash", *args], capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, **(env or {})))


class Banc:
    """Un conteneur simulé : dossiers sortie/ et entree/app.apk côte à côte, faux outils journalisant leurs appels."""

    def __init__(self, **env):
        self.env = env

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        t = self.t = Path(self._t.name)
        self.bin, self.sortie, self.entree = t / "bin", t / "sortie", t / "entree"
        for d in (self.bin, self.sortie, self.entree):
            d.mkdir()
        (self.entree / "app.apk").write_bytes(b"PK\x03\x04apk-factice")
        self.fichier_journal = t / "appels.txt"
        for nom, corps in (("adb", ADB_FACTICE), ("emulator", EMULATEUR_FACTICE), ("sleep", SLEEP_FACTICE),
                           ("ffmpeg", FFMPEG_FACTICE)):
            (self.bin / nom).write_text("#!/usr/bin/env bash\n" + corps + "\n", newline="\n")   # bash : exec -a
            (self.bin / nom).chmod(0o755)
        self.n = 0
        self.sortie_posix = posix(self.sortie)
        return self

    def __exit__(self, *a):
        for pid in (self.sortie / "emulateur.pid", self.t / "film.pid"):
            if pid.exists():
                bash('kill -9 "$(cat "$1")" 2>/dev/null; exit 0', pid.as_posix())
        time.sleep(0.2)
        self._t.cleanup()

    def faux(self, nom, corps):
        (self.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
        (self.bin / nom).chmod(0o755)

    def lien(self, cible, lien):
        """Lien symbolique créé par bash (vu comme tel par le pont) ; le test est ignoré si le système ne sait pas en faire."""
        # Sous Git bash, `ln -s` copie par défaut ; winsymlinks:lnk fait de vrais liens (vus par [ -L ]) sans droit particulier.
        r = bash('ln -s "$1" "$2" && [ -L "$2" ]', posix(cible), posix(lien), env={"MSYS": "winsymlinks:lnk"})
        if r.returncode != 0:
            raise unittest.SkipTest("liens symboliques non pris en charge")

    def logcat(self, texte):
        f = self.t / "logcat.txt"
        f.write_bytes(texte if isinstance(texte, bytes) else texte.encode("utf-8"))
        self.env["FAUX_LOGCAT"] = f.as_posix()

    def _preparer(self, args, env):
        self.n += 1
        fichier_args = self.t / f"args{self.n}.bin"
        fichier_args.write_bytes(b"".join(a.encode("utf-8") + b"\0" for a in args))
        e = dict(os.environ, PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"], PONT_SORTIE=self.sortie_posix,
                 FAUX_JOURNAL=self.fichier_journal.as_posix(), FAUX_FILM_PID=(self.t / "film.pid").as_posix())
        for nom in ("PONT_PAQUET", "PONT_ADB", "PONT_EMULATEUR", "PONT_AVD", "PONT_FFMPEG"):
            e.pop(nom, None)
        e.update(self.env)
        e.update(env)
        return ["bash", "-c", PILOTE, "pilote", fichier_args.as_posix(), SCRIPT.as_posix()], e

    def lancer_fond(self, *args, **env):
        commande, e = self._preparer(args, env)
        return subprocess.Popen(commande, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", env=e)

    def lancer(self, *args, **env):
        """Rend (code, objet JSON) ; exige UNE seule ligne JSON sur la sortie standard."""
        commande, e = self._preparer(args, env)
        r = subprocess.run(commande, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", env=e, timeout=60)
        self.derniere = r
        lignes = [x for x in r.stdout.splitlines() if x.strip()]
        assert len(lignes) == 1, (r.returncode, r.stdout, r.stderr)
        d = json.loads(lignes[0])
        assert set(d) == CLES, d
        assert isinstance(d["ok"], bool) and isinstance(d["verbe"], str) and isinstance(d["detail"], str), d
        assert d["ok"] == (r.returncode == 0), (r.returncode, d)
        return r.returncode, d

    @property
    def appels(self):
        return self.fichier_journal.read_text(encoding="utf-8").splitlines() if self.fichier_journal.exists() else []

    def oublier_appels(self):
        if self.fichier_journal.exists():
            self.fichier_journal.unlink()

    @property
    def lignes_pont_log(self):
        f = self.sortie / "pont.log"
        return f.read_text(encoding="utf-8").splitlines() if f.exists() else []

    def arbre(self):
        """Tous les fichiers du banc, sauf pont.log (seule écriture permise pour un appel refusé)."""
        return sorted(p.relative_to(self.t).as_posix() for p in self.t.rglob("*")
                      if p != self.sortie / "pont.log" and p != self.fichier_journal and not p.name.startswith("args"))

    def captures(self):
        d = self.sortie / "captures"
        return sorted(p.name for p in d.iterdir()) if d.exists() else []


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestPont(unittest.TestCase):
    def test_verbe_inconnu_refuse(self):
        with Banc() as b:
            for verbe in ("rm", "", "TOUCHER", "toucher;ls", "sh", "eval", "demarrer\n", "../pont"):
                with self.subTest(verbe=verbe):
                    code, d = b.lancer(verbe, "1", "2")
                    self.assertEqual(code, 2)
                    self.assertFalse(d["ok"])
                    self.assertIn("inconnu", d["detail"])
            self.assertEqual(b.appels, [])

    def test_arguments_hostiles_refuses_sans_rien_executer(self):
        communs = [";", "$(x)", "`x`", "a\nb", "", "$(touch ../pwn)", "*", "a;b", "x'y", "a|b",
                   "&", ">", "a\r", "\r", "--", "-s", "?", "[", "a&b", "a>b"]
        cas = {
            "toucher": [[h, "10"] for h in communs + ["..", "-1", "99999", "1.5", " 1"]] + [["10", h] for h in ("-1", "99999")]
                       + [["10"], ["10", "20", "30"]],
            "glisser": [["1", "2", "3", h] for h in communs + ["..", "-1", "99999"]] + [["1", "2", "3"]],
            "attendre": [[h] for h in communs + ["..", "-1", "99999", "121", "1000"]],
            "capturer": [[h] for h in communs + ["..", "../x", "a/b", "A", "x.png", "a" * 41]] + [["a", "b"]],
            "texte": [[h] for h in communs + ["a" * 61, "a/b", "é", "50%"]],
            "touche": [[h] for h in communs + ["..", "-1", "99999", "power", "retour "]],
            "journal": [[h] for h in communs + ["a b", "a/b", "a" * 61]] + [["a", "b"]],
            "installer": [["/etc/passwd"], ["../entree/app.apk"], [";"], [""]],
            "demarrer": [["-1"]], "lancer": [[".."]], "arreter": [["99999"]],
            "filmer": [[h] for h in communs + ["..", "../x", "a/b", "A", "x.mp4", "a" * 41, "con", "nul"]]
                      + [["demo", h] for h in communs + ["0", "181", "030", "-1", "1.5", "999"]] + [["a", "30", "x"]],
            "finfilm": [["demo"], [";"], ["--"]],
        }
        with Banc() as b:
            avant = b.arbre()
            for verbe, listes in cas.items():
                for args in listes:
                    with self.subTest(verbe=verbe, args=args):
                        code, d = b.lancer(verbe, *args)
                        self.assertEqual(code, 2, d)
                        self.assertEqual(d["verbe"], verbe)
            self.assertEqual(b.appels, [])            # ni adb, ni emulator, ni sleep
            self.assertEqual(b.arbre(), avant)        # aucune écriture hors pont.log (pas même captures/)
            self.assertFalse((b.t / "pwn").exists())

    def test_toucher_appelle_adb_input_tap(self):
        with Banc() as b:
            code, d = b.lancer("toucher", "540", "1200")
            self.assertEqual(code, 0, d)
            self.assertEqual(b.appels, ["adb shell input tap 540 1200"])
            b.oublier_appels()
            code, _ = b.lancer("toucher", "0", "9999")
            self.assertEqual(code, 0)
            self.assertEqual(b.appels, ["adb shell input tap 0 9999"])

    def test_glisser_et_touche_bornes(self):
        with Banc() as b:
            code, _ = b.lancer("glisser", "100", "1500", "100", "300")
            self.assertEqual(code, 0)
            self.assertEqual(b.appels, ["adb shell input swipe 100 1500 100 300"])
            for nom, valeur in (("retour", "4"), ("accueil", "3"), ("menu", "82")):
                with self.subTest(touche=nom):
                    b.oublier_appels()
                    code, _ = b.lancer("touche", nom)
                    self.assertEqual(code, 0)
                    self.assertEqual(b.appels, [f"adb shell input keyevent {valeur}"])
            b.oublier_appels()
            for args in (["100", "1500", "100", "10000"], ["1", "2", "3", "4", "5"]):
                self.assertEqual(b.lancer("glisser", *args)[0], 2)
            self.assertEqual(b.lancer("touche", "KEYCODE_POWER")[0], 2)
            self.assertEqual(b.appels, [])

    def test_texte_remplace_les_espaces_pour_input_text(self):
        with Banc() as b:
            code, _ = b.lancer("texte", "Bonjour le monde, 3.5_kg-x")
            self.assertEqual(code, 0)
            self.assertEqual(b.appels, ["adb shell input text Bonjour%sle%smonde,%s3.5_kg-x"])

    def test_attendre_borne_a_120(self):
        with Banc() as b:
            for s in ("0", "7", "120"):
                b.oublier_appels()
                self.assertEqual(b.lancer("attendre", s)[0], 0)
                self.assertEqual(b.appels, [f"sleep {int(s)}"])
            b.oublier_appels()
            self.assertEqual(b.lancer("attendre", "121")[0], 2)
            self.assertEqual(b.appels, [])

    def test_capturer_ecrit_un_png_et_refuse_un_nom_pris(self):
        with Banc() as b:
            code, d = b.lancer("capturer", "accueil-1")
            self.assertEqual(code, 0, d)
            png = b.sortie / "captures" / "accueil-1.png"
            self.assertTrue(png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(len(png.read_bytes()), 108)          # binaire intact
            self.assertIn("captures/accueil-1.png", d["detail"])
            self.assertEqual(b.appels, ["adb exec-out screencap -p"])
            b.oublier_appels()
            code, d = b.lancer("capturer", "accueil-1")
            self.assertEqual(code, 2, d)
            self.assertIn("déjà", d["detail"])
            self.assertEqual(b.appels, [])
            self.assertEqual(b.captures(), ["accueil-1.png"])

    def test_capture_qui_n_est_pas_un_png_est_un_echec_sans_fichier(self):
        with Banc(FAUX_ADB_ECHEC="1") as b:
            code, _ = b.lancer("capturer", "rate")
            self.assertEqual(code, 4)
            self.assertEqual(b.captures(), [])

    def test_limite_de_captures_donne_3(self):
        with Banc(PONT_CAPTURES="2") as b:
            self.assertEqual(b.lancer("capturer", "a")[0], 0)
            self.assertEqual(b.lancer("capturer", "b")[0], 0)
            code, d = b.lancer("capturer", "c")
            self.assertEqual(code, 3, d)
            self.assertIn("imite", d["detail"])
            self.assertEqual(len([x for x in b.appels if "screencap" in x]), 2)   # la troisième n'a pas été prise
            self.assertEqual(b.captures(), ["a.png", "b.png"])

    def test_limite_d_octets_donne_3(self):
        # 108 octets par capture : la première tient dans 150, la seconde dépasserait (216) et n'est pas gardée.
        with Banc(PONT_OCTETS="150") as b:
            self.assertEqual(b.lancer("capturer", "a")[0], 0)
            code, d = b.lancer("capturer", "b")
            self.assertEqual(code, 3, d)
            self.assertEqual(b.captures(), ["a.png"])           # ni b.png, ni temporaire
        # déjà au-delà avant de capturer : adb n'est pas appelé
        with Banc(PONT_OCTETS="100") as b:
            self.assertEqual(b.lancer("capturer", "a")[0], 3)
            self.assertEqual(b.captures(), [])
            (b.sortie / "captures").mkdir(exist_ok=True)
            (b.sortie / "captures" / "ancienne.png").write_bytes(b"x" * 100)
            b.oublier_appels()
            self.assertEqual(b.lancer("capturer", "b")[0], 3)
            self.assertEqual(b.appels, [])

    def test_limites_mal_formees_refusees(self):
        with Banc(PONT_CAPTURES="1;x") as b:
            self.assertEqual(b.lancer("capturer", "a")[0], 4)
            self.assertEqual(b.appels, [])

    def test_journal_borne_a_200_lignes(self):
        with Banc() as b:
            b.logcat("".join(f"I Test: ligne {i} {'pair' if i % 2 == 0 else 'autre'}\n" for i in range(500)))
            code, d = b.lancer("journal")
            self.assertEqual(code, 0, d)
            lignes = d["detail"].splitlines()
            self.assertEqual(len(lignes), 200)
            self.assertEqual(lignes[-1], "I Test: ligne 499 autre")
            self.assertEqual(b.appels, ["adb logcat -d"])
            code, d = b.lancer("journal", "pair")
            lignes = d["detail"].splitlines()
            self.assertEqual(len(lignes), 200)
            self.assertTrue(all(x.endswith(" pair") for x in lignes), lignes)
            self.assertEqual(lignes[-1], "I Test: ligne 498 pair")
            code, d = b.lancer("journal", "introuvable")
            self.assertEqual((code, d["detail"]), (0, ""))

    def test_installer_chemin_fixe_seulement(self):
        with Banc() as b:
            for args in (["/etc/passwd"], ["../entree/app.apk"], [(b.entree / "app.apk").as_posix()]):
                with self.subTest(args=args):
                    self.assertEqual(b.lancer("installer", *args)[0], 2)
            self.assertEqual(b.appels, [])
            code, d = b.lancer("installer")
            self.assertEqual(code, 0, d)
            installs = [x for x in b.appels if x.startswith("adb install")]
            self.assertEqual(installs, [f"adb install -r {b.sortie_posix}/../entree/app.apk"])
            self.assertIn(PAQUET, d["detail"])
            self.assertEqual((b.sortie / ".paquet").read_text().strip(), PAQUET)
            (b.entree / "app.apk").unlink()
            b.oublier_appels()
            self.assertEqual(b.lancer("installer")[0], 4)
            self.assertEqual([x for x in b.appels if x.startswith("adb install")], [])

    def test_installer_refuse_un_paquet_ambigu_ou_hostile(self):
        for paquets in ("package:com.a\npackage:com.b", "package:com.x;reboot", ""):
            with self.subTest(paquets=paquets), Banc(FAUX_PAQUETS=paquets) as b:
                self.assertEqual(b.lancer("installer")[0], 4)
                self.assertFalse((b.sortie / ".paquet").exists())

    def test_demarrer_lancer_arreter_appellent_les_outils(self):
        with Banc(PONT_AVD="emu34") as b:
            code, d = b.lancer("demarrer")
            self.assertEqual(code, 0, d)
            emus = [x for x in b.appels if x.startswith("emulator ")]
            self.assertEqual(len(emus), 1, b.appels)
            self.assertRegex(emus[0], r"^emulator -avd emu34 .*-no-window.*-no-audio")
            self.assertIn("adb shell getprop sys.boot_completed", b.appels)
            b.oublier_appels()
            self.assertEqual(b.lancer("lancer")[0], 4)            # paquet inconnu : installer d'abord
            self.assertEqual(b.lancer("installer")[0], 0)
            b.oublier_appels()
            self.assertEqual(b.lancer("lancer")[0], 0)
            self.assertEqual(b.appels, [f"adb shell monkey -p {PAQUET} -c android.intent.category.LAUNCHER 1"])
            b.oublier_appels()
            self.assertEqual(b.lancer("arreter")[0], 0)
            self.assertIn("adb emu kill", b.appels)
        with Banc(PONT_AVD="../x") as b:
            self.assertEqual(b.lancer("demarrer")[0], 4)
            self.assertEqual(b.appels, [])

    def test_plantage_detecte_dans_le_journal(self):
        fatal = ("E AndroidRuntime: FATAL EXCEPTION: main\n"
                 "E AndroidRuntime: Process: {p}, PID: 4242\n"
                 "E AndroidRuntime: java.lang.NullPointerException\n")
        anr = "E ActivityManager: ANR in {p} ({p}/.Principale)\n"
        for nom, texte, attendu in (("fatal", fatal.format(p=PAQUET), True), ("anr", anr.format(p=PAQUET), True),
                                    ("fatal autre", fatal.format(p="com.autre"), False),
                                    ("fatal prefixe", fatal.format(p=PAQUET + "plus"), False),
                                    ("anr autre", anr.format(p=PAQUET + ".service"), False), ("rien", "I Test: tout va bien\n", False)):
            for source in ("env", "installer"):
                with self.subTest(cas=nom, paquet=source), Banc() as b:
                    b.logcat("I Test: avant\n" + texte + "I Test: apres\n")
                    if source == "env":
                        b.env["PONT_PAQUET"] = PAQUET
                    else:
                        self.assertEqual(b.lancer("installer")[0], 0)
                    self.assertEqual(b.lancer("journal", "Test")[0], 0)
                    plantage = b.sortie / "plantage.txt"
                    self.assertEqual(plantage.exists(), attendu, nom)
                    if attendu:
                        contenu = plantage.read_text()
                        self.assertIn("FATAL EXCEPTION" if nom == "fatal" else "ANR in", contenu)
                        self.assertIn(PAQUET, contenu)
        with Banc(PONT_PAQUET=PAQUET) as b:                 # l'arrêt relit aussi le journal
            b.logcat(fatal.format(p=PAQUET))
            self.assertEqual(b.lancer("arreter")[0], 0)
            self.assertTrue((b.sortie / "plantage.txt").exists())
        with Banc() as b:                                    # paquet inconnu : pas de détection, pas d'erreur
            b.logcat(fatal.format(p=PAQUET))
            self.assertEqual(b.lancer("journal")[0], 0)
            self.assertFalse((b.sortie / "plantage.txt").exists())

    def test_chaque_appel_laisse_une_ligne_de_journal(self):
        with Banc(PONT_CAPTURES="1") as b:
            appels = [("toucher", "10", "20"), ("toucher", "a\nb", "2"), ("inconnu",), ("capturer", "a"), ("capturer", "b"),
                      ("texte", "un deux"), ("", ), ("journal",)]
            for args in appels:
                b.lancer(*args)
            lignes = b.lignes_pont_log
            self.assertEqual(len(lignes), len(appels), lignes)
            for ligne in lignes:
                self.assertRegex(ligne, LIGNE_JOURNAL)
            self.assertRegex(lignes[0], r"^toucher 10 20 \d+ms$")
            self.assertRegex(lignes[1], r"^toucher a\?b 2 \d+ms$")         # le retour à la ligne ne forge pas de ligne
            self.assertRegex(lignes[5], r"^texte un deux \d+ms$")

    def test_activite_touchee_au_debut_de_chaque_verbe_valide(self):
        with Banc() as b:
            activite = b.sortie / ".activite"
            self.assertEqual(b.lancer("toucher", "10", "20")[0], 0)
            self.assertTrue(activite.is_file())
            self.assertEqual(activite.stat().st_size, 0)                  # mtime seulement, aucun contenu
            activite.write_text("garde", newline="\n")
            self.assertEqual(b.lancer("attendre", "0")[0], 0)
            self.assertEqual(activite.read_text(), "garde")               # un fichier existant n'est jamais tronqué (touch, pas « : > »)
            os.utime(activite, (1000000, 1000000))
            self.assertEqual(b.lancer("attendre", "0")[0], 0)
            self.assertGreater(activite.stat().st_mtime, 1000000)         # chaque verbe valide le rafraîchit
            activite.unlink()
            self.assertEqual(b.lancer("toucher", "a;b", "2")[0], 2)       # un verbe refusé n'est pas de l'activité
            self.assertFalse(activite.exists())

    def test_activite_aussi_a_la_fin_de_chaque_verbe(self):
        with Banc() as b:
            activite = b.sortie / ".activite"
            # le faux adb efface .activite pendant le verbe : seule une retouche en FIN de verbe la ramène (verbe long = activité)
            self.assertEqual(b.lancer("toucher", "10", "20", FAUX_EFFACER_ACTIVITE="1")[0], 0)
            self.assertTrue(activite.is_file())
            self.assertEqual(activite.stat().st_size, 0)

    def _lancer_borne(self, b, *args, delai=15):
        """Un verbe avec garde dure : sortie dans des FICHIERS (aucun tube qu'un petit-enfant bloqué garderait ouvert), attente bornée,
        arbre de processus tué puis échec franc si le verbe ne rend pas la main (jamais un blocage de la campagne)."""
        commande, e = b._preparer(args, {})
        with open(b.t / "borne.out", "wb") as sortie:
            p = subprocess.Popen(commande, stdin=subprocess.DEVNULL, stdout=sortie, stderr=subprocess.STDOUT, env=e)
            try:
                p.wait(timeout=delai)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                else:
                    p.kill()
                p.wait(timeout=10)
                self.fail(f"le verbe {args} n'a pas rendu la main en {delai} s (blocage sur un fichier non ordinaire ?)")
        return p.returncode

    def test_activite_non_ordinaire_n_est_jamais_ouvert(self):
        with Banc() as b:
            activite = b.sortie / ".activite"
            # un dossier : jamais touché ; un FIFO (si le système sait en faire) : l'ouvrir en écriture bloquerait le verbe
            activite.mkdir()
            self.assertEqual(self._lancer_borne(b, "toucher", "10", "20"), 0)
            activite.rmdir()
            if bash('mkfifo "$1"', posix(activite)).returncode != 0:
                return
            self.assertEqual(self._lancer_borne(b, "toucher", "10", "20"), 0)

    def test_activite_ne_suit_pas_un_lien_symbolique(self):
        with Banc() as b:
            cible = b.t / "ailleurs.txt"
            cible.write_text("intact", newline="\n")
            b.lien(cible, b.sortie / ".activite")
            os.utime(cible, (1000000, 1000000))
            self.assertEqual(b.lancer("toucher", "10", "20")[0], 0)       # le verbe réussit
            self.assertEqual(cible.read_text(), "intact")                 # rien n'est écrit à travers le lien
            self.assertEqual(int(cible.stat().st_mtime), 1000000)

    def test_sortie_toujours_une_ligne_json_valide(self):
        with Banc(PONT_PAQUET=PAQUET) as b:
            b.logcat(b'I Test: "guillemets" \\ barre \t tab \x1b[31m \xff\xfe \r\n'
                     b'E AndroidRuntime: FATAL EXCEPTION: main\nE AndroidRuntime: Process: com.exemple.app, PID: 1\n')
            for args, code in ((("journal",), 0), (("x\x01\"\\y",), 2), (("toucher", "\"", "\\"), 2), (("capturer", "ok"), 0),
                               (("touche", "menu"), 0), (("journal", "Test"), 0)):
                with self.subTest(args=args):
                    self.assertEqual(b.lancer(*args)[0], code)    # Banc.lancer vérifie déjà une ligne, un JSON, ses clés
            _, d = b.lancer("journal", "Test")
            self.assertIn('"guillemets"', d["detail"])
        with Banc(FAUX_ADB_ECHEC="1", FAUX_EMU_MEURT="1") as b:
            for args in (("toucher", "1", "2"), ("journal",), ("demarrer",), ("arreter",)):
                with self.subTest(echec=args):
                    self.assertEqual(b.lancer(*args)[0], 4)

    # --- Corrections de revue (tour 1) ---------------------------------------------------------------------

    def test_captures_simultanees_respectent_les_limites(self):
        with Banc(PONT_CAPTURES="2", FAUX_CAPTURE_LENTE="1") as b:
            procs = [b.lancer_fond("capturer", f"n{i}") for i in range(5)]
            codes = [p.wait(timeout=120) for p in procs]
            for p in procs:
                p.communicate()
            self.assertLessEqual(len(b.captures()), 2, (codes, b.captures()))
            self.assertEqual(codes.count(0), len(b.captures()), codes)
            self.assertEqual(sorted(codes), [0, 0, 3, 3, 3], codes)

    def test_meme_nom_simultane_un_seul_ok(self):
        with Banc(FAUX_CAPTURE_LENTE="1") as b:
            procs = [b.lancer_fond("capturer", "meme") for _ in range(4)]
            codes = [p.wait(timeout=120) for p in procs]
            for p in procs:
                p.communicate()
            self.assertEqual(sorted(codes), [0, 2, 2, 2], codes)
            self.assertEqual(b.captures(), ["meme.png"])         # aucun temporaire laissé

    def test_echec_du_comptage_ferme_les_limites(self):
        with Banc() as b:
            b.faux("find", "exit 1")
            code, d = b.lancer("capturer", "a")
            self.assertEqual(code, 4, d)
            self.assertEqual([x for x in b.appels if "screencap" in x], [])
            self.assertEqual(b.captures(), [])

    def test_adb_bloque_est_coupe_par_le_delai(self):
        with Banc(FAUX_ADB_LENT="30", PONT_DELAI_ADB_S="1") as b:
            for args in (("toucher", "1", "2"), ("journal",), ("capturer", "a")):
                with self.subTest(args=args):
                    debut = time.monotonic()
                    self.assertEqual(b.lancer(*args)[0], 4)
                    self.assertLess(time.monotonic() - debut, 15)
            self.assertEqual(b.captures(), [])

    def test_demarrer_avec_adb_bloque_s_arrete_a_l_echeance(self):
        with Banc(FAUX_ADB_LENT="30", FAUX_EMU_RESTE="1", PONT_DEMARRAGE_S="3") as b:
            debut = time.monotonic()
            self.assertEqual(b.lancer("demarrer")[0], 4)
            self.assertLess(time.monotonic() - debut, 25)

    def test_journal_d_un_appel_borne_et_rapide(self):
        with Banc() as b:
            debut = time.monotonic()
            code, _ = b.lancer("zz", *(["1"] * 20000))
            self.assertEqual(code, 2)
            self.assertLess(time.monotonic() - debut, 20)
            self.assertEqual(b.lancer("toucher", *[str(i) for i in range(10)])[0], 2)
            lignes = b.lignes_pont_log
            self.assertEqual(len(lignes), 2)
            for ligne in lignes:
                self.assertLess(len(ligne), 300)
                self.assertRegex(ligne, LIGNE_JOURNAL)
            self.assertRegex(lignes[1], r"^toucher 0 1 2 3 4 5 … ")

    def test_demarrer_deux_fois_refuse_et_arreter_tue_l_emulateur(self):
        with Banc(FAUX_EMU_RESTE="1") as b:
            self.assertEqual(b.lancer("demarrer")[0], 0)
            pid = b.sortie / "emulateur.pid"
            self.assertTrue(pid.exists())
            numero = pid.read_text().strip()
            code, d = b.lancer("demarrer")
            self.assertEqual(code, 2, d)
            self.assertIn("déjà", d["detail"])
            self.assertEqual(len([x for x in b.appels if x.startswith("emulator ")]), 1)
            code, d = b.lancer("arreter")                    # adb emu kill ne tue rien ici : le pont tue le processus
            self.assertEqual(code, 0, d)
            self.assertNotEqual(bash('kill -0 "$1" 2>/dev/null', numero).returncode, 0, "émulateur encore vivant")
            self.assertFalse(pid.exists())
            self.assertEqual(b.lancer("demarrer")[0], 0)     # redémarrage possible après l'arrêt
            self.assertEqual(b.lancer("arreter")[0], 0)

    def test_chemins_d_environnement_invalides_refuses(self):
        with Banc() as b:
            for env in ({"PONT_SORTIE": ""}, {"PONT_SORTIE": "sortie"}, {"PONT_SORTIE": b.sortie_posix + "/../x"},
                        {"PONT_ADB": ""}, {"PONT_ADB": "bin/adb"}, {"PONT_EMULATEUR": ""}, {"PONT_EMULATEUR": "./emulator"}):
                with self.subTest(env=env):
                    self.assertEqual(b.lancer("toucher", "1", "2", **env)[0], 4)
            self.assertEqual(b.appels, [])
            self.assertFalse((b.t / "x").exists())
            self.assertEqual(b.lancer("toucher", "1", "2", PONT_ADB="adb")[0], 0)

    def test_journal_coupe_les_lignes_longues(self):
        with Banc() as b:
            b.logcat("I Test: " + "x" * 5000 + "\nI Test: court\n")
            code, d = b.lancer("journal")
            self.assertEqual(code, 0)
            lignes = d["detail"].splitlines()
            self.assertEqual(len(lignes[0]), 500)
            self.assertEqual(lignes[1], "I Test: court")

    def test_apk_lien_symbolique_refuse(self):
        with Banc() as b:
            vrai = b.t / "ailleurs.apk"
            vrai.write_bytes(b"PK")
            (b.entree / "app.apk").unlink()
            b.lien(vrai, b.entree / "app.apk")
            self.assertEqual(b.lancer("installer")[0], 4)
            self.assertEqual([x for x in b.appels if x.startswith("adb install")], [])

    # --- Corrections de revue (tour 2) : verrou et PID ------------------------------------------------------

    def _pid_mort(self):
        return bash("echo $$").stdout.strip()                 # un processus terminé : son PID n'existe plus

    def _sleep_etranger(self):
        p = subprocess.Popen(["bash", "-c", "echo $$; exec /usr/bin/sleep 60"], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (bash('kill -9 "$1" 2>/dev/null; exit 0', numero), p.wait(timeout=30)))
        numero = p.stdout.readline().strip()
        return numero

    def test_verrou_ne_fuit_pas_vers_les_outils(self):
        with Banc(FAUX_VERIF_FD9="1", FAUX_EMU_RESTE="1") as b:
            b.faux("flock", "exit 0")                          # chemin de production : flock tient le descripteur 9
            self.assertEqual(b.lancer("capturer", "a")[0], 0, b.appels)
            self.assertEqual(b.lancer("demarrer")[0], 0, b.appels)
            self.assertEqual([x for x in b.appels if "herite" in x], [])

    def test_flock_en_echec_refuse_la_capture(self):
        with Banc() as b:
            b.faux("flock", "exit 1")
            self.assertEqual(b.lancer("capturer", "a")[0], 4)
            self.assertEqual([x for x in b.appels if "screencap" in x], [])
            self.assertEqual(b.captures(), [])

    def test_verrou_perime_est_repris(self):
        with Banc() as b:
            verrou = b.sortie / ".verrou-captures.d"
            verrou.mkdir()
            (verrou / "pid").write_text(self._pid_mort() + "\n", newline="\n")
            debut = time.monotonic()
            self.assertEqual(b.lancer("capturer", "a")[0], 0)
            self.assertLess(time.monotonic() - debut, 20)
            self.assertFalse(verrou.exists())
            self.assertEqual(b.captures(), ["a.png"])

    def test_nom_pris_par_un_lien_symbolique(self):
        with Banc() as b:
            ailleurs = b.t / "ailleurs.png"
            (b.sortie / "captures").mkdir()
            b.lien(ailleurs, b.sortie / "captures" / "a.png")
            self.assertEqual(b.lancer("capturer", "a")[0], 2)
            self.assertFalse(ailleurs.exists())
            self.assertEqual([x for x in b.appels if "screencap" in x], [])

    def test_pid_mort_efface_et_demarrer_permis(self):
        with Banc(FAUX_EMU_RESTE="1") as b:
            pid = b.sortie / "emulateur.pid"
            pid.write_text(self._pid_mort() + "\n", newline="\n")
            self.assertEqual(b.lancer("arreter")[0], 0)
            self.assertFalse(pid.exists())
            pid.write_text(self._pid_mort() + "\n", newline="\n")
            self.assertEqual(b.lancer("demarrer")[0], 0)
            self.assertEqual(b.lancer("arreter")[0], 0)

    def test_pid_etranger_jamais_tue(self):
        with Banc(FAUX_EMU_RESTE="1") as b:
            etranger = self._sleep_etranger()
            pid = b.sortie / "emulateur.pid"
            pid.write_text(etranger + "\n", newline="\n")
            self.assertEqual(b.lancer("arreter")[0], 0)
            self.assertEqual(bash('kill -0 "$1"', etranger).returncode, 0, "processus étranger tué")
            self.assertFalse(pid.exists())
            pid.write_text(etranger + "\n", newline="\n")
            self.assertEqual(b.lancer("demarrer")[0], 0)          # un PID étranger n'est pas un émulateur en marche
            self.assertNotEqual(pid.read_text().strip(), etranger)
            self.assertEqual(b.lancer("arreter")[0], 0)
            self.assertEqual(bash('kill -0 "$1"', etranger).returncode, 0, "processus étranger tué")

    @unittest.skipUnless(sys.platform.startswith("linux"), "processus zombie : Linux seulement")
    def test_pid_zombie_n_est_pas_un_emulateur(self):
        with Banc(FAUX_EMU_RESTE="1") as b:
            z = subprocess.Popen(["true"])
            time.sleep(0.5)                                    # terminé, pas encore attendu : zombie
            (b.sortie / "emulateur.pid").write_text(f"{z.pid}\n", newline="\n")
            self.assertEqual(b.lancer("demarrer")[0], 0)
            self.assertEqual(b.lancer("arreter")[0], 0)
            z.wait()

    def test_demarrer_simultanes_un_seul_emulateur(self):
        with Banc(FAUX_EMU_RESTE="1") as b:
            procs = [b.lancer_fond("demarrer") for _ in range(3)]
            codes = [p.wait(timeout=120) for p in procs]
            for p in procs:
                p.communicate()
            self.assertEqual(sorted(codes), [0, 2, 2], codes)
            self.assertEqual(len([x for x in b.appels if x.startswith("emulator ")]), 1, b.appels)
            numero = (b.sortie / "emulateur.pid").read_text().strip()
            self.assertEqual(bash('kill -0 "$1"', numero).returncode, 0)
            self.assertEqual(b.lancer("arreter")[0], 0)

    # --- Corrections de revue (tour 3) : démarrage et arrêt sûrs --------------------------------------------

    def _vivant(self, numero):
        return bash('kill -0 "$1" 2>/dev/null', numero).returncode == 0

    def test_demarrer_simultanes_avec_emulateur_lent_a_se_presenter(self):
        # L'émulateur met 1 s à devenir « emulator » (exec tardif) : le perdant ne doit pas en lancer un second.
        with Banc() as b:
            lent = b.bin / "emulateur-lent"
            lent.write_text('#!/usr/bin/env bash\necho "emulator $*" >> "$FAUX_JOURNAL"\n/usr/bin/sleep 1\n'
                            'exec -a emulator-lent /usr/bin/sleep 60\n', newline="\n")
            lent.chmod(0o755)
            procs = [b.lancer_fond("demarrer", PONT_EMULATEUR=posix(lent)) for _ in range(3)]
            codes = [p.wait(timeout=120) for p in procs]
            for p in procs:
                p.communicate()
            self.assertEqual(sorted(codes), [0, 2, 2], codes)
            self.assertEqual(len([x for x in b.appels if x.startswith("emulator ")]), 1, b.appels)
            self.assertTrue(self._vivant((b.sortie / "emulateur.pid").read_text().strip()))
            self.assertEqual(b.lancer("arreter")[0], 0)

    def test_pid_invalide_jamais_signale(self):
        with Banc() as b:
            temoin = self._sleep_etranger()
            pid = b.sortie / "emulateur.pid"
            for contenu in ("1", "0", "99999999", "abc", "", "-1", f"-{temoin}", f"{temoin} 1"):
                with self.subTest(contenu=contenu):
                    pid.write_text(contenu + "\n", newline="\n")
                    self.assertEqual(b.lancer("arreter")[0], 0)
                    self.assertFalse(pid.exists())
                    self.assertTrue(self._vivant(temoin))

    def test_pid_non_chef_de_groupe_signale_seul(self):
        # Un « émulateur » qui n'est pas chef de son groupe : seul lui est arrêté, pas le témoin du même groupe.
        with Banc() as b:
            p = subprocess.Popen(["bash", "-c", "exec -a emulator-groupe /usr/bin/sleep 60 & echo $!; "
                                  "/usr/bin/sleep 60 & echo $!; wait"], stdout=subprocess.PIPE, text=True)
            emu, temoin = p.stdout.readline().strip(), p.stdout.readline().strip()
            self.addCleanup(lambda: (bash('kill -9 "$1" "$2" 2>/dev/null; exit 0', emu, temoin), p.wait(timeout=30)))
            time.sleep(1)
            (b.sortie / "emulateur.pid").write_text(emu + "\n", newline="\n")
            self.assertEqual(b.lancer("arreter")[0], 0)
            self.assertFalse(self._vivant(emu))
            self.assertTrue(self._vivant(temoin))

    def test_arreter_n_efface_pas_un_pid_reecrit(self):
        # Un nouveau PID écrit pendant l'arrêt (autre demarrer) n'est pas effacé : seul celui qu'on a traité l'est.
        with Banc() as b:
            self.assertEqual(b.lancer("demarrer")[0], 0)
            pid = b.sortie / "emulateur.pid"
            ancien = pid.read_text().strip()
            b.faux("adb", f'echo "adb $*" >> "$FAUX_JOURNAL"\n'
                          f'[ "$1" = emu ] && printf "424242\\n" > "{b.sortie_posix}/emulateur.pid"\nexit 0')
            self.assertEqual(b.lancer("arreter")[0], 0)
            self.assertFalse(self._vivant(ancien))
            self.assertEqual(pid.read_text().strip(), "424242")

    def test_verrou_sans_pid_ancien_est_repris(self):
        with Banc(PONT_DELAI_ADB_S="1") as b:
            verrou = b.sortie / ".verrou-captures.d"
            verrou.mkdir()
            vieux = time.time() - 3600
            os.utime(verrou, (vieux, vieux))
            self.assertEqual(b.lancer("capturer", "a")[0], 0)
            self.assertFalse(verrou.exists())
            self.assertEqual([x.name for x in b.sortie.iterdir() if x.name.startswith(".verrou")], [])

    def test_dossier_captures_lien_symbolique_refuse(self):
        with Banc() as b:
            ailleurs = b.t / "ailleurs"
            ailleurs.mkdir()
            b.lien(ailleurs, b.sortie / "captures")
            self.assertEqual(b.lancer("capturer", "a")[0], 4)
            self.assertEqual(list(ailleurs.iterdir()), [])
            self.assertEqual([x for x in b.appels if "screencap" in x], [])


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestJournalSauvegarde(unittest.TestCase):
    """`journal` ajoute aussi ses lignes (mêmes bornes, caractères de contrôle remplacés) à sortie/logcat.txt."""

    def test_journal_ajoute_a_logcat_txt_avec_un_en_tete_par_appel(self):
        with Banc() as b:
            b.logcat("I Test: un\x1b[31m rouge\nI Test: deux pair\n")
            self.assertEqual(b.lancer("journal")[0], 0)
            self.assertEqual(b.lancer("journal", "pair")[0], 0)
            lignes = (b.sortie / "logcat.txt").read_text(encoding="utf-8").splitlines()
            self.assertRegex(lignes[0], r"^# journal - \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertEqual(lignes[1], "I Test: un?[31m rouge")
            self.assertEqual(lignes[2], "I Test: deux pair")
            self.assertRegex(lignes[3], r"^# journal pair \d{4}-")
            self.assertEqual(lignes[4:], ["I Test: deux pair"])

    def test_logcat_txt_plafonne(self):
        with Banc(PONT_LOGCAT_OCTETS="300") as b:
            b.logcat("".join(f"I Test: ligne {i}\n" for i in range(100)))
            for _ in range(3):
                self.assertEqual(b.lancer("journal")[0], 0)        # la réponse reste complète
            self.assertLessEqual((b.sortie / "logcat.txt").stat().st_size, 300)

    def test_logcat_txt_jamais_suivi_s_il_est_un_lien(self):
        with Banc() as b:
            cible = b.t / "ailleurs.txt"
            cible.write_text("intact\n", encoding="utf-8")
            b.lien(cible, b.sortie / "logcat.txt")
            b.logcat("I Test: x\n")
            code, d = b.lancer("journal")
            self.assertEqual(code, 0, d)
            self.assertEqual(cible.read_text(encoding="utf-8"), "intact\n")


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestFilm(unittest.TestCase):
    """`filmer <nom> [secondes]` lance screenrecord en arrière-plan ; `finfilm` l'arrête, rapatrie le mp4 et en tire des images."""

    def filmer(self, b, nom="demo", *plus, **env):
        code, d = b.lancer("filmer", nom, *plus, **env)
        self.assertEqual(code, 0, (d, b.derniere.stderr))
        return d

    def test_filmer_puis_finfilm(self):
        with Banc() as b:
            d = self.filmer(b)
            self.assertIn("demo", d["detail"])
            enreg = [x for x in b.appels if "screenrecord" in x]
            self.assertEqual(enreg, ["adb shell screenrecord --size 360x720 --bit-rate 1500000 --time-limit 30 "
                                     "/data/local/tmp/demo.mp4"])
            code, d = b.lancer("finfilm")
            self.assertEqual(code, 0, (d, b.derniere.stderr))
            self.assertIn("adb shell pkill -2 screenrecord", b.appels)
            self.assertTrue(any(x.startswith("adb pull /data/local/tmp/demo.mp4 ") for x in b.appels), b.appels)
            video = b.sortie / "videos" / "demo.mp4"
            self.assertEqual(video.read_bytes()[4:8], b"ftyp")
            images = sorted(p.name for p in (b.sortie / "videos" / "demo-img").iterdir())
            self.assertEqual(images, ["demo-001.png", "demo-002.png", "demo-003.png"])
            ff = [x for x in b.appels if x.startswith("ffmpeg ")][0]
            self.assertIn("fps=1/2,scale=320:-2", ff)
            self.assertIn("-frames:v 30", ff)
            self.assertTrue(ff.endswith("/videos/demo-img/demo-%03d.png"), ff)
            self.assertRegex(d["detail"], r"^videos/demo\.mp4 \(\d+ octets, \d+ s, 3 images\)")
            self.assertFalse((b.sortie / ".film").exists())
            self.assertEqual(sorted(p.name for p in (b.sortie / "videos").iterdir()), ["demo-img", "demo.mp4"])

    def test_duree_choisie_et_bornee(self):
        with Banc() as b:
            self.filmer(b, "a", "180")
            self.assertIn("--time-limit 180", [x for x in b.appels if "screenrecord" in x][0])
            self.assertEqual(b.lancer("finfilm")[0], 0)

    def test_un_seul_film_a_la_fois(self):
        with Banc() as b:
            self.filmer(b, "un")
            code, d = b.lancer("filmer", "deux")
            self.assertEqual(code, 2, d)
            self.assertEqual(len([x for x in b.appels if "screenrecord" in x]), 1)
            self.assertEqual(b.lancer("finfilm")[0], 0)
            self.filmer(b, "deux")                                    # le film fini, un autre peut commencer
            self.assertEqual(b.lancer("finfilm")[0], 0)

    def test_finfilm_sans_film_donne_2(self):
        with Banc() as b:
            code, d = b.lancer("finfilm")
            self.assertEqual(code, 2, d)
            self.assertEqual(b.appels, [])

    def test_nom_deja_pris_refuse(self):
        with Banc() as b:
            (b.sortie / "videos").mkdir()
            (b.sortie / "videos" / "demo.mp4").write_bytes(b"x")
            self.assertEqual(b.lancer("filmer", "demo")[0], 2)
            self.assertEqual([x for x in b.appels if "screenrecord" in x], [])

    def test_cinq_videos_au_plus(self):
        with Banc() as b:
            (b.sortie / "videos").mkdir()
            for i in range(5):
                (b.sortie / "videos" / f"v{i}.mp4").write_bytes(b"x")
            self.assertEqual(b.lancer("filmer", "sixieme")[0], 3)
            self.assertEqual([x for x in b.appels if "screenrecord" in x], [])

    def test_video_au_dela_des_octets_effacee_code_3(self):
        with Banc(PONT_OCTETS="1000", FAUX_MP4_OCTETS="5000") as b:
            self.filmer(b)
            code, d = b.lancer("finfilm")
            self.assertEqual(code, 3, d)
            videos = b.sortie / "videos"
            self.assertEqual([p.name for p in videos.iterdir()] if videos.exists() else [], [])
            self.assertFalse((b.sortie / ".film").exists())

    def test_video_trop_grosse_par_fichier_code_3(self):
        with Banc(PONT_VIDEO_OCTETS="1000", FAUX_MP4_OCTETS="5000") as b:
            self.filmer(b)
            self.assertEqual(b.lancer("finfilm")[0], 3)
            self.assertFalse((b.sortie / "videos" / "demo.mp4").exists())

    def test_fichier_qui_n_est_pas_un_mp4_efface_code_4(self):
        with Banc(FAUX_MP4_FAUX="1") as b:
            self.filmer(b)
            code, d = b.lancer("finfilm")
            self.assertEqual(code, 4, d)
            self.assertFalse((b.sortie / "videos" / "demo.mp4").exists())
            self.assertEqual([x for x in b.appels if x.startswith("ffmpeg")], [])

    def test_extraction_d_images_en_echec_garde_la_video(self):
        with Banc(FAUX_FFMPEG_ECHEC="1") as b:
            self.filmer(b)
            code, d = b.lancer("finfilm")
            self.assertEqual(code, 0, d)
            self.assertIn("0 images", d["detail"])
            self.assertTrue((b.sortie / "videos" / "demo.mp4").exists())

    def test_enregistrement_qui_meurt_aussitot_est_un_echec(self):
        with Banc(FAUX_FILM_MEURT="1") as b:
            code, d = b.lancer("filmer", "demo")
            self.assertEqual(code, 4, d)
            self.assertFalse((b.sortie / ".film").exists())

    def test_arreter_finit_un_film_en_cours(self):
        with Banc() as b:
            self.filmer(b)
            code, d = b.lancer("arreter")
            self.assertEqual(code, 0, d)
            self.assertTrue((b.sortie / "videos" / "demo.mp4").exists())
            self.assertIn("videos/demo.mp4", d["detail"])
            self.assertFalse((b.sortie / ".film").exists())

    def _pid_vivant(self):
        p = subprocess.Popen(["bash", "-c", "echo $$; exec /usr/bin/sleep 60"], stdout=subprocess.PIPE, text=True)
        numero = p.stdout.readline().strip()
        self.addCleanup(lambda: (bash('kill -9 "$1" 2>/dev/null; exit 0', numero), p.wait(timeout=30)))
        return numero

    def test_filmer_n_attend_le_verrou_que_quelques_secondes(self):
        # Revue 1 : un finfilm en cours tient le verrou « film » longtemps ; filmer renonce vite (code 4), bien avant le
        # délai SSH de filmer côté poste.
        with Banc() as b:
            verrou = b.sortie / ".verrou-film.d"
            verrou.mkdir(parents=True)
            (verrou / "pid").write_text(self._pid_vivant() + "\n", newline="\n")
            debut = time.monotonic()
            code, d = b.lancer("filmer", "demo")
            self.assertEqual(code, 4, d)
            self.assertLess(time.monotonic() - debut, 15)
            self.assertEqual([x for x in b.appels if "screenrecord" in x], [])

    def test_trace_du_film_gardee_tant_que_le_travail_n_est_pas_fini(self):
        # Revue 2 : un finfilm interrompu (ici : ffmpeg tué) ne perd pas la trace ; un finfilm suivant reprend le film.
        with Banc() as b:
            self.filmer(b)
            # tue le pont (grand-parent : pont -> timeout -> ffmpeg) pendant l'extraction des images
            b.faux("ffmpeg", 'echo "ffmpeg $*" >> "$FAUX_JOURNAL"; kill -9 "$(cut -d" " -f4 /proc/$PPID/stat)"')
            commande, e = b._preparer(["finfilm"], {})
            subprocess.run(commande, stdin=subprocess.DEVNULL, capture_output=True, env=e, timeout=60)
            self.assertTrue((b.sortie / ".film.fin").exists() or (b.sortie / ".film").exists())
            self.assertEqual(b.lancer("filmer", "autre")[0], 2)                        # pas de nouveau film entre-temps
            (b.bin / "ffmpeg").write_text("#!/usr/bin/env bash\n" + FFMPEG_FACTICE + "\n", newline="\n")
            code, d = b.lancer("finfilm")
            self.assertIn(code, (0, 2), d)
            self.assertFalse((b.sortie / ".film").exists())
            self.assertFalse((b.sortie / ".film.fin").exists())

    def test_processus_reconnu_par_ses_arguments_exacts(self):
        # Revue 3 : un processus dont la ligne de commande CONTIENT « screenrecord » sans en être un n'est pas le film.
        with Banc() as b:
            p = subprocess.Popen(["bash", "-c", "echo $$; exec -a xscreenrecordx /usr/bin/sleep 60"],
                                 stdout=subprocess.PIPE, text=True)
            numero = p.stdout.readline().strip()
            self.addCleanup(lambda: (bash('kill -9 "$1" 2>/dev/null; exit 0', numero), p.wait(timeout=30)))
            (b.sortie / ".film").write_text(f"demo {numero} {int(time.time())} 30\n", newline="\n")
            code, d = b.lancer("finfilm")
            self.assertEqual(code, 0, d)
            self.assertIsNone(p.poll())                                              # jamais signalé

    def test_duree_rendue_bornee_par_la_duree_demandee_et_images_sur_tout_le_film(self):
        # Revues 6 et 7 : durée = min(temps écoulé, durée demandée) ; une image toutes les max(2, durée/30) s.
        with Banc() as b:
            (b.sortie / ".film").write_text(f"demo 999999 {int(time.time()) - 1000} 180\n", newline="\n")
            code, d = b.lancer("finfilm")
            self.assertEqual(code, 0, d)
            self.assertIn(", 180 s,", d["detail"])
            ff = [x for x in b.appels if x.startswith("ffmpeg ")][0]
            self.assertIn("fps=1/6,scale=320:-2", ff)
        with Banc() as b:
            (b.sortie / ".film").write_text(f"court 999999 {int(time.time()) - 1000} 20\n", newline="\n")
            self.assertEqual(b.lancer("finfilm")[0], 0)
            self.assertIn("fps=1/2,scale=320:-2", [x for x in b.appels if x.startswith("ffmpeg ")][0])

    def test_arreter_dit_un_film_au_dela_des_limites(self):
        # Revue 5 : le film fini par arreter dépasse les octets : code 3 (le lanceur note la limite), détail explicite.
        with Banc(PONT_OCTETS="1000", FAUX_MP4_OCTETS="5000") as b:
            self.filmer(b)
            code, d = b.lancer("arreter")
            self.assertEqual(code, 3, d)
            self.assertIn("Émulateur arrêté", d["detail"])
            self.assertIn("Limite d'octets", d["detail"])
        with Banc(FAUX_MP4_FAUX="1") as b:
            self.filmer(b)
            code, d = b.lancer("arreter")
            self.assertEqual(code, 4, d)
            self.assertIn("MP4", d["detail"])

    def test_film_court_fini_avant_le_controle_est_un_film(self):
        # Revue 10 : filmer 1 s : l'enregistrement a pu finir (proprement) avant le contrôle d'une seconde.
        with Banc(FAUX_FILM_COURT="1") as b:
            code, d = b.lancer("filmer", "bref", "1")
            self.assertEqual(code, 0, d)
            self.assertEqual(b.lancer("finfilm")[0], 0)
            self.assertTrue((b.sortie / "videos" / "bref.mp4").exists())

    def test_logcat_txt_sous_verrou(self):
        # Revue 4 : les ajouts à logcat.txt prennent un verrou (le plafond tient même à plusieurs).
        with Banc(PONT_LOGCAT_OCTETS="2000") as b:
            b.logcat("".join(f"I Test: ligne {i}\n" for i in range(40)))
            fils = [b.lancer_fond("journal") for _ in range(4)]
            for f in fils:
                f.communicate(timeout=60)
            self.assertLessEqual((b.sortie / "logcat.txt").stat().st_size, 2000)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("prendre_verrou journal", source)

    def test_dossier_videos_lien_symbolique_refuse(self):
        with Banc() as b:
            ailleurs = b.t / "ailleurs"
            ailleurs.mkdir()
            b.lien(ailleurs, b.sortie / "videos")
            self.assertEqual(b.lancer("filmer", "demo")[0], 4)
            self.assertEqual(list(ailleurs.iterdir()), [])
            self.assertEqual([x for x in b.appels if "screenrecord" in x], [])


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestConcordancePontHote(unittest.TestCase):
    """Décision R2 : les MÊMES exemples (valides et hostiles, filmer et finfilm compris) passent par pont.sh,
    serveur_tache.valider_verbe et le pont hôte (sa table, et une vraie requête qui ne doit rien exécuter si elle est refusée)."""

    def test_motifs_pont_sh_python_et_pont_hote_s_accordent(self):
        from tests.test_serveur_pont_hote import Banc as BancHote, PH, st
        from tests.test_serveur_tache import ACCEPTES, REFUSES
        self.assertEqual({v: tuple(m) for v, m in PH.VERBES.items()}, {v: tuple(m) for v, m in st.VERBES.items()})
        self.assertEqual(dict(PH.FACULTATIFS), dict(st.FACULTATIFS))
        self.assertEqual(PH.MOTIF_NOM_RESERVE, st.MOTIF_NOM_RESERVE)
        for nom in ("filmer", "finfilm"):
            self.assertIn(nom, PH.VERBES)
        with Banc(PONT_PAQUET="com.exemple.app") as banc, BancHote() as hote:
            for v, args in ACCEPTES + REFUSES:
                with self.subTest(verbe=v, args=args):
                    try:
                        st.valider_verbe(v, args)
                        python = True
                    except ValueError:
                        python = False
                    try:
                        PH.valider_verbe(v, args)
                        cote_hote = True
                    except PH.Refus:
                        cote_hote = False
                    self.assertEqual(python, cote_hote, (v, args))
                    if not (v == "demarrer" and cote_hote):  # sans émulation : un verbe valide rend 4, un refusé 2
                        code_hote, d = hote.appel(v, *args)
                        self.assertEqual(cote_hote, code_hote != 2, (v, args, d))
                    if (v == "lancer" and not args) or (v == "finfilm" and not args):
                        continue                                # exige un paquet installé / un film en cours : couverts ailleurs
                    code, _d = banc.lancer(v, *args)
                    self.assertEqual(python, code != 2, (v, args, code, _d))
                    if v == "filmer" and code == 0:
                        self.assertEqual(banc.lancer("finfilm")[0], 0)
            self.assertEqual(hote.faux.appels, [])


if __name__ == "__main__":
    unittest.main()
