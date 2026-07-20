from __future__ import annotations

import cv2
import numpy as np


class Img:
    """Small OpenCV-backed implementation of the required Img API.

    All color parameters follow OpenCV's BGR(A) channel order convention.
    """

    def __init__(self, pixels: np.ndarray):
        self._pixels = pixels

    @classmethod
    def read(cls, path: str) -> "Img":
        pixels = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if pixels is None:
            raise FileNotFoundError(f"Could not read image: {path}")
        if pixels.ndim == 2:
            pixels = cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)
        return cls(pixels)

    @property
    def pixels(self) -> np.ndarray:
        return self._pixels

    def copy(self) -> "Img":
        return Img(self._pixels.copy())

    def draw_on(self, other: "Img", x: int = 0, y: int = 0) -> "Img":
        """Draw this image onto other with alpha support."""
        src = self._pixels
        dst = other._pixels

        h, w = src.shape[:2]
        dst_h, dst_w = dst.shape[:2]

        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(dst_w, x + w)
        y1 = min(dst_h, y + h)
        if x0 >= x1 or y0 >= y1:
            return other

        sx0 = x0 - x
        sy0 = y0 - y
        sx1 = sx0 + (x1 - x0)
        sy1 = sy0 + (y1 - y0)

        src_crop = src[sy0:sy1, sx0:sx1]
        dst_crop = dst[y0:y1, x0:x1]

        if src_crop.shape[2] == 4:
            alpha = src_crop[:, :, 3:4].astype(np.float32) / 255.0
            src_rgb = src_crop[:, :, :3].astype(np.float32)
            dst_rgb = dst_crop[:, :, :3].astype(np.float32)
            blended = src_rgb * alpha + dst_rgb * (1.0 - alpha)
            dst_crop[:, :, :3] = blended.astype(np.uint8)
            if dst_crop.shape[2] == 4:
                dst_crop[:, :, 3] = 255
        else:
            dst_crop[:, :, :3] = src_crop[:, :, :3]
            if dst_crop.shape[2] == 4:
                dst_crop[:, :, 3] = 255

        dst[y0:y1, x0:x1] = dst_crop
        return other

    def fill_rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        color_bgr: tuple[int, int, int],
    ) -> "Img":
        """Fill a solid rectangle on this image (BGR, in-place)."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self._pixels.shape[1], x + w)
        y1 = min(self._pixels.shape[0], y + h)
        if x0 < x1 and y0 < y1:
            self._pixels[y0:y1, x0:x1, :3] = color_bgr
        return self

    def put_text(
        self,
        text: str,
        x: int,
        y: int,
        color_bgr: tuple[int, int, int] = (255, 255, 255),
        scale: float = 1.0,
        font: int = cv2.FONT_HERSHEY_SIMPLEX,
        thickness: int = 2,
    ) -> "Img":
        """Render text onto this image.

        Args:
            text:      The string to render.
            x, y:      Baseline origin in pixels.
            color_bgr: Text colour in BGR channel order.
            scale:     Font scale factor.
            font:      OpenCV font face constant.
            thickness: Stroke thickness in pixels.
        """
        if self._pixels.shape[2] == 4:
            canvas = self._pixels[:, :, :3].copy()
            cv2.putText(
                canvas,
                text,
                (int(x), int(y)),
                font,
                float(scale),
                color_bgr,
                thickness,
                cv2.LINE_AA,
            )
            self._pixels[:, :, :3] = canvas
        else:
            canvas = self._pixels
            if not canvas.flags["C_CONTIGUOUS"]:
                canvas = np.ascontiguousarray(canvas)
                self._pixels[:, :, :3] = canvas[:, :, :3]
            cv2.putText(
                canvas,
                text,
                (int(x), int(y)),
                font,
                float(scale),
                color_bgr,
                thickness,
                cv2.LINE_AA,
            )
        return self

    def show(self, title: str = "Img") -> int:
        view = self._pixels
        if view.shape[2] == 4:
            view = cv2.cvtColor(view, cv2.COLOR_BGRA2BGR)
        cv2.imshow(title, view)
        return cv2.waitKey(1)
