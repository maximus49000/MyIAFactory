"""Déploiement automatique du service permanent d'un projet après une livraison validée (docs/serveur-services.md).

À la fin de chaque livraison (`regles._est_une_livraison`, rapport « fait » : la livraison suit toujours la validation du
Directeur dans le workflow), si le projet a `.factory/service.json` ET l'accord du Directeur (action `service` réglée sur
« serveur » dans ses réglages enregistrés au bureau), le moteur lance `serveur_service.deployer` au commit courant du
projet, dans un fil : la boucle ne l'attend jamais. Un seul fil par projet ; le serveur refuse de toute façon deux
déploiements simultanés. Le résultat (ok, retour arrière, échec) est écrit dans le cache `services.json` que le bureau
montre (zone Services) ; aucune valeur secrète ne passe ici.
"""
import sys
from datetime import datetime, timezone
import threading
from pathlib import Path

_OUTILS = str(Path(__file__).resolve().parent.parent / "outils")
_EN_VOL = {}
_VERROU = threading.Lock()


def _module():
    if _OUTILS not in sys.path:
        sys.path.insert(0, _OUTILS)
    import serveur_service
    return serveur_service


def raison_de_ne_pas_deployer(dossier, module=None):
    """None si le service du projet doit être déployé ; sinon la raison (texte court), ou "" s'il n'y a pas de service."""
    m = module or _module()
    if not m.a_un_service(dossier):
        return ""
    from bureau import deport_types
    refus = deport_types.refus_accord(str(Path(dossier).resolve()), m.ACTION)
    if refus:
        return ("le projet déclare un service permanent (.factory/service.json) mais l'action « service » n'est pas "
                "réglée sur serveur : pas de déploiement automatique (" + refus[:200] + ")")
    return None


ESSAIS = {}                   # {dossier: (commit essayé, heure)} : jamais deux fois de suite le même commit en échec
DELAI_MIN_S = 120             # au plus une vérification toutes les deux minutes par projet
EN_COURS_PERIME_S = 3300      # un « en cours » plus vieux que la durée maximale d'un déploiement (envoi 600 s + 2400 s) est abandonné
_DERNIERE = {}


