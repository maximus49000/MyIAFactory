"""Exécution déportée : génération du workflow GitHub Actions des actions déportées sur GitHub.

Texte pur, sans bibliothèque YAML (gabarit texte) et déterministe : la même entrée donne le même texte, sans date.
La première ligne porte une empreinte (sha256 du reste) : si le fichier est retouché à la main, l'empreinte ne
correspond plus au corps et le bureau le détecte au lieu d'écraser la modification.

Le cron de GitHub est en UTC : `charge_heure` ("HH:MM") est donc une heure UTC.
Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""
import difflib
import hashlib
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bureau.deport_types import GENERIQUE  # noqa: E402

MARQUEUR = "# généré par MyIAFactory empreinte="
_MOTIF_ENTETE = re.compile(r"^# généré par MyIAFactory empreinte=([0-9a-f]{64})$")
_MOTIF_HEURE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _normaliser(texte):
    return texte.replace("\r\n", "\n").replace("\r", "\n")


def _empreinte(corps):
    return hashlib.sha256(_normaliser(corps).encode("utf-8")).hexdigest()


def _une_ligne(valeur):
    """Un nom sur une seule ligne, sans guillemet : il va entre guillemets doubles dans le YAML."""
    texte = " ".join(str(valeur).split())
    return texte.replace("\\", "").replace('"', "'")


def _bloc_commande(commande):
    """La commande indentée pour un bloc `run: |` : le YAML déduit l'indentation du bloc de sa première ligne,
    qui ne doit donc pas commencer par une espace (commande collée avec une première ligne indentée)."""
    lignes = textwrap.dedent(_normaliser(commande)).split("\n")
    while lignes and not lignes[0].strip():
        lignes.pop(0)
    while lignes and not lignes[-1].strip():
        lignes.pop()
    if lignes:
        lignes[0] = lignes[0].lstrip()
    return "\n".join(("          " + ligne.rstrip()) if ligne.strip() else "" for ligne in lignes)


def _cron(charge_heure):
    trouve = _MOTIF_HEURE.match(str(charge_heure).strip())
    if not trouve:
        raise ValueError("Heure de charge invalide : « %s » (attendu HH:MM)." % (charge_heure,))
    return "%d %d * * *" % (int(trouve.group(2)), int(trouve.group(1)))


def _commande_de(action, commandes, catalogue):
    """La commande donnée par le Directeur pour l'action, sinon celle du catalogue (vide si on ne la connaît pas)."""
    donnee = str(commandes.get(action) or "")
    return donnee if donnee.strip() else str(catalogue[action].get("commande") or "")


def _de_nuit(actions, catalogue):
    """Les jobs qui tournent sur la planification : `charge` et, de proche en proche, les jobs dont elle dépend."""
    if "charge" not in actions:
        return set()
    vus, a_voir = set(), ["charge"]
    while a_voir:
        a = a_voir.pop()
        if a in vus or a not in actions:
            continue
        vus.add(a)
        a_voir.extend(catalogue[a]["consomme"])
    return vus


def _gradle(commande):
    """Vrai si la commande lance le wrapper Gradle du dépôt (`./gradlew …`)."""
    return textwrap.dedent(_normaliser(commande)).strip().startswith("./gradlew")


def _tache(action, commande, deportees, catalogue, sauf_la_nuit=False):
    attend = [dep for dep in catalogue[action]["consomme"] if dep in deportees]
    lignes = ["  %s:" % action, "    runs-on: ubuntu-latest"]
    if sauf_la_nuit:      # la planification ne lance que la charge (et ce dont elle dépend)
        lignes.append("    if: github.event_name != 'schedule'")
    if attend:
        lignes.append("    needs: [%s]" % ", ".join(attend))
    lignes += ["    steps:", "      - uses: actions/checkout@v4"]
    gradle = _gradle(commande)
    if gradle:      # projet Gradle : un JDK 17 (minimum d'AGP récent) ; le SDK Android est préinstallé sur ubuntu-latest
        lignes += ["      - uses: actions/setup-java@v4",
                   "        with:",
                   "          distribution: temurin",
                   "          java-version: '17'"]
    for dep in attend:
        produit = catalogue[dep]["produit"]
        if produit:
            lignes += ["      - uses: actions/download-artifact@v4",
                       "        with:",
                       "          name: %s" % produit,
                       "          path: artefacts/%s" % produit]
    if gradle:      # un dépôt créé sous Windows enregistre gradlew sans le bit exécutable : « Permission denied »
        lignes += ["      - run: chmod +x gradlew"]
    lignes += ["      - name: %s" % action, "        run: |", _bloc_commande(commande)]
    produit, chemin = catalogue[action]["produit"], catalogue[action]["artefact"]
    if produit and chemin:
        lignes += ["      - uses: actions/upload-artifact@v4",
                   "        with:",
                   "          name: %s" % produit,
                   "          path: '%s'" % chemin]
    return "\n".join(lignes)


