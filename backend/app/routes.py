from __future__ import annotations

import uuid

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

import yaml

from fastapi import (
    APIRouter,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from app.broadcastify_worker import (
    broadcastify_worker_manager,
)

from app.call_processor import (
    call_processor_manager,
)

from app.call_queue import (
    call_queue_manager,
)

from app.config_store import (
    mode_config_store,
)

from app.rf import (
    discover_soapy_devices,
)

from app.route_runtime import (
    route_runtime_manager,
)

from app.sources import (
    get_source_or_404,
)


router = APIRouter(
    prefix="/api/routes",
    tags=["routes"],
)


Protocol = Literal[
    "fm",
    "dmr",
    "p25",
    "tetra",
]


BACKEND_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

DATA_DIR = (
    BACKEND_DIR
    / "data"
)

ROUTES_FILE = (
    DATA_DIR
    / "routes.yaml"
)


DEFAULT_STORE = {
    "version": 1,
    "routes": [],
}


_store_lock = RLock()


class RouteCreateRequest(
    BaseModel
):
    name: str = Field(
        min_length=1,
        max_length=120,
    )

    source_id: str = Field(
        min_length=1,
        max_length=128,
    )

    device_id: str = Field(
        min_length=1,
        max_length=256,
    )

    protocol: Protocol

    enabled: bool = True


class RouteUpdateRequest(
    BaseModel
):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )

    source_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )

    device_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
    )

    protocol: Protocol | None = None

    enabled: bool | None = None


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def ensure_storage() -> None:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if ROUTES_FILE.exists():
        return

    save_store(
        deepcopy(
            DEFAULT_STORE
        )
    )


def load_store() -> dict:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not ROUTES_FILE.exists():
        return deepcopy(
            DEFAULT_STORE
        )

    with _store_lock:
        try:
            with ROUTES_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = (
                    yaml.safe_load(
                        file
                    )
                    or {}
                )

        except Exception as error:
            raise RuntimeError(
                (
                    "Unable to read "
                    "routes store: "
                    f"{error}"
                )
            ) from error

    if not isinstance(
        loaded,
        dict,
    ):
        return deepcopy(
            DEFAULT_STORE
        )

    loaded.setdefault(
        "version",
        1,
    )

    loaded.setdefault(
        "routes",
        [],
    )

    if not isinstance(
        loaded[
            "routes"
        ],
        list,
    ):
        loaded[
            "routes"
        ] = []

    return loaded


def save_store(
    store: dict,
) -> None:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = (
        ROUTES_FILE.with_suffix(
            ".yaml.tmp"
        )
    )

    with _store_lock:
        try:
            with temporary_file.open(
                "w",
                encoding="utf-8",
            ) as file:
                yaml.safe_dump(
                    store,
                    file,
                    sort_keys=False,
                    allow_unicode=True,
                )

            temporary_file.replace(
                ROUTES_FILE
            )

        except Exception as error:
            raise RuntimeError(
                (
                    "Unable to save "
                    "routes store: "
                    f"{error}"
                )
            ) from error


def normalize_name(
    name: str,
) -> str:
    normalized = (
        " ".join(
            name.split()
        )
        .strip()
    )

    if not normalized:
        raise HTTPException(
            status_code=400,
            detail=(
                "Route name "
                "cannot be empty"
            ),
        )

    return normalized


def get_route_or_404(
    route_id: str,
) -> dict:
    store = load_store()

    for route in store.get(
        "routes",
        [],
    ):
        if (
            route.get(
                "id"
            )
            == route_id
        ):
            return deepcopy(
                route
            )

    raise HTTPException(
        status_code=404,
        detail="Route not found",
    )


def validate_source(
    source_id: str,
) -> None:
    get_source_or_404(
        source_id
    )


