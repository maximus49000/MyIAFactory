# L'installation sur un projet — passation entre conversations

Le plan (`2026-11-11-installation-sur-un-projet.md`) est réalisé en sept phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** (la norme de la skill, section 14 de la conception) : depuis la phase D, les tâches restantes sont regroupées pour qu'un même modèle fasse d'une traite tout ce qu'il peut faire d'affilée ; l'ordre des tâches est celui de la phase, pas celui des numéros. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-10-parcours-d-une-tache-passation.md`.

Les phases A à F et la phase « Essais réels » se font **dans ce dépôt**. La phase G se fait **dans le dépôt privé du projet pilote** : elle y tient ses notes, et n'écrit ici que des corrections génériques et, à la toute fin, une ligne générique dans le `README.md` et dans ce fichier.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Où | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | ce dépôt | 1 à 3 : chemins `~`, limite d'agents locaux, leçon gardée en local | Changements courts et cadrés, tests nommés | fait |
| B | Sonnet 5.5 | ce dépôt | 4 à 6 : dossier stable, examen du dossier, calibrage et estimation | Fonctions au contrat écrit, tests en tableau | fait |
| C | Opus 5.5 | ce dépôt | 7 et 8 : proposition, mise en place, bureau commun, réparation, ligne de commande | Écritures atomiques sur plusieurs formats, réparation sans casser les adaptateurs | fait |
| D | Opus 5.5 | ce dépôt | 14, 9 puis 15 : le support de traitement, le plugin et les consignes de la discussion, le bureau ouvert au téléphone | Les consignes guident toute l'installation ; la sécurité du bureau ouvert ne laisse rien passer sans code | fait |
| E | Sonnet 5.5 | ce dépôt | 10, 17 puis 16 : l'organisation qui évolue, les lots par modèle, la vue 3D adaptée au mobile | Commandes, algorithme et vue au contrat écrit, tests nommés, vue vérifiée au navigateur | fait |
| F | Opus 5.5 | ce dépôt | 11 : guides et relecture finale | Relecture finale contre la conception sur un modèle fort | fait |
| H | Sonnet 5.5 | ce dépôt | 18 puis 20 : le catalogue des partenaires, l'espace partenaire au bureau | Données et vue au contrat écrit (la tâche 20 s'appuie sur la forme du relevé donnée par le plan, pas sur le code de la 19) | fait |
| I | Opus 5.5 | ce dépôt | 19 puis 21 : connexions, quotas, règles, choix et usage ; les partenaires dans les consignes et l'installation | Clés secrètes jamais écrites ; consignes qui guident l'orchestrateur | à faire |
| Essais réels | Opus 5.5 | ce dépôt (projets copiés hors dépôt) | 12 : le vrai passage sur un projet vide et un projet existant, téléphone compris, mené avec l'utilisateur | Diagnostic d'une installation réelle sur un modèle fort | à faire, **après la fin de toute l'implémentation** (le bureau partenaire, à concevoir, vient avant) |
| G | Opus 5.5 | dépôt du projet pilote | 13 : le projet pilote rejoint le nouveau rangement | Dernier mot sur « rien n'est perdu » | à faire, après les essais réels |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. Haiku n'est retenu pour aucune phase : chacune demande de lire une conception et de tenir des tests. **Fable n'est utilisé dans aucune phase**, ni pour exécuter, ni pour relire.

Notes laissées par les phases précédentes (écarts au plan, choix faits, points à surveiller) :

Phase A (Sonnet 5.5) :

- Les tâches 1 à 3 sont dans un seul commit (les mêmes fichiers, dont les consignes, sont modifiés par plusieurs tâches).
- `releve.developper` n'accepte que `~/` et `~\` en début d'argument ; le même test vaut pour `factory.lire` (`~x` et `a~b` restent relatifs). Tout passe par `releve._executer`, donc le relevé, les actions, le catalogue et la demande en profitent sans autre changement.
- `depart.agent_libre` : la limite ne compte que les tâches actives tenues par une fiche de lieu `local` ; avec `lieu` non précisé, un agent cloud libre reste rendu quand les locaux sont retenus. La raison « limite de {n} agents locaux atteinte » n'apparaît que si un agent local aurait été rendu sans la limite.
- Relevé : `agents_locaux_max` est un champ de racine de la version 4 ; `libelleCharge(c, agentsLocauxMax)` (`bureau/web/ui/texte.js`) ajoute « {n} agents locaux au plus » à la bulle ; documenté dans `docs/releve.md` et `docs/orchestrateur.md`.
- `test_echec_du_push_defait_tout` est remplacé par `test_push_refuse_garde_le_commit_local` ; `test_echec_du_commit_defait_tout` garde l'ancienne garantie pour les autres échecs.

