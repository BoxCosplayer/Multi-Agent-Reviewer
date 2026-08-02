from __future__ import annotations

import asyncio
import base64
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from review_engine.agents import WorkflowEngine
from review_engine.cli import async_main, parse_args
from review_engine.configuration import (
    compose_skill_text,
    load_project_configuration,
    resolve_run_config,
    select_reviewer_names,
)
from review_engine.core import (
    consensus_reached,
    make_artifact,
    render_artifact_markdown,
)
from review_engine.models import (
    BlockingFinding,
    Review,
    ReviewerConfig,
    TextArtifactContent,
    WorkflowError,
)
from review_engine.persistence import (
    load_artifact,
    load_config_snapshot,
    load_state,
    save_artifact,
    save_reviews,
    save_state,
)
from review_engine.source import build_source_input, load_source
from review_engine.workflow import create_run, execute_workflow, resume_run


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def make_project(root: Path) -> None:
    skill_contents = {
        "design-base": "DESIGN BASE",
        "design-domain": "DESIGN DOMAIN",
        "review-base": "REVIEW BASE",
        "review-domain": "REVIEW DOMAIN",
        "review-extra": "REVIEW EXTRA",
    }
    for name, content in skill_contents.items():
        path = root / "skills" / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(content, encoding="utf-8")
    write_json(
        root / "designers.json",
        [
            {
                "name": "sample",
                "label": "Sample Designer",
                "skills": ["skills/design-base/SKILL.md"],
            }
        ],
    )
    write_json(
        root / "reviewers.json",
        [
            {
                "name": "quality",
                "label": "Quality",
                "skills": ["skills/review-base/SKILL.md"],
            },
            {
                "name": "extra",
                "label": "Extra",
                "skills": ["skills/review-extra/SKILL.md"],
            },
        ],
    )
    profiles = root / "profiles"
    profiles.mkdir()
    write_json(
        profiles / "sample.json",
        {
            "name": "sample",
            "label": "Sample Design",
            "designer": "sample",
            "reviewers": ["quality"],
            "designer_skills": ["skills/design-domain/SKILL.md"],
            "reviewer_skills": {"quality": ["skills/review-domain/SKILL.md"]},
            "accepted_blueprint_types": [
                "text/plain",
                "text/markdown",
                "application/pdf",
            ],
            "pdf_detail": "auto",
        },
    )


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.content = TextArtifactContent(
            title="Test artifact",
            summary="A test summary.",
            body_markdown="## Design\n\nUseful content.",
        )
        self.artifact = make_artifact(self.content, version=1)

    def make_review(
        self,
        reviewer: str,
        verdict: str = "approve",
    ) -> Review:
        findings = []
        if verdict == "changes_required":
            findings = [
                BlockingFinding(
                    id="F-1",
                    title="Missing requirement",
                    requirement="R1",
                    evidence="The artifact omits R1.",
                    risk="R1 cannot be met.",
                    recommendation="Address R1.",
                )
            ]
        return Review(
            reviewer=reviewer,
            artifact_sha256=self.artifact.sha256,
            verdict=verdict,
            blocking_findings=findings,
        )

    def test_consensus_requires_all_reviewers_and_same_artifact(self) -> None:
        reviews = [self.make_review("quality"), self.make_review("security")]
        self.assertTrue(
            consensus_reached(
                reviews,
                self.artifact.sha256,
                {"quality", "security"},
            )
        )
        self.assertFalse(
            consensus_reached(
                reviews[:1],
                self.artifact.sha256,
                {"quality", "security"},
            )
        )
        reviews[0].artifact_sha256 = "different"
        self.assertFalse(
            consensus_reached(
                reviews,
                self.artifact.sha256,
                {"quality", "security"},
            )
        )

    def test_changes_required_needs_a_blocking_finding(self) -> None:
        with self.assertRaises(ValidationError):
            Review(
                reviewer="quality",
                artifact_sha256=self.artifact.sha256,
                verdict="changes_required",
            )

    def test_markdown_render_and_artifact_round_trip(self) -> None:
        markdown = render_artifact_markdown(self.content)
        self.assertIn("# Test artifact", markdown)
        self.assertIn("## Assumptions\n\n- None recorded.", markdown)
        with TemporaryDirectory() as temporary:
            from review_engine.persistence import save_artifact

            run_dir = Path(temporary)
            save_artifact(run_dir, self.artifact)
            loaded = load_artifact(run_dir, 1)
            self.assertEqual(loaded.sha256, self.artifact.sha256)
            self.assertEqual(
                (run_dir / "artifact-v1.md").read_text(encoding="utf-8"),
                markdown,
            )


