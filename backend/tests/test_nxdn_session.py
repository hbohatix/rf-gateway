import unittest

from app.voice import fec
from app.voice.nxdn import (
    MESSAGE_TX_REL,
    MESSAGE_VCALL,
    NXDNStreamingSession,
    lich_byte,
    LICH_STEAL_NONE,
    LICH_USC_SACCH_SS,
)

from tests.test_dmr_session import CountingEncoder, FakeEndpoint


SETTINGS = {"frequency_hz": 438800000, "radio_id": 1234, "talkgroup": 65000, "ran": 1, "call_type": "group"}


def make_session(settings=SETTINGS):
    session = NXDNStreamingSession(mode_config=settings, encoder_factory=CountingEncoder, pace=False)
    endpoint = FakeEndpoint()
    session._endpoint = endpoint
    return session, endpoint


class NXDNPacketTest(unittest.TestCase):
    def test_sequence(self):
        session, endpoint = make_session()
        session.start()
        session.feed_pcm(bytes(320 * 18))  # 18 frames -> 5 voice frames (padded to 20)
        session.end()

        packets = endpoint.packets
        self.assertTrue(all(len(p) == 102 and p[:4] == b"ICOM" for p in packets))
        frames = [p[40:73] for p in packets]
        self.assertEqual(len(frames), 1 + 5 + 1)

        header, *voice, trailer = frames
        self.assertEqual(header[5] & 0x3F, MESSAGE_VCALL)
        self.assertEqual(trailer[5] & 0x3F, MESSAGE_TX_REL)
        self.assertEqual(int.from_bytes(header[8:10], "big"), 1234)
        self.assertEqual(int.from_bytes(header[10:12], "big"), 65000)
        self.assertEqual(header[7] & 0x80, 0)  # group call

        expected_lich = lich_byte(usc=LICH_USC_SACCH_SS, option=LICH_STEAL_NONE)
        self.assertTrue(all(frame[0] == expected_lich for frame in voice))
        # SACCH superframe structure: 1/4, 2/4, 3/4, 4/4, then 1/4 again.
        self.assertEqual([frame[1] >> 6 for frame in voice], [3, 2, 1, 0, 3])

        # The four SACCH parts reassemble the 72-bit VCALL message.
        bits = []
        for frame in voice[:4]:
            bits.extend(fec.read_bit(frame[1:5], 8 + i) for i in range(18))
        self.assertEqual(fec.bits_to_bytes(bits)[:7], header[5:12])
        self.assertEqual(session.status()["padding_frames"], 2)

    def test_private_call(self):
        session, endpoint = make_session(dict(SETTINGS, call_type="private", talkgroup=4321))
        session.start()
        session.end()
        self.assertEqual(endpoint.packets[0][40 + 7] & 0x80, 0x80)

    def test_rejects_large_unit_id(self):
        session, _ = make_session(dict(SETTINGS, radio_id=2601292))
        with self.assertRaises(Exception):
            session.start()


if __name__ == "__main__":
    unittest.main()
