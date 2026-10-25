import math
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.voice import fec
from app.voice.dmr import (
    DT_TERMINATOR_WITH_LC,
    DT_VOICE_LC_HEADER,
    DMRStreamingSession,
    build_lc_burst,
    build_full_lc,
)


NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
CHECKER = NATIVE_DIR / "tools" / "dmr_frame_check"
AMBE_LIBRARY = NATIVE_DIR / "libambe_vocoder_wrapper.so"

SETTINGS = {
    "frequency_hz": 438800000,
    "radio_id": 2601292,
    "talkgroup": 260,
    "timeslot": 2,
    "color_code": 1,
    "call_type": "group",
}


class FakeEndpoint:
    def __init__(self):
        self.packets = []
        self.is_open = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def send(self, payload):
        self.packets.append(bytes(payload))
        return len(payload)

    def drain(self):
        return 0

    def status(self):
        return {"open": self.is_open, "datagrams_sent": len(self.packets)}


class CountingEncoder:
    """Deterministic stand-in for the AMBE encoder."""

    def __init__(self, settings):
        self.count = 0

    def encode_49(self, pcm_frame):
        self.count += 1
        return [(self.count >> (i % 8)) & 1 for i in range(49)]

    def close(self):
        pass

    def status(self):
        return {"backend": "fake", "frames_encoded": self.count}


def make_session(encoder_factory=CountingEncoder):
    session = DMRStreamingSession(mode_config=SETTINGS, encoder_factory=encoder_factory, pace=False)
    endpoint = FakeEndpoint()
    session._endpoint = endpoint
    return session, endpoint


def speech_like_pcm(seconds: float) -> bytes:
    """Voiced, slowly gliding harmonic signal with a syllable-rate envelope."""
    samples = []
    phase = 0.0
    total = int(8000 * seconds)
    for n in range(total):
        t = n / 8000.0
        f0 = 140.0 + 30.0 * math.sin(2 * math.pi * 0.7 * t)
        phase += 2 * math.pi * f0 / 8000.0
        envelope = 0.55 + 0.45 * math.sin(2 * math.pi * 3.0 * t)
        value = sum(math.sin(k * phase) / k for k in range(1, 12))
        samples.append(int(max(-1.0, min(1.0, 0.25 * envelope * value)) * 32767))
    return struct.pack(f"<{len(samples)}h", *samples)


class DMRPacketSequenceTest(unittest.TestCase):
    def test_header_voice_and_terminator(self):
        session, endpoint = make_session()
        session.start()
        session.feed_pcm(bytes(320 * 20))  # 400 ms -> 20 frames
        session.end()

        packets = endpoint.packets
        self.assertTrue(all(len(p) == 55 and p[:4] == b"DMRD" for p in packets))
        flags = [p[15] for p in packets]

        # Two LC headers, 7 voice bursts (20 frames padded to 21), terminator.
        self.assertEqual(flags[0], 0x80 | 0x20 | DT_VOICE_LC_HEADER)
        self.assertEqual(flags[1], 0x80 | 0x20 | DT_VOICE_LC_HEADER)
        self.assertEqual(flags[-1], 0x80 | 0x20 | DT_TERMINATOR_WITH_LC)
        voice = flags[2:-1]
        self.assertEqual(len(voice), 7)
        self.assertEqual(voice, [0x90, 0x81, 0x82, 0x83, 0x84, 0x85, 0x90])

        seqs = [p[4] for p in packets]
        self.assertEqual(seqs, list(range(len(packets))))
        stream_ids = {p[16:20] for p in packets}
        self.assertEqual(len(stream_ids), 1)
        for packet in packets:
            self.assertEqual(int.from_bytes(packet[5:8], "big"), SETTINGS["radio_id"])
            self.assertEqual(int.from_bytes(packet[8:11], "big"), SETTINGS["talkgroup"])

        status = session.status()
        self.assertEqual(status["padding_frames"], 1)
        self.assertEqual(status["voice_bursts_sent"], 7)
        self.assertEqual(status["superframes_sent"], 1)

    def test_private_call_sets_flco_bit(self):
        settings = dict(SETTINGS, call_type="private", talkgroup=2601001)
        session = DMRStreamingSession(mode_config=settings, encoder_factory=CountingEncoder, pace=False)
        endpoint = FakeEndpoint()
        session._endpoint = endpoint
        session.start()
        session.end()
        self.assertTrue(all(p[15] & 0x40 for p in endpoint.packets))

    def test_voice_frames_round_trip(self):
        session, endpoint = make_session()
        session.start()
        session.feed_pcm(bytes(320 * 3))
        session.end()
        burst = endpoint.packets[2][20:53]
        for index in range(3):
            a, b, c = fec.extract_dmr_ambe(burst, index)
            expected = [((index + 1) >> (i % 8)) & 1 for i in range(49)]
            self.assertEqual(fec.abc_to_ambe49(a, b, c), expected)

    def test_rejects_timeslot_out_of_range(self):
        session = DMRStreamingSession(mode_config=dict(SETTINGS, timeslot=3), encoder_factory=CountingEncoder, pace=False)
        session._endpoint = FakeEndpoint()
        with self.assertRaises(Exception):
            session.start()


