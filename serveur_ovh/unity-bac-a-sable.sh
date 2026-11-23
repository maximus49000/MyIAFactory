#!/usr/bin/env bash
# Bac à sable Unity de l'HÔTE (conception § 5.16, option A, tâche 14h). SCRIPT RACINE : déposé par l'étape unity_bac_a_sable
# de mise_en_place.sh en /usr/local/lib/myiafactory/unity-bac-a-sable.sh (root, 0755), appelé par l'enveloppe des tests
# (lancer_tests.sh, utilisateur principal) par `sudo -n` et une règle sudoers limitée à CE chemin. CODE TRÈS SENSIBLE : du code
# de projet non fiable (tests C#, greffons natifs) s'exécute sur l'hôte, dans une unité systemd transitoire confinée sous
# l'utilisateur dédié unity-tests. Rien ici n'est jamais passé à un shell ; chaque argument est validé par un motif ANCRÉ avant
# tout usage ; aucune propriété systemd hors de la liste FIGÉE ci-dessous ; la licence n'est jamais lue ni copiée.
# Usage :
#   lancer  <id> <cpus> <memoire_mo> <duree_s> <version> <reseau>   campagne : entrée standard = 1re ligne la commande (tableau
#           JSON, 4 096 octets au plus, commençant par "unity-editor"), puis l'instantané (tar) ; sortie et sortie d'erreur =
#           celles de l'unité ; code = celui de la commande dans l'unité (entree-tests.sh puis entree-unity.sh)
#   arreter <id>                                                     arrête l'unité unity-tests-<id> (systemctl stop) ; code 0
#   auditer <id> <cpus> <memoire_mo> <duree_s> <version> <reseau>   audit J14 : MÊME unité, MÊMES propriétés, la sonde
#           sonde-bac-a-sable.sh à la place de l'éditeur (entrée standard ignorée) ; n'écrit AUCUN marqueur
#   unite                                                            réservé : lancé DANS l'unité (unity-tests), jamais en root
# Motifs : id ^t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$ (tranche A) ; cpus 1..64 ; memoire_mo 256..65536 ; duree_s 1..3600 (sans zéro
#   initial) ; version ^[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3}$ ; reseau ^(aucun|licence)$.
# Codes propres : 2 argument ou commande refusés, identifiant déjà utilisé (aucun systemd-run) ; 77 prérequis absent
#   (utilisateur unity-tests, éditeur /opt/unity/editors/<version>/Editor/Unity, licence de l'utilisateur principal, scripts
#   d'entrée, mandataire de la licence) : rien n'a tourné ; 1 panne. La commande dans l'unité ne rend jamais 77 (entree-unity.sh
#   ramène les codes de l'éditeur à 0..3, 81, 82 ; entree-tests.sh 2 et 70) : l'enveloppe le traite comme un refus.
# PROPRIÉTÉS FIGÉES de l'unité (§ 5.16 ; toute autre est interdite) : User=unity-tests, ProtectHome=tmpfs, ProtectSystem=strict,
#   PrivateTmp=yes, PrivateDevices=yes, NoNewPrivileges=yes, CapabilityBoundingSet= (vide), ProtectProc=invisible,
#   ProcSubset=pid, ProtectKernelTunables=yes, ProtectKernelModules=yes, ProtectKernelLogs=yes, RestrictNamespaces=yes,
#   RestrictSUIDSGID=yes, LockPersonality=yes, SystemCallFilter=@system-service, InaccessiblePaths= des sockets Docker,
#   ReadWritePaths= le seul dossier de la campagne, BindReadOnlyPaths= l'éditeur et les fichiers de licence (vers le HOME de
#   l'unité, dans la campagne), PrivateNetwork=yes (reseau=aucun) ou IPAddressDeny=any + IPAddressAllow=<mandataire>/32
#   (reseau=licence : le mandataire des hôtes de licence, § 5.13, ouvert par l'enveloppe), MemoryMax, MemorySwapMax=0,
#   CPUQuota, TasksMax=2048, LimitNOFILE=8192, RuntimeMaxSec (duree_s + 30 : l'échéance de l'enveloppe passe d'abord).
# Campagne /var/lib/unity-tests/campagnes/<id>/ (unity-tests, 0700) : entree/commande.json (écrit ici après validation),
#   entree/entree.tar (écrit DANS l'unité depuis l'entrée standard : la racine n'ouvre jamais un fichier de l'utilisateur
#   principal), work/ (l'instantané est extrait DANS l'unité), home/ (HOME de l'unité ; licence LIÉE en lecture seule, jamais
#   copiée), tmp/ (journal et résultats de l'éditeur). Library/ : si un cache figé /var/lib/unity-tests/library/<version>/
#   existe (root ; préparé par un échauffement à venir), monté en overlay (couche haute dans la campagne), à défaut copié
#   (cp --reflink=auto) ; choix à mesurer à J14. Tout est effacé à la fin (démontage d'abord, jamais à travers un montage).
# Une campagne à la fois (verrou /run/lock/myiafactory-unity-bac-a-sable.verrou, attendu) : les unités partagent l'uid
#   unity-tests, deux campagnes simultanées pourraient se voir (/proc) et se lire. Balayage à chaque lancement : unités
#   unity-tests-* actives depuis plus de 6 h arrêtées ; dossiers de campagne de plus de 6 h sans unité active effacés.
# Réservée aux tests, IGNORÉE en root : BAC_A_SABLE_RACINE_TEST (préfixe des chemins fixes) ; hors root, le HOME de l'appelant
#   tient lieu d'utilisateur principal et aucun chown n'est fait.
set -u
export LC_ALL=C
umask 077