def _commit_du_depot(dossier):
    """Le commit courant du projet (`git rev-parse HEAD`), ou None."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(dossier), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    sortie = r.stdout.strip()
    return sortie if r.returncode == 0 and len(sortie) == 40 else None


def _en_cours_perime(deploiement, maintenant):
    """Vrai si le déploiement « en cours » du cache est plus vieux que la durée maximale d'un déploiement : le poste (ou le
    moteur) s'est arrêté pendant qu'il tournait et n'a jamais pu le conclure ; il ne doit plus bloquer les suivants."""
    try:
        debut = datetime.strptime(str(deploiement.get("debut")), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return maintenant - debut.timestamp() > EN_COURS_PERIME_S


def deployer_si_modifie(dossier, maintenant, module=None, commit_du_depot=_commit_du_depot, declencher_=None,
                        annoncer=None):
    """La case « Déployer automatiquement à chaque modification » : si elle est cochée pour ce projet et que son commit
    courant n'est pas celui du serveur, le service est redéployé sans demander. Rend la ligne dite, ou None (rien à faire).
    Un commit déjà essayé et en échec n'est pas retenté (un nouveau commit relance) ; un déploiement en cours attend."""
    cle = str(Path(dossier).resolve())
    if maintenant - _DERNIERE.get(cle, 0) < DELAI_MIN_S:
        return None
    _DERNIERE[cle] = maintenant
    if not (Path(dossier) / ".factory" / "service.json").is_file():
        return None
    m = module or _module()
    projet = m.identifiant(Path(dossier))
    if m.lire_auto().get(projet) is not True:
        return None
    fil = _EN_VOL.get(cle)
    if fil is not None and fil.is_alive():
        return None
    fiche = m.lire_cache().get(projet)
    fiche = fiche if isinstance(fiche, dict) else {}
    if (isinstance(fiche.get("deploiement"), dict) and fiche["deploiement"].get("statut") == "en_cours"
            and not _en_cours_perime(fiche["deploiement"], maintenant) and not getattr(m, "deploiement_abandonne", lambda _d: False)(fiche["deploiement"])):
        return None
    commit = commit_du_depot(dossier)
    if commit is None:
        return None
    etat = fiche.get("etat") if isinstance(fiche.get("etat"), dict) else {}
    if etat.get("commit") == commit and etat.get("etat") == "actif":
        return None
    if ESSAIS.get(cle) == commit:
        return None
    ESSAIS[cle] = commit
    ligne = (declencher_ or declencher)(dossier, annoncer=annoncer)
    return ("Déploiement automatique (case cochée) : " + ligne) if ligne else None


def annonce(resultat):
    """Le message dit au Directeur après un déploiement : en ligne (adresse), retour arrière ou échec, avec la raison. Jamais le
    jeton ni un secret (le jeton se copie dans la zone « Services » du bureau). `resultat` : `(code, réponse)` de `deployer`."""
    try:
        code, rep = resultat
    except (TypeError, ValueError):
        return "Le déploiement du service permanent n'a pas rendu de résultat lisible : voir la zone « Services » du bureau."
    rep = rep if isinstance(rep, dict) else {}
    detail = str(rep.get("detail") or "")[:300]
    adresse = rep.get("adresse") if isinstance(rep.get("adresse"), str) else ""
    if rep.get("statut") == "ok" and code == 0:
        return ("Le service permanent est en ligne" + (f" : {adresse}" if adresse else "") + ". Le jeton d'accès se copie dans la "
                "zone « Services » du bureau (il n'est jamais écrit dans un message)." + (f" {detail}" if detail else ""))
    if rep.get("statut") == "retour_arriere":
        return ("Le déploiement du service permanent a échoué : retour automatique à la version précédente"
                + (f" ({adresse})" if adresse else "") + (f". {detail}" if detail else "."))
    return "Le service permanent n'a pas pu être déployé" + (f" : {detail}" if detail else ".") + " Voir la zone « Services »."


def declencher(dossier, synchrone=False, module=None, refus=raison_de_ne_pas_deployer, annoncer=None):
    """Lance le déploiement du service du projet `dossier` s'il le faut ; rend la ligne à mettre au journal de la tâche
    (None s'il n'y a pas de service). Jamais d'exception : un échec est dit, jamais une raison d'arrêter la livraison."""
    try:
        if module is None and not (Path(dossier) / ".factory" / "service.json").is_file():
            return None                      # sans déclaration, rien n'est chargé ni lu
        m = module or _module()
        raison = refus(dossier, m)
    except Exception as e:  # noqa: BLE001
        return f"Service permanent : vérification impossible ({type(e).__name__})."
    if raison == "":
        return None
    if raison:
        return f"Service permanent : {raison}."
    cle = str(Path(dossier).resolve())
    with _VERROU:
        fil = _EN_VOL.get(cle)
        if fil is not None and fil.is_alive():
            return "Service permanent : un déploiement est déjà en cours ; celui-ci sera fait à la prochaine livraison."

        def travail():
            try:
                resultat = m.deployer(dossier)
            except Exception:  # noqa: BLE001 — le cache garde l'état « en cours » ; le bureau le montre
                resultat = (1, {"statut": "echec", "detail": "erreur inattendue au poste"})
            if annoncer is not None:
                try:
                    annoncer(annonce(resultat))
                except Exception:  # noqa: BLE001 — l'annonce n'est jamais une raison d'échouer
                    pass
        if synchrone:
            travail()
            return "Service permanent : déploiement fait au serveur (résultat dans la zone Services du bureau)."
        fil = threading.Thread(target=travail, name=f"service-{Path(dossier).name}", daemon=True)
        _EN_VOL[cle] = fil
        fil.start()
    return ("Service permanent : déploiement lancé au serveur (commit de la livraison, contrôle de santé et retour "
            "arrière automatique) ; résultat dans la zone Services du bureau.")
