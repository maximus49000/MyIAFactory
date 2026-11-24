#!/usr/bin/env bash
# Enveloppe HÔTE de construction des images dérivées des tests (conception § 5.12, tâche 14c) : exécutée sur le serveur par une
# session SSH du poste. CODE SENSIBLE : elle lance `docker build` AVEC LE RÉSEAU sur un Dockerfile rendu au poste. Elle ne croit
# donc rien du poste : motifs stricts, somme du Dockerfile approuvée, contexte réduit, aucun montage, aucun --build-arg,
# aucun --privileged, aucune valeur du poste dans la commande docker (l'étiquette et la somme ont passé leurs motifs).
# Usage :
#   construire_image_tests.sh <etiquette> <sha256>   construit l'image ; <etiquette> = myiafactory/tests-<12 hexa>, <sha256> = les
#                                                    64 hexa du Dockerfile que la Direction a approuvé
#   construire_image_tests.sh --ramasser <budget_go> supprime des images dérivées (voir plus bas)
#   construire_image_tests.sh --utilise <etiquette>  marque l'image « utilisée maintenant » (le poste l'appelle au départ d'une
#                                                    campagne qui la prend ; sans cela le ramassage ne connaît que sa date de création)
# Contexte de construction ~/tests/.construction/<etiquette>/ (donc .../myiafactory/tests-<12 hexa>/), déposé par le poste AVANT :
#   le seul fichier `Dockerfile` (64 Ko au plus, UNE instruction FROM sur une base fermée, ni ADD, ni VOLUME, ni ONBUILD, ni
#   --mount/--network/--security). Tout autre fichier, lien ou dossier -> refus. `entree-tests.sh` est COPIÉ ici depuis le dépôt du
#   serveur (jamais celui du poste). Aucun fichier du projet : la construction n'exécute aucun code du projet.
# Codes : 0 ; 2 refus (argument, motif, contexte, somme différente, Dockerfile hors gabarit) : rien n'est lancé ni effacé ;
#   76 disque libre < 10 Go : rien n'est lancé ; 124 construction au-delà de 1 800 s ; 1 construction ou docker en échec.
#   Après tout départ de `docker build`, le contexte est effacé. Journal de la construction : ~/tests/.construction/journaux/
#   <tests-12hexa>.log (les 64 derniers Ko), les dernières lignes vont aussi sur la sortie d'erreur.
# Sortie standard : `#image <etiquette> <taille_mo>` après une construction réussie ; une ligne `#ramassee <etiquette>` par image
#   supprimée au ramassage.
# Étiquettes posées : myiafactory.genre=tests-derivee, myiafactory.empreinte=<sha256 du Dockerfile> (ÉCART À LA CONCEPTION :
#   l'enveloppe ne connaît que cette somme, pas l'empreinte d'image du poste ; le registre du poste garde l'empreinte d'image).
# Jamais de `--pull` : une base locale `myiafactory/*` n'existe sur aucun registre ; une base `unityci/editor` (tâche 14g)
#   est l'image GameCI DÉJÀ présente (27 Go), épinglée par son digest local (`unityci/editor:ubuntu-<version>-android-<x.y.z>
#   @sha256:<64 hexa>`, jamais une étiquette seule) : absente du serveur -> refus 2, jamais tirée. Une image dérivée d'Unity
#   porte en plus l'étiquette myiafactory/tests-unity-<version> (celle que l'enveloppe des tests attend) ; son contexte reçoit
#   aussi entree-unity.sh (du dépôt du serveur) ; la taille de `#image` est alors sa taille PROPRE (image moins base).
# Ramassage : ne touche QUE les images portant le label myiafactory.genre=tests-derivee ; jamais une image que le moindre
#   conteneur référence (docker ps -a ; en plus, rmi sans -f refuse une image en usage) ; d'abord toute image sans usage depuis
#   plus de 30 jours, puis la moins récemment utilisée tant que le total dépasse le budget. Taille d'une image : sa taille
#   PROPRE (couches non partagées, colonne UNIQUE SIZE de `docker system df -v`, comme tests_images.taille_propre_mo) : une
#   image dérivée de l'image GameCI (27 Go apparents) n'y compte que pour sa couche ; à défaut (docker system df illisible),
#   la taille apparente (docker image inspect .Size, par excès). Les étiquettes myiafactory/tests-unity-* d'une image ramassée
#   sont retirées avec elle (sinon l'image resterait). Usage = date du fichier ~/tests/.construction/usage/<tests-12hexa>
#   (posé à la construction et par --utilise), sinon la date de création de l'image.
# Réservée aux tests : SERVEUR_OVH_DIR (dépôt du serveur).
set -u
export LC_ALL=C
umask 077

