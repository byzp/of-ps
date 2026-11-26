import hashlib
import hmac
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import CreatePayOrderReq, StatusCode
import handlers.CreatePayOrder as payment_handler
import server.payment_security as payment
import utils.db as db
import utils.res_loader as res_loader


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class PaymentSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        Config.DB_PATH = str(Path(self.tmp.name) / "player.db")
        Config.IN_MEMORY = False
        db.exit()
        db.init()
        for player_id in (1, 2, 3):
            db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(?,?)", (player_id, f"p{player_id}"))
        self.secret = "payment-test-secret-" + "x" * 32
        self.now = 2_000_000_000
        self.product = payment.Product(100, 1, 150, "goods.6", ((108, 60),))
        self.prices = {"goods.6": 600}
        self.interval = patch.object(Config, "PAYMENT_ORDER_MIN_INTERVAL_SECONDS", 0, create=True)
        self.interval.start()
        self.addCleanup(self.interval.stop)

    def tearDown(self):
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory

    def create_order(self, player_id=1, recipient=1, now=None):
        return payment.create_payment_order(
            player_id, recipient, self.product, self.prices, self.secret,
            self.now if now is None else now,
        )

    def payload(self, order, **changes):
        value = {
            "event_id": "event-1",
            "order_id": order["order_id"],
            "player_id": order["player_id"],
            "amount_minor": order["amount_minor"],
            "currency": order["currency"],
            "goods_id": order["goods_id"],
            "status": "paid",
            "provider_trade_no": "trade-1",
        }
        value.update(changes)
        return value

    def signed_body(self, payload, now=None):
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        timestamp = str(self.now if now is None else now)
        signature = hmac.new(
            self.secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest()
        return body, {"X-Payment-Timestamp": timestamp, "X-Payment-Signature": signature}

    def test_product_resolution_ignores_client_pool_and_unselected_items(self):
        resources = {"Shop": {
            "grid": {"datas": [{"i_d": 100, "items": [{
                "grid_i_d": 1, "index": 2, "shop_pool_i_d": 150, "goods_i_d": "goods.6",
            }]}]},
            "pool": {"datas": [{"i_d": 150, "items": [
                {"index": 1, "item_i_d": 999, "item_num": 999},
                {"index": 2, "item_i_d": 108, "item_num": 60},
            ]}]},
        }}
        product = payment.resolve_product(100, 1, 0, resources)
        self.assertEqual(product.rewards, ((108, 60),))
        with self.assertRaises(payment.PaymentError) as caught:
            payment.resolve_product(100, 1, 151, resources)
        self.assertEqual(caught.exception.code, "bad_request")

    def test_order_uses_server_price_identity_and_recipient(self):
        order = self.create_order(recipient=2)
        self.assertEqual(order["amount_minor"], 600)
        self.assertEqual(order["player_id"], 1)
        self.assertEqual(order["to_player_id"], 2)
        self.assertEqual(order["status"], "pending")
        payment.verify_order(order, self.secret, self.now)
        tampered = dict(order, amount_minor=1)
        with self.assertRaises(payment.PaymentError) as caught:
            payment.verify_order(tampered, self.secret, self.now)
        self.assertEqual(caught.exception.code, "invalid_signature")

    def test_callback_signature_covers_raw_body_and_rejects_stale_or_wrong_secret(self):
        order = self.create_order()
        body, headers = self.signed_body(self.payload(order))
        payment.verify_callback_request(body, headers, self.secret, self.now)
        tampered = body.replace(b'"amount_minor":600', b'"amount_minor":1')
        with self.assertRaises(payment.PaymentError) as caught:
            payment.verify_callback_request(tampered, headers, self.secret, self.now)
        self.assertEqual(caught.exception.code, "invalid_signature")
        with self.assertRaises(payment.PaymentError):
            payment.verify_callback_request(body, headers, self.secret, self.now + 301)
        with self.assertRaises(payment.PaymentError):
            payment.verify_callback_request(body, headers, "z" * 32, self.now)

    def test_callback_rejects_amount_uid_and_product_forgery(self):
        order = self.create_order()
        grants = []
        cases = (
            ({"amount_minor": 1}, "amount_mismatch"),
            ({"player_id": 2}, "uid_mismatch"),
            ({"goods_id": "goods.648"}, "amount_mismatch"),
        )
        for changes, expected_code in cases:
            body, headers = self.signed_body(self.payload(order, **changes))
            payment.verify_callback_request(body, headers, self.secret, self.now)
            with self.assertRaises(payment.PaymentError) as caught:
                payment.settle_payment_order(
                    payment.parse_callback(body), self.secret,
                    lambda *args: grants.append(args), self.now,
                )
            self.assertEqual(caught.exception.code, expected_code)
        self.assertEqual(grants, [])

    def test_valid_callback_grants_stored_recipient_once_and_replay_is_noop(self):
        order = self.create_order(recipient=2)
        grants = []
        payload = self.payload(order, event_id="event-1", provider_trade_no="trade-1", to_player_id=3)
        self.assertTrue(payment.settle_payment_order(
            payload, self.secret, lambda *args: grants.append(args), self.now
        ))
        self.assertFalse(payment.settle_payment_order(
            payload, self.secret, lambda *args: grants.append(args), self.now
        ))
        self.assertEqual(grants, [(2, [[108, 60]])])
        stored = json.loads(bytes(db.get_kv(0, "payment_orders", order["order_id"])).decode())
        self.assertEqual(stored["status"], "fulfilled")
        payment.verify_order(stored, self.secret)

    def test_provider_trade_cannot_be_reused_for_another_order(self):
        first = self.create_order()
        second = self.create_order()
        grants = []
        self.assertTrue(payment.settle_payment_order(
            self.payload(first, event_id="event-1", provider_trade_no="same-trade"),
            self.secret, lambda *args: grants.append(args), self.now,
        ))
        with self.assertRaises(payment.PaymentError) as caught:
            payment.settle_payment_order(
                self.payload(second, event_id="event-2", provider_trade_no="same-trade"),
                self.secret, lambda *args: grants.append(args), self.now,
            )
        self.assertEqual(caught.exception.code, "conflict")
        self.assertEqual(len(grants), 1)

    def test_grant_failure_rolls_back_order_event_and_trade_markers(self):
        order = self.create_order()
        payload = self.payload(order)
        with self.assertRaisesRegex(RuntimeError, "synthetic grant failure"):
            payment.settle_payment_order(
                payload, self.secret, lambda *_: (_ for _ in ()).throw(RuntimeError("synthetic grant failure")), self.now
            )
        stored = json.loads(bytes(db.get_kv(0, "payment_orders", order["order_id"])).decode())
        self.assertEqual(stored["status"], "pending")
        self.assertIsNone(db.get_kv(0, "payment_events", "event-1"))
        self.assertIsNone(db.get_kv(0, "payment_trades", "trade-1"))
        grants = []
        self.assertTrue(payment.settle_payment_order(
            payload, self.secret, lambda *args: grants.append(args), self.now
        ))
        self.assertEqual(len(grants), 1)

    def test_concurrent_duplicate_callbacks_fulfill_once(self):
        order = self.create_order()
        payload = self.payload(order)
        barrier = threading.Barrier(4)
        grants = []

        def worker(_):
            barrier.wait()
            return payment.settle_payment_order(
                payload, self.secret, lambda *args: grants.append(args), self.now
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(worker, range(4)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 3)
        self.assertEqual(len(grants), 1)

    def test_expired_pending_order_rejected_but_fulfilled_replay_remains_idempotent(self):
        fulfilled = self.create_order()
        pending = self.create_order()
        grants = []
        self.assertTrue(payment.settle_payment_order(
            self.payload(fulfilled), self.secret, lambda *args: grants.append(args), self.now
        ))
        later = self.now + 901
        with self.assertRaises(payment.PaymentError) as caught:
            payment.settle_payment_order(
                self.payload(pending, event_id="event-2", provider_trade_no="trade-2"),
                self.secret, lambda *args: grants.append(args), later,
            )
        self.assertEqual(caught.exception.code, "expired")
        self.assertFalse(payment.settle_payment_order(
            self.payload(fulfilled), self.secret, lambda *args: grants.append(args), later
        ))
        self.assertEqual(len(grants), 1)

    def test_missing_server_price_or_secret_fails_closed(self):
        with self.assertRaises(payment.PaymentError) as caught:
            payment.create_payment_order(1, 1, self.product, {}, self.secret, self.now)
        self.assertEqual(caught.exception.code, "unavailable")
        with self.assertRaises(payment.PaymentError):
            payment.create_payment_order(1, 1, self.product, self.prices, "short", self.now)

    def test_handler_default_denial_and_pending_order_never_grant(self):
        session = FakeSession()
        request = CreatePayOrderReq(shop_id=100, grid_id=1, pool_id=150, to_player_id=2)
        with patch.object(Config, "REJECT_PAYMENT", False), \
             patch.object(Config, "PAYMENT_PROVIDER_ENABLED", False, create=True), \
             patch("utils.item_mgr.grant_single_item") as grant:
            payment_handler.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_Not_Payment)
        self.assertEqual(session.sent[0][1].result_str, "payment unavailable")
        grant.assert_not_called()

        resources = {"Shop": {
            "grid": {"datas": [{"i_d": 100, "items": [{
                "grid_i_d": 1, "index": 1, "shop_pool_i_d": 150, "goods_i_d": "goods.6",
            }]}]},
            "pool": {"datas": [{"i_d": 150, "items": [{"index": 1, "item_i_d": 108, "item_num": 60}]}]},
        }}
        session = FakeSession()
        with patch.object(Config, "REJECT_PAYMENT", False), \
             patch.object(Config, "PAYMENT_PROVIDER_ENABLED", True, create=True), \
             patch.object(Config, "PAYMENT_CALLBACK_SECRET", self.secret, create=True), \
             patch.object(Config, "PAYMENT_PRICES", self.prices, create=True), \
             patch.dict(res_loader.res, resources, clear=True), \
             patch("utils.item_mgr.grant_single_item") as grant:
            payment_handler.Handler().handle(session, request.SerializeToString(), 2)
        self.assertEqual(session.sent[0][0], MsgId.CreatePayOrderRsp)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_OK)
        self.assertEqual(session.sent[0][1].result_str, "pending")
        self.assertEqual(len(session.sent), 1)
        grant.assert_not_called()
        order = json.loads(bytes(db.get_kv(0, "payment_orders", session.sent[0][1].order_id)).decode())
        self.assertEqual(order["to_player_id"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
