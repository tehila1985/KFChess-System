# UI Layer

This package contains a thin, decoupled UI architecture for Kung-Fu Chess.

## Structure

- `state/`: Observer bus, events, and `GameFacade` bridge around engine logic.
- `graphics/`: Rendering abstractions that must use `vendor/img.py` for drawing.
- `animation/`: Frame clock, motion interpolation, and piece animation state.
- `user_input/`: Input adapters (intentionally not named `input/`).
- `ui_components/`: Observer subscribers such as score/moves/banner.
- `vendor/img.py`: Graphical primitive entrypoint (`read`, `draw_on`, `put_text`, `show`).

## Design Rules

- Keep game rules in `engine/`; UI modules must not re-implement rule logic.
- Publish UI updates through events (`MoveAccepted`, `MoveRejected`, `PieceArrived`,
  `PieceCaptured`, `GameOver`).
- Use only the provided `Img` API for graphical output.
