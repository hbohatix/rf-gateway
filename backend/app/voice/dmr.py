"""DMR voice transmit session (PCM -> AMBE+2 -> DMRD -> MMDVM-Host).

MMDVM-Host's [DMR Network] is a plain UDP "DMRD" (Homebrew data packet)
interface when it talks to a local gateway: no login handshake. MMDVM-Host
regenerates the slot type, sync, EMB and embedded LC of every frame it
receives, so this session only has to supply:

* a voice LC header (full LC, BPTC(196,96) + RS(12,9)),
* voice bursts carrying three FEC-protected AMBE+2 frames each,
* a terminator with LC.
"""

from __future__ import annotations

import random
import time
from copy import deepcopy
from threading import RLock
from typing import Any

from app.config_store import mode_config_store
from app.voice import fec
from app.voice.ambe_vocoder import ambe_vocoder_status, create_ambe_encoder
from app.voice.base import (
    FRAME_SECONDS,
    Pacer,
    PcmFramer,
    UdpEndpoint,
    VoiceSessionConfigurationError,
    VoiceSessionError,
    validate_pcm,
)


DMR_GATEWAY_ADDRESS = "127.0.0.1"
DMR_GATEWAY_PORT = 62031  # RF Gateway side ([DMR Network] GatewayPort)
DMR_MMDVM_ADDRESS = "127.0.0.1"
DMR_MMDVM_PORT = 62032  # MMDVM-Host side ([DMR Network] LocalPort)

DT_VOICE_PI_HEADER = 0x00
DT_VOICE_LC_HEADER = 0x01
DT_TERMINATOR_WITH_LC = 0x02

FLCO_GROUP = 0x00
FLCO_USER_USER = 0x03

VOICE_LC_HEADER_CRC_MASK = b"\x96\x96\x96"
TERMINATOR_WITH_LC_CRC_MASK = b"\x99\x99\x99"

DMR_BURST_SECONDS = 3 * FRAME_SECONDS  # 60 ms per voice burst
DMR_BURSTS_PER_SUPERFRAME = 6
DMR_HEADER_REPEATS = 2
DMRD_PACKET_LENGTH = 55


def build_full_lc(*, flco: int, src_id: int, dst_id: int, fid: int = 0x00, options: int = 0x00) -> bytes:
    return bytes((
        flco & 0x3F,
        fid & 0xFF,
        options & 0xFF,
        (dst_id >> 16) & 0xFF, (dst_id >> 8) & 0xFF, dst_id & 0xFF,
        (src_id >> 16) & 0xFF, (src_id >> 8) & 0xFF, src_id & 0xFF,
    ))


def build_lc_burst(lc: bytes, data_type: int) -> bytes:
    """33-byte DMR burst carrying a voice LC header or terminator."""
    if data_type == DT_VOICE_LC_HEADER:
        mask = VOICE_LC_HEADER_CRC_MASK
    elif data_type == DT_TERMINATOR_WITH_LC:
        mask = TERMINATOR_WITH_LC_CRC_MASK
    else:
        raise ValueError(f"Unsupported LC data type {data_type}")
    parity = fec.rs_12_9_parity(lc)
    payload = lc + bytes(p ^ m for p, m in zip(parity, mask))
    burst = bytearray(33)
    fec.bptc_196_96_encode(payload, burst)
    return bytes(burst)


def build_voice_burst(frames49: list[list[int]]) -> bytes:
    if len(frames49) != 3:
        raise ValueError("A DMR voice burst carries exactly three AMBE+2 frames")
    burst = bytearray(33)
    for index, bits in enumerate(frames49):
        fec.place_dmr_ambe(burst, index, bits)
    return bytes(burst)


def build_dmrd_packet(
    *,
    seq: int,
    src_id: int,
    dst_id: int,
    repeater_id: int,
    slot: int,
    private_call: bool,
    stream_id: int,
    burst: bytes,
    data_type: int | None = None,
    voice_sync: bool = False,
    voice_n: int = 0,
) -> bytes:
    if len(burst) != 33:
        raise ValueError("DMR burst must be 33 bytes")
    flags = 0x80 if slot == 2 else 0x00
    if private_call:
        flags |= 0x40
    if data_type is not None:
        flags |= 0x20 | (data_type & 0x0F)
    elif voice_sync:
        flags |= 0x10
    else:
        flags |= voice_n & 0x0F
    packet = bytearray(DMRD_PACKET_LENGTH)
    packet[0:4] = b"DMRD"
    packet[4] = seq & 0xFF
    packet[5:8] = (src_id & 0xFFFFFF).to_bytes(3, "big")
    packet[8:11] = (dst_id & 0xFFFFFF).to_bytes(3, "big")
    packet[11:15] = (repeater_id & 0xFFFFFFFF).to_bytes(4, "big")
    packet[15] = flags
    packet[16:20] = (stream_id & 0xFFFFFFFF).to_bytes(4, "big")
    packet[20:53] = burst
    packet[53] = 0  # BER
    packet[54] = 0  # RSSI
    return bytes(packet)


