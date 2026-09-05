from __future__ import annotations

import shutil
import subprocess

from dataclasses import (
    dataclass,
)

from typing import (
    Any,
)


DEFAULT_SAMPLE_RATE = 8000

DEFAULT_CHANNELS = 1

DEFAULT_SAMPLE_WIDTH_BYTES = 2

DEFAULT_SAMPLE_FORMAT = "s16le"

DEFAULT_TIMEOUT_SECONDS = 30.0

DEFAULT_MAX_INPUT_BYTES = (
    32
    * 1024
    * 1024
)


class AudioDecoderError(
    RuntimeError
):
    pass


class AudioDecoderUnavailableError(
    AudioDecoderError
):
    pass


@dataclass(
    frozen=True,
)
class DecodedAudio:
    pcm: bytes

    sample_rate: int

    channels: int

    sample_width_bytes: int

    sample_format: str

    input_content_type: str | None

    duration_seconds: float

    samples_per_channel: int


    @property
    def size_bytes(
        self,
    ) -> int:
        return len(
            self.pcm
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

            "sample_format":
                self.sample_format,

            "input_content_type":
                self.input_content_type,

            "duration_seconds":
                self.duration_seconds,

            "samples_per_channel":
                self.samples_per_channel,

            "size_bytes":
                self.size_bytes,
        }


class AudioDecoder:
    def __init__(
        self,
        *,
        ffmpeg_path:
            str
            | None = None,
        sample_rate: int = (
            DEFAULT_SAMPLE_RATE
        ),
        channels: int = (
            DEFAULT_CHANNELS
        ),
        timeout_seconds: float = (
            DEFAULT_TIMEOUT_SECONDS
        ),
        max_input_bytes: int = (
            DEFAULT_MAX_INPUT_BYTES
        ),
    ) -> None:
        if sample_rate <= 0:
            raise ValueError(
                (
                    "sample_rate must be "
                    "greater than zero"
                )
            )

        if channels <= 0:
            raise ValueError(
                (
                    "channels must be "
                    "greater than zero"
                )
            )

        if timeout_seconds <= 0:
            raise ValueError(
                (
                    "timeout_seconds must be "
                    "greater than zero"
                )
            )

        if max_input_bytes <= 0:
            raise ValueError(
                (
                    "max_input_bytes must be "
                    "greater than zero"
                )
            )

        resolved_ffmpeg = (
            ffmpeg_path
            or
            shutil.which(
                "ffmpeg"
            )
        )

        if not resolved_ffmpeg:
            raise (
                AudioDecoderUnavailableError(
                    (
                        "ffmpeg executable "
                        "was not found"
                    )
                )
            )

        self.ffmpeg_path = (
            resolved_ffmpeg
        )

        self.sample_rate = int(
            sample_rate
        )

        self.channels = int(
            channels
        )

        self.timeout_seconds = float(
            timeout_seconds
        )

        self.max_input_bytes = int(
            max_input_bytes
        )


    def _validate_input(
        self,
        audio: bytes,
    ) -> bytes:
        if not isinstance(
            audio,
            (
                bytes,
                bytearray,
                memoryview,
            ),
        ):
            raise TypeError(
                (
                    "audio must be bytes, "
                    "bytearray or memoryview"
                )
            )

        payload = bytes(
            audio
        )

        if not payload:
            raise (
                AudioDecoderError(
                    "audio input is empty"
                )
            )

        if (
            len(
                payload
            )
            >
            self.max_input_bytes
        ):
            raise (
                AudioDecoderError(
                    (
                        "audio input exceeds "
                        "maximum allowed size: "
                        f"{len(payload)} > "
                        f"{self.max_input_bytes}"
                    )
                )
            )

        return payload


    def _build_command(
        self,
    ) -> list[str]:
        return [
            self.ffmpeg_path,

            "-hide_banner",

            "-loglevel",
            "error",

            "-i",
            "pipe:0",

            "-map",
            "0:a:0",

            "-vn",

            "-sn",

            "-dn",

            "-ac",
            str(
                self.channels
            ),

            "-ar",
            str(
                self.sample_rate
            ),

            "-c:a",
            "pcm_s16le",

            "-f",
            DEFAULT_SAMPLE_FORMAT,

            "pipe:1",
        ]


    def decode(
        self,
        audio: bytes,
        *,
        content_type:
            str
            | None = None,
    ) -> DecodedAudio:
        payload = (
            self._validate_input(
                audio
            )
        )

        command = (
            self._build_command()
        )

        try:
            result = (
                subprocess.run(
                    command,
                    input=payload,
                    stdout=(
                        subprocess.PIPE
                    ),
                    stderr=(
                        subprocess.PIPE
                    ),
                    check=False,
                    timeout=(
                        self.timeout_seconds
                    ),
                )
            )

        except subprocess.TimeoutExpired as error:
            raise (
                AudioDecoderError(
                    (
                        "ffmpeg audio decode "
                        "timed out after "
                        f"{self.timeout_seconds} "
                        "seconds"
                    )
                )
            ) from error

        except OSError as error:
            raise (
                AudioDecoderError(
                    (
                        "failed to start ffmpeg: "
                        f"{error}"
                    )
                )
            ) from error

        stderr = (
            result.stderr
            .decode(
                "utf-8",
                errors="replace",
            )
            .strip()
        )

        if result.returncode != 0:
            message = (
                "ffmpeg audio decode failed"
            )

            if stderr:
                message += (
                    ": "
                    + stderr[
                        :2000
                    ]
                )

            raise (
                AudioDecoderError(
                    message
                )
            )

        pcm = bytes(
            result.stdout
        )

        if not pcm:
            raise (
                AudioDecoderError(
                    (
                        "ffmpeg returned "
                        "empty PCM output"
                    )
                )
            )

        bytes_per_frame = (
            DEFAULT_SAMPLE_WIDTH_BYTES
            *
            self.channels
        )

        if (
            len(
                pcm
            )
            %
            bytes_per_frame
            != 0
        ):
            raise (
                AudioDecoderError(
                    (
                        "decoded PCM length is "
                        "not aligned to the "
                        "configured frame size"
                    )
                )
            )

        frame_count = (
            len(
                pcm
            )
            //
            bytes_per_frame
        )

        duration_seconds = (
            frame_count
            /
            self.sample_rate
        )

        normalized_content_type = (
            content_type.strip()
            if (
                isinstance(
                    content_type,
                    str,
                )
                and
                content_type.strip()
            )
            else None
        )

        return (
            DecodedAudio(
                pcm=pcm,

                sample_rate=(
                    self.sample_rate
                ),

                channels=(
                    self.channels
                ),

                sample_width_bytes=(
                    DEFAULT_SAMPLE_WIDTH_BYTES
                ),

                sample_format=(
                    DEFAULT_SAMPLE_FORMAT
                ),

                input_content_type=(
                    normalized_content_type
                ),

                duration_seconds=(
                    duration_seconds
                ),

                samples_per_channel=(
                    frame_count
                ),
            )
        )


audio_decoder = (
    AudioDecoder()
)
