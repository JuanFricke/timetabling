"""
CRUD endpoints for the problem definition:
  school config, teachers, subjects, classes, requirements, hard blocks.

All mutations rebuild a new HardBlocksInput and write it back to state,
which triggers Pydantic cross-validation automatically.
"""
from __future__ import annotations

from copy import deepcopy

from flask import Blueprint, jsonify, request
from flask_jwt_extended import verify_jwt_in_request
from pydantic import ValidationError

import timetabling.api.state as state
from timetabling.api.errors import bad_request, not_found, validation_error
from timetabling.models.domain import (
    ClassUnavailableBlock,
    HardBlocksInput,
    TeacherUnavailableBlock,
)

bp = Blueprint("problem", __name__, url_prefix="/api")


@bp.before_request
def _require_jwt():
    verify_jwt_in_request()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dump(obj) -> dict:
    """Pydantic model → plain dict (no extra fields)."""
    return obj.model_dump()


def _rebuild(problem: HardBlocksInput) -> HardBlocksInput:
    """Re-validate the mutated problem (triggers cross_validate)."""
    try:
        return HardBlocksInput.model_validate(problem.model_dump())
    except ValidationError as exc:
        raise exc


# ---------------------------------------------------------------------------
# Full problem dump / replace
# ---------------------------------------------------------------------------

@bp.get("/problem")
def get_problem():
    p = state.get_problem()
    return jsonify(_dump(p))


@bp.put("/problem")
def put_problem():
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    try:
        new_p = HardBlocksInput.model_validate(data)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return jsonify(_dump(new_p)), 200


# ---------------------------------------------------------------------------
# School config
# ---------------------------------------------------------------------------

@bp.get("/school")
def get_school():
    return jsonify(_dump(state.get_problem().school))


@bp.put("/school")
def put_school():
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    raw["school"] = data
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return jsonify(_dump(new_p.school)), 200


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

@bp.get("/teachers")
def list_teachers():
    return jsonify([_dump(t) for t in state.get_problem().teachers])


@bp.post("/teachers")
def create_teacher():
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    raw["teachers"].append(data)
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    added = next(t for t in new_p.teachers if t.id == data.get("id"))
    return jsonify(_dump(added)), 201


@bp.put("/teachers/<teacher_id>")
def update_teacher(teacher_id: str):
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    teachers = raw["teachers"]
    idx = next((i for i, t in enumerate(teachers) if t["id"] == teacher_id), None)
    if idx is None:
        return not_found(f"Teacher '{teacher_id}' not found")
    teachers[idx] = {**teachers[idx], **data, "id": teacher_id}
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    updated = next(t for t in new_p.teachers if t.id == teacher_id)
    return jsonify(_dump(updated)), 200


@bp.delete("/teachers/<teacher_id>")
def delete_teacher(teacher_id: str):
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    if not any(t["id"] == teacher_id for t in raw["teachers"]):
        return not_found(f"Teacher '{teacher_id}' not found")
    orphan_reqs = [r for r in raw["requirements"] if r["teacher_id"] == teacher_id]
    if orphan_reqs:
        return bad_request(
            f"Cannot delete teacher '{teacher_id}': "
            f"{len(orphan_reqs)} requirement(s) still reference this teacher"
        )
    raw["teachers"] = [t for t in raw["teachers"] if t["id"] != teacher_id]
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return "", 204


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

@bp.get("/subjects")
def list_subjects():
    return jsonify([_dump(s) for s in state.get_problem().subjects])


@bp.post("/subjects")
def create_subject():
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    raw["subjects"].append(data)
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    added = next(s for s in new_p.subjects if s.id == data.get("id"))
    return jsonify(_dump(added)), 201


@bp.put("/subjects/<subject_id>")
def update_subject(subject_id: str):
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    subjects = raw["subjects"]
    idx = next((i for i, s in enumerate(subjects) if s["id"] == subject_id), None)
    if idx is None:
        return not_found(f"Subject '{subject_id}' not found")
    subjects[idx] = {**subjects[idx], **data, "id": subject_id}
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    updated = next(s for s in new_p.subjects if s.id == subject_id)
    return jsonify(_dump(updated)), 200


