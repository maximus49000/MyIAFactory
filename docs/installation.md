# Installer et configurer le bureau vivant

> L'installation en tant que skill Claude arrivera avec le projet 4 ; ce manuel sera alors complété. Pour l'instant, on lance le bureau à la main, depuis une copie de ce dépôt.

## Ce qu'il faut

- Windows (la mesure de charge de l'ordinateur n'existe que sous Windows ; ailleurs, le bureau fonctionne mais la barre affiche « Mesure indisponible »).
- Python 3.12, lancé par `py -3.12`.
- Un navigateur récent.

Rien d'autre : pas de paquet à installer, ni Python ni npm. three.js est déjà copié dans le dépôt.

## Essayer avec la démo

Depuis la racine du dépôt :

```bash
py -3.12 lancer.py serveur --reglages exemples/demo/reglages.json
```

Le terminal affiche `Le bureau est ouvert sur http://127.0.0.1:8770/`. Ouvrez cette adresse dans le navigateur (l'adresse `http://localhost:8770/` marche aussi ; aucune autre n'est acceptée).

Ce qu'on doit voir : le bâtiment en 3D isométrique, une pièce par service (Métier, Dev, QA, Intégration, Facturation), le coin café, le bureau du Directeur avec une pastille « 2 » (deux décisions en attente), le chef près du Kanban central rempli de post-its, le voyant de la factory et la barre de charge en haut. Survolez un agent pour voir sa carte, cliquez sur une pièce pour ouvrir son panneau à droite, sur un post-it pour le détailler. Échap ferme.

**Pourquoi les agents de la démo sont « sans nouvelles »** : les dates `maj` du relevé de démonstration sont fixes, donc de plus en plus anciennes. Le bureau ne prétend jamais qu'un agent travaille si rien n'a bougé depuis plus que le délai de fraîcheur (30 minutes par défaut) : ils restent à leur poste, avec une bulle grisée. Pour les voir au travail, ouvrez `exemples/demo/releve.json` et mettez à une tâche active une `maj` récente (par exemple l'heure qu'il est) ; pour voir un déplacement, changez en plus sa `colonne`. Dans les secondes qui suivent, l'agent marche jusqu'au Kanban et déplace son post-it. Passez `factory.etat` à `"en pause"` : le voyant change et la lumière baisse.

Arrêter le bureau : `Ctrl+C` dans le terminal.

## Brancher son projet

Un projet réel se branche **depuis son propre dépôt** : rien n'est à modifier ici.

