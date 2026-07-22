# Chess Backend — Implementation Plan

**Scope:** Add a server-side backend (shell/CLI client, not GUI) to an existing chess project:
login (SQLite-backed), 2-player games, ELO rating, matchmaking (`Play`), rooms
(`Room` — create/join/spectate), disconnect → 20s countdown auto-resign, and
full client+server logging.

This document is the spec to hand to yourself (or an AI coding agent) *before*
writing code. Follow it phase by phase. Do not skip the "Definition of Done" /
test sections — they are what makes the later phases safe to build on.

---

## 1. Guiding Principles (non-negotiable)

| Principle | What it means here | How we enforce it |
|---|---|---|
| **DRY** | ELO math, validation, message framing, timers — each lives in exactly one function/class. | Shared `core/` and `common/` packages imported by both matchmaking and rooms; no copy-pasted logic between "Play" and "Room" flows — they both terminate in the same `GameSession`. |
| **SRP** | One reason to change per unit. | See §8 — every module below is named after the *one* thing it does. A `MatchmakingService` never touches the DB directly; a `RatingService` never touches sockets. |
| **No hardcoded constants/strings** | Rating band (±100), queue timeout (60s), disconnect grace (20s), starting ELO (1200), K-factor, message type strings, table/column names — all externalized. | `config/default.yaml` + `protocol/message_types.py` (enums) — see §6 and §9. |
| **Encapsulation** | No module reaches into another's internal dict/state by "knowing" a key. | Every stateful class exposes a narrow public API (methods/dataclasses); internal storage is name-mangled/private and never returned by reference — see §8.9. |
| **Testability** | Every module is unit-testable without a live socket or a real DB. | Dependency injection everywhere (see §13); SQLite repo behind an interface so it can be swapped for an in-memory fake in tests. |

---

## 2. Recommended Tech Stack

Pick one column consistently. Recommendation (marked ★) assumes Python because
it keeps client and server in one language, has `sqlite3` built in, and a
mature async websocket library — but the architecture in §4/§8 is stack-agnostic.

| Layer | ★ Recommended | Alternative |
|---|---|---|
| Server runtime | Python 3.11+, `asyncio` | Node.js + `ws`, or Go |
| Transport | WebSockets (`websockets` lib) | raw TCP sockets, or Socket.IO |
| DB | SQLite via `sqlite3` / `SQLAlchemy` (async) | same, ORM optional |
| Client | Python shell app (`prompt_toolkit` or plain `input()` loop) + `websockets` client | any CLI-capable language |
| Config | YAML (`config/*.yaml`) loaded via `pydantic-settings` | `.env` + `dynaconf` |
| Testing | `pytest`, `pytest-asyncio`, `freezegun` (for timers) | `unittest` |
| Logging | stdlib `logging` with JSON formatter, rotating file handler | `structlog` |

Why WebSockets over raw sockets: you need server-initiated pushes (opponent's
move, countdown ticks, "match found") — a request/response REST API would
force ugly polling for the countdown and matchmaking wait.

---

## 3. High-Level Architecture

