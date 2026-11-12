"""Les fichiers joints à un échange : la liste blanche et les plafonds (`bureau.fichiers_joints`), la vérification de la
demande par le bureau, le rangement par l'outil sous `pieces/<fonctionnalité>/`, le relevé, le téléchargement et la
matière transmise aux agents. Aucun appel à un vrai modèle."""
import base64
import json
import unittest
import zipfile
from io import BytesIO

from bureau import demandes, fichiers_joints as fj, releve
from orchestrateur import suivi
from tests.orch_aide import AvecProjet
from tests.test_demandes import R4
from tests.test_moteur_parcours import AvecParcours, CLASSER_MEME, CREATION

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "
WAV = b"RIFF\x10\x00\x00\x00WAVEfmt "
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 8
PDF = b"%PDF-1.7\n"


def zip_octets():
    tampon = BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("notes.txt", "bonjour")
    return tampon.getvalue()


def fichier(nom, contenu, type_="application/octet-stream"):
    return {"nom": nom, "type": type_, "donnees": base64.b64encode(contenu).decode("ascii")}


# Un exemple valide par extension de la liste blanche.
EXEMPLES = {".png": PNG, ".jpg": JPEG, ".jpeg": JPEG, ".gif": GIF, ".webp": WEBP, ".mp4": MP4, ".webm": WEBM,
            ".mp3": b"ID3\x03\x00\x00\x00", ".ogg": b"OggS\x00\x02", ".wav": WAV, ".flac": b"fLaC\x00\x00",
            ".pdf": PDF, ".md": "# Titre\n".encode(), ".txt": b"bonjour", ".csv": b"a,b\n1,2\n", ".json": b"{}",
            ".docx": zip_octets(), ".xlsx": zip_octets(), ".pptx": zip_octets(), ".zip": zip_octets(),
            ".glb": b"glTF\x02\x00\x00\x00", ".gltf": b'{"asset": {"version": "2.0"}}', ".fbx": b"Kaydara FBX Binary  \x00",
            ".obj": b"v 0 0 0\nv 1 0 0\n", ".mtl": b"newmtl matiere\n"}


