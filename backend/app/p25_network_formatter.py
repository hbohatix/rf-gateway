from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


IMBE_BYTES_PER_FRAME = 11

P25_FRAMES_PER_LDU = 9

P25_LDU_AUDIO_DURATION_SECONDS = (
    P25_FRAMES_PER_LDU
    * 0.020
)

P25_SUPERFRAME_AUDIO_FRAMES = (
    P25_FRAMES_PER_LDU
    * 2
)

P25_SUPERFRAME_AUDIO_DURATION_SECONDS = (
    P25_SUPERFRAME_AUDIO_FRAMES
    * 0.020
)


class P25NetworkFormatterError(
    ValueError
):
    pass


@dataclass(
    frozen=True,
)
class P25NetworkRecord:
    record_type: int
    data: bytes
    imbe_index: int | None = None

    @property
    def size_bytes(
        self,
    ) -> int:
        return len(
            self.data
        )

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "record_type": (
                f"0x{self.record_type:02X}"
            ),
            "size_bytes": (
                self.size_bytes
            ),
            "imbe_index": (
                self.imbe_index
            ),
        }


@dataclass(
    frozen=True,
)
class P25NetworkLDU:
    kind: str
    records: tuple[
        P25NetworkRecord,
        ...
    ]

    @property
    def record_count(
        self,
    ) -> int:
        return len(
            self.records
        )

    @property
    def datagrams(
        self,
    ) -> tuple[
        bytes,
        ...
    ]:
        return tuple(
            record.data
            for record
            in self.records
        )

    @property
    def size_bytes(
        self,
    ) -> int:
        return sum(
            record.size_bytes
            for record
            in self.records
        )

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "record_count": (
                self.record_count
            ),
            "size_bytes": (
                self.size_bytes
            ),
            "audio_frames": (
                P25_FRAMES_PER_LDU
            ),
            "audio_duration_seconds": (
                P25_LDU_AUDIO_DURATION_SECONDS
            ),
            "records": [
                record.status()
                for record
                in self.records
            ],
        }


@dataclass(
    frozen=True,
)
class P25NetworkSuperframe:
    ldu1: P25NetworkLDU
    ldu2: P25NetworkLDU

    @property
    def records(
        self,
    ) -> tuple[
        P25NetworkRecord,
        ...
    ]:
        return (
            self.ldu1.records
            + self.ldu2.records
        )

    @property
    def datagrams(
        self,
    ) -> tuple[
        bytes,
        ...
    ]:
        return tuple(
            record.data
            for record
            in self.records
        )

    @property
    def record_count(
        self,
    ) -> int:
        return len(
            self.records
        )

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "record_count": (
                self.record_count
            ),
            "audio_frames": (
                P25_SUPERFRAME_AUDIO_FRAMES
            ),
            "audio_duration_seconds": (
                P25_SUPERFRAME_AUDIO_DURATION_SECONDS
            ),
            "ldu1": (
                self.ldu1.status()
            ),
            "ldu2": (
                self.ldu2.status()
            ),
        }


