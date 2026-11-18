"""Le partage des connaissances entre bureaux MyIAFactory : donnant-donnant, anonymisé, chiffré.

Le réglage vaut pour tout le bureau (le poste), dans `~/MyIAFactory/connaissances/partage.json` :
- partage ACTIF : les leçons « skill » et « genre » validées sont anonymisées (niveau réglable, `anonymat`), chiffrées
  et poussées sur le dépôt public de la skill ; les agents reçoivent aussi les leçons des autres bureaux.
- partage REFUSÉ (ou jamais choisi) : rien ne part sur GitHub ; les leçons restent dans la file locale de ce poste (les
  agents du poste en profitent) ; la clé est effacée, et les leçons partagées des autres, chiffrées, sont illisibles.
- RÉACTIVATION : la clé est reprise, les leçons gardées en local sont anonymisées puis montrées au Directeur, qui valide
  ce qui part.

La clé de chiffrement n'est jamais dans le dépôt public : elle vit dans un dépôt GitHub privé (`DEPOT_CLE`), où le
mainteneur invite chaque bureau qui partage ; activer le partage la télécharge avec les accès git de l'utilisateur.

La file locale (`file.json`) : une entrée par leçon confiée, avec son texte d'origine (jamais envoyé), le texte
anonymisé (ce qui part) et son état :
  locale        gardée sur ce poste (partage désactivé) ; proposée à la réactivation
  a_anonymiser  attend la relecture par Claude (le moteur s'en charge)
  a_relire      attend la validation du Directeur (niveau strict, ou leçon gardée pendant un refus)
  a_envoyer     prête : chiffrée et poussée au prochain passage
  envoyee       dans le dépôt partagé
  ecartee       le Directeur ne la partage pas ; elle reste à ce poste
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

from . import anonymat, chiffre, memoire

DEPOT_CLE = "https://github.com/maximus49000/MyIAFactory-cle.git"
FICHIER_CLE_DEPOT = "cle.txt"
ETATS = ("locale", "a_anonymiser", "a_relire", "a_envoyer", "envoyee", "ecartee")
A_TRAITER = ("a_anonymiser", "a_relire", "a_envoyer")
COUT_ESTIME_RELECTURE_USD = 0.003   # avant la première mesure : un appel Haiku d'environ 1 500 jetons
NOTE = ("Partager les connaissances met en commun, entre tous les bureaux MyIAFactory qui partagent, ce que vos agents "
        "apprennent (leçons de niveau skill et genre). Avant d'être envoyée sur GitHub, chaque leçon est anonymisée : "
        "on y lit des concepts, jamais votre projet (ni son nom, ni ses fichiers, adresses, clients ou chiffres), puis "
        "elle est chiffrée. Les leçons de niveau projet ne quittent jamais ce poste.")
NOTE_REFUS = ("Désactivé, rien n'est envoyé : vos leçons restent sur ce poste et servent toujours à vos agents. En "
              "contrepartie, vos agents ne reçoivent plus les connaissances des autres bureaux (elles sont chiffrées et "
              "la clé est retirée de ce poste). En réactivant, vous relirez et validerez les leçons gardées avant leur "
              "envoi.")


def dossier():
    d = os.environ.get("MYIAFACTORY_CONNAISSANCES")
    return Path(d) if d else Path("~/MyIAFactory/connaissances").expanduser()


def _maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _lire_json(chemin, defaut):
    try:
        d = json.loads(Path(chemin).read_text(encoding="utf-8-sig"))
        return d if isinstance(d, type(defaut)) else defaut
    except (OSError, ValueError):
        return defaut


def _ecrire_json(chemin, donnees):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)
    for essai in range(20):   # Windows : un lecteur peut tenir le fichier un instant
        try:
            os.replace(tmp, chemin)
            return
        except PermissionError:
            time.sleep(0.05 * (essai + 1))
    os.replace(tmp, chemin)


class _Verrou:
    """Un verrou de fichier entre processus (bureau, moteur, outils des projets). Périmé après 120 s."""

    def __init__(self, delai_s=30):
        self.chemin, self.delai_s = dossier() / ".verrou", delai_s

    def __enter__(self):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fin = time.monotonic() + self.delai_s
        while True:
            try:
                os.close(os.open(str(self.chemin), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.chemin.stat().st_mtime > 120:
                        self.chemin.unlink(missing_ok=True)
                        continue
                except OSError:
                    continue
                if time.monotonic() > fin:
                    raise TimeoutError("La file des connaissances est occupée.")
                time.sleep(0.05)

    def __exit__(self, *_):
        self.chemin.unlink(missing_ok=True)


# --- Le réglage.

def reglage():
    d = _lire_json(dossier() / "partage.json", {})
    niveau = d.get("niveau") if d.get("niveau") in anonymat.NIVEAUX else anonymat.NIVEAU_DEFAUT
    rel = d.get("relectures") if isinstance(d.get("relectures"), dict) else {}
    return {"actif": d.get("actif") if isinstance(d.get("actif"), bool) else None, "niveau": niveau,
            "change_le": d.get("change_le"),
            "relectures": {"nombre": int(rel.get("nombre") or 0), "cout_usd": float(rel.get("cout_usd") or 0.0)}}


def _ecrire_reglage(r):
    _ecrire_json(dossier() / "partage.json", r)


def cle():
    """Les octets de la clé, seulement quand le partage est actif et la clé présente ; sinon None."""
    if reglage()["actif"] is not True:
        return None
    try:
        return chiffre.lire_cle((dossier() / "cle").read_text(encoding="utf-8"))
    except (OSError, chiffre.CleInvalide):
        return None


def oublier_cle():
    try:
        (dossier() / "cle").unlink(missing_ok=True)
    except OSError:
        pass


def recuperer_cle(git=memoire.executer_git):
    """(ok, message) : la clé, téléchargée du dépôt privé avec les accès git de l'utilisateur."""
    depot = os.environ.get("MYIAFACTORY_DEPOT_CLE") or DEPOT_CLE
    tmp = Path(tempfile.mkdtemp(prefix="cle-connaissances-"))
    try:
        code, sortie = git(["clone", "-q", "--depth", "1", depot, str(tmp / "d")], tmp)
        if code != 0:
            if memoire.sans_droits(sortie) or "not found" in sortie.lower() or "repository" in sortie.lower():
                return False, ("Ce poste n'a pas accès au dépôt privé de la clé des connaissances. Demandez au "
                               "mainteneur de MyIAFactory une invitation à ce dépôt (votre compte GitHub), acceptez-la, "
                               "puis réactivez le partage.")
            return False, f"Téléchargement de la clé impossible (réseau ?) : {sortie[:200]}"
        try:
            valeur = chiffre.lire_cle((tmp / "d" / FICHIER_CLE_DEPOT).read_text(encoding="utf-8"))
        except (OSError, chiffre.CleInvalide) as e:
            return False, f"La clé du dépôt privé est illisible : {e}"
        (dossier()).mkdir(parents=True, exist_ok=True)
        (dossier() / "cle").write_text(valeur.hex(), encoding="utf-8")
        return True, "Clé des connaissances récupérée."
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def regler(actif=None, niveau=None, git=memoire.executer_git):
    """(ok, message). Activer télécharge la clé (sans elle, le partage reste désactivé) et remet les leçons gardées en
    local dans le circuit, avec la validation du Directeur ; désactiver efface la clé et garde tout en local."""
    r = reglage()
    if niveau is not None:
        if niveau not in anonymat.NIVEAUX:
            return False, f"Niveau d'anonymisation inconnu : « {niveau} »."
        r["niveau"] = niveau
    message = f"Niveau d'anonymisation : {anonymat.LIBELLES[r['niveau']]}."
    if actif is True and r["actif"] is not True:
        ok, msg = recuperer_cle(git)
        if not ok:
            return False, msg
        r["actif"], r["change_le"] = True, _maintenant()
        _ecrire_reglage(r)
        n = _reprendre_locales()
        message = ("Partage activé : vos agents reçoivent les connaissances des autres bureaux."
                   + (f" {n} leçon(s) gardée(s) en local vous attendent pour validation avant envoi." if n else ""))
    elif actif is False and r["actif"] is not False:
        r["actif"], r["change_le"] = False, _maintenant()
        _ecrire_reglage(r)
        oublier_cle()
        _garder_en_local()
        message = "Partage désactivé : rien ne sera envoyé, et les connaissances des autres bureaux ne sont plus lues."
    else:
        _ecrire_reglage(r)
    return True, message


