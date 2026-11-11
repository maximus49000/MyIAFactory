"""Lire ce qu'il reste chez un partenaire, par son API. Un lecteur par partenaire qui le permet.

La clé n'est envoyée qu'à l'adresse fixe du partenaire (jamais à une adresse venue d'un fichier), dans l'en-tête qu'il
attend ; elle n'est ni gardée, ni écrite, ni rendue. Toute erreur (réseau, refus, réponse inattendue) rend `None` :
« quota inconnu », jamais zéro.
"""
import json
import urllib.request

DELAI_S = 10
OCTETS_MAX = 1_000_000
ILLIMITE_DEEPL = 1_000_000_000_000   # la valeur que DeepL donne pour « aucune limite »


def _ouvrir(url, entetes):
    """Le JSON d'un GET (délai 10 s, réponse bornée). Lève une exception en cas d'échec."""
    req = urllib.request.Request(url, headers={**entetes, "Accept": "application/json",
                                                "User-Agent": "MyIAFactory-quota"})
    with urllib.request.urlopen(req, timeout=DELAI_S) as r:
        return json.loads(r.read(OCTETS_MAX).decode("utf-8"))


def _n(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x:
        raise ValueError("nombre attendu")
    return x


def _elevenlabs(cle, ouvrir):
    d = ouvrir("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": cle})
    r = {"reste": max(0, _n(d["character_limit"]) - _n(d["character_count"])), "unite": "caractères"}
    if isinstance(d.get("tier"), str) and d["tier"]:
        r["abonnement"] = d["tier"]
    return r


def _bfl(cle, ouvrir):
    return {"reste": _n(ouvrir("https://api.bfl.ai/v1/credits", {"x-key": cle})["credits"]), "unite": "crédits"}


def _stability(cle, ouvrir):
    d = ouvrir("https://api.stability.ai/v1/user/balance", {"Authorization": f"Bearer {cle}"})
    return {"reste": _n(d["credits"]), "unite": "crédits"}


def _leonardo(cle, ouvrir):
    d = ouvrir("https://cloud.leonardo.ai/api/rest/v1/me", {"Authorization": f"Bearer {cle}"})
    u = d["user_details"][0]
    jetons = [u.get(c) for c in ("apiSubscriptionTokens", "apiPaidTokens") if u.get(c) is not None]
    if not jetons:
        raise ValueError("aucun solde d'API dans la réponse")
    return {"reste": sum(_n(x) for x in jetons), "unite": "jetons d'API"}


def _meshy(cle, ouvrir):
    d = ouvrir("https://api.meshy.ai/openapi/v1/balance", {"Authorization": f"Bearer {cle}"})
    return {"reste": _n(d["balance"]), "unite": "crédits"}


def _removebg(cle, ouvrir):
    a = ouvrir("https://api.remove.bg/v1.0/account", {"X-Api-Key": cle})["data"]["attributes"]
    r = {"reste": _n(a["credits"]["total"]), "unite": "crédits"}
    gratuits = (a.get("api") or {}).get("free_calls")
    if gratuits is not None:
        r["unite"] = f"crédits (et {int(_n(gratuits))} appels gratuits)"
    return r


def _deepl(cle, ouvrir):
    hote = "api-free.deepl.com" if cle.endswith(":fx") else "api.deepl.com"
    d = ouvrir(f"https://{hote}/v2/usage", {"Authorization": f"DeepL-Auth-Key {cle}"})
    limite = _n(d["character_limit"])
    if limite >= ILLIMITE_DEEPL:
        return {"illimite": True, "unite": "caractères"}
    return {"reste": max(0, limite - _n(d["character_count"])), "unite": "caractères"}


def _kiri(cle, ouvrir):
    d = ouvrir("https://api.kiriengine.app/api/v1/open/balance", {"Authorization": f"Bearer {cle}"})
    if d.get("ok") is False or d.get("code") not in (0, None):
        raise ValueError("refus")
    return {"reste": _n(d["data"]["balance"]), "unite": "crédits"}


_LECTEURS = {"elevenlabs": _elevenlabs, "bfl": _bfl, "stability": _stability, "leonardo": _leonardo,
             "meshy": _meshy, "removebg": _removebg, "deepl": _deepl, "kiri": _kiri}
LECTEURS = frozenset(_LECTEURS)


def lire(lecteur, cle, ouvrir=None):
    """{"reste"?, "unite"?, "illimite"?, "abonnement"?} ou None (lecteur inconnu, pas de clé, toute erreur)."""
    if lecteur not in _LECTEURS or not isinstance(cle, str) or not cle:
        return None
    try:
        return _LECTEURS[lecteur](cle, ouvrir or _ouvrir)
    except Exception:   # noqa: BLE001 — une lecture ratée n'est jamais une erreur pour la factory
        return None
