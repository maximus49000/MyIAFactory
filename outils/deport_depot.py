"""Exécution déportée : aperçu, validation et envoi du workflow GitHub Actions du projet.

Rien n'est jamais envoyé sans la validation explicite du Directeur : `apercu` ne fait que lire ; `appliquer` reçoit
l'empreinte que le Directeur a vue et refuse si le contenu voulu a changé depuis. L'envoi se fait sur la branche de
travail `deport/workflow` seulement (jamais la branche courante ni la principale) depuis un dossier de travail git
temporaire : la branche courante et le dossier du projet restent intacts. Toute commande git passe par
`moteur.git_sur` (une à la fois par dépôt).

Reste compatible Python 3.9 : le code déporté est aussi lancé par les agents.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_github  # noqa: E402
from bureau.deport_types import catalogue_du_projet, racine_du_projet  # noqa: E402
from moteur import git_sur  # noqa: E402

BRANCHE = "deport/workflow"
MARQUEUR = "[MyIAFactory-deport] "   # début du message de TOUS nos commits : la branche distante est alors la nôtre
DELAI_GIT_S = 120
DELAI_PUSH_S = 300
_NOM_DEFAUT = "myiafactory"


def nom_fichier(texte):
    """Un nom de fichier sûr (minuscules, chiffres, tirets) tiré du nom du dossier du projet."""
    ascii_ = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-") or _NOM_DEFAUT


def _executer(argv, cwd, delai_s):
    env = {k: v for k, v in os.environ.items()}
    env["GIT_TERMINAL_PROMPT"] = "0"
    fini = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=delai_s, stdin=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return fini.returncode, fini.stdout if fini.returncode == 0 or fini.stdout else fini.stderr


def _racine_du_depot(dossier):
    """Le plus proche dossier (le projet, puis ses parents) qui contient `.git` ; sinon le dossier du projet."""
    dossier = Path(dossier).resolve()
    for d in (dossier, *dossier.parents):
        if (d / ".git").exists():
            return d
    return dossier


def _nom_du_projet(dossier):
    """Le nom du projet : celui du plus proche dossier qui contient `.factory/` (un agent peut donner un
    sous-dossier, ex. `app/`), sinon du dossier donné."""
    return Path(racine_du_projet(Path(dossier).resolve())).name


def _texte(sortie):
    return sortie.decode("utf-8", "replace") if isinstance(sortie, bytes) else str(sortie or "")


def _amont(git, courante):
    """`(nom, sha)` du sommet distant de la branche courante : son amont suivi (`@{u}`), sinon `origin/<courante>` ;
    `(None, None)` si la branche n'existe pas sur le dépôt distant. `git(*args) -> (code, sortie)`."""
    if not courante or courante == "HEAD":
        return None, None
    code, sortie = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    nom = _texte(sortie).strip() if code == 0 else ""
    for candidat in ([nom] if "/" in nom else []) + ["origin/" + courante]:
        code, sortie = git("rev-parse", "--verify", "-q", "refs/remotes/%s^{commit}" % candidat)
        sha = _texte(sortie).strip() if code == 0 else ""
        if sha:
            return candidat, sha
    return None, None


def _msg_sans_amont(courante):
    return ("La branche « %s » n'est pas sur le dépôt distant : pousse ta branche d'abord (git push -u origin %s), "
            "puis relance. Le workflow part du sommet distant de ta branche, jamais de tes commits locaux."
            % (courante, courante))


def _note_non_pousses(nombre, amont):
    if not nombre:
        return ""
    return ("%d commit%s local%s non poussé%s ne %s PAS inclus : la branche « %s » part de %s."
            % (nombre, "s" if nombre > 1 else "", "aux" if nombre > 1 else "", "s" if nombre > 1 else "",
               "sont" if nombre > 1 else "est", BRANCHE, amont))


def _base_distante(dossier, executer=None):
    """`{"amont", "non_pousses", "note"}` pour l'aperçu : la base distante de la branche de travail et les commits
    locaux qu'elle n'inclura pas. Lecture seule ; ne lève jamais."""
    executer = executer or _executer
    racine = _racine_du_depot(dossier)

    def git(*args):
        try:
            return executer(["git", *args], str(racine), DELAI_GIT_S)
        except (OSError, subprocess.TimeoutExpired):
            return 127, ""
    code, sortie = git("rev-parse", "--abbrev-ref", "HEAD")
    courante = _texte(sortie).strip() if code == 0 else ""
    if not courante:
        return {"amont": None, "non_pousses": 0, "note": ""}
    amont, sha = _amont(git, courante)
    if amont is None:
        return {"amont": None, "non_pousses": 0, "note": _msg_sans_amont(courante)}
    code, sortie = git("rev-list", "--count", sha + "..HEAD")
    try:
        nombre = int(_texte(sortie).strip()) if code == 0 else 0
    except ValueError:
        nombre = 0
    return {"amont": amont, "non_pousses": nombre, "note": _note_non_pousses(nombre, amont)}


