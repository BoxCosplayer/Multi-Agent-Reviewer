---
name: review-architecture-dx
description: Review a software architecture for developer experience, API ergonomics, integration clarity, local development, debugging, documentation, delivery complexity, versioning, and service ownership. Use for independent DX review of architecture diagrams and design proposals.
---

# Review Architecture DX

Review the design from the perspective of engineers who must build, integrate,
debug, deploy, and operate it.

## Review checklist

- Check component ownership and whether responsibilities are understandable.
- Check API contracts, schemas, errors, idempotency, compatibility, and
  versioning.
- Check local development, test environments, fixtures, and dependency setup.
- Check discoverability through documentation, examples, and service catalogs.
- Check debugging across boundaries through correlation IDs, logs, traces, and
  actionable errors.
- Check deployment coupling, configuration burden, migrations, and rollback.
- Check integration onboarding, authentication setup, sandboxing, and feedback
  loops.
- Check whether operational ownership and escalation paths are clear.
- Flag accidental complexity that is not justified by a requirement.

## Finding policy

- Mark an issue blocking when the design is infeasible to implement or operate
  safely, or when a required integration lacks a workable contract.
- Keep convenience improvements and stylistic preferences advisory.
- State the developer task or journey affected by each finding.
- Approve when no blocking issue remains.
