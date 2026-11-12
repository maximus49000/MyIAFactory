"""L'échange avec le chef avant la création : les tours (faux `appeler`, aucun vrai modèle), la proposition calculée,
le tour en arrière-plan, puis la validation finale qui crée le projet (git et gh simulés)."""
import copy
import json
import threading
from datetime import datetime
from pathlib import Path

from installation import brouillons, definition
from installation.dossier import Echec
from moteur import appel
from tests.inst_aide import AvecMaison

GENRES = [{"id": "jeu-web", "domaine": "Jeux dans le navigateur", "livrable": "un site", "outils": ["node"]}]
INFOS = {"parent": "C:/x", "nom": "Casse-briques", "mots_interdits": ["secretcorp"], "facturation": False,
         "github": False, "description": "Un jeu de casse-briques pour téléphone."}
USAGE = {"modele": "sonnet", "entree": 2, "sortie": 600, "cache_lecture": 0, "cache_ecriture": 2700}
T0 = datetime(2026, 11, 12, 9, 0)

QUESTIONS = {"type": "questions", "message": "Quelques questions.",
             "questions": [{"id": "style", "texte": "Quel style ?", "choix": ["Néon", "Rétro"]},
                           {"id": "niveaux", "texte": "Combien de niveaux ?", "choix": []}]}


def proposition(**extra):
    o = {"type": "proposition", "message": "Voici le workflow.", "genre": None,
         "nouveau": {"id": "jeu-android", "description": "Un jeu pour Android livré en apk."},
         "flux": [{"etape": "dev", "nom": "Développement du jeu", "role": "dev", "service": "dev",
                   "raison": "Écrire le jeu."},
                  {"etape": "essai", "nom": "Essai de l'apk", "validation": True, "raison": "Vous l'essayez."},
                  {"etape": "livraison", "nom": "Livraison de l'apk", "role": "livreur", "service": "dev",
                   "raison": "Remettre l'apk."}],
         "services": [{"id": "dev", "nom": "Développement"}],
         "agents": [{"cle": "dev-1", "prenom": "Noé", "role": "dev", "service": "dev", "modele": "Sonnet",
                     "justification": "Il écrit du code.", "fable_suggere": False, "texte": "Tu écris le jeu."},
                    {"cle": "livreur-1", "role": "livreur", "service": "dev", "modele": "Haiku",
                     "justification": "Tâche mécanique.", "fable_suggere": False, "texte": "Tu remets l'apk."}],
         "briefs": {"dev": "Écris le code du jeu.", "livreur": "Remets l'apk."},
         "livrable": "Un apk signé",
         "environnement": [{"outil": "JDK", "version_min": "17", "pour": "dev", "executables": ["java"],
                            "installation": "winget install Microsoft.OpenJDK.17"}],
         "outils_installation": ["Bash(winget:*)"]}
    o.update(copy.deepcopy(extra))
    return o


class Faux:
    """Un faux `appeler` : rend les réponses dans l'ordre et note les dossiers reçus."""

    def __init__(self, *reponses, usage=USAGE):
        self.reponses, self.dossiers, self.usage = list(reponses), [], usage

    def __call__(self, consigne, dossier, modele, *, couche="claude", **_):
        self.dossiers.append(json.loads(dossier))
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return appel.Reponse(r if isinstance(r, str) else json.dumps(r), [dict(self.usage)])


def en_place(outils):
    return [dict(o, etat="en_place", chemin="C:/jdk/java.exe", version="java 21.0.2") for o in outils]


def a_installer(outils):
    return [dict(o, etat="a_installer") for o in outils]


def prix(modele):
    return {"entree": 3e-6, "sortie": 15e-6, "cache_lecture": 0.3e-6, "cache_ecriture": 3.75e-6}


class Base(AvecMaison):
    def setUp(self):
        super().setUp()
        self.d = self.base / "creations"
        brouillons._VIVANTS.clear()
        self.addCleanup(brouillons._VIVANTS.clear)

    def brouillon(self, **infos):
        return brouillons.creer(dict(INFOS, **infos), dossier=self.d, maintenant=T0)

    def tour(self, b, faux, **kw):
        kw.setdefault("genres_connus", GENRES)
        kw.setdefault("couche", "claude")
        kw.setdefault("verifier_environnement", a_installer)
        return definition.tour(b, appeler=faux, maintenant=T0, **kw)


