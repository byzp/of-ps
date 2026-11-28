import threading
import unittest
from types import SimpleNamespace

from proto.net_pb2 import (
    PopEmojiReq,
    SendActionReq,
    SendChatMsgReq,
    StatusCode,
)
from server import shared_projection
from utils.metrics import metrics
from utils.rate_limit import SessionRateLimiter, TokenBucket


class TokenBucketTests(unittest.TestCase):
    def setUp(self):
        metrics.reset()
        self.now = [100.0]
        self.bucket = TokenBucket(2.0, 2, clock=lambda: self.now[0])

    def tearDown(self):
        metrics.reset()

    def test_burst_is_available_immediately(self):
        self.assertTrue(self.bucket.consume())
        self.assertTrue(self.bucket.consume())
        self.assertFalse(self.bucket.consume())

    def test_tokens_refill_over_time(self):
        self.assertTrue(self.bucket.consume())
        self.assertTrue(self.bucket.consume())
        self.assertFalse(self.bucket.consume())
        self.now[0] += 0.5
        self.assertTrue(self.bucket.consume())
        self.assertFalse(self.bucket.consume())

    def test_concurrent_consumers_cannot_exceed_burst(self):
        bucket = TokenBucket(0.0001, 10, clock=lambda: 100.0)
        results = []
        lock = threading.Lock()

        def consume():
            allowed = bucket.consume()
            with lock:
                results.append(allowed)

        threads = [threading.Thread(target=consume) for _ in range(50)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(results), 10)

    def test_invalid_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            TokenBucket(0, 1)
        with self.assertRaises(ValueError):
            TokenBucket(1, 0)
        with self.assertRaises(ValueError):
            self.bucket.consume(0)


class SocialRateLimitHandlerTests(unittest.TestCase):
    def setUp(self):
        metrics.reset()
        shared_projection.store.clear()
        self.now = [100.0]
        self.limiter = SessionRateLimiter(
            {"chat": (0.01, 1), "action": (0.01, 1), "emoji": (0.01, 1)},
            clock=lambda: self.now[0],
        )
        self.responses = []
        self.session = SimpleNamespace(
            rate_limiter=self.limiter,
            send=lambda msg_id, message, packet_id: self.responses.append(
                (msg_id, message, packet_id)
            ),
        )

    def tearDown(self):
        metrics.reset()
        shared_projection.store.clear()

    def exhaust(self, bucket):
        self.assertTrue(self.limiter.allow(bucket))

    def test_chat_rejection_uses_protocol_status(self):
        from handlers.SendChatMsg import Handler

        self.exhaust("chat")
        Handler().handle(
            self.session,
            SendChatMsgReq(text="spam").SerializeToString(),
            7,
        )
        msg_id, response, packet_id = self.responses[-1]
        self.assertEqual(response.status, StatusCode.StatusCode_REQUESTS_TOO_FREQUENT)
        self.assertEqual(packet_id, 7)
        self.assertEqual(
            metrics.snapshot()["counters"]["ofps.rate_limit.chat_rejections_total"],
            1,
        )

    def test_action_rejection_uses_protocol_status(self):
        from handlers.SendAction import Handler

        self.exhaust("action")
        Handler().handle(
            self.session,
            SendActionReq(action_id=1).SerializeToString(),
            8,
        )
        _, response, packet_id = self.responses[-1]
        self.assertEqual(response.status, StatusCode.StatusCode_REQUESTS_TOO_FREQUENT)
        self.assertEqual(packet_id, 8)

    def test_emoji_rejection_uses_protocol_status(self):
        from handlers.PopEmoji import Handler

        self.exhaust("emoji")
        Handler().handle(
            self.session,
            PopEmojiReq(emoji_id=1).SerializeToString(),
            9,
        )
        _, response, packet_id = self.responses[-1]
        self.assertEqual(response.status, StatusCode.StatusCode_REQUESTS_TOO_FREQUENT)
        self.assertEqual(packet_id, 9)


if __name__ == "__main__":
    unittest.main()
