"""Le départ d'un agent : choisir l'agent libre, le modèle, et assembler son message de départ.

Le message est toujours assemblé par cette commande, jamais à la main : un agent repart d'un contexte neuf à chaque
tâche, avec sa fiche entière, les leçons de la skill et du genre qui touchent son rôle, le brief du rôle, sa tâche
et la consigne de fin d'étape.
"""
import json
import re
from pathlib import Path

from orchestrateur import modele_necessaire as mn
from orchestrateur import regles_projet as rp

ECHELLE = ("Haiku", "Sonnet", "Opus")   # on monte d'un cran au plus ; Fable n'en fait jamais partie
_ROLE_SUR = re.compile(r"^[A-Za-z0-9_-]+\Z")


def monter(modele, fable=False):
    """Le modèle du cran au-dessus (Haiku → Sonnet → Opus → Opus). Un autre nom reste tel quel ; jamais Fable, sauf
    `fable` (un projet aux agents polyvalents) : Opus → Fable, une demande que le Directeur accorde ou non avant le
    départ de la tâche (sans accord, elle part sur Opus)."""
    if modele not in ECHELLE:
        return modele
    if fable and modele == ECHELLE[-1]:
        return mn.FABLE
    return ECHELLE[min(ECHELLE.index(modele) + 1, len(ECHELLE) - 1)]


def agent_libre(fiches, taches, role, modele=None, lieu=None, agents_locaux_max=None, lieu_reserve=None,
                lieu_etape=None):
    """(clé, raison) du premier spécialiste du rôle sans tâche active, au lieu demandé, dont le plafond (le modèle de sa
    fiche) suffit au `modele` nécessaire de la tâche : le plus petit plafond suffisant d'abord (il fera tourner la tâche
    sur ce modèle, jamais au-dessus de son plafond). Un agent cloud sans session attitrée n'est pas utilisable : la raison dit qu'il faut créer la session.
    Quand `agents_locaux_max` tâches actives sont déjà tenues par des agents locaux, aucun agent local n'est rendu
    (les agents cloud ne comptent pas dans la limite et ne la subissent pas).
    Après les spécialistes du rôle viennent les agents polyvalents (fiche sans rôle) : n'importe lequel, libre, au lieu
    demandé, sans plafond. `lieu_reserve` : le lieu que le métier de la tâche impose (`Lieu : local` de son brief) ; la
    tâche attend alors une place de ce lieu. `lieu_etape` : le `lieu` écrit de l'étape de la tâche, qui l'emporte sur
    le métier (`local` : la tâche attend le poste local ; `indifférent` : aucun lieu imposé)."""
    reserve = mn.lieu_impose(lieu_etape, lieu_reserve)
    if lieu_etape == "local" and lieu and lieu != "local":
        return None, "l'étape exige le poste : la tâche attend le poste local"
    if lieu_etape == "cloud" and lieu and lieu != "cloud":
        return None, "l'étape se fait dans le cloud : la tâche attend un agent cloud"
    if reserve and lieu and lieu != reserve:
        return None, (f"le métier {role} se fait en local : la tâche attend une place locale" if reserve == "local"
                      else f"le métier {role} se fait dans le cloud : la tâche attend une place cloud")
    lieu = lieu or reserve
    occupes = {t.get("agent") for t in taches if t.get("active") and t.get("agent")}
    locales = {f["cle"] for f in fiches if f["lieu"] == "local"}
    limite = (agents_locaux_max is not None
              and sum(1 for t in taches if t.get("active") and t.get("agent") in locales) >= agents_locaux_max)
    retenu_par_la_limite = False
    for f in mn.possibles(fiches, role, modele):
        if lieu and f["lieu"] != lieu:
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
    if lieu_etape == "local":
        return None, f"aucun agent local libre{sur} : la tâche attend le poste local"
    if lieu == "cloud":
        attend = sans_session(fiches, role, modele)
        if attend:   # une fiche existe mais n'a pas de session : c'est elle que la décision nommera
            return None, f"aucun agent cloud {role}{sur} : session à créer pour {attend}"
        if not any(f["lieu"] == "cloud" for f in mn.possibles(fiches, role, modele)):
            return None, f"aucune fiche cloud {role}{sur} : ajoutez-en une"
        return None, f"aucun agent cloud {role} libre{sur}"   # tous occupés : on attend
    return None, f"aucun {role} libre{sur}"


