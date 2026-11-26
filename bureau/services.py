"""La zone « Services » du bureau : le service permanent de chaque projet sur le serveur (docs/serveur-services.md).

- `GET /api/services` : les projets du bureau qui déclarent un service (`.factory/service.json`), avec le dernier état
  connu (cache `~/MyIAFactory/services.json`, jamais de connexion), l'adresse publique, la présence du jeton au coffre et
  la présence de chaque secret (OUI/NON par nom, jamais la valeur), le dernier journal (masqué au serveur).
- `POST /api/services/<projet>/<action>` (depuis l'ordinateur seulement, `X-Bureau: 1`, JSON) :
  `etat`, `journal`, `redemarrer`, `arreter`, `deployer` : lancés dans un fil (202), un seul à la fois par projet ;
  `secrets` : corps `{"secrets": {"NOM": "valeur"}}`, noms DÉCLARÉS seulement, posés au serveur dans un fil (202) : la valeur
  ne reste qu'en mémoire le temps de l'envoi, n'est jamais écrite au poste, jamais journalisée, jamais rendue ;
  `auto` : corps `{"actif": true|false}` : la case « Déployer automatiquement à chaque modification » (200, tout de suite) ;
  `jeton` : rend le jeton du coffre du poste (200) pour le bouton « Copier », au Directeur seul.
`<projet>` est l'identifiant calculé d'un projet ENREGISTRÉ au bureau (jamais un chemin reçu) : le dossier vient des réglages
du bureau, pas du cache.
"""
import re
import sys
import threading
import time
from pathlib import Path

_OUTILS = str(Path(__file__).resolve().parent.parent / "outils")
_ROUTE = re.compile(r"/api/services/([a-z][a-z0-9-]{1,39})/(etat|journal|redemarrer|arreter|deployer|secrets|jeton|auto)")
EN_FIL = ("etat", "journal", "redemarrer", "arreter", "deployer", "secrets")
TAILLE_MAX = 64 * 1024
JOURNAL_MAX = 200


def _module():
    if _OUTILS not in sys.path:
        sys.path.insert(0, _OUTILS)
    import serveur_service
    return serveur_service


def route_post(chemin):
    """`(projet, action)` pour une route POST des services, sinon None."""
    m = _ROUTE.fullmatch(chemin)
    return (m.group(1), m.group(2)) if m else None


class Travaux:
    """Un fil par projet au plus ; l'état de la dernière action (sans valeur secrète) reste en mémoire pour l'écran."""

    def __init__(self, module=None, dossier=None):
        self._module = module
        self.dossier = dossier
        self._fils = {}
        self.dernier = {}
        self._verrou = threading.Lock()

    @property
    def module(self):
        return self._module or _module()

    def en_cours(self, projet):
        f = self._fils.get(projet)
        return f is not None and f.is_alive()

    def lancer(self, projet, action, travail):
        with self._verrou:
            if self.en_cours(projet):
                return False
            self.dernier[projet] = {"action": action, "statut": "en_cours", "debut": time.time()}

            def fil():
                try:
                    code, rep = travail()
                    statut, detail = rep.get("statut"), rep.get("detail")
                except Exception as e:  # noqa: BLE001
                    code, statut, detail = 1, "echec", f"Erreur inattendue ({type(e).__name__})."
                self.dernier[projet] = {"action": action, "statut": statut, "code": code,
                                        "detail": str(detail or "")[:500], "fin": time.time()}
            t = threading.Thread(target=fil, name=f"service-{projet}-{action}", daemon=True)
            self._fils[projet] = t
            t.start()
        return True

    def attendre(self, delai=10):
        for t in list(self._fils.values()):
            t.join(delai)


def _projets(dossiers, module):
    """{identifiant: dossier} des projets enregistrés qui déclarent un service."""
    rendu = {}
    for d in dossiers:
        d = Path(d)
        if module.a_un_service(d):
            rendu[module.identifiant(d)] = d
    return rendu


