"""Le moniteur de l'orchestrateur (`lancer guetter`) : une ligne par nouvelle demande du bureau (c'est ce qui réveille
l'orchestrateur) et, toutes les 20 s, sa présence dans `presence.json` (à côté du suivi). Le moniteur vit tant que la
conversation orchestratrice vit : une présence fraîche veut dire « l'orchestrateur est en cours »."""
import json
import os
import sys
import time
from datetime import datetime

PAS_S = 2            # le journal des demandes est relu toutes les 2 s
PRESENCE_S = 20      # la présence est notée toutes les 20 s
FRAICHEUR_S = 120    # au-delà, l'orchestrateur n'est plus tenu pour présent (un moniteur réarmé, un outil appelé)


def _maintenant():
    return datetime.now().astimezone()


def ecrire_presence(presence, quand):
    tmp = presence.with_name(presence.name + ".tmp")
    tmp.write_text(json.dumps({"maj": quand.isoformat(timespec="seconds"), "pid": os.getpid()}), encoding="utf-8")
    os.replace(tmp, presence)


def _annoncer(journal, pos, sortie):
    """Annonce les lignes ajoutées après `pos` ; rend la nouvelle position."""
    try:
        taille = journal.stat().st_size
    except OSError:
        return 0
    if taille < pos:   # journal recréé ou raccourci : on repart du début
        pos = 0
    if taille == pos:
        return pos
    with open(journal, "rb") as f:
        f.seek(pos)
        brut = f.read()
    fin = brut.rfind(b"\n") + 1   # une ligne pas encore finie attend le tour suivant
    for ligne in brut[:fin].decode("utf-8", "replace").splitlines():
        try:
            d = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(d, dict):
            sortie(f"demande {d.get('id', '?')} {d.get('type', '?')}")
    return pos + fin


def guetter(journal, presence, dormir=time.sleep, horloge=_maintenant, tours=None, sortie=None):
    sortie = sortie or (lambda l: print(l, flush=True))
    pos = journal.stat().st_size if journal.exists() else 0
    derniere = None
    n = 0
    while tours is None or n < tours:
        maintenant = horloge()
        if derniere is None or (maintenant - derniere).total_seconds() >= PRESENCE_S:
            ecrire_presence(presence, maintenant)
            derniere = maintenant
        pos = _annoncer(journal, pos, sortie)
        dormir(PAS_S)
        n += 1


def present(presence, maintenant):
    """Vrai si le moniteur de l'orchestrateur a noté sa présence il y a moins de FRAICHEUR_S secondes."""
    try:
        maj = datetime.fromisoformat(json.loads(presence.read_text(encoding="utf-8"))["maj"])
        ecart = (maintenant - maj).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return -FRAICHEUR_S < ecart < FRAICHEUR_S


if __name__ == "__main__":   # pour essai : py -3.12 guetteur.py <demandes.jsonl>
    from pathlib import Path
    j = Path(sys.argv[1])
    guetter(j, j.with_name("presence.json"))
