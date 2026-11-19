"""Étape licence Unity de la plateforme : geste guidé sans unity.ulf, envoi en stdin avec, licence jamais visible."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plateforme  # noqa: E402
from test_plateforme import Base, ClientFactice, SshFactice  # noqa: E402

LICENCE = ('<?xml version="1.0" encoding="UTF-8"?>\n<root>\n  <License id="Terms">\n'
           '    <DeveloperData Value="AAAABBBBCCCCDDDDEEEE"/>\n  </License>\n</root>\n')
LIGNE = 'DeveloperData Value="AAAABBBBCCCCDDDDEEEE"'
ECHAPPEE = json.dumps(LICENCE)[1:-1]


class SshLicence(SshFactice):
    """Fait répondre l'étape licence à la demande : `reponse(commande, stdin)` renvoie (code, sortie, erreur)."""
    def __init__(self, reponse=None):
        super().__init__()
        self.reponse, self.recus = reponse, []

    def executer(self, hote, commande, cle, stdin=None, delai=60):
        if "--etape licence" in commande:
            self.recus.append((commande, stdin))
            if self.reponse:
                return self.reponse(commande, stdin)
        return super().executer(hote, commande, cle, stdin, delai)


def _json(statut, detail):
    return 0, json.dumps({"etape": "licence", "statut": statut, "detail": detail}) + "\n", ""


class TestLicence(Base):
    def licence(self, etat):
        return [e for e in etat["etapes"] if e["id"] == "licence"][0]

    def jamais_visible(self, *textes):
        for t in textes:
            for forme in (LICENCE, ECHAPPEE, LIGNE, LICENCE.strip()):
                self.assertNotIn(forme, t)

    def cache(self):
        return (self.dossier / "plateforme.json").read_text(encoding="utf-8")

    def test_sans_ulf_geste_guide_avec_lien(self):
        ssh = SshLicence()
        etat = self.lancer(ClientFactice(), ssh, accord=True)
        lic = self.licence(etat)
        self.assertEqual(lic["statut"], "a_faire")
        for mot in ("Unity Hub", "Unity_lic.ulf", str(self.dossier / "unity.ulf"), "6000.6.7f1", "Pro/Plus",
                    "https://docs.unity3d.com/6000.6/Documentation/Manual/ManualActivationGuide.html"):
            self.assertIn(mot, lic["geste"])
        self.assertEqual(ssh.recus, [])
        self.assertTrue(etat["pret"] and etat["pret_sans_unity"])

    def test_avec_ulf_active_via_stdin_et_masque_la_sortie(self):
        (self.dossier / "unity.ulf").write_bytes(LICENCE.replace("\n", "\r\n").encode("utf-8"))
        ssh = SshLicence(lambda c, s: _json("fait", f"activée {s}"))
        etat = self.lancer(ClientFactice(), ssh, accord=True)
        self.assertEqual(len(ssh.recus), 1)
        commande, stdin = ssh.recus[0]
        self.assertEqual(stdin, LICENCE.replace("\n", "\r\n"))
        self.assertNotIn("AAAABBBB", commande)
        self.assertEqual(self.licence(etat)["statut"], "fait")
        self.jamais_visible(json.dumps(etat), self.cache())

    def test_licence_refusee_par_unity_donne_statut_bloque_lisible(self):
        (self.dossier / "unity.ulf").write_text(LICENCE, encoding="utf-8")
        ssh = SshLicence(lambda c, s: _json("bloque", "Activation non prouvée dans le conteneur de test."))
        etat = self.lancer(ClientFactice(), ssh, accord=True)
        lic = self.licence(etat)
        self.assertEqual(lic["statut"], "bloque")
        self.assertIn("non prouvée", lic["detail"])
        self.assertTrue(lic["geste"])
        self.assertTrue(etat["pret"] and etat["pret_sans_unity"])      # facultative : ne retire jamais « prêt »

    def test_ulf_jamais_dans_etat_ni_journal(self):
        (self.dossier / "unity.ulf").write_text(LICENCE, encoding="utf-8")
        # écho brut, écho échappé JSON, écho d'une seule ligne sur stderr, sortie illisible
        for reponse in (lambda c, s: _json("bloque", f"refus {LICENCE}"),
                        lambda c, s: _json("bloque", f"refus {ECHAPPEE}"),
                        lambda c, s: (1, "pas du json", f"erreur : {LIGNE} invalide"),
                        lambda c, s: _json("bloque", f"refus {LIGNE}")):
            etat = self.lancer(ClientFactice(), SshLicence(reponse), accord=True)
            self.assertEqual(self.licence(etat)["statut"], "bloque")
            self.jamais_visible(json.dumps(etat), json.dumps(etat, ensure_ascii=False), self.cache())
            self.assertIn("***", json.dumps(etat))
            (self.dossier / "plateforme.json").unlink()

    def test_licence_dans_un_message_d_exception_masquee(self):
        (self.dossier / "unity.ulf").write_text(LICENCE, encoding="utf-8")

        def casse(c, s):
            raise plateforme.ErreurSsh(f"ssh a échoué : {LICENCE} / {ECHAPPEE}")
        etat = self.lancer(ClientFactice(), SshLicence(casse), accord=True)
        self.assertEqual(self.licence(etat)["statut"], "bloque")
        self.jamais_visible(json.dumps(etat), self.cache())

    def test_cli_n_affiche_jamais_la_licence(self):
        (self.dossier / "unity.ulf").write_text(LICENCE, encoding="utf-8")
        brut = {"etat": plateforme.calculer_etat({"licence": {"statut": "bloque", "detail": f"x {ECHAPPEE} y {LIGNE}"}})}
        (self.dossier / "plateforme.json").write_text(json.dumps(brut), encoding="utf-8")
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            plateforme.main(["etat", "--dossier", str(self.dossier)])
        self.jamais_visible(sortie.getvalue())
        self.assertIn("***", sortie.getvalue())

    def test_ulf_vide_bloque_sans_appel_distant(self):
        (self.dossier / "unity.ulf").write_text("  \n", encoding="utf-8")
        ssh = SshLicence()
        etat = self.lancer(ClientFactice(), ssh, accord=True)
        self.assertEqual(self.licence(etat)["statut"], "bloque")
        self.assertEqual(ssh.recus, [])


if __name__ == "__main__":
    unittest.main()
