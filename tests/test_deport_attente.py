"""L'attente d'une exécution distante n'est pas un blocage : `detache.attente_deportee` et le garde-fou d'`attendre`."""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from moteur import detache



def maintenant():
    return datetime.now().astimezone()


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.racine = Path(self._t.name)
        self.attentes = self.racine / "deport-en-cours"
        self.attentes.mkdir()
        self.projet = str(self.racine / "projet")

    def ecrire(self, nom="a1", dossier=None, battement=None, **plus):
        battement = battement or maintenant()
        d = {"action": "apk", "attend": "apk", "lieu": "github", "dossier": self.projet if dossier is None else dossier,
             "depuis": (battement - timedelta(minutes=12)).isoformat(timespec="seconds"),
             "battement": battement.isoformat(timespec="seconds"), **plus}
        (self.attentes / (nom + ".json")).write_text(json.dumps(d), encoding="utf-8")


class Lecture(Base):
    def lire(self, cwd=None, **kw):
        return detache.attente_deportee(self.attentes, maintenant(), cwd=cwd or self.projet, **kw)

    def test_une_attente_vivante_est_rendue(self):
        self.ecrire()
        r = self.lire()
        self.assertEqual((r["action"], r["attend"], r["lieu"]), ("apk", "apk", "github"))
        self.assertIn("depuis", r)

    def test_battement_perime_ignore(self):
        self.ecrire(battement=maintenant() - timedelta(minutes=4))
        self.assertIsNone(self.lire())

    def test_battement_de_moins_de_3_min_vivant(self):
        self.ecrire(battement=maintenant() - timedelta(minutes=2))
        self.assertIsNotNone(self.lire())

    def test_dossier_vide_ou_absent(self):
        self.assertIsNone(self.lire())
        self.assertIsNone(detache.attente_deportee(self.racine / "nexiste-pas", maintenant(), cwd=self.projet))

    def test_dossier_du_projet_dedans_ou_au_dessus(self):
        self.ecrire()
        self.assertIsNotNone(self.lire(cwd=os.path.join(self.projet, "sous", "dossier")))
        self.assertIsNotNone(self.lire(cwd=str(self.racine)))

    def test_un_dossier_frere_au_prefixe_commun_ne_correspond_pas(self):
        self.ecrire()
        self.assertIsNone(self.lire(cwd=self.projet + "-bis"))
        self.assertIsNone(self.lire(cwd=self.projet[:-1]))

    def test_un_autre_dossier_ou_sans_cwd_ne_correspond_pas(self):
        self.ecrire()
        self.assertIsNone(self.lire(cwd=str(self.racine / "autre")))
        self.assertIsNone(detache.attente_deportee(self.attentes, maintenant()))
        self.ecrire(nom="vide", dossier="")
        self.assertIsNone(self.lire(cwd=str(self.racine / "autre")))

    def test_fichiers_illisibles_ignores_et_le_bon_est_trouve(self):
        (self.attentes / "a0.json").write_text("{pas du json", encoding="utf-8")
        (self.attentes / "a1.json").write_text("[1, 2]", encoding="utf-8")
        (self.attentes / "a2.json").write_text(json.dumps({"dossier": self.projet, "battement": "hier"}), encoding="utf-8")
        (self.attentes / "a3.json").write_text(json.dumps({"dossier": 5, "battement": None}), encoding="utf-8")
        (self.attentes / "x.lock").write_text("verrou", encoding="utf-8")
        self.assertIsNone(self.lire())
        self.ecrire(nom="b")
        self.assertIsNotNone(self.lire())

    def test_lecture_seule(self):
        self.ecrire()
        avant = (self.attentes / "a1.json").read_bytes()
        self.lire()
        self.assertEqual((self.attentes / "a1.json").read_bytes(), avant)


