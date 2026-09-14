import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.bootstrap import configured_admin_app
from ncs_backend.shared.config import Settings


if __name__ == "__main__":
    configured_admin_app(Settings.from_env()).run(host="127.0.0.1", port=5001)
