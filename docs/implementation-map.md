# Architecture-to-Implementation Map

| Architecture concern | Implementation location |
|---|---|
| Keycloak/JWT identity | `backend/app/auth/` and `keycloak/nodeswarm-realm.json` |
| RBAC/ABAC capability enforcement | `backend/app/policy/` |
| Input DLP and prompt safety | `backend/app/safety/` |
| Fictional corpus ingestion | `knowledge/`, `backend/app/retrieval/policy_source.py`, `ingestion.py` |
| Qdrant vector store and authorized RAG | `backend/app/retrieval/qdrant_store.py`, `gateway.py` |
| Gemini adapter and prompt contracts | `backend/app/llm/`, `backend/app/domains/` |
| Controlled LangGraph workflow | `backend/app/graph/` |
| Mock human review and audit chain | `backend/app/tools/`, `backend/app/services/review.py`, `backend/app/audit/` |
| REST/SSE API and JavaScript React portal | `backend/app/api/`, `frontend/src/` |
| Redacted logs, OpenTelemetry, LangSmith lifecycle metadata | `backend/app/observability/` |

## Portfolio description

Built a full-stack fictional enterprise policy-support system using Python, FastAPI, React with JavaScript, PostgreSQL, Qdrant, Keycloak, JWT/RBAC, LangGraph, Gemini, LangSmith, and SSE. The application routes HR, IT Support, and Operations questions through authorized retrieval and typed domain handoffs; produces cited policy explanations; and escalates individual or sensitive requests to a durable mock specialist-review workflow. It deliberately excludes production PII, live enterprise integrations, autonomous record changes, and compliance-certification claims.
