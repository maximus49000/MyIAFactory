"""Agents sur le serveur (tranche B) : demande d'agent validée, paquet Git à l'aller (`git bundle`), lancement de
`serveur_ovh/taches/lancer_agent.sh`, rapatriement du flux, de `fin.json` et du paquet résultat.

Aucune écriture sur GitHub depuis le serveur : l'aller est un paquet Git envoyé par SSH, le retour un paquet rapatrié en
octets. Tout ce que le serveur renvoie (fin.json, flux, paquet) est une DONNÉE NON FIABLE : `fin.json` est revalidé champ par
champ, le paquet est analysé (en-tête relu ici, puis `git bundle verify` et `list-heads`) et seule la référence
`refs/heads/agent/<tâche>` est acceptée, sans jamais exécuter ce que contient un dépôt du serveur. Sections : demande ;
paquets Git ; scripts distants ; lancer ; récupérer ; index.
"""
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

import plateforme_acces
import plateforme_ssh
import serveur_capacites
import serveur_tache as st
from plateforme import DOSSIER_DISTANT, RACINE_SERVEUR

# ---------------------------------------------------------------- demande

LIMITES_AGENT = {"duree_s": 2400, "tours": 200, "memoire_mo": 4096, "cpus": 2, "paquet_octets": 524288000,
                 "flux_octets": 20971520}
MODES_AGENT = ("seul", "pilote")
PLACES_DEFAUT = 2
CLES_DEMANDE_AGENT = frozenset({"id", "projet", "tache", "mode", "modele", "branche", "base", "limites", "reprend", "places"})
# Mêmes motifs que serveur_ovh/images/agent/entree-agent.py (qui les revérifie sur le serveur).
MOTIF_TACHE = re.compile(r"[A-Za-z0-9_.-]{1,60}", re.ASCII)
MOTIF_BRANCHE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}", re.ASCII)
MOTIF_BASE = re.compile(r"[0-9a-f]{40}", re.ASCII)
MOTIF_MODELE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\[\]-]{0,59}", re.ASCII)
ENTETE_MAX = 65536                 # en-tête d'un paquet Git : lu sur 64 Ko au plus
FIN_MAX_OCTETS = 65536
DELAI_GIT_S = 300


@dataclass(frozen=True)
class DemandeAgent:
    id: str
    projet: str
    tache: str
    mode: str
    modele: object
    branche: str
    base: str
    limites: object          # MappingProxyType : immuable
    reprend: object
    places: int


class RefusRecuperation(ValueError):
    """Ce que le serveur a renvoyé est refusé (fin.json ou paquet suspect, branche locale divergente) : message français."""


