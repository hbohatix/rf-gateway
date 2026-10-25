"""Shared building blocks for the voice transmit sessions."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol


PCM_SAMPLE_RATE = 8000
PCM_SAMPLES_PER_FRAME = 160
PCM_BYTES_PER_FRAME = PCM_SAMPLES_PER_FRAME * 2  # 20 ms of S16LE mono
FRAME_SECONDS = 0.020


class VoiceSessionError(RuntimeError):
    """Base error for voice sessions."""


class VoiceSessionConfigurationError(VoiceSessionError):
    """Mode settings or local dependencies are not usable."""


class VoiceSessionInputError(VoiceSessionError):
    """The supplied PCM is not 8 kHz mono S16LE."""


class VoiceSession(Protocol):
    """Interface shared with :class:`app.p25_streaming_session.P25StreamingSession`."""

    @property
    def active(self) -> bool: ...

    def start(self) -> dict[str, Any]: ...

    def feed_pcm(self, pcm: bytes) -> dict[str, Any]: ...

    def end(self) -> dict[str, Any]: ...

    def close(self) -> None: ...

    def status(self) -> dict[str, Any]: ...


def validate_pcm(pcm: bytes | bytearray) -> bytes:
    if not isinstance(pcm, (bytes, bytearray)):
        raise VoiceSessionInputError("PCM must be bytes")
    data = bytes(pcm)
    if len(data) % 2:
        raise VoiceSessionInputError("PCM is not aligned to 16-bit samples")
    return data


class PcmFramer:
    """Collects arbitrary PCM byte chunks into 20 ms frames."""

    def __init__(self) -> None:
        self._pending = bytearray()

    def push(self, pcm: bytes) -> list[bytes]:
        self._pending.extend(pcm)
        frames = []
        while len(self._pending) >= PCM_BYTES_PER_FRAME:
            frames.append(bytes(self._pending[:PCM_BYTES_PER_FRAME]))
            del self._pending[:PCM_BYTES_PER_FRAME]
        return frames

    def flush(self) -> bytes | None:
        """Return the zero-padded remainder (or ``None`` when empty)."""
        if not self._pending:
            return None
        frame = bytes(self._pending) + bytes(PCM_BYTES_PER_FRAME - len(self._pending))
        self._pending.clear()
        return frame

    def clear(self) -> None:
        self._pending.clear()


class Pacer:
    """Keeps network handoff at real-time pace without accumulating drift."""

    def __init__(self, interval_seconds: float, *, max_lag_seconds: float = 0.5) -> None:
        self.interval = float(interval_seconds)
        self.max_lag = float(max_lag_seconds)
        self._next_at: float | None = None

    def reset(self) -> None:
        self._next_at = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._next_at is None or now - self._next_at > self.max_lag:
            # First packet, or the source stalled: restart the clock instead of bursting.
            self._next_at = now
        delay = self._next_at - now
        if delay > 0:
            time.sleep(delay)
        self._next_at += self.interval


@dataclass
class UdpEndpointStats:
    datagrams_sent: int = 0
    bytes_sent: int = 0
    errors: int = 0
    last_error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "datagrams_sent": self.datagrams_sent,
            "bytes_sent": self.bytes_sent,
            "errors": self.errors,
            "last_error": self.last_error,
        }


@dataclass
class UdpEndpoint:
    """Bound UDP socket used to talk to one MMDVM-Host network port.

    MMDVM-Host only accepts datagrams from the configured gateway address
    and port, so the socket is always bound to ``local_port``.
    """

    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    stats: UdpEndpointStats = field(default_factory=UdpEndpointStats)
    _socket: socket.socket | None = None
    _lock: RLock = field(default_factory=RLock)

    @property
    def is_open(self) -> bool:
        return self._socket is not None

    def open(self) -> None:
        with self._lock:
            if self._socket is not None:
                return
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self.local_address, int(self.local_port)))
                sock.setblocking(False)
            except OSError as error:
                sock.close()
                raise VoiceSessionError(
                    f"Unable to bind UDP {self.local_address}:{self.local_port}: {error}"
                ) from error
            self._socket = sock

    def close(self) -> None:
        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.close()
                finally:
                    self._socket = None

    def send(self, payload: bytes) -> int:
        with self._lock:
            if self._socket is None:
                raise VoiceSessionError("UDP endpoint is not open")
            try:
                sent = self._socket.sendto(payload, (self.remote_address, int(self.remote_port)))
            except OSError as error:
                self.stats.errors += 1
                self.stats.last_error = str(error)
                raise VoiceSessionError(f"UDP send failed: {error}") from error
            self.stats.datagrams_sent += 1
            self.stats.bytes_sent += sent
            return sent

    def drain(self) -> int:
        """Discard anything MMDVM-Host sent back (pings, RF traffic)."""
        drained = 0
        with self._lock:
            if self._socket is None:
                return 0
            while True:
                try:
                    data = self._socket.recv(2048)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    break
                if not data:
                    break
                drained += 1
        return drained

    def status(self) -> dict[str, Any]:
        result = {
            "open": self.is_open,
            "local_address": self.local_address,
            "local_port": int(self.local_port),
            "mmdvm_address": self.remote_address,
            "mmdvm_port": int(self.remote_port),
        }
        result.update(self.stats.status())
        return result


def utc_timestamp() -> float:
    return time.time()
