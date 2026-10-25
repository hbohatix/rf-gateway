"""End-to-end check of a voice session against the real MMDVM-Host binary,
without any radio hardware and without transmitting.

MMDVM-Host is started with the configuration RF Gateway generates, but its
modem is a fake UDP modem in this script (protocol v2). The fake modem
records every frame MMDVM-Host would send to the transmitter.

    cd backend
    .venv/bin/python -m tools.mmdvm_loopback dmr
    .venv/bin/python -m tools.mmdvm_loopback ysf --seconds 4

Exit code 0 means MMDVM-Host accepted the network stream and queued
voice frames for the modem with no FEC errors reported.
"""

from __future__ import annotations

import argparse
import math
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

from app.mmdvm.config_generator import render_mmdvm_host_config
from app.voice.registry import create_voice_session


REPO_ROOT = Path(__file__).resolve().parents[2]
MMDVM_HOST_BINARY = REPO_ROOT / "third_party" / "MMDVM-Host" / "MMDVM-Host"
FAKE_MODEM_PORT = 43334
HOST_MODEM_PORT = 43335

MODEM_FRAME_NAMES = {
    0x10: "DSTAR_HEADER", 0x11: "DSTAR_DATA", 0x13: "DSTAR_EOT",
    0x18: "DMR_DATA1", 0x1A: "DMR_DATA2", 0x1C: "DMR_SHORTLC", 0x1D: "DMR_START", 0x1E: "DMR_ABORT",
    0x20: "YSF_DATA", 0x30: "P25_HDR", 0x31: "P25_LDU", 0x40: "NXDN_DATA",
    0x65: "FM_DATA", 0x67: "FM_EOT", 0x60: "FM_PARAMS1", 0x61: "FM_PARAMS2", 0x62: "FM_PARAMS3", 0x63: "FM_PARAMS4",
    0x02: "SET_CONFIG", 0x03: "SET_MODE", 0x04: "SET_FREQ", 0x01: "GET_STATUS", 0x00: "GET_VERSION",
}

MODE_SETTINGS = {
    "dmr": {"frequency_hz": 438800000, "radio_id": 2601292, "talkgroup": 260, "timeslot": 2, "color_code": 1,
            "call_type": "group", "vocoder": "software"},
    "ysf": {"frequency_hz": 438800000, "callsign": "SP5OPS", "destination": "ALL", "dg_id": 0, "vocoder": "software"},
    "dstar": {"frequency_hz": 438800000, "callsign": "SP5OPS", "suffix": "RFGW", "your_call": "CQCQCQ", "module": "B"},
    "nxdn": {"frequency_hz": 438800000, "radio_id": 1234, "talkgroup": 65000, "ran": 1, "call_type": "group",
             "vocoder": "software"},
    "p25": {"frequency_hz": 438800000, "radio_id": 1000, "nac": "293", "talkgroup": 260, "modulation": "c4fm"},
    "fm": {"frequency_hz": 145500000, "channel_spacing_khz": 12.5, "deviation_khz": 2.5, "pre_emphasis": True},
}

STATUS_MODES = {"dstar": 1, "dmr": 2, "ysf": 3, "p25": 4, "nxdn": 5, "fm": 10}


