#!/bin/bash
# Commandes uniques d'un agent serveur d'un projet Flutter : CE fichier, monté en lecture seule par lancer_agent.sh sous
# trois noms dans /opt/outils (dans le PATH du conteneur) ; le nom d'appel choisit l'étape, valeurs figées :
#   analyser-flutter          flutter analyze                 (aucun argument)
#   tester-flutter            flutter test                    (aucun argument)
#   construire-apk [release|debug]   flutter build apk --release (défaut) ou --debug
# Au serveur personne n'approuve une commande : la fiche n'ouvre que des commandes SIMPLES (Bash(analyser-flutter:*)…) ;
# chaque commande fait donc l'étape complète : elle se place d'elle-même dans le dossier Flutter du projet (nom relatif
# écrit par l'enveloppe dans /opt/outils/dossier-flutter, motif strict, jamais « .. » ni chemin absolu, sous
# /travail/projet sans suivre de lien qui en sortirait), lance `flutter pub get` si les paquets ne sont pas à jour, puis
# la commande figée. Sortie standard et erreurs mêlées, bornées aux 200 000 derniers octets.
# Codes : celui de flutter ; 2 nom ou argument refusé (rien n'est lancé) ; 3 dossier Flutter inconnu ou refusé.
# Réservées aux tests : OUTIL_FLUTTER_RACINE (/travail/projet), OUTIL_FLUTTER_CONF (/opt/outils/dossier-flutter).
set -u
export LC_ALL=C
RACINE="${OUTIL_FLUTTER_RACINE:-/travail/projet}"
CONF="${OUTIL_FLUTTER_CONF:-/opt/outils/dossier-flutter}"
SORTIE_MAX=200000

refuser() { printf '%s\n' "$2" >&2; exit "$1"; }

case "${0##*/}" in
  analyser-flutter)
    [ $# -eq 0 ] || refuser 2 "analyser-flutter : aucun argument admis."
    COMMANDE=(analyze) ;;
  tester-flutter)
    [ $# -eq 0 ] || refuser 2 "tester-flutter : aucun argument admis."
    COMMANDE=(test) ;;
  construire-apk)
    [ $# -le 1 ] || refuser 2 "construire-apk : un seul argument, release ou debug."
    case "${1-release}" in
      release) COMMANDE=(build apk --release) ;;
      debug) COMMANDE=(build apk --debug) ;;
      *) refuser 2 "construire-apk : release ou debug seulement." ;;
    esac ;;
  *) refuser 2 "Commande inconnue : analyser-flutter, tester-flutter ou construire-apk." ;;
esac

dossier=""
if [ -f "$CONF" ]; then IFS= read -r dossier < "$CONF"; fi
[[ $dossier =~ ^(\.|[A-Za-z0-9_][A-Za-z0-9_.-]{0,99})$ ]] && [ "$dossier" != .. ] ||
  refuser 3 "Dossier Flutter du projet inconnu ou refusé (transmis par le poste)."
racine=$(cd -P -- "$RACINE" 2>/dev/null && pwd -P) || refuser 3 "Dépôt du projet introuvable ($RACINE)."
cd -P -- "$racine/$dossier" 2>/dev/null || refuser 3 "Dossier Flutter absent : $dossier."
ici=$(pwd -P)
case "$ici/" in "$racine/"*) ;; *) refuser 3 "Dossier Flutter hors du dépôt : refusé." ;; esac
[ -f pubspec.yaml ] || refuser 3 "Pas de pubspec.yaml dans $dossier."

lancer() {
  {
    if [ ! -f .dart_tool/package_config.json ] || [ pubspec.yaml -nt .dart_tool/package_config.json ] ||
       { [ -f pubspec.lock ] && [ pubspec.lock -nt .dart_tool/package_config.json ]; }; then
      flutter pub get || return $?
    fi
    flutter "${COMMANDE[@]}"
  }
}
lancer 2>&1 | tail -c "$SORTIE_MAX"
exit "${PIPESTATUS[0]}"
