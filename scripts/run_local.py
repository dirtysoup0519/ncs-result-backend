import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.local_database import initialize_local_database
from ncs_backend.bootstrap import configured_admin_app, configured_db_console_app, configured_query_app
from ncs_backend.shared.config import Settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one NCS service against the local development database")
    parser.add_argument("service", choices=("admin", "query", "console"))
    parser.add_argument("--sqlite", type=Path, default=Path(".local/ncs.sqlite"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)

    database = args.sqlite.resolve()
    initialize_local_database(database)
    settings = Settings(database_url=f"sqlite:///{database.as_posix()}")
    factories = {
        "admin": (configured_admin_app, 5001),
        "query": (configured_query_app, 5000),
        "console": (configured_db_console_app, 5002),
    }
    factory, default_port = factories[args.service]
    factory(settings).run(host=args.host, port=args.port or default_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
