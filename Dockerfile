FROM python:3.12-slim

WORKDIR /app

# Cache bust - v3.1
ARG CACHE_BUST=3.1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]