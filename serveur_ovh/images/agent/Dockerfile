# Image des agents : Node et CLI Claude, par-dessus Ubuntu épinglé (voir serveur_ovh/versions.json).
# L'image livrée n'a ni curl ni wget : curl ne sert qu'à récupérer le dépôt de Node et est purgé en fin de la même couche.
# JDK 17 de la distribution (openjdk-17-jdk-headless, /usr/lib/jvm/java-17-openjdk-amd64) : construire l'APK d'un projet
# Flutter au serveur (Gradle) ; JAVA_HOME n'est posé par l'entrée que pour les projets Flutter.
ARG UBUNTU_TAG=24.04
FROM ubuntu:${UBUNTU_TAG}

ARG NODE_MAJEUR=22
ARG CLAUDE_CODE=2.1.328

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git python3 openjdk-17-jdk-headless \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJEUR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE}

# Entrée de l'agent et client du pont : propriétaire root, lecture seule (l'agent tourne sous l'identifiant de l'hôte).
COPY entree-agent.py /usr/local/bin/entree-agent
COPY pont /usr/local/bin/pont
RUN chown root:root /usr/local/bin/entree-agent /usr/local/bin/pont \
    && chmod 0555 /usr/local/bin/entree-agent /usr/local/bin/pont

WORKDIR /projet
