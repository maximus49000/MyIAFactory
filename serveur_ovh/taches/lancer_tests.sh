#!/usr/bin/env bash
# Enveloppe HÔTE d'une campagne de tests : exécutée sur le serveur par UNE session SSH du poste, elle reste au premier plan
# du début à la fin (place, conteneur, sortie en direct, nettoyage) ; l'entrée standard de la session sert de laisse.
# Usage : lancer_tests.sh <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps> [<travail_go> [<image> [<famille>
#         [<echauffement> [<reseau_code> [<budget_caches_go> [<budget_unites> [<executeur> [<licence> [<hotes_licence>
#         [<version_hote>]]]]]]]]]]]]
#   POSITIONS (tâche 14g, fixées après relecture de l'état livré en 14e) : executeur = 15e, licence = 16e, hotes_licence = 17e ;
#   version_hote = 18e (tâche 14h).
#   executeur (15e) ^(conteneur|hote_bac_a_sable)$, défaut conteneur : qui exécute la commande. Les fonctions
#   executeur_<nom>_lancer / executeur_<nom>_arreter sont les SEULES différences ; places, jetons, file, laisse, timeout, coupe
#   à 50 Mo, préfixe `| `, `#fin` et nettoyage sont communs. hote_bac_a_sable (option A, § 5.16, tâche 14h ; famille unity
#   seulement) : `sudo -n /usr/local/lib/myiafactory/unity-bac-a-sable.sh lancer <id> <cpus> <memoire_mo> <duree_s> <version>
#   <reseau>` (unité systemd confinée sous l'utilisateur unity-tests ; voir ce script), entrée = la commande puis l'instantané ;
#   arrêt : `… arreter <id>`. reseau = licence pour B3 (le mandataire de la campagne, ouvert ici), aucun sinon (B1 et B2 :
#   l'hôte EST la machine de la licence). Aucune image Docker n'est demandée. Son code 77 (prérequis absent sur l'hôte :
#   utilisateur, éditeur, licence, scripts ; rien n'a tourné) devient un refus (#refus 77) : la commande de l'unité ne rend
#   jamais 77.
#   version_hote (18e) « - » (défaut : la version du projet, celle de l'image ^myiafactory/tests-unity-<v>$) ou une version Unity
#   (même motif), avec hote_bac_a_sable seulement : la version de repli décidée par le Directeur (tests.profil_force.
#   unity_version_hote) ; différente de celle du projet, la sortie commence par « Éditeur <v> au lieu de <v projet> : résultats
#   indicatifs ».
#   licence (16e) ^(-|B1|B2|B3)$, défaut « - » : exigée (≠ -) pour la famille unity, refusée pour toute autre famille. Montages
#   de la table FERMÉE ci-dessous (jamais une valeur du poste, jamais unityhub, jamais une socket, jamais ~/.config/unity3d
#   entier), en lecture seule ; au moins l'un des deux doit exister (sinon 77, aucun conteneur) :
#     $HOME/.config/unity3d/Unity/licenses -> /licence/droits:ro (licence par droits, celle de Hub)
#     $HOME/.local/share/unity3d/Unity/Unity_lic.ulf -> /licence/ulf:ro (licence manuelle, s'il existe)
#   B1 : ces fichiers seuls, --network none. B2 : B1 + /etc/machine-id:/etc/machine-id:ro et --hostname de l'hôte (identifiants de
#   machine, aucun secret ; /etc/machine-id absent : 77). B3 : B2 + réseau --internal deps-<id> et le mandataire éphémère (§ 5.13)
#   vers les seuls hôtes de hotes_licence. CONTRAIRE À --network none : la route ne l'envoie qu'avec
#   tests.adoption.reseau_licence == "accorde" (décision du Directeur, QU1). Le contenu de la licence n'est jamais lu ici.
#   hotes_licence (17e) : « - » (défaut), ou pour B3 seulement 1 à 8 noms d'hôtes séparés par des virgules, chacun
#   ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$ (aucune quote, `$`, espace, tiret initial),
#   dernier libellé alphabétique (jamais une adresse IP), et égal à un suffixe de la table FERMÉE SUFFIXES_LICENCE ou dessous ;
#   B3 sans liste, ou liste sans B3 : 2. ÉCART AU BRIEF : il annonçait deux arguments ; la liste des hôtes de B3, « passée par le
#   poste », en demande un troisième.
#   Famille unity : image ^myiafactory/tests-unity-<version Unity>$ (et seulement pour elle), /tmp tmpfs 6 Go, variable
#   MYIAFACTORY_TESTS_FAMILLE=unity (entree-tests.sh passe alors la main à entree-unity.sh, qui copie la licence sur le tmpfs,
#   garde le journal de l'éditeur dans /tmp et ne relaie qu'un résumé filtré ; codes 81 licence refusée, 82 aucun test).
#   id t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; places 1..4 ; cpus 1..64 ; memoire_mo 256..65536 ; duree_s 1..3600 (nombres sans zéro
#   initial) ; projet ^[a-z0-9][a-z0-9-]{0,39}$ ; deps 16 hexa (empreinte du cache, tests_profil.empreinte_deps) ou « - » ;
#   echauffement (11e) : clé de la table FERMÉE ECH (npm, pip, gradle…), par défaut celle de la famille (ECH_DEFAUT) ;
#   reseau_code (12e) accorde|refuse (défaut refuse) : l'accord du Directeur pour le réseau d'un échauffement qui exécute du
#   code du projet (posé par la route d'après tests.adoption) ; budget_caches_go (13e) 1..1000, défaut 40 (Q5) ;
#   budget_unites (14e, tâche 14e) ^([4-9]|1[0-9]|20)$, défaut 16 : le budget mémoire des tests du serveur, en jetons de 2 Go.
# JETONS DE MÉMOIRE (conception § 5.5 et § 5.14) : ~/taches/.jeton-tests-1..20 (flock -n, un descripteur chacun, comme la place) ;
#   une campagne en veut ceil(memoire_mo / 2048) EN PLUS de sa place ; jamais plus de budget_unites tenus en tout (les jetons
#   tenus par d'autres comptent, même au-delà du budget : abaisser le budget n'expulse personne). Seul le PREMIER ticket de la
#   file en prend, un par un, et les garde jusqu'à en avoir assez (puis prend sa place) : pas d'interblocage, pas de famine ; un
#   ticket qui cesse d'être le premier (un plus ancien arrive après coup) rend les siens. Un poids au-delà du budget est refusé
#   (code 2) : il attendrait pour toujours. Rendus avec la place (fin, laisse coupée, panne : le verrou meurt avec la session).
#   RÉSIDUEL CONNU : les jetons ne sont pas refermés dans les fils (comme la place, descripteur 8, seuls les appels docker
#   brefs le font) : si l'enveloppe était tuée net, le conteneur (docker run) les garderait jusqu'à ce que le surveillant le tue.
# DÉPENDANCES (conception § 5.13, tâche 14d et sa relecture), quand deps ≠ « - » : cache ~/tests/.deps/<projet>/<clé>-<deps>/
#   (contenu/ = ce que l'outil a produit, .pret, .utilise, .verrou-produit et .non-verrouille éventuels) ; son verrou est HORS
#   du dossier : <projet>/.<clé>-<deps>.verrou. Absent (ou « non verrouillé » et .pret de plus de 7 jours) : ÉCHAUFFEMENT avant
#   la file, sous flock -x <projet>/.<clé>-<deps>.echauffement, sur une des 2 places ~/taches/.echauffement-N (#attente sinon),
#   sauf échec retenu de moins d'une heure (<projet>/<clé>-<deps>.echec : repli immédiat, même raison) : conteneur deps-<id>
#   (même image, mêmes durcissements que les tests, aucun secret, /work en tmpfs borné, durée, taille et inodes de la table
#   ECH), TOUJOURS sur un réseau Docker --internal deps-<id> sans DNS (--dns 0.0.0.0), avec pour seule sortie le mandataire
#   éphémère mandataire-<id> (tests_hote.py --mandataire : CONNECT :443 vers la liste fermée ECH_HOTES, écoute sur le réseau
#   interne seulement), joint par --add-host ; une clé qui exécute du code du projet exige en plus reseau_code=accorde.
#   Gradle : wrapper comparé aux sommes publiées de TOUTES les versions, distribution téléchargée par l'hôte (redirections
#   limitées à DIST_HOTES), vérifiée par son .sha256 officiel et copiée dans le cache. Le contenu s'écrit dans <cache>.tmp,
#   renommé et .pret posé après succès. Échec : ligne `#deps-echec <mot de RAISONS>`, code 79 (rien n'est prêt, <cache>.tmp
#   effacé). Pendant les tests : flock -s sur le verrou, volume `overlay` tests-deps-<id> (basse : contenu/ en lecture seule ;
#   haute : ~/tests/<id>/deps-haut, effacée avec le dossier), ESSAYÉ par un conteneur bref sans réseau, monté sur /deps ;
#   variables et drapeaux hors ligne de la table fermée (tests_hote.py --hors-ligne). Éviction après chaque usage : deux caches
#   au plus par projet et par clé, puis budget_caches_go, le moins récemment utilisé (.utilise) d'abord, jamais un cache tenu
#   (flock -x -n) ni celui de la campagne ; le cache est d'abord renommé .supprime-<ts>-<nom> (atomique), puis effacé.
#   gradle-android : SDK de l'hôte en copie sur écriture (volume overlay tests-sdk-<id>, essayé lui aussi : AGP peut y écrire
#   .temp, licences… sans jamais toucher ~/android-sdk), à défaut monté en lecture seule.
#   travail_go 1..200 (facultatif, 10 par défaut) : taille maximale de travail/ (l'arbre extrait et ce que les tests écrivent) ;
#   image (facultatif, 9e argument) ^myiafactory/tests(-[a-z0-9]{1,24})?$, défaut myiafactory/tests : l'image du catalogue (§ 5.12) ;
#   famille (facultatif, 10e) dans FAMILLES, défaut python : table FERMÉE de l'enveloppe qui ajoute montages et variables du
#   conteneur (gradle-android : SDK de l'hôte ~/android-sdk en copie sur écriture sur /opt/android-sdk, ANDROID_HOME,
#   GRADLE_OPTS, GRADLE_USER_HOME=/deps/gradle si un cache Gradle est monté, sinon /tmp/gradle ; gradle-jvm : sans le SDK). Jamais une valeur venue du poste hors de ces motifs : image et famille ne sont
#   que des clés, les montages et variables sont écrits ici. Sans ces deux arguments : le conteneur d'avant, à l'identique.
#   Chaque valeur est validée par un motif strict AVANT tout usage ; rien n'est jamais interprété par un shell (tableaux).
# Entrée standard : 1re ligne = la commande, tableau JSON de chaînes (4 096 octets au plus, contrôlé par tests_hote.py
#   --commande, la règle de entree-tests.sh) ; le reste = la laisse : un fils la lit jusqu'à la fin de fichier (session SSH
#   fermée, poste parti), pose la marque laisse-coupee, puis tue le conteneur (docker kill tests-<id>, répété tant que
#   l'enveloppe vit : un conteneur encore en création est tué aussi, par la laisse ou par le surveillant) ; code 130.
# Dossier ~/tests/<id>/ (déposé par le poste avant ; ~/tests, ~/tests/<id> et entree/ à nous, remis en 0700) :
#   entree/entree.tar (l'instantané, relu par tests_hote.py --archive avant docker : fichiers ordinaires USTAR seulement,
#   limites de l'instantané). ÉCART À LA CONCEPTION : elle disait ~/tests/<id>/entree.tar ; le brief (tâche 4) et ce script
#   disent ~/tests/<id>/entree/entree.tar (entree/ est monté seul, en lecture seule). Écrits par l'enveloppe :
#   entree/commande.json (0600), travail/ (0700, créé vide ; un travail/ déjà là = identifiant déjà utilisé, refusé),
#   enveloppe.pid et les marques privées de l'hôte (code, sortie-coupee, erreur-coupee, laisse-coupee, disque-plein,
#   inodes, travail-plein, echeance), jamais montées dans le conteneur.
# Sortie standard : celle du conteneur, séparateurs de lignes autres que \n réécrits (tests_hote.py --couper), coupée à
#   50 Mo (52 428 800 octets ; le reste est lu et jeté).
# Sortie d'erreur : `#attente <rang> <total> <jetons_libres>` pendant la file (à chaque changement, rappel toutes les 30 s) ; la sortie
#   d'erreur du conteneur préfixée `| ` à chaque ligne (\r devenu \n, \x0b \x0c \x1c-\x1e U+0085 U+2028 U+2029 écrits en
#   texte ; coupée à 50 Mo) ; les messages de l'enveloppe (« lancer_tests : … ») ; puis, SEULEMENT pour un code produit par
#   l'enveloppe elle-même, la ligne `#refus <code>` ; et TOUJOURS en dernière ligne
#   `#fin <code> <debut_epoch> <fin_epoch> <attente_s>` (debut = départ du conteneur, ou de l'enveloppe s'il n'est pas parti).
# CONTRAT DU POSTE : couper la sortie d'erreur sur b"\n" SEULEMENT ; ne croire que la DERNIÈRE ligne (`#fin`) ; un code
#   d'origine enveloppe (refus, panne, laisse, limite) n'est cru que si la ligne non vide qui précède `#fin` est exactement
#   `#refus <même code>`. Un code du conteneur (même 76, 77, 124 ou 130) n'a jamais de `#refus` : aucune ligne du conteneur
#   ne peut commencer par `#`.
# Codes : celui du conteneur (la commande ; 2 commande invalide, 70 extraction : entree-tests.sh), sans `#refus` ; avec
#   `#refus` : 2 argument, commande, dossier ou entree.tar refusés, ou identifiant déjà utilisé (rien écrit, rien effacé) ;
#   70 instantané refusé par l'hôte (refus explicite du vérificateur, code 3) ; 74 campagne ARRÊTÉE EN COURS par
#   l'enveloppe (le conteneur a pu tourner : le poste ne la rejoue jamais) : disque libre < 2 Go, inodes libres < 5 %,
#   travail/ au-delà de travail_go, échéance du surveillant (duree_s + 30 s), ou état final inattendu (running,
#   restarting, paused, removing, created déjà démarré, docker inspect en panne : conteneur tué puis supprimé) ;
#   76 disque libre < 5 Go ou inodes libres < 5 % AU DÉPART (rien n'a tourné) ; 77 image absente, python3 absent ou en
#   panne, utilisateur du serveur autre que 1000 ; 78 cache des dépendances en lien ou pas à nous ; 79 échauffement des
#   dépendances impossible (ligne `#deps-echec <raison>` avant : réseau non accordé, wrapper Gradle modifié, échec, durée,
#   plafond, copie sur écriture refusée) ; 124 durée dépassée
#   (`timeout`) ; code de docker run (125-127…) quand le conteneur n'a JAMAIS démarré (absent, ou « created » avec
#   StartedAt à la date nulle) ; 130 laisse coupée ou signal ; 1 erreur de l'enveloppe. Après un refus 2, rien n'est
#   effacé ; après tout autre départ, ~/tests/<id> est effacé (sans chmod -R si l'arrêt du conteneur n'est pas confirmé),
#   le ticket retiré et la place libérée. `#refus` et `#fin` sont précédés d'un retour à la ligne (lignes vides ignorées
#   par le poste) ; `#fin` est la toute dernière écriture (les fils tués sont attendus avant, leurs avis jetés).
# File : ticket ~/tests/.file/<date +%s%N>-<id> (contenu : le PID de l'enveloppe, écrit par un temporaire puis mv) ; tour
#   quand aucun ticket vivant (processus_vivant : PID dont la ligne de commande porte lancer_tests.sh et l'identifiant) n'est
#   plus ancien ; les tickets morts sont effacés. Place : le premier `flock -n` libre parmi ~/taches/.creneau-tests-1..4
#   (descripteur 8), et seulement si moins de <places> verrous sont tenus (comme lancer_agent.sh).
# Balayage à chaque lancement, dans cet ordre : conteneurs étiquetés myiafactory.genre=tests dont l'enveloppe ne vit plus
#   -> supprimés (docker rm -f) ; PUIS ~/tests/t* de plus de 6 h sans enveloppe vivante et dont le conteneur tests-<id> est
#   confirmé absent -> effacés (sinon laissés, au balayage suivant). Pas d'échéance dans l'image (ce serait changer
#   l'empreinte) : la défense en profondeur reste le surveillant, la laisse et ce balayage.
# Surveillant (fils, pendant le conteneur, toutes les 0,5 s) : disque libre < 2 Go, inodes libres < 5 %, travail/ au-delà
#   de travail_go (du -sk en arrière-plan, sous timeout 60 et nice/ionice -c3, relancé 5 s après sa FIN), échéance duree_s + 30 s (si `timeout` n'a pas suffi : le client docker relaie
#   le TERM et attend), laisse coupée ou enveloppe disparue -> docker kill tests-<id>. Il est arrêté et attendu dès la
#   fin de docker run, AVANT la lecture de ses marques (une marque tardive ne change jamais un code rendu). RÉSIDUEL CONNU : ce sont des
#   sondages, pas des quotas ; entre deux sondages un test peut écrire en rafale (au plus ~0,5 s de débit disque, 5 s pour
#   travail/). Pas de --ulimit fsize : il casserait un gros artefact de construction légitime sans fermer la rafale
#   (plusieurs fichiers) ; le plafond passe par du et df.
# Conteneur : sans réseau, racine en lecture seule, aucune capacité, utilisateur 1000, pas de fichier core, journal Docker
#   désactivé (la sortie ne remplit pas le disque), seulement travail/ (/work), entree/ (lecture seule), le cache de
#   dépendances (copie sur écriture, /deps) et, pour gradle-android, le SDK (copie sur écriture) montés ; /tmp tmpfs 4 Go exécutable (nosuid, nodev par défaut) ; aucun secret, aucune variable de
#   l'appelant : -e HOME=/tmp et -e MYIAFACTORY_TESTS_CONTENEUR=1 seulement (famille unity : en plus les montages de licence
#   en lecture seule, -e MYIAFACTORY_TESTS_FAMILLE=unity, /tmp 6 Go, et pour B3 seulement le réseau interne du mandataire ;
#   voir executeur et licence plus haut). Sans --rm : l'enveloppe lit l'état final
#   (docker inspect) pour distinguer un code du conteneur d'une panne de docker, puis le supprime (docker rm -f).
# Réservées aux tests : ENVELOPPE_SONDE_S (période de la file et du surveillant, 0,5 s par défaut), ENVELOPPE_SORTIE_MAX_OCTETS,
#   ENVELOPPE_MARGE_S (marge de l'échéance du surveillant, 30 s), ENVELOPPE_DU_S (période de du, 5 s).
set -u
export LC_ALL=C
umask 077

