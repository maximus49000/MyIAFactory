"""Les fiches d'agents : un fichier texte par agent, en-tête `Clé : valeur`, texte libre, puis `## Leçons`.

    Clé : dev-1
    Prénom : Léa
    Rôle : dev
    Service : dev
    Modèle : Sonnet
    Lieu : local
    Session : (cloud seulement)
    Spécialité : écrans et mise en page
    Outils : Read, Write, Edit, Bash(py:*)   (facultatif : les outils d'un agent lancé par le moteur)
    Fable : accordé par le Directeur le 2026-11-12   (facultatif : la seule façon d'avoir `Modèle : Fable`)
    Retrait : prévu   (facultatif, agent polyvalent : l'équipe a perdu une place pendant qu'il travaillait ; il finit
                       sa tâche, ne reprend rien, puis il est retiré)
    Retrait : fait    (agent retiré de l'équipe : gardé, inactif, pour l'historique de ses tâches ; jamais réactivé)

    Texte libre…

    ## Leçons
    - [à valider] dev-1:L1 : Relancer les tests après chaque changement.
    - [validée] dev-1:L0 : Nommer les écrans comme dans la maquette.
"""
import os
import re
import tempfile
from pathlib import Path

ENTETES = ("Clé", "Prénom", "Rôle", "Service", "Modèle", "Lieu", "Session", "Spécialité", "Outils", "Fable", "Retrait")
# Les outils d'un agent lancé sans fenêtre quand sa fiche n'en déclare pas : lire, écrire et modifier dans le dossier
# du projet, lancer Python (`py`, mais aussi `python`, que les agents emploient d'eux-mêmes : refusé, il bloquait toute
# production à l'essai de la phase D), créer un dossier, `git`. Jamais le mode qui contourne les autorisations.
OUTILS_PAR_DEFAUT = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(py:*)", "Bash(python:*)", "Bash(python3:*)",
                     "Bash(mkdir:*)", "Bash(git:*)"]
MODELES = ("Haiku", "Sonnet", "Opus")
# Fable n'est jamais choisi par le moteur ni par un outil : une fiche l'a seulement si le Directeur l'a accordé, pour
# cet agent seulement, et la fiche le dit (ligne `Fable :`).
ACCORD_FABLE = re.compile(r"^accordé par le Directeur le \d{4}-\d{2}-\d{2}\Z")
RETRAIT_PREVU = "prévu"
RETRAIT_FAIT = "fait"      # retiré de l'équipe : gardé, inactif, pour l'historique des tâches qu'il a réalisées
ETATS = ("à valider", "validée")
_ENTETE = re.compile(r"^(Clé|Prénom|Rôle|Service|Modèle|Lieu|Session|Spécialité|Outils|Fable|Retrait)\s*:\s*(.*?)\s*$")
_LECON = re.compile(r"^-\s*\[(à valider|validée)\]\s*(\S+)\s*:\s*(.*)$")


class FicheInvalide(Exception):
    pass


