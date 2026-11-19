#!/usr/bin/env bash
# Pont d'actions de l'émulateur : SEULE porte d'entrée d'un agent ou d'une recette dans le conteneur `myiafactory/emulateur`
# (copié en /usr/local/bin/pont par l'image).
# Usage : pont <verbe> [arguments]
# Liste fermée de verbes ; chaque argument est validé par un motif AVANT tout usage ; aucun eval, aucun argument dans une
# commande composée ni dans un motif de fichiers (expansion des motifs coupée : set -f) ; les limites sont appliquées ici,
# pas par la bonne foi de l'appelant.
# Les arguments donnés à `adb shell` sont relus par le shell de l'appareil : c'est pourquoi les motifs n'admettent aucun
# caractère spécial du shell (ni ; $ ` ' " | & < > ( ) * ? \ ni retour à la ligne).
# Sortie standard : UNE ligne JSON {"ok": bool, "verbe": "...", "detail": "..."}.
# Codes de retour : 0 ok, 2 verbe ou argument refusé (nom de capture déjà pris compris), 3 limite atteinte, 4 outil en échec.
# Environnement (posé par l'enveloppe lancer_emulation.sh, jamais par l'appelant) : PONT_SORTIE (/sortie), PONT_CAPTURES (50),
# PONT_OCTETS (104857600 = 100 Mo de captures cumulées), PONT_AVD (emulateur), PONT_DEMARRAGE_S (300), PONT_PAQUET (facultatif :
# sinon le paquet est relevé par `installer`) ; PONT_ADB / PONT_EMULATEUR remplacent adb / emulator (tests).
# Écrit seulement sous PONT_SORTIE : pont.log, captures/<nom>.png, plantage.txt, .paquet, emulateur.log.
# Un appel = une ligne « verbe arguments durée » ajoutée à ${PONT_SORTIE}/pont.log (caractères hors liste remplacés par « ? »).
set -u
set -f
set -o pipefail
export LC_ALL=C
exec </dev/null

# ==============================================================================================================
# MOTIFS DU PONT : table unique, expressions régulières POSIX étendues ancrées.
# Miroir Python à garder IDENTIQUE : VERBES de outils/serveur_tache.py (décision R2) ; le test
# test_motifs_python_et_pont_s_accordent fait passer les mêmes exemples par les deux.
MOTIF_ENTIER='^[0-9]{1,4}$'                     # coordonnée : 0 à 9999
MOTIF_DUREE='^([0-9]{1,2}|1[01][0-9]|120)$'      # attendre : 0 à 120 secondes
MOTIF_NOM='^[a-z0-9_-]{1,40}$'                  # nom de capture
MOTIF_TEXTE='^[A-Za-z0-9 .,_-]{1,60}$'          # texte saisi (espaces transmis en %s à `input text`)
MOTIF_FILTRE='^[A-Za-z0-9._:-]{1,60}$'          # filtre du journal (texte littéral, pas une expression)
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
# Internes (hors table de l'appelant) : nom de paquet relevé sur l'appareil, réglages numériques de l'environnement.
MOTIF_PAQUET='^[A-Za-z][A-Za-z0-9_]{0,60}(\.[A-Za-z][A-Za-z0-9_]{0,60}){1,10}$'
MOTIF_REGLAGE='^[0-9]{1,12}$'
# ==============================================================================================================

LISTE_VERBES="demarrer, installer, lancer, toucher, glisser, texte, touche, attendre, capturer, journal, arreter"
LIGNES_JOURNAL=200
SORTIE="${PONT_SORTIE:-/sortie}"
SORTIE="${SORTIE%/}"
APK="$SORTIE/../entree/app.apk"
ADB="${PONT_ADB:-adb}"
EMULATEUR="${PONT_EMULATEUR:-emulator}"

# --- Utilitaires -----------------------------------------------------------

horloge_us() {
  local t="${EPOCHREALTIME:-}"
  t="${t//[.,]/}"
  if [[ $t =~ ^[0-9]+$ ]]; then printf '%s' "$((10#$t))"; else printf '%s' "$((SECONDS * 1000000))"; fi
}
DEBUT_US=$(horloge_us)

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

# Forme sûre d'un mot pour le journal et la réponse : tronqué, caractères hors liste remplacés.
mot_sur() {
  local m="${1:0:80}"
  [ -n "$m" ] || { printf '""'; return; }
  printf '%s' "${m//[^A-Za-z0-9 .,_:-]/?}"
}

