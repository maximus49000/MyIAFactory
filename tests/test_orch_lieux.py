"""Découper un workflow selon le poste (conception 2026-11-13-etapes-locales-design.md) : la validation stricte d'une
proposition (filet de sécurité d'un projet en production : un test par cas refusé), son application à tous les
workflows du projet, par identifiant d'étape, rejouable, sans toucher aucune tâche. Aucun appel réel."""
import copy
import json
import unittest

from orchestrateur import lieux
from tests.orch_aide import AvecProjet

FLUX = [{"id": "conception", "nom": "Conception", "role": "designer", "service": "dev"},
        {"id": "valid-design", "nom": "Validation du design", "validation": True},
        {"id": "prototype", "nom": "Prototype jouable", "role": "dev", "service": "dev", "modele": "Opus",
         "justification": "Cœur du jeu."},
        {"id": "tests", "nom": "Tests sur émulateur", "role": "qa", "service": "dev"},
        {"id": "livraison", "nom": "Livraison de l'apk", "role": "release", "service": "dev"}]


def decoupee(flux=FLUX):
    """La proposition type : le prototype découpé (code dans le cloud, puis mise en place et tests sur le poste), les
    tests sur émulateur locaux, la conception sans poste."""
    sortie = []
    for e in copy.deepcopy(flux):
        if e["id"] == "prototype":
            sortie.append(dict(e, nom="Prototype jouable : code", lieu="indifférent"))
            sortie.append({"id": "prototype-local", "nom": "Prototype jouable : mise en place et tests", "role": "dev",
                           "service": "dev", "lieu": "local"})
        elif e["id"] == "tests":
            sortie.append(dict(e, lieu="local"))
        elif e["id"] == "conception":
            sortie.append(dict(e, lieu="indifférent"))
        else:
            sortie.append(e)
    return sortie


