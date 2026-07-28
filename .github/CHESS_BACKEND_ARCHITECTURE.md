# Chess Backend Architecture

This document describes everything under `chess-backend/`: the networked
server, the SQLite-backed persistence layer, the wire protocol, and both
clients (terminal and graphical). It reflects the code as built, not the
original spec — see `chess-backend-implementation-plan.md` for the
pre-implementation design document this was built from.

## Purpose

`chess-backend/` adds a server-side backend to the existing local chess
project (`engine/`, `ui/`): login (SQLite-backed), 2-player games, ELO
rating, matchmaking ("Play"), rooms (create/join/spectate), disconnect →
auto-resign, and full client+server logging. The existing chess
move-generation engine is treated as a black box and wrapped, never
reimplemented.

## High-Level Architecture

```
                    ┌───────────────────────────┐   ┌───────────────────────────┐
                    │   Terminal client (CLI)     │   │   Graphical client (GUI)   │
                    │   client/main.py             │   │   client/gui_main.py       │
                    │   ShellUI + screens/*         │   │   App + gui/scenes/*       │
                    │   ClientSession (ws conn)      │   │   NetworkClient (ws conn,  │
                    │                                 │   │   own asyncio thread)      │
                    └────────────────┬────────────┘   └────────────────┬────────────┘
                                     │ WebSocket (JSON envelopes, common/protocol/)
┌────────────────────────────────────┼──────────────────────────────────────────────┐
│ Server (server/main.py)             ▼                                               │
│  ConnectionHub ──▶ MessageRouter ──▶ Handlers (auth/play/room/game/system)          │
│                                        │                                             │
│   AuthService   MatchmakingService   RoomService                                     │
│        │                │                 │                                          │
│        ▼                ▼                 ▼                                          │
│   UserRepository    GameSessionFactory ──▶ GameSession (per game)                    │
│   (SQLite)               │                  - wraps engine.GameEngine (real-time)     │
│                           │                  - DisconnectMonitor (20s countdown)      │
│                           │                  - RatingService (ELO update on end)      │
│                           ▼                                                          │
│                      GameRepository (SQLite) — audit trail                            │
│  ServerLogger — injected into every service, JSON lines to logs/server.log            │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

Key decision carried through the whole codebase: `MatchmakingService` and
`RoomService` are both just *ways of pairing two connections*. Once a
pairing is decided, both hand off to the same `GameSessionFactory` → the
same `GameSession` class runs the actual game, disconnect timer, and
rating update. Neither "Play" nor "Room" duplicates game logic.

## Project Structure

```
chess-backend/
├── config/default.yaml          # every tunable (rating, matchmaking, game, room, auth, server, logging)
├── server/
│   ├── main.py                   # entrypoint — wires the full DI container, runs the websocket server
│   ├── config_loader.py          # loads default.yaml into a typed, frozen Settings dataclass tree
│   ├── connection_hub.py         # conn_id ↔ websocket / session_token registry
│   ├── message_router.py         # decodes envelope JSON, dispatches by MessageType
│   ├── handlers/                 # one handler per message family → thin, calls into services
│   │   ├── auth_handler.py, play_handler.py, room_handler.py, game_handler.py, system_handler.py
│   ├── services/                 # business logic
│   │   ├── auth_service.py, rating_service.py, matchmaking_service.py, room_service.py
│   │   ├── game_session.py, game_session_factory.py, disconnect_monitor.py
│   ├── repositories/             # only place SQL lives
│   │   ├── base_repository.py (interface + value objects), user_repository.py, game_repository.py
│   ├── domain/                   # pure value objects/enums, no I/O
│   │   ├── player.py, room.py, elo.py, enums.py
│   ├── db/                       # schema.sql, database.py (connection + schema init)
│   └── logging_/                 # logger_factory.py (JSON line formatter), server_logger.py
├── client/
│   ├── main.py                   # terminal entrypoint
│   ├── shell_ui.py, client_session.py
│   ├── screens/                  # text-menu screens (home/login/play/room/game)
│   ├── gui_main.py               # graphical entrypoint
│   ├── gui/                      # cv2-based graphical client (see below)
│   └── logging_/client_logger.py
├── common/
│   └── protocol/                 # message_types.py (enum), schemas.py (pydantic payloads)
└── tests/
    ├── unit/, integration/, e2e/
