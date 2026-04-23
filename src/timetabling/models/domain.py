"""
Pydantic domain models — validated representations of the JSON input.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, computed_field, model_validator


# ---------------------------------------------------------------------------
# Helpers — time parsing
# ---------------------------------------------------------------------------

def _parse_hhmm(time_str: str) -> int:
    """Parse 'HH:MM' into total minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _fmt_hhmm(minutes: int) -> str:
    """Format total minutes since midnight as 'HH:MM'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---------------------------------------------------------------------------
# School calendar
# ---------------------------------------------------------------------------

class SlotDef(BaseModel):
    id: int = Field(gt=0, description="Global slot number (1-based)")
    label: str = Field(description="Human-readable time label, e.g. '07:00'")


class BreakDef(BaseModel):
    after_period: int = Field(gt=0, description="Insert break after this many periods within the block")
    duration_minutes: int = Field(gt=0)


class BlockDef(BaseModel):
    name: str = Field(description="Block name, e.g. 'morning' or 'afternoon'")
    start_time: str = Field(description="Start time of the first period, 'HH:MM'")
    period_duration_minutes: int = Field(gt=0, default=60)
    periods: int = Field(gt=0, description="Number of teaching periods in this block")
    breaks: list[BreakDef] = Field(default_factory=list)


class SchoolConfig(BaseModel):
    days: list[str] = Field(
        min_length=1,
        description="Ordered list of school days, e.g. ['Monday', ..., 'Friday']",
    )
    blocks: list[BlockDef] = Field(
        min_length=1,
        description="Ordered teaching blocks that make up the school day",
    )
    lunch_duration_minutes: int = Field(
        default=0,
        ge=0,
        description="Duration of the lunch break between blocks (informational)",
    )

    @computed_field
    @property
    def slots(self) -> list[SlotDef]:
        """Derive sequential SlotDef entries from all blocks."""
        result: list[SlotDef] = []
        slot_id = 1
        for block in self.blocks:
            current = _parse_hhmm(block.start_time)
            break_map = {b.after_period: b.duration_minutes for b in block.breaks}
            for p in range(1, block.periods + 1):
                result.append(SlotDef(id=slot_id, label=_fmt_hhmm(current)))
                slot_id += 1
                current += block.period_duration_minutes
                current += break_map.get(p, 0)
        return result

    def slots_for_block(self, block_name: str) -> list[int]:
        """Return slot IDs belonging to the named block."""
        result: list[int] = []
        slot_id = 1
        for block in self.blocks:
            block_slot_ids = list(range(slot_id, slot_id + block.periods))
            if block.name == block_name:
                result.extend(block_slot_ids)
            slot_id += block.periods
        return result


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

class Teacher(BaseModel):
    id: str
    name: str
    subjects: list[str] = Field(min_length=1, description="List of subject IDs this teacher can teach")
    min_hours_per_week: int | None = Field(
        default=None,
        ge=0,
        description="Minimum total weekly teaching hours across all assignments",
    )
    max_hours_per_week: int | None = Field(
        default=None,
        ge=0,
        description="Maximum total weekly teaching hours across all assignments",
    )


class Subject(BaseModel):
    id: str
    name: str
    category: str = Field(
        default="",
        description="Knowledge area, e.g. 'exatas', 'humanas', 'biologicas'",
    )


class Class(BaseModel):
    id: str
    name: str
    level: str = Field(default="", description="e.g. 'fundamental', 'medio'")
    shift: Literal["morning", "afternoon", "full"] = Field(
        default="full",
        description="Which school blocks this class attends; available_slots is derived automatically",
    )
    available_slots: list[int] = Field(
        default_factory=list,
        description="Slot IDs derived from shift + SchoolConfig; do not set manually",
    )


class Requirement(BaseModel):
    class_id: str
    subject_id: str
    teacher_id: str
    hours_per_week: int = Field(gt=0)


# ---------------------------------------------------------------------------
# Hard block types
# ---------------------------------------------------------------------------

class TeacherUnavailableBlock(BaseModel):
    type: Literal["teacher_unavailable"]
    teacher_id: str
    day: str
    slot: int


class ClassUnavailableBlock(BaseModel):
    type: Literal["class_unavailable"]
    class_id: str
    day: str
    slot: int


HardBlock = Annotated[
    Union[TeacherUnavailableBlock, ClassUnavailableBlock],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Soft block types
# ---------------------------------------------------------------------------

class TeacherPreferredSlotBlock(BaseModel):
    type: Literal["teacher_preferred_slot"]
    teacher_id: str
    day: str
    slot: int
    weight: int = Field(gt=0)


class ClassPreferredSlotBlock(BaseModel):
    type: Literal["class_preferred_slot"]
    class_id: str
    day: str
    slot: int
    weight: int = Field(gt=0)


class AvoidLastSlotBlock(BaseModel):
    """Penalise scheduling lessons at the last slot of a class's day."""
    type: Literal["avoid_last_slot"]
    class_id: str
    weight: int = Field(gt=0)


class AvoidTeacherGapsBlock(BaseModel):
    """Penalise idle slots between lessons in a teacher's day."""
    type: Literal["avoid_teacher_gaps"]
    teacher_id: str
    weight: int = Field(gt=0)


class AvoidClassGapsBlock(BaseModel):
    """Penalise idle slots between the first and last lesson of a class on a day."""
    type: Literal["avoid_class_gaps"]
    class_id: str
    weight: int = Field(gt=0)


