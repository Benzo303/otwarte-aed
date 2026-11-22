FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    AED_OFFLINE=true \
    AED_AREA=polska \
    AED_LISTEN_HOST=0.0.0.0

WORKDIR /app

# Takze w kontenerze aplikacja i biblioteki dzialaja w lokalnym .venv.
RUN python -m venv /app/.venv
COPY backend/requirements.txt /app/backend/requirements.txt
RUN /app/.venv/bin/python -m pip install --no-cache-dir --only-binary=:all: -r /app/backend/requirements.txt

RUN groupadd --gid 10001 aed \
    && useradd --uid 10001 --gid aed --create-home aed

COPY --chown=aed:aed backend /app/backend
COPY --chown=aed:aed frontend /app/frontend
COPY --chown=aed:aed data_standard /app/data_standard
COPY --chown=aed:aed backend/data/cache/poland_boundary.json /app/seed/poland_boundary.json
COPY --chown=aed:aed backend/data/cache/locations.json /app/seed/locations.json

RUN mkdir -p /app/backend/exports /app/backend/data/state \
    && chown aed:aed /app/backend/exports /app/backend/data/cache /app/backend/data/state

USER aed
EXPOSE 8000
CMD ["/app/.venv/bin/python", "-m", "backend.container_start"]
