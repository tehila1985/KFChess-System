# Server Design — Scaling to Cloud Scale

## Context

Everything in `chess-backend/` today (`server/main.py` and friends,
documented in `CHESS_BACKEND_ARCHITECTURE.md`) is **one process**: one
`ConnectionHub` holding every socket in a Python dict, one in-memory
`MatchmakingService` queue, one SQLite file, one `GameSession` object per
game living in that same process's memory. That design is correct and
appropriate for what it's for — a small number of concurrent players on
one machine — and every principle in it (SRP, DRY, the `GameEngine` as
sole authority) carries forward unchanged into this document. What
changes is *scale*: this is no longer a question of "which class does
this belong in" but "which machine, in which region, does this belong
on, and how does everyone find it." The two problems share principles;
they don't share solutions.

This document answers four concrete requirements with real numbers, then
lays out the component architecture, data layer, routing/coordination
layer, deployment topology, and a migration path from the code that
exists today to the design described here.

**Non-negotiable constraint, unchanged from the current codebase:**
*the client never decides game rules, and neither does any gateway.*
`GameEngine` (wrapped by `GameSession`, wrapped by whatever runs it) is
the single source of truth for legality, timing, and outcome, exactly as
it is today. Every component added below is either "in front of" the
authoritative game (routing, fan-out, matchmaking) or "behind" it
(persistence, analytics) — nothing is added that second-guesses the
engine.

---

## 1. The Four Questions

### Q1 — 100,000,000 registered users: is SQLite still fine?

No. Not because of row count — 100M rows of `(id, username,
password_hash, elo, timestamps)` is maybe 15–25 GB, trivial for modern
storage. SQLite fails at this scale for a structural reason: **it is an
embedded, single-process, single-writer library, not a networked
database.** It has no client/server protocol at all — a process talks to
it by opening the file directly. The moment you have more than one
`server` process (which you must, per Q2), they cannot share one SQLite
file over a network without putting the file on shared storage (NFS or
similar), which turns every write into a distributed-locking nightmare
and a single point of failure, and still caps you at one writer at a
time even with WAL mode.

**Use PostgreSQL** (as already listed in the target stack), split by
access pattern rather than treated as one moving part:

| Data | Store | Why |
|---|---|---|
| `users` (login, elo, profile) | PostgreSQL primary + read replicas | Relatively low write rate (registrations, ELO updates on game end — see Q4 for the actual number), high read rate (login checks, leaderboards) → read replicas absorb reads, primary absorbs the (much smaller) write stream |
| `games` (completed-game audit, one row per game) | PostgreSQL, **partitioned by month** and eventually **sharded by `user_id` hash** if one cluster's write throughput becomes the bottleneck (Q4 shows it will, at 10M concurrent) | Ever-growing, append-only, no need for it to sit in the same table/instance as `users` |
| `moves` (per-ply log) | **Not Postgres at this scale.** A log-oriented store (Kafka/NATS JetStream topic, archived to object storage/columnar store) if move replay is ever needed | At 5,000,000 moves/sec (Q3), a row-per-move relational table is not a database problem, it's a streaming problem |

SQLite doesn't disappear from the codebase — it's still exactly right for
local dev / `docker-compose` / running the existing test suite, which is
why the migration path (§7) keeps it there behind the same
`AbstractUserRepository`/`AbstractGameRepository` interfaces that already
exist in `server/repositories/base_repository.py`. Swapping the
implementation, not the interface, is the entire point of that
abstraction already being in place.

### Q2 — 10,000,000 concurrent players: one server, or many, and how does anyone find anyone?

One server cannot do this — not "one server is slow," but **structurally
impossible**: a single OS process has hard ceilings on open file
descriptors (sockets), and a single machine has one NIC, one region, and
one failure domain. Someone in Tokyo talking to a lone server in Virginia
adds ~150–200ms of pure geography before a single byte of game logic
runs — noticeable even for a 2-second move cadence, and a guaranteed poor
experience at global scale.

