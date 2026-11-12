"""La mémoire à trois étages : la skill, le genre du projet, le projet.

Les deux premiers sont des fichiers Markdown de ce dépôt, `memoire/skill.md` et `memoire/genres/<id>.md`.
Une leçon n'y entre qu'après la mise à jour du dépôt (`Synchro`), sans mot interdit du projet ; seul son fichier est
commité (`git commit -- <fichier>`), puis le tout est poussé. Les autres fichiers modifiés du dépôt ne bloquent rien.

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
from dataclasses import dataclass
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
    """Minuscules, sans accents (œ et æ écrits oe et ae) ; tirets, apostrophes et séparateurs de chemin deviennent
    des espaces ; espaces réduits."""
    t = str(texte).replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[-'’`´‑–—_/\\:]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def mots_trouves(texte, mots_interdits):
    """Les mots interdits (tels que le projet les écrit) que le texte contient, comparés sans casse ni accents."""
    plat = f" {normaliser_mot(texte)} "
    return [m for m in mots_interdits if normaliser_mot(m) and normaliser_mot(m) in plat]


def executer_git(args, cwd):
    """(code, sortie) d'une commande git. Jamais de question posée au clavier."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_EDITOR": "true"}
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, timeout=DELAI_GIT_S, env=env,
                           stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"git n'a pas pu s'exécuter : {e}"
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace").strip()


@dataclass
class Resultat:
    """Ce qu'une écriture dans la mémoire a donné. `ok` : la leçon est écrite et commitée (ou, en cas d'échec, rien n'a
    été écrit) ; `publie` : le commit est aussi poussé ; `transitoire` : un échec qui peut passer tout seul (réseau,
    conflit avec le distant) et qu'on réessaie, par opposition à un refus qui demande une main (mot interdit, fichier
    modifié à la main)."""
    ok: bool
    message: str
    commite: bool = False
    publie: bool = False
    transitoire: bool = False


def _compter(git, dossier, plage):
    code, sortie = git(["rev-list", "--count", plage], dossier)
    return int(sortie) if code == 0 and sortie.strip().isdigit() else 0


class Synchro:
    """La mise à jour du dépôt avant d'écrire (faite une seule fois pour tout un lot) et la publication (une seule fois
    à la fin). Le dépôt est celui où l'on développe : ses autres fichiers modifiés ne sont jamais touchés (ni pile, ni
    reset, ni `add -A`). `git fetch` d'abord ; sans rien de neuf au distant, pas de pull ; avec du neuf et un arbre propre,
    `git pull --rebase` ; avec du neuf et d'autres fichiers modifiés, pas de rebase : le commit reste local et sa
    publication est réessayée plus tard (`republier`)."""

    def __init__(self, dossier, git=executer_git):
        self.dossier, self.git = Path(dossier), git
        self.distant_en_avance = False
        self._fait, self._echec = False, None

    def preparer(self):
        """`None` si le dépôt est prêt, sinon `(message, transitoire)` de ce qui l'en empêche."""
        if self._fait:
            return self._echec
        self._fait = True
        git, d = self.git, self.dossier
        code, sortie = git(["status", "--porcelain", "--untracked-files=no"], d)
        if code != 0:
            self._echec = (f"« git status » a échoué (le dossier n'est pas un dépôt git ?). {sortie}", False)
            return self._echec
        propre = not sortie.strip()
        code, _ = git(["fetch", "-q"], d)
        if code == 0:
            self.distant_en_avance = _compter(git, d, "HEAD..@{u}") > 0
        if self.distant_en_avance and propre:
            code, sortie = git(["pull", "--rebase", "-q"], d)
            if code != 0:
                git(["rebase", "--abort"], d)
                self._echec = (f"« git pull --rebase » a échoué (conflit ou dépôt injoignable). {sortie}", True)
                return self._echec
            self.distant_en_avance = False
        return None

    def publier(self):
        """(publié, raison) : un seul `git push`, sauf si le distant a du nouveau que l'arbre modifié empêche de prendre."""
        if self.distant_en_avance:
            return False, ("le dépôt distant a du nouveau et l'arbre a d'autres fichiers modifiés (pas de « git pull "
                           "--rebase » : ils ne sont pas touchés) : elle n'est pas publiée, nouvel essai plus tard.")
        code, sortie = self.git(["push", "-q"], self.dossier)
        if code != 0:
            return False, f"« git push » a échoué (droits ou réseau) : elle n'est pas publiée. {sortie}"
        return True, ""


