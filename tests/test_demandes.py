import base64
import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bureau import demandes, releve

R = releve.normaliser({
    "version": 2, "projet": "P", "factory": {"etat": "en marche"},
    "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}, {"id": "b", "nom": "B"}],
    "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
    "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}],
    "file": {"visibles": [{"id": "q1", "titre": "Q"}], "suite": [{"id": "q2", "titre": "Q2"}], "reste": 5},
    "actions": [{"id": "pause", "libelle": "Pause"},
                {"id": "doc", "libelle": "Doc", "lien": "https://exemple.org"},
                {"id": "gris", "libelle": "G", "actif": False}],
    "lecons": [{"id": "d1:L1", "agent": "d1", "texte": "t"}]})


class TestVerifier(unittest.TestCase):
    def ok(self, d):
        self.assertIsNone(demandes.verifier(d, R), d)

    def refus(self, d):
        m = demandes.verifier(d, R)
        self.assertTrue(m, d)
        return m

    def test_acceptees(self):
        self.ok({"type": "bouton", "id": "pause"})
        self.ok({"type": "deplacer", "tache": "t1", "colonne": "b"})
        self.ok({"type": "deplacer", "tache": "q1", "colonne": "a"})
        self.ok({"type": "deplacer", "tache": "q2", "colonne": "b"})  # un élément de la suite
        self.ok({"type": "retour", "tache": "t1", "texte": "bien"})
        self.ok({"type": "retour", "tache": "t1", "texte": "x" * 3500})
        self.ok({"type": "lecon", "id": "d1:L1", "verdict": "valider"})
        self.ok({"type": "lecon", "id": "d1:L1", "verdict": "invalider"})

    def test_refusees(self):
        for d in (None, [], "x", {}, {"type": "autre"},
                  {"type": "bouton", "id": "inconnu"}, {"type": "bouton"},
                  {"type": "bouton", "id": "doc"},  # un lien n'est pas une demande
                  {"type": "bouton", "id": "gris"},  # grisé
                  {"type": "bouton", "id": 3},
                  {"type": "deplacer", "tache": "zz", "colonne": "a"},
                  {"type": "deplacer", "tache": "t1", "colonne": "zz"},
                  {"type": "deplacer", "tache": "t1"},
                  {"type": "deplacer", "tache": "q3", "colonne": "a"},  # dans le « reste », ni visible ni dans la suite
                  {"type": "retour", "tache": "zz", "texte": "x"},
                  {"type": "retour", "tache": "t1", "texte": "   \n"},
                  {"type": "retour", "tache": "t1", "texte": 3},
                  {"type": "retour", "tache": "t1", "texte": "x" * 3501},
                  {"type": "lecon", "id": "inconnue", "verdict": "valider"},
                  {"type": "lecon", "id": "d1:L1", "verdict": "peut-être"},
                  {"type": "lecon", "id": "d1:L1"}):
            self.refus(d)

    def test_version_1_sans_actions(self):
        r1 = releve.normaliser({k: v for k, v in R.items() if k not in ("actions", "lecons")} | {"version": 1})
        self.assertTrue(demandes.verifier({"type": "bouton", "id": "pause"}, r1))

    def test_nettoyer_ne_garde_que_les_champs_connus(self):
        d = demandes.nettoyer({"type": "retour", "tache": "t1", "texte": "x", "t": "faux", "autre": 1})
        self.assertEqual(d, {"type": "retour", "tache": "t1", "texte": "x"})


R3 = releve.normaliser({
    "version": 3, "projet": "P", "factory": {"etat": "en marche"},
    "services": [{"id": "dev", "nom": "Dev", "kpi": [{"id": "defauts", "nom": "Défauts", "valeur": 2}]}],
    "colonnes": [{"id": "a", "nom": "A"}],
    "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local",
                    "connaissances": [{"id": "k1", "texte": "a"}, {"id": "k2", "texte": "b"}],
                    "lecons": [{"id": "l1", "texte": "c", "etat": "validée"},
                               {"id": "l2", "texte": "d", "etat": "à valider"}]}],
    "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}],
    "challenges": [{"id": "ch1", "cible": {"type": "connaissance", "id": "k2"}, "texte": "c",
                    "solutions": [{"id": "s1", "texte": "x", "auteur": "directeur"}]}]})

SOURCE = "source:dev:tache_chere:t1"


