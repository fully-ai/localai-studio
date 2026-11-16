"""Pydantic request and response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ModelParameters(BaseModel):
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1, le=200)
    num_ctx: int = Field(default=4096, ge=256, le=131072)
    repeat_penalty: float = Field(default=1.1, ge=0.5, le=2.0)


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=120)
    system_prompt: str = Field(default="", max_length=8000)
    parameters: ModelParameters = Field(default_factory=ModelParameters)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    system_prompt: str | None = Field(default=None, max_length=8000)
    parameters: ModelParameters | None = None


class ChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    stream: bool = True


class SystemPromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=8000)


class PreferencesUpdate(BaseModel):
    default_model: str | None = Field(default=None, min_length=1, max_length=120)
    theme: str | None = Field(default=None, pattern="^(dark|light)$")
    stream_responses: bool | None = None
    default_parameters: ModelParameters | None = None


class ModelPullRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9._:/-]+$")


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
    ollama_url: str
    details: dict[str, Any] = Field(default_factory=dict)
