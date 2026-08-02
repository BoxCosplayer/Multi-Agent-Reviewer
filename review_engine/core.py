from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from .models import Artifact, Review, TextArtifactContent


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json(value: BaseModel) -> str:
    return json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def make_artifact(content: TextArtifactContent, version: int) -> Artifact:
    return Artifact(
        version=version,
        sha256=sha256_text(canonical_json(content)),
        content=content,
    )


def _markdown_list(values: list[str]) -> str:
    if not values:
        return "- None recorded."
    return "\n".join(f"- {value}" for value in values)


def render_artifact_markdown(content: TextArtifactContent) -> str:
    return (
        f"# {content.title.strip()}\n\n"
        f"{content.summary.strip()}\n\n"
        f"{content.body_markdown.strip()}\n\n"
        "## Assumptions\n\n"
        f"{_markdown_list(content.assumptions)}\n\n"
        "## Decisions\n\n"
        f"{_markdown_list(content.decisions)}\n\n"
        "## Change log\n\n"
        f"{_markdown_list(content.change_log)}\n"
    )


def validate_review(
    review: Review,
    expected_reviewer: str,
    expected_hash: str,
) -> None:
    if review.reviewer != expected_reviewer:
        raise ValueError(
            f"Expected reviewer '{expected_reviewer}', got '{review.reviewer}'."
        )
    if review.artifact_sha256 != expected_hash:
        raise ValueError("The reviewer returned the wrong artifact SHA-256.")


def consensus_reached(
    reviews: list[Review],
    expected_hash: str,
    expected_reviewers: set[str],
) -> bool:
    return (
        {review.reviewer for review in reviews} == expected_reviewers
        and len(reviews) == len(expected_reviewers)
        and all(review.artifact_sha256 == expected_hash for review in reviews)
        and all(review.verdict == "approve" for review in reviews)
        and all(not review.blocking_findings for review in reviews)
    )