if [ "$EUID" = 0 ]; then
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  export PATH
  RACINE=""
else
  RACINE="${BAC_A_SABLE_RACINE_TEST:-}"
fi
UTILISATEUR=unity-tests
LIB="$RACINE/usr/local/lib/myiafactory"
VAR="$RACINE/var/lib/unity-tests"
CAMPAGNES="$VAR/campagnes"
LIBRARY="$VAR/library"
EDITEURS="$RACINE/opt/unity/editors"
VERROU="$RACINE/run/lock/myiafactory-unity-bac-a-sable.verrou"
MOTIF_ID='^t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$'
MOTIF_VERSION='^[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3}$'
MOTIF_CHEMIN='^/[A-Za-z0-9._/-]{1,300}$'
MOTIF_IP_PRIVEE='^(10\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.[0-9]{1,3}\.[0-9]{1,3}$'
LICENCE_DROITS_REL=".config/unity3d/Unity/licenses"
LICENCE_ULF_REL=".local/share/unity3d/Unity/Unity_lic.ulf"
ARCHIVE_MAX=4294967296                  # 4 Gio : l'instantané, déjà contrôlé par l'enveloppe (tests_hote.py --archive)
SIX_HEURES_US=21600000000

refuser() { printf 'unity-bac-a-sable : %s\n' "$2" >&2; exit "$1"; }
chemin_sur() { [[ $1 =~ $MOTIF_CHEMIN ]] && [[ $1 != *..* ]]; }

