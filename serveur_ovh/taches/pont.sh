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
#   PONT_SORTIE (/sortie ; absolu, sans . ni ..), PONT_CAPTURES (50), PONT_OCTETS (104857600 = 100 Mo de captures cumulées),
#   PONT_AVD (emulateur ; motif MOTIF_NOM, donc en minuscules : la tâche 4 nomme l'AVD « emul »), PONT_DEMARRAGE_S (300),
#   PONT_DELAI_ADB_S (30 : délai de chaque appel à adb, `installer` x4 ; attente d'un verrou = 3 x délai + 10 s),
#   PONT_PAQUET (facultatif : sinon le paquet est relevé par `installer`) ;
#   PONT_ADB / PONT_EMULATEUR : « adb » / « emulator » ou un chemin absolu (tests).
# Écrit seulement sous PONT_SORTIE : pont.log, captures/<nom>.png, plantage.txt, .paquet, emulateur.log, emulateur.pid,
# .verrou-captures, .verrou-demarrer (ou leurs dossiers .d sans flock).
# Exige `timeout` (coreutils) : sans lui, refus (code 4) plutôt qu'un adb sans borne. Aucun outil ne reçoit le descripteur 9
# du verrou (9>&-) : un serveur adb resté en vie ne doit pas garder le verrou.
# emulateur.pid ne désigne l'émulateur que si /proc/<pid> le confirme (ni zombie, ni « emulator »/« qemu » absent de la ligne
# de commande) : un PID mort, zombie ou recyclé n'est jamais signalé.
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
# verbe -> motifs de ses arguments, dans l'ordre ; FACULTATIFS = nombre de derniers arguments facultatifs.
#   demarrer, installer, lancer, arreter : aucun argument (installer prend toujours entree/app.apk, chemin fixe)
motifs_du_verbe() {
  MOTIFS=(); FACULTATIFS=0
  case "$1" in
    demarrer|installer|lancer|arreter) ;;
    toucher)  MOTIFS=("$MOTIF_ENTIER" "$MOTIF_ENTIER") ;;
    glisser)  MOTIFS=("$MOTIF_ENTIER" "$MOTIF_ENTIER" "$MOTIF_ENTIER" "$MOTIF_ENTIER") ;;
    texte)    MOTIFS=("$MOTIF_TEXTE") ;;
    touche)   MOTIFS=("$MOTIF_TOUCHE") ;;
    attendre) MOTIFS=("$MOTIF_DUREE") ;;
    capturer) MOTIFS=("$MOTIF_NOM") ;;
    journal)  MOTIFS=("$MOTIF_FILTRE"); FACULTATIFS=1 ;;
    *) return 1 ;;
  esac
}
# Internes (hors table de l'appelant) : nom de paquet relevé sur l'appareil, réglages de l'environnement.
MOTIF_PAQUET='^[A-Za-z][A-Za-z0-9_]{0,60}(\.[A-Za-z][A-Za-z0-9_]{0,60}){1,10}$'
MOTIF_REGLAGE='^[0-9]{1,12}$'
MOTIF_POINTS='(^|/)\.\.?(/|$)'                           # composant . ou .. dans un chemin
# ==============================================================================================================

