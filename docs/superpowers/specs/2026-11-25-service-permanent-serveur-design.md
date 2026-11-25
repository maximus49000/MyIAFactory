# Service permanent sur le serveur OVH — conception

Statut : validé par le Directeur le 2026-11-25 (« Public + auto si possible »). Contexte : FM_Stats f14 « Serveur de données
distant autonome » (une instance permanente sur OVH avec ses outils de gestion et d'appel) ; la plateforme ne sait lancer que des
conteneurs temporaires (build, tests, émulation, agents). Voir `docs/serveur-taches.md`, `docs/serveur-agents.md`,
`moteur/deploiement.py` (la correction « Déployer et installer » qui réclame cet outil).

## But
Faire tourner, par projet, **un service qui reste en place** sur le serveur OVH : il redémarre seul, garde ses données et ses
clés, répond depuis Internet, et se met à jour à chaque livraison validée. Un agent ne déploie jamais lui-même : il prépare, le
moteur déploie.

## Non-buts
Plusieurs instances par projet, haute disponibilité, certificats pour un domaine personnalisé (un port + jeton suffit), accès
root à l'hôte pour un agent, tout changement de pare-feu autre que le port du service.

## Décisions du Directeur
1. **Accès public** (Internet), protégé par un jeton : les liens directs vers les graphiques d'équipe doivent s'ouvrir pour
   d'autres personnes.
2. **Déploiement automatique** à chaque livraison validée du projet (pas de clic), avec retour arrière si la santé échoue.

## Ce que fait la plateforme
- **Déclaration** : le projet dépose `.factory/service.json` : `{nom, image|dockerfile, port_interne, sante: "/sante", donnees:
  "/data", variables: [noms...], secrets: [noms...]}`. Rien d'autre n'est lu ; valeurs strictement validées (motifs, plafonds).
- **Lancement** : un conteneur par projet, `--restart unless-stopped`, `--read-only` hors `/data` et `/tmp`, utilisateur non
  privilégié, `--cap-drop ALL`, `no-new-privileges`, limites mémoire/CPU/pids, volume `~/services/<projet>/data`, port hôte
  attribué par la plateforme dans une plage fixe (par ex. 18000–18999) et mémorisé.
- **Pare-feu** : `ufw allow <port>/tcp` pour ce seul port, retiré à l'arrêt ; jamais d'autre règle.
- **Accès** : le service exige `Authorization: Bearer <jeton du service>` sauf `/sante`. Le jeton est généré par la plateforme
  (32 octets aléatoires), rangé sur le serveur (0600) et au coffre du poste ; le Directeur le lit au bureau.
- **Secrets** : saisis par le Directeur seul au bureau (jamais lus par un agent, jamais dans un journal ni dans l'état) ; posés
  sur le serveur en fichier 0600, passés au conteneur en variables.
- **Mise à jour** : le moteur déclenche `deployer-service` après une livraison validée ; construction de la nouvelle image,
  démarrage à côté, contrôle de santé (délai borné), bascule, ancien conteneur gardé jusqu'au succès, **retour arrière
  automatique** si la santé échoue ; un seul déploiement à la fois par projet.
- **Gestion** (commandes du poste et boutons du bureau, aucune pour un agent hors `etat`) : `service etat|journal|redemarrer|
  arreter|mettre-a-jour|supprimer`. `etat` et `journal` (200 dernières lignes, secrets masqués) sont lisibles par l'agent.

## Où
- Serveur : `serveur_ovh/services/` (script hôte unique, étapes idempotentes, JSON en sortie, `--simuler`), état dans
  `~/services/<projet>/etat.json`.
- Poste : `bureau/` (type de déport `service`, réglages, zone « Services » du bureau avec état, jeton, journal) et
  `moteur/` (déclenchement automatique après livraison validée, correction « Déployer et installer » qui l'utilise).

## Sécurité (non négociable)
- Le jeton et les secrets ne sont jamais écrits en clair dans le suivi, les journaux, les rapports d'agent ni les messages.
- Le port ouvert est dans la plage réservée ; une seule règle ufw par service ; la règle SSH n'est jamais touchée.
- L'image est construite sur le serveur depuis le dépôt du projet à un commit précis (celui de la livraison validée).
- Le premier déploiement réel et toute modification de pare-feu exigent l'accord explicite du Directeur au moment de l'essai ;
  tout le reste se teste en simulation.

## Approches considérées
A. Tâche « service permanent » dans la plateforme (retenue) : cohérent avec les tâches existantes, sécurité maîtrisée.
B. Docker Compose libre déposé par le projet : trop de pouvoir donné au projet (ports, volumes, privilèges).
C. Tailscale seulement : refusé par le Directeur (liens à partager).

## Reste au constructeur
Format exact des fichiers d'état, noms des commandes, plage de ports, tests (simulation, motifs hostiles, retour arrière,
masquage des secrets), documentation `docs/serveur-services.md`.
