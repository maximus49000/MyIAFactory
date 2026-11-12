import copy
import json
import os
import sys
import tempfile
import time
import subprocess
import unittest
from pathlib import Path

from unittest import mock

from bureau import releve

RACINE = Path(__file__).resolve().parent.parent

BASE = {"version": 1, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}]}


class TestValider(unittest.TestCase):
    def test_base_valide(self):
        self.assertEqual(releve.valider(BASE), [])

    def test_erreurs(self):
        cas = [("colonne inconnue", lambda r: r["taches"][0].update(colonne="z")),
               ("titulaire inconnu", lambda r: r["taches"][0].update(titulaire="x")),
               ("etat factory", lambda r: r["factory"].update(etat="arrêt")),
               ("lieu", lambda r: r["titulaires"][0].update(lieu="lune")),
               ("service inconnu", lambda r: r["titulaires"][0].update(service="rh")),
               ("doublon", lambda r: r["taches"].append(dict(r["taches"][0]))),
               ("9 services", lambda r: r.update(services=[{"id": str(i), "nom": "S"} for i in range(9)])),
               ("deux chefs", lambda r: r["titulaires"].extend([{"cle": "c1", "lieu": "local", "chef": True}, {"cle": "c2", "lieu": "local", "chef": True}])),
               ("champ manquant", lambda r: r.pop("colonnes")),
               # Champs facultatifs de mauvais type : la page s'y casserait.
               ("file pas un objet", lambda r: r.update(file=[])),
               ("file.visibles pas une liste", lambda r: r.update(file={"visibles": 3})),
               ("file.visibles avec null", lambda r: r.update(file={"visibles": [None]})),
               ("file.visibles sans id", lambda r: r.update(file={"visibles": [{"titre": "T"}]})),
               ("file.visibles titre", lambda r: r.update(file={"visibles": [{"id": "q", "titre": 3}]})),
               ("file.reste texte", lambda r: r.update(file={"reste": "beaucoup"})),
               ("file.reste négatif", lambda r: r.update(file={"reste": -1})),
               ("decisions texte", lambda r: r.update(decisions="2")),
               ("decisions booléen", lambda r: r.update(decisions=True)),
               ("postit texte", lambda r: r["taches"][0].update(postit="oui")),
               ("etape nombre", lambda r: r["taches"][0].update(etape=3)),
               ("maj nombre", lambda r: r["taches"][0].update(maj=20261110)),
               ("nom de service", lambda r: r["services"][0].update(nom=None)),
               ("nom de colonne", lambda r: r["colonnes"][0].update(nom=["A"])),
               ("modele", lambda r: r["titulaires"][0].update(modele={"x": 1})),
               ("permanent", lambda r: r["titulaires"][0].update(permanent="oui")),
               ("fraicheur_min", lambda r: r["titulaires"][0].update(fraicheur_min="30")),
               ("factory.depuis", lambda r: r["factory"].update(depuis=3))]
        for nom, casser in cas:
            r = copy.deepcopy(BASE)
            casser(r)
            self.assertTrue(releve.valider(r), nom)

    def test_champs_facultatifs_bien_formes(self):
        r = copy.deepcopy(BASE)
        r["factory"]["depuis"] = "2026-11-10T09:00:00"
        r["file"] = {"visibles": [{"id": "q1", "titre": "Q"}], "reste": 4}
        r["decisions"] = 2
        r["taches"][0].update(postit=False, etape=None, maj=None)
        r["titulaires"][0].update(modele="Sonnet", permanent=True, fraicheur_min=12.5)
        self.assertEqual(releve.valider(r), [])

    def test_valider_ne_plante_pas_sur_n_importe_quoi(self):
        for r in (None, [], "x", {"taches": 3}, {"version": 1, "taches": [None]}):
            self.assertTrue(releve.valider(r))


class TestNormaliser(unittest.TestCase):
    def test_normaliser_ajoute_chef_et_defauts(self):
        n = releve.normaliser(BASE)
        self.assertIn("chef", [t["cle"] for t in n["titulaires"]])
        self.assertEqual((n["taches"][0]["postit"], n["file"], n["decisions"]),
                         (True, {"visibles": [], "reste": 0}, 0))
        self.assertEqual(n["titulaires"][0]["modele"], "?")
        self.assertNotIn("file", BASE)
        self.assertEqual(len(BASE["titulaires"]), 1)


V2 = {**copy.deepcopy(BASE), "version": 2}


def v2(**champs):
    r = copy.deepcopy(V2)
    r.update(champs)
    return r


