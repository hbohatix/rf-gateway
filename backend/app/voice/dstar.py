"""D-Star DV voice session: PCM -> AMBE 2400 -> DSRP -> MMDVM-Host.

MMDVM-Host's [D-Star Network] speaks the ircDDBGateway "DSRP" protocol.
A transmission is a 41-byte radio header followed by 20 ms voice frames
(9 bytes AMBE + 3 bytes slow data), 21 frames per superframe.
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


DSTAR_GATEWAY_ADDRESS = "127.0.0.1"
DSTAR_GATEWAY_PORT = 20010  # RF Gateway side ([D-Star Network] GatewayPort)
DSTAR_MMDVM_ADDRESS = "127.0.0.1"
DSTAR_MMDVM_PORT = 20011  # MMDVM-Host side ([D-Star Network] LocalPort)

DSTAR_FRAMES_PER_SUPERFRAME = 21
DSTAR_SCRAMBLER = bytes((0x70, 0x4F, 0x93))
DSTAR_NULL_SLOW_DATA = bytes((0x16, 0x29, 0xF5))  # 0x66 0x66 0x66 scrambled
DSTAR_SLOW_SYNC = bytes((0x55, 0x2D, 0x16))
DSTAR_END_FRAME = bytes((0x55, 0x55, 0x55, 0x55, 0xC8, 0x7A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
DSTAR_SLOW_DATA_TEXT = 0x40


# OP25's AMBE 2400 quantizer codes the absolute gain (not a delta as in
# AMBE+2) and saturates near the top of the gain table; without this offset
# the decoded audio is ~15 dB too loud and clips. Calibrated with
# backend/native/tools/dstar_frame_check (decoded level within about
# 0.6-1.3x of the input for -10 dB and 0 dB test signals).
DSTAR_GAIN_OFFSET = 4.5


def _software_dstar_encoder(settings: dict[str, Any]):
    # The DVSI path is not wired for AMBE 2400 yet; always use OP25's encoder.
    try:
        user_gain = float(settings.get("vocoder_gain_db") or 0.0)
    except (TypeError, ValueError):
        user_gain = 0.0
    return create_ambe_encoder(
        {**settings, "vocoder": "software", "vocoder_gain_db": DSTAR_GAIN_OFFSET + user_gain},
        dstar=True,
    )


def pad_callsign(value: str | None, length: int) -> bytes:
    text = (value or "").upper().encode("ascii", "replace")[:length]
    return text.ljust(length, b" ")


def build_header(*, my_call: str, my_suffix: str, your_call: str, rpt1: str, rpt2: str, flag1: int = 0x00) -> bytes:
    header = bytearray(41)
    header[0] = flag1
    header[1] = 0x00
    header[2] = 0x00
    header[3:11] = pad_callsign(rpt2, 8)
    header[11:19] = pad_callsign(rpt1, 8)
    header[19:27] = pad_callsign(your_call, 8)
    header[27:35] = pad_callsign(my_call, 8)
    header[35:39] = pad_callsign(my_suffix, 4)
    header[39:41] = fec.crc_ccitt161(header[0:39])
    return bytes(header)


def slow_data_text_frames(message: str) -> list[bytes]:
    """20-character text message as 8 scrambled 3-byte slow-data chunks."""
    text = message.encode("ascii", "replace")[:20].ljust(20, b" ")
    chunks: list[bytes] = []
    for block in range(4):
        raw = bytes((DSTAR_SLOW_DATA_TEXT | block,)) + text[block * 5:block * 5 + 5]
        for half in (raw[0:3], raw[3:6]):
            chunks.append(bytes(b ^ s for b, s in zip(half, DSTAR_SCRAMBLER)))
    return chunks


def build_dsrp_header_packet(stream_id: int, header: bytes) -> bytes:
    return b"DSRP" + bytes((0x20,)) + stream_id.to_bytes(2, "big") + b"\x00" + header


def build_dsrp_data_packet(stream_id: int, seq: int, frame12: bytes, *, end: bool = False) -> bytes:
    if len(frame12) != 12:
        raise ValueError("D-Star voice frame must be 12 bytes")
    flags = (seq & 0x1F) | (0x40 if end else 0x00)
    return b"DSRP" + bytes((0x21,)) + stream_id.to_bytes(2, "big") + bytes((flags, 0x00)) + frame12


def normalize_dstar_settings(settings: dict[str, Any]) -> dict[str, Any]:
    callsign = str(settings.get("callsign") or "").strip().upper()
    if not 3 <= len(callsign) <= 8:
        raise VoiceSessionConfigurationError("D-Star callsign must be 3-8 characters")
    module = str(settings.get("module") or "B").strip().upper()[:1] or "B"
    result = dict(settings)
    result.update(
        callsign=callsign,
        suffix=str(settings.get("suffix") or "RFGW").strip().upper()[:4],
        your_call=str(settings.get("your_call") or "CQCQCQ").strip().upper()[:8] or "CQCQCQ",
        module=module,
        message=str(settings.get("message") or "RF Gateway")[:20],
    )
    return result


class DStarStreamingSession:
    protocol = "dstar"

    def __init__(
        self,
        *,
        local_address: str = DSTAR_GATEWAY_ADDRESS,
        local_port: int = DSTAR_GATEWAY_PORT,
        mmdvm_address: str = DSTAR_MMDVM_ADDRESS,
        mmdvm_port: int = DSTAR_MMDVM_PORT,
        mode_config: dict[str, Any] | None = None,
        encoder_factory=None,
        pace: bool = True,
    ) -> None:
        self._endpoint = UdpEndpoint(local_address, int(local_port), mmdvm_address, int(mmdvm_port))
        self._supplied_mode_config = deepcopy(mode_config) if mode_config is not None else None
        self._encoder_factory = encoder_factory or _software_dstar_encoder
        self._pacer = Pacer(FRAME_SECONDS) if pace else None
        self._lock = RLock()
        self._framer = PcmFramer()
        self._encoder = None
        self._settings: dict[str, Any] | None = None
        self._active = False
        self._stream_id = 0
        self._seq = 0
        self._text_chunks: list[bytes] = []
        self._started_at: float | None = None
        self._ended_at: float | None = None
        self._last_error: str | None = None
        self._counters = {
            "transmissions": 0,
            "pcm_frames_received": 0,
            "pcm_bytes_received": 0,
            "ambe_frames_encoded": 0,
            "headers_sent": 0,
            "voice_frames_sent": 0,
            "superframes_sent": 0,
            "terminators_sent": 0,
            "network_packets_sent": 0,
        }

    @property
    def active(self) -> bool:
        return self._active

    def _load_settings(self) -> dict[str, Any]:
        config = self._supplied_mode_config
        if config is None:
            config = mode_config_store.get_mode("dstar")
        if not config:
            raise VoiceSessionConfigurationError("D-Star mode settings have not been saved")
        return normalize_dstar_settings(config)

    def _send(self, packet: bytes, *, paced: bool) -> None:
        if paced and self._pacer is not None:
            self._pacer.wait()
        self._endpoint.send(packet)
        self._endpoint.drain()
        self._counters["network_packets_sent"] += 1

    def _header(self) -> bytes:
        settings = self._settings or {}
        return build_header(
            my_call=settings["callsign"],
            my_suffix=settings["suffix"],
            your_call=settings["your_call"],
            rpt1="DIRECT",
            rpt2="DIRECT",
        )

    def _slow_data(self, seq: int) -> bytes:
        if seq == 0:
            return DSTAR_SLOW_SYNC
        index = seq - 1
        if index < len(self._text_chunks):
            return self._text_chunks[index]
        return DSTAR_NULL_SLOW_DATA

    def _send_voice(self, pcm_frame: bytes) -> None:
        params = self._encoder.encode_params(pcm_frame)
        self._counters["ambe_frames_encoded"] += 1
        ambe = fec.dstar_ambe_frame(fec.dstar_params_to_bits(params))
        frame = ambe + self._slow_data(self._seq)
        self._send(build_dsrp_data_packet(self._stream_id, self._seq, frame), paced=True)
        self._counters["voice_frames_sent"] += 1
        self._seq = (self._seq + 1) % DSTAR_FRAMES_PER_SUPERFRAME
        if self._seq == 0:
            self._counters["superframes_sent"] += 1

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
            self._seq = 0
            self._stream_id = random.randint(1, 0xFFFF)
            self._text_chunks = slow_data_text_frames(self._settings["message"])
            if self._pacer is not None:
                self._pacer.reset()
            self._active = True
            self._started_at = time.time()
            self._ended_at = None
            self._last_error = None
            self._counters["transmissions"] += 1
            try:
                self._send(build_dsrp_header_packet(self._stream_id, self._header()), paced=False)
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
                raise VoiceSessionError("D-Star session is not active")
            self._counters["pcm_bytes_received"] += len(data)
            for frame in self._framer.push(data):
                self._counters["pcm_frames_received"] += 1
                self._send_voice(frame)
            return self.status()

    def end(self) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return self.status()
            try:
                remainder = self._framer.flush()
                if remainder is not None:
                    self._send_voice(remainder)
                self._send(build_dsrp_data_packet(self._stream_id, self._seq, DSTAR_END_FRAME, end=True), paced=True)
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
            "callsign": settings.get("callsign"),
            "your_call": settings.get("your_call"),
            "stream_id": f"{self._stream_id:04X}" if self._stream_id else None,
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "last_error": self._last_error,
            "vocoder": encoder.status() if encoder is not None else None,
            "network": self._endpoint.status(),
            "network_records_sent": self._counters["network_packets_sent"],
            **self._counters,
        }

    def __enter__(self) -> "DStarStreamingSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def dstar_bridge_capability(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings is None:
        settings = mode_config_store.get_mode("dstar") or {}
    # Only the software encoder can produce D-Star AMBE (2400) here.
    vocoder = ambe_vocoder_status({**settings, "vocoder": "software"})
    ready = bool(vocoder.get("available"))
    return {
        "protocol": "dstar",
        "audio_input_supported": True,
        "encoder_required": True,
        "framing_required": True,
        "bridge_state": "ready" if ready else "unavailable",
        "blocking_reason": None if ready else "dstar_ambe_vocoder_unavailable",
        "vocoder": {"name": "AMBE 2400", "frame_samples": 160, "frame_duration_seconds": FRAME_SECONDS, **vocoder},
        "network": {
            "local_address": DSTAR_GATEWAY_ADDRESS,
            "local_port": DSTAR_GATEWAY_PORT,
            "mmdvm_address": DSTAR_MMDVM_ADDRESS,
            "mmdvm_port": DSTAR_MMDVM_PORT,
        },
    }
