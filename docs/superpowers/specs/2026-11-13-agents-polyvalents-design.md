# Agents polyvalents — conception

Date : 2026-11-13. Décidé avec le Directeur (l'utilisateur) en conversation ; les points marqués **[choix de
conception]** sont des décisions prises en rédigeant, à vérifier à la relecture.

## Pourquoi

Aujourd'hui, une fiche d'agent = un rôle = un service. Un projet comme ZooRunner a 10 fiches (dev, designer,
designer-1 à 3, graphiste, qa, release, equilibreur…), dont la plupart attendent à la cafétéria pendant que deux ou
trois travaillent. Les places de parallélisme (onglet Facturation) limitent déjà le nombre de lancements simultanés,
mais une place libre ne sert à rien si l'agent du bon rôle est occupé.

Le Directeur veut des **agents polyvalents** : chaque agent prend n'importe quelle tâche prête et devient, pour cette
tâche, le spécialiste de son métier. Cela facilite la parallélisation et supprime les agents inoccupés.

## Ce qui est décidé (par le Directeur)

1. **Agent polyvalent.** Un agent n'appartient plus à un rôle ni à un service. Il prend la prochaine tâche prête,
   quel qu'en soit le métier (le `role` de l'étape).
2. **Toujours spécialiste.** Pour chaque tâche, l'agent reçoit la consigne complète du métier de la tâche (le brief
   `briefs/<role>.md`, la spécialité, les outils du métier) et les leçons de ce métier. Jamais un généraliste qui
   « dépanne ».
3. **Leçons par métier.** Une leçon appartient à un métier (`role`), pas à un agent : toute leçon du développement
   sert à tout agent qui fait du développement. (Les étages genre et skill, déjà filtrés par rôle, ne changent pas.)
4. **Modèle par tâche, ni plus ni moins.** Chaque tâche tourne sur le modèle recommandé pour elle
   (`modele_necessaire.de_la_tache`, montée comprise). L'agent n'a plus de modèle plafond. **Fable** : si une tâche
   semble demander Fable, une décision est posée au bureau de direction **avant le lancement** ; rien ne part sur
   Fable sans l'accord du Directeur ; sans accord, la tâche part sur Opus. Jamais Fable sans accord (règle existante).
5. **Équipe = places.** À la création d'un projet, le Directeur choisit seulement le **nombre d'agents locaux et
   cloud**. Ces nombres sont exactement les places de l'onglet Facturation (`agents_locaux_max`,
   `agents_cloud_max`) : changer une place ajoute ou retire un agent. Les prénoms sont tirés automatiquement.
6. **Liens entre tâches.** Une tâche ne démarre que si les tâches dont elle a besoin sont faites. Si une vérification
   humaine (validation du Directeur, décision bloquante) est prévue en amont et n'a pas été faite, la tâche ne part
   pas : la place reste libre (la barre le dit déjà : « des places attendent une validation du Directeur »).
7. **Reprise des projets ouverts.** Chaque projet existant passe au nouveau standard par une reprise, sans perte :
   les leçons validées des fiches sont regroupées par métier, l'équipe est ramenée aux places.

## Ce que cela change, partie par partie

### Fiches et métiers

- Deux notions séparées :
  - **l'agent** (`fiches/<cle>.md`) : clé, prénom, lieu (local ou cloud), session cloud éventuelle. Plus de rôle,
    service, modèle, spécialité ni leçons.
  - **le métier** (`briefs/<role>.md`, existant) : la consigne de spécialiste, la spécialité, les outils, le service
    où il travaille, et ses leçons (`## Leçons`, même format que les fiches aujourd'hui).
- **[choix de conception]** Le service d'une tâche est celui de son étape (les étapes du workflow portent déjà
  `service`) ; à défaut, celui écrit dans l'en-tête du brief du métier.
