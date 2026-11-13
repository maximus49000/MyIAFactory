# Agents polyvalents — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer « un agent par rôle » par N agents polyvalents (= les places de Facturation), qui prennent n'importe quelle tâche prête en spécialistes de son métier, avec leçons par métier et modèle par tâche.

**Architecture:** Le métier (`briefs/<role>.md`) devient l'unité de spécialité : consigne, service, modèle par défaut, lieu réservé, outils, leçons. La fiche d'agent ne garde que l'identité (clé, prénom, lieu, session). Le moteur choisit un agent libre au bon lieu sans regarder son rôle, après la vérification des liens amont ; le message de départ porte le métier de la tâche. Une reprise passe chaque projet ouvert au nouveau format.

**Tech Stack:** Python 3.12 (bibliothèque standard), JS sans dépendance (`node --test`), tests par `py -3.12 outils/tests.py <mots>`.

**Spec:** `docs/superpowers/specs/2026-11-13-agents-polyvalents-design.md` (validée le 2026-11-13).

## Global Constraints

- Python 3.12 bibliothèque standard seule ; page en JS sans dépendance.
- Jamais Fable sans accord du Directeur, accord **par tâche** ; sans accord, Opus.
- Aucune clé écrite ni affichée ; aucune dépense réelle sans accord ; rien installé sur le poste sans accord.
- La skill garde la mécanique, jamais la connaissance d'un projet ; les données d'essai restent hors du dépôt.
- Ancien format (fiche avec `Rôle`/`Modèle`/`## Leçons`) toujours lisible : un projet non repris marche comme avant.
- Tout ce qui se règle doit pouvoir se régler depuis le bureau.
- Ne committer que ses fichiers ; jamais de stash, reset, changement de branche.

## Review Focus

