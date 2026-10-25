#!/usr/bin/env bash
# Build the development-only frame checkers (dmr_frame_check, ysf_frame_check).
# They validate frames produced by app.voice with MMDVM-Host's own decoders.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NATIVE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${NATIVE_DIR}/../.." && pwd)"
MMDVM_DIR="${REPO_ROOT}/third_party/MMDVM-Host"
AMBE_DIR="${NATIVE_DIR}/ambe"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

gcc -O2 -I"${AMBE_DIR}" -c "${AMBE_DIR}/mbelib.c" -o "${BUILD_DIR}/mbelib.o"
gcc -O2 -I"${AMBE_DIR}" -c "${AMBE_DIR}/ambe.c" -o "${BUILD_DIR}/ambe.o"

COMMON=(-O2 -std=c++17 -I"${MMDVM_DIR}" -I"${AMBE_DIR}")

g++ "${COMMON[@]}" "${SCRIPT_DIR}/dmr_frame_check.cpp" \
    "${MMDVM_DIR}/AMBEFEC.cpp" "${MMDVM_DIR}/BPTC19696.cpp" "${MMDVM_DIR}/DMRFullLC.cpp" \
    "${MMDVM_DIR}/DMRLC.cpp" "${MMDVM_DIR}/Golay24128.cpp" "${MMDVM_DIR}/Hamming.cpp" \
    "${MMDVM_DIR}/RS129.cpp" "${MMDVM_DIR}/Utils.cpp" \
    "${BUILD_DIR}/mbelib.o" "${BUILD_DIR}/ambe.o" -lm -o "${SCRIPT_DIR}/dmr_frame_check"
echo "Built ${SCRIPT_DIR}/dmr_frame_check"

g++ "${COMMON[@]}" "${SCRIPT_DIR}/ysf_frame_check.cpp" \
    "${MMDVM_DIR}/YSFFICH.cpp" "${MMDVM_DIR}/YSFPayload.cpp" "${MMDVM_DIR}/YSFConvolution.cpp" \
    "${MMDVM_DIR}/CRC.cpp" "${MMDVM_DIR}/Golay24128.cpp" "${MMDVM_DIR}/AMBEFEC.cpp" \
    "${MMDVM_DIR}/Hamming.cpp" "${MMDVM_DIR}/Utils.cpp" \
    "${BUILD_DIR}/mbelib.o" "${BUILD_DIR}/ambe.o" -lm -o "${SCRIPT_DIR}/ysf_frame_check"
echo "Built ${SCRIPT_DIR}/ysf_frame_check"

g++ "${COMMON[@]}" "${SCRIPT_DIR}/dstar_frame_check.cpp" \
    "${MMDVM_DIR}/DStarHeader.cpp" "${MMDVM_DIR}/CRC.cpp" "${MMDVM_DIR}/Golay24128.cpp" \
    "${MMDVM_DIR}/AMBEFEC.cpp" "${MMDVM_DIR}/Hamming.cpp" "${MMDVM_DIR}/Utils.cpp" \
    "${BUILD_DIR}/mbelib.o" "${BUILD_DIR}/ambe.o" -lm -o "${SCRIPT_DIR}/dstar_frame_check"
echo "Built ${SCRIPT_DIR}/dstar_frame_check"
