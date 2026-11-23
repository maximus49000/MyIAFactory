#!/usr/bin/env bash
# Mise en place du serveur dédié (Ubuntu LTS). Le contrôleur dépose d'abord ce script dans un fichier du serveur, puis lance
# `bash <fichier> --etape X`.
# Contrat d'entrée standard : SEULES les étapes licence (la licence) et bureau_distant (UNE ligne : le mot de passe de la
# session graphique) lisent stdin. Pour toutes les autres, stdin est fermé (/dev/null) afin qu'aucune commande
# (ssh, apt, docker...) ne puisse consommer ce que l'appelant envoie.
# Les étapes android_build, android_emulateur, emulateur_image, agent_image, tests_image, tests_android_image, unity_cli et unity_bac_a_sable (capacités du serveur) ne lisent pas non plus stdin : aucun secret.
# Usage : mise_en_place.sh --etape <durcissement|docker|images|licence|bureau_distant|android_build|android_emulateur|emulateur_image|agent_image|tests_image|tests_android_image|unity_cli|unity_bac_a_sable|etat> [--simuler]
# Réservées aux tests (valeurs par défaut en production) : JVM_RACINE, KVM_PERIPH, SDK_DELAI_S.
# Sortie standard : UN SEUL objet JSON {"etape","statut","detail","versions","disque_libre_go"}.
# Idempotent : chaque étape constate l'état avant d'agir. --simuler n'exécute aucune commande apt/docker/ufw/systemctl.
# La licence Unity (.ulf) et le mot de passe de session arrivent par l'entrée standard (stdin), jamais en argument, et ne sont jamais réaffichés.
set -u

# Étiquettes épinglées (miroir de serveur_ovh/versions.json ; aucune étiquette sans étiquette flottante).
V_UNITY="unityci/editor:ubuntu-6000.6.7f1-android-4.0.0"
V_UBUNTU="ubuntu:24.04"
V_BUILD_TOOLS="34.0.0"
V_PLATEFORME="34"
V_CMDLINE_TOOLS="11076708"
# emulateur_cmdline_tools : outils propres à l'image de l'émulateur (23.0 : lit le XML v4 des images système)
V_CMDLINE_TOOLS_EMULATEUR="16111833"
V_GRADLE="8.7"
V_NODE="22"
V_CLAUDE_CODE="2.1.328"
# SDK Android dédié du serveur (miroir de la clé android_sdk de serveur_ovh/versions.json), installé dans ~/android-sdk.
V_SDK_PLATEFORME="android-36"
V_SDK_BUILD_TOOLS="36.0.0"
V_SDK_IMAGE_EMULATEUR="system-images;android-34;google_apis;x86_64"
URL_MANIFESTE_ANDROID="https://dl.google.com/android/repository/repository2-3.xml"
URL_DEPOT_ANDROID="https://dl.google.com/android/repository"
URL_INSTALLEUR_UNITY="https://unity.com/install.sh"
# Session graphique : dépôts apt (sources notées dans serveur_ovh/versions.json, clé unity_hub ; paquets non épinglés).
URL_DEPOT_UNITY_HUB="https://hub.unity3d.com/linux/repos/deb"
URL_CLE_UNITY_HUB="https://hub.unity3d.com/linux/keys/public"
URL_DEPOT_MOZILLA="https://packages.mozilla.org/apt"
URL_CLE_MOZILLA="https://packages.mozilla.org/apt/repo-signing-key.gpg"
MOT_DE_PASSE_MIN=16
# Étiquette collée aux images construites : si elle diffère des valeurs épinglées, l'image est reconstruite.
EMPREINTE_ANDROID="ubuntu=${V_UBUNTU};build_tools=${V_BUILD_TOOLS};plateforme=${V_PLATEFORME};cmdline_tools=${V_CMDLINE_TOOLS};gradle=${V_GRADLE}"
EMPREINTE_AGENT="ubuntu=${V_UBUNTU};node=${V_NODE};claude_code=${V_CLAUDE_CODE}"
# Image de l'émulateur : versions ET empreinte des fichiers de son contexte (Dockerfile, entree-tache.sh, pont.sh) : un pont modifié la reconstruit.
EMPREINTE_EMULATEUR_BASE="ubuntu=${V_UBUNTU};jdk=17"
# Image des campagnes de tests : Python 3.12 de la distribution Ubuntu 24.04, Node épinglé, puis l'empreinte de ses fichiers.
EMPREINTE_TESTS="ubuntu=${V_UBUNTU};python=3.12;node=${V_NODE}"
SEUIL_DISQUE_GO=20
DOSSIER_IMAGES="${SERVEUR_OVH_DIR:-$HOME/myiafactory/serveur_ovh}/images"   # là où l'installation dépose serveur_ovh

ETAPE=""
SIMULER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --etape)
      [ $# -ge 2 ] || { echo "L'option --etape attend une valeur (durcissement, docker, images, licence, bureau_distant, android_build, android_emulateur, emulateur_image, agent_image, tests_image, tests_android_image, unity_cli, unity_bac_a_sable ou etat)." >&2; exit 2; }
      ETAPE="$2"; shift 2 ;;
    --simuler) SIMULER=1; shift ;;
    *) echo "Argument inconnu : $1" >&2; exit 2 ;;
  esac
done
case "$ETAPE" in
  durcissement|docker|images|licence|bureau_distant|android_build|android_emulateur|emulateur_image|agent_image|tests_image|tests_android_image|unity_cli|unity_bac_a_sable|etat) ;;
  *) echo "Étape inconnue ou absente : '$ETAPE'" >&2; exit 2 ;;
esac

# Seules les étapes licence et bureau_distant lisent stdin ; ailleurs il est fermé.
if [ "$ETAPE" != "licence" ] && [ "$ETAPE" != "bureau_distant" ]; then
  exec </dev/null
fi

# --- Utilitaires -----------------------------------------------------------

echapper_json() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

disque_libre_go() {
  if [ -n "${DISQUE_LIBRE_GO:-}" ]; then
    printf '%s' "$DISQUE_LIBRE_GO"
    return
  fi
  local ko
  ko=$(df -Pk / 2>/dev/null | awk 'NR==2 {print $4}')
  printf '%s' $(( ${ko:-0} / 1024 / 1024 ))
}

# repondre <statut> <détail> : écrit l'unique objet JSON et termine.
repondre() {
  local statut="$1" detail="$2"
  printf '{"etape": "%s", "statut": "%s", "detail": "%s", "versions": {"unity": "%s", "ubuntu": "%s", "android_build_tools": "%s"}, "disque_libre_go": %s}\n' \
    "$ETAPE" "$statut" "$(echapper_json "$detail")" "$V_UNITY" "$V_UBUNTU" "$V_BUILD_TOOLS" "$(disque_libre_go)"
  exit 0
}

# --- Durcissement ----------------------------------------------------------

# Ouvre une seconde session SSH par clé (clé jetable, retirée ensuite) : prouve que la clé suffit avant de couper le mot de passe.
# Retourne 2 si authorized_keys ne contient aucune clé autre que la clé jetable : la clé jetable ne prouve que sshd,
# pas que le Directeur pourra se reconnecter.
verifier_seconde_session() {
  local tmp cle ok=1
  if ! grep -vF "myiafactory-verif" "$HOME/.ssh/authorized_keys" 2>/dev/null | grep -qE '^[[:space:]]*[^#[:space:]]'; then
    return 2
  fi
  tmp=$(mktemp -d) || return 1
  cle="$tmp/cle"
  ssh-keygen -q -t ed25519 -N "" -C "myiafactory-verif" -f "$cle" || { rm -rf "$tmp"; return 1; }
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  cat "$cle.pub" >> "$HOME/.ssh/authorized_keys"
  if ssh -n -i "$cle" -o BatchMode=yes -o PasswordAuthentication=no -o IdentitiesOnly=yes \
        -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$(id -un)@127.0.0.1" true; then
    ok=0
  fi
  grep -vF "myiafactory-verif" "$HOME/.ssh/authorized_keys" > "$tmp/ak" && cat "$tmp/ak" > "$HOME/.ssh/authorized_keys"
  rm -rf "$tmp"
  return $ok
}

durcissement_fait() {
  sudo sshd -T 2>/dev/null | grep -qi '^passwordauthentication no' \
    && sudo env LC_ALL=C ufw status 2>/dev/null | grep -q '^Status: active' \
    && dpkg -s unattended-upgrades >/dev/null 2>&1
}

etape_durcissement() {
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : installerait ufw et unattended-upgrades, vérifierait qu'une seconde session SSH par clé s'ouvre, puis couperait la connexion par mot de passe, limiterait ufw au port 22 et l'activerait."
  fi
  if durcissement_fait; then
    repondre fait "Déjà durci : connexion par mot de passe coupée, pare-feu actif, mises à jour automatiques installées."
  fi
  sudo apt-get update -y >/dev/null 2>&1
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ufw unattended-upgrades openssh-server >/dev/null 2>&1 \
    || repondre bloque "Installation d'ufw et d'unattended-upgrades impossible."
  sudo dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1
  # Garde-fou : jamais couper le mot de passe ni activer le pare-feu sans preuve qu'une clé ouvre une seconde session.
  verifier_seconde_session
  case $? in
    0) ;;
    2) repondre bloque "Aucune clé SSH autre que la clé de vérification n'est installée pour cet utilisateur : installez d'abord la clé dédiée (authorized_keys). Mot de passe et pare-feu laissés intacts pour ne pas vous enfermer dehors." ;;
    *) repondre bloque "Seconde session SSH par clé impossible : mot de passe et pare-feu laissés intacts pour ne pas vous enfermer dehors." ;;
  esac
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' | sudo tee /etc/ssh/sshd_config.d/00-myiafactory.conf >/dev/null
  if ! sudo sshd -t; then
    sudo rm -f /etc/ssh/sshd_config.d/00-myiafactory.conf
    repondre bloque "Configuration sshd invalide : retour en arrière, mot de passe conservé."
  fi
  sudo systemctl reload ssh >/dev/null 2>&1 || sudo systemctl reload sshd >/dev/null 2>&1
  sudo ufw limit 22/tcp >/dev/null 2>&1 || repondre bloque "Règle ufw « limit 22/tcp » impossible : pare-feu non activé."
  sudo ufw show added 2>/dev/null | grep -q '22' || repondre bloque "Règle ufw du port 22 introuvable : pare-feu non activé pour ne pas couper l'accès."
  sudo ufw --force enable >/dev/null 2>&1 || repondre bloque "Activation d'ufw impossible."
  repondre fait "Durci : clé SSH seule, ufw limité au port 22, mises à jour automatiques actives."
}

# --- Docker ----------------------------------------------------------------