So: many machines, many processes, globally distributed. The real
question the prompt is asking is the harder one: **if a game can be
running on any of a thousand `Game Server Shard` instances, how does a
message from a player in Brazil find the one process, anywhere in the
world, that's authoritative for their specific game?** This is a routing
problem, not a database-size problem, and it's the crux of the whole
architecture:

```
Player A (Brazil)                          Player B (India)
      │                                            │
      ▼                                            ▼
WebSocket Gateway (São Paulo)              WebSocket Gateway (Mumbai)
      │                                            │
      │   "I need game g-4471, who has it?"        │
      └──────────────┬─────────────────────────────┘
                      ▼
              Redis: game:g-4471 -> shard-eu-west-1-pod-0312
                      │
                      ▼
         Game Server Shard (eu-west-1, pod 0312)
         — the ONE process running this GameEngine —
```

**The mechanism: a `conn_id`/`game_id` → shard directory, in Redis,
that every Gateway and every Shard reads and writes.** This is exactly
what `ConnectionHub` already does today (`conn_id → websocket`,
`session_token ↔ conn_id`) — it just currently lives in one process's
Python dict. At cloud scale that dict becomes Redis keys:

```
session:{token}         -> { user_id, username, elo, gateway_id, expires_at }
game:{game_id}          -> shard_id                      (which shard owns this game's authoritative state)
room:{room_id}          -> { game_id, owner, white, black, viewers[] }
matchmaking:queue       -> Redis sorted set, score = elo, member = user_id  (region-partitioned, see below)
shard:{shard_id}:load   -> current game count, capacity, region            (heartbeated every few seconds)
```

This is why **WebSocket Gateway** and **Game Server Shard** are drawn as
separate components even though today's `server/main.py` does both in
one process: they scale on *completely different axes*.
- A **Gateway** is a dumb, stateless edge: accept the TLS/WS handshake,
  authenticate the token, then for every inbound message look up
  `game:{game_id}` in Redis and forward the message to that shard over
  the internal bus (NATS/Redis pub-sub); for outbound, subscribe to that
  game's broadcast channel and relay frames to whichever of *its own*
  sockets belong to that game. It holds real TCP connections, so it's
  bound by connection count and pure fan-out CPU, and is trivially
  horizontally scaled behind a normal load balancer / GeoDNS (route to
  the nearest region).
- A **Game Server Shard** holds the actual `GameEngine` + `GameSession`
  objects in memory (exactly the classes that exist today, unmodified —
  see §7). It never talks to a client socket directly; it only exists to
  a Gateway as "the process I forward game g-4471's messages to." It's
  bound by CPU (real-time tick math per active game) and memory (state
  per game), not by connection count.

Because the *socket* a client holds is pinned to whichever Gateway
accepted it (you cannot move an established TCP connection to another
machine), but the *game* is pinned to whichever Shard the Game Allocator
placed it on, and the two are **never required to be the same machine or
even the same region** — the Gateway↔Shard hop over the internal bus is
what makes "anyone can join any room, from anywhere" work at all. A room
ID or game ID is never "owned" by a specific edge location from the
client's point of view; the directory in Redis is what makes it global.

**Matchmaking and rooms are global state for the same reason** — the
queue and room registry cannot live inside one Shard's memory (today's
`MatchmakingService`/`RoomService` in-memory structures), because *any*
Gateway anywhere must be able to enqueue a player or resolve a room ID.
They move to Redis (`matchmaking:queue` as an ELO-scored sorted set;
`room:{room_id}` as a hash), read/written by however many **Matchmaker**
and **Game Allocator** replicas are running — those two remain logically
centralized (globally consistent state) but are horizontally scaled and
made stateless *themselves* by keeping all state in Redis, not in their
own process memory. One nuance worth calling out: the ELO-cadence
real-time game design here has a much looser latency budget than, say,
an FPS — a player moves roughly every 2 seconds, so even 150–300ms of
inter-region latency is imperceptible. That means the Matchmaker can
prefer same-region pairing (for the Game Allocator to place the game
near both players, and to avoid needless cross-region backbone traffic)
without it being a hard requirement — a global matchmaking pool with a
regional-affinity heuristic, not strict regional sharding, is enough.

