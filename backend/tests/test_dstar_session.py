import math
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.voice import fec
from app.voice.dstar import DStarStreamingSession, build_header, slow_data_text_frames

from tests.test_dmr_session import FakeEndpoint, speech_like_pcm


NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
CHECKER = NATIVE_DIR / "tools" / "dstar_frame_check"
AMBE_LIBRARY = NATIVE_DIR / "libambe_vocoder_wrapper.so"
MMDVM_HOST_DIR = Path(__file__).resolve().parents[2] / "third_party" / "MMDVM-Host"

SETTINGS = {"frequency_hz": 438800000, "callsign": "SP5OPS", "suffix": "RFGW", "your_call": "CQCQCQ"}


class ParamEncoder:
    def __init__(self, settings):
        self.count = 0

    def encode_params(self, pcm_frame):
        self.count += 1
        return [self.count % 128, 3, 5, 100, 50, 7, 9, 2, 4]

    def close(self):
        pass

    def status(self):
        return {"backend": "fake"}


def make_session(encoder_factory=ParamEncoder):
    session = DStarStreamingSession(mode_config=SETTINGS, encoder_factory=encoder_factory, pace=False)
    endpoint = FakeEndpoint()
    session._endpoint = endpoint
    return session, endpoint


class DStarCrcTest(unittest.TestCase):
    @unittest.skipUnless((MMDVM_HOST_DIR / "CRC.cpp").is_file(), "MMDVM-Host submodule not checked out")
    def test_matches_mmdvm_table(self):
        source = (MMDVM_HOST_DIR / "CRC.cpp").read_text(encoding="utf-8", errors="replace")
        table = [int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", re.search(r"CCITT16_TABLE1\[\]\s*=\s*\{(.*?)\};", source, re.S).group(1))]

        def table_crc(data):
            crc = 0xFFFF
            for byte in data:
                crc = (crc >> 8) ^ table[(crc & 0xFF) ^ byte]
            crc ^= 0xFFFF
            return bytes((crc & 0xFF, (crc >> 8) & 0xFF))

        for sample in (b"", b"123456789", bytes(range(39))):
            self.assertEqual(fec.crc_ccitt161(sample), table_crc(sample))


class DStarPacketTest(unittest.TestCase):
    def test_sequence(self):
        session, endpoint = make_session()
        session.start()
        session.feed_pcm(bytes(320 * 25))
        session.end()
        packets = endpoint.packets
        self.assertEqual(packets[0][:5], b"DSRP\x20")
        self.assertEqual(len(packets[0]), 49)
        stream = packets[0][5:7]
        data = packets[1:]
        self.assertEqual(len(data), 26)
        self.assertTrue(all(p[:5] == b"DSRP\x21" and p[5:7] == stream and len(p) == 21 for p in data))
        seqs = [p[7] & 0x1F for p in data]
        self.assertEqual(seqs[:22], list(range(21)) + [0])
        self.assertEqual([p[7] & 0x40 for p in data], [0] * 25 + [0x40])
        self.assertEqual(data[0][18:21], b"\x55\x2d\x16")

    def test_header_crc_and_fields(self):
        header = build_header(my_call="SP5OPS", my_suffix="RFGW", your_call="CQCQCQ", rpt1="DIRECT", rpt2="DIRECT")
        self.assertEqual(len(header), 41)
        self.assertEqual(header[27:35], b"SP5OPS  ")
        self.assertEqual(fec.crc_ccitt161(header[:39]), header[39:41])

    def test_text_message_chunks(self):
        chunks = slow_data_text_frames("RF Gateway")
        self.assertEqual(len(chunks), 8)
        first = bytes(b ^ s for b, s in zip(chunks[0], (0x70, 0x4F, 0x93)))
        self.assertEqual(first, b"\x40RF")


@unittest.skipUnless(CHECKER.is_file() and AMBE_LIBRARY.is_file(), "native AMBE encoder / D-Star checker not built")
class DStarAgainstMMDVMHostTest(unittest.TestCase):
    def test_frames_validate_and_audio_survives(self):
        pcm_in = speech_like_pcm(3.0)
        session, endpoint = make_session(encoder_factory=None)
        from app.voice.dstar import _software_dstar_encoder
        session._encoder_factory = _software_dstar_encoder
        session.start()
        for offset in range(0, len(pcm_in), 640):
            session.feed_pcm(pcm_in[offset:offset + 640])
        session.end()

        lines = []
        for packet in endpoint.packets:
            if packet[4] == 0x20:
                lines.append("H " + packet[8:49].hex())
            elif not packet[7] & 0x40:
                lines.append("V " + packet[9:21].hex())
        with tempfile.TemporaryDirectory() as tmp:
            pcm_path = Path(tmp) / "decoded.raw"
            result = subprocess.run([str(CHECKER), str(pcm_path)], input="\n".join(lines) + "\n",
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("HEADER my=SP5OPS  /RFGW your=CQCQCQ", result.stdout)
            decoded = pcm_path.read_bytes()

        samples_in = struct.unpack(f"<{len(pcm_in) // 2}h", pcm_in)
        samples_out = struct.unpack(f"<{len(decoded) // 2}h", decoded)

        def energy(samples):
            return [math.sqrt(sum(s * s for s in samples[i:i + 160]) / 160.0) for i in range(0, len(samples) - 160, 160)]

        a_all, b_all = energy(samples_in), energy(samples_out)
        best = -1.0
        for lag in range(6):
            a = a_all[: len(b_all) - lag]
            b = b_all[lag: lag + len(a)]
            n = min(len(a), len(b))
            a, b = a[:n], b[:n]
            ma, mb = sum(a) / n, sum(b) / n
            cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            va = math.sqrt(sum((x - ma) ** 2 for x in a))
            vb = math.sqrt(sum((y - mb) ** 2 for y in b))
            if va and vb:
                best = max(best, cov / (va * vb))
        self.assertGreater(best, 0.75, f"envelope correlation {best:.2f}")
        mean_in = sum(a_all) / len(a_all)
        mean_out = sum(b_all) / len(b_all)
        # Level must be roughly preserved (no clipping from the gain quantizer).
        self.assertLess(mean_out, mean_in * 2.5)
        self.assertGreater(mean_out, mean_in / 4)


if __name__ == "__main__":
    unittest.main()
