#!/bin/bash
# Commandes uniques d'un agent serveur d'un projet Flutter : CE fichier, monté en lecture seule par lancer_agent.sh sous
# trois noms dans /opt/outils (dans le PATH du conteneur) ; le nom d'appel choisit l'étape, valeurs figées :
#   analyser-flutter          flutter analyze                 (aucun argument)
#   tester-flutter            flutter test                    (aucun argument)
#   construire-apk [release|debug] [variante]   flutter build apk --release (défaut) ou --debug, avec --build-number (temps en
#   minutes) ; une variante (flavor Android : minuscule puis lettres/chiffres, 30 au plus) ajoute --flavor <variante>
# Au serveur personne n'approuve une commande : la fiche n'ouvre que des commandes SIMPLES (Bash(analyser-flutter:*)…) ;
# chaque commande fait donc l'étape complète : elle se place d'elle-même dans le dossier Flutter du projet (nom relatif
# écrit par l'enveloppe dans /opt/outils/dossier-flutter, motif strict, jamais « .. » ni chemin absolu, sous
# /travail/projet sans suivre de lien qui en sortirait), lance `flutter pub get` si les paquets ne sont pas à jour, puis
# la commande figée. Sortie standard et erreurs mêlées, bornées aux 200 000 derniers octets.
# « Release signé » (tâche 15d) : quand le projet signe au poste (/opt/outils/signature vaut « poste_signe », écrit par
# l'enveloppe d'après le réglage « Signature des APK »), `construire-apk release` construit la release NON signée : un
# script d'init Gradle (posé le temps de la construction dans $GRADLE_USER_HOME/init.d, retiré ensuite) retire la
# signature de la release (androidComponents.finalizeDsl, signingConfig = null), puis l'APK est rangé sous
# build/app/outputs/flutter-apk/app-release-unsigned.apk (une sortie que le rapatriement accepte) ; aucune clé n'est lue.
# Fichier absent : « aucune » (rien ne change) ; toute autre valeur que aucune|debug_serveur|poste_signe : refus 3.
# Codes : celui de flutter ; 2 nom ou argument refusé (rien n'est lancé) ; 3 dossier Flutter ou choix de signature refusé ;
# 4 variables de construction refusées (fichier mal formé) ; 5 l'adresse du service demandée n'est pas dans l'APK construit.
# Variables de construction (`construire-apk` seul) : si /entree/construction.env existe (déposé par le poste, 0600, jamais
# dans le dépôt du projet), chaque ligne « <variante|*> <NOM> <valeur> » dont la variante est celle de la construction (ou
# « * ») ajoute `--dart-define=NOM=valeur` : l'adresse du service (et son jeton) intégrés à l'APK Client. Noms et valeurs
# sont validés de nouveau ici (motifs stricts, jamais d'espace ni de guillemet), les arguments sont construits par ce script et
# jamais par l'agent ; la sortie est masquée (aucune valeur n'y apparaît). Après la construction, si une variable
# SERVEUR_URL a été passée, le script vérifie que l'adresse est bien DANS l'APK construit (libapp.so) : sinon code 5.
# Réservées aux tests : OUTIL_FLUTTER_RACINE (/travail/projet), OUTIL_FLUTTER_CONF (/opt/outils/dossier-flutter),
# OUTIL_FLUTTER_SIGNATURE (/opt/outils/signature), OUTIL_FLUTTER_CONSTRUCTION (/entree/construction.env).
set -u
export LC_ALL=C
RACINE="${OUTIL_FLUTTER_RACINE:-/travail/projet}"
CONF="${OUTIL_FLUTTER_CONF:-/opt/outils/dossier-flutter}"
CONF_SIGNATURE="${OUTIL_FLUTTER_SIGNATURE:-/opt/outils/signature}"
CONF_CONSTRUCTION="${OUTIL_FLUTTER_CONSTRUCTION:-/entree/construction.env}"
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
    [ $# -le 2 ] || refuser 2 "construire-apk : release ou debug, puis au plus une variante."
    # Une variante (flavor) Android : un APK par variante (app-<variante>-release.apk). Sans cela, un projet à deux variantes
    # (Maître/Client) ne pouvait construire que la variante par défaut au serveur (essai réel FM_Stats, 2026-11-25).
    VARIANTE=""
    if [ $# -eq 2 ]; then
      [[ $2 =~ ^[a-z][A-Za-z0-9]{0,29}$ ]] || refuser 2 "construire-apk : variante refusée (minuscule puis lettres ou chiffres, 30 au plus)."
      case "$2" in release|debug|profile) refuser 2 "construire-apk : variante refusée (nom de mode réservé)." ;; esac
      VARIANTE="$2"
    fi
    # Chaque APK porte un numéro de version (versionCode) qui augmente : le temps en minutes depuis 1970 (tient dans les
    # 2,1 milliards d'un versionCode jusqu'en 2038). Sans lui tous les APK portaient 1 et rien ne distinguait le dernier
    # du précédent (essai réel FM_Stats, 2026-11-25). Valeur imposée possible pour les tests : OUTIL_FLUTTER_NUMERO.
    NUMERO="${OUTIL_FLUTTER_NUMERO:-$(( $(date +%s) / 60 ))}"
    [[ $NUMERO =~ ^[1-9][0-9]{0,9}$ ]] && [ "$NUMERO" -le 2100000000 ] ||
      refuser 2 "construire-apk : numéro de version refusé (entier de 1 à 2100000000)."
    case "${1-release}" in
      release) COMMANDE=(build apk --release "--build-number=$NUMERO"); RELEASE=1 ;;
      debug) COMMANDE=(build apk --debug "--build-number=$NUMERO") ;;
      *) refuser 2 "construire-apk : release ou debug seulement." ;;
    esac
    [ -z "$VARIANTE" ] || COMMANDE+=("--flavor=$VARIANTE") ;;
  *) refuser 2 "Commande inconnue : analyser-flutter, tester-flutter ou construire-apk." ;;
