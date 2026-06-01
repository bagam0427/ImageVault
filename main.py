"""ImageVault — Secure encrypted image viewer. Double-click run.bat to launch."""
import ctypes
import os
import sys
import traceback
import tkinter as tk
from tkinter import messagebox

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "startup.log")


def _log(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _check_single_instance():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "ImageVault_SingleInstance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        hwnd = ctypes.windll.user32.FindWindowW("Tk", "ImageVault")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        return True
    return False


def main():
    if _check_single_instance():
        sys.exit(0)

    _log("=== ImageVault starting ===")
    _log(f"Python: {sys.executable}")
    _log(f"CWD: {os.getcwd()}")

    from vault_gui import VaultApp, PasswordDialog
    from crypto_engine import CryptoEngine
    _log("imports OK")

    root = tk.Tk()
    _log("Tk() created")
    root.attributes('-alpha', 0)  # transparent — not withdrawn, Toplevel works normally
    root.geometry('1x1+0+0')

    dialog = PasswordDialog(root)
    dialog.lift()
    dialog.focus_force()
    _log("PasswordDialog created, waiting...")
    root.wait_window(dialog)
    _log(f"PasswordDialog closed, result={'***' if dialog.result else 'None'}")

    if dialog.result is None:
        root.destroy()
        _log("User cancelled, exiting")
        return

    engine = CryptoEngine(dialog.result)
    dialog.result = None
    _log("CryptoEngine initialized")

    root.destroy()
    _log("Temp root destroyed")

    app = VaultApp(engine)
    _log("VaultApp created, entering mainloop")
    app.mainloop()
    _log("mainloop exited")


if __name__ == '__main__':
    try:
        main()
    except Exception:
        _log(f"FATAL ERROR:\n{traceback.format_exc()}")
        messagebox.showerror(
            "ImageVault 错误",
            f"启动失败：\n\n{traceback.format_exc()}"
        )
