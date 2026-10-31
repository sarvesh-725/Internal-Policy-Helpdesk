# Dynamic Enterprise Support Swarm — System Architecture

> **Status:** Design baseline for a portfolio-grade SDE-1 project  
> **Primary goal:** Securely answer internal employee policy questions across HR, IT, and Operations by routing to specialized LangGraph subgraphs, retrieving only authorized policy content, and escalating high-risk cases to a human-review workflow.  
> **Scope rule:** This system uses fictional policy documents and synthetic employee profiles. It is a privacy-by-design demonstration, **not** a claim of GDPR, HIPAA, SOC 2, legal, medical, HR, or financial compliance.

---

## 1. Executive summary

Employees routinely ask questions that cross departmental boundaries:

> “If I begin medical leave today, what operations policy applies to the workflow I need to follow?”

The problem is not simply generating a fluent answer. A reliable internal support system must:

1. Identify the relevant departments.
2. Preserve the employee's verified identity and access scope through every step.
3. Retrieve policy content the employee is authorized to see.
4. Prevent sensitive data from entering prompts, logs, and traces unnecessarily.
5. Pass only the minimum required context between domain agents.
6. Cite the policy evidence used in an answer.
7. Refuse or escalate requests that require a person to make an individual HR, operations, legal, medical, payroll, or access-control decision.

This architecture deliberately uses a **controlled hub-and-spoke LangGraph workflow**, rather than an unconstrained agent swarm. The orchestrator controls every transition; domain agents cannot independently call other domain agents, gain new permissions, or perform real-world writes.

### 1.1 Product boundary

| In scope | Explicitly out of scope |
|---|---|
| Read-only policy explanations with policy citations | Determining an individual employee's actual leave, pay, operations outcome, tax, or legal outcome |
| HR Leave, IT Support, and Operations policy domains | Live enterprise-system integrations |
| Simulated roles, employee profiles, support tickets, and approvals | Real employee PII, medical records, credentials, or production company documents |
| RBAC-filtered retrieval and mock tool actions | Autonomous changes to employee records, leave, operational records, or permissions |
| Human-review queue and durable pause/resume | Multi-region/high-availability infrastructure |
| Tests, evaluation datasets, tracing, and audit events | Compliance certification or legal advice |

### 1.2 Design principles

- **Policy, not personal-record decisions:** Explain policy; do not adjudicate an individual's entitlement.
- **Authorization is deterministic:** The API and retrieval gateway enforce permissions. The LLM is never an authorization engine.
- **Least privilege:** Each subgraph receives a narrow capability set and only the context it needs.
- **Evidence before prose:** A policy answer needs retrieved, versioned, authorized citations. No evidence means clarification or escalation.
- **Typed interfaces:** Routing, handoffs, tool calls, responses, and audit events use validated schemas.
- **Safe failure:** Ambiguity, conflicts, missing sources, unsafe content, and system limits result in an escalation—not a guess.
- **Observability without oversharing:** Logs and traces use redacted payloads and stable IDs rather than raw sensitive content.
- **Build simple first:** One deployable backend and one database in Docker Compose. Future components have clear extension points but are not required in the first milestone.

---

## 2. Architecture at a glance

```mermaid
flowchart TB
    Employee[Employee / Manager / Support Specialist]
    Browser[Web portal\nReact + JavaScript]
    IdP[Keycloak\nOIDC + JWT + roles]
    API[FastAPI application\nAuth, session, SSE]
    Guard[Request guardrail pipeline\nRate limit · DLP · intent safety]
    Graph[LangGraph orchestrator\nHub-and-spoke workflow]
    HR[HR Leave subgraph]
    IT[IT Support subgraph]
    OPS[Operations subgraph]
    Review[Human-review subgraph\nMock approval queue]
    Policy[Policy & authorization layer\nRBAC / ABAC rules]
    Retrieve[Retrieval gateway\nACL-filtered RAG]
    VDB[(PostgreSQL + Qdrant\nPolicies, users, checkpoints, audits)]
    Docs[Versioned fictional policy corpus\nMarkdown / PDF]
    Model[LLM provider adapter\nSmall router + stronger synthesizer]
    Trace[LangSmith\nRedacted graph traces + evals]
    OTel[OpenTelemetry SDK / Collector]
    Metrics[Prometheus + Grafana\nBuild later]

    Employee --> Browser
    Browser -->|OIDC login| IdP
    Browser -->|JWT + request| API
    API --> Guard --> Graph
    Graph --> HR
    Graph --> IT
    Graph --> OPS
    Graph --> Review
    Graph --> Policy
    HR --> Retrieve
    IT --> Retrieve
    EQ --> Retrieve
    Retrieve --> Policy
    Retrieve --> VDB
    Docs -->|ingestion pipeline| VDB
    Graph --> Model
    Graph -. redacted traces .-> Trace
    API -. telemetry .-> OTel
    OTel -. build later .-> Metrics
    Graph -->|checkpoints / audit events| VDB
```

---

## 3. Logical system context

### 3.1 Actors

| Actor | Permitted purpose | Prohibited purpose |
|---|---|---|
| Employee | Ask about generally available policies and their own process | Access another employee's data; request a final individual decision |
| Manager | Ask about manager-visible process and team policy | View subordinate medical details, compensation, operations-case details, or private cases |
| HR specialist | Review escalations and HR-scoped mock cases | Access IT-only secrets or alter unrelated records |
| IT support specialist | Review IT escalations and mock access tickets | Access medical, compensation, or operations-case information |
| Operations specialist | Review operations escalations and mock workflow cases | Make unapproved changes to an operational record or compensation record |
| System administrator | Manage policy documents, roles, and system configuration | Read raw private conversations unless separately authorized |

### 3.2 Trust zones

```mermaid
flowchart LR
    subgraph Z1[Client zone]
      U[Browser]
    end
    subgraph Z2[Application trust boundary]
      A[FastAPI]
      G[Guardrails]
      L[LangGraph]
      P[Policy Enforcement Point]
    end
    subgraph Z3[Data zone]
      DB[(PostgreSQL + Qdrant)]
      OS[Optional MinIO object storage\nBuild later]
    end
    subgraph Z4[Controlled external services]
      I[Keycloak]
      M[LLM provider]
      S[LangSmith redacted tracing]
    end

    U -->|TLS, JWT| A
    A --> G --> L
    L --> P --> DB
    A --> I
    L -->|redacted / minimized prompt| M
    L -->|redacted traces only| S
    DB -. future document blobs .-> OS
```

