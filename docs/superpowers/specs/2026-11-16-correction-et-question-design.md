# « Nouvelle correction » et « Une question » — conception

Date : 2026-11-16. Décidé avec le Directeur ; les points **[choix de conception]** sont à vérifier à la relecture.

## Pourquoi

Le bureau n'a qu'une porte d'entrée pour faire travailler la factory : « + Nouvelle fonctionnalité ». Deux besoins
passent mal par elle :

- **Une anomalie** du projet (« le score ne se remet pas à zéro ») suit tout le parcours d'une fonctionnalité :
  classement du genre, proposition de workflow, cadrage, cahier des charges, découpage. C'est lourd, cher, et la
  factory ne sait pas qu'il s'agit de réparer l'existant.
- **Une question** sur le projet (« comment est calculé le score ? », « que se passe-t-il si le joueur quitte en plein
  niveau ? ») n'a aucune porte : la poser en « nouvelle fonctionnalité » lance un parcours de production pour rien.

## Ce qui est décidé (par le Directeur)

1. **Deux boutons à côté de « + Nouvelle fonctionnalité »** : « + Nouvelle correction » et « ? Une question ».
2. **Une correction suit un parcours court dédié** : pas de classement de genre ni de cahier des charges ; un cadrage
   court, puis diagnostic et correctif, vérification, validation du Directeur.
3. **Une question reçoit une réponse en escalade** : d'abord un appel court sur les documents du projet (sans lire le
   code) ; s'il n'est pas sûr, ou sur le clic « Chercher dans le code », un agent lit le dépôt et répond.
4. **Les questions sont gardées par projet**, dans un panneau « Questions », avec des questions de suivi dans le même
   fil. Quand la réponse suggère une fonctionnalité ou une correction, un bouton ouvre le formulaire correspondant
   **prérempli d'un brouillon**, que l'utilisateur relit avant d'envoyer.

## Ce que cela change

### 1. La barre du haut

- `bureau/web/ui/barre.js` : deux boutons de plus, `boutonCorrection` (« + Nouvelle correction ») et `boutonQuestion`
  (« ? Une question »), placés juste après `boutonNouvelle`. Ils suivent exactement sa règle d'affichage (relevé
  version 4 et commande `agir`).
- `bureau/web/ui/panneaux.js` : `boutonCorrection` ouvre le panneau `fonctionnalite` en mode correction
  (`ouvrirPanneau("fonctionnalite", null, {nature: "correction"})`) ; `boutonQuestion` ouvre le panneau `questions`.
- Sur un écran étroit (téléphone), les trois boutons gardent le comportement de repli actuel de la barre.

### 2. Nouvelle correction

#### Le modèle

- Une correction **est une fonctionnalité** qui porte `nature: "correction"` (absent : `"fonctionnalite"`, comme
  aujourd'hui ; aucun projet existant ne change). Elle profite ainsi de tout ce qui existe : Kanban, tâches,
  facturation, coût et empreinte carbone, fenêtre de validation, documents, transfert au catalogue.
- Elle peut viser une **fonctionnalité concernée** (`concerne: "<fid>"`, facultatif) : le diagnostic reçoit alors son
  cahier des charges et ses éléments comme contexte.
- La liste « Fonctionnalités » et l'en-tête du panneau montrent un badge « Correction ».

#### Le formulaire

Le panneau `fonctionnalite` en mode correction (`bureau/web/ui/fonctionnalite.js`) :
- titre « Nouvelle correction » ;
- un texte guidé (aide sous le champ) : ce qui se passe, comment le reproduire, ce qui était attendu ;
- les images et fichiers joints, comme une fonctionnalité ;
- une liste « Fonctionnalité concernée » (facultative) : les fonctionnalités du projet hors corrections terminées.

La demande déposée reste `fonctionnalite`, avec deux champs facultatifs de plus : `nature` (`"correction"`) et
`concerne` (un id de fonctionnalité du relevé). `bureau/demandes.py` les vérifie : `nature` dans
`("fonctionnalite", "correction")`, `concerne` présent dans le relevé et seulement avec `nature: "correction"`.

#### Le parcours (moteur)

`moteur/regles.py`, `_sur_fonctionnalite` : une demande `nature: "correction"` ne passe ni par `_classer` ni par
`_proposer`. Elle part sur `_sur_correction` :

1. La fonctionnalité est créée avec `nature` et `concerne`, nommée comme aujourd'hui (`_nommer`), et prend le **genre
   du projet** (ou celui de la fonctionnalité concernée) pour ses leçons et règles ; aucune décision de genre n'est
   posée.
2. Son **workflow de correction** est construit **par le code, sans appel d'IA** (`orchestrateur/workflows.py`,
   `de_correction(fac, fid)`), à partir des métiers du projet :

   | Étape | Rôle | Ce que fait l'agent |
   |---|---|---|
   | `<fid>-cadrage` | rôle de cadrage du projet (`_role_cadrage`) | lit le signalement ; pose une ou deux questions au Directeur **seulement si** il ne peut pas reproduire ou comprendre l'attendu ; sinon passe |
   | `<fid>-correctif` | rôle de production (`_role_production`) | reproduit l'anomalie par un test qui échoue, trouve la cause, corrige, fait passer le test et les tests existants |
   | `<fid>-verification` | rôle QA s'il en existe un dans les métiers du projet | rejoue le scénario du signalement et les tests ; **étape absente** si le projet n'a pas de rôle QA |
   | `<fid>-validation` | validation du Directeur | reçoit le diagnostic (cause), le correctif (fichiers touchés) et la preuve (test qui passe, captures) |

   La consigne de chaque étape vient d'un fichier de consignes de la skill (`orchestrateur/consignes-correction.md`)
   **[choix de conception]**, rappelé au départ de l'agent comme les autres consignes.