1. **Un projet non repris** (fiches à l'ancienne) doit se comporter exactement comme avant : mêmes agents choisis, mêmes modèles. → test de non-régression dans les tâches 4 et 5.
2. **Une tâche dont l'amont attend une validation du Directeur** ne doit partir par **aucun** chemin (lot, `a_lancer`, retour, reprise après redémarrage, session cloud) même avec des places libres. → un test par chemin, tâche 4.
3. **Baisser les places pendant qu'un agent travaille** : l'agent finit sa tâche, puis est retiré ; il ne reprend rien entre-temps. → tâche 7.
4. **Reprise rejouée deux fois** ou interrompue à mi-chemin : aucune leçon dupliquée ni perdue, aucun agent en trop. → tâche 9.
5. **Leçon « à valider » à l'ancien id** (`dev:L31`) validée après la reprise : elle s'écrit dans le métier `dev`, sans erreur. → tâche 3.

---

### Task 1: Le métier (brief enrichi)

**Files:**
- Create: `orchestrateur/metiers.py`
- Test: `tests/test_orch_metiers.py`

**Interfaces:**
- Produces: `lire_metier(dossier_briefs: Path, role: str) -> dict | None` → `{role, service, modele, lieu, specialite, outils, texte, lecons, chemin}` ; `lire_tous(dossier_briefs) -> dict[role, dict]` ; `ecrire_metier(metier: dict) -> None` ; `ajouter_lecon(metier, lecon: {id, etat, texte}) -> bool` (False si texte identique déjà présent) ; `MetierInvalide(Exception)`.
- En-tête du brief : lignes facultatives `Service : …`, `Modèle : Haiku|Sonnet|Opus`, `Lieu : local|cloud|indifférent`, `Spécialité : …`, `Outils : a, b` ; puis le texte ; puis `## Leçons` au format des fiches (`- [à valider|validée] <id> : texte`). Un brief sans en-tête (format actuel) se lit : tous ces champs à `None`, `lieu` = `"indifférent"`.

- [ ] Tests : `test_brief_actuel_sans_entete_se_lit`, `test_entete_complete_relue_a_l_identique` (écrire puis relire = même dict), `test_modele_fable_refuse_dans_un_brief` (`Modèle : Fable` → `MetierInvalide`), `test_ajouter_lecon_sans_doublon`, `test_lecons_a_valider_gardees`.
- [ ] Implémenter, tests verts, commit.

### Task 2: La fiche d'agent polyvalente

**Files:**
- Modify: `orchestrateur/fiches.py` (`lire_fiche` :44, `ecrire_fiche` :104)
- Test: `tests/test_orch_fiches.py`

**Interfaces:**
- Produces: une fiche sans ligne `Rôle` est **polyvalente** : `role=None`, `modele=None`, `service=None`, `lecons=[]` ; `est_polyvalente(fiche) -> bool` ; `nouvelle_fiche(cle, prenom, lieu, session=None) -> dict`.
- `lire_fiche` n'exige plus `Rôle` ni `Modèle` quand la fiche est polyvalente ; une fiche avec `Rôle` garde toutes les règles actuelles.

- [ ] Tests : `test_fiche_polyvalente_minimale` (Clé, Prénom, Lieu), `test_fiche_ancienne_inchangee`, `test_polyvalente_avec_modele_refusee` (une fiche polyvalente ne porte pas de modèle : refus lisible).
- [ ] Implémenter, `py -3.12 outils/tests.py fiches orch` vert, commit.

### Task 3: Leçons par métier

**Files:**
- Modify: `orchestrateur/outil.py` (`_noter_lecon` :2716, `_appliquer_verdicts` :2790), `orchestrateur/depart.py` (`_entete` :202, `_texte_fiche` :96)
- Test: `tests/test_orch_lecons_metier.py`

**Interfaces:**
- Consumes: `metiers.lire_metier`, `metiers.ajouter_lecon`, `fiches.est_polyvalente`.
- Produces: une leçon notée par un agent polyvalent a l'id `<role>:L<n>` où `role` est celui de la **tâche** ; validée, elle s'écrit dans `briefs/<role>.md`. Une leçon à l'ancien id `<agent>:L<n>` validée après la reprise s'écrit dans le métier du rôle de l'ancienne fiche (rôle noté sur la leçon dans `s["lecons"]` ; sinon le préfixe d'id si c'est un rôle connu). `_entete` met « ## Ton métier » (texte du brief, leçons validées du métier) au lieu de « ## Ta fiche » pour un agent polyvalent.

- [ ] Tests : `test_lecon_polyvalent_id_par_role`, `test_lecon_validee_ecrite_dans_le_metier`, `test_ancien_id_valide_apres_reprise_va_au_metier`, `test_message_porte_les_lecons_du_metier_de_la_tache` (deux tâches de métiers différents, même agent : lessons différentes), `test_fiche_ancienne_message_inchange`.
- [ ] Implémenter, `py -3.12 outils/tests.py orch lecon depart` vert, commit.

### Task 4: Choix de l'agent et liens amont

**Files:**
- Modify: `orchestrateur/depart.py` (`agent_libre` :25), `orchestrateur/modele_necessaire.py` (`possibles` :121), `orchestrateur/outil.py` (`_modele_et_lieu` :3115, `cmd_lots` :3137), `moteur/regles.py` (`_choisir_agent` :2392, `_demarrer_en_attente` :2282, `_repondre_cadrage` :1932, `_places` :2146)
- Test: `tests/test_moteur_polyvalents.py`

**Interfaces:**
- Consumes: `fiches.est_polyvalente`, `metiers.lire_metier` (champ `lieu`).
- Produces: `agent_libre(fiches, taches, role, modele, lieu, agents_locaux_max)` rend, pour un projet polyvalent, le premier agent polyvalent libre au lieu voulu, **sans filtre de rôle ni de plafond** ; lieu voulu = `local` si le métier dit `Lieu : local`, sinon local s'il reste une place locale, sinon cloud (un agent cloud sans session est sauté, comme aujourd'hui). Une tâche reprise (`a_lancer`, retour, session cloud) reprend son ancien agent s'il est libre.
- Produces: `regles._amont_pret(projet, etat, tache) -> bool` : vrai seulement si les étapes précédentes de l'élément sont faites, aucune décision `valider_etape` ni tâche `validation:*` ouverte en amont, et les barrières (`_barrieres`) levées. Appelé par **tous** les chemins de départ.

