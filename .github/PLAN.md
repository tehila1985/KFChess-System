# Kung-Fu Chess UI — Plan & Build Log

This documents the full `ui/` build: the constraints it had to work within, the
folder structure, the order it was built in, and the reasoning behind the
non-obvious decisions. The original stage-by-stage implementation plan lived
at a local path outside the repo; this file is the durable, in-repo version of
it, updated to match what was actually built (including things that changed
along the way).

## Context and constraints

- `server/` (the real-time chess engine) was already complete before this
  work started. `ui/` began as an empty folder with a placeholder README.
- Course rule: **all graphics must go through the provided `Img` class**
  (vendored at `ui/vendor/img.py`) — no PyGame/SFML/LWJGL. `Img` itself only
  has 4 methods (`read`, `draw_on`, `put_text`, `show`) and has no game-loop,
  mouse-handling, or animation support — all of that had to be built on top of
  it, without ever drawing pixels through anything but `Img.draw_on`.
- The repo must not depend on the course's GitHub repo (`KamaTechOrg/CTD26`)
  at runtime or build time — the `Img` class and sprite assets were copied in
  as real files, not submodules/references.

## Folder structure

```
ui/
  server_bridge.py       # inserts server/ onto sys.path — imported first, before any model/engine import
  main.py                 # entrypoint: builds the facade/controller/renderer, runs the loop
  ui_config.py             # UI-only constants (window title, sidebar width, skin name)

  vendor/img.py             # the course-provided Img class, verbatim

  assets/
    board.png                     # course-provided board background
    selection_highlight.png        # pre-baked transparent border overlay (selected cell)
    halt_flash.png                  # pre-baked translucent red overlay (mid-flight halt)
    panel_background.png             # solid-color HUD sidebar background
    pieces1/, pieces3/                # sprite sets — see "Skins" below

  IMG/                    # source art for the "pieces3" skin (see Skins) + a board photo (unused)
  tools/
    generate_pieces3_skin.py  # build-time script: turns ui/IMG/ into the pieces3 skin

  graphics/
    window.py              # non-blocking cv2 loop: imshow + setMouseCallback + waitKey(1) + close-detect
    sprite_loader.py         # loads config.json + Img frames per (piece_code, state), cached
    renderer.py              # composes board + animated pieces + selection/halt overlays per frame
    hud_renderer.py           # composes the board canvas with the sidebar (score + moves log)

  animation/
    animation_clock.py       # perf_counter-based dt_ms, injectable time source
    piece_animator.py         # per-piece state machine (idle/move/jump/short_rest/long_rest)
    motion_predictor.py        # pure lerp: (src_px, dst_px, t) -> pixel

  user_input/
    mouse_controller.py        # cv2 mouse-callback adapter -> server's Controller.click(x, y)
    (named user_input/, not input/ — server/input/ already exists, and since
    server/ sits ahead of ui/ on sys.path, ui/input/ would have been silently
    unreachable under the shared package name)

  state/
    game_events.py            # MoveAccepted, MoveRejected, PieceArrived, PieceCaptured,
                                # PieceHalted, Promotion, GameOver dataclasses
    snapshot_diff.py            # pure fn: turns a completed pending motion into event(s);
                                  # also FrozenSnapshot (see "Bugs found" below)
    observer.py                  # Subject: subscribe(callback) / publish(event) — no game knowledge
    game_facade.py                 # GameFacade(engine): request_move/request_jump/tick(dt_ms);
                                     # owns the pending-motion table; the one Subject instance

  ui_components/             # small Observer subscribers, each independent of the render loop
    moves_log_panel.py
    score_panel.py
    player_labels.py
    game_over_banner.py
    halt_flash.py

  tests/
    conftest.py                # puts server/ on sys.path for pytest, same as server_bridge.py does
    unit/test_*.py              # 57 tests covering every pure-logic module above
```

## Skins

Two sprite sets exist under `ui/assets/`, selected via `ui_config.SKIN`:

