from __future__ import annotations

from copy import deepcopy
from typing import Literal


Protocol = Literal[
    "fm",
    "dmr",
    "p25",
    "tetra",
]


CAPABILITIES = {
    "fm": {
        "protocol": "fm",
        "audio_input_supported": False,
        "encoder_required": False,
        "framing_required": False,
        "bridge_state": "not_implemented",
        "blocking_reason": "fm_audio_bridge_not_implemented",
    },

    "dmr": {
        "protocol": "dmr",
        "audio_input_supported": False,
        "encoder_required": True,
        "framing_required": True,
        "bridge_state": "not_implemented",
        "blocking_reason": "dmr_vocoder_and_framing_not_implemented",
    },

    "p25": {
        "protocol": "p25",
        "audio_input_supported": False,
        "encoder_required": True,
        "framing_required": True,
        "bridge_state": "not_implemented",
        "blocking_reason": "p25_vocoder_and_framing_not_implemented",
    },

    "tetra": {
        "protocol": "tetra",
        "audio_input_supported": False,
        "encoder_required": True,
        "framing_required": True,
        "bridge_state": "not_implemented",
        "blocking_reason": "tetra_vocoder_and_framing_not_implemented",
    },
}


def get_audio_bridge_capability(
    protocol: Protocol,
) -> dict:
    capability = (
        CAPABILITIES.get(
            protocol
        )
    )

    if capability is None:
        raise ValueError(
            (
                "Unsupported protocol: "
                f"{protocol}"
            )
        )

    return deepcopy(
        capability
    )


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
            deepcopy(
                capability
            )

        for (
            protocol,
            capability
        )
        in CAPABILITIES.items()
    }
