#!/usr/bin/env bash
# Sonde d'audit du bac à sable Unity (conception § 5.16, option A ; audit du jalon J14, tâche 14h). Lancée DANS l'unité, à la
# place de l'éditeur, par `sudo -n /usr/local/lib/myiafactory/unity-bac-a-sable.sh auditer <id> <cpus> <memoire_mo> <duree_s>
# <version> <reseau>` : MÊMES propriétés que pour une campagne. Elle constate (jamais ne suppose) ce que le code d'un projet
# verrait. Une ligne par contrôle : `ok <nom>` ou `echec <nom> : <raison>` ; code 0 si tout est ok, 1 sinon. Elle n'écrit AUCUN
# marqueur : ~/.myiafactory/unity-bac-a-sable.version est écrit par l'audit J14 (le Directeur ou son agent), après lecture de ce
# résultat. La licence n'est JAMAIS lue : seulement `test -r` / `test -w` sur ses noms.
# Variables posées par le script racine : HOME (dans la campagne), MYIAFACTORY_SONDE_PRINCIPAL (le dossier de l'utilisateur
# principal), MYIAFACTORY_SONDE_RESEAU (aucun|licence), MYIAFACTORY_UNITY_EDITEUR, ENTREE_TESTS_RACINE (la campagne).
set -u
exec </dev/null
export LC_ALL=C

ECHECS=0
ok() { printf 'ok %s\n' "$1"; }
ko() { printf 'echec %s : %s\n' "$1" "$2"; ECHECS=$((ECHECS + 1)); }
verifier() { local nom="$1" raison="$2"; shift 2; if "$@"; then ok "$nom"; else ko "$nom" "$raison"; fi; }

PRINCIPAL="${MYIAFACTORY_SONDE_PRINCIPAL:-}"
RESEAU="${MYIAFACTORY_SONDE_RESEAU:-aucun}"
C="${ENTREE_TESTS_RACINE:-}"
statut() { grep -E "^$1:" /proc/self/status 2>/dev/null | awk '{ print $2 }'; }

# Identité : unity-tests, hors des groupes qui ouvrent l'hôte.
verifier utilisateur "uid autre que unity-tests" test "$(id -un 2>/dev/null)" = unity-tests
groupes=" $(id -nG 2>/dev/null) "
verifier groupes "membre de docker, kvm, sudo, adm ou lxd" \
  bash -c '[[ $1 != *" docker "* && $1 != *" kvm "* && $1 != *" sudo "* && $1 != *" adm "* && $1 != *" lxd "* ]]' _ "$groupes"
# Privilèges : aucun, et aucun moyen d'en regagner.
verifier no-new-privileges "NoNewPrivs absent" test "$(statut NoNewPrivs)" = 1
verifier capacites "CapBnd non vide" test "$(statut CapBnd)" = 0000000000000000
verifier capacites-effectives "CapEff non vide" test "$(statut CapEff)" = 0000000000000000
verifier seccomp "filtre d'appels système absent" test "$(statut Seccomp)" = 2
# Ce que l'utilisateur principal garde : invisible (ProtectHome=tmpfs).
if [ -n "$PRINCIPAL" ]; then
  for d in agent-identifiants .ssh taches tests myiafactory .config/unityhub; do
    verifier "invisible-$d" "~/$d visible depuis l'unité" test ! -e "$PRINCIPAL/$d"
  done
else
  ko principal "MYIAFACTORY_SONDE_PRINCIPAL absent : contrôle impossible"
fi
# Docker : aucune socket joignable.
for s in /run/docker.sock /var/run/docker.sock /run/containerd/containerd.sock; do
  verifier "socket-${s##*/}" "$s accessible" bash -c '! { [ -r "$1" ] || [ -w "$1" ]; } || ! [ -e "$1" ]' _ "$s"
done
# Écriture : seulement la campagne (ProtectSystem=strict, ReadWritePaths).
essai_ecriture() { ( : > "$1/.sonde-$$" ) 2>/dev/null && { rm -f -- "$1/.sonde-$$"; return 0; }; return 1; }
for d in /etc /usr /opt /var/tmp /var/lib/unity-tests /var/lib/unity-tests/campagnes; do
  verifier "lecture-seule-$d" "$d inscriptible" \
    bash -c 'if ( : > "$1/.sonde-$2" ) 2>/dev/null; then rm -f -- "$1/.sonde-$2"; exit 1; fi' _ "$d" "$$"
done
verifier campagne-inscriptible "la campagne n'est pas inscriptible" essai_ecriture "${C:-/nulle-part}"
verifier tmp-prive "/tmp inscriptible absent" essai_ecriture /tmp
# Processus : seulement les siens (ProtectProc=invisible).
moi=$(id -u)
autres=0
for p in /proc/[0-9]*; do
  u=$(stat -c %u "$p" 2>/dev/null) || continue
  [ "$u" = "$moi" ] || autres=$((autres + 1))
done
verifier processus "$autres processus d'autres utilisateurs visibles" test "$autres" = 0
# Périphériques : privés.
verifier peripheriques "/dev/kvm ou un disque visible" bash -c '! [ -e /dev/kvm ] && ! ls /dev/sd* /dev/nvme* >/dev/null 2>&1'
# Réseau.
interfaces=$(ls /sys/class/net 2>/dev/null | tr '\n' ' ')
if [ "$RESEAU" = aucun ]; then
  verifier reseau-prive "interfaces visibles : $interfaces" test "$interfaces" = "lo "
else
  ok "reseau-licence (interfaces : $interfaces ; IPAddressDeny/Allow à éprouver par une connexion à l'audit)"
fi
# Licence : lisible, non inscriptible ; jamais lue.
droits="$HOME/.config/unity3d/Unity/licenses"
ulf="$HOME/.local/share/unity3d/Unity/Unity_lic.ulf"
vue=0
if [ -d "$droits" ]; then
  for f in "$droits"/*; do
    [ -f "$f" ] || continue
    vue=1
    verifier "licence-lisible-${f##*/}" "illisible" test -r "$f"
    verifier "licence-lecture-seule-${f##*/}" "inscriptible" test ! -w "$f"
  done
fi
if [ -f "$ulf" ]; then
  vue=1
  verifier licence-ulf-lisible "illisible" test -r "$ulf"
  verifier licence-ulf-lecture-seule "inscriptible" test ! -w "$ulf"
fi
verifier licence-liee "aucun fichier de licence dans le HOME de l'unité" test "$vue" = 1
verifier editeur "éditeur absent ou non exécutable" test -x "${MYIAFACTORY_UNITY_EDITEUR:-/nulle-part}"
# Limites (cgroup v2) : relevées, et pas « max ».
cg=$(awk -F: '$1 == "0" { print $3 }' /proc/self/cgroup 2>/dev/null)
for l in memory.max memory.swap.max pids.max cpu.max; do
  v=$(head -c 64 "/sys/fs/cgroup$cg/$l" 2>/dev/null | tr -d '\n')
  case "$l:$v" in
    memory.max:max|pids.max:max|"cpu.max:max "*|*:) ko "limite-$l" "valeur « $v »" ;;
    memory.swap.max:0) ok "limite-$l ($v)" ;;
    memory.swap.max:*) ko "limite-$l" "valeur « $v »" ;;
    *) ok "limite-$l ($v)" ;;
  esac
done
verifier fichiers-ouverts "ulimit -n autre que 8192" test "$(ulimit -n)" = 8192
printf 'bilan %s echec(s)\n' "$ECHECS"
[ "$ECHECS" = 0 ]