TESTS="$HOME/tests"
CONSTRUCTION="$TESTS/.construction"
SERVEUR_OVH="${SERVEUR_OVH_DIR:-$HOME/myiafactory/serveur_ovh}"
MOTIF_ETIQUETTE='^myiafactory/tests-[0-9a-f]{12}$'
MOTIF_SOMME='^[0-9a-f]{64}$'
MOTIF_BASE_LOCALE='^myiafactory/tests(-[a-z0-9]{1,24})?(@sha256:[0-9a-f]{64})?$'
MOTIF_BASE_UNITY='^unityci/editor:ubuntu-([0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3})-android-[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}@sha256:[0-9a-f]{64}$'
MOTIF_ETIQUETTE_UNITY='^myiafactory/tests-unity-[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,3}$'
DISQUE_MIN_KO=10485760                   # 10 Go libres pour construire
DUREE_MAX=1800
DOSSIER_MAX_OCTETS=65536
JOURNAL_OCTETS=65536
JOURS_INUTILISEE=30

echouer() { printf 'construire_image_tests : %s\n' "$2" >&2; exit "$1"; }
dk() { local delai="$1"; shift; timeout "$delai" sudo -n docker "$@" </dev/null; }
une_ligne() { tr -c '[:print:]\n' '?' | head -c 4000; }

# --- Utilisation d'une image ------------------------------------------------