class TestVerifierChallenges(unittest.TestCase):
    def ok(self, d, cibles=frozenset()):
        self.assertIsNone(demandes.verifier(d, R3, cibles), d)

    def refus(self, d, cibles=frozenset(), r=R3):
        m = demandes.verifier(d, r, cibles)
        self.assertTrue(m, d)
        return m

    def test_challenge_accepte(self):
        self.ok({"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}})
        self.ok({"type": "challenge", "cible": {"type": "connaissance", "id": "l1"}, "texte": "pourquoi",
                 "solution": "faire autrement"})
        self.ok({"type": "challenge", "cible": {"type": "kpi", "id": "kpi:dev:defauts"}})
        self.ok({"type": "challenge", "cible": {"type": "kpi", "id": "kpi:dev:cout_moyen"}},
                {"kpi:dev:cout_moyen": "constat"})
        self.ok({"type": "challenge", "cible": {"type": "source", "id": SOURCE}}, {SOURCE: "constat"})

    def test_challenge_cible_absente(self):
        for cible in ({"type": "connaissance", "id": "k9"}, {"type": "connaissance", "id": "l2"},
                      {"type": "kpi", "id": "kpi:dev:inconnu"}, {"type": "kpi", "id": "defauts"},
                      {"type": "source", "id": SOURCE}, {"type": "source", "id": "k1"}):
            self.refus({"type": "challenge", "cible": cible})

    def test_challenge_d_une_lecon(self):
        # Version 4 : une leçon, même encore « à valider », peut être challengée (cible « lecon »).
        r4 = copy.deepcopy(R3)
        r4["version"] = 4
        r4 = releve.normaliser(r4)
        r4["lecons"] = [{"id": "d1:L7", "agent": "d1", "texte": "T", "etage_propose": "projet"}]
        self.assertIsNone(demandes.verifier({"type": "challenge", "cible": {"type": "lecon", "id": "d1:L7"},
                                             "texte": "Pourquoi ?"}, r4), "leçon à valider")
        self.refus({"type": "challenge", "cible": {"type": "lecon", "id": "d1:L9"}, "texte": "x"}, r=r4)
        self.refus({"type": "challenge", "cible": {"type": "lecon", "id": "d1:L7"}})          # en version 3
        self.refus({"type": "challenge", "cible": {"type": "lecon", "id": "d1:L7"}}, r=r4)    # sans texte

    def test_challenge_mal_forme(self):
        for d in ({"type": "challenge"}, {"type": "challenge", "cible": "k1"},
                  {"type": "challenge", "cible": {"type": "tache", "id": "t1"}},
                  {"type": "challenge", "cible": {"type": "connaissance", "id": 3}},
                  {"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}, "texte": 3},
                  {"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}, "solution": "  "},
                  {"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}, "solution": "x" * 3501},
                  {"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}, "texte": "x" * 3501}):
            self.refus(d)

    def test_challenge_deja_ouvert(self):
        m = self.refus({"type": "challenge", "cible": {"type": "connaissance", "id": "k2"}})
        self.assertIn("existe déjà", m)

    def test_solution(self):
        self.ok({"type": "solution", "challenge": "ch1", "texte": "x" * 3500})
        for d in ({"type": "solution", "challenge": "ch9", "texte": "x"},
                  {"type": "solution", "challenge": "ch1", "texte": " \n"},
                  {"type": "solution", "challenge": "ch1", "texte": "x" * 3501},
                  {"type": "solution", "challenge": "ch1"}):
            self.refus(d)

    def test_verdict_solution(self):
        self.ok({"type": "verdict_solution", "challenge": "ch1", "solution": "s1", "verdict": "valider"})
        self.ok({"type": "verdict_solution", "challenge": "ch1", "solution": "s1", "verdict": "ecarter"})
        for d in ({"type": "verdict_solution", "challenge": "ch9", "solution": "s1", "verdict": "valider"},
                  {"type": "verdict_solution", "challenge": "ch1", "solution": "s9", "verdict": "valider"},
                  {"type": "verdict_solution", "challenge": "ch1", "solution": "s1", "verdict": "invalider"},
                  {"type": "verdict_solution", "challenge": "ch1", "solution": "s1"}):
            self.refus(d)

    def test_version_2_refuse(self):
        # Les challenges n'existent qu'en version 3.
        self.refus({"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}}, r=R)
        self.refus({"type": "solution", "challenge": "ch1", "texte": "x"}, r=R)

    def test_nettoyer_challenge(self):
        d = demandes.nettoyer({"type": "challenge", "cible": {"type": "kpi", "id": "x", "autre": 1},
                               "texte": "a", "solution": "b", "pirate": 1})
        self.assertEqual(d, {"type": "challenge", "cible": {"type": "kpi", "id": "x"}, "texte": "a", "solution": "b"})
        self.assertEqual(demandes.nettoyer({"type": "challenge", "cible": {"type": "kpi", "id": "x"}}),
                         {"type": "challenge", "cible": {"type": "kpi", "id": "x"}})


class TestEnvoyer(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.sortie = self.tmp / "sortie.jsonl"

    def regl(self, code, extra=None):
        return {"dossier": str(self.tmp), "actions": {"commande": [sys.executable, "-c", code] + (extra or []),
                                                      "dossier": "."}}

    def test_recopie_la_demande_en_json_utf8(self):
        code = ("import sys; open(sys.argv[1],'ab').write(sys.stdin.buffer.read()+b'\\n')")
        regl = self.regl(code, [str(self.sortie)])
        self.assertEqual(demandes.envoyer(regl, {"type": "retour", "tache": "t1", "texte": "é — ü"}), (True, ""))
        ligne = json.loads(self.sortie.read_bytes().decode("utf-8"))
        self.assertEqual((ligne["type"], ligne["texte"]), ("retour", "é — ü"))
        self.assertRegex(ligne["t"], r"^\d{4}-\d\d-\d\dT")

    def test_echec_avec_message(self):
        regl = self.regl("import sys; sys.stdin.read(); print('non'); sys.exit(3)")
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}), (False, "non"))

    def test_echec_message_des_erreurs(self):
        regl = self.regl("import sys; sys.stderr.write('oups\\nsuite'); sys.exit(1)")
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}), (False, "oups"))

    def test_echec_sans_message(self):
        regl = self.regl("import sys; sys.exit(2)")
        ok, m = demandes.envoyer(regl, {"type": "bouton", "id": "x"})
        self.assertFalse(ok)
        self.assertIn("2", m)

    def test_depassement(self):
        ancien = releve.DELAI_COMMANDE_S
        releve.DELAI_COMMANDE_S = 1
        self.addCleanup(setattr, releve, "DELAI_COMMANDE_S", ancien)
        regl = self.regl("import time; time.sleep(15)")
        debut = time.monotonic()
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}),
                         (False, "La commande d'actions a dépassé 1 s."))
        self.assertLess(time.monotonic() - debut, 10)

    def test_grosse_demande_a_une_commande_qui_ne_lit_pas(self):
        ancien = releve.DELAI_COMMANDE_S
        releve.DELAI_COMMANDE_S = 1
        self.addCleanup(setattr, releve, "DELAI_COMMANDE_S", ancien)
        regl = self.regl("import time; time.sleep(30)")
        debut = time.monotonic()
        ok, m = demandes.envoyer(regl, {"type": "retour", "tache": "t1", "texte": "é" * 3500})
        self.assertFalse(ok)
        self.assertIn("dépassé", m)
        self.assertLess(time.monotonic() - debut, 8)

    def test_sans_commande(self):
        for regl in ({"dossier": str(self.tmp)}, {"dossier": str(self.tmp), "actions": {}},
                     {"dossier": str(self.tmp), "actions": {"commande": "python x.py"}}):
            self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}),
                             (False, "Aucune commande d'actions dans les réglages."))

    def test_commande_introuvable(self):
        regl = {"dossier": str(self.tmp), "actions": {"commande": ["commande-qui-n-existe-pas"]}}
        ok, m = demandes.envoyer(regl, {"type": "bouton", "id": "x"})
        self.assertFalse(ok)
        self.assertTrue(m)

    def test_commande_qui_ferme_son_entree(self):
        # n'écrit pas dans le tube (ne lit pas l'entrée) : pas d'erreur côté bureau
        regl = self.regl("pass")
        self.assertEqual(demandes.envoyer(regl, {"type": "bouton", "id": "x"}), (True, ""))


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16


def image(nom="a.png", contenu=PNG, type_="image/png", donnees=None):
    return {"nom": nom, "type": type_,
            "donnees": donnees if donnees is not None else base64.b64encode(contenu).decode("ascii")}


R4 = releve.normaliser({
    "version": 4, "projet": "P", "factory": {"etat": "en marche"},
    "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}],
    "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
    "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}],
    "fonctionnalites": [
        {"id": "f1", "nom": "Cahier", "etape": "cahier",
         "decisions": [{"id": "dc", "genre": "valider_cahier", "texte": "Valider ?"}]},
        {"id": "f2", "nom": "Méthode", "etape": "methode",
         "decisions": [{"id": "dm", "genre": "valider_methode", "texte": "Valider ?"}]},
        {"id": "f3", "nom": "À revoir", "etape": "cadrage",
         "decisions": [{"id": "dr", "genre": "methode_a_revoir", "texte": "À revoir ?"}]},
        {"id": "f4", "nom": "Série", "etape": "serie", "catalogue": True},
        {"id": "f5", "nom": "Simple", "etape": "cadrage"},
        {"id": "f6", "nom": "Comme une autre", "etape": "decoupage",
         "decisions": [{"id": "dp", "genre": "reprendre_methode", "texte": "Reprendre la méthode de « Badges » ?"}]}],
    "decisions_projet": [
        {"id": "g1", "genre": "confirmer_genre", "texte": "Genre ?", "propose": "ville",
         "genres_connus": ["ville"]},
        {"id": "s1", "genre": "session_cloud", "texte": "Session ?", "agent": "d1"},
        {"id": "s2", "genre": "session_cloud", "texte": "Session ?", "agent": "d1", "tache": "t1",
         "depart": "Tu repars de zéro.", "lien": "https://claude.ai/code"},
        {"id": "o1", "genre": "organisation", "texte": "Organisation ?",
         "organisation": {"services": [{"id": "dev", "nom": "Dev"}], "flux": [], "agents": [], "briefs": {},
                          "cout": {"tokens": [1, 2], "euros": None}}}],
    "lecons": [{"id": "l1", "agent": "d1", "texte": "t"},
               {"id": "l2", "agent": "d1", "texte": "t", "etage_propose": "genre", "texte_general": "G"},
               {"id": "l3", "agent": "d1", "texte": "t", "etage_propose": "projet"}]})


