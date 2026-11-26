"""Rejoue le banc avec le VRAI jugement (`moteur.jugement.juger("decider_autonome", …)`, l'appel d'IA du moteur) :

    py -3.12 -m tests.banc_autonome                 # tous les cas
    py -3.12 -m tests.banc_autonome --cas recette   # les cas dont l'id contient ce texte
    py -3.12 -m tests.banc_autonome --modele opus   # un autre modèle que celui du moteur (jamais Fable)
    py -3.12 -m tests.banc_autonome --simule        # sans appel : les réponses simulées des cas (essai de la commande)

Imprime, par cas, attendu / obtenu / juste ou faux, puis le score. Coût : un appel d'IA par cas de jugement (au plus deux
si la première réponse est invalide) ; les cas « hors jugement » et « règle du moteur » ne coûtent rien. Un cas dont
l'appel échoue est compté faux (jamais ignoré). Code de sortie : 0 si tout est juste, 1 sinon, 2 si l'appel est impossible
(le programme `claude` est introuvable : rien n'est mesuré, aucun score n'est inventé).
"""
import argparse
import sys

from moteur import appel, jugement
from tests import banc_autonome as banc


def _vrai_jugement(modele, couche):
    def juger(dossier):
        d = jugement.juger("decider_autonome", dossier, couche=couche, modele=modele)
        if d.objet is None:
            raise RuntimeError(f"jugement sans réponse valable : {d.question}")
        return d.objet
    return juger


def principal(argv=None):
    p = argparse.ArgumentParser(prog="py -3.12 -m tests.banc_autonome")
    p.add_argument("--cas", default="", help="ne rejouer que les cas dont l'id contient ce texte")
    p.add_argument("--modele", default=None, help="modèle du jugement (défaut : celui du moteur ; jamais Fable)")
    p.add_argument("--couche", default="claude", choices=("claude", "api"))
    p.add_argument("--simule", action="store_true", help="sans appel : rejoue les réponses simulées des cas")
    a = p.parse_args(argv)
    cas = [c for c in banc.charger() if a.cas in c["id"]]
    if not cas:
        print("Aucun cas ne correspond.")
        return 2
    if a.simule:
        def juger_cas(c):
            return banc.rejouer(c, lambda _d, c=c: c["simule"])
    else:
        if a.couche == "claude" and appel.trouver_claude() is None:
            print("Le programme `claude` est introuvable : le vrai jugement ne peut pas être appelé d'ici. Rien n'est mesuré.")
            return 2
        juger = _vrai_jugement(a.modele, a.couche)

        def juger_cas(c):
            return banc.rejouer(c, juger)
    resultats = []
    for c in cas:
        r = juger_cas(c)
        resultats.append(r)
        print(f"{'JUSTE' if r['juste'] else 'FAUX '}  {r['id']}\n       attendu : {r['attendu']}\n       obtenu  : {r['obtenu']}")
        for d in r["defauts"]:
            print(f"       défaut  : {d}")
    justes, total = banc.score(resultats)
    print(f"\nScore : {justes}/{total}" + (" (réponses simulées : ce n'est pas une mesure du jugement)" if a.simule else ""))
    return 0 if justes == total else 1


if __name__ == "__main__":
    sys.exit(principal())