def lire(travaux, dossiers):
    m = travaux.module
    k = {} if travaux.dossier is None else {"dossier": travaux.dossier}
    cache = m.lire_cache(**k)
    auto = m.lire_auto(**k)
    services = []
    for projet, dossier in sorted(_projets(dossiers, m).items()):
        fiche = cache.get(projet) if isinstance(cache.get(projet), dict) else {}
        etat = fiche.get("etat") if isinstance(fiche.get("etat"), dict) else {}
        try:
            declaration = m.lire_declaration(dossier)
            erreur = None
        except ValueError as e:
            declaration, erreur = {}, str(e)[:300]
        presents = etat.get("secrets") if isinstance(etat.get("secrets"), dict) else {}
        secrets = {n: presents.get(n) is True for n in declaration.get("secrets", [])}
        journal = fiche.get("journal") if isinstance(fiche.get("journal"), dict) else {}
        services.append({
            "projet": projet, "nom": declaration.get("nom") or projet, "declaration_erreur": erreur,
            "etat": etat.get("etat") or "inconnu", "sante_ok": etat.get("sante_ok"), "commit": etat.get("commit"),
            "deploye_le": etat.get("deploye_le"), "dernier_deploiement": etat.get("dernier_deploiement"),
            "adresse": fiche.get("adresse") if isinstance(fiche.get("adresse"), str) else None,
            "jeton_present": bool(m.lire_jeton(projet, **k)), "secrets": secrets,
            "journal": [str(l)[:500] for l in (journal.get("lignes") or [])][-JOURNAL_MAX:],
            "deploiement": _deploiement_lu(m, fiche.get("deploiement")),
            "auto": auto.get(projet) is True,
            "action": travaux.dernier.get(projet), "occupe": travaux.en_cours(projet), "maj": fiche.get("maj")})
    return {"services": services}


def _deploiement_lu(m, dep):
    """Le déploiement du cache ; « en cours » devient « interrompu » si le processus qui le menait n'existe plus."""
    if not isinstance(dep, dict):
        return None
    abandonne = getattr(m, "deploiement_abandonne", None)
    if callable(abandonne) and abandonne(dep):
        return dict(dep, statut="interrompu")
    return dep


def poster(travaux, projet, action, corps, dossiers):
    m = travaux.module
    k = {} if travaux.dossier is None else {"dossier": travaux.dossier}
    dossier = _projets(dossiers, m).get(projet)
    if dossier is None:
        return 404, {"erreur": "Aucun service déclaré pour ce projet."}
    if action == "auto":     # la case « Déployer automatiquement » : {"actif": true|false}, écrite tout de suite (pas de fil)
        if set(corps) != {"actif"} or not isinstance(corps.get("actif"), bool):
            return 400, {"erreur": "Corps attendu : {\"actif\": true} ou {\"actif\": false}."}
        return 200, {"auto": m.poser_auto(projet, corps["actif"], **k)}
    if action == "jeton":
        j = m.lire_jeton(projet, **k)
        return (200, {"jeton": j}) if j else (404, {"erreur": "Pas encore de jeton : déployez le service d'abord."})
    if action == "secrets":
        valeurs = corps.get("secrets")
        try:
            declares = set(m.lire_declaration(dossier)["secrets"])
        except ValueError as e:
            return 400, {"erreur": str(e)[:300]}
        if not isinstance(valeurs, dict) or not valeurs or set(corps) != {"secrets"}:
            return 400, {"erreur": "Corps attendu : {\"secrets\": {\"NOM\": \"valeur\"}}."}
        inconnus = sorted(n for n in valeurs if n not in declares)
        if inconnus:
            return 400, {"erreur": "Secret non déclaré dans .factory/service.json : " + ", ".join(str(n)[:40] for n in inconnus[:5])}
        if any(not isinstance(v, str) or not v.strip() for v in valeurs.values()):
            return 400, {"erreur": "Chaque secret doit être un texte non vide d'une ligne."}
        valeurs = {n: v.strip() for n, v in valeurs.items()}
        try:
            m.HOTE.valider_valeurs(__import__("json").dumps(valeurs).encode("utf-8"), "secrets")
        except ValueError:
            return 400, {"erreur": "Secret refusé : une ligne de 4096 caractères au plus."}

        def travail():
            return m.poser_secrets(dossier, valeurs, **k)
    elif action == "deployer":
        def travail():
            return m.deployer(dossier, **k)
    else:
        def travail():
            return m.gerer(dossier, action, **k)
    if corps and action != "secrets":
        return 400, {"erreur": "Corps attendu : {}."}
    if not travaux.lancer(projet, action, travail):
        return 409, {"erreur": "Une action sur ce service est déjà en cours : réessayez à sa fin."}
    return 202, {"demarre": True}
