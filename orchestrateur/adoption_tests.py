"""Adoption des tests au serveur : les décisions de Direction et leurs réponses (conception § 5.15, tâche 15b).

`outil.py evaluer-tests-serveur` lance l'évaluation (`outils/tests_adoption.py`), écrit `tests.adoption` dans les réglages du
projet et pose UNE décision de projet selon le verdict. La réponse du Directeur (demande `tests_serveur`) revient à la même
commande (`decision`, `verdict`). Jamais d'activation automatique : seule la réponse `activer` règle l'action « tests » du
projet sur le serveur. Aucune construction d'image ici : `construire` est une information pour le contrôleur ou le bureau.
"""
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
GENRES = ("tests_serveur_adoption", "tests_image_derivee", "tests_reseau_echauffement", "tests_profil")
REPONSES_ADOPTION = {"passe": ("activer", "plus_tard"), "echoue": ("marquer", "garder_poste", "plus_tard"),
                     "non_deportable": ("garder_poste",), "injoignable": ("reessayer", "garder_poste"),
                     "trop_long": ("reessayer", "garder_poste")}
REPONSES = {"tests_image_derivee": ("construire", "plus_tard", "garder_poste"),
            "tests_reseau_echauffement": ("accorder", "refuser"),
            "tests_profil": ("reevaluer", "plus_tard")}
MAX_CHARGE_OCTETS = 24000


def reponses_de(genre, charge):
    """Les réponses admises à une décision de ce genre (celles de `tests_serveur_adoption` dépendent du statut)."""
    if genre == "tests_serveur_adoption":
        return REPONSES_ADOPTION.get((charge or {}).get("statut"), ())
    return REPONSES.get(genre, ())


def verifier_charge(genre, texte, charge, reponses=None):
    """Message d'erreur, ou None : la charge est un objet JSON borné, les réponses sont celles du genre."""
    if genre not in GENRES:
        return f"genre inconnu « {genre} »."
    if not isinstance(charge, dict):
        return "« charge » est un objet."
    try:
        if len(json.dumps(charge, ensure_ascii=False)) > MAX_CHARGE_OCTETS:
            return f"« charge » dépasse {MAX_CHARGE_OCTETS} caractères."
    except (TypeError, ValueError):
        return "« charge » n'est pas du JSON."
    if reponses is not None and tuple(reponses) != tuple(reponses_de(genre, charge)):
        return "« reponses » n'est pas la liste de ce genre de décision."
    return None


def decision_pour(resultat) -> dict:
    """La décision à poser pour ce verdict d'évaluation : `{genre, texte, charge}` ; `{}` quand il n'y a rien à décider
    (l'information est dans le résultat : pile sans commande, serveur à préparer)."""
    statut, attend = resultat.get("statut"), resultat.get("attend")
    base = {"statut": statut, "image": resultat.get("image"), "duree_s": resultat.get("duree_s"),
            "nb_tests": resultat.get("nb_tests"), "raison": resultat.get("raison")}
    if statut == "image_a_construire":
        if attend == "image":
            d = resultat.get("decision") or {}
            return {"genre": "tests_image_derivee",
                    "texte": "Les tests de ce projet demandent une image au serveur qui n'existe pas encore. Elle se construit au "
                             f"serveur (environ {d.get('duree_estimee_s', '?')} s, {d.get('taille_estimee_mo', '?')} Mo) avec le "
                             "Dockerfile ci-dessous : lisez-le avant de répondre.",
                    "charge": {**base, **{k: d.get(k) for k in ("dockerfile", "sha256", "etiquette", "taille_estimee_mo",
                                                                 "duree_estimee_s")}}}
        if attend == "reseau":
            return {"genre": "tests_reseau_echauffement",
                    "texte": "Pour préparer les dépendances des tests, le serveur doit ouvrir le réseau vers les registres du "
                             "projet pendant la préparation. Le code de construction du projet tourne avec ce réseau.",
                    "charge": base}
        return {}
    texte = {"passe": "Les tests du projet passent au serveur : activer les tests sur le serveur ?",
             "echoue": "Des tests échouent au serveur (voir les premiers échecs et leur classe).",
             "non_deportable": "Ce projet ne peut pas tester au serveur : " + str(resultat.get("raison") or ""),
             "injoignable": "Le serveur n'a pas pu mener l'évaluation : " + str(resultat.get("raison") or ""),
             "trop_long": "L'évaluation a dépassé la durée de la famille : " + str(resultat.get("raison") or "")}.get(statut)
    if texte is None:
        return {}
    charge = dict(base, empreinte_profil=resultat.get("empreinte_profil"))
    if statut == "echoue":
        charge.update(echecs=resultat.get("echecs") or [], marqueur=resultat.get("marqueur"))
    return {"genre": "tests_serveur_adoption", "texte": texte, "charge": charge}


