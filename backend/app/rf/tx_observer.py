"""RF TX evidence; never treat UDP send success as proof of on-air RF.

MMDVM-IQ's TX ON/OFF log lines are modem-level indications.
An *independent* calibrated receiver can write an atomic JSON observation
at RF_TX_EVIDENCE_FILE with:
{"observed_at_unix": 1792000000.0, "frequency_hz": 438825000,
 "rf_detected": true, "power_dbm": -48.2}
Only a fresh observation during a call can confirm radiated RF energy.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any


def _tail_from(path: Path, start: int) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, min(start, size)))
            return fh.read(512 * 1024).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _end(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _latest_sensor_evidence(since: float, frequency_hz: int | None) -> dict[str, Any]:
    configured = (os.getenv("RF_TX_EVIDENCE_FILE") or "").strip()
    if not configured:
        return {"state": "not_configured", "verified": False}
    if frequency_hz is None:
        return {"state": "unknown_frequency", "verified": False}
    try:
        path = Path(configured)
        if path.stat().st_size > 16384:
            raise ValueError("Evidence file too large")
        data = json.loads(path.read_text(encoding="utf-8"))
        timestamp = float(data["observed_at_unix"])
        frequency = int(data["frequency_hz"])
        detected = data.get("rf_detected") is True
        if not (since <= timestamp <= time.time() + 2):
            return {"state": "stale", "verified": False}
        if frequency_hz is not None and abs(frequency - frequency_hz) > 15000:
            return {"state": "wrong_frequency", "verified": False}
        return {
            "state": "detected" if detected else "not_detected",
            "verified": detected,
            "frequency_hz": frequency,
            "observed_at_unix": timestamp,
            "power_dbm": data.get("power_dbm"),
            "measurement": "external_rf_energy",
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        return {"state": "invalid", "verified": False, "error": str(error)[:180]}


def capture_tx_start() -> dict[str, Any]:
    from app.mmdvm.process_manager import MMDVM_IQ_LOG, MMDVM_HOST_LOG
    return {
        "started_at_unix": time.time(),
        "iq_log_offset": _end(MMDVM_IQ_LOG),
        "host_log_offset": _end(MMDVM_HOST_LOG),
    }


def capture_tx_result(start: dict[str, Any], frequency_hz: int | None = None) -> dict[str, Any]:
    from app.mmdvm.process_manager import (
        MMDVM_IQ_LOG, MMDVM_HOST_LOG, mmdvm_process_manager
    )
    iq = _tail_from(MMDVM_IQ_LOG, int(start["iq_log_offset"]))
    host = _tail_from(MMDVM_HOST_LOG, int(start["host_log_offset"]))
    runtime = mmdvm_process_manager.status()
    tx_on = len(re.findall(r"\bTX ON\b", iq))
    tx_off = len(re.findall(r"\bTX OFF\b", iq))
    failures = [
        line[:220] for line in host.splitlines()
        if re.search(r"\b(?:error|failed|lost|NAK)\b", line, re.IGNORECASE)
    ][-5:]
    if frequency_hz is None:
        raw_frequency = runtime.get("channel_frequency_hz")
        try:
            frequency_hz = int(raw_frequency) if raw_frequency else None
        except (TypeError, ValueError):
            frequency_hz = None
    independent = _latest_sensor_evidence(
        float(start["started_at_unix"]), frequency_hz
    )
    return {
        "mmdvm_runtime_active": bool(runtime.get("runtime_active")),
        "mmdvm_ready": bool(runtime.get("runtime_ready")),
        "mmdvm_rf_tx_active": bool(runtime.get("rf_tx_active")),
        "modem_tx_on_events": tx_on,
        "modem_tx_off_events": tx_off,
        "modem_reported_tx": tx_on > 0,
        "modem_signal": "observed" if tx_on else (
            "unavailable" if runtime.get("backend") == "mmdvm_uart"
            else "not_observed"
        ),
        "mmdvm_errors": failures,
        "rf": independent,
        "rf_verified": bool(independent.get("verified")),
        "verification_note": (
            "External receiver measured RF energy; modulation/audio not independently decoded."
            if independent.get("verified")
            else "P25 UDP and modem TX indications do not prove radiated RF. External receiver required."
        ),
    }


def live_rf_tx_status() -> dict[str, Any]:
    from app.mmdvm.process_manager import mmdvm_process_manager
    runtime = mmdvm_process_manager.status()
    return {
        "backend": runtime.get("backend"),
        "runtime_active": bool(runtime.get("runtime_active")),
        "runtime_ready": bool(runtime.get("runtime_ready")),
        "modem_rf_tx_active": bool(runtime.get("rf_tx_active")),
        "hardware_tx_observation": (
            "modem_indication"
            if runtime.get("backend") != "mmdvm_uart"
            else "unavailable"
        ),
        "last_error": runtime.get("last_error"),
        "rf_verified": False,
        "note": "Modem indication only; see last completed call for external RF confirmation.",
    }
