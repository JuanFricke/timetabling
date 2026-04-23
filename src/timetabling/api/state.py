"""
In-memory state singleton for the API.

Holds the current HardBlocksInput and SoftBlocksInput. Initialized from the
JSON files on disk at first access; falls back to empty models if files are
missing or invalid. All mutations go through the set_* helpers which hold a
threading.Lock so concurrent Flask requests stay consistent.
"""
from __future__ import annotations

import threading
from pathlib import Path

import timetabling.config as cfg
from timetabling.models.domain import (
    HardBlocksInput,
    SchoolConfig,
    BlockDef,
    SoftBlocksInput,
)

_lock = threading.Lock()
_problem: HardBlocksInput | None = None
_soft: SoftBlocksInput | None = None


def _load_from_disk() -> tuple[HardBlocksInput | None, SoftBlocksInput | None]:
    """Try to hydrate state from the configured JSON paths."""
    try:
        from timetabling.io.json_loader import load_hard_blocks, load_soft_blocks
        problem = load_hard_blocks(cfg.HARD_BLOCKS_PATH)
        soft = load_soft_blocks(cfg.SOFT_BLOCKS_PATH)
        return problem, soft
    except Exception:
        return None, None


def _default_problem() -> HardBlocksInput:
    """Return a minimal valid HardBlocksInput with no entities."""
    school = SchoolConfig(
        days=["Segunda", "Terca", "Quarta", "Quinta", "Sexta"],
        blocks=[
            BlockDef(
                name="morning",
                start_time="07:00",
                period_duration_minutes=60,
                periods=4,
            )
        ],
    )
    return HardBlocksInput(
        school=school,
        teachers=[],
        classes=[],
        subjects=[],
        requirements=[],
        hard_blocks=[],
    )


def _default_soft() -> SoftBlocksInput:
    return SoftBlocksInput(soft_blocks=[])


def _ensure_loaded() -> None:
    """Load from disk on first access (called inside the lock)."""
    global _problem, _soft
    if _problem is None:
        p, s = _load_from_disk()
        _problem = p if p is not None else _default_problem()
        _soft = s if s is not None else _default_soft()


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def get_problem() -> HardBlocksInput:
    with _lock:
        _ensure_loaded()
        return _problem  # type: ignore[return-value]


def set_problem(problem: HardBlocksInput) -> None:
    global _problem
    with _lock:
        _ensure_loaded()
        _problem = problem


def get_soft() -> SoftBlocksInput:
    with _lock:
        _ensure_loaded()
        return _soft  # type: ignore[return-value]


def set_soft(soft: SoftBlocksInput) -> None:
    global _soft
    with _lock:
        _ensure_loaded()
        _soft = soft
