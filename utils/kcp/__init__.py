"""
KCP Protocol Python Wrapper

Provides reliable UDP transport using the KCP protocol.
Supports multiple servers and clients with thread-safe sessions.

Usage:
    from utils.kcp import KCPSession, get_conv, current_ms

    # Server side - manage multiple clients
    sessions = {}  # conv -> KCPSession

    def on_udp_recv(data, addr):
        conv = get_conv(data)
        if conv not in sessions:
            sessions[conv] = KCPSession(conv, lambda d: sock.sendto(d, addr))
        sessions[conv].input(data)

        while True:
            msg = sessions[conv].recv()
            if msg is None:
                break
            handle_message(msg)

    # Client side
    session = KCPSession(conv=12345, output=lambda d: sock.sendto(d, server_addr))
    session.send(b"Hello")
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional, Any
from collections.abc import Callable as CallableABC

from ._kcp import KCPSession, get_conv, current_ms, OVERHEAD

__all__ = [
    "KCPSession",
    "KCPManager",
    "get_conv",
    "current_ms",
    "OVERHEAD",
]


class KCPManager:
    """
    Manages multiple KCP sessions for server-side use.
    Thread-safe session management for handling multiple clients.
    """

    def __init__(
        self,
        output_factory: Callable[[int], Callable[[bytes], None]],
        on_recv: Optional[Callable[[int, bytes], None]] = None,
        on_dead: Optional[Callable[[int], None]] = None,
    ):
        """
        Initialize KCP Manager.

        Args:
            output_factory: Factory function that takes conv and returns
                           an output callback for sending UDP packets.
                           Signature: (conv: int) -> (data: bytes) -> None
            on_recv: Optional callback when data is received.
                    Signature: (conv: int, data: bytes) -> None
            on_dead: Optional callback when a session dies.
                    Signature: (conv: int) -> None
        """
        self._sessions: Dict[int, KCPSession] = {}
        self._lock = threading.Lock()
        self._output_factory = output_factory
        self._on_recv = on_recv
        self._on_dead = on_dead
        self._running = False
        self._update_thread: Optional[threading.Thread] = None

    def get_or_create(self, conv: int) -> KCPSession:
        """Get existing session or create new one."""
        with self._lock:
            if conv not in self._sessions:
                output = self._output_factory(conv)
                session = KCPSession(conv, output)
                self._sessions[conv] = session
            return self._sessions[conv]

    def get(self, conv: int) -> Optional[KCPSession]:
        """Get session by conv ID, or None if not exists."""
        with self._lock:
            return self._sessions.get(conv)

    def remove(self, conv: int) -> bool:
        """Remove session by conv ID. Returns True if removed."""
        with self._lock:
            if conv in self._sessions:
                del self._sessions[conv]
                return True
            return False

    def input(self, data: bytes) -> Optional[int]:
        """
        Feed UDP packet to the appropriate session.
        Creates session if not exists.
        Returns conv ID, or None if data is invalid.
        """
        if len(data) < OVERHEAD:
            return None

        conv = get_conv(data)
        session = self.get_or_create(conv)
        session.input(data)
        return conv

    def recv(self, conv: int) -> Optional[bytes]:
        """Receive data from specific session."""
        session = self.get(conv)
        if session is None:
            return None
        return session.recv()

    def recv_all(self, conv: int) -> list[bytes]:
        """Receive all available messages from session."""
        session = self.get(conv)
        if session is None:
            return []

        messages = []
        while True:
            msg = session.recv()
            if msg is None:
                break
            messages.append(msg)
        return messages

    def send(self, conv: int, data: bytes) -> bool:
        """Send data to specific session. Returns False if session not found."""
        session = self.get(conv)
        if session is None:
            return False
        session.send(data)
        return True

    def update_all(self) -> list[int]:
        """
        Update all sessions.
        Returns list of dead session conv IDs (already removed).
        """
        dead_convs = []

        with self._lock:
            sessions = list(self._sessions.items())

        for conv, session in sessions:
            session.update()
            if session.dead:
                dead_convs.append(conv)

        # Remove dead sessions
        for conv in dead_convs:
            self.remove(conv)
            if self._on_dead:
                try:
                    self._on_dead(conv)
                except Exception:
                    pass

        return dead_convs

    def start_update_loop(self, interval_ms: int = 10) -> None:
        """Start background update thread."""
        if self._running:
            return

        self._running = True

        def update_loop():
            interval = interval_ms / 1000.0
            while self._running:
                self.update_all()

                # Process receives if callback set
                if self._on_recv:
                    with self._lock:
                        convs = list(self._sessions.keys())

                    for conv in convs:
                        for msg in self.recv_all(conv):
                            try:
                                self._on_recv(conv, msg)
                            except Exception:
                                pass

                time.sleep(interval)

        self._update_thread = threading.Thread(target=update_loop, daemon=True)
        self._update_thread.start()

    def stop_update_loop(self) -> None:
        """Stop background update thread."""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=1.0)
            self._update_thread = None

    def close_all(self) -> None:
        """Close all sessions."""
        self.stop_update_loop()
        with self._lock:
            self._sessions.clear()

    @property
    def session_count(self) -> int:
        """Get number of active sessions."""
        with self._lock:
            return len(self._sessions)

    @property
    def sessions(self) -> Dict[int, KCPSession]:
        """Get copy of sessions dict."""
        with self._lock:
            return dict(self._sessions)

    def __bool__(self) -> bool:
        return True

    def __len__(self) -> int:
        return self.session_count

    def __contains__(self, conv: int) -> bool:
        with self._lock:
            return conv in self._sessions

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close_all()