def _lire_reglages(fichier):
    chemin = Path(fichier)
    donnees = json.loads(chemin.read_text(encoding="utf-8-sig")) if chemin.exists() else {}
    if not isinstance(donnees, dict):
        raise ValueError("réglages illisibles")
    return donnees


def activer(fichier_reglages, racine):
    """Règle l'action « tests » du projet sur le serveur (accord R10), les autres réglages du déport gardés. Seule la réponse
    `activer` du Directeur l'appelle."""
    sys.path.insert(0, str(RACINE))
    from bureau import deport_types, reglages
    donnees = _lire_reglages(fichier_reglages)
    deport = donnees.get("deport") if isinstance(donnees.get("deport"), dict) else {}
    lieux = dict(deport.get("lieux") or {})
    lieux["tests"] = "serveur"
    nouveau = {k: v for k, v in deport.items() if k != "lieux"}
    nouveau["lieux"] = lieux
    catalogue = deport_types.catalogue_du_projet(str(racine))[1]
    reglages.fixer_deport(Path(fichier_reglages), nouveau, catalogue)


def noter_reseau(fichier_reglages, accorde):
    """`tests.adoption.reseau_echauffement` : `accorde` ou `refuse` (la réponse du Directeur)."""
    donnees = _lire_reglages(fichier_reglages)
    tests = donnees.get("tests") if isinstance(donnees.get("tests"), dict) else {}
    adoption = tests.get("adoption") if isinstance(tests.get("adoption"), dict) else {}
    adoption["reseau_echauffement"] = "accorde" if accorde else "refuse"
    tests["adoption"] = adoption
    donnees["tests"] = tests
    tmp = Path(str(fichier_reglages) + ".reseau.tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, fichier_reglages)


def reponse(genre, verdict, charge, fichier_reglages, racine) -> dict:
    """Applique la réponse du Directeur ; rend `{"fait": texte, "suite": None | "evaluer" | "construire" | "marquer"}`."""
    if verdict == "plus_tard":
        return {"fait": "Rien ne change ; la question reviendra à la prochaine évaluation.", "suite": None}
    if verdict == "garder_poste":
        return {"fait": "Les tests restent sur le poste.", "suite": None}
    if genre == "tests_serveur_adoption":
        if verdict == "activer":
            activer(fichier_reglages, racine)
            return {"fait": "Les tests de ce projet partent désormais au serveur (réglage « tests » : serveur).", "suite": None}
        if verdict == "marquer":
            return {"fait": "Marquage proposé : à créer comme tâche, jamais appliqué seul.", "suite": "marquer",
                    "marqueur": charge.get("marqueur"), "echecs": charge.get("echecs") or []}
        if verdict == "reessayer":
            return {"fait": "Nouvelle évaluation demandée.", "suite": "evaluer"}
    if genre == "tests_image_derivee" and verdict == "construire":
        return {"fait": "Construction de l'image demandée : le contrôleur ou le bureau la lance (construire_image_tests.sh), "
                        "jamais un agent. L'évaluation reprendra ensuite.", "suite": "construire"}
    if genre == "tests_reseau_echauffement":
        noter_reseau(fichier_reglages, verdict == "accorder")
        if verdict == "accorder":
            return {"fait": "Réseau d'échauffement accordé.", "suite": "evaluer"}
        return {"fait": "Réseau d'échauffement refusé : les tests restent sur le poste.", "suite": None}
    if genre == "tests_profil" and verdict == "reevaluer":
        return {"fait": "Nouvelle évaluation demandée.", "suite": "evaluer"}
    raise ValueError(f"réponse « {verdict} » inconnue pour « {genre} »")
