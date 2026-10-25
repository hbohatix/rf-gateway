"""The transmitter: one MMDVM RF runtime, one transmit mode.

The transmit mode (protocol + its saved settings, chosen on the RF Output
page) is the only place a mode lives. Routes do not carry a protocol: when
a route starts, the RF runtime is brought to exactly the current transmit
mode, and restarted if anything (protocol, device or any setting) differs
from what is running.
"""

from __future__ import annotations

from threading import RLock
from typing import Any

from app.config_store import mode_config_store
from app.mmdvm import mmdvm_process_manager, validate_runtime_mode
from app.rf import get_rf_device, rf_device_manager, validate_device_frequency


DEFAULT_CALLSIGN = "SP5OPS"

# Keys that do not change what goes on air.
_IGNORED_KEYS = {"updated_at", "protocol", "device_id"}

_lock = RLock()

runtime_state: dict[str, Any] = {
    "tx": False,
    "runtime_active": False,
    "rf_tx_active": False,
    "tx_stream_active": False,
    "protocol": None,
    "device_id": None,
    "config": None,
    "mmdvm": None,
    "error": None,
}


class RFControlError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def apply_mmdvm_status(status: dict[str, Any]) -> None:
    rf_tx_active = bool(status.get("rf_tx_active", False))
    runtime_state["runtime_active"] = bool(status.get("runtime_active", False))
    runtime_state["rf_tx_active"] = rf_tx_active
    runtime_state["tx_stream_active"] = rf_tx_active
    runtime_state["tx"] = rf_tx_active
    runtime_state["mmdvm"] = status


def refresh_status() -> dict[str, Any]:
    apply_mmdvm_status(mmdvm_process_manager.status())
    status = dict(runtime_state)
    protocol, settings = active_mode()
    status["active_protocol"] = protocol
    status["active_mode_summary"] = describe_mode(protocol, settings)
    return status


# ------------------------------------------------------------ transmit mode
def active_mode() -> tuple[str | None, dict[str, Any] | None]:
    protocol = mode_config_store.get_active_protocol()
    if not protocol:
        return None, None
    return protocol, mode_config_store.get_mode(protocol)


def require_active_mode() -> tuple[str, dict[str, Any]]:
    protocol, settings = active_mode()
    if not protocol:
        raise RFControlError(400, "Choose a transmit mode on the RF Output page first")
    if not settings:
        raise RFControlError(400, f"{protocol.upper()} settings have not been saved yet (RF Output page)")
    return protocol, settings


def settings_signature(settings: dict[str, Any] | None) -> dict[str, Any]:
    return {key: value for key, value in (settings or {}).items() if key not in _IGNORED_KEYS}


def _frequency_label(settings: dict[str, Any]) -> str | None:
    try:
        return f"{int(settings['frequency_hz']) / 1e6:.4f} MHz"
    except (KeyError, TypeError, ValueError):
        return None


def describe_mode(protocol: str | None, settings: dict[str, Any] | None) -> str | None:
    """Short human label, e.g. ``DMR · TS1 · CC15 · TG 12345 · 433.4500 MHz``."""
    if not protocol:
        return None
    s = settings or {}
    parts: list[str]
    if protocol == "dmr":
        target = "TG" if s.get("call_type", "group") == "group" else "ID"
        parts = ["DMR", f"TS{s.get('timeslot', '?')}", f"CC{s.get('color_code', '?')}", f"{target} {s.get('talkgroup', '?')}"]
    elif protocol == "p25":
        parts = ["P25", f"NAC {s.get('nac', '?')}", f"TG {s.get('talkgroup', '?')}"]
    elif protocol == "nxdn":
        target = "TG" if s.get("call_type", "group") == "group" else "ID"
        parts = ["NXDN", f"RAN {s.get('ran', '?')}", f"{target} {s.get('talkgroup', '?')}"]
    elif protocol == "ysf":
        parts = ["YSF", f"DG-ID {s.get('dg_id', 0)}", str(s.get("callsign") or "?")]
    elif protocol == "dstar":
        parts = ["D-Star", f"{s.get('callsign') or '?'} → {s.get('your_call') or 'CQCQCQ'}"]
    elif protocol == "fm":
        parts = ["FM", f"{s.get('deviation_khz', '?')} kHz dev"]
        if s.get("tx_ctcss_hz"):
            parts.append(f"CTCSS {s['tx_ctcss_hz']} Hz")
    else:
        parts = [protocol.upper()]
    frequency = _frequency_label(s)
    if frequency:
        parts.append(frequency)
    return " · ".join(parts)


# ------------------------------------------------------------ RF runtime
def runtime_matches(protocol: str, settings: dict[str, Any], device_id: str) -> bool:
    return bool(
        mmdvm_process_manager.is_running
        and runtime_state.get("protocol") == protocol
        and runtime_state.get("device_id") == device_id
        and settings_signature(runtime_state.get("config")) == settings_signature(settings)
    )


def _start_runtime_unlocked(protocol: str, settings: dict[str, Any], device_id: str) -> None:
    device = get_rf_device(device_id)
    if device is None or not device.get("available", False) or not device.get("probe_ok", False):
        raise RFControlError(400, f"RF device {device_id} is not available")

    request_data = {**settings_signature(settings), "protocol": protocol, "device_id": device_id}
    try:
        validate_runtime_mode(protocol, request_data)
        validate_device_frequency(device, int(request_data["frequency_hz"]))
    except (KeyError, TypeError, ValueError) as error:
        raise RFControlError(400, f"{protocol.upper()} settings: {error}") from error

    try:
        rf_device_manager.close(device_id)
    except Exception:
        pass

    runtime_state["protocol"] = protocol
    runtime_state["device_id"] = device_id
    runtime_state["config"] = request_data

    try:
        status = mmdvm_process_manager.start(
            protocol,
            request_data,
            device=device,
            callsign=str(request_data.get("callsign") or DEFAULT_CALLSIGN).strip().upper(),
        )
    except Exception as error:
        apply_mmdvm_status(mmdvm_process_manager.status())
        runtime_state["error"] = str(error)
        raise RFControlError(500, str(error)) from error

    apply_mmdvm_status(status)
    runtime_state["error"] = None


def ensure_runtime(protocol: str, settings: dict[str, Any], device_id: str) -> str:
    """Run exactly ``protocol``/``settings`` on ``device_id``.

    Returns ``"kept"`` (already running like that), ``"started"`` or
    ``"restarted"`` (something differed, so it was stopped first).
    """
    protocol = str(protocol).strip().lower()
    with _lock:
        if runtime_matches(protocol, settings, device_id):
            return "kept"
        was_running = bool(mmdvm_process_manager.is_running)
        if was_running:
            stop_rf_runtime()
        _start_runtime_unlocked(protocol, settings, device_id)
        return "restarted" if was_running else "started"


def stop_rf_runtime() -> dict[str, Any]:
    with _lock:
        apply_mmdvm_status(mmdvm_process_manager.stop())
        runtime_state["protocol"] = None
        runtime_state["device_id"] = None
        runtime_state["config"] = None
        runtime_state["error"] = None
        return runtime_state
