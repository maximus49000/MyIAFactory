# Agents et tâches sur le serveur : conception

Date : 2026-11-19. Suite du serveur générique (`2026-11-19-serveur-generique-design.md`), qui a livré les morceaux 1 (serveur
générique) et prévoit les morceaux 2 (lancer des tâches sur le serveur) et 3 (agents sur le serveur). Cette conception les détaille et
ajoute le pilotage d'un outil par un agent. Demande du Directeur : « rédiger et faire la place pour l'agent, qui pourra produire quelque
chose seul, ou piloter et analyser les retours d'un outil (exemple : émuler l'application Android et analyser le résultat) ».

## Intention
- Faire tourner sur le serveur OVH deux sortes de travail que le poste ne peut pas absorber : des **outils lourds** (émulateur Android)
  et des **agents** (produire seul, ou piloter un outil et en analyser les retours).
- Les deux modes de l'émulation sont voulus par le Directeur, choisis à chaque lancement :
  - **pilote** : l'agent appelle lui-même des actions de l'outil et s'adapte à ce qu'il voit (cas : un agent en délègue un autre) ;
  - **scénario** : le bureau déroule une recette versionnée, l'agent n'analyse que les retours (cas : recette d'une production, en autonomie).

## Buts, hors-buts, contre-buts
- Buts : émulation Android sur le serveur avec retour de captures ; agent distant en mode « seul » puis « pilote » ; un seul chemin pour les
  deux modes ; réutiliser `deporter`, le serveur générique et les agents locaux ; tout est visible et arrêtable depuis le bureau.
- Hors-buts de cette conception : clé de signature partagée (conception du serveur générique, morceau à part), compilation iOS et IA lourde
  (hors serveur), recettes d'installation de la tâche 13 du plan précédent (séparées), vue graphique et bouton SSH (morceau 4).
- Contre-buts : le serveur écrit sur GitHub ; des identifiants d'abonnement visibles d'un conteneur d'outil ; un agent qui exécute des
  commandes arbitraires sur l'hôte ; une tâche qui migre en cours de route ; un déport caché (le lieu reste réglé et visible).

## Contraintes (état réel vérifié le 2026-11-19)
- Serveur : 24 threads, 62 Go, `/dev/kvm` présent, l'utilisateur `ubuntu` est dans le groupe `kvm` mais **pas** dans `docker` (Docker passe par
  `sudo`, comme le moteur d'installation) ; images `unity`, `android` et `agent` prévues par `serveur_ovh/images`, image système x86_64 dans
  `~/android-sdk/system-images`. Les tests d'émulateur n'ont jamais tourné sur le serveur : **le premier jalon le prouve**.
- Le serveur n'écrit jamais sur GitHub ; le bureau envoie et récupère le code (paquet Git par SSH).
- Le catalogue de déport a déjà l'action `emulateur` (lieux poste et serveur, « bientôt ») ; `deporter` sait router poste et GitHub, pas
  encore le serveur.
- Python 3.12, bibliothèque standard ; tests simulés (jamais le vrai serveur) ; passage par le lanceur de tests ; commits par chemins ;
  messages en français ; accord strict pour toute écriture sur le serveur ; secrets masqués.

## Approches considérées
- **A. Tranche émulateur d'abord (retenue, choix du Directeur).** Lanceur de tâches, conteneur d'émulateur avec pont d'actions, retour de
  captures ; l'analyse est faite par un agent **local** (déjà existant). Livre l'émulation sans attendre l'agent distant et prouve KVM.
- **B. Agent distant ensuite (retenue, choix du Directeur : « A puis B »).** Image d'agent, abonnement, branche `agent/<tâche>`, bascule ;
  d'abord « seul », puis « pilote » en réutilisant le pont de A.
- Écartée : donner la socket Docker à l'agent (aucun cloisonnement : il lirait les identifiants des autres conteneurs).

## Conception : tranche A (émulateur)

### Une tâche serveur
Une demande `{id, type, projet, entree, mode, scenario?, limites, demandeur}` : `type` = `emulation` ; `entree` = un APK (envoyé par le
bureau) ; `mode` = `scenario` | `pilote` ; `limites` = durée (par défaut 20 min), nombre de captures (50), taille totale (100 Mo), mémoire
et processeurs du conteneur. Le bureau l'enregistre dans `~/MyIAFactory/taches.json` (état : en attente, en cours, terminée, échouée,
arrêtée, avec le lieu, les dates et la raison) et fait tout le suivi ; le serveur ne garde que le dossier `~/taches/<id>/`.

