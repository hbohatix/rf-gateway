import math
import socket
import struct
import threading
import time
import unittest

from app.remote_sdr.client import parse_remote_sdr_url

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class ParseRemoteSdrUrlTest(unittest.TestCase):
    def test_rtl_tcp_defaults_and_canonical_url(self):
        config = parse_remote_sdr_url("rtl_tcp://192.168.1.50?freq=145.5")
        self.assertEqual(config.kind, "rtl_tcp")
        self.assertEqual(config.port, 1234)
        self.assertEqual(config.frequency_hz, 145_500_000)
        self.assertEqual(config.modulation, "nfm")
        self.assertIsNone(config.squelch_db)
        self.assertEqual(config.url, "rtl_tcp://192.168.1.50:1234?freq=145500000&mod=nfm&gain=auto")

    def test_rtl_tcp_manual_gain_and_squelch(self):
        config = parse_remote_sdr_url("rtl_tcp://sdr.lan:7373?freq=433500000&mod=am&gain=28.0&squelch=-45&ppm=3")
        self.assertEqual(config.gain, "28.0")
        self.assertEqual(config.squelch_db, -45.0)
        self.assertEqual(config.ppm, 3)
        self.assertEqual(config.modulation, "am")

    def test_kiwisdr(self):
        config = parse_remote_sdr_url("kiwisdr://kiwi.example.org?freq=7100000&mod=lsb")
        self.assertEqual(config.kind, "kiwisdr")
        self.assertEqual(config.port, 8073)
        self.assertEqual(config.modulation, "lsb")

    def test_kiwisdr_rejects_vhf(self):
        with self.assertRaises(ValueError):
            parse_remote_sdr_url("kiwisdr://kiwi.example.org?freq=145500000")

    def test_udp_raw_pcm_defaults(self):
        config = parse_remote_sdr_url("udp://0.0.0.0:7355")
        self.assertEqual(config.kind, "audio_stream")
        self.assertEqual(config.pcm_format, "s16le")
        self.assertEqual(config.pcm_rate, 48000)

    def test_rejects_unknown_scheme_and_credentials(self):
        with self.assertRaises(ValueError):
            parse_remote_sdr_url("ftp://example.org/audio")
        with self.assertRaises(ValueError):
            parse_remote_sdr_url("rtl_tcp://user:pw@host?freq=145500000")
        with self.assertRaises(ValueError):
            parse_remote_sdr_url("rtl_tcp://host")  # no frequency


def fm_iq(seconds, *, iq_rate, offset_hz, tone_hz, deviation_hz, amplitude=0.6, noise=0.0, seed=1):
    n = np.arange(int(seconds * iq_rate))
    phase = 2 * np.pi * offset_hz * n / iq_rate
    phase += (deviation_hz / tone_hz) * np.sin(2 * np.pi * tone_hz * n / iq_rate)
    iq = amplitude * np.exp(1j * phase)
    if noise:
        rng = np.random.default_rng(seed)
        iq = iq + noise * (rng.standard_normal(n.size) + 1j * rng.standard_normal(n.size))
    return iq.astype(np.complex64)


def dominant_frequency(samples, rate):
    window = samples * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(window))
    spectrum[:5] = 0
    return np.argmax(spectrum) * rate / len(samples)