- **`pieces1`** — the course-provided set. Hand-drawn 5-frame sequences per
  state, each with its own `config.json` (`frames_per_sec`, `is_loop`,
  `next_state_when_finished`).
- **`pieces3`** (current default) — built from the user's own single static
  image per piece (`ui/IMG/<CODE>.png`, e.g. `QW.png` = white queen). Since
  there's only one source frame per piece (no hand-drawn animation), each
  state's 5 frames are generated *procedurally* by
  `ui/tools/generate_pieces3_skin.py`, using simple affine transforms anchored
  at the piece's bottom edge so it never appears to float off its square:
  - `idle` — a subtle scale "breathing" pulse, looping.
  - `move` — a lean (horizontal shear), looping.
  - `jump` — a real squash-and-stretch arc, non-looping → `short_rest`.
  - `short_rest` / `long_rest` — a settling wobble that decays to neutral,
    non-looping → `idle`.

  Output matches `pieces1`'s exact folder/config convention, so
  `SpriteLoader`/`PieceAnimator` needed zero code changes to support it —
  only `ui_config.SKIN` points at the new name. Re-run the generator after
  changing anything in `ui/IMG/`:
  ```bash
  uv run python ui/tools/generate_pieces3_skin.py
  ```
  A matching board photo (`ui/IMG/OOAD630.jpg`) was tried as a `board.png`
  replacement too, but its playing surface isn't a clean full-bleed 8×8 crop —
  stretched to the canvas it misaligned the squares against piece positions,
  so `board.png` stayed the course-provided one.

## Build order

Each stage was independently runnable and manually verified (rendered frames
to PNG and inspected them, or drove the real `GameFacade`/`Controller` with
scripted clicks) before moving to the next.

1. **Vendoring & wiring** — copied `Img`, `board.png`, `pieces1/` in;
   `server_bridge.py`; a smoke-test `main.py` that built a `GameEngine` and
   printed one token.
2. **Static render** — `SpriteLoader` + `BoardRenderer` draw the board and
   every piece's idle sprite once.
3. **Non-blocking loop** — `Window` replaces `Img.show()`'s blocking
   `imshow`+`waitKey(0)` with a real per-frame loop; `Clock` measures dt;
   an FPS overlay confirms it.
4. **Idle animation** — `PieceAnimator` drives frame advancement from each
   state's `config.json`.
5. **Mouse input** — `MouseController` routes clicks into server's own
   `Controller`/`BoardMapper`, unmodified; selection highlighted via a
   pre-baked overlay asset (kept inside the "only `Img` draws pixels" rule).
6. **Real-time motion interpolation** — `GameFacade` predicts each accepted
   move/jump's travel time using the server's own
   `MOVE_TRAVEL_TIME_PER_CELL`/`JUMP_TRAVEL_TIME` constants (never
   re-derived), since the engine's snapshot only ever shows a piece "resting
   at source" or "resting at destination" — never mid-flight.
   `motion_predictor.interpolate_pixel` lerps the drawn position each frame;
   the animator plays `move`/`jump` meanwhile and carries over to
   `next_state_when_finished` on a clean arrival instead of snapping straight
   to idle.
7. **Observer/event system** — `Subject`/`game_events`/`snapshot_diff` land;
   `GameFacade` becomes the sole publisher. `MoveAccepted`/`MoveRejected` fire
   synchronously from the engine's `MoveResult`; `PieceArrived`,
   `PieceCaptured`, `PieceHalted`, `Promotion`, `GameOver` are derived once a
   pending motion's predicted duration elapses, by diffing a frozen
   pre-tick snapshot against the post-tick one.
8. **Moves-log sidebar** — `MovesLogPanel` subscribes and renders a
   human-readable, algebraic-notation history; `HudRenderer` composes it
   into a wider scene alongside the board.
9. **Score panel** — `ScorePanel` subscribes to `PieceCaptured` and tallies
   captures per side; fully derived, since the engine has no scoring concept.
