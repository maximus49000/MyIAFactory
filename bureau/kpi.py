"""Les KPI d'un service : ceux du projet (tels quels) et ceux que le bureau tire du relevé.

Le bureau ne connaît aucune règle d'un projet : un KPI du projet est montré comme il le donne, alerte
comprise. Il calcule lui-même quatre chiffres (tâches terminées, allers-retours moyens, durée moyenne
d'une tâche, coût moyen par tâche) sur la période choisie. Il garde aussi la date de première alerte de
chaque KPI du projet, pour dire si un problème est « revenu » après la connaissance qui devait le régler.
"""
import json
import os
import threading
from datetime import timedelta
from pathlib import Path

from .cout import _dans_la_periode, euros_en_clair
from .statuts import TRES_ANCIEN, duree_en_clair, lire_date

LIBELLES_PERIODE = {"aujourdhui": "aujourd'hui", "7j": "les 7 derniers jours", "30j": "les 30 derniers jours"}
SANS_TACHE = ""  # clé de « hors tâche » dans cout.facturation


def _service_de(r):
    """{clé de titulaire: service} ; le chef n'a pas de service."""
    return {t["cle"]: t.get("service") for t in r.get("titulaires", []) if not t.get("chef") and t.get("service")}


def _calcule(id_, nom, valeur, periode, unite=None):
    return {"id": id_, "nom": nom, "valeur": valeur, "unite": unite, "evolution": None, "alerte": False,
            "texte": None, "periodes": {periode: valeur}, "calcule": True}


def _duree_minutes(tache):
    dates = [lire_date(j.get("t")) for j in tache.get("journal") or [] if isinstance(j, dict)]
    dates = [d for d in dates if d != TRES_ANCIEN]
    if len(dates) < 2:
        return None
    return (max(dates) - min(dates)) / timedelta(minutes=1)


def calcules(r, usages_cout, periode, maintenant):
    """{service: [kpi calculés]} ; un chiffre sans donnée est omis plutôt que montré à 0.
    `usages_cout` : le résultat de `cout.facturation` pour la même période (ou None)."""
    service_de = _service_de(r)
    terminees = {c["id"] for c in r.get("colonnes", []) if c.get("terminee")}
    par_service = {s["id"]: [] for s in r.get("services", [])}
    for t in r.get("taches", []):
        s = service_de.get(t.get("titulaire"))
        if s in par_service and _dans_la_periode(t.get("maj"), periode, maintenant):
            par_service[s].append(t)
    sortie = {}
    for sid, taches in par_service.items():
        liste = [_calcule("taches_terminees", "Tâches terminées",
                          sum(1 for t in taches if t.get("colonne") in terminees), periode, "tâches")]
        if taches:
            moyenne = sum(len(t.get("retours") or []) for t in taches) / len(taches)
            liste.append(_calcule("allers_retours", "Allers-retours moyens", round(moyenne, 1), periode, "par tâche"))
        durees = [d for d in map(_duree_minutes, taches) if d is not None]
        if durees:
            liste.append(_calcule("duree_tache", "Durée moyenne d'une tâche",
                                  duree_en_clair(sum(durees) / len(durees)), periode))
        couts = [c["total"] for i, c in ((usages_cout or {}).get("services", {}).get(sid) or {}).get("taches", {}).items()
                 if i != SANS_TACHE and c["total"] > 0]
        if couts:
            liste.append(_calcule("cout_moyen", "Coût moyen par tâche", euros_en_clair(sum(couts) / len(couts)),
                                  periode))
        sortie[sid] = liste
    return sortie


def du_projet(r):
    """{service: [kpi du projet]} pour les services qui en donnent une liste."""
    return {s["id"]: [dict(k, calcule=False) for k in s["kpi"]]
            for s in r.get("services", []) if isinstance(s.get("kpi"), list)}


def tous(r, usages_cout, periode, maintenant):
    """Ceux du projet d'abord, puis les calculés dont l'identifiant n'est pas déjà pris par le projet."""
    projet, calcule = du_projet(r), calcules(r, usages_cout, periode, maintenant)
    sortie = {}
    for sid in {s["id"] for s in r.get("services", [])}:
        propres = projet.get(sid, [])
        pris = {k["id"] for k in propres}
        sortie[sid] = propres + [k for k in calcule.get(sid, []) if k["id"] not in pris]
    return sortie


