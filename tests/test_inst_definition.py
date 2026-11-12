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
                            "installation": "winget install Microsoft.OpenJDK.17", "autonome": True,
                            "objectif": "Compiler le jeu à l'étape « dev ».",
                            "telechargement": "https://adoptium.net/temurin/releases/",
                            "etapes": ["Ouvrir la page.", "Télécharger le .zip.", "L'extraire.", "Lancer java -version."]}],
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
        sans_prix = definition.cout_echange([u], lambda m: None)
        self.assertEqual((sans_prix["tokens"], sans_prix["euros"]), (4100, None))
        self.assertEqual(definition.cout_echange([], prix), {"tokens": 0, "euros": 0.0})

    def test_cout_echange_porte_l_empreinte_des_tokens_de_sortie(self):
        from bureau import empreinte
        u = {"modele": "sonnet", "entree": 1000, "sortie": 1000, "cache_lecture": 0, "cache_ecriture": 0}
        c = definition.cout_echange([u, u], prix)
        self.assertAlmostEqual(c["co2"]["min"], 2 * empreinte.estimer("sonnet", 1000)["min"], places=5)
        # le prix inconnu n'empêche pas l'empreinte ; un modèle inconnu n'a pas de valeur
        self.assertIn("co2", definition.cout_echange([u], lambda m: None))
        inconnu = dict(u, modele="gpt-x")
        self.assertNotIn("co2", definition.cout_echange([inconnu], prix))

    def test_la_proposition_porte_l_empreinte_estimee(self):
        b = self.tour(self.brouillon(), Faux(proposition()), verifier_environnement=en_place)
        c = b["proposition"]["cout"]
        self.assertLess(c["co2"]["min"], c["co2"]["max"])
        self.assertIn("CO₂e", b["proposition"]["texte"])

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


class Pont:
    """Un exécuteur d'outil : les commandes de `simulees` rendent la réponse donnée, les autres vont à l'outil réel."""

    def __init__(self, simulees=None):
        self.appels, self.simulees = [], simulees or {}

    def __call__(self, factory, argv, entree=None):
        from orchestrateur import outil
        self.appels.append((argv[1], entree))
        if argv[1] in self.simulees:
            return self.simulees[argv[1]]
        return outil.executer(factory, argv, entree)