# --- La file locale.

def _file():
    return _lire_json(dossier() / "file.json", {"entrees": []}).get("entrees") or []


def _ecrire_file(entrees):
    _ecrire_json(dossier() / "file.json", {"entrees": entrees})


def entrees():
    return _file()


def _reprendre_locales():
    with _Verrou():
        f = _file()
        n = 0
        for x in f:
            if x["etat"] == "locale":
                x.update(etat="a_anonymiser", validation_requise=True, raison=None)
                n += 1
        _ecrire_file(f)
    return n


def _garder_en_local():
    with _Verrou():
        f = _file()
        for x in f:
            if x["etat"] in A_TRAITER:
                x.update(etat="locale", raison=None)
        _ecrire_file(f)


def _prochain_id(f):
    return "c" + str(max([int(x["id"][1:]) for x in f if str(x.get("id", "")).startswith("c")
                          and x["id"][1:].isdigit()] or [0]) + 1)


def confier(dossier_memoire, lecons, mots, git=memoire.executer_git, projet=None):
    """Confie des leçons `[(etage, genre, {titre, texte, roles})]` validées au partage. Rend un `memoire.Resultat` par
    leçon : réussi dès qu'elle est dans la file (le projet n'a plus rien à réessayer). Le niveau standard part tout de
    suite ; les autres attendent la relecture (moteur) ou le Directeur."""
    r = reglage()
    actif = r["actif"] is True and cle() is not None
    resultats = []
    with _Verrou():
        f = _file()
        for etage, genre, lecon in lecons:
            if etage not in ("skill", "genre"):
                resultats.append(memoire.Resultat(False, "Seuls les étages « skill » et « genre » se partagent."))
                continue
            if etage == "genre" and not (isinstance(genre, str) and memoire.MOTIF_GENRE.match(genre)):
                resultats.append(memoire.Resultat(False, "Le projet n'a pas de genre : une leçon de genre ne peut pas "
                                                         "être rangée."))
                continue
            titre = " ".join(str(lecon.get("titre") or "").split())[:80]
            texte = str(lecon.get("texte") or "").strip()
            if not titre or not texte:
                resultats.append(memoire.Resultat(False, "Une leçon a un titre et un texte."))
                continue
            if any((x["titre"], x["texte"], x["etage"], x.get("genre")) == (titre, texte, etage, genre if etage == "genre"
                    else None) for x in f):
                resultats.append(memoire.Resultat(True, "Leçon déjà confiée au partage.", commite=True, publie=True))
                continue
            entree = {"id": _prochain_id(f), "etage": etage, "genre": genre if etage == "genre" else None,
                      "titre": titre, "texte": texte, "roles": lecon.get("roles") or ["tous"],
                      "date": lecon.get("date") or date.today().isoformat(), "mots": list(mots or []),
                      "projet": projet, "cree_le": _maintenant(), "etat": "locale" if not actif else "a_anonymiser",
                      "validation_requise": False, "raison": None}
            f.append(entree)
            msg = ("Leçon gardée sur ce poste (partage des connaissances désactivé)." if not actif
                   else "Leçon confiée au partage : anonymisée puis chiffrée avant envoi.")
            resultats.append(memoire.Resultat(True, msg, commite=True, publie=True))
        _ecrire_file(f)
    if actif:
        traiter(dossier_memoire, git=git)
    return resultats


