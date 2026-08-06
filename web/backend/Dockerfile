# Build from the REPO ROOT, not this directory, so this can also COPY
# ffmpeg-bulk-cutter/ - e.g.:
#   docker build -f web/backend/Dockerfile -t kalakaar-backend .
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# ffmpeg-bulk-cutter kept as a sibling directory and added to PYTHONPATH
# below, not converted into an installable package - preserves "zero
# changes to the existing, tested pipeline scripts" for both this service
# and anyone still using them as standalone CLI tools.
COPY ffmpeg-bulk-cutter/ ./ffmpeg-bulk-cutter/
COPY web/backend/ ./web/backend/

RUN pip install --no-cache-dir -r ffmpeg-bulk-cutter/requirements.txt \
    && pip install --no-cache-dir -r ffmpeg-bulk-cutter/requirements-scoring.txt \
    && pip install --no-cache-dir -r web/backend/requirements.txt

ENV PYTHONPATH="/srv/ffmpeg-bulk-cutter"
WORKDIR /srv/web/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
