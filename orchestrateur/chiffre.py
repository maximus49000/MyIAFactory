"""Le chiffrement des connaissances partagées, avec la seule bibliothèque standard.

Une clé de 32 octets (en hexadécimal dans le fichier de clé). Le flux de chiffrement est HMAC-SHA256 en mode compteur
(clé dérivée « chiffrement », un aléa de 16 octets par message), puis un sceau HMAC-SHA256 sur version, aléa et texte
chiffré (clé dérivée « integrite ») : chiffrer puis sceller. Un jeton est `v1.<base64url>` ; il tient sur une ligne.
"""
import base64
import hashlib
import hmac
import secrets

VERSION = b"v1"
PREFIXE = "v1."
TAILLE_CLE = 32
_ALEA = 16
_SCEAU = 32


class CleInvalide(ValueError):
    pass


class JetonInvalide(ValueError):
    """Le jeton est abîmé ou chiffré avec une autre clé."""


def nouvelle_cle():
    return secrets.token_hex(TAILLE_CLE)


def lire_cle(texte):
    """Les octets d'une clé écrite en hexadécimal (espaces et retours ignorés)."""
    try:
        cle = bytes.fromhex("".join(str(texte or "").split()))
    except ValueError:
        raise CleInvalide("La clé des connaissances n'est pas en hexadécimal.")
    if len(cle) != TAILLE_CLE:
        raise CleInvalide(f"La clé des connaissances doit faire {TAILLE_CLE} octets.")
    return cle


def _derivee(cle, usage):
    return hmac.new(cle, b"myiafactory-connaissances:" + usage, hashlib.sha256).digest()


def _flux(cle_chiffrement, alea, longueur):
    blocs, n = [], 0
    while 32 * n < longueur:
        blocs.append(hmac.new(cle_chiffrement, alea + n.to_bytes(8, "big"), hashlib.sha256).digest())
        n += 1
    return b"".join(blocs)[:longueur]


def chiffrer(cle, texte):
    """Le jeton d'un texte (UTF-8). `cle` : les octets rendus par `lire_cle`."""
    clair = str(texte).encode("utf-8")
    alea = secrets.token_bytes(_ALEA)
    chiffre = bytes(a ^ b for a, b in zip(clair, _flux(_derivee(cle, b"chiffrement"), alea, len(clair))))
    sceau = hmac.new(_derivee(cle, b"integrite"), VERSION + alea + chiffre, hashlib.sha256).digest()
    return PREFIXE + base64.urlsafe_b64encode(alea + chiffre + sceau).decode("ascii").rstrip("=")


def dechiffrer(cle, jeton):
    """Le texte d'un jeton ; `JetonInvalide` s'il est abîmé ou d'une autre clé (jamais un texte faux)."""
    jeton = str(jeton or "").strip()
    if not jeton.startswith(PREFIXE):
        raise JetonInvalide("Jeton de connaissance d'une version inconnue.")
    corps = jeton[len(PREFIXE):]
    try:
        brut = base64.urlsafe_b64decode(corps + "=" * (-len(corps) % 4))
    except (ValueError, TypeError):
        raise JetonInvalide("Jeton de connaissance illisible.")
    if len(brut) < _ALEA + _SCEAU:
        raise JetonInvalide("Jeton de connaissance trop court.")
    alea, chiffre, sceau = brut[:_ALEA], brut[_ALEA:-_SCEAU], brut[-_SCEAU:]
    attendu = hmac.new(_derivee(cle, b"integrite"), VERSION + alea + chiffre, hashlib.sha256).digest()
    if not hmac.compare_digest(sceau, attendu):
        raise JetonInvalide("Jeton de connaissance abîmé ou chiffré avec une autre clé.")
    clair = bytes(a ^ b for a, b in zip(chiffre, _flux(_derivee(cle, b"chiffrement"), alea, len(chiffre))))
    return clair.decode("utf-8")
