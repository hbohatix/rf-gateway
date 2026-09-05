from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


PCM_SAMPLE_RATE = 8000
PCM_CHANNELS = 1
PCM_SAMPLE_WIDTH_BYTES = 2

PCM_SAMPLES_PER_FRAME = 160
PCM_BYTES_PER_FRAME = (
    PCM_SAMPLES_PER_FRAME
    * PCM_SAMPLE_WIDTH_BYTES
)

IMBE_BYTES_PER_FRAME = 11

FRAME_DURATION_SECONDS = (
    PCM_SAMPLES_PER_FRAME
    / PCM_SAMPLE_RATE
)


class IMBEEncoderError(
    RuntimeError
):
    pass


class IMBEEncoderUnavailableError(
    IMBEEncoderError
):
    pass


@dataclass(
    frozen=True,
)
class EncodedIMBEFrame:
    data: bytes
    pcm_samples: int
    pcm_bytes: int
    imbe_bytes: int
    sample_rate: int
    channels: int
    sample_width_bytes: int
    duration_seconds: float

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "pcm_samples": (
                self.pcm_samples
            ),
            "pcm_bytes": (
                self.pcm_bytes
            ),
            "imbe_bytes": (
                self.imbe_bytes
            ),
            "sample_rate": (
                self.sample_rate
            ),
            "channels": (
                self.channels
            ),
            "sample_width_bytes": (
                self.sample_width_bytes
            ),
            "duration_seconds": (
                self.duration_seconds
            ),
        }


