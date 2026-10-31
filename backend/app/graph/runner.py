from uuid import UUID

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from sqlalchemy import select

from app.graph.workflow import build_support_graph
from app.observability.setup import RedactedTelemetry
from app.persistence.database import SessionLocal
from app.persistence.models import ConversationMessage, ConversationThread, MockReviewTask
from app.schemas import SafeResponse


class SupportGraphRunner:
    """Durably executes or resumes one redacted graph thread using PostgreSQL checkpoints."""

    def run(self, initial_state: dict) -> dict:
        thread_id = str(initial_state["thread_id"])
        RedactedTelemetry().record_workflow_event(
            request_id=UUID(initial_state["request_id"]), event="workflow_started", status="processing", trace_id=initial_state.get("trace_id")
        )
        try:
            return self._invoke(input_value=initial_state, thread_id=thread_id)
        except Exception:
            self._persist_unavailable(thread_id=UUID(thread_id), request_id=UUID(initial_state["request_id"]))
            return {}

    def resume(self, *, thread_id: UUID, decision: dict) -> dict:
        try:
            return self._invoke(input_value=Command(resume=decision), thread_id=str(thread_id))
        except Exception:
            with SessionLocal() as session:
                request_id = session.scalar(select(MockReviewTask.request_id).where(MockReviewTask.thread_id == thread_id).order_by(MockReviewTask.created_at.desc()))
            if request_id is not None:
                self._persist_unavailable(thread_id=thread_id, request_id=request_id)
            return {}

    def _invoke(self, *, input_value, thread_id: str) -> dict:
        with PostgresSaver.from_conn_string(checkpoint_database_url()) as checkpointer:
            checkpointer.setup()
            graph = build_support_graph(checkpointer=checkpointer)
            result = graph.invoke(input_value, config={"configurable": {"thread_id": thread_id}})
        if result.get("__interrupt__"):
            self._set_thread_status(UUID(thread_id), "awaiting_review")
            RedactedTelemetry().record_workflow_event(
                request_id=UUID(result["request_id"]), event="workflow_paused", status="awaiting_review", trace_id=result.get("trace_id")
            )
            return result
        final_response = SafeResponse.model_validate(result.get("final_response"))
        self._persist_terminal_result(thread_id=UUID(thread_id), request_id=UUID(result["request_id"]), response=final_response)
        RedactedTelemetry().record_workflow_event(
            request_id=UUID(result["request_id"]), event="workflow_completed", status=final_response.status.value, trace_id=result.get("trace_id")
        )
        return result

    @staticmethod
    def _set_thread_status(thread_id: UUID, status: str) -> None:
        with SessionLocal() as session:
            thread = session.get(ConversationThread, thread_id)
            if thread is not None:
                thread.status = status
                session.commit()

    @staticmethod
    def _persist_terminal_result(*, thread_id: UUID, request_id: UUID, response: SafeResponse) -> None:
        with SessionLocal() as session:
            thread = session.get(ConversationThread, thread_id)
            if thread is None:
                return
            existing = session.scalar(
                select(ConversationMessage).where(
                    ConversationMessage.request_id == request_id,
                    ConversationMessage.actor_type == "assistant",
                )
            )
            if existing is None:
                session.add(
                    ConversationMessage(
                        thread_id=thread_id,
                        request_id=request_id,
                        actor_type="assistant",
                        content_redacted=response.message,
                        citation_metadata={"citations": [citation.model_dump(mode="json") for citation in response.citations]},
                    )
                )
            thread.status = response.status.value
            session.commit()

    @staticmethod
    def _persist_unavailable(*, thread_id: UUID, request_id: UUID) -> None:
        from app.graph.workflow import unavailable_response

        SupportGraphRunner._persist_terminal_result(thread_id=thread_id, request_id=request_id, response=unavailable_response("workflow_unavailable"))


def checkpoint_database_url() -> str:
    from app.config import get_settings

    url = get_settings().database_url
    return url.replace("postgresql+psycopg://", "postgresql://", 1)
