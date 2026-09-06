from __future__ import annotations

import math
import struct

from collections import deque

from dataclasses import (
    dataclass,
)

from typing import (
    Any,
)


DEFAULT_SAMPLE_RATE = 8000

DEFAULT_CHANNELS = 1

DEFAULT_SAMPLE_WIDTH_BYTES = 2

DEFAULT_CHUNK_DURATION_MS = 20


DEFAULT_PRE_ROLL_MS = 400

DEFAULT_ATTACK_MS = 100

DEFAULT_HANG_MS = 3000


DEFAULT_TRIGGER_MARGIN_DB = 10.0

DEFAULT_HYSTERESIS_DB = 6.0

DEFAULT_MINIMUM_TRIGGER_DBFS = -60.0

DEFAULT_INITIAL_NOISE_FLOOR_DBFS = -70.0

DEFAULT_NOISE_FLOOR_ALPHA = 0.02

DEFAULT_MIN_NOISE_FLOOR_DBFS = -90.0

DEFAULT_MAX_NOISE_FLOOR_DBFS = -25.0

DEFAULT_SILENCE_DBFS = -96.0


class AudioActivityGateError(
    RuntimeError
):
    pass


class AudioActivityGateInputError(
    AudioActivityGateError
):
    pass


@dataclass(
    frozen=True,
)
class AudioActivityGateConfig:
    sample_rate: int = (
        DEFAULT_SAMPLE_RATE
    )

    channels: int = (
        DEFAULT_CHANNELS
    )

    sample_width_bytes: int = (
        DEFAULT_SAMPLE_WIDTH_BYTES
    )

    chunk_duration_ms: int = (
        DEFAULT_CHUNK_DURATION_MS
    )

    pre_roll_ms: int = (
        DEFAULT_PRE_ROLL_MS
    )

    attack_ms: int = (
        DEFAULT_ATTACK_MS
    )

    hang_ms: int = (
        DEFAULT_HANG_MS
    )

    trigger_margin_db: float = (
        DEFAULT_TRIGGER_MARGIN_DB
    )

    hysteresis_db: float = (
        DEFAULT_HYSTERESIS_DB
    )

    minimum_trigger_dbfs: float = (
        DEFAULT_MINIMUM_TRIGGER_DBFS
    )

    initial_noise_floor_dbfs: float = (
        DEFAULT_INITIAL_NOISE_FLOOR_DBFS
    )

    noise_floor_alpha: float = (
        DEFAULT_NOISE_FLOOR_ALPHA
    )

    minimum_noise_floor_dbfs: float = (
        DEFAULT_MIN_NOISE_FLOOR_DBFS
    )

    maximum_noise_floor_dbfs: float = (
        DEFAULT_MAX_NOISE_FLOOR_DBFS
    )

    silence_dbfs: float = (
        DEFAULT_SILENCE_DBFS
    )


    def __post_init__(
        self,
    ) -> None:
        if self.sample_rate <= 0:
            raise ValueError(
                (
                    "sample_rate must be "
                    "greater than zero"
                )
            )


        if self.channels != 1:
            raise ValueError(
                (
                    "Audio activity gate "
                    "currently requires "
                    "mono PCM"
                )
            )


        if (
            self.sample_width_bytes
            != 2
        ):
            raise ValueError(
                (
                    "Audio activity gate "
                    "currently requires "
                    "16-bit PCM"
                )
            )


        if self.chunk_duration_ms <= 0:
            raise ValueError(
                (
                    "chunk_duration_ms must "
                    "be greater than zero"
                )
            )


        if self.pre_roll_ms < 0:
            raise ValueError(
                (
                    "pre_roll_ms cannot "
                    "be negative"
                )
            )


        if self.attack_ms < 0:
            raise ValueError(
                (
                    "attack_ms cannot "
                    "be negative"
                )
            )


        if self.hang_ms < 0:
            raise ValueError(
                (
                    "hang_ms cannot "
                    "be negative"
                )
            )


        if self.trigger_margin_db < 0:
            raise ValueError(
                (
                    "trigger_margin_db cannot "
                    "be negative"
                )
            )


        if self.hysteresis_db < 0:
            raise ValueError(
                (
                    "hysteresis_db cannot "
                    "be negative"
                )
            )


        if not (
            0.0
            <
            self.noise_floor_alpha
            <=
            1.0
        ):
            raise ValueError(
                (
                    "noise_floor_alpha must "
                    "be between 0 and 1"
                )
            )


        if (
            self.minimum_noise_floor_dbfs
            >=
            self.maximum_noise_floor_dbfs
        ):
            raise ValueError(
                (
                    "minimum noise floor must "
                    "be lower than maximum "
                    "noise floor"
                )
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
            self.sample_width_bytes
        )


    @property
    def pre_roll_chunks(
        self,
    ) -> int:
        if self.pre_roll_ms <= 0:
            return 0

        return max(
            1,
            math.ceil(
                self.pre_roll_ms
                /
                self.chunk_duration_ms
            ),
        )


    @property
    def attack_chunks(
        self,
    ) -> int:
        if self.attack_ms <= 0:
            return 1

        return max(
            1,
            math.ceil(
                self.attack_ms
                /
                self.chunk_duration_ms
            ),
        )


    @property
    def hang_chunks(
        self,
    ) -> int:
        if self.hang_ms <= 0:
            return 0

        return max(
            1,
            math.ceil(
                self.hang_ms
                /
                self.chunk_duration_ms
            ),
        )


    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "sample_rate":
                self.sample_rate,

            "channels":
                self.channels,

            "sample_width_bytes":
                self.sample_width_bytes,

            "chunk_duration_ms":
                self.chunk_duration_ms,

            "chunk_samples":
                self.chunk_samples,

            "chunk_bytes":
                self.chunk_bytes,

            "pre_roll_ms":
                self.pre_roll_ms,

            "pre_roll_chunks":
                self.pre_roll_chunks,

            "attack_ms":
                self.attack_ms,

            "attack_chunks":
                self.attack_chunks,

            "hang_ms":
                self.hang_ms,

            "hang_chunks":
                self.hang_chunks,

            "trigger_margin_db":
                self.trigger_margin_db,

            "hysteresis_db":
                self.hysteresis_db,

            "minimum_trigger_dbfs":
                self.minimum_trigger_dbfs,

            "initial_noise_floor_dbfs":
                self.initial_noise_floor_dbfs,

            "noise_floor_alpha":
                self.noise_floor_alpha,

            "minimum_noise_floor_dbfs":
                self.minimum_noise_floor_dbfs,

            "maximum_noise_floor_dbfs":
                self.maximum_noise_floor_dbfs,

            "silence_dbfs":
                self.silence_dbfs,
        }


