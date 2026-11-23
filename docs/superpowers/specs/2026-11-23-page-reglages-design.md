# Page « Réglages » : un registre de réglages à trois niveaux — conception

Date : 2026-11-23. Statut : **proposition, à valider par le Directeur. Rien n'est implémenté.**

## 1. Intention

Le bureau de direction accumule des réglages sous un titre qui n'a aucun rapport (« Leçons à valider ») et répète le
même choix à deux endroits. Le Directeur veut **une page de configuration**, sans redite, où chaque réglage se pose à
plusieurs niveaux (global, par type de projet, par projet) et où l'on voit d'où vient la valeur en vigueur.

### Les redites constatées (état de `main`, 2026-11-23)

- « Où tournent les actions » existe deux fois : bloc de Direction (`bureau/web/ui/deport.js`, boutons poste / GitHub /
  serveur par projet) et carte « Serveurs de travail » (`bureau/web/ui/serveurs.js`, `dessinerLieux`, pastilles d'état +
  boutons). « Où s'exécutent les étapes » (`lieux.js`, local / cloud / indifférent) est un autre choix au nom voisin.
- Six réglages sont rangés sous « Leçons à valider » (`directeur.js`, autour de `caseLeconsAuto`) : leçons automatiques,
  analyse des blocages, livraison sur demande, évolution moyenne en une session, dossier approuvé cloud, déport.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Un seul endroit pour régler : la page « Réglages ». Direction ne garde que décisions, leçons à valider, échanges.
- Trois niveaux, un ordre fixe : **projet > type de projet > global > défaut**. Chaque valeur affiche son origine
  (« hérité du global », « du type Android », « propre à ce projet ») et un bouton « revenir à l'hérité ».
- Un **registre** : chaque réglage déclaré une fois (id, libellé, aide, forme de la valeur, niveaux permis, défaut,
  section). La page et la résolution lisent le registre ; ajouter un réglage = une déclaration.
- Livraison par étapes : d'abord le registre, la page et le déport ; ensuite les six cases de Direction.

**Non-objectifs**
- Pas de réécriture de la logique de déport (`bureau/deport.py`, `lancer.py deporter`, verrou du poste).
- Les réglages de l'application des projets eux-mêmes ne sont pas concernés (seulement ceux du bureau / du moteur).
- Le design « tests sur le serveur » (places, ordre de préférence) n'est **pas** dans ce lot ; le registre doit
  seulement pouvoir l'accueillir ensuite.

**Anti-objectifs** (un échec même si « ça marche »)
- Un réglage qui apparaît à deux endroits. Un réglage dont la valeur effective n'est pas explicable depuis la page.
- Un changement silencieux de comportement : après migration, chaque projet garde exactement ses valeurs actuelles.
- Un réglage de sécurité (accord permanent, recette au seul serveur) qui devient héritable sans que ce soit voulu.

## 3. Contraintes

- **Existant à conserver** : fichier du bureau (`reglages.lire_bureau`, `fichier_bureau`) = niveau global ;
  `<projet>/.factory/reglages.json` = niveau projet (`/api/reglages?projet=`, écriture par le serveur du bureau avec
  l'en-tête `X-Bureau`) ; `deport.lieu_effectif` déjà en cascade projet > global > poste.
- **Nouveau** : le niveau « type de projet » n'existe pas comme niveau de valeurs (le catalogue du type, dans
  `deport_types.py`, dit seulement ce qui est possible). Le genre se lit dans `.factory/factory.json`. Il faut un
  endroit où écrire des valeurs par type (proposition : section `types.<genre>` du fichier du bureau).
- Règle déjà en vigueur à respecter : une action « au seul serveur » (recette émulateur) ne prend que le réglage du
  projet, jamais l'héritage ; le registre doit pouvoir déclarer « niveaux permis = projet seulement ».
- Écriture : le serveur valide et refuse, l'interface redit l'état réel en cas de refus (comportement actuel).
- Aucun coût d'IA ; tests par le lanceur (`CLAUDE.md`), tests touchés seulement au quotidien.

## 4. Approches considérées

- **A. Registre + page qui le lit — retenue.** Une résolution unique, une page générique, extensible.
  Coût : reprendre le stockage des cases ; on migre le déport d'abord (cascade déjà là), puis les cases une à une.
- **B. Déplacer les blocs existants dans une page, sélecteur de niveau pour le seul déport.** Rapide, mais les six
  cases restent « par projet seulement » et chaque nouveau réglage global est à recâbler à la main. **Reprise comme
  deuxième temps de A** : le déplacement des six cases se fait une fois le registre prêt.
- **C. Deux pages (globale, par projet).** Mêmes réglages dans les deux : redites. Écartée.

Choix du Directeur : **A d'abord, puis le déplacement des cases (B)**.

## 5. Conception

### 5.1 Registre et résolution (côté serveur du bureau)

- Un module de registre déclare chaque réglage : `id`, `section`, `libelle`, `aide`, `forme` (booléen, choix, entier,
  table par action), `niveaux` (sous-ensemble de `global`, `type`, `projet`), `defaut`.
- Une fonction unique `valeur_effective(id, projet)` rend `{valeur, origine}` avec `origine` ∈ `defaut | global |
  type:<genre> | projet`. `deport.lieu_effectif` en devient un cas (table par action), sans changer ses résultats.
