"""
CLI entrypoint.

Usage:
    uv run python -m timetabling.main solve [OPTIONS]
    uv run python -m timetabling.main serve [OPTIONS]

solve options:
    --hard PATH     Path to hard_blocks.json  [default: from env / data/input/hard_blocks.json]
    --soft PATH     Path to soft_blocks.json  [default: from env / data/input/soft_blocks.json]
    --output DIR    Output directory for CSVs  [default: from env / data/output]
    --no-db         Skip MySQL persistence

serve options:
    --port PORT     Port to listen on  [default: 5000]
    --host HOST     Host to bind to   [default: 0.0.0.0]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import timetabling.config as cfg
from timetabling.io.csv_exporter import export
from timetabling.io.json_loader import load_hard_blocks, load_soft_blocks
from timetabling.models.domain import Schedule
from timetabling.solver import cp_solver, local_search
from timetabling.solver.evaluator import score

console = Console()


def _parse_args() -> dict:
    args = sys.argv[1:]
    opts: dict = {
        "command": None,
        "hard": cfg.HARD_BLOCKS_PATH,
        "soft": cfg.SOFT_BLOCKS_PATH,
        "output": cfg.OUTPUT_DIR,
        "no_db": False,
        "port": "5000",
        "host": "0.0.0.0",
    }

    if not args:
        _print_help()
        sys.exit(0)

    opts["command"] = args[0]
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--hard" and i + 1 < len(args):
            opts["hard"] = args[i + 1]
            i += 2
        elif a == "--soft" and i + 1 < len(args):
            opts["soft"] = args[i + 1]
            i += 2
        elif a == "--output" and i + 1 < len(args):
            opts["output"] = args[i + 1]
            i += 2
        elif a == "--no-db":
            opts["no_db"] = True
            i += 1
        elif a == "--port" and i + 1 < len(args):
            opts["port"] = args[i + 1]
            i += 2
        elif a == "--host" and i + 1 < len(args):
            opts["host"] = args[i + 1]
            i += 2
        else:
            i += 1

    return opts


def _print_help() -> None:
    console.print(
        Panel(
            "[bold]timetabling solve[/bold] [--hard PATH] [--soft PATH] "
            "[--output DIR] [--no-db]\n"
            "[bold]timetabling serve[/bold] [--host HOST] [--port PORT]",
            title="School Timetabling — Hybrid CP + Local Search",
        )
    )


def _print_summary(schedule: Schedule, problem, files: list[Path]) -> None:
    table = Table(title="Schedule Summary", show_lines=True)
    table.add_column("Class", style="cyan")
    table.add_column("Lessons", justify="right")

    by_class = schedule.by_class()
    for cls in problem.classes:
        entries = by_class.get(cls.id, [])
        table.add_row(cls.name, str(len(entries)))

    console.print(table)
    console.print(f"\n[green]Soft penalty score:[/green] {schedule.soft_score}")
    console.print("\n[bold]CSV files written:[/bold]")
    for f in files:
        console.print(f"  {f}")


def cmd_solve(opts: dict) -> None:
    # ── 1. Load & validate JSON ──────────────────────────────────────────────
    console.rule("[bold blue]Step 1 — Loading input")
    console.print(f"  hard_blocks : {opts['hard']}")
    console.print(f"  soft_blocks : {opts['soft']}")

    problem = load_hard_blocks(opts["hard"])
    soft = load_soft_blocks(opts["soft"])

    console.print(
        f"  [green]✓[/green]  {len(problem.classes)} classes, "
        f"{len(problem.teachers)} teachers, "
        f"{len(problem.subjects)} subjects, "
        f"{len(problem.requirements)} requirements"
    )

    # ── 2. CP-SAT phase ─────────────────────────────────────────────────────
    console.rule("[bold blue]Step 2 — CP-SAT (feasibility)")
    t0 = time.perf_counter()
    initial = cp_solver.solve(problem, time_limit_seconds=cfg.CP_TIME_LIMIT_SECONDS)
    cp_elapsed = time.perf_counter() - t0

    if initial is None:
        console.print(
            f"[red]✗ No feasible solution found within {cfg.CP_TIME_LIMIT_SECONDS}s.[/red]\n"
            "  Hints:\n"
            "   • Increase CP_TIME_LIMIT_SECONDS\n"
            "   • Reduce hours_per_week requirements\n"
            "   • Remove or relax hard_blocks"
        )
        sys.exit(1)

    initial_score = score(initial, soft, problem)
    initial.soft_score = initial_score
    console.print(
        f"  [green]✓[/green]  Feasible solution found in {cp_elapsed:.1f}s  "
        f"| soft penalty = {initial_score}"
    )

    # ── 3. Local Search phase ────────────────────────────────────────────────
    console.rule("[bold blue]Step 3 — Local Search (quality improvement)")

    def progress(iteration: int, current: int) -> None:
        console.print(f"  iter {iteration:>5}  penalty = {current}")

    t1 = time.perf_counter()
    final, iterations = local_search.improve(
        initial,
        soft,
        problem,
        max_iterations=cfg.LS_MAX_ITERATIONS,
        progress_callback=progress,
    )
    ls_elapsed = time.perf_counter() - t1

    console.print(
        f"  [green]✓[/green]  Local search done in {ls_elapsed:.1f}s  "
        f"| {iterations} iterations  "
        f"| soft penalty: {initial_score} → {final.soft_score}"
    )

    # ── 4. Persist to MySQL ──────────────────────────────────────────────────
    run_id = None
    if not opts["no_db"]:
        console.rule("[bold blue]Step 4 — Saving to MySQL")
        try:
            from sqlalchemy.orm import Session

            from timetabling.db.repository import (
                create_tables,
                get_engine,
                save_schedule,
                upsert_problem,
                wait_for_db,
            )

            wait_for_db(cfg.DATABASE_URL)
            engine = get_engine(cfg.DATABASE_URL)
            create_tables(engine)

            with Session(engine) as session:
                upsert_problem(session, problem)
                run_id = save_schedule(
                    session,
                    final,
                    cp_feasible=True,
                    soft_score_initial=initial_score,
                    ls_iterations=iterations,
                )
                session.commit()

            console.print(f"  [green]✓[/green]  Saved as run_id={run_id}")
        except Exception as exc:
            console.print(f"  [yellow]⚠ DB save skipped:[/yellow] {exc}")
    else:
        console.rule("[bold blue]Step 4 — MySQL (skipped via --no-db)")

    # ── 5. Export CSVs ───────────────────────────────────────────────────────
    console.rule("[bold blue]Step 5 — Exporting CSVs")
    files = export(final, problem, opts["output"])
    _print_summary(final, problem, files)
    console.print("\n[bold green]Done![/bold green]")


def cmd_serve(opts: dict) -> None:
    from timetabling.api import create_app

    host = opts["host"]
    port = int(opts["port"])
    console.rule("[bold blue]School Timetabling — API Server")
    console.print(f"  Listening on [green]http://{host}:{port}[/green]")
    console.print("  State initialised from disk (hard_blocks.json / soft_blocks.json)")
    console.print("  Press Ctrl+C to stop\n")
    app = create_app()
    app.run(host=host, port=port, debug=False, threaded=True)


def app() -> None:
    opts = _parse_args()
    if opts["command"] == "solve":
        cmd_solve(opts)
    elif opts["command"] == "serve":
        cmd_serve(opts)
    else:
        _print_help()
        sys.exit(1)


if __name__ == "__main__":
    app()