@dataclass(
    frozen=True,
)
class AudioActivityDecision:
    level_dbfs: float

    noise_floor_dbfs: float

    trigger_dbfs: float

    release_dbfs: float

    signal_active: bool

    tx_active: bool

    started: bool

    ended: bool

    output_chunks: tuple[
        bytes,
        ...,
    ]

    attack_progress_chunks: int

    hang_remaining_chunks: int


    @property
    def output_bytes(
        self,
    ) -> bytes:
        return b"".join(
            self.output_chunks
        )


    @property
    def output_size_bytes(
        self,
    ) -> int:
        return sum(
            len(
                chunk
            )
            for chunk
            in self.output_chunks
        )


    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "level_dbfs":
                self.level_dbfs,

            "noise_floor_dbfs":
                self.noise_floor_dbfs,

            "trigger_dbfs":
                self.trigger_dbfs,

            "release_dbfs":
                self.release_dbfs,

            "signal_active":
                self.signal_active,

            "tx_active":
                self.tx_active,

            "started":
                self.started,

            "ended":
                self.ended,

            "output_chunks":
                len(
                    self.output_chunks
                ),

            "output_size_bytes":
                self.output_size_bytes,

            "attack_progress_chunks":
                self.attack_progress_chunks,

            "hang_remaining_chunks":
                self.hang_remaining_chunks,
        }


