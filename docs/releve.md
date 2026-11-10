# Le relevé : le contrat entre un projet et le bureau

Le bureau ne connaît aucun projet. Chaque projet lui fournit un **relevé** : un document JSON qui dit les faits bruts. Le bureau en déduit tout le reste (prénoms, statuts, charge de l'ordinateur).

## Deux façons de fournir le relevé

Dans le fichier de réglages du projet (par exemple `reglages.json`), la clé `releve` désigne la source. Les chemins relatifs sont résolus depuis le dossier du fichier de réglages.

**Un fichier tenu à jour par le projet :**

```json
{"releve": {"fichier": "releve.json"}}
```

**Une commande que le bureau lance** (sans shell, 10 secondes au plus, le relevé est lu sur la sortie standard en UTF-8) :

```json
{"releve": {"commande": ["python", "mon_releve.py"], "dossier": "."}}
```

Au-delà de 10 secondes, le bureau arrête la commande et tous les processus qu'elle a lancés, et affiche « La commande du relevé a dépassé 10 s ». La sortie doit être en UTF-8 (un BOM en tête est accepté, comme pour les fichiers). Sous Windows, un script PowerShell écrit par défaut dans la page de codes de la console : commencez-le par `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`. En Python, `sys.stdout.reconfigure(encoding="utf-8")`.

> **Écrivez le fichier par remplacement atomique** : écrivez dans un fichier temporaire du même dossier, puis renommez-le sur `releve.json`. Le bureau relit le fichier toutes les quelques secondes ; un fichier écrit à moitié est refusé (le bureau garde alors sa dernière scène et affiche un bandeau), mais un remplacement atomique évite même cela.

## Les champs

| Champ | Obligatoire | Valeurs |
|---|---|---|
| `version` | oui | `1` ou `2` (la version 2 ajoute les champs marqués ci-dessous ; un relevé version 1 marche toujours, sans eux) |
| `projet` | oui | nom affiché |
| `factory.etat` | oui | `"en marche"` ou `"en pause"` |
| `factory.depuis` | non | date ISO 8601 |
| `services` | oui | liste de `{id, nom}` ; **8 au plus**, identifiants uniques |
| `colonnes` | oui | liste de `{id, nom}` dans l'ordre du Kanban |
| `titulaires` | oui | voir ci-dessous |
| `taches` | oui | voir ci-dessous |
| `file` | non | `{"visibles": [{id, titre}], "reste": n}` — vide par défaut |
| `decisions` | non | nombre de décisions qui attendent le Directeur — `0` par défaut |
| `actions` | non, v2 | les boutons de la factory (voir « Faire agir le bureau ») |
| `types` | non, v2 | liste de `{id, nom}` : les types de tâches, pour le filtre de la vue liste |
| `lecons` | non, v2 | les leçons **à valider** : liste de `{id, agent, texte, tache?, date?, verdict_demande?}` ; `id` unique, `agent` = clé d'un titulaire, `verdict_demande` = `"valider"` ou `"invalider"` (verdict envoyé, pas encore appliqué : le bureau affiche « Verdict envoyé ») |

**Titulaire** (un agent) : `cle` (stable, unique), `lieu` (`"local"` ou `"cloud"`) et `service` (sauf pour le chef) sont obligatoires. Facultatifs : `modele` (`"?"` par défaut), `permanent` (ne quitte jamais le bureau), `chef` (le chef d'atelier ; un seul au plus, le bureau en ajoute un de clé `"chef"` s'il n'y en a aucun), `fraicheur_min` (délai de fraîcheur propre à cet agent, pour les travaux longs et silencieux).

Facultatifs en version 2 : `prenom` (remplace le prénom tiré par le bureau, sans être écrit dans `equipe.json`, et tant que le relevé le donne : il l'emporte sur celui du fichier), `specialite` (texte) et `lecons` (liste de `{id, texte, etat}`, `etat` valant `"à valider"` ou `"validée"`).

**Tâche** : `id` (unique), `titre`, `colonne` (connue) et `active` (vrai/faux) sont obligatoires. Facultatifs : `titulaire` (clé connue, ou nul), `etape` (texte en clair), `maj` (date de dernière mise à jour), `postit` (vrai par défaut ; faux = pas de post-it sur le Kanban).

Facultatifs en version 2, pour le détail d'une tâche :

| Champ | Valeurs |
|---|---|
| `type` | identifiant d'un type de `types` (s'il y en a) |
| `journal` | liste de `{t, texte}` ; le plus récent est montré en premier |
| `images` | liste de `{chemin, legende?}` ; **40 au plus** ; voir « Les images » |
| `liens` | liste de `{libelle, url}` ; schémas `https`, `http` ou `claude` (ce dernier ouvre l'application Claude de bureau) ; ouverts dans un nouvel onglet |
| `retours` | liste de `{t, texte, reponse?, etat?}` (`etat` : mot court affiché à côté de la date, par exemple « nouveau » ou « pris en compte ») ; un retour sans `reponse` est « en attente de réponse » et compte pour le Directeur |
| `notes` | liste de `{libelle, texte}` (deux textes non vides) : notes libres, montrées sous l'étape ; le texte peut avoir plusieurs lignes |
| `bloquee` | texte : la raison, si la tâche attend une décision (compte pour le Directeur) |

Un champ facultatif de mauvais type (par exemple un `journal` qui n'est pas une liste, ou un lien `javascript:`) rend tout le relevé invalide : le bandeau « Relevé invalide » nomme le champ, et la scène garde sa dernière image. Un champ facultatif à `null` compte pour absent. En version 1, ces champs sont ignorés.

## Faire agir le bureau

Le bureau **n'agit jamais lui-même** sur la factory : chaque geste de l'utilisateur (un bouton, un déplacement de tâche, un retour, un verdict sur une leçon) devient une **demande** remise à votre projet, par une commande d'actions que vous déclarez dans les réglages :

```json
{"actions": {"commande": ["python", "actions.py"], "dossier": "."}}
```

Le bureau lance cette commande (sans shell, 10 secondes au plus, dans `dossier`, relatif au dossier des réglages) **une demande à la fois**, avec la demande en JSON, en **UTF-8**, sur l'entrée standard. Code de sortie 0 : demande prise. Autre code, commande absente ou trop lente : la page affiche « Demande refusée : » suivi de la première ligne que la commande a écrite (200 caractères au plus). Sans `actions` dans les réglages, la page est en lecture seule : aucun bouton-demande, aucun menu, aucune zone de retour.

| `type` | Champs | Sens |
|---|---|---|
| `bouton` | `id` | l'utilisateur a cliqué un bouton-demande |
| `deplacer` | `tache`, `colonne` | passer une tâche (ou un élément de `file.visibles`, par son `id`) dans cette colonne |
| `retour` | `tache`, `texte` (3 500 caractères au plus) | un retour de l'utilisateur sur une tâche |
| `lecon` | `id`, `verdict` (`"valider"` ou `"invalider"`) | la décision du Directeur sur une leçon |

Chaque demande porte aussi `t` (date ISO). Le bureau ne transmet une demande qu'après l'avoir comparée au dernier relevé valide : un bouton, une colonne, une tâche ou une leçon qui n'y figure pas est refusé sans lancer la commande.

**Les boutons** (`actions` dans le relevé) : liste de `{id, libelle}` plus, au choix, `lien` (le bouton ouvre cette adresse dans un nouvel onglet) ou rien (le bouton envoie une demande `bouton`) ; facultativement `confirmer` (la question posée avant l'envoi) et `actif` (`false` = grisé). Pour un bouton à bascule (Pause / Reprendre), c'est le projet qui donne le bon libellé à chaque relevé. **Choisissez des identifiants qui disent l'état voulu** (`pause` puis `reprendre`, pas `basculer`) : un double clic avant le relevé suivant ne défait alors pas la demande.

**Ce que la page montre après un geste** : seulement « Demande envoyée ». L'effet (post-it qui bouge, voyant qui change, leçon qui disparaît) n'apparaît qu'au relevé suivant, quand votre projet l'a vraiment fait.

L'exemple de démonstration, [`exemples/demo/actions.py`](../exemples/demo/actions.py), applique chaque demande à `releve.json`.

## Les images

Une image d'une tâche est un fichier du projet. Les réglages disent d'où le bureau a le droit d'en servir :

```json
{"images": {"racines": ["images"]}}
```

Les racines sont relatives au dossier des réglages. Le champ `chemin` d'une image est relatif à ce même dossier. Le bureau ne sert que les fichiers `.png`, `.jpg` et `.jpeg` qui, une fois le chemin résolu (liens symboliques compris), sont dans une de ces racines ; tout le reste est refusé (404). Sans `images` dans les réglages, les tâches n'ont pas de vignettes. Les images sont chargées quand elles deviennent visibles dans le panneau ; l'adresse porte la `maj` de la tâche : mettez-la à jour quand une image est refaite sous le même nom.

Les textes sont affichés comme du texte, jamais comme du HTML, et tronqués s'ils sont longs.

## Ce que le bureau en déduit

- **Au travail** : le titulaire tient une tâche `active` dont `maj` est récente (30 minutes par défaut).
- **Sans nouvelles** : tâche active mais `maj` plus ancienne que le délai de fraîcheur — l'agent reste à son poste, sans animation, avec une bulle grisée. Une `maj` absente ou illisible compte comme « très ancienne ». Une date sans fuseau est une heure locale.
- **Libre** : aucune tâche active — l'agent va au café. Après 24 h sans activité, et s'il n'est ni permanent ni chef, il quitte le bureau.
- Quand une tâche **change de colonne** entre deux lectures, l'agent qui la tenait avant va déplacer son post-it sur le Kanban.
- Si la factory est **en pause**, le voyant le dit et les agents dont la tâche n'est plus à jour vont au café.

## Exemple complet

Voir [`exemples/demo/releve.json`](../exemples/demo/releve.json) (projet inventé « Démo », version 2 : boutons, détail d'une tâche, leçon à valider, retour sans réponse, tâche bloquée).

Version minimale :

```json
{
  "version": 1,
  "projet": "Mon projet",
  "factory": {"etat": "en marche"},
  "services": [{"id": "dev", "nom": "Dev"}],
  "colonnes": [{"id": "afaire", "nom": "À faire"}, {"id": "fait", "nom": "Fait"}],
  "titulaires": [{"cle": "dev:1", "service": "dev", "lieu": "local"}],
  "taches": [{"id": "t1", "titre": "Une tâche", "colonne": "afaire", "active": true,
              "titulaire": "dev:1", "maj": "2026-11-10T09:12:00"}]
}
```
