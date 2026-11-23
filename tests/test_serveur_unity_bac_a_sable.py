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
          "LimitNOFILE", "RuntimeMaxSec",
          # relecture 14h (I4)
          "PrivateIPC", "RemoveIPC", "TemporaryFileSystem", "LimitCORE", "ProtectControlGroups", "SystemCallArchitectures",
          "RestrictRealtime", "ProtectHostname", "ProtectClock", "UMask", "RestrictAddressFamilies"}
FIXES = {"User": "unity-tests", "ProtectHome": "tmpfs", "ProtectSystem": "strict", "PrivateTmp": "yes", "PrivateDevices": "yes",
         "NoNewPrivileges": "yes", "CapabilityBoundingSet": "", "ProtectProc": "invisible", "ProcSubset": "pid",
         "ProtectKernelTunables": "yes", "ProtectKernelModules": "yes", "ProtectKernelLogs": "yes", "RestrictNamespaces": "yes",
         "RestrictSUIDSGID": "yes", "LockPersonality": "yes", "SystemCallFilter": "@system-service",
         "InaccessiblePaths": "-/run/docker.sock -/var/run/docker.sock -/dev/mqueue", "MemorySwapMax": "0", "TasksMax": "2048",
         "LimitNOFILE": "8192", "PrivateIPC": "yes", "RemoveIPC": "yes", "TemporaryFileSystem": "/dev/shm:size=512M,mode=1777",
         "LimitCORE": "0", "ProtectControlGroups": "yes", "SystemCallArchitectures": "native", "RestrictRealtime": "yes",
         "ProtectHostname": "yes", "ProtectClock": "yes", "UMask": "0077"}
TRAVAIL = "10"

