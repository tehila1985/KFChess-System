"""
gateway/main.py — Phase 2 of .github/Server_Design_Implementation_Plan.md.

Owns the WS listener and the actual client sockets — nothing else. Every
inbound client message is published to NATS as a "shard.{shard_id}.inbound"
event; every reply comes back on "shard.{shard_id}.outbound" and gets
written to whichever local conn_id it's addressed to. No business logic
lives here: auth, matchmaking, rooms, and game state are entirely the
Shard's responsibility (shard/main.py).

Phase 3 update: outbound is now a wildcard subscription
("shard.*.outbound") so this Gateway receives replies from *any* Shard,
not just its configured default. Inbound routing for MOVE/RESIGN consults
"conn:{conn_id}:shard" in Redis (written by whichever Shard actually ended
up owning that connection's GameSession — see
server/services/game_handoff.py) so those messages reach the right Shard
even if the Game Allocator placed the game somewhere other than this
Gateway's default. Every other message type (LOGIN/REGISTER/PLAY_*/ROOM_*)
is stateless across Shards (same Redis, same users DB) and always goes to
this Gateway's own configured default shard_id — no need to look anything
up for those.

Run: python -m gateway.main  (needs Redis + NATS reachable — see docker-compose.yml)
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import uuid

import nats
import redis as redis_lib
import websockets

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, ErrorPayload
from server.config_loader import load_settings
from server.logging_.server_logger import build_server_logger


async def serve(settings=None, server_logger=None, nats_client=None, redis_client=None):
    if settings is None:
        settings = load_settings()
        # Separate log file from shard/main.py — two processes must not
        # share one rotating file handler.
        settings = dataclasses.replace(
            settings,
            logging=dataclasses.replace(
                settings.logging,
                server_log_path=settings.logging.server_log_path.replace(".log", "-gateway.log"),
            ),
        )

    if server_logger is None:
        server_logger = build_server_logger(settings)

    # Same logger name build_server_logger() configures (handlers attached
    # to "chess.server", exactly like server/main.py) so these .info() calls
    # actually reach gateway's own log file instead of an unconfigured logger.
    raw_logger = logging.getLogger("chess.server")
    shard_id = settings.backend.shard_id

    if nats_client is None:
        nats_client = await nats.connect(settings.backend.nats_url)
    if redis_client is None:
        redis_client = redis_lib.Redis.from_url(settings.backend.redis_url, decode_responses=True)

    default_inbound_subject = f"shard.{shard_id}.inbound"
    outbound_wildcard_subject = "shard.*.outbound"

    # Message types whose active GameSession may live on a shard other than
    # this Gateway's configured default — everything else is stateless
    # across shards (shared Redis, shared users DB) and always goes home.
    _GAME_SCOPED_TYPES = {"MOVE", "RESIGN"}

    connections: dict[str, "websockets.asyncio.server.ServerConnection"] = {}

    async def on_outbound(msg):
        try:
            event = json.loads(msg.data.decode())
        except Exception:
            raw_logger.warning("gateway_outbound_decode_error subject=%s", msg.subject)
            return
        ws = connections.get(event.get("conn_id"))
        if ws is None:
            return  # this gateway doesn't own that connection (already disconnected)
        try:
            await ws.send(event["message"])
        except Exception as exc:
            raw_logger.warning("gateway_outbound_send_error conn_id=%s exc=%s", event.get("conn_id"), exc)

    subscription = await nats_client.subscribe(outbound_wildcard_subject, cb=on_outbound)

    def _game_shard_subject_or_none(conn_id: str) -> "str | None":
        """The Shard that owns conn_id's active game, if any and if
        different from this Gateway's own default."""
        target_shard = redis_client.get(f"conn:{conn_id}:shard")
        if target_shard is None:
            return None
        if isinstance(target_shard, bytes):
            target_shard = target_shard.decode()
        if target_shard == shard_id:
            return None
        return f"shard.{target_shard}.inbound"

    def _inbound_subject_for(conn_id: str, raw_message: str) -> str:
        try:
            msg_type = json.loads(raw_message).get("type")
        except Exception:
            return default_inbound_subject
        if msg_type not in _GAME_SCOPED_TYPES:
            return default_inbound_subject
        return _game_shard_subject_or_none(conn_id) or default_inbound_subject

    async def connection_handler(websocket):
        conn_id = str(uuid.uuid4())
        remote = str(websocket.remote_address)
        connections[conn_id] = websocket
        server_logger.connection_opened(conn_id, remote)
        await nats_client.publish(
            default_inbound_subject,
            json.dumps({"kind": "connected", "conn_id": conn_id, "remote": remote}).encode(),
        )

        try:
            async for raw_message in websocket:
                subject = _inbound_subject_for(conn_id, raw_message)
                await nats_client.publish(
                    subject,
                    json.dumps({"kind": "message", "conn_id": conn_id, "raw": raw_message}).encode(),
                )
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            connections.pop(conn_id, None)
            server_logger.connection_closed(conn_id, remote)
            disconnect_event = json.dumps({"kind": "disconnected", "conn_id": conn_id, "remote": remote}).encode()
            # Always tell the default shard (it may have this conn_id queued
            # in matchmaking) *and* the shard actually running this conn_id's
            # game, if placement put it somewhere else — either could have
            # cleanup to do, and a disconnect must never go unnoticed on
            # either side.
            await nats_client.publish(default_inbound_subject, disconnect_event)
            game_shard_subject = _game_shard_subject_or_none(conn_id)
            if game_shard_subject is not None:
                await nats_client.publish(game_shard_subject, disconnect_event)

    known_shards_key = "shards:known"

    def _heartbeat_key(sid: str) -> str:
        return f"shard:{sid}:heartbeat"

    async def shard_watchdog_loop():
        """
        Detect a hard-killed Shard process via its Redis heartbeat key
        expiring (see shard/main.py's heartbeat_loop), and tell every
        client whose connection was actually on that shard — for
        connections with no "conn:{conn_id}:shard" entry (never in a game,
        or in a game still on this Gateway's own default), that's this
        Gateway's own default shard_id.

        Watches every shard in "shards:known" (Phase 3, many shards), not
        just this Gateway's own default (Phase 2, exactly one) — a game
        placed elsewhere by the Allocator must still produce this same
        client-visible signal if *that* shard dies, not just the default.
        This is the observable signal for Server_Design.md §1 Q4/§5's
        "aborted" outcome.
        """
        known_up: dict[str, bool] = {}
        try:
            while True:
                await asyncio.sleep(1.0)
                watched = {shard_id} | {
                    (s.decode() if isinstance(s, bytes) else s)
                    for s in redis_client.smembers(known_shards_key)
                }
                for sid in watched:
                    is_up = bool(redis_client.exists(_heartbeat_key(sid)))
                    was_up = known_up.get(sid)
                    if was_up is True and is_up is False:
                        raw_logger.warning("shard_unavailable shard_id=%s", sid)
                        err = Envelope(
                            type=MessageType.ERROR,
                            payload=ErrorPayload(reason="shard_unavailable").model_dump(),
                        ).to_json()
                        for conn_id, ws in list(connections.items()):
                            conn_shard = redis_client.get(f"conn:{conn_id}:shard") or shard_id
                            if isinstance(conn_shard, bytes):
                                conn_shard = conn_shard.decode()
                            if conn_shard != sid:
                                continue
                            try:
                                await ws.send(err)
                            except Exception:
                                pass
                    known_up[sid] = is_up
        except asyncio.CancelledError:
            pass

    watchdog_task = asyncio.create_task(shard_watchdog_loop())

    host = settings.server.host
    port = settings.server.port
    raw_logger.info("gateway_starting host=%s port=%s shard_id=%s", host, port, shard_id)

    try:
        async with websockets.serve(connection_handler, host, port):
            await asyncio.Future()  # run forever
    finally:
        watchdog_task.cancel()
        await subscription.unsubscribe()


if __name__ == "__main__":
    asyncio.run(serve())
