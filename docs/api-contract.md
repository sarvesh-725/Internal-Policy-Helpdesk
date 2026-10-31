# API Contract

All authenticated endpoints require a Keycloak bearer access token. Responses omit raw guard input, prompts, model diagnostics, retrieved chunks, credentials, and internal errors.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/chat/threads` | Create a redacted conversation thread. |
| `POST /api/v1/chat/threads/{threadId}/messages` | Guard input, record a redacted message, and queue a graph run. |
| `GET /api/v1/chat/threads/{threadId}` | Read the owning user's safe messages and citations. |
| `GET /api/v1/chat/threads/{threadId}/events` | Fetch an authenticated SSE stream of allowlisted workflow states; supports `Last-Event-ID` for a safe reconnect cursor. |
| `GET /api/v1/review/tasks` | List mock review tasks matching the authenticated specialist role. |
| `GET /api/v1/review/tasks/{taskId}` | Read a mock case status as its owner or matching specialist. |
| `POST /api/v1/review/tasks/{taskId}/decision` | Approve, reject, or safely edit a mock response and resume its graph. |
| `POST /api/v1/admin/policies/ingest` | Ingest the fictional corpus; requires `policy_admin`. |
| `GET /api/v1/admin/audit-events` | Read redacted audit events and safe trace-correlation IDs; requires `system_admin`. |
| `POST /api/v1/feedback` | Record safe feedback for an owned thread. |
| `GET /healthz` | Liveness endpoint. |
| `GET /readyz` | Readiness endpoint; checks PostgreSQL and Qdrant without calling Gemini. |

The SSE stream can emit `request_received`, `identity_verified`, `classifying_request`, `searching_authorized_hr_policy`, `searching_authorized_it_policy`, `searching_authorized_operations_policy`, `preparing_cited_response`, `awaiting_specialist_review`, `review_decision_recorded`, and `completed`.

Each SSE payload contains only its event ID, request ID, timestamp, and an allowlisted status payload. It never includes a prompt, raw policy chunk, user message, tool result, token, or server diagnostic.

Thread details include only the owner’s latest safe mock-review status (`task_id`, lifecycle status, expiry, and required specialist role); specialist case summaries and reviewer identity are not exposed to the employee route.
