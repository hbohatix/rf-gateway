from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Event, RLock, Thread
from typing import Any

from app.audio_bridge import (
    AudioBridgeError,
    bridge_decoded_audio,
    get_audio_bridge_capability,
)

from app.audio_decoder import (
    AudioDecoder,
    AudioDecoderError,
    DecodedAudio,
    audio_decoder,
)

from app.broadcastify_calls_client import (
    BroadcastifyCallsClient,
    BroadcastifyCallsConfigurationError,
    BroadcastifyCallsError,
    BroadcastifyCallsHTTPError,
    broadcastify_calls_client,
)

from app.call_queue import (
    CallQueueManager,
    call_queue_manager,
)


DEFAULT_POLL_INTERVAL_SECONDS = 0.25


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def get_call_key(
    call: dict[str, Any],
) -> str | None:
    queue_metadata = (
        call.get(
            "_queue"
        )
        or {}
    )

    call_key = (
        queue_metadata.get(
            "call_key"
        )
    )

    if call_key:
        return str(
            call_key
        )

    group_id = (
        call.get(
            "group_id"
        )
        or
        call.get(
            "groupId"
        )
    )

    ts = (
        call.get(
            "ts"
        )
    )

    if (
        group_id is None
        or
        ts is None
    ):
        return None

    return (
        f"{group_id}:"
        f"{ts}"
    )


def get_group_id(
    call: dict[str, Any],
) -> str | None:
    value = (
        call.get(
            "group_id"
        )
        or
        call.get(
            "groupId"
        )
    )

    if value is None:
        return None

    normalized = (
        str(
            value
        )
        .strip()
    )

    return (
        normalized
        or None
    )


def get_call_ts(
    call: dict[str, Any],
) -> int | None:
    value = (
        call.get(
            "ts"
        )
    )

    if value is None:
        return None

    try:
        timestamp = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if timestamp <= 0:
        return None

    return timestamp


