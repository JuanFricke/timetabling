"""
Async solver endpoints.

POST /api/solve
    Validate current state, start a background thread, return {job_id}.
    Returns 409 if a solve is already running.
    Requires JWT — school_id is captured from the token and stored with the run.

GET /api/solve/<job_id>
    Poll job status.
    Response shape:
      {
        "job_id": "...",
        "status": "pending" | "running" | "done" | "error",
        "soft_score": <int>,           # only when done
        "iterations": <int>,           # only when done
        "schedule": { "entries": [...] },  # only when done
        "error": "..."                 # only when error
      }

GET /api/schedule
    Returns the last successfully completed schedule, or 404.

GET /api/schedule/by-class
    Same as above, grouped by class_id.
"""
from __future__ import annotations

import threading
import uuid
from typing import Any

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy.orm import Session

import timetabling.api.state as state
import timetabling.config as cfg
from timetabling.api.errors import bad_request, conflict, not_found
from timetabling.db.repository import (
    create_tables,
    get_engine,
    save_schedule,
    upsert_problem,
)
from timetabling.solver import cp_solver, local_search
from timetabling.solver.evaluator import score as eval_score

bp = Blueprint("solver", __name__, url_prefix="/api")


@bp.before_request
def _require_jwt():
    verify_jwt_in_request()


# ---------------------------------------------------------------------------
# In-process job store
# ---------------------------------------------------------------------------

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()

_last_schedule: dict | None = None
_last_schedule_lock = threading.Lock()

_solve_running = threading.Event()


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_solve(job_id: str, school_id: int | None) -> None:
    global _last_schedule

    def _update(patch: dict) -> None:
        with _jobs_lock:
            _jobs[job_id].update(patch)

    try:
        _update({"status": "running"})
        problem = state.get_problem()
        soft = state.get_soft()

        initial = cp_solver.solve(problem, time_limit_seconds=cfg.CP_TIME_LIMIT_SECONDS)
        if initial is None:
            _update({"status": "error", "error": "CP-SAT found no feasible solution"})
            return

        initial_score = eval_score(initial, soft, problem)
        initial.soft_score = initial_score

        final, iterations = local_search.improve(
            initial,
            soft,
            problem,
            max_iterations=cfg.LS_MAX_ITERATIONS,
        )

        # ── Persist to DB ─────────────────────────────────────────────────
        run_id = None
        try:
            engine = get_engine(cfg.DATABASE_URL)
            create_tables(engine)
            with Session(engine) as session:
                upsert_problem(session, problem)
                run_id = save_schedule(
                    session,
                    final,
                    cp_feasible=True,
                    soft_score_initial=initial_score,
                    ls_iterations=iterations,
                    school_id=school_id,
                )
                session.commit()
        except Exception as db_exc:
            # DB failure should not fail the solve response
            pass

        result = {
            "status": "done",
            "soft_score": final.soft_score,
            "iterations": iterations,
            "run_id": run_id,
            "schedule": final.model_dump(),
        }
        _update(result)

        with _last_schedule_lock:
            _last_schedule = result

    except Exception as exc:
        _update({"status": "error", "error": str(exc)})
    finally:
        _solve_running.clear()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.post("/solve")
def start_solve():
    if _solve_running.is_set():
        return conflict("A solve job is already running")

    problem = state.get_problem()
    if not problem.requirements:
        return bad_request(
            "No requirements defined — add classes, subjects and requirements before solving"
        )

    school_id_str = get_jwt_identity()
    school_id = int(school_id_str) if school_id_str else None

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"job_id": job_id, "status": "pending"}

    _solve_running.set()
    thread = threading.Thread(target=_run_solve, args=(job_id, school_id), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@bp.get("/solve/<job_id>")
def poll_solve(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return not_found(f"Job '{job_id}' not found")
    return jsonify(job), 200


@bp.get("/schedule")
def get_last_schedule():
    with _last_schedule_lock:
        if _last_schedule is None:
            return not_found("No completed schedule available yet")
        return jsonify(_last_schedule), 200


@bp.get("/schedule/by-class")
def get_schedule_by_class():
    with _last_schedule_lock:
        if _last_schedule is None:
            return not_found("No completed schedule available yet")
        entries = _last_schedule.get("schedule", {}).get("entries", [])

    by_class: dict[str, list] = {}
    for entry in entries:
        by_class.setdefault(entry["class_id"], []).append(entry)

    return jsonify(by_class), 200
