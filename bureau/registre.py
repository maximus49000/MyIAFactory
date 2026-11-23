"""Registre des réglages et résolution à trois niveaux : projet > type > global > défaut (logique pure).

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents. N'importe que `bureau.deport`.
Origine d'une valeur : `defaut`, `global`, `type:<genre>` ou `projet`.
"""

from dataclasses import dataclass

from . import deport

NIVEAUX = ("global", "type", "projet")


@dataclass(frozen=True)
class Reglage:
    id: str
    section: str
    libelle: str
    aide: str
    forme: str          # "booleen" | "lieu" | "choix"
    niveaux: tuple      # sous-ensemble de NIVEAUX où ce réglage peut être posé
    defaut: object
    cle: str            # clé à plat dans le JSON du projet (« lecons_auto »)
    options: tuple = ()    # forme « choix » : les valeurs admises (la première est la plus sûre, le défaut)
    libelles_options: tuple = ()   # leurs libellés, dans le même ordre (affichés par la page)


FORMES = ("booleen", "lieu", "choix")

_TROIS = ("global", "type", "projet")


def _case(id_, libelle, aide, defaut, niveaux=_TROIS):
    return Reglage(id_, "automatisations", libelle, aide, "booleen", niveaux, defaut, id_)


def _choix(id_, section, libelle, aide, options, libelles, niveaux=_TROIS):
    """Un réglage à choix fermé : le défaut est la première option, la plus sûre."""
    return Reglage(id_, section, libelle, aide, "choix", niveaux, options[0], id_, tuple(options), tuple(libelles))


# Signature des APK que construit le serveur (tâche 15e) : un choix de l'utilisateur, jamais codé en dur.
SIGNATURES_APK = ("aucune", "debug_serveur", "poste_signe")


# les réglages à cases sont déclarés ici ; les lieux sont dérivés du catalogue du déport.
# `cloud_dossier_approuve` et `livraison_github` : accord permanent propre au projet, jamais hérité.
REGISTRE = (
    _case("lecons_auto", "Valider les leçons automatiquement",
          "Cochée, chaque leçon proposée est validée d'elle-même au niveau proposé (projet, genre ou skill). Les "
          "leçons genre et skill vont au partage des connaissances (s'il est activé).", False),
    _case("analyse_blocages", "Analyse intelligente des blocages",
          "Cochée, le Chef analyse chaque tâche bloquée par un échec d'agent : il la relance avec une consigne, "
          "confie une correction, ou vous pose la question avec sa recommandation, et en tire une leçon. Il n'ouvre "
          "jamais un outil et ne dépense rien sans vous.", True),
    _case("une_session_moyenne", "Évolution moyenne : une seule session",
          "Cochée, une évolution moyenne (dont vous validez le cahier ensuite) n'a plus de session de tests et de "
          "revue à part : l'agent qui programme relit et teste lui-même. Moins cher et plus court (3 à 7 minutes, "
          "0,12 à 0,17 €), mais sans regard neuf d'un second agent. Décochée : comme avant.", False),
    _case("livraison_sur_demande", "Livrer seulement sur demande",
          "Cochée, l'apk (8 à 14 minutes de construction) ne se fabrique pas tout seul quand le travail est "
          "conforme : il attend « Livrer maintenant » dans l'avis qui s'affiche. Décochée, la livraison part dès que "
          "plus rien n'est en cours.", False),
    _case("cloud_dossier_approuve", "Dossier approuvé pour les sessions cloud",
          "Le moteur répond lui-même « Yes, I trust this folder » quand Claude Code le demande pour lancer une "
          "session cloud dans ce projet.", False, ("projet",)),
    _case("livraison_github", "Livrer automatiquement sur GitHub",
          "Cochée, chaque livrable téléchargeable terminé (apk, zip…) est publié en release GitHub privée du projet "
          "(v121, v122…), sans entrer dans l'historique git ; son lien est rangé dans le livrable. Décochée, rien "
          "n'est publié seul.", False, ("projet",)),
    _choix("signature_apk", "serveur", "Signature des APK construits au serveur",
           "Qui signe l'APK quand un agent du serveur le construit. « Aucune clé ne quitte le poste » (défaut) : APK non "
           "signé ou clé jetable. « Clé de debug copiée au serveur » : le serveur signe avec ~/android-signature/debug.keystore "
           "(montée en lecture seule dans le conteneur de l'agent, seulement avec ce choix). « Le serveur construit, le poste "
           "signe » : la clé de release reste au poste.",
           SIGNATURES_APK, ("Aucune clé ne quitte le poste", "Clé de debug copiée au serveur",
                            "Le serveur construit, le poste signe")),
)


