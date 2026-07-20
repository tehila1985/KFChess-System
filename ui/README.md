# UI Layer

This package contains a thin, decoupled UI architecture for Kung-Fu Chess.

## Structure

- `interaction/`: Input mapping and click-to-action orchestration (`BoardMapper`, `Controller`, `ControllerOutcomeAdapter`).
- `composition/`: Application wiring (`build_container`, `AppContainer`).
- `state/`: Observer bus, events, and `GameFacade` bridge around engine logic.
- `animation/`: Frame clock, motion interpolation, and piece animation state.
- `rendering/`: Board/HUD render stages and render context contracts.
- `rendering/text_renderer.py`: Text snapshot renderer for CLI and tests.
- `user_input/`: Device adapters (mouse/pointer) that delegate into `interaction/`.
- `ui_components/`: Observer subscribers such as score/moves/banner.
- `vendor/img.py`: Graphical primitive entrypoint (`read`, `draw_on`, `put_text`, `show`).
- `runtime/game_loop.py`: OpenCV runtime loop with orchestration only.
- `resources/asset_loader.py`: UI asset loading and preprocessing.
- `config/`: UI runtime/layout/status constants and core UI settings.

## Design Rules

- Keep game rules in `engine/`; UI modules must not re-implement rule logic.
- Publish UI updates through events (`MoveAccepted`, `MoveRejected`, `PieceArrived`,
  `PieceCaptured`, `GameOver`).
- Use only the provided `Img` API for graphical output.
- Keep runtime constants in `ui/config/` modules only.
