# Agents polyvalents — passation entre conversations

Le plan (`2026-11-13-agents-polyvalents.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite toutes les tâches de sa phase, sans s'arrêter, puis s'arrête et annonce la suivante. C'est l'utilisateur qui crée chaque conversation et choisit le modèle.

La conception (`docs/superpowers/specs/2026-11-13-agents-polyvalents-design.md`) est **validée par l'utilisateur** le 2026-11-13 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'essai restent **hors dépôt** (chemins donnés par l'utilisateur). Les sessions de phase vérifient par les tests et par des requêtes HTTP, pas par le panneau navigateur. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**, jamais de stash, reset ni changement de branche ; pousser à la fin de la phase.

**Dépenses** : seule la phase E appelle de vrais agents. Elle **attend l'accord explicite de l'utilisateur** avant le premier lancement, dit ce qu'elle va lancer et à peu près combien, et note le coût réel ici. Aucune phase n'installe de logiciel sur le poste.

## Où on en est

Tenir ce tableau à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Dépense réelle | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2, 3 : métier (brief enrichi), fiche polyvalente, leçons par métier | non | Formats et lecture au contrat écrit, tests nommés | **faite 2026-11-13** |
| B | Opus 5.5 | 4, 5, 6 : choix de l'agent et liens amont, modèle par tâche et Fable sur accord, départ par métier | non | Cœur du moteur : chemins de départ multiples, garde Fable, risque de régression | **faite 2026-11-13** |
| C | Sonnet 5.5 | 7, 8, 9 : équipe = places, création au nouveau format, reprise des projets | non (banc gratuit seulement) | Commandes et installation au contrat écrit | **faite 2026-11-13** |
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

**Phase B (2026-11-13, Opus 5.5)** — tâches 4, 5, 6 faites, sans appel réel. Commits `1ce321a`, `33f0932`, `551a7e5`.
Suite complète verte (2042 tests ; un échec d'accès de fichier Windows, `test_bureau_creation`, passe seul) ; `node --test` 514/514.

- **Choix de l'agent** : `modele_necessaire.possibles` ajoute les polyvalents (fiche sans rôle) **après** les spécialistes du
  rôle, sans plafond ; un projet sans polyvalent choisit exactement comme avant (test `test_projet_non_repris_choisit_comme_avant`,
  avec un brief à en-tête `Lieu : cloud` / `Modèle : Haiku` ignoré). Le lieu réservé du métier (`Lieu :` du brief) n'est lu
  **que si le projet a des polyvalents** (`outil.lieu_reserve`, `regles._lieu_reserve`) ; `depart.agent_libre` a un argument
  `lieu_reserve`. Un lot dont un métier est réservé au local ne prend pas de place cloud.
- **Reprise** : une tâche commencée (ou dans `a_lancer`) revient à son agent polyvalent s'il est libre, sinon à un autre ;
  le cadrage garde son agent attitré ; un spécialiste à l'ancienne est attendu comme avant. Reprise par un autre agent : l'entrée
  `etat["cloud"][tid]` de l'ancien est oubliée.
- **Liens amont** : `regles._amont_pret(projet, etat, tache, court, barrieres, cache)` = `depend_de` faites, barrières
  (`_barrieres`) levées et, pour une étape de flux d'un élément, aucune tâche d'avant du même élément pas faite (une tâche
  **bloquée** ne retient rien, comme dans `_barrieres`) ni décision `valider_etape` d'une étape d'avant. Appelé par
  `_demarrer_en_attente` (lot, `a_lancer`, retour, reprise), `_noter_les_places_libres` (la barre « places libres »),
  `orphelines` (une tâche active dont l'amont attend est rendue inactive, elle repartira par le départ ordinaire),
  `_sur_session_cloud` (la tâche n'est pas relevée : elle passe dans `a_lancer`) et `demarrer_installation`.
- **Modèle** : agent polyvalent = `regles._modele_voulu` (montée, modèle du lot, `de_la_tache`, modèle du métier, Sonnet), sans
  plafond. cmd_lots (`_modele_et_lieu`) fait de même. Les fiches à l'ancienne gardent `plafonne`/`ramene`.
- **Fable** : `MODELES_D_ETAPE` (factory, workflows, `modele_necessaire`) et le validateur d'étape de `jugement` acceptent
  `Fable` (écart : les **consignes** `proposer_organisation`/`definir_workflow` disent toujours « jamais Fable », leurs tests
  l'exigent ; à revoir en phase C si le Chef doit pouvoir le proposer). La montée Opus → Fable n'est acceptée par `lancer tache`
  **que dans un projet qui a des polyvalents** (`depart.monter(m, fable=True)`), pour garder l'ancien format intact. Dans un projet
  polyvalent, avant le départ : décision de projet `fable_tache {tache, raison}` (posée une fois), la tâche attend ; demande
  `fable_tache {decision, verdict: autoriser|refuser}` → `fable_accordee` vrai/faux sur la tâche. `_modele_de_depart` rend Opus
  pour toute tâche Fable sans `fable_accordee` (tous chemins, orphelines comprises). Une tâche Fable n'est jamais mise en lot et
  part **en local seulement** (`cloud.lancer_session` refuse Fable) ; la boucle lance l'agent avec une fiche qui porte l'accord
  pour ce départ seulement (`Moteur._fiche_avec_accord`, `fable_accorde` noté aussi au registre détaché). Estimation : Fable compté
  Opus (`mn.estime`). Bureau : carte « Tâches qui demandent Fable » (`decisions.js`), demande vérifiée (`bureau/demandes.py`),
  réponse unique (`serveur.REPONSES_UNE_FOIS`), consignes de l'orchestrateur à jour.
- **Départ** : la boucle ajoute aux outils de l'agent polyvalent ceux du métier de chaque tâche (`Outils :` du brief, des règles
  comme dans les fiches) ; la décision `session_cloud` d'un polyvalent nomme le modèle de la tâche. Une session inscrite sert
  toutes les tâches de l'agent, tous métiers (`sessions_cloud[cle]`).
- Rôles tenus par un polyvalent quand le métier a son brief : cadrage (`_role_cadrage`), relecture (`_sans_relecteur`),
  installation (`installations_pretes` : tout polyvalent).
- Tests anciens adaptés (spec) : étape Fable désormais permise (`test_orch_factory`, `test_orch_workflows`, `test_moteur_jugement`,
  `test_modele_necessaire`) ; deux tests d'empreinte qui prenaient « Fable » comme modèle sans donnée utilisent un nom inventé
  (`test_inst_estimation`, `test_etat`).
- **Pour la phase C** : `recruter`, `parallelisme`, la reprise et la création ne connaissent pas encore les polyvalents. Un projet
  mixte (anciennes fiches + polyvalents) fonctionne (spécialistes d'abord) mais n'est pas un cas visé. Non vérifié en vrai
  (aucun agent lancé) : la sortie réelle de `claude` avec une fiche « accord par tâche ».

**Phase C (2026-11-13, Sonnet 5.5)** — tâches 7, 8, 9 faites, sans appel réel (banc gratuit vert). Commits `740f2ed` (7), `5eb33b1` (8), `5695982` (9, avec la passation).

- **Tâche 7, équipe = places.** `parallelisme` rend en plus `crees`, `retires`, `retraits_prevus` (clés ; vides pour un projet à
  l'ancienne ou mixte). La fiche d'un agent au travail à retirer porte la ligne d'en-tête `Retrait : prévu` (`retrait_prevu` dans
  le dict de la fiche) : jamais choisi (`modele_necessaire.possibles`), jamais libre (`etat.agents[].libre` faux,
  `retrait_prevu` vrai). Nouvelle commande `equipe` (sans entrée, `outil.synchroniser_equipe`) : retire les agents marqués dont la
  tâche est finie ; le moteur la lance en tête de `_demarrer_en_attente` tant qu'un agent est marqué. Seul `parallelisme` crée des
  agents (clé `agent-<n>`, prénom tiré dans `bureau/equipe.PRENOMS`) ; la couleur est tirée par le bureau à la première vue. Ordre
  de retrait : libres sans session d'abord, derniers de la liste d'abord ; puis, faute de libres, les derniers au travail sont
  marqués. Une place remontée annule d'abord les retraits prévus. `recruter` refuse dès qu'il y a un polyvalent (« L'équipe suit
  les places de l'onglet Facturation. ») ; le relevé met `recrutement.polyvalent` (roles/propositions vides) et la page cache le
  bloc Recruter. Un projet mixte (ancien + polyvalents, reprise interrompue) n'est jamais ajusté.
- **Relevé (hors plan, nécessaire).** Un titulaire polyvalent n'a ni `service` ni `modele` : le validateur du relevé refusait tout
  projet polyvalent. Le relevé porte maintenant `polyvalent: true` (et `retrait_prevu: true`) sans service ni modèle, le validateur
  l'accepte, et `agent_cadrage` d'une fonctionnalité dont l'agent a été retiré est publié `null`. **Phase D** : la page ne sait pas
  encore placer un titulaire sans service (pièce de la tâche), ni afficher son modèle ; c'est exactement la tâche 10.
- **Tâche 8, nouveau format d'organisation.** `{metiers: [{role, service, modele?, lieu?, specialite?, outils?, brief}], agents:
  {locaux, cloud}}` remplace `agents` (liste) + `briefs` ; `proposition.verifier_organisation(..., metiers=, equipe_en_place=)`,
  `proposition.est_polyvalente`, `verifier_metiers`, `verifier_equipe`, `agents_pour_estimer` (estimation sans plafond :
  `mn.estime` ignore le plafond des agents `sans_plafond`). `mise_en_place.ecrire_organisation(..., metiers=)` écrit les briefs
  enrichis (`metiers.ecrire_metier`) ; un projet sans équipe reçoit `n + m` fiches polyvalentes et ses places (`agents_locaux_max`,
  `agents_cloud_max`) sont réglées à `n` et `m` ; un projet qui a déjà son équipe la garde (`agents` absent). Le contrôle refuse
  des agents par rôle dans un projet polyvalent et des métiers dans un projet qui a encore des agents par rôle ; l'ancien format
  reste accepté partout ailleurs (tests `test_ancienne_organisation_acceptee`, `test_projet_a_l_ancienne_refuse_les_metiers`).
  Le chef (`definir_workflow`) ne propose plus que le nouveau format ; `proposer_organisation` suit le dossier : s'il porte
  `metiers`, il propose des métiers. L'agent d'installation devient un métier `environnement` (ses règles d'outils vont dans son
  brief). Fable ne se coche plus par agent dans le nouveau format (refusé par `appliquer`). Fenêtre du chef et décision
  d'organisation : lignes « Métiers » et « Équipe : N agents locaux, M agents cloud » (`echange.js`, `organisation.js`).
- **Écarts au plan (tâche 8).** Les tests de longueur des consignes (`test_moteur_jugement` : 40 lignes, 4600 caractères) portent
  maintenant 56 lignes et 5600 caractères (`proposer_organisation` décrit les deux formats) ; la consigne de `definir_workflow` ne
  dit plus « plafond Opus » ni `fable_suggere`, son exemple de test est au nouveau format. Le nombre d'agents cloud proposé par
  le chef n'est pas confronté à GitHub (la consigne dit 0 sans GitHub, non vérifié en code). L'estimation du coût en
  euros compte les métiers du projet existants par leur modèle de brief ; sans brief de modèle : Sonnet.
- **Tâche 9, la reprise.** `orchestrateur/reprise_polyvalents.py` (`reprendre`, et les étapes `mettre_de_cote`,
  `fixer_les_metiers`, `regrouper_les_lecons`, `ramener_l_equipe`, chacune rejouable) ; commande `polyvalents` (`{confirme: true}`),
  demande `passer_polyvalent` (bureau, outil, moteur, bouton « Passer aux agents polyvalents » avec confirmation dans
  « Parallélisme du projet », visible tant que `recrutement.reprise_possible`). Choix : (a) l'original de chaque fiche est copié
  dans `<fiches>/avant-polyvalents/` avant toute réécriture (jamais écrasé) ; (b) le « journal du projet » n'existant pas, le compte
  rendu est ajouté à `.factory/reprise-polyvalents.md` et rendu en réponse de la demande ; (c) gardés d'abord : agents au travail,
  agent de cadrage d'une fonctionnalité en cadrage, session cloud, puis ordre des noms de fichier ; (d) la reprise **ne crée jamais
  d'agent cloud** et ajoute seulement des agents locaux si les places en demandent plus que de fiches locales ; (e) les places
  cloud sans réglage valent l'ancienne limite (3) pour un projet qui a des agents cloud (`depart.places_cloud`) ; (f) un brief de
  métier illisible arrête la reprise avant toute écriture ; (g) les leçons « à valider » du suivi portent `metier`, les validées
  sont déjà dans le brief ; une validation ultérieure par l'ancien id va au métier (test `test_validation_apres_reprise_va_au_metier`).
  Le chef (fiche de rôle `chef`) n'est pas repris.
- **Pour la phase D.** Le relevé d'un projet repris : titulaires `polyvalent: true`, sans `service` ni `modele` ; la tâche porte
  `role`, `modele_depart`, `etape`, le service de la tâche est celui de son étape (workflow) ou du brief du métier
  (`metiers.lire_metier(...)["service"]`, non publié au relevé aujourd'hui) ; `recrutement.polyvalent` et `reprise_possible`
  sont publiés. Les leçons des agents polyvalents n'existent plus dans leur fiche : elles sont dans les briefs (le relevé ne les
  publie pas encore par métier ; `titulaires[].lecons` est vide pour un polyvalent).
- **Non vérifié.** Aucune reprise lancée sur ZooRunner ni sur un vrai projet ; le moteur en marche pendant une reprise (une fiche
  réécrite sous un agent au travail) est raisonné, pas essayé : lancer la reprise de préférence quand aucun agent ne travaille.
  La page (`node --test` seulement), jamais ouverte dans un navigateur.