- [ ] Tests : `test_un_agent_prend_des_taches_de_metiers_differents`, `test_metier_local_attend_une_place_locale`, `test_cloud_quand_le_local_est_plein`, `test_reprise_revient_au_meme_agent_libre`, `test_amont_en_validation_bloque_<chemin>` pour `lot`, `a_lancer`, `retour`, `reprise_apres_redemarrage`, `session_cloud` (place libre, tâche ne part pas, barre `attente_validation` dite), `test_projet_non_repris_choisit_comme_avant`.
- [ ] Implémenter, `py -3.12 outils/tests.py moteur orch` vert, commit.

### Task 5: Modèle par tâche et Fable sur accord

**Files:**
- Modify: `orchestrateur/modele_necessaire.py` (`de_l_etape` :37, `de_la_tache` :67, `MODELES`), `orchestrateur/depart.py` (`monter`, `ECHELLE` :14), `moteur/regles.py` (`_modele_de_depart` :2437, `_modele_necessaire` :2430), `moteur/jugement.py` (:396, :423), `moteur/boucle.py` (:487), `installation/estimation.py` (Fable compté Opus)
- Test: `tests/test_moteur_modele_polyvalent.py`

**Interfaces:**
- Consumes: `metiers` (`modele` par défaut du métier).
- Produces: modèle de lancement d'un agent polyvalent = `de_la_tache` (étape, nature, montée) sinon modèle du métier sinon `Sonnet` ; **aucun plafonnement par fiche**. Une étape peut porter `modele: Fable` ; la montée va d'Opus à Fable. Dans ces deux cas, décision de projet `fable_tache` `{tache, raison}` posée **avant** le départ ; demande de réponse `fable_tache` `{decision, verdict: autoriser|refuser}` ; `autoriser` → la tâche part sur Fable, accord noté sur la tâche (`fable_accordee: true`) ; `refuser` → Opus. `_interdit` / `MODELES_INTERDITS` laissent passer Fable **seulement** pour une tâche `fable_accordee`.

- [ ] Tests : `test_modele_de_l_etape_sans_plafond`, `test_tache_sans_etape_prend_le_modele_du_metier`, `test_sans_metier_sonnet`, `test_etape_fable_pose_la_decision_et_attend`, `test_accord_fable_part_sur_fable`, `test_refus_fable_part_sur_opus`, `test_montee_opus_vers_fable_demande_l_accord`, `test_fable_jamais_sans_accord` (chaque chemin de départ), `test_estimation_compte_opus`.
- [ ] Ajouter `fable_tache` à `outil.TYPES_DEMANDE`, `bureau/demandes.py` (`decision`, `verdict`), et la carte de décision dans `bureau/web/ui/decisions.js` (« Autoriser Fable » / « Refuser : Opus ») avec un test `node`.
- [ ] Implémenter, `py -3.12 outils/tests.py moteur orch jugement estimation` et `node --test` verts, commit.

### Task 6: Le départ porte le métier

**Files:**
- Modify: `orchestrateur/outil.py` (`cmd_depart` :3071, `_depart_d_un_lot` :3035), `orchestrateur/depart.py` (`message` :272, `message_lot` :309), `moteur/boucle.py` (`_partir` :478, `_partir_cloud` :620)
- Test: `tests/test_orch_depart_polyvalent.py`

