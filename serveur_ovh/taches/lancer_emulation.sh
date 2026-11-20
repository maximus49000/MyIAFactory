#!/usr/bin/env bash
# Enveloppe HÔTE d'une tâche d'émulation : exécutée sur le serveur (par SSH), elle prend le créneau, démarre le conteneur
# `myiafactory/emulateur` puis rend la main ; un veilleur DÉTACHÉ (setsid + nohup, survit à la fin de la session SSH) tient le
# créneau, applique les limites et écrit l'état final. Un appelant mort ne laisse donc ni conteneur ni créneau.
# Usage : lancer_emulation.sh <id> <mode> [duree_s [inactivite_s [memoire_mo [cpus [captures [octets]]]]]]
#   captures (1..50) et octets (1..104857600) facultatifs : passés au conteneur en -e PONT_CAPTURES / -e PONT_OCTETS (limites du pont) ;
#   absents, le conteneur garde les valeurs du pont (50 captures, 100 Mo).
#   id : t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; mode : scenario | pilote ; valeurs par défaut : 1200 s, 600 s, 6144 Mo, 2 processeurs
#   (inactivite_s 600 > PONT_DEMARRAGE_S 300 : un `demarrer` en cours n'est jamais pris pour de l'inactivité).
#   Chaque valeur est validée par un motif strict AVANT tout usage (nombres entiers sans zéro initial : duree_s et inactivite_s
#   1..86400, memoire_mo 256..65536, cpus 1..64) ; rien n'en est jamais interprété par un shell : les commandes sont des tableaux.
# Sortie standard : UNE ligne JSON, l'état écrit dans ~/taches/<id>/etat.json.
# Codes : 0 conteneur démarré (état en_cours) ; 1 démarrage impossible (état echouee) ; 2 argument refusé (rien créé) ;
#   3 tâche déjà en cours : veilleur vivant OU enveloppe vivante (démarrage en cours, enveloppe.pid) (rien modifié) ;
#   4 identifiant déjà utilisé (état final, ou en_cours sans veilleur ni enveloppe vivants : rien modifié, à nettoyer par le lanceur) ; 75 créneau occupé ou un conteneur tache-* existe déjà (en_attente, à relancer).
# Dossier de la tâche ~/taches/<id>/ : entree/ (monté en lecture seule, l'APK y est déposé avant), sortie/ (monté en écriture :
#   pont.log, captures/, plantage.txt, entree-tache.log), etat.json, arret (créé par le lanceur : demande d'arrêt),
#   enveloppe.pid, veilleur.pid, veilleur.log, docker-run.log. Créneau : verrou flock sur ~/taches/.creneau-emulation (descripteur 8, hérité
#   par le veilleur).
# etat.json : {"id","etat","statut","debut","fin","raison"}, écrit par un fichier temporaire puis mv (jamais à moitié écrit).
#   etat : en_attente | en_cours | terminee | arretee | echouee ; statut (à la fin) : ok | plantage | limite | erreur.
#   Fin par le fichier arret -> arretee, ok (plantage si sortie/plantage.txt) ; échéance duree_s ou inactivité du pilote
#   (voir Inactivité) -> terminee, limite (plantage prime) ; conteneur disparu seul -> terminee, plantage si
#   plantage.txt existe, sinon echouee, erreur ; docker en échec -> echouee, erreur ; sortie/ au-delà de 2 x 100 Mo + 50 Mo
#   (du -sk) -> terminee, limite « sortie trop volumineuse ». L'état du conteneur est constaté AVANT d'honorer arret ;
#   arret contient « fin » (fin normale demandée par le lanceur) -> terminee, ok ; tout autre contenu -> arretee, ok.
#   Inactivité du pilote = max(mtime sortie/pont.log, sortie/.activite (touché par pont.sh au début ET à la fin de chaque verbe),
#   sortie/.avd-pret, début de la tâche).
# Limite de taille : sondage toutes les ENVELOPPE_SONDE_S (5 s) de `du -sk`, PAS un quota : un dépassement entre deux sondages
#   est accepté (résiduel connu) ; la limite du pont (octets de captures) reste la première barrière.
# ÉCART VOLONTAIRE : l'échéance duree_s est appliquée par le veilleur (et, en dernier recours, par `timeout duree+60` dans le
#   conteneur : entree-tache.sh), et non par `timeout <duree_s>` autour de `docker run -d`, qui rend la main aussitôt.
# Réservées aux tests : ENVELOPPE_SONDE_S (période de surveillance, 5 s par défaut ; le veilleur se réveille plus tôt pour
#   l'échéance de durée ou d'inactivité, jamais une période en retard ; l'état du conteneur : voir etat_docker). Aucun identifiant n'est monté ni transmis ;
# le conteneur reçoit seulement les réglages posés ci-dessous (-e NOM=valeur, jamais l'environnement de l'appelant).
set -u
export LC_ALL=C
exec </dev/null

