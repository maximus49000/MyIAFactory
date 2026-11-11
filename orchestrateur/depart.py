"""Le départ d'un agent : choisir l'agent libre, le modèle, et assembler son message de départ.

Le message est toujours assemblé par cette commande, jamais à la main : un agent repart d'un contexte neuf à chaque
tâche, avec sa fiche entière, les leçons de la skill et du genre qui touchent son rôle, le brief du rôle, sa tâche
et la consigne de fin d'étape.
"""
import re
from pathlib import Path

ECHELLE = ("Haiku", "Sonnet", "Opus")   # on monte d'un cran au plus ; Fable n'en fait jamais partie
_ROLE_SUR = re.compile(r"^[A-Za-z0-9_-]+\Z")


def monter(modele):
    """Le modèle du cran au-dessus (Haiku → Sonnet → Opus → Opus). Un autre nom reste tel quel ; jamais Fable."""
    if modele not in ECHELLE:
        return modele
    return ECHELLE[min(ECHELLE.index(modele) + 1, len(ECHELLE) - 1)]


def agent_libre(fiches, taches, role, modele=None, lieu=None, agents_locaux_max=None):
    """(clé, raison) du premier spécialiste du rôle sans tâche active, au modèle et au lieu demandés.
    Un agent cloud sans session attitrée n'est pas utilisable : la raison dit qu'il faut créer la session.
    Quand `agents_locaux_max` tâches actives sont déjà tenues par des agents locaux, aucun agent local n'est rendu
    (les agents cloud ne comptent pas dans la limite et ne la subissent pas)."""
    occupes = {t.get("agent") for t in taches if t.get("active") and t.get("agent")}
    locales = {f["cle"] for f in fiches if f["lieu"] == "local"}
    limite = (agents_locaux_max is not None
              and sum(1 for t in taches if t.get("active") and t.get("agent") in locales) >= agents_locaux_max)
    retenu_par_la_limite = False
    for f in fiches:
        if f["role"] != role or (modele and f["modele"] != modele) or (lieu and f["lieu"] != lieu):
            continue
        if f["cle"] in occupes or (f["lieu"] == "cloud" and not f.get("session")):
            continue
        if limite and f["lieu"] == "local":
            retenu_par_la_limite = True
            continue
        return f["cle"], f"{f.get('prenom') or f['cle']} est libre"
    if retenu_par_la_limite:
        return None, f"limite de {agents_locaux_max} agents locaux atteinte"
    sur = f" sur {modele}" if modele else ""
    if lieu == "cloud":
        attend = sans_session(fiches, role, modele)
        if attend:   # une fiche existe mais n'a pas de session : c'est elle que la décision nommera
            return None, f"aucun agent cloud {role}{sur} : session à créer pour {attend}"
        if not any(f["role"] == role and f["lieu"] == "cloud" and (not modele or f["modele"] == modele) for f in fiches):
            return None, f"aucune fiche cloud {role}{sur} : ajoutez-en une"
        return None, f"aucun agent cloud {role} libre{sur}"   # tous occupés : on attend
    return None, f"aucun {role} libre{sur}"


def sans_session(fiches, role, modele=None):
    """La clé de la première fiche cloud du rôle (et du modèle) qui n'a pas de session attitrée, ou `None`."""
    for f in fiches:
        if (f["role"] == role and f["lieu"] == "cloud" and not f.get("session")
                and (not modele or f["modele"] == modele)):
            return f["cle"]
    return None


def brief(factory, role):
    """Le brief du rôle (`<fiches>/briefs/<rôle>.md`), ou `None` s'il n'existe pas."""
    if not isinstance(role, str) or not _ROLE_SUR.match(role):
        return None
    chemin = Path(factory["fiches"]) / "briefs" / f"{role}.md"
    return chemin.read_text(encoding="utf-8-sig").strip() if chemin.is_file() else None


def _texte_fiche(f):
    """La fiche, sans les leçons « à valider » : elles ne sont pas encore la règle (et coûteraient à chaque départ)."""
    chemin = f.get("chemin")
    if chemin and Path(chemin).is_file():
        lignes = Path(chemin).read_text(encoding="utf-8-sig").splitlines()
        return "\n".join(x for x in lignes if not x.lstrip().startswith("- [à valider]")).strip()
    lignes = [f"Clé : {f['cle']}", f"Rôle : {f['role']}", f"Modèle : {f['modele']}", f"Lieu : {f['lieu']}"]
    if f.get("session"):
        lignes.append(f"Session : {f['session']}")
    lignes += ["", f.get("texte") or "", "", "## Leçons"]
    lignes += [f"- [{x['etat']}] {x['id']} : {x['texte']}" for x in f.get("lecons") or [] if x["etat"] != "à valider"]
    return "\n".join(lignes).strip()


SOBRIETE = """## Sobriété
Chaque lecture et chaque essai se paient en tokens. Ne lis que ce que ta tâche, ton brief et le registre des
contrôles désignent ; n'explore pas le projet au-delà. Ne relis pas un fichier déjà lu dans cette tâche, ne refais
pas un essai qui a réussi, et préfère un outil du projet qui fait le travail à une longue lecture. Si une information
manque, dis-le dans ton résultat plutôt que de la chercher partout."""


def _lecons(titre, lecons):
    lignes = [f"- {x['titre']} — {x['texte']}" if x.get("titre") else f"- {x.get('texte', '')}" for x in lecons]
    corps = "\n".join(lignes) if lignes else "(aucune)"
    return f"## {titre}\n{corps}"


