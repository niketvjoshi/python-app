# Stage 1: Build (The "Kitchen")
FROM python:3.12-alpine AS builder

# 1. Install system tools needed for psutil and C-compilation
RUN apk add --no-cache gcc musl-dev linux-headers python3-dev

WORKDIR /app

# 2. Build Wheels (pre-compiled binaries) for all requirements
COPY app/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt


# Stage 2: Final Production (The "Dining Room")
FROM python:3.12-alpine

WORKDIR /app

# 3. Copy only the compiled wheels from the builder stage
COPY --from=builder /app/wheels /app/wheels
COPY --from=builder /app/requirements.txt .

# 4. Install using the pre-compiled wheels (No gcc needed here!)
RUN pip install --no-cache-dir /app/wheels/*

# 5. Copy the rest of your app
COPY app/ .

# Security: Non-root user
RUN adduser -D appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

# Metadata for your Jenkins pipeline to inject
ARG APP_VERSION=unknown
ENV VERSION=${APP_VERSION}

# Production server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "2", "--timeout", "60", "main:app"]