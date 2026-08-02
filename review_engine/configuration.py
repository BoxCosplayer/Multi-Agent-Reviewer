from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .core import canonical_json, sha256_text
from .models import (
    ConfigManifest,
    DesignerConfig,
    ProfileConfig,
    ResolvedRunConfig,
    ReviewerConfig,
    SkillDocument,
    WorkflowError,
)


DESIGNERS_FILENAME = "designers.json"
REVIEWERS_FILENAME = "reviewers.json"
PROFILES_DIRNAME = "profiles"
SKILLS_DIRNAME = "skills"


def _load_json(path: Path) -> object:
    if not path.is_file():
        raise WorkflowError(f"Required configuration is missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowError(f"Cannot load configuration {path}: {error}") from error


def _load_registry(
    path: Path,
    model: type[DesignerConfig] | type[ReviewerConfig],
) -> list[DesignerConfig] | list[ReviewerConfig]:
    payload = _load_json(path)
    if not isinstance(payload, list) or not payload:
        raise WorkflowError(f"Configuration must be a non-empty array: {path}")
    try:
        agents = [model.model_validate(item) for item in payload]
    except ValidationError as error:
        raise WorkflowError(f"Invalid configuration in {path}: {error}") from error
    names = [agent.name for agent in agents]
    if len(names) != len(set(names)):
        raise WorkflowError(f"Duplicate agent names in {path}.")
    return agents


def load_designers(project_root: Path) -> list[DesignerConfig]:
    return list(_load_registry(project_root / DESIGNERS_FILENAME, DesignerConfig))


def load_reviewers(project_root: Path) -> list[ReviewerConfig]:
    return list(_load_registry(project_root / REVIEWERS_FILENAME, ReviewerConfig))


def _validate_skill_path(project_root: Path, configured_path: str) -> Path:
    relative = Path(configured_path)
    if relative.is_absolute():
        raise WorkflowError(f"Skill paths must be relative: {configured_path}")
    if relative.name != "SKILL.md":
        raise WorkflowError(f"Skill paths must point to SKILL.md: {configured_path}")
    skills_root = (project_root / SKILLS_DIRNAME).resolve()
    resolved = (project_root / relative).resolve()
    try:
        resolved.relative_to(skills_root)
    except ValueError as error:
        raise WorkflowError(
            f"Skill path must stay under {SKILLS_DIRNAME}/: {configured_path}"
        ) from error
    if not resolved.is_file():
        raise WorkflowError(f"Required skill is missing: {resolved}")
    return resolved


def _validate_combined_skills(
    project_root: Path,
    owner: str,
    paths: list[str],
) -> None:
    if not paths:
        raise WorkflowError(f"Agent '{owner}' has no resolved skills.")
    if len(paths) != len(set(paths)):
        raise WorkflowError(f"Agent '{owner}' resolves duplicate skill paths.")
    for path in paths:
        _validate_skill_path(project_root, path)


def load_profiles(
    project_root: Path,
    designers: list[DesignerConfig],
    reviewers: list[ReviewerConfig],
) -> dict[str, ProfileConfig]:
    profiles_dir = project_root / PROFILES_DIRNAME
    if not profiles_dir.is_dir():
        raise WorkflowError(f"Required profiles directory is missing: {profiles_dir}")

    profiles: dict[str, ProfileConfig] = {}
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            profile = ProfileConfig.model_validate(_load_json(path))
        except ValidationError as error:
            raise WorkflowError(f"Invalid profile {path}: {error}") from error
        if path.stem != profile.name or profile.designer != profile.name:
            raise WorkflowError(
                f"Profile filename, name, and designer must match: {path}"
            )
        if profile.name in profiles:
            raise WorkflowError(f"Duplicate profile: {profile.name}")
        profiles[profile.name] = profile

    designer_names = {designer.name for designer in designers}
    reviewer_names = {reviewer.name for reviewer in reviewers}
    missing_profiles = designer_names - set(profiles)
    extra_profiles = set(profiles) - designer_names
    if missing_profiles or extra_profiles:
        details: list[str] = []
        if missing_profiles:
            details.append("missing: " + ", ".join(sorted(missing_profiles)))
        if extra_profiles:
            details.append("unknown: " + ", ".join(sorted(extra_profiles)))
        raise WorkflowError(
            "Profiles must map one-to-one with designers (" + "; ".join(details) + ")."
        )

    designers_by_name = {designer.name: designer for designer in designers}
    reviewers_by_name = {reviewer.name: reviewer for reviewer in reviewers}
    for profile in profiles.values():
        unknown_defaults = set(profile.reviewers) - reviewer_names
        unknown_overlays = set(profile.reviewer_skills) - reviewer_names
        if unknown_defaults or unknown_overlays:
            unknown = sorted(unknown_defaults | unknown_overlays)
            raise WorkflowError(
                f"Profile '{profile.name}' references unknown reviewers: "
                + ", ".join(unknown)
            )
        _validate_combined_skills(
            project_root,
            profile.designer,
            [
                *designers_by_name[profile.designer].skills,
                *profile.designer_skills,
            ],
        )
        for reviewer_name, skills in profile.reviewer_skills.items():
            _validate_combined_skills(
                project_root,
                reviewer_name,
                [*reviewers_by_name[reviewer_name].skills, *skills],
            )

    return profiles


def load_project_configuration(
    project_root: Path,
) -> tuple[
    list[DesignerConfig],
    list[ReviewerConfig],
    dict[str, ProfileConfig],
]:
    designers = load_designers(project_root)
    reviewers = load_reviewers(project_root)
    for agent in [*designers, *reviewers]:
        for path in agent.skills:
            _validate_skill_path(project_root, path)
    profiles = load_profiles(project_root, designers, reviewers)
    return designers, reviewers, profiles


def select_reviewer_names(
    requested: str | None,
    default_names: list[str],
    reviewers: list[ReviewerConfig],
) -> list[str]:
    if requested is None:
        return list(default_names)
    names = [name.strip() for name in requested.split(",") if name.strip()]
    if not names:
        raise WorkflowError(
            "--reviewers must be a comma-separated list of reviewer names."
        )
    if len(names) != len(set(names)):
        raise WorkflowError("--reviewers contains duplicate reviewer names.")
    available = {reviewer.name for reviewer in reviewers}
    unknown = [name for name in names if name not in available]
    if unknown:
        raise WorkflowError(
            "Unknown reviewer(s): "
            + ", ".join(unknown)
            + ". Available reviewers: "
            + ", ".join(sorted(available))
        )
    return names


def resolve_run_config(
    project_root: Path,
    designer_name: str,
    requested_reviewers: str | None = None,
) -> ResolvedRunConfig:
    designers, reviewers, profiles = load_project_configuration(project_root)
    designers_by_name = {designer.name: designer for designer in designers}
    reviewers_by_name = {reviewer.name: reviewer for reviewer in reviewers}
    if designer_name not in designers_by_name:
        raise WorkflowError(
            f"Unknown designer '{designer_name}'. Available designers: "
            + ", ".join(sorted(designers_by_name))
        )

    profile = profiles[designer_name]
    selected_names = select_reviewer_names(
        requested_reviewers,
        profile.reviewers,
        reviewers,
    )
    designer = designers_by_name[designer_name]
    designer_paths = [*designer.skills, *profile.designer_skills]
    _validate_combined_skills(project_root, designer.name, designer_paths)

    selected_reviewers = [reviewers_by_name[name] for name in selected_names]
    reviewer_paths: dict[str, list[str]] = {}
    for reviewer in selected_reviewers:
        paths = [
            *reviewer.skills,
            *profile.reviewer_skills.get(reviewer.name, []),
        ]
        _validate_combined_skills(project_root, reviewer.name, paths)
        reviewer_paths[reviewer.name] = paths

    all_paths = list(
        dict.fromkeys(
            [
                *designer_paths,
                *[path for name in selected_names for path in reviewer_paths[name]],
            ]
        )
    )
    documents = []
    for configured_path in all_paths:
        path = _validate_skill_path(project_root, configured_path)
        content = path.read_text(encoding="utf-8")
        documents.append(
            SkillDocument(
                path=configured_path,
                sha256=sha256_text(content),
                content=content,
            )
        )

    return ResolvedRunConfig(
        profile=profile,
        designer=designer,
        reviewers=selected_reviewers,
        selected_reviewers=selected_names,
        designer_skill_paths=designer_paths,
        reviewer_skill_paths=reviewer_paths,
        skill_documents=documents,
    )


def resolved_config_hash(config: ResolvedRunConfig) -> str:
    return sha256_text(canonical_json(config))


def profile_hash(profile: ProfileConfig) -> str:
    return sha256_text(canonical_json(profile))


def compose_skill_text(
    config: ResolvedRunConfig,
    paths: list[str],
) -> str:
    documents = {document.path: document for document in config.skill_documents}
    parts: list[str] = []
    for path in paths:
        document = documents.get(path)
        if document is None:
            raise WorkflowError(f"Resolved skill is missing from snapshot: {path}")
        if sha256_text(document.content) != document.sha256:
            raise WorkflowError(f"Resolved skill content is corrupt: {path}")
        parts.append(f"--- Skill: {path} ---\n{document.content.strip()}")
    return "\n\n".join(parts)


def build_manifest(config: ResolvedRunConfig) -> ConfigManifest:
    return ConfigManifest(
        sha256=resolved_config_hash(config),
        selected_reviewers=config.selected_reviewers,
        designer_skill_paths=config.designer_skill_paths,
        reviewer_skill_paths=config.reviewer_skill_paths,
    )