Rules across trust zones:

- Browser input is untrusted, including user-provided role claims, links, pasted policies, and instructions embedded in documents.
- Only Keycloak-issued, signature-validated JWT claims become `UserContext`.
- The retrieval gateway, not the LLM, decides whether a document chunk is visible.
- The LLM provider receives a minimized prompt, never raw database records or access tokens.
- LangSmith receives redacted traces only in this project; disable external tracing when testing any non-synthetic data.
- Database credentials, OIDC secrets, model keys, and trace keys remain server-side.

---

## 4. Container/component architecture

```mermaid
flowchart TB
    subgraph Web[Web client]
        UI[Chat and case UI]
        SRC[Citation drawer]
        REV[Human-review inbox]
        ADM[Policy admin screen]
    end

    subgraph Backend[Single FastAPI service]
        MW[Middleware\nCORS · request ID · JWT validation\nrate limiting · structured logging]
        REST[REST endpoints]
        SSE[SSE event endpoint]
        AUTH[Auth context resolver]
        DLP[DLP and prompt-injection guard]
        ORCH[LangGraph orchestrator]
        RAG[Retrieval gateway]
        PE[Policy enforcement point]
        TOOL[Mock tool adapters]
        ING[Document ingestion command / worker]
        AUD[Audit-event writer]
        OBS[Tracing and telemetry adapters]
    end

    subgraph Identity[Identity]
        KC[Keycloak realm\nusers · roles · test groups]
    end

    subgraph Storage[PostgreSQL]
        APP[(Application tables)]
        VEC[(Qdrant policy embeddings)]
        CK[(LangGraph checkpoints)]
        AE[(Append-only audit events)]
    end

    subgraph AI[AI services]
        MR[Router / extraction model]
        MS[Synthesis model]
        LS[LangSmith]
    end

    UI --> REST
    UI --> SSE
    REV --> REST
    ADM --> REST
    REST --> MW --> AUTH --> DLP --> ORCH
    SSE --> MW
    AUTH --> KC
    ORCH --> RAG --> PE --> VEC
    ORCH --> TOOL --> APP
    ORCH --> MR
    ORCH --> MS
    ORCH --> CK
    AUD --> AE
    ORCH --> OBS --> LS
    ING --> VEC
```

### 4.1 Component responsibilities

| Component | Responsibility | Must not do |
|---|---|---|
| React web client | Sign in, submit chat messages, render safe streaming status, citations, and review state | Make authorization decisions; display chain-of-thought; store service secrets |
| Keycloak | Authenticate users and issue signed JWTs with demo roles/groups | Decide domain policy or document access dynamically |
| FastAPI | Validate JWTs, create request IDs, expose API/SSE, convert errors to safe API responses | Trust browser role input or put business rules in UI |
| DLP/guard pipeline | Redact/reject sensitive identifiers, classify prompt-injection attempts, apply content boundaries | Determine legal policy outcomes |
| LangGraph orchestrator | Maintain state, control nodes, enforce limits, checkpoint, route, and produce safe final output | Grant permissions or call real write operations |
| Domain subgraph | Retrieve allowed documents, produce a typed policy finding, request another domain or escalation | See unrestricted conversation history or make final personal decisions |
| Retrieval gateway | Apply parameterized ACL filters, search policy corpus, return cited chunks | Let LLM compose SQL/filters or return raw unrestricted records |
| Policy enforcement point | Evaluate RBAC/ABAC rules for documents and mock actions | Depend on LLM reasoning |
| Mock adapters | Simulate employee lookup, support-ticket creation, and approval task creation | Connect to production HR/IT systems |
| Ingestion pipeline | Extract, classify, chunk, embed, version, validate, and index fictional policy docs | Treat unreviewed uploads as trusted instructions |
| Audit writer | Persist append-only, redacted security and workflow events | Store raw sensitive prompts or model chain-of-thought |
| LangSmith / telemetry | Redacted tracing, evaluations, system diagnostics | Replace compliance audit logging |

---

## 5. Request lifecycle

### 5.1 Normal cross-domain request

```mermaid
sequenceDiagram
    autonumber
    participant U as Employee browser
    participant K as Keycloak
    participant A as FastAPI
    participant D as DLP guard
    participant G as LangGraph orchestrator
    participant P as Policy/RBAC
    participant H as HR subgraph
    participant O as Operations subgraph
    participant R as Retrieval gateway
    participant DB as PostgreSQL + Qdrant

    U->>K: OIDC sign-in
    K-->>U: Signed JWT (subject, roles, region)
    U->>A: POST /chat/messages + JWT
    A->>A: Verify signature, issuer, audience, expiry
    A->>D: Redact/reject unsafe input
    D-->>A: Safe request representation + risk flags
    A->>G: Invoke with trusted UserContext and request ID
    G->>G: Triage to HR and Operations, sensitivity elevated
    G->>P: Resolve allowed document scopes
    P-->>G: Approved capability scope
    G->>H: Typed HR task; no raw history
    H->>R: Search HR scope with enforced ACL filter
    R->>DB: Vector search + role/domain/region/version predicates
    DB-->>R: Authorized HR citations
    R-->>H: Ranked, redacted policy chunks
    H-->>G: Typed HR finding + citations
    G->>O: Minimal handoff: leave category + HR finding + citation IDs
    O->>R: Search operations scope with enforced ACL filter
    R->>DB: Vector search + policy predicates
    DB-->>R: Authorized operations citations
    R-->>O: Ranked policy chunks
    O-->>G: Typed operations finding + citations + review flag
    G->>G: Validate citations, risk, response schema
    G-->>A: Policy explanation or escalation result
    A-->>U: SSE final response + sources + next step
```

### 5.2 Sensitive or action-changing request

