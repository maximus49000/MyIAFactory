# Captures de validation prises sur le serveur — conception

Date : 2026-11-25. Statut : **implémenté (voir le plan)**.

## 1. Intention

Pour valider une correction ou une nouvelle fonctionnalité, le Directeur installe l'APK et cherche lui-même ce qui a
changé. Deux fois le 2026-11-25 (FM_Stats), le livrable transmis ne contenait pas les corrections annoncées ; même quand
il les contient, il faut les retrouver dans l'application. Le Directeur veut que la validation soit **illustrée par des
captures de l'application réelle**, prises sur le serveur, qui montrent ce qui a été fait.

Mots du Directeur (2026-11-25) :
- « lancer sur le serveur une prise de capture dans l'environnement réel de l'applicatif pour illustrer les validations
  (bien sûr si possible) » ;
- pour les corrections en cours **et** pour chaque nouvelle correction ou fonctionnalité ;
- pour les suivantes, « on demandera pour chaque correction si on souhaite une capture des nouveaux éléments ou non » ;
- « on ne reprend pas toutes les captures mais celles qui illustrent ce qui a été fait. Ça peut être une capture ou
  plusieurs, selon qu'il y a un workflow avec enchaînement d'actions ».

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Une validation montre, sans que le Directeur ait à chercher, **ce qui a changé** : une capture, ou une suite de
  captures quand le changement est un enchaînement d'actions (ordre et légendes dits).
- Les captures viennent de **l'APK qui est joint à la validation** : si l'APK est périmé ou absent, pas de capture.
- Une **correction** montre, quand c'est possible, l'avant et l'après du même écran (appel de Claude, à confirmer) ;
  une **fonctionnalité** ne montre que le résultat (il n'y a pas d'avant).
- Le choix « capture : oui / non » est fait **par demande** (correction ou fonctionnalité), pas pour tout le projet.
- Pour les trois corrections de FM_Stats en cours le 2026-11-25 (t84, t85, t86) : la capture est faite à la livraison
  de leur APK, sans les refaire.

**Non-objectifs**
- Pas de tour complet de l'application : seulement ce que la demande a changé.
- Pas de test automatique de l'application ni de remplacement de la validation du Directeur.
- Pas de nouvel émulateur ni de nouveau serveur : l'émulateur du serveur (tranche A, mode « pilote ») existe.
- Pas de capture sur le poste du Directeur ni sur un téléphone.

**Anti-objectifs** (un échec même si « ça marche »)
- Une capture qui ne vient pas de l'APK joint (ancienne version, autre branche) : elle ferait croire à une correction
  absente ou présente à tort.
- Une validation bloquée parce que la capture est impossible (créneau pris, émulateur indisponible) : la capture est
  un plus, la validation avec l'APK reste possible, avec la raison dite en clair.
- Un coût d'agent non voulu : sans « oui », rien ne se lance.
- Des dizaines de captures dont aucune ne dit ce qui a changé.

## 3. Contraintes (état de `main`, 2026-11-25)

- Le mode **pilote** existe : un agent serveur conduit un émulateur Android par `pont <verbe>` (`demarrer`, `capturer`,
  `arreter`…), captures lues sous `/outil/` (`docs/serveur-agents.md`, « Pilote »). Conditions : l'action
  `recette-emulateur` réglée sur « serveur » pour le projet, **un APK trouvé au lancement**
  (`moteur/boucle.py: apk_pour_le_pilote`), un serveur sondé avec `agent`, `agent-abonnement` et `emulateur-image`.
  FM_Stats les remplit (sonde du 2026-11-25 09:11 : `emulateur-image` présente ; `recette-emulateur: serveur`).
- **Un seul créneau d'émulation par serveur**, partagé avec les tâches « Test » et les recettes : les captures de
  plusieurs validations passent l'une après l'autre.
- Limites de l'émulation liée : 50 captures, 64 Mo par fichier, pas de réseau, durée bornée par le temps de l'agent.
- Les agents de correction de FM_Stats ont écrit (contrôles C121, 2026-11-25) qu'une correction visuelle « sans
  émulateur ne peut pas produire de capture » : ils partaient « seuls ». Cause **non vérifiée** ; hypothèse : l'étape
  démarre avant que l'APK de la correction existe, ou avec un ancien APK.
- Une validation porte déjà des **images** (`nature: visuel`, `message.images`, `releve.est_image`) ; l'écran de
  validation (`bureau/web/ui/validation.js`) sait les afficher. Le livrable d'une correction est exigé et daté
  (`regles._apk_exige`, `_apk_perime`, PR 40).
