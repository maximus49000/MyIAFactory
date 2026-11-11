"""La mise en place, le bureau commun, la réparation. HOME et USERPROFILE sont temporaires ; git est simulé."""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from unittest import mock

from bureau import reglages
from installation import dossier, mise_en_place as mep
from installation.dossier import Echec
from orchestrateur import factory as fa
from orchestrateur import fiches
from tests.inst_aide import AvecMaison, instantane, proposition_valide

MAINTENANT = datetime(2026, 11, 11, 10, 0)
RACINE = Path(__file__).resolve().parent.parent


class Base(AvecMaison):
    def lier_skill(self):
        """Le dossier stable pointe sur ce dépôt (si le test n'a pas préparé sa propre skill) : la vérification lance
        alors vraiment la commande du relevé du bureau. Le lien est retiré avant le dossier temporaire."""
        s = dossier.skill()
        if s.exists():
            return
        dossier.creer_lien(RACINE, s)
        self.addCleanup(os.rmdir, s)   # retire la jonction seule, jamais ce qu'elle désigne

    def appliquer(self, **extra):
        self.lier_skill()
        return mep.appliquer(proposition_valide(self.projet, **extra), MAINTENANT, git=self.git_simule,
                             adresses=self.adresses)

    def adresses(self):
        return {"tailscale": "100.64.0.7", "reseau_local": "192.168.1.20"}

    def git_simule(self, args, cwd):
        return 0, ""

    def autre_projet(self, nom):
        d = self.base / nom / ".factory"
        d.mkdir(parents=True)
        r = d / "reglages.json"
        r.write_text("{}", encoding="utf-8")
        return r


