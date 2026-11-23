"""Bac à sable Unity de l'hôte (conception § 5.16, option A, tâche 14h). CODE TRÈS SENSIBLE : du code de projet non fiable
tourne sur l'hôte, dans une unité systemd transitoire confinée sous l'utilisateur dédié unity-tests.

Rien de réel ici : faux `systemd-run`, `systemctl`, `sudo`, `setfacl`, `useradd`, `visudo`, `id`, `mount`, `cp` dans le PATH ;
le script racine (`serveur_ovh/unity-bac-a-sable.sh`) tourne SANS root, ses chemins fixes sous BAC_A_SABLE_RACINE_TEST (ignorée
en root) ; aucune vraie licence (valeur `LICENCE-FACTICE-1` dans un HOME temporaire) ; aucun utilisateur, ACL ni règle sudoers
n'est créé (le faux `sudo` ne fait que journaliser, sauf pour le script racine, docker, visudo, systemctl et setfacl, eux aussi
faux). L'enveloppe (`serveur_ovh/taches/lancer_tests.sh`) tourne avec le banc de `test_serveur_tests_deps`."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import serveur_installation as inst  # noqa: E402
import test_serveur_tests_deps as D  # noqa: E402
import test_serveur_tests_enveloppe as E  # noqa: E402
import test_serveur_tests_unity as U  # noqa: E402

SERVEUR = RACINE / "serveur_ovh"
SCRIPT_RACINE = SERVEUR / "unity-bac-a-sable.sh"
SONDE = SERVEUR / "sonde-bac-a-sable.sh"
MISE = SERVEUR / "mise_en_place.sh"
CHEMIN_RACINE = "/usr/local/lib/myiafactory/unity-bac-a-sable.sh"
ID, ID_B = E.ID, E.ID_B
VERSION, REPLI = U.VERSION, "6000.6.10f1"
FACTICE = U.FACTICE
# La liste FIGÉE du § 5.16 : rien d'autre ne doit jamais apparaître dans un -p.
FIGEES = {"User", "ProtectHome", "ProtectSystem", "PrivateTmp", "PrivateDevices", "NoNewPrivileges", "CapabilityBoundingSet",
          "ProtectProc", "ProcSubset", "ProtectKernelTunables", "ProtectKernelModules", "ProtectKernelLogs", "RestrictNamespaces",
          "RestrictSUIDSGID", "LockPersonality", "SystemCallFilter", "InaccessiblePaths", "ReadWritePaths", "BindReadOnlyPaths",
          "PrivateNetwork", "IPAddressDeny", "IPAddressAllow", "MemoryMax", "MemorySwapMax", "CPUQuota", "TasksMax",
          "LimitNOFILE", "RuntimeMaxSec"}
FIXES = {"User": "unity-tests", "ProtectHome": "tmpfs", "ProtectSystem": "strict", "PrivateTmp": "yes", "PrivateDevices": "yes",
         "NoNewPrivileges": "yes", "CapabilityBoundingSet": "", "ProtectProc": "invisible", "ProcSubset": "pid",
         "ProtectKernelTunables": "yes", "ProtectKernelModules": "yes", "ProtectKernelLogs": "yes", "RestrictNamespaces": "yes",
         "RestrictSUIDSGID": "yes", "LockPersonality": "yes", "SystemCallFilter": "@system-service",
         "InaccessiblePaths": "-/run/docker.sock -/var/run/docker.sock", "MemorySwapMax": "0", "TasksMax": "2048",
         "LimitNOFILE": "8192"}

SYSTEMD_RUN = r'''n=0; while [ -e "$FAUX_ETAT/systemd-run-$n.txt" ]; do n=$((n + 1)); done
printf '%s\n' "$@" > "$FAUX_ETAT/systemd-run-$n.txt"
echo "systemd-run $*" >> "$FAUX_JOURNAL"
cat > "$FAUX_ETAT/unite-entree-$n"
echo "sortie de l'unité"
echo "erreur de l'unité" >&2
if [ -n "${FAUX_UNITE_ATTENDRE:-}" ]; then
  while [ ! -e "$FAUX_ETAT/unite-arretee" ]; do sleep 0.05; done
  exit 143
fi
exit "${FAUX_UNITE_CODE:-0}"'''
SYSTEMCTL = r'''echo "systemctl $*" >> "$FAUX_JOURNAL"
case "$1" in
  --version) echo "systemd ${FAUX_SYSTEMD:-255} (255.4-1ubuntu8)" ;;
  stop) [ -n "${FAUX_ETAT:-}" ] && : > "$FAUX_ETAT/unite-arretee" ;;
  list-units) [ -n "${FAUX_UNITES:-}" ] && for u in $FAUX_UNITES; do echo "$u loaded active running x"; done ;;
  show) echo "${FAUX_DEPUIS_US:-1}" ;;
  is-active) exit 3 ;;
esac
exit 0'''
# Le faux sudo journalise TOUT ; il n'exécute que les faux (et le script racine du dépôt à la place de son chemin installé).
SUDO = r'''echo "sudo $*" >> "$FAUX_JOURNAL"
[ "$1" = -n ] && shift
case "$1" in
  ''' + CHEMIN_RACINE + r''') shift; exec bash "$FAUX_BAC_A_SABLE" "$@" ;;
  docker|visudo|systemctl|setfacl|true) exec "$@" ;;
esac
exit 0'''
ID_FAUX = r'''case "$*" in
  -u) echo "${FAUX_UID:-1000}" ;;
  -un) echo "${FAUX_NOM:-principal}" ;;
  "-u unity-tests") [ -n "${FAUX_SANS_UNITY:-}" ] && exit 1; echo 998 ;;
  "-nG unity-tests") echo "${FAUX_GROUPES_UNITY:-unity-tests}" ;;
  *) echo "${FAUX_UID:-1000}" ;;
esac'''
VISUDO = r'''echo "visudo $*" >> "$FAUX_JOURNAL"
f=""; prec=""; for a in "$@"; do [ "$prec" = -f ] && f="$a"; prec="$a"; done
if [ -n "$f" ]; then cp "$f" "$FAUX_ETAT/sudoers"; [ "${FAUX_VISUDO_ECHEC:-}" = fichier ] && exit 1; exit 0; fi
[ "${FAUX_VISUDO_ECHEC:-}" = global ] && exit 1
exit 0'''
JOURNALISER = 'echo "{nom} $*" >> "$FAUX_JOURNAL"\nexit {code}'
CP = 'echo "cp $*" >> "$FAUX_JOURNAL"\nPATH="${PATH#*:}" exec cp "$@"'
FAUX = dict(D.FAUX, **{"systemd-run": SYSTEMD_RUN, "systemctl": SYSTEMCTL, "sudo": SUDO, "id": ID_FAUX, "visudo": VISUDO,
                       "setfacl": JOURNALISER.format(nom="setfacl", code=0), "useradd": JOURNALISER.format(nom="useradd", code=0),
                       "mount": 'echo "mount $*" >> "$FAUX_JOURNAL"\nexit "${FAUX_MOUNT_CODE:-32}"',
                       "umount": JOURNALISER.format(nom="umount", code=0), "mountpoint": "exit 1", "cp": CP})


def _ecrire(chemin, texte, mode=0o644):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8", newline="\n")
    chemin.chmod(mode)


@unittest.skipUnless(shutil.which("bash"), "bash absent")
@unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "le script racine n'accepte ses chemins de test que hors root")
class TestBacASable(D.Banc):
    @classmethod
    def setUpClass(cls):
        D.Banc.setUpClass()
        for nom, corps in FAUX.items():
            (cls.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (cls.bin / nom).chmod(0o755)

    def setUp(self):
        D.Banc.setUp(self)
        r = self.r = self.t / "racine"
        lib = r / "usr" / "local" / "lib" / "myiafactory"
        lib.mkdir(parents=True)
        for src in (SCRIPT_RACINE, SONDE, SERVEUR / "images" / "tests" / "entree-tests.sh",
                    SERVEUR / "images" / "tests" / "entree-unity.sh"):
            shutil.copy(src, lib / src.name)
        (r / "var" / "lib" / "unity-tests" / "campagnes").mkdir(parents=True)
        (r / "run" / "lock").mkdir(parents=True)
        self.editeur(VERSION)
        self.droits = self.home / ".config" / "unity3d" / "Unity" / "licenses"
        _ecrire(self.droits / "UnityEntitlementLicense.xml", FACTICE, 0o600)
        self.ulf = self.home / ".local" / "share" / "unity3d" / "Unity" / "Unity_lic.ulf"
        _ecrire(self.ulf, FACTICE, 0o600)
        self.h, self.rm = E._msys(self.home), E._msys(r)
        self.env.update(BAC_A_SABLE_RACINE_TEST=self.rm, FAUX_BAC_A_SABLE=SCRIPT_RACINE.as_posix())

    def editeur(self, version):
        _ecrire(self.r / "opt" / "unity" / "editors" / version / "Editor" / "Unity", "#!/bin/sh\nexit 0\n", 0o755)

    def campagne(self, ident=ID):
        return f"{self.rm}/var/lib/unity-tests/campagnes/{ident}"

    # --- enveloppe -----------------------------------------------------------------------------------------------------
    def demarrer_hote(self, *plus, ident=ID, env=None, commande=json.dumps(U.COMMANDE_UNITY), licence="B1"):
        entree = self.home / "tests" / ident / "entree"
        entree.mkdir(parents=True)
        (entree / "entree.tar").write_bytes(D.TAR_NODE)
        etat = self.t / "etat" / ident
        etat.mkdir(parents=True, exist_ok=True)
        e = dict(self.env, FAUX_ETAT=etat.as_posix(), **(env or {}))
        args = ["bash", E.SCRIPT.as_posix(), ident, "2", "4", "8192", "1800", "projet-a", "-", *U.UNITY_14,
                "hote_bac_a_sable", licence, *plus]
        sortie, erreur = open(etat / "out", "w+b"), open(etat / "err", "w+b")
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=sortie, stderr=erreur, env=e)
        try:
            p.stdin.write((commande + "\n").encode())
            p.stdin.flush()
        except OSError:
            pass
        return p, sortie, erreur, etat

    def finir_hote(self, lance, fermer=True):
        p, sortie, erreur, etat = lance
        try:
            code = p.wait(timeout=90)
        finally:
            if p.poll() is None:
                p.kill()
            if fermer:
                try:
                    p.stdin.close()
                except OSError:
                    pass
        sortie.seek(0)
        erreur.seek(0)
        out, err = sortie.read().decode("utf-8", "replace"), erreur.read().decode("utf-8", "replace")
        sortie.close()
        erreur.close()
        lignes = [x for x in err.split("\n") if x]
        self.assertTrue(E.FIN.match(lignes[-1]), lignes[-5:])
        return code, out, lignes, etat

    def hote(self, *plus, **k):
        return self.finir_hote(self.demarrer_hote(*plus, **k))

    @staticmethod
    def unite(etat, n=0):
        f = etat / f"systemd-run-{n}.txt"
        return f.read_text(encoding="utf-8").splitlines() if f.exists() else None

    @staticmethod
    def proprietes(args):
        return [b for a, b in zip(args, args[1:]) if a == "-p"]

    def direct(self, *args, entree=b"", env=None):
        etat = self.t / "etat" / "direct"
        etat.mkdir(parents=True, exist_ok=True)
        e = dict(self.env, FAUX_ETAT=etat.as_posix(), **(env or {}))
        r = subprocess.run(["bash", SCRIPT_RACINE.as_posix(), *args], input=entree, capture_output=True, env=e, timeout=60)
        return r, etat

    def campagnes(self):
        return sorted(p.name for p in (self.r / "var" / "lib" / "unity-tests" / "campagnes").iterdir())

    # --- tests ---------------------------------------------------------------------------------------------------------
    def test_proprietes_figees_de_l_unite(self):
        code, out, err, etat = self.hote()
        self.assertEqual(code, 0, err)
        args = self.unite(etat)
        self.assertIsNotNone(args, self.journal)
        props = self.proprietes(args)
        cles = [p.split("=", 1)[0] for p in props]
        self.assertEqual(set(cles) - FIGEES, set(), props)                                 # rien hors de la liste figée
        for cle, valeur in FIXES.items():
            self.assertIn(f"{cle}={valeur}", props)
        c = self.campagne()
        self.assertEqual([p for p in props if p.startswith("ReadWritePaths=")], [f"ReadWritePaths={c}"])
        liees = sorted(p.split("=", 1)[1] for p in props if p.startswith("BindReadOnlyPaths="))
        self.assertEqual(liees, sorted([f"{self.rm}/opt/unity/editors/{VERSION}",
                                        f"{self.h}/.config/unity3d/Unity/licenses:{c}/home/.config/unity3d/Unity/licenses",
                                        f"{self.h}/.local/share/unity3d/Unity/Unity_lic.ulf:"
                                        f"{c}/home/.local/share/unity3d/Unity/Unity_lic.ulf"]))
        self.assertFalse([a for a in args if a.startswith(("BindPaths", "--property", "-E"))], args)
        self.assertIn("MemoryMax=8192M", props)
        self.assertIn("CPUQuota=400%", props)
        self.assertIn("RuntimeMaxSec=1830", props)
        self.assertEqual(args[:6], ["--quiet", "--pipe", "--wait", "--collect", "--unit", f"unity-tests-{ID}"])
        options = [a for a in args[:args.index("--")] if a.startswith("-") and a != "-p" and not a.startswith("--setenv=")]
        self.assertEqual(options, ["--quiet", "--pipe", "--wait", "--collect", "--unit"])
        env = dict(a[len("--setenv="):].split("=", 1) for a in args if a.startswith("--setenv="))
        self.assertEqual(env, {"HOME": f"{c}/home", "PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C",
                               "ENTREE_TESTS_RACINE": c, "MYIAFACTORY_TESTS_FAMILLE": "unity",
                               "MYIAFACTORY_UNITY_LICENCE": "liee",
                               "MYIAFACTORY_UNITY_EDITEUR": f"{self.rm}/opt/unity/editors/{VERSION}/Editor/Unity"})
        self.assertEqual(args[args.index("--") + 1:],
                         ["/bin/bash", f"{self.rm}/usr/local/lib/myiafactory/unity-bac-a-sable.sh", "unite"])
        # L'instantané passe par l'entrée de l'unité (la racine n'ouvre aucun fichier de l'utilisateur principal) ; la sortie
        # suit le chemin commun (préfixe `| ` de la sortie d'erreur) ; aucun conteneur ; la campagne est effacée.
        self.assertEqual((etat / "unite-entree-0").read_bytes(), D.TAR_NODE)
        self.assertIn("sortie de l'unité", out)
        self.assertIn("| erreur de l'unité", err)
        self.assertIn(f"sudo -n {CHEMIN_RACINE} lancer {ID} 4 8192 1800 {VERSION} aucun", self.journal)
        self.assertNotIn("docker run", self.journal)
        self.assertNotIn("docker image inspect", self.journal)
        self.assertEqual(self.campagnes(), [])
        self.assertFalse((self.home / "tests" / ID).exists())
        self.assertNotIn(FACTICE, self.journal + out + "\n".join(err))

    def test_arguments_hostiles_refuses(self):
        bons = [ID, "4", "8192", "1800", VERSION, "aucun"]
        mauvais = {0: ["../x", "t20261123-101500-ab12/../x", "t20261123-101500-AB12", "t20261123-101500-ab12\nx", "$(id)"],
                   1: ["0", "65", "04", "4;id"], 2: ["255", "65537", "08192", "-1"], 3: ["0", "3601", "01800", "1e3"],
                   4: ["6000.6.7f1;id", "6000.6.7f1 ", "../6000.6.7f1", "6000.6.7", "x6000.6.7f1", "6000.6.7f1/.."],
                   5: ["bridge", "host", "aucun;id", "LICENCE", ""]}
        for i, valeurs in mauvais.items():
            for v in valeurs:
                with self.subTest(position=i, valeur=v):
                    args = list(bons)
                    args[i] = v
                    r, etat = self.direct("lancer", *args, entree=(json.dumps(U.COMMANDE_UNITY) + "\n").encode())
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertIsNone(self.unite(etat))
        for extra in (["lancer", *bons, "x"], ["lancer", *bons[:5]], ["arreter", "../x"], ["arreter", ID, "x"],
                      ["inconnu", *bons], ["unite"], []):
            with self.subTest(args=extra):
                r, etat = self.direct(*extra)
                self.assertEqual(r.returncode, 2, r.stderr)
        for commande in ('["bash","-c","id"]', '["unity-editor"', "x", '["unity-editor","a\tb"]', "[" + "x" * 4100 + "]"):
            with self.subTest(commande=commande):
                r, etat = self.direct("lancer", *bons, entree=(commande + "\n").encode())
                self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn("systemd-run", self.journal)
        self.assertEqual(self.campagnes(), [])
        # Par l'enveloppe : une version de repli hors motif est refusée avant tout (aucun sudo, rien écrit).
        code, out, err, etat = self.hote("-", "6000.6.7f1;id")
        self.assertEqual(code, 2, err)
        self.assertEqual(err[-2], "#refus 2")
        self.assertNotIn(CHEMIN_RACINE, self.journal)
        # L'exécuteur hôte est réservé à la famille unity ; une version de repli exige l'exécuteur hôte.
        code, err, _ = self.lancer("10", "myiafactory/tests", "node", "-", "refuse", "40", "16", "hote_bac_a_sable", "-",
                                   deps="-", ident=E.ident(60))
        self.assertEqual(code, 2, err)
        code, err, _ = self.lancer(*U.UNITY_14, "conteneur", "B1", "-", REPLI, deps="-", ident=E.ident(61))
        self.assertEqual(code, 2, err)
        self.assertNotIn(CHEMIN_RACINE, self.journal)

    def test_licence_liee_jamais_copiee(self):
        code, out, err, etat = self.hote()
        self.assertEqual(code, 0, err)
        copies = [x for x in self.journal.splitlines() if x.startswith("cp ")]
        self.assertFalse([x for x in copies if "licenses" in x or ".ulf" in x], copies)
        liees = [p for p in self.proprietes(self.unite(etat)) if "unity3d" in p]
        self.assertTrue(liees)
        self.assertTrue(all(p.startswith("BindReadOnlyPaths=") for p in liees), liees)    # en lecture seule, jamais BindPaths
        self.assertNotIn(FACTICE, self.journal + out + "\n".join(err))
        self.assertEqual(self.droits.joinpath("UnityEntitlementLicense.xml").read_text(encoding="utf-8"), FACTICE)
        # Sans le .ulf : seuls les droits ; sans aucune licence : 77 (refus), aucune unité.
        self.ulf.unlink()
        code, out, err, etat = self.hote(ident=ID_B)
        self.assertEqual(code, 0, err)
        self.assertFalse([p for p in self.proprietes(self.unite(etat)) if ".ulf" in p])
        shutil.rmtree(self.droits)
        r, etat = self.direct("lancer", E.ident(70), "4", "8192", "1800", VERSION, "aucun",
                              entree=(json.dumps(U.COMMANDE_UNITY) + "\n").encode())
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertIsNone(self.unite(etat))
        # Un lien à la place du dossier de licence n'est jamais lié (il pourrait viser n'importe quoi de lisible par root).
        if os.name != "nt":
            ailleurs = self.t / "ailleurs"
            ailleurs.mkdir()
            (ailleurs / "secret").write_text("x", encoding="utf-8")
            self.droits.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(ailleurs, self.droits)
            r, etat = self.direct("lancer", E.ident(71), "4", "8192", "1800", VERSION, "aucun",
                                  entree=(json.dumps(U.COMMANDE_UNITY) + "\n").encode())
            self.assertEqual(r.returncode, 77, r.stderr)

    def test_reseau_prive_par_defaut(self):
        code, out, err, etat = self.hote()
        self.assertEqual(code, 0, err)
        props = self.proprietes(self.unite(etat))
        self.assertIn("PrivateNetwork=yes", props)
        self.assertFalse([p for p in props if p.startswith("IPAddress")], props)
        self.assertFalse([a for a in self.unite(etat) if "PROXY" in a.upper()])
        # B3 (accord vérifié par la route) : le mandataire de la campagne seul, jamais le réseau de l'hôte entier.
        code, out, err, etat = self.hote("license.unity3d.com", ident=ID_B, licence="B3")
        self.assertEqual(code, 0, err)
        args = self.unite(etat)
        props = self.proprietes(args)
        self.assertNotIn("PrivateNetwork=yes", props)
        self.assertEqual([p for p in props if p.startswith("IPAddress")],
                         ["IPAddressDeny=any", f"IPAddressAllow={D.IP_MANDATAIRE}/32"])
        self.assertIn(f"--setenv=HTTPS_PROXY=http://{D.IP_MANDATAIRE}:3128", args)
        self.assertIn(f"sudo -n {CHEMIN_RACINE} lancer {ID_B} 4 8192 1800 {VERSION} licence", self.journal)
        self.assertIn(f"docker rm -f mandataire-{ID_B}", self.journal)                       # fermé par l'enveloppe

    def test_arreter_arrete_l_unite(self):
        lance = self.demarrer_hote(env={"FAUX_UNITE_ATTENDRE": "1", "ENVELOPPE_SONDE_S": "0.05"})
        fin = time.time() + 30
        while self.unite(lance[3]) is None and time.time() < fin:
            time.sleep(0.05)
        self.assertIsNotNone(self.unite(lance[3]), self.journal)
        lance[0].stdin.close()                                                             # la laisse est coupée
        code, out, err, etat = self.finir_hote(lance, fermer=False)
        self.assertEqual(code, 130, err)
        self.assertEqual(err[-2], "#refus 130")
        self.assertIn(f"sudo -n {CHEMIN_RACINE} arreter {ID}", self.journal)
        self.assertIn(f"systemctl stop unity-tests-{ID}.service", self.journal)
        self.assertEqual(self.campagnes(), [])
        # arreter seul : l'unité de cet identifiant, rien d'autre.
        r, _ = self.direct("arreter", ID_B)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"systemctl stop unity-tests-{ID_B}.service", self.journal)

    def test_version_absente_refusee(self):
        r, etat = self.direct("lancer", ID, "4", "8192", "1800", REPLI, "aucun",
                              entree=(json.dumps(U.COMMANDE_UNITY) + "\n").encode())
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertIn(REPLI, r.stderr.decode())
        self.assertIsNone(self.unite(etat))
        self.assertEqual(self.campagnes(), [])
        code, out, err, etat = self.hote("-", REPLI, ident=ID_B)                                 # par l'enveloppe : refus 77
        self.assertEqual(code, 77, err)
        self.assertEqual(err[-2], "#refus 77")
        self.assertIsNone(self.unite(etat))
        # Sans l'utilisateur unity-tests : 77 aussi.
        r, etat = self.direct("lancer", E.ident(72), "4", "8192", "1800", VERSION, "aucun",
                              entree=(json.dumps(U.COMMANDE_UNITY) + "\n").encode(), env={"FAUX_SANS_UNITY": "1"})
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertIsNone(self.unite(etat))

    def test_avertissement_version_de_repli(self):
        self.editeur(REPLI)
        code, out, err, etat = self.hote("-", REPLI)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f"Éditeur {REPLI} au lieu de {VERSION} : résultats indicatifs")
        self.assertIn(f"sudo -n {CHEMIN_RACINE} lancer {ID} 4 8192 1800 {REPLI} aucun", self.journal)
        self.assertIn(f"BindReadOnlyPaths={self.rm}/opt/unity/editors/{REPLI}", self.proprietes(self.unite(etat)))
        for ident, plus in ((ID_B, ()), (E.ident(73), ("-", VERSION))):                       # la version du projet : rien à dire
            with self.subTest(plus=plus):
                code, out, err, _ = self.hote(*plus, ident=ident)
                self.assertEqual(code, 0, err)
                self.assertNotIn("au lieu de", out)

    def test_code_de_l_unite_rendu_sans_refus(self):
        for i, code_unite in enumerate((2, 81, 82)):
            with self.subTest(code=code_unite):
                code, out, err, _ = self.hote(ident=E.ident(80 + i), env={"FAUX_UNITE_CODE": str(code_unite)})
                self.assertEqual(code, code_unite, err)
                self.assertNotIn(f"#refus {code_unite}", err)

    def test_library_en_overlay_sinon_copie(self):
        cache = self.r / "var" / "lib" / "unity-tests" / "library" / VERSION
        _ecrire(cache / "ArtifactDB", "cache")
        code, out, err, etat = self.hote()
        self.assertEqual(code, 0, err)
        c = self.campagne()
        self.assertIn(f"mount -t overlay overlay -o lowerdir={self.rm}/var/lib/unity-tests/library/{VERSION},"
                      f"upperdir={c}/library-haut,workdir={c}/library-ov {c}/work/Library", self.journal)
        self.assertIn(f"cp -a --reflink=auto -- {self.rm}/var/lib/unity-tests/library/{VERSION}/. {c}/work/Library/",
                      self.journal)                                                          # overlay refusé : copie
        self.assertEqual(self.campagnes(), [])
        self.assertTrue((cache / "ArtifactDB").exists())                                    # le cache figé n'est jamais touché

    def test_balayage_des_unites_anciennes(self):
        vieille = "t20261122-010000-0000"
        try:
            demarre_depuis_s = float(Path("/proc/uptime").read_text().split()[0])
        except (OSError, ValueError, IndexError):
            self.skipTest("/proc/uptime illisible ici")
        if demarre_depuis_s < 6 * 3600 + 60:
            self.skipTest("machine démarrée depuis moins de 6 h : aucune unité ne peut être plus ancienne")
        r, _ = self.direct("lancer", ID, "4", "8192", "1800", VERSION, "aucun",
                           entree=(json.dumps(U.COMMANDE_UNITY) + "\n").encode(),
                           env={"FAUX_UNITES": f"unity-tests-{vieille}.service unity-tests-x;id.service"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"systemctl stop unity-tests-{vieille}.service", self.journal)
        self.assertNotIn("x;id", self.journal.replace("list-units", ""))

    def test_sonde_d_audit(self):
        r, etat = self.direct("auditer", ID, "4", "8192", "1800", VERSION, "aucun")
        self.assertEqual(r.returncode, 0, r.stderr)
        args = self.unite(etat)
        self.assertEqual(args[args.index("--") + 1:], ["/bin/bash", f"{self.rm}/usr/local/lib/myiafactory/sonde-bac-a-sable.sh"])
        self.assertIn("PrivateNetwork=yes", self.proprietes(args))
        self.assertIn(f"--setenv=MYIAFACTORY_SONDE_PRINCIPAL={self.h}", args)
        self.assertFalse((self.home / ".myiafactory" / "unity-bac-a-sable.version").exists())   # l'audit J14 seulement
        # La sonde, hors unité : des échecs constatés, une ligne par contrôle, jamais la licence.
        s = subprocess.run(["bash", SONDE.as_posix()], capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, HOME=self.h, MYIAFACTORY_SONDE_PRINCIPAL=self.h, MYIAFACTORY_SONDE_RESEAU="aucun"))
        self.assertEqual(s.returncode, 1, s.stdout)
        for ligne in s.stdout.splitlines():
            self.assertRegex(ligne, r"^(ok|echec|bilan) ")
        self.assertIn("echec utilisateur", s.stdout)
        self.assertNotIn(FACTICE, s.stdout + s.stderr)

    # --- étape unity_bac_a_sable de mise_en_place.sh ------------------------------------------------------------------
    def etape(self, simuler=False, env=None):
        etat = self.t / "etat" / "etape"
        etat.mkdir(parents=True, exist_ok=True)
        for d in ("agent-identifiants", ".ssh", "taches"):
            p = self.home / d
            p.mkdir(exist_ok=True)
            p.chmod(0o700)
        e = dict(self.env, FAUX_ETAT=etat.as_posix(), SERVEUR_OVH_DIR=SERVEUR.as_posix(), DISQUE_LIBRE_GO="50", **(env or {}))
        args = ["bash", MISE.as_posix(), "--etape", "unity_bac_a_sable"] + (["--simuler"] if simuler else [])
        r = subprocess.run(args, capture_output=True, text=True, env=e, timeout=60)
        return json.loads(r.stdout.strip().splitlines()[-1]), etat

    def test_etape_simulee(self):
        d, _ = self.etape(simuler=True)
        self.assertEqual((d["etape"], d["statut"]), ("unity_bac_a_sable", "a_faire"))
        self.assertTrue(d["detail"].startswith("Simulation"), d)
        for interdit in ("useradd", "sudo", "setfacl", "visudo", "systemctl"):
            self.assertNotIn(interdit, self.journal)
        self.assertIn("unity_bac_a_sable", MISE.read_text(encoding="utf-8").split("\n")[7])     # ligne d'usage

    def test_etape_installe_sans_marqueur(self):
        d, etat = self.etape(env={"FAUX_SANS_UNITY_AVANT": "1"})
        self.assertEqual(d["statut"], "fait", d)
        j = self.journal
        self.assertIn("sudo -n install -o root -g root -m 0755 " + SERVEUR.as_posix() + "/unity-bac-a-sable.sh " + CHEMIN_RACINE, j)
        self.assertIn("sudo -n install -d -o unity-tests -g unity-tests -m 0700 /var/lib/unity-tests", j)
        self.assertEqual((etat / "sudoers").read_text(encoding="utf-8"),
                         f"principal ALL=(root) NOPASSWD: {CHEMIN_RACINE}\n")                  # le script exact, rien d'autre
        self.assertIn("sudo -n install -o root -g root -m 0440 ", j)
        acl = [x for x in j.splitlines() if x.startswith("setfacl ")]
        self.assertEqual(sorted(acl), sorted([f"setfacl -m u:unity-tests:rx -- {self.h}/.config/unity3d/Unity/licenses",
                                              f"setfacl -d -m u:unity-tests:r -- {self.h}/.config/unity3d/Unity/licenses",
                                              f"setfacl -m u:unity-tests:r -- {self.h}/.config/unity3d/Unity/licenses/"
                                              "UnityEntitlementLicense.xml",
                                              f"setfacl -m u:unity-tests:r -- {self.h}/.local/share/unity3d/Unity/Unity_lic.ulf"]))
        self.assertFalse((self.home / ".myiafactory" / "unity-bac-a-sable.version").exists())   # écrit par l'audit J14 seulement
        self.assertNotIn(FACTICE, j + json.dumps(d))
        # Utilisateur absent : créé système, sans shell ni répertoire créé ; membre d'un groupe sensible : bloqué.
        self.journal_fichier.unlink()
        d, _ = self.etape(env={"FAUX_SANS_UNITY": "1"})
        self.assertIn("sudo -n useradd --system --user-group --home-dir /var/lib/unity-tests --no-create-home "
                      "--shell /usr/sbin/nologin unity-tests", self.journal)
        d, _ = self.etape(env={"FAUX_GROUPES_UNITY": "unity-tests docker"})
        self.assertEqual(d["statut"], "bloque", d)
        self.assertIn("docker", d["detail"])

    @unittest.skipIf(os.name == "nt", "droits de fichier sans effet sous Windows")
    def test_etape_refuse_dossiers_lisibles(self):
        for d in ("agent-identifiants", ".ssh", "taches"):
            with self.subTest(dossier=d):
                self.etape()                                                               # remet tout en 0700
                if self.journal_fichier.exists():
                    self.journal_fichier.unlink()
                (self.home / d).chmod(0o755)
                r = subprocess.run(["bash", MISE.as_posix(), "--etape", "unity_bac_a_sable"], capture_output=True, text=True,
                                   timeout=60, env=dict(self.env, FAUX_ETAT=(self.t / "etat").as_posix(),
                                                        SERVEUR_OVH_DIR=SERVEUR.as_posix(), DISQUE_LIBRE_GO="50"))
                resultat = json.loads(r.stdout.strip().splitlines()[-1])
                self.assertEqual(resultat["statut"], "bloque", resultat)
                self.assertIn(d, resultat["detail"])
                self.assertIn("700", resultat["detail"])
                self.assertNotIn("useradd", self.journal)
                self.assertNotIn("sudo", self.journal)
                (self.home / d).chmod(0o700)

    def test_sudoers_verifie(self):
        for mode in ("global", "fichier"):
            with self.subTest(echec=mode):
                if self.journal_fichier.exists():
                    self.journal_fichier.unlink()
                d, _ = self.etape(env={"FAUX_VISUDO_ECHEC": mode})
                self.assertEqual(d["statut"], "bloque", d)
                self.assertIn("visudo", d["detail"])
                lignes = self.journal.splitlines()
                retrait = "sudo -n rm -f /etc/sudoers.d/myiafactory-unity"
                self.assertIn(retrait, lignes)
                pose = [i for i, x in enumerate(lignes) if x.startswith("sudo -n install -o root -g root -m 0440 ")]
                if mode == "global":                                                       # posée, refusée : retirée APRÈS
                    self.assertEqual(len(pose), 1)
                    self.assertGreater(lignes.index(retrait), pose[0])
                else:                                                                      # refusée avant d'être posée
                    self.assertEqual(pose, [])
                self.assertFalse([x for x in lignes if x.startswith("setfacl")])           # rien d'autre après le refus

    # --- installation : fichiers déposés, marqueur ----------------------------------------------------------------------
    def test_fichiers_de_l_installation(self):
        self.assertEqual(inst.FICHIERS_ETAPE["unity_bac_a_sable"],
                         ("unity-bac-a-sable.sh", "sonde-bac-a-sable.sh", "images/tests/entree-tests.sh",
                          "images/tests/entree-unity.sh"))
        self.assertEqual(inst.MARQUEURS["unity-bac-a-sable"],
                         ("unity_bac_a_sable", "$HOME/.myiafactory/unity-bac-a-sable.version"))
        self.assertRegex(inst.empreinte_etape("unity_bac_a_sable"), r"^bac_a_sable=A;utilisateur=unity-tests;fichiers=[0-9a-f]{16}$")
        # 14g : entree-unity.sh et construire_image_tests.sh déposés avec l'étape tests_image, hors de l'empreinte de l'image.
        self.assertIn("images/tests/entree-unity.sh", inst.FICHIERS_ETAPE["tests_image"])
        self.assertIn("taches/construire_image_tests.sh", inst.FICHIERS_ETAPE["tests_image"])
        self.assertEqual(inst.EMPREINTE_FICHIERS["tests_image"], ("images/tests/Dockerfile", "images/tests/entree-tests.sh"))
        for etape in ("unity_bac_a_sable", "tests_image"):                                # fichiers présents, archivables
            self.assertTrue(inst._archive_fichiers(etape))
        # Le script racine, la sonde et l'étape : fins de ligne LF (bash refuse un \r dans un script déposé tel quel).
        for f in (SCRIPT_RACINE, SONDE):
            self.assertNotIn(b"\r", f.read_bytes())


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEntreeUnityLiee(U.TestEntreeUnity):
    """entree-unity.sh dans l'unité (option A) : licence LIÉE dans le HOME (jamais copiée), éditeur de l'hôte."""

    def setUp(self):
        U.TestEntreeUnity.setUp(self)
        shutil.rmtree(self.t / "licence")                                     # pas de montage /licence sur l'hôte
        self.droits = self.t / "home" / ".config" / "unity3d" / "Unity" / "licenses" / "UnityEntitlementLicense.xml"
        _ecrire(self.droits, FACTICE, 0o640)                                  # comme liée par systemd (lecture seule)
        editeur = self.t / "editeurs" / REPLI / "Editor" / "Unity"
        _ecrire(editeur, '#!/bin/sh\necho "$0" > "$FAUX_UNITY/editeur"\nexec unity-editor "$@"\n', 0o755)
        self.env.update(MYIAFACTORY_UNITY_LICENCE="liee", MYIAFACTORY_UNITY_EDITEUR=editeur.as_posix())

    def test_licence_liee_ni_copiee_ni_modifiee(self):
        avant = self.droits.stat()
        r = self.lancer("ok\n", U.xml_resultats(1, 1, 0))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(FACTICE, r.stdout + r.stderr)
        # Le seul fichier de licence du HOME est celui qui était lié ; aucune copie dans la campagne.
        porteurs = [p for d in ("home", "work", "tmp", "entree") for p in (self.t / d).rglob("*")
                    if p.is_file() and FACTICE in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(porteurs, [self.droits])
        if os.name != "nt":
            self.assertEqual(self.droits.stat().st_mode & 0o777, 0o640)        # jamais chmod (le montage est en lecture seule)
        self.assertEqual(self.droits.stat().st_mtime, avant.st_mtime)
        # L'éditeur de l'hôte remplace unity-editor ; -projectPath vise la copie extraite de la campagne.
        self.assertTrue((self.faux_unity / "editeur").exists())
        args = (self.faux_unity / "args.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(args[args.index("-projectPath") + 1], (self.t / "work").as_posix())

    def test_licence_liee_absente_81(self):
        self.droits.unlink()
        r = self.lancer("ok\n", U.xml_resultats(1, 1, 0))
        self.assertEqual(r.returncode, 81, r.stderr)

    # Les tests hérités qui supposent la copie depuis /licence ne s'appliquent pas à la licence liée.
    test_journal_unity_filtre = None
    test_licence_refusee_code_81 = None


if __name__ == "__main__":
    unittest.main()
