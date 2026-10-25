"""NXDN (4800 bps EHR) voice session: PCM -> AMBE+2 -> MMDVM-Host.

MMDVM-Host's Icom-protocol [NXDN Network] carries *unencoded* NXDN frames
(33 bytes): the LICH byte, the 26-bit SACCH payload and either two pairs
of raw 49-bit AMBE+2 frames or raw FACCH1 messages. MMDVM-Host adds the
CRCs, convolutional coding, interleaving and scrambling itself.

A transmission is:
    VCALL header (FACCH1)  ->  voice frames (80 ms, 4 AMBE frames each,
    VCALL split over a 4-frame SACCH superframe)  ->  TX_REL (FACCH1).
"""

from __future__ import annotations

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


NXDN_GATEWAY_ADDRESS = "127.0.0.1"
NXDN_GATEWAY_PORT = 14020  # RF Gateway side ([NXDN Network] GatewayPort)
NXDN_MMDVM_ADDRESS = "127.0.0.1"
NXDN_MMDVM_PORT = 14021  # MMDVM-Host side ([NXDN Network] LocalPort)

NXDN_FRAME_SECONDS = 4 * FRAME_SECONDS  # 80 ms

LICH_RFCT_RDCH = 2
LICH_USC_SACCH_NS = 0
LICH_USC_SACCH_SS = 2
LICH_STEAL_FACCH = 0
LICH_STEAL_NONE = 3
LICH_DIRECTION_INBOUND = 0

SR_SINGLE = 0
SR_PARTS = (3, 2, 1, 0)  # SR 1/4, 2/4, 3/4, 4/4

MESSAGE_VCALL = 0x01
MESSAGE_TX_REL = 0x08
MESSAGE_IDLE = 0x10

CALL_TYPE_GROUP = 0x20  # call type 001 (group), 4800 bps EHR, half duplex
CALL_TYPE_INDIVIDUAL = 0x80  # call type 100 (individual)

ICOM_TYPE_VOICE_HEADER = bytes((0x23, 0x1C, 0x21))
ICOM_TYPE_VOICE_BODY = bytes((0x23, 0x10, 0x21))


def lich_byte(*, usc: int, option: int, rfct: int = LICH_RFCT_RDCH, direction: int = LICH_DIRECTION_INBOUND) -> int:
    value = ((rfct & 3) << 6) | ((usc & 3) << 4) | ((option & 3) << 2) | ((direction & 1) << 1)
    if (value & 0xF0) in (0x80, 0xB0):
        value |= 0x01  # MMDVM CNXDNLICH::getParity
    return value


def layer3_call(message_type: int, *, src_id: int, dst_id: int, group: bool) -> bytes:
    """10-byte Layer 3 VCALL / TX_REL message (CRC is added by MMDVM-Host)."""
    data = bytearray(10)
    data[0] = message_type & 0x3F
    data[1] = 0x00  # CC option
    data[2] = CALL_TYPE_GROUP if group else CALL_TYPE_INDIVIDUAL
    data[3:5] = (src_id & 0xFFFF).to_bytes(2, "big")
    data[5:7] = (dst_id & 0xFFFF).to_bytes(2, "big")
    return bytes(data)


def sacch_raw(structure: int, data18: list[int]) -> bytes:
    """4 raw SACCH bytes: structure (2) + RAN (6, set by MMDVM) + 18 data bits."""
    raw = bytearray(4)
    raw[0] = (structure & 3) << 6
    for index, bit in enumerate(data18):
        fec.write_bit(raw, 8 + index, bit)
    return bytes(raw)


def sacch_idle() -> bytes:
    bits = fec.bytes_to_bits(bytes((MESSAGE_IDLE, 0x00, 0x00)))[:18]
    return sacch_raw(SR_SINGLE, bits)


