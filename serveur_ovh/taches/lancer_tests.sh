#!/usr/bin/env bash
# Enveloppe HÔTE d'une campagne de tests : exécutée sur le serveur par UNE session SSH du poste, elle reste au premier plan
# du début à la fin (place, conteneur, sortie en direct, nettoyage) ; l'entrée standard de la session sert de laisse.
# Usage : lancer_tests.sh <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps> [<travail_go> [<image> [<famille>]]]
#   id t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; places 1..4 ; cpus 1..64 ; memoire_mo 256..65536 ; duree_s 1..3600 (nombres sans zéro
#   initial) ; projet ^[a-z0-9][a-z0-9-]{0,39}$ ; deps 16 hexa (cache Node ~/tests/.deps/<projet>/<deps>) ou « - » ;
#   travail_go 1..200 (facultatif, 10 par défaut) : taille maximale de travail/ (l'arbre extrait et ce que les tests écrivent) ;
#   image (facultatif, 9e argument) ^myiafactory/tests(-[a-z0-9]{1,24})?$, défaut myiafactory/tests : l'image du catalogue (§ 5.12) ;
#   famille (facultatif, 10e) dans FAMILLES, défaut python : table FERMÉE de l'enveloppe qui ajoute montages et variables du
#   conteneur (gradle-android : SDK de l'hôte ~/android-sdk monté en lecture seule sur /opt/android-sdk, ANDROID_HOME,
#   GRADLE_OPTS, GRADLE_USER_HOME=/tmp/gradle, GRADLE_RO_DEP_CACHE=/deps si un cache est monté ; gradle-jvm : sans le SDK). Jamais une valeur venue du poste hors de ces motifs : image et famille ne sont
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
#   panne, utilisateur du serveur autre que 1000 ; 78 cache Node absent (ou pas à nous) ; 124 durée dépassée
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
#   désactivé (la sortie ne remplit pas le disque), seulement travail/ (/work), entree/ (lecture seule) et le cache Node
#   (lecture seule) montés ; /tmp tmpfs 4 Go exécutable (nosuid, nodev par défaut) ; aucun secret, aucune variable de
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
GRADLE_OPTS_FERME="-Dorg.gradle.daemon=false -Dorg.gradle.vfs.watch=false -Dorg.gradle.offline=true -Dkotlin.compiler.execution.strategy=in-process"
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

[ $# -ge 7 ] && [ $# -le 10 ] || refuser "usage : <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps> [<travail_go> [<image> [<famille>]]]"
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
IMAGE="$IMAGE_DEMANDEE"
TRAVAIL_MAX_KO=$((TRAVAIL_GO * 1048576))
[[ ${HOME:-} == /* ]] || refuser "HOME absent ou relatif."
case "$HOME" in *[:,]*) refuser "HOME non admis (deux-points ou virgule : montage impossible)." ;; esac
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
  [ -n "$TICKET" ] && rm -f -- "$TICKET"
  liberer_creneau
  if [ -e "$DOSSIER/sortie-coupee" ]; then printf '%s\n' "Sortie coupée à 50 Mo" >&2; fi
  if [ -e "$DOSSIER/erreur-coupee" ]; then printf '%s\n' "Sortie d'erreur coupée à 50 Mo" >&2; fi
  if [ "$A_NOUS" = 1 ]; then
    if [ "$sur" = 1 ] && [ ! -L "$DOSSIER/travail" ]; then
      chmod -R u+rwX -- "$DOSSIER/travail" 2>/dev/null   # un dossier sans droits laissé par les tests s'efface aussi
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
DEPS_DOSSIER=""
if [ "$DEPS" != - ]; then
  DEPS_DOSSIER="$TESTS/.deps/$PROJET/$DEPS"
  for d in "$TESTS/.deps" "$TESTS/.deps/$PROJET" "$DEPS_DOSSIER"; do
    [ -d "$d" ] && [ ! -L "$d" ] || echouer 78 "cache des dépendances Node absent (~/tests/.deps/$PROJET/$DEPS)."
    [ -O "$d" ] || echouer 78 "cache des dépendances Node à un autre propriétaire (~/tests/.deps/$PROJET/$DEPS)."
  done
fi
raison=$(python3 -I "$AIDE" --archive "$ENTREE/entree.tar" 2>&1 >/dev/null); r=$?
if [ "$r" = 3 ]; then echouer 70 "$(printf '%s' "$raison" | une_ligne)"; fi   # 3 : refus explicite du vérificateur
[ "$r" = 0 ] || echouer 77 "contrôle de l'instantané impossible (python3, code $r)."
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
if [ -n "$DEPS_DOSSIER" ]; then COMMANDE+=(-v "$DEPS_DOSSIER:/deps:ro"); fi
# Table fermée par famille : montages et variables écrits ici, jamais lus du poste.
# Gradle : GRADLE_USER_HOME dans /tmp (tmpfs, seul endroit inscriptible : la racine est en lecture seule et /deps l'est aussi) ;
# un cache de dépendances monté en :ro sous /deps n'est lu que par GRADLE_RO_DEP_CACHE.
case "$FAMILLE" in
  gradle-android|gradle-jvm)
    if [ "$FAMILLE" = gradle-android ]; then COMMANDE+=(-v "$HOME/android-sdk:/opt/android-sdk:ro" -e ANDROID_HOME=/opt/android-sdk); fi
    COMMANDE+=(-e "GRADLE_OPTS=$GRADLE_OPTS_FERME" -e GRADLE_USER_HOME=/tmp/gradle)
    if [ -n "$DEPS_DOSSIER" ]; then COMMANDE+=(-e GRADLE_RO_DEP_CACHE=/deps); fi ;;
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
