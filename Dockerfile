FROM python:3.12-slim

WORKDIR /app

# requirements.txt copied and installed before the rest of the source so a plain code change
# doesn't invalidate this layer and force a full dependency reinstall on every rebuild.
COPY requirements.txt .
# --timeout/--retries: PyPI downloads over a flaky network path (seen locally on Docker
# Desktop's WSL2 networking, but a real deploy target could hit the same kind of transient
# blip) otherwise fail the whole build on one dropped connection instead of just retrying.
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt

COPY . .

# STORAGE_ROOT defaults to "storage" (a path resolved relative to the CWD, i.e. here) when not
# overridden — this directory is what docker-compose.yml mounts a volume onto for
# STORAGE_BACKEND=local so uploaded files survive the container being recreated, not just
# restarted. Created here too so the app still works standalone (docker run, no compose,
# STORAGE_ROOT left at its default) without a missing-directory error on first upload.
RUN mkdir -p /app/storage

EXPOSE 8000

# Same migrate-then-serve sequence already proven in render.yaml's own startCommand — no new,
# untested startup logic for this deployment target.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
