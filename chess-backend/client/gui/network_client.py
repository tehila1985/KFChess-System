"""
network_client.py — threaded asyncio wrapper around ClientSession.

The cv2 GUI runs a blocking window loop on the main thread; the websocket
client needs its own asyncio event loop. This class owns that loop on a
background daemon thread and exposes a small thread-safe surface to the
main thread:
  - request()     blocking request/response, for explicit user actions
                   (login, register, room create/join, play request, move)
  - send()        fire-and-forget (e.g. resign)
  - poll_events()  drains push-style server messages that arrive unprompted
                   (GAME_START, PLAY_MATCH_FOUND/TIMEOUT, MOVE_BROADCAST,
                   OPPONENT_DISCONNECTED, DISCONNECT_COUNTDOWN_TICK, GAME_END)

ClientSession itself (send/receive framing, request_id correlation) is
reused unchanged — this class only adds the thread boundary.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Optional

from client.client_session import ClientSession
from client.logging_.client_logger import ClientLogger
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

# Messages that are NOT correlated to a request() call and must be drained
# by the main thread via poll_events(). MOVE_ACK is deliberately excluded —
# moves are sent via request(), so the ACK resolves that call directly.
_PUSH_TYPES = (
    MessageType.GAME_START,
    MessageType.PLAY_MATCH_FOUND,
    MessageType.PLAY_TIMEOUT,
    MessageType.MOVE_BROADCAST,
    MessageType.GAME_END,
    MessageType.OPPONENT_DISCONNECTED,
    MessageType.DISCONNECT_COUNTDOWN_TICK,
)


class NetworkClient:
    """Runs ClientSession on a background asyncio loop; thread-safe facade for the GUI thread."""

    def __init__(self, uri: str, client_logger: ClientLogger) -> None:
        self._uri = uri
        self._log = client_logger
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[ClientSession] = None
        self._events: "queue.Queue[Envelope]" = queue.Queue()
        self._ready = threading.Event()
        self._connect_error: Optional[BaseException] = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self, timeout: float = 10.0) -> None:
        """Start the background loop and connect. Blocks until connected or raises."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise TimeoutError("Timed out connecting to server")
        if self._connect_error is not None:
            raise self._connect_error

    def stop(self) -> None:
        if self._loop is None or self._session is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self._session.disconnect(), self._loop)
        try:
            fut.result(timeout=3.0)
        except Exception:
            pass  # best-effort — we're shutting down either way
        self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_and_serve())

    async def _connect_and_serve(self) -> None:
        session = ClientSession(uri=self._uri, client_logger=self._log)
        try:
            await session.connect()
        except Exception as exc:
            self._connect_error = exc
            self._ready.set()
            return
        self._session = session
        for msg_type in _PUSH_TYPES:
            session.on(msg_type, self._enqueue)
        self._ready.set()
        await session.receive_loop()

    def _enqueue(self, env: Envelope) -> None:
        self._events.put(env)

    # ── Main-thread API ──────────────────────────────────────────────

    @property
    def session(self) -> ClientSession:
        assert self._session is not None, "NetworkClient not started"
        return self._session

    def request(self, envelope: Envelope, timeout: float = 10.0) -> Envelope:
        """Blocking request/response — for explicit user-submitted actions."""
        fut = asyncio.run_coroutine_threadsafe(
            self._session.request(envelope, timeout=timeout), self._loop
        )
        return fut.result(timeout=timeout + 2.0)

    def send(self, envelope: Envelope) -> None:
        """Fire-and-forget send."""
        asyncio.run_coroutine_threadsafe(self._session.send(envelope), self._loop)

    def poll_events(self) -> list[Envelope]:
        """Drain all push-style messages received since the last poll."""
        events: list[Envelope] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events
