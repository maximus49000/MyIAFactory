#!/usr/bin/env bash
# Enveloppe HÔTE d'une campagne de tests : exécutée sur le serveur par UNE session SSH du poste, elle reste au premier plan
# du début à la fin (place, conteneur, sortie en direct, nettoyage) ; l'entrée standard de la session sert de laisse.
# Usage : lancer_tests.sh <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps> [<travail_go> [<image> [<famille>
#         [<echauffement> [<reseau_code> [<budget_caches_go>]]]]]]
#   id t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; places 1..4 ; cpus 1..64 ; memoire_mo 256..65536 ; duree_s 1..3600 (nombres sans zéro
#   initial) ; projet ^[a-z0-9][a-z0-9-]{0,39}$ ; deps 16 hexa (empreinte du cache, tests_profil.empreinte_deps) ou « - » ;
#   echauffement (11e) : clé de la table FERMÉE ECH (npm, pip, gradle…), par défaut celle de la famille (ECH_DEFAUT) ;
#   reseau_code (12e) accorde|refuse (défaut refuse) : l'accord du Directeur pour le réseau d'un échauffement qui exécute du
#   code du projet (posé par la route d'après tests.adoption) ; budget_caches_go (13e) 1..1000, défaut 40 (Q5).
# DÉPENDANCES (conception § 5.13, tâche 14d), quand deps ≠ « - » : cache ~/tests/.deps/<projet>/<clé>-<deps>/ (contenu/ = ce
#   que l'outil a produit, .pret, .utilise, .verrou, .verrou-produit et .non-verrouille éventuels). Absent (ou « non
#   verrouillé » et .pret de plus de 7 jours) : ÉCHAUFFEMENT avant la file, sous flock -x <projet>/.<clé>-<deps>.echauffement :
#   conteneur deps-<id> (même image, mêmes durcissements que les tests, aucun secret, durée et plafond de la table ECH),
#   réseau `bridge` pour une clé qui n'exécute pas de code du projet (Q2), sinon SEULEMENT avec reseau_code=accorde : réseau
#   Docker --internal deps-<id> + mandataire éphémère mandataire-<id> (tests_hote.py --mandataire : CONNECT :443 vers la liste
#   fermée ECH_HOTES), supprimés à la fin. Le contenu s'écrit dans <cache>.tmp, renommé et .pret posé après succès. Échec,
#   durée, plafond, wrapper Gradle différent des sommes publiées, réseau non accordé : ligne `#deps-echec <raison>`, code 79
#   (rien n'est prêt, <cache>.tmp effacé). Pendant les tests : flock -s <cache>/.verrou, volume `overlay` tests-deps-<id>
#   (basse : contenu/ en lecture seule ; haute : ~/tests/<id>/deps-haut, effacée avec le dossier) monté sur /deps, variables
#   et drapeaux hors ligne de la table fermée (tests_hote.py --hors-ligne). Éviction après chaque usage : deux caches au plus
#   par projet et par clé, puis budget_caches_go, le moins récemment utilisé (.utilise) d'abord, jamais un cache tenu
#   (flock -x -n) ni celui de la campagne. gradle-android : SDK de l'hôte en copie sur écriture (volume overlay tests-sdk-<id> :
#   AGP peut y écrire .temp, licences… sans jamais toucher ~/android-sdk), à défaut monté en lecture seule.
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
# Sortie d'erreur : `#attente <rang> <total>` pendant la file (à chaque changement, rappel toutes les 30 s) ; la sortie
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
#   l'appelant : -e HOME=/tmp et -e MYIAFACTORY_TESTS_CONTENEUR=1 seulement. Sans --rm : l'enveloppe lit l'état final
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
# exécute_du_code". La commande elle-même est dans tests_hote.py (plan_echauffement), jamais venue du poste.
declare -A ECH
ECH[npm]="900 2 0"
ECH[pnpm]="900 2 0"
ECH[yarn]="900 2 0"
ECH[pip]="900 2 0"
ECH[pip-sources]="900 2 1"
ECH[gradle]="1800 6 1"
ECH[maven]="1800 6 1"
ECH[dotnet]="1800 6 0"
ECH[cargo]="1800 6 0"
ECH[go]="900 2 0"
ECH[unity]="3600 10 1"
declare -A ECH_DEFAUT=([python]=pip [node]=npm [gradle-android]=gradle [gradle-jvm]=gradle [maven]=maven [dotnet]=dotnet
                       [go]=go [rust]=cargo [unity]=unity)
