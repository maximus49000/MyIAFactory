# Image des agents : Node et CLI Claude, par-dessus Ubuntu épinglé (voir serveur_ovh/versions.json).
FROM ubuntu:24.04

ARG NODE_MAJEUR=20

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git python3 \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJEUR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /projet
