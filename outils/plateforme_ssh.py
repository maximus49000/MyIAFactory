"""Exécuteur SSH et clé dédiée de la plateforme (client OpenSSH de Windows).

Règles : jamais `StrictHostKeyChecking=no` (`accept-new`), toujours `BatchMode=yes` et `PasswordAuthentication=no`
(aucun mot de passe), clé dédiée `-i`. Un texte sensible (licence) passe par l'entrée standard (`input=` du runner),
jamais dans les arguments de la commande. `oublier_hote` retire une empreinte connue : accord explicite requis.
Tout sous-processus passe par `runner` (injectable) : les tests ne font aucune connexion réelle.
"""
import re
import subprocess
import threading
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


# --- Session en flux avec laisse (route serveur des tests) -------------------------------------------------------------
# Protocole de `serveur_ovh/taches/lancer_tests.sh` : la sortie d'erreur du conteneur arrive préfixée par `| ` ; seules
# les lignes de l'enveloppe commencent par `#`. La marque de fin n'est crue que si c'est la DERNIÈRE ligne non vide de la
# sortie d'erreur, entière (terminée par un retour) et exactement de la forme `#fin <code> <debut> <fin> <attente>` :
# une ligne des tests qui imite `#fin 0 …` (préfixée, ou suivie d'autre chose) ne peut pas changer un échec en succès.
MOTIF_FIN = re.compile(rb"#fin ([0-9]{1,3}) ([0-9]{1,12}) ([0-9]{1,12}) ([0-9]{1,12})")
MOTIF_ATTENTE = re.compile(rb"#attente ([0-9]{1,6}) ([0-9]{1,6})(?: [0-9]{1,6})?")
LIGNE_MAX = 4096           # une ligne de la sortie d'erreur au-delà : gardée tronquée, jamais une marque
ERREUR_GARDEE = 65536      # la fin de la sortie d'erreur gardée pour le diagnostic
PREMIERE_LIGNE_MAX = 4096  # la commande JSON lue par l'enveloppe


def _marque_de_fin(ligne):
    m = MOTIF_FIN.fullmatch(ligne) if ligne else None
    if m is None or int(m.group(1)) > 255:
        return None
    return tuple(int(x) for x in m.groups())


class _Erreurs:
    """Lit la sortie d'erreur de ssh ligne par ligne (mémoire bornée) : `#attente` → `sur_attente`, le reste gardé
    (64 Ko de fin) et montré sur `sortie_erreur`, et la dernière ligne non vide notée pour la marque de fin."""

    def __init__(self, sur_attente, sortie_erreur, activite):
        self.sur_attente = sur_attente
        self.sortie_erreur = sortie_erreur
        self.activite = activite
        self.garde = bytearray()
        self.ligne = bytearray()
        self.trop_long = False
        self.derniere = None     # dernière ligne non vide complète ; b"" : une ligne qui ne peut pas être une marque
        self.vu = False          # quelque chose de l'enveloppe (place, sortie du conteneur, marque) est arrivé

    def lire(self, flux):
        lire = getattr(flux, "read1", None) or flux.read
        try:
            while True:
                b = lire(65536)
                if not b:
                    break
                self.activite()
                self._morceau(b)
        except (OSError, ValueError):
            pass
        if self.ligne.strip() or self.trop_long:   # ligne finale sans retour : session coupée, jamais une marque
            self._montrer(bytes(self.ligne))
            self.derniere = b""

    def _morceau(self, b):
        debut = 0
        while True:
            i = b.find(b"\n", debut)
            if i < 0:
                self._ajouter(b[debut:])
                return
            self._ajouter(b[debut:i])
            self._ligne_finie()
            debut = i + 1

    def _ajouter(self, part):
        if self.trop_long or not part:
            return
        place = LIGNE_MAX - len(self.ligne)
        if len(part) > place:
            self.ligne += part[:place]
            self.trop_long = True
        else:
            self.ligne += part

    def _ligne_finie(self):
        brute, trop_long = bytes(self.ligne), self.trop_long
        self.ligne, self.trop_long = bytearray(), False
        ligne = brute[:-1] if brute.endswith(b"\r") else brute
        if trop_long:
            self.derniere = b""
            self._montrer(brute + b"...\n")
            return
        if not ligne.strip():
            self._montrer(brute + b"\n")
            return
        self.derniere = ligne
        if ligne.startswith(b"| "):
            self.vu = True
        m = MOTIF_ATTENTE.fullmatch(ligne)
        if m is not None:
            self.vu = True
            if self.sur_attente is not None:
                try:
                    self.sur_attente(int(m.group(1)), int(m.group(2)))
                except Exception:   # noqa: BLE001 — un affichage cassé ne doit jamais bloquer la lecture (tuyau plein)
                    pass
            return
        if MOTIF_FIN.fullmatch(ligne):
            self.vu = True
            return
        self._montrer(brute + b"\n")

    def _montrer(self, b):
        self.garde += b
        if len(self.garde) > 2 * ERREUR_GARDEE:
            del self.garde[:-ERREUR_GARDEE]
        if self.sortie_erreur is not None:
            try:
                self.sortie_erreur.write(b)
                self.sortie_erreur.flush()
            except (OSError, ValueError):
                self.sortie_erreur = None

    def texte(self):
        return bytes(self.garde[-ERREUR_GARDEE:]).decode("utf-8", "replace")