- Lecture : l'état du bureau publie, par projet, la liste des réglages avec valeur effective et origine. Écriture :
  `POST /api/reglages` accepte déjà le niveau projet ; on ajoute le niveau (global ou type) et la suppression
  (« revenir à l'hérité » = effacer la clé du niveau). Le serveur valide selon la `forme` du registre.

### 5.2 La page

- Nouveau panneau « Réglages » du bureau (même mécanique que les autres panneaux), sections : *Où tournent les
  actions*, *Agents : local ou cloud (par étape)*, *Automatisations*, *Partage des connaissances* (déjà global).
- Sélecteur de niveau en haut : Global | Type (celui du projet courant) | Projet (le projet courant). On y édite ce
  niveau ; chaque ligne montre en plus la valeur effective et son origine, grisée si un niveau plus proche la masque.
- « Où s'exécutent les étapes » est rebaptisé « Agents : local ou cloud » pour ne plus ressembler à « Où tournent les
  actions ».
- Les réglages à niveau « projet seulement » n'apparaissent pas sous Global / Type.

### 5.3 Fin des redites

- « Serveurs de travail » : `dessinerLieux` devient **lecture seule** (pastilles d'état, « Manque : … ») avec un lien
  « Régler dans Réglages » ; les boutons de choix y disparaissent (un seul endroit de saisie).
- Direction : les six cases et `blocDeport` en sortent au fur et à mesure de leur migration (étape 2) ; à la fin,
  « Leçons à valider » ne contient plus que des leçons.

### 5.4 Étapes de livraison

1. **Registre + résolution + page, avec le déport** (les trois niveaux, origines, retour à l'hérité) ; lecture seule
   dans « Serveurs de travail ». Direction montre encore les six cases.
2. **Migration des six cases** vers le registre et la page ; retrait de Direction. Valeurs existantes conservées.
3. Hors lot : réglages des places / ordre de préférence du design « tests sur le serveur ».

## 6. Ce qui est laissé au réalisateur

Forme exacte du registre et des fichiers (hors respect de 3.), emplacement et nom de la section `types`, présentation
fine de la page (maquettes à valider avec le Directeur avant la mise en forme), découpage en tests.

## 6 bis. Précisions décidées après relecture (appels de Claude, à vérifier par le Directeur)

- **Sans genre, ou genre hors catalogue** : le niveau « type » est sauté et le sélecteur Type est grisé (résolution :
  projet > global > défaut).
- **« Agents : local ou cloud » (`lieux.js`)** : ce choix est propre à chaque étape de chaque projet et passe par une
  demande au projet ; il ne reçoit **pas** de niveaux global / type. Étape 1 : la section est seulement *affichée* dans
  la page (déplacée de Direction, comportement inchangé) ; elle ne passe pas par le registre.
- **« Partage des connaissances »** (déjà global) : affiché dans la page au niveau Global, migré au registre à l'étape 2.
  Sans projet sélectionné, la page ne montre que le niveau Global.
- **Valeur inapplicable** (action non offerte au type du projet) : au niveau projet, l'écriture est refusée ; aux
  niveaux global et type, elle est acceptée mais ignorée pour les projets concernés, avec l'origine « non applicable ».
- **Niveaux permis des six cases** : voir 6 ter (à confirmer).

### 6 ter. Niveaux permis proposés (question au Directeur)

| Réglage | Niveaux | Raison |
|---|---|---|
| Valider les leçons automatiquement | global, type, projet | confort, sans accord engagé |
| Analyse intelligente des blocages | global, type, projet | idem |
| Évolution moyenne : une seule session | global, type, projet | idem |
| Livrer seulement sur demande | global, type, projet | idem (réduit les envois) |
| Dossier approuvé pour les sessions cloud | **projet seul** | accord permanent sur un dossier précis |
| Déport : actions au seul serveur (recette émulateur) | **projet seul** | accord permanent, règle déjà en vigueur |
| Déport : autres actions | global, type, projet | cascade déjà en place |

| Livrer automatiquement sur GitHub (`livraison_github`, absente de la liste d'origine) | **projet seul** | publie hors du bureau ; appel de Claude après la maquette |

Défauts inchangés : chaque projet garde sa valeur actuelle à la migration.

### 6 quater. Précisions après maquette (2026-11-23, validée par le Directeur)

- Le moteur (`moteur/boucle.py`, `moteur/regles.py`) lit ces réglages par `reglages.charger(<projet>)` : pour qu'une valeur
  posée en global ou par type agisse vraiment, ces lectures passent par la valeur effective (étape 2, point sensible).
- Dans « Serveurs de travail », les boutons de « Où tournent les actions » n'enregistraient rien (conseil local). La
  carte devient « Aptitude des lieux », en lecture seule, avec un lien vers Réglages.
- La section « Agents : local ou cloud » de la page affiche un résumé et renvoie aux étapes (choix par étape, par projet).

## 7. Risques

| Risque | Parade |
|---|---|
| Changement de comportement à la migration | tests de non-régression : valeurs effectives avant / après identiques pour chaque projet |
| Un réglage de sécurité devenu héritable | niveaux permis déclarés au registre ; test dédié à la recette émulateur |
| Fichier du bureau abîmé ou écrit à la main | lecture tolérante comme `lieux_du_projet` (valeur inconnue = défaut), jamais d'écrasement silencieux |
| Écritures concurrentes (deux projets, fichier du bureau partagé) | écriture atomique du fichier du bureau, relecture avant écriture |
