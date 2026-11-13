"""La reprise d'un projet ouvert aux agents polyvalents (conception 2026-11-13-agents-polyvalents-design.md).

Un projet à l'ancienne a une fiche par agent, chacune avec son rôle, son service, son modèle et ses leçons. La reprise le
passe au nouveau standard, sans perte :

1. un **métier** par rôle des fiches (`briefs/<rôle>.md`) : le brief existant est gardé, sinon créé depuis le texte d'une
   fiche du rôle ; sa spécialité, ses outils, son service et son modèle viennent d'une fiche du rôle ; il est réservé au
   local quand toutes ses fiches étaient locales et déclarent des outils installés ;
2. les **leçons** des fiches (validées et « à valider ») vont dans le métier de leur rôle, ids gardés, doublons exacts
   fusionnés ; une leçon « à valider » du suivi porte son métier (`metier`) pour qu'elle se valide au bon endroit ;
3. l'**équipe** est ramenée aux places (Facturation) : on garde d'abord les agents au travail, puis ceux d'une fonctionnalité
   en cadrage, puis ceux qui ont une session cloud ; les autres partent. Un agent au travail au-delà des places n'est jamais
   retiré : il porte `Retrait : prévu` et part à la fin de sa tâche. Les fiches gardées deviennent polyvalentes ; aucun agent
   cloud n'est créé, les agents locaux manquants le sont jusqu'aux places ;
4. aucune tâche n'est touchée ; l'original de chaque fiche est mis de côté (`<fiches>/avant-polyvalents/`) ; un compte rendu
   est écrit dans `.factory/reprise-polyvalents.md`.

Chaque étape se rejoue sans effet : une reprise interrompue se relance telle quelle, sans leçon perdue ni dupliquée.
"""
import shutil
from pathlib import Path

from orchestrateur import fiches as fi
from orchestrateur import metiers
from orchestrateur import suivi as su

DOSSIER_AVANT = "avant-polyvalents"
JOURNAL = "reprise-polyvalents.md"


class RepriseImpossible(Exception):
    pass


def _a_reprendre(fiches_):
    """Les fiches à l'ancienne (avec un rôle), hors le chef, qui reste à part."""
    return [x for x in fiches_ if x["role"] and x["role"] != "chef"]


def _par_role(anciennes):
    sortie = {}
    for x in anciennes:
        sortie.setdefault(x["role"], []).append(x)
    return sortie


def _lire_metier(ctx, role):
    try:
        return metiers.lire_metier(Path(ctx.f["fiches"]) / "briefs", role)
    except metiers.MetierInvalide as e:
        raise RepriseImpossible(f"Le brief du métier « {role} » est illisible ({e}) : corrigez-le avant la reprise.")


def mettre_de_cote(ctx):
    """Copie l'original de chaque fiche à l'ancienne dans `avant-polyvalents/` (sans jamais écraser une copie : la
    première est l'original). Rend le nombre de copies faites."""
    dossier = Path(ctx.f["fiches"]) / DOSSIER_AVANT
    faites = 0
    for x in _a_reprendre(ctx.fiches()):
        cible = dossier / Path(x["chemin"]).name
        if cible.exists():
            continue
        dossier.mkdir(exist_ok=True)
        shutil.copy2(x["chemin"], cible)
        faites += 1
    return faites


def _depuis_les_fiches(role, siennes):
    """Les champs du métier d'un rôle, d'après ses fiches : service, modèle, spécialité et outils viennent d'une fiche du
    rôle (la première qui déclare une spécialité ou des outils, sinon la première) ; réservé au local quand toutes
    étaient locales et déclarent des outils installés."""
    source = next((x for x in siennes if x["specialite"] or x["outils"]), siennes[0])
    modele = source["modele"] if source["modele"] in metiers.MODELES else "Opus"     # Fable : jamais dans un brief
    lieu = "local" if all(x["lieu"] == "local" for x in siennes) and any(x["outils"] for x in siennes) \
        else "indifférent"
    return {"service": source["service"] or next((x["service"] for x in siennes if x["service"]), None),
            "modele": modele, "specialite": source["specialite"], "outils": source["outils"], "lieu": lieu}


