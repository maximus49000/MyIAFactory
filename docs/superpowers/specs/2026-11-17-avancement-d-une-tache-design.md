# Avancement d'une tâche sur sa fiche (conception courte)

## Pourquoi
Le Directeur ne sait pas où en est une tâche : la fiche dit seulement « au travail depuis 6 min · lance py ». Il veut, d'un
coup d'œil : **où l'agent en est exactement dans sa tâche**, **le temps passé**, **le temps restant (approximatif)** et
**si ça avance ou si c'est bloqué**. Essai réel du 2026-11-17 : t314 a paru « bloquée » alors que l'agent avait fini et
que le moteur n'avait pas lu son résultat ; rien sur la fiche ne permettait de le dire.

## Buts / hors-buts / à éviter
- Buts : les quatre réponses ci-dessus, sur la fiche de la tâche (bureau), mises à jour en direct.
- Hors-buts : prévoir précisément la fin ; changer le parcours des tâches ; remplacer le journal.
- À éviter : une estimation fausse présentée comme sûre (« inconnu » vaut mieux qu'un chiffre inventé) ; un agent qui
  dépense des tokens à rapporter son avancement ; une liste vide ou périmée affichée comme à jour.

## Approches considérées
A. Tout déduire du flux de l'agent (phases) : gratuit, mais « où exactement » reste flou.
B. L'agent tient sa liste d'avancement : exact, mais vide si l'agent oublie.
**C. Les deux (retenue par le Directeur)** : liste de l'agent quand elle existe, sinon phase déduite du flux.

## Conception
1. **Où il en est.** La consigne de l'étape demande à l'agent d'écrire, dès le début, la liste de ses points (pour une
   correction : les défauts du refus) dans `agents-en-cours/<tâche>.avancement.json`, et de cocher chaque point fait. Une
   ligne « en cours » dit ce qu'il fait. Sans liste, ou si elle n'a pas bougé depuis longtemps, la fiche affiche la
   **phase déduite du flux** (lecture, modification, compilation, tests) et dit que la liste manque.
2. **Temps passé.** Depuis le démarrage de l'agent de l'essai en cours, et, à côté, le temps cumulé de la tâche sur tous
   ses essais (reprises comprises).
3. **Temps restant.** Une fourchette (ex. « 10 à 20 min ») tirée des durées des mêmes étapes déjà terminées dans le
   projet, ajustée par la part de la liste déjà cochée. Moins de 3 durées connues : « inconnu ».
4. **Avance ou bloqué.** Trois états visibles : *avance* (action réelle récente), *commande longue en cours* (test,
   compilation : normal, avec sa durée), *sans action depuis N min, arrêt automatique à M min* (le garde-fou existant,
   montré). Ajout : *agent terminé, résultat en attente de lecture par le moteur* depuis plus de 2 min, et *moteur non
   joignable* si son processus est mort ou sans signe de vie.

## Contraintes
Un seul rédacteur par fichier (l'agent écrit sa liste, le moteur écrit le reste) ; aucun accès aux contenus de commandes
ou de fichiers (déjà la règle de `derniere_action`) ; Python 3.9 pour tout ce que lance un agent ; tests du moteur et de
l'interface ; règle globale : une seule règle, pas un cas par cas.

## Laissé au réalisateur
Format exact du fichier d'avancement, seuils (2 min, 3 durées), classement des phases, mise en page de la fiche.
