import unittest
from unittest import mock

from app import rf_control


class FakeManager:
    def __init__(self, protocol=None, device_id=None):
        self.protocol = protocol
        self.device_id = device_id
        self.calls = []

    @property
    def is_running(self):
        return self.protocol is not None

    def status(self):
        return {
            "runtime_active": self.is_running,
            "protocol": self.protocol,
            "device_id": self.device_id,
            "rf_tx_active": False,
        }

    def start(self, protocol, settings, *, device, callsign):
        self.calls.append(("start", protocol, device["id"], callsign))
        self.protocol = protocol
        self.device_id = device["id"]
        return self.status()

    def stop(self):
        self.calls.append(("stop",))
        self.protocol = None
        self.device_id = None
        return self.status()


DEVICE = {"id": "soapy-0", "available": True, "probe_ok": True, "capabilities": {}}
MODES = {
    "fm": {"frequency_hz": 433450000, "deviation_khz": 2.5, "channel_spacing_khz": 12.5, "pre_emphasis": True},
    "dmr": {"frequency_hz": 433450000, "radio_id": 9999, "talkgroup": 260, "timeslot": 2, "color_code": 1},
    "p25": {"frequency_hz": 438800000, "radio_id": 1, "talkgroup": 1, "nac": "293", "modulation": "c4fm"},
}


class RFControlTest(unittest.TestCase):
    def setUp(self):
        self.manager = FakeManager()
        self.route_states = []
        patches = [
            mock.patch.object(rf_control, "mmdvm_process_manager", self.manager),
            mock.patch.object(rf_control, "get_rf_device", lambda device_id: dict(DEVICE, id=device_id)),
            mock.patch.object(rf_control, "validate_device_frequency", lambda device, hz: None),
            mock.patch.object(rf_control.route_runtime_manager, "list_states", lambda: list(self.route_states)),
            mock.patch.object(rf_control.mode_config_store, "get_mode", lambda protocol: dict(MODES.get(protocol, {}))),
            mock.patch.object(rf_control.mode_config_store, "save_mode", lambda protocol, settings: settings),
            mock.patch.object(rf_control.rf_device_manager, "close", lambda device_id: None),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def route(self, protocol, route_id="r1", device_id="soapy-0"):
        return {"id": route_id, "protocol": protocol, "device_id": device_id}

    def test_starts_runtime_when_stopped(self):
        plan = rf_control.ensure_rf_runtime_for_route(self.route("dmr"))
        self.assertEqual(plan["action"], "start")
        self.assertEqual(self.manager.protocol, "dmr")
        self.assertEqual(self.manager.calls, [("start", "dmr", "soapy-0", "SP5OPS")])

    def test_nothing_to_do_when_runtime_matches(self):
        self.manager.protocol, self.manager.device_id = "fm", "soapy-0"
        plan = rf_control.ensure_rf_runtime_for_route(self.route("fm"))
        self.assertEqual(plan["action"], "none")
        self.assertTrue(plan["matches"])
        self.assertEqual(self.manager.calls, [])

    def test_switches_protocol_when_no_other_route_runs(self):
        # The reported bug: RF runtime in FM, route encodes P25 -> nothing on air.
        self.manager.protocol, self.manager.device_id = "fm", "soapy-0"
        plan = rf_control.ensure_rf_runtime_for_route(self.route("p25"))
        self.assertEqual(plan["action"], "switch")
        self.assertEqual(self.manager.calls, [("stop",), ("start", "p25", "soapy-0", "SP5OPS")])
        self.assertIn("FM to P25", plan["message"])

    def test_blocks_when_another_route_uses_the_runtime(self):
        self.manager.protocol, self.manager.device_id = "p25", "soapy-0"
        self.route_states = [{"route_id": "other", "state": "running", "protocol": "p25", "device_id": "soapy-0"}]
        with self.assertRaises(rf_control.RFControlError) as context:
            rf_control.ensure_rf_runtime_for_route(self.route("dmr"))
        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(self.manager.protocol, "p25")

    def test_manual_start_refuses_protocol_of_running_route(self):
        self.route_states = [{"route_id": "abcdef12", "state": "running", "protocol": "p25", "device_id": "soapy-0"}]
        with self.assertRaises(rf_control.RFControlError) as context:
            rf_control.start_rf_runtime("fm", MODES["fm"], "soapy-0")
        self.assertIn("P25", str(context.exception))
        self.assertEqual(self.manager.calls, [])

    def test_missing_mode_settings(self):
        with mock.patch.object(rf_control.mode_config_store, "get_mode", lambda protocol: None):
            with self.assertRaises(rf_control.RFControlError):
                rf_control.ensure_rf_runtime_for_route(self.route("nxdn"))


class DeviceReservationTest(unittest.TestCase):
    def test_ready_route_does_not_reserve_device(self):
        from app.route_runtime import RouteRuntimeManager

        manager = RouteRuntimeManager()
        manager._states["a"] = {"route_id": "a", "device_id": "soapy-0", "state": "ready"}
        self.assertIsNone(manager._device_in_use("b", "soapy-0"))
        manager._states["a"]["state"] = "running"
        self.assertEqual(manager._device_in_use("b", "soapy-0"), "a")


if __name__ == "__main__":
    unittest.main()