@bp.delete("/subjects/<subject_id>")
def delete_subject(subject_id: str):
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    if not any(s["id"] == subject_id for s in raw["subjects"]):
        return not_found(f"Subject '{subject_id}' not found")
    orphan_reqs = [r for r in raw["requirements"] if r["subject_id"] == subject_id]
    if orphan_reqs:
        return bad_request(
            f"Cannot delete subject '{subject_id}': "
            f"{len(orphan_reqs)} requirement(s) still reference this subject"
        )
    raw["subjects"] = [s for s in raw["subjects"] if s["id"] != subject_id]
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return "", 204


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

@bp.get("/classes")
def list_classes():
    return jsonify([_dump(c) for c in state.get_problem().classes])


@bp.post("/classes")
def create_class():
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    raw["classes"].append(data)
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    added = next(c for c in new_p.classes if c.id == data.get("id"))
    return jsonify(_dump(added)), 201


@bp.put("/classes/<class_id>")
def update_class(class_id: str):
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    classes = raw["classes"]
    idx = next((i for i, c in enumerate(classes) if c["id"] == class_id), None)
    if idx is None:
        return not_found(f"Class '{class_id}' not found")
    classes[idx] = {**classes[idx], **data, "id": class_id}
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    updated = next(c for c in new_p.classes if c.id == class_id)
    return jsonify(_dump(updated)), 200


@bp.delete("/classes/<class_id>")
def delete_class(class_id: str):
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    if not any(c["id"] == class_id for c in raw["classes"]):
        return not_found(f"Class '{class_id}' not found")
    orphan_reqs = [r for r in raw["requirements"] if r["class_id"] == class_id]
    if orphan_reqs:
        return bad_request(
            f"Cannot delete class '{class_id}': "
            f"{len(orphan_reqs)} requirement(s) still reference this class"
        )
    raw["classes"] = [c for c in raw["classes"] if c["id"] != class_id]
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return "", 204


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

@bp.get("/requirements")
def list_requirements():
    p = state.get_problem()
    reqs = [_dump(r) for r in p.requirements]
    class_id = request.args.get("class_id")
    teacher_id = request.args.get("teacher_id")
    if class_id:
        reqs = [r for r in reqs if r["class_id"] == class_id]
    if teacher_id:
        reqs = [r for r in reqs if r["teacher_id"] == teacher_id]
    return jsonify(reqs)


@bp.post("/requirements")
def create_requirement():
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    raw["requirements"].append(data)
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return jsonify(data), 201


@bp.delete("/requirements")
def delete_requirement():
    """Remove by {class_id, subject_id, teacher_id} in the request body."""
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON with class_id, subject_id, teacher_id")
    cid = data.get("class_id")
    sid = data.get("subject_id")
    tid = data.get("teacher_id")
    if not (cid and sid and tid):
        return bad_request("Provide class_id, subject_id and teacher_id")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    before = len(raw["requirements"])
    raw["requirements"] = [
        r for r in raw["requirements"]
        if not (r["class_id"] == cid and r["subject_id"] == sid and r["teacher_id"] == tid)
    ]
    if len(raw["requirements"]) == before:
        return not_found("Requirement not found")
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return "", 204


# ---------------------------------------------------------------------------
# Hard blocks
# ---------------------------------------------------------------------------

@bp.get("/hard-blocks")
def list_hard_blocks():
    return jsonify([_dump(hb) for hb in state.get_problem().hard_blocks])


@bp.post("/hard-blocks")
def create_hard_block():
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    raw["hard_blocks"].append(data)
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return jsonify(data), 201


@bp.delete("/hard-blocks")
def delete_hard_block():
    """Remove a hard block by matching all its fields (passed as JSON body)."""
    data = request.get_json(silent=True)
    if not data:
        return bad_request("Request body must be JSON")
    p = deepcopy(state.get_problem())
    raw = _dump(p)
    before = len(raw["hard_blocks"])
    raw["hard_blocks"] = [hb for hb in raw["hard_blocks"] if hb != data]
    if len(raw["hard_blocks"]) == before:
        return not_found("Hard block not found")
    try:
        new_p = HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        return validation_error(exc)
    state.set_problem(new_p)
    return "", 204
