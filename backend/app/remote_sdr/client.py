"""Continuous 8 kHz PCM from a remote SDR.

A remote SDR source is described entirely by its URL, so it fits the
existing source store (``sources.json``) and route setup:

``rtl_tcp://host:1234?freq=145500000&mod=nfm&gain=auto&squelch=auto``
    Raw IQ from an ``rtl_tcp`` server, demodulated here (NFM or AM).

``kiwisdr://host:8073?freq=7100000&mod=lsb``
    Audio from a KiwiSDR (public or private) over its WebSocket API.

``udp://0.0.0.0:7355?format=s16le&rate=48000&channels=1``
``tcp://host:port?format=s16le&rate=48000``
    Raw PCM pushed by GQRX ("UDP audio"), SDR++ (network sink),
    SDRangel, rtl_fm | nc, ... ``udp`` listens locally, ``tcp`` connects.

``http(s)://``, ``rtsp://``, ``rtp://``, ``srt://`` with ``sdr=1``
    Compressed streams from OpenWebRX/Icecast/darkice set-ups (FFmpeg).

Only use receivers and audio you are allowed to retransmit.
"""

from __future__ import annotations

import queue
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit


CHUNK_BYTES = 320  # 20 ms of 8 kHz S16LE mono
QUEUE_CAPACITY = 150

REMOTE_SDR_KINDS = ("rtl_tcp", "kiwisdr", "audio_stream")
AUDIO_STREAM_SCHEMES = ("udp", "tcp", "http", "https", "rtsp", "rtp", "srt")
RAW_PCM_FORMATS = ("s16le", "s16be", "f32le", "u8")
BLOCKED_HOST_SUFFIXES = ("broadcastify.com", "bcfy.io", "radioreference.com")

RTL_TCP_DEFAULT_PORT = 1234
RTL_TCP_IQ_RATE = 240000
RTL_TCP_OFFSET_HZ = 60000  # tune off-centre to keep the DC spike out of the channel
KIWISDR_DEFAULT_PORT = 8073

RTL_TCP_TUNERS = {
    0: "unknown", 1: "E4000", 2: "FC0012", 3: "FC0013", 4: "FC2580", 5: "R820T", 6: "R828D",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RemoteSdrError(RuntimeError):
    pass


# ----------------------------------------------------------------- URL model

@dataclass
class RemoteSdrConfig:
    kind: str
    url: str
    host: str
    port: int | None
    frequency_hz: int | None = None
    modulation: str | None = None
    gain: str = "auto"
    ppm: int = 0
    squelch_db: float | None = None
    bandwidth_hz: int = 12500
    audio_gain: float = 1.0
    pcm_format: str | None = None
    pcm_rate: int | None = None
    pcm_channels: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        if self.kind in ("rtl_tcp", "kiwisdr"):
            freq = f"{(self.frequency_hz or 0) / 1e6:.4f} MHz"
            return f"{self.kind} {self.host}:{self.port} {freq} {str(self.modulation).upper()}"
        return f"{self.kind} {self.url}"

    def public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "host": self.host,
            "port": self.port,
            "frequency_hz": self.frequency_hz,
            "modulation": self.modulation,
            "gain": self.gain,
            "ppm": self.ppm,
            "squelch_db": self.squelch_db,
            "bandwidth_hz": self.bandwidth_hz,
            "audio_gain": self.audio_gain,
            "pcm_format": self.pcm_format,
            "pcm_rate": self.pcm_rate,
            "pcm_channels": self.pcm_channels,
            "description": self.describe(),
        }


def _first(query: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    values = query.get(key)
    if not values:
        return default
    return values[0].strip()


def _parse_frequency(value: str | None) -> int:
    if not value:
        raise ValueError("Remote SDR URL needs freq=<Hz> (or MHz with a decimal point)")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"Invalid frequency: {value}") from error
    # Accept "145.5" (MHz) as well as "145500000" (Hz).
    hz = int(round(number * 1e6)) if number < 10000 else int(round(number))
    if not 10_000 <= hz <= 6_000_000_000:
        raise ValueError("Frequency must be between 10 kHz and 6 GHz")
    return hz