**Interfaces:**
- Consumes: Task 1, 3, 5.
- Produces: pour un agent polyvalent, le message prend brief, spécialité, outils et leçons du **métier de la tâche** (un brief par métier dans un lot, comme aujourd'hui). Un agent cloud garde **une** session pour tous les métiers (`sessions_cloud[cle]`).

- [ ] Tests : `test_message_specialiste_du_metier_de_la_tache`, `test_lot_multi_metiers_porte_chaque_brief`, `test_meme_session_cloud_pour_deux_metiers`.
- [ ] Implémenter, tests verts, commit.

### Task 7: L'équipe = les places

**Files:**
- Modify: `orchestrateur/outil.py` (`cmd_parallelisme` :2930, `cmd_recruter` :2977, `places_cloud_du_projet` :2923), `orchestrateur/recrutement.py`, `moteur/regles.py` (`_sur_parallelisme` :1882, `_sur_recruter` :1894), `bureau/web/ui/facturation.js` (:256-282, :327-516)
- Test: `tests/test_orch_equipe_places.py`, `bureau/web/tests/facturation.test.js`

**Interfaces:**
- Produces: pour un projet polyvalent, `parallelisme` crée ou retire des fiches polyvalentes pour que le nombre d'agents locaux et cloud soit égal aux places (prénom et couleur tirés, `bureau/equipe.py`) ; un agent au travail n'est jamais retiré : il porte `retrait_prevu` et n'est plus choisi, retiré à la fin de sa tâche. Bornes : locaux 1..16, cloud 0..16 ; valeurs effectives = `factory.agents_locaux_max` (2 par défaut) et `depart.places_cloud`. `recruter` refuse pour un projet polyvalent (« L'équipe suit les places de l'onglet Facturation. ») ; le bloc « Recruter » de Facturation est caché pour un projet polyvalent, le texte de la note dit « Chaque place est un agent polyvalent. »

- [ ] Tests : `test_monter_les_places_cree_des_agents`, `test_baisser_retire_un_agent_libre`, `test_agent_au_travail_retire_a_la_fin`, `test_retrait_prevu_jamais_choisi`, `test_recruter_refuse_si_polyvalent`, page : `bloc recruter caché si polyvalent`.
- [ ] Implémenter, tests verts, commit.

### Task 8: Création et installation au nouveau format

**Files:**
- Modify: `moteur/consignes/proposer_organisation.md`, `moteur/jugement.py` (validateur `proposer_organisation`, `definir_workflow`), `moteur/regles.py` (`_apres_proposer_organisation` :1065), `installation/proposition.py` (`verifier_organisation` :75, :153, :159), `installation/mise_en_place.py` (`ajouter_agent` :219, `ecrire_organisation` :244), `installation/definition.py` (`_organisation` :352), `skills/installer/SKILL.md` (:131-133), `bureau/web/ui/echange.js` (`lignesProposition` :134), `bureau/web/ui/organisation.js` (:45-63)
- Test: `tests/test_inst_polyvalents.py`, `bureau/web/tests/echange.test.js`

**Interfaces:**
- Produces: une organisation porte `metiers` (`[{role, service, modele, lieu, specialite, outils, brief}]`) et `agents` (`{locaux: n, cloud: m}`) ; `verifier_organisation` exige un métier par rôle du workflow ; la mise en place écrit `briefs/<role>.md` (Task 1) et `n + m` fiches polyvalentes, et règle les places à `n` et `m`. L'ancien format d'organisation reste accepté (projets créés avant). La fenêtre du chef montre les métiers et « N agents locaux, M agents cloud ».

- [ ] Tests : `test_organisation_polyvalente_verifiee`, `test_role_sans_metier_refuse`, `test_mise_en_place_ecrit_metiers_et_agents`, `test_ancienne_organisation_acceptee`, page : `lignesProposition montre les métiers et le nombre d'agents`.
- [ ] Banc gratuit (`py -3.12 outils/tests.py banc`) vert ; **aucun appel réel** dans cette tâche.
- [ ] Implémenter, commit.

### Task 9: La reprise d'un projet ouvert

**Files:**
- Create: `orchestrateur/reprise_polyvalents.py`
- Modify: `orchestrateur/outil.py` (commande `polyvalents`, type de demande `passer_polyvalent`), `moteur/regles.py` (`_sur_passer_polyvalent`), `bureau/demandes.py`, `bureau/web/ui/facturation.js` (bouton « Passer aux agents polyvalents » avec confirmation, visible tant que le projet n'est pas repris)
- Test: `tests/test_orch_reprise_polyvalents.py`

**Interfaces:**
- Produces: `reprendre(ctx) -> {"metiers": [...], "lecons_regroupees": n, "doublons": n, "agents_gardes": [...], "agents_retires": [...], "compte_rendu": str}`. Étapes : (1) un métier par rôle des fiches, brief créé s'il manque depuis le texte, spécialité et outils d'une fiche du rôle, `Modèle` = modèle de cette fiche, `Lieu : local` si toutes ses fiches étaient locales et déclarent `Outils` ; (2) leçons validées et « à valider » des fiches vers leur métier, doublons exacts fusionnés, ids gardés ; (3) fiches réécrites polyvalentes, en gardant d'abord celles qui ont une tâche en cours ou une session cloud, autant que les places effectives par lieu ; les autres retirées (au travail : `retrait_prevu`) ; (4) aucune tâche touchée ; compte rendu dans le journal du projet et en réponse de la demande. Idempotente.

- [ ] Tests : `test_reprise_zoo_like` (10 fiches → métiers + 5 agents pour 2 locaux + 3 cloud ; leçons toutes présentes une fois), `test_reprise_rejouee_sans_effet`, `test_reprise_interrompue_puis_rejouee`, `test_aucune_tache_touchee`, `test_agent_au_travail_garde`, `test_aucun_agent_cloud_au_dela_des_places`.
- [ ] Implémenter, tests verts, commit.

### Task 10: Le bureau vivant

**Files:**
- Modify: `orchestrateur/outil.py` (titulaires du relevé :2045-2065 : `service` = service de l'étape de la tâche en cours, sinon celui du métier, sinon `null` ; `metier` ajouté), `bureau/etat.py` (:128), `bureau/web/logique/regie.js` (:204, :217), `bureau/web/ui/dossier.js`, `ui/panneaux.js` (carte agent : « Tâche » et « Modèle de la tâche » au lieu de « Plafond » pour un polyvalent), `ui/directeur.js` (`contenuAgent`), `ui/connaissances.js` (leçons par métier)
- Test: `tests/test_releve_polyvalent.py`, `bureau/web/tests/regie.test.js`, `bureau/web/tests/panneaux.test.js`

**Interfaces:**
- Produces: un agent polyvalent au travail s'assoit dans la pièce du service de sa tâche, libre il va à la cafétéria ; les panneaux de service listent les agents dont la tâche en cours est du service ; les leçons d'un service s'affichent par métier.

- [ ] Tests : `test_titulaire_suit_le_service_de_sa_tache`, régie : `agent polyvalent change de pièce avec sa tâche`, panneaux : `carte d'un polyvalent sans plafond`.
- [ ] Implémenter, `node --test` et `py -3.12 outils/tests.py releve bureau` verts, commit.

### Task 11: Essai réel (avec l'utilisateur)

- [ ] Sur un projet d'essai **donné par l'utilisateur** (ZooRunner), lancer la reprise **depuis le bureau** ; vérifier le compte rendu, les métiers, les leçons, l'équipe = places.
- [ ] **Dépense** : avec l'accord explicite de l'utilisateur, laisser le moteur lancer quelques tâches : un même agent prend deux métiers ; une tâche en aval d'une validation attend ; aucune tâche sur Fable sans décision.
- [ ] Noter écarts et coûts dans la passation.
