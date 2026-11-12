# La fenêtre de validation — conception

Date : 2026-11-12. Suite de `2026-11-12-parallelisme-design.md` (décision `valider_etape`, compte rendu propre à l'élément).

## 1. Intention (les mots de l'utilisateur)

« Pour valider un livrable de type APK ou autre, il faut que je puisse le télécharger et l'installer […] sur mobile
aussi. » « Explique-moi à chaque fois ce que je dois valider (un questionnaire, des bulles à valider ou refuser, et du
texte libre). » « On ne valide plus automatiquement hors de l'interface. » « Si nous développons un site web, on
enverra le lien d'accès de la plateforme qui tourne. On aura toujours soit des images, soit un livrable avec un lien,
mais jamais rien à valider. »

## 2. Ce qui est décidé

1. **Au bureau de direction**, un élément à valider n'a plus que son résumé (élément, objectif, « À valider ») et un
   bouton **« Ouvrir la validation »**. Plus aucun « Valider » / « Renvoyer » dans la liste.
2. **La fenêtre** (modale ; plein écran sous 700 px ; Fermer, Échap, clic hors fenêtre ; focus piégé puis rendu au
   bouton) : (1) Objectif et À valider ; (2) ce qu'il y a à vérifier : livrables (nom, taille, date, « Télécharger »),
   lien d'accès (« Ouvrir »), images légendées agrandissables ; (3) le compte rendu de l'élément ; (4) les points à
   vérifier, chacun avec deux bulles « OK » / « À revoir », tous à choisir ; (5) un champ libre facultatif ; un seul
   bouton d'envoi.
3. **Issue** : tous OK → l'élément est validé ; le texte libre est noté sur la tâche de validation et transmis à la
   tâche suivante (« Note du Directeur »). Au moins un « À revoir » → l'étape précédente est refaite avec une remarque
   structurée : « Remarque du Directeur : points à revoir : … ; … » suivie du texte libre.
4. **Demande** `valider_etape` : `{decision, verdict, reponses: [{point, ok}], texte?}`. Le bureau vérifie que les
   réponses couvrent exactement les points de la décision et que le verdict en découle ; l'outil vérifie la forme ; le
   moteur revérifie. Sans `reponses` (ancienne page), l'ancienne règle vaut (remarque obligatoire pour renvoyer).
5. **Points à vérifier** : l'agent de l'étape qui précède une validation rend `points_a_verifier` (3 à 8 phrases de
   160 caractères au plus, vérifiables par l'utilisateur, tirées du cahier) — consigne dans sa matière. À défaut (ou
   forme fautive), le moteur les dérive : objectif, puis « se télécharge et s'installe », « le site s'ouvre »,
   « les images montrent… » selon ce qu'il y a. Stockés sur la décision (`points`). Une décision d'avant, sans
   `points`, s'ouvre avec un seul point : « L'élément correspond à l'objectif ».
6. **Livrables téléchargeables** : les fichiers de la décision (et les documents `livrable` de la fonctionnalité)
   d'une extension téléchargeable (apk, aab, zip, pdf, exe, msi…) ; l'outil y note `taille` et `date` à la pose.
   Route `GET /api/telecharger?projet=…&fonctionnalite=…&chemin=…` : pièce jointe, bon type, 500 Mo au plus ; le
   fichier doit être sous une racine `livrables`/`documents` ou déclaré (document `livrable` de la fonctionnalité,
   fichier d'une décision `valider_etape` de cette fonctionnalité) ; toujours dans le projet, sans `..`, sans lien
   sortant, jamais dans `.git`. Même garde que les autres routes (code d'accès sur l'écouteur distant). La partie
   « Livrables » d'une fonctionnalité a aussi son « Télécharger ».
7. **Lien d'accès** : l'agent rend `acces: {url, description}` (dans son rapport ou dans le compte rendu de
   l'élément). Sur l'ordinateur : lien direct. Au téléphone, une URL locale (http, 127.0.0.1/localhost/[::1], port
   explicite) passe par le relais du bureau `/apercu/<projet>/<décision>/<chemin>` : GET/HEAD/POST seulement, en-têtes
   triés (ni cookie du bureau, ni `Set-Cookie`, ni encodage compressé), `Location` réécrite, pas de WebSocket (501),
   derrière le code d'accès ; il ne vit que tant que la décision est posée. Une URL non locale (https d'un hébergement
   d'essai) est un lien direct partout.
8. **Jamais rien à valider** : un élément qui arrive à une validation sans image, sans livrable téléchargeable
   existant et sans lien d'accès ne pose pas de décision : l'étape précédente est relancée une fois avec la consigne
   d'ajouter de quoi vérifier ; au second échec, la tâche de validation est bloquée avec la raison.

9. **Ce que dit une validation** (ajout, constat : un apk qui affiche un menu sans rien de jouable, et l'utilisateur ne
   savait pas s'il devait valider le fonctionnel ou seulement l'ouverture). Chaque demande dit trois choses, rendues par
   l'agent qui précède la validation à côté de `points_a_verifier` et stockées sur la décision : `doit_marcher` (une
   à trois phrases, obligatoire), `pas_encore` (ce qui n'est pas encore attendu ; peut être vide) et `conclusion` (une
   phrase : « Validez si… »). La fenêtre les montre en tête, après l'objectif : « Ce qui doit marcher », « Pas encore
   attendu à ce stade », « À conclure », puis les points. Sans `doit_marcher`, la demande n'est pas posée : même relance
   unique que « jamais rien à valider » (un seul compteur), puis tâche bloquée avec la raison. Une décision déjà posée
   sans ces champs n'affiche que « Ce qui doit marcher : l'élément correspond à son objectif » (rien d'inventé) ;
   l'action `decision completer` de l'outil la complète sans toucher au reste.

## 3. Limites dites

- Le relais sert l'application à la même origine que le bureau : une application qui écrit des URL absolues
  (`/src/main.js`, `/api/…`) les fait partir hors du relais ; il faut la lancer avec une base relative (Vite :
  `--base ./` pour un `build`/`preview`). Le rechargement à chaud (WebSocket/HMR) ne passe pas : recharger la page.
- L'application relayée tourne à la même origine que le bureau : c'est le code du projet, écrit par ses agents, qui
  ont déjà la main sur l'ordinateur ; on ne relaie jamais un hôte non local.
- La taille et la date d'un livrable sont celles du moment où la décision est posée.
