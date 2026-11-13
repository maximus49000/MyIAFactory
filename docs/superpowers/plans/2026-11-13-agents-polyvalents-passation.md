# Agents polyvalents — passation entre conversations

Le plan (`2026-11-13-agents-polyvalents.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite toutes les tâches de sa phase, sans s'arrêter, puis s'arrête et annonce la suivante. C'est l'utilisateur qui crée chaque conversation et choisit le modèle.

La conception (`docs/superpowers/specs/2026-11-13-agents-polyvalents-design.md`) est **validée par l'utilisateur** le 2026-11-13 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'essai restent **hors dépôt** (chemins donnés par l'utilisateur). Les sessions de phase vérifient par les tests et par des requêtes HTTP, pas par le panneau navigateur. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**, jamais de stash, reset ni changement de branche ; pousser à la fin de la phase.

**Dépenses** : seule la phase E appelle de vrais agents. Elle **attend l'accord explicite de l'utilisateur** avant le premier lancement, dit ce qu'elle va lancer et à peu près combien, et note le coût réel ici. Aucune phase n'installe de logiciel sur le poste.

## Où on en est

Tenir ce tableau à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Dépense réelle | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2, 3 : métier (brief enrichi), fiche polyvalente, leçons par métier | non | Formats et lecture au contrat écrit, tests nommés | à faire |
| B | Opus 5.5 | 4, 5, 6 : choix de l'agent et liens amont, modèle par tâche et Fable sur accord, départ par métier | non | Cœur du moteur : chemins de départ multiples, garde Fable, risque de régression | à faire |
| C | Sonnet 5.5 | 7, 8, 9 : équipe = places, création au nouveau format, reprise des projets | non (banc gratuit seulement) | Commandes et installation au contrat écrit | à faire |
| D | Sonnet 5.5 | 10 : bureau vivant (pièce de la tâche, panneaux, leçons par métier) | non | Page et relevé au contrat écrit | à faire |
| E | Opus 5.5 | 11 : essai réel sur ZooRunner, avec l'utilisateur | **oui** (quelques tâches réelles, sur accord) | Jugement de ce qui accroche en vrai | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. **Fable n'est utilisé dans aucune phase.** Ordre imposé : A avant B (B lit métiers et fiches polyvalentes) ; B avant C (la tâche 7 s'appuie sur le choix polyvalent, la 9 sur les leçons par métier) ; D après A (peut se faire avant ou après C) ; E en dernier.

## Ce que chaque phase doit vérifier avant de finir

- **A** : un projet à l'ancienne lit ses fiches et ses leçons exactement comme avant (`py -3.12 outils/tests.py orch fiches lecon depart`) ; un brief sans en-tête se lit ; une leçon à l'ancien id validée après la reprise va au métier.
- **B** : un projet non repris choisit les mêmes agents et les mêmes modèles qu'avant ; aucun chemin de départ (lot, `a_lancer`, retour, reprise après redémarrage, session cloud) ne lance une tâche dont l'amont attend une validation ; Fable ne part jamais sans décision acceptée ; `py -3.12 outils/tests.py` complet vert et `node --test` vert.
- **C** : monter ou baisser les places depuis Facturation ajoute ou retire des agents, jamais un agent au travail ; la reprise est rejouable sans effet ; le banc gratuit est vert ; aucun appel réel.
- **D** : un agent change de pièce avec sa tâche (`node --test`) ; la carte d'un polyvalent montre la tâche et son modèle ; les leçons s'affichent par métier.
- **E** : reprise lancée depuis le bureau sur ZooRunner ; compte rendu juste (leçons toutes présentes une fois, équipe = places) ; sur accord, quelques tâches réelles : un agent prend deux métiers, une tâche en aval d'une validation attend, pas de Fable sans décision. Coût noté ici.

## Messages à coller pour lancer chaque phase

**Phase A (Sonnet 5.5)** :
> Lis `docs/superpowers/plans/2026-11-13-agents-polyvalents-passation.md`, puis exécute la phase A du plan `docs/superpowers/plans/2026-11-13-agents-polyvalents.md` (tâches 1, 2, 3) d'une traite, avec superpowers:executing-plans. Mets à jour la passation, pousse, puis dis-moi la phase suivante.

**Phase B (Opus 5.5)** :
> Lis `docs/superpowers/plans/2026-11-13-agents-polyvalents-passation.md`, puis exécute la phase B (tâches 4, 5, 6) d'une traite, avec superpowers:executing-plans. Mets à jour la passation, pousse, puis dis-moi la phase suivante.

**Phase C (Sonnet 5.5)** :
> Lis `docs/superpowers/plans/2026-11-13-agents-polyvalents-passation.md`, puis exécute la phase C (tâches 7, 8, 9) d'une traite, avec superpowers:executing-plans. Aucun appel réel. Mets à jour la passation, pousse, puis dis-moi la phase suivante.

**Phase D (Sonnet 5.5)** :
> Lis `docs/superpowers/plans/2026-11-13-agents-polyvalents-passation.md`, puis exécute la phase D (tâche 10) d'une traite, avec superpowers:executing-plans. Mets à jour la passation, pousse, puis dis-moi la phase suivante.

**Phase E (Opus 5.5)** :
> Lis `docs/superpowers/plans/2026-11-13-agents-polyvalents-passation.md`, puis mène la phase E (tâche 11) avec moi sur ZooRunner (`C:\Users\maxim\EssaisMyIAFactory\ZooRunner`). Demande mon accord avant tout lancement réel d'agent.

## Notes laissées par les phases

(Écarts au plan, choix faits, points à surveiller.)
