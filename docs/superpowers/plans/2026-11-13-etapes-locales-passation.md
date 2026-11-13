# Étapes locales et étapes découpées — passation entre conversations

Le plan (`2026-11-13-etapes-locales.md`) est réalisé en phases, chacune dans sa propre conversation, avec le modèle
indiqué. La conception (`docs/superpowers/specs/2026-11-13-etapes-locales-design.md`) est validée par le Directeur le
2026-11-13. Toutes les phases se font dans ce dépôt ; ne committer que ses propres fichiers, jamais de stash, reset ni
changement de branche ; pousser à la fin de la phase. Aucune donnée de projet réel n'est touchée avant la phase C.

## Où on en est

| Phase | Modèle | Tâches du plan | Dépense réelle | État |
|---|---|---|---|---|
| A | Opus 5.5 | 1, 2, 3 : lieu d'une étape et choix de l'agent, découper un workflow, jugement et décision | non (banc gratuit) | **faite 2026-11-13** |
| B | Sonnet 5.5 | 4 : le bureau (carte de décision, « Étapes et lieux », « Sur le poste local ») | non | à faire |
| C | Opus 5.5 | 5 : essai réel sur ZooRunner, avec le Directeur | **oui** (un appel `decouper_lieux` Sonnet, puis la production), sur accord | à faire |

## Notes laissées par les phases

**Phase A (2026-11-13, Opus 5.5)** — tâches 1, 2, 3 faites, sans appel réel ni navigateur.

### Ce qui est en place

- **Le lieu d'une étape.** Champ facultatif `lieu` d'une étape d'agent : `local` ou `indifférent` (`workflows.LIEUX_D_ETAPE`,
  `workflows.lieu(e)`) ; refusé sur une validation et pour toute autre valeur (`factory.lire`, validateurs de
  `definir_workflow` / `proposer_organisation`, `proposition.verifier_organisation`). `etape_ecrite` le garde ; il passe
  de la proposition du chef à la factory (`definition.proposition_calculee`, `regles._apres_proposer_organisation`).
- **Choix de l'agent.** `modele_necessaire.lieu_de_la_tache(f, t, fonctionnalites)` (lieu écrit de l'étape de la tâche, via
  `etape_de_la_tache` : une relecture/correction prend l'étape de son rôle) et `lieu_impose(lieu_etape, lieu_metier)` :
  `local` → local ; `indifférent` → aucun lieu imposé, **même si le métier est `Lieu : local`** ; absent → le métier
  (seulement dans un projet à polyvalents, comme avant). Branché dans `depart.agent_libre(..., lieu_etape=)`, la commande
  `agent-libre` (champ facultatif `tache`), `outil._modele_et_lieu` (lots), `regles._lieu_reserve(projet, court, tache)`
  et `_choisir_agent` (qui passe `tache` à `agent-libre`). Un projet sans `lieu` choisit exactement comme avant
  (tests de non-régression, suites `polyval`, `moteur` vertes).