class TestTour(Base):
    def test_premier_tour_pose_des_questions(self):
        faux = Faux(QUESTIONS)
        b = self.tour(self.brouillon(), faux)
        self.assertEqual(b["tours"], 1)
        self.assertEqual(b["echange"][-1]["auteur"], "chef")
        self.assertEqual([q["id"] for q in b["echange"][-1]["questions"]], ["style", "niveaux"])
        self.assertIsNone(b["proposition"])
        self.assertEqual(len(b["usages"]), 1)
        self.assertEqual(b["usages"][0]["t"], "2026-11-12T09:00:00")
        d = faux.dossiers[0]
        self.assertEqual((d["tours_de_questions"], d["tours_max"], d["proposer_maintenant"]), (0, 4, False))
        self.assertEqual(d["projet"]["nom"], "Casse-briques")
        self.assertEqual(d["mots_interdits"], ["secretcorp", "Casse-briques"])
        self.assertEqual(d["genres_connus"], GENRES)

    def test_reponses_ajoutees_avant_l_appel(self):
        b = self.tour(self.brouillon(), Faux(QUESTIONS))
        faux = Faux(proposition(genre="jeu-web", nouveau=None))
        b = self.tour(b, faux, reponses=[{"question": "style", "texte": "Néon"},
                                         {"question": "niveaux", "texte": " 10 "}])
        envoye = faux.dossiers[0]["echange"]
        self.assertEqual(envoye[-1], {"auteur": "utilisateur", "reponses": [
            {"question": "style", "texte": "Néon"}, {"question": "niveaux", "texte": "10"}]})
        self.assertEqual(envoye[0]["auteur"], "chef")
        self.assertEqual([e["auteur"] for e in b["echange"]], ["chef", "utilisateur", "chef"])
        self.assertEqual(b["tours"], 1)    # une proposition n'est pas un tour de questions

    def test_reponse_a_une_question_inconnue_refusee(self):
        b = self.tour(self.brouillon(), Faux(QUESTIONS))
        for mauvaises in ([{"question": "autre", "texte": "x"}], [{"question": "style", "texte": " "}], [],
                          [{"question": "style", "texte": "a"}, {"question": "style", "texte": "b"}]):
            with self.assertRaises(Echec, msg=repr(mauvaises)):
                self.tour(b, Faux(), reponses=mauvaises)
        with self.assertRaises(Echec):
            self.tour(self.brouillon(), Faux(), reponses=[{"question": "style", "texte": "x"}])   # rien n'est posé

    def test_cinquieme_appel_demande_la_proposition(self):
        b = self.brouillon()
        for _ in range(4):
            b = self.tour(b, Faux(QUESTIONS), reponses=[{"question": "style", "texte": "x"}] if b["echange"] else None)
        self.assertEqual(b["tours"], 4)
        faux = Faux(proposition())
        b = self.tour(b, faux, reponses=[{"question": "style", "texte": "Néon"}])
        self.assertIs(faux.dossiers[0]["proposer_maintenant"], True)
        self.assertEqual(faux.dossiers[0]["tours_de_questions"], 4)
        self.assertIsNotNone(b["proposition"])
        # Si le chef pose encore des questions au 5e appel, la validation refuse puis redemande : 2 appels, 1 proposition.
        b = self.brouillon()
        b["tours"] = 4
        faux = Faux(QUESTIONS, proposition())
        b = self.tour(b, faux)
        self.assertEqual(len(faux.dossiers), 2)
        self.assertIn("erreur_de_ta_reponse_precedente", faux.dossiers[1])
        self.assertIsNotNone(b["proposition"])
        self.assertEqual(b["tours"], 4)

    def test_proposer_maintenant(self):
        b = self.tour(self.brouillon(), Faux(QUESTIONS))
        faux = Faux(proposition())
        b = self.tour(b, faux, proposer_maintenant=True)
        self.assertIs(faux.dossiers[0]["proposer_maintenant"], True)
        self.assertIsNotNone(b["proposition"])

    def test_proposition_calculee_poste_et_cout(self):
        b = self.tour(self.brouillon(facturation=True), Faux(proposition()), verifier_environnement=a_installer,
                      prix_de=prix)
        p = b["proposition"]
        self.assertEqual(p["genre"], {"id": "jeu-android", "nouveau": True,
                                      "description": "Un jeu pour Android livré en apk."})
        self.assertEqual(p["workflow"]["id"], "w-jeu-android")
        self.assertEqual(p["workflow"]["flux"][1], {"id": "essai", "nom": "Essai de l'apk", "validation": True})
        self.assertEqual(p["workflow"]["flux"][0]["role"], "dev")
        self.assertEqual(p["raisons"]["essai"], "Vous l'essayez.")
        self.assertEqual([s["id"] for s in p["services"]], ["facturation", "dev"])
        cles = [a["cle"] for a in p["agents"]]
        self.assertEqual(cles, ["dev-1", "livreur-1", p["installateur"]])
        installateur = p["agents"][2]
        self.assertEqual((installateur["role"], installateur["service"], installateur["lieu"]),
                         ("environnement", "dev", "local"))
        self.assertIn("Bash(winget:*)", installateur["outils"])
        self.assertIn("Write", installateur["outils"])
        self.assertIn("environnement", p["briefs"])
        self.assertEqual(p["environnement"][0]["etat"], "a_installer")
        self.assertEqual(p["outils_installation"], ["Bash(winget:*)"])
        self.assertEqual(len(p["cout"]["tokens"]), 2)
        self.assertEqual(len(p["cout"]["euros"]), 2)     # les prix sont connus
        self.assertIn("À installer : JDK", p["texte"])
        self.assertIn("validation du Directeur", p["texte"])
        self.assertIn("Noé", p["texte"])
        self.assertIn("nouveau", p["texte"])
        # Poste en place : pas d'agent d'installation. Prix inconnus : pas d'euros.
        b = self.tour(self.brouillon(), Faux(proposition()), verifier_environnement=en_place)
        p = b["proposition"]
        self.assertIsNone(p["installateur"])
        self.assertEqual([a["cle"] for a in p["agents"]], ["dev-1", "livreur-1"])
        self.assertIsNone(p["cout"]["euros"])
        self.assertIn("Déjà en place sur le poste : JDK (java 21.0.2)", p["texte"])
        self.assertNotIn("facturation", [s["id"] for s in p["services"]])

    def test_validation_ne_coute_rien(self):
        avec = self.tour(self.brouillon(), Faux(proposition()), verifier_environnement=en_place)["proposition"]
        sans_flux = proposition(flux=[x for x in proposition()["flux"] if not x.get("validation")])
        sans = self.tour(self.brouillon(), Faux(sans_flux), verifier_environnement=en_place)["proposition"]
        self.assertEqual(avec["cout"], sans["cout"])

    def test_correction_hors_des_quatre_tours(self):
        b = self.tour(self.brouillon(), Faux(QUESTIONS))
        b = self.tour(b, Faux(proposition()), reponses=[{"question": "style", "texte": "x"}])
        self.assertEqual(b["tours"], 1)
        faux = Faux(proposition(message="Corrigé."))
        c = self.tour(b, faux, correction="Ajoute un essai avant la livraison.")
        d = faux.dossiers[0]
        self.assertEqual(d["correction"], "Ajoute un essai avant la livraison.")
        self.assertEqual(d["proposition_precedente"]["type"], "proposition")
        self.assertEqual(c["tours"], 1)
        self.assertEqual(c["proposition"]["message"], "Corrigé.")
        self.assertEqual(c["echange"][-2], {"auteur": "utilisateur", "correction": "Ajoute un essai avant la livraison."})
        # Une question en réponse à une correction est refusée par la validation (puis redemandée).
        faux = Faux(QUESTIONS, proposition())
        c = self.tour(b, faux, correction="Autre chose.")
        self.assertEqual(c["tours"], 1)
        self.assertEqual(len(faux.dossiers), 2)

    def test_tour_rate_ne_compte_pas(self):
        b = self.tour(self.brouillon(), Faux(QUESTIONS))
        avant = copy.deepcopy(b)
        faux = Faux("pas du json", "toujours pas")
        r = self.tour(b, faux, reponses=[{"question": "style", "texte": "Néon"}])
        self.assertEqual(r["tours"], 1)
        self.assertIsNone(r["proposition"])
        self.assertIn("Je n'ai pas réussi", r["erreur"])
        self.assertEqual(len(r["usages"]), len(avant["usages"]) + 2)   # son coût est compté
        self.assertEqual([e["auteur"] for e in r["echange"]], ["chef", "utilisateur"])
        # Un appel qui échoue pour de bon compte aussi ce qu'il a coûté.
        err = appel.ErreurAppel("réseau coupé", usages=[dict(USAGE)])
        r2 = self.tour(avant, Faux(err, err), reponses=[{"question": "style", "texte": "x"}])
        self.assertEqual(len(r2["usages"]), len(avant["usages"]) + 2)
        self.assertIn("réseau coupé", r2["erreur"])
        # Le tour suivant réussi efface l'erreur.
        ok = self.tour(r, Faux(proposition()))
        self.assertIsNone(ok["erreur"])

    def test_cout_echange_cumule(self):
        u = {"modele": "sonnet", "entree": 1000, "sortie": 100, "cache_lecture": 1000, "cache_ecriture": 2000}
        c = definition.cout_echange([u, u], prix)
        self.assertEqual(c["tokens"], 8200)
        un = 1000 * 3e-6 + 100 * 15e-6 + 1000 * 0.3e-6 + 2000 * 3.75e-6
        self.assertAlmostEqual(c["euros"], round(2 * un, 4), places=6)
        self.assertEqual(definition.cout_echange([u], lambda m: None), {"tokens": 4100, "euros": None})
        self.assertEqual(definition.cout_echange([], prix), {"tokens": 0, "euros": 0.0})

    def test_la_cle_n_est_jamais_dans_le_brouillon(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-secret-9876"}):
            b = self.tour(self.brouillon(), Faux(proposition()))
        brouillons.ecrire(b, dossier=self.d)
        self.assertNotIn("sk-ant", (self.d / f"{b['id']}.json").read_text(encoding="utf-8"))


class TestEnArriere(Base):
    def lancer(self, b, faux, **kw):
        kw.setdefault("genres_connus", GENRES)
        kw.setdefault("couche", "claude")
        kw.setdefault("verifier_environnement", a_installer)
        kw.setdefault("dossier", self.d)
        return definition.lancer_tour(b["id"], appeler=faux, maintenant=T0, **kw)

    def relire(self, b):
        return brouillons.lire(b["id"], dossier=self.d)

    def test_le_tour_repond_tout_de_suite_et_ecrit_le_resultat(self):
        b = self.brouillon()
        ouvert, libere = threading.Event(), threading.Event()

        def lent(consigne, dossier, modele, **kw):
            ouvert.set()
            libere.wait(10)
            return appel.Reponse(json.dumps(QUESTIONS), [dict(USAGE)])
        vu = self.lancer(b, lent)
        self.assertTrue(ouvert.wait(10))
        self.assertEqual(vu["en_cours"]["depuis"], "2026-11-12T09:00:00")
        self.assertEqual(definition.vue(self.relire(b))["tour"], "en_cours")
        self.assertIsNone(definition.vue(self.relire(b))["erreur"])
        libere.set()
        self.assertTrue(definition.attendre(b["id"]))
        fini = self.relire(b)
        self.assertIsNone(fini["en_cours"])
        self.assertEqual((fini["tours"], definition.vue(fini)["tour"]), (1, "libre"))
        self.assertEqual(len(fini["usages"]), 1)

    def test_tour_deja_en_cours_refuse(self):
        b = self.brouillon()
        ouvert, libere = threading.Event(), threading.Event()
        appels = []

        def lent(consigne, dossier, modele, **kw):
            appels.append(1)
            ouvert.set()
            libere.wait(10)
            return appel.Reponse(json.dumps(QUESTIONS), [dict(USAGE)])
        self.lancer(b, lent)
        self.assertTrue(ouvert.wait(10))
        with self.assertRaises(brouillons.TourEnCours):
            self.lancer(b, lent)
        with self.assertRaises(brouillons.TourEnCours):
            self.lancer(b, lent, proposer_maintenant=True)
        with self.assertRaises(brouillons.TourEnCours):
            brouillons.abandonner(b["id"], dossier=self.d, commun=self.base / "u.jsonl")
        libere.set()
        definition.attendre(b["id"])
        self.assertEqual(len(appels), 1)
        self.assertEqual(len(self.relire(b)["usages"]), 1)    # rien n'est compté deux fois

    def test_les_reponses_sont_gardees_des_le_lancement(self):
        b = self.brouillon()
        self.lancer(b, Faux(QUESTIONS), en_arriere=False)
        ouvert, libere = threading.Event(), threading.Event()

        def lent(consigne, dossier, modele, **kw):
            ouvert.set()
            libere.wait(10)
            return appel.Reponse(json.dumps(proposition()), [dict(USAGE)])
        self.lancer(b, lent, reponses=[{"question": "style", "texte": "Néon"}])
        ouvert.wait(10)
        self.assertEqual(self.relire(b)["echange"][-1]["auteur"], "utilisateur")    # la page les voit déjà
        libere.set()
        definition.attendre(b["id"])
        self.assertIsNotNone(self.relire(b)["proposition"])

    def test_un_envoi_incoherent_ne_lance_rien(self):
        b = self.brouillon()
        self.lancer(b, Faux(QUESTIONS), en_arriere=False)
        for kw in ({}, {"correction": "x"}, {"reponses": [{"question": "zz", "texte": "x"}]}):
            with self.assertRaises(Echec, msg=repr(kw)):
                self.lancer(b, Faux(), **kw)
            self.assertIsNone(self.relire(b)["en_cours"])
            self.assertEqual(brouillons.etat_du_tour(self.relire(b)), "libre")
        self.lancer(b, Faux(proposition()), proposer_maintenant=True, en_arriere=False)
        with self.assertRaises(Echec):
            self.lancer(b, Faux())      # une proposition est prête : il faut une correction
        with self.assertRaises(Echec):
            self.lancer(b, Faux(), correction="x" * 3000)

    def test_erreur_imprevue_ne_bloque_pas(self):
        b = self.brouillon()

        def casse(consigne, dossier, modele, **kw):
            raise FileNotFoundError("claude introuvable")
        self.lancer(b, casse)
        definition.attendre(b["id"])
        lu = self.relire(b)
        self.assertIsNone(lu["en_cours"])
        self.assertIn("claude introuvable", lu["erreur"])
        self.assertEqual(brouillons.etat_du_tour(lu), "libre")
        self.lancer(b, Faux(QUESTIONS), en_arriere=False)      # on peut renvoyer
        self.assertEqual(self.relire(b)["tours"], 1)

    def test_tour_rate_renvoye_avec_sa_correction(self):
        b = self.brouillon()
        self.lancer(b, Faux(proposition()), proposer_maintenant=True, en_arriere=False)
        r = self.lancer(b, Faux("rien", "rien"), correction="Ajoute un essai.", en_arriere=False)
        self.assertIn("Je n'ai pas réussi", r["erreur"])
        faux = Faux(proposition(message="Avec essai."))
        r = self.lancer(b, faux, en_arriere=False)       # renvoyer sans rien retaper
        self.assertEqual(faux.dossiers[0]["correction"], "Ajoute un essai.")
        self.assertEqual(r["proposition"]["message"], "Avec essai.")
        self.assertIsNone(r["erreur"])

    def test_tour_interrompu_par_un_redemarrage(self):
        b = self.brouillon()
        self.lancer(b, Faux(proposition()), proposer_maintenant=True, en_arriere=False)
        # Le bureau est relancé pendant un tour : le fichier dit « en cours », plus rien ne tourne.
        interrompu = self.relire(b)
        interrompu["en_cours"] = {"depuis": "2026-11-12T09:00:00", "correction": "Plus court."}
        brouillons.ecrire(interrompu, dossier=self.d)
        brouillons._VIVANTS.clear()
        v = definition.vue(self.relire(b))
        self.assertEqual(v["tour"], "interrompu")
        self.assertIn("interrompu", v["erreur"])
        faux = Faux(proposition(message="Plus court."))
        r = self.lancer(b, faux, en_arriere=False)       # renvoyer reprend la demande interrompue
        self.assertEqual(faux.dossiers[0]["correction"], "Plus court.")
        self.assertEqual(r["proposition"]["message"], "Plus court.")
        self.assertEqual(brouillons.etat_du_tour(r), "libre")
        self.assertIn(b["id"], [x["id"] for x in brouillons.lister(dossier=self.d)])

    def test_vue(self):
        b = self.brouillon()
        self.lancer(b, Faux(QUESTIONS), en_arriere=False)
        v = definition.vue(self.relire(b), prix)
        self.assertEqual(sorted(v), ["cout", "echange", "en_cours", "erreur", "id", "infos", "proposition", "tour",
                                     "tours", "tours_max"])
        self.assertEqual((v["tours"], v["tours_max"], v["tour"]), (1, 4, "libre"))
        self.assertGreater(v["cout"]["tokens"], 0)
        self.assertIsNotNone(v["cout"]["euros"])
