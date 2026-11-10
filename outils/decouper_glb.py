"""Découpe un GLB qui contient plusieurs objets côte à côte en un GLB par objet.

À lancer avec Blender (testé avec Blender 3.2), pas avec Python :

    blender -b -P outils/decouper_glb.py -- <entree.glb|entree.fbx> <dossier_sortie> <nom1,nom2,...>

Ce que fait le script :
  1. importe le GLB et réunit tous ses morceaux de maillage ;
  2. les sépare par parties non reliées, puis regroupe en un seul objet les parties dont les
     boîtes englobantes se touchent ou se recouvrent (un écran et son clavier, un pot et sa plante) ;
  3. trie les objets de gauche à droite (sens de lecture de la vue de face), les nomme dans
     l'ordre des noms donnés ;
  4. recentre chacun (centre en x et en profondeur, base au sol) ;
  5. exporte un GLB par objet : <dossier_sortie>/<nom>.glb.

Si le nombre d'objets trouvés n'est pas celui des noms donnés, le script s'arrête avec un
message clair et n'écrit rien. Convention du reste du projet : l'avant d'un objet regarde vers +z
(repère glTF), la base est à y = 0.
"""
import sys
from pathlib import Path

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:  # lancé avec Python au lieu de Blender
    print("Ce script se lance avec Blender : blender -b -P outils/decouper_glb.py -- "
          "<entree.glb|entree.fbx> <dossier_sortie> <nom1,nom2,...>")
    sys.exit(2)

MARGE_RELATIVE = 0.005   # tolérance de contact : 0,5 % de la taille de l'ensemble


def arreter(message, code=1):
    print(f"\nERREUR : {message}\n")
    sys.exit(code)


def lire_arguments():
    argv = sys.argv
    if "--" not in argv:
        arreter("usage : blender -b -P outils/decouper_glb.py -- <entree.glb|entree.fbx> <dossier_sortie> <nom1,nom2,...>", 2)
    args = argv[argv.index("--") + 1:]
    if len(args) != 3:
        arreter("il faut trois arguments : <entree.glb|entree.fbx> <dossier_sortie> <nom1,nom2,...>", 2)
    entree, sortie = Path(args[0]), Path(args[1])
    noms = [n.strip() for n in args[2].split(",") if n.strip()]
    if not entree.is_file():
        arreter(f"fichier introuvable : {entree}", 2)
    if not noms or len(set(noms)) != len(noms):
        arreter("la liste des noms est vide ou contient un doublon", 2)
    return entree, sortie, noms


def boite_monde(objet):
    """Boîte englobante (min, max) en coordonnées du monde."""
    coins = [objet.matrix_world @ Vector(c) for c in objet.bound_box]
    return (Vector((min(c[i] for c in coins) for i in range(3))),
            Vector((max(c[i] for c in coins) for i in range(3))))


def se_touchent(a, b, marge):
    return all(a[0][i] - marge <= b[1][i] and b[0][i] - marge <= a[1][i] for i in range(3))


def selectionner(objets):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objets:
        o.select_set(True)
    if objets:
        bpy.context.view_layer.objects.active = objets[0]


def main():
    entree, sortie, noms = lire_arguments()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if entree.suffix.lower() == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(entree))   # la texture est cherchée dans le dossier .fbm voisin
    else:
        bpy.ops.import_scene.gltf(filepath=str(entree))

    maillages = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not maillages:
        arreter("le fichier ne contient aucun maillage.")

    # Tout détacher de ses parents en gardant la position, jeter les objets vides, tout réunir.
    selectionner(list(bpy.context.scene.objects))
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    autres = [o for o in bpy.context.scene.objects if o.type != "MESH"]
    for o in autres:
        bpy.data.objects.remove(o, do_unlink=True)
    selectionner(maillages)
    if len(maillages) > 1:
        bpy.ops.object.join()
    unique = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # Séparer par parties non reliées.
    selectionner([unique])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    # Les coutures de texture dédoublent des sommets : on les ressoude pour ne pas obtenir
    # des milliers de petits morceaux (le regroupement ci-dessous s'en chargerait, mais lentement).
    bpy.ops.mesh.remove_doubles(threshold=1e-5)
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    parties = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.context.view_layer.update()

    # Regrouper les parties qui se touchent (union-find sur les boîtes englobantes).
    boites = [boite_monde(o) for o in parties]
    tout_min = Vector((min(b[0][i] for b in boites) for i in range(3)))
    tout_max = Vector((max(b[1][i] for b in boites) for i in range(3)))
    marge = max(tout_max - tout_min) * MARGE_RELATIVE
    parent = list(range(len(parties)))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Balayage en x : on trie par bord gauche et on s'arrête dès que les boîtes ne peuvent plus se toucher.
    ordre = sorted(range(len(parties)), key=lambda i: boites[i][0].x)
    for a, i in enumerate(ordre):
        for j in ordre[a + 1:]:
            if boites[j][0].x - marge > boites[i][1].x:
                break
            if se_touchent(boites[i], boites[j], marge):
                parent[racine(i)] = racine(j)
    groupes = {}
    for i, o in enumerate(parties):
        groupes.setdefault(racine(i), []).append(o)

    # Gauche -> droite : ordre croissant du centre en x.
    def centre_x(groupe):
        bs = [boite_monde(o) for o in groupe]
        return (min(b[0].x for b in bs) + max(b[1].x for b in bs)) / 2

    ordonnes = sorted(groupes.values(), key=centre_x)
    if len(ordonnes) != len(noms) and len(parties) == len(noms):
        # Autant de parties non reliées que d'objets attendus : leurs boîtes se recouvrent
        # seulement (une chaise devant un clavier), elles ne se touchent pas vraiment.
        ordonnes = sorted(([o] for o in parties), key=centre_x)
    print(f"{len(parties)} parties non reliées, regroupées en {len(ordonnes)} objets "
          f"(attendu : {len(noms)}).")
    if len(ordonnes) != len(noms):
        detail = ", ".join(f"objet {k + 1} : {len(g)} partie(s) vers x = {centre_x(g):.2f}" for k, g in enumerate(ordonnes))
        arreter(f"{len(ordonnes)} objets trouvés, {len(noms)} attendus ({', '.join(noms)}). {detail}. "
                "Vérifiez que les objets de la génération ne se touchent pas (ou, au contraire, "
                "que chaque objet est d'un seul tenant), puis relancez la génération.")

    # Un GLB par objet, recentré, base au sol.
    sortie.mkdir(parents=True, exist_ok=True)
    for nom, groupe in zip(noms, ordonnes):
        selectionner(groupe)
        if len(groupe) > 1:
            bpy.ops.object.join()
        objet = bpy.context.view_layer.objects.active
        objet.name = nom
        objet.data.name = nom
        bpy.context.view_layer.update()
        bas, haut = boite_monde(objet)
        decalage = Vector(((bas.x + haut.x) / 2, (bas.y + haut.y) / 2, bas.z))
        objet.data.transform(Matrix.Translation(-decalage))   # la base au sol, centré
        objet.location = (0, 0, 0)
        bpy.context.view_layer.update()
        chemin = sortie / f"{nom}.glb"
        selectionner([objet])
        bpy.ops.export_scene.gltf(filepath=str(chemin), export_format="GLB", use_selection=True, export_yup=True)
        taille = objet.dimensions
        print(f"  {nom}.glb : {taille.x:.3f} x {taille.z:.3f} (haut) x {taille.y:.3f} (unités du fichier)")
    print("Découpe terminée.")


main()
