# Fonctions communes des enveloppes HÔTE des tâches du serveur (lancer_emulation.sh, lancer_agent.sh) : SOURCÉ, jamais exécuté.
# Extraites telles quelles de lancer_emulation.sh (aucun changement de comportement) : écriture de etat.json (temporaire puis
# mv), motifs des arguments, docker borné sans le verrou du créneau, état du conteneur (docker inspect puis /proc), arrêt
# confirmé par une réponse nette, veilleur détaché (setsid + nohup) et processus vivants reconnus par leur ligne de commande.
# Variables attendues de l'enveloppe qui source ce fichier : ID, DOSSIER, SELF (son propre chemin) ; descripteur 8 = créneau.

MOTIF_ID='^t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$'
MOTIF_DUREE='^[1-9][0-9]{0,4}$'          # 1..99999, borné à 86400 plus bas
MOTIF_MEMOIRE='^[1-9][0-9]{2,4}$'        # 100..99999, borné à 256..65536 plus bas
MOTIF_CPUS='^[1-9][0-9]?$'
MOTIF_SONDE='^[0-9]{1,2}(\.[0-9]{1,3})?$'

# --- Utilitaires -----------------------------------------------------------

maintenant_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echapper_json() {
  local s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/ }"; s="${s//$'\r'/ }"; s="${s//$'\t'/ }"
  printf '%s' "$s"
}

# ecrire_etat <etat> <statut|""> <debut|""> <fin|""> <raison> : fichier temporaire puis mv, un seul fichier etat.json.
ecrire_etat() {
  local tmp="$DOSSIER/etat.json.$$.tmp" s=null d=null f=null
  [ -n "$2" ] && s="\"$2\""
  [ -n "$3" ] && d="\"$3\""
  [ -n "$4" ] && f="\"$4\""
  printf '{"id": "%s", "etat": "%s", "statut": %s, "debut": %s, "fin": %s, "raison": "%s"}\n' \
    "$ID" "$1" "$s" "$d" "$f" "$(echapper_json "$5")" > "$tmp" && mv -f "$tmp" "$DOSSIER/etat.json" || rm -f "$tmp"
}

montrer_etat() { [ -f "$DOSSIER/etat.json" ] && tr -d '\n' < "$DOSSIER/etat.json" && printf '\n'; }

debut_ecrit() {   # date de début lue dans etat.json (écrit par nous)
  sed -n 's/.*"debut": "\([0-9TZ:-]*\)".*/\1/p' "$DOSSIER/etat.json" 2>/dev/null | head -n 1
}

liberer_creneau() { flock -u 8 2>/dev/null; exec 8>&-; }

# docker sans hériter du verrou (8>&-) ni de l'entrée, et borné : un docker figé ne fige jamais l'enveloppe.
dk() { local delai="$1"; shift; timeout "$delai" sudo -n docker "$@" 8>&- </dev/null; }

# État du conteneur : `docker inspect` (par sudo : une ligne d'auth.log) seulement quand il le faut. Entre deux, le processus
# principal du conteneur (PID relevé par inspect) est suivi dans /proc, sans sudo : même PID ET même date de démarrage
# (champ 22 de /proc/<pid>/stat), jamais un PID recyclé.
PID_CONTENEUR=""; DEBUT_CONTENEUR=""
debut_processus() {   # debut_processus <pid> : date de démarrage du processus (ticks depuis l'amorçage)
  local s
  s=$(cat -- "/proc/$1/stat" 2>/dev/null) || return 1
  s="${s##*) }"
  set -- $s
  [[ ${20:-} =~ ^[0-9]+$ ]] || return 1
  printf '%s' "${20}"
}

# Seule la SORTIE STANDARD de docker inspect est analysée : un avertissement sur la sortie d'erreur (« sudo: unable to
# resolve host », avertissement du client docker) avec le code 0 ne doit jamais faire passer un conteneur vivant pour
# disparu. La sortie d'erreur va dans un fichier privé du dossier de la tâche (retiré aussitôt) et n'est lue que pour
# « No such » (conteneur absent). Une réponse qui n'a pas exactement la forme « true|false <pid> » = on ne sait pas (2).
etat_docker() {   # 0 vivant, 1 absent ou arrêté, 2 docker ne répond pas ou réponse illisible
  local sortie r erreurs fichier="$DOSSIER/.inspect.$$.err" p
  sortie=$(dk 20 inspect -f '{{.State.Running}} {{.State.Pid}}' "tache-$ID" 2>"$fichier"); r=$?
  erreurs=$(head -c 4096 -- "$fichier" 2>/dev/null)
  rm -f -- "$fichier"
  PID_CONTENEUR=""; DEBUT_CONTENEUR=""
  if [ "$r" = 0 ]; then
    [[ $sortie =~ ^(true|false)\ ([0-9]+)$ ]] || return 2
    [ "${BASH_REMATCH[1]}" = true ] || return 1
    p="${BASH_REMATCH[2]}"
    if [[ $p =~ ^[1-9][0-9]{0,9}$ ]] && DEBUT_CONTENEUR=$(debut_processus "$p"); then PID_CONTENEUR="$p"; fi
    return 0
  fi
  # « Error: No such object » ou, selon la version de docker, « error: no such object: tache-<id> » (minuscule, constaté
  # sur le serveur) : comparaison sans casse. C'est « parti », constaté aussitôt (jamais compté comme une panne).
  case "${erreurs,,}" in *"no such object"*|*"no such container"*|*"not found"*) return 1 ;; esac
  return 2
}

