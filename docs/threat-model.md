# Threat Model

This project demonstrates a constrained policy-navigation assistant using fictional data only. It is not a compliance certification and must never receive real employee records, credentials, medical data, or production policy material.

| Threat | Control |
|---|---|
| Spoofed browser role | FastAPI validates Keycloak issuer, audience, signature, expiry, and claims; request bodies never carry trusted roles. |
| Unauthorized policy retrieval | PostgreSQL resolves permitted documents first; Qdrant receives a server-built payload filter; every result is re-authorized after retrieval. |
| Sensitive input leakage | The request guard redacts identifiers before state/model/tracing access, blocks credentials and restricted identifiers, and reduces medical/employment details to a generic escalation placeholder. |
| Prompt injection | User and policy content are treated as untrusted data; prompts are separated from references; outputs use schemas; models cannot select tools, SQL, URLs, or permissions. |
| Cross-domain oversharing | HR, IT, and Operations subgraphs receive a redacted question and their own authorized evidence only. The orchestrator transfers typed findings, not raw local state. |
| Hallucinated policy | Domain findings may cite only supplied authorized references. Final policy prose requires at least one authorized citation. Missing evidence escalates. |
| Uncited reviewer claim | Reviewer edits are limited to a safe process-status message; policy claims remain the graph's cited-output responsibility. |
| Human-review replay | PostgreSQL-backed LangGraph checkpoints use stable thread IDs. Reviewer decisions are role-checked, stored as mock actions, audited, and resumed with a typed payload. |
| Audit tampering | Events are hash-chained under a database transaction lock. The FastAPI runtime uses a separate database role whose `UPDATE` and `DELETE` privileges on `audit_events` are revoked. |
| Observability leakage | Logs, OpenTelemetry spans, and optional LangSmith events carry IDs, categories, statuses, and prompt versions only—never raw prompts, chunks, credentials, or generated text. |

## Explicit boundaries

- No real external HR, IT, payroll, access-control, medical, legal, or Operations write is implemented.
- Qdrant is not an authorization system; it is queried only after PostgreSQL authorization and is always re-checked afterward.
- A model cannot grant access, override a guard, or decide an individual outcome.
