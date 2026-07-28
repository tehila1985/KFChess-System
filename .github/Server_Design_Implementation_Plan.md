# Server Design — Implementation Plan

## Context

`Server_Design.md` describes the *target* architecture: API Gateway,
WebSocket Gateway, Matchmaker, Game Allocator, Game Server Shards,
Redis/PostgreSQL/NATS, deployed across regions. This document is the
*ordered route* from today's single-process `chess-backend/` codebase to
that target — phase by phase, each one shippable and tested on its own,
mirroring the same discipline `chess-backend-implementation-plan.md`
already used to build the current system ("Definition of Done" per
phase, don't start the next one until the current one's tests are
green). Nothing here is a big-bang rewrite: every phase leaves the system
running and playable, just closer to the target than before.

**Guiding rule for ordering the phases:** migrate **one axis of change at
a time**. There are four largely-independent axes — (1) where state
lives (in-process → Redis), (2) how many processes there are (one →
Gateway/Shard split → many replicas), (3) which database durable data
lives in (SQLite → PostgreSQL), (4) how many regions are live (one →
many). Combining two of these in one phase is where migrations actually
go wrong — you lose the ability to tell which change broke what. Each
phase below moves exactly one axis.

---

## Phase Overview

| Phase | Goal | New infra introduced | Code touched | Can run in prod after this phase? |
|---|---|---|---|---|
| 0 | Seams or it doesn't happen | none (docker-compose gets new services, unused) | interfaces only | Yes — behavior-identical |
| 1 | Shared state, still 1 process | Redis | `ConnectionHub`, `MatchmakingService`, `RoomService` get Redis-backed variants | Yes — identical behavior, now horizontally-*ready* |
| 2 | Real Gateway/Shard network hop, still 1 of each | NATS | new `gateway/` and `shard/` entrypoints | Yes — same capacity as today, new failure modes to watch |
| 3 | Horizontal scale-out, one region | K8s/K3s, load balancer, autoscaling | Game Allocator gets real placement logic | Yes — this is "cloud-scale, one region" |
| 4 | Durable store swap | PostgreSQL, write-behind queue (NATS JetStream) | `UserRepository`/`GameRepository` Postgres impls | Yes |
| 5 | Multi-region | regional K8s clusters, GeoDNS, replicated control plane | Matchmaker region-affinity | Yes — this is the full target design |
| 6 | Resilience & security hardening | chaos-testing harness, rate limiter | — | Hardens what's already live |
| 7 | Full-scale load test & calibration | load-test harness (Observability) | capacity constants everywhere | Confirms the numbers in `Server_Design.md` §1 for real |

---

## Phase 0 — Foundations (no behavior change)

**Goal:** put every seam this migration needs to cut along into place,
*before* touching any deployment topology, so later phases are pure
swaps behind interfaces that already exist.

**Tasks:**
- Confirm `AbstractUserRepository`/`AbstractGameRepository`
  (`server/repositories/base_repository.py`) are the *only* way any
  service touches persistence — already true today; add a lint/CI check
  (grep for raw SQL/`sqlite3` imports outside `server/repositories/` and
  `server/db/`) so it stays true.
- Introduce three new, currently-trivial interfaces, one per in-memory
  structure that Phase 1 will move to Redis, so the *call sites* in
  `MatchmakingService`, `RoomService`, and `ConnectionHub` never change
  again after this phase:
  - `AbstractConnectionDirectory` (register/unregister/get_conn_id_by_token/broadcast) — today's `ConnectionHub` becomes the in-memory implementation of it.
  - `AbstractMatchQueue` (enqueue/dequeue/pop_expired/pairs_within_range) — today's `MatchmakingService`'s internal `list` becomes the in-memory implementation.
  - `AbstractRoomRegistry` (create/get/join) — today's `RoomService`'s internal `dict` becomes the in-memory implementation.
- Add `redis-py` (or `redis.asyncio`), `nats-py`, and `psycopg`/`asyncpg`
  as dependencies, and add **unused** Redis, NATS, and Postgres services
  to `docker-compose.yml` — unused on purpose, so every developer's local
  environment has them running before any code depends on them, removing
  "works on my machine, no Redis installed" as a failure mode later.

**Definition of done:** full existing test suite (296 tests) still green,
**zero behavior change** — this phase only introduces interfaces and
unused infra. Every one of `MatchmakingService`/`RoomService`/
`ConnectionHub`'s existing unit tests passes unmodified against the new
interface-typed constructor parameter (still backed by the same
in-memory implementation).

---

## Phase 1 — Externalize ephemeral state to Redis (still one process)

**Goal:** prove the Redis-backed state model works — session tokens,
room registry, matchmaking queue all live in Redis — while *everything
still runs in one process*, so this phase's only variable is "did the
Redis integration work," not "did the network split also work."

