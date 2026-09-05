#!/usr/bin/env bash

set -euo pipefail


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"

VOCODER_DIR="${REPO_ROOT}/third_party/imbe_vocoder"
WRAPPER_SOURCE="${SCRIPT_DIR}/imbe_wrapper.cpp"
OUTPUT_LIBRARY="${SCRIPT_DIR}/libimbe_vocoder_wrapper.so"


echo "=== RF Gateway IMBE wrapper build ==="
echo
echo "Repository:"
echo "  ${REPO_ROOT}"
echo
echo "Vocoder:"
echo "  ${VOCODER_DIR}"
echo
echo "Wrapper:"
echo "  ${WRAPPER_SOURCE}"
echo
echo "Output:"
echo "  ${OUTPUT_LIBRARY}"
echo


if ! command -v g++ >/dev/null 2>&1; then
    echo "ERROR: g++ not found" >&2
    exit 1
fi


if ! command -v nm >/dev/null 2>&1; then
    echo "ERROR: nm not found" >&2
    exit 1
fi


if ! command -v file >/dev/null 2>&1; then
    echo "ERROR: file command not found" >&2
    exit 1
fi


if [ ! -f "${WRAPPER_SOURCE}" ]; then
    echo \
        "ERROR: wrapper source not found: ${WRAPPER_SOURCE}" \
        >&2

    exit 1
fi


if [ ! -f "${VOCODER_DIR}/imbe_vocoder_api.h" ]; then
    echo \
        "ERROR: imbe_vocoder submodule is not initialized" \
        >&2

    echo \
        "Run: git submodule update --init --recursive" \
        >&2

    exit 1
fi


mapfile -t VOCODER_SOURCES < <(
    find "${VOCODER_DIR}" \
        -maxdepth 1 \
        -type f \
        -name '*.cc' \
        -print \
        | sort
)


if [ "${#VOCODER_SOURCES[@]}" -eq 0 ]; then
    echo \
        "ERROR: no imbe_vocoder C++ sources found" \
        >&2

    exit 1
fi


echo "Compiler:"
g++ --version | head -n 1

echo
echo "Architecture:"
uname -m

echo
echo "Vocoder source files:"
printf '  %s\n' "${VOCODER_SOURCES[@]}"

echo
echo "Building..."


rm -f "${OUTPUT_LIBRARY}"


g++ \
    -O2 \
    -Wall \
    -Wextra \
    -fPIC \
    -shared \
    -I"${VOCODER_DIR}" \
    "${WRAPPER_SOURCE}" \
    "${VOCODER_SOURCES[@]}" \
    -o "${OUTPUT_LIBRARY}"


echo
echo "=== BUILD RESULT ==="

ls -lh "${OUTPUT_LIBRARY}"

file "${OUTPUT_LIBRARY}"


echo
echo "=== EXPORTED RF GATEWAY SYMBOLS ==="

nm -D "${OUTPUT_LIBRARY}" \
    | grep 'rf_gateway_imbe_'


echo
echo "IMBE WRAPPER BUILD OK"
