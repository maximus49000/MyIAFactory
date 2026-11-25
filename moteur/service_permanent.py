"""Déploiement automatique du service permanent d'un projet après une livraison validée (docs/serveur-services.md).

À la fin de chaque livraison (`regles._est_une_livraison`, rapport « fait » : la livraison suit toujours la validation du
Directeur dans le workflow), si le projet a `.factory/service.json` ET l'accord du Directeur (action `service` réglée sur
« serveur » dans ses réglages enregistrés au bureau), le moteur lance `serveur_service.deployer` au commit courant du
projet, dans un fil : la boucle ne l'attend jamais. Un seul fil par projet ; le serveur refuse de toute façon deux
déploiements simultanés. Le résultat (ok, retour arrière, échec) est écrit dans le cache `services.json` que le bureau
montre (zone Services) ; aucune valeur secrète ne passe ici.
"""
import sys
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


def declencher(dossier, synchrone=False, module=None, refus=raison_de_ne_pas_deployer):
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
                m.deployer(dossier)
            except Exception:  # noqa: BLE001 — le cache garde l'état « en cours » ; le bureau le montre
                pass
        if synchrone:
            travail()
            return "Service permanent : déploiement fait au serveur (résultat dans la zone Services du bureau)."
        fil = threading.Thread(target=travail, name=f"service-{Path(dossier).name}", daemon=True)
        _EN_VOL[cle] = fil
        fil.start()
    return ("Service permanent : déploiement lancé au serveur (commit de la livraison, contrôle de santé et retour "
            "arrière automatique) ; résultat dans la zone Services du bureau.")
