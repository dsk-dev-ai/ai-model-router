"""OpenAI-compatible request/response schemas plus internal router metadata."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RouterSpec(BaseModel):
    """Per-request routing hints — every field is optional."""

    model_config = ConfigDict(extra="allow")

    policy: str = "priority"
    providers: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    max_cost_usd: float | None = None
    priority: list[str] = Field(default_factory=list)
    fallback: bool = True


class ChatRequest(BaseModel):
    """Minimal OpenAI chat-completion request; extra fields are preserved."""

    model_config = ConfigDict(extra="allow")

    model: str = "auto"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    router: RouterSpec = Field(default_factory=RouterSpec)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = "assistant"
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int = 0
    message: ChatMessage = Field(default_factory=ChatMessage)
    finish_reason: str | None = None


class RouteInfo(BaseModel):
    """Metadata about how the router selected a provider/model."""

    requested_model: str = "auto"
    chosen_model: str = ""
    provider: str = ""
    policy_used: str = ""
    attempts: int = 0
    fallback_used: bool = False
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0
    router_reason: str = ""


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=int)
    model: str = ""
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    route: RouteInfo = Field(default_factory=RouteInfo)


def new_response(model: str) -> ChatResponse:
    return ChatResponse(model=model, created=int(time.time()))
