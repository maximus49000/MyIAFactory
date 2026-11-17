# Développer MyIAFactory

## Les tests

- **Une seule campagne de tests à la fois sur le poste.** Deux suites lancées ensemble se disputent la mémoire, le
  disque et le processeur : chacune devient jusqu'à dix fois plus lente (mesure : 1 861 s au lieu de 253 s).
- **Toujours passer par le lanceur**, jamais `python -m unittest discover` ni `pytest` directement : il prend le verrou
  du poste (`~/MyIAFactory/tests-en-cours.json`) et attend la fin d'une autre campagne, la sienne ou une suite lancée
  à la main.
- **Les agents des projets passent par le même verrou** : `python lancer.py tests --dossier <d> -- <commande>` (consigne
  de départ de tout agent local, `orchestrateur/depart.py`). Les suites `vitest`, `jest`, `playwright test`, `mocha`
  lancées sans lui sont repérées et attendues, comme `unittest` et `pytest`.

```
py -3.12 outils/tests_paralleles.py --touches     # au quotidien : seulement les tests touchés par vos changements
py -3.12 outils/tests_paralleles.py               # avant de pousser : toute la suite (environ 4 minutes)
py -3.12 outils/tests_paralleles.py orch_memoire  # un module précis
```

- **Un projet dont des actions sont déportées sur GitHub** : ses agents les lancent par `python lancer.py deporter <type> …`
  (le message de départ donne la commande exacte ; voir `docs/deport.md`), jamais directement.
- `--sans-attendre` refuse (code 3) au lieu d'attendre ; utile dans un script qui ne doit pas rester bloqué.
- Un morceau en échec est relancé seul : « instable » s'il passe alors (sensible à la charge), vrai échec sinon.