def fixer_les_metiers(ctx):
    """Un métier par rôle des fiches. Un brief existant est gardé (seuls les champs d'en-tête qui lui manquent sont
    ajoutés) ; un brief absent est créé depuis le texte d'une fiche du rôle. Rend `([{role, cree}], changement)`."""
    sortie, change = [], False
    dossier = Path(ctx.f["fiches"]) / "briefs"
    for role, siennes in _par_role(_a_reprendre(ctx.fiches())).items():
        voulus = _depuis_les_fiches(role, siennes)
        m = _lire_metier(ctx, role)
        cree = m is None
        if cree:
            m = {"role": role, "service": None, "modele": None, "lieu": "indifférent", "specialite": None,
                 "outils": None, "texte": next((x["texte"] for x in siennes if x["texte"]), ""), "lecons": [],
                 "chemin": dossier / f"{role}.md"}
        avant = dict(m)
        for cle in ("service", "modele", "specialite", "outils"):
            if not m.get(cle):
                m[cle] = voulus[cle]
        if m["lieu"] == "indifférent":
            m["lieu"] = voulus["lieu"]
        if cree or m != avant:
            metiers.ecrire_metier(m)
            change = True
        sortie.append({"role": role, "cree": cree})
    return sortie, change


def regrouper_les_lecons(ctx):
    """Les leçons des fiches à l'ancienne vont dans le métier de leur rôle. Une leçon déjà là (même id, même texte) est
    laissée ; un texte identique sous un autre id est fusionné (le plus avancé des deux états l'emporte). Les leçons « à
    valider » du suivi portent leur métier. Rend `(regroupees, doublons)`."""
    regroupees = doublons = 0
    a_etiqueter = {}
    for role, siennes in _par_role(_a_reprendre(ctx.fiches())).items():
        m = _lire_metier(ctx, role)
        if m is None:
            raise RepriseImpossible(f"Le métier « {role} » n'existe pas : les métiers se fixent d'abord.")
        ecrire = False
        for x in siennes:
            for le in x["lecons"]:
                texte = le["texte"].strip()
                if le["etat"] == "à valider":
                    a_etiqueter[le["id"]] = role
                deja = next((y for y in m["lecons"] if y["id"] == le["id"]), None)
                if deja is not None:
                    if le["etat"] == "validée" and deja["etat"] != "validée" and deja["texte"].strip() == texte:
                        deja["etat"] = "validée"
                        ecrire = True
                    continue
                pareille = next((y for y in m["lecons"] if y["texte"].strip() == texte), None)
                if pareille is not None:
                    doublons += 1
                    if le["etat"] == "validée" and pareille["etat"] != "validée":
                        pareille["etat"] = "validée"
                        ecrire = True
                    continue
                if metiers.ajouter_lecon(m, {"id": le["id"], "etat": le["etat"], "texte": texte}):
                    regroupees += 1
                    ecrire = True
        if ecrire:
            metiers.ecrire_metier(m)
    if a_etiqueter:
        with ctx.suivi.transaction() as s:
            for lecon in s["lecons"]:
                role = a_etiqueter.get(lecon["id"])
                if role and lecon["etat"] == "à valider" and lecon.get("metier") != role:
                    lecon["metier"] = role
    return regroupees, doublons


def _priorite(x, occupes, cadrage, sessions):
    """0 : au travail ; 1 : agent de cadrage d'une fonctionnalité en cadrage ; 2 : une session cloud ; 3 : les autres."""
    if x["cle"] in occupes:
        return 0
    if x["cle"] in cadrage:
        return 1
    return 2 if (sessions.get(x["cle"]) or x["session"]) else 3