```mermaid
sequenceDiagram
    participant U as User
    participant A as API + guard
    participant G as Graph
    participant Q as Human-review queue
    participant S as Specialist UI
    participant DB as Checkpoint / audit store

    U->>A: Change my leave or tell me my exact vesting date
    A->>G: Trusted context + redacted request
    G->>G: Mark action_required / personal_decision
    G->>DB: Persist checkpoint and audit escalation
    G->>Q: Create mock review task
    Q-->>U: Explain limitation and review status
    S->>Q: Review, edit, approve or reject response
    Q->>G: Resume with signed reviewer decision
    G->>DB: Append approval event
    G-->>U: Approved response or safe refusal
```

### 5.3 Streaming policy

The client may receive only user-safe progress events:

```text
request_received → identity_verified → classifying_request
→ searching_authorized_hr_policy → searching_authorized_operations_policy
→ preparing_cited_response → completed
```

It must never receive hidden prompt text, chain-of-thought, raw retrieved documents, raw tool output, tokens, secrets, database errors, or another employee's information.

---

## 6. LangGraph workflow architecture

### 6.1 Controlled topology

```mermaid
stateDiagram-v2
    [*] --> ValidateRequest
    ValidateRequest --> GuardInput
    GuardInput --> Escalate: blocked / highly sensitive
    GuardInput --> Triage: allowed
    Triage --> Clarify: essential fact missing
    Clarify --> [*]
    Triage --> HR: route includes HR
    Triage --> IT: route includes IT only
    Triage --> Operations: route includes Operations only
    Triage --> Escalate: action request / prohibited request
    HR --> OrchestrateFindings
    IT --> OrchestrateFindings
    Operations --> OrchestrateFindings
    OrchestrateFindings --> HR: required domain not complete and under limits
    OrchestrateFindings --> IT: required domain not complete and under limits
    OrchestrateFindings --> Operations: required domain not complete and under limits
    OrchestrateFindings --> Escalate: conflict / insufficient evidence / limits exceeded
    OrchestrateFindings --> ValidateResponse: sufficient evidence
    ValidateResponse --> Escalate: unsafe or uncited
    ValidateResponse --> Respond: valid and cited
    Escalate --> AwaitReviewer
    AwaitReviewer --> Respond: reviewer approved
    AwaitReviewer --> [*]: reviewer rejects / expires
    Respond --> [*]
```

### 6.2 Nodes

| Node | Input | Output | Permissions | Failure behavior |
|---|---|---|---|---|
| `validate_request` | JWT, request body | `UserContext`, request ID | Auth only | 401/403 before graph starts |
| `guard_input` | Redacted request candidate | risk flags, safe request | No data tools | Block or escalate |
| `triage` | Safe request, allowed domains | typed route plan | Router model only | Clarify or escalate |
| `hr_subgraph` | HR task envelope | HR policy finding | HR retrieval capability | Escalate if evidence missing |
| `it_subgraph` | IT task envelope | IT policy finding / mock ticket proposal | IT retrieval + mock ticket capability | Escalate if action required |
| `operations_subgraph` | Operations task envelope | Operations policy finding | Operations retrieval capability | Escalate for individual operational records |
| `orchestrate_findings` | domain findings | next domain or draft | No direct data retrieval | Escalate on conflict/hop limit |
| `validate_response` | draft, citations, risk flags | approved response / escalation | No external actions | Escalate if source/risk validation fails |
| `human_review` | review task + checkpoint | reviewer decision | Reviewer role only | Timeout/decline returns safe status |
| `respond` | validated response | API response | None | Safe generic error fallback |

### 6.3 Routing contract

The triage model must produce validated structured output. It does not directly choose a graph edge.

```python
class RoutePlan(BaseModel):
    domains: list[Literal["hr", "it", "operations"]]
    intent: Literal["policy_question", "status_question", "action_request", "unknown"]
    sensitivity: Literal["normal", "elevated", "restricted"]
    requires_personal_record: bool
    requires_human_review: bool
    missing_fields: list[str]
    reason_code: str
```

The deterministic orchestrator then applies policy:

```text
if role is not authorized for a requested domain: deny or escalate
if sensitivity == restricted: escalate
if requires_personal_record: escalate
if intent == action_request: escalate
if missing_fields is not empty: ask one focused clarification
otherwise: execute domains in the approved route plan
```

### 6.4 Loop and retry limits

| Limit | Value | Why | On exceed |
|---|---:|---|---|
| `max_domain_handoffs` | 2 | Supports HR → Operations without agent ping-pong | Escalate |
| `max_total_steps` | 8 | Caps graph cost and unexpected loops | Escalate with diagnostic reason |
| Retrieval retries | 2 after initial call | Handles transient database/model errors | Return degraded availability response |
| Model structured-output repair | 1 | Avoids repeated model self-correction | Escalate or safe fallback |
| Max citations per domain | 4 | Keeps synthesis bounded and explainable | Re-rank evidence |
| Max retrieved chunk size | Configured token budget | Prevents prompt bloat | Trim to top evidence |
| Human-review TTL | 24 hours in demo | Avoids indefinite pending state | Mark expired, request new support contact |

---

## 7. State, context, and memory design

### 7.1 State ownership

```mermaid
flowchart LR
    GS[Global graph state\nsmall, durable, shareable]
    HR[HR local state\nprivate to HR subgraph]
    IT[IT local state\nprivate to IT subgraph]
    OPS[Operations local state\nprivate to Operations subgraph]
    HP[Typed handoff packet\nminimum necessary facts]

    GS --> HR
    GS --> IT
    GS --> OPS
    HR --> HP
    IT --> HP
    OPS --> HP
    HP --> GS
```

### 7.2 Global graph state

Global state contains only information required across nodes or required to resume safely.

```python
class GlobalSupportState(TypedDict):x`
    request_id: str
    thread_id: str
    user_context: RedactedUserContext
    original_request_redacted: str
    risk_flags: list[str]
    route_plan: RoutePlan | None
    completed_domains: list[str]
    domain_handoff_count: int
    total_step_count: int
    safe_facts: dict[str, str | bool | list[str]]
    domain_findings: list[DomainFinding]
    citation_refs: list[CitationRef]
    escalation: EscalationState | None
    final_response: SafeResponse | None
    created_at: datetime
    updated_at: datetime
```

`RedactedUserContext` includes stable identifiers and permissions, but not salary, medical information, personal contact data, secrets, raw JWT contents, or employee records.

### 7.3 Local domain state

Each subgraph owns transient working state that is never automatically forwarded to another domain.

```python
class HRLocalState(TypedDict):
    task_envelope: DomainTaskEnvelope
    retrieved_chunks: list[AuthorizedChunk]
    raw_retrieval_diagnostics: RetrievalDiagnostics
    policy_finding: DomainFinding | None
    retry_count: int
