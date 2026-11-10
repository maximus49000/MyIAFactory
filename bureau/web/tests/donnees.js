// Données inventées partagées par les tests de la logique de la page.

export const SERVICES = [{id: "dev", nom: "Dev"}, {id: "qa", nom: "QA"}];
export const COLS = [
  {id: "afaire", nom: "À faire"}, {id: "encours", nom: "En cours"},
  {id: "revue", nom: "Relecture"}, {id: "fait", nom: "Fait"},
];

function agent(id, service, statut, extra = {}) {
  return {id, prenom: id, service, lieu: "local", modele: "Sonnet", couleur: "#2f6fd0",
          chef: false, statut, bulle: "", taches: [], ...extra};
}

// E1 : dev1 travaille sur t1 (en cours), qa1 est libre, t2 attend sans titulaire.
export const E1 = {
  version: 1, horodatage: "2026-11-10T10:00:00", projet: "Démo", erreur: null,
  factory: {etat: "en marche", depuis: "2026-11-10T09:00:00", derniere_activite: "2026-11-10T09:59:00", inactive: false},
  services: SERVICES, colonnes: COLS, file: {visibles: [], reste: 0}, decisions: 0,
  agents: [
    agent("chef", null, "libre", {chef: true}),
    agent("dev1", "dev", "travail", {taches: ["t1"]}),
    agent("qa1", "qa", "libre"),
  ],
  taches: [
    {id: "t1", titre: "Écran d'accueil", colonne: "encours", agent: "dev1", etape: "", maj: "", postit: true},
    {id: "t2", titre: "Rapport", colonne: "afaire", agent: null, etape: "", maj: "", postit: true},
    {id: "t9", titre: "Interne", colonne: "encours", agent: null, etape: "", maj: "", postit: false},
  ],
};

export function copie(e) { return JSON.parse(JSON.stringify(e)); }

export function modifier(etat, idTache, champs) {
  const e = copie(etat);
  Object.assign(e.taches.find((t) => t.id === idTache), champs);
  return e;
}

export function statut(etat, idAgent, s) {
  const e = copie(etat);
  e.agents.find((a) => a.id === idAgent).statut = s;
  return e;
}

export function sansAgent(etat, idAgent) {
  const e = copie(etat);
  e.agents = e.agents.filter((a) => a.id !== idAgent);
  for (const t of e.taches) if (t.agent === idAgent) t.agent = null;
  return e;
}

// E2 : t1 passe en relecture et part chez qa1 ; dev1 n'a plus rien, qa1 travaille.
export const E2 = statut(statut(modifier(E1, "t1", {colonne: "revue", agent: "qa1"}), "dev1", "libre"), "qa1", "travail");
