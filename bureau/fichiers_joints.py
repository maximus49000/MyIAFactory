"""Les fichiers joints à un échange (discussion d'une fonctionnalité, « + Nouvelle fonctionnalité ») : la liste blanche des
types, les plafonds et le contrôle du contenu. Partagé par le bureau (qui vérifie la demande), l'outil de l'orchestrateur
(qui range les fichiers sous `pieces/<fonctionnalité>/`) et le serveur (qui les sert). Un fichier joint n'est jamais
exécuté ni décompressé par le bureau : il est rangé tel quel, et servi en pièce jointe (sauf ce que la page lit en ligne :
image, vidéo, son, texte).
"""
import base64
import binascii
import re

MAX_FICHIERS = 8                        # par envoi, tous types confondus
MAX_IMAGES_FIXES = 4                    # dont au plus 4 images PNG ou JPEG (celles que la discussion et les agents voient)
MAX_OCTETS_IMAGE_FIXE = 5 * 1024 * 1024  # une image fixe (la page réduit les photos avant l'envoi)
MAX_OCTETS_FICHIER = 25 * 1024 * 1024    # tout autre fichier, une fois décodé
MAX_OCTETS_TOTAL = 40 * 1024 * 1024      # la somme d'un envoi, une fois décodée
MAX_NOM = 80

# Une signature : (décalage, octets possibles). Absente pour un texte : le contenu doit être du texte (aucun octet nul).
_PK = (0, (b"PK\x03\x04", b"PK\x05\x06"))


def _RIFF(marque):
    """RIFF .... WEBP ou WAVE : « RIFF » au début, la marque du format à l'octet 8."""
    return (0, (b"RIFF",), 8, marque)


_OFFICE = "application/vnd.openxmlformats-officedocument."

