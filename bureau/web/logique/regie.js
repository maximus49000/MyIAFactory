// La régie : qui est où, qui va où, la file au tableau, le temps qui passe.
// Classe pure : ni DOM, ni three.js. Le rendu lit `acteurs` et `postits`.

const VITESSE = 1.5;        // m/s
const DUREE_POSE = 1.2;     // s devant le tableau pour poser un post-it
const MAX_MISSIONS = 6;     // au-delà, les post-its sont déplacés directement
const PAS = 0.1;            // s : avancer() découpe le temps en pas de cette taille au plus

export class Regie {
  constructor(plan) {
    this.plan = plan;
    this.acteurs = new Map();   // id -> {x, z, cap, action, agent}
    this.postits = new Map();   // tacheId -> {colonne, rang}
    this.etat = null;
    this._postes = new Map();   // agentId -> {service, i} : indice de place dans ce service
    this._cafe = new Map();     // agentId -> indice de place au café
    this._missions = new Map(); // porteurId -> [{tache, vers}]
    this._file = [];            // porteurs, dans l'ordre de passage au tableau
    this._minuteur = 0;
    this._idChef = null;
  }

  get nombreMissions() {
    let n = 0;
    for (const l of this._missions.values()) n += l.length;
    return n;
  }

  // Remet tout à plat sur cet état : chacun à sa place, post-its à leur colonne, aucune mission.
  reinitialiser(etat) {
    this.acteurs.clear();
    this.postits.clear();
    this._postes.clear();
    this._cafe.clear();
    this._missions.clear();
    this._file = [];
    this._minuteur = 0;
    this.etat = null;
    this.appliquer(etat, []);
  }

  appliquer(etat, changements) {
    const premier = this.etat === null;
    this.etat = etat;
    const agents = new Map((etat.agents || []).map((a) => [a.id, a]));
    const chef = (etat.agents || []).find((a) => a.chef);
    this._idChef = chef ? chef.id : null;

    // Agents partis : leurs missions passent au chef.
    for (const id of [...this.acteurs.keys()]) {
      if (agents.has(id)) continue;
      this.acteurs.delete(id);
      this._postes.delete(id);
      this._cafe.delete(id);
      this._transmettre(id);
    }

    // Agents présents : création, mise à jour, places.
    for (const a of agents.values()) {
      let acteur = this.acteurs.get(a.id);
      const nouveau = !acteur;
      if (nouveau) {
        acteur = {x: 0, z: 0, cap: 0, action: "debout", agent: a, _cle: null, _chemin: [], _dest: null};
        this.acteurs.set(a.id, acteur);
      }
      acteur.agent = a;
      this._placer(a);
      if (nouveau) this._poser(acteur);
    }

    // Tâches visibles sur le tableau.
    const taches = (etat.taches || []).filter((t) => t.postit !== false);
    const ids = new Set(taches.map((t) => t.id));
    for (const id of [...this.postits.keys()]) if (!ids.has(id)) this.postits.delete(id);
    for (const [porteur, liste] of this._missions) {
      const reste = liste.filter((m) => ids.has(m.tache));
      if (reste.length) this._missions.set(porteur, reste);
      else this._retirerPorteur(porteur);
    }

    if (!premier) {
      for (const c of changements || []) {
        if (!ids.has(c.tache)) continue;
        const enCours = this._missionDe(c.tache);
        if (enCours) { enCours.vers = c.vers; continue; }
        const porteur = this.acteurs.has(c.porteur) ? c.porteur : this._idChef;
        if (!porteur || !this.acteurs.has(porteur) || this.nombreMissions >= MAX_MISSIONS) continue;
        if (!this._missions.has(porteur)) this._missions.set(porteur, []);
        this._missions.get(porteur).push({tache: c.tache, vers: c.vers});
        if (!this._file.includes(porteur)) this._file.push(porteur);
      }
    }

    // Tout post-it sans mission est à sa place réelle.
    for (const t of taches) {
      if (this._missionDe(t.id)) continue;
      const p = this.postits.get(t.id);
      if (!p || p.colonne !== t.colonne) this.postits.set(t.id, {colonne: t.colonne, rang: 0});
    }
    this._ranger();

    if (premier) for (const acteur of this.acteurs.values()) this._poser(acteur);
  }

  avancer(dt) {
    if (!(dt > 0)) {
      for (const acteur of this.acteurs.values()) this._viser(acteur);
      return;
    }
    let reste = Math.min(dt, 24 * 3600);
    while (reste > 1e-9) {
      const pas = Math.min(PAS, reste);
      this._pas(pas);
      reste -= pas;
    }
  }

  // --- interne

