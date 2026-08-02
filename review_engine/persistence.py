from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .configuration import build_manifest, resolved_config_hash
from .core import render_artifact_markdown
from .models import (
    Artifact,
    ConfigManifest,
    DesignerConfig,
    PersistedState,
    ProfileConfig,
    ResolvedRunConfig,
    Review,
    ReviewerConfig,
    SkillDocument,
    SourceMetadata,
    WorkflowError,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, value: BaseModel | dict | list) -> None:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def artifact_path(run_dir: Path, version: int) -> Path:
    return run_dir / f"artifact-v{version}.json"


def review_path(run_dir: Path, version: int) -> Path:
    return run_dir / f"reviews-v{version}.json"


def save_artifact(run_dir: Path, artifact: Artifact) -> None:
    write_json_atomic(artifact_path(run_dir, artifact.version), artifact)
    markdown_path = run_dir / f"artifact-v{artifact.version}.md"
    markdown_path.write_text(
        render_artifact_markdown(artifact.content),
        encoding="utf-8",
    )


def load_artifact(run_dir: Path, version: int) -> Artifact:
    path = artifact_path(run_dir, version)
    if not path.is_file():
        raise WorkflowError(f"Artifact is missing: {path}")
    try:
        artifact = Artifact.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as error:
        raise WorkflowError(f"Saved artifact is invalid: {path}: {error}") from error
    from .core import make_artifact

    expected = make_artifact(artifact.content, artifact.version)
    if artifact.sha256 != expected.sha256:
        raise WorkflowError(f"Saved artifact hash is invalid: {path}")
    return artifact


def save_reviews(run_dir: Path, version: int, reviews: list[Review]) -> None:
    write_json_atomic(
        review_path(run_dir, version),
        [review.model_dump(mode="json") for review in reviews],
    )


def load_reviews(run_dir: Path, version: int) -> list[Review]:
    path = review_path(run_dir, version)
    if not path.is_file():
        raise WorkflowError(f"Saved reviews are missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [Review.model_validate(item) for item in payload]
    except (json.JSONDecodeError, ValidationError) as error:
        raise WorkflowError(f"Saved reviews are invalid: {path}: {error}") from error


def save_state(run_dir: Path, state: PersistedState) -> None:
    state.updated_at = utc_now()
    write_json_atomic(run_dir / "state.json", state)


def load_state(run_dir: Path) -> PersistedState:
    path = run_dir / "state.json"
    if not path.is_file():
        raise WorkflowError(f"Run state is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise WorkflowError(f"Run state is invalid: {path}: {error}") from error
    if payload.get("schema_version") != 2:
        raise WorkflowError(
            "This run uses the legacy architecture-only state format and cannot "
            "be resumed. Start a new run with --designer."
        )
    try:
        return PersistedState.model_validate(payload)
    except ValidationError as error:
        raise WorkflowError(f"Run state is invalid: {path}: {error}") from error


def save_config_snapshot(run_dir: Path, config: ResolvedRunConfig) -> str:
    config_dir = run_dir / "config"
    config_dir.mkdir()
    write_json_atomic(config_dir / "profile.json", config.profile)
    write_json_atomic(config_dir / "designer.json", config.designer)
    write_json_atomic(
        config_dir / "reviewers.json",
        [reviewer.model_dump(mode="json") for reviewer in config.reviewers],
    )
    write_json_atomic(
        config_dir / "skills.json",
        [document.model_dump(mode="json") for document in config.skill_documents],
    )
    manifest = build_manifest(config)
    write_json_atomic(config_dir / "manifest.json", manifest)
    return manifest.sha256


def load_config_snapshot(run_dir: Path) -> ResolvedRunConfig:
    config_dir = run_dir / "config"
    required = {
        "profile": config_dir / "profile.json",
        "designer": config_dir / "designer.json",
        "reviewers": config_dir / "reviewers.json",
        "skills": config_dir / "skills.json",
        "manifest": config_dir / "manifest.json",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise WorkflowError("Saved configuration is missing: " + ", ".join(missing))
    try:
        profile = ProfileConfig.model_validate(_read_json(required["profile"]))
        designer = DesignerConfig.model_validate(_read_json(required["designer"]))
        reviewers_payload = _read_json(required["reviewers"])
        skills_payload = _read_json(required["skills"])
        reviewers = [ReviewerConfig.model_validate(item) for item in reviewers_payload]
        skills = [SkillDocument.model_validate(item) for item in skills_payload]
        manifest = ConfigManifest.model_validate(_read_json(required["manifest"]))
    except (ValidationError, TypeError) as error:
        raise WorkflowError(f"Saved configuration is invalid: {error}") from error

    config = ResolvedRunConfig(
        profile=profile,
        designer=designer,
        reviewers=reviewers,
        selected_reviewers=manifest.selected_reviewers,
        designer_skill_paths=manifest.designer_skill_paths,
        reviewer_skill_paths=manifest.reviewer_skill_paths,
        skill_documents=skills,
    )
    actual_hash = resolved_config_hash(config)
    if actual_hash != manifest.sha256:
        raise WorkflowError(
            "The saved profile, agents, or skill contents have changed. "
            "Restore the run configuration or start a new run."
        )
    return config


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowError(
            f"Cannot load saved configuration {path}: {error}"
        ) from error


def save_source_snapshot(
    run_dir: Path,
    metadata: SourceMetadata,
    data: bytes,
) -> None:
    write_bytes_atomic(run_dir / metadata.stored_filename, data)
    write_json_atomic(run_dir / "source.json", metadata)


def load_source_metadata(run_dir: Path) -> SourceMetadata:
    path = run_dir / "source.json"
    if not path.is_file():
        raise WorkflowError(f"Source metadata is missing: {path}")
    try:
        return SourceMetadata.model_validate(_read_json(path))
    except ValidationError as error:
        raise WorkflowError(f"Source metadata is invalid: {path}: {error}") from error