@unittest.skipUnless(CHECKER.is_file() and AMBE_LIBRARY.is_file(), "native AMBE encoder / frame checker not built")
class DMRAgainstMMDVMHostTest(unittest.TestCase):
    def test_frames_validate_and_audio_survives(self):
        from app.voice.ambe_vocoder import create_ambe_encoder

        pcm_in = speech_like_pcm(3.0)
        session, endpoint = make_session(create_ambe_encoder)
        session.start()
        for offset in range(0, len(pcm_in), 640):
            session.feed_pcm(pcm_in[offset:offset + 640])
        session.end()

        lines = []
        for packet in endpoint.packets:
            flags = packet[15]
            burst = packet[20:53].hex()
            if flags & 0x20:
                lines.append(("H" if (flags & 0x0F) == DT_VOICE_LC_HEADER else "T") + " " + burst)
            else:
                lines.append("V " + burst)

        with tempfile.TemporaryDirectory() as tmp:
            pcm_path = Path(tmp) / "decoded.raw"
            result = subprocess.run(
                [str(CHECKER), str(pcm_path)],
                input="\n".join(lines) + "\n",
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"src={SETTINGS['radio_id']} dst={SETTINGS['talkgroup']}", result.stdout)
            decoded = pcm_path.read_bytes()

        samples_in = struct.unpack(f"<{len(pcm_in) // 2}h", pcm_in)
        samples_out = struct.unpack(f"<{len(decoded) // 2}h", decoded)
        self.assertGreaterEqual(len(samples_out), len(samples_in) - 160 * 3)

        def frame_energy(samples):
            return [
                math.sqrt(sum(s * s for s in samples[i:i + 160]) / 160.0)
                for i in range(0, len(samples) - 160, 160)
            ]

        energy_in = frame_energy(samples_in)
        energy_out = frame_energy(samples_out)
        # The vocoder delays audio by a few frames; find the best lag.
        best = -1.0
        for lag in range(0, 6):
            a = energy_in[: len(energy_out) - lag]
            b = energy_out[lag: lag + len(a)]
            n = min(len(a), len(b))
            a, b = a[:n], b[:n]
            mean_a, mean_b = sum(a) / n, sum(b) / n
            cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
            var_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
            var_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
            if var_a and var_b:
                best = max(best, cov / (var_a * var_b))
        # The decoded audio must follow the syllable envelope of the input.
        self.assertGreater(best, 0.8, f"envelope correlation {best:.2f}")
        mean_in = sum(energy_in) / len(energy_in)
        mean_out = sum(energy_out) / len(energy_out)
        self.assertLess(mean_out, mean_in * 2.5)
        self.assertGreater(mean_out, mean_in / 4)


class LcBurstTest(unittest.TestCase):
    def test_lc_burst_is_33_bytes_and_deterministic(self):
        lc = build_full_lc(flco=0, src_id=2601292, dst_id=260)
        first = build_lc_burst(lc, DT_VOICE_LC_HEADER)
        second = build_lc_burst(lc, DT_VOICE_LC_HEADER)
        self.assertEqual(len(first), 33)
        self.assertEqual(first, second)
        self.assertNotEqual(first, build_lc_burst(lc, DT_TERMINATOR_WITH_LC))


if __name__ == "__main__":
    unittest.main()
