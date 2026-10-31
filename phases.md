# Dynamic Enterprise Support Swarm — Implementation Phases

This implementation plan follows `architecture.md`, with the project choices that best support the résumé narrative: React with JavaScript, Gemini for LLM calls, Qdrant for vector search, and HR, IT Support, and Operations as the three policy domains.

**Current implementation:** phases 1–15 are complete. Automated tests, evaluation datasets, regression thresholds, and release-gate execution remain intentionally deferred by request and are documented as incomplete quality work.

## Implementation constraints

- The product uses only fictional policies, synthetic profiles, and mock workflow actions.
- PostgreSQL owns relational application data, policy metadata, checkpoints, conversations, and audit events; Qdrant owns vector embeddings and filterable chunk payloads.
- `GEMINI_API_KEY` is configured only through server-side environment variables. It has a blank placeholder in `.env.example` and is never added to browser code or version control.
- The frontend is React + JavaScript. No TypeScript files, compiler configuration, or TypeScript tooling are introduced.
- No automated or manual test execution is included in these phases, by request. Evaluation datasets, test suites, and release gates stay deferred.

## Phase 1 — Repository and local runtime foundation

Create the repository layout and local Docker runtime: backend, frontend, Keycloak realm assets, fictional policy corpus, and documentation. Add Docker Compose services for PostgreSQL, Qdrant, Keycloak, the FastAPI backend, and the JavaScript React frontend. Establish `.env.example` with all runtime variables, including blank `GEMINI_API_KEY`, database credentials, Qdrant endpoint, Keycloak issuer/audience, model names, and workflow limits. Keep browser configuration limited to non-secret public values.

Deliverables: root Compose file, backend and frontend Dockerfiles, environment template, initial README, service-ignore files, and a JavaScript-only Vite/React shell.

## Phase 2 — PostgreSQL persistence foundation

Create the Python package, dependency manifest, typed configuration, SQLAlchemy engine/session lifecycle, declarative base, and Alembic migration environment. Model the system-of-record tables for policy metadata, document versions, access rules, synthetic employees, threads, messages, review tasks, checkpoints, feedback, and append-only audit events. Store vectors only in Qdrant; PostgreSQL policy chunks retain canonical text, citations, source hash, and Qdrant point identifier.

Deliverables: settings module, database lifecycle, ORM models, initial migration, repository boundaries, and persistent identifiers/timestamps designed for later auditability and durable graph execution.

## Phase 3 — FastAPI shell and safe API contracts

Build the FastAPI application factory and `/api/v1` router structure. Add request-ID middleware, CORS from explicit settings, JSON logging, safe error responses, health/readiness endpoints, database-session dependency, and Pydantic contracts for all future chat, review, admin, citation, audit, feedback, and SSE interactions. Implement only harmless initial endpoints in this phase: `GET /healthz` and `GET /api/v1/meta`.

Deliverables: runnable API shell, versioned route modules, standard response/error envelope, request correlation, and shared domain schemas without graph, retrieval, or model calls.

## Phase 4 — Keycloak identity and trusted user context

Create a Keycloak realm export with public/browser client configuration, backend audience, demo roles, synthetic users, and regional attributes. Implement bearer-token extraction, JWKS discovery/caching, issuer/audience/signature/expiry checks, realm/client role extraction, and conversion into immutable `UserContext`. Add route dependencies for authenticated user and role requirements. Never accept identity, role, region, or capability values from request bodies.

Deliverables: Keycloak realm JSON, JWT validation module, trusted auth dependencies, `GET /api/v1/auth/me`, and safe unauthorized/forbidden response behavior.

## Phase 5 — RBAC, ABAC, and per-request capabilities

Implement deterministic authorization rules for domain access, document audience, region, document state, action permissions, and specialist review responsibility. Build immutable `CapabilitySet` derivation from `UserContext`; the graph and every tool will receive this reduced capability set rather than raw role claims. Implement a policy-enforcement interface that later retrieval and mock tools must call before each operation.

Deliverables: role/domain matrix, document-access evaluator, capability factory, policy decision records, and authorization reason codes.

## Phase 6 — Curated HR, IT, and Operations knowledge corpus

Author a small, internally consistent fictional policy corpus in `knowledge/hr`, `knowledge/it`, and `knowledge/operations`. Require YAML front matter for document ID, title, domain, allowed roles, allowed regions, effective date, version, status, owner role, and review date. Add policy examples that demonstrate general employee-visible content and specialist-only content without using real employee data.

Deliverables: versioned fictional Markdown policies, corpus conventions, source hashing, and metadata validation contract.

## Phase 7 — Ingestion and Qdrant indexing

Implement a controlled ingestion command. It discovers policy files, validates metadata, extracts Markdown/PDF text, performs structure-aware chunking, rejects duplicate active versions, stores canonical metadata and chunk text in PostgreSQL, obtains embeddings through a Gemini embedding adapter, and upserts Qdrant points with server-owned payload fields. Invalid documents are recorded as quarantined and never indexed.