def _publier(synchro, resultats):
    """Un seul push pour toutes les leçons écrites du lot ; chacune en reçoit le résultat."""
    ecrits = [r for r in resultats if r.ok and r.commite]
    if not ecrits:
        return
    publie, raison = synchro.publier()
    for r in ecrits:
        r.publie = publie
        r.message = ("Leçon ajoutée, commitée et poussée." if publie
                     else f"Leçon ajoutée et commitée dans la copie locale ; {raison}"[:400])


def republier(dossier, git=executer_git):
    """Pousse les commits de mémoire restés en local (push refusé, ou distant en avance avec un arbre modifié). Rend un
    `Resultat` : `publie` quand il ne reste rien à pousser."""
    synchro = Synchro(dossier, git)
    echec = synchro.preparer()
    if echec:
        return Resultat(False, f"Arrêt : {echec[0]}"[:400], commite=True, transitoire=echec[1])
    if _compter(git, dossier, "@{u}..HEAD") == 0:
        return Resultat(True, "Rien à publier : le dépôt distant a déjà tout.", commite=True, publie=True)
    r = Resultat(True, "", commite=True)
    _publier(synchro, [r])
    return r


def _ecrire(dossier, chemin, nouveau_texte, mots_interdits, texte_controle, message_commit, git, synchro):
    """Écrit le contenu et ne commite QUE ce fichier (`git commit -- <chemin>`) ; ne pousse pas (voir `_publier`). Tout
    échec remet le fichier tel quel et ne touche à rien d'autre."""
    dossier, chemin = Path(dossier), Path(chemin)
    trouves = mots_trouves(texte_controle, mots_interdits)
    if trouves:
        return Resultat(False, "Arrêt : le texte contient un mot interdit du projet (« " + "», « ".join(trouves)
                        + " »). Rien n'a été écrit ; réécrire la leçon en termes généraux.")
    code, sortie = git(["status", "--porcelain", "--", str(chemin)], dossier)
    if code != 0:
        return Resultat(False, f"Arrêt : « git status » a échoué (le dossier n'est pas un dépôt git ?). {sortie}"[:400])
    if sortie.strip():
        return Resultat(False, f"Arrêt : le fichier de mémoire « {chemin.name} » a des modifications non commitées "
                               "d'une autre origine : la leçon n'est pas écrite. Commitez ou annulez ces modifications, "
                               "puis validez de nouveau.")
    echec = synchro.preparer()
    if echec:
        return Resultat(False, f"Arrêt : {echec[0]} Rien n'a été écrit."[:400], transitoire=echec[1])
    avant = _lire(chemin) if chemin.is_file() else None

    def defaire():
        if avant is None:
            chemin.unlink(missing_ok=True)
        else:
            chemin.write_text(avant, encoding="utf-8", newline="\n")
        git(["reset", "-q", "--", str(chemin)], dossier)

    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(nouveau_texte(avant or ""), encoding="utf-8", newline="\n")
        for etape, args in (("git add", ["add", "--", str(chemin)]),
                            ("git commit", ["commit", "-q", "-m", message_commit, "--", str(chemin)])):
            code, sortie = git(args, dossier)
            if code != 0:
                defaire()
                return Resultat(False, f"Arrêt : « {etape} » a échoué ; le fichier de mémoire est remis tel qu'il était. {sortie}"[:400])
    except OSError as e:
        defaire()
        return Resultat(False, f"Arrêt : écriture impossible ({e}).")
    return Resultat(True, "", commite=True)


def _ecrire_et_pousser(dossier, chemin, nouveau_texte, mots_interdits, texte_controle, message_commit, git):
    """Met à jour le dépôt, ajoute le contenu, commite (ce fichier seul) et pousse. Tout échec remet le fichier tel quel,
    sauf celui de `git push` : la leçon reste écrite et commitée dans la copie locale, et le message dit qu'elle n'est
    pas publiée."""
    synchro = Synchro(dossier, git)
    r = _ecrire(dossier, chemin, nouveau_texte, mots_interdits, texte_controle, message_commit, git, synchro)
    _publier(synchro, [r])
    return r.ok, r.message


def _prochain_id(texte, prefixe):
    n = max([int(m.group(1)) for m in re.finditer(rf"^## {prefixe}(\d+) — ", texte, re.M)] or [0])
    return f"{prefixe}{n + 1}"