class TestVersion2(unittest.TestCase):
    def test_version_2_minimale_valide(self):
        self.assertEqual(releve.valider(V2), [])

    def test_version_5_refusee(self):
        self.assertTrue(releve.valider({**BASE, "version": 5}))

    def test_neuf_services_refuses(self):
        def avec(n):
            return v2(services=[{"id": str(i), "nom": "S"} for i in range(n)], titulaires=[], taches=[])
        self.assertEqual(releve.valider(avec(8)), [])
        self.assertTrue(any("8" in m for m in releve.valider(avec(9))))

    def test_lien_javascript_refuse(self):
        r = v2(actions=[{"id": "a", "libelle": "A", "lien": "javascript:alert(1)"}])
        self.assertTrue(any("actions" in m for m in releve.valider(r)))

    def test_lien_claude_accepte(self):
        r = v2(actions=[{"id": "a", "libelle": "A", "lien": "claude://claude.ai/code/x"}])
        self.assertEqual(releve.valider(r), [])
        self.assertTrue(releve.lien_valide("https://exemple.org/x"))
        self.assertTrue(releve.lien_valide("http://exemple.org/x"))
        for mauvais in ("javascript:x", "file:///x", "https://a b", "https://a\n.b", "", None, 3, "//x"):
            self.assertFalse(releve.lien_valide(mauvais), mauvais)

    def test_journal_pas_liste(self):
        r = v2()
        r["taches"][0]["journal"] = "texte"
        self.assertTrue(any("journal" in m for m in releve.valider(r)))

    def test_lien_de_tache_javascript(self):
        r = v2()
        r["taches"][0]["liens"] = [{"libelle": "x", "url": "javascript:alert(1)"}]
        self.assertTrue(any("liens" in m for m in releve.valider(r)))

    def test_lecon_agent_inconnu(self):
        r = v2(lecons=[{"id": "l1", "agent": "inconnu", "texte": "t"}])
        self.assertTrue(any("l1" in m for m in releve.valider(r)))
        r = v2(lecons=[{"id": "l1", "agent": "d1", "texte": "t", "verdict_demande": "valider"}])
        self.assertEqual(releve.valider(r), [])
        r = v2(lecons=[{"id": "l1", "agent": "d1", "texte": "t", "verdict_demande": "peut-etre"}])
        self.assertTrue(releve.valider(r))

    def test_quarante_et_une_images(self):
        r = v2()
        r["taches"][0]["images"] = [{"chemin": f"{i}.png"} for i in range(40)]
        self.assertEqual(releve.valider(r), [])
        r["taches"][0]["images"].append({"chemin": "41.png"})
        self.assertTrue(any("images" in m for m in releve.valider(r)))

    def test_type_inconnu(self):
        r = v2(types=[{"id": "bug", "nom": "Bug"}])
        r["taches"][0]["type"] = "autre"
        self.assertTrue(any("type" in m for m in releve.valider(r)))
        r["taches"][0]["type"] = "bug"
        self.assertEqual(releve.valider(r), [])

    def test_titulaire_et_retours(self):
        r = v2()
        r["titulaires"][0].update(prenom="Zoé", specialite="Tests",
                                  lecons=[{"id": "x", "texte": "t", "etat": "validée"}])
        r["taches"][0].update(retours=[{"t": "2026-11-10T10:00:00", "texte": "r", "reponse": "ok"}],
                              bloquee="attend", journal=[{"t": "x", "texte": "y"}])
        self.assertEqual(releve.valider(r), [])
        r["titulaires"][0]["lecons"][0]["etat"] = "autre"
        self.assertTrue(releve.valider(r))

    def test_valeurs_non_hachables_refusees_sans_exception(self):
        mauvais = [v2(actions=[{"id": [], "libelle": "A"}]), v2(actions=[{"id": {}, "libelle": "A"}]),
                   v2(lecons=[{"id": [], "agent": "d1", "texte": "t"}]),
                   v2(lecons=[{"id": "l", "agent": [], "texte": "t"}])]
        for champ, valeur in (("colonne", []), ("titulaire", []), ("colonne", {})):
            r = v2()
            r["taches"][0][champ] = valeur
            mauvais.append(r)
        r = v2()
        r["titulaires"][0]["service"] = []
        mauvais.append(r)
        for r in mauvais:
            self.assertTrue(releve.valider(r))

    def test_actions_mal_formees(self):
        for actions in ("x", [3], [{"id": "", "libelle": "A"}],
                        [{"id": "a", "libelle": "A"}, {"id": "a", "libelle": "B"}],
                        [{"id": "a", "libelle": "A", "actif": "oui"}],
                        [{"id": "a", "libelle": 3}], [{"id": "a", "libelle": "A", "confirmer": 3}]):
            self.assertTrue(releve.valider(v2(actions=actions)), actions)

    def test_champs_facultatifs_nuls_comptent_pour_absents(self):
        r = v2(actions=[{"id": "a", "libelle": "A", "lien": None, "confirmer": None, "actif": None}])
        r["titulaires"][0].update({"prenom": None, "specialite": None})
        self.assertEqual(releve.valider(r), [])
        n = releve.normaliser(r)
        self.assertIsNone(n["actions"][0]["lien"])

    def test_notes_valides(self):
        r = v2()
        r["taches"][0]["notes"] = [{"libelle": "L", "texte": "a\nb"}]
        r["taches"][0]["retours"] = [{"t": "1", "texte": "x", "etat": "nouveau"}, {"t": "2", "texte": "y", "etat": None}]
        self.assertEqual(releve.valider(r), [])
        r["taches"][0]["notes"] = None
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(releve.normaliser(r)["taches"][0]["notes"], [])

    def test_notes_mal_formees(self):
        for notes in ("x", [3], [{"libelle": "", "texte": "a"}], [{"libelle": "L", "texte": ""}],
                      [{"libelle": "L"}], [{"libelle": 1, "texte": "a"}]):
            r = v2()
            r["taches"][0]["notes"] = notes
            self.assertTrue(releve.valider(r), notes)
        r = v2()
        r["taches"][0]["retours"] = [{"t": "1", "texte": "x", "etat": 3}]
        self.assertTrue(releve.valider(r))

    def test_notes_absentes_en_version_1(self):
        r = copy.deepcopy(BASE)
        r["taches"][0]["notes"] = "n'importe quoi"
        self.assertEqual(releve.valider(r), [])
        self.assertNotIn("notes", releve.normaliser(r)["taches"][0])

    def test_version_1_ignore_les_ajouts(self):
        r = copy.deepcopy(BASE)
        r["actions"] = "n'importe quoi"
        r["taches"][0]["journal"] = 3
        self.assertEqual(releve.valider(r), [])
        n = releve.normaliser(r)
        self.assertNotIn("actions", n)
        self.assertNotIn("journal", n["taches"][0])
        self.assertNotIn("bloquee", n["taches"][0])

    def test_normaliser_v2_defauts(self):
        n = releve.normaliser(V2)
        self.assertEqual((n["actions"], n["types"], n["lecons"]), ([], [], []))
        t = n["taches"][0]
        self.assertEqual((t["journal"], t["images"], t["liens"], t["retours"], t["type"], t["bloquee"]),
                         ([], [], [], [], None, None))


def v3(**champs):
    r = copy.deepcopy({**BASE, "version": 3})
    r.update(champs)
    return r


def usage(**champs):
    u = {"id": "u1", "tache": "t1", "agent": "d1", "modele": "sonnet", "etape": "dev",
         "t": "2026-11-09T10:00:00", "entree": 1000, "sortie": 200}
    u.update(champs)
    return u


class TestVersion3(unittest.TestCase):
    def test_version_3_valide(self):
        self.assertEqual(releve.valider(v3()), [])

    def test_v2_inchange(self):
        # Les contrôles de la version 2 s'appliquent aussi à la 3.
        for version in (2, 3):
            r = copy.deepcopy({**BASE, "version": version})
            r["taches"][0]["journal"] = 3
            self.assertTrue(releve.valider(r), version)
        n = releve.normaliser(v3())
        self.assertEqual((n["actions"], n["types"], n["lecons"]), ([], [], []))
        self.assertEqual(n["taches"][0]["journal"], [])
        self.assertEqual(n["file"]["suite"], [])

    def test_usage_valide(self):
        r = v3(usage=[usage(), usage(id="u2", tache=None, cache_lecture=5, cache_ecriture=0),
                      usage(id="u3", etape=None)])
        self.assertEqual(releve.valider(r), [])

    def test_usage_id_en_double(self):
        erreurs = releve.valider(v3(usage=[usage(), usage()]))
        self.assertTrue(any("usage" in m for m in erreurs), erreurs)

    def test_usage_tokens_negatifs(self):
        for champ in ("entree", "sortie", "cache_lecture", "cache_ecriture"):
            erreurs = releve.valider(v3(usage=[usage(**{champ: -1})]))
            self.assertTrue(any("usage" in m for m in erreurs), champ)
        for valeur in (1.5, "12", None):
            self.assertTrue(releve.valider(v3(usage=[usage(entree=valeur)])), valeur)

    def test_usage_bool_refuse(self):
        self.assertTrue(releve.valider(v3(usage=[usage(entree=True)])))
        self.assertTrue(releve.valider(v3(usage=[usage(cache_lecture=False)])))

    def test_usage_agent_inconnu(self):
        erreurs = releve.valider(v3(usage=[usage(agent="x")]))
        self.assertTrue(any("usage" in m for m in erreurs), erreurs)
        self.assertTrue(releve.valider(v3(usage=[usage(agent=["d1"])])))

    def test_usage_tache_inconnue(self):
        erreurs = releve.valider(v3(usage=[usage(tache="t9")]))
        self.assertTrue(any("usage" in m for m in erreurs), erreurs)

    def test_usage_mal_forme(self):
        cas = [("pas une liste", {"usage": 3}),
               ("élément pas un objet", {"usage": [3]}),
               ("id vide", {"usage": [usage(id="")]}),
               ("modele vide", {"usage": [usage(modele="")]}),
               ("modele nombre", {"usage": [usage(modele=3)]}),
               ("etape nombre", {"usage": [usage(etape=3)]}),
               ("t absent", {"usage": [{k: v for k, v in usage().items() if k != "t"}]}),
               ("t illisible", {"usage": [usage(t="hier")]}),
               ("sortie absente", {"usage": [{k: v for k, v in usage().items() if k != "sortie"}]})]
        for nom, champs in cas:
            erreurs = releve.valider(v3(**champs))
            self.assertTrue(any("usage" in m for m in erreurs), nom)

    def test_usage_du_chef(self):
        # Le chef ajouté par la normalisation (clé « chef ») est connu, comme un chef déclaré.
        self.assertEqual(releve.valider(v3(usage=[usage(agent="chef", tache=None)])), [])
        r = v3(usage=[usage(agent="dir", tache=None)])
        r["titulaires"].append({"cle": "dir", "lieu": "local", "chef": True})
        self.assertEqual(releve.valider(r), [])

    def test_usage_ignore_en_v2(self):
        for version in (1, 2):
            r = copy.deepcopy({**BASE, "version": version, "usage": [usage(entree=-5)]})
            self.assertEqual(releve.valider(r), [], version)
            self.assertNotIn("usage", releve.normaliser(r))

    def test_usage_5001_refuse(self):
        def avec(n):
            return v3(usage=[usage(id=f"u{i}") for i in range(n)])
        self.assertEqual(releve.valider(avec(releve.MAX_USAGE)), [])
        self.assertEqual(releve.MAX_USAGE, 5000)
        erreurs = releve.valider(avec(5001))
        self.assertTrue(any("usage" in m and "5000" in m for m in erreurs), erreurs[:3])

    def test_normaliser_usage_defaut(self):
        self.assertEqual(releve.normaliser(v3())["usage"], [])
        self.assertEqual(releve.normaliser(v3(usage=None))["usage"], [])
        n = releve.normaliser(v3(usage=[usage()]))
        self.assertEqual(n["usage"][0]["id"], "u1")
        self.assertEqual((n["usage"][0]["cache_lecture"], n["usage"][0]["cache_ecriture"]), (0, 0))


