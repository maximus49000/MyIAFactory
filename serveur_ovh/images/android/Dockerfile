# Image de construction Android : JDK 17, SDK Android, Gradle. Étiquettes épinglées (voir serveur_ovh/versions.json).
ARG UBUNTU_TAG=24.04
FROM ubuntu:${UBUNTU_TAG}

ARG CMDLINE_TOOLS=11076708
ARG BUILD_TOOLS=34.0.0
ARG PLATEFORME=34
ARG GRADLE=8.7

ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    GRADLE_USER_HOME=/cache/gradle
ENV PATH="${PATH}:/opt/gradle/bin:/opt/android-sdk/cmdline-tools/installe/bin:/opt/android-sdk/platform-tools"

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jdk-headless curl unzip git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/gradle.zip "https://services.gradle.org/distributions/gradle-${GRADLE}-bin.zip" \
    && unzip -q /tmp/gradle.zip -d /opt && mv /opt/gradle-${GRADLE} /opt/gradle && rm /tmp/gradle.zip

RUN mkdir -p ${ANDROID_HOME}/cmdline-tools \
    && curl -fsSL -o /tmp/cmd.zip "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
    && unzip -q /tmp/cmd.zip -d ${ANDROID_HOME}/cmdline-tools \
    && mv ${ANDROID_HOME}/cmdline-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/installe \
    && rm /tmp/cmd.zip \
    && yes | sdkmanager --licenses > /dev/null \
    && sdkmanager "platform-tools" "platforms;android-${PLATEFORME}" "build-tools;${BUILD_TOOLS}"

VOLUME /cache/gradle
WORKDIR /projet