**Tasks:**
- Implement `RedisConnectionDirectory`, `RedisMatchQueue`,
  `RedisRoomRegistry` against the Phase 0 interfaces. Key shapes exactly
  as specified in `Server_Design.md` §1 Q2 (`session:{token}`,
  `game:{game_id}`, `room:{room_id}`, `matchmaking:queue` as an
  ELO-scored sorted set).
- `server/main.py` (still one process) is configured to use the Redis
  implementations instead of the in-memory ones — a config flag, not a
  code fork, so CI can run the existing test suite against *both*
  backends and prove parity.
- Add a TTL/heartbeat pattern for session tokens and room entries (Redis
  `EXPIRE`) so state can't leak forever if a cleanup path is missed —
  today's in-memory dicts never needed this since process death cleared
  everything for free; Redis needs it explicit.
- Port every existing `MatchmakingService`/`RoomService`/`ConnectionHub`
  unit test to run twice — once per backend — via a pytest fixture
  parametrized over the two implementations. This is the actual
  regression net for this phase: identical behavior, different storage.

**Definition of done:** the parametrized test suite is green against
both the in-memory and Redis-backed implementations. A manual two-client
game (exactly the smoke test already used for the GUI client) works
identically with `REDIS_BACKEND=true`. Redis becoming unavailable
mid-game is tested explicitly (expect: in-flight game continues locally
since `GameSession` itself doesn't touch Redis yet in this phase; new
matchmaking/room operations fail loudly, not silently).

---

## Phase 2 — Split Gateway / Shard (still 1 of each, real network hop)

**Goal:** introduce the actual process boundary and NATS hop described
in `Server_Design.md` §2.2/§2.5 — but with exactly one Gateway and one
Shard, so the *only* new variable is "does cross-process routing work,"
not "does it work under load or with many replicas."

**Tasks:**
- New entrypoint `gateway/main.py`: owns the WS listener
  (`websockets.serve`), auth handshake, and the Redis-backed session
  lookup from Phase 1. On each inbound envelope, looks up
  `game:{game_id}` in Redis, publishes to `shard.{shard_id}.inbound` on
  NATS. Subscribes to `shard.{shard_id}.outbound.{game_id}` per active
  game to relay frames back to its own sockets.
