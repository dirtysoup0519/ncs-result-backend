"""Create a handoff zip from committed files only."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import zipfile

FORBIDDEN_PARTS = {".env", ".local", "__pycache__", ".pytest_cache"}
FORBIDDEN_SUFFIXES = {".sqlite", ".db", ".pem", ".key", ".pfx", ".p12"}
FORBIDDEN_CONTENT = (
    re.compile(rb"mysql(?:\+pymysql)?://[^\s:<]+:[^\s@<]+@", re.IGNORECASE),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create a credential-free frontend handoff archive")
    parser.add_argument("--output", type=Path, default=Path("dist/ncs-frontend-handoff.zip"))
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[1]
    output = args.output if args.output.is_absolute() else repository / args.output
    _require_clean_worktree(repository)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "archive", "--format=zip", f"--output={output}", "HEAD"],
        cwd=repository,
        check=True,
    )
    _verify_archive(output)
    print(f"handoff archive: {output}")
    return 0


def _require_clean_worktree(repository: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repository, check=True, capture_output=True, text=True
    )
    if result.stdout.strip():
        raise RuntimeError("commit or stash changes before packaging; the archive contains HEAD only")


def _verify_archive(path: Path) -> None:
    unsafe = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            item = Path(name)
            if FORBIDDEN_PARTS.intersection(item.parts) or item.suffix.lower() in FORBIDDEN_SUFFIXES:
                unsafe.append(name)
                continue
            info = archive.getinfo(name)
            if not name.endswith("/") and info.file_size <= 2_000_000:
                content = archive.read(name)
                if any(pattern.search(content) for pattern in FORBIDDEN_CONTENT):
                    unsafe.append(name)
    if unsafe:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"handoff archive contains forbidden files: {unsafe}")


if __name__ == "__main__":
    raise SystemExit(main())