etat_docker_sur() {   # comme etat_docker, avec un second essai si la première réponse est illisible ou absente (2)
  local r
  etat_docker; r=$?
  if [ "$r" = 2 ]; then sleep 1; etat_docker; r=$?; fi
  return "$r"
}

conteneur_vivant() {   # 0 vivant, 1 absent, 2 docker ne répond pas
  local d
  if [ -n "$PID_CONTENEUR" ] && d=$(debut_processus "$PID_CONTENEUR") && [ "$d" = "$DEBUT_CONTENEUR" ]; then return 0; fi
  etat_docker
}

# Délai laissé au conteneur entre SIGTERM et SIGKILL (docker stop -t) : 10 s (émulation) ; l'enveloppe d'agent le porte à 60 s
# APRÈS avoir sourcé ce fichier (l'entrée de l'agent conclut : commit des restes, paquet, fin.json). Jamais lu de l'environnement.
DELAI_ARRET=10
arreter_conteneur() {   # 0 si le conteneur n'existe plus : constaté par une réponse NETTE de docker (jamais par /proc)
  local r
  dk $((DELAI_ARRET + 50)) stop -t "$DELAI_ARRET" "tache-$ID" >/dev/null 2>&1 || dk 30 kill "tache-$ID" >/dev/null 2>&1
  etat_docker_sur; r=$?
  if [ "$r" != 1 ]; then dk 30 rm -f "tache-$ID" >/dev/null 2>&1; etat_docker_sur; r=$?; fi
  [ "$r" = 1 ]
}

mtime() { local m; m=$(stat -c %Y "$1" 2>/dev/null); if [[ $m =~ ^[0-9]+$ ]]; then printf '%s' "$m"; else printf 0; fi; }

# --- Enveloppe : états finaux, créneau, processus vivants ------------------

fin_erreur() {   # fin_erreur <raison> : tâche échouée, créneau libéré (un état final déjà écrit par arreter est gardé)
  if grep -qE '"etat": "(terminee|arretee|echouee)"' "$DOSSIER/etat.json" 2>/dev/null; then
    liberer_creneau; montrer_etat; exit 4
  fi
  ecrire_etat echouee erreur "$(debut_ecrit)" "$(maintenant_iso)" "$1"
  liberer_creneau
  montrer_etat
  exit 1
}

# Un veilleur est vivant si son PID existe ET si /proc/<pid>/cmdline porte le marqueur --veilleur et l'identifiant (jamais un
# PID recyclé par un autre processus).
processus_vivant() {   # processus_vivant <fichier du pid> <motif>... : le PID existe ET sa ligne de commande porte tous les motifs
  local fichier="$1" pid="" cmd m
  shift
  [ -f "$fichier" ] && IFS= read -r pid < "$fichier"
  [[ $pid =~ ^[0-9]{1,10}$ ]] || return 1
  [ -r "/proc/$pid/cmdline" ] || return 1
  cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  for m in "$@"; do [[ $cmd == *"$m"* ]] || return 1; done
  return 0
}

# Un `arreter` du lanceur a pu passer pendant l'attente du créneau : un état FINAL est alors honoré, jamais réécrit (ni
# en_attente, ni en_cours). Relu sous le créneau, juste avant chaque écriture d'état (voir lancer_emulation.sh).
honorer_final() {
  if grep -qE '"etat": "(terminee|arretee|echouee)"' "$DOSSIER/etat.json" 2>/dev/null; then
    liberer_creneau
    montrer_etat
    exit 4
  fi
}
occupe() {   # occupe <raison> : ne remplace jamais un état en_cours ni un état final
  honorer_final
  grep -q '"etat": "en_cours"' "$DOSSIER/etat.json" 2>/dev/null || ecrire_etat en_attente "" "" "" "$1"
  liberer_creneau
  montrer_etat
  exit 75
}

# detacher_veilleur <arguments du veilleur>... : veilleur détaché (setsid + nohup) ; il hérite du descripteur 8 (donc du
# créneau) et le libère à la fin, même si la session SSH a disparu. Rend la main seulement quand veilleur.pid existe : après,
# « en_cours sans veilleur vivant » ne peut plus être qu'un veilleur mort.
detacher_veilleur() {
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup bash "$SELF" --veilleur "$@" </dev/null >> "$DOSSIER/veilleur.log" 2>&1 &
  else
    nohup bash "$SELF" --veilleur "$@" </dev/null >> "$DOSSIER/veilleur.log" 2>&1 &
  fi
  disown 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    [ -s "$DOSSIER/veilleur.pid" ] && break
    sleep 0.1
  done
}