class AudioActivityGate:
    def __init__(
        self,
        config: (
            AudioActivityGateConfig
            | None
        ) = None,
    ) -> None:
        self.config = (
            config
            or
            AudioActivityGateConfig()
        )

        pre_roll_capacity = max(
            1,
            self.config
            .pre_roll_chunks,
        )

        self._pre_roll: deque[
            bytes
        ] = (
            deque(
                maxlen=(
                    pre_roll_capacity
                )
            )
        )

        self._tx_active = False

        self._attack_progress = 0

        self._hang_remaining = 0

        self._noise_floor_dbfs = float(
            self.config
            .initial_noise_floor_dbfs
        )

        self._chunks_processed = 0

        self._tx_start_count = 0

        self._tx_end_count = 0

        self._active_output_chunks = 0

        self._active_output_bytes = 0

        self._last_level_dbfs = (
            self.config
            .silence_dbfs
        )


    @property
    def tx_active(
        self,
    ) -> bool:
        return self._tx_active


    @property
    def noise_floor_dbfs(
        self,
    ) -> float:
        return (
            self._noise_floor_dbfs
        )


    def _validate_chunk(
        self,
        chunk: bytes,
    ) -> bytes:
        if not isinstance(
            chunk,
            (
                bytes,
                bytearray,
                memoryview,
            ),
        ):
            raise (
                AudioActivityGateInputError(
                    (
                        "PCM chunk must be bytes, "
                        "bytearray or memoryview"
                    )
                )
            )

        payload = bytes(
            chunk
        )

        expected = (
            self.config
            .chunk_bytes
        )

        if (
            len(
                payload
            )
            !=
            expected
        ):
            raise (
                AudioActivityGateInputError(
                    (
                        "PCM chunk has invalid "
                        "size: expected "
                        f"{expected}, "
                        f"received {len(payload)}"
                    )
                )
            )

        return payload


    def _calculate_level_dbfs(
        self,
        chunk: bytes,
    ) -> float:
        sample_count = (
            len(
                chunk
            )
            //
            2
        )

        if sample_count <= 0:
            return (
                self.config
                .silence_dbfs
            )


        total_square = 0


        for (
            sample,
        ) in struct.iter_unpack(
            "<h",
            chunk,
        ):
            total_square += (
                sample
                *
                sample
            )


        if total_square <= 0:
            return (
                self.config
                .silence_dbfs
            )


        mean_square = (
            total_square
            /
            sample_count
        )


        rms = math.sqrt(
            mean_square
        )


        if rms <= 0:
            return (
                self.config
                .silence_dbfs
            )


        level_dbfs = (
            20.0
            *
            math.log10(
                rms
                /
                32768.0
            )
        )


        return max(
            self.config
            .silence_dbfs,
            level_dbfs,
        )


    def _clamp_noise_floor(
        self,
        value: float,
    ) -> float:
        return min(
            self.config
            .maximum_noise_floor_dbfs,

            max(
                self.config
                .minimum_noise_floor_dbfs,

                value,
            ),
        )


    def _update_noise_floor(
        self,
        level_dbfs: float,
    ) -> None:
        alpha = (
            self.config
            .noise_floor_alpha
        )


        updated = (
            (
                1.0
                -
                alpha
            )
            *
            self._noise_floor_dbfs
            +
            alpha
            *
            level_dbfs
        )


        self._noise_floor_dbfs = (
            self._clamp_noise_floor(
                updated
            )
        )


    def _thresholds(
        self,
    ) -> tuple[
        float,
        float,
    ]:
        adaptive_trigger = (
            self._noise_floor_dbfs
            +
            self.config
            .trigger_margin_db
        )


        trigger = max(
            self.config
            .minimum_trigger_dbfs,

            adaptive_trigger,
        )


        release = (
            trigger
            -
            self.config
            .hysteresis_db
        )


        return (
            trigger,
            release,
        )


    def _append_pre_roll(
        self,
        chunk: bytes,
    ) -> None:
        if (
            self.config
            .pre_roll_chunks
            <= 0
        ):
            return

        self._pre_roll.append(
            chunk
        )


    def _record_output(
        self,
        chunks: tuple[
            bytes,
            ...,
        ],
    ) -> None:
        self._active_output_chunks += (
            len(
                chunks
            )
        )

        self._active_output_bytes += sum(
            len(
                chunk
            )
            for chunk
            in chunks
        )


    def process_chunk(
        self,
        chunk: bytes,
    ) -> AudioActivityDecision:
        payload = (
            self._validate_chunk(
                chunk
            )
        )


        level_dbfs = (
            self._calculate_level_dbfs(
                payload
            )
        )


        self._last_level_dbfs = (
            level_dbfs
        )

        self._chunks_processed += 1


        (
            trigger_dbfs,
            release_dbfs,
        ) = self._thresholds()


        started = False

        ended = False

        signal_active = False

        output_chunks: tuple[
            bytes,
            ...,
        ] = ()


        if not self._tx_active:
            self._append_pre_roll(
                payload
            )


            signal_active = bool(
                level_dbfs
                >=
                trigger_dbfs
            )


            if signal_active:
                self._attack_progress += 1

            else:
                self._attack_progress = 0

                self._update_noise_floor(
                    level_dbfs
                )


            if (
                self._attack_progress
                >=
                self.config
                .attack_chunks
            ):
                self._tx_active = True

                started = True

                self._tx_start_count += 1

                self._hang_remaining = (
                    self.config
                    .hang_chunks
                )


                if (
                    self.config
                    .pre_roll_chunks
                    >
                    0
                ):
                    output_chunks = tuple(
                        self._pre_roll
                    )

                else:
                    output_chunks = (
                        payload,
                    )


                self._pre_roll.clear()

                self._attack_progress = 0


        else:
            signal_active = bool(
                level_dbfs
                >=
                release_dbfs
            )


            output_chunks = (
                payload,
            )


            if signal_active:
                self._hang_remaining = (
                    self.config
                    .hang_chunks
                )


            else:
                if (
                    self.config
                    .hang_chunks
                    <=
                    0
                ):
                    self._hang_remaining = 0

                    self._tx_active = False

                    ended = True


                else:
                    self._hang_remaining = max(
                        0,
                        self._hang_remaining
                        -
                        1,
                    )


                    if (
                        self._hang_remaining
                        <=
                        0
                    ):
                        self._tx_active = False

                        ended = True


                if ended:
                    self._tx_end_count += 1

                    self._attack_progress = 0

                    self._pre_roll.clear()

                    self._update_noise_floor(
                        level_dbfs
                    )


        if output_chunks:
            self._record_output(
                output_chunks
            )


        (
            final_trigger_dbfs,
            final_release_dbfs,
        ) = self._thresholds()


        return (
            AudioActivityDecision(
                level_dbfs=(
                    level_dbfs
                ),

                noise_floor_dbfs=(
                    self._noise_floor_dbfs
                ),

                trigger_dbfs=(
                    final_trigger_dbfs
                ),

                release_dbfs=(
                    final_release_dbfs
                ),

                signal_active=(
                    signal_active
                ),

                tx_active=(
                    self._tx_active
                ),

                started=(
                    started
                ),

                ended=(
                    ended
                ),

                output_chunks=(
                    output_chunks
                ),

                attack_progress_chunks=(
                    self._attack_progress
                ),

                hang_remaining_chunks=(
                    self._hang_remaining
                ),
            )
        )


    def reset(
        self,
    ) -> None:
        self._pre_roll.clear()

        self._tx_active = False

        self._attack_progress = 0

        self._hang_remaining = 0

        self._noise_floor_dbfs = float(
            self.config
            .initial_noise_floor_dbfs
        )

        self._chunks_processed = 0

        self._tx_start_count = 0

        self._tx_end_count = 0

        self._active_output_chunks = 0

        self._active_output_bytes = 0

        self._last_level_dbfs = (
            self.config
            .silence_dbfs
        )


    def status(
        self,
    ) -> dict[str, Any]:
        (
            trigger_dbfs,
            release_dbfs,
        ) = self._thresholds()


        return {
            "tx_active":
                self._tx_active,

            "last_level_dbfs":
                self._last_level_dbfs,

            "noise_floor_dbfs":
                self._noise_floor_dbfs,

            "trigger_dbfs":
                trigger_dbfs,

            "release_dbfs":
                release_dbfs,

            "attack_progress_chunks":
                self._attack_progress,

            "hang_remaining_chunks":
                self._hang_remaining,

            "pre_roll_buffer_chunks":
                len(
                    self._pre_roll
                ),

            "chunks_processed":
                self._chunks_processed,

            "tx_start_count":
                self._tx_start_count,

            "tx_end_count":
                self._tx_end_count,

            "active_output_chunks":
                self._active_output_chunks,

            "active_output_bytes":
                self._active_output_bytes,

            "config":
                self.config
                .status(),
        }
