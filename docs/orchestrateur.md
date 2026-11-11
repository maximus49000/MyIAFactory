# Passer un projet sur l'orchestrateur générique

Ce guide sert à deux cas : **démarrer un projet neuf** avec les outils génériques de la skill, ou **faire passer un
projet qui a déjà sa factory** (ses consignes, ses outils, son relevé) sur l'orchestrateur générique **sans rien lui
faire perdre**. L'orchestrateur générique est une conversation Claude (sur Sonnet par défaut, Opus pour un projet exigeant) qui lit
[`orchestrateur/consignes.md`](../orchestrateur/consignes.md), puis les consignes propres du projet, et mène les
fonctionnalités du cadrage jusqu'à la série. Une conversation orchestratrice par projet.

## 1. Le fichier de factory

Un fichier JSON **versionné dans le dépôt du projet** (par exemple `.factory/factory.json`). Tous ses chemins sont
relatifs à lui. Partez du modèle [`orchestrateur/modeles/factory.json`](../orchestrateur/modeles/factory.json).

| Clé | Obligatoire | Sens |
|---|---|---|
| `skill` | oui | le chemin de la skill sur la machine ; dans un fichier versionné, `~/MyIAFactory/skill` (le dossier stable de l'installation), jamais un chemin absolu |
| `flux` | oui | les étapes de la série, dans l'ordre : `{id, nom, role, service}` ; elles donnent les colonnes du bureau (`cadrage` et `fait` sont ajoutées) |
| `services` | non | les services du bureau, `{id, nom}` (chaque étape du flux en nomme un) ; un service `facturation` donne une pièce où l'onglet Facturation est toujours visible |
| `nom` | non | le nom du projet (défaut : le nom du dossier) |
| `genre` | non | l'identifiant du genre du projet ; `null` au départ, l'orchestrateur le propose au premier cadrage |
| `mots_interdits` | non | le nom du projet, ses lieux, ses chemins, ses personnes : aucune leçon de genre ou de skill ne part s'il en contient un (comparaison sans casse ni accents) |
| `fiches` | non | le dossier des fiches d'agents (défaut `fiches`), avec `briefs/<rôle>.md` |
| `controles` | non | le registre des contrôles (défaut `controles.md`) |
| `consignes` | non | **les consignes propres du projet** (un document) |
| `reglages` | non | les réglages du bureau du projet (pour `charge`) |
| `modele_orchestrateur` | non | le modèle de la conversation orchestratrice : `Sonnet` (défaut), `Opus` ou `Haiku` (jamais Fable) |
| `agents_locaux_max` | non | combien d'agents locaux travaillent en même temps, de 1 à 16 (2 par défaut) ; `agent-libre` n'en rend plus au-delà |
| `seuil_methode` | non | le nombre de tours de corrections d'un élément avant « méthode à revoir ? » (défaut 3) |
| `catalogues` | non | la source du catalogue de chaque fonctionnalité : `{<id>: {fichier} | {commande}}` ; la clé `"*"` vaut pour toutes, et `{fonctionnalite}` y est remplacé par l'identifiant |
| `commandes` | non | **les adaptateurs** : `{<commande>: [arguments]}`, qui remplacent les outils génériques (section 2) |
| `suivi`, `sessions`, `pieces` | non | le suivi des tâches (`suivi.json`), la table des sessions attitrées (`sessions.json`), le dossier des images jointes (`pieces`) |
| `memoire` | non | le dossier de la mémoire (défaut : celui de la skill) |

Le bureau trouve ce fichier par la clé `orchestrateur` des réglages du projet (chemin relatif aux réglages) : il y lit
la déclaration des catalogues.

## 2. Les commandes et leurs adaptateurs

L'orchestrateur n'appelle les outils que par :

```
py -3.12 <skill>/orchestrateur/outil.py --factory <fichier de factory> lancer <commande>
```

`lancer` prend la commande déclarée par le projet dans `commandes` s'il y en a une, sinon l'outil générique. Le
contrat de chaque commande (entrée JSON, sortie JSON, codes de retour) est dans
[`orchestrateur/interface.md`](../orchestrateur/interface.md).

**Projet neuf** : ne déclarez rien, les outils génériques font tout (suivi, relevé, demandes, fiches, leçons,
mémoire, départ des agents, catalogue).

**Projet qui a déjà ses outils** : gardez-les **sans les modifier** et écrivez, commande par commande, un petit
**adaptateur** qui respecte l'interface en appelant votre outil. Pour chaque commande de `interface.md` :

1. votre outil fait-il déjà ce travail ? Si non, laissez l'outil générique (ne déclarez rien) ;
2. si oui, écrivez l'adaptateur : il lit l'entrée JSON, appelle votre outil, traduit sa sortie en JSON au format
   de l'interface, et rend `0`, `1` (refus, avec `{"erreur"}`) ou `2` ;
3. déclarez-le : `"commandes": {"depart": ["python", "adaptateurs/depart.py"]}` (lancé depuis le dossier du
   fichier de factory, avec la variable `MYIAFACTORY_FACTORY`) ;
4. vérifiez (section 3).

Les commandes à regarder d'abord, parce qu'un projet en a souvent déjà une : `releve` (votre relevé, passé en
version 4), `actions` (votre commande d'actions, qui apprend les demandes nouvelles), `depart` (votre commande de
message de départ), `lecon`, `controle`, `charge`, `catalogue` (votre catalogue, traduit au format de la skill).

`partenaires` (connexions, quotas, choix, règles et usage des services extérieurs) reste générique : ses fichiers sont
ceux de la machine (`~/MyIAFactory/partenaires.json`) et les conseils du projet (`partenaires.json` à côté du fichier
de factory). Les partenaires sont facultatifs ; voir « Le bureau partenaire » dans [installation.md](installation.md).

## 3. Vérifier : `verifier_interface.py`

```
py -3.12 <skill>/orchestrateur/verifier_interface.py --factory <fichier de factory>
```

Il lance chaque commande par `lancer` et contrôle ses champs, ses types et ses codes. Sans `--complet`, il ne lance
que les commandes qui ne changent rien : vous pouvez le passer sur le projet lui-même. Avec `--complet`, il joue un
petit scénario qui **modifie** le suivi, les fiches et la table des sessions : faites-le **sur une copie** du projet,
marquée par un fichier vide `.copie-de-verification` à côté du fichier de factory (sinon il refuse). Une ligne par
commande : `ok`, `ÉCART …` ou `ignoré …` ; le passage est bon quand il ne reste aucun écart.

## 4. Les consignes propres

Le document d'orchestration que le projet suit aujourd'hui devient **ses consignes propres** (clé `consignes`). On
n'y garde que ce qui est propre au projet : ses règles de boucle (une seule construction à la fois, des
préparations gardées d'avance, un livrable demandé qui passe avant tout…), ses outils, ses lieux. Ce que les
consignes génériques disent déjà peut en être retiré, mais rien n'y est perdu : **quand les deux se contredisent,
les consignes propres l'emportent**, et l'orchestrateur le note pour l'utilisateur.

## 5. La liste de compatibilité

Pour un projet qui a déjà sa factory, écrivez **dans le dépôt du projet** (pas dans celui de la skill, puisqu'elle
nomme ses fichiers) une **liste de compatibilité** : chaque comportement actuel, l'outil ou la consigne qui le porte
après le passage, et comment le vérifier. Le passage est terminé quand chaque ligne est cochée. Points à ne pas
oublier : la pause et les modes (en ligne, local avec `charge`), les fiches et leur message de départ, les sessions
cloud attitrées, les règles propres de la boucle, les outils d'abord, les leçons et leurs verdicts, le registre des
contrôles, le commit et le push à chaque étape, le relevé, la commande d'actions et le catalogue existant.

Remplissez aussi `mots_interdits`, puis passez `git grep -i` sur le dépôt de la skill avec chacun de ces mots :
aucun résultat ne doit sortir.

## 6. Les réglages du bureau

Les réglages du projet (`reglages.json`) pointent sur les commandes de l'orchestrateur :

```json
{
  "releve": {"commande": ["python", "<skill>/orchestrateur/outil.py", "--factory", "factory.json", "lancer", "releve"]},
  "actions": {"commande": ["python", "<skill>/orchestrateur/outil.py", "--factory", "factory.json", "lancer", "actions"]},
  "images": {"racines": ["pieces", "captures"]},
  "orchestrateur": "factory.json"
}
```

et le fichier de factory déclare un catalogue pour toutes ses fonctionnalités :

```json
"catalogues": {"*": {"commande": ["python", "<skill>/orchestrateur/outil.py", "--factory", "factory.json",
                                  "lancer", "catalogue", "{fonctionnalite}"]}}
```

`<skill>` s'y écrit `~/MyIAFactory/skill` : le bureau développe ce préfixe avant de lancer la commande. Pour plusieurs
projets dans un même bureau, voir « Plusieurs projets » dans [`installation.md`](installation.md) ; l'installation
inscrit chaque projet au bureau commun `~/MyIAFactory/bureau.json`.

## 7. Démarrer la conversation orchestratrice

Ouvrez une conversation Claude sur **Sonnet** (ou Opus pour un projet exigeant : indiquez-le alors dans
`modele_orchestrateur` du fichier de factory, pour que le bureau et la facturation le montrent), dans le dossier du projet, et donnez-lui ce message de départ :

> Tu es l'orchestrateur du projet dont le fichier de factory est `<chemin du fichier de factory>`. Lis
> `<skill>/orchestrateur/consignes.md`, puis les consignes propres du projet, et commence la boucle de réveil.

Elle tient le bureau à jour (`reveil` à chaque tour : sans lui, la page affiche « En attente de l'orchestrateur ») et
se réveille sur le journal des demandes. Ensuite, tout se fait depuis le bureau : « + Nouvelle fonctionnalité », la
discussion, les validations du Directeur, le catalogue.

## Démarrer un projet neuf

Le plus simple : la commande `/myiafactory:installer` du plugin, lancée dans une conversation Claude Code ouverte dans
le dossier du projet (voir « Installer MyIAFactory sur un projet » dans [`installation.md`](installation.md)). Elle
mène la discussion, propose une organisation chiffrée, écrit tout après validation (fichier de factory, réglages,
fiches, briefs, contrôles), inscrit le projet au bureau commun, passe `verifier_interface.py` et donne le message de la
section 7.

À la main, sans le plugin : copiez [`exemples/projet-neuf/`](../exemples/projet-neuf/) dans `.factory/` du projet,
`git init`, mettez `~/MyIAFactory/skill` dans `skill` (`factory.json`) et
`~/MyIAFactory/skill/orchestrateur/outil.py` dans la commande du catalogue (`catalogues["*"]`) et dans
`reglages.json` (relevé et actions), remplissez `mots_interdits` et les fiches (un agent par rôle), puis passez
`verifier_interface.py` et ouvrez le bureau. Un projet déjà branché à la main se met au nouveau rangement (dossier
stable, versionnement, bureau commun, agents locaux en parallèle) par `installation/outil.py reparer <dossier>`, qui
garde ses adaptateurs (`commandes`) tels quels.