def _parse_squelch(value: str | None) -> float | None:
    if value in (None, "", "auto"):
        return None
    if value in ("off", "open", "none"):
        return -200.0
    try:
        return float(value)
    except ValueError as error:
        raise ValueError("squelch must be auto, off or a dBFS level") from error


def parse_remote_sdr_url(url: str) -> RemoteSdrConfig:
    value = (url or "").strip()
    if not value or len(value) > 2048:
        raise ValueError("Remote SDR URL must be 1-2048 characters")
    # "_" is not valid in a URL scheme (RFC 3986); accept the familiar name anyway.
    if value.lower().startswith("rtl_tcp://"):
        value = "rtl-tcp://" + value[len("rtl_tcp://"):]
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise ValueError("Invalid remote SDR URL") from error
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    query = parse_qs(parts.query, keep_blank_values=False)
    if parts.username or parts.password or parts.fragment:
        raise ValueError("Credentials in URLs and URL fragments are not supported")
    if any(host == s or host.endswith("." + s) for s in BLOCKED_HOST_SUFFIXES):
        raise ValueError("Broadcastify feeds need separately licensed programmatic access")

    try:
        audio_gain = float(_first(query, "audio_gain", "1.0") or 1.0)
    except ValueError as error:
        raise ValueError("audio_gain must be a number") from error
    if not 0 < audio_gain <= 16:
        raise ValueError("audio_gain must be between 0 and 16")

    if scheme in ("rtl-tcp", "rtltcp"):
        if not host:
            raise ValueError("rtl_tcp URL needs a host")
        modulation = (_first(query, "mod", "nfm") or "nfm").lower()
        if modulation not in ("nfm", "am"):
            raise ValueError("rtl_tcp demodulation supports mod=nfm or mod=am")
        gain = (_first(query, "gain", "auto") or "auto").lower()
        if gain != "auto":
            try:
                float(gain)
            except ValueError as error:
                raise ValueError("gain must be auto or a value in dB") from error
        try:
            ppm = int(_first(query, "ppm", "0") or 0)
            bandwidth = int(_first(query, "bw", "12500") or 12500)
        except ValueError as error:
            raise ValueError("ppm and bw must be integers") from error
        if not 3000 <= bandwidth <= 40000:
            raise ValueError("bw must be between 3000 and 40000 Hz")
        config = RemoteSdrConfig(
            kind="rtl_tcp",
            url="",
            host=host,
            port=port or RTL_TCP_DEFAULT_PORT,
            frequency_hz=_parse_frequency(_first(query, "freq")),
            modulation=modulation,
            gain=gain,
            ppm=ppm,
            squelch_db=_parse_squelch(_first(query, "squelch")),
            bandwidth_hz=bandwidth,
            audio_gain=audio_gain,
        )
        params = {"freq": config.frequency_hz, "mod": modulation, "gain": gain}
        if ppm:
            params["ppm"] = ppm
        if bandwidth != 12500:
            params["bw"] = bandwidth
        squelch = _first(query, "squelch")
        if squelch:
            params["squelch"] = squelch
        if audio_gain != 1.0:
            params["audio_gain"] = audio_gain
        config.url = f"rtl_tcp://{host}:{config.port}?{urlencode(params)}"
        return config

    if scheme in ("kiwisdr", "kiwi"):
        if not host:
            raise ValueError("KiwiSDR URL needs a host")
        modulation = (_first(query, "mod", "am") or "am").lower()
        if modulation not in ("am", "amn", "nbfm", "usb", "lsb", "cw"):
            raise ValueError("KiwiSDR mod must be am, amn, nbfm, usb, lsb or cw")
        config = RemoteSdrConfig(
            kind="kiwisdr",
            url="",
            host=host,
            port=port or KIWISDR_DEFAULT_PORT,
            frequency_hz=_parse_frequency(_first(query, "freq")),
            modulation=modulation,
            squelch_db=_parse_squelch(_first(query, "squelch")),
            audio_gain=audio_gain,
        )
        if config.frequency_hz > 32_000_000:
            raise ValueError("KiwiSDR receivers cover 0-32 MHz")
        params = {"freq": config.frequency_hz, "mod": modulation}
        squelch = _first(query, "squelch")
        if squelch:
            params["squelch"] = squelch
        if audio_gain != 1.0:
            params["audio_gain"] = audio_gain
        config.url = f"kiwisdr://{host}:{config.port}?{urlencode(params)}"
        return config

    if scheme in AUDIO_STREAM_SCHEMES:
        if scheme in ("udp", "tcp", "rtp", "srt") and port is None:
            raise ValueError(f"{scheme}:// audio needs a port")
        if scheme != "udp" and not host:
            raise ValueError("Audio stream URL needs a host")
        pcm_format = _first(query, "format")
        pcm_rate = _first(query, "rate")
        channels = _first(query, "channels", "1")
        if scheme in ("udp", "tcp") and not pcm_format:
            pcm_format = "s16le"
        if pcm_format is not None:
            pcm_format = pcm_format.lower()
            if pcm_format not in RAW_PCM_FORMATS:
                raise ValueError(f"format must be one of {', '.join(RAW_PCM_FORMATS)}")
        try:
            rate = int(pcm_rate) if pcm_rate else (48000 if pcm_format else None)
            channel_count = int(channels or 1)
        except ValueError as error:
            raise ValueError("rate and channels must be integers") from error
        if rate is not None and not 8000 <= rate <= 192000:
            raise ValueError("rate must be 8000-192000 Hz")
        if channel_count not in (1, 2):
            raise ValueError("channels must be 1 or 2")
        config = RemoteSdrConfig(
            kind="audio_stream",
            url=value,
            host=host or "0.0.0.0",
            port=port,
            audio_gain=audio_gain,
            pcm_format=pcm_format,
            pcm_rate=rate,
            pcm_channels=channel_count,
        )
        return config

    raise ValueError(
        "Remote SDR URL must start with rtl_tcp://, kiwisdr://, udp://, tcp://, "
        "http(s)://, rtsp://, rtp:// or srt://"
    )


