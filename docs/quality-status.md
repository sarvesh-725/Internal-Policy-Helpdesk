# Quality Status and Deferred Evaluation Work

Automated test execution, evaluation datasets, regression thresholds, and release gates are intentionally deferred at the user’s request. They are not implemented and must not be represented as complete.

Before any non-demo deployment, add and execute the following work:

| Area | Required evidence |
|---|---|
| Authorization | Deterministic tests proving role/region/document filters deny unauthorized retrieval and mock tools. |
| Safety | Guardrail cases for credentials, identifiers, medical/employment details, prompt injection, and unsafe reviewer edits. |
| Workflow | Graph route, handoff, step-limit, interruption, resume, expiry, and idempotency cases. |
| Retrieval | Corpus ingestion validation, Qdrant payload filtering, source re-authorization, and citation-verification cases. |
| UI/API | Authenticated request, SSE reconnect, thread ownership, reviewer role, audit-admin role, and safe-error tests. |
| Evaluation | Versioned synthetic golden cases for routing, evidence grounding, cross-domain handoffs, escalation, and failure handling. |
| Operations | Migration, readiness, configuration, secret scanning, log/trace redaction, and backup/restore verification. |

Suggested initial release gates are retained from the architecture baseline: all RBAC-violation cases deny access, all sensitive action cases escalate, every policy answer has at least one valid citation, and no tool call bypasses typed authorization.
