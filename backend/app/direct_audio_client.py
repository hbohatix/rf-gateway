"""Continuous PCM input for user-owned or explicitly authorized HTTP audio streams.

Not a Broadcastify login, HLS token scraper, or proxy. Requires a direct
media endpoint and permission to use/retransmit the underlying content.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit


CHUNK_BYTES = 320  # 20 ms, signed 16-bit mono, 8 kHz
QUEUE_CAPACITY = 125
BLOCKED_HOST_SUFFIXES = ("broadcastify.com", "bcfy.io", "radioreference.com")


def validate_direct_audio_url(url: str) -> str:
    value = (url or "").strip()
    if not value or len(value) > 2048:
        raise ValueError("Direct audio URL must be 1-2048 characters")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise ValueError("Invalid direct audio URL") from error

    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or not host:
        raise ValueError("Direct audio requires an http:// or https:// media URL")
    if parts.username or parts.password or parts.fragment:
        raise ValueError("Credentials in URLs and URL fragments are not supported")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("Invalid direct audio port")
    if any(host == suffix or host.endswith("." + suffix)
           for suffix in BLOCKED_HOST_SUFFIXES):
        raise ValueError(
            "Broadcastify feeds need separately licensed programmatic access; "
            "use a stream you own or are authorized to integrate"
        )
    return value


class DirectAudioStream:
    def __init__(self, url: str, ffmpeg_path: str) -> None:
        self.url = validate_direct_audio_url(url)
        self.ffmpeg_path = ffmpeg_path
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=QUEUE_CAPACITY)
        self._lock = threading.Lock()
        self._attempts = 0
        self._received_chunks = 0
        self._dropped_chunks = 0
        self._last_pcm_at: float | None = None
        self._error: str | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive()
                    and not self._stop.is_set())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="direct-audio-ffmpeg"
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                self._attempts += 1
                self._error = None
            command = [
                self.ffmpeg_path, "-nostdin", "-hide_banner",
                "-loglevel", "error", "-rw_timeout", "10000000",
                "-re", "-i", self.url, "-vn", "-ac", "1", "-ar", "8000",
                "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1",
            ]
            try:
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                with self._lock:
                    self._process = process
                assert process.stdout is not None
                while not self._stop.is_set():
                    chunk = process.stdout.read(CHUNK_BYTES)
                    if len(chunk) != CHUNK_BYTES:
                        break
                    with self._lock:
                        self._received_chunks += 1
                        self._last_pcm_at = time.monotonic()
                    try:
                        self._queue.put_nowait(chunk)
                    except queue.Full:
                        try:
                            self._queue.get_nowait()
                        except queue.Empty:
                            pass
                        with self._lock:
                            self._dropped_chunks += 1
                        try:
                            self._queue.put_nowait(chunk)
                        except queue.Full:
                            pass
                if not self._stop.is_set():
                    with self._lock:
                        self._error = "Audio stream ended or decoder disconnected"
            except OSError as error:
                with self._lock:
                    self._error = f"Unable to start FFmpeg: {error}"
            finally:
                with self._lock:
                    process = self._process
                    self._process = None
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2.0)
                    if process.stdout:
                        process.stdout.close()
            if self._stop.wait(2.0):
                break

    def read_chunk(self, timeout_seconds: float = 0.5) -> bytes:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        try:
            return self._queue.get(timeout=timeout_seconds)
        except queue.Empty:
            return b""

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "transport": "direct_http_ffmpeg",
                "decoder": "ffmpeg_continuous",
                "sample_rate": 8000,
                "channels": 1,
                "chunk_duration_ms": 20,
                "chunk_bytes": CHUNK_BYTES,
                "queue_size": self._queue.qsize(),
                "attempts": self._attempts,
                "chunks_enqueued": self._received_chunks,
                "chunks_dropped": self._dropped_chunks,
                "last_pcm_seconds_ago": (
                    round(time.monotonic() - self._last_pcm_at, 1)
                    if self._last_pcm_at else None
                ),
                "error": self._error,
            }

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None


class DirectAudioClient:
    sample_rate = 8000
    chunk_duration_ms = 20
    chunk_bytes = CHUNK_BYTES

    def __init__(self) -> None:
        self.ffmpeg_path = shutil.which("ffmpeg")

    def open_stream(self, url: str) -> DirectAudioStream:
        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg is required for direct audio")
        stream = DirectAudioStream(url, self.ffmpeg_path)
        stream.start()
        return stream


direct_audio_client = DirectAudioClient()
