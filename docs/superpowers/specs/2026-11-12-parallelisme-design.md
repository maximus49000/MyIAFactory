# Le parallélisme d'agents et les validations-barrières — conception

Date : 2026-11-12. Suite de `2026-11-12-workflow-des-la-creation-design.md` (étapes « validation du Directeur »).

## 1. Intention (les mots de l'utilisateur)

« Paramétrer le parallélisme d'agents : le nombre d'agents et d'agents cloud qui travaillent sur un projet […] On
priorise le parallélisme pour aller aux étapes intermédiaires de validation : si on a convenu une validation visuelle, on
n'attaque pas le jeu tant que le visuel n'est pas finalisé. » Le réglage est dans l'onglet Facturation. Une validation
ne porte que sur les éléments qu'elle concerne ; sous chaque élément à valider, seul SON compte rendu s'affiche, avec
l'objectif de l'élément et ce qu'il y a à valider.

## 2. Réglages (par projet, dans le fichier de factory)

- `agents_locaux_max` : 1 à 16, 2 par défaut (existant) — les places locales, soumises à la charge du poste.
- `agents_cloud_max` : 0 à 16, **0 par défaut** — les places cloud, hors charge du poste. Clé absente : un projet qui a
  déjà des agents cloud garde l'ancienne limite (`agents_cloud_max` de ses réglages, 3 par défaut) ; sans agent cloud,
  0. Le relevé publie la valeur effective.
- Modifiés depuis l'onglet Facturation (partie « Parallélisme du projet ») : demande `parallelisme`
  `{agents_locaux_max, agents_cloud_max}`, vérifiée par le bureau, puis par l'outil (`lancer parallelisme`, seule
  écriture), traitée par le moteur au passage suivant.
- Une place est tenue par un agent recruté (une fiche = une tâche à la fois, comme avant) : pour 3 tâches d'un même
  rôle en même temps, il faut 3 agents de ce rôle. Les places cloud ne servent qu'aux agents cloud recrutés, sur un
  projet GitHub (prérequis inchangés). La partie le rappelle (agents recrutés, locaux et cloud).

## 3. Ordonnancement (`regles._demarrer_en_attente`)

1. Pause manuelle ou installation prioritaire (`pause_globale`) : rien ne part (inchangé, au-dessus de tout).
2. Places libres = (`agents_locaux_max` − tâches actives d'agents locaux, 0 si la charge dépasse le plafond) +
   (`agents_cloud_max` effectif − tâches actives d'agents cloud).
3. Les tâches prêtes **retenues par une barrière** sont écartées ; les autres sont rangées : d'abord celles situées
   avant une validation à venir (cadrage, prototype, étapes avant une validation du workflow non franchie), puis les
   corrections, puis l'ordre de création. Chaque lot prend une place (locale d'abord, puis cloud).
4. Places restantes sans tâche permise alors qu'une validation attend le Directeur : le bureau le dit,
   « 2 places libres : en attente de votre validation « Validation de la direction artistique » » (fichier
   `attente-places.json`, comme l'attente de charge).
5. Série : le nombre d'éléments au travail en même temps vaut au moins 2 et au plus le nombre de places ; un élément
   qui attend le Directeur ou une barrière ne compte pas (sinon l'élément suivant, qui doit lui-même arriver à la
   validation, ne partirait jamais).

## 4. Barrières

- Toute validation du Directeur est une barrière : les validations fixes (cahier, méthode/prototype) le sont déjà par
  construction (la série ne part qu'après la méthode) ; une étape `validation` du workflow de rang k est **franchie**
  quand plus aucun élément qu'elle concerne n'est avant elle ou dessus (dans la file, en cours avant k, ou en attente
  du Directeur). Les éléments laissés de côté (bloqués) ne retiennent rien.
- Une tâche de flux de rang r > k ne démarre pas tant que la barrière k n'est pas franchie : ni pour un élément
  validé (il attend les autres), ni pour un élément non concerné.
- Calculé depuis le suivi à chaque passage (la file, les tâches de chaque élément), donc juste après un redémarrage.

## 5. Portée d'une validation (choix)

- Le découpage rend pour chaque élément, en option, `validations` (les `id` des étapes de validation du flux qui le
  concernent) et `objectif` (une phrase : ce que l'élément doit produire). La consigne de `decouper` les demande dès que
  le flux a une validation ; un `id` inconnu est ignoré.
- Défaut raisonnable : `validations` absent = **toutes** les validations concernent l'élément (les projets et
  découpages existants gardent leur comportement exact).
- Un élément non concerné passe l'étape sans arrêt (aucune décision), **mais reste soumis à la barrière** : l'étape de
  validation est placée dans un flux commun, ce qui la suit est fait par les mêmes agents avec ce qui vient d'être
  validé (le visuel validé sert au jeu, même à la mise en place du projet Godot quand elle continue après) ; le moteur
  ne peut pas savoir sans risque que la suite n'en dépend pas. L'élément évite seulement d'encombrer le Directeur.
  (Choix écarté : une déduction par mots du nom de l'étape et de l'élément — fragile, et silencieuse quand elle se
  trompe.)

## 6. Ce que voit le Directeur sous chaque élément à valider

- « Objectif : … » : `objectif` de l'élément s'il est donné ; sinon « Produire « <nom> » (<groupe>) » suivi de l'étape
  qui précède la validation et de la dernière consigne de sa tâche (une remarque du Directeur, par exemple). Sans appel
  d'IA.
- « À valider : <nom de l'étape> » et sa `raison` si le workflow en porte une.
- Le compte rendu de **cet** élément : dans un lot, la partie `comptes_rendus` du rapport qui le désigne (nouveau champ
  facultatif `[{element, texte, images?}]`, demandé aux lots) ; à défaut, les paragraphes du message qui le nomment
  (son id, son nom ou l'id de sa tâche) ; le message entier seulement si la tâche ne portait que lui. Les fichiers et
  images : ceux marqués de son élément (ceux sans élément seulement hors lot à plusieurs éléments).

## 7. Mesure

- Banc rejoué gratuit inchangé (un projet sans validation : ni barrière, ni changement d'ordre ; places = limite
  locale déjà appliquée par `agent-libre`).
- Essai réel : un projet à validation de direction artistique, 3 agents locaux, vérifier qu'aucune tâche de jeu ne
  part avant la validation et que la barre dit les places libres.
