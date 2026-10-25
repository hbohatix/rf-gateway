"""Protocol -> voice session lookup used by the Live Audio pipeline and Calls bridge."""

from __future__ import annotations

from typing import Any

from app.voice.dmr import DMRStreamingSession, dmr_bridge_capability
from app.voice.fm import FMStreamingSession, fm_bridge_capability
from app.voice.dstar import DStarStreamingSession, dstar_bridge_capability
from app.voice.nxdn import NXDNStreamingSession, nxdn_bridge_capability
from app.voice.ysf import YSFStreamingSession, ysf_bridge_capability


# Protocols whose source audio can be transmitted through MMDVM-Host.
STREAMING_PROTOCOLS = ("p25", "dmr", "ysf", "dstar", "nxdn", "fm")


def normalize_protocol(protocol: str) -> str:
    return str(protocol or "").strip().lower()


def supports_streaming(protocol: str) -> bool:
    return normalize_protocol(protocol) in STREAMING_PROTOCOLS


def create_voice_session(protocol: str, *, mode_config: dict[str, Any] | None = None):
    name = normalize_protocol(protocol)
    if name == "p25":
        # Imported lazily: the P25 module pulls in the IMBE ctypes wrapper.
        from app.p25_streaming_session import P25StreamingSession

        return P25StreamingSession(mode_config=mode_config)
    if name == "dmr":
        return DMRStreamingSession(mode_config=mode_config)
    if name == "fm":
        return FMStreamingSession(mode_config=mode_config)
    if name == "ysf":
        return YSFStreamingSession(mode_config=mode_config)
    if name == "dstar":
        return DStarStreamingSession(mode_config=mode_config)
    if name == "nxdn":
        return NXDNStreamingSession(mode_config=mode_config)
    raise ValueError(f"No voice session for protocol {protocol!r}")


def voice_bridge_capability(protocol: str) -> dict[str, Any] | None:
    """Capability for the protocols implemented in :mod:`app.voice` (not P25)."""
    name = normalize_protocol(protocol)
    if name == "dmr":
        return dmr_bridge_capability()
    if name == "fm":
        return fm_bridge_capability()
    if name == "ysf":
        return ysf_bridge_capability()
    if name == "dstar":
        return dstar_bridge_capability()
    if name == "nxdn":
        return nxdn_bridge_capability()
    return None
