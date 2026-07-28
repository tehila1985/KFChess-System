"""
Unit tests for client/gui/widgets.py — Button, TextField, draw_error.

Pure logic (hit-testing, keystroke handling) plus smoke tests that draw()
doesn't raise. Visual output isn't asserted (no display in CI), but the
drawing primitives (Img.fill_rect/put_text) run for real against a real
numpy-backed canvas — this is exactly the code path the GUI scenes use
every frame, so it's worth exercising even without pixel assertions.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.widgets import Button, TextField, draw_error
from ui.vendor.img import Img


def _canvas() -> Img:
    return Img(np.zeros((200, 300, 3), dtype=np.uint8))


class TestButton:
    def test_contains_inside(self):
        b = Button("OK", x=10, y=10, w=50, h=20)
        assert b.contains(10, 10) is True
        assert b.contains(59, 29) is True

    def test_contains_outside(self):
        b = Button("OK", x=10, y=10, w=50, h=20)
        assert b.contains(9, 10) is False
        assert b.contains(60, 10) is False
        assert b.contains(10, 30) is False

    def test_draw_does_not_raise(self):
        b = Button("Login", x=5, y=5, w=100, h=40)
        b.draw(_canvas())


class TestTextField:
    def test_contains(self):
        f = TextField(x=0, y=0, w=100, h=30)
        assert f.contains(50, 15) is True
        assert f.contains(100, 15) is False

    def test_typing_appends_printable_chars(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=True)
        for ch in "alice":
            f.handle_key(ord(ch))
        assert f.value == "alice"

    def test_ignores_keys_when_not_focused(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=False)
        f.handle_key(ord("a"))
        assert f.value == ""

    def test_ignores_no_key(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=True)
        assert f.handle_key(-1) is False
        assert f.value == ""

    def test_backspace_removes_last_char(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=True, value="hello")
        f.handle_key(8)
        assert f.value == "hell"
        f.handle_key(127)
        assert f.value == "hel"

    def test_backspace_on_empty_is_safe(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=True, value="")
        f.handle_key(8)
        assert f.value == ""

    def test_enter_returns_true_without_appending(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=True, value="pw")
        assert f.handle_key(13) is True
        assert f.handle_key(10) is True
        assert f.value == "pw"

    def test_max_len_enforced(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=True, max_len=3)
        for ch in "abcdef":
            f.handle_key(ord(ch))
        assert f.value == "abc"

    def test_non_printable_key_ignored(self):
        f = TextField(x=0, y=0, w=100, h=30, focused=True)
        f.handle_key(1)  # control character, outside 32-126 printable range
        assert f.value == ""

    def test_draw_unfocused_and_masked_do_not_raise(self):
        f = TextField(x=0, y=0, w=100, h=30, label="Password", value="secret", mask=True)
        f.draw(_canvas())

    def test_draw_focused_shows_cursor_and_does_not_raise(self):
        f = TextField(x=0, y=0, w=100, h=30, label="Username", value="bob", focused=True)
        f.draw(_canvas())


def test_draw_error_does_not_raise():
    draw_error(_canvas(), 10, 10, "Something went wrong")
