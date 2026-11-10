# Les dossiers des services — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cliquer un service ouvre un dossier à quatre onglets (Tâches, Connaissances, KPI, Facturation) : coût en euros estimé à partir des tokens avec prix mis à jour automatiquement, connaissances partagées entre agents, geste « Challenger » qui mène à une connaissance validée, KPI par service.

**Architecture:** Le relevé passe en version 3 (`usage`, `kpi`, `connaissances`, `challenges`). Côté serveur : `usage.py` (historique des usages), `prix.py` (table de prix datée, mise à jour automatique avec sources injectables), `cout.py` (calcul pur), `kpi.py` (KPI calculés, historique des alertes) ; `demandes.py` gagne trois types ; `serveur.py` gagne `GET /api/facturation` et un fil de mise à jour des prix. Côté page : `ui/dossier.js` (quatre onglets) et un module par onglet.

**Tech Stack:** Python 3.12 bibliothèque standard (`urllib`, `xml.etree`) ; JavaScript en modules ; tests `unittest` et `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-10-dossiers-des-services-design.md` (contexte : `2026-11-10-bureau-qui-agit-design.md`, `2026-11-10-bureau-vivant-design.md`).

## Global Constraints

- Dépôt public, vide de tout projet : aucun nom, chemin ou fichier d'un projet réel.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"` (guillemets compris).
- Relevé : `version` 1, 2 ou 3 ; les versions 1 et 2 marchent exactement comme avant (pas de dossier enrichi, pas de facturation). Tous les ajouts de la version 3 sont facultatifs ; leur absence masque l'onglet concerné.
- **Aucun test ne sort sur Internet** : les sources de prix sont injectées (fonction `ouvrir(url) -> str`). Les deux adresses de source sont des constantes du code, pas des réglages. `prix_automatiques: false` → aucune requête.
- Un prix qui change ne modifie jamais un coût passé : prix d'un usage = dernier prix enregistré à sa date de première apparition ou avant ; avant le premier prix, le premier prix, signalé.
- Un modèle sans prix n'est jamais compté à zéro : « prix inconnu », tokens montrés, exclu des euros avec mention.
- Les euros s'affichent précédés de « ≈ » ; période par défaut 7 jours (`aujourdhui`, `7j`, `30j`).
- Demandes nouvelles : `challenge` `{cible:{type,id}, texte?, solution?}`, `solution` `{challenge, texte}` (3 500 caractères au plus), `verdict_solution` `{challenge, solution, verdict}` avec `verdict` ∈ `valider`, `ecarter`. `cible.type` ∈ `kpi`, `connaissance`, `source`. Mêmes en-têtes, mêmes règles d'envoi (une à la fois, 10 s) que les demandes existantes.
- Le bureau n'invente jamais une solution et n'écrit jamais une connaissance ; la scène ne montre jamais l'effet d'une demande avant le relevé qui le confirme.
- Textes de la page toujours insérés comme texte (`textContent`), y compris ceux qui viennent de la source de prix.
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer, tous les tests ; cocher dans le `README.md` ; commit en français terminé par `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` ; `git push`.

## Review Focus

1. Source de prix injoignable, illisible, ou valeur absurde (négative, nulle, ×10 d'un jour à l'autre) : dernier prix gardé, signalé dans la facturation, le serveur reste disponible.
2. Un usage republié avec les mêmes `id` et des compteurs plus grands : compteurs mis à jour, date de prix et service inchangés ; un prix qui change après coup ne bouge pas son coût.
3. Usage d'un modèle inconnu, d'un agent parti ou du chef : « prix inconnu » ou « direction / hors service », jamais 0 € ni plantage.
4. Demande `challenge` sur une cible absente du relevé et des cibles recalculées, ou `verdict_solution` sur une solution inconnue : 400, la commande n'est pas lancée ; double clic « Challenger » : un seul challenge.
5. Textes hostiles (`<img onerror>` dans une connaissance, un constat, un nom de modèle de la source de prix) : affichés littéralement, console vide.

