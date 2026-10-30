FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=8 \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8000 \
    SERVER_RELOAD=false

WORKDIR /app
COPY requirements.txt ./
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --retries 8 --timeout 180 \
    --index-url "${PIP_INDEX_URL}" -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["python", "run.py"]
