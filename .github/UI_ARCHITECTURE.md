# UI Architecture

This document explains the UI architecture, module responsibilities, runtime flow, and test structure.

## Overview

The UI layer is responsible for rendering, user input, and presentation state.
Game rules and authoritative state remain in the engine layer.

High-level direction:
- Engine owns game truth: legality, motion, collision, cooldown, score, game-over.
- UI reads immutable snapshots and renders frames.
- UI sends user actions back to the engine through a facade/controller boundary.
- Observer-based components consume UI events for side panels (moves, score, banner).

## Main Runtime Entry

File: `ui/main.py`

Responsibilities:
- Build the game stack (`Board`, `RuleEngine`, `RealTimeArbiter`, `GameEngine`, `GameFacade`).
- Configure mapper/controller and UI subscribers (`MovesFeed`, `ScorePanel`, `Banner`).
- Load visual assets (board, sprites, overlays).
- Run the non-blocking frame loop:
  - handle click events,
  - advance time (`AnimationClock`),
  - call `facade.tick(delta_ms)`,
  - render frame and display window.

Important render features:
- Piece animation states (`idle`, `move`, `jump`, rest states).
- Selection highlight for the chosen source square.
- Legal-destination highlights for selected piece.
- Cooldown visual overlay.
- Sidebars with per-side score and moves.

## UI Input Pipeline

### `ui/board_mapper.py`
- Converts pixel coordinates to board positions.
- Isolates pixel/grid mapping from the rest of the code.

### `ui/controller.py`
- Two-click input model:
  - first click selects source,
  - second click attempts move to destination.
- Handles click edge-cases:
  - outside board clears selection,
  - selecting same-color piece switches source,
  - frozen/cooldown piece selection can be ignored,
  - stale source selections are recovered safely.
- Delegates all legality to engine/facade, no chess rules inside controller.

## State and Event Layer

### `ui/state/game_facade.py`
- Thin boundary around `GameEngine` for UI use.
- Exposes engine snapshot and helper queries (cooldown/game-over/legal destinations).
- Publishes UI-level events on observer bus:
  - `MoveAccepted`, `MoveRejected`,
  - `PieceArrived`, `PieceCaptured`,
  - `GameOver`.

### `ui/state/game_events.py`
- Dataclasses for event payloads.
- Move metadata includes side, piece type, and move timestamp for UI formatting.

### `ui/state/observer.py`
- Subject/event bus abstraction used by UI components.

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

## Animation and Rendering Helpers

### `ui/animation.py`
- Frame-time clock (`tick_ms`).
- Pixel interpolation for smooth motion rendering.

### `ui/vendor/img.py`
- Image wrapper over OpenCV operations.
- Handles alpha-safe text and overlay drawing.

## Data Flow

1. User clicks in OpenCV window.
2. `main.py` receives mouse event and forwards to `Controller.on_click(...)`.
3. Controller uses `BoardMapper` and delegates move requests via facade.
4. Engine accepts/rejects request and updates motion state.
5. Per frame, `facade.tick(dt)` advances simulation.
6. `main.py` reads `facade.get_snapshot()` and renders board/pieces/overlays.
7. Observer subscribers update sidebars from published events.

## Boundaries and Invariants

- UI never mutates board state directly.
- Engine remains single source of truth.
- Rule legality always evaluated in `RuleEngine`.
- Controller remains stateless with respect to chess rules.
- Rendering is driven by immutable snapshot objects.

## Test Structure

All tests are now organized under `tests/` by domain.

### `tests/server/`
Engine/server domain tests:
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

- If adding a new visual overlay, keep state derivation in engine/facade and draw only in `main.py`.
- If adding new user interactions, keep coordinate logic in mapper/controller; keep rules in engine/rules.
- If adding new side panel data, prefer observer events and small subscriber components.
