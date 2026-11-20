#!/usr/bin/env bash
# Pont d'actions de l'émulateur : SEULE porte d'entrée d'un agent ou d'une recette dans le conteneur `myiafactory/emulateur`
# (copié en /usr/local/bin/pont par l'image).
# Usage : pont <verbe> [arguments]
# Liste fermée de verbes ; chaque argument est validé par un motif AVANT tout usage ; aucun eval, aucun argument dans une
# commande composée ni dans un motif de fichiers (expansion des motifs coupée : set -f) ; les limites sont appliquées ici,
# pas par la bonne foi de l'appelant.
# Les arguments donnés à `adb shell` sont relus par le shell de l'appareil : c'est pourquoi les motifs n'admettent aucun
# caractère spécial du shell (ni ; $ ` ' " | & < > ( ) * ? [ \ ni retour à la ligne) et commencent par une lettre ou un
# chiffre (jamais une option comme -s ou --).
# Sortie standard : UNE ligne JSON {"ok": bool, "verbe": "...", "detail": "..."}.
# Codes de retour : 0 ok ; 2 verbe ou argument refusé ; 3 limite atteinte ; 4 outil ou réglage en échec.
#   Décision R7 : un nom de capture déjà pris rend 2 (argument refusé), JAMAIS 3 : 3 est réservé aux vraies limites
#   (nombre ou octets de captures), pour que le statut « limite » du rapport reste juste. Un second `demarrer` alors que
#   l'émulateur tourne rend aussi 2.
# Environnement : posé par l'enveloppe lancer_emulation.sh, JAMAIS transmis par l'appelant (celui qui relaie un verbe ne doit
# en aucun cas faire suivre son propre environnement : ces variables désignent les outils exécutés et les limites).
#   PONT_SORTIE (/sortie ; absolu, sans . ni ..), PONT_CAPTURES (50), PONT_OCTETS (104857600 = 100 Mo de médias cumulés :
#   captures, vidéos et images des vidéos),
#   PONT_AVD (emulateur ; motif MOTIF_NOM, donc en minuscules : la tâche 4 nomme l'AVD « emul »), PONT_DEMARRAGE_S (300),
#   PONT_DELAI_ADB_S (30 : délai de chaque appel à adb, `installer` x4 ; attente d'un verrou = 3 x délai + 10 s),
#   PONT_PAQUET (facultatif : sinon le paquet est relevé par `installer`) ;
#   PONT_ADB / PONT_EMULATEUR / PONT_FFMPEG : « adb » / « emulator » / « ffmpeg » ou un chemin absolu (tests) ;
#   PONT_LOGCAT_OCTETS (2097152 : plafond de logcat.txt), PONT_VIDEOS (5 vidéos), PONT_VIDEO_OCTETS (62914560 = 60 Mo par
#   vidéo), PONT_FILM_PAS (2 : écart minimal en secondes entre deux images d'une vidéo ; 30 images au plus, réparties sur
#   tout le film : une toutes les max(PONT_FILM_PAS, durée/30) s).
#   Les octets des médias (captures, vidéos, images des vidéos) se partagent la limite PONT_OCTETS.
# Écrit seulement sous PONT_SORTIE : .activite (vide, touché au début et à la fin de chaque verbe valide), pont.log, captures/<nom>.png, plantage.txt, .paquet, emulateur.log, emulateur.pid,
# logcat.txt (lignes de `journal`), videos/<nom>.mp4 et videos/<nom>-img/<nom>-NNN.png, .film (le film en cours),
# .film.fin (un film en train d'être fini), .verrou-captures, .verrou-demarrer, .verrou-film, .verrou-journal (ou leurs
# dossiers .d sans flock).
# Film : `filmer` lance `adb shell screenrecord` DÉTACHÉ (rend la main aussitôt ; borné par --time-limit côté appareil et par
# timeout côté conteneur) et note « nom pid début durée » dans .film ; un seul film à la fois. `finfilm` (ou `arreter`, qui
# finit un film resté en cours plutôt que de le perdre) envoie SIGINT au screenrecord de l'appareil (mp4 finalisé), rapatrie
# le fichier, le vérifie (signature « ftyp » aux octets 4..8, tailles) puis en tire des images avec ffmpeg.
# Exige `timeout` (coreutils) : sans lui, refus (code 4) plutôt qu'un adb sans borne. Aucun outil ne reçoit le descripteur 9
# du verrou (9>&-) : un serveur adb resté en vie ne doit pas garder le verrou.
# emulateur.pid ne désigne l'émulateur que si /proc/<pid> le confirme (PID >= 2, pas zombie, argv[0] de nom de base
# emulator* ou qemu-system*) : un PID mort, zombie, recyclé, 0 ou 1 n'est jamais signalé ; le groupe n'est visé que si
# l'émulateur en est le chef. `demarrer` garde son verrou jusqu'à ce que le nouveau processus soit reconnu (5 s au plus).
# Un appel = une ligne « verbe arguments durée » ajoutée à ${PONT_SORTIE}/pont.log (au plus 6 arguments, chacun tronqué à
# 80 caractères, caractères hors liste remplacés par « ? »).
set -u
set -f
set -o pipefail
export LC_ALL=C
exec </dev/null

