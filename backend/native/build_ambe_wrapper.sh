#!/usr/bin/env bash
# Build libambe_vocoder_wrapper.so: OP25's software AMBE+2/AMBE encoder
# (backend/native/ambe) on top of the imbe_vocoder submodule.
#
# Used by the DMR (and other AMBE based) voice sessions. No DVSI hardware
# is required; a hardware vocoder can still be selected in mode settings.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"

VOCODER_DIR="${REPO_ROOT}/third_party/imbe_vocoder"
AMBE_DIR="${SCRIPT_DIR}/ambe"
WRAPPER_SOURCE="${SCRIPT_DIR}/ambe_wrapper.cpp"
OUTPUT_LIBRARY="${SCRIPT_DIR}/libambe_vocoder_wrapper.so"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

echo "=== RF Gateway AMBE encoder build ==="

for tool in gcc g++ nm; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "ERROR: ${tool} not found" >&2
        exit 1
    fi
done

if [ ! -f "${VOCODER_DIR}/imbe_vocoder.h" ]; then
    echo "ERROR: imbe_vocoder submodule is not initialized" >&2
    echo "Run: git submodule update --init --recursive" >&2
    exit 1
fi

mapfile -t VOCODER_SOURCES < <(find -L "${VOCODER_DIR}" -maxdepth 1 -type f -name '*.cc' -print | sort)

if [ "${#VOCODER_SOURCES[@]}" -eq 0 ]; then
    echo "ERROR: no imbe_vocoder sources found in ${VOCODER_DIR}" >&2
    exit 1
fi

COMMON_FLAGS=(-O2 -fPIC -I"${VOCODER_DIR}" -I"${AMBE_DIR}")

echo "Compiling mbelib (C)..."
gcc "${COMMON_FLAGS[@]}" -c "${AMBE_DIR}/mbelib.c" -o "${BUILD_DIR}/mbelib.o"
gcc "${COMMON_FLAGS[@]}" -c "${AMBE_DIR}/ambe.c" -o "${BUILD_DIR}/ambe.o"

echo "Linking ${OUTPUT_LIBRARY}..."
rm -f "${OUTPUT_LIBRARY}"
g++ "${COMMON_FLAGS[@]}" -Wall -shared \
    "${WRAPPER_SOURCE}" \
    "${AMBE_DIR}/ambe_encoder.cc" \
    "${VOCODER_SOURCES[@]}" \
    "${BUILD_DIR}/mbelib.o" \
    "${BUILD_DIR}/ambe.o" \
    -lm \
    -Wl,--no-undefined \
    -o "${OUTPUT_LIBRARY}"

echo
ls -lh "${OUTPUT_LIBRARY}"
nm -D "${OUTPUT_LIBRARY}" | grep 'rf_gateway_ambe_'
echo
echo "AMBE WRAPPER BUILD OK"
