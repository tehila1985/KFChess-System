# UI Architecture

This document explains the UI architecture, module responsibilities, runtime flow, and test structure.

## Overview

The UI layer is responsible for rendering, user input, and presentation state.
Game rules and authoritative state remain in the engine layer.

High-level direction:
- Engine owns game truth: legality, motion, collision, cooldown, score, game-over.
- UI reads immutable snapshots and renders frames.
- UI sends user actions back to the engine through a mapper/controller/facade boundary.
- Observer-based components consume UI events for side panels (moves, score, banner).

## Main Runtime Entry

Files: `ui/main.py`, `ui/runtime/game_loop.py`

Responsibilities:
- `ui/main.py`: thin entry point only.
- `ui/runtime/game_loop.py`: runtime orchestration and frame loop only.
- Load visual assets through `ui/resources/asset_loader.py`.
- Run the non-blocking frame loop:
  - handle pointer events,
  - left click routes through `ControllerOutcomeAdapter` for select/move,
  - right click maps to board position and triggers `facade.request_jump(...)`,
  - advance time (`AnimationClock`),
  - call `facade.tick(delta_ms)`,
  - render frame through `CompositeRenderer`,
  - display window.

Important render features:
- Piece animation states (`idle`, `move`, `jump`, rest states).
- Selection highlight for the chosen source square.
- Legal-destination highlights for selected piece.
- Cooldown visual overlay.
- Sidebars with per-side score and moves.

## Composition Root

### `ui/composition/container.py`
- Defines `AppContainer` with the UI runtime dependencies:
  - `GameFacade`,
  - `Controller`,
  - `BoardMapper`,
  - sidebar subscribers (`MovesFeed`, `ScorePanel`, `Banner`).
- `build_container(...)` wires board + engine + facade + UI subscribers.
- Keeps wiring out of the frame loop.

## UI Input Pipeline

### `ui/interaction/board_mapper.py`
- Converts pixel coordinates to board positions.
- Isolates pixel/grid mapping from the rest of the code.

### `ui/interaction/controller.py`
- Two-click input model:
  - first click selects source,
  - second click attempts move to destination.
- Handles click edge-cases:
  - outside board clears selection,
  - selecting same-color piece switches source,
  - frozen/cooldown piece selection can be ignored,
  - stale source selections are recovered safely.
- Delegates all legality to server/facade, no chess rules inside controller.
- Jump is intentionally not part of controller state-machine and is handled as a runtime action.

### `ui/interaction/controller_outcome.py`
- Normalizes controller result values to `ActionOutcome`.
- Keeps UI runtime logic independent from raw engine result enums.

### `ui/user_input/mouse_controller.py`
- Thin adapter that forwards pointer coordinates to controller click handling.

## State and Event Layer

### `ui/state/game_facade.py`
- Thin boundary around `GameEngine` for UI use.
- Exposes engine snapshot and helper queries (cooldown/game-over/legal destinations).
- Publishes UI-level events on observer bus:
  - `MoveAccepted`, `MoveRejected`,
  - `PieceArrived`, `PieceCaptured`,
  - `GameOver`.
- Detects completed motions by diffing active motions before/after tick.
- Detects captures from pre-tick destination occupancy.

### `ui/state/game_events.py`
- Dataclasses for event payloads.
- Move metadata includes side, piece type, and move timestamp for UI formatting.

### `ui/state/observer.py`
- Subject/event bus abstraction used by UI components.

### `ui/state/outcome.py`
- Defines `ActionOutcome` used by the UI flow.

## UI Components

### `ui/ui_components/moves_feed.py`
- Subscribes to `MoveAccepted`.
- Builds move history entries in chess-like notation.
- Stores separate lists for white and black sidebars.

### `ui/ui_components/score_panel.py`
- Subscribes to `PieceCaptured`.
- Maintains capture counts per side for display.

### `ui/ui_components/banner.py`
- Subscribes to game-level events.
- Displays transient or persistent status/banner messages.

## Animation and Rendering

### `ui/animation/`
- `animation_clock.py`: frame-time clock (`tick_ms`).
- `motion_predictor.py`: pixel interpolation for smooth motion rendering.
- `piece_animator.py`: animation helpers for piece state transitions.

### `ui/rendering/`
- `interfaces.py`: renderer protocol and immutable `RenderContext`.
- `renderers.py`:
  - `BoardRenderer` draws board, pieces, legal targets, cooldown overlay, active motions.
  - `HudRenderer` draws side panels, score, moves feed, banner and status line.
  - `CompositeRenderer` composes rendering pipeline by stage.
- `dirty.py`: `DirtyState` utility for frame invalidation decisions.

### `ui/vendor/img.py`
- Image wrapper over OpenCV operations.
- Handles alpha-safe text and overlay drawing.

## Asset and Runtime Config

### `ui/resources/asset_loader.py`
- Dedicated loader for board image, piece frames, overlays and HUD panel background.
- Centralizes sprite-size preprocessing and per-state fps extraction.

### `ui/config/app_config.py`
- Holds UI runtime constants/messages used by runtime and render flow.
- Avoids hard-coded strings and display constants in business/runtime logic.

### `ui/config/ui_config.py`
- Holds global UI defaults (window title, sidebar width, board cell sizing, skin name).
- Keeps static UI settings in a single place shared by runtime/composition/resources.

## Data Flow

1. User clicks in OpenCV window.
2. `main.py` forwards pointer events to `ui/runtime/game_loop.py`.
3. Left click path: `ControllerOutcomeAdapter` -> controller -> `GameFacade.request_move(...)`.
4. Right click path: mapper -> `GameFacade.request_jump(...)`.
5. Per frame, `facade.tick(dt)` advances simulation and publishes arrival/capture/game-over events.
6. `CompositeRenderer` executes board stage then HUD stage using `RenderContext`.
7. Observer subscribers update sidebars from published events.

## Boundaries and Invariants

- UI never mutates board state directly.
- Engine remains single source of truth.
- Rule legality always evaluated in `RuleEngine`.
- Controller remains stateless with respect to chess rules.
- Rendering is driven by immutable snapshots plus render context.
- Dependency wiring lives in `ui/composition/container.py`, not in rendering or controller code.

## Test Structure

All tests are now organized under `tests/` by domain.

### `tests/server/`
Server domain tests:
- Arbiter behavior
- Engine request/tick/snapshot behavior
- Rule engine and models
- Integration scenarios and runner scenarios

### `tests/ui/`
UI/domain-adapter tests:
- Mapper and controller behavior
- Facade event publishing
- Observer/event bus behavior
- UI component subscribers
- Animation and user input adapters
- Text-render oriented UI tests

This split keeps responsibilities clear and helps run focused suites:
- `pytest tests/server -q`
- `pytest tests/ui -q`

## Notes for Future Changes

- If adding a new visual overlay, keep state derivation in server/facade and draw only in `main.py`.
- If adding new user interactions, keep coordinate logic in mapper/controller; keep rules in server/rules.
- If adding new side panel data, prefer observer events and small subscriber components.
