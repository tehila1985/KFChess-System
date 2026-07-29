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

**On infrastructure this plan doesn't have yet:** Phases 0–2 and 4 are
fully provable with tools already available in a normal dev environment —
Docker Desktop running Redis/NATS/Postgres containers, and Python
subprocesses standing in for separate hosts. Phases 3, 5, 6, and 7
originally assumed a live Kubernetes cluster, multiple real regions, a
staging environment with a scheduler, and a load-generating fleet — none
of which exist in a local sandbox (this repo's own dev environment has
`kubectl` installed but no cluster behind it, for instance). Rather than
write untested manifests and untestable claims for infrastructure that
isn't there, those four phases below are scoped to what a single local
machine with Docker actually *can* prove — real placement logic, real
concurrency-safety, real chaos scenarios, real measured local capacity
numbers — with the genuinely infrastructure-bound parts (a live cluster,
real regions, a staging scheduler, cloud-scale numbers) named explicitly
as deferred, not faked.

---

## Phase Overview

| Phase | Goal | New infra introduced | Code touched | Can run in prod after this phase? |
|---|---|---|---|---|
| 0 | Seams or it doesn't happen | none (docker-compose gets new services, unused) | interfaces only | Yes — behavior-identical |
| 1 | Shared state, still 1 process | Redis | `ConnectionHub`, `MatchmakingService`, `RoomService` get Redis-backed variants | Yes — identical behavior, now horizontally-*ready* |
| 2 | Real Gateway/Shard network hop, still 1 of each | NATS | new `gateway/` and `shard/` entrypoints | Yes — same capacity as today, new failure modes to watch |
| 3 | Horizontal scale-out, one region — proven locally | multiple local Gateway/Shard processes, docker-compose scale; K8s manifests written but not applied (no cluster in this environment) | Game Allocator gets real placement logic | Locally proven; real cluster/autoscaling behavior deferred until a cluster exists |
| 4 | Durable store swap | PostgreSQL, write-behind queue (NATS JetStream) | `UserRepository`/`GameRepository` Postgres impls | Yes |
| 5 | Multi-region — affinity logic proven with simulated regions | two locally-run shard/gateway groups tagged by region; no real second region/GeoDNS available here | Matchmaker region-affinity | Locally proven decision logic; real cross-region latency/GeoDNS deferred until real regions exist |
| 6 | Resilience & security hardening — runnable on demand | local chaos script, rate limiter | — | Hardens what's already live; scheduled staging runs deferred until a staging environment exists |
| 7 | Load test & capacity calibration at local-machine scale | local load-test harness | capacity constants everywhere | Confirms real per-process numbers on this machine; cloud-scale figures are an explicit formula, not a measurement |

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

## Phase 3 — Horizontal scale-out (one region, proven locally — no live cluster required)

**Reality check:** this environment has `kubectl` installed but no
cluster behind it — no kind/k3d/minikube, no cloud cluster. Writing K8s
YAML and calling the phase "done" without ever applying it would be
exactly the kind of untested claim this plan's own discipline (green
tests before moving on) argues against. Instead, this phase proves the
*logic* that has to be correct before a cluster ever matters — real
placement decisions, real concurrency-safety — using what's already
available locally: multiple `gateway/main.py` / `shard/main.py`
processes on one machine (the same subprocess harness Phase 2's e2e test
already uses, extended from 1 shard to N), plus `docker compose` for the
supporting Redis/NATS/Postgres containers. The K8s manifests are still
written, since they're needed the moment a real cluster exists, but their
correctness claim stops at "schema-valid YAML" — not "deployed and
load-tested," which needs infrastructure this phase doesn't have.

**Tasks:**
- Game Allocator becomes real: consumes match/room-ready events, reads
  `shard:{id}:load` keys from Redis (the heartbeat key Phase 2 already
  writes gets a load-count field added), picks the least-loaded of N
  locally-running Shard processes, writes the `game:{game_id}` mapping.
  Verified by checking which shard process actually ended up with the
  game, not just that the game worked.
- Matchmaker becomes its own replicated loop: run 2 local processes both
  reading/writing the Redis sorted set from Phase 1, with an explicit
  concurrency-safety test — two Matchmaker replicas racing to pair the
  same two queued players must not produce two games (fully provable
  locally with two Python processes sharing one Redis; no cluster
  needed).