10. **Polish** — `PlayerLabels` (static names), `GameOverBanner` (a "GAME
    OVER" banner on king capture), `HaltFlashTracker` (a brief red flash on a
    mid-flight same-color halt).
11. **Real unit tests** — 57 tests under `ui/tests/unit/`, covering every
    pure-logic module (see "Testing" below).
12. **Cooldown restored** (server-side, not originally in this plan) — see
    "Later additions".
13. **Custom art skin (`pieces3`)** (not originally in this plan) — see
    "Skins" above.

## Design decisions worth knowing

- **Observer lives in `ui/`, not in `server/`.** `server/` was already fully
  tested with a clean-architecture goal, and the UI is already the sole
  caller of `engine.wait()`, making it the natural place to inspect what
  changed immediately after each call — zero server changes needed.
- **Client-side motion prediction, reconciled every tick.** Because the
  engine never exposes a mid-flight position, all animation smoothness is a
  client-side guess, corrected against the real snapshot once the predicted
  duration elapses. Four outcomes all fall out of the same
  create/drop-per-occupied-cell logic in `BoardRenderer`, with no
  special-casing: a clean arrival (animator carried over to keep playing its
  rest animation), a stale-target cancellation (piece never left, animator
  untouched), a mid-flight same-color halt (piece rests somewhere new, fresh
  animator), a mid-flight kill (piece's animator just disappears).
- **A real bug found along the way:** `GameEngine.snapshot()` returns a thin
  *live view* over the engine's own mutable `Board`, not a real point-in-time
  copy — reading an "earlier" snapshot again after `engine.wait()` shows the
  *new* state, silently breaking any before/after diff. `snapshot_diff.
  FrozenSnapshot` copies every token out up front to fix this; it's the
  reconciliation logic's dependency, not a general-purpose replacement for
  `GameSnapshot`.
- **Two package-name collisions with `server/`, both fixed:** `ui/input/`
  would have collided with `server/input/` (server sits ahead of `ui/` on
  `sys.path`, so the ui-side module would have been silently unreachable) —
  renamed to `ui/user_input/`. `ui/config.py` would have collided with
  `server/config.py` — named `ui_config.py` instead.
- **On-screen extras (selection highlight, halt flash) are pre-baked PNG
  overlays drawn via `Img.draw_on`,** not raw `cv2.rectangle` calls — keeping
  every visible pixel drawn through `Img`, per the course rule, even for
  things `Img` itself has no primitive for.

## Later additions (outside the original 9-stage plan)

- **Cooldown after arrival, restored server-side.** Git history showed this
  existed once (`820a921`) and was deliberately removed (`be5f1b8`) because
  it failed the course's official grading suite at the time. It was
  restored anyway, as an explicit, informed decision — see
  `server/config.py` (`COOLDOWN_MS`), `server/realtime/real_time_arbiter.py`
  (`start_cooldown`/`is_on_cooldown`), and `server/engine/game_engine.py`.
  Needed zero changes on the `ui/` side — `GameFacade`/`Controller` already
  treat a cooldown rejection like any other illegal move.
- **The `pieces3` custom-art skin** — see "Skins" above.

## Testing

Pure-logic pieces have real `pytest` unit tests (`ui/tests/unit/`, 57 tests):
`Subject`, `Clock`, `interpolate_pixel`, `PieceAnimator` (fake sprite loader,
no real image loading), `snapshot_diff` (every reconciliation case, plus a
regression test for the live-vs-frozen snapshot bug), `GameFacade` (against a
**real** `GameEngine`/`Board`, deliberately — the whole point of `GameFacade`
is reconciling against the engine's actual timing, so a mock would risk
hiding the exact kind of integration bug a fake can't reproduce), and the
small `ui_components`.

```bash
uv run python -m pytest ui/tests/unit -v    # 57 tests
uv run python -m pytest server              # 241 tests, unaffected by any of this
```

Rendering, animation feel, and click responsiveness aren't practically
automatable — see `ui/README.md`'s manual-playthrough checklist for what to
eyeball instead.

## Running it

```bash
uv run python ui/main.py
```