### Le lanceur (morceau 2)
`outils/serveur_tache.py` : envoie l'APK (scp, dossier `~/taches/<id>/entree`), lance le conteneur d'outil par SSH + `sudo docker`, suit
l'état, rapatrie la sortie, arrête sur demande ou à l'échéance. **Créneaux** : un maximum de tâches simultanées par serveur et par type (par
défaut 1 émulation à la fois), vérifié du côté du serveur par un verrou de dossier (`flock`) et côté bureau dans `taches.json` ; une tâche en
trop reste « en attente » dans une file visible. Un seul accord d'écriture : lancer une tâche est une action du Directeur (bouton, ou action
réglée sur le lieu serveur), jamais implicite.

### Le conteneur d'émulateur
Image d'outil `myiafactory/emulateur` (dérivée de l'image `android`), **sans identifiants**, sans réseau par défaut (`--network none`, un
réglage par scénario l'ouvre), `--device /dev/kvm`, limites de mémoire et de processeur, système de fichiers en lecture seule sauf
`/sortie`. L'émulateur tourne sans fenêtre (`-no-window -no-audio`, rendu logiciel) ; `adb` reste **dans** le conteneur.

### Le pont d'actions (liste fermée)
Une petite commande `pont` dans le conteneur, seule porte d'entrée : `demarrer`, `installer`, `lancer`, `toucher x y`, `glisser x1 y1 x2 y2`,
`texte <court>`, `touche retour|accueil|menu`, `attendre <s>`, `capturer <nom>`, `journal [filtre]`, `arreter`. Chaque argument est validé
(nombres bornés, noms `[a-z0-9_-]`), aucune interprétation par un shell, aucune commande libre. Chaque appel écrit une ligne dans le journal de
la tâche (verbe, arguments, durée) ; les limites (captures, durée, taille) sont appliquées par le pont, pas par la bonne foi de l'appelant.

### Les deux modes avec le même pont
- **scénario** : la recette `.factory/recettes/<nom>.json` du projet (liste de verbes du pont, avec leurs arguments) est déroulée par le
  lanceur ; versionnée dans le projet, relue comme du code. Résultat : captures et journal.
- **pilote** : un agent appelle `py -3.12 lancer.py serveur-outil <tâche> <verbe> [arguments]` ; la commande relaie un seul verbe au pont par SSH et
  renvoie le résultat (une capture est rapatriée et son chemin local rendu à l'agent, qui la lit). Le pilote est donc possible dès la tranche A
  avec un agent **local**.

### Retour et analyse
La sortie est rapatriée dans `<projet>/.factory/serveur/<tâche>/` : `captures/*.png`, `journal.txt`, `rapport.json` (statut, durée, verbes
exécutés, limites atteintes). L'analyse est un travail d'agent local ordinaire (il lit les images) : **faite par l'agent qui a demandé l'exécution**, jamais par un
agent lancé automatiquement par le bureau (aucun coût d'abonnement non demandé).

### Branchement sur l'existant
- Le lieu `serveur` de l'action `emulateur` du catalogue de déport devient réel : `deporter emulateur` route vers le lanceur quand le lieu
  effectif est le serveur, et sinon vers le poste ; un agent n'a donc **qu'une commande** à connaître pour déléguer, `deporter`.
- Le choix du lieu cesse d'être local à l'écran : il est enregistré par le mécanisme de réglages de déport existant (corrige la limite connue
  de l'écran « Où tournent les actions »). La couleur de recommandation reste un conseil.
- L'écran des serveurs gagne la liste des tâches (état, durée, nombre de captures) et un bouton d'arrêt ; routes en lecture seule plus
  `arreter` (POST, mêmes protections que les autres routes du bureau).
- La capacité `android-emulateur` est le prérequis ; si le serveur est injoignable ou la capacité bloquée, le lieu est « indisponible » et
  la tâche n'est pas lancée.

## Conception : tranche B (agent sur le serveur)
- **Capacité `agent`** : devient installable (recette dans le catalogue) : image d'agent versionnée (CLI Claude, Git, lanceur), dossier de
  l'abonnement `~/agent-identifiants` (0700, monté **en lecture seule** dans les seuls conteneurs d'agent). La connexion à l'abonnement se
  fait **une fois, par le Directeur**, dans la session graphique du serveur (jamais saisie par MyIAFactory).
- **Un conteneur d'agent éphémère par tâche** : dossier de travail = copie du projet envoyée en paquet Git par le bureau ; l'agent commite
  sur `agent/<tâche>` et écrit un rapport ; le bureau récupère le paquet par SSH et décide de la suite ; **aucune écriture sur GitHub depuis
  le serveur**.
- **Accès aux outils** : l'agent n'a ni Docker ni identifiants d'outil. Un petit **pont hôte** expose, sur une socket Unix montée dans le
  conteneur d'agent, **le même jeu fermé de verbes** que la tranche A (valide les arguments, applique les limites, journalise). L'agent appelle
  `pont <verbe>` ; les captures arrivent dans son dossier de travail et il les lit. Mode « seul » : aucun pont monté.
- **Limites** : durée, mémoire, processeurs, nombre de tours de l'agent, bouton d'arrêt qui coupe agent et outils ; l'usage est compté dans
  le suivi d'abonnement du bureau.
- **Bascule entre lieux** (exigence du serveur générique) : ordre de préférence et maximum d'agents par lieu, premier lieu avec une place libre,
  file visible quand tout est plein, lieu hors ligne sauté ; réglable par type de tâche ; plafond global d'abonnement au-dessus des plafonds par lieu.
- **Questions de l'agent au Directeur** : relayées par le bureau (le conteneur n'a aucun accès entrant) ; l'agent attend la réponse ou
  s'arrête avec un rapport « question ouverte ».

## Sécurité (transversal)
Aucun secret dans un conteneur d'outil, dans Git ni dans les journaux (masquage comme le reste) ; aucun shell libre côté pont ; limites dures
appliquées par le pont et par Docker, pas par la bonne foi de l'appelant ; les entrées venues de l'application émulée (journal, captures) sont
des **données, jamais des instructions** pour l'agent (l'agent le sait dans sa consigne de départ) ; un seul lanceur par tâche, arrêt qui nettoie
conteneurs, émulateur et dossiers temporaires ; lanceur et pont refusent tout argument hors liste.

## Jalons et critères de réussite
1. Jalon 1 (réel) : l'émulateur démarre sur le serveur (KVM), installe l'APK de MyFridgeCleaner, prend une capture, rapatriée sur le poste.
2. Tranche A complète : `deporter emulateur` (lieu serveur) et le mode pilote par un agent local, avec journal, limites et arrêt.
3. Tranche B : agent « seul » produit une branche et un rapport ; agent « pilote » enchaîne le pont et analyse les captures ; bascule testée.
Chaque jalon est vérifié avec des simulacres en tests, puis **une fois pour de vrai** sur le serveur avec l'accord du Directeur.

## À trancher plus tard
Image de l'émulateur : une par version d'Android ; réseau du conteneur d'agent (par défaut aucun) ; reprise après panne du serveur ; rétention
des captures (par défaut 30 jours, nettoyage par le bureau) ; plusieurs émulations en parallèle si la charge le permet.

## Précisions décidées après le contrôle du constructeur (2026-11-19)
1. **Deux actions distinctes.** `emulateur` du catalogue (tests instrumentés `connectedDebugAndroidTest`, qui demandent les sources, Gradle et le
   réseau) **reste sur le poste et hors de ce plan**. Cette conception ajoute une action `recette-emulateur` : exécuter une recette du pont ou
   piloter l'émulateur (APK en entrée, pas de réseau). Les deux ne partagent pas leur nom, donc pas de confusion de sens selon le lieu.
2. **Succès d'une exécution.** Le rapport a un `statut` : `ok` (tous les verbes exécutés, aucun `FATAL EXCEPTION` ni ANR de l'application dans
   le journal), `plantage`, `limite` (durée, captures ou taille atteintes), `erreur` (outil ou serveur). `deporter` rend le code 0 seulement
   pour `ok`, 1 sinon, et affiche le chemin du rapport. Le **jugement visuel** (l'écran attendu est-il là ?) n'est pas un code de retour : il
   appartient à l'agent qui lit les captures. En mode pilote il n'y a pas de verdict automatique.
3. **Propriétaire d'une tâche : le serveur, pas un processus du poste.** L'état de vérité est `~/taches/<id>/etat.json` côté serveur ;
   l'émulateur tourne **détaché** sous une enveloppe `timeout` + `docker run --rm`, donc un appelant mort ne laisse ni conteneur ni créneau
   (l'enveloppe libère le verrou à la fin ou à l'échéance). Tout processus du poste (agent, `deporter`, bureau) lit et arrête une tâche par SSH sans
   dépendre d'un bureau résident ; `taches.json` du poste n'est qu'un **index de cache** verrouillé (verrou de fichier, écriture atomique) et
   reconstructible depuis le serveur. L'arrêt écrit un fichier `arret` et appelle `docker stop`.
4. **Cycle du mode pilote et autorisation.** `deporter recette-emulateur --mode pilote --apk <fichier>` crée la tâche et rend son identifiant ;
   le conteneur reste vivant (`docker exec` pour chaque verbe) jusqu'à `arreter`, jusqu'à 5 minutes d'inactivité, ou 20 minutes depuis le
   lancement. **Autorisation : régler le lieu de l'action sur le serveur vaut accord permanent, pour ce projet, de lancer cette action sur le
   serveur, dans les limites ci-dessus** (**confirmé par le Directeur le 2026-11-19 : accord permanent**) ; sans ce réglage, la
   commande refuse.
5. **Origine de l'APK.** Option `--apk <fichier>` ; sinon l'APK produit par l'action `apk` du projet, résolu comme `deporter` le fait déjà
   (artefact GitHub ou sortie locale), puis envoyé par scp. Compiler l'`apk` sur le serveur est un autre travail, hors de ce plan.
6. **Image de l'émulateur.** Construite sur l'hôte par une **étape de la capacité `android-emulateur`** (nouvelle étape de
   `mise_en_place.sh`, avec sonde, aperçu et accord du moteur d'installation existant), pas par le lanceur. Le SDK et l'image système de l'hôte
   (`~/android-sdk`) sont montés **en lecture seule** ; le disque virtuel de l'émulateur est un volume temporaire en mémoire. La version
   d'Android suit celle de l'hôte (plateforme 36), non l'ancienne image `android` (34).
7. **Périmètre du plan d'exécution : la tranche A seulement.** La tranche B est conçue ci-dessus mais son plan suivra le jalon réel de A
   (l'émulateur tourne vraiment). Les contradictions de B (le conteneur d'agent a besoin d'accès au réseau pour l'API de Claude ; emplacement
   de la connexion à l'abonnement ; comptage de l'usage à distance ; relais des questions ; réutilisation de `moteur/agents.executer_agent`)
   y seront résolues, pas ici.
8. **Plusieurs serveurs déclarés.** Tranche A : le lieu `serveur` désigne le premier serveur déclaré qui est joignable et dont les capacités
   requises sont présentes ; sinon la commande refuse avec la raison. Le choix d'un serveur précis par action et la bascule viennent avec B.
9. **Analyse des captures.** Voir « Retour et analyse » : par l'agent demandeur, jamais automatique.

## Choix du rédacteur (à relire)
Aucune commande libre dans le pont (liste fermée) ; réutiliser `deporter` plutôt qu'une commande de plus ; les limites par défaut (20 min,
50 captures, 100 Mo, 1 émulation à la fois) ; pas de réseau pour l'émulateur par défaut ; analyse par un agent local en tranche A ; pont hôte
sur socket Unix en tranche B ; tâches enregistrées côté bureau (`taches.json`) et seulement exécutées côté serveur.