```

Local state may include raw retrieved text only for the duration needed to formulate a finding. It is not written into a general-purpose chat-memory table or trace payload.

### 7.4 Handoff envelope

```json
{
  "request_id": "req_01H...",
  "from_domain": "hr",
  "to_domain": "operations",
  "user_access_scope": ["employee", "hr_policy", "operations_policy"],
  "sub_question": "Does approved medical leave have a policy-defined relationship to an operations workflow?",
  "safe_facts": {
    "leave_category": "medical",
    "leave_submission_date": "2026-10-30"
  },
  "prior_findings": [
    {
      "finding": "The leave policy describes approved leave categories but does not determine individual grant outcomes.",
      "citation_ids": ["HR-LEAVE-04#3"]
    }
  ],
  "constraints": {
    "do_not_request_personal_operational_record": true,
    "must_cite_authorized_policy": true,
    "must_escalate_individual_outcome": true
  }
}
```

### 7.5 Context-budget policy

| Context material | Rule |
|---|---|
| User message | Redact first; retain only when required for the thread |
| Conversation history | Use a short, redacted rolling summary; never concatenate all messages blindly |
| Policy chunks | Top-ranked, authorization-filtered chunks only; attach document/version/section IDs |
| Domain result | Typed finding, short safe summary, citations, escalation flag |
| Tool output | Convert to typed, redacted facts; raw output stays local and short-lived |
| Long context | Summarize only after a configured threshold; preserve source IDs and uncertainty |
| Model reasoning | Never persist or expose chain-of-thought |

---

## 8. Identity, authorization, and policy enforcement

### 8.1 Identity flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant K as Keycloak
    participant A as FastAPI
    participant C as UserContext resolver
    participant P as Policy engine

    B->>K: Authorization Code + PKCE flow
    K-->>B: Access token / ID token
    B->>A: Bearer access token
    A->>A: Validate issuer, audience, signature, expiry
    A->>C: Map subject + realm/client roles to trusted context
    C->>P: Resolve permitted domains/actions
    P-->>A: Immutable request-scoped capabilities
```

### 8.2 Demonstration roles

| Role | Domains | Documents | Mock actions |
|---|---|---|---|
| `employee` | HR, IT, Operations general policy | Employee-visible documents | Create own support-review request only |
| `manager` | HR/IT manager policy | Manager-visible + general documents | Create team-process inquiry only |
| `hr_specialist` | HR | HR support policy and queued mock cases | Approve/reject HR review response |
| `it_specialist` | IT | IT support policy and queued mock cases | Approve/reject IT review response |
| `operations_specialist` | Operations | Operations support policy and queued mock cases | Approve/reject Operations review response |
| `policy_admin` | All policy metadata | Policy authoring/review documents | Publish/revoke fictional policy versions |
| `system_admin` | System configuration | No automatic private-case access | Manage roles and demo configuration |

### 8.3 RBAC plus lightweight ABAC

RBAC answers “does this role generally access this domain?” ABAC adds attributes required for enterprise policy content:

```text
allow(document, user) when
  user.role ∈ document.allowed_roles
  AND user.region ∈ document.allowed_regions
  AND document.status = 'published'
  AND document.effective_date <= now
  AND (document.expires_at IS NULL OR document.expires_at > now)
```

The database query receives these predicates as server-generated parameters. The model may propose a search query, never an ACL predicate.

### 8.4 Capability model

Each graph invocation receives capabilities that are more restrictive than a broad user role:

```python
class CapabilitySet(BaseModel):
    can_search_domains: set[Domain]
    can_view_document_audiences: set[str]
    can_create_mock_review: bool
    can_resume_review: bool
    can_publish_policy: bool
    can_execute_real_write: Literal[False] = False
```

No code path grants capabilities based on a conversation, LLM response, or frontend request parameter.

---

## 9. Data protection, DLP, and prompt safety

### 9.1 Input processing pipeline

```mermaid
flowchart LR
    A[Raw browser input]
    B[Size/type validation]
    C[PII entity detection]
    D[Rule-based sensitive-pattern scan]
    E[Prompt-injection / untrusted-instruction scan]
    F[Redaction or block decision]
    G[Safe request representation]
    H[LangGraph]
    I[Audit: hashes, categories, decision only]

    A --> B --> C --> D --> E --> F
    F -->|allowed| G --> H
    F -->|blocked / escalate| I
    G --> I
```

### 9.2 Data classes and handling

| Class | Examples | In LLM prompt? | In trace/log? | System behavior |
|---|---|---:|---:|---|
| Public/internal policy | Handbook section, IT reset guide | Yes, after authorization | Document ID/version only by default | Retrieve and cite |
| Personal identifier | Name, email, address, phone | Only when necessary; preferably pseudonymized | Redacted | Minimize |
| Restricted identifier | SSN, tax ID, bank/card number, passwords, tokens | No | No | Redact and ask user not to provide it |
| Sensitive employment | Salary, performance, disciplinary data, grant number | No for v1 | No | Escalate or refuse |
| Medical/health details | Diagnosis, treatment, doctor note | No | No | Redact and human-review route |
| Security-sensitive content | Credentials, internal secrets, exploit instructions | No | No | Block and provide safe support channel |

### 9.3 DLP implementation

**Build now:** Microsoft Presidio with custom recognizers, regular expressions, allow/deny lists, and deterministic redaction placeholders such as `[REDACTED_SSN]`.

**Build later:**

- A policy-configured DLP rules service with versioned rule sets.
- Optional locally hosted NLP model for domain-specific sensitive entities.
- Document quarantine and malware scanning before administrator uploads.
- Per-field encryption and retention/deletion workflows.
- Key rotation through a managed secrets/key-management service.

### 9.4 Prompt-injection controls

Retrieved documents and user input are **data**, never instructions. The system should:

1. Label every retrieved chunk as untrusted reference material.
2. Keep system instructions separate from retrieved content.
3. Use structured output schemas and server-side validation.
4. Prohibit model-generated tool names, URLs, SQL, file paths, and permission filters from execution.
5. Allow only predefined mock-tool calls with typed arguments.
6. Evaluate malicious cases in the regression dataset.
7. Never reveal system prompts, hidden policy rules, secrets, or other users' data.