- Les nouvelles leçons ont l'id `<role>:L<n>` (aujourd'hui `<agent>:L<n>`). **[choix de conception]** Les anciens
  ids ne sont pas réécrits (ni dans la mémoire genre/skill, ni dans les validations en cours) : ils restent lisibles
  et une leçon en attente de validation se valide toujours par son ancien id.
- La garde Fable par agent (`ACCORD_FABLE` dans la fiche) devient une garde **par tâche** (voir Modèles).

### Choix de l'agent (moteur)

- `agent_libre` ne filtre plus par rôle ni par plafond : il rend un agent libre au lieu demandé (local ou cloud),
  dans la limite des places.
- Le lieu d'une tâche : **[choix de conception]** un agent local si une place locale est libre, sinon cloud ;
  un métier réservé au local (émulateur, programmes installés sur le PC…) le dit dans l'en-tête de son brief
  (`Lieu : local`) et ses tâches attendent une place locale. La reprise le pose pour un métier dont toutes les
  anciennes fiches étaient locales et qui déclare des outils installés (`Outils`).
- **[choix de conception]** Une session cloud sert tous les métiers : la session clone le dépôt, et c'est le message
  de départ qui porte la consigne du métier. Un agent cloud garde donc une seule session.
- Les lots (`lots.former`) restent : un lot va à un seul agent, il peut mêler les métiers seulement si un message de
  lot sait porter plusieurs briefs (c'est déjà le cas : un brief par rôle) ; même modèle et même lieu, comme
  aujourd'hui.
- Le cadrage d'une fonctionnalité garde un agent attitré pendant le cadrage (`agent_cadrage`), pris parmi les agents
  libres.
- Une tâche reprise (retour, correction, session cloud) **[choix de conception]** revient de préférence au même
  agent s'il est libre (il a le contexte, la session cloud), sinon à n'importe quel agent libre.

### Liens entre tâches et vérifications humaines

- La prise d'une tâche par n'importe quel agent passe par la même vérification que les barrières actuelles : toutes
  les tâches amont faites, aucune validation du Directeur ni décision bloquante en attente en amont.
- **[choix de conception]** « En amont » = les étapes précédentes du workflow pour le même élément, plus les
  barrières de fonctionnalité existantes (`_barrieres`) ; le constructeur vérifie qu'aucun chemin (lot, reprise,
  `a_lancer`, retour) ne contourne cette vérification, et l'ajoute là où il manque, avec un test par chemin.

### Modèles et Fable

- Le modèle de lancement = `modele_necessaire.de_la_tache` (étape, nature, montée), plus aucun plafonnement par la
  fiche (`plafonne`, `ramene`, `_modele_de_depart`).
- Fable : aujourd'hui rien ne peut demander Fable (`modele_necessaire.MODELES` l'exclut des étapes, `depart.monter`
  s'arrête à Opus). Le Directeur veut que le moteur **puisse le proposer** quand il le juge nécessaire. Donc :
  - une étape peut porter `modele: Fable` (la validation des workflows l'accepte, toujours comme une proposition) ;
  - la montée peut aller d'Opus à Fable (une tâche qui a échoué sur Opus) ;
  - dans les deux cas, avant le départ, le moteur pose une décision au bureau de direction (« Cette tâche demande
    Fable : l'autoriser ? », avec la raison). Accord → la tâche part sur Fable (accord noté pour cette tâche
    seulement) ; refus → Opus. La tâche attend la réponse ; les autres continuent. Les estimations de coût comptent
    Opus tant que l'accord n'est pas donné.
- **[choix de conception]** Une tâche sans modèle d'étape (cadrage, prototype, installation, étape inconnue) prend le
  modèle par défaut de son métier, écrit dans l'en-tête du brief (`Modèle : …`) ; la reprise l'initialise avec le
  modèle de l'ancienne fiche de ce rôle ; sans métier connu : Sonnet.

### Places, équipe, Facturation

- Le nombre d'agents locaux et cloud = `agents_locaux_max` et `agents_cloud_max`. Augmenter une place crée une fiche
  d'agent (prénom tiré, couleur) ; la baisser retire un agent libre (jamais un agent au travail : il est retiré à la
  fin de sa tâche).
