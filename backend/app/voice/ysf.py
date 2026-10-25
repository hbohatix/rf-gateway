"""System Fusion (YSF) DN voice session: PCM -> AMBE+2 -> YSF V/D mode 2.

Frames are built exactly as MMDVM-Host's YSFFICH/YSFPayload encoders do
and sent to MMDVM-Host's [System Fusion Network] as ``YSFD`` packets.
Each communication frame lasts 100 ms and carries five AMBE+2 frames.
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


YSF_GATEWAY_ADDRESS = "127.0.0.1"
YSF_GATEWAY_PORT = 4200  # RF Gateway side ([System Fusion Network] GatewayPort)
YSF_MMDVM_ADDRESS = "127.0.0.1"
YSF_MMDVM_PORT = 3200  # MMDVM-Host side ([System Fusion Network] LocalPort)

YSF_SYNC = bytes((0xD4, 0x71, 0xC9, 0x63, 0x4D))
YSF_FRAME_BYTES = 120
YSF_PAYLOAD_OFFSET = 30  # sync (5) + FICH (25)
YSF_CALLSIGN_LENGTH = 10

YSF_FI_HEADER = 0
YSF_FI_COMMUNICATIONS = 1
YSF_FI_TERMINATOR = 2
YSF_DT_VD_MODE2 = 2
YSF_CM_GROUP1 = 0
YSF_CM_INDIVIDUAL = 3
YSF_MR_BUSY = 2
YSF_CS = 2  # callsign information present (as sent by radios / OP25)
YSF_VD2_FT = 6  # frame total: FN 0..6 per superframe

WHITENING_DATA = bytes((
    0x93, 0xD7, 0x51, 0x21, 0x9C, 0x2F, 0x6C, 0xD0, 0xEF, 0x0F,
    0xF8, 0x3D, 0xF1, 0x73, 0x20, 0x94, 0xED, 0x1E, 0x7C, 0xD8,
))

YSF_FRAME_SECONDS = 5 * FRAME_SECONDS  # 100 ms


def _interleave_table(columns: int) -> list[int]:
    # MMDVM INTERLEAVE_TABLE_x_20: dibit index i -> bit position.
    return [(i % columns) * 40 + (i // columns) * 2 for i in range(columns * 20)]


INTERLEAVE_9_20 = _interleave_table(9)
INTERLEAVE_5_20 = _interleave_table(5)
INTERLEAVE_26_4 = [(i % 26) * 4 + i // 26 for i in range(104)]


def _spread_dibits(convolved: bytes | bytearray, table: list[int], size: int) -> bytearray:
    out = bytearray(size)
    for i, n in enumerate(table):
        fec.write_bit(out, n, fec.read_bit(convolved, 2 * i))
        fec.write_bit(out, n + 1, fec.read_bit(convolved, 2 * i + 1))
    return out


def callsign_field(value: str | None) -> bytes:
    text = (value or "").upper().encode("ascii", "replace")[:YSF_CALLSIGN_LENGTH]
    return text.ljust(YSF_CALLSIGN_LENGTH, b" ")


# ------------------------------------------------------------------- FICH

def encode_fich(
    *,
    fi: int,
    fn: int,
    ft: int,
    dt: int = YSF_DT_VD_MODE2,
    cs: int = YSF_CS,
    cm: int = YSF_CM_GROUP1,
    bn: int = 0,
    bt: int = 0,
    dev: bool = False,
    mr: int = YSF_MR_BUSY,
    voip: bool = True,
    sql: bool = False,
    dgid: int = 0,
) -> bytes:
    """25 FICH bytes (Golay(24,12) + K=5 convolution + interleave)."""
    fich = bytearray(6)
    fich[0] = ((fi & 3) << 6) | ((cs & 3) << 4) | ((cm & 3) << 2) | (bn & 3)
    fich[1] = ((bt & 3) << 6) | ((fn & 7) << 3) | (ft & 7)
    fich[2] = (0x40 if dev else 0) | ((mr & 7) << 3) | (0x04 if voip else 0) | (dt & 3)
    fich[3] = (0x80 if sql else 0) | (dgid & 0x7F)
    fich[4:6] = fec.crc_ccitt162(fich[0:4])

    groups = (
        ((fich[0] << 4) & 0xFF0) | ((fich[1] >> 4) & 0x00F),
        ((fich[1] << 8) & 0xF00) | fich[2],
        ((fich[3] << 4) & 0xFF0) | ((fich[4] >> 4) & 0x00F),
        ((fich[4] << 8) & 0xF00) | fich[5],
    )
    conv_in = bytearray(13)
    for index, group in enumerate(groups):
        conv_in[index * 3:index * 3 + 3] = fec.golay_24_12_encode(group).to_bytes(3, "big")
    convolved = fec.ysf_convolve(conv_in, 100)
    return bytes(_spread_dibits(convolved, INTERLEAVE_5_20, 25))


# ---------------------------------------------------------------- payload

def _encode_csd(data20: bytes) -> bytearray:
    output = bytearray(23)
    for i in range(20):
        output[i] = data20[i] ^ WHITENING_DATA[i]
    output[20:22] = fec.crc_ccitt162(output[0:20])
    convolved = fec.ysf_convolve(output, 180)
    return _spread_dibits(convolved, INTERLEAVE_9_20, 45)


def write_header_payload(frame: bytearray, csd1: bytes, csd2: bytes) -> None:
    """Header/terminator payload (MMDVM CYSFPayload::writeHeader)."""
    first = _encode_csd(csd1)
    second = _encode_csd(csd2)
    for block in range(5):
        base = YSF_PAYLOAD_OFFSET + block * 18
        frame[base:base + 9] = first[block * 9:block * 9 + 9]
        frame[base + 9:base + 18] = second[block * 9:block * 9 + 9]


def write_vd2_dch(frame: bytearray, data10: bytes) -> None:
    """V/D mode 2 data channel (10 bytes per frame)."""
    output = bytearray(13)
    for i in range(10):
        output[i] = data10[i] ^ WHITENING_DATA[i]
    output[10:12] = fec.crc_ccitt162(output[0:10])
    convolved = fec.ysf_convolve(output, 100)
    dch = _spread_dibits(convolved, INTERLEAVE_5_20, 25)
    for block in range(5):
        base = YSF_PAYLOAD_OFFSET + block * 18
        frame[base:base + 5] = dch[block * 5:block * 5 + 5]


def write_vd2_vch(frame: bytearray, block: int, bits49: list[int]) -> None:
    """One AMBE+2 frame into VCH ``block`` (0..4) of a V/D mode 2 frame."""
    if len(bits49) != 49:
        raise ValueError("AMBE+2 frame must be 49 bits")
    raw = [bit for bit in bits49[:27] for _ in range(3)] + list(bits49[27:]) + [0]
    vch = bytearray(fec.bits_to_bytes(raw))
    for i in range(13):
        vch[i] ^= WHITENING_DATA[i]
    offset = YSF_PAYLOAD_OFFSET * 8 + 40 + block * 144
    for i, n in enumerate(INTERLEAVE_26_4):
        fec.write_bit(frame, offset + n, fec.read_bit(vch, i))


def build_frame(fich: bytes) -> bytearray:
    frame = bytearray(YSF_FRAME_BYTES)
    frame[0:5] = YSF_SYNC
    frame[5:30] = fich
    return frame


def build_ysfd_packet(*, gateway: bytes, source: bytes, dest: bytes, counter: int, end: bool, frame: bytes) -> bytes:
    if len(frame) != YSF_FRAME_BYTES:
        raise ValueError("YSF frame must be 120 bytes")
    return (
        b"YSFD" + gateway + source + dest
        + bytes((((counter & 0x7F) << 1) | (1 if end else 0),))
        + bytes(frame)
    )


def normalize_ysf_settings(settings: dict[str, Any]) -> dict[str, Any]:
    callsign = str(settings.get("callsign") or "").strip().upper()
    if not callsign or len(callsign) > YSF_CALLSIGN_LENGTH:
        raise VoiceSessionConfigurationError("YSF source callsign must be 1-10 characters")
    try:
        dgid = int(settings.get("dg_id", 0) or 0)
    except (TypeError, ValueError) as error:
        raise VoiceSessionConfigurationError("DG-ID must be a number") from error
    if not 0 <= dgid <= 99:
        raise VoiceSessionConfigurationError("DG-ID must be 0..99")
    result = dict(settings)
    result.update(
        callsign=callsign,
        destination=str(settings.get("destination") or "ALL").strip().upper()[:YSF_CALLSIGN_LENGTH] or "ALL",
        dg_id=dgid,
        low_deviation=bool(settings.get("low_deviation", False)),
    )
    return result


class YSFStreamingSession:
    protocol = "ysf"

    def __init__(
        self,
        *,
        local_address: str = YSF_GATEWAY_ADDRESS,
        local_port: int = YSF_GATEWAY_PORT,
        mmdvm_address: str = YSF_MMDVM_ADDRESS,
        mmdvm_port: int = YSF_MMDVM_PORT,
        mode_config: dict[str, Any] | None = None,
        encoder_factory=None,
        pace: bool = True,
    ) -> None:
        self._endpoint = UdpEndpoint(local_address, int(local_port), mmdvm_address, int(mmdvm_port))
        self._supplied_mode_config = deepcopy(mode_config) if mode_config is not None else None
        self._encoder_factory = encoder_factory or create_ambe_encoder
        self._pacer = Pacer(YSF_FRAME_SECONDS) if pace else None
        self._lock = RLock()
        self._framer = PcmFramer()
        self._encoder = None
        self._settings: dict[str, Any] | None = None
        self._active = False
        self._frames: list[list[int]] = []
        self._counter = 0
        self._fn = 0
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
            "communication_frames_sent": 0,
            "terminators_sent": 0,
            "network_packets_sent": 0,
        }

    @property
    def active(self) -> bool:
        return self._active

    def _load_settings(self) -> dict[str, Any]:
        config = self._supplied_mode_config
        if config is None:
            config = mode_config_store.get_mode("ysf")
        if not config:
            raise VoiceSessionConfigurationError("YSF mode settings have not been saved")
        return normalize_ysf_settings(config)

    # Callsign fields used in the network header and the DCH.
    def _fields(self) -> dict[str, bytes]:
        settings = self._settings or {}
        return {
            "gateway": callsign_field("RFGATEWAY"),
            "source": callsign_field(settings.get("callsign")),
            "dest": callsign_field(settings.get("destination", "ALL")),
            "down": callsign_field(""),
            "up": callsign_field(""),
        }

    def _fich(self, fi: int, fn: int) -> bytes:
        settings = self._settings or {}
        return encode_fich(
            fi=fi,
            fn=fn,
            ft=YSF_VD2_FT,
            dev=bool(settings.get("low_deviation")),
            dgid=int(settings.get("dg_id", 0)),
        )

    def _send(self, frame: bytes, *, end: bool = False) -> None:
        fields = self._fields()
        packet = build_ysfd_packet(
            gateway=fields["gateway"],
            source=fields["source"],
            dest=fields["dest"],
            counter=self._counter,
            end=end,
            frame=frame,
        )
        if self._pacer is not None:
            self._pacer.wait()
        self._endpoint.send(packet)
        self._endpoint.drain()
        self._counter = (self._counter + 1) & 0x7F
        self._counters["network_packets_sent"] += 1

    def _header_frame(self, fi: int) -> bytes:
        fields = self._fields()
        frame = build_frame(self._fich(fi, 0))
        write_header_payload(frame, fields["dest"] + fields["source"], fields["down"] + fields["up"])
        return bytes(frame)

    def _dch_data(self, fn: int) -> bytes:
        fields = self._fields()
        return {
            0: fields["dest"],
            1: fields["source"],
            2: fields["down"],
            3: fields["up"],
        }.get(fn, b" " * YSF_CALLSIGN_LENGTH)

    def _send_communication_frame(self, frames: list[list[int]]) -> None:
        frame = build_frame(self._fich(YSF_FI_COMMUNICATIONS, self._fn))
        write_vd2_dch(frame, self._dch_data(self._fn))
        for block, bits in enumerate(frames):
            write_vd2_vch(frame, block, bits)
        self._send(bytes(frame))
        self._fn = (self._fn + 1) % (YSF_VD2_FT + 1)
        self._counters["communication_frames_sent"] += 1

    def _encode(self, pcm_frame: bytes) -> list[int]:
        bits = self._encoder.encode_49(pcm_frame)
        self._counters["ambe_frames_encoded"] += 1
        return bits

    def _flush(self) -> None:
        while len(self._frames) >= 5:
            chunk, self._frames = self._frames[:5], self._frames[5:]
            self._send_communication_frame(chunk)

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
            self._fn = 0
            if self._pacer is not None:
                self._pacer.reset()
            self._active = True
            self._started_at = time.time()
            self._ended_at = None
            self._last_error = None
            self._counters["transmissions"] += 1
            try:
                self._send(self._header_frame(YSF_FI_HEADER))
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
                raise VoiceSessionError("YSF session is not active")
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
                while self._frames and len(self._frames) % 5:
                    self._frames.append(self._encode(bytes(320)))
                    self._counters["padding_frames"] += 1
                self._flush()
                self._send(self._header_frame(YSF_FI_TERMINATOR), end=True)
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
            "destination": settings.get("destination"),
            "dg_id": settings.get("dg_id"),
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "last_error": self._last_error,
            "vocoder": encoder.status() if encoder is not None else None,
            "network": self._endpoint.status(),
            "network_records_sent": self._counters["network_packets_sent"],
            **self._counters,
        }

    def __enter__(self) -> "YSFStreamingSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def ysf_bridge_capability(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings is None:
        settings = mode_config_store.get_mode("ysf") or {}
    vocoder = ambe_vocoder_status(settings)
    ready = bool(vocoder.get("available"))
    return {
        "protocol": "ysf",
        "audio_input_supported": True,
        "encoder_required": True,
        "framing_required": True,
        "bridge_state": "ready" if ready else "unavailable",
        "blocking_reason": None if ready else "ysf_ambe_vocoder_unavailable",
        "vocoder": {"name": "AMBE+2 (DN)", "frame_samples": 160, "frame_duration_seconds": FRAME_SECONDS, **vocoder},
        "network": {
            "local_address": YSF_GATEWAY_ADDRESS,
            "local_port": YSF_GATEWAY_PORT,
            "mmdvm_address": YSF_MMDVM_ADDRESS,
            "mmdvm_port": YSF_MMDVM_PORT,
        },
    }
