from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas import HealthResponse, MetaResponse, ReadinessResponse
from app.services.health import DependencyUnavailableError, ReadinessService

router = APIRouter(tags=["system"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse()


@router.get("/readyz", response_model=ReadinessResponse)
def readyz() -> ReadinessResponse:
    try:
        ReadinessService().check()
    except DependencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Service is not ready.") from exc
    return ReadinessResponse()


@router.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    settings = get_settings()
    return MetaResponse(
        name=settings.app_name,
        environment=settings.app_env,
        api_version="v1",
        llm_provider=settings.llm_provider,
    )