- **« attend le poste local ».** Les tâches restées dont le lieu imposé est `local` (étape, ou métier réservé) sont dites
  dans `etat["attente_charge"]` = `{"texte": "En attente : attend le poste local", "taches": [ids], "charge": null,
  "plafond": null}`, sauf si la charge y est déjà (elle passe d'abord). Même fichier `attente-charge.json` qu'avant.
- **Découper un workflow** (`orchestrateur/lieux.py`). `flux_de_reference(f)` : principal et workflows de genre, puis
  les étapes des workflows de fonctionnalité sans leur préfixe `<fid>-` (sans doublon). `verifier_proposition(flux,
  propose)` : validation stricte (un test par cas refusé dans `tests/test_orch_lieux.py`). `appliquer(flux, propose,
  prefixe)` : par identifiant, rejouable, jamais une étape qui a déjà `<id>-local`, une étape non citée gardée.
  `etapes_locales_suggerees(flux, environnement)` : `pour` (id ou nom) ou `objectif` qui nomme l'étape.
  `CONSIGNE_PARTIE_LOCALE` et `est_partie_locale(flux, etape)`.
- **Commande `lieux`** : `{action: reference}` → `{flux, suggerees}` ; `{action: decouper, flux}` (revérifié sur le flux
  de référence du moment, appliqué à tous les workflows, `factory.lire` contrôle le fichier avant de le remplacer) ;
  `{action: regler, etape, lieu}` (`lieu` : `local`, `indifférent` ou null = retiré ; refusé sur une validation ou une
  étape inconnue). Rend `{change, flux}`. Aucune tâche touchée. Interdite au conseil.
- **Jugement `decouper_lieux`** (Sonnet, `moteur/consignes/decouper_lieux.md`) : dossier `{flux, environnement: [{outil,
  pour, objectif}], suggerees, metiers: [{role, lieu}]}` ; réponse `{flux, message}` validée par
  `lieux.verifier_proposition` (redemandée une fois avec l'erreur, puis abandonnée).
- **Moteur.** Demande `proposer_decoupage` → jugement → décision de projet `decoupage_lieux` (rien n'est appliqué avant).
  Deux essais ratés : pas de décision, la demande répond « … rien n'a changé ». Demande `decoupage_lieux` `{decision,
  verdict: valider|refuser}` : `valider` → `lancer lieux decouper`, la décision est levée, chaque élément en cours garde
  son étape par identifiant (`v["pas"]` recalculé : il finit sa partie code puis enchaîne sur `<id>-local`), puis départ
  de ce qui peut partir ; `refuser` → levée, rien ne change. Demande `lieu_etape` `{etape, lieu}` → `lancer lieux regler`
  tout de suite, sans décision ni coût. La tâche d'une partie locale porte `CONSIGNE_PARTIE_LOCALE` en tête de son journal
  (récupérer, compiler, tester au premier plan, capturer, rendre ce que la validation attend, ne pas réécrire le code).
- **Consignes du chef** : `definir_workflow` et `proposer_organisation` rendent `lieu` par étape et découpent une étape
  mixte (`<id>` « … : code » `indifférent`, puis `<id>-local` `local`). Longueurs tenues : `proposer_organisation`
  56 lignes / 5519 caractères (limites 56 / 5600), `definir_workflow` 47 / 5208.

### Ce que la phase B doit savoir (bureau)

- **Relevé** (`outil.construire_releve`, validé et normalisé par `bureau/releve.py`) :
  - `etapes_lieux` (racine, toujours publié en version 4 ; retiré par le normaliseur s'il n'est pas une liste) :
    `[{id, nom, role, validation, lieu, suggeree}]`, les étapes du flux de référence (ids **sans** préfixe `<fid>-`) ;
    `lieu` : `"local"`, `"indifférent"` ou `null` (le métier décide) ; une validation a `validation: true` et
    `lieu: null` (pas de sélecteur) ; `suggeree` : un outil de l'environnement la cite.
  - `colonnes[].lieu` : seulement quand l'étape de la colonne en porte un (ids **avec** préfixe pour les copies).
  - `taches[].lieu` : `"local"` quand la tâche (pas faite) doit se faire sur le poste — son étape l'exige, ou son métier
    est `Lieu : local` dans un projet à polyvalents ; **absent** sinon. C'est le « Sur le poste local » de la fiche.
  - Décision de projet `decoupage_lieux` : `{id, genre, texte, avant, apres, message}` ; `avant` et `apres` sont des
    listes d'étapes `{id, nom, role?, service?, validation?, modele?, justification?, lieu?}` (forme `etape_ecrite`) ;
    une étape de `apres` absente de `avant` est une partie locale ajoutée (`<id>-local`, juste après son `<id>`).
    Une seule à la fois.
  - La barre : `attente_charge.texte` vaut « En attente : attend le poste local » (avec `taches`) quand une tâche locale
    attend une place locale ; `charge` et `plafond` sont alors nuls.
- **Demandes** (`bureau/demandes.py`, `outil.TYPES_DEMANDE`) :
  - `proposer_decoupage` `{}` — refusée si `etapes_lieux` est absent, sans étape d'agent, ou si une décision
    `decoupage_lieux` attend déjà (le bouton « Proposer le découpage » se grise alors).
  - `decoupage_lieux` `{decision, verdict: "valider" | "refuser"}` — réponse unique (`serveur.REPONSES_UNE_FOIS`).
  - `lieu_etape` `{etape, lieu}` — `etape` : un `id` de `etapes_lieux` qui n'est pas une validation ; `lieu` :
    `"local"`, `"indifférent"` ou `null` (le champ doit être présent). Le sélecteur « poste local / cloud possible » peut
    offrir un troisième choix « selon le métier » (`null`).
- **Pas fait** : `bureau/etat.py` ne copie encore ni `etapes_lieux` ni `taches[].lieu` (tâche 4) ; aucune page.

### Écarts au plan, choix

- **Pas de proposition automatique après la reprise des agents polyvalents** (la conception la prévoyait « une fois ») :
  elle coûterait un appel Sonnet sans clic du Directeur ; seul le bouton la déclenche (règle « seule dépense : sur
  accord »). À trancher avec le Directeur en phase C.
- Le **flux de référence** fusionne tous les workflows (principal, de genre, copies sans préfixe) : le jugement voit un
  seul flux, appliqué ensuite par identifiant partout. Pour ZooRunner : `w-jeu-mobile-roguelike` (sans préfixe) et
  `w-f1` (préfixe `f1-`) ont les mêmes étapes de base.
- `etapes_locales_suggerees` sur ZooRunner (lu, pas modifié) donnerait : prototype, contenu, build, tests (Godot, JDK,
  SDK Android).
- `lieu_etape` avec `lieu: null` retire le champ (le métier redécide) : utile pour revenir en arrière.
- `outil.etapes_lieux_du_releve`, `lieu_de_la_tache`, `lieu_de_l_etape` sont les points d'entrée côté outil.
- Le relevé marque aussi « poste local » les tâches d'un métier `Lieu : local` (le palliatif actuel de ZooRunner) : la
  fiche le dira dès la phase B, avant tout découpage.
- Tests ajoutés : `test_moteur_etapes_locales.py` (17), `test_orch_lieux.py` (45), `test_moteur_decoupage_lieux.py`
  (17) ; `test_moteur_jugement.py` : type `decouper_lieux` dans les tables, consignes (lieu, partie locale).

### Non vérifié

- Aucun appel réel du jugement `decouper_lieux` (la qualité de sa proposition sur ZooRunner se verra en phase C).
- Le moteur en marche pendant un découpage (fichier de factory réécrit sous lui) : l'écriture est atomique et le moteur
  relit la factory à chaque usage ; les éléments en mémoire sont recalés par identifiant. Raisonné, pas essayé en vrai.
- Une session cloud qui fait la partie code puis un agent local qui récupère le dépôt : dépend des sessions cloud
  existantes (fusion avant le départ de l'étape suivante), non essayé.
