"""La mémoire à trois étages : la skill, le genre du projet, le projet.

Les deux premiers sont des fichiers Markdown de ce dépôt, `memoire/skill.md` et `memoire/genres/<id>.md`.
Une leçon n'y entre qu'après `git pull --rebase`, sans mot interdit du projet ; elle est commitée et poussée.

Format d'un fichier :

    # <titre>
    Domaine : …            (un genre seulement : en tête, sa description)
    Livrable : …
    Outils : …

    ## <id> — <titre court>
    Rôles : <r1>, <r2> | tous
    Date : AAAA-MM-JJ

    <le texte de la leçon>
"""
import os
import re
import subprocess
import unicodedata
from datetime import date
from pathlib import Path

MOTIF_GENRE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")
_SECTION = re.compile(r"^## (\S+) — (.*)$")
_TETE = re.compile(r"^(Domaine|Livrable|Outils)\s*:\s*(.*?)\s*$")
DELAI_GIT_S = 120


def _lire(chemin):
    chemin = Path(chemin)
    return chemin.read_text(encoding="utf-8-sig") if chemin.is_file() else ""


def analyser(texte):
    """Un fichier de mémoire : {titre, domaine, livrable, outils, lecons: [{id, titre, roles, date, texte}]}."""
    sortie = {"titre": "", "domaine": None, "livrable": None, "outils": None, "lecons": []}
    courante, corps = None, []

    def clore():
        if courante is not None:
            courante["texte"] = "\n".join(corps).strip()
            sortie["lecons"].append(courante)

    for ligne in texte.splitlines():
        m = _SECTION.match(ligne)
        if m:
            clore()
            courante, corps = {"id": m.group(1), "titre": m.group(2).strip(), "roles": ["tous"], "date": None,
                               "texte": ""}, []
            continue
        if courante is None:
            if ligne.startswith("# ") and not sortie["titre"]:
                sortie["titre"] = ligne[2:].strip()
            else:
                t = _TETE.match(ligne)
                if t:
                    sortie[t.group(1).lower()] = t.group(2)
            continue
        if not corps and ligne.startswith("Rôles :"):
            valeur = ligne.split(":", 1)[1].strip()
            courante["roles"] = ["tous"] if valeur == "tous" else [r.strip() for r in valeur.split(",") if r.strip()]
        elif not corps and ligne.startswith("Date :"):
            courante["date"] = ligne.split(":", 1)[1].strip() or None
        elif corps or ligne.strip():
            corps.append(ligne)
    clore()
    return sortie


def _chemin_genre(dossier, genre):
    return Path(dossier) / "genres" / f"{genre}.md"


def lire(dossier, genre, role):
    """Les leçons de la skill et du genre du projet qui touchent ce rôle (ou « tous »). Un genre nul, inconnu
    ou mal écrit ne donne rien ; jamais le fichier d'un autre genre."""
    def pour(lecons):
        return [x for x in lecons if "tous" in x["roles"] or role in x["roles"]]

    sortie = {"skill": pour(analyser(_lire(Path(dossier) / "skill.md"))["lecons"]), "genre": []}
    if isinstance(genre, str) and MOTIF_GENRE.match(genre):
        sortie["genre"] = pour(analyser(_lire(_chemin_genre(dossier, genre)))["lecons"])
    return sortie


def genres(dossier):
    """Les genres connus, avec leur description : [{id, domaine, livrable, outils}]."""
    sortie = []
    for chemin in sorted((Path(dossier) / "genres").glob("*.md")):
        if not MOTIF_GENRE.match(chemin.stem):
            continue   # LISEZMOI.md et tout ce qui n'est pas un genre
        a = analyser(_lire(chemin))
        sortie.append({"id": chemin.stem, "domaine": a["domaine"], "livrable": a["livrable"], "outils": a["outils"]})
    return sortie


