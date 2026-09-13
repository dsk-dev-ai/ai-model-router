"""``ai-model-router`` CLI entrypoint — runs the FastAPI server."""

from __future__ import annotations

import uvicorn

from ai_model_router.config import Settings
from ai_model_router.server import create_app


def main() -> None:
    settings = Settings.from_env()
    app = create_app(settings=settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
