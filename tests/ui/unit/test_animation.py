import ui.animation.animation_clock as animation_clock_module
from ui.animation.animation_clock import AnimationClock
from ui.animation.motion_predictor import interpolate_pixel


def test_interpolate_pixel_clamps_low() -> None:
    """Verify interpolate pixel clamps low."""
    assert interpolate_pixel((0, 0), (10, 10), -1.0) == (0, 0)


def test_interpolate_pixel_clamps_high() -> None:
    """Verify interpolate pixel clamps high."""
    assert interpolate_pixel((0, 0), (10, 10), 2.0) == (10, 10)


def test_interpolate_pixel_midpoint() -> None:
    """Verify interpolate pixel midpoint."""
    assert interpolate_pixel((0, 0), (10, 20), 0.5) == (5, 10)


def test_animation_clock_uses_delta_ms(monkeypatch) -> None:
    """Verify animation clock uses delta ms."""
    points = iter([1.0, 1.015, 1.035])
    monkeypatch.setattr(animation_clock_module, "perf_counter", lambda: next(points))

    clock = AnimationClock()
    assert clock.tick_ms() == 0
    assert clock.tick_ms() in (14, 15)
    assert clock.tick_ms() == 20
