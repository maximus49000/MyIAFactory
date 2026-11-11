---
name: installer
description: Installe MyIAFactory sur le projet du dossier courant. Mène la discussion (projet vide ou existant), propose une organisation chiffrée, puis configure tout après validation ; répare une installation existante. À lancer depuis le dossier d'un projet.
---

# Installer MyIAFactory sur un projet

Tu installes MyIAFactory sur le projet du dossier courant : comprendre le projet, proposer une organisation, la mettre
en place après validation. Le projet doit être **prêt pour une première fonctionnalité**, sans la lancer.

## Les règles

- **Rien n'est écrit dans le projet avant que l'utilisateur ait validé la proposition.** Tes fichiers de travail
  (JSON de la proposition) restent dans un dossier temporaire, hors du projet.
- **Sobriété.** Une installation plus coûteuse en tokens qu'un néophyte gérant seul son projet avec Claude est un
  échec. Réponses courtes, une question à la fois, rien de lu sans raison.
- **Viser juste.** Ne devine rien en silence : reformule, fais corriger. Une question de plus coûte moins que trois
  tours de corrections.
- **Le plus petit modèle capable** pour chaque agent : Haiku quand il suffit, Sonnet par défaut, Opus seulement quand
  la tâche l'exige. Fable n'est jamais choisi.
- Tout ce qui écrit passe par l'outil ; tu ne crées pas les fichiers de configuration à la main.
- Réponds dans la langue de l'utilisateur.

## 1. Préparer la skill

```
py -3.12 "${CLAUDE_PLUGIN_ROOT}/installation/outil.py" preparer
```

(Hors Windows : `python3` à la place de `py -3.12`.) La commande crée ou met à jour le dossier stable
`~/MyIAFactory` ; dis en une ligne ce qu'elle a fait (`message`). Elle rend `skill`, le chemin de la skill : dans la
suite, **OUTIL** désigne `py -3.12 "<skill>/installation/outil.py"`. Chaque commande rend du JSON ; un code 1 est un
refus (`erreur`, parfois `erreurs`) : montre-le, corrige, recommence.

## 2. Examiner le dossier

`OUTIL` → `outil.py examiner "<dossier courant>"`. Selon `cas` :

- `installe` : le projet est déjà installé. Lance `outil.py reparer "<dossier>"` et rends compte des `corrections`
  (aucune : « tout est en ordre ») et de `pret` ; si `relancer_bureau` est vrai, lance `outil.py bureau --relancer`. Si l'utilisateur veut ouvrir le bureau au
  téléphone, ajoute `--tailscale` ou `--reseau-local` (section 4). Puis arrête-toi : les évolutions de
  l'organisation viennent des fonctionnalités, pas de cette commande.
- `factory_propre` : le projet a déjà un `.factory/` fait à la main (sa propre factory, ou un branchement sans
  fichier de factory). Renvoie vers `<skill>/docs/orchestrateur.md` (adaptateurs,
  liste de compatibilité) et arrête-toi.
- `vide` : section 3a.
- `existant` : section 3b.

### Les partenaires (facultatifs)

Pour `vide` et `existant`, lance `outil.py partenaires "<dossier>"` : la détection (`detecter`) des serveurs MCP et
des variables présentes, sans jamais lire une valeur de clé. Dis en une ligne ce qui est déjà connecté ou déclaré
(`connexions`). Ensuite, au fil de la discussion :

- **projet existant** : reprends les partenaires déjà définis (`partenaires_declares` d'`examiner` : serveurs de
  `.mcp.json`, paquets, variables de `.env.example`) ;
- **projet vide** : choisis dans `besoins` les sous-catégories utiles (voix, images, 3D…), lance
  `outil.py partenaires "<dossier>" --besoins <a,b>` et propose deux ou trois partenaires par besoin, avec leur lien.

Rien n'est obligatoire : l'utilisateur garde, retire ou ajoute ; pour un partenaire non connecté, donne le lien
d'inscription (il se connecte lui-même). Les partenaires retenus, avec une raison d'une phrase, vont dans
`partenaires_conseilles` (section 6).

## 3a. Projet vide : les questions

Une question à la fois, dans cet ordre ; saute ce qui est déjà répondu :

