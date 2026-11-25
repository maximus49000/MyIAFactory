# Le service permanent d'un projet sur le serveur

Un projet peut faire tourner sur le serveur **un service qui reste en place** (un serveur de données, une API, des pages
web) : il redémarre seul, garde ses données et ses secrets, répond depuis Internet avec un jeton, et se met à jour après
chaque livraison validée. **Un agent ne déploie jamais lui-même : il prépare, le moteur déploie.**
Conception : [`2026-11-25-service-permanent-serveur-design.md`](superpowers/specs/2026-11-25-service-permanent-serveur-design.md).
Le serveur lui-même : [`serveur.md`](serveur.md) ; les tâches temporaires : [`serveur-taches.md`](serveur-taches.md),
[`serveur-agents.md`](serveur-agents.md).

> **Rien de ceci n'a encore tourné sur un vrai serveur.** Tout est vérifié par un faux `docker`, un faux `ufw` et un faux
> SSH qui conduisent le vrai script hôte (liste dans « Non vérifié en réel »). Le **premier déploiement réel** et toute
> modification de pare-feu demandent l'accord explicite du Directeur au moment de l'essai.

## En bref

| Qui | Fait quoi |
|---|---|
| L'agent du projet | écrit le service et `.factory/service.json` ; lit l'état et le journal (`python lancer.py deporter service etat\|journal`) |
| Le Directeur | règle l'action « Service permanent » sur **serveur** (accord permanent du projet), saisit les secrets et copie le jeton dans la zone **Services** du bureau, redémarre ou arrête |
| Le moteur | redéploie le service à la fin de chaque livraison faite (elle suit toujours la validation du Directeur) |
| Le serveur | construit l'image au commit livré, démarre, contrôle la santé et le jeton, bascule, ou revient en arrière |

## La déclaration : `.factory/service.json`

Le seul fichier que la plateforme lit dans le projet. Il est traité comme une **donnée hostile** et validé en entier, au poste
puis au serveur (même code : le script hôte) ; toute autre clé est refusée, une clé en double aussi.

```json
{
  "nom": "donnees-exemple",
  "dockerfile": "serveur/Dockerfile",
  "port_interne": 8080,
  "sante": "/sante",
  "donnees": "/data",
  "variables": ["NIVEAU_JOURNAL"],
  "secrets": ["CLE_API_EXEMPLE"]
}
```

