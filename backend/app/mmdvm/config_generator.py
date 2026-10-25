from __future__ import annotations

from pathlib import Path
from typing import Any


SUPPORTED_RUNTIME_PROTOCOLS = {
    "dmr",
    "fm",
    "p25",
    "ysf",
    "dstar",
    "nxdn",
}

# Protocols identified by callsign rather than a numeric radio ID.
CALLSIGN_PROTOCOLS = {
    "fm",
    "ysf",
    "dstar",
}


# Local network ports shared with the voice sessions in app.voice.
DMR_NETWORK_LOCAL_PORT = 62032
DMR_NETWORK_GATEWAY_PORT = 62031
FM_NETWORK_LOCAL_PORT = 3810
FM_NETWORK_GATEWAY_PORT = 4810
YSF_NETWORK_LOCAL_PORT = 3200
YSF_NETWORK_GATEWAY_PORT = 4200
DSTAR_NETWORK_LOCAL_PORT = 20011
DSTAR_NETWORK_GATEWAY_PORT = 20010
NXDN_NETWORK_LOCAL_PORT = 14021
NXDN_NETWORK_GATEWAY_PORT = 14020


P25_NETWORK_LOCAL_ADDRESS = (
    "127.0.0.1"
)

P25_NETWORK_LOCAL_PORT = (
    32010
)

P25_NETWORK_GATEWAY_ADDRESS = (
    "127.0.0.1"
)

P25_NETWORK_GATEWAY_PORT = (
    42020
)


def _require_frequency(
    settings: dict[str, Any],
) -> int:
    frequency_hz = int(
        settings.get(
            "frequency_hz",
            0,
        )
    )

    if frequency_hz <= 0:
        raise ValueError(
            "Invalid RF frequency"
        )

    return frequency_hz


def _require_radio_id(
    settings: dict[str, Any],
) -> int:
    radio_id = int(
        settings.get(
            "radio_id",
            0,
        )
    )

    if radio_id <= 0:
        raise ValueError(
            "Radio ID must be greater than zero"
        )

    return radio_id


def _normalize_nac(
    value: Any,
) -> str:
    raw = str(
        value
    ).strip()

    if raw.lower().startswith(
        "0x"
    ):
        raw = raw[2:]

    try:
        nac = int(
            raw,
            16,
        )

    except ValueError as error:
        raise ValueError(
            f"Invalid P25 NAC: {value}"
        ) from error

    if (
        nac < 0
        or nac > 0xFFF
    ):
        raise ValueError(
            "P25 NAC must be between 000 and FFF"
        )

    return f"{nac:03X}"


def validate_runtime_mode(
    protocol: str,
    settings: dict[str, Any],
) -> None:
    protocol = (
        protocol
        .strip()
        .lower()
    )

    if protocol == "tetra":
        raise ValueError(
            "TETRA is not supported by the "
            "current MMDVM runtime"
        )


    if protocol not in (
        SUPPORTED_RUNTIME_PROTOCOLS
    ):
        raise ValueError(
            f"Unsupported runtime protocol: "
            f"{protocol}"
        )

    _require_frequency(
        settings
    )

    if protocol not in CALLSIGN_PROTOCOLS:
        _require_radio_id(
            settings
        )

    if protocol == "ysf":
        callsign = str(settings.get("callsign") or "").strip()
        if not 1 <= len(callsign) <= 10:
            raise ValueError(
                "YSF callsign must be 1-10 characters"
            )

    if protocol == "dstar":
        callsign = str(settings.get("callsign") or "").strip()
        if not 3 <= len(callsign) <= 8:
            raise ValueError(
                "D-Star callsign must be 3-8 characters"
            )

    if protocol == "dmr":
        color_code = int(
            settings.get(
                "color_code",
                -1,
            )
        )

        if not 0 <= color_code <= 15:
            raise ValueError(
                "DMR Color Code must be "
                "between 0 and 15"
            )

        timeslot = int(
            settings.get(
                "timeslot",
                0,
            )
        )

        if timeslot not in (
            1,
            2,
        ):
            raise ValueError(
                "DMR Timeslot must be 1 or 2"
            )


    if protocol == "p25":
        _normalize_nac(
            settings.get(
                "nac",
                "",
            )
        )

        modulation = str(
            settings.get(
                "modulation",
                "",
            )
        ).strip().lower()

        if modulation != "c4fm":
            raise ValueError(
                "Current P25 runtime supports "
                "the C4FM path only"
            )


