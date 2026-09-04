from typing import Annotated, Literal, Union

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.rf import discover_soapy_devices


API_VERSION = "0.3.0"


app = FastAPI(
    title="RF Gateway API",
    description="Backend API for RF Gateway",
    version=API_VERSION,
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


class FMStartRequest(BaseModel):
    protocol: Literal["fm"]
    frequency_hz: int = Field(gt=0)
    channel_spacing_khz: Literal[12.5, 25.0]
    deviation_khz: Literal[2.5, 5.0]
    tx_ctcss_hz: float | None = None
    rx_ctcss_hz: float | None = None
    pre_emphasis: bool


class DMRStartRequest(BaseModel):
    protocol: Literal["dmr"]
    frequency_hz: int = Field(gt=0)
    color_code: int = Field(ge=0, le=15)
    timeslot: Literal[1, 2]
    talkgroup: int = Field(ge=0)
    radio_id: int = Field(ge=0)


class P25StartRequest(BaseModel):
    protocol: Literal["p25"]
    frequency_hz: int = Field(gt=0)
    nac: str = Field(min_length=1)
    talkgroup: int = Field(ge=0)
    radio_id: int = Field(ge=0)
    modulation: Literal["c4fm", "cqpsk"]


class TETRAStartRequest(BaseModel):
    protocol: Literal["tetra"]
    frequency_hz: int = Field(gt=0)
    mode: Literal["dmo", "tmo"]
    mcc: str = Field(min_length=1)
    mnc: str = Field(min_length=1)
    color_code: int = Field(ge=0)
    gssi: int = Field(ge=0)


RFStartRequest = Annotated[
    Union[
        FMStartRequest,
        DMRStartRequest,
        P25StartRequest,
        TETRAStartRequest,
    ],
    Field(discriminator="protocol"),
]


runtime_state = {
    "tx": False,
    "protocol": None,
    "device_id": None,
    "config": None,
}


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


@app.get("/api/rf/status")
async def rf_status():
    return runtime_state


@app.post("/api/rf/start")
async def rf_start(
    request: RFStartRequest,
):
    runtime_state["tx"] = True
    runtime_state["protocol"] = request.protocol
    runtime_state["config"] = request.model_dump()

    print()
    print("=== RF START ===")
    print(f"Protocol: {request.protocol}")
    print(request.model_dump())
    print("================")
    print()

    return runtime_state


@app.post("/api/rf/stop")
async def rf_stop():
    runtime_state["tx"] = False

    print()
    print("=== RF STOP ===")
    print("================")
    print()

    return runtime_state
