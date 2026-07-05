# ml service image — the only one carrying the scientific stack (doc 1 §4.0)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared/pyproject.toml shared/
COPY services/api/pyproject.toml services/api/
COPY services/worker/pyproject.toml services/worker/
COPY services/ml/pyproject.toml services/ml/
RUN uv sync --frozen --no-install-workspace --no-dev --package forecast-ml

COPY shared/ shared/
COPY services/ml/ services/ml/
RUN uv sync --frozen --no-dev --package forecast-ml

EXPOSE 8100
CMD ["uv", "run", "--no-sync", "uvicorn", "ml.app:app", "--host", "0.0.0.0", "--port", "8100"]