def _render_fm_section(
    settings: dict[str, Any],
) -> str:
    """[FM] keys for network (external audio) transmission."""
    ctcss = settings.get("tx_ctcss_hz")
    try:
        ctcss_hz = float(ctcss) if ctcss not in (None, "") else 0.0
    except (TypeError, ValueError):
        ctcss_hz = 0.0
    deviation = float(settings.get("deviation_khz", 2.5) or 2.5)
    # MaxDevLevel is a percentage of the modem's full deviation (5 kHz).
    max_dev_level = max(10, min(100, int(round(deviation / 5.0 * 100))))
    lines = [
        "CallsignSpeed=20",
        "CallsignFrequency=1000",
        "CallsignTime=10",
        "CallsignHoldoff=0",
        "CallsignHighLevel=50",
        "CallsignLowLevel=20",
        "CallsignAtStart=0",
        "CallsignAtEnd=0",
        "CallsignAtLatch=0",
        "RFAck=",
        "ExtAck=",
        "AckSpeed=20",
        "AckFrequency=1750",
        "AckMinTime=4",
        "AckDelay=1000",
        "AckLevel=50",
        "TimeoutLevel=80",
        f"CTCSSFrequency={ctcss_hz if ctcss_hz > 0 else 88.4}",
        "CTCSSThreshold=30",
        f"CTCSSLevel={20 if ctcss_hz > 0 else 0}",
        "KerchunkTime=0",
        "HangTime=3",
        "AccessMode=1",
        "LinkMode=1",
        "COSInvert=0",
        "NoiseSquelch=0",
        "SquelchThreshold=30",
        "RFAudioBoost=1",
        f"MaxDevLevel={max_dev_level}",
        "ExtAudioBoost=1",
    ]
    return "\n".join(lines)