class TestRegles(unittest.TestCase):
    def test_liste_blanche_documentee(self):
        self.assertEqual(sorted(fj.EXTENSIONS), sorted(EXEMPLES))
        self.assertEqual(fj.MAX_FICHIERS, 8)
        self.assertEqual((fj.MAX_OCTETS_FICHIER, fj.MAX_OCTETS_IMAGE_FIXE, fj.MAX_OCTETS_TOTAL),
                         (25 * 1024 * 1024, 5 * 1024 * 1024, 40 * 1024 * 1024))

    def test_chaque_type_est_accepte_avec_son_contenu(self):
        for ext, contenu in EXEMPLES.items():
            self.assertIsNone(fj.verifier([fichier(f"a{ext.upper()}", contenu)]), ext)
        self.assertIsNone(fj.verifier([]))

    def test_types_refuses(self):
        for nom in ("a.exe", "a.bat", "a.js", "a.html", "a.svg", "a.apk", "a.7z", "a.tar", "a", "a.", ".zip.exe", "a.png.exe"):
            self.assertTrue(fj.verifier([fichier(nom, b"MZ12345")]), nom)

    def test_signature_du_contenu(self):
        faux = {"a.zip": PNG, "a.pdf": b"PK\x03\x04", "a.png": GIF, "a.gif": PNG, "a.mp4": PDF, "a.webp": WAV, "a.wav": WEBP,
                "a.docx": PDF, "a.mp3": PNG, "a.txt": b"abc\x00def", "a.json": b"\x00\x01",
                "a.glb": PNG, "a.fbx": b"MZ\x90\x00", "a.obj": b"\x00\x01binaire"}
        for nom, contenu in faux.items():
            self.assertIn("contenu", fj.verifier([fichier(nom, contenu)]), nom)

    def test_le_type_annonce_par_le_navigateur_ne_compte_pas(self):
        self.assertIsNone(fj.verifier([fichier("a.zip", zip_octets(), "application/x-zip-compressed")]))
        self.assertIsNone(fj.verifier([fichier("a.md", b"# x", "")]))

    def test_plafonds(self):
        self.assertIn("Au plus 8", fj.verifier([fichier(f"{i}.txt", b"x") for i in range(9)]))
        self.assertIsNone(fj.verifier([fichier(f"{i}.txt", b"x") for i in range(8)]))
        self.assertIn("Au plus 8", fj.verifier([fichier("a.txt", b"x")], deja=8))
        self.assertIn("4 images", fj.verifier([fichier(f"{i}.png", PNG) for i in range(5)]))
        self.assertIn("4 images", fj.verifier([fichier("a.png", PNG)], 1, 4))
        self.assertIsNone(fj.verifier([fichier(f"{i}.gif", GIF) for i in range(6)]))   # un gif n'est pas une image fixe
        mo = 1024 * 1024
        self.assertIn("25 Mo", fj.verifier([fichier("g.zip", zip_octets() + b"\x00" * (25 * mo))]))
        self.assertIsNone(fj.verifier([fichier("j.zip", zip_octets() + b"\x00" * (25 * mo - len(zip_octets())))]))
        self.assertIn("5 Mo", fj.verifier([fichier("g.png", PNG + b"\x00" * (5 * mo))]))
        trois = [fichier(f"{i}.zip", zip_octets() + b"\x00" * (14 * mo)) for i in range(3)]
        self.assertIn("40 Mo en tout", fj.verifier(trois))

    def test_noms(self):
        for nom in ("../x.txt", "d/x.txt", "d\\x.txt", "a:b.txt", "a\x01.txt", "a" * 77 + ".txt", "", "  ", None, 3,
                    'a"b.txt', "a|b.txt"):
            self.assertTrue(fj.verifier([fichier(nom if isinstance(nom, str) else "x.txt", b"x") | {"nom": nom}]), repr(nom))
        self.assertTrue(fj.verifier(["a.txt"]))
        self.assertTrue(fj.verifier("x"))
        self.assertTrue(fj.verifier([{"nom": "a.txt", "type": "text/plain"}]))
        self.assertTrue(fj.verifier([fichier("a.txt", b"")]))
        self.assertTrue(fj.verifier([{"nom": "a.txt", "donnees": "!!pas du base64!!"}]))

    def test_nom_sur(self):
        self.assertEqual(fj.nom_sur("Mon rapport (v2).PDF"), "Mon_rapport_v2.pdf")
        self.assertEqual(fj.nom_sur("é à.md"), "é_à.md")
        self.assertEqual(fj.nom_sur("CON.txt"), "_CON.txt")
        self.assertEqual(fj.nom_sur("_.zip"), "fichier.zip")
        self.assertEqual(fj.nom_sur("a.b.c.zip"), "a_b_c.zip")
        self.assertTrue(fj.nom_sur("x" * 80 + ".zip").endswith(".zip"))
        for nom in ("a b.txt", "a<b>.txt", "a*.zip"):
            sur = fj.nom_sur(nom)
            self.assertFalse(set(sur) & set('/\\:*?"<>| '), sur)

    def test_lignes_pour_l_agent(self):
        lignes = fj.lignes_pour_agent([{"chemin": "pieces/f1/a.zip", "nom": "a.zip", "type": "application/zip", "taille": 2048},
                                       {"mauvais": 1}])
        self.assertEqual(lignes, ["  - fichier joint : pieces/f1/a.zip (application/zip, 2,0 Ko)"])
        self.assertEqual(fj.taille_lisible(12 * 1024 * 1024 + 300000), "12 Mo")


