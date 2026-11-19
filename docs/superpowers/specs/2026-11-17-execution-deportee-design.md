# Exécution déportée : confier les tâches lourdes à GitHub, puis à un serveur (conception)

## Pourquoi
Compiler l'APK, lancer les tests, l'émulateur ou les tests de charge **ralentit le poste** (PC de 7,5 Go) et fait perdre
du temps au Directeur. Il veut **déporter les tâches les plus coûteuses en mémoire et en processeur** vers l'extérieur
pour que le poste reste fluide. La skill étant globale, **tout est paramétrable** : quelqu'un dont l'ordinateur suffit
laisse tout sur le poste (comportement par défaut).

## Buts / hors-buts / à éviter
- Buts : des cases à cocher, dans le bureau, qui disent **où s'exécute chaque type d'action** ; le résultat revient
  dans la fiche du projet ; la consommation est suivie.
- Hors-buts (cette version) : déport automatique selon la charge du poste ; saisie des secrets à la place du Directeur ;
  achat ou création de serveur par l'application ; Windows et macOS côté GitHub (facturés plus cher).
- À éviter : une application qui dépend de GitHub pour fonctionner ; un fichier de workflow poussé sans accord ;
  un dépassement de quota qui facture sans prévenir ; une régression du flux local (le défaut reste *poste*).

## Approches considérées
A. GitHub seul : simple et gratuit en public, mais quota en privé et émulateur/charge aléatoires.
B. Serveur personnel seul (type Hetzner) : tout est possible, mais administration et coût dès le départ.
**C. Un lieu par type d'action, GitHub d'abord puis serveur (retenue par le Directeur).**

## Conception
1. **Types d'action** : `apk`, `tests`, `charge`, `emulateur` (liste extensible).
2. **Lieux** : `poste` (défaut), `github`, `serveur`. Un réglage par type d'action.
3. **Portée du réglage** : valeur globale (configuration de la skill) avec **surcharge par projet**, dans les réglages
   du projet (`bureau/reglages.py`, comme `lecons_auto`), validée à la lecture. Les cases du bureau écrivent là.
4. **Étape 1, `github`** : à partir des cases, le bureau génère `.github/workflows/<projet>.yml` (Linux uniquement),
   l'**affiche pour validation** avant le premier push, puis le pousse. Déclencheurs : push, bouton manuel, planification
   (tests de charge de nuit). L'APK compilé est publié en artefact.
5. **Étape 2, `serveur`** : le lanceur de tests exécute la commande sur le serveur par SSH, avec le même verrou de
   campagne que sur le poste (voir CLAUDE.md). Ajouté après l'étape 1, sans refaire l'écran.
   Ce lieu s'appuie sur la plateforme OVH (voir `2026-11-19-serveur-ovh-plateforme-design.md`).
6. **Retour des résultats** : la fiche du projet montre, par action déportée, réussi/échoué, durée et lien. Les agents
   lisent ce résultat (`gh run list/view`) au lieu de lancer la commande.
7. **Suivi de la consommation** : somme des durées d'exécution par projet, type d'action et mois, dans la vue des coûts.
   Quota officiel (minutes restantes) lu par l'API de facturation **si** le Directeur accorde l'autorisation `user` à
   `gh` ; sinon, estimation par les durées. Alerte à 80 % du quota ; blocage possible des actions coûteuses avant
   dépassement. Dépôt public : illimité, pas de quota à afficher.
8. **Hors ligne ou refus** : si le lieu choisi est indisponible (pas de réseau, quota atteint), l'action est
   **proposée au poste avec accord du Directeur**, jamais relancée en silence.

## Dépendances entre actions (ajout demandé par le Directeur)
Une action peut avoir besoin du produit d'une autre (les tests ont besoin de l'APK). Si elles ne tournent pas au même
lieu, l'agent doit **attendre** la première, puis récupérer son produit.
1. **Dépendances déclarées** : chaque type d'action dit ce qu'il produit et ce qu'il consomme (`apk` produit l'APK ;
   `tests` et `emulateur` le consomment ; `charge` consomme l'APK ou l'application lancée). Liste extensible.
