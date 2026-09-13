FROM python:3.12-slim

LABEL org.opencontainers.image.source=https://github.com/dsk-dev-ai/ai-model-router
LABEL org.opencontainers.image.description="OpenAI-compatible LLM gateway: routing, fallback, and cost tracking."
LABEL org.opencontainers.image.licenses=MIT

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . && \
    rm -rf /root/.cache && \
    useradd --create-home --shell /usr/sbin/nologin router

ENV PYTHONUNBUFFERED=1
ENV ROUTER_HOST=0.0.0.0
ENV ROUTER_PORT=8000

EXPOSE 8000

USER router

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" \
        || exit 1

ENTRYPOINT ["python", "-m", "ai_model_router", "serve"]