# Paquets dont dépendent l'extraction des modules Unity et les builds (absents du serveur réel au départ) : constat par dpkg,
# installation seulement s'il en manque. $@ = paquets. Retourne 0 si tous sont présents à la fin.
assurer_paquets() {
  local p manque=0
  for p in "$@"; do
    [ "$(LC_ALL=C dpkg-query -W -f='${db:Status-Status}' "$p" 2>/dev/null)" = installed ] || manque=1
  done
  [ "$manque" = 0 ] && return 0
  sudo apt-get -o DPkg::Lock::Timeout=120 update -y >/dev/null 2>&1
  sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=120 install -y "$@" >/dev/null 2>&1
}

etape_docker() {
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : installerait unzip et zip, ajouterait le dépôt officiel Docker, installerait docker-ce puis lancerait docker run hello-world."
  fi
  assurer_paquets unzip zip || repondre bloque "Installation de unzip et zip impossible."
  if command -v docker >/dev/null 2>&1 && sudo docker run --rm hello-world >/dev/null 2>&1; then
    repondre fait "Docker déjà installé et fonctionnel (hello-world réussi)."
  fi
  sudo apt-get update -y >/dev/null 2>&1
  sudo apt-get install -y ca-certificates curl >/dev/null 2>&1
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
    || repondre bloque "Clé du dépôt Docker introuvable."
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y >/dev/null 2>&1
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null 2>&1 \
    || repondre bloque "Installation de Docker impossible."
  sudo systemctl enable --now docker >/dev/null 2>&1
  if sudo docker run --rm hello-world >/dev/null 2>&1; then
    repondre fait "Docker installé depuis le dépôt officiel, hello-world réussi."
  fi
  repondre bloque "Docker installé mais hello-world a échoué."
}

# --- Images ----------------------------------------------------------------

etape_images() {
  local libre
  libre=$(disque_libre_go)
  if [ "$libre" -lt "$SEUIL_DISQUE_GO" ]; then
    repondre bloque "Disque presque plein : ${libre} Go libres, il en faut au moins ${SEUIL_DISQUE_GO} Go avant de tirer ou construire des images."
  fi
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : créerait les volumes gradle-cache et unity-cache, tirerait ${V_UNITY}, construirait les images android et agent depuis ${DOSSIER_IMAGES}."
  fi
  sudo docker volume create gradle-cache >/dev/null 2>&1
  sudo docker volume create unity-cache >/dev/null 2>&1
  local manque=""
  sudo docker image inspect "$V_UNITY" >/dev/null 2>&1 || {
    sudo docker pull "$V_UNITY" >/dev/null 2>&1 || repondre bloque "Tirage de ${V_UNITY} impossible."
    manque="$manque unity"
  }
  local nom
  local empreinte actuelle
  for nom in android agent; do
    if [ "$nom" = android ]; then empreinte="$EMPREINTE_ANDROID"; else empreinte="$EMPREINTE_AGENT"; fi
    actuelle=$(sudo docker image inspect -f '{{ index .Config.Labels "versions" }}' "myiafactory/$nom" 2>/dev/null)
    # Image absente ou construite avec d'autres versions : on la reconstruit. L'image des agents peut aussi venir de l'étape
    # agent_image (capacité agent) : même versions, suivies de ";fichiers=<empreinte>" : elle est alors à jour.
    if [ "$actuelle" != "$empreinte" ] && ! { [ "$nom" = agent ] && [[ $actuelle == "$empreinte;fichiers="* ]]; }; then
      libre=$(disque_libre_go)
      [ "$libre" -ge "$SEUIL_DISQUE_GO" ] || repondre bloque "Disque presque plein en cours de route : ${libre} Go libres."
      if [ "$nom" = android ]; then
        sudo docker build --label "versions=$empreinte" \
          --build-arg "UBUNTU_TAG=${V_UBUNTU#ubuntu:}" --build-arg "BUILD_TOOLS=$V_BUILD_TOOLS" --build-arg "PLATEFORME=$V_PLATEFORME" \
          --build-arg "CMDLINE_TOOLS=$V_CMDLINE_TOOLS" --build-arg "GRADLE=$V_GRADLE" \
          -t "myiafactory/$nom" "$DOSSIER_IMAGES/$nom" >/dev/null 2>&1 \
          || repondre bloque "Construction de l'image $nom impossible (dossier ${DOSSIER_IMAGES}/$nom)."
      else
        sudo docker build --label "versions=$empreinte" \
          --build-arg "UBUNTU_TAG=${V_UBUNTU#ubuntu:}" --build-arg "NODE_MAJEUR=$V_NODE" --build-arg "CLAUDE_CODE=$V_CLAUDE_CODE" \
          -t "myiafactory/$nom" "$DOSSIER_IMAGES/$nom" >/dev/null 2>&1 \
          || repondre bloque "Construction de l'image $nom impossible (dossier ${DOSSIER_IMAGES}/$nom)."
      fi
      manque="$manque $nom"
    fi
  done
  if [ -z "$manque" ]; then
    repondre fait "Images déjà présentes (unity, android, agent) et volumes gradle-cache, unity-cache créés."
  fi
  repondre fait "Images prêtes (nouvelles :${manque}) ; volumes gradle-cache et unity-cache créés."
}

# --- Licence Unity ---------------------------------------------------------