LISTE_VERBES="demarrer, installer, lancer, toucher, glisser, texte, touche, attendre, capturer, journal, arreter"
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
repondre() {
  local code="$1" detail="$2" ok=false
  [ "$code" -eq 0 ] && ok=true
  printf '{"ok": %s, "verbe": "%s", "detail": "%s"}\n' "$ok" "$VERBE_SUR" "$(echapper_json "$detail")"
  journaliser
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
  for nom in adb emulator; do
    if [ "$nom" = adb ]; then valeur="${PONT_ADB-adb}"; else valeur="${PONT_EMULATEUR-emulator}"; fi
    [ "$valeur" = "$nom" ] && continue
    [ "${valeur:0:1}" = / ] && [[ ! $valeur =~ $MOTIF_POINTS ]] && continue
    repondre 4 "Outil $nom mal désigné : « $nom » ou un chemin absolu."
  done
  SORTIE="$s"
  SORTIE_VALIDE=1
  APK="$SORTIE/../entree/app.apk"
  ADB="${PONT_ADB-adb}"
  EMULATEUR="${PONT_EMULATEUR-emulator}"
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
prendre_verrou() {   # prendre_verrou <nom>
  local f="$SORTIE/.verrou-$1" attente=$((3 * DELAI_ADB + 10)) debut=$SECONDS p q
  if command -v flock > /dev/null 2>&1; then
    exec 9>> "$f" || repondre 4 "Verrou $1 impossible."
    VERROU_FD=1
    flock -w "$attente" 9 || repondre 4 "Verrou $1 occupé depuis $attente s."
    return 0
  fi
  until mkdir -- "$f.d" 2>/dev/null; do
    p=""
    IFS= read -r p < "$f.d/pid" 2>/dev/null
    if [[ $p =~ ^[0-9]{1,10}$ ]] && ! kill -0 "$p" 2>/dev/null; then
      # Détenteur mort : le dossier est mis de côté sous un nom unique, puis supprimé si c'est bien le même détenteur.
      if mv -- "$f.d" "$f.d.perime.$$" 2>/dev/null; then
        q=""
        IFS= read -r q < "$f.d.perime.$$/pid" 2>/dev/null
        if [ "$q" = "$p" ]; then rm -rf -- "$f.d.perime.$$"; else mv -- "$f.d.perime.$$" "$f.d" 2>/dev/null; fi
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

# est_emulateur <pid> : vrai seulement pour un processus vivant (pas zombie) dont la ligne de commande contient
# « emulator » ou « qemu ». Un PID mort, zombie ou recyclé par un autre programme n'est jamais pris pour l'émulateur.
est_emulateur() {
  local p="$1" stat etat cmd
  [[ $p =~ ^[0-9]{1,10}$ ]] || return 1
  stat=$(cat -- "/proc/$p/stat" 2>/dev/null) || return 1
  etat="${stat##*) }"
  etat="${etat%% *}"
  [ -n "$etat" ] && [ "$etat" != Z ] || return 1
  cmd=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || return 1
  case "$cmd" in *emulator*|*qemu*) return 0 ;; esac
  return 1
}

# Processus de l'émulateur noté par `demarrer` (émulateur vivant), sinon rien.
pid_emulateur() {
  local p=""
  [ -f "$SORTIE/emulateur.pid" ] && IFS= read -r p < "$SORTIE/emulateur.pid"
  est_emulateur "$p" && printf '%s' "$p"
}

# signaler <signal> <pid> : au groupe de processus (setsid en a fait le chef), sinon au processus ; jamais sans
# avoir revérifié juste avant que c'est bien l'émulateur.
signaler() {
  est_emulateur "$2" || return 0
  kill "-$1" -- "-$2" 2>/dev/null || kill "-$1" "$2" 2>/dev/null
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
  local avd="${PONT_AVD:-emulateur}" limite pid debut etat ancien reste detache
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

verbe_journal() {
  local brut lignes
  brut=$(outil "$DELAI_ADB" "$ADB" logcat -d 2>/dev/null) || repondre 4 "adb a échoué (logcat)."
  detecter_plantage "$brut"
  if [ ${#ARGS[@]} -eq 1 ]; then
    lignes=$(printf '%s\n' "$brut" | tr -d '\r' | { grep -F -e "${ARGS[0]}" || true; } | tail -n "$LIGNES_JOURNAL" \
             | cut -c "1-$LARGEUR_JOURNAL" | assainir)
  else
    lignes=$(printf '%s\n' "$brut" | tr -d '\r' | tail -n "$LIGNES_JOURNAL" | cut -c "1-$LARGEUR_JOURNAL" | assainir)
  fi
  repondre 0 "$lignes"
}

# Arrêt : adb emu kill, puis, si le processus noté par demarrer vit encore, TERM puis KILL.
verbe_arreter() {
  local brut adb_ok=1 pid detail="Émulateur arrêté."
  brut=$(outil "$DELAI_ADB" "$ADB" logcat -d 2>/dev/null) && detecter_plantage "$brut"
  outil "$DELAI_ADB" "$ADB" emu kill > /dev/null 2>&1 || adb_ok=0
  if pid=$(pid_emulateur); then
    if ! attendre_fin "$pid" 10; then
      signaler TERM "$pid"
      attendre_fin "$pid" 5 || { signaler KILL "$pid"; attendre_fin "$pid" 5; }
      detail="Émulateur arrêté par signal."
    fi
    est_emulateur "$pid" && repondre 4 "L'émulateur (processus $pid) ne s'arrête pas."
  elif [ "$adb_ok" = 0 ]; then
    rm -f -- "$SORTIE/emulateur.pid"     # PID mort, zombie ou étranger : effacé, jamais signalé
    repondre 4 "adb a échoué (arrêt de l'émulateur)."
  fi
  rm -f -- "$SORTIE/emulateur.pid"
  if [ -f "$SORTIE/plantage.txt" ]; then detail="$detail Plantage relevé (plantage.txt)."; fi
  repondre 0 "$detail"
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
done
reglage PONT_DELAI_ADB_S "${PONT_DELAI_ADB_S:-}" 30; DELAI_ADB=$REGLAGE
command -v timeout > /dev/null 2>&1 || repondre 4 "timeout absent : le pont refuse d'appeler adb sans délai."
mkdir -p -- "$SORTIE" 2>/dev/null || repondre 4 "Dossier de sortie inaccessible."

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
esac
repondre 4 "Verbe sans exécution."
