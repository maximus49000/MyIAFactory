# Image des campagnes de tests (myiafactory/tests) : Python 3.12 de la distribution, Node du majeur épinglé, outils de
# construction, par-dessus Ubuntu épinglé (voir serveur_ovh/versions.json). Ni Claude Code, ni jeton, ni pont, ni client
# réseau : l'image livrée n'a ni curl ni wget (curl ne sert qu'à récupérer l'archive de Node et est purgé en fin de la même
# couche). Le conteneur tourne sans réseau, racine en lecture seule, sous l'utilisateur 1000 (« ubuntu » de l'image de base),
# HOME=/tmp ; /work est un montage de l'hôte (~/tests/<id>/travail, sur disque) et /tmp un tmpfs, posés par l'enveloppe
# hôte (taches/lancer_tests.sh).
ARG UBUNTU_TAG=24.04
FROM ubuntu:${UBUNTU_TAG}

ARG NODE_MAJEUR=22

ENV DEBIAN_FRONTEND=noninteractive

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

# JDK 17 : les tests du proxy sortant de l'émulateur (source Java de lancer_emulation.sh) le compilent et le lancent.
# Node : archive officielle de nodejs.org et son SHASUMS256.txt (même répertoire), vérifiée par sha256sum -c (échec de la
# construction sinon) ; jamais de script d installation lu au vol. curl, xz-utils et le reste ne servent qu'ici ; curl est purgé en fin de
# couche. Racine de confiance : TLS vers nodejs.org (pas de vérification de signature GPG).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git python3 python3-venv bash util-linux tar xz-utils build-essential openjdk-17-jdk-headless \
    && mkdir /tmp/node && cd /tmp/node \
    && curl -fsSL -o SHASUMS256.txt "https://nodejs.org/dist/latest-v${NODE_MAJEUR}.x/SHASUMS256.txt" \
    && grep -E "^[0-9a-f]{64}  node-v${NODE_MAJEUR}\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz\$" SHASUMS256.txt > somme.txt \
    && test "$(wc -l < somme.txt)" = 1 \
    && archive="$(cut -d' ' -f3 somme.txt)" \
    && curl -fsSL -o "$archive" "https://nodejs.org/dist/latest-v${NODE_MAJEUR}.x/$archive" \
    && sha256sum -c somme.txt \
    && tar -xJf "$archive" -C /usr/local --strip-components=1 --no-same-owner \
    && rm -f /usr/local/CHANGELOG.md /usr/local/LICENSE /usr/local/README.md \
    && cd / && rm -rf /tmp/node \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

# Vérifié à la construction : Python 3.12 et son venv (l'échauffement pip en crée un : python3-venv, ensurepip), Node du
# majeur demandé (avec npm), flock ; aucun client réseau ni sudo.
RUN python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' \
    && python3 -m venv /tmp/essai-venv && rm -rf /tmp/essai-venv \
    && node --version | grep "^v${NODE_MAJEUR}\." >/dev/null \
    && npm --version >/dev/null \
    && command -v flock >/dev/null \
    && test -x /usr/local/bin/node \
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