CLOUD_PAR_DEFAUT = 3     # l'ancienne limite (réglage `agents_cloud_max` des réglages du projet), avant le réglage par projet


def places_cloud(regle, ancienne, a_des_agents_cloud):
    """Les places cloud effectives d'un projet : `agents_cloud_max` de la factory s'il est réglé ; sinon l'ancienne
    limite des réglages (`ancienne`, 3 par défaut) pour un projet qui a déjà des agents cloud, et 0 pour les autres."""
    if regle is not None:
        return regle
    return (ancienne if isinstance(ancienne, int) and not isinstance(ancienne, bool) else CLOUD_PAR_DEFAUT) \
        if a_des_agents_cloud else 0


def ancienne_limite_cloud(chemin_reglages):
    """`agents_cloud_max` des réglages du projet (l'ancienne limite commune), 3 s'il manque ou s'il est illisible."""
    try:
        v = json.loads(Path(chemin_reglages).read_text(encoding="utf-8-sig")).get("agents_cloud_max")
    except (OSError, ValueError, TypeError, AttributeError):
        return CLOUD_PAR_DEFAUT
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else CLOUD_PAR_DEFAUT


def sans_session(fiches, role, modele=None):
    """La clé de la première fiche cloud du rôle (au plafond suffisant pour `modele`, le plus petit d'abord) qui n'a pas
    de session attitrée, ou `None`."""
    for f in mn.possibles(fiches, role, modele):
        if f["lieu"] == "cloud" and not f.get("session"):
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
   à corriger.

Termine ta réponse par un bloc ```json (le dernier de ta réponse), de cette forme, que le moteur lit pour tenir le suivi :
```json
{"statut": "fait", "message": {"texte": "ce que tu dis dans la discussion", "images": [{"chemin": "relatif au projet", "legende": "une phrase : à quoi l'image fait référence"}], "questions": [{"texte": "…", "choix": ["…", "…"], "multiple": false}], "glossaire": [], "attend": false},
 "fichiers": [{"chemin": "relatif au projet", "titre": "…", "element": "…", "livrable": false}],
 "lecons": [{"texte": "…", "roles": ["dev"], "etage_propose": "projet", "texte_general": "…"}],
 "controles": [{"texte": "…", "origine": "…"}], "retours_factory": ["…"],
 "verdicts": [{"element": "…", "conforme": true, "points": []}], "lignes": 0}
