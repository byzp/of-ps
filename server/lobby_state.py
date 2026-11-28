"""Lobby snapshot persistence and host lease primitives."""

import base64
import json
import math
import os
import time
import uuid
from threading import Lock

from google.protobuf.message import DecodeError
from proto.net_pb2 import PlayerRecorderData
from server import shared_projection
from server.scene_data import export_scene_snapshots, import_scene_snapshots

STATE_VERSION = 1


class LobbyStateError(ValueError):
    pass


class StaleEpochError(LobbyStateError):
    pass


def capture_lobby_state(host_id, epoch):
    scene_snapshots = {}
    with shared_projection.store.locked():
        for scene_id, channels in export_scene_snapshots().items():
            scene_snapshots[str(scene_id)] = {}
            for channel_id, players in channels.items():
                scene_snapshots[str(scene_id)][str(channel_id)] = {
                    str(player_id): base64.b64encode(payload).decode("ascii")
                    for player_id, payload in players.items()
                }
        projections = {
            str(player_id): projection
            for player_id, projection in shared_projection.store.snapshot().items()
        }
    return {
        "version": STATE_VERSION,
        "host_id": str(host_id),
        "epoch": int(epoch),
        "captured_at": time.time(),
        "projections": projections,
        "scene_snapshots": scene_snapshots,
    }


def validate_lobby_state(state):
    if not isinstance(state, dict):
        raise LobbyStateError("lobby state must be an object")
    if state.get("version") != STATE_VERSION:
        raise LobbyStateError("unsupported lobby state version")
    if not isinstance(state.get("host_id"), str) or not state["host_id"]:
        raise LobbyStateError("lobby state host_id is invalid")
    epoch = state.get("epoch")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise LobbyStateError("lobby state epoch is invalid")
    if not isinstance(state.get("projections"), dict):
        raise LobbyStateError("lobby state projections are invalid")
    if not isinstance(state.get("scene_snapshots"), dict):
        raise LobbyStateError("lobby state scene snapshots are invalid")
    return state


def restore_lobby_state(state, current_epoch=0, allow_equal=False):
    validate_lobby_state(state)
    epoch = int(state["epoch"])
    if epoch < current_epoch or (epoch == current_epoch and not allow_equal):
        raise StaleEpochError(
            f"lobby state epoch {epoch} is stale; current epoch is {current_epoch}"
        )

    projections = state["projections"]
    try:
        for player_id, projection in projections.items():
            if not isinstance(projection, dict):
                raise LobbyStateError("projection must be an object")
            if projection.get("player_id") != int(player_id):
                raise LobbyStateError("projection player_id mismatch")
            for field in ("scene_id", "channel_id", "char_id", "version"):
                value = projection.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, int):
                    raise LobbyStateError(f"projection {field} is invalid")
            if projection["version"] < 1:
                raise LobbyStateError("projection version is invalid")
            for field in ("position", "rotation"):
                vector = projection.get(field)
                if not isinstance(vector, (list, tuple)) or len(vector) != 3:
                    raise LobbyStateError(f"projection {field} is invalid")
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in vector
                ):
                    raise LobbyStateError(f"projection {field} is invalid")
            updated_at = projection.get("updated_at", 0.0)
            if (
                isinstance(updated_at, bool)
                or not isinstance(updated_at, (int, float))
                or not math.isfinite(updated_at)
                or updated_at < 0
            ):
                raise LobbyStateError("projection updated_at is invalid")
            if not isinstance(projection.get("restored", True), bool):
                raise LobbyStateError("projection restored flag is invalid")
    except (TypeError, ValueError) as error:
        if isinstance(error, LobbyStateError):
            raise
        raise LobbyStateError("projection data is invalid") from error

    decoded_scene_snapshots = {}
    try:
        for scene_id, channels in state["scene_snapshots"].items():
            decoded_scene_snapshots[int(scene_id)] = {}
            for channel_id, players in channels.items():
                decoded_players = decoded_scene_snapshots[int(scene_id)][
                    int(channel_id)
                ] = {}
                for player_id, payload in players.items():
                    recorder = PlayerRecorderData()
                    recorder.ParseFromString(base64.b64decode(payload, validate=True))
                    decoded_players[int(player_id)] = recorder.SerializeToString()
    except (TypeError, ValueError, DecodeError) as error:
        raise LobbyStateError("lobby state scene snapshot encoding is invalid") from error

    shared_projection.store.restore(projections)
    import_scene_snapshots(decoded_scene_snapshots)
    return epoch


def persist_lobby_state(path, state):
    validate_lobby_state(state)
    target = os.path.abspath(path)
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    temporary = target + ".tmp-" + uuid.uuid4().hex
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_lobby_state(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise LobbyStateError("unable to read lobby state") from error
    return validate_lobby_state(state)


def prepare_lobby_failover(path, new_host_id, expected_epoch=None):
    state = load_lobby_state(path)
    if state is None:
        raise LobbyStateError("lobby state does not exist")
    if expected_epoch is not None and state["epoch"] != int(expected_epoch):
        raise StaleEpochError(
            f"lobby state epoch {state['epoch']} does not match {expected_epoch}"
        )
    if not isinstance(new_host_id, str) or not new_host_id:
        raise LobbyStateError("new host_id is invalid")
    state["host_id"] = new_host_id
    state["epoch"] += 1
    state["failover_at"] = time.time()
    persist_lobby_state(path, state)
    return state


class LobbyHostLease:
    def __init__(self, host_id, epoch=1, lease_seconds=10.0, clock=time.monotonic):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.host_id = str(host_id)
        self.epoch = int(epoch)
        self.lease_seconds = float(lease_seconds)
        self._clock = clock
        self._lock = Lock()
        self._lease_until = self._clock() + self.lease_seconds

    def renew(self, epoch=None):
        with self._lock:
            if epoch is not None and int(epoch) != self.epoch:
                raise StaleEpochError("cannot renew a lease with a stale epoch")
            current = self._clock()
            if current >= self._lease_until:
                raise StaleEpochError("cannot renew an expired host lease")
            self._lease_until = current + self.lease_seconds

    def is_valid(self, now=None):
        with self._lock:
            current = self._clock() if now is None else now
            return current < self._lease_until

    def assert_valid(self, now=None):
        if not self.is_valid(now):
            raise StaleEpochError("host lease has expired")

    def acquire_if_expired(self, host_id, now=None):
        with self._lock:
            current = self._clock() if now is None else now
            if current < self._lease_until:
                return False
            self.host_id = str(host_id)
            self.epoch += 1
            self._lease_until = current + self.lease_seconds
            return True

    def snapshot(self):
        with self._lock:
            return {
                "host_id": self.host_id,
                "epoch": self.epoch,
                "lease_until": self._lease_until,
            }


_active_lease = None
_active_lease_lock = Lock()


def activate_host_lease(lease):
    global _active_lease
    with _active_lease_lock:
        _active_lease = lease


def deactivate_host_lease(lease):
    global _active_lease
    with _active_lease_lock:
        if _active_lease is lease:
            _active_lease = None


def host_lease_is_valid():
    with _active_lease_lock:
        lease = _active_lease
    return lease is None or lease.is_valid()


def assert_host_authority():
    with _active_lease_lock:
        lease = _active_lease
    if lease is not None:
        lease.assert_valid()