def _anonymiser_filtre(x):
    texte, sortes = anonymat.filtrer(x["texte"], x.get("mots"))
    titre, sortes_t = anonymat.filtrer(x["titre"], x.get("mots"))
    return titre, texte, sorted(set(sortes) | set(sortes_t))


def traiter(dossier_memoire, reecrire=None, git=memoire.executer_git):
    """Fait avancer la file (partage actif seulement) : anonymise (filtre ; relecture par `reecrire` si fournie), puis
    chiffre et pousse ce qui est prêt. `reecrire(titre, texte) -> ({titre, texte} | {refus}, cout_usd)`.
    Rend {anonymisees, envoyees, a_relire, erreurs}."""
    bilan = {"anonymisees": 0, "envoyees": 0, "a_relire": 0, "erreurs": []}
    r = reglage()
    k = cle()
    if r["actif"] is not True or k is None:
        return bilan
    niveau = r["niveau"]
    # 1. L'anonymisation (hors verrou pour la relecture, qui dure).
    for x in [y for y in _file() if y["etat"] == "a_anonymiser"]:
        titre, texte, sortes = _anonymiser_filtre(x)
        mise_a_jour = {"remplacements": sortes}
        if niveau == "standard" and not x.get("validation_requise"):
            mise_a_jour.update(titre_partage=titre, texte_partage=texte, etat="a_envoyer")
        else:
            if niveau == "standard":   # leçon gardée pendant un refus : le filtre, puis le Directeur
                mise_a_jour.update(titre_partage=titre, texte_partage=texte, etat="a_relire")
            elif reecrire is None:
                continue                # la relecture viendra du moteur
            else:
                try:
                    rep, cout = reecrire(titre, texte)
                except Exception as e:   # jamais d'envoi sans relecture : la leçon attend
                    bilan["erreurs"].append(f"{x['id']} : relecture impossible ({e})"[:200])
                    continue
                _noter_cout(cout)
                if rep.get("refus"):
                    mise_a_jour.update(etat="a_relire", raison=f"Claude juge la leçon impossible à rendre générale : "
                                                               f"{rep['refus']}", titre_partage=titre,
                                       texte_partage=texte)
                else:
                    t2, s2 = anonymat.filtrer(rep["texte"], x.get("mots"))
                    ti2, _ = anonymat.filtrer(rep["titre"], x.get("mots"))
                    mise_a_jour.update(titre_partage=ti2, texte_partage=t2, remplacements=sorted(set(sortes) | set(s2)),
                                       etat="a_relire" if niveau == "strict" or x.get("validation_requise")
                                       else "a_envoyer")
        bilan["anonymisees"] += 1
        _mettre_a_jour(x["id"], "a_anonymiser", mise_a_jour)
    # 2. L'envoi.
    with _Verrou():
        f = _file()
        prets = [x for x in f if x["etat"] == "a_envoyer"]
        bilan["a_relire"] = sum(1 for x in f if x["etat"] == "a_relire")
    if not prets:
        _republier(dossier_memoire, git)
        return bilan
    plans, mots = [], []
    for x in prets:
        restes = anonymat.reste_identifiant(x["titre_partage"] + "\n" + x["texte_partage"], x.get("mots") or [])
        if restes:
            _mettre_a_jour(x["id"], "a_envoyer", {"etat": "a_relire", "raison": "Le texte nomme encore le projet."})
            continue
        if x["etage"] == "genre":
            _assurer_genre(dossier_memoire, x["genre"], x.get("mots") or [], git)
        plans.append((x, (x["etage"], x["genre"], {"titre": x["titre_partage"], "texte": x["texte_partage"],
                                                   "roles": x["roles"], "date": x["date"]})))
        mots += x.get("mots") or []
    if not plans:
        _republier(dossier_memoire, git)
        return bilan
    resultats = memoire.ecrire_lecons(dossier_memoire, [p for _, p in plans], sorted(set(mots)), git=git, cle=k)
    for (x, _), m in zip(plans, resultats):
        if m.ok and m.publie:
            _mettre_a_jour(x["id"], "a_envoyer", {"etat": "envoyee", "envoye_le": _maintenant(), "raison": None})
            bilan["envoyees"] += 1
        elif m.ok and m.commite:   # commitée, pas poussée : `republier` au prochain passage
            _mettre_a_jour(x["id"], "a_envoyer", {"etat": "envoyee", "envoye_le": _maintenant(),
                                                  "raison": m.message, "a_pousser": True})
        elif m.transitoire:
            _mettre_a_jour(x["id"], "a_envoyer", {"raison": m.message})
        else:
            _mettre_a_jour(x["id"], "a_envoyer", {"etat": "a_relire", "raison": m.message})
            bilan["erreurs"].append(f"{x['id']} : {m.message}"[:200])
    _republier(dossier_memoire, git)
    return bilan


