# Observability and Trace Boundaries

This project distinguishes product audit records from engineering telemetry. Neither is a substitute for compliance monitoring or incident response in a production environment.

## Correlation model

Each HTTP request receives a server-generated or client-supplied `X-Request-ID`. The backend creates an OpenTelemetry request span and derives a trace ID; both appear in the structured request-completion log. The request ID and trace ID are correlation identifiers only; they contain no user message, document text, JWT, credential, or model output.

| Signal | Store / transport | Allowed fields | Explicitly excluded |
|---|---|---|---|
| Structured application log | stdout JSON | request ID, method, path, status, duration | Headers, query text, body, JWT, exceptions, model text |
| OpenTelemetry span | configured OTLP endpoint | request ID, safe workflow event, lifecycle status | Prompts, policy chunks, retrieval scores, response text, personal data |
| LangSmith opt-in event | LangSmith project | request ID, event name, status, trace ID | Prompt, completion, retrieved content, user input, raw tool output |
| Audit event | PostgreSQL `audit_events` | actor subject hash, role names, action, redacted categories, trace ID | Raw personal values, JWTs, chain-of-thought, secret values |
| Browser SSE | authenticated owner stream | event ID, request ID, timestamp, allowlisted UI state | Any internal diagnostics or evidence body |

## Runtime configuration

`OTEL_EXPORTER_OTLP_ENDPOINT` is optional. When blank, spans remain process-local and no collector is contacted. `LANGSMITH_TRACING` defaults to `false`; it should only be enabled for synthetic data and only with `LANGSMITH_API_KEY` configured server-side.

The implementation emits redacted LangSmith lifecycle events directly rather than automatically tracing Gemini prompts. This preserves phase-15 operational correlation without expanding the sensitive-data boundary.

## Operational queries

- Use `X-Request-ID` to correlate a browser/API response with its structured application log.
- Use the trace ID in a redacted audit event to associate a workflow decision with OpenTelemetry/LangSmith lifecycle metadata.
- Use the system-admin audit explorer for business workflow decisions; use service logs or the configured telemetry backend for latency and availability diagnosis.

## Safety rules

- Do not enable a generic SDK auto-capture setting that uploads request bodies, response bodies, headers, prompts, completions, or database statements.
- Do not use raw error text as an observability attribute. The API logs only a fixed failure message for unhandled exceptions.
- Treat LangSmith, an OTLP collector, and any log aggregation destination as controlled external services.
