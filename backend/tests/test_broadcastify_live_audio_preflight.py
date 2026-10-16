"""Regression tests for Broadcastify Live Audio session validation."""

import unittest
from unittest.mock import patch

from app.broadcastify_live_audio_client import (
    BroadcastifyLiveAudioAuthenticationError,
    BroadcastifyLiveAudioClient,
    BroadcastifyLiveAudioError,
)
from app.route_runtime import RouteRuntimeManager


class BroadcastifySessionTests(unittest.TestCase):
    def setUp(self):
        # Session parsing does not execute curl; no network is needed.
        self.client = BroadcastifyLiveAudioClient(curl_path="curl")

    def test_login_page_reports_authentication_required(self):
        page = "<html><body>Sign In | Create Account</body></html>"
        with patch.object(self.client, "fetch_feed_page", return_value=page):
            with self.assertRaises(
                BroadcastifyLiveAudioAuthenticationError
            ) as ctx:
                self.client.resolve_session(32602)
        self.assertIn("requires sign-in", str(ctx.exception))

    def test_changed_player_markup_has_actionable_message(self):
        page = "<html><body>Live Audio</body></html>"
        with patch.object(self.client, "fetch_feed_page", return_value=page):
            with self.assertRaises(BroadcastifyLiveAudioError) as ctx:
                self.client.resolve_session(32602)
        self.assertIn("player format changed", str(ctx.exception))

    def test_valid_session_still_parses(self):
        page = (
            'var player = {feedId: 32602, '
            'hlsUrl: "https://hls.example.com/live.m3u8", '
            'sessionId: "abc", '
            'beaconUrl: "https://www.example.com/beacon"};'
        )
        with patch.object(self.client, "fetch_feed_page", return_value=page):
            session = self.client.resolve_session(32602)
        self.assertEqual(session.feed_id, 32602)
        self.assertEqual(session.session_id, "abc")
        self.assertIn("s=abc", session.signed_hls_url)


class RoutePreflightTests(unittest.TestCase):
    def test_unavailable_live_audio_blocks_route_with_error(self):
        runtime = RouteRuntimeManager()
        result = runtime.preflight(
            route={
                "id": "test-route",
                "source_id": "source",
                "device_id": "soapy-0",
                "protocol": "p25",
                "enabled": True,
            },
            source={
                "probe": {
                    "reachable": True,
                    "audio_api_configured": False,
                    "playback_error": "Broadcastify requires sign-in",
                }
            },
            device={"available": True, "probe_ok": True},
            mode_config={"protocol": "p25"},
        )
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["blocked_reason"], "source_stream_unavailable")
        self.assertEqual(result["error"], "Broadcastify requires sign-in")
        self.assertFalse(result["source_ready"])

    def test_live_route_rechecks_session_before_ready(self):
        from app.routes import run_preflight

        route = {
            "id": "test-route",
            "source_id": "source",
            "device_id": "soapy-0",
            "protocol": "p25",
            "enabled": True,
        }
        source = {
            "type": "broadcastify_live_audio",
            "feed_id": 32602,
            "probe": {
                "reachable": True,
                "audio_api_configured": True,
            },
        }
        with (
            patch("app.routes.get_source_or_404", return_value=source),
            patch("app.routes.get_device_or_404", return_value={}),
            patch("app.routes.get_protocol_config", return_value={}),
            patch(
                "app.routes.broadcastify_live_audio_client.resolve_session",
                side_effect=BroadcastifyLiveAudioAuthenticationError(
                    "Broadcastify requires sign-in"
                ),
            ) as resolve,
            patch("app.routes.route_runtime_manager.preflight") as preflight,
        ):
            run_preflight(route)

        resolve.assert_called_once_with(32602)
        submitted = preflight.call_args.kwargs["source"]["probe"]
        self.assertFalse(submitted["audio_api_configured"])
        self.assertEqual(submitted["playback_state"], "stream_unavailable")
        self.assertIn("sign-in", submitted["playback_error"])


if __name__ == "__main__":
    unittest.main()