class Verifier(unittest.TestCase):
    def refuse(self, propose, flux=FLUX):
        erreur = lieux.verifier_proposition(flux, propose)
        self.assertIsInstance(erreur, str)
        self.assertTrue(erreur.strip())

    def test_insertion_de_la_partie_locale_acceptee(self):
        self.assertIsNone(lieux.verifier_proposition(FLUX, decoupee()))

    def test_seul_le_lieu_change_accepte(self):
        self.assertIsNone(lieux.verifier_proposition(FLUX, [dict(e, lieu="local") if e["id"] == "tests" else e
                                                            for e in FLUX]))
        self.assertIsNone(lieux.verifier_proposition(FLUX, copy.deepcopy(FLUX)))

    def test_pas_une_liste_refusee(self):
        self.refuse({"flux": FLUX})
        self.refuse([])
        self.refuse(["prototype"])

    def test_suppression_refusee(self):
        self.refuse([e for e in decoupee() if e["id"] != "livraison"])

    def test_suppression_d_une_validation_refusee(self):
        self.refuse([e for e in decoupee() if e["id"] != "valid-design"])

    def test_renommage_refuse(self):
        self.refuse([dict(e, nom="Recette") if e["id"] == "tests" else e for e in decoupee()])

    def test_renommage_d_une_validation_refuse(self):
        self.refuse([dict(e, nom="Essai") if e["id"] == "valid-design" else e for e in decoupee()])

    def test_changement_d_identifiant_refuse(self):
        self.refuse([dict(e, id="essais") if e["id"] == "tests" else e for e in decoupee()])

    def test_reordre_refuse(self):
        p = decoupee()
        i, j = next(k for k, e in enumerate(p) if e["id"] == "tests"), next(k for k, e in enumerate(p)
                                                                              if e["id"] == "livraison")
        p[i], p[j] = p[j], p[i]
        self.refuse(p)

    def test_role_change_refuse(self):
        self.refuse([dict(e, role="dev") if e["id"] == "tests" else e for e in decoupee()])

    def test_service_change_refuse(self):
        self.refuse([dict(e, service="art") if e["id"] == "tests" else e for e in decoupee()])

    def test_modele_change_refuse(self):
        self.refuse([dict(e, modele="Haiku") if e["id"] == "prototype" else e for e in decoupee()])

    def test_nature_changee_refusee(self):
        self.refuse([{"id": "tests", "nom": "Tests sur émulateur", "validation": True} if e["id"] == "tests" else e
                     for e in decoupee()])

    def test_lieu_inconnu_refuse(self):
        self.refuse([dict(e, lieu="ailleurs") if e["id"] == "tests" else e for e in decoupee()])

    def test_lieu_sur_une_validation_refuse(self):
        self.refuse([dict(e, lieu="local") if e["id"] == "valid-design" else e for e in decoupee()])

    def test_regroupement_propose_accepte(self):
        """Le Chef peut rendre « regroupe » pour une étape qui modifie des fichiers communs : seul le regroupement change."""
        p = [dict(e, regroupement="regroupe") if e["id"] == "tests" else e for e in decoupee()]
        self.assertIsNone(lieux.verifier_proposition(FLUX, p))
        p = [dict(e, regroupement="regroupe") if e["id"] == "prototype" else e for e in decoupee()]
        self.assertIsNone(lieux.verifier_proposition(FLUX, p))             # une étape découpée aussi

    def test_regroupement_inconnu_ou_sur_une_validation_refuse(self):
        self.refuse([dict(e, regroupement="tous") if e["id"] == "tests" else e for e in decoupee()])
        self.refuse([dict(e, regroupement="regroupe") if e["id"] == "valid-design" else e for e in decoupee()])

    def test_une_proposition_qui_oublie_le_regroupement_n_est_pas_refusee(self):
        flux = [dict(e, regroupement="regroupe") if e["id"] == "tests" else e for e in FLUX]
        self.assertIsNone(lieux.verifier_proposition(flux, decoupee()))

    def test_etape_inventee_refusee(self):
        p = decoupee()
        p.insert(1, {"id": "maquette", "nom": "Maquette", "role": "designer", "service": "dev", "lieu": "local"})
        self.refuse(p)

    def test_partie_locale_pas_juste_apres_refusee(self):
        p = decoupee()
        local = p.pop(next(k for k, e in enumerate(p) if e["id"] == "prototype-local"))
        p.append(local)
        self.refuse(p)

    def test_partie_locale_d_une_validation_refusee(self):
        p = decoupee()
        k = next(k for k, e in enumerate(p) if e["id"] == "valid-design")
        p.insert(k + 1, {"id": "valid-design-local", "nom": "x", "role": "dev", "service": "dev", "lieu": "local"})
        self.refuse(p)

    def test_partie_locale_d_un_autre_role_refusee(self):
        self.refuse([dict(e, role="qa") if e["id"] == "prototype-local" else e for e in decoupee()])

    def test_partie_locale_d_un_autre_service_refusee(self):
        self.refuse([dict(e, service="art") if e["id"] == "prototype-local" else e for e in decoupee()])

    def test_partie_locale_pas_locale_refusee(self):
        self.refuse([dict(e, lieu="indifférent") if e["id"] == "prototype-local" else e for e in decoupee()])

    def test_partie_locale_validation_refusee(self):
        self.refuse([{"id": "prototype-local", "nom": "x", "validation": True} if e["id"] == "prototype-local" else e
                     for e in decoupee()])

    def test_partie_locale_sans_nom_refusee(self):
        self.refuse([dict(e, nom=" ") if e["id"] == "prototype-local" else e for e in decoupee()])

    def test_partie_code_sans_lieu_indifferent_refusee(self):
        self.refuse([dict(e, lieu="local") if e["id"] == "prototype" else e for e in decoupee()])
        p = decoupee()
        del next(e for e in p if e["id"] == "prototype")["lieu"]
        self.refuse(p)

    def test_partie_code_sans_nom_refusee(self):
        self.refuse([dict(e, nom="") if e["id"] == "prototype" else e for e in decoupee()])

    def test_etape_deja_decoupee_pas_redecoupee(self):
        deja = lieux.appliquer(FLUX, decoupee())
        p = decoupee(deja)       # la partie locale existe : une seconde insertion est un doublon
        self.refuse(p, flux=deja)
        self.assertIsNone(lieux.verifier_proposition(deja, deja))

    def test_partie_locale_jamais_redecoupee(self):
        deja = lieux.appliquer(FLUX, decoupee())
        p = copy.deepcopy(deja)
        k = next(k for k, e in enumerate(p) if e["id"] == "prototype-local")
        p[k]["lieu"] = "indifférent"
        p.insert(k + 1, {"id": "prototype-local-local", "nom": "x", "role": "dev", "service": "dev", "lieu": "local"})
        self.refuse(p, flux=deja)

    def test_doublon_refuse(self):
        p = decoupee()
        p.append(dict(p[-1]))
        self.refuse(p)

    def test_identifiant_trop_long_refuse(self):
        long_ = "a" * 36
        flux = [{"id": long_, "nom": "Long", "role": "dev", "service": "dev"}]
        self.refuse([dict(flux[0], nom="Long : code", lieu="indifférent"),
                     {"id": f"{long_}-local", "nom": "Long : mise en place", "role": "dev", "service": "dev",
                      "lieu": "local"}], flux=flux)