VERBE="${1-}"
[ $# -gt 0 ] && shift
ARGS=("$@")
VERBE_SUR="${VERBE:0:40}"
VERBE_SUR="${VERBE_SUR//[^a-z0-9_-]/?}"

journaliser() {
  local ligne a fin
  ligne=$(mot_sur "$VERBE_SUR")
  for a in "${ARGS[@]}"; do ligne+=" $(mot_sur "$a")"; done
  fin=$(horloge_us)
  mkdir -p -- "$SORTIE" 2>/dev/null
  printf '%s %sms\n' "$ligne" "$(( (fin - DEBUT_US) / 1000 ))" >> "$SORTIE/pont.log" 2>/dev/null
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
      else if (apres($0, "ANR in " p)) print }' | head -n "$LIGNES_JOURNAL" | assainir)
  [ -n "$trouve" ] || return 0
  printf '%s\n' "$trouve" > "$SORTIE/plantage.txt.tmp" && mv -f -- "$SORTIE/plantage.txt.tmp" "$SORTIE/plantage.txt"
}

liste_paquets() {
  local brut
  brut=$("$ADB" shell pm list packages -3 2>/dev/null) || return 1
  printf '%s\n' "$brut" | tr -d '\r' | sed -n 's/^package://p' | sort -u
}

# --- Verbes ----------------------------------------------------------------

verbe_demarrer() {
  local avd="${PONT_AVD:-emulateur}" limite pid debut etat
  [[ $avd =~ $MOTIF_NOM ]] || repondre 4 "Réglage PONT_AVD mal formé."
  reglage PONT_DEMARRAGE_S "${PONT_DEMARRAGE_S:-}" 300; limite=$REGLAGE
  "$EMULATEUR" -avd "$avd" -no-window -no-audio -no-boot-anim -no-snapshot-save -gpu swiftshader_indirect \
    > "$SORTIE/emulateur.log" 2>&1 &
  pid=$!
  debut=$SECONDS
  while :; do
    etat=$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n')
    [ "$etat" = 1 ] && repondre 0 "Émulateur démarré."
    kill -0 "$pid" 2>/dev/null || repondre 4 "L'émulateur s'est arrêté avant la fin du démarrage (voir emulateur.log)."
    [ $((SECONDS - debut)) -lt "$limite" ] || repondre 4 "L'émulateur n'a pas fini de démarrer en $limite s."
    sleep 2
  done
}

verbe_installer() {
  local avant apres nouveaux p="" ancien
  [ -f "$APK" ] && [ ! -L "$APK" ] || repondre 4 "APK absent : l'enveloppe le dépose dans entree/app.apk."
  avant=$(liste_paquets) || repondre 4 "adb ne répond pas (liste des paquets)."
  "$ADB" install -r "$APK" > /dev/null 2>&1 || repondre 4 "adb install a échoué."
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
  sortie=$("$ADB" shell monkey -p "$p" -c android.intent.category.LAUNCHER 1 2>&1) || repondre 4 "adb a échoué (lancement)."
  case "$sortie" in *"No activities found"*|*"aborted"*) repondre 4 "L'application n'a pas d'activité de lancement." ;; esac
  repondre 0 "Application lancée : $p."
}

verbe_toucher() {
  "$ADB" shell input tap "${ARGS[0]}" "${ARGS[1]}" > /dev/null 2>&1 || repondre 4 "adb a échoué (input tap)."
  repondre 0 "Touché en ${ARGS[0]} ${ARGS[1]}."
}

verbe_glisser() {
  "$ADB" shell input swipe "${ARGS[0]}" "${ARGS[1]}" "${ARGS[2]}" "${ARGS[3]}" > /dev/null 2>&1 \
    || repondre 4 "adb a échoué (input swipe)."
  repondre 0 "Glissé de ${ARGS[0]} ${ARGS[1]} à ${ARGS[2]} ${ARGS[3]}."
}

verbe_texte() {
  "$ADB" shell input text "${ARGS[0]// /%s}" > /dev/null 2>&1 || repondre 4 "adb a échoué (input text)."
  repondre 0 "Texte saisi (${#ARGS[0]} caractères)."
}

verbe_touche() {
  local code
  case "${ARGS[0]}" in retour) code=4 ;; accueil) code=3 ;; menu) code=82 ;; esac
  "$ADB" shell input keyevent "$code" > /dev/null 2>&1 || repondre 4 "adb a échoué (input keyevent)."
  repondre 0 "Touche ${ARGS[0]}."
}

