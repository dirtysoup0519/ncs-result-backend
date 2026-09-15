import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verify_dual_entry_idempotency import main  # noqa: E402


def test_dual_entry_idempotency_acceptance_passes_on_sqlite(tmp_path):
    exit_code = main([
        "--sqlite", str(tmp_path / "acceptance.sqlite"),
        "--work-dir", str(tmp_path / "work"),
    ])
    assert exit_code == 0
