from __future__ import annotations


def interpolate_pixel(src_px: tuple[int, int], dst_px: tuple[int, int], t: float) -> tuple[int, int]:
    """Linear interpolation used by the renderer for smooth travel prediction."""
    clamped = max(0.0, min(1.0, t))
    x = int(src_px[0] + (dst_px[0] - src_px[0]) * clamped)
    y = int(src_px[1] + (dst_px[1] - src_px[1]) * clamped)
    return x, y