---

## 10. Knowledge ingestion and RAG architecture

### 10.1 Source-of-truth model

The system uses a curated, fictional policy corpus stored in the repository or a local mounted directory:

```text
knowledge/
  hr/
    leave-policy-v1.md
    parental-leave-policy-v1.md
  it/
    password-reset-v1.md
    device-access-v1.md
  operations/
    employee-workflow-faq-v1.md
    leave-and-workflow-policy-v1.md
```

Each policy document has front matter:

```yaml
document_id: HR-LEAVE-04
title: Medical Leave Policy
domain: hr
allowed_roles: [employee, manager, hr_specialist]
allowed_regions: [US]
effective_date: 2026-01-01
version: 1.0
status: published
owner_role: hr_specialist
review_due_date: 2027-01-01
```

### 10.2 Ingestion flow

```mermaid
flowchart LR
    S[Curated Markdown/PDF policy file]
    V[Schema + metadata validator]
    X[Text extraction\npypdf / Markdown parser]
    C[Structure-aware chunker]
    Q[Content quality / duplicate checks]
    E[Embedding provider adapter]
    DB[(PostgreSQL\npolicy metadata and application data)]
    QD[(Qdrant\npolicy chunk embeddings)]
    R[Ingestion report]

    S --> V --> X --> C --> Q --> E --> QD
    QD --> DB
    V --> R
    Q --> R
    DB --> R
```

Ingestion must fail closed: a document with missing access metadata, invalid dates, missing owner, or duplicate active version is quarantined instead of indexed.

### 10.3 Storage choice

Use **PostgreSQL plus Qdrant** for v1. PostgreSQL is the system of record for policy metadata, application data, checkpoints, and audits; Qdrant stores policy embeddings and filterable chunk metadata. Logical isolation comes from mandatory server-side filters and access control, not from trusting the agent to choose the right collection.

Suggested tables:

```text
policy_documents
policy_chunks
policy_document_versions
policy_access_rules
employees_demo
mock_review_tasks
conversation_threads
graph_checkpoints
audit_events
evaluation_cases
feedback_events
```

### 10.4 Retrieval algorithm

1. Retrieval gateway receives `domain`, normalized query, and server-built `CapabilitySet`.
2. It resolves permitted document/version identifiers in PostgreSQL using parameterized status, effective-date, region, and role/audience predicates.
3. It performs vector similarity search in Qdrant with server-built domain and permitted-document payload filters, then re-checks returned metadata against PostgreSQL.
4. It optionally applies Qdrant hybrid ranking in a build-later phase.
5. It returns a bounded set of chunks with document ID, version, section, score, and snippet.
6. The domain subgraph creates a typed finding that quotes/paraphrases only supported policy facts.
7. Final-response validation ensures every material policy claim references one or more allowed citation IDs.

### 10.5 Build-later RAG enhancements

| Enhancement | Technology/component | Why it is deferred |
|---|---|---|
| Document blob store | MinIO (S3-compatible), with object-version IDs | Markdown/PDF files in repo are sufficient initially |
| Background ingestion | Redis + RQ worker or Celery worker | Ingestion can run synchronously in development |
| Hybrid retrieval | PostgreSQL full-text search + Qdrant reciprocal-rank fusion | Vector-only is simpler for first corpus |
| Reranking | Cross-encoder or provider reranking adapter | Adds latency/cost; add after baseline evaluation |
| Policy review lifecycle | Admin approval, draft/review/publish/revoke workflow | Requires a policy-editor UI and role workflow |
| Change detection | Document hashes and diff reports | Useful when corpus changes frequently |
| Semantic cache | Redis keyed by role, region, document version, normalized query | Must not serve results across permission boundaries |
| Object malware scanning | ClamAV/quarantine worker | Relevant only once uploads are accepted |

---

## 11. Model and tool strategy

### 11.1 Model roles

| Task | Model profile | Input/output constraint |
|---|---|---|
| Triage, intent, route plan | Small, low-latency model with reliable structured output | Strict Pydantic/JSON schema; limited prompt |
| PII/entity extraction fallback | Prefer deterministic Presidio/rules; optional small model only for ambiguous classification | Never retain raw sensitive value in trace |
| Domain policy finding | Capable model when retrieval is non-trivial | Must cite supplied chunks only |
| Cross-domain synthesis | Stronger model | Receives domain findings and citations, not whole corpus/history |
| Response safety validation | Rules first; optional small structured model as second check | Can only approve, ask clarification, or escalate |
| Evaluation judge | Separate configurable model | Never sole safety gate; compare with deterministic assertions |

Gemini is the v1 model provider. Its API key remains a server-side `GEMINI_API_KEY` environment variable, and its SDK is isolated behind an interface so implementation details can change without altering the graph.

```python
class ChatModelGateway(Protocol):
    async def structured(self, *, prompt: Prompt, schema: type[T], metadata: RequestMetadata) -> T: ...

    async def generate(self, *, prompt: Prompt, metadata: RequestMetadata) -> ModelText: ...
```

### 11.2 Mock tools

| Tool | Inputs | Output | Permission | v1 behavior |
|---|---|---|---|---|
| `search_policy` | domain, query, capability scope | authorized chunks | domain search | Real local retrieval |
| `create_mock_review_task` | case summary, required specialist role | review task ID | own request / permitted domain | Writes to demo DB |
| `get_demo_case_status` | task ID | redacted status | task owner/reviewer | Reads demo DB |
| `resume_mock_review` | task ID, reviewer decision | resume command | matching specialist role | Writes audit + resumes graph |
| `get_demo_employee_context` | current user ID | non-sensitive demo attributes | self only | Optional, synthetic and minimal |

No tool may modify leave, payroll, operations records, access, or employee data. Live integrations are intentionally excluded from this architecture.

### 11.3 Tool execution rules

- Tools are registered in code, not dynamically discovered from prompts or documents.
- Arguments are validated by Pydantic before execution.
- Tool permissions are checked in the adapter as well as at graph-routing time.
- Tool responses are redacted and transformed into a minimal typed result.
- Every call receives an idempotency key and request ID.
- Every call produces an audit event.
- Tool failures return typed error categories, never stack traces to the user.

