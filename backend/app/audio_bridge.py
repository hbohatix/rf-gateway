from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
import time
from typing import Any, Literal

from app.config_store import (
    mode_config_store,
)

from app.imbe_encoder import (
    IMBEEncoderError,
    IMBEEncoderUnavailableError,
    PCM_CHANNELS,
    PCM_SAMPLE_RATE,
    PCM_SAMPLE_WIDTH_BYTES,
    imbe_encoder,
)

from app.p25_network_formatter import (
    P25NetworkFormatter,
    P25NetworkFormatterError,
)

from app.p25_network_sender import (
    DEFAULT_LOCAL_ADDRESS,
    DEFAULT_LOCAL_PORT,
    DEFAULT_MMDVM_ADDRESS,
    DEFAULT_MMDVM_PORT,
    P25NetworkSender,
    P25NetworkSenderError,
)


Protocol = Literal[
    "fm",
    "dmr",
    "p25",
    "tetra",
]


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

P25_IMBE_FRAMES_PER_SUPERFRAME = 18
P25_FRAME_INTERVAL_SECONDS = 0.020


class AudioBridgeError(
    RuntimeError
):
    pass


class AudioBridgeUnavailableError(
    AudioBridgeError
):
    pass


class AudioBridgeConfigurationError(
    AudioBridgeError
):
    pass


class AudioBridgeInputError(
    AudioBridgeError
):
    pass


@dataclass(
    frozen=True,
)
class P25AudioBridgeResult:
    source_id: int
    destination_id: int

    input_pcm_bytes: int
    input_duration_seconds: float

    encoded_imbe_frames: int
    padding_imbe_frames: int
    transmitted_imbe_frames: int

    superframes: int
    network_records: int

    network_bytes: int
    terminator_bytes: int

    transmitted_duration_seconds: float

    sender_stats: dict[str, Any]


    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "protocol":
                "p25",

            "source_id":
                self.source_id,

            "destination_id":
                self.destination_id,

            "input_pcm_bytes":
                self.input_pcm_bytes,

            "input_duration_seconds":
                self.input_duration_seconds,

            "encoded_imbe_frames":
                self.encoded_imbe_frames,

            "padding_imbe_frames":
                self.padding_imbe_frames,

            "transmitted_imbe_frames":
                self.transmitted_imbe_frames,

            "superframes":
                self.superframes,

            "network_records":
                self.network_records,

            "network_bytes":
                self.network_bytes,

            "terminator_bytes":
                self.terminator_bytes,

            "transmitted_duration_seconds":
                self.transmitted_duration_seconds,

            "sender_stats":
                deepcopy(
                    self.sender_stats
                ),
        }


CAPABILITIES = {
    "fm": {
        "protocol":
            "fm",

        "audio_input_supported":
            False,

        "encoder_required":
            False,

        "framing_required":
            False,

        "bridge_state":
            "not_implemented",

        "blocking_reason":
            "fm_audio_bridge_not_implemented",
    },

    "dmr": {
        "protocol":
            "dmr",

        "audio_input_supported":
            False,

        "encoder_required":
            True,

        "framing_required":
            True,

        "bridge_state":
            "not_implemented",

        "blocking_reason":
            "dmr_vocoder_and_framing_not_implemented",
    },

    "p25": {
        "protocol":
            "p25",

        "audio_input_supported":
            True,

        "encoder_required":
            True,

        "framing_required":
            True,

        "bridge_state":
            "ready",

        "blocking_reason":
            None,

        "audio_format": {
            "sample_rate":
                PCM_SAMPLE_RATE,

            "channels":
                PCM_CHANNELS,

            "sample_width_bytes":
                PCM_SAMPLE_WIDTH_BYTES,

            "sample_format":
                "s16le",
        },

        "vocoder": {
            "name":
                "IMBE",

            "frame_samples":
                160,

            "frame_bytes":
                11,

            "frame_duration_seconds":
                P25_FRAME_INTERVAL_SECONDS,
        },

        "network": {
            "local_address":
                DEFAULT_LOCAL_ADDRESS,

            "local_port":
                DEFAULT_LOCAL_PORT,

            "mmdvm_address":
                DEFAULT_MMDVM_ADDRESS,

            "mmdvm_port":
                DEFAULT_MMDVM_PORT,
        },
    },

    "tetra": {
        "protocol":
            "tetra",

        "audio_input_supported":
            False,

        "encoder_required":
            True,

        "framing_required":
            True,

        "bridge_state":
            "not_implemented",

        "blocking_reason":
            "tetra_vocoder_and_framing_not_implemented",
    },
}


def _normalize_protocol(
    protocol: str,
) -> str:
    return (
        str(
            protocol
        )
        .strip()
        .lower()
    )