MOTIF_ID='^t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$'
MOTIF_DUREE='^[1-9][0-9]{0,4}$'          # 1..99999, borné à 86400 plus bas
MOTIF_MEMOIRE='^[1-9][0-9]{2,4}$'        # 100..99999, borné à 256..65536 plus bas
MOTIF_CPUS='^[1-9][0-9]?$'
MOTIF_SONDE='^[0-9]{1,2}(\.[0-9]{1,3})?$'
IMAGE="myiafactory/emulateur"
IMAGE_SYSTEME="system-images;android-34;google_apis;x86_64"   # miroir de android_sdk.emulator_image de versions.json (test de concordance)
MOTIF_IMAGE_SYSTEME='^system-images;android-[0-9]{1,3}(-[a-z0-9]+)?;[a-z0-9_]+;x86_64$'
LIMITE_SORTIE_KO=256000                   # 2 x 100 Mo de captures + 50 Mo, en Ko (du -sk)
if [[ ${ENVELOPPE_SORTIE_MAX_KO:-} =~ ^[1-9][0-9]{0,8}$ ]]; then LIMITE_SORTIE_KO="$ENVELOPPE_SORTIE_MAX_KO"; fi   # tests
# /avd est un tmpfs de 9 Go (un PLAFOND : seul ce qui est écrit occupe la mémoire, ~760 Mo constatés). Pourquoi 9 Go : au premier
# démarrage l'émulateur fait une copie inscriptible du system.img de l'hôte (4,3 Go pour android-34 google_apis, partitions
# dynamiques) dans l'AVD et exige ~6 Go x 1,2 = 7,4 Go libres (« Not enough space to create userdata partition » avec 4 Go,
# constaté sur le serveur) ; disk.dataPartition.size du config.ini n'y change rien (essayé : 2G, 2048M, 2048, -partition-size).
# Une image système plus grosse que le tmpfs moins 2 Go de marge est refusée AVANT docker run, avec sa raison.
AVD_TMPFS_GO=9
IMAGE_MAX_OCTETS=$(( (9 - 2) * 1024 * 1024 * 1024 ))
if [[ ${ENVELOPPE_IMAGE_MAX_OCTETS:-} =~ ^[1-9][0-9]{0,11}$ ]]; then IMAGE_MAX_OCTETS="$ENVELOPPE_IMAGE_MAX_OCTETS"; fi   # tests

refuser() { printf '%s\n' "lancer_emulation : $1" >&2; exit 2; }

