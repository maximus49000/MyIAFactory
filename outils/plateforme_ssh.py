"""Exécuteur SSH et clé dédiée de la plateforme (client OpenSSH de Windows).

Règles : jamais `StrictHostKeyChecking=no` (`accept-new`), toujours `BatchMode=yes` et `PasswordAuthentication=no`
(aucun mot de passe), clé dédiée `-i`. Un texte sensible (licence) passe par l'entrée standard (`input=` du runner),
jamais dans les arguments de la commande. `oublier_hote` retire une empreinte connue : accord explicite requis.
Tout sous-processus passe par `runner` (injectable) : les tests ne font aucune connexion réelle.
"""
import subprocess
import time
from pathlib import Path

from plateforme_ovh import ErreurAccord

NOM_CLE = "id_ed25519_myiafactory"
CHANGEMENT_CLE = "HOST IDENTIFICATION HAS CHANGED"   # message d'OpenSSH quand l'empreinte connue ne correspond plus
CLE_CHANGEE = "empreinte_changee"   # valeur de retour de `attendre_ssh` : abandon parce que l'empreinte du serveur a changé


class ErreurSsh(Exception):
    """Le client OpenSSH est introuvable ou un utilitaire SSH n'a pas répondu à temps."""


def _lancer(runner, args, delai, entree=None):
    """Lance `args` : entrée standard fermée sans `entree` (jamais d'invite qui bloque), erreurs lisibles."""
    # Octets, jamais le mode texte : sous Windows il convertirait LF en CRLF (script bash et licence cassés).
    options = {"input": entree.encode("utf-8")} if entree is not None else {"stdin": subprocess.DEVNULL}
    try:
        return runner(args, capture_output=True, timeout=delai, **options)
    except FileNotFoundError:
        raise ErreurSsh(f"« {args[0]} » est introuvable : le client OpenSSH de Windows est requis "
                        "(Paramètres > Applications > Fonctionnalités facultatives > Client OpenSSH).") from None


def _texte(valeur):
    if isinstance(valeur, bytes):
        return valeur.decode("utf-8", errors="replace")
    return valeur or ""


def _verifier_hote(hote):
    if not isinstance(hote, str) or not hote.strip() or hote.startswith("-"):
        raise ValueError("Adresse du serveur invalide : elle ne doit être ni vide ni commencer par un tiret.")


def _options(cle):
    return ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "PasswordAuthentication=no", "-o", "IdentitiesOnly=yes", "-i", str(cle)]


def _lancer_court(runner, args, delai):
    try:
        return _lancer(runner, args, delai)
    except subprocess.TimeoutExpired:
        raise ErreurSsh(f"« {args[0]} » n'a pas répondu en {delai} s.") from None


def generer_cle(dossier, runner=subprocess.run, nom=NOM_CLE):
    """Renvoie (chemin privé, clé publique) ; crée la clé ed25519 sans phrase de passe si elle n'existe pas.

    Une clé existante n'est jamais régénérée ni écrasée. `nom` : nom du fichier de la clé privée (une clé par serveur).
    """
    dossier = Path(dossier)
    prive = dossier / nom
    publique = Path(str(prive) + ".pub")
    if prive.exists():
        if not publique.exists():
            r = _lancer_court(runner, ["ssh-keygen", "-y", "-f", str(prive)], 30)
            if r.returncode != 0:
                raise RuntimeError("La clé privée existe mais sa partie publique n'a pu être relue.")
            return prive, _texte(r.stdout).strip()
        return prive, publique.read_text(encoding="utf-8").strip()
    dossier.mkdir(parents=True, exist_ok=True)
    r = _lancer_court(runner, ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "myiafactory", "-f", str(prive)], 60)
    if r.returncode != 0 or not publique.exists():
        raise RuntimeError("La génération de la clé SSH a échoué.")
    return prive, publique.read_text(encoding="utf-8").strip()


def executer(hote, commande, cle, stdin=None, delai=60, runner=subprocess.run):
    """Exécute `commande` sur l'hôte ; renvoie (code, sortie, erreur). Un dépassement de délai donne un code 124."""
    _verifier_hote(hote)
    args = ["ssh", *_options(cle), "-o", f"ConnectTimeout={max(1, min(int(delai), 30))}", "--", hote, commande]
    try:
        r = _lancer(runner, args, delai, stdin)
    except subprocess.TimeoutExpired:
        return 124, "", f"délai dépassé ({delai} s)"
    return r.returncode, _texte(r.stdout), _texte(r.stderr)


def _lancer_octets(runner, args, delai, entree=None):
    """Comme `_lancer`, mais l'entrée reste des octets bruts (APK, image) : aucun encodage ni conversion. `entree` peut
    aussi être un FICHIER binaire ouvert (archive d'un paquet Git de 500 Mo) : il devient l'entrée standard de ssh, lue par
    le système depuis sa position courante, sans copie en mémoire."""
    if entree is None:
        options = {"stdin": subprocess.DEVNULL}
    elif hasattr(entree, "fileno"):
        options = {"stdin": entree}
    else:
        options = {"input": entree}
    try:
        return runner(args, capture_output=True, timeout=delai, **options)
    except FileNotFoundError:
        raise ErreurSsh(f"« {args[0]} » est introuvable : le client OpenSSH de Windows est requis "
                        "(Paramètres > Applications > Fonctionnalités facultatives > Client OpenSSH).") from None