def generer(nom, actions_github, commandes, charge_heure="03:00", catalogue=GENERIQUE):
    """Texte du workflow pour les actions déportées sur GitHub ; lève ValueError si une commande manque.

    Les actions, leurs commandes par défaut, leurs artefacts et leurs dépendances viennent du `catalogue` du type
    de projet ; une commande donnée dans `commandes` l'emporte sur celle du catalogue. Une tâche par action (sur
    ubuntu-latest) ; une action qui consomme l'artefact d'une action aussi déportée ici l'attend (`needs`) et le
    télécharge. Déclencheurs : `workflow_dispatch` toujours (jamais `push`) ; `schedule` seulement si `charge` est
    déportée (heure UTC), et alors les autres jobs portent `if: github.event_name != 'schedule'`, sauf ceux dont la
    charge dépend.
    """
    actions = []
    for action in actions_github:
        if action not in catalogue:
            raise ValueError("Action inconnue : « %s » (attendu : %s)." % (action, ", ".join(catalogue)))
        if action not in actions:
            actions.append(action)
    commandes = commandes or {}
    for action in actions:
        if not _commande_de(action, commandes, catalogue).strip():
            raise ValueError("Aucune commande pour l'action « %s » : renseignez la commande à lancer." % action)
    # Pas de `push` : un push suivi du déclenchement par l'agent donnerait deux exécutions pour un commit (le quota
    # est limité). Seuls le bouton manuel (`deporter`) et, si la charge est déportée, la planification de nuit.
    corps = ["name: \"%s\"" % (_une_ligne(nom) or "MyIAFactory"),
             "",
             "on:",
             "  workflow_dispatch:"]
    de_nuit = _de_nuit(actions, catalogue)
    if de_nuit:
        corps += ["  schedule:",
                  "    # GitHub lit l'heure en UTC (et non en heure locale).",
                  "    - cron: '%s'" % _cron(charge_heure)]
    corps += ["", "jobs:"]
    corps.append("\n\n".join(_tache(a, _commande_de(a, commandes, catalogue), actions, catalogue,
                                    sauf_la_nuit=bool(de_nuit) and a not in de_nuit) for a in actions))
    texte = _normaliser("\n".join(corps)).rstrip("\n") + "\n"
    return "%s%s\n%s" % (MARQUEUR, _empreinte(texte), texte)


def _separer(contenu):
    """(empreinte annoncée ou None, corps) d'un contenu dont les fins de ligne sont normalisées."""
    contenu = _normaliser(contenu)
    entete, _, corps = contenu.partition("\n")
    trouve = _MOTIF_ENTETE.match(entete)
    return (trouve.group(1) if trouve else None), corps


def etat_du_fichier(chemin, contenu_voulu):
    """"absent", "a_jour", "a_valider" (généré par MyIAFactory mais différent du voulu) ou "modifie_a_la_main"."""
    chemin = Path(chemin)
    return etat_du_contenu(chemin.read_bytes() if chemin.exists() else None, contenu_voulu)


def etat_du_contenu(actuel, contenu_voulu):
    """Comme `etat_du_fichier`, pour un contenu déjà lu (octets ou texte ; `None` : absent)."""
    if actuel is None:
        return "absent"
    if isinstance(actuel, bytes):
        actuel = actuel.decode("utf-8", errors="replace")
    if actuel.startswith("﻿"):
        actuel = actuel[1:]
    empreinte, corps = _separer(actuel)
    if empreinte is None or empreinte != _empreinte(corps):
        return "modifie_a_la_main"
    return "a_jour" if _normaliser(actuel) == _normaliser(contenu_voulu) else "a_valider"


def diff(ancien, nouveau):
    """Diff unifié entre deux textes (vide s'ils sont identiques)."""
    return "".join(difflib.unified_diff(_normaliser(ancien).splitlines(True), _normaliser(nouveau).splitlines(True),
                                        "actuel", "proposé"))