def get_device_or_404(
    device_id: str,
) -> dict:
    try:
        discovery = (
            discover_soapy_devices()
        )

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "RF device discovery "
                f"failed: {error}"
            ),
        ) from error

    devices = (
        discovery.get(
            "devices",
            [],
        )
        if isinstance(
            discovery,
            dict,
        )
        else []
    )

    for device in devices:
        if (
            device.get(
                "id"
            )
            == device_id
        ):
            return deepcopy(
                device
            )

    raise HTTPException(
        status_code=404,
        detail=(
            "RF device not found: "
            f"{device_id}"
        ),
    )


def get_protocol_config(
    protocol: str,
) -> dict | None:
    try:
        config = (
            mode_config_store
            .get_mode(
                protocol
            )
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to load "
                "protocol configuration: "
                f"{error}"
            ),
        ) from error

    if config is None:
        return None

    return deepcopy(
        config
    )


def run_preflight(
    route: dict,
) -> dict:
    source = (
        get_source_or_404(
            route[
                "source_id"
            ]
        )
    )

    device = (
        get_device_or_404(
            route[
                "device_id"
            ]
        )
    )

    mode_config = (
        get_protocol_config(
            route[
                "protocol"
            ]
        )
    )

    return (
        route_runtime_manager
        .preflight(
            route=route,
            source=source,
            device=device,
            mode_config=mode_config,
        )
    )


def get_worker_status(
    route_id: str,
) -> dict | None:
    worker = (
        broadcastify_worker_manager
        .get(
            route_id
        )
    )

    if worker is None:
        return None

    return worker.status()


def get_processor_status(
    route_id: str,
) -> dict | None:
    return (
        call_processor_manager
        .status(
            route_id
        )
    )


def get_queue_status(
    route_id: str,
) -> dict:
    queue = (
        call_queue_manager
        .get_queue(
            route_id
        )
    )

    return queue.stats()


def start_source_pipeline(
    route: dict,
    source: dict,
) -> tuple[
    dict,
    dict,
]:
    route_id = str(
        route[
            "id"
        ]
    )

    protocol = str(
        route[
            "protocol"
        ]
    )

    worker = (
        broadcastify_worker_manager
        .create_or_get(
            route_id=route_id,
            source=source,
        )
    )

    worker_status = (
        worker.start()
    )

    try:
        processor_status = (
            call_processor_manager
            .start(
                route_id,
                protocol,
            )
        )

    except Exception as error:
        broadcastify_worker_manager.stop(
            route_id
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to start "
                "call processor: "
                f"{error}"
            ),
        ) from error

    return (
        worker_status,
        processor_status,
    )


def stop_source_pipeline(
    route_id: str,
    *,
    clear_queue: bool,
) -> dict:
    processor_status = (
        call_processor_manager
        .stop(
            route_id
        )
    )

    worker_status = (
        broadcastify_worker_manager
        .stop(
            route_id
        )
    )

    queue = (
        call_queue_manager
        .get_queue(
            route_id
        )
    )

    queue_clear = None

    if clear_queue:
        queue_clear = (
            queue.clear(
                clear_seen=False
            )
        )

    return {
        "worker":
            worker_status,

        "processor":
            processor_status,

        "queue_clear":
            queue_clear,

        "queue":
            queue.stats(),
    }


#
# Static endpoints first.
#
# Otherwise "/runtime", "/workers"
# or "/processors" could be
# interpreted as a route_id.
#


@router.get(
    "/runtime"
)
def list_route_runtime():
    states = (
        route_runtime_manager
        .list_states()
    )

    active_count = sum(
        1
        for state in states
        if state.get(
            "active",
            False,
        )
    )

    ready_count = sum(
        1
        for state in states
        if state.get(
            "runtime_ready",
            False,
        )
    )

    blocked_count = sum(
        1
        for state in states
        if state.get(
            "state"
        )
        == "blocked"
    )

    return {
        "count":
            len(
                states
            ),

        "active_count":
            active_count,

        "ready_count":
            ready_count,

        "blocked_count":
            blocked_count,

        "routes":
            states,
    }


