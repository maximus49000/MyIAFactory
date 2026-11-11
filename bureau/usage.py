"""L'historique des usages : ce que le projet a consommé, gardé par le bureau.

Le relevé ne porte que les usages récents. Le bureau les range ici, dédoublonnés par `id`,
pour qu'un usage enregistré ne disparaisse pas quand le projet le retire du relevé.

Un `id` porte des compteurs cumulés : on garde les derniers vus. En revanche la date de prix
(`t_prix`, le `t` de la première apparition) et le service (celui de l'agent à ce moment-là)
sont figés : un coût passé ne bouge ni quand un prix change, ni quand un agent change de service.
"""
import json
import os
import threading
from pathlib import Path

COMPTEURS = ("entree", "sortie", "cache_lecture", "cache_ecriture")
TEXTES = ("tache", "agent", "service", "modele", "etape", "lot", "reparti")
FACULTATIFS = ("lot", "reparti")   # absents quand le relevé n'en porte pas
CHAMPS = ("id", "tache", "agent", "service", "modele", "etape", "lot", "reparti", "t", "t_prix") + COMPTEURS
# Une ligne d'usage d'un partenaire (voix, images…) : sa quantité, son coût d'origine (ou null : non chiffré).
CHAMPS_PARTENAIRE = ("id", "genre", "partenaire", "tache", "agent", "service", "quantite", "unite", "cout", "devise",
                     "estime", "t", "t_prix")


def _entier_positif(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _nombre(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and 0 <= v < float("inf")


def _ligne_partenaire_valide(d):
    return (isinstance(d, dict) and d.get("genre") == "partenaire" and isinstance(d.get("id"), str) and d["id"]
            and isinstance(d.get("partenaire"), str) and d["partenaire"] and _nombre(d.get("quantite"))
            and isinstance(d.get("unite"), str) and isinstance(d.get("t"), str) and isinstance(d.get("t_prix"), str)
            and (d.get("cout") is None or (_nombre(d["cout"]) and isinstance(d.get("devise"), str)))
            and isinstance(d.get("estime"), bool)
            and all(d.get(c) is None or isinstance(d.get(c), str) for c in ("tache", "agent", "service")))


def _ligne_valide(d):
    if isinstance(d, dict) and d.get("genre") is not None:
        return _ligne_partenaire_valide(d)
    return (isinstance(d, dict) and isinstance(d.get("id"), str) and d["id"]
            and isinstance(d.get("modele"), str) and d["modele"]
            and isinstance(d.get("t"), str) and isinstance(d.get("t_prix"), str)
            and all(_entier_positif(d.get(c)) for c in COMPTEURS)
            and all(d.get(c) is None or isinstance(d.get(c), str) for c in TEXTES))


def _service_de(r, agent):
    """Service de l'agent dans ce relevé ; None pour le chef, un agent inconnu ou absent."""
    for t in r.get("titulaires") or []:
        if t.get("cle") == agent:
            return None if t.get("chef") else t.get("service")
    return None


class HistoriqueUsage:
    def __init__(self, chemin):
        self.chemin = Path(chemin)
        self._verrou = threading.Lock()

    def _lignes(self):
        """{id: ligne} dans l'ordre du fichier ; les lignes illisibles sont ignorées."""
        try:
            texte = self.chemin.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        lignes = {}
        for brut in texte.splitlines():
            try:
                d = json.loads(brut)
            except ValueError:
                continue
            if _ligne_valide(d) and d.get("genre") == "partenaire":
                lignes[d["id"]] = {c: d.get(c) for c in CHAMPS_PARTENAIRE}
            elif _ligne_valide(d):
                lignes[d["id"]] = {c: d.get(c) for c in CHAMPS if c not in FACULTATIFS or d.get(c) is not None}
        return lignes

    def lire(self):
        with self._verrou:
            return list(self._lignes().values())

    def integrer(self, r):
        """Ajoute ou met à jour les usages du relevé normalisé `r`. Rien n'est jamais supprimé."""
        usages = r.get("usage") if isinstance(r, dict) else None
        if not isinstance(usages, list) or not usages:
            return
        with self._verrou:
            lignes = self._lignes()
            change = False
            for u in usages:
                if not isinstance(u, dict) or not isinstance(u.get("id"), str):
                    continue
                ancienne = lignes.get(u["id"])
                if u.get("genre") == "partenaire":
                    nouvelle = {c: u.get(c) for c in CHAMPS_PARTENAIRE}
                    nouvelle["service"] = ancienne["service"] if ancienne else _service_de(r, u.get("agent"))
                    nouvelle["t_prix"] = ancienne["t_prix"] if ancienne else u.get("t")   # le taux du jour, figé
                    nouvelle["estime"] = u.get("estime") is True
                    if _ligne_valide(nouvelle) and nouvelle != ancienne:
                        lignes[u["id"]] = nouvelle
                        change = True
                    continue
                nouvelle = {
                    "id": u["id"], "tache": u.get("tache"), "agent": u.get("agent"),
                    "service": ancienne["service"] if ancienne else _service_de(r, u.get("agent")),
                    "modele": u.get("modele"), "etape": u.get("etape"), "t": u.get("t"),
                    "t_prix": ancienne["t_prix"] if ancienne else u.get("t"),
                }
                nouvelle.update({c: u[c] for c in FACULTATIFS if u.get(c) is not None})
                for c in COMPTEURS:
                    nouvelle[c] = u.get(c) or 0
                if not _ligne_valide(nouvelle):
                    continue
                if nouvelle != ancienne:
                    lignes[u["id"]] = nouvelle
                    change = True
            if change:
                self._ecrire(lignes.values())

    def _ecrire(self, lignes):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.chemin.with_name(self.chemin.name + ".tmp")
        tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes), encoding="utf-8")
        os.replace(tmp, self.chemin)
