"""« Release signé » : le serveur compile, le poste signe (tâche 15d, option 1 du Directeur).

La clé de release ne quitte jamais le poste. Le serveur construit la release NON signée (`*-release-unsigned.apk`, ou un `.aab`) ;
ce module, lancé AU POSTE par le Directeur, aligne (`zipalign`) puis signe (`apksigner`, ou `jarsigner` pour un AAB) avec les
outils du SDK Android du poste. Le mot de passe du coffre est saisi au poste (`getpass`) : il n'est jamais lu d'un argument,
d'un fichier ou de l'environnement de l'appelant, jamais journalisé ni stocké ; il ne passe qu'à l'environnement du sous-processus
de signature (jamais sur sa ligne de commande). Une signature n'est jamais lancée par un agent : sans terminal interactif, refus.

    py -3.12 lancer.py signer-release --artefact <apk non signé ou aab> --keystore <coffre> --alias <alias> --sortie <fichier> [--sdk <dossier du SDK>]
    py -3.12 lancer.py signer-release --dossier <projet> --keystore … --alias … --sortie …   (la plus récente release non
        signée rapatriée dans le projet : `construire-apk` au serveur la range sous build/app/outputs/flutter-apk/)
"""
import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VARIABLE_MOT_DE_PASSE = "MYIAFACTORY_SIGNATURE_MDP"
MOTIF_ALIAS = re.compile(r"[A-Za-z0-9_.@-]{1,64}", re.ASCII)
MOTIF_VERSION = re.compile(r"[0-9]{1,3}(\.[0-9]{1,3}){0,3}", re.ASCII)
DELAI_S = 300


class RefusSignature(Exception):
    """Message français, jamais un mot de passe."""


def chercher_artefact(dossier):
    """Le plus récent `*-release-unsigned.apk` (ou `.aab`) sous `dossier` (artefacts rapatriés du serveur) : un fichier ordinaire,
    jamais un lien. `RefusSignature` s'il n'y en a pas."""
    trouves = []
    for chemin in Path(dossier).rglob("*"):
        if chemin.is_symlink() or not chemin.is_file():
            continue
        if chemin.name.endswith("-release-unsigned.apk") or chemin.suffix == ".aab":
            trouves.append(chemin)
    if not trouves:
        raise RefusSignature("Aucune release non signée (*-release-unsigned.apk ou .aab) dans " + str(dossier))
    return max(trouves, key=lambda p: p.stat().st_mtime)


def outils_sdk(sdk, version=None):
    """`{"zipalign", "apksigner"}` : les programmes de `build-tools/<version>` (la plus haute par défaut) du SDK du poste."""
    base = Path(sdk) / "build-tools"
    if not base.is_dir():
        raise RefusSignature(f"SDK Android introuvable ({base}) : indiquez --sdk.")
    versions = sorted((v.name for v in base.iterdir() if v.is_dir() and MOTIF_VERSION.fullmatch(v.name)),
                      key=lambda n: [int(x) for x in n.split(".")])
    if version is not None:
        if version not in versions:
            raise RefusSignature(f"build-tools {version} absent du SDK.")
        versions = [version]
    if not versions:
        raise RefusSignature("Aucune version de build-tools dans le SDK.")
    dossier = base / versions[-1]
    sortie = {}
    for nom in ("zipalign", "apksigner"):
        for suffixe in ("", ".bat", ".exe"):
            if (dossier / (nom + suffixe)).is_file():
                sortie[nom] = str(dossier / (nom + suffixe))
                break
        else:
            raise RefusSignature(f"{nom} absent de build-tools/{versions[-1]}.")
    return sortie


def _lancer(executer, argv, mot_de_passe):
    """Un sous-processus de signature : le mot de passe seulement dans son environnement."""
    env = dict(os.environ)
    env[VARIABLE_MOT_DE_PASSE] = mot_de_passe
    p = executer(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=DELAI_S)
    if p.returncode != 0:
        # la sortie du programme peut citer le coffre, jamais le mot de passe (passé par l'environnement) ; coupée tout de même
        detail = (p.stderr or b"")[-400:].decode("utf-8", "replace").replace(mot_de_passe, "***") if mot_de_passe else ""
        raise RefusSignature(f"{Path(argv[0]).stem} a échoué (code {p.returncode}) : {detail.strip()}")
    return p


