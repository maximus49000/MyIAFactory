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
ATTENTE_LONGUE_S = 1800     # une exécution distante attendue depuis plus de 30 min : anormalement longue
NOMS_ATTENDUS = {"apk": "l'APK"}
NOMS_LIEUX = {"github": "GitHub"}
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


def pour_la_tache(tache, taches, executions, moteur_vivant, maintenant, delai_arret_s,
                  attente_longue_s=ATTENTE_LONGUE_S):
    """Ce que dit la fiche d'une tâche : `{etat, etat_texte, points, en_cours, phase, passe_s, cumul_s, reste,
    reste_texte}` ; `moteur_vivant` : vrai, faux, ou `None` si on ne sait pas. `None` quand aucun agent n'est dessus (ni au travail, ni terminé depuis plus de 2 min)."""
    travail = tache.get("travail") if isinstance(tache.get("travail"), dict) else None
    termine = tache.get("agent_termine") if isinstance(tache.get("agent_termine"), dict) else None
    lot = tache.get("dans_le_lot") if isinstance(tache.get("dans_le_lot"), dict) and not travail else None
    if lot:
        return _dans_le_lot(lot, taches, moteur_vivant)
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
    attente = travail.get("attente_deportee") if isinstance(travail.get("attente_deportee"), dict) else None
    if attente:      # l'agent attend une exécution distante : une attente, pas un blocage (le garde-fou la laisse durer)
        depuis = _secondes(attente.get("depuis"), maintenant)
        minutes = _minutes(depuis or 0)
        attend = attente.get("attend")
        lieu = attente.get("lieu")
        qui = NOMS_ATTENDUS.get(attend, attend if isinstance(attend, str) and attend else "une exécution")
        ou = NOMS_LIEUX.get(lieu, lieu if isinstance(lieu, str) and lieu else "à distance")
        if depuis is not None and depuis >= attente_longue_s:
            return rendre("attente_longue", f"attente anormalement longue ({minutes} min) : {qui} ({ou})")
        # les durées des exécutions distantes passées ne sont pas notées : la durée habituelle est dite inconnue
        return rendre("attente_deportee", f"en attente de {qui} ({ou}, depuis {minutes} min), durée habituelle inconnue")
    arret = f"arrêt automatique à {_minutes(delai_arret_s)} min"
    attente = travail.get("attente_tests") if isinstance(travail.get("attente_tests"), dict) else None
    if attente:      # l'agent a lancé ses tests, une autre campagne occupe le poste : il attend, il n'est pas bloqué
        depuis = _secondes(attente.get("depuis"), maintenant)
        rang, total = attente.get("rang"), attente.get("total")
        position = isinstance(rang, int) and isinstance(total, int) and 1 <= rang <= total
        texte = "en attente pour lancer les tests"
        if position:
            texte += f" · position {rang} sur {total} dans la file"
            texte += " (passe dès que le poste se libère)" if rang == 1 else ""
        else:
            texte += " (une autre campagne tourne sur le poste)"
        r = rendre("attente_tests", texte + (f" · depuis {_minutes(depuis)} min" if depuis is not None else ""))
        r["file_tests"] = {"rang": rang, "total": total} if position else None
        return r
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


def _titre(taches, tid):
    t = next((x for x in taches if isinstance(x, dict) and x.get("id") == tid), None)
    titre = (t or {}).get("titre")
    return f"{tid} ({titre})" if isinstance(titre, str) and titre.strip() else str(tid)


def _dans_le_lot(lot, taches, moteur_vivant):
    """Une tâche d'un lot que la session de l'agent ne fait pas en ce moment (`dans_le_lot`, voir
    `detache.ajouter_au_travail`) : finie, l'agent poursuit le lot ; à venir, elle attend son tour dans la même session.
    Ni temps passé ni temps restant : ils sont sur la tâche en cours."""
    liste = lot.get("avancement") if isinstance(lot.get("avancement"), dict) else {}
    base = {"points": liste.get("points") or [], "en_cours": liste.get("en_cours"), "phase": None, "passe_s": None,
            "cumul_s": None, "reste": None, "reste_texte": "inconnu", "lot": {k: lot.get(k) for k in ("rang", "total")}}
    courante = _titre(taches, lot.get("courante"))
    if moteur_vivant is False:
        return {**base, "etat": "moteur_arrete", "etat_texte": "moteur arrêté : rien n'avance tant qu'il n'est pas relancé"}
    if lot.get("etat") == "faite":
        return {**base, "etat": "lot_faite", "etat_texte": f"faite ; l'agent poursuit le lot dans la même session, "
                                                           f"sur {courante}"}
    return {**base, "etat": "lot_a_venir", "etat_texte": f"attend son tour dans le lot : l'agent fait d'abord {courante}"}
