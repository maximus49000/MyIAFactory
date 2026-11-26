"""Banc de cas rejoués de « Claude autonome » : des cas réels figés (dossier reçu par `decider_autonome`, réponse attendue,
note), un chargeur, une notation et un rejeu. Voir `LISEZMOI.md` (rejeu avec le vrai jugement, ajout d'un cas).

Un cas (`cas/NN_nom.json`) :
- `type` : `jugement` (le dossier de `decider_autonome`), `hors_jugement` (une décision qui ne doit jamais arriver à Claude)
  ou `moteur_impasse` (une règle du moteur rejouée sur un état figé) ;
- `dossier`, `attendu`, `note` (pourquoi), `simule` (la réponse valable qui sert au test rapide, sans appel), `negatif`.

`attendu` (tous les champs sont facultatifs, sauf `verdicts` pour un jugement) :
- `verdicts` : les verdicts acceptables ; `choix_commence_par` : avec `choisir`, le choix doit commencer ainsi ;
- `tache_dev` : la tâche de dev visée par `renvoyer` ; `amelioration` : une amélioration doit être notée ;
- `texte_evoque` : liste de groupes, le texte doit contenir au moins un mot de chaque groupe (sans casse) ;
  `texte_evoque_si_refus` : idem, seulement pour `refuser` ; `texte_exclut` : mots qui ne doivent pas y figurer.
"""
import json
from pathlib import Path

DOSSIER_CAS = Path(__file__).resolve().parent / "cas"
TYPES = ("jugement", "hors_jugement", "moteur_impasse")


def charger(dossier=DOSSIER_CAS):
    """Tous les cas, triés par id. Un cas mal formé lève `ValueError` en disant lequel."""
    cas = []
    for f in sorted(Path(dossier).glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if c.get("id") != f.stem:
            raise ValueError(f"{f.name} : « id » doit valoir {f.stem}.")
        for cle in ("titre", "type", "note", "dossier", "attendu"):
            if not c.get(cle):
                raise ValueError(f"{f.name} : « {cle} » est obligatoire.")
        if c["type"] not in TYPES:
            raise ValueError(f"{f.name} : type inconnu {c['type']}.")
        if c["type"] == "jugement" and not (c["attendu"].get("verdicts") and isinstance(c.get("simule"), dict)):
            raise ValueError(f"{f.name} : un cas de jugement a `attendu.verdicts` et `simule`.")
        cas.append(c)
    return cas


def _contient(texte, mots):
    t = (texte or "").lower()
    return any(m.lower() in t for m in mots)


def noter(cas, objet):
    """(juste, [défauts]) : la réponse `objet` de Claude (un dict) à un cas de jugement, comparée à l'attendu."""
    a, defauts = cas["attendu"], []
    verdict, texte = objet.get("verdict"), objet.get("texte")
    if verdict not in a["verdicts"]:
        defauts.append(f"verdict {verdict!r} au lieu de {' ou '.join(a['verdicts'])}")
        return False, defauts
    if verdict == "choisir" and a.get("choix_commence_par") and not str(objet.get("choix") or "").startswith(a["choix_commence_par"]):
        defauts.append(f"choix {objet.get('choix')!r} : devait commencer par {a['choix_commence_par']!r}")
    if a.get("tache_dev") and verdict == "renvoyer" and objet.get("tache_dev") != a["tache_dev"]:
        defauts.append(f"tache_dev {objet.get('tache_dev')!r} au lieu de {a['tache_dev']!r}")
    if a.get("amelioration") and not objet.get("amelioration"):
        defauts.append("aucune amélioration notée")
    groupes = list(a.get("texte_evoque") or []) + (list(a.get("texte_evoque_si_refus") or []) if verdict == "refuser" else [])
    for g in groupes:
        if not _contient(texte, g):
            defauts.append(f"le texte devait évoquer l'un de : {', '.join(g)}")
    if texte and _contient(texte, a.get("texte_exclut") or []):
        defauts.append("le texte contient un mot interdit")
    return not defauts, defauts


def decision_du_dossier(cas):
    """La décision (`d`) telle que le moteur la porte, reconstruite du dossier : de quoi appeler `_demande_autonome`."""
    dec, t = cas["dossier"]["decision"], cas["dossier"].get("tache") or {}
    return {"id": cas.get("decision_id", "d1"), "genre": dec["genre"], "tache": t.get("id"), "motif": dec.get("motif")}


def rejouer(cas, juger):
    """Un cas rejoué : `juger(dossier)` rend la réponse (dict) de Claude, ou lève une exception. Rend un dict :
    `id`, `attendu` (texte court), `obtenu` (texte court), `juste` (bool), `defauts`."""
    attendu = " ou ".join((cas["attendu"].get("verdicts") or [])) or ("aucun jugement" if cas["type"] == "hors_jugement" else "aucune impasse")
    if cas["type"] == "jugement":
        try:
            objet = juger(cas["dossier"])
        except Exception as e:  # noqa: BLE001 : un cas qui échoue ne doit pas arrêter le rejeu
            return {"id": cas["id"], "attendu": attendu, "obtenu": f"erreur : {e}", "juste": False, "defauts": [str(e)]}
        juste, defauts = noter(cas, objet)
        return {"id": cas["id"], "attendu": attendu, "obtenu": str(objet.get("verdict")), "juste": juste, "defauts": defauts}
    from moteur import regles
    if cas["type"] == "hors_jugement":
        genre = cas["dossier"]["decision"]["genre"]
        juste = genre not in regles.VERDICTS_AUTONOMES and regles._reponse_autonome({"id": "d1", "genre": genre}) is None
        return {"id": cas["id"], "attendu": attendu, "obtenu": "aucun jugement" if juste else "un jugement serait demandé",
                "juste": juste, "defauts": [] if juste else [f"le genre {genre} arrive à Claude autonome"]}
    from unittest import mock
    court, detail = cas["dossier"]["etat_court"], cas["dossier"]["detail"]
    with mock.patch.object(regles, "_etat", return_value=court), mock.patch.object(regles, "_fonc", return_value=detail):
        obtenues = regles.impasses(None, regles.nouvel_etat(), delai=0)
    juste = [list(x) for x in obtenues] == cas["attendu"]["impasses"]
    return {"id": cas["id"], "attendu": attendu, "obtenu": "aucune impasse" if not obtenues else f"impasse : {obtenues}",
            "juste": juste, "defauts": [] if juste else [f"impasses obtenues : {obtenues}"]}


def score(resultats):
    justes = sum(1 for r in resultats if r["juste"])
    return justes, len(resultats)