@router.get(
    "/workers"
)
def list_route_workers():
    workers = (
        broadcastify_worker_manager
        .list_status()
    )

    running_count = sum(
        1
        for worker in workers
        if worker.get(
            "running",
            False,
        )
    )

    return {
        "count":
            len(
                workers
            ),

        "running_count":
            running_count,

        "workers":
            workers,
    }


@router.get(
    "/processors"
)
def list_route_processors():
    processors = (
        call_processor_manager
        .list_status()
    )

    running_count = sum(
        1
        for processor in processors
        if processor.get(
            "running",
            False,
        )
    )

    return {
        "count":
            len(
                processors
            ),

        "running_count":
            running_count,

        "processors":
            processors,
    }


@router.get("")
def list_routes():
    store = load_store()

    routes = (
        store.get(
            "routes",
            [],
        )
    )

    enabled_count = sum(
        1
        for route in routes
        if route.get(
            "enabled",
            False,
        )
    )

    return {
        "version":
            store.get(
                "version",
                1,
            ),

        "count":
            len(
                routes
            ),

        "enabled_count":
            enabled_count,

        "routes":
            routes,
    }


@router.post("")
def create_route(
    request: RouteCreateRequest,
):
    validate_source(
        request.source_id
    )

    now = utc_now()

    route = {
        "id":
            str(
                uuid.uuid4()
            ),

        "name":
            normalize_name(
                request.name
            ),

        "source_id":
            request.source_id,

        "device_id":
            request.device_id,

        "protocol":
            request.protocol,

        "enabled":
            request.enabled,

        "created_at":
            now,

        "updated_at":
            now,
    }

    store = load_store()

    store.setdefault(
        "routes",
        [],
    ).append(
        route
    )

    save_store(
        store
    )

    return route


@router.get(
    "/{route_id}"
)
def get_route(
    route_id: str,
):
    route = get_route_or_404(
        route_id
    )

    return {
        **route,

        "runtime":
            route_runtime_manager
            .get(
                route_id
            ),

        "worker":
            get_worker_status(
                route_id
            ),

        "processor":
            get_processor_status(
                route_id
            ),

        "queue":
            get_queue_status(
                route_id
            ),
    }


@router.get(
    "/{route_id}/runtime"
)
def get_route_runtime(
    route_id: str,
):
    get_route_or_404(
        route_id
    )

    return {
        "runtime":
            route_runtime_manager
            .get(
                route_id
            ),

        "worker":
            get_worker_status(
                route_id
            ),

        "processor":
            get_processor_status(
                route_id
            ),

        "queue":
            get_queue_status(
                route_id
            ),
    }


@router.get(
    "/{route_id}/worker"
)
def get_route_worker(
    route_id: str,
):
    get_route_or_404(
        route_id
    )

    worker = (
        get_worker_status(
            route_id
        )
    )

    return {
        "exists":
            worker is not None,

        "worker":
            worker,

        "processor":
            get_processor_status(
                route_id
            ),

        "queue":
            get_queue_status(
                route_id
            ),
    }


@router.get(
    "/{route_id}/processor"
)
def get_route_processor(
    route_id: str,
):
    get_route_or_404(
        route_id
    )

    processor = (
        get_processor_status(
            route_id
        )
    )

    return {
        "exists":
            processor is not None,

        "processor":
            processor,

        "queue":
            get_queue_status(
                route_id
            ),
    }


@router.get(
    "/{route_id}/queue"
)
def get_route_queue(
    route_id: str,
):
    get_route_or_404(
        route_id
    )

    queue = (
        call_queue_manager
        .get_queue(
            route_id
        )
    )

    return {
        "stats":
            queue.stats(),

        "pending":
            queue.list_pending(),
    }


@router.post(
    "/{route_id}/preflight"
)
def preflight_route(
    route_id: str,
):
    route = get_route_or_404(
        route_id
    )

    runtime = run_preflight(
        route
    )

    return {
        "route":
            route,

        "runtime":
            runtime,

        "worker":
            get_worker_status(
                route_id
            ),

        "processor":
            get_processor_status(
                route_id
            ),

        "queue":
            get_queue_status(
                route_id
            ),
    }


