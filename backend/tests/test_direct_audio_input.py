"""Direct audio regression tests (no network or transmitter required)."""

from email.message import Message
from unittest import TestCase
from unittest.mock import patch

from app.broadcastify_live_audio_pipeline import BroadcastifyLiveAudioPipeline
from app.direct_audio_client import (
    DirectAudioClient,
    DirectAudioStream,
    validate_direct_audio_url,
)
from app.sources import probe_direct_audio


class DirectAudioTests(TestCase):
    def test_accepts_user_owned_local_stream(self):
        self.assertEqual(
            validate_direct_audio_url("http://127.0.0.1:8000/live.mp3"),
            "http://127.0.0.1:8000/live.mp3",
        )

    def test_rejects_provider_bypass_and_non_http_inputs(self):
        invalid_urls = (
            "https://www.broadcastify.com/listen/feed/32602",
            "https://sub.broadcastify.com/stream.m3u8",
            "https://bcfy.io/stream",
            "file:///etc/passwd",
            "http://user:pass@localhost:8080/live",
            "ftp://localhost/audio.mp3",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_direct_audio_url(url)

    def test_probe_audio_http_response(self):
        class Response:
            status = 200
            headers = Message()
            headers["Content-Type"] = "audio/mpeg"

            def geturl(self):
                return "http://127.0.0.1:8000/live.mp3"

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        with (
            patch("app.sources.urllib.request.urlopen", return_value=Response()),
            patch("app.sources.shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            result = probe_direct_audio("http://127.0.0.1:8000/live.mp3")
        self.assertTrue(result["reachable"])
        self.assertEqual(result["source_type"], "direct_audio")
        self.assertTrue(result["audio_api_configured"])

    def test_html_page_does_not_count_as_audio(self):
        class Response:
            status = 200
            headers = Message()
            headers["Content-Type"] = "text/html"

            def geturl(self):
                return "http://127.0.0.1:8000/"

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        with patch("app.sources.urllib.request.urlopen", return_value=Response()):
            result = probe_direct_audio("http://127.0.0.1:8000/")
        self.assertFalse(result["reachable"])

    def test_pipeline_reuses_p25_live_audio(self):
        source = {
            "type": "direct_audio",
            "provider": "direct",
            "url": "http://localhost:8000/live.mp3",
            "id": "source-id",
        }
        pipeline = BroadcastifyLiveAudioPipeline(
            route_id="test-route",
            source=source,
            protocol="p25",
        )
        self.assertIsInstance(pipeline.client, DirectAudioClient)
        self.assertEqual(
            pipeline._validate_source(), source["url"]
        )

    def test_pcm_output_chunks_have_expected_frame_length(self):
        stream = DirectAudioStream("http://localhost:8000/live.mp3", "ffmpeg")
        self.assertFalse(stream.running)
        self.assertEqual(stream.read_chunk(0.01), b"")
        self.assertEqual(stream.status()["chunk_bytes"], 320)


if __name__ == "__main__":
    import unittest
    unittest.main()
