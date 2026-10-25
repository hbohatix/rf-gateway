"""Single-step source + route setup regression tests (no network/RF)."""

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routes import RouteSetupRequest, setup_route, start_route


class UnifiedRouteSetupTests(unittest.TestCase):
    def _request(self, **kwargs):
        return RouteSetupRequest(
            device_id="soapy-0", protocol="p25", **kwargs
        )

    def test_requires_exactly_one_source(self):
        for payload in ({}, {"source_id": "old", "source_url": "https://x"}):
            with self.subTest(payload=payload):
                with self.assertRaises(HTTPException) as result:
                    setup_route(self._request(**payload))
                self.assertEqual(result.exception.status_code, 400)

    @patch("app.routes.create_route")
    @patch("app.routes.get_source_or_404")
    def test_reuses_existing_source_by_id(self, existing, create):
        existing.return_value = {
            "id": "source-id",
            "name": "Dispatch",
            "probe": {"page_name": "Dispatch"},
        }
        create.return_value = {"id": "route-id", "enabled": True}
        result = setup_route(self._request(source_id="source-id"))
        self.assertFalse(result["source_created"])
        self.assertFalse(result["start_requested"])
        self.assertIsNone(result["start"])
        self.assertEqual(create.call_args.args[0].source_id, "source-id")
        self.assertEqual(create.call_args.args[0].name, "Dispatch")

    @patch("app.routes.create_route")
    @patch("app.routes.create_source")
    @patch("app.routes.load_sources_store")
    @patch("app.routes.parse_broadcastify_source_url")
    def test_creates_source_from_url_only_once(self, parse, load, create_source, create):
        parse.return_value = {
            "source_type": "broadcastify_calls",
            "canonical_url": "https://www.broadcastify.com/calls/playlists/?uuid=example",
        }
        load.return_value = {"sources": []}
        create_source.return_value = {
            "id": "new-source",
            "name": "Calls",
            "probe": {"page_name": "System Dispatch"},
        }
        create.return_value = {"id": "new-route"}
        result = setup_route(self._request(source_url="https://example.com/input"))
        self.assertTrue(result["source_created"])
        self.assertEqual(result["route"]["id"], "new-route")
        self.assertEqual(create.call_args.args[0].name, "System Dispatch")
        create_source.assert_called_once()

    @patch("app.routes.create_route")
    @patch("app.routes.create_source")
    @patch("app.routes.load_sources_store")
    @patch("app.routes.parse_broadcastify_source_url")
    def test_deduplicates_same_canonical_url(self, parse, load, create_source, create):
        parse.return_value = {
            "source_type": "broadcastify_calls",
            "canonical_url": "https://www.broadcastify.com/calls/playlists/?uuid=old",
        }
        load.return_value = {"sources": [{
            "id": "old-source",
            "type": "broadcastify_calls",
            "url": "https://www.broadcastify.com/calls/playlists/?uuid=old",
            "name": "Existing",
        }]}
        create.return_value = {"id": "new-route"}
        result = setup_route(self._request(source_url="https://example.com/input"))
        self.assertFalse(result["source_created"])
        create_source.assert_not_called()
        self.assertEqual(create.call_args.args[0].source_id, "old-source")

    @patch("app.routes.start_route")
    @patch("app.routes.create_route")
    @patch("app.routes.get_source_or_404")
    def test_start_now_requires_explicit_flag(self, source, create, start):
        source.return_value = {"id": "saved-source", "name": "Saved"}
        create.return_value = {"id": "new-route"}
        setup_route(self._request(source_id="saved-source"))
        start.assert_not_called()
        start.return_value = {"started": False, "runtime": {"error": "No access"}}
        result = setup_route(self._request(source_id="saved-source", start_now=True))
        start.assert_called_once_with("new-route")
        self.assertFalse(result["start"]["started"])

    @patch("app.routes.stop_rf_runtime")
    @patch("app.routes.run_preflight")
    @patch("app.routes._sync_route_to_mode")
    @patch("app.routes.require_active_mode", return_value=("dmr", {"frequency_hz": 1}))
    @patch("app.routes.get_route_or_404")
    def test_explicit_start_enables_route_in_transmit_mode(self, get_route, mode, sync, preflight, stop_rf):
        get_route.return_value = {"id": "route", "enabled": False, "protocol": "p25"}
        sync.return_value = {"id": "route", "enabled": True, "protocol": "dmr", "device_id": "sx"}
        preflight.return_value = {"state": "blocked", "error": "no audio"}
        with (
            patch("app.routes._halt_route"),
            patch("app.routes.get_worker_status", return_value=None),
            patch("app.routes.get_processor_status", return_value=None),
            patch("app.routes.get_live_audio_status", return_value=None),
            patch("app.routes.get_queue_status", return_value={}),
        ):
            result = start_route("route")
        self.assertFalse(result["started"])
        self.assertEqual(sync.call_args.args[1], "dmr")
        preflight.assert_called_once_with(sync.return_value)
        stop_rf.assert_called_once()



