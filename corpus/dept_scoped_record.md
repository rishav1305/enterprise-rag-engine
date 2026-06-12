---
doc_id: dept-scoped-record
title: Engineering On-Call Incident Record (Department-Scoped)
allowed_roles: [ENGINEERING]
clearance_level: 2
sensitivity_class: G
need_to_know_roles: [ENGINEERING]
partial_for: [ON_CALL]
owner_department: Engineering
summary: A department-scoped engineering incident record — full to Engineering, row-scoped (partial) to on-call.
---
# Engineering On-Call Incident Record (Department-Scoped)

This incident record belongs to the Engineering vertical. It is governed by
need-to-know: the Engineering role sees it in full; an out-of-scope role that is on
the on-call rotation (ON_CALL) gets row-scoped PARTIAL access (the record is
admitted with a scope predicate, content withheld). Everyone else is denied.

Incident MER-4821: payments service latency spike at 14:02 UTC, component
payments-gateway, severity SEV-2, owning team Engineering. Root cause: a connection
pool exhaustion in the gateway. On-call paged at 14:05; mitigated by 14:31.

Full detail (root-cause analysis, the internal runbook link, and the affected
customer-impact estimate) is visible only to the Engineering need-to-know role; the
on-call cross-team responder sees a scoped summary.
