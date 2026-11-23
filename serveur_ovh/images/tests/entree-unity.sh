#!/usr/bin/env bash
# Entrée Unity du conteneur `myiafactory/tests-unity-<version>` (copiée en /usr/local/bin/entree-unity.sh) : appelée par
# entree-tests.sh (instantané déjà extrait, dossier courant /work) quand l'enveloppe hôte pose MYIAFACTORY_TESTS_FAMILLE=unity.
# CODE SENSIBLE (conception § 5.16, option B, tâche 14g) : la licence Unity de l'hôte est montée en lecture seule dans ce
# conteneur, qui exécute du code du projet.
# - Licence : /licence/droits/ (licence par droits, celle de Hub) est COPIÉE dans $HOME/.config/unity3d/Unity/licenses/ et
#   /licence/ulf (licence manuelle) dans $HOME/.local/share/unity3d/Unity/Unity_lic.ulf, fichiers 0600 (HOME=/tmp : tmpfs, la
#   copie meurt avec le conteneur ; le client de licence veut écrire, le montage est en lecture seule). Rien n'est jamais lu,
#   affiché ni comparé ici : seulement copié. Aucune licence montée : code 81.
# - Commande : le tableau reçu, qui doit commencer par `unity-editor`. Tout `-logFile` et tout `-testResults` (et leur valeur)
#   sont RETIRÉS, puis `-logFile /tmp/unity.log -testResults /tmp/resultats.xml` ajoutés : le journal de l'éditeur ne va jamais
#   sur la sortie (`-logFile -`). La sortie et la sortie d'erreur de l'éditeur vont dans /tmp/unity.sortie, jamais relayées
#   brutes.
# - Relais (sortie standard) : un RÉSUMÉ. Les lignes du journal et de la sortie de l'éditeur, SANS celles qui contiennent
#   (sans tenir compte de la casse) licen|entitlement|serial|token|ulf, ni celles qui portent une suite de 40 caractères de
#   type base64 ou plus (défense en profondeur, au-delà du brief), 200 dernières, 500 caractères chacune ; puis le bilan du XML
#   de résultats : `total=… passed=… failed=…` et 20 noms d'échecs au plus (mêmes filtres).
# - Codes : 81 licence Unity refusée (un motif de refus trouvé dans le journal ou la sortie par `grep -qiE`, jamais affiché) ;
#   82 aucun test découvert (XML absent, illisible ou total == 0, quand l'éditeur rend 0 ou 2 : jamais une réussite) ; sinon
#   celui de l'éditeur (0 tous passent, 2 des échecs, 3 erreur d'exécution, autre : panne), 2 si l'éditeur rend 0 avec des
#   échecs dans le XML ; 2 commande autre que unity-editor.
# Réservée aux tests : ENTREE_TESTS_RACINE (préfixe de /licence et /tmp ; vide en production).
set -u
exec </dev/null
umask 077
export LC_ALL=C

racine="${ENTREE_TESTS_RACINE:-}"
LICENCE_MONTEE="$racine/licence"
T="$racine/tmp"
JOURNAL="$T/unity.log"
SORTIE="$T/unity.sortie"
RESULTATS="$T/resultats.xml"
MOTIF_SECRET='licen|entitlement|serial|token|ulf'          # lignes retirées (sans casse) : valeur du brief, telle quelle
MOTIF_JETON='[A-Za-z0-9+/=_-]{40,}'                        # défense en profondeur : une longue suite base64 n'est jamais relayée
# Licence refusée : motifs de l'étape `licence` de mise_en_place.sh (sans « aborting batchmode », qui suit aussi une erreur
# de compilation) et formes voisines ; À CONFIRMER au jalon J13 sur un vrai refus (journal relevé par noms seulement).
MOTIF_REFUS='no valid unity editor license|not licensed|no ulf license found|license (is )?(not valid|invalid|expired)|licen[cs]e activation (failed|error)'
LIGNES=200
NOMS=20

echec() { printf 'entree-unity : %s\n' "$2" >&2; exit "$1"; }

