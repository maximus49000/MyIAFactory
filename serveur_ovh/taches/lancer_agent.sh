#!/usr/bin/env bash
# Enveloppe HÔTE d'une tâche d'agent : exécutée sur le serveur (par SSH), elle prend une place d'agent, démarre le conteneur
# `myiafactory/agent` (entree-agent : claude -p sur le dépôt de la tâche) puis rend la main ; un veilleur DÉTACHÉ (setsid +
# nohup, survit à la fin de la session SSH) tient la place, applique les limites, contrôle le secret puis écrit l'état final.
# Usage : lancer_agent.sh <id> <seul|pilote> <duree_s> <memoire_mo> <cpus> <places> [<emulation_id>]
#   id et emulation_id : t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; duree_s 1..86400, memoire_mo 256..65536, cpus 1..64 (nombres sans zéro
#   initial) ; places 1..4 : nombre de places d'agent du serveur. Chaque valeur est validée par un motif strict AVANT tout
#   usage ; rien n'en est jamais interprété par un shell : les commandes sont des tableaux.
#   pilote : exige pont_hote.py à côté de ce script (tâche 7 ; absent, le mode pilote est refusé, code 2) et entree/app.apk.
# Sortie standard : UNE ligne JSON, l'état écrit dans ~/taches/<id>/etat.json (même forme que lancer_emulation.sh).
# Codes : 0 conteneur démarré (en_cours) ; 1 démarrage impossible (echouee) ; 2 argument refusé (rien créé) ; 3 tâche déjà en
#   cours (veilleur ou enveloppe vivants, rien modifié) ; 4 identifiant déjà utilisé (rien modifié) ; 75 toutes les places
#   prises (en_attente, à relancer).
# Place : le premier `flock -n` libre parmi ~/taches/.creneau-agent-1..<places> (descripteur 8, hérité par le veilleur) ; son
#   numéro est noté dans ~/taches/<id>/creneau.
# Dossier ~/taches/<id>/ : entree/ (déposé par le poste AVANT le lancement : projet.bundle, argv.json, consigne.md, message.md,
#   demande.json, et app.apk en pilote ; monté en lecture seule), travail/ (le dépôt de l'agent), maison/ (HOME de l'agent :
#   sessions de claude), sortie/ (flux.jsonl, claude.err, resultat.bundle, fin.json), pont/ et outil/ (pilote : socket du pont
#   hôte ; médias copiés par le pont hôte, en lecture seule dans le conteneur), etat.json, arret, enveloppe.pid, veilleur.pid,
#   pont-hote.pid, veilleur.log, docker-run.log, controle.log. travail/, maison/, sortie/ : 0700 (le conteneur tourne sous
#   l'utilisateur de l'hôte, --user $(id -u):$(id -g)).
# Reprise : si demande.json porte « "reprend": "<id>" » (une tâche finie), ~/taches/<id>/{travail,maison} sont copiés par
#   `cp -a` (liens copiés comme liens, jamais suivis).
# Jeton de l'abonnement : ~/agent-identifiants/jeton, monté EN LECTURE SEULE dans le seul conteneur de l'agent ; jamais lu par
#   cette enveloppe (sauf comme motif de grep -F, sans l'afficher), jamais sur une ligne de commande, en -e, ni dans un journal.
# Fin (veilleur), AVANT l'état final : (1) arrêt du conteneur, du pont hôte et, s'il existe, `arret: fin` de l'émulation liée
#   (emulation_id, sinon pont/emulation écrit par le pont hôte) ; (2) contrôle du secret : grep -F du jeton dans sortie/ (liens,
#   tubes et autres fichiers spéciaux retirés d'abord) puis dans le texte que produit `entree-agent --verifier` (git log -p et
#   objets du paquet) dans un conteneur de contrôle SANS jeton NI réseau (travail, sortie, entree en lecture seule) ; trouvé,
#   ou contrôle impossible -> sortie/ vidée, echouee/erreur, raison « secret de l'abonnement trouvé dans la sortie : rien n'est
#   rapatrié » ; (3) l'hôte ne lance JAMAIS git lui-même (ni sur travail/, ni ailleurs).
# Fin par le fichier arret : « fin » -> terminee, ok ; autre contenu -> arretee, ok ; échéance duree_s -> terminee, limite ;
#   conteneur parti avec sortie/fin.json -> terminee, ok (le code de claude est dans fin.json), sans -> echouee, erreur ;
#   sortie/ au-delà de LIMITE_SORTIE_KO (sondage du -sk, pas un quota) -> terminee, limite.
# Réservées aux tests : ENVELOPPE_SONDE_S (période de surveillance, 5 s), ENVELOPPE_SORTIE_MAX_KO.
set -u
export LC_ALL=C
exec </dev/null

