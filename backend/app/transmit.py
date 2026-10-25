"""Simple transmit API used by the UI: pick a mode, pick a source, start/stop.

Routes are an internal detail here: one route per source is created on
first start and kept in sync with the transmit mode and RF device.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config_store import mode_config_store
from app.rf import discover_rf_devices
from app.remote_sdr.client import describe_remote_sdr_url
from app.rf_control import active_mode, describe_mode, refresh_status
from app.route_runtime import route_runtime_manager
from app.routes import (
    ON_AIR_STATES,
    RouteCreateRequest,
    TRANSMIT_LOCK,
    create_route,
    get_live_audio_status,
    get_processor_status,
    get_queue_status,
    get_worker_status,
    load_store as load_routes_store,
    save_store as save_routes_store,
    schedule_transmit_apply,
    start_route_on_air,
    stop_all_transmission,
    stop_route,
)
from app.sources import (
    SourceCreateRequest,
    create_source,
    delete_source,
    get_source_or_404,
    list_sources,
    load_store as load_sources_store,
    save_store as save_sources_store,
)


router = APIRouter(prefix="/api/transmit", tags=["transmit"])

# source_id -> message of the last failed start (shown next to the source).
_last_errors: dict[str, str] = {}


class ModeRequest(BaseModel):
    protocol: str | None = None


class DeviceRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=256)


class StartRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=128)


class AddSourceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=120)


def _usable_devices() -> list[dict[str, Any]]:
    devices = discover_rf_devices().get("devices", [])
    return [device for device in devices if device.get("available") and device.get("probe_ok")]


def _resolve_device_id() -> str:
    stored = mode_config_store.get_active_device()
    usable = _usable_devices()
    if stored and any(device.get("id") == stored for device in usable):
        return stored
    if not usable:
        raise HTTPException(status_code=400, detail="No usable RF device found (RF Devices page)")
    device_id = str(usable[0]["id"])
    mode_config_store.set_active_device(device_id)
    return device_id


def _routes() -> list[dict[str, Any]]:
    return load_routes_store().get("routes", [])


def _route_for_source(source_id: str, device_id: str, protocol: str) -> dict[str, Any]:
    routes = [route for route in _routes() if route.get("source_id") == source_id]
    for route in routes:
        if route.get("device_id") == device_id:
            return route
    if routes:
        return routes[0]
    source = get_source_or_404(source_id)
    return create_route(
        RouteCreateRequest(
            name=str(source.get("name") or "Source")[:120],
            source_id=source_id,
            device_id=device_id,
            protocol=protocol,
            enabled=True,
        )
    )


def _on_air() -> dict[str, Any] | None:
    routes = {route.get("id"): route for route in _routes()}
    for state in route_runtime_manager.list_states():
        if state.get("state") not in ON_AIR_STATES:
            continue
        route_id = state["route_id"]
        route = routes.get(route_id) or {}
        live = get_live_audio_status(route_id) or {}
        worker = get_worker_status(route_id) or {}
        processor = get_processor_status(route_id) or {}
        return {
            "route_id": route_id,
            "source_id": route.get("source_id") or state.get("source_id"),
            "protocol": state.get("protocol"),
            "state": state.get("state"),
            "started_at": state.get("started_at"),
            "error": state.get("error"),
            "live_audio": {
                key: live.get(key)
                for key in (
                    "state", "running", "error", "pcm_bytes_received", "tx_start_count",
                    "tx_end_count", "last_activity_level_dbfs", "last_pcm_at", "voice",
                )
            } if live else None,
            "calls": {
                "worker_state": worker.get("state"),
                "calls_observed": processor.get("calls_observed") or get_queue_status(route_id).get("total_enqueued"),
                "processor_state": processor.get("state"),
                "calls_sent": processor.get("calls_completed"),
                "current_call": processor.get("current_call_key"),
                "queue": get_queue_status(route_id),
            } if worker else None,
        }
    return None


@router.get("")
def transmit_state():
    protocol, settings = active_mode()
    return {
        "mode": {
            "protocol": protocol,
            "summary": describe_mode(protocol, settings),
            "configured": bool(settings),
        },
        "device_id": mode_config_store.get_active_device(),
        "rf": refresh_status(),
        "on_air": _on_air(),
        "errors": dict(_last_errors),
    }


@router.put("/mode")
def set_mode(request: ModeRequest):
    protocol = mode_config_store.set_active_protocol(request.protocol)
    schedule_transmit_apply(delay=0.2)
    return {"protocol": protocol}


@router.put("/device")
def set_device(request: DeviceRequest):
    mode_config_store.set_active_device(request.device_id)
    return {"device_id": request.device_id}


@router.post("/start")
def start(request: StartRequest):
    get_source_or_404(request.source_id)
    protocol, _ = active_mode()
    if not protocol:
        raise HTTPException(status_code=400, detail="Choose a transmit mode first")
    with TRANSMIT_LOCK:
        device_id = _resolve_device_id()
        route = _route_for_source(request.source_id, device_id, protocol)
        result = start_route_on_air(route["id"], device_id=device_id)
    if result.get("started"):
        _last_errors.pop(request.source_id, None)
    else:
        _last_errors[request.source_id] = str(result.get("message") or "Start failed")
    return {"started": bool(result.get("started")), "message": result.get("message")}


@router.post("/stop")
def stop():
    return stop_all_transmission()


GENERIC_SOURCE_NAMES = {"broadcastify calls", "broadcastify live audio", "direct audio", "new source", "remote sdr", ""}


@router.get("/sources")
def sources():
    """Saved sources; a generic name falls back to the name of a route using it."""
    data = list_sources()
    route_names = {route.get("source_id"): route.get("name") for route in _routes() if route.get("name")}
    for source in data["sources"]:
        if str(source.get("name") or "").strip().lower() in GENERIC_SOURCE_NAMES and source["id"] in route_names:
            source["name"] = route_names[source["id"]]
    return data


@router.post("/sources")
def add_source(request: AddSourceRequest):
    name = (request.name or "").strip()
    try:
        source = create_source(SourceCreateRequest(name=name or "New source", type="auto", url=request.url.strip()))
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if not name:
        probe = source.get("probe") or {}
        detected = probe.get("page_name")
        if not detected and source.get("type") == "remote_sdr":
            detected = describe_remote_sdr_url(source["url"])
        if detected:
            store = load_sources_store()
            for item in store.get("sources", []):
                if item.get("id") == source["id"]:
                    item["name"] = str(detected)[:120]
                    source = {**source, "name": item["name"]}
            save_sources_store(store)
    return source


@router.delete("/sources/{source_id}")
def remove_source(source_id: str):
    get_source_or_404(source_id)
    with TRANSMIT_LOCK:
        store = load_routes_store()
        route_ids = [route["id"] for route in store.get("routes", []) if route.get("source_id") == source_id]
        for route_id in route_ids:
            stop_route(route_id)
            route_runtime_manager.remove(route_id)
        store["routes"] = [route for route in store.get("routes", []) if route.get("id") not in route_ids]
        save_routes_store(store)
    _last_errors.pop(source_id, None)
    delete_source(source_id)
    return {"deleted": True, "source_id": source_id}
