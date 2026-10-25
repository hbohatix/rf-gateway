import math
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.voice import fec
from app.voice.ysf import YSFStreamingSession, YSF_SYNC, encode_fich

from tests.test_dmr_session import CountingEncoder, FakeEndpoint, speech_like_pcm


NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
CHECKER = NATIVE_DIR / "tools" / "ysf_frame_check"
AMBE_LIBRARY = NATIVE_DIR / "libambe_vocoder_wrapper.so"
MMDVM_HOST_DIR = Path(__file__).resolve().parents[2] / "third_party" / "MMDVM-Host"

SETTINGS = {"frequency_hz": 438800000, "callsign": "SP5OPS", "destination": "ALL", "dg_id": 0}


def make_session(encoder_factory=CountingEncoder, settings=SETTINGS):
    session = YSFStreamingSession(mode_config=settings, encoder_factory=encoder_factory, pace=False)
    endpoint = FakeEndpoint()
    session._endpoint = endpoint
    return session, endpoint


class CrcTest(unittest.TestCase):
    @unittest.skipUnless((MMDVM_HOST_DIR / "CRC.cpp").is_file(), "MMDVM-Host submodule not checked out")
    def test_matches_mmdvm_ccitt_table(self):
        source = (MMDVM_HOST_DIR / "CRC.cpp").read_text(encoding="utf-8", errors="replace")
        match = re.search(r"CCITT16_TABLE2\[\]\s*=\s*\{(.*?)\};", source, re.S)
        table = [int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", match.group(1))]

        def table_crc(data):
            crc = 0
            for byte in data:
                crc = ((crc << 8) & 0xFFFF) ^ table[((crc >> 8) & 0xFF) ^ byte]
            crc ^= 0xFFFF
            return bytes(((crc >> 8) & 0xFF, crc & 0xFF))

        for sample in (b"", b"\x00", b"123456789", bytes(range(20)), b"SP5OPS    ALL       "):
            self.assertEqual(fec.crc_ccitt162(sample), table_crc(sample))


class YSFPacketTest(unittest.TestCase):
    def test_sequence(self):
        session, endpoint = make_session()
        session.start()
        session.feed_pcm(bytes(320 * 12))  # 12 frames -> 3 comm frames (padded)
        session.end()

        packets = endpoint.packets
        self.assertTrue(all(len(p) == 155 and p[:4] == b"YSFD" for p in packets))
        self.assertTrue(all(p[35:40] == YSF_SYNC for p in packets))
        self.assertEqual(packets[0][14:24], b"SP5OPS    ")
        self.assertEqual(packets[0][24:34], b"ALL       ")
        counters = [p[34] >> 1 for p in packets]
        self.assertEqual(counters, list(range(len(packets))))
        self.assertEqual([p[34] & 1 for p in packets], [0] * (len(packets) - 1) + [1])
        self.assertEqual(len(packets), 1 + 3 + 1)
        self.assertEqual(session.status()["padding_frames"], 3)

    def test_fich_changes_with_frame_number(self):
        self.assertNotEqual(encode_fich(fi=1, fn=0, ft=6), encode_fich(fi=1, fn=1, ft=6))
        self.assertEqual(len(encode_fich(fi=0, fn=0, ft=6)), 25)

    def test_rejects_long_callsign(self):
        session, _ = make_session(settings=dict(SETTINGS, callsign="TOOLONGCALL1"))
        with self.assertRaises(Exception):
            session.start()


@unittest.skipUnless(CHECKER.is_file() and AMBE_LIBRARY.is_file(), "native AMBE encoder / YSF checker not built")
class YSFAgainstMMDVMHostTest(unittest.TestCase):
    def test_frames_validate_and_audio_survives(self):
        from app.voice.ambe_vocoder import create_ambe_encoder

        pcm_in = speech_like_pcm(3.0)
        session, endpoint = make_session(create_ambe_encoder)
        session.start()
        for offset in range(0, len(pcm_in), 640):
            session.feed_pcm(pcm_in[offset:offset + 640])
        session.end()

        lines = ["Y " + packet[35:155].hex() for packet in endpoint.packets]
        with tempfile.TemporaryDirectory() as tmp:
            pcm_path = Path(tmp) / "decoded.raw"
            result = subprocess.run(
                [str(CHECKER), str(pcm_path)], input="\n".join(lines) + "\n",
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("HEADER src=SP5OPS     dst=ALL", result.stdout)
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
        self.assertGreater(best, 0.8, f"envelope correlation {best:.2f}")
        mean_in = sum(a_all) / len(a_all)
        mean_out = sum(b_all) / len(b_all)
        self.assertLess(mean_out, mean_in * 2.5)
        self.assertGreater(mean_out, mean_in / 4)


if __name__ == "__main__":
    unittest.main()