```
`statut` vaut `fait`, `accord_requis`, `outil_refuse`, `a_faire_chez_partenaire` ou `echec`. Seul `statut` est obligatoire ; omets ce qui est vide.
Chaque image que tu rends (dans `message.images`, comme dans une maquette du cahier) porte sa **légende** : une phrase
de 160 caractères au plus qui dit à quoi elle correspond (écran, élément, moment du jeu…) ; le bureau l'affiche sous
l'image.
Chaque fois que tu demandes l'avis ou l'accord de l'utilisateur, pose-le en `message.questions` à choix (forme exacte
ci-dessus), avec `attend: true` : « Le style vous convient-il ? » → « Oui, on continue », « À corriger (précisez) ».
Jamais une demande d'avis en simple phrase : la page n'offrirait aucun bouton.
Si une dépense ou un changement de partenaire ou le navigateur demande l'accord de l'utilisateur, arrête-toi et rends
`statut: accord_requis` avec `"accord": {"quoi", "partenaire", "cout"}`. Si un outil t'est refusé, rends
`statut: outil_refuse` avec `"outil": "<son nom>"`.
Partenaire **inscrit** (compte, pas de liaison directe) : ne l'appelle pas ; rends `statut: a_faire_chez_partenaire` avec
`"chez_partenaire": {"partenaire" (id), "quoi", "prompt" (prêt à copier, selon ses règles), "reglages" (chacun), "mode_operatoire" (où
cliquer), "a_rapporter": {"description", "nom"}, "elements" (groupés en une génération)}`. L'utilisateur le fait et te rapporte le résultat.
Avant une action qui fait apparaître une fenêtre sur l'ordinateur de l'utilisateur (pare-feu Windows pour adb.exe, un
émulateur ou un serveur local ; droits d'administrateur (UAC) ; pilote), arrête-toi : mets en tête de ton `message.texte` quelle fenêtre va s'ouvrir,
pourquoi et quoi choisir (« Une fenêtre du pare-feu Windows va s'ouvrir pour adb.exe : choisissez Réseaux privés. »), avec `attend: true`, et
n'agis qu'après sa réponse. Ne réponds jamais à ces fenêtres à sa place. Si une commande attend, bloquée par une
fenêtre, dis-le dans ton compte rendu.
**Jamais d'installation ni de test sur un appareil physique de l'utilisateur** : pas d'`adb devices` ni d'`adb install`
vers un téléphone branché, pas de demande de brancher un téléphone ni d'activer le débogage USB. Les tests automatiques
d'une application mobile se font sur un émulateur (AVD sans fenêtre : `emulator -no-window`) ; s'il manque, déclare-le
comme outil du poste à installer. La version, c'est l'utilisateur qui la valide dans la fenêtre de validation
(`nature: en_jeu`, apk à télécharger et mode opératoire). Si tu juges quand même nécessaire un test sur appareil, rends
`accord_requis` : c'est le Directeur qui statue, et s'il refuse, continue sans ce test (installation non faite)."""


def fin_cloud(tache_id):
    """La consigne d'un agent cloud : personne ne lit sa réponse, le moteur lit son dépôt."""
    return (f"""## Rends ton rapport par le dépôt
Ta réponse n'est lue par personne : le moteur relève ton travail dans le dépôt. Quand tu as fini (ou que tu dois
t'arrêter, par exemple pour un accord de l'utilisateur), **écris le bloc JSON demandé ci-dessus dans le fichier
`.factory/rapports/{tache_id}.json`** (le JSON seul, sans texte autour), **commite-le sur ta branche `claude/…` avec
ton travail et pousse**. Ajoute-y `"usage_estime"` : ton estimation, en nombre entier, des tokens employés. Sans ce
fichier poussé, ton travail n'existe pas pour la factory. Si `.factory/rapports/commandes-figees.jsonl` existe, une
commande figée (processeur immobile) a été arrêtée pendant ta session : dis lesquelles dans `message.texte`.""")


def _bloc_tache(tache):
    t = [f"- Tâche : {tache.get('titre', '')} ({tache.get('id', '?')})"]
    for cle, nom in (("fonctionnalite", "Fonctionnalité"), ("element", "Élément"), ("etape", "Étape")):
        if tache.get(cle):
            t.append(f"- {nom} : {tache[cle]}")
    m = tache.get("montee")
    if m:
        t.append(f"- Modèle : {m['a']} (monté depuis {m['de']} : {m['raison']})")
    return t


def outils_du_poste(factory):
    """« Outils du poste : … » : les outils déjà en place (nom, chemin, version), tels que le projet les a notés. Rien
    s'il n'y en a pas."""
    lignes = []
    for o in factory.get("environnement") or []:
        if isinstance(o, dict) and o.get("etat") == "en_place" and o.get("outil"):
            if o.get("declare") is True:      # le Directeur l'affirme installé, on ne l'a pas trouvé : l'agent doit le savoir
                lignes.append(f"- {o['outil']} : {o.get('note') or 'déclaré installé par le Directeur (non vérifié)'} ;"
                              " s'il est introuvable, dis-le plutôt que de le réinstaller")
                continue
            lignes.append(f"- {o['outil']} : {o.get('chemin') or '(sur le PATH)'}" + (f" ({o['version']})" if o.get("version") else ""))
    return ("## Outils du poste\nDéjà installés ; sers-t'en directement, sans les réinstaller :\n" + "\n".join(lignes)) if lignes else ""


def _section_metier(metiers_):
    """« Ton métier » d'un agent polyvalent : pour chaque métier de la tâche (ou du lot), sa spécialité, ses outils et ses
    leçons validées (celles « à valider » ne sont pas encore la règle). Le texte du brief est donné à part."""
    blocs = []
    for m in metiers_:
        lignes = [f"### Métier : {m['role']}"] if len(metiers_) > 1 else []
        for nom, cle in (("Service", "service"), ("Spécialité", "specialite"), ("Outils", "outils")):
            if m.get(cle):
                lignes.append(f"{nom} : {m[cle]}")
        validees = [x for x in m.get("lecons") or [] if x["etat"] == "validée"]
        lignes.append("Leçons de ce métier :")
        lignes += [f"- {x['texte']}" for x in validees] if validees else ["(aucune)"]
        blocs.append("\n".join(lignes))
    titre = metiers_[0]["role"] if len(metiers_) == 1 else "les métiers de ce lot"
    return f"## Ton métier : {titre}\nPour cette tâche, tu es le spécialiste de ce métier.\n" + "\n\n".join(blocs)


def _entete(factory, fiche, lecons_memoire, regles_projet=(), metiers_=None):
    parties = []
    if fiche["lieu"] == "cloud":
        parties.append("Tu repars de zéro. Rien de ce qui s'est dit dans cette session avant ce message ne compte : "
                       "tout ce qu'il te faut est ci-dessous.")
    genre = factory.get("genre")
    parties.append(f"# Projet : {factory['nom']}" + (f" (genre : {genre})" if genre else ""))
    regles = rp.en_tete(regles_projet)
    if regles:
        parties.append(regles)       # en tête : ce que le Directeur a décidé pour ce projet
    poste = outils_du_poste(factory)
    if poste:
        parties.append(poste)
    if metiers_:   # un agent polyvalent : l'identité est dans l'en-tête, le reste est celui du métier de la tâche
        parties.append(_section_metier(metiers_))
    else:
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


def _regles_partenaires(regles):
    """Les règles d'usage des partenaires de la tâche, mot pour mot. `regles` : [(nom, [textes])]."""
    lignes = ["## Règles de tes partenaires",
              "Suis ces règles quand tu appelles ces partenaires. Une règle qui contredit une consigne explicite de "
              "l'utilisateur pour cette tâche cède devant elle : dis-le dans ton résultat. La clé d'un partenaire se lit "
              "dans l'environnement ou le `.env` du projet au moment de l'appel : ne l'écris, ne l'affiche et ne la "
              "journalise jamais. Après chaque appel payant, note-le : `lancer partenaires` avec "
              '`{"action": "usage", "partenaire", "tache", "quantite", "unite", "cout"?, "devise"?, "estime"?}` ; sur un '
              'refus pour quota ou paiement, `{"action": "limite", "partenaire", "raison"}`, puis arrête-toi et dis-le.']
    for nom, textes in regles:
        lignes.append(f"\n### {nom}")
        lignes += [f"- {x}" for x in textes] or ["(aucune règle)"]
    return "\n".join(lignes)


def _partenaires_inscrits(inscrits, ecartes):
    """Les partenaires où l'utilisateur est inscrit (hors liaison directe) : l'agent ne les appelle pas, il prépare ce que
    l'utilisateur fait chez eux. `inscrits` : [{nom, site?, note?, regles: [textes], prompt_max?, reglages: bool}] ;
    `ecartes` : les noms que le cadrage a écartés."""
    lignes = []
    if inscrits:
        lignes += ["## Partenaires où l'utilisateur est inscrit",
                   "Il a un compte chez eux, sans liaison directe : n'appelle ni leur API ni leur MCP, ne dépense rien chez eux. "
                   "Quand ta tâche en a besoin, prépare ce qu'il fera lui-même sur leur site et rends `statut: "
                   "a_faire_chez_partenaire` (forme en fin d'étape) : le prompt prêt à copier qui respecte leurs règles, chacun de "
                   "leurs réglages, où cliquer, le fichier à te rapporter et son nom. Groupe les éléments en une seule "
                   "génération quand c'est possible ; une génération à la fois par partenaire. Il te rend le résultat, "
                   "tu reprends."]
        for p in inscrits:
            lignes.append(f"\n### {p['nom']}" + (f" ({p['site']})" if p.get("site") else "")
                          + (f" — compte : {p['note']}" if p.get("note") else ""))
            if p.get("prompt_max"):
                lignes.append(f"- Prompt : {p['prompt_max']} caractères au plus (l'outil refuse au-delà).")
            if p.get("reglages"):
                lignes.append("- Donne chacun des réglages du partenaire (au moins un : l'outil refuse sans).")
            lignes += [f"- {x}" for x in p.get("regles") or []]
    if ecartes:
        lignes += ["" if lignes else None, "## Partenaires écartés au cadrage",
                   "L'utilisateur a décidé de ne pas utiliser : " + ", ".join(ecartes) + ". N'en appelle aucun et ne prépare "
                   "rien pour eux."]
    return "\n".join(x for x in lignes if x is not None)


