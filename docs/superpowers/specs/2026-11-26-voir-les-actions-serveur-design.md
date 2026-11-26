# Voir les actions du serveur — conception (2026-11-26)

## Intention et pourquoi

Quand un agent travaille sur le serveur, le bureau ne montre rien : il ne sait que « en cours » et une durée. Le Directeur
juge l'avancement à ce qu'il voit à l'écran ; il l'a dit plusieurs fois (« je ne vois rien bouger »). Il veut voir un agent
serveur **comme un agent local** : ce qu'il a prévu de faire, ce qu'il reste à faire, et **l'historique de ses appels**.

Cet historique n'existe pas non plus pour les agents locaux (la fiche ne dit que la dernière action) : il est ajouté pour
les deux, une seule fois.

## Ce qui existe (constat du 2026-11-26)

- Fiche d'un agent local (`bureau/avancement.py`, `moteur/detache.py`) : dernière action en clair (`derniere_action`),
  phase (`phase_du_flux`), liste de points que l'agent écrit lui-même (`<tâche>.avancement.json`, `lire_avancement`),
  temps passé et fourchette du temps restant, coût en direct (`conso_en_cours`, lit le flux local).
- Agent serveur : `bureau/serveurs.py` (`_fiche_tache`) ne rend que l'index local (`taches.json`) : état, mode, projet,
  durée, statut, branche. Le flux (`flux.jsonl`) n'est rapatrié qu'à la fin (`outils/serveur_agent.py`, `docs/serveur-agents.md`
  § « Limites connues » : « on ne peut pas suivre l'agent en direct »).
- Cause : l'entrée du conteneur écrit le flux dans un fichier sans nom, recopié dans `sortie/` seulement à la fin, après le
  contrôle du jeton. C'est une garantie de sécurité (l'agent ne peut pas falsifier ce qui sort).
- L'écran Serveurs a déjà « Tâches du serveur » (émulations et agents, arrêt possible), alimenté par `GET /api/serveurs/taches`.

## Buts

1. Un agent serveur en cours montre, dans la même fiche qu'un agent local : sa dernière action, sa phase, sa liste de points
   (faits, en cours, restants), le temps passé et restant, son coût en direct.
2. **Historique des appels** : la suite des actions déjà faites, la plus récente en haut, pour un agent local **et** un agent
   serveur. Actions dites courtes (« modifie scenes/combat.gd », « lance python »), jamais le contenu d'une commande, d'un
   fichier ni d'un message.
3. Les campagnes de tests et les builds déportés ont une fiche simple : étape en cours et durée.

## Hors périmètre

- Une zone « Serveur » sur la scène du bureau et l'animation des agents serveur : étape suivante, après celle-ci.
- Contrôle de l'agent depuis la fiche (déjà : arrêt) ; reprise, réponse : inchangés.

## Contre-buts

- Pas de fuite : le jeton de l'agent et tout secret ne sortent jamais du serveur avant le contrôle ; aucun contenu brut du
  flux n'est affiché.
- Rien ne doit rendre le suivi obligatoire : serveur muet ou lecture en échec → la fiche garde l'état d'avant et le dit.
- Pas de charge excessive : une lecture bornée, pas un flux continu.

## Contraintes

- Les données du serveur sont **non fiables** (règle existante) : tailles, motifs et nombre de lignes bornés, texte rendu en
  `textContent`, masquage des secrets connus (`_masquer`).
- Un seul fil de fond à la fois côté bureau (`Travaux`) : la lecture du suivi ne doit pas bloquer sonde, installation ni arrêt.
- Tests passent par le lanceur (`CLAUDE.md`) ; une campagne à la fois.
- Aucun identifiant réel dans le dépôt.

## Approches envisagées

1. **Suivre le flux en direct (retenue).** Le serveur expose, pendant la tâche, une copie lisible de la fin du flux ; le
   moteur la relit périodiquement, en extrait actions, phase, points et consommation avec les mêmes fonctions que pour un
   agent local, et la fiche affiche le tout. Historique ajouté une fois pour les deux types.
2. Historique seulement dans l'écran Serveurs (rapide ; l'agent reste muet pendant son travail) : écartée, elle ne règle
   pas « je ne vois rien bouger ».
3. Tout d'un coup, avec la zone sur la scène : écartée comme premier pas ; la zone vient après.

Choix du Directeur : approche 1, avec l'historique pour le local et le serveur.

## Ce qui est décidé

- Même fiche, mêmes champs pour local et serveur (`pour_la_tache`) ; seule la **source** du flux diffère (fichier local /
  lecture sur le serveur).
- Historique : liste d'actions courtes, plus récente en haut ; la profondeur (20 dernières ou complet) est **à confirmer**
  par le Directeur ; défaut proposé : 20 dernières, avec « voir tout » si le flux le permet.
- Campagnes de tests et builds : fiche simple (étape, durée) depuis les données existantes (`serveurs-etat.json`, tâches
  serveur, `_attentes_tests`).

## Laissé au bâtisseur

- Le mécanisme exact côté serveur pour exposer le flux en direct **sans affaiblir** la garantie actuelle (copie nettoyée par
  le veilleur, analyse du jeton sur ce qui sort, ou résumé produit sur le serveur). Point de sécurité le plus sensible :
  à traiter en premier, avec une relecture de `docs/serveur-agents.md` § Sécurité.
- Fréquence de relecture, tailles limites, nom des champs de l'API (`/api/serveurs/taches` ou route dédiée).
- Le rendu précis dans la fiche et dans l'écran Serveurs ; l'estimation du coût en direct pour un agent serveur
  (déjà prévue par la note « coût en direct »).
- Mise à jour de `docs/serveur-agents.md` (retirer la limite « pas de suivi en direct »).
