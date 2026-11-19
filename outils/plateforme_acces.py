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
        "minimaux sur ce seul serveur : GET /dedicated/server/<nom du serveur>, GET /dedicated/server/<nom du serveur>/* "
        "(modèles d'installation et suivi des tâches) et POST /dedicated/server/<nom du serveur>/reinstall ; "
        "indiquez dans « serveur » le nom de ce serveur."
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
    manquants = [c for c in CHAMPS if donnees.get(c) is None or (isinstance(donnees[c], str) and not donnees[c].strip())]
    if manquants:
        raise ErreurAcces(f"{chemin} : champ(s) manquant(s) ou vide(s) : {', '.join(manquants)}. {_mode_operatoire(dossier)}")
    pas_texte = [c for c in CHAMPS if not isinstance(donnees[c], str)]
    if pas_texte:
        raise ErreurAcces(f"{chemin} : champ(s) qui doivent être du texte entre guillemets : {', '.join(pas_texte)}. "
                          f"{_mode_operatoire(dossier)}")
    return {c: donnees[c].strip() for c in CHAMPS}


def chemin_licence(dossier=DOSSIER):
    chemin = Path(dossier) / "unity.ulf"
    return chemin if chemin.is_file() else None


def secrets_licence(texte):
    """Formes à masquer d'une licence multi-ligne : entière, nettoyée, échappée JSON, et chaque ligne ; chaque forme >= 12 caractères."""
    brut = [texte, texte.strip(), texte.replace("\r\n", "\n"), texte.replace("\r\n", "\n").strip()]
    brut += [ligne.strip() for ligne in texte.splitlines() if len(ligne.strip()) >= 12]
    formes = []
    for m in brut:
        if len(m.strip()) >= 12:           # une forme courte ("\n", "x") abîmerait tout texte masqué
            formes += [m, json.dumps(m)[1:-1], json.dumps(m, ensure_ascii=False)[1:-1]]
    return formes


def masquer(texte, secrets):
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        texte = texte.replace(secret, "***")
    return texte
