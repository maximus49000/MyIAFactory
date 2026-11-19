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
TERMES_SECRETS = ("password", "passwd", "passphrase", "secret", "token", "jeton", "mdp", "apikey", "api_key", "cle_api",
                  "cle_app", "mot_de_passe")      # comparés par segments entiers : « passerelle », « bypass » ne correspondent pas
LONGUEURS_MAX = {"hote": 253, "utilisateur": 64, "id": 64, "nom": 100}
IDENTIFIANT_RESERVE = "migration"      # les routes /api/serveurs/migration/... ne doivent pas se confondre avec /api/serveurs/<id>/...
CARACTERES_HOTE_INTERDITS = set("/:[],")


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
    valeur = valeur.strip()
    if champ in LONGUEURS_MAX and len(valeur) > LONGUEURS_MAX[champ]:
        raise ValueError(f"Le champ « {champ} » est trop long ({LONGUEURS_MAX[champ]} caractères au plus).")
    if any(ord(c) < 32 or ord(c) == 127 for c in valeur):
        raise ValueError(f"Le champ « {champ} » ne doit contenir aucun caractère de contrôle.")
    return valeur


def _contient_secret(valeur):
    """Vrai si une clé (à n'importe quel niveau d'imbrication) porte un nom de secret, par segments entiers."""
    if isinstance(valeur, dict):
        for k, v in valeur.items():
            if isinstance(k, str):
                segments = "_".join(s for s in re.split(r"[^a-z0-9]+", k.lower()) if s)
                if any(f"_{t}_" in f"_{segments}_" for t in TERMES_SECRETS):
                    return True
            if _contient_secret(v):
                return True
    elif isinstance(valeur, list):
        return any(_contient_secret(v) for v in valeur)
    return False


def valider(serveur):
    """Contrôle un serveur (dict) et le renvoie sous forme de `Serveur` ; `ValueError` en français sinon.

    Sans `id`, l'identifiant est tiré du nom (voir `_identifiant`)."""
    if not isinstance(serveur, dict):
        raise ValueError("Un serveur doit être décrit par un objet (nom, hote, utilisateur, cle).")
    hote = _texte(serveur.get("hote"), "hote")
    if hote.startswith("-") or any(c.isspace() or c in CARACTERES_HOTE_INTERDITS for c in hote) or "@" in hote:
        raise ValueError("Adresse du serveur invalide : ni espace, ni « @ », ni « / : [ ] , », ni tiret au début.")
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
    if _contient_secret(reglages):
        raise ValueError("Les réglages du fournisseur ne doivent contenir aucun secret : les clés d'API restent "
                         "dans leurs propres fichiers.")
    nom = serveur.get("nom")
    nom = _texte(nom, "nom") if isinstance(nom, str) and nom.strip() else hote
    ident = serveur.get("id")
    if ident is None or (isinstance(ident, str) and not ident.strip()):
        ident = (_identifiant(nom) or _identifiant(hote))[:LONGUEURS_MAX["id"]].strip("-")
        if not ident:
            raise ValueError("Identifiant impossible à déduire du nom : indiquez-en un.")
    else:
        ident = _identifiant(_texte(ident, "id"))       # forme de slug : sûre comme segment d'URL ou de nom de fichier
        if not ident:
            raise ValueError("Identifiant invalide : il doit contenir au moins une lettre ou un chiffre.")
    if ident == IDENTIFIANT_RESERVE:
        raise ValueError("Ce nom est réservé (il se confondrait avec l'adresse /api/serveurs/migration) : choisissez-en un autre.")
    return Serveur(ident, nom, hote, utilisateur, cle, fournisseur, dict(reglages))


def lire_avec_rejets(dossier=DOSSIER):
    """(serveurs valides, rejets) ; `rejets` : messages français courts, sans valeur secrète, un par entrée refusée ou
    un seul si le fichier est abîmé. Fichier absent : ([], []). Jamais d'exception."""
    chemin = Path(dossier) / FICHIER
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return [], []
    except (OSError, ValueError):
        return [], [f"{FICHIER} est illisible (JSON invalide ou fichier inaccessible)."]
    if not isinstance(donnees, list):
        return [], [f"{FICHIER} doit contenir une liste de serveurs."]
    serveurs, rejets = [], []
    for numero, entree in enumerate(donnees, 1):
        try:
            serveurs.append(valider(entree))
        except Exception as e:
            rejets.append(f"entrée {numero} : {e}" if isinstance(e, ValueError) else f"entrée {numero} : refusée.")
    return serveurs, rejets


def lire(dossier=DOSSIER):
    """Serveurs configurés ; liste vide si le fichier est absent ou abîmé, entrées invalides ignorées. Jamais d'exception."""
    return lire_avec_rejets(dossier)[0]


def ecrire_atomique(chemin, texte):
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


_ecrire_atomique = ecrire_atomique      # ancien nom conservé


def _exiger_fichier_sain(dossier):
    """Refuse de réécrire un `serveurs.json` abîmé ou contenant des entrées refusées : elles seraient perdues. Renvoie les serveurs."""
    existants, rejets = lire_avec_rejets(dossier)
    if rejets:
        raise ValueError(f"{FICHIER} contient {len(rejets)} entrée(s) refusée(s) ou est abîmé : corrigez-le ou supprimez-le "
                         f"avant d'ajouter. Détail : {' '.join(rejets)}")
    return existants


def ecrire(serveurs, dossier=DOSSIER):
    """Enregistre la liste (atomique, droits restreints). Chaque entrée est revalidée : aucun secret ni valeur piégée.

    Refuse (ValueError, fichier intact) si le fichier existant est abîmé ou a des entrées refusées."""
    contenu = [asdict(valider(asdict(s) if isinstance(s, Serveur) else s)) for s in serveurs]
    _exiger_fichier_sain(dossier)
    Path(dossier).mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(Path(dossier) / FICHIER, json.dumps(contenu, ensure_ascii=False, indent=2) + "\n")


def ajouter(serveur, dossier=DOSSIER):
    """Valide et ajoute un serveur (dict ou `Serveur`) ; refuse un identifiant déjà pris et un fichier abîmé.

    Sans `cle`, la clé du serveur est `<dossier>/id_ed25519_<id>`. Renvoie le serveur enregistré."""
    donnees = asdict(serveur) if isinstance(serveur, Serveur) else dict(serveur) if isinstance(serveur, dict) else serveur
    if isinstance(donnees, dict) and not (isinstance(donnees.get("cle"), str) and donnees["cle"].strip()):
        ident = valider({**donnees, "cle": "x"}).id
        donnees["cle"] = str(Path(dossier) / f"id_ed25519_{ident}")
    nouveau = valider(donnees)
    existants = _exiger_fichier_sain(dossier)
    if any(s.id == nouveau.id for s in existants):
        raise ValueError(f"Un serveur d'identifiant « {nouveau.id} » existe déjà.")
    ecrire([*existants, nouveau], dossier)
    return nouveau


def ligne_cle_publique(dossier, serveur, runner=subprocess.run):
    """Ligne à coller dans `authorized_keys` du serveur ; la clé est celle du serveur, à `serveur.cle` (un chemin relatif
    s'entend depuis `dossier`), générée seulement si elle est absente, jamais écrasée."""
    cle = Path(dossier) / serveur.cle       # un chemin absolu l'emporte
    return plateforme_ssh.generer_cle(cle.parent, runner, nom=cle.name)[1]
