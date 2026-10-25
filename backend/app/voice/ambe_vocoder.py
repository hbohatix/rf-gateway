"""AMBE+2 (3600x2450) voice encoders used by DMR, YSF DN and NXDN.

Two families are supported:

* ``software`` - OP25's AMBE encoder built into
  ``backend/native/libambe_vocoder_wrapper.so`` (no extra hardware).
* ``dv3000_serial`` / ``ambeserver`` - a DVSI AMBE-3000 chip (ThumbDV,
  DV3000, DVstick) on a serial port or behind an AMBEServer UDP bridge.
  This path is experimental and was written against the DVSI packet
  format; it needs real hardware for validation.

Every encoder returns the 49 voice bits of one 20 ms frame in mbelib
``ambe_d`` order. FEC and interleaving are added by :mod:`app.voice.fec`.
"""

from __future__ import annotations

import ctypes
import os
import socket
import struct
import time
from pathlib import Path
from threading import RLock
from typing import Any

from app.voice.base import PCM_BYTES_PER_FRAME, VoiceSessionConfigurationError, VoiceSessionError


NATIVE_DIR = Path(__file__).resolve().parent.parent.parent / "native"
SOFTWARE_LIBRARY_PATH = NATIVE_DIR / "libambe_vocoder_wrapper.so"

VOCODER_BACKENDS = ("software", "dv3000_serial", "ambeserver")

# Frame MMDVM-Host substitutes for an unusable AMBE+2 frame (AMBEFEC.cpp).
NULL_AMBE_A = 0xF00292
NULL_AMBE_B = 0x0E0B20


class AmbeEncoderError(VoiceSessionError):
    pass


def _bytes_to_49_bits(data: bytes) -> list[int]:
    bits = [(byte >> (7 - i)) & 1 for byte in data for i in range(8)]
    return bits[:49]


# ------------------------------------------------------------ software (OP25)

class _SoftwareLibrary:
    """Lazily loaded shared library (one per process)."""

    _lock = RLock()
    _library: ctypes.CDLL | None = None
    _error: str | None = None

    @classmethod
    def load(cls, path: Path = SOFTWARE_LIBRARY_PATH) -> ctypes.CDLL:
        with cls._lock:
            if cls._library is not None:
                return cls._library
            if not path.is_file():
                cls._error = (
                    f"AMBE encoder library not found: {path}. "
                    "Build it with backend/native/build_ambe_wrapper.sh"
                )
                raise VoiceSessionConfigurationError(cls._error)
            try:
                library = ctypes.CDLL(str(path))
                library.rf_gateway_ambe_abi_version.restype = ctypes.c_int
                library.rf_gateway_ambe_create.argtypes = [ctypes.c_int]
                library.rf_gateway_ambe_create.restype = ctypes.c_void_p
                library.rf_gateway_ambe_destroy.argtypes = [ctypes.c_void_p]
                library.rf_gateway_ambe_destroy.restype = None
                library.rf_gateway_ambe_set_gain_adjust.argtypes = [ctypes.c_void_p, ctypes.c_float]
                library.rf_gateway_ambe_set_gain_adjust.restype = None
                library.rf_gateway_ambe_encode_49.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_int16),
                    ctypes.POINTER(ctypes.c_uint8),
                ]
                library.rf_gateway_ambe_encode_49.restype = ctypes.c_int
                library.rf_gateway_ambe_encode_params.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_int16),
                    ctypes.POINTER(ctypes.c_int),
                ]
                library.rf_gateway_ambe_encode_params.restype = ctypes.c_int
                version = library.rf_gateway_ambe_abi_version()
                if version != 1:
                    raise VoiceSessionConfigurationError(f"Unsupported AMBE wrapper ABI {version}")
            except (OSError, AttributeError) as error:
                cls._error = f"Unable to load AMBE encoder library: {error}"
                raise VoiceSessionConfigurationError(cls._error) from error
            cls._library = library
            cls._error = None
            return library

    @classmethod
    def status(cls, path: Path = SOFTWARE_LIBRARY_PATH) -> dict[str, Any]:
        try:
            cls.load(path)
        except VoiceSessionConfigurationError as error:
            return {"available": False, "library_path": str(path), "error": str(error)}
        return {"available": True, "library_path": str(path), "error": None}