def pack_ambe_pair(first49: list[int], second49: list[int]) -> bytes:
    if len(first49) != 49 or len(second49) != 49:
        raise ValueError("AMBE+2 frames must be 49 bits")
    bits = list(first49) + list(second49) + [0] * (112 - 98)
    return fec.bits_to_bytes(bits)


def build_frame(lich: int, sacch: bytes, first: bytes, second: bytes) -> bytes:
    frame = bytearray(33)
    frame[0] = lich
    frame[1:5] = sacch
    frame[5:5 + len(first)] = first
    frame[19:19 + len(second)] = second
    return bytes(frame)


def build_icom_packet(frame33: bytes, *, header: bool) -> bytes:
    if len(frame33) != 33:
        raise ValueError("NXDN network frame must be 33 bytes")
    packet = bytearray(102)
    packet[0:4] = b"ICOM"
    packet[4:8] = bytes((0x01, 0x01, 0x08, 0xE0))
    packet[37:40] = ICOM_TYPE_VOICE_HEADER if header else ICOM_TYPE_VOICE_BODY
    packet[40:73] = frame33
    return bytes(packet)


def normalize_nxdn_settings(settings: dict[str, Any]) -> dict[str, Any]:
    try:
        unit_id = int(settings.get("radio_id", 0))
        destination = int(settings.get("talkgroup", 0))
        ran = int(settings.get("ran", 1))
    except (TypeError, ValueError) as error:
        raise VoiceSessionConfigurationError(f"Invalid NXDN settings: {error}") from error
    if not 1 <= unit_id <= 65519:
        raise VoiceSessionConfigurationError("NXDN unit ID must be 1..65519")
    if not 0 <= destination <= 65535:
        raise VoiceSessionConfigurationError("NXDN talkgroup must be 0..65535")
    if not 0 <= ran <= 63:
        raise VoiceSessionConfigurationError("NXDN RAN must be 0..63")
    call_type = str(settings.get("call_type") or "group").strip().lower()
    if call_type not in ("group", "private"):
        raise VoiceSessionConfigurationError("NXDN call type must be group or private")
    result = dict(settings)
    result.update(radio_id=unit_id, talkgroup=destination, ran=ran, call_type=call_type)
    return result


