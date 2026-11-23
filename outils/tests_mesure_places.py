"""Mesure du nombre de campagnes de tests simultanées qu'un serveur supporte (réglage `places_tests`).

    py -3.12 outils/tests_mesure_places.py --paliers 1,2,3,4

Chaque palier k lance k campagnes complètes en même temps au serveur (`tests_serveur.executer(..., forcer=True)`), relève
la durée de chacune et écrit `~/MyIAFactory/tests-places-mesure.json`. `recommander` en tire le plus grand k dont la durée
médiane reste sous 1,5 fois celle d'une campagne seule et dont la mémoire cumulée tient dans la moitié de celle du serveur.
"""
import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
RESULTAT = Path("~/MyIAFactory/tests-places-mesure.json").expanduser()
FACTEUR_DUREE = 1.5
PART_MEMOIRE = 0.5


def recommander(mesures, memoire_serveur_mo):
    """`mesures` : {k: {"durees": [s, ...], "pics_mo": [Mo, ...]}} ; rend le plus grand k acceptable, 1 au moins."""
    seule = mesures.get(1) or mesures.get("1")
    if not seule or not seule.get("durees"):
        return 1
    base = statistics.median(seule["durees"])
    meilleur = 1
    for k in sorted(int(c) for c in mesures):
        m = mesures.get(k) or mesures.get(str(k))
        if not m or not m.get("durees"):
            continue
        if statistics.median(m["durees"]) > FACTEUR_DUREE * base:
            break
        if sum(m.get("pics_mo") or []) > PART_MEMOIRE * memoire_serveur_mo:
            break
        meilleur = k
    return meilleur


class _Collecteur:
    def write(self, b):
        return len(b)

    def flush(self):
        pass


def mesurer(paliers, executer, horloge=time.time):
    """Lance, pour chaque palier k, k campagnes simultanées ; rend {k: {"durees": [...], "codes": [...]}}."""
    mesures = {}
    for k in paliers:
        durees, codes = [], []

        def une():
            debut = horloge()
            code = executer()
            codes.append(code)
            durees.append(horloge() - debut)

        fils = [threading.Thread(target=une) for _ in range(k)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        mesures[k] = {"durees": durees, "codes": codes, "pics_mo": []}
    return mesures


def principal(argv=None):
    import tests_serveur
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paliers", default="1,2,3")
    ap.add_argument("--memoire-serveur-mo", type=int, default=62 * 1024)
    args = ap.parse_args(argv)
    paliers = [int(x) for x in args.paliers.split(",") if x.strip()]
    commande = ["python3", "outils/tests_paralleles.py", "-j", str(tests_serveur.LIMITES["cpus"])]

    def executer():
        return tests_serveur.executer(commande, dossier=RACINE, attendre=True, forcer=True, places=max(paliers),
                                      sortie=_Collecteur(), sortie_erreur=_Collecteur())

    mesures = mesurer(paliers, executer)
    reco = recommander(mesures, args.memoire_serveur_mo)
    RESULTAT.parent.mkdir(parents=True, exist_ok=True)
    RESULTAT.write_text(json.dumps({"mesures": mesures, "recommandation": reco}, indent=2), encoding="utf-8")
    for k, m in mesures.items():
        print(f"{k} campagne(s) : médiane {statistics.median(m['durees']):.0f} s, codes {m['codes']}")
    print(f"Recommandation : places_tests = {reco}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
