# Suivre la consommation par compte Claude

Date : 2026-11-16. Statut : **à traiter, mis de côté** (proposition non encore validée ni réalisée).

## Le besoin

Une même personne utilise plusieurs comptes Claude (par exemple « Pro » et « Perso »), sur plusieurs postes, et bascule
de compte sur un même poste (`/login`). Aujourd'hui, MyIAFactory ne connaît pas la notion de compte : tout passe par le
compte connecté dans Claude Code au moment de l'appel.

## Ce qui se passe aujourd'hui

- Les agents locaux, les décisions du moteur (`claude -p`) et les sessions cloud consomment le compte connecté sur le
  poste (`~/.claude/.credentials.json`). Avec `ANTHROPIC_API_KEY`, les décisions vont à l'API, facturées à part.
- Les jauges du bureau (5 h, semaine) lisent `/api/oauth/usage` avec le jeton du poste : le quota réel du compte
  connecté, toutes machines comprises. Elles sont justes.
- **Le défaut** : `~/MyIAFactory/abonnement-historique.jsonl` ne note pas le compte. Après une bascule, les mesures des
  deux comptes se mélangent : la courbe de la semaine et l'étalonnage « ≈ x % de la semaine par euro » deviennent
  faux. Les coûts en euros, calculés sur les tokens, restent justes.

## La proposition

1. **Reconnaître le compte sans donnée personnelle** : une empreinte courte (SHA-256 de `accountUuid`, lu dans
   `~/.claude.json` → `oauthAccount`, 10 caractères). Jamais l'adresse, le nom ni un jeton. Un nom lisible choisi une
   fois dans le bureau, gardé sur le poste (`~/MyIAFactory/comptes.json`) ; par défaut « Compte 1 », « Compte 2 ».
2. **Marquer chaque mesure** de l'historique (appel du moteur, lecture des jauges) avec l'empreinte du compte connecté.
   Courbe, étalonnage et jauges ne prennent que les mesures du compte connecté. Les mesures d'avant, déjà mélangées,
   restent à part (« avant le suivi des comptes ») et sortent de l'étalonnage, qui repart des appels réels.
3. **Au bureau** : « Compte : Pro » dans la barre du haut, à côté du rond ; un filtre par compte dans « Voir plus » ;
   la bascule est vue au relevé suivant un `/login`.
4. **Plusieurs postes** : chaque poste n'étalonne que sur ses propres appels. Un autre poste qui consomme le même compte
   en même temps fausserait l'étalonnage : les intervalles où le compte monte plus que les appels locaux ne
   l'expliquent en sont écartés. L'historique n'est pas partagé entre postes (un autre chantier).

## Hors champ

- Choisir le compte, ou basculer d'un compte à l'autre quand l'un atteint sa limite : la skill utilise le compte
  connecté dans Claude Code.
- Les coûts en euros des projets, indépendants du compte.

## Fichiers touchés (prévision)

Un nouveau `bureau/compte.py` ; `bureau/abonnement.py`, `bureau/conso.py`, `bureau/web/ui/abonnement.js` ; leurs
tests. À faire quand aucune autre session ne travaille sur ces fichiers du bureau.
