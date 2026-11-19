#!/usr/bin/env bash
# Mise en place du serveur dédié (Ubuntu LTS). Envoyé par SSH (entrée standard) : aucun fichier voisin n'est supposé.
# Usage : mise_en_place.sh --etape <durcissement|docker|images|licence|etat> [--simuler]
# Sortie standard : UN SEUL objet JSON {"etape","statut","detail","versions","disque_libre_go"}.
# Idempotent : chaque étape constate l'état avant d'agir. --simuler n'exécute aucune commande apt/docker/ufw/systemctl.
# La licence Unity (.ulf) arrive par l'entrée standard (stdin), jamais en argument, et n'est jamais réaffichée.
set -u

# Étiquettes épinglées (miroir de serveur_ovh/versions.json ; aucune étiquette sans étiquette flottante).
V_UNITY="unityci/editor:ubuntu-2022.3.45f1-base-3.1.0"
V_UBUNTU="ubuntu:24.04"
V_BUILD_TOOLS="34.0.0"
SEUIL_DISQUE_GO=20
DOSSIER_IMAGES="${SERVEUR_OVH_DIR:-/opt/myiafactory/serveur_ovh}/images"

ETAPE=""
SIMULER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --etape) ETAPE="${2:-}"; shift 2 ;;
    --simuler) SIMULER=1; shift ;;
    *) echo "Argument inconnu : $1" >&2; exit 2 ;;
  esac
done
case "$ETAPE" in
  durcissement|docker|images|licence|etat) ;;
  *) echo "Étape inconnue ou absente : '$ETAPE'" >&2; exit 2 ;;
esac

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
verifier_seconde_session() {
  local tmp cle ok=1
  tmp=$(mktemp -d) || return 1
  cle="$tmp/cle"
  ssh-keygen -q -t ed25519 -N "" -C "myiafactory-verif" -f "$cle" || { rm -rf "$tmp"; return 1; }
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  cat "$cle.pub" >> "$HOME/.ssh/authorized_keys"
  if ssh -i "$cle" -o BatchMode=yes -o PasswordAuthentication=no -o IdentitiesOnly=yes \
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
  if ! verifier_seconde_session; then
    repondre bloque "Seconde session SSH par clé impossible : mot de passe et pare-feu laissés intacts pour ne pas vous enfermer dehors."
  fi
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' | sudo tee /etc/ssh/sshd_config.d/00-myiafactory.conf >/dev/null
  if ! sudo sshd -t; then
    sudo rm -f /etc/ssh/sshd_config.d/00-myiafactory.conf
    repondre bloque "Configuration sshd invalide : retour en arrière, mot de passe conservé."
  fi
  sudo systemctl reload ssh >/dev/null 2>&1 || sudo systemctl reload sshd >/dev/null 2>&1
  sudo ufw limit 22/tcp >/dev/null 2>&1
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
  for nom in android agent; do
    if ! sudo docker image inspect "myiafactory/$nom" >/dev/null 2>&1; then
      libre=$(disque_libre_go)
      [ "$libre" -ge "$SEUIL_DISQUE_GO" ] || repondre bloque "Disque presque plein en cours de route : ${libre} Go libres."
      sudo docker build -t "myiafactory/$nom" "$DOSSIER_IMAGES/$nom" >/dev/null 2>&1 \
        || repondre bloque "Construction de l'image $nom impossible (dossier ${DOSSIER_IMAGES}/$nom)."
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
  if printf '%s' "$licence" | sudo docker run --rm -i -v unity-cache:/root/.local/share/unity3d "$V_UNITY" \
       bash -c 'mkdir -p /root/.local/share/unity3d/Unity && cat > /root/.local/share/unity3d/Unity/Unity_lic.ulf && unity-editor -batchmode -nographics -quit -logFile - >/dev/null 2>&1' ; then
    repondre fait "Licence Unity activée dans un conteneur de test."
  fi
  repondre bloque "Activation de la licence Unity refusée dans le conteneur de test."
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
    sudo docker image inspect "$V_UNITY" >/dev/null 2>&1 || manque="$manque images"
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
