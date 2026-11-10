"""Dessine les petites images inventées de la démo (PNG, bibliothèque standard seulement).

    py -3.12 outils/images_demo.py

Les images sont versionnées : ce script ne sert qu'à les refaire. Tout y est inventé : un magasin imaginaire
(rayons vus de face et de côté, « réel » et « produit »), une maquette, un croquis.
"""
import struct
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
L, H = 240, 160


def png(chemin, pixels):
    lignes = b"".join(b"\x00" + bytes(v for p in ligne for v in p) for ligne in pixels)

    def bloc(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", L, H, 8, 2, 0, 0, 0))
                       + bloc(b"IDAT", zlib.compress(lignes, 9)) + bloc(b"IEND", b""))


def toile(fond):
    return [[fond] * L for _ in range(H)]


def rect(px, x0, y0, x1, y1, c):
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(L, x1)):
            px[y][x] = c


def grain(px, force, graine):
    """Un léger bruit régulier : la « photo réelle » n'est pas aussi lisse que le rendu."""
    for y in range(H):
        for x in range(L):
            d = ((x * 31 + y * 17 + graine * 7) % 11 - 5) * force
            px[y][x] = tuple(max(0, min(255, v + d)) for v in px[y][x])


def rayon(couleur, etageres=3, cote=False, reel=False, graine=0, passe=2):
    """Un rayon de magasin : un meuble, des étagères, des produits colorés."""
    px = toile((236, 230, 218) if not reel else (222, 214, 200))
    rect(px, 0, 128, L, H, (190, 176, 156))                                  # le sol
    x0, x1 = (60, 200) if cote else (30, 210)
    rect(px, x0, 22, x1, 128, (120, 92, 70))                                # le meuble
    for i in range(etageres):
        y = 30 + i * (92 // etageres)
        rect(px, x0 + 6, y, x1 - 6, y + 4, (90, 68, 52))                    # l'étagère
        pas = 14 if cote else 18
        for k, x in enumerate(range(x0 + 10, x1 - 14, pas)):
            teinte = tuple(max(0, min(255, c + ((k + i + graine) % 3 - 1) * 28)) for c in couleur)
            haut = 18 if passe >= 2 else 12
            rect(px, x, y - haut, x + pas - 5, y, teinte)                   # un produit
    if reel:
        grain(px, 2, graine)
    return px


def maquette():
    px = toile((250, 248, 242))
    rect(px, 10, 10, L - 10, 30, (31, 58, 107))                             # le bandeau
    for i, c in enumerate([(200, 120, 60), (60, 120, 170), (90, 150, 90)]):
        rect(px, 16 + i * 74, 44, 80 + i * 74, 120, c)                      # trois zones
    rect(px, 16, 130, L - 16, 146, (210, 204, 190))                         # une barre de recherche
    return px


def croquis():
    px = toile((255, 255, 250))
    for y in (40, 70, 100, 130):
        rect(px, 20, y, L - 20, y + 2, (120, 120, 140))                     # les lignes de l'agenda
    rect(px, 60, 72, 150, 98, (240, 170, 60))                               # un rendez-vous
    rect(px, 20, 14, 120, 28, (60, 60, 80))                                 # le titre
    return px


def main():
    demo = RACINE / "exemples" / "demo" / "images"
    rayons = {"fruits": (190, 70, 60), "pain": (205, 160, 90), "fromage": (230, 210, 120),
              "boissons": (60, 120, 180), "jouets": (150, 90, 170), "caisse": (90, 150, 110)}
    for i, (nom, c) in enumerate(rayons.items()):
        png(demo / "magasin" / f"{nom}-p1.png", rayon(c, graine=i, passe=1))
        png(demo / "magasin" / f"{nom}-p2.png", rayon(c, graine=i, passe=2))
    for nom in ("fruits", "pain"):
        c = rayons[nom]
        png(demo / "magasin" / f"{nom}-reel-face.png", rayon(c, reel=True, graine=3))
        png(demo / "magasin" / f"{nom}-reel-cote.png", rayon(c, cote=True, reel=True, graine=5))
        png(demo / "magasin" / f"{nom}-produit-cote.png", rayon(c, cote=True, graine=5))
    png(demo / "magasin" / "maquette.png", maquette())
    for projet in ("demo", "demo-b"):
        dossier = RACINE / "exemples" / projet / "images" / "parcours"
        png(dossier / "maquette.png", maquette())
        png(dossier / "prototype.png", rayon((120, 140, 200), etageres=2))
    png(RACINE / "exemples" / "demo-b" / "images" / "croquis-agenda.png", croquis())


if __name__ == "__main__":
    main()
