#!/usr/bin/env bash
# Enveloppe HÔTE d'une campagne de tests : exécutée sur le serveur par UNE session SSH du poste, elle reste au premier plan
# du début à la fin (place, conteneur, sortie en direct, nettoyage) ; l'entrée standard de la session sert de laisse.
# Usage : lancer_tests.sh <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps>
#   id t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; places 1..4 ; cpus 1..64 ; memoire_mo 256..65536 ; duree_s 1..3600 (nombres sans zéro
#   initial) ; projet ^[a-z0-9][a-z0-9-]{0,39}$ ; deps 16 hexa (cache Node ~/tests/.deps/<projet>/<deps>) ou « - ».
#   Chaque valeur est validée par un motif strict AVANT tout usage ; rien n'est jamais interprété par un shell (tableaux).
# Entrée standard : 1re ligne = la commande, tableau JSON de chaînes (4 096 octets au plus, contrôlé par tests_hote.py
#   --commande, la règle de entree-tests.sh) ; le reste = la laisse : un fils la lit jusqu'à la fin de fichier (session SSH
#   fermée, poste parti) puis tue le conteneur (docker kill tests-<id>) et l'enveloppe, qui nettoie (code 130).
# Dossier ~/tests/<id>/ (déposé par le poste avant) : entree/entree.tar (l'instantané, relu par tests_hote.py --archive avant
#   docker : fichiers ordinaires USTAR seulement, limites de l'instantané) ; écrits par l'enveloppe : entree/commande.json
#   (0600), travail/ (0700, créé vide ; un travail/ déjà là = identifiant déjà utilisé, refusé), enveloppe.pid et les
#   marques privées de l'hôte (code, sortie-coupee, erreur-coupee, disque-plein), jamais montées dans le conteneur.
# Sortie standard : celle du conteneur telle quelle, coupée à 50 Mo (52 428 800 octets ; le reste est lu et jeté).
# Sortie d'erreur : `#attente <rang> <total>` pendant la file (à chaque changement, rappel toutes les 30 s) ; la sortie
#   d'erreur du conteneur préfixée `| ` à chaque ligne (coupée à 50 Mo) ; les messages de l'enveloppe (« lancer_tests : … ») ;
#   et TOUJOURS en dernière ligne `#fin <code> <debut_epoch> <fin_epoch> <attente_s>` (debut = départ du conteneur, ou de
#   l'enveloppe s'il n'est pas parti). Aucune ligne du conteneur ne peut commencer par `#`.
# Codes : celui du conteneur (la commande ; 2 commande invalide, 70 extraction : entree-tests.sh) ; 124 durée dépassée ;
#   2 argument, commande, dossier ou entree.tar refusés, ou identifiant déjà utilisé (rien écrit, rien effacé) ;
#   70 instantané refusé par l'hôte ; 76 disque libre < 5 Go au départ, ou < 2 Go pendant la campagne (conteneur tué) ;
#   77 image myiafactory/tests absente, contrôle impossible ou utilisateur du serveur autre que 1000 ; 78 cache Node
#   absent ; 130 laisse coupée ou signal ; 1 erreur de l'enveloppe. Après un refus 2, rien n'est effacé ; après tout autre
#   départ, ~/tests/<id> est effacé, le ticket retiré et la place libérée.
# File : ticket ~/tests/.file/<date +%s%N>-<id> (contenu : le PID de l'enveloppe, écrit par un temporaire puis mv) ; tour
#   quand aucun ticket vivant (processus_vivant : PID dont la ligne de commande porte lancer_tests.sh et l'identifiant) n'est
#   plus ancien ; les tickets morts sont effacés. Place : le premier `flock -n` libre parmi ~/taches/.creneau-tests-1..4
#   (descripteur 8), et seulement si moins de <places> verrous sont tenus (comme lancer_agent.sh).
# Balayage à chaque lancement : ~/tests/t* de plus de 6 h sans enveloppe vivante -> effacés ; conteneurs étiquetés
#   myiafactory.genre=tests dont l'enveloppe ne vit plus -> supprimés (docker rm -f).
# Surveillant (fils, pendant le conteneur) : disque libre < 2 Go, échéance duree_s + 30 s (si `timeout` n'a pas suffi) ou
#   enveloppe disparue -> docker kill tests-<id>.
# Conteneur : sans réseau, racine en lecture seule, aucune capacité, utilisateur 1000, journal Docker désactivé (la sortie ne
#   remplit pas le disque), seulement travail/ (/work), entree/ (lecture seule) et le cache Node (lecture seule) montés ;
#   aucun secret, aucune variable de l'appelant : -e HOME=/tmp et -e MYIAFACTORY_TESTS_CONTENEUR=1 seulement.
# Réservées aux tests : ENVELOPPE_SONDE_S (période de la file et du surveillant, 1 s par défaut), ENVELOPPE_SORTIE_MAX_OCTETS.
set -u
export LC_ALL=C
umask 077

