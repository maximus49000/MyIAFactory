"""Variables de construction d'un APK Flutter au serveur : l'adresse du service du projet et son jeton, intégrés à l'APK
(`--dart-define`), sans jamais entrer dans un dépôt, un journal, un rapport ou un message.

Le réglage du projet (`variables_construction`, voir `bureau.reglages.normaliser_variables_construction`) dit, par variante
Android, le NOM de chaque variable Dart et sa SOURCE, jamais sa valeur :

    {"client": {"SERVEUR_URL": "service.adresse", "SERVEUR_JETON": "service.jeton"}}

- `service.adresse` : l'adresse du service permanent du projet (le cache du poste, `serveur_service.lire_cache`) ;
- `service.jeton` : le jeton du service, lu dans le coffre du poste (`serveur_service.lire_jeton`) ;
- `valeur:<texte>` : une valeur littérale NON secrète (même jeu de caractères que le script du serveur).

Le poste résout les valeurs au lancement d'une tâche d'agent et en fait le fichier `entree/construction.env` (0600), une ligne
par variable : `<variante|*> <NOM> <valeur>`. Seul `construire-apk` (`serveur_ovh/agent-outils/outil-flutter.sh`) le lit : il
revalide chaque ligne, ajoute les `--dart-define`, masque les valeurs dans sa sortie et vérifie que l'adresse est bien dans
l'APK construit. Une variable dont la source manque (pas d'adresse, pas de jeton) est une construction refusée AVANT tout envoi,
avec un message qui dit quoi régler : jamais un APK livré sans ce qu'il devait contenir.

Limite à connaître : le jeton intégré à l'APK est extractible par quiconque décompile l'application (choix explicite du
Directeur : l'APK Client est distribué à des personnes de confiance). Il n'est jamais dans le dépôt.
"""
import re

import serveur_service

MOTIF_VARIANTE = re.compile(r"^(\*|[a-z][A-Za-z0-9]{0,29})$")
MOTIF_NOM = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
MOTIF_VALEUR = re.compile(r"^[A-Za-z0-9._~:/?#@&+=%-]{1,512}$")        # le même jeu que le script du serveur
SOURCES = ("service.adresse", "service.jeton")
PREFIXE_LITTERAL = "valeur:"
MAX_VARIABLES = 16


class ConstructionRefusee(ValueError):
    """Les variables de construction ne peuvent pas être résolues : le message dit quoi régler (jamais une valeur)."""


def source_valide(source):
    return isinstance(source, str) and (source in SOURCES or (
        source.startswith(PREFIXE_LITTERAL) and bool(MOTIF_VALEUR.fullmatch(source[len(PREFIXE_LITTERAL):]))))


def _adresse_du_service(racine, dossier):
    identifiant = serveur_service.identifiant(racine)
    fiche = serveur_service.lire_cache(dossier).get(identifiant)
    adresse = fiche.get("adresse") if isinstance(fiche, dict) else None
    if not isinstance(adresse, str) or not MOTIF_VALEUR.fullmatch(adresse):
        raise ConstructionRefusee(
            "adresse du service introuvable : déployez le service du projet (il l'écrit au cache du poste), puis relancez.")
    return adresse


def _jeton_du_service(racine, dossier):
    jeton = serveur_service.lire_jeton(serveur_service.identifiant(racine), dossier)
    if not jeton or not MOTIF_VALEUR.fullmatch(jeton):
        raise ConstructionRefusee(
            "jeton du service introuvable au coffre du poste : déployez le service (il le range) ou saisissez-le "
            "(`lancer.py serveur-service jeton`), puis relancez.")
    return jeton


def resoudre(racine, variables, dossier):
    """`{variante: {NOM: valeur}}` d'après le réglage `variables` ({variante: {NOM: source}}). Lève `ConstructionRefusee`
    si une source manque ; la valeur d'un secret n'est jamais dans un message."""
    sortie = {}
    adresse = jeton = None
    for variante, noms in (variables or {}).items():
        for nom, source in noms.items():
            try:
                if source == "service.adresse":
                    adresse = adresse or _adresse_du_service(racine, dossier)
                    valeur = adresse
                elif source == "service.jeton":
                    jeton = jeton or _jeton_du_service(racine, dossier)
                    valeur = jeton
                elif source_valide(source):
                    valeur = source[len(PREFIXE_LITTERAL):]
                else:
                    raise ConstructionRefusee("source inconnue.")
            except ConstructionRefusee as e:
                raise ConstructionRefusee(f"Variable de construction « {nom} » (variante {variante}) : {e}") from None
            sortie.setdefault(variante, {})[nom] = valeur
    return sortie


def contenu_entree(resolu):
    """Le fichier `entree/construction.env` (octets) : une ligne `<variante> <NOM> <valeur>` par variable."""
    lignes = []
    for variante, noms in sorted((resolu or {}).items()):
        for nom, valeur in sorted(noms.items()):
            if not (MOTIF_VARIANTE.fullmatch(variante) and MOTIF_NOM.fullmatch(nom) and MOTIF_VALEUR.fullmatch(valeur)):
                raise ConstructionRefusee(f"Variable de construction « {nom} » : valeur ou nom refusé.")
            lignes.append(f"{variante} {nom} {valeur}")
    if len(lignes) > MAX_VARIABLES:
        raise ConstructionRefusee(f"{MAX_VARIABLES} variables de construction au plus.")
    return ("\n".join(lignes) + "\n").encode("utf-8") if lignes else b""


def valeurs_secretes(variables, resolu):
    """Les valeurs secrètes (celles dont la SOURCE est le jeton du service), à masquer dans toute sortie du poste. L'adresse
    et les valeurs littérales ne sont pas des secrets."""
    return [resolu[variante][nom] for variante, noms in (variables or {}).items() for nom, source in noms.items()
            if source == "service.jeton" and nom in (resolu or {}).get(variante, {})]
