# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Cloud Run sets PORT env var (default 8080)
ENV PORT=8080

EXPOSE 8080

# Use Gunicorn with Uvicorn workers for production
CMD exec uvicorn main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers 2 \
    --log-level info
