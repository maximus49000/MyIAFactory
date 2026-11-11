# Le premier lancement du bureau — conception

## Intention

La toute première fois que l'utilisateur ouvre le bureau après avoir installé le plugin, un petit moment de mise en
scène : l'interface de l'application Claude (celle où il vient de discuter de l'installation) se dissout en pluie de
caractères et ces lignes de code « entrent » dans le monde 3D du bureau, qui naît derrière. C'est un clin d'œil, pas
une fonction : il ne doit jamais gêner ni ralentir.

## Ce que l'utilisateur a décidé

- **Une seule fois, en tout.** Seulement à la première ouverture après l'installation. Vu une fois, où que ce soit
  (ordinateur ou téléphone), il n'est plus jamais proposé : le « déjà vu » est gardé par le serveur du bureau, pas par
  le navigateur.
- **Une question discrète** avant : « Voir le lancement » ou « Masquer ». « Masquer » ouvre directement le bureau.
- **Le décor** ressemble à la vraie fenêtre de l'application Claude actuelle, en thème sombre : à gauche la colonne
  (quelques entrées de menu, puis des titres de discussions groupés par projet), au centre le texte de la discussion
  en cours (bulle de l'utilisateur à droite, réponse en texte libre), la zone de saisie en bas, le petit panneau de
  droite (Environnement, Contexte, Connecteurs). Rien n'est cliquable : c'est un décor.
- **Le contenu est inventé** et fixe : une discussion fictive sur l'installation de MyIAFactory, des titres de
  discussions inventés. Rien de personnel ni de propre à un projet réel (dépôt public).

## Comportement

1. Au démarrage, la page lance tout de suite le chargement normal du bureau, et en parallèle demande au serveur si le
   lancement a déjà été vu (`GET /api/lancement` → `{"vu": true|false}`).
2. **Déjà vu** (le cas de toutes les ouvertures sauf une) : rien d'autre ne se passe. Le code de l'effet n'est même
   pas chargé (import dynamique uniquement quand `vu` est faux). Une erreur de lecture vaut « déjà vu » : jamais de
   question sur une panne.
3. **Pas encore vu** : un voile sombre couvre la page, avec deux mots discrets au centre, en petit et en gris :
   « Voir le lancement » · « Masquer ». Aucun titre, aucune explication.
4. **Masquer** : le serveur note « vu » (`POST /api/lancement`), le voile s'efface (fondu court, ≈ 0,3 s), le
   bureau est là (il a continué de charger derrière).
5. **Voir** : le serveur note « vu » tout de suite (un rechargement en pleine animation ne la rejoue pas), puis :
   - la fenêtre factice apparaît, la dernière demande de l'utilisateur est « Ouvre le bureau. » ; dessous,
     « Réflexion… » s'anime (≈ 2,2 s) — le petit moment de réflexion voulu par l'utilisateur ;
   - la réponse s'écrit lettre à lettre (≈ 2 s), puis une courte pause (≈ 0,9 s) ;
   - **les vrais caractères de la fenêtre tombent** (validé sur maquette) : chaque lettre affichée (titre, colonnes,
     discussion, zone de saisie) se décroche à sa place, garde sa police et sa couleur, et tombe avec la pesanteur,
     départs étalés (de gauche à droite et un peu au hasard) ; en tombant, certaines se changent en signes de code et
     laissent une légère traînée — le seul clin d'œil à Matrix ; **pas de voile ni de pluie verte par-dessus** ;
   - la fenêtre vide tombe à son tour (pesanteur, légère bascule) et laisse place au bureau 3D. Si le bureau n'est pas
     encore prêt, la fenêtre vide attend en place (le fond reste sombre) jusqu'à ce qu'il le soit (plafond 10 s
     depuis « Voir », puis elle tombe quand même) ;
   - Total visé ≈ 8 s. Un clic, un toucher ou une touche passe directement à la fin (fondu court).
6. **Téléphone** (classe `mobile` sur `<html>`) : même question, même déroulé ; la fenêtre factice prend la forme
   étroite (la colonne de gauche et le panneau de droite disparaissent, il reste la barre du haut, la discussion et
   la zone de saisie) ; moins de lettres tombent donc, c'est léger.
7. `prefers-reduced-motion` : « Voir » montre la fenêtre et la réponse, puis un simple fondu vers le bureau, sans chute.

## Serveur

- Fichier `~/MyIAFactory/lancement.json` (`{"vu": true}`), à côté de `acces.json`, hors de tout dépôt. Écriture
  atomique comme `acces.py`. Absent ou illisible → pas vu.
- `GET /api/lancement` → `{"vu": bool}` ; `POST /api/lancement` (en-tête `X-Bureau: 1`, corps vide ou `{}`) →
  `{"vu": true}`. Routes globales (pas de `?projet=`), permises aussi depuis le téléphone associé (mêmes gardes que le
  reste : hôte, cookie, origine).
- `serveur.creer(..., lancement=None)` : sans chemin, le drapeau vit en mémoire (les tests n'écrivent jamais dans le
  dossier personnel) ; `main` passe `~/MyIAFactory/lancement.json`.

## Code de la page

- `logique/lancement.js` — fonctions pures testées sous node : lecture de la réponse (`doitProposer(reponse)`), la
  ligne du temps (phase et avancement à l'instant t, avec passage à la fin et attente du bureau), le tirage des
  colonnes de pluie (graine fixe pour les tests), le choix de la taille de caractère selon la largeur.
- `ui/lancement.js` — la question, la fenêtre factice (DOM + CSS, icônes en traits simples dessinés en SVG), la pluie
  (un `<canvas>` 2D par-dessus). Chargé à la demande. Tout est retiré du DOM à la fin.
- `main.js` — quelques lignes : lancer la vérification en parallèle de `demarrer()`, et signaler au module quand la
  scène est prête.
- Styles dans `style.css`, préfixés `.lancement-`.

## Non-objectifs, anti-objectifs

- Pas de vraie interface, pas de vraies conversations, rien de lu dans les fichiers de l'utilisateur.
- Pas de logo, de marque ni d'élément copié du film : ce sont les lettres de la fenêtre qui tombent, avec quelques
  signes de code (lettres latines, chiffres, symboles) pour le clin d'œil.
- Échec si : l'ouverture normale devient plus lente, la question revient, l'animation bloque l'accès au bureau, ou
  elle saccade sur le téléphone.

## Choix laissés au constructeur (mes décisions)

- Les durées ci-dessus, le passage par clic/touche, le comportement en mouvement réduit.
- « Masquer » compte aussi comme vu.
- La forme étroite sur téléphone.
- Le texte exact de la discussion inventée et des titres.
- « Bureau prêt » = la première image de la scène 3D dessinée : `demarrer()` résout une promesse à ce moment-là
  (rejetée si le démarrage échoue ; alors on s'efface au plafond de 10 s, la page montre son message d'erreur).
- Seule une réponse compte comme « vu » : recharger pendant la question la fait revenir.
- Un `POST` raté n'empêche rien : l'animation part sans l'attendre ; au pire la question reviendra une fois.
- Le voile bloque clics et clavier sur le bureau, prend le focus ; il est posé dès la réponse du `GET` (la scène
  n'est jamais prête avant, elle attend l'état et les modèles).
- Ordinateur et téléphone ouverts en même temps avant toute réponse : les deux posent la question, c'est accepté.
- La référence visuelle est la capture de l'application que l'utilisateur a montrée (non versionnée : elle contient
  ses titres réels) : thème sombre gris très foncé, colonne gauche ≈ 215 px avec menu (Créer, Rechercher, Artéfacts,
  Personnalisation, Plus) puis groupes de titres avec pastilles, barre de titre fine avec le titre de la discussion,
  colonne de conversation centrée ≈ 700 px, bulle utilisateur gris foncé arrondie à droite, réponse en texte clair
  avec gras, zone de saisie arrondie en bas, panneau droit ≈ 310 px.
