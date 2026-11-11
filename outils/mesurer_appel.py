"""Mesure le coût d'un appel `claude -p` vide (tâche 1 du plan de l'orchestrateur procédural).

Lance 3 fois, sur Haiku puis Sonnet, la commande dépouillée retenue pour les appels de jugement, avec la consigne
« Réponds {"ok":true} », dans un dossier temporaire vide ; puis une fois la commande par défaut (`claude -p` seul),
pour comparaison. Affiche par appel les tokens d'entrée, de cache (lecture, écriture), de sortie et `total_cost_usd`.

    py -3.12 outils/mesurer_appel.py [--claude CHEMIN] [--fois 3]

Aucune clé n'est lue ni affichée : l'appel passe par la connexion de Claude Code.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

CONSIGNE = "Tu réponds seulement par du JSON, sans rien autour."
PROMPT = 'Réponds {"ok":true}'


def trouver_claude():
    """La commande `claude` du PATH, sinon celle installée par l'application Claude (la plus récente)."""
    chemin = shutil.which("claude")
    if chemin:
        return chemin
    racine = os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code")
    trouves = sorted(glob.glob(os.path.join(racine, "*", "*", "claude.exe")), key=os.path.getmtime)
    return trouves[-1] if trouves else None


def argv_depouille(claude, modele, fichier_consigne):
    return [claude, "-p", "--output-format", "json", "--model", modele,
            "--tools", "", "--system-prompt-file", fichier_consigne,
            "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
            "--no-session-persistence"]


def argv_defaut(claude, modele):
    return [claude, "-p", "--output-format", "json", "--model", modele, "--no-session-persistence"]


def lancer(argv, dossier):
    fini = subprocess.run(argv, input=PROMPT.encode("utf-8"), cwd=dossier, capture_output=True, timeout=300)
    if fini.returncode != 0:
        return {"erreur": fini.stderr.decode("utf-8", "replace")[:300] or fini.stdout.decode("utf-8", "replace")[:300]}
    sortie = json.loads(fini.stdout.decode("utf-8"))
    u = sortie.get("usage", {})
    return {"entree": u.get("input_tokens", 0), "cache_lecture": u.get("cache_read_input_tokens", 0),
            "cache_ecriture": u.get("cache_creation_input_tokens", 0), "sortie": u.get("output_tokens", 0),
            "cout_usd": sortie.get("total_cost_usd", 0.0), "texte": sortie.get("result", "")}


def ligne(nom, r):
    if "erreur" in r:
        return f"  {nom:<10} ERREUR {r['erreur']}"
    total = r["entree"] + r["cache_lecture"] + r["cache_ecriture"]
    return (f"  {nom:<10} entrée {r['entree']:>6}  cache lu {r['cache_lecture']:>6}  cache écrit {r['cache_ecriture']:>6}"
            f"  sortie {r['sortie']:>4}  (total entrée {total:>6})  {r['cout_usd']:.5f} $  → {r['texte'][:30]!r}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--claude", default=None)
    p.add_argument("--fois", type=int, default=3)
    a = p.parse_args()
    claude = a.claude or trouver_claude()
    if not claude:
        sys.exit("La commande claude est introuvable.")
    with tempfile.TemporaryDirectory() as dossier:
        vide = os.path.join(dossier, "vide")
        os.mkdir(vide)
        fichier = os.path.join(dossier, "consigne.md")
        with open(fichier, "w", encoding="utf-8") as f:
            f.write(CONSIGNE)
        print("Commande retenue :", " ".join(repr(x) if x == "" else x for x in argv_depouille("claude", "<modele>", "<consigne>")))
        for modele in ("haiku", "sonnet"):
            print(f"\n{modele} — commande dépouillée")
            for i in range(a.fois):
                print(ligne(f"appel {i + 1}", lancer(argv_depouille(claude, modele, fichier), vide)))
            print(f"{modele} — commande par défaut (comparaison)")
            print(ligne("défaut", lancer(argv_defaut(claude, modele), vide)))


if __name__ == "__main__":
    main()
