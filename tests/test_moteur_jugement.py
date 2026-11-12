"""Les appels de jugement du moteur : consignes, dossier, validation des réponses. Aucun appel réel."""
import json
import unittest
from pathlib import Path

from moteur import appel, jugement

RACINE = Path(__file__).resolve().parent.parent

VALIDES = {
    "decouper": {"elements": [{"id": "e1", "nom": "Accueil", "groupe": "écrans"},
                              {"id": "e2", "nom": "Profil", "groupe": "écrans"}],
                 "prototype": "e1", "depend_de": {"e2": ["e1"]}, "reprendre_methode": None,
                 "message": "Deux écrans, le premier sert de prototype."},
    "traduire_retour": {"validation": False, "consigne": "Agrandir le titre de l'écran d'accueil."},
    "ecrire_methode": {"document": "# Méthode\n\n1. Faire l'écran.", "briefs": {"dev": "Fais l'écran selon la méthode."},
                       "controles": [{"texte": "Le titre fait au moins 24 px.", "origine": "prototype"}]},
    "apres_refus": {"suite": "corriger", "consigne": "Agrandir le titre.", "raison": "Le titre est trop petit."},
    "conseil": {"action": "repondre", "parametres": {}, "reponse": "C'est noté."},
    "classer_genre": {"verdict": "proche", "genre": "badges-stream", "nouveau": None,
                      "raison": "Mêmes outils de dessin et même sorte d'image que les badges."},
    "proposer_organisation": {
        "flux": [{"etape": "dev", "nom": "Développement", "role": "dev", "service": "jeu"},
                 {"etape": "qualite", "nom": "Contrôle qualité", "role": "testeur", "service": "qualite"},
                 {"etape": "livraison", "nom": "Livraison de l'apk signé", "role": "livreur", "service": "livraison"}],
        "services": [{"id": "qualite", "nom": "Qualité"}, {"id": "livraison", "nom": "Livraison"}],
        "agents": [{"cle": "testeur", "prenom": "Inès", "role": "testeur", "service": "qualite", "modele": "Haiku",
                    "justification": "Vérification mécanique des tests et du livrable.", "texte": "Tu testes le jeu."},
                   {"cle": "livreur", "role": "livreur", "service": "livraison", "modele": "Sonnet",
                    "justification": "Construction et signature courantes.", "fable_suggere": False,
                    "texte": "Tu construis et signes l'apk."}],
        "briefs": {"testeur": "Lance les tests et essaie le jeu.", "livreur": "Construis l'apk signé et dépose-le."},
        "livrable": "Le jeu en fichier .apk signé, déposé dans les livrables.",
        "environnement": [{"outil": "JDK 17", "pour": "livraison", "executables": ["java", "javac"],
                           "installation": "winget install Microsoft.OpenJDK.17 (source officielle, environ 180 Mo)."}],
        "outils_installation": ["Bash(winget:*)", "Bash(sdkmanager:*)"]},
}

# Une proposition de `definir_workflow` : le workflow du projet, avec une validation du Directeur avant la livraison.
VALIDES["definir_workflow"] = {
    "type": "proposition", "message": "Voici le workflow : le jeu est codé, testé, vous le validez, puis il est livré.",
    "genre": None, "nouveau": {"id": "jeu-mobile-arcade", "description": "Petits jeux d'arcade pour téléphone."},
    "flux": [{"etape": "dev", "nom": "Développement", "role": "dev", "service": "jeu",
              "raison": "Le jeu est écrit en Kotlin."},
             {"etape": "qualite", "nom": "Contrôle qualité", "role": "testeur", "service": "qualite",
              "raison": "Les tests et un essai sur émulateur."},
             {"etape": "validation", "nom": "Essai par le Directeur", "validation": True,
              "raison": "Vous voulez essayer le jeu avant qu'il soit livré."},
             {"etape": "livraison", "nom": "Livraison de l'apk signé", "role": "livreur", "service": "jeu",
              "raison": "L'apk signé est déposé dans les livrables."}],
    "services": [{"id": "jeu", "nom": "Jeu"}, {"id": "qualite", "nom": "Qualité"}],
    "agents": [{"cle": "dev", "role": "dev", "service": "jeu", "modele": "Sonnet",
                "justification": "Code courant.", "texte": "Tu écris le jeu."},
               {"cle": "testeur", "role": "testeur", "service": "qualite", "modele": "Haiku",
                "justification": "Vérification mécanique.", "texte": "Tu testes le jeu."},
               {"cle": "livreur", "role": "livreur", "service": "jeu", "modele": "Sonnet",
                "justification": "Construction et signature.", "texte": "Tu construis l'apk."}],
    "briefs": {"dev": "Écris le jeu.", "testeur": "Teste le jeu.", "livreur": "Construis et signe l'apk."},
    "livrable": "Le jeu en fichier .apk signé.",
    "environnement": [{"outil": "JDK", "version_min": "17", "pour": "livraison", "executables": ["java"],
                       "installation": "winget install Microsoft.OpenJDK.17 (source officielle)."}],
    "outils_installation": ["Bash(winget:*)"]}

QUESTIONS = {"type": "questions", "message": "Quelques questions avant de proposer le workflow.",
             "questions": [{"id": "q1", "texte": "Le jeu doit-il fonctionner hors ligne ?", "choix": ["Oui", "Non"]},
                           {"id": "q2", "texte": "Quelles étapes voulez-vous valider vous-même ?", "choix": []}]}