def connaissance(**champs):
    c = {"id": "k1", "texte": "Relire les exports", "date": "2026-11-08",
         "origine": "ch1", "appris_de": [{"agent": "d1", "tache": "t1", "retour": "2026-11-07"}]}
    c.update(champs)
    return c


def challenge(**champs):
    c = {"id": "ch1", "cible": {"type": "connaissance", "id": "k1"}, "texte": "Constat",
         "date": "2026-11-09", "solutions": [{"id": "s1", "texte": "Faire X", "auteur": "directeur",
                                              "etat": "proposée"},
                                             {"id": "s2", "texte": "Faire Y", "auteur": "service"}]}
    c.update(champs)
    return c


def avec_connaissances(*liste, **champs):
    r = v3(**champs)
    r["titulaires"][0]["connaissances"] = list(liste)
    return r


class TestConnaissances(unittest.TestCase):
    def test_connaissance_valide(self):
        self.assertEqual(releve.valider(avec_connaissances(connaissance(), connaissance(id="k2", date=None,
                                                                                        origine=None,
                                                                                        appris_de=None))), [])
        self.assertEqual(releve.valider(avec_connaissances()), [])
        n = releve.normaliser(avec_connaissances(connaissance(id="k2", appris_de=None)))
        self.assertEqual(n["titulaires"][0]["connaissances"][0]["appris_de"], [])

    def test_connaissance_mal_formee(self):
        cas = [("pas une liste", 3), ("élément", [3]), ("id vide", [connaissance(id="")]),
               ("texte absent", [{"id": "k1"}]), ("date nombre", [connaissance(date=3)]),
               ("origine nombre", [connaissance(origine=3)]), ("appris_de objet", [connaissance(appris_de={})]),
               ("doublon", [connaissance(), connaissance()])]
        for nom, valeur in cas:
            r = v3()
            r["titulaires"][0]["connaissances"] = valeur
            self.assertTrue(any("connaissance" in m.lower() for m in releve.valider(r)), nom)

    def test_id_connaissance_double_entre_titulaires(self):
        r = avec_connaissances(connaissance())
        r["titulaires"].append({"cle": "d2", "service": "dev", "lieu": "local", "connaissances": [connaissance()]})
        self.assertTrue(releve.valider(r))

    def test_appris_de_agent_inconnu_refuse(self):
        r = avec_connaissances(connaissance(appris_de=[{"agent": "x"}]))
        self.assertTrue(any("appris_de" in m for m in releve.valider(r)))
        r = avec_connaissances(connaissance(appris_de=[{"agent": "d1", "tache": 3}]))
        self.assertTrue(releve.valider(r))
        r = avec_connaissances(connaissance(appris_de=[{"agent": "d1", "retour": 3}]))
        self.assertTrue(releve.valider(r))
        # Le chef ajouté par la normalisation est un agent connu.
        self.assertEqual(releve.valider(avec_connaissances(connaissance(appris_de=[{"agent": "chef"}]))), [])

    def test_id_connaissance_double_avec_une_lecon(self):
        r = avec_connaissances(connaissance(id="l1"))
        r["titulaires"][0]["lecons"] = [{"id": "l1", "texte": "Ancien", "etat": "validée"}]
        self.assertEqual(releve.valider(r), [])

    def test_challenge_valide(self):
        self.assertEqual(releve.valider(v3(challenges=[challenge(), challenge(id="ch2", date=None,
                                                                              cible={"type": "kpi", "id": "x"},
                                                                              solutions=[])])), [])
        self.assertEqual(releve.valider(v3(challenges=[challenge(id="ch3", cible={"type": "source", "id": "y"},
                                                                 solutions=None)])), [])
        n = releve.normaliser(v3(challenges=[challenge(solutions=None)]))
        self.assertEqual(n["challenges"][0]["solutions"], [])

    def test_challenge_mal_forme(self):
        cas = [("pas une liste", 3), ("élément", [3]), ("id vide", [challenge(id="")]),
               ("texte absent", [{k: v for k, v in challenge().items() if k != "texte"}]),
               ("cible absente", [{k: v for k, v in challenge().items() if k != "cible"}]),
               ("cible id vide", [challenge(cible={"type": "kpi", "id": ""})]),
               ("date nombre", [challenge(date=3)]), ("solutions objet", [challenge(solutions={})]),
               ("doublon", [challenge(), challenge()]),
               ("solution sans texte", [challenge(solutions=[{"id": "s1", "auteur": "service"}])]),
               ("solution etat nombre", [challenge(solutions=[{"id": "s1", "texte": "a", "auteur": "service",
                                                              "etat": 1}])]),
               ("solution en double", [challenge(), challenge(id="ch2")])]
        for nom, valeur in cas:
            self.assertTrue(any("challenge" in m.lower() for m in releve.valider(v3(challenges=valeur))), nom)

    def test_solution_auteur_inconnu(self):
        r = v3(challenges=[challenge(solutions=[{"id": "s1", "texte": "a", "auteur": "stagiaire"}])])
        self.assertTrue(any("auteur" in m for m in releve.valider(r)))
        for auteur in ("directeur", "service", "utilisateur"):
            r = v3(challenges=[challenge(solutions=[{"id": "s1", "texte": "a", "auteur": auteur}])])
            self.assertEqual(releve.valider(r), [], auteur)

    def test_cible_type_inconnu(self):
        r = v3(challenges=[challenge(cible={"type": "tache", "id": "t1"})])
        self.assertTrue(any("cible" in m for m in releve.valider(r)))

    def test_v2_ignore_les_ajouts(self):
        for version in (1, 2):
            r = avec_connaissances(3, challenges=3)
            r["version"] = version
            self.assertEqual(releve.valider(r), [], version)
            n = releve.normaliser(r)
            self.assertNotIn("challenges", n)
            self.assertNotIn("connaissances", n["titulaires"][0])

    def test_normaliser_absents_restent_absents(self):
        # L'absence masque l'onglet : la normalisation n'invente pas de liste vide.
        n = releve.normaliser(v3())
        self.assertNotIn("challenges", n)
        self.assertNotIn("connaissances", n["titulaires"][0])