def ajouter(dossier, etage, genre, lecon, mots_interdits, git=executer_git):
    """Ajoute une leçon à la mémoire de la skill (`etage` « skill ») ou du genre (« genre »).
    `lecon` : {titre, texte, roles?, date?}. Rend (ok, message)."""
    r = ecrire_lecons(dossier, [(etage, genre, lecon)], mots_interdits, git)[0]
    return r.ok, r.message


def ecrire_lecons(dossier, lecons, mots_interdits, git=executer_git):
    """Ajoute plusieurs leçons `[(etage, genre, lecon)]` avec une seule synchronisation du dépôt et un seul push. Rend un
    `Resultat` par leçon, dans l'ordre : l'échec de l'une n'arrête pas les autres."""
    synchro = Synchro(dossier, git)
    resultats = []
    for etage, genre, lecon in lecons:
        plan = _plan_ajout(dossier, etage, genre, lecon)
        if isinstance(plan, Resultat):
            resultats.append(plan)
        else:
            chemin, nouveau, controle, message_commit = plan
            resultats.append(_ecrire(dossier, chemin, nouveau, mots_interdits, controle, message_commit, git, synchro))
    _publier(synchro, resultats)
    return resultats


def _plan_ajout(dossier, etage, genre, lecon):
    """Un `Resultat` d'échec, ou ce qu'il faut pour écrire : (chemin, nouveau_texte, texte_controle, message_commit)."""
    if etage not in ("skill", "genre"):
        return Resultat(False, "Seuls les étages « skill » et « genre » vivent dans ce dépôt.")
    if etage == "genre" and not (isinstance(genre, str) and MOTIF_GENRE.match(genre)):
        return Resultat(False, "Le projet n'a pas de genre : une leçon de genre ne peut pas être rangée.")
    titre = " ".join(str(lecon.get("titre") or "").split())[:80]
    texte = str(lecon.get("texte") or "").strip()
    if not titre or not texte:
        return Resultat(False, "Une leçon a un titre et un texte.")
    roles = lecon.get("roles") or ["tous"]
    chemin = Path(dossier) / "skill.md" if etage == "skill" else _chemin_genre(dossier, genre)
    if etage == "genre" and not chemin.is_file():
        return Resultat(False, f"Genre inconnu : « {genre} » (aucun fichier de mémoire).")

    def nouveau(actuel):
        i = lecon.get("id") or _prochain_id(actuel, "S" if etage == "skill" else "G")
        base = actuel if actuel.strip() else "# Mémoire de la skill\n"
        section = (f"## {i} — {titre}\nRôles : {'tous' if 'tous' in roles else ', '.join(roles)}\n"
                   f"Date : {lecon.get('date') or date.today().isoformat()}\n\n{texte}\n")
        return base.rstrip("\n") + "\n\n" + section

    return chemin, nouveau, "\n".join([titre, texte, " ".join(roles)]), f"Mémoire ({etage}) : {titre}"


def decrire_genre(dossier, genre, description, mots_interdits, git=executer_git):
    """Remplace la description (ligne « Domaine : ») d'un genre existant. Rend (ok, message)."""
    if not (isinstance(genre, str) and MOTIF_GENRE.match(genre)):
        return False, "Identifiant de genre refusé (minuscules, chiffres et tirets, 40 caractères au plus)."
    description = " ".join(str(description or "").split())
    if not description:
        return False, "Une description de genre ne peut pas être vide."
    chemin = _chemin_genre(dossier, genre)
    if not chemin.is_file():
        return False, f"Genre inconnu : « {genre} » (aucun fichier de mémoire)."

    def nouveau(actuel):
        lignes = actuel.split("\n")
        i = next((k for k, ligne in enumerate(lignes) if ligne.startswith("Domaine :")), None)
        if i is None:     # un fichier sans ligne de domaine : on l'ajoute sous le titre
            i = 1 if lignes and lignes[0].startswith("# ") else 0
            lignes.insert(i, "")
        lignes[i] = f"Domaine : {description}"
        return "\n".join(lignes)

    return _ecrire_et_pousser(dossier, chemin, nouveau, mots_interdits, description,
                              f"Mémoire (genre) : description de {genre} élargie", git)


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
    # L'identifiant aussi : il devient un nom de fichier, un titre et un message de commit publics.
    return _ecrire_et_pousser(dossier, chemin, lambda _: contenu, mots_interdits, genre + "\n" + description,
                              f"Mémoire (genre) : nouveau genre {genre}", git)
