"""Regression tests for licensed BCFY Calls developer auth (no live requests)."""

import base64
import json
import unittest
from unittest.mock import patch

from app.broadcastify_calls_client import (
    BroadcastifyCallsClient,
    BroadcastifyCallsConfig,
    BroadcastifyCallsConfigurationError,
    DEFAULT_LIVE_CALLS_URL,
)
from app.broadcastify_worker import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
)


def client(endpoint=DEFAULT_LIVE_CALLS_URL):
    return BroadcastifyCallsClient(
        BroadcastifyCallsConfig(
            base_url="https://api.bcfy.io",
            key_id="test-kid",
            signing_secret="not-a-real-secret",
            issuer="test-application-iss",
            live_calls_path=endpoint,
        )
    )


class DeveloperCallsAuthTests(unittest.TestCase):
    def test_default_uses_developer_api_not_web_ajax(self):
        self.assertEqual(
            DEFAULT_LIVE_CALLS_URL, "https://api.bcfy.io/calls/v1/live/"
        )

    def test_jwt_claims_signed_with_app_identity(self):
        token = client().mint_jwt(now=1000)
        head, payload, sig = token.split(".")
        decode = lambda value: json.loads(
            base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        )
        self.assertEqual(decode(head)["kid"], "test-kid")
        self.assertEqual(decode(head)["alg"], "HS256")
        self.assertEqual(decode(payload)["iss"], "test-application-iss")
        self.assertEqual(decode(payload)["iat"], 1000)
        self.assertTrue(sig)

    def test_playlist_uses_get_and_cursor(self):
        c = client()
        with patch.object(c, "_request_json", return_value={
            "calls": [], "lastPos": 1234
        }) as request:
            result = c.get_live_calls(
                playlist_uuid="example-uuid",
                extra_query={
                    "pos": 1230,
                    "doInit": 1,
                    "sid": 0,
                    "sessionKey": "legacy",
                    "systemId": 0,
                },
            )
        self.assertEqual(result["lastPos"], 1234)
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["method"], "GET")
        self.assertEqual(kwargs["path"], DEFAULT_LIVE_CALLS_URL)
        self.assertEqual(kwargs["query"], {
            "playlist_uuid": "example-uuid",
            "pos": 1230,
        })

    def test_group_uses_expected_selector_and_init(self):
        c = client()
        with patch.object(c, "_request_json", return_value={"calls":[]}) as request:
            c.get_live_calls(group_id="123", extra_query={"pos": 123, "doInit": 1})
        self.assertEqual(request.call_args.kwargs["query"], {
            "groups": "123", "pos": 123, "init": 1,
        })

    def test_mismatched_selectors_rejected(self):
        c = client()
        with self.assertRaises(ValueError):
            c.get_live_calls(playlist_uuid="a", group_id="b")

    def test_website_endpoint_rejected_before_jwt_disclosure(self):
        c = client("https://www.broadcastify.com/calls/apis/live-calls")
        with patch.object(c, "_request_json") as request:
            with self.assertRaises(BroadcastifyCallsConfigurationError):
                c.get_live_calls(playlist_uuid="something")
        request.assert_not_called()

    def test_polling_uses_five_second_minimum(self):
        self.assertGreaterEqual(MIN_POLL_INTERVAL_SECONDS, 5.0)
        self.assertGreaterEqual(DEFAULT_POLL_INTERVAL_SECONDS, 5.0)


if __name__ == "__main__":
    unittest.main()
