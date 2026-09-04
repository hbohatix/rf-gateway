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

MMDVM_IQ_DIR="$PROJECT_DIR/third_party/MMDVM-IQ"
MMDVM_HOST_DIR="$PROJECT_DIR/third_party/MMDVM-Host"


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
    python3-soapysdr \
    build-essential \
    pkg-config \
    ffmpeg \
    usbutils \
    pciutils \
    jq \
    libsoapysdr-dev \
    soapysdr-tools \
    libmosquitto-dev \
    mosquitto \
    mosquitto-clients \
    nlohmann-json3-dev


# ------------------------------------------------------------
# MQTT
# ------------------------------------------------------------

echo
echo "Starting Mosquitto MQTT broker..."
echo


$SUDO systemctl enable --now mosquitto


if systemctl is-active --quiet mosquitto; then

    echo "Mosquitto:"
    echo "  active"

else

    echo "ERROR:"
    echo "Mosquitto failed to start."
    exit 1

fi


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

    if [ "$NODE_MAJOR" -ne 22 ]; then
        echo "RF Gateway expects Node.js 22.x."
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

    curl -fsSL https://deb.nodesource.com/setup_22.x \
        | $SUDO -E bash -

    $SUDO apt-get install -y nodejs

fi


echo
echo "Node.js:"
node --version

echo
echo "npm:"
npm --version


# ------------------------------------------------------------
# Git submodules
# ------------------------------------------------------------

echo
echo "Initializing Git submodules..."
echo


cd "$PROJECT_DIR"


git submodule sync --recursive


git submodule update \
    --init \
    --recursive


# ------------------------------------------------------------
# Python virtual environment
# ------------------------------------------------------------

echo
echo "Preparing Python virtual environment..."
echo


RECREATE_VENV=0


if [ ! -d "$VENV_DIR" ]; then

    RECREATE_VENV=1

elif [ ! -f "$VENV_DIR/pyvenv.cfg" ]; then

    RECREATE_VENV=1

elif ! grep -q \
    '^include-system-site-packages = true$' \
    "$VENV_DIR/pyvenv.cfg"; then

    echo
    echo "Existing Python virtual environment does not use"
    echo "system site packages."
    echo
    echo "It will be recreated so the backend can access"
    echo "Debian's python3-soapysdr package."
    echo

    RECREATE_VENV=1

fi


if [ "$RECREATE_VENV" -eq 1 ]; then

    rm -rf "$VENV_DIR"

    python3 -m venv \
        --system-site-packages \
        "$VENV_DIR"

fi


# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"


echo
echo "Upgrading pip..."
echo


python -m pip install \
    --upgrade \
    pip \
    setuptools \
    wheel


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


python -m pip install \
    -r "$BACKEND_DIR/requirements.txt"


# ------------------------------------------------------------
# Python SoapySDR test
# ------------------------------------------------------------

echo
echo "Checking Python SoapySDR binding..."
echo


python - <<'PY'
import SoapySDR

print("SoapySDR Python binding:")
print(f"  {SoapySDR.__file__}")
PY


deactivate


# ------------------------------------------------------------
# MMDVM-IQ
# ------------------------------------------------------------

echo
echo "Building MMDVM-IQ..."
echo


if [ ! -d "$MMDVM_IQ_DIR" ]; then

    echo "ERROR:"
    echo "Missing MMDVM-IQ submodule:"
    echo "  $MMDVM_IQ_DIR"

    exit 1

fi


cd "$MMDVM_IQ_DIR"


make -j"$(nproc)"


if [ ! -x "$MMDVM_IQ_DIR/MMDVM-IQ" ]; then

    echo "ERROR:"
    echo "MMDVM-IQ binary was not created."

    exit 1

fi


echo
echo "MMDVM-IQ version:"
"$MMDVM_IQ_DIR/MMDVM-IQ" --version


# ------------------------------------------------------------
# MMDVM-Host
# ------------------------------------------------------------

echo
echo "Building MMDVM-Host..."
echo


if [ ! -d "$MMDVM_HOST_DIR" ]; then

    echo "ERROR:"
    echo "Missing MMDVM-Host submodule:"
    echo "  $MMDVM_HOST_DIR"

    exit 1

fi


cd "$MMDVM_HOST_DIR"


make -j"$(nproc)"


if [ ! -x "$MMDVM_HOST_DIR/MMDVM-Host" ]; then

    echo "ERROR:"
    echo "MMDVM-Host binary was not created."

    exit 1

fi


echo
echo "MMDVM-Host version:"
"$MMDVM_HOST_DIR/MMDVM-Host" --version


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
# SoapySDR check
# ------------------------------------------------------------

echo
echo "Checking SoapySDR..."
echo


SoapySDRUtil --info || true


echo
echo "Detected SoapySDR devices:"
echo


SoapySDRUtil --find || true


# ------------------------------------------------------------
# MQTT check
# ------------------------------------------------------------

echo
echo "Checking MQTT listener..."
echo


ss -ltn | grep ':1883' || true


# ------------------------------------------------------------
# USB devices
# ------------------------------------------------------------

echo
echo "Detected USB devices:"
echo


lsusb || true


# ------------------------------------------------------------
# PCI devices
# ------------------------------------------------------------

echo
echo "Detected PCI devices:"
echo


lspci || true


# ------------------------------------------------------------
# Finished
# ------------------------------------------------------------

cd "$PROJECT_DIR"


echo
echo "============================================================"
echo " RF Gateway installation completed"
echo "============================================================"
echo

echo "Backend environment:"
echo
echo "  source backend/.venv/bin/activate"

echo
echo "MMDVM-IQ:"
echo
echo "  third_party/MMDVM-IQ/MMDVM-IQ"

echo
echo "MMDVM-Host:"
echo
echo "  third_party/MMDVM-Host/MMDVM-Host"

echo
echo "MMDVM configuration:"
echo
echo "  config/mmdvm/"

echo
echo "Development startup:"
echo
echo "  ./scripts/run-dev.sh"
echo