3. Le cadrage court démarre aussitôt (`_repondre_cadrage`, avec la consigne de correction). Il ne rend pas de cahier
   des charges : il se termine par une **fiche de correction** (symptôme, reproduction, attendu, fonctionnalité
   concernée), gardée comme document de la fonctionnalité, **sans validation du Directeur** à ce stade
   **[choix de conception]**. Pas de découpage : une correction a **un seul élément**, la correction elle-même, et la
   tâche `<fid>-correctif` est créée directement avec la fiche pour matière.

Un projet sans rôle de production identifiable (cas qui ne devrait pas exister après l'installation) : la correction
est posée en décision au Directeur (« quel métier corrige ? »), comme les autres cas où le moteur ne sait pas.

### 3. Une question

#### Le stockage

- `orchestrateur/questions.py`, sur le modèle de `orchestrateur/anomalies.py` : un fichier
  `.factory/questions.jsonl` à côté du fichier de factory, **un fil par ligne** :
  `{id: "q1", ouverte: date, fonctionnalite?: fid, messages: [{auteur: "utilisateur"|"factory", texte, images?,
  niveau?: "documents"|"code", sur?: bool, suggestion?: {...}, date}], etat: "en_cours"|"repondue"|"en_lecture"}`.
- Au plus 200 fils ; au-delà, les plus anciens partent d'abord. Une ligne illisible est ignorée.
- Commande `lancer questions` (lister, ouvrir, ajouter un message, changer l'état) ; le relevé publie `questions`
  (les 50 derniers fils, messages coupés à `MAX_RETOUR`).

#### Les demandes du bureau

`bureau/demandes.py`, deux demandes version 4 de plus :
- `question` : `texte` (obligatoire), `images` et `fichiers` (facultatifs, mêmes règles que `message`), `fil`
  (facultatif : l'id d'un fil existant pour une question de suivi), `fonctionnalite` (facultatif : la question porte
  sur cette fonctionnalité) ;
- `question_approfondir` : `fil` (obligatoire), un fil dont le dernier message est une réponse « documents ».

#### Premier niveau : l'appel court sur les documents

Nouveau type de jugement `repondre_question` (`moteur/jugement.py`, consigne `moteur/consignes/repondre_question.md`),
modèle **Sonnet** **[choix de conception]** : Haiku répond trop vite « je ne sais pas » sur des questions de
fonctionnement.

- **Dossier** : `projet` (nom, description), `genre`, `fonctionnalites` ([{id, nom, nature, etape, resume du cahier}]),
  `fonctionnalite` visée (cahier complet et éléments, si la question en vise une), `regles_projet`, `fil` (les messages
  précédents), `question` (texte, images), `mots_interdits`.
- **Réponse validée** : `{reponse: texte (markdown, ≤ MAX_RETOUR), sur: bool, suggestion: null | {nature:
  "fonctionnalite"|"correction", texte: brouillon de la demande (≤ MAX_TEXTE), concerne?: fid}}`.
  `sur: false` quand la réponse dépend de la façon dont c'est codé ; `suggestion` seulement si la question révèle un
  manque (fonctionnalité) ou un comportement anormal (correction). `concerne` ne peut citer qu'une fonctionnalité du
  dossier.
- Une réponse invalide est redemandée une fois (règle commune des jugements) ; un second échec répond « Je n'ai pas pu
  répondre » avec le bouton « Chercher dans le code ».

#### Second niveau : l'agent lecteur

- Il part **automatiquement** quand l'appel court rend `sur: false`, ou sur `question_approfondir`.
- C'est un `claude -p` **Sonnet**, lancé par `appel.appeler` avec `outils=["Read", "Grep", "Glob"]` : `--tools` ne lui
  donne que ces trois outils, il ne peut ni écrire ni lancer de commande. Dossier courant : le dépôt du projet.
- Consigne `moteur/consignes/lire_pour_repondre.md` : chercher dans le code, citer les fichiers lus
  (`chemin:ligne`), répondre dans la même forme JSON que `repondre_question` (avec `niveau: "code"`).
- Il tourne **dans un fil du moteur** (comme l'attente d'un agent), pas dans un processus détaché, et ne prend **pas de
  place d'agent** du Kanban **[choix de conception]** : c'est une lecture courte, pas de la production. Son usage est
  noté par `lancer usage` comme tout appel (coût visible dans la facturation, ligne « Questions »). Si le moteur
  redémarre pendant la lecture, le fil repasse en `repondue` avec le message « Lecture interrompue » et le bouton
  « Chercher dans le code ».
- Le bouton « Chercher dans le code » affiche avant le clic le coût estimé et la part d'abonnement
  (`bureau/prix.py`, `bureau/abonnement.py`).

#### Distinction avec la question au Chef

Le message au Chef (`_question_au_chef`, jugement `conseil`) reste ce qu'il est : une question sur **l'avancement**
de la factory (qui fait quoi, ce qui bloque). « Une question » porte sur **le projet et son fonctionnement**. Les deux
ne se mélangent pas.

#### Le panneau « Questions »

`bureau/web/ui/questions.js` (nouveau), ouvert par le bouton de la barre :
- en haut, le champ « Votre question » (texte, images), une liste facultative « À propos de » (une fonctionnalité) et
  « Envoyer » ;
- dessous, les fils du plus récent au plus ancien : la question, puis chaque réponse rendue en markdown
  (`bureau/web/ui/markdown.js`), avec un repère « D'après les documents » ou « D'après le code » ;
- sous une réponse : « Poser une question de suivi » (le même champ, rattaché au fil) ; « Chercher dans le code » sur
  une réponse « documents » ; et, si la réponse a une `suggestion`, « Ouvrir une correction » ou « Ouvrir une
  fonctionnalité » ;
- pendant le traitement : l'accusé de réception habituel (« Reçu, en cours de traitement… »), puis « Lecture du code
  en cours… » pour l'agent lecteur.

« Ouvrir une correction / fonctionnalité » ouvre le panneau `fonctionnalite` dans le mode voulu, champ texte prérempli
du brouillon (et `concerne` présélectionné). **Rien n'est envoyé sans le clic de l'utilisateur.**

## Ce qui ne change pas

- Le parcours d'une nouvelle fonctionnalité, ses demandes et son relevé (les nouveaux champs sont facultatifs).
- Les projets existants : sans `nature`, une fonctionnalité est une fonctionnalité.
- Le bureau ne fait toujours qu'envoyer des demandes ; c'est le moteur du projet qui agit.

## Tests

Rapides et qualitatifs, sans appel d'IA réel (les appels sont simulés comme dans les tests existants) :
- `tests/test_demandes.py` : `fonctionnalite` avec `nature` / `concerne` (valides, `concerne` inconnu, `concerne` sans
  correction) ; `question` et `question_approfondir` (fil inconnu, texte vide, images) ;
- `tests/test_orch_workflows.py` : `de_correction` avec et sans rôle QA, ids préfixés ;
- `tests/test_moteur_parcours.py` : une correction ne pose aucune décision de genre ni de workflow et démarre le
  cadrage ; une correction qui vise une fonctionnalité transmet son cahier ;
- `tests/test_questions.py` (nouveau) : stockage (ajout, suivi, limite, ligne illisible) ; `repondre_question` valide
  et invalide (`concerne` hors dossier) ; escalade automatique sur `sur: false` ; l'agent lecteur est appelé avec les
  seuls outils de lecture ; lecture interrompue ;
- un essai manuel sur la démo (`exemples/`, copiée ailleurs) : les deux boutons, une correction jusqu'au cadrage, une
  question et son ouverture d'un brouillon.

## Documentation

- `README.md`, section « Fonctionnalités » : une ligne pour chaque nouveau parcours.
- `docs/avancement.md` : l'état de la réalisation.
- `docs/releve.md` : `questions`, `nature` et `concerne` dans le relevé.
