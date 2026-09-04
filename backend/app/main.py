from contextlib import asynccontextmanager
from typing import Annotated, Literal, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config_store import (
    mode_config_store,
)

from app.mmdvm import (
    mmdvm_process_manager,
    validate_runtime_mode,
)

from app.mmdvm.control import (
    send_cw_command,
)

from app.rf import (
    discover_soapy_devices,
    rf_device_manager,
)


API_VERSION = "0.10.0"


ModeProtocol = Literal[
    "fm",
    "dmr",
    "p25",
    "tetra",
]


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    yield

    mmdvm_process_manager.stop()
    rf_device_manager.close_all()


app = FastAPI(
    title="RF Gateway API",
    description="Backend API for RF Gateway",
    version=API_VERSION,
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.100.20:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeviceConfigureRequest(BaseModel):
    rx_frequency_hz: float | None = Field(
        default=None,
        gt=0,
    )

    tx_frequency_hz: float | None = Field(
        default=None,
        gt=0,
    )

    rx_sample_rate: float | None = Field(
        default=None,
        gt=0,
    )

    tx_sample_rate: float | None = Field(
        default=None,
        gt=0,
    )

    rx_bandwidth_hz: float | None = Field(
        default=None,
        ge=0,
    )

    tx_bandwidth_hz: float | None = Field(
        default=None,
        ge=0,
    )

    rx_gain_db: float | None = None
    tx_gain_db: float | None = None


class FMModeSettings(BaseModel):
    protocol: Literal["fm"]

    frequency_hz: int = Field(
        gt=0,
    )

    channel_spacing_khz: Literal[
        12.5,
        25.0,
    ]

    deviation_khz: Literal[
        2.5,
        5.0,
    ]

    tx_ctcss_hz: float | None = None
    rx_ctcss_hz: float | None = None

    pre_emphasis: bool


class DMRModeSettings(BaseModel):
    protocol: Literal["dmr"]

    frequency_hz: int = Field(
        gt=0,
    )

    color_code: int = Field(
        ge=0,
        le=15,
    )

    timeslot: Literal[
        1,
        2,
    ]

    talkgroup: int = Field(
        ge=0,
    )

    radio_id: int = Field(
        gt=0,
    )


class P25ModeSettings(BaseModel):
    protocol: Literal["p25"]

    frequency_hz: int = Field(
        gt=0,
    )

    nac: str = Field(
        min_length=1,
    )

    talkgroup: int = Field(
        ge=0,
    )

    radio_id: int = Field(
        gt=0,
    )

    modulation: Literal[
        "c4fm",
        "cqpsk",
    ]


class TETRAModeSettings(BaseModel):
    protocol: Literal["tetra"]

    frequency_hz: int = Field(
        gt=0,
    )

    mode: Literal[
        "dmo",
        "tmo",
    ]

    mcc: str = Field(
        min_length=1,
    )

    mnc: str = Field(
        min_length=1,
    )

    color_code: int = Field(
        ge=0,
    )

    gssi: int = Field(
        ge=0,
    )


ModeSettingsRequest = Annotated[
    Union[
        FMModeSettings,
        DMRModeSettings,
        P25ModeSettings,
        TETRAModeSettings,
    ],
    Field(
        discriminator="protocol",
    ),
]


class FMStartRequest(FMModeSettings):
    device_id: str = Field(
        min_length=1,
    )


class DMRStartRequest(DMRModeSettings):
    device_id: str = Field(
        min_length=1,
    )


class P25StartRequest(P25ModeSettings):
    device_id: str = Field(
        min_length=1,
    )


class TETRAStartRequest(TETRAModeSettings):
    device_id: str = Field(
        min_length=1,
    )


RFStartRequest = Annotated[
    Union[
        FMStartRequest,
        DMRStartRequest,
        P25StartRequest,
        TETRAStartRequest,
    ],
    Field(
        discriminator="protocol",
    ),
]


class CWTestRequest(BaseModel):
    text: str = Field(
        default="SP5OPS",
        min_length=1,
        max_length=32,
    )


runtime_state = {
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


def device_exists(
    device_id: str,
) -> bool:
    discovery = (
        discover_soapy_devices()
    )

    for device in discovery.get(
        "devices",
        [],
    ):
        if (
            device.get("id")
            == device_id
        ):
            return bool(
                device.get(
                    "available",
                    False,
                )
                and
                device.get(
                    "probe_ok",
                    False,
                )
            )

    return False


def ensure_direct_soapy_available():
    if (
        mmdvm_process_manager
        .is_running
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "SXceiver is owned by "
                "the MMDVM runtime"
            ),
        )


def apply_mmdvm_status(
    status: dict,
) -> None:
    runtime_active = bool(
        status.get(
            "runtime_active",
            False,
        )
    )

    rf_tx_active = bool(
        status.get(
            "rf_tx_active",
            False,
        )
    )

    runtime_state[
        "runtime_active"
    ] = runtime_active

    runtime_state[
        "rf_tx_active"
    ] = rf_tx_active

    runtime_state[
        "tx_stream_active"
    ] = rf_tx_active

    runtime_state[
        "tx"
    ] = rf_tx_active

    runtime_state[
        "mmdvm"
    ] = status


@app.get("/")
async def root():
    return {
        "service": "RF Gateway API",
        "version": API_VERSION,
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "rf-gateway",
        "version": API_VERSION,
    }


@app.get("/api/config/modes")
def get_mode_configs():
    return (
        mode_config_store
        .get_all()
    )


@app.get(
    "/api/config/modes/{protocol}"
)
def get_mode_config(
    protocol: ModeProtocol,
):
    config = (
        mode_config_store
        .get_mode(protocol)
    )

    if config is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No saved configuration "
                f"for {protocol.upper()}"
            ),
        )

    return {
        "protocol": protocol,
        "config": config,
    }


