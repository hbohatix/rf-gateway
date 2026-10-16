"""Tests for Calls playlist/group selection without network access or RF."""

import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.broadcastify_worker import BroadcastifyWorker
from app.call_queue import CallQueueManager
from app.routes import RouteSetupRequest, resolve_setup_source
from app.sources import normalize_calls_selection, register_calls_selection


class CallsSelectorTests(unittest.TestCase):
    def test_playlist_uuid_is_canonical(self):
        s = normalize_calls_selection(
            playlist_uuid="abcd1234-1111-2222-3333-444444444444"
        )
        self.assertEqual(s["playlist_uuid"], "abcd1234-1111-2222-3333-444444444444")
        self.assertTrue(s["canonical_url"].startswith("https://www.broadcastify.com/"))

    def test_groups_validate_and_sort(self):
        s = normalize_calls_selection(group_ids=["c-223312", "2-3416"])
        self.assertEqual(s["group_ids"], ["2-3416", "c-223312"])
        for bad in (["26021"], ["a-b"], ["2-3416"] * 2, ["2-1"] * 6):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_calls_selection(group_ids=bad)

    @patch("app.sources.save_store")
    @patch("app.sources.get_audio_api_status", return_value={"live_playback_configured": True})
    @patch("app.sources.load_store")
    def test_registration_is_deduplicated(self, load, config, save):
        store = {"version": 1, "sources": []}
        load.return_value = store
        one, created = register_calls_selection(group_ids=["2-3416"], name="Dispatch")
        self.assertTrue(created)
        self.assertEqual(one["group_ids"], ["2-3416"])
        self.assertEqual(len(store["sources"]), 1)
        two, created = register_calls_selection(group_ids=["2-3416"])
        self.assertFalse(created)
        self.assertEqual(one["id"], two["id"])
        save.assert_called_once()

    @patch("app.routes.register_calls_selection")
    def test_setup_chooses_groups_without_url(self, register):
        register.return_value = ({"id": "source"}, True)
        req = RouteSetupRequest(
            device_id="soapy-0", protocol="p25", group_ids=["c-223312"]
        )
        self.assertTrue(resolve_setup_source(req)[1])
        register.assert_called_once()
        with self.assertRaises(HTTPException):
            resolve_setup_source(RouteSetupRequest(
                device_id="soapy-0", protocol="p25",
                source_id="saved", group_ids=["c-223312"]
            ))

    def test_worker_uses_authenticated_group_selector(self):
        client = Mock()
        client.get_live_calls.return_value = {"calls": [], "lastPos": 123}
        source = {
            "id": "s", "type": "broadcastify_calls",
            "provider": "broadcastify",
            "group_ids": ["2-3416", "c-223312"],
        }
        worker = BroadcastifyWorker(
            route_id="group-select-test",
            source=source,
            client=client,
            queue_manager=CallQueueManager(),
        )
        with (
            patch.object(worker, "_poll_configuration_ready", return_value=True),
            patch.object(worker, "_prepare_poll_cursor", return_value=100),
        ):
            result = worker.poll_once()
        self.assertFalse(result["poll"]["suspended"])
        kwargs = client.get_live_calls.call_args.kwargs
        self.assertIsNone(kwargs["playlist_uuid"])
        self.assertEqual(kwargs["group_id"], "2-3416,c-223312")
        self.assertEqual(kwargs["extra_query"]["pos"], 100)


if __name__ == "__main__":
    unittest.main()
