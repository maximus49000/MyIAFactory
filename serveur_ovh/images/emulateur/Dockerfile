# Image d'outil de l'émulateur Android (sans fenêtre, KVM) : lance la commande `pont` et rien d'autre.
# Construite sur l'hôte par l'étape emulateur_image de mise_en_place.sh, dans un contexte assemblé par l'étape :
# Dockerfile + entree-tache.sh (ce dossier) + pont.sh (serveur_ovh/taches). Jamais construite par un test.
# SANS identifiants, et l'image LIVRÉE sans curl ni wget ni unzip : le SDK Android de l'hôte (~/android-sdk : emulator, image
# système, platform-tools) est monté en LECTURE SEULE sur /opt/android-sdk. adb vient de ce SDK (platform-tools) plutôt que
# du paquet android-tools-adb : même version que l'émulateur (un adb d'une autre version redémarre le serveur adb en boucle).
# Les OUTILS EN LIGNE DE COMMANDE Android (avdmanager) viennent de l'image elle-même : le SDK de l'hôte n'en a pas (l'étape
# android_build ne les garde pas). Version épinglée PROPRE à cette image (emulateur_cmdline_tools de versions.json, 16111833 =
# cmdline-tools 23.0 : la 11076708 (12.0) de l'image android ne lit pas le package.xml en XML v4 de l'image système de l'hôte et
# échoue « AVD not created », constaté sur le serveur ; 23.0 crée l'AVD sans avertissement sur JDK 17),
# téléchargée À LA CONSTRUCTION dans une étape séparée « outils » : archive vérifiée contre le SHA-1 du manifeste officiel
# Google (même discipline que installer_cmdline_tools de mise_en_place.sh), échec de la construction sinon ; seule l'arborescence
# extraite passe dans l'image livrée (environ 180 Mo de plus). La valeur réelle est passée par l'étape (--build-arg).
# Disposition : /opt/sdk-tache/cmdline-tools/latest (vrai dossier) + liens /opt/sdk-tache/{emulator,platform-tools,platforms,
# system-images,licenses,build-tools} -> /opt/android-sdk/... : avdmanager déduit la racine du SDK de sa propre place
# (<racine>/cmdline-tools/latest) et y trouve l'image système montée de l'hôte.
# L'ENV ci-dessous pose les réglages du pont dans l'image : `docker exec` les retrouve sans que l'appelant n'en transmette aucun.
ARG UBUNTU_TAG=24.04

FROM ubuntu:${UBUNTU_TAG} AS outils
ARG CMDLINE_TOOLS=16111833
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*
# Le manifeste officiel donne le SHA-1 de l'archive épinglée (commandlinetools-linux-<N>_latest.zip) ; téléchargement dans un
# fichier (jamais « curl | sh »), vérification, extraction, contrôle de avdmanager, puis rien ne reste dans /tmp.
RUN set -eu; \
    archive="commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip"; \
    curl -fsSL -o /tmp/manifeste.xml "https://dl.google.com/android/repository/repository2-3.xml"; \
    attendu=$(tr -d '\r\n' < /tmp/manifeste.xml \
      | grep -oE "<checksum type=\"sha1\">[0-9a-fA-F]{40}</checksum> *<url>${archive}</url>" \
      | head -n 1 | sed -E 's/.*type="sha1">([0-9a-fA-F]{40})<.*/\1/' | tr 'A-F' 'a-f'); \
    [ -n "$attendu" ] || { echo "Archive ${archive} absente du manifeste officiel Google : construction refusée." >&2; exit 1; }; \
    curl -fsSL -o /tmp/outils.zip "https://dl.google.com/android/repository/${archive}"; \
    obtenu=$(sha1sum /tmp/outils.zip | cut -d' ' -f1); \
    [ "$obtenu" = "$attendu" ] || { echo "SHA-1 de ${archive} inattendu (${obtenu} au lieu de ${attendu}) : construction refusée." >&2; exit 1; }; \
    mkdir -p /tmp/extrait /opt/sdk-tache/cmdline-tools; \
    unzip -q /tmp/outils.zip -d /tmp/extrait; \
    [ -x /tmp/extrait/cmdline-tools/bin/avdmanager ] || { echo "avdmanager absent de ${archive}." >&2; exit 1; }; \
    mv /tmp/extrait/cmdline-tools /opt/sdk-tache/cmdline-tools/latest; \
    rm -rf /tmp/outils.zip /tmp/manifeste.xml /tmp/extrait

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
    PATH="/usr/local/bin:/usr/bin:/bin:/opt/sdk-tache/cmdline-tools/latest/bin"

# util-linux : flock et setsid ; coreutils : timeout, stat, sleep fractionnaire ; bash >= 4.4 (tableaux vides sous set -u).
# openjdk-17 : avdmanager (outils 16111833 = version 23.0, essayés sur JDK 17 sur le serveur). Bibliothèques de l'émulateur : rendu logiciel
# (swiftshader) et dépendances de qemu même sans fenêtre.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash coreutils util-linux procps ca-certificates openjdk-17-jdk-headless \
        libpulse0 libnss3 libx11-6 libxext6 libxrender1 libxcomposite1 libxcursor1 libxdamage1 libxfixes3 libxi6 libxrandr2 \
        libxtst6 libxkbfile1 libxcb1 libgl1 libasound2t64 libdbus-1-3 libbsd0 libunwind8 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=outils /opt/sdk-tache /opt/sdk-tache
COPY pont.sh /usr/local/bin/pont
COPY entree-tache.sh /usr/local/bin/entree-tache
# Liens vers le SDK monté de l'hôte (pendants à la construction, résolus à l'exécution) ; outils lisibles par l'utilisateur
# 1000 (celui d'Ubuntu 24.04, « ubuntu », s'il existe, créé sinon) ; /avd et /tmp sont des volumes mémoire (docker run).
RUN chmod -R a+rX /opt/sdk-tache \
    && for d in emulator platform-tools platforms system-images licenses build-tools; do ln -s "/opt/android-sdk/$d" "/opt/sdk-tache/$d"; done \
    && chmod 755 /usr/local/bin/pont /usr/local/bin/entree-tache \
    && { getent passwd 1000 >/dev/null || useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin emul; }

USER 1000:1000
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/entree-tache"]