1. De quoi parle le projet, en une ou deux phrases ?
2. Que doit-il produire, et pour qui ?
3. Qu'est-ce qui ferait qu'un résultat est faux ou raté ? (Ces réponses deviennent les premiers contrôles.)
4. Des outils, langages ou moteurs imposés ou souhaités ? (Sinon, propose.)
5. Quelle première fonctionnalité envisages-tu ? (Pour dimensionner l'organisation au juste besoin.)

Puis les questions communes (section 4).

## 3b. Projet existant : la lecture, puis les questions

Confie la lecture à **un sous-agent Haiku**. Donne-lui le chemin du dossier et l'`inventaire` rendu par
`examiner` (arbre, fichiers clés, extensions), et demande-lui : lire les fichiers clés, la documentation et un
échantillon du code (représentatif, pas tout) ; rendre **un résumé du métier en 300 mots au plus** :
le domaine, ce que le projet produit et pour qui, ses outils, son état, ses conventions (tests, structure), et ce
qu'un agent cloud devrait trouver dans son environnement (langage, version, dépendances, outils ; l'`environnement`
rendu par `examiner` en donne une première liste). Ne lis pas le code toi-même.

Reformule ce résumé à l'utilisateur en quelques lignes et fais-le corriger. Pose ensuite, une à la fois, les questions
sur ce que le dossier ne dit pas : ce qui ferait qu'un résultat est faux, la première fonctionnalité envisagée, et
toute zone d'ombre qui changerait l'organisation. Puis les questions communes (section 4).

## 4. Les questions communes

Pour économiser des tours, pose **en un seul message** les questions fermées (support, cloud, facturation, dépôt
GitHub), numérotées, chacune avec ses choix (oui ou non…), puis **en un second** ta
proposition de genre et de mots interdits, à confirmer ou corriger. Redis chaque réponse comprise en une ligne
(« Facturation : oui ») ; une réponse ambiguë se repose, jamais devinée. N'explique
Tailscale et le Wi-Fi que si le mobile est retenu.

- **Le support de traitement** : ordinateur, mobile, ou les deux (choix multiple). Avec le mobile, le bureau doit être
  joignable du téléphone comme de l'ordinateur, vue 3D comprise. Lance `outil.py acces`, puis propose :
  - **Tailscale (par défaut)** : gratuit, chiffré, joignable de partout (4G comprise), rien d'exposé sur Internet.
    L'utilisateur l'installe lui-même sur l'ordinateur (tailscale.com/download) et le téléphone (son magasin
    d'applications), avec **le même compte** sur les deux ; tu n'installes rien. Puis relance `outil.py acces` :
    `tailscale` doit donner une adresse.
  - **Le Wi-Fi de la maison (secours)** : rien à installer, mais le téléphone doit être sur le même Wi-Fi et **le
    trafic n'y est pas chiffré** : dis-le au choix. `reseau_local` donne l'adresse (nulle : pas de réseau privé).
  Les deux peuvent être ouverts ; sans mobile, rien.
- **Agents cloud, ou local seulement ?** Le cloud sert aux tâches longues ou parallèles ; le moteur lance les sessions
  (abonnement, coût **estimé**) et exige un projet **sur GitHub** et `claude` connecté : `proposer` rend
  `prerequis_cloud` (la raison) ; dis-la. Sans eux : un agent local.
- **Clé API pour les décisions de l'orchestrateur ?** Pose `proposition.question_api()` (facturée à part), **défaut :
  non**. Jamais la clé dans la discussion (l'utilisateur la met dans `ANTHROPIC_API_KEY`). Note `moteur` dans la proposition.
- **La facturation est-elle un objectif du projet ?** Oui : une pièce Facturation et les prix automatiques. Non : pas
  de pièce dédiée.
- **Projet vide : faut-il créer un dépôt GitHub ?** (Privé.)
- **Le genre du projet.** Liste les fichiers de `<skill>/orchestrateur/memoire/genres/` (hors `LISEZMOI.md`) et lis
  seulement leur ligne `Domaine`. Propose le genre qui correspond, ou un nouveau (un identifiant court et une
  description générale, sans aucun nom propre au projet). L'utilisateur confirme. Lis ensuite en entier la mémoire du
  genre retenu, et `<skill>/orchestrateur/memoire/skill.md` ; jamais la mémoire d'un autre genre.
- **Les mots interdits** : les noms propres au projet (nom, personnes, lieux, fichiers ou marques propres) qui ne
  doivent jamais partir dans une leçon publique. Propose-les, fais compléter.

Lance enfin `outil.py calibrer` : il rend `charge_max` et `agents_locaux_max` (les agents locaux qui peuvent tourner
en même temps sur cette machine) avec une `explication` ; reprends-la en une phrase.

## 5. La proposition

Prépare l'organisation la plus petite qui tienne :

- **Le workflow le plus court qui tienne** : le moins d'étapes et de relectures possible, adapté au métier (pars de ce
  que le genre a appris quand il est connu). Le cadrage validé par l'utilisateur est déjà fait par l'orchestrateur
  avant chaque fonctionnalité : ne l'ajoute pas. Chaque étape a une **justification** d'une phrase.