  _pas(dt) {
    for (const acteur of this.acteurs.values()) {
      this._viser(acteur);
      let distance = VITESSE * dt;
      while (distance > 0 && acteur._chemin.length) {
        const cible = acteur._chemin[0];
        const dx = cible.x - acteur.x, dz = cible.z - acteur.z;
        const d = Math.hypot(dx, dz);
        if (d > 1e-9) acteur.cap = Math.atan2(dx, dz);
        if (d <= distance) {
          acteur.x = cible.x; acteur.z = cible.z;
          acteur._chemin.shift();
          distance -= d;
        } else {
          acteur.x += dx / d * distance; acteur.z += dz / d * distance;
          distance = 0;
        }
      }
      if (acteur._chemin.length) { acteur.action = "marche"; acteur.assis = false; }
      else this._arrive(acteur);
    }

    const tete = this._file[0];
    const acteur = tete && this.acteurs.get(tete);
    if (acteur && !acteur._chemin.length && acteur._dest && acteur._dest.tableau) {
      acteur.action = "postit";
      this._minuteur += dt;
      if (this._minuteur >= DUREE_POSE - 1e-9) {
        this._minuteur = 0;
        const liste = this._missions.get(tete);
        const m = liste.shift();
        this.postits.set(m.tache, {colonne: m.vers, rang: 0});
        this._ranger();
        if (!liste.length) this._retirerPorteur(tete);
      }
    }
  }

  // Calcule la destination et, si elle a changé, le chemin pour y aller.
  _viser(acteur) {
    const d = this._destination(acteur);
    const cle = `${d.x.toFixed(3)}|${d.z.toFixed(3)}`;
    acteur._dest = d;
    if (cle !== acteur._cle) {
      acteur._cle = cle;
      acteur._chemin = this.plan.chemin({x: acteur.x, z: acteur.z}, d).slice(1);
    }
  }

  _arrive(acteur) {
    const d = acteur._dest;
    acteur.x = d.x; acteur.z = d.z; acteur.cap = d.cap; acteur.action = d.action;
    acteur.assis = Boolean(d.assis);
  }

  _poser(acteur) {
    const d = this._destination(acteur);
    acteur._dest = d;
    acteur._cle = `${d.x.toFixed(3)}|${d.z.toFixed(3)}`;
    acteur._chemin = [];
    this._arrive(acteur);
  }

  _destination(acteur) {
    const a = acteur.agent;
    const k = this._file.indexOf(a.id);
    if (k >= 0) {
      const kanban = this.plan.kanban;
      if (k === 0) {
        const m = this._missions.get(a.id)[0];
        const i = Math.max(0, (this.etat.colonnes || []).findIndex((c) => c.id === m.vers));
        return {...kanban.devantColonne(i), action: "debout", tableau: true};
      }
      return {...kanban.attente(k - 1), action: "debout"};
    }
    if (a.chef) return {...this.plan.chef, action: "debout"};
    if (this._postes.has(a.id)) {
      const p = this.plan.poste(a.service, this._postes.get(a.id).i);
      return {...p, action: p.assis ? "assis" : "debout"};
    }
    return {...this.plan.cafe(this._cafe.get(a.id) ?? 0), action: "cafe"};
  }

  _placer(a) {
    const travaille = !a.chef && (a.statut === "travail" || a.statut === "sans_nouvelles") && this.plan.aService(a.service);
    if (travaille) {
      this._cafe.delete(a.id);
      // Changement de service : la place gardée était celle de l'ancien service.
      if (this._postes.get(a.id)?.service !== a.service) this._postes.delete(a.id);
      if (!this._postes.has(a.id)) {
        const pris = new Set();
        for (const p of this._postes.values()) if (p.service === a.service) pris.add(p.i);
        let i = 0;
        while (pris.has(i)) i++;
        this._postes.set(a.id, {service: a.service, i});
      }
    } else {
      this._postes.delete(a.id);
      if (!a.chef && !this._cafe.has(a.id)) {
        const pris = new Set(this._cafe.values());
        let i = 0;
        while (pris.has(i)) i++;
        this._cafe.set(a.id, i);
      }
    }
  }

  _missionDe(tache) {
    for (const l of this._missions.values()) {
      const m = l.find((x) => x.tache === tache);
      if (m) return m;
    }
    return null;
  }

  _retirerPorteur(id) {
    this._missions.delete(id);
    const k = this._file.indexOf(id);
    if (k >= 0) this._file.splice(k, 1);
    if (k === 0) this._minuteur = 0;
  }

  _transmettre(id) {
    const liste = this._missions.get(id);
    const k = this._file.indexOf(id);
    this._retirerPorteur(id);
    const chef = this._idChef;
    if (!liste || !liste.length || !chef || chef === id || !this.acteurs.has(chef)) return;
    if (!this._missions.has(chef)) this._missions.set(chef, []);
    this._missions.get(chef).push(...liste);
    if (!this._file.includes(chef)) this._file.splice(Math.max(0, k), 0, chef);
  }

  // Rang de chaque post-it dans sa colonne, dans l'ordre des tâches de l'état.
  _ranger() {
    const compte = new Map();
    for (const t of this.etat.taches || []) {
      const p = this.postits.get(t.id);
      if (!p) continue;
      const r = compte.get(p.colonne) || 0;
      p.rang = r;
      compte.set(p.colonne, r + 1);
    }
  }
}