class TestColonneTerminee(unittest.TestCase):
    def test_terminee_bien_formee(self):
        for valeur in (True, False, None):
            r = v2(colonnes=[{"id": "a", "nom": "A", "terminee": valeur}])
            self.assertEqual(releve.valider(r), [], valeur)

    def test_terminee_mal_formee(self):
        for valeur in ("oui", 1, [], {}):
            r = v2(colonnes=[{"id": "a", "nom": "A", "terminee": valeur}])
            self.assertTrue(releve.valider(r), valeur)

    def test_terminee_ignoree_en_version_1(self):
        r = {**copy.deepcopy(BASE), "colonnes": [{"id": "a", "nom": "A", "terminee": "oui"}]}
        self.assertEqual(releve.valider(r), [])
        self.assertNotIn("terminee", releve.normaliser(r)["colonnes"][0])

    def test_normaliser_terminee(self):
        r = v2(colonnes=[{"id": "a", "nom": "A"}, {"id": "b", "nom": "B", "terminee": True},
                         {"id": "c", "nom": "C", "terminee": None}])
        self.assertEqual([c["terminee"] for c in releve.normaliser(r)["colonnes"]], [False, True, False])


class TestSuiteDeFile(unittest.TestCase):
    def file(self, **champs):
        return v2(file={"visibles": [{"id": "q1", "titre": "Q"}], "reste": 3, **champs})

    def test_suite_valide(self):
        r = self.file(suite=[{"id": "q2", "titre": "Q2"}, {"id": "q3", "titre": None}])
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(releve.valider(self.file(suite=None)), [])
        self.assertEqual(releve.valider(self.file(suite=[])), [])

    def test_suite_peut_etre_plus_courte_que_reste(self):
        self.assertEqual(releve.valider(self.file(reste=50, suite=[{"id": "q2", "titre": "Q2"}])), [])

    def test_suite_mal_formee(self):
        for suite in (3, "x", {}, [None], [{"titre": "T"}], [{"id": "", "titre": "T"}],
                      [{"id": 3, "titre": "T"}], [{"id": "q2", "titre": 3}]):
            self.assertTrue(releve.valider(self.file(suite=suite)), suite)

    def test_suite_cinq_cent_un_elements(self):
        def suite(n):
            return [{"id": f"s{i}", "titre": "S"} for i in range(n)]
        self.assertEqual(releve.valider(self.file(suite=suite(500))), [])
        self.assertTrue(releve.valider(self.file(suite=suite(501))))

    def test_identifiants_uniques_entre_visibles_suite_et_taches(self):
        for suite in ([{"id": "q1", "titre": "doublon visible"}],
                      [{"id": "t1", "titre": "doublon tâche"}],
                      [{"id": "q2", "titre": "a"}, {"id": "q2", "titre": "b"}]):
            self.assertTrue(releve.valider(self.file(suite=suite)), suite)
        self.assertTrue(releve.valider(v2(file={"visibles": [{"id": "t1", "titre": "Q"}]})))

    def test_suite_ignoree_en_version_1(self):
        r = {**copy.deepcopy(BASE), "file": {"visibles": [], "reste": 2, "suite": 3}}
        self.assertEqual(releve.valider(r), [])
        self.assertNotIn("suite", releve.normaliser(r)["file"])

    def test_normaliser_suite(self):
        self.assertEqual(releve.normaliser(self.file())["file"]["suite"], [])
        n = releve.normaliser(self.file(suite=[{"id": "q2", "titre": "Q2"}]))
        self.assertEqual(n["file"]["suite"], [{"id": "q2", "titre": "Q2"}])
        self.assertEqual(releve.normaliser(v2())["file"]["suite"], [])
        self.assertEqual(releve.normaliser(self.file(suite=None))["file"]["suite"], [])


