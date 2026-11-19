# Image des agents : Node et CLI Claude, par-dessus Ubuntu épinglé (voir serveur_ovh/versions.json).
ARG UBUNTU_TAG=24.04
FROM ubuntu:${UBUNTU_TAG}

ARG NODE_MAJEUR=22
ARG CLAUDE_CODE=2.1.328

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git python3 \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJEUR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE}

WORKDIR /projet
