# « Nouvelle correction » et « Une question » — passation

Date : 2026-11-16. Arrêt demandé par le Directeur au milieu de la tâche 6 ; à reprendre dans une autre discussion.

- Conception : [../specs/2026-11-16-correction-et-question-design.md](../specs/2026-11-16-correction-et-question-design.md)
- Plan : [2026-11-16-correction-et-question.md](2026-11-16-correction-et-question.md)
- Branche : `correction-et-question` (partie de `main` à `cf97f6d`), dans le worktree
  `~/.claude/plugins/marketplaces/myiafactory-correction-question`. Rien n'est encore fusionné dans `main`.
- Méthode : superpowers:subagent-driven-development (un implémenteur par tâche, une relecture par tâche, une revue
  finale de la branche).

## Où on en est

| Tâche | État | Commits |
|---|---|---|
| 1. Stockage des questions | faite, relue | `9268389` |
| 2. Demandes du bureau (nature, concerne, question) | faite, relue | `94d0cbe` |
| 3. Workflow de correction | faite, relue (1 ronde) | `dfac989`, `8b325c5`, puis `fc37912` (livraison) |
| 4. Parcours d'une correction dans le moteur | faite, relue (1 ronde) | `d9ea11a`, `0bab6e8` |
| 5. Jugement `repondre_question` | faite, relue | `3274235` |
| 6. Agent lecteur | **ronde de correction 1 interrompue** | `96c12c5` + commit « en cours » (voir plus bas) |
| 7. Boutons et mode correction du bureau | à faire | — |
| 8. Panneau « Questions » | à faire | — |
| 9. Documentation, essai sur la démo, poussée | à faire | — |

### Tâche 6 : la ronde interrompue

La relecture de `96c12c5` a demandé :

1. **(Important)** `moteur/boucle.py` (~ligne 625) : le lecteur est appelé avec `couche=projet.couche` ; en couche
   `api`, `appel.appeler` ignore `outils` et `dossier_travail` : le lecteur répond sans lire le code et la réponse est
   marquée « code ». Forcer `couche="claude"` (comme `agents.py:93`) et le vérifier dans le test de boucle.
2. **(Important)** Double « Chercher dans le code » : `bureau/demandes.py` (~464) accepte `question_approfondir`
   pendant `en_lecture` → deux lecteurs, deux réponses, double facturation. Refuser avec « Je cherche déjà dans le
   code. », même garde dans `regles._sur_question_approfondir` ; un test chacun.
3. `premiere_reponse` (`regles.py` ~507) : prendre le premier message de la factory `niveau == "documents"` après la
   dernière question, pas le dernier message (qui peut être « Lecture interrompue »).
4. Une lecture ratée (`LECTURE_RATEE`) est écrite en niveau `code`, ce qui empêche de relancer : l'écrire en
   `documents` (sur false) ; tester qu'une relance est acceptée après un échec.
5. `banc/jouer.py` (~152) : compter `etape == "questions"` comme l'orchestration (pas la production).

L'implémenteur a été arrêté en cours de route : ses modifications non terminées (`banc/jouer.py`,
`bureau/demandes.py`, `moteur/boucle.py`, `moteur/regles.py`, `tests/test_demandes.py`,
`tests/test_moteur_boucle.py`, `tests/test_questions.py`) sont gardées dans un commit « en cours » de la branche.
**Elles ne sont ni terminées ni testées** : à relire et compléter avant la relecture ciblée de la ronde 1.

## Décisions prises en cours de route (à connaître)

- Un projet de correction prend le `service` de chaque rôle dans les étapes d'agent déjà connues du projet
  (`workflows.service_du_role`) ; un rôle sans étape connue → le moteur demande au Directeur « quel métier corrige ? ».
- **Une validation du Directeur n'est jamais la dernière étape** (règle du projet) : le workflow de correction est
  correctif → vérification (si rôle QA) → validation → **livraison** (`<fid>-livraison`, rôle de production). Écart
  volontaire à la conception, qui mettait la validation en dernier.