esac

# Variables de construction : seulement pour `construire-apk`. Une ligne : « <variante|*> <NOM> <valeur> ».
# Valeur : lettres, chiffres et . _ ~ : / ? # @ & + = % - seulement (jamais d'espace, de guillemet, d'antislash ni de $).
DEFINES=()          # les arguments --dart-define=NOM=valeur (construits ici, jamais par l'agent)
VALEURS=()          # les valeurs à masquer dans la sortie
URL_ATTENDUE=""     # la valeur de SERVEUR_URL, vérifiée dans l'APK construit
if [ "${0##*/}" = construire-apk ] && [ -e "$CONF_CONSTRUCTION" ]; then
  [ -f "$CONF_CONSTRUCTION" ] && [ ! -L "$CONF_CONSTRUCTION" ] || refuser 4 "Variables de construction refusées : fichier non ordinaire."
  MOTIF_VARIABLE='^(\*|[a-z][A-Za-z0-9]{0,29}) ([A-Z][A-Z0-9_]{0,63}) ([A-Za-z0-9._~:/?#@&+=%-]{1,512})$'
  nb=0
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    [ -n "$ligne" ] || continue
    nb=$((nb + 1)); [ "$nb" -le 16 ] || refuser 4 "Variables de construction refusées : 16 au plus."
    [[ $ligne =~ $MOTIF_VARIABLE ]] || refuser 4 "Variables de construction refusées : la ligne $nb est mal formée."
    var="${BASH_REMATCH[1]}"; nom="${BASH_REMATCH[2]}"; valeur="${BASH_REMATCH[3]}"
    if [ "$var" = "*" ] || [ "$var" = "${VARIANTE:-}" ]; then
      DEFINES+=("--dart-define=$nom=$valeur"); VALEURS+=("$valeur")
      [ "$nom" != SERVEUR_URL ] || URL_ATTENDUE="$valeur"
    fi
  done < "$CONF_CONSTRUCTION"
  [ "${#DEFINES[@]}" -eq 0 ] || COMMANDE+=("${DEFINES[@]}")      # (un tableau vide fait échouer set -u sous bash < 4.4)
fi

signature=aucune
if [ -f "$CONF_SIGNATURE" ]; then IFS= read -r signature < "$CONF_SIGNATURE" || true; fi
case "$signature" in
  aucune|debug_serveur|poste_signe) ;;
  *) refuser 3 "Choix de signature refusé (transmis par le poste) : aucune, debug_serveur ou poste_signe." ;;
esac
NON_SIGNEE=""
[ "$signature" = poste_signe ] && [ "${RELEASE:-}" = 1 ] && NON_SIGNEE=1

dossier=""
if [ -f "$CONF" ]; then IFS= read -r dossier < "$CONF"; fi
[[ $dossier =~ ^(\.|[A-Za-z0-9_][A-Za-z0-9_.-]{0,99})$ ]] && [ "$dossier" != .. ] ||
  refuser 3 "Dossier Flutter du projet inconnu ou refusé (transmis par le poste)."
racine=$(cd -P -- "$RACINE" 2>/dev/null && pwd -P) || refuser 3 "Dépôt du projet introuvable ($RACINE)."
cd -P -- "$racine/$dossier" 2>/dev/null || refuser 3 "Dossier Flutter absent : $dossier."
ici=$(pwd -P)
case "$ici/" in "$racine/"*) ;; *) refuser 3 "Dossier Flutter hors du dépôt : refusé." ;; esac
[ -f pubspec.yaml ] || refuser 3 "Pas de pubspec.yaml dans $dossier."