- Le choix d'une correction se pose au dépôt de la demande (bureau) ; l'agent d'une correction est cadré par une fiche
  (`fiche_correction`) dont le mode opératoire (« Installer l'APK, ouvrir … ») est déjà écrit pour la validation.
- Les consommations d'agent serveur passent par l'abonnement : une capture coûte du temps d'agent et des jetons.
- Tests par le lanceur (`CLAUDE.md`) ; mêmes garde-fous que les agents serveur : l'émulateur ne porte jamais d'accord
  sans que `recette-emulateur` soit réglé sur « serveur ».

## 4. Approches considérées

- **A. Une étape de capture dédiée, après la construction de l'APK final — retenue (recommandée).** Un agent pilote
  installe l'APK joint, va à l'écran concerné d'après la fiche et le mode opératoire, prend la ou les captures qui
  illustrent le changement, avec légendes et ordre. Pour une correction, une première passe sur l'APK précédent donne
  l'« avant ». Les captures sont jointes à la validation. Avantages : l'APK est déjà le bon ; fonctionne pour les
  corrections en cours ; l'émulateur n'est tenu que le temps de la capture. Coût : une étape d'agent de plus.
- **B. L'agent du correctif prend lui-même ses captures** (le moteur construit l'APK avant de le lancer en pilote).
  Une seule étape, mais l'agent garde l'émulateur longtemps et juge son propre travail ; l'APK change encore pendant
  l'étape. Écartée pour la vérité des captures.
- **C. Un script de navigation écrit à la main par projet, sans IA.** Peu coûteux, mais à écrire pour chaque écran et
  fragile dès qu'un écran change : inadapté à des corrections variées. Écartée.

Choix du Directeur (2026-11-25) : **A**.

## 5. Conception

### 5.1 Le choix « capture : oui / non »
- À chaque dépôt d'une correction ou d'une fonctionnalité, le bureau pose la question « Illustrer la validation par des
  captures de l'application ? » (oui par défaut quand la demande touche l'interface, non sinon ; appel de Claude).
  Le choix est mémorisé avec la demande (champ de la fiche de la demande) et lisible par le moteur.
- Hors projet à APK ou sans émulateur « serveur » : la question n'est pas posée (ou posée grisée avec la raison).
- Pour les trois corrections en cours (t84, t85, t86) : « oui », décidé ici par le Directeur.

### 5.2 L'étape de capture
- Elle se place **entre la construction de l'APK et la décision de validation** : le moteur (`_attendre_le_directeur`)
  ne pose la validation qu'avec l'APK à jour (PR 40) ; avec « capture : oui », il lance d'abord l'étape de capture, puis
  pose la validation avec les captures jointes.
- L'agent de capture reçoit : la fiche (ce qui a changé), le mode opératoire déjà écrit, l'APK joint, et pour une
  correction l'APK précédent (celui qui a servi à la validation d'avant, ou la dernière livraison). Il rend la **liste
  ordonnée** des captures avec, pour chacune, sa légende (ce qu'on y voit et ce qui a changé) et, pour un enchaînement,
  l'étape de l'enchaînement. Il écarte celles qui n'illustrent rien.
- Sortie : images jointes à la décision (mêmes chemins et types que les images de validation actuelles), avant et après
  côte à côte quand les deux existent.

### 5.3 L'écran de validation
- Une section « Ce qui a changé » : les captures dans l'ordre, légendées ; « avant » / « après » pour une correction ;
  les étapes numérotées pour un enchaînement. Au-dessus des points à vérifier, sous le « En clair ».
- Sans capture (non demandée, impossible, échec) : l'écran dit pourquoi en une ligne et garde l'APK à télécharger.

### 5.4 Les cas dégradés
- Créneau d'émulation pris : la capture attend son tour (file) ; si l'attente dépasse le délai (§6 bis, 5), la validation
  est posée sans capture avec la raison.
- Émulateur ou agent en échec, ou écran introuvable : même chose, jamais une validation retenue.
- Projet non Flutter / sans APK : hors périmètre de cette première livraison.

## 6. Ce qui est laissé au réalisateur

La forme de l'étape (workflow de correction étendu, ou tâche à part comme les tests serveur), le délai d'attente du
créneau, le nom des champs, le format de la liste de captures, la présentation fine de l'écran (une maquette à valider
avec le Directeur avant la mise en forme), le découpage en tests, et la manière d'obtenir l'APK « avant »
(archive de la dernière livraison, ou reconstruction de la branche précédente).

