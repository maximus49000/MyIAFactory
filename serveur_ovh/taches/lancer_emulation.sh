#!/usr/bin/env bash
# Enveloppe HÔTE d'une tâche d'émulation : exécutée sur le serveur (par SSH), elle prend le créneau, démarre le conteneur
# `myiafactory/emulateur` puis rend la main ; un veilleur DÉTACHÉ (setsid + nohup, survit à la fin de la session SSH) tient le
# créneau, applique les limites et écrit l'état final. Un appelant mort ne laisse donc ni conteneur ni créneau.
# Usage : lancer_emulation.sh <id> <mode> [duree_s [inactivite_s [memoire_mo [cpus]]]]
#   id : t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; mode : scenario | pilote ; valeurs par défaut : 1200 s, 300 s, 4096 Mo, 2 processeurs.
#   Chaque valeur est validée par un motif strict AVANT tout usage (nombres entiers sans zéro initial : duree_s et inactivite_s
#   1..86400, memoire_mo 256..65536, cpus 1..64) ; rien n'en est jamais interprété par un shell : les commandes sont des tableaux.
# Sortie standard : UNE ligne JSON, l'état écrit dans ~/taches/<id>/etat.json.
# Codes : 0 conteneur démarré (état en_cours) ; 1 démarrage impossible (état echouee) ; 2 argument refusé (rien créé) ;
#   3 tâche déjà en cours (rien modifié) ; 75 créneau occupé (état en_attente, à relancer plus tard).
# Dossier de la tâche ~/taches/<id>/ : entree/ (monté en lecture seule, l'APK y est déposé avant), sortie/ (monté en écriture :
#   pont.log, captures/, plantage.txt, entree-tache.log), etat.json, arret (créé par le lanceur : demande d'arrêt),
#   veilleur.pid, veilleur.log, docker-run.log. Créneau : verrou flock sur ~/taches/.creneau-emulation (descripteur 8, hérité
#   par le veilleur).
# etat.json : {"id","etat","statut","debut","fin","raison"}, écrit par un fichier temporaire puis mv (jamais à moitié écrit).
#   etat : en_attente | en_cours | terminee | arretee | echouee ; statut (à la fin) : ok | plantage | limite | erreur.
#   Fin par le fichier arret -> arretee, ok (plantage si sortie/plantage.txt) ; échéance duree_s ou inactivité du pilote
#   (mtime de sortie/pont.log) -> terminee, limite (plantage prime) ; conteneur disparu seul -> terminee, plantage si
#   plantage.txt existe, sinon echouee, erreur ; docker en échec -> echouee, erreur.
# Réservées aux tests : ENVELOPPE_SONDE_S (période de surveillance, 2 s par défaut). Aucun identifiant n'est monté ni transmis ;
# le conteneur reçoit seulement les réglages posés ci-dessous (-e NOM=valeur, jamais l'environnement de l'appelant).
set -u
export LC_ALL=C
exec </dev/null

MOTIF_ID='^t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$'
MOTIF_DUREE='^[1-9][0-9]{0,4}$'          # 1..99999, borné à 86400 plus bas
MOTIF_MEMOIRE='^[1-9][0-9]{2,4}$'        # 100..99999, borné à 256..65536 plus bas
MOTIF_CPUS='^[1-9][0-9]?$'
MOTIF_SONDE='^[0-9]{1,2}(\.[0-9]{1,3})?$'
IMAGE="myiafactory/emulateur"

refuser() { printf '%s\n' "lancer_emulation : $1" >&2; exit 2; }