class RouteEditingAndCleanupTests(unittest.TestCase):
    def _request(self, **kwargs):
        return RouteSetupRequest(
            device_id="soapy-0", protocol="p25", **kwargs
        )

    @patch("app.routes.update_route")
    @patch("app.routes.get_live_audio_status", return_value=None)
    @patch("app.routes.get_worker_status", return_value=None)
    @patch("app.routes.route_runtime_manager.get", return_value={"state": "stopped", "active": False})
    @patch("app.routes.get_source_or_404")
    @patch("app.routes.get_route_or_404")
    def test_edit_reuses_source_and_keeps_route_stopped(
        self, get_route, get_source, runtime, worker, live, update
    ):
        from app.routes import edit_route_setup

        get_route.return_value = {"id": "r", "name": "Old", "enabled": False}
        get_source.return_value = {"id": "s", "name": "Source"}
        update.return_value = {"id": "r", "name": "New"}
        result = edit_route_setup(
            "r", self._request(source_id="s", name="New")
        )
        self.assertFalse(result["start_requested"])
        self.assertEqual(update.call_args.args[1].enabled, None)
        self.assertEqual(update.call_args.args[1].source_id, "s")

    @patch("app.routes.get_route_or_404", return_value={"id": "r", "name": "R"})
    @patch("app.routes.route_runtime_manager.get", return_value={"active": True})
    def test_edit_running_route_blocked_before_source_change(self, runtime, get_route):
        from app.routes import edit_route_setup

        with self.assertRaises(HTTPException) as ctx:
            edit_route_setup(
                "r", self._request(source_url="https://example.org/media")
            )
        self.assertEqual(ctx.exception.status_code, 409)

    @patch("app.routes.get_route_or_404", return_value={"id": "r", "name": "R"})
    def test_edit_does_not_start_rf(self, get_route):
        from app.routes import edit_route_setup

        with self.assertRaises(HTTPException) as ctx:
            edit_route_setup(
                "r", self._request(source_id="s", start_now=True)
            )
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("app.routes.route_runtime_manager.remove")
    @patch("app.routes.call_queue_manager.remove_queue")
    @patch("app.routes.call_processor_manager.remove")
    @patch("app.routes.broadcastify_worker_manager.remove")
    @patch("app.routes.broadcastify_live_audio_pipeline_manager.remove")
    @patch("app.routes.delete_source")
    @patch("app.routes.save_store")
    @patch("app.routes.load_store")
    def test_delete_shared_source_keeps_source(
        self, load, save, delete_source, live, worker, processor, queue, runtime
    ):
        from app.routes import delete_route
        load.return_value = {"routes": [
            {"id": "a", "source_id": "shared"},
            {"id": "b", "source_id": "shared"},
        ]}
        result = delete_route("a", cleanup_source=True)
        self.assertTrue(result["source_shared"])
        self.assertFalse(result["source_deleted"])
        delete_source.assert_not_called()
        self.assertEqual(len(save.call_args.args[0]["routes"]), 1)

    @patch("app.routes.route_runtime_manager.remove")
    @patch("app.routes.call_queue_manager.remove_queue")
    @patch("app.routes.call_processor_manager.remove")
    @patch("app.routes.broadcastify_worker_manager.remove")
    @patch("app.routes.broadcastify_live_audio_pipeline_manager.remove")
    @patch("app.routes.delete_source")
    @patch("app.routes.save_store")
    @patch("app.routes.load_store")
    def test_delete_last_route_cleans_orphan(
        self, load, save, delete_source, live, worker, processor, queue, runtime
    ):
        from app.routes import delete_route
        load.return_value = {"routes": [{"id": "only", "source_id": "my-source"}]}
        result = delete_route("only", cleanup_source=True)
        self.assertTrue(result["source_deleted"])
        self.assertFalse(result["source_shared"])
        delete_source.assert_called_once_with("my-source")
        self.assertEqual(save.call_args.args[0]["routes"], [])

    @patch("app.routes.load_store", return_value={"routes": [
        {"id": "route", "source_id": "kept"}
    ]})
    def test_advanced_source_delete_rejects_in_use_source(self, load):
        from app.sources import delete_source
        with self.assertRaises(HTTPException) as ctx:
            delete_source("kept")
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