```

## Server Layer

### `server/main.py` — entrypoint
`serve()` builds the whole dependency-injection graph (settings → repos →
services → handlers → router), registers a handler per `MessageType`,
starts `MatchmakingService`'s background pairing loop, and runs
`websockets.serve(...)`. On each new connection it registers it in
`ConnectionHub`, logs `connection_opened`, and on close (or exception)
looks up any active `GameSession` for that connection and calls
`handle_disconnect` on it. Run as `python -m server.main` from
`chess-backend/` (needs the package import context — running the bare
script file directly will fail).

### `server/connection_hub.py` — `ConnectionHub`
The only place that owns raw websocket objects. Maps `conn_id → websocket`
and `session_token ↔ conn_id`. On `unregister`, the token→conn mapping is
*deliberately kept* (only `conn_id→token` is dropped) so a `GAME_END`
broadcast by token can still find a reconnecting player before the
message is sent. `broadcast`/`broadcast_to_tokens` fan out concurrently
via `asyncio.gather`. Supports a disconnect-callback registry (unused by
`main.py` today — disconnects are detected inline in the connection
handler instead).

### `server/message_router.py` — `MessageRouter`
Parses raw JSON into an `Envelope`, looks up the registered handler for
`envelope.type`, and dispatches. Any parse failure, missing handler, or
handler exception gets turned into an `ERROR` envelope sent back to the
same connection — a client never gets silence on a malformed request.

### `server/handlers/*` — one per message family
Each handler validates its payload via the matching pydantic model
(catches `TypeError`/`ValidationError` → `invalid_payload` error),
validates the session token via `AuthService.validate_token`, and either
calls straight into a service or (for `auth_handler`) into `AuthService`
directly.

- **`auth_handler.py`** — `LOGIN`/`REGISTER` → `AuthService.login`/`register`.
- **`play_handler.py`** — `PLAY_REQUEST` enqueues into `MatchmakingService` and immediately acks `PLAY_SEARCHING`; `PLAY_CANCEL` dequeues.
- **`room_handler.py`** — `ROOM_CREATE`/`ROOM_JOIN` → `RoomService`; starts the game via `RoomService.start_game_if_ready` once the second slot fills.
- **`game_handler.py`** — `MOVE`/`RESIGN` → looks up the active `GameSession` for the connection (`conn_id → game_id` map, populated by `register_session`, called by both matchmaking and room paths) and delegates. Owns the `game_id ↔ GameSession` and `conn_id ↔ game_id` registries — the only place these exist.
- **`system_handler.py`** — `PING` → `PONG`.

### `server/services/*`

- **`auth_service.py`** — hashes with Argon2 (`argon2-cffi`), never logs
  passwords. Session tokens are an **instance-level** dict
  (`{token: (user_id, username, elo, expires_at)}`) with a TTL from
  config — deliberately not a module-level global (that was a bug, fixed:
  a shared global would leak session state across every `AuthService`
  instance in the process, including across unrelated test suites).
  `validate_token` is the single source of truth every handler calls to
  authenticate a request.
- **`rating_service.py`** — thin wrapper delegating to
  `domain/elo.py::calculate_both`; pure, easy to unit test in isolation.
- **`matchmaking_service.py`** — in-memory FIFO queue. A background
  `asyncio.Task` (`start_background_loop`) wakes every
  `matchmaking.poll_interval_seconds` and, each tick, greedily pairs
  entries within `±rating.match_range` ELO (first enqueued of a pair =
  White) and expires anyone past `matchmaking.queue_timeout_seconds`. On a
  pair it calls `GameSessionFactory.create(...)` then `session.start()` —
  it never touches `GameSession` internals.
- **`room_service.py`** — `RoomIdGenerator` builds IDs from
  `room.id_length`/`room.id_alphabet` (no hardcoded charset). Role
  assignment: 1st joiner (creator) = White, 2nd = Black (triggers game
  start), 3rd+ = Viewer. A viewer joining *after* the game has already
  started is attached directly to the existing `GameSession` via
  `add_viewer` — this used to spin up a duplicate session with a reset
  board; fixed.
- **`game_session.py`** — the biggest service; one instance per active
  game. See "GameSession internals" below.
- **`game_session_factory.py`** — the *only* place that constructs a
  `GameSession`; both matchmaking and rooms call it. This is the DRY seam
  that keeps the two entry points from diverging.
- **`disconnect_monitor.py`** — a standalone countdown: emits `on_tick`
  once per `game.countdown_tick_seconds` and fires `on_timeout` once
  `game.disconnect_grace_seconds` elapses, unless `cancel()`ed first
  (reconnect). `cancel()` is a no-op once the monitor has already fired —
  without that guard, `GameSession.end_game`'s own monitor-cleanup loop
  would self-cancel the monitor whose `on_timeout` callback is *currently
  running* that same `end_game`, throwing a stray `CancelledError` into
  the in-flight `GAME_END` broadcast and silently dropping it (this was
  the original bug this whole project started from — see the disconnect
  e2e tests for the regression coverage).

### `GameSession` internals (`server/services/game_session.py`)

Wraps `engine.game_engine.GameEngine` + `RealTimeArbiter` + `RuleEngine`
(the existing chess project's real-time move engine — pieces travel over
real wall-clock time and have a post-arrival cooldown; there is **no
turn concept** at the engine level).

- **`apply_move(conn_id, src, dst)`** — before delegating to the engine,
  checks that the piece at `src` belongs to the requesting player's
  color (`engine.get_piece_at(src).color`). Without this check, since the
  engine has no turn enforcement, either player could move the
  opponent's pieces over the wire — this was a real bug, fixed, covered
  by a regression test in both `test_phase4_game_session.py` and
  `test_phase4_game_e2e.py`.
- **Real-time clock** — `apply_move` calls a private `_tick_engine()`
  (before *and* after validating the move) which advances the engine's
  internal clock by the actual wall-clock milliseconds elapsed since the
  last tick (tracked via `time.monotonic()`). Earlier this ticked with a
  hardcoded `0`, which meant the engine's simulated clock never advanced
  at all — a piece's in-flight motion could never complete, so the piece
  became permanently stuck "empty" after its very first move. Fixed;
  regression test `test_same_piece_can_move_again_after_real_time_passes`
  actually waits out a real cooldown to prove it.
- **`start()` / `apply_move()` broadcast payloads** — both include the
  full board snapshot (`board`, `scores`, `game_over`, `winner`, computed
  via `_snapshot_wire_fields()`), not just the move delta. This is what
  lets a client render the board without maintaining its own copy of the
  rules — see "Wire protocol" below.
- **`handle_disconnect`/`handle_reconnect`** — starts/cancels a
  `DisconnectMonitor` per connection; on timeout, ends the game with
  `EndReason.DISCONNECT_TIMEOUT` in the opponent's favor.
- **`end_game(result, reason)`** — idempotent (guarded by `self._ended`),
  updates ELO via `RatingService`, persists via `GameRepository`, and
  broadcasts `GAME_END` to both players *by session token* (survives a
  stale `conn_id` after a reconnect) plus any viewers by `conn_id`.
- **`get_state()`** — returns a frozen `BoardStateDTO`; no caller ever
  gets a reference to the engine's live, mutable internals.

### `server/repositories/*`
`UserRepository`/`GameRepository` are the only classes touching SQL; both
implement the `Abstract*Repository` interfaces from `base_repository.py`
so tests can swap in fakes. `schema.sql` defines `users`, `games`, and
`moves` tables (the `moves` table — a per-ply move log — exists in the
schema but nothing currently writes to it; the plan marks it optional).

### `server/logging_/*`
`logger_factory.py::build_logger` builds a `RotatingFileHandler` +
console handler pair with a `JsonFormatter` (one JSON object per line,
merging any `extra={}` fields). `server_logger.py::ServerLogger` defines
one named method per §11 event category (connection, auth, matchmaking,
room, move, disconnect, rating, error) — in practice most call sites use
the plain injected stdlib `logging.Logger` directly with a formatted
message string rather than these category methods (only
`connection_opened`/`connection_closed` in `main.py` use `ServerLogger`
itself); every category is still emitted and covered by
`caplog`-based e2e assertions, just via the raw-logger path.

## Client Layer

Two independent front ends talk to the same server over the same
protocol; either can be run against it interchangeably.

### Terminal client (`client/main.py`)
`ClientSession` (`client/client_session.py`) owns the websocket: framing,
`request()`/`send()`, and `request_id`-correlated request/response
matching, plus a `receive_loop()` that dispatches unmatched incoming
messages to handlers registered via `on(msg_type, handler)`. `ShellUI`
drives a simple `input()`-based menu (`Login/Register/Play/Room/Quit`,
`client/screens/home_screen.py`); each flow is a small screen class
(`login_screen.py`, `play_screen.py`, `room_screen.py`, `game_screen.py`).
`game_screen.py` renders the board as plain text via the existing
project's `ui.rendering.renderers.TextRenderer`, fed the `board`/`scores`/
`game_over`/`winner` fields now included in `GAME_START`/`MOVE_BROADCAST`.

### Graphical client (`client/gui_main.py`, `client/gui/`)
Reuses the existing local chess GUI's rendering stack
(`ui/rendering`, `ui/composition/container.py`, `ui/interaction`,
`ui/animation`, `ui/ui_components`, `ui/resources/asset_loader.py`) —
sprites, slide animations, sound, the two-panel HUD (player name, PTS,
move list) — completely unmodified, driven by the network instead of a
local engine.

```
client/gui/
├── network_client.py   # runs ClientSession on its own asyncio event loop,
│                        # on a background daemon thread (cv2's blocking window
│                        # loop and asyncio can't share one thread); exposes
│                        # request()/send()/poll_events() to the main thread
├── widgets.py           # Button, TextField — hand-rolled cv2 draw+hit-test
│                        # widgets (cv2 has no native text input)
├── app.py                # one cv2 window; scene loop (duck-typed scenes:
│                        # on_click/on_key/update/render, return (name, data)
│                        # to switch scenes)
└── scenes/
    ├── home_scene.py, auth_scene.py, play_scene.py, room_scene.py
    └── game_scene.py     # the networked board — see below
```

**Design: server-authoritative replay, no client-side prediction.**
`game_scene.py` builds a *local mirror* `GameEngine`/`GameFacade` via the
same `ui.composition.container.build_container()` the offline game uses,
purely for rendering/animation/sound. Clicking a piece **never mutates
that mirror directly** — `Controller` (reused unmodified) is given a
`NetworkMoveRequester` adapter instead of the raw facade: its read
methods (`get_piece_at`/`is_on_cooldown`/`is_game_over`) proxy to the
mirror for responsive click feedback, but `request_move` only sends a
`MOVE` envelope to the server and returns the server's accept/reject
result — it does not touch the mirror. The mirror is mutated **only**
when the server's own `MOVE_BROADCAST` for that move comes back (sent to
*both* players for every accepted move, including the mover's own) and
gets replayed through the real `facade.request_move(...)`. This is what
lets the entire existing animation/sound/HUD event-subscriber stack
(`MovesFeed`, `ScorePanel`, `Banner`, `SoundPlayer`,
`GameAnimationController`) work completely unchanged against a networked
opponent — there is no local/server state to reconcile because the local
state is never allowed to diverge from what the server confirmed.

Two bugs found and fixed while building this that are worth knowing
about if you touch `game_scene.py` again:
- **HUD panels invisible**: `board.png` has an alpha channel. `HudRenderer`
  pads its sidebars with alpha=0 before drawing panel content on top via
  `fill_rect`/`put_text` (which never touch the alpha channel), so the
  sidebar pixels stayed alpha=0. `game_scene.py` used to composite the
  final frame onto a larger canvas (to make room for a bottom control
  bar) via `Img.draw_on`, which *does* alpha-blend — so it silently
  discarded the whole sidebar, showing the destination canvas's plain
  background instead. Fixed by dropping the alpha channel (`cv2.cvtColor
  BGRA→BGR`, a straight channel-drop, not a blend) before padding with
  `cv2.copyMakeBorder`, matching how `ui/runtime/game_loop.py` already
  avoids the issue (it hands its renderer's output straight to
  `Img.show()`, which does the same BGRA→BGR drop, never a blend).
- **HUD labels generic**: `HudRenderer` defaults to literal `"WHITE"`/
  `"BLACK"` panel labels. `game_scene.py` now passes a custom `hud_config`
  (`dataclasses.replace(DEFAULT_APP_CONFIG.hud, white_label=..., black_label=...)`)
  built from the real usernames in the `GAME_START` payload — `HudRenderer`
  already supported this as a per-instance override, so no `ui/` changes
  needed.

Run with `python client/gui_main.py` from `chess-backend/` (needs the
server running first).

## Wire Protocol (`common/protocol/`)

Every message, both directions, is one JSON envelope:
```json
{"type": "MOVE", "request_id": "uuid-v4", "payload": {...}}
```
`message_types.py::MessageType` is the single enum source of truth for
every `type` string used anywhere in the codebase — grep confirms no
handler or service uses a raw message-type string literal.
`schemas.py` has one pydantic model per payload, validated on receipt.
Notably, `GameStartPayload` and `MoveBroadcastPayload` both carry
`board: list[list[str]]`, `scores: dict[str,int]`, `game_over: bool`,
`winner: Optional[str]` — the full board snapshot, not just a move
delta — specifically so a client (either one) can render the board
without independently re-deriving game state.

## Configuration (`config/default.yaml` + `server/config_loader.py`)

Every tunable named in the original spec lives here and nowhere else:
`rating.{starting_elo,k_factor,match_range}`,
`matchmaking.{queue_timeout_seconds,poll_interval_seconds}`,
`game.{disconnect_grace_seconds,countdown_tick_seconds}`,
`room.{id_length,id_alphabet}`,
`auth.{password_hash_scheme,min_password_length,session_token_ttl_seconds}`,
`server.{host,port,db_path}`, `logging.{server_log_path,client_log_path,level,rotate_max_bytes,rotate_backups}`.
`load_settings()` reads the YAML once into a frozen `Settings` dataclass
tree, injected into every service at construction — nothing re-reads the
file on a hot path. (`auth.password_hash_scheme` is loaded but not
actually branched on — `AuthService` always uses Argon2; the config field
is currently decorative.)

`server.host` defaults to `"0.0.0.0"` (bind-all); both clients translate
that to `127.0.0.1` for their own outbound connection, since `0.0.0.0` is
not a connectable address on Windows.

## Key Flows

- **Login/Register** — client sends `LOGIN`/`REGISTER` → `AuthService` →
  `LOGIN_OK{session_token,elo}` or `*_ERROR{reason}`. Logged on both
  sides; the password is never logged or echoed back.
- **Play (matchmaking)** — `PLAY_REQUEST` → `PLAY_SEARCHING` ack →
  background loop pairs within the ELO band or times out →
  `PLAY_MATCH_FOUND{opponent,color,game_id}` then `GAME_START` to both.
- **Room** — `ROOM_CREATE` → `ROOM_CREATED{room_id}`; second client
  `ROOM_JOIN{room_id}` → `ROOM_ROLE_ASSIGNED{role:black}` + `GAME_START`
  to both; further joiners get `role:viewer` and are subscribed to
  broadcasts with no move rights.
- **Disconnect → auto-resign** — socket close detected in
  `server/main.py`'s connection handler → `GameSession.handle_disconnect`
  starts a 20s `DisconnectMonitor` → `DISCONNECT_COUNTDOWN_TICK` broadcast
  each second to the opponent (and viewers) → reconnect within the window
  cancels it, else `end_game(reason=disconnect_timeout)`.
- **Rating** — computed once per game end via `RatingService` →
  `UserRepository.update_elo` + `GameRepository.record_game` for
  before/after auditability.

## Test Layout (`tests/`)

- **`tests/unit/`** — one file per phase (`test_phase1_foundations.py` …
  `test_phase7_disconnect.py`). Pure logic: config loading, envelope
  round-trip, `ConnectionHub`, `elo.py` (hand-computed scenarios),
  `AuthService`/`UserRepository` (fakes + a temp SQLite file),
  `MatchmakingService` pairing/timeout rules, `RoomService`/
  `RoomIdGenerator`, `DisconnectMonitor` (fake clock), `GameSession` move
  handling. Both loggers (`test_loggers.py`) and the entire GUI client are
  covered here too, since they're pure logic given a fake network/session:
  `test_gui_widgets.py`, one file per scene
  (`test_gui_{home,auth,play,room,game}_scene.py`),
  `test_gui_network_move_requester.py`, `test_gui_app.py` (scene dispatch
  only — `App.run()` itself opens a real window, not testable headlessly),
  and the terminal client's own screens/shell (`test_cli_screens.py`,
  `test_cli_game_screen.py`, `test_shell_ui.py`).
- **`tests/integration/`** — `test_phase1_ping_pong.py`: router + hub
  wiring over a real socket, no service logic yet.
- **`tests/e2e/`** — real `websockets.serve()` test servers on dedicated
  ports (`182xx` — check the top of each file before picking a new one)
  driving the full stack for auth, game (incl. the move-ownership
  regression), matchmaking, rooms, disconnect (incl. the `GAME_END`
  regression and per-category `caplog` log assertions), and
  `test_gui_network_client.py` (drives the real `NetworkClient` — start/
  request/poll_events — across its background thread against a real
  server; note it must offload those *blocking* calls via
  `loop.run_in_executor` since the test's own server shares the test's
  event loop).

Run everything: `cd chess-backend && python -m pytest -q` (296 tests,
all green as of this writing; `--cov=server --cov=client --cov=common`
reports 88% overall statement coverage).

## Running It

```
# terminal 1 — server (stays running)
cd chess-backend
python -m server.main

# terminal 2 — a player (terminal client)
cd chess-backend
python client/main.py

# terminal 2/3 — a player (graphical client)
cd chess-backend
python client/gui_main.py
```
Both clients speak the same protocol to the same server and can be mixed
(one terminal player, one graphical player, same game).
