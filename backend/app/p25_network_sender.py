from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Iterable

from app.p25_network_formatter import (
    P25NetworkLDU,
    P25NetworkRecord,
    P25NetworkSuperframe,
)


DEFAULT_LOCAL_ADDRESS = "127.0.0.1"
DEFAULT_LOCAL_PORT = 42020

DEFAULT_MMDVM_ADDRESS = "127.0.0.1"
DEFAULT_MMDVM_PORT = 32010

P25_FRAME_INTERVAL_SECONDS = 0.020


class P25NetworkSenderError(
    RuntimeError
):
    pass


@dataclass(
    frozen=True,
)
class P25NetworkSenderStats:
    datagrams_sent: int
    bytes_sent: int
    last_record_type: int | None

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "datagrams_sent": (
                self.datagrams_sent
            ),
            "bytes_sent": (
                self.bytes_sent
            ),
            "last_record_type": (
                (
                    f"0x{self.last_record_type:02X}"
                )
                if self.last_record_type
                is not None
                else None
            ),
        }


class P25NetworkSender:
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

        self._socket: (
            socket.socket
            | None
        ) = None

        self._lock = Lock()

        self._datagrams_sent = 0
        self._bytes_sent = 0

        self._last_record_type: (
            int
            | None
        ) = None

        self._last_error: (
            str
            | None
        ) = None

    @property
    def local_address(
        self,
    ) -> str:
        return self._local_address

    @property
    def local_port(
        self,
    ) -> int:
        return self._local_port

    @property
    def mmdvm_address(
        self,
    ) -> str:
        return self._mmdvm_address

    @property
    def mmdvm_port(
        self,
    ) -> int:
        return self._mmdvm_port

    @property
    def is_open(
        self,
    ) -> bool:
        return (
            self._socket
            is not None
        )

    @property
    def last_error(
        self,
    ) -> str | None:
        return self._last_error

    def open(
        self,
    ) -> None:
        with self._lock:
            if (
                self._socket
                is not None
            ):
                return

            udp_socket = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
            )

            try:
                udp_socket.bind(
                    (
                        self._local_address,
                        self._local_port,
                    )
                )

            except Exception:
                udp_socket.close()
                raise

            self._socket = (
                udp_socket
            )

            self._last_error = None

    def close(
        self,
    ) -> None:
        with self._lock:
            udp_socket = (
                self._socket
            )

            self._socket = None

            if (
                udp_socket
                is not None
            ):
                udp_socket.close()

    def reset_stats(
        self,
    ) -> None:
        with self._lock:
            self._datagrams_sent = 0
            self._bytes_sent = 0
            self._last_record_type = None
            self._last_error = None

    def stats(
        self,
    ) -> P25NetworkSenderStats:
        with self._lock:
            return (
                P25NetworkSenderStats(
                    datagrams_sent=(
                        self._datagrams_sent
                    ),
                    bytes_sent=(
                        self._bytes_sent
                    ),
                    last_record_type=(
                        self._last_record_type
                    ),
                )
            )

    def status(
        self,
    ) -> dict[str, Any]:
        stats = self.stats()

        return {
            "open": (
                self.is_open
            ),
            "local_address": (
                self._local_address
            ),
            "local_port": (
                self._local_port
            ),
            "mmdvm_address": (
                self._mmdvm_address
            ),
            "mmdvm_port": (
                self._mmdvm_port
            ),
            "frame_interval_seconds": (
                P25_FRAME_INTERVAL_SECONDS
            ),
            "last_error": (
                self._last_error
            ),
            "stats": (
                stats.status()
            ),
        }

    def _require_socket(
        self,
    ) -> socket.socket:
        udp_socket = (
            self._socket
        )

        if (
            udp_socket
            is None
        ):
            raise P25NetworkSenderError(
                "P25 network sender "
                "is not open"
            )

        return udp_socket

    def send_datagram(
        self,
        data: bytes,
        *,
        record_type: int | None = None,
    ) -> int:
        payload = bytes(
            data
        )

        if not payload:
            raise P25NetworkSenderError(
                "Cannot send empty "
                "P25 datagram"
            )

        with self._lock:
            udp_socket = (
                self._require_socket()
            )

            try:
                sent = (
                    udp_socket.sendto(
                        payload,
                        (
                            self._mmdvm_address,
                            self._mmdvm_port,
                        ),
                    )
                )

            except OSError as error:
                self._last_error = str(
                    error
                )

                raise (
                    P25NetworkSenderError(
                        "Unable to send "
                        "P25 UDP datagram: "
                        f"{error}"
                    )
                ) from error

            if (
                sent
                != len(payload)
            ):
                self._last_error = (
                    "Partial UDP datagram send"
                )

                raise P25NetworkSenderError(
                    "Partial P25 UDP "
                    "datagram send"
                )

            self._datagrams_sent += 1
            self._bytes_sent += sent

            self._last_record_type = (
                record_type
            )

            self._last_error = None

            return sent

    def send_record(
        self,
        record: P25NetworkRecord,
    ) -> int:
        if not isinstance(
            record,
            P25NetworkRecord,
        ):
            raise TypeError(
                "record must be "
                "P25NetworkRecord"
            )

        if not record.data:
            raise P25NetworkSenderError(
                "P25 record has no data"
            )

        if (
            record.data[0]
            != record.record_type
        ):
            raise P25NetworkSenderError(
                "P25 record type does "
                "not match first byte"
            )

        return self.send_datagram(
            record.data,
            record_type=(
                record.record_type
            ),
        )

    def send_records(
        self,
        records: Iterable[
            P25NetworkRecord
        ],
        *,
        paced: bool = True,
        interval_seconds: float = (
            P25_FRAME_INTERVAL_SECONDS
        ),
    ) -> int:
        interval_seconds = float(
            interval_seconds
        )

        if (
            interval_seconds
            < 0.0
        ):
            raise ValueError(
                "interval_seconds "
                "cannot be negative"
            )

        normalized = tuple(
            records
        )

        total_bytes = 0

        next_send_time = (
            time.monotonic()
        )

        for index, record in enumerate(
            normalized
        ):
            if (
                paced
                and index > 0
            ):
                next_send_time += (
                    interval_seconds
                )

                delay = (
                    next_send_time
                    - time.monotonic()
                )

                if (
                    delay > 0.0
                ):
                    time.sleep(
                        delay
                    )

            total_bytes += (
                self.send_record(
                    record
                )
            )

        return total_bytes

    def send_ldu(
        self,
        ldu: P25NetworkLDU,
        *,
        paced: bool = True,
    ) -> int:
        if not isinstance(
            ldu,
            P25NetworkLDU,
        ):
            raise TypeError(
                "ldu must be "
                "P25NetworkLDU"
            )

        return self.send_records(
            ldu.records,
            paced=paced,
        )

    def send_superframe(
        self,
        superframe: (
            P25NetworkSuperframe
        ),
        *,
        paced: bool = True,
    ) -> int:
        if not isinstance(
            superframe,
            P25NetworkSuperframe,
        ):
            raise TypeError(
                "superframe must be "
                "P25NetworkSuperframe"
            )

        return self.send_records(
            superframe.records,
            paced=paced,
        )

    def __enter__(
        self,
    ) -> P25NetworkSender:
        self.open()

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


p25_network_sender = (
    P25NetworkSender()
)
