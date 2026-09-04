from __future__ import annotations

import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, TextIO

from app.rf.soapysdr import (
    mark_driver_closed,
    mark_driver_open,
)

from .config_generator import (
    validate_runtime_mode,
    write_mmdvm_host_config,
)


PROJECT_DIR = (
    Path(__file__)
    .resolve()
    .parents[3]
)

MMDVM_IQ_DIR = (
    PROJECT_DIR
    / "third_party"
    / "MMDVM-IQ"
)

MMDVM_HOST_DIR = (
    PROJECT_DIR
    / "third_party"
    / "MMDVM-Host"
)

MMDVM_IQ_BINARY = (
    MMDVM_IQ_DIR
    / "MMDVM-IQ"
)

MMDVM_HOST_BINARY = (
    MMDVM_HOST_DIR
    / "MMDVM-Host"
)

MMDVM_IQ_CONFIG = (
    PROJECT_DIR
    / "config"
    / "mmdvm"
    / "MMDVM-IQ.ini"
)

RUNTIME_DIR = (
    PROJECT_DIR
    / "backend"
    / "data"
    / "runtime"
    / "mmdvm"
)

MMDVM_HOST_RUNTIME_CONFIG = (
    RUNTIME_DIR
    / "MMDVM-Host.ini"
)

MMDVM_IQ_LOG = (
    RUNTIME_DIR
    / "MMDVM-IQ.log"
)

MMDVM_HOST_LOG = (
    RUNTIME_DIR
    / "MMDVM-Host.log"
)


