import ui.animation.animation_clock as animation_clock_module
from ui.animation.animation_clock import AnimationClock
from ui.animation.motion_predictor import interpolate_pixel
from ui.animation.piece_animator import PieceAnimator


def test_interpolate_pixel_clamps_low() -> None:
    assert interpolate_pixel((0, 0), (10, 10), -1.0) == (0, 0)


def test_interpolate_pixel_clamps_high() -> None:
    assert interpolate_pixel((0, 0), (10, 10), 2.0) == (10, 10)


def test_interpolate_pixel_midpoint() -> None:
    assert interpolate_pixel((0, 0), (10, 20), 0.5) == (5, 10)


def test_piece_animator_tick_and_state_reset() -> None:
    animator = PieceAnimator(token="wR")
    animator.tick(120)
    assert animator.elapsed_ms == 120

    animator.set_state("move")
    assert animator.state == "move"
    assert animator.elapsed_ms == 0


def test_animation_clock_uses_delta_ms(monkeypatch) -> None:
    points = iter([1.0, 1.015, 1.035])
    monkeypatch.setattr(animation_clock_module, "perf_counter", lambda: next(points))

    clock = AnimationClock()
    assert clock.tick_ms() == 0
    assert clock.tick_ms() in (14, 15)
    assert clock.tick_ms() == 20
