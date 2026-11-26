# Les tests sur le serveur et des places par lieu — évaluation et conception

Date : 2026-11-20. Statut : **proposition, à valider par le Directeur. Rien n'est implémenté, rien n'a été mesuré sur le serveur
(accord requis), `CLAUDE.md` n'est pas modifié.**

## 1. Ce qui existe

- **Verrou unique du poste** : `outils/campagne.py` (`~/MyIAFactory/tests-en-cours.json`, file d'attente
  `tests-en-attente/`, repérage des suites lancées sans lanceur). Les agents y passent par `lancer.py tests ... -- <commande>`
  (consigne `tests_un_a_la_fois()` de `orchestrateur/depart.py`). Motif : 2 suites en parallèle sur le PC (7,5 Go) = jusqu'à
  10 fois plus lent (1 861 s au lieu de 253 s).
- **Déport** : `lancer.py deporter <type>` route une action vers `poste` ou `github` (`docs/deport.md`) ; `tests` est déjà
  déportable sur GitHub. Le lieu `serveur` est grisé « bientôt » sauf pour `recette-emulateur`.
- **Tâches serveur (tranche A, fusionnée)** : `outils/serveur_tache.py`, conteneur éphémère sans réseau ni secret, envoi
  d'entrées, rapatriement de `sortie/`, créneau `flock` **unique** (`~/taches/.creneau-emulation`), limites par défaut
  (6 Go / 2 processeurs pour l'émulateur), arrêt, rapport, index local `taches.json`.
- **Tranche B** : branche `agents-serveur-b`, **pas encore fusionnée dans `main`** (6 commits en avance : enveloppe d'agent,
  capacités `agent` / `agent-abonnement`). Cette évaluation a été préparée avant cette fusion ; la section 5 dit ce qui
  dépend d'elle (bascule `lieu_pour`, file visible, plafonds par lieu).

## 2. Chiffrage — ce qu'on sait, ce qu'on ne sait pas

**Mesuré sur le serveur : rien.** Aucun essai n'a été lancé (règle : accord explicite du Directeur avant tout essai réel).

Données disponibles (poste, fichier `.durees-tests.json`) : 143 modules de test, **2 340 s de travail cumulé**, suite
complète 253 s sur le poste en parallèle (≈ 9 cœurs utiles). Le plus long module : 217 s ; ensuite 165, 149, 123, 111 s.

**Estimation (à confirmer par mesure, pas un résultat)** : sur 12 threads Linux sans contention, le travail cumulé donne
2 340 / 12 ≈ **200 s** en suite seule, plancher imposé par les gros modules (217 s) — donc entre 220 et 300 s selon la vitesse
des cœurs. Avec K suites en parallèle sur 12 threads, le débit total n'augmente pas : K suites durent environ K fois plus
chacune une fois les 12 threads saturés. **Le gain du serveur n'est pas d'aller plus vite que le poste, c'est de ne plus
charger le poste et de ne plus faire la queue derrière une seule suite.** Marge mémoire : 62 Go, émulateur 6 Go + ~3,4 Go
résidents, agents de la tranche B (à chiffrer), le reste est largement libre ; le disque (~12 Mo par tâche d'émulation, aucun
nettoyage) est le point à surveiller.

**N recommandé (provisoire, à valider par la mesure de la section 6)** : **N = 2 places de tests** sur le serveur, chacune
limitée à 5 processeurs (`--cpus 5`, `-j 5`), soit 10 threads sur 12 ; **N = 1 place** (ou 2 à `--cpus 4`) tant qu'une
émulation (2 processeurs, ~160 %) ou des agents tournent. Une place de plus ne gagne rien tant que les 12 threads sont pris.

## 3. Risque principal : les tests passent-ils sous Linux ?

La suite de MyIAFactory est écrite et jouée sous Windows : **58 des 159 fichiers de `tests/`** mentionnent `powershell`,
`schtasks`, `.exe` ou `ctypes.windll`, et `campagne._lancer` distingue `win32`. Une partie échouera ou sera ignorée sous
Linux. Il faut donc **d'abord** un passage à blanc de la suite complète en conteneur Linux (sur GitHub Actions, gratuit pour un
dépôt public, ou sur le serveur après accord) pour établir la liste des tests dépendant de Windows, avant tout chiffrage fiable.
Pour les **projets des agents** (Gradle, vitest, etc.), le risque est plus faible : ce sont déjà des outils portables, et
GitHub les joue sous Linux.

## 4. Conception proposée

### 4.1 Nouvelle action : « tests sur le serveur »

Sur le modèle de `recette-emulateur`, mais **déportable depuis `tests`** : le lieu `serveur` devient réel pour l'action
`tests` (même catalogue, même réglage par projet). `lancer.py deporter tests` route : poste, GitHub **ou serveur**.

