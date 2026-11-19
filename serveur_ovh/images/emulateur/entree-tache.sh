#!/usr/bin/env bash
# Processus principal du conteneur `myiafactory/emulateur` (copié en /usr/local/bin/entree-tache) : crée l'AVD « emul » dans
# /avd (volume mémoire) depuis l'image système du SDK monté en lecture seule, puis attend. Les verbes de la tâche arrivent
# ensuite par `docker exec ... pont <verbe>` : l'environnement (PONT_*, ANDROID_AVD_HOME, HOME) vient de l'image et de
# `docker run`, jamais de l'appelant de `docker exec`.
# Écrit /sortie/entree-tache.log ; /sortie/.avd-pret apparaît quand l'AVD existe (le pont peut alors démarrer).
# En cas d'échec il sort avec 1 : le conteneur s'arrête et l'enveloppe hôte le constate.
# TACHE_DUREE_S (posé par l'enveloppe) : dernière sécurité, le conteneur s'arrête seul 60 s après l'échéance même si
# l'enveloppe hôte a disparu ; l'émulateur meurt avec lui.
set -u
export LC_ALL=C
exec </dev/null

SDK=/opt/android-sdk
SORTIE="${PONT_SORTIE:-/sortie}"
AVD="${PONT_AVD:-emul}"
JOURNAL="$SORTIE/entree-tache.log"

echec() {
  printf '%s\n' "$1" >> "$JOURNAL" 2>/dev/null
  printf '%s\n' "$1" >&2
  exit 1
}

[[ $AVD =~ ^[a-z0-9][a-z0-9_-]{0,39}$ ]] || echec "PONT_AVD mal formé."
[ -d "$SORTIE" ] && [ -w "$SORTIE" ] || echec "Dossier de sortie $SORTIE absent ou non inscriptible."
[ -x "$SDK/cmdline-tools/latest/bin/avdmanager" ] || echec "avdmanager introuvable dans le SDK monté ($SDK/cmdline-tools/latest/bin)."
[ -x "$SDK/platform-tools/adb" ] || echec "adb introuvable dans le SDK monté ($SDK/platform-tools)."
[ -x "$SDK/emulator/emulator" ] || echec "emulator introuvable dans le SDK monté ($SDK/emulator)."

# Première image système x86_64 trouvée : system-images/<android-N>/<variante>/x86_64 -> « system-images;android-N;variante;x86_64 ».
paquet=""
for d in "$SDK"/system-images/*/*/x86_64; do
  [ -d "$d" ] || continue
  rel="${d#"$SDK"/system-images/}"
  paquet="system-images;${rel//\//;}"
  break
done
[ -n "$paquet" ] || echec "Aucune image système x86_64 sous $SDK/system-images."

mkdir -p "${ANDROID_AVD_HOME:-/avd}" "${HOME:-/tmp}/.android" 2>/dev/null
if ! printf 'no\n' | "$SDK/cmdline-tools/latest/bin/avdmanager" create avd --force --name "$AVD" --package "$paquet" >> "$JOURNAL" 2>&1; then
  echec "Création de l'AVD $AVD impossible (image $paquet)."
fi
: > "$SORTIE/.avd-pret"

duree="${TACHE_DUREE_S:-}"
if [[ $duree =~ ^[1-9][0-9]{0,5}$ ]]; then
  exec timeout "$((duree + 60))" sleep infinity
fi
exec sleep infinity
