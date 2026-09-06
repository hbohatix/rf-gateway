from __future__ import annotations

import time

from copy import deepcopy

from threading import (
    RLock,
)

from typing import (
    Any,
)

from app.config_store import (
    mode_config_store,
)

from app.imbe_encoder import (
    IMBEEncoderError,
    IMBEEncoderUnavailableError,
    PCM_BYTES_PER_FRAME,
    imbe_encoder,
)

from app.p25_network_formatter import (
    P25NetworkFormatter,
    P25NetworkFormatterError,
    P25NetworkRecord,
)

from app.p25_network_sender import (
    DEFAULT_LOCAL_ADDRESS,
    DEFAULT_LOCAL_PORT,
    DEFAULT_MMDVM_ADDRESS,
    DEFAULT_MMDVM_PORT,
    P25NetworkSender,
    P25NetworkSenderError,
)


P25_FRAME_INTERVAL_SECONDS = 0.020

P25_IMBE_FRAMES_PER_LDU = 9

P25_LCF_GROUP = 0x00

P25_MFID_STANDARD = 0x00

P25_ALGO_UNENCRYPT = 0x80

P25_KEY_ID_CLEAR = 0x0000

P25_MESSAGE_INDICATOR_CLEAR = bytes(
    9
)

P25_NULL_IMBE = bytes.fromhex(
    "040cfd7bfb7df27b3d9e45"
)


class P25StreamingSessionError(
    RuntimeError
):
    pass


class P25StreamingSessionConfigurationError(
    P25StreamingSessionError
):
    pass


class P25StreamingSessionInputError(
    P25StreamingSessionError
):
    pass


