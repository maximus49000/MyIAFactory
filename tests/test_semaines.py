"""L'archive des semaines du forfait, l'arbre des sujets et les routes qui les servent. Dossiers temporaires seulement."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from bureau import abonnement, prix, semaines, serveur, sujets
from bureau.usage import HistoriqueUsage

REMISE = 1_800_000_000          # une remise à zéro quelconque
DEBUT = REMISE - semaines.DUREE


def snap(t, pourcent, remise=REMISE):
    return {"seven_day": {"pourcent": pourcent, "remise": remise}, "t": t}


class AvecDossier(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)


class Archive(AvecDossier):
    def test_un_point_par_changement_et_un_fichier_par_semaine(self):
        semaines.noter(snap(DEBUT + 100, 1.0), "compte", self.tmp)
        semaines.noter(snap(DEBUT + 200, 1.0), "compte", self.tmp)    # inchangé : pas de nouveau point
        semaines.noter(snap(DEBUT + 300, 2.5), "moteur", self.tmp)
        s = semaines.lire(self.tmp, semaines._nom(REMISE, 0))
        self.assertEqual([(p["t"], p["pourcent"], p["source"]) for p in s["points"]],
                         [(DEBUT + 100, 1.0, "compte"), (DEBUT + 300, 2.5, "moteur")])
        self.assertEqual((s["debut"], s["remise"], s["vu"]), (DEBUT, REMISE, DEBUT + 300))
        fichiers = sorted(p.name for p in semaines.dossier(self.tmp).iterdir())
        self.assertEqual(len(fichiers), 1)
        self.assertRegex(fichiers[0], r"^20\d\d-\d\d-\d\d\.json$")
        self.assertEqual(list(semaines.dossier(self.tmp).glob("*.tmp")), [])      # écriture atomique : rien ne traîne

    def test_remise_a_quelques_secondes_pres_meme_semaine_sinon_une_autre(self):
        semaines.noter(snap(DEBUT + 10, 1.0), "compte", self.tmp)
        semaines.noter(snap(DEBUT + 20, 2.0, REMISE + 1), "compte", self.tmp)     # même fenêtre (fraction de seconde)
        semaines.noter(snap(REMISE + 100, 0.0, REMISE + semaines.DUREE), "compte", self.tmp)
        liste = semaines.lister(self.tmp, DEBUT + 50)
        self.assertEqual(len(liste), 2)
        self.assertEqual(liste[0]["remise"], REMISE + semaines.DUREE)             # la plus récente d'abord
        self.assertEqual((liste[1]["n"], liste[1]["courante"], liste[1]["max"]), (2, True, 2.0))
        self.assertFalse(liste[0]["courante"])

    def test_deux_semaines_le_meme_jour_ont_chacune_leur_fichier(self):
        semaines.noter(snap(DEBUT + 10, 1.0), "compte", self.tmp)
        semaines.noter(snap(DEBUT + 3600 + 10, 4.0, REMISE + 3600), "compte", self.tmp)   # remise une heure plus tard
        self.assertEqual(len(semaines.lister(self.tmp, DEBUT)), 2)

    def test_instant_hors_semaine_ou_sans_fenetre_ignore(self):
        semaines.noter(snap(DEBUT - 10_000, 1.0), "compte", self.tmp)
        semaines.noter({"five_hour": {"pourcent": 5.0, "remise": REMISE}, "t": DEBUT + 10}, "compte", self.tmp)
        semaines.noter(None, "compte", self.tmp)
        self.assertEqual(semaines.lister(self.tmp, DEBUT), [])

    def test_ordre_inverse_insere_au_bon_endroit(self):
        semaines.noter(snap(DEBUT + 300, 3.0), "moteur", self.tmp)
        semaines.noter(snap(DEBUT + 100, 1.0), "moteur", self.tmp)               # un appel daté de son début, écrit à sa fin
        s = semaines.lire(self.tmp, semaines._nom(REMISE, 0))
        self.assertEqual([p["t"] for p in s["points"]], [DEBUT + 100, DEBUT + 300])

    def test_identifiant_invalide_ou_inconnu(self):
        for i in ("../x", "2026-11-12/../a", "", None, "2030-01-01"):
            self.assertIsNone(semaines.lire(self.tmp, i))

    def test_fichier_abime_ignore(self):
        d = semaines.dossier(self.tmp)
        d.mkdir(parents=True)
        (d / "2026-01-01.json").write_text("{pas du json", encoding="utf-8")
        self.assertEqual(semaines.lister(self.tmp, DEBUT), [])

    def test_l_archive_survit_au_rognage_de_l_historique(self):
        abonnement.DOSSIER = self.tmp
        self.addCleanup(setattr, abonnement, "DOSSIER", None)
        for i in range(10):
            abonnement.noter(snap(DEBUT + 100 + i * 60, float(i)), 0.5)
        (self.tmp / abonnement.NOM_HISTORIQUE).write_text("", encoding="utf-8")   # l'historique rogné jusqu'au vide
        s = semaines.lire(self.tmp, semaines.lister(self.tmp, DEBUT + 1)[0]["id"])
        self.assertEqual(len(s["points"]), 10)

    def test_l_instantane_du_compte_et_des_appels_alimentent_l_archive(self):
        abonnement.DOSSIER = self.tmp
        self.addCleanup(setattr, abonnement, "DOSSIER", None)
        abonnement.noter(snap(DEBUT + 100, 1.0), source=abonnement.SOURCE_COMPTE)
        abonnement.noter(snap(DEBUT + 200, 2.0), 0.4)
        s = semaines.lire(self.tmp, semaines.lister(self.tmp, DEBUT + 1)[0]["id"])
        self.assertEqual([p["source"] for p in s["points"]], ["compte", "moteur"])

    def test_importer_amorce_depuis_l_historique(self):
        histo = [dict(abonnement.valider(snap(DEBUT + 100, 1.0)), cout_usd=None, source="compte"),
                 dict(abonnement.valider(snap(DEBUT + 200, 3.0)), cout_usd=0.2)]
        semaines.importer(histo, self.tmp)
        s = semaines.lire(self.tmp, semaines.lister(self.tmp, DEBUT + 1)[0]["id"])
        self.assertEqual([(p["pourcent"], p["source"]) for p in s["points"]], [(1.0, "compte"), (3.0, "moteur")])


# --- L'arbre des sujets.

PRIX_REGL = {"prix": {"sonnet": [{"entree": 3.0, "sortie": 15.0, "date": "2026-01-01"}]}}


def usage(id, tache="t1", etape="Tests", t=DEBUT + 1000, modele="sonnet", **extra):
    u = {"id": id, "tache": tache, "agent": "d1", "service": "dev", "modele": modele, "etape": etape,
         "t": _iso(t), "t_prix": _iso(t), "entree": 1_000_000, "sortie": 10_000, "cache_lecture": 0, "cache_ecriture": 0}
    u.update(extra)
    return u


def _iso(t):
    from datetime import datetime, timezone
    if isinstance(t, str):
        return t
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def prix_de(modele, date_iso):
    return prix.prix_effectif(prix.TablePrix(Path("absent.jsonl")), PRIX_REGL, modele, date_iso)


RELEVE_A = {"projet": "Alpha", "taches": [{"id": "t1", "titre": "Écran", "fonctionnalite": "f1"},
                                         {"id": "t2", "titre": "Menu", "fonctionnalite": "f1"},
                                         {"id": "t3", "titre": "Libre"}],
            "fonctionnalites": [{"id": "f1", "nom": "Accueil"}]}


class Arbre(unittest.TestCase):
    def lignes(self, usages, releve=RELEVE_A, pid="a", nom="Alpha"):
        return sujets.lignes_projet(pid, nom, usages, releve, prix_de, DEBUT, REMISE)

    def test_hierarchie_projet_fonctionnalite_tache_etape(self):
        a = sujets.arbre(self.lignes([usage("u1"), usage("u2", etape="Maquette"), usage("u3", tache="t2")]))
        self.assertEqual(a["n"], 3)
        projet = a["sujets"][0]
        self.assertEqual((projet["nom"], projet["genre"]), ("Alpha", "projet"))
        fonct = projet["enfants"][0]
        self.assertEqual((fonct["nom"], fonct["genre"]), ("Accueil", "fonctionnalite"))
        taches = {t["nom"]: t for t in fonct["enfants"]}
        self.assertEqual(set(taches), {"Écran", "Menu"})
        self.assertEqual({e["nom"] for e in taches["Écran"]["enfants"]}, {"Tests", "Maquette"})
        # les euros se cumulent à chaque niveau : 1 M entrée à 3 € + 10 000 sortie à 15 €/M
        un = 3.0 + 0.15
        self.assertAlmostEqual(a["euros"], 3 * un, places=5)
        self.assertAlmostEqual(taches["Écran"]["euros"], 2 * un, places=5)
        self.assertAlmostEqual(projet["euros"], fonct["euros"], places=6)

    def test_tri_par_cout_decroissant(self):
        a = sujets.arbre(self.lignes([usage("u1", tache="t2"), usage("u2", tache="t1"), usage("u3", tache="t1")]))
        taches = a["sujets"][0]["enfants"][0]["enfants"]
        self.assertEqual([t["nom"] for t in taches], ["Écran", "Menu"])

    def test_groupes_speciaux(self):
        a = sujets.arbre(self.lignes([
            usage("o", etape="orchestration", tache=None), usage("d", tache=None, service=None, agent=None),
            usage("h", tache=None), usage("l", tache="t3"), usage("r", tache="retiree")]))
        projet = a["sujets"][0]
        noms = {e["nom"]: e for e in projet["enfants"]}
        self.assertEqual(set(noms), {"Orchestration", "Direction", "Hors tâche", "Hors fonctionnalité"})
        self.assertEqual({t["nom"] for t in noms["Hors fonctionnalité"]["enfants"]}, {"Libre", "retiree"})

    def test_marques_aux_dates_des_usages_dans_la_semaine_seulement(self):
        a = sujets.arbre(self.lignes([usage("u1", t=DEBUT + 500, duree=90), usage("u2", t=DEBUT - 5),
                                      usage("u3", t=REMISE + 5), usage("u4", t="pas une date")]))
        self.assertEqual(a["n"], 1)
        feuille = a["sujets"][0]["enfants"][0]["enfants"][0]["enfants"][0]
        self.assertEqual(feuille["marques"], [{"t": DEBUT + 500, "euros": feuille["euros"], "modele": "sonnet",
                                               "duree": 90.0}])
        self.assertIsNone(sujets.arbre(self.lignes([usage("u", duree=-3)]))["sujets"][0]["enfants"][0]
                          ["enfants"][0]["enfants"][0]["marques"][0]["duree"])
        # seul le nœud où le chemin s'arrête porte les marques
        self.assertEqual(a["sujets"][0]["marques"], [])

    def test_prix_inconnu_jamais_zero_et_empreinte(self):
        a = sujets.arbre(self.lignes([usage("u1"), usage("u2", modele="inconnu-9")]))
        self.assertEqual(a["sans_prix"], 1)
        self.assertEqual(a["n"], 2)
        self.assertGreater(a["euros"], 0)
        self.assertIn("co2", a)                       # le modèle connu a une empreinte
        self.assertTrue(a["co2"]["incomplet"])        # l'autre, sans donnée, le dit

    def test_partenaires_exclus(self):
        p = {"id": "p", "genre": "partenaire", "partenaire": "x", "t": _iso(DEBUT + 5), "t_prix": _iso(DEBUT + 5),
             "tache": "t1", "cout": 1.0, "devise": "EUR", "quantite": 1, "unite": "u", "estime": False}
        self.assertEqual(self.lignes([p]), [])

    def test_plusieurs_projets_et_echanges_de_creation(self):
        releve_b = {"projet": "Beta", "taches": [{"id": "t1", "titre": "Autre", "fonctionnalite": "f1"}],
                    "fonctionnalites": [{"id": "f1", "nom": "Jeu"}]}
        creation = sujets.lignes_creation("c1", "Casse-briques", [usage("x"), dict(usage("y"), t=_iso(REMISE + 9))],
                                          lambda u: 0.5, DEBUT, REMISE)
        a = sujets.arbre(self.lignes([usage("u1")]) + self.lignes([usage("u2"), usage("u3")], releve_b, "b", "Beta")
                         + creation)
        self.assertEqual({s["nom"] for s in a["sujets"]}, {"Alpha", "Beta", "Échanges de création"})
        self.assertEqual(a["n"], 4)
        echanges = next(s for s in a["sujets"] if s["id"] == "creations")
        self.assertEqual((echanges["enfants"][0]["nom"], echanges["euros"], len(echanges["enfants"][0]["marques"])),
                         ("Casse-briques", 0.5, 1))
        # des projets distincts n'ont jamais les mêmes identifiants de nœud, même avec la même tâche
        ids = []

        def tous(n):
            ids.append(n["id"])
            for e in n["enfants"]:
                tous(e)
        for s in a["sujets"]:
            tous(s)
        self.assertEqual(len(ids), len(set(ids)))


# --- Les routes : plusieurs projets, sans jamais toucher au vrai dossier.

class FauxProjet:
    def __init__(self, dossier, id_, releve, usages):
        self.id = id_
        self.dernier_releve = releve
        self.usage = HistoriqueUsage(dossier / f"{id_}-usage.jsonl")
        self.usage.integrer({"usage": usages})
        self.table_prix = prix.TablePrix(dossier / f"{id_}-prix.jsonl")
        self._premiers_prix = SimpleNamespace(wait=lambda s=None: None)

    def etat(self):
        return {}

    def reglages(self):
        return PRIX_REGL, None


class Routes(AvecDossier):
    def setUp(self):
        super().setUp()
        abonnement.DOSSIER = self.tmp / "commun"
        self.addCleanup(setattr, abonnement, "DOSSIER", None)
        t = __import__("time").time()
        self.maintenant = int(t)
        self.remise = self.maintenant + 3 * 86400
        for i, p in enumerate((1.0, 2.0, 5.0)):
            abonnement.noter(snap(self.maintenant - 3000 + i * 600, p, self.remise), 0.1)
        self.debut = self.remise - semaines.DUREE
        self.bureau = SimpleNamespace(
            projets={"a": FauxProjet(self.tmp, "a", RELEVE_A, [usage("a1", t=self.maintenant - 2000),
                                                                usage("a2", tache="t2", t=self.maintenant - 1000)]),
                     "b": FauxProjet(self.tmp, "b", {"projet": "Beta", "taches": []},
                                     [usage("b1", tache=None, service=None, t=self.maintenant - 500)])},
            actualiser_projets=lambda: None, fichier_bureau=None, dossier_creations=None, commun_creations=None)

    def test_liste_et_serie(self):
        liste = serveur.Bureau.liste_semaines(self.bureau)
        self.assertEqual(len(liste["semaines"]), 1)
        self.assertTrue(liste["semaines"][0]["courante"])
        code, s = serveur.Bureau.serie_semaine(self.bureau, liste["semaines"][0]["id"])
        self.assertEqual((code, len(s["points"]), s["remise"]), (200, 3, self.remise))
        self.assertEqual(serveur.Bureau.serie_semaine(self.bureau, "2001-01-01")[0], 404)
        self.assertEqual(serveur.Bureau.serie_semaine(self.bureau, "../x")[0], 404)

    def test_la_liste_amorce_l_archive_depuis_l_historique(self):
        import shutil
        shutil.rmtree(semaines.dossier(abonnement.racine()))
        self.assertEqual(len(serveur.Bureau.liste_semaines(self.bureau)["semaines"]), 1)

    def test_les_sujets_reunissent_tous_les_projets(self):
        ident = serveur.Bureau.liste_semaines(self.bureau)["semaines"][0]["id"]
        code, r = serveur.Bureau.sujets_semaine(self.bureau, ident)
        self.assertEqual(code, 200)
        self.assertEqual(r["n"], 3)
        self.assertEqual({s["nom"] for s in r["sujets"]}, {"Alpha", "Beta"})
        # chaque niveau est filtrable : projet → fonctionnalité → tâche → étape
        alpha = next(s for s in r["sujets"] if s["nom"] == "Alpha")
        fonct = alpha["enfants"][0]
        tache = fonct["enfants"][0]
        etape = tache["enfants"][0]
        self.assertEqual([x["genre"] for x in (alpha, fonct, tache, etape)], ["projet", "fonctionnalite", "tache", "etape"])
        self.assertEqual(len(etape["marques"]), 1)
        self.assertAlmostEqual(alpha["euros"], r["euros"] - next(s for s in r["sujets"] if s["nom"] == "Beta")["euros"],
                               places=6)
        self.assertEqual(serveur.Bureau.sujets_semaine(self.bureau, "2001-01-01")[0], 404)

    def test_un_projet_en_panne_n_empeche_pas_les_autres(self):
        def casse():
            raise RuntimeError("panne")
        self.bureau.projets["a"].etat = casse
        ident = serveur.Bureau.liste_semaines(self.bureau)["semaines"][0]["id"]
        code, r = serveur.Bureau.sujets_semaine(self.bureau, ident)
        self.assertEqual((code, [s["nom"] for s in r["sujets"]]), (200, ["Beta"]))

    def test_les_echanges_de_creation_comptent(self):
        from installation import brouillons
        commun = self.tmp / "usage-creations.jsonl"
        ligne = {"modele": "sonnet", "entree": 1000, "sortie": 100, "cache_lecture": 0, "cache_ecriture": 0,
                 "t": _iso(self.maintenant - 100)}
        commun.write_text(json.dumps(ligne) + "\n", encoding="utf-8")
        self.bureau.fichier_bureau = self.tmp / "bureau.json"
        self.bureau.dossier_creations = self.tmp / "creations"
        self.bureau.commun_creations = commun
        self.bureau.prix_de_modele = lambda m: {"entree": 3e-6, "sortie": 15e-6}
        ident = serveur.Bureau.liste_semaines(self.bureau)["semaines"][0]["id"]
        code, r = serveur.Bureau.sujets_semaine(self.bureau, ident)
        echanges = next(s for s in r["sujets"] if s["id"] == "creations")
        self.assertAlmostEqual(echanges["euros"], 1000 * 3e-6 + 100 * 15e-6)
        self.assertEqual(echanges["enfants"][0]["nom"], "Échanges abandonnés")
        del brouillons


class ParHttp(AvecDossier):
    """Les trois routes, par un vrai serveur HTTP sur un dossier temporaire."""

    def test_routes(self):
        from tests import copie_demo
        from tests.test_serveur import SourceSimulee
        abonnement.DOSSIER = self.tmp / "commun"
        self.addCleanup(setattr, abonnement, "DOSSIER", None)
        copie_demo(self.tmp / "demo")
        remise = int(__import__("time").time()) + 86400
        abonnement.noter(snap(remise - 600, 7.0, remise), 0.1)
        srv = serveur.creer(self.tmp / "demo" / "reglages.json", port=0, ouvrir=SourceSimulee())
        srv.dossier_creations, srv.commun_creations = self.tmp / "c", self.tmp / "c.jsonl"
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))

        def get(chemin):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=20)
            c.request("GET", chemin, headers={"X-Bureau": "1"})
            r = c.getresponse()
            return r.status, json.loads(r.read())
        code, liste = get("/api/semaines")
        self.assertEqual(code, 200)
        ident = liste["semaines"][0]["id"]
        self.assertEqual(get(f"/api/semaine?id={ident}")[1]["points"][0]["pourcent"], 7.0)
        self.assertEqual(get("/api/semaine")[0], 404)
        self.assertEqual(get("/api/semaine?id=nimporte")[0], 404)
        code, arbre = get(f"/api/sujets?semaine={ident}")
        self.assertEqual((code, arbre["semaine"]), (200, ident))
        self.assertIsInstance(arbre["sujets"], list)      # les usages de la démonstration, ou rien
        self.assertEqual(get("/api/sujets")[0], 404)
