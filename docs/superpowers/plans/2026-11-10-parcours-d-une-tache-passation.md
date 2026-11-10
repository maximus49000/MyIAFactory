# Le parcours d'une tâche — passation entre conversations

Le plan (`2026-11-10-parcours-d-une-tache.md`) est réalisé en dix phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-10-dossiers-des-services-passation.md`.

Les phases A à G se font **dans ce dépôt**. Les phases H, I et J se font **dans le dépôt privé du projet pilote** : elles tiennent leurs notes dans ce dépôt privé, et n'écrivent ici que des corrections génériques et, à la toute fin, une ligne générique dans le `README.md` et dans ce fichier.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Où | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | ce dépôt | 1 à 3 : relevé v4, état v4, demandes et images jointes | Validation de champs entièrement décrite par le plan, tests en tableau | fait |
| B | Opus 5.5 | ce dépôt | 4 et 5 : plusieurs projets, catalogue et livrable servis | Serveur à fils scindé en deux classes sans rien casser, isolation entre projets, fichiers servis (bac à sable) | fait |
| C | Sonnet 5.5 | ce dépôt | 6 à 8 : sélecteur, panneau de fonctionnalité et discussion, Directeur | Interface cadrée par les demandes et l'état des phases A et B | fait |
| D | Opus 5.5 | ce dépôt | 9 : le catalogue | Reprendre fidèlement le design d'une page existante, carte avec zoom, 5 000 éléments | fait |
| E | Sonnet 5.5 | ce dépôt | 10 à 12 : fichier de factory, suivi, mémoire, départ d'un agent, vérificateur | Outils en ligne de commande au contrat écrit ; les cas difficiles (git, mots interdits, écritures concurrentes) ont leurs tests nommés | fait |
| F | Opus 5.5 | ce dépôt | 13 et 14 : consignes génériques, démo, documentation, relecture finale | Les consignes guident l'orchestrateur : leur justesse compte plus que tout ; relecture finale sur un modèle fort | à faire |
| G | Opus 5.5 | ce dépôt (projets copiés hors dépôt) | 15 : le vrai passage de bout en bout, mené avec l'utilisateur | Diagnostic d'un orchestrateur réel et corrections génériques | à faire |
| H | Opus 5.5 | dépôt du projet pilote | la liste de compatibilité | Ne rien oublier du fonctionnement actuel : lecture fine de longues consignes | à faire |
| I | Sonnet 5.5 | dépôt du projet pilote | les adaptateurs, la version 4, les demandes, le catalogue | Travail cadré par l'interface et contrôlé par `verifier_interface.py` | à faire |
| J | Opus 5.5 | dépôt du projet pilote | la bascule et la vérification finale | Dernier mot sur « rien n'est perdu » | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. Haiku n'est retenu pour aucune phase : chacune demande de lire une conception longue et de tenir des tests. **Fable n'est utilisé dans aucune phase**, ni pour exécuter, ni pour relire (la relecture finale se fait sur Opus).

Notes laissées par les phases précédentes (écarts au plan, choix faits, points à surveiller) :

**Phase A (Sonnet 5.5) — écarts et points à surveiller**

- `bureau/demandes.py` : `verifier(demande, r, cibles_calculees=frozenset(), elements=None)` ; `verifier_images` rejette aussi un type incohérent avec l'extension et un nom contenant `:` ; `nettoyer` ne garde que `nom`, `type`, `donnees` de chaque image ; une `lecon` portant `etage` est refusée sur un relevé de version < 4.
- `bureau/serveur.py` : `MAX_CORPS_DEMANDE`, `MAX_CORPS_REGLAGES`, `GARDE_DOUBLON_S`. L'anti-doublon est dans `Bureau.demande` (champ `_derniere_creation`, un seul emplacement, contrôlé **avant** la lecture du relevé, rempli seulement quand la commande a réussi). **Phase B** : ce champ, comme `_challenges_envoyes`, passe dans `Projet` (un par projet) ; `Bureau.demande` appelle `verifier(..., None)` pour `elements`, la phase B (tâche 5) fournit la lecture du catalogue.
- `bureau/releve.py` : constantes `ETAPES`, `DECISIONS_FONCTIONNALITE`, `DECISIONS_PROJET`, `ETAGES`, `MOTIF_GENRE` (compilé, `^…\Z`), `MAX_FONCTIONNALITES`, `MAX_MESSAGES`, `MAX_IMAGES_MESSAGE`. Un livrable exige `libelle` ; `date` est un texte ou nul. Les ids de décisions sont uniques dans tout le relevé ; les ids de messages le sont seulement dans leur discussion.
- `bureau/etat.py` : en version 4, `etat` gagne `genre`, `livrable`, `fonctionnalites`, `decisions_projet`, `orchestrateur_actif`, et `directeur` gagne `fonctionnalites` et `projet` ; ces clés sont **absentes** en version < 4. Chaque tâche porte ses quatre champs v4. Les leçons gardent `etage_propose`, `texte_general`, `roles`.
- Tests : 388 `unittest` et 95 `node --test` verts en fin de phase.

**Phase B (Opus 5.5) — écarts et points à surveiller**

- `bureau/serveur.py` : `Projet` (un par fichier de réglages : équipe, historiques, prix et son fil, cache d'état, dernier relevé, demandes, gardes des challenges et des doublons) et `Bureau(adresse, [(id, chemin)], ouvrir=None, multi=True)` (`projets` dict dans l'ordre du fichier, `projet(id=None)`, une seule `sonde`/`lisseur`, `_ranger_mesure` note chaque mesure dans l'historique de chaque projet). `--reglages` → un projet d'id `projet`, `multi=False`. Les tests serveur passent par `self.p` (`srv.projets["projet"]`).
- Routes de projet (`?projet=`, absent → le premier, vide/répété/inconnu → 404 `{"erreur": "Projet inconnu."}`) : `/api/etat`, `/api/charge`, `/api/conseil`, `/api/facturation`, `/api/kpi`, `/api/image`, `/api/catalogue`, `/api/livrable`, `POST /api/demande`, `POST /api/reglages`. **Phase C** : la page doit ajouter `projet=<id>` à chacune quand `multi` est vrai (sinon rien ne change).
- `GET /api/projets` → `{multi, projets: [{id, nom, attente, erreur}]}` ; il sert le dernier état connu (relu en arrière-plan, projets lus en parallèle) : on peut le sonder souvent. `nom` vaut l'id quand le relevé est en erreur.
- `reglages.lire_bureau` (écart utile au plan, après relecture) refuse aussi un fichier de réglages **introuvable** et deux projets dont les réglages sont **dans le même dossier**.
- `bureau/catalogue.py` : `declaration(regl, f)` rend aussi `base` (écart : les chemins d'une déclaration du fichier de factory sont relatifs **au fichier de factory**, comme le dit la tâche 10 ; ceux des réglages, aux réglages). `lire` → `(code, objet)` ; `ids(regl, f)` → ensemble ou `None` ; `valider` retire les champs inconnus sans le dire, et retire avec avertissement un champ facultatif au mauvais type (une liste entière si un de ses objets est fautif) ; une adresse ou un chemin absolu dans `captures[].chemin`, `comparaisons[].reel/.produit`, et un lien invalide dans `liens[].url`/`comparaisons[].lien`, sont retirés un à un. `trace[].points` = liste de paires `[x, y]`. Avertissements bornés à 100. **Phase D** : formes exactes dans `OBJ_*` et `ELEMENT` de ce fichier ; `GET /api/catalogue?projet=&fonctionnalite=` (sans `fonctionnalite` → 404).
- `GET /api/livrable?projet=&fonctionnalite=?` : sert le `chemin` du livrable (du projet, ou de la fonctionnalité) dans `livrables.racines` ; un livrable donné par `lien` → 404 (la page ouvre le lien elle-même). `.html`/`.txt` avec `Content-Security-Policy: sandbox` et `nosniff` ; `.zip`/`.glb` en pièce jointe.
- Mineurs laissés (relecture) : déclaration invalide dans les réglages qui retombe sans le dire sur le fichier de factory ; caches du catalogue sans éviction ; `Content-Length` du livrable si le fichier change pendant l'envoi ; le bac à sable HTML n'empêche pas de charger une image distante ; un fil des prix par projet ; tests à ajouter (livrable `../ailleurs/x.png`, lien symbolique sortant).
- Tests : 424 `unittest` et 95 `node --test` verts en fin de phase.

**Phase C (Sonnet 5.5) — écarts et points à surveiller**

- `bureau/web/ui/projets.js` : `avecProjet`, `projetInitial`, `livrables(etat, projet)` (purs) ; état du projet courant (`definirProjet`, `projetCourant`, `urlProjet`) ; `lireProjets`. `main.js` lit `/api/projets` au démarrage ; si `multi`, il fixe le projet (mémorisé sous `myiafactory.projet`, sinon le premier) et **toute** requête de la page passe par `urlProjet` (état, charge, conseil, réglages, demandes, facturation, KPI, images via `imagesUrl`). **Phase D** : faire passer `/api/catalogue` et les images du catalogue par `urlProjet` aussi. Un changement de projet recharge la page ; les pastilles suivent à chaque lecture de l'état.
- `ui/barre.js` : `majProjets`, `boutonNouvelle`, `boutonFonctions` (montrés pour un relevé v4 avec `agir`), « Dernier livrable » (lien, ou menu `details` s'il y en a plusieurs). `ui/panneaux.js` branche les deux boutons.
- `ui/fonctionnalite.js` : fonctions pures du plan, plus `contenuFonctionnalite(ctx, contenu, f|null)` et `contenuFonctionnalites`. Panneaux ajoutés : `fonctionnalite` (id ou `null` = discussion neuve) et `fonctionnalites`. Le contexte gagne `envois`, `envoyes`, `nouvelle`, `rouvrir`, `ouvrirFonctionnalite`, `ouvrirNouvelle`. Le panneau d'une fonctionnalité se redessine même pendant la saisie (le brouillon, ses images et le curseur sont conservés). Un message envoyé reste affiché (« en attente ») tant que le relevé ne l'a pas repris. **Phase D** : le bouton « Catalogue » n'apparaît que si le contexte fournit `ctx.ouvrirCatalogue(id)` ; il suffit de le définir dans `contexte()` de `panneaux.js`.
- `ui/actions.js` : `decisionsDirecteur`, `demandeLecon`, `demandeGenre`, `demandeSession`, `libelleMontee`. Les parties de décisions du Directeur sont dans `ui/decisions.js` (écart : fichier en plus) ; `ui/directeur.js` ajoute l'étage et le texte général aux leçons ; `detail.js` montre la montée de modèle.
- Vérifié au navigateur sur deux projets (un v3, un v4) : sélecteur, pastilles, choix retenu, discussion avec image, texte hostile littéral, « En attente de l'orchestrateur », double clic = une demande, chaque bouton du Directeur envoie la bonne demande, console vide (hors un 502 voulu venant d'une commande de test cassée). Le cas `--reglages` (sans sélecteur) est couvert par `lireProjets` (404 ou `multi` faux), pas revu au navigateur.
- Mineur laissé : les messages de la discussion ne défilent pas automatiquement vers le dernier.
- Tests : 424 `unittest` et 110 `node --test` verts en fin de phase.

**Phase D (Opus 5.5) — écarts et points à surveiller**

- La page du projet pilote a été lue en lecture seule ; rien n'en est recopié. Le design qui en est repris : fiches à plaque émaillée (nom en capitales sur fond bleu nuit, filet clair), palette pierre / papier / ardoise, grille de cartes, filtres « pressés » en ardoise, compteurs en chiffres tabulaires, comparaison à barre glissante avec étiquettes « Produit » / « Réel », badge de passe sur la capture, légende en pastilles. Les polices gardent les mêmes familles en premier choix, avec des polices locales en repli : **aucune police n'est chargée d'Internet** (pas de requête sortante nouvelle). Tout est dans `.catalogue` (variables `--cat-*` à la fin de `style.css`).
- `ui/catalogue.js` : les fonctions pures du plan, plus `sansAccents`, `teinte(e)` (`doute` d'abord, puis `ok` pour `valide`/`fait`/`termine`/`ok`, `a-faire` pour `a_revoir`/`a_faire`/`en_cours`/`todo`, sinon `autre`) et `libelleEtat` (« à revoir », « validé »…, sinon l'id avec des espaces). **Phase E/F** : `interface.md` et la démo devraient recommander ces ids d'état, sinon tout tombe dans « autre » sur la carte. `pageDe` compte les pages à partir de 0 et rend `{elements, page, pages, total}`.
- `ui/vue-de-haut.js` : `cadrage` (pur), puis la carte sur `<canvas>`. **Repère choisi : y vers le haut** (le nord en haut) pour `position` et `trace` ; à écrire dans `interface.md` (phase E). Les éléments hors filtre sont estompés, pas retirés. La molette au-dessus de la carte zoome (comme sur la page pilote) : pour faire défiler le panneau, il faut être hors de la carte.
- Panneau : type `catalogue` (id = fonctionnalité). Il élargit le panneau à 620 px (`body.panneau-catalogue`) ; « Agrandir » le met en plein écran (`body.panneau-grand`). Échap revient d'abord du plein écran, puis ferme ; Échap dans un champ rempli ne fait rien (vaut pour tous les panneaux). Contexte : `ouvrirCatalogue(id)` (ouvre la page, pas la dernière fiche), `estOuvert(type, id)`, `catalogues`, `vuesCatalogue`, `retoursEnvoyes`, `grand()`, `basculerGrand()`. La barre gagne `surCatalogue(fn)` : le menu « Dernier livrable » liste aussi « Catalogue · <nom> » pour chaque fonctionnalité qui a `catalogue: true` (bouton « Catalogue » seul s'il n'y a que lui). Rien n'a changé dans `fonctionnalite.js` : le bouton « Catalogue » y apparaît dès que `ctx.ouvrirCatalogue` existe.
- Le catalogue est lu à l'ouverture puis gardé ; « Actualiser » le relit (le serveur garde une commande 30 s en cache). Un retour envoyé reste affiché « envoyée · en attente du catalogue » jusqu'à ce que le catalogue relu contienne le même texte (comparé sans les espaces autour). Il n'y a pas de relecture automatique.
- La démo n'a pas encore de catalogue (c'est la phase F) : la vérification au navigateur s'est faite sur deux catalogues inventés hors dépôt (5 éléments avec tous les cas, et 5 000 éléments). Vérifié : filtres et recherche sans accents (23 ms sur 5 000), pages de 100, carte (zoom autour du curseur, glisser, clic vers la fiche, zoom gardé après la fiche et après « Agrandir »), comparaison à deux angles, retour envoyé (un double clic donne une seule demande, aux champs exacts), texte hostile littéral, image hors racine en 404, projet v3 sans menu catalogue, console vide hors ce 404 voulu.
- Relecture indépendante (Opus) faite, avec corrections. Mineurs laissés : des ids de groupe ou des numéros de passe en double donnent deux boutons ; seules quatre teintes sur la carte (pas une couleur par état inconnu) ; le menu s'appelle « Dernier livrable » même s'il n'a que des catalogues ; une fiche rouverte par le catalogue (pas par la barre ni la fonctionnalité) garde la dernière fiche vue.
- Tests : 424 `unittest` et 120 `node --test` verts en fin de phase.

**Phase E (Sonnet 5.5) — écarts et points à surveiller**

- Fichiers : `orchestrateur/{factory,suivi,fiches,memoire,depart,outil,verifier_interface}.py` (**`fiches.py` en plus** : lecture et écriture des fiches), `interface.md`, `memoire/skill.md` (sans leçon) et `memoire/genres/LISEZMOI.md` (aucun genre livré), `modeles/fiche-agent.md`. Tests : `tests/orch_aide.py` (projet minimal fabriqué en dossier temporaire, `AvecProjet.outil/ok`) et `test_orch_{factory,suivi,memoire,depart,interface}.py`.
- `outil.COMMANDES` : dictionnaire `nom → (fonction, mode d'entrée)` ; `outil.executer(factory, argv, entree) → (code, objet)` rend l'exécution en processus. **Phase F** : `test_chaque_commande_documentee` compare `outil.COMMANDES` aux titres `### \`commande\`` de `interface.md` (hors `lancer`, qui est un mode d'appel et non une commande ; les titres `##` ne sont pas des commandes). Les commandes sont : releve, charge, actions, reveil, demandes, demande-traitee, etat, fonctionnalite, message, decision, tache, file, file-prendre, session, catalogue, memoire, genre, lecon, controle, agent-libre, depart.
- Écarts au plan, tous dans `interface.md` : (1) **`actions` refuse par une ligne de texte brut** et non par `{"erreur"}`, car le bureau montre la première ligne telle quelle ; (2) une commande « sans entrée » ne lit jamais l'entrée standard (une commande lancée sans entrée ne se bloque pas) ; (3) `catalogue` accepte aussi l'identifiant en argument (`catalogue f1`) pour servir de commande de catalogue au bureau, qui n'envoie pas d'entrée ; (4) dans une demande enregistrée, l'`id` d'un bouton ou d'une leçon visée passe dans `cible` (l'`id` est celui de la demande, `r<n>`) ; (5) les images d'une demande vont dans `pieces/<id de la fonctionnalité>/` (la fonctionnalité est créée tout de suite, il n'y a pas de dossier « nouvelle ») ; (6) le fichier de factory accepte une clé `nom` (défaut : le nom du dossier du projet, ou de son parent pour `.factory`) ; (7) un refus de commande déclarée garde son code et sa sortie telle quelle ; (8) `lecon noter` ajoute la ligne « à valider » à la fiche **et** garde ses champs (étage proposé, texte général, rôles) dans le suivi ; la leçon appliquée reste dans le suivi, « validée » ; (9) `decision poser` est idempotent (même portée, genre et texte : même identifiant), et `genres_connus` vaut par défaut la liste des genres de la mémoire.
- Suivi : fichier `suivi.json` (verrou `suivi.json.verrou`, 5 s, un verrou de plus de 30 s est repris) ; journal `demandes.jsonl` à côté ; table des sessions `sessions.json` ; registre `controles.md`. Le relevé donne à chaque fiche `permanent: true` (les agents sont toujours visibles à leur bureau), ajoute le chef (la fiche de rôle `chef`, sinon un titulaire `chef`), une tâche « Orchestration » (`maj` = dernier `reveil`, donc `orchestrateur_actif` du bureau) et, pendant le cadrage, « Cadrage : <nom> » pour l'agent de cadrage. Les chemins du suivi sont relatifs au fichier de factory ; le relevé et le catalogue les rendent relatifs au dossier des réglages.
- **Point ouvert pour la phase F (démo, consignes)** : le bureau cherche la déclaration d'un catalogue par **identifiant de fonctionnalité** (`catalogues` du fichier de factory) ; or les fonctionnalités créées par le bureau reçoivent des identifiants `f1`, `f2`… au fil du temps. Soit la démo et le guide déclarent `catalogues: {"f1": {"commande": [… "outil.py", "--factory", F, "catalogue", "f1"]}}` au moment où l'orchestrateur fait passer la fonctionnalité en série, soit `bureau/catalogue.declaration` accepte une déclaration générique (par exemple la clé `*`). À trancher ; je n'ai pas touché au bureau. `fonctionnalite {catalogue: true}` suffit pour que le bureau montre le bouton « Catalogue ».
- Mémoire : `memoire.ajouter` et `memoire.creer_genre` prennent un `git` injectable ; un échec à n'importe quel pas remet le fichier et défait le commit local. Un nouveau genre est créé par `genre fixer` avec sa description (`Domaine : <description>`, `Livrable` et `Outils` : « à préciser »). Variable `MYIAFACTORY_MOTS` : fichier de mots interdits (un par ligne) tenu hors du dépôt ; sans elle, `test_skill_md_sans_projet` est sauté (c'est le seul test sauté).
- Vérificateur : sans `--complet` il ne change rien ; avec, il rejoue un scénario (fonctionnalité, tâche, décision, leçon invalidée, session, contrôle…) puis relit. `genre fixer` n'est essayé que si le projet a déjà un genre. Refuse `--complet` dans un dépôt git sans fichier `.copie-de-verification`.
- Pas encore écrit (phase F) : `consignes.md`, `modeles/brief-role.md`, `modeles/registre-controles.md`, `modeles/factory.json`, `docs/orchestrateur.md`, `tests/test_orch_consignes.py`, la démo à deux projets. Les ids d'état du catalogue et le repère de la carte (y vers le haut) sont déjà écrits dans `interface.md`.
- Mineurs laissés : `fonctionnalite` n'écrit pas de `livrable` de projet (seulement par fonctionnalité) ; `charge` lance la vraie mesure (cinq secondes) ; pas de nettoyage des vieux enregistrements du suivi ; une leçon dont l'agent n'a pas de fiche reste seulement dans le suivi. Honnêteté sur la méthode : pour les tâches 11 et 12, j'ai écrit les tests avant le code mais je n'ai vu « échouer » que ceux de la tâche 12 et ceux de la tâche 10 ; les tests de la mémoire ont été lancés une première fois avec le code déjà écrit.
- Tests : 507 `unittest` (1 sauté : `MYIAFACTORY_MOTS`) et 120 `node --test` verts en fin de phase.

