# L'orchestrateur procédural — plan d'implémentation

> **Pour les agents qui exécutent :** sous-compétence requise : superpowers:subagent-driven-development (conseillé) ou superpowers:executing-plans, tâche par tâche. Les étapes se cochent (`- [ ]`). Le découpage en phases par modèle est dans `2026-11-11-orchestrateur-procedural-passation.md`.

**But :** un moteur Python qui remplace la conversation orchestratrice : il traite seul le déterministe et n'appelle l'IA qu'en appels courts à contexte neuf pour le jugement ; un banc d'essai qui le compare à l'orchestrateur actuel et à un agent seul.

**Architecture :** un paquet `moteur/` (couche d'appel, appels de jugement, rapport structuré des agents, table de règles, boucle) qui passe toujours par `orchestrateur.outil.executer(chemin_factory, ["lancer", nom], entree)` ; un paquet `banc/` (scénario, rejoueur d'agents, agent seul, mesure de référence, rapport). Les données d'un vrai essai restent hors dépôt (`~/MyIAFactory/bancs/`).

**Pile :** Python 3.12, bibliothèque standard seulement (`py -3.12`), `unittest` ; la CLI `claude` (`claude -p`) ; en option l'API Messages d'Anthropic par `urllib`.

**Conception :** `docs/superpowers/specs/2026-11-11-orchestrateur-procedural-design.md` (à lire en entier avant toute tâche), avec `orchestrateur/consignes.md` et `orchestrateur/interface.md`.

## Contraintes globales

- Python 3.12, bibliothèque standard seulement ; tests `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"`, tous verts à chaque commit.
- Le moteur n'écrit dans un projet **que** par `lancer <commande>` (fonction `executer`), jamais par les fonctions internes de `outil.py` : un adaptateur de projet reste respecté.
- **Aucun appel réel** à `claude` ni à l'API dans les tests : la couche d'appel et le lanceur d'agents prennent un exécuteur injectable.
- Fable n'est jamais choisi par le moteur (refus en code avant tout appel).
- Aucune valeur de clé (`ANTHROPIC_API_KEY`, clés de partenaires) écrite, affichée, journalisée, ni passée en argument de ligne de commande.
- La couche API n'est utilisée que si les réglages du projet l'activent (`"moteur": {"couche": "api"}`) **et** que la clé est dans l'environnement ; sinon `claude -p`.
- Rien de propre à un essai réel dans le dépôt (nom, rapports, images, chemins) ; les tests n'utilisent que le scénario synthétique.
- Les textes destinés à l'utilisateur : en français, sans jargon.
- Les agents de production restent sur `claude -p`, jamais avec l'option qui contourne toutes les autorisations ; outils autorisés par rôle.

## Points d'attention de la relecture

