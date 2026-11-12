# Le workflow défini dès la création d'un projet au bureau — conception

Date : 2026-11-12. Statut : en relecture par l'utilisateur.
Suite de `2026-11-11-genre-par-fonctionnalite-design.md` (genres et workflows par fonctionnalité), qui reste valable.

## 1. Intention

Aujourd'hui, un projet créé au bureau (« Nouveau projet… ») naît **vide** : ni workflow, ni service, ni agent. Son
workflow n'est proposé qu'à sa première demande. L'utilisateur veut l'inverse : le workflow est fixé **dès la
création**, au cours d'un échange avec le chef, **avant** que le bureau du projet n'existe. Le chef pose toutes les
questions utiles (besoin, livrables, étapes de validation humaine…), en déduit un workflow, l'explique ; après
validation seulement, le projet est créé avec ses services et ses agents recrutés.

Pourquoi : un projet qui démarre avec un workflow pensé pour lui, discuté avec l'utilisateur, évite de découvrir
l'organisation au fil des demandes, et place les validations humaines là où l'utilisateur les veut.

## 2. Objectifs, non-objectifs, anti-objectifs

Objectifs :
- La création au bureau se fait en deux fenêtres : (1) les informations générales du projet, validées ; (2) la
  définition du workflow par un échange avec le chef.
- Le chef pose ses questions ; l'utilisateur répond à chacune dans un champ texte, ou d'un bouton quand le chef
  propose des réponses.
- Le workflow peut contenir des **étapes de validation du Directeur** placées où l'utilisateur le veut.
- Après validation du workflow : le projet est créé, ses services et agents recrutés, son genre enregistré, et
  son premier bureau s'ouvre, prêt à recevoir une demande.
- Plus tard, si un besoin n'est pas couvert par le workflow, le moteur propose de le modifier (comportement des
  genres par fonctionnalité, inchangé).

Non-objectifs :
- L'installation par la skill (`skills/installer`, lancée depuis Claude Code) ne change pas : elle mène déjà sa
  discussion avant d'ouvrir le bureau.
- Pas de refonte du moteur de séries, du cadrage, ni des workflows par fonctionnalité.

Anti-objectifs (ce qui serait un échec même si ça marche) :
- Un projet à moitié créé sur le disque ou au bureau si l'utilisateur abandonne en cours d'échange.
- Un chef qui repose ce que la description ou une réponse précédente dit déjà, ou qui pose des questions sans fin.
- Une demande du genre du projet (la première comme les suivantes) qui redemande de valider le workflow validé à la
  création (choix de l'utilisateur, 2026-11-12).
- Fable recruté sans l'accord du Directeur ; une clé écrite ou affichée.

## 3. Le parcours

### Fenêtre 1 : les informations générales

Ce qu'il y a déjà dans « Nouveau projet… » : nom, dossier parent, GitHub ou non, courte description (obligatoire
désormais : c'est la base de l'échange). L'utilisateur **valide** cette fenêtre. Les contrôles actuels
(`creation.verifier_nom`, `verifier_parent`, nom déjà pris) s'appliquent **à la validation de la fenêtre 1**, pour ne
pas découvrir un nom invalide après l'échange. Rien n'est encore écrit sur le disque ni au bureau.

### Fenêtre 2 : l'échange avec le chef

- Le chef écrit des messages ; chaque message porte une ou plusieurs questions. Chaque question a un champ texte et,
  si le chef en propose, des boutons de réponse (un clic = cette réponse ; le champ texte reste toujours possible).
- Ce que le chef cherche à savoir, sans reposer ce qui est déjà connu : le besoin, les livrables et leur forme
  (`.apk`, site, images…), les étapes où l'utilisateur veut valider lui-même, le niveau d'exigence sur la qualité et
  les tests, et toute zone d'ombre qui changerait le workflow.
