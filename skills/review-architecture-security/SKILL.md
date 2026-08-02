---
name: review-architecture-security
description: Review a software architecture for security, privacy, identity, authorization, trust boundaries, tenant isolation, secrets, auditability, data protection, abuse resistance, and supply-chain risk. Use for independent security review of architecture diagrams and design proposals.
---

# Review Architecture Security

Review defensively from the blueprint and visible design. Do not invent exploit
steps or claim controls that are absent.

## Review checklist

- Identify assets, actors, entry points, trust boundaries, and privileged paths.
- Verify authentication, session handling, authorization, and least privilege.
- Check tenant or business-unit isolation at retrieval, storage, cache, and log
  boundaries.
- Check encryption in transit and at rest, key ownership, secret storage, and
  rotation.
- Check input validation, content ingestion, untrusted data, and dependency
  boundaries.
- Check audit events, tamper resistance, administrative actions, and incident
  investigation needs.
- Check data minimization, retention, deletion, revocation, and privacy
  expectations.
- Check abuse resistance, rate controls, egress controls, and third-party risk.
- Check build, artifact, dependency, and deployment supply-chain controls.

## Finding policy

- Mark an issue blocking when it creates a credible path to unauthorized access,
  material data exposure, privilege escalation, or violation of an explicit
  security or privacy requirement.
- Tie each finding to evidence in the artifact and a concrete required outcome.
- Keep speculative hardening ideas advisory.
- Approve when no blocking issue remains.
