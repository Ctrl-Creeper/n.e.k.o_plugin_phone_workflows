#!/usr/bin/env python3
"""Synchronize the host-neutral phone runtime from hermes-phone-agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

CORE_FILES = (
    "backend.py",
    "adb_backend.py",
    "appium_backend.py",
    "appium_manager.py",
    "host_ocr.py",
    "policy.py",
    "sanitize.py",
    "wechat.py",
    "wechat_context.py",
    "native/phone_ocr.swift",
)
HELPER_APK = "helper-apk/releases/hermes-phone-agent-v0.2.4.apk"
HELPER_VERSION = "0.2.4"
PACKAGE_MARKER = '"""Generated from hermes-phone-agent; do not edit manually."""\n'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(source: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _expected(source: Path, plugin_root: Path) -> list[tuple[Path, Path]]:
    pairs = [
        (
            source / "plugins" / "phone_use" / relative,
            plugin_root / "upstream" / "phone_core" / relative,
        )
        for relative in CORE_FILES
    ]
    pairs.extend(
        [
            (
                source / HELPER_APK,
                plugin_root / "assets" / "android" / Path(HELPER_APK).name,
            ),
            (
                source / "LICENSE",
                plugin_root / "THIRD_PARTY_LICENSES" / "hermes-phone-agent-AGPL-3.0.txt",
            ),
            (source / "LICENSE", plugin_root / "LICENSE"),
        ]
    )
    return pairs


def _manifest(source: Path, plugin_root: Path) -> dict[str, object]:
    files = {}
    for _, destination in _expected(source, plugin_root):
        relative = destination.relative_to(plugin_root).as_posix()
        files[relative] = _sha256(destination)
    return {
        "repository": "https://github.com/Ctrl-Creeper/hermes-phone-agent",
        "commit": _git_commit(source),
        "helper": {
            "package": "com.hermes.phoneagent",
            "version": HELPER_VERSION,
            "sha256": files[f"assets/android/{Path(HELPER_APK).name}"],
        },
        "files": files,
    }


def _write_package_markers(plugin_root: Path) -> None:
    for relative in ("upstream/__init__.py", "upstream/phone_core/__init__.py"):
        path = plugin_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PACKAGE_MARKER, encoding="utf-8")


def sync(source: Path, plugin_root: Path) -> None:
    for origin, destination in _expected(source, plugin_root):
        if not origin.is_file():
            raise FileNotFoundError(origin)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination)
    _write_package_markers(plugin_root)
    manifest = _manifest(source, plugin_root)
    (plugin_root / "UPSTREAM.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def check(source: Path, plugin_root: Path) -> None:
    stale = []
    for origin, destination in _expected(source, plugin_root):
        if not destination.is_file() or _sha256(origin) != _sha256(destination):
            stale.append(destination.relative_to(plugin_root).as_posix())
    if stale:
        raise SystemExit("out-of-date synchronized files:\n  " + "\n  ".join(stale))

    marker_paths = {
        plugin_root / "upstream" / "__init__.py",
        plugin_root / "upstream" / "phone_core" / "__init__.py",
    }
    stale_markers = [
        path.relative_to(plugin_root).as_posix()
        for path in marker_paths
        if not path.is_file() or path.read_text(encoding="utf-8") != PACKAGE_MARKER
    ]
    if stale_markers:
        raise SystemExit("out-of-date package markers:\n  " + "\n  ".join(stale_markers))

    managed_roots = (
        plugin_root / "upstream",
        plugin_root / "assets" / "android",
        plugin_root / "THIRD_PARTY_LICENSES",
    )
    expected_managed = {
        destination.resolve()
        for _, destination in _expected(source, plugin_root)
        if any(destination.is_relative_to(root) for root in managed_roots)
    } | {path.resolve() for path in marker_paths}
    actual_managed = {
        path.resolve()
        for root in managed_roots
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }
    extras = sorted(
        path.relative_to(plugin_root).as_posix()
        for path in actual_managed - expected_managed
    )
    if extras:
        raise SystemExit("unexpected synchronized files:\n  " + "\n  ".join(extras))

    manifest_path = plugin_root / "UPSTREAM.json"
    try:
        recorded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid UPSTREAM.json: {exc}") from exc
    expected_manifest = _manifest(source, plugin_root)
    if recorded_manifest != expected_manifest:
        raise SystemExit("UPSTREAM.json does not match the synchronized source and files")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    plugin_root = Path(__file__).resolve().parents[1]
    if args.check:
        check(source, plugin_root)
    else:
        sync(source, plugin_root)


if __name__ == "__main__":
    main()
