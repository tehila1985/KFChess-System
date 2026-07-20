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

- `engine/` owns game truth: move legality, motion timing, collision resolution, score, game-over, and king capture handling.
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
- Connects input, the facade, and rendering.
- Reads all runtime defaults from `ui/config/app_config.py`.
- Uses `AnimationClock` to advance wall-clock-like time in the render loop.
- Emits frame updates through `CompositeRenderer` only when the frame is dirty.

Responsibilities of the runtime loop:
- handle left and right mouse actions,
- convert pointer state into engine or facade calls,
- advance simulation with `facade.tick(delta_ms)`,
- detect selection changes to gate rendering (only re-render on change),
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
4. If the frame is dirty (click, selection change, or observer event), `CompositeRenderer` draws board and HUD using the latest snapshot and context.

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
- Also contains `ControllerOutcomeAdapter`, which normalizes raw `RequestMoveResult`
  values into `ActionOutcome` objects for the runtime loop.
- Handles click edge cases:
  - outside-board clicks clear or preserve state safely,
  - selecting another piece updates the source,
  - stale or frozen selections are handled defensively,
  - controller does not contain chess rule logic.
- Delegates all move legality to the engine/facade boundary.

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
- Emits a runtime warning if a captured piece type has no configured score value.

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
- Maintains separate `white_entries` and `black_entries` move histories.

### `ui/ui_components/score_panel.py`
- Subscribes to `PieceCaptured`.
- Keeps capture point totals for each side.

### `ui/ui_components/banner.py`
- Subscribes to `GameOver`.
- Shows a persistent game-over message.

## Animation and Rendering

### `ui/animation/`
- `animation_clock.py`: frame-time clock utilities.
- `motion_predictor.py`: pixel interpolation for smooth motion.

### `ui/rendering/`
- `interfaces.py`: `IRenderer` protocol and `RenderContext` definition.
- `renderers.py`:
  - `BoardRenderer` draws board state, pieces, highlights, cooldown overlay, and active motions.
  - `HudRenderer` draws sidebars, score, moves, banner, and status line.
    Uses `_draw_side_panel(...)` to avoid duplicating left/right panel logic.
  - `CompositeRenderer` composes renderers in order.

### `ui/vendor/img.py`
- Image wrapper over OpenCV.
- Handles drawing, compositing, rectangle fills, and text operations.
- All color parameters follow BGR(A) channel order (OpenCV convention).

## Asset Loading and UI Config

### `ui/resources/asset_loader.py`
- Loads board art, cooldown art, piece frames, overlays, and sidebar background.
- Centralizes sprite resizing and frame-rate extraction.
- Reads all UI styling and token catalogs from config objects rather than hardcoded inline values.
- Preserves backward-compatible fallbacks for missing skins and asset folders.

### `ui/config/app_config.py`
The single configuration file for the entire UI layer. Contains:

| Dataclass | Purpose |
|---|---|
| `UiAssetsConfig` | Asset paths, board/piece pixel sizes |
| `UiOverlayStyleConfig` | Selection and legal-move overlay colours (BGRA) |
| `UiPanelStyleConfig` | Sidebar width and background colour (BGR) |
| `UiPieceCatalogConfig` | Piece token catalog and animation state names |
| `UiHudTextConfig` | Label strings for the HUD |
| `UiHudLayoutConfig` | Pixel positions for all HUD text elements |
| `UiColorPaletteConfig` | Centralised BGR colour palette for all HUD text |
| `UiFontConfig` | OpenCV font face and thickness |
| `UiInputConfig` | Left/right action names |
| `UiBoardConfig` | Cell size and default starting position |
| `UiLayoutConfig` | Overlay and panel sub-configs |
| `UiStatusTextConfig` | Status-line message strings |
| `UiRuntimeConfig` | Window title, fallback frame time |
| `UiThemeConfig` | Active skin name |

`AppConfig.__post_init__` validates that `board_size_px`, `cell_size_px`, and
`piece_size_px`/`piece_padding_px` are mutually consistent, catching misconfiguration
at startup rather than silently misaligning the board.

All colour values in config use OpenCV BGR(A) channel order and are suffixed
`_bgr` or `_bgra` to make the convention explicit.

## Rendering Pipeline

1. `load_ui_assets(DEFAULT_APP_CONFIG)` loads board art, overlays, and piece frame caches.
2. `BoardRenderer` renders the board snapshot, pieces, selection highlight, legal destinations, cooldown overlay, and active motions.
3. `HudRenderer` renders side panels (via `_draw_side_panel`), scores, move lists, banner (white text on dark box), and the status line.
4. `CompositeRenderer` applies renderers in sequence and returns the final frame.
5. `Img.show(...)` presents the frame in the OpenCV window.

The game loop only calls `renderer.draw(...)` when `needs_redraw` is `True`, avoiding
unnecessary work on idle frames.

Important visual features:
- piece animation states: `idle`, `move`, `jump`, and rest states,
- selected-source highlight,
- legal destination markers,
- cooldown fade overlay,
- side panels for score and move history,
- game-over banner (high-contrast white text on dark background fill),
- status line.

## Runtime State and Invariants

- UI never mutates the board directly.
- UI only renders immutable snapshots plus current `RenderContext`.
- Engine remains the single source of truth for rules and state changes.
- Rendering code does not decide legality or resolve outcomes.
- Controller code does not know chess rules.
- Engine interaction is centralized in `GameFacade`.
- Dependency wiring belongs in `ui/composition/container.py`.
- The runtime loop holds only one controller reference: `ControllerOutcomeAdapter`.
  `pending_src` is read from the adapter, not from the raw `Controller`.

## Test Layout

The test tree is split by domain and test type.

### `tests/ui/unit/`
Unit-style UI tests for isolated adapters and components:
- animation helpers (`test_animation.py`),
- board mapper and controller (`test_controller.py`, `test_ui.py`),
- facade event publishing (`test_game_facade.py`),
- observer/event bus (`test_observer.py`),
- UI component subscribers (`test_ui_components.py`).

### `tests/ui/integration/`
UI integration tests that exercise the runtime pointer-routing path:
- `test_runtime_jump.py`.

### `tests/engine/unit/`
Server-side unit tests for isolated logic:
- arbiter behavior,
- engine request/tick/snapshot behavior,
- board/model invariants,
- rule engine behavior,
- capture and scoring logic.

### `tests/engine/integration/`
Server integration and end-to-end scenario tests:
- full engine/controller/rendering scenarios,
- command-runner scenarios,
- capture flow and game-over flow.

Focused suites:
```
pytest tests/ui/unit -q
pytest tests/ui/integration -q
pytest tests/engine/unit -q
pytest tests/engine/integration -q
```

## Notes for Future Changes

- If you add a new overlay or visual effect, derive its state in the facade or runtime config and keep drawing logic in the renderer.
- If you add a new input gesture, keep coordinate mapping in the mapper/controller layer and avoid rule logic in the UI.
- If you add new side-panel data, prefer observer events plus small subscriber components.
- If you add new assets or skins, extend the config objects and asset loader fallbacks instead of hardcoding file names.
- If you add a new piece type, add its score to `DEFAULT_CONFIG.piece_score`; the facade will emit a `warnings.warn` at runtime if a captured piece type has no configured score.
