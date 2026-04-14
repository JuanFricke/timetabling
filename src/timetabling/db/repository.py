"""Database repository — persist and query timetabling data."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from timetabling.db.schema import (
    Base,
    ClassRow,
    ClassSlotRow,
    RequirementRow,
    ScheduleEntryRow,
    ScheduleRunRow,
    SlotRow,
    SubjectRow,
    TeacherRow,
    TeacherSubjectRow,
)
from timetabling.models.domain import HardBlocksInput, Schedule, ScheduleEntry


def get_engine(database_url: str):
    return create_engine(database_url, echo=False, pool_pre_ping=True)


def create_tables(engine) -> None:
    """Create all tables (idempotent — uses CREATE IF NOT EXISTS via SQLAlchemy)."""
    Base.metadata.create_all(engine)


def wait_for_db(database_url: str, retries: int = 20, delay: float = 3.0) -> None:
    """Block until the database is reachable."""
    import time

    engine = get_engine(database_url)
    for attempt in range(retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(delay)


def upsert_problem(session: Session, problem: HardBlocksInput) -> None:
    """Insert or update all static problem data (teachers, classes, etc.)."""

    # Slots
    existing_slots = {r.id for r in session.query(SlotRow).all()}
    for slot in problem.school.slots:
        if slot.id not in existing_slots:
            session.add(SlotRow(id=slot.id, label=slot.label))

    # Subjects
    existing_subjects = {r.id for r in session.query(SubjectRow).all()}
    for subj in problem.subjects:
        if subj.id not in existing_subjects:
            session.add(SubjectRow(id=subj.id, name=subj.name))

    # Teachers
    existing_teachers = {r.id for r in session.query(TeacherRow).all()}
    for teacher in problem.teachers:
        if teacher.id not in existing_teachers:
            session.add(TeacherRow(id=teacher.id, name=teacher.name))
            for subj_id in teacher.subjects:
                session.add(TeacherSubjectRow(teacher_id=teacher.id, subject_id=subj_id))

    # Classes
    existing_classes = {r.id for r in session.query(ClassRow).all()}
    for cls in problem.classes:
        if cls.id not in existing_classes:
            session.add(ClassRow(id=cls.id, name=cls.name, level=cls.level))
            for slot_id in cls.available_slots:
                session.add(ClassSlotRow(class_id=cls.id, slot_id=slot_id))

    # Requirements
    session.query(RequirementRow).delete()
    for req in problem.requirements:
        session.add(
            RequirementRow(
                class_id=req.class_id,
                subject_id=req.subject_id,
                teacher_id=req.teacher_id,
                hours_per_week=req.hours_per_week,
            )
        )

    session.flush()


def save_schedule(
    session: Session,
    schedule: Schedule,
    *,
    cp_feasible: bool,
    soft_score_initial: int | None,
    ls_iterations: int | None,
    notes: str | None = None,
) -> int:
    """Persist a schedule run and return the run id."""
    run = ScheduleRunRow(
        cp_feasible=cp_feasible,
        soft_score_initial=soft_score_initial,
        soft_score_final=schedule.soft_score,
        ls_iterations=ls_iterations,
        notes=notes,
    )
    session.add(run)
    session.flush()

    for entry in schedule.entries:
        session.add(
            ScheduleEntryRow(
                run_id=run.id,
                class_id=entry.class_id,
                subject_id=entry.subject_id,
                teacher_id=entry.teacher_id,
                day=entry.day,
                slot_id=entry.slot,
            )
        )

    session.flush()
    return run.id


def load_latest_schedule(session: Session) -> list[ScheduleEntry]:
    """Load entries from the most recent schedule run."""
    latest = (
        session.query(ScheduleRunRow)
        .order_by(ScheduleRunRow.created_at.desc())
        .first()
    )
    if latest is None:
        return []
    return [
        ScheduleEntry(
            class_id=e.class_id,
            subject_id=e.subject_id,
            teacher_id=e.teacher_id,
            day=e.day,
            slot=e.slot_id,
        )
        for e in latest.entries
    ]
