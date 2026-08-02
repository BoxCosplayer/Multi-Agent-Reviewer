# Multi-Agent Design Review

This command-line application turns a text or PDF source document into a
reviewable Markdown artifact, sends the exact artifact and source to independent
reviewers in parallel, and returns blocking feedback to the same designer
session until every selected reviewer approves or the review-round limit is
reached.

Designers, reviewers, profiles, and skills are configuration-driven. The
included `architecture` profile preserves the original software-architecture
workflow, but new artifact types do not require Python changes.

Consensus is determined by Python code. Every reviewer must approve the same
artifact SHA-256 with no blocking findings.

## Setup

Requires Python 3.10 or newer, network access, and an OpenAI Platform API key.
This uses API billing rather than a ChatGPT subscription allowance.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. `OPENAI_MODEL` controls designers and
`OPENAI_REVIEW_MODEL` optionally selects a different reviewer model.

Validate every registry, profile, skill, and agent definition without making an
API call:

```powershell
python multi_agent_review.py --check
```

List available agents:

```powershell
python multi_agent_review.py --list-designers
python multi_agent_review.py --list-reviewers
```

## Run a design review

New runs require an explicit designer. The designer name also selects the
same-named profile:

```powershell
python multi_agent_review.py `
  --designer architecture `
  examples\blueprint.md
```

PDF sources use the same command:

```powershell
python multi_agent_review.py `
  --designer architecture `
  'C:\path\to\blueprint.pdf'
```

The original PDF is sent directly as a Responses API `input_file`; the API
provides its extracted text and page images to vision-capable models. PDFs must
be smaller than 50 MB. Diagram-heavy PDFs can consume substantially more input
tokens than text because page images are included. See the
[OpenAI file-input guide](https://developers.openai.com/api/docs/guides/file-inputs).

Replace the profile's default reviewers with any registered set:

```powershell
python multi_agent_review.py `
  --designer architecture `
  --reviewers security,performance `
  examples\blueprint.md
```

Other useful options:

```powershell
python multi_agent_review.py `
  --designer architecture `
  --run-id support-assistant `
  --max-rounds 2 `
  examples\blueprint.md
```

## Resume a run

The program prints the run ID when it starts:

```powershell
python multi_agent_review.py --resume 20260802T120000Z-a1b2c3d4
```

Increase the round limit when continuing a run that required human review:

```powershell
python multi_agent_review.py `
  --resume 20260802T120000Z-a1b2c3d4 `
  --max-rounds 8
```

Do not pass `--designer` or `--reviewers` when resuming. A run freezes its
profile, selected agents, ordered skill paths, and complete skill text. Editing
project configuration affects new runs only. Runs created by the old
architecture-only state format cannot be resumed; start a new profile-based
run.

## Configuration

`designers.json` defines reusable designers and their base skills:

```json
[
  {
    "name": "architecture",
    "label": "Architecture Designer",
    "skills": [
      "skills/design-core/SKILL.md"
    ]
  }
]
```

`reviewers.json` defines reusable reviewer concerns:

```json
[
  {
    "name": "security",
    "label": "Security",
    "skills": [
      "skills/review-core/SKILL.md",
      "skills/review-security/SKILL.md"
    ]
  }
]
```

Each designer has exactly one matching file under `profiles/`. The filename,
profile `name`, and `designer` must match:

```json
{
  "name": "architecture",
  "label": "Software Architecture",
  "designer": "architecture",
  "reviewers": ["qa", "security", "dx", "ux", "performance"],
  "designer_skills": [
    "skills/design-architecture/SKILL.md"
  ],
  "reviewer_skills": {
    "security": [
      "skills/review-architecture-security/SKILL.md"
    ]
  },
  "accepted_blueprint_types": [
    "text/plain",
    "text/markdown",
    "application/pdf"
  ],
  "pdf_detail": "auto"
}
```

Skill paths are ordered, relative paths under `skills/`, and must end in
`SKILL.md`. Instructions compose in this order:

1. Non-editable application invariants.
2. Base skills from the designer or reviewer registry.
3. Domain overlays from the selected profile.

`pdf_detail` accepts `auto`, `low`, or `high`.

## Add a designer and profile

1. Create its generic and domain-specific `SKILL.md` files under `skills/`.
2. Add the designer and its base skill paths to `designers.json`.
3. Create `profiles/<designer-name>.json`.
4. Select the profile's default reviewers and optional per-reviewer domain skill
   overlays.
5. Run `python multi_agent_review.py --check`.
6. Start it with `--designer <designer-name>`.

Every designer returns the same structured text contract: title, summary,
Markdown body, assumptions, decisions, and change log. This makes new designers
configuration-only while retaining deterministic revision and rendering.

## Add a reviewer

1. Create one or more generic reviewer skills under `skills/`.
2. Add the reviewer and ordered base skill paths to `reviewers.json`.
3. Add it to a profile's default `reviewers` list when desired.
4. Optionally add domain-specific paths under the profile's
   `reviewer_skills`.
5. Run `python multi_agent_review.py --check`.

A reviewer chosen with `--reviewers` but absent from the profile uses its
registry skills without a domain overlay.

## Run output

Each execution is stored under `runs/<run-id>/`:

```text
runs/<run-id>/
├── source.md or source.pdf
├── source.json
├── state.json
├── designer-session.db
├── config/
│   ├── profile.json
│   ├── designer.json
│   ├── reviewers.json
│   ├── skills.json
│   └── manifest.json
├── artifact-v1.json
├── artifact-v1.md
├── reviews-v1.json
└── decision.json
```

The JSON artifact is the hashed structured source of truth.
`artifact-vN.md` is its deterministic human-readable rendering. Reviewers are
stateless and independently receive the same immutable artifact and source;
the designer session persists across revisions and restarts.

## Tests

```powershell
python -m unittest discover -s tests -v
python multi_agent_review.py --check
```

The suite does not call the OpenAI API. A live run is the optional PDF smoke
test when an API key and billing are available.