def ramener_l_equipe(ctx, locaux, cloud):
    """Les fiches deviennent polyvalentes, autant que de places par lieu (les agents au travail d'abord) ; les autres sont
    retirées, ou marquées `Retrait : prévu` quand elles travaillent. Rend `(gardes, retires, retraits_prevus)` (clés)."""
    from orchestrateur import outil
    s = ctx.suivi.lire()
    agents = [x for x in ctx.fiches() if x["role"] != "chef" and not x.get("retire")]
    occupes = {t["agent"] for t in s["taches"] if t.get("active") and t.get("agent")}
    avec_taches = {t["agent"] for t in s["taches"] if t.get("agent")}
    cadrage = {f["agent_cadrage"] for f in s["fonctionnalites"] if f.get("etape") == "cadrage" and f.get("agent_cadrage")}
    sessions = ctx.sessions()
    gardes, retires, retraits = [], [], []
    for lieu, voulu in (("local", locaux), ("cloud", cloud)):
        # on garde d'abord les agents au travail, puis ceux qui ont déjà réalisé une tâche (leurs fiches sont les seules
        # qu'il faudrait de toute façon garder pour l'historique), puis le reste de l'ordre de priorité
        ordre = sorted((x for x in agents if x["lieu"] == lieu),
                       key=lambda x: (x["cle"] not in occupes, x["cle"] not in avec_taches,
                                      _priorite(x, occupes, cadrage, sessions)))
        for rang, x in enumerate(ordre):
            garde = rang < voulu
            if not garde and x["cle"] not in occupes:
                # sans aucune tâche : supprimé ; sinon gardé, inactif (fiche polyvalente `Retrait : fait`, identité gardée)
                neuve = fi.nouvelle_fiche(x["cle"], x["prenom"], x["lieu"], session=x["session"])
                neuve["chemin"] = x["chemin"]
                neuve["retire"] = True
                outil.retirer_l_agent(neuve, x["cle"] in avec_taches)
                retires.append(x["cle"])
                continue
            (gardes if garde else retraits).append(x["cle"])
            if fi.est_polyvalente(x) and bool(x.get("retrait_prevu")) == (not garde):
                continue
            neuve = fi.nouvelle_fiche(x["cle"], x["prenom"], x["lieu"], session=x["session"])
            neuve["chemin"] = x["chemin"]
            neuve["retrait_prevu"] = not garde
            fi.ecrire_fiche(neuve)
    return gardes, retires, retraits


def restaurer_les_retires(ctx):
    """Rejouée sur un projet déjà repris : un agent dont la fiche manque (supprimée par une reprise qui ne gardait pas les
    agents retirés) et qui a au moins une tâche au suivi revient, retiré, depuis sa fiche d'origine
    (`avant-polyvalents/<clé>.md`) : clé, prénom, lieu et session gardés. Sans tâche, rien ne revient. Rend les clés."""
    dossier = Path(ctx.f["fiches"]) / DOSSIER_AVANT
    if not dossier.is_dir():
        return []
    presentes = {x["cle"] for x in ctx.fiches()}
    avec_taches = {t["agent"] for t in ctx.suivi.lire()["taches"] if t.get("agent")}
    sessions, restaures = ctx.sessions(), []
    for chemin in sorted(dossier.glob("*.md")):
        origine = fi.lire_fiche(chemin)
        cible = Path(ctx.f["fiches"]) / chemin.name
        if origine["role"] == "chef" or origine["cle"] in presentes or origine["cle"] not in avec_taches or cible.exists():
            continue
        neuve = fi.nouvelle_fiche(origine["cle"], origine["prenom"], origine["lieu"],
                                  session=sessions.get(origine["cle"]) or origine["session"])
        neuve["chemin"] = cible
        neuve["retire"] = True
        fi.ecrire_fiche(neuve)
        restaures.append(origine["cle"])
    return restaures


