# UI Architecture

This document describes the UI layer, its runtime flow, module boundaries, configuration surface, asset loading, rendering pipeline, and the current test layout.

## Purpose

The UI is responsible for:
- rendering the board and HUD,
- collecting user input,
- converting user intent into engine-safe actions,
- presenting engine snapshots and observer events,
- keeping all chess rules and authoritative state out of the UI.

The UI must remain a presentation layer only. It may interpret user events and render derived state, but it must not decide move legality, resolve collisions, score captures, or mutate the board directly.

## High-Level Boundaries

- `server/` owns game truth: move legality, motion timing, collision resolution, score, game-over, and king capture handling.
- `ui/` owns the OpenCV window, interaction adapters, event subscribers, and frame rendering.
- `ui/state/game_facade.py` is the only UI-facing boundary that touches `GameEngine` directly.
- `ui/composition/container.py` is the wiring root for the UI runtime.

## Runtime Entry Points

Files:
- `ui/main.py`
- `ui/runtime/game_loop.py`

### `ui/main.py`
- Thin executable entry point.
- Calls `run_game()` and does not contain runtime policy.

### `ui/runtime/game_loop.py`
- Coordinates the frame loop.
- Connects input, the facade, rendering, and dirty-state management.
- Reads runtime defaults from `ui/config/app_config.py` and `ui/config/ui_config.py`.
- Uses `AnimationClock` to advance wall-clock-like time in the render loop.
- Emits frame updates through `CompositeRenderer`.

Responsibilities of the runtime loop:
- handle left and right mouse actions,
- convert pointer state into engine or facade calls,
- advance simulation with `facade.tick(delta_ms)`,
- mark and clear dirty UI state,
- render and present the final OpenCV frame,
- terminate on `q`, `ESC`, or window close.

## Interaction Flow

### Left click path
1. OpenCV captures pointer coordinates.
2. `ControllerOutcomeAdapter` converts controller return values to `ActionOutcome`.
3. `Controller` manages the two-click select/move state machine.
4. `GameFacade.request_move(...)` forwards the request into the server layer.

### Right click path
1. OpenCV captures pointer coordinates.
2. `BoardMapper` converts the click into a board position.
3. `GameFacade.request_jump(...)` sends the jump request to the server.

### Per-frame path
1. `AnimationClock.tick_ms()` computes elapsed milliseconds.
2. `GameFacade.tick(delta_ms)` advances the engine.
3. `GameFacade` publishes UI events for motion completion, captures, and game-over.
4. `CompositeRenderer` draws board and HUD using the latest snapshot and context.

## Composition Root

File: `ui/composition/container.py`

`build_container(...)` wires together:
- `Board`,
- `RuleEngine`,
- `RealTimeArbiter`,
- `GameEngine`,
- `GameFacade`,
- `BoardMapper`,
- `Controller`,
- observer-driven UI components (`MovesFeed`, `ScorePanel`, `Banner`).

The container keeps construction and dependency wiring out of the runtime loop and rendering classes.

## Input and Control Layer

### `ui/interaction/board_mapper.py`
- Converts pixel coordinates into board positions.
- Keeps pixel/grid math isolated from controller logic.
- Used both by the runtime loop and by any click-to-grid UI adapter.

### `ui/interaction/controller.py`
- Implements the two-click selection model:
  - first click selects a source,
  - second click requests a move.
- Handles click edge cases:
  - outside-board clicks clear or preserve state safely,
  - selecting another piece updates the source,
  - stale or frozen selections are handled defensively,
  - controller does not contain chess rule logic.
- Delegates all move legality to the engine/facade boundary.

### `ui/interaction/controller_outcome.py`
- Normalizes controller responses to `ActionOutcome`.
- Keeps runtime code independent from raw engine result enums.

### `ui/user_input/mouse_controller.py`
- Small adapter for pointer-to-controller forwarding.

## State and Event Layer

### `ui/state/game_facade.py`
- Thin UI-facing wrapper around `GameEngine`.
- Exposes engine snapshot and queries for:
  - legal destinations,
  - cooldown state,
  - game-over state.
- Publishes UI-level observer events:
  - `MoveAccepted`,
  - `MoveRejected`,
  - `PieceArrived`,
  - `PieceCaptured`,
  - `GameOver`.
- Diffs active motions before and after `tick()` to infer completed motion events.
- Detects captures from the destination occupancy before the tick resolves.

### `ui/state/game_events.py`
- Dataclasses for UI event payloads.
- Carries move metadata such as side, piece type, source/destination, and timestamps.

### `ui/state/observer.py`
- Lightweight event bus used by UI components.
- Supports subscribe, publish, and unsubscribe semantics.