Deliverables: ingestion service/command, document validators, chunking strategy, Gemini embedding gateway, Qdrant collection bootstrap, ingestion report, and metadata-to-point mapping.

## Phase 8 — Authorized retrieval gateway and citations

Create `search_policy` as the only policy-retrieval path. Resolve permitted published document/version IDs in PostgreSQL first; build Qdrant query filters from the trusted capability set and allowed identifiers; re-check each result against PostgreSQL; then return only bounded authorized chunks. Define stable citations with document ID, title, version, effective date, section, excerpt, and score.

Deliverables: retrieval gateway, Qdrant payload filter builder, result re-authorization, citation factory, query normalization, and bounded evidence results.

## Phase 9 — Input safety and prompt-injection defenses

Implement request size/type limits, Presidio analyzers, custom restricted-data recognizers, deterministic redaction placeholders, sensitive employment/medical handling, and prompt-injection signal classification. Convert accepted input into a redacted safe request representation before it can reach persistence, Gemini, LangSmith, or LangGraph. Block or escalate unsafe requests using typed risk flags and audited categories, never raw captured values.

Deliverables: guard pipeline, redaction service, safe-request contract, risk taxonomy, and secure audit metadata builder.

## Phase 10 — Gemini model gateway and prompt modules

Implement a provider-isolated Gemini gateway for structured route plans, domain findings, and final generation. Use `GEMINI_API_KEY`, `LLM_ROUTER_MODEL`, and `LLM_SYNTHESIS_MODEL` only in backend settings. Build versioned prompts that label user content and retrieved policy chunks as data, require strict schema output, prohibit tool/permission invention, and keep contexts narrow.

Deliverables: Gemini SDK adapter, structured-output parsing/repair boundary, prompt modules, request metadata redaction, and model failure categories.

## Phase 11 — Controlled LangGraph orchestration

Implement the global support state, private subgraph state, and the controlled hub-and-spoke graph: request validation, guard, triage, clarification, HR/IT/Operations dispatch, finding orchestration, response validation, escalation, reviewer wait, and safe response. Enforce deterministic post-triage policy decisions, a two-handoff limit, eight-step limit, bounded retries, and explicit escalation reasons.

Deliverables: LangGraph state schemas, route controller, bounded execution configuration, checkpoint hooks, and typed workflow outcomes.

## Phase 12 — HR, IT, and Operations subgraphs

Implement the three narrowly scoped domain subgraphs. Each receives a `DomainTaskEnvelope`, invokes only the permitted retrieval gateway, creates a cited `DomainFinding`, and returns a minimal safe summary. The orchestrator alone decides cross-domain sequencing. Build `HandoffEnvelope` construction so, for example, HR can pass a leave category and citation IDs to Operations without passing medical details, raw chunks, full message history, or individual operational records.

Deliverables: HR, IT, and Operations prompts/schemas/subgraphs; finding/citation validation; and minimum-necessary cross-domain handoffs.

## Phase 13 — Response safety, mock tools, and human review

Implement final response validation: all material policy claims require authorized citations, individual decisions trigger escalation, and sensitive/internal content is excluded. Add only mock adapters for review-task creation, task-status lookup, reviewer resume, and minimal current-user synthetic context. Add PostgreSQL-backed review tasks, graph interrupt/resume, specialist role checks, expiration handling, idempotency keys, and append-only audit events with SHA-256 hash chaining.

Deliverables: cited safe response builder, mock tool registry, durable review queue, reviewer resume flow, and tamper-evident audit chain.

## Phase 14 — API, SSE, and React JavaScript portal

Implement thread/message, review, policy-ingest, audit, and feedback endpoints. Add safe SSE statuses only. Build the React JavaScript portal with Keycloak login, employee chat, citation drawer, escalation status, specialist review inbox/decision view, policy ingestion report, scoped audit explorer, and feedback controls. The UI renders only approved safe responses and citation metadata; it never decides permissions or stores server secrets.

Deliverables: complete API surface, SSE stream, JavaScript React feature modules, authenticated routing, employee/reviewer/admin views, and safe API client.

## Phase 15 — Observability, documentation, and deferred quality work

Add request-correlated structured logs, OpenTelemetry hooks, and opt-in redacted LangSmith tracing. Complete the README, threat model, API contract, data-handling guide, runbook, and portfolio explanation focused on the résumé-oriented stack: FastAPI, React JavaScript, Keycloak/JWT/RBAC, LangGraph, Gemini, Qdrant RAG, PostgreSQL, LangSmith, and SSE. Keep all tests, evaluation cases, and release thresholds explicitly deferred until requested.

Deliverables: redacted observability adapters, operator documentation, architecture-to-implementation cross-reference, and clear demo-scope limitations.