T0=$(date +%s)
DEBUT=""; ATTENTE=0

fin_simple() { printf '#fin %s %s %s 0\n' "$1" "$T0" "$(date +%s)" >&2; exit "$1"; }
refuser() { printf '%s\n' "lancer_tests : $1" >&2; fin_simple 2; }

ICI="$(cd "$(dirname "$0")" && pwd)"
. "$ICI/commun.sh" || refuser "commun.sh introuvable à côté de l'enveloppe."
AIDE="$ICI/tests_hote.py"
IMAGE="myiafactory/tests"
PLACES_MAX=4
DUREE_MAX=3600
DISQUE_MIN_KO=5242880                    # 5 Go libres au départ
DISQUE_ARRET_KO=2097152                  # 2 Go libres pendant la campagne
SORTIE_MAX=52428800
if [[ ${ENVELOPPE_SORTIE_MAX_OCTETS:-} =~ ^[1-9][0-9]{0,8}$ ]]; then SORTIE_MAX="$ENVELOPPE_SORTIE_MAX_OCTETS"; fi   # tests
SONDE="${ENVELOPPE_SONDE_S:-1}"
[[ $SONDE =~ $MOTIF_SONDE ]] || SONDE=1

# --- Arguments (rien n'est écrit avant la fin de ce bloc) ------------------

