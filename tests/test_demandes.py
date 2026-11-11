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
        {"id": "f5", "nom": "Simple", "etape": "cadrage"}],
    "decisions_projet": [
        {"id": "g1", "genre": "confirmer_genre", "texte": "Genre ?", "propose": "ville",
         "genres_connus": ["ville"]},
        {"id": "s1", "genre": "session_cloud", "texte": "Session ?", "agent": "d1"},
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


if __name__ == "__main__":
    unittest.main()
