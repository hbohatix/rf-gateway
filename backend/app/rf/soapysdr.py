from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


SOAPY_EXECUTABLE = "SoapySDRUtil"


def _run_soapy(
    arguments: list[str],
    timeout: int = 15,
) -> tuple[int, str]:
    executable = shutil.which(SOAPY_EXECUTABLE)

    if executable is None:
        return (
            127,
            "SoapySDRUtil is not installed or not available in PATH.",
        )

    try:
        process = subprocess.run(
            [
                executable,
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        output = "\n".join(
            part
            for part in [
                process.stdout.strip(),
                process.stderr.strip(),
            ]
            if part
        )

        return process.returncode, output

    except subprocess.TimeoutExpired:
        return (
            124,
            "SoapySDRUtil command timed out.",
        )

    except OSError as error:
        return (
            1,
            str(error),
        )


def _parse_find_output(
    output: str,
) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []

    current_device: dict[str, Any] | None = None

    for line in output.splitlines():
        stripped = line.strip()

        found_match = re.match(
            r"Found device\s+(\d+)",
            stripped,
        )

        if found_match:
            if current_device is not None:
                devices.append(current_device)

            current_device = {
                "index": int(found_match.group(1)),
            }

            continue

        if current_device is None:
            continue

        key_value_match = re.match(
            r"([A-Za-z0-9_.-]+)\s*=\s*(.+)",
            stripped,
        )

        if not key_value_match:
            continue

        key = key_value_match.group(1).strip()
        value = key_value_match.group(2).strip()

        current_device[key] = value

    if current_device is not None:
        devices.append(current_device)

    return devices


def _parse_probe_output(
    output: str,
) -> dict[str, Any]:
    details: dict[str, Any] = {}


    hardware_version_match = re.search(
        r"\[INFO\]\s+Hardware version\s+(.+)",
        output,
    )

    if hardware_version_match:
        details["hardware_version"] = (
            hardware_version_match
            .group(1)
            .strip()
        )


    clock_match = re.search(
        r"\[INFO\]\s+Detected clock as\s+(.+)",
        output,
    )

    if clock_match:
        details["clock"] = (
            clock_match
            .group(1)
            .strip()
        )


    commit_match = re.search(
        r"soapysx_commit=(.+)",
        output,
    )

    if commit_match:
        details["soapysx_commit"] = (
            commit_match
            .group(1)
            .strip()
        )


    tag_match = re.search(
        r"soapysx_tag=(.+)",
        output,
    )

    if tag_match:
        details["soapysx_tag"] = (
            tag_match
            .group(1)
            .strip()
        )


    hardware_match = re.search(
        r"hardware=(.+)",
        output,
    )

    if hardware_match:
        details["hardware"] = (
            hardware_match
            .group(1)
            .strip()
        )


    channels_match = re.search(
        r"Channels:\s*(\d+)\s*Rx,\s*(\d+)\s*Tx",
        output,
    )

    if channels_match:
        details["rx_channels"] = int(
            channels_match.group(1)
        )

        details["tx_channels"] = int(
            channels_match.group(2)
        )


    timestamps_match = re.search(
        r"Timestamps:\s*(YES|NO)",
        output,
    )

    if timestamps_match:
        details["timestamps"] = (
            timestamps_match.group(1) == "YES"
        )


    full_duplex_matches = re.findall(
        r"Full-duplex:\s*(YES|NO)",
        output,
    )

    if full_duplex_matches:
        details["full_duplex"] = all(
            value == "YES"
            for value in full_duplex_matches
        )


    agc_matches = re.findall(
        r"Supports AGC:\s*(YES|NO)",
        output,
    )

    if agc_matches:
        details["agc"] = any(
            value == "YES"
            for value in agc_matches
        )


    gain_ranges = re.findall(
        r"Full gain range:\s*\[([^\]]+)\]\s*dB",
        output,
    )

    if len(gain_ranges) >= 1:
        details["rx_gain_range_db"] = (
            gain_ranges[0].strip()
        )

    if len(gain_ranges) >= 2:
        details["tx_gain_range_db"] = (
            gain_ranges[1].strip()
        )


    sample_rate_matches = re.findall(
        r"Sample rates:\s*(.+)",
        output,
    )

    if len(sample_rate_matches) >= 1:
        details["rx_sample_rates"] = (
            sample_rate_matches[0]
            .strip()
        )

    if len(sample_rate_matches) >= 2:
        details["tx_sample_rates"] = (
            sample_rate_matches[1]
            .strip()
        )


    return details


def _probe_device(
    driver: str,
) -> tuple[dict[str, Any], str | None]:
    return_code, output = _run_soapy(
        [
            f"--probe=driver={driver}",
        ]
    )

    if return_code != 0:
        return (
            {},
            output or "Unable to probe SoapySDR device.",
        )

    return (
        _parse_probe_output(output),
        None,
    )


def discover_soapy_devices() -> dict[str, Any]:
    executable = shutil.which(
        SOAPY_EXECUTABLE
    )

    if executable is None:
        return {
            "backend": "soapysdr",
            "available": False,
            "device_count": 0,
            "devices": [],
            "error": (
                "SoapySDRUtil is not installed "
                "or not available in PATH."
            ),
        }


    return_code, output = _run_soapy(
        [
            "--find",
        ]
    )


    if return_code != 0:
        return {
            "backend": "soapysdr",
            "available": True,
            "device_count": 0,
            "devices": [],
            "error": (
                output
                or "SoapySDR device discovery failed."
            ),
        }


    discovered = _parse_find_output(
        output
    )


    devices: list[dict[str, Any]] = []


    for device in discovered:
        index = device.get(
            "index",
            len(devices),
        )

        driver = str(
            device.get(
                "driver",
                "unknown",
            )
        )

        label = str(
            device.get(
                "label",
                driver,
            )
        )


        probe_details: dict[str, Any] = {}
        probe_error: str | None = None


        if driver != "unknown":
            probe_details, probe_error = (
                _probe_device(driver)
            )


        devices.append(
            {
                "id": f"soapy-{index}",
                "type": "sdr",
                "backend": "soapysdr",
                "driver": driver,
                "label": label,
                "available": True,
                "probe_ok": (
                    probe_error is None
                ),
                "probe_error": probe_error,
                "capabilities": probe_details,
            }
        )


    return {
        "backend": "soapysdr",
        "available": True,
        "device_count": len(devices),
        "devices": devices,
        "error": None,
    }