- **[choix de conception]** Les bornes restent celles de la factory : au moins 1 agent local, de 0 à 16 cloud. Un
  projet sans réglage prend les valeurs effectives d'aujourd'hui (2 locaux par défaut ; pour le cloud, la valeur que
  calcule `depart.places_cloud`, ancienne limite comprise). La reprise lit ces valeurs effectives, jamais l'absence de
  réglage, et ne crée aucun agent cloud au-delà.
- Le recrutement par rôle (`recruter`, `fiches_a_recruter`, `proposer`, le bloc « Recruter » de Facturation)
  disparaît, remplacé par le seul réglage des places.
- Un agent cloud sans session cloud : la démarche de session existante (« Sessions cloud à créer ») vaut pour lui.

### Création d'un projet et installation

- La proposition d'organisation (chef, installer, `proposer_organisation`) propose les métiers (briefs) du workflow et
  le nombre d'agents locaux et cloud, plus une fiche par agent. `verifier_organisation` exige un brief par métier du
  workflow, et non plus un agent par rôle.
- La fenêtre « proposition du chef » montre les métiers et « N agents locaux, M agents cloud ».

### Bureau vivant

- Un agent au travail va s'asseoir dans la pièce du **service du métier de sa tâche** ; libre, il va à la cafétéria.
  (**[choix de conception]**, pas encore confirmé par le Directeur.)
- Les panneaux qui filtrent les agents par service (`dossier.js`, `panneaux.js`, `connaissances.js`, `decisions.js`,
  `directeur.js`) filtrent par le service de la tâche en cours ; les leçons s'affichent par métier (panneau de
  service ou de connaissances) et non plus par agent.
- La carte d'un agent montre son lieu, sa tâche en cours et le modèle de cette tâche (plus de « Plafond »).

### Reprise des projets ouverts

Une commande de reprise, lancée depuis le bureau (bouton dans l'onglet Facturation ou à l'ouverture du projet, avec
confirmation du Directeur), qui :

1. crée un brief par métier s'il manque, à partir du texte d'une fiche de ce rôle (consigne, spécialité, outils) ;
2. regroupe les leçons **validées** des fiches dans le brief de leur métier (rôle de la fiche), en gardant le texte ;
   les leçons « à valider » vont aussi au métier, toujours « à valider » ; doublons exacts fusionnés ;
3. ramène l'équipe aux places : garde autant d'agents que de places (de préférence ceux qui ont une session cloud ou
   une tâche en cours), retire les autres une fois libres ;
4. ne touche à aucune tâche en cours ; écrit un compte rendu de la reprise (ce qui a été regroupé, retiré).

Elle est rejouable sans effet (idempotente).

## Hors champ

- Aucun changement des workflows, des étapes ni des validations eux-mêmes.
- Pas de nouveaux métiers ni de nouvelles consignes de spécialiste.
- Le Chef (orchestrateur) reste à part : il n'est pas un agent polyvalent.

## Contraintes du projet (rappel)

- Python 3.12 bibliothèque standard seule ; page en JS sans dépendance, testée avec `node --test`.
- Jamais Fable sans accord du Directeur ; aucune dépense réelle sans accord ; aucune clé écrite ni affichée.
- La skill garde la mécanique, jamais la connaissance d'un projet précis ; les données d'essai restent hors du dépôt.
- Tout ce qui se règle ici doit pouvoir se régler depuis le bureau.

## Laissé au constructeur

- Le format exact des fiches d'agent et des briefs enrichis, tant que l'ancien format reste lisible pendant la reprise.
- Le découpage en tâches, l'ordre, les noms internes.
- Le tirage des prénoms et des couleurs.
