# Étapes locales et étapes découpées — conception

Date : 2026-11-13. Décidé avec le Directeur ; les points **[choix de conception]** sont à vérifier à la relecture.

## Pourquoi

Avec les agents polyvalents, une tâche part chez n'importe quel agent libre. Essai réel (ZooRunner) : le prototype
« Événements, boutique… » est parti dans une session cloud, qui n'a ni Godot ni SDK Android : ni test, ni capture, la
validation s'est bloquée. Le palliatif du jour (un métier entier réservé au local) bloque aussi tout ce qui pourrait se
faire dans le cloud, alors qu'il n'y a qu'une place locale.

## Ce qui est décidé (par le Directeur)

1. **Le lieu se décide par étape.** Chaque étape du workflow dit si elle a besoin des logiciels installés sur le poste
   (alors un agent local la fait) ou non (alors n'importe quel agent, cloud compris).
2. **Une étape mixte se découpe** : la partie sans logiciel (écrire le code, les données, les textes) par un agent
   cloud, puis la partie qui exige le poste (récupérer, compiler, tester, capturer, exporter) par un agent local.
   Exemple : « Prototype jouable » → « Prototype jouable : code » puis « Prototype jouable : mise en place et tests ».
3. **ZooRunner est découpé maintenant**, pas seulement les prochains projets.

## Ce que cela change

### Le lieu d'une étape

- Une étape de flux porte un champ facultatif `lieu` : `local` (elle exige le poste) ou `indifférent` (cloud possible).
- Le choix de l'agent (moteur, `agent_libre` / `_choisir_agent`) suit le `lieu` de l'étape de la tâche quand il est
  écrit ; absent (étape non encore découpée, ou tâche sans étape), on retombe sur le `Lieu :` du métier, comme
  aujourd'hui. **[choix de conception]**
- Une étape `local` attend une place locale (il y en a toujours au moins une) ; le bureau le dit dans la barre et sur la
  carte (« attend le poste local »). Les autres prennent la place libre qui se présente (locale d'abord).

### Quelles étapes sont locales

- **[choix de conception]** Une étape est locale si un outil de l'environnement du projet la cite (`pour`, ou son
  `objectif` qui nomme l'étape), ou si sa nature l'exige (tests sur émulateur, export, captures du jeu).
- Le Chef le propose ; le Directeur valide (comme l'organisation). Le Directeur peut ensuite changer le lieu de chaque
  étape depuis le bureau.

### Le découpage

- Une étape locale qui a une partie écrivable sans le poste est découpée en deux étapes consécutives, même rôle et même
  service :
  - `<id>` gardé pour la partie « code » (`lieu: indifférent`, écrit explicitement pour l'emporter sur le métier),
    nom « <nom> : code » ;
  - `<id>-local` pour la partie locale (lieu `local`), nom « <nom> : mise en place et tests ».
  Garder l'identifiant de la première partie laisse valides les tâches et les éléments déjà en cours. **[choix de
  conception]**
- Une étape entièrement locale (tests sur émulateur, export de l'apk) n'est pas découpée : elle est juste `local`.
- La partie locale reçoit le compte rendu de la partie code (déjà transmis d'étape en étape) ; le code de l'agent cloud
  est déjà fusionné dans le dépôt avant le départ de l'étape suivante (sessions cloud existantes). La partie locale ne
  refait pas le code : sa consigne dit de récupérer, compiler, tester, capturer, et de rendre ce que la validation
  attend (captures, apk, mode opératoire).
- Les étapes de validation ne changent pas.

### Qui propose, qui décide

- **Nouveau projet** : `definir_workflow` / `proposer_organisation` rendent déjà le flux ; ils rendent aussi `lieu` par
  étape et le découpage, d'après les outils déclarés. Le Directeur valide comme aujourd'hui.
- **Projet en cours** (ZooRunner) : un jugement `decouper_lieux` (un appel, Sonnet) reçoit le workflow et l'environnement
  et propose le nouveau flux ; le moteur pose une décision de projet « Découper les étapes selon le poste » avec
  l'avant/après ; « Valider » l'applique à tous les workflows du projet (principal et copies `w-<fid>`), « Refuser » ne
  change rien. Déclenchée par un bouton du bureau (Facturation, à côté des places) et proposée une fois après la reprise
  des agents polyvalents.
- Validation stricte de la proposition : chaque étape existante garde son `id`, son ordre, son rôle, son service et sa
  nature (validation ou non) ; seuls changent `lieu`, le nom de la partie code et l'insertion de `<id>-local` juste
  après `<id>`. Une proposition qui supprime, renomme ou réordonne une étape est refusée (le jugement est redemandé une
  fois, puis la décision n'est pas posée et le bureau le dit).
- Appliquer le découpage : à chaque workflow du projet (principal et copies `w-<fid>`) par identifiant d'étape, la même
  transformation ; une étape qui a déjà sa sœur `<id>-local` n'est jamais redécoupée ; rejouable sans effet, aucune tâche
  touchée ; un élément dont l'étape courante est découpée
  continue sur sa tâche en cours (partie code), puis enchaîne sur la partie locale.

### Bureau

- La décision montre chaque étape avant/après, avec « poste local » ou « cloud possible ».
- Le lieu de chaque étape se change depuis le bureau (une liste « Étapes et lieux » dans Facturation, un sélecteur
  local / cloud possible par étape de flux, pas pour les validations), par une demande au moteur appliquée tout de
  suite, sans décision ni coût.
- La fiche d'une tâche dit « Sur le poste local » quand son étape l'exige.

## Ajouts du Directeur (2026-11-13, après validation)

### Trois choix par étape, et ce qui est figé

- Le lieu d'une étape vaut **Local** (seul un agent local la prend ; il attend sinon), **Cloud** (seul un agent cloud ;
  il attend sinon) ou **Indifférent** (le premier agent libre). Le réglage se fait dans l'espace de direction.
- Une étape qui **exige le poste** (un logiciel que le cloud ne sait pas installer) est figée sur Local. Une étape faisable
  aux deux endroits laisse les trois choix. Un outil de l'environnement porte `cloud: true` quand le cloud sait
  l'installer (vérifié par un essai réel : voir « Équiper les sessions cloud »).

### Équiper les sessions cloud

- Une session cloud clone le dépôt du projet et lance ses hooks `SessionStart` (`.claude/settings.json`) : un script
  `.claude/cloud/installation.sh` du projet y installe les outils déclarés (ne fait rien hors du cloud ; les agents
  locaux du moteur sont lancés sans les réglages du projet). Ajouter ce hook à un projet passe par une décision du
  Directeur au bureau de direction (jamais en silence).
- Un outil installé ainsi et vérifié par un essai réel est marqué `cloud: true` : ses étapes ne sont plus figées.

### À l'initialisation d'un projet

- Quand le Chef définit le workflow (`definir_workflow`), il évalue pour chaque étape si elle est exécutable dans le
  cloud (ses outils s'y installent-ils ?) et le dit avec l'étape (`exige_poste`, et pour chaque outil `cloud`).
- Si le Directeur a choisi de travailler avec des agents cloud, la création propose ensuite, après la définition du
  workflow, l'écran « Où s'exécutent les étapes » (les trois choix, figés pour ce qui exige le poste) : il choisit quels
  agents font quoi avant que le projet démarre.

## Hors champ

- Pas de nouveau métier ; pas de changement des validations.
- Pas de détection automatique des logiciels manquants dans le cloud (on s'appuie sur l'environnement déclaré).

## Contraintes

- Python 3.12 bibliothèque standard ; JS sans dépendance.
- Jamais Fable sans accord ; la seule dépense réelle est l'appel `decouper_lieux` (et la production qui suit), sur accord.
- La skill garde la mécanique, jamais la connaissance d'un projet ; tout se règle depuis le bureau.
- Un projet sans `lieu` sur ses étapes marche comme aujourd'hui (métier `Lieu :` comme repli).

## Laissé au constructeur

- Le texte exact des consignes de la partie locale et du jugement ; les noms internes ; le découpage en tâches.
