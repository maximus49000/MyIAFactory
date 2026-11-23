"""Adoption des tests au serveur par projet (conception § 5.15, tâche 15b) : analyse, profil, image, échauffement, évaluation.

Pour tout projet : `evaluer` suit la chaîne analyse -> profil -> image -> réseau d'échauffement -> UNE campagne
d'évaluation par la route (`tests_serveur.executer(forcer=True, evaluation=True)`), sans repli au poste ni nouvelle
tentative, et rend un verdict (`passe`, `echoue`, `image_a_construire`, `non_deportable`, `injoignable`, `trop_long`).
Ce module ne construit jamais d'image (le contrôleur ou le bureau le font, `construire_image_tests.sh`), n'active jamais
rien (R10 : l'activation est la réponse du Directeur) et n'écrit `tests.adoption` que par `noter_adoption`, appelée par
l'outil du bureau, jamais par un agent. Python 3.12, bibliothèque standard.
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

import tests_images  # noqa: E402
import tests_profil  # noqa: E402
import tests_serveur  # noqa: E402

STATUTS = ("passe", "echoue", "image_a_construire", "non_deportable", "injoignable", "trop_long")
ETAPES = ("image", "sdk_android", "reseau", "echauffement", "evaluation")
MAX_ECHECS = 20
EXTRAIT_MAX = 4096
SORTIE_MAX = 65536

# Le marqueur conseillé par pile pour un test qui ne peut pas tourner sous Linux (§ 5.9) : une indication, jamais appliquée seule.
MARQUEURS = {
    "python": "plateforme_tests.windows_seulement",
    "gradle-android": "Assume.assumeTrue (JUnit 4) ou @EnabledOnOs(OS.WINDOWS) (JUnit 5)",
    "gradle-jvm": "Assume.assumeTrue (JUnit 4) ou @EnabledOnOs(OS.WINDOWS) (JUnit 5)",
    "maven": "Assume.assumeTrue (JUnit 4) ou @EnabledOnOs(OS.WINDOWS) (JUnit 5)",
    "node": "it.skipIf(process.platform === 'win32') (Vitest)",
    "dotnet": "[SkippableFact] avec Skip.IfNot(OperatingSystem.IsWindows())",
    "rust": "#[cfg(windows)]",
    "go": "t.Skip(\"Windows seulement\")",
}
MARQUEUR_DEFAUT = "le marqueur « Windows seulement » de la pile du projet"


def marqueur_pour(famille) -> str:
    return MARQUEURS.get(famille, MARQUEUR_DEFAUT)


_WINDOWS = re.compile(r"[A-Za-z]:\\|\\\\|\bHKEY_|\bwinreg\b|\.exe\b|\bcmd(\.exe)?\b|\bWindowsError\b", re.IGNORECASE)
_RESEAU = re.compile(r"ConnectionError|ConnectionRefused|Connection refused|Name or service not known|getaddrinfo|"
                     r"UnknownHostException|ECONNREFUSED|ENOTFOUND|Temporary failure in name resolution|"
                     r"Network is unreachable|timed out connecting|SSLError|socket\.gaierror", re.IGNORECASE)
_SECRET = re.compile(r"\bKeyError: ['\"][A-Z0-9_]{3,}['\"]|\b(API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIALS?)\b.{0,40}"
                     r"(not set|missing|manquant|absent|undefined|is required)|(missing|manquant|absent).{0,40}"
                     r"\b(API_KEY|SECRET|TOKEN|PASSWORD)\b|401 Unauthorized|403 Forbidden", re.IGNORECASE)


def classer_echec(nom, extrait) -> str:
    """`windows`, `reseau`, `secret` ou `autre` d'après le nom du test et 4 Ko d'extrait au plus ; pur."""
    texte = f"{nom}\n{str(extrait or '')[:EXTRAIT_MAX]}"
    if _WINDOWS.search(texte):
        return "windows"
    if _RESEAU.search(texte):
        return "reseau"
    if _SECRET.search(texte):
        return "secret"
    return "autre"


def etapes(racine, profil, etat) -> List[str]:
    """Ce qui reste à faire pour adopter ce projet, dans l'ordre ; pur. `etat` : `{"image": bool (l'image du profil est
    là), "sdk_android": bool, "reseau": bool (échauffement accordé ou inutile), "echauffement": bool, "evaluation": bool}`
    (une clé absente vaut « pas fait »)."""
    if profil.non_deportable:
        return []
    voulues = ["image"]
    if "gradle-android" in profil.familles:
        voulues.append("sdk_android")
    cle = tests_profil.cle_echauffement(profil)
    if cle is not None:
        if tests_profil.ECHAUFFEMENTS[cle]["execute_du_code"]:
            voulues.append("reseau")
        voulues.append("echauffement")
    voulues.append("evaluation")
    return [e for e in voulues if not (etat or {}).get(e)]


# --- campagne d'évaluation ------------------------------------------------------------------------------------------

class _Collecteur:
    """Reçoit la sortie d'une campagne (octets) et n'en garde que la fin."""

    def __init__(self):
        self.fin = b""

    def write(self, b):
        self.fin = (self.fin + bytes(b))[-SORTIE_MAX:]

    def flush(self):
        pass

    def texte(self):
        return self.fin.decode("utf-8", "replace")


_ECHEC = (re.compile(r"^(?:FAIL|ERROR): (\S.*)$"),                      # unittest
          re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)"),                  # pytest
          re.compile(r"^(\S.* > \S.*) FAILED$"),                        # Gradle
          re.compile(r"^\s*(?:✗|×|FAIL)\s+(\S.*)$"),                    # vitest / jest
          re.compile(r"^\s*(?:Failed|Échec)\s+(\S+)", re.IGNORECASE))    # dotnet


def extraire_echecs(texte) -> List[dict]:
    """Les 20 premiers tests en échec lus dans la fin de la sortie, `{"nom", "classe"}` ; sans doublon."""
    lignes = str(texte or "").splitlines()
    sortie, vus = [], set()
    for i, ligne in enumerate(lignes):
        for motif in _ECHEC:
            m = motif.match(ligne.rstrip())
            if m:
                nom = m.group(1).strip()[:200]
                if nom not in vus:
                    vus.add(nom)
                    extrait = "\n".join(lignes[i + 1:i + 40])[:EXTRAIT_MAX]
                    sortie.append({"nom": nom, "classe": classer_echec(nom, extrait)})
                break
        if len(sortie) >= MAX_ECHECS:
            break
    return sortie


def _nb_tests(texte):
    try:
        return tests_serveur._tests_mesures().nb_tests_de(texte)
    except Exception:  # noqa: BLE001
        return None


def route_par_defaut(commande, racine, delai_s, accord=None):
    """Une campagne d'évaluation par la route : jamais de repli au poste (`forcer`), aucune ligne de mesure ordinaire
    (`evaluation`). Rend `{"code", "sortie", "messages"}`. `accord` : voir `evaluer`."""
    sortie, erreur, messages = _Collecteur(), _Collecteur(), []
    code = tests_serveur.executer(
        list(commande), dossier=racine, attendre=True, forcer=True, evaluation=True,
        accord=accord, sortie=sortie, sortie_erreur=erreur, dire=messages.append,
        ressources_forcees=lambda _racine: {"duree_s": int(delai_s)} if delai_s else {})
    return {"code": code, "sortie": sortie.texte() + "\n" + erreur.texte(), "messages": messages}


def _rendu(statut, profil=None, **autres):
    r = {"statut": statut, "profil": None, "empreinte_profil": None, "image": None, "duree_s": None, "nb_tests": None,
         "echecs": [], "raison": None, "attend": None}
    if profil is not None:
        r["profil"] = {"familles": list(profil.familles), "confiance": profil.confiance, "commandes": profil.commandes}
        r["empreinte_profil"] = profil.empreinte
    r.update(autres)
    return r


def _image_du_profil(profil, serveur_id, image_connue):
    """`(etiquette, presente, decision)` : l'image du catalogue ou dérivée que la campagne utilisera. Unity : l'image de la
    version du projet, construite par `construire_image_tests.sh` ; sa présence est vérifiée par l'enveloppe (code 77)."""
    if "unity" in profil.familles:
        return None, True, None
    choix = tests_images.choisir_image(profil)
    if not choix["derivee"]:
        return choix["image"], True, None
    empreinte = tests_profil.empreinte_image(profil)
    etiquette = tests_images.etiquette_derivee(profil)
    if image_connue(serveur_id, empreinte):
        return etiquette, True, None
    return etiquette, False, tests_images.decision_image_derivee(profil)


def evaluer(racine, commande=None, route=None, construire=None, delai_s=None, lire=None, analyse=None, reseau=None,
            image_connue=None, serveur_id="", accord=None, horloge=time.monotonic) -> dict:
    """L'évaluation du projet `racine` (§ 5.15) ; rend `{"statut", "profil", "empreinte_profil", "image", "duree_s",
    "nb_tests", "echecs": [≤ 20 {"nom", "classe"}], "raison", "attend"}`.
    - `non_deportable` : rien n'est envoyé, la raison N1–N6 est dite.
    - image dérivée absente : `image_a_construire` (`attend` = « image », avec `decision` : le Dockerfile et ses estimations).
      `construire` (`profil -> bool`, facultatif) n'est appelé que pour ce cas : l'outil ne le fournit que si le Directeur a
      répondu `construire` ; sans lui rien n'est construit.
    - échauffement qui exécute du code du projet sans accord du réseau : `image_a_construire`, `attend` = « reseau ».
    - sinon UNE campagne par `route(commande, racine, delai_s) -> {"code", "sortie", "messages"}`, sans repli ni nouvelle
      tentative. `accord(racine) -> refus | None` : l'accord de la route (`tests_serveur` le demande à chaque appel) ; les
      évaluations lancées par le Directeur (bouton, installation) passent `lambda r: None`."""
    try:
        profil = (analyse or tests_profil.analyser)(str(racine), commande=list(commande) if commande else None, lire=lire)
    except Exception as e:  # noqa: BLE001 — jamais de route sur un doute
        return _rendu("non_deportable", raison=f"analyse du projet impossible ({type(e).__name__})")
    if profil.non_deportable:
        return _rendu("non_deportable", profil, raison=profil.non_deportable)
    if not profil.commandes and not commande:
        return _rendu("image_a_construire", profil, attend="commande",
                      raison="aucune commande de tests connue pour ce projet : indiquez-la (action « tests » du projet)")
    lancee = list(commande) if commande else list(profil.commandes[0])
    famille = profil.familles[0] if profil.familles else "python"

    etiquette, presente, decision = _image_du_profil(profil, serveur_id, image_connue or tests_images.image_connue)
    if not presente and construire is not None:
        try:
            presente = bool(construire(profil))
        except Exception:  # noqa: BLE001
            presente = False
    if not presente:
        return _rendu("image_a_construire", profil, image=etiquette, attend="image", decision=decision,
                      raison="aucune image du catalogue ne convient : une image dérivée est à construire")

    cle = tests_profil.cle_echauffement(profil)
    if cle is not None and tests_profil.ECHAUFFEMENTS[cle]["execute_du_code"] \
            and not (reseau or tests_serveur._reseau_code_par_defaut)(str(racine)):
        return _rendu("image_a_construire", profil, image=etiquette, attend="reseau",
                      raison="l'échauffement des dépendances exécute du code du projet : le réseau n'est pas accordé")

    delai = delai_s or (profil.ressources or {}).get("duree_s") or tests_serveur.LIMITES["duree_s"]
    depart = horloge()
    try:
        rendu = (route or route_par_defaut)(lancee, str(racine), delai, **({"accord": accord} if accord else {}))
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001
        return _rendu("injoignable", profil, image=etiquette, raison=f"campagne impossible ({type(e).__name__})")
    duree = max(0, round(horloge() - depart))
    code = rendu.get("code")
    sortie = rendu.get("sortie") or ""
    messages = " ".join(str(m) for m in rendu.get("messages") or [])
    commun = {"image": etiquette, "duree_s": duree}
    if code == 0:
        return _rendu("passe", profil, nb_tests=_nb_tests(sortie), **commun)
    if code == 124:
        return _rendu("trop_long", profil, raison=f"au-delà de {delai} s ({famille}), conteneur arrêté", **commun)
    if code in (4, 2):
        raison = messages.strip() or "refus de la route"
        if re.search(r"image|sdk android|cache|échauffement", raison, re.IGNORECASE) and "injoignable" not in raison:
            return _rendu("image_a_construire", profil, raison=raison, attend="serveur", **commun)
        return _rendu("injoignable", profil, raison=raison, **commun)
    if code in (74, 130, 255):
        return _rendu("injoignable", profil, raison=messages.strip() or f"campagne interrompue (code {code})", **commun)
    return _rendu("echoue", profil, nb_tests=_nb_tests(sortie), echecs=extraire_echecs(sortie),
                  raison=f"code {code}", marqueur=marqueur_pour(famille), **commun)


# --- réglages : `tests.adoption`, écrit par le bureau / l'outil seulement ----------------------------------------------

def adoption_lue(racine) -> Optional[dict]:
    """`tests.adoption` des réglages enregistrés au bureau pour ce projet (le premier fichier qui en a une) ; None sinon."""
    try:
        try:
            from bureau import deport_types
        except ImportError:
            sys.path.append(str(ICI.parent))
            from bureau import deport_types
        for fichier in deport_types.reglages_enregistres(str(racine)) or []:
            x = deport_types._lire_json_sur(fichier)
            tests = x.get("tests") if isinstance(x, dict) else None
            adoption = tests.get("adoption") if isinstance(tests, dict) else None
            if isinstance(adoption, dict):
                return adoption
    except Exception:  # noqa: BLE001
        return None
    return None


CLES_ADOPTION = ("date", "statut", "empreinte_profil", "image", "reseau_echauffement", "duree_s", "nb_tests")


def noter_adoption(fichier_reglages, resultat, reseau_echauffement=None, date=None) -> dict:
    """Écrit `tests.adoption` dans le fichier de réglages du projet (relu et réécrit d'un trait, autres clés gardées) ; rend
    ce qui est écrit. Appelée par l'outil du bureau, jamais par un agent."""
    entree = {"date": date or time.strftime("%Y-%m-%dT%H:%M:%S"), "statut": resultat.get("statut"),
              "empreinte_profil": resultat.get("empreinte_profil"), "image": resultat.get("image"),
              "reseau_echauffement": reseau_echauffement, "duree_s": resultat.get("duree_s"),
              "nb_tests": resultat.get("nb_tests")}
    chemin = Path(fichier_reglages)
    donnees = {}
    if chemin.exists():
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
        if not isinstance(donnees, dict):
            raise ValueError("réglages illisibles")
    tests = donnees.get("tests")
    if not isinstance(tests, dict):
        tests = {}
    tests["adoption"] = entree
    donnees["tests"] = tests
    tmp = chemin.with_name(chemin.name + ".adoption.tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, chemin)
    return entree


def profil_change(racine, profil, adoption=None) -> bool:
    """Vrai si le projet a une adoption notée dont l'empreinte de profil n'est plus celle du profil courant."""
    adoption = adoption if adoption is not None else adoption_lue(racine)
    if not isinstance(adoption, dict) or not adoption.get("empreinte_profil"):
        return False
    return adoption["empreinte_profil"] != profil.empreinte
