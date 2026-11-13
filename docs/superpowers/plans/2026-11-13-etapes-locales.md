# Étapes locales et étapes découpées — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** chaque étape du workflow dit si elle exige le poste (agent local) ; une étape mixte est découpée en « code »
(cloud possible) puis « mise en place et tests » (poste local) ; ZooRunner est découpé maintenant, sur décision du Directeur.

**Spec:** `docs/superpowers/specs/2026-11-13-etapes-locales-design.md` (validée le 2026-11-13).

**Tech Stack:** Python 3.12 bibliothèque standard ; JS sans dépendance (`node --test`) ; `py -3.12 outils/tests.py <mots>`.

## Global Constraints

- Un projet sans `lieu` sur ses étapes marche exactement comme aujourd'hui (repli sur `Lieu :` du métier).
- Aucune tâche touchée par un découpage ; une étape existante garde id, ordre, rôle, service, nature.
- Seule dépense : l'appel `decouper_lieux` (Sonnet) et la production qui suit, sur accord du Directeur (phase C).
- La skill garde la mécanique ; tout se règle depuis le bureau ; jamais Fable sans accord.

## Phases

| Phase | Modèle | Tâches |
|---|---|---|
| A | Opus 5.5 | 1, 2, 3 (moteur, données, jugement) |
| B | Sonnet 5.5 | 4 (bureau) |
| C | Opus 5.5 | 5 (essai réel sur ZooRunner, avec le Directeur) |

### Task 1 : le lieu d'une étape et le choix de l'agent

**Files:** `orchestrateur/factory.py` et `orchestrateur/workflows.py` (champ `lieu` ∈ {`local`, `indifférent`} sur une étape
de flux, refusé sur une validation), `moteur/jugement.py` (validateurs `definir_workflow`, `proposer_organisation`
acceptent `lieu`), `orchestrateur/depart.py` (`agent_libre`), `moteur/regles.py` (`_choisir_agent`, `_demarrer_en_attente`
: lieu de l'étape d'abord, repli sur le métier ; une tâche locale sans place locale libre est dite dans `attente_charge` :
« attend le poste local »), `orchestrateur/modele_necessaire.py` si besoin (`etape_de_la_tache`).
**Tests:** `tests/test_moteur_etapes_locales.py` : `test_etape_locale_attend_le_poste`, `test_etape_indifferente_part_dans_le_cloud_meme_si_metier_local`,
`test_sans_lieu_repli_sur_le_metier`, `test_validation_refuse_un_lieu`, `test_attente_dit_le_poste_local`, non-régression projet sans `lieu`.

### Task 2 : découper un workflow

**Files:** `orchestrateur/lieux.py` (nouveau) : `verifier_proposition(flux, propose) -> str | None` (validation stricte de
la conception), `appliquer(flux, propose) -> flux` (par id ; jamais redécouper une étape qui a sa sœur `<id>-local`),
`etapes_locales_suggerees(flux, environnement) -> set(ids)` (outils `pour` / `objectif`) ; `orchestrateur/outil.py` :
commande `lieux` (`{action: "decouper", flux}` appliqué à tous les workflows du projet ; `{action: "regler", etape, lieu}`
pour une étape, dans tous les workflows qui l'ont).
**Tests:** `tests/test_orch_lieux.py` : proposition qui supprime / renomme / réordonne une étape refusée ; insertion de
`<id>-local` après `<id>` acceptée ; appliquer deux fois = une fois ; copies `w-<fid>` découpées par id ; aucune tâche touchée.

### Task 3 : le jugement et la décision

**Files:** `moteur/consignes/decouper_lieux.md` (nouveau), `moteur/jugement.py` (type `decouper_lieux`, Sonnet, validateur
qui appelle `lieux.verifier_proposition`), `moteur/regles.py` (demande `proposer_decoupage` → jugement → décision de projet
`decoupage_lieux` avec avant/après ; demande `decoupage_lieux` `{decision, verdict: valider|refuser}` → `lancer lieux` ;
demande `lieu_etape` `{etape, lieu}` → `lancer lieux regler`), consignes `definir_workflow.md` et `proposer_organisation.md`
(rendre `lieu` et découper d'après les outils), `orchestrateur/outil.py` (`TYPES_DEMANDE`), `bureau/demandes.py`,
`bureau/releve.py` (décision `decoupage_lieux`, `lieu` des étapes au relevé). Consigne de la partie locale : récupérer le
code, compiler, tester au premier plan, capturer, rendre ce que la validation attend, ne pas réécrire le code.
**Tests:** jugement redemandé une fois puis pas de décision si invalide ; valider applique, refuser ne change rien ;
`lieu_etape` immédiat ; banc gratuit vert ; **aucun appel réel**.

### Task 4 : le bureau

**Files:** `bureau/web/ui/decisions.js` (carte « Découper les étapes selon le poste » : avant/après, « poste local » /
« cloud possible », Valider / Refuser), `bureau/web/ui/facturation.js` (liste « Étapes et lieux » : sélecteur local /
cloud possible par étape de flux, bouton « Proposer le découpage »), `bureau/web/ui/detail.js` (« Sur le poste local »
pour une tâche dont l'étape l'exige), `bureau/etat.py` (étapes et lieux servis).
**Tests:** `node --test` : carte, sélecteur (pas pour une validation), mention sur la fiche.

### Task 5 : essai réel (avec le Directeur)

- [ ] Sur accord : « Proposer le découpage » sur ZooRunner ; relire la proposition ; le Directeur valide au bureau.
- [ ] Vérifier : prototype, contenu, build… locaux ou découpés ; une partie code part dans le cloud, sa partie locale
  attend le poste ; coûts notés.

### Task 6 : équiper les sessions cloud et choisir à l'initialisation (ajout du Directeur)

- Décision « Équiper les sessions cloud » : le moteur propose d'ajouter au projet `.claude/settings.json` (hook
  `SessionStart`) et `.claude/cloud/installation.sh` généré depuis l'environnement (commandes Linux des outils) ; sur
  « Valider », il les écrit, commite et pousse ; un essai cloud vérifie chaque outil et marque `cloud: true`.
- `definir_workflow` rend, par étape, si elle est exécutable dans le cloud ; la création (`bureau/web/ui/echange.js`,
  `installation/creation.py`) propose l'écran « Où s'exécutent les étapes » quand le projet a des agents cloud.
- Tests : décision posée et appliquée, script généré sans clé ni donnée de projet, écran de création (`node --test`).