1. Dans le dossier du projet, créez un dossier `.factory/` et ajoutez `.factory/` au `.gitignore` du projet (on n'y range que des choses propres à la machine : réglages, équipe, historique de charge).
2. Écrivez `.factory/reglages.json`. Le plus simple, un relevé tenu à jour dans un fichier :

   ```json
   {"releve": {"fichier": "releve.json"}}
   ```

   ou un relevé obtenu par une commande que le bureau lance :

   ```json
   {"releve": {"commande": ["python", "mon_releve.py"], "dossier": ".."}}
   ```

   Les chemins relatifs sont résolus depuis le dossier du fichier de réglages (ici `.factory/`).
3. Faites produire le relevé par le projet : le format est décrit dans [releve.md](releve.md). Écrivez le fichier par remplacement atomique.
4. Lancez le bureau en pointant sur ces réglages, depuis ce dépôt :

   ```bash
   py -3.12 lancer.py serveur --reglages <chemin du projet>/.factory/reglages.json
   ```

Le bureau crée lui-même, à côté des réglages, `equipe.json` (prénoms, couleurs) et `charge-historique.jsonl` (historique de charge, 7 jours).

## Les réglages

Fichier JSON ; toutes les clés sont facultatives sauf `releve`.

| Clé | Défaut | Effet |
|---|---|---|
| `port` | `8770` | Port du serveur (il n'écoute que sur `127.0.0.1`). |
| `charge_max` | `75` | Charge maximum (en %) sous laquelle on a le droit de lancer une nouvelle étape locale. Entre 30 et 95. Se règle aussi depuis la page. |
| `fraicheur_min` | `30` | Minutes sans mise à jour au-delà desquelles un agent actif est « sans nouvelles ». Chaque titulaire du relevé peut avoir le sien (`fraicheur_min`). |
| `releve.fichier` | — | Chemin du relevé, relu toutes les quelques secondes. |
| `releve.commande` | — | Commande (liste de mots, sans shell, 10 s au plus) qui écrit le relevé sur sa sortie standard en UTF-8. |
| `releve.dossier` | dossier des réglages | Dossier où la commande est lancée. |
| `actions.commande` | — | Commande d'actions (liste de mots, sans shell, 10 s au plus) : elle reçoit chaque demande en JSON UTF-8 sur son entrée standard. Voir « Faire agir le bureau ». |
| `actions.dossier` | dossier des réglages | Dossier où la commande d'actions est lancée. |
| `images.racines` | — | Dossiers (relatifs au dossier des réglages) d'où le bureau peut servir les images des tâches. |

## Faire agir le bureau

Par défaut, le bureau regarde seulement. Pour qu'il transmette les gestes de l'utilisateur à votre projet (mettre la factory en pause, déplacer une tâche, faire un retour, valider une leçon), suivez ces étapes. Le bureau ne change jamais lui-même l'état de la factory : il dépose des **demandes**, et c'est votre projet qui agit.

1. Faites produire un relevé `version` 2 (voir [releve.md](releve.md)) avec, selon vos besoins, `actions` (les boutons), `types`, `lecons`, et le détail des tâches (`journal`, `images`, `liens`, `retours`, `bloquee`).
2. Écrivez une commande d'actions : un programme qui lit **une demande JSON en UTF-8 sur son entrée standard**, l'applique, et rend le code 0 (ou un autre code, avec une ligne d'explication sur sa sortie, pour la refuser). Le modèle à suivre : [`exemples/demo/actions.py`](../exemples/demo/actions.py).
3. Déclarez-la dans les réglages, avec les dossiers d'images si les tâches en ont :

   ```json
   {
     "releve": {"fichier": "releve.json"},
     "actions": {"commande": ["python", "actions.py"], "dossier": "."},
     "images": {"racines": ["images"]}
   }
   ```

4. Relancez le bureau. Les boutons apparaissent à droite du voyant ; « Toutes les tâches » ouvre la vue liste ; un clic sur un post-it ouvre le détail de la tâche ; un clic sur le Directeur ouvre ses leçons à valider, les retours sans réponse et les tâches bloquées.

Pour essayer sans rien brancher (les gestes de la démo réécrivent son `releve.json`, donc ne travaillez pas sur l'original), copiez `exemples/demo/` ailleurs et lancez le bureau sur la copie (`py -3.12 lancer.py serveur --reglages <copie>/reglages.json`) : « Pause », un déplacement, un retour et un verdict modifient `releve.json` de la copie, et la scène suit au relevé suivant.

Le serveur reste réservé à votre machine : `POST /api/demande` exige les mêmes en-têtes que le réglage de charge, et les demandes passent une à une.

## L'équipe

Le relevé ne donne pas de prénom (sauf, en version 2, un `prenom` facultatif par titulaire, qui n'est pas écrit dans ce fichier) : le bureau en attribue un à chaque clé de titulaire, avec une couleur, et le retient dans `equipe.json`, à côté des réglages. Un agent qui revient retrouve son prénom.

Pour changer un prénom, une couleur ou un modèle, éditez ce fichier (le fichier est lu au lancement : arrêtez le bureau et relancez-le après une modification) :

```json
{"agents": {"dev:1": {"prenom": "Zoé", "couleur": "#2f6fd0", "modele": "Haiku"}}}
```

Vos valeurs ne sont jamais réécrites. Le chef s'appelle « Chef » tant qu'on ne change rien.

## La charge

- **Ce qui est mesuré** : la charge réelle de cet ordinateur, la plus élevée entre le processeur (lissé sur une minute, pour ignorer les pics) et la mémoire. Les sessions cloud n'utilisent pas la machine : elles ne comptent pas.
- **La barre du haut** : le trait marque la charge maximum réglée ; la barre devient rouge au-dessus. Survolez-la pour le détail.
- **Régler le maximum** : cliquez sur la pièce Facturation (ou, si le projet n'a pas de service `facturation`, sur la direction), curseur de 30 à 95, puis « Enregistrer ». Le réglage est écrit dans `reglages.json`.
- **« Me conseiller »** : propose une valeur et l'explique en une phrase. Sans assez de mesures avec des agents locaux au travail, il part des seules caractéristiques de la machine (cœurs, mémoire) et reste prudent ; ensuite il s'appuie sur l'historique. « Appliquer » enregistre la valeur.
- **La commande `charge`** : un orchestrateur l'appelle avant de lancer une étape locale.

  ```bash
  py -3.12 lancer.py charge --reglages <chemin>/reglages.json
  ```

  Elle mesure pendant 5 secondes, puis affiche `ok : charge 42 % (max 75 %)` et rend le code 0 (on peut y aller), ou affiche `attendre : charge 83 % (max 75 %)` et rend le code 1 (trop chargé). Hors Windows : `mesure indisponible, on laisse passer`, code 0.

  Ligne type à ajouter aux consignes d'un orchestrateur :

  > Avant de lancer une étape locale, exécute `py -3.12 <chemin du bureau>/lancer.py charge --reglages <chemin>/reglages.json`. Si le code de retour est 1, attends une minute et recommence ; ne lance l'étape que sur le code 0. Les étapes cloud ne sont pas concernées.

## En cas de problème

- **« Impossible de démarrer le serveur »** : le port est déjà pris (un autre bureau tourne, ou un autre programme). Fermez l'autre, ou mettez un autre `port` dans les réglages.
- **Bandeau « Relevé indisponible »** : le relevé est absent, incomplet (fichier écrit à moitié) ou invalide, ou la commande a échoué ou dépassé 10 secondes. Le bandeau donne la raison. La scène garde sa dernière image ; elle repart toute seule dès que le relevé redevient lisible.
- **Barre « Mesure indisponible »** : le système n'est pas Windows, ou la mesure a échoué. Le bureau fonctionne ; la commande `charge` laisse alors passer.
- **Page blanche ou « Hôte refusé »** : ouvrez la page par `http://127.0.0.1:<port>/` ou `http://localhost:<port>/` ; toute autre adresse est refusée. Vérifiez aussi que le terminal du serveur est toujours ouvert.
- **Un agent n'a pas la bonne couleur ou le bon prénom** : voir « L'équipe ».
