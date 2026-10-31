# Local Runbook

1. Copy `.env.example` to `.env`; leave `GEMINI_API_KEY` blank until Gemini-backed policy ingestion/retrieval is desired.
2. Copy `frontend/.env.example` to `frontend/.env` for public browser configuration. These values are not secrets.
3. Start the Compose runtime. The backend applies Alembic migrations before it starts serving requests.
4. Sign in with a fictional Keycloak account from `keycloak/nodeswarm-realm.json`.
5. A `policy_admin` may start fictional policy ingestion only after `GEMINI_API_KEY` is present. Invalid policies are quarantined in ingestion records instead of indexed.

Use `GET /healthz` for process liveness and `GET /readyz` for readiness. Readiness checks PostgreSQL and Qdrant; it deliberately does not require a Gemini key or call a model.

The browser portal exposes only the workspace tabs authorized by the signed-in role: policy support for all authorized users, the reviewer inbox for matching specialists, and administration controls for policy/system administrators.

## Operational constraints

- Do not paste a real API key, password, token, SSN, bank identifier, diagnosis, medical record, or personal employment data into the browser.
- Never set `LANGSMITH_TRACING=true` for non-synthetic content. The implementation sends redacted workflow metadata only, but the demonstration remains fictional-data-only.
- The workflow persists only a redacted identity context (subject hash, roles, and region) in LangGraph state and passes typed, minimum-necessary handoffs between domains. Review tasks are mock tasks with a 24-hour TTL. They cannot change a real record.
- Use a separate deployment configuration and secret manager before exposing the service outside local demonstration use.
- The local Compose database initializes a restricted `nodeswarm_app` runtime role. On a pre-existing local database volume, apply the role initialization and latest migration before starting the backend; a fresh local volume runs the initialization automatically.
