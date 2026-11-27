# Corrections qui ne tournent pas en boucle

Une correction doit se terminer, pas tourner : FM_Stats a perdu environ quatre heures sur une correction « fait » depuis le
début, et une heure sur une autre pour des raisons de forme. La règle vaut pour tous les projets.

| | Règle | Où |
|---|---|---|
| A. Périmètre | La vérification d'une correction ne porte que sur les critères de l'élément corrigé. Un défaut hors périmètre est noté à part (`hors_perimetre` → une anomalie), jamais un échec ni une nouvelle correction. | `CONSIGNE_RECETTE`, `_noter_les_limites_de_la_recette` |
| B. Non vérifiable ≠ échec | Ce que le cadre de la recette ne permet pas (émulateur sans réseau, base partielle, pas de jeton, écran d'une autre fonctionnalité) est rendu dans `non_verifie` : dit au Directeur, la recette reste réussie si le reste passe. | idem |
| C. Préexistant | Un test qui échoue aussi sur la base est classé `echecs_preexistants` (tâche dédiée, une fois). Un test que la recette n'a pas pu classer est rendu dans `echecs_a_classer` : une tâche le rejoue sur la base, la recette n'est pas rouverte. | `_ouvrir_les_echecs_preexistants`, `_noter_les_limites_de_la_recette` |
| D. Forme | Un rapport illisible (bloc manquant) a un rappel ciblé dans la même session ; deux rejets de forme : la tâche est bloquée et une anomalie « Rapport rejeté pour sa forme » est notée, pas de troisième essai identique. | `agents`, `_agent_en_echec` |
| E. Fusion | Un conflit de fusion qui ne porte que sur de la documentation (`docs/…`) est résolu seul, dans la même tâche : la version de la branche sur les passages en conflit, le reste du dépôt à jour. Aucune tâche de correction. | `_fusion_de_documentation`, `cloud.fusion_bornee` |
| F. Plafond | Au-delà de 2 cycles correction → vérification sur un même élément, avec le même motif d'échec, aucune troisième correction : sous « Claude autonome » la recette est clôturée (« non vérifié : … »), l'élément passe à la validation du Directeur. Un motif qui change ou sans « Claude autonome » : le blocage d'avant (le Chef analyse, le Directeur tranche). | `_recadrer_la_recette` |
| G. Mesure | À chaque cycle à partir du 2e, le Chef dit le numéro du cycle et la durée depuis le premier échec ; au 3e, une anomalie « Boucle de correction » est notée. | idem |

Jamais présenté « terminé » : un élément clôturé « non vérifié » reste à valider par le Directeur, qui voit ce qui n'a pas
été vérifié. Le motif de deux échecs est le même quand plus de la moitié des mots significatifs du plus court se retrouvent.

## Les tâches actives longues

Sous « Claude autonome », une tâche d'agent active depuis plus de 15 minutes (vérification) ou 45 minutes (autre travail) sans
que son journal ni son avancement bougent est revue une fois par minute (`_taches_longues`). Claude lit son journal, son
avancement, les lignes répétées, les corrections en cours sur le même élément et l'état réel du service, puis répond :
`conclure` (retour : ce qui est vérifié, le reste « non vérifié : <cause> », aucune nouvelle correction), `recadrer` (elle tourne
en rond), `laisser` (elle avance) ou `signaler` (cas douteux : rien n'est envoyé, une anomalie « Tâche longue »). Le Chef le dit ;
le même retour n'est jamais renvoyé pour la même tâche ; le retour ne contient ni jeton, ni demande de redéploiement.