class MMDVMProcessManager:
    def __init__(
        self,
    ) -> None:
        self._lock = (
            threading.RLock()
        )

        self._iq_process: (
            subprocess.Popen[Any]
            | None
        ) = None

        self._host_process: (
            subprocess.Popen[Any]
            | None
        ) = None

        self._iq_log_handle: (
            TextIO
            | None
        ) = None

        self._host_log_handle: (
            TextIO
            | None
        ) = None

        self._protocol: (
            str
            | None
        ) = None

        self._settings: (
            dict[str, Any]
            | None
        ) = None

        self._last_error: (
            str
            | None
        ) = None


    @staticmethod
    def _process_running(
        process: (
            subprocess.Popen[Any]
            | None
        ),
    ) -> bool:
        return (
            process is not None
            and process.poll() is None
        )


    @staticmethod
    def _udp_port_bound(
        port: int,
    ) -> bool:
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        try:
            sock.bind(
                (
                    "127.0.0.1",
                    port,
                )
            )

            return False

        except OSError:
            return True

        finally:
            sock.close()


    @staticmethod
    def _tail_file(
        path: Path,
        lines: int = 60,
    ) -> str:
        if not path.exists():
            return ""

        try:
            content = (
                path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                .splitlines()
            )

        except OSError:
            return ""

        return "\n".join(
            content[-lines:]
        )


    @staticmethod
    def _read_recent_text(
        path: Path,
        max_bytes: int = 512 * 1024,
    ) -> str:
        if not path.exists():
            return ""

        try:
            with path.open(
                "rb"
            ) as file:
                file.seek(
                    0,
                    os.SEEK_END,
                )

                size = (
                    file.tell()
                )

                offset = max(
                    0,
                    size - max_bytes,
                )

                file.seek(
                    offset,
                    os.SEEK_SET,
                )

                data = (
                    file.read()
                )

        except OSError:
            return ""

        return data.decode(
            "utf-8",
            errors="replace",
        )


    def _parse_iq_telemetry(
        self,
        *,
        iq_running: bool,
    ) -> dict[str, Any]:
        text = (
            self._read_recent_text(
                MMDVM_IQ_LOG
            )
        )

        modem_mode: (
            str
            | None
        ) = None

        rf_tx_active = False

        sdr_tx_center_frequency_hz: (
            int
            | None
        ) = None

        sdr_rx_center_frequency_hz: (
            int
            | None
        ) = None

        sample_rate_hz: (
            int
            | None
        ) = None

        actual_tx_rate_hz: (
            int
            | None
        ) = None

        actual_rx_rate_hz: (
            int
            | None
        ) = None

        hardware_version: (
            str
            | None
        ) = None

        driver_name: (
            str
            | None
        ) = None

        setup_complete = False


        for line in (
            text.splitlines()
        ):
            mode_match = (
                re.search(
                    r"Mode set to\s+(.+?)\s*$",
                    line,
                )
            )

            if mode_match:
                modem_mode = (
                    mode_match
                    .group(1)
                    .strip()
                )


            if re.search(
                r"\bTX ON\b",
                line,
            ):
                rf_tx_active = True


            if re.search(
                r"\bTX OFF\b",
                line,
            ):
                rf_tx_active = False


            tx_frequency_match = (
                re.search(
                    r"TX Frequency:\s+"
                    r"([0-9]+)\s+Hz",
                    line,
                )
            )

            if tx_frequency_match:
                sdr_tx_center_frequency_hz = int(
                    tx_frequency_match.group(1)
                )


            rx_frequency_match = (
                re.search(
                    r"RX Frequency:\s+"
                    r"([0-9]+)\s+Hz",
                    line,
                )
            )

            if rx_frequency_match:
                sdr_rx_center_frequency_hz = int(
                    rx_frequency_match.group(1)
                )


            sample_rate_match = (
                re.search(
                    r"Sample Rate:\s+"
                    r"([0-9]+)\s+samples/sec",
                    line,
                )
            )

            if sample_rate_match:
                sample_rate_hz = int(
                    sample_rate_match.group(1)
                )


            actual_tx_rate_match = (
                re.search(
                    r"Actual TX Rate:\s+"
                    r"([0-9]+)\s+samples/sec",
                    line,
                )
            )

            if actual_tx_rate_match:
                actual_tx_rate_hz = int(
                    actual_tx_rate_match.group(1)
                )


            actual_rx_rate_match = (
                re.search(
                    r"Actual RX Rate:\s+"
                    r"([0-9]+)\s+samples/sec",
                    line,
                )
            )

            if actual_rx_rate_match:
                actual_rx_rate_hz = int(
                    actual_rx_rate_match.group(1)
                )


            hardware_match = (
                re.search(
                    r"Hardware version\s+(.+?)\s*$",
                    line,
                )
            )

            if hardware_match:
                hardware_version = (
                    hardware_match
                    .group(1)
                    .strip()
                )


            driver_match = (
                re.search(
                    r"Using\s+(.+?)\s+driver",
                    line,
                )
            )

            if driver_match:
                driver_name = (
                    driver_match
                    .group(1)
                    .strip()
                )


            if (
                "SoapySDR device setup done"
                in line
            ):
                setup_complete = True


        if not iq_running:
            modem_mode = None
            rf_tx_active = False
            setup_complete = False


        return {
            "ready":
                iq_running
                and setup_complete,

            "hardware_open":
                iq_running
                and setup_complete,

            "iq_streams_active":
                iq_running
                and setup_complete,

            "modem_mode":
                modem_mode,

            "rf_tx_active":
                (
                    rf_tx_active
                    if iq_running
                    else False
                ),

            "sdr_tx_center_frequency_hz":
                sdr_tx_center_frequency_hz,

            "sdr_rx_center_frequency_hz":
                sdr_rx_center_frequency_hz,

            "sample_rate_hz":
                (
                    actual_tx_rate_hz
                    or actual_rx_rate_hz
                    or sample_rate_hz
                ),

            "actual_tx_rate_hz":
                actual_tx_rate_hz,

            "actual_rx_rate_hz":
                actual_rx_rate_hz,

            "hardware_version":
                hardware_version,

            "driver_name":
                driver_name,
        }


    def _host_ready(
        self,
        *,
        host_running: bool,
    ) -> bool:
        if not host_running:
            return False

        text = (
            self._read_recent_text(
                MMDVM_HOST_LOG
            )
        )

        return (
            "Starting protocol handlers"
            in text
        )


    def _wait_for_udp_port(
        self,
        *,
        port: int,
        process: subprocess.Popen[Any],
        process_name: str,
        timeout: float,
        log_path: Path,
    ) -> None:
        deadline = (
            time.monotonic()
            + timeout
        )

        while (
            time.monotonic()
            < deadline
        ):
            if (
                process.poll()
                is not None
            ):
                log_tail = (
                    self._tail_file(
                        log_path
                    )
                )

                raise RuntimeError(
                    f"{process_name} exited "
                    f"with code "
                    f"{process.returncode}.\n"
                    f"{log_tail}"
                )

            if self._udp_port_bound(
                port
            ):
                return

            time.sleep(
                0.1
            )

        raise RuntimeError(
            f"{process_name} did not "
            f"open UDP port {port} "
            f"within {timeout:.1f}s"
        )


    def _wait_for_host_ready(
        self,
        *,
        timeout: float = 10.0,
    ) -> None:
        if (
            self._host_process
            is None
        ):
            raise RuntimeError(
                "MMDVM-Host process "
                "does not exist"
            )

        deadline = (
            time.monotonic()
            + timeout
        )

        ready_markers = (
            "Starting protocol handlers",
        )

        failure_markers = (
            "Received a NAK",
            "cannot read the .ini file",
            "unable to open",
            "Error opening",
        )


        while (
            time.monotonic()
            < deadline
        ):
            if (
                self._host_process.poll()
                is not None
            ):
                log_tail = (
                    self._tail_file(
                        MMDVM_HOST_LOG
                    )
                )

                raise RuntimeError(
                    "MMDVM-Host exited "
                    f"with code "
                    f"{self._host_process.returncode}.\n"
                    f"{log_tail}"
                )


            log_text = (
                self._tail_file(
                    MMDVM_HOST_LOG,
                    lines=120,
                )
            )


            for marker in (
                failure_markers
            ):
                if (
                    marker
                    in log_text
                ):
                    raise RuntimeError(
                        "MMDVM-Host startup "
                        f"failed: {marker}\n"
                        f"{log_text}"
                    )


            if all(
                marker
                in log_text
                for marker
                in ready_markers
            ):
                return


            time.sleep(
                0.1
            )


        log_tail = (
            self._tail_file(
                MMDVM_HOST_LOG,
                lines=120,
            )
        )

        raise RuntimeError(
            "MMDVM-Host did not reach "
            "the protocol handler state "
            f"within {timeout:.1f}s.\n"
            f"{log_tail}"
        )


    def _check_paths(
        self,
    ) -> None:
        required_paths = (
            MMDVM_IQ_BINARY,
            MMDVM_HOST_BINARY,
            MMDVM_IQ_CONFIG,
        )

        for path in (
            required_paths
        ):
            if not path.exists():
                raise RuntimeError(
                    f"Missing required "
                    f"MMDVM file: {path}"
                )


        if not os.access(
            MMDVM_IQ_BINARY,
            os.X_OK,
        ):
            raise RuntimeError(
                "MMDVM-IQ binary is "
                "not executable"
            )


        if not os.access(
            MMDVM_HOST_BINARY,
            os.X_OK,
        ):
            raise RuntimeError(
                "MMDVM-Host binary is "
                "not executable"
            )


    def _check_ports_free(
        self,
    ) -> None:
        for port in (
            3334,
            3335,
        ):
            if self._udp_port_bound(
                port
            ):
                raise RuntimeError(
                    f"UDP port {port} "
                    f"is already in use. "
                    "Stop manually started "
                    "MMDVM processes first."
                )


    def _close_log_handles(
        self,
    ) -> None:
        if (
            self._host_log_handle
            is not None
        ):
            try:
                self._host_log_handle.close()

            finally:
                self._host_log_handle = None


        if (
            self._iq_log_handle
            is not None
        ):
            try:
                self._iq_log_handle.close()

            finally:
                self._iq_log_handle = None


    @staticmethod
    def _stop_process(
        process: (
            subprocess.Popen[Any]
            | None
        ),
        timeout: float = 4.0,
    ) -> None:
        if (
            process is None
            or process.poll()
            is not None
        ):
            return


        process.terminate()


        try:
            process.wait(
                timeout=timeout
            )

        except subprocess.TimeoutExpired:
            process.kill()

            process.wait(
                timeout=2.0
            )


    def start(
        self,
        protocol: str,
        settings: dict[str, Any],
        *,
        callsign: str = "SP5OPS",
    ) -> dict[str, Any]:
        with self._lock:
            if self.is_running:
                raise RuntimeError(
                    "MMDVM runtime is "
                    "already active"
                )


            validate_runtime_mode(
                protocol,
                settings,
            )

            self._check_paths()
            self._check_ports_free()


            RUNTIME_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )


            write_mmdvm_host_config(
                MMDVM_HOST_RUNTIME_CONFIG,
                protocol,
                settings,
                callsign=callsign,
            )


            MMDVM_IQ_LOG.write_text(
                "",
                encoding="utf-8",
            )

            MMDVM_HOST_LOG.write_text(
                "",
                encoding="utf-8",
            )


            self._protocol = (
                protocol
            )

            self._settings = dict(
                settings
            )

            self._last_error = None


            try:
                mark_driver_open(
                    "sx"
                )


                self._iq_log_handle = (
                    MMDVM_IQ_LOG.open(
                        "a",
                        encoding="utf-8",
                        buffering=1,
                    )
                )


                self._iq_process = (
                    subprocess.Popen(
                        [
                            str(
                                MMDVM_IQ_BINARY
                            ),
                            str(
                                MMDVM_IQ_CONFIG
                            ),
                        ],
                        cwd=str(
                            MMDVM_IQ_DIR
                        ),
                        stdin=(
                            subprocess.DEVNULL
                        ),
                        stdout=(
                            self._iq_log_handle
                        ),
                        stderr=(
                            subprocess.STDOUT
                        ),
                        start_new_session=True,
                    )
                )


                self._wait_for_udp_port(
                    port=3334,
                    process=self._iq_process,
                    process_name="MMDVM-IQ",
                    timeout=5.0,
                    log_path=MMDVM_IQ_LOG,
                )


                self._host_log_handle = (
                    MMDVM_HOST_LOG.open(
                        "a",
                        encoding="utf-8",
                        buffering=1,
                    )
                )


                self._host_process = (
                    subprocess.Popen(
                        [
                            str(
                                MMDVM_HOST_BINARY
                            ),
                            str(
                                MMDVM_HOST_RUNTIME_CONFIG
                            ),
                        ],
                        cwd=str(
                            MMDVM_HOST_DIR
                        ),
                        stdin=(
                            subprocess.DEVNULL
                        ),
                        stdout=(
                            self._host_log_handle
                        ),
                        stderr=(
                            subprocess.STDOUT
                        ),
                        start_new_session=True,
                    )
                )


                self._wait_for_udp_port(
                    port=3335,
                    process=self._host_process,
                    process_name="MMDVM-Host",
                    timeout=5.0,
                    log_path=MMDVM_HOST_LOG,
                )


                self._wait_for_host_ready(
                    timeout=10.0
                )


                return self.status()


            except Exception as error:
                self._last_error = str(
                    error
                )


                self._stop_process(
                    self._host_process
                )

                self._stop_process(
                    self._iq_process
                )


                self._host_process = None
                self._iq_process = None


                self._close_log_handles()


                mark_driver_closed(
                    "sx"
                )


                raise


    def stop(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            self._stop_process(
                self._host_process
            )

            self._stop_process(
                self._iq_process
            )


            self._host_process = None
            self._iq_process = None


            self._close_log_handles()


            mark_driver_closed(
                "sx"
            )


            self._protocol = None
            self._settings = None


            return self.status()


    @property
    def is_running(
        self,
    ) -> bool:
        return (
            self._process_running(
                self._iq_process
            )
            and
            self._process_running(
                self._host_process
            )
        )


    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            iq_running = (
                self._process_running(
                    self._iq_process
                )
            )

            host_running = (
                self._process_running(
                    self._host_process
                )
            )


            runtime_active = (
                iq_running
                and host_running
            )


            iq_telemetry = (
                self._parse_iq_telemetry(
                    iq_running=iq_running,
                )
            )


            host_ready = (
                self._host_ready(
                    host_running=host_running,
                )
            )


            channel_frequency_hz = (
                self._settings.get(
                    "frequency_hz"
                )
                if self._settings
                else None
            )


            sdr_tx_center_frequency_hz = (
                iq_telemetry[
                    "sdr_tx_center_frequency_hz"
                ]
            )

            sdr_rx_center_frequency_hz = (
                iq_telemetry[
                    "sdr_rx_center_frequency_hz"
                ]
            )


            digital_if_hz: (
                int
                | None
            ) = None


            if (
                channel_frequency_hz
                is not None
                and
                sdr_tx_center_frequency_hz
                is not None
            ):
                digital_if_hz = (
                    int(
                        channel_frequency_hz
                    )
                    -
                    int(
                        sdr_tx_center_frequency_hz
                    )
                )


            rf_tx_active = bool(
                iq_telemetry[
                    "rf_tx_active"
                ]
            )


            return {
                "runtime_active":
                    runtime_active,

                "runtime_ready":
                    (
                        runtime_active
                        and host_ready
                        and bool(
                            iq_telemetry[
                                "ready"
                            ]
                        )
                    ),

                "protocol":
                    self._protocol,

                "frequency_hz":
                    channel_frequency_hz,

                "channel_frequency_hz":
                    channel_frequency_hz,

                "sdr_tx_center_frequency_hz":
                    sdr_tx_center_frequency_hz,

                "sdr_rx_center_frequency_hz":
                    sdr_rx_center_frequency_hz,

                "digital_if_hz":
                    digital_if_hz,

                "sample_rate_hz":
                    iq_telemetry[
                        "sample_rate_hz"
                    ],

                "actual_tx_rate_hz":
                    iq_telemetry[
                        "actual_tx_rate_hz"
                    ],

                "actual_rx_rate_hz":
                    iq_telemetry[
                        "actual_rx_rate_hz"
                    ],

                "modem_mode":
                    iq_telemetry[
                        "modem_mode"
                    ],

                "rf_tx_active":
                    rf_tx_active,

                #
                # Deprecated compatibility alias.
                # This now reflects real MMDVM-IQ
                # RF TX state, not runtime state.
                #
                "tx_stream_active":
                    rf_tx_active,

                "hardware_open":
                    bool(
                        iq_telemetry[
                            "hardware_open"
                        ]
                    ),

                "iq_streams_active":
                    bool(
                        iq_telemetry[
                            "iq_streams_active"
                        ]
                    ),

                "hardware_version":
                    iq_telemetry[
                        "hardware_version"
                    ],

                "driver_name":
                    iq_telemetry[
                        "driver_name"
                    ],

                "mmdvm_iq": {
                    "running":
                        iq_running,

                    "ready":
                        bool(
                            iq_telemetry[
                                "ready"
                            ]
                        ),

                    "pid":
                        (
                            self._iq_process.pid
                            if (
                                iq_running
                                and
                                self._iq_process
                            )
                            else None
                        ),

                    "udp_port":
                        3334,
                },

                "mmdvm_host": {
                    "running":
                        host_running,

                    "ready":
                        host_ready,

                    "pid":
                        (
                            self._host_process.pid
                            if (
                                host_running
                                and
                                self._host_process
                            )
                            else None
                        ),

                    "udp_port":
                        3335,
                },

                "runtime_config":
                    str(
                        MMDVM_HOST_RUNTIME_CONFIG
                    ),

                "last_error":
                    self._last_error,
            }


    def logs(
        self,
        lines: int = 80,
    ) -> dict[str, str]:
        lines = max(
            1,
            min(
                lines,
                500,
            ),
        )

        return {
            "mmdvm_iq":
                self._tail_file(
                    MMDVM_IQ_LOG,
                    lines,
                ),

            "mmdvm_host":
                self._tail_file(
                    MMDVM_HOST_LOG,
                    lines,
                ),
        }


mmdvm_process_manager = (
    MMDVMProcessManager()
)
