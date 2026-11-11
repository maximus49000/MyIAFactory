"""Le calibrage de la machine : charge maximum et nombre d'agents locaux en parallèle.

Part de ce que le bureau sait déjà faire (`bureau.charge`). Hors Windows la mesure n'existe pas : valeur prudente."""
import math
import statistics

from bureau import charge

MESURES_MIN = 30


def _repos_et_par_agent(historique):
    actifs = [x for x in historique if x["agents_locaux"] >= 1]
    au_repos = [x["charge"] for x in historique if x["agents_locaux"] == 0]
    repos = statistics.median(au_repos) if au_repos else min(x["charge"] for x in historique)
    par_agent = max(0.0, statistics.median((x["charge"] - repos) / x["agents_locaux"] for x in actifs))
    return repos, par_agent


def calibrer(mach, historique):
    conseil = charge.conseiller(historique, mach)
    charge_max = conseil["valeur"]
    if not mach.get("disponible", True):
        return {"charge_max": charge_max, "agents_locaux_max": 1, "source": "indisponible",
                "explication": "Mesure indisponible sur cette machine : 1 agent local, par prudence."}
    actifs = [x for x in historique if x["agents_locaux"] >= 1]
    if len(actifs) < MESURES_MIN:
        n = min(mach["coeurs"] // 4, int(mach["memoire_totale_go"] // 6))
        n = max(1, min(4, n))
        return {"charge_max": charge_max, "agents_locaux_max": n, "source": "machine",
                "explication": (f"D'après la machine ({mach['coeurs']} cœurs, {mach['memoire_totale_go']:.0f} Go) : "
                                f"{n} agent{'s' if n > 1 else ''} local{'aux' if n > 1 else ''} au plus, "
                                f"charge maximum {charge_max} %.")}
    repos, par_agent = _repos_et_par_agent(historique)
    n = max(1, min(6, math.floor((85 - repos) / par_agent))) if par_agent > 0 else 6
    return {"charge_max": charge_max, "agents_locaux_max": n, "source": "historique",
            "explication": (f"Au repos la machine est à {repos:.0f} %, chaque agent local ajoute environ "
                            f"{par_agent:.0f} % : {n} agent{'s' if n > 1 else ''} local{'aux' if n > 1 else ''} "
                            f"au plus, charge maximum {charge_max} %.")}
