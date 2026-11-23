# Image des campagnes de tests Gradle/Android (myiafactory/tests-android) : myiafactory/tests (Ubuntu, Python 3.12, Node, outils
# de construction, sans curl ni wget, utilisateur 1000) + JDK 17 et JDK 21 de la distribution (paquets Ubuntu signés), rien
# d'autre. Le SDK Android est celui de l'hôte (~/android-sdk), monté en LECTURE SEULE sur /opt/android-sdk par l'enveloppe
# hôte (taches/lancer_tests.sh, famille gradle-android) ; Gradle vient du wrapper du projet (distribution mise en cache à
# l'échauffement) ; GRADLE_USER_HOME est posé par l'enveloppe sur /tmp/gradle
# (inscriptible) ; le cache monté en lecture seule sur /deps n'est lu que par GRADLE_RO_DEP_CACHE. Le conteneur tourne sans réseau, racine en
# lecture seule, sous l'utilisateur 1000, comme myiafactory/tests (entrée et ENTRYPOINT hérités).
FROM myiafactory/tests

USER root
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jdk-headless openjdk-21-jdk-headless \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --set java /usr/lib/jvm/java-17-openjdk-amd64/bin/java \
    && update-alternatives --set javac /usr/lib/jvm/java-17-openjdk-amd64/bin/javac \
    && install -d -m 0755 /opt/android-sdk

# Vérifié à la construction : java par défaut en 17 (21 présent pour les projets qui le demandent), ni curl ni wget.
RUN java -version 2>&1 | grep -q '"17\.' \
    && test -x /usr/lib/jvm/java-21-openjdk-amd64/bin/java \
    && ! command -v curl && ! command -v wget

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    ANDROID_HOME=/opt/android-sdk

USER 1000:1000
WORKDIR /work