@router.post(
    "/{route_id}/worker/start"
)
def start_route_worker(
    route_id: str,
):
    route = get_route_or_404(
        route_id
    )

    if not route.get(
        "enabled",
        False,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Route is disabled"
            ),
        )

    source = (
        get_source_or_404(
            route[
                "source_id"
            ]
        )
    )

    if (
        source.get(
            "type"
        )
        != "broadcastify_calls"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Route source is not "
                "a Broadcastify Calls source"
            ),
        )

    (
        worker_status,
        processor_status,
    ) = start_source_pipeline(
        route,
        source,
    )

    return {
        "worker_started":
            bool(
                worker_status.get(
                    "running",
                    False,
                )
            ),

        "processor_started":
            bool(
                processor_status.get(
                    "running",
                    False,
                )
            ),

        "route":
            route,

        "worker":
            worker_status,

        "processor":
            processor_status,

        "queue":
            get_queue_status(
                route_id
            ),
    }


@router.post(
    "/{route_id}/worker/stop"
)
def stop_route_worker(
    route_id: str,
):
    get_route_or_404(
        route_id
    )

    result = (
        stop_source_pipeline(
            route_id,
            clear_queue=True,
        )
    )

    processor = (
        result[
            "processor"
        ]
    )

    return {
        "worker_stopped":
            True,

        "processor_stopped":
            (
                processor is None
                or
                not processor.get(
                    "running",
                    False,
                )
            ),

        "worker":
            result[
                "worker"
            ],

        "processor":
            processor,

        "queue_clear":
            result[
                "queue_clear"
            ],

        "queue":
            result[
                "queue"
            ],
    }


@router.post(
    "/{route_id}/start"
)
def start_route(
    route_id: str,
):
    route = get_route_or_404(
        route_id
    )

    runtime = run_preflight(
        route
    )

    if (
        runtime.get(
            "state"
        )
        != "ready"
    ):
        return {
            "started":
                False,

            "worker_started":
                False,

            "processor_started":
                False,

            "route":
                route,

            "runtime":
                runtime,

            "worker":
                get_worker_status(
                    route_id
                ),

            "processor":
                get_processor_status(
                    route_id
                ),

            "queue":
                get_queue_status(
                    route_id
                ),

            "message":
                (
                    "Route runtime "
                    "preflight failed"
                ),
        }

    source = (
        get_source_or_404(
            route[
                "source_id"
            ]
        )
    )

    (
        worker_status,
        processor_status,
    ) = start_source_pipeline(
        route,
        source,
    )

    #
    # IMPORTANT:
    #
    # Source worker and CallProcessor
    # may now both be running.
    #
    # We intentionally DO NOT call:
    #
    # route_runtime_manager.mark_running()
    #
    # yet.
    #
    # CallProcessor currently only:
    #
    # queue.peek()
    # -> inspect call
    # -> inspect audio bridge
    #
    # The following stages are still
    # not connected:
    #
    # queued call
    # -> Broadcastify audio download
    # -> audio decode
    # -> vocoder / protocol framing
    # -> MMDVM / RF hand-off
    #
    # Therefore the Route itself is
    # not yet considered actively
    # transmitting.
    #

    return {
        "started":
            False,

        "worker_started":
            bool(
                worker_status.get(
                    "running",
                    False,
                )
            ),

        "processor_started":
            bool(
                processor_status.get(
                    "running",
                    False,
                )
            ),

        "route":
            route,

        "runtime":
            runtime,

        "worker":
            worker_status,

        "processor":
            processor_status,

        "queue":
            get_queue_status(
                route_id
            ),

        "message":
            (
                "Source worker and "
                "call processor started. "
                "Audio-to-RF processing "
                "is not connected yet."
            ),
    }