class Garde(Base):
    """`attendre` avec une horloge simulée : un agent vivant, sans aucune action dans son flux."""

    def monter(self, rafraichir):
        self.debut = self.t = time.time()      # l'horloge simulée part de l'heure réelle (les battements sont datés)
        self.tues = []
        self.rafraichir = rafraichir
        registre = detache.Registre(self.racine / ".factory", vivant=lambda e: True, tuer=self.tues.append,
                                    dormir=self.dormir, horloge=lambda: self.t, noter_abonnement=False, pas_s=2,
                                    dossier_attente=self.attentes)
        detache._preparer(registre.dossier)
        etat = {"genre": "tache", "cle": "t1", "pid": 4242, "debut": self.t, "dossier": self.projet}
        (registre.dossier / "t1.json").write_text(json.dumps(etat), encoding="utf-8")
        (registre.dossier / "t1.jsonl").write_text("", encoding="utf-8")
        return registre

    def dormir(self, s):
        self.t += s
        if self.t > self.debut + 30 * 3600:      # garde dur : une boucle qui ne finit pas échoue au lieu de tourner
            raise AssertionError("attendre ne finit pas : le garde-fou ne s'applique jamais")
        self.rafraichir(datetime.fromtimestamp(self.t).astimezone())

    def test_une_attente_vivante_n_est_pas_un_blocage_puis_le_compte_reprend(self):
        def rafraichir(m):
            if self.t < self.debut + 45 * 60:        # `deporter` bat toutes les minutes
                if int(self.t - self.debut) % 60 == 0:
                    self.ecrire(battement=m)
            elif (self.attentes / "a1.json").exists():
                (self.attentes / "a1.json").unlink()      # l'attente finit
        r = self.monter(rafraichir)
        with self.assertRaises(TimeoutError):
            r.attendre("t1", 2400)
        # arrêté 2400 s après la fin de l'attente, pas à 40 min depuis le début
        fin_attente = self.debut + 45 * 60
        self.assertGreaterEqual(self.t, fin_attente + 2400)
        self.assertLess(self.t, fin_attente + 2400 + 10)
        self.assertEqual(self.tues, [4242])

    def test_une_attente_sans_fin_est_bornee_par_un_plafond(self):
        def battre(m):      # `deporter` bat chaque minute, sans jamais s'arrêter
            if int(self.t - self.debut) % 60 == 0:
                self.ecrire(battement=m)
        self.ecrire()
        r = self.monter(battre)
        with self.assertRaises(TimeoutError):
            r.attendre("t1", 2400)
        self.assertGreaterEqual(self.t - self.debut, detache.PLAFOND_ATTENTE_S)
        self.assertLess(self.t - self.debut, detache.PLAFOND_ATTENTE_S + 2400 + 10)

    def test_un_battement_dans_le_futur_ne_protege_pas(self):
        self.ecrire(battement=maintenant() + timedelta(hours=5))
        r = self.monter(lambda m: None)
        with self.assertRaises(TimeoutError):
            r.attendre("t1", 2400)
        self.assertLess(self.t - self.debut, 2400 + 10)

    def test_battement_perime_le_garde_fou_s_applique(self):
        self.ecrire(battement=maintenant() - timedelta(minutes=10))     # un reste : personne ne bat plus
        r = self.monter(lambda m: None)
        with self.assertRaises(TimeoutError):
            r.attendre("t1", 2400)
        self.assertLess(self.t - self.debut, 2400 + 10)

    def test_sans_fichier_le_comportement_est_inchange(self):
        r = self.monter(lambda m: None)
        with self.assertRaises(TimeoutError):
            r.attendre("t1", 2400)
        self.assertLess(self.t - self.debut, 2400 + 10)
        self.assertEqual(self.tues, [4242])

    def test_l_attente_d_un_autre_dossier_ne_protege_pas_l_agent(self):
        r = self.monter(lambda m: self.ecrire(dossier=self.projet + "-bis", battement=m))
        with self.assertRaises(TimeoutError):
            r.attendre("t1", 2400)
        self.assertLess(self.t - self.debut, 2400 + 10)