### `ui/state/outcome.py`
- Defines `ActionOutcome` for controller/runtime normalization.

## UI Subscriber Components

### `ui/ui_components/moves_feed.py`
- Subscribes to `MoveAccepted`.
- Formats move notation for the side panels.
- Maintains separate white and black move histories.

### `ui/ui_components/score_panel.py`
- Subscribes to `PieceCaptured`.
- Keeps capture counts for each side.

### `ui/ui_components/banner.py`
- Subscribes to game-state events.
- Shows transient or persistent status messages.

## Animation and Rendering

### `ui/animation/`
- `animation_clock.py`: frame-time clock utilities.
- `motion_predictor.py`: pixel interpolation for smooth motion.
- `piece_animator.py`: animation-state placeholder for pieces keyed by token.

### `ui/rendering/`
- `interfaces.py`: renderer protocol and `RenderContext` definition.
- `dirty.py`: `DirtyState` helper for frame invalidation.
- `renderers.py`:
  - `BoardRenderer` draws board state, pieces, highlights, cooldown overlay, and active motions.
  - `HudRenderer` draws sidebars, score, moves, banner, and status line.
  - `CompositeRenderer` composes renderers in order.

### `ui/vendor/img.py`
- Image wrapper over OpenCV.
- Handles drawing, compositing, and text operations in a safer API.

## Asset Loading and UI Config

### `ui/resources/asset_loader.py`
- Loads board art, cooldown art, piece frames, overlays, and sidebar background.
- Centralizes sprite resizing and frame-rate extraction.
- Reads all UI styling and token catalogs from config objects rather than hardcoded inline values.
- Preserves backward-compatible fallbacks for missing skins and asset folders.

### `ui/config/app_config.py`
- Holds UI asset sizing, overlay colors, panel styles, input actions, board defaults, HUD labels, and status strings.
- Keeps magic values out of runtime and rendering code.
- Serves as the main configuration object injected into asset loading and runtime logic.

### `ui/config/ui_config.py`
- Holds shared UI defaults such as window title, board cell size, sidebar width, and skin name.
- Provides stable defaults for composition and resource loading.

## Rendering Pipeline

1. `load_ui_assets(DEFAULT_APP_CONFIG)` loads board art, overlays, and piece frame caches.
2. `BoardRenderer` renders the board snapshot, pieces, selection highlight, legal destinations, cooldown overlay, and active motions.
3. `HudRenderer` renders side panels, scores, move lists, banner text, and the status line.
4. `CompositeRenderer` applies renderers in sequence and returns the final frame.
5. `Img.show(...)` presents the frame in the OpenCV window.

Important visual features:
- piece animation states: `idle`, `move`, `jump`, and rest states,
- selected-source highlight,
- legal destination markers,
- cooldown fade overlay,
- side panels for score and move history,
- banner and status line.

## Runtime State and Invariants

- UI never mutates the board directly.
- UI only renders immutable snapshots plus current `RenderContext`.
- Engine remains the single source of truth for rules and state changes.
- Rendering code does not decide legality or resolve outcomes.
- Controller code does not know chess rules.
- Engine interaction is centralized in `GameFacade`.
- Dependency wiring belongs in `ui/composition/container.py`.

## Test Layout

The test tree is now split by domain and test type.

### `tests/UI/unit/`
Unit-style UI tests for isolated adapters and components:
- animation helpers,
- board mapper and controller,
- controller outcome normalization,
- facade event publishing,
- observer/event bus,
- UI component subscribers,
- text-render-style UI behavior,
- mouse/controller adapter behavior.

### `tests/UI/integration/`
UI integration tests that exercise the runtime pointer-routing path:
- `test_runtime_jump.py`.

### `tests/SERVER/unit/`
Server-side unit tests for isolated logic:
- arbiter behavior,
- engine request/tick/snapshot behavior,
- board/model invariants,
- rule engine behavior,
- capture and scoring logic.

### `tests/SERVER/integration/`
Server integration and end-to-end scenario tests:
- full engine/controller/rendering scenarios,
- command-runner scenarios,
- capture flow and game-over flow.

This split lets you run focused suites:
- `pytest tests/UI/unit -q`
- `pytest tests/UI/integration -q`
- `pytest tests/SERVER/unit -q`
- `pytest tests/SERVER/integration -q`

## Notes for Future Changes

- If you add a new overlay or visual effect, derive its state in the facade or runtime config and keep drawing logic in the renderer.
- If you add a new input gesture, keep coordinate mapping in the mapper/controller layer and avoid rule logic in the UI.
- If you add new side-panel data, prefer observer events plus small subscriber components.
- If you add new assets or skins, extend the config objects and asset loader fallbacks instead of hardcoding file names.
