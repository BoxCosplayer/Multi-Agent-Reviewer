from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from agents import SQLiteSession

from .agents import WorkflowEngine
from .configuration import profile_hash, resolved_config_hash
from .core import consensus_reached, make_artifact
from .models import (
    PersistedState,
    ResolvedRunConfig,
    RUN_ID_PATTERN,
    WorkflowError,
)
from .persistence import (
    artifact_path,
    load_artifact,
    load_config_snapshot,
    load_reviews,
    load_source_metadata,
    load_state,
    save_artifact,
    save_config_snapshot,
    save_reviews,
    save_source_snapshot,
    save_state,
    utc_now,
    write_json_atomic,
)
from .source import LoadedSource, load_saved_source, load_source


DEFAULT_MAX_REVIEW_ROUNDS = 5


def new_run_id() -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise WorkflowError(
            "Run IDs may contain only letters, digits, underscores, and "
            "hyphens, and must be at most 80 characters."
        )


def create_run(
    source_path: Path,
    runs_dir: Path,
    max_review_rounds: int,
    designer_model: str,
    reviewer_model: str,
    config: ResolvedRunConfig,
    requested_run_id: str | None,
) -> tuple[Path, LoadedSource, PersistedState, ResolvedRunConfig]:
    source = load_source(
        source_path,
        config.profile.accepted_blueprint_types,
    )
    run_id = requested_run_id or new_run_id()
    validate_run_id(run_id)
    run_dir = runs_dir / run_id
    if run_dir.exists():
        raise WorkflowError(
            f"Run directory already exists; use --resume instead: {run_dir}"
        )
    run_dir.mkdir(parents=True)

    save_source_snapshot(run_dir, source.metadata, source.data)
    config_sha256 = save_config_snapshot(run_dir, config)
    now = utc_now()
    state = PersistedState(
        run_id=run_id,
        source_sha256=source.metadata.sha256,
        source_filename=source.metadata.original_filename,
        source_media_type=source.metadata.media_type,
        designer_id=config.designer.name,
        profile_sha256=profile_hash(config.profile),
        resolved_config_sha256=config_sha256,
        designer_session_id=f"designer:{run_id}",
        designer_model=designer_model,
        reviewer_model=reviewer_model,
        max_review_rounds=max_review_rounds,
        created_at=now,
        updated_at=now,
    )
    save_state(run_dir, state)
    return run_dir, source, state, config


def resume_run(
    run_id: str,
    runs_dir: Path,
    max_review_rounds: int | None,
) -> tuple[Path, LoadedSource, PersistedState, ResolvedRunConfig]:
    validate_run_id(run_id)
    run_dir = runs_dir / run_id
    state = load_state(run_dir)
    config = load_config_snapshot(run_dir)
    if resolved_config_hash(config) != state.resolved_config_sha256:
        raise WorkflowError(
            "The saved resolved configuration does not match state.json."
        )
    if profile_hash(config.profile) != state.profile_sha256:
        raise WorkflowError("The saved profile does not match state.json.")
    if config.designer.name != state.designer_id:
        raise WorkflowError("The saved designer does not match state.json.")

    metadata = load_source_metadata(run_dir)
    if (
        metadata.sha256 != state.source_sha256
        or metadata.original_filename != state.source_filename
        or metadata.media_type != state.source_media_type
    ):
        raise WorkflowError("The saved source metadata does not match state.json.")
    source = load_saved_source(run_dir, metadata)

    if max_review_rounds is not None:
        state.max_review_rounds = max_review_rounds
        if (
            state.status == "human_review_required"
            and state.completed_review_rounds < max_review_rounds
        ):
            state.status = "awaiting_review"
        save_state(run_dir, state)
    return run_dir, source, state, config


async def execute_workflow(
    engine: WorkflowEngine,
    run_dir: Path,
    source: LoadedSource,
    state: PersistedState,
) -> int:
    if state.status == "approved":
        print(f"Run is already approved: {run_dir}")
        return 0
    if state.status == "human_review_required":
        print(
            "Run already requires human review. Increase --max-rounds when "
            "resuming if you want to continue."
        )
        return 2

    designer_session = SQLiteSession(
        state.designer_session_id,
        str(run_dir / "designer-session.db"),
    )

    if state.current_version == 0:
        content = await engine.create_initial_artifact(source, designer_session)
        artifact = make_artifact(content, version=1)
        save_artifact(run_dir, artifact)
        state.current_version = artifact.version
        state.status = "awaiting_review"
        save_state(run_dir, state)

    if state.status == "revising":
        current = load_artifact(run_dir, state.current_version)
        next_path = artifact_path(run_dir, state.current_version + 1)
        if next_path.is_file():
            next_artifact = load_artifact(
                run_dir,
                state.current_version + 1,
            )
        else:
            pending_reviews = load_reviews(run_dir, state.current_version)
            content = await engine.revise_artifact(
                current,
                pending_reviews,
                designer_session,
            )
            next_artifact = make_artifact(content, current.version + 1)
            save_artifact(run_dir, next_artifact)
        state.current_version = next_artifact.version
        state.status = "awaiting_review"
        save_state(run_dir, state)

    while state.completed_review_rounds < state.max_review_rounds:
        artifact = load_artifact(run_dir, state.current_version)
        reviews = await engine.run_review_round(source, artifact)
        save_reviews(run_dir, artifact.version, reviews)
        state.completed_review_rounds += 1

        if consensus_reached(
            reviews,
            artifact.sha256,
            set(engine.config.selected_reviewers),
        ):
            state.status = "approved"
            save_state(run_dir, state)
            write_json_atomic(
                run_dir / "decision.json",
                {
                    "status": "approved",
                    "run_id": state.run_id,
                    "artifact_version": artifact.version,
                    "artifact_sha256": artifact.sha256,
                    "completed_review_rounds": state.completed_review_rounds,
                    "decided_at": utc_now(),
                },
            )
            print(f"Approved artifact: {run_dir / f'artifact-v{artifact.version}.md'}")
            return 0

        if state.completed_review_rounds >= state.max_review_rounds:
            break

        state.status = "revising"
        save_state(run_dir, state)
        content = await engine.revise_artifact(
            artifact,
            reviews,
            designer_session,
        )
        artifact = make_artifact(content, artifact.version + 1)
        save_artifact(run_dir, artifact)
        state.current_version = artifact.version
        state.status = "awaiting_review"
        save_state(run_dir, state)

    state.status = "human_review_required"
    save_state(run_dir, state)
    write_json_atomic(
        run_dir / "decision.json",
        {
            "status": "human_review_required",
            "run_id": state.run_id,
            "last_reviewed_version": state.current_version,
            "completed_review_rounds": state.completed_review_rounds,
            "reason": "Consensus was not reached within the configured limit.",
            "decided_at": utc_now(),
        },
    )
    print(f"Consensus not reached. Inspect the run at: {run_dir}")
    return 2
