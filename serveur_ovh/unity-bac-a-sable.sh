#!/bin/bash
# Bac à sable Unity de l'HÔTE (conception § 5.16, option A, tâche 14h et sa relecture). SCRIPT RACINE : déposé par l'étape
# unity_bac_a_sable de mise_en_place.sh en /usr/local/lib/myiafactory/unity-bac-a-sable.sh (root, 0755), appelé par l'enveloppe
# des tests (lancer_tests.sh, utilisateur principal) par `sudo -n` et une règle sudoers limitée à CE chemin. CODE TRÈS SENSIBLE :
# du code de projet non fiable (tests C#, greffons natifs) s'exécute sur l'hôte, dans une unité systemd transitoire confinée
# sous l'utilisateur dédié unity-tests. Rien ici n'est jamais passé à un shell ; chaque argument est validé par un motif ANCRÉ
# avant tout usage ; aucune propriété systemd hors de la liste FIGÉE ci-dessous ; la licence n'est jamais lue ni copiée.
# Usage :
#   lancer  <id> <cpus> <memoire_mo> <duree_s> <version> <reseau> <travail_go>   campagne : entrée standard = 1re ligne la
#           commande (tableau JSON, 4 096 octets au plus, commençant par "unity-editor"), puis l'instantané (tar) ; sortie et
#           sortie d'erreur = celles de l'unité
#   arreter <id>                                                     arrête l'unité unity-tests-<id> (systemctl stop) ; code 0
#   auditer <id> <cpus> <memoire_mo> <duree_s> <version> <reseau> <travail_go>   audit J14 : MÊME unité, MÊMES propriétés, la
#           sonde sonde-bac-a-sable.sh à la place de l'éditeur (entrée standard ignorée) ; n'écrit AUCUN marqueur
#   unite                                                            réservé : lancé DANS l'unité (unity-tests), jamais en root
# Motifs : id ^t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$ (tranche A) ; cpus 1..64 ; memoire_mo 256..65536 ; duree_s 1..3600 ; travail_go
#   1..200 (nombres sans zéro initial) ; version ^[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3}$ ; reseau ^(aucun|licence)$.
# TABLE DES CODES (relecture 14h, I6 : un refus du script ne se confond jamais avec un code des tests) :
#   77  refus du script, RIEN n'a tourné : argument, commande, identifiant déjà pris, instantané non reçu (mode unite),
#       prérequis absent (utilisateur unity-tests, éditeur /opt/unity/editors/<version>/Editor/Unity, scripts, licence,
#       mandataire), dossiers privés de l'utilisateur principal autrement qu'en 0700, bac à sable occupé au-delà de l'attente
#   74  campagne arrêtée en cours : la campagne a dépassé travail_go
#   124 durée dépassée (RuntimeMaxSec atteint)
#   1   panne du script
#   sinon : le code de la commande dans l'unité (entree-tests.sh 2 et 70, entree-unity.sh 0..3, 81, 82) ; jamais 74, 77 ni 124.
# PROPRIÉTÉS FIGÉES de l'unité (§ 5.16 amendé ; toute autre est interdite) : User=unity-tests, ProtectHome=tmpfs,
#   ProtectSystem=strict, PrivateTmp=yes, PrivateDevices=yes, NoNewPrivileges=yes, CapabilityBoundingSet= (vide),
#   ProtectProc=invisible, ProcSubset=pid, ProtectKernelTunables=yes, ProtectKernelModules=yes, ProtectKernelLogs=yes,
#   RestrictNamespaces=yes, RestrictSUIDSGID=yes, LockPersonality=yes, SystemCallFilter=@system-service, PrivateIPC=yes,
#   RemoveIPC=yes, TemporaryFileSystem=/dev/shm:size=512M,mode=1777, LimitCORE=0, ProtectControlGroups=yes,
#   SystemCallArchitectures=native, RestrictRealtime=yes, ProtectHostname=yes, ProtectClock=yes, UMask=0077,
#   InaccessiblePaths= les sockets Docker et /dev/mqueue, ReadWritePaths= le seul dossier de la campagne, BindReadOnlyPaths=
#   l'éditeur et les fichiers de licence (vers le HOME de l'unité, dans la campagne), réseau : PrivateNetwork=yes et
#   RestrictAddressFamilies=AF_UNIX (reseau=aucun) ou IPAddressDeny=any + IPAddressAllow=<mandataire>/32 et
#   RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 (reseau=licence : le mandataire des hôtes de licence, ouvert par
#   l'enveloppe ; les sockets Unix abstraites de l'hôte restent joignables : risque connu), MemoryMax=<memoire_mo>M,
#   MemorySwapMax=0, CPUQuota=<cpus × 100>%, TasksMax=2048, LimitNOFILE=8192, RuntimeMaxSec=<duree_s − attente − 5>.
# Campagne /var/lib/unity-tests/campagnes/<id>/ (ROOT, 0711 : le projet ne peut ni renommer ni remplacer ce qui s'y trouve) :
#   entree/ (commande.json écrit ici après validation ; entree.tar écrit DANS l'unité depuis l'entrée standard : la racine
#   n'ouvre jamais un fichier de l'utilisateur principal), work/ (l'instantané extrait DANS l'unité), home/ (HOME de l'unité ;
#   licence LIÉE en lecture seule, jamais copiée), tmp/ (journal et résultats de l'éditeur) : à unity-tests, 0700, chown fait
#   AVANT tout montage. Library/ : si un cache figé /var/lib/unity-tests/library/<version>/ existe (préparé par un échauffement
#   à venir), overlay monté en <campagne>/library (HORS de work/, sous un dossier de root), couche haute <campagne>/library-haut,
#   à défaut copie (cp --reflink=auto) ; work/Library en est un lien. Le montage est démonté par le chemin NOTÉ à la pose
#   (findmnt), sans suivre de lien (umount -c), jamais par un chemin sous le contrôle du projet ; tout est effacé à la fin
#   (rm --one-file-system, jamais à travers un montage). L'overlay dans l'espace de montage PRIVÉ de l'unité n'est pas possible
#   avec la liste figée (l'unité n'a aucune capacité) : écart noté au § 5.16.
# Une campagne à la fois : verrou /run/myiafactory/unity-bac-a-sable.verrou (root 0755). Sous le verrou, toute unité
#   unity-tests-* dont le script n'existe plus (fichier /run/myiafactory/unity-tests-<id>.pid, processus vérifié par sa ligne de
#   commande) ou active depuis plus de 6 h est arrêtée ; la campagne ne part jamais tant qu'une unité est active. L'attente
#   (verrou + unités) est bornée (300 s, sinon 77 « occupé ») et DÉCOMPTÉE de la durée de l'unité. Puis les dossiers de campagne
#   sans unité active ni script vivant sont effacés.
# Dossiers privés de l'utilisateur principal (~/agent-identifiants, ~/.ssh, ~/taches) : revérifiés en 0700 à chaque lancement.
# Réservées aux tests, IGNORÉES en root : BAC_A_SABLE_RACINE_TEST (préfixe des chemins fixes), BAC_A_SABLE_ATTENTE_MAX_TEST,
#   BAC_A_SABLE_DU_S_TEST ; hors root, le HOME de l'appelant tient lieu d'utilisateur principal et aucun chown n'est fait.
set -u
IFS=$' \t\n'
export LC_ALL=C
umask 077

