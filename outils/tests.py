"""Toute la suite de tests, en parallèle : les tests Python (une classe de test par processus, sur tous les cœurs),
puis, seuls, ceux qui mesurent des durées et ceux de la page (`node --test`).

    py -3.12 outils/tests.py                  # tout
    py -3.12 outils/tests.py moteur orch_suivi  # seulement les fichiers tests/test_*<mot>*.py (pas la page)
    py -3.12 outils/tests.py --sans-page      # sans les tests de la page
    py -3.12 outils/tests.py -j 4             # 4 processus au plus

Affiche le détail de chaque échec, puis une ligne de bilan. Code de sortie : 0 tout est vert, 1 sinon.
"""
import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
TESTS = RACINE / "tests"
# Les classes qui mesurent une durée : lancées seules, après les autres (la machine chargée les ferait échouer à tort).
SEULES = {"tests.test_inst_examen.TestExamen"}
# Les classes longues : une unité par test, pour qu'elles ne fixent pas la durée de toute la suite.
DECOUPEES = {"tests.test_orch_interface.TestVerificateur", "tests.test_orch_memoire.TestMemoire",
             "tests.test_serveur.TestServeur", "tests.test_demo_v4.TestProjetNeuf", "tests.test_inst_outil.TestOutil"}


def unites(mots=()):
    """[(nom unittest, taille)] : une par classe qui porte des `test_…`, la plus grosse d'abord (elle part en premier)."""
    rendu = []
    for fichier in sorted(TESTS.glob("test_*.py")):
        if mots and not any(m in fichier.stem for m in mots):
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in arbre.body:
            if isinstance(noeud, ast.ClassDef):
                tests = [x.name for x in noeud.body if isinstance(x, ast.FunctionDef) and x.name.startswith("test")]
                nom = f"tests.{fichier.stem}.{noeud.name}"
                if nom in DECOUPEES:
                    rendu += [(f"{nom}.{x}", 1) for x in tests]
                elif tests:
                    rendu.append((nom, len(tests)))
    return sorted(rendu, key=lambda u: -u[1])


def _python(nom):
    debut = time.time()
    p = subprocess.run([sys.executable, "-m", "unittest", nom], cwd=str(RACINE), capture_output=True,
                       stdin=subprocess.DEVNULL, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    texte = p.stderr.decode("utf-8", "replace")
    m = re.search(r"Ran (\d+) tests?", texte)
    return {"nom": nom, "ok": p.returncode == 0, "tests": int(m.group(1)) if m else 0,
            "duree": time.time() - debut, "texte": texte}


def _page():
    debut = time.time()
    node = shutil.which("node")
    if not node:
        return {"nom": "page (node --test)", "ok": False, "tests": 0, "duree": 0.0, "texte": "node introuvable"}
    fichiers = sorted(str(p) for p in (RACINE / "bureau" / "web" / "tests").glob("*.test.js"))
    p = subprocess.run([node, "--test", *fichiers], cwd=str(RACINE), capture_output=True, stdin=subprocess.DEVNULL)
    texte = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    m = re.search(r"^# tests (\d+)", texte, re.M)
    return {"nom": "page (node --test)", "ok": p.returncode == 0, "tests": int(m.group(1)) if m else 0,
            "duree": time.time() - debut, "texte": texte}


def main(argv=None):
    a = argparse.ArgumentParser(description="La suite de tests en parallèle.")
    a.add_argument("mots", nargs="*", help="ne lancer que les fichiers tests/test_*<mot>*.py")
    a.add_argument("-j", type=int, default=os.cpu_count() or 4, help="processus au plus (défaut : un par cœur)")
    a.add_argument("--sans-page", action="store_true", help="sans les tests de la page")
    o = a.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    debut = time.time()
    liste = unites(o.mots)
    with ThreadPoolExecutor(max(1, o.j)) as ex:
        resultats = list(ex.map(_python, [n for n, _ in liste if n not in SEULES]))
    # puis, la machine au repos, ce qui mesure des durées : les classes `SEULES` et la page (elle a des seuils en ms)
    resultats += [_python(n) for n, _ in liste if n in SEULES]
    if not (o.mots or o.sans_page):
        resultats.append(_page())
    echecs = [r for r in resultats if not r["ok"]]
    for r in echecs:
        print(f"\n=== ÉCHEC : {r['nom']} ===\n{r['texte'].rstrip()}")
    lentes = sorted(resultats, key=lambda r: -r["duree"])[:3]
    print("\nLes plus longues : " + ", ".join(f"{r['nom']} {r['duree']:.0f} s" for r in lentes))
    total = sum(r["tests"] for r in resultats)
    bilan = "vert" if not echecs else f"{len(echecs)} unité(s) en échec"
    print(f"{total} tests, {len(resultats)} unités, {time.time() - debut:.0f} s : {bilan}.")
    return 0 if not echecs else 1


if __name__ == "__main__":
    sys.exit(main())
