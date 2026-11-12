# MyIAFactory

Une skill Claude qui montre une « factory » d'agents IA comme un **bureau d'entreprise de jeu vidéo** : un open space en 3D isométrique, un bureau par service (Métier, Dev, QA, Intégration, Facturation…), des agents à prénom qui travaillent, vont au café quand ils sont libres, et viennent déplacer leur post-it sur le Kanban central.

Elle s'adresse à qui fait travailler une équipe d'agents IA sur un projet (logiciel, jeu, site, contenu…) et veut **voir ce qui se passe, décider aux bons moments et maîtriser le coût**. Le projet fournit un **relevé** (qui tient quelle tâche, dans quelle colonne) ; un serveur local, en Python sans rien à installer, en déduit qui travaille, qui est sans nouvelles, qui est libre, et la page 3D joue les déplacements. Rien n'est simulé. Ce dépôt contient la skill **vide de tout projet** : un projet qui veut son bureau l'installe depuis son propre dépôt.

![Le bureau vivant, avec l'exemple de démonstration](docs/img/bureau.jpg)

## Comment l'installer

Prérequis : Python 3.12 (`py -3.12`) et un navigateur récent ; Windows pour la mesure de charge (ailleurs, le bureau marche sans elle). Aucun paquet à installer.

Le plugin s'ajoute une fois par machine, dans une conversation Claude Code :

```
/plugin marketplace add maximus49000/MyIAFactory
/plugin install myiafactory@myiafactory
```

Puis, dans une conversation Claude Code ouverte dans le dossier d'un projet :

```
/myiafactory:installer
```

La commande comprend le projet (vide ou existant), propose une organisation chiffrée et configure tout après votre validation. Le bureau commun se lance ensuite avec `py -3.12 "$HOME/MyIAFactory/skill/lancer.py" serveur --bureau "$HOME/MyIAFactory/bureau.json"` (adresse `http://127.0.0.1:8770/`), et s'ouvre au téléphone par Tailscale ou le Wi-Fi, avec un QR code. Un nouveau projet peut aussi se créer depuis le bureau (« Nouveau projet… »).

Pour essayer la démo sans rien brancher : `py -3.12 lancer.py serveur --bureau exemples/bureau.json` (copiez d'abord `exemples/` ailleurs : les gestes de la démo réécrivent ses fichiers). Le détail (réglages, plusieurs projets, prix, téléphone, partenaires, dépannage) est dans [docs/installation.md](docs/installation.md) ; passer à la main un projet qui a déjà sa factory : [docs/orchestrateur.md](docs/orchestrateur.md).

## Fonctionnalités

- **Bureau vivant en 3D** : un bureau par service, des agents à prénom qui travaillent, vont au café, déplacent leur post-it sur le Kanban ; voyant de la factory et barre de charge de l'ordinateur.
- **Un bureau qui agit** : pause, déplacement de tâches, retours, détail d'une tâche avec journal et images ; le bureau dépose des demandes, c'est le projet qui agit.
- **Dossiers des services, facturation et KPI** : tâches, connaissances partagées entre agents, KPI et alertes, coût estimé en euros d'après les tokens et les prix du jour, geste « Challenger » du problème à la connaissance validée.
- **Plusieurs projets dans un même bureau**, avec un sélecteur et la pastille de ce qui attend l'utilisateur.
- **Parcours d'une fonctionnalité** : « + Nouvelle fonctionnalité », discussion de cadrage avec questions à boutons et images, cahier des charges, découpage, prototype, méthode, série, coût et documents de la fonctionnalité.
- **Catalogue d'une fonctionnalité** : vue de haut, fiches, comparaison « Produit » / « Réel », demandes de modification.
- **Le Directeur** : décisions, leçons, cahiers et méthodes à valider, sessions à créer.
- **Moteur procédural et banc** : `py -3.12 -m moteur` applique les consignes de l'orchestrateur sans conversation orchestratrice et ne fait appel à l'IA que pour juger ; un banc rejoue un scénario pour mesurer le coût et régler les consignes.
- **Un genre et un workflow par fonctionnalité** : chaque demande est classée par genre et jugée cohérente ou non avec la description du projet ; elle reprend le workflow du genre du projet, ou reçoit un workflow dédié proposé ; description de genre proposée d'avance et élargie avec l'accord du Directeur.
- **Création d'un projet avec le chef** : depuis le bureau, en deux fenêtres (informations, puis échange de quelques tours), avec brouillons à reprendre et coût affiché ; le projet naît avec son workflow, ses services, ses agents et son genre.
- **Validations du Directeur** : des étapes du workflow où l'élément attend « Valider » ou « Renvoyer avec une remarque ».
- **Outils du poste** : vérification des versions, objectif, lien officiel et mode opératoire de chaque outil manquant, installation en autonomie uniquement sur clic.
- **Jauges d'abonnement Claude** : deux jauges (fenêtre de 5 h, semaine) dans la barre du haut, et à côté de chaque coût en euros la part estimée de l'abonnement (≈ x % semaine), étalonnée sur les appels réels.
- **Empreinte carbone estimée** : à côté de chaque coût en euros (onglet Facturation par ligne et en total, panneau de chaque fonctionnalité, échange de création, workflows proposés), une fourchette en gCO₂e (≈ a à b g CO₂e) calculée avec la méthode EcoLogits sur les tokens de sortie.
- **Partenaires** : catalogue de services extérieurs (voix, images, 3D, recherche…), connexions, quotas, règles d'usage et coûts, tous facultatifs.
- **Mémoire à trois étages et leçons** : ce qui est appris se garde au niveau du projet, du genre ou de la skill, après validation de l'utilisateur.
- **Lots par modèle et choix du modèle** : un modèle fait d'une traite ce qu'il peut enchaîner ; la montée de modèle se décide, Fable seulement sur accord.
- **Bureau au téléphone** : accès privé par Tailscale ou Wi-Fi, code d'accès, vue 3D adaptée.
- **Installation guidée** : le plugin et la commande `/myiafactory:installer`, organisation chiffrée, réparation d'une installation existante.

![Le dossier d'un service : alerte, KPI, connaissances, facturation](docs/img/dossier.jpg)

![Une fonctionnalité : le bandeau du parcours, la discussion de cadrage, le cahier des charges](docs/img/fonctionnalite.jpg)

![Le catalogue d'une fonctionnalité : la fiche d'un élément et sa comparaison « Produit » / « Réel »](docs/img/catalogue.jpg)

## Objectifs

- Voir et piloter une équipe d'agents comme un bureau : qui fait quoi, où en est chaque élément, ce qui attend l'utilisateur.
- Garder le **coût maîtrisé et visible** : estimation en euros, modèle le plus économe qui tienne, aucun appel d'IA là où le code suffit.
- Laisser l'utilisateur décider **aux bons moments** (cahier, méthode, validations, leçons, dépenses), jamais à sa place.
- Que la skill porte la **mécanique** et jamais la connaissance d'un projet précis : tout ce qui est propre à un projet vit dans le projet.
- Une installation simple sur un projet vide comme sur un projet existant.

Non-objectifs : héberger quoi que ce soit sur Internet, remplacer le projet (le bureau regarde et transmet des demandes), simuler une activité qui n'a pas lieu.

## Documents

- Où en est la réalisation : [docs/avancement.md](docs/avancement.md)
- Conception : [docs/superpowers/specs/2026-11-10-bureau-vivant-design.md](docs/superpowers/specs/2026-11-10-bureau-vivant-design.md) ; le bureau qui agit : [docs/superpowers/specs/2026-11-10-bureau-qui-agit-design.md](docs/superpowers/specs/2026-11-10-bureau-qui-agit-design.md) ; les dossiers des services : [docs/superpowers/specs/2026-11-10-dossiers-des-services-design.md](docs/superpowers/specs/2026-11-10-dossiers-des-services-design.md) ; le parcours d'une tâche : [docs/superpowers/specs/2026-11-10-parcours-d-une-tache-design.md](docs/superpowers/specs/2026-11-10-parcours-d-une-tache-design.md)
- Plan de réalisation : [docs/superpowers/plans/2026-11-10-bureau-vivant.md](docs/superpowers/plans/2026-11-10-bureau-vivant.md)
- L'installation sur un projet : [conception](docs/superpowers/specs/2026-11-11-installation-sur-un-projet-design.md), [plan](docs/superpowers/plans/2026-11-11-installation-sur-un-projet.md), [passation](docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md)
- L'orchestrateur procédural : [conception](docs/superpowers/specs/2026-11-11-orchestrateur-procedural-design.md), [plan](docs/superpowers/plans/2026-11-11-orchestrateur-procedural.md), [passation](docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md)
- Un genre et un workflow par fonctionnalité : [conception](docs/superpowers/specs/2026-11-11-genre-par-fonctionnalite-design.md), [plan](docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite.md), [passation](docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md)
- Le workflow défini dès la création, outils à installer compris : [conception](docs/superpowers/specs/2026-11-12-workflow-des-la-creation-design.md), [plan](docs/superpowers/plans/2026-11-12-workflow-des-la-creation.md), [passation](docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md)
- Plan du parcours d'une tâche : [docs/superpowers/plans/2026-11-10-parcours-d-une-tache.md](docs/superpowers/plans/2026-11-10-parcours-d-une-tache.md), sa passation : [docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md](docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md)
- Passation entre conversations (phases et modèles) : [docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md](docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md)
- Manuel d'installation et de configuration : [docs/installation.md](docs/installation.md)
- Format du relevé : [docs/releve.md](docs/releve.md)
- L'orchestrateur générique : [orchestrateur/consignes.md](orchestrateur/consignes.md), [orchestrateur/interface.md](orchestrateur/interface.md), et le guide de passage d'un projet [docs/orchestrateur.md](docs/orchestrateur.md)