1. **Une réponse de jugement invalide deux fois** (JSON cassé, action hors liste) : le moteur pose une question au Directeur au lieu de boucler ou de se taire. (Tâche 3 : `test_reponse_invalide_deux_fois_devient_question`.)
2. **Un agent qui ne rend pas de bloc JSON** (sortie libre, coupée, code d'erreur, délai) : la tâche est relancée une fois puis passe bloquée avec la raison au journal ; l'usage de l'appel raté est quand même noté. (Tâche 5 : `test_agent_sans_bloc_relance_puis_bloque`, `test_usage_note_meme_en_echec`.)
3. **Le moteur arrêté puis relancé** pendant qu'un agent tournait : la tâche active sans processus est relancée une fois, une demande déjà traitée n'est pas retraitée. (Tâche 7 : `test_reprise_relance_tache_orpheline`, `test_demande_traitee_pas_rejouee`.)
4. **Deux projets au bureau, l'un en pause** : la pause de l'un n'arrête pas l'autre ; aucune étape nouvelle dans le projet en pause, ses demandes sont quand même traitées. (Tâche 7 : `test_pause_par_projet`.)
5. **La clé API absente alors que les réglages demandent l'API** : bascule sur `claude -p`, une seule ligne au bureau, aucun plantage. (Tâche 2 : `test_api_sans_cle_bascule_une_fois`.)

---

## Étape 1 — la couche d'appel et le jugement

### Tâche 1 : mesurer un appel vide

**Fichiers :**
- Créer : `outils/mesurer_appel.py`
- Modifier : `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` (section « Mesures »)

Pas de test : c'est une mesure qui fixe la commande de la tâche 2.

- [x] **Étape 1 : lire `claude --help`** et retenir les options qui coupent les outils, le prompt système par défaut, les serveurs MCP et les réglages du dossier, et la sortie JSON (`--output-format json`, `--model`).
- [x] **Étape 2 : écrire `outils/mesurer_appel.py`** : lance 3 fois, sur Haiku puis Sonnet, `claude -p` avec la commande la plus dépouillée trouvée et le prompt « Réponds {"ok":true} », dans un dossier temporaire vide ; affiche par appel les tokens d'entrée, de cache (lecture, écriture), de sortie et `total_cost_usd`.
- [x] **Étape 3 : lancer** `py -3.12 outils/mesurer_appel.py` et noter dans la passation : la commande retenue, les tokens d'un appel vide, son coût. Règle : si un appel vide Haiku coûte plus de 0,004 $ (soit 25 appels pour 0,10 €), écrire « couche API conseillée » dans la passation.
- [x] **Étape 4 : commit** `git add outils/mesurer_appel.py docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` puis `git commit -m "Moteur : mesure d'un appel claude -p vide"`.

### Tâche 2 : la couche d'appel

**Fichiers :**
- Créer : `moteur/__init__.py`, `moteur/appel.py`
- Test : `tests/test_moteur_appel.py`

**Interfaces :**
- Produit :
  - `Usage = dict` avec les clés `modele, entree, sortie, cache_lecture, cache_ecriture` (entiers) ;
  - `class Reponse: texte: str, usage: Usage, session: str | None` ;
  - `appeler(consigne: str, dossier: str, modele: str, *, couche: str = "claude", executer=None, outils: list[str] | None = None, dossier_travail: str | None = None, reprendre: str | None = None, delai_s: int = 600) -> Reponse` ; lève `ErreurAppel(raison: str)` ;
  - `choisir_couche(reglages: dict, environ: dict) -> tuple[str, str | None]` : `("api", None)`, `("claude", None)` ou `("claude", "<ligne à dire au bureau>")`.
- `modele` est `"haiku"`, `"sonnet"` ou `"opus"` ; `"fable"` lève `ErreurAppel` avant tout appel.
- `executer(argv: list[str], entree: bytes, env: dict, cwd: str | None, delai_s: int) -> tuple[int, bytes]` pour `claude` ; pour l'API, `executer(url: str, corps: bytes, entetes: dict) -> tuple[int, bytes]`.

- [x] **Étape 1 : écrire les tests qui échouent**

```python
def test_claude_p_rend_texte_et_usage(self):
    sortie = json.dumps({"result": '{"ok": true}', "session_id": "s1", "modelUsage": {"claude-haiku-5-5": {
        "inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 100, "cacheCreationInputTokens": 7}}}).encode()
    r = appel.appeler("consigne", "dossier", "haiku", executer=lambda *a: (0, sortie))
    self.assertEqual(r.texte, '{"ok": true}')
    self.assertEqual(r.usage, {"modele": "claude-haiku-5-5", "entree": 10, "sortie": 5, "cache_lecture": 100, "cache_ecriture": 7})
    self.assertEqual(r.session, "s1")

def test_consigne_et_dossier_passent_par_l_entree_pas_par_argv(self):
    vu = {}
    def ex(argv, entree, env, cwd, delai):
        vu.update(argv=argv, entree=entree); return 0, SORTIE_OK
    appel.appeler("CONSIGNE", "DOSSIER", "haiku", executer=ex)
    self.assertNotIn("DOSSIER", " ".join(vu["argv"]))
    self.assertIn(b"DOSSIER", vu["entree"])

def test_fable_refuse_avant_appel(self):
    with self.assertRaises(appel.ErreurAppel):
        appel.appeler("c", "d", "fable", executer=lambda *a: self.fail("appelé"))

def test_code_non_nul_leve(self):
    with self.assertRaises(appel.ErreurAppel):
        appel.appeler("c", "d", "haiku", executer=lambda *a: (1, b"boom"))

def test_api_rend_texte_et_usage_sans_cle_dans_les_erreurs(self):
    ...  # executer API rend 200 et un corps Messages ; usage lu dans "usage" ; une erreur 401 lève ErreurAppel
         # dont le message ne contient pas la valeur de la clé ("sk-test-123")

def test_api_sans_cle_bascule_une_fois(self):
    self.assertEqual(appel.choisir_couche({"moteur": {"couche": "api"}}, {})[0], "claude")
    self.assertIsNotNone(appel.choisir_couche({"moteur": {"couche": "api"}}, {})[1])
    self.assertEqual(appel.choisir_couche({"moteur": {"couche": "api"}}, {"ANTHROPIC_API_KEY": "x"}), ("api", None))
    self.assertEqual(appel.choisir_couche({}, {"ANTHROPIC_API_KEY": "x"}), ("claude", None))
```

- [x] **Étape 2 : lancer** `py -3.12 -m unittest tests.test_moteur_appel -v` : échec (module absent).
- [x] **Étape 3 : écrire `moteur/appel.py`** : la commande `claude` est celle notée en tâche 1 ; la consigne passe en prompt système par fichier temporaire ou entrée standard, le dossier par l'entrée standard ; `reprendre` ajoute la reprise de session (pour l'agent seul du banc) ; `outils` vide = aucun outil. Modèles API : `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5` ; la clé est lue dans `os.environ` au moment de l'appel. Si la forme exacte de `--output-format json` diffère du test (noms des champs d'usage), aligner le test sur la sortie réelle relevée en tâche 1.
- [x] **Étape 4 : lancer les tests** : verts.
- [x] **Étape 5 : commit** `Moteur : la couche d'appel (claude -p, API en option)`.

