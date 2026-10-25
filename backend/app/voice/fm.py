"""Analog FM transmit session (PCM -> MMDVM-Host FM network).

MMDVM-Host's [FM Network] accepts ``FMD`` datagrams carrying 8 kHz S16LE
samples and plays them out as external audio through the modem's FM mode
(pre-emphasis, CTCSS and deviation are applied by MMDVM-Host/modem).
"""

from __future__ import annotations

import time
from copy import deepcopy
from threading import RLock
from typing import Any

from app.config_store import mode_config_store
from app.voice.base import (
    FRAME_SECONDS,
    Pacer,
    PcmFramer,
    UdpEndpoint,
    VoiceSessionConfigurationError,
    VoiceSessionError,
    validate_pcm,
)


FM_GATEWAY_ADDRESS = "127.0.0.1"
FM_GATEWAY_PORT = 4810  # RF Gateway side ([FM Network] GatewayPort)
FM_MMDVM_ADDRESS = "127.0.0.1"
FM_MMDVM_PORT = 3810  # MMDVM-Host side ([FM Network] LocalPort)

# Lead-out silence so the modem's external-audio hang does not clip the tail.
FM_TAIL_SILENCE_FRAMES = 10


def build_fm_data_packet(pcm_frame: bytes) -> bytes:
    return b"FMD" + pcm_frame


def build_fm_start_packet(callsign: str) -> bytes:
    return b"FMS" + callsign.encode("ascii", "replace")[:16] + b"\x00"


FM_END_PACKET = b"FME"


class FMStreamingSession:
    protocol = "fm"

    def __init__(
        self,
        *,
        local_address: str = FM_GATEWAY_ADDRESS,
        local_port: int = FM_GATEWAY_PORT,
        mmdvm_address: str = FM_MMDVM_ADDRESS,
        mmdvm_port: int = FM_MMDVM_PORT,
        mode_config: dict[str, Any] | None = None,
        callsign: str = "RFGW",
        pace: bool = True,
    ) -> None:
        self._endpoint = UdpEndpoint(local_address, int(local_port), mmdvm_address, int(mmdvm_port))
        self._supplied_mode_config = deepcopy(mode_config) if mode_config is not None else None
        self._callsign = callsign
        self._pacer = Pacer(FRAME_SECONDS) if pace else None
        self._lock = RLock()
        self._framer = PcmFramer()
        self._active = False
        self._gain = 1.0
        self._started_at: float | None = None
        self._ended_at: float | None = None
        self._last_error: str | None = None
        self._counters = {
            "transmissions": 0,
            "pcm_frames_received": 0,
            "pcm_bytes_received": 0,
            "audio_frames_sent": 0,
            "network_packets_sent": 0,
        }

    @property
    def active(self) -> bool:
        return self._active

    def _load_settings(self) -> dict[str, Any]:
        config = self._supplied_mode_config
        if config is None:
            config = mode_config_store.get_mode("fm")
        if not config:
            raise VoiceSessionConfigurationError("FM mode settings have not been saved")
        return dict(config)

    def _apply_gain(self, frame: bytes) -> bytes:
        if self._gain == 1.0:
            return frame
        import array

        samples = array.array("h")
        samples.frombytes(frame)
        for index, value in enumerate(samples):
            scaled = int(value * self._gain)
            samples[index] = max(-32768, min(32767, scaled))
        return samples.tobytes()

    def _send(self, packet: bytes, *, paced: bool) -> None:
        if paced and self._pacer is not None:
            self._pacer.wait()
        self._endpoint.send(packet)
        self._endpoint.drain()
        self._counters["network_packets_sent"] += 1

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._active:
                return self.status()
            settings = self._load_settings()
            try:
                self._gain = float(settings.get("audio_gain", 1.0) or 1.0)
            except (TypeError, ValueError) as error:
                raise VoiceSessionConfigurationError("FM audio gain must be a number") from error
            self._endpoint.open()
            self._framer.clear()
            if self._pacer is not None:
                self._pacer.reset()
            self._active = True
            self._started_at = time.time()
            self._ended_at = None
            self._last_error = None
            self._counters["transmissions"] += 1
            self._send(build_fm_start_packet(self._callsign), paced=False)
            return self.status()

    def feed_pcm(self, pcm: bytes) -> dict[str, Any]:
        data = validate_pcm(pcm)
        with self._lock:
            if not self._active:
                raise VoiceSessionError("FM session is not active")
            self._counters["pcm_bytes_received"] += len(data)
            for frame in self._framer.push(data):
                self._counters["pcm_frames_received"] += 1
                self._send(build_fm_data_packet(self._apply_gain(frame)), paced=True)
                self._counters["audio_frames_sent"] += 1
            return self.status()

    def end(self) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return self.status()
            try:
                remainder = self._framer.flush()
                if remainder is not None:
                    self._send(build_fm_data_packet(self._apply_gain(remainder)), paced=True)
                    self._counters["audio_frames_sent"] += 1
                for _ in range(FM_TAIL_SILENCE_FRAMES):
                    self._send(build_fm_data_packet(bytes(320)), paced=True)
                self._send(FM_END_PACKET, paced=False)
            except VoiceSessionError as error:
                self._last_error = str(error)
                raise
            finally:
                self._active = False
                self._ended_at = time.time()
            return self.status()

    def close(self) -> None:
        with self._lock:
            if self._active:
                try:
                    self.end()
                except VoiceSessionError:
                    pass
            self._endpoint.close()

    def status(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "active": self._active,
            "audio_gain": self._gain,
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "last_error": self._last_error,
            "network": self._endpoint.status(),
            "network_records_sent": self._counters["network_packets_sent"],
            **self._counters,
        }

    def __enter__(self) -> "FMStreamingSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def fm_bridge_capability(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "protocol": "fm",
        "audio_input_supported": True,
        "encoder_required": False,
        "framing_required": False,
        "bridge_state": "ready",
        "blocking_reason": None,
        "vocoder": {"name": "analog (PCM)", "frame_samples": 160, "frame_duration_seconds": FRAME_SECONDS},
        "network": {
            "local_address": FM_GATEWAY_ADDRESS,
            "local_port": FM_GATEWAY_PORT,
            "mmdvm_address": FM_MMDVM_ADDRESS,
            "mmdvm_port": FM_MMDVM_PORT,
        },
    }
