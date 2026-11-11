"""« Lancer l'orchestrateur » (essai réel) : le seul geste du bureau qui agit lui-même, et seulement sur un clic.

Il ouvre une fenêtre de terminal visible où `claude` démarre, dans le dossier du projet, sur le modèle de
l'orchestrateur, avec le message d'ouverture. Sans `claude`, rien ne démarre : la réponse donne le message à coller dans
une nouvelle conversation et la commande pour installer `claude`.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

INSTALLER_CLAUDE = "npm install -g @anthropic-ai/claude-code"


def _projet_de(factory_json):
    """Le dossier du projet : celui qui contient `.factory/`, sinon celui du fichier de factory."""
    d = factory_json.parent
    return d.parent if d.name == ".factory" else d


def _ps(texte):
    return "'" + str(texte).replace("'", "''") + "'"


def ouvrir_terminal(claude, modele, message, dossier):
    """Windows : une console PowerShell visible, qui reste ouverte. Le message passe par un fichier (aucun
    guillemet à échapper dans une ligne de commande)."""
    fichier = Path("~/MyIAFactory/orchestrateur-message.txt").expanduser()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(message, encoding="utf-8")
    commande = (f"& {_ps(claude)} --model {modele} (Get-Content -Raw -Encoding UTF8 -LiteralPath {_ps(fichier)})")
    subprocess.Popen(["powershell", "-NoExit", "-NoProfile", "-Command", commande], cwd=str(dossier),
                     creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)


def demarrer(reglages, trouver=shutil.which, ouvrir=ouvrir_terminal, windows=None):
    """Rend `{"ok", "message", "a_copier"?}`."""
    factory_json = Path(reglages).parent / "factory.json"
    try:
        f = json.loads(factory_json.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {"ok": False, "message": "Aucun fichier de factory lisible à côté des réglages : ouvrez vous-même "
                                        "la conversation orchestratrice."}
    from installation.mise_en_place import message_orchestrateur   # le même message qu'à l'installation
    modele = str(f.get("modele_orchestrateur") or "Sonnet")
    message = message_orchestrateur(factory_json)
    claude = trouver("claude")
    windows = sys.platform == "win32" if windows is None else windows
    if not claude or not windows:
        quoi = ("La commande claude n'est pas installée (" + INSTALLER_CLAUDE + ")") if not claude else \
            "Le lancement automatique ne marche que sous Windows"
        return {"ok": False, "a_copier": message,
                "message": f"{quoi} : ouvrez une nouvelle conversation Claude dans {_projet_de(factory_json)}, sur "
                           f"{modele}, et collez-y le message ci-dessous."}
    ouvrir(claude, modele.lower(), message, _projet_de(factory_json))
    return {"ok": True, "message": f"L'orchestrateur démarre dans une nouvelle fenêtre ({modele})."}