# Les jugements dont la validation lit le dossier (genres connus, agents et services du projet).
DOSSIERS = {
    "classer_genre": {"demande": {"texte": "Un logo pour le chat", "images": []},
                      "projet": {"nom": "Projet d'essai", "description": "Des badges pour une chaîne."},
                      "genres_du_projet": [{"id": "badges-stream", "domaine": "images", "livrable": "png",
                                            "outils": "dessin"}],
                      "genres_connus": [{"id": "badges-stream"}, {"id": "jeu-android"}],
                      "mots_interdits": ["Zorglub"]},
    "proposer_organisation": {"demande": {"texte": "Un casse-briques Android", "images": []}, "genre": "jeu-android",
                              "projet": {"nom": "Projet d'essai", "description": "Des jeux."},
                              "services": [{"id": "jeu", "nom": "Jeu"}],
                              "agents": [{"cle": "dev", "role": "dev", "modele": "Sonnet", "specialite": "code"}],
                              "workflows_du_genre": [], "fonctionnalite": "f2", "refus": None},
    "definir_workflow": {"projet": {"nom": "Projet d'essai", "description": "Un casse-briques pour Android.",
                                    "facturation": False, "github": False},
                         "genres_connus": [{"id": "jeu-android", "domaine": "jeux", "livrable": "apk",
                                            "outils": "gradle"}],
                         "mots_interdits": ["Zorglub"], "services": [], "echange": [], "tours_de_questions": 0,
                         "tours_max": 4, "proposer_maintenant": False, "proposition_precedente": None,
                         "correction": None},
}


def reponse(objet, *, texte=None, modele="claude-haiku-5-5"):
    t = texte if texte is not None else json.dumps(objet, ensure_ascii=False)
    return appel.Reponse(t, [{"modele": modele, "entree": 10, "sortie": 5, "cache_lecture": 0, "cache_ecriture": 0}])


class Appels:
    """Un faux `appeler` qui rend les réponses données, dans l'ordre, et garde ce qu'il a reçu."""

    def __init__(self, *reponses):
        self.reponses, self.recus = list(reponses), []

    def __call__(self, consigne, dossier, modele, **options):
        self.recus.append({"consigne": consigne, "dossier": dossier, "modele": modele, **options})
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Juger(unittest.TestCase):
    def test_une_reponse_valide_par_type(self):
        for type_, objet in VALIDES.items():
            with self.subTest(type_=type_):
                a = Appels(reponse(objet))
                d = jugement.juger(type_, DOSSIERS.get(type_, {"demande": "x"}), couche="claude", appeler=a)
                self.assertEqual(d.objet, objet)
                self.assertIsNone(d.question)
                self.assertEqual(len(d.usages), 1)
                self.assertEqual(a.recus[0]["modele"], jugement.TYPES[type_])
                self.assertEqual(a.recus[0]["couche"], "claude")
                self.assertEqual(a.recus[0]["consigne"], jugement.consigne(type_))

    def test_modeles_par_type(self):
        self.assertEqual(jugement.TYPES, {"decouper": "sonnet", "traduire_retour": "haiku", "ecrire_methode": "sonnet",
                                          "apres_refus": "haiku", "conseil": "haiku", "classer_genre": "haiku",
                                          "proposer_organisation": "sonnet", "definir_workflow": "sonnet"})
        self.assertEqual(jugement.LIBELLES["definir_workflow"], "définir le workflow du projet")
        self.assertEqual((jugement.TOURS_MAX_DEFINITION, jugement.QUESTIONS_PAR_TOUR_MAX,
                          jugement.CHOIX_PAR_QUESTION_MAX), (4, 5, 6))

    def test_la_validation_lit_le_dossier(self):
        """Un genre inconnu du dossier est refusé, puis redemandé avec l'erreur."""
        mauvais = dict(VALIDES["classer_genre"], genre="inconnu")
        a = Appels(reponse(mauvais), reponse(VALIDES["classer_genre"]))
        d = jugement.juger("classer_genre", DOSSIERS["classer_genre"], couche="claude", appeler=a)
        self.assertEqual(d.objet, VALIDES["classer_genre"])
        self.assertIn("inconnu", json.loads(a.recus[1]["dossier"])[jugement.CLE_ERREUR])

    def test_modele_impose(self):
        a = Appels(reponse(VALIDES["ecrire_methode"]))
        jugement.juger("ecrire_methode", {}, couche="api", appeler=a, modele="opus")
        self.assertEqual(a.recus[0]["modele"], "opus")
        self.assertEqual(a.recus[0]["couche"], "api")

    def test_fable_refuse_avant_appel(self):
        with self.assertRaises(appel.ErreurAppel):
            jugement.juger("conseil", {}, couche="claude", appeler=lambda *a, **k: self.fail("appelé"), modele="fable")

    def test_type_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            jugement.juger("deviner", {}, couche="claude", appeler=lambda *a, **k: self.fail("appelé"))

    def test_reponse_invalide_redemandee_une_fois(self):
        a = Appels(reponse(None, texte="je ne sais pas"), reponse(VALIDES["apres_refus"]))
        d = jugement.juger("apres_refus", {"rapport": "r"}, couche="claude", appeler=a)
        self.assertEqual(d.objet, VALIDES["apres_refus"])
        self.assertIsNone(d.question)
        self.assertEqual(len(d.usages), 2)
        self.assertEqual(len(a.recus), 2)
        second = json.loads(a.recus[1]["dossier"])
        self.assertEqual(second["rapport"], "r")
        self.assertIn(jugement.CLE_ERREUR, second)
        self.assertIn("JSON", second[jugement.CLE_ERREUR])

    def test_reponse_invalide_deux_fois_devient_question(self):
        mauvais = dict(VALIDES["conseil"], action="tout_casser")
        a = Appels(reponse(mauvais), reponse(mauvais))
        d = jugement.juger("conseil", {"demande": "x"}, couche="claude", appeler=a)
        self.assertIsNone(d.objet)
        self.assertTrue(d.question)
        self.assertEqual(len(d.usages), 2)
        self.assertEqual(len(a.recus), 2)

    def test_appel_en_echec_deux_fois_devient_question_avec_ses_usages(self):
        u = {"modele": "claude-haiku-5-5", "entree": 3, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0}
        a = Appels(appel.ErreurAppel("délai dépassé (600 s)", [u]), appel.ErreurAppel("boom"))
        d = jugement.juger("traduire_retour", {}, couche="claude", appeler=a)
        self.assertIsNone(d.objet)
        self.assertTrue(d.question)
        self.assertEqual(d.usages, [u])

    def test_json_entoure_de_texte_est_lu(self):
        texte = "Voici ma décision.\n```json\n" + json.dumps(VALIDES["apres_refus"]) + "\n```\nBonne journée."
        d = jugement.juger("apres_refus", {}, couche="claude", appeler=Appels(reponse(None, texte=texte)))
        self.assertEqual(d.objet, VALIDES["apres_refus"])

    def test_le_dernier_bloc_json_compte(self):
        texte = ("```json\n{\"brouillon\": 1}\n```\npuis\n```json\n" + json.dumps(VALIDES["apres_refus"]) + "\n```")
        self.assertEqual(jugement.extraire_json(texte), VALIDES["apres_refus"])

    def test_json_nu_ou_entre_accolades_est_lu(self):
        self.assertEqual(jugement.extraire_json('  {"a": 1}  '), {"a": 1})
        self.assertEqual(jugement.extraire_json('Réponse : {"a": 1} voilà'), {"a": 1})
        self.assertIsNone(jugement.extraire_json("rien"))
        self.assertIsNone(jugement.extraire_json("[1, 2]"))

    def test_dossier_ne_contient_que_ses_cles(self):
        dossier = {"demande": {"type": "message", "texte": "Plus grand"}, "cahier": {"etapes": ["a"]}}
        a = Appels(reponse(VALIDES["traduire_retour"]))
        jugement.juger("traduire_retour", dossier, couche="claude", appeler=a)
        envoye = a.recus[0]["dossier"]
        self.assertEqual(json.loads(envoye), dossier)
        self.assertEqual(envoye.count("Plus grand"), 1)
        self.assertNotIn("Plus grand", a.recus[0]["consigne"])