def _voulu(dossier, reglages):
    """(actions sur GitHub, nom du projet, nom du fichier, texte voulu ou None sans action) ; ValueError si une
    commande manque."""
    deport = (reglages or {}).get("deport") or {}
    lieux = deport.get("lieux") or {}
    catalogue = catalogue_du_projet(racine_du_projet(dossier))[1]
    actions = [a for a in catalogue if lieux.get(a) == "github"]
    nom = _nom_du_projet(dossier)
    fichier = nom_fichier(nom)
    if not actions:
        return actions, nom, fichier, None
    texte = workflow_github.generer(nom, actions, deport.get("commandes") or {}, deport.get("charge_heure", "03:00"),
                                     catalogue)
    return actions, nom, fichier, texte


def _empreinte_de(texte):
    return texte.split("\n", 1)[0].rpartition("=")[2]


def _chemin(racine, fichier):
    return Path(racine) / ".github" / "workflows" / (fichier + ".yml")


def apercu(dossier, reglages, executer=None):
    """Ce que le déport écrirait : `{"etat", "diff", "chemin", "empreinte", "amont", "non_pousses", "note"}`, sans
    rien écrire.

    `etat` : absent, a_jour, a_valider, modifie_a_la_main, ou aucune_action (rien n'est déporté sur GitHub).
    `amont` : la branche distante dont partira `deport/workflow` (None : la branche n'est pas poussée, l'envoi sera
    refusé) ; `non_pousses` : les commits locaux qui ne seront PAS envoyés ; `note` : la phrase à afficher.
    Lève ValueError (message en français) si une commande manque.
    """
    racine = _racine_du_depot(dossier)
    _, _, fichier, texte = _voulu(dossier, reglages)
    chemin = _chemin(racine, fichier)
    if texte is None:
        return {"etat": "aucune_action", "diff": "", "chemin": str(chemin), "empreinte": "", "amont": None,
                "non_pousses": 0, "note": ""}
    etat = workflow_github.etat_du_fichier(chemin, texte)
    ancien = chemin.read_bytes().decode("utf-8", errors="replace") if chemin.exists() else ""
    return dict({"etat": etat, "diff": workflow_github.diff(ancien, texte), "chemin": str(chemin),
                 "empreinte": _empreinte_de(texte)}, **_base_distante(dossier, executer))


def _refus(message, **autres):
    return dict({"ok": False, "message": message}, **autres)


