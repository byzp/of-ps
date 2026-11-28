"""Atomic redemption-code and invite-relation operations.

The existing ``player_kv`` and ``redeem_*`` tables are sufficient for the local
server.  Every state transition and its item grant shares one SQLite transaction;
a failed grant cannot consume a code or an invite reward.
"""

import hashlib
import json
import re
import time

import utils.db as db
from utils import item_mgr
from server.payment_security import audit, audit_best_effort

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{3,127}$")
_INVITE_NAMESPACE = "invite"
_MAX_REWARDS = 128
_MAX_REWARD_COUNT = 1_000_000


def normalize_code(code):
    if not isinstance(code, str):
        return ""
    code = code.strip()
    return code if _CODE_RE.fullmatch(code) else ""


def code_fingerprint(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def parse_rewards(rewards_str):
    if not isinstance(rewards_str, str) or not rewards_str or len(rewards_str) > 8192:
        raise ValueError("Invalid redemption reward configuration")
    merged = {}
    pairs = rewards_str.split(",")
    if len(pairs) > _MAX_REWARDS:
        raise ValueError("Too many redemption rewards")
    for pair in pairs:
        if pair.count(":") != 1:
            raise ValueError("Invalid redemption reward pair")
        item_raw, count_raw = pair.split(":", 1)
        item_raw, count_raw = item_raw.strip(), count_raw.strip()
        if not item_raw.isdigit() or not count_raw.isdigit():
            raise ValueError("Invalid redemption reward number")
        item_id, count = int(item_raw), int(count_raw)
        if not 0 < item_id <= 2**31 - 1 or not 0 < count <= _MAX_REWARD_COUNT:
            raise ValueError("Invalid redemption reward value")
        merged[item_id] = merged.get(item_id, 0) + count
        if merged[item_id] > _MAX_REWARD_COUNT:
            raise ValueError("Redemption reward count is too large")
    if not merged:
        raise ValueError("Redemption code has no rewards")
    return tuple(merged.items())


def validate_rewards(rewards):
    if not isinstance(rewards, (list, tuple)) or not rewards or len(rewards) > _MAX_REWARDS:
        raise ValueError("Invalid reward list")
    result = []
    for reward in rewards:
        if not isinstance(reward, (list, tuple)) or len(reward) != 2:
            raise ValueError("Invalid reward entry")
        item_id, count = reward
        if type(item_id) is not int or type(count) is not int:
            raise ValueError("Invalid reward number")
        if not 0 < item_id <= 2**31 - 1 or not 0 < count <= _MAX_REWARD_COUNT:
            raise ValueError("Invalid reward value")
        result.append((item_id, count))
    return tuple(result)


def redeem_code(player_id, code, rsp_rewards, pack_notice, now=None):
    """Return ``(status, rewards)``; status 0 means the grant committed.

    Statuses: 1 missing/type mismatch, 2 expired, 3 exhausted, 4 player already
    used it, 5 malformed code, 6 malformed server reward configuration.
    """
    normalized = normalize_code(code)
    if not normalized:
        audit_best_effort(player_id, "redeem_code", "invalid_code")
        return 5, ()
    current_time = int(time.time() if now is None else now)
    fingerprint = code_fingerprint(normalized)

    # Match item_mgr's lock-before-database order to avoid cross-handler deadlocks.
    with item_mgr.player_lock(player_id):
        with db.transaction():
            row = db.conn.execute(
                "SELECT code_type, rewards, max_uses, used, expire_time FROM redeem_codes WHERE code=?",
                (normalized,),
            ).fetchone()
            if row is None or row[0] != "redeem":
                audit(player_id, "redeem_code", "not_found", code_hash=fingerprint)
                return 1, ()
            _, rewards_str, max_uses, used, expire_time = row
            if type(max_uses) is not int or max_uses < 0 or type(used) is not int or used < 0:
                audit(player_id, "redeem_code", "invalid_config", code_hash=fingerprint)
                return 6, ()
            if type(expire_time) is not int or expire_time < 0:
                audit(player_id, "redeem_code", "invalid_config", code_hash=fingerprint)
                return 6, ()
            if expire_time and current_time >= expire_time:
                audit(player_id, "redeem_code", "expired", code_hash=fingerprint)
                return 2, ()
            if max_uses and used >= max_uses:
                audit(player_id, "redeem_code", "exhausted", code_hash=fingerprint)
                return 3, ()
            try:
                rewards = parse_rewards(rewards_str)
            except ValueError:
                audit(player_id, "redeem_code", "invalid_rewards", code_hash=fingerprint)
                return 6, ()

            prior = db.conn.execute(
                "SELECT 1 FROM redeem_code_uses WHERE code=? AND player_id=?",
                (normalized, player_id),
            ).fetchone()
            if prior is not None:
                audit(player_id, "redeem_code", "already_used", code_hash=fingerprint)
                return 4, ()

            cursor = db.conn.execute(
                """UPDATE redeem_codes SET used=used+1
                   WHERE code=? AND code_type='redeem'
                     AND (max_uses=0 OR used<max_uses)
                     AND (expire_time=0 OR expire_time>?)""",
                (normalized, current_time),
            )
            if cursor.rowcount != 1:
                cursor.close()
                audit(player_id, "redeem_code", "exhausted", code_hash=fingerprint)
                return 3, ()
            cursor.close()
            cursor = db.conn.execute(
                "INSERT INTO redeem_code_uses (code, player_id, use_time) VALUES (?, ?, ?)",
                (normalized, player_id, current_time),
            )
            cursor.close()
            # Any exception from the item layer rolls back both the use marker
            # and the global counter, allowing a safe retry.
            db.grant_rewards(player_id, rewards, rsp_rewards, pack_notice)
            audit(player_id, "redeem_code", "fulfilled", code_hash=fingerprint)
    return 0, rewards


def register_invite_code(code, owner_id):
    """Register an owner's reusable invite code (GM/admin integration helper)."""
    normalized = normalize_code(code)
    if not normalized or type(owner_id) is not int or owner_id <= 0:
        raise ValueError("Invalid invite code or owner")
    key = f"code:{normalized}"
    with db.transaction():
        if db.conn.execute("SELECT 1 FROM players WHERE player_id=?", (owner_id,)).fetchone() is None:
            raise ValueError("Invite owner does not exist")
        existing = db.get_kv(0, _INVITE_NAMESPACE, key)
        if existing is not None and int(existing) != owner_id:
            raise ValueError("Invite code already belongs to another player")
        db.set_kv(0, _INVITE_NAMESPACE, key, str(owner_id))
        audit(owner_id, "invite_code", "registered", code_hash=code_fingerprint(normalized))
    return normalized


def _load_invitees(owner_id):
    raw = db.get_kv(owner_id, _INVITE_NAMESPACE, "invitees")
    if raw is None:
        return []
    try:
        values = json.loads(bytes(raw).decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise ValueError("Corrupt invite relation state") from error
    if not isinstance(values, list) or any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("Corrupt invite relation state")
    if len(values) != len(set(values)):
        raise ValueError("Corrupt invite relation state")
    return values


def invite_count(owner_id):
    return len(_load_invitees(owner_id))


def _would_create_cycle(invitee_id, inviter_id):
    """An inviter may not already be reachable below the invitee."""
    pending = [invitee_id]
    visited = set()
    while pending:
        current = pending.pop()
        if current == inviter_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        if len(visited) > 10_000:
            raise ValueError("Invite relation graph is too large")
        pending.extend(_load_invitees(current))
    return False


def use_invite_code(player_id, code, rewards, rsp_rewards, pack_notice):
    """Bind one invitee to one inviter and grant the invitee reward atomically."""
    normalized = normalize_code(code)
    if not normalized:
        audit_best_effort(player_id, "invite_code_use", "invalid_code")
        return "invalid_code", 0
    try:
        rewards = validate_rewards(rewards)
    except ValueError:
        audit_best_effort(player_id, "invite_code_use", "invalid_rewards")
        return "invalid_rewards", 0
    fingerprint = code_fingerprint(normalized)

    with item_mgr.player_lock(player_id):
        with db.transaction():
            if db.get_kv(player_id, _INVITE_NAMESPACE, "inviter") is not None or db.get_kv(
                player_id, _INVITE_NAMESPACE, "used"
            ) is not None:
                audit(player_id, "invite_code_use", "already_filled", code_hash=fingerprint)
                return "already_filled", 0
            owner_raw = db.get_kv(0, _INVITE_NAMESPACE, f"code:{normalized}")
            if owner_raw is None:
                audit(player_id, "invite_code_use", "not_found", code_hash=fingerprint)
                return "not_found", 0
            try:
                owner_id = int(owner_raw)
            except (TypeError, ValueError) as error:
                raise ValueError("Corrupt invite owner mapping") from error
            if owner_id == player_id:
                audit(player_id, "invite_code_use", "self_invite", code_hash=fingerprint)
                return "self_invite", owner_id
            if db.conn.execute("SELECT 1 FROM players WHERE player_id=?", (owner_id,)).fetchone() is None:
                audit(player_id, "invite_code_use", "owner_missing", code_hash=fingerprint)
                return "not_found", 0
            if db.conn.execute("SELECT 1 FROM players WHERE player_id=?", (player_id,)).fetchone() is None:
                audit(player_id, "invite_code_use", "invitee_missing", code_hash=fingerprint)
                return "not_found", 0

            invitees = _load_invitees(owner_id)
            if player_id in invitees:
                audit(player_id, "invite_code_use", "already_filled", code_hash=fingerprint)
                return "already_filled", owner_id
            if _would_create_cycle(player_id, owner_id):
                audit(player_id, "invite_code_use", "cycle_rejected", code_hash=fingerprint)
                return "cycle", owner_id
            invitees.append(player_id)
            db.set_kv(owner_id, _INVITE_NAMESPACE, "invitees", json.dumps(invitees).encode("ascii"))
            db.set_kv(player_id, _INVITE_NAMESPACE, "inviter", str(owner_id))
            db.set_kv(player_id, _INVITE_NAMESPACE, "used", b"1")
            db.set_kv(0, _INVITE_NAMESPACE, f"relation:{player_id}", str(owner_id))
            db.grant_rewards(player_id, rewards, rsp_rewards, pack_notice)
            audit(
                owner_id, "invite_code_use", "fulfilled", invitee_id=player_id,
                code_hash=fingerprint, invitee_reward=True,
            )
    return "ok", owner_id


def claim_invite_reward(
    player_id, activity_id, condition_id, rewards, required_count,
    predecessor_id, rsp_rewards, pack_notice,
):
    """Claim an inviter reward using server-derived valid invitee count."""
    try:
        rewards = validate_rewards(rewards)
    except ValueError:
        return "invalid_rewards"
    if (
        type(required_count) is not int
        or not 1 <= required_count <= 1000
        or type(activity_id) is not int
        or activity_id <= 0
        or type(condition_id) is not int
        or condition_id <= 0
    ):
        return "invalid_request"

    with item_mgr.player_lock(player_id):
        with db.transaction():
            count = invite_count(player_id)
            if count < required_count:
                audit(
                    player_id, "invite_reward", "not_completed", activity_id=activity_id,
                    condition_id=condition_id, invitee_count=count, required_count=required_count,
                )
                return "not_completed"
            claim_key = f"{activity_id}:{condition_id}"
            if predecessor_id and not db.has_claimed(
                player_id, "activity_invite", f"{activity_id}:{predecessor_id}"
            ):
                audit(
                    player_id, "invite_reward", "predecessor_missing", activity_id=activity_id,
                    condition_id=condition_id,
                )
                return "not_completed"
            if not db.try_claim(player_id, "activity_invite", claim_key):
                audit(player_id, "invite_reward", "already_claimed", activity_id=activity_id, condition_id=condition_id)
                return "already_claimed"
            db.grant_rewards(player_id, rewards, rsp_rewards, pack_notice)
            audit(
                player_id, "invite_reward", "fulfilled", activity_id=activity_id,
                condition_id=condition_id, invitee_count=count,
            )
    return "ok"
