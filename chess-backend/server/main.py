"""
main.py — server entrypoint.

Wires up the full DI container (auth, rating, matchmaking, rooms, game
sessions, disconnect handling) and runs the WebSocket server.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import websockets

from server.config_loader import load_settings
from server.connection_hub import ConnectionHub
from server.directories.redis_backed import (
    RedisConnectionDirectory,
    RedisMatchQueue,
    RedisRoomRegistry,
)
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


async def serve(settings=None, router: MessageRouter = None, hub: ConnectionHub = None,
                server_logger=None):
    """
    Main server coroutine. Creates all objects and starts listening.

    Parameters are injectable for testing.
    """
    if settings is None:
        settings = load_settings()

    if server_logger is None:
        server_logger = build_server_logger(settings)

    raw_logger = logging.getLogger("chess.server")

    match_queue = None
    room_registry = None
    if settings.backend.redis_enabled:
        import redis as redis_lib

        redis_client = redis_lib.Redis.from_url(settings.backend.redis_url, decode_responses=True)
        if hub is None:
            hub = RedisConnectionDirectory(
                redis_client,
                key_prefix=settings.backend.session_key_prefix,
                ttl_seconds=settings.auth.session_token_ttl_seconds,
                logger=raw_logger,
            )
        match_queue = RedisMatchQueue(redis_client, key=settings.backend.match_queue_key)
        room_registry = RedisRoomRegistry(
            redis_client,
            key_prefix=settings.backend.room_key_prefix,
            ttl_seconds=settings.auth.session_token_ttl_seconds,
        )
        raw_logger.info("backend_redis_enabled url=%s", settings.backend.redis_url)

    if hub is None:
        hub = ConnectionHub(logger=raw_logger)

    db_conn = get_connection(settings.server.db_path)
    user_repo = UserRepository(db_conn)
    game_repo = GameRepository(db_conn)

    auth_svc = AuthService(repo=user_repo, settings=settings, logger=raw_logger)
    rating_svc = RatingService(settings)

    game_handler = GameHandler(hub=hub, auth_service=auth_svc, logger=raw_logger)
    factory = GameSessionFactory(
        hub=hub, user_repo=user_repo, game_repo=game_repo,
        rating_service=rating_svc, settings=settings, logger=raw_logger,
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

    if router is None:
        router = MessageRouter(hub=hub, logger=raw_logger)

    auth_handler = AuthHandler(auth_service=auth_svc, hub=hub, logger=raw_logger)
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

    async def connection_handler(websocket):
        conn_id = str(uuid.uuid4())
        remote = str(websocket.remote_address)
        hub.register(conn_id, websocket)
        server_logger.connection_opened(conn_id, remote)

        try:
            async for raw_message in websocket:
                await router.route(conn_id, raw_message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            session = game_handler.get_session_by_conn(conn_id)
            hub.unregister(conn_id)
            matchmaking.dequeue(conn_id)
            server_logger.connection_closed(conn_id, remote)
            if session is not None:
                asyncio.ensure_future(session.handle_disconnect(conn_id))

    host = settings.server.host
    port = settings.server.port
    raw_logger.info("Server starting on %s:%s", host, port)

    try:
        async with websockets.serve(connection_handler, host, port):
            await asyncio.Future()  # run forever
    finally:
        matchmaking.stop()


if __name__ == "__main__":
    asyncio.run(serve())