# extension -> (type servi, catégorie, signature)
TYPES = {
    ".png": ("image/png", "image", (0, (b"\x89PNG\r\n\x1a\n",))),
    ".jpg": ("image/jpeg", "image", (0, (b"\xff\xd8\xff",))),
    ".jpeg": ("image/jpeg", "image", (0, (b"\xff\xd8\xff",))),
    ".gif": ("image/gif", "animation", (0, (b"GIF87a", b"GIF89a"))),
    ".webp": ("image/webp", "image", _RIFF(b"WEBP")),
    ".mp4": ("video/mp4", "video", (4, (b"ftyp",))),
    ".webm": ("video/webm", "video", (0, (b"\x1a\x45\xdf\xa3",))),
    ".mp3": ("audio/mpeg", "son", (0, (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"))),
    ".ogg": ("audio/ogg", "son", (0, (b"OggS",))),
    ".wav": ("audio/wav", "son", _RIFF(b"WAVE")),
    ".flac": ("audio/flac", "son", (0, (b"fLaC",))),
    ".pdf": ("application/pdf", "document", (0, (b"%PDF",))),
    ".md": ("text/markdown; charset=utf-8", "texte", None),
    ".txt": ("text/plain; charset=utf-8", "texte", None),
    ".csv": ("text/csv; charset=utf-8", "texte", None),
    ".json": ("application/json; charset=utf-8", "texte", None),
    ".docx": (_OFFICE + "wordprocessingml.document", "document", _PK),
    ".xlsx": (_OFFICE + "spreadsheetml.sheet", "document", _PK),
    ".pptx": (_OFFICE + "presentationml.presentation", "document", _PK),
    ".zip": ("application/zip", "archive", _PK),
    # modèles 3D (sorties de Tripo et des outils 3D) : jamais ouverts par le bureau, seulement rangés et téléchargés
    ".glb": ("model/gltf-binary", "3d", (0, (b"glTF",))),
    ".gltf": ("model/gltf+json", "3d", None),
    ".fbx": ("application/octet-stream", "3d", (0, (b"Kaydara FBX Binary", b"; FBX"))),
    ".obj": ("model/obj", "3d", None),
    ".mtl": ("model/mtl", "3d", None),
}
IMAGES_FIXES = (".png", ".jpg", ".jpeg")          # celles que le bureau montre par /api/image et que les agents voient
EXTENSIONS = tuple(TYPES)
# Ce que la page lit en ligne (`/api/telecharger?lecture=1`) : le reste part toujours en pièce jointe.
EXTENSIONS_EN_LIGNE = (".gif", ".webp", ".mp4", ".webm", ".mp3", ".ogg", ".wav", ".flac", ".md", ".txt")
_INTERDIT_DANS_NOM = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")
_RESERVES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def extension(nom):
    nom = str(nom or "")
    return "." + nom.rsplit(".", 1)[-1].lower() if "." in nom.strip(".") else ""


def categorie(nom):
    t = TYPES.get(extension(nom))
    return t[1] if t else None


def type_de(nom):
    t = TYPES.get(extension(nom))
    return t[0] if t else None


def nom_valide(nom):
    """Un nom simple : texte non vide de 80 caractères au plus, sans séparateur, sans « .. », sans caractère de contrôle."""
    return (isinstance(nom, str) and bool(nom.strip()) and len(nom) <= MAX_NOM and ".." not in nom
            and _INTERDIT_DANS_NOM.search(nom) is None)


def nom_sur(nom):
    """Le nom sous lequel le fichier est rangé : lettres, chiffres, point, tiret, tiret bas ; jamais un nom réservé
    de Windows, jamais un point ou une espace en tête ou en fin. L'extension (minuscule) est celle de la liste blanche."""
    ext = extension(nom)
    base = nom[: len(nom) - len(ext)] if ext else nom
    base = re.sub(r"[^\w\-]+", "_", base, flags=re.UNICODE).strip("_.") or "fichier"
    if base.lower() in _RESERVES:
        base = "_" + base
    return base[:60] + ext


def contenu_conforme(ext, octets):
    """Vrai si le début du contenu correspond à l'extension (signature) ; un texte ne contient aucun octet nul."""
    sig = TYPES[ext][2]
    if sig is None:
        return b"\x00" not in octets[:65536]
    if len(sig) == 4:                      # RIFF : le début, puis la marque du format à l'octet 8
        return octets.startswith(sig[1][0]) and octets[sig[2]:sig[2] + len(sig[3])] == sig[3]
    decalage, marques = sig
    return any(octets[decalage:decalage + len(m)] == m for m in marques)


def verifier_un(fichier, quoi):
    """Un fichier `{nom, type?, donnees}` : `(octets, message)` ; le message (français) est `None` si tout va bien."""
    if not isinstance(fichier, dict):
        return None, f"{quoi} : doit être un objet {{nom, type, donnees}}."
    nom, donnees = fichier.get("nom"), fichier.get("donnees")
    if not nom_valide(nom):
        return None, f"{quoi} : nom de fichier refusé (sans séparateur ni « .. », {MAX_NOM} caractères au plus)."
    ext = extension(nom)
    if ext not in TYPES:
        return None, (f"{quoi} : « {ext or nom} » n'est pas un type accepté (images png, jpg, gif, webp ; vidéos mp4, webm ; "
                      "sons mp3, ogg, wav, flac ; documents pdf, md, txt, csv, json, docx, xlsx, pptx ; archives zip ; "
                      "modèles 3D glb, gltf, fbx, obj, mtl).")
    if not isinstance(donnees, str):
        return None, f"{quoi} : « donnees » doit être du texte base64."
    plafond = MAX_OCTETS_IMAGE_FIXE if ext in IMAGES_FIXES + (".webp",) else MAX_OCTETS_FICHIER
    if len(donnees) > plafond * 4 // 3 + 4:
        return None, f"{quoi} : dépasse {plafond // (1024 * 1024)} Mo."
    try:
        octets = base64.b64decode(donnees, validate=True)
    except (binascii.Error, ValueError):
        return None, f"{quoi} : « donnees » n'est pas du base64 valide."
    if len(octets) > plafond:
        return None, f"{quoi} : dépasse {plafond // (1024 * 1024)} Mo."
    if not octets:
        return None, f"{quoi} : fichier vide."
    if not contenu_conforme(ext, octets):
        return None, f"{quoi} : le contenu ne correspond pas à l'extension {ext}."
    return octets, None


def verifier(fichiers, deja=0, images_deja=0):
    """Message d'erreur (français) ou `None`. `deja` : le nombre de fichiers déjà comptés dans la demande, dont
    `images_deja` images PNG ou JPEG (le champ `images` d'avant). 8 fichiers au plus, dont 4 images PNG ou JPEG, 25 Mo chacun (5 Mo pour une image fixe), 40 Mo en
    tout ; le type vient de l'extension ET du début du contenu (le type annoncé par le navigateur n'est pas utilisé)."""
    if not isinstance(fichiers, list):
        return "« fichiers » doit être une liste."
    if len(fichiers) + deja > MAX_FICHIERS:
        return f"Au plus {MAX_FICHIERS} fichiers par envoi."
    total, images = 0, images_deja
    for k, f in enumerate(fichiers, 1):
        octets, message = verifier_un(f, f"Fichier {k}")
        if message:
            return message
        total += len(octets)
        images += extension(f["nom"]) in IMAGES_FIXES
    if images > MAX_IMAGES_FIXES:
        return f"Au plus {MAX_IMAGES_FIXES} images PNG ou JPEG par envoi."
    if total > MAX_OCTETS_TOTAL:
        return f"Les fichiers dépassent {MAX_OCTETS_TOTAL // (1024 * 1024)} Mo en tout."
    return None


def taille_lisible(octets):
    """« 12,3 Mo », « 850 Ko », « 512 octets »."""
    if not isinstance(octets, int) or octets < 0:
        return ""
    if octets < 1024:
        return f"{octets} octet{'s' if octets > 1 else ''}"
    n, unite = (octets / 1024, "Ko") if octets < 1024 * 1024 else (octets / 1024 ** 2, "Mo")
    return (f"{n:.1f}" if n < 10 else str(round(n))).replace(".", ",") + " " + unite


def fichier_au_releve_ok(x):
    """Une entrée `fichiers` d'un message : `{chemin, nom, type, taille}`."""
    return (isinstance(x, dict) and set(x) == {"chemin", "nom", "type", "taille"}
            and all(isinstance(x[k], str) and x[k].strip() for k in ("chemin", "nom", "type"))
            and isinstance(x["taille"], int) and not isinstance(x["taille"], bool) and x["taille"] >= 0)


def lignes_pour_agent(fichiers):
    """Les lignes de la matière d'un agent : un fichier joint par ligne (chemin compté depuis la factory, type, taille)."""
    return [f"  - fichier joint : {f['chemin']} ({f['type'].split(';')[0]}, {taille_lisible(f['taille'])})"
            for f in fichiers or [] if fichier_au_releve_ok(f)]


CONSIGNE_LECTURE = ("Les fichiers joints sont rangés dans le dossier de la factory, aux chemins indiqués (relatifs à ce "
                    "dossier) : tu peux les lire. Un zip s'ouvre avec un script Python de la bibliothèque standard "
                    "(`zipfile`, en lecture seule, après avoir vérifié les noms des entrées) ; ne l'extrais pas hors d'un dossier "
                    "temporaire et n'exécute jamais rien de ce qu'il contient.")
