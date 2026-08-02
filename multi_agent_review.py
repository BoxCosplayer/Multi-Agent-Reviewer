"""Command-line entry point for the multi-agent review engine."""

from review_engine import (
    Artifact,
    BlockingFinding,
    DesignerConfig,
    ProfileConfig,
    Review,
    ReviewerConfig,
    SourceMetadata,
    TextArtifactContent,
    WorkflowError,
    canonical_json,
    consensus_reached,
    make_artifact,
    render_artifact_markdown,
    sha256_bytes,
    sha256_text,
    validate_review,
)
from review_engine.cli import main, parse_args
from review_engine.configuration import (
    load_project_configuration,
    resolve_run_config,
    select_reviewer_names,
)
from review_engine.workflow import create_run, execute_workflow, resume_run

__all__ = [
    "Artifact",
    "BlockingFinding",
    "DesignerConfig",
    "ProfileConfig",
    "Review",
    "ReviewerConfig",
    "SourceMetadata",
    "TextArtifactContent",
    "WorkflowError",
    "canonical_json",
    "consensus_reached",
    "create_run",
    "execute_workflow",
    "load_project_configuration",
    "main",
    "make_artifact",
    "parse_args",
    "render_artifact_markdown",
    "resolve_run_config",
    "resume_run",
    "select_reviewer_names",
    "sha256_bytes",
    "sha256_text",
    "validate_review",
]


if __name__ == "__main__":
    raise SystemExit(main())