class SoftwareAmbeEncoder:
    name = "software"

    def __init__(self, *, dstar: bool = False, gain_db: float = 0.0) -> None:
        self._library = _SoftwareLibrary.load()
        handle = self._library.rf_gateway_ambe_create(1 if dstar else 0)
        if not handle:
            raise AmbeEncoderError("Unable to allocate AMBE encoder")
        self._handle = ctypes.c_void_p(handle)
        self._lock = RLock()
        self._dstar = dstar
        self.frames_encoded = 0
        self.fallback_frames = 0
        if gain_db:
            self._library.rf_gateway_ambe_set_gain_adjust(self._handle, float(gain_db))

    def _samples(self, pcm_frame: bytes):
        if len(pcm_frame) != PCM_BYTES_PER_FRAME:
            raise AmbeEncoderError("AMBE encoder needs exactly 160 samples")
        return (ctypes.c_int16 * 160).from_buffer_copy(pcm_frame)

    def encode_49(self, pcm_frame: bytes) -> list[int]:
        samples = self._samples(pcm_frame)
        output = (ctypes.c_uint8 * 49)()
        with self._lock:
            if self._handle is None:
                raise AmbeEncoderError("AMBE encoder is closed")
            result = self._library.rf_gateway_ambe_encode_49(self._handle, samples, output)
        if result < 0:
            raise AmbeEncoderError("AMBE encoder rejected the frame")
        self.frames_encoded += 1
        if result == 0:
            self.fallback_frames += 1
        return [int(bit) & 1 for bit in output]

    def encode_params(self, pcm_frame: bytes) -> list[int]:
        samples = self._samples(pcm_frame)
        output = (ctypes.c_int * 9)()
        with self._lock:
            if self._handle is None:
                raise AmbeEncoderError("AMBE encoder is closed")
            result = self._library.rf_gateway_ambe_encode_params(self._handle, samples, output)
        if result < 0:
            raise AmbeEncoderError("AMBE encoder rejected the frame")
        self.frames_encoded += 1
        if result == 0:
            self.fallback_frames += 1
        return list(output)

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._library.rf_gateway_ambe_destroy(self._handle)
                self._handle = None

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "codec": "AMBE 3600x2400" if self._dstar else "AMBE+2 3600x2450",
            "frames_encoded": self.frames_encoded,
            "fallback_frames": self.fallback_frames,
            "library_path": str(SOFTWARE_LIBRARY_PATH),
        }

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        try:
            self.close()
        except Exception:
            pass


# ------------------------------------------------------- DVSI AMBE-3000 chip

DV3000_START = 0x61
DV3000_TYPE_CONTROL = 0x00
DV3000_TYPE_CHANNEL = 0x01
DV3000_TYPE_SPEECH = 0x02
DV3000_PKT_PRODID = 0x30
DV3000_PKT_RESET = 0x33
DV3000_PKT_READY = 0x39
DV3000_PKT_RATET = 0x09
DV3000_FIELD_SPEECHD = 0x00
DV3000_FIELD_CHAND = 0x01
# Rate index 34: AMBE+2 2450 bps voice without FEC (49 bits / 20 ms).
DV3000_RATE_AMBE2_2450_NOFEC = 34


def dv3000_packet(packet_type: int, payload: bytes) -> bytes:
    return struct.pack(">BHB", DV3000_START, len(payload), packet_type) + payload