def message(factory, fiche, tache, brief_du_role, lecons_memoire, glossaire=(), regles=(), regles_projet=(), inscrits=(),
            ecartes=(), metiers_=None):
    """Le message de départ d'un agent. `lecons_memoire` : `{"skill": [...], "genre": [...]}`, déjà filtré sur le
    rôle de l'agent. En cloud, il commence par « Tu repars de zéro. »."""
    parties = _entete(factory, fiche, lecons_memoire, regles_projet, metiers_)
    parties.append("## Le brief de ton rôle\n" + (brief_du_role or "(pas de brief propre à ce rôle)"))
    parties.append("\n".join(["## Ta tâche"] + _bloc_tache(tache)))
    if glossaire:
        parties.append(_vocabulaire(glossaire))
    if regles:
        parties.append(_regles_partenaires(regles))
    if inscrits or ecartes:
        parties.append(_partenaires_inscrits(inscrits, ecartes))
    parties.append(SOBRIETE)
    parties.append(FIN_D_ETAPE)
    if fiche["lieu"] == "cloud":
        parties.append(fin_cloud(tache.get("id", "?")))
    return "\n\n".join(parties) + "\n"


def compte_rendu_par_tache(cle):
    """La consigne d'enchaînement d'un lot : chaque tâche est marquée active à son début et rendue à sa fin (sa durée
    sert à répartir le coût du lot)."""
    return ("Enchaîne ces tâches d'une traite, dans cet ordre, avec ce même contexte. La première est déjà marquée "
            "comme la tienne. **À la fin de chaque tâche, rends compte avant de passer à la suivante** : `lancer tache` "
            "avec son `id` (journal, `colonne`, `active: false`), puis marque aussitôt la suivante : `lancer tache` "
            f'avec `{{"id": <son id>, "agent": "{cle}", "active": true}}`, et seulement ensuite commence-la.')


