#!/usr/bin/env bash

set -euo pipefail


PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MMDVM_IQ_DIR="$PROJECT_DIR/third_party/MMDVM-IQ"
SOURCE_FILE="$MMDVM_IQ_DIR/SDRSoapy.cpp"


if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERROR:"
    echo "Missing MMDVM-IQ source:"
    echo "  $SOURCE_FILE"
    exit 1
fi


BACKUP_FILE="$(mktemp)"


cleanup() {
    cp "$BACKUP_FILE" "$SOURCE_FILE"
    rm -f "$BACKUP_FILE"
}


trap cleanup EXIT


cp "$SOURCE_FILE" "$BACKUP_FILE"


python3 - "$SOURCE_FILE" <<'PY'
from pathlib import Path
import sys


source_path = Path(
    sys.argv[1]
)

source = source_path.read_text(
    encoding="utf-8"
)


marker = "RF_GATEWAY_US_VHF_PATCH"


if marker in source:
    print(
        "MMDVM-IQ VHF patch already present "
        "in source tree."
    )
    raise SystemExit(0)


old = """  if ((txFreq < MIN_RF_FREQUENCY) || (txFreq > MAX_RF_FREQUENCY))
    return 4U;

  if ((rxFreq < MIN_RF_FREQUENCY) || (rxFreq > MAX_RF_FREQUENCY))
    return 4U;

  if ((pocsagFreq < MIN_RF_FREQUENCY) || (pocsagFreq > MAX_RF_FREQUENCY))
    return 4U;
"""


new = """  // RF_GATEWAY_US_VHF_PATCH
  //
  // Keep the upstream UHF range while additionally allowing
  // the US 2 m amateur allocation used by RF Gateway.
  // Actual hardware/driver limits are still enforced by SoapySDR.
  const auto supportedFrequency = [](uint32_t frequency) {
    const bool vhf =
      frequency >= 144000000U &&
      frequency <= 148000000U;

    const bool uhf =
      frequency >= MIN_RF_FREQUENCY &&
      frequency <= MAX_RF_FREQUENCY;

    return vhf || uhf;
  };

  if (!supportedFrequency(txFreq))
    return 4U;

  if (!supportedFrequency(rxFreq))
    return 4U;

  if (!supportedFrequency(pocsagFreq))
    return 4U;
"""


if old not in source:
    raise SystemExit(
        "ERROR: MMDVM-IQ SDRSoapy.cpp no longer matches "
        "the expected upstream frequency validation block. "
        "Refusing to patch automatically."
    )


source_path.write_text(
    source.replace(
        old,
        new,
        1,
    ),
    encoding="utf-8",
)


print(
    "Applied temporary RF Gateway MMDVM-IQ frequency patch:"
)
print(
    "  144.000-148.000 MHz"
)
print(
    "  upstream UHF range remains enabled"
)
PY


echo
echo "Building MMDVM-IQ..."
echo


make     -C "$MMDVM_IQ_DIR"     -j"$(nproc)"


if [ ! -x "$MMDVM_IQ_DIR/MMDVM-IQ" ]; then
    echo "ERROR:"
    echo "MMDVM-IQ binary was not created."
    exit 1
fi


echo
echo "MMDVM-IQ build completed."
echo
echo "The upstream source file is restored automatically;"
echo "the compiled binary retains the RF Gateway VHF extension."
echo
