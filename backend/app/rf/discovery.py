from __future__ import annotations

import hashlib
import os

from copy import deepcopy
from pathlib import Path
from typing import Any

from .soapysdr import discover_soapy_devices


MMDVM_UART_SPEED = 115200

MMDVM_IQ_FREQUENCY_RANGES_HZ = [
    [144_000_000, 148_000_000],
    [420_000_000, 450_000_000],
]


def _serial_candidates() -> list[Path]:
    candidates: list[Path] = []

    by_id_dir = Path(
        "/dev/serial/by-id"
    )

    if by_id_dir.is_dir():
        candidates.extend(
            sorted(
                by_id_dir.glob("*")
            )
        )

    for pattern in (
        "/dev/ttyACM*",
        "/dev/ttyUSB*",
        "/dev/ttyAMA*",
    ):
        candidates.extend(
            sorted(
                Path("/").glob(
                    pattern.lstrip("/")
                )
            )
        )

    for alias in (
        Path("/dev/serial0"),
        Path("/dev/serial1"),
    ):
        if (
            alias.exists()
            or alias.is_symlink()
        ):
            candidates.append(
                alias
            )

    return candidates


def _serial_profile(
    path: Path,
) -> tuple[str, str]:
    value = str(
        path
    ).lower()

    if "zum" in value:
        return (
            "zumspot",
            "ZUMspot"
        )

    if "dvmega" in value:
        return (
            "dvmega",
            "DVMEGA"
        )

    if (
        "mmdvm_hs_dual"
        in value
        or
        "dual_hat"
        in value
    ):
        return (
            "mmdvm_hs_dual_hat",
            "MMDVM_HS Dual Hat"
        )

    if (
        "mmdvm_hs"
        in value
        or
        "mmdvm"
        in value
    ):
        return (
            "mmdvm_hs",
            "MMDVM_HS / MMDVM"
        )

    if (
        "ttyama"
        in value
        or
        path.name
        in (
            "serial0",
            "serial1",
        )
    ):
        return (
            "mmdvm_gpio_uart",
            "MMDVM GPIO/UART"
        )

    if (
        "ttyacm"
        in value
        or
        "ttyusb"
        in value
    ):
        return (
            "generic_mmdvm_usb",
            "MMDVM USB/UART"
        )

    return (
        "generic_mmdvm_uart",
        "Generic MMDVM UART"
    )


def _serial_device_id(
    path: Path,
) -> str:
    digest = (
        hashlib.sha1(
            str(path).encode(
                "utf-8"
            )
        )
        .hexdigest()[:12]
    )

    return (
        f"mmdvm-uart-{digest}"
    )


def discover_mmdvm_uart_devices(
) -> dict[str, Any]:
    devices: list[
        dict[str, Any]
    ] = []

    seen_targets: set[str] = set()

    for path in (
        _serial_candidates()
    ):
        try:
            resolved = (
                path.resolve(
                    strict=False
                )
            )

        except OSError:
            resolved = path

        target_key = str(
            resolved
        )

        if target_key in seen_targets:
            continue

        seen_targets.add(
            target_key
        )

        exists = (
            path.exists()
            or path.is_symlink()
        )

        accessible = bool(
            exists
            and
            os.access(
                path,
                os.R_OK
                | os.W_OK,
            )
        )

        (
            profile,
            family_name,
        ) = _serial_profile(
            path
        )

        if (
            "/dev/serial/by-id/"
            in str(path)
        ):
            label = (
                f"{family_name} · "
                f"{path.name}"
            )

        else:
            label = (
                f"{family_name} · "
                f"{path}"
            )

        devices.append(
            {
                "id":
                    _serial_device_id(
                        path
                    ),

                "type":
                    "modem",

                "backend":
                    "mmdvm_uart",

                "driver":
                    "mmdvm",

                "label":
                    label,

                "available":
                    exists,

                "probe_ok":
                    accessible,

                "probe_error":
                    (
                        None
                        if accessible
                        else
                        (
                            "Serial port is not "
                            "read/write accessible"
                        )
                    ),

                "capabilities": {
                    "connection":
                        "uart",

                    "uart_port":
                        str(path),

                    "uart_resolved_port":
                        target_key,

                    "uart_speed":
                        MMDVM_UART_SPEED,

                    "profile":
                        profile,

                    "mmdvm_compatible":
                        True,

                    "mmdvm_host_protocol":
                        "uart",

                    "mmdvm_iq_required":
                        False,

                    "frequency_policy":
                        "modem_firmware",
                },
            }
        )

    return {
        "backend":
            "mmdvm_uart",

        "available":
            True,

        "device_count":
            len(devices),

        "devices":
            devices,

        "error":
            None,
    }


def _decorate_soapy_device(
    device: dict[str, Any],
) -> dict[str, Any]:
    decorated = deepcopy(
        device
    )

    capabilities = dict(
        decorated.get(
            "capabilities"
        )
        or {}
    )

    capabilities.update(
        {
            "connection":
                "mmdvm_iq",

            "mmdvm_host_protocol":
                "udp",

            "mmdvm_iq_required":
                True,

            "frequency_ranges_hz":
                deepcopy(
                    MMDVM_IQ_FREQUENCY_RANGES_HZ
                ),

            "frequency_policy":
                (
                    "rf_gateway_mmdvm_iq_"
                    "amateur_profile"
                ),
        }
    )

    decorated[
        "capabilities"
    ] = capabilities

    return decorated


def discover_rf_devices(
) -> dict[str, Any]:
    soapy = (
        discover_soapy_devices()
    )

    serial = (
        discover_mmdvm_uart_devices()
    )

    soapy_devices = [
        _decorate_soapy_device(
            device
        )
        for device
        in soapy.get(
            "devices",
            [],
        )
    ]

    serial_devices = list(
        serial.get(
            "devices",
            [],
        )
    )

    devices = [
        *soapy_devices,
        *serial_devices,
    ]

    warnings: list[str] = []

    soapy_error = (
        soapy.get(
            "error"
        )
    )

    if soapy_error:
        warnings.append(
            str(
                soapy_error
            )
        )

    return {
        "backend":
            "rf_gateway",

        "available":
            bool(
                devices
                or
                soapy.get(
                    "available",
                    False,
                )
                or
                serial.get(
                    "available",
                    False,
                )
            ),

        "device_count":
            len(devices),

        "devices":
            devices,

        "warnings":
            warnings,

        "error":
            (
                None
                if devices
                else
                (
                    "; ".join(
                        warnings
                    )
                    or None
                )
            ),
    }


def get_rf_device(
    device_id: str,
) -> dict[str, Any] | None:
    discovery = (
        discover_rf_devices()
    )

    for device in (
        discovery.get(
            "devices",
            []
        )
    ):
        if (
            device.get(
                "id"
            )
            == device_id
        ):
            return deepcopy(
                device
            )

    return None
