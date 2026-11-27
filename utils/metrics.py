"""Process-local multiplayer metrics with bounded, label-free cardinality."""

from collections import Counter
from threading import RLock


class MetricsRegistry:
    def __init__(self):
        self._lock = RLock()
        self._counters = Counter()
        self._gauges = {}
        self._timers = {}

    def inc(self, name, value=1):
        with self._lock:
            self._counters[name] += value

    def set(self, name, value):
        with self._lock:
            self._gauges[name] = value

    def observe(self, name, seconds):
        with self._lock:
            state = self._timers.setdefault(name, [0, 0.0, 0.0])
            state[0] += 1
            state[1] += max(0.0, float(seconds))
            state[2] = max(state[2], float(seconds))

    def snapshot(self):
        with self._lock:
            return {
                "counters": dict(sorted(self._counters.items())),
                "gauges": dict(sorted(self._gauges.items())),
                "timers": {
                    name: {
                        "count": state[0],
                        "total_seconds": state[1],
                        "max_seconds": state[2],
                        "avg_seconds": state[1] / state[0] if state[0] else 0.0,
                    }
                    for name, state in sorted(self._timers.items())
                },
            }

    def reset(self):
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()


metrics = MetricsRegistry()
