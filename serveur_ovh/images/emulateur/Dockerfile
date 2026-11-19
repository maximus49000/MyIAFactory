# Image d'outil de l'émulateur Android (sans fenêtre, KVM) : lance la commande `pont` et rien d'autre.
# Construite sur l'hôte par l'étape emulateur_image de mise_en_place.sh, dans un contexte assemblé par l'étape :
# Dockerfile + entree-tache.sh (ce dossier) + pont.sh (serveur_ovh/taches). Jamais construite par un test.
# SANS identifiants, sans curl ni wget, sans adb ni SDK : le SDK Android de l'hôte (~/android-sdk : emulator, image système,
# platform-tools, cmdline-tools) est monté en LECTURE SEULE sur /opt/android-sdk. adb vient de ce SDK (platform-tools) plutôt
# que du paquet android-tools-adb : même version que l'émulateur (un adb d'une autre version redémarre le serveur adb en boucle).
# L'ENV ci-dessous pose les réglages du pont dans l'image : `docker exec` les retrouve sans que l'appelant n'en transmette aucun.
ARG UBUNTU_TAG=24.04
FROM ubuntu:${UBUNTU_TAG}

ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    ANDROID_AVD_HOME=/avd \
    HOME=/tmp \
    PONT_SORTIE=/sortie \
    PONT_AVD=emul \
    PONT_EMULATEUR=/opt/android-sdk/emulator/emulator \
    PONT_ADB=/opt/android-sdk/platform-tools/adb \
    PATH="/usr/local/bin:/usr/bin:/bin:/opt/android-sdk/cmdline-tools/latest/bin"

# util-linux : flock et setsid ; coreutils : timeout, stat, sleep fractionnaire ; bash >= 4.4 (tableaux vides sous set -u).
# Bibliothèques de l'émulateur : rendu logiciel (swiftshader) et dépendances de qemu même sans fenêtre.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash coreutils util-linux procps ca-certificates openjdk-17-jdk-headless \
        libpulse0 libnss3 libx11-6 libxext6 libxrender1 libxcomposite1 libxcursor1 libxdamage1 libxfixes3 libxi6 libxrandr2 \
        libxtst6 libxkbfile1 libxcb1 libgl1 libasound2t64 libdbus-1-3 libbsd0 libunwind8 \
    && rm -rf /var/lib/apt/lists/*

COPY pont.sh /usr/local/bin/pont
COPY entree-tache.sh /usr/local/bin/entree-tache
# Utilisateur 1000 : celui d'Ubuntu 24.04 (« ubuntu ») s'il existe, créé sinon ; /avd et /tmp sont des volumes mémoire (docker run).
RUN chmod 755 /usr/local/bin/pont /usr/local/bin/entree-tache \
    && { getent passwd 1000 >/dev/null || useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin emul; }

USER 1000:1000
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/entree-tache"]
