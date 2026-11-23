"""Aides HÔTE de l'enveloppe des campagnes de tests (`taches/lancer_tests.sh`), lancées par `python3 -I` sur le serveur.

Bibliothèque standard seulement (Python 3.9 et plus) ; aucune donnée lue ici n'est jamais une consigne.

- `--commande` : la commande (entrée standard) doit être un tableau JSON de 1 à 64 chaînes, 4 096 octets au plus, premier
  élément non vide, aucun NUL : la règle même de `entree-tests.sh`, contrôlée AVANT toute écriture. Code 0 admise, 2 refusée.
- `--archive <entree.tar>` : l'instantané déposé par le poste est relu en-tête par en-tête AVANT `docker run`, sans
  `tarfile` (qui comprend trop de formats) : seulement des membres USTAR (`ustar\\0` + `00`) de type fichier ordinaire
  (`0` ou NUL), somme de contrôle juste, taille en octal (jamais base 256), aucun lien (nom de lien vide), droits sans
  bit spécial, nom relatif sûr (`nom_sur`, la règle de `outils/tests_instantane.py`), aucun doublon ni fichier qui serait
  aussi un dossier, `MAX_FICHIER` par fichier, `MAX_TOTAL` au total, `MAX_FICHIERS` membres, archive de `MAX_ARCHIVE`
  octets au plus, multiple de 512, et rien que des zéros après le premier bloc nul. Ni dossier, ni lien symbolique ou dur,
  ni périphérique, ni membre GNU (noms longs, éparpillés), ni en-tête pax : l'extraction de `tar -x` du conteneur ne peut
  donc créer que des fichiers ordinaires sous /work. Code 0 admise, 3 refusée (raison sur la sortie d'erreur) ; tout autre
  code (plantage de python : 1) n'est pas un refus de l'archive.
- `--prefixer <marque> <max>` : relaie l'entrée vers la sortie en mettant `| ` au début de CHAQUE ligne (bloc par bloc, sans
  attendre la fin des lignes : la sortie reste en direct) et finit toujours par un retour à la ligne ; \r devient \n et les
  autres séparateurs de lignes (\x0b \x0c \x1c-\x1e U+0085 U+2028 U+2029) sont écrits sous forme de texte (`Nettoyeur`) :
  aucune ligne du conteneur ne peut ressembler à une ligne de l'enveloppe (`#fin`, `#refus`, `#attente`). Au-delà de
  `<max>` octets ÉCRITS (après réécriture et préfixe), le reste est lu et jeté (le conteneur n'est jamais bloqué) et le fichier `<marque>` est créé.
- `--couper <marque> <max>` : relaie l'entrée (mêmes séparateurs réécrits, sans préfixe), `<max>` octets écrits au plus, puis lit
  et jette le reste et crée `<marque>`. Une sortie fermée (poste parti) ne bloque jamais : l'entrée est vidée jusqu'au bout.
- Messages (`texte_sur`) : contrôles et séparateurs d'un nom refusé écrits sous forme de texte, sur une seule ligne.
"""
import json
import os
import re
import stat
import sys

MAX_FICHIER = 50 * 1024 * 1024           # mêmes limites que outils/tests_instantane.py
MAX_TOTAL = 200 * 1024 * 1024
MAX_FICHIERS = 50000
BLOC = 512
# Chaque membre : un en-tête et au plus 511 octets de bourrage ; fin : deux blocs nuls et le bourrage jusqu'à un
# enregistrement de 10 240 octets (tarfile).
MAX_ARCHIVE = MAX_TOTAL + MAX_FICHIERS * 2 * BLOC + 2 * 10240
MAX_COMMANDE = 4096
REFUS_ARCHIVE = 3                        # code de --archive pour une archive refusée (l'enveloppe rend alors 70)
LIRE = 65536

_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_LECTEUR = re.compile(r"^[A-Za-z]:")
_OCTAL = re.compile(rb"^ *([0-7]{1,12}) *$")