@router.post(
    "/{route_id}/stop"
)
def stop_route(
    route_id: str,
):
    route = get_route_or_404(
        route_id
    )

    result = (
        stop_source_pipeline(
            route_id,
            clear_queue=True,
        )
    )

    runtime = (
        route_runtime_manager
        .stop(
            route_id
        )
    )

    return {
        "stopped":
            True,

        "route":
            route,

        "runtime":
            runtime,

        "worker":
            result[
                "worker"
            ],

        "processor":
            result[
                "processor"
            ],

        "queue":
            {
                "clear":
                    result[
                        "queue_clear"
                    ],

                "stats":
                    result[
                        "queue"
                    ],
            },
    }


@router.put(
    "/{route_id}"
)
def update_route(
    route_id: str,
    request: RouteUpdateRequest,
):
    store = load_store()

    routes = (
        store.get(
            "routes",
            [],
        )
    )

    route = None

    for item in routes:
        if (
            item.get(
                "id"
            )
            == route_id
        ):
            route = item

            break

    if route is None:
        raise HTTPException(
            status_code=404,
            detail="Route not found",
        )

    fields_set = (
        request.model_fields_set
    )

    runtime_relevant_change = False

    if (
        "name"
        in fields_set
    ):
        if request.name is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Route name "
                    "cannot be null"
                ),
            )

        route[
            "name"
        ] = normalize_name(
            request.name
        )

    if (
        "source_id"
        in fields_set
    ):
        if request.source_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "source_id "
                    "cannot be null"
                ),
            )

        validate_source(
            request.source_id
        )

        if (
            route.get(
                "source_id"
            )
            != request.source_id
        ):
            runtime_relevant_change = True

        route[
            "source_id"
        ] = request.source_id

    if (
        "device_id"
        in fields_set
    ):
        if request.device_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "device_id "
                    "cannot be null"
                ),
            )

        if (
            route.get(
                "device_id"
            )
            != request.device_id
        ):
            runtime_relevant_change = True

        route[
            "device_id"
        ] = request.device_id

    if (
        "protocol"
        in fields_set
    ):
        if request.protocol is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "protocol "
                    "cannot be null"
                ),
            )

        if (
            route.get(
                "protocol"
            )
            != request.protocol
        ):
            runtime_relevant_change = True

        route[
            "protocol"
        ] = request.protocol

    if (
        "enabled"
        in fields_set
    ):
        if request.enabled is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "enabled "
                    "cannot be null"
                ),
            )

        if (
            route.get(
                "enabled"
            )
            != request.enabled
        ):
            runtime_relevant_change = True

        route[
            "enabled"
        ] = request.enabled

    route[
        "updated_at"
    ] = utc_now()

    save_store(
        store
    )

    if runtime_relevant_change:
        broadcastify_worker_manager.remove(
            route_id
        )

        call_processor_manager.remove(
            route_id
        )

        call_queue_manager.remove_queue(
            route_id
        )

        route_runtime_manager.stop(
            route_id
        )

    return {
        **deepcopy(
            route
        ),

        "runtime":
            route_runtime_manager
            .get(
                route_id
            ),

        "worker":
            get_worker_status(
                route_id
            ),

        "processor":
            get_processor_status(
                route_id
            ),

        "queue":
            get_queue_status(
                route_id
            ),
    }


@router.delete(
    "/{route_id}"
)
def delete_route(
    route_id: str,
):
    store = load_store()

    routes = (
        store.get(
            "routes",
            [],
        )
    )

    remaining = [
        route
        for route in routes
        if route.get(
            "id"
        )
        != route_id
    ]

    if (
        len(
            remaining
        )
        ==
        len(
            routes
        )
    ):
        raise HTTPException(
            status_code=404,
            detail="Route not found",
        )

    store[
        "routes"
    ] = remaining

    save_store(
        store
    )

    broadcastify_worker_manager.remove(
        route_id
    )

    call_processor_manager.remove(
        route_id
    )

    call_queue_manager.remove_queue(
        route_id
    )

    route_runtime_manager.remove(
        route_id
    )

    return {
        "deleted":
            True,

        "id":
            route_id,
    }