# ------------------------------------------------------------ base stream

class _BaseStream:
    transport = "remote_sdr"

    def __init__(self, config: RemoteSdrConfig) -> None:
        self.config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=QUEUE_CAPACITY)
        self._lock = threading.Lock()
        self._pending = bytearray()
        self._attempts = 0
        self._chunks = 0
        self._dropped = 0
        self._last_pcm_at: float | None = None
        self._connected = False
        self._error: str | None = None
        self._details: dict[str, Any] = {}

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._supervise, daemon=True, name=f"remote-sdr-{self.config.kind}")
        self._thread.start()

    def _supervise(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                self._attempts += 1
            try:
                self._run_once()
                if not self._stop.is_set():
                    self._set_error("Remote SDR stream ended")
            except Exception as error:  # noqa: BLE001 - reported in status
                self._set_error(str(error) or type(error).__name__)
            finally:
                with self._lock:
                    self._connected = False
            if self._stop.wait(3.0):
                break

    def _run_once(self) -> None:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def _set_error(self, message: str | None) -> None:
        with self._lock:
            self._error = message

    def _set_connected(self, **details: Any) -> None:
        with self._lock:
            self._connected = True
            self._error = None
            self._details.update(details)

    def _emit_pcm(self, pcm: bytes) -> None:
        self._pending.extend(pcm)
        while len(self._pending) >= CHUNK_BYTES:
            chunk = bytes(self._pending[:CHUNK_BYTES])
            del self._pending[:CHUNK_BYTES]
            with self._lock:
                self._chunks += 1
                self._last_pcm_at = time.monotonic()
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                with self._lock:
                    self._dropped += 1
                try:
                    self._queue.put_nowait(chunk)
                except queue.Full:
                    pass

    def read_chunk(self, timeout_seconds: float = 0.5) -> bytes:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        try:
            return self._queue.get(timeout=timeout_seconds)
        except queue.Empty:
            return b""

    def extra_status(self) -> dict[str, Any]:
        return {}

    def status(self) -> dict[str, Any]:
        with self._lock:
            result = {
                "running": self.running,
                "connected": self._connected,
                "transport": self.transport,
                "kind": self.config.kind,
                "receiver": self.config.describe(),
                "sample_rate": 8000,
                "channels": 1,
                "chunk_duration_ms": 20,
                "chunk_bytes": CHUNK_BYTES,
                "queue_size": self._queue.qsize(),
                "attempts": self._attempts,
                "chunks_enqueued": self._chunks,
                "chunks_dropped": self._dropped,
                "last_pcm_seconds_ago": (
                    round(time.monotonic() - self._last_pcm_at, 1) if self._last_pcm_at else None
                ),
                "error": self._error,
                **self._details,
            }
        result.update(self.extra_status())
        return result

    def _interrupt(self) -> None:
        """Unblock the worker (close sockets / processes)."""

    def close(self) -> None:
        self._stop.set()
        self._interrupt()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4.0)
        self._thread = None