T0=$(date +%s)
DEBUT=""; ATTENTE=0

fin_simple() { printf '\n#refus %s\n\n#fin %s %s %s 0\n' "$1" "$1" "$T0" "$(date +%s)" >&2; exit "$1"; }
refuser() { printf '%s\n' "lancer_tests : $1" >&2; fin_simple 2; }

ICI="$(cd "$(dirname "$0")" && pwd)"
. "$ICI/commun.sh" || refuser "commun.sh introuvable à côté de l'enveloppe."
AIDE="$ICI/tests_hote.py"
IMAGE="myiafactory/tests"
FAMILLES=" python node gradle-android gradle-jvm maven dotnet go rust godot unity ruby php make "   # miroir de tests_profil.FAMILLES
GRADLE_OPTS_FERME="-Dorg.gradle.daemon=false -Dorg.gradle.vfs.watch=false -Dorg.gradle.offline=true -Dkotlin.compiler.execution.strategy=in-process -Dorg.gradle.project.android.builder.sdkDownload=false"
# Table FERMÉE des échauffements (miroir de outils/tests_profil.py:ECHAUFFEMENTS, vérifié par test) : "durée_s plafond_go
# exécute_du_code". La commande elle-même est dans tests_hote.py (plan_echauffement), jamais venue du poste. exécute_du_code
# = la restauration PEUT exécuter du code choisi par le projet (scripts Gradle/Maven, .props/.targets de dotnet,
# .cargo/config.toml de cargo, yarnPath et extensions de Yarn Berry, sdist de pip) : seulement avec l'accord (reseau_code).
declare -A ECH
ECH[npm]="900 2 0"
ECH[pnpm]="900 2 0"
ECH[yarn]="900 2 0"
ECH[yarn-berry]="900 2 1"
ECH[pip]="900 2 0"
ECH[pip-sources]="900 2 1"
ECH[gradle]="1800 6 1"
ECH[maven]="1800 6 1"
ECH[dotnet]="1800 6 1"
ECH[cargo]="1800 6 1"
ECH[go]="900 2 0"
ECH[unity]="3600 10 1"
declare -A ECH_DEFAUT=([python]=pip [node]=npm [gradle-android]=gradle [gradle-jvm]=gradle [maven]=maven [dotnet]=dotnet
                       [go]=go [rust]=cargo [unity]=unity)
# Sortie du mandataire (liste fermée par clé, Q4). TOUS les échauffements passent par lui (réseau interne, jamais bridge) :
# même sans code exécuté, un verrou npm (`resolved`) ou une dépendance par URL choisirait l'hôte. GitHub n'y est JAMAIS ; la
# distribution Gradle est téléchargée par l'hôte (DIST_HOTES), pas par le conteneur.
declare -A ECH_HOTES
ECH_HOTES[npm]="registry.npmjs.org"
ECH_HOTES[pnpm]="registry.npmjs.org"
ECH_HOTES[yarn]="registry.yarnpkg.com registry.npmjs.org"
ECH_HOTES[yarn-berry]="registry.yarnpkg.com registry.npmjs.org repo.yarnpkg.com"
ECH_HOTES[pip]="pypi.org files.pythonhosted.org"
ECH_HOTES[pip-sources]="pypi.org files.pythonhosted.org"
ECH_HOTES[gradle]="plugins.gradle.org plugins-artifacts.gradle.org repo.maven.apache.org repo1.maven.org dl.google.com maven.google.com"
ECH_HOTES[maven]="repo.maven.apache.org repo1.maven.org"
ECH_HOTES[dotnet]="api.nuget.org"
ECH_HOTES[cargo]="index.crates.io static.crates.io crates.io"
ECH_HOTES[go]="proxy.golang.org sum.golang.org"
SOMMES_GRADLE_URL="https://services.gradle.org/distributions"
VERSIONS_GRADLE_URL="https://services.gradle.org/versions/all"
DIST_HOTES=" services.gradle.org downloads.gradle.org "  # redirections admises pour la distribution (hôte), jamais d'autre
INODES_MAX=500000                                      # inodes d'un cache en préparation et de son /work (tmpfs)
ECHAUFFEMENTS_MAX=2                                    # échauffements simultanés au serveur (~/taches/.echauffement-1..2)
# Mots fermés de `#deps-echec` (tout autre : « inconnue »). Échecs d'échauffement retenus pour CETTE empreinte (repli immédiat,
# même raison) : RAISONS_MEMOIRE une heure, RAISONS_BREVES (pannes passagères) cinq minutes ; `memoire` (137 sans marque du
# surveillant) n'est jamais retenu : une panne de mémoire ne doit pas interdire le serveur au projet.
RAISONS=" reseau-non-accorde wrapper-modifie wrapper-absent wrapper-illisible distribution-hors-services-gradle
  somme-gradle-injoignable somme-gradle-illisible sommes-gradle-inaccessibles curl-absent distribution-injoignable
  distribution-redirection distribution-somme echauffement plafond inodes duree memoire disque copie-sur-ecriture
  unity-tache-14g cache-inaccessible echauffement-concurrent ecriture reseau-interne mandataire reseau-sans-liste cache-verrou
  cache-disparu "
RAISONS="${RAISONS//$'\n'/ }"
RAISONS_MEMOIRE=" echauffement plafond inodes duree distribution-redirection distribution-somme "
RAISONS_BREVES=" distribution-injoignable mandataire reseau-interne "
# Unity (tâche 14g) : l'image de la famille (version Unity : miroir de tests_images.MOTIFS_VERSION["unity"]), les noms d'hôtes de
# B3, et la table FERMÉE des montages de licence (lecture seule ; jamais unityhub, jamais une socket, jamais le dossier entier).
MOTIF_IMAGE_UNITY='^myiafactory/tests-unity-[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3}$'
MOTIF_HOTE='^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$'
# Table FERMÉE des suffixes de licence Unity (B3) : le poste ne choisit qu'un sous-ensemble de noms SOUS ces domaines (ou eux-
# mêmes) ; jamais une adresse IP (dernier libellé alphabétique exigé), jamais un autre domaine. Miroir : tests_serveur.SUFFIXES_LICENCE.
SUFFIXES_LICENCE=" unity3d.com unity.com "
LICENCE_DROITS_REL=".config/unity3d/Unity/licenses"     # -> /licence/droits:ro
LICENCE_ULF_REL=".local/share/unity3d/Unity/Unity_lic.ulf"   # -> /licence/ulf:ro
MACHINE_ID=/etc/machine-id                             # B2 et B3 : -> /etc/machine-id:ro
PLACES_MAX=4
JETONS_MAX=20
DUREE_MAX=3600
DISQUE_MIN_KO=5242880                    # 5 Go libres au départ
DISQUE_ARRET_KO=2097152                  # 2 Go libres pendant la campagne
INODES_MIN_PC=5                          # inodes libres : 5 % au moins (départ et campagne)
SORTIE_MAX=52428800
if [[ ${ENVELOPPE_SORTIE_MAX_OCTETS:-} =~ ^[1-9][0-9]{0,8}$ ]]; then SORTIE_MAX="$ENVELOPPE_SORTIE_MAX_OCTETS"; fi   # tests
SONDE="${ENVELOPPE_SONDE_S:-0.5}"
[[ $SONDE =~ $MOTIF_SONDE ]] || SONDE=0.5
MARGE=30
if [[ ${ENVELOPPE_MARGE_S:-} =~ ^[0-9]{1,3}$ ]]; then MARGE="$ENVELOPPE_MARGE_S"; fi                           # tests
DU_S=5
if [[ ${ENVELOPPE_DU_S:-} =~ ^[0-9]{1,3}$ ]]; then DU_S="$ENVELOPPE_DU_S"; fi                                  # tests

