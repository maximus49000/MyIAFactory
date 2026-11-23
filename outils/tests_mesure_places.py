"""Mesure du nombre de campagnes de tests simultanées qu'un serveur supporte (réglage `places_tests`).

    py -3.12 outils/tests_mesure_places.py --paliers 1,2,3,4
    py -3.12 outils/tests_mesure_places.py --mixte gradle:2,python:2 --dossier-gradle <projet Gradle>   # jalon J11

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


FAMILLES_MIXTES = {"python": None, "gradle": ["./gradlew", "testDebugUnitTest"], "node": ["npm", "test"]}


def lire_mixte(texte):
    """`gradle:2,python:2` -> [("gradle", 2), ("python", 2)] ; ValueError si une famille est inconnue, un nombre n'est pas
    de 1 à 4, ou si le total dépasse 4 (le plafond des places)."""
    paliers = []
    for morceau in str(texte).split(","):
        famille, _, n = morceau.strip().partition(":")
        if famille not in FAMILLES_MIXTES or not n.isdigit() or not 1 <= int(n) <= 4:
            raise ValueError(f"palier mixte refusé : {morceau!r} (famille:nombre, familles {sorted(FAMILLES_MIXTES)}, 1 à 4)")
        paliers.append((famille, int(n)))
    if not paliers or sum(n for _, n in paliers) > 4:
        raise ValueError("palier mixte refusé : de 1 à 4 campagnes en tout")
    return paliers


def mesurer_mixte(paliers, executer, horloge=time.time):
    """Lance TOUTES les campagnes du palier en même temps (`executer(famille) -> code`) ; rend
    {famille: {"durees": [...], "codes": [...]}} (jalon J11 : par exemple 2 Gradle et 2 Python)."""
    mesures = {}
    verrou = threading.Lock()

    def une(famille):
        debut = horloge()
        code = executer(famille)
        with verrou:
            m = mesures.setdefault(famille, {"durees": [], "codes": []})
            m["codes"].append(code)
            m["durees"].append(horloge() - debut)

    fils = [threading.Thread(target=une, args=(famille,)) for famille, n in paliers for _ in range(n)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    return mesures


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
    ap.add_argument("--mixte", help="paliers mixtes, ex. gradle:2,python:2 (toutes en même temps)")
    ap.add_argument("--dossier-gradle", help="projet Gradle des campagnes « gradle » d'un palier mixte")
    args = ap.parse_args(argv)
    if args.mixte:
        paliers = lire_mixte(args.mixte)
        if any(f == "gradle" for f, _ in paliers) and not args.dossier_gradle:
            ap.error("--mixte avec gradle demande --dossier-gradle")
        places = min(4, sum(n for _, n in paliers))

        def executer_mixte(famille):
            commande = FAMILLES_MIXTES[famille] or ["python3", "outils/tests_paralleles.py", "-j", str(tests_serveur.LIMITES["cpus"])]
            dossier = args.dossier_gradle if famille == "gradle" else RACINE
            return tests_serveur.executer(commande, dossier=dossier, attendre=True, forcer=True, places=places,
                                          sortie=_Collecteur(), sortie_erreur=_Collecteur())

        mesures = mesurer_mixte(paliers, executer_mixte)
        RESULTAT.parent.mkdir(parents=True, exist_ok=True)
        RESULTAT.write_text(json.dumps({"mixte": mesures}, indent=2), encoding="utf-8")
        for famille, m in mesures.items():
            print(f"{famille} x{len(m['durees'])} : médiane {statistics.median(m['durees']):.0f} s, codes {m['codes']}")
        return 0
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