Phase B (Sonnet 5.5) :

- Les tâches 4 à 6 sont dans un seul commit. Le paquet `installation/` contient `dossier.py`, `examen.py`, `calibrage.py`, `estimation.py` (la phase C ajoute `proposition.py`, `mise_en_place.py`, `outil.py`).
- `dossier.Echec` est l'exception de refus de tout le paquet : la phase C la réutilise (`from installation.dossier import Echec`). `preparer` rend aussi l'action `deja_lie` quand `lier` désigne déjà la cible du dossier stable ; sinon, avec `lier` et un dossier stable déjà dépôt git, le `pull` passe d'abord.
- `examiner` rend en plus la clé `factory` (booléen) ; `nb_fichiers` vaut `"100000+"` au-delà de la borne ; `extensions` est une liste de `[extension, nombre]`.
- `calibrer` : mesure indisponible → `charge_max` reste celui du `conseiller` ; avec historique, `agents_locaux_max` = `floor((85 - repos) / par_agent)` borné à 1..6 (6 si `par_agent` est nul).
- `estimer` lève `ValueError` si un rôle du flux n'a pas d'agent (la proposition le refuse avant). `usages_du_genre` lit le genre de chaque projet du bureau par la clé `orchestrateur` de ses réglages ; un projet illisible est ignoré. Les euros comptent `PART_SORTIE` en sortie et ignorent les caches.

Phase C (Opus 5.5) :

