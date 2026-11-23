#!/usr/bin/env bash
# Enveloppe HÔTE d'une tâche d'agent : exécutée sur le serveur (par SSH), elle prend une place d'agent, démarre le conteneur
# `myiafactory/agent` (entree-agent : claude -p sur le dépôt de la tâche) puis rend la main ; un veilleur DÉTACHÉ (setsid +
# nohup, survit à la fin de la session SSH) tient la place, applique les limites, contrôle le secret puis écrit l'état final.
# Usage : lancer_agent.sh <id> <seul|pilote> <duree_s> <memoire_mo> <cpus> <places> [<emulation_id>]
#   id et emulation_id : t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; duree_s 1..86400, memoire_mo 256..65536, cpus 1..64 (nombres sans zéro
#   initial) ; places 1..4 : nombre de places d'agent du serveur. Chaque valeur est validée par un motif strict AVANT tout
#   usage ; rien n'en est jamais interprété par un shell : les commandes sont des tableaux.
#   pilote : exige pont_hote.py et lancer_emulation.sh à côté de ce script (déposés avec lui ; absents, le mode pilote est
#   refusé, code 2) et entree/app.apk. Le pont hôte (python3 -I pont_hote.py <id> <duree_s>, détaché, chef de son groupe ;
#   l'émulation liée reçoit la durée qui reste à l'agent) crée
#   l'émulation au premier `demarrer` de l'agent (créneau d'émulation à part des places d'agent).
# Sortie standard : UNE ligne JSON, l'état écrit dans ~/taches/<id>/etat.json (même forme que lancer_emulation.sh).
# Codes : 0 conteneur démarré (en_cours) ; 1 démarrage impossible (echouee) ; 2 argument refusé (rien créé) ; 3 tâche déjà en
#   cours (veilleur ou enveloppe vivants, rien modifié) ; 4 identifiant déjà utilisé (rien modifié) ; 75 toutes les places
#   prises (en_attente, à relancer).
# Place : le premier `flock -n` libre parmi ~/taches/.creneau-agent-1..<places> (descripteur 8, hérité par le veilleur), et
#   seulement si moins de <places> verrous parmi les 4 sont tenus ; son numéro est noté dans ~/taches/<id>/creneau.
# Conteneurs étiquetés myiafactory.genre=agent (agent et contrôle) : lancer_emulation.sh ne les prend pas pour un émulateur.
# Émulation liée (pilote) : l'argument 7, sinon ~/taches/<id>/emulation (écrit sur l'hôte par le pont hôte, hors de tout
#   montage) ; elle n'est arrêtée que si ~/taches/<emu>/demande.json porte "type": "emulation" et ~/taches/<emu>/agent porte <id>.
# Dossier ~/taches/<id>/ : entree/ (déposé par le poste AVANT le lancement : projet.bundle, argv.json, consigne.md, message.md,
#   demande.json, et app.apk en pilote ; monté en lecture seule), travail/ (le dépôt de l'agent), maison/ (HOME de l'agent :
#   sessions de claude), sortie/ (flux.jsonl, claude.err, resultat.bundle, fin.json), pont/ et outil/ (pilote : socket du pont
#   hôte ; médias copiés par le pont hôte, en lecture seule dans le conteneur), etat.json, arret, enveloppe.pid, veilleur.pid,
#   pont-hote.pid, pont-hote.log et pont-hote.out (journal et sorties du pont hôte), emulation (pilote : l'émulation liée),
#   veilleur.log, docker-run.log, controle.log. travail/, maison/, sortie/ : 0700 (le conteneur tourne sous
#   l'utilisateur de l'hôte, --user $(id -u):$(id -g)).
# Reprise : si demande.json porte « "reprend": "<id>" » (une tâche finie), ~/taches/<id>/{travail,maison} sont copiés par
#   `cp -a` (liens copiés comme liens, jamais suivis).
# Jeton de l'abonnement : ~/agent-identifiants/jeton, monté EN LECTURE SEULE dans le seul conteneur de l'agent ; jamais lu par
#   cette enveloppe (sauf comme motif de grep -F, sans l'afficher), jamais sur une ligne de commande, en -e, ni dans un journal.
# Fin (veilleur), AVANT l'état final : (1) arrêt du conteneur (docker stop -t 60 : l'entrée conclut sur SIGTERM, le travail
#   déjà fait n'est pas perdu), du pont hôte (son groupe) et `arret: fin` de l'émulation liée ; (2) contrôle du secret : le
#   fichier du jeton doit être UNE ligne valide (sinon contrôle impossible) ; grep -F du jeton et de ses trois alignements base64
#   dans sortie/ (liens, tubes et autres fichiers spéciaux retirés d'abord) puis, TOUJOURS, dans le texte que produit
#   `entree-agent --verifier` (git log -p et objets du paquet) dans un conteneur de contrôle SANS jeton NI réseau (travail,
#   sortie, entree en lecture seule ; ses erreurs vont dans controle.log, filtrées du jeton, 64 Ko) ; trouvé -> sortie/ vidée,
#   echouee/erreur, raison « secret de l'abonnement trouvé dans la sortie : rien n'est rapatrié » ; contrôle impossible -> de
#   même (sortie/ vidée, echouee/erreur) ; (3) l'hôte ne lance JAMAIS git lui-même (ni sur travail/, ni ailleurs).
# Fin par le fichier arret : « fin » -> terminee, ok ; autre contenu -> arretee, ok ; échéance duree_s -> terminee, limite ;
#   conteneur parti avec sortie/fin.json -> terminee, ok (le code de claude est dans fin.json ; "echeance": true -> limite),
#   sans -> echouee, erreur ; sortie/ au-delà de LIMITE_SORTIE_KO, travail/ + maison/ au-delà de TRAVAIL_MAX_KO (sondages du
#   en taille apparente, pas des quotas), moins de LIBRE_MIN_KO libres sur le disque -> terminee, limite.
# Durée : duree_s (argument 3) fait foi ; elle est passée au conteneur (-e AGENT_DUREE_S) : l'échéance interne de l'entrée
#   (duree_s - 120 s) et celle du veilleur partent de la même valeur, quoi que porte limites.duree_s dans demande.json.
# Hôte exigé : kernel.yama.ptrace_scope >= 1 (lu dans /proc/sys/kernel/yama/ptrace_scope ; 0 -> echouee, rien ne démarre ;
#   illisible -> avertissement dans veilleur.log et sur stderr, la tâche démarre).
# Réservées aux tests : ENVELOPPE_SONDE_S (période de surveillance, 5 s), ENVELOPPE_SORTIE_MAX_KO, ENVELOPPE_TRAVAIL_MAX_KO,
#   ENVELOPPE_DU_TRAVAIL_S, ENVELOPPE_LIBRE_MIN_KO, ENVELOPPE_PTRACE_SCOPE (fichier lu à la place de celui de Yama).
set -u
export LC_ALL=C
exec </dev/null

