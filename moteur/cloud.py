"""Les agents cloud : des sessions cloud de Claude Code (sur l'abonnement), lancées et relevées par le moteur.

Aucune API ne rend la fin d'une session cloud, son texte ni ses tokens. Le contrat est donc le dépôt :
- **le départ** : le moteur pousse le dépôt du projet (la session clone la branche poussée) puis lance
  `claude --cloud "<message de départ>"` ; la sortie donne l'identifiant et l'adresse de la session ;
- **le retour** : le message de départ demande à l'agent de committer son rapport structuré dans
  `.factory/rapports/<tâche>.json` sur sa branche `claude/…` et de la pousser ; le moteur fait un `git fetch`, cherche ce
  fichier sur les branches `claude/…`, l'applique comme un rapport local, puis **fusionne la branche** ;
- **une suite** (l'accord de l'utilisateur) : `claude -p "<texte>" --cloud <session>`.

Toute commande passe par `executer(argv, cwd, delai_s) -> (code, sortie en octets)` (remplaçable pour les essais). Aucune
clé n'est lue ni transmise : `ANTHROPIC_API_KEY` est retirée de l'environnement, pour rester sur l'abonnement.
"""
import os
import re
import subprocess
import time
from pathlib import Path

from moteur import appel, rapport

DOSSIER_RAPPORTS = ".factory/rapports"
PREFIXE_BRANCHES = "claude/"
DELAI_GIT_S = 120
DELAI_CLAUDE_S = 300
LONGUEUR_MAX_DEPART = 24000     # une ligne de commande Windows ne passe pas 32 767 caractères
_ADRESSE = re.compile(r"https://claude\.ai/code/[A-Za-z0-9_./-]*[A-Za-z0-9_]")
_SESSION = re.compile(r"\b(session_[A-Za-z0-9]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")


class ErreurCloud(Exception):
    """Le départ, la relève ou la fusion d'une session cloud n'a pas pu se faire."""

    def __init__(self, raison):
        super().__init__(raison)
        self.raison = raison


class ErreurDossierAApprouver(ErreurCloud):
    """Claude Code demande d'approuver le dossier du projet (« Is this a project you created or one you trust? ») et
    l'utilisateur ne l'a pas accordé : seul lui peut le faire (le moteur ne répond jamais de lui-même)."""


# La raison de `ErreurDossierAApprouver` ; la reconnaître dans l'erreur d'un départ marque la décision `session_cloud`
# (`dossier_a_approuver`) : le bureau propose alors « Approuver le dossier et relancer ».
RAISON_DOSSIER_A_APPROUVER = ("Claude Code demande d'approuver le dossier du projet pour les sessions cloud : à "
                              "approuver une fois (lancer claude dans le dossier et répondre « Yes, I trust this "
                              "folder »)")