## 6 bis. Précisions décidées après relecture (appels de Claude, à vérifier par le Directeur)

1. **Tâche 0, et barrière : comprendre pourquoi les agents de FM_Stats partent « seuls ».** Le moteur note la raison
   (`mode pilote impossible, l'agent serveur part seul… : <raison>`) dans son journal (`moteur-sortie.log`) ; celui du
   2026-11-25 a été écrasé par la relance de 09:40, la raison est donc à relever au prochain lancement d'un agent. Si
   la cause est structurelle (le pilote n'est pas ouvert aux étapes de correction, ou l'APK n'existe pas au lancement),
   une correction préalable vient avant l'étape de capture ; l'approche A reste la même.
2. **L'« avant » est au mieux, jamais exigé.** Corrections : l'avant est pris si l'APK précédent est retrouvé (la
   dernière livraison validée archivée, sinon la reconstruction de la branche d'avant n'est **pas** faite en première
   version). Sinon : « après » seul, avec la mention « avant non disponible ». §5.3 l'affiche ainsi.
3. **Corrections en cours (t84, t85, t86).** Rien n'est ajouté à une validation déjà posée (une décision n'est pas
   modifiée après coup). Leur validation n'est pas encore posée (renvoyées ou en cours le 2026-11-25) : l'étape de
   capture s'applique donc naturellement à leur prochaine livraison d'APK. Pas de « capture à demander plus tard » en
   première version (retiré de §5.4).
4. **Où se pose le choix.** Au dépôt dans le bureau (formulaire de demande). Une demande qui n'en vient pas (correction
   créée par un agent, ligne de commande) et toute fiche sans le champ valent **« non »** : rien ne se lance sans « oui »
   (coût). Pour t84, t85, t86 le « oui » est écrit à la main dans leur demande.
5. **Bloquant, avec délai.** L'étape de capture est bloquante pour poser la validation, bornée à **20 minutes** d'attente
   du créneau et **15 minutes** de travail de l'agent (valeurs de départ, à régler ensuite). Au-delà : validation posée
   sans capture, raison dite en une ligne, APK à télécharger.
6. **Créneau et budget.** Les captures de validation passent dans la file du créneau d'émulation comme les tâches
   « Test » (premier arrivé, premier servi ; pas de priorité). Au plus **8 captures** par validation (l'enchaînement le
   plus long reste lisible), dans la limite de 50 de l'émulation.
7. **Une fonctionnalité.** Elle a déjà un mode opératoire exigé à la validation d'un élément « en jeu » ; l'agent de
   capture le suit. S'il ne trouve pas l'écran, il le dit (« écran introuvable : <raison> ») : le Directeur voit cette
   ligne à la place des captures, et la validation reste posée.

8. **Faits finaux, différents de la proposition.** (a) Les images voyagent par la **copie de l'agent** (`/outil/captures/<nom>.png` vers
   `<pièces>/<fid>/captures/<tid>/`, un dossier par tâche de capture, commit, chemin relatif cité) puis l'**extraction par le moteur depuis la branche** rapatriée, avant la fusion
   (`moteur/cloud.py : extraire_de_la_branche`) ; seuls les chemins d'images `.factory/pieces/<x>/…` sont acceptés. (b) L'« avant » est une **seconde tâche de capture**
   (une émulation = un APK), sur l'APK archivé `.factory/livrables-precedents/dernier.apk` ; la phase est bornée à 2 x (20 + 15) = 70 minutes. (c) Le minuteur des
   20 minutes vit dans la **mémoire du moteur** et repart après un redémarrage du moteur.

## 7. Risques

| Risque | Parade |
|---|---|
| Capture d'un APK périmé | la capture n'est lancée qu'avec l'APK déjà accepté par `_apk_perime` ; son nom et sa date sont écrits sur la capture |
| Agent qui capture le mauvais écran | légende obligatoire, vérifiée contre la fiche ; le Directeur voit aussi l'APK et peut renvoyer |
| Créneau d'émulation saturé | file d'attente, délai, validation posée sans capture |
| Coût d'agent | « oui » demandé par demande ; une seule étape de capture par validation |
| Causes de l'absence de capture constatée (C121) mal comprises | vérifier d'abord pourquoi les agents sont partis « seuls » (journal du moteur) |
