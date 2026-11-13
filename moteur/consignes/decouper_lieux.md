Tu décides, étape par étape, où le workflow d'un projet en cours se fait : sur le poste de l'utilisateur, où ses
logiciels sont installés, ou n'importe où (une session dans le cloud n'a aucun de ces logiciels).

Tu reçois un dossier JSON : `flux` (les étapes actuelles, dans l'ordre), `environnement` (les outils du poste : `outil`,
`pour` l'étape qui s'en sert, `objectif`), `suggerees` (les étapes qu'un outil cite) et `metiers` (rôle, lieu).

Pour chaque étape d'agent, choisis son `lieu` :
- `local` : elle exige un logiciel du poste (compiler, lancer le jeu, tester sur émulateur, capturer, exporter, signer).
- `indifférent` : elle s'écrit sans logiciel (code, données, textes, conception) ; un agent cloud peut la faire.
Une étape mixte (du code à écrire, puis à compiler et tester sur le poste) se **découpe** en deux étapes de suite :
- `<id>` garde la partie code : même `id`, nom « <nom> : code », `"lieu": "indifférent"` ;
- juste après, `<id>-local` : nom « <nom> : mise en place et tests », même `role` et même `service`,
  `"lieu": "local"`. Cette partie ne réécrit pas le code : elle le récupère, compile, teste, capture, et rend ce que la
  validation suivante attend (captures, apk, mode opératoire).
Une étape entièrement locale (tests sur émulateur, export de l'apk) n'est pas découpée : seulement `"lieu": "local"`.

Pour chaque étape d'agent, choisis aussi son `regroupement` (facultatif) : `"regroupe"` quand ses tâches (une par élément)
modifient toutes les mêmes fichiers communs (un équilibrage dont les valeurs vivent dans les mêmes fichiers de données :
en parallèle, les branches se fusionneraient mal), alors un seul agent les enchaîne. Sinon n'écris rien (`parallele`, par
défaut : les tâches se répartissent entre les agents libres). Garde celui qu'une étape a déjà. Jamais sur une validation.

Règles strictes, sinon la proposition est refusée : chaque étape existante reste, dans le même ordre, avec son `id`, son
`nom` (sauf la partie code d'une étape découpée), son `role`, son `service`, son `modele` et sa `justification`. Les
validations du Directeur (`"validation": true`) restent telles quelles, sans `lieu` ni `regroupement`. N'ajoute aucune autre étape. Une
étape qui a déjà sa partie `<id>-local`, ou qui en est une, ne se découpe pas.

Dans `message`, dis en deux ou trois phrases, en français, sans jargon, ce qui change et pourquoi : il s'affiche au
Directeur avec l'avant/après.

Forme de la réponse (le flux entier, toutes les étapes) :

```json
{"flux": [{"id": "conception", "nom": "Conception", "role": "designer", "service": "jeu", "lieu": "indifférent"},
          {"id": "valid-design", "nom": "Validation du design", "validation": true},
          {"id": "prototype", "nom": "Prototype jouable : code", "role": "dev", "service": "jeu", "lieu": "indifférent"},
          {"id": "prototype-local", "nom": "Prototype jouable : mise en place et tests", "role": "dev",
           "service": "jeu", "lieu": "local"}],
 "message": "…"}
```

Réponds seulement par ce JSON.
