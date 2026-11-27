"""Payment callback and secondary-password security boundaries.

No payment provider is bundled.  ``CreatePayOrder`` therefore fails closed until a
provider adapter, an authenticated HTTP callback route and explicit price/secret
configuration are installed.  Order creation never grants items.
"""

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
from dataclasses import dataclass

from config import Config
import utils.db as db
import server.photo_share as photo_share

logger = logging.getLogger(__name__)

_PASSWORD_PREFIX = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 210_000
_MAX_PASSWORD_LENGTH = 128
_SP_NAMESPACE = "secondary_password"
_SP_KEY = "state"
_SP_MAX_FAILURES = 5
_SP_LOCK_SECONDS = 15 * 60
_SP_VERIFICATION_TTL_SECONDS = 5 * 60
_ORDER_NAMESPACE = "payment_orders"
_EVENT_NAMESPACE = "payment_events"
_TRADE_NAMESPACE = "payment_trades"
_ORDER_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_CALLBACK_MAX_BYTES = 64 * 1024
_CALLBACK_CLOCK_SKEW_SECONDS = 5 * 60


class SecurityError(RuntimeError):
    """Security state is unavailable or corrupt; callers must fail closed."""


class PaymentError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Product:
    shop_id: int
    grid_id: int
    pool_id: int
    goods_id: str
    rewards: tuple


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def audit(player_id, action, outcome, **details):
    """Append a tamper-evident-at-rest JSON audit event without secret material."""
    payload = {
        "time": int(time.time()),
        "player_id": int(player_id),
        "action": str(action),
        "outcome": str(outcome),
        "details": details,
    }
    key = f"{time.time_ns()}:{uuid.uuid4().hex}"
    db.set_kv(0, "security_audit", key, _json_bytes(payload))
    logger.info(
        "security_event action=%s player_id=%s outcome=%s details=%s",
        action,
        player_id,
        outcome,
        json.dumps(details, sort_keys=True, ensure_ascii=True),
    )


def audit_best_effort(player_id, action, outcome, **details):
    try:
        audit(player_id, action, outcome, **details)
    except Exception:
        # A rejected request must remain rejected even if audit storage is down.
        logger.exception("Could not persist security audit action=%s", action)


# ---------------- secondary password ----------------

def password_length():
    for entry in res_password_rows():
        if entry.get("key") == "SecondaryVerificationPasswordLength":
            try:
                length = int(entry["values"][0])
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise SecurityError("Invalid secondary-password length configuration") from error
            if not 6 <= length <= _MAX_PASSWORD_LENGTH:
                raise SecurityError("Secondary-password length must be between 6 and 128")
            return length
    return 6


def res_password_rows():
    from utils.res_loader import res

    rows = res.get("GlobalConfig", {}).get("config", {}).get("datas", ())
    return rows if isinstance(rows, (list, tuple)) else ()


def validate_password(password, required_length):
    if not isinstance(password, str) or len(password) != required_length:
        return False
    # Secondary passwords are printable ASCII; reject whitespace/control and
    # oversized protobuf strings before doing any expensive PBKDF2 work.
    return all(33 <= ord(char) <= 126 for char in password)


def hash_password(password):
    if not isinstance(password, str) or not 1 <= len(password) <= _MAX_PASSWORD_LENGTH:
        raise ValueError("Invalid secondary-password length")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), _PASSWORD_ITERATIONS
    ).hex()
    return f"{_PASSWORD_PREFIX}${_PASSWORD_ITERATIONS}${salt}${digest}"


def _parse_pbkdf2(stored):
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == _PASSWORD_PREFIX:
        _, iterations_raw, salt, expected = parts
        iterations = int(iterations_raw)
    elif len(parts) == 3 and parts[0] == _PASSWORD_PREFIX:
        # Version 1 written by the previous SPOperate handler.
        _, salt, expected = parts
        iterations = _PASSWORD_ITERATIONS
    else:
        raise ValueError("Unsupported password hash format")
    if not 100_000 <= iterations <= 2_000_000:
        raise ValueError("Invalid PBKDF2 iteration count")
    if not re.fullmatch(r"[0-9a-f]{32}", salt) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Invalid PBKDF2 parameters")
    return iterations, salt, expected


