"""Install the blender-mcp-plus addon into a Blender version's user add-ons folder, as the package
`blender_mcp_plus`: addon.py as its __init__.py, addon_plus.py beside it, and live_dir.txt naming this repository's
mcp/blender-live (the likeness, paint and sculpt code it runs). Enable it in Blender afterwards (Preferences >
Add-ons > "MCP for Blender", folder blender_mcp_plus) or from Python with addon_utils.enable("blender_mcp_plus").

  python mcp/blender-mcp-plus/install_addon.py [--blender-version 4.5] [--addons-dir PATH]
"""
import argparse
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))


def default_addons_dir(version: str) -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "Blender Foundation", "Blender", version, "scripts", "addons")


def install(addons_dir: str) -> str:
    target = os.path.join(addons_dir, "blender_mcp_plus")
    os.makedirs(target, exist_ok=True)
    shutil.copy2(os.path.join(HERE, "addon.py"), os.path.join(target, "__init__.py"))
    shutil.copy2(os.path.join(HERE, "addon_plus.py"), os.path.join(target, "addon_plus.py"))
    with open(os.path.join(target, "live_dir.txt"), "w", encoding="utf-8") as f:
        f.write(os.path.abspath(os.path.join(HERE, "..", "blender-live")))
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender-version", default="4.5")
    ap.add_argument("--addons-dir", default="")
    a = ap.parse_args()
    print(install(a.addons_dir or default_addons_dir(a.blender_version)))