- Si le rôle QA n'a pas d'agent, la correction part sans vérification et le dit dans sa discussion.
- La fiche de correction est rangée comme `cahier` (maquette vide, étapes = symptôme, reproduction, attendu, piste) ;
  pas de `methode` ; un seul élément `correction` passe en série. Les agents du flux reçoivent la fiche et la section
  de `orchestrateur/consignes-correction.md` de leur étape. Trop de tours sur une correction : l'élément est bloqué
  (pas de « revoir la méthode »).
- Les jugements `repondre_question` et le lecteur sont facturés sous l'étape `questions` (ligne « dont questions »
  dans la facturation : `bureau/cout.py`, `bureau/sujets.py`, `bureau/web/ui/facturation.js`).
- Le lecteur tourne dans un fil de la boucle ; les écritures se font au passage suivant (file `queue`) ; un fil ne
  reste jamais `en_lecture` (échec → message de la factory, fil `repondue`) ; au redémarrage, `lecture_interrompue`.
- **Pour les tâches 7-8** : la fonction qui ouvre le formulaire prérempli s'appelle `ouvrirNouvelle(nature, texte,
  concerne)` (exposée par `panneaux.js`) ; `ctx.nouvelle` reste l'objet `{envoi, nature, brouillon}`. Le plan
  réutilisait le nom pour deux choses.
- Aides de test réelles : `self.ok("<commande>", entree=…)` sur `tests.test_moteur_regles.Base`, refus par
  `self.outil(...)` (code 1, `objet["erreur"]`).

## Remarques mineures gardées pour la revue finale

- T1 : `questions.lire` n'attrape que `OSError` ; `images` non validées ; ids en double ; tests manquants (41
  messages, plafond 50 au relevé, `niveau` refusé, `suggestion`/`fichiers_lus`, lister/ajouter/marquer par la
  commande) ; import dans le corps d'un test ; `ETATS_QUESTION` coupe le bloc anomalies de `bureau/releve.py`.
- T2 : `fil` non typé (liste → TypeError) ; messages vides → IndexError ; `fichiers` accepté pour une question mais
  ignoré ; `fil` vide ouvre un fil neuf ; tuple des natures dupliqué.
- T3 : `role_qa == role_production` non refusé ; `TestDeCorrection` après le bloc `__main__`.
- T4 : genre = celui du projet (pas celui de la fonctionnalité concernée) ; partenaires non proposés au cadrage de
  correction ; lecture de la consigne sans garde `OSError` ; fichiers partiels possibles si l'écriture échoue avec QA
  puis réussit sans.
- T5 : dossier de la question non borné (règles, cahier, texte) ; `mots_interdits` non contrôlés ; `_fil` →
  `StopIteration` sur un fil inconnu.
- T6 : la branche threadée n'est testée qu'en mode synchrone.

## Tests

- Base de référence (suite complète à `cf97f6d`, 2504 tests, ~41 min) : **10 échecs préexistants** —
  `test_banc_scenario…test_vrais_agents_a_la_place_du_rejoueur`, `test_inst_creation` (2),
  `test_inst_examen.test_gros_dossier`, `test_inst_mise_en_place.test_appliquer_projet_vide`,
  `test_moteur_rapport.Consigne` (3), `test_orch_transcriptions.test_le_reveil_note_la_gestion`,
  `test_sans_fenetre.test_chaque_commande_lancee_masque_sa_fenetre`.
- Après la tâche 4 : `test_moteur_correction` + `test_orch_workflows` (39) et `test_moteur_parcours` +
  `test_moteur_regles` (214) passent. Après la tâche 6 (`96c12c5`) : `test_questions`, `test_moteur_boucle`,
  `test_moteur_priorite`, `test_moteur_reveil` (92) et les tests de coût passent.

## Pour reprendre

1. Ouvrir le worktree (ou `git switch correction-et-question` dans un clone), relire le commit « en cours » de la
   tâche 6, finir les 5 points ci-dessus, lancer `tests.test_questions`, `tests.test_moteur_boucle`,
   `tests.test_demandes`, puis faire la relecture ciblée de la ronde 1.
2. Tâches 7, 8, 9 du plan (avec la décision `ouvrirNouvelle`).
3. Revue finale de toute la branche (`git merge-base main HEAD`..HEAD), en lui donnant la liste des remarques mineures
   ci-dessus ; suite complète comparée aux 10 échecs préexistants.
4. Fusion dans `main` et `git push origin main` (règle du dépôt : toute correction est poussée).