class Valider(unittest.TestCase):
    def test_valides(self):
        for type_, objet in VALIDES.items():
            self.assertIsNone(jugement.valider(type_, objet, DOSSIERS.get(type_)), type_)

    def test_pas_un_objet(self):
        for type_ in VALIDES:
            self.assertIsNotNone(jugement.valider(type_, [1], DOSSIERS.get(type_)))
            self.assertIsNotNone(jugement.valider(type_, None, DOSSIERS.get(type_)))

    def _varie(self, type_, dossier=None, **changements):
        objet = json.loads(json.dumps(VALIDES[type_]))
        objet.update(changements)
        return jugement.valider(type_, objet, dossier if dossier is not None else DOSSIERS.get(type_))

    # --- classer_genre

    def test_classer_genre_valide(self):
        v = lambda **c: self._varie("classer_genre", **c)
        self.assertIsNone(v(verdict="meme"))
        self.assertIsNone(v(verdict="autre", genre="jeu-android"))
        self.assertIsNone(v(verdict="autre", genre=None, nouveau={"id": "jeu-web", "description": "Jeux web."}))
        self.assertIsNone(v(verdict="incertain", genre=None))
        self.assertIsNone(v(verdict="incertain", genre="jeu-android"))
        self.assertIsNotNone(v(verdict="peut-etre"))
        self.assertIsNotNone(v(raison=""))
        self.assertIsNotNone(v(genre=None))                               # proche sans genre
        self.assertIsNotNone(v(genre="inconnu"))                          # proche : un genre connu seulement
        self.assertIsNotNone(v(verdict="meme", genre="jeu-android"))      # meme : un genre du projet
        self.assertIsNotNone(v(nouveau={"id": "logo", "description": "x"}))   # proche ne crée pas de genre
        self.assertIsNotNone(v(verdict="autre", genre=None))              # autre : genre ou nouveau
        self.assertIsNotNone(v(verdict="autre", nouveau={"id": "jeu-web", "description": "Jeux web."}))  # pas les deux
        self.assertIsNotNone(v(verdict="autre", genre=None, nouveau={"id": "Jeu Web", "description": "x"}))
        self.assertIsNotNone(v(verdict="autre", genre=None, nouveau={"id": "jeu-web", "description": ""}))
        self.assertIsNotNone(v(verdict="autre", genre=None, nouveau={"id": "jeu-android", "description": "x"}))

    def test_classer_genre_intitule_facultatif_court_sur_une_ligne(self):
        v = lambda **c: self._varie("classer_genre", **c)
        self.assertIsNone(v(intitule="Casse-briques Android"))
        self.assertIsNone(v(intitule=None))
        self.assertIsNotNone(v(intitule=""))
        self.assertIsNotNone(v(intitule="deux\nlignes"))
        self.assertIsNotNone(v(intitule="x" * 61))
        self.assertIsNotNone(v(intitule=3))

    def test_classer_genre_coherente_booleen_ou_null_facultatif(self):
        v = lambda **c: self._varie("classer_genre", **c)
        self.assertIsNone(v(coherente=True))
        self.assertIsNone(v(coherente=False))
        self.assertIsNone(v(coherente=None))
        self.assertIsNone(v())                                            # absent : compatible
        self.assertIsNotNone(v(coherente="oui"))
        self.assertIsNotNone(v(coherente=1))

    def test_classer_genre_elargissement_facultatif_sans_mot_interdit(self):
        v = lambda **c: self._varie("classer_genre", **c)
        self.assertIsNone(v(elargissement="Badges et emotes de chat, et aussi logos de chaîne."))
        self.assertIsNone(v(elargissement=None))
        self.assertIsNotNone(v(elargissement=""))
        self.assertIsNotNone(v(elargissement="deux\nlignes"))
        self.assertIsNotNone(v(elargissement="x" * 301))
        self.assertIsNotNone(v(elargissement=3))
        self.assertIsNotNone(v(elargissement="Les logos de Zorglub."))      # mot interdit : un genre est public

    def test_classer_genre_nouveau_mot_interdit_refuse(self):
        v = lambda **c: self._varie("classer_genre", verdict="autre", genre=None, **c)
        self.assertIsNotNone(v(nouveau={"id": "zorglub-jeux", "description": "Les jeux."}))
        self.assertIsNotNone(v(nouveau={"id": "jeu-web", "description": "Les jeux de Zorglub."}))
        self.assertIsNone(v(nouveau={"id": "jeu-web", "description": "Les jeux web."}))

    def test_classer_genre_sans_dossier_ne_connait_aucun_genre(self):
        self.assertIsNotNone(self._varie("classer_genre", dossier={}))
        self.assertIsNone(self._varie("classer_genre", dossier={}, verdict="incertain", genre=None))

    # --- proposer_organisation

    def _orga(self, dossier=None, **changements):
        return self._varie("proposer_organisation", dossier, **changements)

    def _agents(self, **sur_le_premier):
        agents = json.loads(json.dumps(VALIDES["proposer_organisation"]["agents"]))
        agents[0].update(sur_le_premier)
        return agents

    def test_proposer_organisation_environnement_valide(self):
        env = VALIDES["proposer_organisation"]["environnement"][0]
        self.assertIsNone(self._orga(environnement=[]))
        self.assertIsNone(self._orga(outils_installation=[]))
        self.assertIsNotNone(self._orga(environnement=None))
        self.assertIsNotNone(self._orga(environnement=[dict(env, executables=[])]))
        self.assertIsNotNone(self._orga(environnement=[dict(env, executables="java")]))
        self.assertIsNotNone(self._orga(environnement=[dict(env, executables=["java --version"])]))
        self.assertIsNotNone(self._orga(environnement=[dict(env, executables=["C:\\jdk\\java"])]))
        self.assertIsNotNone(self._orga(environnement=[dict(env, installation="")]))
        self.assertIsNotNone(self._orga(environnement=[dict(env, outil="")]))
        self.assertIsNotNone(self._orga(environnement=[dict(env, pour="publication")]))   # étape inconnue
        self.assertIsNone(self._orga(environnement=[dict(env, pour="Livraison de l'apk signé")]))   # nom de l'étape
        self.assertIsNotNone(self._orga(outils_installation=["Bash"]))
        self.assertIsNotNone(self._orga(outils_installation=["Bash(*)"]))
        self.assertIsNotNone(self._orga(outils_installation=["Write"]))
        self.assertIsNotNone(self._orga(outils_installation="Bash(winget:*)"))
        self.assertIsNone(self._orga(outils_installation=["PowerShell(winget:*)", "Bash(gradle build)"]))

    def test_proposer_organisation_sans_livraison_refuse(self):
        flux = json.loads(json.dumps(VALIDES["proposer_organisation"]["flux"]))
        self.assertIsNotNone(self._orga(livrable=""))
        self.assertIsNotNone(self._orga(flux=flux[:2]))   # finit par le contrôle qualité
        flux[2]["nom"] = "Remise du jeu"
        self.assertIsNone(self._orga(flux=flux))
        flux[2]["nom"] = "Fichier .apk signé"           # le nom reprend le livrable
        self.assertIsNone(self._orga(flux=flux))

    def test_proposer_organisation_fable_refuse(self):
        self.assertIsNotNone(self._orga(agents=self._agents(modele="Fable")))
        self.assertIsNotNone(self._orga(agents=self._agents(modele="fable")))
        self.assertIsNotNone(self._orga(agents=self._agents(modele="GPT")))
        self.assertIsNone(self._orga(agents=self._agents(modele="Opus", fable_suggere=True)))
        self.assertIsNotNone(self._orga(agents=self._agents(fable_suggere="oui")))
        self.assertIn("Fable", self._orga(agents=self._agents(modele="Fable")))

    def test_modele_necessaire_par_etape(self):
        """Chaque étape d'agent porte le modèle que demande son travail, avec sa justification d'une ligne (bornée) ;
        les agents n'ont plus besoin de modèle : ils sont recrutés avec le plafond Opus."""
        flux = json.loads(json.dumps(VALIDES["proposer_organisation"]["flux"]))
        avec = lambda k, **x: [dict(e, **x) if i == k else e for i, e in enumerate(flux)]   # noqa: E731
        j = "Vérification mécanique."
        self.assertIsNone(self._orga(flux=avec(1, modele="Haiku", justification=j)))
        self.assertIsNone(self._orga(flux=avec(1, modele="Opus", justification="x" * jugement.LONGUEUR_JUSTIFICATION)))
        self.assertIsNotNone(self._orga(flux=avec(1, modele="Opus", justification="x" * (jugement.LONGUEUR_JUSTIFICATION + 1))))
        self.assertIsNotNone(self._orga(flux=avec(1, modele="Haiku")))                    # sans justification
        self.assertIsNotNone(self._orga(flux=avec(1, modele="Haiku", justification="a\nb")))
        self.assertIn("Fable", self._orga(flux=avec(1, modele="Fable", justification=j)))
        self.assertIsNotNone(self._orga(flux=avec(1, modele="GPT", justification=j)))
        sans = [{k: v for k, v in a.items() if k not in ("modele", "justification")}
                for a in VALIDES["proposer_organisation"]["agents"]]
        self.assertIsNone(self._orga(agents=sans))
        val = {"etape": "essai", "nom": "Essai par le Directeur", "validation": True, "modele": "Haiku",
               "justification": j}
        self.assertIsNotNone(self._orga(flux=[flux[0], val] + flux[1:]))
        o = json.loads(json.dumps(VALIDES["definir_workflow"]))
        o["flux"][1].update(modele="Haiku", justification=j)
        self.assertIsNone(self._def(o))
        o["flux"][1]["modele"] = "Fable"
        self.assertIsNotNone(self._def(o))

    def test_proposer_organisation_role_sans_agent_refuse(self):
        agents = VALIDES["proposer_organisation"]["agents"]
        self.assertIsNotNone(self._orga(agents=agents[1:]))              # testeur sans agent
        sans_dev = dict(DOSSIERS["proposer_organisation"], agents=[])
        self.assertIsNotNone(self._orga(dossier=sans_dev))               # dev sans agent
        self.assertIsNotNone(self._orga(briefs={"livreur": "x"}))        # testeur sans brief

    def test_proposer_organisation_flux_et_services(self):
        flux = VALIDES["proposer_organisation"]["flux"]
        self.assertIsNotNone(self._orga(flux=[]))
        self.assertIsNotNone(self._orga(flux=[dict(flux[0], service="inconnu")] + flux[1:]))
        self.assertIsNotNone(self._orga(flux=[dict(flux[0], etape="cadrage")] + flux[1:]))
        self.assertIsNotNone(self._orga(flux=[flux[0], flux[0]] + flux[1:]))
        self.assertIsNotNone(self._orga(flux=[dict(flux[0], etape="Dév")] + flux[1:]))
        self.assertIsNotNone(self._orga(services=[{"id": "jeu", "nom": "Jeu"}] +
                                        VALIDES["proposer_organisation"]["services"]))   # déjà au projet
        self.assertIsNotNone(self._orga(agents=self._agents(cle="dev")))  # clé déjà prise
        self.assertIsNotNone(self._orga(agents=self._agents(justification="")))
        self.assertIsNotNone(self._orga(agents=self._agents(texte="")))
        self.assertIsNotNone(self._orga(agents=self._agents(service="inconnu")))

    def test_validation_premiere_ou_double_refusee(self):
        """Les deux jugements : une validation du Directeur ni en première, ni en dernière, ni deux de suite, sans rôle."""
        val = {"etape": "essai", "nom": "Essai par le Directeur", "validation": True, "raison": "Vous essayez."}
        flux_orga = VALIDES["proposer_organisation"]["flux"]
        self.assertIsNone(self._orga(flux=flux_orga[:2] + [val] + flux_orga[2:]))
        self.assertIsNone(self._orga(flux=flux_orga[:1] + [dict(val, raison=None)] + flux_orga[1:]))
        flux_def = VALIDES["definir_workflow"]["flux"]                     # dev, qualite, validation, livraison
        for type_, flux in (("proposer_organisation", flux_orga), ("definir_workflow", flux_def)):
            with self.subTest(type_=type_):
                v = lambda f: self._varie(type_, flux=f)
                self.assertIn("première", v([val] + flux))
                self.assertIn("dernière", v(flux + [val]))
                self.assertIn("de suite", v(flux[:1] + [val, dict(val, etape="essai-2")] + flux[1:]))
                self.assertIsNotNone(v(flux[:1] + [dict(val, role="dev", service="jeu")] + flux[1:]))
                self.assertIsNotNone(v(flux[:1] + [dict(val, validation="oui", role=None)] + flux[1:]))

    def test_aide_d_installation_telechargement_etapes_autonome(self):
        env = VALIDES["proposer_organisation"]["environnement"][0]
        etapes = ["Ouvrir la page.", "Télécharger l'archive.", "L'extraire dans le profil.", "Lancer java -version."]
        bon = dict(env, telechargement="https://adoptium.net/temurin/releases/", etapes=etapes, autonome=True)
        self.assertIsNone(self._orga(environnement=[bon]))
        self.assertIsNone(self._orga(environnement=[dict(bon, telechargement=None)]))
        self.assertIsNone(self._orga(environnement=[env]))               # les anciens résultats restent acceptés
        for url in ("http://adoptium.net/", "adoptium.net", "ftp://x.org/a", "https://", "https://u:p@x.org/a",
                    "https://x.org/a b", "https://x.org/" + "a" * 300, 5, ""):
            self.assertIn("telechargement", self._orga(environnement=[dict(bon, telechargement=url)]), repr(url))
        for e in ([], ["une seule"], etapes[:1], ["a"] * 9, ["a", ""], ["a", 3], ["a", "b\nc"], "a. b.", None,
                  ["a", "b" * 201]):
            self.assertIn("etapes", self._orga(environnement=[dict(bon, etapes=e)]), repr(e))
        self.assertIsNone(self._orga(environnement=[dict(bon, etapes=["a"] * 8)]))
        for a in ("oui", 1, None, "true"):
            self.assertIn("autonome", self._orga(environnement=[dict(bon, autonome=a)]), repr(a))
        self.assertIsNone(self._orga(environnement=[dict(bon, objectif="Compiler le jeu à l'étape « Livraison ».")]))
        for obj in ("", "deux\nlignes", 3, "x" * 251, "  "):
            self.assertIn("objectif", self._orga(environnement=[dict(bon, objectif=obj)]), repr(obj))
        self.assertIsNone(self._varie("definir_workflow"))
        o = json.loads(json.dumps(VALIDES["definir_workflow"]))
        o["environnement"][0].update(telechargement="http://x.org/", etapes=etapes, autonome=False)
        self.assertIn("telechargement", self._def(o))
        o["environnement"][0].update(telechargement="https://x.org/jdk", autonome="oui")
        self.assertIn("autonome", self._def(o))

    def test_version_min_lue(self):
        env = VALIDES["proposer_organisation"]["environnement"][0]
        for version in ("17", "8.7", "1.8.0"):
            self.assertIsNone(self._orga(environnement=[dict(env, version_min=version)]), version)
        self.assertIsNone(self._orga(environnement=[dict(env, version_min=None)]))
        for version in ("", "17+", "v17", "dix-sept", 17, "1" * 21):
            self.assertIsNotNone(self._orga(environnement=[dict(env, version_min=version)]), version)
        self.assertIsNone(self._varie("definir_workflow"))                 # sa proposition porte version_min « 17 »

    # --- definir_workflow

    def _def(self, objet=None, **dossier):
        d = dict(DOSSIERS["definir_workflow"], **dossier)
        return jugement.valider("definir_workflow", objet if objet is not None else VALIDES["definir_workflow"], d)

    def _questions(self, **changements):
        o = json.loads(json.dumps(QUESTIONS))
        o.update(changements)
        return o

    def test_definir_workflow_questions_valides(self):
        self.assertIsNone(self._def(QUESTIONS))
        self.assertIsNone(self._def(QUESTIONS, tours_de_questions=3))
        q = QUESTIONS["questions"][0]
        self.assertIsNone(self._def(self._questions(questions=[dict(q, choix=[f"c{i}" for i in range(6)])])))
        self.assertIsNotNone(self._def(self._questions(message="")))
        self.assertIsNotNone(self._def(self._questions(questions=[])))
        self.assertIsNotNone(self._def(self._questions(questions=[q, q])))                 # ids en double
        self.assertIsNotNone(self._def(self._questions(questions=[dict(q, texte="")])))
        self.assertIsNotNone(self._def(self._questions(questions=[dict(q, id="")])))
        self.assertIsNotNone(self._def(self._questions(questions=[dict(q, choix=None)])))
        self.assertIsNotNone(self._def(self._questions(questions=[dict(q, choix=[""])])))
        self.assertIsNotNone(self._def(self._questions(questions=[dict(q, choix=["x" * 81])])))
        self.assertIsNotNone(self._def(self._questions(type="question")))

    def test_definir_workflow_multiple_booleen_facultatif(self):
        q = QUESTIONS["questions"][0]
        self.assertIsNone(self._def(self._questions(questions=[dict(q, multiple=True)])))
        self.assertIsNone(self._def(self._questions(questions=[dict(q, multiple=False)])))
        for faux in ("oui", 1, 0, None, []):
            self.assertIsNotNone(self._def(self._questions(questions=[dict(q, multiple=faux)])), faux)

    def test_consigne_definir_workflow_dit_quand_plusieurs_choix(self):
        texte = jugement.consigne("definir_workflow")
        self.assertIn('"multiple"', texte)
        self.assertIn("plusieurs", texte)

    def test_definir_workflow_trop_de_questions_refuse(self):
        q = QUESTIONS["questions"][0]
        cinq = [dict(q, id=f"q{i}") for i in range(5)]
        self.assertIsNone(self._def(self._questions(questions=cinq)))
        self.assertIsNotNone(self._def(self._questions(questions=cinq + [dict(q, id="q9")])))
        self.assertIsNotNone(self._def(self._questions(questions=[dict(q, choix=[f"c{i}" for i in range(7)])])))

    def test_cinquieme_appel_exige_une_proposition(self):
        """Après 4 tours de questions (ou quand l'utilisateur demande la proposition), des questions sont refusées."""
        self.assertIn("proposition", self._def(QUESTIONS, tours_de_questions=4))
        self.assertIn("proposition", self._def(QUESTIONS, proposer_maintenant=True))
        self.assertIsNone(self._def(tours_de_questions=4))
        self.assertIsNone(self._def(proposer_maintenant=True))

    def test_correction_exige_une_proposition(self):
        self.assertIn("proposition", self._def(QUESTIONS, correction="Ajoute une validation après le développement.",
                                                proposition_precedente=VALIDES["definir_workflow"]))
        self.assertIsNone(self._def(correction="Ajoute une validation après le développement.",
                                    proposition_precedente=VALIDES["definir_workflow"]))

    def test_definir_workflow_proposition_valide(self):
        o = VALIDES["definir_workflow"]
        self.assertIsNone(self._def())
        self.assertIsNone(self._def(dict(o, genre="jeu-android", nouveau=None)))
        self.assertIsNotNone(self._def(dict(o, genre="jeu-inconnu", nouveau=None)))       # genre hors du dossier
        self.assertIsNotNone(self._def(dict(o, genre=None, nouveau=None)))                 # ni l'un ni l'autre
        self.assertIsNotNone(self._def(dict(o, genre="jeu-android")))                      # les deux
        self.assertIsNotNone(self._def(dict(o, nouveau={"id": "jeu-android", "description": "x"})))  # déjà connu
        self.assertIsNotNone(self._def(dict(o, nouveau={"id": "Jeu Mobile", "description": "x"})))
        self.assertIsNotNone(self._def(dict(o, message="")))
        self.assertIsNotNone(self._def(dict(o, agents=o["agents"][1:])))                   # dev sans agent
        self.assertIsNotNone(self._def(dict(o, flux=o["flux"][:3])))                       # finit par une validation
        self.assertIsNotNone(self._def(dict(o, type="organisation")))
        etape_longue = dict(o["flux"][0], etape="x" * 37)                                  # trop longue une fois préfixée
        self.assertIsNotNone(self._def(dict(o, flux=[etape_longue] + o["flux"][1:])))
        self.assertIsNone(self._def(dict(o, flux=[dict(o["flux"][0], etape="x" * 35)] + o["flux"][1:])))

    def test_definir_workflow_genre_nouveau_mot_interdit_refuse(self):
        o = VALIDES["definir_workflow"]
        self.assertIsNotNone(self._def(dict(o, nouveau={"id": "zorglub-jeux", "description": "Des jeux."})))
        # Le nom du projet est interdit dès la fenêtre 1, même absent de la liste des mots interdits.
        self.assertIsNotNone(self._def(dict(o, nouveau={"id": "jeu-mobile", "description": "Les jeux du Projet d'essai."}),
                                       mots_interdits=[]))
        self.assertIsNone(self._def(dict(o, nouveau={"id": "jeu-mobile", "description": "Jeux pour téléphone."}),
                                    mots_interdits=[]))

    def test_etape_sans_raison_refusee(self):
        o = VALIDES["definir_workflow"]
        for k in range(len(o["flux"])):
            with self.subTest(etape=k):
                flux = json.loads(json.dumps(o["flux"]))
                flux[k]["raison"] = ""
                self.assertIn("raison", self._def(dict(o, flux=flux)))
                flux[k]["raison"] = "deux\nlignes"
                self.assertIsNotNone(self._def(dict(o, flux=flux)))
                del flux[k]["raison"]
                self.assertIsNotNone(self._def(dict(o, flux=flux)))

    def test_decouper(self):
        self.assertIsNotNone(self._varie("decouper", elements=[]))
        self.assertIsNotNone(self._varie("decouper", prototype="e9"))
        self.assertIsNotNone(self._varie("decouper", depend_de={"e2": ["e9"]}))
        self.assertIsNotNone(self._varie("decouper", elements=[{"id": "e1", "nom": "A", "groupe": "g"},
                                                               {"id": "e1", "nom": "B", "groupe": "g"}]))
        self.assertIsNotNone(self._varie("decouper", elements=[{"id": "a/b", "nom": "A", "groupe": "g"}],
                                         prototype="a/b", depend_de={}))
        self.assertIsNotNone(self._varie("decouper", elements=[{"id": "e1", "nom": "", "groupe": "g"}],
                                         prototype="e1", depend_de={}))
        self.assertIsNotNone(self._varie("decouper", message=""))
        un = lambda **plus: [{"id": "e1", "nom": "A", "groupe": "g", **plus}]   # noqa: E731
        self.assertIsNone(self._varie("decouper", elements=un(validations=["f1-da"], objectif="L'accueil."),
                                      prototype="e1", depend_de={}))
        self.assertIsNone(self._varie("decouper", elements=un(validations=[]), prototype="e1", depend_de={}))
        for mauvais in ({"validations": "f1-da"}, {"validations": [""]}, {"objectif": ""}, {"objectif": "x" * 301}):
            self.assertIsNotNone(self._varie("decouper", elements=un(**mauvais), prototype="e1", depend_de={}), mauvais)
        self.assertIsNotNone(self._varie("decouper", reprendre_methode={"fonctionnalite": "f1"}))
        self.assertIsNone(self._varie("decouper", reprendre_methode={"fonctionnalite": "f1", "version": 2,
                                                                     "pourquoi": "même élément, même flux"}))

    def test_traduire_retour(self):
        self.assertIsNotNone(self._varie("traduire_retour", consigne=None))
        self.assertIsNotNone(self._varie("traduire_retour", validation="oui"))
        self.assertIsNone(self._varie("traduire_retour", validation=True, consigne=None))

    def test_ecrire_methode(self):
        self.assertIsNotNone(self._varie("ecrire_methode", document=""))
        self.assertIsNotNone(self._varie("ecrire_methode", briefs={}))
        self.assertIsNotNone(self._varie("ecrire_methode", briefs={"dev": ""}))
        self.assertIsNotNone(self._varie("ecrire_methode", controles=[{"texte": "x"}]))
        self.assertIsNone(self._varie("ecrire_methode", controles=[]))

    def test_apres_refus(self):
        self.assertIsNotNone(self._varie("apres_refus", suite="abandonner"))
        self.assertIsNotNone(self._varie("apres_refus", consigne=None))
        self.assertIsNotNone(self._varie("apres_refus", raison=""))
        self.assertIsNone(self._varie("apres_refus", suite="bloquer", consigne=None))
        self.assertIsNone(self._varie("apres_refus", suite="methode_a_revoir", consigne=None))

    def test_conseil_actions_de_la_liste_fermee(self):
        self.assertEqual(jugement.ACTIONS_CONSEIL, ("repondre", "transmettre_agent", "poser_decision", "lancer", "rien"))
        self.assertIsNotNone(self._varie("conseil", action="improviser"))
        self.assertIsNotNone(self._varie("conseil", parametres=None))
        self.assertIsNotNone(self._varie("conseil", reponse=None))
        self.assertIsNone(self._varie("conseil", action="rien", reponse=""))
        self.assertIsNone(self._varie("conseil", action="transmettre_agent", parametres={"consigne": "Refaire."}))
        self.assertIsNotNone(self._varie("conseil", action="transmettre_agent", parametres={}))
        self.assertIsNone(self._varie("conseil", action="poser_decision", parametres={"texte": "Garder A ou B ?"}))
        self.assertIsNotNone(self._varie("conseil", action="poser_decision", parametres={}))

    def test_conseil_lancer(self):
        self.assertIsNone(self._varie("conseil", action="lancer",
                                      parametres={"commande": "tache", "entree": {"id": "t1", "colonne": "fait"}}))
        self.assertIsNotNone(self._varie("conseil", action="lancer", parametres={}))
        self.assertIsNotNone(self._varie("conseil", action="lancer", parametres={"commande": "inventee"}))
        self.assertIsNotNone(self._varie("conseil", action="lancer", parametres={"commande": "tache", "entree": [1]}))

    def test_conseil_refuse_commande_lecon(self):
        self.assertIsNotNone(self._varie("conseil", action="lancer",
                                         parametres={"commande": "lecon", "entree": {"action": "appliquer"}}))
        self.assertIsNotNone(self._varie("conseil", action="lancer", parametres={"commande": "genre", "entree": {}}))

    def test_conseil_refuse_commande_du_bureau(self):
        from orchestrateur.outil import COMMANDES_DU_BUREAU
        for commande in COMMANDES_DU_BUREAU:
            self.assertIsNotNone(self._varie("conseil", action="lancer", parametres={"commande": commande}))


