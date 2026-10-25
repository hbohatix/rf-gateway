import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.rf import network_devices


BASE = """[General]
Daemon=0

[Modem]
Driver=Soapy

[Soapy]
# comment
Type=sx
RxGain=50
TxGain=0

[Multi]
LocalPort=48100
"""


class NetworkDevicesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(network_devices, "STORE_PATH", Path(self.tmp.name) / "devices.json")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_add_list_remove(self):
        device = network_devices.add_network_device({"sdr_type": "plutosdr", "uri": "ip:192.168.2.1", "tx_gain": 40})
        self.assertTrue(device["id"].startswith("net-"))
        self.assertEqual(device["rx_gain"], 30)  # type default
        self.assertEqual([d["id"] for d in network_devices.list_network_devices()], [device["id"]])
        self.assertTrue(network_devices.remove_network_device(device["id"]))
        self.assertEqual(network_devices.list_network_devices(), [])

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            network_devices.add_network_device({"sdr_type": "hackrf"})
        with self.assertRaises(ValueError):
            network_devices.add_network_device({"sdr_type": "plutosdr", "uri": "ip:1.2.3.4\nType=sx"})
        with self.assertRaises(ValueError):
            network_devices.add_network_device({"sdr_type": "usrp", "tx_gain": 150})

    def test_render_replaces_soapy_section(self):
        device = network_devices.to_rf_device(
            {"id": "net-1", "sdr_type": "plutosdr", "uri": "ip:192.0.2.1", "rx_gain": 30, "tx_gain": 45, "label": "Pluto"},
            [[144_000_000, 148_000_000]],
        )
        text = network_devices.render_mmdvm_iq_config(BASE, device)
        self.assertIn("[Soapy]\nType=plutosdr\nRxGain=30\nTxGain=45\nURI=ip:192.0.2.1\n", text)
        self.assertNotIn("Type=sx", text)
        self.assertIn("[Multi]", text)
        self.assertEqual(text.count("[Soapy]"), 1)
        self.assertEqual(device["backend"], "soapysdr_network")
        self.assertFalse(device["probe_ok"])  # TEST-NET address is unreachable


if __name__ == "__main__":
    unittest.main()
