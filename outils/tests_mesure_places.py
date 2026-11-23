"""Mesure du nombre de campagnes de tests simultanées qu'un serveur supporte (réglage `places_tests`).

    py -3.12 outils/tests_mesure_places.py --paliers 1,2,3,4
    py -3.12 outils/tests_mesure_places.py --mixte gradle:2,python:2 --dossier-gradle <projet Gradle>   # jalon J11

Chaque palier k lance k campagnes complètes en même temps au serveur (`tests_serveur.executer(..., forcer=True)`), relève
la durée de chacune et écrit `~/MyIAFactory/tests-places-mesure.json`. `recommander` en tire le plus grand k dont la durée
médiane reste sous 1,5 fois celle d'une campagne seule et dont la mémoire cumulée tient dans la moitié de celle du serveur.

La mémoire : une sonde lit `/proc/meminfo` du serveur (`--serveur-id`, défaut le premier déclaré) toutes les 3 s pendant
le palier ; le pic est compté au-dessus de la mémoire utilisée au départ (agents, émulateur déjà en place).
`--avec-emulation <apk> --projet-emulation <projet enregistré>` : une émulation pilote (émulateur démarré) tourne
pendant toute la mesure, arrêtée à la fin, même en cas d'erreur.
"""
import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
RESULTAT = Path("~/MyIAFactory/tests-places-mesure.json").expanduser()
FACTEUR_DUREE = 1.5
PART_MEMOIRE = 0.5


def recommander(mesures, memoire_serveur_mo):
    """`mesures` : {k: {"durees": [s, ...], "pics_mo": [Mo, ...]}} ; rend le plus grand k acceptable, 1 au moins."""
    seule = mesures.get(1) or mesures.get("1")
    if not seule or not seule.get("durees"):
        return 1
    base = statistics.median(seule["durees"])
    meilleur = 1
    for k in sorted(int(c) for c in mesures):
        m = mesures.get(k) or mesures.get(str(k))
        if not m or not m.get("durees"):
            continue
        if statistics.median(m["durees"]) > FACTEUR_DUREE * base:
            break
        if sum(m.get("pics_mo") or []) > PART_MEMOIRE * memoire_serveur_mo:
            break
        meilleur = k
    return meilleur


FAMILLES_MIXTES = {"python": None, "gradle": ["./gradlew", "testDebugUnitTest"], "node": ["npm", "test"]}


def lire_mixte(texte):
    """`gradle:2,python:2` -> [("gradle", 2), ("python", 2)] ; ValueError si une famille est inconnue, un nombre n'est pas
    de 1 à 4, ou si le total dépasse 4 (le plafond des places)."""
    paliers = []
    for morceau in str(texte).split(","):
        famille, _, n = morceau.strip().partition(":")
        if famille not in FAMILLES_MIXTES or not n.isdigit() or not 1 <= int(n) <= 4:
            raise ValueError(f"palier mixte refusé : {morceau!r} (famille:nombre, familles {sorted(FAMILLES_MIXTES)}, 1 à 4)")
        paliers.append((famille, int(n)))
    if not paliers or sum(n for _, n in paliers) > 4:
        raise ValueError("palier mixte refusé : de 1 à 4 campagnes en tout")
    return paliers