# Le script d'init Gradle de la release non signée : texte figé, aucune valeur du projet ni du poste.
INIT_GRADLE='// MyIAFactory (tâche 15d) : la release se construit NON signée ; la signature se fait au poste.
allprojects { p ->
    p.plugins.withId("com.android.application") {
        def composants = p.extensions.findByName("androidComponents")
        if (composants != null) {
            composants.finalizeDsl { ext ->
                def release = ext.buildTypes.findByName("release")
                if (release != null) { release.signingConfig = null }
            }
        }
    }
}'
init=""
if [ -n "$NON_SIGNEE" ]; then
  init="${GRADLE_USER_HOME:-$HOME/.gradle}/init.d/myiafactory-release-non-signee.gradle"
  trap 'rm -f -- "$init"' EXIT
fi

ranger_non_signee() {
  local sorties=build/app/outputs source="" nom="app-release" repertoire="release"
  if [ -n "${VARIANTE:-}" ]; then nom="app-$VARIANTE-release"; repertoire="$VARIANTE/release"; fi
  local non_signe="build/app/outputs/flutter-apk/$nom-unsigned.apk"
  if [ -f "$sorties/flutter-apk/$nom.apk" ] && [ ! -L "$sorties/flutter-apk/$nom.apk" ]; then
    source="$sorties/flutter-apk/$nom.apk"
  elif [ -f "$sorties/apk/$repertoire/$nom-unsigned.apk" ] && [ ! -L "$sorties/apk/$repertoire/$nom-unsigned.apk" ]; then
    source="$sorties/apk/$repertoire/$nom-unsigned.apk"
  fi
  [ -n "$source" ] || { echo "Release non signée introuvable dans $sorties." >&2; return 1; }
  mkdir -p -- "$sorties/flutter-apk" && rm -f -- "$non_signe" && cp -- "$source" "$non_signe" || return 1
  # jamais un nom de release signée pour un APK qui ne l'est pas
  rm -f -- "$sorties/flutter-apk/$nom.apk" "$sorties/flutter-apk/$nom.apk.sha1"
  echo "Release NON signée : $dossier/$non_signe (à déclarer livrable)."
  echo "La signature se fait au poste, par le Directeur : py -3.12 lancer.py signer-release --dossier <projet> --keystore <coffre> --alias <alias> --sortie <fichier>."
}

lancer() {
  {
    if [ ! -f .dart_tool/package_config.json ] || [ pubspec.yaml -nt .dart_tool/package_config.json ] ||
       { [ -f pubspec.lock ] && [ pubspec.lock -nt .dart_tool/package_config.json ]; }; then
      flutter pub get || return $?
    fi
    if [ -n "$init" ]; then
      mkdir -p -- "${init%/*}" && rm -f -- "$init" && printf '%s\n' "$INIT_GRADLE" > "$init" ||
        { echo "Script d'init Gradle non écrit (${init%/*})." >&2; return 1; }
    fi
    flutter "${COMMANDE[@]}" || return $?
    if [ -n "$URL_ATTENDUE" ]; then verifier_l_adresse || return $?; fi
    if [ -n "$NON_SIGNEE" ]; then ranger_non_signee || return 1; fi
  }
}

# L'adresse demandée (SERVEUR_URL) doit être DANS l'APK construit : on la cherche dans le code natif de l'application
# (libapp.so / app.so, sous build/). Sinon la construction est refusée (code 5) et l'APK est retiré : jamais livré comme
# réussi un APK qui n'a pas l'adresse. Le message ne montre jamais la valeur.
verifier_l_adresse() {
  local f trouve=0
  while IFS= read -r f; do
    if grep -a -F -q -- "$URL_ATTENDUE" "$f" 2>/dev/null; then trouve=1; break; fi
  done < <(find build -type f \( -name libapp.so -o -name app.so \) 2>/dev/null)
  if [ "$trouve" = 1 ]; then
    echo "Adresse du service intégrée à l'APK : oui."
    return 0
  fi
  echo "Adresse du service intégrée à l'APK : NON. Construction refusée : l'APK n'a pas reçu SERVEUR_URL." >&2
  local nom="app-release"
  [ -z "${VARIANTE:-}" ] || nom="app-$VARIANTE-release"
  rm -f -- "build/app/outputs/flutter-apk/$nom.apk" "build/app/outputs/flutter-apk/$nom.apk.sha1"            "build/app/outputs/flutter-apk/$nom-unsigned.apk"
  return 5
}

# Aucune valeur de variable de construction n'apparaît dans la sortie : chacune est remplacée par ***.
masquer() {
  if [ "${#VALEURS[@]}" -eq 0 ]; then cat; return; fi
  VALEURS_A_MASQUER=$(printf '%s\n' "${VALEURS[@]}") awk '
    BEGIN { n = split(ENVIRON["VALEURS_A_MASQUER"], v, "\n") }
    { l = $0
      for (i = 1; i <= n; i++) {
        if (v[i] == "") continue
        while ((p = index(l, v[i])) > 0) l = substr(l, 1, p - 1) "***" substr(l, p + length(v[i]))
      }
      print l }'
}
lancer 2>&1 | masquer | tail -c "$SORTIE_MAX"
code="${PIPESTATUS[0]}"
[ -z "$init" ] || rm -f -- "$init"
exit "$code"
