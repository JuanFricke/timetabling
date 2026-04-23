"""
Soft-constraint evaluator.

Returns the total weighted penalty for a given Schedule.
Lower score = better (penalty minimisation).

Supported soft block types:
  - teacher_preferred_slot   : +weight if teacher NOT teaching at that (day, slot)
  - class_preferred_slot     : +weight if class NOT teaching at that (day, slot)
  - avoid_last_slot          : +weight for each lesson assigned to the last slot of
                               a class's available_slots on any day
  - avoid_teacher_gaps       : +weight for each idle slot between the first and last
                               lesson of a teacher on a day
  - avoid_class_gaps         : +weight for each idle slot between the first and last
                               lesson of a class on a day
  - subject_spread           : +weight for each day a subject appears more than once
                               for a class (prefers lessons spread across days)
  - max_consecutive          : +weight for each run of lessons exceeding max_consecutive
                               for a class on a day
"""
from __future__ import annotations

from collections import defaultdict

from timetabling.models.domain import (
    AvoidClassGapsBlock,
    AvoidLastSlotBlock,
    AvoidTeacherGapsBlock,
    ClassPreferredSlotBlock,
    HardBlocksInput,
    MaxConsecutiveBlock,
    Schedule,
    ScheduleEntry,
    SoftBlocksInput,
    SubjectSpreadBlock,
    TeacherPreferredSlotBlock,
)


def _build_indexes(schedule: Schedule):
    """Pre-compute index structures for fast lookup."""
    # (class_id, day) → sorted list of slot ids
    class_day_slots: dict[tuple[str, str], list[int]] = defaultdict(list)
    # (teacher_id, day) → sorted list of slot ids
    teacher_day_slots: dict[tuple[str, str], list[int]] = defaultdict(list)
    # (class_id, day) → set of slot ids with a lesson
    class_day_slot_set: dict[tuple[str, str], set[int]] = defaultdict(set)
    # (teacher_id, day, slot) → True if teaching
    teacher_teaching: set[tuple[str, str, int]] = set()
    # (class_id, day, slot) → True if occupied
    class_occupied: set[tuple[str, str, int]] = set()
    # (class_id, subject_id, day) → count of lessons
    class_subj_day: dict[tuple[str, str, str], int] = defaultdict(int)

    for e in schedule.entries:
        class_day_slots[(e.class_id, e.day)].append(e.slot)
        teacher_day_slots[(e.teacher_id, e.day)].append(e.slot)
        class_day_slot_set[(e.class_id, e.day)].add(e.slot)
        teacher_teaching.add((e.teacher_id, e.day, e.slot))
        class_occupied.add((e.class_id, e.day, e.slot))
        class_subj_day[(e.class_id, e.subject_id, e.day)] += 1

    # Sort slot lists
    for k in class_day_slots:
        class_day_slots[k].sort()
    for k in teacher_day_slots:
        teacher_day_slots[k].sort()

    return (
        class_day_slots,
        teacher_day_slots,
        class_day_slot_set,
        teacher_teaching,
        class_occupied,
        class_subj_day,
    )


def _last_slot_per_class(problem: HardBlocksInput) -> dict[str, int]:
    """Map class_id → maximum slot id in its available_slots."""
    return {cls.id: max(cls.available_slots) for cls in problem.classes}


def score(
    schedule: Schedule,
    soft: SoftBlocksInput,
    problem: HardBlocksInput,
) -> int:
    """Compute total weighted penalty (lower is better)."""
    (
        class_day_slots,
        teacher_day_slots,
        class_day_slot_set,
        teacher_teaching,
        class_occupied,
        class_subj_day,
    ) = _build_indexes(schedule)

    last_slot = _last_slot_per_class(problem)
    days = problem.school.days
    penalty = 0

    for sb in soft.soft_blocks:

        if isinstance(sb, TeacherPreferredSlotBlock):
            # Reward if teacher IS teaching at preferred slot; penalise otherwise
            if (sb.teacher_id, sb.day, sb.slot) not in teacher_teaching:
                penalty += sb.weight

        elif isinstance(sb, ClassPreferredSlotBlock):
            if (sb.class_id, sb.day, sb.slot) not in class_occupied:
                penalty += sb.weight

        elif isinstance(sb, AvoidLastSlotBlock):
            ls = last_slot.get(sb.class_id)
            if ls is None:
                continue
            for day in days:
                if ls in class_day_slot_set.get((sb.class_id, day), set()):
                    penalty += sb.weight

        elif isinstance(sb, AvoidTeacherGapsBlock):
            for day in days:
                slots = teacher_day_slots.get((sb.teacher_id, day), [])
                if len(slots) < 2:
                    continue
                # Gaps = (last - first + 1) - number_of_lessons
                span = slots[-1] - slots[0] + 1
                gaps = span - len(slots)
                penalty += gaps * sb.weight

        elif isinstance(sb, AvoidClassGapsBlock):
            for day in days:
                slots = class_day_slots.get((sb.class_id, day), [])
                if len(slots) < 2:
                    continue
                span = slots[-1] - slots[0] + 1
                gaps = span - len(slots)
                penalty += gaps * sb.weight

        elif isinstance(sb, SubjectSpreadBlock):
            for day in days:
                count = class_subj_day.get((sb.class_id, sb.subject_id, day), 0)
                if count > 1:
                    penalty += (count - 1) * sb.weight

        elif isinstance(sb, MaxConsecutiveBlock):
            for day in days:
                slots = sorted(class_day_slots.get((sb.class_id, day), []))
                if not slots:
                    continue
                # Count max consecutive run length
                run = 1
                for i in range(1, len(slots)):
                    if slots[i] == slots[i - 1] + 1:
                        run += 1
                    else:
                        run = 1
                    if run > sb.max_consecutive:
                        penalty += sb.weight

    return penalty
