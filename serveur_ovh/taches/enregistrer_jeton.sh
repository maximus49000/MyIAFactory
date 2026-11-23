#!/usr/bin/env bash
# Enregistre le jeton de l'abonnement que les agents du serveur utilisent. Lancé PAR LE DIRECTEUR, sur le serveur, une seule fois :
#   bash ~/myiafactory/serveur_ovh/taches/enregistrer_jeton.sh
# MyIAFactory ne lance jamais ce script et ne voit jamais le jeton (voir docs/serveur-agents.md#connexion-a-l-abonnement).
# Le jeton est lu sur l'entrée standard SANS écho (read -rs), jamais en argument ni dans une variable d'environnement exportée, et
# n'est jamais affiché. Il est écrit dans ~/agent-identifiants/jeton (dossier 0700, fichier 0600) par un fichier temporaire puis mv :
# un refus ou une panne laisse le jeton déjà en place intact.
# Codes de sortie : 0 jeton enregistré ; 2 refusé ou non enregistré (message sans la valeur saisie).
set -u
export LC_ALL=C
umask 077

dossier="$HOME/agent-identifiants"
tmp=""
trap '[ -n "$tmp" ] && rm -f "$tmp"' EXIT

refuser() {
  printf '%s\n' "$1" >&2
  exit 2
}

# droits <chemin> <mode> : ne touche à rien si le mode est déjà le bon (le umask 077 l'a posé à la création).
droits() {
  [ "$(stat -c %a "$1" 2>/dev/null)" = "$2" ] || chmod "$2" "$1"
}

if [ -t 0 ]; then
  printf 'Collez le jeton (rien ne s affiche), puis Entrée : ' >&2
fi
# Une saisie sans retour à la ligne final fait échouer read tout en remplissant la variable : le code de retour est ignoré.
IFS= read -rs jeton || true
if [ -t 0 ]; then
  printf '\n' >&2
fi

[ -n "$jeton" ] || refuser "Jeton vide : rien n'a été enregistré."
# Longueur contrôlée à part : le moteur d'expressions de bash plafonne les répétitions {n,m} (255 sous certaines bibliothèques).
{ [ "${#jeton}" -ge 20 ] && [ "${#jeton}" -le 400 ] && [[ $jeton =~ ^[A-Za-z0-9._-]+$ ]]; } || refuser "Jeton refusé : il doit faire de 20 à 400 caractères parmi les lettres, chiffres, point, tiret et tiret bas (ni espace, ni guillemet, ni autre signe). Rien n'a été enregistré."

mkdir -p "$dossier" || refuser "Dossier $dossier non créable. Rien n'a été enregistré."
droits "$dossier" 700 || refuser "Droits du dossier $dossier non réglables. Rien n'a été enregistré."
tmp=$(mktemp "$dossier/.jeton.XXXXXX") || refuser "Fichier temporaire non créable dans $dossier. Rien n'a été enregistré."
if ! { printf '%s\n' "$jeton" > "$tmp" && droits "$tmp" 600 && mv -f "$tmp" "$dossier/jeton"; }; then
  refuser "Jeton non écrit dans $dossier/jeton. L'éventuel jeton précédent est conservé."
fi
tmp=""
printf '%s\n' "Jeton enregistré dans ~/agent-identifiants/jeton (droits 0600, dossier 0700). La capacité « agent-abonnement » sera constatée à la prochaine sonde du serveur."
exit 0
