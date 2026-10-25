from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Annotated, Literal, Union


def load_local_environment() -> None:
    env_file = (
        Path(__file__)
        .resolve()
        .parent
        .parent
        / ".env"
    )

    if not env_file.is_file():
        return

    for raw_line in env_file.read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
        ):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        key, separator, value = (
            line.partition("=")
        )

        if not separator:
            continue

        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ("'", '"')
        ):
            value = value[1:-1]

        os.environ[key] = value


load_local_environment()


from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.broadcastify_worker import (
    broadcastify_worker_manager,
)

from app.call_processor import (
    call_processor_manager,
)

from app.rf_control import (
    RFControlError,
    ensure_runtime,
    refresh_status,
    runtime_state,
)

from app.audio_bridge import (
    get_all_audio_bridge_capabilities,
)

from app.rf.network_devices import (
    NETWORK_SDR_TYPES,
    add_network_device,
    list_network_devices,
    remove_network_device,
)

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
    discover_rf_devices,
    get_rf_device,
    rf_device_manager,
    validate_device_frequency,
)

from app.sources import (
    router as sources_router,
)

from app.routes import (
    apply_transmit_mode,
    router as routes_router,
    schedule_transmit_apply,
    stop_all_transmission,
)

from app.transmit import (
    router as transmit_router,
)


API_VERSION = "0.13.0"


ModeProtocol = Literal[
    "fm",
    "dmr",
    "p25",
    "ysf",
    "dstar",
    "nxdn",
    "tetra",
]


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    yield

    broadcastify_worker_manager.stop_all()
    call_processor_manager.stop_all()

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


app.include_router(
    sources_router
)

app.include_router(
    routes_router
)

app.include_router(
    transmit_router
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

    # Linear gain applied to source audio before it reaches MMDVM-Host.
    audio_gain: float = Field(
        default=1.0,
        gt=0,
        le=8,
    )


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

    call_type: Literal[
        "group",
        "private",
    ] = "group"

    # AMBE+2 vocoder: OP25 software encoder or a DVSI AMBE-3000 chip.
    vocoder: Literal[
        "software",
        "dv3000_serial",
        "ambeserver",
    ] = "software"

    vocoder_device: str | None = None

    vocoder_baud: int | None = Field(
        default=None,
        gt=0,
    )

    vocoder_host: str | None = None

    vocoder_port: int | None = Field(
        default=None,
        gt=0,
        lt=65536,
    )

    vocoder_gain_db: float = Field(
        default=0.0,
        ge=-20,
        le=20,
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


class YSFModeSettings(BaseModel):
    protocol: Literal["ysf"]

    frequency_hz: int = Field(
        gt=0,
    )

    # Source callsign shown on Fusion radios (1-10 characters).
    callsign: str = Field(
        min_length=1,
        max_length=10,
    )

    destination: str = Field(
        default="ALL",
        max_length=10,
    )

    dg_id: int = Field(
        default=0,
        ge=0,
        le=99,
    )

    low_deviation: bool = False

    vocoder: Literal[
        "software",
        "dv3000_serial",
        "ambeserver",
    ] = "software"

    vocoder_device: str | None = None

    vocoder_baud: int | None = Field(
        default=None,
        gt=0,
    )

    vocoder_host: str | None = None

    vocoder_port: int | None = Field(
        default=None,
        gt=0,
        lt=65536,
    )

    vocoder_gain_db: float = Field(
        default=0.0,
        ge=-20,
        le=20,
    )


class DStarModeSettings(BaseModel):
    protocol: Literal["dstar"]

    frequency_hz: int = Field(
        gt=0,
    )

    # Station callsign (MY), also used as the MMDVM-Host callsign.
    callsign: str = Field(
        min_length=3,
        max_length=8,
    )

    suffix: str = Field(
        default="RFGW",
        max_length=4,
    )

    your_call: str = Field(
        default="CQCQCQ",
        max_length=8,
    )

    module: str = Field(
        default="B",
        min_length=1,
        max_length=1,
    )

    message: str = Field(
        default="RF Gateway",
        max_length=20,
    )

    vocoder_gain_db: float = Field(
        default=0.0,
        ge=-20,
        le=20,
    )


class NXDNModeSettings(BaseModel):
    protocol: Literal["nxdn"]

    frequency_hz: int = Field(
        gt=0,
    )

    ran: int = Field(
        default=1,
        ge=0,
        le=63,
    )

    talkgroup: int = Field(
        ge=0,
        le=65535,
    )

    radio_id: int = Field(
        gt=0,
        le=65519,
    )

    call_type: Literal[
        "group",
        "private",
    ] = "group"

    vocoder: Literal[
        "software",
        "dv3000_serial",
        "ambeserver",
    ] = "software"

    vocoder_device: str | None = None

    vocoder_baud: int | None = Field(
        default=None,
        gt=0,
    )

    vocoder_host: str | None = None

    vocoder_port: int | None = Field(
        default=None,
        gt=0,
        lt=65536,
    )

    vocoder_gain_db: float = Field(
        default=0.0,
        ge=-20,
        le=20,
    )


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
        YSFModeSettings,
        DStarModeSettings,
        NXDNModeSettings,
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


class YSFStartRequest(YSFModeSettings):
    device_id: str = Field(
        min_length=1,
    )


class DStarStartRequest(DStarModeSettings):
    device_id: str = Field(
        min_length=1,
    )


class NXDNStartRequest(NXDNModeSettings):
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
        YSFStartRequest,
        DStarStartRequest,
        NXDNStartRequest,
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


def device_exists(
    device_id: str,
) -> bool:
    discovery = (
        discover_rf_devices()
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
                "RF hardware is owned by "
                "the MMDVM runtime"
            ),
        )


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

    # Editing the transmit mode applies it to whatever is on air.
    if protocol == mode_config_store.get_active_protocol():
        schedule_transmit_apply()

    return {
        "protocol": protocol,
        "config": saved,
    }


@app.get("/api/voice/capabilities")
def get_voice_capabilities():
    """Which protocols can carry source audio right now, and why not."""
    return get_all_audio_bridge_capabilities()


class NetworkSDRRequest(BaseModel):
    sdr_type: Literal[
        "plutosdr",
        "libresdr",
        "limesdr",
        "limemini",
        "usrp",
    ]

    uri: str = Field(
        default="",
        max_length=200,
    )

    label: str | None = Field(
        default=None,
        max_length=60,
    )

    rx_gain: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    tx_gain: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )


@app.get("/api/devices/network")
def get_network_sdr_devices():
    """Registered network SDR transmitters (PlutoSDR, LibreSDR, Lime, USRP)."""
    return {
        "types": NETWORK_SDR_TYPES,
        "devices": list_network_devices(),
    }


@app.post("/api/devices/network")
def add_network_sdr_device(request: NetworkSDRRequest):
    payload = {
        key: value
        for key, value in request.model_dump().items()
        if value is not None
    }
    try:
        return add_network_device(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/devices/network/{device_id}")
def delete_network_sdr_device(device_id: str):
    if runtime_state.get("device_id") == device_id and mmdvm_process_manager.is_running:
        raise HTTPException(status_code=409, detail="Stop the RF runtime before removing its device")
    if not remove_network_device(device_id):
        raise HTTPException(status_code=404, detail="Network SDR not found")
    return {"deleted": True, "id": device_id}


@app.get("/api/devices")
def get_devices():
    return discover_rf_devices()


@app.post("/api/devices/refresh")
def refresh_devices():
    return discover_rf_devices()


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
    return refresh_status()


@app.post("/api/rf/start")
def rf_start(
    request: RFStartRequest,
):
    """Select ``protocol`` as the transmit mode and run the transmitter in it.

    Anything already on air follows the new mode.
    """
    request_data = request.model_dump()
    device_id = request_data.pop("device_id")
    protocol = request.protocol
    mode_config_store.save_mode(protocol, request_data)
    mode_config_store.set_active_protocol(protocol)
    mode_config_store.set_active_device(device_id)
    try:
        if apply_transmit_mode().get("action") == "none":
            ensure_runtime(protocol, mode_config_store.get_mode(protocol) or {}, device_id)
    except RFControlError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=str(error),
        ) from error
    return refresh_status()


@app.post("/api/rf/stop")
def rf_stop():
    """Turn everything off: every route and the transmitter."""
    stop_all_transmission()
    return refresh_status()
