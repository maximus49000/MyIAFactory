"""Catalogue des capacités installables sur un serveur distant générique : données et logique pures (ni SSH ni E/S).

Chaque capacité nomme l'étape distante du script `mise_en_place.sh` qui l'installe (`etape`), ses dépendances et une
sonde SHELL strictement en lecture seule (code 0 = présente). Les étapes `android_build`, `android_emulateur` et
`unity_cli` sont créées par un autre morceau du plan : le catalogue ne fait que les nommer.

`taille_go` et `duree_min` sont des ESTIMATIONS tirées de nos installations réelles (espace disque en Go, durée en minutes),
pas des garanties : elles servent à chiffrer une proposition avant validation.
"""
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Capacite:
    id: str
    libelle: str
    depend: tuple
    etape: str
    sonde: str
    taille_go: float
    duree_min: int
    installable: bool = True
    raison_non_installable: str = ""


CATALOGUE = {
    "base": Capacite(
        "base", "Base du serveur (Docker, outils)", (), "docker",
        "command -v docker >/dev/null", 0.5, 5),
    "durcissement": Capacite(
        "durcissement", "Durcissement SSH (connexion par clé seulement)", ("base",), "durcissement",
        "test -f /etc/ssh/sshd_config.d/00-myiafactory.conf", 0, 2),
    "android-build": Capacite(
        "android-build", "Construction Android (SDK, plateforme 36, Java)", ("base",), "android_build",
        "test -x ~/android-sdk/platform-tools/adb && test -d ~/android-sdk/platforms/android-36 "
        "&& test -d ~/android-sdk/build-tools/36.0.0 && command -v java >/dev/null", 5.4, 10),
    "android-emulateur": Capacite(
        "android-emulateur", "Émulateur Android (KVM)", ("android-build",), "android_emulateur",
        "test -x ~/android-sdk/emulator/emulator && test -d ~/android-sdk/system-images "
        "&& id -nG | grep -qw kvm && test -e /dev/kvm", 2.0, 8),
    "unity": Capacite(
        "unity", "Unity (éditeur en ligne de commande)", ("base",), "unity_cli",
        "ls ~/Unity/Hub/Editor/*/Editor/Unity >/dev/null 2>&1", 24, 25),
    "session-graphique": Capacite(
        "session-graphique", "Session graphique distante (bureau + Unity Hub)", ("base",), "bureau_distant",
        "ss -ltn | grep -q '127.0.0.1:3389' && command -v unityhub >/dev/null", 3, 12,
        installable=False,
        raison_non_installable="installer par `lancer.py plateforme installer --bureau-distant`"),
    "agent": Capacite(
        "agent", "Agent de développement sur le serveur", (), "agent",
        "command -v claude >/dev/null", 1, 5,
        installable=False, raison_non_installable="non installable avant le morceau 3"),
}

BESOINS = {
    "apk": ("android-build",),
    "tests": ("android-build",),
    "lint": ("android-build",),
    "release": ("android-build",),
    "emulateur": ("android-emulateur",),
    "charge": (),
}


def verifier_catalogue(catalogue=None) -> None:
    """Lève `ValueError` pour une dépendance inconnue ou un cycle."""
    catalogue = CATALOGUE if catalogue is None else catalogue
    for cap in catalogue.values():
        for d in cap.depend:
            if d not in catalogue:
                raise ValueError(f"La capacité « {cap.id} » dépend de « {d} », qui n'existe pas au catalogue.")
    etat = {}                                   # 1 = en cours, 2 = terminée

    def visiter(i, chemin):
        if etat.get(i) == 2:
            return
        if etat.get(i) == 1:
            raise ValueError("Cycle de dépendances entre capacités : " + " -> ".join(chemin + [i]))
        etat[i] = 1
        for d in catalogue[i].depend:
            visiter(d, chemin + [i])
        etat[i] = 2

    for i in catalogue:
        visiter(i, [])


def _fermeture(demandees, catalogue):
    """Capacités demandées et leurs dépendances, dépendances d'abord, sans doublon (ordre stable)."""
    verifier_catalogue(catalogue)
    ordre = []

    def visiter(i):
        if i not in catalogue:
            raise ValueError(f"Capacité inconnue : « {i} ». Connues : {', '.join(sorted(catalogue))}.")
        if i in ordre:
            return
        for d in catalogue[i].depend:
            visiter(d)
        ordre.append(i)

    for i in demandees:
        visiter(i)
    return ordre


def ordre_installation(demandees: Iterable[str], installees: set, catalogue=None) -> list:
    """Capacités manquantes, dépendances d'abord. Une capacité non installable reste dans la liste : voir `bloquees`."""
    catalogue = CATALOGUE if catalogue is None else catalogue
    for i in installees:                        # une capacité présente suppose ses dépendances présentes
        if i in catalogue:
            installees = set(installees) | set(_fermeture([i], catalogue))
    return [i for i in _fermeture(list(demandees), catalogue) if i not in installees]


def bloquees(ids: Iterable[str], catalogue=None) -> list:
    """Capacités non installables parmi `ids` et leurs dépendances : `[{"id", "raison"}]`."""
    catalogue = CATALOGUE if catalogue is None else catalogue
    return [{"id": i, "raison": catalogue[i].raison_non_installable}
            for i in _fermeture(list(ids), catalogue) if not catalogue[i].installable]


def manquantes_pour(actions: Iterable[str], installees: set, catalogue=None) -> list:
    """Capacités à installer pour permettre `actions` (via `BESOINS`), dans l'ordre d'installation."""
    requises = []
    for a in actions:
        if a not in BESOINS:
            raise ValueError(f"Action inconnue : « {a} ». Connues : {', '.join(sorted(BESOINS))}.")
        requises.extend(BESOINS[a])
    return ordre_installation(requises, installees, catalogue)