def get_audio_bridge_capability(
    protocol: Protocol,
) -> dict:
    normalized_protocol = (
        _normalize_protocol(
            protocol
        )
    )

    capability = (
        CAPABILITIES.get(
            normalized_protocol
        )
    )

    if capability is None:
        raise ValueError(
            (
                "Unsupported protocol: "
                f"{protocol}"
            )
        )

    result = deepcopy(
        capability
    )

    if (
        normalized_protocol
        == "p25"
    ):
        encoder_status = (
            imbe_encoder.status()
        )

        result[
            "encoder"
        ] = deepcopy(
            encoder_status
        )

        if not (
            encoder_status.get(
                "available",
                False,
            )
        ):
            result[
                "bridge_state"
            ] = "unavailable"

            result[
                "blocking_reason"
            ] = (
                "p25_imbe_encoder_unavailable"
            )

    return result


def audio_bridge_ready(
    protocol: Protocol,
) -> bool:
    capability = (
        get_audio_bridge_capability(
            protocol
        )
    )

    return bool(
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


def get_all_audio_bridge_capabilities() -> dict:
    return {
        protocol:
            get_audio_bridge_capability(
                protocol
            )

        for protocol
        in CAPABILITIES
    }


class P25AudioBridge:
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

        self._formatter = (
            P25NetworkFormatter()
        )

        self._lock = (
            RLock()
        )


    def _load_mode_config(
        self,
        mode_config: (
            dict[str, Any]
            | None
        ),
    ) -> dict[str, Any]:
        if (
            mode_config
            is not None
        ):
            config = deepcopy(
                mode_config
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
                    AudioBridgeConfigurationError(
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
                AudioBridgeConfigurationError(
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

        if (
            modulation
            != "c4fm"
        ):
            raise (
                AudioBridgeConfigurationError(
                    (
                        "Unsupported P25 modulation: "
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
                AudioBridgeConfigurationError(
                    (
                        "P25 radio_id is missing "
                        "or invalid"
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
                AudioBridgeConfigurationError(
                    (
                        "P25 talkgroup is missing "
                        "or invalid"
                    )
                )
            ) from error

        if not (
            1
            <= source_id
            <= 0xFFFFFF
        ):
            raise (
                AudioBridgeConfigurationError(
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
                AudioBridgeConfigurationError(
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


    def _validate_audio(
        self,
        decoded_audio: Any,
    ) -> bytes:
        pcm = getattr(
            decoded_audio,
            "pcm",
            None,
        )

        sample_rate = getattr(
            decoded_audio,
            "sample_rate",
            None,
        )

        channels = getattr(
            decoded_audio,
            "channels",
            None,
        )

        sample_width_bytes = getattr(
            decoded_audio,
            "sample_width_bytes",
            None,
        )

        if not isinstance(
            pcm,
            (
                bytes,
                bytearray,
            ),
        ):
            raise (
                AudioBridgeInputError(
                    (
                        "Decoded audio does not "
                        "contain PCM bytes"
                    )
                )
            )

        pcm_bytes = bytes(
            pcm
        )

        if not pcm_bytes:
            raise (
                AudioBridgeInputError(
                    "Decoded PCM is empty"
                )
            )

        if (
            sample_rate
            != PCM_SAMPLE_RATE
        ):
            raise (
                AudioBridgeInputError(
                    (
                        "P25 bridge requires "
                        f"{PCM_SAMPLE_RATE} Hz PCM; "
                        f"received {sample_rate}"
                    )
                )
            )

        if (
            channels
            != PCM_CHANNELS
        ):
            raise (
                AudioBridgeInputError(
                    (
                        "P25 bridge requires "
                        f"{PCM_CHANNELS} channel; "
                        f"received {channels}"
                    )
                )
            )

        if (
            sample_width_bytes
            != PCM_SAMPLE_WIDTH_BYTES
        ):
            raise (
                AudioBridgeInputError(
                    (
                        "P25 bridge requires "
                        f"{PCM_SAMPLE_WIDTH_BYTES}-byte "
                        "PCM samples; "
                        "received "
                        f"{sample_width_bytes}"
                    )
                )
            )

        if (
            len(
                pcm_bytes
            )
            %
            PCM_SAMPLE_WIDTH_BYTES
            != 0
        ):
            raise (
                AudioBridgeInputError(
                    (
                        "Decoded PCM is not aligned "
                        "to 16-bit samples"
                    )
                )
            )

        return pcm_bytes


    def transmit(
        self,
        decoded_audio: Any,
        *,
        mode_config: (
            dict[str, Any]
            | None
        ) = None,
    ) -> P25AudioBridgeResult:
        capability = (
            get_audio_bridge_capability(
                "p25"
            )
        )

        if not (
            capability.get(
                "bridge_state"
            )
            == "ready"
        ):
            raise (
                AudioBridgeUnavailableError(
                    (
                        capability.get(
                            "blocking_reason"
                        )
                        or
                        "P25 audio bridge "
                        "is unavailable"
                    )
                )
            )

        config = (
            self._load_mode_config(
                mode_config
            )
        )

        (
            source_id,
            destination_id,
        ) = (
            self._validate_mode_config(
                config
            )
        )

        pcm = (
            self._validate_audio(
                decoded_audio
            )
        )

        with self._lock:
            try:
                encoded_frames = (
                    imbe_encoder
                    .encode_pcm(
                        pcm,
                        pad_final_frame=True,
                    )
                )

            except (
                IMBEEncoderError,
                IMBEEncoderUnavailableError,
            ) as error:
                raise (
                    AudioBridgeError(
                        (
                            "P25 IMBE encode failed: "
                            f"{error}"
                        )
                    )
                ) from error

            if not encoded_frames:
                raise (
                    AudioBridgeError(
                        (
                            "P25 IMBE encoder "
                            "returned no frames"
                        )
                    )
                )

            imbe_frames = [
                bytes(
                    frame.data
                )

                for frame
                in encoded_frames
            ]

            encoded_frame_count = (
                len(
                    imbe_frames
                )
            )

            remainder = (
                encoded_frame_count
                %
                P25_IMBE_FRAMES_PER_SUPERFRAME
            )

            padding_frames = 0

            if remainder:
                padding_frames = (
                    P25_IMBE_FRAMES_PER_SUPERFRAME
                    - remainder
                )

                imbe_frames.extend(
                    P25_NULL_IMBE

                    for _
                    in range(
                        padding_frames
                    )
                )

            records = []

            try:
                for offset in range(
                    0,
                    len(
                        imbe_frames
                    ),
                    P25_IMBE_FRAMES_PER_SUPERFRAME,
                ):
                    chunk = (
                        imbe_frames[
                            offset:
                            offset
                            + P25_IMBE_FRAMES_PER_SUPERFRAME
                        ]
                    )

                    superframe = (
                        self._formatter
                        .format_superframe(
                            chunk,

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

                    records.extend(
                        superframe.records
                    )

            except (
                P25NetworkFormatterError
            ) as error:
                raise (
                    AudioBridgeError(
                        (
                            "P25 network framing "
                            f"failed: {error}"
                        )
                    )
                ) from error

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
                with sender:
                    network_bytes = (
                        sender.send_records(
                            records,
                            paced=True,
                        )
                    )

                    time.sleep(
                        P25_FRAME_INTERVAL_SECONDS
                    )

                    terminator_bytes = (
                        sender.send_record(
                            self._formatter
                            .terminator()
                        )
                    )

                    sender_stats = (
                        sender
                        .stats()
                        .status()
                    )

            except (
                P25NetworkSenderError,
                OSError,
            ) as error:
                raise (
                    AudioBridgeError(
                        (
                            "P25 network hand-off "
                            f"failed: {error}"
                        )
                    )
                ) from error

        transmitted_frame_count = (
            len(
                imbe_frames
            )
        )

        superframe_count = (
            transmitted_frame_count
            //
            P25_IMBE_FRAMES_PER_SUPERFRAME
        )

        input_duration_seconds = (
            len(
                pcm
            )
            /
            (
                PCM_SAMPLE_RATE
                *
                PCM_CHANNELS
                *
                PCM_SAMPLE_WIDTH_BYTES
            )
        )

        transmitted_duration_seconds = (
            transmitted_frame_count
            *
            P25_FRAME_INTERVAL_SECONDS
        )

        return (
            P25AudioBridgeResult(
                source_id=(
                    source_id
                ),

                destination_id=(
                    destination_id
                ),

                input_pcm_bytes=(
                    len(
                        pcm
                    )
                ),

                input_duration_seconds=(
                    input_duration_seconds
                ),

                encoded_imbe_frames=(
                    encoded_frame_count
                ),

                padding_imbe_frames=(
                    padding_frames
                ),

                transmitted_imbe_frames=(
                    transmitted_frame_count
                ),

                superframes=(
                    superframe_count
                ),

                network_records=(
                    len(
                        records
                    )
                ),

                network_bytes=(
                    network_bytes
                ),

                terminator_bytes=(
                    terminator_bytes
                ),

                transmitted_duration_seconds=(
                    transmitted_duration_seconds
                ),

                sender_stats=(
                    sender_stats
                ),
            )
        )


p25_audio_bridge = (
    P25AudioBridge()
)


def bridge_decoded_audio(
    protocol: Protocol,
    decoded_audio: Any,
    *,
    mode_config: (
        dict[str, Any]
        | None
    ) = None,
) -> dict[str, Any]:
    normalized_protocol = (
        _normalize_protocol(
            protocol
        )
    )

    if (
        normalized_protocol
        != "p25"
    ):
        capability = (
            get_audio_bridge_capability(
                normalized_protocol
            )
        )

        raise (
            AudioBridgeUnavailableError(
                (
                    capability.get(
                        "blocking_reason"
                    )
                    or
                    (
                        "Audio bridge is not "
                        "implemented for protocol "
                        f"{normalized_protocol}"
                    )
                )
            )
        )

    result = (
        p25_audio_bridge
        .transmit(
            decoded_audio,
            mode_config=(
                mode_config
            ),
        )
    )

    return result.status()