def appliquer(dossier, empreinte, reglages, executer=None):
    """Écrit le workflow sur la branche `deport/workflow` et pousse cette branche seule.

    `executer(argv, cwd, delai_s) -> (code, sortie)` (défaut : sous-processus réel). Rend `{"ok", "message", ...}` ;
    un refus n'écrit rien. Le dossier du projet et sa branche courante ne sont jamais touchés.
    """
    executer = executer or _executer
    try:
        _, _, fichier, texte = _voulu(dossier, reglages)
    except ValueError as e:
        return _refus(str(e))
    if texte is None:
        return _refus("Aucune action n'est déportée sur GitHub : rien à envoyer.")
    if not empreinte or empreinte != _empreinte_de(texte):
        return _refus("Le workflow voulu n'est plus à jour : l'aperçu validé est périmé. Rouvrez l'aperçu, relisez-le "
                      "puis validez à nouveau.")
    racine = _racine_du_depot(dossier)

    def git(*args, cwd=None, delai=DELAI_GIT_S):
        dans = str(cwd or racine)
        try:
            return git_sur.executer(lambda argv: executer(argv, dans, delai), racine, ["git", *args])
        except (subprocess.TimeoutExpired, TimeoutError):
            return 124, "délai dépassé (%d s) : git %s" % (delai, args[0])
        except OSError as e:
            return 127, "git n'a pas pu être lancé : %s" % e

    def lu(sortie):
        brut = sortie.decode("utf-8", "replace") if isinstance(sortie, bytes) else str(sortie or "")
        return re.sub(r"://[^/@\s]+@", "://***@", brut).strip()[:300]

    with git_sur.verrou(racine):
        code, sortie = git("rev-parse", "--abbrev-ref", "HEAD")
        if code != 0:
            return _refus("Le dossier du projet n'est pas un dépôt git utilisable : %s" % lu(sortie))
        courante = lu(sortie)
        if courante == BRANCHE:
            return _refus("La branche « %s » est déjà la branche courante : revenez sur la branche principale." % BRANCHE)
        if courante == "HEAD":
            return _refus("Tête détachée : placez-vous sur votre branche de travail, poussée, puis relancez.")
        # la base est le sommet DISTANT de la branche courante : un commit local non poussé (travail d'un agent,
        # peut-être un secret) ne part jamais sur GitHub ; le Directeur n'a validé que le diff du workflow
        amont, base = _amont(git, courante)
        if amont is None:
            return _refus(_msg_sans_amont(courante))
        relatif = ".github/workflows/%s.yml" % fichier
        code, sortie = git("show", "HEAD:" + relatif)
        if code == 0:      # le workflow tel qu'il est dans la branche LOCALE (fusionné mais peut-être pas poussé)
            etat_local = workflow_github.etat_du_contenu(
                sortie if isinstance(sortie, bytes) else str(sortie).encode("utf-8"), texte)
            if etat_local == "a_jour":
                return {"ok": True, "etat": "a_jour", "message": "Le workflow est déjà à jour dans votre branche : "
                        "rien à envoyer (poussez-la si ce n'est pas encore fait)."}
            if etat_local == "modifie_a_la_main":
                return _refus("Le fichier %s a été modifié à la main : MyIAFactory ne l'écrase pas. Reprenez-le ou "
                              "supprimez-le, puis relancez." % relatif)
        git("worktree", "prune")
        temporaire = tempfile.mkdtemp(prefix="deport-")
        travail = os.path.join(temporaire, "copie")
        cree = False
        try:
            code, sortie = git("worktree", "add", "-q", "--detach", travail, base)
            if code != 0:
                return _refus("Impossible de préparer la branche de travail : %s" % lu(sortie))
            cree = True
            chemin = _chemin(travail, fichier)
            etat = workflow_github.etat_du_fichier(chemin, texte)
            # la même règle que l'aperçu : la copie de l'arbre de travail compte aussi (modification non commitée)
            copie = _chemin(racine, fichier)
            etat_copie = workflow_github.etat_du_fichier(copie, texte)
            if etat_copie == "modifie_a_la_main":
                etat = etat_copie
            elif etat_copie not in ("absent", "a_jour"):
                dans_head = chemin.read_bytes() if chemin.exists() else None
                if dans_head != copie.read_bytes():
                    return _refus("Le fichier %s a une modification non commitée dans le dossier du projet : "
                                  "commitez-la ou annulez-la, puis relancez." % copie.relative_to(racine).as_posix())
            if etat == "modifie_a_la_main":
                return _refus("Le fichier %s a été modifié à la main : MyIAFactory ne l'écrase pas. Reprenez-le ou "
                              "supprimez-le, puis relancez." % chemin.relative_to(travail).as_posix())
            if etat == "a_jour":
                return {"ok": True, "etat": "a_jour", "message": "Le workflow est déjà à jour : rien à envoyer."}
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(texte.encode("utf-8"))
            relatif = chemin.relative_to(travail).as_posix()
            for args, quoi in ((("add", "--", relatif), "préparation"),
                               (("commit", "-q", "-m", MARQUEUR + "Déport : workflow GitHub Actions des actions déportées",
                                 "--", relatif), "commit")):
                code, sortie = git(*args, cwd=travail)
                if code != 0:
                    return _refus("Échec (%s) : %s" % (quoi, lu(sortie)))
            ref = "refs/heads/" + BRANCHE
            code, sortie = git("ls-remote", "origin", ref, cwd=travail)
            if code != 0:
                return _refus("Impossible de lire la branche « %s » sur origin : %s" % (BRANCHE, lu(sortie)))
            vu = lu(sortie).split()
            pousser = ["push"]
            if vu:
                sha = vu[0]
                code, sortie = git("fetch", "-q", "origin", ref, cwd=travail, delai=DELAI_PUSH_S)
                if code != 0:
                    return _refus("Impossible de lire la branche « %s » sur origin : %s" % (BRANCHE, lu(sortie)))
                code, sortie = git("log", "-1", "--format=%s", "FETCH_HEAD", cwd=travail)
                if code != 0 or not lu(sortie).startswith(MARQUEUR):
                    return _refus("La branche « %s » existe déjà et n'a pas été créée par MyIAFactory : renommez-la "
                                  "ou supprimez-la." % BRANCHE)
                pousser.append("--force-with-lease=%s:%s" % (ref, sha))
            code, sortie = git(*(pousser + ["origin", "HEAD:" + ref]), cwd=travail, delai=DELAI_PUSH_S)
            if code != 0:
                return _refus("Échec du push de la branche « %s » : %s" % (BRANCHE, lu(sortie)))
            return {"ok": True, "etat": etat, "branche": BRANCHE, "base": amont,
                    "message": "Workflow envoyé sur la branche « %s » (partie de %s) : ouvrez-la sur GitHub pour la "
                               "fusionner." % (BRANCHE, amont)}
        finally:
            if cree:
                git("worktree", "remove", "--force", travail)
            shutil.rmtree(temporaire, ignore_errors=True)
            git("worktree", "prune")
