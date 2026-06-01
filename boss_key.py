"""Boss key — system-wide global hotkey to hide/restore the app.

Uses Windows RegisterHotKey API via ctypes. No external dependencies.
"""
import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312

_VK_MAP = {chr(i): i for i in range(0x41, 0x5B)}  # A-Z
_VK_MAP.update({str(i): 0x30 + i for i in range(10)})   # 0-9
_VK_MAP.update({
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "tab": 0x09,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "printscreen": 0x2C, "pause": 0x13,
})


def _parse_combo(combo: str) -> tuple[int, int]:
    """Parse 'ctrl+shift+h' → (modifiers, vk_code)."""
    parts = [p.strip().lower() for p in combo.split("+")]
    mod = 0
    vk = None
    for p in parts:
        if p == "ctrl" or p == "control":
            mod |= MOD_CONTROL
        elif p == "shift":
            mod |= MOD_SHIFT
        elif p == "alt":
            mod |= MOD_ALT
        elif p == "win":
            mod |= MOD_WIN
        else:
            vk = _VK_MAP.get(p) or _VK_MAP.get(p.upper())
            if vk is None:
                raise ValueError(f"Unknown key: {p!r}")
    if vk is None:
        raise ValueError("No key specified in combo")
    return mod, vk


class BossKeyHandler:
    """Register a global hotkey and fire a Tkinter virtual event when pressed."""

    def __init__(self, widget, combo: str = "ctrl+shift+h"):
        self._widget = widget
        self._hotkey_id = 1
        self._mod, self._vk = _parse_combo(combo)
        self._running = False

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        if not user32.RegisterHotKey(None, self._hotkey_id, self._mod, self._vk):
            return  # hotkey already registered by another instance

        self._running = True
        msg = wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                try:
                    self._widget.event_generate("<<BossKey>>", when="tail")
                except Exception:
                    pass

    def unregister(self):
        self._running = False
        user32.UnregisterHotKey(None, self._hotkey_id)
        user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)  # WM_QUIT
