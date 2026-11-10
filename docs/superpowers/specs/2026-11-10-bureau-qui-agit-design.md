# Le bureau qui agit — conception

Date : 2026-11-10. Suite du projet 1 (`2026-11-10-bureau-vivant-design.md`, appelé ici « la conception du bureau »), à lire avant celle-ci.

Convention : ce qui vient de l'utilisateur est écrit sans mention. Ce qui est un choix du rédacteur est marqué **[choix]**.

## 1. Pourquoi

Le premier projet réel qui se branche sur le bureau a déjà sa propre page de suivi. L'utilisateur veut que **le bureau la remplace** : tout ce que le bureau fait déjà, plus ce que cette page fait et que le bureau ne fait pas. L'ancienne page sera ensuite fermée. L'accès depuis le téléphone est abandonné dans un premier temps ; une application de suivi à distance viendra plus tard, dans un projet à part.

Ce que la page de suivi d'un projet sait faire et que le bureau ne sait pas :

- commander la factory : la mettre en pause ou la relancer, changer de mode de travail, demander une livraison, ouvrir la dernière livraison ;
- déplacer une tâche d'une colonne à une autre (c'est une demande à l'orchestrateur, pas un changement direct) ;
- écrire un retour sur une tâche et lire la réponse de l'orchestrateur ;
- montrer le détail d'une tâche : journal, images intermédiaires, lien vers la session qui la porte ;
- filtrer les tâches (par type, en cours ou toutes) et les voir en liste.

S'y ajoute une demande nouvelle : les **agents déclarés à mémoire**. Le projet déclare des agents spécialistes ; chacun apprend au fil des tâches, et chaque leçon apprise est signalée sur le bureau du Directeur, qui la **valide ou l'invalide**.

Ce document avance donc une partie des projets 2 et 3 de la vision (commander la factory, le Directeur et les apprentissages des agents). Le reste de ces projets est inchangé.

## 2. La règle qui ne bouge pas

Ce dépôt reste **vide de tout projet** : le bureau ne connaît ni les boutons d'un projet, ni ses colonnes, ni ses fichiers. Tout ce qui est propre à un projet passe par le relevé (ce que le projet montre) et par une commande d'actions (ce que le bureau demande au projet).

Et une règle nouvelle, de l'utilisateur : **le bureau n'agit jamais lui-même sur la factory**. Chaque geste dans la page devient une demande remise au projet ; c'est l'orchestrateur du projet qui la lit et agit. Le bureau qui « commande » ne fait que déposer des demandes.

## 3. Ce que l'utilisateur voit en plus

**[choix]** pour toute cette section (disposition), dans l'esprit de la conception du bureau : la scène reste au centre, tout s'ouvre dans le panneau de droite déjà en place.