- New entrypoint `shard/main.py`: subscribes to its own
  `shard.{shard_id}.inbound` NATS subject, runs `MessageRouter` +
  `GameHandler` + `GameSession` exactly as today, publishes outbound
  envelopes to `shard.{shard_id}.outbound.{game_id}` instead of writing
  directly to a websocket (`ConnectionHub.send` becomes "publish to
  NATS," not "write to socket" — this is the one real code change to
  `GameSession`'s hub dependency, and it's a *substitution*, not a
  rewrite, since `GameSession` already only depends on the `hub`
  parameter's `send`/`broadcast` interface).
- Game Allocator, at this phase, is trivial (one shard exists, so
  "allocate" always resolves to it) — implemented as the simplest
  possible thing that writes `game:{game_id} -> shard_id` to Redis, so
  the *interface* the real allocator will have in Phase 3 already exists
  and is exercised.
- Add an integration test that starts a Gateway process, a Shard
  process, and Redis+NATS test containers, and runs the existing e2e
  scenarios (`test_phase4_game_e2e.py`'s full game, disconnect/
  reconnect) *across the process boundary* instead of in one process.

**Definition of done:** every existing e2e test passes against the
2-process (Gateway+Shard) topology. Killing the Shard process mid-game
produces the `aborted` outcome described in `Server_Design.md` §1 Q4 and
§5, observed end-to-end from a real client. Killing the Gateway process
mid-game and reconnecting a client to a *freshly started* Gateway process
resumes the game (proves the Redis-backed session/game directory, not
gateway-local state, is what makes reconnect work).

---

## Phase 3 — Horizontal scale-out (one region, many replicas)

**Goal:** many Gateways, many Shards, a real Game Allocator making real
placement decisions — this is "cloud-scale" for one region.

**Tasks:**
- Game Allocator becomes its own service: consumes match/room-ready
  events from NATS, reads `shard:{id}:load` capacity keys from Redis
  (populated by each Shard's own heartbeat, per `Server_Design.md` §1
  Q4), picks a shard with headroom, writes the `game:{game_id}` mapping.
  Implement as a horizontally-scalable stateless consumer group (NATS
  queue groups) from the start — no single-instance version to
  deprecate later.
- Matchmaker becomes its own replicated service reading/writing the
  Redis sorted set from Phase 1; multiple replicas process the queue
  concurrently (partition by a hash of `user_id` or by region tag on the
  queue entries to avoid duplicate-pairing races — needs an explicit
  concurrency-safety test: two Matchmaker replicas racing to pair the
  same two queued players must not produce two games).
- Kubernetes/K3s manifests: separate Deployments for API Gateway, WS
  Gateway, Matchmaker, Game Allocator, Game Server Shard, each with its
  **own** HorizontalPodAutoscaler target metric — connection count for
  WS Gateway, concurrent-game-count/CPU for Shard (per
  `Server_Design.md` §4's explicit warning against conflating these).
- Load balancer / ingress in front of the WS Gateway fleet; health/
  readiness probes for every component (a Shard reporting itself
  "unhealthy" must stop receiving new game placements without dropping
  its *current* games).

**Definition of done:** a load test (see Phase 7 for the full-scale
version; here, a *modest* one — hundreds to low thousands of simulated
concurrent games) survives a rolling restart of the Shard fleet and of
the Gateway fleet independently, with no client-visible game loss beyond
the individually-affected in-flight games on a restarted pod (matches
the accepted blast-radius tradeoff in `Server_Design.md` §1 Q4). Two
Matchmaker replicas running concurrently never double-pair a player
(explicit concurrency test, not just "seemed fine manually").

---

## Phase 4 — Durable store migration to PostgreSQL

**Goal:** move `users`/`games` off SQLite without a cutover outage or a
silent data-integrity gap.

**Tasks:**
- Implement `PostgresUserRepository`/`PostgresGameRepository` against
  the existing `AbstractUserRepository`/`AbstractGameRepository`
  interfaces — no service-layer code changes, by construction (this is
  the entire reason those interfaces exist today).
- **Shadow-write period:** for a bounded time, write to *both* SQLite and
  Postgres, read from SQLite (unchanged), and run an offline
  reconciliation job comparing the two — this catches encoding/precision/
  constraint mismatches before any read path depends on Postgres.
- Cut reads over to Postgres (feature-flagged, reversible in one config
  change), then stop writing to SQLite.
- Build the write-behind queue for game-end persistence: `GameSession
  .end_game` publishes a `game_ended` event to a NATS JetStream stream
  instead of calling `GameRepository.record_game`/`UserRepository
  .update_elo` synchronously; a small pool of writer workers consumes the
  stream and batches inserts/updates into Postgres. ELO itself is also
  written to a Redis key immediately (read by Matchmaker/leaderboard
  queries) so gameplay-facing reads never wait on the batched Postgres
  write.
- Add PostgreSQL read replicas for the `users` table once read volume
  (login checks, leaderboard queries) is measured to need them (don't
  provision speculatively — measure first, per the Phase 7 philosophy).

**Definition of done:** shadow-write reconciliation shows zero
discrepancies over a full day of realistic traffic before cutover.
Write-behind queue backlog under a synthetic burst (simulate 250,000
game-ends/sec per `Server_Design.md` §1 Q4) drains without gameplay
impact — the queue absorbs it, no `GameSession` blocks on a database
call. Existing `test_phase2_auth.py`/`test_phase3_rating.py` etc. pass
unmodified against the Postgres-backed repositories via the same
parametrized-fixture pattern used in Phase 1.

---

## Phase 5 — Multi-region rollout

**Goal:** the full target topology — regional Gateway+Shard pairs, a
region-aware Matchmaker, a replicated global control plane.

**Tasks:**
- Stand up a second region's full stack (Gateway, Shard, Matchmaker,
  Allocator replicas) pointed at a *replicated* Redis/NATS (e.g. Redis
  Cluster with cross-region replication, or a per-region Redis with an
  async replication bridge for the small slice of state that must be
  globally visible — the `game:{game_id}` and `room:{room_id}` directory
  keys specifically, since a player in one region must be able to join a
  room created in another).
- Matchmaker gains the region-affinity heuristic from `Server_Design.md`
  §1 Q2: prefer pairing within the same region/continent, fall back to
  cross-region pairing only past a wait-time threshold (reuses the exact
  timeout-then-widen pattern `MatchmakingService` already has for
  ELO-range expiry — same mechanism, a second axis).
- Game Allocator's placement preference: same-region as both matched
  players first, nearest region second.
- GeoDNS / anycast in front of the WS Gateway fleet so clients connect to
  their nearest region without a manual region picker.

**Definition of done:** a client in region A can create a room and a
client in region B can join it and play a full game, with the Game
Server Shard placed in whichever region the Allocator chose — verified
by checking which shard actually hosts the session, not just that the
game worked. A simulated region outage (kill an entire region's
Gateway+Shard deployment) results in new connections from that region's
players routing to the next-nearest region, with existing cross-region
games elsewhere unaffected.

---

## Phase 6 — Resilience & Security Hardening

**Goal:** turn the failure-mode table in `Server_Design.md` §5 and the
security section §6 from design intent into tested behavior.

**Tasks:**
- Chaos-testing harness: scripted, repeatable fault injection for every
  row of `Server_Design.md`'s reliability table (kill a Gateway pod, kill
  a Shard pod, partition Redis, saturate the write-behind queue, drop a
  region) run against a staging environment on a schedule, not just once.
