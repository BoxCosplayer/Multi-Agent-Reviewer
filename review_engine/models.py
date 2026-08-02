from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
AGENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
SUPPORTED_SOURCE_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
}

Verdict = Literal["approve", "changes_required"]
WorkflowStatus = Literal[
    "created",
    "awaiting_review",
    "revising",
    "approved",
    "human_review_required",
]
PdfDetail = Literal["auto", "low", "high"]


class WorkflowError(RuntimeError):
    """Raised when workflow configuration or persisted state is unsafe."""


class NamedAgentConfig(BaseModel):
    name: str
    label: str
    skills: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_agent(self) -> "NamedAgentConfig":
        if not AGENT_NAME_PATTERN.fullmatch(self.name):
            raise ValueError(
                "Agent names must start with a lowercase letter and contain "
                "only lowercase letters, digits, underscores, or hyphens."
            )
        if not self.label.strip():
            raise ValueError("Agent labels cannot be empty.")
        if len(self.skills) != len(set(self.skills)):
            raise ValueError(f"Agent '{self.name}' contains duplicate skills.")
        return self


class DesignerConfig(NamedAgentConfig):
    pass


class ReviewerConfig(NamedAgentConfig):
    pass


class ProfileConfig(BaseModel):
    name: str
    label: str
    designer: str
    reviewers: list[str] = Field(min_length=1)
    designer_skills: list[str] = Field(default_factory=list)
    reviewer_skills: dict[str, list[str]] = Field(default_factory=dict)
    accepted_blueprint_types: list[str] = Field(min_length=1)
    pdf_detail: PdfDetail = "auto"

    @model_validator(mode="after")
    def valid_profile(self) -> "ProfileConfig":
        if not AGENT_NAME_PATTERN.fullmatch(self.name):
            raise ValueError("Profile names must use the agent-name format.")
        if not self.label.strip():
            raise ValueError("Profile labels cannot be empty.")
        if len(self.reviewers) != len(set(self.reviewers)):
            raise ValueError(f"Profile '{self.name}' has duplicate reviewers.")
        if len(self.designer_skills) != len(set(self.designer_skills)):
            raise ValueError(f"Profile '{self.name}' has duplicate designer skills.")
        unknown_types = set(self.accepted_blueprint_types) - SUPPORTED_SOURCE_TYPES
        if unknown_types:
            raise ValueError(
                "Unsupported blueprint MIME types: " + ", ".join(sorted(unknown_types))
            )
        if len(self.accepted_blueprint_types) != len(
            set(self.accepted_blueprint_types)
        ):
            raise ValueError(
                f"Profile '{self.name}' has duplicate blueprint MIME types."
            )
        for reviewer, skills in self.reviewer_skills.items():
            if len(skills) != len(set(skills)):
                raise ValueError(
                    f"Profile '{self.name}' has duplicate skills for "
                    f"reviewer '{reviewer}'."
                )
        return self


class SkillDocument(BaseModel):
    path: str
    sha256: str
    content: str


class ResolvedRunConfig(BaseModel):
    schema_version: Literal[1] = 1
    profile: ProfileConfig
    designer: DesignerConfig
    reviewers: list[ReviewerConfig]
    selected_reviewers: list[str]
    designer_skill_paths: list[str]
    reviewer_skill_paths: dict[str, list[str]]
    skill_documents: list[SkillDocument]


class ConfigManifest(BaseModel):
    schema_version: Literal[1] = 1
    sha256: str
    selected_reviewers: list[str]
    designer_skill_paths: list[str]
    reviewer_skill_paths: dict[str, list[str]]


class SourceMetadata(BaseModel):
    original_filename: str
    stored_filename: str
    media_type: str
    sha256: str
    size_bytes: int = Field(ge=1)


class TextArtifactContent(BaseModel):
    title: str
    summary: str
    body_markdown: str
    assumptions: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    change_log: list[str] = Field(default_factory=list)


class Artifact(BaseModel):
    version: int = Field(ge=1)
    sha256: str
    content: TextArtifactContent


class BlockingFinding(BaseModel):
    id: str
    title: str
    requirement: str
    evidence: str
    risk: str
    recommendation: str


class Review(BaseModel):
    reviewer: str
    artifact_sha256: str
    verdict: Verdict
    blocking_findings: list[BlockingFinding] = Field(default_factory=list)
    advisory_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def verdict_matches_findings(self) -> "Review":
        if self.verdict == "approve" and self.blocking_findings:
            raise ValueError("An approval cannot contain blocking findings.")
        if self.verdict == "changes_required" and not self.blocking_findings:
            raise ValueError(
                "changes_required must include at least one blocking finding."
            )
        return self


class PersistedState(BaseModel):
    schema_version: Literal[2] = 2
    run_id: str
    status: WorkflowStatus = "created"
    current_version: int = Field(default=0, ge=0)
    completed_review_rounds: int = Field(default=0, ge=0)
    max_review_rounds: int = Field(ge=1)
    source_sha256: str
    source_filename: str
    source_media_type: str
    designer_id: str
    profile_sha256: str
    resolved_config_sha256: str
    designer_session_id: str
    designer_model: str
    reviewer_model: str
    created_at: str
    updated_at: str
