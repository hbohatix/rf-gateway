from __future__ import annotations

import json
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from collections import deque

from dataclasses import (
    dataclass,
)

from typing import (
    Any,
)

from app.audio_decoder import (
    AudioDecoderError,
    DecodedAudio,
    audio_decoder,
)


DEFAULT_BASE_URL = (
    "https://www.broadcastify.com"
)

DEFAULT_TIMEOUT_SECONDS = 15.0

DEFAULT_SAMPLE_RATE = 8000

DEFAULT_CHANNELS = 1

DEFAULT_SAMPLE_WIDTH_BYTES = 2

DEFAULT_SAMPLE_FORMAT = "s16le"

DEFAULT_CHUNK_DURATION_MS = 20

DEFAULT_BEACON_INTERVAL_SECONDS = 60.0

DEFAULT_MANIFEST_POLL_SECONDS = 1.0

DEFAULT_READ_TIMEOUT_SECONDS = 5.0

DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/152.0.0.0 "
    "Safari/537.36"
)

DEFAULT_HLS_REFERER = (
    "https://www.broadcastify.com/"
)

DEFAULT_HLS_ORIGIN = (
    "https://www.broadcastify.com"
)

DEFAULT_HLS_ACCEPT_LANGUAGE = (
    "en-US,en;q=0.9"
)

DEFAULT_SEC_CH_UA = (
    '"Chromium";v="152", '
    '"Google Chrome";v="152", '
    '"Not_A Brand";v="99"'
)

MAX_PAGE_BYTES = (
    2
    * 1024
    * 1024
)

MAX_TRANSPORT_ERRORS = 100

MAX_SEEN_SEGMENTS = 4096

MAX_PCM_QUEUE_CHUNKS = 1500


class BroadcastifyLiveAudioError(
    RuntimeError
):
    pass


class BroadcastifyLiveAudioConfigurationError(
    BroadcastifyLiveAudioError
):
    pass


class BroadcastifyLiveAudioHTTPError(
    BroadcastifyLiveAudioError
):
    def __init__(
        self,
        status_code: int,
        message: str,
        response_body:
            str
            | None = None,
    ) -> None:
        super().__init__(
            message
        )

        self.status_code = int(
            status_code
        )

        self.response_body = (
            response_body
        )


class BroadcastifyLiveAudioStreamError(
    BroadcastifyLiveAudioError
):
    pass


@dataclass(
    frozen=True,
)
class BroadcastifyLiveAudioSession:
    feed_id: int

    page_url: str

    hls_url: str

    session_id: str

    beacon_url: str

    fleet: str


    @property
    def signed_hls_url(
        self,
    ) -> str:
        separator = (
            "&"
            if "?" in self.hls_url
            else "?"
        )

        return (
            self.hls_url
            + separator
            + urllib.parse.urlencode(
                {
                    "s":
                        self.session_id,
                }
            )
        )


    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "feed_id":
                self.feed_id,

            "page_url":
                self.page_url,

            "hls_url":
                self.hls_url,

            "session_id_present":
                bool(
                    self.session_id
                ),

            "beacon_url":
                self.beacon_url,

            "fleet":
                self.fleet,

            "signed_hls_url_ready":
                bool(
                    self.hls_url
                    and
                    self.session_id
                ),
        }


@dataclass(
    frozen=True,
)
class HLSSegment:
    sequence: int

    duration_seconds: float

    uri: str

    url: str


@dataclass(
    frozen=True,
)
class HLSManifest:
    media_sequence: int

    target_duration: float

    segments: list[HLSSegment]


def _decode_js_string(
    value: str,
) -> str:
    try:
        return json.loads(
            '"'
            + value
            + '"'
        )

    except json.JSONDecodeError:
        return (
            value
            .replace(
                r"\/",
                "/",
            )
            .replace(
                r"\\",
                "\\",
            )
        )


