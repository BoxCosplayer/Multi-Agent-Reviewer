---
name: design-architecture
description: Design or revise reviewable software architecture from a product or technical blueprint. Use for architecture diagrams, component boundaries, data flows, trust boundaries, deployment topology, architectural decisions, assumptions, and reviewer-driven revisions.
---

# Design Architecture

Turn the blueprint into a concrete architecture that independent reviewers can
evaluate without guessing.

## Workflow

1. Extract goals, users, constraints, data classifications, scale, and quality
   attributes from the blueprint.
2. Record missing information as explicit assumptions. Do not silently invent
   requirements.
3. Define component responsibilities and ownership boundaries.
4. Show synchronous and asynchronous data flows, protocols, storage, external
   systems, and trust boundaries.
5. Cover deployment, observability, failure handling, recovery, and security
   controls in proportion to the blueprint.
6. Prefer the simplest design that satisfies the stated constraints.
7. Put a complete Mermaid `flowchart` in a fenced `mermaid` block within
   `body_markdown`.
8. Record consequential trade-offs in decisions.

## Revision rules

- Treat each blocking review finding as a requirement to resolve or rebut with
  concrete evidence.
- Preserve unaffected sound decisions.
- Update the whole Markdown artifact so the diagram and narrative remain
  consistent.
- Add a concise change-log entry for each material revision.
- Never claim reviewer approval; only the orchestrator determines consensus.

## Quality bar

- Every important arrow has a meaningful direction and purpose.
- Every data store identifies the class of data it owns.
- Authentication, authorization, and tenant or business-unit boundaries are
  visible where relevant.
- Critical dependencies and failure paths are explicit.
- Assumptions are testable and decisions state their trade-offs.
