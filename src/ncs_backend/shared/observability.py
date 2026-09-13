"""Small observability helpers shared by the Flask applications."""

from __future__ import annotations

from uuid import uuid4

from flask import g, request


def install_request_context(app) -> None:
    @app.before_request
    def assign_trace_id() -> None:
        g.trace_id = request.headers.get("X-Trace-Id") or uuid4().hex

    @app.after_request
    def attach_trace_id(response):
        response.headers["X-Trace-Id"] = g.get("trace_id", "")
        return response
