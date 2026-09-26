FROM python:3.12-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001

CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5001", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
