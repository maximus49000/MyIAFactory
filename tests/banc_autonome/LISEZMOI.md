# Banc de cas rejoués de « Claude autonome »

Quinze cas figés (dix réels de l'essai FM_Stats du 2026-11-26, cinq négatifs ou de règle) : chacun est le dossier que
reçoit `decider_autonome`, la réponse attendue et une note « pourquoi ». Le banc mesure si le jugement ressemble à celui
d'un humain expérimenté, avant et après chaque amélioration.

## Test rapide (sans appel)

Fait partie de la suite : `py -3.12 outils/tests_paralleles.py --serveur --touches` (module `test_banc_autonome`). Il
vérifie le chargeur, la forme des dossiers, que la réponse simulée de chaque cas est acceptée par `jugement.valider`,
notée juste, et transformée en demande par le moteur (`regles._demande_autonome`), et que la notation rend faux les
mauvais verdicts.

## Rejeu avec le vrai jugement

```
py -3.12 -m tests.banc_autonome                 # tous les cas : attendu / obtenu / juste ou faux, puis le score
py -3.12 -m tests.banc_autonome --cas recette   # un sous-ensemble
py -3.12 -m tests.banc_autonome --modele opus   # un autre modèle (jamais Fable)
py -3.12 -m tests.banc_autonome --simule        # sans appel : essai de la commande (ce n'est pas une mesure)
```

Il appelle `moteur.jugement.juger("decider_autonome", …)` : le programme `claude` doit être installé et connecté (un
appel par cas de jugement, donc un coût en jetons). S'il est introuvable, la commande le dit et ne mesure rien (code 2).
Un appel qui échoue compte faux. Pour comparer deux versions du moteur, lancer le banc sur chaque branche et comparer
les scores ; les réponses d'IA varient d'un essai à l'autre : relancer 2 ou 3 fois avant de conclure.

## Ajouter un cas dès qu'une erreur est constatée

1. Prendre le dossier réel : la décision rendue au bureau (ou le dossier du journal du jugement) ; le copier dans un
   nouveau `cas/NN_nom.json` (`id` = nom du fichier sans `.json`). Remplacer tout identifiant réel (adresse IP, clé,
   jeton, nom de projet) par une valeur factice (`https://service.exemple`).
2. Écrire `attendu` (voir l'en-tête de `__init__.py` : verdicts acceptables, mots que le texte doit évoquer ou éviter),
   `note` (pourquoi cette réponse est la bonne), `simule` (une réponse valable, pour le test rapide) et `negatif: true`
   si c'est une chose que Claude autonome ne doit jamais faire.
3. Lancer le test rapide, puis `py -3.12 -m tests.banc_autonome --cas NN` : le cas doit être faux avant le correctif et
   juste après.
