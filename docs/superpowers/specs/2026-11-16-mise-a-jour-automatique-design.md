# La skill se met à jour toute seule

Date : 2026-11-16. Statut : validé.

## Le besoin

La skill évolue sur un poste A et y est poussée sur GitHub ; un poste B qui a la skill doit le découvrir et passer au
nouveau code sans geste. Rien ne doit écraser un développement en cours sur un poste.

## Ce qui est décidé

- **Toutes les copies** se mettent à jour, **sauf celles qui ont du travail local** : elles attendent et le disent.
- **Le passage au nouveau code est automatique**, dès qu'aucun agent ne travaille.

## Qui vérifie, et quand

- **Le moteur** (un par poste) fait un `git fetch` du dépôt de la skill toutes les 15 minutes (`INTERVALLE_S`), dans
  un fil à part : un réseau lent ne retient jamais un passage. La première vérification a lieu au démarrage.
- **Le bureau**, lancé par l'installation (`outil.py bureau`), vérifie avant de démarrer : un poste rallumé sans moteur
  se met aussi à jour.

Le dépôt vérifié est celui du code qui tourne (le dossier parent de `moteur/`), donc `~/MyIAFactory/skill` ou le clone
lié par `preparer --lier`.

## Quand la copie se met à jour (`installation/mise_a_jour.py`, `verifier`)

1. `git fetch`. Échec : `injoignable`, rien ne change. Pas de branche suivie : `sans_suivi`, rien ne change.
2. Rien de neuf au distant : `a_jour`.
3. Des fichiers suivis modifiés : `bloquee` (les fichiers sont nommés). Les fichiers non suivis ne bloquent rien.
4. Des commits locaux non poussés :
   - tous dans `orchestrateur/memoire/` (leçons gardées faute de droits) : `git pull --rebase` ; un conflit est
     défait (`rebase --abort`) et donne `bloquee` ;
   - un autre fichier touché : `bloquee` (un développement non poussé).
5. Sinon : `git merge --ff-only @{u}` : `mise_a_jour`, avec la liste des commits reçus.

Jamais de `stash`, de `reset` ni de `--force`. L'état est écrit dans `~/MyIAFactory/mise-a-jour.json`
(`etat`, `message`, `version`, `commits`, `fichiers`, `t`) et une ligne va au journal du moteur.

## Le passage au nouveau code

Après une mise à jour, le moteur attend un passage où aucun agent ne travaille (aucune tâche `en_cours` dans aucun
projet, aucune installation en file ou en cours, aucun retour d'agent non lu). Alors :

1. il relance le bureau par `lanceur.lancer(relancer=True)` (un bureau lancé à la main est laissé, et c'est dit) ;
2. il se relance lui-même : il libère son verrou, démarre un nouveau moteur détaché avec la même ligne de commande,
   puis s'arrête. Le nouveau moteur prend le verrou ; s'il en trouve un autre déjà lancé, il s'efface (code 3).

## Hors champ

- Le plugin Claude Code (`/myiafactory:installer`) : il ne sert qu'à l'amorçage ; ensuite tout passe par la copie.
- Le bandeau du bureau : une étape suivante, lisant `mise-a-jour.json`.

## Tests

De vrais dépôts git locaux (un distant nu, un poste A, un poste B) : A pousse, B se met à jour ; B a un fichier modifié
et reste intact ; B a une leçon locale et passe par un rebase ; B a un développement non poussé et attend ; un conflit
est défait. Un faux moteur : pas de relance tant qu'une tâche est en cours, relance au passage libre ; aucune
vérification quand la mise à jour n'est pas branchée (les essais du moteur ne touchent jamais au vrai dépôt).

## Étapes de réalisation

1. `installation/mise_a_jour.py` (`verifier`, `ecrire_etat`) et ses tests.
2. Le moteur : `Moteur(mise_a_jour=…)`, la vérification en fil, la relance au passage libre ; `moteur/__main__.py`
   branche la vraie mise à jour et se relance quand le moteur le demande.
3. Le bureau : `outil.py bureau` vérifie avant `lanceur.lancer`.
4. Suite de tests, puis publication.