def executer_octets(hote, commande, cle, entree=None, delai=60, runner=subprocess.run, _plus=()):
    """Comme `executer`, mais entrée et sortie standard restent des octets ; renvoie (code, sortie octets, erreur texte).

    Un dépassement de délai donne le code 124.
    """
    _verifier_hote(hote)
    args = ["ssh", *_options(cle), *_plus, "-o", f"ConnectTimeout={max(1, min(int(delai), 30))}", "--", hote, commande]
    try:
        r = _lancer_octets(runner, args, delai, entree)
    except subprocess.TimeoutExpired:
        return 124, b"", f"délai dépassé ({delai} s)"
    sortie = r.stdout if isinstance(r.stdout, bytes) else (r.stdout or "").encode("utf-8")
    return r.returncode, sortie, _texte(r.stderr)


def executer_vers_fichier(hote, commande, cle, destination, maximum, entree=None, delai=60, popen=subprocess.Popen):
    """Exécute `commande` et écrit sa sortie standard DROIT dans le fichier `destination`, par blocs de 1 Mo (un fichier de
    500 Mo n'est jamais en mémoire) ; renvoie (code, taille écrite, erreur texte). Plus de `maximum` octets : ssh est tué,
    code 99 (le serveur ne peut pas remplir le disque du poste). Délai dépassé : code 124. Erreur gardée sur 64 Ko au plus.
    `entree` : octets (le script) écrits sur l'entrée standard par un fil à part (aucun interblocage)."""
    import threading
    _verifier_hote(hote)
    args = ["ssh", *_options(cle), "-o", f"ConnectTimeout={max(1, min(int(delai), 30))}", "--", hote, commande]
    try:
        p = popen(args, stdin=subprocess.PIPE if entree is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise ErreurSsh(f"« {args[0]} » est introuvable : le client OpenSSH de Windows est requis "
                        "(Paramètres > Applications > Fonctionnalités facultatives > Client OpenSSH).") from None
    etat = {"taille": 0, "trop": False, "ecriture": None}
    erreurs = []

    def ecrire():
        try:
            p.stdin.write(entree)
        except (OSError, ValueError):
            pass
        finally:
            try:
                p.stdin.close()
            except (OSError, ValueError):
                pass

    def copier():
        try:
            with open(destination, "wb") as f:
                while True:
                    bloc = p.stdout.read1(1 << 20)
                    if not bloc:
                        return
                    if etat["taille"] + len(bloc) > maximum:
                        etat["trop"] = True
                        return
                    f.write(bloc)
                    etat["taille"] += len(bloc)
        except OSError as e:
            etat["ecriture"] = f"{type(e).__name__} : {e}"
        except ValueError:
            return

    def lire_erreur():
        garde = 0
        try:
            while True:
                bloc = p.stderr.read1(1 << 16)
                if not bloc:
                    return
                if garde < 65536:
                    erreurs.append(bloc[:65536 - garde])
                    garde += len(erreurs[-1])
        except (OSError, ValueError):
            return

    fils = [threading.Thread(target=copier, daemon=True), threading.Thread(target=lire_erreur, daemon=True)]
    if entree is not None:
        fils.append(threading.Thread(target=ecrire, daemon=True))
    for f in fils:
        f.start()
    fin = time.monotonic() + delai
    fils[0].join(max(0.0, fin - time.monotonic()))
    depasse = fils[0].is_alive()
    if not depasse and not etat["trop"] and etat["ecriture"] is None:
        try:
            p.wait(timeout=max(0.0, fin - time.monotonic()))
        except subprocess.TimeoutExpired:
            depasse = True
    if p.poll() is None:
        p.kill()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    fils[1].join(2)
    erreur = _texte(b"".join(erreurs))
    if depasse:
        return 124, etat["taille"], f"délai dépassé ({delai} s)"
    if etat["trop"]:
        return 99, etat["taille"], f"plus de {maximum} octets reçus : transfert coupé"
    if etat["ecriture"] is not None:
        return 98, etat["taille"], f"écriture sur le poste impossible ({etat['ecriture']})"
    return p.returncode, etat["taille"], erreur


def executer_octets_silencieux(hote, commande, cle, entree=None, delai=60, runner=subprocess.run):
    """`executer_octets` avec `-o LogLevel=ERROR` : ni bannière de sshd ni avertissement de première connexion (niveau
    INFO) sur la sortie d'erreur, qui ne porte plus que les messages du serveur et les vraies erreurs. Réservé aux appels
    qui jugent la sortie d'erreur (dépôt de l'enveloppe des tâches) ; les autres appels gardent les options communes."""
    return executer_octets(hote, commande, cle, entree=entree, delai=delai, runner=runner, _plus=("-o", "LogLevel=ERROR"))


def attendre_ssh(hote, cle, delai_total, pas=10, runner=subprocess.run, dormir=time.sleep):
    """Réessaie une commande triviale jusqu'au succès.

    Renvoie True au succès, False une fois `delai_total` secondes écoulées, ou `CLE_CHANGEE` dès qu'OpenSSH refuse parce que
    l'empreinte connue du serveur a changé (attendre n'y changerait rien : l'appelant décide s'il peut l'oublier).
    Tester le succès par `is True` (`CLE_CHANGEE` est un texte non vide).
    """
    ecoule = 0
    while True:
        code, _sortie, erreur = executer(hote, "true", cle, delai=min(pas, 30), runner=runner)
        if code == 0:
            return True
        if CHANGEMENT_CLE in erreur:
            return CLE_CHANGEE
        if ecoule >= delai_total:
            return False
        dormir(pas)
        ecoule += pas
        if ecoule >= delai_total:
            return False


def oublier_hote(hote, accord, runner=subprocess.run):
    """Retire l'hôte de known_hosts (`ssh-keygen -R`) ; exige un accord strictement booléen."""
    if accord is not True:
        raise ErreurAccord("Oublier l'empreinte de l'hôte exige l'accord explicite de l'utilisateur.")
    _verifier_hote(hote)
    _lancer_court(runner, ["ssh-keygen", "-R", hote], 30)