def verify_password(stored, password):
    if not isinstance(stored, str) or not isinstance(password, str):
        return False
    if len(password) > _MAX_PASSWORD_LENGTH:
        return False
    try:
        iterations, salt, expected = _parse_pbkdf2(stored)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), iterations
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        # Legacy snapshots may contain plaintext.  They are accepted only for a
        # successful migration and are never written back by this module.
        return hmac.compare_digest(stored, password)


def password_needs_upgrade(stored):
    try:
        parts = stored.split("$")
        return not (
            len(parts) == 4
            and parts[0] == _PASSWORD_PREFIX
            and int(parts[1]) == _PASSWORD_ITERATIONS
        )
    except (AttributeError, TypeError, ValueError):
        return True


def _empty_sp_state():
    return {
        "version": 2,
        "password_hash": "",
        "open": False,
        "failed_attempts": 0,
        "locked_until": 0.0,
        "updated_at": 0,
    }


def load_secondary_state(player_id):
    """Load state; caller holds photo_share.lock_sp when mutation is required."""
    if db.conn is None:
        raise SecurityError("Database is not initialized")
    raw = db.get_kv(player_id, _SP_NAMESPACE, _SP_KEY)
    if raw is not None:
        try:
            state = json.loads(bytes(raw).decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError) as error:
            raise SecurityError("Corrupt secondary-password state") from error
        if not isinstance(state, dict):
            raise SecurityError("Corrupt secondary-password state")
        result = _empty_sp_state()
        result.update(state)
        if (
            result["version"] != 2
            or not isinstance(result["password_hash"], str)
            or type(result["open"]) is not bool
            or type(result["failed_attempts"]) is not int
            or result["failed_attempts"] < 0
            or type(result["locked_until"]) not in (int, float)
        ):
            raise SecurityError("Corrupt secondary-password state")
        return result

    # One-time migration from the old whole-snapshot state.  The legacy value is
    # removed from the mirror after the first successful persistent write.
    legacy = photo_share.sp_state.get(player_id)
    if not legacy:
        return _empty_sp_state()
    state = _empty_sp_state()
    state["password_hash"] = str(legacy.get("password", ""))
    state["open"] = bool(legacy.get("open", False))
    return state


def save_secondary_state(player_id, state):
    if db.conn is None:
        raise SecurityError("Database is not initialized")
    state["version"] = 2
    state["updated_at"] = int(time.time())
    db.set_kv(player_id, _SP_NAMESPACE, _SP_KEY, _json_bytes(state))
    # Keep the old read model coherent for photo_share snapshots/other modules;
    # player_kv is the authoritative lockout and password store.
    photo_share.sp_state[player_id] = {
        "password": state["password_hash"],
        "open": state["open"],
    }


def state_fingerprint(state):
    return hashlib.sha256(state["password_hash"].encode("utf-8")).hexdigest()


def record_verification(session, player_id, password_hash):
    session._ofps_sp_verified = (
        int(player_id),
        time.monotonic(),
        state_fingerprint({"password_hash": password_hash}),
    )


def verification_is_current(session, state, now=None):
    marker = getattr(session, "_ofps_sp_verified", None)
    if not isinstance(marker, tuple) or len(marker) != 3:
        return False
    player_id, verified_at, fingerprint = marker
    current_time = time.monotonic() if now is None else now
    return bool(
        state["open"]
        and state["password_hash"]
        and player_id == getattr(session, "player_id", None)
        and 0 <= current_time - verified_at <= _SP_VERIFICATION_TTL_SECONDS
        and hmac.compare_digest(fingerprint, state_fingerprint(state))
    )


def _register_sp_failure(state, now):
    state["failed_attempts"] += 1
    if state["failed_attempts"] >= _SP_MAX_FAILURES:
        state["locked_until"] = now + _SP_LOCK_SECONDS
    player_id = state.pop("_player_id")
    save_secondary_state(player_id, state)


