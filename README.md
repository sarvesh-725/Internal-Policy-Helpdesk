# Dynamic Enterprise Support Swarm

A portfolio-oriented, fictional enterprise policy-support application for HR, IT Support, and Operations workflows. It uses FastAPI, React with JavaScript, PostgreSQL, Qdrant, Keycloak, JWT/RBAC, LangGraph, Gemini, LangSmith, and SSE.

The application explains authorized policy content and creates mock review tasks. It does not make real HR, IT, payroll, access-control, legal, medical, or operational-record changes. Never use production employee data or credentials.

## Local configuration

Copy `.env.example` to `.env` and set `GEMINI_API_KEY` before running policy ingestion or retrieval. The key stays server-side and is never sent to the browser.

## Runtime services

Docker Compose defines PostgreSQL for transactional data and policy metadata, Qdrant for policy vectors, Keycloak for demo identity, FastAPI for the API, and React/JavaScript for the portal.

## Safety and model boundaries

Before a request can enter future graph or Gemini flows, the backend guard redacts identifiers, blocks secrets and restricted identifiers, and escalates sensitive employment, medical, and prompt-injection signals. Gemini prompt builders accept only the guard-approved request representation and authorized retrieval evidence; raw browser input, credentials, JWTs, and audit data are never prompt material.

See [architecture.md](architecture.md) for the system design and [phases.md](phases.md) for the delivery plan.

The core operational documents are the [threat model](docs/threat-model.md), [API contract](docs/api-contract.md), [local runbook](docs/runbook.md), [observability guide](docs/observability.md), and [data-handling guide](docs/data-handling.md). The [implementation map](docs/implementation-map.md) ties the architecture to code, and [quality status](docs/quality-status.md) records the deliberately deferred evaluation work.
