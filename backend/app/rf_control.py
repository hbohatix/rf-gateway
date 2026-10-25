"""Start / stop of the MMDVM RF runtime, shared by the RF API and routes.

A route encodes audio for its own protocol (P25, DMR, FM, ...), and
MMDVM-Host only listens on the network port of the mode it was started
in. Routes therefore have to run with an RF runtime in the same protocol
on the same device; :func:`ensure_rf_runtime_for_route` takes care of it.
"""

from __future__ import annotations

from threading import RLock
from typing import Any

from app.config_store import mode_config_store
from app.mmdvm import mmdvm_process_manager, validate_runtime_mode
from app.rf import get_rf_device, rf_device_manager, validate_device_frequency
from app.route_runtime import route_runtime_manager


DEFAULT_CALLSIGN = "SP5OPS"

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
    return runtime_state


def current_runtime() -> dict[str, Any]:
    """Protocol and device of the running RF runtime (or inactive)."""
    status = mmdvm_process_manager.status()
    active = bool(mmdvm_process_manager.is_running)
    return {
        "active": active,
        "protocol": (status.get("protocol") or runtime_state.get("protocol")) if active else None,
        "device_id": (status.get("device_id") or runtime_state.get("device_id")) if active else None,
    }


def running_routes(*, device_id: str | None = None, exclude: str | None = None) -> list[dict[str, Any]]:
    """Routes whose source pipelines are running (i.e. sending audio)."""
    result = []
    for state in route_runtime_manager.list_states():
        if state.get("state") != "running":
            continue
        if exclude and state.get("route_id") == exclude:
            continue
        if device_id and state.get("device_id") != device_id:
            continue
        result.append(state)
    return result


def start_rf_runtime(protocol: str, settings: dict[str, Any], device_id: str) -> dict[str, Any]:
    protocol = str(protocol).strip().lower()
    with _lock:
        if mmdvm_process_manager.is_running:
            raise RFControlError(409, "RF runtime is already active")

        conflicting = [
            state for state in running_routes(device_id=device_id)
            if str(state.get("protocol") or "").lower() != protocol
        ]
        if conflicting:
            names = ", ".join(
                f"{state.get('route_id', '')[:8]} ({str(state.get('protocol')).upper()})" for state in conflicting
            )
            raise RFControlError(
                409,
                f"Route(s) {names} are running on this device in another protocol. "
                f"Stop them first, or change their protocol to {protocol.upper()}.",
            )

        device = get_rf_device(device_id)
        if device is None or not device.get("available", False) or not device.get("probe_ok", False):
            raise RFControlError(400, f"RF device {device_id} is not available")

        request_data = {**settings, "protocol": protocol, "device_id": device_id}
        try:
            validate_runtime_mode(protocol, request_data)
            validate_device_frequency(device, int(request_data["frequency_hz"]))
        except (KeyError, TypeError, ValueError) as error:
            raise RFControlError(400, str(error)) from error

        mode_config_store.save_mode(protocol, request_data)

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
        return runtime_state


def stop_rf_runtime() -> dict[str, Any]:
    with _lock:
        apply_mmdvm_status(mmdvm_process_manager.stop())
        runtime_state["protocol"] = None
        runtime_state["device_id"] = None
        runtime_state["config"] = None
        runtime_state["error"] = None
        return runtime_state


def plan_for_route(route: dict[str, Any]) -> dict[str, Any]:
    """What starting ``route`` would do to the RF runtime (no side effects)."""
    protocol = str(route.get("protocol") or "").lower()
    device_id = route.get("device_id")
    runtime = current_runtime()
    plan: dict[str, Any] = {
        "runtime_active": runtime["active"],
        "runtime_protocol": runtime["protocol"],
        "runtime_device_id": runtime["device_id"],
        "route_protocol": protocol,
        "matches": bool(runtime["active"] and runtime["protocol"] == protocol and runtime["device_id"] == device_id),
    }
    if plan["matches"]:
        plan["action"] = "none"
        plan["message"] = None
    elif not runtime["active"]:
        plan["action"] = "start"
        plan["message"] = f"Start will turn on the RF runtime in {protocol.upper()}."
    else:
        others = running_routes(exclude=route.get("id"))
        if others:
            plan["action"] = "blocked"
            plan["message"] = (
                f"The RF runtime is running {str(runtime['protocol']).upper()} for another route. "
                f"Stop that route first; this route transmits {protocol.upper()}."
            )
        else:
            plan["action"] = "switch"
            plan["message"] = (
                f"The RF runtime is running {str(runtime['protocol']).upper()}; "
                f"Start will switch it to {protocol.upper()}."
            )
    return plan


def ensure_rf_runtime_for_route(route: dict[str, Any]) -> dict[str, Any]:
    """Make the RF runtime run the route's protocol on the route's device."""
    with _lock:
        plan = plan_for_route(route)
        action = plan["action"]
        if action == "none":
            return plan
        if action == "blocked":
            raise RFControlError(409, plan["message"])

        protocol = plan["route_protocol"]
        settings = mode_config_store.get_mode(protocol)
        if not settings:
            raise RFControlError(400, f"{protocol.upper()} settings have not been saved (RF Output page)")

        if action == "switch":
            stop_rf_runtime()

        start_rf_runtime(protocol, settings, route["device_id"])
        plan["message"] = (
            f"RF runtime switched from {str(plan['runtime_protocol']).upper()} to {protocol.upper()}"
            if action == "switch"
            else f"RF runtime started in {protocol.upper()}"
        )
        return plan
