#!/usr/bin/env bash

set -euo pipefail


PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

VENV_DIR="$BACKEND_DIR/.venv"


BACKEND_PID=""
FRONTEND_PID=""


cleanup() {
    echo
    echo "Stopping RF Gateway..."


    if [ -n "$BACKEND_PID" ]; then
        kill -- "-$BACKEND_PID" 2>/dev/null || true
    fi


    if [ -n "$FRONTEND_PID" ]; then
        kill -- "-$FRONTEND_PID" 2>/dev/null || true
    fi


    wait 2>/dev/null || true


    echo "RF Gateway stopped."
}


trap cleanup EXIT INT TERM


if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR:"
    echo "Python virtual environment does not exist."
    echo
    echo "Run:"
    echo
    echo "  ./scripts/install-debian.sh"
    echo

    exit 1
fi


echo
echo "============================================================"
echo " RF Gateway Development Runtime"
echo "============================================================"
echo


# ------------------------------------------------------------
# Port checks
# ------------------------------------------------------------

if ss -ltn 2>/dev/null | grep -q ':8000 '; then
    echo "ERROR:"
    echo "Port 8000 is already in use."
    echo
    echo "Check:"
    echo "  ss -ltnp | grep ':8000'"
    echo

    exit 1
fi


if ss -ltn 2>/dev/null | grep -q ':5173 '; then
    echo "ERROR:"
    echo "Port 5173 is already in use."
    echo
    echo "Check:"
    echo "  ss -ltnp | grep ':5173'"
    echo

    exit 1
fi


# ------------------------------------------------------------
# Backend
# ------------------------------------------------------------

echo "Starting FastAPI..."
echo


cd "$BACKEND_DIR"


# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"


setsid uvicorn app.main:app \
    --reload \
    --host 0.0.0.0 \
    --port 8000 &


BACKEND_PID=$!


# ------------------------------------------------------------
# Frontend
# ------------------------------------------------------------

echo "Starting React / Vite..."
echo


cd "$FRONTEND_DIR"


setsid npm run dev -- \
    --host 0.0.0.0 \
    --port 5173 \
    --strictPort &


FRONTEND_PID=$!


# ------------------------------------------------------------
# URLs
# ------------------------------------------------------------

echo
echo "RF Gateway running:"
echo
echo "Frontend:"
echo "  http://localhost:5173"
echo
echo "Backend:"
echo "  http://localhost:8000"
echo
echo "API documentation:"
echo "  http://localhost:8000/docs"
echo
echo "Press CTRL+C to stop."
echo


wait