ADRESSE_CODE = "https://claude.ai/code"
_SESSION_SEULE = re.compile(r"(session_[A-Za-z0-9]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_ADRESSE_COLLEE = re.compile(r"https://claude\.ai/code/([A-Za-z0-9_-]+)/?(?:[?#].*)?")


def lire_session(texte):
    """L'identifiant ou l'adresse claude.ai/code d'une session, collé par l'utilisateur : `{"session", "adresse"}`,
    ou `None` si ce n'est ni l'un ni l'autre."""
    t = (texte or "").strip() if isinstance(texte, str) else ""
    if len(t) > 200:
        return None
    m = _ADRESSE_COLLEE.fullmatch(t)
    ident = m.group(1) if m else (t if _SESSION_SEULE.fullmatch(t) else None)
    if not ident or ident == "session_":
        return None
    return {"session": ident, "adresse": f"{ADRESSE_CODE}/{ident}"}


def chemin_rapport(tache):
    return f"{DOSSIER_RAPPORTS}/{tache}.json"


def _executer(argv, cwd, delai_s):
    env = {k: v for k, v in os.environ.items() if k != appel.VARIABLE_CLE}
    env["GIT_TERMINAL_PROMPT"] = "0"
    fini = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=delai_s, stdin=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return fini.returncode, fini.stdout if fini.returncode == 0 or fini.stdout else fini.stderr


def _lancer(executer, argv, cwd, delai_s):
    try:
        return (executer or _executer)(argv, str(cwd), delai_s)
    except (subprocess.TimeoutExpired, TimeoutError):
        raise ErreurCloud(f"délai dépassé ({delai_s} s) : {' '.join(argv[:2])}")
    except OSError as e:
        raise ErreurCloud(f"{argv[0]} n'a pas pu être lancé : {e}")


def _texte(octets):
    return (octets or b"").decode("utf-8", "replace").strip()


def _git(executer, dossier, *args, delai_s=DELAI_GIT_S):
    return _lancer(executer, ["git", *args], dossier, delai_s)


PUSH_ESSAIS = 4
PUSH_PAUSE_S = 3
_PUSH_CONCURRENT = ("cannot lock ref", "failed to lock", "unable to lock", "incorrect old value")


def _pousser(executer, dossier):
    """`git push`, réessayé quand un autre push du même dépôt est en cours (cas réel : trois sessions cloud lancées
    ensemble, GitHub en refusait deux avec « cannot lock ref »)."""
    for essai in range(PUSH_ESSAIS):
        code, sortie = _git(executer, dossier, "push")
        if code == 0 or not any(m in _texte(sortie) for m in _PUSH_CONCURRENT) or essai == PUSH_ESSAIS - 1:
            return code, sortie
        time.sleep(PUSH_PAUSE_S * (essai + 1))
    return code, sortie


def prerequis(dossier_projet, *, executer=None, trouver=appel.trouver_claude):
    """`None` si le cloud est possible (le projet est sur GitHub, `claude` est là), sinon la raison, en français."""
    if not trouver():
        return "la commande claude n'est pas installée"
    try:
        code, sortie = _git(executer, dossier_projet, "remote", "get-url", "origin", delai_s=30)
    except ErreurCloud:
        return "git n'est pas utilisable"
    if code != 0 or "github.com" not in _texte(sortie):
        return "le projet n'est pas sur GitHub"
    return None


DOSSIER_DEPARTS = ".factory/departs"


def _depart_en_fichier(executer, dossier_projet, depart):
    """Écrit le message de départ dans `.factory/departs/depart-<empreinte>.md` du projet, le commite seul et rend la
    consigne courte qui le remplace en ligne de commande. `ErreurCloud` si le fichier ne peut pas être commité."""
    import hashlib
    nom = f"depart-{hashlib.sha256(depart.encode('utf-8')).hexdigest()[:12]}.md"
    relatif = f"{DOSSIER_DEPARTS}/{nom}"
    chemin = Path(dossier_projet) / DOSSIER_DEPARTS / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(depart, encoding="utf-8", newline="\n")
    code, sortie = _git(executer, dossier_projet, "add", "--", relatif)
    if code == 0:
        code, sortie = _git(executer, dossier_projet, "commit", "-q", "-m", "Départ d'une session cloud (message long)",
                            "--", relatif)
    if code != 0 and "nothing to commit" not in _texte(sortie) and "rien à valider" not in _texte(sortie):
        raise ErreurCloud("le message de départ, trop long, n'a pas pu être mis dans le dépôt : " + _texte(sortie)[:200])
    return (f"Ton message de départ complet est dans le fichier `{relatif}` de ce dépôt : lis-le entièrement maintenant, "
            "puis fais exactement ce qu'il demande (consignes, tâche, rapport attendu).")


def lancer_session(depart, *, dossier_projet, modele, executer=None, trouver=appel.trouver_claude, terminal=None,
                   approuver_dossier=False):
    """Pousse le dépôt puis lance la session cloud. Rend `{"session", "adresse"}`. Lève `ErreurCloud`.

    `claude --cloud` exige un terminal : sans `executer` (le vrai moteur), la commande est lancée dans le faux terminal
    (`terminal`, par défaut `pseudo_terminal.lancer`) quand le poste en a un ; `approuver_dossier` n'est vrai que si
    l'utilisateur a accordé ce dossier (sinon `ErreurDossierAApprouver`). Sans faux terminal : la commande directe, qui
    échoue avec une raison claire (la démarche manuelle prend alors le relais)."""
    m = (modele or "").strip().lower()
    if "fable" not in m and m in appel.MODELES and len(depart) > LONGUEUR_MAX_DEPART:
        # Trop long pour la ligne de commande (essai réel : la consigne complète du métier et ses leçons d'un agent
        # polyvalent) : le message va dans un fichier du dépôt, poussé avec lui ; la session reçoit l'ordre de le lire.
        depart = _depart_en_fichier(executer, dossier_projet, depart)
    if "fable" in m or m not in appel.MODELES:
        raise ErreurCloud("le moteur ne choisit jamais Fable" if "fable" in m else f"modèle inconnu : {modele}")
    claude = trouver()
    if not claude:
        raise ErreurCloud("la commande claude n'est pas installée")
    code, sortie = _pousser(executer, dossier_projet)
    if code != 0:
        raise ErreurCloud("le dépôt n'a pas pu être poussé : " + _texte(sortie)[:200])
    argv = [claude, "--cloud", depart, "--model", m]
    if terminal is not None or (executer is None and _faux_terminal_possible()):
        return _lancer_dans_le_faux_terminal(argv, dossier_projet, terminal, approuver_dossier)
    code, sortie = _lancer(executer, argv, dossier_projet, DELAI_CLAUDE_S)
    texte = _texte(sortie)
    if code != 0:
        raise ErreurCloud(_sans_terminal(texte) or f"claude --cloud a rendu le code {code} : {texte[:200]}")
    adresse = _ADRESSE.search(texte)
    session = _SESSION.search(texte) or (re.search(r"([A-Za-z0-9_-]+)$", adresse.group(0)) if adresse else None)
    if not session:
        raise ErreurCloud("la sortie de claude --cloud ne donne pas la session : " + texte[:200])
    return {"session": session.group(1), "adresse": adresse.group(0) if adresse else None}


def _faux_terminal_possible():
    from moteur import pseudo_terminal as pt
    return pt.disponible()


def _lancer_dans_le_faux_terminal(argv, dossier_projet, terminal, approuver_dossier):
    from moteur import pseudo_terminal as pt
    r = essai_pseudo_terminal(argv, dossier_projet, env=pt.environnement_sans(appel.VARIABLE_CLE),
                              delai_s=DELAI_CLAUDE_S, lancer=terminal, approuver_dossier=approuver_dossier)
    if r["issue"] == "session":
        return {"session": r["session"], "adresse": r["adresse"]}
    if r.get("dossier_a_approuver"):
        raise ErreurDossierAApprouver(RAISON_DOSSIER_A_APPROUVER)
    raise ErreurCloud((r["raison"] or "pas de session créée") + " (faux terminal)")


def envoyer_suite(session, texte, *, executer=None, dossier_projet=".", trouver=appel.trouver_claude):
    """Envoie une suite (l'accord de l'utilisateur) à la même session : `claude -p "<texte>" --cloud <session>`."""
    claude = trouver()
    if not claude:
        raise ErreurCloud("la commande claude n'est pas installée")
    code, sortie = _lancer(executer, [claude, "-p", texte, "--cloud", session], dossier_projet, DELAI_CLAUDE_S)
    if code != 0:
        raise ErreurCloud(_sans_terminal(_texte(sortie)) or f"la suite n'a pas pu être envoyée : {_texte(sortie)[:200]}")


SANS_TERMINAL = ("claude --cloud exige un terminal interactif : le moteur, qui tourne sans terminal, ne peut pas "
                 "créer ni joindre la session lui-même")


def _sans_terminal(texte):
    """La raison claire quand `claude` refuse `--cloud` hors d'un terminal (Claude Code 2.1.321 : « --cloud requires an
    interactive terminal »), sinon `None`."""
    return SANS_TERMINAL if "interactive terminal" in (texte or "") else None


# --- L'essai du faux terminal (`moteur.pseudo_terminal`) : `claude --cloud` lancé dans une pseudo-console invisible.
# Essai réel du 2026-11-12 (Claude Code 2.1.321) : la commande accepte la pseudo-console, mais s'arrête d'abord sur
# l'accueil d'une première utilisation (thème, notes de sécurité), puis sur l'approbation du dossier (« Is this a
# project you created or one you trust? ») ; aucune session n'est créée sans ces réponses. Pas branché dans
# `lancer_session` : voir docs/superpowers/specs/2026-11-12-sessions-cloud-design.md et `outils/essai_session_cloud.py`.

ECRANS_SANS_RISQUE = (("Choose the text style", "\r"),          # le thème proposé par défaut
                      ("Press Enter to continue", "\r"),        # les notes de sécurité, à lire seulement
                      # « Claude in Chrome extension detected » : Échap garde les outils navigateur coupés (le choix
                      # proposé par défaut, le plus prudent ; un agent n'utilise jamais le navigateur du Directeur)
                      ("Esc to keep browser tools off", "\x1b"))
DEMANDES_A_L_UTILISATEUR = (("trust this folder", "Claude Code demande d'approuver le dossier du projet (« Is this a "
                                                  "project you created or one you trust? »)"),
                            ("Enter to confirm", "Claude Code attend un choix"),
                            ("/login", "Claude Code demande de se connecter"))
GRACE_APRES_ADRESSE_S = 3
PASSES_STABLES = 25            # l'écran n'a pas changé pendant ce nombre de passages (0,1 s chacun) : il est complet.
# Essai réel : une flèche envoyée moins d'une seconde après le menu « trust this folder » revenait sur « No, exit » ;
# après 2 s, elle tient.
MARQUE_DOSSIER = "trust this folder"
OUI_DOSSIER = "Yes, I trust this folder"
BAS = "\x1b[B"                  # la flèche vers le bas : « No, exit » est proposé d'abord


TITRE_DOSSIER = "Quick safety check"
BAS_MAX = 4                     # flèches vers le bas au plus : jamais Entrée tant que « Yes » n'est pas choisi


def _oui_est_choisi(texte):
    """Sur l'écran d'approbation, la dernière ligne marquée par ❯ (après le dernier « Quick safety check », sinon dans
    tout le texte) est-elle « Yes » ? Essai réel : les redessins du menu n'ajoutent que les deux lignes d'options, sans
    nouveau « Enter to confirm » ; c'est la dernière ligne marquée qui dit le choix."""
    i = texte.rfind(TITRE_DOSSIER)
    apres = texte[i:] if i >= 0 else texte
    marquees = [x.strip() for x in apres.split("\n") if x.strip().startswith("❯")]
    return bool(marquees) and OUI_DOSSIER in marquees[-1]


def essai_pseudo_terminal(argv, cwd, *, env=None, delai_s=180, lancer=None, approuver_dossier=False):
    """Lance `argv` (`claude --cloud …`) dans la pseudo-console : répond seulement aux écrans sans risque
    (`ECRANS_SANS_RISQUE`, une fois chacun), s'arrête sur une demande à l'utilisateur, ou peu après l'adresse de la
    session. Rend `{"issue": "session" | "demande" | "fini" | "delai", "session", "adresse", "raison", "ecran",
    "dossier_a_approuver"}` (`ecran` : la fin de la sortie nettoyée). Lève `ErreurCloud` si la pseudo-console manque.

    `approuver_dossier` (vrai seulement si l'utilisateur a accordé CE dossier) : à l'écran d'approbation du dossier,
    une flèche vers le bas (réessayée sur chaque écran stable, `BAS_MAX` fois au plus) puis Entrée, et Entrée seulement
    si « Yes, I trust this folder » est bien la ligne choisie.
    Sinon cet écran est une demande à l'utilisateur et rien n'est tapé."""
    from moteur import pseudo_terminal as pt
    lancer = lancer or pt.lancer
    faits, vu = set(), {"adresse": None, "demande": None}
    suivi = {"texte": None, "stables": 0, "bas": 0}
    debut = time.monotonic()

    def apres_les_reponses(texte):
        """Ce qui s'affiche après le dernier écran déjà répondu."""
        marques = [m for m in (*(m for m, _ in ECRANS_SANS_RISQUE), OUI_DOSSIER) if m in faits]
        coupe = max((texte.rfind(m) + len(m) for m in marques), default=0)
        return texte[coupe:]

    def repondre(texte):
        suivi["stables"] = suivi["stables"] + 1 if texte == suivi["texte"] else 0
        suivi["texte"] = texte
        for marque, touches in ECRANS_SANS_RISQUE:
            if marque not in faits and marque in apres_les_reponses(texte):
                faits.add(marque)
                return touches
        if (approuver_dossier and OUI_DOSSIER not in faits and MARQUE_DOSSIER in apres_les_reponses(texte)
                and suivi["stables"] >= PASSES_STABLES):
            # Essai réel : une flèche envoyée trop tôt est perdue (le menu redessine « ❯ Yes » puis revient sur
            # « ❯ No, exit ») : sur chaque écran redevenu stable, Entrée si « Yes » est choisi, sinon une nouvelle
            # flèche, BAS_MAX fois au plus. Jamais Entrée sur « No ».
            if _oui_est_choisi(texte):
                faits.add(OUI_DOSSIER)
                return "\r"
            if suivi["bas"] < BAS_MAX:
                suivi["bas"] += 1
                suivi["stables"] = 0
                return BAS
        return None

    def arret(texte):
        reste = apres_les_reponses(texte)
        adresse = _ADRESSE.search(reste)
        if adresse and vu["adresse"] is None:
            vu["adresse"] = (adresse.group(0), time.monotonic())
        if vu["adresse"]:
            return time.monotonic() - vu["adresse"][1] >= GRACE_APRES_ADRESSE_S
        if any(m not in faits and m in reste for m, _ in ECRANS_SANS_RISQUE):
            return False
        if approuver_dossier and OUI_DOSSIER not in faits and MARQUE_DOSSIER in reste:
            return False                  # l'approbation accordée est en cours : le délai tranche si elle échoue
        vu["demande"] = next((raison for marque, raison in DEMANDES_A_L_UTILISATEUR if marque in reste), None)
        return vu["demande"] is not None

    try:
        r = lancer(argv, cwd=str(cwd), delai_s=delai_s, env=env, arret=arret, repondre=repondre)
    except pt.PseudoTerminalIndisponible as e:
        raise ErreurCloud(f"pas de faux terminal sur ce poste : {e}")
    except OSError as e:
        raise ErreurCloud(f"{argv[0]} n'a pas pu être lancé dans le faux terminal : {e}")
    ecran = r.texte[-1500:]
    if vu["adresse"] is None and r.fini:       # la commande a rendu la main avant que le suivi voie l'adresse
        adresse = _ADRESSE.search(apres_les_reponses(r.texte))
        if adresse:
            vu["adresse"] = (adresse.group(0), 0)
    if vu["adresse"]:
        adresse = vu["adresse"][0]
        return {"issue": "session", "session": re.search(r"([A-Za-z0-9_-]+)$", adresse).group(1), "adresse": adresse,
                "raison": None, "ecran": ecran, "dossier_a_approuver": False}
    if vu["demande"]:
        return {"issue": "demande", "session": None, "adresse": None, "raison": vu["demande"], "ecran": ecran,
                "dossier_a_approuver": MARQUE_DOSSIER in apres_les_reponses(r.texte)}
    if r.fini:
        return {"issue": "fini", "session": None, "adresse": None, "ecran": ecran, "dossier_a_approuver": False,
                "raison": _sans_terminal(r.texte) or f"claude a rendu le code {r.code}"}
    return {"issue": "delai", "session": None, "adresse": None, "ecran": ecran, "dossier_a_approuver": False,
            "raison": f"rien d'exploitable après {round(time.monotonic() - debut)} s" + _fin_d_ecran(r.texte)}


def _fin_d_ecran(texte, n=3):
    """« ; dernier écran : … » (les dernières lignes non vides, sans les traits) : de quoi savoir où il a attendu."""
    lignes = [x.strip() for x in texte.splitlines() if x.strip() and set(x.strip()) - set("─━-")]
    return ("; dernier écran : " + " / ".join(lignes[-n:]))[:300] if lignes else ""


def chercher_rapports(dossier_projet, taches, *, executer=None):
    """Après `git fetch`, pour chaque tâche dont `.factory/rapports/<tâche>.json` existe sur une branche `claude/…`,
    `(branche, rapport)`. Un rapport illisible est ignoré (la session peut encore le réécrire)."""
    if not taches:
        return {}
    code, sortie = _git(executer, dossier_projet, "fetch", "--prune", "origin")
    if code != 0:
        raise ErreurCloud("git fetch a échoué : " + _texte(sortie)[:200])
    code, sortie = _git(executer, dossier_projet, "for-each-ref", "--format=%(refname:short)",
                        f"refs/remotes/origin/{PREFIXE_BRANCHES}")
    branches = [b for b in _texte(sortie).splitlines() if b.strip()] if code == 0 else []
    trouves = {}
    for tache in taches:
        for branche in branches:
            code, contenu = _git(executer, dossier_projet, "show", f"{branche}:{chemin_rapport(tache)}", delai_s=30)
            if code != 0:
                continue
            try:
                trouves[tache] = (branche.split("/", 1)[1], rapport.lire(_texte(contenu)))
                break
            except rapport.RapportIllisible:
                continue
    return trouves


def fusionner(dossier_projet, branche, *, executer=None):
    """Fusionne la branche de la session dans la branche du projet, puis pousse. `None` si c'est fait, sinon la raison
    (un conflit : la fusion est annulée, rien n'est cassé)."""
    code, sortie = _git(executer, dossier_projet, "merge", "--no-ff", "-m", f"Factory : fusion de {branche}",
                        f"origin/{branche}")
    if code != 0:
        _git(executer, dossier_projet, "merge", "--abort")
        return "conflit de fusion : " + _texte(sortie)[:200]
    code, sortie = _git(executer, dossier_projet, "push")
    if code != 0:
        return "la fusion est faite mais n'a pas pu être poussée : " + _texte(sortie)[:200]
    return None

