---
name: review-architecture-performance
description: Review a software architecture for latency, throughput, capacity, scalability, resource efficiency, load resilience, and performance observability. Use for independent performance review of architecture diagrams and design proposals.
---

# Review Architecture Performance

Review independently and report only evidence-based performance issues.

## Review checklist

- Trace performance-sensitive user journeys and system flows end to end.
- Check stated latency, throughput, concurrency, and capacity requirements.
- Check scaling boundaries, bottlenecks, serialization points, and hot paths.
- Check caching strategy, invalidation, batching, pagination, and data access.
- Check synchronous dependencies, network hops, queues, and backpressure.
- Check resource limits for compute, memory, storage, connections, and workers.
- Check behavior under load spikes, degraded dependencies, and retry storms.
- Check performance testability, representative workloads, metrics, and budgets.

## Finding policy

- Mark an issue blocking when the architecture cannot credibly meet an explicit
  performance requirement or lacks a necessary control for predictable load.
- Cite the affected requirement and visible architectural evidence.
- State the measurable risk and the minimum outcome a correction must achieve.
- Keep speculative optimizations and tuning preferences advisory.
- Approve when no blocking issue remains.