if [ "${1:-}" = "--utilise" ]; then
  [ $# -eq 2 ] || echouer 2 "usage : --utilise <etiquette>"
  [[ $2 =~ $MOTIF_ETIQUETTE ]] || echouer 2 "étiquette refusée."
  mkdir -p -- "$CONSTRUCTION/usage" || echouer 1 "dossier d'usage impossible."
  touch -- "$CONSTRUCTION/usage/${2#myiafactory/}" || echouer 1 "usage non noté."
  exit 0
fi

# --- Ramassage ----------------------------------------------------------------

if [ "${1:-}" = "--ramasser" ]; then
  [ $# -eq 2 ] || echouer 2 "usage : --ramasser <budget_go>"
  [[ $2 =~ ^[1-9][0-9]{0,3}$ ]] || echouer 2 "budget refusé (1 à 9999 Go)."
  budget_mo=$(($2 * 1024))
  # Par identifiant, sans tag compris : une reconstruction sous la même étiquette laisse l'ancienne image sans tag (<none>),
  # qui porte encore le label et doit pouvoir être ramassée.
  ids=$(dk 60 image ls --filter label=myiafactory.genre=tests-derivee --format '{{.ID}}') \
    || echouer 1 "liste des images impossible (docker)."
  # L'image de chaque conteneur : son nom (ps --format {{.Image}}) ET son identifiant (inspect {{.Image}}) ; jamais
  # {{.ImageID}} de `ps --format`, inconnu de Docker 29 (serveur, 2026-11-24 : le ramassage échouait sans rien supprimer).
  vivantes=$(dk 60 ps -a --format '{{.Image}}') || echouer 1 "liste des conteneurs impossible (docker) : rien n'est supprimé."
  conteneurs=$(dk 60 ps -aq) || echouer 1 "liste des conteneurs impossible (docker) : rien n'est supprimé."
  if [ -n "$conteneurs" ]; then
    # shellcheck disable=SC2086  # identifiants hexadécimaux de docker, un par mot
    images_c=$(dk 60 inspect --format '{{.Image}}' $conteneurs) || echouer 1 "images des conteneurs illisibles (docker) : rien n'est supprimé."
    vivantes+=$'\n'"$images_c"
  fi
  vivantes=$(tr ' ' '\n' <<< "$vivantes" | sed -e 's/^sha256://' -e 's/^\([0-9a-f]\{12\}\)[0-9a-f]*$/\1/')
  # Tailles propres « <id 12 hexa> <Mo> » (UNIQUE SIZE, unités décimales de docker, Mo de 1 048 576 octets arrondis au-dessus).
  propres=$(dk 120 system df -v 2>/dev/null | awk '
    /^Images space usage/ { dans = 1; next }
    /space usage/ { dans = 0 }
    dans && NF >= 7 && length($3) == 12 && $3 ~ /^[0-9a-f]+$/ {
      u = $(NF - 1)
      if (match(u, /^[0-9]+(\.[0-9]+)?/)) {
        v = substr(u, 1, RLENGTH); s = substr(u, RLENGTH + 1)
        m = (s == "B") ? 1 : (s == "kB" || s == "KB") ? 1e3 : (s == "MB") ? 1e6 : (s == "GB") ? 1e9 : (s == "TB") ? 1e12 : 0
        if (m > 0) { o = v * m; mo = int(o / 1048576); if (mo * 1048576 < o) mo++; print $3, mo }
      }
    }')
  maintenant=$(date +%s)
  lignes=""; total_mo=0
  while IFS= read -r id; do
    id="${id#sha256:}"; id="${id:0:12}"
    [[ $id =~ ^[0-9a-f]{12}$ ]] || continue
    grep -Eq -- " $id\$" <<< "$lignes" && continue                   # une image par identifiant
    mo=$(awk -v i="$id" '$1 == i { print $2; exit }' <<< "$propres")
    if ! [[ $mo =~ ^[0-9]{1,9}$ ]]; then
      octets=$(dk 60 image inspect --format '{{.Size}}' "$id") || continue
      [[ $octets =~ ^[0-9]{1,15}$ ]] || continue
      mo=$((octets / 1048576))
    fi
    cible="$id"; unity=""
    for tag in $(dk 60 image inspect --format '{{range .RepoTags}}{{.}} {{end}}' "$id" 2>/dev/null); do
      tag="${tag%:latest}"
      if [[ $tag =~ $MOTIF_ETIQUETTE_UNITY ]]; then unity+="$tag,"; continue; fi
      [[ $tag =~ $MOTIF_ETIQUETTE ]] && [ "$cible" = "$id" ] && cible="$tag"
    done
    usage="$CONSTRUCTION/usage/${cible#myiafactory/}"
    quand=""
    if [ "$cible" != "$id" ] && [ -f "$usage" ] && [ ! -L "$usage" ]; then
      quand=$(stat -c %Y -- "$usage" 2>/dev/null)
    else
      cree=$(dk 60 image inspect --format '{{.Created}}' "$id" 2>/dev/null)
      quand=$(date -d "$cree" +%s 2>/dev/null)
    fi
    [[ ${quand:-} =~ ^[0-9]{1,12}$ ]] || quand="$maintenant"          # date illisible : jamais « ancienne »
    lignes+="$quand $cible $mo $id ${unity:--}"$'\n'
    total_mo=$((total_mo + mo))
  done <<< "$ids"
  while read -r quand cible mo id unity; do
    [ -n "${id:-}" ] || continue
    [ "${unity:--}" = - ] && unity=""
    ancienne=0
    [ $((maintenant - quand)) -gt $((JOURS_INUTILISEE * 86400)) ] && ancienne=1
    [ "$ancienne" = 1 ] || [ "$total_mo" -gt "$budget_mo" ] || continue
    if grep -Fxq -- "$id" <<< "$vivantes" || grep -Fxq -- "$cible" <<< "$vivantes" || grep -Fxq -- "$cible:latest" <<< "$vivantes"; then
      continue
    fi
    tenue=0; etiquettes_unity=()
    [ -n "$unity" ] && IFS=, read -r -a etiquettes_unity <<< "$unity"
    for u in "${etiquettes_unity[@]}"; do
      if grep -Fxq -- "$u" <<< "$vivantes" || grep -Fxq -- "$u:latest" <<< "$vivantes"; then tenue=1; fi
    done
    [ "$tenue" = 1 ] && continue
    if dk 120 rmi "$cible" >/dev/null 2>&1; then
      # L'étiquette Unity seulement APRÈS la cible : une cible refusée laisse l'image entière et toutes ses étiquettes.
      for u in "${etiquettes_unity[@]}"; do dk 120 rmi "$u" >/dev/null 2>&1; done
      rm -f -- "$CONSTRUCTION/usage/${cible#myiafactory/}"
      total_mo=$((total_mo - mo))
      printf '#ramassee %s\n' "$cible"
    fi
  done < <(sort -n -k1,1 -k2,2 <<< "$lignes")
  exit 0
fi

# --- Construction ---------------------------------------------------------------

[ $# -eq 2 ] || echouer 2 "usage : <etiquette> <sha256> | --ramasser <budget_go> | --utilise <etiquette>"
ETIQUETTE="$1"; SOMME="$2"
[[ $ETIQUETTE =~ $MOTIF_ETIQUETTE ]] || echouer 2 "étiquette refusée (myiafactory/tests-<12 hexa>)."
[[ $SOMME =~ $MOTIF_SOMME ]] || echouer 2 "somme refusée (64 hexa)."
NOM="${ETIQUETTE#myiafactory/}"
CONTEXTE="$CONSTRUCTION/$ETIQUETTE"
for d in "$TESTS" "$CONSTRUCTION" "$CONSTRUCTION/myiafactory" "$CONTEXTE"; do
  [ -d "$d" ] && [ ! -L "$d" ] && [ -O "$d" ] || echouer 2 "contexte de construction absent ou pas à nous ($CONTEXTE)."
done
# Rien d'autre que Dockerfile (et entree-tests.sh, qui sera remplacé) : fichiers ordinaires, pas de lien.
shopt -s nullglob dotglob
contenu=("$CONTEXTE"/*)
shopt -u nullglob dotglob
[ "${#contenu[@]}" -ge 1 ] && [ "${#contenu[@]}" -le 2 ] || echouer 2 "le contexte doit contenir le seul Dockerfile."
for f in "${contenu[@]}"; do
  base="${f##*/}"
  [ "$base" = Dockerfile ] || [ "$base" = entree-tests.sh ] || echouer 2 "fichier inattendu dans le contexte."
  [ -f "$f" ] && [ ! -L "$f" ] || echouer 2 "$base n'est pas un fichier ordinaire."
done
DEPOT="$CONTEXTE/Dockerfile"
[ -f "$DEPOT" ] || echouer 2 "Dockerfile absent du contexte."
taille=$(stat -c %s -- "$DEPOT" 2>/dev/null)
[[ ${taille:-} =~ ^[0-9]{1,9}$ ]] && [ "$taille" -le "$DOSSIER_MAX_OCTETS" ] || echouer 2 "Dockerfile trop gros (64 Ko au plus)."
# Copie privée à l'enveloppe : c'est CETTE copie qui est hachée, contrôlée et construite (le dossier déposé peut changer entre
# le contrôle et la construction ; la copie, non).
PRIVE=$(mktemp -d "$CONSTRUCTION/ctx.XXXXXX") || echouer 1 "contexte privé impossible."
trap 'rm -rf -- "$PRIVE"' EXIT
cp -- "$DEPOT" "$PRIVE/Dockerfile" || echouer 1 "copie du Dockerfile impossible."
DOCKERFILE="$PRIVE/Dockerfile"
reelle=$(sha256sum -- "$DOCKERFILE" | cut -d' ' -f1)
[ "$reelle" = "$SOMME" ] || echouer 2 "le SHA-256 du Dockerfile n'est pas celui qui a été approuvé : construction refusée."
# Défense en profondeur (la somme approuvée suffit, ceci borne ce qu'un gabarit trafiqué pourrait demander).
[ "$(grep -Eic '^[[:space:]]*FROM[[:space:]]' "$DOCKERFILE")" = 1 ] || echouer 2 "une seule instruction FROM est permise."
BASE=$(awk 'toupper($1) == "FROM" { print $2; exit }' "$DOCKERFILE")
VERSION_UNITY=""; ETIQUETTES_PLUS=()
if [[ $BASE =~ $MOTIF_BASE_LOCALE ]]; then
  PULL=()
  # Base locale : elle doit exister ici, sinon docker irait chercher un espace « myiafactory » sur le Docker Hub.
  dk 20 image inspect "$BASE" >/dev/null 2>&1 || echouer 2 "image de base $BASE absente du serveur (installez la capacité qui la fournit)."
elif [[ $BASE =~ $MOTIF_BASE_UNITY ]]; then
  PULL=()
  VERSION_UNITY="${BASH_REMATCH[1]}"
  # Base GameCI : DÉJÀ présente au serveur (27 Go), jamais tirée ; son digest local est celui qu'a lu la sonde du poste.
  dk 20 image inspect "$BASE" >/dev/null 2>&1 || echouer 2 "image GameCI $BASE absente du serveur (installez la capacité unity-cli) : jamais tirée."
  ETIQUETTES_PLUS=(-t "myiafactory/tests-unity-$VERSION_UNITY")
else echouer 2 "image de base refusée."; fi
if grep -Eiq '^[[:space:]]*(ADD|VOLUME|ONBUILD)[[:space:]]' "$DOCKERFILE" \
   || grep -Eiq -- '(^|[[:space:]])--(mount|network|security|privileged)([=[:space:]]|$)' "$DOCKERFILE" \
   || grep -Eiq -- '--from=' "$DOCKERFILE" \
   || grep -Eq '^#[[:space:]]*[A-Za-z]+[[:space:]]*=' "$DOCKERFILE"; then   # --from= ; directives d'analyse (# syntax=, # escape=)
  echouer 2 "instruction, option ou directive interdite dans le Dockerfile."
fi
[ -f "$SERVEUR_OVH/images/tests/entree-tests.sh" ] && [ ! -L "$SERVEUR_OVH/images/tests/entree-tests.sh" ] \
  || echouer 1 "entree-tests.sh introuvable dans le dépôt du serveur."
if [ -n "$VERSION_UNITY" ]; then
  [ -f "$SERVEUR_OVH/images/tests/entree-unity.sh" ] && [ ! -L "$SERVEUR_OVH/images/tests/entree-unity.sh" ] \
    || echouer 1 "entree-unity.sh introuvable dans le dépôt du serveur."
fi
libre=$(df -Pk -- "$HOME" 2>/dev/null | awk 'NR == 2 { print $4 }')
[[ ${libre:-} =~ ^[0-9]{1,15}$ ]] || echouer 76 "espace disque libre illisible (df)."
[ "$libre" -ge "$DISQUE_MIN_KO" ] || echouer 76 "disque presque plein : $((libre / 1024)) Mo libres, 10 Go au moins."

# À partir d'ici le dossier déposé est à nous : effacé à la sortie, quoi qu'il arrive.
trap 'rm -rf -- "$CONTEXTE" "$PRIVE"' EXIT
cp -- "$SERVEUR_OVH/images/tests/entree-tests.sh" "$PRIVE/entree-tests.sh" || echouer 1 "copie de entree-tests.sh impossible."
if [ -n "$VERSION_UNITY" ]; then
  cp -- "$SERVEUR_OVH/images/tests/entree-unity.sh" "$PRIVE/entree-unity.sh" || echouer 1 "copie de entree-unity.sh impossible."
fi
mkdir -p -- "$CONSTRUCTION/journaux" "$CONSTRUCTION/usage" || echouer 1 "dossiers de journaux impossibles."
JOURNAL="$CONSTRUCTION/journaux/$NOM.log"

# Seuls arguments : le réseau de construction par défaut, les deux étiquettes, l'étiquette de l'image et la copie privée.
timeout -k 30 "$DUREE_MAX" sudo -n docker build "${PULL[@]}" \
  --label myiafactory.genre=tests-derivee --label "myiafactory.empreinte=$SOMME" \
  "${ETIQUETTES_PLUS[@]}" -t "$ETIQUETTE" "$PRIVE" </dev/null 2>&1 | tail -c "$JOURNAL_OCTETS" > "$JOURNAL"
code=${PIPESTATUS[0]}
if [ "$code" != 0 ]; then
  tail -n 20 -- "$JOURNAL" 2>/dev/null | une_ligne >&2
  [ "$code" = 124 ] && echouer 124 "construction interrompue au-delà de $DUREE_MAX s."
  echouer 1 "docker build en échec (code $code)."
fi
octets=$(dk 60 image inspect --format '{{.Size}}' "$ETIQUETTE") && [[ $octets =~ ^[0-9]{1,15}$ ]] \
  || echouer 1 "taille de l'image illisible."
if [ -n "$VERSION_UNITY" ]; then                  # taille propre : l'image moins sa base GameCI (couches partagées)
  base_o=$(dk 60 image inspect --format '{{.Size}}' "$BASE") && [[ $base_o =~ ^[0-9]{1,15}$ ]] && [ "$base_o" -le "$octets" ] \
    && octets=$((octets - base_o))
fi
touch -- "$CONSTRUCTION/usage/$NOM" 2>/dev/null
printf '#image %s %s\n' "$ETIQUETTE" "$((octets / 1048576))"