# Fonctions communes aux enveloppes et motifs MOTIF_ID, MOTIF_DUREE, MOTIF_MEMOIRE, MOTIF_CPUS, MOTIF_SONDE : commun.sh.
ICI="$(cd "$(dirname "$0")" && pwd)"
. "$ICI/commun.sh" || { printf '%s\n' "lancer_agent : commun.sh introuvable à côté de l'enveloppe." >&2; exit 2; }
IMAGE="myiafactory/agent"
RESEAU="myiafactory-agents"
RAISON_SECRET="secret de l'abonnement trouvé dans la sortie : rien n'est rapatrié"
LIMITE_SORTIE_KO=540672                   # paquet 500 Mo + flux 20 Mo + erreurs et fin.json, en Ko (du -sk)
if [[ ${ENVELOPPE_SORTIE_MAX_KO:-} =~ ^[1-9][0-9]{0,8}$ ]]; then LIMITE_SORTIE_KO="$ENVELOPPE_SORTIE_MAX_KO"; fi   # tests
DELAI_CONTROLE_S=900
MOTIF_REPREND='"reprend"[[:space:]]*:[[:space:]]*"(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})"'
MOTIF_REPREND_NUL='"reprend"[[:space:]]*:[[:space:]]*null'

refuser() { printf '%s\n' "lancer_agent : $1" >&2; exit 2; }

