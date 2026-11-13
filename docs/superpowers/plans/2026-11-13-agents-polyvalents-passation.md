# Agents polyvalents — passation entre conversations

Le plan (`2026-11-13-agents-polyvalents.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite toutes les tâches de sa phase, sans s'arrêter, puis s'arrête et annonce la suivante. C'est l'utilisateur qui crée chaque conversation et choisit le modèle.

La conception (`docs/superpowers/specs/2026-11-13-agents-polyvalents-design.md`) est **validée par l'utilisateur** le 2026-11-13 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'essai restent **hors dépôt** (chemins donnés par l'utilisateur). Les sessions de phase vérifient par les tests et par des requêtes HTTP, pas par le panneau navigateur. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**, jamais de stash, reset ni changement de branche ; pousser à la fin de la phase.

**Dépenses** : seule la phase E appelle de vrais agents. Elle **attend l'accord explicite de l'utilisateur** avant le premier lancement, dit ce qu'elle va lancer et à peu près combien, et note le coût réel ici. Aucune phase n'installe de logiciel sur le poste.

## Où on en est

Tenir ce tableau à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Dépense réelle | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2, 3 : métier (brief enrichi), fiche polyvalente, leçons par métier | non | Formats et lecture au contrat écrit, tests nommés | **faite 2026-11-13** |
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

**Phase A (2026-11-13, Sonnet 5.5)** — tâches 1, 2, 3 faites, sans appel réel.

- `orchestrateur/metiers.py` : `lire_metier`, `lire_tous`, `ecrire_metier`, `ajouter_lecon`, `MetierInvalide`. Le champ `chemin` du métier sert à `ecrire_metier` (un métier neuf se construit avec `chemin = briefs/<role>.md`). `Modèle : Fable` ou un lieu inconnu lèvent `MetierInvalide` à la lecture. `ecrire_metier` n'écrit `Lieu` que s'il n'est pas « indifférent » et ajoute toujours un `## Leçons` (un brief ancien relu puis réécrit en gagne un, sans autre changement).
- `orchestrateur/fiches.py` : `est_polyvalente(fiche)` (= pas de `role`), `nouvelle_fiche(cle, prenom, lieu, session=None)` (à compléter de `chemin` avant `ecrire_fiche`). Une fiche sans `Rôle` exige seulement `Clé` et `Lieu` ; elle refuse `Modèle`, `Service`, `Fable` et toute leçon (écart au plan : le plan ne citait que `Modèle`). Une fiche avec `Rôle` : règles inchangées. Les fiches polyvalentes ont `role/service/modele = None` : **les chemins du moteur qui lisent `fiche["role"]` ou `fiche["modele"]` n'ont pas encore été adaptés** (phases B et C) ; ne pas créer de fiche polyvalente dans un vrai projet avant la phase B.
- Leçons (`outil.py`) : pour un agent polyvalent, `lecon noter` exige `tache` (tâche existante avec un `role`, sinon refus lisible) ; l'id est `<role>:L<n>` ; la leçon porte `metier` dans `s["lecons"]` et est écrite « à valider » dans `briefs/<role>.md` (rien si le brief n'existe pas : la validation le crée). Au verdict : `valider` → « validée » dans le métier, `invalider` → retirée. `_metier_de_la_lecon` décide où va une leçon validée : `metier` de la leçon ; sinon fiche ancienne encore en place → la fiche (comportement d'avant) ; sinon (fiche reprise ou disparue) → `role` noté sur la leçon, puis préfixe d'id si `briefs/<préfixe>.md` existe, puis rôle de sa tâche. **Phase C (reprise)** : pour les leçons « à valider » regroupées, écrire `role` (ou `metier`) sur l'entrée de `s["lecons"]` ; `metier` fait aller la leçon au métier même si l'ancienne fiche existe encore.
- Message de départ (`depart.py`, `outil.py`) : `message` et `message_lot` prennent `metiers_=None` ; pour un agent polyvalent `cmd_depart` met « ## Ton métier : <role> » (service, spécialité, outils, leçons validées du métier) à la place de « ## Ta fiche », et « Le brief de ton rôle » prend le texte du brief **sans** en-tête ni leçons (pas de doublon). Les leçons genre/skill sont lues pour le rôle de la **tâche**. Un rôle sans brief donne un métier vide. Le lot est traité de la même façon (un bloc par métier) mais **la tâche 6 reste à faire** (session cloud, `message_lot` en multi-métiers testé de bout en bout). Un agent à fiche ancienne : message strictement inchangé (test `test_fiche_ancienne_message_inchange`).
- Tests ajoutés : `test_orch_metiers.py` (5), `test_orch_fiches.py` (4), `test_orch_lecons_metier.py` (6).
- Pour la phase B : `fiches.est_polyvalente` est le test à utiliser ; `metiers.lire_metier(...)["lieu"]` vaut `indifférent`/`local`/`cloud` et `["modele"]` le modèle par défaut du métier. `outil._metier_de(ctx, role)` rend toujours un dict de métier (vide si pas de brief).