- A local horizontal-scale-out harness (extends Phase 2's
  subprocess-spawning test helpers): starts N Gateway + M Shard
  processes, drives dozens-to-low-hundreds of concurrent simulated games
  through them, kills and restarts one Shard process mid-run, and
  asserts only *that* Shard's own in-flight games were affected — the
  rest kept running. This is the local proxy for "rolling restart of the
  fleet," at a scale this one machine can actually generate.
- Kubernetes/K3s manifests (`deploy/k8s/`): separate Deployments for API
  Gateway, WS Gateway, Matchmaker, Game Allocator, Game Server Shard,
  each with its own HorizontalPodAutoscaler target metric (connection
  count for WS Gateway, concurrent-game-count/CPU for Shard, per
  `Server_Design.md` §4's explicit warning against conflating these).
  Written now so they're ready the moment a real cluster exists;
  validated here only via `kubectl apply --dry-run=client -f
  deploy/k8s/` (schema correctness), not deployed.

**Definition of done:** the local N-Shard/M-Gateway harness survives
killing and restarting one Shard process with no client-visible loss
beyond that shard's own in-flight games; two local Matchmaker replicas
never double-pair a player (explicit concurrency test, not "seemed fine
manually"); `deploy/k8s/*.yaml` passes `kubectl apply --dry-run=client`.
Explicitly **not** claimed by this phase: real autoscaling behavior, real
load-balancer/ingress behavior, or any number that depends on actual
cluster networking — those need a real cluster and are deferred to
whenever one is provisioned, at which point this phase's manifests are
the starting point, not a rewrite.

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

## Phase 5 — Multi-region rollout (affinity logic proven locally with simulated regions)

**Reality check:** there is no second region, no GeoDNS, and no real
cross-region network reachable from this environment. This phase proves
the *region-affinity decision logic* — the part that's actually code and
actually testable without real infrastructure — using two locally-run
shard/gateway groups tagged with a fake region label. Real GeoDNS/anycast
and real cross-region latency numbers are explicitly deferred to whenever
real regional infrastructure exists; fabricating them here would be a
number with no meaning behind it.

**Tasks:**
- Run two local Gateway+Shard+Allocator groups tagged `region=local-a` /
  `region=local-b` via a config value (not real geography), both against
  the *same* local Redis/NATS — a real second region would need
  cross-region replication of the `game:{game_id}`/`room:{room_id}`
  directory keys, but simulating that replication's latency locally
  would just be another fabricated number, so this phase tests the
  affinity *decision*, not the replication itself.
- Matchmaker gains the region-affinity heuristic from `Server_Design.md`
  §1 Q2: prefer pairing within the same region tag, fall back to
  cross-region pairing only past a wait-time threshold (reuses the exact
  timeout-then-widen pattern `MatchmakingService` already has for
  ELO-range expiry — same mechanism, a second axis).
- Game Allocator's placement preference: same-region as both matched
  players first, other region second — verified by checking which of
  the two local shard groups actually got the game.
- An artificial delay (e.g. `asyncio.sleep` in a test-only wrapper around
  the cross-region path) standing in for real inter-region latency,
  used only to prove the affinity heuristic actually avoids crossing it
  when possible — not presented as a real latency measurement.

**Definition of done:** a simulated client tagged `region=local-a`
matched against one tagged `region=local-b` only crosses regions after
the configured wait threshold, and the Game Allocator places the game in
the majority region when there is one — both verified by inspecting
which local shard group actually got the game. Explicitly **not**
claimed by this phase: real cross-region latency numbers, real GeoDNS
behavior, or a real replicated control plane — those need real regions
and are deferred until they exist.

---

## Phase 6 — Resilience & Security Hardening (runnable on demand, not on a schedule)

**Reality check:** there is no staging environment and no CI/cron runner
in this environment to run chaos tests "on a schedule." This phase builds
the chaos harness and the hardening it verifies as real, runnable code —
runnable on demand, locally, against the docker-compose stack — rather
than skipping it entirely. Scheduling it against a real staging
environment later is an ops/config step, not a code change, once that
environment exists.

**Tasks:**
- Chaos-testing harness (`scripts/chaos/`): scripted, repeatable fault
  injection runnable locally on demand — kill a Gateway process, kill a
  Shard process, `docker network disconnect` to partition Redis or NATS
  from the rest of the compose stack, saturate the Phase 4 write-behind
  queue — one scenario per row of `Server_Design.md`'s reliability
  table, each with an automated pass/fail assertion, not manual
  observation.
- Rate limiting at the Gateway (per-IP and per-account, on
  `LOGIN`/`REGISTER`/`MOVE` submission rate independent of game-logic
  validation) — a Redis-backed token bucket so the limit holds across
  multiple local Gateway processes; fully testable locally.
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

**Definition of done:** every scenario in `scripts/chaos/` has an
automated pass/fail assertion and passes when run locally on demand.
Rate limits and token-cache TTLs are exercised by the Phase 7 local
load-test harness to confirm they don't themselves become the
bottleneck at the scale this machine can generate. Explicitly **not**
claimed by this phase: a scheduled staging job — that needs a staging
environment and a scheduler, both deferred until they exist.

---

## Phase 7 — Load Test & Capacity Calibration (at local-machine scale)

**Reality check:** 10M concurrent players can't be simulated on one
development machine, and there's no fleet of load-generating hosts
available here. This phase measures real per-process capacity numbers
*on this machine* — genuinely measured, not estimated — and turns the
cloud-scale numbers in `Server_Design.md` §1/§8 into an explicit formula
(measured local per-shard/per-gateway capacity × horizontal replica
count) rather than pretending a local run can validate a cloud-scale
number directly.

**Tasks:**
- Build a local load-test harness (`scripts/loadtest/`) simulating many
  concurrent `GameSession`-driving connections at the real move cadence
  (1 move/2s/player) against the Phase 2/3 local Gateway/Shard processes
  — a first-class, reusable script, not a throwaway, since every future
  capacity decision depends on it.
- Measure, on this machine: concurrent games sustainable per single
  Shard process before latency/CPU degrades; concurrent connections
  sustainable per single Gateway process; sustained Postgres
  write-behind throughput (Phase 4) before the JetStream backlog grows
  unbounded.
- Re-run the bandwidth calculation from `Server_Design.md` §1 Q3 against
  *measured* payload sizes and message rates from this local load test —
  payload size doesn't change with scale, so this particular number
  stays meaningful even measured locally — and confirm or revise the
  recommendation to move `MOVE_BROADCAST`'s hot path to a delta-only
  payload.
- Publish the measured local-machine numbers into `Server_Design.md` §8
  alongside the explicit extrapolation formula for cloud scale
  (measured-per-pod × replica count), clearly labeled "measured locally"
  vs. "extrapolated" so the two are never confused later.

**Definition of done:** concurrent-games-per-Shard-process,
concurrent-connections-per-Gateway-process, and write-behind drain rate
are all real measured numbers from a run on this machine, not estimates.
`Server_Design.md` §8 is updated with those measured numbers and the
extrapolation formula. Explicitly **not** claimed by this phase: a
validated cloud-scale number — that requires the real fleet Phase 3/5's
cloud rollout would eventually provide.

---

## Rollback Strategy by Phase

| Phase | Rollback if it goes wrong |
|---|---|
| 0 | No-op — pure additions, nothing depends on them yet. |
| 1 | Config flag flips back to in-memory backends; Redis becomes unused again, not removed. |
| 2 | Revert to the monolithic `server/main.py` entrypoint; Gateway/Shard split entrypoints are additive, the old one isn't deleted until Phase 3 is stable. |
| 3 | Stop the extra local Shard/Gateway processes and go back to one of each; the Game Allocator's "pick least-loaded" logic degrades to "pick the only one" automatically. Once a real cluster exists, scaling replicas back to one there is a manifest config change, not a code change. |
| 4 | Shadow-write period means SQLite is still authoritative until the explicit cutover flag flips — cutover is reversible until the flag flips a second time to remove SQLite writes entirely (a deliberate, separate, later step). |
| 5 | Disable the second local region tag / stop pairing across it; existing single-region traffic is unaffected since region-affinity is a preference, not a hard partition. Once real regions exist, disabling GeoDNS entries for one is the equivalent production step. |
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
