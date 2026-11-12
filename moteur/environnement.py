"""L'environnement du poste : ce que le workflow d'une fonctionnalité demande comme outils, et ce qui est déjà là.

La proposition d'un workflow (`proposer_organisation`) liste les outils dont ses étapes ont besoin :
`{"outil", "pour", "executables": [noms], "installation": texte}`. `verifier` regarde, **en code**, lesquels sont déjà
sur le poste : jamais une commande écrite par l'IA. Un exécutable est un **nom** (`java`, `gradle`), cherché dans le
`PATH` puis aux emplacements usuels (`JAVA_HOME`, `ANDROID_HOME`, `ANDROID_SDK_ROOT`) ; un nom qui n'a pas la forme d'un
nom de programme (espace, `;`, `&`, chemin, option) est refusé sans être cherché ni lancé. Ce qui est trouvé n'est lancé
que pour lire sa version, avec une option d'une liste fixe (`--version`, `-version`, `version`), délai de 10 s.

Chaque outil rendu porte son `etat` : `en_place` (avec `chemin` et, si lisible, `version`) ou `a_installer`.

Un outil peut porter une **version minimale** (champ `version_min`, ou le nombre qui suit son nom : « JDK 17 »). La
version lue est alors comparée : trop ancienne (Java 8 pour un JDK 17), l'outil est `a_installer` et `raison` dit ce
qui a été trouvé ; illisible, il reste `en_place` mais `raison` dit que la version n'a pas pu être vérifiée.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

from moteur.jugement import MOTIF_EXECUTABLE
from orchestrateur import fiches

OPTIONS_DE_VERSION = ("--version", "-version", "version")   # la liste fixe : jamais une option venue de l'IA
DELAI_VERSION_S = 10
LONGUEUR_VERSION = 120
# Où chercher après le PATH : (variable d'environnement, sous-dossiers du SDK ou du JDK). `*` : tous les dossiers du niveau.
EMPLACEMENTS = (("JAVA_HOME", ("bin",)),
                ("ANDROID_HOME", ("cmdline-tools/latest/bin", "cmdline-tools/bin", "platform-tools", "tools/bin",
                                  "emulator", "build-tools/*")),
                ("ANDROID_SDK_ROOT", ("cmdline-tools/latest/bin", "cmdline-tools/bin", "platform-tools", "tools/bin",
                                      "emulator", "build-tools/*")))


def executer_version(argv, delai_s=DELAI_VERSION_S):
    """(code, sortie) d'un programme lancé pour lire sa version : sans fenêtre, sans entrée, sortie et erreurs réunies."""
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=delai_s,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return p.returncode, (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")


def _dossiers_usuels(env):
    for variable, sous_dossiers in EMPLACEMENTS:
        racine = (env.get(variable) or "").strip()
        if not racine or not Path(racine).is_dir():
            continue
        for sous in sous_dossiers:
            if sous.endswith("/*"):
                parent = Path(racine) / sous[:-2]
                if parent.is_dir():
                    yield from sorted((d for d in parent.iterdir() if d.is_dir()), reverse=True)
            else:
                yield Path(racine) / sous


# Le `PATH` d'un poste Windows se lit dans le registre : un logiciel installé après le démarrage du moteur y est, mais pas
# dans l'environnement du processus (Windows n'actualise pas l'environnement d'un processus déjà lancé). Le système
# d'abord, puis l'utilisateur, comme Windows les assemble pour un nouveau processus.
REGISTRE = (("HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            ("HKEY_CURRENT_USER", "Environment"))
VARIABLES_RELUES = tuple(v for v, _ in EMPLACEMENTS)       # JAVA_HOME, ANDROID_HOME… peuvent aussi être posées après coup
# Où les installateurs courants déposent leurs programmes : (variable du dossier de base, motif relatif ; `*` = un niveau).
INSTALLATIONS = (("LOCALAPPDATA", "Microsoft/WinGet/Links"),
                 ("LOCALAPPDATA", "Microsoft/WinGet/Packages/*"),
                 ("LOCALAPPDATA", "Microsoft/WinGet/Packages/*/*"),
                 ("LOCALAPPDATA", "Microsoft/WinGet/Packages/*/bin"),
                 ("LOCALAPPDATA", "Microsoft/WinGet/Packages/*/*/bin"),
                 *((base, f"{sous}/bin") for base in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")
                   for sous in ("Eclipse Adoptium/*", "Microsoft/jdk-*", "Java/*")))


def lire_registre(racine, sous_cle, nom):
    """La valeur texte `nom` de `racine\\sous_cle` (`winreg`, aucune commande lancée), ou `None` : pas Windows, clé ou valeur
    absente."""
    try:
        import winreg
        with winreg.OpenKey(getattr(winreg, racine), sous_cle) as cle:
            valeur, _ = winreg.QueryValueEx(cle, nom)
    except (ImportError, OSError, AttributeError):
        return None
    return valeur if isinstance(valeur, str) else None


def _variable(env, nom):
    if nom in env:
        return env[nom]
    return next((v for k, v in env.items() if str(k).upper() == nom.upper()), None)


def developper(texte, env):
    """`texte` avec ses `%VARIABLES%` remplacées par celles de `env` (sans tenir compte de la casse) ; une variable
    inconnue reste telle quelle."""
    def remplacer(m):
        v = _variable(env, m.group(1))
        return str(v) if v not in (None, "") else m.group(0)
    return re.sub(r"%([^%=]+)%", remplacer, str(texte or ""))


def environnement_a_jour(env, lire=lire_registre):
    """`env` complété par le registre : les variables du système puis de l'utilisateur (`JAVA_HOME`…, développées) priment
    sur celles du processus, qui peuvent dater d'avant l'installation."""
    a_jour = dict(env)
    for racine, sous_cle in REGISTRE:
        for variable in VARIABLES_RELUES:
            valeur = lire(racine, sous_cle, variable)
            if valeur and valeur.strip():
                a_jour[variable] = developper(valeur.strip(), a_jour)
    return a_jour


def dossiers_du_path_a_jour(env, lire=lire_registre):
    """Les dossiers du `PATH` tel que Windows le donne à un nouveau processus (registre système puis utilisateur, variables
    développées), dans l'ordre, sans doublon."""
    vus, dossiers = set(), []
    for racine, sous_cle in REGISTRE:
        brut = lire(racine, sous_cle, "Path") or lire(racine, sous_cle, "PATH")
        for morceau in developper(brut or "", env).split(";"):
            morceau = morceau.strip().strip('"')
            if morceau and morceau.lower() not in vus:
                vus.add(morceau.lower())
                dossiers.append(Path(morceau))
    return dossiers


def _developper_motif(base, motif):
    """Les dossiers existants qui répondent à `base/motif` (`*` et `?` valent pour un niveau), les plus récents d'abord."""
    racine = Path(base)
    if not racine.is_dir():
        return []
    return sorted((p for p in racine.glob(motif) if p.is_dir()), key=lambda p: str(p), reverse=True)


def dossiers_d_installation(env):
    """Les dossiers où winget (`WinGet\\Links`, `WinGet\\Packages\\…`) et les JDK (`Eclipse Adoptium`, `Microsoft\\jdk-*`,
    `Java`) s'installent d'ordinaire, quand ils existent."""
    vus, dossiers = set(), []
    for variable, motif in INSTALLATIONS:
        base = (_variable(env, variable) or "").strip()
        if not base:
            continue
        for d in _developper_motif(base, motif):
            if str(d).lower() not in vus:
                vus.add(str(d).lower())
                dossiers.append(d)
    return dossiers


def dossiers_a_chercher(env, lire=lire_registre):
    """Après le `PATH` du processus : les emplacements usuels (variables relues dans le registre), le `PATH` à jour, puis les
    dossiers d'installation courants."""
    env = environnement_a_jour(env, lire) if lire else env
    yield from _dossiers_usuels(env)
    if lire:
        yield from dossiers_du_path_a_jour(env, lire)
    yield from dossiers_d_installation(env)


def trouver(nom, *, which=shutil.which, env=None, lire=None):
    """Le chemin du programme `nom` (un nom seul), ou `None` : le `PATH` du processus, les emplacements usuels, le `PATH` à
    jour du registre (Windows), puis les dossiers d'installation courants. Sans `env` (le vrai poste) le registre est lu ;
    avec un `env` donné, seulement si `lire` l'est (les essais ne lisent pas le vrai registre)."""
    if env is None:
        env, lire = dict(os.environ), lire or lire_registre
    chemin = which(nom)
    if chemin:
        return str(chemin)
    for dossier in dossiers_a_chercher(env, lire):
        chemin = which(nom, path=str(dossier))
        if chemin:
            return str(chemin)
    return None


def lire_version(chemin, executer=executer_version):
    """La première ligne de la sortie de la première option de la liste fixe qui répond (code 0), sinon `None`."""
    for option in OPTIONS_DE_VERSION:
        code, sortie = executer([chemin, option], DELAI_VERSION_S)
        lignes = [x.strip() for x in str(sortie or "").splitlines() if x.strip()]
        if code == 0 and lignes:
            return lignes[0][:LONGUEUR_VERSION]
    return None


def _numeros(texte):
    m = re.search(r"\d+(?:\.\d+)*", str(texte or ""))
    return tuple(int(x) for x in m.group(0).split(".")) if m else None


def version_minimale(outil):
    """La version minimale demandée par un outil, en nombres (`(17,)`), ou `None` : le champ `version_min`, sinon le
    nombre qui suit un nom d'un seul mot (« JDK 17 », « Gradle 8.5 ») ; « Android SDK 34 complet » n'en porte pas."""
    explicite = outil.get("version_min")
    if explicite not in (None, ""):
        return _numeros(explicite)
    m = re.fullmatch(r"\S+ v?(\d+(?:\.\d+)*)\+?", str(outil.get("outil") or "").strip())
    return _numeros(m.group(1)) if m else None


def numeros_de_version(ligne):
    """Les nombres de la version lue dans une ligne (`(8,)` pour « java version "1.8.0_351" », `(21, 0, 4)` pour
    « openjdk version "21.0.4" »), ou `None` si rien de lisible. Java 1.x est la version x."""
    texte = str(ligne or "")
    m = re.search(r'"(\d+(?:\.\d+)*)', texte) or re.search(r"\d+(?:\.\d+)+", texte) or re.search(r"\d+", texte)
    if not m:
        return None
    n = tuple(int(x) for x in re.findall(r"\d+", m.group(0) if m.lastindex is None else m.group(1)))
    if re.search(r"java|jdk|jre", texte, re.I) and len(n) > 1 and n[0] == 1:
        n = n[1:]
    return n


def version_suffisante(lue, minimale):
    """La version lue (une ligne de sortie, ou un numéro) atteint-elle la version minimale ? `None` si l'une des deux
    manque ou n'a aucun nombre. Les nombres se comparent dans l'ordre (`21.0.2` ≥ `17` ; `17` < `17.0.1`) ; une version
    Java `1.x` vaut `x` quand la ligne dit java, jdk ou jre (`java version "1.8.0_381"` < `17`)."""
    trouvee, voulue = numeros_de_version(lue), _numeros(minimale)
    if trouvee is None or voulue is None:
        return None
    return trouvee + (0,) * (len(voulue) - len(trouvee)) >= voulue


def verifier(outils, *, which=shutil.which, executer=executer_version, env=None, lire=None):
    """Chaque outil de la proposition avec son état : `en_place` (`chemin`, `version`?) ou `a_installer`. Un outil est en
    place quand **tous** ses exécutables sont trouvés. Un exécutable est cherché une seule fois, même s'il sert à
    plusieurs outils. Un nom refusé (pas un nom de programme) n'est ni cherché ni lancé : l'outil reste à installer et
    le dit dans `refuses`. Un outil à installer porte aussi `introuvables` (les exécutables qu'on n'a pas trouvés) ;
    trop ancien, il garde la `version` trouvée."""
    trouves = {}      # nom -> chemin | None, pour ne chercher (et ne lancer) qu'une fois chaque exécutable
    versions = {}
    sortie = []
    for outil in outils:
        o = avec_aide(outil)
        noms = [n for n in outil.get("executables") or [] if isinstance(n, str)]
        valides = [n for n in noms if MOTIF_EXECUTABLE.match(n)]
        refuses = [n for n in noms if not MOTIF_EXECUTABLE.match(n)]
        for n in valides:
            if n not in trouves:
                trouves[n] = trouver(n, which=which, env=env, lire=lire)
        chemins = [trouves[n] for n in valides]
        if valides and not refuses and all(chemins):
            o["etat"], o["chemin"] = "en_place", chemins[0]
            for ancien in ("version", "raison", "introuvables", "refuses"):
                o.pop(ancien, None)
            if valides[0] not in versions:
                versions[valides[0]] = lire_version(chemins[0], executer)
            if versions[valides[0]]:
                o["version"] = versions[valides[0]]
            minimale = version_minimale(outil)
            if minimale:
                texte_min = ".".join(str(x) for x in minimale)
                suffisante = version_suffisante(versions[valides[0]], texte_min)
                if suffisante is None:
                    o["raison"] = f"version {texte_min} minimum demandée, version non vérifiée (illisible)"
                elif not suffisante:
                    o["etat"] = "a_installer"
                    o["raison"] = f"version trouvée : {versions[valides[0]]} ; {texte_min} minimum demandée"
        else:
            o["etat"] = "a_installer"
            o.pop("chemin", None)
            o.pop("version", None)
            o.pop("raison", None)
            o["introuvables"] = [n for n in valides if not trouves[n]]
            if refuses:
                o["refuses"] = refuses
        sortie.append(o)
    return sortie


def a_installer(outils):
    return [o for o in outils if o.get("etat") != "en_place"]


NOTE_DECLARE = "déclaré installé par le Directeur (non vérifié)"
CHAMPS_DE_CONSTAT = ("verification", "raison", "refuses", "introuvables", "chemin", "version")   # ce qu'une vérification pose


def constat(outil_verifie):
    """Ce qu'une vérification a trouvé pour un outil (sortie de `verifier`), en clair, pour le bureau : `{trouve,
    cherche: [exécutables], introuvables: [exécutables], version_demandee, version_trouvee, raison?}`."""
    trouve = outil_verifie.get("etat") == "en_place"
    cherche = [n for n in outil_verifie.get("executables") or [] if isinstance(n, str)]
    introuvables = [n for n in outil_verifie.get("introuvables") or [] if isinstance(n, str)] if not trouve else []
    if not trouve and not introuvables and not outil_verifie.get("raison"):
        introuvables = list(cherche)
    minimale = version_minimale(outil_verifie)
    c = {"trouve": trouve, "cherche": cherche, "introuvables": introuvables,
         "version_demandee": ".".join(str(x) for x in minimale) if minimale else None,
         "version_trouvee": outil_verifie.get("version") if isinstance(outil_verifie.get("version"), str) else None}
    if outil_verifie.get("raison"):
        c["raison"] = str(outil_verifie["raison"])
    return c


def declare(outil):
    """L'outil que le Directeur affirme installé : `en_place`, `declare` vrai et la note, sans rien qu'une vérification ait
    posé (chemin, version, raison) : on ne l'a pas trouvé."""
    o = {k: v for k, v in outil.items() if k not in CHAMPS_DE_CONSTAT and k != "en_cours"}
    o.update(etat="en_place", declare=True, note=NOTE_DECLARE)
    return o


def texte_du_constat(outil, constat_):
    """« JDK 21 : non trouvé (cherché : java, javac ; version 17 minimum ; trouvée : …) » ou « JDK 21 : trouvé »."""
    if constat_.get("trouve"):
        return f"{outil} : trouvé"
    morceaux = []
    if constat_.get("cherche"):
        morceaux.append("cherché : " + ", ".join(constat_["cherche"]))
    if constat_.get("introuvables") and constat_["introuvables"] != constat_.get("cherche"):
        morceaux.append("introuvable : " + ", ".join(constat_["introuvables"]))
    if constat_.get("version_demandee"):
        morceaux.append(f"version {constat_['version_demandee']} minimum demandée")
    if constat_.get("version_trouvee"):
        morceaux.append(f"version trouvée : {constat_['version_trouvee']}")
    return f"{outil} : non trouvé" + (f" ({' ; '.join(morceaux)})" if morceaux else "")


def avec_aide(outil):
    """L'outil avec ses trois champs d'aide à l'installation, valeurs par défaut comprises (un ancien résultat n'en a
    pas) : `telechargement` (URL https officielle ou `None`), `etapes` (le mode opératoire, une liste de textes) et
    `autonome` (vrai si un agent peut l'installer seul, sans clic ni droits d'administrateur) ; `objectif` s'ajoute
    (à quoi l'outil sert dans ce projet, `None` pour un ancien résultat : l'étape `pour` le remplace à l'affichage)."""
    o = dict(outil)
    url = o.get("telechargement")
    o["telechargement"] = url if isinstance(url, str) and url.startswith("https://") else None
    etapes = o.get("etapes")
    o["etapes"] = [x for x in etapes if isinstance(x, str) and x.strip()] if isinstance(etapes, list) else []
    o["autonome"] = o.get("autonome") is True
    objectif = o.get("objectif")
    o["objectif"] = objectif.strip() if isinstance(objectif, str) and objectif.strip() else None
    return o


def autonomes_a_installer(outils):
    """Les outils qui manquent et qu'un agent peut installer seul : les seuls qu'il reçoit."""
    return [o for o in a_installer(outils) if o.get("autonome") is True]


def installe_par(journal_ou_lignes, outil):
    """Vrai si une ligne du journal d'une tâche d'installation nomme cet outil (`- <outil> (…`)."""
    return any(str(x).startswith(f"- {outil} (") for x in journal_ou_lignes or [])


ROLE_INSTALLATION = "environnement"      # l'agent qui installe les outils du poste
TITRE_INSTALLATION = "Mise en place de l'environnement"


def journal_d_installation(manquants):
    """Les consignes de la tâche d'installation : chaque outil qui manque, son programme et comment l'installer."""
    journal = ["Outils à installer (de préférence sans droits d'administrateur, depuis les sources officielles) :"]
    journal += [f"- {x['outil']} ({', '.join(x.get('executables') or [])}) : {x.get('installation', '')}"
                + (f" Objectif : {x['objectif']}" if x.get("objectif") else "")
                + (f" Page officielle : {x['telechargement']}" if x.get("telechargement") else "")
                for x in manquants]
    journal.append("Vérifie chaque outil après son installation (chemin et version) et rends compte.")
    return journal


def texte_des_manquants(manquants, intro=None):
    """Le texte de la décision `environnement` : les noms seulement ; l'objectif, le lien officiel, le mode opératoire et
    le bouton d'installation en autonomie de chaque outil sont montrés par le bureau, outil par outil."""
    return ((intro + " ") if intro else "") + (
        "Il manque encore des outils sur le poste : " + ", ".join(x["outil"] for x in manquants) + ". Pour chacun, "
        "à quoi il sert, le lien de téléchargement officiel et le mode opératoire ; un bouton l'installe en autonomie "
        "quand un agent peut le faire seul. Dites « C'est fait » quand c'est installé (je revérifie), ou « Continuer "
        "sans » : les étapes qui en ont besoin le diront.")


def tache_d_installation_du_projet(manquants):
    """L'entrée `lancer tache` de l'installation portée par le projet (sans fonctionnalité, colonne « cadrage ») : le
    moteur la lance seul, et son retour revérifie le poste sans retenir le cadrage d'aucune demande."""
    return {"titre": TITRE_INSTALLATION, "etape": "environnement", "role": ROLE_INSTALLATION, "colonne": "cadrage",
            "active": False, "journal": journal_d_installation(manquants)}


def agent_d_installation(existants, nouveaux, flux, services, outils_installation=None):
    """L'agent qui installe les outils du poste, et son brief : `(agent, brief)`, ou `(None, None)` si un agent du rôle
    existe déjà (parmi `existants` et `nouveaux`, des fiches `{cle, role}`) ou si aucun service ne peut l'accueillir.
    Son service : celui de la première étape d'agent du `flux` (pas le premier du projet, souvent la facturation), à
    défaut le premier de `services`. Avec `outils_installation`, sa fiche porte ces règles d'outils (`outils` : les
    outils habituels, puis les règles)."""
    etapes = [e for e in flux if not e.get("validation")]
    service = etapes[0]["service"] if etapes else (services[0]["id"] if services else None)
    if any(a["role"] == ROLE_INSTALLATION for a in list(existants) + list(nouveaux)) or not service:
        return None, None
    pris = {a["cle"] for a in existants} | {a["cle"] for a in nouveaux}
    cle = next(c for c in (f"env-{n}" for n in range(1, 100)) if c not in pris)
    agent = {"cle": cle, "role": ROLE_INSTALLATION, "service": service, "modele": "Sonnet",
             "lieu": "local", "justification": "Installer et vérifier les outils, avec soin.", "fable_suggere": False,
             "texte": "Tu installes les outils du poste dont le workflow a besoin, puis tu vérifies chacun."}
    if outils_installation:
        agent["outils"] = ", ".join(dict.fromkeys(list(fiches.OUTILS_PAR_DEFAUT) + list(outils_installation)))
    brief = ("Tu installes les outils du poste demandés par une tâche « Mise en place de l'environnement ». Installe "
             "de préférence pour l'utilisateur seul (sans droits d'administrateur) et depuis les sources officielles. "
             "Après chaque installation, vérifie l'outil (chemin et version) et rends compte. Si une installation "
             "échoue (droits d'administrateur, téléchargement refusé, outil introuvable), dis ce qui manque, pourquoi "
             "et comment l'installer à la main : n'insiste pas.")
    return agent, brief