# --- Mode « unite » : DANS l'unité, sous unity-tests ; écrit l'instantané reçu, puis l'entrée commune des tests ----------
if [ "${1:-}" = unite ]; then
  [ "$EUID" != 0 ] || refuser 2 "le mode unite ne tourne jamais en root."
  C="${ENTREE_TESTS_RACINE:-}"
  chemin_sur "$C" && [[ ${C##*/} =~ $MOTIF_ID ]] && [ -d "$C/entree" ] || refuser 2 "dossier de campagne absent ou hors motif."
  ici="$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  head -c "$ARCHIVE_MAX" > "$C/entree/entree.tar" || refuser 70 "instantané non reçu."
  exec </dev/null
  exec /bin/bash "$ici/entree-tests.sh"
fi

# --- Arguments (rien n'est écrit ni lancé avant la fin de ce bloc) ----------------------------------------------------
for a in "$@"; do [[ $a == *[[:cntrl:]]* ]] && refuser 2 "caractère de contrôle refusé dans un argument."; done
MODE="${1:-}"
case "$MODE" in
  arreter)
    [ $# = 2 ] && [[ $2 =~ $MOTIF_ID ]] || refuser 2 "usage : arreter <id>."
    timeout 120 systemctl stop "unity-tests-$2.service" </dev/null >/dev/null 2>&1
    exit 0 ;;
  lancer|auditer) ;;
  *) refuser 2 "usage : lancer|auditer <id> <cpus> <memoire_mo> <duree_s> <version> <reseau> ; arreter <id>." ;;
esac
[ $# = 7 ] || refuser 2 "usage : $MODE <id> <cpus> <memoire_mo> <duree_s> <version> <reseau>."
ID="$2"; CPUS="$3"; MEMOIRE="$4"; DUREE="$5"; VERSION="$6"; RESEAU="$7"
[[ $ID =~ $MOTIF_ID ]] || refuser 2 "identifiant refusé."
[[ $CPUS =~ ^[1-9][0-9]?$ ]] && [ "$CPUS" -le 64 ] || refuser 2 "cpus refusés (1 à 64)."
[[ $MEMOIRE =~ ^[1-9][0-9]{2,4}$ ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser 2 "memoire_mo refusée (256 à 65536)."
[[ $DUREE =~ ^[1-9][0-9]{0,3}$ ]] && [ "$DUREE" -le 3600 ] || refuser 2 "duree_s refusée (1 à 3600)."
[[ $VERSION =~ $MOTIF_VERSION ]] || refuser 2 "version Unity refusée."
[[ $RESEAU =~ ^(aucun|licence)$ ]] || refuser 2 "reseau refusé (aucun ou licence)."
COMMANDE=""
if [ "$MODE" = lancer ]; then
  IFS= read -r -n 4097 COMMANDE || [ -n "$COMMANDE" ] || refuser 2 "commande absente (1re ligne de l'entrée standard)."
  [ "${#COMMANDE}" -le 4096 ] || refuser 2 "commande trop longue (4 096 octets au plus)."
  [[ $COMMANDE == *[[:cntrl:]]* ]] && refuser 2 "caractère de contrôle refusé dans la commande."
  [[ $COMMANDE =~ ^\[\"unity-editor\"(,.*)?\]$ ]] || refuser 2 "commande refusée : un tableau JSON qui commence par \"unity-editor\" est attendu."
else
  exec </dev/null
fi

# --- Prérequis (77 : rien n'a tourné) ------------------------------------------------------------------------------------
id -u "$UTILISATEUR" >/dev/null 2>&1 || refuser 77 "utilisateur $UTILISATEUR absent : installez le bac à sable (étape unity_bac_a_sable)."
if [ "$EUID" = 0 ]; then                       # l'utilisateur principal : celui qui a appelé sudo (jamais une valeur passée)
  [[ ${SUDO_UID:-} =~ ^[1-9][0-9]{0,9}$ ]] || refuser 2 "appel hors sudo refusé."
  PRINCIPAL=$(getent passwd "$SUDO_UID" | cut -d: -f6)
else
  PRINCIPAL="${HOME:-}"
fi
chemin_sur "$PRINCIPAL" || refuser 77 "dossier de l'utilisateur principal illisible ou hors motif."
EDITEUR_DIR="$EDITEURS/$VERSION"
EDITEUR="$EDITEUR_DIR/Editor/Unity"
[ -f "$EDITEUR" ] && [ -x "$EDITEUR" ] || refuser 77 "éditeur Unity $VERSION absent de l'hôte ($EDITEUR)."
for f in entree-tests.sh entree-unity.sh sonde-bac-a-sable.sh unity-bac-a-sable.sh; do
  [ -f "$LIB/$f" ] && [ ! -L "$LIB/$f" ] || refuser 77 "$LIB/$f absent : réinstallez le bac à sable (étape unity_bac_a_sable)."
done
# Licence : chaque élément du chemin est un dossier (jamais un lien) ; noms seulement, jamais le contenu.
sans_lien() {   # sans_lien <racine> <relatif> : aucun lien de <racine> jusqu'au bout
  local p="$1" r="$2" x
  [ -d "$p" ] && [ ! -L "$p" ] || return 1
  IFS=/ read -r -a parts <<< "$r"
  for x in "${parts[@]}"; do p="$p/$x"; [ ! -L "$p" ] || return 1; done
}
DROITS=""; ULF=""
if sans_lien "$PRINCIPAL" "$LICENCE_DROITS_REL" && [ -d "$PRINCIPAL/$LICENCE_DROITS_REL" ] &&
   [ -n "$(ls -A -- "$PRINCIPAL/$LICENCE_DROITS_REL" 2>/dev/null)" ]; then
  DROITS="$PRINCIPAL/$LICENCE_DROITS_REL"
fi
if sans_lien "$PRINCIPAL" "$LICENCE_ULF_REL" && [ -f "$PRINCIPAL/$LICENCE_ULF_REL" ]; then
  ULF="$PRINCIPAL/$LICENCE_ULF_REL"
fi
[ -n "$DROITS$ULF" ] || refuser 77 "licence Unity absente de l'hôte (~/$LICENCE_DROITS_REL ou ~/$LICENCE_ULF_REL)."
MANDATAIRE=""
if [ "$RESEAU" = licence ]; then   # l'adresse du mandataire éphémère de la campagne (réseau interne deps-<id>), lue ici
  MANDATAIRE=$(timeout 20 docker inspect -f "{{(index .NetworkSettings.Networks \"deps-$ID\").IPAddress}}" "mandataire-$ID" \
                 </dev/null 2>/dev/null)
  [[ $MANDATAIRE =~ $MOTIF_IP_PRIVEE ]] || refuser 77 "mandataire de la licence introuvable (mandataire-$ID)."
fi

# --- Une campagne à la fois, puis balayage ----------------------------------------------------------------------------
[ -d "$CAMPAGNES" ] && [ ! -L "$CAMPAGNES" ] || refuser 77 "$CAMPAGNES absent : réinstallez le bac à sable (étape unity_bac_a_sable)."
exec 9>> "$VERROU" || refuser 1 "verrou $VERROU inaccessible."
until flock -n 9; do sleep 1; done
uptime_us() { local u; read -r u _ < /proc/uptime 2>/dev/null; [[ $u =~ ^([0-9]+)\.([0-9]{2}) ]] && printf '%s' "${BASH_REMATCH[1]}${BASH_REMATCH[2]}0000"; }
actif() { timeout 30 systemctl is-active --quiet "unity-tests-$1.service" </dev/null >/dev/null 2>&1; }
effacer() {   # effacer <dossier de campagne> : démonte Library/ s'il le faut ; jamais d'effacement à travers un montage
  local d="$1"
  [ -d "$d" ] && [ ! -L "$d" ] || return 0
  if [ -d "$d/work/Library" ] && mountpoint -q "$d/work/Library" 2>/dev/null; then
    umount "$d/work/Library" 2>/dev/null || umount -l "$d/work/Library" 2>/dev/null || return 1
  fi
  rm -rf --one-file-system -- "$d"
}
maintenant=$(uptime_us)
while IFS= read -r nom; do
  [[ $nom =~ ^unity-tests-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})\.service$ ]] || continue
  depuis=$(timeout 30 systemctl show -p ActiveEnterTimestampMonotonic --value "$nom" </dev/null 2>/dev/null)
  [[ $depuis =~ ^[1-9][0-9]{0,19}$ ]] && [[ $maintenant =~ ^[0-9]+$ ]] || continue
  [ $((maintenant - depuis)) -gt "$SIX_HEURES_US" ] && timeout 120 systemctl stop "$nom" </dev/null >/dev/null 2>&1
done < <(timeout 30 systemctl list-units --all --plain --no-legend --type=service 'unity-tests-*' </dev/null 2>/dev/null |
           awk '{ print $1 }')
while IFS= read -r -d '' d; do
  autre="${d##*/}"
  [[ $autre =~ $MOTIF_ID ]] && [ "$autre" != "$ID" ] || continue
  actif "$autre" || effacer "$d"
done < <(find "$CAMPAGNES" -mindepth 1 -maxdepth 1 -name 't*' -mmin +360 -print0 2>/dev/null)

# --- Dossier de la campagne ---------------------------------------------------------------------------------------------
C="$CAMPAGNES/$ID"
[ ! -e "$C" ] && [ ! -L "$C" ] || refuser 2 "identifiant $ID déjà utilisé."
UNITE_LANCEE=0; MONTE=0; PID_UNITE=""
nettoyer() {
  trap '' TERM INT HUP PIPE
  if [ "$UNITE_LANCEE" = 1 ]; then
    timeout 120 systemctl stop "unity-tests-$ID.service" </dev/null >/dev/null 2>&1
    [ -n "$PID_UNITE" ] && { kill "$PID_UNITE"; wait "$PID_UNITE"; } 2>/dev/null
  fi
  effacer "$C"
}
trap 'nettoyer; exit 143' TERM INT HUP PIPE
trap 'nettoyer' EXIT
mkdir -m 700 -- "$C" || refuser 1 "dossier de campagne non créable."
mkdir -m 700 -- "$C/entree" "$C/work" "$C/home" "$C/tmp" || exit 1
if [ "$MODE" = lancer ]; then
  printf '%s' "$COMMANDE" > "$C/entree/commande.json" || exit 1
fi
# Points de montage de la licence (vides, dans le HOME de l'unité) : la liaison les couvre, rien n'est copié.
if [ -n "$DROITS" ]; then mkdir -p -m 700 -- "$C/home/$LICENCE_DROITS_REL" || exit 1; fi
if [ -n "$ULF" ]; then mkdir -p -m 700 -- "$C/home/${LICENCE_ULF_REL%/*}" && : > "$C/home/$LICENCE_ULF_REL" || exit 1; fi
# Library/ : cache figé en overlay (couche haute dans la campagne), à défaut copie (copie sur écriture si le système le permet).
if [ -d "$LIBRARY/$VERSION" ] && [ ! -L "$LIBRARY/$VERSION" ] && [ "$MODE" = lancer ]; then
  mkdir -m 700 -- "$C/work/Library" "$C/library-haut" "$C/library-ov" || exit 1
  if mount -t overlay overlay -o "lowerdir=$LIBRARY/$VERSION,upperdir=$C/library-haut,workdir=$C/library-ov" "$C/work/Library" \
       </dev/null >/dev/null 2>&1; then
    MONTE=1
    mount --make-private "$C/work/Library" </dev/null >/dev/null 2>&1
  else
    cp -a --reflink=auto -- "$LIBRARY/$VERSION/." "$C/work/Library/" 2>/dev/null ||
      printf '%s\n' "unity-bac-a-sable : cache Library/ non copié : import complet par l'éditeur." >&2
  fi
fi
if [ "$EUID" = 0 ]; then
  chown -hR "$UTILISATEUR:$UTILISATEUR" -- "$C" || exit 1
fi

# --- L'unité : la liste FIGÉE, rien d'autre ------------------------------------------------------------------------------
P=(-p "User=$UTILISATEUR" -p ProtectHome=tmpfs -p ProtectSystem=strict -p PrivateTmp=yes -p PrivateDevices=yes
   -p NoNewPrivileges=yes -p CapabilityBoundingSet= -p ProtectProc=invisible -p ProcSubset=pid
   -p ProtectKernelTunables=yes -p ProtectKernelModules=yes -p ProtectKernelLogs=yes -p RestrictNamespaces=yes
   -p RestrictSUIDSGID=yes -p LockPersonality=yes -p SystemCallFilter=@system-service
   -p "InaccessiblePaths=-/run/docker.sock -/var/run/docker.sock"
   -p "ReadWritePaths=$C"
   -p "BindReadOnlyPaths=$EDITEUR_DIR")
[ -n "$DROITS" ] && P+=(-p "BindReadOnlyPaths=$DROITS:$C/home/$LICENCE_DROITS_REL")
[ -n "$ULF" ] && P+=(-p "BindReadOnlyPaths=$ULF:$C/home/$LICENCE_ULF_REL")
if [ "$RESEAU" = licence ]; then P+=(-p IPAddressDeny=any -p "IPAddressAllow=$MANDATAIRE/32")
else P+=(-p PrivateNetwork=yes); fi
P+=(-p "MemoryMax=${MEMOIRE}M" -p MemorySwapMax=0 -p "CPUQuota=$((CPUS * 100))%" -p TasksMax=2048 -p LimitNOFILE=8192
    -p "RuntimeMaxSec=$((DUREE + 30))")
ENV=(--setenv=HOME="$C/home" --setenv=PATH=/usr/local/bin:/usr/bin:/bin --setenv=LC_ALL=C --setenv=ENTREE_TESTS_RACINE="$C"
     --setenv=MYIAFACTORY_TESTS_FAMILLE=unity --setenv=MYIAFACTORY_UNITY_LICENCE=liee --setenv=MYIAFACTORY_UNITY_EDITEUR="$EDITEUR")
if [ "$RESEAU" = licence ]; then
  p="http://$MANDATAIRE:3128"
  ENV+=(--setenv=HTTPS_PROXY="$p" --setenv=HTTP_PROXY="$p" --setenv=https_proxy="$p" --setenv=http_proxy="$p")
fi
if [ "$MODE" = auditer ]; then
  ENV+=(--setenv=MYIAFACTORY_SONDE_PRINCIPAL="$PRINCIPAL" --setenv=MYIAFACTORY_SONDE_RESEAU="$RESEAU")
  EXEC=(/bin/bash "$LIB/sonde-bac-a-sable.sh")
else
  EXEC=(/bin/bash "$LIB/unity-bac-a-sable.sh" unite)
fi
# En arrière-plan puis `wait` : un signal (laisse, timeout) est traité aussitôt (nettoyer arrête l'unité), jamais après elle.
exec 3<&0
UNITE_LANCEE=1
systemd-run --quiet --pipe --wait --collect --unit "unity-tests-$ID" "${P[@]}" "${ENV[@]}" -- "${EXEC[@]}" <&3 3<&- 9>&- &
PID_UNITE=$!
exec 3<&-
wait "$PID_UNITE"
code=$?
PID_UNITE=""
UNITE_LANCEE=0                                           # --wait : l'unité est finie (et ramassée, --collect)
exit "$code"
