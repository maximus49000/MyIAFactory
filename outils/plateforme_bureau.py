"""Étape facultative « session graphique » de la plateforme : mot de passe de session et envoi à l'étape distante.

Le mot de passe vit dans `<dossier>/bureau-distant.txt` (UTF-8, réservé à l'utilisateur) et nulle part ailleurs : il est
envoyé par l'entrée standard SSH, ajouté aux secrets masqués AVANT tout envoi, jamais écrit dans le cache, l'état ni les journaux.
"""
import getpass
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import plateforme_ssh

FICHIER_RDP = "bureau-distant.rdp"
PORT_LOCAL = 33890
PORT_XRDP = 3389
UTILISATEUR_DISTANT = "ubuntu"
FICHIER_MDP = "bureau-distant.txt"
LONGUEUR_MDP = 24
LONGUEUR_MIN = 16
ALPHABET = "".join(c for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0Oo1lI")


def _restreindre_windows(chemin):
    """Au mieux : retire les droits hérités et ne laisse que l'utilisateur courant (sans effet hors Windows)."""
    if sys.platform != "win32":
        return
    try:
        subprocess.run(["icacls", str(chemin), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:F"],
                       capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


AVIS_COURT = f"Mot de passe trop court dans {FICHIER_MDP} : remplacé par un mot de passe généré."


class ErreurFichierMdp(OSError):
    """Le fichier du mot de passe existe mais n'est pas du texte UTF-8 : jamais écrasé."""


def _ecrire_atomique(chemin, mdp):
    """Temporaire créé en 0600 (O_EXCL) dans le même dossier, écrit puis `os.replace` : jamais de fichier tronqué."""
    tmp = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
    try:
        tmp.unlink()
    except OSError:
        pass
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    try:
        _restreindre_windows(tmp)        # avant d'y écrire le secret
        with os.fdopen(fd, "wb") as f:
            f.write((mdp + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, chemin)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _lire_ou_generer(dossier):
    """(mot de passe, avis) ; l'avis est non vide quand un fichier trop court a été remplacé. Un fichier présent mais
    inaccessible lève OSError : il n'est jamais écrasé à l'aveugle."""
    chemin = Path(dossier) / FICHIER_MDP
    avis = ""
    try:
        octets = chemin.read_bytes()
    except FileNotFoundError:
        octets = None
    if octets is not None:       # tout autre échec de lecture (OSError) remonte : jamais d'écrasement
        try:
            if octets[:2] in (b"\xff\xfe", b"\xfe\xff"):
                raise UnicodeError("UTF-16")
            premiere = (octets.decode("utf-8-sig").splitlines() or [""])[0].strip()
        except UnicodeError:
            raise ErreurFichierMdp(f"{chemin} n'est pas lisible comme du texte UTF-8") from None
        if len(premiere) >= LONGUEUR_MIN:
            return premiere, ""
        avis = AVIS_COURT
    for vieux in Path(dossier).glob(f".{FICHIER_MDP}.*.tmp"):     # temporaires de runs morts : ils contiennent le mot de passe
        try:
            vieux.unlink()
        except OSError:
            pass
    mdp ="".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_MDP))
    Path(dossier).mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(chemin, mdp)
    return mdp, avis


def mot_de_passe(dossier):
    """Relit le mot de passe de session (1re ligne, 16 caractères au moins) ou en génère un et l'écrit."""
    return _lire_ou_generer(dossier)[0]


def etape_bureau_distant(c, lancer_etape):
    """Envoie le mot de passe par stdin à l'étape distante `bureau_distant` ; renvoie son rapport."""
    try:
        mdp, avis = _lire_ou_generer(c.dossier)
    except ErreurFichierMdp:
        chemin = Path(c.dossier) / FICHIER_MDP
        return {"statut": "bloque", "detail": f"{FICHIER_MDP} n'est pas lisible comme du texte UTF-8 (fichier enregistré en UTF-16 ?).",
                "geste": f"Réenregistrez {chemin} en UTF-8 (avec PowerShell 5, utilisez -Encoding utf8) ou supprimez-le pour "
                         "qu'un nouveau mot de passe soit généré, puis relancez."}
    except OSError as e:
        return {"statut": "bloque", "detail": f"Mot de passe de session illisible ou impossible à écrire ({type(e).__name__}).",
                "geste": f"Vérifiez les droits de {Path(c.dossier) / FICHIER_MDP}, puis relancez."}
    if mdp not in c.secrets:
        c.secrets.append(mdp)        # masqué partout AVANT le premier envoi
    r = lancer_etape(c, "bureau_distant", stdin=mdp + "\n")
    if avis:
        r["detail"] = f"{avis} {r.get('detail', '')}".strip()
    if r["statut"] == "fait":
        r["geste"] = (f"Lancez py -3.12 lancer.py plateforme bureau-distant pour ouvrir la session ; "
                      f"le mot de passe est dans {Path(c.dossier) / FICHIER_MDP}.")
    return r


def _windows():
    return sys.platform == "win32"


def _port_libre(prefere=PORT_LOCAL):
    """`prefere` s'il est libre sur 127.0.0.1, sinon un port libre choisi par le système."""
    for port in (prefere, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise OSError("aucun port local libre")


ATTENTE_TUNNEL_S = 25      # plus long que ConnectTimeout=20 du tunnel : une connexion lente n'est pas prise pour un échec


def _attendre_port(port, proc, delai=ATTENTE_TUNNEL_S, connecter=socket.create_connection, dormir=time.sleep, horloge=time.monotonic):
    """Vrai si 127.0.0.1:<port> accepte une connexion ET que ssh tourne encore (avant et après une courte confirmation) :
    un port pris par un autre processus pendant que ssh sort ne doit pas être pris pour le tunnel."""
    fin = horloge() + delai
    while horloge() < fin:
        if proc.poll() is not None:
            return False
        try:
            with connecter(("127.0.0.1", port), timeout=1):
                pass
        except OSError:
            dormir(0.3)
            continue
        dormir(0.5)
        return proc.poll() is None
    return False


def _ouvrir_erreurs(dossier):
    """Fichier temporaire (0600) qui reçoit la sortie d'erreur du tunnel : jamais un tube qui peut se remplir."""
    chemin = Path(dossier) / f".{FICHIER_RDP}.{os.getpid()}.err"
    try:
        chemin.unlink()
    except OSError:
        pass
    fd = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    return chemin, os.fdopen(fd, "wb")


def _echec_tunnel(chemin, ip):
    """Message français précis, construit après la sortie de ssh ; jamais la sortie brute."""
    try:
        erreur = chemin.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        erreur = ""
    if plateforme_ssh.CHANGEMENT_CLE in erreur:
        return (f"L'empreinte du serveur a changé : le tunnel est refusé par sécurité. Si le serveur a bien été réinstallé, "
                f"exécutez ssh-keygen -R {ip} puis relancez ; sinon, ne continuez pas.")
    return ("Le tunnel SSH ne s'est pas ouvert (serveur injoignable, clé refusée ou port local pris). "
            "Lancez py -3.12 lancer.py plateforme verifier pour le détail.")


def _arreter(proc):
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except OSError:
        pass


def _ecrire_rdp(dossier, port):
    chemin = Path(dossier) / FICHIER_RDP
    chemin.write_text(f"full address:s:127.0.0.1:{port}\r\nusername:s:{UTILISATEUR_DISTANT}\r\n"
                      "prompt for credentials:i:1\r\n", encoding="utf-8")
    return chemin


def ouvrir(dossier, popen=subprocess.Popen, lancer_rdp=subprocess.run, port_libre=_port_libre,
           attendre_port=_attendre_port, ssh_options=plateforme_ssh._options):
    """Ouvre la session graphique : tunnel SSH (127.0.0.1 seulement) puis Bureau à distance de Windows. Code 0/1/2."""
    import plateforme    # import tardif : plateforme importe ce module
    dossier = Path(dossier)
    cache = plateforme._lire_cache(dossier)
    etapes = ((cache.get("etat") or {}).get("etapes") or [])
    etape = next((e for e in etapes if isinstance(e, dict) and e.get("id") == "bureau_distant"), {})
    ip = cache.get("ip")
    if etape.get("statut") != "fait" or not ip:
        print("Installez d'abord la session : lancer.py plateforme installer --bureau-distant", file=sys.stderr)
        return 1
    if not _windows():
        print("Le client « mstsc » (Bureau à distance) n'existe que sous Windows : la session ne peut pas s'ouvrir d'ici.",
              file=sys.stderr)
        return 2
    if not isinstance(ip, str) or any(ch.isspace() or ch == "@" for ch in ip):
        print("Adresse du serveur invalide dans le cache : relancez lancer.py plateforme installer.", file=sys.stderr)
        return 1
    try:
        plateforme_ssh._verifier_hote(ip)
    except ValueError:
        print("Adresse du serveur invalide dans le cache : relancez lancer.py plateforme installer.", file=sys.stderr)
        return 1
    hote = f"{UTILISATEUR_DISTANT}@{ip}"
    erreurs, fichier_err = None, None
    try:
        port = port_libre()
        args = ["ssh", "-N", "-L", f"127.0.0.1:{port}:127.0.0.1:{PORT_XRDP}", *ssh_options(dossier / plateforme_ssh.NOM_CLE),
                "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=20",
                "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "--", hote]
        erreurs, fichier_err = _ouvrir_erreurs(dossier)
        proc = popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=fichier_err)
        fichier_err.close()
    except FileNotFoundError:
        _nettoyer(erreurs, fichier_err)
        print("« ssh » est introuvable : le client OpenSSH de Windows est requis "
              "(Paramètres > Applications > Fonctionnalités facultatives > Client OpenSSH).", file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        _nettoyer(erreurs, fichier_err)
        print(f"Tunnel impossible à lancer : {type(e).__name__}.", file=sys.stderr)
        return 1
    try:
        if not attendre_port(port, proc):
            _arreter(proc)       # la sortie d'erreur n'est lue qu'une fois ssh terminé
            print(_echec_tunnel(erreurs, ip), file=sys.stderr)
            return 1
        fichier = _ecrire_rdp(dossier, port)
        print(f"Ouverture de la session graphique (mot de passe dans {dossier / FICHIER_MDP}).")
        try:
            lancer_rdp(["mstsc", str(fichier)])
        except FileNotFoundError:       # seulement ici : une autre FileNotFoundError n'est pas « mstsc introuvable »
            print("mstsc introuvable (Bureau à distance de Windows).", file=sys.stderr)
            return 2
        return 0
    except KeyboardInterrupt:
        print("Interrompu : le tunnel est fermé.", file=sys.stderr)
        return 1
    except Exception as e:      # jamais de trace de pile : un message clair
        print(f"La session n'a pas pu s'ouvrir ({type(e).__name__}).", file=sys.stderr)
        return 1
    finally:
        _arreter(proc)
        _nettoyer(erreurs, None)


def _nettoyer(chemin, fichier):
    for f in (fichier,):
        try:
            if f is not None:
                f.close()
        except OSError:
            pass
    try:
        if chemin is not None:
            chemin.unlink()
    except OSError:
        pass