def a_faire():
    """Vrai s'il reste quelque chose à faire avancer (anonymiser, envoyer, pousser)."""
    return any(x["etat"] in A_TRAITER or x.get("a_pousser") for x in _file())


def _republier(dossier_memoire, git):
    """Pousse les leçons commitées mais pas encore poussées (push refusé, distant en avance)."""
    if not any(x.get("a_pousser") for x in _file()):
        return
    pub = memoire.republier(dossier_memoire, git=git)
    if pub.ok and pub.publie:
        with _Verrou():
            f = _file()
            for x in f:
                if x.pop("a_pousser", None):
                    x["raison"] = None
            _ecrire_file(f)


def _assurer_genre(dossier_memoire, genre, mots, git):
    """Un genre créé sur ce poste pendant un refus : son fichier (description filtrée) entre au dépôt avant sa leçon."""
    if not genre or memoire._chemin_genre(dossier_memoire, genre).is_file():
        return
    local = _chemin_genre_local(genre)
    description = memoire.analyser(memoire._lire(local)).get("domaine") if local.is_file() else None
    description, _ = anonymat.filtrer(description or genre.replace("-", " "), mots)
    memoire.creer_genre(dossier_memoire, genre, description, mots, git=git)


def _mettre_a_jour(i, etat_attendu, champs):
    with _Verrou():
        f = _file()
        for x in f:
            if x["id"] == i and x["etat"] == etat_attendu:
                x.update(champs)
        _ecrire_file(f)


