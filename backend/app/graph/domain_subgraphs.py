import asyncio

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from app.domains.contracts import DomainFinding, DomainTaskEnvelope
from app.domains.prompts import build_domain_finding_prompt
from app.config import get_settings
from app.llm.contracts import RequestMetadata
from app.llm.gemini_gateway import GeminiChatModelGateway
from app.policy.enforcement import PolicyEnforcementPoint
from app.retrieval.gateway import PolicyRetrievalGateway, RetrievalAccessDenied
from app.schemas import Domain


class DomainLocalState(TypedDict):
    """Private local state; raw retrieval chunks do not leave this graph."""

    task: dict
    finding: dict | None
    error_code: str | None


def build_domain_subgraph(domain: Domain):
    """A private, single-domain graph with no automatic access to sibling domain state."""

    def retrieve_and_find(state: DomainLocalState) -> dict:
        try:
            task = DomainTaskEnvelope.model_validate(state["task"])
        except Exception:
            return {"finding": None, "error_code": "invalid_domain_task"}
        if task.target_domain is not domain or task.handoff.to_domain is not domain:
            return {"finding": None, "error_code": "domain_task_scope_mismatch"}
        user = task.user_context.as_policy_user()
        capabilities = PolicyEnforcementPoint().capabilities_for(user)
        chunks = None
        for _ in range(1 + get_settings().retrieval_retry_attempts):
            try:
                from app.persistence.database import SessionLocal

                with SessionLocal() as session:
                    chunks = PolicyRetrievalGateway(session).search_policy(
                        domain=domain,
                        query=task.safe_subquestion,
                        user=user,
                        capabilities=capabilities,
                    )
                break
            except RetrievalAccessDenied:
                return {"finding": None, "error_code": "domain_retrieval_not_authorized"}
            except Exception:
                continue
        if chunks is None:
            return {"finding": None, "error_code": "domain_retrieval_unavailable"}
        if not chunks:
            return {"finding": None, "error_code": "insufficient_authorized_evidence"}
        prompt = build_domain_finding_prompt(
            task=task,
            authorized_chunks=chunks,
        )
        try:
            finding = asyncio.run(
                GeminiChatModelGateway().structured(
                    prompt=prompt,
                    schema=DomainFinding,
                    metadata=RequestMetadata.model_validate(
                        {
                            "request_id": task.request_id,
                            "thread_id": task.thread_id,
                            "actor_subject_hash": task.user_context.subject_hash,
                            "prompt_version": f"{domain.value}-finding-v1",
                        }
                    ),
                )
            )
        except Exception:
            return {"finding": None, "error_code": "domain_model_unavailable"}
        if finding.domain is not domain:
            return {"finding": None, "error_code": "domain_schema_mismatch"}
        supplied_citations = {citation_key(chunk.citation.model_dump(mode="json")) for chunk in chunks}
        if not all(citation_key(citation.model_dump(mode="json")) in supplied_citations for citation in finding.citations):
            return {"finding": None, "error_code": "unauthorized_model_citation"}
        return {"finding": finding.model_dump(mode="json"), "error_code": None}

    builder = StateGraph(DomainLocalState)
    builder.add_node("retrieve_and_find", retrieve_and_find)
    builder.add_edge(START, "retrieve_and_find")
    builder.add_edge("retrieve_and_find", END)
    return builder.compile()


def citation_key(citation: dict) -> tuple[str, str, str]:
    return (str(citation.get("document_id")), str(citation.get("version")), str(citation.get("section_id")))
