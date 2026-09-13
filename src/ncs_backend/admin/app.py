"""Flask application factory for the internal administration service."""

from __future__ import annotations

from flask import Flask, jsonify

from ncs_backend.shared.config import Settings
from ncs_backend.shared.errors import AppError
from ncs_backend.shared.observability import install_request_context


def create_app(settings: Settings | None = None) -> Flask:
    app = Flask(__name__)
    app.config["NCS_SETTINGS"] = settings or Settings.from_env()
    install_request_context(app)

    @app.get("/health/live")
    def live():
        return jsonify({"code": 0, "message": "ok", "data": {"status": "alive"}})

    @app.get("/health/ready")
    def ready():
        current: Settings = app.config["NCS_SETTINGS"]
        if not current.database_configured:
            return jsonify({"code": "DEPENDENCY_NOT_READY", "message": "database is not configured"}), 503
        return jsonify({"code": 0, "message": "ok", "data": {"status": "ready"}})

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(error.to_dict()), error.status_code

    return app
