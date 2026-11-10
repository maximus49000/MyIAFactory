Clé : <identifiant unique de l'agent, par exemple dev-1>
Prénom : <prénom affiché au bureau (facultatif)>
Rôle : <le rôle qu'il tient : dev, relecteur, cadrage… ; « chef » pour l'orchestrateur>
Service : <l'identifiant d'un service du fichier de factory>
Modèle : <Haiku, Sonnet ou Opus>
Lieu : <local ou cloud>
Session : <le nom de sa session attitrée (cloud seulement)>
Spécialité : <ce qu'il fait le mieux (facultatif)>

Le texte libre de la fiche : ce que l'agent doit savoir de son métier dans ce projet, ses habitudes de travail, ses
limites. Il est donné en entier à chaque départ de l'agent.

## Leçons
- [validée] dev-1:L1 : Une leçon validée, sur une seule ligne.
- [à valider] dev-1:L2 : Une leçon notée en fin d'étape, en attente du verdict de l'utilisateur.

<!-- Un fichier par agent, dans le dossier des fiches du projet. Les en-têtes `Clé`, `Rôle`, `Modèle` et `Lieu` sont
obligatoires. Une fiche cloud porte une `Session` : sans elle, l'agent n'est pas utilisable et l'orchestrateur pose
une décision « créer une session cloud ». Les leçons sont gérées par `outil.py lecon`, pas à la main. -->
