"""
Phase 2 — Local Search improvement via Hill Climbing with random restarts.

Starts from the CP-SAT feasible solution and iteratively applies neighbourhood
moves that preserve hard-constraint feasibility while reducing the soft penalty.

Neighbourhood moves:
  - SWAP: exchange the (day, slot) of two entries belonging to the same class.
  - MOVE: relocate a single entry to a different (day, slot) for its class,
          provided that slot is in the class's available_slots and not blocked.

Feasibility checks after each move (hard constraints):
  1. Class collision: no two lessons for the same class at the same (day, slot).
  2. Teacher collision: no teacher teaches two classes at the same (day, slot).
  3. Class available_slots: the target slot must be in the class's available_slots.
  4. Hard blocks: teacher-unavailable and class-unavailable blocks.
"""
from __future__ import annotations

import random
from copy import deepcopy
from typing import Callable

from timetabling.models.domain import (
    ClassUnavailableBlock,
    HardBlocksInput,
    Schedule,
    ScheduleEntry,
    SoftBlocksInput,
    TeacherUnavailableBlock,
)
from timetabling.solver.evaluator import score


# ---------------------------------------------------------------------------
# Feasibility helpers
# ---------------------------------------------------------------------------

def _build_feasibility_sets(problem: HardBlocksInput):
    """Pre-compute block sets and available-slot sets for fast feasibility checks."""
    blocked_teacher: set[tuple[str, str, int]] = set()
    blocked_class: set[tuple[str, str, int]] = set()
    for hb in problem.hard_blocks:
        if isinstance(hb, TeacherUnavailableBlock):
            blocked_teacher.add((hb.teacher_id, hb.day, hb.slot))
        elif isinstance(hb, ClassUnavailableBlock):
            blocked_class.add((hb.class_id, hb.day, hb.slot))

    class_available: dict[str, set[int]] = {
        cls.id: set(cls.available_slots) for cls in problem.classes
    }
    return blocked_teacher, blocked_class, class_available


def _is_feasible(entries: list[ScheduleEntry], problem: HardBlocksInput,
                 blocked_teacher, blocked_class, class_available) -> bool:
    """Check all hard constraints on the full entry list."""
    class_slots: set[tuple[str, str, int]] = set()
    teacher_slots: set[tuple[str, str, int]] = set()

    for e in entries:
        # Available slots
        if e.slot not in class_available.get(e.class_id, set()):
            return False
        # Hard blocks
        if (e.teacher_id, e.day, e.slot) in blocked_teacher:
            return False
        if (e.class_id, e.day, e.slot) in blocked_class:
            return False
        # Collision — class
        ck = (e.class_id, e.day, e.slot)
        if ck in class_slots:
            return False
        class_slots.add(ck)
        # Collision — teacher
        tk = (e.teacher_id, e.day, e.slot)
        if tk in teacher_slots:
            return False
        teacher_slots.add(tk)

    return True


# ---------------------------------------------------------------------------
# Neighbourhood moves
# ---------------------------------------------------------------------------

def _swap_move(entries: list[ScheduleEntry], i: int, j: int) -> list[ScheduleEntry]:
    """Swap (day, slot) of entries i and j (must be same class_id)."""
    new_entries = list(entries)
    ei = ScheduleEntry(
        class_id=entries[i].class_id,
        subject_id=entries[i].subject_id,
        teacher_id=entries[i].teacher_id,
        day=entries[j].day,
        slot=entries[j].slot,
    )
    ej = ScheduleEntry(
        class_id=entries[j].class_id,
        subject_id=entries[j].subject_id,
        teacher_id=entries[j].teacher_id,
        day=entries[i].day,
        slot=entries[i].slot,
    )
    new_entries[i] = ei
    new_entries[j] = ej
    return new_entries


def _move_entry(
    entries: list[ScheduleEntry],
    idx: int,
    new_day: str,
    new_slot: int,
) -> list[ScheduleEntry]:
    """Move entry at idx to a new (day, slot)."""
    new_entries = list(entries)
    e = entries[idx]
    new_entries[idx] = ScheduleEntry(
        class_id=e.class_id,
        subject_id=e.subject_id,
        teacher_id=e.teacher_id,
        day=new_day,
        slot=new_slot,
    )
    return new_entries


# ---------------------------------------------------------------------------
# Main local search loop
# ---------------------------------------------------------------------------

def improve(
    initial: Schedule,
    soft: SoftBlocksInput,
    problem: HardBlocksInput,
    max_iterations: int = 5000,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[Schedule, int]:
    """
    Hill-climbing local search.

    Returns (improved_schedule, iterations_performed).
    The improved_schedule.soft_score holds the final penalty.
    """
    blocked_teacher, blocked_class, class_available = _build_feasibility_sets(problem)
    days = problem.school.days

    best_entries = list(initial.entries)
    best_score = score(Schedule(entries=best_entries), soft, problem)

    current_entries = best_entries[:]
    current_score = best_score

    # Index entries by class for faster swap selection
    class_indexes: dict[str, list[int]] = {}
    for idx, e in enumerate(current_entries):
        class_indexes.setdefault(e.class_id, []).append(idx)

    iterations_done = 0

    for iteration in range(max_iterations):
        improved = False

        # Choose a random move type
        move_type = random.choice(["swap", "move"])

        if move_type == "swap":
            # Pick a class with ≥2 entries and swap two random entries
            eligible = [cid for cid, idxs in class_indexes.items() if len(idxs) >= 2]
            if not eligible:
                move_type = "move"
            else:
                cid = random.choice(eligible)
                i, j = random.sample(class_indexes[cid], 2)
                candidate = _swap_move(current_entries, i, j)

        if move_type == "move":
            # Pick a random entry and move it to a random (day, slot) for its class
            idx = random.randrange(len(current_entries))
            entry = current_entries[idx]
            avail = list(class_available.get(entry.class_id, set()))
            if not avail:
                iterations_done += 1
                continue
            new_day = random.choice(days)
            new_slot = random.choice(avail)
            if new_day == entry.day and new_slot == entry.slot:
                iterations_done += 1
                continue
            candidate = _move_entry(current_entries, idx, new_day, new_slot)

        if not _is_feasible(candidate, problem, blocked_teacher, blocked_class, class_available):
            iterations_done += 1
            continue

        candidate_score = score(Schedule(entries=candidate), soft, problem)

        if candidate_score < current_score:
            current_entries = candidate
            current_score = candidate_score
            improved = True

            # Re-build class index after move
            class_indexes = {}
            for i2, e2 in enumerate(current_entries):
                class_indexes.setdefault(e2.class_id, []).append(i2)

            if current_score < best_score:
                best_entries = current_entries[:]
                best_score = current_score

        if progress_callback and iteration % 500 == 0:
            progress_callback(iteration, current_score)

        iterations_done += 1

        if best_score == 0:
            break  # Optimal soft score reached

    return Schedule(entries=best_entries, soft_score=best_score), iterations_done