### Q3 — Network traffic: is 5,000,000 moves/sec "a lot"?

Yes — and the exact number depends directly on a design decision this
session made, worth confronting honestly.

**Assumptions** (stated explicitly since the answer is sensitive to
them): 10,000,000 concurrent players → 5,000,000 concurrent games
(2 players/game; viewers add connections but not games, treated as a
multiplier below, not the baseline). Each player moves on average once
every 2 seconds → 0.5 moves/sec/player → **5,000,000 accepted moves/sec,
system-wide.**

Per the wire protocol as it exists in `common/protocol/schemas.py` right
now, one accepted move produces **four** messages, not one:
1. inbound `MOVE` (client → server)
2. outbound `MOVE_ACK` (server → the mover, confirming/rejecting)
3. outbound `MOVE_BROADCAST` → white's connection
4. outbound `MOVE_BROADCAST` → black's connection

→ **20,000,000 messages/sec** system-wide, before counting viewers.

Payload size is where the honest part comes in. Earlier this session,
`MOVE_BROADCAST` and `GAME_START` were deliberately changed to carry the
**full 8×8 board snapshot** (`board`, `scores`, `game_over`, `winner`) on
every move, specifically so a client never has to maintain its own copy
of game rules to render — a good simplicity/robustness tradeoff at the
scale that code runs at today. At 20M messages/sec, that tradeoff has a
direct, quantifiable cost:

| Message | Current design (full board) | Delta-only alternative |
|---|---|---|
| `MOVE` (in) | ~200 B (incl. 64-char session token, uuid request_id) | same, ~200 B |
| `MOVE_ACK` (out) | ~160 B | same, ~160 B |
| `MOVE_BROADCAST` (out, ×2) | ~550 B each (grid + scores + envelope) | ~120 B each (src/dst/color only) |
| **Bytes per move** | **1,460 B** | **600 B** |
| **Aggregate (× 5,000,000/sec)** | **7.3 GB/s ≈ 58 Gbps** | **3.0 GB/s ≈ 24 Gbps** |

(Both figures exclude WebSocket framing, TCP/IP headers, and TLS record
overhead — real WSS traffic, add roughly 10–20% on top of either
number.)

**Is that a lot?** Yes, on both counts, but not in the way raw "Gbps"
suggests — the binding constraint at this message size is **packets per
second, not bytes per second.** 20,000,000 tiny (100s of bytes) messages
per second is an enormous PPS figure; a single well-tuned modern host
tops out somewhere in the low millions of PPS even with kernel-bypass
techniques. This isn't solved by a bigger NIC — it's solved by **the
same horizontal fan-out as Q2**: spreading the 20M msg/sec across
hundreds to low thousands of Gateway/Shard instances, globally
distributed, each individually handling a modest, comfortable slice.

**Recommendation, concretely:** keep the full-board `MOVE_BROADCAST`
payload for `GAME_START` and for reconnect-resync (correctness matters
more than bytes on the rare path), but switch the *hot path*
(`MOVE_BROADCAST` during normal play) to a delta-only payload
(`src`/`dst`/`color`, ~2.5x smaller), with clients reconstructing board
state incrementally — exactly the pattern `game_scene.py`'s local mirror
`GameFacade` already implements (it replays deltas onto a local engine;
it doesn't need the full grid every time, it only ever *used* the full
grid because that's what today's server happens to send). Moving to a
compact binary encoding (protobuf/msgpack) instead of JSON text for this
one hot-path message is the next lever if 24 Gbps is still too much.

### Q4 — 30–90 second games: what does that mean for the Docker roles?

