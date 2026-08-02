from __future__ import annotations

import unittest

from pydantic import ValidationError

from multi_agent_review import (
    ArchitectureContent,
    Review,
    consensus_reached,
    make_artifact,
)


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
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
        self.assertFalse(consensus_reached(reviews, self.artifact.sha256))

    def test_consensus_requires_same_artifact(self) -> None:
        reviews = [
            self.make_review("qa"),
            self.make_review("security"),
            self.make_review("dx"),
            self.make_review("ux"),
        ]
        reviews[0].artifact_sha256 = "different"
        self.assertFalse(consensus_reached(reviews, self.artifact.sha256))

    def test_consensus_accepts_four_clean_approvals(self) -> None:
        reviews = [
            self.make_review("qa"),
            self.make_review("security"),
            self.make_review("dx"),
            self.make_review("ux"),
        ]
        self.assertTrue(consensus_reached(reviews, self.artifact.sha256))

    def test_changes_required_needs_a_blocking_finding(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_review("qa", verdict="changes_required")


if __name__ == "__main__":
    unittest.main()
