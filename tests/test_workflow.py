from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from multi_agent_review import (
    ArchitectureContent,
    Review,
    ReviewerConfig,
    WorkflowError,
    consensus_reached,
    create_run,
    make_artifact,
    resume_run,
    select_reviewer_configs,
)


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected_reviewers = {"qa", "security", "dx", "ux"}
        self.artifact = make_artifact(
            ArchitectureContent(
                title="Test architecture",
                diagram_mermaid="flowchart LR\n  A --> B",
                overview="Test",
            ),
            version=1,
        )

    def make_review(
        self,
        reviewer: str,
        verdict: str = "approve",
    ) -> Review:
        return Review(
            reviewer=reviewer,
            artifact_sha256=self.artifact.sha256,
            verdict=verdict,
            blocking_findings=[],
        )

    def test_consensus_requires_all_reviewers(self) -> None:
        reviews = [
            self.make_review("qa"),
            self.make_review("security"),
            self.make_review("dx"),
        ]
        self.assertFalse(
            consensus_reached(
                reviews,
                self.artifact.sha256,
                self.expected_reviewers,
            )
        )

    def test_consensus_requires_same_artifact(self) -> None:
        reviews = [
            self.make_review("qa"),
            self.make_review("security"),
            self.make_review("dx"),
            self.make_review("ux"),
        ]
        reviews[0].artifact_sha256 = "different"
        self.assertFalse(
            consensus_reached(
                reviews,
                self.artifact.sha256,
                self.expected_reviewers,
            )
        )

    def test_consensus_accepts_four_clean_approvals(self) -> None:
        reviews = [
            self.make_review("qa"),
            self.make_review("security"),
            self.make_review("dx"),
            self.make_review("ux"),
        ]
        self.assertTrue(
            consensus_reached(
                reviews,
                self.artifact.sha256,
                self.expected_reviewers,
            )
        )

    def test_consensus_supports_a_configured_reviewer(self) -> None:
        reviews = [
            self.make_review("qa"),
            self.make_review("performance"),
        ]
        self.assertTrue(
            consensus_reached(
                reviews,
                self.artifact.sha256,
                {"qa", "performance"},
            )
        )

    def test_reviewer_selection_preserves_requested_order(self) -> None:
        available = [
            ReviewerConfig(
                name="qa",
                label="QA",
                skill="review-architecture-qa",
            ),
            ReviewerConfig(
                name="security",
                label="Security",
                skill="review-architecture-security",
            ),
            ReviewerConfig(
                name="performance",
                label="Performance",
                skill="review-architecture-performance",
            ),
        ]
        selected = select_reviewer_configs("performance,qa", available)
        self.assertEqual(
            [reviewer.name for reviewer in selected],
            ["performance", "qa"],
        )

    def test_reviewer_selection_rejects_unknown_names(self) -> None:
        available = [
            ReviewerConfig(
                name="qa",
                label="QA",
                skill="review-architecture-qa",
            )
        ]
        with self.assertRaisesRegex(WorkflowError, "Unknown reviewer"):
            select_reviewer_configs("qa,missing", available)

    def test_changes_required_needs_a_blocking_finding(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_review("qa", verdict="changes_required")

    def test_resume_uses_the_run_reviewer_snapshot(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            blueprint_path = root / "blueprint.md"
            blueprint_path.write_text("Build a test service.", encoding="utf-8")
            configured_reviewers = [
                ReviewerConfig(
                    name="qa",
                    label="QA",
                    skill="review-architecture-qa",
                )
            ]
            run_dir, _, _, _ = create_run(
                blueprint_path,
                root / "runs",
                2,
                "architect-model",
                "reviewer-model",
                configured_reviewers,
                "test-run",
            )

            _, _, _, resumed_reviewers = resume_run(
                "test-run",
                root / "runs",
                None,
                [
                    ReviewerConfig(
                        name="performance",
                        label="Performance",
                        skill="review-architecture-performance",
                    )
                ],
            )

            self.assertEqual(
                [reviewer.name for reviewer in resumed_reviewers],
                ["qa"],
            )
            self.assertTrue((run_dir / "reviewers.json").is_file())


if __name__ == "__main__":
    unittest.main()
