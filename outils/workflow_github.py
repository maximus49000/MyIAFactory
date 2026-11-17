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

from bureau.deport import ACTIONS  # noqa: E402

MARQUEUR = "# généré par MyIAFactory empreinte="
_MOTIF_ENTETE = re.compile(r"^# généré par MyIAFactory empreinte=([0-9a-f]{64})$")
_MOTIF_HEURE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_ARTEFACT = "apk"
_CHEMIN_APK = "**/build/outputs/apk/**/*.apk"


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


def _tache(action, commande, deportees):
    attend = [dep for dep in ACTIONS[action]["consomme"] if dep in deportees]
    lignes = ["  %s:" % action, "    runs-on: ubuntu-latest"]
    if attend:
        lignes.append("    needs: [%s]" % ", ".join(attend))
    lignes += ["    steps:", "      - uses: actions/checkout@v4"]
    if _ARTEFACT in attend:
        lignes += ["      - uses: actions/download-artifact@v4",
                   "        with:",
                   "          name: %s" % _ARTEFACT,
                   "          path: artefacts/%s" % _ARTEFACT]
    lignes += ["      - name: %s" % action, "        run: |", _bloc_commande(commande)]
    if ACTIONS[action]["produit"] == _ARTEFACT:
        lignes += ["      - uses: actions/upload-artifact@v4",
                   "        with:",
                   "          name: %s" % _ARTEFACT,
                   "          path: '%s'" % _CHEMIN_APK]
    return "\n".join(lignes)


def generer(nom, actions_github, commandes, charge_heure="03:00"):
    """Texte du workflow pour les actions déportées sur GitHub ; lève ValueError si une commande manque.

    Une tâche par action (sur ubuntu-latest) ; une action qui consomme l'APK d'une action aussi déportée ici
    l'attend (`needs`) et le télécharge. `schedule` n'existe que si `charge` est déportée ; son heure est en UTC.
    """
    actions = []
    for action in actions_github:
        if action not in ACTIONS:
            raise ValueError("Action inconnue : « %s » (attendu : %s)." % (action, ", ".join(ACTIONS)))
        if action not in actions:
            actions.append(action)
    commandes = commandes or {}
    for action in actions:
        if not str(commandes.get(action) or "").strip():
            raise ValueError("Aucune commande pour l'action « %s » : renseignez la commande à lancer." % action)
    corps = ["name: \"%s\"" % (_une_ligne(nom) or "MyIAFactory"),
             "",
             "on:",
             "  push:",
             "  workflow_dispatch:"]
    if "charge" in actions:
        corps += ["  schedule:",
                  "    # GitHub lit l'heure en UTC (et non en heure locale).",
                  "    - cron: '%s'" % _cron(charge_heure)]
    corps += ["", "jobs:"]
    corps.append("\n\n".join(_tache(a, commandes[a], actions) for a in actions))
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
    if not chemin.exists():
        return "absent"
    actuel = chemin.read_bytes().decode("utf-8", errors="replace")
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