## Ce que chaque conversation doit savoir

**Le cadre**

- Dossier de travail : la racine de ce dépôt (phases A à G). Dépôt GitHub public `maximus49000/MyIAFactory`, branche `main`.
- La conception et le plan sont **validés par l'utilisateur**. Il ne faut ni reposer les questions de cadrage ni refaire un plan : on exécute. La conversation réalise elle-même les tâches de sa phase, dans l'ordre (skill `superpowers:executing-plans`).
- Lire d'abord, en entier : la conception `docs/superpowers/specs/2026-11-10-parcours-d-une-tache-design.md`, le plan `docs/superpowers/plans/2026-11-10-parcours-d-une-tache.md`, et ce fichier. Les sections « Global Constraints » et « Review Focus » du plan valent pour toutes les tâches.

**Les règles à ne pas oublier**

- Dépôt public et vide de tout projet : rien de propre à un projet réel, rien de privé. Le projet pilote n'est jamais nommé ici, ni dans le code, ni dans les mémoires, ni dans les commits.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"`.
- Aucun test ne sort sur Internet ; les tests de mémoire n'utilisent que des dépôts git temporaires locaux.
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer. Puis cocher la tâche dans le `README.md`, commit en français terminé par `Co-Authored-By: Claude <modèle de la conversation> <noreply@anthropic.com>`, et `git push`.
- Ne jamais annoncer qu'une tâche est finie sans avoir lancé les tests et lu leur sortie. Si un test échoue ou si une tâche ne peut pas être faite comme prévu, le dire avec la sortie, ne pas contourner. Si un passage complet de `unittest` échoue une fois sans raison visible, rediriger la sortie dans un fichier et noter le nom du test.
- Un écart au plan (signature changée, fichier en plus) est permis s'il est nécessaire : le noter ci-dessus dans « Notes laissées », car la phase suivante ne lit que le plan et ce fichier.
- Répondre à l'utilisateur en français.

