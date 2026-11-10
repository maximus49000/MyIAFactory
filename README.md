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

## Avancement

Projet 1, le bureau vivant :

- [x] 1. Socle et réglages
- [x] 2. Le relevé (contrat entre un projet et le bureau) et l'exemple de démonstration
- [x] 3. Statuts : fraîcheur, pause, départ
- [ ] 4. L'équipe : prénoms et couleurs
- [ ] 5. L'état servi à la page
- [ ] 6. La charge de l'ordinateur et le serveur
- [ ] 7. La logique de la page : changements, plan, régie
- [ ] 8. La scène 3D en volumes simples
- [ ] 9. L'interface : voyant, barre de charge, cartes, panneaux
- [ ] 10. Le mode d'emploi
- [ ] 11. Le mobilier (modèles Tripo)
- [ ] 12. Le personnage (modèle Tripo)

État : étapes 1 à 3 faites.

## Ce qu'il reste à faire ensuite

- **Projet 2, les dossiers des services** : tâches d'un agent, facturation en tokens jusqu'à la micro-tâche, cas de test, cahiers des charges, décisions du Directeur.
- **Projet 3, le parcours d'une tâche** : création depuis le bureau, cahier des charges, micro-tâches, boucle QA, choix de l'agent et du modèle.
- **Projet 4, l'installation sur un projet** : scan, proposition de services, calibrage sur la machine, renfort cloud, emballage en skill.

## Documents

- Conception : [docs/superpowers/specs/2026-11-10-bureau-vivant-design.md](docs/superpowers/specs/2026-11-10-bureau-vivant-design.md)
- Plan de réalisation : [docs/superpowers/plans/2026-11-10-bureau-vivant.md](docs/superpowers/plans/2026-11-10-bureau-vivant.md)
- Passation entre conversations (phases et modèles) : [docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md](docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md)
- Manuel d'installation et de configuration : `docs/installation.md` (à venir, étape 10)
- Format du relevé : [docs/releve.md](docs/releve.md)
