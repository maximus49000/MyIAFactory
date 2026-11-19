"""La plateforme (serveur OVH) vue du bureau : lecture du cache, lancement de l'installation en arrière-plan.

Colle mince au-dessus de `outils/plateforme.py` : la lecture ne contacte jamais OVH ni SSH (elle relit seulement
`plateforme.json`), l'installation tourne dans un fil, un seul à la fois, et ne fait jamais tomber le bureau.
"""
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

DOSSIER = None   # None : le dossier des secrets (`plateforme_acces.DOSSIER`) ; remplacé dans les essais
_OUTILS = str(Path(__file__).resolve().parent.parent / "outils")


def _modules():
    """`outils/plateforme.py` et `outils/plateforme_acces.py` (modules à plat : le dossier `outils` doit être sur le chemin)."""
    if _OUTILS not in sys.path:
        sys.path.append(_OUTILS)
    import plateforme
    import plateforme_acces
    return plateforme, plateforme_acces


def dossier():
    """`DOSSIER`, sinon la variable `MYIAFACTORY_PLATEFORME` (posée par `tests/__init__.py` : un essai ne lit jamais le vrai
    dossier personnel), sinon `plateforme_acces.DOSSIER`."""
    brut = DOSSIER or os.environ.get("MYIAFACTORY_PLATEFORME")
    return Path(brut) if brut else _modules()[1].DOSSIER


def _masquer(v, secrets, acces):
    if isinstance(v, str):
        return acces.masquer(v, secrets)
    if isinstance(v, list):
        return [_masquer(x, secrets, acces) for x in v]
    return {k: _masquer(x, secrets, acces) for k, x in v.items()} if isinstance(v, dict) else v


def _secrets(d, acces):
    """Les secrets connus du dossier (sans exiger `ovh.json`) : le cache est déjà masqué, ceci est une seconde garde."""
    secrets = []
    try:
        secrets += [v for k, v in acces.charger_ovh(d).items() if k in ("cle_app", "secret", "consommateur")]
    except Exception:
        pass
    try:
        licence = acces.chemin_licence(d)
        if licence:
            secrets += acces.secrets_licence(licence.read_bytes().decode("utf-8", errors="replace"))
    except Exception:
        pass
    return [s for s in secrets if isinstance(s, str)]


def _interrompu(d, plateforme, travail, vivant):
    """Une étape « en cours » au cache n'est vraie que si un fil du bureau tourne, ou si un verrou tenu par un autre processus
    vivant existe (installation lancée en ligne de commande). Sinon l'exécution a été coupée : l'étape est à reprendre."""
    if travail and travail.en_cours():
        return False
    try:
        return not plateforme._verrou_tenu(d / plateforme.VERROU, vivant or plateforme.pid_vivant)
    except Exception:
        return True


def lire(d=None, travail=None, vivant=None):
    """L'état tel que le dit le cache (jamais d'appel OVH ni SSH) ; sans cache : toutes les étapes à faire.

    Les étapes « en cours » qu'aucune exécution ne porte plus (bureau fermé, panne) sont rendues « à faire : à reprendre »."""
    plateforme, acces = _modules()
    d = Path(d) if d else dossier()
    rapports, date = {}, ""
    try:
        brut = plateforme._lire_cache(d).get("rapports")
        if isinstance(brut, dict):
            rapports = {k: v for k, v in brut.items() if k in plateforme.ETAPES and isinstance(v, dict)}
        date = datetime.fromtimestamp((d / plateforme.CACHE).stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except (OSError, ValueError, AttributeError):
        pass
    if any(r.get("statut") == "en_cours" for r in rapports.values()) and _interrompu(d, plateforme, travail, vivant):
        rapports = {k: ({"statut": "a_faire", "detail": "Interrompu : à reprendre", "geste": ""} if r.get("statut") == "en_cours" else r)
                    for k, r in rapports.items()}
    try:
        etat = _masquer(plateforme.calculer_etat(rapports), _secrets(d, acces), acces)
    except Exception:   # un cache abîmé (types inattendus) : l'état « tout à faire », jamais une erreur
        etat = plateforme.calculer_etat({})
    etat["derniere_lecture"] = date
    etat["en_cours"] = bool(travail and travail.en_cours())
    if travail and getattr(travail, "erreur", ""):
        etat["erreur"] = _masquer(str(travail.erreur), _secrets(d, acces), acces)
    return etat


def autre_installation(d=None):
    """Le message d'un refus si l'installation générique des serveurs de travail tourne (elle partage le script distant avec
    celle de la plateforme : jamais les deux ensemble) ; `None` sinon ou au moindre ennui."""
    try:
        _modules()
        import serveur_installation
        d = Path(d) if d else dossier()
        if serveur_installation.installation_en_cours(d):
            return "Une installation des serveurs de travail est en cours : attendez sa fin avant de lancer celle de la plateforme."
    except Exception:
        pass
    return None


def pret(d=None):
    """La plateforme est-elle prête (étapes 1 à 6 faites, d'après le cache) ? Faux au moindre ennui."""
    try:
        return lire(d)["pret"] is True
    except Exception:
        return False


class Travail:
    """Une installation à la fois, dans un fil : `lancer` rend faux si une autre tourne déjà."""

    def __init__(self, installer=None):
        self._installer = installer
        self._verrou = threading.Lock()
        self._fil = None
        self.erreur = None

    def en_cours(self):
        with self._verrou:
            return self._fil is not None and self._fil.is_alive()

    def lancer(self, d=None, accord_reinstallation=False):
        with self._verrou:
            if self._fil is not None and self._fil.is_alive():
                return False
            self.erreur = None   # l'erreur de l'exécution précédente ne doit pas survivre à une nouvelle exécution
            self._fil = threading.Thread(target=self._courir, args=(Path(d) if d else dossier(), accord_reinstallation is True),
                                         daemon=True)
            self._fil.start()
            return True

    def attendre(self, delai=10):
        fil = self._fil
        if fil is not None:
            fil.join(delai)

    def _courir(self, d, accord):
        try:
            installer = self._installer or _modules()[0].installer
            installer(d, accord_reinstallation=accord)
            self.erreur = None
        except BaseException as e:   # jamais un fil qui meurt avec un message qui pourrait citer un secret
            self.erreur = f"Installation interrompue ({type(e).__name__}) ; le cache garde le dernier état connu."
            print(self.erreur, file=sys.stderr)