# --- Arguments (rien n'est écrit avant la fin de ce bloc) ------------------

[ $# -ge 7 ] && [ $# -le 18 ] || refuser "usage : <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps> [<travail_go> [<image> [<famille> [<echauffement> [<reseau_code> [<budget_caches_go> [<budget_unites> [<executeur> [<licence> [<hotes_licence> [<version_hote>]]]]]]]]]]]"
for argument in "$@"; do
  [[ $argument == *[[:cntrl:]]* ]] && refuser "caractère de contrôle refusé dans un argument."
done
ID="$1"; PLACES="$2"; CPUS="$3"; MEMOIRE="$4"; DUREE="$5"; PROJET="$6"; DEPS="$7"; TRAVAIL_GO="${8-10}"; IMAGE_DEMANDEE="${9-myiafactory/tests}"; FAMILLE="${10-python}"
[[ $ID =~ $MOTIF_ID ]] || refuser "identifiant refusé."
[[ $PLACES =~ ^[1-4]$ ]] || refuser "places refusées (1 à $PLACES_MAX)."
[[ $CPUS =~ $MOTIF_CPUS ]] && [ "$CPUS" -le 64 ] || refuser "cpus refusés (1 à 64)."
[[ $MEMOIRE =~ $MOTIF_MEMOIRE ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser "memoire_mo refusée (256 à 65536)."
[[ $DUREE =~ $MOTIF_DUREE ]] && [ "$DUREE" -le "$DUREE_MAX" ] || refuser "duree_s refusée (1 à $DUREE_MAX, sans zéro initial)."
[[ $PROJET =~ ^[a-z0-9][a-z0-9-]{0,39}$ ]] || refuser "projet refusé."
[[ $DEPS =~ ^([0-9a-f]{16}|-)$ ]] || refuser "deps refusé (16 hexa ou -)."
[[ $TRAVAIL_GO =~ ^[1-9][0-9]{0,2}$ ]] && [ "$TRAVAIL_GO" -le 200 ] || refuser "travail_go refusé (1 à 200)."
IMAGE_UNITY=0
if [[ $IMAGE_DEMANDEE =~ $MOTIF_IMAGE_UNITY ]]; then IMAGE_UNITY=1
else [[ $IMAGE_DEMANDEE =~ ^myiafactory/tests(-[a-z0-9]{1,24})?$ ]] || refuser "image refusée (myiafactory/tests ou myiafactory/tests-<nom>)."; fi
[[ $FAMILLE =~ ^[a-z][a-z-]{1,15}$ ]] && [[ $FAMILLES == *" $FAMILLE "* ]] || refuser "famille refusée."
EXECUTEUR="${15-conteneur}"; LICENCE="${16--}"; HOTES_LICENCE="${17--}"
[[ $EXECUTEUR =~ ^(conteneur|hote_bac_a_sable)$ ]] || refuser "executeur refusé (conteneur ou hote_bac_a_sable)."
[[ $LICENCE =~ ^(-|B1|B2|B3)$ ]] || refuser "licence refusée (-, B1, B2 ou B3)."
HOTES_B3=()
if [ "$HOTES_LICENCE" != - ]; then
  [ "$LICENCE" = B3 ] || refuser "hotes_licence refusés : seulement avec la licence B3."
  [ "${#HOTES_LICENCE}" -le 512 ] || refuser "hotes_licence refusés (512 caractères au plus)."
  IFS=, read -r -a HOTES_B3 <<< "$HOTES_LICENCE"
  [ "${#HOTES_B3[@]}" -ge 1 ] && [ "${#HOTES_B3[@]}" -le 8 ] || refuser "hotes_licence refusés (1 à 8 noms)."
  for h in "${HOTES_B3[@]}"; do
    [[ $h =~ $MOTIF_HOTE ]] || refuser "hotes_licence refusés (nom d'hôte hors motif)."
    [[ ${h##*.} =~ ^[a-z]{2,63}$ ]] || refuser "hotes_licence refusés (adresse IP ou dernier libellé non alphabétique)."
    admis=0
    for s in $SUFFIXES_LICENCE; do [ "$h" = "$s" ] || [[ $h == *".$s" ]] && admis=1; done
    [ "$admis" = 1 ] || refuser "hotes_licence refusés ($h hors de la table des domaines de licence Unity)."
  done
  [[ $HOTES_LICENCE == *, || $HOTES_LICENCE == ,* || $HOTES_LICENCE == *,,* ]] && refuser "hotes_licence refusés (liste mal formée)."
fi
[ "$LICENCE" = B3 ] && [ "${#HOTES_B3[@]}" = 0 ] && refuser "licence B3 sans hotes_licence : rien ne part."
if [ "$FAMILLE" = unity ]; then
  [ "$IMAGE_UNITY" = 1 ] || refuser "famille unity : image myiafactory/tests-unity-<version> attendue."
  [ "$LICENCE" != - ] || refuser "famille unity : licence B1, B2 ou B3 attendue."
else
  [ "$IMAGE_UNITY" = 0 ] || refuser "image Unity refusée hors de la famille unity."
  [ "$LICENCE" = - ] || refuser "licence refusée hors de la famille unity."
fi
VERSION_HOTE="${18--}"
[ "$EXECUTEUR" = conteneur ] || [ "$FAMILLE" = unity ] || refuser "exécuteur hote_bac_a_sable : famille unity seulement."
if [ "$VERSION_HOTE" != - ]; then
  [ "$EXECUTEUR" = hote_bac_a_sable ] || refuser "version_hote refusée : seulement avec l'exécuteur hote_bac_a_sable."
  [[ myiafactory/tests-unity-$VERSION_HOTE =~ $MOTIF_IMAGE_UNITY ]] || refuser "version_hote refusée (version Unity hors motif)."
fi
VERSION_PROJET="${IMAGE_DEMANDEE#myiafactory/tests-unity-}"
ECH_CLE="${11-${ECH_DEFAUT[$FAMILLE]-"-"}}"; RESEAU="${12-refuse}"; BUDGET="${13-40}"; BUDGET_U="${14-16}"
if [ "$ECH_CLE" != - ]; then
  [[ $ECH_CLE =~ ^[a-z][a-z-]{1,11}$ ]] && [ -n "${ECH[$ECH_CLE]+x}" ] || refuser "échauffement refusé (clé hors de la table)."
fi
[[ $RESEAU =~ ^(accorde|refuse)$ ]] || refuser "reseau_code refusé (accorde ou refuse)."
[[ $BUDGET =~ ^[1-9][0-9]{0,3}$ ]] && [ "$BUDGET" -le 1000 ] || refuser "budget_caches_go refusé (1 à 1000)."
[[ $BUDGET_U =~ ^([4-9]|1[0-9]|20)$ ]] || refuser "budget_unites refusé (4 à $JETONS_MAX)."
POIDS=$(((MEMOIRE + 2047) / 2048))
[ "$POIDS" -le "$BUDGET_U" ] || refuser "memoire_mo refusée : $POIDS jetons de 2 Go, plus que le budget de mémoire du serveur ($BUDGET_U)."
[ "$DEPS" = - ] || [ "$ECH_CLE" != - ] || refuser "deps sans échauffement connu pour la famille $FAMILLE."
IMAGE="$IMAGE_DEMANDEE"
TRAVAIL_MAX_KO=$((TRAVAIL_GO * 1048576))
[[ ${HOME:-} == /* ]] || refuser "HOME absent ou relatif."
case "$HOME" in *[:,]*) refuser "HOME non admis (deux-points ou virgule : montage impossible)." ;; esac
case "$AIDE" in *[:,]*) refuser "chemin de l'enveloppe non admis (deux-points ou virgule : montage impossible)." ;; esac
command -v python3 >/dev/null 2>&1 || { printf '%s\n' "lancer_tests : python3 absent du serveur." >&2; fin_simple 77; }

# La commande : 1re ligne de l'entrée standard, lue octet par octet (read), jamais au-delà de 4 097 octets.
COMMANDE_JSON=""
IFS= read -r -n 4097 COMMANDE_JSON || [ -n "$COMMANDE_JSON" ] || refuser "commande absente (1re ligne de l'entrée standard)."
[ "${#COMMANDE_JSON}" -le 4096 ] || refuser "commande trop longue (4 096 octets au plus)."
[[ $COMMANDE_JSON == \[*\] ]] || refuser "commande refusée : un tableau JSON est attendu."
printf '%s' "$COMMANDE_JSON" | python3 -I "$AIDE" --commande 2>/dev/null || refuser "commande refusée : un tableau JSON de 1 à 64 chaînes est attendu."

TESTS="$HOME/tests"
DOSSIER="$TESTS/$ID"
ENTREE="$DOSSIER/entree"
for d in "$TESTS" "$DOSSIER" "$ENTREE"; do              # des dossiers (pas des liens) à nous (-O : propriétaire effectif)
  [ -d "$d" ] && [ ! -L "$d" ] || refuser "dossier ${d#"$HOME"/} absent (ou lien) : déposez l'instantané d'abord."
  [ -O "$d" ] || refuser "dossier ${d#"$HOME"/} : propriétaire autre que l'utilisateur de l'enveloppe."
done
[ -f "$ENTREE/entree.tar" ] && [ ! -L "$ENTREE/entree.tar" ] && [ -O "$ENTREE/entree.tar" ] ||
  refuser "instantané ~/tests/$ID/entree/entree.tar absent (ou lien, ou à un autre propriétaire)."
# travail/ créé ici, et par nous seuls (mkdir échoue s'il existe) : c'est la prise de l'identifiant. Rien d'autre n'a été écrit.
mkdir -m 700 -- "$DOSSIER/travail" 2>/dev/null || refuser "identifiant $ID déjà utilisé (travail/ existe)."
chmod 700 -- "$TESTS" "$DOSSIER" "$ENTREE" 2>/dev/null   # 0700 imposé (créés par le poste, umask inconnu)

# --- À partir d'ici, toute fin passe par finir : nettoyage, #refus éventuel, puis #fin ------------------------------

declare -A MES_JETONS=()                               # numéro -> descripteur des jetons de mémoire tenus
liberer_jetons() {
  local k f
  [ "${#MES_JETONS[@]}" -gt 0 ] || return 0              # tableau vide sous set -u : à éviter avant bash 4.4
  for k in "${!MES_JETONS[@]}"; do
    f="${MES_JETONS[$k]}"
    flock -u "$f" 2>/dev/null; exec {f}>&-
  done
  MES_JETONS=()
}
A_NOUS=1; TICKET=""; PID_LAISSE=""; PID_SURVEILLANT=""; CONTENEUR=0
DEPS_CONTENEUR=0; MANDATAIRE=0; DEPS_RESEAU=""; VOLUMES=(); TMP_CACHE=""

fermer_reseau() {   # le mandataire et le réseau interne d'un échauffement : jamais laissés derrière
  if [ "$MANDATAIRE" = 1 ]; then dk 30 rm -f "mandataire-$ID" >/dev/null 2>&1; MANDATAIRE=0; fi
  if [ -n "$DEPS_RESEAU" ]; then dk 30 network rm "$DEPS_RESEAU" >/dev/null 2>&1; DEPS_RESEAU=""; fi
}

conteneur_absent() {   # conteneur_absent [<id>] : 0 seulement si docker répond nettement « pas de tel conteneur »
  local e
  e=$(dk 20 inspect --type container -f '{{.State.Status}}' "tests-${1:-$ID}" 2>&1 >/dev/null) && return 1
  case "${e,,}" in *"no such"*|*"not found"*) return 0 ;; esac
  return 1
}

finir() {   # finir <code> [conteneur] : « conteneur » = le code vient du conteneur (pas de #refus)
  local code="$1" origine="${2:-enveloppe}" sur=1
  trap '' PIPE TERM INT HUP
  trap - EXIT
  # Fils tués PUIS attendus, leurs avis (« Terminated ») jetés : rien ne s'écrit après #fin.
  { for p in $PID_LAISSE $PID_SURVEILLANT; do kill "$p"; wait "$p"; done; } 2>/dev/null
  PID_LAISSE=""; PID_SURVEILLANT=""
  if [ "$CONTENEUR" = 1 ]; then                       # parti sans fin constatée : jamais de conteneur laissé derrière
    "$ARRETER"
    dk 30 rm -f "tests-$ID" >/dev/null 2>&1
    conteneur_absent || sur=0                         # arrêt non confirmé : le conteneur peut encore écrire dans travail/
  fi
  if [ "$DEPS_CONTENEUR" = 1 ]; then
    dk 30 kill "deps-$ID" >/dev/null 2>&1
    dk 30 rm -f "deps-$ID" >/dev/null 2>&1
    DEPS_CONTENEUR=0
  fi
  fermer_reseau
  for v in "${VOLUMES[@]}"; do dk 30 volume rm -f "$v" >/dev/null 2>&1; done   # les couches hautes partent avec le dossier
  if [ -n "$TMP_CACHE" ] && [ -d "$TMP_CACHE" ] && [ ! -L "$TMP_CACHE" ]; then   # échauffement inachevé : rien n'est prêt
    chmod -R u+rwX -- "$TMP_CACHE" 2>/dev/null; rm -rf -- "$TMP_CACHE"
  fi
  exec 3>&- 5>&- 6>&- 7>&-                             # sommes Gradle, cache, place d'échauffement, préparation rendus
  [ -n "$TICKET" ] && rm -f -- "$TICKET"
  liberer_creneau
  liberer_jetons
  if [ -e "$DOSSIER/sortie-coupee" ]; then printf '%s\n' "Sortie coupée à 50 Mo" >&2; fi
  if [ -e "$DOSSIER/erreur-coupee" ]; then printf '%s\n' "Sortie d'erreur coupée à 50 Mo" >&2; fi
  if [ "$A_NOUS" = 1 ]; then
    if [ "$sur" = 1 ]; then
      for d in travail deps-travail deps-haut sdk-haut; do   # un dossier sans droits laissé par les tests s'efface aussi
        [ -d "$DOSSIER/$d" ] && [ ! -L "$DOSSIER/$d" ] && chmod -R u+rwX -- "$DOSSIER/$d" 2>/dev/null
      done
    fi
    rm -rf -- "$DOSSIER"
  fi
  # Un retour à la ligne d'abord, toujours (le poste ignore les lignes vides) : jamais collé à une ligne inachevée.
  [ "$origine" = conteneur ] || printf '\n#refus %s\n' "$code" >&2
  printf '\n#fin %s %s %s %s\n' "$code" "${DEBUT:-$T0}" "$(date +%s)" "$ATTENTE" >&2
  exit "$code"
}
echouer() { printf '%s\n' "lancer_tests : $2" >&2; finir "$1"; }
trap 'finir 130' TERM INT HUP PIPE
trap 'finir 1' EXIT
# Fichiers de l'hôte dans ~/tests/<id>/ (hors de tout montage) : retirés d'abord, jamais écrits à travers un lien déposé.
for f in enveloppe.pid code sortie-coupee erreur-coupee laisse-coupee disque-plein inodes travail-plein echeance; do
  rm -f -- "$DOSSIER/$f"
done
( set -C; printf '%s\n' "$$" > "$DOSSIER/enveloppe.pid" ) 2>/dev/null || echouer 1 "enveloppe.pid non écrit."
enveloppe_vivante() { processus_vivant "$TESTS/$1/enveloppe.pid" "lancer_tests.sh" "$1"; }

# --- Exécuteurs (tâche 14g) : SEULE différence entre conteneur et hôte ; tout le reste (place, jetons, file, laisse, surveillant,
# coupe, préfixe, #fin, nettoyage) est commun. _lancer écrit la sortie de la commande sur la sortie standard et sa sortie
# d'erreur sur la sortie d'erreur, rend son code ; _arreter l'arrête (laisse, surveillant, fin), sans rien écrire.
executeur_conteneur_lancer() { timeout "$DUREE" sudo -n docker "${COMMANDE[@]}"; }
executeur_conteneur_arreter() { dk 30 kill "tests-$ID" >/dev/null 2>&1; }
# Option A (§ 5.16, tâche 14h) : le script racine (sudo -n, règle sudoers limitée à ce chemin) lance l'unité confinée. Il reçoit
# la commande (1re ligne) puis l'instantané, lus ICI par l'utilisateur principal : la racine n'ouvre aucun fichier de ~/tests.
BAC_A_SABLE=/usr/local/lib/myiafactory/unity-bac-a-sable.sh
executeur_hote_lancer() {
  local v="$VERSION_PROJET" reseau=aucun
  [ "$VERSION_HOTE" != - ] && v="$VERSION_HOTE"
  [ "$LICENCE" = B3 ] && reseau=licence
  [ "$v" = "$VERSION_PROJET" ] || printf 'Éditeur %s au lieu de %s : résultats indicatifs\n' "$v" "$VERSION_PROJET"
  { printf '%s\n' "$COMMANDE_JSON"; cat -- "$ENTREE/entree.tar"; } |
    timeout "$DUREE" sudo -n "$BAC_A_SABLE" lancer "$ID" "$CPUS" "$MEMOIRE" "$DUREE" "$v" "$reseau"
}
executeur_hote_arreter() { timeout 130 sudo -n "$BAC_A_SABLE" arreter "$ID" </dev/null >/dev/null 2>&1 8>&-; }
case "$EXECUTEUR" in
  conteneur) LANCER=executeur_conteneur_lancer; ARRETER=executeur_conteneur_arreter ;;
  *) LANCER=executeur_hote_lancer; ARRETER=executeur_hote_arreter ;;
esac

# Laisse : le reste de l'entrée standard. Fin de fichier = la session SSH est partie : marque, puis conteneur tué et
# enveloppe arrêtée, répétés tant que l'enveloppe vit (vérifiée par sa ligne de commande : jamais un PID recyclé).
exec 6<&0 </dev/null
( trap - TERM INT HUP PIPE
  while IFS= read -r _ <&6; do :; done
  exec 6<&-
  : > "$DOSSIER/laisse-coupee"
  while :; do
    "$ARRETER"
    dk 30 kill "deps-$ID" >/dev/null 2>&1
    enveloppe_vivante "$ID" || exit 0
    kill -TERM "$$" 2>/dev/null
    sleep 1
  done ) >/dev/null 2>&1 &
PID_LAISSE=$!
exec 6<&-

disque_libre_ko() { df -Pk -- "$HOME" 2>/dev/null | awk 'NR == 2 { print $4 }'; }
inodes_bas() {   # 0 si moins de 5 % d'inodes libres (un système sans inodes comptés, 0, n'est jamais « bas »)
  local l
  l=$(df -Pi -- "$HOME" 2>/dev/null | awk 'NR == 2 { print $2, $4 }')
  [[ $l =~ ^([0-9]{1,15})\ ([0-9]{1,15})$ ]] || return 1
  [ "${BASH_REMATCH[1]}" -gt 0 ] && [ $((BASH_REMATCH[2] * 100)) -lt $((BASH_REMATCH[1] * INODES_MIN_PC)) ]
}
# Un message sur une ligne : contrôles puis NEL, LS, PS REMPLACÉS par « ? » (jamais retirés : un retrait rapprocherait
# deux octets qui reformeraient un séparateur).
une_ligne() { tr '\000-\037\177' '?' | sed -e 's/\xc2\x85/?/g' -e 's/\xe2\x80\xa8/?/g' -e 's/\xe2\x80\xa9/?/g' | head -c 300; }

# --- Contrôles avant la file ------------------------------------------------

libre=$(disque_libre_ko)
[[ $libre =~ ^[0-9]{1,15}$ ]] || echouer 76 "espace disque libre illisible (df)."
[ "$libre" -ge "$DISQUE_MIN_KO" ] || echouer 76 "disque presque plein : $((libre / 1024)) Mo libres, 5 Go au moins."
inodes_bas && echouer 76 "inodes presque épuisés : moins de ${INODES_MIN_PC} % libres."
[ "$(id -u)" = 1000 ] || echouer 77 "l'utilisateur du serveur doit être 1000 (celui du conteneur de tests)."
if [ "$EXECUTEUR" = conteneur ]; then                  # l'exécuteur hôte n'a pas d'image (l'éditeur de l'hôte)
  dk 20 image inspect "$IMAGE" >/dev/null 2>&1 || echouer 77 "image $IMAGE absente : installez la capacité qui la fournit (tests-image, tests-android)."
fi
if [ "$FAMILLE" = gradle-android ]; then
  [ -d "$HOME/android-sdk" ] || echouer 77 "SDK Android de l'hôte absent (~/android-sdk) : installez la capacité android-build."
fi
# Licence Unity (famille unity seulement, table fermée de l'en-tête) : chaque source est vérifiée AVANT d'être montée (un
# `docker -v` sur un chemin absent créerait un dossier de root sur l'hôte) ; un lien n'est jamais monté. Rien n'est lu.
LICENCE_ARGS=()
if [ "$FAMILLE" = unity ]; then
  droits="$HOME/$LICENCE_DROITS_REL"; ulf="$HOME/$LICENCE_ULF_REL"
  # Lisible par l'uid du conteneur (1000, celui de l'enveloppe, vérifié plus haut) : dossier parcourable, chaque fichier
  # lisible (noms seulement, -r ; jamais le contenu) ; sinon 77 explicite plutôt qu'un refus de licence trompeur dans le conteneur.
  if [ -d "$droits" ] && [ ! -L "$droits" ]; then
    [ -r "$droits" ] && [ -x "$droits" ] && [ -z "$(find "$droits" \( -type f -o -type d \) ! -readable -print -quit 2>/dev/null)" ] ||
      echouer 77 "licence Unity illisible par l'utilisateur des tests (~/$LICENCE_DROITS_REL) : droits à corriger."
    LICENCE_ARGS+=(-v "$droits:/licence/droits:ro")
  fi
  if [ -f "$ulf" ] && [ ! -L "$ulf" ]; then
    [ -r "$ulf" ] || echouer 77 "licence Unity illisible par l'utilisateur des tests (~/$LICENCE_ULF_REL) : droits à corriger."
    LICENCE_ARGS+=(-v "$ulf:/licence/ulf:ro")
  fi
  [ "${#LICENCE_ARGS[@]}" -gt 0 ] ||
    echouer 77 "licence Unity absente de l'hôte (~/$LICENCE_DROITS_REL ou ~/$LICENCE_ULF_REL) : installez la capacité unity-cli."
  # B2 et B3 en conteneur : identifiants de machine de l'hôte (sur l'hôte, option A, l'unité les a d'elle-même).
  if [ "$EXECUTEUR" = conteneur ] && { [ "$LICENCE" = B2 ] || [ "$LICENCE" = B3 ]; }; then
    [ -f "$MACHINE_ID" ] && [ ! -L "$MACHINE_ID" ] || echouer 77 "$MACHINE_ID absent de l'hôte : licence $LICENCE impossible."
    nom_hote=$(hostname 2>/dev/null || uname -n 2>/dev/null)
    [[ $nom_hote =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,62}$ ]] || echouer 77 "nom d'hôte illisible : licence $LICENCE impossible."
    LICENCE_ARGS+=(-v "$MACHINE_ID:$MACHINE_ID:ro" --hostname "$nom_hote")
  fi
  LICENCE_ARGS+=(-e MYIAFACTORY_TESTS_FAMILLE=unity)
fi
DEPS_RACINE=""; CACHE=""
if [ "$DEPS" != - ]; then
  DEPS_RACINE="$TESTS/.deps/$PROJET"
  CACHE="$DEPS_RACINE/$ECH_CLE-$DEPS"
  for d in "$TESTS/.deps" "$DEPS_RACINE" "$CACHE" "$CACHE/contenu" "$CACHE.tmp"; do   # absent : préparé plus bas
    if [ -e "$d" ] || [ -L "$d" ]; then
      [ -d "$d" ] && [ ! -L "$d" ] && [ -O "$d" ] ||
        echouer 78 "cache des dépendances ~/${d#"$HOME"/} : lien, fichier ou autre propriétaire."
    fi
  done
fi
raison=$(python3 -I "$AIDE" --archive "$ENTREE/entree.tar" 2>&1 >/dev/null); r=$?
if [ "$r" = 3 ]; then echouer 70 "$(printf '%s' "$raison" | une_ligne)"; fi   # 3 : refus explicite du vérificateur
[ "$r" = 0 ] || echouer 77 "contrôle de l'instantané impossible (python3, code $r)."
# Drapeaux hors ligne de la famille (table fermée de tests_hote.py --hors-ligne), ajoutés ICI, jamais par le poste.
case "$ECH_CLE" in
  gradle|maven|cargo|dotnet)
    if hl=$(printf '%s' "$COMMANDE_JSON" | python3 -I "$AIDE" --hors-ligne "$ECH_CLE" 2>/dev/null) && [[ $hl == \[*\] ]]; then
      COMMANDE_JSON="$hl"
    fi ;;
esac
rm -f -- "$ENTREE/commande.json"                    # jamais écrit à travers un lien
( set -C; printf '%s' "$COMMANDE_JSON" > "$ENTREE/commande.json" ) 2>/dev/null || echouer 1 "commande.json non écrit."

# --- Balayage ----------------------------------------------------------------

# Les conteneurs d'abord (sans enveloppe vivante : supprimés), puis les dossiers : un dossier dont le conteneur tests-<id>
# n'est pas CONFIRMÉ absent est laissé tel quel (ni chmod -R, ni rm -rf : le conteneur pourrait encore y écrire).
noms=$(dk 20 ps -a --filter "label=myiafactory.genre=tests" --format '{{.Names}}' 2>/dev/null)
while IFS= read -r n; do
  [[ $n =~ ^tests-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$ ]] || continue
  autre="${BASH_REMATCH[1]}"
  [ "$autre" = "$ID" ] || enveloppe_vivante "$autre" || dk 30 rm -f "tests-$autre" >/dev/null 2>&1
done <<< "$noms"
while IFS= read -r -d '' d; do
  nom="${d##*/}"
  [[ $nom =~ $MOTIF_ID ]] && [ "$nom" != "$ID" ] || continue
  if [ -L "$d" ]; then rm -f -- "$d"; continue; fi
  [ -d "$d" ] || continue
  enveloppe_vivante "$nom" && continue
  conteneur_absent "$nom" || continue
  for s in travail deps-haut sdk-haut; do              # chmod suit un lien nommé : jamais sur un lien
    [ -d "$d/$s" ] && [ ! -L "$d/$s" ] && chmod -R u+rwX -- "$d/$s" 2>/dev/null
  done
  rm -rf -- "$d"
done < <(find "$TESTS" -mindepth 1 -maxdepth 1 -name 't*' -mmin +360 -print0 2>/dev/null)
# Restes d'échauffement (conteneurs deps-/mandataire-/essai-, réseaux deps-, volumes tests-deps-/tests-sdk-) dont l'enveloppe
# ne vit plus : les conteneurs d'abord, puis réseaux et volumes (un volume encore monté résiste : repris au balayage suivant).
balayer() {   # balayer <motif du nom, identifiant en 2e groupe> <commande de suppression>... ; noms de la liste filtrée par l'étiquette
  local motif="$1" n autre; shift
  while IFS= read -r n; do
    [[ $n =~ $motif ]] || continue
    autre="${BASH_REMATCH[2]}"
    [ "$autre" = "$ID" ] || enveloppe_vivante "$autre" || dk 30 "$@" "$n" >/dev/null 2>&1
  done
}
# ~/tests/.deps existe dès le premier cache ou le premier SDK en copie sur écriture : sans lui, rien de tel n'a jamais été
# créé (trois listes docker de moins à chaque lancement).
if [ -d "$TESTS/.deps" ]; then
  balayer '^(deps|mandataire|essai-deps|essai-sdk)-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$' rm -f \
    < <(dk 20 ps -a --filter "label=myiafactory.genre=tests-deps" --format '{{.Names}}' 2>/dev/null)
  balayer '^(deps)-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$' network rm \
    < <(dk 20 network ls --filter "label=myiafactory.genre=tests-deps" --format '{{.Name}}' 2>/dev/null)
  balayer '^tests-(deps|sdk)-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$' volume rm -f \
    < <(dk 20 volume ls --filter "label=myiafactory.genre=tests-deps" --format '{{.Name}}' 2>/dev/null)
fi
# Caches en préparation abandonnés (<clé>-<deps>.tmp dont le verrou de préparation est libre : sa préparation est morte) et
# caches évincés (.supprime-*, déjà renommés : plus personne ne les trouve) : chmod d'abord (cache Go en lecture seule).
for t in "$TESTS"/.deps/*/*.tmp; do
  [ -d "$t" ] && [ ! -L "$t" ] || continue
  nom="${t##*/}"; nom="${nom%.tmp}"
  [[ $nom =~ ^[a-z][a-z-]{1,11}-[0-9a-f]{16}$ ]] || continue
  exec 4>> "${t%/*}/.$nom.echauffement" || continue
  if flock -x -n 4; then chmod -R u+rwX -- "$t" 2>/dev/null; rm -rf -- "$t"; fi
  exec 4>&-
done
for t in "$TESTS"/.deps/*/.supprime-*; do
  [ -d "$t" ] && [ ! -L "$t" ] || continue
  chmod -R u+rwX -- "$t" 2>/dev/null; rm -rf -- "$t"
done

# --- Dépendances : wrapper Gradle, échauffement, cache tenu, éviction (§ 5.13) ------------------------------------------

ECHAUFFE=0
deps_echec() {   # deps_echec <raison> : `#deps-echec <mot fermé>`, retenu une heure si c'est un échec d'échauffement, puis 79
  local r="$1"
  [[ $RAISONS == *" $r "* ]] || r=inconnue
  if [ "$ECHAUFFE" = 1 ] && [[ $RAISONS_MEMOIRE$RAISONS_BREVES == *" $r "* ]] && [ -n "$DEPS_RACINE" ]; then
    printf '%s %s\n' "$(date +%s)" "$r" > "$DEPS_RACINE/.$ECH_CLE-$DEPS.echec.tmp" 2>/dev/null &&
      mv -f -- "$DEPS_RACINE/.$ECH_CLE-$DEPS.echec.tmp" "$DEPS_RACINE/$ECH_CLE-$DEPS.echec" 2>/dev/null
  fi
  printf '#deps-echec %s\n' "$r" >&2
  echouer 79 "échauffement des dépendances impossible ($r) : les tests ne partent pas au serveur."
}
memoire_echec() {   # un échec retenu (1 h, ou 5 min pour une panne passagère), pour CETTE empreinte : repli immédiat
  local f="$DEPS_RACINE/$ECH_CLE-$DEPS.echec" quand raison delai=3600
  [ -f "$f" ] && [ ! -L "$f" ] || return 0
  read -r quand raison < "$f" 2>/dev/null || return 0
  [[ $quand =~ ^[0-9]{1,12}$ ]] && [[ $RAISONS_MEMOIRE$RAISONS_BREVES == *" $raison "* ]] || { rm -f -- "$f"; return 0; }
  [[ $RAISONS_BREVES == *" $raison "* ]] && delai=300
  if [ $(($(date +%s) - quand)) -lt "$delai" ]; then
    printf '%s\n' "lancer_tests : échauffement en échec il y a moins de $((delai / 60)) min pour ces dépendances : pas de nouvel essai." >&2
    deps_echec "$raison"
  fi
  rm -f -- "$f"
}
verrou_de() { printf '%s/.%s.verrou' "${1%/*}" "${1##*/}"; }   # HORS du dossier du cache ; jamais effacé (voir effacer_cache)
cache_pret() { [ -f "$1/.pret" ] && [ -d "$1/contenu" ] && [ ! -L "$1" ] && [ ! -L "$1/contenu" ]; }
cache_perime() { [ -f "$1/.non-verrouille" ] && [ -n "$(find "$1/.pret" -mmin +10080 2>/dev/null)" ]; }   # 7 jours
du_ko() { local k; k=$(timeout 120 du -sk -- "$1" 2>/dev/null 8>&- | cut -f1); [[ $k =~ ^[0-9]{1,15}$ ]] && printf '%s' "$k"; }
du_inodes() { local k; k=$(timeout 120 du --inodes -s -- "$1" 2>/dev/null 8>&- | cut -f1); [[ $k =~ ^[0-9]{1,15}$ ]] && printf '%s' "$k"; }
effacer_cache() {   # effacer_cache <cache> : seulement si personne ne le tient (flock -x -n sur son verrou) ; 0 si effacé
  local c="$1" v t
  [ -d "$c" ] && [ ! -L "$c" ] || return 1
  v=$(verrou_de "$c")
  exec 4>> "$v" || return 1
  if ! flock -x -n 4; then exec 4>&-; return 1; fi
  t="${c%/*}/.supprime-$(date +%s%N)-${c##*/}"
  if ! mv -- "$c" "$t"; then exec 4>&-; return 1; fi   # atomique : plus aucune campagne ne le trouve prêt
  # Le fichier .verrou n'est JAMAIS effacé : effacé, une campagne qui l'a ouvert juste avant tiendrait un verrou sur un inode
  # orphelin pendant qu'une autre en crée un nouveau (deux « verrous » pour le même cache). Quelques octets par empreinte.
  exec 4>&-
  chmod -R u+rwX -- "$t" 2>/dev/null                   # le cache de modules Go (entre autres) est en lecture seule
  rm -rf -- "$t"
  return 0
}
lister_caches() {   # lister_caches <dossier de projet>... [-- <clé>] : « mtime chemin », du moins récemment utilisé au plus récent
  local cle="" p d nom
  local -a projets=()
  while [ $# -gt 0 ]; do [ "$1" = -- ] && { cle="$2"; break; }; projets+=("$1"); shift; done
  for p in "${projets[@]}"; do
    [ -d "$p" ] && [ ! -L "$p" ] || continue
    for d in "$p"/*; do
      nom="${d##*/}"
      [[ $nom =~ ^[a-z][a-z-]{1,11}-[0-9a-f]{16}$ ]] && [ -d "$d" ] && [ ! -L "$d" ] || continue
      [ -z "$cle" ] || [ "${nom%-*}" = "$cle" ] || continue
      printf '%s %s\n' "$(mtime "$d/.utilise")" "$d"
    done
  done | sort -n
}
evincer() {   # deux caches au plus par projet et par clé, puis le budget ; jamais $CACHE, jamais un cache tenu
  local l c n
  local -a caches=()
  while IFS= read -r l; do caches+=("${l#* }"); done < <(lister_caches "$DEPS_RACINE" -- "$ECH_CLE")
  n=${#caches[@]}
  for c in "${caches[@]}"; do
    [ "$n" -le 2 ] && break
    [ "$c" = "$CACHE" ] && continue
    effacer_cache "$c" && n=$((n - 1))
  done
  caches=()
  while IFS= read -r l; do caches+=("${l#* }"); done < <(lister_caches "$TESTS/.deps"/*)
  for c in "${caches[@]}"; do
    n=$(du_ko "$TESTS/.deps") || break   # COÛT CONNU (M6) : du de tout ~/tests/.deps à chaque éviction
    [ "$n" -gt $((BUDGET * 1048576)) ] || break
    [ "$c" = "$CACHE" ] || effacer_cache "$c"
  done
}
essayer_volume() {   # essayer_volume <volume> : un conteneur bref, sans réseau, le monte et y écrit (copie sur écriture réelle)
  dk 120 run --rm --pull never --name "essai-${1#tests-}" --label myiafactory.genre=tests-deps --log-driver none \
    --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000 \
    --pids-limit 64 --memory 128m --memory-swap 128m --mount "type=volume,src=$1,dst=/v" --entrypoint /bin/sh "$IMAGE" \
    -c 'test -d /v && : > /v/.essai-ecriture && rm -f /v/.essai-ecriture' >/dev/null 2>&1
}

# --- Wrapper et distribution Gradle (I4). LE CONTRÔLE DU WRAPPER N'EST PAS UNE BARRIÈRE : l'échauffement Gradle exécute de
# toute façon les scripts du projet ; la barrière est le conteneur (sans secret, durci, borné) et le mandataire (liste
# fermée). Ce contrôle écarte seulement un wrapper altéré (code arbitraire au tout premier lancement) et garde la
# distribution hors du conteneur : elle est téléchargée par l'hôte, vérifiée, puis copiée dans le cache.
SOMMES="$TESTS/.deps/.gradle-wrapper"
telecharger() {   # telecharger <url> <fichier> : https seulement, sans suivre de redirection, borné
  timeout -k 10 60 curl -fsS --proto =https --max-time 50 -o "$2" "$1" </dev/null >/dev/null 2>&1 8>&-
}
somme_publiee() {   # somme_publiee <version> : 0 si $SOMMES/<version>.sha256 (somme officielle) est là, récupérée au besoin
  local v="$1" f="$SOMMES/$1.sha256" o
  [ -f "$f" ] && [ ! -L "$f" ] && return 0
  rm -f -- "$f.tmp-$ID"
  telecharger "$SOMMES_GRADLE_URL/gradle-$v-wrapper.jar.sha256" "$f.tmp-$ID" || { rm -f -- "$f.tmp-$ID"; return 1; }
  o=$(head -c 200 -- "$f.tmp-$ID" 2>/dev/null | tr -d ' \r\n'); rm -f -- "$f.tmp-$ID"
  [[ $o =~ ^[0-9a-f]{64}$ ]] || return 2
  printf '%s\n' "$o" > "$f.tmp-$ID" && mv -f -- "$f.tmp-$ID" "$f"
}
somme_connue() { local f; for f in "$SOMMES"/*.sha256; do [ -f "$f" ] && grep -qxF -- "$1" "$f" && return 0; done; return 1; }
GRADLE_VERSION=""; GRADLE_GENRE=""; GRADLE_HACHE=""
# Le dossier des sommes et des distributions est partagé par les campagnes : une seule à la fois l'écrit (descripteur 3,
# rendu à la fin de chaque fonction ; finir le ferme aussi). Les temporaires portent en plus l'identifiant de la campagne.
tenir_sommes() { exec 3>> "$SOMMES/.verrou" && flock -x -w 1200 3 || deps_echec sommes-gradle-inaccessibles; }
lacher_sommes() { exec 3>&-; }
verifier_wrapper() {   # le jar de l'instantané doit être l'un des wrappers PUBLIÉS par Gradle (toutes versions), sinon 79
  local ligne r raison somme v debut
  ligne=$(python3 -I "$AIDE" --wrapper "$ENTREE/entree.tar" 2>"$DOSSIER/.wrapper.err"); r=$?
  raison=$(head -n 1 "$DOSSIER/.wrapper.err" 2>/dev/null | tr -cd 'a-z-' | head -c 60); rm -f -- "$DOSSIER/.wrapper.err"
  [ "$r" = 3 ] && deps_echec "${raison:-wrapper-illisible}"
  [ "$r" = 0 ] || deps_echec wrapper-illisible
  [[ $ligne =~ ^([0-9a-f]{64})\ ([0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,2})?(-rc-[0-9]{1,2})?)\ (bin|all)\ ([0-9a-z]{1,30})$ ]] ||
    deps_echec wrapper-illisible
  somme="${BASH_REMATCH[1]}"; GRADLE_VERSION="${BASH_REMATCH[2]}"; GRADLE_GENRE="${BASH_REMATCH[5]}"; GRADLE_HACHE="${BASH_REMATCH[6]}"
  mkdir -p -m 700 -- "$SOMMES" 2>/dev/null
  [ -d "$SOMMES" ] && [ ! -L "$SOMMES" ] && [ -O "$SOMMES" ] || deps_echec sommes-gradle-inaccessibles
  command -v curl >/dev/null 2>&1 || deps_echec curl-absent
  tenir_sommes
  somme_publiee "$GRADLE_VERSION"; r=$?
  [ "$r" = 1 ] && deps_echec somme-gradle-injoignable
  [ "$r" = 2 ] && deps_echec somme-gradle-illisible
  somme_connue "$somme" && { lacher_sommes; return 0; }
  # Jar d'une autre version : la liste officielle de toutes les versions (rafraîchie au plus une fois par jour), puis la somme
  # publiée de chacune (seulement l'URL officielle attendue, jamais une URL lue dans la réponse ; 600 s au plus).
  # `.liste` n'est posée (pour 24 h) que si la liste est COMPLÈTE : non vide, chaque somme obtenue, avant les 600 s.
  if [ -z "$(find "$SOMMES/.liste" -mmin -1440 2>/dev/null)" ]; then
    local json="$SOMMES/versions.json.$ID" complete=1 vues=0
    rm -f -- "$json"
    telecharger "$VERSIONS_GRADLE_URL" "$json" || { rm -f -- "$json"; deps_echec somme-gradle-injoignable; }
    debut=$(date +%s)
    while IFS= read -r v; do
      v="${v%$'\r'}"                                   # python sous Windows (bancs) écrit \r\n
      [[ $v =~ ^[0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,2})?(-rc-[0-9]{1,2})?$ ]] || continue
      if [ $(($(date +%s) - debut)) -ge 600 ]; then complete=0; break; fi
      vues=$((vues + 1))
      somme_publiee "$v" || complete=0
    done < <(python3 -I "$AIDE" --versions-gradle "$json" 2>/dev/null)
    rm -f -- "$json"
    [ "$complete" = 1 ] && [ "$vues" -gt 0 ] && : > "$SOMMES/.liste"
  fi
  lacher_sommes
  somme_connue "$somme" || deps_echec wrapper-modifie
}
distribution_gradle() {   # distribution_gradle <contenu du cache en préparation> : téléchargée par l'HÔTE, vérifiée, copiée
  local nom="gradle-$GRADLE_VERSION-$GRADLE_GENRE.zip" d="$SOMMES/dist" url r loc h i officielle somme dest t
  mkdir -p -m 700 -- "$d" 2>/dev/null
  [ -d "$d" ] && [ ! -L "$d" ] || deps_echec sommes-gradle-inaccessibles
  tenir_sommes
  t="$d/$nom.tmp-$ID"
  # Une distribution gardée n'est crue que si sa somme est celle, OFFICIELLE, gardée avec elle (zip tronqué, somme absente ou
  # différente : effacée et retéléchargée) ; jamais seulement parce que le fichier existe.
  if [ -f "$d/$nom" ] && [ ! -L "$d/$nom" ] && [ -f "$d/$nom.sha256" ] &&
     [ "$(sha256sum -- "$d/$nom" 2>/dev/null | cut -d' ' -f1)" = "$(head -c 64 -- "$d/$nom.sha256" 2>/dev/null)" ]; then
    :
  else
    rm -f -- "$d/$nom" "$d/$nom.sha256" "$t"
    url="$SOMMES_GRADLE_URL/$nom"
    for i in 1 2 3 4 5; do
      [ "$i" = 5 ] && { rm -f -- "$t"; deps_echec distribution-redirection; }
      r=$(timeout -k 10 900 curl -sS --proto =https --max-time 880 -o "$t" -w '%{http_code} %{redirect_url}' \
            "$url" </dev/null 2>/dev/null 8>&-) || { rm -f -- "$t"; deps_echec distribution-injoignable; }
      case "$r" in
        "200 "*) break ;;
        30[1278]\ https://*)                            # redirection suivie à la main : seulement vers DIST_HOTES
          loc="${r#* }"; h="${loc#https://}"; h="${h%%/*}"
          [[ $DIST_HOTES == *" $h "* ]] && [[ $loc =~ ^https://[a-z0-9.-]{1,253}/[A-Za-z0-9._/%+=-]{1,500}$ ]] ||
            { rm -f -- "$t"; deps_echec distribution-redirection; }
          url="$loc" ;;
        *) rm -f -- "$t"; deps_echec distribution-injoignable ;;
      esac
    done
    telecharger "$SOMMES_GRADLE_URL/$nom.sha256" "$t.sha256" || { rm -f -- "$t" "$t.sha256"; deps_echec distribution-injoignable; }
    officielle=$(head -c 200 -- "$t.sha256" 2>/dev/null | tr -d ' \r\n'); rm -f -- "$t.sha256"
    somme=$(sha256sum -- "$t" 2>/dev/null | cut -d' ' -f1)
    if ! [[ $officielle =~ ^[0-9a-f]{64}$ ]] || [ "$somme" != "$officielle" ]; then
      rm -f -- "$t"; deps_echec distribution-somme
    fi
    printf '%s\n' "$officielle" > "$d/$nom.sha256" && mv -f -- "$t" "$d/$nom" || { rm -f -- "$t"; deps_echec ecriture; }
  fi
  # Là où le wrapper la cherche (GRADLE_USER_HOME=/deps/gradle) : une COPIE (jamais un lien dur : le conteneur écrit dans
  # contenu/ et ne doit pas pouvoir altérer la distribution vérifiée de l'hôte), revérifiée APRÈS la copie.
  dest="$1/gradle/wrapper/dists/gradle-$GRADLE_VERSION-$GRADLE_GENRE/$GRADLE_HACHE"
  mkdir -p -- "$dest" && cp -- "$d/$nom" "$dest/$nom" || deps_echec ecriture
  [ "$(sha256sum -- "$dest/$nom" 2>/dev/null | cut -d' ' -f1)" = "$(head -c 64 -- "$d/$nom.sha256")" ] ||
    { rm -f -- "$dest/$nom"; deps_echec distribution-somme; }
  lacher_sommes
}

# SDK Android de l'hôte en copie sur écriture : AGP peut écrire (.temp, licences, .knownPackages) dans la couche haute, effacée
# avec le dossier ; ~/android-sdk n'est jamais inscriptible par un conteneur. Overlay refusé (création ou essai) : lecture seule.
SDK_MONTAGE=()
if [ "$FAMILLE" = gradle-android ]; then
  SDK_MONTAGE=(-v "$HOME/android-sdk:/opt/android-sdk:ro")
  mkdir -p -m 700 -- "$TESTS/.deps" 2>/dev/null          # le balayage des volumes tests-sdk- s'y fie
  if mkdir -m 700 -- "$DOSSIER/sdk-haut" "$DOSSIER/sdk-ov" 2>/dev/null; then
    VOLUMES+=("tests-sdk-$ID")
    if dk 30 volume create --driver local --label myiafactory.genre=tests-deps --opt type=overlay --opt device=overlay \
         --opt "o=lowerdir=$HOME/android-sdk,upperdir=$DOSSIER/sdk-haut,workdir=$DOSSIER/sdk-ov" "tests-sdk-$ID" >/dev/null 2>&1 &&
       essayer_volume "tests-sdk-$ID"; then
      SDK_MONTAGE=(--mount "type=volume,src=tests-sdk-$ID,dst=/opt/android-sdk")
    else
      printf '%s\n' "lancer_tests : copie sur écriture du SDK indisponible : SDK monté en lecture seule." >&2
    fi
  fi
  SDK_MONTAGE+=(-e ANDROID_HOME=/opt/android-sdk)
fi

prendre_echauffement() {   # une des ECHAUFFEMENTS_MAX places d'échauffement (descripteur 6), en file avec #attente
  local i dit="" dernier_t=0 maintenant
  mkdir -p -m 700 -- "$HOME/taches" 2>/dev/null
  while :; do
    for ((i = 1; i <= ECHAUFFEMENTS_MAX; i++)); do
      exec 6>> "$HOME/taches/.echauffement-$i" || deps_echec ecriture
      flock -n 6 && return 0
      exec 6>&-
    done
    [ -e "$DOSSIER/laisse-coupee" ] && finir 130
    maintenant=$(date +%s)
    if [ -z "$dit" ] || [ $((maintenant - dernier_t)) -ge 30 ]; then
      printf '#attente 1 1\n' >&2; dit=1; dernier_t=$maintenant
    fi
    sleep "$SONDE"
  done
}

# Réseau interne + mandataire éphémère (liste fermée d'hôtes) : l'échauffement (§ 5.13) et la licence B3 (§ 5.16).
# ouvrir_mandataire <durée_s> <hôte>... : 0 et RESEAU_MANDATAIRE (les options docker run du conteneur client : réseau interne,
# DNS coupé, mandataire joint par --add-host, variables de mandataire) ; 1 réseau interne impossible ; 2 mandataire en échec.
# Le réseau et le mandataire sont TOUJOURS fermés par fermer_reseau (finir, ou l'appelant).
RESEAU_MANDATAIRE=()
ouvrir_mandataire() {
  local duree="$1" ip p; shift
  DEPS_RESEAU="deps-$ID"
  dk 30 network create --internal --label myiafactory.genre=tests-deps "deps-$ID" >/dev/null 2>&1 || return 1
  MANDATAIRE=1
  # Créé sur le réseau INTERNE seul (il y écoute, et seulement là), puis branché au bridge pour sortir ; toujours l'image de
  # base myiafactory/tests (jamais une image dérivée : elle porte des outils de plus et ne sert qu'au code du projet).
  dk 60 run -d --pull never --init --name "mandataire-$ID" --label myiafactory.genre=tests-deps --log-driver none \
    --network "deps-$ID" --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000 \
    --pids-limit 256 --memory 256m --memory-swap 256m --cpus 1 --tmpfs /tmp:size=16m \
    -v "$AIDE:/opt/myiafactory/tests_hote.py:ro" --entrypoint python3 myiafactory/tests \
    -I /opt/myiafactory/tests_hote.py --mandataire 3128 "$duree" "$@" >/dev/null 2>&1 || return 2
  dk 30 network connect bridge "mandataire-$ID" >/dev/null 2>&1 || return 2
  ip=$(dk 20 inspect -f "{{(index .NetworkSettings.Networks \"deps-$ID\").IPAddress}}" "mandataire-$ID" 2>/dev/null)
  [[ $ip =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 2
  p="http://mandataire:3128"
  RESEAU_MANDATAIRE=(--network "deps-$ID" --dns 0.0.0.0 --add-host "mandataire:$ip"
    -e "HTTPS_PROXY=$p" -e "HTTP_PROXY=$p" -e "https_proxy=$p" -e "http_proxy=$p" -e "NO_PROXY=localhost,127.0.0.1"
    -e "JAVA_TOOL_OPTIONS=-Dhttps.proxyHost=mandataire -Dhttps.proxyPort=3128 -Dhttp.proxyHost=mandataire -Dhttp.proxyPort=3128")
  return 0
}

echauffer() {
  local duree plafond code r ko hotes de="$DOSSIER/deps-entree" tmp="$CACHE.tmp"
  read -r duree plafond code <<< "${ECH[$ECH_CLE]}"
  local memoire=$((MEMOIRE + plafond * 1024)) depart   # le tmpfs /work compte dans --memory : il s'y ajoute
  [ "$ECH_CLE" = unity ] && deps_echec unity-tache-14g
  [ "$code" = 1 ] && [ "$RESEAU" != accorde ] && deps_echec reseau-non-accorde
  mkdir -p -m 700 -- "$DEPS_RACINE" 2>/dev/null
  for d in "$TESTS/.deps" "$DEPS_RACINE"; do
    [ -d "$d" ] && [ ! -L "$d" ] && [ -O "$d" ] || deps_echec cache-inaccessible
  done
  exec 7>> "$DEPS_RACINE/.$ECH_CLE-$DEPS.echauffement" || deps_echec cache-inaccessible
  flock -x -w $((duree + 300)) 7 || deps_echec echauffement-concurrent
  if cache_pret "$CACHE" && ! cache_perime "$CACHE"; then exec 7>&-; return 0; fi   # préparé pendant l'attente
  memoire_echec                                         # un autre vient peut-être d'échouer
  prendre_echauffement
  ECHAUFFE=1
  TMP_CACHE="$tmp"
  if [ -d "$tmp" ] && [ ! -L "$tmp" ]; then chmod -R u+rwX -- "$tmp" 2>/dev/null; fi
  rm -rf -- "$tmp"
  mkdir -m 700 -- "$tmp" "$tmp/contenu" "$tmp/meta" "$de" || deps_echec ecriture
  ln -- "$ENTREE/entree.tar" "$de/entree.tar" 2>/dev/null || cp -- "$ENTREE/entree.tar" "$de/entree.tar" || deps_echec ecriture
  printf '["python3","-I","/opt/myiafactory/tests_hote.py","--echauffer","%s","%s"]' "$ECH_CLE" "$FAMILLE" > "$de/commande.json" ||
    deps_echec ecriture
  [ "$ECH_CLE" = gradle ] && distribution_gradle "$tmp/contenu"
  # /work : tmpfs borné (taille = plafond de la clé, inodes = INODES_MAX), jamais le disque de l'hôte.
  local -a run=(run --pull never --init --name "deps-$ID" --label myiafactory.genre=tests-deps --log-driver none
    --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000
    --pids-limit 2048 --ulimit nofile=8192:8192 --ulimit core=0
    --memory "${memoire}m" --memory-swap "${memoire}m" --cpus "$CPUS"
    --tmpfs /tmp:size=4g,mode=1777,exec --tmpfs "/work:size=${plafond}g,nr_inodes=$INODES_MAX,mode=1777,exec"
    -v "$de:/entree:ro" -v "$tmp/contenu:/deps" -v "$tmp/meta:/deps-meta"
    -v "$AIDE:/opt/myiafactory/tests_hote.py:ro" "${SDK_MONTAGE[@]}")
  # Réseau : TOUJOURS interne + mandataire (liste fermée), jamais bridge ; DNS coupé, le mandataire joint par --add-host.
  read -r -a hotes <<< "${ECH_HOTES[$ECH_CLE]-}"
  [ "${#hotes[@]}" -gt 0 ] || deps_echec reseau-sans-liste
  ouvrir_mandataire $((duree + 120)) "${hotes[@]}"
  case $? in 0) ;; 1) deps_echec reseau-interne ;; *) deps_echec mandataire ;; esac
  run+=("${RESEAU_MANDATAIRE[@]}" -e HOME=/tmp -e MYIAFACTORY_TESTS_CONTENEUR=1 "$IMAGE")
  printf '%s\n' "lancer_tests : échauffement des dépendances ($ECH_CLE, ${duree} s et ${plafond} Go au plus)." >&2
  rm -f -- "$DOSSIER/deps-plafond" "$DOSSIER/deps-inodes" "$DOSSIER/deps-disque"
  # Surveillant de l'échauffement : plafond (taille, inodes) du cache, disque ; la laisse tue deps-<id> elle aussi.
  ( trap - TERM INT HUP PIPE
    du_t=0
    while sleep "$SONDE" 6>&- 7>&-; do
      enveloppe_vivante "$ID" || { dk 30 kill "deps-$ID" >/dev/null 2>&1; exit 0; }
      l=$(disque_libre_ko)
      if [[ $l =~ ^[0-9]{1,15}$ ]] && [ "$l" -lt "$DISQUE_ARRET_KO" ]; then : > "$DOSSIER/deps-disque"; dk 30 kill "deps-$ID" >/dev/null 2>&1; fi
      maintenant=$(date +%s)
      [ $((maintenant - du_t)) -ge "$DU_S" ] || continue
      ko=$(du_ko "$tmp"); n=$(du_inodes "$tmp"); du_t=$(date +%s)   # la période repart à la FIN de du
      if [[ $ko =~ ^[0-9]+$ ]] && [ "$ko" -gt $((plafond * 1048576)) ]; then
        : > "$DOSSIER/deps-plafond"; dk 30 kill "deps-$ID" >/dev/null 2>&1
      fi
      if [[ $n =~ ^[0-9]+$ ]] && [ "$n" -gt "$INODES_MAX" ]; then
        : > "$DOSSIER/deps-inodes"; dk 30 kill "deps-$ID" >/dev/null 2>&1
      fi
    done ) >/dev/null 2>&1 6>&- 7>&- &
  PID_SURVEILLANT=$!
  DEPS_CONTENEUR=1
  depart=$(date +%s)
  timeout -k 30 "$duree" sudo -n docker "${run[@]}" </dev/null 2>&1 6>&- 7>&- 8>&- |
    python3 -I "$AIDE" --couper "$DOSSIER/deps-journal-coupe" 1048576 > "$DOSSIER/deps.log" 6>&- 7>&- 8>&-
  r=${PIPESTATUS[0]}
  { kill "$PID_SURVEILLANT"; wait "$PID_SURVEILLANT"; } 2>/dev/null
  PID_SURVEILLANT=""
  dk 30 rm -f "deps-$ID" >/dev/null 2>&1 && DEPS_CONTENEUR=0
  fermer_reseau
  exec 6>&-                                             # place d'échauffement rendue
  [ -e "$DOSSIER/laisse-coupee" ] && finir 130
  [ -e "$DOSSIER/deps-disque" ] && deps_echec disque
  ko=$(du_ko "$tmp") || ko=0
  { [ -e "$DOSSIER/deps-plafond" ] || [ "$ko" -gt $((plafond * 1048576)) ]; } && deps_echec plafond
  n=$(du_inodes "$tmp") || n=0
  { [ -e "$DOSSIER/deps-inodes" ] || [ "$n" -gt "$INODES_MAX" ]; } && deps_echec inodes
  if [ ! -f "$tmp/meta/ok" ]; then
    if [ "$r" = 124 ] || { [ "$r" = 137 ] && [ $(($(date +%s) - depart)) -ge "$duree" ]; }; then deps_echec duree; fi
    [ "$r" = 137 ] && deps_echec memoire                 # tué sans marque du surveillant ni échéance : mémoire (OOM)
  fi
  if [ "$r" != 0 ] || [ ! -f "$tmp/meta/ok" ]; then
    tail -n 20 -- "$DOSSIER/deps.log" 2>/dev/null | tr '\000-\011\013-\037\177' '?' |
      sed -e 's/\xc2\x85/?/g' -e 's/\xe2\x80\xa8/?/g' -e 's/\xe2\x80\xa9/?/g' -e 's/^/| /' | head -c 4096 >&2
    deps_echec echauffement
  fi
  if [ -f "$tmp/meta/verrou-produit" ] && [ ! -L "$tmp/meta/verrou-produit" ]; then
    mv -f -- "$tmp/meta/verrou-produit" "$tmp/.verrou-produit"   # jamais réécrit dans le projet
  fi
  [ -f "$tmp/meta/non-verrouille" ] && : > "$tmp/.non-verrouille"
  rm -rf -- "$tmp/meta" "$de"
  : > "$tmp/.utilise"
  if [ -d "$CACHE" ] && ! effacer_cache "$CACHE"; then   # rafraîchissement d'un cache tenu par une autre campagne : gardé
    chmod -R u+rwX -- "$tmp" 2>/dev/null; rm -rf -- "$tmp"; TMP_CACHE=""
    printf '%s\n' "lancer_tests : cache tenu par une autre campagne : l'ancien est gardé." >&2
    ECHAUFFE=0; exec 7>&-; return 0
  fi
  mv -- "$tmp" "$CACHE" || deps_echec ecriture
  TMP_CACHE=""
  date +%s > "$CACHE/.pret" || deps_echec ecriture
  rm -f -- "$DEPS_RACINE/$ECH_CLE-$DEPS.echec"
  ECHAUFFE=0
  exec 7>&-
}

if [ -n "$CACHE" ]; then
  [ "$ECH_CLE" = gradle ] && verifier_wrapper            # avant TOUT lancement Gradle (échauffement et tests)
  if ! cache_pret "$CACHE" || cache_perime "$CACHE"; then
    [ -d "$DEPS_RACINE" ] && memoire_echec
    echauffer
  fi
  exec 5>> "$(verrou_de "$CACHE")" || deps_echec cache-inaccessible
  flock -s 5 || deps_echec cache-verrou                  # tenu pendant toute la campagne : jamais évincé sous nos pieds
  cache_pret "$CACHE" || deps_echec cache-disparu        # évincé (renommé) entre-temps
  touch -- "$CACHE/.utilise"
  evincer
  mkdir -m 700 -- "$DOSSIER/deps-haut" "$DOSSIER/deps-ov" || deps_echec ecriture
  VOLUMES+=("tests-deps-$ID")
  dk 30 volume create --driver local --label myiafactory.genre=tests-deps --opt type=overlay --opt device=overlay \
    --opt "o=lowerdir=$CACHE/contenu,upperdir=$DOSSIER/deps-haut,workdir=$DOSSIER/deps-ov" "tests-deps-$ID" >/dev/null 2>&1 ||
    deps_echec copie-sur-ecriture
  essayer_volume "tests-deps-$ID" || deps_echec copie-sur-ecriture   # le volume se monte vraiment (I1)
fi

# --- File et place -------------------------------------------------------------

FILE="$TESTS/.file"
mkdir -p -m 700 -- "$FILE" 2>/dev/null
[ -d "$FILE" ] && [ ! -L "$FILE" ] || echouer 1 "file ~/tests/.file inaccessible."
mkdir -p -m 700 -- "$HOME/taches" 2>/dev/null
NOM_TICKET="$(date +%s%N)-$ID"
[[ $NOM_TICKET =~ ^[0-9]{10,20}-t ]] || echouer 1 "horloge illisible (date +%s%N)."
printf '%s\n' "$$" > "$FILE/.$NOM_TICKET.tmp" && mv -f -- "$FILE/.$NOM_TICKET.tmp" "$FILE/$NOM_TICKET" || echouer 1 "ticket non écrit."
TICKET="$FILE/$NOM_TICKET"

prendre_place() {   # 0 si une place est prise (descripteur 8)
  local i tenues=0 creneau=""
  for ((i = 1; i <= PLACES_MAX; i++)); do
    exec 9>> "$HOME/taches/.creneau-tests-$i" || echouer 1 "place de tests inaccessible."
    if flock -n 9; then
      if [ -z "$creneau" ] && [ "$i" -le "$PLACES" ]; then creneau="$i"; exec 8>&9; else flock -u 9; fi
    else
      tenues=$((tenues + 1))
    fi
    exec 9>&-
  done
  [ -n "$creneau" ] || return 1
  if [ "$tenues" -ge "$PLACES" ]; then liberer_creneau; return 1; fi
  return 0
}

# `#attente … libres` est une photo : pendant un passage de prise/relâche (le premier ticket tient un instant les jetons libres
# le temps de choisir) elle peut être fausse de 1 à 2 unités en moins ; jamais en trop pour le budget, que seuls les jetons
# gardés (mes + autres < budget) engagent.
JETONS_LIBRES=0
compter_jetons_libres() {   # sans rien garder : JETONS_LIBRES = budget - (tenus par d'autres) - (les miens)
  local k f autres=0
  for ((k = 1; k <= JETONS_MAX; k++)); do
    [ -n "${MES_JETONS[$k]+x}" ] && continue
    exec {f}>> "$HOME/taches/.jeton-tests-$k" || echouer 1 "jeton de mémoire inaccessible."
    if flock -n "$f"; then flock -u "$f"; else autres=$((autres + 1)); fi
    exec {f}>&-
  done
  JETONS_LIBRES=$((BUDGET_U - autres - ${#MES_JETONS[@]})); [ "$JETONS_LIBRES" -ge 0 ] || JETONS_LIBRES=0
}
tenir_jetons() {   # un passage, réservé au premier ticket (le poids atteint, il n'est plus appelé) ; jamais plus de BUDGET_U tenus en tout
  local k f autres=0 i
  local -a nums=() fds=()
  for ((k = 1; k <= JETONS_MAX; k++)); do
    [ -n "${MES_JETONS[$k]+x}" ] && continue
    exec {f}>> "$HOME/taches/.jeton-tests-$k" || echouer 1 "jeton de mémoire inaccessible."
    if flock -n "$f"; then nums+=("$k"); fds+=("$f"); else autres=$((autres + 1)); exec {f}>&-; fi
  done
  # Les libres sont tenus le temps du choix : personne d'autre ne peut les prendre ; gardés seulement ceux qu'il faut.
  for ((i = 0; i < ${#nums[@]}; i++)); do
    if [ "${#MES_JETONS[@]}" -lt "$POIDS" ] && [ $((${#MES_JETONS[@]} + autres)) -lt "$BUDGET_U" ]; then
      MES_JETONS[${nums[$i]}]="${fds[$i]}"
    else
      f="${fds[$i]}"; flock -u "$f" 2>/dev/null; exec {f}>&-
    fi
  done
  JETONS_LIBRES=$((BUDGET_U - autres - ${#MES_JETONS[@]})); [ "$JETONS_LIBRES" -ge 0 ] || JETONS_LIBRES=0
}

DEBUT_ATTENTE=$(date +%s); dernier=""; dernier_l=""; dernier_t=0
while :; do
  rang=1; total=0
  for t in "$FILE"/*; do
    [ -f "$t" ] && [ ! -L "$t" ] || continue
    nom="${t##*/}"
    if [ "$t" = "$TICKET" ]; then total=$((total + 1)); continue; fi
    if ! [[ $nom =~ ^[0-9]{10,20}-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$ ]]; then rm -f -- "$t"; continue; fi
    autre="${BASH_REMATCH[1]}"
    if processus_vivant "$t" "lancer_tests.sh" "$autre"; then
      total=$((total + 1))
      [[ $nom < $NOM_TICKET ]] && rang=$((rang + 1))
    else
      rm -f -- "$t"                                   # ticket mort : son enveloppe ne vit plus
    fi
  done
  connu=0
  if [ "$rang" = 1 ]; then
    if [ "${#MES_JETONS[@]}" -lt "$POIDS" ]; then tenir_jetons; connu=1; fi   # le poids atteint : plus rien à sonder
    if [ "${#MES_JETONS[@]}" -ge "$POIDS" ] && prendre_place; then break; fi
  elif [ "${#MES_JETONS[@]}" -gt 0 ]; then
    liberer_jetons                                    # plus le premier (un plus ancien est arrivé) : jamais de jeton en attente d'un autre
  fi
  maintenant=$(date +%s)
  if [ "$rang $total" != "$dernier" ] || { [ "$connu" = 1 ] && [ "$JETONS_LIBRES" != "$dernier_l" ]; } ||
     [ $((maintenant - dernier_t)) -ge 30 ]; then
    [ "$connu" = 1 ] || compter_jetons_libres
    printf '#attente %s %s %s
' "$rang" "$total" "$JETONS_LIBRES" >&2
    dernier="$rang $total"; dernier_l="$JETONS_LIBRES"; dernier_t=$maintenant
  fi
  sleep "$SONDE"
done
rm -f -- "$TICKET"; TICKET=""
DEBUT=$(date +%s)
ATTENTE=$((DEBUT - DEBUT_ATTENTE))

# --- Conteneur ------------------------------------------------------------------

# Réseau des tests : AUCUN (--network none), sauf la licence B3 (réseau interne + mandataire vers les seuls hôtes de licence,
# accord du Directeur vérifié par la route). /tmp : 4 Go, 6 Go pour Unity (préférences, caches de l'éditeur, copie de licence).
RESEAU_TESTS=(--network none); TMP_GO=4
[ "$FAMILLE" = unity ] && TMP_GO=6
if [ "$LICENCE" = B3 ]; then
  mkdir -p -m 700 -- "$TESTS/.deps" 2>/dev/null          # le balayage des réseaux deps- et des mandataires s'y fie
  ouvrir_mandataire $((DUREE + 120)) "${HOTES_B3[@]}"
  case $? in 0) ;; 1) echouer 77 "réseau interne de la licence B3 impossible." ;; *) echouer 77 "mandataire de la licence B3 en échec." ;; esac
  RESEAU_TESTS=("${RESEAU_MANDATAIRE[@]}")
fi
COMMANDE=(run --pull never --init --name "tests-$ID" --label myiafactory.genre=tests --log-driver none
  "${RESEAU_TESTS[@]}" --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000
  --pids-limit 2048 --ulimit nofile=8192:8192 --ulimit core=0
  --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS"
  --tmpfs "/tmp:size=${TMP_GO}g,mode=1777,exec"
  -v "$DOSSIER/travail:/work" -v "$ENTREE:/entree:ro" "${LICENCE_ARGS[@]}")
# Cache de dépendances : copie sur écriture (volume overlay, basse = le cache figé), jamais le cache lui-même.
if [ -n "$CACHE" ]; then
  COMMANDE+=(--mount "type=volume,src=tests-deps-$ID,dst=/deps")
  # Variables hors ligne par clé (table fermée, § 5.13), écrites ici, jamais lues du poste.
  case "$ECH_CLE" in
    npm|pnpm|yarn) COMMANDE+=(-e npm_config_offline=true) ;;
    pip|pip-sources) COMMANDE+=(-e "PATH=/deps/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
                                -e VIRTUAL_ENV=/deps/venv -e PIP_NO_INDEX=1) ;;
    maven) COMMANDE+=(-e "MAVEN_OPTS=-Dmaven.repo.local=/deps/m2" -e MAVEN_USER_HOME=/deps/m2home) ;;
    dotnet) COMMANDE+=(-e NUGET_PACKAGES=/deps/nuget -e DOTNET_CLI_HOME=/tmp) ;;
    cargo) COMMANDE+=(-e CARGO_HOME=/deps/cargo -e CARGO_NET_OFFLINE=true) ;;
    go) COMMANDE+=(-e GOMODCACHE=/deps/gomod -e GOFLAGS=-mod=readonly -e GOPROXY=off -e GOPATH=/tmp/go) ;;
  esac