def _noter_cout(cout):
    r = reglage()
    r["relectures"]["nombre"] += 1
    r["relectures"]["cout_usd"] = round(r["relectures"]["cout_usd"] + float(cout or 0.0), 6)
    _ecrire_reglage(r)


def valider(dossier_memoire, ids, textes=None, git=memoire.executer_git):
    """Le Directeur valide l'envoi de leçons « à relire » (le texte, s'il le corrige : `textes[id]`). (ok, message)"""
    if cle() is None:
        return False, "Le partage des connaissances est désactivé : rien ne peut partir."
    textes = textes or {}
    with _Verrou():
        f = _file()
        n = 0
        for x in f:
            if x["id"] in ids and x["etat"] == "a_relire":
                if isinstance(textes.get(x["id"]), str) and textes[x["id"]].strip():
                    x["texte_partage"], _ = anonymat.filtrer(textes[x["id"]].strip(), x.get("mots"))
                x.update(etat="a_envoyer", raison=None, validation_requise=False)
                n += 1
        _ecrire_file(f)
    bilan = traiter(dossier_memoire, git=git)
    return True, (f"{bilan['envoyees']} leçon(s) envoyée(s) sur {n} validée(s)."
                  + (f" {'; '.join(bilan['erreurs'])}" if bilan["erreurs"] else ""))


def ecarter(ids):
    with _Verrou():
        f = _file()
        for x in f:
            if x["id"] in ids and x["etat"] in ("a_relire", "a_anonymiser", "a_envoyer", "locale"):
                x["etat"] = "ecartee"
        _ecrire_file(f)
    return True, "Ces leçons ne seront pas partagées ; elles restent sur ce poste."


