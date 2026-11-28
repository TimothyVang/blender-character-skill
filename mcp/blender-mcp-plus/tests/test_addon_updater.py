"""The addon's update machinery. blender-mcp-plus never fetches upstream's addon.py (it would replace the fork's
hooks and port); the install path still never installs something that isn't the addon and leaves the installed
file untouched when anything goes wrong.
"""
import types

import pytest

from conftest import ROOT_ADDON
from test_polypizza import _load_addon, _scene

SOURCE = ROOT_ADDON.read_text(encoding="utf-8")


def _with_version(version, protocol):
    """The real addon.py with its version and protocol swapped."""
    import re

    text = re.sub(r'"version": \(\d+, \d+\)', f'"version": {version}', SOURCE, count=1)
    return re.sub(r"^ADDON_PROTOCOL_VERSION = \d+", f"ADDON_PROTOCOL_VERSION = {protocol}", text, count=1, flags=re.M)


@pytest.fixture
def addon(monkeypatch):
    module = _load_addon(monkeypatch, _scene())
    module._addon_update.update(status="idle", version=None, source=None, error=None)
    return module


def _serve(monkeypatch, addon, response):
    monkeypatch.setattr(addon.requests, "get", lambda url, timeout=None: response, raising=False)


def test_release_key_reads_version_and_protocol(addon):
    key = addon.addon_release_key(SOURCE)
    assert key == tuple(addon.bl_info["version"]) + (0, addon.ADDON_PROTOCOL_VERSION)
    assert addon.addon_release_key(_with_version((2, 0, 3), 40)) == (2, 0, 3, 40)
    assert addon.addon_version_label((2, 0, 3, 40)) == "2.0.3"
    assert addon.addon_version_label((1, 8, 0, 12)) == "1.8"


@pytest.mark.parametrize("text", [
    "print('hello')",
    SOURCE.replace('"name": "MCP for Blender"', '"name": "Something Else"', 1),
    SOURCE.replace("ADDON_PROTOCOL_VERSION = ", "PROTOCOL = ", 1),
], ids=["not-the-addon", "renamed-addon", "no-protocol"])
def test_release_key_rejects_files_that_are_not_the_addon(addon, text):
    assert addon.addon_release_key(text) is None


def test_the_fork_never_fetches_or_offers_upstream(monkeypatch, addon):
    def fetch(url, timeout=None):
        raise AssertionError(f"fetched {url}")
    monkeypatch.setattr(addon.requests, "get", fetch, raising=False)
    addon.check_for_addon_update()
    assert addon._addon_update["status"] == "current"
    assert addon._addon_update["source"] is None


def test_version_still_known_when_loaded_as_an_extension(monkeypatch, addon):
    # Blender deletes bl_info from a module it loads as an extension (#443).
    monkeypatch.delattr(addon, "bl_info")
    assert addon._local_release_key() == addon.ADDON_VERSION + (0, addon.ADDON_PROTOCOL_VERSION)
    info = addon.BlenderMCPServer().get_addon_info()
    assert (info["name"], info["addon_version"]) == ("MCP for Blender", list(addon.ADDON_VERSION))

    sent = {}

    def request(method, url, headers=None, **_kwargs):
        sent.update(headers)
        raise ConnectionError("offline")
    monkeypatch.setattr(addon.requests, "request", request, raising=False)
    addon.premium_request("GET", "/v1/usage", auth=False)
    assert sent["X-Addon-Version"] == ".".join(str(part) for part in addon.ADDON_VERSION)

    _serve(monkeypatch, addon, types.SimpleNamespace(status_code=200, text=SOURCE))
    addon.check_for_addon_update()
    assert addon._addon_update["status"] == "current"


def test_install_replaces_the_file_and_keeps_a_backup(tmp_path, addon):
    target = tmp_path / "addon.py"
    target.write_text(SOURCE, encoding="utf-8")
    newer = _with_version((99, 0), 99)
    addon.install_addon_update(str(target), newer)
    assert target.read_text(encoding="utf-8") == newer
    assert (tmp_path / "addon.py.bak").read_text(encoding="utf-8") == SOURCE
    assert not (tmp_path / "addon.py.new").exists()


@pytest.mark.parametrize(
    "bad",
    ["print('not the addon')", _with_version((99, 0), 99) + "\ndef broken(:\n"],
    ids=["not-the-addon", "syntax-error"],
)
def test_install_refuses_anything_but_a_valid_addon(tmp_path, addon, bad):
    target = tmp_path / "addon.py"
    target.write_text(SOURCE, encoding="utf-8")
    with pytest.raises(Exception):
        addon.install_addon_update(str(target), bad)
    assert target.read_text(encoding="utf-8") == SOURCE
    assert list(tmp_path.iterdir()) == [target]
