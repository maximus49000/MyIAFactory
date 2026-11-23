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
# `--pull` : seulement quand la base n'est pas une image locale `myiafactory/*` (elle n'existe sur aucun registre : docker
#   build --pull échouerait) ; une base `unityci/editor` est tirée.
# Ramassage : ne touche QUE les images portant le label myiafactory.genre=tests-derivee ; jamais une image que le moindre
#   conteneur référence (docker ps -a ; en plus, rmi sans -f refuse une image en usage) ; d'abord toute image sans usage depuis
#   plus de 30 jours, puis la moins récemment utilisée tant que le total (docker image inspect .Size : la taille apparente,
#   qui compte la base partagée, donc par excès) dépasse le budget. Usage = date du fichier ~/tests/.construction/usage/<tests-12hexa>
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
MOTIF_BASE_UNITY='^unityci/editor(:[A-Za-z0-9._-]{1,100}|@sha256:[0-9a-f]{64})$'
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
  noms=$(dk 60 image ls --filter label=myiafactory.genre=tests-derivee --format '{{.Repository}}') \
    || echouer 1 "liste des images impossible (docker)."
  vivantes=$(dk 60 ps -a --format '{{.Image}}') || echouer 1 "liste des conteneurs impossible (docker) : rien n'est supprimé."
  maintenant=$(date +%s)
  lignes=""; total_mo=0
  while IFS= read -r nom; do
    [[ $nom =~ $MOTIF_ETIQUETTE ]] || continue
    grep -Fq -- " $nom " <<< "$lignes" && continue                    # une image par nom
    octets=$(dk 60 image inspect --format '{{.Size}}' "$nom") || continue
    [[ $octets =~ ^[0-9]{1,15}$ ]] || continue
    mo=$((octets / 1048576))
    usage="$CONSTRUCTION/usage/${nom#myiafactory/}"
    if [ -f "$usage" ] && [ ! -L "$usage" ]; then
      quand=$(stat -c %Y -- "$usage" 2>/dev/null)
    else
      cree=$(dk 60 image inspect --format '{{.Created}}' "$nom" 2>/dev/null)
      quand=$(date -d "$cree" +%s 2>/dev/null)
    fi
    [[ ${quand:-} =~ ^[0-9]{1,12}$ ]] || quand="$maintenant"          # date illisible : jamais « ancienne »
    lignes+="$quand $nom $mo"$'\n'
    total_mo=$((total_mo + mo))
  done <<< "$noms"
  while read -r quand nom mo; do
    [ -n "${nom:-}" ] || continue
    ancienne=0
    [ $((maintenant - quand)) -gt $((JOURS_INUTILISEE * 86400)) ] && ancienne=1
    [ "$ancienne" = 1 ] || [ "$total_mo" -gt "$budget_mo" ] || continue
    if grep -Fxq -- "$nom" <<< "$vivantes" || grep -Fxq -- "$nom:latest" <<< "$vivantes"; then continue; fi
    if dk 120 rmi "$nom" >/dev/null 2>&1; then
      rm -f -- "$CONSTRUCTION/usage/${nom#myiafactory/}"
      total_mo=$((total_mo - mo))
      printf '#ramassee %s\n' "$nom"
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
DOCKERFILE="$CONTEXTE/Dockerfile"
[ -f "$DOCKERFILE" ] || echouer 2 "Dockerfile absent du contexte."
taille=$(stat -c %s -- "$DOCKERFILE" 2>/dev/null)
[[ ${taille:-} =~ ^[0-9]{1,9}$ ]] && [ "$taille" -le "$DOSSIER_MAX_OCTETS" ] || echouer 2 "Dockerfile trop gros (64 Ko au plus)."
reelle=$(sha256sum -- "$DOCKERFILE" | cut -d' ' -f1)
[ "$reelle" = "$SOMME" ] || echouer 2 "le SHA-256 du Dockerfile n'est pas celui qui a été approuvé : construction refusée."
# Défense en profondeur (la somme approuvée suffit, ceci borne ce qu'un gabarit trafiqué pourrait demander).
[ "$(grep -Eic '^[[:space:]]*FROM[[:space:]]' "$DOCKERFILE")" = 1 ] || echouer 2 "une seule instruction FROM est permise."
BASE=$(awk 'toupper($1) == "FROM" { print $2; exit }' "$DOCKERFILE")
if [[ $BASE =~ $MOTIF_BASE_LOCALE ]]; then PULL=(); elif [[ $BASE =~ $MOTIF_BASE_UNITY ]]; then PULL=(--pull)
else echouer 2 "image de base refusée."; fi
if grep -Eiq '^[[:space:]]*(ADD|VOLUME|ONBUILD)[[:space:]]' "$DOCKERFILE" \
   || grep -Eiq -- '(^|[[:space:]])--(mount|network|security|privileged)([=[:space:]]|$)' "$DOCKERFILE"; then
  echouer 2 "instruction ou option interdite dans le Dockerfile."
fi
[ -f "$SERVEUR_OVH/images/tests/entree-tests.sh" ] && [ ! -L "$SERVEUR_OVH/images/tests/entree-tests.sh" ] \
  || echouer 1 "entree-tests.sh introuvable dans le dépôt du serveur."
libre=$(df -Pk -- "$HOME" 2>/dev/null | awk 'NR == 2 { print $4 }')
[[ ${libre:-} =~ ^[0-9]{1,15}$ ]] || echouer 76 "espace disque libre illisible (df)."
[ "$libre" -ge "$DISQUE_MIN_KO" ] || echouer 76 "disque presque plein : $((libre / 1024)) Mo libres, 10 Go au moins."

# À partir d'ici le contexte est à nous : effacé à la sortie, quoi qu'il arrive.
trap 'rm -rf -- "$CONTEXTE"' EXIT
rm -f -- "$CONTEXTE/entree-tests.sh"
cp -- "$SERVEUR_OVH/images/tests/entree-tests.sh" "$CONTEXTE/entree-tests.sh" || echouer 1 "copie de entree-tests.sh impossible."
mkdir -p -- "$CONSTRUCTION/journaux" "$CONSTRUCTION/usage" || echouer 1 "dossiers de journaux impossibles."
JOURNAL="$CONSTRUCTION/journaux/$NOM.log"

# Seuls arguments : le réseau de construction par défaut, les deux étiquettes, l'étiquette de l'image et le contexte.
timeout "$DUREE_MAX" sudo -n docker build "${PULL[@]}" \
  --label myiafactory.genre=tests-derivee --label "myiafactory.empreinte=$SOMME" \
  -t "$ETIQUETTE" "$CONTEXTE" </dev/null 2>&1 | tail -c "$JOURNAL_OCTETS" > "$JOURNAL"
code=${PIPESTATUS[0]}
if [ "$code" != 0 ]; then
  tail -n 20 -- "$JOURNAL" 2>/dev/null | une_ligne >&2
  [ "$code" = 124 ] && echouer 124 "construction interrompue au-delà de $DUREE_MAX s."
  echouer 1 "docker build en échec (code $code)."
fi
octets=$(dk 60 image inspect --format '{{.Size}}' "$ETIQUETTE") && [[ $octets =~ ^[0-9]{1,15}$ ]] \
  || echouer 1 "taille de l'image illisible."
touch -- "$CONSTRUCTION/usage/$NOM" 2>/dev/null
printf '#image %s %s\n' "$ETIQUETTE" "$((octets / 1048576))"