def commande_valide(brut):
    """Vrai si `brut` (octets) est la commande admise par entree-tests.sh."""
    if not isinstance(brut, bytes) or len(brut) > MAX_COMMANDE:
        return False
    try:
        c = json.loads(brut.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    if not (isinstance(c, list) and 1 <= len(c) <= 64 and all(isinstance(x, str) and "\0" not in x for x in c)
            and c[0]):
        return False
    try:                                 # demi-substitut seul (« \ud800 ») : l'entrée du conteneur ne l'encoderait pas
        for x in c:
            x.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def nom_sur(nom):
    """Relatif, segments non vides, ni `.` ni `..`, ni `\\`, ni caractère de contrôle, ni lettre de lecteur."""
    if not nom or nom.startswith("/") or "\\" in nom or _CONTROLE.search(nom) or _LECTEUR.match(nom):
        return False
    return all(s not in ("", ".", "..") for s in nom.split("/"))


def _champ(entete, debut, longueur):
    """Champ texte d'en-tête : jusqu'au premier NUL (comme tar)."""
    return entete[debut:debut + longueur].split(b"\0", 1)[0]


def _octal(champ):
    m = _OCTAL.match(champ.split(b"\0", 1)[0])
    return int(m.group(1), 8) if m else None


def verifier_archive(chemin):
    """None si l'archive est admise, sinon la raison (français)."""
    try:
        if stat.S_ISLNK(os.lstat(chemin).st_mode):     # O_NOFOLLOW n'existe pas partout : le lien est refusé d'abord
            return "archive : lien refusé"
        fd = os.open(chemin, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as e:
        return "archive illisible (%s)" % e.strerror
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            return "archive : pas un fichier ordinaire"
        taille = st.st_size
        if taille > MAX_ARCHIVE:
            return "archive trop grosse (%d octets, %d au plus)" % (taille, MAX_ARCHIVE)
        if taille % BLOC:
            return "archive : taille non multiple de 512"
        noms, dossiers = set(), set()
        total = n = 0
        while True:
            entete = f.read(BLOC)
            if len(entete) < BLOC:
                return "archive tronquée (pas de bloc de fin)"
            if entete == b"\0" * BLOC:
                break
            somme = _octal(entete[148:156])
            calcul = sum(entete[:148]) + 8 * 32 + sum(entete[156:])
            if somme is None or somme != calcul:
                return "en-tête invalide (somme de contrôle) au membre %d" % (n + 1)
            if entete[257:263] != b"ustar\0" or entete[263:265] != b"00":
                return "membre %d hors USTAR (GNU, ancien format ou autre)" % (n + 1)
            if entete[156:157] not in (b"0", b"\0"):
                return "membre %d : type %r refusé (fichiers ordinaires seulement)" % (n + 1, entete[156:157])
            if _champ(entete, 157, 100):
                return "membre %d : nom de lien refusé" % (n + 1)
            mode, t = _octal(entete[100:108]), _octal(entete[124:136])
            if mode is None or mode & ~0o777:
                return "membre %d : droits refusés" % (n + 1)
            if t is None:
                return "membre %d : taille illisible" % (n + 1)
            try:
                nom = _champ(entete, 0, 100).decode("utf-8")
                prefixe = _champ(entete, 345, 155).decode("utf-8")
            except UnicodeDecodeError:
                return "membre %d : nom non UTF-8" % (n + 1)
            if prefixe:
                nom = prefixe + "/" + nom
            if not nom_sur(nom):
                return "nom refusé : %r" % nom[:200]
            n += 1
            if n > MAX_FICHIERS:
                return "trop de fichiers (%d au plus)" % MAX_FICHIERS
            if t > MAX_FICHIER:
                return "fichier trop gros : %s" % nom
            total += t
            if total > MAX_TOTAL:
                return "instantané trop gros (plus de %d octets)" % MAX_TOTAL
            parties = nom.split("/")
            parents = {"/".join(parties[:i]) for i in range(1, len(parties))}
            if nom in noms or nom in dossiers or parents & noms:
                return "nom en double ou fichier et dossier à la fois : %s" % nom
            noms.add(nom)
            dossiers |= parents
            saut = (t + BLOC - 1) // BLOC * BLOC
            if f.tell() + saut > taille:
                return "archive tronquée au membre %s" % nom
            f.seek(saut, os.SEEK_CUR)
        while True:                                     # après le premier bloc nul : des zéros seulement
            reste = f.read(LIRE)
            if not reste:
                return None
            if reste.strip(b"\0"):
                return "données après la fin de l'archive"


def _vider(entree):
    while os.read(entree, LIRE):
        pass


def _marquer(marque):
    try:
        os.close(os.open(marque, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600))
    except OSError:
        pass


def _ecrire(sortie, octets):
    """Écrit tout ; False si la sortie est fermée (le poste est parti)."""
    try:
        while octets:
            octets = octets[os.write(sortie, octets):]
        return True
    except OSError:
        return False


# Séparateurs de lignes autres que \n (str.splitlines, terminaux) : un « \r#fin 0 … » ou « \x0c#fin 0 … » du conteneur ne
# doit jamais commencer une ligne, même pour un lecteur moins strict que le poste. \r et \r\n deviennent \n (la ligne qui
# suit est donc préfixée) ; \x0b, \x0c, \x1c-\x1e et U+0085, U+2028, U+2029 (en UTF-8) sont écrits sous forme de texte
# (« \x0c », «   »). Contrat du poste : la sortie d'erreur se coupe sur b"\n" SEULEMENT, et seule la DERNIÈRE ligne
# (`#fin`) et celle qui la précède (`#refus`) sont crues.
_SEPARATEURS = re.compile(rb"\r\n?|[\x0b\x0c\x1c-\x1e]|\xc2\x85|\xe2\x80[\xa8\xa9]")
_DEBUTS = (b"\xe2\x80", b"\xe2", b"\xc2", b"\r")         # début possible d'un séparateur coupé entre deux blocs


def _remplacer(m):
    s = m.group()
    if s[:1] == b"\r":
        return b"\n"
    if len(s) == 1:
        return b"\\x%02x" % s[0]
    return b"\\u%04x" % ord(s.decode("utf-8"))


class Nettoyeur:
    """Réécrit les séparateurs bloc par bloc ; un séparateur coupé entre deux blocs est gardé pour le bloc suivant."""

    def __init__(self):
        self.reste = b""

    def traiter(self, bloc):
        d, self.reste = self.reste + bloc, b""
        for debut in _DEBUTS:
            if d.endswith(debut):
                d, self.reste = d[:-len(debut)], debut
                break
        return _SEPARATEURS.sub(_remplacer, d)

    def finir(self):
        d, self.reste = self.reste, b""
        return _SEPARATEURS.sub(_remplacer, d)


def _prefixer_texte(propre, debut):
    """(texte avec `| ` au début de chaque ligne, vrai si le texte finit par \n) ; seul \n sépare les lignes ici."""
    morceaux = []
    parties = propre.split(b"\n")
    for i, partie in enumerate(parties):
        dernier = i == len(parties) - 1
        if dernier and not partie:
            break
        if debut:
            morceaux.append(b"| ")
        morceaux.append(partie)
        if dernier:
            debut = False
        else:
            morceaux.append(b"\n")
            debut = True
    return b"".join(morceaux), debut


def _relayer(entree, sortie, marque, maximum, prefixe):
    """Le plafond compte les octets ÉCRITS (après réécriture et préfixe : le flux peut grossir de 3 à 4 fois)."""
    nettoyeur, etat = Nettoyeur(), {"ouverte": True, "debut": True, "ecrits": 0}

    def envoyer(propre):   # vrai si le plafond est atteint
        if prefixe:
            propre, etat["debut"] = _prefixer_texte(propre, etat["debut"])
        coupe = etat["ecrits"] + len(propre) > maximum
        if coupe:
            propre = propre[:maximum - etat["ecrits"]]
            etat["debut"] = propre.endswith(b"\n") if propre else etat["debut"]
        etat["ecrits"] += len(propre)
        if etat["ouverte"] and propre:
            etat["ouverte"] = _ecrire(sortie, propre)
        return coupe

    coupe = False
    while not coupe:
        bloc = os.read(entree, LIRE)
        if not bloc:
            coupe = envoyer(nettoyeur.finir())
            break
        coupe = envoyer(nettoyeur.traiter(bloc))
    if coupe:
        _marquer(marque)
        _vider(entree)
    if prefixe and etat["ouverte"] and not etat["debut"]:
        _ecrire(sortie, b"\n")


def couper(entree, sortie, marque, maximum):
    _relayer(entree, sortie, marque, maximum, False)


def prefixer(entree, sortie, marque, maximum):
    _relayer(entree, sortie, marque, maximum, True)


_TEXTE_DOUTEUX = re.compile("[\x00-\x1f\x7f-\x9f  ]")


def texte_sur(texte):
    """Un message sur UNE ligne : contrôles et séparateurs écrits sous forme de texte (« \\u000a »)."""
    return _TEXTE_DOUTEUX.sub(lambda m: "\\u%04x" % ord(m.group()), texte)


def principal(argv):
    if argv[:1] == ["--commande"] and len(argv) == 1:
        brut = sys.stdin.buffer.read(MAX_COMMANDE + 1)
        if commande_valide(brut):
            return 0
        sys.stderr.write("commande refusée : un tableau JSON de 1 à 64 chaînes (4 Ko au plus) est attendu.\n")
        return 2
    if argv[:1] == ["--archive"] and len(argv) == 2:
        raison = verifier_archive(argv[1])
        if raison is None:
            return 0
        sys.stderr.write("instantané refusé : %s\n" % texte_sur(raison))
        return REFUS_ARCHIVE                # 3 : refus explicite ; un plantage de python rend 1, jamais 3
    if argv[:1] in (["--prefixer"], ["--couper"]) and len(argv) == 3 and re.match(r"^[1-9][0-9]{0,9}$", argv[2]):
        relais = prefixer if argv[0] == "--prefixer" else couper
        relais(sys.stdin.fileno(), sys.stdout.fileno(), argv[1], int(argv[2]))
        return 0
    sys.stderr.write("usage : tests_hote.py --commande | --archive <tar> | --prefixer|--couper <marque> <max>\n")
    return 2


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