class TestDemandes(unittest.TestCase):
    def ok(self, d):
        self.assertIsNone(demandes.verifier(d, R4, frozenset(), None), d)

    def refus(self, d):
        m = demandes.verifier(d, R4, frozenset(), None)
        self.assertTrue(m, d)
        return m

    def test_acceptes_et_refuses(self):
        self.ok({"type": "fonctionnalite", "texte": "Une ville", "fichiers": [fichier("plan.zip", zip_octets())]})
        self.ok({"type": "message", "fonctionnalite": "f5", "texte": "Voir", "fichiers": [fichier("v.mp4", MP4), fichier("a.pdf", PDF)]})
        self.ok({"type": "message", "fonctionnalite": "f5", "texte": "x", "images": [fichier("a.png", PNG, "image/png")],
                 "fichiers": [fichier("b.gif", GIF)]})
        self.refus({"type": "message", "fonctionnalite": "f5", "texte": "x", "fichiers": [fichier("a.exe", b"MZ")]})
        self.refus({"type": "fonctionnalite", "texte": "x", "fichiers": "pas une liste"})
        self.refus({"type": "message", "fonctionnalite": "f5", "texte": "x",
                    "images": [fichier(f"{i}.png", PNG, "image/png") for i in range(4)],
                    "fichiers": [fichier("e.png", PNG)]})                   # 5 images PNG au total
        self.refus({"type": "message", "fonctionnalite": "f5", "texte": "x",
                    "images": [fichier("a.png", PNG, "image/png")], "fichiers": [fichier(f"{i}.txt", b"x") for i in range(8)]})

    def test_nettoyer_ne_garde_que_nom_type_donnees(self):
        d = demandes.nettoyer({"type": "message", "fonctionnalite": "f5", "texte": "x", "mauvais": 1,
                               "fichiers": [{**fichier("a.zip", zip_octets()), "chemin": "/etc/passwd"}]})
        self.assertEqual(set(d), {"type", "fonctionnalite", "texte", "fichiers"})
        self.assertEqual(set(d["fichiers"][0]), {"nom", "type", "donnees"})
        self.assertEqual(demandes.nettoyer({"type": "retour", "tache": "t1", "texte": "x", "fichiers": []}),
                         {"type": "retour", "tache": "t1", "texte": "x"})        # seules ces deux demandes en portent