class IMBEEncoder:
    def __init__(
        self,
        library_path: (
            str
            | Path
            | None
        ) = None,
    ) -> None:
        self._library_path = (
            Path(
                library_path
            )
            if library_path
            is not None
            else (
                Path(__file__)
                .resolve()
                .parent
                .parent
                / "native"
                / (
                    "libimbe_vocoder_"
                    "wrapper.so"
                )
            )
        )

        self._library: (
            ctypes.CDLL
            | None
        ) = None

        self._handle: (
            int
            | None
        ) = None

        self._lock = Lock()

        self._load_error: (
            str
            | None
        ) = None

        self._load()

    @property
    def library_path(
        self,
    ) -> Path:
        return self._library_path

    @property
    def available(
        self,
    ) -> bool:
        return (
            self._library
            is not None
            and self._handle
            is not None
        )

    @property
    def load_error(
        self,
    ) -> str | None:
        return self._load_error

    def _load(
        self,
    ) -> None:
        if not (
            self._library_path
            .is_file()
        ):
            self._load_error = (
                "IMBE wrapper library "
                "not found: "
                f"{self._library_path}"
            )

            return

        try:
            library = ctypes.CDLL(
                str(
                    self._library_path
                )
            )

            library.rf_gateway_imbe_create.restype = (
                ctypes.c_void_p
            )

            library.rf_gateway_imbe_destroy.argtypes = [
                ctypes.c_void_p,
            ]

            library.rf_gateway_imbe_destroy.restype = (
                None
            )

            library.rf_gateway_imbe_encode_4400.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(
                    ctypes.c_int16
                ),
                ctypes.c_size_t,
                ctypes.POINTER(
                    ctypes.c_uint8
                ),
                ctypes.c_size_t,
            ]

            library.rf_gateway_imbe_encode_4400.restype = (
                ctypes.c_int
            )

            library.rf_gateway_imbe_pcm_samples_per_frame.restype = (
                ctypes.c_size_t
            )

            library.rf_gateway_imbe_pcm_bytes_per_frame.restype = (
                ctypes.c_size_t
            )

            library.rf_gateway_imbe_bytes_per_frame.restype = (
                ctypes.c_size_t
            )

            pcm_samples = int(
                library
                .rf_gateway_imbe_pcm_samples_per_frame()
            )

            pcm_bytes = int(
                library
                .rf_gateway_imbe_pcm_bytes_per_frame()
            )

            imbe_bytes = int(
                library
                .rf_gateway_imbe_bytes_per_frame()
            )

            if (
                pcm_samples
                != PCM_SAMPLES_PER_FRAME
            ):
                raise IMBEEncoderError(
                    "Unexpected IMBE encoder "
                    "PCM frame size: "
                    f"{pcm_samples}"
                )

            if (
                pcm_bytes
                != PCM_BYTES_PER_FRAME
            ):
                raise IMBEEncoderError(
                    "Unexpected IMBE encoder "
                    "PCM byte size: "
                    f"{pcm_bytes}"
                )

            if (
                imbe_bytes
                != IMBE_BYTES_PER_FRAME
            ):
                raise IMBEEncoderError(
                    "Unexpected IMBE encoder "
                    "output size: "
                    f"{imbe_bytes}"
                )

            handle = (
                library
                .rf_gateway_imbe_create()
            )

            if not handle:
                raise IMBEEncoderError(
                    "Unable to create "
                    "IMBE vocoder instance"
                )

            self._library = (
                library
            )

            self._handle = int(
                handle
            )

            self._load_error = None

        except Exception as error:
            self._library = None
            self._handle = None
            self._load_error = str(
                error
            )

    def close(
        self,
    ) -> None:
        with self._lock:
            if (
                self._library
                is None
                or self._handle
                is None
            ):
                return

            self._library.rf_gateway_imbe_destroy(
                ctypes.c_void_p(
                    self._handle
                )
            )

            self._handle = None

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "available": (
                self.available
            ),
            "library_path": str(
                self._library_path
            ),
            "load_error": (
                self._load_error
            ),
            "sample_rate": (
                PCM_SAMPLE_RATE
            ),
            "channels": (
                PCM_CHANNELS
            ),
            "sample_width_bytes": (
                PCM_SAMPLE_WIDTH_BYTES
            ),
            "pcm_samples_per_frame": (
                PCM_SAMPLES_PER_FRAME
            ),
            "pcm_bytes_per_frame": (
                PCM_BYTES_PER_FRAME
            ),
            "imbe_bytes_per_frame": (
                IMBE_BYTES_PER_FRAME
            ),
            "frame_duration_seconds": (
                FRAME_DURATION_SECONDS
            ),
        }

    def encode_frame(
        self,
        pcm: bytes,
    ) -> EncodedIMBEFrame:
        if not self.available:
            raise (
                IMBEEncoderUnavailableError(
                    self._load_error
                    or (
                        "IMBE encoder "
                        "is unavailable"
                    )
                )
            )

        if (
            len(pcm)
            != PCM_BYTES_PER_FRAME
        ):
            raise IMBEEncoderError(
                "IMBE encoder requires "
                f"exactly "
                f"{PCM_BYTES_PER_FRAME} "
                "PCM bytes per frame; "
                f"received {len(pcm)}"
            )

        library = (
            self._library
        )

        handle = (
            self._handle
        )

        if (
            library is None
            or handle is None
        ):
            raise (
                IMBEEncoderUnavailableError(
                    "IMBE encoder "
                    "is unavailable"
                )
            )

        PCMArray = (
            ctypes.c_int16
            * PCM_SAMPLES_PER_FRAME
        )

        IMBEArray = (
            ctypes.c_uint8
            * IMBE_BYTES_PER_FRAME
        )

        pcm_array = (
            PCMArray
            .from_buffer_copy(
                pcm
            )
        )

        imbe_array = (
            IMBEArray()
        )

        with self._lock:
            result = (
                library
                .rf_gateway_imbe_encode_4400(
                    ctypes.c_void_p(
                        handle
                    ),
                    pcm_array,
                    PCM_SAMPLES_PER_FRAME,
                    imbe_array,
                    IMBE_BYTES_PER_FRAME,
                )
            )

        if result != 0:
            raise IMBEEncoderError(
                "IMBE encode failed "
                f"with result {result}"
            )

        encoded = bytes(
            imbe_array
        )

        if (
            len(encoded)
            != IMBE_BYTES_PER_FRAME
        ):
            raise IMBEEncoderError(
                "IMBE encoder returned "
                "unexpected frame size"
            )

        return EncodedIMBEFrame(
            data=encoded,
            pcm_samples=(
                PCM_SAMPLES_PER_FRAME
            ),
            pcm_bytes=(
                PCM_BYTES_PER_FRAME
            ),
            imbe_bytes=(
                IMBE_BYTES_PER_FRAME
            ),
            sample_rate=(
                PCM_SAMPLE_RATE
            ),
            channels=(
                PCM_CHANNELS
            ),
            sample_width_bytes=(
                PCM_SAMPLE_WIDTH_BYTES
            ),
            duration_seconds=(
                FRAME_DURATION_SECONDS
            ),
        )

    def encode_pcm(
        self,
        pcm: bytes,
        *,
        pad_final_frame: bool = True,
    ) -> list[
        EncodedIMBEFrame
    ]:
        if not isinstance(
            pcm,
            bytes,
        ):
            raise TypeError(
                "PCM input must be bytes"
            )

        if not pcm:
            return []

        if (
            len(pcm)
            % PCM_SAMPLE_WIDTH_BYTES
            != 0
        ):
            raise IMBEEncoderError(
                "PCM input is not aligned "
                "to 16-bit samples"
            )

        frames: list[
            EncodedIMBEFrame
        ] = []

        offset = 0

        while (
            offset
            < len(pcm)
        ):
            frame = pcm[
                offset:
                offset
                + PCM_BYTES_PER_FRAME
            ]

            offset += (
                PCM_BYTES_PER_FRAME
            )

            if (
                len(frame)
                < PCM_BYTES_PER_FRAME
            ):
                if not (
                    pad_final_frame
                ):
                    break

                frame = (
                    frame
                    + bytes(
                        PCM_BYTES_PER_FRAME
                        - len(frame)
                    )
                )

            frames.append(
                self.encode_frame(
                    frame
                )
            )

        return frames

    def __enter__(
        self,
    ) -> IMBEEncoder:
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()

    def __del__(
        self,
    ) -> None:
        try:
            self.close()

        except Exception:
            pass


imbe_encoder = (
    IMBEEncoder()
)
