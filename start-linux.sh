#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

docker compose -p gaint-interns-hub-v8-1 up -d postgres
[ -f backend/.env ] || cp backend/.env.example backend/.env
[ -x backend/.venv/bin/python ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
(cd backend && .venv/bin/python -m uvicorn app.main:app --reload) &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT
(cd frontend && npm install && npm run dev)
