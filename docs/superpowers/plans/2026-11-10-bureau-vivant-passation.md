# Le bureau vivant — passation entre conversations

Le plan (`2026-11-10-bureau-vivant.md`) est réalisé en quatre phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les étapes de sa phase sans s'arrêter, puis s'arrête et annonce la suivante.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle | Étapes du plan | État |
|---|---|---|---|
| A | Sonnet | 1 à 6 : le serveur | fait (2026-11-10), 74 tests Python verts |
| B | Opus | 7 et 8 : la logique de la page et la scène 3D | fait (2026-11-10), 31 tests JS verts |
| C | Sonnet | 9, 10 et 11 : l'interface, le mode d'emploi, le mobilier Tripo | fait (2026-11-10), 38 tests JS et 74 tests Python verts |
| D | Opus | 12 : le personnage Tripo, puis la relecture finale de tout le projet | à faire |

Notes laissées par la phase précédente (écarts au plan, choix faits, points à surveiller) :

- Travail fait directement sur `main` (la passation demande de pousser sur `main`), un commit par étape.
- (Résolu en phase B : le dossier `bureau/web/tests/` existe désormais.)
- `bureau/web/index.html` est une page provisoire de deux lignes (nécessaire au test de la page) : à remplacer à l'étape 8/9.
- `Equipe.agent(cle, chef=False)` : le paramètre `chef` sert à donner le prénom « Chef » au chef du relevé quelle que soit sa clé.
- Dans l'état, `agent["taches"]` ne liste que les tâches **actives** de l'agent ; `tache["agent"]` est nul si l'agent est parti ou si la tâche n'a pas de titulaire.
- Le serveur refuse (403) toute requête dont l'en-tête `Host` n'est pas `127.0.0.1:<port>` ou `localhost:<port>` (protection contre les pages tierces). La page doit donc être ouverte par l'une de ces deux adresses.
- `GET /api/charge` : si la mesure est indisponible, `disponible` est faux, `cpu`/`memoire`/`charge` valent `null` et `feu_vert` est vrai. `POST /api/reglages` renvoie les réglages sans la clé `dossier`.
- `Historique` ignore à la lecture les lignes de plus de 7 jours avant la ligne la plus récente du fichier.
- Vérifié à la main sur cette machine (étape 6) : CPU 12,7 % servi contre 12 % mesuré par le système, mémoire 85,0 % contre 85,4 %. La mémoire de la machine est à 85 % : la barre de charge sera donc rouge avec le maximum par défaut de 75 % (c'est la réalité, pas un défaut).
- La suite Python dure ~14 s (la commande `charge` mesure 5 s, le test de relevé cassé attend 2,1 s).

Notes laissées par la phase B :

- **Commande des tests JS** : sous Node 24, `node --test bureau/web/tests/` ne parcourt pas le dossier (il le prend pour un fichier et échoue). La commande qui marche est `node --test "bureau/web/tests/*.test.js"` (guillemets compris). `bureau/web/tests/donnees.js` contient les états inventés partagés par les tests.
- **Écarts d'interface (tous des ajouts, rien de retiré)** :
  - `plan.js` : `poste()` rend aussi `cap` et `assis` (vrai pour les 4 bureaux) ; `cafe()` rend `cap` et `assis` (vrai pour les 2 places du canapé). En plus : `plan.meubles` (`{nom, piece, x, z, cap}` : la scène les pose), `plan.openspace`, `plan.batiment`, `plan.pieceDe(p)`, `plan.aService(id)`, `plan.postit(i, rang)` ; chaque pièce a `dir` (+1 rangée du haut, −1 rangée du bas), `fond`, `porte`, `interieur`, `exterieur`. `plan.kanban` a en plus `largeur`, `hauteur`, `entete`, `lignes`, `colonnes`, `largeurColonne`, `devantColonne(i)` : l'agent se place devant la colonne d'arrivée du post-it.
  - `regie.js` : `reinitialiser(etat)` (remise à plat au retour sur l'onglet) ; chaque acteur a aussi `assis` (canapé du café).
  - `scene.js` : `creerScene(conteneur, plan, modeles)` (les modèles en 3ᵉ paramètre) ; rend aussi `choisissables`, `transition(dt)` (fondu de la pause) et `rendu(majOmbres)`. `pointer()` peut aussi rendre `type: "cafe"`.
  - `personnages.js` et `kanban.js` reçoivent le résultat de `creerScene` (pas la `THREE.Scene`) ; `Kanban` a `animer(dt)` (post-its qui glissent). `modeles.js` : `creer(nom, options)` (le `tableau` reçoit `{largeur}`) et `aModele(nom)`.
- **Le Directeur** est un personnage fixe (doré, étiquette « Directeur ») ajouté par `main.js` ; ce n'est pas un agent du relevé. La pastille des décisions reste à faire (étape 9).
- **Repère des modèles** : l'avant d'un objet regarde vers +z local, base à y = 0, `rotation.y = cap`. Le personnage de repli (figurine articulée : `corps`, `jambeG/D`, `brasG/D`, `tete`, `tasse`) est agrandi ×1,3 par `personnages.js` ; un GLB de personnage (étape 12) ne l'est pas.
- **Le Kanban** est dessiné par `kanban.js` (surface, titres, post-its) ; `modeles.creer("tableau", {largeur})` ne fournit que pieds et cadre. Surface utile : 1,55 m de haut, bord supérieur à 2,0 m. À l'étape 11, ajuster ces deux valeurs (`HAUT` dans `kanban.js`, `hauteur` dans `plan.js`) sur le modèle Tripo.
- **Légèreté** : rendu plafonné à 30 images/s quand quelqu'un marche, 12 sinon, rien quand l'onglet est masqué ; ombres recalculées seulement pendant les déplacements (sinon une fois par seconde). Coût mesuré dans la page : ≈ 3 ms par image au repos, ≈ 4,4 ms avec ombres, soit environ 4 % d'un cœur au repos et 13 % pendant une marche. **Non fait** : la mesure au Gestionnaire des tâches pendant 2 minutes, impossible ici (le panneau du navigateur de la conversation était en arrière-plan, la page y tournait à 2 images/s) ; à refaire à l'étape 9 dans un vrai navigateur.
- **Comportement du serveur observé** : un agent qui perd sa seule tâche active et dont l'autre tâche date de plus de 24 h quitte le bureau tout de suite (règle du départ, étape 3). Dans ce cas c'est le chef qui porte le post-it (conforme à la spec). Pour voir un agent marcher au tableau, changer la colonne d'une tâche d'un agent qui garde une autre tâche active, ou dont la `maj` est récente.
- **Vérification manuelle** : faite sur une copie du relevé de la démo hors du dépôt (`.claude/launch.json`, ignoré par git, pointe vers cette copie). Vu : bâtiment entier en isométrique, une pièce par service avec son nom, agents à leur poste ou au café, Kanban rempli, marche jusqu'au tableau en contournant le Kanban, post-it qui change de colonne à la pose, retour au poste, lumière qui baisse en pause, bandeau « Relevé indisponible » sur `{` puis retour à la normale, aucune erreur de console.
- Le bandeau d'erreur actuel est un simple `body[data-erreur]::after` dans `style.css` : l'étape 9 le remplace par celui de `barre.js`.

Notes laissées par la phase C (en cours) :

- **Interface (étape 9)** : `ui/texte.js` (pur, testé : `tronquer`, `dureeEnClair`, `ilYA`, `voyant`, `libelleCharge`), `ui/barre.js` (`creerBarre(entete, bandeau)` → `majEtat`, `majErreur`, `rafraichirCharge`, `charge()`), `ui/panneaux.js` (`creerPanneaux({conteneur, carte, panneau, sc, plan, etat, barre})` → `maj(etat)` ; pastille des décisions au-dessus du Directeur). La scène se recadre toute seule dans l'espace restant quand le panneau de droite s'ouvre : `main.js` observe la taille de `#scene` (ResizeObserver). L'ancien bandeau `body[data-erreur]` est supprimé. Le panneau « service » se rafraîchit à chaque état (sauf pendant la saisie du réglage). Cliquer sur un agent ou un post-it épingle sa carte jusqu'au prochain clic ou Échap.
- **Vérifié dans le navigateur** (copie du relevé de la démo hors dépôt) : barre et voyant, carte d'un agent, panneau Facturation, « Me conseiller » puis « Appliquer » (le trait bouge, `reglages.json` contient 50), texte hostile (`<img onerror>` + 300 caractères : affiché littéralement, tronqué, rien d'exécuté, console vide), relevé cassé puis rétabli (bandeau puis disparition).
- **Non fait** : la mesure de légèreté au Gestionnaire des tâches (voir phase B) — à refaire à la relecture finale, dans un vrai navigateur.
- **Manuel (étape 10)** : `docs/installation.md` suivi à la lettre sur un dossier temporaire (démo et « brancher son projet ») ; capture `docs/img/bureau.jpg` (JPEG, pas PNG : c'est ce que l'outil de capture fournit). Le README est à jour jusqu'à l'étape 10.
- **Fichiers de démo** : `exemples/demo/equipe.json` et `charge-historique.jsonl` étaient suivis par git alors que le serveur les réécrit à chaque lancement : ils sont désormais ignorés (`.gitignore`) et retirés de l'index.
- **Blender (étape 11)** : Blender 3.2.2 est installé dans `C:\Program Files\Blender Foundation\Blender 3.2lender.exe` (pas dans le PATH). `outils/decouper_glb.py` est écrit et vérifié sur un GLB d'essai (trois objets, dont un en deux morceaux qui se touchent : trois GLB corrects, bases au sol, centrés ; erreur claire avec code 1 si le nombre d'objets est faux). Commande : `"C:\Program Files\Blender Foundation\Blender 3.2lender.exe" -b -P outils/decouper_glb.py -- <entree.glb> <dossier_sortie> <nom1,nom2,…>`. Le chargement d'un GLB par `modeles.js` (échelle à la hauteur du manifeste, base au sol, centré) a été vérifié avec un modèle d'essai, puis retiré.
- **Génération 1 intégrée** (2026-11-10) : les 6 meubles (`bureau`, `chaise`, `ecran`, `armoire`, `etagere`, `plante`) sont dans `bureau/web/modeles/` et déclarés dans `manifeste.json`, vérifiés dans la page (bien posés, à la bonne taille, avant tourné vers les agents ; l'étagère montre son dos au centre de la pièce parce qu'elle est contre le mur). Tripo a livré un **FBX + dossier de texture** (pas de GLB) : `decouper_glb.py` accepte donc aussi un `.fbx`. Le premier jet avait des objets qui se chevauchaient (rejeté) ; le prompt corrigé qui a marché ajoute « each one clearly isolated with a wide empty gap between neighbours, nothing overlapping or touching » et « floating alone without any table » pour l'écran — **reprendre cette formulation pour la génération 2**. Quand deux boîtes englobantes se recouvrent sans que les objets se touchent (chaise devant un clavier), le script retombe sur les parties non reliées si leur nombre est celui attendu. Chaque GLB embarque la texture 2K (~0,7 Mo chacun).
- **Génération 2 intégrée** : `machine_cafe`, `canape`, `table_basse`, `tableau`, `bureau_direction` (même méthode ; Tripo a placé la table basse devant le tableau : l'ordre gauche→droite a donné `tableau` avant `table_basse`, repéré aux dimensions). Écart : `bureau_direction` a `hauteur: 1.45` dans le manifeste (et non 0,78) parce que le modèle inclut la lampe ; ainsi le plateau est à ~0,72 m. 
- **Le Kanban est maintenant fait de panneaux** (écart au plan, nécessaire : le modèle Tripo de tableau a un format fixe, 1,75 m de large sur 2,2 m de haut). `plan.js` : `PAS_TABLEAU = 1,75`, `JEU_TABLEAU = 0,16`, `kanban.panneaux`, `largeur = panneaux × 1,75 − 0,16` (démo : 3 panneaux, 5,09 m), `hauteur` 1,25 (surface blanche), `lignes` 4 (au lieu de 5), obstacle de chemin `hz: 0,7` (les pieds dépassent d'environ 0,5 m). `kanban.js` : un modèle `tableau` par panneau si le GLB existe (sinon le volume simple, ajusté à 1,25 m), `HAUT = 2,04`, la surface dessinée par la page est posée 5 cm devant la face blanche. Vérifié dans la page : les colonnes et post-its se lisent sur une longue surface continue portée par les pieds à roulettes.
- **Barre du haut** : corrigé un chevauchement du titre et du voyant à ~800 px de large (`flex: none`, projet masqué sous 900 px).
- **À regarder à la relecture finale** : le dos de la machine à café et de l'étagère est vu de la caméra (leurs faces regardent vers le nord/ouest, c'est voulu par le plan) ; la capture du README (`docs/img/bureau.jpg`) est à refaire après l'étape 12.

Notes laissées par la phase D :

- **Génération 3 (personnage)** : Tripo a livré un **FBX + texture** (squelette Mixamo de 65 os, une animation « walk » sur place de 57 images à 24 i/s, soit deux pas de 28 images). Converti par `outils/convertir_personnage.py` (Blender) en `bureau/web/modeles/personnage.glb` (~1 Mo, texture 2K). Pas d'autres animations fournies : les poses assis / taper / café / post-it sont fabriquées dans la page.
- **Écart au plan** : un fichier en plus, `bureau/web/scene/squelette.js` (préparation du modèle, poses par rotation d'os, fondu avec la marche, teinte). `personnages.js` l'utilise si le modèle `personnage` est chargé, sinon garde la figurine articulée.
- **Teinte** : seule la tranche « pull » du modèle (36 % à 72 % de la hauteur au repos, gris clair peu saturé) prend la couleur de l'agent, par un petit ajout au shader (`onBeforeCompile`) ; peau, cheveux, pantalon et chaussures restent tels quels. Multiplier toute la texture (le plan) aurait teinté la peau.
- **Marche** : le temps d'animation avance avec la distance parcourue (vitesse des pieds mesurée dans Blender : 0,405 hauteur de personnage par seconde d'animation), donc pas de glissement, quelle que soit la vitesse. À 1,5 m/s, la marche est jouée 2,5 fois plus vite que l'original (pas rapides, style figurine). Hauteur du personnage : 1,45 m (manifeste), comme la figurine de repli.
- **Vérifié dans la page** (panneau masqué : animations figées image par image à la main) : agents assis qui tapent, sans nouvelles tête basse, marche en pleine foulée, bras levé au tableau, café assis sur le canapé tasse en main, Directeur doré, pulls de couleurs distinctes, pieds au sol, aucune erreur de console. Coût du rendu : 3,0 ms par image, 3,4 ms avec ombres (comme avant). Capture du README refaite.

## Ce que chaque conversation doit savoir

**Le cadre**

- Dossier de travail : la racine de ce dépôt. Dépôt GitHub public `maximus49000/MyIAFactory`, branche `main`.
- La conception et le plan sont **validés par l'utilisateur**. Il ne faut ni reposer les questions de cadrage ni refaire un plan : on exécute. Méthode : la conversation réalise elle-même les étapes, dans l'ordre, sans sous-agent par étape (skill `superpowers:executing-plans`).
- Lire d'abord, en entier : la conception `docs/superpowers/specs/2026-11-10-bureau-vivant-design.md`, le plan `docs/superpowers/plans/2026-11-10-bureau-vivant.md`, et ce fichier.
- Les sections « Global Constraints », « Les fichiers » et « Les deux formats » du plan valent pour toutes les étapes.

**Les règles à ne pas oublier**

- Dépôt public et vide de tout projet : rien de propre à un projet réel, rien de privé.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"` (voir les notes de la phase B).
- Chaque étape : test d'abord, le voir échouer, coder, le voir passer. Puis cocher l'étape dans le `README.md`, commit en français terminé par `Co-Authored-By: Claude <noreply@anthropic.com>`, et `git push`.
- Ne jamais annoncer qu'une étape est finie sans avoir lancé les tests et lu leur sortie. Si un test échoue ou si une étape ne peut pas être faite comme prévu, le dire avec la sortie, ne pas contourner.
- Un écart au plan (signature changée, fichier en plus) est permis s'il est nécessaire : le noter ci-dessus dans « Notes laissées », car la phase suivante ne lit que le plan et ce fichier.
- Répondre à l'utilisateur en français.

**Ce qui demande l'utilisateur**

- Étape 8 : son accord avant de télécharger three.js (la liste des fichiers est dans le plan).
- Étapes 11 et 12 : c'est lui qui lance les générations Tripo. Lui donner le prompt du plan **avec tous les réglages**, une génération à la fois, vérifier le nombre de caractères (1000 maximum), attendre la capture puis le fichier, intégrer, et seulement ensuite donner la génération suivante.
- En dehors de ces moments, ne pas s'arrêter pour demander : enchaîner les étapes de la phase.

**La fin d'une phase**

1. Tous les tests passent (les deux commandes), sortie lue.
2. Mettre à jour « Où on en est » : la phase passe à « fait », et les notes pour la suivante sont écrites.
3. Dernier commit et push.
4. Dire à l'utilisateur, en clair : ce qui a été fait, ce qui n'a pas pu l'être, **quelle est la prochaine étape**, avec quel modèle, et le message à coller pour la lancer (ci-dessous). Puis s'arrêter : ne pas entamer la phase suivante.

## Les messages à coller

Un message par conversation. L'utilisateur crée la conversation dans ce dossier, choisit le modèle, colle le message.

**Phase A — Sonnet**

> Réalise la phase A du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les étapes 1 à 6 du plan sans t'arrêter, puis fais la fin de phase décrite dans la passation.

**Phase B — Opus**

> Réalise la phase B du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les étapes 7 et 8 du plan, puis fais la fin de phase décrite dans la passation. Le rendu doit être joli : soigne le cadrage isométrique, la lumière, les couleurs et la fluidité des déplacements.

**Phase C — Sonnet**

> Réalise la phase C du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les étapes 9, 10 et 11 du plan, puis fais la fin de phase décrite dans la passation.

**Phase D — Opus**

> Réalise la phase D du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais l'étape 12 du plan. Ensuite, relis tout le projet contre la conception et le plan (un relecteur indépendant, puis tes corrections) : exactitude, cas de la section « Review Focus », rien de propre à un projet ni de privé dans le dépôt, légèreté de la page. Termine par la fin de phase ; la prochaine étape à annoncer est le branchement d'un premier projet réel, à concevoir dans le dépôt de ce projet.
