"""
Pydantic domain models — validated representations of the JSON input.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# School calendar
# ---------------------------------------------------------------------------

class SlotDef(BaseModel):
    id: int = Field(gt=0, description="Global slot number (1-based)")
    label: str = Field(description="Human-readable time label, e.g. '07:00'")


class SchoolConfig(BaseModel):
    days: list[str] = Field(
        min_length=1,
        description="Ordered list of school days, e.g. ['Monday', ..., 'Friday']",
    )
    slots: list[SlotDef] = Field(
        min_length=1,
        description="All possible time slots defined for the school",
    )

    @model_validator(mode="after")
    def unique_slot_ids(self) -> "SchoolConfig":
        ids = [s.id for s in self.slots]
        if len(ids) != len(set(ids)):
            raise ValueError("slot ids must be unique")
        return self


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

class Teacher(BaseModel):
    id: str
    name: str
    subjects: list[str] = Field(min_length=1, description="List of subject IDs this teacher can teach")


class Subject(BaseModel):
    id: str
    name: str


class Class(BaseModel):
    id: str
    name: str
    level: str = Field(default="", description="e.g. 'fundamental', 'medio'")
    available_slots: list[int] = Field(
        min_length=1,
        description="Slot IDs (from school.slots) that this class attends",
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

        for req in self.requirements:
            if req.class_id not in class_ids:
                raise ValueError(f"Requirement references unknown class '{req.class_id}'")
            if req.subject_id not in subject_ids:
                raise ValueError(f"Requirement references unknown subject '{req.subject_id}'")
            if req.teacher_id not in teacher_ids:
                raise ValueError(f"Requirement references unknown teacher '{req.teacher_id}'")

        for cls in self.classes:
            bad = set(cls.available_slots) - slot_ids
            if bad:
                raise ValueError(f"Class '{cls.id}' references unknown slot ids: {bad}")

        for hb in self.hard_blocks:
            if hb.day not in day_set:
                raise ValueError(f"Hard block references unknown day '{hb.day}'")
            if hb.slot not in slot_ids:
                raise ValueError(f"Hard block references unknown slot '{hb.slot}'")

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
