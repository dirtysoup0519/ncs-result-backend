import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.bootstrap import configured_query_app
from ncs_backend.shared.config import Settings
from ncs_backend.shared.local_config import load_local_config


if __name__ == "__main__":
    load_local_config()
    settings = Settings.from_env()
    configured_query_app(settings).run(host=settings.query_host, port=settings.query_port)