def secondary_password_operation(player_id, operate_type, password, old_password, now=None):
    """Perform one serialized, persistent SP operation.

    Returns ``(ok, reason, state, verified_hash)``.  ``verified_hash`` is set
    only after a successful check/change/open and is bound to the current session
    by the handler.
    """
    current_time = time.time() if now is None else float(now)
    with photo_share.lock_sp:
        with db.transaction():
            state = load_secondary_state(player_id)
            state["_player_id"] = player_id
            stored = state["password_hash"]
            verified_hash = ""

            if state["locked_until"] > current_time:
                state.pop("_player_id", None)
                return False, "locked", state, ""
            if state["locked_until"]:
                state["locked_until"] = 0.0
                state["failed_attempts"] = 0

            required_length = password_length()
            if operate_type == "open":
                if stored or state["open"]:
                    state.pop("_player_id", None)
                    return False, "already_open", state, ""
                if not validate_password(password, required_length):
                    _register_sp_failure(state, current_time)
                    state.pop("_player_id", None)
                    return False, "invalid_password", state, ""
                stored = hash_password(password)
                state["password_hash"] = stored
                state["open"] = True
                state["failed_attempts"] = 0
                verified_hash = stored
            elif operate_type in ("check", "change", "close"):
                if not stored:
                    state.pop("_player_id", None)
                    return False, "not_set", state, ""
                candidate = old_password if operate_type == "change" else password
                if not verify_password(stored, candidate):
                    _register_sp_failure(state, current_time)
                    state.pop("_player_id", None)
                    return False, "invalid_password", state, ""
                if password_needs_upgrade(stored) and operate_type != "change":
                    stored = hash_password(candidate)
                    state["password_hash"] = stored
                state["failed_attempts"] = 0
                state["locked_until"] = 0.0
                if operate_type == "check":
                    verified_hash = stored
                elif operate_type == "change":
                    if not validate_password(password, required_length):
                        state.pop("_player_id", None)
                        return False, "invalid_password", state, ""
                    stored = hash_password(password)
                    state["password_hash"] = stored
                    state["open"] = True
                    verified_hash = stored
                else:
                    state["password_hash"] = ""
                    state["open"] = False
            else:
                state.pop("_player_id", None)
                return False, "bad_request", state, ""

            save_secondary_state(player_id, state)
            state.pop("_player_id", None)
            return True, "ok", state, verified_hash


# ---------------- payment orders and callbacks ----------------

def callback_secret():
    secret = getattr(Config, "PAYMENT_CALLBACK_SECRET", "")
    if not isinstance(secret, str) or len(secret) < 32:
        raise PaymentError("unavailable", "Payment callback secret is not configured")
    return secret


def payment_is_enabled():
    """Explicit opt-in is required in addition to REJECT_PAYMENT=False."""
    if getattr(Config, "REJECT_PAYMENT", True):
        return False
    if getattr(Config, "PAYMENT_PROVIDER_ENABLED", False) is not True:
        return False
    try:
        callback_secret()
    except PaymentError:
        return False
    return True


def _positive_int(value, maximum):
    return type(value) is int and 0 < value <= maximum


def resolve_product(shop_id, grid_id, requested_pool_id, resources=None):
    if not _positive_int(shop_id, 2**32 - 1) or not _positive_int(grid_id, 2**32 - 1):
        raise PaymentError("bad_request", "Invalid shop or grid")
    if requested_pool_id and not _positive_int(requested_pool_id, 2**32 - 1):
        raise PaymentError("bad_request", "Invalid pool")
    if resources is None:
        from utils.res_loader import res

        resources = res
    try:
        shops = resources["Shop"]["grid"]["datas"]
        pools = resources["Shop"]["pool"]["datas"]
    except (KeyError, TypeError) as error:
        raise PaymentError("bad_request", "Shop configuration is missing") from error

    grid_row = next((row for row in shops if row.get("i_d") == shop_id), None)
    grid = next(
        (row for row in (grid_row or {}).get("items", ()) if row.get("grid_i_d") == grid_id),
        None,
    )
    if grid is None:
        raise PaymentError("bad_request", "Shop grid does not exist")
    pool_id = grid.get("shop_pool_i_d")
    if not _positive_int(pool_id, 2**32 - 1):
        raise PaymentError("bad_request", "Shop pool does not exist")
    if requested_pool_id and requested_pool_id != pool_id:
        raise PaymentError("bad_request", "Client pool does not match server configuration")
    goods_id = grid.get("goods_i_d")
    if not isinstance(goods_id, str) or not 1 <= len(goods_id) <= 128:
        raise PaymentError("bad_request", "Product is not payable")
    pool = next((row for row in pools if row.get("i_d") == pool_id), None)
    if pool is None:
        raise PaymentError("bad_request", "Shop pool does not exist")
    index = grid.get("index", 1)
    rewards = []
    for item in pool.get("items", ()):
        if item.get("index", 1) != index:
            continue
        item_id = item.get("item_i_d")
        count = item.get("item_num", 1)
        if not _positive_int(item_id, 2**31 - 1) or not _positive_int(count, 1_000_000):
            raise PaymentError("bad_request", "Invalid product reward")
        rewards.append((item_id, count))
    if not rewards:
        raise PaymentError("bad_request", "Product has no rewards")
    return Product(shop_id, grid_id, pool_id, goods_id, tuple(rewards))


