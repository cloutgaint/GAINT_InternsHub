FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system gaint && adduser --system --ingroup gaint gaint

COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install -r backend/requirements.txt

COPY backend/app ./backend/app
COPY vscode-extension ./vscode-extension
RUN mkdir -p /app/backend/uploads && chown -R gaint:gaint /app

WORKDIR /app/backend
USER gaint

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
