"""Savoir quels partenaires sont déclarés sur la machine et dans le projet, **sans jamais garder une valeur de clé**.

- Serveurs MCP : la configuration de l'utilisateur (`~/.claude.json`, y compris ses serveurs propres au projet) et le
  `.mcp.json` du projet. Les clés `headers`, `env` et `args` sont jetées dès la lecture du JSON : seuls le nom d'un
  serveur et son `url` sont regardés.
- Variables d'environnement : seuls les **noms** comptent (environnement de la machine, `.env` du projet) ; les valeurs
  sont jetées ligne par ligne sans être gardées.
- `cle()` est la seule fonction qui rend une valeur : pour un appel, au moment de l'appel, jamais mise en cache.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

JETEES = frozenset(("headers", "env", "args"))
_NOM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\Z")
_COMMANDE_MCP = re.compile(r"\bclaude\s+mcp\s+add\b(.*)")


def _sans_secrets(paires):
    """`object_hook` du JSON : les champs qui peuvent porter un jeton ne survivent pas à la lecture."""
    return {k: v for k, v in paires if k not in JETEES}


def _lire_json(chemin):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8-sig"), object_pairs_hook=_sans_secrets)
    except (OSError, ValueError):
        return None


def _lignes_env(chemin):
    """(nom, ligne brute après « = ») de chaque affectation d'un fichier `.env`, valeurs sur plusieurs lignes comprises."""
    try:
        texte = Path(chemin).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return
    ouverte = None   # guillemet d'une valeur restée ouverte sur la ligne suivante
    for brut in texte.splitlines():
        if ouverte:
            if ouverte in brut:
                ouverte = None
            continue
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if ligne.startswith("export "):
            ligne = ligne[7:].lstrip()
        nom, egal, reste = ligne.partition("=")
        nom = nom.strip()
        if not egal or not _NOM.match(nom):
            continue
        reste = reste.strip()
        if reste[:1] in ("'", '"') and reste.count(reste[0]) == 1:
            ouverte = reste[0]
        yield nom, reste


def noms_env(chemin):
    """Les noms des variables d'un fichier `.env` (jamais leurs valeurs)."""
    return {nom for nom, _ in _lignes_env(chemin)}


def _valeur(reste):
    if reste[:1] in ("'", '"'):
        fin = reste.find(reste[0], 1)
        return reste[1:fin] if fin > 0 else None   # une valeur sur plusieurs lignes n'est pas une clé d'API
    return reste.split(" #", 1)[0].strip()


