FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels -r requirements.lock \
    && python -m pip wheel --wheel-dir /wheels --no-deps .

FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN groupadd --gid 10001 hermes \
    && useradd --uid 10001 --gid hermes --no-create-home --shell /usr/sbin/nologin hermes
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels hermes-mail-service \
    && rm -rf /wheels
USER 10001:10001
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "hermes.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