# ==============================================================================================================
# MOTIFS DU PONT : table unique, expressions régulières POSIX étendues ancrées.
# Miroir Python à garder IDENTIQUE : VERBES de outils/serveur_tache.py (décision R2) ; le test
# test_motifs_python_et_pont_s_accordent fait passer les mêmes exemples par les deux.
MOTIF_ENTIER='^[0-9]{1,4}$'                              # coordonnée : 0 à 9999
MOTIF_DUREE='^([0-9]{1,2}|1[01][0-9]|120)$'               # attendre : 0 à 120 secondes
MOTIF_NOM='^[a-z0-9][a-z0-9_-]{0,39}$'                   # nom de capture
MOTIF_TEXTE='^[A-Za-z0-9][A-Za-z0-9 .,_-]{0,59}$'        # texte saisi (espaces transmis en %s à `input text`)
MOTIF_FILTRE='^[A-Za-z0-9][A-Za-z0-9._:-]{0,59}$'        # filtre du journal (texte littéral, pas une expression)
MOTIF_TOUCHE='^(retour|accueil|menu)$'
MOTIF_SECONDES_FILM='^([1-9][0-9]?|1[0-7][0-9]|180)$'    # filmer : 1 à 180 secondes
# Refusé EN PLUS de MOTIF_NOM : noms réservés de Windows (la capture ne pourrait pas être rapatriée sur le poste).
MOTIF_NOM_RESERVE='^(con|prn|aux|nul|com[0-9]|lpt[0-9])$'
# verbe -> motifs de ses arguments, dans l'ordre ; FACULTATIFS = nombre de derniers arguments facultatifs.
#   demarrer, installer, lancer, arreter, finfilm : aucun argument (installer prend toujours entree/app.apk, chemin fixe)
motifs_du_verbe() {
  MOTIFS=(); FACULTATIFS=0
  case "$1" in
    demarrer|installer|lancer|arreter|finfilm) ;;
    toucher)  MOTIFS=("$MOTIF_ENTIER" "$MOTIF_ENTIER") ;;
    glisser)  MOTIFS=("$MOTIF_ENTIER" "$MOTIF_ENTIER" "$MOTIF_ENTIER" "$MOTIF_ENTIER") ;;
    texte)    MOTIFS=("$MOTIF_TEXTE") ;;
    touche)   MOTIFS=("$MOTIF_TOUCHE") ;;
    attendre) MOTIFS=("$MOTIF_DUREE") ;;
    capturer) MOTIFS=("$MOTIF_NOM") ;;
    journal)  MOTIFS=("$MOTIF_FILTRE"); FACULTATIFS=1 ;;
    filmer)   MOTIFS=("$MOTIF_NOM" "$MOTIF_SECONDES_FILM"); FACULTATIFS=1 ;;
    *) return 1 ;;
  esac
}
# Internes (hors table de l'appelant) : nom de paquet relevé sur l'appareil, réglages de l'environnement.
MOTIF_PAQUET='^[A-Za-z][A-Za-z0-9_]{0,60}(\.[A-Za-z][A-Za-z0-9_]{0,60}){1,10}$'
MOTIF_REGLAGE='^[0-9]{1,12}$'
MOTIF_POINTS='(^|/)\.\.?(/|$)'                           # composant . ou .. dans un chemin
# ==============================================================================================================

LISTE_VERBES="demarrer, installer, lancer, toucher, glisser, texte, touche, attendre, capturer, journal, arreter, filmer, finfilm"
LIGNES_JOURNAL=200
LARGEUR_JOURNAL=500
ARGS_JOURNALISES=6
SORTIE_VALIDE=0
SORTIE=""

# --- Utilitaires -----------------------------------------------------------