class TestVerifierV4(unittest.TestCase):
    def ok(self, d, elements=None):
        self.assertIsNone(demandes.verifier(d, R4, frozenset(), elements), d)

    def refus(self, d, elements=None):
        m = demandes.verifier(d, R4, frozenset(), elements)
        self.assertTrue(m, d)
        return m

    def test_fonctionnalite(self):
        self.ok({"type": "fonctionnalite", "texte": "Une ville"})
        self.ok({"type": "fonctionnalite", "texte": "Une ville", "images": [image()]})
        for d in ({"type": "fonctionnalite"}, {"type": "fonctionnalite", "texte": "  "},
                  {"type": "fonctionnalite", "texte": 3}, {"type": "fonctionnalite", "texte": "x" * 3501}):
            self.refus(d)
        self.ok({"type": "fonctionnalite", "texte": "x" * 3500})

    def test_message(self):
        self.ok({"type": "message", "fonctionnalite": "f5", "texte": "Bonjour"})
        self.ok({"type": "message", "fonctionnalite": "f5", "texte": "Bonjour", "images": [image(), image("b.jpg", JPEG, "image/jpeg")]})
        self.refus({"type": "message", "fonctionnalite": "zz", "texte": "Bonjour"})
        self.refus({"type": "message", "fonctionnalite": "f5", "texte": ""})
        self.refus({"type": "message", "texte": "Bonjour"})

    def test_cahier(self):
        self.ok({"type": "cahier", "fonctionnalite": "f1", "verdict": "valider"})
        self.ok({"type": "cahier", "fonctionnalite": "f1", "verdict": "corriger", "texte": "Plus grand"})
        self.refus({"type": "cahier", "fonctionnalite": "f5", "verdict": "valider"})  # pas de décision
        self.refus({"type": "cahier", "fonctionnalite": "f1", "verdict": "corriger"})
        self.refus({"type": "cahier", "fonctionnalite": "f1", "verdict": "corriger", "texte": " "})
        self.refus({"type": "cahier", "fonctionnalite": "f1", "verdict": "peut-être"})
        self.refus({"type": "cahier", "fonctionnalite": "zz", "verdict": "valider"})
        self.refus({"type": "cahier", "fonctionnalite": "f1", "verdict": "valider", "texte": "x" * 3501})

    def test_methode(self):
        self.ok({"type": "methode", "fonctionnalite": "f2", "verdict": "valider"})
        self.refus({"type": "methode", "fonctionnalite": "f1", "verdict": "valider"})
        self.ok({"type": "methode", "fonctionnalite": "f3", "verdict": "garder"})
        self.refus({"type": "methode", "fonctionnalite": "f2", "verdict": "garder"})
        self.ok({"type": "methode", "fonctionnalite": "f2", "verdict": "revoir"})  # étape « methode »
        self.ok({"type": "methode", "fonctionnalite": "f4", "verdict": "revoir", "texte": "Mieux"})  # « serie »
        self.ok({"type": "methode", "fonctionnalite": "f3", "verdict": "revoir"})  # décision « à revoir »
        self.refus({"type": "methode", "fonctionnalite": "f5", "verdict": "revoir"})
        self.refus({"type": "methode", "fonctionnalite": "f2", "verdict": "autre"})

    def test_reprendre_une_methode(self):
        # Essai réel : une fonctionnalité qui ressemble à une méthode déjà validée peut partir en série sans
        # prototype : oui (reprendre), modifier le mode opératoire (adapter + texte) ou relancer le prototype (revoir).
        self.ok({"type": "methode", "fonctionnalite": "f6", "verdict": "reprendre"})
        self.ok({"type": "methode", "fonctionnalite": "f6", "verdict": "adapter", "texte": "Bordure plus fine"})
        self.refus({"type": "methode", "fonctionnalite": "f6", "verdict": "adapter"})   # sans ce qui change
        self.ok({"type": "methode", "fonctionnalite": "f6", "verdict": "revoir"})
        for f in ("f2", "f5"):   # sans la question « reprendre ? »
            self.refus({"type": "methode", "fonctionnalite": f, "verdict": "reprendre"})
            self.refus({"type": "methode", "fonctionnalite": f, "verdict": "adapter", "texte": "x"})

    def test_genre(self):
        self.ok({"type": "genre", "decision": "g1", "genre": "ville"})
        self.ok({"type": "genre", "decision": "g1", "genre": "jeu", "description": "Un jeu"})
        self.refus({"type": "genre", "decision": "g1", "genre": "jeu"})  # nouveau sans description
        self.refus({"type": "genre", "decision": "g1", "genre": "jeu", "description": " "})
        self.refus({"type": "genre", "decision": "g1", "genre": "../x", "description": "d"})
        self.refus({"type": "genre", "decision": "g1", "genre": "Ville"})
        self.refus({"type": "genre", "decision": "inconnue", "genre": "ville"})
        self.refus({"type": "genre", "decision": "s1", "genre": "ville"})  # pas une décision de genre

    def test_session_cloud(self):
        self.ok({"type": "session_cloud", "decision": "s1", "session": "Ma session"})
        self.refus({"type": "session_cloud", "decision": "s1", "session": " "})
        self.refus({"type": "session_cloud", "decision": "s1", "session": "x" * 201})
        self.ok({"type": "session_cloud", "decision": "s1", "session": "x" * 200})
        self.refus({"type": "session_cloud", "decision": "g1", "session": "S"})
        self.refus({"type": "session_cloud", "decision": "zz", "session": "S"})

    def test_session_cloud_creee_a_la_main(self):
        # La démarche simplifiée : l'adresse claude.ai/code ou l'identifiant de la session, rien d'autre.
        for bon in ("https://claude.ai/code/session_01AbC", " session_01AbC ",
                    "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b", "https://claude.ai/code/session_01AbC?tab=1"):
            self.ok({"type": "session_cloud", "decision": "s2", "session": bon})
        for mauvais in ("Ma session", "https://example.com/code/session_1", "https://claude.ai/code/", "session_"):
            self.assertIn("claude.ai/code", self.refus({"type": "session_cloud", "decision": "s2", "session": mauvais}))

    def test_retour_element(self):
        d = {"type": "retour_element", "fonctionnalite": "f4", "element": "e1", "texte": "Plus haut"}
        self.ok(d, {"e1", "e2"})
        self.assertEqual(self.refus(d, None), "Catalogue indisponible.")
        self.refus({**d, "element": "e9"}, {"e1"})
        self.refus({**d, "texte": " "}, {"e1"})
        self.refus({**d, "fonctionnalite": "f5"}, {"e1"})  # sans catalogue
        self.refus({**d, "fonctionnalite": "zz"}, {"e1"})

    def test_demande_organisation(self):
        self.ok({"type": "organisation", "decision": "o1", "verdict": "accepter"})
        self.ok({"type": "organisation", "decision": "o1", "verdict": "refuser"})
        self.refus({"type": "organisation", "decision": "g1", "verdict": "accepter"})   # une autre décision
        self.refus({"type": "organisation", "decision": "zz", "verdict": "accepter"})

    def test_demande_organisation_verdict_inconnu(self):
        self.refus({"type": "organisation", "decision": "o1", "verdict": "peut-etre"})
        self.refus({"type": "organisation", "decision": "o1"})

    def test_lecon_etage(self):
        self.ok({"type": "lecon", "id": "l2", "verdict": "valider", "etage": "genre"})
        self.ok({"type": "lecon", "id": "l2", "verdict": "valider", "etage": "skill"})
        self.ok({"type": "lecon", "id": "l1", "verdict": "valider", "etage": "projet"})
        self.refus({"type": "lecon", "id": "l1", "verdict": "valider", "etage": "genre"})  # sans texte_general
        self.refus({"type": "lecon", "id": "l3", "verdict": "valider", "etage": "skill"})
        self.refus({"type": "lecon", "id": "l1", "verdict": "valider", "etage": "monde"})
        self.ok({"type": "lecon", "id": "l1", "verdict": "valider"})

    def test_demandes_v4_refusees_en_v3(self):
        r3 = releve.normaliser({**{k: v for k, v in R4.items() if k not in ("fonctionnalites", "decisions_projet",
                                                                            "genre", "livrable")},
                                "version": 3})
        for d in ({"type": "fonctionnalite", "texte": "x"},
                  {"type": "message", "fonctionnalite": "f5", "texte": "x"},
                  {"type": "cahier", "fonctionnalite": "f1", "verdict": "valider"},
                  {"type": "methode", "fonctionnalite": "f2", "verdict": "valider"},
                  {"type": "genre", "decision": "g1", "genre": "ville"},
                  {"type": "session_cloud", "decision": "s1", "session": "S"},
                  {"type": "retour_element", "fonctionnalite": "f4", "element": "e", "texte": "x"},
                  {"type": "lecon", "id": "l1", "verdict": "valider", "etage": "projet"}):
            m = demandes.verifier(d, r3, frozenset(), {"e"})
            self.assertTrue(m, d)
            self.assertIn("version 4", m)
        self.assertIsNone(demandes.verifier({"type": "lecon", "id": "l1", "verdict": "valider"}, r3))

    def test_demande_organisation_v3_refusee(self):
        r3 = releve.normaliser({**{k: v for k, v in R4.items() if k not in ("fonctionnalites", "decisions_projet",
                                                                            "genre", "livrable")},
                                "version": 3})
        m = demandes.verifier({"type": "organisation", "decision": "o1", "verdict": "accepter"}, r3, frozenset())
        self.assertIn("version 4", m)

    def test_images_refusees(self):
        gros = image("gros.png", PNG + b"\x00" * (6 * 1024 * 1024))
        cas = {"cinq images": [image(f"a{i}.png") for i in range(5)],
               "6 Mo": [gros],
               "gif renommé png": [image("a.png", GIF)],
               "base64 invalide": [image(donnees="!!pas du base64!!")],
               "nom avec ..": [image("../x.png")],
               "nom avec /": [image("dossier/x.png")],
               "nom avec \\": [image("dossier\\x.png")],
               "nom trop long": [image("a" * 77 + ".png")],
               "extension gif": [image("a.gif")],
               "sans extension": [image("a")],
               "type gif": [image("a.png", type_="image/gif")],
               "type et extension incohérents": [image("a.jpg", PNG, "image/png")],
               "jpeg dont la signature est png": [image("a.jpg", PNG, "image/jpeg")],
               "vide": [image("a.png", b"")],
               "pas une liste": "x",
               "pas un objet": ["a.png"],
               "sans données": [{"nom": "a.png", "type": "image/png"}],
               "données non textuelles": [{"nom": "a.png", "type": "image/png", "donnees": 3}]}
        for nom, images in cas.items():
            self.assertTrue(demandes.verifier_images(images), nom)
            self.refus({"type": "fonctionnalite", "texte": "x", "images": images})
            self.refus({"type": "message", "fonctionnalite": "f5", "texte": "x", "images": images})

    def test_image_jpeg_acceptee(self):
        for nom in ("a.jpg", "a.JPEG", "photo.Jpg"):
            self.assertIsNone(demandes.verifier_images([image(nom, JPEG, "image/jpeg")]), nom)
        self.assertIsNone(demandes.verifier_images([image("A.PNG")]))
        self.assertIsNone(demandes.verifier_images([]))
        self.assertIsNone(demandes.verifier_images([image(f"a{i}.png") for i in range(4)]))
        juste = image("juste.png", PNG + b"\x00" * (5 * 1024 * 1024 - len(PNG)))
        self.assertIsNone(demandes.verifier_images([juste]))  # 5 Mo pile

    def test_nettoyer_v4(self):
        d = demandes.nettoyer({"type": "message", "fonctionnalite": "f5", "texte": "x", "mauvais": 1,
                               "images": [{**image(), "chemin": "/etc/passwd"}]})
        self.assertEqual(set(d), {"type", "fonctionnalite", "texte", "images"})
        self.assertEqual(set(d["images"][0]), {"nom", "type", "donnees"})
        d = demandes.nettoyer({"type": "cahier", "fonctionnalite": "f1", "verdict": "valider", "texte": "t", "x": 1})
        self.assertEqual(set(d), {"type", "fonctionnalite", "verdict", "texte"})
        d = demandes.nettoyer({"type": "genre", "decision": "g", "genre": "a", "description": "d", "x": 1})
        self.assertEqual(set(d), {"type", "decision", "genre", "description"})
        d = demandes.nettoyer({"type": "lecon", "id": "l", "verdict": "valider", "etage": "genre", "x": 1})
        self.assertEqual(set(d), {"type", "id", "verdict", "etage"})
        d = demandes.nettoyer({"type": "fonctionnalite", "texte": "x", "images": "pas une liste"})
        self.assertEqual(d["images"], "pas une liste")  # le contrôle le refusera