def _order_signature_payload(order):
    keys = (
        "version", "order_id", "player_id", "to_player_id", "shop_id", "grid_id",
        "pool_id", "goods_id", "rewards", "amount_minor", "currency", "created_at",
        "expires_at", "status", "provider_trade_no", "event_id",
    )
    return _json_bytes({key: order[key] for key in keys})


def sign_order(order, secret):
    return hmac.new(secret.encode("utf-8"), _order_signature_payload(order), hashlib.sha256).hexdigest()


def verify_order(order, secret, now=None):
    if not isinstance(order, dict) or not isinstance(order.get("order_id"), str):
        raise PaymentError("bad_request", "Invalid order")
    if not _ORDER_ID_RE.fullmatch(order["order_id"]):
        raise PaymentError("bad_request", "Invalid order id")
    try:
        signature = order["signature"]
    except KeyError as error:
        raise PaymentError("bad_request", "Order signature is missing") from error
    expected = sign_order(order, secret)
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise PaymentError("invalid_signature", "Order signature mismatch")
    for field in ("player_id", "to_player_id", "shop_id", "grid_id", "pool_id"):
        if not _positive_int(order.get(field), 2**32 - 1):
            raise PaymentError("bad_request", "Invalid order identity")
    if order.get("version") != 1 or order.get("status") not in ("pending", "fulfilled"):
        raise PaymentError("bad_request", "Invalid order state")
    if not _positive_int(order.get("amount_minor"), 10_000_000):
        raise PaymentError("bad_request", "Invalid order amount")
    if order.get("currency") != "CNY" or not isinstance(order.get("goods_id"), str):
        raise PaymentError("bad_request", "Invalid order currency or product")
    rewards = order.get("rewards")
    if not isinstance(rewards, list) or not rewards:
        raise PaymentError("bad_request", "Invalid order rewards")
    for reward in rewards:
        if (
            not isinstance(reward, list)
            or len(reward) != 2
            or not _positive_int(reward[0], 2**31 - 1)
            or not _positive_int(reward[1], 1_000_000)
        ):
            raise PaymentError("bad_request", "Invalid order rewards")
    if type(order.get("created_at")) is not int or type(order.get("expires_at")) is not int:
        raise PaymentError("bad_request", "Invalid order timestamps")
    if now is not None and order["status"] == "pending" and float(now) > order["expires_at"]:
        raise PaymentError("expired", "Payment order has expired")
    return order


def create_payment_order(player_id, to_player_id, product, prices, secret, now=None):
    """Persist a signed pending order.  This function never grants rewards."""
    current_time = int(time.time() if now is None else now)
    if not _positive_int(player_id, 2**32 - 1) or not _positive_int(to_player_id, 2**32 - 1):
        raise PaymentError("bad_request", "Invalid payer or recipient")
    if not isinstance(secret, str) or len(secret) < 32:
        raise PaymentError("unavailable", "Payment callback secret is not configured")
    amount = prices.get(product.goods_id) if isinstance(prices, dict) else None
    if not _positive_int(amount, 10_000_000):
        raise PaymentError("unavailable", "Product has no server-side real-money price")
    ttl = getattr(Config, "PAYMENT_ORDER_TTL_SECONDS", 15 * 60)
    if type(ttl) is not int or not 60 <= ttl <= 24 * 60 * 60:
        raise PaymentError("unavailable", "Invalid payment order TTL")
    rate_seconds = getattr(Config, "PAYMENT_ORDER_MIN_INTERVAL_SECONDS", 1)
    if type(rate_seconds) is not int or not 0 <= rate_seconds <= 3600:
        raise PaymentError("unavailable", "Invalid payment order rate limit")

    with db.transaction():
        if db.conn.execute("SELECT 1 FROM players WHERE player_id=?", (player_id,)).fetchone() is None:
            raise PaymentError("bad_request", "Payer does not exist")
        if db.conn.execute("SELECT 1 FROM players WHERE player_id=?", (to_player_id,)).fetchone() is None:
            raise PaymentError("bad_request", "Recipient does not exist")
        last = db.get_kv(player_id, "payment_order_rate", "last", 0) or 0
        if current_time - int(last) < rate_seconds:
            raise PaymentError("rate_limited", "Payment orders are created too frequently")
        order = {
            "version": 1,
            "order_id": uuid.uuid4().hex,
            "player_id": player_id,
            "to_player_id": to_player_id,
            "shop_id": product.shop_id,
            "grid_id": product.grid_id,
            "pool_id": product.pool_id,
            "goods_id": product.goods_id,
            "rewards": [[item_id, count] for item_id, count in product.rewards],
            "amount_minor": amount,
            "currency": "CNY",
            "created_at": current_time,
            "expires_at": current_time + ttl,
            "status": "pending",
            "provider_trade_no": "",
            "event_id": "",
        }
        order["signature"] = sign_order(order, secret)
        verify_order(order, secret, current_time)
        db.set_kv(0, _ORDER_NAMESPACE, order["order_id"], _json_bytes(order))
        db.set_kv(player_id, "payment_order_rate", "last", current_time)
        audit(player_id, "payment_order", "created", order_id=order["order_id"], amount_minor=amount)
    return order


