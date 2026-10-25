import struct
import unittest

from app.voice.fm import FM_END_PACKET, FM_TAIL_SILENCE_FRAMES, FMStreamingSession


class FakeEndpoint:
    def __init__(self):
        self.packets = []

    def open(self):
        pass

    def close(self):
        pass

    def send(self, payload):
        self.packets.append(bytes(payload))
        return len(payload)

    def drain(self):
        return 0

    def status(self):
        return {"datagrams_sent": len(self.packets)}


class FMSessionTest(unittest.TestCase):
    def make(self, **settings):
        config = {"frequency_hz": 145500000, "deviation_khz": 2.5, "pre_emphasis": True, **settings}
        session = FMStreamingSession(mode_config=config, callsign="SP5OPS", pace=False)
        endpoint = FakeEndpoint()
        session._endpoint = endpoint
        return session, endpoint

    def test_packet_sequence(self):
        session, endpoint = self.make()
        session.start()
        session.feed_pcm(bytes(320 * 5 + 100))
        session.end()
        packets = endpoint.packets
        self.assertEqual(packets[0], b"FMSSP5OPS\x00")
        data = [p for p in packets if p.startswith(b"FMD")]
        # 5 full frames + padded remainder + tail silence.
        self.assertEqual(len(data), 6 + FM_TAIL_SILENCE_FRAMES)
        self.assertTrue(all(len(p) == 3 + 320 for p in data))
        self.assertEqual(packets[-1], FM_END_PACKET)

    def test_gain_is_applied_and_clipped(self):
        session, endpoint = self.make(audio_gain=2.0)
        session.start()
        pcm = struct.pack("<160h", *([1000] * 80 + [30000] * 80))
        session.feed_pcm(pcm)
        session.end()
        samples = struct.unpack("<160h", endpoint.packets[1][3:])
        self.assertEqual(samples[0], 2000)
        self.assertEqual(samples[-1], 32767)

    def test_rejects_odd_length_pcm(self):
        session, _ = self.make()
        session.start()
        with self.assertRaises(Exception):
            session.feed_pcm(b"\x00\x01\x02")


if __name__ == "__main__":
    unittest.main()
