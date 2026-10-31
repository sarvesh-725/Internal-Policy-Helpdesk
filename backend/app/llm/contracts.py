from typing import Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequestMetadata(BaseModel):
    """Trace-safe request metadata; never include a JWT, user message, or retrieved content."""

    model_config = ConfigDict(frozen=True)

    request_id: UUID
    thread_id: UUID | None = None
    actor_subject_hash: str = Field(min_length=64, max_length=64)
    prompt_version: str = Field(min_length=1, max_length=80)


class Prompt(BaseModel):
    """A minimized model input constructed only from already-authorized, redacted data."""

    model_config = ConfigDict(frozen=True)

    system_instruction: str = Field(min_length=1, max_length=12_000)
    user_content: str = Field(min_length=1, max_length=24_000)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)


class ModelText(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    model: str


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class ChatModelGateway(Protocol):
    async def structured(
        self,
        *,
        prompt: Prompt,
        schema: type[StructuredModel],
        metadata: RequestMetadata,
    ) -> StructuredModel: ...

    async def generate(self, *, prompt: Prompt, metadata: RequestMetadata) -> ModelText: ...
