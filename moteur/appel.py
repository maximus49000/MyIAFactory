"""La couche d'appel du moteur : un appel d'IA à contexte neuf, par `claude -p` (défaut) ou par l'API Messages.

`claude -p` est lancé avec la commande dépouillée mesurée en tâche 1 (environ 880 tokens de départ au lieu de 44 000) :
aucun outil, prompt système remplacé par la consigne, ni serveur MCP, ni réglages, ni commandes. La consigne passe par
un fichier temporaire, le dossier par l'entrée standard : rien du contenu n'est sur la ligne de commande.

Un agent de production (`outils` non vide) garde le prompt de Claude Code (il en a besoin pour ses outils), la consigne
y est ajoutée ; ses outils sont listés, tout autre geste est refusé sans attendre personne. Jamais le mode qui
contourne les autorisations.

La couche API n'est qu'une option du paramétrage (`choisir_couche`). La clé est lue dans l'environnement au moment de
l'appel seulement, jamais écrite, affichée, journalisée ni passée en argument ; elle est retirée de l'environnement de
`claude -p`, qui reste ainsi sur l'abonnement.
"""
import glob
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

MODELES = ("haiku", "sonnet", "opus")
MODELES_API = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
URL_API = "https://api.anthropic.com/v1/messages"
VERSION_API = "2023-06-01"
MAX_TOKENS_API = 16000
VARIABLE_CLE = "ANTHROPIC_API_KEY"
LIGNE_SANS_CLE = ("Les réglages demandent la clé API Anthropic pour les décisions de l'orchestrateur, mais "
                  "ANTHROPIC_API_KEY n'est pas dans l'environnement : les décisions passent par claude -p "
                  "(votre abonnement).")


class ErreurAppel(Exception):
    """L'appel n'a pas rendu de réponse utilisable. `usages` garde ce qu'il a coûté quand on le sait."""

    def __init__(self, raison, usages=None):
        super().__init__(raison)
        self.raison = raison
        self.usages = usages or []


class Reponse:
    """Le texte rendu, l'usage exact du modèle principal (`usage`), celui de chaque modèle (`usages`, le principal
    d'abord) et la session (`claude -p` seulement, pour une reprise)."""

    def __init__(self, texte, usages, session=None, cout_usd=None):
        self.texte = texte
        self.usages = usages
        self.usage = usages[0] if usages else _usage("", 0, 0, 0, 0)
        self.session = session
        self.cout_usd = cout_usd

    def __repr__(self):
        return f"Reponse({self.texte[:40]!r}, {self.usage})"


def _usage(modele, entree, sortie, lecture, ecriture):
    return {"modele": modele, "entree": int(entree or 0), "sortie": int(sortie or 0),
            "cache_lecture": int(lecture or 0), "cache_ecriture": int(ecriture or 0)}


def _total(u):
    return u["entree"] + u["sortie"] + u["cache_lecture"] + u["cache_ecriture"]


def _verifier_modele(modele, fable_accorde=False):
    """Le modèle voulu. Fable n'est permis que pour un agent dont la fiche porte l'accord du Directeur
    (`fable_accorde`, posé par `agents.executer_agent`) ; jamais pour un jugement."""
    m = (modele or "").strip().lower()
    if "fable" in m:
        if m != "fable" or not fable_accorde:
            raise ErreurAppel("Le moteur ne choisit jamais Fable.")
        return m
    if m not in MODELES:
        raise ErreurAppel(f"Modèle inconnu : {modele} (attendu : {', '.join(MODELES)}).")
    return m


def choisir_couche(reglages, environ):
    """La couche des appels de jugement : l'API seulement si les réglages l'activent **et** que la clé est là.
    Rend `(couche, ligne)` ; `ligne` est à dire une fois au bureau quand l'API est demandée sans clé."""
    demandee = ((reglages or {}).get("moteur") or {}).get("couche", "claude")
    if demandee != "api":
        return "claude", None
    if (environ.get(VARIABLE_CLE) or "").strip():
        return "api", None
    return "claude", LIGNE_SANS_CLE


def appeler(consigne, dossier, modele, *, couche="claude", executer=None, outils=None, dossier_travail=None,
            reprendre=None, delai_s=600, fable_accorde=False):
    """Un appel à contexte neuf : `consigne` (prompt système), `dossier` (le message). Lève `ErreurAppel`."""
    m = _verifier_modele(modele, fable_accorde)
    if m == "fable" and (couche != "claude" or not outils):
        raise ErreurAppel("Fable ne sert qu'à un agent de production (claude -p, avec ses outils).")
    if couche == "claude":
        return _appeler_claude(consigne, dossier, m, executer or _executer_claude, outils or [], dossier_travail,
                               reprendre, delai_s)
    if couche == "api":
        return _appeler_api(consigne, dossier, m, executer or _executer_api, delai_s)
    raise ErreurAppel(f"Couche d'appel inconnue : {couche}.")


# --- claude -p.

def trouver_claude(which=shutil.which, environ=None):
    """La commande `claude` du PATH, sinon celle que l'application Claude installe (la plus récente)."""
    chemin = which("claude")
    if chemin:
        return chemin
    environ = os.environ if environ is None else environ
    if not environ.get("APPDATA"):
        return None
    motif = os.path.join(environ["APPDATA"], "Claude", "claude-code", "*", "*", "claude.exe")
    trouves = sorted(glob.glob(motif), key=os.path.getmtime)
    return trouves[-1] if trouves else None