etape_licence() {
  # La licence (.ulf) est lue sur stdin uniquement ; elle n'est ni passée en argument ni réaffichée.
  local licence=""
  if [ ! -t 0 ]; then
    licence=$(cat)
  fi
  if [ -z "$licence" ]; then
    repondre a_faire "$([ "$SIMULER" = 1 ] && printf "Simulation : ")Aucune licence Unity reçue sur l'entrée standard : étape à refaire quand le fichier .ulf sera fourni."
  fi
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : écrirait la licence reçue (${#licence} caractères) dans le volume unity-cache et l'activerait dans un conteneur de test."
  fi
  exec </dev/null
  # Le code de sortie d'Unity en -batchmode -quit ne prouve rien : on exige le fichier de licence dans le volume ET une
  # preuve explicite dans le journal (-logFile -). Le journal n'est jamais affiché (grep -q) ; la licence ne passe que par un tube.
  local interne='d=/root/.local/share/unity3d/Unity; mkdir -p "$d"; cat > "$d/Unity_lic.ulf"; [ -s "$d/Unity_lic.ulf" ] || exit 3;
    unity-editor -batchmode -nographics -quit -logFile - > /tmp/unity.log 2>&1 || true;
    if grep -qiE "no valid unity editor license|aborting batchmode|not licensed" /tmp/unity.log; then exit 4; fi;
    grep -qiE "license (is )?(valid|activated|updated)|successfully updated license|next license update check" /tmp/unity.log || exit 5;
    [ -s "$d/Unity_lic.ulf" ]'
  if printf '%s' "$licence" | sudo docker run --rm -i -v unity-cache:/root/.local/share/unity3d "$V_UNITY" bash -c "$interne" >/dev/null 2>&1; then
    repondre fait "Licence Unity activée dans un conteneur de test (preuve trouvée dans le journal Unity)."
  fi
  repondre bloque "Activation de la licence Unity non prouvée dans le conteneur de test (fichier ou journal sans confirmation)."
}

# --- Session graphique (bureau distant) -----------------------------------

# Une clé apt est valide si elle est non vide et lisible par gpg. gpg tourne toujours avec un --homedir temporaire (créé par
# root, supprimé sur tous les chemins) : aucun /root/.gnupg n'est créé. $1 = fichier à valider.
cle_apt_valide() {
  local gh ok=1
  [ -s "$1" ] || return 1
  gh=$(sudo mktemp -d) || return 1
  sudo gpg --homedir "$gh" --batch --no-tty --show-keys "$1" >/dev/null 2>&1 && ok=0
  sudo rm -rf "$gh"
  return "$ok"
}

# Clé de dépôt apt : téléchargée (échec HTTP = échec) dans un temporaire du même dossier, validée (non vide, lisible par gpg),
# puis placée atomiquement ; rien de partiel ne reste. $1 = URL, $2 = destination, $3 = asc (telle quelle) ou dearmor.
installer_cle_apt() {
  local url="$1" final="$2" mode="$3" brut="$2.$$.brut" tmp="$2.$$.tmp" gh ok=1
  sudo rm -f "$brut" "$tmp"
  gh=$(sudo mktemp -d) || return 1
  if sudo curl -fsSL "$url" -o "$brut" >/dev/null 2>&1 && [ -s "$brut" ] \
     && { if [ "$mode" = dearmor ]; then sudo gpg --homedir "$gh" --batch --yes --dearmor -o "$tmp" "$brut" >/dev/null 2>&1; else sudo mv -f "$brut" "$tmp"; fi; } \
     && cle_apt_valide "$tmp" \
     && sudo chmod 0644 "$tmp" && sudo mv -f "$tmp" "$final"; then
    ok=0
  fi
  sudo rm -f "$brut" "$tmp"
  sudo rm -rf "$gh"
  return "$ok"
}

# Après un échec de clé : une liste de sources n'est retirée que si SA clé finale manque ou est invalide ; si une clé valide
# et sa liste existent déjà (exécution précédente réussie), les deux restent intacts. Positionne LISTES_RETIREES et
# LISTES_GARDEES (nombres de listes retirées / conservées avec une clé valide). $1 = dossier apt.
retirer_listes_sans_cle_valide() {
  local apt="$1" liste cle
  LISTES_RETIREES=0
  LISTES_GARDEES=0
  for liste in "mozilla.list:packages.mozilla.org.asc" "unityhub.list:unityhub.gpg"; do
    cle="$apt/keyrings/${liste#*:}"
    liste="$apt/sources.list.d/${liste%%:*}"
    [ -e "$liste" ] || continue
    if cle_apt_valide "$cle"; then
      LISTES_GARDEES=$((LISTES_GARDEES + 1))
    else
      sudo rm -f "$liste"
      LISTES_RETIREES=$((LISTES_RETIREES + 1))
    fi
  done
}

# Sortie bloque APRÈS l'installation du paquet xrdp (qui démarre le service sur 0.0.0.0:3389) : le service est arrêté avant de
# répondre, pour qu'il ne reste jamais exposé derrière ufw seul. $1 = détail.
bloque_xrdp_arrete() {
  sudo systemctl stop xrdp >/dev/null 2>&1
  repondre bloque "$1"
}

# Le mot de passe de session arrive sur la première ligne de stdin ; il n'est ni un argument, ni affiché, ni dans le JSON.
# XRDP_INI, BUREAU_ATTENTE_S et APT_RACINE : réservés aux tests (valeurs par défaut en production).
etape_bureau_distant() {
  local prefixe="" mdp="" utilisateur ecoute ini="${XRDP_INI:-/etc/xrdp/xrdp.ini}" essais attente sortie_sshd apt="${APT_RACINE:-/etc/apt}"
  [ "$SIMULER" = 1 ] && prefixe="Simulation : "
  if [ ! -t 0 ]; then
    IFS= read -r mdp
  fi
  mdp="${mdp%$'\r'}"
  if [ -z "$mdp" ]; then
    repondre a_faire "${prefixe}Aucun mot de passe de session reçu sur l'entrée standard : étape à refaire quand il sera fourni."
  fi
  if [ "${#mdp}" -lt "$MOT_DE_PASSE_MIN" ]; then
    repondre bloque "${prefixe}Mot de passe de session trop court : ${MOT_DE_PASSE_MIN} caractères au moins sont exigés. Rien n'a été installé."
  fi
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : installerait XFCE, xrdp (écoute 127.0.0.1:3389 seulement), Firefox (dépôt Mozilla, hors snap) et Unity Hub (dépôt officiel), fixerait le mot de passe de session et lancerait Unity Hub au démarrage de la session ; ufw et la connexion SSH ne seraient pas modifiés."
  fi
  exec </dev/null
  utilisateur=$(id -un)
  if [ "$utilisateur" = root ]; then
    repondre bloque "L'étape s'exécute en root : le mot de passe de session ne doit jamais être fixé pour root. Lancez-la avec l'utilisateur SSH ordinaire. Rien n'a été modifié."
  fi
  # Garde-fou (échoue fermé) : un mot de passe système n'a de sens que si SSH refuse explicitement le mot de passe ET le
  # clavier interactif (avec UsePAM, ce dernier accepterait le mot de passe système). Sortie vide ou en erreur = bloque.
  sortie_sshd=$(sudo sshd -T 2>/dev/null)
  if ! printf '%s\n' "$sortie_sshd" | grep -qix 'passwordauthentication no' \
     || ! printf '%s\n' "$sortie_sshd" | grep -qix 'kbdinteractiveauthentication no'; then
    repondre bloque "La connexion SSH par mot de passe n'est pas explicitement coupée (passwordauthentication et kbdinteractiveauthentication doivent valoir no) : lancez d'abord l'étape de durcissement avant de fixer un mot de passe de session. Rien n'a été modifié."
  fi

  sudo apt-get update -y >/dev/null 2>&1
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl gpg xfce4 xfce4-terminal dbus-x11 xrdp >/dev/null 2>&1 \
    || bloque_xrdp_arrete "Installation de XFCE et de xrdp impossible."
  # Le paquet xrdp démarre le service sur 0.0.0.0:3389 : on l'arrête tout de suite ; il ne repart qu'après la configuration
  # en boucle locale (restart plus bas). Tout bloque entre-temps le laisse arrêté.
  sudo systemctl stop xrdp >/dev/null 2>&1
  sudo install -m 0755 -d "$apt/keyrings"

  # Clés des deux dépôts tiers, rafraîchies à chaque exécution, AVANT d'écrire les listes de sources. Au moindre échec on
  # ne retire une liste que si sa clé finale manque ou est invalide (un dépôt sans clé valide casserait le apt-get update
  # suivant du serveur, unattended-upgrades compris) ; une clé valide et sa liste déjà en place restent intactes, pour que
  # l'épinglage Mozilla continue de s'appliquer. Aucun fichier temporaire ne reste.
  local echec_cle=""
  installer_cle_apt "$URL_CLE_MOZILLA" "$apt/keyrings/packages.mozilla.org.asc" asc || echec_cle="Mozilla"
  [ -n "$echec_cle" ] || installer_cle_apt "$URL_CLE_UNITY_HUB" "$apt/keyrings/unityhub.gpg" dearmor || echec_cle="Unity Hub"
  if [ -n "$echec_cle" ]; then
    local suite
    retirer_listes_sans_cle_valide "$apt"
    if [ "$LISTES_RETIREES" -gt 0 ] && [ "$LISTES_GARDEES" -gt 0 ]; then
      suite="dépôt sans clé valide retiré, l'autre dépôt (clé valide) est conservé"
    elif [ "$LISTES_RETIREES" -gt 0 ]; then
      suite="dépôt sans clé valide retiré"
    elif [ "$LISTES_GARDEES" -gt 0 ]; then
      suite="la configuration précédente (clés et dépôts valides) est conservée"
    else
      suite="aucun dépôt n'a été ajouté ni modifié"
    fi
    bloque_xrdp_arrete "Clé du dépôt ${echec_cle} introuvable, vide ou illisible : ${suite}, rien n'est installé de plus."
  fi
  # Firefox hors snap : dépôt Mozilla, trousseau signé, priorité sur le paquet de transition d'Ubuntu.
  echo "deb [signed-by=$apt/keyrings/packages.mozilla.org.asc] ${URL_DEPOT_MOZILLA} mozilla main" \
    | sudo tee "$apt/sources.list.d/mozilla.list" >/dev/null
  printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' \
    | sudo tee "$apt/preferences.d/mozilla" >/dev/null
  # Unity Hub : dépôt officiel d'Unity (clé armorée convertie en trousseau).
  echo "deb [signed-by=$apt/keyrings/unityhub.gpg] ${URL_DEPOT_UNITY_HUB} stable main" \
    | sudo tee "$apt/sources.list.d/unityhub.list" >/dev/null
  sudo apt-get update -y >/dev/null 2>&1 \
    || bloque_xrdp_arrete "Mise à jour des index apt impossible après ajout des dépôts Mozilla et Unity Hub : Firefox hors snap non garanti, rien de plus n'a été fait."
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y firefox unityhub >/dev/null 2>&1 \
    || bloque_xrdp_arrete "Installation de Firefox ou d'Unity Hub impossible."

  # xrdp : écoute sur 127.0.0.1 seulement (accès par tunnel SSH), service activé, droit de lire le certificat.
  grep -qx 'port=tcp://127.0.0.1:3389' "$ini" 2>/dev/null || {
    sudo sed -i -E '0,/^port=.*/s//port=tcp:\/\/127.0.0.1:3389/' "$ini" || bloque_xrdp_arrete "Configuration de xrdp impossible."
  }
  id -nG xrdp 2>/dev/null | tr ' ' '\n' | grep -qx ssl-cert || {
    sudo usermod -aG ssl-cert xrdp >/dev/null 2>&1 || bloque_xrdp_arrete "Ajout de xrdp au groupe ssl-cert impossible."
  }
  grep -qx 'startxfce4' "$HOME/.xsession" 2>/dev/null || printf 'startxfce4\n' > "$HOME/.xsession"
  sudo systemctl enable xrdp >/dev/null 2>&1 || bloque_xrdp_arrete "Service xrdp non activable."
  # Toujours redémarrer : le paquet démarre xrdp sur 0.0.0.0 à l'installation, et une exécution précédente a pu écrire
  # le ini puis s'interrompre ; seul un redémarrage garantit que l'écoute en cours est celle du ini.
  sudo systemctl restart xrdp >/dev/null 2>&1 || bloque_xrdp_arrete "Redémarrage de xrdp impossible (service absent ?)."

  # Unity Hub au démarrage de la session graphique.
  mkdir -p "$HOME/.config/autostart"
  printf '[Desktop Entry]\nType=Application\nName=Unity Hub\nExec=unityhub\nTerminal=false\nX-GNOME-Autostart-enabled=true\n' \
    > "$HOME/.config/autostart/unityhub.desktop"

  # Preuves (avant tout mot de passe) : 3389 à l'écoute sur la boucle locale uniquement, aucune règle ufw pour 3389, binaires présents.
  attente="${BUREAU_ATTENTE_S:-15}"
  essais=0
  while :; do
    ecoute=$(ss -ltn 2>/dev/null | awk '$4 ~ /:3389$/ {print $4}')
    [ -n "$ecoute" ] && break
    [ "$essais" -ge "$attente" ] && break
    essais=$((essais + 1))
    sleep 1
  done
  [ -n "$ecoute" ] || bloque_xrdp_arrete "xrdp n'écoute sur aucun port 3389 : service non démarré."
  if printf '%s\n' "$ecoute" | grep -qvx '127\.0\.0\.1:3389'; then
    bloque_xrdp_arrete "Le port 3389 écoute ailleurs que sur 127.0.0.1 : accès distant non sûr, session non validée."
  fi
  if sudo env LC_ALL=C ufw status 2>/dev/null | grep -qE '(^|[^0-9])3389([^0-9]|$)'; then
    repondre bloque "Une règle ufw ouvre le port 3389 : retirez-la (la session ne se joint que par tunnel SSH)."
  fi
  command -v unityhub >/dev/null 2>&1 || repondre bloque "Le programme unityhub est absent après installation."
  command -v startxfce4 >/dev/null 2>&1 || repondre bloque "Le bureau XFCE (startxfce4) est absent après installation."
  # Firefox hors snap : la version installée vient de packages.mozilla.org et le binaire n'est pas le lanceur snap.
  apt-cache policy firefox 2>/dev/null \
    | awk '/^ \*\*\* /{f=1; next} /^ [^ ]/{f=0} f && /packages\.mozilla\.org/{ok=1} END{exit !ok}' \
    || repondre bloque "Le paquet firefox installé ne vient pas du dépôt Mozilla (paquet snap d'Ubuntu probable) : Firefox hors snap non obtenu."
  command -v firefox >/dev/null 2>&1 || repondre bloque "Le programme firefox est absent après installation."
  case "$(readlink -f "$(command -v firefox)" 2>/dev/null)" in
    *snap*) repondre bloque "Firefox est le lanceur snap d'Ubuntu : Firefox hors snap non obtenu." ;;
  esac
  # Mot de passe de session, en dernier et seulement si tout est prouvé : par le tube seulement
  # (printf est interne au shell, rien dans les arguments d'un processus).
  printf '%s:%s\n' "$utilisateur" "$mdp" | sudo chpasswd >/dev/null 2>&1 \
    || repondre bloque "Mot de passe de session non appliqué."
  mdp=""
  repondre fait "Session graphique prête : bureau XFCE, xrdp sur 127.0.0.1:3389, Unity Hub au démarrage de la session."
}

# --- Android : SDK dédié, émulateur ----------------------------------------

SDK_ANDROID="${HOME}/android-sdk"
SEUIL_ANDROID_BUILD_GO=15
SEUIL_EMULATEUR_GO=10
SEUIL_EMULATEUR_IMAGE_GO=3
SEUIL_UNITY_CLI_GO=2
SEUIL_AGENT_IMAGE_GO=3
SEUIL_TESTS_IMAGE_GO=3
SEUIL_TESTS_ANDROID_GO=2
RESEAU_AGENTS="myiafactory-agents"

# Les étapes de capacités s'installent pour l'utilisateur SSH ordinaire, jamais pour root (comme bureau_distant).
refuser_root() {
  if [ "$(id -un)" = root ]; then
    repondre bloque "L'étape s'exécute en root : elle s'installe pour l'utilisateur SSH ordinaire. Lancez-la avec cet utilisateur. Rien n'a été modifié."
  fi
}

# exiger_disque <Go> : bloque si l'espace libre est inférieur au seuil, avant toute installation.
exiger_disque() {
  local libre
  libre=$(disque_libre_go)
  if [ "$libre" -lt "$1" ]; then
    repondre bloque "Disque presque plein : ${libre} Go libres, il en faut au moins $1 Go pour cette étape. Rien n'a été installé."
  fi
}

# JDK d'Ubuntu en version $1 (JVM_RACINE : réservé aux tests). Écrit son dossier (liens résolus) dans JDK_TROUVE ; retourne 1 s'il est absent.
chercher_jdk() {
  local d jvm="${JVM_RACINE:-/usr/lib/jvm}"
  JDK_TROUVE=""
  for d in "$jvm"/java-"$1"-openjdk-*; do
    if [ -x "$d/bin/java" ]; then
      JDK_TROUVE=$(readlink -f "$d" 2>/dev/null || printf '%s' "$d")
      return 0
    fi
  done
  return 1
}

# JDK 17 du projet. Positionne JAVA_HOME ; retourne 1 s'il est absent.
# Sinon, un Java déjà là : le JDK livré avec le module Android d'Unity (UNITY_HUB_RACINE : réservé aux tests), puis `java` du PATH
# (mêmes lieux que la sonde de la capacité android-build). JDK_SOURCE dit lequel a servi.
trouver_jdk17() {
  local d j
  JDK_SOURCE="JDK 17"
  if chercher_jdk 17; then
    JAVA_HOME="$JDK_TROUVE"
    export JAVA_HOME
    return 0
  fi
  for d in "${UNITY_HUB_RACINE:-$HOME/Unity/Hub/Editor}"/*/Editor/Data/PlaybackEngines/AndroidPlayer/OpenJDK; do
    if [ -x "$d/bin/java" ]; then
      JAVA_HOME=$(readlink -f "$d" 2>/dev/null || printf '%s' "$d")
      export JAVA_HOME
      JDK_SOURCE="JDK d'Unity"
      return 0
    fi
  done
  j=$(command -v java 2>/dev/null) || return 1
  j=$(readlink -f "$j" 2>/dev/null || printf '%s' "$j")
  JAVA_HOME="${j%/bin/java}"
  export JAVA_HOME
  JDK_SOURCE="Java du PATH"
  return 0
}

android_sdk_pret() {
  [ -x "$SDK_ANDROID/platform-tools/adb" ] && [ -d "$SDK_ANDROID/platforms/$V_SDK_PLATEFORME" ] \
    && [ -d "$SDK_ANDROID/build-tools/$V_SDK_BUILD_TOOLS" ] && trouver_jdk17
}

# sdkmanager sous délai (SDK_DELAI_S, 1500 s par défaut ; réservé aux tests pour le réduire) et avec le JDK choisi pour lui
# (SDK_JAVA_HOME). Code 124 = délai dépassé. Sans la commande timeout, il tourne sans délai.
sdk_cmd() {
  sdk_cmd_delai "${SDK_DELAI_S:-1500}" "$@"
}

# Comme sdk_cmd, avec un délai propre : $1 = secondes.
sdk_cmd_delai() {
  local delai="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    LC_ALL=C JAVA_HOME="$SDK_JAVA_HOME" timeout "$delai" "$@"
  else
    LC_ALL=C JAVA_HOME="$SDK_JAVA_HOME" "$@"
  fi
}

# Le paquet openjdk-21 passe devant le 17 dans update-alternatives (priorité plus haute) : après son installation, java et
# javac du système seraient devenus le 21. On les remet sur le 17 SEULEMENT s'ils pointent maintenant sur un JDK 21 ; un autre
# réglage (posé par le Directeur) n'est jamais touché. $1 = dossier du JDK 17.
retablir_alternatives_jdk17() {
  local outil valeur echec=0
  for outil in java javac; do
    # LC_ALL=C : la sortie est analysée, et sur un serveur en français la ligne serait « Valeur : ».
    valeur=$(LC_ALL=C update-alternatives --query "$outil" 2>/dev/null | awk '/^Value:/ {print $2}')
    case "$valeur" in
      */java-21-openjdk-*/*)
        if [ -x "$1/bin/$outil" ] && sudo update-alternatives --set "$outil" "$1/bin/$outil" >/dev/null 2>&1; then
          :
        else
          echec=1
        fi ;;
    esac
  done
  return "$echec"
}

# Phrase ajoutée au détail final quand le repli JDK 21 a servi dans cette exécution.
JDK21_NOTE=""

# Choisit le JDK de sdkmanager : le JDK 17 du projet ; si les cmdline-tools récents refusent sa version de classe, le JDK 21
# est installé et sert à sdkmanager SEULEMENT (le JDK 17 reste le JDK du projet). Positionne SDK_JAVA_HOME ; en cas d'échec,
# ECHEC_ANDROID contient la cause et la fonction retourne 1.
preparer_jdk_sdkmanager() {
  local sdkmanager="$SDK_ANDROID/cmdline-tools/latest/bin/sdkmanager" sortie code
  SDK_JAVA_HOME="${JAVA_HOME:-}"
  sortie=$(sdk_cmd "$sdkmanager" --version 2>&1)
  code=$?
  [ "$code" = 0 ] && return 0
  if [ "$code" = 124 ]; then
    ECHEC_ANDROID="Délai dépassé pour « sdkmanager --version »."
    return 1
  fi
  if ! printf '%s' "$sortie" | grep -qiE 'UnsupportedClassVersionError|class file version|Unsupported major\.minor'; then
    ECHEC_ANDROID="sdkmanager inutilisable (« sdkmanager --version » échoue sans rapport avec la version de Java) : supprimez ~/android-sdk/cmdline-tools/latest puis relancez l'étape, ou lancez « rm -rf ~/android-sdk/cmdline-tools/latest » depuis le bureau (rien n'est supprimé automatiquement)."
    return 1
  fi
  assurer_paquets openjdk-21-jdk-headless || { ECHEC_ANDROID="sdkmanager exige un JDK plus récent que le 17 et l'installation du JDK 21 est impossible."; return 1; }
  chercher_jdk 21 || { ECHEC_ANDROID="JDK 21 introuvable après installation (java-21-openjdk) alors que sdkmanager refuse le JDK 17."; return 1; }
  SDK_JAVA_HOME="$JDK_TROUVE"
  JDK21_NOTE=" Le JDK 21 n'a été installé que pour faire tourner sdkmanager ; le JDK 17 reste le JDK du projet (le JDK par défaut du serveur est conservé ou rétabli)."
  if chercher_jdk 17; then
    if ! retablir_alternatives_jdk17 "$JDK_TROUVE"; then
      JDK21_NOTE=" Le JDK 21 n'a été installé que pour faire tourner sdkmanager, mais le JDK 17 n'a pas pu être remis comme Java par défaut du système : le JDK 21 est resté le Java par défaut ; lancez « sudo update-alternatives --config java » (puis javac) pour choisir le 17."
    fi
  fi
  if sdk_cmd "$sdkmanager" --version >/dev/null 2>&1; then
    return 0
  fi
  ECHEC_ANDROID="sdkmanager refuse le JDK 17 et le JDK 21 : aucun JDK installé ne convient à ces cmdline-tools."
  return 1
}

# Télécharge les cmdline-tools officiels de Google sans empreinte codée en dur : le manifeste officiel donne, pour le paquet
# cmdline-tools;latest du canal stable, le nom de l'archive Linux et son SHA-1 ; l'archive est téléchargée (échec HTTP =
# échec), vérifiée contre ce SHA-1, extraite, puis déplacée atomiquement vers cmdline-tools/latest. Tout vit dans un dossier
# temporaire du même dossier, supprimé sur tous les chemins. Un cmdline-tools/latest incomplet (sans sdkmanager exécutable)
# est mis de côté (latest.ancien.<horodatage>, jamais supprimé) juste avant la mise en place, et remis si elle échoue.
# En cas d'échec, ECHEC_ANDROID contient la cause. Retourne 0 si installé.
installer_cmdline_tools() {
  local dest="$SDK_ANDROID/cmdline-tools" travail ligne fichier attendu obtenu ancien="" ok=1
  ECHEC_ANDROID=""
  mkdir -p "$dest" || { ECHEC_ANDROID="Dossier $dest non créable."; return 1; }
  travail=$(mktemp -d "$dest/.telechargement.XXXXXX") || { ECHEC_ANDROID="Dossier temporaire non créable."; return 1; }
  while :; do
    curl -fsSL --connect-timeout 20 --max-time 60 "$URL_MANIFESTE_ANDROID" -o "$travail/manifeste.xml" >/dev/null 2>&1 \
      && [ -s "$travail/manifeste.xml" ] \
      || { ECHEC_ANDROID="Manifeste officiel Google introuvable ou vide (${URL_MANIFESTE_ANDROID})."; break; }
    # Un paquet par ligne ; on garde celui de cmdline-tools;latest au canal stable (channel-0), entrée Linux
    # « <checksum type="sha1">…</checksum><url>commandlinetools-linux-N_latest.zip</url> » (le plus grand N s'il y en a plusieurs).
    ligne=$(tr '\n\r\t' '   ' < "$travail/manifeste.xml" \
      | sed 's#</remotePackage>#&\n#g' \
      | grep -F 'remotePackage path="cmdline-tools;latest"' \
      | grep -F 'channelRef ref="channel-0"' \
      | grep -oE '<checksum type="sha1">[0-9a-fA-F]{40}</checksum> *<url>commandlinetools-linux-[0-9]+_latest\.zip</url>' \
      | sed -E 's/.*type="sha1">([0-9a-fA-F]{40})<\/checksum> *<url>(commandlinetools-linux-([0-9]+)_latest\.zip)<\/url>/\3 \1 \2/' \
      | sort -n | tail -n 1)
    [ -n "$ligne" ] || { ECHEC_ANDROID="Aucune archive cmdline-tools Linux (paquet cmdline-tools;latest, canal stable) dans le manifeste officiel Google."; break; }
    attendu=$(printf '%s' "$ligne" | awk '{print tolower($2)}')
    fichier=$(printf '%s' "$ligne" | awk '{print $3}')
    curl -fsSL --connect-timeout 20 --max-time 1200 "${URL_DEPOT_ANDROID}/${fichier}" -o "$travail/archive.zip" >/dev/null 2>&1 \
      && [ -s "$travail/archive.zip" ] \
      || { ECHEC_ANDROID="Téléchargement de ${fichier} impossible, vide ou tronqué."; break; }
    obtenu=$(sha1sum "$travail/archive.zip" 2>/dev/null | awk '{print tolower($1)}')
    [ -n "$obtenu" ] && [ "$obtenu" = "$attendu" ] \
      || { ECHEC_ANDROID="Empreinte SHA-1 de ${fichier} différente de celle du manifeste officiel : archive refusée."; break; }
    mkdir "$travail/extrait" && unzip -q "$travail/archive.zip" -d "$travail/extrait" >/dev/null 2>&1 \
      && [ -x "$travail/extrait/cmdline-tools/bin/sdkmanager" ] \
      || { ECHEC_ANDROID="Extraction de ${fichier} impossible ou archive sans sdkmanager."; break; }
    if [ -e "$dest/latest" ]; then
      ancien="$dest/latest.ancien.$(date +%Y%m%d%H%M%S)"
      mv -T "$dest/latest" "$ancien" 2>/dev/null \
        || { ancien=""; ECHEC_ANDROID="Mise de côté de l'ancien cmdline-tools/latest incomplet impossible."; break; }
    fi
    if ! mv -T "$travail/extrait/cmdline-tools" "$dest/latest" 2>/dev/null; then
      [ -z "$ancien" ] || mv -T "$ancien" "$dest/latest" 2>/dev/null
      ECHEC_ANDROID="Mise en place de cmdline-tools/latest impossible (l'ancien dossier, s'il existait, a été remis)."
      break
    fi
    ok=0
    break
  done
  rm -rf "$travail"
  return "$ok"
}

# Étape android_build : unzip, zip, JDK 17, SDK dédié ~/android-sdk, licences, platform-tools, plateforme et build-tools.
etape_android_build() {
  local sdkmanager="$SDK_ANDROID/cmdline-tools/latest/bin/sdkmanager" lic code delai="${SDK_DELAI_S:-1500}"
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : installerait unzip, zip et le JDK 17, téléchargerait les cmdline-tools officiels de Google (SHA-1 vérifié d'après le manifeste officiel) dans ${SDK_ANDROID}, accepterait les licences puis installerait platform-tools, ${V_SDK_PLATEFORME} et build-tools ${V_SDK_BUILD_TOOLS}."
  fi
  refuser_root
  # Une session SSH tuée en cours de téléchargement laisse son dossier temporaire : on le retire.
  rm -rf "$SDK_ANDROID"/cmdline-tools/.telechargement.* 2>/dev/null
  if android_sdk_pret; then
    repondre fait "SDK Android déjà en place dans ${SDK_ANDROID} (adb, ${V_SDK_PLATEFORME}, build-tools ${V_SDK_BUILD_TOOLS}, ${JDK_SOURCE})."
  fi
  exiger_disque "$SEUIL_ANDROID_BUILD_GO"
  assurer_paquets unzip zip openjdk-17-jdk-headless || repondre bloque "Installation de unzip, zip et du JDK 17 impossible."
  trouver_jdk17 || repondre bloque "JDK 17 introuvable après installation (java-17-openjdk)."
  if [ ! -x "$sdkmanager" ]; then
    installer_cmdline_tools || repondre bloque "${ECHEC_ANDROID} Rien n'a été installé."
  fi
  preparer_jdk_sdkmanager || repondre bloque "${ECHEC_ANDROID}"
  # Licences : délai court, et un dépassement n'est qu'un avertissement (l'installation qui suit fait foi).
  yes 2>/dev/null | sdk_cmd_delai "${SDK_DELAI_LICENCE_S:-120}" "$sdkmanager" --sdk_root="$SDK_ANDROID" --licenses >/dev/null 2>&1
  lic=${PIPESTATUS[1]}
  sdk_cmd "$sdkmanager" --sdk_root="$SDK_ANDROID" "platform-tools" "platforms;${V_SDK_PLATEFORME}" "build-tools;${V_SDK_BUILD_TOOLS}" >/dev/null 2>&1
  code=$?
  if [ "$code" = 124 ]; then
    repondre bloque "Délai dépassé (${delai} s) pour sdkmanager : installation du SDK Android interrompue, à refaire."
  elif [ "$code" != 0 ] && [ "$lic" != 0 ] && [ "$lic" != 124 ]; then
    repondre bloque "Licences Android non acceptées (sdkmanager --licenses a échoué, code ${lic}) : platform-tools, ${V_SDK_PLATEFORME} et build-tools ${V_SDK_BUILD_TOOLS} non installés."
  elif [ "$code" != 0 ]; then
    repondre bloque "Installation de platform-tools, ${V_SDK_PLATEFORME} et build-tools ${V_SDK_BUILD_TOOLS} par sdkmanager impossible."
  fi
  android_sdk_pret || repondre bloque "SDK Android incomplet après installation (adb, ${V_SDK_PLATEFORME} ou build-tools ${V_SDK_BUILD_TOOLS} manquant)."
  repondre fait "SDK Android installé dans ${SDK_ANDROID} (adb, ${V_SDK_PLATEFORME}, build-tools ${V_SDK_BUILD_TOOLS}, JDK 17).${JDK21_NOTE}"
}

emulateur_pret() {
  local u
  u=$(id -un)
  [ -x "$SDK_ANDROID/emulator/emulator" ] && [ -d "$SDK_ANDROID/${V_SDK_IMAGE_EMULATEUR//;//}" ] \
    && [ -e "${KVM_PERIPH:-/dev/kvm}" ] && id -nG "$u" 2>/dev/null | tr ' ' '\n' | grep -qx kvm
}

# Étape android_emulateur : exige android_build et /dev/kvm ; groupe kvm, emulator et image système x86_64.
etape_android_emulateur() {
  local sdkmanager="$SDK_ANDROID/cmdline-tools/latest/bin/sdkmanager" kvm="${KVM_PERIPH:-/dev/kvm}" u ajoute="" code delai="${SDK_DELAI_S:-1500}"
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : exigerait android_build et /dev/kvm, ajouterait l'utilisateur au groupe kvm puis installerait emulator et ${V_SDK_IMAGE_EMULATEUR} par sdkmanager."
  fi
  refuser_root
  if [ ! -x "$sdkmanager" ] || ! android_sdk_pret; then
    repondre a_faire "SDK Android absent : installez d'abord la capacité android-build (étape android_build), puis refaites celle-ci."
  fi
  if [ ! -e "$kvm" ]; then
    repondre bloque "KVM indisponible sur ce serveur : l'émulateur ne sera pas accéléré (${kvm} absent)."
  fi
  u=$(id -un)
  if [ ! -x "$SDK_ANDROID/emulator/emulator" ] || [ ! -d "$SDK_ANDROID/${V_SDK_IMAGE_EMULATEUR//;//}" ]; then
    exiger_disque "$SEUIL_EMULATEUR_GO"
  fi
  if ! id -nG "$u" 2>/dev/null | tr ' ' '\n' | grep -qx kvm; then
    sudo usermod -aG kvm "$u" >/dev/null 2>&1 || repondre bloque "Ajout de ${u} au groupe kvm impossible."
    ajoute=1
  fi
  if [ ! -x "$SDK_ANDROID/emulator/emulator" ] || [ ! -d "$SDK_ANDROID/${V_SDK_IMAGE_EMULATEUR//;//}" ]; then
    preparer_jdk_sdkmanager || repondre bloque "${ECHEC_ANDROID}"
    sdk_cmd "$sdkmanager" --sdk_root="$SDK_ANDROID" "emulator" "$V_SDK_IMAGE_EMULATEUR" >/dev/null 2>&1
    code=$?
    if [ "$code" = 124 ]; then
      repondre bloque "Délai dépassé (${delai} s) pour sdkmanager : installation de l'émulateur interrompue, à refaire."
    elif [ "$code" != 0 ]; then
      repondre bloque "Installation de l'émulateur et de ${V_SDK_IMAGE_EMULATEUR} par sdkmanager impossible."
    fi
  fi
  emulateur_pret || repondre bloque "Émulateur incomplet après installation (emulator, image système, ${kvm} ou groupe kvm manquant)."
  if [ -n "$ajoute" ]; then
    repondre fait "Émulateur Android installé (${V_SDK_IMAGE_EMULATEUR}). ${u} a été ajouté au groupe kvm : cela prend effet à la prochaine connexion SSH.${JDK21_NOTE}"
  fi
  repondre fait "Émulateur Android en place (${V_SDK_IMAGE_EMULATEUR}), accélération KVM disponible.${JDK21_NOTE}"
}

# --- Image de l'émulateur ----------------------------------------------------

# Étape emulateur_image : construit myiafactory/emulateur depuis images/emulateur/Dockerfile, images/emulateur/entree-tache.sh
# et taches/pont.sh (dossier $SERVEUR_OVH_DIR, par défaut ~/myiafactory/serveur_ovh : celui où l'installation dépose ces fichiers),
# assemblés dans un contexte temporaire. Idempotente : l'image porte une étiquette « versions » (versions + empreinte des
# fichiers) ; elle n'est reconstruite que si l'étiquette diffère. Le marqueur ~/.myiafactory/emulateur-image.version (contenu =
# l'étiquette, testé par la sonde du catalogue) est retiré avant toute reconstruction puis réécrit une fois l'image construite.
# Le SDK Android n'est pas dans l'image : il est monté à l'exécution. Les outils en ligne de commande Android (avdmanager), que
# le SDK de l'hôte n'a pas, sont apportés par l'image (version ${V_CMDLINE_TOOLS_EMULATEUR} épinglée, SHA-1 vérifié d'après le manifeste
# officiel Google à la construction) : la construction a besoin du réseau (aucun --network none), et l'image grossit d'environ
# 180 Mo.
etape_emulateur_image() {
  local racine="${SERVEUR_OVH_DIR:-$HOME/myiafactory/serveur_ovh}" ctx empreinte actuelle marqueur="$HOME/.myiafactory/emulateur-image.version" f journal fin code fichiers_h
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : construirait l'image myiafactory/emulateur (Ubuntu ${V_UBUNTU#ubuntu:}, JDK 17, pont, outils en ligne de commande Android ${V_CMDLINE_TOOLS_EMULATEUR} téléchargés de Google à la construction, SHA-1 vérifié d'après le manifeste officiel, environ 180 Mo de plus) depuis ${racine} puis écrirait ${marqueur}."
  fi
  refuser_root
  exiger_disque "$SEUIL_EMULATEUR_IMAGE_GO"
  command -v docker >/dev/null 2>&1 || repondre a_faire "Docker absent : installez d'abord la capacité base (étape docker), puis refaites celle-ci."
  for f in images/emulateur/Dockerfile images/emulateur/entree-tache.sh taches/pont.sh; do
    [ -f "$racine/$f" ] || repondre bloque "Fichier de l'image introuvable : $racine/$f. Relancez l'installation (elle redépose les fichiers)."
  done
  fichiers_h=$(cat "$racine/images/emulateur/Dockerfile" "$racine/images/emulateur/entree-tache.sh" "$racine/taches/pont.sh" | sha256sum | cut -c1-16)
  [[ $fichiers_h =~ ^[0-9a-f]{16}$ ]] || repondre bloque "Empreinte des fichiers de l'image incalculable (sha256sum) : rien n'a été construit ni écrit."
  empreinte="${EMPREINTE_EMULATEUR_BASE};fichiers=${fichiers_h}"
  actuelle=$(sudo -n docker image inspect -f '{{ index .Config.Labels "versions" }}' myiafactory/emulateur 2>/dev/null)
  if [ "$actuelle" != "$empreinte" ]; then
    rm -f "$marqueur"
    ctx=$(mktemp -d) || repondre bloque "Dossier temporaire non créable pour construire l'image."
    if ! cp "$racine/images/emulateur/Dockerfile" "$racine/images/emulateur/entree-tache.sh" "$racine/taches/pont.sh" "$ctx/"; then
      rm -rf "$ctx"
      repondre bloque "Contexte de construction de l'image non préparable."
    fi
    journal=$(sudo -n docker build --label "versions=$empreinte" --build-arg "UBUNTU_TAG=${V_UBUNTU#ubuntu:}" --build-arg "CMDLINE_TOOLS=$V_CMDLINE_TOOLS_EMULATEUR" -t myiafactory/emulateur "$ctx" 2>&1)
    code=$?
    rm -rf "$ctx"
    if [ "$code" != 0 ]; then
      fin=$(printf '%s\n' "$journal" | tail -n 20 | tr -d '\000-\010\013-\037' | cut -c1-200)
      fin="${fin//$HOME/\~}"
      repondre bloque "Construction de l'image myiafactory/emulateur impossible (contexte ${racine}). Fin du journal de construction : ${fin}"
    fi
    actuelle=""
  fi
  mkdir -p "$HOME/.myiafactory" || repondre bloque "Dossier $HOME/.myiafactory non créable."
  if [ "$(cat "$marqueur" 2>/dev/null)" != "$empreinte" ]; then
    if ! { printf '%s\n' "$empreinte" > "$marqueur.tmp.$$" && mv -f "$marqueur.tmp.$$" "$marqueur"; }; then
      rm -f "$marqueur.tmp.$$"
      repondre bloque "Marqueur $marqueur non écrit."
    fi
  fi
  if [ -z "$actuelle" ]; then repondre fait "Image myiafactory/emulateur construite (${empreinte}) ; marqueur écrit."; fi
  repondre fait "Image myiafactory/emulateur déjà à jour (${empreinte})."
}

# --- Image de l'agent --------------------------------------------------------

# Étape agent_image : construit myiafactory/agent depuis images/agent/ (Dockerfile, entree-agent.py, pont ; dossier
# $SERVEUR_OVH_DIR, par défaut ~/myiafactory/serveur_ovh) assemblés dans un contexte temporaire, crée le réseau Docker
# myiafactory-agents s'il manque (seul réseau des conteneurs d'agent : sortant, nécessaire à l'API de Claude), puis écrit le
# marqueur ~/.myiafactory/agent-image.version (contenu = l'étiquette « versions » de l'image : versions épinglées + 16 hexa du
# SHA-256 des trois fichiers, testé par la sonde du catalogue). Idempotente : l'image n'est reconstruite que si l'étiquette
# diffère ; le marqueur est retiré avant toute reconstruction puis réécrit en dernier. L'entrée de l'agent et le pont arrivent
# aux tâches 2 et 7 : s'ils manquent, l'étape les ignore dans l'empreinte (le Dockerfile, lui, est exigé). Aucun identifiant
# n'entre dans l'image : le jeton de l'abonnement est monté à l'exécution, jamais construit dedans (la construction a besoin du réseau).
# Déposés avec l'étape mais HORS de l'image et de son empreinte : taches/enregistrer_jeton.sh (lancé à la main par le
# Directeur) et taches/pont_hote.py (pont hôte du mode pilote, lancé sur l'hôte par lancer_agent.sh avec le python3 du
# système ; aussi redéposé à chaque lancement pilote avec lancer_agent.sh et lancer_emulation.sh).
etape_agent_image() {
  local racine="${SERVEUR_OVH_DIR:-$HOME/myiafactory/serveur_ovh}" ctx empreinte actuelle marqueur="$HOME/.myiafactory/agent-image.version" f journal fin code fichiers_h
  local presents=()
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : construirait l'image myiafactory/agent (Ubuntu ${V_UBUNTU#ubuntu:}, Node ${V_NODE}, Claude Code ${V_CLAUDE_CODE}, sans curl ni wget) depuis ${racine}, créerait le réseau Docker ${RESEAU_AGENTS} s'il manque, puis écrirait ${marqueur}."
  fi
  refuser_root
  exiger_disque "$SEUIL_AGENT_IMAGE_GO"
  command -v docker >/dev/null 2>&1 || repondre a_faire "Docker absent : installez d'abord la capacité base (étape docker), puis refaites celle-ci."
  [ -f "$racine/images/agent/Dockerfile" ] || repondre bloque "Fichier de l'image introuvable : $racine/images/agent/Dockerfile. Relancez l'installation (elle redépose les fichiers)."
  for f in images/agent/Dockerfile images/agent/entree-agent.py images/agent/pont; do
    if [ -f "$racine/$f" ]; then presents+=("$racine/$f"); fi
  done
  fichiers_h=$(cat "${presents[@]}" | sha256sum | cut -c1-16)
  [[ $fichiers_h =~ ^[0-9a-f]{16}$ ]] || repondre bloque "Empreinte des fichiers de l'image incalculable (sha256sum) : rien n'a été construit ni écrit."
  empreinte="${EMPREINTE_AGENT};fichiers=${fichiers_h}"
  actuelle=$(sudo -n docker image inspect -f '{{ index .Config.Labels "versions" }}' myiafactory/agent 2>/dev/null)
  if [ "$actuelle" != "$empreinte" ]; then
    rm -f "$marqueur"
    ctx=$(mktemp -d) || repondre bloque "Dossier temporaire non créable pour construire l'image."
    if ! cp "${presents[@]}" "$ctx/"; then
      rm -rf "$ctx"
      repondre bloque "Contexte de construction de l'image non préparable."
    fi
    journal=$(sudo -n docker build --label "versions=$empreinte" --build-arg "UBUNTU_TAG=${V_UBUNTU#ubuntu:}" --build-arg "NODE_MAJEUR=$V_NODE" --build-arg "CLAUDE_CODE=$V_CLAUDE_CODE" -t myiafactory/agent "$ctx" 2>&1)
    code=$?
    rm -rf "$ctx"
    if [ "$code" != 0 ]; then
      fin=$(printf '%s\n' "$journal" | tail -n 20 | tr -d '\000-\010\013-\037' | cut -c1-200)
      fin="${fin//$HOME/\~}"
      repondre bloque "Construction de l'image myiafactory/agent impossible (contexte ${racine}). Fin du journal de construction : ${fin}"
    fi
    actuelle=""
  fi
  if ! sudo -n docker network inspect "$RESEAU_AGENTS" >/dev/null 2>&1; then
    if ! sudo -n docker network create "$RESEAU_AGENTS" >/dev/null 2>&1; then
      rm -f "$marqueur"
      repondre bloque "Réseau Docker ${RESEAU_AGENTS} non créable : le marqueur n'est pas écrit, l'image des agents ne peut pas être utilisée."
    fi
  fi
  mkdir -p "$HOME/.myiafactory" || repondre bloque "Dossier $HOME/.myiafactory non créable."
  if [ "$(cat "$marqueur" 2>/dev/null)" != "$empreinte" ]; then
    if ! { printf '%s\n' "$empreinte" > "$marqueur.tmp.$$" && mv -f "$marqueur.tmp.$$" "$marqueur"; }; then
      rm -f "$marqueur.tmp.$$"
      repondre bloque "Marqueur $marqueur non écrit."
    fi
  fi
  if [ -z "$actuelle" ]; then repondre fait "Image myiafactory/agent construite (${empreinte}), réseau ${RESEAU_AGENTS} prêt ; marqueur écrit."; fi
  repondre fait "Image myiafactory/agent déjà à jour (${empreinte}), réseau ${RESEAU_AGENTS} prêt."
}

# --- Image des campagnes de tests --------------------------------------------

# Étape tests_image : construit myiafactory/tests depuis images/tests/ (Dockerfile, entree-tests.sh ; dossier $SERVEUR_OVH_DIR,
# par défaut ~/myiafactory/serveur_ovh) assemblés dans un contexte temporaire, puis écrit le marqueur
# ~/.myiafactory/tests-image.version (contenu = l'étiquette « versions » de l'image : versions épinglées + 16 hexa du SHA-256
# des deux fichiers, testé par la sonde du catalogue). Idempotente : l'image n'est reconstruite que si l'étiquette diffère ;
# le marqueur est retiré avant toute reconstruction puis réécrit en dernier. Aucun réseau Docker n'est créé : les conteneurs
# de tests tournent sans réseau (--network none, posé par taches/lancer_tests.sh). Aucun identifiant n'entre dans l'image ;
# la construction, elle, a besoin du réseau (dépôts Ubuntu et Node).
etape_tests_image() {
  local racine="${SERVEUR_OVH_DIR:-$HOME/myiafactory/serveur_ovh}" ctx empreinte actuelle marqueur="$HOME/.myiafactory/tests-image.version" f journal fin code fichiers_h
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : construirait l'image myiafactory/tests (Ubuntu ${V_UBUNTU#ubuntu:}, Python 3.12, Node ${V_NODE}, outils de construction, sans curl ni wget, utilisateur 1000) depuis ${racine} puis écrirait ${marqueur}."
  fi
  refuser_root
  exiger_disque "$SEUIL_TESTS_IMAGE_GO"
  command -v docker >/dev/null 2>&1 || repondre a_faire "Docker absent : installez d'abord la capacité base (étape docker), puis refaites celle-ci."
  for f in images/tests/Dockerfile images/tests/entree-tests.sh; do
    [ -f "$racine/$f" ] || repondre bloque "Fichier de l'image introuvable : $racine/$f. Relancez l'installation (elle redépose les fichiers)."
  done
  fichiers_h=$(cat "$racine/images/tests/Dockerfile" "$racine/images/tests/entree-tests.sh" | sha256sum | cut -c1-16)
  [[ $fichiers_h =~ ^[0-9a-f]{16}$ ]] || repondre bloque "Empreinte des fichiers de l'image incalculable (sha256sum) : rien n'a été construit ni écrit."
  empreinte="${EMPREINTE_TESTS};fichiers=${fichiers_h}"
  actuelle=$(sudo -n docker image inspect -f '{{ index .Config.Labels "versions" }}' myiafactory/tests 2>/dev/null)
  if [ "$actuelle" != "$empreinte" ]; then
    rm -f "$marqueur"
    ctx=$(mktemp -d) || repondre bloque "Dossier temporaire non créable pour construire l'image."
    if ! cp "$racine/images/tests/Dockerfile" "$racine/images/tests/entree-tests.sh" "$ctx/"; then
      rm -rf "$ctx"
      repondre bloque "Contexte de construction de l'image non préparable."
    fi
    journal=$(sudo -n docker build --label "versions=$empreinte" --build-arg "UBUNTU_TAG=${V_UBUNTU#ubuntu:}" --build-arg "NODE_MAJEUR=$V_NODE" -t myiafactory/tests "$ctx" 2>&1)
    code=$?
    rm -rf "$ctx"
    if [ "$code" != 0 ]; then
      fin=$(printf '%s\n' "$journal" | tail -n 20 | tr -d '\000-\010\013-\037' | cut -c1-200)
      fin="${fin//$HOME/\~}"
      repondre bloque "Construction de l'image myiafactory/tests impossible (contexte ${racine}). Fin du journal de construction : ${fin}"
    fi
    actuelle=""
  fi
  mkdir -p "$HOME/.myiafactory" || repondre bloque "Dossier $HOME/.myiafactory non créable."
  if [ "$(cat "$marqueur" 2>/dev/null)" != "$empreinte" ]; then
    if ! { printf '%s\n' "$empreinte" > "$marqueur.tmp.$$" && mv -f "$marqueur.tmp.$$" "$marqueur"; }; then
      rm -f "$marqueur.tmp.$$"
      repondre bloque "Marqueur $marqueur non écrit."
    fi
  fi
  if [ -z "$actuelle" ]; then repondre fait "Image myiafactory/tests construite (${empreinte}) ; marqueur écrit."; fi
  repondre fait "Image myiafactory/tests déjà à jour (${empreinte})."
}

# --- Image des campagnes de tests Gradle/Android ----------------------------

# Étape tests_android_image : construit myiafactory/tests-android (FROM myiafactory/tests + JDK 17 et 21 de la distribution) depuis
# images/tests-android/Dockerfile seul (contexte temporaire à un fichier), puis écrit ~/.myiafactory/tests-android-image.version
# (contenu = l'étiquette « versions » : étiquette de l'image de base + JDK + 16 hexa du SHA-256 du Dockerfile, même forme que
# serveur_installation.empreinte_etape). Le SDK Android n'entre PAS dans l'image : c'est celui de l'hôte (~/android-sdk,
# capacité android-build), monté en lecture seule par taches/lancer_tests.sh. Idempotente comme tests_image : reconstruite
# seulement si l'étiquette diffère (donc aussi quand l'image de base change) ; marqueur retiré avant, réécrit en dernier.
etape_tests_android_image() {
  local racine="${SERVEUR_OVH_DIR:-$HOME/myiafactory/serveur_ovh}" ctx base empreinte actuelle marqueur="$HOME/.myiafactory/tests-android-image.version" journal fin code fichiers_h
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : construirait l'image myiafactory/tests-android (myiafactory/tests + JDK 17 et 21 de la distribution, SDK Android de l'hôte monté en lecture seule, sans curl ni wget) depuis ${racine} puis écrirait ${marqueur}."
  fi
  refuser_root
  exiger_disque "$SEUIL_TESTS_ANDROID_GO"
  command -v docker >/dev/null 2>&1 || repondre a_faire "Docker absent : installez d'abord la capacité base (étape docker), puis refaites celle-ci."
  [ -f "$racine/images/tests-android/Dockerfile" ] || repondre bloque "Fichier de l'image introuvable : $racine/images/tests-android/Dockerfile. Relancez l'installation (elle redépose les fichiers)."
  base=$(sudo -n docker image inspect -f '{{ index .Config.Labels "versions" }}' myiafactory/tests 2>/dev/null)
  [ -n "$base" ] || repondre a_faire "Image myiafactory/tests absente : installez d'abord la capacité tests-image, puis refaites celle-ci."
  fichiers_h=$(sha256sum < "$racine/images/tests-android/Dockerfile" | cut -c1-16)
  [[ $fichiers_h =~ ^[0-9a-f]{16}$ ]] || repondre bloque "Empreinte du Dockerfile incalculable (sha256sum) : rien n'a été construit ni écrit."
  empreinte="base=${base};jdk=17,21;fichiers=${fichiers_h}"
  actuelle=$(sudo -n docker image inspect -f '{{ index .Config.Labels "versions" }}' myiafactory/tests-android 2>/dev/null)
  if [ "$actuelle" != "$empreinte" ]; then
    rm -f "$marqueur"
    ctx=$(mktemp -d) || repondre bloque "Dossier temporaire non créable pour construire l'image."
    if ! cp "$racine/images/tests-android/Dockerfile" "$ctx/"; then
      rm -rf "$ctx"
      repondre bloque "Contexte de construction de l'image non préparable."
    fi
    journal=$(sudo -n docker build --label "versions=$empreinte" -t myiafactory/tests-android "$ctx" 2>&1)
    code=$?
    rm -rf "$ctx"
    if [ "$code" != 0 ]; then
      fin=$(printf '%s\n' "$journal" | tail -n 20 | tr -d '\000-\010\013-\037' | cut -c1-200)
      fin="${fin//$HOME/\~}"
      repondre bloque "Construction de l'image myiafactory/tests-android impossible (contexte ${racine}). Fin du journal de construction : ${fin}"
    fi
    actuelle=""
  fi
  mkdir -p "$HOME/.myiafactory" || repondre bloque "Dossier $HOME/.myiafactory non créable."
  if [ "$(cat "$marqueur" 2>/dev/null)" != "$empreinte" ]; then
    if ! { printf '%s\n' "$empreinte" > "$marqueur.tmp.$$" && mv -f "$marqueur.tmp.$$" "$marqueur"; }; then
      rm -f "$marqueur.tmp.$$"
      repondre bloque "Marqueur $marqueur non écrit."
    fi
  fi
  if [ -z "$actuelle" ]; then repondre fait "Image myiafactory/tests-android construite (${empreinte}) ; marqueur écrit."; fi
  repondre fait "Image myiafactory/tests-android déjà à jour (${empreinte})."
}

# --- Unity CLI -------------------------------------------------------------

# Étape unity_cli : l'outil officiel Unity CLI seulement, installé pour l'utilisateur dans ~/.local/bin/unity. Le script
# officiel (https://unity.com/install.sh) est d'abord téléchargé dans un fichier, contrôlé (non vide, commence par #!) puis
# exécuté par bash ; jamais de « curl | bash ». C'est ce script qui télécharge le binaire et vérifie son SHA-256. Il est lancé
# avec UNITY_CLI_SKIP_SETUP=1 : sans son étape finale, qui installerait des skills Unity dans tous les clients d'agents trouvés
# sur la machine ; il peut en revanche ajouter ~/.local/bin au PATH de ~/.bashrc (dit dans le détail). Aucun éditeur n'est
# installé ici : il faut une session Unity authentifiée (Unity Hub dans la session graphique, ou `unity install <version>`).
etape_unity_cli() {
  local dossier="$HOME/.local/bin" unity="$HOME/.local/bin/unity" tmp ok=0 prefixe="Unity CLI installé"
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : téléchargerait le script officiel ${URL_INSTALLEUR_UNITY} dans un fichier, le contrôlerait puis l'exécuterait par bash pour installer Unity CLI dans ${unity}."
  fi
  refuser_root
  # Une session SSH tuée en cours de téléchargement laisse son fichier temporaire : on le retire.
  rm -f "$dossier"/.installeur-unity.* 2>/dev/null
  if "$unity" --version >/dev/null 2>&1; then
    prefixe="Unity CLI déjà installé"
  else
    exiger_disque "$SEUIL_UNITY_CLI_GO"
    mkdir -p "$dossier" || repondre bloque "Dossier ${dossier} non créable."
    tmp=$(mktemp "$dossier/.installeur-unity.XXXXXX") || repondre bloque "Fichier temporaire non créable dans ${dossier}."
    if curl -fsSL --connect-timeout 20 --max-time 60 "$URL_INSTALLEUR_UNITY" -o "$tmp" >/dev/null 2>&1 && [ -s "$tmp" ] && [ "$(head -c 2 "$tmp")" = '#!' ]; then
      UNITY_CLI_SKIP_SETUP=1 bash "$tmp" >/dev/null 2>&1 && ok=1
    fi
    rm -f "$tmp"
    if [ "$ok" != 1 ]; then
      repondre bloque "Script officiel d'installation d'Unity CLI introuvable, vide, sans ligne #! ou en échec (${URL_INSTALLEUR_UNITY}) : rien n'a été exécuté de non vérifié."
    fi
    "$unity" --version >/dev/null 2>&1 || repondre bloque "Unity CLI absent ou inutilisable après l'installation (${unity} --version échoue)."
  fi
  repondre fait "${prefixe} ; l'installateur officiel a pu ajouter ~/.local/bin au PATH dans votre profil shell (~/.bashrc). Aucun éditeur installé : installez un éditeur par la session graphique (Unity Hub) ou \`unity install <version>\` une fois connecté."
}

# --- Bac à sable Unity de l'hôte (option A, § 5.16, tâche 14h) --------------

# Étape unity_bac_a_sable : prépare ce qui permet à l'enveloppe des tests de lancer l'éditeur Unity de l'HÔTE dans une unité
# systemd confinée (code de projet non fiable sur l'hôte) : utilisateur système unity-tests (sans shell, mot de passe verrouillé,
# hors docker/kvm/sudo/adm/lxd), /var/lib/unity-tests et campagnes/ (0700, à lui), le script racine et ses entrées dans
# /usr/local/lib/myiafactory (root, 0755), la règle /etc/sudoers.d/myiafactory-unity limitée au SEUL chemin du script racine
# (vérifiée par visudo -c avant ET après la pose, retirée si refus), une ACL de lecture pour unity-tests sur les SEULS fichiers
# de licence (et une ACL par défaut sur licenses/ pour qu'un rafraîchissement par Hub la garde). Vérifie d'abord que
# ~/agent-identifiants, ~/.ssh et ~/taches sont en 0700 (sinon bloque, rien n'est modifié). N'écrit PAS le marqueur
# ~/.myiafactory/unity-bac-a-sable.version : seul l'audit J14 (sonde-bac-a-sable.sh lancée dans l'unité par
# `unity-bac-a-sable.sh auditer …`) l'écrit, après lecture de son résultat. La licence n'est jamais lue (noms seulement).
BAC_LIB=/usr/local/lib/myiafactory
BAC_SCRIPT="$BAC_LIB/unity-bac-a-sable.sh"
BAC_SUDOERS=/etc/sudoers.d/myiafactory-unity
BAC_VAR=/var/lib/unity-tests
BAC_UTILISATEUR=unity-tests
etape_unity_bac_a_sable() {
  local racine="${SERVEUR_OVH_DIR:-$HOME/myiafactory/serveur_ovh}" moi d p m f v tmp groupes g n=0
  local droits="$HOME/.config/unity3d/Unity/licenses" ulf="$HOME/.local/share/unity3d/Unity/Unity_lic.ulf"
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : vérifierait que ~/agent-identifiants, ~/.ssh et ~/taches sont en 0700, créerait l'utilisateur système ${BAC_UTILISATEUR} (sans shell ni mot de passe, hors docker, kvm et sudo) et ${BAC_VAR} (0700), déposerait ${BAC_SCRIPT} (root, 0755) et ses entrées, poserait la règle ${BAC_SUDOERS} limitée à ce script (vérifiée par visudo -c) et une ACL de lecture pour ${BAC_UTILISATEUR} sur les seuls fichiers de licence Unity ; le marqueur ~/.myiafactory/unity-bac-a-sable.version n'est écrit que par l'audit J14."
  fi
  refuser_root
  for d in agent-identifiants .ssh taches; do            # d'abord : rien n'est modifié si un dossier privé est lisible
    p="$HOME/$d"
    [ -e "$p" ] || [ -L "$p" ] || continue
    [ -d "$p" ] && [ ! -L "$p" ] || repondre bloque "~/$d n'est pas un dossier (ou est un lien) : à corriger avant que du code de projet tourne sur l'hôte. Rien n'a été modifié."
    m=$(stat -c %a -- "$p" 2>/dev/null)
    [ "$m" = 700 ] || repondre bloque "~/$d est en ${m:-?} : il doit être en 700 (chmod 700 ~/$d) avant que du code de projet tourne sur l'hôte. Rien n'a été modifié."
  done
  moi=$(id -un 2>/dev/null)
  [[ $moi =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || repondre bloque "Nom de l'utilisateur SSH hors motif : règle sudoers impossible. Rien n'a été modifié."
  for f in unity-bac-a-sable.sh sonde-bac-a-sable.sh images/tests/entree-tests.sh images/tests/entree-unity.sh; do
    [ -f "$racine/$f" ] || repondre bloque "Fichier introuvable : $racine/$f. Relancez l'installation (elle redépose les fichiers)."
  done
  v=$(systemctl --version 2>/dev/null | head -n 1 | awk '{ print $2 }')
  [[ $v =~ ^[0-9]{1,4}$ ]] && [ "$v" -ge 247 ] || repondre bloque "systemd ${v:-absent} : la version 247 au moins est exigée (ProtectProc, ProcSubset). Rien n'a été modifié."
  command -v systemd-run >/dev/null 2>&1 || repondre bloque "systemd-run absent. Rien n'a été modifié."
  command -v setfacl >/dev/null 2>&1 || repondre bloque "setfacl absent (paquet acl : sudo apt-get install acl). Rien n'a été modifié."
  sudo -n true >/dev/null 2>&1 || repondre bloque "sudo sans mot de passe indisponible pour ${moi}. Rien n'a été modifié."
  # Utilisateur dédié : système, sans shell de connexion, mot de passe verrouillé, hors des groupes qui ouvrent l'hôte.
  if ! id -u "$BAC_UTILISATEUR" >/dev/null 2>&1; then
    sudo -n useradd --system --user-group --home-dir "$BAC_VAR" --no-create-home --shell /usr/sbin/nologin "$BAC_UTILISATEUR" \
      >/dev/null 2>&1 || repondre bloque "Création de l'utilisateur ${BAC_UTILISATEUR} impossible."
  fi
  groupes=" $(id -nG "$BAC_UTILISATEUR" 2>/dev/null) "
  for g in docker kvm sudo adm lxd; do
    [[ $groupes == *" $g "* ]] && repondre bloque "${BAC_UTILISATEUR} est membre du groupe $g : retirez-le (sudo gpasswd -d ${BAC_UTILISATEUR} $g) puis relancez."
  done
  sudo -n usermod --shell /usr/sbin/nologin "$BAC_UTILISATEUR" >/dev/null 2>&1 &&
    sudo -n passwd --lock "$BAC_UTILISATEUR" >/dev/null 2>&1 ||
    repondre bloque "Shell ou mot de passe de ${BAC_UTILISATEUR} non verrouillés."
  sudo -n install -d -o "$BAC_UTILISATEUR" -g "$BAC_UTILISATEUR" -m 0700 "$BAC_VAR" "$BAC_VAR/campagnes" >/dev/null 2>&1 ||
    repondre bloque "Dossier ${BAC_VAR} non créable."
  sudo -n install -d -o root -g root -m 0755 "$BAC_LIB" >/dev/null 2>&1 || repondre bloque "Dossier ${BAC_LIB} non créable."
  for f in unity-bac-a-sable.sh sonde-bac-a-sable.sh images/tests/entree-tests.sh images/tests/entree-unity.sh; do
    sudo -n install -o root -g root -m 0755 "$racine/$f" "$BAC_LIB/${f##*/}" >/dev/null 2>&1 ||
      repondre bloque "Dépôt de ${BAC_LIB}/${f##*/} impossible."
  done
  # Règle sudoers : le script exact, rien d'autre ; vérifiée seule, puis avec toute la configuration ; retirée si refus.
  tmp=$(mktemp) || repondre bloque "Fichier temporaire non créable pour la règle sudoers."
  printf '%s ALL=(root) NOPASSWD: %s\n' "$moi" "$BAC_SCRIPT" > "$tmp"
  if ! sudo -n visudo -c -q -f "$tmp" >/dev/null 2>&1; then
    rm -f "$tmp"; sudo -n rm -f "$BAC_SUDOERS" >/dev/null 2>&1
    repondre bloque "Règle sudoers refusée par visudo -c : rien n'est posé (règle retirée)."
  fi
  if ! sudo -n install -o root -g root -m 0440 "$tmp" "$BAC_SUDOERS" >/dev/null 2>&1; then
    rm -f "$tmp"; sudo -n rm -f "$BAC_SUDOERS" >/dev/null 2>&1
    repondre bloque "Pose de la règle ${BAC_SUDOERS} impossible (retirée)."
  fi
  rm -f "$tmp"
  if ! sudo -n visudo -c -q >/dev/null 2>&1; then
    sudo -n rm -f "$BAC_SUDOERS" >/dev/null 2>&1
    repondre bloque "Configuration sudo refusée par visudo -c après la pose : règle ${BAC_SUDOERS} retirée."
  fi
  # ACL : lecture pour unity-tests sur les SEULS fichiers de licence (noms seulement, jamais le contenu).
  if [ -d "$droits" ] && [ ! -L "$droits" ]; then
    setfacl -m "u:$BAC_UTILISATEUR:rx" -- "$droits" >/dev/null 2>&1 &&
      setfacl -d -m "u:$BAC_UTILISATEUR:r" -- "$droits" >/dev/null 2>&1 ||
      repondre bloque "ACL de ${BAC_UTILISATEUR} impossible sur ~/.config/unity3d/Unity/licenses (système de fichiers sans ACL ?)."
    for f in "$droits"/* "$droits"/.[!.]*; do            # fichiers ordinaires seulement, jamais un lien ni un dossier
      [ -f "$f" ] && [ ! -L "$f" ] || continue
      setfacl -m "u:$BAC_UTILISATEUR:r" -- "$f" >/dev/null 2>&1 || repondre bloque "ACL de ${BAC_UTILISATEUR} impossible sur un fichier de licence."
      n=$((n + 1))
    done
  fi
  if [ -f "$ulf" ] && [ ! -L "$ulf" ]; then
    setfacl -m "u:$BAC_UTILISATEUR:r" -- "$ulf" >/dev/null 2>&1 || repondre bloque "ACL de ${BAC_UTILISATEUR} impossible sur Unity_lic.ulf."
    n=$((n + 1))
  fi
  [ "$n" -gt 0 ] || repondre a_faire "Bac à sable Unity installé, mais aucune licence Unity sur l'hôte : connectez Unity Hub (session graphique), puis refaites cette étape pour poser l'ACL de lecture de ${BAC_UTILISATEUR}."
  repondre fait "Bac à sable Unity installé : utilisateur ${BAC_UTILISATEUR}, ${BAC_VAR}, ${BAC_SCRIPT}, règle ${BAC_SUDOERS} vérifiée, ACL de lecture sur ${n} fichier(s) de licence. Le marqueur ~/.myiafactory/unity-bac-a-sable.version sera écrit par l'audit J14 seulement."
}

# --- État ------------------------------------------------------------------

etape_etat() {
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : constaterait durcissement, Docker, images et volumes sans rien modifier."
  fi
  local manque=""
  durcissement_fait || manque="$manque durcissement"
  command -v docker >/dev/null 2>&1 || manque="$manque docker"
  if command -v docker >/dev/null 2>&1; then
    local image
    for image in "$V_UNITY" myiafactory/android myiafactory/agent; do
      sudo docker image inspect "$image" >/dev/null 2>&1 || { manque="$manque images"; break; }
    done
    sudo docker volume inspect gradle-cache unity-cache >/dev/null 2>&1 || manque="$manque volumes"
  fi
  if [ -z "$manque" ]; then
    repondre fait "Serveur prêt : durci, Docker, images et volumes en place."
  fi
  repondre a_faire "À faire :${manque}."
}

case "$ETAPE" in
  durcissement) etape_durcissement ;;
  docker) etape_docker ;;
  images) etape_images ;;
  licence) etape_licence ;;
  bureau_distant) etape_bureau_distant ;;
  android_build) etape_android_build ;;
  android_emulateur) etape_android_emulateur ;;
  emulateur_image) etape_emulateur_image ;;
  agent_image) etape_agent_image ;;
  tests_image) etape_tests_image ;;
  tests_android_image) etape_tests_android_image ;;
  unity_cli) etape_unity_cli ;;
  unity_bac_a_sable) etape_unity_bac_a_sable ;;
  etat) etape_etat ;;
esac
