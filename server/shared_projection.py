"""Minimal cross-player projection stored separately from private player state."""

from dataclasses import dataclass, replace
import math
import threading
import time
from typing import Dict, Optional, Tuple

from utils import metrics as metrics_registry

Vector = Tuple[float, float, float]


def _vector(value) -> Vector:
    result = (float(value.x), float(value.y), float(value.z))
    if not all(math.isfinite(component) for component in result):
        raise ValueError("projection vectors must be finite")
    return result


@dataclass(frozen=True)
class SharedProjection:
    player_id: int
    scene_id: int
    channel_id: int
    char_id: int = 0
    position: Vector = (0.0, 0.0, 0.0)
    rotation: Vector = (0.0, 0.0, 0.0)
    action_id: int = 0
    emoji_id: int = 0
    version: int = 1
    updated_at: float = 0.0
    restored: bool = False

    def squared_distance(self, other: "SharedProjection") -> float:
        return sum((a - b) ** 2 for a, b in zip(self.position, other.position))

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "scene_id": self.scene_id,
            "channel_id": self.channel_id,
            "char_id": self.char_id,
            "position": self.position,
            "rotation": self.rotation,
            "action_id": self.action_id,
            "emoji_id": self.emoji_id,
            "version": self.version,
            "updated_at": self.updated_at,
            "restored": self.restored,
        }


class ProjectionStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._items: Dict[int, SharedProjection] = {}

    def update(self, projection: SharedProjection) -> SharedProjection:
        with self._lock:
            previous = self._items.get(projection.player_id)
            version = (
                previous.version + 1
                if previous is not None
                else max(1, int(projection.version))
            )
            updated = replace(
                projection,
                version=version,
                updated_at=time.time(),
            )
            self._items[projection.player_id] = updated
            metrics_registry.metrics.inc("ofps.projection.updates_total")
            metrics_registry.metrics.set(
                "ofps.projection.active", len(self._items)
            )
            return updated

    def update_from_recorder(
        self,
        player_id: int,
        scene_id: int,
        channel_id: int,
        recorder_data,
    ) -> Optional[SharedProjection]:
        char_records = recorder_data.char_recorder_data_lst
        if not char_records:
            return None
        record = char_records[0]
        projection = SharedProjection(
            player_id=player_id,
            scene_id=scene_id,
            channel_id=channel_id,
            char_id=int(record.char_id),
            position=_vector(record.pos),
            rotation=_vector(record.rot),
        )
        return self.update(projection)

    def record_action(
        self, player_id: int, scene_id: int, channel_id: int, action_id: int
    ) -> Optional[SharedProjection]:
        with self._lock:
            current = self._items.get(player_id)
            if current is None:
                current = SharedProjection(
                    player_id=player_id,
                    scene_id=scene_id,
                    channel_id=channel_id,
                )
            return self.update(replace(current, action_id=int(action_id)))

    def record_emoji(
        self, player_id: int, scene_id: int, channel_id: int, emoji_id: int
    ) -> Optional[SharedProjection]:
        with self._lock:
            current = self._items.get(player_id)
            if current is None:
                current = SharedProjection(
                    player_id=player_id,
                    scene_id=scene_id,
                    channel_id=channel_id,
                )
            return self.update(replace(current, emoji_id=int(emoji_id)))

    def move(self, player_id: int, scene_id: int, channel_id: int):
        with self._lock:
            current = self._items.get(player_id)
            if current is not None:
                self.update(
                    replace(current, scene_id=scene_id, channel_id=channel_id)
                )

    def touch(self, player_id):
        with self._lock:
            current = self._items.get(player_id)
            if current is None:
                return None
            updated = replace(current, updated_at=time.time(), restored=False)
            self._items[player_id] = updated
            return updated

    def prune_restored(self, max_age, now=None):
        if max_age <= 0:
            raise ValueError("max_age must be positive")
        current_time = time.time() if now is None else now
        with self._lock:
            expired = tuple(
                projection
                for projection in self._items.values()
                if projection.restored
                and current_time - projection.updated_at > max_age
            )
            for projection in expired:
                self._items.pop(projection.player_id, None)
            if expired:
                metrics_registry.metrics.inc(
                    "ofps.projection.restored_expirations_total", len(expired)
                )
                metrics_registry.metrics.set(
                    "ofps.projection.active", len(self._items)
                )
            return expired

    def remove(self, player_id: int):
        with self._lock:
            removed = self._items.pop(player_id, None)
            if removed is not None:
                metrics_registry.metrics.inc("ofps.projection.removals_total")
                metrics_registry.metrics.set(
                    "ofps.projection.active", len(self._items)
                )
            return removed

    def get(self, player_id: int) -> Optional[SharedProjection]:
        with self._lock:
            return self._items.get(player_id)

    def channel_snapshot(self, scene_id: int, channel_id: int):
        with self._lock:
            return tuple(
                projection
                for projection in self._items.values()
                if projection.scene_id == scene_id
                and projection.channel_id == channel_id
            )

    def snapshot(self):
        with self._lock:
            return {
                player_id: projection.to_dict()
                for player_id, projection in self._items.items()
            }

    def clear(self):
        with self._lock:
            self._items.clear()
            metrics_registry.metrics.set("ofps.projection.active", 0)

    def restore(self, items):
        with self._lock:
            restored = {}
            for player_id, data in items.items():
                restored[int(player_id)] = SharedProjection(
                    player_id=int(data["player_id"]),
                    scene_id=int(data["scene_id"]),
                    channel_id=int(data["channel_id"]),
                    char_id=int(data.get("char_id", 0)),
                    position=tuple(float(value) for value in data["position"]),
                    rotation=tuple(float(value) for value in data["rotation"]),
                    action_id=int(data.get("action_id", 0)),
                    emoji_id=int(data.get("emoji_id", 0)),
                    version=int(data.get("version", 1)),
                    updated_at=float(data.get("updated_at", 0.0)),
                    restored=bool(data.get("restored", True)),
                )
            self._items = restored
            metrics_registry.metrics.set("ofps.projection.active", len(restored))


store = ProjectionStore()
