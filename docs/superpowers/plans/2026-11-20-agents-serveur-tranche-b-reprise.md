# Tranche B (agents sur le serveur) : où nous en sommes (2026-11-20)

Note de reprise. Plan d'origine : `2026-11-20-agents-serveur-tranche-b.md` ; documentation : `docs/serveur-agents.md`.

## État du code
- Branche `agents-serveur-b`, worktree `.claude/worktrees/agents-serveur-b`, HEAD `4bf9bf0` (plus de 25 commits depuis `fdd0933`), **jamais poussée ni fusionnée**.
- Les 9 tâches sont faites, relues (par tâche, puis relecture finale de toute la branche, puis une vague de corrections unique et sa relecture ciblée). Suite complète : **4 373 tests, 0 échec** (747 s ; `test_serveur_enveloppe` est instable sous charge, il passe seul).
- Registre des décisions et des points laissés de côté : `.superpowers/sdd/2026-11-20-agents-serveur-tranche-b/progress.md` (ignoré par Git, dans le worktree). À relire avant de reprendre.

## Essais réels sur le serveur (accord du Directeur donné le 2026-11-20 : « on passe aux essais réels »)
Fait :
- Capacité `agent` installée (image `myiafactory/agent`, 2 min 52 ; Claude Code 2.1.328 ; pas de curl/wget ; réseau `myiafactory-agents`). `ptrace_scope` du serveur = 1.
- Jeton d'abonnement enregistré par le Directeur (`~/agent-identifiants/jeton`, 0600 dans un dossier 0700) ; **test d'authentification réussi** depuis le conteneur (`claude -p` répond). Le Directeur a eu du mal à copier le jeton (collage impossible dans PowerShell ; deux lignes à rejoindre ; le « code » du navigateur contient un `#` et n'est pas le jeton) : la procédure `nano` est dans `docs/serveur-agents.md`, à y ajouter (voir « À faire »).
- **Palier 1 (agent seul) réussi** : tâche `agent/essai-doc-170543` sur un dépôt jetable (`C:\Users\maxim\EssaisMyIAFactory\essai-agent-seul`), 38 s de bout en bout, branche rapatriée, commit par « Agent serveur MyIAFactory », conteneur disparu, aucune trace du jeton dans les journaux du serveur.
- Défense du secret : l'agent a exécuté `env` ; **`CLAUDE_CODE_OAUTH_TOKEN` n'apparaît pas** dans l'environnement de ses commandes (Claude Code le retire). Un agent qui lit `/run/identifiants/jeton` n'a pas affiché le jeton lors du seul essai (le modèle ne l'a pas fait : 0 commit) : **le contrôle de secret du serveur n'a donc pas encore été déclenché pour de vrai**.

Pas encore fait :
- Palier 2 : agent **pilote** (lance l'appli de MyFridgeCleaner et décrit l'écran, par le pont hôte). Pré-requis déjà en place : accord `recette-emulateur = serveur` dans `EssaisMyIAFactory/MyFridgeCleaner/.factory/reglages.json`, image émulateur installée.
- Palier 3 : bascule entre lieux (places locales pleines → serveur ; serveur hors ligne → file avec raison) et **Arrêter depuis le bureau** pendant que l'agent pilote (agent + pont + émulation s'arrêtent, deux créneaux libérés). Demande de faire tourner le bureau/moteur depuis le worktree.
- Un essai qui déclenche vraiment le contrôle de secret (forcer l'écriture du jeton dans un commit ou une sortie, sans jamais afficher la sortie).
- Les chemins Linux listés dans `docs/serveur-agents.md` (« Non vérifié sur un vrai serveur ») restent à observer au fil des paliers.

## Avant de continuer
- **Révoquer** sur https://claude.ai/settings/claude-code tous les jetons créés pendant la mise en place, en particulier celui qui a été collé dans la conversation (`sk-ant-oat01-Ayk…`, valable un an). Le jeton actuellement sur le serveur est un autre jeton, valide. Aussi : clés OVH collées dans le chat plus tôt, sauvegarde de `id_ed25519_myiafactory`.
- Nettoyage à faire en fin d'essais : `~/taches/*` sur le serveur (4 tâches, 15 Mo), dépôt jetable `C:\Users\maxim\EssaisMyIAFactory\essai-agent-seul`, scripts d'essai du scratchpad.
- Ne rien pousser sans demande : pousser la branche, ouvrir la PR, fusionner, mettre `main` à jour, redémarrer le bureau.

## Décisions et limites (toutes dans le registre)
- Réseau sortant des agents **ouvert** (décision R5 : défaut du plan ; liste blanche vers l'API de Claude écartée, à rouvrir avant des projets sensibles).
- Réglage des places appelable par un agent local (M8) : accepté et documenté ; le plafond d'abonnement du bureau est protégé.
- Projets homonymes identifiés par nom de dossier (M-a), agents serveur non proposés par l'installation (M-k), etc. : voir le registre.

## À faire après les essais
1. Ajouter à `docs/serveur-agents.md` la procédure de copie du jeton qui a marché (`nano`, deux lignes jointes, pas d'espace, jeton complet d'environ 108 caractères ; le test d'authentification est le seul vrai contrôle ; un jeton coupé à la première ligne est accepté par le script mais refusé par l'API).
2. Durcir `serveur_ovh/taches/enregistrer_jeton.sh` : refuser un jeton qui ne commence pas par `sk-ant-oat01-` ou qui est trop court (66 caractères acceptés à tort lors de l'essai).
3. **Suite complète trop lente** (747 s au lieu d'environ 4 min) : cinq modules `serveur_*` pèsent environ 2 300 s cumulées (vrais bash/Git sous Windows). Profiler, puis réduire ou marquer « lents » (ou déporter : voir ci-dessous). Le Directeur est mécontent de cette durée.
4. Évaluation « tests sur le serveur » (carte de session préparée, document de conception `docs/superpowers/specs/2026-11-20-tests-sur-le-serveur-design.md` non commité dans une autre session) : le Directeur veut mesurer **à la fin de la tranche B, pas avant**, avec son accord.
5. Pousser, PR, fusion, `main` à jour, redémarrage du bureau, sur demande.
