"""Load and validate JSON input files into domain models."""
import json
from pathlib import Path

from pydantic import ValidationError

from timetabling.models.domain import HardBlocksInput, SoftBlocksInput


def load_hard_blocks(path: str | Path) -> HardBlocksInput:
    """Parse and validate hard_blocks.json."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Hard blocks file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return HardBlocksInput.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid hard_blocks.json:\n{exc}") from exc


def load_soft_blocks(path: str | Path) -> SoftBlocksInput:
    """Parse and validate soft_blocks.json."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Soft blocks file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SoftBlocksInput.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid soft_blocks.json:\n{exc}") from exc
