"""Les tokens exacts, lus dans les transcriptions locales de Claude Code (`~/.claude/projects/<dossier>/`).

Claude Code y garde chaque conversation (`<session>.jsonl`) et chaque sous-agent
(`<session>/subagents/agent-<id>.jsonl`), avec l'usage de chaque réponse du modèle. On n'en lit que les compteurs et
le modèle : jamais le contenu. Un message rejoué (même identifiant) ne compte qu'une fois.
"""
import json
import re
from pathlib import Path

MOTIF_AGENT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEBUT_LU = 256 * 1024   # pour reconnaître une conversation orchestratrice, on ne lit que son début
CHAMPS = (("input_tokens", "entree"), ("output_tokens", "sortie"), ("cache_read_input_tokens", "cache_lecture"),
          ("cache_creation_input_tokens", "cache_ecriture"))


def racine():
    return Path("~/.claude/projects").expanduser()


def nom_dossier(projet):
    """Le dossier de Claude Code pour un dossier de travail : chaque caractère hors [A-Za-z0-9] devient « - »."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(projet))


def compter(fichier):
    """{modèle: {entree, sortie, cache_lecture, cache_ecriture}} d'une transcription."""
    vus, total = set(), {}
    with open(fichier, encoding="utf-8", errors="replace") as f:
        for brut in f:
            try:
                d = json.loads(brut)
            except ValueError:
                continue
            m = d.get("message") if isinstance(d, dict) else None
            if d.get("type") != "assistant" or not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
                continue
            if m.get("id") in vus:
                continue
            vus.add(m.get("id"))
            c = total.setdefault(str(m.get("model") or "inconnu"), {v: 0 for _, v in CHAMPS})
            for k, v in CHAMPS:
                n = m["usage"].get(k)
                c[v] += n if isinstance(n, int) and n > 0 else 0
    return total


def sous_agent(agent_id, racine=None):
    """La transcription du sous-agent `agent_id`, ou None."""
    if not isinstance(agent_id, str) or not MOTIF_AGENT.match(agent_id):
        return None
    r = Path(racine) if racine else globals()["racine"]()
    for f in r.glob(f"*/*/subagents/agent-{agent_id}.jsonl"):
        return f
    return None


def orchestrations(projet, factory_json, racine=None):
    """Les conversations orchestratrices de ce projet : celles qui s'ouvrent sur le message d'orchestrateur qui
    nomme ce fichier de factory."""
    r = Path(racine) if racine else globals()["racine"]()
    d = r / nom_dossier(projet)
    marque = json.dumps(str(factory_json))[1:-1]   # le chemin tel qu'il paraît dans le JSON (barres échappées)
    trouvees = []
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        try:
            with open(f, encoding="utf-8", errors="replace") as h:
                debut = h.read(DEBUT_LU)
        except OSError:
            continue
        if "Tu es l'orchestrateur du projet" in debut and marque in debut:
            trouvees.append(f)
    return trouvees
