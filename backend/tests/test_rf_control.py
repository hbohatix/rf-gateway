import unittest
from unittest import mock

from app import rf_control, routes
from app.mmdvm.config_generator import render_mmdvm_host_config


class FakeManager:
    def __init__(self):
        self.protocol = None
        self.calls = []

    @property
    def is_running(self):
        return self.protocol is not None

    def status(self):
        return {"runtime_active": self.is_running, "rf_tx_active": False}

    def start(self, protocol, settings, *, device, callsign):
        self.calls.append(("start", protocol, settings.get("talkgroup")))
        self.protocol = protocol
        return self.status()

    def stop(self):
        self.calls.append(("stop",))
        self.protocol = None
        return self.status()


DMR = {"frequency_hz": 433450000, "radio_id": 9999, "talkgroup": 12345, "timeslot": 1, "color_code": 15,
       "call_type": "group"}
P25 = {"frequency_hz": 438800000, "radio_id": 1, "talkgroup": 1, "nac": "293", "modulation": "c4fm"}


class FakeStore:
    def __init__(self):
        self.active = None
        self.modes = {"dmr": dict(DMR), "p25": dict(P25)}

    def get_active_protocol(self):
        return self.active

    def get_mode(self, protocol):
        mode = self.modes.get(protocol)
        return dict(mode) if mode else None


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.manager = FakeManager()
        self.store = FakeStore()
        for patch in (
            mock.patch.object(rf_control, "mmdvm_process_manager", self.manager),
            mock.patch.object(rf_control, "mode_config_store", self.store),
            mock.patch.object(rf_control, "get_rf_device", lambda device_id: {"id": device_id, "available": True, "probe_ok": True}),
            mock.patch.object(rf_control, "validate_device_frequency", lambda device, hz: None),
            mock.patch.object(rf_control.rf_device_manager, "close", lambda device_id: None),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        rf_control.runtime_state.update(protocol=None, device_id=None, config=None)

    def test_start_keep_restart(self):
        self.assertEqual(rf_control.ensure_runtime("dmr", DMR, "sx"), "started")
        self.assertEqual(rf_control.ensure_runtime("dmr", {**DMR, "updated_at": "later"}, "sx"), "kept")
        self.assertEqual(rf_control.ensure_runtime("dmr", {**DMR, "talkgroup": 9}, "sx"), "restarted")
        self.assertEqual(rf_control.ensure_runtime("p25", P25, "sx"), "restarted")
        self.assertEqual(
            self.manager.calls,
            [("start", "dmr", 12345), ("stop",), ("start", "dmr", 9), ("stop",), ("start", "p25", 1)],
        )

    def test_timeslot_1_is_accepted(self):
        rf_control.ensure_runtime("dmr", DMR, "sx")
        self.assertEqual(self.manager.protocol, "dmr")

    def test_require_active_mode(self):
        with self.assertRaises(rf_control.RFControlError):
            rf_control.require_active_mode()
        self.store.active = "dmr"
        self.assertEqual(rf_control.require_active_mode()[0], "dmr")

    def test_describe_mode(self):
        self.assertEqual(rf_control.describe_mode("dmr", DMR), "DMR · TS1 · CC15 · TG 12345 · 433.4500 MHz")
        self.assertIsNone(rf_control.describe_mode(None, None))


class DmrDuplexConfigTest(unittest.TestCase):
    def test_dmr_runs_duplex_with_both_slots(self):
        config = render_mmdvm_host_config("dmr", DMR, callsign="SP5OPS", device={"backend": "soapysdr"})
        self.assertIn("Duplex=1", config)
        self.assertIn("Slot1=1\nSlot2=1", config)

    def test_other_modes_stay_simplex(self):
        config = render_mmdvm_host_config("p25", P25, callsign="SP5OPS", device={"backend": "soapysdr"})
        self.assertIn("Duplex=0", config)


class TakeOverTest(unittest.TestCase):
    """Starting a route stops whatever else is on air and uses the current mode."""

    def setUp(self):
        self.manager = routes.route_runtime_manager.__class__()
        self.halted = []
        self.ensured = []
        self.stored_routes = [
            {"id": "a", "source_id": "sa", "device_id": "sx", "protocol": "p25", "enabled": True},
            {"id": "b", "source_id": "sb", "device_id": "sx", "protocol": "p25", "enabled": True},
        ]

        def preflight(route):
            state = {"route_id": route["id"], "state": "ready", "runtime_ready": True,
                     "protocol": route["protocol"], "device_id": route["device_id"]}
            self.manager._states[route["id"]] = state
            return dict(state)

        def halt(route_id, *, clear_queue):
            self.halted.append(route_id)
            self.manager._states.pop(route_id, None)
            return {"runtime": {}, "worker": None, "processor": None, "live_audio": None, "queue_clear": None, "queue": {}}

        patches = (
            mock.patch.object(routes, "route_runtime_manager", self.manager),
            mock.patch.object(routes, "require_active_mode", lambda: ("dmr", dict(DMR))),
            mock.patch.object(routes, "run_preflight", preflight),
            mock.patch.object(routes, "_halt_route", halt),
            mock.patch.object(routes, "ensure_runtime", lambda p, s, d: self.ensured.append((p, d)) or "started"),
            mock.patch.object(routes, "stop_rf_runtime", lambda: None),
            mock.patch.object(routes, "get_source_or_404", lambda source_id: {"id": source_id, "type": "direct_audio"}),
            mock.patch.object(routes, "start_source_pipeline",
                              lambda route, source: {"source_type": "direct_audio", "live_audio": {"running": True}}),
            mock.patch.object(routes, "get_route_or_404",
                              lambda route_id: dict(next(r for r in self.stored_routes if r["id"] == route_id))),
            mock.patch.object(routes, "load_store", lambda: {"routes": self.stored_routes}),
            mock.patch.object(routes, "save_store", lambda store: None),
            mock.patch.object(routes, "get_queue_status", lambda route_id: {}),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_start_takes_over_in_the_transmit_mode(self):
        self.assertTrue(routes.start_route_on_air("a")["started"])
        self.assertEqual(self.ensured, [("dmr", "sx")])
        # Route protocol follows the transmit mode, not what it was saved with.
        self.assertEqual(self.stored_routes[0]["protocol"], "dmr")

        self.halted.clear()
        self.assertTrue(routes.start_route_on_air("b")["started"])
        self.assertIn("a", self.halted)
        self.assertEqual(routes._on_air_route_ids(), ["b"])


if __name__ == "__main__":
    unittest.main()
