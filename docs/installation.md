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
py -3.12 lancer.py serveur --bureau exemples/bureau.json
```

Le bureau suit alors **deux projets inventés** : « Démo » (une application de gestion, avec une fonctionnalité en
série et son catalogue) et « Démo B » (une fonctionnalité en cadrage). Le sélecteur en haut à gauche passe de l'un à
l'autre (voir « Plusieurs projets »). Pour un seul projet, sans sélecteur, comme avant :

```bash
py -3.12 lancer.py serveur --reglages exemples/demo/reglages.json
```

**La démo joue le projet** : ses commandes d'actions (`exemples/demo/actions.py`, que la démo B réutilise) écrivent
dans `releve.json` et `catalogue-magasin.json`, et rangent les images jointes dans `images/pieces/`. Pour garder le
dépôt propre, copiez le dossier `exemples/` en entier ailleurs et lancez le bureau sur la copie.

Le terminal affiche `Le bureau est ouvert sur http://127.0.0.1:8770/`. Ouvrez cette adresse dans le navigateur (l'adresse `http://localhost:8770/` marche aussi ; aucune autre n'est acceptée).

Ce qu'on doit voir : le bâtiment en 3D isométrique, une pièce par service (Métier, Dev, QA, Intégration, Facturation, Design), le coin café, le bureau du Directeur avec une pastille « 5 » (ce qui l'attend : décisions et leçons), le chef près du Kanban central rempli de post-its, le voyant de la factory et la barre de charge en haut. Survolez un agent pour voir sa carte, cliquez sur une pièce pour ouvrir le dossier du service à droite (voir « Les dossiers des services »), sur un post-it pour le détailler. Échap ferme.