def normaliser_mot(texte):
    """Minuscules, sans accents ; tirets et apostrophes deviennent des espaces ; espaces réduits."""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[-'’`´‑–—_]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def mots_trouves(texte, mots_interdits):
    """Les mots interdits (tels que le projet les écrit) que le texte contient, comparés sans casse ni accents."""
    plat = f" {normaliser_mot(texte)} "
    return [m for m in mots_interdits if normaliser_mot(m) and normaliser_mot(m) in plat]


def executer_git(args, cwd):
    """(code, sortie) d'une commande git. Jamais de question posée au clavier."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_EDITOR": "true"}
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, timeout=DELAI_GIT_S, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"git n'a pas pu s'exécuter : {e}"
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace").strip()


def _ecrire_et_pousser(dossier, chemin, nouveau_texte, mots_interdits, texte_controle, message_commit, git):
    """Met à jour le dépôt, ajoute le contenu, commite et pousse. Tout échec remet le fichier tel quel."""
    dossier, chemin = Path(dossier), Path(chemin)
    trouves = mots_trouves(texte_controle, mots_interdits)
    if trouves:
        return False, ("Arrêt : le texte contient un mot interdit du projet (« " + "», « ".join(trouves)
                       + " »). Rien n'a été écrit ; réécrire la leçon en termes généraux.")
    code, sortie = git(["pull", "--rebase"], dossier)
    if code != 0:
        git(["rebase", "--abort"], dossier)
        return False, f"Arrêt : « git pull --rebase » a échoué (conflit ou dépôt injoignable). Rien n'a été écrit. {sortie}"[:400]
    avant = _lire(chemin) if chemin.is_file() else None
    commite = False

    def defaire():
        if commite:
            git(["reset", "-q", "HEAD~1"], dossier)
        if avant is None:
            chemin.unlink(missing_ok=True)
        else:
            chemin.write_text(avant, encoding="utf-8", newline="\n")
        git(["reset", "-q", "--", str(chemin)], dossier)

    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(nouveau_texte(avant or ""), encoding="utf-8", newline="\n")
        for etape, args in (("git add", ["add", "--", str(chemin)]), ("git commit", ["commit", "-q", "-m", message_commit]),
                            ("git push", ["push", "-q"])):
            code, sortie = git(args, dossier)
            if code != 0:
                defaire()
                return False, f"Arrêt : « {etape} » a échoué ; le fichier de mémoire est remis tel qu'il était. {sortie}"[:400]
            commite = commite or etape == "git commit"
    except OSError as e:
        defaire()
        return False, f"Arrêt : écriture impossible ({e})."
    return True, "Leçon ajoutée, commitée et poussée."


def _prochain_id(texte, prefixe):
    n = max([int(m.group(1)) for m in re.finditer(rf"^## {prefixe}(\d+) — ", texte, re.M)] or [0])
    return f"{prefixe}{n + 1}"


def ajouter(dossier, etage, genre, lecon, mots_interdits, git=executer_git):
    """Ajoute une leçon à la mémoire de la skill (`etage` « skill ») ou du genre (« genre »).
    `lecon` : {titre, texte, roles?, date?}. Rend (ok, message)."""
    if etage not in ("skill", "genre"):
        return False, "Seuls les étages « skill » et « genre » vivent dans ce dépôt."
    if etage == "genre" and not (isinstance(genre, str) and MOTIF_GENRE.match(genre)):
        return False, "Le projet n'a pas de genre : une leçon de genre ne peut pas être rangée."
    titre = " ".join(str(lecon.get("titre") or "").split())[:80]
    texte = str(lecon.get("texte") or "").strip()
    if not titre or not texte:
        return False, "Une leçon a un titre et un texte."
    roles = lecon.get("roles") or ["tous"]
    chemin = Path(dossier) / "skill.md" if etage == "skill" else _chemin_genre(dossier, genre)
    if etage == "genre" and not chemin.is_file():
        return False, f"Genre inconnu : « {genre} » (aucun fichier de mémoire)."

    def nouveau(actuel):
        i = lecon.get("id") or _prochain_id(actuel, "S" if etage == "skill" else "G")
        base = actuel if actuel.strip() else "# Mémoire de la skill\n"
        section = (f"## {i} — {titre}\nRôles : {'tous' if 'tous' in roles else ', '.join(roles)}\n"
                   f"Date : {lecon.get('date') or date.today().isoformat()}\n\n{texte}\n")
        return base.rstrip("\n") + "\n\n" + section

    return _ecrire_et_pousser(dossier, chemin, nouveau, mots_interdits,
                              "\n".join([titre, texte, " ".join(roles)]), f"Mémoire ({etage}) : {titre}", git)


def creer_genre(dossier, genre, description, mots_interdits, git=executer_git):
    """Crée le fichier d'un nouveau genre, avec sa description en tête. Rend (ok, message)."""
    if not (isinstance(genre, str) and MOTIF_GENRE.match(genre)):
        return False, "Identifiant de genre refusé (minuscules, chiffres et tirets, 40 caractères au plus)."
    description = " ".join(str(description or "").split())
    if not description:
        return False, "Un nouveau genre demande une description."
    chemin = _chemin_genre(dossier, genre)
    if chemin.is_file():
        return False, f"Le genre « {genre} » existe déjà."
    contenu = f"# Genre : {genre}\nDomaine : {description}\nLivrable : à préciser\nOutils : à préciser\n"
    return _ecrire_et_pousser(dossier, chemin, lambda _: contenu, mots_interdits, description,
                              f"Mémoire (genre) : nouveau genre {genre}", git)