horloge_us() {   # met dans HORLOGE l'heure en microsecondes (sans processus)
  local t="${EPOCHREALTIME:-}"
  t="${t//[.,]/}"
  if [[ $t =~ ^[0-9]+$ ]]; then HORLOGE=$((10#$t)); else HORLOGE=$((SECONDS * 1000000)); fi
}
horloge_us; DEBUT_US=$HORLOGE

echapper_json() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

# Texte venu de l'extérieur (journal de l'appareil) : tout octet non imprimable devient « ? » (JSON toujours valide).
assainir() { tr -c '[:print:]\t\n' '?'; }

VERBE="${1-}"
[ $# -gt 0 ] && shift
ARGS=("$@")
VERBE_SUR="${VERBE:0:40}"
VERBE_SUR="${VERBE_SUR//[^a-z0-9_-]/?}"

# Une ligne par appel, sans sous-processus par argument : au plus ARGS_JOURNALISES arguments, puis « … (N arguments) ».
journaliser() {
  [ "$SORTIE_VALIDE" = 1 ] || return 0
  local ligne="$VERBE_SUR" a n=0
  [ -n "$ligne" ] || ligne='""'
  for a in "${ARGS[@]}"; do
    if [ "$n" -ge "$ARGS_JOURNALISES" ]; then ligne+=" … (${#ARGS[@]} arguments)"; break; fi
    a="${a:0:80}"
    a="${a//[^A-Za-z0-9 .,_:-]/?}"
    [ -n "$a" ] || a='""'
    ligne+=" $a"
    n=$((n + 1))
  done
  horloge_us
  mkdir -p -- "$SORTIE" 2>/dev/null
  printf '%s %sms\n' "$ligne" "$(( (HORLOGE - DEBUT_US) / 1000 ))" >> "$SORTIE/pont.log" 2>/dev/null
}

# repondre <code> <détail> : écrit l'unique ligne JSON, la ligne du journal, et termine avec <code>.
# Activité : l'enveloppe hôte mesure l'inactivité du pilote sur la date de SORTIE/.activite (jamais lue, vide), touchée au début
# ET à la fin de chaque verbe valide. Sans course : un lien symbolique, un dossier, un FIFO, un périphérique ne sont jamais ouverts
# ni suivis ; un fichier ordinaire existant n'est jamais tronqué (touch -h : date seulement, jamais bloquant) ; la création
# (fichier absent) se fait en noclobber (O_EXCL : échoue si quelque chose est apparu entre-temps, lien compris).
ACTIVITE_ACTIVE=0
activite() {
  local f="$SORTIE/.activite"
  if [ -L "$f" ]; then
    :
  elif [ -f "$f" ]; then
    touch -h -- "$f" 2>/dev/null
  elif [ ! -e "$f" ]; then
    ( set -C; : > "$f" ) 2>/dev/null
  fi
  return 0
}

repondre() {
  local code="$1" detail="$2" ok=false
  [ "$code" -eq 0 ] && ok=true
  printf '{"ok": %s, "verbe": "%s", "detail": "%s"}\n' "$ok" "$VERBE_SUR" "$(echapper_json "$detail")"
  journaliser
  [ "$ACTIVITE_ACTIVE" = 1 ] && activite
  exit "$code"
}

# reglage <nom> <valeur> <défaut> : met dans REGLAGE l'entier venu de l'environnement, sinon refus (code 4).
# Appelé dans le shell principal (jamais dans $(...)) pour que le refus écrive bien sa ligne JSON.
reglage() {
  local v="${2:-$3}"
  [[ $v =~ $MOTIF_REGLAGE ]] || repondre 4 "Réglage $1 mal formé : le pont refuse de travailler sans limite sûre."
  REGLAGE=$((10#$v))
}

# Chemins venus de l'environnement : PONT_SORTIE absolu sans . ni .. ; outils = nom attendu ou chemin absolu.
verifier_environnement() {
  local s="${PONT_SORTIE-/sortie}" nom valeur
  [ -n "$s" ] && [ "${s:0:1}" = / ] || repondre 4 "PONT_SORTIE vide ou non absolu."
  [[ $s =~ $MOTIF_POINTS ]] && repondre 4 "PONT_SORTIE ne doit contenir ni . ni .. ."
  while [ "${s%/}" != "$s" ]; do s="${s%/}"; done
  [ -n "$s" ] || repondre 4 "PONT_SORTIE ne peut pas être la racine."
  for nom in adb emulator ffmpeg; do
    case "$nom" in
      adb) valeur="${PONT_ADB-adb}" ;;
      emulator) valeur="${PONT_EMULATEUR-emulator}" ;;
      ffmpeg) valeur="${PONT_FFMPEG-ffmpeg}" ;;
    esac
    [ "$valeur" = "$nom" ] && continue
    [ "${valeur:0:1}" = / ] && [[ ! $valeur =~ $MOTIF_POINTS ]] && continue
    repondre 4 "Outil $nom mal désigné : « $nom » ou un chemin absolu."
  done
  SORTIE="$s"
  SORTIE_VALIDE=1
  APK="$SORTIE/../entree/app.apk"
  ADB="${PONT_ADB-adb}"
  EMULATEUR="${PONT_EMULATEUR-emulator}"
  FFMPEG="${PONT_FFMPEG-ffmpeg}"
}

# outil <délai s> <commande...> : coupe un outil bloqué (TERM au délai, KILL 2 s plus tard) ; descripteur du verrou fermé.
outil() {
  local d="$1"; shift
  [ "$d" -ge 1 ] || d=1
  timeout -k 2 "$d" "$@" 9>&-
}

# Verrous (captures : compte + capture + revérification + mv ; demarrer : contrôle du PID + lancement + emulateur.pid).
# flock sur le descripteur 9 quand il existe (image Linux) ; sinon un dossier créé atomiquement par mkdir, avec le PID
# du détenteur dedans : un dossier dont le détenteur est mort est repris (verrou périmé après un SIGKILL).
VERROU_DOSSIER=""
VERROU_FD=0
liberer_verrou() {
  local p=""
  if [ "$VERROU_FD" = 1 ]; then exec 9>&-; VERROU_FD=0; fi
  if [ -n "$VERROU_DOSSIER" ]; then
    IFS= read -r p < "$VERROU_DOSSIER/pid" 2>/dev/null
    [ "$p" = "$$" ] && rm -rf -- "$VERROU_DOSSIER"
    VERROU_DOSSIER=""
  fi
  return 0
}
trap liberer_verrou EXIT
prendre_verrou() {   # prendre_verrou <nom> [attente_s] (par défaut 3 x délai adb + 10 s)
  local f="$SORTIE/.verrou-$1" attente="${2:-$((3 * DELAI_ADB + 10))}" debut=$SECONDS p q m perime
  if command -v flock > /dev/null 2>&1; then
    exec 9>> "$f" || repondre 4 "Verrou $1 impossible."
    VERROU_FD=1
    flock -w "$attente" 9 || repondre 4 "Verrou $1 occupé depuis $attente s."
    return 0
  fi
  until mkdir -- "$f.d" 2>/dev/null; do
    p=""
    perime=0
    IFS= read -r p < "$f.d/pid" 2>/dev/null
    if [[ $p =~ ^[0-9]{1,10}$ ]]; then
      [ -d "/proc/$p" ] || perime=1                    # détenteur mort (tué par SIGKILL)
    elif [ -z "$p" ]; then                             # sans PID : périmé seulement s'il est plus vieux que l'attente
      m=$(stat -c %Y -- "$f.d" 2>/dev/null)
      [[ $m =~ ^[0-9]+$ ]] && [ $(( ${EPOCHSECONDS:-$(date +%s)} - m )) -gt "$attente" ] && perime=1
    fi
    if [ "$perime" = 1 ]; then
      # Mis de côté sous un nom unique (mv -T : jamais imbriqué), supprimé si c'est bien le même détenteur.
      if mv -T -- "$f.d" "$f.d.perime.$$" 2>/dev/null; then
        q=""
        IFS= read -r q < "$f.d.perime.$$/pid" 2>/dev/null
        if [ "$q" != "$p" ]; then mv -T -- "$f.d.perime.$$" "$f.d" 2>/dev/null; fi
        rm -rf -- "$f.d.perime.$$"
      fi
      continue
    fi
    [ $((SECONDS - debut)) -lt "$attente" ] || repondre 4 "Verrou $1 occupé depuis $attente s."
    sleep 0.2
  done
  VERROU_DOSSIER="$f.d"
  printf '%s\n' "$$" > "$f.d/pid"
}

# Paquet de l'APK : PONT_PAQUET, sinon celui relevé par `installer` ; rien si inconnu ou mal formé.
paquet_connu() {
  local p="${PONT_PAQUET:-}"
  if [ -z "$p" ] && [ -f "$SORTIE/.paquet" ]; then IFS= read -r p < "$SORTIE/.paquet" || true; fi
  [[ $p =~ $MOTIF_PAQUET ]] && printf '%s' "$p"
}

# Écrit plantage.txt si le journal contient FATAL EXCEPTION (suivie de « Process: <paquet> ») ou « ANR in <paquet> ».
detecter_plantage() {
  local p trouve
  p=$(paquet_connu) || return 0
  trouve=$(printf '%s\n' "$1" | tr -d '\r' | awk -v p="$p" '
    function apres(l, m,   i, c) {
      i = index(l, m); if (!i) return 0
      c = substr(l, i + length(m), 1)
      return c == "" || c == "," || c == " " || c == "(" || c == ":"
    }
    { if (n > 0) { n--; if (apres($0, "Process: " p)) { print f; print; n = 0 } }
      if (index($0, "FATAL EXCEPTION")) { f = $0; n = 3 }
      else if (apres($0, "ANR in " p)) print }' | head -n "$LIGNES_JOURNAL" | cut -c "1-$LARGEUR_JOURNAL" | assainir)
  [ -n "$trouve" ] || return 0
  printf '%s\n' "$trouve" > "$SORTIE/plantage.txt.tmp" && mv -f -- "$SORTIE/plantage.txt.tmp" "$SORTIE/plantage.txt"
}

liste_paquets() {
  local brut
  brut=$(outil "$DELAI_ADB" "$ADB" shell pm list packages -3 2>/dev/null) || return 1
  printf '%s\n' "$brut" | tr -d '\r' | sed -n 's/^package://p' | sort -u
}

# est_emulateur <pid> : vrai seulement pour un PID >= 2, vivant (pas zombie), dont argv[0] a pour nom de base
# emulator* ou qemu-system* ; met son groupe de processus dans GROUPE. Un PID mort, zombie, recyclé par un autre
# programme, 0, 1 ou mal formé n'est jamais pris pour l'émulateur.
GROUPE=""
est_emulateur() {
  local p="$1" stat etat parent groupe a0=""
  GROUPE=""
  [[ $p =~ ^[1-9][0-9]{0,6}$ ]] && [ "$p" -ge 2 ] || return 1
  stat=$(cat -- "/proc/$p/stat" 2>/dev/null) || return 1
  read -r etat parent groupe _ <<< "${stat##*) }"
  [ -n "$etat" ] && [ "$etat" != Z ] || return 1
  IFS= read -r -d '' a0 < "/proc/$p/cmdline" 2>/dev/null
  case "${a0##*/}" in emulator*|qemu-system*) GROUPE="$groupe"; return 0 ;; esac
  return 1
}

# effacer_pid <valeur lue> : retire emulateur.pid seulement s'il contient encore cette valeur (pas un PID réécrit entre-temps).
effacer_pid() {
  local v=""
  [ -f "$SORTIE/emulateur.pid" ] || return 0
  IFS= read -r v < "$SORTIE/emulateur.pid"
  [ "$v" = "$1" ] && rm -f -- "$SORTIE/emulateur.pid"
  return 0
}

# Processus de l'émulateur noté par `demarrer` (émulateur vivant), sinon rien.
pid_emulateur() {
  local p=""
  [ -f "$SORTIE/emulateur.pid" ] && IFS= read -r p < "$SORTIE/emulateur.pid"
  est_emulateur "$p" && printf '%s' "$p"
}

# signaler <signal> <pid> : au groupe seulement si le processus en est le chef (setsid ; champ 5 de /proc/<pid>/stat
# égal au PID), sinon au processus seul ; jamais sans avoir revérifié juste avant que c'est bien l'émulateur.
signaler() {
  est_emulateur "$2" || return 0
  if [ "$GROUPE" = "$2" ]; then kill "-$1" -- "-$2" 2>/dev/null; else kill "-$1" "$2" 2>/dev/null; fi
  return 0
}

# attendre_fin <pid> <essais> : vrai dès que l'émulateur a disparu (mort, zombie ou PID passé à autre chose).
attendre_fin() {
  local i=0
  while est_emulateur "$1"; do
    [ "$i" -lt "$2" ] || return 1
    sleep 1
    i=$((i + 1))
  done
  return 0
}

# --- Verbes ----------------------------------------------------------------

verbe_demarrer() {
  local avd="${PONT_AVD:-emulateur}" limite pid debut etat ancien reste detache presente
  [[ $avd =~ $MOTIF_NOM ]] || repondre 4 "Réglage PONT_AVD mal formé."
  reglage PONT_DEMARRAGE_S "${PONT_DEMARRAGE_S:-}" 300; limite=$REGLAGE
  debut=$SECONDS
  # Sous verrou : deux `demarrer` simultanés ne lancent qu'un émulateur, et le perdant n'écrase pas emulateur.pid.
  prendre_verrou demarrer
  ancien=$(pid_emulateur) && repondre 2 "Émulateur déjà démarré (processus $ancien) : arreter d'abord."
  # Détaché du pont (nouvelle session si setsid existe, insensible à SIGHUP sinon), sans le descripteur du verrou.
  if command -v setsid > /dev/null 2>&1; then detache=setsid; else detache=nohup; fi
  "$detache" "$EMULATEUR" -avd "$avd" -no-window -no-audio -no-boot-anim -no-snapshot-save -gpu swiftshader_indirect \
    > "$SORTIE/emulateur.log" 2>&1 9>&- &
  pid=$!
  printf '%s\n' "$pid" > "$SORTIE/emulateur.pid"
  # Verrou gardé jusqu'à ce que le processus soit reconnu comme l'émulateur (exec fait) : sinon un second `demarrer`
  # le prendrait pour un PID étranger et lancerait un second émulateur.
  presente=$((SECONDS + 5))
  until est_emulateur "$pid"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      effacer_pid "$pid"
      repondre 4 "L'émulateur s'est arrêté aussitôt lancé (voir emulateur.log)."
    fi
    if [ "$SECONDS" -ge "$presente" ]; then
      kill -TERM "$pid" 2>/dev/null
      effacer_pid "$pid"
      repondre 4 "L'émulateur ne s'est pas présenté en 5 s (voir emulateur.log)."
    fi
    sleep 0.1
  done
  liberer_verrou
  # Chaque appel à adb est borné par le temps restant moins les 2 s de grâce du KILL : jamais au-delà de PONT_DEMARRAGE_S.
  while :; do
    reste=$((limite - (SECONDS - debut) - 2))
    [ "$reste" -ge 1 ] || repondre 4 "L'émulateur n'a pas fini de démarrer en $limite s."
    [ "$reste" -le 10 ] || reste=10
    etat=$(outil "$reste" "$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n')
    [ "$etat" = 1 ] && repondre 0 "Émulateur démarré."
    est_emulateur "$pid" || repondre 4 "L'émulateur s'est arrêté avant la fin du démarrage (voir emulateur.log)."
    reste=$((limite - (SECONDS - debut)))
    [ "$reste" -gt 0 ] || repondre 4 "L'émulateur n'a pas fini de démarrer en $limite s."
    [ "$reste" -le 2 ] || reste=2
    sleep "$reste"
  done
}

verbe_installer() {
  local avant apres nouveaux p="" ancien
  [ -f "$APK" ] && [ ! -L "$APK" ] || repondre 4 "APK absent : l'enveloppe le dépose dans entree/app.apk."
  avant=$(liste_paquets) || repondre 4 "adb ne répond pas (liste des paquets)."
  outil $((DELAI_ADB * 4)) "$ADB" install -r "$APK" > /dev/null 2>&1 || repondre 4 "adb install a échoué."
  apres=$(liste_paquets) || repondre 4 "adb ne répond pas (liste des paquets)."
  nouveaux=$(printf '%s\n' "$apres" | grep -vxF -e "$avant" 2>/dev/null)
  [ -n "$avant" ] || nouveaux="$apres"
  if [ -n "$nouveaux" ] && [ "$(printf '%s\n' "$nouveaux" | wc -l)" -eq 1 ]; then
    p="$nouveaux"
  elif [ -n "$apres" ] && [ "$(printf '%s\n' "$apres" | wc -l)" -eq 1 ]; then
    p="$apres"
  else
    ancien=$(paquet_connu) && printf '%s\n' "$apres" | grep -qxF -e "$ancien" && p="$ancien"
  fi
  [[ $p =~ $MOTIF_PAQUET ]] || repondre 4 "Paquet de l'APK introuvable ou ambigu après l'installation."
  printf '%s\n' "$p" > "$SORTIE/.paquet" || repondre 4 "Écriture impossible dans la sortie."
  repondre 0 "APK installé : $p."
}

verbe_lancer() {
  local p sortie
  p=$(paquet_connu) || repondre 4 "Paquet inconnu : appeler installer d'abord."
  sortie=$(outil "$DELAI_ADB" "$ADB" shell monkey -p "$p" -c android.intent.category.LAUNCHER 1 2>&1) \
    || repondre 4 "adb a échoué (lancement)."
  case "$sortie" in *"No activities found"*|*"aborted"*) repondre 4 "L'application n'a pas d'activité de lancement." ;; esac
  repondre 0 "Application lancée : $p."
}

verbe_toucher() {
  outil "$DELAI_ADB" "$ADB" shell input tap "${ARGS[0]}" "${ARGS[1]}" > /dev/null 2>&1 || repondre 4 "adb a échoué (input tap)."
  repondre 0 "Touché en ${ARGS[0]} ${ARGS[1]}."
}

verbe_glisser() {
  outil "$DELAI_ADB" "$ADB" shell input swipe "${ARGS[0]}" "${ARGS[1]}" "${ARGS[2]}" "${ARGS[3]}" > /dev/null 2>&1 \
    || repondre 4 "adb a échoué (input swipe)."
  repondre 0 "Glissé de ${ARGS[0]} ${ARGS[1]} à ${ARGS[2]} ${ARGS[3]}."
}

verbe_texte() {
  outil "$DELAI_ADB" "$ADB" shell input text "${ARGS[0]// /%s}" > /dev/null 2>&1 || repondre 4 "adb a échoué (input text)."
  repondre 0 "Texte saisi (${#ARGS[0]} caractères)."
}

verbe_touche() {
  local code
  case "${ARGS[0]}" in retour) code=4 ;; accueil) code=3 ;; menu) code=82 ;; esac
  outil "$DELAI_ADB" "$ADB" shell input keyevent "$code" > /dev/null 2>&1 || repondre 4 "adb a échoué (input keyevent)."
  repondre 0 "Touche ${ARGS[0]}."
}

