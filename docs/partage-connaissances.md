# Partager les connaissances

Un réglage de tout le bureau (case « Partager les connaissances », dans Réglages, roue crantée en haut à droite : niveau
Global, section « Partage des connaissances » ; elle n'est plus dans le panneau Direction). Donnant-donnant :

| | Partage activé | Partage désactivé |
|---|---|---|
| Leçons skill / genre validées | anonymisées, chiffrées, poussées sur ce dépôt | gardées sur le poste, rien n'est envoyé |
| Leçons des autres bureaux | lues par les agents | illisibles (chiffrées, clé retirée du poste) |
| Leçons de niveau projet | ne quittent jamais le poste | idem |

À la réactivation, les leçons gardées pendant le refus sont anonymisées puis présentées au Directeur, qui valide (ou
corrige, ou écarte) le texte exact avant tout envoi.

## Anonymisation (`orchestrateur/anonymat.py`)

- **Standard** : filtre automatique. Mots interdits, nom du projet, de son dossier et de son dépôt → « le projet » ;
  adresses web, e-mails, IP, chemins, noms de fichiers propres au projet, références de tickets/tâches, empreintes,
  identifiants et longs nombres → mot générique. Aucun surcoût.
- **Renforcé** (par défaut) : filtre, puis relecture par Claude (Haiku, via le moteur) qui réécrit la leçon en concepts
  généraux, puis filtre de nouveau. Jamais d'envoi sans relecture. Surcoût affiché au bureau (estimation, puis moyenne
  mesurée et total).
- **Strict** : renforcé, puis validation du Directeur pour chaque leçon.

## Chiffrement (`orchestrateur/chiffre.py`)

Bibliothèque standard seulement : HMAC-SHA256 en mode compteur, puis sceau HMAC-SHA256 (chiffrer puis sceller). Dans
`orchestrateur/memoire/`, une leçon partagée est une section `## S12 — chiffrée` suivie de `Chiffré : v1.…` : titre,
rôles, date et texte sont dans le jeton ; le message de commit ne dit pas le titre. Les en-têtes des genres (Domaine,
Livrable, Outils) restent lisibles pour classer un projet.

## La clé (mainteneur)

La clé vit dans le dépôt GitHub **privé** `maximus49000/MyIAFactory-cle` (fichier `cle.txt`, 64 caractères
hexadécimaux). Activer le partage la télécharge avec les accès git de l'utilisateur dans
`~/MyIAFactory/connaissances/cle` ; la désactiver l'efface.

- Donner l'accès : inviter le compte GitHub de la personne comme collaborateur (lecture) du dépôt privé.
- Retirer l'accès : retirer l'invitation, puis **changer la clé** (sinon une copie gardée reste valable) :

```
py -3.12 -m orchestrateur.connaissances nouvelle-cle > nouvelle.txt
py -3.12 -m orchestrateur.connaissances chiffrer --cle nouvelle.txt --ancienne ancienne.txt
```

puis remplacer `cle.txt` du dépôt privé par la nouvelle clé.

Limite connue : l'historique git public garde les leçons publiées en clair avant le passage au chiffrement.

## Fichiers du poste (`~/MyIAFactory/connaissances/`)

`partage.json` (réglage, niveau, surcoût mesuré), `cle`, `file.json` (chaque leçon confiée : texte d'origine — jamais
envoyé —, texte anonymisé, état), `genres/` (genres créés pendant un refus).