**Ce qui demande l'utilisateur**

- Phase D : le chemin de la page de catalogue actuelle du projet pilote sur sa machine (lue en lecture seule, rien n'en est recopié).
- Phase G : c'est lui qui crée les conversations orchestratrices et mène la fonctionnalité dans le bureau.
- Phases H à J : c'est lui qui ouvre la conversation sur le dépôt privé, et qui crée les sessions cloud demandées.
- En dehors de ces moments, ne pas s'arrêter pour demander : enchaîner les tâches de la phase.

**La fin d'une phase**

1. Tous les tests passent (les deux commandes), sortie lue.
2. Mettre à jour « Où on en est » : la phase passe à « fait », et les notes pour la suivante sont écrites.
3. Dernier commit et push.
4. Dire à l'utilisateur, en clair : ce qui a été fait, ce qui n'a pas pu l'être, **quelle est la prochaine phase**, avec quel modèle, **dans quel dossier** l'ouvrir, et le message à coller pour la lancer (ci-dessous). Puis s'arrêter : ne pas entamer la phase suivante.

## Les messages à coller

Un message par conversation. L'utilisateur crée la conversation dans le dossier indiqué, choisit le modèle, colle le message.

**Phase A — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase A du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 1 à 3 du plan sans t'arrêter, puis fais la fin de phase décrite dans la passation.

**Phase B — Opus 5.5 — dans ce dépôt**

> Réalise la phase B du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 4 et 5 du plan, puis fais la fin de phase décrite dans la passation.

**Phase C — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase C du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 6 à 8 du plan, puis fais la fin de phase décrite dans la passation.

**Phase D — Opus 5.5 — dans ce dépôt**

> Réalise la phase D du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 9 du plan : demande-moi d'abord le chemin de la page de catalogue actuelle du projet pilote, lis-la en lecture seule pour en reprendre le design, et n'en recopie rien de propre au projet. Termine par la fin de phase décrite dans la passation.

**Phase E — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase E du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 10 à 12 du plan, puis fais la fin de phase décrite dans la passation.

**Phase F — Opus 5.5 — dans ce dépôt**

> Réalise la phase F du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 13 et 14 du plan. La tâche 14 se termine par la relecture de tout le projet contre la conception et le plan (un relecteur indépendant sur Opus, jamais Fable, puis tes corrections) : exactitude, cas du « Review Focus », rien de propre à un projet ni de privé dans le dépôt. Termine par la fin de phase.

**Phase G — Opus 5.5 — dans ce dépôt**

> Réalise la phase G du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 15 du plan avec moi : prépare les projets copiés hors du dépôt, donne-moi le message qui ouvre chaque conversation orchestratrice, puis guide-moi pas à pas et corrige ici, avec un test, chaque écart générique. Termine par la fin de phase ; la prochaine phase à annoncer est la phase H, dans le dépôt privé du projet pilote.

**Phase H — Opus 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase H du parcours d'une tâche de MyIAFactory, pour ce projet. Le dépôt de la skill MyIAFactory est sur cette machine (demande-moi son chemin si tu ne le trouves pas) : lis-y `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md`, la conception, le plan (« Étape 6 ») et `docs/orchestrateur.md` ; tout est validé, rien à recadrer. Relis les consignes d'orchestration actuelles de ce projet et ses outils, puis écris dans ce dépôt : la liste de compatibilité (chaque comportement actuel, l'outil qui le porte, comment le vérifier ; rien ne doit être perdu), le fichier de factory avec ses mots interdits, les consignes propres (le document actuel), le plan des adaptateurs, et une passation pour les phases I et J. N'écris rien de propre à ce projet dans le dépôt de la skill. Arrête-toi ensuite et annonce la phase I.

**Phase I — Sonnet 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase I du parcours d'une tâche de MyIAFactory, pour ce projet. Lis la passation et le plan des adaptateurs écrits en phase H dans ce dépôt, puis, dans le dépôt de la skill, `orchestrateur/interface.md` et `docs/orchestrateur.md`. Écris les adaptateurs (sans modifier les outils existants), les champs de la version 4 du relevé, les nouvelles demandes dans la commande d'actions, l'étage des leçons et le catalogue au format de la skill à côté de la page actuelle. `verifier_interface.py` doit passer sans `--complet` sur ce projet, et avec `--complet` sur une copie marquée. Une correction générique va dans le dépôt de la skill, avec son test et sans nom de ce projet. Arrête-toi ensuite et annonce la phase J.

**Phase J — Opus 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase J du parcours d'une tâche de MyIAFactory, pour ce projet. Lis la passation de ce dépôt. Fais passer ce projet sur l'orchestrateur générique, avec moi : vérifie chaque ligne de la liste de compatibilité et coche-la, et dis-moi en clair toute ligne qui ne passe pas. Lance ensuite, dans le dépôt de la skill, un `git grep` avec les mots interdits de ce projet : aucun résultat attendu. Enfin, dans le dépôt de la skill seulement, mets à jour le `README.md` et `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` en une phrase générique (« projet 3 terminé, vérifié sur le projet pilote »), sans aucun nom, commit et push. Annonce ensuite la prochaine étape : le projet 4, l'installation sur un projet, à concevoir.