[ $# -ge 1 ] && [ "$1" = unity-editor ] || echec 2 "commande Unity attendue (unity-editor …)."

# --- Licence : copie sur le tmpfs, jamais lue -----------------------------------------------------------------------------
droits="$HOME/.config/unity3d/Unity/licenses"
partage="$HOME/.local/share/unity3d/Unity"
mkdir -p -- "$droits" "$partage" 2>/dev/null || echec 81 "licence Unity refusée : dossier de copie impossible."
copie=0
if [ -d "$LICENCE_MONTEE/droits" ] && [ -n "$(ls -A -- "$LICENCE_MONTEE/droits" 2>/dev/null)" ]; then
  cp -R -- "$LICENCE_MONTEE/droits/." "$droits/" 2>/dev/null && copie=1
fi
if [ -f "$LICENCE_MONTEE/ulf" ]; then
  cp -- "$LICENCE_MONTEE/ulf" "$partage/Unity_lic.ulf" 2>/dev/null && copie=1
fi
chmod -R u=rwX,go= -- "$HOME/.config/unity3d" "$HOME/.local/share/unity3d" 2>/dev/null
[ "$copie" = 1 ] || echec 81 "licence Unity refusée : aucune licence montée dans le conteneur."

# --- Commande : journal et résultats imposés -------------------------------------------------------------------------------
cmd=(); saute=0
for a in "$@"; do
  if [ "$saute" = 1 ]; then
    saute=0
    [ "$a" = - ] || [ "${a:0:1}" != - ] && continue      # la valeur de l'option retirée (un drapeau suivant est gardé)
  fi
  case "${a,,}" in -logfile|-testresults) saute=1; continue ;; esac
  cmd+=("$a")
done
cmd+=(-logFile "$JOURNAL" -testResults "$RESULTATS")
mkdir -p -- "$T" 2>/dev/null
rm -f -- "$JOURNAL" "$SORTIE" "$RESULTATS"
"${cmd[@]}" > "$SORTIE" 2>&1
code=$?

# --- Résumé filtré ----------------------------------------------------------------------------------------------------------
filtrer() { grep -aviE "$MOTIF_SECRET" | grep -avE "$MOTIF_JETON"; }
printf 'unity : journal de l%séditeur (lignes filtrées, %s dernières au plus)\n' "'" "$LIGNES"
cat -- "$JOURNAL" "$SORTIE" 2>/dev/null | tr -d '\r' | filtrer | tail -n "$LIGNES" | cut -c1-500

if grep -sqiE -- "$MOTIF_REFUS" "$JOURNAL" "$SORTIE"; then
  echec 81 "licence Unity refusée (motif reconnu dans le journal de l'éditeur, jamais affiché) : code de l'éditeur $code."
fi

BILAN='
import os, re, sys
import xml.etree.ElementTree as ET
chemin, secret, jeton, nombre = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
try:
    if os.path.getsize(chemin) > 64 * 1024 * 1024:
        sys.exit(3)
    racine = ET.parse(chemin).getroot()
except Exception:
    sys.exit(3)
run = racine if racine.tag == "test-run" else racine.find(".//test-run")
if run is None:
    sys.exit(3)
def entier(cle):
    v = run.get(cle, "")
    return int(v) if re.fullmatch(r"[0-9]{1,9}", v) else None
total, reussis, echoues = entier("total"), entier("passed"), entier("failed")
if None in (total, reussis, echoues):
    sys.exit(3)
print(total, reussis, echoues)
vus = 0
for cas in run.iter("test-case"):
    if cas.get("result") != "Failed":
        continue
    nom = "".join(c if c.isprintable() else "?" for c in (cas.get("fullname") or cas.get("name") or ""))[:200]
    if not nom or re.search(secret, nom, re.I) or re.search(jeton, nom):
        continue
    print(nom)
    vus += 1
    if vus >= nombre:
        break
'
bilan=$(python3 -I -c "$BILAN" "$RESULTATS" "$MOTIF_SECRET" "$MOTIF_JETON" "$NOMS" 2>/dev/null); rb=$?
total=""; reussis=""; echoues=""
if [ "$rb" = 0 ]; then
  read -r total reussis echoues <<< "${bilan%%$'\n'*}"
fi
if ! [[ $total =~ ^[0-9]+$ && $reussis =~ ^[0-9]+$ && $echoues =~ ^[0-9]+$ ]]; then
  if [ "$code" = 0 ] || [ "$code" = 2 ]; then
    echec 82 "aucun test découvert (résultats XML absents ou illisibles ; code de l'éditeur $code)."
  fi
  echec "$code" "résultats XML absents ; code de l'éditeur $code."
fi
printf 'unity : bilan total=%s passed=%s failed=%s\n' "$total" "$reussis" "$echoues"
if [ "$echoues" -gt 0 ]; then
  printf '%s\n' "$bilan" | tail -n +2 | sed 's/^/unity : échec /'
fi
if [ "$total" = 0 ] && { [ "$code" = 0 ] || [ "$code" = 2 ]; }; then
  echec 82 "aucun test découvert (0 test exécuté : jamais une réussite)."
fi
[ "$code" = 0 ] && [ "$echoues" -gt 0 ] && code=2
exit "$code"
