# Multi-Agent Architecture Review

This command-line application turns a blueprint into a Mermaid software
architecture, sends the exact artifact to four independent reviewers in
parallel, and returns blocking feedback to the same architect session until all
reviewers approve or the review-round limit is reached.

The reviewers cover:

- QA and operability
- Security and privacy
- Developer experience
- User experience

Consensus is determined by Python code, not by an agent. Every reviewer must
approve the same artifact SHA-256 with no blocking findings.

## How it works

1. The architecture agent creates version 1 from the blueprint.
2. Its conversation history is stored in a file-backed Agents SDK
   `SQLiteSession`.
3. QA, Security, DX, and UX agents review the same immutable artifact in
   parallel. Reviewers do not share sessions or see each other's answers.
4. If any reviewer requests changes, all blocking findings return to the
   architecture agent in its original session.
5. A complete new version is created and all reviewers run again.
6. The workflow ends when all reviewers approve or the maximum number of
   review rounds is reached.

The application loads each local `skills/*/SKILL.md` file into the relevant
agent's instructions. This provides reusable skill behavior without requiring
Codex skill discovery. If a skill needs executable tools later, add those tools
to the corresponding Agents SDK `Agent`.

## Prerequisites

- Python 3.10 or newer
- An OpenAI Platform API key
- Network access to the OpenAI API
- An OpenAI project with access to the configured models

This uses API billing. It does not use a ChatGPT subscription allowance. A run
uses at least one architect call plus four parallel reviewer calls. Each
revision adds another architect call and another four reviews.

The default model is `gpt-5.6`. Set `OPENAI_MODEL` or
`OPENAI_REVIEW_MODEL` if your project uses a different available model.

## Windows setup

Open PowerShell:

```powershell
Set-Location -LiteralPath '[Path]'

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env
```

Add the API key to `.env`:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-5.6
OPENAI_REVIEW_MODEL=gpt-5.6
```

The `.env` file and generated runs are excluded by `.gitignore`.

Verify the local setup without making an API call:

```powershell
python multi_agent_review.py --check
```

## Run the example

```powershell
python multi_agent_review.py examples\blueprint.md
```

Limit the workflow to two review rounds:

```powershell
python multi_agent_review.py examples\blueprint.md --max-rounds 2
```

Give a new run a stable ID:

```powershell
python multi_agent_review.py examples\blueprint.md --run-id support-assistant
```

Run your own blueprint:

```powershell
python multi_agent_review.py 'C:\path\to\blueprint.md'
```

## Resume an interrupted run

The program prints the run ID when it starts. Resume it with:

```powershell
python multi_agent_review.py --resume 20260802T120000Z-a1b2c3d4
```

If a run stopped because it reached its round limit, increase the limit:

```powershell
python multi_agent_review.py `
  --resume 20260802T120000Z-a1b2c3d4 `
  --max-rounds 8
```

The saved blueprint is hashed. If it changes, the application refuses to resume
the old run; start a new run so reviews cannot accidentally refer to mixed
requirements.

## Run output

Each execution is stored under `runs/<run-id>/`:

```text
runs/<run-id>/
├── blueprint.md
├── state.json
├── architect-session.db
├── architecture-v1.json
├── architecture-v1.mmd
├── reviews-v1.json
├── architecture-v2.json
├── architecture-v2.mmd
├── reviews-v2.json
└── decision.json
```

- `architecture-vN.mmd` is the Mermaid diagram.
- `architecture-vN.json` contains the diagram and design narrative.
- `reviews-vN.json` contains the four structured reviews.
- `architect-session.db` preserves the architect conversation across revisions
  and process restarts.
- `decision.json` records approval or human-review escalation.

Paste an `.mmd` file into the
[Mermaid Live Editor](https://mermaid.live/) or use a Mermaid-compatible editor
to render it.

## Customise the skills

Edit:

```text
skills/
├── design-architecture/SKILL.md
├── review-architecture-qa/SKILL.md
├── review-architecture-security/SKILL.md
├── review-architecture-dx/SKILL.md
└── review-architecture-ux/SKILL.md
```

Changes apply to new process invocations. Existing run artifacts are never
silently rewritten, but a resumed run will use the current skill text for its
next model call. For strict audit reproducibility, copy the skills into each run
or record their hashes before production use.

## Operational notes

- The architect session is persistent; reviewers are intentionally stateless.
- Reviews are parallelized with `asyncio.gather`.
- A model cannot declare consensus. The application checks reviewer identity,
  artifact hash, verdict, and blocking findings.
- If the process stops during a model call, resume the run. The current artifact
  remains intact; the incomplete review round may be repeated.
- SQLite is suitable for local use. Use a production session backend such as
  SQLAlchemy/PostgreSQL before running this across multiple workers.
- There is no cross-process lock. Do not resume the same run from two processes
  at once.
- A maximum-round limit prevents an unbounded agent loop.

## Further reading

- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Agents SDK sessions](https://openai.github.io/openai-agents-python/sessions/)
- [Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/)
- [OpenAI API keys](https://platform.openai.com/api-keys)
