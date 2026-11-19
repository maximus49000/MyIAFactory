"""Modèle de serveur distant générique et sa configuration `serveurs.json` (dans ~/MyIAFactory, hors dépôt).

Le fichier ne contient JAMAIS de secret : les clés d'API d'un fournisseur restent dans leurs propres fichiers (ex. `ovh.json`).
`cle` est seulement le chemin de la clé privée SSH dédiée. Lecture tolérante (jamais d'exception), écriture atomique.
"""
import json
import os
import re
import subprocess
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import plateforme_ssh
from plateforme_acces import DOSSIER
from plateforme_bureau import _restreindre_windows

FICHIER = "serveurs.json"
FOURNISSEURS = ("ovh", None)
UTILISATEUR_INTERDIT = "root"
MOTS_SECRETS = ("secret", "jeton", "token", "passe", "password", "cle_app", "cle_api", "api_key")


@dataclass(frozen=True)
class Serveur:
    id: str
    nom: str
    hote: str
    utilisateur: str
    cle: str
    fournisseur: "str | None" = None
    reglages_fournisseur: dict = field(default_factory=dict)


def _identifiant(nom):
    """Identifiant déterministe : nom sans accents, minuscules, tout non alphanumérique remplacé par un tiret."""
    brut = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", brut).strip("-")


def _texte(valeur, champ):
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError(f"Le champ « {champ} » du serveur est obligatoire et doit être un texte non vide.")
    return valeur.strip()


def valider(serveur):
    """Contrôle un serveur (dict) et le renvoie sous forme de `Serveur` ; `ValueError` en français sinon.

    Sans `id`, l'identifiant est tiré du nom (voir `_identifiant`)."""
    if not isinstance(serveur, dict):
        raise ValueError("Un serveur doit être décrit par un objet (nom, hote, utilisateur, cle).")
    hote = _texte(serveur.get("hote"), "hote")
    if hote.startswith("-") or any(c.isspace() for c in hote) or "@" in hote:
        raise ValueError("Adresse du serveur invalide : ni espace, ni « @ », ni tiret au début.")
    utilisateur = _texte(serveur.get("utilisateur"), "utilisateur")
    if utilisateur.lower() == UTILISATEUR_INTERDIT or any(c.isspace() for c in utilisateur) \
            or "@" in utilisateur or utilisateur.startswith("-"):
        raise ValueError("Utilisateur refusé : « root », les espaces, « @ » et le tiret initial sont interdits ; "
                         "utilisez un compte dédié non administrateur.")
    cle = _texte(serveur.get("cle"), "cle")
    fournisseur = serveur.get("fournisseur")
    if fournisseur not in FOURNISSEURS:
        raise ValueError("Fournisseur inconnu : seuls « ovh » ou aucun fournisseur sont acceptés.")
    reglages = serveur.get("reglages_fournisseur", {})
    if reglages is None:
        reglages = {}
    if not isinstance(reglages, dict):
        raise ValueError("Les réglages du fournisseur doivent être un objet.")
    if any(isinstance(k, str) and any(m in k.lower() for m in MOTS_SECRETS) for k in reglages):
        raise ValueError("Les réglages du fournisseur ne doivent contenir aucun secret : les clés d'API restent "
                         "dans leurs propres fichiers.")
    nom = serveur.get("nom")
    nom = nom.strip() if isinstance(nom, str) and nom.strip() else hote
    ident = serveur.get("id")
    if ident is None or (isinstance(ident, str) and not ident.strip()):
        ident = _identifiant(nom) or _identifiant(hote)
    ident = _texte(ident, "id")
    return Serveur(ident, nom, hote, utilisateur, cle, fournisseur, dict(reglages))


def lire(dossier=DOSSIER):
    """Serveurs configurés ; liste vide si le fichier est absent ou abîmé, entrées invalides ignorées. Jamais d'exception."""
    try:
        donnees = json.loads((Path(dossier) / FICHIER).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(donnees, list):
        return []
    serveurs = []
    for entree in donnees:
        try:
            serveurs.append(valider(entree))
        except Exception:
            continue
    return serveurs


def _ecrire_atomique(chemin, texte):
    """Temporaire 0600 (O_EXCL) dans le même dossier, écrit puis `os.replace` : jamais de fichier tronqué."""
    for vieux in chemin.parent.glob(f".{chemin.name}.*.tmp"):
        try:
            vieux.unlink()
        except OSError:
            pass
    tmp = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    try:
        _restreindre_windows(tmp)
        with os.fdopen(fd, "wb") as f:
            f.write(texte.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, chemin)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def ecrire(serveurs, dossier=DOSSIER):
    """Enregistre la liste (atomique, droits restreints). Chaque entrée est revalidée : aucun secret ni valeur piégée."""
    contenu = [asdict(valider(asdict(s) if isinstance(s, Serveur) else s)) for s in serveurs]
    Path(dossier).mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(Path(dossier) / FICHIER, json.dumps(contenu, ensure_ascii=False, indent=2) + "\n")


def ajouter(serveur, dossier=DOSSIER):
    """Valide et ajoute un serveur (dict ou `Serveur`) ; refuse un identifiant déjà pris. Renvoie le serveur enregistré."""
    nouveau = valider(asdict(serveur) if isinstance(serveur, Serveur) else serveur)
    existants = lire(dossier)
    if any(s.id == nouveau.id for s in existants):
        raise ValueError(f"Un serveur d'identifiant « {nouveau.id} » existe déjà.")
    ecrire([*existants, nouveau], dossier)
    return nouveau


def ligne_cle_publique(dossier, serveur, runner=subprocess.run):
    """Ligne à coller dans `authorized_keys` du serveur ; la clé dédiée est générée seulement si elle est absente.

    Le dossier de la clé est celui de `serveur.cle` (jamais écrasée : `plateforme_ssh.generer_cle`)."""
    cle = Path(serveur.cle)
    if cle.name != plateforme_ssh.NOM_CLE:
        cle = Path(dossier) / plateforme_ssh.NOM_CLE
    return plateforme_ssh.generer_cle(cle.parent, runner)[1]
