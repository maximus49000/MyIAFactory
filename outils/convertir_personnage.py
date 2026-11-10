"""Convertit le personnage livré par Tripo (FBX à squelette, avec son animation) en un GLB pour la page.

À lancer avec Blender (testé avec Blender 3.2), pas avec Python :

    blender -b -P outils/convertir_personnage.py -- <entree.fbx|entree.glb> <sortie.glb>

Le script importe le modèle, nomme « marche » sa première animation et exporte un GLB avec la
texture et l'animation. La page (scene/squelette.js) attend des os nommés à la Mixamo (Hips,
LeftUpLeg, LeftArm…), une animation de marche sur place, et l'avant du personnage vers +z
(repère glTF) ; la mise à l'échelle et la pose au sol sont faites par la page (manifeste.json).
"""
import sys

try:
    import bpy
except ImportError:  # lancé avec Python au lieu de Blender
    print("Ce script se lance avec Blender : blender -b -P outils/convertir_personnage.py -- "
          "<entree.fbx|entree.glb> <sortie.glb>")
    sys.exit(2)


def principal():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 2:
        print("Usage : blender -b -P outils/convertir_personnage.py -- <entree.fbx|entree.glb> <sortie.glb>")
        sys.exit(2)
    entree, sortie = args
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if entree.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=entree)
    else:
        bpy.ops.import_scene.gltf(filepath=entree)
    if not any(o.type == "ARMATURE" for o in bpy.data.objects):
        print("Erreur : le modèle n'a pas de squelette.")
        sys.exit(1)
    if not bpy.data.actions:
        print("Erreur : le modèle n'a pas d'animation.")
        sys.exit(1)
    bpy.data.actions[0].name = "marche"
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=sortie, export_format="GLB", export_animations=True,
                              export_yup=True, export_apply=False, export_image_format="AUTO")
    print(f"Écrit : {sortie}")


principal()
