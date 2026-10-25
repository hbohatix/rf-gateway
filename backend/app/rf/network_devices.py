"""Network-attached SDR transmitters (PlutoSDR, LibreSDR, LimeSDR, USRP).

MMDVM-IQ supports these SoapySDR devices natively through its [Soapy]
Type/URI settings, so a remote SDR can be the RF device of a route. The
devices are registered by the operator (they cannot be auto-discovered
reliably over the network) and stored in backend/data/network_sdr_devices.json.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STORE_PATH = DATA_DIR / "network_sdr_devices.json"

# MMDVM-IQ device types (SDRSoapy.cpp). TX gain always defaults to 0 so a new
# transmitter starts at minimum power; the operator raises it deliberately.
NETWORK_SDR_TYPES: dict[str, dict[str, Any]] = {
    "plutosdr": {"label": "ADALM-Pluto", "rx_gain": 30, "tx_gain": 0, "uri_example": "ip:192.168.2.1", "iiod": True},
    "libresdr": {"label": "LibreSDR", "rx_gain": 20, "tx_gain": 0, "uri_example": "ip:192.168.2.10", "iiod": True},
    "limesdr": {"label": "LimeSDR", "rx_gain": 30, "tx_gain": 0, "uri_example": "", "iiod": False},
    "limemini": {"label": "LimeSDR Mini / LimeNET Micro", "rx_gain": 30, "tx_gain": 0, "uri_example": "serial=xxxx", "iiod": False},
    "usrp": {"label": "Ettus USRP", "rx_gain": 30, "tx_gain": 0, "uri_example": "addr=192.168.10.2", "iiod": False},
}

IIOD_PORT = 30431
_lock = threading.Lock()

# SoapySDR module needed by each MMDVM-IQ device type (substring of the module path).
SOAPY_MODULE_HINTS = {
    "plutosdr": ("pluto", "SoapyPlutoSDR"),
    "libresdr": ("pluto", "SoapyPlutoSDR"),
    "limesdr": ("lms7", "SoapyLMS7 (LimeSuite)"),
    "limemini": ("lms7", "SoapyLMS7 (LimeSuite)"),
    "usrp": ("uhd", "SoapyUHD"),
}


def soapy_module_status(sdr_type: str) -> tuple[bool | None, str | None]:
    """Whether the SoapySDR module for ``sdr_type`` is installed (None = unknown)."""
    hint = SOAPY_MODULE_HINTS.get(sdr_type)
    if hint is None:
        return None, None
    try:
        import SoapySDR  # noqa: PLC0415 - optional on development hosts

        modules = [str(module).lower() for module in SoapySDR.listModules()]
    except Exception:  # noqa: BLE001
        return None, None
    if any(hint[0] in module for module in modules):
        return True, None
    return False, f"{hint[1]} SoapySDR module is not installed on this gateway"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict[str, Any]]:
    if not STORE_PATH.is_file():
        return []
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    devices = data.get("devices") if isinstance(data, dict) else None
    return [item for item in devices or [] if isinstance(item, dict)]


def _save(devices: list[dict[str, Any]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STORE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"version": 1, "devices": devices}, indent=2), encoding="utf-8")
    temporary.replace(STORE_PATH)


def _validate(entry: dict[str, Any]) -> dict[str, Any]:
    sdr_type = str(entry.get("sdr_type") or "").strip().lower()
    if sdr_type not in NETWORK_SDR_TYPES:
        raise ValueError(f"SDR type must be one of {', '.join(NETWORK_SDR_TYPES)}")
    uri = str(entry.get("uri") or "").strip()
    if len(uri) > 200 or any(ch in uri for ch in "\r\n\"#;"):
        raise ValueError("Invalid SoapySDR URI")
    if NETWORK_SDR_TYPES[sdr_type]["iiod"] and uri and not re.fullmatch(r"(ip|usb):[\w.\-:]+", uri):
        raise ValueError("Pluto/LibreSDR URI must look like ip:192.168.2.1 or usb:1.2.5")
    defaults = NETWORK_SDR_TYPES[sdr_type]
    try:
        rx_gain = int(entry.get("rx_gain", defaults["rx_gain"]))
        tx_gain = int(entry.get("tx_gain", defaults["tx_gain"]))
    except (TypeError, ValueError) as error:
        raise ValueError("Gains must be integers") from error
    if not 0 <= rx_gain <= 100 or not 0 <= tx_gain <= 100:
        raise ValueError("Gains must be between 0 and 100")
    label = str(entry.get("label") or "").strip()[:60] or f"{defaults['label']} {uri}".strip()
    return {"sdr_type": sdr_type, "uri": uri, "rx_gain": rx_gain, "tx_gain": tx_gain, "label": label}


def list_network_devices() -> list[dict[str, Any]]:
    with _lock:
        return deepcopy(_load())


def add_network_device(entry: dict[str, Any]) -> dict[str, Any]:
    clean = _validate(entry)
    device = {"id": f"net-{uuid.uuid4().hex[:8]}", **clean, "created_at": _utc_now()}
    with _lock:
        devices = _load()
        devices.append(device)
        _save(devices)
    return deepcopy(device)


def remove_network_device(device_id: str) -> bool:
    with _lock:
        devices = _load()
        remaining = [item for item in devices if item.get("id") != device_id]
        if len(remaining) == len(devices):
            return False
        _save(remaining)
    return True


def _iiod_host(uri: str) -> str | None:
    if uri.startswith("ip:"):
        return uri[3:].split(":")[0] or None
    return None


def probe_network_device(entry: dict[str, Any], timeout: float = 1.5) -> tuple[bool, str | None]:
    """Cheap reachability check; does not open the SDR."""
    host = _iiod_host(str(entry.get("uri") or ""))
    if host is None:
        if NETWORK_SDR_TYPES.get(str(entry.get("sdr_type")), {}).get("iiod") and not entry.get("uri"):
            host = "pluto.local"
        else:
            return True, None  # USB/serial/UHD args: checked by MMDVM-IQ at start
    try:
        with socket.create_connection((host, IIOD_PORT), timeout=timeout):
            return True, None
    except OSError as error:
        return False, f"{host}:{IIOD_PORT} unreachable ({error.__class__.__name__})"


def to_rf_device(entry: dict[str, Any], frequency_ranges_hz: list[list[int]]) -> dict[str, Any]:
    reachable, error = probe_network_device(entry)
    module_ok, module_error = soapy_module_status(entry["sdr_type"])
    if module_ok is False:
        reachable = False
        error = module_error if error is None else f"{module_error}; {error}"
    return {
        "id": entry["id"],
        "type": "sdr",
        "backend": "soapysdr_network",
        "driver": entry["sdr_type"],
        "label": entry.get("label") or entry["sdr_type"],
        "available": True,
        "probe_ok": reachable,
        "probe_error": error,
        "capabilities": {
            "connection": "mmdvm_iq",
            "hardware": NETWORK_SDR_TYPES[entry["sdr_type"]]["label"],
            "mmdvm_host_protocol": "udp",
            "mmdvm_iq_required": True,
            "soapy_type": entry["sdr_type"],
            "soapy_uri": entry.get("uri") or "",
            "rx_gain_db": entry.get("rx_gain"),
            "tx_gain_db": entry.get("tx_gain"),
            "frequency_ranges_hz": deepcopy(frequency_ranges_hz),
            "frequency_policy": "rf_gateway_mmdvm_iq_amateur_profile",
        },
    }


def render_mmdvm_iq_config(base_config: str, device: dict[str, Any]) -> str:
    """Copy of the base MMDVM-IQ.ini with the [Soapy] section for ``device``."""
    capabilities = device.get("capabilities") or {}
    soapy_lines = [
        "[Soapy]",
        f"Type={capabilities.get('soapy_type', 'sx')}",
        f"RxGain={int(capabilities.get('rx_gain_db') or 0)}",
        f"TxGain={int(capabilities.get('tx_gain_db') or 0)}",
    ]
    uri = str(capabilities.get("soapy_uri") or "").strip()
    if uri:
        soapy_lines.append(f"URI={uri}")
    section = "\n".join(soapy_lines) + "\n"

    output: list[str] = []
    skipping = False
    for line in base_config.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            skipping = stripped == "[Soapy]"
            if skipping:
                output.append(section)
                continue
        if not skipping:
            output.append(line)
    text = "\n".join(output) + "\n"
    if "[Soapy]" not in text:
        text += "\n" + section
    return text
