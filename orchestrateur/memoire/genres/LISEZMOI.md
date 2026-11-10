# Les mémoires de genre

Un fichier par genre de projet, `<identifiant>.md`, où l'identifiant suit `^[a-z0-9][a-z0-9-]{0,39}$`. **Aucun genre
n'est livré avec la skill** : un genre naît quand l'utilisateur confirme celui d'un projet (commande `genre`).

Seuls les projets de ce genre lisent ce fichier. Il est général : il ne cite aucun projet précis.

## Format

```
# Genre : <identifiant>
Domaine : <une phrase : le domaine du projet>
Livrable : <ce que le projet produit>
Outils : <les outils principaux>

## G1 — <titre court de la leçon>
Rôles : <rôle1>, <rôle2>      (ou : tous)
Date : AAAA-MM-JJ

<le texte de la leçon, en termes généraux>
```

Les leçons sont numérotées `G1`, `G2`… dans l'ordre d'arrivée. Une leçon n'est ajoutée que par la commande
`lecon appliquer` : mise à jour du dépôt (`git pull --rebase`), refus si le texte contient un mot interdit du
projet, ajout, commit, push. En cas de conflit, l'orchestrateur s'arrête et le signale.