Average game length ≈ 60s. With 5,000,000 concurrent games in steady
state, Little's Law (`arrival_rate = concurrency / duration`) gives:

**≈ 83,000 games starting, and ≈ 83,000 games ending, every second,
system-wide.**

That number, not the 100M user count, is the real pressure point on
several components:

- **Game Allocator** must place ~83,000 new games/sec. That rules out
  any design where placement means "query every shard's live load and
  pick the best one" — too slow, too much lock contention at that rate.
  It needs to be **O(1) per placement**: shards push their own capacity
  to Redis every second or two (`shard:{id}:load`), and the Allocator
  (itself horizontally scaled, consuming placement requests off a
  NATS queue) does an atomic `DECR`-style claim against a pre-known
  candidate shard (same-region as both matched players, with headroom),
  falling back to the next candidate on contention. This is a
  distributed-semaphore pattern, not a scheduling-algorithm pattern.
- **Game Server Shards must run many lightweight, in-process concurrent
  games — not one process per game.** At 83,000 game-starts/sec,
  spinning up an OS process per game would mean 83,000 process creations
  per second system-wide; no scheduler survives that. This is exactly
  why `GameSession` today is a plain async object multiplexed inside one
  event loop (`server/main.py` already runs many `GameSession`s
  concurrently in one process) — that pattern is what scales, it just
  needs to be replicated across many shard *pods*, not many processes
  per pod. A reasonable per-pod target (2,000–5,000 concurrent
  lightweight games, depending on real measured CPU/memory per game) puts
  the shard fleet at roughly **1,000–2,500 replicas** for 5,000,000
  concurrent games — a number to be *measured*, not assumed (see the
  Observability component: this is exactly what load testing is for).
  Because games are short-lived, a given shard's load can swing quickly
  in either direction — good news for autoscaling responsiveness (no
  long-lived state pins capacity for hours), but it means capacity
  heartbeats need to be frequent (seconds, not minutes) or the Allocator
  will place onto shards that look free but have just filled up.
- **Persistence load is dominated by game-*end* events, not the user
  table.** Each of those 83,000 game-ends/sec writes 1 row to `games`
  and updates 2 rows in `users.elo` → **~250,000 writes/sec** aimed at
  Postgres. That is far beyond one instance's comfortable sustained
  write rate. The fix is the same shape as Q3's fix: don't write
  synchronously on the hot path. Game-end events go onto a queue
  (NATS/Kafka); a pool of writer workers batches them into Postgres
  (bulk `COPY`/multi-row `INSERT`), and/or `users` is sharded by
  `user_id` hash across several Postgres clusters once one cluster's
  write ceiling is reached. ELO itself can be updated in Redis
  immediately (so the *next* matchmaking lookup sees it right away) and
  flushed to Postgres asynchronously — eventual consistency for the
  audit trail, immediate consistency for gameplay-facing reads.
- **A shard crash has a naturally small blast radius.** Because games
  self-terminate within ~90s regardless, replicating live `GameSession`
  state across machines (to survive a shard crash mid-game) is
  significant engineering for a failure mode that, worst case, aborts a
  handful of already-short games. The pragmatic choice: **don't**
  replicate in-memory game state; let a crashed shard's in-flight games
  end as `aborted` (the `GameResult.ABORTED` value already exists in
  `server/domain/enums.py` for exactly this), have the Allocator stop
  routing new games to a dead shard (missed heartbeat), and let affected
  clients see a `GAME_END{reason=aborted}` and return to matchmaking.
  This is a deliberate scope cut, stated explicitly rather than silently
  assumed.

---

## 2. Component Architecture