VEILLEUR=0
if [ "${1:-}" = --veilleur ]; then VEILLEUR=1; shift; fi
[ $# -ge 6 ] && [ $# -le 7 ] || refuser "usage : <id> <seul|pilote> <duree_s> <memoire_mo> <cpus> <places> [<emulation_id>]"
for argument in "$@"; do                 # aucun caractère de contrôle (retour à la ligne final compris)
  [[ $argument == *[[:cntrl:]]* ]] && refuser "caractère de contrôle refusé dans un argument."
done
ID="$1"; MODE="$2"; DUREE="$3"; MEMOIRE="$4"; CPUS="$5"; PLACES="$6"; EMU=""
[[ $ID =~ $MOTIF_ID ]] || refuser "identifiant refusé."
[ "$MODE" = seul ] || [ "$MODE" = pilote ] || refuser "mode refusé (seul ou pilote)."
[[ $DUREE =~ $MOTIF_DUREE ]] && [ "$DUREE" -le 86400 ] || refuser "duree_s refusée (1 à 86400, sans zéro initial)."
[[ $MEMOIRE =~ $MOTIF_MEMOIRE ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser "memoire_mo refusée (256 à 65536)."
[[ $CPUS =~ $MOTIF_CPUS ]] && [ "$CPUS" -le 64 ] || refuser "cpus refusés (1 à 64)."
[[ $PLACES =~ ^[1-4]$ ]] || refuser "places refusées (1 à 4)."
if [ $# -ge 7 ]; then
  [[ $7 =~ $MOTIF_ID ]] && [ "$7" != "$ID" ] || refuser "identifiant d'émulation refusé."
  EMU="$7"
fi
if [ "$MODE" = pilote ] && [ ! -f "$ICI/pont_hote.py" ]; then
  refuser "mode pilote indisponible : le pont hôte (pont_hote.py) n'est pas sur ce serveur."
fi
[ -n "${HOME:-}" ] || refuser "HOME absent."
SONDE="${ENVELOPPE_SONDE_S:-5}"
[[ $SONDE =~ $MOTIF_SONDE ]] || SONDE=5

TACHES="$HOME/taches"
DOSSIER="$TACHES/$ID"
JETON="$HOME/agent-identifiants/jeton"
SELF="$ICI/$(basename "$0")"

# --- Fin de tâche : pont, émulation liée, contrôle du secret ----------------

pont_vivant() { processus_vivant "$DOSSIER/pont-hote.pid" "pont_hote.py $ID"; }

arreter_pont_et_emulation() {
  local pid="" e="$EMU" n
  if pont_vivant; then
    IFS= read -r pid < "$DOSSIER/pont-hote.pid"
    kill -TERM "$pid" 2>/dev/null
    for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50; do
      pont_vivant || break
      sleep 0.1
    done
    pont_vivant && kill -KILL "$pid" 2>/dev/null
  fi
  # pont/emulation (pilote) est écrit par le pont hôte ; fichier ordinaire seulement (jamais un tube ni un lien), motif strict.
  if [ -z "$e" ] && [ -f "$DOSSIER/pont/emulation" ] && [ ! -L "$DOSSIER/pont/emulation" ]; then
    e=$(head -c 64 -- "$DOSSIER/pont/emulation" 2>/dev/null | head -n 1)
  fi
  if [[ $e =~ $MOTIF_ID ]] && [ "$e" != "$ID" ] && [ -d "$TACHES/$e" ] && [ ! -L "$TACHES/$e" ]; then
    printf 'fin\n' > "$TACHES/$e/arret" 2>/dev/null
  fi
  return 0
}

vider_sortie() {   # rien de sortie/ ne doit plus pouvoir être rapatrié (liens jamais suivis : rm et find ne les suivent pas)
  chmod -R u+rwX -- "$DOSSIER/sortie" 2>/dev/null
  find "$DOSSIER/sortie" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null
  return 0
}

# controle_secret : 0 propre ; 1 jeton trouvé ; 2 contrôle impossible (jeton illisible, grep en échec, conteneur de contrôle
# en échec ou trop long). Le jeton n'est qu'un FICHIER de motifs pour grep -F : sa valeur n'est jamais lue ni affichée ici.
controle_secret() {
  local g ps
  [ -f "$JETON" ] && [ ! -L "$JETON" ] && [ -s "$JETON" ] || return 2
  find "$DOSSIER/sortie" -mindepth 1 ! -type f ! -type d -exec rm -f -- {} + 2>/dev/null   # liens, tubes, sockets : retirés
  chmod -R u+rwX -- "$DOSSIER/sortie" 2>/dev/null                  # un fichier rendu illisible par l'agent est lu quand même
  timeout 600 grep -rqsF -D skip -f "$JETON" -- "$DOSSIER/sortie"; g=$?
  [ "$g" = 0 ] && return 1
  [ "$g" = 1 ] || return 2
  [ -e "$DOSSIER/travail/projet" ] || [ -L "$DOSSIER/travail/projet" ] || return 0      # rien cloné : aucun commit possible
  # Le texte des commits et des objets du paquet, produit dans un conteneur de contrôle SANS jeton ni réseau (jamais par un
  # git de l'hôte : la configuration du dépôt de l'agent pourrait y lancer n'importe quoi).
  CONTROLE=(run --rm --pull never --name "controle-$ID" --network none --user "$UTILISATEUR" --read-only
    --tmpfs /tmp:size=1g --cap-drop ALL --security-opt no-new-privileges --pids-limit 512
    --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS" -e HOME=/tmp
    -v "$DOSSIER/entree:/entree:ro" -v "$DOSSIER/travail:/travail:ro" -v "$DOSSIER/sortie:/sortie:ro"
    "$IMAGE" entree-agent --verifier)
  dk "$DELAI_CONTROLE_S" "${CONTROLE[@]}" 2>>"$DOSSIER/controle.log" | timeout "$DELAI_CONTROLE_S" grep -qF -f "$JETON"
  ps=("${PIPESTATUS[@]}")
  dk 30 rm -f "controle-$ID" >/dev/null 2>&1             # déjà retiré (--rm) d'ordinaire ; jamais un conteneur laissé
  [ "${ps[1]}" = 0 ] && return 1
  [ "${ps[1]}" = 1 ] && [ "${ps[0]}" = 0 ] && return 0
  return 2
}

# --- Veilleur (détaché) ----------------------------------------------------

veilleur() {
  { : >&8; } 2>/dev/null || exit 2                  # sans la place héritée de l'enveloppe, jamais de veilleur
  printf '%s\n' "$$" > "$DOSSIER/veilleur.pid"
  local debut_iso debut_s maintenant pannes=0 etat_conteneur motif ko prochaine pause
  debut_iso=$(debut_ecrit); [ -n "$debut_iso" ] || debut_iso=$(maintenant_iso)
  debut_s=$(date +%s)
  FINI=0
  conclure() {   # conclure <etat> <statut> <raison>
    FINI=1
    ecrire_etat "$1" "$2" "$debut_iso" "$(maintenant_iso)" "$3"
    liberer_creneau
    exit 0
  }
  # finir <etat> <statut> <raison> : le conteneur de l'agent est arrêté ; pont et émulation liée arrêtés, puis contrôle du
  # secret, et seulement alors l'état final.
  finir() {
    local r
    arreter_pont_et_emulation
    controle_secret; r=$?
    if [ "$r" = 1 ]; then vider_sortie; conclure echouee erreur "$RAISON_SECRET"; fi
    if [ "$r" != 0 ]; then
      vider_sortie
      conclure echouee erreur "Contrôle du secret de l'abonnement impossible (voir controle.log) : rien n'est rapatrié."
    fi
    conclure "$1" "$2" "$3"
  }
  trap 'if [ "$FINI" = 0 ]; then arreter_conteneur; arreter_pont_et_emulation; vider_sortie; conclure echouee erreur "Veilleur interrompu avant la fin de la tâche : rien n est rapatrié."; fi' EXIT
  trap 'exit 143' TERM INT HUP
  arreter_puis() {   # arreter_puis <etat> <statut> <raison>
    if ! arreter_conteneur; then
      arreter_pont_et_emulation
      vider_sortie
      conclure echouee erreur "$3 mais le conteneur tache-$ID ne s'arrête pas : à arrêter à la main (docker stop) ; rien n'est rapatrié."
    fi
    finir "$1" "$2" "$3."
  }
  while :; do
    conteneur_vivant; etat_conteneur=$?
    if [ "$etat_conteneur" = 1 ]; then
      if [ -f "$DOSSIER/sortie/fin.json" ] && [ ! -L "$DOSSIER/sortie/fin.json" ]; then
        finir terminee ok "L'agent a fini (sortie/fin.json)."
      fi
      finir echouee erreur "Le conteneur de l'agent s'est arrêté sans écrire fin.json (voir sortie/claude.err)."
    elif [ "$etat_conteneur" = 2 ]; then
      pannes=$((pannes + 1))
      if [ "$pannes" -ge 30 ]; then
        arreter_pont_et_emulation
        vider_sortie
        conclure echouee erreur "Docker ne répond plus : état du conteneur inconnu ; rien n'est rapatrié."
      fi
    else
      pannes=0
    fi
    if [ -e "$DOSSIER/arret" ]; then
      motif=""; IFS= read -r motif < "$DOSSIER/arret" 2>/dev/null
      if [ "$motif" = fin ]; then arreter_puis terminee ok "Fin demandée par le lanceur (arret : fin)"; fi
      arreter_puis arretee ok "Arrêt demandé (fichier arret)"
    fi
    maintenant=$(date +%s)
    if [ $((maintenant - debut_s)) -ge "$DUREE" ]; then arreter_puis terminee limite "Durée maximale atteinte (${DUREE} s)"; fi
    prochaine=$((DUREE - (maintenant - debut_s)))
    ko=$(du -sk "$DOSSIER/sortie" 2>/dev/null | cut -f1)
    if [[ $ko =~ ^[0-9]+$ ]] && [ "$ko" -gt "$LIMITE_SORTIE_KO" ]; then
      arreter_puis terminee limite "Limite atteinte : sortie trop volumineuse (${ko} Ko, maximum ${LIMITE_SORTIE_KO} Ko)"
    fi
    # Sommeil d'une sonde, raccourci jusqu'à l'échéance si elle tombe avant (au moins 1 s).
    pause="$SONDE"
    [ "$prochaine" -ge 1 ] || prochaine=1
    [ "${SONDE%%.*}" -ge "$prochaine" ] && pause="$prochaine"
    sleep "$pause"
  done
}

UTILISATEUR="$(id -u):$(id -g)"           # le conteneur tourne sous l'utilisateur de l'hôte (propriétaire des dossiers)

if [ "$VEILLEUR" = 1 ]; then veilleur; exit 0; fi

# --- Enveloppe (au premier plan, rend vite la main) ------------------------

veilleur_vivant() { processus_vivant "$DOSSIER/veilleur.pid" "--veilleur $ID"; }
enveloppe_vivante() { processus_vivant "$DOSSIER/enveloppe.pid" "lancer_agent.sh $ID"; }
echec() { arreter_pont_et_emulation; fin_erreur "$1"; }   # fin_erreur (commun.sh) après le départ éventuel du pont

# Un identifiant ne sert qu'une fois : seul un état absent ou en_attente (jamais démarré) peut être relancé. Rien n'est modifié.
if [ -f "$DOSSIER/etat.json" ] && ! grep -q '"etat": "en_attente"' "$DOSSIER/etat.json"; then
  montrer_etat
  if grep -q '"etat": "en_cours"' "$DOSSIER/etat.json" && { veilleur_vivant || enveloppe_vivante; }; then exit 3; fi
  exit 4
fi

umask 077
mkdir -p -- "$DOSSIER/entree" "$DOSSIER/sortie" "$DOSSIER/travail" "$DOSSIER/maison" || refuser "dossier de la tâche non créable."
chmod 700 "$DOSSIER/sortie" "$DOSSIER/travail" "$DOSSIER/maison" 2>/dev/null
rm -f "$DOSSIER/arret"

case "$DOSSIER$JETON" in
  *[,:]*) fin_erreur "Chemin non admis (virgule ou deux-points) : montage impossible." ;;
esac
for f in projet.bundle argv.json consigne.md message.md demande.json; do
  [ -f "$DOSSIER/entree/$f" ] && [ ! -L "$DOSSIER/entree/$f" ] || fin_erreur "Entrée manquante : entree/$f (déposée par le poste avant le lancement)."
done
[ -s "$DOSSIER/entree/projet.bundle" ] || fin_erreur "Entrée vide : entree/projet.bundle."
if [ "$MODE" = pilote ]; then
  [ -f "$DOSSIER/entree/app.apk" ] && [ ! -L "$DOSSIER/entree/app.apk" ] && [ -s "$DOSSIER/entree/app.apk" ] ||
    fin_erreur "Entrée manquante : entree/app.apk (mode pilote)."
fi
[ -f "$JETON" ] && [ ! -L "$JETON" ] && [ -s "$JETON" ] ||
  fin_erreur "Jeton de l'abonnement absent (~/agent-identifiants/jeton) : le Directeur l'enregistre une fois sur le serveur par bash ~/myiafactory/serveur_ovh/taches/enregistrer_jeton.sh."
[[ $UTILISATEUR =~ ^[0-9]{1,10}:[0-9]{1,10}$ ]] || fin_erreur "Utilisateur de l'hôte illisible (id -u, id -g)."
[ "${UTILISATEUR%%:*}" != 0 ] || fin_erreur "Refusé : un agent ne tourne jamais sous root (enveloppe à lancer par un utilisateur ordinaire)."

# Reprise : « "reprend": "<id>" » de demande.json (écrit par le poste) ; une clé en double ou une valeur autre qu'un
# identifiant ou null est refusée.
REPREND=""
demande=$(head -c 65536 -- "$DOSSIER/entree/demande.json" 2>/dev/null)
reste="${demande//\"reprend\"/}"
occurrences=$(( (${#demande} - ${#reste}) / 9 ))
if [ "$occurrences" -gt 1 ]; then fin_erreur "demande.json : clé reprend en double."; fi
if [ "$occurrences" = 1 ]; then
  if [[ $demande =~ $MOTIF_REPREND ]]; then REPREND="${BASH_REMATCH[1]}"
  elif ! [[ $demande =~ $MOTIF_REPREND_NUL ]]; then fin_erreur "demande.json : reprise mal formée (identifiant de tâche ou null)."
  fi
fi
SOURCE=""
if [ -n "$REPREND" ]; then
  [ "$REPREND" != "$ID" ] || fin_erreur "Reprise refusée : une tâche ne se reprend pas elle-même."
  SOURCE="$TACHES/$REPREND"
  [ -d "$SOURCE" ] && [ ! -L "$SOURCE" ] && [ -d "$SOURCE/travail" ] && [ ! -L "$SOURCE/travail" ] &&
    [ -d "$SOURCE/maison" ] && [ ! -L "$SOURCE/maison" ] ||
    fin_erreur "Reprise impossible : ~/taches/$REPREND/travail et maison absents."
  grep -qE '"etat": "(terminee|arretee|echouee)"' "$SOURCE/etat.json" 2>/dev/null ||
    fin_erreur "Reprise impossible : la tâche $REPREND n'est pas finie."
fi

trap '' HUP                         # la fin de la session SSH ne doit jamais interrompre l'écriture de l'état
CRENEAU=""
for ((i = 1; i <= PLACES; i++)); do
  exec 8>> "$TACHES/.creneau-agent-$i" || { ecrire_etat echouee erreur "" "$(maintenant_iso)" "Place d'agent inaccessible."; exit 1; }
  if flock -n 8; then CRENEAU="$i"; break; fi
  exec 8>&-
done
[ -n "$CRENEAU" ] || occupe "Toutes les places d'agent du serveur sont prises ($PLACES) : relancez plus tard."
honorer_final
printf '%s\n' "$CRENEAU" > "$DOSSIER/creneau"
printf '%s\n' "$$" > "$DOSSIER/enveloppe.pid"      # AVANT en_cours : un second lancement voit une enveloppe vivante
ecrire_etat en_cours "" "$(maintenant_iso)" "" "Conteneur de l'agent en cours de démarrage."

if [ -n "$REPREND" ]; then                         # liens copiés comme liens (cp -a), jamais suivis
  cp -a -- "$SOURCE/travail/." "$DOSSIER/travail/" && cp -a -- "$SOURCE/maison/." "$DOSSIER/maison/" ||
    fin_erreur "Reprise impossible : copie de ~/taches/$REPREND (travail, maison) en échec."
fi

if [ "$MODE" = pilote ]; then                      # pont hôte détaché, sans la place (8>&-) ni l'environnement Python
  mkdir -p -- "$DOSSIER/pont" "$DOSSIER/outil" && chmod 700 "$DOSSIER/pont" "$DOSSIER/outil" ||
    fin_erreur "Dossiers du pont non créables."
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup python3 -I "$ICI/pont_hote.py" "$ID" </dev/null >> "$DOSSIER/pont-hote.out" 2>&1 8>&- &
  else
    nohup python3 -I "$ICI/pont_hote.py" "$ID" </dev/null >> "$DOSSIER/pont-hote.out" 2>&1 8>&- &
  fi
  printf '%s\n' "$!" > "$DOSSIER/pont-hote.pid"
  disown 2>/dev/null
fi

# -v (et non --mount, voulu par le plan) : chaque source existe déjà (créée ci-dessus, jeton vérifié), jamais créée par root.
COMMANDE=(run --pull never -d --rm --name "tache-$ID" --user "$UTILISATEUR" --read-only --tmpfs /tmp:size=1g
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 512
  --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS" --network "$RESEAU" -e HOME=/maison
  -v "$DOSSIER/entree:/entree:ro" -v "$DOSSIER/travail:/travail" -v "$DOSSIER/maison:/maison" -v "$DOSSIER/sortie:/sortie"
  -v "$JETON:/run/identifiants/jeton:ro")
if [ "$MODE" = pilote ]; then COMMANDE+=(-v "$DOSSIER/pont:/pont" -v "$DOSSIER/outil:/outil:ro"); fi
COMMANDE+=("$IMAGE" entree-agent)
if ! dk 120 "${COMMANDE[@]}" >/dev/null 2>"$DOSSIER/docker-run.log"; then
  dk 30 rm -f "tache-$ID" >/dev/null 2>&1          # un docker run figé (délai) a pu laisser un conteneur à demi créé
  echec "Démarrage du conteneur de l'agent impossible (docker run en échec : voir docker-run.log)."
fi

detacher_veilleur "$ID" "$MODE" "$DUREE" "$MEMOIRE" "$CPUS" "$PLACES" ${EMU:+"$EMU"}
montrer_etat
exit 0
