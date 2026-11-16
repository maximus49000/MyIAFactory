"""La lecture des petits fichiers d'état (suivi, fiches), gardée en mémoire tant que le fichier ne change pas.

Sous Windows, ouvrir un fichier coûte environ une milliseconde (l'antivirus le contrôle à chaque ouverture) ; le
moteur et l'outil relisent les mêmes fichiers des milliers de fois (mesure : 5 040 lectures du suivi et 9 636 de fiches
pour 54 tests, un tiers de leur durée). Un `stat` suffit à savoir si le fichier a changé : la clé porte son numéro de
fichier (une écriture par `os.replace` crée un nouveau fichier), sa date au 100 ns et sa taille. Seul le texte est
gardé : chaque appelant analyse le sien, et ne partage donc aucun objet modifiable.
"""
import os

_TEXTES = {}
_MAX = 512


def texte(chemin, encoding="utf-8-sig"):
    """Le texte du fichier, comme `Path.read_text(encoding=...)` (mêmes erreurs : `OSError`, `UnicodeDecodeError`)."""
    st = os.stat(chemin)
    cle = (os.path.abspath(chemin), encoding)
    marque = (st.st_ino, st.st_mtime_ns, st.st_size)
    garde = _TEXTES.get(cle)
    if garde is not None and garde[0] == marque:
        return garde[1]
    with open(chemin, encoding=encoding) as f:
        contenu = f.read()
    if len(_TEXTES) >= _MAX:
        _TEXTES.clear()
    _TEXTES[cle] = (marque, contenu)
    return contenu