def vue():
    """Ce que le bureau affiche : le réglage, la note, le surcoût de la relecture, et les leçons à relire (le texte
    exact qui partira). Jamais la clé."""
    r = reglage()
    f = _file()
    rel = r["relectures"]
    moyen = rel["cout_usd"] / rel["nombre"] if rel["nombre"] else COUT_ESTIME_RELECTURE_USD
    compte = {e: sum(1 for x in f if x["etat"] == e) for e in ETATS}
    return {
        "actif": r["actif"], "niveau": r["niveau"], "change_le": r["change_le"], "cle_presente": cle() is not None,
        "niveaux": [{"id": n, "libelle": anonymat.LIBELLES[n]} for n in anonymat.NIVEAUX],
        "note": NOTE, "note_refus": NOTE_REFUS,
        "surcout": {"relectures": rel["nombre"], "cout_usd": round(rel["cout_usd"], 4),
                    "par_lecon_usd": round(moyen, 4), "estime": rel["nombre"] == 0,
                    "a_venir": compte["a_anonymiser"] + (compte["locale"] if r["niveau"] != "standard" else 0)},
        "compte": compte,
        "a_relire": [{k: x.get(k) for k in ("id", "etage", "genre", "titre_partage", "texte_partage", "raison",
                                            "remplacements", "projet", "date")}
                     for x in f if x["etat"] == "a_relire"],
    }


# --- La lecture et les genres, pour les agents.

def lire(dossier_memoire, genre, role):
    """Les leçons à donner à un agent : celles du dépôt partagé (lisibles seulement avec la clé, donc partage actif),
    plus les leçons de ce poste pas encore dans le dépôt (texte d'origine : elles ne quittent pas le poste)."""
    k = cle()
    sortie = memoire.lire(dossier_memoire, genre, role, cle=k) if k is not None else {"skill": [], "genre": []}
    if genre and not memoire._chemin_genre(dossier_memoire, genre).is_file() and _chemin_genre_local(genre).is_file():
        sortie["genre"] = []
    for x in _file():
        if x["etat"] == "envoyee" and k is not None:
            continue   # déjà lue dans le dépôt
        if not ("tous" in x["roles"] or role in x["roles"]):
            continue
        lecon = {"id": x["id"], "titre": x["titre"], "texte": x["texte"], "roles": x["roles"], "date": x["date"],
                 "locale": True}
        if x["etage"] == "skill":
            sortie["skill"].append(lecon)
        elif x["etage"] == "genre" and x.get("genre") == genre:
            sortie["genre"].append(lecon)
    return sortie


def _chemin_genre_local(genre):
    return dossier() / "genres" / f"{genre}.md"


def genres(dossier_memoire):
    """Les genres du dépôt (leurs en-têtes restent lisibles) et ceux créés sur ce poste pendant un refus."""
    connus = memoire.genres(dossier_memoire)
    ids = {g["id"] for g in connus}
    for chemin in sorted((dossier() / "genres").glob("*.md")):
        if memoire.MOTIF_GENRE.match(chemin.stem) and chemin.stem not in ids:
            a = memoire.analyser(memoire._lire(chemin))
            connus.append({"id": chemin.stem, "domaine": a["domaine"], "livrable": a["livrable"],
                           "outils": a["outils"], "local": True})
    return connus


def creer_genre(dossier_memoire, genre, description, mots, git=memoire.executer_git):
    """Partage actif : le genre entre au dépôt (description filtrée). Sinon, il est créé sur ce poste seulement."""
    if cle() is not None:
        description, _ = anonymat.filtrer(description or "", mots)
        return memoire.creer_genre(dossier_memoire, genre, description, mots, git=git)
    if not (isinstance(genre, str) and memoire.MOTIF_GENRE.match(genre)):
        return False, "Identifiant de genre refusé (minuscules, chiffres et tirets, 40 caractères au plus)."
    description = " ".join(str(description or "").split())
    if not description:
        return False, "Un nouveau genre demande une description."
    if memoire._chemin_genre(dossier_memoire, genre).is_file() or _chemin_genre_local(genre).is_file():
        return False, f"Le genre « {genre} » existe déjà."
    chemin = _chemin_genre_local(genre)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(f"# Genre : {genre}\nDomaine : {description}\nLivrable : à préciser\nOutils : à préciser\n",
                      encoding="utf-8", newline="\n")
    return True, "Genre créé sur ce poste seulement (partage des connaissances désactivé)."


