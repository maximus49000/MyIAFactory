# Consignes d'une correction

Une correction répare un comportement existant du projet. Elle ne change rien d'autre.

## Cadrage
- Lis le signalement (et, s'il y en a une, la fonctionnalité concernée : son cahier, ses éléments).
- Ne pose une question à l'utilisateur **que** si tu ne peux ni reproduire ni comprendre ce qui était attendu ; une
  seule série de questions, courtes, à choix.
- Rends une fiche : `"fiche_correction": {"symptome": "…", "reproduction": ["étape 1", "…"], "attendu": "…",
  "piste": "… ou null"}` et un `nom` court (« Corriger : … »).

## Correctif
- Commence par un test qui reproduit l'anomalie et **échoue**.
- Trouve la cause, corrige au plus près, sans refonte.
- Fais passer ce test et les tests existants ; écris dans ton rapport la cause, les fichiers touchés et la commande
  de test.

## Vérification
- Rejoue le scénario de la fiche et les tests ; joins une capture si le projet a un écran.
- Si l'anomalie revient ou si autre chose casse, dis-le : la tâche repart au correctif.
