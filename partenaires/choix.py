"""Le choix d'un partenaire pour un besoin : les connectés utilisables, dans l'ordre des conseils du projet.

Rien ne bloque sans partenaire : une liste vide veut dire « mode manuel, navigateur (avec l'accord) ou autre voie ».
"""
import unicodedata

from partenaires.etat import limite_active

SYNONYMES = {"free": "gratuit", "gratuite": "gratuit"}


def _plat(texte):
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower().strip()
    return SYNONYMES.get(t, t)


def tarif(p, connexion):
    """Le tarif de l'usage en cours : celui du plan de l'abonnement connu ; « gratuit » si tous les plans le sont ;
    sinon « inconnu » (traité comme facturé : on demande)."""
    plans = [pl for pl in p.get("plans") or [] if isinstance(pl, dict)]
    abo = _plat((connexion or {}).get("abonnement"))
    if abo:
        for pl in plans:
            if _plat(pl.get("nom")) == abo:
                return pl.get("tarif") or "inconnu"
    if plans and all(pl.get("tarif") == "gratuit" for pl in plans):
        return "gratuit"
    return "inconnu"


def _utilisable(i, par_id, etat, instant):
    p = par_id.get(i)
    return (p is not None and p.get("statut") == "actif"
            and (etat["connexions"].get(i) or {}).get("etat") == "connecte"
            and not limite_active(etat["limites"].get(i), instant))


def ordonner(besoin, conseils, catalogue, etat, instant=None):
    """{"partenaires": [{"id", "tarif", "accord_requis"}], "meilleur_non_connecte": id | None}.

    D'abord les conseils du projet pour ce besoin (dans leur ordre), puis les autres connectés de la même
    sous-catégorie (celle des conseillés, ou le besoin lui-même s'il nomme une sous-catégorie ou une catégorie),
    dans l'ordre du catalogue. `accord_requis` : tarif à l'usage ou inconnu."""
    par_id = {p["id"]: p for p in catalogue["partenaires"]}
    conseils = [i for i in conseils if i in par_id]
    sous_cats = {par_id[i].get("sous_categorie") for i in conseils}
    b = _plat(besoin)
    for p in catalogue["partenaires"]:
        if _plat(p.get("sous_categorie")) == b or _plat(p.get("categorie")) == b:
            sous_cats.add(p.get("sous_categorie"))
    ordre = list(conseils) + [p["id"] for p in catalogue["partenaires"]
                              if p.get("sous_categorie") in sous_cats and p["id"] not in conseils]
    choisis = [i for i in ordre if _utilisable(i, par_id, etat, instant)]
    sortie = []
    for i in choisis:
        t = tarif(par_id[i], etat["connexions"].get(i))
        sortie.append({"id": i, "tarif": t, "accord_requis": t in ("usage", "inconnu")})
    return {"partenaires": sortie, "meilleur_non_connecte": _meilleur_non_connecte(conseils, choisis, ordre, par_id, etat)}


def _meilleur_non_connecte(conseils, choisis, ordre, par_id, etat):
    """Le partenaire qu'on aurait mieux fait d'utiliser : le premier conseil non connecté placé avant le premier choisi ;
    sans conseil, le plus populaire des actifs non connectés du besoin, s'il n'y a aucun choisi."""
    def non_connecte(i):
        return par_id[i].get("statut") == "actif" and (etat["connexions"].get(i) or {}).get("etat") != "connecte"
    for i in conseils:
        if choisis and i == choisis[0]:
            return None
        if non_connecte(i):
            return i
    if choisis or conseils:
        return None
    candidats = [i for i in ordre if non_connecte(i)]
    if not candidats:
        return None
    return max(candidats, key=lambda i: ((par_id[i].get("popularite") or {}).get("niveau") or 0, -candidats.index(i)))