class TestOutil(AvecProjet):
    def discussion(self):
        return suivi.Suivi(self.dossier / "suivi.json").lire()["fonctionnalites"][0]["discussion"]

    def nouvelle(self, **plus):
        code, sortie = self.outil("actions", entree={"type": "fonctionnalite", "texte": "Une page", "t": "2026-11-10T10:00:00+01:00", **plus})
        self.assertEqual(code, 0, sortie)
        return self.ok("etat")["fonctionnalites"][-1]["id"]

    def test_rangement_sous_pieces_avec_un_nom_sur(self):
        lot = [fichier("Mon rapport (v2).pdf", PDF), fichier("../évil.txt".replace("../", ""), b"x"), fichier("plan.zip", zip_octets()),
               fichier("a.png", PNG), fichier("anim.gif", GIF)]
        f = self.nouvelle(fichiers=lot)
        dossier = self.dossier / "pieces" / f
        noms = sorted(p.name for p in dossier.iterdir())
        self.assertEqual(len(noms), 5)
        self.assertTrue(all(n[:15].replace("-", "").isdigit() for n in noms), noms)
        self.assertTrue(any(n.endswith("-Mon_rapport_v2.pdf") for n in noms), noms)
        m = self.discussion()[0]
        self.assertEqual([x["nom"] for x in m["fichiers"]], ["Mon rapport (v2).pdf", "évil.txt", "plan.zip", "a.png", "anim.gif"])
        self.assertEqual([x["type"] for x in m["fichiers"]],
                         ["application/pdf", "text/plain; charset=utf-8", "application/zip", "image/png", "image/gif"])
        self.assertEqual(m["fichiers"][2]["taille"], len(zip_octets()))
        for x in m["fichiers"]:
            self.assertTrue(x["chemin"].startswith(f"pieces/{f}/"), x)
            self.assertEqual((self.dossier / x["chemin"]).stat().st_size, x["taille"])
        self.assertEqual(len(m["images"]), 1)                        # seule l'image PNG reste dans `images`
        self.assertTrue(m["images"][0].endswith("-a.png"))

    def test_rien_n_est_decompresse_ni_execute(self):
        f = self.nouvelle(fichiers=[fichier("plan.zip", zip_octets())])
        self.assertEqual([p.suffix for p in (self.dossier / "pieces" / f).rglob("*") if p.is_file()], [".zip"])

    def test_images_et_fichiers_ensemble_et_retrocompatibilite(self):
        f = self.nouvelle(images=[{"nom": "ref.png", "type": "image/png", "donnees": base64.b64encode(PNG).decode()}])
        m = self.discussion()[0]
        self.assertEqual(len(m["images"]), 1)
        self.assertNotIn("fichiers", m)
        code, _ = self.outil("actions", entree={"type": "message", "fonctionnalite": f, "texte": "Voici", "fichiers": [fichier("n.md", b"# n")]})
        self.assertEqual(code, 0)
        dernier = self.discussion()[-1]
        self.assertEqual([x["nom"] for x in dernier["fichiers"]], ["n.md"])
        self.assertNotIn("images", dernier)

    def test_releve_porte_les_fichiers_et_reste_valide(self):
        f = self.nouvelle(fichiers=[fichier("plan.zip", zip_octets()), fichier("a.jpg", JPEG)])
        r = self.ok("releve")
        m = r["fonctionnalites"][0]["discussion"][0]
        self.assertEqual([x["nom"] for x in m["fichiers"]], ["plan.zip", "a.jpg"])
        self.assertTrue(m["fichiers"][0]["chemin"].startswith(f"pieces/{f}/"))
        self.assertEqual(releve.valider(r), [])
        r["fonctionnalites"][0]["discussion"][0]["fichiers"] = [{"chemin": "x"}]
        self.assertTrue(any("fichiers" in e for e in releve.valider(r)))

    def test_le_journal_ne_garde_pas_les_donnees(self):
        self.nouvelle(fichiers=[fichier("plan.zip", zip_octets())])
        texte = (self.dossier / "demandes.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(base64.b64encode(zip_octets()).decode(), texte)
        self.assertIn("plan.zip", texte)
        self.assertIn("pieces/f1/", texte)

    def test_refus_de_l_outil(self):
        for plus in ({"fichiers": [fichier("a.exe", b"MZ")]}, {"fichiers": [fichier("a.zip", PNG)]},
                     {"fichiers": [fichier("../x.txt", b"x")]}, {"fichiers": [fichier(f"{i}.txt", b"x") for i in range(9)]},
                     {"fichiers": "x"}, {"fichiers": [{"nom": "a.txt", "donnees": "pas du base64 !"}]}):
            code, sortie = self.outil("actions", entree={"type": "fonctionnalite", "texte": "x", **plus})
            self.assertEqual(code, 1, plus)
            self.assertIsInstance(sortie, str)
        self.assertEqual(self.ok("etat")["fonctionnalites"], [])


class TestMatiere(AvecParcours):
    def setUp(self):
        super().setUp()
        self.reecrire(workflows=[CREATION])      # le workflow du genre existe : la demande va droit au cadrage

    def test_la_matiere_du_cadrage_liste_les_fichiers_joints(self):
        self.demander({"classer_genre": CLASSER_MEME}, texte="Un autre badge pour Twitch",
                      fichiers=[fichier("plan.zip", zip_octets()), fichier("brief.pdf", PDF)])
        (t,) = self.taches(etape="cadrage")
        from moteur import regles
        matiere = regles._matiere(self.projet, self.etat, t)
        self.assertRegex(matiere, r"fichier joint : [^\n]*pieces/f1/[^\n]*plan\.zip \(application/zip, \d+ octets\)")
        self.assertRegex(matiere, r"fichier joint : [^\n]*brief\.pdf \(application/pdf, ")
        self.assertIn("tu peux les lire", matiere)
        self.assertIn("zipfile", matiere)
        self.assertIn("n'exécute jamais", matiere)

    def test_sans_fichier_la_consigne_n_apparait_pas(self):
        self.demander({"classer_genre": CLASSER_MEME}, texte="Un autre badge pour Twitch")
        (t,) = self.taches(etape="cadrage")
        from moteur import regles
        matiere = regles._matiere(self.projet, self.etat, t)
        self.assertNotIn("fichier joint", matiere)
        self.assertNotIn("zipfile", matiere)

    def test_message_transmis_a_un_agent_au_travail(self):
        from moteur import regles
        f = {"discussion": [{"auteur": "utilisateur", "texte": "Voici",
                             "fichiers": [{"chemin": "pieces/f1/a.zip", "nom": "a.zip", "type": "application/zip", "taille": 10}]}]}
        texte = regles._texte_discussion(f)
        self.assertIn("- utilisateur : Voici", texte)
        self.assertIn("fichier joint : pieces/f1/a.zip (application/zip, 10 octets)", texte)


if __name__ == "__main__":
    unittest.main()
