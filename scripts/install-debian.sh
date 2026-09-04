#!/usr/bin/env bash

set -euo pipefail


# ============================================================
# RF Gateway
# Debian / Raspberry Pi OS installation script
# ============================================================


PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

VENV_DIR="$BACKEND_DIR/.venv"


echo
echo "============================================================"
echo " RF Gateway Installer"
echo "============================================================"
echo
echo "Project directory:"
echo "  $PROJECT_DIR"
echo


# ------------------------------------------------------------
# Root / sudo detection
# ------------------------------------------------------------

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "ERROR: sudo is required."
        exit 1
    fi
fi


# ------------------------------------------------------------
# OS detection
# ------------------------------------------------------------

if [ ! -f /etc/os-release ]; then
    echo "ERROR: Cannot detect Linux distribution."
    exit 1
fi


. /etc/os-release


echo "Detected operating system:"
echo "  ${PRETTY_NAME:-unknown}"
echo


case "${ID:-}" in
    debian|raspbian)
        ;;
    *)
        echo "WARNING:"
        echo "This installer was designed for Debian / Raspberry Pi OS."
        echo
        ;;
esac


# ------------------------------------------------------------
# Architecture
# ------------------------------------------------------------

ARCH="$(uname -m)"

echo "Architecture:"
echo "  $ARCH"
echo


case "$ARCH" in
    x86_64|aarch64|arm64)
        ;;
    armv7l)
        echo "WARNING:"
        echo "32-bit ARM detected."
        echo
        echo "RF Gateway development is recommended on a 64-bit OS."
        echo
        ;;
    *)
        echo "WARNING: Untested architecture: $ARCH"
        ;;
esac


# ------------------------------------------------------------
# System packages
# ------------------------------------------------------------

echo
echo "Installing system packages..."
echo


$SUDO apt-get update


$SUDO apt-get install -y \
    git \
    curl \
    ca-certificates \
    gnupg \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    pkg-config \
    ffmpeg \
    usbutils \
    pciutils \
    jq


# ------------------------------------------------------------
# Node.js
# ------------------------------------------------------------

echo
echo "Checking Node.js..."
echo


INSTALL_NODE=0


if command -v node >/dev/null 2>&1; then

    NODE_MAJOR="$(node --version | sed 's/^v//' | cut -d. -f1)"

    echo "Found Node.js:"
    echo "  $(node --version)"

    if [ "$NODE_MAJOR" -lt 22 ]; then
        echo "Node.js is too old."
        INSTALL_NODE=1
    fi

else

    echo "Node.js not installed."
    INSTALL_NODE=1

fi


if [ "$INSTALL_NODE" -eq 1 ]; then

    echo
    echo "Installing Node.js 22.x..."
    echo

    curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO -E bash -

    $SUDO apt-get install -y nodejs

fi


echo
echo "Node.js:"
node --version

echo
echo "npm:"
npm --version


# ------------------------------------------------------------
# Python virtual environment
# ------------------------------------------------------------

echo
echo "Creating Python virtual environment..."
echo


if [ ! -d "$VENV_DIR" ]; then

    python3 -m venv "$VENV_DIR"

fi


# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"


echo
echo "Upgrading pip..."
echo


python -m pip install --upgrade pip setuptools wheel


# ------------------------------------------------------------
# Backend dependencies
# ------------------------------------------------------------

echo
echo "Installing backend dependencies..."
echo


if [ ! -f "$BACKEND_DIR/requirements.txt" ]; then

    echo "ERROR:"
    echo "Missing:"
    echo "  $BACKEND_DIR/requirements.txt"

    exit 1

fi


pip install -r "$BACKEND_DIR/requirements.txt"


# ------------------------------------------------------------
# Frontend dependencies
# ------------------------------------------------------------

echo
echo "Installing frontend dependencies..."
echo


cd "$FRONTEND_DIR"


if [ -f package-lock.json ]; then

    npm ci

else

    npm install

fi


# ------------------------------------------------------------
# Build frontend
# ------------------------------------------------------------

echo
echo "Testing frontend production build..."
echo


npm run build


# ------------------------------------------------------------
# FFmpeg check
# ------------------------------------------------------------

echo
echo "Checking FFmpeg..."
echo


ffmpeg -version | head -n 1


# ------------------------------------------------------------
# USB devices
# ------------------------------------------------------------

echo
echo "Detected USB devices:"
echo


lsusb || true


# ------------------------------------------------------------
# Finished
# ------------------------------------------------------------

echo
echo "============================================================"
echo " RF Gateway installation completed"
echo "============================================================"
echo
echo "Backend environment:"
echo
echo "  source backend/.venv/bin/activate"
echo
echo "Development startup:"
echo
echo "  ./scripts/run-dev.sh"
echo