1. **Envoi** : le lanceur construit un paquet Git du **commit poussé** (`git bundle`, comme `deporter` refuse déjà un travail
   non poussé — code 6) ; les modifications non commitées ne partent jamais. Variante simple : `git archive HEAD`.
2. **Exécution** : conteneur éphémère dédié aux tests (image `tests`, distincte de l'image émulateur), **sans réseau pendant
   les tests**, sans secret, utilisateur non root, `--cap-drop ALL`, lecture seule sauf `/work` (copie du paquet) et `sortie/`,
   `--memory`, `--cpus`, durée maximale, nombre de processus bornés (mêmes principes que la tranche A).
   Les dépendances (npm, Gradle, pip) : étape préalable **avec** réseau limité à des dépôts de paquets, ou cache monté en
   lecture seule ; **à décider** (question Q3).
3. **Rapatriement** : `sortie/` = sortie standard, code de sortie, rapport (modules en échec, « instable » comme
   `tests_paralleles`), durées (alimentent `.durees-tests.json` du serveur) ; copié dans
   `<projet>/.factory/serveur/<id>/` ; code de retour de `deporter` = celui des tests (0 / 1), 2 usage, 4 serveur injoignable.
4. **Même cadre de tâche** que la tranche A : `etat.json`, index `taches.json`, arrêt depuis le bureau, rapport, limites.

### 4.2 Des places par lieu à la place du verrou unique

Un **registre de places** par lieu, avec compteur et file d'attente (premier arrivé, premier servi, comme `campagne.py`) :

| Lieu | Places de tests | Réglage |
|---|---|---|
| poste | **1** (inchangé : c'est le motif du verrou) | fixe |
| serveur | **N** (2 recommandé, voir 2) | réglable dans le bureau, par serveur |
| GitHub | illimité (quota vérifié par `deporter`, code 8) | — |

- **Serveur** : un répertoire `~/taches/.places-tests/place-<k>` verrouillé par `flock` (k de 1 à N) — c'est le créneau
  existant, généralisé de 1 à N. Le compteur est la vérité côté serveur, donc robuste si le poste redémarre ; un veilleur
  détaché garde la place même si le lanceur meurt (comme l'émulation). Un cadre dans `etat.json` : `place: k`.
- **Réservation de ressources, pas seulement de places** : une place de tests `--cpus 5` et un émulateur `--cpus 2` doivent
  tenir ensemble dans 12 threads ; le lanceur refuse si la somme des processeurs réservés dépasse un plafond réglable
  (par défaut 12) ; sinon la tâche attend, comme l'émulateur le fait aujourd'hui (code 75, nouvel essai toutes les 15 s).
- **Choix du lieu** : comme la bascule de la tranche B (`lieu_pour`) : ordre de préférence réglable par type d'action (par
  défaut serveur, GitHub, poste), **premier lieu avec une place libre**, lieu hors ligne sauté, **file visible** si tout est
  plein. **Jamais de bascule silencieuse vers le poste** (règle déjà en vigueur dans `deport.md`) : le poste n'est choisi que
  s'il est dans l'ordre réglé par le Directeur.
- **Le verrou du poste reste** pour les tests au poste : `campagne.py` ne change pas, il devient simplement « le registre à
  1 place du lieu poste ». Les suites lancées sans lanceur sont toujours repérées au poste.

### 4.3 Effets sur le reste

- **`CLAUDE.md`** (à modifier **seulement après accord**) : la règle « une seule campagne à la fois sur le poste » ne change
  pas pour le poste ; on ajoute que, si le réglage `tests = serveur` est posé, les tests passent par
  `python lancer.py deporter tests`, qui prend une place au serveur et non le verrou du poste. `outils/tests_paralleles.py`
  gagne `--serveur` (même découpage en morceaux, envoyé par le lanceur).
- **Lanceur de tests** (`lancer.py tests`) : il passe déjà par `deporter` quand les tests sont sur GitHub ; il fera de même
  vers le serveur. Sans réglage, comportement actuel (verrou du poste).
- **Consigne de départ** (`orchestrateur/depart.py`) : `tests_un_a_la_fois()` dit aujourd'hui « une seule campagne à la fois sur
  le poste ». Avec le réglage serveur, la consigne donne la commande `deporter tests` et dit que **le nombre de places est
  géré par le lanceur** : l'agent n'a rien à compter, il attend son tour.
- **Bureau** : le bloc « Où tournent les actions » active « Serveur » pour `tests` ; la carte « Serveurs de travail »
  montre « places de tests : 1/2 prises » et la file.
- **Accord** : régler `tests` sur serveur est, comme pour la recette, un accord permanent par projet (mêmes limites de
  protection, dites dans `serveur-taches.md`).

## 5. Dépendance avec la tranche B

La bascule `lieu_pour`, les plafonds par lieu et la file visible sont **dans `agents-serveur-b`, non fusionnée**. Les
réutiliser évite de les écrire deux fois ; il vaut donc mieux **attendre la fusion** avant d'implémenter. Les agents sur le
serveur consommeront aussi des processeurs et de la mémoire : le plafond global de ressources (section 4.2) doit compter
agents + tests + émulation ensemble.

## 6. Protocole de mesure (à lancer **après accord**)

Sur le serveur, une seule campagne de mesure à la fois, en conteneur de test avec `--cpus` et `--memory` posés :

1. suite complète **seule** (`--cpus 12`, puis `--cpus 5`) : durée, pic de mémoire, écriture disque ;
2. **2, 3, 4 suites en parallèle** à `--cpus 5`, `--cpus 4`, `--cpus 3` : durée de chacune, pic cumulé, charge ;
3. **idem avec une émulation en cours** (6 Go, 2 processeurs) : durée des suites, durée de démarrage de l'émulateur (45 s
   mesurés seul) ;
4. relevés : `docker stats`, `/proc/meminfo`, `iostat`, taille de `/var/lib/docker` avant et après ; nettoyage des conteneurs et
   dossiers ensuite ;
5. déduire N et le plafond de processeurs. Durée prévue : ~30 à 45 minutes de serveur ; coût : aucun (serveur déjà loué).
   Prérequis : l'étape 3 de la section 3 (liste des tests dépendant de Windows) sinon les durées ne veulent rien dire.

## 7. Risques

| Risque | Gravité | Parade |
|---|---|---|
| Tests de MyIAFactory dépendant de Windows | élevée | passage à blanc sous Linux d'abord ; exclusion ou adaptation des tests concernés |
| Saturation du serveur (agents + émulation + tests) | moyenne | plafond global de processeurs, places réglables, file visible |
| Disque du serveur (aucun nettoyage aujourd'hui) | moyenne | nettoyage automatique des tâches terminées **avant** d'ouvrir les tests |
| Dépendances qui exigent le réseau | moyenne | cache monté en lecture seule, ou étape de téléchargement séparée ; décision Q3 |
| Sécurité : exécuter le code d'un agent sur le serveur | moyenne | mêmes protections que l'émulation (sans secret, sans socket Docker, non root, sans réseau pendant les tests) |
| Panne du serveur ou du réseau | faible | pas de repli silencieux sur le poste ; l'ordre de lieux réglé par le Directeur décide |
| Écart entre les durées mesurées au poste et sur le serveur (instabilités de chronométrage) | faible | « instable » relancé seul, comme aujourd'hui |

## 8. Plan (après accord)

1. Passage à blanc Linux de la suite (GitHub Actions ou conteneur) → liste des tests Windows.
2. Nettoyage automatique de `~/taches` (prérequis disque).
3. Mesures de la section 6 → N et plafond de processeurs.
4. Registre de places côté serveur (généralisation du créneau, `flock`, `place: k`, plafond de ressources) + tests simulés.
5. Image `tests`, action `tests` lieu serveur dans `deporter` et le catalogue, rapatriement du rapport.
6. Bureau : réglage, carte des places, file ; documentation (`serveur-taches.md`, `deport.md`).
7. Consigne de départ et `CLAUDE.md` mis à jour **sur demande**, puis premier essai réel sur un projet.

## 9. Questions pour le Directeur

- **Q1** : accordez-vous les **mesures sur le serveur** (section 6, ~45 min, une campagne à la fois, rien de laissé après) ?
  Et le passage à blanc Linux de la suite de MyIAFactory (GitHub, gratuit car dépôt public) ?
- **Q2** : le serveur est-il **prêt à héberger aussi** les agents de la tranche B et l'émulateur ? Quelle priorité en cas de
  saturation (émulation > agents > tests, ou autre) ?
- **Q3** : les projets ont besoin du réseau pour installer leurs dépendances (npm, Gradle) : autorisez-vous un réseau limité
  aux dépôts de paquets pendant une étape préalable, ou préférez-vous un cache de dépendances préparé ?
- **Q4** : **attendre la fusion de la tranche B** (recommandé : on réutilise `lieu_pour` et la file) ou commencer avant ?
- **Q5** : l'ordre de préférence par défaut pour `tests` : serveur → GitHub → poste, ou autre ? Et le poste doit-il rester
  disponible en repli **seulement avec votre accord** (comme aujourd'hui) ?
- **Q6** : N est-il réglable par vous dans le bureau, ou fixé à la valeur mesurée ?