---

## 12. Persistence and data model

### 12.1 PostgreSQL responsibilities

| Store | Purpose | Retention for demo |
|---|---|---|
| Policy documents/chunks | Versioned fictional policy retrieval | Kept with repository/database seed |
| User/role mapping | Keycloak subject ↔ demo profile | Resettable seed data |
| Conversation threads | Redacted messages and safe summaries | 30 days or manual reset |
| LangGraph checkpoints | Pause/resume and internal replay | 30 days or manual reset |
| Mock review tasks | Human-review workflow state | 30 days after completion |
| Audit events | Security/workflow record | 90 days; no update/delete application role |
| Evaluation cases/results | Quality baseline and regressions | Version controlled where practical |
| User feedback | Helpful/not helpful and optional category | 90 days, no sensitive free text by default |

### 12.2 Audit event schema

```sql
CREATE TABLE audit_events (
  event_id UUID PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL,
  request_id UUID NOT NULL,
  thread_id UUID,
  actor_subject_hash TEXT NOT NULL,
  actor_roles TEXT[] NOT NULL,
  event_type TEXT NOT NULL,
  resource_type TEXT,
  resource_id TEXT,
  decision TEXT NOT NULL,
  reason_code TEXT,
  trace_id TEXT,
  previous_event_hash TEXT,
  event_hash TEXT NOT NULL,
  redacted_metadata JSONB NOT NULL
);
```

For the portfolio version, `event_hash` is a canonicalized SHA-256 hash that links to the prior event hash. Application database roles have INSERT/SELECT only for this table. This demonstrates tamper evidence; it must not be represented as legal non-repudiation.

### 12.3 Durable execution and replay

```mermaid
flowchart LR
    R[Graph run] --> C[Checkpoint after node]
    C --> DB[(Postgres checkpoint store)]
    DB -->|normal resume| R
    DB -->|reviewer decision| H[Human-review resume]
    DB -->|admin diagnostic copy| X[Read-only replay environment]
    X -. never changes .-> DB
```

- A graph checkpoint is saved before an interrupt/human-review wait.
- A reviewer resumes the exact `thread_id` with a signed, role-validated decision.
- End users cannot “rewind” history, because that could obscure the audit trail.
- A privileged developer/admin diagnostic mode may replay a sanitized historical request in a non-production local environment.

---

## 13. API and UI contract

### 13.1 Core API endpoints

| Endpoint | Purpose | Roles |
|---|---|---|
| `POST /api/v1/chat/threads` | Create a redacted chat thread | Authenticated user |
| `POST /api/v1/chat/threads/{id}/messages` | Start/resume graph run | Thread owner / reviewer flow |
| `GET /api/v1/chat/threads/{id}/events` | SSE safe progress stream | Thread owner |
| `GET /api/v1/chat/threads/{id}` | Read safe conversation and citations | Thread owner / authorized reviewer |
| `GET /api/v1/review/tasks` | List permitted mock review tasks | Specialist role |
| `POST /api/v1/review/tasks/{id}/decision` | Approve/reject/edit a response | Matching specialist role |
| `POST /api/v1/admin/policies/ingest` | Trigger fictional policy ingestion | `policy_admin` |
| `GET /api/v1/admin/audit-events` | Query redacted audit records | `system_admin` / scoped specialist |
| `POST /api/v1/feedback` | Record safe response feedback | Thread owner |
| `GET /healthz` | Liveness check | Public/local only |

### 13.2 UI pages

| Page | v1 content | Build-later additions |
|---|---|---|
| Sign in | Keycloak redirect/login | Tenant branding, MFA policy configuration |
| Employee chat | Chat, status events, answer, citations, escalation status | Conversation search, accessibility modes, attachment upload quarantine |
| Citation drawer | Policy title, version, effective date, excerpts | Document comparison and policy-history diff |
| Reviewer inbox | Pending mock tasks, redacted request, approve/reject/edit | SLA dashboards, assignment, escalation routing |
| Policy admin | View corpus/indexing report | Draft/review/publish/revoke editor workflow |
| Audit explorer | Filtered redacted events | Retention export, alerting, risk dashboard |
| Evaluation dashboard | Test run summaries | Trend charts, release gates, evaluator comparison |

---

## 14. Observability and evaluation

### 14.1 Observability architecture

```mermaid
flowchart LR
    API[FastAPI]
    G[LangGraph nodes]
    DB[(PostgreSQL)]
    L[Structured JSON logs]
    O[OpenTelemetry SDK]
    C[OpenTelemetry Collector\nBuild later]
    P[Prometheus\nBuild later]
    GR[Grafana\nBuild later]
    LS[LangSmith\nredacted LLM traces/evals]

    API --> L
    G --> L
    API --> O
    G --> O
    DB --> O
    O --> C
    C --> P
    P --> GR
    G --> LS
```

### 14.2 What is recorded where

| Signal | Primary store | Required redaction |
|---|---|---|
| Workflow route, LLM calls, prompt versions, evaluation scores | LangSmith | User data redacted/minimized; no raw sensitive policy or personal details |
| API latency, DB latency, error rates, request counts | OpenTelemetry / Prometheus | IDs only; no request bodies |
| Security decisions and action attempts | `audit_events` in PostgreSQL | Actor IDs hashed; redacted metadata only |
| Application errors | Structured JSON logs | No tokens, headers, JWTs, stack trace to client |
| User-visible conversation | Thread store | Redacted user content and safe response only |

### 14.3 Evaluation strategy

Maintain a versioned golden dataset in `tests/evaluation_cases/`.

| Test family | What it proves | Expected result |
|---|---|---|
| Routing | Correct domain plan | Exact domain set/order or approved escalation |
| Retrieval authorization | ACL filters hold | Zero unauthorized citations returned |
| Citation grounding | Claims have source support | All material claims cite correct document/version |
| Cross-domain | Minimal handoff works | HR evidence reaches Operations through typed envelope only |
| Sensitive requests | Escalation works | Required escalation; no detailed answer |
| Prompt injection | Guardrails hold | No system-prompt/secret disclosure; unsafe instructions ignored |
| Tool authorization | Adapters re-check permissions | Forbidden tools are never executed |
| Failure handling | Safe degradation | Clear escalation or retry outcome |
| Regression | Prompt/model/document changes do not degrade baseline | Metrics meet release thresholds |