class P25StreamingSession:
    def __init__(
        self,
        *,
        local_address: str = (
            DEFAULT_LOCAL_ADDRESS
        ),
        local_port: int = (
            DEFAULT_LOCAL_PORT
        ),
        mmdvm_address: str = (
            DEFAULT_MMDVM_ADDRESS
        ),
        mmdvm_port: int = (
            DEFAULT_MMDVM_PORT
        ),
        mode_config: (
            dict[str, Any]
            | None
        ) = None,
    ) -> None:
        self._local_address = str(
            local_address
        )

        self._local_port = int(
            local_port
        )

        self._mmdvm_address = str(
            mmdvm_address
        )

        self._mmdvm_port = int(
            mmdvm_port
        )

        self._supplied_mode_config = (
            deepcopy(
                mode_config
            )
            if mode_config
            is not None
            else None
        )

        self._formatter = (
            P25NetworkFormatter()
        )

        self._sender: (
            P25NetworkSender
            | None
        ) = None

        self._lock = (
            RLock()
        )

        self._active = False

        self._source_id: (
            int
            | None
        ) = None

        self._destination_id: (
            int
            | None
        ) = None

        self._next_ldu = "ldu1"

        self._imbe_buffer: list[
            bytes
        ] = []

        self._next_send_at: (
            float
            | None
        ) = None

        self._started_at: (
            float
            | None
        ) = None

        self._ended_at: (
            float
            | None
        ) = None

        self._pcm_frames_received = 0

        self._pcm_bytes_received = 0

        self._imbe_frames_encoded = 0

        self._padding_imbe_frames = 0

        self._ldu1_count = 0

        self._ldu2_count = 0

        self._network_records_sent = 0

        self._network_bytes_sent = 0

        self._terminator_bytes_sent = 0


    @property
    def active(
        self,
    ) -> bool:
        return (
            self._active
        )


    def _load_mode_config(
        self,
    ) -> dict[str, Any]:
        if (
            self._supplied_mode_config
            is not None
        ):
            config = deepcopy(
                self._supplied_mode_config
            )

        else:
            try:
                config = (
                    mode_config_store
                    .get_mode(
                        "p25"
                    )
                )

            except Exception as error:
                raise (
                    P25StreamingSessionConfigurationError(
                        (
                            "Unable to load "
                            "P25 mode configuration: "
                            f"{error}"
                        )
                    )
                ) from error


        if not isinstance(
            config,
            dict,
        ):
            raise (
                P25StreamingSessionConfigurationError(
                    (
                        "P25 mode configuration "
                        "is not available"
                    )
                )
            )


        return config


    def _validate_mode_config(
        self,
        config: dict[str, Any],
    ) -> tuple[
        int,
        int,
    ]:
        modulation = (
            str(
                config.get(
                    "modulation",
                    "",
                )
            )
            .strip()
            .lower()
        )


        if modulation != "c4fm":
            raise (
                P25StreamingSessionConfigurationError(
                    (
                        "Unsupported P25 "
                        "modulation: "
                        f"{modulation or 'missing'}"
                    )
                )
            )


        try:
            source_id = int(
                config[
                    "radio_id"
                ]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise (
                P25StreamingSessionConfigurationError(
                    (
                        "P25 radio_id is "
                        "missing or invalid"
                    )
                )
            ) from error


        try:
            destination_id = int(
                config[
                    "talkgroup"
                ]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise (
                P25StreamingSessionConfigurationError(
                    (
                        "P25 talkgroup is "
                        "missing or invalid"
                    )
                )
            ) from error


        if not (
            1
            <= source_id
            <= 0xFFFFFF
        ):
            raise (
                P25StreamingSessionConfigurationError(
                    (
                        "P25 radio_id must be "
                        "between 1 and 16777215"
                    )
                )
            )


        if not (
            1
            <= destination_id
            <= 0xFFFFFF
        ):
            raise (
                P25StreamingSessionConfigurationError(
                    (
                        "P25 talkgroup must be "
                        "between 1 and 16777215"
                    )
                )
            )


        return (
            source_id,
            destination_id,
        )


    def _require_active(
        self,
    ) -> None:
        if not self._active:
            raise (
                P25StreamingSessionError(
                    (
                        "P25 streaming session "
                        "is not active"
                    )
                )
            )


    def _require_sender(
        self,
    ) -> P25NetworkSender:
        sender = (
            self._sender
        )


        if sender is None:
            raise (
                P25StreamingSessionError(
                    (
                        "P25 network sender "
                        "is not available"
                    )
                )
            )


        return sender


    def _validate_pcm(
        self,
        pcm: bytes,
    ) -> bytes:
        if not isinstance(
            pcm,
            (
                bytes,
                bytearray,
                memoryview,
            ),
        ):
            raise (
                P25StreamingSessionInputError(
                    (
                        "PCM input must be bytes, "
                        "bytearray or memoryview"
                    )
                )
            )


        payload = bytes(
            pcm
        )


        if not payload:
            raise (
                P25StreamingSessionInputError(
                    "PCM input is empty"
                )
            )


        if (
            len(
                payload
            )
            %
            PCM_BYTES_PER_FRAME
            !=
            0
        ):
            raise (
                P25StreamingSessionInputError(
                    (
                        "PCM input must contain "
                        "complete 20 ms frames of "
                        f"{PCM_BYTES_PER_FRAME} bytes"
                    )
                )
            )


        return payload


    def _pace_and_send_record(
        self,
        record:
            P25NetworkRecord,
    ) -> int:
        sender = (
            self._require_sender()
        )


        now = (
            time.monotonic()
        )


        if (
            self._next_send_at
            is None
        ):
            self._next_send_at = (
                now
            )


        delay = (
            self._next_send_at
            -
            now
        )


        if delay > 0:
            time.sleep(
                delay
            )


        try:
            sent = (
                sender.send_record(
                    record
                )
            )

        except (
            P25NetworkSenderError,
            OSError,
        ) as error:
            raise (
                P25StreamingSessionError(
                    (
                        "Unable to send "
                        "P25 network record: "
                        f"{error}"
                    )
                )
            ) from error


        self._network_records_sent += 1

        self._network_bytes_sent += (
            sent
        )

        self._next_send_at += (
            P25_FRAME_INTERVAL_SECONDS
        )


        return sent


    def _send_records(
        self,
        records,
    ) -> None:
        for record in records:
            self._pace_and_send_record(
                record
            )


    def _format_and_send_ldu(
        self,
        frames: list[
            bytes
        ],
    ) -> None:
        if (
            len(
                frames
            )
            !=
            P25_IMBE_FRAMES_PER_LDU
        ):
            raise (
                P25StreamingSessionError(
                    (
                        "P25 LDU requires "
                        "exactly 9 IMBE frames"
                    )
                )
            )


        source_id = (
            self._source_id
        )

        destination_id = (
            self._destination_id
        )


        if (
            source_id is None
            or
            destination_id is None
        ):
            raise (
                P25StreamingSessionError(
                    (
                        "P25 source or "
                        "destination ID "
                        "is not configured"
                    )
                )
            )


        try:
            if (
                self._next_ldu
                ==
                "ldu1"
            ):
                ldu = (
                    self._formatter
                    .format_ldu1(
                        frames,

                        source_id=(
                            source_id
                        ),

                        destination_id=(
                            destination_id
                        ),

                        lcf=(
                            P25_LCF_GROUP
                        ),

                        mfid=(
                            P25_MFID_STANDARD
                        ),

                        lsd1=0x00,

                        lsd2=0x00,
                    )
                )

                self._ldu1_count += 1

                self._next_ldu = (
                    "ldu2"
                )


            else:
                ldu = (
                    self._formatter
                    .format_ldu2(
                        frames,

                        message_indicator=(
                            P25_MESSAGE_INDICATOR_CLEAR
                        ),

                        algorithm_id=(
                            P25_ALGO_UNENCRYPT
                        ),

                        key_id=(
                            P25_KEY_ID_CLEAR
                        ),

                        lsd1=0x00,

                        lsd2=0x00,
                    )
                )

                self._ldu2_count += 1

                self._next_ldu = (
                    "ldu1"
                )


        except P25NetworkFormatterError as error:
            raise (
                P25StreamingSessionError(
                    (
                        "P25 network framing "
                        f"failed: {error}"
                    )
                )
            ) from error


        self._send_records(
            ldu.records
        )


    def _flush_complete_ldus(
        self,
    ) -> None:
        while (
            len(
                self._imbe_buffer
            )
            >=
            P25_IMBE_FRAMES_PER_LDU
        ):
            frames = (
                self._imbe_buffer[
                    :
                    P25_IMBE_FRAMES_PER_LDU
                ]
            )

            del self._imbe_buffer[
                :
                P25_IMBE_FRAMES_PER_LDU
            ]


            self._format_and_send_ldu(
                frames
            )


    def start(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            if self._active:
                return (
                    self.status()
                )


            encoder_status = (
                imbe_encoder.status()
            )


            if not (
                encoder_status.get(
                    "available",
                    False,
                )
            ):
                raise (
                    P25StreamingSessionError(
                        (
                            "P25 IMBE encoder "
                            "is unavailable: "
                            f"{encoder_status.get('load_error')}"
                        )
                    )
                )


            config = (
                self._load_mode_config()
            )


            (
                source_id,
                destination_id,
            ) = (
                self._validate_mode_config(
                    config
                )
            )


            sender = (
                P25NetworkSender(
                    local_address=(
                        self._local_address
                    ),

                    local_port=(
                        self._local_port
                    ),

                    mmdvm_address=(
                        self._mmdvm_address
                    ),

                    mmdvm_port=(
                        self._mmdvm_port
                    ),
                )
            )


            try:
                sender.open()

            except (
                P25NetworkSenderError,
                OSError,
            ) as error:
                raise (
                    P25StreamingSessionError(
                        (
                            "Unable to open "
                            "P25 network sender: "
                            f"{error}"
                        )
                    )
                ) from error


            self._sender = sender

            self._source_id = (
                source_id
            )

            self._destination_id = (
                destination_id
            )

            self._next_ldu = (
                "ldu1"
            )

            self._imbe_buffer.clear()

            self._next_send_at = None

            self._started_at = (
                time.monotonic()
            )

            self._ended_at = None

            self._pcm_frames_received = 0

            self._pcm_bytes_received = 0

            self._imbe_frames_encoded = 0

            self._padding_imbe_frames = 0

            self._ldu1_count = 0

            self._ldu2_count = 0

            self._network_records_sent = 0

            self._network_bytes_sent = 0

            self._terminator_bytes_sent = 0

            self._active = True


            return (
                self.status()
            )


    def feed_pcm(
        self,
        pcm: bytes,
    ) -> dict[str, Any]:
        with self._lock:
            self._require_active()

            payload = (
                self._validate_pcm(
                    pcm
                )
            )


            for offset in range(
                0,
                len(
                    payload
                ),
                PCM_BYTES_PER_FRAME,
            ):
                frame_pcm = (
                    payload[
                        offset:
                        offset
                        +
                        PCM_BYTES_PER_FRAME
                    ]
                )


                try:
                    encoded = (
                        imbe_encoder
                        .encode_frame(
                            frame_pcm
                        )
                    )

                except (
                    IMBEEncoderError,
                    IMBEEncoderUnavailableError,
                ) as error:
                    raise (
                        P25StreamingSessionError(
                            (
                                "P25 IMBE encode "
                                f"failed: {error}"
                            )
                        )
                    ) from error


                self._imbe_buffer.append(
                    bytes(
                        encoded.data
                    )
                )

                self._pcm_frames_received += 1

                self._pcm_bytes_received += (
                    len(
                        frame_pcm
                    )
                )

                self._imbe_frames_encoded += 1


            self._flush_complete_ldus()


            return (
                self.status()
            )


    def end(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return (
                    self.status()
                )


            try:
                if self._imbe_buffer:
                    padding_needed = (
                        P25_IMBE_FRAMES_PER_LDU
                        -
                        len(
                            self._imbe_buffer
                        )
                    )


                    if padding_needed < 0:
                        raise (
                            P25StreamingSessionError(
                                (
                                    "Internal P25 "
                                    "IMBE buffer overflow"
                                )
                            )
                        )


                    self._imbe_buffer.extend(
                        P25_NULL_IMBE

                        for _
                        in range(
                            padding_needed
                        )
                    )

                    self._padding_imbe_frames += (
                        padding_needed
                    )


                    self._flush_complete_ldus()


                terminator = (
                    self._formatter
                    .terminator()
                )


                terminator_bytes = (
                    self._pace_and_send_record(
                        terminator
                    )
                )

                self._terminator_bytes_sent = (
                    terminator_bytes
                )


                self._ended_at = (
                    time.monotonic()
                )


            finally:
                sender = (
                    self._sender
                )

                self._active = False

                self._sender = None

                self._next_send_at = None

                self._imbe_buffer.clear()


                if sender is not None:
                    try:
                        sender.close()

                    except Exception:
                        pass


            return (
                self.status()
            )


    def close(
        self,
    ) -> dict[str, Any]:
        return (
            self.end()
        )


    def status(
        self,
    ) -> dict[str, Any]:
        now = (
            time.monotonic()
        )


        if self._started_at is None:
            duration_seconds = 0.0

        elif self._ended_at is not None:
            duration_seconds = (
                self._ended_at
                -
                self._started_at
            )

        else:
            duration_seconds = (
                now
                -
                self._started_at
            )


        sender_status = None


        if self._sender is not None:
            try:
                sender_status = (
                    self._sender
                    .status()
                )

            except Exception:
                sender_status = None


        return {
            "active":
                self._active,

            "source_id":
                self._source_id,

            "destination_id":
                self._destination_id,

            "next_ldu":
                self._next_ldu,

            "buffered_imbe_frames":
                len(
                    self._imbe_buffer
                ),

            "pcm_frames_received":
                self._pcm_frames_received,

            "pcm_bytes_received":
                self._pcm_bytes_received,

            "imbe_frames_encoded":
                self._imbe_frames_encoded,

            "padding_imbe_frames":
                self._padding_imbe_frames,

            "ldu1_count":
                self._ldu1_count,

            "ldu2_count":
                self._ldu2_count,

            "network_records_sent":
                self._network_records_sent,

            "network_bytes_sent":
                self._network_bytes_sent,

            "terminator_bytes_sent":
                self._terminator_bytes_sent,

            "duration_seconds":
                duration_seconds,

            "sender":
                sender_status,
        }


    def __enter__(
        self,
    ) -> "P25StreamingSession":
        self.start()

        return self


    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        try:
            self.end()

        except Exception:
            pass