class _Suivi:
    """La sortie standard de ssh, dont chaque lecture compte comme une activité (délai de silence)."""

    def __init__(self, flux, activite):
        self.flux = flux
        self.activite = activite

    def read1(self, n):
        lire = getattr(self.flux, "read1", None) or self.flux.read
        try:
            b = lire(n)
        except (OSError, ValueError):
            return b""
        if b:
            self.activite()
        return b


def _fermer(flux):
    try:
        flux.close()
    except (OSError, ValueError):
        pass


def _lacher_laisse(p, ecrivain):
    """Ferme l'entrée de ssh (la laisse : l'enveloppe tue le conteneur). Si l'écriture de la première ligne est encore
    bloquée (ssh ne lit pas encore), fermer attendrait le verrou du tampon : ssh est alors tué d'abord."""
    if ecrivain.is_alive():
        try:
            p.kill()
        except OSError:
            pass
    _fermer(p.stdin)


def _arreter(p, ecrivain):
    """Ctrl-C : laisse fermée, `terminate()`, puis `kill()` après 5 s ; un second Ctrl-C ici tue ssh tout de suite."""
    try:
        _lacher_laisse(p, ecrivain)
        try:
            p.terminate()
        except OSError:
            pass
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    except KeyboardInterrupt:
        try:
            p.kill()
        except OSError:
            pass
        raise


