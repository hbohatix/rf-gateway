"""Queue accounting regression tests for live Calls telemetry."""

import unittest

from app.call_queue import RouteCallQueue


class QueueAccountingTests(unittest.TestCase):
    def test_completed_and_cleared_calls_are_distinguishable(self):
        queue = RouteCallQueue("route")
        for ts in (100, 101, 102):
            self.assertTrue(queue.enqueue({"groupId": "20", "ts": ts})["accepted"])

        self.assertIsNotNone(queue.pop_next())
        cleared = queue.clear(clear_seen=False)
        self.assertEqual(cleared["removed"], 2)
        self.assertEqual(cleared["total_cleared"], 2)

        stats = queue.stats()
        self.assertEqual(stats["total_enqueued"], 3)
        self.assertEqual(stats["total_dequeued"], 1)
        self.assertEqual(stats["total_cleared"], 2)
        self.assertEqual(stats["total_dropped"], 0)
        self.assertEqual(stats["queue_size"], 0)

    def test_queue_overflow_is_not_counted_as_clear(self):
        queue = RouteCallQueue("route", max_queue_size=1)
        queue.enqueue({"groupId": "20", "ts": 100})
        queue.enqueue({"groupId": "20", "ts": 101})
        before = queue.stats()
        self.assertEqual(before["total_dropped"], 1)
        self.assertEqual(before["total_cleared"], 0)
        self.assertEqual(before["queue_size"], 1)

        queue.clear()
        after = queue.stats()
        self.assertEqual(after["total_cleared"], 1)
        self.assertEqual(after["total_dropped"], 1)
        self.assertEqual(after["queue_size"], 0)

    def test_empty_clear_does_not_change_counter(self):
        queue = RouteCallQueue("route")
        queue.clear()
        queue.clear()
        self.assertEqual(queue.stats()["total_cleared"], 0)


if __name__ == "__main__":
    unittest.main()
