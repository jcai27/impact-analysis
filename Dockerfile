FROM python:3.12-slim

# git is required for GitPython
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default data directory — mount a Railway volume here to persist the
# cloned repo and the SQLite DB across deploys and re-analysis runs.
RUN mkdir -p /data

EXPOSE 8000

# Railway injects $PORT; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