def verifier_valeur(r, valeur):
    """Refuse (ValueError, français) une valeur qui n'a pas la forme du réglage ; `None` (effacer) passe toujours.
    Une forme inconnue est refusée."""
    if valeur is None:
        return
    if r.forme == "booleen":
        if type(valeur) is not bool:
            raise ValueError("« %s » doit valoir vrai ou faux." % r.libelle)
    elif r.forme == "lieu":
        if not isinstance(valeur, str) or valeur not in deport.LIEUX:
            raise ValueError("« %s » doit être un lieu connu (%s)." % (r.libelle, ", ".join(deport.LIEUX)))
    elif r.forme == "choix":
        if not isinstance(valeur, str) or valeur not in r.options:
            raise ValueError("« %s » doit valoir l'un de : %s." % (r.libelle, ", ".join(r.options)))
    else:
        raise ValueError("« %s » : forme de réglage inconnue (« %s »)." % (r.libelle, r.forme))

_ABSENT = object()


def _dict(valeur):
    return valeur if isinstance(valeur, dict) else {}


def _niveau_type(bureau, genre):
    return _dict(_dict(_dict(bureau).get("types")).get(genre)) if genre else {}


def valeur_effective(r, projet, bureau, genre):
    """`(valeur, origine)` d'un réglage : projet, puis type (si le genre est connu), puis global, puis défaut.
    Un niveau que le réglage ne permet pas est ignoré."""
    projet, bureau = _dict(projet), _dict(bureau)
    if "projet" in r.niveaux and r.cle in projet:
        return projet[r.cle], "projet"
    if genre and "type" in r.niveaux:
        valeurs = _dict(_niveau_type(bureau, genre).get("reglages"))
        if r.id in valeurs:
            return valeurs[r.id], "type:" + genre
    if "global" in r.niveaux:
        valeurs = _dict(bureau.get("reglages"))
        if r.id in valeurs:
            return valeurs[r.id], "global"
    return r.defaut, "defaut"


def _lieux_valides(lieux):
    return {a: v for a, v in _dict(lieux).items() if isinstance(v, str) and v in deport.LIEUX}


def lieux_du_type(bureau, genre):
    """Les lieux posés au niveau type dans le fichier du bureau tel qu'il est écrit (`types.<genre>.deport.lieux`),
    `{action: lieu}` ; tout ce qui est abîmé (objet manquant, valeur qui n'est pas un lieu) est ignoré. `{}` sans genre
    ou pour le genre « generique » (pas de niveau type). Pour les outils qui lancent les actions (`deporter`, la
    consigne de départ) : la même lecture que la page Réglages."""
    if not genre or genre == "generique":
        return {}
    gardes = {}
    for action, lieu in _lieux_valides(_dict(_dict(_niveau_type(bureau, genre).get("deport"))).get("lieux")).items():
        try:      # comme `reglages.lire_bureau` : un lieu que le bureau n'accepte pas est écarté
            deport.valider_lieux({action: lieu}, catalogue=deport.catalogue_union())
        except ValueError:
            continue
        gardes[action] = lieu
    return gardes


def lieux_effectifs(catalogue, projet, bureau, genre):
    """Pour chaque action du catalogue, `(lieu, origine)`. L'action au seul serveur (recette sur émulateur) ne prend
    que le niveau projet (sinon `(None, "defaut")`). `bureau["deport"]["lieux"]` est le niveau global tel qu'écrit
    (lieux explicites seulement) ; une action absente n'y est pas réglée."""
    projet, bureau = _dict(projet), _dict(bureau)
    du_projet = _lieux_valides(_dict(projet.get("deport")).get("lieux"))
    du_type = lieux_du_type(bureau, genre)
    global_ = _lieux_valides(_dict(bureau.get("deport")).get("lieux"))
    resultat = {}
    for action, entree in catalogue.items():
        lieu = deport.lieu_effectif(global_, du_projet, action, catalogue, du_type)
        if deport.sans_poste(entree):
            origine = "projet" if lieu is not None else "defaut"
        elif du_projet.get(action) == lieu:
            origine = "projet"
        elif du_type.get(action) == lieu:
            origine = "type:" + genre
        elif global_.get(action) == lieu:
            origine = "global"
        else:
            origine = "defaut"
        resultat[action] = (lieu, origine)
    return resultat