- Deux commits (tâche 7, tâche 8). Aides de test communes dans `tests/inst_aide.py` (`AvecMaison`, `proposition_valide`, `instantane`).
- `proposition.verifier_organisation(services, flux, agents, briefs, cloud, roles_deja_pourvus, cles_prises, briefs_existants)` est la partie « organisation » du contrôle, réutilisable telle quelle par la tâche 10. Les ids de services, d'étapes, de rôles et de clés d'agents suivent `MOTIF_ID` (ils deviennent des noms de fichiers) ; `prenom`, `specialite`, `nom`, chaque contrôle et chaque mot interdit tiennent sur une ligne. Un service `facturation` déclaré à la main est refusé dans les deux cas (vrai : la mise en place l'ajoute ; faux : pas de pièce).
- `mise_en_place.appliquer(p, maintenant, git=executer_git)` : `git` en plus (pour `creer_genre`). Un genre ni connu ni décrit par `genre_nouveau` est refusé avant toute écriture. Le nouveau genre est créé **en dernier**, après la mise en place (il publie hors du projet) ; s'il échoue, le genre reste nul et le rendu porte `genre_raison`. Un `.factory/` sans `factory.json` est refusé (configuration faite à la main : `docs/orchestrateur.md`). `agents_cloud[].environnement` est une liste ; vide = environnement de base.
- `ecrire_organisation` refuse sans rien écrire (clé ou fichier de fiche déjà pris, rôle sans agent ni fiche existante, brief manquant, Fable) ; un brief existant est gardé, jamais réécrit ; `justification` n'entre pas dans le fichier de factory.
- La vérification se fait en processus (`mise_en_place.verifier`, qui joue `verifier_interface.verifier_lecture`) ; chaque commande reste un sous-processus de `outil.py`, d'où environ 1 s par test de mise en place.
- `reparer` rend aussi `relancer_bureau`. Il contrôle le bureau avant d'écrire, ne crée que les dossiers manquants situés dans le projet (fiches, pièces, racines des réglages), et ne touche ni `commandes` ni un catalogue `{fichier}`.
- `installation/outil.py proposer` **recalcule** l'estimation avec `estimer` (les usages du genre et les prix du bureau commun) et l'enregistre à la place de celle reçue. Le fichier de proposition s'appelle `<nom du dossier>-<empreinte du chemin>.json`. Un refus de `proposer` rend `{"erreur", "erreurs": [...]}` ; une entrée JSON illisible rend le code 2 avec `{"erreur"}`. `reparer` ajoute `calibrage` à sa sortie.
- Pour la phase D : `git init` et `gh repo create` restent dans les consignes de la discussion (aucune commande de l'outil ne les fait).

Phase D (Opus 5.5) :

- Trois commits (tâches 14, 9, 15). `claude plugin validate` n'existe pas sur la machine : non passé (à faire en phase F, au vrai passage).
- Tâche 14 : `supports` et `acces` sont **obligatoires** dans une proposition (`proposition.verifier_supports`). `appliquer(p, maintenant, git, adresses=installation.acces.adresses)` et `reparer(projet, calibrage, acces=None, adresses=...)` : `adresses` est injectable (les tests ne lancent jamais `tailscale`). Le rendu porte toujours `acces` (adresses des accès ouverts, `null` sinon). `relancer_bureau` = le bureau existait avant **et** (projet ajouté ou accès nouvellement ouvert). `mise_en_place.ouvrir_acces(bureau_json, acces) -> [accès ouverts]` fusionne. La réparation reçoit les accès par `outil.py reparer <dossier> [--tailscale] [--reseau-local]` (la proposition n'existe plus à ce moment). `bureau.reglages.lire_acces` et `ACCES` sont réutilisés par le serveur.
- Tâche 9 : dans `SKILL.md`, **OUTIL** désigne le chemin absolu rendu par `preparer` (`skill`), pas `~/MyIAFactory/...` : PowerShell ne développe pas `~` dans les arguments d'un programme. Le propriétaire de la place de marché est « MyIAFactory » (pas de nom de personne). 1 732 mots. `test_plugin` exige que **chaque** commande de `installation/outil.py` soit citée : une commande ajoutée (tâche 10) doit l'être aussi.
- Tâche 15 : `serveur.creer(..., adresses=None, port_distant=None, cles=None)` ; `Bureau.ouvrir_distants`, `Bureau.infos_acces`, classe `Ecouteur` (même `Handler`, délègue au `Bureau`), `srv.annonces` affichées au lancement. `GET /api/acces` sans accès ouvert rend `{"adresses": [], "code": null, "expire": null}` ; `POST /api/acces/revoquer` exige `X-Bureau: 1`. `bureau/acces.py` : 20 échanges ratés annulent les codes en attente (`ESSAIS_MAX`), 20 codes en attente au plus. `vendor/qrcode.js` = qrcode-generator 1.4.4 (npm) tel quel plus une ligne `export default qrcode;`.
- Pour la phase E (tâche 16) : à 800 px de large, la barre déborde déjà (la charge et « Associer un téléphone » sortent de l'écran) ; la barre compacte doit les garder accessibles. Le bouton « Associer un téléphone » n'apparaît jamais sur le téléphone (`/api/acces` y répond 404).
- Essai réel : bureau de démo ouvert sur l'adresse Tailscale et l'adresse Wi-Fi de la machine, panneau et QR codes vérifiés au navigateur, 401 sans code vérifié depuis la machine ; liens d'association donnés à l'utilisateur pour un essai au téléphone (le geste complet au téléphone reste à la tâche 12).

Phase E (Sonnet 5.5) :

- Trois commits (tâches 10, 17, 16). La vue mobile n'a **pas** été vérifiée dans un navigateur (consigne de la session : l'utilisateur suit depuis son téléphone) : tests node de la logique, `node --check` de chaque module, et contrôle HTTP du bureau de démo (33 modules importés servis, manifeste, icône, règles CSS mobiles). **L'essai réel au téléphone reste à faire à la tâche 12** : toucher une pièce, pincer, glisser, valider une décision du Directeur, envoyer une photo, ajouter à l'écran d'accueil.
- Tâche 10 : `proposition.verifier_organisation` est réutilisée par `cmd_decision` (rôles déjà pourvus, clés prises, briefs existants lus dans le projet) ; la décision garde `organisation` normalisée. `lancer organisation` ne sait faire qu'`appliquer` ; **refuser** = `lancer decision` `lever` (dit dans les consignes). Au bureau, la décision est rendue par `bureau/web/ui/organisation.js` (branchée dans `decisions.js`, pas dans `directeur.js` comme le plan le disait). `verifier_interface --complet` joue le scénario `organisation` sur une copie ; il est « ignoré » si l'organisation actuelle du projet ne passe pas son propre contrôle (rôle du flux sans agent ni brief).
- Tâche 17 : `lancer lots` rend aussi `tailles` et `ecartees` (tâche sans rôle ou sans fiche pour son rôle). Une tâche est « partie » si elle est active, dans `fait` ou a déjà un `debut` ; `lancer lots` avec `taches` nommant une tâche partie est refusé, avec `{}` elle est ignorée. Les lots sont numérotés après le plus grand `L<n>` déjà noté sur une tâche. `lots.taille_conseillee` attend des usages portant `lot` et `rang` (l'outil joint le rang depuis la tâche) ; un rang sans mesure ne coupe pas ; une tâche faite seule = un usage sans `lot`. `lots.mode_repartition` dit `temps` (toutes les durées positives) ou `egal`. Usage d'un lot : `lancer usage` avec `lot` rend `{"ids": [...], "reparti"}` et refuse un lot déjà noté ; avec `tache`, `lot` et `id` cumulatif, les cumuls sont gardés dans `usage_cumuls` du suivi. `depart` avec `taches` : `depart.message_lot`. Le bureau marque « estimé (part d'un lot) » (`facturation.js`) ; `bureau/usage.py` garde `lot` et `reparti` seulement quand ils existent.
- Tâche 16 : `ui/gestes.js` (nouveau) tient le glisser et le pincer au doigt (jamais à la souris) ; `scene.js` gagne `zoom`, `zoomer`, `deplacer` (le zoom se fait vers le centre, pas vers les doigts). La classe `mobile` est posée sur `<html>` par `main.js` (`estMobile`) : barre qui défile, panneaux plein écran, « Fermer ». Sur mobile : ombres coupées, définition à 1,5 ×. La barre défile aussi sous 900 px sur ordinateur (le débordement relevé en phase D). Photos : `preparerImage` réduit et réencode (PNG gardé, le reste en JPEG, sous 5 Mo) ; un HEIC que le navigateur ne sait pas décoder donne un message clair. `<link rel="manifest" crossorigin="use-credentials">` : sans cela le manifeste serait refusé par l'écouteur distant (cookie d'accès). L'icône est un PNG 512 px généré, sans lien avec un projet.

Phase F (Opus 5.5), tâche 11 :

- Guides : `docs/installation.md` commence par « Installer MyIAFactory sur un projet » (plugin, commande, dossier stable, bureau commun lancé par `$HOME/MyIAFactory/...`, qui marche dans PowerShell comme dans bash) ; « Brancher son projet » suit la règle de versionnement ; nouvelle section « Le bureau sur le téléphone ». `docs/orchestrateur.md` « Démarrer un projet neuf » renvoie à la commande. Tests : `tests/test_plugin.py` `TestGuides`.
- Relecture indépendante (Opus) : aucun bloquant. Corrigé, chacun avec son test :
  - lots : une tâche notée dans un lot est « partie » (`_partie`), un lot parti n'est jamais refait ; une dépendance partie mais pas finie écarte la tâche (et ce qui l'attend) avec « attend la fin de la tâche … » ; une chaîne d'un même modèle (a → b → c) forme **un** lot (une dépendance placée plus tôt dans le lot courant compte) ;
  - lot : `depart.compte_rendu_par_tache(cle)` : l'orchestrateur marque la première tâche, l'agent rend chacune et marque aussitôt la suivante (`active: true`) : chaque tâche a sa durée, la répartition au temps s'applique ;
  - `message_orchestrateur` donne la skill en chemin absolu (« `<skill>` vaut … ») ; `consignes.md` le dit ;
  - la vérification de `appliquer`/`reparer` ajoute la ligne « le bureau lit le relevé du projet » : elle lance la commande du relevé **déclarée** (`bureau.releve.obtenir`). Les tests de mise en place lient le dossier stable à ce dépôt par une jonction créée dans `Base.appliquer` (seulement si le test n'a pas sa propre skill ; jamais avant, car certains tests écrivent dans la mémoire de la skill) ;
  - **`python` ou `python3` en premier mot d'une commande du bureau = le Python du bureau** (`releve.commande_python`) : sur la machine de l'auteur, `python` est un Python 3.9 ;
  - `preparer --lier` refuse si `~/MyIAFactory/skill` existe déjà et pointe ailleurs ; la mise à jour se fait par `pull --rebase` (puis `rebase --abort` en cas d'échec) ;
  - estimation : les usages mesurés sont chiffrés compteur par compteur (cache au prix de cache de la source, sinon 0,1 × et 1,25 × le prix d'entrée) ;
  - examen : tout `.factory/` sans `factory.json` donne `factory_propre` ; `inventaire.tronque` et `nb_fichiers` « n+ » au délai ; horloge injectable ;
  - `.gitignore` : toute variante de règle qui ignore `.factory/` entier est retirée ; l'adresse Tailscale doit être dans `100.64.0.0/10` ; une organisation ne retire jamais un service qui a encore des agents ;
  - `SKILL.md` : questions fermées groupées en un message, genre et mots interdits dans un second.
- **Le vrai passage (tâche 12) est reporté** à la demande de l'utilisateur : toute l'implémentation se termine d'abord (le bureau partenaire, à concevoir, vient avant), puis la phase « Essais réels » (Opus, tâche 12), puis la phase G. Les messages à coller sont adaptés. Pour les essais : faire `preparer --lier <ce dépôt>` **avant** le premier `/myiafactory:installer` (sinon la commande clone le dépôt public dans `~/MyIAFactory/skill` et `--lier` est ensuite refusé) ; `${CLAUDE_PLUGIN_ROOT}` dans `SKILL.md` et `claude plugin validate` restent à vérifier en vrai ; l'essai au téléphone (toucher, pincer, glisser, décision du Directeur, photo, écran d'accueil) aussi.
- Laissé tel quel (mineur, noté) : le délai de l'examen n'est vérifié qu'entre deux entrées (un `scandir` énorme passe d'abord) ; 20 échanges ratés annulent les codes (gêne possible sur un Wi-Fi partagé, aucune fuite) ; une adresse Wi-Fi privée d'un réseau public n'est pas signalée au lancement.

Phase H (Sonnet 5.5), tâches 18 et 20 :

- Deux commits (tâche 18, tâche 20). Aucune connexion, aucun quota, aucune règle n'existe encore côté outil : c'est la tâche 19 (phase I).
- Tâche 18 : `partenaires/catalogue.json` = **174 entrées** (toutes les lignes de la recherche, fermés et sans API compris ; Cloudflare R2 et Cloudflare Pages/Workers sont deux entrées, comme dans la recherche), `verifie_le: "2026-11-11"`. `site`, `inscription` et les URL de connexion ont été relevés par six agents Sonnet sur les sites des partenaires (au plus deux pages chacun) ; **un lien non trouvé reste `null`** (seules 51 entrées ont un lien d'inscription). Les commandes `claude mcp add` sont celles des documentations, vérifiées sans en-tête ni clé ; une adresse MCP n'est gardée que si la doc la donne comme telle. `connexions[].variables` : le nom lu dans la doc officielle, sinon celui supposé de la recherche (à revérifier par « Mettre à jour les offres »). `catalogue.verifier` exige `https://` pour toute URL, `lecteur` seulement avec `quota_lisible: "oui"` ; `catalogue.lire()` lit le fichier du paquet. Les `lecteur` posés sont exactement ceux de `quota.LECTEURS` de la tâche 19 : `elevenlabs`, `bfl`, `stability`, `leonardo`, `meshy`, `removebg`, `deepl`, `kiri`. Les banques de médias (limites dans les en-têtes) ont `quota_lisible: "oui"` sans `lecteur`. Les générateurs de la recherche ne sont pas dans le dépôt (le catalogue est le livrable).
- Tâche 20 : forme du champ `partenaires` du relevé, **documentée dans `docs/releve.md`** (fin du fichier) et contrôlée par `releve._verifier_partenaires` (ids de `etat` et `conseils` = ceux de `categories` ; dates ISO ; `etat` des connexions ∈ `connecte` / `declare` / `non_connecte`). Ajouts au contrat du plan : `cout_maj: {euros, texte}` (le coût estimé que la fenêtre de confirmation de « Mettre à jour les offres » montre ; `null` → « coût estimé inconnu »), et pour la facturation `partenaires` dans la réponse de `/api/facturation` : `{id: {nom, total (euros), origine: [{montant, devise}], estime, non_chiffre, usages}}`. **La tâche 19 doit remplir `cout_maj` dans `construire_releve` et ce bloc dans `bureau/cout.py`.** `etat.py` rend `partenaires` tel quel (v4 seulement) ; la facturation lit `donnees.partenaires` (un coût absent = « non chiffré », jamais 0).
- Demandes (`bureau/demandes.py`) : `partenaire_regle` (`partenaire` connu du catalogue reçu ; `operation` ; `id` d'une règle existante pour modifier/supprimer ; `texte` ≤ 500), `partenaires_actualiser`, `partenaires_maj` (`confirme: true` strict). Toutes refusées sans `partenaires` dans le relevé. `orchestrateur/consignes.md` ne gagne qu'une ligne de tableau (les trois demandes sont « pas encore prises en charge », exigée par `test_consignes_couvrent_le_parcours`) : **la tâche 21 la remplace par la section « Les partenaires »**. Le démo (`exemples/demo/actions.py`) ne traite pas ces demandes (il ne traite pas non plus `organisation`).
- Vue : `ui/partenaires.js` (pièce « Partenaires » ajoutée par `creerPlan(services, colonnes, {partenaires: true})` à la rangée du bas, après le café ; panneau `partenaires` dans `panneaux.js`, plein écran sur mobile comme les autres). Cartes repliées par défaut (le catalogue en compte 174) : le résumé montre connexion, quota avec date, limite, « prix à vérifier » (fiabilité tierce) ; le détail (plans, liens `https` seulement, commande MCP et « Copier », variables, règles) s'ouvre au clic. « Mettre à jour les offres » ouvre une confirmation en page (pas `window.confirm`) avant la demande. `main.js` recharge la page quand la présence de l'espace partenaire change.
- Vérifié : tests Python et node verts ; requêtes HTTP sur un bureau de démo portant `partenaires` (état, modules servis, demandes acceptées/refusées). **Pas vérifié au navigateur** (consigne de la session) : le rendu visuel de la pièce « Partenaires » et du panneau reste à voir au vrai passage.

## Ce que chaque conversation doit savoir

**Le cadre**

- Dossier de travail : la racine de ce dépôt (phases A à G). Dépôt GitHub public `maximus49000/MyIAFactory`, branche `main`.
- La conception et le plan sont **validés par l'utilisateur**. Il ne faut ni reposer les questions de cadrage ni refaire un plan : on exécute. La conversation réalise elle-même les tâches de sa phase, dans l'ordre (skill `superpowers:executing-plans`).
- Lire d'abord, en entier : la conception `docs/superpowers/specs/2026-11-11-installation-sur-un-projet-design.md`, le plan `docs/superpowers/plans/2026-11-11-installation-sur-un-projet.md`, et ce fichier. Les sections « Global Constraints » et « Review Focus » du plan valent pour toutes les tâches.

**Les règles à ne pas oublier**

- Dépôt public et vide de tout projet : rien de propre à un projet réel, rien de privé. Le projet pilote n'est jamais nommé ici, ni dans le code, ni dans les mémoires, ni dans les commits.
- Contre-buts 1 et 2 de la conception : une installation ou un workflow plus coûteux en tokens que la gestion autonome d'un néophyte, ou des fonctionnalités à côté de la demande, sont des échecs même si tout « marche ».
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"`.
- Aucun test ne sort sur Internet ni ne touche le vrai dossier de l'utilisateur (`HOME` et `USERPROFILE` temporaires, git simulé ou dépôts temporaires locaux).
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer. Puis cocher la tâche dans le `README.md`, commit en français terminé par `Co-Authored-By: Claude <modèle de la conversation> <noreply@anthropic.com>`, et `git push`.
- Ne jamais annoncer qu'une tâche est finie sans avoir lancé les tests et lu leur sortie. Si un test échoue ou si une tâche ne peut pas être faite comme prévu, le dire avec la sortie, ne pas contourner. Deux tests connus pour tomber parfois sous charge (`test_json_tres_imbrique`, `test_ecritures_concurrentes`) : relancer seuls, noter s'ils retombent.
- Une phase enchaîne toutes ses tâches d'une traite, dans l'ordre de la table ci-dessus, sans s'arrêter entre elles.
- Un écart au plan (signature changée, fichier en plus) est permis s'il est nécessaire : le noter ci-dessus dans « Notes laissées », car la phase suivante ne lit que le plan et ce fichier.
- Répondre à l'utilisateur en français.

**Ce qui demande l'utilisateur**

- Phase « Essais réels » : il choisit le petit projet existant à copier, lance la commande, mène les deux discussions, installe Tailscale sur l'ordinateur et le téléphone, et associe son téléphone.
- Phase G : il ouvre la conversation sur le dépôt privé, et valide les corrections de la réparation.
- En dehors de ces moments, ne pas s'arrêter pour demander : enchaîner les tâches de la phase.

**La fin d'une phase**

1. Tous les tests passent (les deux commandes), sortie lue.
2. Mettre à jour « Où on en est » : la phase passe à « fait », et les notes pour la suivante sont écrites.
3. Dernier commit et push.
4. Dire à l'utilisateur, en clair : ce qui a été fait, ce qui n'a pas pu l'être, **quelle est la prochaine phase**, avec quel modèle, **dans quel dossier** l'ouvrir, et le message à coller pour la lancer (ci-dessous). Puis s'arrêter : ne pas entamer la phase suivante.

## Les messages à coller

Un message par conversation. L'utilisateur crée la conversation dans le dossier indiqué, choisit le modèle, colle le message.

**Phase A — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase A de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 1 à 3 du plan sans t'arrêter, puis fais la fin de phase décrite dans la passation.

**Phase B — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase B de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 4 à 6 du plan, puis fais la fin de phase décrite dans la passation.

**Phase C — Opus 5.5 — dans ce dépôt**

> Réalise la phase C de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 7 et 8 du plan, puis fais la fin de phase décrite dans la passation.

**Phase D — Opus 5.5 — dans ce dépôt**

> Réalise la phase D de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 14, 9 puis 15 du plan. Les consignes de la discussion (tâche 9) suivent la conception à la lettre et restent sobres (2 000 mots au plus). Termine par la fin de phase.

**Phase E — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase E de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 10, 17 puis 16 du plan ; vérifie la vue mobile dans le navigateur. Termine par la fin de phase.

**Phase F — Opus 5.5 — dans ce dépôt** (faite)

> Réalise la phase F de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 11 : guides, puis relecture de tout le projet 4 contre la conception et le plan par un relecteur indépendant sur Opus (jamais Fable), puis tes corrections. Termine par la fin de phase.

**Phase H — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase H de l'installation sur un projet (le bureau partenaire). Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : les conceptions et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 18 puis 20 du plan. N'utilise pas le panneau navigateur de l'app (l'utilisateur suit souvent depuis son téléphone) : vérifie par les tests et par des requêtes HTTP. Termine par la fin de phase, sans lancer la suivante.

**Phase I — Opus 5.5 — dans ce dépôt**

> Réalise la phase I de l'installation sur un projet (le bureau partenaire). Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : les conceptions et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 19 puis 21 du plan ; aucune valeur de clé ne doit jamais être écrite, affichée ni journalisée. Termine par la fin de phase, sans lancer la suivante.

**Phase « Essais réels » — Opus 5.5 — dans ce dépôt** (après la fin de toute l'implémentation, bureau partenaire compris)

> Réalise la phase « Essais réels » de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 12, avec moi : commence par `installation/outil.py preparer --lier <ce dépôt>` (sur ma machine, le dossier stable est cette copie de développement), puis prépare hors du dépôt un dossier vide et la copie du petit projet que je te désignerai, dis-moi comment ajouter le plugin depuis ce dépôt, guide-moi pas à pas, y compris pour associer mon téléphone, et corrige ici, avec un test, chaque écart générique. Termine par la fin de phase ; la prochaine phase à annoncer est la phase G, dans le dépôt privé du projet pilote.

**Phase G — Opus 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase G de l'installation sur un projet de MyIAFactory, pour ce projet. Le dépôt de la skill MyIAFactory est sur cette machine (demande-moi son chemin si tu ne le trouves pas) : lis-y `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md`, la conception et le plan (tâche 13) ; tout est validé, rien à recadrer. Vérifie que le dossier stable pointe sur ce dépôt de la skill (`preparer --lier`, fait aux essais réels ; s'il refuse parce qu'une autre copie existe, dis-le-moi), lance la réparation sur ce projet et montre-moi chaque correction, vérifie que ses adaptateurs n'ont pas bougé, fais-lui rejoindre le bureau commun, repasse la liste de compatibilité ligne par ligne, puis `git grep -i` des mots interdits de ce projet dans le dépôt de la skill (aucun résultat attendu). Enfin, dans le dépôt de la skill seulement, mets à jour le `README.md` et cette passation en une phrase générique (« projet 4 terminé, vérifié sur le projet pilote »), sans aucun nom, commit et push.