class ConfigurationTests(unittest.TestCase):
    def test_profile_resolution_and_skill_order(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            designers, reviewers, profiles = load_project_configuration(root)
            self.assertEqual([item.name for item in designers], ["sample"])
            self.assertEqual(set(item.name for item in reviewers), {"quality", "extra"})
            self.assertEqual(set(profiles), {"sample"})

            config = resolve_run_config(root, "sample")
            text = compose_skill_text(config, config.designer_skill_paths)
            self.assertLess(text.index("DESIGN BASE"), text.index("DESIGN DOMAIN"))
            reviewer_text = compose_skill_text(
                config,
                config.reviewer_skill_paths["quality"],
            )
            self.assertLess(
                reviewer_text.index("REVIEW BASE"),
                reviewer_text.index("REVIEW DOMAIN"),
            )

    def test_reviewer_override_can_select_any_registered_reviewer(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            config = resolve_run_config(root, "sample", "extra")
            self.assertEqual(config.selected_reviewers, ["extra"])
            self.assertEqual(
                config.reviewer_skill_paths["extra"],
                ["skills/review-extra/SKILL.md"],
            )

    def test_reviewer_selection_rejects_duplicates_and_unknown_names(self) -> None:
        available = [
            ReviewerConfig(
                name="quality",
                label="Quality",
                skills=["skills/review-core/SKILL.md"],
            )
        ]
        with self.assertRaisesRegex(WorkflowError, "duplicate"):
            select_reviewer_names("quality,quality", ["quality"], available)
        with self.assertRaisesRegex(WorkflowError, "Unknown reviewer"):
            select_reviewer_names("missing", ["quality"], available)

    def test_missing_profile_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            (root / "profiles" / "sample.json").unlink()
            with self.assertRaisesRegex(WorkflowError, "one-to-one"):
                load_project_configuration(root)

    def test_mismatched_profile_name_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            path = root / "profiles" / "sample.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["name"] = "different"
            write_json(path, payload)
            with self.assertRaisesRegex(WorkflowError, "must match"):
                load_project_configuration(root)

    def test_skill_path_cannot_escape_skills_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            payload = json.loads((root / "designers.json").read_text(encoding="utf-8"))
            payload[0]["skills"] = ["../outside/SKILL.md"]
            write_json(root / "designers.json", payload)
            with self.assertRaisesRegex(WorkflowError, "stay under"):
                load_project_configuration(root)

    def test_duplicate_composed_skill_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            path = root / "profiles" / "sample.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["designer_skills"] = ["skills/design-base/SKILL.md"]
            write_json(path, payload)
            with self.assertRaisesRegex(WorkflowError, "duplicate skill"):
                resolve_run_config(root, "sample")


class SourceTests(unittest.TestCase):
    def test_text_source_is_loaded_and_embedded(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "brief.md"
            path.write_text("Build something useful.", encoding="utf-8")
            source = load_source(path, ["text/markdown"])
            value = build_source_input("Create it.", source, "auto")
            self.assertIsInstance(value, str)
            self.assertIn("<source_document>", value)
            self.assertIn("Build something useful.", value)

    def test_pdf_source_builds_responses_input_file(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "brief.pdf"
            data = b"%PDF-1.7\nminimal test bytes"
            path.write_bytes(data)
            source = load_source(path, ["application/pdf"])
            value = build_source_input("Create it.", source, "high")
            self.assertIsInstance(value, list)
            file_item = value[0]["content"][0]
            self.assertEqual(file_item["type"], "input_file")
            self.assertEqual(file_item["detail"], "high")
            prefix, encoded = file_item["file_data"].split(",", 1)
            self.assertEqual(prefix, "data:application/pdf;base64")
            self.assertEqual(base64.b64decode(encoded), data)

    def test_invalid_pdf_header_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "brief.pdf"
            path.write_bytes(b"not a pdf")
            with self.assertRaisesRegex(WorkflowError, "valid PDF header"):
                load_source(path, ["application/pdf"])

    def test_pdf_size_boundary_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "brief.pdf"
            path.write_bytes(b"%PDF-123")
            with patch("review_engine.source.MAX_PDF_BYTES", 8):
                with self.assertRaisesRegex(WorkflowError, "smaller than 50 MB"):
                    load_source(path, ["application/pdf"])

    def test_profile_rejects_unaccepted_source_type(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "brief.txt"
            path.write_text("Hello", encoding="utf-8")
            with self.assertRaisesRegex(WorkflowError, "does not accept"):
                load_source(path, ["application/pdf"])


class PersistenceTests(unittest.TestCase):
    def test_resume_uses_frozen_skills_after_project_edit(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            source_path = root / "brief.md"
            source_path.write_text("Build it.", encoding="utf-8")
            config = resolve_run_config(root, "sample")
            run_dir, _, state, _ = create_run(
                source_path,
                root / "runs",
                2,
                "designer-model",
                "reviewer-model",
                config,
                "test-run",
            )
            original = compose_skill_text(config, config.designer_skill_paths)
            (root / "skills" / "design-base" / "SKILL.md").write_text(
                "EDITED",
                encoding="utf-8",
            )
            _, _, resumed_state, resumed = resume_run(
                "test-run",
                root / "runs",
                None,
            )
            self.assertEqual(resumed_state.run_id, state.run_id)
            self.assertEqual(
                compose_skill_text(resumed, resumed.designer_skill_paths),
                original,
            )
            self.assertTrue((run_dir / "config" / "skills.json").is_file())

    def test_tampered_skill_snapshot_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            source_path = root / "brief.md"
            source_path.write_text("Build it.", encoding="utf-8")
            config = resolve_run_config(root, "sample")
            run_dir, _, _, _ = create_run(
                source_path,
                root / "runs",
                2,
                "designer-model",
                "reviewer-model",
                config,
                "test-run",
            )
            path = run_dir / "config" / "skills.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload[0]["content"] = "TAMPERED"
            write_json(path, payload)
            with self.assertRaisesRegex(WorkflowError, "have changed"):
                load_config_snapshot(run_dir)

    def test_source_tampering_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            source_path = root / "brief.md"
            source_path.write_text("Build it.", encoding="utf-8")
            config = resolve_run_config(root, "sample")
            run_dir, _, _, _ = create_run(
                source_path,
                root / "runs",
                2,
                "designer-model",
                "reviewer-model",
                config,
                "test-run",
            )
            (run_dir / "source.md").write_text("Changed", encoding="utf-8")
            with self.assertRaisesRegex(WorkflowError, "saved source has changed"):
                resume_run("test-run", root / "runs", None)

    def test_legacy_state_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            write_json(run_dir / "state.json", {"run_id": "legacy"})
            with self.assertRaisesRegex(WorkflowError, "legacy"):
                load_state(run_dir)


class CliTests(unittest.TestCase):
    def test_new_run_requires_designer_before_api_key(self) -> None:
        args = parse_args(["brief.md"])
        with self.assertRaisesRegex(WorkflowError, "--designer is required"):
            asyncio.run(async_main(args))

    def test_resume_rejects_designer_and_reviewers(self) -> None:
        args = parse_args(
            [
                "--resume",
                "run-1",
                "--designer",
                "sample",
                "--reviewers",
                "quality",
            ]
        )
        with self.assertRaisesRegex(WorkflowError, "cannot be combined"):
            asyncio.run(async_main(args))


class FakeEngine:
    def __init__(self, config, require_revision: bool = False) -> None:
        self.config = config
        self.require_revision = require_revision
        self.rounds = 0
        self.revise_calls = 0

    async def create_initial_artifact(self, source, session):
        return TextArtifactContent(
            title="Initial",
            summary="Initial summary",
            body_markdown="Initial body",
        )

    async def run_review_round(self, source, artifact):
        self.rounds += 1
        if self.require_revision and self.rounds == 1:
            return [
                Review(
                    reviewer=self.config.selected_reviewers[0],
                    artifact_sha256=artifact.sha256,
                    verdict="changes_required",
                    blocking_findings=[
                        BlockingFinding(
                            id="F-1",
                            title="Revise",
                            requirement="R1",
                            evidence="Initial body",
                            risk="Incomplete",
                            recommendation="Revise it",
                        )
                    ],
                )
            ]
        return [
            Review(
                reviewer=name,
                artifact_sha256=artifact.sha256,
                verdict="approve",
            )
            for name in self.config.selected_reviewers
        ]

    async def revise_artifact(self, artifact, reviews, session):
        self.revise_calls += 1
        return TextArtifactContent(
            title="Revised",
            summary="Revised summary",
            body_markdown="Revised body",
            change_log=["Resolved F-1."],
        )


class WorkflowExecutionTests(unittest.TestCase):
    def create_fixture(self, root: Path, rounds: int = 2):
        make_project(root)
        source_path = root / "brief.md"
        source_path.write_text("Build it.", encoding="utf-8")
        config = resolve_run_config(root, "sample")
        return create_run(
            source_path,
            root / "runs",
            rounds,
            "designer-model",
            "reviewer-model",
            config,
            "test-run",
        )

    def test_mocked_workflow_approves_initial_artifact(self) -> None:
        with TemporaryDirectory() as temporary:
            run_dir, source, state, config = self.create_fixture(Path(temporary))
            result = asyncio.run(
                execute_workflow(
                    FakeEngine(config),
                    run_dir,
                    source,
                    state,
                )
            )
            self.assertEqual(result, 0)
            self.assertEqual(load_state(run_dir).status, "approved")
            self.assertTrue((run_dir / "artifact-v1.md").is_file())

    def test_mocked_workflow_revises_then_approves(self) -> None:
        with TemporaryDirectory() as temporary:
            run_dir, source, state, config = self.create_fixture(Path(temporary))
            result = asyncio.run(
                execute_workflow(
                    FakeEngine(config, require_revision=True),
                    run_dir,
                    source,
                    state,
                )
            )
            self.assertEqual(result, 0)
            saved_state = load_state(run_dir)
            self.assertEqual(saved_state.current_version, 2)
            self.assertEqual(saved_state.completed_review_rounds, 2)
            self.assertEqual(load_artifact(run_dir, 2).content.title, "Revised")

    def test_mocked_workflow_exhausts_round_limit(self) -> None:
        with TemporaryDirectory() as temporary:
            run_dir, source, state, config = self.create_fixture(
                Path(temporary),
                rounds=1,
            )
            result = asyncio.run(
                execute_workflow(
                    FakeEngine(config, require_revision=True),
                    run_dir,
                    source,
                    state,
                )
            )
            self.assertEqual(result, 2)
            self.assertEqual(
                load_state(run_dir).status,
                "human_review_required",
            )

    def test_interrupted_revision_adopts_existing_next_artifact(self) -> None:
        with TemporaryDirectory() as temporary:
            run_dir, source, state, config = self.create_fixture(Path(temporary))
            initial = make_artifact(
                TextArtifactContent(
                    title="Initial",
                    summary="Initial summary",
                    body_markdown="Initial body",
                ),
                1,
            )
            revised = make_artifact(
                TextArtifactContent(
                    title="Already saved revision",
                    summary="Revised summary",
                    body_markdown="Revised body",
                ),
                2,
            )
            save_artifact(run_dir, initial)
            save_artifact(run_dir, revised)
            save_reviews(
                run_dir,
                1,
                [
                    Review(
                        reviewer="quality",
                        artifact_sha256=initial.sha256,
                        verdict="changes_required",
                        blocking_findings=[
                            BlockingFinding(
                                id="F-1",
                                title="Revise",
                                requirement="R1",
                                evidence="Initial body",
                                risk="Incomplete",
                                recommendation="Revise it",
                            )
                        ],
                    )
                ],
            )
            state.current_version = 1
            state.status = "revising"
            save_state(run_dir, state)
            engine = FakeEngine(config)
            result = asyncio.run(execute_workflow(engine, run_dir, source, state))
            self.assertEqual(result, 0)
            self.assertEqual(engine.revise_calls, 0)
            self.assertEqual(load_state(run_dir).current_version, 2)

    def test_engine_passes_pdf_input_to_runner(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            pdf_path = root / "brief.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\nminimal")
            source = load_source(pdf_path, ["application/pdf"])
            config = resolve_run_config(root, "sample")
            engine = WorkflowEngine("designer-model", "reviewer-model", config)
            output = TextArtifactContent(
                title="PDF",
                summary="Summary",
                body_markdown="Body",
            )
            mocked = AsyncMock(return_value=SimpleNamespace(final_output=output))
            with patch("review_engine.agents.Runner.run", mocked):
                asyncio.run(
                    engine.create_initial_artifact(
                        source,
                        SimpleNamespace(),
                    )
                )
            runner_input = mocked.await_args.args[1]
            self.assertEqual(
                runner_input[0]["content"][0]["type"],
                "input_file",
            )


if __name__ == "__main__":
    unittest.main()