```
                         ┌─────────────────────────────────────────┐
                         │              Clients (global)             │
                         └───────────────┬───────────────┬───────────┘
                                         │               │
                     non-real-time HTTPS │               │ WSS (persistent)
                                         ▼               ▼
                       ┌──────────────────────┐   ┌──────────────────────────┐
                       │     API Gateway       │   │   WebSocket Gateway       │
                       │  login, register,     │   │  auth handshake, message  │
                       │  room/game history,   │   │  routing to/from shards,  │
                       │  leaderboards         │   │  per-region, stateless    │
                       └──────────┬───────────┘   └──────────────┬────────────┘
                                  │                               │
                                  │        internal bus (NATS)     │
                                  ▼                               ▼
                       ┌──────────────────────┐   ┌──────────────────────────┐
                       │      Matchmaker       │──▶│     Game Allocator        │
                       │  ELO-scored queue,    │   │  picks a shard w/ headroom │
                       │  region-aware pairing │   │  same-region if possible   │
                       └──────────┬───────────┘   └──────────────┬────────────┘
                                  │                               │
                                  ▼                               ▼
                       ┌───────────────────────────────────────────────────┐
                       │            Game Server Shards (fleet)               │
                       │  many GameSession/GameEngine instances per pod,      │
                       │  authoritative — the ONLY place chess rules run      │
                       └──────────────────────┬──────────────────────────────┘
                                              │
                     ┌────────────────────────┼─────────────────────────┐
                     ▼                        ▼                         ▼
             ┌───────────────┐      ┌──────────────────┐      ┌──────────────────┐
             │     Redis      │      │    PostgreSQL      │      │  Observability     │
             │ sessions, room/│      │ users, games,      │      │ logs, metrics,     │
             │ game directory,│      │ (move history →     │      │ health, load tests │
             │ matchmaking Q  │      │  streaming store)   │      │                    │
             └───────────────┘      └──────────────────┘      └──────────────────┘
```

### 2.1 API Gateway
Everything that isn't latency-sensitive real-time state: `LOGIN`,
`REGISTER`, room/game history queries, leaderboards. Plain stateless
HTTP(S), scales trivially behind a normal load balancer, reads/writes
PostgreSQL (and read replicas for the heavy read paths like
leaderboards). This is a straightforward horizontal-scale problem — it
gets its own component mainly so its very different load profile (bursty
request/response, no persistent connections) doesn't compete for the
same capacity planning as the WebSocket Gateway.

### 2.2 WebSocket Gateway
Owns the live connection and nothing else — no game state, no
matchmaking logic. Responsibilities: TLS/WS handshake, validate the
session token (short-lived local cache of `AuthService.validate_token`
results, backed by Redis, to avoid a Redis round-trip per message),
maintain the `conn_id ↔ session_token` mapping (today's
`ConnectionHub`, now Redis-backed so any Gateway instance can resolve
any token), and route: inbound envelope → look up `game:{game_id}` →
publish to that shard's inbound subject on the internal bus; shard's
outbound broadcast → any Gateway subscribed for that `game_id` relays it
to its own local sockets. Purely stateless and horizontally scaled;
regional placement matters here (route each client to their nearest
region) because this is where connection-level latency is felt.

