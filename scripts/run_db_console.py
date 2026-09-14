import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.db_console.app import create_app
from ncs_backend.shared.config import Settings


if __name__ == "__main__":
    settings = Settings.from_env()
    create_app(settings).run(host=settings.db_console_host, port=settings.db_console_port)
