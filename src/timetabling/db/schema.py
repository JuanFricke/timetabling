"""SQLAlchemy ORM table definitions."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SlotRow(Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(10), nullable=False)


class TeacherRow(Base):
    __tablename__ = "teachers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_links: Mapped[list["TeacherSubjectRow"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )


class SubjectRow(Base):
    __tablename__ = "subjects"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class TeacherSubjectRow(Base):
    __tablename__ = "teacher_subjects"

    teacher_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True
    )
    teacher: Mapped[TeacherRow] = relationship(back_populates="subject_links")


class ClassRow(Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=True)
    slot_links: Mapped[list["ClassSlotRow"]] = relationship(
        back_populates="class_", cascade="all, delete-orphan"
    )


class ClassSlotRow(Base):
    __tablename__ = "class_available_slots"

    class_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True
    )
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("slots.id", ondelete="CASCADE"), primary_key=True
    )
    class_: Mapped[ClassRow] = relationship(back_populates="slot_links")


class RequirementRow(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[str] = mapped_column(String(50), ForeignKey("classes.id", ondelete="CASCADE"))
    subject_id: Mapped[str] = mapped_column(String(50), ForeignKey("subjects.id", ondelete="CASCADE"))
    teacher_id: Mapped[str] = mapped_column(String(50), ForeignKey("teachers.id", ondelete="CASCADE"))
    hours_per_week: Mapped[int] = mapped_column(Integer, nullable=False)


class ScheduleRunRow(Base):
    __tablename__ = "schedule_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cp_feasible: Mapped[bool] = mapped_column(Boolean, default=False)
    soft_score_initial: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soft_score_final: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ls_iterations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entries: Mapped[list["ScheduleEntryRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ScheduleEntryRow(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_runs.id", ondelete="CASCADE"))
    class_id: Mapped[str] = mapped_column(String(50), ForeignKey("classes.id"))
    subject_id: Mapped[str] = mapped_column(String(50), ForeignKey("subjects.id"))
    teacher_id: Mapped[str] = mapped_column(String(50), ForeignKey("teachers.id"))
    day: Mapped[str] = mapped_column(String(20), nullable=False)
    slot_id: Mapped[int] = mapped_column(Integer, ForeignKey("slots.id"))
    run: Mapped[ScheduleRunRow] = relationship(back_populates="entries")

    __table_args__ = (
        UniqueConstraint("run_id", "class_id", "day", "slot_id", name="uq_class_slot"),
        UniqueConstraint("run_id", "teacher_id", "day", "slot_id", name="uq_teacher_slot"),
    )