class SubjectSpreadBlock(BaseModel):
    """Prefer that a subject's weekly lessons are spread across different days."""
    type: Literal["subject_spread"]
    class_id: str
    subject_id: str
    weight: int = Field(gt=0)


class MaxConsecutiveBlock(BaseModel):
    """Penalise more than N consecutive lessons for a class in a day."""
    type: Literal["max_consecutive"]
    class_id: str
    max_consecutive: int = Field(gt=0, default=3)
    weight: int = Field(gt=0)


SoftBlock = Annotated[
    Union[
        TeacherPreferredSlotBlock,
        ClassPreferredSlotBlock,
        AvoidLastSlotBlock,
        AvoidTeacherGapsBlock,
        AvoidClassGapsBlock,
        SubjectSpreadBlock,
        MaxConsecutiveBlock,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Top-level input models
# ---------------------------------------------------------------------------

class HardBlocksInput(BaseModel):
    school: SchoolConfig
    teachers: list[Teacher]
    classes: list[Class]
    subjects: list[Subject]
    requirements: list[Requirement]
    hard_blocks: list[HardBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def cross_validate(self) -> "HardBlocksInput":
        teacher_ids = {t.id for t in self.teachers}
        class_ids = {c.id for c in self.classes}
        subject_ids = {s.id for s in self.subjects}
        slot_ids = {s.id for s in self.school.slots}
        day_set = set(self.school.days)
        block_names = {b.name for b in self.school.blocks}

        # ── Derive available_slots for each class from its shift ──────────────
        for cls in self.classes:
            if cls.shift == "full":
                cls.available_slots = [s.id for s in self.school.slots]
            else:
                derived = self.school.slots_for_block(cls.shift)
                if not derived:
                    raise ValueError(
                        f"Class '{cls.id}' has shift='{cls.shift}' but no block named "
                        f"'{cls.shift}' exists in school.blocks. "
                        f"Available block names: {sorted(block_names)}"
                    )
                cls.available_slots = derived

        # ── Validate requirements reference known entities ────────────────────
        for req in self.requirements:
            if req.class_id not in class_ids:
                raise ValueError(f"Requirement references unknown class '{req.class_id}'")
            if req.subject_id not in subject_ids:
                raise ValueError(f"Requirement references unknown subject '{req.subject_id}'")
            if req.teacher_id not in teacher_ids:
                raise ValueError(f"Requirement references unknown teacher '{req.teacher_id}'")

        # ── Validate hard blocks reference known days/slots ───────────────────
        for hb in self.hard_blocks:
            if hb.day not in day_set:
                raise ValueError(f"Hard block references unknown day '{hb.day}'")
            if hb.slot not in slot_ids:
                raise ValueError(f"Hard block references unknown slot '{hb.slot}'")

        # ── Teacher workload validation ───────────────────────────────────────
        teacher_hours: dict[str, int] = {}
        for req in self.requirements:
            teacher_hours[req.teacher_id] = teacher_hours.get(req.teacher_id, 0) + req.hours_per_week

        for teacher in self.teachers:
            assigned = teacher_hours.get(teacher.id, 0)
            if teacher.min_hours_per_week is not None and assigned < teacher.min_hours_per_week:
                raise ValueError(
                    f"Teacher '{teacher.name}' (id={teacher.id}) is assigned {assigned} h/week "
                    f"but min_hours_per_week={teacher.min_hours_per_week}."
                )
            if teacher.max_hours_per_week is not None and assigned > teacher.max_hours_per_week:
                raise ValueError(
                    f"Teacher '{teacher.name}' (id={teacher.id}) is assigned {assigned} h/week "
                    f"but max_hours_per_week={teacher.max_hours_per_week}."
                )

        # ── Slot capacity check: requirements must fill all available slots ───
        n_days = len(self.school.days)
        class_capacity: dict[str, int] = {
            cls.id: n_days * len(cls.available_slots) for cls in self.classes
        }
        class_hours: dict[str, int] = {}
        for req in self.requirements:
            class_hours[req.class_id] = class_hours.get(req.class_id, 0) + req.hours_per_week

        for cls in self.classes:
            capacity = class_capacity[cls.id]
            assigned = class_hours.get(cls.id, 0)
            if assigned != capacity:
                raise ValueError(
                    f"Class '{cls.name}' (id={cls.id}) has {len(cls.available_slots)} slots/day "
                    f"× {n_days} days = {capacity} slots/week, "
                    f"but requirements total {assigned} hours/week. "
                    f"{'Add' if assigned < capacity else 'Remove'} "
                    f"{abs(capacity - assigned)} hour(s) to fully fill all available slots."
                )

        return self


class SoftBlocksInput(BaseModel):
    soft_blocks: list[SoftBlock] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Solution representation (passed between solver phases)
# ---------------------------------------------------------------------------

class ScheduleEntry(BaseModel):
    class_id: str
    subject_id: str
    teacher_id: str
    day: str
    slot: int


class Schedule(BaseModel):
    """Final timetable produced by the solver."""
    entries: list[ScheduleEntry] = Field(default_factory=list)
    soft_score: int = 0

    def by_class(self) -> dict[str, list[ScheduleEntry]]:
        result: dict[str, list[ScheduleEntry]] = {}
        for e in self.entries:
            result.setdefault(e.class_id, []).append(e)
        return result