def executer_en_flux(hote, commande, cle, premiere_ligne, sortie, sur_attente=None, delai_connexion=30,
                     popen=subprocess.Popen, sortie_erreur=None, delai_total=None, delai_silence=None):
    """Une session ssh qui lance `commande` (l'enveloppe `lancer_tests.sh`, construite de valeurs validées par
    l'appelant) : `premiere_ligne` (la commande JSON) est écrite sur l'entrée standard, terminée par `\\n`, puis l'entrée
    reste OUVERTE jusqu'à la fin de la sortie standard : c'est la laisse (fermée = le serveur tue le conteneur).

    La sortie standard est relayée en direct vers `sortie` (`campagne.relayer`, 4 Ko de fin gardés) ; la sortie d'erreur
    est lue dans un fil : `#attente r t` → `sur_attente(r, t)`, le reste gardé (64 Ko de fin) et, si `sortie_erreur` est
    donnée, montré en direct (c'est là que unittest écrit, préfixé `| `). `delai_total` / `delai_silence` (secondes,
    facultatifs) : au-delà, laisse fermée et ssh tué, code 124. Ctrl-C : laisse fermée, ssh arrêté, exception relevée.

    Rend {"code", "octets", "fin", "fin_serveur", "erreur", "code_ssh", "raison"} : `fin_serveur` = les quatre entiers de
    `#fin` seulement si c'est la dernière ligne non vide de la sortie d'erreur ; `code` = celui de la marque s'il y en a
    une, 124 après un délai, sinon celui de ssh ; `raison` : "fin" (marque lue), "delai", "silence", "connexion" (ssh 255
    sans rien reçu de l'enveloppe) ou "perdue" (session finie sans marque)."""
    import campagne
    _verifier_hote(hote)
    if not isinstance(commande, str) or not commande.strip() or any(c in commande for c in "\r\n\0"):
        raise ValueError("Commande distante invalide : vide ou sur plusieurs lignes.")
    if not isinstance(premiere_ligne, bytes):
        raise ValueError("La première ligne doit être des octets.")
    ligne = premiere_ligne[:-1] if premiere_ligne.endswith(b"\n") else premiere_ligne
    if not ligne.strip() or len(ligne) > PREMIERE_LIGNE_MAX or any(c in ligne for c in b"\r\n\0"):
        raise ValueError(f"Première ligne invalide : vide, sur plusieurs lignes ou plus de {PREMIERE_LIGNE_MAX} octets.")
    args = ["ssh", *_options(cle), "-T", "-o", f"ConnectTimeout={max(1, min(int(delai_connexion), 30))}",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4", "--", hote, commande]
    try:
        p = popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise ErreurSsh(f"« {args[0]} » est introuvable : le client OpenSSH de Windows est requis "
                        "(Paramètres > Applications > Fonctionnalités facultatives > Client OpenSSH).") from None
    etat = {"activite": time.monotonic(), "coupure": None}
    fini = threading.Event()

    def activite():
        etat["activite"] = time.monotonic()

    erreurs = _Erreurs(sur_attente, sortie_erreur, activite)

    def ecrire():
        try:
            p.stdin.write(ligne + b"\n")
            p.stdin.flush()
        except (OSError, ValueError):
            pass     # ssh déjà mort (connexion refusée) : son code et sa sortie d'erreur le diront

    def surveiller():
        debut = time.monotonic()
        delais = [d for d in (delai_total, delai_silence) if d is not None]
        pas = max(0.001, min(0.5, min(delais) / 4))
        while not fini.is_set():
            maintenant = time.monotonic()
            if delai_total is not None and maintenant - debut >= delai_total:
                etat["coupure"] = "delai"
            elif delai_silence is not None and maintenant - etat["activite"] >= delai_silence:
                etat["coupure"] = "silence"
            else:
                fini.wait(pas)
                continue
            try:
                p.kill()
            except OSError:
                pass
            _lacher_laisse(p, ecrivain)
            return

    lecteur = threading.Thread(target=erreurs.lire, args=(p.stderr,), daemon=True)
    ecrivain = threading.Thread(target=ecrire, daemon=True)
    lecteur.start()
    ecrivain.start()
    if delai_total is not None or delai_silence is not None:
        threading.Thread(target=surveiller, daemon=True).start()
    try:
        octets, fin = campagne.relayer(_Suivi(p.stdout, activite), sortie, garder=4096)
        lecteur.join(10)              # la sortie d'erreur finit avec ssh
        _lacher_laisse(p, ecrivain)   # la laisse, seulement après la fin de la sortie standard
        try:
            code_ssh = p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            code_ssh = p.wait(timeout=10)
        lecteur.join(2)
    except BaseException:
        fini.set()
        _arreter(p, ecrivain)
        raise
    finally:
        fini.set()
    fin_serveur = _marque_de_fin(erreurs.derniere) if not lecteur.is_alive() else None
    if fin_serveur is not None:
        code, raison = fin_serveur[0], "fin"
    elif etat["coupure"] is not None:
        code, raison = 124, etat["coupure"]
    else:
        code = code_ssh
        raison = "connexion" if code_ssh == 255 and octets == 0 and not erreurs.vu else "perdue"
    return {"code": code, "octets": octets, "fin": fin, "fin_serveur": fin_serveur, "erreur": erreurs.texte(),
            "code_ssh": code_ssh, "raison": raison}


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
