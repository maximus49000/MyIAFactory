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


def lire(d=None, travail=None):
    """L'état tel que le dit le cache (jamais d'appel OVH ni SSH) ; sans cache : toutes les étapes à faire."""
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
    try:
        etat = _masquer(plateforme.calculer_etat(rapports), _secrets(d, acces), acces)
    except Exception:   # un cache abîmé (types inattendus) : l'état « tout à faire », jamais une erreur
        etat = plateforme.calculer_etat({})
    etat["derniere_lecture"] = date
    etat["en_cours"] = bool(travail and travail.en_cours())
    return etat


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
        self.erreur = ""

    def en_cours(self):
        with self._verrou:
            return self._fil is not None and self._fil.is_alive()

    def lancer(self, d=None, accord_reinstallation=False):
        with self._verrou:
            if self._fil is not None and self._fil.is_alive():
                return False
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
            self.erreur = ""
        except BaseException as e:   # jamais un fil qui meurt avec un message qui pourrait citer un secret
            self.erreur = f"Installation interrompue ({type(e).__name__}) ; le cache garde le dernier état connu."
            print(self.erreur, file=sys.stderr)