FIN_D_ETAPE = """## À la fin de ton étape
Rends, dans cet ordre :
1. **Le résultat** de la tâche : ce qui est fait, où le trouver, ce qui reste.
2. **Tes leçons** : ce que tu as appris et qui servirait ensuite. Pour chacune, propose un **étage** : `projet`
   (ne vaut que pour ce projet), `genre` (vaut pour tous les projets de ce genre) ou `skill` (vaut pour n'importe
   quel projet). Pour `genre` et `skill`, écris aussi le **texte général** : la même leçon réécrite en termes
   généraux, sans nom de projet, de lieu, de fichier ni de personne.
3. **Tes retours sur la factory** : une amélioration d'un outil, un contrôle à ajouter au registre, une consigne
   à corriger."""


def _bloc_tache(tache):
    t = [f"- Tâche : {tache.get('titre', '')} ({tache.get('id', '?')})"]
    for cle, nom in (("fonctionnalite", "Fonctionnalité"), ("element", "Élément"), ("etape", "Étape")):
        if tache.get(cle):
            t.append(f"- {nom} : {tache[cle]}")
    m = tache.get("montee")
    if m:
        t.append(f"- Modèle : {m['a']} (monté depuis {m['de']} : {m['raison']})")
    return t


def _entete(factory, fiche, lecons_memoire):
    parties = []
    if fiche["lieu"] == "cloud":
        parties.append("Tu repars de zéro. Rien de ce qui s'est dit dans cette session avant ce message ne compte : "
                       "tout ce qu'il te faut est ci-dessous.")
    genre = factory.get("genre")
    parties.append(f"# Projet : {factory['nom']}" + (f" (genre : {genre})" if genre else ""))
    parties.append("## Ta fiche\n" + _texte_fiche(fiche))
    parties.append(_lecons("Leçons de la skill qui touchent ton rôle", lecons_memoire.get("skill") or []))
    parties.append(_lecons("Leçons du genre du projet qui touchent ton rôle", lecons_memoire.get("genre") or []))
    return parties


def _vocabulaire(glossaire):
    """Le vocabulaire déjà défini : l'agent le reprend tel quel, sans le redéfinir."""
    return ("## Vocabulaire de la fonctionnalité\n"
            "Ces mots sont déjà définis : emploie-les dans ce sens et ne les redéfinis pas. Si tu emploies un "
            "autre mot spécialisé, donne sa définition avec ton résultat (mot et définition courte).\n"
            + "\n".join(f"- {g['mot']} : {g['definition']}" for g in glossaire))


def message(factory, fiche, tache, brief_du_role, lecons_memoire, glossaire=()):
    """Le message de départ d'un agent. `lecons_memoire` : `{"skill": [...], "genre": [...]}`, déjà filtré sur le
    rôle de l'agent. En cloud, il commence par « Tu repars de zéro. »."""
    parties = _entete(factory, fiche, lecons_memoire)
    parties.append("## Le brief de ton rôle\n" + (brief_du_role or "(pas de brief propre à ce rôle)"))
    parties.append("\n".join(["## Ta tâche"] + _bloc_tache(tache)))
    if glossaire:
        parties.append(_vocabulaire(glossaire))
    parties.append(SOBRIETE)
    parties.append(FIN_D_ETAPE)
    return "\n\n".join(parties) + "\n"


def compte_rendu_par_tache(cle):
    """La consigne d'enchaînement d'un lot : chaque tâche est marquée active à son début et rendue à sa fin (sa durée
    sert à répartir le coût du lot)."""
    return ("Enchaîne ces tâches d'une traite, dans cet ordre, avec ce même contexte. La première est déjà marquée "
            "comme la tienne. **À la fin de chaque tâche, rends compte avant de passer à la suivante** : `lancer tache` "
            "avec son `id` (journal, `colonne`, `active: false`), puis marque aussitôt la suivante : `lancer tache` "
            f'avec `{{"id": <son id>, "agent": "{cle}", "active": true}}`, et seulement ensuite commence-la.')


def message_lot(factory, fiche, taches, briefs, lecons_memoire, glossaire=()):
    """Le message de départ d'un lot : un seul message pour toutes les tâches, dans l'ordre du lot. `briefs` : liste de
    `(rôle, texte | None)`, un par rôle présent dans le lot."""
    parties = _entete(factory, fiche, lecons_memoire)
    if len(briefs) == 1:
        parties.append("## Le brief de ton rôle\n" + (briefs[0][1] or "(pas de brief propre à ce rôle)"))
    else:
        parties.append("## Les briefs des rôles de ce lot\n" + "\n\n".join(
            f"### Rôle : {role}\n{texte or '(pas de brief propre à ce rôle)'}" for role, texte in briefs))
    lignes = [f"## Tes {len(taches)} tâches, dans l'ordre", compte_rendu_par_tache(fiche["cle"])]
    for k, tache in enumerate(taches, 1):
        lignes.append(f"\n### Tâche {k} sur {len(taches)}")
        lignes += _bloc_tache(tache)
    parties.append("\n".join(lignes))
    if glossaire:
        parties.append(_vocabulaire(glossaire))
    parties.append(SOBRIETE)
    parties.append(FIN_D_ETAPE.replace("## À la fin de ton étape", "## À la fin de ton lot")
                   .replace("1. **Le résultat** de la tâche :", "1. **Le résultat** de chaque tâche :", 1))
    return "\n\n".join(parties) + "\n"