def decrire_genre(dossier_memoire, genre, description, mots, git=memoire.executer_git):
    local = _chemin_genre_local(genre)
    if not memoire._chemin_genre(dossier_memoire, genre).is_file() and local.is_file():
        description = " ".join(str(description or "").split())
        if not description:
            return False, "Une description de genre ne peut pas être vide."
        lignes = memoire._lire(local).split("\n")
        lignes = [f"Domaine : {description}" if x.startswith("Domaine :") else x for x in lignes]
        local.write_text("\n".join(lignes), encoding="utf-8", newline="\n")
        return True, "Description du genre mise à jour sur ce poste."
    if cle() is None:
        return True, "Partage des connaissances désactivé : la description n'est pas envoyée."
    description, _ = anonymat.filtrer(description or "", mots)
    return memoire.decrire_genre(dossier_memoire, genre, description, mots, git=git)


# --- Le mainteneur : chiffrer le dépôt, changer de clé.

def chiffrer_depot(dossier_memoire, cle_octets, git=memoire.executer_git, ancienne=None):
    """Réécrit chaque leçon de `skill.md` et `genres/*.md` en section chiffrée (les en-têtes des genres restent
    lisibles), puis commite et pousse. `ancienne` : la clé précédente, pour changer de clé. (ok, message)"""
    d = Path(dossier_memoire)
    fichiers = [d / "skill.md", *sorted((d / "genres").glob("*.md"))]
    changes = []
    for chemin in fichiers:
        if not memoire.MOTIF_GENRE.match(chemin.stem) and chemin.name != "skill.md":
            continue
        texte = memoire._lire(chemin)
        a = memoire.analyser(texte)
        lecons = memoire.dechiffrer_lecons(a["lecons"], ancienne)
        if len(lecons) != len(a["lecons"]):
            return False, f"{chemin.name} : des leçons chiffrées ne s'ouvrent pas avec l'ancienne clé."
        tete = texte.split("\n## ", 1)[0].rstrip("\n")
        sections = [memoire.section_chiffree(x["id"], {"titre": x["titre"], "texte": x["texte"],
                                                       "roles": x["roles"], "date": x.get("date")}, cle_octets)
                    for x in lecons]
        nouveau = tete + "\n\n" + "\n".join(sections) if sections else tete + "\n"
        if nouveau != texte:
            chemin.write_text(nouveau, encoding="utf-8", newline="\n")
            changes.append(str(chemin))
    if not changes:
        return True, "Rien à chiffrer."
    for args in (["add", "--", *changes], ["commit", "-q", "-m", "Mémoire : leçons partagées chiffrées", "--", *changes],
                 ["push", "-q"]):
        code, sortie = git(args, d)
        if code != 0:
            return False, f"« git {args[0]} » a échoué : {sortie[:300]}"
    return True, f"{len(changes)} fichier(s) chiffré(s) et poussé(s)."


def _principal(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Partage des connaissances (mainteneur).")
    p.add_argument("action", choices=("nouvelle-cle", "chiffrer", "etat"))
    p.add_argument("--memoire", default=str(Path(__file__).resolve().parent / "memoire"))
    p.add_argument("--cle", help="fichier de la clé (hexadécimal)")
    p.add_argument("--ancienne", help="fichier de l'ancienne clé (changement de clé)")
    a = p.parse_args(argv)
    if a.action == "nouvelle-cle":
        print(chiffre.nouvelle_cle())
        return 0
    if a.action == "etat":
        print(json.dumps(vue(), ensure_ascii=False, indent=2))
        return 0
    k = chiffre.lire_cle(Path(a.cle).read_text(encoding="utf-8"))
    ancienne = chiffre.lire_cle(Path(a.ancienne).read_text(encoding="utf-8")) if a.ancienne else None
    ok, message = chiffrer_depot(a.memoire, k, ancienne=ancienne)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_principal())