class Appliquer(unittest.TestCase):
    def test_insere_la_partie_locale_apres_le_code(self):
        sortie = lieux.appliquer(FLUX, decoupee())
        self.assertEqual([e["id"] for e in sortie], ["conception", "valid-design", "prototype", "prototype-local",
                                                     "tests", "livraison"])
        code, local = sortie[2], sortie[3]
        self.assertEqual((code["nom"], code["lieu"], code["modele"]), ("Prototype jouable : code", "indifférent", "Opus"))
        self.assertEqual((local["nom"], local["role"], local["service"], local["lieu"]),
                         ("Prototype jouable : mise en place et tests", "dev", "dev", "local"))
        self.assertEqual(sortie[4]["lieu"], "local")
        self.assertNotIn("lieu", sortie[5])

    def test_rien_n_est_modifie_en_place(self):
        avant = copy.deepcopy(FLUX)
        p = decoupee()
        lieux.appliquer(FLUX, p)
        self.assertEqual(FLUX, avant)
        self.assertEqual(p, decoupee())

    def test_appliquer_deux_fois_egale_une_fois(self):
        une = lieux.appliquer(FLUX, decoupee())
        self.assertEqual(lieux.appliquer(une, decoupee()), une)

    def test_copie_decoupee_par_identifiant(self):
        copie = [dict(e, id=f"f1-{e['id']}") for e in FLUX]
        sortie = lieux.appliquer(copie, decoupee(), prefixe="f1-")
        self.assertEqual([e["id"] for e in sortie], ["f1-conception", "f1-valid-design", "f1-prototype",
                                                     "f1-prototype-local", "f1-tests", "f1-livraison"])
        self.assertEqual(sortie[3]["lieu"], "local")
        self.assertEqual(lieux.appliquer(sortie, decoupee(), prefixe="f1-"), sortie)

    def test_etape_inconnue_de_la_proposition_gardee(self):
        flux = FLUX + [{"id": "bonus", "nom": "Bonus", "role": "dev", "service": "dev"}]
        self.assertEqual(lieux.appliquer(flux, decoupee())[-1], flux[-1])

    def test_regroupement_pose_garde_ou_retire(self):
        propose = [dict(e, regroupement="regroupe") if e["id"] == "tests" else e for e in decoupee()]
        une = lieux.appliquer(FLUX, propose)
        self.assertEqual(next(e for e in une if e["id"] == "tests")["regroupement"], "regroupe")
        self.assertEqual(lieux.appliquer(une, propose), une)                      # rejouable sans effet
        self.assertEqual(next(e for e in lieux.appliquer(une, decoupee()) if e["id"] == "tests")["regroupement"],
                         "regroupe")                                              # une proposition muette le garde
        parallele = [dict(e, regroupement="parallele") if e["id"] == "tests" else e for e in decoupee()]
        self.assertNotIn("regroupement", next(e for e in lieux.appliquer(une, parallele) if e["id"] == "tests"))

    def test_lieu_retire_si_la_proposition_n_en_a_plus(self):
        une = lieux.appliquer(FLUX, decoupee())
        sans = [dict(e) for e in une]
        del next(e for e in sans if e["id"] == "tests")["lieu"]
        self.assertNotIn("lieu", next(e for e in lieux.appliquer(une, sans) if e["id"] == "tests"))


class Suggestions(unittest.TestCase):
    ENV = [{"outil": "Godot 4", "pour": "prototype", "objectif": "Exporter l'apk aux étapes prototype, contenu et build."},
           {"outil": "JDK", "pour": "livraison"},
           {"outil": "SDK Android", "pour": "Tests sur émulateur", "objectif": "Lancer l'AVD sans fenêtre."}]

    def test_outils_pour_et_objectif(self):
        self.assertEqual(lieux.etapes_locales_suggerees(FLUX, self.ENV), {"prototype", "livraison", "tests"})

    def test_sans_environnement(self):
        self.assertEqual(lieux.etapes_locales_suggerees(FLUX, []), set())
        self.assertEqual(lieux.etapes_locales_suggerees(FLUX, None), set())

    def test_exige_le_poste_passe_a_la_partie_locale_d_une_etape_decoupee(self):
        env = [{"outil": "Godot 4", "pour": "prototype"}, {"outil": "JDK", "pour": "livraison", "cloud": True}]
        self.assertEqual(lieux.etapes_qui_exigent_le_poste(FLUX, env), {"prototype"})
        decoupe = [dict(e) for e in FLUX]
        k = next(i for i, e in enumerate(decoupe) if e["id"] == "prototype")
        decoupe.insert(k + 1, dict(decoupe[k], id="prototype-local", nom="Prototype : mise en place et tests"))
        self.assertEqual(lieux.etapes_qui_exigent_le_poste(decoupe, env), {"prototype-local"})

    def test_jamais_une_validation(self):
        env = [{"outil": "x", "pour": "valid-design", "objectif": "Validation du design"}]
        self.assertEqual(lieux.etapes_locales_suggerees(FLUX, env), set())