def _git(projet, args, max_octets=None):
    """(code, sortie octets, erreur texte) d'un appel `git` en tableau d'arguments (aucun shell), dans `projet`. Sortie plus
    grande que `max_octets` : arrêt du processus et code 99. Jamais d'invite, ni de configuration de hooks du poste suivie."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        p = subprocess.Popen(["git", *args], cwd=str(projet), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, env=env)
    except OSError as e:
        return 127, b"", f"git introuvable ou inutilisable ({type(e).__name__})"
    morceaux, total, trop = [], 0, False
    try:
        while True:
            bloc = p.stdout.read(1 << 20)
            if not bloc:
                break
            total += len(bloc)
            if max_octets is not None and total > max_octets:
                trop = True
                p.kill()
                break
            morceaux.append(bloc)
        erreur = p.stderr.read(65536)
        p.wait(timeout=DELAI_GIT_S)
    except subprocess.TimeoutExpired:
        p.kill()
        return 124, b"", "git : délai dépassé"
    finally:
        p.stdout.close()
        p.stderr.close()
    if trop:
        return 99, b"", ""
    return p.returncode, b"".join(morceaux), erreur.decode("utf-8", "replace")


def _ref_valide(nom, git_, drapeau=()):
    code, sortie, _e = git_(Path("."), ["check-ref-format", *drapeau, nom])
    return code == 0, sortie.decode("utf-8", "replace").strip()


def _entier_limite(cle, v):
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"La limite « {cle} » doit être un nombre entier.")
    if not 1 <= v <= LIMITES_AGENT[cle]:
        raise ValueError(f"La limite « {cle} » doit être comprise entre 1 et {LIMITES_AGENT[cle]}.")
    return v


def valider_demande_agent(brut, git=_git):
    """`DemandeAgent` validée ; `ValueError` (message français) sinon. Les limites ne dépassent jamais `LIMITES_AGENT`."""
    if not isinstance(brut, dict):
        raise ValueError("La demande d'agent doit être un dictionnaire.")
    inconnues = set(brut) - CLES_DEMANDE_AGENT
    if inconnues:
        raise ValueError("Champ inconnu dans la demande d'agent : "
                         + ", ".join(sorted(repr(str(c)[:40]) for c in inconnues)) + ".")
    mode = brut.get("mode")
    if mode not in MODES_AGENT:
        raise ValueError("Mode inconnu : « seul » ou « pilote ».")
    tache = brut.get("tache")
    if (not isinstance(tache, str) or not MOTIF_TACHE.fullmatch(tache) or tache.startswith(".") or ".." in tache
            or tache.endswith((".", ".lock"))):
        raise ValueError("Nom de tâche invalide (lettres, chiffres, _ . - ; 60 caractères au plus ; ni « .. » ni point "
                         "au début ou à la fin).")
    base = brut.get("base")
    if not isinstance(base, str) or not MOTIF_BASE.fullmatch(base):
        raise ValueError("Base invalide : 40 caractères hexadécimaux (minuscules) attendus.")
    branche = brut.get("branche")
    if (not isinstance(branche, str) or not MOTIF_BRANCHE.fullmatch(branche) or ".." in branche or "//" in branche
            or branche.endswith(("/", ".", ".lock")) or "/." in branche):
        raise ValueError("Nom de branche invalide.")
    bon, _s = _ref_valide(branche, git, ("--branch",))
    if not bon or _s != branche:
        raise ValueError("Nom de branche refusé par git (check-ref-format).")
    bon, _s = _ref_valide(f"refs/heads/agent/{tache}", git)
    if not bon:
        raise ValueError("Nom de tâche refusé par git : la branche agent/<tâche> serait invalide.")
    reprend = brut.get("reprend")
    if reprend is not None and (not isinstance(reprend, str) or not st.MOTIF_ID.fullmatch(reprend)):
        raise ValueError("Reprise invalide : identifiant de tâche attendu.")
    ident = brut["id"] if "id" in brut else st.nouvel_id()
    if not isinstance(ident, str) or not st.MOTIF_ID.fullmatch(ident):
        raise ValueError("Identifiant de tâche invalide.")
    projet = brut.get("projet")
    if (not isinstance(projet, str) or not projet or len(projet.encode("utf-8")) > 200 or '"' in projet or "\\" in projet
            or any(st._controle(c) for c in projet)):
        raise ValueError("Nom de projet invalide (1 à 200 octets, ni guillemet, ni antislash, ni caractère de contrôle).")
    modele = brut.get("modele")
    if modele is not None and (not isinstance(modele, str) or not MOTIF_MODELE.fullmatch(modele)):
        raise ValueError("Nom de modèle invalide.")
    places = brut.get("places", PLACES_DEFAUT)
    if isinstance(places, bool) or not isinstance(places, int) or not 1 <= places <= 4:
        raise ValueError("Le nombre de places d'agent doit être compris entre 1 et 4.")
    limites_brutes = brut.get("limites")
    if limites_brutes is not None and not isinstance(limites_brutes, dict):
        raise ValueError("Les limites doivent être un dictionnaire.")
    limites = dict(LIMITES_AGENT)
    for cle, v in (limites_brutes or {}).items():
        if cle not in LIMITES_AGENT:
            raise ValueError("Limite inconnue : " + repr(str(cle)[:40]) + ".")
        limites[cle] = _entier_limite(cle, v)
    return DemandeAgent(id=ident, projet=projet, tache=tache, mode=mode, modele=modele, branche=branche, base=base,
                        limites=MappingProxyType(limites), reprend=reprend, places=places)


def _demande_dict(d):
    """Contenu de entree/demande.json. `projet` et `reprend` n'y figurent qu'une fois (l'enveloppe les relit par motif) ;
    `limites.duree_s` est la valeur même passée à l'enveloppe (une seule source)."""
    return {"id": d.id, "type": "agent", "projet": d.projet, "tache": d.tache, "mode": d.mode, "modele": d.modele,
            "branche": d.branche, "base": d.base, "limites": dict(d.limites), "reprend": d.reprend}


def _demande_sure(demande):
    if isinstance(demande, DemandeAgent):
        brut = {"id": demande.id, "projet": demande.projet, "tache": demande.tache, "mode": demande.mode,
                "modele": demande.modele, "branche": demande.branche, "base": demande.base,
                "limites": dict(demande.limites), "reprend": demande.reprend, "places": demande.places}
    elif isinstance(demande, dict):
        brut = demande
    else:
        raise st.RefusLancement("La demande doit être une DemandeAgent ou un dictionnaire.")
    try:
        return valider_demande_agent(brut)
    except ValueError as e:
        raise st.RefusLancement(str(e)) from None


# ---------------------------------------------------------------- paquets Git

def preparer_paquet(projet, git=_git):
    """`(paquet, branche, base)` de `HEAD` du dépôt `projet` : `git bundle create - HEAD <branche>`. Refuse un HEAD détaché,
    un dépôt sans commit et un paquet au-dessus de `LIMITES_AGENT["paquet_octets"]`. Les changements non commités ne partent
    pas (le message le dit)."""
    projet = Path(projet)
    code, sortie, _e = git(projet, ["symbolic-ref", "--short", "-q", "HEAD"])
    branche = sortie.decode("utf-8", "replace").strip()
    if code != 0 or not branche:
        raise st.RefusLancement("HEAD est détaché : placez le projet sur une branche avant de lancer un agent serveur "
                                "(seuls les commits de la branche partent).")
    code, sortie, erreur = git(projet, ["rev-parse", "--verify", "-q", "HEAD^{commit}"])
    base = sortie.decode("ascii", "replace").strip()
    if code != 0 or not MOTIF_BASE.fullmatch(base):
        raise st.RefusLancement("Le projet n'a aucun commit : rien à envoyer à l'agent serveur.")
    maximum = LIMITES_AGENT["paquet_octets"]
    code, paquet, erreur = git(projet, ["bundle", "create", "-", "HEAD", branche], max_octets=maximum)
    if code == 99:
        raise st.RefusLancement(f"Le paquet Git du projet dépasse {maximum // (1024 * 1024)} Mo : trop gros pour "
                                "l'agent serveur.")
    if code != 0 or not paquet:
        raise st.RefusLancement(f"Paquet Git impossible (git bundle, code {code}) : {st._court(erreur, 200)}")
    if len(paquet) > maximum:
        raise st.RefusLancement(f"Le paquet Git du projet dépasse {maximum // (1024 * 1024)} Mo : trop gros pour "
                                "l'agent serveur.")
    return paquet, branche, base


def _analyser_entete(paquet, ref, base):
    """Relit l'en-tête du paquet (texte avant la première ligne vide) : version 2 ou 3 (`object-format=sha1` seul),
    exactement un prérequis égal à `base`, exactement une référence `ref`. `RefusRecuperation` sinon. Rend la tête."""
    fin = paquet.find(b"\n\n", 0, ENTETE_MAX)
    if fin < 0:
        raise RefusRecuperation("Paquet Git refusé : en-tête introuvable.")
    lignes = paquet[:fin].decode("utf-8", "replace").split("\n")
    if lignes[0] not in ("# v2 git bundle", "# v3 git bundle"):
        raise RefusRecuperation("Paquet Git refusé : ce n'est pas un paquet reconnu (v2 ou v3).")
    prerequis, refs = [], []
    for ligne in lignes[1:]:
        if ligne.startswith("@"):
            if ligne != "@object-format=sha1" or lignes[0] != "# v3 git bundle":
                raise RefusRecuperation("Paquet Git refusé : capacité non admise.")
            continue
        m = re.fullmatch(r"-([0-9a-f]{40})( .*)?", ligne, re.ASCII | re.DOTALL)
        if m:
            prerequis.append(m.group(1))
            continue
        m = re.fullmatch(r"([0-9a-f]{40}) (\S.*)", ligne, re.ASCII)
        if not m:
            raise RefusRecuperation("Paquet Git refusé : ligne d'en-tête inattendue.")
        refs.append((m.group(1), m.group(2)))
    if [r for _t, r in refs] != [ref] or len(refs) != 1:
        raise RefusRecuperation(f"Paquet Git refusé : la seule référence admise est {ref}.")
    if prerequis != [base]:
        raise RefusRecuperation("Paquet Git refusé : son prérequis n'est pas la base envoyée à l'agent.")
    return refs[0][0]


def _verifier_et_recuperer_paquet(projet, paquet, tache, base, git):
    """Vérifie le paquet (en-tête, `git bundle verify`, `list-heads`) puis le récupère dans le dépôt `projet` par un
    `git fetch` simple de la seule référence admise (jamais forcé : une branche locale divergente n'est pas réécrite).
    Le fichier temporaire est toujours effacé. Rien du dépôt du serveur n'est exécuté : le paquet est un fichier de données,
    lu par git avec les contrôles d'intégrité des objets (`transfer.fsckObjects`), hooks et moniteur de fichiers coupés."""
    ref = f"refs/heads/agent/{tache}"
    tete = _analyser_entete(paquet, ref, base)
    sur = ["-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false", "-c", "gc.auto=0",
           "-c", "maintenance.auto=false", "-c", "transfer.fsckObjects=true"]
    with tempfile.TemporaryDirectory(prefix="agent-paquet-") as tmp:
        fichier = Path(tmp) / "resultat.bundle"
        fichier.write_bytes(paquet)
        code, _o, erreur = git(projet, [*sur, "bundle", "verify", str(fichier)])
        if code != 0:
            raise RefusRecuperation(f"Paquet Git abîmé ou incomplet (git bundle verify) : {st._court(erreur, 200)}")
        code, sortie, erreur = git(projet, [*sur, "bundle", "list-heads", str(fichier)])
        tetes = [ligne.split(" ", 1) for ligne in sortie.decode("utf-8", "replace").splitlines() if ligne.strip()]
        if code != 0 or tetes != [[tete, ref]]:
            raise RefusRecuperation(f"Paquet Git refusé : la seule référence admise est {ref}.")
        code, _o, erreur = git(projet, [*sur, "fetch", "--no-tags", "--no-recurse-submodules", "--quiet",
                                        str(fichier), f"{ref}:{ref}"])
        if code != 0:
            raise RefusRecuperation("Branche non récupérée : la branche locale agent/" + tache + " a divergé ou ne "
                                    f"peut pas être mise à jour (non réécrite) : {st._court(erreur, 200)}")
        code, sortie, _e = git(projet, ["rev-parse", "--verify", "-q", ref])
        if sortie.decode("ascii", "replace").strip() != tete:
            raise RefusRecuperation("Branche récupérée inattendue : vérification impossible.")


# ---------------------------------------------------------------- scripts distants

AGENT_SCRIPT = "taches/lancer_agent.sh"
AGENT_DISTANT = f"{DOSSIER_DISTANT}/{AGENT_SCRIPT}"
PONT_HOTE = "taches/pont_hote.py"          # tâche 7 : déposé s'il existe dans le dépôt (mode pilote)
FICHIERS_ENTREE = ("projet.bundle", "argv.json", "consigne.md", "message.md", "demande.json")
FICHIERS_SORTIE = ("flux.jsonl", "fin.json", "resultat.bundle")
CODE_TROP_GROS = 5

# Préparation : le dossier de la tâche est créé par mkdir (atomique ; 73 s'il existe), l'archive extraite dans un temporaire
# privé, chaque fichier d'entrée vérifié (ordinaire, pas un lien) puis déplacé à sa place ; le temporaire est toujours supprimé.
_PREPARER_AGENT = """# tache:preparer_agent @ID@
umask 077
mkdir -p "$HOME/taches" || exit 1
d="$HOME/taches/@ID@"
mkdir "$d" 2>/dev/null || exit 73
t=$(mktemp -d "$HOME/taches/.depot.XXXXXX") || exit 1
r=1
if tar -x --no-same-owner -C "$t" -f -; then
  ok=1
  for f in @FICHIERS@; do
    [ -f "$t/entree/$f" ] && [ ! -L "$t/entree/$f" ] || ok=0
  done
  if [ "$ok" = 1 ] && mkdir "$d/entree" && chmod 755 "$d/entree" 2>/dev/null; then
    r=0
    for f in @FICHIERS@; do mv -f "$t/entree/$f" "$d/entree/$f" || r=1; done
  fi
fi
rm -rf "$t"
exit $r
"""
_DEPOSER_AGENT = f"""# tache:deposer_agent
umask 077
mkdir -p "$HOME/myiafactory" || exit 1
d=$(mktemp -d "$HOME/myiafactory/.depot.XXXXXX") || exit 1
f="$d/{AGENT_SCRIPT}"
c="$d/{st.COMMUN}"
p="$d/{PONT_HOTE}"
r=1
if tar -x --no-same-owner -C "$d" -f - && [ -f "$f" ] && [ ! -L "$f" ] && [ -s "$f" ] && [ -f "$c" ] && [ ! -L "$c" ] && [ -s "$c" ]; then
  mkdir -p "{DOSSIER_DISTANT}/taches" && mv -f "$c" "{st.COMMUN_DISTANT}" && mv -f "$f" "{AGENT_DISTANT}" && r=0
  if [ "$r" = 0 ] && [ -f "$p" ] && [ ! -L "$p" ] && [ -s "$p" ]; then mv -f "$p" "{DOSSIER_DISTANT}/{PONT_HOTE}" || r=1; fi
fi
rm -rf "$d"
exit $r
"""
# <id> <mode> <duree_s> <memoire_mo> <cpus> <places> : tous validés (identifiant, mode, entiers dans les bornes).
_LANCER_AGENT = f"""# tache:lancer_agent @ID@
exec bash "{AGENT_DISTANT}" @ID@ @MODE@ @DUREE@ @MEMOIRE@ @CPUS@ @PLACES@
"""
# Un fichier de sortie/ : seulement ordinaire (ni lien symbolique, ni lien dur), de taille APPARENTE sous @MAX@ octets, dans
# un sortie/ dont le chemin physique est bien celui de la tâche ; jamais rien d'autre (pont/, travail/, maison/ sont ignorés).
# 3 : absent ; 5 : trop gros ou lien.
_FICHIER = """# tache:fichier @ID@ @NOM@
set -u
r=$(cd -P -- "$HOME/taches/@ID@" 2>/dev/null && pwd -P) || exit 3
cd -P -- "$r/sortie" 2>/dev/null && [ "$(pwd -P)" = "$r/sortie" ] || exit 3
[ -e "./@NOM@" ] || exit 3
[ -f "./@NOM@" ] && [ ! -L "./@NOM@" ] || exit 5
[ -n "$(find "./@NOM@" -maxdepth 0 -type f -links 1 -size -@MAX@c 2>/dev/null)" ] || exit 5
exec head -c @MAX@ -- "./@NOM@"
"""


def _script(modele, ident, **valeurs):
    return st._script(modele, ident, **valeurs)


def _deposer_agent(serveur, ssh, avec_pont):
    """Dépose lancer_agent.sh, commun.sh (qu'il source) et, s'il existe et pour le mode pilote, pont_hote.py. None si réussi,
    sinon le message."""
    fichiers = []
    for rel, mode in ((AGENT_SCRIPT, 0o755), (st.COMMUN, 0o644)):
        source = RACINE_SERVEUR / rel
        if source.is_symlink() or not source.is_file():
            return f"Fichier du dépôt introuvable : serveur_ovh/{rel}."
        fichiers.append((rel, source.read_bytes(), mode))
    pont = RACINE_SERVEUR / PONT_HOTE
    if avec_pont and pont.is_file() and not pont.is_symlink():
        fichiers.append((PONT_HOTE, pont.read_bytes(), 0o644))
    code, _o, erreur = st._octets(serveur, ssh, _DEPOSER_AGENT, st._archive(fichiers), delai=120, silencieux=True)
    if code != 0:
        return f"Dépôt de l'enveloppe d'agent sur le serveur impossible (code {code}) : {st._court(erreur, 200)}"
    messages = [ligne for ligne in erreur.splitlines()
                if ligne.strip() and not ligne.strip().startswith("Warning: Permanently added ")]
    if messages:
        return f"Dépôt de l'enveloppe d'agent douteux (messages du serveur) : {st._court(' '.join(messages), 200)}"
    return None


# ---------------------------------------------------------------- lancer

def _texte_octets(valeur, nom):
    if isinstance(valeur, str):
        return valeur.encode("utf-8")
    if isinstance(valeur, (bytes, bytearray)):
        return bytes(valeur)
    raise st.RefusLancement(f"{nom} : du texte est attendu.")


def _envoyer(serveur, ssh, d, paquet, argv, consigne, message, apk):
    """Crée ~/taches/<id> (qui ne doit pas exister) avec entree/ ; (code, erreur), 73 si l'identifiant est pris."""
    demande = (json.dumps(_demande_dict(d), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    membres = [("entree/projet.bundle", paquet, 0o600),
               ("entree/argv.json", (json.dumps(argv, ensure_ascii=False) + "\n").encode("utf-8"), 0o600),
               ("entree/consigne.md", consigne, 0o600), ("entree/message.md", message, 0o600),
               ("entree/demande.json", demande, 0o600)]
    fichiers = list(FICHIERS_ENTREE)
    if d.mode == "pilote":
        membres.append(("entree/app.apk", apk, 0o644))
        fichiers.append("app.apk")
    code, _s, erreur = st._octets(serveur, ssh, _script(_PREPARER_AGENT, d.id, FICHIERS=" ".join(fichiers)),
                                  st._archive(membres), delai=900)
    return code, erreur


def lancer_agent(demande, paquet, argv, consigne, message, apk=None, dossier=plateforme_acces.DOSSIER,
                 ssh=plateforme_ssh, attente_max_s=600, dormir=time.sleep):
    """Envoie les entrées de l'agent (paquet Git, `argv.json`, consigne, message, demande ; `apk` obligatoire en mode pilote),
    démarre `lancer_agent.sh` sur le serveur choisi (capacités `BESOINS["agent-serveur"]` ou `["agent-pilote"]`), attend une
    place (nouvel essai toutes les 15 s jusqu'à `attente_max_s`) et tient l'index (fiche `type: agent`).

    Renvoie `{id, etat, serveur_id}`, plus `erreur` en cas d'échec ou d'abandon, comme `serveur_tache.lancer`.
    `RefusLancement` avant tout envoi : demande, paquet, argv, APK ou délai invalide, aucun serveur prêt."""
    d = _demande_sure(demande)
    if not isinstance(paquet, (bytes, bytearray)) or not paquet:
        raise st.RefusLancement("Paquet Git absent ou vide : les octets du paquet sont attendus.")
    if len(paquet) > d.limites["paquet_octets"]:
        raise st.RefusLancement(f"Paquet Git trop gros : {d.limites['paquet_octets'] // (1024 * 1024)} Mo au plus.")
    if (not isinstance(argv, list) or not argv or not all(isinstance(a, str) and "\0" not in a for a in argv)
            or len(json.dumps(argv)) > 65536):
        raise st.RefusLancement("argv invalide : une liste de textes (la commande claude et ses options) est attendue.")
    consigne, message = _texte_octets(consigne, "Consigne"), _texte_octets(message, "Message")
    for nom, v in (("Consigne", consigne), ("Message", message)):
        if not v or len(v) > 1024 * 1024:
            raise st.RefusLancement(f"{nom} vide ou trop long (1 Mo au plus).")
    if d.mode == "pilote":
        st._apk_sur(apk)
    else:
        apk = None
    if isinstance(attente_max_s, bool) or not isinstance(attente_max_s, int) or attente_max_s < 0:
        raise st.RefusLancement("attente_max_s doit être un nombre entier de secondes, positif ou nul.")
    requises = serveur_capacites.BESOINS["agent-pilote" if d.mode == "pilote" else "agent-serveur"]
    serveur = st.choisir_serveur(dossier, requises)

    def sortie(etat_, **plus):
        return st._masque({"id": d.id, "etat": etat_, "serveur_id": serveur.id, **plus}, dossier)

    candidat = d.id
    for _ in range(st.ESSAIS_ID):
        if candidat not in st.Index(dossier).lire():
            code, erreur = _envoyer(serveur, ssh, replace(d, id=candidat), paquet, argv, consigne, message, apk)
            if code == 0:
                break
            if code != st.CODE_EXISTE:
                d = replace(d, id=candidat)
                if code not in st.INJOIGNABLE:
                    st._bash(serveur, ssh, _script(st._EFFACER, candidat))
                return sortie("echouee", erreur=f"Envoi des entrées de l'agent impossible (code {code}) : "
                                                f"{st._court(erreur, 200)}")
        candidat = st.nouvel_id()
    else:
        raise st.RefusLancement("Aucun identifiant de tâche libre après plusieurs essais : réessayez.")
    d = replace(d, id=candidat)
    fiche = {"type": "agent", "etat": "en_attente", "serveur_id": serveur.id, "mode": d.mode, "projet": d.projet,
             "tache": d.tache, "session": None, "branche": d.branche, "base": d.base, "reprend": d.reprend,
             "limites": dict(d.limites), "cree": st._maintenant_iso(), "debut": None, "fin": None, "statut": None,
             "raison": "Entrées envoyées : démarrage demandé."}
    try:
        st.Index(dossier).enregistrer(d.id, st._masque(fiche, dossier))
    except (st.ErreurIndex, TimeoutError, ValueError, OSError) as e:
        st._bash(serveur, ssh, _script(st._EFFACER, d.id))
        return sortie("echouee", erreur=f"{st._court(e)} : tâche non démarrée, rien ne tourne sur le serveur.")

    probleme = _deposer_agent(serveur, ssh, d.mode == "pilote")
    if probleme:
        st._bash(serveur, ssh, _script(st._EFFACER, d.id))
        avert = st._noter(dossier, d.id, {"etat": "echouee", "statut": "erreur", "fin": st._maintenant_iso(),
                                          "raison": probleme})
        return sortie("echouee", erreur=probleme + (f" ({avert})" if avert else ""))
    commande = _script(_LANCER_AGENT, d.id, MODE=d.mode, DUREE=str(int(d.limites["duree_s"])),
                       MEMOIRE=str(int(d.limites["memoire_mo"])), CPUS=str(int(d.limites["cpus"])),
                       PLACES=str(int(d.places)))
    attendu = 0
    while True:
        code, sortie_texte, erreur = st._bash(serveur, ssh, commande, delai=180)
        if code != 75:
            break
        if attendu >= attente_max_s:
            message_abandon = (f"Aucune place d'agent libre après {attendu} s : lancement abandonné (la tâche reste en "
                               "attente sur le serveur ; relancez plus tard).")
            avert = st._noter(dossier, d.id, {"etat": "en_attente", "raison": message_abandon, "abandonnee": True})
            return sortie("en_attente", erreur=message_abandon + (f" ({avert})" if avert else ""))
        dormir(st.PAUSE_CRENEAU_S)
        attendu += st.PAUSE_CRENEAU_S

    lu = st._derniere_ligne_json(sortie_texte, d.id)
    if code in (0, 3):
        avert = st._noter(dossier, d.id, {"etat": "en_cours", "debut": (lu or {}).get("debut"),
                                          "raison": (lu or {}).get("raison", "")})
        return sortie("en_cours", erreur=avert) if avert else sortie("en_cours")
    if code in st.INJOIGNABLE or code == 4:
        relu = st._etat(d.id, dossier, ssh)
        if relu["etat"] == "arretee":
            return sortie("arretee", raison=relu.get("raison", ""))
        motif = ("Réponse du serveur perdue pendant le démarrage : état relu sur le serveur."
                 if code != 4 else "Identifiant déjà utilisé sur le serveur : état relu sur le serveur.")
        return sortie(relu["etat"], erreur=f"{motif} {relu.get('raison', '')}".strip())
    raison = (lu or {}).get("raison") or f"Démarrage refusé par l'enveloppe (code {code}) : {st._court(erreur, 200)}"
    if lu is None:                      # argument refusé (code 2) : rien n'a été écrit, le dossier d'entrée est effacé
        st._bash(serveur, ssh, _script(st._EFFACER, d.id))
    avert = st._noter(dossier, d.id, {"etat": "echouee", "statut": "erreur",
                                      "fin": (lu or {}).get("fin") or st._maintenant_iso(), "raison": raison})
    return sortie("echouee", erreur=raison + (f" ({avert})" if avert else ""))


# ---------------------------------------------------------------- récupérer

def _fichier_sortie(serveur, ssh, ident, nom, maximum):
    """Octets d'un fichier de sortie/ ; None s'il est absent ; `RefusRecuperation` s'il est trop gros, n'est pas un fichier
    ordinaire ou si le serveur est muet. Taille bornée par la taille apparente, vérifiée aussi sur ce qui est reçu."""
    if nom not in FICHIERS_SORTIE:
        raise ValueError("Fichier de sortie inconnu.")
    code, donnees, erreur = st._octets(serveur, ssh, "bash -s",
                                       _script(_FICHIER, ident, NOM=nom, MAX=str(maximum + 1)).encode("utf-8"),
                                       delai=900)
    if code == 3:
        return None
    if code == CODE_TROP_GROS:
        raise RefusRecuperation(f"{nom} refusé : fichier trop gros (plus de {maximum} octets) ou qui n'est pas ordinaire.")
    if code != 0:
        raise RefusRecuperation(f"Rapatriement de {nom} en échec (code {code}) : {st._court(erreur, 200)}")
    if len(donnees) > maximum:
        raise RefusRecuperation(f"{nom} refusé : plus de {maximum} octets reçus.")
    return donnees


def _entier_fin(v, nom, maxi):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= maxi:
        raise RefusRecuperation(f"fin.json refusé : « {nom} » invalide.")
    return v


def _lire_fin(octets, tache, base):
    """fin.json NON FIABLE -> `{"code", "commits", "branche", "base"[, "echeance"]}` revalidé (clés inconnues ignorées)."""
    try:
        brut = json.loads(octets.decode("utf-8"))
    except (ValueError, RecursionError):
        raise RefusRecuperation("fin.json refusé : JSON illisible.") from None
    if not isinstance(brut, dict):
        raise RefusRecuperation("fin.json refusé : objet attendu.")
    if isinstance(brut.get("code"), bool) or not isinstance(brut.get("code"), int) or abs(brut["code"]) > 1000:
        raise RefusRecuperation("fin.json refusé : « code » invalide.")
    commits = _entier_fin(brut.get("commits"), "commits", 1_000_000)
    branche = brut.get("branche")
    if commits > 0 and branche != f"agent/{tache}":
        raise RefusRecuperation(f"fin.json refusé : la seule branche admise est agent/{tache}.")
    if branche is not None and (not isinstance(branche, str) or branche != f"agent/{tache}"):
        raise RefusRecuperation(f"fin.json refusé : la seule branche admise est agent/{tache}.")
    if brut.get("base") != base:
        raise RefusRecuperation("fin.json refusé : la base ne correspond pas à celle envoyée à l'agent.")
    fin = {"code": brut["code"], "commits": commits, "branche": branche, "base": base}
    if isinstance(brut.get("echeance"), bool):
        fin["echeance"] = brut["echeance"]
    return fin


def recuperer(ident, projet, dossier=plateforme_acces.DOSSIER, ssh=plateforme_ssh, git=_git):
    """Rapatrie la sortie d'une tâche d'agent FINIE (`terminee` ou `arretee` seulement : `echouee` peut signaler un secret
    trouvé, sortie vidée) : `{"flux": octets, "fin": dict, "branche": "agent/<tâche>" | None}` plus `etat` et, hors fin
    normale, `raison`. Le paquet est vérifié puis la branche récupérée dans le dépôt `projet` (voir
    `_verifier_et_recuperer_paquet`). Une tâche qui n'est pas finie, ou finie en échec, ne rapatrie rien (flux vide, branche
    None). `RefusRecuperation` si le serveur renvoie du suspect (fin.json, paquet, branche divergente)."""
    st._id_valide(ident)
    fiche = st.Index(dossier).lire().get(ident) or {}
    tache, base = fiche.get("tache"), fiche.get("base")
    if (fiche.get("type") != "agent" or not isinstance(tache, str) or not MOTIF_TACHE.fullmatch(tache)
            or not isinstance(base, str) or not MOTIF_BASE.fullmatch(base)):
        raise RefusRecuperation("Cette tâche n'est pas une tâche d'agent connue de l'index (tâche ou base inconnue).")
    lu = st.etat(ident, dossier, ssh)
    if lu.get("etat") not in ("terminee", "arretee"):
        return {"flux": b"", "fin": {}, "branche": None, "etat": lu.get("etat"), "raison": lu.get("raison", "")}
    serveur = st._serveur_de(ident, dossier)
    flux = _fichier_sortie(serveur, ssh, ident, "flux.jsonl", LIMITES_AGENT["flux_octets"]) or b""
    brut_fin = _fichier_sortie(serveur, ssh, ident, "fin.json", FIN_MAX_OCTETS)
    fin = _lire_fin(brut_fin, tache, base) if brut_fin is not None else {}
    branche = None
    if fin.get("commits", 0) > 0:
        paquet = _fichier_sortie(serveur, ssh, ident, "resultat.bundle", LIMITES_AGENT["paquet_octets"])
        if not paquet:
            raise RefusRecuperation("Le paquet résultat est absent alors que fin.json annonce des commits.")
        _verifier_et_recuperer_paquet(Path(projet), paquet, tache, base, git)
        branche = f"agent/{tache}"
    return {"flux": flux, "fin": fin, "branche": branche, "etat": lu["etat"], "raison": lu.get("raison", "")}


# ---------------------------------------------------------------- index

def taches_agent_actives(dossier=plateforme_acces.DOSSIER):
    """Fiches des tâches d'agent en attente ou en cours, lues dans l'index seul (aucune connexion) : pour le rattachement
    après un redémarrage et pour la bascule entre lieux. `[{"id": ..., **fiche}]`."""
    return [{"id": i, **f} for i, f in sorted(st.Index(dossier).lire().items())
            if f.get("type") == "agent" and f.get("etat") in ("en_attente", "en_cours")]
