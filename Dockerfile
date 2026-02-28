FROM python:3.12-alpine

WORKDIR /app

# Install dependencies first (better layer caching)
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Non-root user for security
RUN adduser -D appuser
USER appuser

EXPOSE 5000

# Gunicorn for production (not Flask dev server)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "2", "--timeout", "60", "main:app"]