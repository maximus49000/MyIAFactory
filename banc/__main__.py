"""py -3.12 -m banc construire|reference|moteur|agent-seul|rapport … — le banc d'essai.

Les sorties vont sous `~/MyIAFactory/bancs/<nom>/` (jamais dans le dépôt). `moteur` et `agent-seul` appellent
vraiment `claude -p` : ils coûtent (le premier seulement ses appels de jugement, le second tout un passage). Rien ne
les lance d'office."""
import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from banc import agent_seul, construire, jouer, mesures, rapport, reference, scenario
from bureau import prix
from moteur import appel

BANCS = "~/MyIAFactory/bancs"
PRIX = "~/MyIAFactory/prix-historique.jsonl"


def dossier_du_banc(nom, racine=None):
    if not isinstance(nom, str) or not nom or not all(c.isalnum() or c in "-_" for c in nom):
        raise construire.ErreurBanc("Le nom d'un banc : lettres, chiffres, - et _.")
    d = Path(racine or BANCS).expanduser() / nom
    construire.refuser_dans_le_depot(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def prix_de(fichier):
    """`prix_de(modele, date)` d'après la table de prix du bureau, ou `None` si elle est vide ou absente."""
    table = prix.TablePrix(Path(fichier or PRIX).expanduser())
    if not table.etat():
        return None
    return lambda modele, date_iso: prix.prix_effectif(table, {}, modele, date_iso)


def _ecrire(chemin, objet):
    Path(chemin).write_text(json.dumps(objet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return chemin


def _lire(chemin):
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def cmd_construire(a):
    d = dossier_du_banc(a.nom, a.bancs)
    return construire.construire(Path(a.factory), Path(a.transcriptions), d / "scenario.json")


def cmd_reference(a):
    d = dossier_du_banc(a.nom, a.bancs)
    r = reference.reference(Path(a.transcription), prix_de(a.prix), date.today().isoformat())
    return _ecrire(d / "reference.json", r)


def cmd_moteur(a):
    d = dossier_du_banc(a.nom, a.bancs)
    s = scenario.charger(d / "scenario.json")
    with tempfile.TemporaryDirectory(prefix="banc-moteur-") as t:
        r = jouer.jouer_moteur(s, t, appel.appeler, couche=a.couche)
    p = prix_de(a.prix)
    _ecrire(d / "moteur-brut.json", {k: r[k] for k in ("tours", "appels", "usages_jugement", "usages_production",
                                                       "ecarts", "journal", "gestes_restants", "demandes_en_attente")})
    return _ecrire(d / "moteur.json", mesures.mesure_moteur(r, s, p, date.today().isoformat()))


def cmd_agent_seul(a):
    d = dossier_du_banc(a.nom, a.bancs)
    s = scenario.charger(d / "scenario.json")
    with tempfile.TemporaryDirectory(prefix="banc-agent-seul-") as t:
        r = agent_seul.agent_seul(s, t, couche=a.couche)
    _ecrire(d / "agent-seul-brut.json", r)
    return _ecrire(d / "agent-seul.json", mesures.mesure_agent_seul(r, s, prix_de(a.prix), date.today().isoformat()))


def cmd_rapport(a):
    d = dossier_du_banc(a.nom, a.bancs)
    s = scenario.charger(d / "scenario.json")
    p, jour = prix_de(a.prix), date.today().isoformat()
    resultats = {}
    if (d / "moteur.json").is_file():
        resultats["moteur"] = _lire(d / "moteur.json")
    if (d / "reference.json").is_file():
        resultats["orchestrateur_actuel"] = mesures.mesure_orchestrateur_actuel(_lire(d / "reference.json"), s, p, jour)
    if (d / "agent-seul.json").is_file():
        resultats["agent_seul"] = _lire(d / "agent-seul.json")
    chemin = d / "rapport.md"
    chemin.write_text(rapport.rapport(resultats, s.attendu), encoding="utf-8")
    return chemin


def _analyseur():
    p = argparse.ArgumentParser(prog="banc", description="Le banc d'essai de l'orchestrateur procédural.")
    s = p.add_subparsers(dest="commande", required=True)

    def commun(x, **plus):
        x.add_argument("--nom", required=True, help="le nom du banc (dossier sous ~/MyIAFactory/bancs/)")
        x.add_argument("--bancs", help=f"le dossier des bancs (défaut : {BANCS})")
        x.add_argument("--prix", help=f"la table de prix du bureau (défaut : {PRIX})")
        return x

    x = commun(s.add_parser("construire", help="le scénario d'un essai réel"))
    x.add_argument("--factory", required=True, help="le dossier du fichier de factory de l'essai (.factory/)")
    x.add_argument("--transcriptions", required=True, help="le dossier des transcriptions de la session orchestratrice")
    x.set_defaults(f=cmd_construire)
    x = commun(s.add_parser("reference", help="la mesure de l'orchestrateur actuel, lue dans sa transcription"))
    x.add_argument("--transcription", required=True, help="le fichier .jsonl de la conversation orchestratrice")
    x.set_defaults(f=cmd_reference)
    x = commun(s.add_parser("moteur", help="le moteur sur le scénario (ses appels de jugement sont réels et payés)"))
    x.add_argument("--couche", choices=("claude", "api"), default="claude")
    x.set_defaults(f=cmd_moteur)
    x = commun(s.add_parser("agent-seul", help="un agent seul sur le scénario (passage complet, payé)"))
    x.add_argument("--couche", choices=("claude", "api"), default="claude")
    x.set_defaults(f=cmd_agent_seul)
    x = commun(s.add_parser("rapport", help="le rapport comparé, en Markdown"))
    x.set_defaults(f=cmd_rapport)
    return p


def main(argv=None):
    a = _analyseur().parse_args(argv)
    try:
        sortie = a.f(a)
    except (construire.ErreurBanc, scenario.ScenarioInvalide) as e:
        print(f"Refusé : {e}", file=sys.stderr)
        return 1
    print(sortie)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