```
                         ┌─────────────────────────┐
                         │        Client (CLI)       │
                         │  ─────────────────────    │
                         │  ShellUI  (menus, prompts) │
                         │  ClientSession (ws conn)   │
                         │  ClientLogger              │
                         └────────────┬───────────────┘
                                      │ WebSocket (JSON messages, see §9)
                                      │
┌─────────────────────────────────────┼─────────────────────────────────────┐
│ Server                               ▼                                     │
│  ┌───────────────┐   ┌──────────────────────┐   ┌────────────────────┐   │
│  │ ConnectionHub │──▶│ MessageRouter/Dispatcher│─▶│  Handlers (§8.2-.7)│   │
│  └───────────────┘   └──────────────────────┘   └─────────┬──────────┘   │
│                                                              │              │
│   ┌──────────────┐  ┌────────────────┐  ┌────────────────┐│              │
│   │ AuthService  │  │ MatchmakingSvc  │  │  RoomService    ││              │
│   └──────┬───────┘  └────────┬────────┘  └────────┬───────┘│              │
│          │                    │                     │        │              │
│          ▼                    ▼                     ▼        ▼              │
│   ┌──────────────┐  ┌──────────────────────────────────────────────┐      │
│   │ UserRepository│  │            GameSession (per game)             │      │
│   │ (SQLite)      │  │  - ChessEngine (existing project, reused)     │      │
│   └──────┬───────┘  │  - DisconnectMonitor (20s countdown)           │      │
│          │           │  - RatingService (ELO update on end)          │      │
│          ▼           └──────────────────────────────────────────────┘      │
│   ┌──────────────┐                                                          │
│   │  SQLite DB    │                                                        │
│   └──────────────┘                                                        │
│   ServerLogger (cross-cutting, injected into every service)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key architectural decision: **`MatchmakingService` and `RoomService` are both
just *ways of pairing two connections*.** Once a pairing is decided, both
hand off to the same `GameSessionFactory` → the same `GameSession` class runs
the actual game, disconnect timer, and rating update. This is what keeps
"Play" and "Room" from duplicating game logic (DRY).

---

## 4. Project Structure

```
chess-backend/
├── config/
│   ├── default.yaml            # all tunables (see §6)
│   └── logging.yaml
├── server/
│   ├── main.py                  # entrypoint, wires DI container, starts ConnectionHub
│   ├── connection_hub.py        # tracks live sockets ↔ session tokens (SRP: connection registry only)
│   ├── message_router.py        # decodes envelope, dispatches to handler by MessageType
│   ├── handlers/
│   │   ├── auth_handler.py      # login/register requests → AuthService
│   │   ├── play_handler.py      # "play" requests → MatchmakingService
│   │   ├── room_handler.py      # create/join/spectate → RoomService
│   │   └── game_handler.py      # move/resign requests → GameSession
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── rating_service.py
│   │   ├── matchmaking_service.py
│   │   ├── room_service.py
│   │   ├── game_session.py
│   │   ├── disconnect_monitor.py
│   │   └── game_session_factory.py
│   ├── repositories/
│   │   ├── base_repository.py   # interface, for test fakes
│   │   ├── user_repository.py
│   │   └── game_repository.py   # game history / audit (optional but recommended)
│   ├── db/
│   │   ├── schema.sql
│   │   └── migrations/
│   ├── domain/
│   │   ├── player.py             # value objects, no I/O
│   │   ├── room.py
│   │   ├── elo.py                # pure function(s), heavily unit-tested
│   │   └── enums.py              # GameResult, RoomRole, MatchStatus...
│   └── logging_/server_logger.py
├── client/
│   ├── main.py                   # shell entrypoint
│   ├── shell_ui.py                # menus, input prompts, rendering (SRP: presentation only)
│   ├── client_session.py         # owns the websocket, send/receive framing
│   ├── screens/
│   │   ├── home_screen.py
│   │   ├── login_screen.py
│   │   ├── play_screen.py         # shows searching state + countdown
│   │   ├── room_screen.py
│   │   └── game_screen.py         # renders board (reuses existing chess project's renderer)
│   └── logging_/client_logger.py
├── common/
│   ├── protocol/
│   │   ├── message_types.py       # enum of all message types (single source of truth)
│   │   └── schemas.py             # dataclasses/pydantic models for each message payload
│   └── constants.py                # re-exports config-loaded constants, nothing hardcoded
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── pyproject.toml
```

> Reuse: the *existing* chess move-generation/validation engine is treated as
> a black-box dependency imported by `GameSession`. Do not re-implement chess
> rules here — wrap it.

---

## 5. Configuration Management (no hardcoded values)

`config/default.yaml`:

```yaml
rating:
  starting_elo: 1200
  k_factor: 32
  match_range: 100          # ± ELO window for matchmaking

matchmaking:
  queue_timeout_seconds: 60
  poll_interval_seconds: 1

game:
  disconnect_grace_seconds: 20
  countdown_tick_seconds: 1

room:
  id_length: 6
  id_alphabet: "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no ambiguous chars

auth:
  password_hash_scheme: "argon2"      # or "bcrypt"
  min_password_length: 8
  session_token_ttl_seconds: 86400

