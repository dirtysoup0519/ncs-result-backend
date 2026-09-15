"""Import the newest local ADS package into the configured VM MySQL database."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import shutil
import sys
import tarfile
from uuid import uuid4
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts.import_ads_v23 import main as import_ads_main
from ncs_backend.shared.local_config import load_local_config


PACKAGE_ROOT = REPO_ROOT / "data_exchange" / "packages"
CACHE_ROOT = REPO_ROOT / ".local" / "package-cache"


def main(argv: list[str] | None = None) -> int:
    load_local_config(REPO_ROOT / ".local" / "ncs.env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", nargs="?", type=Path, help="package directory, .zip or .tar.gz; defaults to newest package")
    parser.add_argument("--initialize", action="store_true", help="initialize schema before importing")
    args = parser.parse_args(argv)

    source = _resolve_package(args.package)
    print(f"PACKAGE_SELECTED {source}")
    with _materialized(source) as package_directory:
        command = ["--package", str(package_directory)]
        if not args.initialize:
            command.append("--skip-initialize")
        return import_ads_main(command)


def _resolve_package(requested: Path | None) -> Path:
    if requested is not None:
        path = requested.expanduser()
        if not path.is_absolute():
            direct = (Path.cwd() / path).resolve()
            path = direct if direct.exists() else (PACKAGE_ROOT / path).resolve()
        else:
            path = path.resolve()
        if not path.exists():
            raise SystemExit(f"PACKAGE_NOT_FOUND: {path}")
        return path

    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    candidates = [
        path for path in PACKAGE_ROOT.iterdir()
        if path.is_dir() or path.name.lower().endswith((".zip", ".tar.gz", ".tgz"))
    ]
    if not candidates:
        raise SystemExit(f"NO_PACKAGE: place an ADS package in {PACKAGE_ROOT}")
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


@contextmanager
def _materialized(source: Path):
    if source.is_dir():
        yield source
        return
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    target = CACHE_ROOT / f"{_archive_stem(source)}-{uuid4().hex[:8]}"
    target.mkdir(parents=False)
    succeeded = False
    try:
        if source.name.lower().endswith(".zip"):
            _extract_zip(source, target)
        elif source.name.lower().endswith((".tar.gz", ".tgz")):
            _extract_tar(source, target)
        else:
            raise SystemExit(f"UNSUPPORTED_PACKAGE: {source}")
        yield target
        succeeded = True
    finally:
        if succeeded:
            shutil.rmtree(target)
        else:
            print(f"PACKAGE_CACHE_KEPT {target}", file=sys.stderr)


def _extract_zip(source: Path, target: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            _safe_destination(target, member.filename)
        archive.extractall(target)


def _extract_tar(source: Path, target: Path) -> None:
    with tarfile.open(source, "r:*") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise SystemExit(f"UNSAFE_ARCHIVE_LINK: {member.name}")
            _safe_destination(target, member.name)
        archive.extractall(target)


def _safe_destination(root: Path, member: str) -> Path:
    destination = (root / member).resolve()
    if root.resolve() not in destination.parents and destination != root.resolve():
        raise SystemExit(f"UNSAFE_ARCHIVE_MEMBER: {member}")
    return destination


def _archive_stem(path: Path) -> str:
    name = path.name
    for suffix in (".tar.gz", ".tgz", ".zip"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


if __name__ == "__main__":
    raise SystemExit(main())
