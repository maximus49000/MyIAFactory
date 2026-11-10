import unittest
from datetime import datetime, timedelta, timezone

from bureau import statuts

M = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def t(minutes, active=True, titre="Tâche"):
    """Tâche mise à jour il y a `minutes`."""
    return {"id": titre, "titre": titre, "active": active,
            "maj": (M - timedelta(minutes=minutes)).isoformat()}


class TestStatuts(unittest.TestCase):
    def test_lire_date(self):
        self.assertEqual(statuts.lire_date("2026-11-10T12:00:00+00:00"), M)
        self.assertEqual(statuts.lire_date("2026-11-10T12:00:00"), datetime(2026, 11, 10, 12, 0).astimezone())
        for mauvais in (None, "", "hier", 12):
            self.assertEqual(statuts.lire_date(mauvais), statuts.TRES_ANCIEN)

    def test_duree(self):
        self.assertEqual([statuts.duree_en_clair(m) for m in (45, 60, 125, 47 * 60, 48 * 60, 5000)],
                         ["45 min", "1 h", "2 h", "47 h", "2 j", "3 j"])

    def test_travail(self):
        s = statuts.statut([t(5, titre="A"), t(2, titre="B"), t(1, active=False, titre="C")], M, 30, False)
        self.assertEqual(s, {"statut": "travail", "bulle": "B (+1)"})

    def test_titre_tronque(self):
        self.assertEqual(statuts.statut([t(1, titre="x" * 60)], M, 30, False)["bulle"], "x" * 40 + "…")

    def test_sans_nouvelles(self):
        self.assertEqual(statuts.statut([t(125)], M, 30, False),
                         {"statut": "sans_nouvelles", "bulle": "sans nouvelles depuis 2 h"})

    def test_limite_de_fraicheur(self):
        self.assertEqual(statuts.statut([t(30)], M, 30, False)["statut"], "travail")
        self.assertEqual(statuts.statut([t(31)], M, 30, False)["statut"], "sans_nouvelles")

    def test_pause(self):
        self.assertEqual(statuts.statut([t(125)], M, 30, True), {"statut": "libre", "bulle": ""})
        self.assertEqual(statuts.statut([t(5)], M, 30, True)["statut"], "travail")

    def test_date_illisible(self):
        self.assertEqual(statuts.statut([{"id": "a", "titre": "A", "active": True, "maj": "?"}], M, 30, False),
                         {"statut": "sans_nouvelles", "bulle": "sans nouvelles"})

    def test_libre(self):
        self.assertEqual(statuts.statut([t(1, active=False)], M, 30, False), {"statut": "libre", "bulle": ""})
        self.assertEqual(statuts.statut([], M, 30, False), {"statut": "libre", "bulle": ""})

    def test_present(self):
        self.assertTrue(statuts.present({"cle": "a"}, [t(23 * 60, active=False)], M))
        self.assertFalse(statuts.present({"cle": "a"}, [t(25 * 60, active=False)], M))
        self.assertFalse(statuts.present({"cle": "a"}, [], M))
        self.assertTrue(statuts.present({"cle": "a", "permanent": True}, [], M))
        self.assertTrue(statuts.present({"cle": "a", "chef": True}, [], M))
        self.assertTrue(statuts.present({"cle": "a"}, [t(9999)], M))

    def test_factory_inactive(self):
        f = statuts.factory({"etat": "en marche"}, [t(45)], M, 30)
        self.assertTrue(f["inactive"])
        f = statuts.factory({"etat": "en pause"}, [t(45)], M, 30)
        self.assertFalse(f["inactive"])
        f = statuts.factory({"etat": "en marche"}, [], M, 30)
        self.assertEqual((f["inactive"], f["derniere_activite"]), (True, None))

    def test_factory_active_et_champs(self):
        f = statuts.factory({"etat": "en marche", "depuis": "2026-11-10T09:00:00"}, [t(5), t(50)], M, 30)
        self.assertFalse(f["inactive"])
        self.assertEqual(f["derniere_activite"], (M - timedelta(minutes=5)).isoformat())
        self.assertEqual((f["etat"], f["depuis"]), ("en marche", "2026-11-10T09:00:00"))


if __name__ == "__main__":
    unittest.main()