2. **Le point d'entrée les résout** : `lancer.py deporter <type>` regarde d'où vient ce dont l'action a besoin.
   Produit au même lieu : rien à attendre. Produit ailleurs (APK compilé par GitHub, tests au poste) : il attend la
   fin de l'exécution distante, télécharge l'artefact (`gh run download`), puis lance l'action.
3. **Attente visible et non confondue avec un blocage** : la fiche dit « en attente de l'APK (GitHub, depuis N min) »
   et le garde-fou « sans action depuis N min » ne l'arrête pas pendant cette attente. Une durée type est affichée
   (celle des exécutions passées) ; au-delà d'un seuil, l'attente passe en alerte.
4. **Échec en amont** : si l'APK échoue chez GitHub, l'action dépendante n'est pas lancée ; la fiche renvoie vers
   l'échec, sans retenter en boucle.
5. **Avertissement dans l'écran des cases** : une combinaison qui impose une attente est signalée (« les tests au poste
   attendront l'APK de GitHub, environ N min ») avec la suggestion de mettre la chaîne entière au même lieu.
6. **Même produit, plusieurs consommateurs** : l'APK n'est compilé et téléchargé qu'une fois par version du code
   (identifiée par le commit) ; les actions suivantes le réutilisent.
7. **Version du code** : l'action distante travaille sur le commit poussé ; si l'agent a des changements non poussés,
   le point d'entrée les pousse (sur une branche de travail, avec accord) ou refuse, jamais de compilation d'un code
   différent de celui que l'agent teste.

## Contraintes
- Le dépôt MyFridgeCleaner est **privé** : quota gratuit limité (environ 2 000 min/mois sur Free, à vérifier).
- Les secrets (clé de signature de l'APK, jetons) restent saisis par le Directeur dans GitHub.
- `gh` n'a aujourd'hui que les droits `repo`, `workflow`, `read:org`, `gist`.
- Un agent cloud ne doit jamais attendre un accord impossible (cas t151) : si l'émulateur n'est pas disponible au lieu
  choisi, le dire clairement.

## Choix du rédacteur (à relire, non validés par le Directeur)
1. **Aiguillage** : un point d'entrée commun `lancer.py deporter <type>` lit le lieu réglé et exécute sur le poste ou
   chez GitHub ; `lancer.py tests` l'appelle, et la consigne de départ des agents (`orchestrateur/depart.py`) renvoie
   `apk`, `charge` et `emulateur` vers lui. Étape 1 = réglage + workflow + ce routage.
2. **Workflow régénéré** : fichier marqué « généré » avec une empreinte. Un changement de case produit un nouveau diff
   à valider avant push ; un fichier modifié à la main (empreinte différente) n'est jamais écrasé : le bureau demande.
3. **Sans équivalent réaliste** : `github` propose `apk`, `tests` et `charge` (planifiée) ; `emulateur` y est grisé avec
   le message « peu fiable sur GitHub, utilisez le poste ou le serveur ».
4. **Bouton manuel** = `workflow_dispatch` via `gh`. Charge de nuit à 03:00 par défaut, réglable.
5. **Quota** : cache local dans `~/MyIAFactory`, affiché dans la vue des coûts existante. À 80 % : alerte. À 100 % :
   proposition de passer au poste, avec accord du Directeur (jamais de blocage ni de bascule automatiques).
6. **Serveur** : affiché grisé « bientôt » à l'étape 1 ; la configuration SSH est de l'étape 2.
7. **Public ou privé** : détecté par `gh repo view`, avec possibilité de corriger à la main.

## Laissé au réalisateur
Nom et emplacement du réglage global ; mise en page des cases ; forme exacte du workflow par type de projet ; cache des
résultats ; tests.
