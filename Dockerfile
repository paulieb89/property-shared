FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# System deps for Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# Copy dependency manifests first for better layer caching
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra api --extra snapshot

# Planning disabled: scraping requires UK residential IP
# RUN uv sync ... --extra planning && playwright install chromium

# Copy application code
COPY app ./app
COPY property_core ./property_core

# G1a boot-only verification (docs/design/ppd-private-delivery.md step 4):
# materializes and validates a real snapshot, off the app's own lifespan and
# process state, invoked out of band via `fly ssh console`. Not wired into
# CMD; the app never imports it. One file only -- not tools/ or property_cli/.
COPY tools/ppd_snapshot/boot_only_verify.py ./boot_only_verify.py

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