- Rate limiting at both Gateways (per-IP and per-account, on
  `LOGIN`/`REGISTER`/`MOVE` submission rate independent of game-logic
  validation).
- Session-token validation caching at the Gateway (short-TTL local cache
  in front of the Redis lookup) — add a metric for cache hit rate and an
  explicit test that a revoked/expired token is rejected within the
  cache's TTL window, not indefinitely trusted.
- Re-confirm (as an explicit, permanent test, not a one-time code review)
  that no `src`/`dst`/color trust ever crosses from a Gateway into a
  decision — the only legality authority is `GameSession.apply_move`
  inside a Shard. This is exactly the ownership-check bug fixed earlier
  in this project's history; the test that would have caught it
  (`test_black_cannot_move_whites_piece`) already exists and must keep
  passing unmodified through every phase above.

**Definition of done:** every chaos scenario has an automated pass/fail
assertion (not manual observation), runs in CI or a scheduled staging
job, and is green. Rate limits and token-cache TTLs are load-tested to
confirm they don't themselves become the bottleneck.

---

## Phase 7 — Full-Scale Load Test & Capacity Calibration

**Goal:** replace every estimated number in `Server_Design.md` §1 and §8
with a measured one, at a scale that meaningfully approximates the
target (10M concurrent players may not be affordable to *actually* run
in a pre-production load test — approximate via a smaller multiple with
the same per-shard/per-gateway ratios, and extrapolate linearly, which is
valid as long as Phase 3–5 already proved horizontal scale-out has no
hidden coordination bottleneck).

**Tasks:**
- Build (or adopt) a load-test client farm capable of simulating many
  concurrent `GameSession`-driving connections at the real move cadence
  (1 move/2s/player) — this is a first-class deliverable, not a
  throwaway script, since every future capacity decision depends on it.
- Measure, replacing the assumptions in `Server_Design.md` §8:
  concurrent games sustainable per Shard pod; concurrent connections
  sustainable per Gateway pod; sustained Postgres write-behind throughput
  before backlog grows unbounded; real cross-region latency distribution
  for the actual regions chosen.
- Re-run the bandwidth calculation from `Server_Design.md` §1 Q3 against
  *measured* payload sizes and message rates from this load test, not the
  estimated ones, and confirm (or revise) the recommendation to move
  `MOVE_BROADCAST`'s hot path to a delta-only payload.
- Publish the calibrated numbers back into `Server_Design.md` §8,
  closing out every open question it lists.

**Definition of done:** every "open question" in `Server_Design.md` §8
has a measured answer, and the per-pod capacity numbers used by the
Kubernetes HorizontalPodAutoscaler configs from Phase 3 are updated from
assumed to measured values.

---

## Rollback Strategy by Phase

| Phase | Rollback if it goes wrong |
|---|---|
| 0 | No-op — pure additions, nothing depends on them yet. |
| 1 | Config flag flips back to in-memory backends; Redis becomes unused again, not removed. |
| 2 | Revert to the monolithic `server/main.py` entrypoint; Gateway/Shard split entrypoints are additive, the old one isn't deleted until Phase 3 is stable. |
| 3 | Scale replicas back to one each; the K8s manifests support this as a config change, not a code change. |
| 4 | Shadow-write period means SQLite is still authoritative until the explicit cutover flag flips — cutover is reversible until the flag flips a second time to remove SQLite writes entirely (a deliberate, separate, later step). |
| 5 | Disable the second region's DNS entries; existing single-region traffic is unaffected since region-affinity is a preference, not a hard partition. |
| 6/7 | These phases harden and measure; they don't change production behavior by themselves, so "rollback" means reverting the specific rate-limit/cache config that regressed, not the phase as a whole. |

---

## What Never Changes Across Any Phase

Restated from `Server_Design.md`'s closing argument, because it's the
thing that makes every phase above a *deployment* change and not a
*rewrite*: `engine/` (the chess rules), `server/domain/`,
`server/services/game_session.py`,
`server/services/game_session_factory.py`, and the ELO math in
`server/domain/elo.py` are untouched from Phase 0 through Phase 7. Every
phase either moves *where* something runs or *what it talks to* for
state/storage — never *what decides whether a move is legal or who won*.
