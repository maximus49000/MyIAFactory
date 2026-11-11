"""Les adresses par lesquelles le téléphone atteint le bureau : Tailscale (par défaut) et le réseau local privé.

Rien n'est installé ni envoyé : `tailscale ip -4` est lu s'il existe, et l'adresse de sortie de la machine est lue
par un socket UDP « connecté » sans aucun envoi.
"""
import ipaddress
import socket
import subprocess

RESEAUX_PRIVES = tuple(ipaddress.ip_network(r) for r in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
PLAGE_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
CIBLE_SANS_ENVOI =("192.0.2.1", 9)   # adresse de documentation : connect() en UDP n'envoie rien


def _ipv4(texte):
    try:
        return ipaddress.IPv4Address(texte.strip())
    except (ValueError, AttributeError):
        return None


def adresse_tailscale(executer=subprocess.run):
    """L'adresse Tailscale (IPv4) de la machine, ou None si Tailscale est absent, arrêté ou muet."""
    try:
        r = executer(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    a = _ipv4(r.stdout.splitlines()[0])
    # seule la plage de Tailscale : une autre sortie (0.0.0.0 surtout) ouvrirait un écouteur où il ne faut pas
    return str(a) if a is not None and a in PLAGE_TAILSCALE else None


def adresse_reseau_local(fabrique=socket.socket):
    """L'adresse IPv4 de la machine dans le réseau de la maison, seulement si elle est privée ; sinon None."""
    try:
        with fabrique(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(CIBLE_SANS_ENVOI)
            a = _ipv4(s.getsockname()[0])
    except OSError:
        return None
    return str(a) if a is not None and any(a in r for r in RESEAUX_PRIVES) else None


def adresses():
    """{"tailscale": adresse | None, "reseau_local": adresse | None}."""
    return {"tailscale": adresse_tailscale(), "reseau_local": adresse_reseau_local()}