# ------------------------------------------------------------------ rtl_tcp

def rtl_tcp_command(command: int, value: int) -> bytes:
    return struct.pack(">BI", command, value & 0xFFFFFFFF)


class RtlTcpStream(_BaseStream):
    transport = "rtl_tcp_iq"

    def __init__(self, config: RemoteSdrConfig) -> None:
        super().__init__(config)
        self._socket: socket.socket | None = None
        self._demod = None

    def _interrupt(self) -> None:
        sock = self._socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _run_once(self) -> None:
        try:
            import numpy as np

            from app.remote_sdr.dsp import IqDemodulator, float_to_pcm16
        except ImportError as error:
            raise RemoteSdrError("rtl_tcp sources need numpy (pip install numpy)") from error

        cfg = self.config
        sock = socket.create_connection((cfg.host, int(cfg.port)), timeout=8.0)
        self._socket = sock
        try:
            header = b""
            while len(header) < 12:
                chunk = sock.recv(12 - len(header))
                if not chunk:
                    raise RemoteSdrError("rtl_tcp closed the connection during handshake")
                header += chunk
            if header[:4] != b"RTL0":
                raise RemoteSdrError("Not an rtl_tcp server (missing RTL0 header)")
            tuner_type, gain_count = struct.unpack(">II", header[4:12])

            center = int(cfg.frequency_hz) - RTL_TCP_OFFSET_HZ
            sock.sendall(rtl_tcp_command(0x02, RTL_TCP_IQ_RATE))
            sock.sendall(rtl_tcp_command(0x05, cfg.ppm))
            if cfg.gain == "auto":
                sock.sendall(rtl_tcp_command(0x03, 0))
                sock.sendall(rtl_tcp_command(0x08, 1))
            else:
                sock.sendall(rtl_tcp_command(0x03, 1))
                sock.sendall(rtl_tcp_command(0x04, int(round(float(cfg.gain) * 10))))
            sock.sendall(rtl_tcp_command(0x01, center))

            self._demod = IqDemodulator(
                iq_rate=RTL_TCP_IQ_RATE,
                offset_hz=RTL_TCP_OFFSET_HZ,
                modulation=str(cfg.modulation),
                channel_bandwidth_hz=cfg.bandwidth_hz,
                squelch_db=cfg.squelch_db,
                audio_gain=cfg.audio_gain,
            )
            self._set_connected(
                tuner=RTL_TCP_TUNERS.get(tuner_type, str(tuner_type)),
                tuner_gain_steps=gain_count,
                iq_rate=RTL_TCP_IQ_RATE,
                center_frequency_hz=center,
            )
            sock.settimeout(5.0)
            block_bytes = RTL_TCP_IQ_RATE * 2 // 25  # 40 ms of IQ
            buffer = bytearray()
            while not self._stop.is_set():
                data = sock.recv(65536)
                if not data:
                    break
                buffer.extend(data)
                if len(buffer) < block_bytes:
                    continue
                usable = len(buffer) - (len(buffer) % 2)
                raw = np.frombuffer(bytes(buffer[:usable]), dtype=np.uint8).astype(np.float32)
                del buffer[:usable]
                raw = (raw - 127.5) / 127.5
                iq = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
                audio = self._demod.process(iq)
                self._emit_pcm(float_to_pcm16(audio))
        finally:
            self._socket = None
            try:
                sock.close()
            except OSError:
                pass

    def extra_status(self) -> dict[str, Any]:
        demod = self._demod
        if demod is None:
            return {}
        return {"squelch": demod.squelch.status(), "modulation": demod.modulation}


