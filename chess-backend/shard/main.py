"""
shard/main.py — Phase 2 of .github/Server_Design_Implementation_Plan.md.

Runs the exact same DI wiring as server/main.py (auth, rating, matchmaking,
rooms, game sessions, disconnect handling) — the *business logic* of the
monolith is completely unchanged. The only two differences from
server/main.py:

1. No websockets.serve() here — a Shard never talks to a client socket
   directly. Instead it subscribes to its own "shard.{shard_id}.inbound"
   NATS subject for connection lifecycle events and routed messages.
2. hub is a NatsPublishingConnectionDirectory instead of ConnectionHub/
   RedisConnectionDirectory — GameSession's hub.send()/broadcast() publish
   an outbound envelope to NATS instead of writing to a socket. Every
   service that depends on hub (MessageRouter, handlers, GameSession) is
   otherwise byte-for-byte what server/main.py already wires up.

Run: python -m shard.main  (needs Redis + NATS reachable — see docker-compose.yml)
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging

import nats
import redis as redis_lib

from server.allocator import GameAllocator
from server.config_loader import load_settings
from server.directories.nats_backed import NatsPublishingConnectionDirectory
from server.directories.redis_backed import RedisMatchQueue, RedisRoomRegistry
from server.message_router import MessageRouter
from server.handlers.system_handler import make_ping_handler
from server.handlers.auth_handler import AuthHandler
from server.handlers.game_handler import GameHandler
from server.handlers.play_handler import PlayHandler
from server.handlers.room_handler import RoomHandler
from server.services.auth_service import AuthService
from server.services.rating_service import RatingService
from server.services.matchmaking_service import MatchmakingService
from server.services.room_service import RoomService, RoomIdGenerator
from server.services.game_session_factory import GameSessionFactory
from server.repositories.user_repository import UserRepository
from server.repositories.game_repository import GameRepository
from server.db.database import get_connection
from server.logging_.server_logger import build_server_logger
from common.protocol.message_types import MessageType


async def serve(settings=None, server_logger=None, nats_client=None, redis_client=None):
    """
    Main shard coroutine. Wires the DI container and subscribes to this
    shard's NATS inbound subject. Runs until cancelled.
    """
    if settings is None:
        settings = load_settings()
        settings = dataclasses.replace(
            settings,
            logging=dataclasses.replace(
                settings.logging,
                server_log_path=settings.logging.server_log_path.replace(".log", "-shard.log"),
            ),
        )

    if server_logger is None:
        server_logger = build_server_logger(settings)

    # Same logger name build_server_logger() configures (handlers attached
    # to "chess.server", exactly like server/main.py) so these .info() calls
    # actually reach the shard's own log file instead of an unconfigured logger.
    raw_logger = logging.getLogger("chess.server")
    shard_id = settings.backend.shard_id

    if nats_client is None:
        nats_client = await nats.connect(settings.backend.nats_url)
    if redis_client is None:
        redis_client = redis_lib.Redis.from_url(settings.backend.redis_url, decode_responses=True)

    hub = NatsPublishingConnectionDirectory(
        nats_client, redis_client, shard_id=shard_id,
        session_key_prefix=settings.backend.session_key_prefix,
        ttl_seconds=settings.auth.session_token_ttl_seconds,
        logger=raw_logger,
    )
    match_queue = RedisMatchQueue(redis_client, key=settings.backend.match_queue_key)
    room_registry = RedisRoomRegistry(
        redis_client, key_prefix=settings.backend.room_key_prefix,
        ttl_seconds=settings.auth.session_token_ttl_seconds,
    )
    allocator = GameAllocator(redis_client, shard_id=shard_id)

    db_conn = get_connection(settings.server.db_path)
    user_repo = UserRepository(db_conn)
    game_repo = GameRepository(db_conn)

    auth_svc = AuthService(repo=user_repo, settings=settings, logger=raw_logger)
    rating_svc = RatingService(settings)

    game_handler = GameHandler(hub=hub, auth_service=auth_svc, logger=raw_logger)
    factory = GameSessionFactory(
        hub=hub, user_repo=user_repo, game_repo=game_repo,
        rating_service=rating_svc, settings=settings, logger=raw_logger,
        allocator=allocator,
    )

    matchmaking = MatchmakingService(
        settings=settings, factory=factory, hub=hub,
        game_handler=game_handler, logger=raw_logger, queue=match_queue,
    )
    room_id_gen = RoomIdGenerator(settings)
    room_svc = RoomService(
        settings=settings, factory=factory, hub=hub,
        game_handler=game_handler, id_generator=room_id_gen, logger=raw_logger,
        registry=room_registry,
    )

    router = MessageRouter(hub=hub, logger=raw_logger)
    auth_handler = AuthHandler(auth_service=auth_svc, hub=hub, logger=raw_logger, game_handler=game_handler)
    play_handler = PlayHandler(
        matchmaking=matchmaking, auth_service=auth_svc, user_repo=user_repo,
        hub=hub, logger=raw_logger,
    )
    room_handler = RoomHandler(
        room_service=room_svc, auth_service=auth_svc, user_repo=user_repo,
        hub=hub, logger=raw_logger,
    )

    router.register(MessageType.PING, make_ping_handler(hub, raw_logger))
    router.register(MessageType.LOGIN, auth_handler.make_login_handler())
    router.register(MessageType.REGISTER, auth_handler.make_register_handler())
    router.register(MessageType.PLAY_REQUEST, play_handler.make_play_request_handler())
    router.register(MessageType.PLAY_CANCEL, play_handler.make_play_cancel_handler())
    router.register(MessageType.ROOM_CREATE, room_handler.make_room_create_handler())
    router.register(MessageType.ROOM_JOIN, room_handler.make_room_join_handler())
    router.register(MessageType.MOVE, game_handler.make_move_handler())
    router.register(MessageType.RESIGN, game_handler.make_resign_handler())

    matchmaking.start_background_loop()

    inbound_subject = f"shard.{shard_id}.inbound"

    async def on_inbound(msg):
        try:
            event = json.loads(msg.data.decode())
        except Exception:
            raw_logger.warning("shard_inbound_decode_error subject=%s", msg.subject)
            return

        conn_id = event.get("conn_id")
        kind = event.get("kind")

        if kind == "connected":
            hub.register(conn_id)
            server_logger.connection_opened(conn_id, event.get("remote", ""))
        elif kind == "message":
            await router.route(conn_id, event["raw"])
        elif kind == "disconnected":
            session = game_handler.get_session_by_conn(conn_id)
            hub.unregister(conn_id)
            matchmaking.dequeue(conn_id)
            server_logger.connection_closed(conn_id, event.get("remote", ""))
            if session is not None:
                asyncio.ensure_future(session.handle_disconnect(conn_id))
        else:
            raw_logger.warning("shard_inbound_unknown_kind=%s", kind)

    subscription = await nats_client.subscribe(inbound_subject, cb=on_inbound)
    raw_logger.info("shard_started shard_id=%s subject=%s", shard_id, inbound_subject)

    heartbeat_key = f"shard:{shard_id}:heartbeat"

    async def heartbeat_loop():
        # A dead-man's switch: SET ... EX so a killed (not gracefully
        # stopped) shard process's heartbeat key simply expires on its own —
        # the Gateway doesn't need clock comparison, just key existence.
        try:
            while True:
                redis_client.set(heartbeat_key, "1", ex=5)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    try:
        await asyncio.Future()  # run forever
    finally:
        matchmaking.stop()
        heartbeat_task.cancel()
        await subscription.unsubscribe()


if __name__ == "__main__":
    asyncio.run(serve())
