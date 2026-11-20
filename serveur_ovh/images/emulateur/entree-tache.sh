#!/usr/bin/env bash
# Processus principal du conteneur `myiafactory/emulateur` (copié en /usr/local/bin/entree-tache) : crée l'AVD « emul » dans
# /avd (volume mémoire) depuis l'image système ÉPINGLÉE (TACHE_IMAGE_SYSTEME, posée par l'enveloppe hôte) du SDK monté en lecture
# seule, la dimensionne (RAM 2048, partition de données 2G), puis attend. Les verbes de la tâche arrivent ensuite par
# `docker exec ... pont <verbe>` : l'environnement (PONT_*, ANDROID_AVD_HOME, HOME) vient de l'image et de `docker run`, jamais
# de l'appelant de `docker exec`.
# Écrit /sortie/entree-tache.log ; /sortie/.avd-pret apparaît quand l'AVD existe (le pont peut alors démarrer).
# Codes de sortie (le conteneur s'arrête, l'enveloppe hôte le constate) : 10 SDK ou outil absent ; 11 image système absente ou
# mal formée ; 12 création de l'AVD impossible ; 13 réglage du config.ini impossible ; 1 autre réglage invalide.
# TACHE_DUREE_S (posé par l'enveloppe) : dernière sécurité, le conteneur s'arrête seul 60 s après l'échéance même si
# l'enveloppe hôte a disparu ; l'émulateur meurt avec lui.
# avdmanager est celui de l'IMAGE (/opt/sdk-tache/cmdline-tools/latest, outils épinglés vérifiés à la construction : le SDK de
# l'hôte n'a pas de cmdline-tools) ; il est lancé avec ANDROID_SDK_ROOT=/opt/sdk-tache, dont les liens mènent au SDK monté.
# Réservées aux tests : ENTREE_SDK (SDK, /opt/android-sdk par défaut), ENTREE_OUTILS (racine des outils, /opt/sdk-tache par
# défaut) et ENTREE_SANS_ATTENTE=1 (sortir au lieu d'attendre).
set -u
export LC_ALL=C
exec </dev/null

SDK="${ENTREE_SDK:-/opt/android-sdk}"
OUTILS="${ENTREE_OUTILS:-/opt/sdk-tache}"
AVDMANAGER="$OUTILS/cmdline-tools/latest/bin/avdmanager"     # /opt/sdk-tache/cmdline-tools/latest/bin/avdmanager
SORTIE="${PONT_SORTIE:-/sortie}"
AVD="${PONT_AVD:-emul}"
AVD_RACINE="${ANDROID_AVD_HOME:-/avd}"
IMAGE="${TACHE_IMAGE_SYSTEME:-}"
JOURNAL="$SORTIE/entree-tache.log"

echec() {   # echec <code> <message>
  printf '%s\n' "$2" >> "$JOURNAL" 2>/dev/null
  printf '%s\n' "$2" >&2
  exit "$1"
}

[[ $AVD =~ ^[a-z0-9][a-z0-9_-]{0,39}$ ]] || echec 1 "PONT_AVD mal formé."
[ -d "$SORTIE" ] && [ -w "$SORTIE" ] || echec 1 "Dossier de sortie $SORTIE absent ou non inscriptible."
[ -d "$SDK" ] || echec 10 "SDK Android absent : $SDK n'est pas monté."
[ -x "$AVDMANAGER" ] || echec 10 "avdmanager introuvable dans l'image ($AVDMANAGER) : reconstruisez l'image (capacité emulateur-image)."
[ -x "$SDK/platform-tools/adb" ] || echec 10 "adb introuvable dans le SDK monté ($SDK/platform-tools)."
[ -x "$SDK/emulator/emulator" ] || echec 10 "emulator introuvable dans le SDK monté ($SDK/emulator)."

# Image système épinglée « system-images;android-N;variante;x86_64 » -> dossier system-images/android-N/variante/x86_64.
[[ $IMAGE =~ ^system-images\;android-[0-9]{1,3}(-[a-z0-9]+)?\;[a-z0-9_]+\;x86_64$ ]] || echec 11 "TACHE_IMAGE_SYSTEME absente ou mal formée."
chemin="${IMAGE//;//}"
[ -d "$SDK/$chemin" ] || echec 11 "Image système $IMAGE introuvable sous $SDK/system-images (installez-la : capacité android-emulateur)."

mkdir -p "$AVD_RACINE" "${HOME:-/tmp}/.android" 2>/dev/null
# Sans réseau ni question : « no » répond à la proposition d'un profil matériel personnalisé.
if ! printf 'no\n' | ANDROID_SDK_ROOT="$OUTILS" ANDROID_HOME="$OUTILS" "$AVDMANAGER" create avd --force --name "$AVD" \
     --package "$IMAGE" >> "$JOURNAL" 2>&1; then
  echec 12 "Création de l'AVD $AVD impossible (image $IMAGE)."
fi

# Dimensionnement : 2 Go de RAM et 2 Go de partition de données (l'émulateur par défaut en réserve davantage) ; les lignes
# existantes de ces deux clés sont remplacées, les autres gardées.
config="$AVD_RACINE/$AVD.avd/config.ini"
[ -f "$config" ] || echec 13 "config.ini de l'AVD introuvable ($config)."
if ! { grep -v -e '^hw\.ramSize=' -e '^disk\.dataPartition\.size=' "$config" || :; printf 'hw.ramSize=2048\ndisk.dataPartition.size=2G\n'; } > "$config.tmp" \
   || ! mv -f "$config.tmp" "$config"; then
  echec 13 "Réglage du config.ini impossible ($config)."
fi
: > "$SORTIE/.avd-pret"

[ "${ENTREE_SANS_ATTENTE:-}" = 1 ] && exit 0
duree="${TACHE_DUREE_S:-}"
if [[ $duree =~ ^[1-9][0-9]{0,5}$ ]]; then
  exec timeout "$((duree + 60))" sleep infinity
fi
exec sleep infinity
