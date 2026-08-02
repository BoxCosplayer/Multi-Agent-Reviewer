---
name: review-architecture-ux
description: Review a software architecture for user journeys, responsiveness, accessibility implications, feedback states, error recovery, privacy expectations, consistency, and supportability. Use for independent UX review of architecture diagrams and design proposals.
---

# Review Architecture UX

Review how architectural choices affect complete user journeys, including
degraded and recovery states.

## Review checklist

- Trace primary journeys from user action to visible outcome.
- Check latency budgets, streaming behavior, progress feedback, and cancellation.
- Check empty, loading, stale, partial, offline, timeout, and failure states.
- Check authentication expiry, authorization denial, and recovery without lost
  work.
- Check accessibility implications of asynchronous updates and error handling.
- Check consistency across channels, devices, and repeated actions.
- Check privacy expectations, consent, audit visibility, and user control over
  sensitive data.
- Check administrator and support journeys needed to diagnose user problems.
- Check whether system limitations are communicated honestly and usefully.

## Finding policy

- Mark an issue blocking when a required journey cannot complete, predictably
  loses user work, violates an explicit accessibility or privacy expectation,
  or leaves users without a safe recovery path.
- Keep aesthetic preferences and optional refinements advisory.
- Tie each finding to a named user journey and visible consequence.
- Approve when no blocking issue remains.
