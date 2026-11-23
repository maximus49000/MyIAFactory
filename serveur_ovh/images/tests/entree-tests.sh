#!/usr/bin/env bash
# Entrée du conteneur `myiafactory/tests` (copiée en /usr/local/bin/entree-tests.sh) : lance UNE commande de tests sur
# l'instantané du projet, puis rend son code.
# - /entree/commande.json : la commande, tableau JSON de chaînes (1 à 64 éléments, 4 Ko au plus, premier élément non vide,
#   aucun caractère NUL), validé par `python3 -I` ; jamais un texte passé à un shell : chaque élément reste UN argument.
# - /entree/entree.tar : l'instantané (monté en lecture seule), extrait dans /work sous l'utilisateur du conteneur
#   (tar -x --no-same-owner --no-same-permissions) : un nom piégé n'écrit que dans le conteneur jetable.
# - /deps/node_modules, s'il est monté (cache des dépendances Node préparé par l'enveloppe hôte), est lié en /work/node_modules.
# Puis `cd /work` et `exec` de la commande : le code de sortie du conteneur est celui de la commande. Famille unity
# (MYIAFACTORY_TESTS_FAMILLE=unity, posée par l'enveloppe) : `exec entree-unity.sh <commande>` (voir ce script).
# Codes propres : 2 commande absente ou invalide (rien n'est extrait) ; 70 instantané absent ou extraction impossible.
# La durée maximale, l'absence de réseau et les limites sont posées par l'enveloppe hôte (`docker run`), pas ici.
# Réservée aux tests : ENTREE_TESTS_RACINE (préfixe de /entree, /work et /deps ; vide en production).
set -u
exec </dev/null
umask 022
export HOME="${HOME:-/tmp}"

racine="${ENTREE_TESTS_RACINE:-}"
ENTREE="$racine/entree"
WORK="$racine/work"
DEPS="$racine/deps"

echec() {   # echec <code> <message>
  printf 'entree-tests : %s\n' "$2" >&2
  exit "$1"
}

# Validation de la commande : écrit les éléments séparés par NUL, ou rien (code 2) si le fichier n'est pas un tableau valide.
VALIDER='
import json, sys
try:
    brut = sys.stdin.buffer.read(4097)
    if len(brut) > 4096:
        sys.exit(2)
    c = json.loads(brut.decode("utf-8"))
    if (not isinstance(c, list) or not 1 <= len(c) <= 64 or not all(isinstance(x, str) and "\0" not in x for x in c)
            or not c[0]):
        sys.exit(2)
    sys.stdout.buffer.write(b"".join(x.encode("utf-8") + b"\0" for x in c))
except Exception:
    sys.exit(2)
'

[ -f "$ENTREE/commande.json" ] || echec 2 "commande absente ($ENTREE/commande.json)."
args=()
mapfile -d '' -t args < <(python3 -I -c "$VALIDER" < "$ENTREE/commande.json")
if [ "${#args[@]}" -lt 1 ] || [ -z "${args[0]}" ]; then
  echec 2 "commande invalide : un tableau JSON de 1 à 64 chaînes (4 Ko au plus) est attendu."
fi

[ -f "$ENTREE/entree.tar" ] || echec 70 "instantané absent ($ENTREE/entree.tar)."
mkdir -p "$WORK" 2>/dev/null
tar -x --no-same-owner --no-same-permissions -f "$ENTREE/entree.tar" -C "$WORK" || echec 70 "extraction de l'instantané impossible."

if [ -d "$DEPS/node_modules" ]; then
  rm -rf "$WORK/node_modules" && ln -s "$DEPS/node_modules" "$WORK/node_modules" \
    || echec 70 "cache des dépendances Node non liable en $WORK/node_modules."
fi

cd "$WORK" || echec 70 "dossier de travail $WORK inaccessible."
# Famille unity (variable posée par l'enveloppe hôte, table fermée) : entree-unity.sh, voisine de ce script dans l'image
# myiafactory/tests-unity-<version>, copie la licence montée, lance l'éditeur et ne relaie qu'un résumé filtré.
if [ "${MYIAFACTORY_TESTS_FAMILLE:-}" = unity ]; then
  unity="$(dirname -- "$0")/entree-unity.sh"
  [ -f "$unity" ] || echec 2 "entrée Unity absente de l'image ($unity)."
  exec bash "$unity" "${args[@]}"
fi
exec "${args[@]}"