class CallProcessor:
    def __init__(
        self,
        route_id: str,
        protocol: str,
        *,
        client:
            BroadcastifyCallsClient
            | None = None,
        decoder:
            AudioDecoder
            | None = None,
        queue_manager:
            CallQueueManager
            | None = None,
        poll_interval_seconds: float = (
            DEFAULT_POLL_INTERVAL_SECONDS
        ),
    ) -> None:
        if not route_id:
            raise ValueError(
                "route_id cannot be empty"
            )

        normalized_protocol = (
            protocol
            .strip()
            .lower()
        )

        if normalized_protocol not in {
            "fm",
            "dmr",
            "p25",
            "tetra",
        }:
            raise ValueError(
                (
                    "Unsupported protocol: "
                    f"{normalized_protocol}"
                )
            )

        if (
            poll_interval_seconds
            <= 0
        ):
            raise ValueError(
                (
                    "poll_interval_seconds "
                    "must be greater than zero"
                )
            )

        self.route_id = (
            route_id
        )

        self.protocol = (
            normalized_protocol
        )

        self.poll_interval_seconds = (
            float(
                poll_interval_seconds
            )
        )

        self._client = (
            client
            or
            broadcastify_calls_client
        )

        self._decoder = (
            decoder
            or
            audio_decoder
        )

        self._queue_manager = (
            queue_manager
            or
            call_queue_manager
        )

        self._lock = (
            RLock()
        )

        self._stop_event = (
            Event()
        )

        self._thread: (
            Thread
            | None
        ) = None

        self._state = (
            "stopped"
        )

        self._error: str | None = None

        self._started_at: str | None = None

        self._updated_at = (
            utc_now()
        )

        self._last_call_seen_at: (
            str
            | None
        ) = None

        self._last_metadata_fetch_at: (
            str
            | None
        ) = None

        self._last_audio_download_at: (
            str
            | None
        ) = None

        self._last_audio_decode_at: (
            str
            | None
        ) = None

        self._last_audio_bridge_at: (
            str
            | None
        ) = None

        self._last_completed_call_at: (
            str
            | None
        ) = None

        self._last_completed_call_key: (
            str
            | None
        ) = None

        self._last_audio_bridge_result: (
            dict[str, Any]
            | None
        ) = None

        self._current_call_key: (
            str
            | None
        ) = None

        self._current_group_id: (
            str
            | None
        ) = None

        self._current_ts: (
            int
            | None
        ) = None

        self._current_call_metadata: (
            dict[str, Any]
            | None
        ) = None

        self._current_metadata_source: (
            str
            | None
        ) = None

        self._current_audio_url: (
            str
            | None
        ) = None

        self._current_audio_content_type: (
            str
            | None
        ) = None

        self._current_audio_size_bytes = 0

        self._current_audio: (
            bytes
            | None
        ) = None

        self._current_decoded_audio: (
            DecodedAudio
            | None
        ) = None

        self._current_call_error_stage: (
            str
            | None
        ) = None

        self._calls_observed = 0

        self._metadata_fetch_count = 0

        self._audio_download_count = 0

        self._audio_decode_count = 0

        self._audio_bridge_count = 0

        self._calls_completed = 0

        self._loop_count = 0


    @property
    def is_running(
        self,
    ) -> bool:
        with self._lock:
            return bool(
                self._thread
                and
                self._thread.is_alive()
            )


    def _touch(
        self,
    ) -> None:
        self._updated_at = (
            utc_now()
        )


    def _set_state(
        self,
        state: str,
        *,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self._state = (
                state
            )

            self._error = (
                error
            )

            self._touch()


    def _reset_current_payload(
        self,
    ) -> None:
        self._current_call_metadata = (
            None
        )

        self._current_metadata_source = (
            None
        )

        self._current_audio_url = (
            None
        )

        self._current_audio_content_type = (
            None
        )

        self._current_audio_size_bytes = 0

        self._current_audio = (
            None
        )

        self._current_decoded_audio = (
            None
        )

        self._current_call_error_stage = (
            None
        )

        self._error = (
            None
        )


    def _set_current_call(
        self,
        call: dict[str, Any],
    ) -> None:
        call_key = (
            get_call_key(
                call
            )
        )

        group_id = (
            get_group_id(
                call
            )
        )

        ts = (
            get_call_ts(
                call
            )
        )

        with self._lock:
            changed = (
                call_key
                !=
                self._current_call_key
            )

            if changed:
                self._calls_observed += 1

                self._last_call_seen_at = (
                    utc_now()
                )

                self._reset_current_payload()

            self._current_call_key = (
                call_key
            )

            self._current_group_id = (
                group_id
            )

            self._current_ts = (
                ts
            )

            self._touch()


    def _clear_current_call(
        self,
    ) -> None:
        with self._lock:
            self._current_call_key = (
                None
            )

            self._current_group_id = (
                None
            )

            self._current_ts = (
                None
            )

            self._reset_current_payload()

            self._touch()


    def _record_call_error(
        self,
        *,
        stage: str,
        message: str,
    ) -> None:
        with self._lock:
            self._current_call_error_stage = (
                stage
            )

            self._state = (
                "call_error"
            )

            self._error = (
                message
            )

            self._touch()


    def _http_error_message(
        self,
        *,
        prefix: str,
        error:
            BroadcastifyCallsHTTPError,
    ) -> str:
        message = (
            f"{prefix}: HTTP "
            f"{error.status_code}"
        )

        if error.response_body:
            message += (
                ": "
                + error.response_body[
                    :500
                ]
            )

        return message


    def _ensure_call_metadata(
        self,
        call: dict[str, Any],
    ) -> bool:
        with self._lock:
            if (
                self._current_call_metadata
                is not None
            ):
                return True

            if (
                self._current_call_error_stage
                is not None
            ):
                return False

        live_url_raw = (
            call.get(
                "url"
            )
        )

        live_url = (
            str(
                live_url_raw
            )
            .strip()
            if (
                live_url_raw
                is not None
            )
            else ""
        )

        if live_url:
            with self._lock:
                self._current_call_metadata = (
                    deepcopy(
                        call
                    )
                )

                self._current_metadata_source = (
                    "live"
                )

                self._current_audio_url = (
                    live_url
                )

                self._touch()

            return True

        with self._lock:
            group_id = (
                self._current_group_id
            )

            ts = (
                self._current_ts
            )

        if (
            not group_id
            or
            ts is None
        ):
            self._record_call_error(
                stage=(
                    "metadata"
                ),
                message=(
                    "Call does not contain a valid "
                    "groupId and ts"
                ),
            )

            return False

        self._set_state(
            "fetching_call_metadata"
        )

        try:
            details = (
                self._client
                .get_call(
                    group_id=(
                        group_id
                    ),
                    ts=(
                        ts
                    ),
                )
            )

        except (
            BroadcastifyCallsConfigurationError
        ) as error:
            self._record_call_error(
                stage=(
                    "metadata"
                ),
                message=str(
                    error
                ),
            )

            return False

        except BroadcastifyCallsHTTPError as error:
            self._record_call_error(
                stage=(
                    "metadata"
                ),
                message=(
                    self._http_error_message(
                        prefix=(
                            "Broadcastify Get Call "
                            "failed"
                        ),
                        error=(
                            error
                        ),
                    )
                ),
            )

            return False

        except BroadcastifyCallsError as error:
            self._record_call_error(
                stage=(
                    "metadata"
                ),
                message=str(
                    error
                ),
            )

            return False

        except Exception as error:
            self._record_call_error(
                stage=(
                    "metadata"
                ),
                message=(
                    "Unexpected call metadata "
                    f"error: {error}"
                ),
            )

            return False

        if not isinstance(
            details,
            dict,
        ):
            self._record_call_error(
                stage=(
                    "metadata"
                ),
                message=(
                    "Broadcastify Get Call returned "
                    "an invalid response"
                ),
            )

            return False

        audio_url_raw = (
            details.get(
                "url"
            )
        )

        audio_url = (
            str(
                audio_url_raw
            )
            .strip()
            if (
                audio_url_raw
                is not None
            )
            else ""
        )

        if not audio_url:
            self._record_call_error(
                stage=(
                    "metadata"
                ),
                message=(
                    "Broadcastify Get Call response "
                    "does not contain audio url"
                ),
            )

            return False

        with self._lock:
            self._current_call_metadata = (
                deepcopy(
                    details
                )
            )

            self._current_metadata_source = (
                "call_get"
            )

            self._current_audio_url = (
                audio_url
            )

            self._metadata_fetch_count += 1

            self._last_metadata_fetch_at = (
                utc_now()
            )

            self._touch()

        return True


    def _ensure_audio_downloaded(
        self,
    ) -> bool:
        with self._lock:
            if (
                self._current_audio
                is not None
            ):
                return True

            if (
                self._current_call_error_stage
                is not None
            ):
                return False

            audio_url = (
                self._current_audio_url
            )

        if not audio_url:
            self._record_call_error(
                stage=(
                    "audio_download"
                ),
                message=(
                    "Current call does not contain "
                    "an audio URL"
                ),
            )

            return False

        self._set_state(
            "downloading_audio"
        )

        try:
            (
                audio,
                content_type,
            ) = (
                self._client
                .download_audio(
                    audio_url
                )
            )

        except BroadcastifyCallsHTTPError as error:
            self._record_call_error(
                stage=(
                    "audio_download"
                ),
                message=(
                    self._http_error_message(
                        prefix=(
                            "Broadcastify audio "
                            "download failed"
                        ),
                        error=(
                            error
                        ),
                    )
                ),
            )

            return False

        except BroadcastifyCallsError as error:
            self._record_call_error(
                stage=(
                    "audio_download"
                ),
                message=str(
                    error
                ),
            )

            return False

        except Exception as error:
            self._record_call_error(
                stage=(
                    "audio_download"
                ),
                message=(
                    "Unexpected audio download "
                    f"error: {error}"
                ),
            )

            return False

        if not audio:
            self._record_call_error(
                stage=(
                    "audio_download"
                ),
                message=(
                    "Broadcastify audio download "
                    "returned an empty file"
                ),
            )

            return False

        with self._lock:
            self._current_audio = (
                bytes(
                    audio
                )
            )

            self._current_audio_content_type = (
                content_type
            )

            self._current_audio_size_bytes = (
                len(
                    audio
                )
            )

            self._audio_download_count += 1

            self._last_audio_download_at = (
                utc_now()
            )

            self._touch()

        return True


    def _ensure_audio_decoded(
        self,
    ) -> bool:
        with self._lock:
            if (
                self._current_decoded_audio
                is not None
            ):
                return True

            if (
                self._current_call_error_stage
                is not None
            ):
                return False

            audio = (
                self._current_audio
            )

            content_type = (
                self._current_audio_content_type
            )

        if audio is None:
            self._record_call_error(
                stage=(
                    "audio_decode"
                ),
                message=(
                    "No encoded audio is available "
                    "for decoding"
                ),
            )

            return False

        self._set_state(
            "decoding_audio"
        )

        try:
            decoded = (
                self._decoder
                .decode(
                    audio,
                    content_type=(
                        content_type
                    ),
                )
            )

        except AudioDecoderError as error:
            self._record_call_error(
                stage=(
                    "audio_decode"
                ),
                message=str(
                    error
                ),
            )

            return False

        except Exception as error:
            self._record_call_error(
                stage=(
                    "audio_decode"
                ),
                message=(
                    "Unexpected audio decode "
                    f"error: {error}"
                ),
            )

            return False

        if not isinstance(
            decoded,
            DecodedAudio,
        ):
            self._record_call_error(
                stage=(
                    "audio_decode"
                ),
                message=(
                    "Audio decoder returned an "
                    "invalid result"
                ),
            )

            return False

        if not decoded.pcm:
            self._record_call_error(
                stage=(
                    "audio_decode"
                ),
                message=(
                    "Audio decoder returned "
                    "empty PCM"
                ),
            )

            return False

        with self._lock:
            self._current_decoded_audio = (
                decoded
            )

            self._audio_decode_count += 1

            self._last_audio_decode_at = (
                utc_now()
            )

            self._touch()

        return True


    def _bridge_current_audio(
        self,
    ) -> dict[str, Any] | None:
        with self._lock:
            if (
                self._current_call_error_stage
                is not None
            ):
                return None

            decoded_audio = (
                self._current_decoded_audio
            )

        if decoded_audio is None:
            self._record_call_error(
                stage=(
                    "audio_bridge"
                ),
                message=(
                    "No decoded PCM is available "
                    "for the audio bridge"
                ),
            )

            return None

        if (
            self._stop_event
            .is_set()
        ):
            return None

        self._set_state(
            "bridging_audio"
        )

        try:
            result = (
                bridge_decoded_audio(
                    self.protocol,
                    decoded_audio,
                )
            )

        except AudioBridgeError as error:
            self._record_call_error(
                stage=(
                    "audio_bridge"
                ),
                message=str(
                    error
                ),
            )

            return None

        except Exception as error:
            self._record_call_error(
                stage=(
                    "audio_bridge"
                ),
                message=(
                    "Unexpected audio bridge "
                    f"error: {error}"
                ),
            )

            return None

        if not isinstance(
            result,
            dict,
        ):
            self._record_call_error(
                stage=(
                    "audio_bridge"
                ),
                message=(
                    "Audio bridge returned "
                    "an invalid result"
                ),
            )

            return None

        with self._lock:
            self._audio_bridge_count += 1

            self._last_audio_bridge_at = (
                utc_now()
            )

            self._last_audio_bridge_result = (
                deepcopy(
                    result
                )
            )

            self._touch()

        return deepcopy(
            result
        )


    def _complete_current_call(
        self,
        queue: Any,
    ) -> bool:
        with self._lock:
            current_call_key = (
                self._current_call_key
            )

        if not current_call_key:
            self._record_call_error(
                stage=(
                    "queue_dequeue"
                ),
                message=(
                    "Current call does not "
                    "have a queue key"
                ),
            )

            return False

        pending = (
            queue.peek()
        )

        if pending is None:
            self._record_call_error(
                stage=(
                    "queue_dequeue"
                ),
                message=(
                    "Call queue became empty "
                    "before completion"
                ),
            )

            return False

        pending_call_key = (
            get_call_key(
                pending
            )
        )

        if (
            pending_call_key
            != current_call_key
        ):
            self._record_call_error(
                stage=(
                    "queue_dequeue"
                ),
                message=(
                    "Call queue head changed "
                    "before completion: "
                    f"expected {current_call_key}, "
                    f"found {pending_call_key}"
                ),
            )

            return False

        completed = (
            queue.pop_next()
        )

        if completed is None:
            self._record_call_error(
                stage=(
                    "queue_dequeue"
                ),
                message=(
                    "Call queue became empty "
                    "during completion"
                ),
            )

            return False

        completed_call_key = (
            get_call_key(
                completed
            )
        )

        if (
            completed_call_key
            != current_call_key
        ):
            self._record_call_error(
                stage=(
                    "queue_dequeue"
                ),
                message=(
                    "Dequeued call does not match "
                    "the transmitted call: "
                    f"expected {current_call_key}, "
                    f"got {completed_call_key}"
                ),
            )

            return False

        with self._lock:
            self._calls_completed += 1

            self._last_completed_call_key = (
                current_call_key
            )

            self._last_completed_call_at = (
                utc_now()
            )

            self._touch()

        return True


    def _run(
        self,
    ) -> None:
        self._set_state(
            "starting"
        )

        while not (
            self._stop_event
            .is_set()
        ):
            try:
                with self._lock:
                    self._loop_count += 1

                    self._touch()

                queue = (
                    self._queue_manager
                    .get_queue(
                        self.route_id
                    )
                )

                call = (
                    queue.peek()
                )

                if call is None:
                    self._clear_current_call()

                    self._set_state(
                        "waiting_for_call"
                    )

                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                self._set_current_call(
                    call
                )

                with self._lock:
                    call_error_stage = (
                        self._current_call_error_stage
                    )

                    call_error = (
                        self._error
                    )

                if call_error_stage:
                    self._set_state(
                        "call_error",
                        error=(
                            call_error
                        ),
                    )

                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                if not (
                    self._ensure_call_metadata(
                        call
                    )
                ):
                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                if not (
                    self._ensure_audio_downloaded()
                ):
                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                if not (
                    self._ensure_audio_decoded()
                ):
                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                capability = (
                    get_audio_bridge_capability(
                        self.protocol
                    )
                )

                bridge_ready = bool(
                    capability.get(
                        "audio_input_supported",
                        False,
                    )
                    and
                    capability.get(
                        "bridge_state"
                    )
                    == "ready"
                )

                if not bridge_ready:
                    self._set_state(
                        "waiting_for_audio_bridge"
                    )

                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                bridge_result = (
                    self._bridge_current_audio()
                )

                if bridge_result is None:
                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                if not (
                    self._complete_current_call(
                        queue
                    )
                ):
                    self._stop_event.wait(
                        self.poll_interval_seconds
                    )

                    continue

                self._clear_current_call()

                self._set_state(
                    "call_completed"
                )

            except Exception as error:
                self._set_state(
                    "error",
                    error=str(
                        error
                    ),
                )

                self._stop_event.wait(
                    self.poll_interval_seconds
                )

        self._set_state(
            "stopped"
        )


    def start(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            if (
                self._thread
                and
                self._thread.is_alive()
            ):
                return self.status()

            self._stop_event.clear()

            self._state = (
                "starting"
            )

            self._error = (
                None
            )

            self._started_at = (
                utc_now()
            )

            self._updated_at = (
                self._started_at
            )

            self._thread = (
                Thread(
                    target=(
                        self._run
                    ),
                    name=(
                        "call-processor-"
                        f"{self.route_id}"
                    ),
                    daemon=True,
                )
            )

            self._thread.start()

        return self.status()


    def stop(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            thread = (
                self._thread
            )

            if (
                thread is None
                or
                not thread.is_alive()
            ):
                self._state = (
                    "stopped"
                )

                self._error = (
                    None
                )

                self._thread = (
                    None
                )

                self._clear_current_call()

                self._touch()

                return self.status()

            self._state = (
                "stopping"
            )

            self._touch()

            self._stop_event.set()

        thread.join(
            timeout=2.0
        )

        with self._lock:
            if thread.is_alive():
                self._state = (
                    "error"
                )

                self._error = (
                    "Call processor thread "
                    "did not stop in time"
                )

            else:
                self._state = (
                    "stopped"
                )

                self._error = (
                    None
                )

                self._thread = (
                    None
                )

                self._clear_current_call()

            self._touch()

        return self.status()


    def status(
        self,
    ) -> dict[str, Any]:
        queue = (
            self._queue_manager
            .get_queue(
                self.route_id
            )
        )

        capability = (
            get_audio_bridge_capability(
                self.protocol
            )
        )

        with self._lock:
            decoded_status = (
                self._current_decoded_audio
                .status()
                if (
                    self._current_decoded_audio
                    is not None
                )
                else None
            )

            return {
                "route_id":
                    self.route_id,

                "protocol":
                    self.protocol,

                "state":
                    self._state,

                "running":
                    bool(
                        self._thread
                        and
                        self._thread.is_alive()
                    ),

                "poll_interval_seconds":
                    self.poll_interval_seconds,

                "loop_count":
                    self._loop_count,

                "calls_observed":
                    self._calls_observed,

                "metadata_fetch_count":
                    self._metadata_fetch_count,

                "audio_download_count":
                    self._audio_download_count,

                "audio_decode_count":
                    self._audio_decode_count,

                "audio_bridge_count":
                    self._audio_bridge_count,

                "calls_completed":
                    self._calls_completed,

                "current_call_key":
                    self._current_call_key,

                "current_group_id":
                    self._current_group_id,

                "current_ts":
                    self._current_ts,

                "current_metadata_source":
                    self._current_metadata_source,

                "current_call_metadata":
                    deepcopy(
                        self._current_call_metadata
                    ),

                "current_audio_url":
                    self._current_audio_url,

                "current_audio_content_type":
                    self._current_audio_content_type,

                "current_audio_size_bytes":
                    self._current_audio_size_bytes,

                "current_audio_ready":
                    (
                        self._current_audio
                        is not None
                    ),

                "current_pcm_ready":
                    (
                        self._current_decoded_audio
                        is not None
                    ),

                "current_pcm":
                    (
                        decoded_status
                    ),

                "current_call_error_stage":
                    self._current_call_error_stage,

                "last_call_seen_at":
                    self._last_call_seen_at,

                "last_metadata_fetch_at":
                    self._last_metadata_fetch_at,

                "last_audio_download_at":
                    self._last_audio_download_at,

                "last_audio_decode_at":
                    self._last_audio_decode_at,

                "last_audio_bridge_at":
                    self._last_audio_bridge_at,

                "last_completed_call_at":
                    self._last_completed_call_at,

                "last_completed_call_key":
                    self._last_completed_call_key,

                "last_audio_bridge_result":
                    deepcopy(
                        self._last_audio_bridge_result
                    ),

                "started_at":
                    self._started_at,

                "updated_at":
                    self._updated_at,

                "error":
                    self._error,

                "audio_bridge":
                    deepcopy(
                        capability
                    ),

                "queue":
                    queue.stats(),
            }


class CallProcessorManager:
    def __init__(
        self,
        *,
        queue_manager:
            CallQueueManager
            | None = None,
    ) -> None:
        self._lock = (
            RLock()
        )

        self._queue_manager = (
            queue_manager
            or
            call_queue_manager
        )

        self._processors: dict[
            str,
            CallProcessor,
        ] = {}


    def get(
        self,
        route_id: str,
    ) -> CallProcessor | None:
        with self._lock:
            return (
                self._processors.get(
                    route_id
                )
            )


    def create(
        self,
        route_id: str,
        protocol: str,
    ) -> CallProcessor:
        normalized_protocol = (
            protocol
            .strip()
            .lower()
        )

        with self._lock:
            existing = (
                self._processors.get(
                    route_id
                )
            )

            if existing is not None:
                if (
                    existing.protocol
                    ==
                    normalized_protocol
                ):
                    return existing

                if existing.is_running:
                    raise RuntimeError(
                        (
                            "Cannot change protocol "
                            "while call processor "
                            "is running"
                        )
                    )

                self._processors.pop(
                    route_id,
                    None,
                )

            processor = (
                CallProcessor(
                    route_id=(
                        route_id
                    ),
                    protocol=(
                        normalized_protocol
                    ),
                    queue_manager=(
                        self._queue_manager
                    ),
                )
            )

            self._processors[
                route_id
            ] = (
                processor
            )

            return processor


    def start(
        self,
        route_id: str,
        protocol: str,
    ) -> dict[str, Any]:
        processor = (
            self.create(
                route_id,
                protocol,
            )
        )

        return (
            processor.start()
        )


    def stop(
        self,
        route_id: str,
    ) -> dict[str, Any] | None:
        processor = (
            self.get(
                route_id
            )
        )

        if processor is None:
            return None

        return (
            processor.stop()
        )


    def remove(
        self,
        route_id: str,
    ) -> bool:
        processor = (
            self.get(
                route_id
            )
        )

        if processor is None:
            return False

        processor.stop()

        with self._lock:
            return (
                self._processors.pop(
                    route_id,
                    None,
                )
                is not None
            )


    def status(
        self,
        route_id: str,
    ) -> dict[str, Any] | None:
        processor = (
            self.get(
                route_id
            )
        )

        if processor is None:
            return None

        return (
            processor.status()
        )


    def list_status(
        self,
    ) -> list[
        dict[str, Any]
    ]:
        with self._lock:
            processors = list(
                self._processors
                .values()
            )

        return [
            processor.status()
            for processor
            in processors
        ]


    def stop_all(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            processors = list(
                self._processors
                .values()
            )

        stopped = 0

        for processor in processors:
            processor.stop()

            stopped += 1

        return {
            "processor_count":
                len(
                    processors
                ),

            "stopped":
                stopped,
        }


call_processor_manager = (
    CallProcessorManager()
)