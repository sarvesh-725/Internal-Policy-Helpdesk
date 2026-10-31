import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import Settings, get_settings

_request_id: ContextVar[str | None] = ContextVar("nodeswarm_request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("nodeswarm_trace_id", default=None)


class JsonFormatter(logging.Formatter):
    """Application code supplies only safe request metadata; request bodies and tokens are never logged."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "logger": record.name, "message": record.getMessage()}
        for field in ("request_id", "trace_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, default=str)


def configure_observability(app, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("nodeswarm")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    provider = TracerProvider(resource=Resource.create({"service.name": "nodeswarm-api", "deployment.environment": settings.app_env}))
    if settings.otel_exporter_otlp_endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")


@contextmanager
def request_trace_context(request_id: str):
    """Bind correlation identifiers only; request content is never added to logs or spans."""
    tracer = trace.get_tracer("nodeswarm.request")
    request_token: Token = _request_id.set(request_id)
    with tracer.start_as_current_span("nodeswarm.request") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        trace_token: Token = _trace_id.set(trace_id)
        span.set_attribute("nodeswarm.request_id", request_id)
        try:
            yield
        finally:
            _trace_id.reset(trace_token)
            _request_id.reset(request_token)


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_request_id() -> str | None:
    return _request_id.get()


class RedactedTelemetry:
    """Records IDs and outcomes only; no prompt, retrieval, response, or personal content enters telemetry."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.tracer = trace.get_tracer("nodeswarm.workflow")

    def record_workflow_event(self, *, request_id: UUID, event: str, status: str, trace_id: str | None = None) -> None:
        with self.tracer.start_as_current_span("nodeswarm.workflow") as span:
            span.set_attribute("nodeswarm.request_id", str(request_id))
            span.set_attribute("nodeswarm.event", event)
            span.set_attribute("nodeswarm.status", status)
            if trace_id:
                span.set_attribute("nodeswarm.parent_trace_id", trace_id)
        if self.settings.langsmith_tracing and self.settings.langsmith_api_key:
            self._record_langsmith(request_id=request_id, event=event, status=status, trace_id=trace_id)

    def _record_langsmith(self, *, request_id: UUID, event: str, status: str, trace_id: str | None) -> None:
        try:
            from langsmith import Client
            Client(api_key=self.settings.langsmith_api_key).create_run(
                name="nodeswarm.redacted_workflow_event", run_type="chain",
                inputs={"request_id": str(request_id), "event": event, "trace_id": trace_id},
                outputs={"status": status}, project_name=self.settings.langsmith_project,
            )
        except Exception:
            logging.getLogger("nodeswarm").warning("redacted_trace_unavailable")
