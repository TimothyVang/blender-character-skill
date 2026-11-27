"""Tiny background-Blender job for the blender-live smoke test: add N cubes and report a marker line."""
import bpy, json, sys
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 1
for i in range(n): bpy.ops.mesh.primitive_cube_add(location=(i * 3, 0, 0))
print("HEADLESS " + json.dumps({"cubes": n, "objects": len(bpy.data.objects), "version": bpy.app.version_string}))
