"""Ce qu'il reste à faire après le développement d'une fonctionnalité : la mettre en ligne sur le serveur, l'installer.

Essai réel (FM_Stats, f14 « Serveur de données distant autonome », 2026-11-25) : le code, les tests, la documentation et
l'APK étaient faits, le Chef a dit « La série est terminée. » alors que rien n'était déployé sur le serveur OVH ni installé.
Le moteur ne connaissait pas le déploiement. Règle : une fonctionnalité qui en demande un ne se termine qu'avec lui ; le moteur
ouvre lui-même une correction « Déployer et installer : … » (l'agent demande l'accès et la dépense au Directeur par les voies
habituelles) et ne dit « terminée » qu'une fois cette correction finie.

Module sans dépendance au moteur : il lit seulement les fonctionnalités du suivi."""
import re

TITRE = "Déployer et installer"
ETAPES_FINIES = ("terminee", "deplacee")

LIBELLE_SERVEUR = "le déploiement sur le serveur"
LIBELLE_INSTALLATION = "l'installation de l'application"

# Ce que la demande ou le cahier disent d'une mise en ligne (le Directeur écrit « déporter sur le serveur (ovh) »).
_SERVEUR = re.compile(r"ovh|d[ée]port|d[ée]ploi|h[ée]berg|mise? en ligne|mettre en ligne", re.IGNORECASE)
_INSTALLATION = re.compile(r"install|sur (?:l'|mon |le )?(?:appareil|t[ée]l[ée]phone)", re.IGNORECASE)
GENRES_APK = ("application-mobile-android",)


def _texte(f, noms):
    cahier = f.get("cahier") or {}
    morceaux = [f.get("nom") or "", cahier.get("en_clair") or "", *(cahier.get("etapes") or []), *noms]
    morceaux += [str(m.get("texte") or "") for m in f.get("discussion") or [] if m.get("auteur") == "utilisateur"]
    return " ".join(x for x in morceaux if isinstance(x, str))


def restants(f, noms=()):
    """Ce que la fonctionnalité `f` (détail du suivi) demande encore après son développement : une liste de libellés,
    vide si rien. Une correction, ou la correction de déploiement elle-même, n'en demande jamais."""
    if f.get("nature") == "correction" or str(f.get("nom") or "").startswith(TITRE):
        return []
    texte = _texte(f, noms)
    sortie = []
    if _SERVEUR.search(texte):
        sortie.append(LIBELLE_SERVEUR)
    if _INSTALLATION.search(texte) or (sortie and f.get("genre") in GENRES_APK):
        sortie.append(LIBELLE_INSTALLATION)
    return sortie


def ouverte_pour(fonctionnalites, fid):
    """La correction de déploiement déjà ouverte pour `fid` (état court du moteur), terminée ou non ; None sinon."""
    return next((x for x in fonctionnalites
                 if x.get("nature") == "correction" and x.get("concerne") == fid
                 and str(x.get("nom") or "").startswith(TITRE)), None)


def demande(f, restant):
    """Le texte de la demande de correction (les 40 premiers caractères en font le nom : le titre d'abord)."""
    return (f"{TITRE} : {f['nom']}. Le développement de la fonctionnalité « {f['nom']} » est fini ; il reste à faire "
            + " et ".join(restant) + ". Déploie ce qui doit l'être sur le serveur du projet, installe l'application, "
            "vérifie que cela fonctionne en réel. Il te manque peut-être un accès (serveur, clé, appareil) ou une décision "
            "de dépense : demande-les au Directeur avant d'agir, ne devine rien.")
