# MyIAFactory

Une skill Claude qui montre une « factory » d'agents IA comme un bureau d'entreprise de jeu vidéo : un open space en 3D isométrique, un bureau par service (Métier, Dev, QA, Intégration, Facturation…), des agents à prénom qui travaillent, vont au café quand ils sont libres, et viennent déplacer leur post-it sur le Kanban central.

Ce dépôt contient la skill **vide de tout projet**. Un projet qui veut son bureau le branche depuis son propre dépôt.

## Comment ça marche

```
le projet ──(relevé : qui tient quelle tâche, dans quelle colonne)──► serveur local du bureau
                                                                        │ ajoute prénoms, statuts, charge de l'ordinateur
                                                                        ▼
                                                              page 3D dans le navigateur
```

- Le projet fournit un **relevé** : un petit document JSON qui dit les faits bruts.
- Le **serveur local** (Python, sans rien à installer) en déduit qui travaille, qui est sans nouvelles, qui est libre, et mesure la charge de l'ordinateur.
- La **page** compare les états successifs et joue les déplacements. Rien n'est simulé.

![Le bureau vivant, avec l'exemple de démonstration](docs/img/bureau.jpg)

## Avancement

Projet 1, le bureau vivant :

- [x] 1. Socle et réglages
- [x] 2. Le relevé (contrat entre un projet et le bureau) et l'exemple de démonstration
- [x] 3. Statuts : fraîcheur, pause, départ
- [x] 4. L'équipe : prénoms et couleurs
- [x] 5. L'état servi à la page
- [x] 6. La charge de l'ordinateur et le serveur
- [x] 7. La logique de la page : changements, plan, régie
- [x] 8. La scène 3D en volumes simples
- [x] 9. L'interface : voyant, barre de charge, cartes, panneaux
- [x] 10. Le mode d'emploi
- [x] 11. Le mobilier (modèles Tripo)
- [x] 12. Le personnage (modèle Tripo)

Projet 1 bis, le bureau qui agit ([plan](docs/superpowers/plans/2026-11-10-bureau-qui-agit.md)) :

- [x] 1. Le relevé version 2
- [x] 2. L'état version 2
- [x] 3. Les demandes (du bureau au projet)
- [x] 4. Les images
- [x] 5. Les boutons de la factory et l'envoi des demandes
- [x] 6. Le panneau d'une tâche, la file, la vue liste
- [x] 7. Le Directeur et les leçons
- [x] 8. La démo qui agit, la documentation

Projet 2, les dossiers des services ([plan](docs/superpowers/plans/2026-11-10-dossiers-des-services.md), [passation](docs/superpowers/plans/2026-11-10-dossiers-des-services-passation.md)) :

- [x] 1. Le relevé version 3 et l'usage
- [ ] 2. L'historique des usages
- [ ] 3. Les prix, mise à jour automatique
- [ ] 4. Le calcul des coûts
- [ ] 5. Le serveur sert la facturation
- [ ] 6. Le dossier, l'onglet Tâches et l'onglet Facturation
- [ ] 7. Le relevé et l'état pour les connaissances
- [ ] 8. Les trois demandes
- [ ] 9. L'onglet Connaissances et le volet « Challenger »
- [ ] 10. Les KPI, les alertes, « problème revenu »
- [ ] 11. L'onglet KPI
- [ ] 12. La démo, la documentation, la relecture

État : le bureau vivant est terminé (les douze étapes et la relecture finale), et le bureau agit : il transmet à un projet les gestes de l'utilisateur et montre le détail des tâches (voir « Faire agir le bureau » dans [docs/installation.md](docs/installation.md)). Prochaine étape : brancher un premier projet réel, depuis le dépôt de ce projet.

Essayer la démo : `py -3.12 lancer.py serveur --reglages exemples/demo/reglages.json`, puis ouvrir `http://127.0.0.1:8770/`. Les gestes de la démo (Pause, déplacer, retour, verdict) réécrivent son `releve.json` : pour les essayer sans modifier le dépôt, copiez d'abord `exemples/demo/` ailleurs et lancez le bureau sur la copie.

## Ce qu'il reste à faire ensuite

- **Projet 2, les dossiers des services** : tâches d'un agent, facturation en tokens jusqu'à la micro-tâche, cas de test, cahiers des charges, décisions du Directeur.
- **Projet 3, le parcours d'une tâche** : création depuis le bureau, cahier des charges, micro-tâches, boucle QA, choix de l'agent et du modèle.
- **Projet 4, l'installation sur un projet** : scan, proposition de services, calibrage sur la machine, renfort cloud, emballage en skill.

## Documents

- Conception : [docs/superpowers/specs/2026-11-10-bureau-vivant-design.md](docs/superpowers/specs/2026-11-10-bureau-vivant-design.md) ; le bureau qui agit : [docs/superpowers/specs/2026-11-10-bureau-qui-agit-design.md](docs/superpowers/specs/2026-11-10-bureau-qui-agit-design.md)
- Plan de réalisation : [docs/superpowers/plans/2026-11-10-bureau-vivant.md](docs/superpowers/plans/2026-11-10-bureau-vivant.md)
- Passation entre conversations (phases et modèles) : [docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md](docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md)
- Manuel d'installation et de configuration : [docs/installation.md](docs/installation.md)
- Format du relevé : [docs/releve.md](docs/releve.md)
