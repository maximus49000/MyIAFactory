"""Mandataire HTTPS du script hôte (`serveur_ovh/services/service.py`, commandes `mandataire` et `mandataire-supprimer`) : un Caddy
épinglé par empreinte sur les ports 80 et 443 relaie un domaine vers le port du service. Faux hôte (docker, ufw, sonde HTTP)."""
import json
import re
import unittest

from tests.test_serveur_service_hote import (Base, COMMIT, FauxHote, S, _sources)

DOMAINE = "203-0-113-10.sslip.io"


class HoteHttps(FauxHote):
    """Le faux hôte sait sonder une adresse https (sans port) : répond selon que le mandataire tourne."""

    def __init__(self):
        super().__init__()
        self.https_ok = True

    def http(self, url, jeton=None, delai=3):
        if url.startswith("https://"):
            actif = MANDATAIRE_ACTIF(self)
            return 200 if (actif and self.https_ok and url.endswith("/sante")) else None
        return super().http(url, jeton, delai)


def MANDATAIRE_ACTIF(hote):
    c = hote.conteneurs.get(S.MANDATAIRE_NOM)
    return bool(c and c["en_marche"])


class Mandataire(Base):
    def setUp(self):
        super().setUp()
        self.hote = HoteHttps()

    def service_en_marche(self, projet="fm-stats"):
        self.preparer(projet)
        code, rep, _ = self.appeler("deployer", projet, COMMIT)
        self.assertEqual(code, 0, rep)

    def test_met_le_service_en_https(self):
        self.service_en_marche()
        code, rep, _ = self.appeler("mandataire", "fm-stats", DOMAINE)
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["adresse"], "https://" + DOMAINE)
        c = self.hote.conteneurs[S.MANDATAIRE_NOM]
        self.assertEqual(c["image"], S.MANDATAIRE_IMAGE)
        self.assertIn("@sha256:", c["image"])                                  # image épinglée par empreinte
        self.assertEqual(sorted(r for r in self.hote.regles if r in ("80/tcp", "443/tcp")), ["443/tcp", "80/tcp"])

    def test_le_conteneur_est_durci(self):
        self.service_en_marche()
        self.appeler("mandataire", "fm-stats", DOMAINE)
        argv = " ".join(self.hote.conteneurs[S.MANDATAIRE_NOM]["argv"])
        for attendu in ("--read-only", "--cap-drop ALL", "--cap-add NET_BIND_SERVICE", "--security-opt no-new-privileges",
                        "--memory 256m", "--pids-limit 128", "--network host", "--restart unless-stopped"):
            self.assertIn(attendu, argv)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("docker.sock", argv)

    def test_le_caddyfile_relaie_vers_le_port_du_service_seulement(self):
        self.service_en_marche()
        self.appeler("mandataire", "fm-stats", DOMAINE)
        texte = (self.racine / "mandataire" / "Caddyfile").read_text("utf-8")
        port = S.port_du_projet(self.racine, "fm-stats")
        self.assertIn(f"{DOMAINE} {{", texte)
        self.assertIn(f"reverse_proxy 127.0.0.1:{port}", texte)
        self.assertIn("admin off", texte)                                        # pas d'API d'administration ouverte
        self.assertEqual(len(re.findall("reverse_proxy", texte)), 1)

    def test_deux_services_deux_domaines_un_seul_mandataire(self):
        self.service_en_marche("fm-stats")
        self.service_en_marche("autre-service")
        self.appeler("mandataire", "fm-stats", DOMAINE)
        code, rep, _ = self.appeler("mandataire", "autre-service", "autre.sslip.io")
        self.assertEqual(code, 0, rep)
        texte = (self.racine / "mandataire" / "Caddyfile").read_text("utf-8")
        self.assertEqual(len(re.findall("reverse_proxy", texte)), 2)
        self.assertTrue(any(a[:5] == ["sudo", "-n", "docker", "exec", S.MANDATAIRE_NOM] for a in self.hote.appels))  # rechargé
        self.assertEqual(sum(1 for n in self.hote.conteneurs if n == S.MANDATAIRE_NOM), 1)

    def test_un_domaine_ne_sert_qu_un_service(self):
        self.service_en_marche("fm-stats")
        self.service_en_marche("autre-service")
        self.appeler("mandataire", "fm-stats", DOMAINE)
        code, rep, _ = self.appeler("mandataire", "autre-service", DOMAINE)
        self.assertEqual(code, 2, rep)

    def test_refus_d_un_domaine_invalide_ou_d_une_adresse_ip(self):
        self.service_en_marche()
        for d in ("203.0.113.10", "Domaine.Majuscule.com", "a b.com", "evil.com/../x", "x", "a..b.com", "-a.com",
                  "a.com;rm -rf", "a" * 120 + ".com"):
            code, rep, _ = self.appeler("mandataire", "fm-stats", d)
            self.assertEqual(code, 2, (d, rep))
        self.assertNotIn(S.MANDATAIRE_NOM, self.hote.conteneurs)

    def test_refus_si_le_service_n_est_pas_en_marche(self):
        self.preparer()
        code, rep, _ = self.appeler("mandataire", "fm-stats", DOMAINE)
        self.assertEqual(code, 1, rep)
        self.assertIn("déployé", rep["detail"])
        self.assertNotIn(S.MANDATAIRE_NOM, self.hote.conteneurs)

    def test_echec_visible_si_le_certificat_n_est_pas_obtenu(self):
        self.service_en_marche()
        self.hote.https_ok = False
        self.hote.journaux[S.MANDATAIRE_NOM] = "obtaining certificate failed: connection refused"
        S.DELAI_MANDATAIRE_S, ancien = 0, S.DELAI_MANDATAIRE_S
        try:
            code, rep, _ = self.appeler("mandataire", "fm-stats", DOMAINE)
        finally:
            S.DELAI_MANDATAIRE_S = ancien
        self.assertEqual(code, 1, rep)
        self.assertIn("ne répond pas", rep["detail"])
        self.assertIn("certificate", rep["detail"])                              # la raison du mandataire est rendue

    def test_supprimer_le_dernier_relais_arrete_le_mandataire_et_ferme_les_ports(self):
        self.service_en_marche()
        self.appeler("mandataire", "fm-stats", DOMAINE)
        code, rep, _ = self.appeler("mandataire-supprimer", "fm-stats")
        self.assertEqual(code, 0, rep)
        self.assertNotIn(S.MANDATAIRE_NOM, self.hote.conteneurs)
        self.assertNotIn("443/tcp", self.hote.regles)
        self.assertNotIn("80/tcp", self.hote.regles)

    def test_supprimer_un_relais_garde_les_autres(self):
        self.service_en_marche("fm-stats")
        self.service_en_marche("autre-service")
        self.appeler("mandataire", "fm-stats", DOMAINE)
        self.appeler("mandataire", "autre-service", "autre.sslip.io")
        self.appeler("mandataire-supprimer", "fm-stats")
        self.assertIn(S.MANDATAIRE_NOM, self.hote.conteneurs)
        texte = (self.racine / "mandataire" / "Caddyfile").read_text("utf-8")
        self.assertNotIn(DOMAINE, texte)
        self.assertIn("autre.sslip.io", texte)

    def test_supprimer_sans_relais_est_sans_effet(self):
        self.service_en_marche()
        code, rep, _ = self.appeler("mandataire-supprimer", "fm-stats")
        self.assertEqual(code, 0, rep)

    def test_simulation_ne_lance_rien(self):
        self.service_en_marche()
        code, rep, _ = self.appeler("mandataire", "fm-stats", DOMAINE, "--simuler")
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["statut"], "simule")
        self.assertNotIn(S.MANDATAIRE_NOM, self.hote.conteneurs)
        self.assertFalse((self.racine / "mandataire").exists())

    def test_le_domaine_n_est_attendu_que_pour_mandataire(self):
        self.service_en_marche()
        code, rep, _ = self.appeler("etat", "fm-stats", DOMAINE)
        self.assertEqual(code, 2, rep)


if __name__ == "__main__":
    unittest.main()