# Fonctions communes aux enveloppes et motifs MOTIF_ID, MOTIF_DUREE, MOTIF_MEMOIRE, MOTIF_CPUS, MOTIF_SONDE : commun.sh.
ICI="$(cd "$(dirname "$0")" && pwd)"
. "$ICI/commun.sh" || { printf '%s\n' "lancer_agent : commun.sh introuvable à côté de l'enveloppe." >&2; exit 2; }
IMAGE="myiafactory/agent"
RESEAU="myiafactory-agents"
GENRE="myiafactory.genre=agent"           # étiquette : lancer_emulation.sh ne compte pas ces conteneurs comme des émulateurs
RAISON_SECRET="secret de l'abonnement trouvé dans la sortie : rien n'est rapatrié"
PLACES_MAX=4                              # places de 1 à 4 : les 4 verrous sont toujours comptés (places abaissé : jamais dépassé)
DELAI_ARRET=60                            # docker stop -t : l'entrée de l'agent conclut (restes, paquet, fin.json) sur SIGTERM
# Tailles en taille APPARENTE (du --apparent-size : un fichier creux compte pour sa taille annoncée, celle qu'un transfert
# copierait ; T3 borne aussi ce qu'il rapatrie à la taille apparente).
LIMITE_SORTIE_KO=540672                   # sortie/ : paquet 500 Mo + flux 20 Mo + erreurs et fin.json, en Ko
if [[ ${ENVELOPPE_SORTIE_MAX_KO:-} =~ ^[1-9][0-9]{0,8}$ ]]; then LIMITE_SORTIE_KO="$ENVELOPPE_SORTIE_MAX_KO"; fi   # tests
TRAVAIL_MAX_KO=8388608                    # travail/ + maison/ : 8 Go au plus (sondés toutes les DU_TRAVAIL_S secondes)
if [[ ${ENVELOPPE_TRAVAIL_MAX_KO:-} =~ ^[1-9][0-9]{0,11}$ ]]; then TRAVAIL_MAX_KO="$ENVELOPPE_TRAVAIL_MAX_KO"; fi   # tests
DU_TRAVAIL_S=60
if [[ ${ENVELOPPE_DU_TRAVAIL_S:-} =~ ^[1-9][0-9]{0,3}$ ]]; then DU_TRAVAIL_S="$ENVELOPPE_DU_TRAVAIL_S"; fi          # tests
LIBRE_MIN_KO=5242880                      # disque du serveur : moins de 5 Go libres (df -Pk) -> la tâche s'arrête en limite
if [[ ${ENVELOPPE_LIBRE_MIN_KO:-} =~ ^[1-9][0-9]{0,11}$ ]]; then LIBRE_MIN_KO="$ENVELOPPE_LIBRE_MIN_KO"; fi           # tests
DELAI_CONTROLE_S=900
CONTROLE_LOG_MAX=65536                    # controle.log : 64 Ko par contrôle au plus, lignes portant le jeton retirées
MOTIF_REPREND='"reprend"[[:space:]]*:[[:space:]]*"(t[0-9]{8}-[0-9]{6}-[0-9a-f]{4})"'
MOTIF_REPREND_NUL='"reprend"[[:space:]]*:[[:space:]]*null'
MOTIF_PROJET='"projet"[[:space:]]*:[[:space:]]*"([^"\\]{1,200})"'
MOTIF_TYPE_EMULATION='"type"[[:space:]]*:[[:space:]]*"emulation"'
MOTIF_ECHEANCE='"echeance"[[:space:]]*:[[:space:]]*true'
PTRACE_SCOPE=/proc/sys/kernel/yama/ptrace_scope    # lu seulement (jamais modifié ici)
if [ -n "${ENVELOPPE_PTRACE_SCOPE:-}" ]; then PTRACE_SCOPE="$ENVELOPPE_PTRACE_SCOPE"; fi                           # tests

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
if [ "$MODE" = pilote ]; then
  for f in pont_hote.py lancer_emulation.sh; do
    [ -f "$ICI/$f" ] && [ ! -L "$ICI/$f" ] || refuser "mode pilote indisponible : $f (pont hôte) n'est pas sur ce serveur."
  done