def verify_callback_request(raw_body, headers, secret, now=None):
    """Authenticate the exact HTTP body before JSON parsing or order lookup."""
    if not isinstance(raw_body, (bytes, bytearray)) or not raw_body:
        raise PaymentError("invalid_signature", "Callback body is missing")
    if len(raw_body) > _CALLBACK_MAX_BYTES:
        raise PaymentError("bad_request", "Callback body is too large")
    if not isinstance(secret, str) or len(secret) < 32:
        raise PaymentError("invalid_signature", "Payment callback secret is not configured")
    normalized = {str(key).lower(): value for key, value in headers.items()}
    timestamp_raw = normalized.get("x-payment-timestamp")
    signature = normalized.get("x-payment-signature")
    try:
        if isinstance(timestamp_raw, bool) or not str(timestamp_raw).isdigit():
            raise ValueError
        timestamp = int(timestamp_raw)
    except (TypeError, ValueError) as error:
        raise PaymentError("invalid_signature", "Callback timestamp is missing") from error
    current_time = int(time.time() if now is None else now)
    if abs(current_time - timestamp) > _CALLBACK_CLOCK_SKEW_SECONDS:
        raise PaymentError("invalid_signature", "Callback timestamp is stale")
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise PaymentError("invalid_signature", "Callback signature is missing")
    expected = hmac.new(
        secret.encode("utf-8"), str(timestamp).encode("ascii") + b"." + bytes(raw_body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PaymentError("invalid_signature", "Callback signature mismatch")
    return timestamp


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate callback JSON key")
        result[key] = value
    return result


def _validate_callback_payload(payload):
    if not isinstance(payload, dict):
        raise PaymentError("bad_request", "Callback JSON must be an object")
    for field in ("event_id", "order_id", "provider_trade_no"):
        value = payload.get(field)
        pattern = _ORDER_ID_RE if field == "order_id" else _PROVIDER_ID_RE
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise PaymentError("bad_request", f"Invalid callback {field}")
    if not _positive_int(payload.get("player_id"), 2**32 - 1):
        raise PaymentError("bad_request", "Invalid callback payer")
    if not _positive_int(payload.get("amount_minor"), 10_000_000):
        raise PaymentError("bad_request", "Invalid callback amount")
    if payload.get("currency") != "CNY" or payload.get("status") not in ("paid", "success"):
        raise PaymentError("bad_request", "Callback is not a successful CNY payment")
    if not isinstance(payload.get("goods_id"), str) or not 1 <= len(payload["goods_id"]) <= 128:
        raise PaymentError("bad_request", "Invalid callback product")
    return payload


def parse_callback(raw_body):
    try:
        payload = json.loads(bytes(raw_body).decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise PaymentError("bad_request", "Callback JSON is invalid") from error
    return _validate_callback_payload(payload)


def _load_order(order_id):
    raw = db.get_kv(0, _ORDER_NAMESPACE, order_id)
    if raw is None:
        raise PaymentError("order_not_found", "Payment order does not exist")
    try:
        order = json.loads(bytes(raw).decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise PaymentError("bad_request", "Stored payment order is corrupt") from error
    if not isinstance(order, dict):
        raise PaymentError("bad_request", "Stored payment order is corrupt")
    return order


def _load_event(event_id):
    raw = db.get_kv(0, _EVENT_NAMESPACE, event_id)
    if raw is None:
        return None
    try:
        event = json.loads(bytes(raw).decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise PaymentError("bad_request", "Stored payment event is corrupt") from error
    if not isinstance(event, dict) or not isinstance(event.get("order_id"), str):
        raise PaymentError("bad_request", "Stored payment event is corrupt")
    return event


def settle_payment_order(payload, secret, grant, now=None):
    """Validate callback business fields and atomically fulfill once.

    ``grant(player_id, rewards)`` runs inside the same SQLite transaction as the
    order/event transition.  Any exception rolls back the fulfillment marker, so
    a retry can safely complete the grant.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = parse_callback(payload)
    else:
        payload = _validate_callback_payload(payload)
    current_time = int(time.time() if now is None else now)
    order_id = payload["order_id"]
    event_id = payload["event_id"]
    trade_no = payload["provider_trade_no"]

    preliminary = verify_order(_load_order(order_id), secret)
    # Lock the stored recipient, never a recipient supplied by the callback.
    from utils import item_mgr

    with item_mgr.player_lock(preliminary["to_player_id"]):
        with db.transaction():
            # Replay detection deliberately precedes expiry validation: an exact
            # duplicate of an already-fulfilled callback remains idempotent.
            order = verify_order(_load_order(order_id), secret)
            event = _load_event(event_id)
            if event is not None:
                if event["order_id"] != order_id:
                    raise PaymentError("conflict", "Callback event belongs to another order")
                if (
                    order["status"] == "fulfilled"
                    and order.get("event_id") == event_id
                    and order.get("provider_trade_no") == trade_no
                ):
                    return False
                raise PaymentError("conflict", "Callback event was already processed")
            if order["status"] == "fulfilled":
                raise PaymentError("replay", "Payment order was already fulfilled")
            if order["expires_at"] < current_time:
                raise PaymentError("expired", "Payment order has expired")
            comparisons = (
                (payload["player_id"], order["player_id"], "uid_mismatch", "Callback payer mismatch"),
                (payload["amount_minor"], order["amount_minor"], "amount_mismatch", "Callback amount mismatch"),
                (payload["currency"], order["currency"], "amount_mismatch", "Callback currency mismatch"),
                (payload["goods_id"], order["goods_id"], "amount_mismatch", "Callback product mismatch"),
            )
            for actual, expected, code, message in comparisons:
                if actual != expected:
                    raise PaymentError(code, message)

            trade_raw = db.get_kv(0, _TRADE_NAMESPACE, trade_no)
            if trade_raw is not None:
                try:
                    trade_order_id = bytes(trade_raw).decode("ascii")
                except (TypeError, UnicodeDecodeError) as error:
                    raise PaymentError("bad_request", "Stored payment trade is corrupt") from error
                if trade_order_id != order_id:
                    raise PaymentError("conflict", "Provider trade belongs to another order")

            fulfilled = dict(order)
            fulfilled["status"] = "fulfilled"
            fulfilled["provider_trade_no"] = trade_no
            fulfilled["event_id"] = event_id
            fulfilled["fulfilled_at"] = current_time
            fulfilled["signature"] = sign_order(fulfilled, secret)
            verify_order(fulfilled, secret)
            # Compare-and-swap plus one SQLite writer makes concurrent duplicate
            # callbacks harmless; the transaction also covers the actual grant.
            cursor = db.conn.execute(
                "UPDATE player_kv SET v=? WHERE player_id=0 AND ns=? AND k=? AND v=?",
                (_json_bytes(fulfilled), _ORDER_NAMESPACE, order_id, _json_bytes(order)),
            )
            if cursor.rowcount != 1:
                cursor.close()
                raise PaymentError("replay", "Payment order was already fulfilled")
            cursor.close()
            db.set_kv(0, _EVENT_NAMESPACE, event_id, _json_bytes({"order_id": order_id, "time": current_time}))
            db.set_kv(0, _TRADE_NAMESPACE, trade_no, order_id.encode("ascii"))
            grant(order["to_player_id"], order["rewards"])
            audit(
                order["player_id"], "payment_callback", "fulfilled", order_id=order_id,
                event_id=event_id, amount_minor=order["amount_minor"],
            )
    return True