| Clé | Règle |
|---|---|
| `nom` | minuscules, chiffres, `-` ; 2 à 40 caractères, commence par une lettre |
| `dockerfile` **ou** `image` (exactement un) | `dockerfile` : chemin relatif dans le dépôt (segments `[A-Za-z0-9._-]`, ni `..`, ni segment caché, ni `/` initial, ni `\`) ; `image` : référence **épinglée par empreinte** (`…@sha256:<64 hex>`), jamais une étiquette flottante |
| `port_interne` | entier de 1024 à 65535 (le service tourne sans privilège) |
| `sante` | chemin comme `/sante` (par défaut `/sante`) ; public, sans jeton |
| `donnees` | `/data` seulement (le volume du service) |
| `variables`, `secrets` | 32 **noms** au plus chacun : `[A-Z][A-Z0-9_]{0,63}`, sans doublon, jamais le même nom dans les deux ; noms réservés refusés (`PATH`, `HOME`…, et les préfixes `SERVICE_`, `MYIAFACTORY_`, `LD_`, `DOCKER_`, `PYTHON`, `NODE_OPTIONS`, `JAVA_TOOL_OPTIONS`) |

Fichier de 16 Ko au plus, UTF-8, jamais un lien.

**Ce que le service doit faire** (sinon le déploiement est refusé et l'ancienne version reste) :
- répondre **200** sur `sante` sans jeton, dans les 120 s qui suivent son démarrage ;
- exiger `Authorization: Bearer <jeton>` **partout ailleurs** : `/` sans jeton doit rendre **401 ou 403** (contrôlé à chaque
  déploiement) ; le jeton est dans la variable **`SERVICE_JETON`** ;
- écouter sur `port_interne` (aussi dans `SERVICE_PORT`), n'écrire que sous `/data` (`SERVICE_DONNEES`) et `/tmp` ;
- tourner sous un utilisateur quelconque (le conteneur prend l'utilisateur ordinaire de l'hôte, jamais root).

## Les réglages du Directeur

- **L'accord** : dans les réglages du projet (bureau, page Réglages, ligne « Service permanent »), lieu **serveur**. C'est
  la même règle que la recette sur émulateur : le projet doit être **enregistré** au bureau et l'accord se lit dans ses
  réglages enregistrés (`deport.lieux.service = "serveur"`), jamais dans le défaut du bureau ni dans un autre fichier.
- **Les variables** (non secrètes) : clé `service.variables` des réglages enregistrés, par ex.
  `{"service": {"variables": {"NIVEAU_JOURNAL": "info"}}}` ; seules celles que la déclaration nomme sont passées.
- **Les secrets** : zone **Services** du bureau, un champ masqué par secret déclaré (« Enregistrer » / « Remplacer ») ; ou au
  terminal, `py -3.12 lancer.py service secrets CLE_API_EXEMPLE --dossier <projet>` (saisie sans écho, refusée sans terminal).
  L'écran ne montre que **présent / absent** par nom.

## Où se trouve quoi

Sur le serveur (utilisateur ordinaire, jamais root) :

```
~/myiafactory/serveur_ovh/services/service.py   le script hôte (redéposé à chaque appel)
~/services/                                    0700
  ports.json                                   {projet: port} : la plage 18000-18999, attribuée et mémorisée (sous verrou)
  <projet>/
    etat.json                                  l'état (aucun secret, aucun jeton)
    sources/<commit>/                          les fichiers du commit livré (le courant et le précédent sont gardés)
    data/                                      0700, monté en /data : les données du service (gardées même à « supprimer »)
    jeton                                      0600 : le jeton d'accès (32 octets aléatoires, base64 URL)
    secrets.json, variables.json               0600 : valeurs posées par le poste
    env                                        0600 : le fichier --env-file du conteneur (jeton, variables, secrets)
    .deploiement                               verrou : un seul déploiement à la fois par projet
```

Sur le poste (`~/MyIAFactory`) : `services.json` (le cache que le bureau affiche : état, adresse, dernier journal, dernier
déploiement ; **jamais** de jeton ni de secret) et le **coffre** `services/<projet>.jeton` (0600, ACL de l'utilisateur
sous Windows). L'identifiant `<projet>` est tiré du nom du dossier du projet (`FM_Stats` → `fm-stats`).

## Le déploiement (`deployer`, aussi `mettre-a-jour`)

1. Au poste : déclaration validée, accord vérifié, serveur choisi (capacité `base` présente à la dernière sonde), sources
   du commit par `git archive` (rien du dossier de travail), envoyées par SSH sur l'entrée standard.
2. Au serveur, `recevoir` : archive extraite dans un temporaire (fichiers et dossiers seulement : lien, chemin absolu, `..`,
   fichier spécial = refus de toute l'archive ; 500 Mo et 20 000 membres au plus).
3. `deployer` : verrou du projet (sinon code 75, « déjà en cours ») ; refus sous root ; secret déclaré non posé = refus
   **avant toute commande** ; port attribué ; jeton créé s'il manque ; fichier `env` écrit.
4. Un `svc-<projet>-ancien` laissé seul par une coupure redevient d'abord le service (reprise).
5. Image : `docker build` du Dockerfile dans les sources (30 min au plus), ou `docker pull` de l'image épinglée puis
   étiquette `myiafactory-service-<projet>:<12 premiers du commit>`. **Un échec ici ne touche pas au service en place.**
6. Bascule : l'ancien conteneur est **renommé `-ancien` et arrêté, jamais supprimé** ; le nouveau démarre sur le port.
7. Contrôles : `sante` doit rendre 200 (120 s au plus, toutes les 2 s), `/` sans jeton doit rendre 401 ou 403, `sante` avec
   le jeton 200.
8. Succès : règle `ufw allow <port>/tcp` (idempotente), ancien supprimé, l'avant-dernière image retirée, état écrit.
   Échec : le nouveau est supprimé, l'ancien **remis en place** (renommé, redémarré) : statut `retour_arriere`, code 1 ;
   au premier déploiement, rien n'est ouvert : statut `echec`.

**Pourquoi l'ancien est arrêté avant le nouveau (et non « à côté »).** Deux instances qui écrivent le même `/data` en même
temps (une base SQLite par exemple) peuvent l'abîmer. La bascule coûte donc quelques secondes d'indisponibilité ; l'ancien
reste prêt à repartir jusqu'au succès. La haute disponibilité est un non-but de la conception.

### Le conteneur

`docker run -d --name svc-<projet> --restart unless-stopped --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m
-v ~/services/<projet>/data:/data:rw --user <uid>:<gid de l'hôte> --cap-drop ALL --security-opt no-new-privileges
--memory 1024m --memory-swap 1024m --cpus 1 --pids-limit 256 --log-opt max-size=10m --log-opt max-file=3
--label myiafactory.service=<projet> --env-file ~/services/<projet>/env -p <port>:<port_interne> <image>`.
Ni `--privileged`, ni socket Docker, ni autre volume. Les limites sont fixes : la déclaration ne peut pas les changer.

## Les commandes

```
py -3.12 lancer.py service etat|journal [--lignes N] [--dossier <projet>]            (aussi pour les agents)
python lancer.py deporter service etat|journal [--dossier <projet>]                  (la porte des agents, Python 3.9+)
py -3.12 lancer.py service deployer|mettre-a-jour [--commit <sha>] [--dossier <projet>]   (Directeur ; HEAD par défaut)
py -3.12 lancer.py service redemarrer|arreter|supprimer|jeton [--dossier <projet>]        (Directeur)
py -3.12 lancer.py service secrets <NOM>... [--dossier <projet>]                          (Directeur, au terminal)
```

Sortie : un objet JSON (sans jeton ni secret ; `jeton` imprime le jeton seul). Codes : **0** réussi ; **1** échec (serveur
injoignable, retour arrière, plage pleine) ; **2** usage, accord ou déclaration refusés, ou commande réservée au Directeur
appelée par un agent (variable `MYIAFACTORY_AGENT` posée) ; **75** déploiement déjà en cours.

| Commande (script hôte) | Effet |
|---|---|
| `etat` | état lu (`actif`, `arrete`, `echec`, `absent`, `supprime`), santé, port, commit, dernier déploiement, **présence** de chaque secret |
| `journal` | `docker logs --tail N` (200 au plus), lignes de 500 caractères au plus, **jeton et secrets masqués** (`***masqué***`) |
| `redemarrer` | `docker restart`, puis la règle du port (idempotente) |
| `arreter` | `docker stop` (le service reste arrêté : `unless-stopped`) et **retrait de la seule règle** du port |
| `supprimer` | conteneurs, images, règle, port, sources, jeton, secrets et variables retirés ; **les données sont gardées** |
| `jeton` | la seule commande qui rend le jeton (pour le coffre du poste) |

Toutes acceptent `--simuler` au serveur : aucune commande `docker`, `ufw` ni `sudo`, aucun fichier écrit, le plan rendu
dans `commandes`.

## Le bureau : zone « Services »

Sous l'écran des serveurs. Une carte par projet enregistré qui déclare un service : état en toutes lettres et santé, dernier
déploiement (réussi, refusé avec retour arrière, échoué), **adresse publique** (`http://<hôte du serveur déclaré>:<port>`),
bouton **Copier le jeton** (le jeton est lu au coffre sur le clic et copié, jamais écrit dans la page), **Secrets** (un champ
masqué par nom déclaré, vidé après l'envoi, présent/absent seulement), boutons **Actualiser l'état**, **Lire le journal**,
**Redémarrer**, **Arrêter** (confirmé), **Déployer maintenant** (confirmé), et le journal en texte.

Routes : `GET /api/services` (cache et coffre du poste, jamais de connexion) ; `POST /api/services/<projet>/<action>`
(`etat`, `journal`, `redemarrer`, `arreter`, `deployer`, `secrets`, `jeton`) depuis l'ordinateur seulement (404 sur un écouteur
distant), en-tête `X-Bureau: 1`, JSON (clés en double refusées), 64 Ko au plus. `<projet>` est l'identifiant d'un projet
enregistré qui déclare un service, jamais un chemin. Les actions tournent dans un fil (202), une à la fois par projet (409) ;
`secrets` n'admet que des noms déclarés et des valeurs d'une ligne ; `jeton` rend 200 `{jeton}` ou 404.

## Sécurité

- Le jeton et les secrets ne sont **jamais** en argument d'une commande, dans un journal, dans `etat.json`, dans le cache du
  poste ni dans une réponse (hors `jeton`) : ils voyagent par l'entrée standard de SSH, sont rangés en 0600 et passés au
  conteneur par `--env-file`. Toute sortie du script hôte est masquée (jeton et secrets connus remplacés).
- Un seul port, dans la plage **18000-18999**, une seule règle `ufw` par service ; un port hors plage n'est jamais touché ;
  la règle SSH n'est jamais touchée.
- L'image est construite **au serveur** depuis les fichiers du commit livré (git archive).
- **Les agents** : `etat` et `journal` seulement ; les autres commandes refusent quand `MYIAFACTORY_AGENT` est posé ;
  `deporter service` n'accepte que `etat` et `journal`.

**Limites, dites franchement :**
- **Docker et ufw.** Un port publié par `docker run -p` est ouvert par les règles iptables de Docker **avant** celles d'ufw :
  le port du service est joignable dès que le conteneur tourne, même sans la règle ufw. La règle ufw est posée et retirée
  comme prévu (elle compte pour un pare-feu qui filtre la chaîne `DOCKER-USER`), mais **ce n'est pas elle qui protège** :
  c'est le jeton, contrôlé à chaque déploiement. À l'arrêt, le conteneur arrêté ne répond plus.
- **Agents et poste.** La marque `MYIAFACTORY_AGENT` arrête l'oubli, pas un agent décidé : un agent du poste qui tourne
  sous le même compte Windows peut lire le coffre (`~/MyIAFactory/services/`) ou appeler l'API locale du bureau. Même limite
  que l'accord de la recette (voir [`serveur-taches.md`](serveur-taches.md)) ; piste : un coffre que les agents ne lisent pas.
- **`docker inspect`** montre les variables du conteneur (jeton, secrets) à qui a les droits Docker sur le serveur, c'est-à-dire
  l'utilisateur du serveur (déjà maître de tout).
- **La construction** (`docker build`) exécute le Dockerfile du projet, avec réseau sortant, comme les autres images du
  serveur ; elle ne monte aucun dossier de l'hôte.
- Le service est en **HTTP** (pas de certificat : un port et un jeton, non-but de la conception) : le jeton circule en clair
  sur le réseau. Un certificat (par exemple un mandataire devant le port) reste à décider.

## Non vérifié en réel

Vérifié seulement par simulation (faux docker, faux ufw, faux SSH, vrai script hôte) :
- la construction réelle d'une image et son démarrage sous `--read-only` avec l'utilisateur de l'hôte ;
- le contrôle de santé et du jeton contre un vrai service ; la bascule et le retour arrière sur un vrai Docker ;
- la règle ufw réelle et son interaction avec Docker (voir les limites) ;
- le déclenchement par le moteur après une vraie livraison (le commit pris est HEAD du projet à la fin de la livraison) ;
- la zone Services dans un vrai navigateur (copie du jeton par le presse-papiers).
