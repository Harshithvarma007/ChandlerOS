FROM python:3.14-slim

WORKDIR /srv

COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY app/ app/
COPY ingestion/knowledge.db ingestion/knowledge.db

WORKDIR /srv/app

EXPOSE 8000

# Secrets (GEMINI_API_KEY, GROQ_API_KEY) are injected as container env vars
# at deploy time (see .env.example) — never baked into the image.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
