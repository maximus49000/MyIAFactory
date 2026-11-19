#!/usr/bin/env bash
# Mise en place du serveur dédié (Ubuntu LTS). Le contrôleur dépose d'abord ce script dans un fichier du serveur, puis lance
# `bash <fichier> --etape X`.
# Contrat d'entrée standard : SEULE l'étape licence lit stdin (la licence). Pour toutes les autres, stdin est fermé
# (/dev/null) afin qu'aucune commande (ssh, apt, docker...) ne puisse consommer ce que l'appelant envoie.
# Usage : mise_en_place.sh --etape <durcissement|docker|images|licence|etat> [--simuler]
# Sortie standard : UN SEUL objet JSON {"etape","statut","detail","versions","disque_libre_go"}.
# Idempotent : chaque étape constate l'état avant d'agir. --simuler n'exécute aucune commande apt/docker/ufw/systemctl.
# La licence Unity (.ulf) arrive par l'entrée standard (stdin), jamais en argument, et n'est jamais réaffichée.
set -u

# Étiquettes épinglées (miroir de serveur_ovh/versions.json ; aucune étiquette sans étiquette flottante).
V_UNITY="unityci/editor:ubuntu-6000.6.7f1-android-4.0.0"
V_UBUNTU="ubuntu:24.04"
V_BUILD_TOOLS="34.0.0"
V_PLATEFORME="34"
V_CMDLINE_TOOLS="11076708"
V_GRADLE="8.7"
V_NODE="22"
V_CLAUDE_CODE="2.1.328"
# Étiquette collée aux images construites : si elle diffère des valeurs épinglées, l'image est reconstruite.
EMPREINTE_ANDROID="ubuntu=${V_UBUNTU};build_tools=${V_BUILD_TOOLS};plateforme=${V_PLATEFORME};cmdline_tools=${V_CMDLINE_TOOLS};gradle=${V_GRADLE}"
EMPREINTE_AGENT="ubuntu=${V_UBUNTU};node=${V_NODE};claude_code=${V_CLAUDE_CODE}"
SEUIL_DISQUE_GO=20
DOSSIER_IMAGES="${SERVEUR_OVH_DIR:-/opt/myiafactory/serveur_ovh}/images"

ETAPE=""
SIMULER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --etape)
      [ $# -ge 2 ] || { echo "L'option --etape attend une valeur (durcissement, docker, images, licence ou etat)." >&2; exit 2; }
      ETAPE="$2"; shift 2 ;;
    --simuler) SIMULER=1; shift ;;
    *) echo "Argument inconnu : $1" >&2; exit 2 ;;
  esac
done
case "$ETAPE" in
  durcissement|docker|images|licence|etat) ;;
  *) echo "Étape inconnue ou absente : '$ETAPE'" >&2; exit 2 ;;
esac

# Seule l'étape licence lit stdin ; ailleurs il est fermé.
if [ "$ETAPE" != "licence" ]; then
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
    && sudo ufw status 2>/dev/null | grep -q '^Status: active' \
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

etape_docker() {
  if [ "$SIMULER" = 1 ]; then
    repondre a_faire "Simulation : ajouterait le dépôt officiel Docker, installerait docker-ce puis lancerait docker run hello-world."
  fi
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
    # Image absente ou construite avec d'autres versions : on la reconstruit.
    if [ "$actuelle" != "$empreinte" ]; then
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
  etat) etape_etat ;;
esac
