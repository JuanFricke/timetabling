"""
Auth endpoints — register and login for schools.

POST /api/auth/register  {name, email, password}  → {token, school_id, name}
POST /api/auth/login     {email, password}         → {token, school_id, name}

Passwords are hashed with werkzeug.security (ships with Flask, no extra dep).
JWT tokens are signed with flask-jwt-extended; identity = school_id (int).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

import timetabling.config as cfg
from timetabling.api.errors import bad_request, conflict
from timetabling.db.repository import (
    create_school,
    create_tables,
    find_school_by_email,
    get_engine,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _get_session() -> Session:
    engine = get_engine(cfg.DATABASE_URL)
    create_tables(engine)
    return Session(engine)


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name:
        return bad_request("name is required")
    if not email or "@" not in email:
        return bad_request("valid email is required")
    if len(password) < 6:
        return bad_request("password must be at least 6 characters")

    pw_hash = generate_password_hash(password)

    try:
        with _get_session() as session:
            school = create_school(session, name=name, email=email, password_hash=pw_hash)
            session.commit()
            school_id = school.id
            school_name = school.name
    except IntegrityError:
        return conflict(f"Email '{email}' is already registered")

    token = create_access_token(identity=str(school_id))
    return jsonify({"token": token, "school_id": school_id, "name": school_name}), 201


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return bad_request("email and password are required")

    with _get_session() as session:
        school = find_school_by_email(session, email)
        if school is None or not check_password_hash(school.password_hash, password):
            return bad_request("Invalid email or password")
        school_id = school.id
        school_name = school.name

    token = create_access_token(identity=str(school_id))
    return jsonify({"token": token, "school_id": school_id, "name": school_name}), 200
