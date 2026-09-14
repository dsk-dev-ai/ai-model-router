"""ai-model-router: OpenAI-compatible LLM routing, fallback, and cost control."""

from ai_model_router.catalog import MODEL_CATALOG, Model, list_models
from ai_model_router.models import (
    ChatRequest,
    ChatResponse,
    RouteInfo,
    RouterSpec,
    Usage,
)

__version__ = "1.0.1"
__all__ = [
    "MODEL_CATALOG",
    "ChatRequest",
    "ChatResponse",
    "Model",
    "RouteInfo",
    "RouterSpec",
    "Usage",
    "__version__",
    "list_models",
]