def lire_fiche(chemin):
    """Une fiche : {cle, prenom, role, service, modele, lieu, session, specialite, texte, lecons, chemin}."""
    chemin = Path(chemin)
    lignes = chemin.read_text(encoding="utf-8-sig").splitlines()
    champs, i = {}, 0
    while i < len(lignes):
        m = _ENTETE.match(lignes[i])
        if not m:
            if lignes[i].strip() == "" and champs:
                break
            if lignes[i].strip() == "":
                i += 1
                continue
            break
        champs[m.group(1)] = m.group(2)
        i += 1
    corps, lecons, dans_lecons = [], [], False
    for ligne in lignes[i:]:
        if ligne.strip() == "## Leçons":
            dans_lecons = True
            continue
        if dans_lecons:
            m = _LECON.match(ligne.strip())
            if m:
                lecons.append({"etat": m.group(1), "id": m.group(2), "texte": m.group(3)})
        else:
            corps.append(ligne)
    polyvalente = not champs.get("Rôle")
    if polyvalente:
        # Une fiche polyvalente n'a que l'identité : le métier, le service, le modèle et les leçons sont ceux de la tâche.
        for c in ("Clé", "Lieu"):
            if not champs.get(c):
                raise FicheInvalide(f"Fiche {chemin.name} : « {c} » est obligatoire.")
        for c in ("Modèle", "Service", "Fable"):
            if champs.get(c):
                raise FicheInvalide(f"Fiche {chemin.name} : un agent polyvalent n'a pas de « {c} » (le modèle suit la "
                                    "tâche, le service suit son métier).")
        if lecons:
            raise FicheInvalide(f"Fiche {chemin.name} : un agent polyvalent n'a pas de leçons (elles sont dans le "
                                "brief du métier).")
    else:
        for c in ("Clé", "Rôle", "Modèle", "Lieu"):
            if not champs.get(c):
                raise FicheInvalide(f"Fiche {chemin.name} : « {c} » est obligatoire.")
    accord = champs.get("Fable") or None
    if accord is not None and not ACCORD_FABLE.match(accord):
        raise FicheInvalide(f"Fiche {chemin.name} : « Fable » doit dire « accordé par le Directeur le AAAA-MM-JJ ».")
    if not polyvalente and champs["Modèle"] not in MODELES and not (champs["Modèle"] == "Fable" and accord):
        raise FicheInvalide(f"Fiche {chemin.name} : « Modèle » doit valoir Haiku, Sonnet ou Opus (Fable seulement "
                            "avec l'accord du Directeur, ligne « Fable : »).")
    if champs["Lieu"] not in ("local", "cloud"):
        raise FicheInvalide(f"Fiche {chemin.name} : « Lieu » doit valoir local ou cloud.")
    retrait = champs.get("Retrait") or None
    if retrait is not None and retrait not in (RETRAIT_PREVU, RETRAIT_FAIT):
        raise FicheInvalide(f"Fiche {chemin.name} : « Retrait » doit dire « {RETRAIT_PREVU} » ou « {RETRAIT_FAIT} ».")
    return {"cle": champs["Clé"], "prenom": champs.get("Prénom") or None, "role": champs.get("Rôle") or None,
            "service": champs.get("Service") or None, "modele": champs.get("Modèle") or None, "lieu": champs["Lieu"],
            "session": champs.get("Session") or None, "specialite": champs.get("Spécialité") or None,
            "outils": champs.get("Outils") or None, "fable": accord, "retrait_prevu": retrait == RETRAIT_PREVU,
            "retire": retrait == RETRAIT_FAIT,
            "texte": "\n".join(corps).strip(), "lecons": lecons, "chemin": chemin}


def est_polyvalente(fiche):
    """Vrai pour une fiche sans rôle : un agent qui prend n'importe quelle tâche, en spécialiste du métier de la tâche."""
    return isinstance(fiche, dict) and not fiche.get("role")


def nouvelle_fiche(cle, prenom, lieu, session=None):
    """Une fiche d'agent polyvalent (à compléter de `chemin` avant `ecrire_fiche`)."""
    return {"cle": cle, "prenom": prenom, "role": None, "service": None, "modele": None, "lieu": lieu,
            "session": session, "specialite": None, "outils": None, "fable": None, "retrait_prevu": False, "retire": False, "texte": "",
            "lecons": []}