VEILLEUR=0
if [ "${1:-}" = --veilleur ]; then VEILLEUR=1; shift; fi
[ $# -ge 2 ] && [ $# -le 6 ] || refuser "usage : <id> <scenario|pilote> [duree_s [inactivite_s [memoire_mo [cpus]]]]"
ID="$1"; MODE="$2"; DUREE="${3-1200}"; INACTIVITE="${4-300}"; MEMOIRE="${5-4096}"; CPUS="${6-2}"
[[ $ID =~ $MOTIF_ID ]] || refuser "identifiant refusé."
[ "$MODE" = scenario ] || [ "$MODE" = pilote ] || refuser "mode refusé (scenario ou pilote)."
[[ $DUREE =~ $MOTIF_DUREE ]] && [ "$DUREE" -le 86400 ] || refuser "duree_s refusée (1 à 86400, sans zéro initial)."
[[ $INACTIVITE =~ $MOTIF_DUREE ]] && [ "$INACTIVITE" -le 86400 ] || refuser "inactivite_s refusée (1 à 86400, sans zéro initial)."
[[ $MEMOIRE =~ $MOTIF_MEMOIRE ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser "memoire_mo refusée (256 à 65536)."
[[ $CPUS =~ $MOTIF_CPUS ]] && [ "$CPUS" -le 64 ] || refuser "cpus refusés (1 à 64)."
[ -n "${HOME:-}" ] || refuser "HOME absent."
SONDE="${ENVELOPPE_SONDE_S:-2}"
[[ $SONDE =~ $MOTIF_SONDE ]] || SONDE=2

TACHES="$HOME/taches"
DOSSIER="$TACHES/$ID"
SDK="$HOME/android-sdk"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

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
dk() { local delai="$1"; shift; timeout "$delai" sudo docker "$@" 8>&- </dev/null; }

conteneur_vivant() {   # 0 vivant, 1 absent, 2 docker ne répond pas
  local sortie
  sortie=$(dk 20 ps -q --no-trunc --filter "name=^tache-${ID}\$" 2>/dev/null) || return 2
  [ -n "$sortie" ]
}

arreter_conteneur() {   # 0 si le conteneur n'existe plus
  local r
  dk 60 stop -t 10 "tache-$ID" >/dev/null 2>&1 || dk 30 kill "tache-$ID" >/dev/null 2>&1
  conteneur_vivant; r=$?
  if [ "$r" = 0 ]; then dk 30 rm -f "tache-$ID" >/dev/null 2>&1; conteneur_vivant; r=$?; fi
  [ "$r" = 1 ]
}

# --- Veilleur (détaché) ----------------------------------------------------

veilleur() {
  { : >&8; } 2>/dev/null || exit 2                  # sans le créneau hérité de l'enveloppe, jamais de veilleur
  printf '%s\n' "$$" > "$DOSSIER/veilleur.pid"
  local debut_iso debut_s maintenant derniere m pannes=0 etat_conteneur plantage=0
  debut_iso=$(debut_ecrit); [ -n "$debut_iso" ] || debut_iso=$(maintenant_iso)
  debut_s=$(date +%s)
  FINI=0
  conclure() {   # conclure <etat> <statut> <raison>
    FINI=1
    ecrire_etat "$1" "$2" "$debut_iso" "$(maintenant_iso)" "$3"
    liberer_creneau
    exit 0
  }
  trap 'if [ "$FINI" = 0 ]; then arreter_conteneur; conclure echouee erreur "Veilleur interrompu avant la fin de la tâche."; fi' EXIT
  trap 'exit 143' TERM INT HUP
  while :; do
    if [ -e "$DOSSIER/sortie/plantage.txt" ]; then plantage=1; else plantage=0; fi
    if [ -e "$DOSSIER/arret" ]; then
      arreter_conteneur || conclure echouee erreur "Arrêt demandé mais le conteneur tache-$ID ne s'arrête pas : à arrêter à la main (docker stop)."
      if [ "$plantage" = 1 ]; then conclure arretee plantage "Arrêt demandé (fichier arret) ; plantage relevé (plantage.txt)."; fi
      conclure arretee ok "Arrêt demandé (fichier arret)."
    fi
    conteneur_vivant; etat_conteneur=$?
    if [ "$etat_conteneur" = 1 ]; then
      if [ "$plantage" = 1 ]; then conclure terminee plantage "Le conteneur s'est arrêté ; plantage relevé (plantage.txt)."; fi
      conclure echouee erreur "Le conteneur s'est arrêté de lui-même avant la fin (voir sortie/entree-tache.log)."
    elif [ "$etat_conteneur" = 2 ]; then
      pannes=$((pannes + 1))
      [ "$pannes" -lt 30 ] || conclure echouee erreur "Docker ne répond plus : état du conteneur inconnu."
    else
      pannes=0
    fi
    maintenant=$(date +%s)
    if [ $((maintenant - debut_s)) -ge "$DUREE" ]; then
      arreter_conteneur || conclure echouee erreur "Durée maximale atteinte mais le conteneur tache-$ID ne s'arrête pas : à arrêter à la main (docker stop)."
      if [ "$plantage" = 1 ]; then conclure terminee plantage "Durée maximale atteinte (${DUREE} s) ; plantage relevé (plantage.txt)."; fi
      conclure terminee limite "Durée maximale atteinte (${DUREE} s)."
    fi
    if [ "$MODE" = pilote ]; then
      derniere=$debut_s
      m=$(stat -c %Y "$DOSSIER/sortie/pont.log" 2>/dev/null)
      if [[ $m =~ ^[0-9]+$ ]] && [ "$m" -gt "$derniere" ]; then derniere=$m; fi
      if [ $((maintenant - derniere)) -ge "$INACTIVITE" ]; then
        arreter_conteneur || conclure echouee erreur "Inactivité du pilote mais le conteneur tache-$ID ne s'arrête pas : à arrêter à la main (docker stop)."
        if [ "$plantage" = 1 ]; then conclure terminee plantage "Inactivité du pilote (${INACTIVITE} s) ; plantage relevé (plantage.txt)."; fi
        conclure terminee limite "Inactivité du pilote : aucun verbe depuis ${INACTIVITE} s."
      fi
    fi
    sleep "$SONDE"
  done
}

if [ "$VEILLEUR" = 1 ]; then veilleur; exit 0; fi

# --- Enveloppe (au premier plan, rend vite la main) ------------------------

fin_erreur() {   # fin_erreur <raison> : tâche échouée, créneau libéré
  ecrire_etat echouee erreur "$(debut_ecrit)" "$(maintenant_iso)" "$1"
  liberer_creneau
  montrer_etat
  exit 1
}

umask 077
mkdir -p -- "$DOSSIER/entree" "$DOSSIER/sortie" || refuser "dossier de la tâche non créable."
chmod 755 "$DOSSIER/entree"
chmod 777 "$DOSSIER/sortie"        # écrit par l'utilisateur 1000 du conteneur, quel que soit le propriétaire de l'hôte

if [ -f "$DOSSIER/etat.json" ] && grep -q '"etat": "en_cours"' "$DOSSIER/etat.json"; then
  montrer_etat
  exit 3
fi
rm -f "$DOSSIER/arret"

exec 8>> "$TACHES/.creneau-emulation" || { ecrire_etat echouee erreur "" "$(maintenant_iso)" "Créneau inaccessible."; exit 1; }
if ! flock -n 8; then
  ecrire_etat en_attente "" "" "" "Créneau d'émulation occupé : une autre tâche tourne, relancez plus tard."
  montrer_etat
  exit 75
fi

kvm_gid=$(getent group kvm 2>/dev/null | cut -d: -f3)
[[ $kvm_gid =~ ^[0-9]{1,10}$ ]] || fin_erreur "Groupe kvm introuvable sur ce serveur : l'émulateur ne peut pas être accéléré."

ecrire_etat en_cours "" "$(maintenant_iso)" "" "Conteneur en cours de démarrage."

COMMANDE=(run --rm -d --init --name "tache-$ID" --network none --device /dev/kvm
  --user 1000:1000 --group-add "$kvm_gid" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:size=512m,mode=1777 --tmpfs /avd:size=4g,mode=1777
  --memory "${MEMOIRE}m" --cpus "$CPUS"
  -e ANDROID_AVD_HOME=/avd -e HOME=/tmp -e PONT_SORTIE=/sortie -e PONT_AVD=emul
  -e PONT_EMULATEUR=/opt/android-sdk/emulator/emulator -e PONT_ADB=/opt/android-sdk/platform-tools/adb
  -e "TACHE_DUREE_S=$DUREE"
  -v "$SDK:/opt/android-sdk:ro" -v "$DOSSIER/entree:/entree:ro" -v "$DOSSIER/sortie:/sortie"
  "$IMAGE")
dk 120 "${COMMANDE[@]}" >/dev/null 2>"$DOSSIER/docker-run.log" || fin_erreur "Démarrage du conteneur impossible (docker run en échec : voir docker-run.log)."

# Veilleur détaché : il hérite du descripteur 8 (donc du créneau) et le libère à la fin, même si cette session SSH a disparu.
if command -v setsid >/dev/null 2>&1; then
  setsid nohup bash "$SELF" --veilleur "$ID" "$MODE" "$DUREE" "$INACTIVITE" "$MEMOIRE" "$CPUS" </dev/null >> "$DOSSIER/veilleur.log" 2>&1 &
else
  nohup bash "$SELF" --veilleur "$ID" "$MODE" "$DUREE" "$INACTIVITE" "$MEMOIRE" "$CPUS" </dev/null >> "$DOSSIER/veilleur.log" 2>&1 &
fi
disown 2>/dev/null
montrer_etat
exit 0
