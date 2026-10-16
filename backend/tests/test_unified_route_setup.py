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

    @patch("app.routes.run_preflight")
    @patch("app.routes.update_route")
    @patch("app.routes.get_route_or_404")
    def test_explicit_start_enables_disabled_route(self, get_route, update, preflight):
        get_route.side_effect = [
            {"id": "route", "enabled": False},
            {"id": "route", "enabled": True},
        ]
        preflight.return_value = {"state": "blocked", "error": "no audio"}
        with (
            patch("app.routes.get_worker_status", return_value=None),
            patch("app.routes.get_processor_status", return_value=None),
            patch("app.routes.get_live_audio_status", return_value=None),
            patch("app.routes.get_queue_status", return_value={}),
        ):
            result = start_route("route")
        self.assertFalse(result["started"])
        self.assertEqual(update.call_args.args[1].enabled, True)
        preflight.assert_called_once()


if __name__ == "__main__":
    unittest.main()