verbe_attendre() {
  local s=$((10#${ARGS[0]}))
  sleep "$s" || repondre 4 "Attente interrompue."
  repondre 0 "Attendu $s s."
}

verbe_capturer() {
  local nom="${ARGS[0]}" dossier="$SORTIE/captures" max octets_max cible tmp n s taille sig
  reglage PONT_CAPTURES "${PONT_CAPTURES:-}" 50; max=$REGLAGE
  reglage PONT_OCTETS "${PONT_OCTETS:-}" 104857600; octets_max=$REGLAGE
  cible="$dossier/$nom.png"
  tmp="$dossier/.$nom.png.tmp"
  [ ! -L "$dossier" ] || repondre 4 "Dossier des captures invalide."
  mkdir -p -- "$dossier" || repondre 4 "Écriture impossible dans la sortie."
  if [ -e "$cible" ] || [ -L "$cible" ]; then repondre 2 "Nom de capture déjà pris : $nom."; fi
  read -r n s < <(find "$dossier" -maxdepth 1 -type f -name '*.png' -printf '%s\n' \
                  | awk '{ n++; s += $1 } END { printf "%d %d\n", n, s }')
  [ "${n:-0}" -lt "$max" ] || repondre 3 "Limite de captures atteinte ($max)."
  [ "${s:-0}" -lt "$octets_max" ] || repondre 3 "Limite d'octets des captures atteinte ($octets_max)."
  rm -f -- "$tmp"
  if ! "$ADB" exec-out screencap -p > "$tmp" 2>/dev/null; then rm -f -- "$tmp"; repondre 4 "adb a échoué (capture)."; fi
  sig=$(od -An -tx1 -N8 -- "$tmp" 2>/dev/null | tr -d ' \n')
  if [ "$sig" != 89504e470d0a1a0a ]; then rm -f -- "$tmp"; repondre 4 "La capture n'est pas une image PNG."; fi
  taille=$(wc -c < "$tmp")
  if [ $(( ${s:-0} + taille )) -gt "$octets_max" ]; then rm -f -- "$tmp"; repondre 3 "Limite d'octets des captures atteinte ($octets_max)."; fi
  mv -n -- "$tmp" "$cible"
  if [ -e "$tmp" ]; then rm -f -- "$tmp"; repondre 2 "Nom de capture déjà pris : $nom."; fi
  repondre 0 "captures/$nom.png ($taille octets)."
}

verbe_journal() {
  local brut lignes
  brut=$("$ADB" logcat -d 2>/dev/null) || repondre 4 "adb a échoué (logcat)."
  detecter_plantage "$brut"
  if [ ${#ARGS[@]} -eq 1 ]; then
    lignes=$(printf '%s\n' "$brut" | tr -d '\r' | { grep -F -e "${ARGS[0]}" || true; } | tail -n "$LIGNES_JOURNAL" | assainir)
  else
    lignes=$(printf '%s\n' "$brut" | tr -d '\r' | tail -n "$LIGNES_JOURNAL" | assainir)
  fi
  repondre 0 "$lignes"
}

verbe_arreter() {
  local brut
  brut=$("$ADB" logcat -d 2>/dev/null) && detecter_plantage "$brut"
  "$ADB" emu kill > /dev/null 2>&1 || repondre 4 "adb a échoué (arrêt de l'émulateur)."
  if [ -f "$SORTIE/plantage.txt" ]; then repondre 0 "Émulateur arrêté ; plantage relevé (plantage.txt)."; fi
  repondre 0 "Émulateur arrêté."
}

# --- Validation puis exécution -----------------------------------------------

motifs_du_verbe "$VERBE" || repondre 2 "Verbe inconnu : liste fermée ($LISTE_VERBES)."
VERBE_SUR="$VERBE"
attendus=${#MOTIFS[@]}
if [ ${#ARGS[@]} -lt $((attendus - FACULTATIFS)) ] || [ ${#ARGS[@]} -gt "$attendus" ]; then
  repondre 2 "Nombre d'arguments refusé pour $VERBE."
fi
for i in "${!ARGS[@]}"; do
  [[ ${ARGS[$i]} =~ ${MOTIFS[$i]} ]] || repondre 2 "Argument $((i + 1)) refusé pour $VERBE (forme non permise)."
done
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