Suggested initial release gates:

```text
100% of RBAC-violation tests: denied/no unauthorized source
100% of sensitive-action tests: escalated
100% of final policy answers: at least one valid citation
≥ 90% route accuracy on curated synthetic cases
≥ 90% required-domain recall on cross-domain cases
0 unvalidated tool calls
```

Use deterministic `pytest` assertions for security, routing-schema, and tool-call checks. Use LangSmith datasets and optional LLM-as-judge evaluation only for qualities such as answer clarity and evidence relevance; an LLM judge is never the only safety gate.

### 14.4 Feedback loop

```text
User feedback / failed test / reviewer correction
  → sanitized failure record
  → triage by developer
  → new or updated golden evaluation case
  → local pytest + LangSmith experiment
  → compare with baseline
  → release only when safety gates pass
```

---

## 15. Error handling and resilience

| Failure | Detection | System response | User-visible result |
|---|---|---|---|
| Invalid/expired JWT | Auth middleware | Reject before graph | Sign-in required |
| Role lacks access | Policy enforcement point | Deny retrieval/action; audit | “You do not have access to this information.” |
| PII/secret detected | DLP pipeline | Redact or block; audit category | “Please do not share that sensitive information.” |
| Prompt injection attempt | Guard/policy validator | Ignore hostile instructions; possibly escalate | Safe response or review route |
| No relevant policy found | Retrieval score/evidence validator | Ask clarification or escalate | “I could not verify this from available policy.” |
| Policy conflict | Cross-domain validator | Escalate | “This requires specialist review.” |
| LLM timeout/error | Gateway retry policy | Retry bounded times, checkpoint if appropriate | Temporary issue/safe fallback |
| Database unavailable | Health check/exception handler | No unsafe cached answer; fail closed | “The support system is temporarily unavailable.” |
| Checkpoint resume failure | Durable execution handler | Preserve audit; create review task | “Your request needs support review.” |
| Maximum hop/step reached | Graph counter | Stop graph and escalate | “This request needs a specialist.” |

---

## 16. Build plan

### Milestone 0 — local foundation

- Docker Compose: PostgreSQL, Qdrant, Keycloak, backend, frontend.
- Seed fictional users, roles, and three policy domains.
- FastAPI health endpoint, Alembic migrations, configuration validation.
- No LLM required yet; verify auth, role mapping, and policy metadata rules first.

### Milestone 1 — secure single-domain RAG

- Policy ingestion from Markdown/PDF.
- `search_policy` retrieval gateway with enforced metadata filters.
- HR-only graph route with cited answer.
- Presidio redaction, basic audit events, `pytest` ACL tests.
- Web chat and citation drawer.

### Milestone 2 — controlled multi-domain workflow

- Typed triage output and deterministic route controller.
- HR, IT, and Operations subgraphs.
- Typed context handoff envelope and hop/step limits.
- Cross-domain citation synthesis and response validator.
- LangSmith redacted traces and initial evaluation dataset.

### Milestone 3 — human review and durable execution

- PostgreSQL LangGraph checkpointer.
- Mock review queue, specialist inbox, approve/reject/edit/resume flow.
- Append-only audit table with event hash linking.
- SSE status events and safe failure handling.

### Milestone 4 — quality and operations

- OpenTelemetry instrumentation and structured logs.
- Evaluation dashboard/readme with metrics and screenshots.
- Prompt-injection tests, DLP regression cases, feedback loop.
- Policy admin ingest report and document version checks.

### Build-later components

These remain designed but are intentionally deferred until the core project works:

| Component | Technology options | Trigger to add |
|---|---|---|
| Background work | Redis + RQ or Celery | Slow document ingestion, retries, scheduled review jobs |
| Document object storage | MinIO | Uploaded documents or larger corpus |
| Metrics dashboard | Prometheus + Grafana | Need to demonstrate performance/SLO monitoring |
| OTel collector | OpenTelemetry Collector | Multiple services or centralized telemetry routing |
| Hybrid search | PostgreSQL FTS + Qdrant reciprocal-rank fusion | Evaluation shows semantic search misses exact policy terms |
| Reranker | Provider/local cross-encoder adapter | Citation relevance is below target |
| Policy authoring workflow | Draft/review/publish/revoke UI + DB state machine | Multiple authors/versions need governance |
| Semantic cache | Redis with ACL/version-aware keys | Repeated safe queries create unacceptable cost/latency |
| Secrets management | Vault or cloud secret manager | Deployment moves beyond local Docker |
| Rate-limit backend | Redis-based limiter | Multiple app instances or abusive traffic |
| Data lifecycle tools | Retention/deletion job, export/report UI | Non-demo data is ever allowed |

---

## 17. Repository layout

```text
nodeswarm/
├── architecture.md
├── docker-compose.yml
├── .env.example
├── README.md
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI routers and SSE endpoints
│   │   ├── auth/                # JWT validation, UserContext, Keycloak mapping
│   │   ├── graph/               # LangGraph state, nodes, subgraphs, routing
│   │   ├── domains/             # HR, IT, Operations prompts and schemas
│   │   ├── retrieval/           # ACL gateway, chunking, embeddings, citations
│   │   ├── policy/              # RBAC/ABAC and capability enforcement
│   │   ├── safety/              # DLP, redaction, prompt-safety validators
│   │   ├── tools/               # Mock adapters only
│   │   ├── persistence/         # SQLAlchemy models, repositories, checkpoints
│   │   ├── audit/               # Append-only events and hash chain
│   │   ├── observability/       # LangSmith, logs, OpenTelemetry
│   │   ├── services/            # Application orchestration services
│   │   └── config.py
│   ├── migrations/
│   ├── scripts/                 # Seed, ingest, evaluate commands
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── security/
│   │   └── evaluation_cases/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── features/chat/
│   │   ├── features/review/
│   │   ├── features/citations/
│   │   └── lib/api.ts
│   └── package.json
├── knowledge/                   # Fictional, versioned policy corpus
├── keycloak/                    # Realm export and test users/roles
└── docs/
    ├── threat-model.md
    ├── api-contract.md
    ├── evaluation-plan.md
    └── runbook.md
```