ATTENTE_MAX=300
DU_S=5
if [ "$EUID" = 0 ]; then
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  export PATH
  RACINE=""
else
  RACINE="${BAC_A_SABLE_RACINE_TEST:-}"
  [[ ${BAC_A_SABLE_ATTENTE_MAX_TEST:-} =~ ^[0-9]{1,3}$ ]] && ATTENTE_MAX="$BAC_A_SABLE_ATTENTE_MAX_TEST"
  [[ ${BAC_A_SABLE_DU_S_TEST:-} =~ ^[0-9]{1,2}(\.[0-9]{1,3})?$ ]] && DU_S="$BAC_A_SABLE_DU_S_TEST"
fi
UTILISATEUR=unity-tests
LIB="$RACINE/usr/local/lib/myiafactory"
VAR="$RACINE/var/lib/unity-tests"
CAMPAGNES="$VAR/campagnes"
LIBRARY="$VAR/library"
EDITEURS="$RACINE/opt/unity/editors"
RUN="$RACINE/run/myiafactory"
VERROU="$RUN/unity-bac-a-sable.verrou"
MOTIF_ID='^t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$'
MOTIF_VERSION='^[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3}$'
MOTIF_CHEMIN='^/[A-Za-z0-9._/-]{1,300}$'
MOTIF_IP_PRIVEE='^(10\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.[0-9]{1,3}\.[0-9]{1,3}$'
LICENCE_DROITS_REL=".config/unity3d/Unity/licenses"
LICENCE_ULF_REL=".local/share/unity3d/Unity/Unity_lic.ulf"
ARCHIVE_MAX=4294967296                  # 4 Gio : l'instantané, déjà contrôlé par l'enveloppe (tests_hote.py --archive)
SIX_HEURES_US=21600000000
MARGE_S=5                               # l'unité s'arrête avant l'échéance de l'enveloppe (son timeout de duree_s)

