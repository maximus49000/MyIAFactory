# Sessions cloud : création automatique ou démarche simplifiée — conception (2026-11-12)

Suite de `2026-11-12-recrutement-design.md` (point 8) : le moteur lance lui-même `claude --cloud "<départ>" --model m`.

## 1. Le constat

Claude Code 2.1.321 (Windows), lancé par le moteur (détaché, sans console) :

> Error: --cloud requires an interactive terminal. Non-interactive invocations (piped stdout, --init-only, --sdk-url)
> run locally and would silently ignore --cloud. Drop --cloud, or run from a TTY.

Tout départ cloud échoue donc ; `claude -p … --cloud <session>` (`envoyer_suite`) est, par construction, une invocation
non interactive : refus attendu aussi (non vérifié, faute de session créée). Le moteur traduit ce refus en une raison
claire (`cloud.SANS_TERMINAL`).

## 2. Le faux terminal (`moteur/pseudo_terminal.py`)

Pseudo-console Windows (ConPTY) par `ctypes` : `CreatePipe` ×2, `CreatePseudoConsole`, `STARTUPINFOEX` avec
`PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE` (flux standard nuls : la commande ne voit que la pseudo-console), `CreateProcessW`,
lecture dans un fil, `TerminateProcess` au délai ou à l'arrêt demandé, puis `ClosePseudoConsole`. Aucune fenêtre (la
pseudo-console n'a pas d'écran), y compris depuis un processus sans console. `lancer(argv, cwd, delai_s, env, entree,
arret, repondre)` rend `Resultat(code, texte, brut, fini, arrete)` ; `nettoyer` retire les séquences d'échappement
(couleurs, titres, positionnement ; les liens OSC 8 gardent leur adresse). Hors Windows : `disponible()` faux,
`PseudoTerminalIndisponible`. `environnement_sans` retire la clé API et, si le moteur a été lancé depuis une session de
Claude Code (`CLAUDECODE`), les variables `CLAUDE…`/`ANTHROPIC…` de cette session hôte.

## 3. L'essai réel (2026-11-12, dépôt de test privé, Haiku, message « lis la liste des fichiers… ne modifie rien »)

Quatre lancements de `claude --cloud … --model haiku` dans la pseudo-console ; **aucune session n'a été créée**.

1. La commande **accepte** la pseudo-console (pas d'erreur « interactive terminal »).
2. Avec l'environnement d'une session Claude Code hôte, puis avec un environnement propre : la CLI n'avait jamais été
   utilisée en terminal sur ce poste, elle ouvre l'accueil : « Welcome to Claude Code v2.1.321 … Let's get started.
   Choose the text style that looks best with your terminal » (thème, Entrée = le thème proposé), puis « Security notes:
   … Press Enter to continue… ». Ces deux écrans ont reçu Entrée (sans risque) ; la CLI a noté l'accueil fait dans
   `~/.claude.json` (`hasCompletedOnboarding`).
3. Puis : « Accessing workspace: <dossier> — Quick safety check: Is this a project you created or one you trust? …
   ❯ No, exit / Yes, I trust this folder — Enter to confirm · Esc to cancel ». **Non répondu** (une approbation de
   sécurité appartient à l'utilisateur) : la commande est restée sur cet écran jusqu'au délai (150–180 s), puis le
   processus local a été arrêté. Ni identifiant ni adresse de session affichés.
4. Inconnu à ce jour : ce qui suit l'approbation (choix d'environnement cloud, accès GitHub, confirmation), si la
   commande rend la main après avoir affiché la session, et `envoyer_suite` sous pseudo-console.

**Conclusion** : la création automatique ne marche pas telle quelle. Le faux terminal reste derrière un essai unique
documenté : `cloud.essai_pseudo_terminal` (répond seulement aux écrans sans risque, s'arrête sur toute demande à
l'utilisateur ou peu après l'adresse de la session) et `outils/essai_session_cloud.py <dossier>`, à relancer après avoir
lancé une fois `claude` dans le dossier du projet et répondu « Yes, I trust this folder ». Il n'est pas branché dans
`lancer_session` ; s'il crée un jour la session, le brancher avec repli sur la démarche ci-dessous.

## 4. La démarche simplifiée (secours, et seule voie aujourd'hui)

- **Départ** : `lancer_session` échoue (raison claire) ; si l'agent a une session inscrite (`etat["sessions_cloud"]`, ou
  la table des sessions quand elle a la forme d'une session), le moteur y envoie le départ (`envoyer_suite`) et relève
  cette session. Sinon, ou si cet envoi échoue aussi : nouvel essai, puis tâche bloquée (règle existante).
- **Décision** `session_cloud` (une par agent) : en plus de `agent` et `texte`, `tache`, `depart` (le message de départ
  complet, recalculé par `lancer depart`, 24 000 caractères au plus), `lien` (`https://claude.ai/code`, ou l'adresse de la
  session déjà inscrite pour l'agent), `depot` (l'URL GitHub) et `modele`. Vérifiés par l'outil et par le relevé.
- **Page** (bureau du Directeur, « Sessions cloud à créer ») : lien (nouvel onglet, https seulement), dépôt, modèle,
  message en zone de texte en lecture seule avec « Copier le message » (repli `execCommand` hors contexte sécurisé,
  au téléphone en http), champ « adresse ou identifiant », « C'est fait ». Une décision d'avant (sans `depart`) garde son
  champ de nom.
- **Demande** `session_cloud` : si la décision porte `tache`, `session` doit être `https://claude.ai/code/<id>` ou un
  identifiant (`session_…`, UUID) — même règle en JS (`lireSession`), au bureau (`demandes.py`) et au moteur
  (`cloud.lire_session`).
- **Moteur** (`regles._sur_session_cloud`) : inscrit la session (`lancer session`, l'adresse), lève la décision, et pour
  la tâche de la décision : débloquée, active, journal « Session cloud <id> (<modèle>) : <adresse> » (retrouvé au
  redémarrage), `etat["cloud"][tâche]` posé : la relève par le dépôt et la fusion suivent comme pour un départ
  automatique, sans nouveau lancement. Les autres tâches bloquées de l'agent repartent (et vont à cette session).

## 5. Mesure

Tests : `test_pseudo_terminal` (vraie pseudo-console sur Windows : sortie, code, terminal vu par la commande, entrée,
réponse à un écran, délai, arrêt, environnement), `test_moteur_cloud` (`lire_session`, refus sans terminal, faux
terminal simulé, secours de bout en bout, session inscrite refusée), `test_recrutement`, `test_orch_suivi`,
`test_releve`, `test_demandes`, page (`decisions.test.js`, `actions.test.js`).
