"""
CSV exporter — writes one CSV file per class.

Output format (columns: Slot, Label, <day1>, <day2>, ...):

  Slot,Label,Monday,Tuesday,Wednesday,Thursday,Friday
  1,07:00,Math - Ana Silva,,Portuguese - Carlos Lima,,
  2,08:00,,Physics - Ana Silva,,,

Only slots declared in the class's available_slots appear as rows.
Empty cells mean no lesson is scheduled at that (day, slot) for the class.
"""
from __future__ import annotations

import csv
from pathlib import Path

from timetabling.models.domain import HardBlocksInput, Schedule


def export(schedule: Schedule, problem: HardBlocksInput, output_dir: str | Path) -> list[Path]:
    """
    Write one CSV per class into output_dir.

    Returns the list of file paths written.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build lookup: slot_id → label
    slot_label: dict[int, str] = {s.id: s.label for s in problem.school.slots}

    # Build lookup: class_id → class name
    class_name: dict[str, str] = {c.id: c.name for c in problem.classes}

    # Build lookup: (class_id, day, slot) → "Subject - Teacher Name"
    teacher_name: dict[str, str] = {t.id: t.name for t in problem.teachers}
    subject_name: dict[str, str] = {s.id: s.name for s in problem.subjects}

    cell: dict[tuple[str, str, int], str] = {}
    for entry in schedule.entries:
        key = (entry.class_id, entry.day, entry.slot)
        cell[key] = f"{subject_name[entry.subject_id]} - {teacher_name[entry.teacher_id]}"

    days = problem.school.days
    written: list[Path] = []

    for cls in problem.classes:
        cid = cls.id
        safe_name = cls.name.replace("/", "-").replace(" ", "_")
        filepath = output_dir / f"{safe_name}.csv"

        with filepath.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Slot", "Label"] + days)

            for slot_id in sorted(cls.available_slots):
                label = slot_label.get(slot_id, str(slot_id))
                row = [slot_id, label]
                for day in days:
                    row.append(cell.get((cid, day, slot_id), ""))
                writer.writerow(row)

        written.append(filepath)

    return written