@app.put("/api/config/modes")
def save_mode_config(
    request: ModeSettingsRequest,
):
    request_data = (
        request.model_dump()
    )

    protocol = (
        request.protocol
    )

    saved = (
        mode_config_store
        .save_mode(
            protocol,
            request_data,
        )
    )

    return {
        "protocol": protocol,
        "config": saved,
    }


@app.get("/api/devices")
def get_devices():
    return discover_soapy_devices()


@app.post("/api/devices/refresh")
def refresh_devices():
    return discover_soapy_devices()


@app.post(
    "/api/devices/{device_id}/open"
)
def open_device(
    device_id: str,
):
    ensure_direct_soapy_available()

    try:
        return rf_device_manager.open(
            device_id
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@app.get(
    "/api/devices/{device_id}/status"
)
def get_device_status(
    device_id: str,
):
    try:
        return (
            rf_device_manager
            .get_status(
                device_id
            )
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@app.post(
    "/api/devices/{device_id}/configure"
)
def configure_device(
    device_id: str,
    request: DeviceConfigureRequest,
):
    ensure_direct_soapy_available()

    try:
        device = (
            rf_device_manager.get(
                device_id
            )
        )

        applied = {}

        if (
            request.rx_frequency_hz
            is not None
        ):
            applied[
                "rx_frequency_hz"
            ] = (
                device.set_rx_frequency(
                    request.rx_frequency_hz
                )
            )

        if (
            request.tx_frequency_hz
            is not None
        ):
            applied[
                "tx_frequency_hz"
            ] = (
                device.set_tx_frequency(
                    request.tx_frequency_hz
                )
            )

        if (
            request.rx_sample_rate
            is not None
        ):
            applied[
                "rx_sample_rate"
            ] = (
                device.set_rx_sample_rate(
                    request.rx_sample_rate
                )
            )

        if (
            request.tx_sample_rate
            is not None
        ):
            applied[
                "tx_sample_rate"
            ] = (
                device.set_tx_sample_rate(
                    request.tx_sample_rate
                )
            )

        if (
            request.rx_bandwidth_hz
            is not None
        ):
            applied[
                "rx_bandwidth_hz"
            ] = (
                device.set_rx_bandwidth(
                    request.rx_bandwidth_hz
                )
            )

        if (
            request.tx_bandwidth_hz
            is not None
        ):
            applied[
                "tx_bandwidth_hz"
            ] = (
                device.set_tx_bandwidth(
                    request.tx_bandwidth_hz
                )
            )

        if (
            request.rx_gain_db
            is not None
        ):
            applied[
                "rx_gain_db"
            ] = (
                device.set_rx_gain(
                    request.rx_gain_db
                )
            )

        if (
            request.tx_gain_db
            is not None
        ):
            applied[
                "tx_gain_db"
            ] = (
                device.set_tx_gain(
                    request.tx_gain_db
                )
            )

        return {
            "device_id": device_id,
            "open": device.is_open,
            "applied": applied,
            "state":
                device.get_runtime_state(),
        }

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@app.post(
    "/api/devices/{device_id}/close"
)
def close_device(
    device_id: str,
):
    try:
        return (
            rf_device_manager.close(
                device_id
            )
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@app.get("/api/mmdvm/status")
def mmdvm_status():
    return (
        mmdvm_process_manager
        .status()
    )


@app.get("/api/mmdvm/logs")
def mmdvm_logs(
    lines: int = 80,
):
    return (
        mmdvm_process_manager
        .logs(lines)
    )


@app.post(
    "/api/calibration/cw-id"
)
def calibration_cw_id(
    request: CWTestRequest,
):
    status = (
        mmdvm_process_manager
        .status()
    )

    if not status.get(
        "runtime_active",
        False,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "MMDVM runtime must be "
                "active before CW test"
            ),
        )

    if not status.get(
        "runtime_ready",
        False,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "MMDVM runtime is not ready"
            ),
        )

    if status.get(
        "rf_tx_active",
        False,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "RF transmitter is already active"
            ),
        )

    try:
        result = send_cw_command(
            request.text
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    return {
        **result,

        "runtime_active":
            True,

        "protocol":
            status.get(
                "protocol"
            ),

        "frequency_hz":
            status.get(
                "channel_frequency_hz"
            ),
    }


@app.get("/api/rf/status")
async def rf_status():
    status = (
        mmdvm_process_manager
        .status()
    )

    apply_mmdvm_status(
        status
    )

    return runtime_state


@app.post("/api/rf/start")
async def rf_start(
    request: RFStartRequest,
):
    if (
        mmdvm_process_manager
        .is_running
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "RF runtime is already active"
            ),
        )

    if not device_exists(
        request.device_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"RF device "
                f"{request.device_id} "
                f"is not available"
            ),
        )

    request_data = (
        request.model_dump()
    )

    try:
        validate_runtime_mode(
            request.protocol,
            request_data,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    mode_config_store.save_mode(
        request.protocol,
        request_data,
    )

    try:
        rf_device_manager.close(
            request.device_id
        )

    except Exception:
        pass

    runtime_state[
        "protocol"
    ] = request.protocol

    runtime_state[
        "device_id"
    ] = request.device_id

    runtime_state[
        "config"
    ] = request_data

    try:
        status = (
            mmdvm_process_manager
            .start(
                request.protocol,
                request_data,
                callsign="SP5OPS",
            )
        )

    except Exception as error:
        failed_status = (
            mmdvm_process_manager
            .status()
        )

        apply_mmdvm_status(
            failed_status
        )

        runtime_state[
            "error"
        ] = str(error)

        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    apply_mmdvm_status(
        status
    )

    runtime_state[
        "error"
    ] = None

    return runtime_state


@app.post("/api/rf/stop")
async def rf_stop():
    status = (
        mmdvm_process_manager
        .stop()
    )

    apply_mmdvm_status(
        status
    )

    runtime_state[
        "protocol"
    ] = None

    runtime_state[
        "device_id"
    ] = None

    runtime_state[
        "config"
    ] = None

    runtime_state[
        "error"
    ] = None

    return runtime_state