fi
[ -n "${HOME:-}" ] || refuser "HOME absent."
SONDE="${ENVELOPPE_SONDE_S:-5}"
[[ $SONDE =~ $MOTIF_SONDE ]] || SONDE=5

TACHES="$HOME/taches"
DOSSIER="$TACHES/$ID"
JETON="$HOME/agent-identifiants/jeton"
SELF="$ICI/$(basename "$0")"
case "$DOSSIER$JETON" in                 # -v source:cible[:ro] : ni virgule ni deux-points, refusé avant toute création
  *[,:]*) refuser "chemin non admis (virgule ou deux-points dans HOME) : montage impossible." ;;
esac

# --- Fin de tâche : pont, émulation liée, contrôle du secret ----------------

pont_vivant() { processus_vivant "$DOSSIER/pont-hote.pid" "pont_hote.py $ID"; }

# projet_de <texte de demande.json> : la valeur de "projet" (une seule clé, motif strict), sinon rien.
projet_de() {
  local texte="$1" reste
  reste="${texte//\"projet\"/}"
  [ $(( (${#texte} - ${#reste}) / 8 )) = 1 ] && [[ $texte =~ $MOTIF_PROJET ]] && printf '%s' "${BASH_REMATCH[1]}"
}

# premiere_ligne <fichier> : la première ligne d'un fichier ORDINAIRE (jamais un lien ni un tube), 200 octets au plus.
premiere_ligne() { [ -f "$1" ] && [ ! -L "$1" ] && head -c 200 -- "$1" 2>/dev/null | head -n 1; }

# emulation_liee <id> : 0 si ~/taches/<id> est une tâche d'ÉMULATION (demande.json : "type": "emulation") rattachée à CET
# agent (~/taches/<id>/agent, écrit sur l'hôte par celui qui l'a créée pour l'agent, porte $ID). Jamais une autre tâche.
emulation_liee() {
  local e="$1" d
  [[ $e =~ $MOTIF_ID ]] && [ "$e" != "$ID" ] || return 1
  d="$TACHES/$e"
  [ -d "$d" ] && [ ! -L "$d" ] || return 1
  [ "$(premiere_ligne "$d/agent")" = "$ID" ] || return 1
  [ -f "$d/demande.json" ] && [ ! -L "$d/demande.json" ] || return 1
  [[ $(head -c 65536 -- "$d/demande.json" 2>/dev/null) =~ $MOTIF_TYPE_EMULATION ]]
}

arreter_pont_et_emulation() {
  local pid="" n
  if pont_vivant; then                   # le pont est chef de sa session (setsid) : son groupe entier, sinon lui seul
    IFS= read -r pid < "$DOSSIER/pont-hote.pid"
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50; do
      pont_vivant || break
      sleep 0.1
    done
    if pont_vivant; then kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null; fi
  fi
  fin_emulation_liee
  return 0
}

# « fin » à l'émulation liée : l'argument 7, sinon $DOSSIER/emulation (écrit par le pont hôte, HORS de tout montage du
# conteneur ; pont/emulation, inscriptible par l'agent, n'est jamais lu). Rappelé APRÈS le contrôle du secret (finir) : un
# lancement d'émulation encore en cours au premier appel ne la laisse jamais tourner.
fin_emulation_liee() {
  local e="$EMU"
  [ -n "$e" ] || e=$(premiere_ligne "$DOSSIER/emulation")
  if emulation_liee "$e"; then printf 'fin\n' > "$TACHES/$e/arret" 2>/dev/null; fi
  return 0
}

# motifs_jeton : le jeton et ses trois alignements en base64 (seulement les caractères qui ne dépendent que du jeton), une
# ligne chacun, sur la sortie standard (jamais dans un fichier ni sur une ligne de commande : printf est interne à bash, base64
# lit son entrée standard). 1 si le fichier du jeton n'est pas UNE ligne de 20 à 400 caractères [A-Za-z0-9._-].
motifs_jeton() {
  local t n k pre b64 debut fin
  [ -f "$JETON" ] && [ ! -L "$JETON" ] || return 1
  n=$(wc -l < "$JETON" 2>/dev/null) || return 1
  n="${n//[!0-9]/}"
  [ -n "$n" ] && [ "$n" -le 1 ] || return 1
  t=$(head -c 1024 -- "$JETON" 2>/dev/null) || return 1
  [ "${#t}" -ge 20 ] && [ "${#t}" -le 400 ] && [[ $t =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  printf '%s\n' "$t"
  for k in 0 1 2; do
    case $k in 0) pre=""; debut=0 ;; 1) pre="x"; debut=2 ;; 2) pre="xx"; debut=3 ;; esac
    b64=$(printf '%s%s' "$pre" "$t" | base64 -w 0 2>/dev/null) || return 1
    fin=$(( (k + ${#t}) / 3 * 4 ))
    [ "$fin" -gt "$debut" ] || return 1
    printf '%s\n' "${b64:debut:fin-debut}"
  done
}

vider_sortie() {   # rien de sortie/ ne doit plus pouvoir être rapatrié (liens jamais suivis : rm et find ne les suivent pas)
  chmod -R u+rwX -- "$DOSSIER/sortie" 2>/dev/null
  find "$DOSSIER/sortie" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null
  return 0
}

# controle_secret : 0 propre ; 1 jeton trouvé ; 2 contrôle impossible (jeton illisible, grep en échec, conteneur de contrôle
# en échec ou trop long). Le jeton n'est qu'un FICHIER de motifs pour grep -F : sa valeur n'est jamais lue ni affichée ici.
controle_secret() {
  local g ps motifs err="$DOSSIER/.controle.$$.err"
  motifs=$(motifs_jeton) || return 2
  find "$DOSSIER/sortie" -mindepth 1 ! -type f ! -type d -exec rm -f -- {} + 2>/dev/null   # liens, tubes, sockets : retirés
  chmod -R u+rwX -- "$DOSSIER/sortie" 2>/dev/null                  # un fichier rendu illisible par l'agent est lu quand même
  timeout 600 grep -rqsF -D skip -f <(printf '%s\n' "$motifs") -- "$DOSSIER/sortie"; g=$?
  [ "$g" = 0 ] && return 1
  [ "$g" = 1 ] || return 2
  # TOUJOURS (même sans travail/projet : l'agent a pu l'effacer et déposer un paquet) : le texte des commits et des objets du
  # paquet, produit dans un conteneur de contrôle SANS jeton ni réseau (jamais par un git de l'hôte : la configuration du dépôt
  # de l'agent pourrait y lancer n'importe quoi). Un paquet invérifiable y donne un code non nul : contrôle impossible.
  CONTROLE=(run --rm --pull never --name "controle-$ID" --label "$GENRE" --network none --user "$UTILISATEUR" --read-only
    --tmpfs /tmp:size=1g --cap-drop ALL --security-opt no-new-privileges --pids-limit 512
    --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS" -e HOME=/tmp
    -v "$DOSSIER/entree:/entree:ro" -v "$DOSSIER/travail:/travail:ro" -v "$DOSSIER/sortie:/sortie:ro"
    "$IMAGE" entree-agent --verifier)
  dk "$DELAI_CONTROLE_S" "${CONTROLE[@]}" 2>"$err" | timeout "$DELAI_CONTROLE_S" grep -qF -f <(printf '%s\n' "$motifs")
  ps=("${PIPESTATUS[@]}")
  dk 30 rm -f "controle-$ID" >/dev/null 2>&1             # déjà retiré (--rm) d'ordinaire ; jamais un conteneur laissé
  # controle.log : 64 Ko au plus, sans aucune ligne qui porte le jeton ou l'un de ses alignements base64
  # (lignes entières filtrées d'abord, puis tronquées : jamais un morceau de jeton coupé en fin de journal)
  grep -avF -f <(printf '%s\n' "$motifs") -- "$err" 2>/dev/null | head -c "$CONTROLE_LOG_MAX" >> "$DOSSIER/controle.log"
  rm -f -- "$err"
  [ "${ps[1]}" = 0 ] && return 1
  [ "${ps[1]}" = 1 ] && [ "${ps[0]}" = 0 ] && return 0
  return 2
}

# --- Veilleur (détaché) ----------------------------------------------------

veilleur() {
  { : >&8; } 2>/dev/null || exit 2                  # sans la place héritée de l'enveloppe, jamais de veilleur
  printf '%s\n' "$$" > "$DOSSIER/veilleur.pid"
  local debut_iso debut_s maintenant pannes=0 etat_conteneur motif ko prochaine pause libre dernier_du
  debut_iso=$(debut_ecrit); [ -n "$debut_iso" ] || debut_iso=$(maintenant_iso)
  debut_s=$(date +%s)
  dernier_du=$debut_s
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
    fin_emulation_liee                     # de nouveau, après le contrôle (jusqu'à 15 min) : jamais d'émulation orpheline
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
        # "echeance": true : l'entrée a tenu sa propre échéance (duree_s - 120 s) et conclu ; une valeur forgée ne peut que
        # faire passer une fin normale pour une limite.
        if [[ $(head -c 4096 -- "$DOSSIER/sortie/fin.json" 2>/dev/null) =~ $MOTIF_ECHEANCE ]]; then
          finir terminee limite "Durée maximale atteinte : l'agent a été arrêté à son échéance et a conclu (sortie/fin.json)."
        fi
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
    ko=$(du -sk --apparent-size -- "$DOSSIER/sortie" 2>/dev/null | cut -f1)
    if [[ $ko =~ ^[0-9]+$ ]] && [ "$ko" -gt "$LIMITE_SORTIE_KO" ]; then
      arreter_puis terminee limite "Limite atteinte : sortie trop volumineuse (${ko} Ko, maximum ${LIMITE_SORTIE_KO} Ko)"
    fi
    # Disque du serveur : plancher d'espace libre (df -Pk, colonne « Available »), à chaque sonde.
    libre=""; read -r _ _ _ libre _ <<< "$(df -Pk -- "$DOSSIER" 2>/dev/null | tail -n 1)"
    if [[ $libre =~ ^[0-9]+$ ]] && [ "$libre" -lt "$LIBRE_MIN_KO" ]; then
      arreter_puis terminee limite "Limite atteinte : espace disque du serveur insuffisant (${libre} Ko libres, minimum ${LIBRE_MIN_KO} Ko)"
    fi
    # travail/ + maison/ : plus coûteux à mesurer, toutes les DU_TRAVAIL_S secondes seulement.
    if [ $((maintenant - dernier_du)) -ge "$DU_TRAVAIL_S" ]; then
      dernier_du=$maintenant
      ko=$(du -sck --apparent-size -- "$DOSSIER/travail" "$DOSSIER/maison" 2>/dev/null | tail -n 1 | cut -f1)
      if [[ $ko =~ ^[0-9]+$ ]] && [ "$ko" -gt "$TRAVAIL_MAX_KO" ]; then
        arreter_puis terminee limite "Limite atteinte : travail et maison trop volumineux (${ko} Ko, maximum ${TRAVAIL_MAX_KO} Ko)"
      fi
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
# ptrace : claude tourne sous le même utilisateur que l'entrée de l'agent (PID 1 du conteneur) ; avec ptrace_scope 0, il
# pourrait la tracer et lui faire écrire n'importe quoi. 1 (Ubuntu par défaut) : seul un ancêtre trace, l'entrée est hors
# d'atteinte. 0 : refusé ; fichier absent ou illisible (Yama absent) : avertissement dans veilleur.log et sur stderr.
scope=""
if [ -f "$PTRACE_SCOPE" ]; then IFS= read -r scope < "$PTRACE_SCOPE" 2>/dev/null; fi
case "$scope" in
  0) fin_erreur "Refusé : kernel.yama.ptrace_scope vaut 0 sur ce serveur (un agent pourrait tracer l'entrée de son conteneur) : à régler à 1 (sudo sysctl -w kernel.yama.ptrace_scope=1, et dans /etc/sysctl.d/ pour le garder)." ;;
  [1-3]) ;;
  *) printf '%s\n' "lancer_agent : avertissement : kernel.yama.ptrace_scope inconnu ($PTRACE_SCOPE illisible) : 1 au moins est attendu." |
       tee -a "$DOSSIER/veilleur.log" >&2 ;;
esac

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
  # la tâche reprise est une tâche d'agent (entree/demande.json) du MÊME projet
  projet=$(projet_de "$demande")
  projet_source=""
  if [ -f "$SOURCE/entree/demande.json" ] && [ ! -L "$SOURCE/entree/demande.json" ]; then
    projet_source=$(projet_de "$(head -c 65536 -- "$SOURCE/entree/demande.json" 2>/dev/null)")
  fi
  [ -n "$projet" ] && [ "$projet" = "$projet_source" ] ||
    fin_erreur "Reprise refusée : la tâche $REPREND n'est pas une tâche d'agent du même projet."
fi

# Places : les PLACES_MAX verrous sont tous essayés. Un verrou tenu = un agent qui tourne ; la place prise est le premier
# verrou libre de rang <= places, et seulement si moins de <places> agents tournent (places abaissé pendant que des agents
# tiennent les places 3 et 4 : jamais dépassé). Un verrou libre essayé est relâché aussitôt (descripteur 9).
trap '' HUP                         # la fin de la session SSH ne doit jamais interrompre l'écriture de l'état
CRENEAU=""; tenues=0
for ((i = 1; i <= PLACES_MAX; i++)); do
  exec 9>> "$TACHES/.creneau-agent-$i" || { ecrire_etat echouee erreur "" "$(maintenant_iso)" "Place d'agent inaccessible."; exit 1; }
  if flock -n 9; then
    if [ -z "$CRENEAU" ] && [ "$i" -le "$PLACES" ]; then CRENEAU="$i"; exec 8>&9; else flock -u 9; fi
  else
    tenues=$((tenues + 1))
  fi
  exec 9>&-
done
if [ -z "$CRENEAU" ] || [ "$tenues" -ge "$PLACES" ]; then
  occupe "Toutes les places d'agent du serveur sont prises ($PLACES) : relancez plus tard."
fi
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
    setsid nohup python3 -I "$ICI/pont_hote.py" "$ID" "$DUREE" </dev/null >> "$DOSSIER/pont-hote.out" 2>&1 8>&- &
  else
    nohup python3 -I "$ICI/pont_hote.py" "$ID" "$DUREE" </dev/null >> "$DOSSIER/pont-hote.out" 2>&1 8>&- &
  fi
  printf '%s\n' "$!" > "$DOSSIER/pont-hote.pid"
  disown 2>/dev/null
fi

# -v (et non --mount, voulu par le plan) : chaque source existe déjà (créée ci-dessus, jeton vérifié), jamais créée par root.
COMMANDE=(run --pull never -d --rm --name "tache-$ID" --label "$GENRE" --user "$UTILISATEUR" --read-only --tmpfs /tmp:size=1g
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 512
  --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS" --network "$RESEAU" -e HOME=/maison
  -e "AGENT_DUREE_S=$DUREE"
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