class TestObtenir(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def regl(self, source):
        return {"releve": source, "dossier": str(self.tmp)}

    def test_obtenir_fichier(self):
        (self.tmp / "r.json").write_text(json.dumps(BASE), encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_fichier_absent(self):
        r, err = releve.obtenir(self.regl({"fichier": "absent.json"}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_json_tronque(self):
        (self.tmp / "r.json").write_text('{"version": 1, "ta', encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_invalide(self):
        b = copy.deepcopy(BASE)
        b["taches"][0]["colonne"] = "zzz"
        (self.tmp / "r.json").write_text(json.dumps(b), encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(r)
        self.assertIn("zzz", err)

    def test_obtenir_commande(self):
        cmd = [sys.executable, "-c", "import json,sys; print(json.dumps(%r))" % BASE]
        r, err = releve.obtenir(self.regl({"commande": cmd, "dossier": "."}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_commande_en_echec(self):
        cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
        r, err = releve.obtenir(self.regl({"commande": cmd}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def _avec_delai_court(self):
        ancien = releve.DELAI_COMMANDE_S
        releve.DELAI_COMMANDE_S = 1
        self.addCleanup(setattr, releve, "DELAI_COMMANDE_S", ancien)

    def _processus_lances(self):
        """Note les processus créés par `_executer` pour relire l'état de leurs tubes ensuite."""
        crees = []
        vrai = subprocess.Popen

        def espion(*a, **k):
            p = vrai(*a, **k)
            crees.append(p)
            return p
        patcheur = mock.patch.object(releve.subprocess, "Popen", espion)
        patcheur.start()
        self.addCleanup(patcheur.stop)
        return crees

    def test_executer_ferme_les_tubes(self):
        crees = self._processus_lances()
        releve._executer([sys.executable, "-c", "print(1)"], str(self.tmp))
        releve._executer([sys.executable, "-c", "import sys; sys.exit(3)"], str(self.tmp))
        self.assertEqual(len(crees), 2)
        for p in crees:
            self.assertTrue(p.stdout.closed and p.stderr.closed)

    def test_executer_trop_long_ferme_les_tubes(self):
        self._avec_delai_court()
        crees = self._processus_lances()
        with self.assertRaises(subprocess.TimeoutExpired):
            releve._executer([sys.executable, "-c", "import time; time.sleep(30)"], str(self.tmp))
        time.sleep(0.5)
        self.assertTrue(crees[0].stdout.closed and crees[0].stderr.closed)

    def test_obtenir_commande_trop_longue(self):
        self._avec_delai_court()
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        debut = time.monotonic()
        r, err = releve.obtenir(self.regl({"commande": cmd}))
        self.assertIsNone(r)
        self.assertIn("dépassé", err)
        self.assertLess(time.monotonic() - debut, 6)

    def test_obtenir_commande_dont_un_descendant_garde_la_sortie(self):
        # La commande lance un sous-processus qui hérite de sa sortie et dort : le délai doit tenir.
        self._avec_delai_court()
        enfant = "import time; time.sleep(30)"
        parent = ("import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', %r]); "
                  "time.sleep(30)") % enfant
        debut = time.monotonic()
        r, err = releve.obtenir(self.regl({"commande": [sys.executable, "-c", parent]}))
        self.assertIsNone(r)
        self.assertIn("dépassé", err)
        self.assertLess(time.monotonic() - debut, 6)

    def test_obtenir_fichier_avec_bom(self):
        (self.tmp / "r.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(BASE).encode("utf-8"))
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_commande_introuvable(self):
        r, err = releve.obtenir(self.regl({"commande": ["commande-qui-n-existe-pas"]}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_sans_source(self):
        r, err = releve.obtenir(self.regl({}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_exemple_demo_valide(self):
        d = json.loads((RACINE / "exemples" / "demo" / "releve.json").read_text(encoding="utf-8"))
        self.assertEqual(releve.valider(d), [])


class TestKpi(unittest.TestCase):
    def avec(self, *kpi, service=0):
        r = v3()
        r["services"] = [dict(x) for x in r["services"]] + [{"id": "qa", "nom": "QA"}]
        r["services"][service]["kpi"] = list(kpi)
        return r

    def test_kpi_projet_valide(self):
        k = {"id": "defauts", "nom": "Défauts passés", "valeur": 2, "unite": "défauts", "evolution": "+1 depuis hier",
             "alerte": True, "texte": "remises : passé 2 fois",
             "periodes": {"aujourdhui": 0, "7j": 2, "30j": "5"}}
        r = self.avec(k, {"id": "autre", "nom": "Autre", "valeur": "ok"})
        self.assertEqual(releve.valider(r), [])

    def test_kpi_id_double_dans_un_service(self):
        erreurs = releve.valider(self.avec({"id": "a", "nom": "A", "valeur": 1}, {"id": "a", "nom": "B", "valeur": 2}))
        self.assertTrue(any("kpi" in m for m in erreurs), erreurs)

    def test_kpi_ok_dans_deux_services(self):
        r = self.avec({"id": "a", "nom": "A", "valeur": 1})
        r["services"][1]["kpi"] = [{"id": "a", "nom": "A", "valeur": 1}]
        self.assertEqual(releve.valider(r), [])

    def test_kpi_mal_formes(self):
        for k in ({"nom": "A", "valeur": 1}, {"id": "", "nom": "A", "valeur": 1}, {"id": "a", "valeur": 1},
                  {"id": "a", "nom": "A"}, {"id": "a", "nom": "A", "valeur": True},
                  {"id": "a", "nom": "A", "valeur": None}, {"id": "a", "nom": "A", "valeur": float("inf")},
                  {"id": "a", "nom": "A", "valeur": 1, "unite": 3},
                  {"id": "a", "nom": "A", "valeur": 1, "evolution": 3},
                  {"id": "a", "nom": "A", "valeur": 1, "alerte": "oui"},
                  {"id": "a", "nom": "A", "valeur": 1, "texte": 3},
                  {"id": "a", "nom": "A", "valeur": 1, "periodes": []},
                  {"id": "a", "nom": "A", "valeur": 1, "periodes": {"1an": 3}},
                  {"id": "a", "nom": "A", "valeur": 1, "periodes": {"7j": True}}, 7):
            erreurs = releve.valider(self.avec(k))
            self.assertTrue(any("kpi" in m for m in erreurs), (k, erreurs))
        self.assertTrue(releve.valider(self.avec(service=0) | {"services": [{"id": "dev", "nom": "D", "kpi": 3}]}))

    def test_kpi_ignore_en_v2(self):
        r = self.avec({"id": "a", "valeur": 1})
        r["version"] = 2
        self.assertEqual(releve.valider(r), [])
        self.assertNotIn("kpi", releve.normaliser(r)["services"][0])

    def test_kpi_periodes_normalisees(self):
        n = releve.normaliser(self.avec({"id": "a", "nom": "A", "valeur": 1}))
        self.assertEqual(n["services"][0]["kpi"][0],
                         {"id": "a", "nom": "A", "valeur": 1, "unite": None, "evolution": None, "alerte": False,
                          "texte": None, "periodes": None})
        self.assertNotIn("kpi", n["services"][1])  # absent : reste absent


def v4(**champs):
    r = copy.deepcopy({**BASE, "version": 4})
    r.update(champs)
    return r


def fonc(**champs):
    f = {"id": "f1", "nom": "Ville", "etape": "cadrage"}
    f.update(champs)
    return f


def msg(**champs):
    m = {"id": "m1", "t": "2026-11-10T10:00:00", "auteur": "utilisateur", "texte": "Bonjour"}
    m.update(champs)
    return m


class TestVersion4(unittest.TestCase):
    def refus(self, r, mot):
        erreurs = releve.valider(r)
        self.assertTrue(erreurs, mot)
        self.assertTrue(any(mot in e for e in erreurs), (mot, erreurs))

    def test_version_4_minimale(self):
        self.assertEqual(releve.valider(v4()), [])

    def test_version_5_refusee(self):
        self.assertTrue(releve.valider({**BASE, "version": 5}))

    def test_v3_inchange(self):
        r = {**copy.deepcopy(BASE), "version": 3, "genre": "../x", "fonctionnalites": "n'importe quoi",
             "decisions_projet": 3, "livrable": 5}
        r["taches"][0].update(fonctionnalite=3, element=4, modele_depart=5, montee="x")
        self.assertEqual(releve.valider(r), [])
        n = releve.normaliser(r)
        for c in ("genre", "livrable", "fonctionnalites", "decisions_projet"):
            self.assertNotIn(c, n)
        for c in ("fonctionnalite", "element", "modele_depart", "montee"):
            self.assertNotIn(c, n["taches"][0])

    def test_genre_motif(self):
        for g in ("../x", "A", "", "x" * 41, "-a", 3):
            self.refus(v4(genre=g), "genre")
        for g in ("ville", "jeu-2d", "a", "x" * 40, None):
            self.assertEqual(releve.valider(v4(genre=g)), [], g)

    def test_livrable_lien_et_chemin_refuse(self):
        base = {"libelle": "L", "date": "2026-11-10"}
        self.refus(v4(livrable={**base, "lien": "https://x.fr/a", "chemin": "a.png"}), "livrable")
        self.refus(v4(livrable=base), "livrable")
        self.refus(v4(livrable={**base, "lien": "javascript:alert(1)"}), "livrable")
        self.refus(v4(livrable={"lien": "https://x.fr/a", "date": "d"}), "livrable")
        self.assertEqual(releve.valider(v4(livrable={**base, "lien": "https://x.fr/a"})), [])
        self.assertEqual(releve.valider(v4(livrable={**base, "chemin": "a.png"})), [])

    def test_fonctionnalite_etape_inconnue(self):
        self.refus(v4(fonctionnalites=[fonc(etape="rêve")]), "etape")
        for e in releve.ETAPES:
            self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(etape=e)])), [], e)

    def test_fonctionnalites_ids_doubles(self):
        self.refus(v4(fonctionnalites=[fonc(), fonc()]), "double")
        self.refus(v4(fonctionnalites=[fonc(id="")]), "id")

    def test_fonctionnalites_trop_nombreuses(self):
        self.refus(v4(fonctionnalites=[fonc(id=f"f{i}") for i in range(101)]), "fonctionnalites")

    def test_agent_cadrage(self):
        self.refus(v4(fonctionnalites=[fonc(agent_cadrage="zz")]), "agent_cadrage")
        self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(agent_cadrage="d1")])), [])
        self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(agent_cadrage=None)])), [])

    def test_message_auteur_inconnu(self):
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(auteur="zz")])]), "auteur")
        for a in ("utilisateur", "d1"):
            self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(discussion=[msg(auteur=a)])])), [], a)

    def test_message_champs(self):
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(), msg()])]), "double")
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(texte=3)])]), "texte")
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(t="hier")])]), "« t »")
        self.assertEqual(releve.valider(v4(fonctionnalites=[
            fonc(id="f1", discussion=[msg()]), fonc(id="f2", discussion=[msg()])])), [])  # ids par discussion

    def test_message_trop_nombreux(self):
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(id=f"m{i}") for i in range(1001)])]), "discussion")

    def test_message_cinq_images(self):
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(images=[f"a{i}.png" for i in range(5)])])]), "images")
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(images=[3])])]), "images")
        self.assertEqual(releve.valider(v4(fonctionnalites=[
            fonc(discussion=[msg(images=[f"a{i}.png" for i in range(4)])])])), [])

    def test_attend_reponse_et_catalogue_booleens(self):
        self.refus(v4(fonctionnalites=[fonc(attend_reponse="oui")]), "attend_reponse")
        self.refus(v4(fonctionnalites=[fonc(catalogue=1)]), "catalogue")

    def test_cahier_et_methode(self):
        self.refus(v4(fonctionnalites=[fonc(cahier={"maquette": "a.png", "etapes": []})]), "cahier")
        self.refus(v4(fonctionnalites=[fonc(cahier={"maquette": [], "etapes": [3]})]), "cahier")
        self.assertEqual(releve.valider(v4(fonctionnalites=[
            fonc(cahier={"maquette": ["a.png"], "etapes": ["un"], "valide_le": "2026-11-10"})])), [])
        self.refus(v4(fonctionnalites=[fonc(methode={"version": 0, "chemin": "m.md"})]), "methode")
        self.refus(v4(fonctionnalites=[fonc(methode={"version": 1})]), "methode")
        self.refus(v4(fonctionnalites=[fonc(methode={"version": 1, "chemin": "m", "lien": "https://x.fr"})]), "methode")
        self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(methode={"version": 2, "chemin": "m.md"})])), [])

    def test_orchestrateur_present(self):
        self.assertEqual(releve.valider(v4(orchestrateur_present=True)), [])
        self.assertEqual(releve.valider(v4(orchestrateur_present=False)), [])
        self.refus(v4(orchestrateur_present="oui"), "orchestrateur_present")

    def test_cahiers_precedents(self):
        ancien = {"maquette": ["a.png"], "etapes": ["un"], "remplace_le": "2026-11-11T10:00:00"}
        self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(cahiers_precedents=[ancien])])), [])
        self.refus(v4(fonctionnalites=[fonc(cahiers_precedents=[{"maquette": ["a.png"], "etapes": ["un"]}])]),
                   "cahiers_precedents")
        self.refus(v4(fonctionnalites=[fonc(cahiers_precedents={"x": 1})]), "cahiers_precedents")

    def test_livrable_de_fonctionnalite(self):
        self.refus(v4(fonctionnalites=[fonc(livrable={"libelle": "L", "date": "d"})]), "livrable")

    def test_decision_genre_inconnu(self):
        self.refus(v4(fonctionnalites=[fonc(decisions=[{"id": "d", "genre": "x", "texte": "T"}])]), "genre")
        for g in releve.DECISIONS_FONCTIONNALITE:
            extra = {"genre_fonctionnalite": {"propose": "jeu-mobile", "genres_connus": ["badges"], "incertain": False},
                     "environnement": {"environnement": [{"outil": "Java", "etat": "a_installer"}]}}.get(g, {})
            self.assertEqual(releve.valider(v4(fonctionnalites=[
                fonc(decisions=[{"id": "d", "genre": g, "texte": "T", **extra}])])), [], g)

    def test_decisions_ids_doubles_entre_fonctionnalite_et_projet(self):
        r = v4(fonctionnalites=[fonc(decisions=[{"id": "d", "genre": "valider_cahier", "texte": "T"}])],
               decisions_projet=[{"id": "d", "genre": "session_cloud", "texte": "T", "agent": "d1"}])
        self.refus(r, "double")

    def test_confirmer_genre_sans_propose(self):
        base = {"id": "g", "genre": "confirmer_genre", "texte": "T"}
        self.refus(v4(decisions_projet=[base]), "propose")
        self.refus(v4(decisions_projet=[{**base, "propose": "ville"}]), "genres_connus")
        self.refus(v4(decisions_projet=[{**base, "propose": "../x", "genres_connus": []}]), "propose")
        self.refus(v4(decisions_projet=[{**base, "propose": "ville", "genres_connus": ["A"]}]), "genres_connus")
        self.assertEqual(releve.valider(v4(decisions_projet=[
            {**base, "propose": "ville", "genres_connus": ["jeu"]}])), [])

    def test_session_cloud_agent_inconnu(self):
        base = {"id": "s", "genre": "session_cloud", "texte": "T"}
        self.refus(v4(decisions_projet=[{**base, "agent": "zz"}]), "agent")
        self.refus(v4(decisions_projet=[base]), "agent")
        self.assertEqual(releve.valider(v4(decisions_projet=[{**base, "agent": "d1"}])), [])

    def test_releve_decision_valider_etape(self):
        base = {"id": "v", "genre": "valider_etape", "texte": "Valider ?", "fonctionnalite": "f1",
                "element": {"id": "e1", "nom": "Accueil"}, "etape": "f1-valider", "tache": "t3",
                "compte_rendu": "Tout est vert.", "fichiers": [{"chemin": "pieces/a.png", "titre": "Capture"}]}
        self.assertEqual(releve.valider(v4(decisions_projet=[base])), [])
        self.assertEqual(releve.valider(v4(decisions_projet=[{k: v for k, v in base.items()
                                                                if k not in ("compte_rendu", "fichiers")}])), [])
        self.refus(v4(decisions_projet=[{k: v for k, v in base.items() if k != "element"}]), "element")
        self.refus(v4(decisions_projet=[{**base, "fichiers": [{"chemin": "a.png"}]}]), "fichiers")
        self.refus(v4(decisions_projet=[{**base, "compte_rendu": 3}]), "compte_rendu")
        colonnes = [{"id": "a", "nom": "A", "validation": True}]
        self.assertEqual(releve.valider(v4(colonnes=colonnes)), [])
        self.refus(v4(colonnes=[{"id": "a", "nom": "A", "validation": "oui"}]), "validation")

    def test_releve_decision_environnement_de_projet(self):
        base = {"id": "e", "genre": "environnement", "texte": "Il manque Java.",
                "environnement": [{"outil": "JDK 17", "etat": "a_installer"}]}
        self.assertEqual(releve.valider(v4(decisions_projet=[base])), [])
        self.refus(v4(decisions_projet=[{**base, "environnement": [{"etat": "a_installer"}]}]), "environnement")
        self.refus(v4(decisions_projet=[{k: v for k, v in base.items() if k != "environnement"}]), "environnement")

    def test_decision_organisation_valide(self):
        base = {"id": "o", "genre": "organisation", "texte": "Ajouter un service"}
        org = {"services": [{"id": "dev", "nom": "Dev"}, {"id": "son", "nom": "Son"}],
               "flux": [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}],
               "agents": [{"cle": "son-1", "role": "son", "service": "son", "modele": "Sonnet", "lieu": "local"}],
               "briefs": {"son": "# Brief"}, "cout": {"tokens": [1000, 2000], "euros": None}}
        self.assertEqual(releve.valider(v4(decisions_projet=[{**base, "organisation": org}])), [])
        self.assertEqual(releve.valider(v4(decisions_projet=[
            {**base, "organisation": {**org, "cout": {"tokens": [1000, 2000], "euros": [1.5, 3.0]}}}])), [])
        self.refus(v4(decisions_projet=[base]), "organisation")
        self.refus(v4(decisions_projet=[{**base, "organisation": {**org, "services": "dev"}}]), "services")
        self.refus(v4(decisions_projet=[{**base, "organisation": {**org, "cout": {"tokens": [3, 1]}}}]), "cout")

    def test_decision_organisation_fable_refuse(self):
        base = {"id": "o", "genre": "organisation", "texte": "T"}
        org = {"services": [{"id": "dev", "nom": "Dev"}], "flux": [], "briefs": {},
               "agents": [{"cle": "x-1", "role": "x", "service": "dev", "modele": "Fable", "lieu": "local"}],
               "cout": {"tokens": [1, 2], "euros": None}}
        self.refus(v4(decisions_projet=[{**base, "organisation": org}]), "Fable")

    def test_decision_projet_genre_inconnu(self):
        self.refus(v4(decisions_projet=[{"id": "s", "genre": "valider_cahier", "texte": "T"}]), "genre")

    def test_tache_fonctionnalite_inconnue(self):
        r = v4(fonctionnalites=[fonc()])
        r["taches"][0]["fonctionnalite"] = "zz"
        self.refus(r, "fonctionnalite")
        r["taches"][0]["fonctionnalite"] = "f1"
        self.assertEqual(releve.valider(r), [])

    def test_tache_champs_v4(self):
        r = v4()
        r["taches"][0]["element"] = 3
        self.refus(r, "element")
        r = v4()
        r["taches"][0]["modele_depart"] = 3
        self.refus(r, "modele_depart")
        r = v4()
        r["taches"][0]["montee"] = {"de": "Haiku", "a": "Sonnet"}
        self.refus(r, "montee")
        r["taches"][0]["montee"] = {"de": "Haiku", "a": "Sonnet", "raison": "trop dur"}
        self.assertEqual(releve.valider(r), [])

    def test_questions_a_choix(self):
        q = [{"texte": "Quelle taille ?", "choix": ["28 px", "56 px"]},
             {"texte": "Quels fonds ?", "choix": ["Clair", "Sombre", "Les deux"], "multiple": True}]
        m = msg(id="m2", auteur="d1", texte="Deux questions", questions=q)
        self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(discussion=[m])])), [])
        for mauvais in ("x", [{"choix": ["a", "b"]}], [{"texte": "T", "choix": ["a"]}],
                        [{"texte": "T", "choix": ["a", ""]}], [{"texte": "T", "choix": ["a", "b"], "multiple": "oui"}],
                        [{"texte": "T", "choix": [str(i) for i in range(13)]}],
                        [{"texte": "T", "choix": ["a", "b"]}] * 11):
            with self.subTest(mauvais):
                self.refus(v4(fonctionnalites=[fonc(discussion=[msg(id="m2", auteur="d1", texte="Q", questions=mauvais)])]),
                           "questions")

    def test_document_livrable(self):
        doc = {"chemin": "livrables/e1.png", "titre": "E1", "element": "e1", "livrable": True}
        self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(documents=[doc])])), [])
        self.refus(v4(fonctionnalites=[fonc(documents=[{**doc, "livrable": "oui"}])]), "livrable")

    def test_message_attend(self):
        ok = v4(fonctionnalites=[fonc(discussion=[msg(id="m2", auteur="d1", texte="Fait.", attend=False)])])
        self.assertEqual(releve.valider(ok), [])
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(id="m2", auteur="d1", texte="x", attend="non")])]), "attend")

    def test_glossaire(self):
        g = [{"mot": "Tesselle", "definition": "Petit cube de mosaïque."}]
        ok = v4(fonctionnalites=[fonc(glossaire=g, discussion=[msg(id="m2", auteur="d1", texte="x", glossaire=g)])])
        self.assertEqual(releve.valider(ok), [])
        for mauvais in ("x", [{"mot": "", "definition": "d"}], [{"mot": "m"}], [{"mot": "m" * 61, "definition": "d"}],
                        [{"mot": "m", "definition": "d" * 401}], [{"mot": "m", "definition": "d"}] * 501):
            with self.subTest(str(mauvais)[:40]):
                self.refus(v4(fonctionnalites=[fonc(glossaire=mauvais)]), "glossaire")
        self.refus(v4(fonctionnalites=[fonc(discussion=[msg(id="m2", auteur="d1", texte="x",
                                                            glossaire=[{"mot": "m"}])])]), "glossaire")

    def test_tache_lignes(self):
        r = v4()
        r["taches"][0]["lignes"] = 120
        self.assertEqual(releve.valider(r), [])
        for mauvais in (-1, 1.5, "120", True):
            r["taches"][0]["lignes"] = mauvais
            self.refus(r, "lignes")

    def test_lecon_genre_sans_texte_general(self):
        lecon = {"id": "l1", "agent": "d1", "texte": "T", "etage_propose": "genre"}
        self.refus(v4(lecons=[lecon]), "texte_general")
        self.refus(v4(lecons=[{**lecon, "texte_general": ""}]), "texte_general")
        self.refus(v4(lecons=[{**lecon, "etage_propose": "monde", "texte_general": "G"}]), "etage_propose")
        self.refus(v4(lecons=[{**lecon, "texte_general": "G", "roles": []}]), "roles")
        self.refus(v4(lecons=[{**lecon, "texte_general": "G", "roles": [3]}]), "roles")
        self.assertEqual(releve.valider(v4(lecons=[{**lecon, "texte_general": "G", "roles": ["dev"]}])), [])
        self.assertEqual(releve.valider(v4(lecons=[{**lecon, "etage_propose": "projet"}])), [])

    def test_lecon_de_titulaire(self):
        r = v4()
        r["titulaires"][0]["lecons"] = [{"id": "l", "texte": "T", "etat": "à valider", "etage_propose": "skill"}]
        self.refus(r, "texte_general")

    def test_normaliser_v4_defauts(self):
        r = v4(fonctionnalites=[fonc()], lecons=[{"id": "l1", "agent": "d1", "texte": "T"}])
        n = releve.normaliser(r)
        self.assertIsNone(n["genre"])
        self.assertIsNone(n["livrable"])
        self.assertEqual(n["decisions_projet"], [])
        f = n["fonctionnalites"][0]
        self.assertEqual((f["discussion"], f["decisions"], f["attend_reponse"], f["catalogue"]),
                         ([], [], False, False))
        for c in ("cahier", "methode", "livrable", "agent_cadrage"):
            self.assertIsNone(f[c], c)
        t = n["taches"][0]
        for c in ("fonctionnalite", "element", "modele_depart", "montee"):
            self.assertIsNone(t[c], c)
        le = n["lecons"][0]
        self.assertEqual((le["etage_propose"], le["texte_general"], le["roles"]), ("projet", None, ["tous"]))

    def test_documents_d_une_fonctionnalite(self):
        doc = {"chemin": "pieces/f1/maquette.png", "titre": "Maquette", "agent": "d1", "etape": "cahier",
               "tache": "t1", "element": "e1", "sous_tache": "rendu", "date": "2026-11-10T10:00:00+01:00"}
        self.assertEqual(releve.valider(v4(fonctionnalites=[fonc(documents=[doc, {"chemin": "a.md", "titre": "A"}])])), [])
        for mauvais in ([{"titre": "Sans chemin"}], [{"chemin": "a.png"}], [{"chemin": "/abs.png", "titre": "x"}],
                        [{"chemin": "a.png", "titre": "x", "agent": 3}], "pas une liste", [3]):
            with self.subTest(mauvais):
                self.assertTrue(releve.valider(v4(fonctionnalites=[fonc(documents=mauvais)])))
        self.assertEqual(releve.normaliser(v4(fonctionnalites=[fonc()]))["fonctionnalites"][0]["documents"], [])

    def test_normaliser_v4_sans_rien(self):
        n = releve.normaliser(v4())
        self.assertEqual((n["fonctionnalites"], n["decisions_projet"], n["genre"]), ([], [], None))

    def test_normaliser_v3_retire_les_champs_v4(self):
        n = releve.normaliser({**copy.deepcopy(BASE), "version": 3,
                               "lecons": [{"id": "l", "agent": "d1", "texte": "T", "etage_propose": "genre"}]})
        for c in ("etage_propose", "texte_general", "roles"):
            self.assertNotIn(c, n["lecons"][0])