- **La barre du haut** reçoit les boutons de la factory que le projet déclare (par exemple « Pause », « Local / En ligne », « Générer une livraison », « Dernière livraison »). Un bouton est soit une **demande** (le bureau l'envoie au projet), soit un **lien** (il s'ouvre dans un nouvel onglet). Un bouton peut demander une confirmation.
- **Le panneau d'une tâche** (clic sur un post-it, ou sur une ligne de la liste) : titre, colonne, agent, étape, journal (le plus récent d'abord), images intermédiaires (vignettes, agrandies au clic), liens (vers la session qui la porte), retours déjà faits avec leur réponse, une zone « Faire un retour » avec un bouton « Envoyer », et un menu « Déplacer vers… » qui liste les colonnes.
- **La file d'attente** : les éléments visibles de la file apparaissent en tête de la première colonne du Kanban, plus pâles ; on peut aussi les « déplacer » (le projet en fait alors une tâche).
- **La vue liste** : un bouton dans la barre du haut bascule le panneau de droite sur « Toutes les tâches », en liste, avec des filtres : en cours / toutes, et un filtre par type si le projet donne des types. Le filtre agit aussi sur le Kanban (les post-its filtrés s'estompent).
- **Le bureau du Directeur** : un clic ouvre son panneau, en trois parties :
  1. **Leçons à valider** : pour chacune, le texte, l'agent, la tâche d'où elle vient, la date, et deux boutons **Valider** / **Invalider** ;
  2. **Retours sans réponse** (lien vers la tâche) ;
  3. **Tâches bloquées** (lien vers la tâche, avec la raison).
  La pastille compte le total des trois, plus les `decisions` que le projet donne en nombre (pour un projet qui n'utilise que le compteur de la version 1).
- **La carte d'un agent** montre en plus sa spécialité et le nombre de ses leçons (dont « à valider »), si le projet les donne ; le panneau d'un agent (clic) liste ses leçons.
- Après un geste, le bureau affiche « Demande envoyée » ; l'effet visible (post-it qui bouge, voyant qui change) n'arrive que quand le relevé suivant le montre. **[choix]** Le bureau ne fait pas bouger la scène d'avance : il ne montre jamais ce qui n'est pas vrai.

## 4. Le relevé, version 2

**[choix]** Le relevé passe à `version: 2`. Un relevé en version 1 reste accepté tel quel (aucun bouton, aucun détail, pastille au compteur). Tous les ajouts sont facultatifs.

Au niveau du relevé :

- `actions` : liste de boutons de la factory, chacun `{id, libelle}` plus, au choix, `lien` (adresse http ou https, ouverte dans un nouvel onglet) ou rien (une demande), et facultativement `confirmer` (texte de la question posée avant l'envoi) et `actif` (faux = grisé). Pour un bouton à bascule comme Pause / Reprendre, c'est le projet qui donne le bon libellé à chaque relevé.
- `types` : liste `{id, nom}` pour le filtre par type.
- `lecons` : les leçons **à valider**, chacune `{id, agent, texte, tache?, date}`.
- `services` : la limite passe de 6 à **8** **[choix]** (le premier projet branché en déclare 7 ; le plan de l'open space s'agrandit déjà avec le nombre de services).

Pour un titulaire, en plus : `prenom` (s'il est donné, il remplace celui du fichier d'équipe et n'y est pas écrit), `specialite` (texte), `lecons` (liste `{id, texte, etat}` avec `etat` « à valider » ou « validée »).

Pour une tâche, en plus : `type`, `journal` (liste `{t, texte}`), `images` (liste `{chemin, legende?}`), `liens` (liste `{libelle, url}` : la session qui la porte, par exemple ; schémas acceptés `https`, `http` et `claude` — ce dernier ouvre l'application Claude de bureau), `retours` (liste `{t, texte, reponse?}`), `bloquee` (raison, si la tâche attend une décision).

Pour une leçon, en plus : `verdict_demande` (le verdict envoyé, pas encore appliqué par le projet) : le bureau remplace alors ses boutons par « Verdict envoyé ».

Les identifiants de boutons sont choisis par le projet ; pour un bouton à bascule, il est recommandé (dans `releve.md`) que l'identifiant dise l'état voulu (`pause` / `reprendre`), pour qu'un double clic avant le relevé suivant ne défasse pas la demande.

Le service d'identifiant `facturation`, s'il existe, porte le réglage de la charge, comme au projet 1.

À changer dans le code existant : la validation du relevé n'accepte aujourd'hui que `version == 1` ; elle accepte désormais 1 et 2 (les champs de la version 2 sont ignorés en version 1).

Pour la file, chaque élément visible peut être déplacé comme une tâche (son `id` est envoyé tel quel).

`docs/releve.md` et l'exemple de démonstration sont mis à jour : la démo montre des boutons, une tâche avec journal et images, une leçon à valider, un retour sans réponse.

## 5. Les demandes : du bureau au projet

**[choix]** Le projet déclare dans ses réglages une **commande d'actions** :

```json
{"actions": {"commande": ["python", "actions.py"], "dossier": "."}}
```

Le bureau la lance (sans shell, 10 secondes au plus, même traitement des délais que la commande du relevé) pour chaque demande, avec **une demande en JSON sur l'entrée standard**, en UTF-8 (le lanceur actuel des commandes ferme l'entrée standard : il faut lui permettre de la fournir). Les demandes possibles :

| `type` | Champs | Sens |
|---|---|---|
| `bouton` | `id` | l'utilisateur a cliqué un bouton-demande |
| `deplacer` | `tache`, `colonne` | l'utilisateur demande qu'une tâche (ou un élément de la file) passe dans cette colonne |
| `retour` | `tache`, `texte` (3 500 caractères au plus) | un retour de l'utilisateur sur une tâche |
| `lecon` | `id`, `verdict` (`"valider"` ou `"invalider"`) | la décision du Directeur sur une leçon |

Chaque demande porte aussi `t` (date ISO). La commande répond par son code de sortie (0 = demande prise) et peut écrire une ligne de texte, montrée à l'utilisateur en cas d'échec. Sans `actions` dans les réglages, la page ne montre aucun moyen d'agir (le bureau reste en lecture seule, comme au projet 1).

Le bureau vérifie avant d'appeler la commande : `id` de bouton connu du dernier relevé, colonne connue, tâche ou élément de file connu, leçon connue, texte non vide. **[choix]** Une seule demande à la fois ; une demande arrivée pendant qu'une autre s'exécute attend son tour.

Côté serveur : `POST /api/demande` (le corps est la demande), mêmes protections que le reste (en-tête `Host` local, réponse JSON). Le réglage de la charge maximum reste une affaire du bureau, comme avant.

## 6. Les images

Une image citée par une tâche est un fichier du projet. **[choix]** Les réglages déclarent les dossiers d'où le bureau a le droit de servir des images :

```json
{"images": {"racines": ["../docs/images"]}}
```

Le bureau sert `GET /api/image?chemin=…` seulement pour un fichier `.png`, `.jpg` ou `.jpeg` situé, après résolution, dans une de ces racines ; tout le reste est refusé. Sans `images` dans les réglages, les tâches n'ont pas de vignettes. **[choix]** 40 images au plus par tâche, dans l'ordre donné par le projet, chargées seulement quand elles deviennent visibles dans le panneau.

## 7. Ce qui n'est pas dans ce projet

- L'accès à distance (téléphone, réseau local) : le bureau n'écoute toujours que la machine. L'application de suivi à distance est un projet à part.
- Le choix de l'agent, la recréation d'un agent avec son contexte, l'écriture de sa mémoire : c'est l'affaire du projet et de son orchestrateur. Le bureau montre et transmet des verdicts, il ne tient aucune mémoire d'agent.
- La facturation (tokens), les cas de test, les cahiers des charges.

## 8. Ce qui serait un échec même si ça marche

- Un geste dans la page qui change l'état de la factory sans passer par le projet.
- Une scène qui montre l'effet d'une demande avant que le relevé le confirme.
- Le moindre élément propre à un projet dans ce dépôt.
- Une adresse qui permet de lire un fichier hors des racines d'images déclarées.
- Un relevé de version 1 qui ne marche plus.
- Une fonction de l'ancienne page de suivi du projet qui manque (le document de branchement du projet en fait la liste).

## 9. C'est réussi quand

- Avec la démo, on clique « Pause » : la commande d'actions de la démo note la demande, le relevé suivant passe en pause, le voyant change.
- On déplace une tâche par le menu, on écrit un retour, on valide une leçon : chaque demande arrive dans la commande, et la scène suit quand le relevé change.
- Le panneau d'une tâche montre journal, images et lien ; une adresse d'image hors des racines est refusée.
- Un relevé de version 1 donne exactement le bureau du projet 1.

## 10. Laissé au constructeur

- Le dessin exact des boutons, du panneau de tâche, de la vue liste et du panneau du Directeur, dans le style déjà en place.
- Le format exact de la réponse de `POST /api/demande` et le texte des messages.
- La démo : sa commande d'actions (un petit script Python de la bibliothèque standard qui applique la demande au relevé de démonstration, pour qu'on voie l'effet).