- **Les agents** : un par rôle du workflow au départ (deux seulement si le parallélisme le justifie et que
  `agents_locaux_max` le permet), chacun avec son service, son modèle (le plus petit capable) et son lieu. Un agent
  cloud reçoit `environnement` : ce que la lecture a repéré, ou une liste vide (environnement de base).
- **Les contrôles** : ce que l'utilisateur a dit qui serait faux ou raté, une phrase par contrôle.
- **L'orchestrateur** : Sonnet, sauf projet exigeant (Opus).

Obtiens l'estimation : écris `{"flux", "agents", "genre"}` dans un fichier temporaire et lance
`outil.py estimer < <fichier>`. Elle rend une fourchette en tokens et en euros (`euros` nul : prix inconnu) et dit sur
quoi elle s'appuie.

Présente alors, en cinq parties courtes :

1. **Ce que tu as compris du projet.**
2. **Le paramétrage** : nom, genre, mots interdits, modèle de l'orchestrateur, charge maximum et agents locaux en
   parallèle, supports et accès du téléphone, local seul ou local et cloud, facturation, dépôt GitHub (projet vide), partenaires conseillés.
3. **L'organisation** : les services, et les agents (rôle, service, modèle, local ou cloud).
4. **Le workflow** : les étapes dans l'ordre, chacune avec son rôle, son service et sa justification ; ce sont les
   colonnes du tableau du bureau (`cadrage` et `fait` s'y ajoutent).
5. **L'estimation** du coût d'un élément passé par ce workflow, avec ce sur quoi elle s'appuie.

L'utilisateur corrige autant de tours qu'il le faut ; refais l'estimation si l'organisation change. Rien n'est écrit
tant qu'il n'a pas validé.

## 6. La mise en place

Après « je valide » :

1. Écris la proposition en JSON dans un fichier temporaire. Son format est décrit en tête de
   `<skill>/installation/proposition.py` : lis cet en-tête, pas le reste. Le service `facturation` n'est pas déclaré
   à la main (la mise en place l'ajoute) ; `supports` liste `ordinateur` et/ou `mobile` ; `acces` vaut
   `{"tailscale": vrai ou faux, "reseau_local": vrai ou faux}` (tous deux faux sans mobile) ; `estimation` est le
   résultat de `estimer` ; `briefs` donne un brief par rôle ; `texte` d'un agent est le corps de sa fiche ;
   `partenaires_conseilles` (facultatif) vaut `{besoin: [{"id", "raison"}]}`.
2. `outil.py proposer < <fichier>` : contrôle et enregistre. Un refus liste les erreurs : corrige et recommence.
3. `outil.py appliquer "<dossier>"` : écrit la configuration dans `.factory/`, règle le `.gitignore`, inscrit le
   projet au bureau commun, ouvre les accès demandés, puis vérifie.
4. **Projet vide** : `git init`, puis un premier commit. Si l'utilisateur a demandé un dépôt GitHub, redis-lui le nom
   et attends son accord, puis `gh repo create <nom> --private --source . --push`.
5. **Projet existant** dont `inventaire.git.distant` est un dépôt GitHub : vérifie sa visibilité
   (`gh repo view <distant> --json visibility`). S'il est public, dis-le : la configuration du projet (fiches,
   consignes, contrôles) y sera visible ; ne change rien sans son accord.

Si `genre_raison` n'est pas nul, dis-le : l'orchestrateur reproposera le genre.

## 7. La fin

Dis, sans plus :

- **Si `pret` est faux** : l'installation n'est pas prête. Cite les lignes `ÉCART` de `verification` ; ne prétends
  pas le contraire.
- **Les agents cloud** (`agents_cloud`), un par ligne : sa clé, son rôle, son modèle, l'environnement (vide :
  environnement de base). Rien à créer : le moteur lance leurs sessions.
- **Le bureau** : lance-le toi-même, `outil.py bureau` (avec `--relancer` si `relancer_bureau` est vrai) ; il tourne
  en arrière-plan. Donne son `url` et ses `annonces`. Un refus (bureau lancé à la main) : dis-le tel quel.
- **Avec le mobile** : ouvrir la page sur l'ordinateur ; « Associer un téléphone » ; scanner le QR code avec le
  téléphone. Une adresse nulle dans `acces` : non trouvée (Tailscale arrêté,
  pas de Wi-Fi privé) ; dis quoi vérifier.
- **L'orchestrateur : démarre-le toi-même**, `outil.py orchestrateur "<dossier>"` : le moteur démarre sans fenêtre
  (un seul pour tous les projets). Refus : donne `message_orchestrateur` à coller dans une nouvelle
  session. Sans orchestrateur, le bureau bloque les gestes.

Le projet est prêt pour une première fonctionnalité : elle se lance depuis le bureau (« + Nouvelle fonctionnalité »).
Arrête-toi là.