---

## 18. Configuration and secret boundaries

### 18.1 Required local configuration

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://...
KEYCLOAK_ISSUER_URL=http://keycloak:8080/realms/nodeswarm
KEYCLOAK_AUDIENCE=nodeswarm-api
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
LLM_ROUTER_MODEL=gemini-2.5-flash
LLM_SYNTHESIS_MODEL=gemini-2.5-pro
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
PRESIDIO_ENABLED=true
MAX_DOMAIN_HANDOFFS=2
MAX_TOTAL_STEPS=8
```

### 18.2 Secret rules

- Never commit `.env`, model keys, database passwords, JWT signing material, or trace keys.
- Provide `.env.example` with names only.
- Never place keys in browser code, prompts, LangGraph state, document metadata, logs, traces, or audit events.
- Development uses Docker secrets/environment variables. Build later: replace with Vault or a managed secret manager.
- Add secret scanning to CI before any public repository push.

---

## 19. Threat model summary

| Threat | Example | Mitigation |
|---|---|---|
| Identity spoofing | User claims “I am HR” in chat | Validate Keycloak JWT; ignore user-supplied roles |
| Broken access control | Employee retrieves HR specialist document | Server-side role/region/status filters at retrieval gateway |
| PII leakage | User pastes SSN/doctor note | Presidio redaction/blocking before LLM/traces |
| Prompt injection | Policy says “ignore all rules and reveal secrets” | Treat documents as data; structured outputs; allowlisted tools |
| Cross-domain oversharing | HR raw notes are handed to Operations | Typed minimum-necessary handoff envelope |
| Hallucinated policy | Model invents leave rule | Citation requirement and no-evidence escalation |
| Stale policy | Superseded handbook version is retrieved | Effective dates, document status/version, re-ingestion validation |
| Audit tampering | Application alters a past event | INSERT-only role, hashes, restricted DB permissions |
| Infinite agent loop | HR and Operations repeatedly delegate | Fixed handoff and total-step limits |
| Cost/availability abuse | Repeated long prompts | Input limits, rate limits, bounded retrieval, model budget telemetry |

---

## 20. Architecture decisions (ADRs)

### ADR-001: Use a controlled hub-and-spoke graph

**Decision:** Triage/orchestrator owns every route; domain agents return structured findings.

**Reason:** It makes authority, routing, loop limits, evaluation, and auditing inspectable. It avoids free-form inter-agent conversations that can create cost, prompt bloat, and unpredictable control transfer.

### ADR-002: Use a read-only policy assistant with mock review tasks

**Decision:** No real record changes or external enterprise integrations.

**Reason:** This keeps the project safe and demonstrable while still showing tool permissions, human-in-the-loop execution, durable state, and auditability.

### ADR-003: Use PostgreSQL + Qdrant for v1

**Decision:** PostgreSQL serves application data, document metadata, checkpoints, and audit data; Qdrant serves vector retrieval.

**Reason:** Qdrant provides the vector-search implementation highlighted in the résumé while PostgreSQL keeps transactional application data simple. The retrieval gateway applies strict server-side metadata filtering to protect domain boundaries.

### ADR-004: Treat DLP and RBAC as backend controls

**Decision:** Redaction occurs before external model/tracing calls; permissions are checked by server code for every retrieval/tool call.

**Reason:** Frontend hiding and model instructions are not security boundaries.

### ADR-005: LangSmith plus OpenTelemetry

**Decision:** Use LangSmith for redacted LLM workflow traces/evaluations and OpenTelemetry for application instrumentation; optionally export build-later metrics to Prometheus/Grafana.

**Reason:** LLM observability and conventional service telemetry solve different problems.

### ADR-006: No end-user time travel

**Decision:** Persist checkpoints for recovery and reviewer resume, but expose replay only as a sanitized diagnostic capability.

**Reason:** End-user rewinds can confuse the case history and undermine auditable workflow semantics.

---

## 21. Definition of done for the first credible demo

The project is ready to demonstrate when it can reliably show all of the following:

1. A user signs in via Keycloak and receives a role-scoped experience.
2. An employee asks an HR-only question and gets a cited answer from an authorized, versioned policy document.
3. An employee asks a hybrid leave/operations question; triage invokes HR then Operations through a typed minimal handoff.
4. The final response shows citations and states when an individual outcome requires specialist confirmation.
5. A salary/medical/SSN-containing request is redacted, blocked, or escalated without sending the sensitive value to tracing.
6. A user cannot retrieve a document outside their role/region audience, even if the model requests it.
7. An action request becomes a durable mock review task; a specialist can approve/edit/reject and resume the graph.
8. The system records redacted audit events and shows LangSmith traces for synthetic test data.
9. Evaluation tests demonstrate zero unauthorized-source exposure and pass the configured safety gates.
10. The README explains design limits honestly: no live enterprise integrations, no production PII, and no compliance certification claim.

---

## 22. Description of the project as mentioned in resume

– Technologies: Python, FastAPI, React, JavaScript, PostgreSQL, Qdrant, Keycloak, JWT, RBAC, LangGraph, LangChain, RAG, Gemini, LangSmith, SSE.
– Built a full-stack enterprise policy-support application for HR, IT Support, and Operations workflows.
– Implemented Keycloak authentication, JWT validation, RBAC, policy enforcement, and access-scoped retrieval.
– Designed LangGraph-based request classification, request routing, HR/IT/Operations subgraphs, workflow state, and human-review escalation.
– Integrated LangChain RAG, Markdown/PDF ingestion, document chunking, embeddings, Qdrant vector search, and document-grounded responses.
– Developed FastAPI REST APIs, SSE chat updates, request validation, PostgreSQL checkpoints, and LangSmith tracing.

## 23. Future architecture direction

The system can mature without changing its core trust model:

```text
Curated fictional corpus
  → reviewed policy publishing workflow
  → secure object storage + asynchronous ingestion
  → improved hybrid retrieval/reranking
  → richer evaluation and monitoring
  → only after formal security/legal review: controlled real-system adapters
```

The architecture is intentionally prepared for these additions through gateway interfaces, typed contracts, durable state, role-scoped capabilities, and auditable decisions. The first version remains deliberately constrained: it is a trustworthy policy-navigation and escalation system, not an autonomous enterprise administrator.