# ------------------------------------------------------------------ KiwiSDR

KIWI_FLAG_IQ = 0x08
KIWI_FLAG_COMPRESSED = 0x10

_IMA_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
_IMA_STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
    73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408,
    449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
    9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
)


class ImaAdpcmDecoder:
    """IMA ADPCM as used by KiwiSDR when audio compression is on."""

    def __init__(self) -> None:
        self.index = 0
        self.predictor = 0

    def _nibble(self, code: int) -> int:
        step = _IMA_STEP_TABLE[self.index]
        diff = step >> 3
        if code & 4:
            diff += step
        if code & 2:
            diff += step >> 1
        if code & 1:
            diff += step >> 2
        self.predictor += -diff if code & 8 else diff
        self.predictor = max(-32768, min(32767, self.predictor))
        self.index = max(0, min(88, self.index + _IMA_INDEX_TABLE[code]))
        return self.predictor

    def decode(self, data: bytes):
        import numpy as np

        out = np.empty(len(data) * 2, dtype=np.float32)
        position = 0
        for byte in data:
            out[position] = self._nibble(byte & 0x0F) / 32768.0
            out[position + 1] = self._nibble(byte >> 4) / 32768.0
            position += 2
        return out


def _kiwi_passband(modulation: str) -> tuple[int, int]:
    return {
        "am": (-4900, 4900),
        "amn": (-2500, 2500),
        "nbfm": (-6000, 6000),
        "usb": (300, 2700),
        "lsb": (-2700, -300),
        "cw": (300, 700),
    }.get(modulation, (-4900, 4900))


class KiwiSdrStream(_BaseStream):
    transport = "kiwisdr_websocket"

    def __init__(self, config: RemoteSdrConfig) -> None:
        super().__init__(config)
        self._socket = None
        self._rssi_dbm: float | None = None

    def _interrupt(self) -> None:
        ws = self._socket
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _run_once(self) -> None:
        try:
            import numpy as np
            from websockets.sync.client import connect

            from app.remote_sdr.dsp import OnePoleHighPass, PowerSquelch, Resampler, float_to_pcm16
        except ImportError as error:
            raise RemoteSdrError("KiwiSDR sources need numpy and websockets") from error

        cfg = self.config
        timestamp = int(time.time())
        url = f"ws://{cfg.host}:{cfg.port}/kiwi/{timestamp}/SND"
        with connect(url, open_timeout=8, close_timeout=2, max_size=2 ** 20) as ws:
            self._socket = ws
            send = ws.send
            send("SET auth t=kiwi p=")
            resampler: Resampler | None = None
            adpcm = ImaAdpcmDecoder()
            highpass = OnePoleHighPass(120.0, 8000)
            squelch = PowerSquelch(cfg.squelch_db, auto_margin_db=6.0, hang_blocks=20) if cfg.squelch_db != -200.0 else None
            low, high = _kiwi_passband(str(cfg.modulation))
            configured = False
            last_keepalive = time.monotonic()
            while not self._stop.is_set():
                try:
                    message = ws.recv(timeout=5.0)
                except TimeoutError:
                    message = None
                now = time.monotonic()
                if now - last_keepalive > 5.0:
                    send("SET keepalive")
                    last_keepalive = now
                if message is None:
                    continue
                if isinstance(message, str):
                    message = message.encode("latin-1", "replace")
                tag = message[:3]
                body = message[3:]
                if tag == b"MSG":
                    text = body.decode("utf-8", "replace").strip()
                    params = dict(
                        item.split("=", 1) if "=" in item else (item, "")
                        for item in text.split(" ")
                        if item
                    )
                    if "too_busy" in params or params.get("badp") == "1" or "down" in params:
                        raise RemoteSdrError(f"KiwiSDR refused the connection: {text[:80]}")
                    rate_text = params.get("sample_rate") or params.get("audio_rate")
                    if rate_text and not configured:
                        rate = float(rate_text)
                        resampler = Resampler(rate, 8000)
                        audio_rate = int(round(float(params.get("audio_rate", rate))))
                        send(f"SET AR OK in={audio_rate} out=48000")
                        send("SET squelch=0 max=0")
                        send("SET genattn=0")
                        send("SET gen=0 mix=-1")
                        send("SET ident_user=rf-gateway")
                        send("SET compression=0")
                        send(f"SET mod={cfg.modulation} low_cut={low} high_cut={high} freq={cfg.frequency_hz / 1000:.3f}")
                        send("SET agc=1 hang=0 thresh=-100 slope=6 decay=1000 manGain=50")
                        configured = True
                        self._set_connected(sample_rate_in=rate, url=url.split("/kiwi/")[0])
                    continue
                if tag != b"SND" or resampler is None or len(body) < 7:
                    continue
                flags, _seq = struct.unpack("<BI", body[0:5])
                (smeter,) = struct.unpack(">H", body[5:7])
                self._rssi_dbm = 0.1 * smeter - 127.0
                data = body[7:]
                if flags & KIWI_FLAG_IQ:
                    continue  # IQ mode is never requested
                if flags & KIWI_FLAG_COMPRESSED:
                    samples = adpcm.decode(data)
                else:
                    samples = np.frombuffer(data[: len(data) - len(data) % 2], dtype=">i2").astype(np.float32) / 32768.0
                audio = highpass.process(resampler.process(samples))
                if squelch is not None:
                    level = 10 ** (self._rssi_dbm / 20.0)
                    if not squelch.update(np.full(1, level, dtype=np.float32)):
                        audio = np.zeros_like(audio)
                self._emit_pcm(float_to_pcm16(audio, cfg.audio_gain))
        self._socket = None

    def extra_status(self) -> dict[str, Any]:
        return {"rssi_dbm": None if self._rssi_dbm is None else round(self._rssi_dbm, 1)}


