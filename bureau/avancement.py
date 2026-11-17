"""L'avancement d'une tâche, pour sa fiche : où elle en est, le temps passé, le temps restant (une fourchette) et si
l'agent avance ou est bloqué. Module pur : tout entre en paramètre (aucune lecture de fichier).

Les durées passées viennent des exécutions réelles d'agents notées par le moteur (`durees-agents.jsonl`) ; moins de 3 durées : le
temps restant est « inconnu » plutôt qu'un chiffre inventé."""
import math
import statistics

from .statuts import TRES_ANCIEN, lire_date

ACTION_RECENTE_S = 120      # une action réelle depuis moins de 2 min : l'agent avance
TERMINE_NON_LU_S = 120      # un agent terminé dont le moteur n'a pas lu le résultat depuis plus de 2 min : dit
LISTE_PERIMEE_S = 600       # la liste de l'agent n'a pas bougé depuis 10 min alors qu'il agit
MIN_DUREES = 3
DUREE_MIN_S, DUREE_MAX_S = 30, 6 * 3600     # en dehors : une durée aberrante, écartée


def _secondes(texte, maintenant):
    d = lire_date(texte)
    return None if d == TRES_ANCIEN else max(0.0, (maintenant - d).total_seconds())


def _minutes(secondes):
    return max(0, int(secondes // 60))


def durees_de_l_etape(taches, executions, etape):
    """Les durées (secondes) des exécutions réelles d'agents sur des tâches de cette étape, sans les aberrantes.
    `executions` : `[{"tache", "duree_s"}]` notées par le moteur à la fin de chaque agent (les dates `debut`/`fin` du suivi
    ne mesurent pas le travail : elles repartent à chaque reprise)."""
    etapes = {t.get("id"): t.get("etape") for t in taches if isinstance(t, dict)}
    return [e["duree_s"] for e in executions if isinstance(e, dict) and etapes.get(e.get("tache")) == etape
            and isinstance(e.get("duree_s"), (int, float)) and DUREE_MIN_S <= e["duree_s"] <= DUREE_MAX_S]


def fourchette(durees):
    """`(premier quartile, troisième quartile)` en secondes ; `None` sous 3 durées."""
    if len(durees) < MIN_DUREES:
        return None
    q = statistics.quantiles(durees, n=4, method="inclusive")
    return q[0], q[2]


def _reste(passe_s, durees, points):
    """`(reste | None, texte)` : la fourchette du temps restant, ajustée par la part de la liste déjà cochée."""
    f = fourchette(durees)
    if f is None:
        return None, "inconnu"
    bas, haut = f
    if passe_s > haut:
        return None, "plus long que d'habitude"
    mini, maxi = max(0.0, bas - passe_s), haut - passe_s
    faits = sum(1 for p in points if p.get("fait"))
    if points and faits:
        prevu = passe_s * (len(points) - faits) / faits       # au rythme déjà tenu
        maxi = min(maxi, prevu * 2)
        mini = min(mini, maxi)
    texte = f"{_minutes(mini)} à {max(_minutes(mini), math.ceil(maxi / 60))} min"
    return {"min_s": int(mini), "max_s": int(maxi)}, texte


def pour_la_tache(tache, taches, executions, moteur_vivant, maintenant, delai_arret_s):
    """Ce que dit la fiche d'une tâche : `{etat, etat_texte, points, en_cours, phase, passe_s, cumul_s, reste,
    reste_texte}` ; `moteur_vivant` : vrai, faux, ou `None` si on ne sait pas. `None` quand aucun agent n'est dessus (ni au travail, ni terminé depuis plus de 2 min)."""
    travail = tache.get("travail") if isinstance(tache.get("travail"), dict) else None
    termine = tache.get("agent_termine") if isinstance(tache.get("agent_termine"), dict) else None
    liste = (travail or {}).get("avancement") if isinstance((travail or {}).get("avancement"), dict) else {}
    points = liste.get("points") or []
    base = {"points": points, "en_cours": liste.get("en_cours"), "phase": (travail or {}).get("phase")}
    passe = _secondes((travail or {}).get("depuis"), maintenant)
    cumul = _secondes(tache.get("debut"), maintenant)
    reste, reste_texte = (None, "inconnu")
    if passe is not None:
        reste, reste_texte = _reste(passe, durees_de_l_etape(
            [x for x in taches if x.get("id") != tache.get("id")],
            [x for x in executions if x.get("tache") != tache.get("id")], tache.get("etape")), points)
    # À la minute : la fiche ne se redessine pas à chaque relevé (toutes les 2 s) pour des secondes qui passent.
    if reste:
        reste = {"min_s": reste["min_s"] // 60 * 60, "max_s": reste["max_s"] // 60 * 60}
    base.update(passe_s=None if passe is None else int(passe) // 60 * 60,
                cumul_s=None if cumul is None else int(cumul) // 60 * 60, reste=reste, reste_texte=reste_texte)

    def rendre(etat, texte):
        return {**base, "etat": etat, "etat_texte": texte}

    if travail is None and termine is None:
        return None
    if moteur_vivant is False:      # le verrou du moteur n'a plus de processus vivant : rien ne fera avancer la tâche
        return rendre("moteur_arrete", "moteur arrêté : rien n'avance tant qu'il n'est pas relancé")
    if travail is None:
        age = _secondes(termine.get("t"), maintenant)
        if age is None or age < TERMINE_NON_LU_S:
            return None
        return rendre("termine_non_lu", f"agent terminé, résultat en attente de lecture depuis {_minutes(age)} min")
    arret = f"arrêt automatique à {_minutes(delai_arret_s)} min"
    if not travail.get("action"):
        if passe is not None and passe > ACTION_RECENTE_S:      # aucune action depuis plus de 2 min : pas un démarrage
            return rendre("sans_action", f"sans action depuis {_minutes(passe)} min, {arret}")
        return rendre("demarre", "démarre")
    action, vie = _secondes(travail.get("action_t"), maintenant), _secondes(travail.get("vie_t"), maintenant)
    if action is not None and action <= ACTION_RECENTE_S:
        texte = "avance"
        maj = _secondes(liste.get("maj"), maintenant) if liste else None
        if points and maj is not None and maj >= LISTE_PERIMEE_S:
            texte += f" · liste non mise à jour depuis {_minutes(maj)} min"
        return rendre("avance", texte)
    if action is not None and vie is not None and vie <= ACTION_RECENTE_S:
        return rendre("commande_longue", f"commande longue en cours depuis {_minutes(action)} min ({arret})")
    return rendre("sans_action", f"sans action depuis {_minutes(action or vie or 0)} min, {arret}")
