"""
game_handoff.py — Phase 3 of .github/Server_Design_Implementation_Plan.md.

When a Shard's own MatchmakingService/RoomService wins the race to pair
two players (or fill a room) but the Game Allocator picks a *different*
shard as the least-loaded place to actually run the game, this module is
the hand-off: publish a "create_game" event to the chosen shard's NATS
inbound subject instead of constructing the GameSession locally.

`finalize_local_game` is the shared "actually build it" logic used both by
the shard that keeps a game for itself (no hand-off needed) and by the
target shard that receives a "create_game" event from another shard's
Matchmaker/RoomService — so there is exactly one code path that ever
constructs and starts a GameSession, matching-flow or room-flow, local or
handed-off.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, PlayMatchFoundPayload
from server.domain.player import Player


def player_to_dict(player: Player) -> dict:
    return {
        "user_id": player.user_id,
        "username": player.username,
        "elo": player.elo,
        "conn_id": player.conn_id,
        "session_token": player.session_token,
    }


def player_from_dict(d: dict) -> Player:
    return Player(**d)


async def finalize_local_game(
    factory: Any,              # GameSessionFactory
    game_handler: Any,         # GameHandler
    hub: Any,                  # AbstractConnectionDirectory
    white: Player,
    black: Player,
    game_id: str,
    room_id: Optional[str] = None,
    viewer_conn_ids: Optional[List[str]] = None,
    send_match_found: bool = False,
    logger: Optional[logging.Logger] = None,
    redis_client: Optional[Any] = None,
    own_shard_id: Optional[str] = None,
):
    """
    Construct, register, and start a GameSession on *this* process. The one
    and only place that happens, whether the game originated in this
    process's own matchmaking/room flow or arrived as a hand-off from
    another Shard's Game Allocator decision.

    If redis_client/own_shard_id are given (Phase 3, multi-shard), also
    records "conn:{conn_id}:shard" for both players so the Gateway fleet
    knows where to route their future MOVE/RESIGN messages — the whole
    reason placement can move a game off the shard that won the
    pairing/room-fill race in the first place.
    """
    session = factory.create(white=white, black=black, room_id=room_id, game_id=game_id)
    game_handler.register_session(session)

    if redis_client is not None and own_shard_id is not None:
        for conn_id in (white.conn_id, black.conn_id):
            redis_client.set(f"conn:{conn_id}:shard", own_shard_id, ex=86400)

    for conn_id in (viewer_conn_ids or []):
        session.add_viewer(conn_id)

    if send_match_found:
        for player, color in ((white, "w"), (black, "b")):
            opponent = black if color == "w" else white
            env = Envelope(
                type=MessageType.PLAY_MATCH_FOUND,
                payload=PlayMatchFoundPayload(
                    opponent=opponent.username, color=color, game_id=session.game_id,
                ).model_dump(),
            )
            await hub.send(player.conn_id, env.to_json())

    await session.start()
    if logger is not None:
        logger.info("game_finalized game_id=%s handoff=%s", game_id, room_id is not None or send_match_found)
    return session


async def publish_create_game(
    nats_client: Any,
    target_shard_id: str,
    white: Player,
    black: Player,
    game_id: str,
    room_id: Optional[str] = None,
    viewer_conn_ids: Optional[List[str]] = None,
    send_match_found: bool = False,
) -> None:
    """Hand off game creation to a different Shard process over NATS."""
    payload = {
        "kind": "create_game",
        "white": player_to_dict(white),
        "black": player_to_dict(black),
        "game_id": game_id,
        "room_id": room_id,
        "viewer_conn_ids": viewer_conn_ids or [],
        "send_match_found": send_match_found,
    }
    await nats_client.publish(f"shard.{target_shard_id}.inbound", json.dumps(payload).encode())