# Sortie du mandataire d'un échauffement qui exécute du code (liste fermée par clé, Q4) ; github.com n'y est jamais.
declare -A ECH_HOTES
ECH_HOTES[gradle]="services.gradle.org downloads.gradle.org plugins.gradle.org plugins-artifacts.gradle.org repo.maven.apache.org repo1.maven.org dl.google.com maven.google.com"
ECH_HOTES[maven]="repo.maven.apache.org repo1.maven.org"
ECH_HOTES[pip-sources]="pypi.org files.pythonhosted.org"
SOMMES_GRADLE_URL="https://services.gradle.org/distributions"
PLACES_MAX=4
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

[ $# -ge 7 ] && [ $# -le 13 ] || refuser "usage : <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps> [<travail_go> [<image> [<famille> [<echauffement> [<reseau_code> [<budget_caches_go>]]]]]]"
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
[[ $IMAGE_DEMANDEE =~ ^myiafactory/tests(-[a-z0-9]{1,24})?$ ]] || refuser "image refusée (myiafactory/tests ou myiafactory/tests-<nom>)."
[[ $FAMILLE =~ ^[a-z][a-z-]{1,15}$ ]] && [[ $FAMILLES == *" $FAMILLE "* ]] || refuser "famille refusée."
ECH_CLE="${11-${ECH_DEFAUT[$FAMILLE]-"-"}}"; RESEAU="${12-refuse}"; BUDGET="${13-40}"
if [ "$ECH_CLE" != - ]; then
  [[ $ECH_CLE =~ ^[a-z][a-z-]{1,11}$ ]] && [ -n "${ECH[$ECH_CLE]+x}" ] || refuser "échauffement refusé (clé hors de la table)."
fi
[[ $RESEAU =~ ^(accorde|refuse)$ ]] || refuser "reseau_code refusé (accorde ou refuse)."
[[ $BUDGET =~ ^[1-9][0-9]{0,3}$ ]] && [ "$BUDGET" -le 1000 ] || refuser "budget_caches_go refusé (1 à 1000)."
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
    dk 30 kill "tests-$ID" >/dev/null 2>&1
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
  exec 5>&- 7>&-                                       # cache et préparation rendus
  [ -n "$TICKET" ] && rm -f -- "$TICKET"
  liberer_creneau
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

# Laisse : le reste de l'entrée standard. Fin de fichier = la session SSH est partie : marque, puis conteneur tué et
# enveloppe arrêtée, répétés tant que l'enveloppe vit (vérifiée par sa ligne de commande : jamais un PID recyclé).
exec 6<&0 </dev/null
( trap - TERM INT HUP PIPE
  while IFS= read -r _ <&6; do :; done
  exec 6<&-
  : > "$DOSSIER/laisse-coupee"
  while :; do
    dk 30 kill "tests-$ID" >/dev/null 2>&1
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
dk 20 image inspect "$IMAGE" >/dev/null 2>&1 || echouer 77 "image $IMAGE absente : installez la capacité qui la fournit (tests-image, tests-android)."
if [ "$FAMILLE" = gradle-android ]; then
  [ -d "$HOME/android-sdk" ] || echouer 77 "SDK Android de l'hôte absent (~/android-sdk) : installez la capacité android-build."
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
  [ -L "$d/travail" ] || chmod -R u+rwX -- "$d/travail" 2>/dev/null   # chmod suit un lien nommé : jamais sur un lien
  rm -rf -- "$d"
done < <(find "$TESTS" -mindepth 1 -maxdepth 1 -name 't*' -mmin +360 -print0 2>/dev/null)
# Restes d'échauffement (conteneurs deps-/mandataire-, réseaux deps-, volumes tests-deps-/tests-sdk-) dont l'enveloppe ne vit
# plus : les conteneurs d'abord, puis réseaux et volumes (un volume encore monté résiste : repris au balayage suivant).
balayer() {   # balayer <motif du nom, identifiant en 2e groupe> <commande de suppression>... ; les noms viennent de la liste filtrée par l'étiquette
  local motif="$1" n autre; shift
  while IFS= read -r n; do
    [[ $n =~ $motif ]] || continue
    autre="${BASH_REMATCH[2]}"
    [ "$autre" = "$ID" ] || enveloppe_vivante "$autre" || dk 30 "$@" "$n" >/dev/null 2>&1
  done
}
balayer '^(deps|mandataire)-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$' rm -f \
  < <(dk 20 ps -a --filter "label=myiafactory.genre=tests-deps" --format '{{.Names}}' 2>/dev/null)
balayer '^(deps)-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$' network rm \
  < <(dk 20 network ls --filter "label=myiafactory.genre=tests-deps" --format '{{.Name}}' 2>/dev/null)
balayer '^tests-(deps|sdk)-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$' volume rm -f \
  < <(dk 20 volume ls --filter "label=myiafactory.genre=tests-deps" --format '{{.Name}}' 2>/dev/null)

# --- Dépendances : wrapper Gradle, échauffement, cache tenu, éviction (§ 5.13) ------------------------------------------

deps_echec() {   # deps_echec <raison> : `#deps-echec <raison>` (mot fermé), puis 79 : la route repasse au poste
  printf '#deps-echec %s\n' "$1" >&2
  echouer 79 "échauffement des dépendances impossible ($1) : les tests ne partent pas au serveur."
}
cache_pret() { [ -f "$1/.pret" ] && [ -d "$1/contenu" ] && [ ! -L "$1" ] && [ ! -L "$1/contenu" ]; }
cache_perime() { [ -f "$1/.non-verrouille" ] && [ -n "$(find "$1/.pret" -mmin +10080 2>/dev/null)" ]; }   # 7 jours
du_ko() { local k; k=$(timeout 120 du -sk -- "$1" 2>/dev/null 8>&- | cut -f1); [[ $k =~ ^[0-9]{1,15}$ ]] && printf '%s' "$k"; }
effacer_cache() {   # effacer_cache <cache> : seulement si personne ne le tient (flock -x -n) ; 0 si effacé
  local c="$1"
  [ -d "$c" ] && [ ! -L "$c" ] || return 1
  exec 4>> "$c/.verrou" || return 1
  if ! flock -x -n 4; then exec 4>&-; return 1; fi
  chmod -R u+rwX -- "$c" 2>/dev/null                   # le cache de modules Go (entre autres) est en lecture seule
  rm -rf -- "$c"
  exec 4>&-
  [ ! -e "$c" ]
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
    n=$(du_ko "$TESTS/.deps") || break
    [ "$n" -gt $((BUDGET * 1048576)) ] || break
    [ "$c" = "$CACHE" ] || effacer_cache "$c"
  done
}

verifier_wrapper() {   # gradle-wrapper.jar de l'instantané = la somme PUBLIÉE par Gradle pour la version du wrapper, sinon 79
  local ligne r somme version fichier officielle sommes="$TESTS/.deps/.gradle-wrapper"
  ligne=$(python3 -I "$AIDE" --wrapper "$ENTREE/entree.tar" 2>"$DOSSIER/.wrapper.err"); r=$?
  raison=$(head -n 1 "$DOSSIER/.wrapper.err" 2>/dev/null | tr -cd 'a-z-' | head -c 60); rm -f -- "$DOSSIER/.wrapper.err"
  [ "$r" = 3 ] && deps_echec "${raison:-wrapper-illisible}"
  [ "$r" = 0 ] || deps_echec wrapper-illisible
  [[ $ligne =~ ^([0-9a-f]{64})\ ([0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,2})?(-rc-[0-9]{1,2})?)$ ]] || deps_echec wrapper-illisible
  somme="${BASH_REMATCH[1]}"; version="${BASH_REMATCH[2]}"
  mkdir -p -m 700 -- "$sommes" 2>/dev/null
  [ -d "$sommes" ] && [ ! -L "$sommes" ] && [ -O "$sommes" ] || deps_echec sommes-gradle-inaccessibles
  fichier="$sommes/$version.sha256"
  if ! { [ -f "$fichier" ] && [ ! -L "$fichier" ]; }; then
    # Source officielle (TLS vers services.gradle.org) ; la somme n'est jamais devinée ni écrite à la main.
    command -v curl >/dev/null 2>&1 || deps_echec curl-absent
    rm -f -- "$fichier.tmp"
    timeout 60 curl -fsSL --proto =https --max-time 50 -o "$fichier.tmp" \
      "$SOMMES_GRADLE_URL/gradle-$version-wrapper.jar.sha256" </dev/null >/dev/null 2>&1 8>&- || deps_echec somme-gradle-injoignable
    officielle=$(head -c 200 -- "$fichier.tmp" 2>/dev/null | tr -d ' \r\n')
    [[ $officielle =~ ^[0-9a-f]{64}$ ]] || { rm -f -- "$fichier.tmp"; deps_echec somme-gradle-illisible; }
    printf '%s\n' "$officielle" > "$fichier.tmp" && mv -f -- "$fichier.tmp" "$fichier" || deps_echec ecriture
  fi
  officielle=$(head -c 64 -- "$fichier")
  [ "$somme" = "$officielle" ] || deps_echec wrapper-modifie
}

# SDK Android de l'hôte en copie sur écriture : AGP peut écrire (.temp, licences, .knownPackages) dans la couche haute, effacée
# avec le dossier ; ~/android-sdk n'est jamais inscriptible par un conteneur. Overlay refusé : lecture seule (comme avant).
SDK_MONTAGE=()
if [ "$FAMILLE" = gradle-android ]; then
  SDK_MONTAGE=(-v "$HOME/android-sdk:/opt/android-sdk:ro")
  if mkdir -m 700 -- "$DOSSIER/sdk-haut" "$DOSSIER/sdk-ov" 2>/dev/null; then
    VOLUMES+=("tests-sdk-$ID")
    if dk 30 volume create --driver local --label myiafactory.genre=tests-deps --opt type=overlay --opt device=overlay \
         --opt "o=lowerdir=$HOME/android-sdk,upperdir=$DOSSIER/sdk-haut,workdir=$DOSSIER/sdk-ov" "tests-sdk-$ID" >/dev/null 2>&1; then
      SDK_MONTAGE=(--mount "type=volume,src=tests-sdk-$ID,dst=/opt/android-sdk")
    else
      printf '%s\n' "lancer_tests : copie sur écriture du SDK indisponible : SDK monté en lecture seule." >&2
    fi
  fi
  SDK_MONTAGE+=(-e ANDROID_HOME=/opt/android-sdk)
fi

echauffer() {
  local duree plafond code r ko hotes p de="$DOSSIER/deps-entree" dt="$DOSSIER/deps-travail" tmp="$CACHE.tmp"
  read -r duree plafond code <<< "${ECH[$ECH_CLE]}"
  [ "$ECH_CLE" = unity ] && deps_echec unity-tache-14g
  [ "$code" = 1 ] && [ "$RESEAU" != accorde ] && deps_echec reseau-non-accorde
  mkdir -p -m 700 -- "$DEPS_RACINE" 2>/dev/null
  for d in "$TESTS/.deps" "$DEPS_RACINE"; do
    [ -d "$d" ] && [ ! -L "$d" ] && [ -O "$d" ] || deps_echec cache-inaccessible
  done
  exec 7>> "$DEPS_RACINE/.$ECH_CLE-$DEPS.echauffement" || deps_echec cache-inaccessible
  flock -x -w $((duree + 300)) 7 || deps_echec echauffement-concurrent
  if cache_pret "$CACHE" && ! cache_perime "$CACHE"; then exec 7>&-; return 0; fi   # préparé pendant l'attente
  TMP_CACHE="$tmp"
  if [ -d "$tmp" ] && [ ! -L "$tmp" ]; then chmod -R u+rwX -- "$tmp" 2>/dev/null; fi
  rm -rf -- "$tmp"
  mkdir -m 700 -- "$tmp" "$tmp/contenu" "$tmp/meta" "$de" "$dt" || deps_echec ecriture
  ln -- "$ENTREE/entree.tar" "$de/entree.tar" 2>/dev/null || cp -- "$ENTREE/entree.tar" "$de/entree.tar" || deps_echec ecriture
  printf '["python3","-I","/opt/myiafactory/tests_hote.py","--echauffer","%s","%s"]' "$ECH_CLE" "$FAMILLE" > "$de/commande.json" ||
    deps_echec ecriture
  local -a run=(run --pull never --init --name "deps-$ID" --label myiafactory.genre=tests-deps --log-driver none
    --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000
    --pids-limit 2048 --ulimit nofile=8192:8192 --ulimit core=0
    --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS"
    --tmpfs /tmp:size=4g,mode=1777,exec
    -v "$dt:/work" -v "$de:/entree:ro" -v "$tmp/contenu:/deps" -v "$tmp/meta:/deps-meta"
    -v "$AIDE:/opt/myiafactory/tests_hote.py:ro" "${SDK_MONTAGE[@]}")
  if [ "$code" = 1 ]; then
    # Code du projet : réseau interne seulement, sortie par le mandataire (liste fermée), jamais bridge.
    read -r -a hotes <<< "${ECH_HOTES[$ECH_CLE]-}"
    [ "${#hotes[@]}" -gt 0 ] || deps_echec reseau-sans-liste
    DEPS_RESEAU="deps-$ID"
    dk 30 network create --internal --label myiafactory.genre=tests-deps "deps-$ID" >/dev/null 2>&1 || deps_echec reseau-interne
    MANDATAIRE=1
    dk 60 run -d --pull never --init --name "mandataire-$ID" --label myiafactory.genre=tests-deps --log-driver none \
      --network bridge --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000 \
      --pids-limit 256 --memory 256m --memory-swap 256m --cpus 1 --tmpfs /tmp:size=16m \
      -v "$AIDE:/opt/myiafactory/tests_hote.py:ro" --entrypoint python3 "$IMAGE" \
      -I /opt/myiafactory/tests_hote.py --mandataire 3128 $((duree + 120)) "${hotes[@]}" >/dev/null 2>&1 || deps_echec mandataire
    dk 30 network connect "deps-$ID" "mandataire-$ID" >/dev/null 2>&1 || deps_echec mandataire
    p="http://mandataire-$ID:3128"
    run+=(--network "deps-$ID" -e "HTTPS_PROXY=$p" -e "HTTP_PROXY=$p" -e "https_proxy=$p" -e "http_proxy=$p"
      -e "NO_PROXY=localhost,127.0.0.1"
      -e "JAVA_TOOL_OPTIONS=-Dhttps.proxyHost=mandataire-$ID -Dhttps.proxyPort=3128 -Dhttp.proxyHost=mandataire-$ID -Dhttp.proxyPort=3128")
  else
    run+=(--network bridge)                            # Q2 : aucun code du projet n'est exécuté
  fi
  run+=(-e HOME=/tmp -e MYIAFACTORY_TESTS_CONTENEUR=1 "$IMAGE")
  printf '%s\n' "lancer_tests : échauffement des dépendances ($ECH_CLE, ${duree} s et ${plafond} Go au plus)." >&2
  rm -f -- "$DOSSIER/deps-plafond" "$DOSSIER/deps-disque"
  # Surveillant de l'échauffement : plafond du cache, disque ; la laisse tue deps-<id> elle aussi.
  ( trap - TERM INT HUP PIPE
    du_t=0
    while sleep "$SONDE" 7>&-; do
      enveloppe_vivante "$ID" || { dk 30 kill "deps-$ID" >/dev/null 2>&1; exit 0; }
      l=$(disque_libre_ko)
      if [[ $l =~ ^[0-9]{1,15}$ ]] && [ "$l" -lt "$DISQUE_ARRET_KO" ]; then : > "$DOSSIER/deps-disque"; dk 30 kill "deps-$ID" >/dev/null 2>&1; fi
      maintenant=$(date +%s)
      [ $((maintenant - du_t)) -ge "$DU_S" ] || continue
      ko=$(du_ko "$tmp"); du_t=$(date +%s)              # la période repart à la FIN de du
      if [[ $ko =~ ^[0-9]+$ ]] && [ "$ko" -gt $((plafond * 1048576)) ]; then
        : > "$DOSSIER/deps-plafond"; dk 30 kill "deps-$ID" >/dev/null 2>&1
      fi
    done ) >/dev/null 2>&1 7>&- &
  PID_SURVEILLANT=$!
  DEPS_CONTENEUR=1
  timeout "$duree" sudo -n docker "${run[@]}" </dev/null 2>&1 7>&- 8>&- |
    python3 -I "$AIDE" --couper "$DOSSIER/deps-journal-coupe" 1048576 > "$DOSSIER/deps.log" 7>&- 8>&-
  r=${PIPESTATUS[0]}
  { kill "$PID_SURVEILLANT"; wait "$PID_SURVEILLANT"; } 2>/dev/null
  PID_SURVEILLANT=""
  dk 30 rm -f "deps-$ID" >/dev/null 2>&1 && DEPS_CONTENEUR=0
  fermer_reseau
  [ -e "$DOSSIER/laisse-coupee" ] && finir 130
  [ -e "$DOSSIER/deps-disque" ] && deps_echec disque
  ko=$(du_ko "$tmp") || ko=0
  { [ -e "$DOSSIER/deps-plafond" ] || [ "$ko" -gt $((plafond * 1048576)) ]; } && deps_echec plafond
  [ "$r" = 124 ] && deps_echec duree
  if [ "$r" != 0 ] || [ ! -f "$tmp/meta/ok" ]; then
    tail -n 20 -- "$DOSSIER/deps.log" 2>/dev/null | tr '\000-\011\013-\037\177' '?' |
      sed -e 's/\xc2\x85/?/g' -e 's/\xe2\x80\xa8/?/g' -e 's/\xe2\x80\xa9/?/g' -e 's/^/| /' | head -c 4096 >&2
    deps_echec echauffement
  fi
  if [ -f "$tmp/meta/verrou-produit" ] && [ ! -L "$tmp/meta/verrou-produit" ]; then
    mv -f -- "$tmp/meta/verrou-produit" "$tmp/.verrou-produit"   # jamais réécrit dans le projet
  fi
  [ -f "$tmp/meta/non-verrouille" ] && : > "$tmp/.non-verrouille"
  chmod -R u+rwX -- "$dt" 2>/dev/null
  rm -rf -- "$tmp/meta" "$de" "$dt"
  : > "$tmp/.verrou"; : > "$tmp/.utilise"
  if [ -d "$CACHE" ] && ! effacer_cache "$CACHE"; then   # rafraîchissement d'un cache tenu par une autre campagne : gardé
    chmod -R u+rwX -- "$tmp" 2>/dev/null; rm -rf -- "$tmp"; TMP_CACHE=""
    printf '%s\n' "lancer_tests : cache tenu par une autre campagne : l'ancien est gardé." >&2
    exec 7>&-; return 0
  fi
  mv -- "$tmp" "$CACHE" || deps_echec ecriture
  TMP_CACHE=""
  date +%s > "$CACHE/.pret" || deps_echec ecriture
  exec 7>&-
}

if [ -n "$CACHE" ]; then
  [ "$ECH_CLE" = gradle ] && verifier_wrapper            # avant TOUT lancement Gradle (échauffement et tests)
  if ! cache_pret "$CACHE" || cache_perime "$CACHE"; then echauffer; fi
  exec 5>> "$CACHE/.verrou" || deps_echec cache-inaccessible
  flock -s 5 || deps_echec cache-verrou                  # tenu pendant toute la campagne : jamais évincé sous nos pieds
  cache_pret "$CACHE" || deps_echec cache-disparu
  touch -- "$CACHE/.utilise"
  evincer
  mkdir -m 700 -- "$DOSSIER/deps-haut" "$DOSSIER/deps-ov" || deps_echec ecriture
  VOLUMES+=("tests-deps-$ID")
  dk 30 volume create --driver local --label myiafactory.genre=tests-deps --opt type=overlay --opt device=overlay \
    --opt "o=lowerdir=$CACHE/contenu,upperdir=$DOSSIER/deps-haut,workdir=$DOSSIER/deps-ov" "tests-deps-$ID" >/dev/null 2>&1 ||
    deps_echec copie-sur-ecriture
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

DEBUT_ATTENTE=$(date +%s); dernier=""; dernier_t=0
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
  if [ "$rang" = 1 ] && prendre_place; then break; fi
  maintenant=$(date +%s)
  if [ "$rang $total" != "$dernier" ] || [ $((maintenant - dernier_t)) -ge 30 ]; then
    printf '#attente %s %s\n' "$rang" "$total" >&2
    dernier="$rang $total"; dernier_t=$maintenant
  fi
  sleep "$SONDE"
done
rm -f -- "$TICKET"; TICKET=""
DEBUT=$(date +%s)
ATTENTE=$((DEBUT - DEBUT_ATTENTE))

# --- Conteneur ------------------------------------------------------------------

COMMANDE=(run --pull never --init --name "tests-$ID" --label myiafactory.genre=tests --log-driver none
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000
  --pids-limit 2048 --ulimit nofile=8192:8192 --ulimit core=0
  --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS"
  --tmpfs /tmp:size=4g,mode=1777,exec
  -v "$DOSSIER/travail:/work" -v "$ENTREE:/entree:ro")
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
  arreter() { : > "$DOSSIER/$1"; dk 30 kill "tests-$ID" >/dev/null 2>&1; }
  echeance=$(( $(date +%s) + DUREE + MARGE )); du_t=0; du_en_cours=0
  rm -f -- "$DOSSIER/.du" "$DOSSIER/.du.tmp"
  while sleep "$SONDE" 8>&-; do
    if [ -e "$DOSSIER/laisse-coupee" ]; then
      dk 30 kill "tests-$ID" >/dev/null 2>&1
      enveloppe_vivante "$ID" && kill -TERM "$$" 2>/dev/null
      continue
    fi
    enveloppe_vivante "$ID" || { dk 30 kill "tests-$ID" >/dev/null 2>&1; exit 0; }
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
  { timeout "$DUREE" sudo -n docker "${COMMANDE[@]}" </dev/null 2>&1 1>&3 3>&- 8>&-
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