# ---------------------------------------------------------- FFmpeg audio

class AudioStream(_BaseStream):
    transport = "sdr_audio_ffmpeg"

    def __init__(self, config: RemoteSdrConfig, ffmpeg_path: str) -> None:
        super().__init__(config)
        self.ffmpeg_path = ffmpeg_path
        self._process: subprocess.Popen | None = None

    def command(self) -> list[str]:
        cfg = self.config
        command = [self.ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error"]
        url = cfg.url.split("?", 1)[0] if cfg.pcm_format else cfg.url
        if cfg.pcm_format:
            if url.startswith("udp://"):
                host = cfg.host or "0.0.0.0"
                url = f"udp://{host}:{cfg.port}?listen=1&fifo_size=1000000&overrun_nonfatal=1"
            command += ["-f", cfg.pcm_format, "-ar", str(cfg.pcm_rate or 48000), "-ac", str(cfg.pcm_channels)]
        else:
            command += ["-rw_timeout", "10000000"] if url.startswith(("http", "tcp")) else []
            command += ["-re"]
        command += ["-i", url, "-vn", "-ac", "1", "-ar", "8000"]
        if cfg.audio_gain != 1.0:
            command += ["-af", f"volume={cfg.audio_gain}"]
        command += ["-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]
        return command

    def _interrupt(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def _run_once(self) -> None:
        process = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._process = process
        try:
            assert process.stdout is not None
            first = True
            while not self._stop.is_set():
                chunk = process.stdout.read(CHUNK_BYTES)
                if len(chunk) != CHUNK_BYTES:
                    break
                if first:
                    self._set_connected(decoder="ffmpeg")
                    first = False
                self._emit_pcm(chunk)
            if not self._stop.is_set():
                error = b""
                if process.stderr is not None:
                    try:
                        process.terminate()
                        error = process.stderr.read(400)
                    except Exception:
                        pass
                if error:
                    raise RemoteSdrError(error.decode("utf-8", "replace").strip().splitlines()[-1])
        finally:
            self._process = None
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
            for pipe in (process.stdout, process.stderr):
                if pipe:
                    pipe.close()


# ----------------------------------------------------------------- client

class RemoteSdrClient:
    sample_rate = 8000
    chunk_duration_ms = 20
    chunk_bytes = CHUNK_BYTES

    def __init__(self) -> None:
        self.ffmpeg_path = shutil.which("ffmpeg")

    def open_stream(self, url: str):
        config = parse_remote_sdr_url(url)
        if config.kind == "rtl_tcp":
            stream = RtlTcpStream(config)
        elif config.kind == "kiwisdr":
            stream = KiwiSdrStream(config)
        else:
            if not self.ffmpeg_path:
                raise RemoteSdrError("FFmpeg is required for SDR audio streams")
            stream = AudioStream(config, self.ffmpeg_path)
        stream.start()
        return stream


remote_sdr_client = RemoteSdrClient()


# ------------------------------------------------------------------ probe

def _probe_rtl_tcp(config: RemoteSdrConfig) -> dict[str, Any]:
    with socket.create_connection((config.host, int(config.port)), timeout=5.0) as sock:
        sock.settimeout(5.0)
        header = b""
        while len(header) < 12:
            chunk = sock.recv(12 - len(header))
            if not chunk:
                break
            header += chunk
    if header[:4] != b"RTL0" or len(header) < 12:
        return {"reachable": False, "error": "Server did not answer with an rtl_tcp header"}
    tuner_type, gain_count = struct.unpack(">II", header[4:12])
    return {
        "reachable": True,
        "error": None,
        "receiver_info": {"tuner": RTL_TCP_TUNERS.get(tuner_type, str(tuner_type)), "gain_steps": gain_count},
    }


def _probe_kiwisdr(config: RemoteSdrConfig) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://{config.host}:{config.port}/status",
        headers={"User-Agent": "RF-Gateway/0.13"},
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        text = response.read(8192).decode("utf-8", "replace")
    info: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip()
    if not info:
        return {"reachable": False, "error": "No KiwiSDR /status answer"}
    users = info.get("users")
    users_max = info.get("users_max")
    busy = users is not None and users_max is not None and users.isdigit() and users_max.isdigit() and int(users) >= int(users_max)
    return {
        "reachable": info.get("status", "active") in ("active", "private") and not busy,
        "error": "All KiwiSDR channels are busy" if busy else None,
        "receiver_info": {
            "name": info.get("name"),
            "location": info.get("loc"),
            "users": users,
            "users_max": users_max,
            "bands": info.get("bands"),
            "antenna": info.get("antenna"),
        },
    }


def probe_remote_sdr(url: str) -> dict[str, Any]:
    config = parse_remote_sdr_url(url)
    result: dict[str, Any] = {
        "provider": "sdr",
        "source_type": "remote_sdr",
        "canonical_url": config.url,
        "remote_sdr": config.public_dict(),
        "page_name": config.describe(),
        "final_url": config.url,
        "http_status": None,
        "media_type": None,
        "playback_model": "continuous_stream",
        "audio_api_configured": True,
        "playback_state": "configured",
        "probed_at": utc_now(),
    }
    try:
        if config.kind == "rtl_tcp":
            result.update(_probe_rtl_tcp(config))
            try:
                import numpy  # noqa: F401
            except ImportError:
                result.update(audio_api_configured=False, playback_state="numpy_not_installed")
        elif config.kind == "kiwisdr":
            result.update(_probe_kiwisdr(config))
        else:
            configured = bool(shutil.which("ffmpeg"))
            result.update(
                audio_api_configured=configured,
                playback_state="configured" if configured else "ffmpeg_not_installed",
            )
            if config.url.startswith("udp://"):
                # Push stream: the remote SDR sends to us, nothing to probe.
                result.update(reachable=configured, error=None, listening=True)
            elif config.url.startswith(("http://", "https://")):
                request = urllib.request.Request(config.url, headers={"User-Agent": "RF-Gateway/0.13"})
                with urllib.request.urlopen(request, timeout=6) as response:
                    result["http_status"] = response.status
                    result["media_type"] = response.headers.get_content_type()
                result.update(reachable=True, error=None)
            elif config.url.startswith("tcp://"):
                with socket.create_connection((config.host, int(config.port)), timeout=5.0):
                    pass
                result.update(reachable=True, error=None)
            else:
                result.update(reachable=configured, error=None, probe="not_probed")
    except (OSError, urllib.error.URLError, ValueError) as error:
        result.update(reachable=False, error=f"{type(error).__name__}: {error}"[:300])
    return result


def describe_remote_sdr_url(url: str) -> str:
    try:
        return parse_remote_sdr_url(url).describe()
    except ValueError:
        return url