def lire_toutes(dossier):
    """Les fiches du dossier (`*.md`, par nom de fichier), sans les sous-dossiers (briefs) ni les modèles."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        return []
    fiches, vues = [], set()
    for chemin in sorted(dossier.glob("*.md")):
        f = lire_fiche(chemin)
        if f["cle"] in vues:
            raise FicheInvalide(f"Fiches : clé en double « {f['cle']} ».")
        vues.add(f["cle"])
        fiches.append(f)
    return fiches


def ecrire_fiche(f):
    """Réécrit la fiche (le texte libre et les leçons sont gardés)."""
    lignes = [f"Clé : {f['cle']}"]
    for nom, cle in (("Prénom", "prenom"), ("Rôle", "role"), ("Service", "service"), ("Modèle", "modele"),
                     ("Lieu", "lieu"), ("Session", "session"), ("Spécialité", "specialite"), ("Outils", "outils"),
                     ("Fable", "fable")):
        if f.get(cle):
            lignes.append(f"{nom} : {f[cle]}")
    if f.get("retire"):
        lignes.append(f"Retrait : {RETRAIT_FAIT}")
    elif f.get("retrait_prevu"):
        lignes.append(f"Retrait : {RETRAIT_PREVU}")
    lignes += ["", f["texte"], "", "## Leçons"] if f["texte"] else ["", "## Leçons"]
    lignes += [f"- [{le['etat']}] {le['id']} : {le['texte']}" for le in f["lecons"]]
    chemin = Path(f["chemin"])
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as sortie:
            sortie.write("\n".join(lignes) + "\n")
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def fable_accorde(fiche):
    """Vrai si la fiche est sur Fable ET porte l'accord du Directeur (ligne `Fable : accordé par le Directeur le …`).
    Le moteur ne lance Fable que pour une telle fiche, pour cet agent seulement ; jamais pour un jugement."""
    return (isinstance(fiche, dict) and str(fiche.get("modele") or "").strip().lower() == "fable"
            and isinstance(fiche.get("fable"), str) and bool(ACCORD_FABLE.match(fiche["fable"])))


def accorder_fable(agents, cles, jour):
    """Les agents (copies) dont la clé est dans `cles` passent sur Fable avec l'accord du Directeur daté de `jour`
    (`AAAA-MM-JJ`). `ValueError` pour une clé dont l'agent n'a pas de `fable_suggere` vrai (ou qui n'existe pas)."""
    suggerees = {a["cle"] for a in agents if a.get("fable_suggere") is True}
    hors = [c for c in cles if c not in suggerees]
    if hors:
        raise ValueError("Fable n'a pas été suggéré pour : " + ", ".join(hors) + ".")
    accord = f"accordé par le Directeur le {jour}"
    return [dict(a, modele="Fable", fable=accord) if a["cle"] in cles else dict(a) for a in agents]


def outils(fiche):
    """Les outils de l'agent : la ligne `Outils :` de sa fiche (séparée par des virgules, hors parenthèses : une règle
    comme `Bash(py:*)` reste entière), sinon `OUTILS_PAR_DEFAUT`."""
    brut = (fiche.get("outils") or "").strip()
    if not brut:
        return list(OUTILS_PAR_DEFAUT)
    liste, courant, profondeur = [], "", 0
    for c in brut:
        profondeur += (c == "(") - (c == ")")
        if c == "," and profondeur <= 0:
            liste.append(courant.strip())
            courant = ""
        else:
            courant += c
    liste.append(courant.strip())
    return [o for o in liste if o] or list(OUTILS_PAR_DEFAUT)


MOTIF_PROGRAMME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")   # un nom de programme, rien d'autre
# Un programme désigné par son chemin absolu, barres obliques (`C:/…/emulator.exe`, `/usr/bin/x`) : jamais ouvert par le
# moteur seul, seulement sur l'accord du Directeur. Ni espace, ni variable, ni guillemet, ni `.`/`..` comme dossier.
MOTIF_CHEMIN = re.compile(r"^(?:[A-Za-z]:)?(?:/(?!\.{1,2}(?:/|\Z))[A-Za-z0-9._+-]{1,64}){1,24}\Z")
_REGLE_BASH = re.compile(r"^Bash\(([A-Za-z0-9][A-Za-z0-9._+-]{0,63}|(?:[A-Za-z]:)?/[^()\s:*]+):\*\)\Z")


def est_programme(programme):
    """Un nom de programme simple, ou le chemin absolu d'un programme (`MOTIF_CHEMIN`)."""
    return isinstance(programme, str) and (bool(MOTIF_PROGRAMME.match(programme)) or est_chemin(programme))


def est_chemin(programme):
    return isinstance(programme, str) and len(programme) <= 400 and bool(MOTIF_CHEMIN.match(programme))


def regle_bash(programme):
    """La règle qui ouvre un programme du shell : `Bash(<programme>:*)`. `ValueError` si ce n'est ni un nom de programme
    ni le chemin absolu d'un programme."""
    if not est_programme(programme):
        raise ValueError(f"« {programme} » n'est pas un nom de programme.")
    return f"Bash({programme}:*)"


def programmes_ouverts(fiche):
    """Les programmes du shell que la fiche ouvre (`Bash(<programme>:*)`), et si elle ouvre tout le shell (`Bash` seul)."""
    ouverts, tout = [], False
    for o in outils(fiche):
        m = _REGLE_BASH.match(o)
        if m:
            ouverts.append(m.group(1))
        tout = tout or o == "Bash"
    return ouverts, tout


def ouvrir_outil(fiche, outil):
    """Ajoute `outil` à la ligne `Outils :` de la fiche (les outils par défaut s'il n'y en avait pas), sans l'écrire.
    Seule une règle `Bash(<programme>:*)` s'ouvre ainsi : jamais `Bash` seul. Vrai si la fiche a changé ; `ValueError`
    si la règle n'est pas de cette forme."""
    m = _REGLE_BASH.match(outil) if isinstance(outil, str) else None
    if m is None or not est_programme(m.group(1)):
        raise ValueError("Seule une règle Bash(<programme>:*) peut être ouverte à un agent.")
    actuelles = outils(fiche)
    if outil in actuelles:
        return False
    fiche["outils"] = ", ".join(actuelles + [outil])
    return True


def trouver(fiches, cle):
    return next((f for f in fiches if f["cle"] == cle), None)