### 2.3 Matchmaker
Owns the "Play" queue: `enqueue`/`dequeue` against the Redis sorted set
keyed by ELO, scoped by region for pairing locality. The pairing tick
(today's `MatchmakingService._tick()`, unchanged in logic) runs
continuously across as many Matchmaker replicas as needed, each
processing a shard of the region-partitioned queue — the pairing
*algorithm* (±`match_range` ELO window, FIFO fairness, timeout) is
identical to what exists today; only the queue's storage moves from a
Python list to Redis so it's visible to every replica.

### 2.4 Game Allocator
The only component whose job is fundamentally new versus today's code
(today, `GameSessionFactory` and the process it runs in are the same
thing, so there's no "allocation" — there's only one place a game could
go). Receives "these two players matched, or a room just filled" events,
picks a Game Server Shard (region-affinity + headroom, per Q4), writes
`game:{game_id} -> shard_id` into Redis, and asks that shard (over the
bus) to instantiate the `GameSession`. Everything downstream of that
instantiation — `GameSessionFactory.create()`, `GameSession.start()` — is
the exact code that exists today.

### 2.5 Game Server Shards
Runs the authoritative game loop: many `GameSession` (wrapping
`GameEngine`/`RealTimeArbiter`/`RuleEngine`) instances multiplexed on one
event loop per pod, exactly as `server/main.py` does today for its
single process — this component *is* today's server, just deployed as
one of many identical, horizontally-scaled replicas instead of the only
one. Never touches a client socket directly (that's the Gateway's job);
talks to Gateways only via the internal bus, and to Postgres only
through the write-behind queue described in Q4 (never a synchronous
write on the move/broadcast hot path).

### 2.6 Observability
Structured logs (the existing `JsonFormatter`/`ServerLogger` pattern,
shipped to a central log store instead of a local rotating file),
metrics (shard load, queue depth, match rate, p50/p99 move-round-trip
latency, connection counts per Gateway), health checks (liveness for the
Allocator's shard-selection and the Gateway's routing table), and **load
testing** — explicitly called out because every capacity number in §1
(games/shard, connections/gateway, writes/sec Postgres can sustain) is an
estimate that needs to be measured against a real load-test harness
before it's trusted in production sizing.

---

## 3. Internal Messaging: NATS vs. Redis Pub/Sub

Both are listed in the target stack; pick **NATS** for the
Gateway↔Shard↔Allocator/Matchmaker bus, and reserve **Redis** for state
(sessions, directory, queues) rather than messaging. Reasoning:
- Redis pub/sub has no delivery guarantee and no persistence — a
  subscriber that's momentarily busy (a Gateway under load) silently
  misses messages published while it wasn't listening. For "here's the
  next board update," that's a real correctness risk (a client that
  misses one `MOVE_BROADCAST` renders a stale board until the next one).
- NATS (core pub/sub for broadcast fan-out, or JetStream where an
  at-least-once/replay guarantee is worth the extra cost — e.g. the
  game-end write-behind queue from Q4) is purpose-built for exactly this
  kind of high-throughput, low-latency internal fan-out, and keeps it
  cleanly separate from Redis's job as the state/coordination store.
  Redis stays the single place that answers "where is X right now,"
  which is the property Q2's routing depends on.

---

## 4. Deployment Topology

- **`docker-compose`** (local/dev, and CI for the existing test suite):
  one of each component, SQLite instead of Postgres, a single Redis, a
  single NATS — this is close to what runs today, just with the
  Gateway/Shard split made explicit even at 1-replica-each scale, so the
  routing code path is exercised locally instead of only in production.
