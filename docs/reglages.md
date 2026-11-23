# La page Réglages : trois niveaux

La page s'ouvre par la roue crantée de la barre, entrée « Réglages ». Chaque réglage peut être posé à trois niveaux ; le plus
précis l'emporte. Conception : [docs/superpowers/specs/2026-11-23-page-reglages-design.md](superpowers/specs/2026-11-23-page-reglages-design.md).

## Les niveaux et la cascade

| Niveau | Où il est écrit | Vaut pour |
|---|---|---|
| Global | `~/MyIAFactory/bureau.json` : `deport.lieux` (lieux des actions), `reglages` (autres réglages) | tous les projets du bureau |
| Type | le même fichier, `types.<genre>` : `types.<genre>.deport.lieux`, `types.<genre>.reglages` | les projets de ce genre (`genre` de `.factory/factory.json`) |
| Projet | les réglages du projet (`.factory/reglages.json`) : `deport.lieux`, clés à plat (`lecons_auto`…) | ce projet seulement |

Valeur effective : **projet, puis type, puis global, puis le défaut** (le poste pour un lieu d'action). Un projet générique
(genre absent ou inconnu) n'a pas de niveau type. `deporter`, `lancer.py tests` et la consigne de départ des agents lisent les
mêmes niveaux que la page (`bureau/registre.py`, `lieux_du_type`) : un lieu posé au type compte partout.

## Ce que montre la page

- En haut, le niveau édité : **Global**, **Type : <genre>**, **Projet : <nom>**. « Type » est grisé sans genre connu ;
  « Global » et « Type » le sont pour un bureau lancé sur un seul projet (sans fichier du bureau) : la page retombe sur « Projet ».
- Au niveau Projet, une pastille dit d'où vient chaque valeur : « propre au projet », « hérité du type <genre> », « hérité du
  global » ou « défaut ». Aux niveaux Global et Type : « défini ici » ou « pas défini ici » ; une valeur héritée est estompée.
- Le bouton **« hérité »** efface la valeur posée au niveau édité (le niveau retombe sur le suivant).
- **« Projet seulement »** : la recette sur émulateur ne se règle qu'au projet (accord permanent, jamais hérité) ; aux autres
  niveaux sa rangée est verrouillée. Une action d'un autre type, réglée au global ou au type pour d'autres projets, est
  marquée « non applicable à ce projet ».
- « Serveur » est grisé « bientôt » pour une action que `deporter` n'y sert pas, et, pour la recette, « déclarez d'abord un
  serveur (Serveurs), puis réglez sur serveur » tant qu'aucun serveur n'est déclaré. Les attentes en chaîne (« les tests au
  poste attendront l'APK de GitHub… ») sont redites sous les actions. Détail du déport : [`deport.md`](deport.md).

## Lecture tolérante du fichier du bureau

Un réglage inconnu sous `reglages` (écrit à la main, ou par une version plus récente) et une entrée abîmée sous `types`
(genre mal formé, objet attendu, lieu refusé) sont **écartés** : le bureau, le moteur et le lanceur démarrent avec le reste.
Ce qui est écarté est listé (`ignores`) et dit en haut de la page. `deport.lieux` du fichier du bureau reste vérifié comme
avant (un lieu inconnu rend le fichier illisible). Les écritures, elles, refusent toute valeur inconnue.

## L'état et la route

`GET /api/etat` porte `reglages_page` : `{genre, type_disponible, global_disponible, lignes, ignores}`. Une ligne :
`{id, section, libelle, aide, forme ("lieu" ou "booleen"), choix, niveaux, valeur, origine ("defaut", "global",
"type:<genre>", "projet"), valeurs: {niveau: valeur posée}, applicable, defaut, servie_au_serveur}` ; `id` vaut
`deport.<action>` pour un lieu, l'identifiant du registre sinon. En cas de panne, `reglages_page_erreur` à la place.

`POST /api/reglages/niveau` (en-têtes `X-Bureau: 1` et `Content-Type: application/json`), corps `{niveau, id, valeur}` ;
`valeur: null` efface. Tout est vérifié avant d'écrire (niveau permis, genre connu, lieu offert par l'action, serveur servi et
déclaré) ; le fichier est relu et réécrit sous verrou, de façon atomique, et les objets laissés vides sont élagués. Réponses :
200 et la ligne à jour ; 400 et `{"erreur"}` en français pour un refus ; 500 `{"erreur": "Erreur du bureau : …"}` pour une
panne d'écriture (fichier tenu par un autre programme…). L'ancienne route `POST /api/reglages` (niveau projet) reste.
