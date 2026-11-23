# Image des campagnes de tests (myiafactory/tests) : Python 3.12 de la distribution, Node du majeur épinglé, outils de
# construction, par-dessus Ubuntu épinglé (voir serveur_ovh/versions.json). Ni Claude Code, ni jeton, ni pont, ni client
# réseau : l'image livrée n'a ni curl ni wget (curl ne sert qu'à récupérer le dépôt de Node et est purgé en fin de la même
# couche). Le conteneur tourne sans réseau, racine en lecture seule, sous l'utilisateur 1000 (« ubuntu » de l'image de base),
# HOME=/tmp ; /work et /tmp sont des tmpfs posés par l'enveloppe hôte (taches/lancer_tests.sh).
ARG UBUNTU_TAG=24.04
FROM ubuntu:${UBUNTU_TAG}

ARG NODE_MAJEUR=22

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git python3 bash util-linux tar build-essential \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJEUR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

# Vérifié à la construction : Python 3.12, Node du majeur demandé (avec npm), flock ; aucun client réseau ni sudo.
RUN python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' \
    && node --version | grep -q "^v${NODE_MAJEUR}\." \
    && npm --version >/dev/null \
    && command -v flock >/dev/null \
    && ! command -v curl && ! command -v wget && ! command -v ssh && ! command -v sudo

# Entrée du conteneur : propriétaire root, lecture seule (les tests tournent sous l'utilisateur 1000).
COPY entree-tests.sh /usr/local/bin/entree-tests.sh
RUN chown root:root /usr/local/bin/entree-tests.sh \
    && chmod 0555 /usr/local/bin/entree-tests.sh \
    && install -d -o 1000 -g 1000 -m 0755 /work

ENV HOME=/tmp
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/entree-tests.sh"]