class TestValider(Base):
    def setUp(self):
        super().setUp()
        from bureau import reglages
        from installation import dossier
        from tests.test_inst_creation import Executeur
        self.reglages = reglages
        self.parent = self.base / "mes projets"
        self.bureau = dossier.bureau()
        self.git, self.gh = Executeur(), Executeur()
        self.commun = self.base / "usage-creations.jsonl"

    def pret(self, verifier=a_installer, nom="Casse-briques", **extra):
        """Un brouillon avec une proposition du chef, écrit sur le disque."""
        infos = dict(INFOS, parent=str(self.parent), nom=nom, **{k: v for k, v in extra.items() if k in INFOS})
        b = brouillons.creer(infos, dossier=self.d, maintenant=T0)
        o = proposition(**{k: v for k, v in extra.items() if k not in INFOS})
        b = definition.tour(b, genres_connus=GENRES, couche="claude", appeler=Faux(o), verifier_environnement=verifier,
                            maintenant=T0)
        brouillons.ecrire(b, dossier=self.d, maintenant=T0)
        return b

    def valider(self, b, **kw):
        kw.setdefault("bureau_json", self.bureau)
        kw.setdefault("git", self.git)
        kw.setdefault("gh", self.gh)
        kw.setdefault("maintenant", T0)
        kw.setdefault("dossier", self.d)
        kw.setdefault("commun", self.commun)
        return definition.valider(b, **kw)

    def factory(self, nom="Casse-briques"):
        return self.parent / nom / ".factory" / "factory.json"

    def releve(self, nom="Casse-briques"):
        from orchestrateur import outil
        code, r = outil.executer(self.factory(nom), ["releve"])
        self.assertEqual(code, 0, r)
        return r

    def test_rien_tant_que_rien_n_est_valide(self):
        b = self.pret()
        self.assertFalse((self.parent / "Casse-briques").exists())
        self.assertFalse(self.bureau.exists())
        self.assertEqual(sorted(p.name for p in self.parent.iterdir()), ["Petit projet"])
        self.assertTrue((self.d / f"{b['id']}.json").is_file())

    def test_creer_avec_organisation(self):
        from orchestrateur import factory as fa, fiches, workflows
        b = self.pret(facturation=True)
        r = self.valider(b, installer=True, executer=Pont({"genre": (0, {"genre": "jeu-android", "cree": True})}))
        f = fa.lire(self.factory())
        w = next(x for x in f["workflows"] if x["id"] == "w-jeu-android")
        self.assertEqual((w["genre"], w["fonctionnalite"]), ("jeu-android", None))
        self.assertEqual([e["id"] for e in w["flux"]], ["dev", "essai", "livraison"])    # sans préfixe
        self.assertTrue(workflows.est_validation(w["flux"][1]))
        self.assertEqual(sorted(s["id"] for s in f["services"]), ["dev", "facturation"])
        fs = {x["cle"]: x for x in fiches.lire_toutes(f["fiches"])}
        self.assertEqual(sorted(fs), sorted(a["cle"] for a in b["proposition"]["agents"]))
        self.assertEqual(fs["dev-1"]["modele"], "Sonnet")
        self.assertTrue((f["fiches"] / "briefs" / "dev.md").is_file())
        self.assertTrue((f["fiches"] / "briefs" / "environnement.md").is_file())
        self.assertEqual(f["environnement"][0]["outil"], "JDK")
        self.assertEqual(f["nom"], "Casse-briques")
        self.assertEqual(r["id"], self.reglages.lire_bureau(self.bureau)["projets"][0]["id"])
        self.assertIn("w-jeu-android", r["message"])
        self.assertEqual(self.git.appels, [])    # GitHub non demandé

    def test_genre_connu_fixe_a_la_creation(self):
        from orchestrateur import factory as fa
        b = self.pret(genre="jeu-web", nouveau=None)
        pont = Pont()
        self.valider(b, executer=pont)
        f = fa.lire(self.factory())
        self.assertEqual(f["genre"], "jeu-web")
        self.assertEqual(f["workflows"][0]["id"], "w-jeu-web")
        self.assertNotIn("genre", [c for c, _ in pont.appels])      # un genre connu n'est pas recréé

    def test_organisation_refusee_ne_laisse_rien(self):
        from installation import creation
        b = self.pret()
        org = definition._organisation(b["proposition"], b["infos"], True, [], "2026-11-12")
        org["workflow"]["flux"][0]["service"] = "inconnu"
        avant = sorted(p.name for p in self.parent.iterdir())
        with self.assertRaises(Echec) as c:
            creation.creer_projet(self.parent, "Casse-briques", organisation=org, bureau_json=self.bureau,
                                  git=self.git, gh=self.gh)
        self.assertIn("Organisation refusée", str(c.exception))
        self.assertEqual(sorted(p.name for p in self.parent.iterdir()), avant)
        self.assertFalse(self.bureau.exists())

    def test_nom_pris_entre_temps_retour_infos(self):
        b = self.pret()
        (self.parent / "Casse-briques").mkdir()      # un autre projet du même nom est né pendant l'échange
        with self.assertRaises(definition.InfosAChanger) as c:
            self.valider(b)
        self.assertIn("existe déjà", str(c.exception))
        self.assertTrue(isinstance(c.exception, Echec))
        self.assertTrue((self.d / f"{b['id']}.json").is_file())          # l'échange est gardé
        self.assertEqual(brouillons.lire(b["id"], dossier=self.d)["proposition"]["workflow"]["id"], "w-jeu-android")
        self.assertFalse(self.bureau.exists())
        self.assertEqual(list((self.parent / "Casse-briques").iterdir()), [])
        # Dossier parent disparu, nom devenu invalide : même retour.
        for infos in ({"parent": str(self.base / "disparu")}, {"nom": "a:b"}):
            c2 = brouillons.lire(b["id"], dossier=self.d)
            c2["infos"].update(infos)
            with self.assertRaises(definition.InfosAChanger):
                self.valider(c2)

    def test_bureau_plein_retour_infos(self):
        from unittest import mock
        b = self.pret()
        with mock.patch.object(definition.mep, "_controler_bureau", side_effect=Echec("Le bureau est plein.")):
            with self.assertRaises(definition.InfosAChanger):
                self.valider(b)

    def test_genre_nouveau_cree_par_l_outil(self):
        b = self.pret()
        pont = Pont({"genre": (0, {"genre": "jeu-android", "cree": True})})
        self.valider(b, executer=pont, genre_description="  Jeux mobiles livrés en apk.  ")
        genre = [e for c, e in pont.appels if c == "genre"]
        self.assertEqual(genre, [{"action": "fixer", "genre": "jeu-android",
                                  "description": "Jeux mobiles livrés en apk."}])
        b2 = self.pret(nom="Autre jeu")
        pont = Pont({"genre": (0, {})})
        self.valider(b2, executer=pont)
        self.assertEqual([e["description"] for c, e in pont.appels if c == "genre"],
                         ["Un jeu pour Android livré en apk."])       # sans édition : celle du chef

    def test_genre_nouveau_refuse_projet_garde(self):
        from orchestrateur import factory as fa
        b = self.pret()
        r = self.valider(b, executer=Pont({"genre": (1, {"erreur": "mot interdit"})}))
        self.assertTrue(self.factory().is_file())
        fa.lire(self.factory())
        self.assertIn("jeu-android", r["message"])
        self.assertIn("mot interdit", r["message"])
        self.assertFalse((self.d / f"{b['id']}.json").exists())     # l'échange est fini
        self.assertEqual(len(self.reglages.lire_bureau(self.bureau)["projets"]), 1)

    def test_usages_verses_au_releve(self):
        b = self.pret()
        b["usages"] = [dict(USAGE), dict(USAGE, entree=5)]
        self.valider(b, executer=Pont({"genre": (0, {})}))
        usages = self.releve()["usage"]
        self.assertEqual(sorted(u["entree"] for u in usages), [2, 5])
        self.assertEqual({u.get("etape") for u in usages}, {"orchestration"})
        self.assertEqual(brouillons.usages_abandonnes(commun=self.commun), [])

    def test_usage_non_verse_reste_compte(self):
        b = self.pret()
        b["usages"] = [dict(USAGE)]
        r = self.valider(b, executer=Pont({"genre": (0, {}), "usage": (1, {"erreur": "occupé"})}))
        self.assertIn("1 appel", r["message"])
        self.assertEqual(len(brouillons.usages_abandonnes(commun=self.commun)), 1)

    def test_installation_acceptee_tache_de_projet(self):
        from orchestrateur import factory as fa, fiches
        b = self.pret()
        r = self.valider(b, installer=True, executer=Pont({"genre": (0, {})}))
        taches = self.releve()["taches"]
        t = next(x for x in taches if x["titre"] == "Mise en place de l'environnement")
        self.assertEqual((t["colonne"], t["fonctionnalite"], t["etape"]), ("cadrage", None, "environnement"))
        self.assertIn("JDK", json.dumps(t["journal"], ensure_ascii=False))
        f = fa.lire(self.factory())
        installateur = next(x for x in fiches.lire_toutes(f["fiches"]) if x["role"] == "environnement")
        self.assertIn("Bash(winget:*)", installateur["outils"])
        self.assertIn("installation du poste", r["message"])

    def test_installation_refusee_pas_d_agent_d_installation(self):
        from orchestrateur import factory as fa, fiches
        b = self.pret()
        pont = Pont({"genre": (0, {})})
        self.valider(b, installer=False, executer=pont)
        f = fa.lire(self.factory())
        self.assertNotIn("environnement", [x["role"] for x in fiches.lire_toutes(f["fiches"])])
        self.assertFalse((f["fiches"] / "briefs" / "environnement.md").exists())
        self.assertNotIn("tache", [c for c, _ in pont.appels])
        self.assertEqual([x for x in self.releve()["taches"] if x["titre"] == "Mise en place de l'environnement"], [])

    def test_outil_non_autonome_pas_d_installateur_et_decision_de_projet(self):
        from orchestrateur import factory as fa, fiches
        env = dict(proposition()["environnement"][0], autonome=False)
        b = self.pret(environnement=[env])
        self.assertIsNone(b["proposition"]["installateur"])                     # rien à confier à un agent
        pont = Pont({"genre": (0, {})})
        self.valider(b, installer=True, executer=pont)                          # même cochée : rien ne part
        f = fa.lire(self.factory())
        self.assertNotIn("environnement", [x["role"] for x in fiches.lire_toutes(f["fiches"])])
        self.assertNotIn("tache", [c for c, _ in pont.appels])
        (d,) = [x for x in self.releve()["decisions_projet"] if x["genre"] == "environnement"]
        self.assertEqual((d["environnement"][0]["outil"], d["environnement"][0]["autonome"]), ("JDK", False))
        self.assertEqual(d["environnement"][0]["etapes"][0], "Ouvrir la page.")

    def test_sans_la_case_la_liste_attend_au_bureau(self):
        b = self.pret()
        self.valider(b, installer=False, executer=Pont({"genre": (0, {})}))
        (d,) = [x for x in self.releve()["decisions_projet"] if x["genre"] == "environnement"]
        self.assertTrue(d["environnement"][0]["autonome"])                      # le bouton « Installer en autonomie »
        self.assertIn("JDK", d["texte"])

    def test_poste_en_place_pas_de_tache(self):
        b = self.pret(verifier=en_place)
        pont = Pont({"genre": (0, {})})
        self.valider(b, installer=True, executer=pont)
        self.assertNotIn("tache", [c for c, _ in pont.appels])

    def test_fable_accorde_par_agent(self):
        from orchestrateur import factory as fa, fiches
        agents = proposition()["agents"]
        agents[0].update(modele="Opus", fable_suggere=True)
        b = self.pret(agents=agents)
        self.valider(b, fable=["dev-1"], executer=Pont({"genre": (0, {})}))
        fs = {x["cle"]: x for x in fiches.lire_toutes(fa.lire(self.factory())["fiches"])}
        self.assertEqual(fs["dev-1"]["modele"], "Fable")
        self.assertTrue(fiches.fable_accorde(fs["dev-1"]))
        self.assertEqual(fs["livreur-1"]["modele"], "Haiku")
        # Un agent dont Fable n'a pas été suggéré : refusé, rien n'est créé.
        b2 = self.pret(nom="Autre jeu")
        with self.assertRaises(Echec) as c:
            self.valider(b2, fable=["livreur-1"], executer=Pont())
        self.assertIn("Fable n'a pas été suggéré", str(c.exception))
        self.assertFalse((self.parent / "Autre jeu").exists())

    def test_github_apres_et_sans_rien_defaire(self):
        from tests.test_inst_creation import Executeur
        b = self.pret(github=True)
        gh = Executeur({"auth": (1, "not logged in")})
        r = self.valider(b, executer=Pont({"genre": (0, {})}), gh=gh)
        self.assertTrue(self.factory().is_file())                        # le projet reste créé
        self.assertIn("GitHub n'a pas été fait", r["github"])
        self.assertIn("GitHub n'a pas été fait", r["message"])
        self.assertEqual(self.git.appels, [])
        self.assertFalse((self.d / f"{b['id']}.json").exists())
        b2 = self.pret(github=True, nom="Autre jeu")
        gh2 = Executeur()
        r = self.valider(b2, executer=Pont({"genre": (0, {})}), gh=gh2)
        self.assertEqual(r["github"], "fait")
        self.assertEqual(gh2.appels[-1][0][:2], ["repo", "create"])
        self.assertTrue((self.parent / "Autre jeu" / ".factory" / "factory.json").is_file())   # GitHub vient après

    def test_brouillon_retire_apres_creation(self):
        b = self.pret()
        self.valider(b, executer=Pont({"genre": (0, {})}))
        self.assertEqual(brouillons.lister(dossier=self.d), [])

    def test_valider_sans_proposition_ou_pendant_un_tour(self):
        b = brouillons.creer(dict(INFOS, parent=str(self.parent)), dossier=self.d, maintenant=T0)
        with self.assertRaises(Echec):
            self.valider(b)
        c = self.pret(nom="Autre jeu")
        brouillons.commencer_tour(c["id"], {}, dossier=self.d, maintenant=T0)
        with self.assertRaises(brouillons.TourEnCours):
            self.valider(brouillons.lire(c["id"], dossier=self.d))
        self.assertFalse((self.parent / "Autre jeu").exists())

    def test_demande_du_genre_reprend_le_workflow(self):
        """Le projet créé porte le workflow `w-<genre>` et le genre du projet : le moteur peut le reprendre."""
        from orchestrateur import factory as fa, workflows
        b = self.pret(genre="jeu-web", nouveau=None)
        self.valider(b, executer=Pont())
        f = fa.lire(self.factory())
        self.assertEqual(workflows.de_creation(f)["id"], "w-jeu-web")
