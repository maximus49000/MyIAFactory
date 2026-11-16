# Consignes d'une correction

Une correction répare un comportement existant du projet. Elle ne change rien d'autre.

**Deux lectures, à chaque étape.** Tout ce que tu écris à l'utilisateur sur l'anomalie (ton message, ton compte
rendu) commence par **En clair** : 2 à 4 phrases que n'importe qui comprend, sans jargon ni nom de fichier ou de
fonction (ce qui ne va pas, ce que ça change pour l'utilisateur de l'application, ce qu'on fait). Vient ensuite
**Détail technique** : la description complète (cause, fichiers, données, tests, commandes).

## Diagnostic
- Lis le signalement (et, s'il y en a une, la fonctionnalité concernée : son cahier, ses éléments).
- Ne pose une question à l'utilisateur **que** si tu ne peux ni reproduire ni comprendre ce qui était attendu ; une
  seule série de questions, courtes, à choix.
- Rends une fiche : `"fiche_correction": {"en_clair": "…", "symptome": "…", "reproduction": ["étape 1", "…"],
  "attendu": "…", "piste": "… ou null"}` et un `nom` court (« Corriger : … »). `en_clair` : la lecture pour
  n'importe qui (2 à 4 phrases, sans jargon) ; les autres champs : la description technique complète.
- **Illustre l'anomalie** pour que l'utilisateur la comprenne d'un coup d'œil : au moins une image dans
  `message.images` (`{"chemin": "…", "legende": "…"}`, PNG ou JPEG écrit dans le dossier des pièces de la
  fonctionnalité). De préférence une capture de l'écran où l'anomalie se voit, l'endroit fautif entouré ou signalé ;
  si l'application ne se lance pas ici, un schéma simple (valeurs attendues / obtenues, chronologie, données en
  cause). La légende dit ce qu'on voit et ce qui est faux. Si tu ne peux produire aucune image, dis pourquoi dans ton
  message.

## Correctif
- Commence par un test qui reproduit l'anomalie et **échoue**.
- Trouve la cause, corrige au plus près, sans refonte.
- Fais passer ce test et les tests existants ; écris dans ton rapport la cause, les fichiers touchés et la commande
  de test.
- Joins une illustration **avant / après** du même scénario (captures, ou le schéma du diagnostic refait avec les
  valeurs corrigées), légendée, dans les images de ton compte rendu : le Directeur les voit à la validation.
- **Donne toujours au Directeur de quoi valider**, même si le correctif était déjà en place ou s'il n'y avait rien à
  changer : c'est alors la preuve que l'anomalie ne se reproduit plus qu'il valide.
  - `nature: "visuel"` avec les images avant / après (`message.images`) ; si aucune image n'est possible,
    `nature: "mecanique"` avec un court document md dans `fichiers` (cause, fichiers touchés, test qui reproduisait
    l'anomalie, sa sortie avant et après).
  - `doit_marcher` : le scénario de la fiche donne maintenant le résultat attendu (dis lequel, en une ou deux
    phrases, sans jargon).
  - Ton compte rendu suit les deux lectures : **En clair** (ce qui était faux, ce qui est réparé, pour n'importe
    qui), puis **Détail technique** (cause, fichiers touchés, test et sa sortie).
  - Rends aussi la lecture en clair dans le champ `en_clair` (2 à 4 phrases sans jargon : le problème, ce qui a été
    fait, ce que ça change) : elle s'affiche en tête de la fenêtre de validation du Directeur.
  - `pas_encore` vide (tout est attendu) et `conclusion` : « Validez si … ».
  - `points_a_verifier` : 3 points tirés de la fiche, chacun vérifiable en regardant l'illustration ou le document.

## Vérification
- Rejoue le scénario de la fiche et les tests ; joins la capture (ou le schéma) « après », légendée, en reprenant
  l'illustration du diagnostic pour comparer.
- Si l'anomalie revient ou si autre chose casse, dis-le : la tâche repart au correctif.
- Ton compte rendu commence par **En clair** (l'anomalie est-elle partie ? en 2 à 4 phrases, sans jargon), puis
  **Détail technique** (scénario rejoué, tests et leur sortie).

## Livraison
- Intègre le correctif validé par le Directeur comme toute livraison du projet (commit, poussée, paquet si le projet en produit un) ; ne change plus rien au code.
