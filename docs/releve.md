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
| `version` | oui | `1` |
| `projet` | oui | nom affiché |
| `factory.etat` | oui | `"en marche"` ou `"en pause"` |
| `factory.depuis` | non | date ISO 8601 |
| `services` | oui | liste de `{id, nom}` ; **6 au plus**, identifiants uniques |
| `colonnes` | oui | liste de `{id, nom}` dans l'ordre du Kanban |
| `titulaires` | oui | voir ci-dessous |
| `taches` | oui | voir ci-dessous |
| `file` | non | `{"visibles": [{id, titre}], "reste": n}` — vide par défaut |
| `decisions` | non | nombre de décisions qui attendent le Directeur — `0` par défaut |

**Titulaire** (un agent) : `cle` (stable, unique), `lieu` (`"local"` ou `"cloud"`) et `service` (sauf pour le chef) sont obligatoires. Facultatifs : `modele` (`"?"` par défaut), `permanent` (ne quitte jamais le bureau), `chef` (le chef d'atelier ; un seul au plus, le bureau en ajoute un de clé `"chef"` s'il n'y en a aucun), `fraicheur_min` (délai de fraîcheur propre à cet agent, pour les travaux longs et silencieux).

**Tâche** : `id` (unique), `titre`, `colonne` (connue) et `active` (vrai/faux) sont obligatoires. Facultatifs : `titulaire` (clé connue, ou nul), `etape` (texte en clair), `maj` (date de dernière mise à jour), `postit` (vrai par défaut ; faux = pas de post-it sur le Kanban).

Les textes sont affichés comme du texte, jamais comme du HTML, et tronqués s'ils sont longs.

## Ce que le bureau en déduit

- **Au travail** : le titulaire tient une tâche `active` dont `maj` est récente (30 minutes par défaut).
- **Sans nouvelles** : tâche active mais `maj` plus ancienne que le délai de fraîcheur — l'agent reste à son poste, sans animation, avec une bulle grisée. Une `maj` absente ou illisible compte comme « très ancienne ». Une date sans fuseau est une heure locale.
- **Libre** : aucune tâche active — l'agent va au café. Après 24 h sans activité, et s'il n'est ni permanent ni chef, il quitte le bureau.
- Quand une tâche **change de colonne** entre deux lectures, l'agent qui la tenait avant va déplacer son post-it sur le Kanban.
- Si la factory est **en pause**, le voyant le dit et les agents dont la tâche n'est plus à jour vont au café.

## Exemple complet

Voir [`exemples/demo/releve.json`](../exemples/demo/releve.json) (projet inventé « Démo »).

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
