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
                d = jugement.juger(type_, {"demande": "x"}, couche="claude", appeler=a)
                self.assertEqual(d.objet, objet)
                self.assertIsNone(d.question)
                self.assertEqual(len(d.usages), 1)
                self.assertEqual(a.recus[0]["modele"], jugement.TYPES[type_])
                self.assertEqual(a.recus[0]["couche"], "claude")
                self.assertEqual(a.recus[0]["consigne"], jugement.consigne(type_))

    def test_modeles_par_type(self):
        self.assertEqual(jugement.TYPES, {"decouper": "sonnet", "traduire_retour": "haiku", "ecrire_methode": "sonnet",
                                          "apres_refus": "haiku", "conseil": "haiku"})

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
            self.assertIsNone(jugement.valider(type_, objet), type_)

    def test_pas_un_objet(self):
        for type_ in VALIDES:
            self.assertIsNotNone(jugement.valider(type_, [1]))
            self.assertIsNotNone(jugement.valider(type_, None))

    def _varie(self, type_, **changements):
        objet = json.loads(json.dumps(VALIDES[type_]))
        objet.update(changements)
        return jugement.valider(type_, objet)

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
            self.assertNotIn("fable", texte.replace("jamais fable", ""))


if __name__ == "__main__":
    unittest.main()