class BroadcastifyLiveAudioClient:
    def __init__(
        self,
        *,
        curl_path:
            str
            | None = None,
        timeout_seconds: float = (
            DEFAULT_TIMEOUT_SECONDS
        ),
        sample_rate: int = (
            DEFAULT_SAMPLE_RATE
        ),
        channels: int = (
            DEFAULT_CHANNELS
        ),
        chunk_duration_ms: int = (
            DEFAULT_CHUNK_DURATION_MS
        ),
    ) -> None:
        resolved_curl = (
            curl_path
            or
            shutil.which(
                "curl"
            )
        )


        if not resolved_curl:
            raise (
                BroadcastifyLiveAudioConfigurationError(
                    (
                        "curl executable "
                        "was not found"
                    )
                )
            )


        if timeout_seconds <= 0:
            raise ValueError(
                (
                    "timeout_seconds must "
                    "be greater than zero"
                )
            )


        if sample_rate != 8000:
            raise ValueError(
                (
                    "Broadcastify Live Audio "
                    "currently requires "
                    "8000 Hz output"
                )
            )


        if channels != 1:
            raise ValueError(
                (
                    "Broadcastify Live Audio "
                    "currently requires "
                    "mono output"
                )
            )


        if chunk_duration_ms <= 0:
            raise ValueError(
                (
                    "chunk_duration_ms must "
                    "be greater than zero"
                )
            )


        self.curl_path = (
            resolved_curl
        )

        self.timeout_seconds = float(
            timeout_seconds
        )

        self.sample_rate = int(
            sample_rate
        )

        self.channels = int(
            channels
        )

        self.chunk_duration_ms = int(
            chunk_duration_ms
        )


    @property
    def chunk_samples(
        self,
    ) -> int:
        return int(
            (
                self.sample_rate
                *
                self.chunk_duration_ms
            )
            /
            1000
        )


    @property
    def chunk_bytes(
        self,
    ) -> int:
        return (
            self.chunk_samples
            *
            self.channels
            *
            DEFAULT_SAMPLE_WIDTH_BYTES
        )


    def _headers(
        self,
        *,
        accept: str,
    ) -> dict[str, str]:
        return {
            "Accept":
                accept,

            "User-Agent":
                DEFAULT_BROWSER_USER_AGENT,
        }


    def _read_http_body(
        self,
        request:
            urllib.request.Request,
        *,
        max_bytes: int | None = None,
    ) -> tuple[
        bytes,
        dict[str, str],
        str,
    ]:
        try:
            with urllib.request.urlopen(
                request,
                timeout=(
                    self.timeout_seconds
                ),
            ) as response:
                if max_bytes is None:
                    body = (
                        response.read()
                    )

                else:
                    body = (
                        response.read(
                            max_bytes
                        )
                    )

                return (
                    body,
                    dict(
                        response.headers
                    ),
                    response.geturl(),
                )


        except urllib.error.HTTPError as error:
            try:
                body = error.read()

            except Exception:
                body = b""


            raise (
                BroadcastifyLiveAudioHTTPError(
                    status_code=(
                        error.code
                    ),

                    message=(
                        "Broadcastify Live Audio "
                        f"returned HTTP {error.code}"
                    ),

                    response_body=(
                        body.decode(
                            "utf-8",
                            errors="replace",
                        )
                        if body
                        else None
                    ),
                )
            ) from error


        except urllib.error.URLError as error:
            raise (
                BroadcastifyLiveAudioError(
                    (
                        "Broadcastify Live Audio "
                        "connection failed: "
                        f"{error.reason}"
                    )
                )
            ) from error


        except TimeoutError as error:
            raise (
                BroadcastifyLiveAudioError(
                    (
                        "Broadcastify Live Audio "
                        "request timed out"
                    )
                )
            ) from error


    def _normalize_feed_id(
        self,
        feed_id: int,
    ) -> int:
        try:
            normalized = int(
                feed_id
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "feed_id must be an integer"
            ) from error


        if normalized <= 0:
            raise ValueError(
                (
                    "feed_id must be "
                    "greater than zero"
                )
            )


        return normalized


    def build_feed_page_url(
        self,
        feed_id: int,
    ) -> str:
        normalized = (
            self._normalize_feed_id(
                feed_id
            )
        )

        return (
            DEFAULT_BASE_URL
            + "/listen/feed/"
            + str(
                normalized
            )
        )


    def fetch_feed_page(
        self,
        feed_id: int,
    ) -> str:
        page_url = (
            self.build_feed_page_url(
                feed_id
            )
        )

        request = (
            urllib.request.Request(
                page_url,
                headers=(
                    self._headers(
                        accept=(
                            "text/html,"
                            "application/xhtml+xml"
                        ),
                    )
                ),
            )
        )

        body, _headers, _final_url = (
            self._read_http_body(
                request,
                max_bytes=(
                    MAX_PAGE_BYTES
                ),
            )
        )

        return (
            body.decode(
                "utf-8",
                errors="replace",
            )
        )


    def _extract_integer_option(
        self,
        page: str,
        name: str,
    ) -> int | None:
        pattern = re.compile(
            (
                r"\b"
                + re.escape(
                    name
                )
                + r"\s*:\s*"
                + r"([0-9]+)"
            ),
            flags=re.IGNORECASE,
        )

        match = pattern.search(
            page
        )

        if not match:
            return None


        try:
            return int(
                match.group(
                    1
                )
            )

        except ValueError:
            return None


    def _extract_double_quoted_option(
        self,
        page: str,
        name: str,
    ) -> str | None:
        pattern = re.compile(
            (
                r"\b"
                + re.escape(
                    name
                )
                + r'\s*:\s*"'
                + r'((?:\\.|[^"\\])*)'
                + r'"'
            ),
            flags=re.IGNORECASE,
        )

        match = pattern.search(
            page
        )

        if not match:
            return None


        return (
            _decode_js_string(
                match.group(
                    1
                )
            )
            .strip()
        )


    def _extract_single_quoted_option(
        self,
        page: str,
        name: str,
    ) -> str | None:
        pattern = re.compile(
            (
                r"\b"
                + re.escape(
                    name
                )
                + r"\s*:\s*'"
                + r"((?:\\.|[^'\\])*)"
                + r"'"
            ),
            flags=re.IGNORECASE,
        )

        match = pattern.search(
            page
        )

        if not match:
            return None


        return (
            match.group(
                1
            )
            .replace(
                r"\/",
                "/",
            )
            .strip()
        )


    def _extract_string_option(
        self,
        page: str,
        name: str,
    ) -> str | None:
        return (
            self._extract_double_quoted_option(
                page,
                name,
            )
            or
            self._extract_single_quoted_option(
                page,
                name,
            )
        )


    def _detect_fleet(
        self,
        hls_url: str,
    ) -> str:
        host = (
            urllib.parse.urlparse(
                hls_url
            )
            .hostname
            or ""
        ).lower()


        if host.startswith(
            "hls-o1."
        ):
            return "oci"


        if host.startswith(
            "hls."
        ):
            return "cf"


        return "other"


    def resolve_session(
        self,
        feed_id: int,
    ) -> BroadcastifyLiveAudioSession:
        normalized_feed_id = (
            self._normalize_feed_id(
                feed_id
            )
        )

        page_url = (
            self.build_feed_page_url(
                normalized_feed_id
            )
        )

        page = (
            self.fetch_feed_page(
                normalized_feed_id
            )
        )

        page_feed_id = (
            self._extract_integer_option(
                page,
                "feedId",
            )
        )


        if (
            page_feed_id
            is not None
            and
            page_feed_id
            != normalized_feed_id
        ):
            raise (
                BroadcastifyLiveAudioError(
                    (
                        "Broadcastify page returned "
                        "a different feedId"
                    )
                )
            )


        hls_url = (
            self._extract_string_option(
                page,
                "hlsUrl",
            )
            or ""
        )

        session_id = (
            self._extract_string_option(
                page,
                "sessionId",
            )
            or ""
        )

        beacon_url = (
            self._extract_string_option(
                page,
                "beaconUrl",
            )
            or ""
        )


        if not hls_url:
            raise (
                BroadcastifyLiveAudioError(
                    (
                        "Broadcastify feed page "
                        "does not contain hlsUrl"
                    )
                )
            )


        if not session_id:
            raise (
                BroadcastifyLiveAudioError(
                    (
                        "Broadcastify feed page "
                        "does not contain sessionId"
                    )
                )
            )


        if not beacon_url:
            raise (
                BroadcastifyLiveAudioError(
                    (
                        "Broadcastify feed page "
                        "does not contain beaconUrl"
                    )
                )
            )


        return (
            BroadcastifyLiveAudioSession(
                feed_id=(
                    normalized_feed_id
                ),

                page_url=(
                    page_url
                ),

                hls_url=(
                    hls_url
                ),

                session_id=(
                    session_id
                ),

                beacon_url=(
                    beacon_url
                ),

                fleet=(
                    self._detect_fleet(
                        hls_url
                    )
                ),
            )
        )


    def _curl_command(
        self,
        url: str,
    ) -> list[str]:
        return [
            self.curl_path,

            "--silent",

            "--show-error",

            "--fail",

            "--http2",

            "--location",

            "--connect-timeout",
            str(
                int(
                    self.timeout_seconds
                )
            ),

            "--max-time",
            str(
                int(
                    self.timeout_seconds
                )
            ),

            "--user-agent",
            DEFAULT_BROWSER_USER_AGENT,

            "--referer",
            DEFAULT_HLS_REFERER,

            "--header",
            "Accept: */*",

            "--header",
            (
                "Accept-Language: "
                + DEFAULT_HLS_ACCEPT_LANGUAGE
            ),

            "--header",
            (
                "Origin: "
                + DEFAULT_HLS_ORIGIN
            ),

            "--header",
            "Sec-Fetch-Dest: empty",

            "--header",
            "Sec-Fetch-Mode: cors",

            "--header",
            "Sec-Fetch-Site: same-site",

            "--header",
            (
                "sec-ch-ua: "
                + DEFAULT_SEC_CH_UA
            ),

            "--header",
            "sec-ch-ua-mobile: ?0",

            "--header",
            (
                'sec-ch-ua-platform: '
                '"Windows"'
            ),

            url,
        ]


    def curl_fetch(
        self,
        url: str,
    ) -> bytes:
        try:
            result = (
                subprocess.run(
                    self._curl_command(
                        url
                    ),
                    stdout=(
                        subprocess.PIPE
                    ),
                    stderr=(
                        subprocess.PIPE
                    ),
                    check=False,
                    timeout=(
                        self.timeout_seconds
                        + 2.0
                    ),
                )
            )

        except subprocess.TimeoutExpired as error:
            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "curl HLS request "
                        "timed out"
                    )
                )
            ) from error


        except OSError as error:
            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "Unable to execute curl: "
                        f"{error}"
                    )
                )
            ) from error


        if result.returncode != 0:
            stderr = (
                result.stderr
                .decode(
                    "utf-8",
                    errors="replace",
                )
                .strip()
            )

            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "curl HLS request failed"
                        +
                        (
                            ": "
                            + stderr
                            if stderr
                            else ""
                        )
                    )
                )
            )


        return bytes(
            result.stdout
        )


    def fetch_manifest(
        self,
        session:
            BroadcastifyLiveAudioSession,
    ) -> HLSManifest:
        raw = (
            self.curl_fetch(
                session.signed_hls_url
            )
        )

        text = (
            raw.decode(
                "utf-8",
                errors="replace",
            )
        )


        if not text.lstrip().startswith(
            "#EXTM3U"
        ):
            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "Broadcastify HLS response "
                        "is not an M3U8 playlist"
                    )
                )
            )


        media_sequence = 0

        target_duration = 4.0

        pending_duration = 0.0

        segments: list[
            HLSSegment
        ] = []


        for raw_line in (
            text.splitlines()
        ):
            line = (
                raw_line.strip()
            )

            if not line:
                continue


            if line.startswith(
                "#EXT-X-MEDIA-SEQUENCE:"
            ):
                try:
                    media_sequence = int(
                        line.split(
                            ":",
                            1,
                        )[1]
                    )

                except ValueError:
                    media_sequence = 0

                continue


            if line.startswith(
                "#EXT-X-TARGETDURATION:"
            ):
                try:
                    target_duration = float(
                        line.split(
                            ":",
                            1,
                        )[1]
                    )

                except ValueError:
                    target_duration = 4.0

                continue


            if line.startswith(
                "#EXTINF:"
            ):
                try:
                    pending_duration = float(
                        line.split(
                            ":",
                            1,
                        )[1]
                        .split(
                            ",",
                            1,
                        )[0]
                    )

                except ValueError:
                    pending_duration = 0.0

                continue


            if line.startswith(
                "#"
            ):
                continue


            sequence = (
                media_sequence
                +
                len(
                    segments
                )
            )

            segments.append(
                HLSSegment(
                    sequence=(
                        sequence
                    ),

                    duration_seconds=(
                        pending_duration
                    ),

                    uri=line,

                    url=(
                        urllib.parse.urljoin(
                            session.hls_url,
                            line,
                        )
                    ),
                )
            )

            pending_duration = 0.0


        if not segments:
            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "Broadcastify HLS manifest "
                        "contains no segments"
                    )
                )
            )


        return (
            HLSManifest(
                media_sequence=(
                    media_sequence
                ),

                target_duration=(
                    target_duration
                ),

                segments=(
                    segments
                ),
            )
        )


    def decode_segment(
        self,
        segment_data: bytes,
    ) -> DecodedAudio:
        try:
            decoded = (
                audio_decoder
                .decode(
                    segment_data,
                    content_type=(
                        "video/mp2t"
                    ),
                )
            )

        except AudioDecoderError as error:
            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "Unable to decode "
                        "Broadcastify HLS segment: "
                        f"{error}"
                    )
                )
            ) from error


        if (
            decoded.sample_rate
            !=
            self.sample_rate
        ):
            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "Decoded sample rate "
                        "does not match stream "
                        "configuration"
                    )
                )
            )


        if (
            decoded.channels
            !=
            self.channels
        ):
            raise (
                BroadcastifyLiveAudioStreamError(
                    (
                        "Decoded channel count "
                        "does not match stream "
                        "configuration"
                    )
                )
            )


        return decoded


    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> Any:
        body = (
            json.dumps(
                payload,
                separators=(
                    ",",
                    ":",
                ),
            )
            .encode(
                "utf-8"
            )
        )

        request = (
            urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    **self._headers(
                        accept=(
                            "application/json"
                        ),
                    ),

                    "Content-Type":
                        "application/json",
                },
            )
        )

        response_body, _headers, _final_url = (
            self._read_http_body(
                request
            )
        )


        if not response_body:
            return None


        try:
            return json.loads(
                response_body.decode(
                    "utf-8",
                    errors="strict",
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            return None


    def send_beacon(
        self,
        session:
            BroadcastifyLiveAudioSession,
    ) -> float:
        try:
            response = (
                self._post_json(
                    session.beacon_url,
                    {
                        "feedId":
                            session.feed_id,

                        "sessionId":
                            session.session_id,

                        "fleet":
                            session.fleet,
                    },
                )
            )

        except BroadcastifyLiveAudioError:
            return (
                DEFAULT_BEACON_INTERVAL_SECONDS
            )


        next_interval = None


        if isinstance(
            response,
            dict,
        ):
            next_interval = (
                response.get(
                    "next_interval_s"
                )
            )


        try:
            interval = float(
                next_interval
            )

        except (
            TypeError,
            ValueError,
        ):
            interval = (
                DEFAULT_BEACON_INTERVAL_SECONDS
            )


        if interval <= 0:
            interval = (
                DEFAULT_BEACON_INTERVAL_SECONDS
            )


        return interval


    def send_leave_beacon(
        self,
        session:
            BroadcastifyLiveAudioSession,
    ) -> None:
        body = (
            json.dumps(
                {
                    "feedId":
                        session.feed_id,

                    "sessionId":
                        session.session_id,

                    "leave":
                        1,
                },
                separators=(
                    ",",
                    ":",
                ),
            )
            .encode(
                "utf-8"
            )
        )

        request = (
            urllib.request.Request(
                session.beacon_url,
                data=body,
                method="POST",
                headers={
                    **self._headers(
                        accept="*/*",
                    ),

                    "Content-Type":
                        (
                            "text/plain;"
                            "charset=UTF-8"
                        ),
                },
            )
        )


        try:
            self._read_http_body(
                request
            )

        except BroadcastifyLiveAudioError:
            pass


    def open_stream(
        self,
        feed_id: int,
    ) -> "BroadcastifyLiveAudioStream":
        stream = (
            BroadcastifyLiveAudioStream(
                client=self,

                session=(
                    self.resolve_session(
                        feed_id
                    )
                ),
            )
        )

        stream.start()

        return stream


class BroadcastifyLiveAudioStream:
    def __init__(
        self,
        *,
        client:
            BroadcastifyLiveAudioClient,
        session:
            BroadcastifyLiveAudioSession,
    ) -> None:
        self.client = client

        self.session = session

        self._stop_event = (
            threading.Event()
        )

        self._hls_thread: (
            threading.Thread
            | None
        ) = None

        self._beacon_thread: (
            threading.Thread
            | None
        ) = None

        self._pcm_queue: (
            queue.Queue[bytes]
        ) = (
            queue.Queue(
                maxsize=(
                    MAX_PCM_QUEUE_CHUNKS
                )
            )
        )

        self._transport_errors: (
            deque[str]
        ) = (
            deque(
                maxlen=(
                    MAX_TRANSPORT_ERRORS
                )
            )
        )

        self._seen_segments: (
            deque[str]
        ) = deque()

        self._seen_segment_set: (
            set[str]
        ) = set()

        self._manifest_initialized = False

        self._started_at: (
            float
            | None
        ) = None

        self._next_delivery_at: (
            float
            | None
        ) = None

        self._beacon_started = False

        self._manifest_requests = 0

        self._segment_requests = 0

        self._segment_bytes = 0

        self._segments_decoded = 0

        self._decoded_pcm_bytes = 0

        self._chunks_enqueued = 0

        self._chunks_dropped = 0

        self._chunks_read = 0

        self._pcm_bytes_read = 0

        self._last_media_sequence: (
            int
            | None
        ) = None

        self._last_segment_sequence: (
            int
            | None
        ) = None

        self._last_segment_duration: (
            float
            | None
        ) = None


    @property
    def running(
        self,
    ) -> bool:
        return bool(
            self._hls_thread
            is not None
            and
            self._hls_thread.is_alive()
            and
            not self._stop_event.is_set()
        )


    def _remember_segment(
        self,
        url: str,
    ) -> None:
        if (
            url
            in
            self._seen_segment_set
        ):
            return


        while (
            len(
                self._seen_segments
            )
            >=
            MAX_SEEN_SEGMENTS
        ):
            old = (
                self._seen_segments
                .popleft()
            )

            self._seen_segment_set.discard(
                old
            )


        self._seen_segments.append(
            url
        )

        self._seen_segment_set.add(
            url
        )


    def _queue_chunk(
        self,
        chunk: bytes,
    ) -> None:
        if not chunk:
            return


        try:
            self._pcm_queue.put_nowait(
                chunk
            )

            self._chunks_enqueued += 1

            return

        except queue.Full:
            pass


        try:
            self._pcm_queue.get_nowait()

            self._chunks_dropped += 1

        except queue.Empty:
            pass


        try:
            self._pcm_queue.put_nowait(
                chunk
            )

            self._chunks_enqueued += 1

        except queue.Full:
            self._chunks_dropped += 1


    def _queue_decoded_audio(
        self,
        decoded: DecodedAudio,
    ) -> None:
        pcm = (
            decoded.pcm
        )

        chunk_bytes = (
            self.client
            .chunk_bytes
        )


        for offset in range(
            0,
            len(
                pcm
            ),
            chunk_bytes,
        ):
            chunk = (
                pcm[
                    offset:
                    offset
                    + chunk_bytes
                ]
            )


            if (
                len(
                    chunk
                )
                !=
                chunk_bytes
            ):
                break


            self._queue_chunk(
                bytes(
                    chunk
                )
            )


    def _process_segment(
        self,
        segment: HLSSegment,
    ) -> None:
        data = (
            self.client
            .curl_fetch(
                segment.url
            )
        )


        if not data:
            return


        self._segment_requests += 1

        self._segment_bytes += len(
            data
        )

        decoded = (
            self.client
            .decode_segment(
                data
            )
        )

        self._segments_decoded += 1

        self._decoded_pcm_bytes += (
            decoded.size_bytes
        )

        self._last_segment_sequence = (
            segment.sequence
        )

        self._last_segment_duration = (
            decoded.duration_seconds
        )

        self._queue_decoded_audio(
            decoded
        )


    def _hls_loop(
        self,
    ) -> None:
        consecutive_errors = 0


        while not (
            self._stop_event
            .is_set()
        ):
            try:
                manifest = (
                    self.client
                    .fetch_manifest(
                        self.session
                    )
                )

                self._manifest_requests += 1

                self._last_media_sequence = (
                    manifest.media_sequence
                )

                consecutive_errors = 0


                if not (
                    self._manifest_initialized
                ):
                    for segment in (
                        manifest.segments
                    ):
                        self._remember_segment(
                            segment.url
                        )


                    latest = (
                        manifest.segments[
                            -1
                        ]
                    )

                    self._process_segment(
                        latest
                    )

                    self._manifest_initialized = (
                        True
                    )


                else:
                    for segment in (
                        manifest.segments
                    ):
                        if (
                            segment.url
                            in
                            self._seen_segment_set
                        ):
                            continue


                        self._remember_segment(
                            segment.url
                        )

                        self._process_segment(
                            segment
                        )


                poll_seconds = min(
                    max(
                        (
                            manifest
                            .target_duration
                            /
                            4.0
                        ),
                        0.5,
                    ),
                    DEFAULT_MANIFEST_POLL_SECONDS,
                )


            except Exception as error:
                consecutive_errors += 1

                self._transport_errors.append(
                    str(
                        error
                    )
                )

                poll_seconds = min(
                    float(
                        consecutive_errors
                    ),
                    5.0,
                )


            if (
                self._stop_event
                .wait(
                    poll_seconds
                )
            ):
                break


    def _beacon_loop(
        self,
    ) -> None:
        interval = 0.0


        while not (
            self._stop_event
            .is_set()
        ):
            if interval > 0:
                if (
                    self._stop_event
                    .wait(
                        interval
                    )
                ):
                    break


            if (
                self._stop_event
                .is_set()
            ):
                break


            interval = (
                self.client
                .send_beacon(
                    self.session
                )
            )


    def _start_beacon(
        self,
    ) -> None:
        if self._beacon_started:
            return


        self._beacon_started = True

        self._beacon_thread = (
            threading.Thread(
                target=(
                    self._beacon_loop
                ),
                name=(
                    "broadcastify-live-audio-"
                    "beacon"
                ),
                daemon=True,
            )
        )

        self._beacon_thread.start()


    def _pace_delivery(
        self,
    ) -> None:
        interval = (
            self.client
            .chunk_duration_ms
            /
            1000.0
        )

        now = (
            time.monotonic()
        )


        if (
            self._next_delivery_at
            is None
            or
            now
            >
            (
                self._next_delivery_at
                + 1.0
            )
        ):
            self._next_delivery_at = (
                now
            )


        wait_seconds = (
            self._next_delivery_at
            -
            now
        )


        if wait_seconds > 0:
            self._stop_event.wait(
                wait_seconds
            )


        self._next_delivery_at += (
            interval
        )


    def start(
        self,
    ) -> None:
        if self.running:
            return


        self._stop_event.clear()

        self._next_delivery_at = None

        self._beacon_started = False


        self._hls_thread = (
            threading.Thread(
                target=(
                    self._hls_loop
                ),
                name=(
                    "broadcastify-live-audio-"
                    "hls"
                ),
                daemon=True,
            )
        )

        self._hls_thread.start()


    def read_chunk(
        self,
        timeout_seconds: float = (
            DEFAULT_READ_TIMEOUT_SECONDS
        ),
    ) -> bytes:
        if timeout_seconds <= 0:
            raise ValueError(
                (
                    "timeout_seconds must "
                    "be greater than zero"
                )
            )


        try:
            chunk = (
                self._pcm_queue.get(
                    timeout=(
                        timeout_seconds
                    )
                )
            )

        except queue.Empty:
            return b""


        self._pace_delivery()


        self._chunks_read += 1

        self._pcm_bytes_read += len(
            chunk
        )


        if not self._beacon_started:
            self._start_beacon()


        return chunk


    def transport_error_tail(
        self,
    ) -> list[str]:
        return list(
            self._transport_errors
        )


    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "running":
                self.running,

            "transport":
                "curl_http2_hls_segments",

            "decoder":
                "ffmpeg_per_segment",

            "feed_id":
                self.session.feed_id,

            "fleet":
                self.session.fleet,

            "sample_rate":
                self.client.sample_rate,

            "channels":
                self.client.channels,

            "sample_width_bytes":
                DEFAULT_SAMPLE_WIDTH_BYTES,

            "sample_format":
                DEFAULT_SAMPLE_FORMAT,

            "chunk_duration_ms":
                self.client.chunk_duration_ms,

            "chunk_samples":
                self.client.chunk_samples,

            "chunk_bytes":
                self.client.chunk_bytes,

            "queue_size":
                self._pcm_queue.qsize(),

            "queue_capacity":
                MAX_PCM_QUEUE_CHUNKS,

            "manifest_requests":
                self._manifest_requests,

            "segment_requests":
                self._segment_requests,

            "segment_bytes":
                self._segment_bytes,

            "segments_decoded":
                self._segments_decoded,

            "decoded_pcm_bytes":
                self._decoded_pcm_bytes,

            "chunks_enqueued":
                self._chunks_enqueued,

            "chunks_dropped":
                self._chunks_dropped,

            "chunks_read":
                self._chunks_read,

            "pcm_bytes_read":
                self._pcm_bytes_read,

            "last_media_sequence":
                self._last_media_sequence,

            "last_segment_sequence":
                self._last_segment_sequence,

            "last_segment_duration":
                self._last_segment_duration,

            "beacon_started":
                self._beacon_started,

            "uptime_seconds":
                (
                    (
                        time.monotonic()
                        -
                        self._started_at
                    )
                    if (
                        self._started_at
                        is not None
                    )
                    else 0.0
                ),

            "transport_errors":
                self.transport_error_tail(),
        }


    def close(
        self,
    ) -> None:
        self._stop_event.set()


        if (
            self._hls_thread
            is not None
            and
            self._hls_thread.is_alive()
        ):
            self._hls_thread.join(
                timeout=2.0
            )


        if self._beacon_started:
            self.client.send_leave_beacon(
                self.session
            )


        self._hls_thread = None


    def __enter__(
        self,
    ) -> "BroadcastifyLiveAudioStream":
        if not self.running:
            self.start()

        return self


    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()


broadcastify_live_audio_client = (
    BroadcastifyLiveAudioClient()
)