verbe_attendre() {
  local s=$((10#${ARGS[0]}))
  sleep "$s" || repondre 4 "Attente interrompue."
  repondre 0 "Attendu $s s."
}

verbe_capturer() {
  local nom="${ARGS[0]}" dossier="$SORTIE/captures" max octets_max cible tmp tailles t n=0 s=0 taille sig
  reglage PONT_CAPTURES "${PONT_CAPTURES:-}" 50; max=$REGLAGE
  reglage PONT_OCTETS "${PONT_OCTETS:-}" 104857600; octets_max=$REGLAGE
  cible="$dossier/$nom.png"
  tmp="$dossier/.$nom.$$.tmp"
  [ ! -L "$dossier" ] || repondre 4 "Dossier des captures invalide (lien symbolique)."
  mkdir -p -- "$dossier" || repondre 4 "Écriture impossible dans la sortie."
  [ -d "$dossier" ] && [ ! -L "$dossier" ] || repondre 4 "Dossier des captures invalide."
  prendre_verrou captures
  if [ -e "$cible" ] || [ -L "$cible" ]; then repondre 2 "Nom de capture déjà pris : $nom."; fi
  # Comptage : un échec ferme (code 4), il ne lève jamais les limites.
  tailles=$(find "$dossier" -maxdepth 1 -type f -name '*.png' -printf '%s\n') \
    || repondre 4 "Comptage des captures impossible : capture refusée."
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    [[ $t =~ ^[0-9]{1,15}$ ]] || repondre 4 "Comptage des captures illisible : capture refusée."
    n=$((n + 1)); s=$((s + 10#$t))
  done <<< "$tailles"
  [ "$n" -lt "$max" ] || repondre 3 "Limite de captures atteinte ($max)."
  octets_videos || repondre 4 "Comptage des vidéos impossible : capture refusée."
  s=$((s + OCTETS_VIDEOS))                       # captures et vidéos se partagent la limite d'octets
  [ "$s" -lt "$octets_max" ] || repondre 3 "Limite d'octets des captures atteinte ($octets_max)."
  rm -f -- "$tmp"
  if ! outil "$DELAI_ADB" "$ADB" exec-out screencap -p > "$tmp" 2>/dev/null; then
    rm -f -- "$tmp"; repondre 4 "adb a échoué (capture)."
  fi
  sig=$(od -An -tx1 -N8 -- "$tmp" 2>/dev/null | tr -d ' \n')
  if [ "$sig" != 89504e470d0a1a0a ]; then rm -f -- "$tmp"; repondre 4 "La capture n'est pas une image PNG."; fi
  taille=$(wc -c < "$tmp")
  if [ $((s + taille)) -gt "$octets_max" ]; then rm -f -- "$tmp"; repondre 3 "Limite d'octets des captures atteinte ($octets_max)."; fi
  if ! mv -n -- "$tmp" "$cible" || [ -e "$tmp" ]; then rm -f -- "$tmp"; repondre 2 "Nom de capture déjà pris : $nom."; fi
  repondre 0 "captures/$nom.png ($taille octets)."
}

# --- Médias : octets, sauvegarde du journal, film ---------------------------

# octets_videos / octets_captures : OCTETS_VIDEOS (videos/*.mp4 et videos/*-img/*.png) ou OCTETS_CAPTURES (captures/*.png),
# fichiers ordinaires seulement, sans suivre de lien ; faux si le comptage échoue (l'appelant ferme alors la limite).
octets_de() {   # octets_de <dossier> <profondeur> : met la somme dans OCTETS
  local tailles t
  OCTETS=0
  [ -e "$1" ] || return 0
  [ -d "$1" ] && [ ! -L "$1" ] || return 1
  tailles=$(find "$1" -maxdepth "$2" -type f \( -name '*.png' -o -name '*.mp4' \) -printf '%s\n') || return 1
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    [[ $t =~ ^[0-9]{1,15}$ ]] || return 1
    OCTETS=$((OCTETS + 10#$t))
  done <<< "$tailles"
  return 0
}
octets_videos() { octets_de "$SORTIE/videos" 2 && OCTETS_VIDEOS=$OCTETS; }
octets_captures() { octets_de "$SORTIE/captures" 1 && OCTETS_CAPTURES=$OCTETS; }

# Sauvegarde du journal : les lignes rendues par `journal` (déjà bornées et assainies) sont AJOUTÉES à logcat.txt, précédées
# d'une ligne « # journal <filtre|-> <heure UTC> », jusqu'au plafond PONT_LOGCAT_OCTETS (au-delà, plus rien n'est ajouté ;
# la réponse JSON reste complète). Jamais au travers d'un lien ni dans autre chose qu'un fichier ordinaire : créé en
# noclobber (O_EXCL) s'il manque, sinon revérifié juste avant l'ajout.
sauver_journal() {   # sauver_journal <filtre> <lignes> <plafond>
  local f="$SORTIE/logcat.txt" taille reste bloc
  if [ ! -e "$f" ] && [ ! -L "$f" ]; then ( set -C; : > "$f" ) 2>/dev/null || return 0; fi
  [ -f "$f" ] && [ ! -L "$f" ] || return 0
  taille=$(stat -c %s -- "$f" 2>/dev/null)
  [[ $taille =~ ^[0-9]{1,15}$ ]] || return 0
  reste=$(( $3 - taille ))
  [ "$reste" -gt 0 ] || return 0
  bloc=$(printf '# journal %s %s\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; [ -z "$2" ] || printf '%s\n' "$2")
  [ ! -L "$f" ] || return 0
  printf '%s\n' "$bloc" | head -c "$reste" >> "$f" 2>/dev/null
  return 0
}

# film_vivant <pid> : le processus d'enregistrement lancé par `filmer` (timeout ... adb shell screenrecord) vit encore.
# Reconnu par ses arguments EXACTS (jamais une sous-chaîne de la ligne de commande) : argv[0] de nom de base timeout ou adb,
# et un argument égal à « screenrecord ». Un PID recyclé par un autre programme n'est jamais pris pour le film.
film_vivant() {
  local a=() x vu=0
  [[ $1 =~ ^[1-9][0-9]{0,9}$ ]] || return 1
  [ -r "/proc/$1/cmdline" ] || return 1
  mapfile -d '' -t a < "/proc/$1/cmdline" 2>/dev/null || return 1
  [ "${#a[@]}" -gt 0 ] || return 1
  case "${a[0]##*/}" in timeout|adb) ;; *) return 1 ;; esac
  for x in "${a[@]}"; do [ "$x" = screenrecord ] && vu=1; done
  [ "$vu" = 1 ]
}

reglages_film() {   # réglages des vidéos, lus dans le shell principal (un refus écrit sa ligne JSON)
  reglage PONT_OCTETS "${PONT_OCTETS:-}" 104857600; FILM_OCTETS_MAX=$REGLAGE
  reglage PONT_VIDEOS "${PONT_VIDEOS:-}" 5; FILM_VIDEOS_MAX=$REGLAGE
  reglage PONT_VIDEO_OCTETS "${PONT_VIDEO_OCTETS:-}" 62914560; FILM_VIDEO_OCTETS=$REGLAGE
  reglage PONT_FILM_PAS "${PONT_FILM_PAS:-}" 2; FILM_PAS=$REGLAGE
  [ "$FILM_PAS" -ge 1 ] || FILM_PAS=1
}

dossier_videos() {   # crée SORTIE/videos ; jamais un lien
  local d="$SORTIE/videos"
  [ ! -L "$d" ] || repondre 4 "Dossier des vidéos invalide (lien symbolique)."
  mkdir -p -- "$d" || repondre 4 "Écriture impossible dans la sortie."
  [ -d "$d" ] && [ ! -L "$d" ] || repondre 4 "Dossier des vidéos invalide."
}

verbe_filmer() {
  local nom="${ARGS[0]}" duree="${ARGS[1]:-30}" d="$SORTIE/videos" n pid detache fin statut
  duree=$((10#$duree))
  reglages_film
  dossier_videos
  # Attente courte du verrou : un finfilm en cours (jusqu'à plusieurs minutes) le tient ; filmer renonce vite (code 4).
  prendre_verrou film 5
  if [ -e "$SORTIE/.film" ] || [ -L "$SORTIE/.film" ] || [ -e "$SORTIE/.film.fin" ] || [ -L "$SORTIE/.film.fin" ]; then
    repondre 2 "Un film est déjà en cours (ou pas encore fini) : finfilm d'abord."
  fi
  if [ -e "$d/$nom.mp4" ] || [ -L "$d/$nom.mp4" ] || [ -e "$d/$nom-img" ] || [ -L "$d/$nom-img" ]; then
    repondre 2 "Nom de vidéo déjà pris : $nom."
  fi
  n=$(find "$d" -maxdepth 1 -type f -name '*.mp4' -printf 'x\n' | wc -l) || repondre 4 "Comptage des vidéos impossible."
  [ "$n" -lt "$FILM_VIDEOS_MAX" ] || repondre 3 "Limite de vidéos atteinte ($FILM_VIDEOS_MAX)."
  octets_videos && octets_captures || repondre 4 "Comptage des médias impossible : film refusé."
  [ $((OCTETS_VIDEOS + OCTETS_CAPTURES)) -lt "$FILM_OCTETS_MAX" ] || repondre 3 "Limite d'octets des médias atteinte ($FILM_OCTETS_MAX)."
  # Détaché (nouvelle session si setsid existe), sans le verrou ni les sorties du pont ; borné côté appareil (--time-limit)
  # et côté conteneur (timeout, 30 s de marge). Le nom et la durée sont validés par leurs motifs.
  if command -v setsid > /dev/null 2>&1; then detache=setsid; else detache=nohup; fi
  "$detache" timeout -k 2 "$((duree + 30))" "$ADB" shell screenrecord --size 360x720 --bit-rate 1500000 \
    --time-limit "$duree" "/data/local/tmp/$nom.mp4" > /dev/null 2>&1 9>&- &
  pid=$!
  # Une seconde pour constater que l'enregistrement tient (appareil absent, screenrecord en échec : il meurt aussitôt) ;
  # attendue en entier : juste après le fork, /proc/<pid>/cmdline est encore celle du pont. S'il ne vit plus, son code de
  # sortie (c'est notre enfant : `wait`) départage un film court déjà fini proprement (0 : un film, finfilm le rapatriera)
  # d'un échec (autre code : 4).
  horloge_us; fin=$((HORLOGE + 1000000))
  while horloge_us; [ "$HORLOGE" -lt "$fin" ]; do sleep 0.1; done
  if ! film_vivant "$pid"; then
    wait "$pid" 2>/dev/null; statut=$?
    [ "$statut" = 0 ] || repondre 4 "L'enregistrement n'a pas démarré (adb screenrecord en échec, code $statut)."
  fi
  printf '%s %s %s %s\n' "$nom" "$pid" "$(date +%s)" "$duree" > "$SORTIE/.film.tmp" \
    && mv -f -- "$SORTIE/.film.tmp" "$SORTIE/.film" \
    || { kill -TERM "$pid" 2>/dev/null; repondre 4 "Écriture impossible dans la sortie."; }
  repondre 0 "Film $nom lancé ($duree s au plus) : finfilm pour l'arrêter et le rapatrier."
}

# film_fini <code> <détail> : résultat de finir_film ; la trace .film.fin n'est retirée qu'ici, travail terminé.
film_fini() { FILM_CODE="$1"; FILM_DETAIL="$2"; rm -f -- "$SORTIE/.film.fin"; }

# finir_film : arrête le film noté dans .film, rapatrie et vérifie le mp4, en tire les images. Ne termine jamais le pont :
# met FILM_CODE (0 fait, 2 aucun film, 3 limite, 4 échec) et FILM_DETAIL. Appelé verrou « film » pris, réglages lus.
# La trace .film devient .film.fin le temps du travail et n'est retirée qu'une fois ce travail fini (réussi ou non) : un
# finfilm interrompu (pont tué) la laisse ; le suivant (finfilm, ou arreter) reprend ce film là où il en était.
finir_film() {
  local f="$SORTIE/.film" ff="$SORTIE/.film.fin" d="$SORTIE/videos" ligne="" nom="" pid="" debut="" demandee=""
  local fin tmp video img taille duree pas n=0 note=""
  FILM_CODE=2; FILM_DETAIL="Aucun film en cours."
  if [ ! -e "$ff" ] && [ ! -L "$ff" ]; then
    [ -e "$f" ] || [ -L "$f" ] || return 0
    mv -f -- "$f" "$ff" 2>/dev/null || { FILM_CODE=4; FILM_DETAIL="État du film inaccessible."; return 0; }
  fi
  [ -f "$ff" ] && [ ! -L "$ff" ] && IFS= read -r ligne < "$ff"
  read -r nom pid debut demandee _ <<< "$ligne"
  if ! [[ $nom =~ $MOTIF_NOM ]] || ! [[ $pid =~ ^[1-9][0-9]{0,9}$ ]] || ! [[ $debut =~ ^[0-9]{1,12}$ ]] \
     || ! [[ $demandee =~ $MOTIF_SECONDES_FILM ]]; then
    film_fini 4 "État du film illisible : film abandonné."; return 0
  fi
  # SIGINT au screenrecord de l'appareil : il finalise le mp4. Puis attente bornée de la fin du processus local.
  outil "$DELAI_ADB" "$ADB" shell pkill -2 screenrecord > /dev/null 2>&1
  fin=$((SECONDS + 10))
  while film_vivant "$pid" && [ "$SECONDS" -lt "$fin" ]; do sleep 0.2; done
  film_vivant "$pid" && kill -TERM "$pid" 2>/dev/null
  # Durée : le temps écoulé depuis filmer, jamais plus que la durée demandée (--time-limit l'arrête là côté appareil).
  duree=$(( $(date +%s) - 10#$debut )); [ "$duree" -ge 0 ] || duree=0
  [ "$duree" -le "$((10#$demandee))" ] || duree=$((10#$demandee))
  [ -L "$d" ] || mkdir -p -- "$d" 2>/dev/null
  if [ -L "$d" ] || [ ! -d "$d" ]; then film_fini 4 "Dossier des vidéos invalide."; return 0; fi
  video="$d/$nom.mp4"; tmp="$d/.$nom.$$.tmp"
  if [ -f "$video" ] && [ ! -L "$video" ]; then
    taille=$(wc -c < "$video")                   # reprise : la vidéo avait déjà été rapatriée et vérifiée
  else
    rm -f -- "$tmp"
    if ! outil $((DELAI_ADB * 2)) "$ADB" pull "/data/local/tmp/$nom.mp4" "$tmp" > /dev/null 2>&1 || [ -L "$tmp" ] || [ ! -f "$tmp" ]; then
      rm -f -- "$tmp"; film_fini 4 "adb a échoué (rapatriement de la vidéo $nom)."; return 0
    fi
    outil "$DELAI_ADB" "$ADB" shell rm -f "/data/local/tmp/$nom.mp4" > /dev/null 2>&1
    if [ "$(od -An -tx1 -j4 -N4 -- "$tmp" 2>/dev/null | tr -d ' \n')" != 66747970 ]; then     # « ftyp »
      rm -f -- "$tmp"; film_fini 4 "Le fichier rapatrié n'est pas une vidéo MP4 : effacé."; return 0
    fi
    taille=$(wc -c < "$tmp")
    if ! octets_videos || ! octets_captures; then
      rm -f -- "$tmp"; film_fini 4 "Comptage des médias impossible : vidéo effacée."; return 0
    fi
    if [ "$taille" -gt "$FILM_VIDEO_OCTETS" ] || [ $((OCTETS_VIDEOS + OCTETS_CAPTURES + taille)) -gt "$FILM_OCTETS_MAX" ]; then
      rm -f -- "$tmp"
      film_fini 3 "Limite d'octets atteinte : vidéo de $taille octets effacée (au plus $FILM_VIDEO_OCTETS par vidéo, $FILM_OCTETS_MAX en tout)."
      return 0
    fi
    if ! mv -n -- "$tmp" "$video" || [ -e "$tmp" ]; then rm -f -- "$tmp"; film_fini 2 "Nom de vidéo déjà pris : $nom."; return 0; fi
  fi
  # Images sur TOUT le film : une toutes les max(FILM_PAS, durée/30) secondes, 30 au plus, 320 px de large, dans un dossier
  # neuf (jamais un dossier existant ; à la reprise, celui déjà commencé est gardé tel quel).
  pas=$(( (duree + 29) / 30 )); [ "$pas" -ge "$FILM_PAS" ] || pas=$FILM_PAS
  img="$d/$nom-img"
  if mkdir -- "$img" 2>/dev/null; then
    outil 120 "$FFMPEG" -nostdin -loglevel error -i "$video" -vf "fps=1/$pas,scale=320:-2" -frames:v 30 \
      "$img/$nom-%03d.png" > /dev/null 2>&1
  fi
  if [ -d "$img" ] && [ ! -L "$img" ]; then
    n=$(find "$img" -maxdepth 1 -type f -name "$nom-[0-9][0-9][0-9].png" -printf 'x\n' 2>/dev/null | wc -l)
    if ! octets_videos || ! octets_captures || [ $((OCTETS_VIDEOS + OCTETS_CAPTURES)) -gt "$FILM_OCTETS_MAX" ]; then
      rm -rf -- "$img"; n=0; note=" ; images effacées (limite d'octets)"
    fi
  fi
  film_fini 0 "videos/$nom.mp4 ($taille octets, $duree s, $n images)$note."
}

verbe_finfilm() {
  reglages_film
  prendre_verrou film
  finir_film
  repondre "$FILM_CODE" "$FILM_DETAIL"
}

verbe_journal() {
  local brut lignes plafond
  reglage PONT_LOGCAT_OCTETS "${PONT_LOGCAT_OCTETS:-}" 2097152; plafond=$REGLAGE
  brut=$(outil "$DELAI_ADB" "$ADB" logcat -d 2>/dev/null) || repondre 4 "adb a échoué (logcat)."
  detecter_plantage "$brut"
  if [ ${#ARGS[@]} -eq 1 ]; then
    lignes=$(printf '%s\n' "$brut" | tr -d '\r' | { grep -F -e "${ARGS[0]}" || true; } | tail -n "$LIGNES_JOURNAL" \
             | cut -c "1-$LARGEUR_JOURNAL" | assainir)
  else
    lignes=$(printf '%s\n' "$brut" | tr -d '\r' | tail -n "$LIGNES_JOURNAL" | cut -c "1-$LARGEUR_JOURNAL" | assainir)
  fi
  # Les mêmes lignes, gardées dans logcat.txt (rapatrié), sous verrou : deux journal simultanés respectent le plafond.
  prendre_verrou journal
  sauver_journal "${ARGS[0]:--}" "$lignes" "$plafond"
  liberer_verrou
  repondre 0 "$lignes"
}

# Arrêt : adb emu kill, puis, si le processus noté par demarrer vit encore, TERM puis KILL.
verbe_arreter() {
  local brut adb_ok=1 pid="" detail="Émulateur arrêté." film=""
  # Un film resté en cours est fini AVANT d'arrêter l'émulateur (mp4 finalisé et rapatrié), jamais perdu en silence.
  # Son résultat compte : une vidéo effacée pour une limite (3) ou en échec (4) rend ce code, après l'arrêt de l'émulateur
  # (le lanceur note alors la limite) ; jamais un « ok » silencieux.
  local film_code=0
  if [ -e "$SORTIE/.film" ] || [ -L "$SORTIE/.film" ] || [ -e "$SORTIE/.film.fin" ] || [ -L "$SORTIE/.film.fin" ]; then
    reglages_film
    prendre_verrou film
    finir_film
    liberer_verrou
    film=" Film : $FILM_DETAIL"
    case "$FILM_CODE" in 3|4) film_code=$FILM_CODE ;; esac
  fi
  # PID lu AVANT d'agir : seul ce PID est arrêté, et emulateur.pid n'est retiré que s'il le contient encore.
  [ -f "$SORTIE/emulateur.pid" ] && { IFS= read -r pid < "$SORTIE/emulateur.pid" || true; }
  brut=$(outil "$DELAI_ADB" "$ADB" logcat -d 2>/dev/null) && detecter_plantage "$brut"
  outil "$DELAI_ADB" "$ADB" emu kill > /dev/null 2>&1 || adb_ok=0
  if est_emulateur "$pid"; then
    if ! attendre_fin "$pid" 10; then
      signaler TERM "$pid"
      attendre_fin "$pid" 5 || { signaler KILL "$pid"; attendre_fin "$pid" 5; }
      detail="Émulateur arrêté par signal."
    fi
    est_emulateur "$pid" && repondre 4 "L'émulateur (processus $pid) ne s'arrête pas."
  elif [ "$adb_ok" = 0 ]; then
    effacer_pid "$pid"                  # PID mort, zombie, étranger ou mal formé : effacé, jamais signalé
    repondre 4 "adb a échoué (arrêt de l'émulateur)."
  fi
  effacer_pid "$pid"
  if [ -f "$SORTIE/plantage.txt" ]; then detail="$detail Plantage relevé (plantage.txt)."; fi
  repondre "$film_code" "$detail$film"
}

# --- Validation puis exécution -----------------------------------------------

verifier_environnement
motifs_du_verbe "$VERBE" || repondre 2 "Verbe inconnu : liste fermée ($LISTE_VERBES)."
VERBE_SUR="$VERBE"
attendus=${#MOTIFS[@]}
if [ ${#ARGS[@]} -lt $((attendus - FACULTATIFS)) ] || [ ${#ARGS[@]} -gt "$attendus" ]; then
  repondre 2 "Nombre d'arguments refusé pour $VERBE."
fi
for i in "${!ARGS[@]}"; do
  [[ ${ARGS[$i]} =~ ${MOTIFS[$i]} ]] || repondre 2 "Argument $((i + 1)) refusé pour $VERBE (forme non permise)."
  if [ "${MOTIFS[$i]}" = "$MOTIF_NOM" ] && [[ ${ARGS[$i]} =~ $MOTIF_NOM_RESERVE ]]; then
    repondre 2 "Argument $((i + 1)) refusé pour $VERBE (nom réservé sous Windows)."
  fi
done
reglage PONT_DELAI_ADB_S "${PONT_DELAI_ADB_S:-}" 30; DELAI_ADB=$REGLAGE
command -v timeout > /dev/null 2>&1 || repondre 4 "timeout absent : le pont refuse d'appeler adb sans délai."
mkdir -p -- "$SORTIE" 2>/dev/null || repondre 4 "Dossier de sortie inaccessible."
activite                                       # début du verbe
ACTIVITE_ACTIVE=1                              # et fin : repondre() retouche

case "$VERBE" in
  demarrer) verbe_demarrer ;;
  installer) verbe_installer ;;
  lancer) verbe_lancer ;;
  toucher) verbe_toucher ;;
  glisser) verbe_glisser ;;
  texte) verbe_texte ;;
  touche) verbe_touche ;;
  attendre) verbe_attendre ;;
  capturer) verbe_capturer ;;
  journal) verbe_journal ;;
  arreter) verbe_arreter ;;
  filmer) verbe_filmer ;;
  finfilm) verbe_finfilm ;;
esac
repondre 4 "Verbe sans exécution."