class Travail(Base):
    def test_le_bureau_voit_l_attente_dans_le_travail_de_la_tache(self):
        factory = self.racine / ".factory"
        d = detache.dossier(factory)
        detache._preparer(d)
        (d / "t1.json").write_text(json.dumps({"genre": "tache", "cle": "t1", "pid": os.getpid(), "debut": time.time(),
                                               "dossier": self.projet, "taches": ["t1"]}), encoding="utf-8")
        (d / "t1.jsonl").write_text("", encoding="utf-8")
        self.ecrire()
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, factory, dossier_attente=self.attentes)
        self.assertEqual(taches[0]["travail"]["attente_deportee"]["attend"], "apk")
        os.remove(self.attentes / "a1.json")
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, factory, dossier_attente=self.attentes)
        self.assertIsNone(taches[0]["travail"]["attente_deportee"])


if __name__ == "__main__":
    unittest.main()


class ParAgent(Base):
    """Relecture finale (I6) : deux agents dans le même dossier ; seule l'attente de celui qui attend le protège."""

    def test_lecture_par_cle_d_agent(self):
        self.ecrire(agent="t1")
        self.assertIsNotNone(detache.attente_deportee(self.attentes, maintenant(), cwd=self.projet, agent="t1"))
        self.assertIsNone(detache.attente_deportee(self.attentes, maintenant(), cwd=self.projet, agent="t2"))
        self.assertIsNone(detache.attente_deportee(self.attentes, maintenant(), cwd=self.projet))

    def test_sans_cle_dans_le_fichier_le_dossier_suffit(self):
        self.ecrire()      # usage à la main : pas de clé d'agent
        self.assertIsNotNone(detache.attente_deportee(self.attentes, maintenant(), cwd=self.projet, agent="t2"))

    def test_le_garde_fou_du_frere_s_applique(self):
        self.debut = self.t = time.time()
        self.tues, self.rafraichir = [], (lambda m: self.ecrire(battement=m, agent="autre"))
        r = detache.Registre(self.racine / ".factory", vivant=lambda e: True, tuer=self.tues.append,
                             dormir=lambda s: Garde.dormir(self, s), horloge=lambda: self.t, noter_abonnement=False,
                             pas_s=2, dossier_attente=self.attentes)
        detache._preparer(r.dossier)
        etat = {"genre": "tache", "cle": "t1", "pid": 4242, "debut": self.t, "dossier": self.projet}
        (r.dossier / "t1.json").write_text(json.dumps(etat), encoding="utf-8")
        (r.dossier / "t1.jsonl").write_text("", encoding="utf-8")
        with self.assertRaises(TimeoutError):
            r.attendre("t1", 2400)
        self.assertLess(self.t - self.debut, 2400 + 10)
        self.assertEqual(self.tues, [4242])

    def test_la_fiche_du_seul_agent_qui_attend(self):
        factory = self.racine / ".factory"
        d = detache.dossier(factory)
        detache._preparer(d)
        for cle in ("t1", "t2"):
            (d / (cle + ".json")).write_text(json.dumps({"genre": "tache", "cle": cle, "pid": os.getpid(),
                                                         "debut": time.time(), "dossier": self.projet,
                                                         "taches": [cle]}), encoding="utf-8")
            (d / (cle + ".jsonl")).write_text("", encoding="utf-8")
        self.ecrire(agent="t2")
        taches = [{"id": "t1"}, {"id": "t2"}]
        detache.ajouter_au_travail(taches, factory, dossier_attente=self.attentes)
        self.assertIsNone(taches[0]["travail"]["attente_deportee"])
        self.assertEqual(taches[1]["travail"]["attente_deportee"]["attend"], "apk")

    def test_le_moteur_passe_la_cle_a_l_agent(self):
        vus = []

        class P:
            pid = 1

        def lancer(argv, entree, sortie, erreurs, env, cwd):
            vus.append(env)
            return P()
        r = detache.Registre(self.racine / ".factory", vivant=lambda e: True, noter_abonnement=False,
                             dossier_attente=self.attentes)
        r.lancer = lancer
        r._lancer("cle-7", {}, ["x"], b"", {"PATH": "p"}, self.projet)
        r._lancer("cle-8", {}, ["x"], b"", None, self.projet)
        self.assertEqual(vus[0]["MYIAFACTORY_AGENT"], "cle-7")
        self.assertEqual(vus[0]["PATH"], "p")
        self.assertEqual(vus[1]["MYIAFACTORY_AGENT"], "cle-8")