def _normaliser_url(u):
    if not isinstance(u, str):
        return None
    p = urlsplit(u.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    return f"{p.hostname.lower()}{p.path.rstrip('/')}"


def _plat(texte):
    return re.sub(r"[^a-z0-9]", "", str(texte).lower())


def _nom_de_commande(commande):
    """Le nom du serveur dans `claude mcp add [options] <nom> <url>`."""
    m = _COMMANDE_MCP.search(commande or "")
    if not m:
        return None
    mots, i = m.group(1).split(), 0
    while i < len(mots):
        if mots[i].startswith("-"):
            i += 1 if "=" in mots[i] else 2
            continue
        return mots[i]
    return None


def serveurs_mcp(projet, config_utilisateur=None):
    """[(nom, url | None, origine)] des serveurs MCP déclarés. Rien d'autre n'est lu."""
    config_utilisateur = Path(config_utilisateur) if config_utilisateur else Path.home() / ".claude.json"
    sortie = []

    def prendre(serveurs, origine):
        if isinstance(serveurs, dict):
            for nom, s in serveurs.items():
                url = s.get("url") if isinstance(s, dict) else None
                sortie.append((str(nom), url if isinstance(url, str) else None, origine))

    u = _lire_json(config_utilisateur)
    if isinstance(u, dict):
        prendre(u.get("mcpServers"), "serveur MCP de Claude Code")
        projets = u.get("projects")
        if isinstance(projets, dict):
            cible = os.path.normcase(str(Path(projet).resolve()))
            for chemin, conf in projets.items():
                if isinstance(conf, dict) and os.path.normcase(str(Path(chemin))) == cible:
                    prendre(conf.get("mcpServers"), "serveur MCP de Claude Code (ce projet)")
    m = _lire_json(Path(projet) / ".mcp.json")
    if isinstance(m, dict):
        prendre(m.get("mcpServers"), "serveur MCP du projet (.mcp.json)")
    return sortie


def declares(projet, environ=None, config_utilisateur=None, catalogue=None):
    """{id: source} des partenaires du catalogue déclarés sur la machine ou dans le projet."""
    environ = os.environ if environ is None else environ
    if catalogue is None:
        from partenaires.catalogue import lire
        catalogue = lire()
    serveurs = serveurs_mcp(projet, config_utilisateur)
    noms_dotenv = noms_env(Path(projet) / ".env")
    noms_machine = set(environ.keys())
    sortie = {}
    for p in catalogue["partenaires"]:
        if p.get("statut") not in ("actif", "restreint"):
            continue
        urls, noms, variables = set(), {_plat(p["id"]), _plat(p["nom"])}, []
        for c in p.get("connexions") or []:
            if c.get("type") == "mcp":
                if _normaliser_url(c.get("url")):
                    urls.add(_normaliser_url(c["url"]))
                n = _nom_de_commande(c.get("commande"))
                if n:
                    noms.add(_plat(n))
            variables += c.get("variables") or []
        for nom, url, origine in serveurs:
            if (url and _normaliser_url(url) in urls) or _plat(nom) in noms:
                sortie[p["id"]] = f"{origine} « {nom} »"
                break
        else:
            for v in variables:
                if v in noms_machine:
                    sortie[p["id"]] = f"variable {v} présente (environnement)"
                    break
                if v in noms_dotenv:
                    sortie[p["id"]] = f"variable {v} présente (.env du projet)"
                    break
    return sortie


def cle_des_variables(variables, projet, environ=None):
    """La valeur de la première de ces variables (environnement, puis `.env` du projet), pour un appel seulement."""
    environ = os.environ if environ is None else environ
    for v in variables:
        if environ.get(v):
            return environ[v]
    trouvees = {nom: reste for nom, reste in _lignes_env(Path(projet) / ".env") if nom in variables}
    for v in variables:
        valeur = _valeur(trouvees[v]) if v in trouvees else None
        if valeur:
            return valeur
    return None


def cle(id_, projet, environ=None, catalogue=None):
    """La valeur de la clé d'un partenaire, **pour un appel seulement** : l'environnement d'abord, puis le `.env` du
    projet. Jamais gardée, jamais écrite, jamais rendue dans une sortie."""
    environ = os.environ if environ is None else environ
    if catalogue is None:
        from partenaires.catalogue import lire
        catalogue = lire()
    p = next((x for x in catalogue["partenaires"] if x["id"] == id_), None)
    if p is None:
        return None
    variables = [v for c in p.get("connexions") or [] for v in c.get("variables") or []]
    for v in variables:
        if environ.get(v):
            return environ[v]
    trouvees = {}
    for nom, reste in _lignes_env(Path(projet) / ".env"):
        if nom in variables:
            trouvees[nom] = reste
    for v in variables:
        if v in trouvees:
            valeur = _valeur(trouvees[v])
            if valeur:
                return valeur
    return None


def mettre_a_jour(projet, catalogue, etat_obj, environ=None, config_utilisateur=None):
    """Note les déclarés dans le fichier des partenaires : `declare` ; un `declare` qui n'est plus vu devient
    `non_connecte` ; un `connecte` (confirmé) le reste. Rend {id: {nom, etat, source}} des partenaires non « non connecté »."""
    from orchestrateur.suivi import maintenant
    vus = declares(projet, environ, config_utilisateur, catalogue)
    noms = {p["id"]: p["nom"] for p in catalogue["partenaires"]}
    quand = maintenant()
    with etat_obj.transaction() as d:
        for i, source in vus.items():
            if (d["connexions"].get(i) or {}).get("etat") != "connecte":
                d["connexions"][i] = {**(d["connexions"].get(i) or {}), "etat": "declare", "source": source, "vu_le": quand}
        for i, c in d["connexions"].items():
            if c.get("etat") == "declare" and i not in vus:
                c.update(etat="non_connecte", vu_le=quand)
        return {i: {"nom": noms[i], "etat": c["etat"], "source": c.get("source")}
                for i, c in d["connexions"].items() if i in noms and c.get("etat") != "non_connecte"}