server:
  host: "0.0.0.0"
  port: 8765
  db_path: "data/chess.db"

logging:
  server_log_path: "logs/server.log"
  client_log_path: "logs/client.log"
  level: "INFO"
  rotate_max_bytes: 5_000_000
  rotate_backups: 5
```

Rule: **any literal number/string used in business logic that isn't a pure
language keyword must resolve to a value read from this config** (loaded once
into a typed `Settings` object, injected into services — never re-read from
disk inside a hot path). Message-type strings live in `message_types.py` as an
`Enum`, not as raw strings scattered through the codebase — that's the DRY
mechanism for the protocol itself.

---

## 6. Data Model (SQLite)

```sql
-- users
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    elo           INTEGER NOT NULL DEFAULT 1200,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);

-- games: audit trail, also what rating_service reads to recompute if needed
CREATE TABLE games (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    white_user_id  INTEGER NOT NULL REFERENCES users(id),
    black_user_id  INTEGER NOT NULL REFERENCES users(id),
    result         TEXT NOT NULL,        -- 'white' | 'black' | 'draw' | 'aborted'
    end_reason     TEXT NOT NULL,        -- 'checkmate' | 'resign' | 'disconnect_timeout' | 'draw_agreement' | ...
    white_elo_before INTEGER NOT NULL,
    black_elo_before INTEGER NOT NULL,
    white_elo_after  INTEGER NOT NULL,
    black_elo_after  INTEGER NOT NULL,
    room_id        TEXT,                 -- NULL if matched via "Play"
    started_at     TEXT NOT NULL,
    ended_at       TEXT
);