[ $# -eq 7 ] || refuser "usage : <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps>"
for argument in "$@"; do
  [[ $argument == *[[:cntrl:]]* ]] && refuser "caractère de contrôle refusé dans un argument."
done
ID="$1"; PLACES="$2"; CPUS="$3"; MEMOIRE="$4"; DUREE="$5"; PROJET="$6"; DEPS="$7"
[[ $ID =~ $MOTIF_ID ]] || refuser "identifiant refusé."
[[ $PLACES =~ ^[1-4]$ ]] || refuser "places refusées (1 à $PLACES_MAX)."
[[ $CPUS =~ $MOTIF_CPUS ]] && [ "$CPUS" -le 64 ] || refuser "cpus refusés (1 à 64)."
[[ $MEMOIRE =~ $MOTIF_MEMOIRE ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser "memoire_mo refusée (256 à 65536)."
[[ $DUREE =~ $MOTIF_DUREE ]] && [ "$DUREE" -le "$DUREE_MAX" ] || refuser "duree_s refusée (1 à $DUREE_MAX, sans zéro initial)."
[[ $PROJET =~ ^[a-z0-9][a-z0-9-]{0,39}$ ]] || refuser "projet refusé."
[[ $DEPS =~ ^([0-9a-f]{16}|-)$ ]] || refuser "deps refusé (16 hexa ou -)."
[[ ${HOME:-} == /* ]] || refuser "HOME absent ou relatif."
case "$HOME" in *[:,]*) refuser "HOME non admis (deux-points ou virgule : montage impossible)." ;; esac

# La commande : 1re ligne de l'entrée standard, lue octet par octet (read), jamais au-delà de 4 097 octets.
COMMANDE_JSON=""
IFS= read -r -n 4097 COMMANDE_JSON || [ -n "$COMMANDE_JSON" ] || refuser "commande absente (1re ligne de l'entrée standard)."
[ "${#COMMANDE_JSON}" -le 4096 ] || refuser "commande trop longue (4 096 octets au plus)."
[[ $COMMANDE_JSON == \[*\] ]] || refuser "commande refusée : un tableau JSON est attendu."
printf '%s' "$COMMANDE_JSON" | python3 -I "$AIDE" --commande 2>/dev/null || refuser "commande refusée : un tableau JSON de 1 à 64 chaînes est attendu."

TESTS="$HOME/tests"
DOSSIER="$TESTS/$ID"
ENTREE="$DOSSIER/entree"
for d in "$TESTS" "$DOSSIER" "$ENTREE"; do
  [ -d "$d" ] && [ ! -L "$d" ] || refuser "dossier ${d#"$HOME"/} absent (ou lien) : déposez l'instantané d'abord."
done
[ -f "$ENTREE/entree.tar" ] && [ ! -L "$ENTREE/entree.tar" ] || refuser "instantané ~/tests/$ID/entree/entree.tar absent."
# travail/ créé ici, et par nous seuls (mkdir échoue s'il existe) : c'est la prise de l'identifiant. Rien d'autre n'a été écrit.
mkdir -m 700 -- "$DOSSIER/travail" 2>/dev/null || refuser "identifiant $ID déjà utilisé (travail/ existe)."

# --- À partir d'ici, toute fin passe par finir : nettoyage puis #fin --------

A_NOUS=1; TICKET=""; PID_LAISSE=""; PID_SURVEILLANT=""; CONTENEUR=0

finir() {   # finir <code>
  local code="$1"
  trap '' PIPE TERM INT HUP
  trap - EXIT
  [ -n "$PID_LAISSE" ] && kill "$PID_LAISSE" 2>/dev/null
  [ -n "$PID_SURVEILLANT" ] && kill "$PID_SURVEILLANT" 2>/dev/null
  if [ "$CONTENEUR" = 1 ]; then                       # parti sans fin constatée : jamais de conteneur laissé derrière
    dk 30 kill "tests-$ID" >/dev/null 2>&1
    dk 30 rm -f "tests-$ID" >/dev/null 2>&1
  fi
  [ -n "$TICKET" ] && rm -f -- "$TICKET"
  liberer_creneau
  if [ -e "$DOSSIER/sortie-coupee" ]; then printf '%s\n' "Sortie coupée à 50 Mo" >&2; fi
  if [ -e "$DOSSIER/erreur-coupee" ]; then printf '%s\n' "Sortie d'erreur coupée à 50 Mo" >&2; fi
  if [ "$A_NOUS" = 1 ]; then
    [ -L "$DOSSIER/travail" ] || chmod -R u+rwX -- "$DOSSIER/travail" 2>/dev/null   # un dossier sans droits s'efface aussi
    rm -rf -- "$DOSSIER"
  fi
  printf '#fin %s %s %s %s\n' "$code" "${DEBUT:-$T0}" "$(date +%s)" "$ATTENTE" >&2
  exit "$code"
}
echouer() { printf '%s\n' "lancer_tests : $2" >&2; finir "$1"; }
trap 'finir 130' TERM INT HUP PIPE
trap 'finir 1' EXIT
# Fichiers de l'hôte dans ~/tests/<id>/ (hors de tout montage) : retirés d'abord, jamais écrits à travers un lien déposé.
rm -f -- "$DOSSIER/enveloppe.pid" "$DOSSIER/code" "$DOSSIER/disque-plein" "$DOSSIER/sortie-coupee" "$DOSSIER/erreur-coupee" \
  "$DOSSIER/laisse-coupee"
( set -C; printf '%s\n' "$$" > "$DOSSIER/enveloppe.pid" ) 2>/dev/null || echouer 1 "enveloppe.pid non écrit."

# Laisse : le reste de l'entrée standard. Fin de fichier = la session SSH est partie : conteneur tué, enveloppe arrêtée.
exec 6<&0 </dev/null
( trap - TERM INT HUP PIPE
  while IFS= read -r _ <&6; do :; done
  : > "$DOSSIER/laisse-coupee"                       # avant le kill : l'enveloppe rendra 130, pas le code du conteneur tué
  dk 30 kill "tests-$ID" >/dev/null 2>&1
  kill -TERM "$$" 2>/dev/null ) >/dev/null 2>&1 &
PID_LAISSE=$!
exec 6<&-

disque_libre_ko() { df -Pk -- "$HOME" 2>/dev/null | awk 'NR == 2 { print $4 }'; }

# --- Contrôles avant la file ------------------------------------------------

libre=$(disque_libre_ko)
[[ $libre =~ ^[0-9]{1,15}$ ]] || echouer 76 "espace disque libre illisible (df)."
[ "$libre" -ge "$DISQUE_MIN_KO" ] || echouer 76 "disque presque plein : $((libre / 1024)) Mo libres, 5 Go au moins."
[ "$(id -u)" = 1000 ] || echouer 77 "l'utilisateur du serveur doit être 1000 (celui du conteneur de tests)."
dk 20 image inspect "$IMAGE" >/dev/null 2>&1 || echouer 77 "image $IMAGE absente : installez la capacité tests-image."
DEPS_DOSSIER=""
if [ "$DEPS" != - ]; then
  DEPS_DOSSIER="$TESTS/.deps/$PROJET/$DEPS"
  for d in "$TESTS/.deps" "$TESTS/.deps/$PROJET" "$DEPS_DOSSIER"; do
    [ -d "$d" ] && [ ! -L "$d" ] || echouer 78 "cache des dépendances Node absent (~/tests/.deps/$PROJET/$DEPS)."
  done
fi
raison=$(python3 -I "$AIDE" --archive "$ENTREE/entree.tar" 2>&1 >/dev/null); r=$?
if [ "$r" = 1 ]; then echouer 70 "$(printf '%s' "$raison" | head -c 300 | tr -d '\000-\037')"; fi
[ "$r" = 0 ] || echouer 77 "contrôle de l'instantané impossible (python3)."
rm -f -- "$ENTREE/commande.json"                    # jamais écrit à travers un lien
( set -C; printf '%s' "$COMMANDE_JSON" > "$ENTREE/commande.json" ) 2>/dev/null || echouer 1 "commande.json non écrit."

# --- Balayage ----------------------------------------------------------------

enveloppe_vivante() { processus_vivant "$TESTS/$1/enveloppe.pid" "lancer_tests.sh" "$1"; }
while IFS= read -r -d '' d; do
  nom="${d##*/}"
  [[ $nom =~ $MOTIF_ID ]] && [ "$nom" != "$ID" ] || continue
  if [ -L "$d" ]; then rm -f -- "$d"; continue; fi
  [ -d "$d" ] || continue
  enveloppe_vivante "$nom" && continue
  [ -L "$d/travail" ] || chmod -R u+rwX -- "$d/travail" 2>/dev/null   # chmod suit un lien nommé : jamais sur un lien
  rm -rf -- "$d"
done < <(find "$TESTS" -mindepth 1 -maxdepth 1 -name 't*' -mmin +360 -print0 2>/dev/null)
noms=$(dk 20 ps -a --filter "label=myiafactory.genre=tests" --format '{{.Names}}' 2>/dev/null)
while IFS= read -r n; do
  [[ $n =~ ^tests-(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})$ ]] || continue
  autre="${BASH_REMATCH[1]}"
  [ "$autre" = "$ID" ] || enveloppe_vivante "$autre" || dk 30 rm -f "tests-$autre" >/dev/null 2>&1
done <<< "$noms"

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

COMMANDE=(run --rm --pull never --init --name "tests-$ID" --label myiafactory.genre=tests --log-driver none
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000
  --pids-limit 2048 --ulimit nofile=8192:8192 --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS"
  --tmpfs /tmp:size=4g,mode=1777
  -v "$DOSSIER/travail:/work" -v "$ENTREE:/entree:ro")
if [ -n "$DEPS_DOSSIER" ]; then COMMANDE+=(-v "$DEPS_DOSSIER:/deps:ro"); fi
COMMANDE+=(-e HOME=/tmp -e MYIAFACTORY_TESTS_CONTENEUR=1 "$IMAGE")

# Surveillant : garde la place (descripteur 8) tant qu'il vit ; tue le conteneur si le disque se remplit, si l'échéance
# est dépassée malgré timeout, ou si l'enveloppe a disparu.
( trap - TERM INT HUP PIPE
  echeance=$(( $(date +%s) + DUREE + 30 ))
  while sleep "$SONDE" 8>&-; do
    kill -0 "$$" 2>/dev/null || { dk 30 kill "tests-$ID"; exit 0; }
    l=$(disque_libre_ko)
    if [[ $l =~ ^[0-9]{1,15}$ ]] && [ "$l" -lt "$DISQUE_ARRET_KO" ]; then
      : > "$DOSSIER/disque-plein"; dk 30 kill "tests-$ID"; exit 0
    fi
    [ "$(date +%s)" -lt "$echeance" ] || { dk 30 kill "tests-$ID"; exit 0; }
  done ) >/dev/null 2>&1 &
PID_SURVEILLANT=$!

CONTENEUR=1
{
  { timeout "$DUREE" sudo -n docker "${COMMANDE[@]}" </dev/null 2>&1 1>&3 3>&- 8>&-
    printf '%s\n' "$?" > "$DOSSIER/code"
  } | python3 -I "$AIDE" --prefixer "$DOSSIER/erreur-coupee" "$SORTIE_MAX" >&2 3>&- 8>&-
} 3>&1 | python3 -I "$AIDE" --couper "$DOSSIER/sortie-coupee" "$SORTIE_MAX" 8>&-
if [ -e "$DOSSIER/laisse-coupee" ]; then finir 130; fi
code=""; [ -f "$DOSSIER/code" ] && IFS= read -r code < "$DOSSIER/code"
[[ $code =~ ^[0-9]{1,3}$ ]] || echouer 1 "code du conteneur illisible."
if [ "$code" != 124 ]; then CONTENEUR=0; fi           # docker run a rendu la main : conteneur fini (--rm)
if [ -e "$DOSSIER/disque-plein" ]; then echouer 76 "disque presque plein pendant la campagne : conteneur arrêté."; fi
finir "$code"