class TestAppliquer(Base):
    def test_appliquer_projet_vide(self):
        r = self.appliquer()
        f = fa.lire(self.projet / ".factory" / "factory.json")
        self.assertEqual(f["skill"], (self.maison / "MyIAFactory" / "skill").resolve())
        self.assertEqual(f["agents_locaux_max"], 2)
        self.assertEqual([s["id"] for s in f["services"]], ["dev", "qa", "facturation"])
        brut = json.loads((self.projet / ".factory" / "factory.json").read_text(encoding="utf-8"))
        self.assertEqual(brut["skill"], "~/MyIAFactory/skill")
        self.assertEqual(brut["catalogues"]["*"]["commande"][1], "~/MyIAFactory/skill/orchestrateur/outil.py")
        self.assertNotIn("justification", brut["flux"][0])
        lues = fiches.lire_toutes(f["fiches"])
        self.assertEqual([x["cle"] for x in lues], ["dev-1", "relecteur-1"])
        self.assertEqual(lues[0]["prenom"], "Noé")
        self.assertTrue((f["fiches"] / "briefs" / "relecteur.md").is_file())
        regl = json.loads((self.projet / ".factory" / "reglages.json").read_text(encoding="utf-8"))
        self.assertEqual(regl["releve"]["commande"][1], "~/MyIAFactory/skill/orchestrateur/outil.py")
        self.assertEqual(regl["charge_max"], 70)
        self.assertTrue(regl["prix_automatiques"])
        self.assertEqual(regl["orchestrateur"], "factory.json")
        controles = (self.projet / ".factory" / "controles.md").read_text(encoding="utf-8")
        self.assertIn("- C1 · 2026-11-11 · installation : Le rangement ne perd aucun fichier.", controles)
        self.assertIn("- C2 · 2026-11-11 · installation : Un nom en double est signalé.", controles)
        for d in ("pieces", "captures", "livrables", "methodes", "documents"):
            self.assertTrue((self.projet / ".factory" / d).is_dir(), d)
        self.assertFalse((self.projet / ".factory.tmp").exists())
        self.assertTrue(r["pret"], r["verification"])
        self.assertTrue(r["verification"])
        self.assertIn(str(self.projet / ".factory" / "factory.json"), r["message_orchestrateur"])
        # le message n'est pas versionné : il donne la skill en chemin absolu (PowerShell ne développe pas « ~ »)
        self.assertNotIn("~", r["message_orchestrateur"])
        self.assertIn(str(dossier.skill() / "orchestrateur" / "consignes.md"), r["message_orchestrateur"])
        self.assertIn(f"`<skill>` vaut `{dossier.skill()}`", r["message_orchestrateur"])
        self.assertEqual(r["agents_cloud"], [])
        self.assertFalse(r["relancer_bureau"])
        self.assertEqual(r["bureau"], str(dossier.bureau()))

    def test_rien_avant_appliquer(self):
        avant = instantane(self.projet)
        with self.assertRaises(Echec):
            mep.appliquer(proposition_valide(self.projet, agents_locaux_max=0), MAINTENANT)
        self.assertEqual(instantane(self.projet), avant)
        self.assertFalse(dossier.bureau().exists())

    def test_appliquer_deux_fois_refuse(self):
        self.appliquer()
        avant = instantane(self.projet)
        bureau_avant = dossier.bureau().read_bytes()
        with self.assertRaises(Echec) as c:
            self.appliquer()
        self.assertIn("Déjà installé : lancez la réparation.", str(c.exception))
        self.assertEqual(instantane(self.projet), avant)
        self.assertEqual(dossier.bureau().read_bytes(), bureau_avant)

    def test_facturation_non(self):
        self.appliquer(facturation=False)
        f = fa.lire(self.projet / ".factory" / "factory.json")
        self.assertNotIn("facturation", [s["id"] for s in f["services"]])
        regl = json.loads((self.projet / ".factory" / "reglages.json").read_text(encoding="utf-8"))
        self.assertFalse(regl["prix_automatiques"])

    def test_conseils_ecrits_par_la_mise_en_place(self):
        conseils = {"voix": [{"id": "elevenlabs", "raison": " Voix naturelles. "}]}
        self.appliquer(partenaires_conseilles=conseils)
        lu = json.loads((self.projet / ".factory" / "partenaires.json").read_text(encoding="utf-8"))
        self.assertEqual(lu, {"besoins": {"voix": [{"id": "elevenlabs", "raison": "Voix naturelles."}]}})

    def test_sans_conseils_aucun_fichier(self):
        self.appliquer()
        self.assertFalse((self.projet / ".factory" / "partenaires.json").exists())

    def test_agents_cloud_rendus(self):
        p = proposition_valide(self.projet, cloud=True)
        p["agents"][0].update(lieu="cloud", environnement=["Python"])
        r = mep.appliquer(p, MAINTENANT)
        self.assertEqual(r["agents_cloud"], [{"cle": "dev-1", "role": "dev", "modele": "Sonnet",
                                              "environnement": ["Python"]}])

    def test_genre_connu_ecrit(self):
        genres = dossier.skill() / "orchestrateur" / "memoire" / "genres"
        genres.mkdir(parents=True)
        (genres / "outils.md").write_text("# Genre : outils\nDomaine : des outils\n", encoding="utf-8")
        r = self.appliquer(genre="outils")
        self.assertEqual(fa.lire(self.projet / ".factory" / "factory.json")["genre"], "outils")
        self.assertIsNone(r.get("genre_raison"))

    def test_genre_inconnu_refuse(self):
        with self.assertRaises(Echec):
            self.appliquer(genre="inconnu")
        self.assertFalse((self.projet / ".factory").exists())

    def test_genre_nouveau_cree(self):
        (dossier.skill() / "orchestrateur" / "memoire").mkdir(parents=True)
        self.appliquer(genre="outils", genre_nouveau={"description": "Des petits outils"})
        self.assertEqual(fa.lire(self.projet / ".factory" / "factory.json")["genre"], "outils")
        self.assertTrue((dossier.skill() / "orchestrateur" / "memoire" / "genres" / "outils.md").is_file())

    def test_genre_nouveau_echoue_reste_nul(self):
        (dossier.skill() / "orchestrateur" / "memoire").mkdir(parents=True)
        r = mep.appliquer(proposition_valide(self.projet, genre="outils", genre_nouveau={"description": "Des outils"}),
                          MAINTENANT, git=lambda args, cwd: (1, "conflit"))
        self.assertIsNone(fa.lire(self.projet / ".factory" / "factory.json")["genre"])
        self.assertIn("conflit", r["genre_raison"])

    def test_chemin_espaces_accents(self):
        r = self.appliquer()
        b = reglages.lire_bureau(dossier.bureau())
        self.assertEqual(b["projets"][0]["chemin"].resolve(), (self.projet / ".factory" / "reglages.json").resolve())
        self.assertTrue(r["pret"], r["verification"])
        # le bureau lance la commande du relevé telle qu'elle est déclarée (« ~ », espaces, accents) et la lit
        self.assertIn("ok le bureau lit le relevé du projet", r["verification"])

    def test_bureau_qui_ne_lit_pas_le_releve_pas_pret(self):
        from unittest import mock
        with mock.patch("bureau.releve.obtenir", return_value=(None, "La commande du relevé a échoué (code 9).")):
            r = self.appliquer()
        self.assertFalse(r["pret"])
        self.assertTrue(any(x.startswith("ÉCART le bureau lit le relevé") and "code 9" in x for x in r["verification"]))

    def test_echec_au_milieu_rien_ne_reste(self):
        (self.projet / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        autre = self.autre_projet("autre")
        dossier.racine().mkdir(parents=True)
        dossier.bureau().write_text(json.dumps({"port": 8770, "projets": [str(autre)]}), encoding="utf-8")
        avant, bureau_avant = instantane(self.projet), dossier.bureau().read_bytes()
        vrai, n = fiches.ecrire_fiche, []

        def casse(f):
            n.append(1)
            if len(n) == 2:
                raise OSError(28, "disque plein")
            vrai(f)
        with mock.patch.object(fiches, "ecrire_fiche", casse), self.assertRaises(OSError):
            self.appliquer()
        self.assertEqual(instantane(self.projet), avant)
        self.assertFalse((self.projet / ".factory").exists())
        self.assertFalse((self.projet / ".factory.tmp").exists())
        self.assertEqual(dossier.bureau().read_bytes(), bureau_avant)

    def test_echec_a_l_inscription_defait_tout(self):
        (self.projet / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        avant = instantane(self.projet)
        with mock.patch.object(mep, "inscrire", side_effect=OSError("disque plein")), self.assertRaises(OSError):
            self.appliquer()
        self.assertEqual(instantane(self.projet), avant)


class TestBureau(Base):
    def test_inscription_bureau_nouveau(self):
        r = self.appliquer()
        d = json.loads(dossier.bureau().read_text(encoding="utf-8"))
        self.assertEqual(d["port"], 8770)
        self.assertEqual(len(d["projets"]), 1)
        self.assertTrue(Path(d["projets"][0]["chemin"]).is_absolute())
        self.assertFalse(r["relancer_bureau"])

    def test_inscription_bureau_existant(self):
        autre = self.autre_projet("autre")
        dossier.racine().mkdir(parents=True)
        dossier.bureau().write_text(json.dumps({"port": 9000, "projets": [str(autre)]}), encoding="utf-8")
        r = self.appliquer()
        self.assertFalse(r["relancer_bureau"])   # essai réel : le bureau en marche voit le projet sans redémarrer
        b = reglages.lire_bureau(dossier.bureau())
        self.assertEqual(b["port"], 9000)
        self.assertEqual(len(b["projets"]), 2)

    def test_deja_inscrit(self):
        r = self.autre_projet("autre")
        self.assertTrue(mep.inscrire(dossier.bureau(), r))
        avant = dossier.bureau().read_bytes()
        self.assertFalse(mep.inscrire(dossier.bureau(), r))
        self.assertEqual(dossier.bureau().read_bytes(), avant)

    def test_bureau_plein(self):
        dossier.racine().mkdir(parents=True)
        dossier.bureau().write_text(json.dumps({"projets": [str(self.autre_projet(f"p{i}")) for i in range(12)]}),
                                    encoding="utf-8")
        avant = dossier.bureau().read_bytes()
        with self.assertRaises(Echec) as c:
            self.appliquer()
        self.assertIn("Le bureau suit déjà 12 projets.", str(c.exception))
        self.assertEqual(dossier.bureau().read_bytes(), avant)
        self.assertFalse((self.projet / ".factory").exists())

    def test_bureau_illisible_rien_ecrit(self):
        dossier.racine().mkdir(parents=True)
        dossier.bureau().write_text("{pas du json", encoding="utf-8")
        with self.assertRaises(Echec):
            self.appliquer()
        self.assertEqual(dossier.bureau().read_text(encoding="utf-8"), "{pas du json")
        self.assertEqual(instantane(self.projet), {})


class TestAcces(Base):
    MOBILE = {"supports": ["ordinateur", "mobile"], "acces": {"tailscale": True, "reseau_local": False}}

    def test_ordinateur_seul_rien_d_ouvert(self):
        r = self.appliquer()
        self.assertEqual(r["acces"], {"tailscale": None, "reseau_local": None})
        self.assertNotIn("acces", json.loads(dossier.bureau().read_text(encoding="utf-8")))
        self.assertEqual(reglages.lire_bureau(dossier.bureau())["acces"], {"tailscale": False, "reseau_local": False})

    def test_acces_ecrit_dans_le_bureau(self):
        r = self.appliquer(**self.MOBILE)
        self.assertEqual(reglages.lire_bureau(dossier.bureau())["acces"], {"tailscale": True, "reseau_local": False})
        self.assertEqual(r["acces"], {"tailscale": "100.64.0.7", "reseau_local": None})
        self.assertFalse(r["relancer_bureau"])   # bureau neuf : il n'était pas lancé

    def test_acces_fusionne(self):
        autre = self.autre_projet("autre")
        dossier.racine().mkdir(parents=True)
        dossier.bureau().write_text(json.dumps({"projets": [str(autre)], "acces": {"reseau_local": True}}),
                                    encoding="utf-8")
        r = self.appliquer(**self.MOBILE)
        self.assertEqual(reglages.lire_bureau(dossier.bureau())["acces"], {"tailscale": True, "reseau_local": True})
        self.assertEqual(r["acces"], {"tailscale": "100.64.0.7", "reseau_local": "192.168.1.20"})
        self.assertTrue(r["relancer_bureau"])

    def test_acces_deja_ouvert_ne_relance_pas(self):
        self.appliquer(**self.MOBILE)
        r = mep.reparer(self.projet, TestReparer.CALIBRAGE, acces={"tailscale": True, "reseau_local": False},
                        adresses=self.adresses)
        self.assertEqual(r["corrections"], [])
        self.assertFalse(r["relancer_bureau"])
        self.assertEqual(r["acces"], {"tailscale": "100.64.0.7", "reseau_local": None})

    def test_reparer_ouvre_un_acces(self):
        self.appliquer()
        r = mep.reparer(self.projet, TestReparer.CALIBRAGE, acces={"tailscale": False, "reseau_local": True},
                        adresses=self.adresses)
        self.assertEqual(reglages.lire_bureau(dossier.bureau())["acces"], {"tailscale": False, "reseau_local": True})
        self.assertEqual(r["acces"], {"tailscale": None, "reseau_local": "192.168.1.20"})
        self.assertTrue(r["relancer_bureau"])
        self.assertTrue(any("réseau local" in c for c in r["corrections"]), r["corrections"])


class TestGitignore(Base):
    def lire(self):
        return (self.projet / ".gitignore").read_text(encoding="utf-8")

    def test_gitignore_absent(self):
        self.appliquer()
        t = self.lire()
        self.assertIn("# MyIAFactory : fichiers propres à la machine\n.factory/equipe.json\n"
                      ".factory/*-historique.jsonl\n.env\n.factory/presence.json\n", t)   # clés et présence : hors du dépôt

    def test_gitignore_ancienne_regle(self):
        (self.projet / ".gitignore").write_text("node_modules/\n.factory/\n/.factory\ndist", encoding="utf-8")
        self.appliquer()
        lignes = self.lire().splitlines()
        self.assertNotIn(".factory/", lignes)
        self.assertNotIn("/.factory", lignes)
        self.assertIn("dist", lignes)
        self.assertIn("node_modules/", lignes)
        self.assertIn(".factory/equipe.json", lignes)

    def test_gitignore_variantes_de_l_ancienne_regle(self):
        variantes = [".factory/*", ".factory/**", "/.factory/*", "/.factory/**", "**/.factory", "**/.factory/",
                     ".factory/ ", "  .factory"]
        (self.projet / ".gitignore").write_text("\n".join(variantes + ["garde.txt"]) + "\n", encoding="utf-8")
        self.assertTrue(mep.regler_gitignore(self.projet))
        lignes = [x.strip() for x in self.lire().splitlines()]
        for v in variantes:
            self.assertNotIn(v.strip(), lignes, v)
        self.assertIn("garde.txt", lignes)

    def test_gitignore_idempotent(self):
        (self.projet / ".gitignore").write_text("node_modules/", encoding="utf-8")
        self.assertTrue(mep.regler_gitignore(self.projet))
        une = self.lire()
        self.assertFalse(mep.regler_gitignore(self.projet))
        self.assertEqual(self.lire(), une)
        self.assertEqual(une.count("# MyIAFactory"), 1)
        self.assertTrue(une.startswith("node_modules/\n"))


class TestReparer(Base):
    CALIBRAGE = {"charge_max": 60, "agents_locaux_max": 3, "source": "machine", "explication": ""}

    def projet_a_la_main(self):
        """Un projet branché à la main : chemins absolus, pas de limite d'agents, pas de bureau commun."""
        fd = self.projet / ".factory"
        (fd / "fiches" / "briefs").mkdir(parents=True)
        shutil.copy(RACINE / "exemples" / "projet-neuf" / "fiches" / "dev-1.md", fd / "fiches" / "dev-1.md")
        outil = str(RACINE / "orchestrateur" / "outil.py")
        f = {"nom": "Ancien", "skill": str(RACINE), "genre": None, "mots_interdits": [],
             "services": [{"id": "dev", "nom": "Dev"}],
             "flux": [{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}],
             "reglages": "reglages.json",
             "catalogues": {"*": {"commande": ["python", outil, "--factory", "factory.json", "lancer", "catalogue",
                                               "{fonctionnalite}"]},
                            "decor": {"fichier": "decor.json"}},
             "commandes": {"releve": ["python", "outils/mon_releve.py"],
                           "depart": ["python", "C:/ailleurs/orchestrateur/outil.py", "depart"]}}
        (fd / "factory.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
        regl = {"releve": {"commande": ["python", outil.replace("/", "\\"), "--factory", "factory.json", "lancer",
                                        "releve"]},
                "actions": {"commande": ["python", "../../orchestrateur/outil.py", "lancer", "actions"]},
                "images": {"racines": ["pieces"]}, "orchestrateur": "factory.json", "port": 8771}
        (fd / "reglages.json").write_text(json.dumps(regl), encoding="utf-8")
        (self.projet / ".gitignore").write_text(".factory/\n", encoding="utf-8")
        return fd

    def test_reparer_chemins_absolus(self):
        fd = self.projet_a_la_main()
        r = mep.reparer(self.projet, self.CALIBRAGE)
        self.assertTrue(r["corrections"])
        brut = json.loads((fd / "factory.json").read_text(encoding="utf-8"))
        self.assertEqual(brut["skill"], "~/MyIAFactory/skill")
        self.assertEqual(brut["catalogues"]["*"]["commande"][1], "~/MyIAFactory/skill/orchestrateur/outil.py")
        self.assertEqual(brut["catalogues"]["decor"], {"fichier": "decor.json"})
        self.assertEqual(brut["agents_locaux_max"], 3)
        regl = json.loads((fd / "reglages.json").read_text(encoding="utf-8"))
        self.assertEqual(regl["releve"]["commande"][1], "~/MyIAFactory/skill/orchestrateur/outil.py")
        self.assertEqual(regl["actions"]["commande"][1], "~/MyIAFactory/skill/orchestrateur/outil.py")
        self.assertEqual(regl["port"], 8771)
        self.assertIn(".factory/equipe.json", (self.projet / ".gitignore").read_text(encoding="utf-8").splitlines())
        self.assertNotIn(".factory/", (self.projet / ".gitignore").read_text(encoding="utf-8").splitlines())
        self.assertTrue((fd / "pieces").is_dir())
        self.assertEqual(reglages.lire_bureau(dossier.bureau())["projets"][0]["chemin"].resolve(),
                         (fd / "reglages.json").resolve())
        self.assertIsInstance(r["verification"], list)
        fa.lire(fd / "factory.json")

    def test_reparer_garde_les_adaptateurs(self):
        fd = self.projet_a_la_main()
        avant = json.loads((fd / "factory.json").read_text(encoding="utf-8"))["commandes"]
        mep.reparer(self.projet, self.CALIBRAGE)
        self.assertEqual(json.loads((fd / "factory.json").read_text(encoding="utf-8"))["commandes"], avant)

    def test_reparer_idempotent(self):
        self.projet_a_la_main()
        mep.reparer(self.projet, self.CALIBRAGE)
        fd = self.projet / ".factory"
        avant = instantane(fd)
        r = mep.reparer(self.projet, self.CALIBRAGE)
        self.assertEqual(r["corrections"], [])
        self.assertEqual(instantane(fd), avant)

    def test_reparer_garde_la_limite_existante(self):
        self.appliquer()
        r = mep.reparer(self.projet, self.CALIBRAGE)
        self.assertEqual(r["corrections"], [])
        self.assertEqual(fa.lire(self.projet / ".factory" / "factory.json")["agents_locaux_max"], 2)
        self.assertTrue(r["pret"], r["verification"])

    def test_reparer_sans_installation(self):
        with self.assertRaises(Echec):
            mep.reparer(self.projet, self.CALIBRAGE)


class TestOrganisation(Base):
    def test_ecrire_organisation_ajoute_service_et_etape(self):
        self.appliquer()
        chemin = self.projet / ".factory" / "factory.json"
        services = [{"id": "dev", "nom": "Dev"}, {"id": "qa", "nom": "QA"}, {"id": "facturation", "nom": "Facturation"},
                    {"id": "son", "nom": "Son"}]
        flux = fa.lire(chemin)["flux"] + [{"id": "mixage", "nom": "Mixage", "role": "mixeur", "service": "son"}]
        agents = [{"cle": "mixeur-1", "role": "mixeur", "service": "son", "modele": "Haiku", "lieu": "local",
                   "texte": "Mixe."}]
        mep.ecrire_organisation(chemin, services, flux, agents, {"mixeur": "# Brief du rôle : mixeur"})
        f = fa.lire(chemin)
        self.assertEqual(f["flux"][-1]["id"], "mixage")
        self.assertEqual(f["agents_locaux_max"], 2)
        self.assertIn("mixeur-1", [x["cle"] for x in fiches.lire_toutes(f["fiches"])])
        self.assertTrue((f["fiches"] / "briefs" / "mixeur.md").is_file())

    def test_ecrire_organisation_refuse_sans_rien_ecrire(self):
        self.appliquer()
        chemin = self.projet / ".factory" / "factory.json"
        avant = instantane(self.projet / ".factory")
        flux = [{"id": "mixage", "nom": "Mixage", "role": "mixeur", "service": "son"}]
        with self.assertRaises(Echec):
            mep.ecrire_organisation(chemin, [{"id": "dev", "nom": "Dev"}], flux, [], {})
        with self.assertRaises(Echec):
            mep.ecrire_organisation(chemin, [{"id": "son", "nom": "Son"}], flux,
                                    [{"cle": "dev-1", "role": "mixeur", "service": "son", "modele": "Haiku",
                                      "lieu": "local", "texte": "x"}], {"mixeur": "x"})
        with self.assertRaises(Echec):
            mep.ecrire_organisation(chemin, [{"id": "son", "nom": "Son"}], flux,
                                    [{"cle": "mixeur-1", "role": "mixeur", "service": "son", "modele": "Fable",
                                      "lieu": "local", "texte": "x"}], {"mixeur": "x"})
        self.assertEqual(instantane(self.projet / ".factory"), avant)


if __name__ == "__main__":
    import unittest
    unittest.main()