def constats(r, usages_cout, periode, maintenant):
    """{kpi:<service>:<id>: constat en clair} des KPI calculés (les seules cibles que le bureau recalcule)."""
    projet = du_projet(r)
    noms = {s["id"]: s.get("nom") or s["id"] for s in r.get("services", [])}
    sortie = {}
    for sid, liste in calcules(r, usages_cout, periode, maintenant).items():
        pris = {k["id"] for k in projet.get(sid, [])}
        for k in liste:
            if k["id"] in pris:
                continue
            valeur = f"{k['valeur']} {k['unite']}" if k["unite"] else f"{k['valeur']}"
            sortie[f"kpi:{sid}:{k['id']}"] = (f"KPI « {k['nom']} » du service « {noms[sid]} » : {valeur} sur "
                                              f"{LIBELLES_PERIODE[periode]}.")
    return sortie


def cible_kpi(identifiant, ids_services):
    """(service, id du KPI) d'une cible `kpi:<service>:<id>` ; None si ce n'en est pas une."""
    if not isinstance(identifiant, str) or not identifiant.startswith("kpi:"):
        return None
    reste = identifiant[4:]
    for sid in sorted(ids_services, key=len, reverse=True):  # un identifiant de service peut contenir « : »
        if reste.startswith(sid + ":") and len(reste) > len(sid) + 1:
            return sid, reste[len(sid) + 1:]
    return None


class HistoriqueAlertes:
    """Une ligne par changement d'état d'un KPI du projet (entrée ou sortie d'alerte). La date de
    première alerte est celle de la dernière entrée en alerte : une alerte qui cesse puis revient
    redevient « première » à son retour."""

    def __init__(self, chemin):
        self.chemin = Path(chemin)
        self._verrou = threading.Lock()
        self._etat = self._relire()

    def _relire(self):
        """{(service, kpi): date de l'entrée en alerte | None}."""
        etat = {}
        try:
            texte = self.chemin.read_text(encoding="utf-8")
        except OSError:
            return etat
        for brut in texte.splitlines():
            try:
                d = json.loads(brut)
            except ValueError:
                continue
            if (isinstance(d, dict) and isinstance(d.get("service"), str) and isinstance(d.get("kpi"), str)
                    and isinstance(d.get("t"), str) and isinstance(d.get("alerte"), bool)):
                etat[(d["service"], d["kpi"])] = d["t"] if d["alerte"] else None
        return etat

    def noter(self, service, kpi_id, en_alerte, maintenant):
        with self._verrou:
            cle = (service, kpi_id)
            deja = self._etat.get(cle)
            if (deja is not None) == bool(en_alerte):
                return  # rien n'a changé (un KPI jamais vu et hors alerte n'est pas noté)
            t = maintenant.isoformat()
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            with open(self.chemin, "a", encoding="utf-8") as f:
                f.write(json.dumps({"service": service, "kpi": kpi_id, "t": t, "alerte": bool(en_alerte)},
                                   ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._etat[cle] = t if en_alerte else None

    def lire(self):
        """{(service, kpi): date de première alerte} des KPI actuellement en alerte."""
        with self._verrou:
            return {c: t for c, t in self._etat.items() if t is not None}


def suivre_alertes(r, historique, maintenant):
    """Note l'état d'alerte des KPI du projet et rend les alertes en cours."""
    for sid, liste in du_projet(r).items():
        for k in liste:
            historique.noter(sid, k["id"], k.get("alerte") is True, maintenant)
    return historique.lire()


def probleme_revenu(connaissance_date, alerte_depuis):
    """Vrai si le KPI d'origine est en alerte depuis une date postérieure à la connaissance. Une date
    de connaissance sans heure compte jusqu'à la fin de sa journée (heure locale)."""
    if not alerte_depuis or not isinstance(connaissance_date, str):
        return False
    c, a = lire_date(connaissance_date), lire_date(alerte_depuis)
    if c == TRES_ANCIEN or a == TRES_ANCIEN:
        return False
    if len(connaissance_date.strip()) <= 10:
        return a.astimezone().date() > c.date()
    return a > c
