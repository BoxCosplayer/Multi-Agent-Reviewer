from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agents import WorkflowEngine
from .configuration import (
    load_project_configuration,
    resolve_run_config,
)
from .models import WorkflowError
from .workflow import (
    DEFAULT_MAX_REVIEW_ROUNDS,
    create_run,
    execute_workflow,
    resume_run,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_DIR = PROJECT_ROOT / "runs"


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a text artifact and iterate through parallel configured "
            "reviewers until all selected reviewers approve."
        )
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="UTF-8 Markdown/text or PDF source for a new run.",
    )
    parser.add_argument(
        "--designer",
        help="Designer/profile name for a new run.",
    )
    parser.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="Resume an existing run from the runs directory.",
    )
    parser.add_argument("--run-id", help="Optional stable ID for a new run.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=DEFAULT_RUNS_DIR,
        help=f"Run storage directory (default: {DEFAULT_RUNS_DIR}).",
    )
    parser.add_argument(
        "--max-rounds",
        type=positive_integer,
        default=None,
        help=(f"Maximum review rounds (new-run default: {DEFAULT_MAX_REVIEW_ROUNDS})."),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate all local configuration without calling the API.",
    )
    parser.add_argument(
        "--list-designers",
        action="store_true",
        help="List registered designers and their default profile reviewers.",
    )
    parser.add_argument(
        "--list-reviewers",
        action="store_true",
        help="List every registered reviewer.",
    )
    parser.add_argument(
        "--reviewers",
        metavar="NAMES",
        help=(
            "Comma-separated registered reviewers for a new run; replaces "
            "the profile defaults."
        ),
    )
    return parser.parse_args(argv)


def _ensure_listing_args(args: argparse.Namespace) -> None:
    if any(
        (
            args.source,
            args.resume,
            args.run_id,
            args.max_rounds,
            args.reviewers,
            args.designer,
            args.check,
        )
    ):
        raise WorkflowError(
            "Listing options cannot be combined with run options or --check."
        )


def run_check() -> int:
    designers, reviewers, profiles = load_project_configuration(PROJECT_ROOT)
    designer_model = os.getenv("OPENAI_MODEL", "gpt-5.6")
    reviewer_model = os.getenv("OPENAI_REVIEW_MODEL", designer_model)
    for designer in designers:
        config = resolve_run_config(PROJECT_ROOT, designer.name)
        WorkflowEngine(designer_model, reviewer_model, config)
    print(f"Project root: {PROJECT_ROOT}")
    print("Designers: " + ", ".join(designer.label for designer in designers))
    print("Reviewers: " + ", ".join(reviewer.label for reviewer in reviewers))
    print(f"Profiles: {len(profiles)} valid one-to-one mappings")
    print("Skills and composed instructions: OK")
    print("Agent definitions and structured outputs: OK")
    if os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY: configured")
    else:
        print("OPENAI_API_KEY: not configured (required only for a live run)")
    return 0


async def async_main(args: argparse.Namespace) -> int:
    if args.list_designers and args.list_reviewers:
        raise WorkflowError("Choose only one listing option.")
    if args.list_designers or args.list_reviewers:
        _ensure_listing_args(args)
        designers, reviewers, profiles = load_project_configuration(PROJECT_ROOT)
        if args.list_designers:
            print("Available designers:")
            for designer in designers:
                defaults = ", ".join(profiles[designer.name].reviewers)
                print(f"  {designer.name:<16} {designer.label} [reviewers: {defaults}]")
        else:
            print("Available reviewers:")
            for reviewer in reviewers:
                print(f"  {reviewer.name:<16} {reviewer.label}")
        return 0

    if args.check:
        if any(
            (
                args.source,
                args.resume,
                args.run_id,
                args.max_rounds,
                args.reviewers,
                args.designer,
            )
        ):
            raise WorkflowError("--check cannot be combined with run options.")
        return run_check()

    if bool(args.source) == bool(args.resume):
        raise WorkflowError("Provide exactly one source path or --resume RUN_ID.")
    if args.resume and args.run_id:
        raise WorkflowError("--run-id cannot be combined with --resume.")
    if args.resume and (args.designer or args.reviewers):
        raise WorkflowError(
            "--designer and --reviewers cannot be combined with --resume; "
            "resumed runs use their frozen configuration."
        )
    if args.source and not args.designer:
        raise WorkflowError("--designer is required for a new run.")

    config = None
    if args.source:
        config = resolve_run_config(
            PROJECT_ROOT,
            args.designer,
            args.reviewers,
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise WorkflowError(
            "OPENAI_API_KEY is not configured. Copy .env.example to .env "
            "and add your API key."
        )

    runs_dir = args.runs_dir.resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    if args.resume:
        run_dir, source, state, config = resume_run(
            args.resume,
            runs_dir,
            args.max_rounds,
        )
        designer_model = state.designer_model
        reviewer_model = state.reviewer_model
    else:
        assert config is not None
        designer_model = os.getenv("OPENAI_MODEL", "gpt-5.6")
        reviewer_model = os.getenv("OPENAI_REVIEW_MODEL", designer_model)
        run_dir, source, state, config = create_run(
            args.source,
            runs_dir,
            args.max_rounds or DEFAULT_MAX_REVIEW_ROUNDS,
            designer_model,
            reviewer_model,
            config,
            args.run_id,
        )

    print(f"Run ID: {state.run_id}")
    print(f"Designer: {config.designer.name}")
    print(f"Designer model: {designer_model}")
    print(f"Reviewer model: {reviewer_model}")
    print("Reviewers: " + ", ".join(config.selected_reviewers))
    return await execute_workflow(
        WorkflowEngine(designer_model, reviewer_model, config),
        run_dir,
        source,
        state,
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        return asyncio.run(async_main(parse_args(argv)))
    except WorkflowError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