COMPTE_RENDU_MOTEUR = ("Enchaîne ces tâches d'une traite, dans cet ordre, avec ce même contexte. Ne lance aucune commande "
                       "de la factory (`lancer …`) : le moteur tient le suivi d'après ton rapport. Rends **un seul "
                       "rapport**, à la fin du lot : dans `message`, le résultat de chaque tâche (par son identifiant) ; "
                       "l'`element` de chaque fichier et de chaque verdict ; et, pour chaque élément, son compte rendu "
                       'à part dans `comptes_rendus` : `[{"element": <id>, "texte": "…", "images": [{"chemin", '
                       '"legende"}]}]` (le Directeur ne voit que celui de l\'élément qu\'il valide).')


def message_lot(factory, fiche, taches, briefs, lecons_memoire, glossaire=(), regles=(), par_le_moteur=False,
                regles_projet=(), inscrits=(), ecartes=(), metiers_=None):
    """Le message de départ d'un lot : un seul message pour toutes les tâches, dans l'ordre du lot. `briefs` : liste de
    `(rôle, texte | None)`, un par rôle présent dans le lot. `par_le_moteur` : le moteur procédural lance le lot et
    tient le suivi d'après le rapport (aucun `lancer tache` demandé à l'agent)."""
    parties = _entete(factory, fiche, lecons_memoire, regles_projet, metiers_)
    if len(briefs) == 1:
        parties.append("## Le brief de ton rôle\n" + (briefs[0][1] or "(pas de brief propre à ce rôle)"))
    else:
        parties.append("## Les briefs des rôles de ce lot\n" + "\n\n".join(
            f"### Rôle : {role}\n{texte or '(pas de brief propre à ce rôle)'}" for role, texte in briefs))
    lignes = [f"## Tes {len(taches)} tâches, dans l'ordre",
              COMPTE_RENDU_MOTEUR if par_le_moteur else compte_rendu_par_tache(fiche["cle"])]
    for k, tache in enumerate(taches, 1):
        lignes.append(f"\n### Tâche {k} sur {len(taches)}")
        lignes += _bloc_tache(tache)
    parties.append("\n".join(lignes))
    if glossaire:
        parties.append(_vocabulaire(glossaire))
    if regles:
        parties.append(_regles_partenaires(regles))
    if inscrits or ecartes:
        parties.append(_partenaires_inscrits(inscrits, ecartes))
    parties.append(SOBRIETE)
    parties.append(FIN_D_ETAPE.replace("## À la fin de ton étape", "## À la fin de ton lot")
                   .replace("1. **Le résultat** de la tâche :", "1. **Le résultat** de chaque tâche :", 1))
    if fiche["lieu"] == "cloud":
        parties.append(fin_cloud(taches[0].get("id", "?")))
    return "\n\n".join(parties) + "\n"