def releve_base_v4():
    return {"version": 4, "projet": "P", "factory": {"etat": "en marche"},
            "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}],
            "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
            "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}]}


class TestPartenairesDemandes(unittest.TestCase):
    def setUp(self):
        from tests.part_aide import partenaires_exemple
        self.r = releve.normaliser({**releve_base_v4(), "partenaires": partenaires_exemple()})

    def ok(self, d):
        self.assertIsNone(demandes.verifier(d, self.r), d)

    def refus(self, d):
        m = demandes.verifier(d, self.r)
        self.assertTrue(m, d)
        return m

    def test_regle(self):
        self.ok({"type": "partenaire_regle", "partenaire": "tripo", "operation": "ajouter", "texte": "Un seul prompt."})
        self.ok({"type": "partenaire_regle", "partenaire": "tripo", "operation": "modifier", "id": "r1", "texte": "Autre."})
        self.ok({"type": "partenaire_regle", "partenaire": "tripo", "operation": "supprimer", "id": "r1"})
        self.refus({"type": "partenaire_regle", "partenaire": "zz", "operation": "ajouter", "texte": "x"})
        self.refus({"type": "partenaire_regle", "partenaire": "tripo", "operation": "effacer", "id": "r1"})
        self.refus({"type": "partenaire_regle", "partenaire": "tripo", "operation": "supprimer", "id": "zz"})
        self.refus({"type": "partenaire_regle", "partenaire": "vox", "operation": "supprimer", "id": "r1"})
        self.refus({"type": "partenaire_regle", "partenaire": "tripo", "operation": "ajouter"})
        self.refus({"type": "partenaire_regle", "partenaire": "tripo", "operation": "ajouter", "texte": "  "})

    def test_demande_regle_texte_trop_long(self):
        base = {"type": "partenaire_regle", "partenaire": "tripo", "operation": "ajouter"}
        self.ok({**base, "texte": "x" * 500})
        self.assertIn("500", self.refus({**base, "texte": "x" * 501}))
        self.refus({**base, "texte": 12})

    def test_actualiser(self):
        self.ok({"type": "partenaires_actualiser"})

    def test_demande_maj_sans_confirmation_refusee(self):
        self.ok({"type": "partenaires_maj", "confirme": True})
        for d in ({"type": "partenaires_maj"}, {"type": "partenaires_maj", "confirme": False},
                  {"type": "partenaires_maj", "confirme": "true"}, {"type": "partenaires_maj", "confirme": 1}):
            self.refus(d)

    def test_sans_espace_partenaire_ou_avant_v4(self):
        sans = releve.normaliser(releve_base_v4())
        self.assertTrue(demandes.verifier({"type": "partenaires_actualiser"}, sans))
        v3 = releve.normaliser({**releve_base_v4(), "version": 3})
        self.assertTrue(demandes.verifier({"type": "partenaires_maj", "confirme": True}, v3))

    def test_inscrit(self):
        base = {"type": "partenaire_inscrit", "partenaire": "tripo"}
        self.ok({**base, "inscrit": True})
        self.ok({**base, "inscrit": False})
        self.ok({**base, "inscrit": True, "note": "compte gratuit, offre Pro"})
        self.refus({**base, "inscrit": "oui"})
        self.refus({**base})
        self.refus({**base, "partenaire": "zz", "inscrit": True})
        self.assertIn("mot de passe", self.refus({**base, "inscrit": True, "note": "mot de passe : abc"}))
        self.refus({**base, "inscrit": True, "note": "x" * 201})
        self.refus({**base, "inscrit": True, "note": 3})
        self.assertEqual(demandes.nettoyer({**base, "inscrit": True, "note": "n", "cle": "SECRET"}),
                         {**base, "inscrit": True, "note": "n"})
        self.r["partenaires"]["categories"]["video-3d-avatars"][0]["statut"] = "ferme"
        self.refus({**base, "inscrit": True})
        self.ok({**base, "inscrit": False})       # on peut toujours retirer son inscription

    def test_sans_espace_partenaire_pour_l_inscription(self):
        sans = releve.normaliser(releve_base_v4())
        self.assertTrue(demandes.verifier({"type": "partenaire_inscrit", "partenaire": "tripo", "inscrit": True}, sans))

    def test_faire_chez_partenaire(self):
        import base64
        r = releve.normaliser({**releve_base_v4(), "partenaires": self.r["partenaires"], "decisions_projet": [
            {"id": "d1", "genre": "faire_chez_partenaire", "texte": "À faire chez Tripo", "agent": "d1", "tache": "t1",
             "partenaire": "tripo", "quoi": "Un dragon", "prompt": "Un dragon", "reglages": [], "mode_operatoire": ["Ouvrir"],
             "a_rapporter": {"description": "Le .glb"}},
            {"id": "d2", "genre": "faire_chez_partenaire", "texte": "À faire chez Tripo", "agent": "d1", "tache": "t1",
             "partenaire": "tripo", "quoi": "Un loup", "prompt": "Un loup", "reglages": [], "mode_operatoire": ["Ouvrir"],
             "a_rapporter": {"description": "Le .glb"}, "apres": "d1"}]})
        png = base64.b64encode(PNG).decode()
        fichier = {"nom": "dragon.png", "type": "image/png", "donnees": png}

        def v(d):
            return demandes.verifier({"type": "faire_chez_partenaire", **d}, r)
        self.assertIsNone(v({"decision": "d1", "verdict": "fait"}))
        self.assertIsNone(v({"decision": "d1", "verdict": "fait", "texte": "Fait, en haute qualité.", "fichiers": [fichier]}))
        self.assertIsNone(v({"decision": "d1", "verdict": "impossible", "texte": "Plus de crédits."}))
        self.assertTrue(v({"decision": "d1", "verdict": "impossible"}))                       # dire pourquoi
        self.assertTrue(v({"decision": "d1", "verdict": "impossible", "texte": "x", "fichiers": [fichier]}))
        self.assertTrue(v({"decision": "d1", "verdict": "peut-être"}))
        self.assertTrue(v({"decision": "zz", "verdict": "fait"}))
        self.assertTrue(v({"decision": "d1", "verdict": "fait", "texte": "x" * 3501}))
        self.assertTrue(v({"decision": "d1", "verdict": "fait", "fichiers": [{**fichier, "nom": "x.exe"}]}))
        self.assertTrue(v({"decision": "d1", "verdict": "fait", "fichiers": [{**fichier, "donnees": "AAAA"}]}))
        self.assertIn("d1", v({"decision": "d2", "verdict": "fait"}))      # une génération à la fois : après d1
        r["decisions_projet"] = r["decisions_projet"][1:]
        self.assertIsNone(v({"decision": "d2", "verdict": "fait"}))        # d1 est faite : d2 vient
        self.assertEqual(demandes.nettoyer({"type": "faire_chez_partenaire", "decision": "d1", "verdict": "fait", "texte": "t",
                                            "fichiers": [{**fichier, "x": 1}], "autre": 1}),
                         {"type": "faire_chez_partenaire", "decision": "d1", "verdict": "fait", "texte": "t", "fichiers": [fichier]})

    def test_nettoyer(self):
        d = demandes.nettoyer({"type": "partenaire_regle", "partenaire": "tripo", "operation": "ajouter",
                               "texte": "x", "cle": "SECRET", "autre": 1})
        self.assertEqual(d, {"type": "partenaire_regle", "partenaire": "tripo", "operation": "ajouter", "texte": "x"})
        self.assertEqual(demandes.nettoyer({"type": "partenaires_maj", "confirme": True, "x": 1}),
                         {"type": "partenaires_maj", "confirme": True})
        self.assertEqual(demandes.nettoyer({"type": "partenaires_actualiser", "x": 1}), {"type": "partenaires_actualiser"})


ORGANISATION_WORKFLOW = {
    "services": [{"id": "dev", "nom": "Dev"}], "flux": [], "briefs": {}, "cout": {"tokens": [1, 2], "euros": None},
    "agents": [{"cle": "liv-1", "role": "livreur", "service": "dev", "modele": "Opus", "fable_suggere": True},
               {"cle": "dev-2", "role": "dev", "service": "dev", "modele": "Sonnet"}],
    "fonctionnalite": "f1", "workflow": {"id": "w-f1", "genre": "badges", "flux": []}}
R5 = releve.normaliser({
    "version": 4, "projet": "P", "factory": {"etat": "en marche"},
    "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}],
    "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
    "taches": [],
    "fonctionnalites": [
        {"id": "f1", "nom": "Casse-briques", "etape": "cadrage",
         "decisions": [{"id": "q1", "genre": "genre_fonctionnalite", "texte": "Où le faire ?", "propose": "jeu-mobile",
                        "genres_connus": ["badges"], "incertain": False,
                        "nouveau": {"id": "jeu-mobile", "description": "Jeux"}}]},
        {"id": "f2", "nom": "Incertain", "etape": "cadrage",
         "decisions": [{"id": "q2", "genre": "genre_fonctionnalite", "texte": "Même genre ?", "propose": "badges",
                        "genres_connus": ["badges"], "incertain": True}]}],
    "decisions_projet": [{"id": "o2", "genre": "organisation", "texte": "Workflow ?",
                          "organisation": ORGANISATION_WORKFLOW},
                         {"id": "v1", "genre": "valider_etape", "texte": "Valider ?", "fonctionnalite": "f1",
                          "element": {"id": "e1", "nom": "Accueil"}, "etape": "a", "tache": "t1",
                          "compte_rendu": "", "fichiers": []},
                         {"id": "e1", "genre": "elargir_genre", "texte": "Élargir ?", "cible": "badges",
                          "ancienne": "Badges", "propose": "Badges et logos", "fonctionnalite": "f1"},
                         {"id": "o1", "genre": "outil_agent", "texte": "Curl ?", "agent": "d1", "tache": "t1",
                          "outil": "Bash(curl:*)", "programme": "curl"},
                         {"id": "a1", "genre": "accord_agent", "texte": "Accord ?", "agent": "d1", "tache": "t1",
                          "quoi": "Générer 5 images"},
                         {"id": "o2", "genre": "outil_agent", "texte": "WebSearch ?", "agent": "d1", "tache": "t1",
                          "outil": "WebSearch"},
                         {"id": "c1", "genre": "confirmer_genre", "texte": "Genre ?", "propose": "jeu-mobile",
                          "genres_connus": ["badges"], "description": "Jeux pour téléphone"}]})


class TestVerifierGenreEtWorkflow(unittest.TestCase):
    """Les réponses aux décisions du parcours d'une nouvelle fonctionnalité (genre, workflow)."""

    def ok(self, d):
        self.assertIsNone(demandes.verifier(d, R5, frozenset(), None), d)

    def refus(self, d):
        self.assertTrue(demandes.verifier(d, R5, frozenset(), None), d)

    def test_environnement_d_une_fonctionnalite_ou_du_projet(self):
        import copy
        r = copy.deepcopy(R5)
        r["fonctionnalites"][0]["decisions"].append({"id": "n1", "genre": "environnement", "texte": "Il manque Java.",
                                                     "environnement": [{"outil": "JDK 17", "etat": "a_installer"}]})
        r["decisions_projet"].append({"id": "n2", "genre": "environnement", "texte": "Il manque Java.",
                                      "environnement": [{"outil": "JDK 17", "etat": "a_installer"}]})
        ok = lambda d: self.assertIsNone(demandes.verifier(d, r, frozenset(), None), d)
        refus = lambda d: self.assertTrue(demandes.verifier(d, r, frozenset(), None), d)
        ok({"type": "environnement", "decision": "n1", "fonctionnalite": "f1", "verdict": "fait"})
        ok({"type": "environnement", "decision": "n2", "verdict": "continuer"})          # sans fonctionnalité : le projet
        refus({"type": "environnement", "decision": "n1", "verdict": "fait"})              # n1 est celle de f1
        refus({"type": "environnement", "decision": "n2", "fonctionnalite": "f1", "verdict": "fait"})
        refus({"type": "environnement", "decision": "n2", "verdict": "plus tard"})
        refus({"type": "environnement", "decision": "zz", "verdict": "fait"})

    def test_installer_outil_en_autonomie(self):
        import copy
        r = copy.deepcopy(R5)
        auto = {"outil": "JDK 17", "etat": "a_installer", "autonome": True, "etapes": ["a", "b"],
                "telechargement": "https://adoptium.net/", "objectif": "Compiler le jeu."}
        r["fonctionnalites"][0]["decisions"].append({"id": "n1", "genre": "environnement", "texte": "Il manque.",
                                                     "environnement": [auto, {"outil": "Gradle", "etat": "a_installer"},
                                                                       dict(auto, outil="Pris", en_cours=True)]})
        r["decisions_projet"].append({"id": "n2", "genre": "environnement", "texte": "Il manque.",
                                      "environnement": [auto]})
        ok = lambda d: self.assertIsNone(demandes.verifier(d, r, frozenset(), None), d)
        refus = lambda d: self.assertTrue(demandes.verifier(d, r, frozenset(), None), d)
        ok({"type": "installer_outil", "decision": "n1", "fonctionnalite": "f1", "outil": "JDK 17"})
        ok({"type": "installer_outil", "decision": "n2", "outil": "JDK 17"})                 # celle du projet
        refus({"type": "installer_outil", "decision": "n1", "fonctionnalite": "f1", "outil": "Gradle"})   # pas autonome
        refus({"type": "installer_outil", "decision": "n1", "fonctionnalite": "f1", "outil": "Pris"})     # déjà en cours
        refus({"type": "installer_outil", "decision": "n1", "fonctionnalite": "f1", "outil": "Inconnu"})
        refus({"type": "installer_outil", "decision": "n1", "outil": "JDK 17"})                # n1 est celle de f1
        refus({"type": "installer_outil", "decision": "n2", "fonctionnalite": "f1", "outil": "JDK 17"})
        refus({"type": "installer_outil", "decision": "n1", "fonctionnalite": "zz", "outil": "JDK 17"})
        refus({"type": "installer_outil", "decision": "zz", "outil": "JDK 17"})
        refus({"type": "installer_outil", "decision": "n2", "outil": 3})
        refus({"type": "installer_outil", "decision": "n2"})
        self.assertEqual(demandes.nettoyer({"type": "installer_outil", "decision": "n2", "outil": "JDK 17", "x": 1}),
                         {"type": "installer_outil", "decision": "n2", "outil": "JDK 17"})

    def test_acceptation_avec_installation_en_autonomie(self):
        import copy
        r = copy.deepcopy(R5)
        org = copy.deepcopy(r["decisions_projet"][0]["organisation"])
        org["environnement"] = [{"outil": "JDK 17", "etat": "a_installer", "autonome": True},
                                {"outil": "Gradle", "etat": "a_installer"}, {"outil": "Git", "etat": "en_place",
                                                                              "autonome": True}]
        r["decisions_projet"][0]["organisation"] = org
        base = {"type": "organisation", "decision": "o2", "verdict": "accepter"}
        ok = lambda d: self.assertIsNone(demandes.verifier(d, r, frozenset(), None), d)
        refus = lambda d: self.assertTrue(demandes.verifier(d, r, frozenset(), None), d)
        ok({**base, "installer": ["JDK 17"]})
        ok({**base, "installer": []})
        refus({**base, "installer": ["Gradle"]})            # pas autonome
        refus({**base, "installer": ["Git"]})               # déjà en place
        refus({**base, "installer": ["JDK 17", "Inconnu"]})
        refus({**base, "installer": "JDK 17"})
        refus({**base, "installer": [3]})
        refus({**base, "verdict": "refuser", "installer": ["JDK 17"]})
        self.assertEqual(demandes.nettoyer({**base, "installer": ["JDK 17"], "x": 1}), {**base, "installer": ["JDK 17"]})

    def test_genre_fonctionnalite(self):
        base = {"type": "genre_fonctionnalite", "decision": "q1", "fonctionnalite": "f1"}
        self.ok({**base, "choix": "ici"})
        self.ok({**base, "choix": "ici", "genre": "badges"})
        self.ok({**base, "choix": "ici", "genre": "jeu-mobile"})                     # le genre nouveau de la décision
        self.ok({**base, "choix": "ici", "genre": "jeu-de-role", "description": "Jeux de rôle"})
        self.ok({**base, "choix": "nouveau_projet", "projet_cree": "C:/p/reglages.json"})
        self.refus({**base, "choix": "ici", "genre": "jeu-de-role"})                  # nouveau, sans description
        self.refus({**base, "choix": "ici", "genre": "Pas Valide"})
        self.refus({**base, "choix": "meme"})                                         # le moteur n'hésitait pas
        self.refus({**base, "choix": "nouveau_projet"})                               # sans le projet créé
        self.refus({**base, "choix": "ailleurs"})
        self.refus({**base, "choix": "ici", "decision": "zz"})
        self.refus({**base, "choix": "ici", "fonctionnalite": "zz"})
        self.refus({**base, "choix": "ici", "decision": "q2"})                        # la question d'une autre fonctionnalité
        self.ok({"type": "genre_fonctionnalite", "decision": "q2", "fonctionnalite": "f2", "choix": "meme"})

    def test_genre_du_projet_avec_la_phrase_proposee(self):
        base = {"type": "genre", "decision": "c1"}
        self.ok({**base, "genre": "jeu-mobile"})                                      # la phrase proposée suffit
        self.ok({**base, "genre": "jeu-mobile", "description": "Autre phrase"})
        self.refus({**base, "genre": "jeu-de-role"})                                  # autre genre nouveau : sa phrase

    def test_elargir_genre(self):
        base = {"type": "elargir_genre", "decision": "e1"}
        self.ok({**base, "verdict": "valider"})
        self.ok({**base, "verdict": "valider", "description": "Badges, logos et emotes"})
        self.ok({**base, "verdict": "refuser"})
        self.refus({**base, "verdict": "peut-etre"})
        self.refus({**base, "verdict": "valider", "decision": "zz"})
        self.refus({**base, "verdict": "valider", "description": "x" * 3501})
        self.assertEqual(demandes.nettoyer({**base, "verdict": "valider", "description": "d", "autre": 1}),
                         {**base, "verdict": "valider", "description": "d"})

    def test_outil_agent(self):
        base = {"type": "outil_agent", "decision": "o1"}
        self.ok({**base, "verdict": "autoriser"})
        self.ok({**base, "verdict": "refuser"})
        self.refus({**base, "verdict": "peut-etre"})
        self.refus({**base, "verdict": "autoriser", "decision": "zz"})
        self.refus({**base, "verdict": "autoriser", "decision": "o2"})          # pas de programme à autoriser
        self.ok({**base, "verdict": "relancer", "decision": "o2"})
        self.assertEqual(demandes.nettoyer({**base, "verdict": "refuser", "autre": 1}), {**base, "verdict": "refuser"})

    def test_fable_tache(self):
        r = copy.deepcopy(R5)
        r["decisions_projet"].append({"id": "d90", "genre": "fable_tache", "texte": "Fable ?", "tache": "t1",
                                      "raison": "Une preuve difficile."})
        de_la_decision = lambda r: [x for x in releve.valider(r) if "d90" in x]   # noqa: E731
        self.assertEqual(de_la_decision(r), [])
        base = {"type": "fable_tache", "decision": "d90"}
        for verdict in ("autoriser", "refuser"):
            self.assertIsNone(demandes.verifier({**base, "verdict": verdict}, r, frozenset(), None))
        for mauvais in ({**base, "verdict": "accepter"}, {**base, "verdict": "autoriser", "decision": "o1"}):
            self.assertIsNotNone(demandes.verifier(mauvais, r, frozenset(), None), mauvais)
        sans_raison = copy.deepcopy(r)
        del sans_raison["decisions_projet"][-1]["raison"]
        self.assertNotEqual(de_la_decision(sans_raison), [])

    def test_serie_arretee_et_fin_vue(self):
        r = copy.deepcopy(R5)
        r["decisions_projet"].append({"id": "s1", "genre": "serie_arretee", "texte": "La série ne progresse plus",
                                      "fonctionnalite": "f1"})
        r["fonctionnalites"][0]["fin"] = {"date": "2026-11-12T20:00:00+01:00", "vu": False, "livrables": []}
        verifier = lambda d: demandes.verifier(d, r, frozenset(), None)     # noqa: E731
        self.assertIsNone(verifier({"type": "serie_arretee", "decision": "s1", "verdict": "relancer"}))
        self.assertTrue(verifier({"type": "serie_arretee", "decision": "s1", "verdict": "garder"}))
        self.assertTrue(verifier({"type": "serie_arretee", "decision": "a1", "verdict": "relancer"}))
        self.assertIsNone(verifier({"type": "fin_vue", "fonctionnalite": "f1"}))
        self.assertTrue(verifier({"type": "fin_vue", "fonctionnalite": "f2"}))       # sans avis de fin
        self.assertTrue(verifier({"type": "fin_vue", "fonctionnalite": "f9"}))
        self.assertEqual(demandes.nettoyer({"type": "fin_vue", "fonctionnalite": "f1", "autre": 1}),
                         {"type": "fin_vue", "fonctionnalite": "f1"})

    def test_accord_agent(self):
        base = {"type": "accord_agent", "decision": "a1"}
        self.ok({**base, "verdict": "accepter"})
        self.ok({**base, "verdict": "refuser", "texte": "Utilise l'émulateur."})
        self.refus({**base, "verdict": "autoriser"})
        self.refus({**base, "verdict": "refuser", "decision": "zz"})
        self.refus({**base, "verdict": "refuser", "texte": "x" * 3501})
        self.assertEqual(demandes.nettoyer({**base, "verdict": "refuser", "texte": "t", "autre": 1}),
                         {**base, "verdict": "refuser", "texte": "t"})

    def test_valider_etape(self):
        base = {"type": "valider_etape", "decision": "v1"}
        self.ok({**base, "verdict": "valider"})
        self.ok({**base, "verdict": "valider", "texte": "Bravo"})
        self.ok({**base, "verdict": "renvoyer", "texte": "Le menu est trop chargé"})
        self.refus({**base, "verdict": "renvoyer"})                                  # une remarque est obligatoire
        self.refus({**base, "verdict": "renvoyer", "texte": "   "})
        self.refus({**base, "verdict": "renvoyer", "texte": "x" * 3501})
        self.refus({**base, "verdict": "peut-etre"})
        self.refus({**base, "verdict": "valider", "decision": "zz"})
        self.refus({**base, "verdict": "valider", "decision": "o2"})                 # la décision d'un autre genre
        self.assertEqual(demandes.nettoyer({**base, "verdict": "renvoyer", "texte": "t", "autre": 1}),
                         {**base, "verdict": "renvoyer", "texte": "t"})

    def test_valider_etape_depuis_la_fenetre(self):
        """Une réponse par point ; une décision d'avant (sans points) n'en a qu'un ; le verdict en découle ; renvoyer
        n'exige plus de texte (les points à revoir en tiennent lieu)."""
        import copy
        r = copy.deepcopy(R5)
        r["decisions_projet"].append({"id": "v2", "genre": "valider_etape", "texte": "Valider ?", "fonctionnalite": "f1",
                                      "element": {"id": "e2", "nom": "Jeu"}, "etape": "a", "tache": "t1",
                                      "compte_rendu": "", "fichiers": [], "points": ["Le jeu se lance", "Le son marche"]})
        ok = lambda d: self.assertIsNone(demandes.verifier(d, r, frozenset(), None), d)            # noqa: E731
        refus = lambda d: self.assertTrue(demandes.verifier(d, r, frozenset(), None), d)           # noqa: E731
        ancien = {"type": "valider_etape", "decision": "v1"}
        ok({**ancien, "verdict": "valider", "reponses": [{"point": "L'élément correspond à l'objectif", "ok": True}]})
        refus({**ancien, "verdict": "valider", "reponses": [{"point": "Autre chose", "ok": True}]})
        base = {"type": "valider_etape", "decision": "v2"}
        tous = [{"point": "Le jeu se lance", "ok": True}, {"point": "Le son marche", "ok": True}]
        ok({**base, "verdict": "valider", "reponses": tous})
        ok({**base, "verdict": "valider", "reponses": tous, "texte": "Une note hors validation"})
        ok({**base, "verdict": "renvoyer", "reponses": [tous[0], {"point": "Le son marche", "ok": False}]})
        refus({**base, "verdict": "renvoyer", "reponses": tous})                          # le verdict ne découle pas
        refus({**base, "verdict": "valider", "reponses": tous[:1]})                       # un point sans réponse
        refus({**base, "verdict": "valider", "reponses": tous + [{"point": "En plus", "ok": True}]})
        refus({**base, "verdict": "valider", "reponses": [{"point": "Le jeu se lance", "ok": "oui"}, tous[1]]})
        refus({**base, "verdict": "valider", "reponses": "tout"})
        refus({**base, "verdict": "valider", "reponses": tous, "texte": "x" * 3501})
        self.assertEqual(demandes.nettoyer({**base, "verdict": "valider", "reponses": [{**tous[0], "x": 1}], "y": 2}),
                         {**base, "verdict": "valider", "reponses": [tous[0]]})

    def test_parallelisme(self):
        base = {"type": "parallelisme"}
        self.ok({**base, "agents_locaux_max": 1, "agents_cloud_max": 0})
        self.ok({**base, "agents_locaux_max": 16, "agents_cloud_max": 16})
        for mauvais in ({"agents_locaux_max": 0, "agents_cloud_max": 0}, {"agents_locaux_max": 17, "agents_cloud_max": 0},
                        {"agents_locaux_max": 2, "agents_cloud_max": -1}, {"agents_locaux_max": 2, "agents_cloud_max": 17},
                        {"agents_locaux_max": "2", "agents_cloud_max": 0}, {"agents_locaux_max": True, "agents_cloud_max": 0},
                        {"agents_locaux_max": 2.0, "agents_cloud_max": 0}, {"agents_locaux_max": 2}):
            self.refus({**base, **mauvais})
        self.assertEqual(demandes.nettoyer({**base, "agents_locaux_max": 2, "agents_cloud_max": 1, "autre": 1}),
                         {**base, "agents_locaux_max": 2, "agents_cloud_max": 1})

    def test_organisation_d_un_workflow(self):
        base = {"type": "organisation", "decision": "o2"}
        self.ok({**base, "verdict": "accepter"})
        self.ok({**base, "verdict": "accepter", "fable": ["liv-1"]})
        self.ok({**base, "verdict": "accepter", "fable": []})
        self.ok({**base, "verdict": "refuser", "texte": "Sans service de livraison"})
        self.ok({**base, "verdict": "refuser"})
        self.ok({**base, "verdict": "abandonner"})
        self.refus({**base, "verdict": "accepter", "fable": ["dev-2"]})                # Fable pas suggéré pour lui
        self.refus({**base, "verdict": "accepter", "fable": "liv-1"})
        self.refus({**base, "verdict": "refuser", "fable": ["liv-1"]})
        self.refus({**base, "verdict": "refuser", "texte": "  "})
        self.refus({**base, "verdict": "peut-etre"})

    def test_abandonner_seulement_un_workflow(self):
        sans = copy.deepcopy(R4)
        self.assertTrue(demandes.verifier({"type": "organisation", "decision": "o1", "verdict": "abandonner"}, sans,
                                          frozenset(), None))

    def test_nettoyer(self):
        d = demandes.nettoyer({"type": "genre_fonctionnalite", "decision": "q1", "fonctionnalite": "f1",
                               "choix": "ici", "genre": "x", "description": "d", "projet_cree": "p", "autre": 1})
        self.assertEqual(d, {"type": "genre_fonctionnalite", "decision": "q1", "fonctionnalite": "f1", "choix": "ici",
                             "genre": "x", "description": "d", "projet_cree": "p"})
        d = demandes.nettoyer({"type": "organisation", "decision": "o2", "verdict": "accepter", "fable": ["liv-1"],
                               "texte": "t", "autre": 1})
        self.assertEqual(d, {"type": "organisation", "decision": "o2", "verdict": "accepter", "texte": "t",
                             "fable": ["liv-1"]})


if __name__ == "__main__":
    unittest.main()
