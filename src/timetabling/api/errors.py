"""
Centralised error helpers for the API.

All error responses follow the shape:  {"error": "<human-readable message>"}
"""
from __future__ import annotations

from flask import Flask, jsonify
from pydantic import ValidationError


def err(message: str, status: int):
    """Return a JSON error response."""
    return jsonify({"error": message}), status


def bad_request(message: str):
    return err(message, 400)


def not_found(message: str):
    return err(message, 404)


def conflict(message: str):
    return err(message, 409)


def validation_error(exc: ValidationError):
    """Flatten pydantic validation errors into a readable 400 response."""
    details = "; ".join(
        f"{' → '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    return bad_request(details)


def register_error_handlers(app: Flask) -> None:
    """Attach global error handlers to the Flask app."""

    @app.errorhandler(400)
    def handle_400(e):
        return err(str(e), 400)

    @app.errorhandler(404)
    def handle_404(e):
        return err(str(e), 404)

    @app.errorhandler(405)
    def handle_405(e):
        return err(str(e), 405)

    @app.errorhandler(500)
    def handle_500(e):
        return err("Internal server error", 500)