class NXDNStreamingSession:
    protocol = "nxdn"

    def __init__(
        self,
        *,
        local_address: str = NXDN_GATEWAY_ADDRESS,
        local_port: int = NXDN_GATEWAY_PORT,
        mmdvm_address: str = NXDN_MMDVM_ADDRESS,
        mmdvm_port: int = NXDN_MMDVM_PORT,
        mode_config: dict[str, Any] | None = None,
        encoder_factory=None,
        pace: bool = True,
    ) -> None:
        self._endpoint = UdpEndpoint(local_address, int(local_port), mmdvm_address, int(mmdvm_port))
        self._supplied_mode_config = deepcopy(mode_config) if mode_config is not None else None
        self._encoder_factory = encoder_factory or create_ambe_encoder
        self._pacer = Pacer(NXDN_FRAME_SECONDS) if pace else None
        self._lock = RLock()
        self._framer = PcmFramer()
        self._encoder = None
        self._settings: dict[str, Any] | None = None
        self._active = False
        self._frames: list[list[int]] = []
        self._superframe_index = 0
        self._vcall_bits: list[int] = []
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
            "voice_frames_sent": 0,
            "terminators_sent": 0,
            "network_packets_sent": 0,
        }

    @property
    def active(self) -> bool:
        return self._active

    def _load_settings(self) -> dict[str, Any]:
        config = self._supplied_mode_config
        if config is None:
            config = mode_config_store.get_mode("nxdn")
        if not config:
            raise VoiceSessionConfigurationError("NXDN mode settings have not been saved")
        return normalize_nxdn_settings(config)

    def _message(self, message_type: int) -> bytes:
        settings = self._settings or {}
        return layer3_call(
            message_type,
            src_id=settings["radio_id"],
            dst_id=settings["talkgroup"],
            group=settings["call_type"] == "group",
        )

    def _send(self, frame: bytes, *, header: bool) -> None:
        if self._pacer is not None:
            self._pacer.wait()
        self._endpoint.send(build_icom_packet(frame, header=header))
        self._endpoint.drain()
        self._counters["network_packets_sent"] += 1

    def _send_facch(self, message_type: int) -> None:
        message = self._message(message_type)
        raw = message + bytes(2)  # 12-byte FACCH1 raw: CRC12 is added by MMDVM-Host
        frame = build_frame(
            lich_byte(usc=LICH_USC_SACCH_NS, option=LICH_STEAL_FACCH),
            sacch_idle(),
            raw,
            raw,
        )
        self._send(frame, header=True)

    def _send_voice(self, frames: list[list[int]]) -> None:
        part = self._superframe_index % 4
        sacch = sacch_raw(SR_PARTS[part], self._vcall_bits[part * 18:part * 18 + 18])
        frame = build_frame(
            lich_byte(usc=LICH_USC_SACCH_SS, option=LICH_STEAL_NONE),
            sacch,
            pack_ambe_pair(frames[0], frames[1]),
            pack_ambe_pair(frames[2], frames[3]),
        )
        self._send(frame, header=False)
        self._superframe_index += 1
        self._counters["voice_frames_sent"] += 1

    def _encode(self, pcm_frame: bytes) -> list[int]:
        bits = self._encoder.encode_49(pcm_frame)
        self._counters["ambe_frames_encoded"] += 1
        return bits

    def _flush(self) -> None:
        while len(self._frames) >= 4:
            chunk, self._frames = self._frames[:4], self._frames[4:]
            self._send_voice(chunk)

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
            self._superframe_index = 0
            self._vcall_bits = fec.bytes_to_bits(self._message(MESSAGE_VCALL))[:72]
            if self._pacer is not None:
                self._pacer.reset()
            self._active = True
            self._started_at = time.time()
            self._ended_at = None
            self._last_error = None
            self._counters["transmissions"] += 1
            try:
                self._send_facch(MESSAGE_VCALL)
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
                raise VoiceSessionError("NXDN session is not active")
            self._counters["pcm_bytes_received"] += len(data)
            for frame in self._framer.push(data):
                self._counters["pcm_frames_received"] += 1
                self._frames.append(self._encode(frame))
                self._flush()
            return self.status()

    def end(self) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return self.status()
            try:
                remainder = self._framer.flush()
                if remainder is not None:
                    self._frames.append(self._encode(remainder))
                while self._frames and len(self._frames) % 4:
                    self._frames.append(self._encode(bytes(320)))
                    self._counters["padding_frames"] += 1
                self._flush()
                self._send_facch(MESSAGE_TX_REL)
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
            "call_type": settings.get("call_type"),
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "last_error": self._last_error,
            "vocoder": encoder.status() if encoder is not None else None,
            "network": self._endpoint.status(),
            "network_records_sent": self._counters["network_packets_sent"],
            **self._counters,
        }

    def __enter__(self) -> "NXDNStreamingSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def nxdn_bridge_capability(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings is None:
        settings = mode_config_store.get_mode("nxdn") or {}
    vocoder = ambe_vocoder_status(settings)
    ready = bool(vocoder.get("available"))
    return {
        "protocol": "nxdn",
        "audio_input_supported": True,
        "encoder_required": True,
        "framing_required": True,
        "bridge_state": "ready" if ready else "unavailable",
        "blocking_reason": None if ready else "nxdn_ambe_vocoder_unavailable",
        "vocoder": {"name": "AMBE+2 (EHR)", "frame_samples": 160, "frame_duration_seconds": FRAME_SECONDS, **vocoder},
        "network": {
            "local_address": NXDN_GATEWAY_ADDRESS,
            "local_port": NXDN_GATEWAY_PORT,
            "mmdvm_address": NXDN_MMDVM_ADDRESS,
            "mmdvm_port": NXDN_MMDVM_PORT,
        },
    }
