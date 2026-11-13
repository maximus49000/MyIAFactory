"""Statuts des agents : dates, fraîcheur, pause, départ, bulles."""
from datetime import datetime, timedelta, timezone

TRES_ANCIEN = datetime(1970, 1, 1, tzinfo=timezone.utc)
LONGUEUR_BULLE = 40
DEPART_APRES = timedelta(hours=24)


def lire_date(texte):
    """Date ISO 8601 avec fuseau. Sans fuseau : heure locale. Illisible : TRES_ANCIEN."""
    if not isinstance(texte, str) or not texte.strip():
        return TRES_ANCIEN
    try:
        d = datetime.fromisoformat(texte.strip())
        if d.tzinfo is None:
            d = d.astimezone()
        return d
    except (ValueError, OverflowError, OSError):
        return TRES_ANCIEN


def duree_en_clair(minutes):
    if minutes < 60:
        return f"{int(minutes)} min"
    if minutes < 48 * 60:
        return f"{int(minutes // 60)} h"
    return f"{int(minutes // (24 * 60))} j"


def _tronquer(titre):
    titre = titre if isinstance(titre, str) else ""
    return titre if len(titre) <= LONGUEUR_BULLE else titre[:LONGUEUR_BULLE] + "…"


def _age_min(tache, maintenant):
    return (maintenant - lire_date(tache.get("maj"))).total_seconds() / 60


def statut(taches, maintenant, fraicheur_min, en_pause):
    actives = [x for x in taches if x.get("active")]
    if not actives:
        return {"statut": "libre", "bulle": ""}
    actives.sort(key=lambda x: lire_date(x.get("maj")), reverse=True)
    recente = actives[0]
    age = _age_min(recente, maintenant)
    if age <= fraicheur_min:
        bulle = _tronquer(recente.get("titre"))
        if len(actives) > 1:
            bulle += f" (+{len(actives) - 1})"
        return {"statut": "travail", "bulle": bulle}
    if en_pause:
        return {"statut": "libre", "bulle": ""}
    if lire_date(recente.get("maj")) == TRES_ANCIEN:
        return {"statut": "sans_nouvelles", "bulle": "sans nouvelles"}
    return {"statut": "sans_nouvelles", "bulle": "sans nouvelles depuis " + duree_en_clair(age)}


VIE_RECENTE_MIN = 5    # un agent local qui a donné signe de vie depuis moins de 5 min : l'atelier est actif


def activite_des_agents(etat_factory, taches, maintenant):
    """Un agent local qui travaille (`travail` : sa dernière action, ses signes de vie) est une activité de l'atelier,
    même si le suivi n'a pas bougé (essai réel : « sans activité depuis 48 min » pendant que Léa lançait ses tests).
    Met à jour `derniere_activite` et `inactive` du voyant, en place."""
    if not isinstance(etat_factory, dict):
        return etat_factory
    vies = [lire_date((t.get("travail") or {}).get(c)) for t in taches if isinstance(t, dict)
            for c in ("vie_t", "action_t", "depuis")]
    vies = [d for d in vies if d != TRES_ANCIEN]
    if not vies:
        return etat_factory
    recente = max(vies)
    avant = lire_date(etat_factory.get("derniere_activite"))
    if avant == TRES_ANCIEN or recente > avant:
        etat_factory["derniere_activite"] = recente.isoformat()
    if (maintenant - recente).total_seconds() / 60 <= VIE_RECENTE_MIN:
        etat_factory["inactive"] = False
    return etat_factory


def agents_au_travail(agents, taches):
    """Un agent dont le processus local tourne sur une de ses tâches (`travail`, ajouté par le bureau) est au travail,
    même si le suivi n'a pas bougé depuis longtemps (essai réel : Hugo lançait les tests, sa bulle disait « sans
    nouvelles depuis 31 min »). Modifie `agents` en place."""
    par_id = {t.get("id"): t for t in taches if isinstance(t, dict)}
    for a in agents:
        if a.get("statut") != "sans_nouvelles":
            continue
        vivantes = [par_id[i] for i in a.get("taches") or [] if i in par_id and par_id[i].get("travail")]
        if vivantes:
            a["statut"] = "travail"
            a["bulle"] = _tronquer(vivantes[0].get("titre")) + (f" (+{len(vivantes) - 1})" if len(vivantes) > 1 else "")
    return agents


def present(titulaire, taches, maintenant):
    if titulaire.get("permanent") or titulaire.get("chef"):
        return True
    if any(x.get("active") for x in taches):
        return True
    if not taches:
        return False
    derniere = max(lire_date(x.get("maj")) for x in taches)
    return maintenant - derniere < DEPART_APRES


def factory(releve_factory, taches, maintenant, fraicheur_min):
    dates = [lire_date(x.get("maj")) for x in taches]
    dates = [d for d in dates if d != TRES_ANCIEN]
    derniere = max(dates) if dates else None
    en_marche = releve_factory.get("etat") == "en marche"
    inactive = en_marche and (derniere is None
                              or (maintenant - derniere).total_seconds() / 60 > fraicheur_min)
    return {"etat": releve_factory.get("etat"), "depuis": releve_factory.get("depuis"),
            "derniere_activite": derniere.isoformat() if derniere else None,
            "inactive": bool(inactive)}