fi
# Table fermée par famille : montages et variables écrits ici, jamais lus du poste.
# Gradle : GRADLE_USER_HOME inscriptible : /deps/gradle (le cache d'échauffement, copie sur écriture : distribution du wrapper
# et caches/modules-2 hors ligne), sinon /tmp/gradle (tmpfs).
case "$FAMILLE" in
  gradle-android|gradle-jvm)
    COMMANDE+=("${SDK_MONTAGE[@]}" -e "GRADLE_OPTS=$GRADLE_OPTS_FERME")
    if [ -n "$CACHE" ] && [ "$ECH_CLE" = gradle ]; then COMMANDE+=(-e GRADLE_USER_HOME=/deps/gradle)
    else COMMANDE+=(-e GRADLE_USER_HOME=/tmp/gradle); fi ;;
esac
COMMANDE+=(-e HOME=/tmp -e MYIAFACTORY_TESTS_CONTENEUR=1 "$IMAGE")

# Surveillant : garde la place (descripteur 8) tant qu'il vit ; tue le conteneur (marque d'abord) si le disque, les inodes
# ou travail/ débordent, si l'échéance est dépassée malgré timeout, si la laisse est coupée (et arrête l'enveloppe, tant
# qu'elle vit), ou si l'enveloppe a disparu.
# du : en arrière-plan (les autres sondes restent à 0,5 s), borné (timeout 60), de basse priorité (nice, ionice -c3 si
# présents) ; son résultat arrive par le fichier .du (temporaire puis mv) et la période repart quand il est FINI.
DU=(du -sk --)
if command -v ionice >/dev/null 2>&1; then DU=(ionice -c3 "${DU[@]}"); fi
if command -v nice >/dev/null 2>&1; then DU=(nice -n 19 "${DU[@]}"); fi
DU=(timeout 60 "${DU[@]}" "$DOSSIER/travail")
( trap - TERM INT HUP PIPE
  arreter() { : > "$DOSSIER/$1"; "$ARRETER"; }
  echeance=$(( $(date +%s) + DUREE + MARGE )); du_t=0; du_en_cours=0
  rm -f -- "$DOSSIER/.du" "$DOSSIER/.du.tmp"
  while sleep "$SONDE" 8>&-; do
    if [ -e "$DOSSIER/laisse-coupee" ]; then
      "$ARRETER"
      enveloppe_vivante "$ID" && kill -TERM "$$" 2>/dev/null
      continue
    fi
    enveloppe_vivante "$ID" || { "$ARRETER"; exit 0; }
    l=$(disque_libre_ko)
    if [[ $l =~ ^[0-9]{1,15}$ ]] && [ "$l" -lt "$DISQUE_ARRET_KO" ]; then arreter disque-plein; continue; fi
    if inodes_bas; then arreter inodes; continue; fi
    maintenant=$(date +%s)
    if [ "$du_en_cours" = 1 ] && [ -f "$DOSSIER/.du" ]; then
      ko=""; IFS= read -r ko < "$DOSSIER/.du"; rm -f -- "$DOSSIER/.du"
      du_en_cours=0; du_t=$maintenant                    # la période repart à la FIN de du
      if [[ $ko =~ ^[0-9]{1,15}$ ]] && [ "$ko" -gt "$TRAVAIL_MAX_KO" ]; then arreter travail-plein; continue; fi
    fi
    if [ "$du_en_cours" = 0 ] && [ $((maintenant - du_t)) -ge "$DU_S" ]; then
      du_en_cours=1
      ( ko=$("${DU[@]}" 2>/dev/null 8>&- | cut -f1)
        printf '%s\n' "$ko" > "$DOSSIER/.du.tmp" && mv -f -- "$DOSSIER/.du.tmp" "$DOSSIER/.du" ) 8>&- &
    fi
    [ "$maintenant" -lt "$echeance" ] || arreter echeance
  done ) >/dev/null 2>&1 &
