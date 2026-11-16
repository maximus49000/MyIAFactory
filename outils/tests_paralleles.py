"""Lance la suite de tests en parallèle, autant de morceaux à la fois que de cœurs (réglable).

    py -3.12 outils/tests_paralleles.py                 # toute la suite
    py -3.12 outils/tests_paralleles.py -j 4            # 4 morceaux à la fois
    py -3.12 outils/tests_paralleles.py orch_memoire    # les modules dont le nom contient ce texte
    py -3.12 outils/tests_paralleles.py --lents 15      # les 15 morceaux les plus longs, à la fin

Rien à installer : la bibliothèque standard seule. Un morceau est un module de test, ou une classe de test pour les
modules longs (plus de `SEUIL_DECOUPE_S` lors du dernier passage) : un gros module ne tient plus toute la suite à lui
seul. Chaque morceau tourne dans son propre processus, comme `py -3.12 -m unittest tests.<module>[.<Classe>]` : les
variables d'environnement qu'un test modifie ne débordent pas sur un autre. Les morceaux les plus longs connus
(fichier `.durees-tests.json`, hors dépôt) partent en premier.

Le dossier temporaire passé aux tests est écrit en chemin long : sous Windows, un TEMP en nom court (`NOM~1.EXT`)
fait échouer les tests qui comparent des chemins. Un morceau en échec est relancé seul une fois, à la fin : s'il passe,
il est signalé « instable » (sensible à la charge, souvent un test de chronométrage) ; sinon c'est un vrai échec, et
le code de sortie vaut 1.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DUREES = RACINE / ".durees-tests.json"
DELAI_S = 1800
SEUIL_DECOUPE_S = 40


def modules(filtres):
    noms = sorted(p.stem for p in (RACINE / "tests").glob("test_*.py"))
    return [n for n in noms if not filtres or any(f in n for f in filtres)]


def classes(module):
    """Les classes de test (`unittest.TestCase`) définies dans le module et qui ont au moins un test. Une exception ou
    une classe d'aide du module n'est pas un morceau (`unittest` la refuserait). Module impossible à importer : rien,
    il reste entier et son erreur sera dite par son propre passage."""
    import importlib
    import unittest
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    try:
        mod = importlib.import_module(f"tests.{module}")
    except Exception:
        return []
    chargeur = unittest.TestLoader()
    return [nom for nom, c in vars(mod).items()
            if isinstance(c, type) and issubclass(c, unittest.TestCase) and c.__module__ == mod.__name__
            and chargeur.getTestCaseNames(c)]


def morceaux(liste, connues, decouper=False):
    """Avec `decouper`, les modules longs au dernier passage sont découpés par classe ; sinon tout reste entier.
    Mesure (8 cœurs, Windows) : découper a doublé la durée (1 016 s contre 453 s), trop de classes gourmandes en
    accès disque tournant ensemble ; c'est donc un choix, pas le défaut."""
    if not decouper:
        return list(liste)
    sortie = []
    for m in liste:
        long = connues.get(m, 0) > SEUIL_DECOUPE_S
        noms = classes(m) if long else []
        sortie += [f"{m}.{c}" for c in noms] if noms else [m]
    return sortie


def _lire_durees():
    try:
        return json.loads(DUREES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _environnement():
    temp = str(Path(tempfile.gettempdir()).resolve())   # le chemin long, même si TEMP est en nom court
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "TEMP": temp, "TMP": temp, "TMPDIR": temp}


def lancer(morceau, env):
    debut = time.monotonic()
    try:
        p = subprocess.run([sys.executable, "-m", "unittest", f"tests.{morceau}"], cwd=RACINE, capture_output=True,
                           timeout=DELAI_S, env=env, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        code, sortie = p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        code, sortie = 1, f"Délai dépassé ({DELAI_S} s)."
    m = re.search(r"Ran (\d+) tests?", sortie)
    if code == 5 and "NO TESTS RAN" in sortie:   # une classe de base sans test : rien à faire, pas un échec
        code = 0
    return morceau, code, time.monotonic() - debut, int(m.group(1)) if m else 0, sortie


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("filtres", nargs="*", help="textes contenus dans le nom des modules à lancer")
    a.add_argument("-j", type=int, default=os.cpu_count() or 4, help="morceaux lancés à la fois (défaut : les cœurs)")
    a.add_argument("--lents", type=int, default=10, help="nombre de morceaux les plus longs à afficher")
    a.add_argument("--decouper", action="store_true", help="découper les modules longs par classe de test")
    o = a.parse_args(argv)
    liste = modules(o.filtres)
    if not liste:
        print("Aucun module de test ne correspond.")
        return 1
    connues, env = _lire_durees(), _environnement()
    parts = morceaux(liste, connues, o.decouper)
    parts.sort(key=lambda n: -connues.get(n, 1e9))   # inconnus d'abord (prudence), puis les plus longs
    debut, resultats, echecs = time.monotonic(), [], []
    print(f"{len(liste)} modules en {len(parts)} morceaux, {o.j} à la fois.", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, o.j)) as pool:
        for f in as_completed([pool.submit(lancer, n, env) for n in parts]):
            morceau, code, duree, nb, sortie = f.result()
            resultats.append((morceau, code, duree, nb))
            print(f"[{len(resultats)}/{len(parts)}] {'ok' if code == 0 else 'ÉCHEC':5} {duree:7.1f} s  {nb:4} tests  "
                  f"{morceau}", flush=True)
            if code != 0:
                echecs.append(morceau)
    instables, vrais = [], []
    for morceau in sorted(echecs):   # relancé seul : la charge parallèle n'est plus en cause
        _, code, duree, _, sortie = lancer(morceau, env)
        print(f"relance seule : {'ok' if code == 0 else 'ÉCHEC':5} {duree:7.1f} s  {morceau}", flush=True)
        (instables if code == 0 else vrais).append((morceau, sortie))
    total = time.monotonic() - debut
    for m, _, d, _ in resultats:
        connues[m] = round(d, 1)
    for m in liste:   # la durée d'un module découpé : la somme de ses classes, pour le prochain découpage
        sous = [d for k, _, d, _ in resultats if k.startswith(m + ".")]
        if sous:
            connues[m] = round(sum(sous), 1)
    try:
        DUREES.write_text(json.dumps(connues, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    if o.lents:
        print(f"\nLes {o.lents} morceaux les plus longs :")
        for m, _, d, nb in sorted(resultats, key=lambda r: -r[2])[:o.lents]:
            print(f"  {d:7.1f} s  {nb:4} tests  {m}")
    for morceau, sortie in vrais:
        print(f"\n===== {morceau} =====\n{sortie[-4000:]}")
    cumul = sum(r[2] for r in resultats)
    print(f"\n{sum(r[3] for r in resultats)} tests ; {len(vrais)} morceau(x) en échec"
          + (f", {len(instables)} instable(s) sous charge ({', '.join(m for m, _ in instables)})" if instables else "")
          + f" ; {total:.0f} s au total ({cumul:.0f} s cumulées).")
    return 1 if vrais else 0


if __name__ == "__main__":
    sys.exit(main())