def _texte_du_compte_rendu(metiers_, regroupees, doublons, gardes, retires, retraits, crees, rien_a_faire):
    if rien_a_faire:
        return ("Le projet est déjà passé aux agents polyvalents : rien à reprendre "
                f"({len(gardes)} agent{'s' if len(gardes) > 1 else ''}).")

    def pluriel(n, un, plusieurs):
        return f"{n} {un if n <= 1 else plusieurs}"
    morceaux = [f"Passage aux agents polyvalents : {pluriel(len(metiers_), 'métier', 'métiers')} "
                f"({', '.join(m['role'] for m in metiers_)}"
                + (f" ; créés : {', '.join(m['role'] for m in metiers_ if m['cree'])}" if any(m['cree'] for m in metiers_)
                   else "") + ")",
                f"{pluriel(regroupees, 'leçon regroupée', 'leçons regroupées')} par métier"
                + (f", {pluriel(doublons, 'doublon fusionné', 'doublons fusionnés')}" if doublons else ""),
                f"équipe : {pluriel(len(gardes), 'agent gardé', 'agents gardés')} ({', '.join(gardes) or 'aucun'})"
                + (f", {pluriel(len(retires), 'agent retiré', 'agents retirés')} ({', '.join(retires)})" if retires else "")
                + (f", {pluriel(len(retraits), 'agent partira', 'agents partiront')} à la fin de leur tâche "
                   f"({', '.join(retraits)})" if retraits else "")
                + (f", {pluriel(len(crees), 'agent local ajouté', 'agents locaux ajoutés')}" if crees else "")]
    return "; ".join(morceaux) + ". Aucune tâche n'a été touchée ; les fiches d'origine sont dans " \
        f"« {DOSSIER_AVANT} »."


def reprendre(ctx):
    """Passe le projet aux agents polyvalents (voir le haut du fichier). Rejouable sans effet.
    `{metiers: [{role, cree}], lecons_regroupees, doublons, agents_gardes, agents_retires, retraits_prevus,
    agents_crees, deja, compte_rendu}`. `RepriseImpossible` : un brief illisible (rien n'est changé)."""
    from orchestrateur import outil
    anciennes = _a_reprendre(ctx.fiches())
    for role in _par_role(anciennes):       # un brief illisible arrête tout avant la première écriture
        _lire_metier(ctx, role)
    if not anciennes:
        restaures = restaurer_les_retires(ctx)
        gardes = [x["cle"] for x in ctx.fiches() if x["role"] != "chef" and not x.get("retire")]
        compte_rendu = _texte_du_compte_rendu([], 0, 0, gardes, [], [], [], True)
        if restaures:
            compte_rendu += (f" {len(restaures)} agent{'s' if len(restaures) > 1 else ''} retiré"
                             f"{'s' if len(restaures) > 1 else ''} de l'équipe remis en historique ({', '.join(restaures)}).")
            journal = Path(ctx.f["suivi"]).with_name(JOURNAL)
            ancien = journal.read_text(encoding="utf-8") if journal.is_file() else "# Passage aux agents polyvalents\n"
            journal.write_text(ancien.rstrip("\n") + f"\n\n## {su.maintenant()}\n\n{compte_rendu}\n", encoding="utf-8",
                               newline="\n")
        return {"metiers": [], "lecons_regroupees": 0, "doublons": 0, "agents_gardes": gardes, "agents_retires": restaures,
                "retraits_prevus": [x["cle"] for x in ctx.fiches() if x.get("retrait_prevu")], "agents_crees": [],
                "deja": not restaures, "compte_rendu": compte_rendu}
    locaux, cloud = ctx.f["agents_locaux_max"], outil.places_cloud_du_projet(ctx)
    mettre_de_cote(ctx)
    metiers_, _ = fixer_les_metiers(ctx)
    regroupees, doublons = regrouper_les_lecons(ctx)
    gardes, retires, retraits = ramener_l_equipe(ctx, locaux, cloud)
    sync = outil.synchroniser_equipe(ctx, creer=True, cloud_aussi=False)     # les agents locaux qui manquent aux places
    compte_rendu = _texte_du_compte_rendu(metiers_, regroupees, doublons, gardes, retires, retraits, sync["crees"], False)
    journal = Path(ctx.f["suivi"]).with_name(JOURNAL)
    ancien = journal.read_text(encoding="utf-8") if journal.is_file() else "# Passage aux agents polyvalents\n"
    journal.write_text(ancien.rstrip("\n") + f"\n\n## {su.maintenant()}\n\n{compte_rendu}\n", encoding="utf-8", newline="\n")
    return {"metiers": metiers_, "lecons_regroupees": regroupees, "doublons": doublons,
            "agents_gardes": gardes, "agents_retires": retires, "retraits_prevus": retraits,
            "agents_crees": sync["crees"], "deja": False, "compte_rendu": compte_rendu}