REC62 = bytes(
    [
        0x62,
        0x02,
        0x02,
        0x0C,
        0x0B,
        0x12,
        0x64,
        0x00,
        0x00,
        0x80,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)

REC63 = bytes(
    [
        0x63,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC64 = bytes(
    [
        0x64,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC65 = bytes(
    [
        0x65,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC66 = bytes(
    [
        0x66,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC67 = bytes(
    [
        0x67,
        0xF0,
        0x9D,
        0x6A,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC68 = bytes(
    [
        0x68,
        0x19,
        0xD4,
        0x26,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC69 = bytes(
    [
        0x69,
        0xE0,
        0xEB,
        0x7B,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC6A = bytes(
    [
        0x6A,
        0x00,
        0x00,
        0x02,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)

REC6B = bytes(
    [
        0x6B,
        0x02,
        0x02,
        0x0C,
        0x0B,
        0x12,
        0x64,
        0x00,
        0x00,
        0x80,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)

REC6C = bytes(
    [
        0x6C,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC6D = bytes(
    [
        0x6D,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC6E = bytes(
    [
        0x6E,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC6F = bytes(
    [
        0x6F,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC70 = bytes(
    [
        0x70,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC71 = bytes(
    [
        0x71,
        0xAC,
        0xB8,
        0xA4,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC72 = bytes(
    [
        0x72,
        0x9B,
        0xDC,
        0x75,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
    ]
)

REC73 = bytes(
    [
        0x73,
        0x00,
        0x00,
        0x02,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)

REC80 = bytes(
    [
        0x80,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)


def _require_byte(
    value: int,
    name: str,
) -> int:
    value = int(
        value
    )

    if not 0 <= value <= 0xFF:
        raise P25NetworkFormatterError(
            f"{name} must be between "
            "0 and 255"
        )

    return value


def _require_uint16(
    value: int,
    name: str,
) -> int:
    value = int(
        value
    )

    if not 0 <= value <= 0xFFFF:
        raise P25NetworkFormatterError(
            f"{name} must be between "
            "0 and 65535"
        )

    return value


def _require_uint24(
    value: int,
    name: str,
) -> int:
    value = int(
        value
    )

    if not 0 <= value <= 0xFFFFFF:
        raise P25NetworkFormatterError(
            f"{name} must be between "
            "0 and 16777215"
        )

    return value


def _uint16_be(
    value: int,
) -> bytes:
    return bytes(
        [
            (
                value
                >> 8
            )
            & 0xFF,
            value
            & 0xFF,
        ]
    )


def _uint24_be(
    value: int,
) -> bytes:
    return bytes(
        [
            (
                value
                >> 16
            )
            & 0xFF,
            (
                value
                >> 8
            )
            & 0xFF,
            value
            & 0xFF,
        ]
    )


def _normalize_imbe_frames(
    frames: Iterable[
        bytes
    ],
) -> tuple[
    bytes,
    ...
]:
    normalized = tuple(
        bytes(
            frame
        )
        for frame
        in frames
    )

    if (
        len(normalized)
        != P25_FRAMES_PER_LDU
    ):
        raise P25NetworkFormatterError(
            "P25 LDU requires exactly "
            f"{P25_FRAMES_PER_LDU} "
            "IMBE frames"
        )

    for index, frame in enumerate(
        normalized
    ):
        if (
            len(frame)
            != IMBE_BYTES_PER_FRAME
        ):
            raise P25NetworkFormatterError(
                "IMBE frame "
                f"{index} must contain "
                f"{IMBE_BYTES_PER_FRAME} "
                "bytes"
            )

    return normalized


def _insert(
    template: bytes,
    offset: int,
    payload: bytes,
) -> bytearray:
    result = bytearray(
        template
    )

    end = (
        offset
        + len(
            payload
        )
    )

    if end > len(
        result
    ):
        raise P25NetworkFormatterError(
            "Payload exceeds "
            "P25 record size"
        )

    result[
        offset:end
    ] = payload

    return result


class P25NetworkFormatter:
    def format_ldu1(
        self,
        imbe_frames: Iterable[
            bytes
        ],
        *,
        source_id: int,
        destination_id: int,
        lcf: int = 0x00,
        mfid: int = 0x00,
        lsd1: int = 0x00,
        lsd2: int = 0x00,
    ) -> P25NetworkLDU:
        frames = (
            _normalize_imbe_frames(
                imbe_frames
            )
        )

        source_id = (
            _require_uint24(
                source_id,
                "source_id",
            )
        )

        destination_id = (
            _require_uint24(
                destination_id,
                "destination_id",
            )
        )

        lcf = _require_byte(
            lcf,
            "lcf",
        )

        mfid = _require_byte(
            mfid,
            "mfid",
        )

        lsd1 = _require_byte(
            lsd1,
            "lsd1",
        )

        lsd2 = _require_byte(
            lsd2,
            "lsd2",
        )

        records: list[
            P25NetworkRecord
        ] = []

        record = _insert(
            REC62,
            10,
            frames[0],
        )

        records.append(
            P25NetworkRecord(
                record_type=0x62,
                data=bytes(
                    record
                ),
                imbe_index=0,
            )
        )

        record = _insert(
            REC63,
            1,
            frames[1],
        )

        records.append(
            P25NetworkRecord(
                record_type=0x63,
                data=bytes(
                    record
                ),
                imbe_index=1,
            )
        )

        record = bytearray(
            REC64
        )

        record[1] = lcf
        record[2] = mfid

        record[
            5:16
        ] = frames[2]

        records.append(
            P25NetworkRecord(
                record_type=0x64,
                data=bytes(
                    record
                ),
                imbe_index=2,
            )
        )

        record = bytearray(
            REC65
        )

        record[
            1:4
        ] = _uint24_be(
            destination_id
        )

        record[
            5:16
        ] = frames[3]

        records.append(
            P25NetworkRecord(
                record_type=0x65,
                data=bytes(
                    record
                ),
                imbe_index=3,
            )
        )

        record = bytearray(
            REC66
        )

        record[
            1:4
        ] = _uint24_be(
            source_id
        )

        record[
            5:16
        ] = frames[4]

        records.append(
            P25NetworkRecord(
                record_type=0x66,
                data=bytes(
                    record
                ),
                imbe_index=4,
            )
        )

        for (
            record_type,
            template,
            frame_index,
        ) in (
            (
                0x67,
                REC67,
                5,
            ),
            (
                0x68,
                REC68,
                6,
            ),
            (
                0x69,
                REC69,
                7,
            ),
        ):
            record = _insert(
                template,
                5,
                frames[
                    frame_index
                ],
            )

            records.append(
                P25NetworkRecord(
                    record_type=(
                        record_type
                    ),
                    data=bytes(
                        record
                    ),
                    imbe_index=(
                        frame_index
                    ),
                )
            )

        record = bytearray(
            REC6A
        )

        record[1] = lsd1
        record[2] = lsd2

        record[
            4:15
        ] = frames[8]

        records.append(
            P25NetworkRecord(
                record_type=0x6A,
                data=bytes(
                    record
                ),
                imbe_index=8,
            )
        )

        return P25NetworkLDU(
            kind="ldu1",
            records=tuple(
                records
            ),
        )

    def format_ldu2(
        self,
        imbe_frames: Iterable[
            bytes
        ],
        *,
        message_indicator: bytes,
        algorithm_id: int,
        key_id: int,
        lsd1: int = 0x00,
        lsd2: int = 0x00,
    ) -> P25NetworkLDU:
        frames = (
            _normalize_imbe_frames(
                imbe_frames
            )
        )

        message_indicator = bytes(
            message_indicator
        )

        if (
            len(
                message_indicator
            )
            != 9
        ):
            raise P25NetworkFormatterError(
                "P25 message_indicator "
                "must contain exactly "
                "9 bytes"
            )

        algorithm_id = (
            _require_byte(
                algorithm_id,
                "algorithm_id",
            )
        )

        key_id = (
            _require_uint16(
                key_id,
                "key_id",
            )
        )

        lsd1 = _require_byte(
            lsd1,
            "lsd1",
        )

        lsd2 = _require_byte(
            lsd2,
            "lsd2",
        )

        records: list[
            P25NetworkRecord
        ] = []

        record = _insert(
            REC6B,
            10,
            frames[0],
        )

        records.append(
            P25NetworkRecord(
                record_type=0x6B,
                data=bytes(
                    record
                ),
                imbe_index=0,
            )
        )

        record = _insert(
            REC6C,
            1,
            frames[1],
        )

        records.append(
            P25NetworkRecord(
                record_type=0x6C,
                data=bytes(
                    record
                ),
                imbe_index=1,
            )
        )

        for (
            record_type,
            template,
            frame_index,
            mi_offset,
        ) in (
            (
                0x6D,
                REC6D,
                2,
                0,
            ),
            (
                0x6E,
                REC6E,
                3,
                3,
            ),
            (
                0x6F,
                REC6F,
                4,
                6,
            ),
        ):
            record = bytearray(
                template
            )

            record[
                1:4
            ] = (
                message_indicator[
                    mi_offset:
                    mi_offset + 3
                ]
            )

            record[
                5:16
            ] = frames[
                frame_index
            ]

            records.append(
                P25NetworkRecord(
                    record_type=(
                        record_type
                    ),
                    data=bytes(
                        record
                    ),
                    imbe_index=(
                        frame_index
                    ),
                )
            )

        record = bytearray(
            REC70
        )

        record[1] = (
            algorithm_id
        )

        record[
            2:4
        ] = _uint16_be(
            key_id
        )

        record[
            5:16
        ] = frames[5]

        records.append(
            P25NetworkRecord(
                record_type=0x70,
                data=bytes(
                    record
                ),
                imbe_index=5,
            )
        )

        for (
            record_type,
            template,
            frame_index,
        ) in (
            (
                0x71,
                REC71,
                6,
            ),
            (
                0x72,
                REC72,
                7,
            ),
        ):
            record = _insert(
                template,
                5,
                frames[
                    frame_index
                ],
            )

            records.append(
                P25NetworkRecord(
                    record_type=(
                        record_type
                    ),
                    data=bytes(
                        record
                    ),
                    imbe_index=(
                        frame_index
                    ),
                )
            )

        record = bytearray(
            REC73
        )

        record[1] = lsd1
        record[2] = lsd2

        record[
            4:15
        ] = frames[8]

        records.append(
            P25NetworkRecord(
                record_type=0x73,
                data=bytes(
                    record
                ),
                imbe_index=8,
            )
        )

        return P25NetworkLDU(
            kind="ldu2",
            records=tuple(
                records
            ),
        )

    def format_superframe(
        self,
        imbe_frames: Iterable[
            bytes
        ],
        *,
        source_id: int,
        destination_id: int,
        lcf: int,
        mfid: int,
        message_indicator: bytes,
        algorithm_id: int,
        key_id: int,
        lsd1: int = 0x00,
        lsd2: int = 0x00,
    ) -> P25NetworkSuperframe:
        frames = tuple(
            bytes(
                frame
            )
            for frame
            in imbe_frames
        )

        if (
            len(frames)
            != P25_SUPERFRAME_AUDIO_FRAMES
        ):
            raise P25NetworkFormatterError(
                "P25 network superframe "
                "requires exactly "
                f"{P25_SUPERFRAME_AUDIO_FRAMES} "
                "IMBE frames"
            )

        ldu1 = self.format_ldu1(
            frames[
                0:
                P25_FRAMES_PER_LDU
            ],
            source_id=(
                source_id
            ),
            destination_id=(
                destination_id
            ),
            lcf=lcf,
            mfid=mfid,
            lsd1=lsd1,
            lsd2=lsd2,
        )

        ldu2 = self.format_ldu2(
            frames[
                P25_FRAMES_PER_LDU:
                P25_SUPERFRAME_AUDIO_FRAMES
            ],
            message_indicator=(
                message_indicator
            ),
            algorithm_id=(
                algorithm_id
            ),
            key_id=(
                key_id
            ),
            lsd1=lsd1,
            lsd2=lsd2,
        )

        return P25NetworkSuperframe(
            ldu1=ldu1,
            ldu2=ldu2,
        )

    def terminator(
        self,
    ) -> P25NetworkRecord:
        return P25NetworkRecord(
            record_type=0x80,
            data=REC80,
            imbe_index=None,
        )


p25_network_formatter = (
    P25NetworkFormatter()
)
