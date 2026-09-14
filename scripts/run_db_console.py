import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.bootstrap import configured_db_console_app
from ncs_backend.shared.config import Settings


if __name__ == "__main__":
    settings = Settings.from_env()
    configured_db_console_app(settings).run(host=settings.db_console_host, port=settings.db_console_port)
