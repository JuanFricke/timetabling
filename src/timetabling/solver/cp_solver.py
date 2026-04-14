"""
Phase 1 — Constraint Programming with OR-Tools CP-SAT.

Finds an initial feasible schedule satisfying all hard constraints.
Variables: x[class_id, subject_id, teacher_id, day, slot] ∈ {0, 1}
  = 1  iff that (class, subject, teacher) is assigned to that (day, slot).

Hard constraints encoded:
  1. Each requirement (class, subject, teacher, hours_per_week) must be fulfilled exactly.
  2. A class can have at most one lesson per (day, slot).
  3. A teacher can teach at most one class per (day, slot).
  4. A class may only be scheduled in its declared available_slots.
  5. Teacher-unavailable hard blocks: block specific (teacher, day, slot).
  6. Class-unavailable hard blocks: block specific (class, day, slot).
"""
from __future__ import annotations

from ortools.sat.python import cp_model

from timetabling.models.domain import (
    ClassUnavailableBlock,
    HardBlocksInput,
    Schedule,
    ScheduleEntry,
    TeacherUnavailableBlock,
)


def solve(problem: HardBlocksInput, time_limit_seconds: int = 60) -> Schedule | None:
    """
    Run CP-SAT to find a feasible schedule.

    Returns a Schedule if feasible, or None if no solution was found within
    the time limit.
    """
    model = cp_model.CpModel()

    days = problem.school.days
    slot_ids = {s.id for s in problem.school.slots}

    # Build lookup structures
    class_available: dict[str, set[int]] = {
        cls.id: set(cls.available_slots) for cls in problem.classes
    }
    teacher_subjects: dict[str, set[str]] = {
        t.id: set(t.subjects) for t in problem.teachers
    }

    # Collect blocked (teacher, day, slot) and (class, day, slot) pairs
    blocked_teacher: set[tuple[str, str, int]] = set()
    blocked_class: set[tuple[str, str, int]] = set()
    for hb in problem.hard_blocks:
        if isinstance(hb, TeacherUnavailableBlock):
            blocked_teacher.add((hb.teacher_id, hb.day, hb.slot))
        elif isinstance(hb, ClassUnavailableBlock):
            blocked_class.add((hb.class_id, hb.day, hb.slot))

    # ---------------------------------------------------------------------------
    # Decision variables
    # x[(class_id, subject_id, teacher_id, day, slot)] = BoolVar
    # Only created for valid (class × available_slot) combinations.
    # ---------------------------------------------------------------------------
    x: dict[tuple[str, str, str, str, int], cp_model.IntVar] = {}

    for req in problem.requirements:
        cid, sid, tid = req.class_id, req.subject_id, req.teacher_id

        # Teacher must be qualified
        if sid not in teacher_subjects.get(tid, set()):
            raise ValueError(
                f"Teacher '{tid}' is not qualified to teach subject '{sid}' "
                f"(required for class '{cid}')"
            )

        for day in days:
            for slot in class_available.get(cid, set()):
                if (tid, day, slot) in blocked_teacher:
                    continue
                if (cid, day, slot) in blocked_class:
                    continue
                key = (cid, sid, tid, day, slot)
                x[key] = model.new_bool_var(f"x_{cid}_{sid}_{tid}_{day}_{slot}")

    # ---------------------------------------------------------------------------
    # Constraint 1 — fulfil weekly hours for each requirement exactly
    # ---------------------------------------------------------------------------
    for req in problem.requirements:
        cid, sid, tid = req.class_id, req.subject_id, req.teacher_id
        vars_for_req = [
            x[k] for k in x if k[0] == cid and k[1] == sid and k[2] == tid
        ]
        if not vars_for_req:
            raise ValueError(
                f"No feasible (day, slot) combination found for requirement "
                f"class={cid} subject={sid} teacher={tid}. "
                f"Check available_slots and hard blocks."
            )
        model.add(sum(vars_for_req) == req.hours_per_week)

    # ---------------------------------------------------------------------------
    # Constraint 2 — a class has at most one lesson per (day, slot)
    # ---------------------------------------------------------------------------
    for cls in problem.classes:
        cid = cls.id
        for day in days:
            for slot in cls.available_slots:
                vars_at_slot = [
                    x[k]
                    for k in x
                    if k[0] == cid and k[3] == day and k[4] == slot
                ]
                if vars_at_slot:
                    model.add(sum(vars_at_slot) <= 1)

    # ---------------------------------------------------------------------------
    # Constraint 3 — a teacher teaches at most one class per (day, slot)
    # ---------------------------------------------------------------------------
    for teacher in problem.teachers:
        tid = teacher.id
        for day in days:
            for slot in slot_ids:
                vars_for_teacher = [
                    x[k]
                    for k in x
                    if k[2] == tid and k[3] == day and k[4] == slot
                ]
                if vars_for_teacher:
                    model.add(sum(vars_for_teacher) <= 1)

    # ---------------------------------------------------------------------------
    # Solve
    # ---------------------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_workers = 4  # parallel search workers

    status = solver.solve(model)

    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return None

    entries: list[ScheduleEntry] = []
    for key, var in x.items():
        if solver.value(var) == 1:
            cid, sid, tid, day, slot = key
            entries.append(
                ScheduleEntry(
                    class_id=cid,
                    subject_id=sid,
                    teacher_id=tid,
                    day=day,
                    slot=slot,
                )
            )

    return Schedule(entries=entries)