- **Kubernetes/K3s** (production): every component above is its own
  Deployment, horizontally scaled independently (Gateways and Shards
  scale on entirely different signals — connection count vs. game
  count/CPU — so they must never share an autoscaling policy), spread
  across regions with regional Gateway+Shard pairs and a global
  Redis/Postgres/NATS control plane (itself regionally replicated for
  latency and disaster recovery — a single global Redis instance would
  reintroduce exactly the single-point-of-failure/latency problem this
  whole design exists to avoid). Shard pods should be sized and
  autoscaled off *game count* and CPU, not connection count (that's the
  Gateway's signal) — conflating the two metrics is the most common
  mistake in sizing a split like this.

---

## 5. Reliability & Failure Modes

| Failure | Behavior |
|---|---|
| A Gateway instance dies | Its sockets drop. Clients reconnect (same session token) to *any* other Gateway — the token, room, and game all resolve via Redis regardless of which Gateway serves the new connection. This is the cloud-scale version of `ConnectionHub`'s existing "keep the token→conn mapping across reconnect" behavior. |
| A Shard instance dies | Its in-flight games (naturally short-lived, per Q4) end as `aborted`; the Allocator stops routing new games there on missed heartbeat. Deliberately not replicated — see Q4. |
| Redis is unavailable | Existing games in flight on a Shard can continue locally for their (short) remaining duration, but no new routing/matchmaking/room lookups can succeed — Redis is a hard dependency for anything cross-shard. Runs as a replicated cluster (not a single instance) specifically because of this. |
| Postgres write queue backs up | Game-end persistence lags but does not block gameplay — the queue (NATS JetStream) absorbs the burst; ELO reads for matchmaking come from Redis (already updated immediately), not from the lagging Postgres write. |
| A whole region goes dark | Players in that region reconnect to the nearest surviving region (higher latency, but functional) — this is why Gateways and Shards are deployed per-region rather than assuming one global pool. |

---

## 6. Security at This Scale

- Rate-limit at the API Gateway and WebSocket Gateway (per-IP and
  per-account) — `REGISTER`/`LOGIN` attempts and `MOVE` submission rate
  both need bounds independent of the game logic's own validation, since
  a malicious or buggy client spamming `MOVE` is a routing/CPU problem
  before it's ever a "is this move legal" problem.
- Session token validation is on the hot path of *every* message — cache
  `validate_token` results (short TTL) at the Gateway so 20,000,000
  msg/sec doesn't mean 20,000,000 Redis round-trips/sec for auth alone.
- Never trust `src`/`dst`/color from the client beyond what
  `GameSession.apply_move`'s existing ownership check already enforces
  (fixed earlier this session) — that check, and everything else that
  makes the engine authoritative, must run **only** inside the Game
  Server Shard, never inferred or pre-filtered by a Gateway trying to be
  helpful.

---

## 7. Migration Path from Today's Code

Nothing in `server/domain/`, `server/services/game_session.py`,
`server/services/game_session_factory.py`, or `engine/` changes in
*logic* — only in *deployment*. Concretely:

| Today | Becomes |
|---|---|
| `ConnectionHub` (in-process dict) | WebSocket Gateway + Redis-backed directory (same conceptual API: register/unregister/send/broadcast-by-token) |
| `MatchmakingService` (in-process list) | Matchmaker service, same pairing algorithm, Redis sorted set instead of a Python list |
| `RoomService` (in-process dict) | Room state in Redis (`room:{room_id}` hash), read/written by any Matchmaker/Allocator/Gateway replica |
| `GameSessionFactory.create()` | Called by the Game Allocator instead of directly by `MatchmakingService`/`RoomService` — same method, same return type |
| `GameSession`/`GameEngine`/`RealTimeArbiter` | Unchanged. Runs inside a Game Server Shard pod instead of the monolith process. |
| `UserRepository`/`GameRepository` (SQLite) | Same interfaces (`AbstractUserRepository`/`AbstractGameRepository`), PostgreSQL implementation instead of SQLite, plus a write-behind queue in front of `GameRepository.record_game` |
| `server/main.py`'s single `websockets.serve(...)` | Split into the API Gateway (HTTP) and WebSocket Gateway (WS) deployments |
| `ServerLogger`/`JsonFormatter` | Same format, shipped to centralized log aggregation instead of a local rotating file |

This is the concrete argument for why the current codebase's SRP
boundaries (services never reach into repositories' SQL, handlers never
touch the engine directly, `GameSessionFactory` is the only place a
`GameSession` gets built) matter beyond code cleanliness: every one of
those boundaries is exactly the seam this migration cuts along. A
codebase without them would need a rewrite here; this one needs a
redeployment.

---

## 8. Open Questions for Load Testing

These are stated as assumptions above and need real numbers before
production sizing:
- Concurrent `GameSession` objects sustainable per Shard pod (CPU/memory
  per game under real tick load, not estimated).
- Concurrent WS connections sustainable per Gateway pod (real fan-out
  CPU cost, not just idle-connection file-descriptor limits).
- Sustained write throughput of a single Postgres cluster for the
  game-end write-behind queue, to calibrate how many `users`-table shards
  are actually needed versus assumed.
- Actual cross-region latency distribution for a global player base, to
  validate that "prefer same-region, don't require it" is the right
  Matchmaker policy rather than stricter regional partitioning.