def render_mmdvm_host_config(
    protocol: str,
    settings: dict[str, Any],
    *,
    callsign: str,
    device: dict[str, Any] | None = None,
) -> str:
    protocol = (
        protocol
        .strip()
        .lower()
    )

    validate_runtime_mode(
        protocol,
        settings,
    )

    frequency_hz = (
        _require_frequency(
            settings
        )
    )

    radio_id = (
        _require_radio_id(
            settings
        )
        if protocol not in CALLSIGN_PROTOCOLS
        else int(
            settings.get(
                "radio_id",
                0,
            )
            or 1
        )
    )

    dmr_enable = (
        1
        if protocol == "dmr"
        else 0
    )

    ysf_enable = (
        1
        if protocol == "ysf"
        else 0
    )

    nxdn_enable = (
        1
        if protocol == "nxdn"
        else 0
    )

    nxdn_ran = (
        int(settings.get("ran", 1))
        if protocol == "nxdn"
        else 1
    )

    dstar_enable = (
        1
        if protocol == "dstar"
        else 0
    )

    dstar_module = (
        str(settings.get("module") or "B").strip().upper()[:1]
        if protocol == "dstar"
        else "B"
    ) or "B"

    ysf_low_deviation = (
        1
        if protocol == "ysf"
        and settings.get("low_deviation")
        else 0
    )

    fm_enable = (
        1
        if protocol == "fm"
        else 0
    )

    fm_section = _render_fm_section(
        settings
        if protocol == "fm"
        else {}
    )

    p25_enable = (
        1
        if protocol == "p25"
        else 0
    )

    dmr_id = radio_id

    dmr_color_code = int(
        settings.get(
            "color_code",
            1,
        )
    )

    p25_id = radio_id

    p25_nac = (
        _normalize_nac(
            settings.get(
                "nac",
                "293",
            )
        )
        if protocol == "p25"
        else "293"
    )

    device = (
        device
        or {}
    )

    device_backend = str(
        device.get(
            "backend",
            "soapysdr",
        )
    ).strip().lower()

    device_capabilities = (
        device.get(
            "capabilities"
        )
        or {}
    )

    if device_backend == "mmdvm_uart":
        uart_port = str(
            device_capabilities.get(
                "uart_port",
                "",
            )
        ).strip()

        uart_speed = int(
            device_capabilities.get(
                "uart_speed",
                115200,
            )
        )

        if not uart_port:
            raise ValueError(
                "MMDVM UART device has no UART port"
            )

        modem_connection = (
            "Protocol=uart\n"
            f"UARTPort={uart_port}\n"
            f"UARTSpeed={uart_speed}"
        )

        modem_description = str(
            device.get(
                "label",
                "MMDVM UART modem",
            )
        ).strip()

    else:
        modem_connection = (
            "Protocol=udp\n"
            "ModemAddress=127.0.0.1\n"
            "ModemPort=3334\n"
            "LocalAddress=127.0.0.1\n"
            "LocalPort=3335"
        )

        modem_description = str(
            device.get(
                "label",
                "MMDVM-IQ / SoapySDR",
            )
        ).strip()

    runtime_comments: list[str] = [
        "# ------------------------------------------------------------",
        "# AUTO-GENERATED BY RF GATEWAY",
        "# DO NOT EDIT MANUALLY",
        "#",
        f"# Protocol: {protocol.upper()}",
        f"# Frequency from GUI: {frequency_hz} Hz",
    ]

    if protocol == "dmr":
        runtime_comments.extend(
            [
                (
                    "# Requested DMR Timeslot: "
                    f"{settings['timeslot']}"
                ),
                (
                    "# Requested DMR Talkgroup: "
                    f"{settings['talkgroup']}"
                ),
                (
                    "# Requested DMR Radio ID: "
                    f"{settings['radio_id']}"
                ),
            ]
        )

    if protocol == "p25":
        runtime_comments.extend(
            [
                (
                    "# Requested P25 NAC: "
                    f"{p25_nac}"
                ),
                (
                    "# Requested P25 Talkgroup: "
                    f"{settings['talkgroup']}"
                ),
                (
                    "# Requested P25 Radio ID: "
                    f"{settings['radio_id']}"
                ),
                (
                    "# Requested P25 Modulation: "
                    f"{settings['modulation']}"
                ),
                (
                    "# P25 Network Local: "
                    f"{P25_NETWORK_LOCAL_ADDRESS}:"
                    f"{P25_NETWORK_LOCAL_PORT}"
                ),
                (
                    "# P25 Network Gateway: "
                    f"{P25_NETWORK_GATEWAY_ADDRESS}:"
                    f"{P25_NETWORK_GATEWAY_PORT}"
                ),
            ]
        )

    runtime_comments.extend(
        [
            "# ------------------------------------------------------------",
            "",
        ]
    )

    # DMR is sent as a repeater downlink (Duplex=1: BS sync, CACH, both
    # timeslots), so TS1 and TS2 both work like on any repeater channel.
    # In simplex (DMO) MMDVM-Host drops all network TS1 traffic.
    duplex = 1 if protocol == "dmr" else 0
    dmr_slot1 = 1 if protocol == "dmr" else 0
    dmr_slot2 = 1

    body = f"""[General]
Callsign={callsign}
Id={radio_id}
Timeout=180
Duplex={duplex}
Daemon=0

[Info]
Power=0
Latitude=0.0
Longitude=0.0
Height=0
Location=RF Gateway
Description=RF Gateway - {modem_description}
URL=

[Log]
DisplayLevel=2
FileLevel=0
MQTTLevel=1

[MQTT]
Host=127.0.0.1
Port=1883
Keepalive=60
Name=rf-gateway-mmdvm-host
Auth=0
Username=mmdvm
Password=mmdvm

[Remote Control]
Enable=1

[CW Id]
Enable=0
Time=10
Callsign={callsign}

[Modem]
{modem_connection}

RXFrequency={frequency_hz}
TXFrequency={frequency_hz}

RXInvert=1
TXInvert=1
PTTInvert=0

TXDelay=100
DMRDelay=0

RXOffset=0
TXOffset=0
RXDCOffset=0
TXDCOffset=0

RFLevel=100
RXLevel=83
TXLevel=83

Trace=0
Debug=0

[DMR]
Enable={dmr_enable}
Id={dmr_id}
ColorCode={dmr_color_code}
Beacons=0
SelfOnly=0
EmbeddedLCOnly=0
DumpTAData=0
CallHang=3
TXHang=4

[P25]
Enable={p25_enable}
Id={p25_id}
NAC={p25_nac}
SelfOnly=0
OverrideUIDCheck=0
RemoteGateway=0
SoftId=0
TXHang=5

[D-Star]
Enable={dstar_enable}
Module={dstar_module}
SelfOnly=0
AckReply=0
AckTime=750
AckMessage=0
ErrorReply=0
RemoteGateway=0

[System Fusion]
Enable={ysf_enable}
LowDeviation={ysf_low_deviation}
SelfOnly=0
TXHang=4
RemoteGateway=0

[NXDN]
Enable={nxdn_enable}
RAN={nxdn_ran}
SelfOnly=0
RemoteGateway=0
TXHang=5

[POCSAG]
Enable=0
Frequency={frequency_hz}

[FM]
Enable={fm_enable}
{fm_section}

[DMR Network]
Enable={dmr_enable}
LocalAddress=127.0.0.1
LocalPort={DMR_NETWORK_LOCAL_PORT}
GatewayAddress=127.0.0.1
GatewayPort={DMR_NETWORK_GATEWAY_PORT}
Jitter=360
Slot1={dmr_slot1}
Slot2={dmr_slot2}
Debug=0

[D-Star Network]
Enable={dstar_enable}
LocalAddress=127.0.0.1
LocalPort={DSTAR_NETWORK_LOCAL_PORT}
GatewayAddress=127.0.0.1
GatewayPort={DSTAR_NETWORK_GATEWAY_PORT}
Debug=0

[NXDN Network]
Enable={nxdn_enable}
Protocol=Icom
LocalAddress=127.0.0.1
LocalPort={NXDN_NETWORK_LOCAL_PORT}
GatewayAddress=127.0.0.1
GatewayPort={NXDN_NETWORK_GATEWAY_PORT}
Debug=0

[System Fusion Network]
Enable={ysf_enable}
LocalAddress=127.0.0.1
LocalPort={YSF_NETWORK_LOCAL_PORT}
GatewayAddress=127.0.0.1
GatewayPort={YSF_NETWORK_GATEWAY_PORT}
Debug=0

[FM Network]
Enable={fm_enable}
LocalAddress=127.0.0.1
LocalPort={FM_NETWORK_LOCAL_PORT}
GatewayAddress=127.0.0.1
GatewayPort={FM_NETWORK_GATEWAY_PORT}
PreEmphasis={1 if settings.get("pre_emphasis", True) else 0}
DeEmphasis=1
TXAudioGain=1.0
RXAudioGain=1.0
Debug=0

[P25 Network]
Enable={p25_enable}
LocalAddress={P25_NETWORK_LOCAL_ADDRESS}
LocalPort={P25_NETWORK_LOCAL_PORT}
GatewayAddress={P25_NETWORK_GATEWAY_ADDRESS}
GatewayPort={P25_NETWORK_GATEWAY_PORT}
Debug=0
"""

    return (
        "\n".join(
            runtime_comments
        )
        + body
    )


def write_mmdvm_host_config(
    output_path: Path,
    protocol: str,
    settings: dict[str, Any],
    *,
    callsign: str,
    device: dict[str, Any] | None = None,
) -> Path:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rendered = (
        render_mmdvm_host_config(
            protocol,
            settings,
            callsign=callsign,
            device=device,
        )
    )

    temporary_path = (
        output_path.with_suffix(
            ".ini.tmp"
        )
    )

    temporary_path.write_text(
        rendered,
        encoding="utf-8",
    )

    temporary_path.replace(
        output_path
    )

    return output_path