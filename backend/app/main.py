from contextlib import asynccontextmanager
from typing import Annotated, Literal, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.rf import (
    discover_soapy_devices,
    rf_device_manager,
)


API_VERSION = "0.5.0"


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    yield

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


class FMStartRequest(BaseModel):
    protocol: Literal["fm"]

    device_id: str = Field(
        min_length=1,
    )

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


class DMRStartRequest(BaseModel):
    protocol: Literal["dmr"]

    device_id: str = Field(
        min_length=1,
    )

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
        ge=0,
    )


class P25StartRequest(BaseModel):
    protocol: Literal["p25"]

    device_id: str = Field(
        min_length=1,
    )

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
        ge=0,
    )

    modulation: Literal[
        "c4fm",
        "cqpsk",
    ]


class TETRAStartRequest(BaseModel):
    protocol: Literal["tetra"]

    device_id: str = Field(
        min_length=1,
    )

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


runtime_state = {
    "tx": False,
    "protocol": None,
    "device_id": None,
    "config": None,
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
            "device_id":
                device_id,

            "open":
                device.is_open,

            "applied":
                applied,

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


@app.get("/api/rf/status")
async def rf_status():
    return runtime_state


@app.post("/api/rf/start")
async def rf_start(
    request: RFStartRequest,
):
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


    runtime_state["tx"] = True

    runtime_state["protocol"] = (
        request.protocol
    )

    runtime_state["device_id"] = (
        request.device_id
    )

    runtime_state["config"] = (
        request.model_dump()
    )


    print()
    print("=== RF START ===")

    print(
        f"Device: "
        f"{request.device_id}"
    )

    print(
        f"Protocol: "
        f"{request.protocol}"
    )

    print(
        request.model_dump()
    )

    print("================")
    print()


    return runtime_state


@app.post("/api/rf/stop")
async def rf_stop():
    runtime_state["tx"] = False


    print()
    print("=== RF STOP ===")

    print(
        f"Device: "
        f"{runtime_state['device_id']}"
    )

    print(
        f"Protocol: "
        f"{runtime_state['protocol']}"
    )

    print("================")
    print()


    return runtime_state
