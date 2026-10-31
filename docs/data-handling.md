# Data Handling and Retention

The project is a fictional-data demonstration. Its schemas and retention values describe the intended local demo behavior; they do not create legal, regulatory, or contractual obligations.

| Data category | Storage boundary | Allowed content | Intended demo retention |
|---|---|---|---|
| Policy source | Repository / local mount | Fictional versioned Markdown/PDF policies | Kept with repository |
| Policy metadata and chunks | PostgreSQL + Qdrant payload metadata | Authorized fictional policy text and versions | Kept until source is replaced/reset |
| Conversation message | PostgreSQL | Guard-redacted user text and safe response only | 30 days or local reset |
| Graph checkpoint | PostgreSQL LangGraph tables | Redacted workflow state, hashes, domains, citations | 30 days or local reset |
| Mock review task | PostgreSQL | Safe case summary, role, lifecycle decision | 30 days after completion |
| Audit event | PostgreSQL | Subject hash, roles, reason codes, redacted metadata | 90 days or local reset |
| Telemetry | Configured service | IDs, event names, status, timing | Service/operator policy; synthetic data only |

## Before external model or trace access

The request guard runs before LangGraph, Gemini, LangSmith, or telemetry receives request-derived data. It redacts identifiers; blocks credentials and restricted identifiers; and converts sensitive medical or employment content to a generic escalation representation.

Retrieved policy text is authorized server-side. It can reach Gemini only through a scoped domain prompt. It is never placed in audit events, structured logs, SSE payloads, or the redacted LangSmith lifecycle event.

## Reset and deletion

The local Compose volume is a development convenience, not a retention system. To reset fictional demo data, use an explicit local-environment reset procedure outside the application. Do not add automated destructive retention jobs until their target database and operational authority are explicitly defined.