def signer(artefact, keystore, alias, sortie, mot_de_passe, sdk=None, outils=None, executer=subprocess.run, jarsigner="jarsigner"):
    """Aligne puis signe `artefact` vers `sortie` ; rend `sortie`. APK : `zipalign -p -f 4`, `apksigner sign` puis `verify` ;
    AAB : copie signée par `jarsigner`. `outils` : `{"zipalign", "apksigner"}` (par défaut ceux du SDK)."""
    artefact, keystore, sortie = Path(artefact), Path(keystore), Path(sortie)
    if not isinstance(alias, str) or not MOTIF_ALIAS.fullmatch(alias):
        raise RefusSignature("Alias invalide (lettres, chiffres, _ . @ - ; 64 caractères au plus).")
    if not isinstance(mot_de_passe, str) or not mot_de_passe:
        raise RefusSignature("Mot de passe du coffre vide.")
    if not artefact.is_file() or artefact.is_symlink():
        raise RefusSignature("Artefact à signer introuvable : " + artefact.name)
    if not keystore.is_file():
        raise RefusSignature("Coffre de clés introuvable : " + keystore.name)
    if sortie.exists():
        raise RefusSignature("Le fichier de sortie existe déjà : " + sortie.name)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="myiafactory-signature-") as prive:
        if artefact.suffix == ".aab":
            copie = Path(prive) / "app.aab"
            shutil.copyfile(artefact, copie)
            _lancer(executer, [jarsigner, "-keystore", str(keystore), "-storepass:env", VARIABLE_MOT_DE_PASSE,
                               "-keypass:env", VARIABLE_MOT_DE_PASSE, "-sigalg", "SHA256withRSA", "-digestalg", "SHA-256",
                               str(copie), alias], mot_de_passe)
            shutil.move(str(copie), str(sortie))
            return sortie
        if artefact.suffix != ".apk":
            raise RefusSignature("Seuls un .apk et un .aab se signent.")
        outils = outils or outils_sdk(sdk or os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "")
        aligne = Path(prive) / "aligne.apk"
        _lancer(executer, [outils["zipalign"], "-p", "-f", "4", str(artefact), str(aligne)], mot_de_passe)
        signe = Path(prive) / "signe.apk"
        _lancer(executer, [outils["apksigner"], "sign", "--ks", str(keystore), "--ks-key-alias", alias,
                           "--ks-pass", "env:" + VARIABLE_MOT_DE_PASSE, "--key-pass", "env:" + VARIABLE_MOT_DE_PASSE,
                           "--out", str(signe), str(aligne)], mot_de_passe)
        _lancer(executer, [outils["apksigner"], "verify", str(signe)], mot_de_passe)
        shutil.move(str(signe), str(sortie))
    return sortie


def main(argv=None, saisir=getpass.getpass, interactif=None, executer=subprocess.run, outils=None) -> int:
    """`signer-release (--artefact A | --dossier P) --keystore K --alias L --sortie S [--sdk D]` ; code 0 fait, 1 refusé,
    2 appel invalide. `--dossier` : la plus récente release non signée sous le projet (`chercher_artefact`). Le mot de passe
    est demandé au poste (`saisir`) ; sans terminal interactif, refus."""
    argv = list(sys.argv[1:] if argv is None else argv)
    usage = ("Usage : signer-release (--artefact <apk non signé ou aab> | --dossier <projet>) --keystore <coffre> "
             "--alias <alias> --sortie <fichier> [--sdk <SDK>]")
    valeurs, i = {}, 0
    while i < len(argv):
        nom = argv[i]
        if nom not in ("--artefact", "--dossier", "--keystore", "--alias", "--sortie", "--sdk") or i + 1 >= len(argv) \
                or nom[2:] in valeurs:
            print(usage, file=sys.stderr)
            return 2
        valeurs[nom[2:]] = argv[i + 1]
        i += 2
    if not all(k in valeurs for k in ("keystore", "alias", "sortie")) or ("artefact" in valeurs) == ("dossier" in valeurs):
        print(usage, file=sys.stderr)
        return 2
    if interactif is None:
        interactif = bool(sys.stdin and sys.stdin.isatty())
    if not interactif:
        print("Signature refusée : le mot de passe du coffre se saisit au poste, dans un terminal (jamais par un agent).",
              file=sys.stderr)
        return 1
    try:
        if "dossier" in valeurs:
            valeurs["artefact"] = str(chercher_artefact(valeurs["dossier"]))
            print("Release à signer : " + valeurs["artefact"])
        mot_de_passe = saisir("Mot de passe du coffre de clés (non enregistré) : ")
        signer(valeurs["artefact"], valeurs["keystore"], valeurs["alias"], valeurs["sortie"], mot_de_passe,
               sdk=valeurs.get("sdk"), outils=outils, executer=executer)
    except RefusSignature as e:
        print("Signature refusée : " + str(e), file=sys.stderr)
        return 1
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Signature impossible ({type(e).__name__}).", file=sys.stderr)
        return 1
    print("Release signée : " + str(valeurs["sortie"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
