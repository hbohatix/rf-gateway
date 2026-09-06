from __future__ import annotations

import time

from copy import (
    deepcopy,
)

from datetime import (
    datetime,
    timezone,
)

from threading import (
    Event,
    RLock,
    Thread,
)

from typing import (
    Any,
)

from app.audio_activity_gate import (
    AudioActivityGate,
    AudioActivityGateConfig,
)

from app.broadcastify_live_audio_client import (
    BroadcastifyLiveAudioClient,
    BroadcastifyLiveAudioStream,
    broadcastify_live_audio_client,
)

from app.p25_streaming_session import (
    P25StreamingSession,
)


DEFAULT_READ_TIMEOUT_SECONDS = 0.5

DEFAULT_TRANSPORT_GAP_END_SECONDS = 3.0


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


class BroadcastifyLiveAudioPipelineError(
    RuntimeError
):
    pass


class BroadcastifyLiveAudioPipeline:
    def __init__(
        self,
        *,
        route_id: str,
        source: dict[str, Any],
        protocol: str,
        client:
            BroadcastifyLiveAudioClient
            | None = None,
        read_timeout_seconds: float = (
            DEFAULT_READ_TIMEOUT_SECONDS
        ),
        transport_gap_end_seconds: float = (
            DEFAULT_TRANSPORT_GAP_END_SECONDS
        ),
    ) -> None:
        if not route_id:
            raise ValueError(
                "route_id cannot be empty"
            )

        if read_timeout_seconds <= 0:
            raise ValueError(
                (
                    "read_timeout_seconds must "
                    "be greater than zero"
                )
            )

        if transport_gap_end_seconds <= 0:
            raise ValueError(
                (
                    "transport_gap_end_seconds "
                    "must be greater than zero"
                )
            )

        self.route_id = str(
            route_id
        )

        self.source = deepcopy(
            source
        )

        self.protocol = (
            str(
                protocol
            )
            .strip()
            .lower()
        )

        self.client = (
            client
            or
            broadcastify_live_audio_client
        )

        self.read_timeout_seconds = float(
            read_timeout_seconds
        )

        self.transport_gap_end_seconds = float(
            transport_gap_end_seconds
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

        self._stream: (
            BroadcastifyLiveAudioStream
            | None
        ) = None

        self._gate: (
            AudioActivityGate
            | None
        ) = None

        self._p25: (
            P25StreamingSession
            | None
        ) = None

        self._last_pcm_monotonic: (
            float
            | None
        ) = None

        self._state: dict[
            str,
            Any,
        ] = {
            "route_id":
                self.route_id,

            "source_id":
                self.source.get(
                    "id"
                ),

            "source_type":
                self.source.get(
                    "type"
                ),

            "feed_id":
                self.source.get(
                    "feed_id"
                ),

            "protocol":
                self.protocol,

            "state":
                "stopped",

            "running":
                False,

            "error":
                None,

            "read_timeout_seconds":
                self.read_timeout_seconds,

            "transport_gap_end_seconds":
                self.transport_gap_end_seconds,

            "pcm_chunks_received":
                0,

            "pcm_bytes_received":
                0,

            "tx_start_count":
                0,

            "tx_end_count":
                0,

            "transport_gap_end_count":
                0,

            "last_pcm_at":
                None,

            "last_tx_start_at":
                None,

            "last_tx_end_at":
                None,

            "last_activity_level_dbfs":
                None,

            "last_noise_floor_dbfs":
                None,

            "last_trigger_dbfs":
                None,

            "started_at":
                None,

            "stopped_at":
                None,

            "updated_at":
                utc_now(),
        }


    def _touch(
        self,
    ) -> None:
        self._state[
            "updated_at"
        ] = utc_now()


    def _set_state(
        self,
        state: str,
        *,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self._state[
                "state"
            ] = state

            self._state[
                "error"
            ] = error

            self._touch()


    def _validate_source(
        self,
    ) -> int:
        source_type = (
            str(
                self.source.get(
                    "type"
                )
                or ""
            )
            .strip()
            .lower()
        )

        provider = (
            str(
                self.source.get(
                    "provider"
                )
                or ""
            )
            .strip()
            .lower()
        )

        if (
            source_type
            !=
            "broadcastify_live_audio"
        ):
            raise (
                BroadcastifyLiveAudioPipelineError(
                    (
                        "Live Audio pipeline "
                        "requires source type "
                        "broadcastify_live_audio"
                    )
                )
            )

        if (
            provider
            !=
            "broadcastify"
        ):
            raise (
                BroadcastifyLiveAudioPipelineError(
                    (
                        "Live Audio pipeline "
                        "requires provider "
                        "broadcastify"
                    )
                )
            )

        if self.protocol != "p25":
            raise (
                BroadcastifyLiveAudioPipelineError(
                    (
                        "Broadcastify Live Audio "
                        "pipeline currently supports "
                        "protocol p25 only"
                    )
                )
            )

        try:
            feed_id = int(
                self.source[
                    "feed_id"
                ]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise (
                BroadcastifyLiveAudioPipelineError(
                    (
                        "Broadcastify Live Audio "
                        "source does not contain "
                        "a valid feed_id"
                    )
                )
            ) from error

        if feed_id <= 0:
            raise (
                BroadcastifyLiveAudioPipelineError(
                    (
                        "Broadcastify Live Audio "
                        "feed_id must be greater "
                        "than zero"
                    )
                )
            )

        return feed_id


    def _activity_config(
        self,
    ) -> AudioActivityGateConfig:
        raw = (
            self.source.get(
                "activity_detection"
            )
        )

        if not isinstance(
            raw,
            dict,
        ):
            raw = {}

        allowed_keys = {
            "pre_roll_ms",
            "attack_ms",
            "hang_ms",
            "trigger_margin_db",
            "hysteresis_db",
            "minimum_trigger_dbfs",
            "initial_noise_floor_dbfs",
            "noise_floor_alpha",
            "minimum_noise_floor_dbfs",
            "maximum_noise_floor_dbfs",
            "silence_dbfs",
        }

        values = {
            key:
                value

            for (
                key,
                value,
            ) in raw.items()

            if key in allowed_keys
        }

        values[
            "sample_rate"
        ] = 8000

        values[
            "channels"
        ] = 1

        values[
            "sample_width_bytes"
        ] = 2

        values[
            "chunk_duration_ms"
        ] = (
            self.client
            .chunk_duration_ms
        )

        return (
            AudioActivityGateConfig(
                **values
            )
        )


    def _finish_tx(
        self,
        *,
        reason: str,
    ) -> None:
        p25 = (
            self._p25
        )

        if (
            p25 is None
            or
            not p25.active
        ):
            return

        p25.end()

        with self._lock:
            self._state[
                "tx_end_count"
            ] += 1

            self._state[
                "last_tx_end_at"
            ] = utc_now()

            if (
                reason
                ==
                "transport_gap"
            ):
                self._state[
                    "transport_gap_end_count"
                ] += 1

            self._touch()


    def _handle_transport_gap(
        self,
    ) -> None:
        last_pcm = (
            self._last_pcm_monotonic
        )

        if last_pcm is None:
            return

        elapsed = (
            time.monotonic()
            -
            last_pcm
        )

        p25 = (
            self._p25
        )

        if (
            p25 is None
            or
            not p25.active
        ):
            return

        if (
            elapsed
            <
            self.transport_gap_end_seconds
        ):
            return

        self._finish_tx(
            reason="transport_gap"
        )

        gate = (
            self._gate
        )

        if gate is not None:
            gate.reset()

        self._set_state(
            "waiting_for_audio"
        )


    def _process_pcm_chunk(
        self,
        chunk: bytes,
    ) -> None:
        gate = (
            self._gate
        )

        p25 = (
            self._p25
        )

        if (
            gate is None
            or
            p25 is None
        ):
            raise (
                BroadcastifyLiveAudioPipelineError(
                    (
                        "Live Audio pipeline "
                        "components are not "
                        "initialized"
                    )
                )
            )

        decision = (
            gate.process_chunk(
                chunk
            )
        )

        with self._lock:
            self._state[
                "pcm_chunks_received"
            ] += 1

            self._state[
                "pcm_bytes_received"
            ] += len(
                chunk
            )

            self._state[
                "last_pcm_at"
            ] = utc_now()

            self._state[
                "last_activity_level_dbfs"
            ] = (
                decision.level_dbfs
            )

            self._state[
                "last_noise_floor_dbfs"
            ] = (
                decision.noise_floor_dbfs
            )

            self._state[
                "last_trigger_dbfs"
            ] = (
                decision.trigger_dbfs
            )

            self._touch()

        if decision.started:
            p25.start()

            with self._lock:
                self._state[
                    "tx_start_count"
                ] += 1

                self._state[
                    "last_tx_start_at"
                ] = utc_now()

                self._state[
                    "state"
                ] = "transmitting"

                self._touch()

        if decision.output_chunks:
            if not p25.active:
                raise (
                    BroadcastifyLiveAudioPipelineError(
                        (
                            "Activity gate produced "
                            "TX audio while P25 "
                            "session is inactive"
                        )
                    )
                )

            payload = b"".join(
                decision.output_chunks
            )

            p25.feed_pcm(
                payload
            )

        if decision.ended:
            self._finish_tx(
                reason="activity_end"
            )

            self._set_state(
                "listening"
            )


    def _run(
        self,
    ) -> None:
        stream: (
            BroadcastifyLiveAudioStream
            | None
        ) = None

        p25: (
            P25StreamingSession
            | None
        ) = None

        error_message: (
            str
            | None
        ) = None

        try:
            feed_id = (
                self._validate_source()
            )

            gate = (
                AudioActivityGate(
                    self._activity_config()
                )
            )

            p25 = (
                P25StreamingSession()
            )

            with self._lock:
                self._gate = gate

                self._p25 = p25

                self._state[
                    "state"
                ] = "connecting"

                self._touch()

            stream = (
                self.client
                .open_stream(
                    feed_id
                )
            )

            with self._lock:
                self._stream = stream

                self._state[
                    "state"
                ] = "listening"

                self._touch()

            while not (
                self._stop_event
                .is_set()
            ):
                chunk = (
                    stream.read_chunk(
                        timeout_seconds=(
                            self.read_timeout_seconds
                        )
                    )
                )

                if not chunk:
                    self._handle_transport_gap()

                    continue

                self._last_pcm_monotonic = (
                    time.monotonic()
                )

                self._process_pcm_chunk(
                    chunk
                )

        except Exception as error:
            error_message = str(
                error
            )

            self._set_state(
                "error",
                error=(
                    error_message
                ),
            )

        finally:
            if (
                p25 is not None
                and
                p25.active
            ):
                try:
                    self._finish_tx(
                        reason="pipeline_stop"
                    )

                except Exception as error:
                    if error_message is None:
                        error_message = str(
                            error
                        )

            if stream is not None:
                try:
                    stream.close()

                except Exception as error:
                    if error_message is None:
                        error_message = str(
                            error
                        )

            with self._lock:
                self._stream = None

                self._state[
                    "running"
                ] = False

                self._state[
                    "stopped_at"
                ] = utc_now()

                if error_message is None:
                    self._state[
                        "state"
                    ] = "stopped"

                    self._state[
                        "error"
                    ] = None

                else:
                    self._state[
                        "state"
                    ] = "error"

                    self._state[
                        "error"
                    ] = error_message

                self._touch()


    def start(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            if (
                self._thread
                is not None
                and
                self._thread.is_alive()
            ):
                return (
                    self.status()
                )

            self._validate_source()

            self._stop_event.clear()

            self._last_pcm_monotonic = None

            self._state[
                "running"
            ] = True

            self._state[
                "state"
            ] = "starting"

            self._state[
                "error"
            ] = None

            self._state[
                "started_at"
            ] = utc_now()

            self._state[
                "stopped_at"
            ] = None

            self._touch()

            self._thread = (
                Thread(
                    target=(
                        self._run
                    ),
                    name=(
                        "broadcastify-live-audio-"
                        f"{self.route_id}"
                    ),
                    daemon=True,
                )
            )

            self._thread.start()

        return (
            self.status()
        )


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
                self._state[
                    "running"
                ] = False

                self._state[
                    "state"
                ] = "stopped"

                self._touch()

                return (
                    self.status()
                )

            self._state[
                "state"
            ] = "stopping"

            self._touch()

            self._stop_event.set()

        thread.join(
            timeout=5.0
        )

        with self._lock:
            if not thread.is_alive():
                self._thread = None

            self._touch()

        return (
            self.status()
        )


    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(
                self._state
            )

            gate = (
                self._gate
            )

            stream = (
                self._stream
            )

            p25 = (
                self._p25
            )

        gate_status = None

        stream_status = None

        p25_status = None

        if gate is not None:
            try:
                gate_status = (
                    gate.status()
                )

            except Exception:
                gate_status = None

        if stream is not None:
            try:
                stream_status = (
                    stream.status()
                )

            except Exception:
                stream_status = None

        if p25 is not None:
            try:
                p25_status = (
                    p25.status()
                )

            except Exception:
                p25_status = None

        state[
            "gate"
        ] = gate_status

        state[
            "stream"
        ] = stream_status

        state[
            "p25"
        ] = p25_status

        return state


class BroadcastifyLiveAudioPipelineManager:
    def __init__(
        self,
    ) -> None:
        self._lock = (
            RLock()
        )

        self._pipelines: dict[
            str,
            BroadcastifyLiveAudioPipeline,
        ] = {}


    def create_or_get(
        self,
        *,
        route_id: str,
        source: dict[str, Any],
        protocol: str,
    ) -> BroadcastifyLiveAudioPipeline:
        with self._lock:
            pipeline = (
                self._pipelines.get(
                    route_id
                )
            )

            if pipeline is not None:
                return pipeline

            pipeline = (
                BroadcastifyLiveAudioPipeline(
                    route_id=(
                        route_id
                    ),

                    source=(
                        source
                    ),

                    protocol=(
                        protocol
                    ),
                )
            )

            self._pipelines[
                route_id
            ] = pipeline

            return pipeline


    def get(
        self,
        route_id: str,
    ) -> (
        BroadcastifyLiveAudioPipeline
        | None
    ):
        with self._lock:
            return (
                self._pipelines.get(
                    route_id
                )
            )


    def stop(
        self,
        route_id: str,
    ) -> dict[str, Any] | None:
        pipeline = (
            self.get(
                route_id
            )
        )

        if pipeline is None:
            return None

        return pipeline.stop()


    def remove(
        self,
        route_id: str,
    ) -> bool:
        pipeline = (
            self.get(
                route_id
            )
        )

        if pipeline is None:
            return False

        pipeline.stop()

        with self._lock:
            self._pipelines.pop(
                route_id,
                None,
            )

        return True


    def stop_all(
        self,
    ) -> None:
        with self._lock:
            pipelines = list(
                self._pipelines
                .values()
            )

        for pipeline in pipelines:
            pipeline.stop()


    def list_status(
        self,
    ) -> list[
        dict[str, Any]
    ]:
        with self._lock:
            pipelines = list(
                self._pipelines
                .values()
            )

        return [
            pipeline.status()
            for pipeline
            in pipelines
        ]


broadcastify_live_audio_pipeline_manager = (
    BroadcastifyLiveAudioPipelineManager()
)