- Le chef s'arrête quand il en sait assez, et présente le workflow expliqué :
  - le genre du projet (connu, ou nouveau avec sa phrase courte pré-remplie, comme au point 13 de la conception
    précédente) ;
  - les étapes dans l'ordre, chacune avec son rôle, son service et sa raison d'être ;
  - les validations du Directeur placées dans le flux ;
  - les agents à recruter et leurs modèles avec justification (Fable : seulement suggéré, accord du Directeur agent
    par agent, comme aujourd'hui) ;
  - l'environnement du poste (déjà en place / à installer, versions comparées) ;
  - le coût estimé d'un élément, en euros quand les prix sont connus.
- L'utilisateur **valide**, ou demande une correction (texte libre) : le chef ajuste et réexplique, sans reposer
  toutes les questions.
- Le coût de l'échange s'affiche au fil de l'eau (cumul des appels).
- Quitter l'écran avant de valider ne crée rien. L'échange en cours est gardé comme brouillon pour pouvoir le
  reprendre (recharger la page, changer d'appareil) ; un brouillon abandonné peut être supprimé.

### Après validation

Le projet est créé sur le disque et inscrit au bureau **avec** son organisation : workflow du genre du projet,
services, agents recrutés, briefs, genre enregistré (et nouveau genre créé avec sa phrase validée). Si des outils
sont « à installer » et que l'utilisateur l'a accepté dans la proposition, la tâche d'installation est créée comme
pour une fonctionnalité (agent d'installation, conception précédente). GitHub se fait à ce moment-là, comme
aujourd'hui. Le projet apparaît dans la liste déroulante et son bureau s'ouvre.

**Toute demande du genre du projet** (la première comme les suivantes) : elle reprend le workflow validé à la création **sans nouvelle proposition
ni validation** (l'anti-objectif ci-dessus). Une demande d'un autre genre suit le parcours actuel (classement,
cohérence, workflow dédié proposé).

## 4. Les étapes de validation du Directeur

- Nouvelle sorte d'étape dans un flux : une étape « validation du Directeur » (pas de rôle d'agent, pas de service
  à recruter). Elle peut se placer n'importe où après la première étape de production.
- Quand un élément y arrive, le travail s'arrête : l'élément apparaît au bureau de direction avec le livrable de
  l'étape précédente (ses fichiers, son compte rendu).
- Deux choix : **Valider** → l'élément passe à l'étape suivante ; **Renvoyer avec une remarque** (texte obligatoire)
  → l'étape précédente est refaite pour cet élément, la remarque jointe à sa matière ; puis l'élément revient à la
  validation.
- Ces étapes ne coûtent rien en agents ; l'estimation de coût les ignore.
- Elles existent aussi dans les workflows proposés par fonctionnalité (`proposer_organisation`) : le chef de la
  fonctionnalité peut en proposer, et le Directeur peut en demander par un refus avec texte.
- Les deux validations fixes d'aujourd'hui (cahier au cadrage, méthode et prototype) restent ce qu'elles sont.

## 5. Ce qui est décidé côté technique

- L'échange avec le chef se fait par des **appels de jugement** du moteur (`moteur/jugement.py`, même couche que les
  autres, même garde-fous de validation et de reprise), pas par un agent Claude Code : un appel par tour, avec tout
  l'échange dans le dossier. Modèle : Sonnet. Le dernier tour rend une proposition dans la forme de
  `proposer_organisation` (étendue au genre du projet et aux étapes de validation), calculs d'environnement et de coût
  faits en code comme aujourd'hui.
- Plafond : le chef a au plus 4 tours de questions avant de proposer ; il peut proposer avant.
- La création sur le disque réutilise `installation/creation.creer_projet` et la mise en place des organisations
  validées par le moteur (recrutement, services, briefs, workflows) ; pas de seconde façon de recruter.
- Le brouillon d'échange vit hors des projets, dans le dossier commun de MyIAFactory ; il ne contient aucune clé.

## 5 bis. Précisions (choix du concepteur, après relecture)

- **Le workflow de création** est un workflow **de genre** (`w-<genre>`, étapes sans préfixe de fonctionnalité),
  enregistré dans le projet comme les autres. Une demande classée `meme` (genre du projet) le reprend : ses étapes
  sont copiées dans le workflow de la fonctionnalité (`w-<fid>`, préfixe `<fid>-`) **sans appel
  `proposer_organisation` ni décision `organisation`**. Une demande `proche` ou `autre` suit le parcours actuel ; le
  workflow de création reste dans `workflows_du_genre` pour inspirer les propositions suivantes.
- **Application** : `creer_projet` reçoit l'organisation validée et l'écrit dans la même transaction que la
  configuration (dossier temporaire puis renommage, comme aujourd'hui). Le recrutement réutilise les fonctions de
  mise en place de l'organisation du moteur (fiches, briefs, services). Tout échec avant l'inscription au bureau
  annule tout ; GitHub reste après, et son échec ne défait rien (comportement actuel).
- **Appels avant le projet** : couche du moteur et prix lus dans le bureau commun (réglages de l'installation, pas un
  projet). Les usages de l'échange sont cumulés dans le brouillon, affichés au fil de l'eau, puis versés au relevé du
  nouveau projet à sa création ; un échange abandonné reste compté dans le relevé du bureau commun.
- **Étape de validation** : une étape de flux `{"id", "nom", "validation": true}` sans `role` ni `service` ; les
  validateurs, l'estimation et le recrutement l'ignorent. Interdite en première étape et deux fois de suite.
  L'arrivée d'un élément pose une décision de portée projet (comme les autres décisions du Directeur) ; « Renvoyer »
  remet l'élément à l'étape précédente avec la remarque dans sa matière. Le banc ne contient aucune de ces étapes :
  il ne doit pas bouger.
- **Tours** : au plus 4 tours de questions ; au 5ᵉ appel, la consigne et la validation exigent une proposition.
  Les corrections après proposition ne comptent pas dans les 4 tours ; chacune est un appel.
- **Brouillons** : plusieurs possibles, un par projet en cours de définition ; « Nouveau projet… » propose de
  reprendre ceux qui existent. Nom et dossier sont recontrôlés à la validation finale (s'ils sont devenus invalides,
  retour à la fenêtre 1 sans perdre l'échange). Suppression à la main ; purge automatique après 30 jours.
- **Genres** : même source que `classer_genre` (genres connus de la skill, mots interdits — le nom du projet en
  fait partie dès la fenêtre 1). Le genre nouveau est écrit à la création, par l'outil existant.
- **Fable** : l'écran de validation reprend l'accord par agent de la décision `organisation` actuelle.
- **Installation** : si des outils sont à installer et acceptés, la tâche d'installation est créée au premier
  bureau, portée par le projet (pas par une fonctionnalité), avant toute demande.

## 6. Laissé au constructeur

- La forme exacte des messages du chef (schéma JSON des questions et des propositions de réponse), dans l'esprit des
  jugements existants.
- La mise en page des deux fenêtres, dans le style actuel de `creation.js`, utilisable au téléphone.
- Le nom et le format du brouillon.
- Le découpage en tâches et phases (par modèle, comme les chantiers précédents).

## 7. Mesure

- Le banc gratuit (rejoueur) ne doit pas bouger pour les projets existants.
- Un essai réel au bureau : création d'un projet de jeu Android avec une validation du Directeur avant la livraison ;
  coût de l'échange relevé (cible : moins de 0,10 € pour l'échange complet).

## 8. Outils à installer : lien, mode opératoire, autonomie (2026-11-12)

Constat : un outil « à installer » n'était qu'une ligne de texte collée dans une phrase, et l'installation partait d'elle-même
à l'acceptation du workflow. Désormais :

- **Données.** Chaque outil de `environnement` (rendu par `proposer_organisation` et `definir_workflow`) porte en plus
  `objectif` (à quoi il sert dans CE projet et à quelle étape, une phrase concrète ; absent d'un ancien résultat, l'étape
  `pour` le remplace à l'affichage), `telechargement` (URL https de la page officielle de l'éditeur, jamais un miroir, nulle
  si inconnue), `etapes` (mode opératoire Windows, 2 à 8 lignes, jusqu'à la vérification) et `autonome` (un agent peut
  l'installer seul, sans clic ni droits d'administrateur). Les validateurs refusent une URL non https, des étapes mal
  bornées, un `autonome` non booléen ; les anciens résultats restent acceptés (valeurs par défaut `null`, `[]`, `false`).
- **Un seul endroit durable : la partie existante « Environnement du poste à compléter »** (décision `environnement`, boutons
  « C'est fait » et « Continuer sans »). Aucune nouvelle partie n'a été créée : la décision montre, pour chaque outil qui
  manque, l'objectif, le lien (nouvel onglet, `rel="noopener noreferrer"`), le mode opératoire numéroté et, si l'outil est
  `autonome`, « Installer en autonomie ». « C'est fait » garde son rôle (revérification en code, versions comparées),
  « Continuer sans » est inchangé. Le texte de la décision ne porte plus que les noms ; la ligne `installation` brute en est
  retirée. La même présentation sert à la proposition de workflow d'une fonctionnalité et à la proposition du chef à la création.
- **Jamais d'installation d'elle-même.** Trois clics possibles : le bouton de la décision (nouvelle demande `installer_outil`,
  `{decision, outil, fonctionnalite?}`), le choix « Installer en autonomie » par outil dans la proposition de workflow (envoyé
  avec « Accepter » : `installer`), la case « installer » de la création (limitée aux outils `autonome`). L'agent
  d'installation ne reçoit que les outils autonomes choisis ; il n'est proposé que s'il y en a, et recruté au clic s'il manque
  (`lancer organisation` avec `action: installateur`, règle `Bash(winget:*)`). Une tâche par outil : le relevé marque
  `en_cours` l'outil qu'une tâche non finie couvre, et le moteur refuse un second clic.
- **Sans clic, la liste attend.** À l'acceptation sans choix, à la création sans case, ou pour les outils non autonomes, la
  décision `environnement` (de la fonctionnalité, ou du projet) est posée ; la fin d'une tâche d'installation revérifie le poste
  et remplace la décision par la liste de ce qui manque encore.

## 9. Questions à plusieurs réponses (2026-11-12)

- Une question à choix porte `multiple` (booléen, absent = faux = un seul choix, comportement inchangé). Elle existait déjà
  pour la discussion d'une fonctionnalité (relevé, `message.questions`) ; elle est ajoutée aux questions du chef de la
  création (`definir_workflow` : validateur booléen, consigne, exemple) et à la consigne de cadrage.
- Page : une question `multiple` montre des boutons bascule (`aria-pressed`, coche visible, sélection de 1 à N) ; le champ
  texte reste, comme réponse libre ajoutée. L'envoi est refusé tant qu'aucun choix ni texte n'est donné.
- Réponse transmise au chef : `"Fun ; Jouabilité ; Autre : texte libre"` (dans le `texte` de la réponse, sans changement
  de serveur ni de format de stockage). La discussion garde son format « question → choix, choix ».
- Anciennes questions et anciens brouillons (sans `multiple`) : lus comme des questions à un seul choix.