def normalize_dmr_settings(settings: dict[str, Any]) -> dict[str, Any]:
    try:
        radio_id = int(settings.get("radio_id", 0))
        talkgroup = int(settings.get("talkgroup", 0))
        timeslot = int(settings.get("timeslot", 2))
        color_code = int(settings.get("color_code", 1))
    except (TypeError, ValueError) as error:
        raise VoiceSessionConfigurationError(f"Invalid DMR settings: {error}") from error
    if not 1 <= radio_id <= 0xFFFFFF:
        raise VoiceSessionConfigurationError("DMR source ID must be 1..16777215")
    if not 1 <= talkgroup <= 0xFFFFFF:
        raise VoiceSessionConfigurationError("DMR destination (talkgroup/ID) must be 1..16777215")
    if timeslot not in (1, 2):
        raise VoiceSessionConfigurationError("DMR timeslot must be 1 or 2")
    if not 0 <= color_code <= 15:
        raise VoiceSessionConfigurationError("DMR color code must be 0..15")
    call_type = str(settings.get("call_type") or "group").strip().lower()
    if call_type not in ("group", "private"):
        raise VoiceSessionConfigurationError("DMR call type must be group or private")
    result = dict(settings)
    result.update(
        radio_id=radio_id,
        talkgroup=talkgroup,
        timeslot=timeslot,
        color_code=color_code,
        call_type=call_type,
    )
    return result


