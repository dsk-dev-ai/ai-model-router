FROM python:3.12-slim

LABEL org.opencontainers.image.source=https://github.com/dsk-dev-ai/ai-model-router
LABEL org.opencontainers.image.description="OpenAI-compatible LLM gateway: routing, fallback, and cost tracking."
LABEL org.opencontainers.image.licenses=MIT

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . && \
    rm -rf /tmp/*

ENV PYTHONUNBUFFERED=1
ENV ROUTER_HOST=0.0.0.0
ENV ROUTER_PORT=8000

EXPOSE 8000

ENTRYPOINT ["python", "-m", "ai_model_router"]