class TestTilde(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def _home(self, nom="home"):
        home = self.tmp / nom
        home.mkdir()
        env = mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)})
        env.start()
        self.addCleanup(env.stop)
        return home

    def test_python_en_tete_est_celui_du_bureau(self):
        # « python » peut désigner un autre Python (3.9, le stub du Microsoft Store) : le bureau prend le sien
        for mot in ("python", "python3"):
            code, sortie, _ = releve._executer([mot, "-c", "import sys; print(sys.executable)"], str(self.tmp))
            self.assertEqual(code, 0)
            self.assertEqual(os.path.normcase(sortie.decode().strip()), os.path.normcase(sys.executable))
        self.assertEqual(releve.commande_python(["git", "python"]), ["git", "python"])

    def test_developper(self):
        home = self._home()
        for debut in ("~/", "~\\"):
            self.assertEqual(releve.developper(debut + "s"), os.path.expanduser(debut + "s"))
            self.assertTrue(releve.developper(debut + "s").startswith(str(home)))
        for texte in ("a~b", "~x", "x/~/y", "", "py"):
            self.assertEqual(releve.developper(texte), texte)

    def test_commande_releve_tilde(self):
        home = self._home()
        (home / "s").mkdir()
        (home / "s" / "ecrire.py").write_text("print('ecrit')", encoding="utf-8")
        code, sortie, _ = releve._executer([sys.executable, "~/s/ecrire.py"], str(self.tmp))
        self.assertEqual((code, sortie.strip()), (0, b"ecrit"))

    def test_tilde_espaces_accents(self):
        home = self._home("Zoé Martin")
        (home / "s").mkdir()
        (home / "s" / "ecrire.py").write_text("print('ok')", encoding="utf-8")
        code, sortie, _ = releve._executer([sys.executable, "~/s/ecrire.py"], str(self.tmp))
        self.assertEqual((code, sortie.strip()), (0, b"ok"))


