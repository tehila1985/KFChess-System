"""
disconnect_monitor.py — runs a countdown for exactly one disconnected player.

SRP: countdown only. Emits one tick per second, fires on_timeout callback
when the grace period expires, cancels cleanly on reconnect.

Independently unit-testable with a fake clock.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Optional


class DisconnectMonitor:
    """
    Countdown timer for one disconnected player.

    Usage:
        monitor = DisconnectMonitor(
            grace_seconds=20,
            tick_seconds=1.0,
            on_tick=lambda s: ...,
            on_timeout=lambda: ...,
            logger=...,
        )
        await monitor.start()   # starts the countdown task
        monitor.cancel()        # call if player reconnects
    """

    def __init__(
        self,
        grace_seconds: int,
        tick_seconds: float,
        on_tick: Callable[[int], Coroutine],   # called each second with seconds_left
        on_timeout: Callable[[], Coroutine],   # called when countdown reaches 0
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._grace = grace_seconds
        self._tick = tick_seconds
        self._on_tick = on_tick
        self._on_timeout = on_timeout
        self._log = logger or logging.getLogger(__name__)
        self._task: Optional[asyncio.Task] = None
        self._cancelled = False
        self._fired = False

    async def start(self) -> None:
        """Start the countdown task."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    def cancel(self) -> None:
        """Cancel the countdown (call when player reconnects)."""
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def did_fire(self) -> bool:
        """Returns True if the timeout callback was invoked."""
        return self._fired

    async def _run(self) -> None:
        seconds = self._grace
        try:
            while seconds > 0:
                await self._on_tick(seconds)
                await asyncio.sleep(self._tick)
                seconds -= 1

            if not self._cancelled:
                self._fired = True
                try:
                    await self._on_timeout()
                except Exception as exc:
                    self._log.exception("disconnect_monitor_timeout_callback_error: %s", exc)
        except asyncio.CancelledError:
            pass