-- optional: move log per game, useful for reconnection/replay/debugging
CREATE TABLE moves (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id    INTEGER NOT NULL REFERENCES games(id),
    ply_number INTEGER NOT NULL,
    move_san   TEXT NOT NULL,
    played_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_users_elo ON users(elo);
CREATE INDEX idx_games_users ON games(white_user_id, black_user_id);
```

`UserRepository` and `GameRepository` are the **only** classes that hold SQL.
Every other service calls repository methods (`get_by_username`,
`update_elo`, `record_game`) — never raw queries.

---

## 7. Communication Protocol

Single JSON envelope for every message, both directions:

```json
{
  "type": "PLAY_REQUEST",
  "request_id": "uuid-v4",
  "payload": { }
}
```

`type` values come from `common/protocol/message_types.py` (`Enum`), e.g.:

```
AUTH:      LOGIN, REGISTER, LOGIN_OK, LOGIN_ERROR
PLAY:      PLAY_REQUEST, PLAY_SEARCHING, PLAY_MATCH_FOUND, PLAY_TIMEOUT
ROOM:      ROOM_CREATE, ROOM_JOIN, ROOM_CREATED, ROOM_JOINED, ROOM_ERROR, ROOM_ROLE_ASSIGNED
GAME:      GAME_START, MOVE, MOVE_ACK, MOVE_BROADCAST, GAME_END,
           OPPONENT_DISCONNECTED, DISCONNECT_COUNTDOWN_TICK, AUTO_RESIGN
SYSTEM:    ERROR, PONG, PING
```

Every payload has a schema (pydantic model) in `schemas.py`, validated on
receipt — this is what stops one handler from silently depending on another
handler's undocumented dict shape (encapsulation, applies to wire format too).

---

## 8. Core Modules (SRP breakdown)

### 8.1 `AuthService`
- `register(username, password) -> UserId | AuthError`
- `login(username, password) -> SessionToken | AuthError`
- Does: hashing/verification, delegates persistence to `UserRepository`.
- Does **not**: know about sockets, rooms, or games.

### 8.2 `RatingService`
- `update_ratings(white_elo, black_elo, result) -> (new_white_elo, new_black_elo)`
- Pure function wrapping `domain/elo.py::calculate_elo`. No I/O — takes ints,
  returns ints. Persistence is the caller's (`GameSession`'s) job via
  `UserRepository`.
- This purity is what makes ELO trivially unit-testable (§13).

### 8.3 `MatchmakingService`
- Owns one in-memory priority structure: waiting players keyed by ELO.
- `enqueue(player) -> None`, `dequeue(player) -> None`
- Background loop (its own, single-purpose async task) that, on each tick:
  1. tries to pair waiting players within `config.rating.match_range`
  2. expires players who exceeded `config.matchmaking.queue_timeout_seconds`
- On a successful pair: calls `GameSessionFactory.create_from_match(...)` —
  does not construct `GameSession` itself (keeps it decoupled from game
  internals).
- Does **not** decide colors beyond "first enqueued = White" — see §11.2.

### 8.4 `RoomService`
- `create_room(owner) -> RoomId`
- `join_room(room_id, player) -> RoomRole` (`BLACK` or `VIEWER`, per §11.3 rule)
- Generates IDs via a small `RoomIdGenerator` (uses `config.room.id_length`
  and `id_alphabet` — no hardcoded charset in the service itself).
- Hands off to the same `GameSessionFactory` once 2 players are present.

### 8.5 `GameSessionFactory`
- The **only** place that constructs a `GameSession`. Both
  `MatchmakingService` and `RoomService` call it. This is the DRY seam that
  prevents divergent game-start logic between the two entry points.

### 8.6 `GameSession`
- One instance per active game. Owns: board state (delegates to existing
  chess engine), whose turn it is, connected sockets for White/Black/viewers.
- `apply_move(player, move) -> MoveResult`
- `handle_disconnect(player) -> None` → starts `DisconnectMonitor`
- `handle_reconnect(player) -> None` → cancels monitor if within grace period
- `end_game(result, reason) -> None` → calls `RatingService`, persists via
  `GameRepository`, broadcasts `GAME_END`.
- Broadcasts moves to viewers too (viewers are just read-only subscribers on
  the same `GameSession`).

### 8.7 `DisconnectMonitor`
- Single responsibility: run a 20-second countdown for exactly one
  disconnected player, emit a tick event once per second (for the client's
  countdown display), and fire an `on_timeout` callback if not cancelled.
- Implemented as its own class (not inline in `GameSession`) so it's
  independently unit-testable with a fake clock, and reusable if you ever add
  a "disconnect grace" to spectator reconnection or room ownership later.

### 8.8 `ConnectionHub`
- Maps `connection_id ↔ user_session`. Nothing else. Used by `GameSession`
  to push messages without knowing transport details.

### 8.9 Encapsulation rule of thumb
No class returns its internal storage by reference, and no class reaches into
another's internals:
- ❌ `matchmaking_service.waiting_players["by_elo"][1200]` accessed from a handler.
- ✅ `matchmaking_service.enqueue(player)` / `matchmaking_service.pop_expired()`.
- `GameSession` never exposes its raw board dict — it exposes `get_state() ->
  BoardStateDTO` (a read-only, purpose-built object), so nothing downstream
  can accidentally mutate state through a side door or start depending on an
  internal key name.

---

## 9. Client (Shell) Architecture

- `ShellUI` renders menus/prompts and reads stdin — **pure presentation**,
  no networking code.
- `ClientSession` owns the websocket connection, message send/receive,
  request/response correlation via `request_id`.
- Each `screens/*.py` is a small state machine driven by messages arriving
  from `ClientSession` (e.g. `PlayScreen` re-renders on every
  `PLAY_SEARCHING` tick and every `DISCONNECT_COUNTDOWN_TICK`).
- `ClientLogger` logs every outgoing/incoming message and user action to
  `config.logging.client_log_path`.

Home screen menu (text-based):
```
=== Chess ===
1) Login
2) Register
3) Play
4) Room
5) Quit
```
After login, `Play`/`Room` become active; before login they prompt to log in
first (no duplicated auth-check logic — a single `require_login()` guard used
by both).

---

## 10. Key Flows

### 10.1 Login
1. Client → `LOGIN {username, password}`
2. `AuthService.login` verifies hash via `UserRepository.get_by_username`
3. Server → `LOGIN_OK {session_token, elo}` or `LOGIN_ERROR {reason}`
4. Both sides log the attempt (username, result, timestamp — **never the
   password**, hashed or not).

### 10.2 Play (matchmaking)
1. Client → `PLAY_REQUEST`
2. Server enqueues player in `MatchmakingService`, replies `PLAY_SEARCHING`
3. Client renders "Searching for opponent... (elapsed Xs)"
4. On match: both clients get `PLAY_MATCH_FOUND {opponent, color, game_id}`,
   then `GAME_START`
5. On 60s timeout: `PLAY_TIMEOUT` → client shows a popup/message
   ("Could not find an opponent") and returns to Home.

### 10.3 Room
1. Client → `ROOM_CREATE` → server generates ID via `RoomIdGenerator` →
   `ROOM_CREATED {room_id}` → client displays the ID at the top of screen.
2. Second client → `ROOM_JOIN {room_id}` → `RoomService.join_room` assigns
   `BLACK` → `ROOM_ROLE_ASSIGNED {role: BLACK}` → `GAME_START` fires for both.
3. Any further joiner → `ROOM_ROLE_ASSIGNED {role: VIEWER}` → subscribed to
   board broadcasts, no move rights.
4. Room ID stays pinned at the top of both players'/viewers' screens for the
   duration (client-side persistent header, not re-fetched per render).

### 10.4 Disconnect → auto-resign
1. `ConnectionHub` detects socket close → notifies the owning `GameSession`.
2. `GameSession.handle_disconnect(player)` starts `DisconnectMonitor`
   (20s, `config.game.disconnect_grace_seconds`).
3. Every second: `DISCONNECT_COUNTDOWN_TICK {seconds_left}` broadcast to the
   *other* player (and viewers); their client renders a live countdown.
4. If the player reconnects within the window (same session token) →
   `handle_reconnect` cancels the monitor, game resumes, countdown clears.
5. If it elapses → `GameSession.end_game(result=<opponent wins>,
   reason='disconnect_timeout')` → `RatingService` updates ELO → persisted →
   `GAME_END` broadcast.

### 10.5 Rating update (on any game end)
1. `GameSession.end_game` computes result and calls
   `RatingService.update_ratings(white_elo, black_elo, result)`.
2. New ELOs persisted via `UserRepository.update_elo`.
3. Game row inserted via `GameRepository.record_game` with before/after ELOs
   for auditability.

---

## 11. Logging Strategy

Both sides log structured JSON lines (one event per line) — easy to grep and
easy to feed into a log viewer later.

**Server** (`server_logger.py`), one call site per event category, injected
into services (never `print()`):
- connection opened/closed, auth attempts, matchmaking enqueue/timeout/match,
  room create/join, every move, disconnects, countdown ticks, auto-resigns,
  rating changes, errors/exceptions with stack trace.

**Client** (`client_logger.py`):
- every user menu action, every message sent/received (payload, not raw
  password), render errors, connection drops/reconnect attempts.

Both use the same rotating-file config shape (`config.logging.*`) — one
`LoggerFactory` in `common/` builds both, parameterized by `log_path`, so the
setup code isn't duplicated between client and server (DRY).

---

## 12. Testing Strategy

| Layer | What to test | How |
|---|---|---|
| `domain/elo.py` | Known ELO scenarios (win/loss/draw, K=32, equal & unequal ratings) against hand-computed expected values | pure unit tests, no mocks needed |
| `RatingService` | Delegates correctly to `elo.py`; does not mutate input | unit |
| `UserRepository` | CRUD, uniqueness constraint on username, ELO update | unit, against a temp SQLite file (or `:memory:`) |
| `AuthService` | Correct hash/verify, rejects wrong password, rejects duplicate username | unit, `UserRepository` faked via interface |
| `MatchmakingService` | Pairs within ±100 ELO band; does *not* pair outside band; expires after configured timeout; FIFO fairness | unit, fake clock (`freezegun`/manual tick), in-memory queue |
| `RoomService` / `RoomIdGenerator` | Unique IDs, correct role assignment order (1st=owner/White implicit via GameSession, 2nd=Black, 3rd+=Viewer) | unit |
| `DisconnectMonitor` | Emits exactly one tick per second, fires timeout at exactly `disconnect_grace_seconds`, cancels cleanly on reconnect, no double-fire | unit, fake clock |
| `GameSession` | Legal/illegal move handling delegates to chess engine; end_game triggers rating update exactly once; viewers receive broadcasts, cannot move | unit, chess engine faked/stubbed |
| Protocol schemas | Reject malformed payloads, round-trip serialize/deserialize | unit |
| End-to-end | Two simulated clients: login → play → match → moves → resign → rating changed in DB. Disconnect scenario: one client closes socket, other sees countdown then win. Room scenario: 3 clients, 3rd is viewer-only. | `pytest-asyncio` spinning up the real server on a test port + `websockets` test clients |

**Definition of done for each phase (§14):** the phase's services have unit
tests green, plus at least one integration test exercising the flow through
the router, before moving to the next phase.

---

## 13. Extensibility / Future-Proofing Notes

- Swapping SQLite for Postgres later = only touch `repositories/*` (they're
  behind an interface) + connection string in config. No service code changes.
- Adding a real GUI later = only replace `client/` (`ShellUI`,
  `screens/*`); protocol and server are already UI-agnostic.
- Adding tournaments/leaderboards later = new `TournamentService` built on
  top of the existing `GameSessionFactory`/`RatingService` — no changes needed
  to matchmaking or rooms.
- Adding reconnection to rooms mid-spectate, chat, or draw offers = new
  message types in `message_types.py` + a new small handler; existing ones
  untouched (open/closed principle falls out naturally from the SRP split).
- Horizontal scaling later: `ConnectionHub` + in-memory matchmaking queue are
  the two components that assume a single process. If you outgrow one
  process, these are the two to move behind Redis (queue) and a pub/sub
  layer (broadcast) — everything else (services, repositories) is already
  stateless/DB-backed and scales out for free.

---

## 14. Implementation Phases (build & test in this order)

1. **Foundations**: config loader, `LoggerFactory`, protocol envelope +
   `message_types.py`, `ConnectionHub`, `MessageRouter` skeleton (echoes
   `PING`→`PONG`). *Test: connection + ping/pong integration test.*
2. **Auth + DB**: schema, `UserRepository`, `AuthService`, `auth_handler`,
   client `LoginScreen`/`HomeScreen`. *Test: register/login unit + e2e.*
3. **Rating core**: `domain/elo.py`, `RatingService` (unit-tested in
   isolation, no game plumbed in yet).
4. **Game session**: wrap existing chess engine in `GameSession`,
   `GameSessionFactory`, `game_handler`, client `GameScreen`. Two players get
   in via a temporary "debug join" path. *Test: full game to checkmate/resign
   e2e, rating updates correctly.*
5. **Matchmaking ("Play")**: `MatchmakingService`, `play_handler`, client
   `PlayScreen` with countdown/timeout popup. *Test: pairing rules,
   timeout, e2e two-client match.*
6. **Rooms**: `RoomService`, `RoomIdGenerator`, `room_handler`, client
   `RoomScreen`. *Test: create/join/role-assignment, 3-viewer e2e.*
7. **Disconnect handling**: `DisconnectMonitor` wired into `GameSession`,
   countdown broadcast, client rendering. *Test: timeout auto-resign e2e,
   reconnect-cancels-timer e2e.*
8. **Logging hardening**: confirm every event category in §11 is actually
   emitted; add log-based assertions to key e2e tests.
9. **Polish**: config review for stray literals, docstring pass, error-path
   coverage (bad room ID, wrong password, double-login, move-out-of-turn).

---

## 15. Pre-flight Checklist Before Writing Code

- [ ] `config/default.yaml` has every tunable mentioned in this doc — grep
      the eventual codebase for bare numbers/strings in `services/` and
      `handlers/` before calling a phase done.
- [ ] Every service constructor takes its dependencies as parameters
      (repositories, config, logger) — never imports a global singleton.
- [ ] Every cross-module interaction goes through a public method/DTO, never
      a shared mutable dict.
- [ ] Every phase in §14 has its tests green before starting the next.
- [ ] Passwords: hashed (argon2/bcrypt) at rest, never logged, never sent
      back in any payload.