@unittest.skipIf(np is None, "numpy not installed")
class DemodulatorTest(unittest.TestCase):
    def test_nfm_recovers_tone(self):
        from app.remote_sdr.dsp import IqDemodulator

        demod = IqDemodulator(iq_rate=240000, offset_hz=60000, modulation="nfm",
                              channel_bandwidth_hz=12500, squelch_db=-200.0)
        iq = fm_iq(1.0, iq_rate=240000, offset_hz=60000, tone_hz=1000, deviation_hz=2500)
        audio = np.concatenate([demod.process(iq[i:i + 9600]) for i in range(0, iq.size, 9600)])
        self.assertAlmostEqual(len(audio), 8000, delta=10)
        tail = audio[2000:]
        self.assertAlmostEqual(dominant_frequency(tail, 8000), 1000, delta=15)
        self.assertGreater(float(np.sqrt(np.mean(tail ** 2))), 0.2)

    def test_auto_squelch_mutes_noise_and_opens_on_carrier(self):
        from app.remote_sdr.dsp import IqDemodulator

        demod = IqDemodulator(iq_rate=240000, offset_hz=60000, modulation="nfm",
                              channel_bandwidth_hz=12500, squelch_db=None)
        rng = np.random.default_rng(7)
        noise = (0.01 * (rng.standard_normal(240000) + 1j * rng.standard_normal(240000))).astype(np.complex64)
        quiet = np.concatenate([demod.process(noise[i:i + 9600]) for i in range(0, noise.size, 9600)])
        self.assertEqual(float(np.max(np.abs(quiet))), 0.0)
        self.assertFalse(demod.squelch.open)

        signal = fm_iq(1.0, iq_rate=240000, offset_hz=60000, tone_hz=800, deviation_hz=2500, noise=0.01)
        loud = np.concatenate([demod.process(signal[i:i + 9600]) for i in range(0, signal.size, 9600)])
        self.assertTrue(demod.squelch.open)
        self.assertGreater(float(np.max(np.abs(loud))), 0.1)

    def test_resampler_rate(self):
        from app.remote_sdr.dsp import Resampler

        resampler = Resampler(12001.135, 8000)
        tone = np.sin(2 * np.pi * 600 * np.arange(12001) / 12001.135).astype(np.float32)
        out = np.concatenate([resampler.process(tone[i:i + 512]) for i in range(0, tone.size, 512)])
        self.assertAlmostEqual(len(out), 8000, delta=5)
        self.assertAlmostEqual(dominant_frequency(out[1000:], 8000), 600, delta=10)


class FakeRtlTcpServer(threading.Thread):
    def __init__(self, iq_bytes: bytes):
        super().__init__(daemon=True)
        self.iq_bytes = iq_bytes
        self.commands = []
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]

    def run(self):
        conn, _ = self.server.accept()
        conn.sendall(b"RTL0" + struct.pack(">II", 5, 29))
        conn.settimeout(0.05)
        sent = 0
        chunk = 240000 * 2 // 50  # 20 ms
        start = time.monotonic()
        try:
            while sent < len(self.iq_bytes):
                try:
                    data = conn.recv(64)
                    for i in range(0, len(data) - 4, 5):
                        self.commands.append(struct.unpack(">BI", data[i:i + 5]))
                except socket.timeout:
                    pass
                conn.sendall(self.iq_bytes[sent:sent + chunk])
                sent += chunk
                target = start + sent / (240000 * 2)
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
        except OSError:
            pass
        finally:
            conn.close()
            self.server.close()


@unittest.skipIf(np is None, "numpy not installed")
class RtlTcpStreamTest(unittest.TestCase):
    def test_end_to_end_tone(self):
        from app.remote_sdr.client import remote_sdr_client

        iq = fm_iq(1.5, iq_rate=240000, offset_hz=60000, tone_hz=1200, deviation_hz=2500)
        interleaved = np.empty(iq.size * 2, dtype=np.float32)
        interleaved[0::2] = iq.real
        interleaved[1::2] = iq.imag
        raw = np.clip(np.round(interleaved * 127.5 + 127.5), 0, 255).astype(np.uint8).tobytes()
        server = FakeRtlTcpServer(raw)
        server.start()

        stream = remote_sdr_client.open_stream(f"rtl_tcp://127.0.0.1:{server.port}?freq=145500000&squelch=off")
        chunks = []
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and len(chunks) < 60:
            chunk = stream.read_chunk(0.5)
            if chunk:
                chunks.append(chunk)
        status = stream.status()
        stream.close()

        self.assertGreaterEqual(len(chunks), 40, status)
        self.assertTrue(all(len(c) == 320 for c in chunks))
        audio = np.frombuffer(b"".join(chunks[10:]), dtype="<i2").astype(np.float32) / 32768
        self.assertAlmostEqual(dominant_frequency(audio, 8000), 1200, delta=20)
        # Tuned 60 kHz below the channel, sample rate 240k, auto gain.
        self.assertIn((0x02, 240000), server.commands)
        self.assertIn((0x01, 145500000 - 60000), server.commands)
        self.assertEqual(status["tuner"], "R820T")


if __name__ == "__main__":
    unittest.main()