def mesurer_mixte(paliers, executer, horloge=time.time):
    """Lance TOUTES les campagnes du palier en même temps (`executer(famille) -> code`) ; rend
    {famille: {"durees": [...], "codes": [...]}} (jalon J11 : par exemple 2 Gradle et 2 Python)."""
    mesures = {}
    verrou = threading.Lock()

    def une(famille):
        debut = horloge()
        code = executer(famille)
        with verrou:
            m = mesures.setdefault(famille, {"durees": [], "codes": []})
            m["codes"].append(code)
            m["durees"].append(horloge() - debut)

    fils = [threading.Thread(target=une, args=(famille,)) for famille, n in paliers for _ in range(n)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    return mesures


class _Collecteur:
    def write(self, b):
        return len(b)

    def flush(self):
        pass


def memoire_utilisee_mo(meminfo):
    """`MemTotal - MemAvailable` d'un `/proc/meminfo`, en Mo ; None si illisible."""
    valeurs = {}
    for ligne in str(meminfo).splitlines():
        nom, _, reste = ligne.partition(":")
        morceaux = reste.split()
        if morceaux and morceaux[0].isdigit():
            valeurs[nom.strip()] = int(morceaux[0])
    if "MemTotal" not in valeurs or "MemAvailable" not in valeurs:
        return None
    return (valeurs["MemTotal"] - valeurs["MemAvailable"]) // 1024


class Sonde:
    """Relève la mémoire utilisée du serveur (`lire() -> Mo | None`) toutes les `pas` secondes dans un fil ; le pic d'un
    palier est mesuré AU-DESSUS de la première lecture (ce qui tournait déjà : agents, émulateur de `--avec-emulation`)."""

    def __init__(self, lire, pas=3.0):
        self._lire, self._pas = lire, pas
        self._depart = self._pic = None
        self._fin = threading.Event()
        self._fil = None

    def depart(self):
        self._depart = self._lire()

    def relever(self):
        v = self._lire()
        if v is not None and (self._pic is None or v > self._pic):
            self._pic = v

    def pic_au_dessus(self):
        if self._depart is None or self._pic is None:
            return None
        return max(0, self._pic - self._depart)

    def demarrer(self):
        self.depart()

        def boucle():
            while not self._fin.wait(self._pas):
                self.relever()

        self._fil = threading.Thread(target=boucle, daemon=True)
        self._fil.start()

    def arreter(self):
        self._fin.set()
        if self._fil is not None:
            self._fil.join()
        self.relever()
        return self.pic_au_dessus()


def sonde_ssh(serveur, ssh=None, pas=3.0):
    """Une `Sonde` qui lit `/proc/meminfo` du serveur par SSH (lecture seule, aucun droit d'administrateur)."""
    if ssh is None:
        import plateforme_ssh as ssh

    def lire():
        code, sortie, _ = ssh.executer(f"{serveur.utilisateur}@{serveur.hote}", "cat /proc/meminfo", serveur.cle, delai=20)
        return memoire_utilisee_mo(sortie) if code == 0 else None

    return lambda: Sonde(lire, pas)


def mesurer(paliers, executer, horloge=time.time, sonde=None):
    """Lance, pour chaque palier k, k campagnes simultanées ; rend {k: {"durees": [...], "codes": [...], "pics_mo": [...]}}.
    Avec `sonde` (fabrique d'objets `demarrer()`/`arreter() -> Mo`) : `pics_mo` vaut [pic mémoire cumulé du palier]."""
    mesures = {}
    for k in paliers:
        durees, codes = [], []

        def une():
            debut = horloge()
            code = executer()
            codes.append(code)
            durees.append(horloge() - debut)

        s = sonde() if sonde else None
        if s:
            s.demarrer()
        fils = [threading.Thread(target=une) for _ in range(k)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        pic = s.arreter() if s else None
        mesures[k] = {"durees": durees, "codes": codes, "pics_mo": [] if pic is None else [pic]}
    return mesures


def _lanceur_cli(args):
    import subprocess
    r = subprocess.run([sys.executable, str(RACINE / "lancer.py"), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def demarrer_emulation(apk, projet, lanceur=_lanceur_cli):
    """`--avec-emulation` : une tâche d'émulation en mode pilote (projet enregistré, `recette-emulateur` au serveur),
    émulateur démarré (`demarrer`) ; rend son identifiant. RuntimeError si le lancement est refusé."""
    code, sortie = lanceur(["serveur-tache", "lancer", "--apk", str(apk), "--mode", "pilote", "--projet", str(projet)])
    try:
        ident = json.loads(sortie[sortie.index("{"):sortie.rindex("}") + 1]).get("id") if code == 0 else None
    except (ValueError, AttributeError):
        ident = None
    if not ident:
        raise RuntimeError(f"Émulation non lancée (code {code}) : {sortie.strip()[-400:]}")
    code, sortie = lanceur(["serveur-outil", ident, "demarrer", "--projet", str(projet)])
    if code != 0:
        arreter_emulation(ident, lanceur)
        raise RuntimeError(f"Émulateur non démarré (code {code}) : {sortie.strip()[-400:]}")
    return ident


def arreter_emulation(ident, lanceur=_lanceur_cli):
    return lanceur(["serveur-tache", "arreter", ident])[0]


def principal(argv=None):
    import tests_serveur
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paliers", default="1,2,3")
    ap.add_argument("--memoire-serveur-mo", type=int, default=62 * 1024)
    ap.add_argument("--mixte", help="paliers mixtes, ex. gradle:2,python:2 (toutes en même temps)")
    ap.add_argument("--dossier-gradle", help="projet Gradle des campagnes « gradle » d'un palier mixte")
    ap.add_argument("--serveur-id", help="le serveur sondé pour la mémoire (défaut : le premier déclaré)")
    ap.add_argument("--avec-emulation", metavar="APK", help="une émulation pilote tourne pendant la mesure (APK)")
    ap.add_argument("--projet-emulation", help="projet enregistré de l'émulation (`recette-emulateur` au serveur)")
    args = ap.parse_args(argv)
    if args.avec_emulation and not args.projet_emulation:
        ap.error("--avec-emulation demande --projet-emulation")
    if args.mixte and any(f == "gradle" for f, _ in lire_mixte(args.mixte)) and not args.dossier_gradle:
        ap.error("--mixte avec gradle demande --dossier-gradle")
    import plateforme_acces
    import serveur_modele
    serveurs = serveur_modele.lire(plateforme_acces.DOSSIER)
    serveur = next((s for s in serveurs if not args.serveur_id or s.id == args.serveur_id), None)
    if serveur is None:
        ap.error("serveur inconnu")
    sonde = sonde_ssh(serveur)
    emulation = demarrer_emulation(args.avec_emulation, args.projet_emulation) if args.avec_emulation else None
    try:
        return _principal(args, tests_serveur, sonde)
    finally:
        if emulation:
            arreter_emulation(emulation)


def _noter(cle, valeur, fichier=None):
    """Ajoute la mesure `cle` (« paliers », « paliers+emulation », « mixte… ») au fichier des mesures, sans effacer
    les autres."""
    fichier = Path(fichier or RESULTAT)
    try:
        tout = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tout = {}
    tout = tout if isinstance(tout, dict) else {}
    tout[cle] = valeur
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(tout, indent=2), encoding="utf-8")


def _principal(args, tests_serveur, sonde):
    cle = ("mixte " + args.mixte if args.mixte else "paliers " + args.paliers) + (" +emulation" if args.avec_emulation else "")
    if args.mixte:
        paliers = lire_mixte(args.mixte)
        places = min(4, sum(n for _, n in paliers))

        def executer_mixte(famille):
            commande = FAMILLES_MIXTES[famille] or ["python3", "outils/tests_paralleles.py", "-j", str(tests_serveur.LIMITES["cpus"])]
            dossier = args.dossier_gradle if famille == "gradle" else RACINE
            return tests_serveur.executer(commande, dossier=dossier, attendre=True, forcer=True, places=places,
                                          sortie=_Collecteur(), sortie_erreur=_Collecteur())

        s = sonde()
        s.demarrer()
        mesures = mesurer_mixte(paliers, executer_mixte)
        pic = s.arreter()
        _noter(cle, {"mesures": mesures, "pic_mo": pic})
        for famille, m in mesures.items():
            print(f"{famille} x{len(m['durees'])} : médiane {statistics.median(m['durees']):.0f} s, codes {m['codes']}")
        print(f"Pic mémoire cumulé (au-dessus du départ) : {pic} Mo")
        return 0
    paliers = [int(x) for x in args.paliers.split(",") if x.strip()]
    commande = ["python3", "outils/tests_paralleles.py", "-j", str(tests_serveur.LIMITES["cpus"])]

    def executer():
        return tests_serveur.executer(commande, dossier=RACINE, attendre=True, forcer=True, places=max(paliers),
                                      sortie=_Collecteur(), sortie_erreur=_Collecteur())

    mesures = mesurer(paliers, executer, sonde=sonde)
    reco = recommander(mesures, args.memoire_serveur_mo)
    _noter(cle, {"mesures": mesures, "recommandation": reco})
    for k, m in mesures.items():
        print(f"{k} campagne(s) : médiane {statistics.median(m['durees']):.0f} s, codes {m['codes']}, "
              f"pic mémoire {m['pics_mo'] or '?'} Mo")
    print(f"Recommandation : places_tests = {reco}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
