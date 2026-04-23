"""
Flask application factory.
"""
from __future__ import annotations

import timetabling.config as cfg
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from timetabling.api.errors import register_error_handlers


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = cfg.JWT_SECRET_KEY

    CORS(app)
    JWTManager(app)

    # ── Health (public) ───────────────────────────────────────────────────────
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ── Blueprints ────────────────────────────────────────────────────────────
    from timetabling.api.routes.auth import bp as auth_bp
    from timetabling.api.routes.problem import bp as problem_bp
    from timetabling.api.routes.preferences import bp as preferences_bp
    from timetabling.api.routes.solver import bp as solver_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(problem_bp)
    app.register_blueprint(preferences_bp)
    app.register_blueprint(solver_bp)

    register_error_handlers(app)

    return app