class TestAgentsLocauxMax(unittest.TestCase):
    def test_agents_locaux_max_releve_v4(self):
        self.assertEqual(releve.valider(v4(agents_locaux_max=3)), [])
        self.assertEqual(releve.normaliser(v4(agents_locaux_max=3))["agents_locaux_max"], 3)
        self.assertIsNone(releve.normaliser(v4())["agents_locaux_max"])
        self.assertIsNone(releve.normaliser(v4(agents_locaux_max=None))["agents_locaux_max"])
        for mauvais in (0, -1, True, "2", 1.5, []):
            with self.subTest(mauvais):
                self.assertTrue(releve.valider(v4(agents_locaux_max=mauvais)))

    def test_agents_locaux_max_ignore_avant_v4(self):
        n = releve.normaliser({**copy.deepcopy(BASE), "version": 3, "agents_locaux_max": 3})
        self.assertNotIn("agents_locaux_max", n)



class TestPartenaires(unittest.TestCase):
    """Le champ facultatif `partenaires` (version 4) : l'espace partenaire du bureau."""

    def r(self, p=None, version=4):
        from tests.part_aide import partenaires_exemple
        return {**copy.deepcopy(BASE), "version": version, "partenaires": p if p is not None else partenaires_exemple()}

    def refus(self, p, mot):
        erreurs = releve.valider(self.r(p))
        self.assertTrue(any(mot in e for e in erreurs), (mot, erreurs))

    def test_releve_partenaires_valide(self):
        self.assertEqual(releve.valider(self.r()), [])
        n = releve.normaliser(self.r())
        self.assertEqual(n["partenaires"]["etat"]["limites"]["echo"]["raison"], "quota épuisé")

    def test_releve_partenaires_minimal(self):
        self.assertEqual(releve.valider(self.r({"categories": {}})), [])
        n = releve.normaliser(self.r({"categories": {}}))
        self.assertEqual(n["partenaires"]["etat"], {"connexions": {}, "quotas": {}, "limites": {}, "regles": {}})
        self.assertEqual((n["partenaires"]["conseils"], n["partenaires"]["maj_catalogue"], n["partenaires"]["cout_maj"]),
                         ({}, None, None))

    def test_releve_partenaires_id_inconnu(self):
        from tests.part_aide import partenaires_exemple
        for section in ("connexions", "quotas", "limites", "regles"):
            p = partenaires_exemple()
            p["etat"][section]["inconnu"] = copy.deepcopy(next(iter(p["etat"][section].values())))
            self.refus(p, "inconnu")
        p = partenaires_exemple()
        p["conseils"]["voix"].append({"id": "inconnu", "raison": "x"})
        self.refus(p, "inconnu")

    def test_releve_partenaires_mal_formes(self):
        from tests.part_aide import partenaires_exemple
        for modif, mot in (
                (lambda p: p["etat"]["connexions"]["vox"].update(etat="bof"), "etat"),
                (lambda p: p["etat"]["connexions"]["vox"].update(vu_le="hier"), "date"),
                (lambda p: p["etat"]["quotas"]["vox"].update(reste="beaucoup"), "reste"),
                (lambda p: p["etat"]["quotas"]["vox"].update(reste=True), "reste"),
                (lambda p: p["etat"]["quotas"]["vox"].update(lu_le="2026-99-99"), "date"),
                (lambda p: p["etat"]["limites"]["echo"].update(raison=3), "raison"),
                (lambda p: p["etat"]["regles"]["tripo"].append({"id": "r1", "texte": "x", "cree_le": "2026-11-11"}), "double"),
                (lambda p: p["etat"]["regles"]["tripo"][0].update(texte=""), "texte"),
                (lambda p: p["categories"]["voix-audio"][0].update(verifie_le="demain"), "date"),
                (lambda p: p["categories"]["voix-audio"].append({"id": "vox", "nom": "Bis"}), "double"),
                (lambda p: p["categories"]["voix-audio"][0].update(popularite={"niveau": 9, "base": "x", "date": "2026-11-12"}), "popularite"),
                (lambda p: p["categories"]["voix-audio"][0].update(description="  "), "description"),
                (lambda p: p["categories"].update({"voix-audio": "x"}), "categories"),
                (lambda p: p.update(maj_catalogue="bientôt"), "date"),
                (lambda p: p["conseils"].update(voix="x"), "conseils"),
                (lambda p: p.update(cout_maj={"euros": -1}), "cout_maj"),
                (lambda p: p.update(categories=[]), "categories")):
            p = partenaires_exemple()
            modif(p)
            self.refus(p, mot)
        self.assertTrue(releve.valider(self.r("x")))

    def test_partenaires_ignores_avant_la_version_4(self):
        r = self.r(version=3)
        self.assertEqual(releve.valider(r), [])
        self.assertNotIn("partenaires", releve.normaliser(r))


if __name__ == "__main__":
    unittest.main()
