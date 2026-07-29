"""
gateway/main.py — Phase 2 of .github/Server_Design_Implementation_Plan.md.

Owns the WS listener and the actual client sockets — nothing else. Every
inbound client message is published to NATS as a "shard.{shard_id}.inbound"
event; every reply comes back on "shard.{shard_id}.outbound" and gets
written to whichever local conn_id it's addressed to. No business logic
lives here: auth, matchmaking, rooms, and game state are entirely the
Shard's responsibility (shard/main.py).

Phase 2 has exactly one Shard, so routing is trivial: every inbound event
goes to the single configured shard_id. Phase 3 (many shards) will need the
Gateway to learn each in-game connection's shard affinity (e.g. a
"conn:{conn_id}:shard" Redis key written when the Game Allocator places a
match) — deliberately not built here, since Phase 2's only variable is
"does the Gateway/Shard network hop work at all," not "does multi-shard
routing work."

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

    inbound_subject = f"shard.{shard_id}.inbound"
    outbound_subject = f"shard.{shard_id}.outbound"

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

    subscription = await nats_client.subscribe(outbound_subject, cb=on_outbound)

    async def connection_handler(websocket):
        conn_id = str(uuid.uuid4())
        remote = str(websocket.remote_address)
        connections[conn_id] = websocket
        server_logger.connection_opened(conn_id, remote)
        await nats_client.publish(
            inbound_subject,
            json.dumps({"kind": "connected", "conn_id": conn_id, "remote": remote}).encode(),
        )

        try:
            async for raw_message in websocket:
                await nats_client.publish(
                    inbound_subject,
                    json.dumps({"kind": "message", "conn_id": conn_id, "raw": raw_message}).encode(),
                )
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            connections.pop(conn_id, None)
            server_logger.connection_closed(conn_id, remote)
            await nats_client.publish(
                inbound_subject,
                json.dumps({"kind": "disconnected", "conn_id": conn_id, "remote": remote}).encode(),
            )

    heartbeat_key = f"shard:{shard_id}:heartbeat"

    async def shard_watchdog_loop():
        """
        Detect a hard-killed Shard process via its Redis heartbeat key
        expiring (see shard/main.py), and tell every client connected to
        *this* Gateway — since Phase 2 has exactly one Shard, "the shard is
        gone" means "every one of this gateway's in-progress games is gone."
        This is the observable, client-visible signal for
        Server_Design.md §1 Q4 / §5's "aborted" outcome that Phase 2's own
        DoD requires end-to-end, not just as a server-side log line.
        """
        shard_was_up = None  # unknown until the first observed heartbeat
        try:
            while True:
                await asyncio.sleep(1.0)
                shard_is_up = bool(redis_client.exists(heartbeat_key))
                if shard_was_up is True and shard_is_up is False:
                    raw_logger.warning("shard_unavailable shard_id=%s", shard_id)
                    err = Envelope(
                        type=MessageType.ERROR,
                        payload=ErrorPayload(reason="shard_unavailable").model_dump(),
                    ).to_json()
                    for conn_id, ws in list(connections.items()):
                        try:
                            await ws.send(err)
                        except Exception:
                            pass
                shard_was_up = shard_is_up
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