La démo fait deux lectures sur Internet pour connaître les prix des modèles (voir « Les euros : d'où viennent les prix ») ; pour l'essayer sans aucune requête sortante, ajoutez `"prix_automatiques": false` à `exemples/demo/reglages.json` (les coûts s'affichent alors « prix inconnu »).

**Pourquoi les agents de la démo sont « sans nouvelles »** : les dates `maj` du relevé de démonstration sont fixes, donc de plus en plus anciennes. Le bureau ne prétend jamais qu'un agent travaille si rien n'a bougé depuis plus que le délai de fraîcheur (30 minutes par défaut) : ils restent à leur poste, avec une bulle grisée. Pour les voir au travail, ouvrez `exemples/demo/releve.json` et mettez à une tâche active une `maj` récente (par exemple l'heure qu'il est) ; pour voir un déplacement, changez en plus sa `colonne`. Dans les secondes qui suivent, l'agent marche jusqu'au Kanban et déplace son post-it. Passez `factory.etat` à `"en pause"` : le voyant change et la lumière baisse.

Arrêter le bureau : `Ctrl+C` dans le terminal.

## Plusieurs projets

Un **fichier de bureau** liste les réglages de plusieurs projets (12 au plus), chemins relatifs à lui :

```json
{"port": 8770, "projets": [{"chemin": "demo/reglages.json", "id": "demo"}, "demo-b/reglages.json"]}
```

```bash
py -3.12 lancer.py serveur --bureau exemples/bureau.json
```

`id` (facultatif) est l'identifiant du projet dans les adresses (`?projet=…`) ; sans lui, il vient du nom du dossier.
Deux projets ne peuvent pas avoir leurs réglages dans le même dossier. Le nom du projet devient un **sélecteur**, avec
pour chaque projet la pastille de ce qui l'attend ; le choix est retenu par le navigateur, et changer de projet
recharge la page. Chaque geste va à la commande d'actions **du projet choisi**, vérifié contre son relevé ; un projet
aux réglages illisibles n'empêche pas les autres de marcher. La charge est celle de la machine, commune à tous.

## Nouvelle fonctionnalité et discussion

Avec un relevé en version 4 et une commande d'actions, la barre gagne « **+ Nouvelle fonctionnalité** » et
« **Fonctionnalités** ». Le panneau d'une fonctionnalité s'ouvre à droite (la scène reste visible) : le bandeau du
parcours (Cadrage, Cahier des charges, Découpage, Prototype, Méthode, Série), la discussion de cadrage, une zone de
saisie avec « Joindre une image » (PNG ou JPEG, 4 au plus, 5 Mo chacune) et « Envoyer ». Sous la discussion : la
maquette et les étapes du cahier des charges, « Valider le cahier des charges » / « Demander une correction », la
méthode et « Valider la méthode », et « Catalogue ».

Le bureau ne parle à aucune IA : votre message devient une demande `message` pour le projet, et la réponse de
l'agent de cadrage n'apparaît qu'au relevé suivant. Tant qu'elle n'est pas là, la page affiche « <prénom> est en
train d'écrire… » si l'orchestrateur tourne, sinon « En attente de l'orchestrateur ». « Tourne » se juge à la
fraîcheur du chef (30 minutes par défaut) : une conversation orchestratrice fermée à l'instant compte encore comme
active pendant ce délai. Dans la démo, les réponses sont
fixes : un message de cadrage fait passer au cahier des charges, sa validation au prototype, la validation de la
méthode à la série.

Le **Directeur** montre en plus les cahiers et les méthodes à valider, les genres à confirmer, les « méthode à
revoir ? » et les sessions cloud à créer (créez la session vous-même, puis donnez son nom et cliquez « C'est fait ») ;
pour une leçon, il montre l'étage proposé (projet, genre ou skill) et le texte général, que vous validez mot pour mot.

## Le catalogue

Le catalogue d'une fonctionnalité s'ouvre depuis son panneau (« Catalogue ») ou depuis le menu « Dernier livrable ».
Il s'affiche à droite ; « Agrandir » le met en plein écran (Échap pour revenir). On y trouve le choix du groupe, la
**vue de haut** (une carte des éléments : molette pour zoomer, glisser pour se déplacer, un clic ouvre la fiche), les
compteurs, les demandes de modification et leurs réponses, les passes, « Ce que j'ai appris », les filtres et la
recherche, la liste par pages de 100 et le kit. La **fiche** d'un élément montre ses captures, la comparaison
« Produit » / « Réel » à plusieurs angles (une barre à glisser), sa connaissance, son doute, et « **Demander à
modifier** », qui envoie une demande `retour_element` au projet. Une partie sans donnée n'est pas montrée. Le format
et la déclaration du catalogue sont dans [`releve.md`](releve.md) (« Le catalogue d'une fonctionnalité »).

## L'orchestrateur générique

Pour qu'une conversation Claude mène vos fonctionnalités du cadrage à la série avec les outils de la skill, suivez
[`orchestrateur.md`](orchestrateur.md). Pour **démarrer un projet neuf**, copiez
[`exemples/projet-neuf/`](../exemples/projet-neuf/) dans un dossier à vous, `git init`, mettez le chemin de ce dépôt
dans `skill` (`factory.json`) et celui de `orchestrateur/outil.py` dans `reglages.json` et dans la déclaration du
catalogue, puis :

```bash
py -3.12 <ce dépôt>/orchestrateur/verifier_interface.py --factory <votre dossier>/factory.json
```

```bash
py -3.12 <ce dépôt>/lancer.py serveur --reglages <votre dossier>/reglages.json
```

et ouvrez la conversation orchestratrice avec le message de départ donné dans `orchestrateur.md`.

## Brancher son projet

Un projet réel se branche **depuis son propre dépôt** : rien n'est à modifier ici.

1. Dans le dossier du projet, créez un dossier `.factory/` et ajoutez `.factory/` au `.gitignore` du projet (on n'y range que des choses propres à la machine et au projet : réglages, équipe, historiques).
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

Le bureau crée lui-même, à côté des réglages, `equipe.json` (prénoms, couleurs), `charge-historique.jsonl` (historique de charge, 7 jours) et, avec un relevé version 3, `usage-historique.jsonl` (les usages déjà vus), `prix-historique.jsonl` (les prix lus, datés) et `alertes-historique.jsonl` (les entrées et sorties d'alerte des KPI). Ne les effacez pas : les coûts passés et la marque « problème revenu » en dépendent.

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
| `prix_automatiques` | `true` | `false` (le booléen, pas le texte `"false"`) : le bureau ne fait aucune requête sortante ; seuls comptent les prix déjà enregistrés et ceux de `prix`. Voir « Les euros : d'où viennent les prix ». |
| `alias_modeles` | — | Nom de modèle du relevé → nom dans la liste de prix. |
| `prix` | — | Prix donnés à la main, en euros par million de tokens, avec leur date. |

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

## Les dossiers des services

Avec un relevé `version` 3 (voir « Version 3 » dans [releve.md](releve.md)), cliquer une pièce ouvre le **dossier** du service : un sélecteur de période (aujourd'hui, 7 jours, 30 jours) et jusqu'à quatre onglets. Un onglet n'apparaît que si le relevé donne de quoi le remplir.

![Le dossier d'un service, avec l'exemple de démonstration](img/dossier.jpg)

- **Tâches** : les tâches en cours du service, avec leur coût estimé ; en haut, les KPI en alerte et la liste des challenges du service (un challenge reste ouvrable même quand son alerte est levée).
- **Connaissances** : ce que chaque agent du service sait, d'où il le tient (« appris du retour de … »), ce qui est partagé, et qui n'a rien reçu sur la période.
- **KPI** : les chiffres que le projet donne, et ceux que le bureau calcule (tâches terminées, allers-retours, durée et coût moyens d'une tâche).
- **Facturation** : le coût estimé du service, par tâche, par étape, par modèle et discussion par discussion, les sources d'amélioration, puis le total de tout le projet (dont la part « direction / hors service », qui n'a pas de dossier).

Le bouton **« Challenger »** (sur une alerte, un KPI, une connaissance ou une source d'amélioration) ouvre un volet : le problème, les solutions proposées par le Directeur et par le service, une zone pour écrire la vôtre, et « Valider la sélection » ou « Écarter la sélection » pour les solutions cochées. Comme tous les gestes, il ne fait que déposer des demandes : c'est le projet qui ouvre le challenge, propose les solutions et inscrit la solution validée dans les connaissances des agents. Il faut donc une commande d'actions (voir « Faire agir le bureau ») qui sache traiter les demandes `challenge`, `solution` et `verdict_solution`.

**Essayer avec la démo** (sur une copie, car les gestes réécrivent `releve.json`) : cliquez la pièce Dev. L'onglet Tâches rappelle l'alerte « Défauts passés au contrôle » ; « Voir le challenge » montre trois solutions (le Directeur, le service, vous) : cochez-en une, « Valider la sélection », et au relevé suivant elle est « validée » et figure dans l'onglet Connaissances des deux agents du service. Dans l'onglet Connaissances, « Challenger » sur une connaissance ouvre un nouveau challenge : la démo répond aussitôt par une solution du Directeur et une du service (textes fixes : dans un vrai projet, ce sont les agents qui les écrivent). L'onglet Facturation montre trois sources d'amélioration, et dans le service Design un usage du modèle « Maison », laissé exprès sans prix pour montrer « prix inconnu ».

Les usages de la démo sont datés du 9 novembre 2026 : passé sept jours, choisissez « 30 jours » ; passé trente jours, ils sortent de toutes les périodes (mettez une date récente dans le `t` de quelques usages de `releve.json` pour les revoir).

## Les euros : d'où viennent les prix

Les euros affichés sont des **estimations** pour piloter (toujours précédées de « ≈ »), pas une facture. Le projet donne des tokens ; le bureau les multiplie par le prix du modèle à la date de l'usage.

**Les deux requêtes sortantes.** Pour connaître les prix, le bureau lit, au démarrage puis une fois par jour (toutes les heures tant qu'une des deux lectures échoue), deux adresses publiques, et seulement celles-là (elles sont écrites dans le code, aucun réglage ne peut les changer) :

| Quoi | Adresse |
|---|---|
| Prix des modèles, en dollars par token (liste tenue par la communauté LiteLLM) | `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json` |
| Taux dollar-euro du jour (Banque centrale européenne) | `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` |

Ce sont de simples lectures : rien de votre projet n'est envoyé. Pour n'avoir **aucune requête sortante**, mettez `"prix_automatiques": false` dans les réglages (les prix déjà enregistrés continuent de servir, les autres se donnent à la main, voir plus bas ; le remettre à `true` demande de relancer le bureau).

**Un coût passé ne bouge pas.** Chaque lecture est datée et gardée dans `prix-historique.jsonl`, à côté des réglages. Le prix d'un usage est le dernier prix enregistré à sa date ou avant. Un usage plus ancien que le premier prix enregistré prend ce premier prix, et l'onglet le dit (« prix du jour de l'installation »).

**Quand une source ne répond pas**, ou donne une valeur absurde (négative, nulle, ou plus de dix fois plus grande ou plus petite que le dernier prix gardé), le bureau garde le dernier prix connu et l'écrit en haut de l'onglet Facturation (« Prix du 3 novembre, mise à jour impossible : … », ou « valeur absurde dans la source pour … : dernier prix gardé », redit tant qu'une lecture ne l'a pas remplacé). Si un prix a vraiment changé de plus de dix fois, donnez-le à la main (`prix`) : le bureau ne l'acceptera pas tout seul.

> **Sous Windows, « certificat de www.ecb.europa.eu non reconnu ».** Python ne fait confiance qu'aux autorités de certification déjà installées dans Windows, et Windows n'installe celle de la BCE qu'à la première visite. Ouvrez une fois `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` dans Edge, puis relancez le bureau. Tant qu'aucun taux n'a été lu, **tous les prix automatiques restent « inconnus »** (le bureau ne devine pas un taux) ; seuls les prix donnés à la main comptent.

**Rapprocher les noms de modèles** (`alias_modeles`). Le relevé écrit « Sonnet », la liste de prix dit autre chose : donnez la correspondance, nom du relevé → nom exact dans la liste.

```json
{"alias_modeles": {"Sonnet": "claude-sonnet-5-5", "Haiku": "claude-haiku-4-5"}}
```

Un modèle sans correspondance, ou absent de la liste, reste à « prix inconnu » : ses tokens sont montrés, il est exclu des euros, et chaque chiffre qui en dépend le dit (« ≈ 3,00 € + prix inconnu »). Il n'est jamais compté à zéro.

Attention : un alias n'a pas de date. Le changer re-chiffre **aussi les usages passés** de ce nom de modèle (c'est ce qu'on veut quand l'alias était faux). Quand un nom du relevé change de modèle réel, donnez plutôt un nouveau nom dans le relevé.

**Donner ou corriger un prix à la main** (`prix`) : en **euros par million de tokens**, avec la date à partir de laquelle il vaut. La correction passe avant le prix automatique à partir de cette date, et ne touche pas les usages antérieurs à cette date (une correction datée du passé re-chiffre donc les usages faits depuis). La clé est le nom du relevé (ou celui de la liste) ; `cache_lecture` et `cache_ecriture` sont facultatifs (sans eux, les tokens de cache comptent au prix d'entrée). Pour plusieurs prix successifs, donnez une liste.

```json
{"prix": {"Maison": {"entree": 0.5, "sortie": 1.5, "date": "2026-11-01"},
          "Sonnet": [{"entree": 2.6, "sortie": 13, "date": "2026-09-01"},
                     {"entree": 2.8, "sortie": 14, "date": "2026-11-01"}]}}
```

Une correction sans `date` lisible est ignorée (elle changerait le passé).

**La ligne « gestion »** de la facturation est le coût du bureau lui-même : il vaut 0, car le bureau ne consomme aucun token (ses deux lectures de prix ne coûtent que du temps).

## L'équipe

Le relevé ne donne pas de prénom (sauf, en version 2, un `prenom` facultatif par titulaire, qui n'est pas écrit dans ce fichier et l'emporte sur lui tant que le relevé le donne) : le bureau en attribue un à chaque clé de titulaire, avec une couleur, et le retient dans `equipe.json`, à côté des réglages. Un agent qui revient retrouve son prénom.

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
- **Facturation : « prix inconnu » partout, ou « mise à jour impossible »** : le message en haut de l'onglet donne la raison. Certificat de la BCE non reconnu, nom de modèle sans correspondance (`alias_modeles`), ou prix automatiques coupés : voir « Les euros : d'où viennent les prix ».
- **Un onglet du dossier manque** : le relevé n'est pas en version 3, ou ne donne pas le champ correspondant (`usage`, `kpi`, `connaissances` ou `challenges`).
- **« Challenger » répond « Un challenge existe déjà » ou reste sur « Demande envoyée »** : le projet n'a pas encore ajouté le challenge à son relevé.