class FakeModem(threading.Thread):
    """Minimal MMDVM protocol v2 modem on UDP."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", FAKE_MODEM_PORT))
        self.sock.settimeout(0.2)
        self.frames: Counter[str] = Counter()
        self.payloads: list[tuple[int, bytes]] = []
        self.mode = 0
        self.stop = False

    def reply(self, data: bytes, address) -> None:
        self.sock.sendto(data, address)

    def run(self) -> None:
        while not self.stop:
            try:
                data, address = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            offset = 0
            while offset + 3 <= len(data):
                if data[offset] == 0xE0:
                    length = data[offset + 1]
                    header = 2
                elif data[offset] == 0xE1:
                    length = (data[offset + 1] << 8) | data[offset + 2]
                    header = 3
                else:
                    break
                frame = data[offset:offset + length]
                offset += length
                command = frame[header]
                payload = frame[header + 1:]
                self.frames[MODEM_FRAME_NAMES.get(command, f"0x{command:02X}")] += 1
                if command == 0x00:  # GET_VERSION
                    description = b"RF Gateway fake modem"
                    body = bytes((0x00, 2, 0x5F, 0x01, 0x02)) + bytes(16) + description
                    self.reply(bytes((0xE0, 2 + len(body))) + body, address)
                elif command == 0x01:  # GET_STATUS (v2)
                    body = bytes((0x01, self.mode, 0x00, 0x00, 10, 10, 10, 10, 10, 10, 0, 50, 10))
                    self.reply(bytes((0xE0, 2 + len(body))) + body, address)
                elif command in (0x02, 0x04, 0x0A):
                    self.reply(bytes((0xE0, 0x04, 0x70, command)), address)
                elif command == 0x03:
                    self.mode = payload[0] if payload else 0
                    self.reply(bytes((0xE0, 0x04, 0x70, command)), address)
                else:
                    self.payloads.append((command, bytes(payload)))


def speech_like_pcm(seconds: float) -> bytes:
    samples = []
    phase = 0.0
    for n in range(int(8000 * seconds)):
        t = n / 8000.0
        f0 = 140.0 + 30.0 * math.sin(2 * math.pi * 0.7 * t)
        phase += 2 * math.pi * f0 / 8000.0
        envelope = 0.55 + 0.45 * math.sin(2 * math.pi * 3.0 * t)
        value = sum(math.sin(k * phase) / k for k in range(1, 12))
        samples.append(int(max(-1.0, min(1.0, 0.25 * envelope * value)) * 32767))
    return struct.pack(f"<{len(samples)}h", *samples)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("protocol", choices=sorted(MODE_SETTINGS))
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()

    if not MMDVM_HOST_BINARY.is_file():
        print(f"MMDVM-Host binary not found: {MMDVM_HOST_BINARY}")
        return 2

    settings = MODE_SETTINGS[args.protocol]
    callsign = str(settings.get("callsign") or "SP5OPS")
    config = render_mmdvm_host_config(args.protocol, settings, callsign=callsign, device={"backend": "soapysdr"})
    config = config.replace("ModemPort=3334", f"ModemPort={FAKE_MODEM_PORT}")
    config = config.replace("LocalPort=3335", f"LocalPort={HOST_MODEM_PORT}")
    config = re.sub(r"\[Remote Control\]\nEnable=1", "[Remote Control]\nEnable=0", config)

    modem = FakeModem()
    modem.start()
    with tempfile.TemporaryDirectory() as tmp:
        ini = Path(tmp) / "MMDVM-Host.ini"
        ini.write_text(config, encoding="utf-8")
        process = subprocess.Popen(
            [str(MMDVM_HOST_BINARY), str(ini)],
            cwd=tmp,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines: list[str] = []
        reader = threading.Thread(target=lambda: lines.extend(iter(process.stdout.readline, "")), daemon=True)
        reader.start()
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not any("running" in line.lower() for line in lines):
                time.sleep(0.2)
            time.sleep(1.0)

            session = create_voice_session(args.protocol, mode_config=settings)
            pcm = speech_like_pcm(args.seconds)
            session.start()
            for offset in range(0, len(pcm), 320):
                session.feed_pcm(pcm[offset:offset + 320])
            status = session.end()
            session.close()
            time.sleep(2.0)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            modem.stop = True

    relevant = [line.rstrip() for line in lines if re.search(r"DMR|YSF|D-Star|P25|NXDN|FM|network|error|Error", line)]
    print("--- MMDVM-Host log (filtered) ---")
    for line in relevant[-25:]:
        print(line)
    print("--- frames written to the modem ---")
    print(dict(modem.frames))
    print("--- session ---")
    print({key: status.get(key) for key in ("network_records_sent", "ambe_frames_encoded", "pcm_frames_received")})

    voice_frames = {
        "dmr": modem.frames["DMR_DATA2"],
        "ysf": modem.frames["YSF_DATA"],
        "dstar": modem.frames["DSTAR_DATA"],
        "p25": modem.frames["P25_LDU"],
        "nxdn": modem.frames["NXDN_DATA"],
        "fm": modem.frames["FM_DATA"],
    }[args.protocol]
    # Only end-of-transmission reports carry a BER figure ("BER: x.y%").
    errors = [line for line in lines if re.search(r"BER: \d", line) and not re.search(r"BER: 0\.0%", line)]
    for line in errors:
        print("BER warning:", line.rstrip())
    ok = voice_frames > 0 and not errors
    print(f"RESULT {'OK' if ok else 'FAIL'}: {voice_frames} voice frames to the modem; ber_warnings={len(errors)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