class Commande(AvecProjet):
    """La commande `lieux` : `decouper` sur tous les workflows du projet, `regler` une étape ; aucune tâche touchée."""

    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = []
        f["workflows"] = [{"id": "w-jeu", "fonctionnalite": None, "genre": "jeu", "flux": FLUX},
                          {"id": "w-f1", "fonctionnalite": "f1", "genre": "jeu",
                           "flux": [dict(e, id=f"f1-{e['id']}") for e in FLUX]},
                          {"id": "w-f2", "fonctionnalite": "f2", "genre": "jeu",
                           "flux": [dict(e, id=f"f2-{e['id']}") for e in FLUX]}]
        f["consignes_maison"] = "gardée"     # une clé inconnue du fichier reste telle quelle
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("tache", entree={"titre": "Proto", "fonctionnalite": "f1", "colonne": "f1-prototype",
                                 "etape": "flux:f1-prototype", "element": "e1", "role": "dev", "active": False})

    def lu(self):
        return json.loads(self.factory.read_text(encoding="utf-8"))

    def suivi(self):
        return (self.dossier / "suivi.json").read_bytes()

    def test_reference_decrit_les_workflows_du_projet(self):
        r = self.ok("lieux", entree={"action": "reference"})
        self.assertEqual([e["id"] for e in r["flux"]], [e["id"] for e in FLUX])

    def test_decouper_tous_les_workflows(self):
        avant = self.suivi()
        r = self.ok("lieux", entree={"action": "decouper", "flux": decoupee()})
        self.assertTrue(r["change"])
        d = self.lu()
        for w, p in (("w-jeu", ""), ("w-f1", "f1-"), ("w-f2", "f2-")):
            ids = [e["id"] for e in next(x for x in d["workflows"] if x["id"] == w)["flux"]]
            self.assertIn(f"{p}prototype-local", ids)
            self.assertEqual(ids.index(f"{p}prototype-local"), ids.index(f"{p}prototype") + 1)
        self.assertEqual(d["consignes_maison"], "gardée")
        self.assertEqual(self.suivi(), avant)       # aucune tâche touchée

    def test_decouper_rejoue_sans_effet(self):
        self.ok("lieux", entree={"action": "decouper", "flux": decoupee()})
        une = self.factory.read_bytes()
        r = self.ok("lieux", entree={"action": "decouper", "flux": decoupee()})
        self.assertFalse(r["change"])
        self.assertEqual(self.factory.read_bytes(), une)

    def test_decouper_refuse_une_proposition_invalide(self):
        avant = self.factory.read_bytes()
        code, r = self.outil("lieux", entree={"action": "decouper", "flux": decoupee()[:-1]})
        self.assertNotEqual(code, 0)
        self.assertEqual(self.factory.read_bytes(), avant)

    def test_regler_une_etape_dans_tous_les_workflows(self):
        avant = self.suivi()
        self.ok("lieux", entree={"action": "regler", "etape": "tests", "lieu": "local"})
        d = self.lu()
        lieux_ = [e.get("lieu") for w in d["workflows"] for e in w["flux"] if e["id"].endswith("tests")]
        self.assertEqual(lieux_, ["local"] * 3)
        self.ok("lieux", entree={"action": "regler", "etape": "tests", "lieu": None})
        self.assertNotIn("lieu", next(e for e in self.lu()["workflows"][1]["flux"] if e["id"] == "f1-tests"))
        self.assertEqual(self.suivi(), avant)

    def test_regler_refuse_une_validation_ou_un_lieu_inconnu(self):
        for entree in ({"etape": "valid-design", "lieu": "local"}, {"etape": "tests", "lieu": "ailleurs"},
                       {"etape": "inconnue", "lieu": "local"}):
            with self.subTest(entree=entree):
                code, _ = self.outil("lieux", entree={"action": "regler", **entree})
                self.assertNotEqual(code, 0)

    def test_regler_cloud_possible_sauf_si_l_etape_exige_le_poste(self):
        """Choix du Directeur : local, cloud ou indifférent ; une étape qui exige les logiciels du poste reste locale."""
        self.ok("lieux", entree={"action": "regler", "etape": "tests", "lieu": "cloud"})
        self.assertEqual(next(e for e in self.lu()["workflows"][0]["flux"] if e["id"] == "tests")["lieu"], "cloud")
        f = self.lu()
        f["environnement"] = [{"outil": "Godot 4", "pour": "prototype"}]
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for lieu in ("cloud", "indifférent"):
            code, _ = self.outil("lieux", entree={"action": "regler", "etape": "prototype", "lieu": lieu})
            self.assertNotEqual(code, 0)
        self.ok("lieux", entree={"action": "regler", "etape": "prototype", "lieu": "local"})
        f = self.lu()
        f["environnement"] = [{"outil": "Godot 4", "pour": "prototype", "cloud": True}]   # le cloud sait l'installer
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.ok("lieux", entree={"action": "regler", "etape": "prototype", "lieu": "cloud"})

    def test_regrouper_une_etape_dans_tous_les_workflows(self):
        avant = self.suivi()
        r = self.ok("lieux", entree={"action": "regrouper", "etape": "tests", "regroupement": "regroupe"})
        self.assertTrue(r["change"])
        d = self.lu()
        self.assertEqual([e.get("regroupement") for w in d["workflows"] for e in w["flux"] if e["id"].endswith("tests")],
                         ["regroupe"] * 3)
        self.assertEqual([e.get("regroupement") for e in d["workflows"][0]["flux"] if not e["id"].endswith("tests")],
                         [None] * 4)
        self.assertFalse(self.ok("lieux", entree={"action": "regrouper", "etape": "tests",
                                                  "regroupement": "regroupe"})["change"])
        self.ok("lieux", entree={"action": "regrouper", "etape": "tests", "regroupement": "parallele"})
        self.assertNotIn("regroupement", next(e for e in self.lu()["workflows"][1]["flux"] if e["id"] == "f1-tests"))
        self.assertEqual(self.suivi(), avant)

    def test_regrouper_refuse_une_validation_une_valeur_ou_une_etape_inconnue(self):
        for entree in ({"etape": "valid-design", "regroupement": "regroupe"}, {"etape": "tests", "regroupement": "tous"},
                       {"etape": "tests", "regroupement": None}, {"etape": "inconnue", "regroupement": "regroupe"}):
            with self.subTest(entree=entree):
                avant = self.factory.read_bytes()
                code, _ = self.outil("lieux", entree={"action": "regrouper", **entree})
                self.assertNotEqual(code, 0)
                self.assertEqual(self.factory.read_bytes(), avant)

    def test_regrouper_ne_touche_pas_au_lieu_et_inversement(self):
        self.ok("lieux", entree={"action": "regler", "etape": "tests", "lieu": "local"})
        self.ok("lieux", entree={"action": "regrouper", "etape": "tests", "regroupement": "regroupe"})
        self.ok("lieux", entree={"action": "regler", "etape": "tests", "lieu": None})
        e = next(e for e in self.lu()["workflows"][0]["flux"] if e["id"] == "tests")
        self.assertEqual(e.get("regroupement"), "regroupe")
        self.assertNotIn("lieu", e)

    def test_le_releve_dit_le_regroupement_de_chaque_etape(self):
        self.ok("lieux", entree={"action": "regrouper", "etape": "tests", "regroupement": "regroupe"})
        etapes = {e["id"]: e for e in self.ok("releve")["etapes_lieux"]}
        self.assertEqual(etapes["tests"]["regroupement"], "regroupe")
        self.assertEqual(etapes["conception"]["regroupement"], "parallele")
        self.assertEqual(etapes["valid-design"]["regroupement"], "parallele")

    def test_factory_refuse_un_regroupement_invalide(self):
        for e in ({"id": "tests", "nom": "T", "role": "qa", "service": "dev", "regroupement": "tous"},
                  {"id": "tests", "nom": "T", "validation": True, "regroupement": "regroupe"}):
            f = self.lu()
            f["workflows"][0]["flux"] = [e]
            self.factory.write_text(json.dumps(f), encoding="utf-8")
            with self.assertRaises(lieux.fa.FactoryInvalide):
                lieux.fa.lire(self.factory)

    def test_action_inconnue_refusee(self):
        code, _ = self.outil("lieux", entree={"action": "tout"})
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
