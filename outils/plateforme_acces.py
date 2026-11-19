"""Accès et secrets de la plateforme (serveur dédié OVH) : lecture de `ovh.json`, licence Unity, masquage.

Les secrets vivent dans ~/MyIAFactory (hors dépôt). Aucun message d'erreur ne reprend une valeur de secret : seuls les
noms de champs et les chemins sont cités.
"""
import json
from pathlib import Path

DOSSIER = Path("~/MyIAFactory").expanduser()
CHAMPS = ("point", "cle_app", "secret", "consommateur", "serveur")
LIEN_JETON = "https://eu.api.ovh.com/createToken/"


class ErreurAcces(Exception):
    pass


def _mode_operatoire(dossier):
    return (
        f"Créez le fichier {Path(dossier) / 'ovh.json'} avec les champs {', '.join(CHAMPS)}. "
        f"Pour obtenir cle_app, secret et consommateur, créez une clé d'API sur {LIEN_JETON} en n'accordant que les droits "
        "minimaux sur ce seul serveur (GET/POST/PUT/DELETE limités à /dedicated/server/<nom du serveur>/*), "
        "et indiquez dans « serveur » le nom de ce serveur."
    )


def charger_ovh(dossier=DOSSIER):
    chemin = Path(dossier) / "ovh.json"
    if not chemin.is_file():
        raise ErreurAcces(f"{chemin} est absent. {_mode_operatoire(dossier)}")
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ErreurAcces(f"{chemin} est illisible (JSON invalide). {_mode_operatoire(dossier)}") from None
    if not isinstance(donnees, dict):
        raise ErreurAcces(f"{chemin} doit contenir un objet JSON. {_mode_operatoire(dossier)}")
    manquants = [c for c in CHAMPS if not str(donnees.get(c) or "").strip()]
    if manquants:
        raise ErreurAcces(f"{chemin} : champ(s) manquant(s) ou vide(s) : {', '.join(manquants)}. {_mode_operatoire(dossier)}")
    return {c: donnees[c] for c in CHAMPS}


def chemin_licence(dossier=DOSSIER):
    chemin = Path(dossier) / "unity.ulf"
    return chemin if chemin.is_file() else None


def masquer(texte, secrets):
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        texte = texte.replace(secret, "***")
    return texte
