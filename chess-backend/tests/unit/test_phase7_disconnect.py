"""
Phase 7 unit tests — DisconnectMonitor and GameSession disconnect handling.
"""
from __future__ import annotations

import asyncio
import pytest

from server.services.disconnect_monitor import DisconnectMonitor
from server.config_loader import load_settings


# ── DisconnectMonitor ────────────────────────────────────────────────────────

class TestDisconnectMonitor:

    async def test_fires_timeout_after_grace_period(self):
        """on_timeout is called once all ticks have elapsed."""
        ticks: list[int] = []
        fired: list[bool] = []

        async def on_tick(s): ticks.append(s)
        async def on_timeout(): fired.append(True)

        monitor = DisconnectMonitor(
            grace_seconds=3,
            tick_seconds=0.01,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        await monitor.start()
        await asyncio.sleep(0.15)  # enough time for 3 ticks + timeout

        assert fired == [True], "timeout callback must fire exactly once"
        assert monitor.did_fire()

    async def test_emits_one_tick_per_second(self):
        """Ticks count down from grace_seconds to 1."""
        ticks: list[int] = []

        async def on_tick(s): ticks.append(s)
        async def on_timeout(): pass

        monitor = DisconnectMonitor(
            grace_seconds=3,
            tick_seconds=0.01,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        await monitor.start()
        await asyncio.sleep(0.15)

        assert ticks == [3, 2, 1]

    async def test_cancel_prevents_timeout(self):
        """cancel() before timeout means on_timeout is never called."""
        fired: list[bool] = []

        async def on_tick(s): pass
        async def on_timeout(): fired.append(True)

        monitor = DisconnectMonitor(
            grace_seconds=5,
            tick_seconds=0.05,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        await monitor.start()
        await asyncio.sleep(0.08)  # let one tick fire
        monitor.cancel()
        await asyncio.sleep(0.3)   # wait past what would have been the timeout

        assert fired == [], "timeout must not fire after cancel"
        assert not monitor.did_fire()

    async def test_cancel_mid_countdown(self):
        """Cancelling mid-countdown leaves is_running() False."""
        async def on_tick(s): pass
        async def on_timeout(): pass

        monitor = DisconnectMonitor(
            grace_seconds=10,
            tick_seconds=0.02,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        await monitor.start()
        assert monitor.is_running()
        monitor.cancel()
        await asyncio.sleep(0.05)
        assert not monitor.is_running()

    async def test_no_double_fire(self):
        """start() called twice does not start a second task."""
        calls: list[int] = []

        async def on_tick(s): pass
        async def on_timeout(): calls.append(1)

        monitor = DisconnectMonitor(
            grace_seconds=2,
            tick_seconds=0.01,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        await monitor.start()
        await monitor.start()  # second call should be no-op
        await asyncio.sleep(0.1)

        assert len(calls) == 1, "timeout must fire exactly once even with duplicate start()"

    async def test_timeout_not_called_if_cancelled_before_start(self):
        """Cancelling before start means task never runs."""
        fired: list[bool] = []

        async def on_tick(s): pass
        async def on_timeout(): fired.append(True)

        monitor = DisconnectMonitor(
            grace_seconds=1,
            tick_seconds=0.01,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        monitor.cancel()   # cancel before start
        await monitor.start()
        await asyncio.sleep(0.1)

        assert fired == []

    async def test_is_running_false_before_start(self):
        async def on_tick(s): pass
        async def on_timeout(): pass

        monitor = DisconnectMonitor(
            grace_seconds=5,
            tick_seconds=1,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        assert not monitor.is_running()

    async def test_did_fire_false_before_timeout(self):
        async def on_tick(s): pass
        async def on_timeout(): pass

        monitor = DisconnectMonitor(
            grace_seconds=5,
            tick_seconds=0.05,
            on_tick=on_tick,
            on_timeout=on_timeout,
        )
        await monitor.start()
        await asyncio.sleep(0.08)
        assert not monitor.did_fire()
        monitor.cancel()


# ── GameSession disconnect integration ──────────────────────────────────────

class TestGameSessionDisconnect:
    """Tests that GameSession correctly wires DisconnectMonitor."""

    def _make_session(self):
        """Build a GameSession with a real ConnectionHub and fake websockets.

        Uses the real ConnectionHub (not a bare MagicMock) so that
        end_game()'s broadcast path runs through actual asyncio.gather /
        genuine await-suspension points, the same way it does in production.
        A bare MagicMock for hub.broadcast_to_tokens resolves synchronously
        and would hide bugs that only manifest when a task is cancelled at a
        real suspension point (see test_disconnect_timeout_triggers_end_game).
        """
        import uuid
        from unittest.mock import MagicMock
        from server.services.game_session import GameSession
        from server.services.rating_service import RatingService
        from server.domain.player import Player
        from server.connection_hub import ConnectionHub

        class FakeWebSocket:
            def __init__(self):
                self.sent: list[str] = []

            async def send(self, message: str) -> None:
                await asyncio.sleep(0)  # genuine suspension, like a real socket write
                self.sent.append(message)

        hub = ConnectionHub(logger=MagicMock())
        white_ws = FakeWebSocket()
        black_ws = FakeWebSocket()
        hub.register("conn-alice", white_ws)
        hub.register("conn-bob", black_ws)
        hub.associate_token("conn-alice", "tok-alice")
        hub.associate_token("conn-bob", "tok-bob")

        user_repo = MagicMock()
        user_repo.update_elo = MagicMock()

        game_repo = MagicMock()
        game_repo.record_game = MagicMock()

        white = Player(user_id=1, username="Alice", conn_id="conn-alice", elo=1200, session_token="tok-alice")
        black = Player(user_id=2, username="Bob",   conn_id="conn-bob",   elo=1200, session_token="tok-bob")

        rating = RatingService(load_settings())

        session = GameSession(
            game_id=str(uuid.uuid4()),
            white=white,
            black=black,
            hub=hub,
            user_repo=user_repo,
            game_repo=game_repo,
            rating_service=rating,
            logger=MagicMock(),
            disconnect_grace_seconds=3,
            countdown_tick_seconds=0.01,
        )
        return session, white, black, hub, white_ws, black_ws

    async def test_handle_disconnect_starts_monitor(self):
        """handle_disconnect stores a monitor for the disconnected player."""
        session, white, black, hub, white_ws, black_ws = self._make_session()
        await session.handle_disconnect(white.conn_id)
        assert white.conn_id in session._monitors
        # Cleanup
        session._monitors[white.conn_id].cancel()

    async def test_handle_reconnect_cancels_monitor(self):
        """handle_reconnect cancels the existing monitor."""
        session, white, black, hub, white_ws, black_ws = self._make_session()
        await session.handle_disconnect(white.conn_id)
        await session.handle_reconnect(white.conn_id, "new-conn")
        assert white.conn_id not in session._monitors

    async def test_disconnect_timeout_triggers_end_game(self):
        """After the grace period, end_game is called with opponent wins."""
        session, white, black, hub, white_ws, black_ws = self._make_session()
        await session.handle_disconnect(white.conn_id)

        # Wait for countdown (3 × 0.01s ticks + a bit more)
        await asyncio.sleep(0.15)

        # game should have ended — ELO updated
        assert session._user_repo.update_elo.called
        # GAME_END must actually reach both players — regression guard for the
        # self-cancellation bug where end_game() cancelling all monitors
        # (including the one whose on_timeout is currently running it) threw
        # a stray CancelledError that aborted the broadcast mid-flight.
        assert any('"type":"GAME_END"' in msg for msg in white_ws.sent), white_ws.sent
        assert any('"type":"GAME_END"' in msg for msg in black_ws.sent), black_ws.sent

    async def test_reconnect_within_grace_prevents_auto_resign(self):
        """Reconnecting before the countdown ends cancels auto-resign."""
        session, white, black, hub, white_ws, black_ws = self._make_session()

        # Use a longer grace so reconnect arrives in time
        session._disconnect_grace = 10
        session._tick_seconds = 0.05

        await session.handle_disconnect(white.conn_id)
        await asyncio.sleep(0.02)  # let one tick fire
        await session.handle_reconnect(white.conn_id, "new-conn")
        await asyncio.sleep(0.3)  # wait past what would have been timeout

        # ELO should NOT have been updated (game not ended)
        assert not session._user_repo.update_elo.called

    async def test_handle_reconnect_repoints_conn_id_so_moves_from_new_conn_work(self):
        """
        Regression guard for Phase 2 of
        .github/Server_Design_Implementation_Plan.md: handle_reconnect used
        to only cancel the disconnect countdown, leaving self._white/_black
        addressing the dead conn_id — apply_move from the new conn_id would
        have failed with 'not_a_player' forever.
        """
        session, white, black, hub, white_ws, black_ws = self._make_session()
        hub.register("conn-alice-2", type(white_ws)())
        hub.associate_token("conn-alice-2", "tok-alice")

        await session.handle_reconnect(white.conn_id, "conn-alice-2")

        assert session.white.conn_id == "conn-alice-2"
        # The old conn_id is no longer recognized as a player in this game.
        result = await session.apply_move("conn-alice", 6, 4, 4, 4)
        assert result.accepted is False
        assert result.reason == "not_a_player"
        # The new conn_id is.
        result2 = await session.apply_move("conn-alice-2", 6, 4, 4, 4)
        assert result2.accepted is True

    async def test_handle_reconnect_updates_session_token_too(self):
        """
        A fresh login mints a brand-new session_token — end_game()'s
        broadcast_to_tokens() would otherwise keep targeting the stale
        pre-reconnect token forever.
        """
        session, white, black, hub, white_ws, black_ws = self._make_session()
        await session.handle_reconnect(white.conn_id, "conn-alice-2", "tok-alice-new")
        assert session.white.session_token == "tok-alice-new"

    async def test_end_game_cancels_all_monitors(self):
        """end_game cleans up all monitors."""
        from server.domain.enums import GameResult, EndReason
        session, white, black, hub, white_ws, black_ws = self._make_session()

        await session.handle_disconnect(white.conn_id)
        assert len(session._monitors) == 1

        await session.end_game(GameResult.BLACK_WINS, EndReason.RESIGN)
        assert len(session._monitors) == 0