### Tâche 3 : les appels de jugement

**Fichiers :**
- Créer : `moteur/jugement.py`, `moteur/consignes/decouper.md`, `traduire_retour.md`, `ecrire_methode.md`, `apres_refus.md`, `conseil.md`
- Test : `tests/test_moteur_jugement.py`

**Interfaces :**
- Consomme : `appel.appeler`, `appel.ErreurAppel`.
- Produit :
  - `TYPES = {"decouper": "sonnet", "traduire_retour": "haiku", "ecrire_methode": "sonnet", "apres_refus": "haiku", "conseil": "haiku"}` ;
  - `juger(type_: str, dossier: dict, *, couche: str, appeler=appel.appeler, modele: str | None = None) -> Decision` ;
  - `class Decision: objet: dict | None, usages: list[Usage], question: str | None` (exactement un de `objet` / `question` non nul) ;
  - `ACTIONS_CONSEIL = ("repondre", "transmettre_agent", "poser_decision", "lancer", "rien")`.
- Formes rendues (validées par `valider(type_, objet) -> str | None`, le message d'erreur ou `None`) :
  - `decouper` : `{"elements": [{"id", "nom", "groupe"}], "prototype": id, "depend_de": {id: [id]}, "reprendre_methode": null | {"fonctionnalite", "version", "pourquoi"}, "message": str}` ; `prototype` est un des `id` ;
  - `traduire_retour` : `{"validation": bool, "consigne": str | null}` (consigne obligatoire si `validation` faux) ;
  - `ecrire_methode` : `{"document": str, "briefs": {role: str}, "controles": [{"texte", "origine"}]}` ;
  - `apres_refus` : `{"suite": "corriger" | "methode_a_revoir" | "bloquer", "consigne": str | null, "raison": str}` ;
  - `conseil` : `{"action": une de ACTIONS_CONSEIL, "parametres": dict, "reponse": str}` ; `lancer` exige `parametres.commande` hors `COMMANDES_DU_BUREAU` et hors `lecon`/`genre`.

- [x] **Étape 1 : écrire les tests qui échouent** : une réponse valide par type rend `objet` ; `test_reponse_invalide_redemandee_une_fois` (premier appel invalide, second valide → `objet`, deux usages, le second dossier contient l'erreur) ; `test_reponse_invalide_deux_fois_devient_question` (→ `question` non vide, deux usages) ; `test_json_entoure_de_texte_est_lu` (le bloc ```json … ``` est extrait) ; `test_conseil_refuse_commande_lecon` ; `test_dossier_ne_contient_que_ses_cles` (le texte envoyé ne contient que les clés du dossier, sérialisées une fois).
- [x] **Étape 2 : lancer** : échec.
- [x] **Étape 3 : écrire `moteur/jugement.py` et les cinq consignes.** Chaque consigne fait au plus 40 lignes : ce qu'il faut décider (repris de la section concernée de `consignes.md`), la forme JSON exacte, « réponds seulement par ce JSON ». `decouper` et `ecrire_methode` reprennent mot pour mot les règles de `consignes.md` (élément qui se répète, groupes, méthode écrite, briefs, contrôles de départ). Aucune consigne ne nomme un projet.
- [x] **Étape 4 : lancer les tests** : verts.
- [x] **Étape 5 : commit** `Moteur : les appels de jugement et leurs consignes`.

## Étape 2 — les agents et la table de règles

### Tâche 4 : le rapport structuré des agents

**Fichiers :**
- Modifier : `orchestrateur/depart.py` (consigne de fin d'étape), `orchestrateur/outil.py` (`cmd_usage` : l'agent `orchestrateur` accepté sans fiche)
- Créer : `moteur/rapport.py`
- Test : `tests/test_moteur_rapport.py`, `tests/test_orch_depart.py` (ajouts)

**Interfaces :**
- Produit :
  - `lire(texte: str) -> dict` (lève `RapportIllisible`) : le dernier bloc ```json du texte ; forme `{"statut": "fait" | "accord_requis" | "outil_refuse" | "echec", "message": {"texte", "images"?, "questions"?, "glossaire"?, "attend"}?, "fichiers": [{"chemin", "titre", "element"?, "livrable"?}], "lecons": [{"texte", "roles", "etage_propose", "texte_general"?}], "controles": [{"texte", "origine"}], "retours_factory": [str], "verdicts": [{"element", "conforme": bool, "points": [str]}], "accord": {"quoi", "partenaire", "cout"}?, "outil": str?, "lignes": int?}` ;
  - `commandes(rapport: dict, *, fonctionnalite: str, tache: str, agent: str, etape: str) -> list[tuple[str, dict]]` : les `(commande, entree)` à passer à `lancer`, dans l'ordre : `message`, `document` (un par fichier), `controle`, `lecon` (`action: noter`).
- `depart.message(...)` ajoute à sa consigne de fin le paragraphe « Termine ta réponse par un bloc ```json » avec cette forme, et : « Si une dépense ou un changement de partenaire ou le navigateur demande l'accord de l'utilisateur, arrête-toi et rends `statut: accord_requis` ».

- [x] **Étape 1 : tests qui échouent** : `test_lit_le_dernier_bloc_json`, `test_rapport_sans_bloc_illisible`, `test_commandes_dans_l_ordre` (message puis documents puis contrôles puis leçons, avec `auteur` = l'agent), `test_accord_requis_ne_rend_aucune_commande_de_production`, `test_depart_demande_le_bloc_json` (le message de `lancer depart` contient « bloc ```json » et « accord_requis »), `test_usage_accepte_orchestrateur` (`lancer usage` avec `agent: "orchestrateur"` sur un projet sans cette fiche : code 0).
- [x] **Étape 2 : lancer** : échec.
- [x] **Étape 3 : écrire** `moteur/rapport.py`, la consigne de fin dans `depart.py`, l'exception `orchestrateur` dans `cmd_usage` (constante `AGENT_ORCHESTRATEUR = "orchestrateur"`).
- [x] **Étape 4 : lancer toute la suite** : verte (les tests existants de `depart` restent verts).
- [x] **Étape 5 : commit** `Moteur : le rapport structuré des agents`.

### Tâche 5 : lancer un agent

**Fichiers :**
- Créer : `moteur/agents.py`
- Modifier : `orchestrateur/fiches.py` (ligne `Outils :` facultative d'une fiche)
- Test : `tests/test_moteur_agents.py`

**Interfaces :**
- Consomme : `appel.appeler` (avec `outils`, `dossier_travail`), `rapport.lire`.
- Produit :
  - `OUTILS_PAR_DEFAUT = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(py:*)", "Bash(git:*)"]` ;
  - `class Execution: tache: str, agent: str, lot: str | None, rapport: dict | None, usage: Usage, erreur: str | None` ;
  - `executer_agent(depart: str, matiere: str, *, agent: dict, modele: str, dossier_projet: str, appeler=appel.appeler) -> Execution` (synchrone ; la boucle le met dans un fil) ;
  - `fiches.outils(fiche: dict) -> list[str]` : la ligne `Outils :` séparée par des virgules, sinon `OUTILS_PAR_DEFAUT`.

- [x] **Étape 1 : tests qui échouent** : `test_agent_rend_son_rapport_et_son_usage` ; `test_outils_de_la_fiche_passent_a_l_appel` ; `test_jamais_de_contournement_des_autorisations` (aucun argument de l'appel ne contient `dangerously` ni `bypass`) ; `test_agent_sans_bloc_relance_puis_bloque` (deux sorties sans bloc → `erreur` non nul, deux usages cumulés) ; `test_usage_note_meme_en_echec` ; `test_fable_dans_la_fiche_refuse`.
- [x] **Étape 2 : lancer** : échec.
- [x] **Étape 3 : écrire** `moteur/agents.py` et `fiches.outils`.
- [x] **Étape 4 : lancer** : vert.
- [x] **Étape 5 : commit** `Moteur : lancer un agent sans fenêtre`.

### Tâche 6 : la table de règles

**Fichiers :**
- Créer : `moteur/regles.py`
- Test : `tests/test_moteur_regles.py` (projet minimal de `tests/orch_aide.py`, appels et agents simulés)

**Interfaces :**
- Consomme : `orchestrateur.outil.executer`, `jugement.juger`, `rapport.commandes`.
- Produit :
  - `class Projet: factory: Path, couche: str` et `lancer(projet, nom, entree=None) -> dict` (lève `Refus(message)` sur code 1, `ErreurMoteur` sur code 2) ;
  - `class Action` : `("lancer", nom, entree)`, `("juger", type_, dossier, suite)`, `("agent", agent, taches, matiere)` ;
  - `traiter_demande(projet, demande: dict, etat: dict) -> list[Action]` ;
  - `traiter_retour(projet, execution: agents.Execution, etat: dict) -> list[Action]` ;
  - `avancer(projet, etat: dict) -> list[Action]` (série : `file-prendre`, `lots`, départs ; relecture croisée ; `terminee`) ;
  - `appliquer_jugement(projet, type_, decision, contexte) -> list[Action]`.
- Chaque ligne de la table de la section 4.2 de la conception est une fonction `_sur_<type>` (`_sur_fonctionnalite`, `_sur_message`, `_sur_cahier`, `_sur_methode`, `_sur_lecon`, `_sur_genre`, `_sur_organisation`, `_sur_session_cloud`, `_sur_retour`, `_sur_retour_element`, `_sur_deplacer`, `_sur_bouton`, `_sur_partenaires`, `_sur_challenge`) ; un type inconnu ou un bouton du projet → `("juger", "conseil", …)`.
- Chaque demande se termine par `demande-traitee` avec une `reponse` gabarit (ou celle du jugement).

- [x] **Étape 1 : tests qui échouent**, un par ligne de la table : `test_fonctionnalite_lance_le_cadrage`, `test_cahier_valider_juge_decouper`, `test_decoupage_ecrit_file_et_prototype`, `test_cahier_corriger_rouvre_cadrage`, `test_message_prototype_traduit_puis_transmet`, `test_methode_valider_ecrit_methode_briefs_controles`, `test_lecon_appliquee_sans_ia`, `test_refus_controle_juge_apres_refus`, `test_meme_controle_deux_elements_pose_methode_a_revoir` (sans IA), `test_seuil_methode_sans_ia`, `test_serie_deux_elements_au_plus`, `test_prototype_jamais_parallele`, `test_accord_requis_pose_une_decision`, `test_outil_refuse_pose_une_question`, `test_type_inconnu_demande_conseil`, `test_aucune_demande_sans_reponse` (pour chaque type, la dernière action est `demande-traitee`).
- [x] **Étape 2 : lancer** : échec.
- [x] **Étape 3 : écrire** `moteur/regles.py`. La relecture croisée suit la section « La relecture croisée » de `consignes.md` en code ; « le même contrôle échoue sur deux éléments » se lit dans les `verdicts`.
- [x] **Étape 4 : lancer** : vert.
- [x] **Étape 5 : commit** `Moteur : la table de règles`.

### Tâche 7 : la boucle

**Fichiers :**
- Créer : `moteur/boucle.py`, `moteur/__main__.py`
- Test : `tests/test_moteur_boucle.py`

**Interfaces :**
- Consomme : `regles.*`, `agents.executer_agent`, `jugement.juger`, `orchestrateur.guetteur.ecrire_presence`, la liste des projets de `~/MyIAFactory/bureau.json` (même lecture que le bureau).
- Produit :
  - `class Moteur(projets: list[Projet], *, appeler=appel.appeler, horloge=time.time)` ;
  - `Moteur.tour() -> None` : un passage (présence, demandes, retours d'agents terminés, avancer, commit) ; testable sans fil ;
  - `Moteur.tourner(arret: threading.Event)` : `tour()` toutes les 2 s ;
  - entrée `py -3.12 -m moteur [--bureau ~/MyIAFactory/bureau.json]`.
- Les agents tournent dans des fils (un par exécution) ; leurs `Execution` arrivent dans une file lue par `tour()`.
- Chaque appel (jugement ou agent) → `lancer usage` (jugement : `agent: "orchestrateur"`, `etape: "orchestration"`, la tâche servie ou aucune).
- Commit et push du dépôt du projet après une étape qui produit (même règle que `consignes.md`), message `Factory : <ce qui a été produit>`.
- Partenaires : `partenaires detecter` au démarrage d'un projet, `partenaires quota` à chaque tour (l'outil ne relit qu'une fois par heure) ; jamais de `confirmer` d'office (c'est un geste de l'utilisateur ou d'un agent qui voit les outils).

- [x] **Étape 1 : tests qui échouent** : `test_tour_ecrit_la_presence`, `test_tour_traite_les_messages_d_abord`, `test_usage_de_chaque_jugement_note`, `test_pause_par_projet`, `test_reprise_relance_tache_orpheline`, `test_demande_traitee_pas_rejouee`, `test_feu_vert_faux_ne_lance_rien`, `test_ligne_couche_dite_une_fois` (la ligne de `choisir_couche` part une seule fois au bureau, en `reponse` de la première demande traitée), `test_projet_ajoute_au_bureau_pris_sans_redemarrer`.
- [x] **Étape 2 : lancer** : échec.
- [x] **Étape 3 : écrire** `moteur/boucle.py` et `moteur/__main__.py`.
- [x] **Étape 4 : lancer toute la suite** : verte.
- [x] **Étape 5 : commit** `Moteur : la boucle`.

## Étape 3 — le bureau et l'installation

### Tâche 8 : démarrer le moteur depuis le bureau, l'option API à l'installation

**Fichiers :**
- Modifier : `bureau/demarrage.py`, `bureau/cout.py` et `bureau/kpi.py` (si besoin), `bureau/reglages.py` (clé `moteur.couche` : `"claude"` | `"api"`), `installation/` (la question du paramétrage et son estimation), `skills/installer/SKILL.md`, `orchestrateur/consignes.md`, `docs/orchestrateur.md`
- Test : `tests/test_serveur.py`, `tests/test_reglages.py`, `tests/test_inst_proposition.py`, `tests/test_orch_consignes.py` (ajouts)

**Interfaces :**
- `demarrage.demarrer(reglages, ...)` démarre `py -3.12 -m moteur` sans fenêtre s'il ne tourne pas (un seul moteur : verrou `~/MyIAFactory/moteur.pid`), et rend `{"ok": True, "message": "L'orchestrateur démarre."}`, pour tous les projets, cloud compris. `claude` se cherche comme `moteur.appel.trouver_claude()` (PATH, puis l'installation de l'application).
- La proposition d'installation porte `moteur: {"couche": "claude" | "api", "ecart_estime": str}` ; la question : « Utiliser une clé API Anthropic pour les décisions de l'orchestrateur ? Elle est facturée à part de votre abonnement ; écart estimé : … ». Défaut `claude`. Jamais de clé demandée dans la discussion : l'utilisateur la met lui-même dans son environnement.
- `consignes.md` : un premier paragraphe dit que le moteur procédural applique ces consignes (local et cloud), et que la conversation orchestratrice ne sert plus qu'aux projets à adaptateur pas encore passés au moteur.

- La facturation du bureau montre l'orchestration à part : les usages de l'agent `orchestrateur` forment une ligne « Orchestration » distincte de la production (`bureau/cout.py`, `bureau/kpi.py` et la page s'ils ne le font pas déjà par agent).

- [ ] **Étape 1 : tests qui échouent** : `test_facturation_isole_l_orchestration`, `test_demarrer_lance_le_moteur_une_fois`, `test_projet_cloud_passe_aussi_par_le_moteur`, `test_reglage_couche_valide` (refus d'une autre valeur), `test_proposition_pose_la_question_api_defaut_claude`, `test_consignes_mentionnent_le_moteur`.
- [ ] **Étape 2 : lancer** : échec.
- [ ] **Étape 3 : écrire** les modifications.
- [ ] **Étape 4 : lancer toute la suite (Python et page)** : verte.
- [ ] **Étape 5 : commit** `Moteur : démarrage depuis le bureau, option API au paramétrage`.

### Tâche 12 : les agents cloud

**Fichiers :**
- Créer : `moteur/cloud.py`
- Modifier : `moteur/boucle.py` (départs et retours cloud), `moteur/regles.py` (lieu `cloud` : plus de décision `session_cloud`), `orchestrateur/depart.py` (consigne de fin d'un agent cloud), `bureau/reglages.py` (`agents_cloud_max`, 3 par défaut), `installation/` (prérequis GitHub et `claude` connecté quand le cloud est choisi)
- Test : `tests/test_moteur_cloud.py`, ajouts à `tests/test_moteur_boucle.py` et `tests/test_orch_depart.py`

**Interfaces :**
- Consomme : `appel.trouver_claude`, `rapport.lire`, `regles.lancer`.
- Produit :
  - `lancer_session(depart: str, *, dossier_projet: str, modele: str, executer=None) -> dict` : pousse le dépôt, lance `claude --cloud`, rend `{"session", "adresse"}` ; lève `ErreurCloud` ;
  - `envoyer_suite(session: str, texte: str, *, executer=None) -> None` (`claude -p … --cloud <session>`) ;
  - `chercher_rapports(dossier_projet: str, taches: list[str], *, executer=None) -> dict[str, tuple[str, dict]]` : après `git fetch`, pour chaque tâche dont `.factory/rapports/<tâche>.json` existe sur une branche `claude/…`, `(branche, rapport)` ;
  - `fusionner(dossier_projet: str, branche: str, *, executer=None) -> str | None` : `None` si fusionnée et poussée, sinon la raison (conflit : fusion annulée, rien de cassé).
- `depart.message` pour une fiche de lieu `cloud` : « Tu repars de zéro », puis la consigne de committer et pousser le rapport structuré dans `.factory/rapports/<tâche>.json`, avec `usage_estime` (tokens).
- Usage d'un agent cloud : `lancer usage` avec `total` = `usage_estime` (estimé).
- Avant d'écrire `lancer_session`, vérifier dans `claude --help` si `--cloud` accepte `--model` ; sinon noter le modèle par défaut sur la tâche et l'écrire dans la passation.

- [ ] **Étape 1 : tests qui échouent** : `test_lancer_session_pousse_puis_lance`, `test_lancer_session_rend_session_et_adresse`, `test_rapport_trouve_sur_branche_claude`, `test_rapport_absent_rien_rendu`, `test_fusion_conflit_annule_et_rend_raison`, `test_retour_cloud_applique_puis_fusionne`, `test_conflit_pose_decision_avec_adresse`, `test_usage_cloud_estime`, `test_accord_cloud_envoie_suite_meme_session`, `test_limite_agents_cloud`, `test_session_muette_deux_heures_pose_decision`, `test_sans_github_bascule_en_local_et_le_dit`, `test_depart_cloud_demande_rapport_commite`.
- [ ] **Étape 2 : lancer** : échec.
- [ ] **Étape 3 : écrire** `moteur/cloud.py` et les modifications.
- [ ] **Étape 4 : lancer toute la suite** : verte.
- [ ] **Étape 5 : commit** `Moteur : les agents cloud (sessions Claude Code, coût estimé)`.

## Étape 4 — le banc d'essai

### Tâche 9 : le scénario et le rejoueur

**Fichiers :**
- Créer : `banc/__init__.py`, `banc/scenario.py`, `banc/rejoueur.py`, `banc/exemples/synthetique.json`
- Test : `tests/test_banc_scenario.py`

**Interfaces :**
- Format (`version: 1`) : `{"version", "projet": {...factory minimale...}, "gestes": [{"apres": "attente_utilisateur" | "immediat", "demande": {...}}], "rapports": [{"etape", "role", "rang", "texte", "fichiers": [{"chemin", "contenu_base64"}], "usage": Usage}], "attendu": [str]}`.
- `charger(chemin) -> Scenario` ; `Scenario.prochain_geste(etat) -> dict | None` ; `class Rejoueur(scenario)` avec la signature d'`agents.executer_agent` : rend le rapport de (étape, rôle, rang), sinon un rapport `fait` vide et note un **écart** (`Rejoueur.ecarts: list[str]`).
- `banc/exemples/synthetique.json` : une fonctionnalité de 2 éléments, un cahier corrigé une fois, un contrôle refusé ; aucun mot d'un essai réel.

- [ ] **Étape 1 : tests qui échouent** : `test_synthetique_charge`, `test_rejoueur_rend_le_rapport_par_rang`, `test_rejoueur_note_un_ecart`, `test_moteur_va_au_bout_du_synthetique` (moteur + rejoueur + jugements simulés : toutes les demandes traitées, fonctionnalité `terminee`).
- [ ] **Étape 2 à 5 : lancer (échec), écrire, lancer (vert), commit** `Banc : scénario et rejoueur`.

### Tâche 10 : construire un scénario d'essai réel, mesure de référence, agent seul, rapport

**Fichiers :**
- Créer : `banc/construire.py`, `banc/reference.py`, `banc/agent_seul.py`, `banc/rapport.py`, `banc/__main__.py`
- Test : `tests/test_banc_outils.py` (sur des transcriptions et un suivi fabriqués dans un dossier temporaire)

**Interfaces :**
- `construire(dossier_factory: Path, transcriptions: Path, sortie: Path)` : lit `demandes.jsonl`, le suivi et les rapports des sous-agents dans les transcriptions ; écrit le scénario **et refuse une `sortie` à l'intérieur du dépôt** (`ErreurBanc`).
- `reference(transcription: Path) -> dict` : `{"appels", "tokens", "par_modele": {modele: Usage}}` de la conversation orchestratrice (sous-agents exclus) ; le coût en euros vient de `bureau/prix.py` et `bureau/cout.py`.
- `agent_seul(scenario, dossier_vide: Path, *, appeler=appel.appeler) -> dict` : une conversation `claude -p` reprise à chaque geste, Sonnet 5.5, outils par défaut ; compte les appels, l'usage, les questions (une réponse qui attend l'utilisateur).
- `rapport(resultats: dict, attendu: list[str]) -> str` (Markdown) : par façon de faire, appels, tokens, coût, part orchestration / production, questions, attendu coché, écarts ; et les trois objectifs (≤ 0,10 €, total moteur < agent seul, même résultat) marqués tenus ou non.
- `py -3.12 -m banc construire|moteur|agent-seul|rapport …` ; sorties sous `~/MyIAFactory/bancs/<nom>/`.

- [ ] **Étape 1 : tests qui échouent** : `test_construire_refuse_une_sortie_dans_le_depot`, `test_reference_exclut_les_sous_agents`, `test_reference_compte_un_appel_par_message`, `test_agent_seul_compte_les_questions`, `test_rapport_marque_les_objectifs`.
- [ ] **Étape 2 à 5 : lancer (échec), écrire, lancer (vert), commit** `Banc : construire, référence, agent seul, rapport`.

## Étape 5 — le vrai passage (avec l'utilisateur)

### Tâche 11 : le banc sur l'essai de référence

Pas de code nouveau, sauf corrections ; chaque correction suit le cycle test → code → commit.

- [ ] **Étape 1 : construire le scénario** de l'essai de référence (son suivi et ses transcriptions sont hors dépôt ; leurs chemins sont dans la passation, jamais dans le dépôt) : `py -3.12 -m banc construire …`.
- [ ] **Étape 2 : mesure de référence** : `py -3.12 -m banc reference …` ; attendu : environ 97 appels et environ 1,76 €.
- [ ] **Étape 3 : moteur avec rejoueur** : `py -3.12 -m banc moteur …` ; lire le rapport. Si l'orchestration dépasse 0,10 €, regarder quel type d'appel coûte, resserrer son dossier ou sa consigne, et recommencer (au plus 3 tours, chacun noté dans la passation) ; si l'appel vide est en cause, proposer à l'utilisateur la couche API.
- [ ] **Étape 4 : passage complet en vrai, avec l'accord de l'utilisateur** (il coûte une vraie production) : moteur avec vrais agents, puis agent seul, sur une copie vide du projet. Rapport final.
- [ ] **Étape 5 : écrire le bilan** dans la passation (chiffres, objectifs tenus ou non) ; commit des seules corrections et de la passation.