def _argv(claude, modele, fichier_consigne, outils, reprendre):
    argv = [claude, "-p", "--output-format", "json", "--model", modele]
    if outils:
        noms = []
        for o in outils:
            nom = o.split("(", 1)[0].strip()
            if nom not in noms:
                noms.append(nom)
        argv += ["--tools", ",".join(noms), "--allowedTools", ",".join(outils), "--permission-prompts", "none",
                 "--append-system-prompt-file", fichier_consigne]
    else:
        argv += ["--tools", "", "--system-prompt-file", fichier_consigne]
    argv += ["--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands"]
    if reprendre:
        argv += ["--resume", reprendre]
    elif not outils:
        argv.append("--no-session-persistence")
    return argv


def _executer_claude(argv, entree, env, cwd, delai_s):
    fini = subprocess.run(argv, input=entree, env=env, cwd=cwd, capture_output=True, timeout=delai_s,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return fini.returncode, fini.stdout if fini.returncode == 0 or fini.stdout else fini.stderr


def _appeler_claude(consigne, dossier, modele, executer, outils, dossier_travail, reprendre, delai_s):
    claude = trouver_claude() or "claude"
    env = {k: v for k, v in os.environ.items() if k != VARIABLE_CLE}
    with tempfile.TemporaryDirectory(prefix="moteur-") as tmp:
        fichier = os.path.join(tmp, "consigne.md")
        with open(fichier, "w", encoding="utf-8") as f:
            f.write(consigne)
        cwd = dossier_travail
        if cwd is None:
            cwd = os.path.join(tmp, "vide")
            os.mkdir(cwd)
        try:
            code, sortie = executer(_argv(claude, modele, fichier, outils, reprendre), dossier.encode("utf-8"), env,
                                    cwd, delai_s)
        except (subprocess.TimeoutExpired, TimeoutError):
            raise ErreurAppel(f"délai dépassé ({delai_s} s)")
        except OSError as e:
            raise ErreurAppel(f"claude n'a pas pu être lancé : {e}")
    if code != 0:
        raise ErreurAppel(f"claude a rendu le code {code} : {_extrait(sortie)}", _usages_claude(sortie))
    try:
        r = json.loads(sortie.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ErreurAppel(f"sortie de claude illisible : {_extrait(sortie)}")
    usages = _usages_de(r)
    if r.get("is_error") or r.get("subtype", "success") != "success":
        raise ErreurAppel(f"claude signale une erreur ({r.get('subtype')}) : {str(r.get('result', ''))[:200]}",
                          usages)
    return Reponse(r.get("result") or "", usages, r.get("session_id"), r.get("total_cost_usd"))


def _usages_de(r):
    usages = [_usage(nom, u.get("inputTokens"), u.get("outputTokens"), u.get("cacheReadInputTokens"),
                     u.get("cacheCreationInputTokens"))
              for nom, u in (r.get("modelUsage") or {}).items()]
    usages.sort(key=_total, reverse=True)
    return usages


def _usages_claude(sortie):
    try:
        return _usages_de(json.loads(sortie.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return []


def _extrait(octets):
    return octets.decode("utf-8", "replace").strip()[:300] if octets else "(rien)"


# --- API Messages (option du paramétrage).

def _executer_api(url, corps, entetes, delai_s=600):
    requete = urllib.request.Request(url, data=corps, headers=entetes, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=delai_s) as rep:
            return rep.status, rep.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _appeler_api(consigne, dossier, modele, executer, delai_s):
    cle = (os.environ.get(VARIABLE_CLE) or "").strip()
    if not cle:
        raise ErreurAppel("ANTHROPIC_API_KEY n'est pas dans l'environnement.")
    corps = json.dumps({"model": MODELES_API[modele], "max_tokens": MAX_TOKENS_API, "system": consigne,
                        "messages": [{"role": "user", "content": dossier}]}).encode("utf-8")
    entetes = {"x-api-key": cle, "anthropic-version": VERSION_API, "content-type": "application/json"}
    try:
        if executer is _executer_api:
            code, sortie = _executer_api(URL_API, corps, entetes, delai_s)
        else:
            code, sortie = executer(URL_API, corps, entetes)
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        raise ErreurAppel(_sans_cle(f"l'API n'a pas répondu : {e}", cle))
    try:
        r = json.loads(sortie.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        raise ErreurAppel(_sans_cle(f"réponse de l'API illisible (code {code})", cle))
    if code != 200:
        message = ((r.get("error") or {}).get("message") or "") if isinstance(r, dict) else ""
        raise ErreurAppel(_sans_cle(f"l'API a rendu le code {code} : {message[:200]}", cle))
    u = r.get("usage") or {}
    usages = [_usage(r.get("model") or MODELES_API[modele], u.get("input_tokens"), u.get("output_tokens"),
                     u.get("cache_read_input_tokens"), u.get("cache_creation_input_tokens"))]
    if r.get("stop_reason") in ("refusal", "max_tokens"):
        raise ErreurAppel(f"l'API s'est arrêtée ({r.get('stop_reason')})", usages)
    texte = "".join(b.get("text", "") for b in r.get("content") or [] if b.get("type") == "text")
    return Reponse(texte, usages)


def _sans_cle(texte, cle):
    return texte.replace(cle, "***") if cle else texte
