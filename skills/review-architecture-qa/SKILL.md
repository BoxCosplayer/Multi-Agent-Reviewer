---
name: review-architecture-qa
description: Review a software architecture for correctness, testability, reliability, operability, scalability, recoverability, and acceptance-criteria coverage. Use for independent QA review of architecture diagrams and design proposals.
---

# Review Architecture QA

Review independently and report only evidence-based issues.

## Review checklist

- Trace every stated capability to one or more components and data flows.
- Check load, latency, concurrency, capacity, and growth assumptions.
- Check timeouts, retries, idempotency, backpressure, and partial failure.
- Check deployment safety, rollback, configuration, migrations, and dependency
  compatibility.
- Check monitoring, logs, metrics, traces, health signals, and alert ownership.
- Check backup, restore, disaster recovery, retention, and data reconciliation.
- Check whether critical behavior is testable in isolation and end to end.
- Check whether success criteria can be measured.

## Finding policy

- Mark an issue blocking only when the architecture cannot reliably satisfy a
  stated requirement or a necessary operational property.
- Cite the affected requirement and visible architectural evidence.
- State the concrete risk and the minimum outcome a correction must achieve.
- Put useful but nonessential improvements in advisory notes.
- Approve when no blocking issue remains.