PID_SURVEILLANT=$!

[ -e "$DOSSIER/laisse-coupee" ] && finir 130          # laisse coupée avant le départ : rien ne démarre
CONTENEUR=1
{
  { "$LANCER" </dev/null 2>&1 1>&3 3>&- 8>&-
    printf '%s\n' "$?" > "$DOSSIER/code"
  } | python3 -I "$AIDE" --prefixer "$DOSSIER/erreur-coupee" "$SORTIE_MAX" >&2 3>&- 8>&-
} 3>&1 | python3 -I "$AIDE" --couper "$DOSSIER/sortie-coupee" "$SORTIE_MAX" 8>&-

# Le surveillant est arrêté (et attendu) AVANT de lire ses marques : une marque posée après la fin du conteneur ne change
# jamais un code rendu par lui.
{ kill "$PID_SURVEILLANT"; wait "$PID_SURVEILLANT"; } 2>/dev/null
PID_SURVEILLANT=""
# Origine du code : les marques de l'hôte d'abord (posées AVANT tout kill), puis l'état final lu par docker inspect.
[ -e "$DOSSIER/laisse-coupee" ] && finir 130
[ -e "$DOSSIER/disque-plein" ] && echouer 74 "disque presque plein pendant la campagne : conteneur arrêté."
[ -e "$DOSSIER/inodes" ] && echouer 74 "inodes presque épuisés pendant la campagne : conteneur arrêté."
[ -e "$DOSSIER/travail-plein" ] && echouer 74 "travail/ au-delà de ${TRAVAIL_GO} Go : conteneur arrêté."
[ -e "$DOSSIER/echeance" ] && echouer 74 "échéance du surveillant dépassée (${DUREE} s + ${MARGE} s) : conteneur arrêté."
code=""; [ -f "$DOSSIER/code" ] && IFS= read -r code < "$DOSSIER/code"
[[ $code =~ ^[0-9]{1,3}$ ]] || echouer 1 "code de docker run illisible."
# Exécuteur hôte : pas de conteneur à inspecter. 124 : timeout (CONTENEUR reste 1 : finir arrête l'unité) ; 77 : refus du script
# racine (prérequis absent, rien n'a tourné ; la commande de l'unité ne rend jamais 77) ; sinon le code de la commande.
if [ "$EXECUTEUR" = hote_bac_a_sable ]; then
  [ "$code" = 124 ] && echouer 124 "durée maximale dépassée (${DUREE} s)."
  CONTENEUR=0                                           # --wait : l'unité est finie et ramassée
  [ "$code" = 77 ] && echouer 77 "bac à sable Unity : prérequis absent sur l'hôte (utilisateur unity-tests, éditeur, licence ou scripts) ; rien n'a tourné."
  finir "$code" conteneur
