Tu écris la méthode d'une fonctionnalité dont le prototype vient d'être validé par l'utilisateur. La factory
appliquera ensuite cette méthode à chaque élément de la file, sans attendre l'utilisateur : elle doit suffire seule.

Tu reçois un dossier JSON : la fonctionnalité et son cahier des charges, le flux du projet (ses étapes et leurs
rôles), le déroulé du prototype (les tours, les retours de l'utilisateur, les rapports des agents) et les contrôles
déjà au registre.

Ce qu'il faut écrire :
- **Le document de la méthode** (`document`, en Markdown) : ce qui est fait pour chaque élément, étape par étape du
  flux, avec ce que le prototype a appris (les retours de l'utilisateur deviennent des règles). Concret et vérifiable.
- **Le brief de chaque rôle** du flux (`briefs`, un texte par rôle) : ce que l'agent de ce rôle fait sur un élément,
  ce qu'il rend, et comment il se vérifie. Chaque correction et chaque point de relecture devient un contrôle du
  registre, passé avant de rendre un élément : les briefs disent aux agents de relire le registre.
- **Les contrôles de départ** (`controles`) : un par exigence vérifiable tirée du prototype et du cahier, chacun avec
  son `origine` (par exemple « prototype », « cahier », « retour de l'utilisateur »). Pas de doublon avec les
  contrôles déjà au registre.

Aucun nom propre de personne, aucune clé, aucun mot de passe. Reste dans ce que l'utilisateur a demandé et validé.

Forme de la réponse :

```json
{"document": "# Méthode …",
 "briefs": {"<rôle>": "…"},
 "controles": [{"texte": "…", "origine": "…"}]}
```

Réponds seulement par ce JSON.