class DMRStreamingSession:
    protocol = "dmr"

    def __init__(
        self,
        *,
        local_address: str = DMR_GATEWAY_ADDRESS,
        local_port: int = DMR_GATEWAY_PORT,
        mmdvm_address: str = DMR_MMDVM_ADDRESS,
        mmdvm_port: int = DMR_MMDVM_PORT,
        mode_config: dict[str, Any] | None = None,
        encoder_factory=None,
        pace: bool = True,
    ) -> None:
        self._endpoint = UdpEndpoint(local_address, int(local_port), mmdvm_address, int(mmdvm_port))
        self._supplied_mode_config = deepcopy(mode_config) if mode_config is not None else None
        self._encoder_factory = encoder_factory or create_ambe_encoder
        self._pacer = Pacer(DMR_BURST_SECONDS) if pace else None
        self._lock = RLock()
        self._framer = PcmFramer()
        self._encoder = None
        self._settings: dict[str, Any] | None = None
        self._active = False
        self._frames: list[list[int]] = []
        self._seq = 0
        self._stream_id = 0
        self._burst_index = 0
        self._started_at: float | None = None
        self._ended_at: float | None = None
        self._last_error: str | None = None
        self._counters = {
            "transmissions": 0,
            "pcm_frames_received": 0,
            "pcm_bytes_received": 0,
            "ambe_frames_encoded": 0,
            "padding_frames": 0,
            "headers_sent": 0,
            "voice_bursts_sent": 0,
            "superframes_sent": 0,
            "terminators_sent": 0,
            "network_packets_sent": 0,
        }

    # ------------------------------------------------------------ properties
    @property
    def active(self) -> bool:
        return self._active

    # --------------------------------------------------------------- helpers
    def _load_settings(self) -> dict[str, Any]:
        config = self._supplied_mode_config
        if config is None:
            config = mode_config_store.get_mode("dmr")
        if not config:
            raise VoiceSessionConfigurationError("DMR mode settings have not been saved")
        return normalize_dmr_settings(config)

    def _send(self, packet: bytes) -> None:
        if self._pacer is not None:
            self._pacer.wait()
        self._endpoint.send(packet)
        self._endpoint.drain()
        self._counters["network_packets_sent"] += 1
        self._seq = (self._seq + 1) & 0xFF

    def _packet(self, burst: bytes, **kwargs: Any) -> bytes:
        settings = self._settings or {}
        return build_dmrd_packet(
            seq=self._seq,
            src_id=settings["radio_id"],
            dst_id=settings["talkgroup"],
            repeater_id=settings["radio_id"],
            slot=settings["timeslot"],
            private_call=settings["call_type"] == "private",
            stream_id=self._stream_id,
            burst=burst,
            **kwargs,
        )

    def _lc(self) -> bytes:
        settings = self._settings or {}
        flco = FLCO_USER_USER if settings.get("call_type") == "private" else FLCO_GROUP
        return build_full_lc(flco=flco, src_id=settings["radio_id"], dst_id=settings["talkgroup"])

    def _send_voice_burst(self, frames: list[list[int]]) -> None:
        position = self._burst_index % DMR_BURSTS_PER_SUPERFRAME
        burst = build_voice_burst(frames)
        if position == 0:
            packet = self._packet(burst, voice_sync=True)
        else:
            packet = self._packet(burst, voice_n=position)
        self._send(packet)
        self._burst_index += 1
        self._counters["voice_bursts_sent"] += 1
        if position == DMR_BURSTS_PER_SUPERFRAME - 1:
            self._counters["superframes_sent"] += 1

    def _encode(self, pcm_frame: bytes) -> list[int]:
        bits = self._encoder.encode_49(pcm_frame)
        self._counters["ambe_frames_encoded"] += 1
        return bits

    def _flush_complete_bursts(self) -> None:
        while len(self._frames) >= 3:
            burst_frames, self._frames = self._frames[:3], self._frames[3:]
            self._send_voice_burst(burst_frames)

    # ------------------------------------------------------------ public API
    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._active:
                return self.status()
            self._settings = self._load_settings()
            try:
                self._encoder = self._encoder_factory(self._settings)
                self._endpoint.open()
            except Exception:
                self._close_encoder()
                raise
            self._framer.clear()
            self._frames = []
            self._burst_index = 0
            self._stream_id = random.randint(1, 0xFFFFFFFE)
            if self._pacer is not None:
                self._pacer.reset()
            self._active = True
            self._started_at = time.time()
            self._ended_at = None
            self._last_error = None
            self._counters["transmissions"] += 1
            header = build_lc_burst(self._lc(), DT_VOICE_LC_HEADER)
            try:
                for _ in range(DMR_HEADER_REPEATS):
                    self._send(self._packet(header, data_type=DT_VOICE_LC_HEADER))
                    self._counters["headers_sent"] += 1
            except VoiceSessionError as error:
                self._last_error = str(error)
                self._active = False
                raise
            return self.status()

    def feed_pcm(self, pcm: bytes) -> dict[str, Any]:
        data = validate_pcm(pcm)
        with self._lock:
            if not self._active:
                raise VoiceSessionError("DMR session is not active")
            frames = self._framer.push(data)
            self._counters["pcm_bytes_received"] += len(data)
            for frame in frames:
                self._counters["pcm_frames_received"] += 1
                self._frames.append(self._encode(frame))
                self._flush_complete_bursts()
            return self.status()

    def end(self) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return self.status()
            try:
                remainder = self._framer.flush()
                if remainder is not None:
                    self._frames.append(self._encode(remainder))
                while self._frames and len(self._frames) % 3:
                    self._frames.append(self._encode(bytes(320)))
                    self._counters["padding_frames"] += 1
                self._flush_complete_bursts()
                terminator = build_lc_burst(self._lc(), DT_TERMINATOR_WITH_LC)
                self._send(self._packet(terminator, data_type=DT_TERMINATOR_WITH_LC))
                self._counters["terminators_sent"] += 1
            except VoiceSessionError as error:
                self._last_error = str(error)
                raise
            finally:
                self._active = False
                self._ended_at = time.time()
                self._close_encoder()
            return self.status()

    def _close_encoder(self) -> None:
        encoder, self._encoder = self._encoder, None
        if encoder is not None:
            try:
                encoder.close()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            if self._active:
                try:
                    self.end()
                except VoiceSessionError:
                    pass
            self._close_encoder()
            self._endpoint.close()

    def status(self) -> dict[str, Any]:
        settings = self._settings or {}
        encoder = self._encoder
        return {
            "protocol": self.protocol,
            "active": self._active,
            "source_id": settings.get("radio_id"),
            "destination_id": settings.get("talkgroup"),
            "timeslot": settings.get("timeslot"),
            "call_type": settings.get("call_type"),
            "stream_id": f"{self._stream_id:08X}" if self._stream_id else None,
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "last_error": self._last_error,
            "vocoder": encoder.status() if encoder is not None else None,
            "network": self._endpoint.status(),
            # Same counter name as the P25 session so existing monitors keep working.
            "network_records_sent": self._counters["network_packets_sent"],
            **self._counters,
        }

    def __enter__(self) -> "DMRStreamingSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def dmr_bridge_capability(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings is None:
        settings = mode_config_store.get_mode("dmr") or {}
    vocoder = ambe_vocoder_status(settings)
    ready = bool(vocoder.get("available"))
    return {
        "protocol": "dmr",
        "audio_input_supported": True,
        "encoder_required": True,
        "framing_required": True,
        "bridge_state": "ready" if ready else "unavailable",
        "blocking_reason": None if ready else "dmr_ambe_vocoder_unavailable",
        "vocoder": {"name": "AMBE+2", "frame_samples": 160, "frame_duration_seconds": FRAME_SECONDS, **vocoder},
        "network": {
            "local_address": DMR_GATEWAY_ADDRESS,
            "local_port": DMR_GATEWAY_PORT,
            "mmdvm_address": DMR_MMDVM_ADDRESS,
            "mmdvm_port": DMR_MMDVM_PORT,
        },
    }
