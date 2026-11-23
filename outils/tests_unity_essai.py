"""Expériences réelles de la licence Unity au serveur (conception § 5.16 et § 8, jalons J13 et J14 ; tâche 14i). Outil du
CONTRÔLEUR seul, lancé avec le feu vert du Directeur : jamais par un agent de projet.

`py -3.12 outils/tests_unity_essai.py --serveur-id <id> --dossier <projet> --test <nom> [--variantes B1,B2[,B3]]
[--hotes-licence h1,h2] [--hote]`

J13 (sans `--hote`) : lecture et conteneur seulement, aucun changement de l'hôte.
  1. Inventaire des NOMS et tailles des fichiers de licence (`find … -printf '%p %s'`) et des sockets du client de licence
     (`ss -xl` filtré) : JAMAIS un contenu (aucun `cat`, `head`, `base64`, `xxd`, `cp`).
  2. Une campagne `-testFilter <nom>` par variante, dans l'ordre B1, B2 (B3 seulement si `--variantes` la cite ET que la décision
     QU1 est `accorde`, avec les hôtes de licence relevés dans le journal du client à la main : jamais devinés), à froid puis à
     chaud, par `tests_serveur.executer(…, forcer=True, evaluation=True, executeur="conteneur", licence=<variante>)`.
  3. Verdict : `conteneur` (première variante qui rend 0 : au moins un test exécuté, 82 sinon), `hote` (81 en B1 ET en B2, et
     dans toutes les variantes permises), `indetermine` (82, erreur de compilation, test en échec, refus, autre code : RIEN n'est écrit, jamais une
     conclusion pour A). L'état est écrit par l'étape `unity_licence_etat` (puis l'état local) ; `hote` pose aussi l'étape humaine
     « Installer 6000.6.7f1 par Hub » (QU2).
J14 (`--hote`, seulement si l'état relevé est `hote`) : l'audit du bac à sable (`sudo -n unity-bac-a-sable.sh auditer …` : la
  sonde du dépôt `sonde-bac-a-sable.sh` dans l'unité, jamais le code du projet) ; le marqueur
  `~/.myiafactory/unity-bac-a-sable.version` n'est écrit que si TOUTES ses vérifications passent ; puis le même test par
  l'exécuteur `hote_bac_a_sable` (choisi par la règle : l'état relevé et la capacité, après une sonde).
Relevés (durées par passage ; pic mémoire et taille de `Library/` quand ils sont connus) : `~/MyIAFactory/tests-unity-essai.json`.
Tout accès au serveur passe par `bash` (`serveur_tache._bash`) et `executer` (injectables : les tests n'appellent rien de réel).
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

import plateforme_acces  # noqa: E402
import serveur_tache  # noqa: E402
import tests_serveur  # noqa: E402

RELEVES = Path("~/MyIAFactory/tests-unity-essai.json").expanduser()
RELEVES_MAX = 20
MOTIF_TEST = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.]{0,199}", re.ASCII)
VARIANTES = tests_serveur.LICENCES
ENTREES_MAX = 100
# Les NOMS et tailles seulement : `find -printf` (jamais un contenu lu), `ss -xl` filtré sur le client de licence. Aucune valeur
# du poste n'y entre. Ni `~/.config/unityhub` (session du compte) ni `~/.config/unity3d` en entier (journal de l'éditeur).
SCRIPT_INVENTAIRE = (
    'for d in "$HOME/.config/unity3d/Unity/licenses" "$HOME/.local/share/unity3d/Unity"; do\n'
    '  [ -d "$d" ] && find "$d" -maxdepth 1 -type f -printf \'fichier %p %s\\n\' 2>/dev/null\n'
    'done\n'
    'find "$HOME/.config/unity3d/Unity" -maxdepth 1 -type f -name \'Unity.Licensing.Client.log\' '
    '-printf \'fichier %p %s\\n\' 2>/dev/null\n'
    'ss -xl 2>/dev/null | grep -i \'licens\' | awk \'{ print "socket " $5 }\'\n'
    'exit 0\n')
_LIGNE_FICHIER = re.compile(r"fichier (/[A-Za-z0-9_./ -]{1,300}) ([0-9]{1,15})", re.ASCII)
_LIGNE_SOCKET = re.compile(r"socket (@?/?[A-Za-z0-9_./-]{1,300})", re.ASCII)
BAC_A_SABLE = "/usr/local/lib/myiafactory/unity-bac-a-sable.sh"
MARQUEUR_BAC = "$HOME/.myiafactory/unity-bac-a-sable.version"
_MOTIF_EMPREINTE = re.compile(r"[A-Za-z0-9=;_.,-]{1,200}", re.ASCII)
AUDIT = {"cpus": 4, "memoire_mo": 10240, "duree_s": 900, "travail_go": 10}


def _erreurs_ecriture():
    import serveur_installation
    return (serveur_installation.ErreurInstallation, OSError)


class Refus(Exception):
    """L'essai ne peut pas partir (arguments, état) ; rien n'a été lancé ni écrit."""


# --- inventaire ------------------------------------------------------------------------------------------------------

def lire_inventaire(sortie) -> dict:
    """`{"fichiers": [{"nom", "taille"}], "sockets": [nom]}` lus dans la sortie de `SCRIPT_INVENTAIRE` ; toute autre ligne est
    ignorée ; 100 entrées de chaque au plus."""
    fichiers, sockets = [], []
    for ligne in str(sortie or "").splitlines()[:1000]:
        m = _LIGNE_FICHIER.fullmatch(ligne.strip())
        if m and len(fichiers) < ENTREES_MAX:
            fichiers.append({"nom": m.group(1), "taille": int(m.group(2))})
            continue
        m = _LIGNE_SOCKET.fullmatch(ligne.strip())
        if m and len(sockets) < ENTREES_MAX:
            sockets.append(m.group(1))
    return {"fichiers": fichiers, "sockets": sockets}


def inventaire(serveur, bash) -> dict:
    code, sortie, _erreur = bash(serveur, SCRIPT_INVENTAIRE)
    if code != 0:
        return {"fichiers": [], "sockets": [], "erreur": f"inventaire impossible (code {code})"}
    return lire_inventaire(sortie)


# --- variantes et commande -------------------------------------------------------------------------------------------

def variantes_permises(demandees, accord_b3, hotes_licence):
    """(variantes dans l'ordre B1, B2, B3, messages) : B3 seulement citée, accordée (QU1) et avec ses hôtes de licence."""
    voulues, messages = [], []
    for v in VARIANTES:
        if v not in demandees:
            continue
        if v == "B3":
            if not accord_b3:
                messages.append("B3 écartée : la décision QU1 (réseau de licence pendant les tests) n'est pas « accorde ».")
                continue
            if not hotes_licence:
                messages.append("B3 écartée : aucun hôte de licence donné (--hotes-licence, relevés dans le journal du client).")
                continue
        voulues.append(v)
    return voulues, messages


def commande_essai(racine, test, analyse=None) -> list:
    """La commande Unity du profil du projet (EditMode) avec `-testFilter <test>` ; `Refus` hors motif ou sans profil Unity."""
    if not isinstance(test, str) or not MOTIF_TEST.fullmatch(test):
        raise Refus("nom de test refusé (lettres, chiffres, « _ » et « . », 200 caractères au plus)")
    if analyse is None:
        import tests_profil
        analyse = tests_profil.analyser
    profil = analyse(racine, lancee=["unity-editor"])
    if tuple(profil.familles) != ("unity",) or not profil.commandes:
        raise Refus("le dossier n'est pas un projet Unity reconnu (ProjectSettings/ProjectVersion.txt)")
    return [*profil.commandes[0], "-testFilter", test], profil


# --- audit J14 ---------------------------------------------------------------------------------------------------------

def lire_audit(code, sortie):
    """(tout passe, lignes) : vrai seulement si le code est 0, au moins une ligne `ok`, aucune ligne `echec` et le bilan
    « bilan 0 echec(s) ». Les lignes gardées sont celles de la sonde (`ok …`, `echec …`, `bilan …`), 200 au plus."""
    lignes = [x.strip()[:200] for x in str(sortie or "").splitlines() if re.match(r"(ok|echec|bilan) ", x.strip())][:200]
    passe = (code == 0 and any(x.startswith("ok ") for x in lignes) and not any(x.startswith("echec ") for x in lignes)
             and "bilan 0 echec(s)" in lignes)
    return passe, lignes


def script_audit(ident, version):
    if not serveur_tache.MOTIF_ID.fullmatch(ident) or not tests_serveur.MOTIF_IMAGE_UNITY.fullmatch(f"myiafactory/tests-unity-{version}"):
        raise Refus("identifiant ou version hors motif")
    a = AUDIT
    return (f"sudo -n {BAC_A_SABLE} auditer {ident} {a['cpus']} {a['memoire_mo']} {a['duree_s']} {version} aucun "
            f"{a['travail_go']} </dev/null 2>&1\n")


def script_marqueur(empreinte):
    if not isinstance(empreinte, str) or not _MOTIF_EMPREINTE.fullmatch(empreinte):
        raise Refus("empreinte du bac à sable hors motif")
    return ('install -d -m 700 "$HOME/.myiafactory" && umask 077 && '
            f"printf '%s\\n' '{empreinte}' > \"{MARQUEUR_BAC}.tmp\" && mv -f \"{MARQUEUR_BAC}.tmp\" \"{MARQUEUR_BAC}\"\n")


# --- l'essai ----------------------------------------------------------------------------------------------------------

def _passages(executer, commande, dossier, executeur, licence, hotes, horloge, dire):
    """Une campagne à froid puis, si elle rend 0, une à chaud. Rend la liste des relevés (code, durée)."""
    passages = []
    for passage in ("froid", "chaud"):
        t0 = horloge()
        code = executer(commande, dossier=dossier, forcer=True, evaluation=True, executeur=executeur, licence=licence,
                        hotes_licence=hotes)
        passages.append({"executeur": executeur, "variante": licence, "passage": passage, "code": code,
                         "duree_s": round(max(0.0, horloge() - t0), 1), "pic_memoire_mo": None, "library_mo": None})
        dire(f"{executeur} {licence} ({passage}) : code {code}, {passages[-1]['duree_s']} s.")
        if code != 0:
            break
    return passages


def essai(serveur_id, dossier, test, variantes=("B1", "B2"), hote=False, hotes_licence=(), *,
          dossier_etat=plateforme_acces.DOSSIER, bash=None, executer=None, noter_licence=None, poser_etape=None,
          accord_b3=None, lire_serveurs=None, etat_serveurs=None, rafraichir=None, empreinte_bac=None, analyse=None,
          nouvel_id=None, horloge=time.monotonic, dire=print, releves=None, modifier=None):
    """L'expérience J13 (ou J14 avec `hote`). Rend le relevé écrit (`verdict` : conteneur | hote | indetermine |
    bac_a_sable_pret | audit_echoue | etat_non_ecrit | hote_echoue). `Refus` avant toute connexion pour un argument ou un état qui ne convient pas."""
    racine = str(Path(dossier).resolve())
    serveurs = (lire_serveurs or _lire_serveurs)(dossier_etat)
    serveur = next((s for s in serveurs if getattr(s, "id", None) == serveur_id), None)
    if serveur is None:
        raise Refus(f"serveur inconnu : {serveur_id}")
    commande, profil = commande_essai(racine, test, analyse)
    bash = bash or (lambda s, script: serveur_tache._bash(s, _ssh(), script, delai=120))
    executer = executer or _executer_vers(serveur, dossier_etat)
    noter_licence = noter_licence or tests_serveur.noter_licence_unity
    poser_etape = poser_etape or tests_serveur.poser_etape_humaine
    etat_srv = ((etat_serveurs or tests_serveur._etat_serveurs_par_defaut)(dossier_etat) or {}).get(serveur.id) or {}
    releve = {"date": datetime.now().astimezone().isoformat(timespec="seconds"), "serveur_id": serveur.id, "test": test,
              "jalon": "J14" if hote else "J13", "passages": [], "messages": []}
    if hote:
        return _essai_hote(serveur, racine, commande, profil, etat_srv, releve, bash, executer, rafraichir, empreinte_bac,
                           nouvel_id or serveur_tache.nouvel_id, horloge, dire, releves, dossier_etat, modifier)
    accord = (accord_b3 or tests_serveur._reseau_licence_par_defaut)(racine) is True
    hotes = [h for h in hotes_licence or () if tests_serveur._hote_de_licence(h)]
    if len(hotes) != len(list(hotes_licence or ())):
        raise Refus("hôte de licence hors des domaines de licence Unity")
    voulues, messages = variantes_permises(tuple(variantes), accord, hotes)
    for m in messages:
        dire(m)
    releve["messages"] += messages
    if not voulues:
        raise Refus("aucune variante permise")
    releve["inventaire"] = inventaire(serveur, bash)
    dire(f"Inventaire : {len(releve['inventaire']['fichiers'])} fichier(s) de licence (noms et tailles), "
         f"{len(releve['inventaire']['sockets'])} socket(s) du client.")
    verdict, variante, raison = "hote", None, "licence refusée (81) dans toutes les variantes permises"
    for v in voulues:
        passages = _passages(executer, commande, racine, "conteneur", v, hotes if v == "B3" else None, horloge, dire)
        releve["passages"] += passages
        code = passages[0]["code"]
        if code == 0:
            verdict, variante, raison = "conteneur", v, ""
            break
        if code == tests_serveur.CODE_LICENCE_REFUSEE:
            continue
        verdict, variante = "indetermine", None
        raison = ("aucun test découvert (82)" if code == tests_serveur.CODE_AUCUN_TEST
                  else f"code {code} (erreur de compilation, test en échec, refus ou autre) : rien n'est conclu")
        break
    tentees = {p["variante"] for p in releve["passages"]}
    if verdict == "hote" and not {"B1", "B2"} <= tentees:
        # A ne se conclut que si B1 ET B2 ont été tentées et refusées (81) : une seule variante ne prouve rien
        verdict, raison = "indetermine", "B1 et B2 n'ont pas toutes deux été tentées : rien n'est conclu pour A"
    releve.update(verdict=verdict, variante=variante, raison=raison)
    try:
        if verdict == "conteneur":
            r = noter_licence(dossier_etat, serveur, "conteneur", variante, hotes=hotes if variante == "B3" else None)
            releve["etat_ecrit"] = r[0]
        elif verdict == "hote":
            r = noter_licence(dossier_etat, serveur, "hote", None)
            releve["etat_ecrit"] = r[0]
            if poser_etape(dossier_etat, serveur.id, "unity-editeur-6000.6.7f1"):
                dire("Étape humaine posée au bureau : « Installer 6000.6.7f1 par Hub » (QU2).")
        else:
            releve["etat_ecrit"] = None          # indéterminé : RIEN n'est écrit
    except _erreurs_ecriture() as e:
        # une écriture refusée (installation en cours) n'efface pas l'expérience : le relevé est écrit, l'état est à refaire
        releve["etat_ecrit"] = "non_ecrit"
        releve["messages"].append(f"état non écrit : {e} — relancez l'outil à la fin de l'installation")
        dire(f"État non écrit : {e}")
    dire(f"Verdict : {verdict}" + (f" ({variante})" if variante else "") + (f" — {raison}" if raison else ""))
    _ecrire_releves(releves, releve)
    return releve


def _essai_hote(serveur, racine, commande, profil, etat_srv, releve, bash, executer, rafraichir, empreinte_bac, nouvel_id,
                horloge, dire, releves, dossier_etat, modifier=None):
    lic = tests_serveur.licence_relevee(etat_srv)
    if lic["etat"] != "hote":
        raise Refus("J14 seulement si J13 a rendu « hote » (état relevé : " + lic["etat"] + ")")
    version = (profil.outils or {}).get("unity")
    code, sortie, _e = bash(serveur, script_audit(nouvel_id(), version))
    passe, lignes = lire_audit(code, sortie)
    releve["audit"] = {"code": code, "lignes": lignes, "passe": passe}
    if not passe:
        releve.update(verdict="audit_echoue", raison="audit du bac à sable : au moins une vérification échoue, aucun marqueur")
        dire("Audit du bac à sable : ÉCHEC ; aucun marqueur écrit, aucun test lancé sur l'hôte.")
        _ecrire_releves(releves, releve)
        return releve
    import serveur_installation
    if empreinte_bac is None:
        empreinte_bac = serveur_installation.empreinte_etape("unity_bac_a_sable")
    # l'état local de l'audit D'ABORD : refusé (installation en cours), le marqueur n'est PAS posé et rien ne tourne
    try:
        (modifier or serveur_installation.modifier_etat_capacite)(
            dossier_etat, serveur.id, tests_serveur.CAP_BAC_A_SABLE,
            lambda ancien: {**ancien, "audit": "passe", "date": releve["date"]})
    except _erreurs_ecriture() as e:
        releve.update(verdict="etat_non_ecrit", raison=f"état local non écrit ({e}) : marqueur non posé")
        dire(f"Audit passé, mais l'état local n'a pas pu être écrit ({e}) : marqueur non posé, relancez.")
        _ecrire_releves(releves, releve)
        return releve
    code, _s, _e = bash(serveur, script_marqueur(empreinte_bac))
    if code != 0:
        releve.update(verdict="audit_echoue", raison=f"marqueur non écrit (code {code})")
        _ecrire_releves(releves, releve)
        return releve
    dire("Audit du bac à sable : tout passe ; marqueur écrit.")
    try:
        (rafraichir or _rafraichir)(serveur, dossier_etat)
    except _erreurs_ecriture() as e:
        releve.update(verdict="hote_echoue", raison=f"sonde non rangée ({e}) : test non lancé, relancez")
        _ecrire_releves(releves, releve)
        return releve
    passages = _passages(executer, commande, racine, "hote_bac_a_sable", lic["variante"] or "B1", None, horloge, dire)
    releve["passages"] += passages
    ok = passages[0]["code"] == 0
    releve.update(verdict="bac_a_sable_pret" if ok else "hote_echoue",
                  raison="" if ok else f"code {passages[0]['code']} par l'exécuteur hote_bac_a_sable",
                  risque=tests_serveur.RISQUE_A)
    _ecrire_releves(releves, releve)
    return releve


# --- branchements réels (jamais appelés par les tests) ---------------------------------------------------------------

def _ssh():
    import plateforme_ssh
    return plateforme_ssh


def _lire_serveurs(dossier_etat):
    import serveur_modele
    return serveur_modele.lire(dossier_etat)


def _executer_vers(serveur, dossier_etat):
    def executer(commande, **k):
        return tests_serveur.executer(commande, dossier_etat=dossier_etat, choisir=lambda d, requises: serveur, **k)
    return executer


def _rafraichir(serveur, dossier_etat):
    import serveur_etat
    import serveur_installation
    mots = {}
    etat = serveur_etat.sonder(serveur, mots=mots)
    joint = not all(s == "inconnue" for s in etat.values())
    serveur_installation.enregistrer_sonde(dossier_etat, serveur, etat, mots=mots,
                                           charge=serveur_etat.charge(serveur) if joint else None)   # la charge n'est pas effacée


def _ecrire_releves(chemin, releve):
    chemin = Path(chemin or RELEVES)
    try:
        x = json.loads(chemin.read_text(encoding="utf-8"))
        essais = x.get("essais") if isinstance(x, dict) and isinstance(x.get("essais"), list) else []
    except (OSError, ValueError):
        essais = []
    essais = (essais + [releve])[-RELEVES_MAX:]
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
    temporaire.write_text(json.dumps({"essais": essais}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporaire, chemin)


def main(argv=None, essai_=essai) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="tests_unity_essai.py", description="Expérience J13/J14 de la licence Unity au serveur.")
    p.add_argument("--serveur-id", required=True)
    p.add_argument("--dossier", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--variantes", default="B1,B2")
    p.add_argument("--hotes-licence", default="")
    p.add_argument("--hote", action="store_true")
    a = p.parse_args(argv)
    variantes = tuple(v for v in a.variantes.split(",") if v)
    if not variantes or not all(v in VARIANTES for v in variantes):
        print("Variantes : B1, B2, B3 (séparées par des virgules).", file=sys.stderr)
        return 2
    try:
        r = essai_(a.serveur_id, a.dossier, a.test, variantes, a.hote, [h for h in a.hotes_licence.split(",") if h])
    except Refus as e:
        print(f"Refusé : {e}", file=sys.stderr)
        return 2
    return 0 if r.get("verdict") in ("conteneur", "hote", "bac_a_sable_pret") else 1


if __name__ == "__main__":
    sys.exit(main())
