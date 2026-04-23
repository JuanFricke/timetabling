"""
Endpoints for soft preferences (soft_blocks).

GET /api/soft-blocks        — return full list
PUT /api/soft-blocks        — replace full list
POST /api/soft-blocks       — append a single soft block
DELETE /api/soft-blocks     — remove by exact match (JSON body)
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import verify_jwt_in_request
from pydantic import ValidationError

import timetabling.api.state as state
from timetabling.api.errors import bad_request, not_found, validation_error
from timetabling.models.domain import SoftBlocksInput

bp = Blueprint("preferences", __name__, url_prefix="/api")


@bp.before_request
def _require_jwt():
    verify_jwt_in_request()


@bp.get("/soft-blocks")
def list_soft_blocks():
    soft = state.get_soft()
    return jsonify([sb.model_dump() for sb in soft.soft_blocks])


@bp.put("/soft-blocks")
def replace_soft_blocks():
    """Replace the entire soft_blocks list."""
    data = request.get_json(silent=True)
    if data is None:
        return bad_request("Request body must be JSON")
    if not isinstance(data, list):
        return bad_request("Expected a JSON array of soft blocks")
    try:
        new_soft = SoftBlocksInput.model_validate({"soft_blocks": data})
    except ValidationError as exc:
        return validation_error(exc)
    state.set_soft(new_soft)
    return jsonify([sb.model_dump() for sb in new_soft.soft_blocks]), 200


@bp.post("/soft-blocks")
def add_soft_block():
    """Append a single soft block."""
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    soft = state.get_soft()
    existing = [sb.model_dump() for sb in soft.soft_blocks]
    existing.append(data)
    try:
        new_soft = SoftBlocksInput.model_validate({"soft_blocks": existing})
    except ValidationError as exc:
        return validation_error(exc)
    state.set_soft(new_soft)
    return jsonify(data), 201


@bp.delete("/soft-blocks")
def delete_soft_block():
    """Remove a soft block by exact match (full JSON body)."""
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    soft = state.get_soft()
    blocks = [sb.model_dump() for sb in soft.soft_blocks]
    before = len(blocks)
    blocks = [b for b in blocks if b != data]
    if len(blocks) == before:
        return not_found("Soft block not found")
    try:
        new_soft = SoftBlocksInput.model_validate({"soft_blocks": blocks})
    except ValidationError as exc:
        return validation_error(exc)
    state.set_soft(new_soft)
    return "", 204