def dv3000_speech_packet(pcm_frame: bytes) -> bytes:
    """PCM (S16LE) -> DVSI speech packet (big-endian samples)."""
    if len(pcm_frame) != PCM_BYTES_PER_FRAME:
        raise AmbeEncoderError("DV3000 speech packet needs 160 samples")
    samples = struct.unpack("<160h", pcm_frame)
    return dv3000_packet(
        DV3000_TYPE_SPEECH,
        bytes((DV3000_FIELD_SPEECHD, 160)) + struct.pack(">160h", *samples),
    )


def dv3000_parse_channel_packet(packet: bytes) -> list[int]:
    if len(packet) < 6 or packet[0] != DV3000_START or packet[3] != DV3000_TYPE_CHANNEL:
        raise AmbeEncoderError("DV3000 returned an unexpected packet")
    payload = packet[4:]
    if payload[0] != DV3000_FIELD_CHAND:
        raise AmbeEncoderError("DV3000 channel packet without CHAND field")
    bit_count = payload[1]
    data = payload[2:2 + (bit_count + 7) // 8]
    if bit_count < 49 or len(data) < 7:
        raise AmbeEncoderError(f"DV3000 returned {bit_count} bits; expected 49")
    return _bytes_to_49_bits(data)


class _Dv3000Transport:
    def write(self, data: bytes) -> None: ...
    def read_packet(self, timeout: float) -> bytes: ...
    def close(self) -> None: ...


class _SerialTransport(_Dv3000Transport):
    BAUD_RATES = {
        115200: "B115200",
        230400: "B230400",
        460800: "B460800",
        921600: "B921600",
    }

    def __init__(self, device: str, baud: int) -> None:
        try:
            import termios  # Linux only
        except ImportError as error:  # pragma: no cover - Windows dev hosts
            raise VoiceSessionConfigurationError("Serial DV3000 requires Linux termios") from error
        if baud not in self.BAUD_RATES:
            raise VoiceSessionConfigurationError(f"Unsupported DV3000 baud rate {baud}")
        try:
            self._fd = os.open(device, os.O_RDWR | os.O_NOCTTY)
        except OSError as error:
            raise VoiceSessionConfigurationError(f"Unable to open {device}: {error}") from error
        attrs = termios.tcgetattr(self._fd)
        speed = getattr(termios, self.BAUD_RATES[baud])
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag
        attrs[3] = 0  # lflag
        attrs[4] = speed
        attrs[5] = speed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 1
        termios.tcsetattr(self._fd, termios.TCSANOW, attrs)
        termios.tcflush(self._fd, termios.TCIOFLUSH)

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(self._fd, view)
            view = view[written:]

    def _read_exact(self, size: int, deadline: float) -> bytes:
        buffer = bytearray()
        while len(buffer) < size:
            if time.monotonic() > deadline:
                raise AmbeEncoderError("DV3000 read timeout")
            chunk = os.read(self._fd, size - len(buffer))
            if chunk:
                buffer.extend(chunk)
        return bytes(buffer)

    def read_packet(self, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while True:
            first = self._read_exact(1, deadline)
            if first[0] == DV3000_START:
                break
        header = self._read_exact(3, deadline)
        length = (header[0] << 8) | header[1]
        return first + header + self._read_exact(length, deadline)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


class _UdpTransport(_Dv3000Transport):
    def __init__(self, host: str, port: int) -> None:
        self._address = (host, int(port))
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def write(self, data: bytes) -> None:
        self._socket.sendto(data, self._address)

    def read_packet(self, timeout: float) -> bytes:
        self._socket.settimeout(timeout)
        try:
            data, _ = self._socket.recvfrom(2048)
        except socket.timeout as error:
            raise AmbeEncoderError("AMBEServer read timeout") from error
        return data

    def close(self) -> None:
        self._socket.close()


class Dv3000AmbeEncoder:
    """DVSI AMBE-3000 based encoder (experimental)."""

    def __init__(self, transport: _Dv3000Transport, *, name: str, timeout: float = 0.5) -> None:
        self.name = name
        self._transport = transport
        self._timeout = timeout
        self._lock = RLock()
        self.frames_encoded = 0
        self.product_id: str | None = None
        self._initialise()

    def _control(self, payload: bytes) -> bytes:
        self._transport.write(dv3000_packet(DV3000_TYPE_CONTROL, payload))
        return self._transport.read_packet(self._timeout * 4)

    def _initialise(self) -> None:
        reply = self._control(bytes((DV3000_PKT_RESET,)))
        if DV3000_PKT_READY not in reply[4:]:
            raise VoiceSessionConfigurationError("DV3000 did not report READY after reset")
        reply = self._control(bytes((DV3000_PKT_PRODID,)))
        self.product_id = reply[5:].split(b"\x00", 1)[0].decode("ascii", "replace") or None
        reply = self._control(bytes((DV3000_PKT_RATET, DV3000_RATE_AMBE2_2450_NOFEC)))
        if len(reply) < 6 or reply[4] != DV3000_PKT_RATET or reply[5] != 0:
            raise VoiceSessionConfigurationError("DV3000 rejected AMBE+2 rate 34")

    def encode_49(self, pcm_frame: bytes) -> list[int]:
        with self._lock:
            self._transport.write(dv3000_speech_packet(pcm_frame))
            packet = self._transport.read_packet(self._timeout)
        self.frames_encoded += 1
        return dv3000_parse_channel_packet(packet)

    def close(self) -> None:
        self._transport.close()

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "codec": "AMBE+2 3600x2450",
            "product_id": self.product_id,
            "frames_encoded": self.frames_encoded,
            "experimental": True,
        }


# --------------------------------------------------------------------- factory

def normalize_vocoder_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    settings = settings or {}
    backend = str(settings.get("vocoder") or "software").strip().lower()
    if backend not in VOCODER_BACKENDS:
        raise VoiceSessionConfigurationError(f"Unsupported AMBE vocoder backend: {backend}")
    return {
        "vocoder": backend,
        "vocoder_device": str(settings.get("vocoder_device") or "/dev/ttyUSB0"),
        "vocoder_baud": int(settings.get("vocoder_baud") or 460800),
        "vocoder_host": str(settings.get("vocoder_host") or "127.0.0.1"),
        "vocoder_port": int(settings.get("vocoder_port") or 2460),
        "vocoder_gain_db": float(settings.get("vocoder_gain_db") or 0.0),
    }


def create_ambe_encoder(settings: dict[str, Any] | None, *, dstar: bool = False):
    options = normalize_vocoder_settings(settings)
    backend = options["vocoder"]
    if backend == "software":
        return SoftwareAmbeEncoder(dstar=dstar, gain_db=options["vocoder_gain_db"])
    if dstar:
        raise VoiceSessionConfigurationError("D-Star with a DVSI chip is not implemented yet")
    if backend == "dv3000_serial":
        transport = _SerialTransport(options["vocoder_device"], options["vocoder_baud"])
        return Dv3000AmbeEncoder(transport, name=backend)
    transport = _UdpTransport(options["vocoder_host"], options["vocoder_port"])
    return Dv3000AmbeEncoder(transport, name=backend)


def ambe_vocoder_status(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cheap readiness check (does not open hardware)."""
    try:
        options = normalize_vocoder_settings(settings)
    except VoiceSessionConfigurationError as error:
        return {"available": False, "backend": None, "error": str(error)}
    backend = options["vocoder"]
    if backend == "software":
        result = _SoftwareLibrary.status()
        result["backend"] = backend
        return result
    if backend == "dv3000_serial":
        device = options["vocoder_device"]
        exists = os.path.exists(device)
        return {
            "available": exists,
            "backend": backend,
            "device": device,
            "experimental": True,
            "error": None if exists else f"Serial device {device} not found",
        }
    return {
        "available": True,
        "backend": backend,
        "host": options["vocoder_host"],
        "port": options["vocoder_port"],
        "experimental": True,
        "error": None,
    }