VEILLEUR=0
if [ "${1:-}" = --veilleur ]; then VEILLEUR=1; shift; fi
[ $# -ge 2 ] && [ $# -le 8 ] || refuser "usage : <id> <scenario|pilote> [duree_s [inactivite_s [memoire_mo [cpus [captures [octets]]]]]]"
for argument in "$@"; do                 # aucun caractère de contrôle (retour à la ligne final compris : `$` d'un motif l'accepterait)
  [[ $argument == *[[:cntrl:]]* ]] && refuser "caractère de contrôle refusé dans un argument."
done
ID="$1"; MODE="$2"; DUREE="${3-1200}"; INACTIVITE="${4-600}"; MEMOIRE="${5-6144}"; CPUS="${6-2}"
[[ $ID =~ $MOTIF_ID ]] || refuser "identifiant refusé."
[ "$MODE" = scenario ] || [ "$MODE" = pilote ] || refuser "mode refusé (scenario ou pilote)."
[[ $DUREE =~ $MOTIF_DUREE ]] && [ "$DUREE" -le 86400 ] || refuser "duree_s refusée (1 à 86400, sans zéro initial)."
[[ $INACTIVITE =~ $MOTIF_DUREE ]] && [ "$INACTIVITE" -le 86400 ] || refuser "inactivite_s refusée (1 à 86400, sans zéro initial)."
[[ $MEMOIRE =~ $MOTIF_MEMOIRE ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser "memoire_mo refusée (256 à 65536)."
[[ $CPUS =~ $MOTIF_CPUS ]] && [ "$CPUS" -le 64 ] || refuser "cpus refusés (1 à 64)."
SUPPL=(); ENV_SUPPL=()                   # arguments facultatifs 7 et 8 : relayés au veilleur et au conteneur
if [ $# -ge 7 ]; then
  [[ $7 =~ ^[1-9][0-9]?$ ]] && [ "$7" -le 50 ] || refuser "captures refusées (1 à 50, sans zéro initial)."
  SUPPL+=("$7"); ENV_SUPPL+=(-e "PONT_CAPTURES=$7")
fi
if [ $# -ge 8 ]; then
  [[ $8 =~ ^[1-9][0-9]{0,8}$ ]] && [ "$8" -le 104857600 ] || refuser "octets refusés (1 à 104857600, sans zéro initial)."
  SUPPL+=("$8"); ENV_SUPPL+=(-e "PONT_OCTETS=$8")
fi
[ -n "${HOME:-}" ] || refuser "HOME absent."
SONDE="${ENVELOPPE_SONDE_S:-5}"
[[ $SONDE =~ $MOTIF_SONDE ]] || SONDE=5

TACHES="$HOME/taches"
DOSSIER="$TACHES/$ID"
SDK="$HOME/android-sdk"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# --- Utilitaires -----------------------------------------------------------

maintenant_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echapper_json() {
  local s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/ }"; s="${s//$'\r'/ }"; s="${s//$'\t'/ }"
  printf '%s' "$s"
}

# ecrire_etat <etat> <statut|""> <debut|""> <fin|""> <raison> : fichier temporaire puis mv, un seul fichier etat.json.
ecrire_etat() {
  local tmp="$DOSSIER/etat.json.$$.tmp" s=null d=null f=null
  [ -n "$2" ] && s="\"$2\""
  [ -n "$3" ] && d="\"$3\""
  [ -n "$4" ] && f="\"$4\""
  printf '{"id": "%s", "etat": "%s", "statut": %s, "debut": %s, "fin": %s, "raison": "%s"}\n' \
    "$ID" "$1" "$s" "$d" "$f" "$(echapper_json "$5")" > "$tmp" && mv -f "$tmp" "$DOSSIER/etat.json" || rm -f "$tmp"
}

montrer_etat() { [ -f "$DOSSIER/etat.json" ] && tr -d '\n' < "$DOSSIER/etat.json" && printf '\n'; }

debut_ecrit() {   # date de début lue dans etat.json (écrit par nous)
  sed -n 's/.*"debut": "\([0-9TZ:-]*\)".*/\1/p' "$DOSSIER/etat.json" 2>/dev/null | head -n 1
}

liberer_creneau() { flock -u 8 2>/dev/null; exec 8>&-; }

# docker sans hériter du verrou (8>&-) ni de l'entrée, et borné : un docker figé ne fige jamais l'enveloppe.
dk() { local delai="$1"; shift; timeout "$delai" sudo -n docker "$@" 8>&- </dev/null; }

# État du conteneur : `docker inspect` (par sudo : une ligne d'auth.log) seulement quand il le faut. Entre deux, le processus
# principal du conteneur (PID relevé par inspect) est suivi dans /proc, sans sudo : même PID ET même date de démarrage
# (champ 22 de /proc/<pid>/stat), jamais un PID recyclé.
PID_CONTENEUR=""; DEBUT_CONTENEUR=""
debut_processus() {   # debut_processus <pid> : date de démarrage du processus (ticks depuis l'amorçage)
  local s
  s=$(cat -- "/proc/$1/stat" 2>/dev/null) || return 1
  s="${s##*) }"
  set -- $s
  [[ ${20:-} =~ ^[0-9]+$ ]] || return 1
  printf '%s' "${20}"
}

# Seule la SORTIE STANDARD de docker inspect est analysée : un avertissement sur la sortie d'erreur (« sudo: unable to
# resolve host », avertissement du client docker) avec le code 0 ne doit jamais faire passer un conteneur vivant pour
# disparu. La sortie d'erreur va dans un fichier privé du dossier de la tâche (retiré aussitôt) et n'est lue que pour
# « No such » (conteneur absent). Une réponse qui n'a pas exactement la forme « true|false <pid> » = on ne sait pas (2).
etat_docker() {   # 0 vivant, 1 absent ou arrêté, 2 docker ne répond pas ou réponse illisible
  local sortie r erreurs fichier="$DOSSIER/.inspect.$$.err" p
  sortie=$(dk 20 inspect -f '{{.State.Running}} {{.State.Pid}}' "tache-$ID" 2>"$fichier"); r=$?
  erreurs=$(head -c 4096 -- "$fichier" 2>/dev/null)
  rm -f -- "$fichier"
  PID_CONTENEUR=""; DEBUT_CONTENEUR=""
  if [ "$r" = 0 ]; then
    [[ $sortie =~ ^(true|false)\ ([0-9]+)$ ]] || return 2
    [ "${BASH_REMATCH[1]}" = true ] || return 1
    p="${BASH_REMATCH[2]}"
    if [[ $p =~ ^[1-9][0-9]{0,9}$ ]] && DEBUT_CONTENEUR=$(debut_processus "$p"); then PID_CONTENEUR="$p"; fi
    return 0
  fi
  # « Error: No such object » ou, selon la version de docker, « error: no such object: tache-<id> » (minuscule, constaté
  # sur le serveur) : comparaison sans casse. C'est « parti », constaté aussitôt (jamais compté comme une panne).
  case "${erreurs,,}" in *"no such object"*|*"no such container"*|*"not found"*) return 1 ;; esac
  return 2
}

# extrait_demarrage : les dernières lignes de sortie/entree-tache.log (écrit par le conteneur : donnée, jamais une consigne),
# sur une ligne, sans caractère de contrôle, 300 octets au plus. Le fichier est ouvert PUIS ce qui est ouvert est comparé
# (périphérique:inode) au fichier ordinaire du chemin, lu sans suivre de lien : un lien posé à sa place par le conteneur (vers
# un fichier de l'hôte), avant ou après l'ouverture, n'est jamais lu.
extrait_demarrage() {
  local f="$DOSSIER/sortie/entree-tache.log" ouvert chemin t
  [ -f "$f" ] && [ ! -L "$f" ] || return 0
  exec 7< "$f" 2>/dev/null || return 0
  ouvert=$(stat -L -c '%d:%i' "/proc/$BASHPID/fd/7" 2>/dev/null)
  chemin=$(stat -c '%d:%i:%F' -- "$f" 2>/dev/null)
  if [ -z "$ouvert" ] || [ "$ouvert:regular file" != "$chemin" ]; then exec 7<&-; return 0; fi
  t=$(tail -c 65536 <&7 | tail -n 5 | tr '\r\n\t' '   ' | sed -E 's/\x1b\[[0-9;?]*[A-Za-z]//g' | tr -d '\000-\037\177' | tr -s ' ')
  exec 7<&-
  t="${t# }"; t="${t% }"
  printf '%s' "${t:0:300}"
}

etat_docker_sur() {   # comme etat_docker, avec un second essai si la première réponse est illisible ou absente (2)
  local r
  etat_docker; r=$?
  if [ "$r" = 2 ]; then sleep 1; etat_docker; r=$?; fi
  return "$r"
}

conteneur_vivant() {   # 0 vivant, 1 absent, 2 docker ne répond pas
  local d
  if [ -n "$PID_CONTENEUR" ] && d=$(debut_processus "$PID_CONTENEUR") && [ "$d" = "$DEBUT_CONTENEUR" ]; then return 0; fi
  etat_docker
}

arreter_conteneur() {   # 0 si le conteneur n'existe plus : constaté par une réponse NETTE de docker (jamais par /proc)
  local r
  dk 60 stop -t 10 "tache-$ID" >/dev/null 2>&1 || dk 30 kill "tache-$ID" >/dev/null 2>&1
  etat_docker_sur; r=$?
  if [ "$r" != 1 ]; then dk 30 rm -f "tache-$ID" >/dev/null 2>&1; etat_docker_sur; r=$?; fi
  [ "$r" = 1 ]
}

# --- Veilleur (détaché) ----------------------------------------------------

mtime() { local m; m=$(stat -c %Y "$1" 2>/dev/null); if [[ $m =~ ^[0-9]+$ ]]; then printf '%s' "$m"; else printf 0; fi; }

veilleur() {
  { : >&8; } 2>/dev/null || exit 2                  # sans le créneau hérité de l'enveloppe, jamais de veilleur
  printf '%s\n' "$$" > "$DOSSIER/veilleur.pid"
  local debut_iso debut_s maintenant derniere m pannes=0 etat_conteneur plantage=0 motif ko prochaine pause ext
  debut_iso=$(debut_ecrit); [ -n "$debut_iso" ] || debut_iso=$(maintenant_iso)
  debut_s=$(date +%s)
  FINI=0
  conclure() {   # conclure <etat> <statut> <raison>
    FINI=1
    ecrire_etat "$1" "$2" "$debut_iso" "$(maintenant_iso)" "$3"
    liberer_creneau
    exit 0
  }
  trap 'if [ "$FINI" = 0 ]; then arreter_conteneur; conclure echouee erreur "Veilleur interrompu avant la fin de la tâche."; fi' EXIT
  trap 'exit 143' TERM INT HUP
  # arreter_puis <etat> <statut> <raison> : arrête le conteneur ; plantage.txt prime sur ok et limite.
  arreter_puis() {
    local etat="$1" statut="$2" raison="$3"
    arreter_conteneur || conclure echouee erreur "$raison mais le conteneur tache-$ID ne s'arrête pas : à arrêter à la main (docker stop)."
    if [ -e "$DOSSIER/sortie/plantage.txt" ]; then plantage=1; fi       # relu APRÈS l'arrêt : un plantage écrit entre-temps compte
    if [ "$plantage" = 1 ]; then conclure "$etat" plantage "$raison ; plantage relevé (plantage.txt)."; fi
    conclure "$etat" "$statut" "$raison."
  }
  while :; do
    if [ -e "$DOSSIER/sortie/plantage.txt" ]; then plantage=1; else plantage=0; fi
    # L'état du conteneur d'abord : un conteneur mort reste une erreur même si arret existe.
    conteneur_vivant; etat_conteneur=$?
    if [ "$etat_conteneur" = 1 ]; then
      if [ "$plantage" = 1 ]; then conclure terminee plantage "Le conteneur s'est arrêté ; plantage relevé (plantage.txt)."; fi
      if [ ! -e "$DOSSIER/sortie/.avd-pret" ]; then         # mort avant que l'AVD n'existe : la raison est dans le journal d'entrée
        ext=$(extrait_demarrage)
        [ -n "$ext" ] || ext="voir sortie/entree-tache.log"
        conclure echouee erreur "Le conteneur s'est arrêté au démarrage : $ext"
      fi
      conclure echouee erreur "Le conteneur s'est arrêté de lui-même avant la fin (voir sortie/entree-tache.log)."
    elif [ "$etat_conteneur" = 2 ]; then
      pannes=$((pannes + 1))
      [ "$pannes" -lt 30 ] || conclure echouee erreur "Docker ne répond plus : état du conteneur inconnu."
    else
      pannes=0
    fi
    if [ -e "$DOSSIER/arret" ]; then
      motif=""; IFS= read -r motif < "$DOSSIER/arret" 2>/dev/null
      if [ "$motif" = fin ]; then arreter_puis terminee ok "Fin demandée par le lanceur (arret : fin)"; fi
      arreter_puis arretee ok "Arrêt demandé (fichier arret)"
    fi
    maintenant=$(date +%s)
    if [ $((maintenant - debut_s)) -ge "$DUREE" ]; then arreter_puis terminee limite "Durée maximale atteinte (${DUREE} s)"; fi
    prochaine=$((DUREE - (maintenant - debut_s)))            # secondes avant la prochaine échéance (durée, puis inactivité)
    ko=$(du -sk "$DOSSIER/sortie" 2>/dev/null | cut -f1)
    if [[ $ko =~ ^[0-9]+$ ]] && [ "$ko" -gt "$LIMITE_SORTIE_KO" ]; then
      arreter_puis terminee limite "Limite atteinte : sortie trop volumineuse (${ko} Ko, maximum ${LIMITE_SORTIE_KO} Ko)"
    fi
    if [ "$MODE" = pilote ]; then
      derniere=$debut_s
      m=$(mtime "$DOSSIER/sortie/pont.log"); [ "$m" -gt "$derniere" ] && derniere=$m
      m=$(mtime "$DOSSIER/sortie/.activite"); [ "$m" -gt "$derniere" ] && derniere=$m
      m=$(mtime "$DOSSIER/sortie/.avd-pret"); [ "$m" -gt "$derniere" ] && derniere=$m      # AVD créé : le conteneur travaille
      if [ $((maintenant - derniere)) -ge "$INACTIVITE" ]; then
        arreter_puis terminee limite "Inactivité du pilote : aucun verbe depuis ${INACTIVITE} s"
      fi
      [ $((INACTIVITE - (maintenant - derniere))) -lt "$prochaine" ] && prochaine=$((INACTIVITE - (maintenant - derniere)))
    fi
    # Sommeil d'une sonde, raccourci jusqu'à l'échéance la plus proche si elle tombe avant (au moins 1 s).
    pause="$SONDE"
    [ "$prochaine" -ge 1 ] || prochaine=1
    [ "${SONDE%%.*}" -ge "$prochaine" ] && pause="$prochaine"
    sleep "$pause"
  done
}

if [ "$VEILLEUR" = 1 ]; then veilleur; exit 0; fi

# --- Enveloppe (au premier plan, rend vite la main) ------------------------

fin_erreur() {   # fin_erreur <raison> : tâche échouée, créneau libéré (un état final déjà écrit par arreter est gardé)
  if grep -qE '"etat": "(terminee|arretee|echouee)"' "$DOSSIER/etat.json" 2>/dev/null; then
    liberer_creneau; montrer_etat; exit 4
  fi
  ecrire_etat echouee erreur "$(debut_ecrit)" "$(maintenant_iso)" "$1"
  liberer_creneau
  montrer_etat
  exit 1
}

# Un veilleur est vivant si son PID existe ET si /proc/<pid>/cmdline porte le marqueur --veilleur et l'identifiant (jamais un
# PID recyclé par un autre processus).
processus_vivant() {   # processus_vivant <fichier du pid> <motif>... : le PID existe ET sa ligne de commande porte tous les motifs
  local fichier="$1" pid="" cmd m
  shift
  [ -f "$fichier" ] && IFS= read -r pid < "$fichier"
  [[ $pid =~ ^[0-9]{1,10}$ ]] || return 1
  [ -r "/proc/$pid/cmdline" ] || return 1
  cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  for m in "$@"; do [[ $cmd == *"$m"* ]] || return 1; done
  return 0
}
veilleur_vivant() { processus_vivant "$DOSSIER/veilleur.pid" "--veilleur $ID"; }
# L'enveloppe d'un lancement en cours de démarrage (docker run peut durer 120 s, le veilleur n'existe pas encore).
enveloppe_vivante() { processus_vivant "$DOSSIER/enveloppe.pid" "lancer_emulation.sh $ID"; }   # paire contiguë, comme le lanceur

umask 077
mkdir -p -- "$DOSSIER/entree" "$DOSSIER/sortie" || refuser "dossier de la tâche non créable."
chmod 755 "$DOSSIER/entree"
chmod 777 "$DOSSIER/sortie"        # écrit par l'utilisateur 1000 du conteneur, quel que soit le propriétaire de l'hôte

# Un identifiant ne sert qu'une fois : seul un état absent ou en_attente (jamais démarré) peut être relancé, de sorte que
# plantage.txt, .avd-pret ou des captures d'une tâche précédente ne fuient jamais dans la suivante. Rien n'est modifié.
if [ -f "$DOSSIER/etat.json" ] && ! grep -q '"etat": "en_attente"' "$DOSSIER/etat.json"; then
  montrer_etat
  if grep -q '"etat": "en_cours"' "$DOSSIER/etat.json" && { veilleur_vivant || enveloppe_vivante; }; then exit 3; fi
  exit 4
fi
rm -f "$DOSSIER/arret"

case "$SDK$DOSSIER" in
  *,*) fin_erreur "Chemin non admis (virgule) : montage impossible." ;;
esac

exec 8>> "$TACHES/.creneau-emulation" || { ecrire_etat echouee erreur "" "$(maintenant_iso)" "Créneau inaccessible."; exit 1; }
trap '' HUP                         # la fin de la session SSH ne doit jamais interrompre l'écriture de l'état
# Un `arreter` du lanceur a pu passer pendant l'attente du créneau (il retire l'APK puis écrit arretee) : un état FINAL est
# alors honoré, jamais réécrit (ni en_attente, ni en_cours) ; la tâche ne démarre jamais sans son APK. Relu sous le créneau,
# juste avant chaque écriture d'état. RÉSIDUEL CONNU (laissé ouvert) : entre honorer_final et ecrire_etat en_cours (moins
# d'une milliseconde), un _ARRETER du lanceur, qui ne prend pas le créneau, peut encore retirer l'APK et écrire arretee ;
# son second contrôle voit alors en_cours et n'écrase rien, et le lanceur, qui tient l'état rendu par arreter pour seul
# juge, rappelle arreter (fichier arret) : la tâche démarrée sans APK est arrêtée au tour suivant. Le fermer demanderait un
# verrou par tâche partagé par l'enveloppe et _ARRETER.
honorer_final() {
  if grep -qE '"etat": "(terminee|arretee|echouee)"' "$DOSSIER/etat.json" 2>/dev/null; then
    liberer_creneau
    montrer_etat
    exit 4
  fi
}
occupe() {   # occupe <raison> : jamais deux émulateurs ; ne remplace jamais un état en_cours ni un état final
  honorer_final
  grep -q '"etat": "en_cours"' "$DOSSIER/etat.json" 2>/dev/null || ecrire_etat en_attente "" "" "" "$1"
  liberer_creneau
  montrer_etat
  exit 75
}
flock -n 8 || occupe "Créneau d'émulation occupé : une autre tâche tourne, relancez plus tard."
honorer_final
existants=$(dk 20 ps -q --filter "name=^tache-") || fin_erreur "Docker ne répond pas : impossible de vérifier qu'aucun émulateur ne tourne."
[ -z "$existants" ] || occupe "Un conteneur tache-* tourne déjà (veilleur mort ?) : relancez plus tard."

kvm_gid=$(getent group kvm 2>/dev/null | cut -d: -f3)
[[ $kvm_gid =~ ^[0-9]{1,10}$ ]] || fin_erreur "Groupe kvm introuvable sur ce serveur : l'émulateur ne peut pas être accéléré."
[[ $IMAGE_SYSTEME =~ $MOTIF_IMAGE_SYSTEME ]] || fin_erreur "Image système mal formée."
# Taille du system.img de l'image épinglée (stat sans suivre de lien : absent ici, l'entrée du conteneur dira l'image absente).
taille_img=$(stat -c %s -- "$SDK/${IMAGE_SYSTEME//;//}/system.img" 2>/dev/null)
if [[ $taille_img =~ ^[0-9]{1,15}$ ]] && [ "$taille_img" -gt "$IMAGE_MAX_OCTETS" ]; then
  fin_erreur "Image système trop grosse pour /avd : system.img fait $((taille_img / 1048576)) Mo, au plus $((IMAGE_MAX_OCTETS / 1048576)) Mo (tmpfs /avd de ${AVD_TMPFS_GO} Go moins 2 Go de marge : l'émulateur en fait une copie inscriptible)."
fi

honorer_final                                       # relu juste avant d'écrire en_cours
printf '%s\n' "$$" > "$DOSSIER/enveloppe.pid"      # AVANT en_cours : un second lancement voit une enveloppe vivante, pas un veilleur mort
ecrire_etat en_cours "" "$(maintenant_iso)" "" "Conteneur en cours de démarrage."

# --mount (et non -v) : un chemin source absent est une erreur, jamais un dossier créé par root ; SDK et entree en lecture seule.
COMMANDE=(run --pull never --rm -d --init --name "tache-$ID" --network none --device /dev/kvm
  --user 1000:1000 --group-add "$kvm_gid" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:size=512m,mode=1777 --tmpfs "/avd:size=${AVD_TMPFS_GO}g,mode=1777"
  --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS" --pids-limit 512 --ulimit nofile=4096:4096
  -e ANDROID_AVD_HOME=/avd -e HOME=/tmp -e ANDROID_USER_HOME=/tmp/.android -e PONT_SORTIE=/sortie -e PONT_AVD=emul
  -e PONT_EMULATEUR=/opt/android-sdk/emulator/emulator -e PONT_ADB=/opt/android-sdk/platform-tools/adb
  -e "TACHE_DUREE_S=$DUREE" -e "TACHE_IMAGE_SYSTEME=$IMAGE_SYSTEME" ${ENV_SUPPL[@]+"${ENV_SUPPL[@]}"}
  --mount "type=bind,src=$SDK,dst=/opt/android-sdk,readonly"
  --mount "type=bind,src=$DOSSIER/entree,dst=/entree,readonly"
  --mount "type=bind,src=$DOSSIER/sortie,dst=/sortie"
  "$IMAGE")
if ! dk 120 "${COMMANDE[@]}" >/dev/null 2>"$DOSSIER/docker-run.log"; then
  dk 30 rm -f "tache-$ID" >/dev/null 2>&1          # un docker run figé (délai) a pu laisser un conteneur à demi créé
  fin_erreur "Démarrage du conteneur impossible (docker run en échec : voir docker-run.log)."
fi

# Veilleur détaché : il hérite du descripteur 8 (donc du créneau) et le libère à la fin, même si cette session SSH a disparu.
if command -v setsid >/dev/null 2>&1; then
  setsid nohup bash "$SELF" --veilleur "$ID" "$MODE" "$DUREE" "$INACTIVITE" "$MEMOIRE" "$CPUS" ${SUPPL[@]+"${SUPPL[@]}"} </dev/null >> "$DOSSIER/veilleur.log" 2>&1 &
else
  nohup bash "$SELF" --veilleur "$ID" "$MODE" "$DUREE" "$INACTIVITE" "$MEMOIRE" "$CPUS" ${SUPPL[@]+"${SUPPL[@]}"} </dev/null >> "$DOSSIER/veilleur.log" 2>&1 &
fi
disown 2>/dev/null
# Rendre la main seulement quand veilleur.pid existe : après, « en_cours sans veilleur vivant » ne peut plus être qu'un veilleur mort.
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  [ -s "$DOSSIER/veilleur.pid" ] && break
  sleep 0.1
done
montrer_etat
exit 0
