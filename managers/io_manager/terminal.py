"""Terminal: low-level terminal access: raw keys, mouse clicks and
length-limited line reading."""

import codecs
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .constants import IS_WINDOWS

if IS_WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes
else:
    import select
    import termios
    import tty


class Terminal:
    """Low-level terminal access: raw keys, mouse clicks and length-limited
    line reading. One instance per program."""

    STD_INPUT_HANDLE = -10
    ENABLE_MOUSE_INPUT = 0x0010
    ENABLE_EXTENDED_FLAGS = 0x0080

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("ignore")
        if IS_WINDOWS:
            self._kernel32 = ctypes.windll.kernel32
            self._saved_console_mode = wintypes.DWORD()

    # ----- raw bytes -----
    def _getb(self) -> bytes:
        """Read one raw byte (blocks, no CPU spinning)."""
        if IS_WINDOWS:
            return msvcrt.getch()
        return os.read(sys.stdin.fileno(), 1)

    def _pending(self, timeout: float = 0.02) -> bool:
        """Is another byte already waiting?"""
        if IS_WINDOWS:
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if msvcrt.kbhit():
                    return True
                time.sleep(0.002)
            return False
        return bool(select.select([sys.stdin.fileno()], [], [], timeout)[0])

    @contextmanager
    def raw_input(self) -> Iterator[None]:
        """Raw terminal mode on Unix, set once and restored after. No-op on Windows."""
        if IS_WINDOWS:
            yield
            return
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # ----- mouse tracking -----
    def enable_mouse_tracking(self) -> None:
        sys.stdout.write("\033[?1000h\033[?25l")  # mouse on, hide cursor
        sys.stdout.flush()
        if IS_WINDOWS:
            handle = self._kernel32.GetStdHandle(self.STD_INPUT_HANDLE)
            self._kernel32.GetConsoleMode(handle, ctypes.byref(self._saved_console_mode))
            mode = self._saved_console_mode.value
            self._kernel32.SetConsoleMode(
                handle, (mode & ~self.ENABLE_EXTENDED_FLAGS) | self.ENABLE_MOUSE_INPUT
            )

    def disable_mouse_tracking(self) -> None:
        sys.stdout.write("\033[?1000l\033[?25h\n")  # mouse off, show cursor
        sys.stdout.flush()
        if IS_WINDOWS:
            handle = self._kernel32.GetStdHandle(self.STD_INPUT_HANDLE)
            self._kernel32.SetConsoleMode(handle, self._saved_console_mode.value)

    # ----- one event reader shared by every button/choice prompt -----
    def _read_event(self) -> tuple[str, Any] | None:
        """Return ("key", char), ("click", column), or None for anything ignorable."""
        b = self._getb()

        if IS_WINDOWS and b in (b"\x00", b"\xe0"):  # arrow/function key: skip 2nd byte
            self._getb()
            return None

        if b != b"\x1b":
            return ("key", b.decode("utf-8", "ignore"))

        # ESC: either a lone Esc press or the start of an escape sequence
        if not self._pending() or self._getb() != b"[":
            return None
        if not self._pending() or self._getb() != b"M":  # some other sequence
            return None

        # Mouse report: ESC [ M <button> <x> <y>
        btn, x, _y = self._getb(), self._getb(), self._getb()
        if btn[0] - 32 == 0:  # left button press
            return ("click", x[0] - 32)
        return None

    def wait_for_choice(
        self, art: str, regions: dict[Any, tuple[int, int]], keys: dict[str, Any]
    ) -> Any:
        """Show `art`, then wait for a mapped key or a left click inside a region.

        regions: {value: (min_x, max_x)}    keys: {"y": value, "\\r": value, ...}
        Returns the matching value.
        """
        print(art, end="", flush=True)
        self.enable_mouse_tracking()
        try:
            with self.raw_input():
                while True:
                    event = self._read_event()
                    if event is None:
                        continue
                    kind, val = event
                    if kind == "key":
                        if val == "\x03":
                            raise KeyboardInterrupt
                        if val.lower() in keys:
                            return keys[val.lower()]
                    else:
                        for value, (lo, hi) in regions.items():
                            if lo <= val <= hi:
                                return value
        finally:
            self.disable_mouse_tracking()

    def execute_button_interaction(
        self, button_art: str, min_x: int = 5, max_x: int = 35
    ) -> None:
        self.wait_for_choice(
            button_art, {True: (min_x, max_x)}, {"\r": True, "\n": True}
        )

    def execute_choice_interaction(
        self, art: str, regions: dict[Any, tuple[int, int]], keys: dict[str, Any]
    ) -> Any:
        return self.wait_for_choice(art, regions, keys)

    # ----- text input: length-limited line reader -----
    def _read_key(self) -> str:
        """Read one character without waiting for Enter."""
        if IS_WINDOWS:
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()
                return ""
            return ch
        while True:  # assemble multi-byte UTF-8 characters
            s = self._decoder.decode(self._getb())
            if s:
                return s

    def read_limited(self, max_len: int, blocked: str = "") -> str:
        """Read a line, silently ignoring keys once max_len characters are typed."""
        buf: list[str] = []
        with self.raw_input():  # set once, not per keystroke
            while True:
                ch = self._read_key()

                if ch in ("\r", "\n"):
                    break
                if ch == "\x03":
                    raise KeyboardInterrupt
                if ch in ("\x08", "\x7f"):
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                if not ch or not ch.isprintable() or ch in blocked:
                    continue
                if len(buf) >= max_len:
                    continue

                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

        return "".join(buf)