SYSTEMD_RUN = r'''n=0; while [ -e "$FAUX_ETAT/systemd-run-$n.txt" ]; do n=$((n + 1)); done
printf '%s\n' "$@" > "$FAUX_ETAT/systemd-run-$n.txt"
echo "systemd-run $*" >> "$FAUX_JOURNAL"
cat > "$FAUX_ETAT/unite-entree-$n"
c=""; for a in "$@"; do case "$a" in --setenv=ENTREE_TESTS_RACINE=*) c="${a#--setenv=ENTREE_TESTS_RACINE=}" ;; esac; done
case "${FAUX_PROJET_HOSTILE:-}" in                       # le code du projet déplace ou remplace work/
  mv) mv "$c/work" "$c/x" && mkdir "$c/work" ;;
  lien) rm -rf "$c/work" && ln -s "$FAUX_AILLEURS" "$c/work" ;;
esac
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
  list-units) for u in ${FAUX_UNITES:-}; do echo "$u loaded active running x"; done ;;
  show) echo "${FAUX_DEPUIS_US:-1}" ;;
  is-active) [ -n "${FAUX_ACTIF:-}" ] && exit 0; exit 3 ;;
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
# Montages : $FAUX_ETAT/montes (un chemin par ligne) ; mount l'ajoute (FAUX_MOUNT_CODE=0), umount le retire, findmnt le lit.
MOUNT = r'''echo "mount $*" >> "$FAUX_JOURNAL"
c="${FAUX_MOUNT_CODE:-32}"; [ "$c" = 0 ] || exit "$c"
[ "$1" = --make-private ] && exit 0
for a in "$@"; do p="$a"; done; echo "$p" >> "$FAUX_ETAT/montes"'''
UMOUNT = r'''echo "umount $*" >> "$FAUX_JOURNAL"
for a in "$@"; do p="$a"; done
[ -f "$FAUX_ETAT/montes" ] && { grep -vxF -- "$p" "$FAUX_ETAT/montes" > "$FAUX_ETAT/montes.tmp"; mv "$FAUX_ETAT/montes.tmp" "$FAUX_ETAT/montes"; }
exit 0'''
FINDMNT = r'''for a in "$@"; do p="$a"; done
[ -f "$FAUX_ETAT/montes" ] && grep -qxF -- "$p" "$FAUX_ETAT/montes" && { echo "$p"; exit 0; }
exit 1'''
DU_CAMPAGNE = ('for a in "$@"; do p="$a"; done\n'
               'case "$p" in */campagnes/*) printf \'%s\\t%s\\n\' "${FAUX_DU_CAMPAGNE_KO:-4}" "$p"; exit 0 ;; esac\n' + D.DU)
FAUX = dict(D.FAUX, **{"systemd-run": SYSTEMD_RUN, "systemctl": SYSTEMCTL, "sudo": SUDO, "id": ID_FAUX, "visudo": VISUDO,
                       "setfacl": JOURNALISER.format(nom="setfacl", code=0), "useradd": JOURNALISER.format(nom="useradd", code=0),
                       "mount": MOUNT, "umount": UMOUNT, "findmnt": FINDMNT, "cp": CP, "du": DU_CAMPAGNE})


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
        (r / "run").mkdir(parents=True)
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
        self.directs = getattr(self, "directs", 0) + 1                                       # un dossier d'état par appel
        etat = self.t / "etat" / f"direct-{self.directs}"
        etat.mkdir(parents=True, exist_ok=True)
        e = dict(self.env, FAUX_ETAT=etat.as_posix(), **(env or {}))
        r = subprocess.run(["bash", SCRIPT_RACINE.as_posix(), *args], input=entree, capture_output=True, env=e, timeout=60)
        return r, etat

    def lancer_direct(self, ident=ID, version=VERSION, reseau="aucun", env=None, mode="lancer"):
        entree = (json.dumps(U.COMMANDE_UNITY) + "\n").encode() if mode == "lancer" else b""
        return self.direct(mode, ident, "4", "8192", "1800", version, reseau, TRAVAIL, entree=entree, env=env)

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
        self.assertIn("RestrictAddressFamilies=AF_UNIX", props)                             # reseau=aucun : AF_UNIX seul
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
        # durée de la campagne moins l'attente (bornée, décomptée) moins 5 s de marge : l'enveloppe ne coupe jamais la première
        duree = [int(p.split("=", 1)[1]) for p in props if p.startswith("RuntimeMaxSec=")]
        self.assertEqual(len(duree), 1)
        self.assertTrue(1785 <= duree[0] <= 1795, duree)
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
        self.assertEqual((etat / "unite-entree-0").read_bytes(), D.TAR_NODE)
        self.assertIn("sortie de l'unité", out)
        self.assertIn("| erreur de l'unité", err)
        self.assertIn(f"sudo -n {CHEMIN_RACINE} lancer {ID} 4 8192 1800 {VERSION} aucun {TRAVAIL}", self.journal)
        self.assertNotIn("docker run", self.journal)
        self.assertNotIn("docker image inspect", self.journal)
        self.assertEqual(self.campagnes(), [])
        self.assertFalse((self.home / "tests" / ID).exists())
        self.assertNotIn(FACTICE, self.journal + out + "\n".join(err))
        self.assertIn(f"flock -n 9", self.journal)                                         # le verrou de /run/myiafactory
        self.assertTrue((self.r / "run" / "myiafactory" / "unity-bac-a-sable.verrou").exists())

    def test_arguments_hostiles_refuses(self):
        # I6 : tout refus du script racine rend 77 (jamais 2, le code « des tests échouent »).
        bons = [ID, "4", "8192", "1800", VERSION, "aucun", TRAVAIL]
        mauvais = {0: ["../x", "t20261123-101500-ab12/../x", "t20261123-101500-AB12", "t20261123-101500-ab12\nx", "$(id)"],
                   1: ["0", "65", "04", "4;id"], 2: ["255", "65537", "08192", "-1"], 3: ["0", "3601", "01800", "1e3"],
                   4: ["6000.6.7f1;id", "6000.6.7f1 ", "../6000.6.7f1", "6000.6.7", "x6000.6.7f1", "6000.6.7f1/.."],
                   5: ["bridge", "host", "aucun;id", "LICENCE", ""], 6: ["0", "201", "010", "1;id"]}
        for i, valeurs in mauvais.items():
            for v in valeurs:
                with self.subTest(position=i, valeur=v):
                    args = list(bons)
                    args[i] = v
                    r, etat = self.direct("lancer", *args, entree=(json.dumps(U.COMMANDE_UNITY) + "\n").encode())
                    self.assertEqual(r.returncode, 77, r.stderr)
                    self.assertIsNone(self.unite(etat))
        for extra in (["lancer", *bons, "x"], ["lancer", *bons[:6]], ["arreter", "../x"], ["arreter", ID, "x"],
                      ["inconnu", *bons], []):
            with self.subTest(args=extra):
                r, etat = self.direct(*extra)
                self.assertEqual(r.returncode, 77, r.stderr)
        for commande in ('["bash","-c","id"]', '["unity-editor"', "x", '["unity-editor","a\tb"]', "[" + "x" * 4100 + "]"):
            with self.subTest(commande=commande):
                r, etat = self.direct("lancer", *bons, entree=(commande + "\n").encode())
                self.assertEqual(r.returncode, 77, r.stderr)
        # Mode unite : instantané non reçu (dossier de campagne absent) -> 77, jamais 2 ni 70.
        r, _ = self.direct("unite", env={"ENTREE_TESTS_RACINE": f"{self.rm}/nulle-part/{ID}"})
        self.assertEqual(r.returncode, 77, r.stderr)
        # Identifiant déjà pris : 77, la campagne existante n'est pas touchée.
        pris = self.r / "var" / "lib" / "unity-tests" / "campagnes" / ID
        (pris / "work").mkdir(parents=True)
        r, etat = self.lancer_direct()
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertTrue((pris / "work").exists())
        shutil.rmtree(pris)
        self.assertNotIn("systemd-run", self.journal)
        self.assertEqual(self.campagnes(), [])
        # Par l'enveloppe : une version de repli hors motif est refusée avant tout (aucun sudo, rien écrit).
        code, out, err, etat = self.hote("-", "6000.6.7f1;id")
        self.assertEqual(code, 2, err)
        self.assertEqual(err[-2], "#refus 2")
        self.assertNotIn(CHEMIN_RACINE, self.journal)
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
        self.ulf.unlink()
        code, out, err, etat = self.hote(ident=ID_B)
        self.assertEqual(code, 0, err)
        self.assertFalse([p for p in self.proprietes(self.unite(etat)) if ".ulf" in p])
        shutil.rmtree(self.droits)
        r, etat = self.lancer_direct(E.ident(70))
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertIsNone(self.unite(etat))
        if os.name != "nt":
            ailleurs = self.t / "ailleurs"
            ailleurs.mkdir()
            (ailleurs / "secret").write_text("x", encoding="utf-8")
            self.droits.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(ailleurs, self.droits)
            r, etat = self.lancer_direct(E.ident(71))
            self.assertEqual(r.returncode, 77, r.stderr)

    def test_reseau_prive_par_defaut(self):
        code, out, err, etat = self.hote()
        self.assertEqual(code, 0, err)
        props = self.proprietes(self.unite(etat))
        self.assertIn("PrivateNetwork=yes", props)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", props)
        self.assertFalse([p for p in props if p.startswith("IPAddress")], props)
        self.assertFalse([a for a in self.unite(etat) if "PROXY" in a.upper()])
        code, out, err, etat = self.hote("license.unity3d.com", ident=ID_B, licence="B3")
        self.assertEqual(code, 0, err)
        args = self.unite(etat)
        props = self.proprietes(args)
        self.assertNotIn("PrivateNetwork=yes", props)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", props)
        self.assertEqual([p for p in props if p.startswith("IPAddress")],
                         ["IPAddressDeny=any", f"IPAddressAllow={D.IP_MANDATAIRE}/32"])
        self.assertIn(f"--setenv=HTTPS_PROXY=http://{D.IP_MANDATAIRE}:3128", args)
        self.assertIn(f"sudo -n {CHEMIN_RACINE} lancer {ID_B} 4 8192 1800 {VERSION} licence {TRAVAIL}", self.journal)
        self.assertIn(f"docker rm -f mandataire-{ID_B}", self.journal)

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
        r, _ = self.direct("arreter", ID_B)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"systemctl stop unity-tests-{ID_B}.service", self.journal)

    def test_version_absente_refusee(self):
        r, etat = self.lancer_direct(version=REPLI)
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertIn(REPLI, r.stderr.decode())
        self.assertIsNone(self.unite(etat))
        self.assertEqual(self.campagnes(), [])
        code, out, err, etat = self.hote("-", REPLI, ident=ID_B)                            # par l'enveloppe : refus 77
        self.assertEqual(code, 77, err)
        self.assertEqual(err[-2], "#refus 77")
        self.assertIsNone(self.unite(etat))
        r, etat = self.lancer_direct(E.ident(72), env={"FAUX_SANS_UNITY": "1"})
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertIsNone(self.unite(etat))

    def test_avertissement_version_de_repli(self):
        self.editeur(REPLI)
        code, out, err, etat = self.hote("-", REPLI)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f"Éditeur {REPLI} au lieu de {VERSION} : résultats indicatifs")
        self.assertIn(f"sudo -n {CHEMIN_RACINE} lancer {ID} 4 8192 1800 {REPLI} aucun {TRAVAIL}", self.journal)
        self.assertIn(f"BindReadOnlyPaths={self.rm}/opt/unity/editors/{REPLI}", self.proprietes(self.unite(etat)))
        for ident, plus in ((ID_B, ()), (E.ident(73), ("-", VERSION))):
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

    def test_travail_au_dela_de_travail_go(self):
        code, out, err, etat = self.hote(env={"FAUX_DU_CAMPAGNE_KO": str(11 * 1048576), "FAUX_UNITE_ATTENDRE": "1",
                                              "BAC_A_SABLE_DU_S_TEST": "0.1"})
        self.assertEqual(code, 74, err)
        self.assertEqual(err[-2], "#refus 74")
        self.assertIn(f"systemctl stop unity-tests-{ID}.service", self.journal)
        self.assertEqual(self.campagnes(), [])

    def test_library_copiee_si_overlay_refuse(self):
        cache = self.r / "var" / "lib" / "unity-tests" / "library" / VERSION
        _ecrire(cache / "ArtifactDB", "cache")
        code, out, err, etat = self.hote()
        self.assertEqual(code, 0, err)
        c = self.campagne()
        self.assertIn(f"mount -t overlay overlay -o lowerdir={self.rm}/var/lib/unity-tests/library/{VERSION},"
                      f"upperdir={c}/library-haut,workdir={c}/library-ov {c}/library", self.journal)
        self.assertIn(f"cp -a --reflink=auto -- {self.rm}/var/lib/unity-tests/library/{VERSION}/. {c}/library/", self.journal)
        self.assertNotIn("umount", self.journal)                                           # rien de monté : rien à démonter
        self.assertEqual(self.campagnes(), [])
        self.assertTrue((cache / "ArtifactDB").exists())

    def test_library_overlay_demonte_par_le_chemin_note(self):
        # I2/I3 : le montage est HORS de work/ (sous le contrôle du projet) ; il est démonté par le chemin noté à la pose
        # (findmnt), sans suivre de lien : un projet qui déplace work/ ou le remplace par un lien ne fait rien démonter d'autre.
        cache = self.r / "var" / "lib" / "unity-tests" / "library" / VERSION
        _ecrire(cache / "ArtifactDB", "cache")
        ailleurs = self.t / "ailleurs"
        ailleurs.mkdir()
        autre = f"{E._msys(ailleurs)}/Library"
        for i, hostile in enumerate(("", "mv", "lien")):
            with self.subTest(hostile=hostile):
                ident = E.ident(90 + i)
                etat = self.t / "etat" / ident
                etat.mkdir(parents=True)
                (etat / "montes").write_text(autre + "\n", encoding="utf-8")              # un autre montage, joignable par un lien
                avant = len(self.journal.splitlines())
                code, out, err, _ = self.hote(ident=ident, env={"FAUX_MOUNT_CODE": "0", "FAUX_PROJET_HOSTILE": hostile,
                                                                "FAUX_AILLEURS": E._msys(ailleurs)})
                self.assertEqual(code, 0, err)
                c = self.campagne(ident)
                demontages = [x for x in self.journal.splitlines()[avant:] if x.startswith("umount")]
                self.assertEqual(demontages, [f"umount -c -- {c}/library"])
                self.assertEqual((etat / "montes").read_text(encoding="utf-8").split(), [autre])
        self.assertEqual(self.campagnes(), [])
        self.assertTrue((cache / "ArtifactDB").exists())

    def test_unites_orphelines_arretees_et_campagne_occupee(self):
        # I1 : sous le verrou, une unité dont le script n'existe plus est arrêtée avant le départ.
        orpheline = "t20261122-010000-0000"
        r, _ = self.lancer_direct(env={"FAUX_UNITES": f"unity-tests-{orpheline}.service unity-tests-x;id.service"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"systemctl stop unity-tests-{orpheline}.service", self.journal)
        self.assertNotIn("x;id", self.journal.replace("list-units", ""))
        # Une unité active dont le script vit encore : on attend (borné), puis refus 77 ; elle n'est jamais arrêtée.
        if os.name == "nt":
            self.skipTest("/proc/<pid>/cmdline absent sous Windows")
        vivante = "t20261122-020000-0000"
        p = subprocess.Popen(["bash", "-c", "sleep 30; :", "unity-bac-a-sable.sh", vivante])   # « ; : » : bash reste (pas d'exec)
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        run = self.r / "run" / "myiafactory"
        run.mkdir(parents=True, exist_ok=True)
        (run / f"unity-tests-{vivante}.pid").write_text(f"{p.pid}\n", encoding="utf-8")
        recente = max(1, int(float(Path("/proc/uptime").read_text().split()[0]) * 1e6) - 10_000_000)   # active depuis 10 s
        r, etat = self.lancer_direct(E.ident(74), env={"FAUX_UNITES": f"unity-tests-{vivante}.service", "FAUX_ACTIF": "1",
                                                       "BAC_A_SABLE_ATTENTE_MAX_TEST": "2", "FAUX_DEPUIS_US": str(recente)})
        self.assertEqual(r.returncode, 77, r.stderr)
        self.assertIn("occupé", r.stderr.decode())
        self.assertIsNone(self.unite(etat))
        self.assertNotIn(f"systemctl stop unity-tests-{vivante}.service", self.journal)

    @unittest.skipIf(os.name == "nt", "droits de fichier sans effet sous Windows")
    def test_dossiers_prives_reverifies_a_chaque_lancement(self):
        for d in ("agent-identifiants", ".ssh", "taches"):
            with self.subTest(dossier=d):
                p = self.home / d
                p.mkdir(exist_ok=True)
                p.chmod(0o755)
                r, etat = self.lancer_direct(E.ident(75))
                self.assertEqual(r.returncode, 77, r.stderr)
                self.assertIn(d, r.stderr.decode())
                self.assertIsNone(self.unite(etat))
                p.chmod(0o700)

    def test_sonde_d_audit(self):
        r, etat = self.lancer_direct(mode="auditer")
        self.assertEqual(r.returncode, 0, r.stderr)
        args = self.unite(etat)
        self.assertEqual(args[args.index("--") + 1:], ["/bin/bash", f"{self.rm}/usr/local/lib/myiafactory/sonde-bac-a-sable.sh"])
        self.assertIn("PrivateNetwork=yes", self.proprietes(args))
        self.assertIn(f"--setenv=MYIAFACTORY_SONDE_PRINCIPAL={self.h}", args)
        self.assertFalse((self.home / ".myiafactory" / "unity-bac-a-sable.version").exists())   # l'audit J14 seulement
        r, etat = self.lancer_direct(E.ident(76), reseau="licence", mode="auditer")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"--setenv=MYIAFACTORY_SONDE_MANDATAIRE={D.IP_MANDATAIRE}", self.unite(etat))
        # La sonde, hors unité : des échecs constatés, une ligne par contrôle, jamais la licence ; en mode licence, le réseau est
        # ÉPROUVÉ (connexion hors mandataire, liste des sockets Unix), jamais un « ok » sans essai.
        for reseau in ("aucun", "licence"):
            with self.subTest(reseau=reseau):
                s = subprocess.run(["bash", SONDE.as_posix()], capture_output=True, text=True, timeout=60,
                                   env=dict(os.environ, HOME=self.h, MYIAFACTORY_SONDE_PRINCIPAL=self.h,
                                            MYIAFACTORY_SONDE_RESEAU=reseau, MYIAFACTORY_SONDE_MANDATAIRE="192.0.2.1",
                                            MYIAFACTORY_SONDE_DELAI_S="2"))
                self.assertEqual(s.returncode, 1, s.stdout)
                for ligne in s.stdout.splitlines():
                    self.assertRegex(ligne, r"^(ok|echec|info|bilan) ")
                self.assertIn("echec utilisateur", s.stdout)
                self.assertNotIn(FACTICE, s.stdout + s.stderr)
                self.assertRegex(s.stdout, r"(?m)^(ok|echec) reseau-hors-mandataire")
                if reseau == "licence":
                    self.assertRegex(s.stdout, r"(?m)^(ok|echec) sockets-unix")
                    self.assertNotRegex(s.stdout, r"(?m)^ok reseau-licence \(")              # l'ancien « ok » sans essai

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
        self.assertIn("sudo -n install -d -o root -g root -m 0711 /var/lib/unity-tests/campagnes", j)
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