fi
# État final : « jamais démarré » SEULEMENT si le conteneur est absent, ou « created » avec StartedAt à la date nulle ; fini
# (exited, dead) après un vrai départ : code du conteneur ; tout le reste (running, restarting, paused, removing, inspect
# en panne, réponse illisible) : conteneur tué puis supprimé, 74 (le code de docker n'est jamais rendu comme un refus).
ZERO='0001-01-01T00:00:00Z'
etat=$(dk 20 inspect --type container -f '{{.State.Status}} {{.State.ExitCode}} {{.State.StartedAt}}' "tests-$ID" \
  2>"$DOSSIER/.inspect.err"); r=$?
erreur=$(head -c 4096 -- "$DOSSIER/.inspect.err" 2>/dev/null); rm -f -- "$DOSSIER/.inspect.err"
if [ "$r" != 0 ]; then
  case "${erreur,,}" in
    *"no such"*|*"not found"*)
      [ "$code" = 0 ] && code=1
      CONTENEUR=0
      echouer "$code" "le conteneur n'a jamais démarré (docker run : code $code ; conteneur absent)." ;;
  esac
  echouer 74 "état final du conteneur illisible (docker inspect en échec) : conteneur arrêté."
fi
if [[ $etat =~ ^created\ [0-9]{1,3}\ (.*)$ ]] && [ "${BASH_REMATCH[1]}" = "$ZERO" ]; then
  [ "$code" = 0 ] && code=1
  echouer "$code" "le conteneur n'a jamais démarré (docker run : code $code ; état created)."
fi
if ! [[ $etat =~ ^(exited|dead)\ ([0-9]{1,3})\ (.+)$ ]] || [ "${BASH_REMATCH[3]}" = "$ZERO" ]; then
  echouer 74 "conteneur dans un état inattendu après docker run (« $(printf '%s' "${etat:0:60}" | une_ligne) ») : arrêté."
fi
sortie_conteneur="${BASH_REMATCH[2]}"
if [ "$code" = 124 ] && [ "$sortie_conteneur" != 124 ]; then echouer 124 "durée maximale dépassée (${DUREE} s)."; fi
dk 30 rm -f "tests-$ID" >/dev/null 2>&1 && CONTENEUR=0  # fini et supprimé : rien à tuer, travail/ ne change plus
finir "$sortie_conteneur" conteneur
