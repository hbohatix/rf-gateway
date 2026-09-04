from __future__ import annotations

import re
import shutil
import subprocess


MMDVM_HOST_MQTT_TOPIC = (
    "rf-gateway-mmdvm-host/command"
)

CW_TEXT_PATTERN = re.compile(
    r"^[A-Za-z0-9 /._-]+$"
)


def normalize_cw_text(
    text: str,
) -> str:
    normalized = (
        text
        .strip()
        .upper()
    )

    if not normalized:
        raise ValueError(
            "CW text cannot be empty"
        )

    if len(normalized) > 32:
        raise ValueError(
            "CW text cannot exceed "
            "32 characters"
        )

    if not CW_TEXT_PATTERN.fullmatch(
        normalized
    ):
        raise ValueError(
            "CW text contains unsupported "
            "characters"
        )

    return normalized


def send_cw_command(
    text: str,
) -> dict[str, str | bool]:
    normalized = (
        normalize_cw_text(
            text
        )
    )

    mosquitto_pub = (
        shutil.which(
            "mosquitto_pub"
        )
    )

    if mosquitto_pub is None:
        raise RuntimeError(
            "mosquitto_pub is not installed"
        )

    command = (
        f"cw {normalized}"
    )

    try:
        result = subprocess.run(
            [
                mosquitto_pub,
                "-h",
                "127.0.0.1",
                "-p",
                "1883",
                "-t",
                MMDVM_HOST_MQTT_TOPIC,
                "-m",
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )

    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "MQTT CW command timed out"
        ) from error

    if result.returncode != 0:
        error_text = (
            result.stderr.strip()
            or
            result.stdout.strip()
            or
            "unknown mosquitto_pub error"
        )

        raise RuntimeError(
            "Unable to publish CW command: "
            f"{error_text}"
        )

    return {
        "accepted": True,
        "text": normalized,
        "mqtt_topic":
            MMDVM_HOST_MQTT_TOPIC,
        "command": command,
    }