---

## Étape 1 — la facturation

### Task 1 : le relevé version 3 et l'usage

**Files:** Modify `bureau/releve.py`, `tests/test_releve.py`

**Interfaces:**
- Produces: `valider(r)` accepte `version` ∈ {1,2,3} ; les contrôles de la version 2 s'appliquent aussi à la 3 (`r["version"] >= 2`). En version 3, `usage` (liste facultative) : chaque entrée `{id: texte non vide unique, tache: clé connue ou nul, agent: clé de titulaire connue, modele: texte non vide, etape?: texte, t: texte, entree: entier ≥ 0, sortie: entier ≥ 0, cache_lecture?, cache_ecriture?: entiers ≥ 0}` ; erreur qui nomme `usage`. `normaliser(r)` : `usage` → `[]` par défaut en version 3, retiré sinon. `MAX_USAGE = 5000`.

- [ ] **Step 1 : tests** — `test_version_3_valide`, `test_version_4_refusee`, `test_v2_inchange`, `test_usage_valide`, `test_usage_id_en_double`, `test_usage_tokens_negatifs`, `test_usage_bool_refuse` (`entree: true`), `test_usage_agent_inconnu`, `test_usage_tache_inconnue`, `test_usage_ignore_en_v2` (champ invalide ignoré), `test_usage_5001_refuse`, `test_normaliser_usage_defaut`.
- [ ] **Step 2–4 :** échec, coder, tous les tests verts. **Step 5 :** commit « Relevé version 3 : l'usage ».

### Task 2 : l'historique des usages

**Files:** Create `bureau/usage.py`, `tests/test_usage.py`

**Interfaces:**
- Produces: `class HistoriqueUsage(chemin)` ; `integrer(r) -> None` : pour chaque entrée de `r["usage"]`, ajoute-ou-met-à-jour la ligne d'`id` (compteurs = derniers vus ; `t_prix` = `t` à la première apparition, jamais modifié ; `service` = service de l'agent à ce moment, `None` pour le chef ou si inconnu, jamais modifié) ; `lire() -> list[dict]` lignes `{id, tache, agent, service, modele, etape, t, t_prix, entree, sortie, cache_lecture, cache_ecriture}`. Fichier JSONL, réécrit par remplacement atomique ; une ligne illisible est ignorée ; rien n'est supprimé.

- [ ] **Step 1 : tests** — `test_premiere_apparition`, `test_compteurs_mis_a_jour_date_inchangee`, `test_service_fige_quand_l_agent_change`, `test_agent_parti_garde_son_usage`, `test_chef_sans_service`, `test_ligne_illisible_ignoree`, `test_survit_au_redemarrage`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Historique des usages ».

### Task 3 : les prix, mise à jour automatique

**Files:** Create `bureau/prix.py`, `tests/test_prix.py`