class Consignes(unittest.TestCase):
    def test_cinq_consignes_courtes(self):
        for type_ in jugement.TYPES:
            texte = jugement.consigne(type_)
            self.assertLessEqual(len(texte.splitlines()), 40, type_)
            self.assertIn("Réponds seulement par ce JSON.", texte, type_)

    def test_chaque_consigne_donne_ses_champs(self):
        for type_, objet in VALIDES.items():
            texte = jugement.consigne(type_)
            for cle in objet:
                self.assertIn(f'"{cle}"', texte, f"{type_} : {cle}")

    def test_conseil_liste_ses_actions(self):
        texte = jugement.consigne("conseil")
        for action in jugement.ACTIONS_CONSEIL:
            self.assertIn(action, texte)

    def test_decouper_et_methode_reprennent_les_consignes(self):
        decouper = jugement.consigne("decouper")
        self.assertIn("Identifie l'élément qui se répète et les groupes", decouper)
        self.assertIn("même élément et même flux", decouper)
        methode = jugement.consigne("ecrire_methode")
        self.assertIn("les briefs disent aux agents de relire le registre", methode)
        self.assertIn("contrôles de départ", methode)

    def test_aucune_consigne_ne_parle_de_fable_ni_d_un_projet(self):
        for type_ in jugement.TYPES:
            texte = jugement.consigne(type_).lower()
            self.assertNotIn("myiafactory", texte)
            self.assertNotIn("fable", texte.replace("jamais fable", "").replace("fable_suggere", ""))

    def test_classer_genre_porte_les_decisions_de_l_utilisateur(self):
        texte = jugement.consigne("classer_genre")
        self.assertIn("mêmes savoir-faire, mêmes outils, même sorte de livrable", texte)
        self.assertIn("dans le doute, `incertain`", texte)
        for verdict in jugement.VERDICTS_GENRE:
            self.assertIn(f"`{verdict}`", texte)

    def test_proposer_organisation_porte_les_decisions_de_l_utilisateur(self):
        texte = jugement.consigne("proposer_organisation")
        self.assertIn("de la demande au livrable remis", texte)
        self.assertIn("qualité", texte)
        self.assertIn("tel quel", texte)
        for modele in ("Haiku", "Sonnet", "Opus"):
            self.assertIn(modele, texte)
        self.assertIn("jamais Fable", texte)
        self.assertIn('"validation": true', texte)
        self.assertIn("version_min", texte)

    def test_modele_par_etape_et_plafond_opus_dans_les_deux_consignes(self):
        for type_ in ("proposer_organisation", "definir_workflow"):
            texte = jugement.consigne(type_)
            self.assertIn('"modele": "Haiku", "justification"', texte, type_)    # sur l'étape, dans l'exemple
            self.assertIn("plafond Opus", texte, type_)
            self.assertLess(len(texte), 4600, type_)                             # une consigne reste courte

    def test_definir_workflow_porte_les_decisions_de_l_utilisateur(self):
        texte = jugement.consigne("definir_workflow")
        for attendu in ("ne repose jamais", "livrables", "valider", "tests", "assez", "choix",
                        "de la demande au livrable remis", '"validation": true', "jamais Fable", "fable_suggere",
                        "raison", "4", "proposer_maintenant", "correction", "courts"):
            self.assertIn(attendu, texte)
        for modele in ("Haiku", "Sonnet", "Opus"):
            self.assertIn(modele, texte)
        for cle in QUESTIONS["questions"][0]:
            self.assertIn(f'"{cle}"', texte)


if __name__ == "__main__":
    unittest.main()
