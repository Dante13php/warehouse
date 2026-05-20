# ---------------------------------------------------------------------------
# ARQ worker — async background job processor for Warehouse.
# Placeholder image until the worker module is implemented.
# When the app code lands, mount/copy it and switch CMD to:
#   arq app.infrastructure.worker.WorkerSettings
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Minimal deps so the worker can connect to Redis once implemented.
RUN pip install --no-cache-dir "arq>=0.25" "redis>=5.0"

# Placeholder entrypoint: keeps the container alive and reachable until the
# real ARQ WorkerSettings module exists in the application package.
CMD ["python", "-c", "import time; print('ARQ worker placeholder running — implement app.infrastructure.worker.WorkerSettings', flush=True); [time.sleep(3600) for _ in iter(int, 1)]"]