**Interfaces:**
- Produces: constantes `URL_PRIX` (fichier de prix LiteLLM sur GitHub) et `URL_TAUX` (flux quotidien de la BCE) ; `lire_prix(texte_json) -> dict[str, {"entree": float, "sortie": float, "cache_lecture": float|None, "cache_ecriture": float|None}]` (dollars par million de tokens, déduits des champs « par token » × 10⁶ ; entrées illisibles ignorées) ; `lire_taux(texte_xml) -> (date_iso, float)` (euros pour un dollar, déduit du taux EUR→USD) ; `class TablePrix(chemin)` : `ajouter(date_iso, modeles, taux) -> None` (ligne datée, remplacement atomique), `prix_a(modele, date_iso) -> (prix_euros_par_million | None, date_du_prix, ancien: bool)` (dernier enregistré ≤ date ; sinon le premier avec `ancien=True`), `derniere_maj() -> str | None` ; `actualiser(table, ouvrir, aujourdhui_iso) -> dict` `{"ok": bool, "message": str}` : une seule fois par jour, rejette (garde l'ancien et le dit) une source injoignable ou un prix ≤ 0 ou ×10 / ÷10 par rapport au précédent ; `ouvrir_url(url) -> str` (`urllib`, 10 s, https seulement, 5 Mo au plus).
- Réglages lus par `prix_effectif(table, regl, modele, date_iso)` : `prix` (corrections à la main `{modele: {entree, sortie, date}}`, passent avant l'automatique à partir de leur date) et `alias_modeles` (`{nom du relevé: nom de la liste}`).

- [ ] **Step 1 : tests** (JSON et XML inventés, jamais d'Internet) — `test_lire_prix_conversion_par_million`, `test_lire_prix_entree_illisible_ignoree`, `test_lire_taux`, `test_prix_a_dernier_avant_la_date`, `test_prix_a_avant_le_premier_prix`, `test_changement_de_prix_ne_bouge_pas_le_passe`, `test_actualiser_une_fois_par_jour`, `test_source_injoignable_garde_l_ancien`, `test_prix_absurde_refuse` (négatif, zéro, ×10), `test_correction_manuelle_prioritaire`, `test_alias`, `test_modele_inconnu_none`, `test_ouvrir_url_refuse_http_et_autres_hotes` (n'ouvre jamais une URL qui n'est pas l'une des deux constantes).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Prix des modèles et taux, mise à jour automatique ».

### Task 4 : le calcul des coûts

**Files:** Create `bureau/cout.py`, `tests/test_cout.py`

**Interfaces:**
- Consumes: `HistoriqueUsage.lire()`, `prix_effectif`, le relevé normalisé.
- Produces: `facturation(usages, prix_de, r, periode, maintenant) -> dict` (pur) avec `periode` ∈ `aujourdhui`, `7j`, `30j` ; `prix_de(modele, date_iso) -> (prix | None, date, ancien)`. Résultat : `{"total": euros, "gestion": euros, "sans_prix": [{modele, tokens}], "services": {id|"direction": {total, taches: {id: {total, etapes: {nom: euros}}}, modeles: {nom: euros}, usages: [...]}}, "sources": [{id, genre, service, tache?, texte}], "prix_du": date, "avertissement": str|None}`. Un usage compte si sa date `t` est dans la période. `sources` : tâches > 3 × médiane du service ; étape faite par un modèle plus cher que la médiane des autres usages de cette étape ; part des allers-retours (tâches avec ≥ 2 `retours`). Identifiants : `source:<service>:<genre>:<tache>`.

- [ ] **Step 1 : tests** — `test_cout_d_un_usage` (valeurs inventées, calcul exact), `test_agregats_par_tache_etape_modele_service`, `test_periode_filtre`, `test_modele_inconnu_exclu_et_signale`, `test_prix_ancien_signale`, `test_source_tache_chere`, `test_source_modele_trop_fort`, `test_aucun_usage_total_zero`, `test_chef_dans_direction`, `test_identifiants_deterministes`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Calcul des coûts ».

### Task 5 : le serveur sert la facturation

**Files:** Modify `bureau/serveur.py`, `bureau/etat.py`, `bureau/reglages.py` (défaut `prix_automatiques: true`), `tests/test_serveur.py`, `tests/test_etat.py`

**Interfaces:**
- Produces: `Bureau.__init__` crée `HistoriqueUsage(dossier/"usage-historique.jsonl")` et `TablePrix(dossier/"prix-historique.jsonl")` ; un fil `_boucle_prix` (au démarrage puis toutes les heures, `actualiser` une fois par jour) n'existe que si `prix_automatiques` n'est pas faux ; `Bureau.ouvrir` (par défaut `prix.ouvrir_url`, remplaçable par les tests) ; à chaque relevé valide en version 3, `integrer(r)`. `GET /api/facturation?periode=7j` → `cout.facturation(...)` + `{"maj": derniere_maj, "message": ...}` ; période inconnue → 400 ; relevé sans `usage` ou version < 3 → `{"disponible": false}`. `etat` gagne `dossier: {facturation: bool, kpi: bool, connaissances: bool}` (ce que le relevé fournit).

- [ ] **Step 1 : tests** (source de prix simulée par `Bureau.ouvrir`) — `test_api_facturation`, `test_periode_inconnue_400`, `test_v2_facturation_indisponible`, `test_prix_automatiques_faux_aucune_requete` (le simulateur lève s'il est appelé), `test_source_en_panne_serveur_ok_et_message`, `test_usage_integre_au_releve_valide`, `test_hote_refuse_403`.
- [ ] **Step 2–4 :** échec, coder, tous verts. **Step 5 :** commit « Le serveur sert la facturation ».

## Étape 2 — le dossier à quatre onglets

### Task 6 : le dossier, l'onglet Tâches et l'onglet Facturation

**Files:** Create `bureau/web/ui/dossier.js`, `bureau/web/ui/facturation.js`, `bureau/web/tests/facturation.test.js` ; Modify `bureau/web/ui/texte.js` (+ test), `bureau/web/ui/panneaux.js`, `bureau/web/style.css`

**Interfaces:**
- Produces (purs, testés) dans `texte.js` : `euros(v) -> "≈ 1,42 €"` (virgule, deux décimales, `"≈ 0,00 €"` si 0, `"—"` si nul) ; `tokens(n) -> "12,4 k"|"1,3 M"` ; `libellePeriode(p)`. `dossier.js` : `contenuDossier(contexte, conteneur, service, onglet)` dessine en-tête (nom, sélecteur de période), quatre onglets (un onglet sans donnée est masqué ; Tâches est toujours là), mémorise onglet et période choisis le temps de la session. `facturation.js` : `contenuFacturation(contexte, conteneur, service, periode)` récupère `/api/facturation?periode=…` avec `AbortSignal.timeout(15000)` ; montre le total « ≈ », le détail par tâche/étape/modèle, les sources d'amélioration (bouton « Challenger » inerte jusqu'à la tâche 9), l'avertissement de prix, la ligne gestion. Le panneau « service » de `panneaux.js` appelle `contenuDossier` (la phrase « arriveront avec le projet 2 » disparaît ; le réglage de charge reste pour la facturation).

- [ ] **Step 1 : tests JS** — `euros` (cas ci-dessus), `tokens`, `libellePeriode`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur sur une copie de la démo avec un relevé version 3 inventé : quatre onglets, période qui recharge, prix inconnu visible, texte hostile affiché tel quel, console vide. **Step 6 :** commit « Dossier de service : tâches et facturation ».

## Étape 3 — connaissances et challenges

### Task 7 : le relevé et l'état pour les connaissances

**Files:** Modify `bureau/releve.py`, `bureau/etat.py`, `tests/test_releve.py`, `tests/test_etat.py`

**Interfaces:**
- Produces: version 3, par titulaire `connaissances: [{id, texte, date?, origine?, appris_de?: [{agent, tache?, retour?}]}]` ; `challenges: [{id, cible:{type,id}, texte, date?, solutions:[{id, texte, auteur ∈ directeur|service|utilisateur, etat?}]}]` ; ids de connaissances, leçons, challenges et solutions uniques dans tout le relevé (si une leçon et une connaissance ont le même `id`, la connaissance l'emporte). `etat.construire` : `agent["connaissances"]` = connaissances du relevé + leçons validées (sans doublon), chacune avec `partagee` (vrai si `appris_de` non vide) ; `etat["challenges"]` ; `etat["dossier"]["connaissances"]`. Par agent, `recu_periode` n'est pas calculé ici : l'onglet le calcule à partir des dates.

- [ ] **Step 1 : tests** — `test_connaissance_valide`, `test_appris_de_agent_inconnu_refuse`, `test_id_connaissance_double_avec_une_lecon`, `test_challenge_valide`, `test_solution_auteur_inconnu`, `test_cible_type_inconnu`, `test_v2_ignore_les_ajouts`, `test_etat_fusionne_lecons_validees`, `test_etat_marque_partagee`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Connaissances et challenges dans le relevé ».

### Task 8 : les trois demandes

**Files:** Modify `bureau/demandes.py`, `bureau/serveur.py`, `tests/test_demandes.py`, `tests/test_serveur.py`

**Interfaces:**
- Produces: `CHAMPS` gagne `challenge: ("cible",)` (+ `texte`, `solution` facultatifs), `solution: ("challenge","texte")`, `verdict_solution: ("challenge","solution","verdict")` ; `nettoyer` garde `texte` et `solution` facultatifs de `challenge` ; `verifier(demande, r, cibles_calculees=frozenset())` : une cible `connaissance` doit être dans le relevé (id de connaissance ou de leçon), `kpi` dans les KPI du projet du relevé ou dans `cibles_calculees`, `source` dans `cibles_calculees` ; `solution` : challenge présent dans le relevé, texte non vide ≤ 3 500 ; `verdict_solution` : challenge et solution présents, verdict ∈ `valider`, `ecarter` ; `challenge` sur une cible qui a déjà un challenge au relevé : refusé (« Un challenge existe déjà : ouvrez-le »). `Bureau.demande` passe les cibles calculées (vides tant que la tâche 10 n'est pas faite).

- [ ] **Step 1 : tests** — un refus par cas ci-dessus, un accepté par type, `test_commande_non_lancee_si_refus`, `test_solution_dans_le_meme_geste` (la commande reçoit `solution`), `test_trois_demandes_en_alternance`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Demandes : challenge, solution, verdict ».

### Task 9 : l'onglet Connaissances et le volet « Challenger »

**Files:** Create `bureau/web/ui/connaissances.js`, `bureau/web/ui/challenge.js`, `bureau/web/tests/challenge.test.js` ; Modify `bureau/web/ui/dossier.js`, `bureau/web/ui/actions.js` (+ test), `bureau/web/ui/facturation.js`

**Interfaces:**
- Produces (purs, testés) dans `actions.js` : `demandeChallenge(cible, texte, solution) -> demande`, `demandeSolution(challenge, texte)`, `demandesVerdicts(challenge, cochees, toutes) -> liste` (un `verdict_solution` `valider` par solution cochée, rien pour les autres), `challengeDe(etat, cible) -> challenge | null`. `connaissances.js` : vue d'ensemble du service groupée par agent ; chaque connaissance avec date, origine, « appris du retour de <agent> sur <tâche> », marque « partagée » (y compris venant d'un autre service) ; liste des agents du service qui n'ont rien reçu depuis la période (comparée à tout le projet) ; marque « problème revenu » quand l'état la porte. `challenge.js` : volet (constat, solutions avec auteur, zone « Ma solution », « Valider la sélection ») ; un second clic ouvre le challenge existant ; envoi des verdicts l'un après l'autre, résumé de ceux partis et refusés en cas d'échec partiel ; « Demande envoyée » tant que le relevé ne le montre pas.

- [ ] **Step 1 : tests JS** — formes exactes des trois demandes, `demandesVerdicts` (non coché → absent), `challengeDe` (trouve, ne trouve pas).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur : ouvrir un challenge depuis une connaissance, voir les solutions du Directeur et du service, valider, texte hostile affiché tel quel, console vide. **Step 6 :** commit « Connaissances et geste Challenger ».

## Étape 4 — les KPI

### Task 10 : les KPI, les alertes, « problème revenu »

**Files:** Create `bureau/kpi.py`, `tests/test_kpi.py` ; Modify `bureau/releve.py`, `bureau/etat.py`, `bureau/serveur.py`, `tests/test_releve.py`, `tests/test_etat.py`

**Interfaces:**
- Produces: version 3, par service `kpi: [{id unique dans le service, nom, valeur, unite?, evolution?: texte, alerte?: bool, texte?, periodes?: {aujourdhui, 7j, 30j}}]` (valeur : nombre ou texte). `kpi.calcules(r, usages_cout, periode, maintenant) -> {service: [kpi]}` : `taches_terminees` (tâches dans une colonne `terminee` dont `maj` tombe dans la période), `allers_retours` (moyenne des `retours` par tâche), `duree_tache` (première à dernière entrée du `journal`, moyenne), `cout_moyen` (depuis `cout`). `class HistoriqueAlertes(chemin)` : `noter(service, kpi_id, en_alerte, maintenant)` garde la date de première alerte ; `lire()`. `kpi.probleme_revenu(connaissance_date, alerte_depuis) -> bool` (vrai si le KPI d'origine est en alerte avec une première alerte postérieure à la connaissance). `GET /api/kpi?periode=…` ; `Bureau.demande` passe `cibles_calculees` (`kpi:<service>:<id>`, `source:…` venant de `cout.facturation`) à `verifier` ; `etat.agents[].connaissances[].probleme_revenu`.

- [ ] **Step 1 : tests** — `test_kpi_projet_valide`, `test_kpi_id_double_dans_un_service`, `test_kpi_ok_dans_deux_services`, `test_kpi_periodes`, `test_calcules_taches_terminees`, `test_calcules_allers_retours`, `test_duree_moyenne`, `test_cout_moyen`, `test_alerte_date_de_premiere_alerte`, `test_probleme_revenu`, `test_challenge_sur_kpi_calcule_accepte`, `test_challenge_sur_source_calculee_accepte`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « KPI par service ».

### Task 11 : l'onglet KPI

**Files:** Create `bureau/web/ui/kpi.js`, `bureau/web/tests/kpi.test.js` ; Modify `bureau/web/ui/dossier.js`, `bureau/web/ui/texte.js`

**Interfaces:**
- Produces (purs, testés) : `valeurKpi(kpi, periode) -> texte` (utilise `periodes[p]` sinon `valeur`, avec l'unité) ; `etiquettePeriode(kpi) -> "toutes périodes" | null` ; `kpiEnAlerte(liste) -> liste`. `kpi.js` : grille de chiffres, `evolution` affichée telle quelle, KPI en alerte marqué avec son `texte` et un bouton « Challenger » (volet de la tâche 9) ; rappel des alertes en haut de l'onglet Tâches.

- [ ] **Step 1 : tests JS.** **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur sur la démo : grille, alerte, période, console vide. **Step 6 :** commit « Onglet KPI ».

### Task 12 : la démo, la documentation, la relecture

**Files:** Modify `exemples/demo/releve.json` (version 3 : `usage` inventé sur plusieurs modèles, `kpi`, `connaissances` dont une `appris_de` d'un autre service, un `challenge` avec trois solutions), `exemples/demo/actions.py` (applique `challenge`, `solution`, `verdict_solution`), `exemples/demo/reglages.json` (`alias_modeles`), `tests/test_demo_actions.py`, `docs/releve.md`, `docs/installation.md`, `README.md` ; Create `docs/img/dossier.jpg`

- [ ] **Step 1 : tests** — `test_demo_challenge` (challenge → solutions → validation, chaque effet relu au relevé, relevé encore valide).
- [ ] **Step 2–4 :** échec, coder, tous les tests Python et JS verts. **Step 5 :** documenter le relevé version 3 (§8 de la spec), les réglages `prix`, `alias_modeles`, `prix_automatiques`, et les deux requêtes sortantes. **Step 6 :** suivre la démo à la lettre dans le navigateur ; capture refaite. **Step 7 :** `git grep` : aucun nom, chemin ou fichier propre à un projet réel (motifs tenus hors de ce dépôt). **Step 8 :** relecteur indépendant sur tout le projet contre la spec et le Review Focus, corrections, puis commit « Dossiers des services : démo et documentation » et push.