refuser() { printf 'unity-bac-a-sable : %s\n' "$2" >&2; exit "$1"; }
chemin_sur() { [[ $1 =~ $MOTIF_CHEMIN ]] && [[ $1 != *..* ]]; }

# --- Mode « unite » : DANS l'unité, sous unity-tests ; écrit l'instantané reçu, puis l'entrée commune des tests ----------
if [ "${1:-}" = unite ]; then
  [ "$EUID" != 0 ] || refuser 77 "le mode unite ne tourne jamais en root."
  C="${ENTREE_TESTS_RACINE:-}"
  chemin_sur "$C" && [[ ${C##*/} =~ $MOTIF_ID ]] && [ -d "$C/entree" ] || refuser 77 "dossier de campagne absent ou hors motif."
  ici="$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  head -c "$ARCHIVE_MAX" > "$C/entree/entree.tar" || refuser 77 "instantané non reçu."
  exec </dev/null
  exec /bin/bash "$ici/entree-tests.sh"
fi

# --- Arguments (rien n'est écrit ni lancé avant la fin de ce bloc) ----------------------------------------------------
DEBUT=$(date +%s)
for a in "$@"; do [[ $a == *[[:cntrl:]]* ]] && refuser 77 "caractère de contrôle refusé dans un argument."; done
MODE="${1:-}"
case "$MODE" in
  arreter)
    [ $# = 2 ] && [[ $2 =~ $MOTIF_ID ]] || refuser 77 "usage : arreter <id>."
    timeout 120 systemctl stop "unity-tests-$2.service" </dev/null >/dev/null 2>&1
    exit 0 ;;
  lancer|auditer) ;;
  *) refuser 77 "usage : lancer|auditer <id> <cpus> <memoire_mo> <duree_s> <version> <reseau> <travail_go> ; arreter <id>." ;;
esac
[ $# = 8 ] || refuser 77 "usage : $MODE <id> <cpus> <memoire_mo> <duree_s> <version> <reseau> <travail_go>."
ID="$2"; CPUS="$3"; MEMOIRE="$4"; DUREE="$5"; VERSION="$6"; RESEAU="$7"; TRAVAIL_GO="$8"
[[ $ID =~ $MOTIF_ID ]] || refuser 77 "identifiant refusé."
[[ $CPUS =~ ^[1-9][0-9]?$ ]] && [ "$CPUS" -le 64 ] || refuser 77 "cpus refusés (1 à 64)."
[[ $MEMOIRE =~ ^[1-9][0-9]{2,4}$ ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser 77 "memoire_mo refusée (256 à 65536)."
[[ $DUREE =~ ^[1-9][0-9]{0,3}$ ]] && [ "$DUREE" -le 3600 ] || refuser 77 "duree_s refusée (1 à 3600)."
[[ $VERSION =~ $MOTIF_VERSION ]] || refuser 77 "version Unity refusée."
[[ $RESEAU =~ ^(aucun|licence)$ ]] || refuser 77 "reseau refusé (aucun ou licence)."
[[ $TRAVAIL_GO =~ ^[1-9][0-9]{0,2}$ ]] && [ "$TRAVAIL_GO" -le 200 ] || refuser 77 "travail_go refusé (1 à 200)."
COMMANDE=""
if [ "$MODE" = lancer ]; then
  IFS= read -r -n 4097 COMMANDE || [ -n "$COMMANDE" ] || refuser 77 "commande absente (1re ligne de l'entrée standard)."
  [ "${#COMMANDE}" -le 4096 ] || refuser 77 "commande trop longue (4 096 octets au plus)."
  [[ $COMMANDE == *[[:cntrl:]]* ]] && refuser 77 "caractère de contrôle refusé dans la commande."
  [[ $COMMANDE =~ ^\[\"unity-editor\"(,.*)?\]$ ]] || refuser 77 "commande refusée : un tableau JSON qui commence par \"unity-editor\" est attendu."
else
  exec </dev/null
fi

# --- Prérequis (77 : rien n'a tourné) ------------------------------------------------------------------------------------
id -u "$UTILISATEUR" >/dev/null 2>&1 || refuser 77 "utilisateur $UTILISATEUR absent : installez le bac à sable (étape unity_bac_a_sable)."
if [ "$EUID" = 0 ]; then                       # l'utilisateur principal : celui qui a appelé sudo (jamais une valeur passée)
  [[ ${SUDO_UID:-} =~ ^[1-9][0-9]{0,9}$ ]] || refuser 77 "appel hors sudo refusé."
  PRINCIPAL=$(getent passwd "$SUDO_UID" | cut -d: -f6)
else
  PRINCIPAL="${HOME:-}"
fi
chemin_sur "$PRINCIPAL" || refuser 77 "dossier de l'utilisateur principal illisible ou hors motif."
for d in agent-identifiants .ssh taches; do              # revérifiés à chaque lancement (l'étape les a vus en 0700)
  p="$PRINCIPAL/$d"
  [ -e "$p" ] || [ -L "$p" ] || continue
  [ -d "$p" ] && [ ! -L "$p" ] && [ "$(stat -c %a -- "$p" 2>/dev/null)" = 700 ] ||
    refuser 77 "~/$d n'est pas un dossier en 0700 : rien ne tourne sur l'hôte tant qu'il est lisible."
done
EDITEUR_DIR="$EDITEURS/$VERSION"
EDITEUR="$EDITEUR_DIR/Editor/Unity"
[ -f "$EDITEUR" ] && [ -x "$EDITEUR" ] || refuser 77 "éditeur Unity $VERSION absent de l'hôte ($EDITEUR)."
for f in entree-tests.sh entree-unity.sh sonde-bac-a-sable.sh unity-bac-a-sable.sh; do
  [ -f "$LIB/$f" ] && [ ! -L "$LIB/$f" ] || refuser 77 "$LIB/$f absent : réinstallez le bac à sable (étape unity_bac_a_sable)."
done
# Licence : chaque élément du chemin est un dossier (jamais un lien) ; noms seulement, jamais le contenu.
sans_lien() {   # sans_lien <racine> <relatif> : aucun lien de <racine> jusqu'au bout
  local p="$1" x
  local -a parts
  [ -d "$p" ] && [ ! -L "$p" ] || return 1
  IFS=/ read -r -a parts <<< "$2"
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
[ -d "$CAMPAGNES" ] && [ ! -L "$CAMPAGNES" ] || refuser 77 "$CAMPAGNES absent : réinstallez le bac à sable (étape unity_bac_a_sable)."

# --- Verrou, unités orphelines, attente bornée et décomptée -------------------------------------------------------------
if [ "$EUID" = 0 ]; then install -d -o root -g root -m 0755 "$RUN" || refuser 1 "$RUN non créable."
else mkdir -p "$RUN" || refuser 1 "$RUN non créable."; fi
[ -d "$RUN" ] && [ ! -L "$RUN" ] || refuser 1 "$RUN n'est pas un dossier."
attente_depassee() { [ $(($(date +%s) - DEBUT)) -ge "$ATTENTE_MAX" ]; }
exec 9>> "$VERROU" || refuser 1 "verrou $VERROU inaccessible."
until flock -n 9; do
  attente_depassee && refuser 77 "bac à sable occupé par une autre campagne Unity au-delà de ${ATTENTE_MAX} s."
  sleep 1
done
script_vivant() {   # script_vivant <id> : le script racine de cette campagne vit (PID noté ET ligne de commande vérifiée)
  local pid="" cmd
  [ -f "$RUN/unity-tests-$1.pid" ] && IFS= read -r pid < "$RUN/unity-tests-$1.pid"
  [[ $pid =~ ^[1-9][0-9]{0,9}$ ]] && [ -r "/proc/$pid/cmdline" ] || return 1
  cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  [[ $cmd == *unity-bac-a-sable.sh* && $cmd == *"$1"* ]]
}
actif() { timeout 30 systemctl is-active --quiet "unity-tests-$1.service" </dev/null >/dev/null 2>&1; }
uptime_us() { local u; read -r u _ < /proc/uptime 2>/dev/null; [[ $u =~ ^([0-9]+)\.([0-9]{2}) ]] && printf '%s' "${BASH_REMATCH[1]}${BASH_REMATCH[2]}0000"; }
while :; do
  occupe=0
  maintenant=$(uptime_us)
  while IFS= read -r nom; do
    [[ $nom =~ ^unity-tests-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})\.service$ ]] || continue
    autre="${BASH_REMATCH[1]}"
    depuis=$(timeout 30 systemctl show -p ActiveEnterTimestampMonotonic --value "$nom" </dev/null 2>/dev/null)
    vieille=0
    [[ $depuis =~ ^[1-9][0-9]{0,19}$ ]] && [[ $maintenant =~ ^[0-9]+$ ]] &&
      [ $((maintenant - depuis)) -gt "$SIX_HEURES_US" ] && vieille=1
    if [ "$vieille" = 1 ] || ! script_vivant "$autre"; then
      timeout 120 systemctl stop "$nom" </dev/null >/dev/null 2>&1
    fi
    actif "$autre" && occupe=1
  done < <(timeout 30 systemctl list-units --all --plain --no-legend --type=service 'unity-tests-*' </dev/null 2>/dev/null |
             awk '{ print $1 }')
  [ "$occupe" = 0 ] && break
  attente_depassee && refuser 77 "bac à sable occupé : une unité unity-tests-* est encore active après ${ATTENTE_MAX} s."
  sleep 1
done
RESTE=$((DUREE - ($(date +%s) - DEBUT) - MARGE_S))
[ "$RESTE" -ge 1 ] || refuser 77 "bac à sable occupé : plus assez de temps pour la campagne après l'attente."

effacer() {   # effacer <dossier de campagne> : démonte <dossier>/library (chemin construit par nous, jamais suivi), puis efface
  local d="$1" m
  [ -d "$d" ] && [ ! -L "$d" ] || return 0
  m=$(findmnt -n -o TARGET -M "$d/library" 2>/dev/null)
  if [ -n "$m" ]; then
    [ "$m" = "$d/library" ] || return 1
    umount -c -- "$d/library" 2>/dev/null || umount -c -l -- "$d/library" 2>/dev/null || return 1
    [ -z "$(findmnt -n -o TARGET -M "$d/library" 2>/dev/null)" ] || return 1
  fi
  rm -rf --one-file-system -- "$d"
}
for d in "$CAMPAGNES"/t*; do                             # campagnes mortes : ni script vivant ni unité active
  autre="${d##*/}"
  [[ $autre =~ $MOTIF_ID ]] && [ "$autre" != "$ID" ] || continue
  script_vivant "$autre" || actif "$autre" || { effacer "$d"; rm -f -- "$RUN/unity-tests-$autre.pid"; }
done

# --- Dossier de la campagne ---------------------------------------------------------------------------------------------
C="$CAMPAGNES/$ID"
[ ! -e "$C" ] && [ ! -L "$C" ] || refuser 77 "identifiant $ID déjà utilisé."
TROP="$RUN/unity-tests-$ID.trop"
UNITE_LANCEE=0; MONTAGE=""; PID_UNITE=""; PID_DU=""
nettoyer() {
  trap '' TERM INT HUP PIPE
  [ -n "$PID_DU" ] && { kill "$PID_DU"; wait "$PID_DU"; } 2>/dev/null
  if [ "$UNITE_LANCEE" = 1 ]; then
    timeout 120 systemctl stop "unity-tests-$ID.service" </dev/null >/dev/null 2>&1
    [ -n "$PID_UNITE" ] && { kill "$PID_UNITE"; wait "$PID_UNITE"; } 2>/dev/null
  fi
  effacer "$C"
  rm -f -- "$RUN/unity-tests-$ID.pid" "$TROP"
}
trap 'nettoyer; exit 143' TERM INT HUP PIPE
trap 'nettoyer' EXIT
printf '%s\n' "$$" > "$RUN/unity-tests-$ID.pid" || exit 1
rm -f -- "$TROP"
mkdir -m 711 -- "$C" || refuser 1 "dossier de campagne non créable."
mkdir -m 700 -- "$C/entree" "$C/work" "$C/home" "$C/tmp" || exit 1
if [ "$MODE" = lancer ]; then
  printf '%s' "$COMMANDE" > "$C/entree/commande.json" || exit 1
fi
# Points de montage de la licence (vides, dans le HOME de l'unité) : la liaison les couvre, rien n'est copié.
if [ -n "$DROITS" ]; then mkdir -p -m 700 -- "$C/home/$LICENCE_DROITS_REL" || exit 1; fi
if [ -n "$ULF" ]; then mkdir -p -m 700 -- "$C/home/${LICENCE_ULF_REL%/*}" && : > "$C/home/$LICENCE_ULF_REL" || exit 1; fi
if [ "$EUID" = 0 ]; then                                 # AVANT tout montage : jamais de chown à travers l'overlay
  chown -hR "$UTILISATEUR:$UTILISATEUR" -- "$C/entree" "$C/work" "$C/home" "$C/tmp" || exit 1
fi
# Library/ : overlay en <campagne>/library (sous un dossier de root, hors de work/), chemin NOTÉ par findmnt ; à défaut copie.
if [ -d "$LIBRARY/$VERSION" ] && [ ! -L "$LIBRARY/$VERSION" ] && [ "$MODE" = lancer ]; then
  mkdir -m 700 -- "$C/library" "$C/library-haut" "$C/library-ov" || exit 1
  [ "$EUID" = 0 ] && { chown -h "$UTILISATEUR:$UTILISATEUR" -- "$C/library" "$C/library-haut" || exit 1; }
  if mount -t overlay overlay -o "lowerdir=$LIBRARY/$VERSION,upperdir=$C/library-haut,workdir=$C/library-ov" "$C/library" \
       </dev/null >/dev/null 2>&1; then
    MONTAGE=$(findmnt -n -o TARGET -M "$C/library" 2>/dev/null)
    [ "$MONTAGE" = "$C/library" ] || refuser 1 "montage de Library/ introuvable à l'endroit posé."
    mount --make-private "$MONTAGE" </dev/null >/dev/null 2>&1
  else
    if cp -a --reflink=auto -- "$LIBRARY/$VERSION/." "$C/library/" 2>/dev/null; then
      [ "$EUID" = 0 ] && { chown -hR "$UTILISATEUR:$UTILISATEUR" -- "$C/library" || exit 1; }
    else
      printf '%s\n' "unity-bac-a-sable : cache Library/ non copié : import complet par l'éditeur." >&2
    fi
  fi
  ln -s -- "$C/library" "$C/work/Library" || exit 1
  [ "$EUID" = 0 ] && chown -h "$UTILISATEUR:$UTILISATEUR" -- "$C/work/Library"
fi

# --- L'unité : la liste FIGÉE, rien d'autre ------------------------------------------------------------------------------
P=(-p "User=$UTILISATEUR" -p ProtectHome=tmpfs -p ProtectSystem=strict -p PrivateTmp=yes -p PrivateDevices=yes
   -p NoNewPrivileges=yes -p CapabilityBoundingSet= -p ProtectProc=invisible -p ProcSubset=pid
   -p ProtectKernelTunables=yes -p ProtectKernelModules=yes -p ProtectKernelLogs=yes -p RestrictNamespaces=yes
   -p RestrictSUIDSGID=yes -p LockPersonality=yes -p SystemCallFilter=@system-service
   -p PrivateIPC=yes -p RemoveIPC=yes -p "TemporaryFileSystem=/dev/shm:size=512M,mode=1777" -p LimitCORE=0
   -p ProtectControlGroups=yes -p SystemCallArchitectures=native -p RestrictRealtime=yes -p ProtectHostname=yes
   -p ProtectClock=yes -p UMask=0077
   -p "InaccessiblePaths=-/run/docker.sock -/var/run/docker.sock -/dev/mqueue"
   -p "ReadWritePaths=$C"
   -p "BindReadOnlyPaths=$EDITEUR_DIR")
[ -n "$DROITS" ] && P+=(-p "BindReadOnlyPaths=$DROITS:$C/home/$LICENCE_DROITS_REL")
[ -n "$ULF" ] && P+=(-p "BindReadOnlyPaths=$ULF:$C/home/$LICENCE_ULF_REL")
if [ "$RESEAU" = licence ]; then
  P+=(-p IPAddressDeny=any -p "IPAddressAllow=$MANDATAIRE/32" -p "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6")
else
  P+=(-p PrivateNetwork=yes -p RestrictAddressFamilies=AF_UNIX)
fi
P+=(-p "MemoryMax=${MEMOIRE}M" -p MemorySwapMax=0 -p "CPUQuota=$((CPUS * 100))%" -p TasksMax=2048 -p LimitNOFILE=8192
    -p "RuntimeMaxSec=$RESTE")
ENV=(--setenv=HOME="$C/home" --setenv=PATH=/usr/local/bin:/usr/bin:/bin --setenv=LC_ALL=C --setenv=ENTREE_TESTS_RACINE="$C"
     --setenv=MYIAFACTORY_TESTS_FAMILLE=unity --setenv=MYIAFACTORY_UNITY_LICENCE=liee --setenv=MYIAFACTORY_UNITY_EDITEUR="$EDITEUR")
if [ "$RESEAU" = licence ]; then
  p="http://$MANDATAIRE:3128"
  ENV+=(--setenv=HTTPS_PROXY="$p" --setenv=HTTP_PROXY="$p" --setenv=https_proxy="$p" --setenv=http_proxy="$p")
fi
if [ "$MODE" = auditer ]; then
  ENV+=(--setenv=MYIAFACTORY_SONDE_PRINCIPAL="$PRINCIPAL" --setenv=MYIAFACTORY_SONDE_RESEAU="$RESEAU")
  [ -n "$MANDATAIRE" ] && ENV+=(--setenv=MYIAFACTORY_SONDE_MANDATAIRE="$MANDATAIRE")
  EXEC=(/bin/bash "$LIB/sonde-bac-a-sable.sh")
else
  EXEC=(/bin/bash "$LIB/unity-bac-a-sable.sh" unite)
fi
# Surveillant de taille : au-delà de travail_go, marque puis arrêt de l'unité (74).
( trap - TERM INT HUP PIPE
  while sleep "$DU_S"; do
    k=$(du -sk --one-file-system -- "$C" 2>/dev/null | cut -f1)
    if [[ $k =~ ^[0-9]{1,15}$ ]] && [ "$k" -gt $((TRAVAIL_GO * 1048576)) ]; then
      : > "$TROP"
      timeout 120 systemctl stop "unity-tests-$ID.service" </dev/null >/dev/null 2>&1
      exit 0
    fi
  done ) </dev/null >/dev/null 2>&1 9>&- &
PID_DU=$!
# En arrière-plan puis `wait` : un signal (laisse, timeout) est traité aussitôt (nettoyer arrête l'unité), jamais après elle.
exec 3<&0
UNITE_LANCEE=1
DEPART=$(date +%s)
systemd-run --quiet --pipe --wait --collect --unit "unity-tests-$ID" "${P[@]}" "${ENV[@]}" -- "${EXEC[@]}" <&3 3<&- 9>&- &
PID_UNITE=$!
exec 3<&-
wait "$PID_UNITE"
code=$?
PID_UNITE=""
UNITE_LANCEE=0                                           # --wait : l'unité est finie (et ramassée, --collect)
{ kill "$PID_DU"; wait "$PID_DU"; } 2>/dev/null
PID_DU=""
if [ -e "$TROP" ]; then
  printf '%s\n' "unity-bac-a-sable : campagne au-delà de ${TRAVAIL_GO} Go : unité arrêtée." >&2
  exit 74
fi
if [ "$code" != 0 ] && [ $(($(date +%s) - DEPART)) -ge "$RESTE" ]; then
  printf '%s\n' "unity-bac-a-sable : durée dépassée (${RESTE} s) : unité arrêtée." >&2
  exit 124
fi
# 74 et 124 ne viennent que d'ici ; 77 de l'unité est le refus du mode unite (instantané non reçu), jamais de l'éditeur.
case "$code" in 74|124) code=1 ;; esac
exit "$code"
