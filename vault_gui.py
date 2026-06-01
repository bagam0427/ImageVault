"""ImageVault GUI — Tkinter-based image viewer with encryption support."""
import ctypes
import io
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from boss_key import BossKeyHandler
from config import load_config, save_config
from crypto_engine import CryptoEngine
from lang import tr, set_lang, get_lang


def _load_image(data: bytes) -> Image.Image:
    """Load image from bytes. Falls back to imageio if Pillow decoder produces all-black.

    Some JPEG encodings (notably from Adobe Photoshop) are decoded as all-black
    by Pillow 11.x on Windows.  imageio uses a different backend that handles them.
    """
    pil_img = Image.open(io.BytesIO(data))
    pil_img.load()
    # Detect Pillow decoder bug: large RGB image whose first 100 pixels are black
    if pil_img.mode == "RGB" and pil_img.width * pil_img.height > 2500:
        pixels = list(pil_img.getdata())
        if all(p == (0, 0, 0) for p in pixels[:100]):
            import imageio.v3 as iio
            arr = iio.imread(data)
            pil_img = Image.fromarray(arr)
    return pil_img


def _normalize_mode(img: Image.Image, bg_color: str = "#2d2d2d") -> Image.Image:
    """Convert RGBA/PA/LA/P to RGB, composited on bg_color."""
    if img.mode in ("RGBA", "PA", "LA"):
        bg = Image.new("RGB", img.size, bg_color)
        if img.mode == "PA":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1])
        return bg
    if img.mode == "P":
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, bg_color)
        bg.paste(img, mask=img.split()[-1])
        return bg
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img


VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VAULT")

THUMB_SIZE = (150, 150)
THUMB_PAD_COLOR = "#2d2d2d"  # dark gray, not pure black
BATCH_SIZE = 8
MIN_ZOOM = 0.1
MAX_ZOOM = 5.0
ZOOM_STEP = 0.1
COL_PADDING = 6
ROW_PADDING = 36


# ═══════════════════════════════════════════════════════════════════════
# PasswordDialog
# ═══════════════════════════════════════════════════════════════════════

class PasswordDialog(tk.Toplevel):
    """Modal password prompt shown at launch."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result: str | None = None

        self.title(tr("pw_title"))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build_ui()
        self.update_idletasks()  # ensure window is realized before querying screen size

        # center on screen
        w, h = 400, 180
        ws = self.winfo_screenwidth()
        hs = self.winfo_screenheight()
        x = (ws - w) // 2
        y = (hs - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.attributes("-topmost", True)

        # boss key (global hotkey)
        self._boss_key = BossKeyHandler(self)
        self.bind("<<BossKey>>", self._toggle_boss)
        self._hidden = False

        # focus chain
        self._entry.focus_set()
        self.bind("<Return>", lambda e: self._on_unlock())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _build_ui(self):
        pad = {"padx": 16, "pady": 6}

        ttk.Label(self, text=tr("pw_prompt"), font=("", 11)).pack(
            anchor="w", **pad
        )

        entry_frame = ttk.Frame(self)
        entry_frame.pack(fill="x", **pad)

        self._show_pw = tk.BooleanVar(value=False)
        self._entry = ttk.Entry(entry_frame, show="*", font=("", 11))
        self._entry.pack(side="left", fill="x", expand=True)
        cb = ttk.Checkbutton(
            entry_frame, text=tr("pw_show"), variable=self._show_pw,
            command=self._toggle_show
        )
        cb.pack(side="left", padx=(8, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", **pad)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        ttk.Button(btn_frame, text=tr("pw_unlock"), command=self._on_unlock).grid(
            row=0, column=0, padx=(0, 4), sticky="ew"
        )
        ttk.Button(btn_frame, text=tr("pw_cancel"), command=self._on_cancel).grid(
            row=0, column=1, padx=(4, 0), sticky="ew"
        )

    def _toggle_show(self):
        self._entry.config(show="" if self._show_pw.get() else "*")

    def _on_unlock(self):
        pw = self._entry.get()
        if not pw:
            return
        self._boss_key.unregister()
        self.result = pw
        self.attributes("-topmost", False)
        self.destroy()

    def _on_cancel(self):
        self._boss_key.unregister()
        self.result = None
        self.destroy()

    def _toggle_boss(self, _event=None):
        if self._hidden:
            self.deiconify()
            self.lift()
            self.focus_force()
            self._hidden = False
        else:
            self._hidden = True
            self.withdraw()


# ═══════════════════════════════════════════════════════════════════════
# ThumbnailGallery
# ═══════════════════════════════════════════════════════════════════════

class ThumbnailGallery(ttk.Frame):
    """Grid of decrypted thumbnail images."""

    def __init__(self, parent, engine: CryptoEngine, on_click, status_var: tk.StringVar):
        super().__init__(parent)
        self.engine = engine
        self._on_click = on_click
        self._status_var = status_var

        self._dat_files: list[str] = []
        self._photos: list[ImageTk.PhotoImage] = []  # prevent GC
        self._thumb_widgets: list[ttk.Label] = []
        self._success_count = 0

        self._build_ui()

    def _build_ui(self):
        # ---- top bar ----
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(top, text=tr("tg_vault_dir")).pack(side="left")
        self._folder_var = tk.StringVar()
        self._folder_entry = ttk.Entry(top, textvariable=self._folder_var, state="readonly")
        self._folder_entry.pack(side="left", fill="x", expand=True, padx=6)

        ttk.Button(top, text=tr("tg_browse"), command=self._browse_folder).pack(side="left", padx=2)
        ttk.Button(top, text=tr("tg_scan"), command=self._scan).pack(side="left", padx=2)

        # ---- canvas area ----
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill="both", expand=True, padx=8, pady=4)
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(canvas_frame, bg="#f0f0f0", highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(canvas_frame, orient="vertical", command=self._canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=vsb.set)

        self._inner = ttk.Frame(self._canvas)
        self._inner_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # mouse wheel scrolling
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        # arrow key navigation
        self._canvas.focus_set()
        self._canvas.bind("<Left>", lambda e: self._nav(-1))
        self._canvas.bind("<Right>", lambda e: self._nav(1))
        self._canvas.bind("<Up>", lambda e: self._nav(-self._cols))
        self._canvas.bind("<Down>", lambda e: self._nav(self._cols))

        # right-click context menu
        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label=tr("tg_decrypt_save"), command=self._decrypt_save)
        self._ctx_menu.add_command(label=tr("tg_delete"), command=self._delete_file)
        self._ctx_index: int | None = None

    # ---- scrolling ----

    def _on_inner_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._inner_id, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ---- folder / scan ----

    def _browse_folder(self):
        os.makedirs(VAULT_DIR, exist_ok=True)
        path = filedialog.askdirectory(title=tr("tg_choose_vault"), initialdir=VAULT_DIR)
        if path:
            self._folder_var.set(path)
            self._scan()

    def set_folder(self, path: str):
        self._folder_var.set(path)
        self._scan()

    def _scan(self):
        path = self._folder_var.get()
        if not path:
            return
        self._clear_gallery()
        self._dat_files = sorted(
            os.path.join(path, f)
            for f in os.listdir(path)
            if f.lower().endswith(".dat")
        )
        self._success_count = 0
        if not self._dat_files:
            self._status_var.set(tr("tg_no_dat"))
            tk.Label(
                self._inner,
                text=tr("tg_no_dat_detail"),
                justify="center", foreground="#888",
            ).grid(row=0, column=0, padx=40, pady=60)
            return
        self._cols = max(1, self._canvas.winfo_width() // (THUMB_SIZE[0] + COL_PADDING))
        if self._cols < 1:
            self._cols = 5
        self._status_var.set(tr("tg_loading", current=0, total=len(self._dat_files)))
        self._load_batch(0)

    def _clear_gallery(self):
        self._photos.clear()
        self._thumb_widgets.clear()
        for w in self._inner.winfo_children():
            w.destroy()

    # ---- batched loading ----

    def _load_batch(self, start_idx: int):
        end = min(start_idx + BATCH_SIZE, len(self._dat_files))
        for i in range(start_idx, end):
            self._load_one(i)
            self._status_var.set(tr("tg_loading", current=i + 1, total=len(self._dat_files)))
            self.update_idletasks()
        if end < len(self._dat_files):
            self.after(1, self._load_batch, end)
        else:
            self._status_var.set(tr("tg_loaded", count=self._success_count))
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _load_one(self, idx: int):
        filepath = self._dat_files[idx]
        try:
            with open(filepath, "rb") as f:
                raw = f.read()
            img_bytes = self.engine.decrypt_image(raw)
            pil_img = _load_image(img_bytes)
            pil_img = _normalize_mode(pil_img, THUMB_PAD_COLOR)
            thumb = ImageOps.pad(pil_img, THUMB_SIZE, color=THUMB_PAD_COLOR)
            photo = ImageTk.PhotoImage(thumb)
            self._photos.append(photo)
        except Exception:
            return  # silently skip files that can't be decrypted

        self._add_thumbnail(self._success_count, photo, os.path.basename(filepath))
        self._success_count += 1

    def _add_thumbnail(self, idx: int, photo: ImageTk.PhotoImage, name: str):
        row = idx // self._cols
        col = idx % self._cols

        frame = ttk.Frame(self._inner)
        frame.grid(row=row, column=col, padx=COL_PADDING // 2, pady=ROW_PADDING // 2)

        lbl = tk.Label(frame, image=photo, cursor="hand2",
                       background="#f0f0f0", borderwidth=0)
        lbl.image = photo  # anchor
        lbl.pack()
        tk.Label(frame, text=self._truncate_name(name), font=("", 8),
                 background="#f0f0f0", borderwidth=0).pack()
        lbl.bind("<Button-1>", lambda e, i=idx: self._on_thumb_click(i))
        lbl.bind("<Button-3>", lambda e, i=idx: self._on_right_click(i, e))
        self._thumb_widgets.append(lbl)

    def _truncate_name(self, name: str, max_len: int = 18) -> str:
        if len(name) <= max_len:
            return name
        dot = name.rfind(".")
        base = name[:dot] if dot > 0 else name
        ext = name[dot:] if dot > 0 else ""
        keep = max_len - len(ext) - 1
        if keep < 4:
            return name[:max_len - 3] + "..."
        return base[:keep] + "..." + ext

    # ---- interaction ----

    def _on_thumb_click(self, idx: int):
        self._on_click(idx)

    def _on_right_click(self, idx: int, event):
        self._ctx_index = idx
        self._ctx_menu.post(event.x_root, event.y_root)

    def _nav(self, delta: int):
        if not self._thumb_widgets:
            return
        # find current focus or use first
        try:
            cur = self._thumb_widgets.index(self.focus_get())
        except ValueError:
            cur = 0
        new = max(0, min(len(self._thumb_widgets) - 1, cur + delta))
        self._thumb_widgets[new].focus_set()

    # ---- context menu actions ----

    def _decrypt_save(self):
        idx = self._ctx_index
        if idx is None:
            return
        filepath = self._dat_files[idx]
        out_name = os.path.splitext(os.path.basename(filepath))[0]  # strip .dat
        if out_name.endswith(".jpg") or out_name.endswith(".png") or out_name.endswith(".gif") or \
           out_name.endswith(".webp") or out_name.endswith(".bmp") or out_name.endswith(".jpeg"):
            save_name = out_name
        else:
            save_name = out_name + ".png"

        save_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=save_name,
            filetypes=[(tr("tg_filetype_img"), "*.jpg *.jpeg *.png *.gif *.webp *.bmp"), (tr("tg_filetype_all"), "*.*")],
        )
        if not save_path:
            return
        try:
            with open(filepath, "rb") as f:
                raw = f.read()
            img_bytes = self.engine.decrypt_image(raw)
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            messagebox.showinfo(tr("tg_done"), tr("tg_saved_to", save_path=save_path))
        except Exception as e:
            messagebox.showerror(tr("tg_error"), str(e))

    def _delete_file(self):
        idx = self._ctx_index
        if idx is None:
            return
        filepath = self._dat_files[idx]
        if not messagebox.askyesno(tr("tg_confirm"), tr("tg_delete_confirm", name=os.path.basename(filepath))):
            return
        try:
            os.remove(filepath)
            self._scan()
        except OSError as e:
            messagebox.showerror(tr("tg_error"), str(e))

    # ---- public helpers ----

    @property
    def file_count(self) -> int:
        return len(self._dat_files)

    @property
    def file_list(self) -> list[str]:
        return self._dat_files


# ═══════════════════════════════════════════════════════════════════════
# ImageViewer
# ═══════════════════════════════════════════════════════════════════════

class ImageViewer(ttk.Frame):
    """Full-size image viewer with zoom and pan."""

    def __init__(self, parent, engine: CryptoEngine, file_list: list[str],
                 status_var: tk.StringVar, on_back):
        super().__init__(parent)
        self.engine = engine
        self._file_list = file_list
        self._status_var = status_var
        self._on_back = on_back

        self._current_idx = 0
        self._zoom = 1.0
        self._pil_image: Image.Image | None = None
        self._tk_image: ImageTk.PhotoImage | None = None
        self._canvas_img_id: int | None = None

        # float / frameless mode state
        self._is_floating = False
        self._saved_geometry = ""
        self._offset_x = 0
        self._offset_y = 0
        # resize state (borderless mode)
        self._resize_edge: str | None = None
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0
        self._resize_start_root_x = 0
        self._resize_start_root_y = 0
        # animation state
        self._frames: list[Image.Image] = []
        self._frame_delays: list[int] = []
        self._loop_count: int = 0
        self._current_frame: int = 0
        self._anim_after_id: str | None = None
        self._loop_remaining: int = 0
        self._is_playing: bool = False

        self._build_ui()

    def _build_ui(self):
        # ---- toolbar ----
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=4)

        ttk.Button(toolbar, text=tr("iv_back_gallery"), command=self._back_to_gallery).pack(side="left")

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(toolbar, text=tr("iv_prev_img"), command=self._prev).pack(side="left", padx=2)
        ttk.Button(toolbar, text=tr("iv_next_img"), command=self._next).pack(side="left", padx=2)

        # GIF frame controls (hidden by default)
        style = ttk.Style()
        style.configure("GifBtn.TButton", padding=(8, 3))
        self._gif_ctrl_frame = ttk.Frame(toolbar)
        self._btn_prev_frame = ttk.Button(self._gif_ctrl_frame, text=tr("iv_prev_frame"), width=3,
                                           style="GifBtn.TButton", command=self._prev_frame)
        self._btn_prev_frame.pack(side="left", padx=1)
        self._btn_play_pause = ttk.Button(self._gif_ctrl_frame, text=tr("iv_play"), width=3,
                                           style="GifBtn.TButton", command=self._toggle_play)
        self._btn_play_pause.pack(side="left", padx=1)
        self._btn_next_frame = ttk.Button(self._gif_ctrl_frame, text=tr("iv_next_frame"), width=3,
                                           style="GifBtn.TButton", command=self._next_frame)
        self._btn_next_frame.pack(side="left", padx=1)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(toolbar, text="−", width=3, command=self._zoom_out).pack(side="left", padx=2)
        self._zoom_label = ttk.Label(toolbar, text="100%", width=6)
        self._zoom_label.pack(side="left")
        ttk.Button(toolbar, text="＋", width=3, command=self._zoom_in).pack(side="left", padx=2)
        ttk.Button(toolbar, text=tr("iv_fit"), command=self._fit_to_window).pack(side="left", padx=4)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        self._info_label1 = ttk.Label(toolbar, text="")
        self._info_label1.pack(side="left", padx=4)

        # ---- image canvas ----
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill="both", expand=True, padx=8, pady=4)
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(canvas_frame, bg="#2d2d2d", highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._hsb = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self._canvas.xview)
        self._vsb = ttk.Scrollbar(canvas_frame, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=self._hsb.set, yscrollcommand=self._vsb.set)

        # ---- mouse bindings ----
        self._canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._canvas.bind("<B1-Motion>", self._on_drag_move)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._canvas.bind("<Button-3>", self._on_right_click)
        # keyboard
        self._canvas.focus_set()
        self._canvas.bind("<Left>", lambda e: self._prev())
        self._canvas.bind("<Right>", lambda e: self._next())

        # right-click context menu
        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label=tr("iv_float_mode"), command=self._toggle_float_mode)
        self._ctx_menu.add_command(label=tr("tg_decrypt_save"), command=self._save_current)

        # references for fullscreen toggle
        self._toolbar_frame = toolbar
        self._canvas_frame = canvas_frame

        # ---- info bar ----
        self._info_label2 = ttk.Label(self, text="", anchor="w")
        self._info_label2.pack(fill="x", padx=8, pady=(0, 4))

    # ---- load / display ----

    def _back_to_gallery(self):
        self._stop_animation()
        self._on_back()

    def destroy(self):
        self._stop_animation()
        super().destroy()

    def show_image(self, idx: int):
        if not self._file_list:
            return
        self._current_idx = idx % len(self._file_list)
        filepath = self._file_list[self._current_idx]
        try:
            with open(filepath, "rb") as f:
                raw = f.read()
            img_bytes = self.engine.decrypt_image(raw)
            self._stop_animation()
            self._frames.clear()
            pil_img = _load_image(img_bytes)
            n_frames = getattr(pil_img, 'n_frames', 1)

            if n_frames > 1:
                self._frame_delays.clear()
                for i in range(n_frames):
                    pil_img.seek(i)
                    frame = _normalize_mode(pil_img.copy())
                    self._frames.append(frame)
                    delay = pil_img.info.get('duration', 100)
                    if delay < 20:
                        delay *= 10  # fix centisecond vs millisecond ambiguity
                    self._frame_delays.append(delay)
                self._loop_count = pil_img.info.get('loop', 0)
                self._current_frame = 0
                self._pil_image = self._frames[0]
                self._display()
                self._start_animation()
                self._gif_ctrl_frame.pack(side="left", padx=(8, 0))
            else:
                self._gif_ctrl_frame.pack_forget()
                pil_img = _normalize_mode(pil_img)
                self._pil_image = pil_img
                self._display()

            w, h = self._pil_image.size
            name = os.path.basename(filepath)
            extra = tr("iv_gif_frames", n_frames=n_frames) if n_frames > 1 else ""
            self._info_label2.config(
                text=tr("iv_info_bar", name=name, w=w, h=h, size=f"{len(img_bytes):,}", extra=extra)
            )
            self._info_label1.config(text=tr("iv_img_n_of_m", current=self._current_idx + 1, total=len(self._file_list)))
        except Exception as e:
            self._canvas.delete("all")
            self._canvas.create_text(
                self._canvas.winfo_width() // 2, self._canvas.winfo_height() // 2,
                text=str(e), fill="#ff4444", font=("", 14),
            )

    def _display(self):
        if self._pil_image is None:
            return
        self._canvas.delete("all")

        w = int(self._pil_image.width * self._zoom)
        h = int(self._pil_image.height * self._zoom)
        resized = self._pil_image.resize((w, h), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(resized)

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        cx = max(0, (cw - w) // 2)
        cy = max(0, (ch - h) // 2)
        self._canvas_img_id = self._canvas.create_image(cx, cy, anchor="nw", image=self._tk_image)

        self._img_width = max(w, cw)
        self._img_height = max(h, ch)
        self._canvas.configure(scrollregion=(0, 0, self._img_width, self._img_height))
        self._update_scrollbars(w, h)
        self._zoom_label.config(text=f"{int(self._zoom * 100)}%")

    # ---- animation ----

    def _stop_animation(self):
        if self._anim_after_id is not None:
            self.after_cancel(self._anim_after_id)
            self._anim_after_id = None
        self._is_playing = False
        self._btn_play_pause.config(text=tr("iv_play"))

    def _start_animation(self):
        self._stop_animation()
        if not self._frames:
            return
        self._is_playing = True
        self._btn_play_pause.config(text=tr("iv_pause"))
        self._loop_remaining = self._loop_count
        self._schedule_next_frame()

    def _schedule_next_frame(self):
        if not self._frames:
            return
        delay = max(self._frame_delays[self._current_frame], 20)
        self._anim_after_id = self.after(delay, self._advance_frame)

    def _advance_frame(self):
        if not self._frames:
            return
        self._current_frame += 1
        if self._current_frame >= len(self._frames):
            if self._loop_count == 0:
                self._current_frame = 0
            elif self._loop_remaining > 1:
                self._loop_remaining -= 1
                self._current_frame = 0
            else:
                return  # stop at last frame
        self._pil_image = self._frames[self._current_frame]
        self._display()
        self._schedule_next_frame()

    def _prev_frame(self):
        if not self._frames:
            return
        self._stop_animation()
        self._current_frame = (self._current_frame - 1) % len(self._frames)
        self._pil_image = self._frames[self._current_frame]
        self._display()

    def _next_frame(self):
        if not self._frames:
            return
        self._stop_animation()
        self._current_frame = (self._current_frame + 1) % len(self._frames)
        self._pil_image = self._frames[self._current_frame]
        self._display()

    def _toggle_play(self):
        if self._is_playing:
            self._stop_animation()
        else:
            self._start_animation()

    def _update_scrollbars(self, img_w: int, img_h: int):
        if self._is_floating:
            return
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if img_w > cw:
            self._hsb.grid(row=1, column=0, sticky="ew")
        else:
            self._hsb.grid_forget()
        if img_h > ch:
            self._vsb.grid(row=0, column=1, sticky="ns")
        else:
            self._vsb.grid_forget()

    # ---- zoom ----

    def _zoom_in(self):
        self._set_zoom(self._zoom + ZOOM_STEP)

    def _zoom_out(self):
        self._set_zoom(self._zoom - ZOOM_STEP)

    def _fit_to_window(self):
        if self._pil_image is None:
            return
        cw = self._canvas.winfo_width() - 4
        ch = self._canvas.winfo_height() - 4
        iw, ih = self._pil_image.size
        self._set_zoom(min(cw / iw, ch / ih, 1.0))

    def _set_zoom(self, z: float):
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, z))
        self._display()

    # ---- navigation ----

    def _prev(self):
        if self._file_list:
            self.show_image(self._current_idx - 1)

    def _next(self):
        if self._file_list:
            self.show_image(self._current_idx + 1)

    # ---- mouse handlers ----

    def _on_ctrl_wheel(self, event):
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ---- edge detection for borderless resize ----
    EDGE_MARGIN = 6
    _CURSORS = {
        "n": "sb_v_double_arrow",
        "s": "sb_v_double_arrow",
        "e": "sb_h_double_arrow",
        "w": "sb_h_double_arrow",
        "ne": "size_ne_sw",
        "sw": "size_ne_sw",
        "nw": "size_nw_se",
        "se": "size_nw_se",
    }

    def _detect_edge(self, event) -> str | None:
        """Return edge direction if cursor is near window border, else None."""
        top = self.winfo_toplevel()
        m = self.EDGE_MARGIN
        w, h = top.winfo_width(), top.winfo_height()
        x, y = event.x_root - top.winfo_rootx(), event.y_root - top.winfo_rooty()
        n = y <= m
        s = y >= h - m
        e = x >= w - m
        w_ = x <= m
        if n and e:  return "ne"
        if n and w_:  return "nw"
        if s and e:  return "se"
        if s and w_:  return "sw"
        if n:  return "n"
        if s:  return "s"
        if e:  return "e"
        if w_: return "w"
        return None

    def _on_motion(self, event):
        if not self._is_floating:
            self._canvas.configure(cursor="")
            return
        edge = self._detect_edge(event)
        cursor = self._CURSORS.get(edge, "") if edge else ""
        self._canvas.configure(cursor=cursor)

    def _on_drag_start(self, event):
        self._canvas.focus_set()
        if self._is_floating:
            edge = self._detect_edge(event)
            if edge:
                # resize mode
                self._resize_edge = edge
                top = self.winfo_toplevel()
                self._resize_start_x = top.winfo_x()
                self._resize_start_y = top.winfo_y()
                self._resize_start_w = top.winfo_width()
                self._resize_start_h = top.winfo_height()
                self._resize_start_root_x = event.x_root
                self._resize_start_root_y = event.y_root
                return
            if event.state & 0x0004:  # Ctrl held — pan image
                self._canvas.scan_mark(event.x, event.y)
            else:  # move window
                top = self.winfo_toplevel()
                self._offset_x = event.x_root - top.winfo_rootx()
                self._offset_y = event.y_root - top.winfo_rooty()
        else:
            self._canvas.scan_mark(event.x, event.y)

    def _on_drag_move(self, event):
        if self._is_floating:
            edge = self._resize_edge
            if edge:
                top = self.winfo_toplevel()
                dx = event.x_root - self._resize_start_root_x
                dy = event.y_root - self._resize_start_root_y
                nx, ny, nw, nh = (
                    self._resize_start_x, self._resize_start_y,
                    self._resize_start_w, self._resize_start_h,
                )
                if "e" in edge:
                    nw = max(200, self._resize_start_w + dx)
                if "w" in edge:
                    nw = max(200, self._resize_start_w - dx)
                    nx = self._resize_start_x + self._resize_start_w - nw
                if "s" in edge:
                    nh = max(150, self._resize_start_h + dy)
                if "n" in edge:
                    nh = max(150, self._resize_start_h - dy)
                    ny = self._resize_start_y + self._resize_start_h - nh
                top.geometry(f"{nw}x{nh}+{nx}+{ny}")
                return
            if event.state & 0x0004:  # Ctrl held — pan image
                self._canvas.scan_dragto(event.x, event.y, gain=1)
            else:  # move window
                top = self.winfo_toplevel()
                new_x = event.x_root - self._offset_x
                new_y = event.y_root - self._offset_y
                top.geometry(f"+{new_x}+{new_y}")
        else:
            self._canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_drag_end(self, _event):
        self._resize_edge = None

    # ---- right-click / fullscreen ----

    def _on_right_click(self, event):
        self._ctx_menu.post(event.x_root, event.y_root)

    def _toggle_float_mode(self):
        self._is_floating = not self._is_floating
        top = self.winfo_toplevel()

        if self._is_floating:
            self._saved_geometry = top.geometry()
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            top.config(menu="")
            top._statusbar.pack_forget()
            self._toolbar_frame.pack_forget()
            self._info_label2.pack_forget()
            self._hsb.grid_forget()
            self._vsb.grid_forget()
            self._canvas_frame.pack_configure(padx=0, pady=0)
            self.update_idletasks()
            self._fit_to_window()
            top.bind("<Escape>", self._exit_float_mode)
        else:
            top.overrideredirect(False)
            top.attributes('-topmost', False)
            top.unbind("<Escape>")
            top.config(menu=top._menubar)
            top._statusbar.pack(side="bottom", fill="x")
            self._canvas_frame.pack_configure(padx=8, pady=4)
            self._toolbar_frame.pack(before=self._canvas_frame, fill="x", padx=8, pady=4)
            self._info_label2.pack(fill="x", padx=8, pady=(0, 4))
            top.geometry(self._saved_geometry)
            self._fit_to_window()

    def _exit_float_mode(self, _event=None):
        if getattr(self, '_is_floating', False):
            self._toggle_float_mode()

    def _save_current(self):
        filepath = self._file_list[self._current_idx]
        out_name = os.path.splitext(os.path.basename(filepath))[0]
        if not (out_name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))):
            out_name = out_name + ".png"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=out_name,
            filetypes=[(tr("tg_filetype_img"), "*.jpg *.jpeg *.png *.gif *.webp *.bmp"), (tr("tg_filetype_all"), "*.*")],
        )
        if not save_path:
            return
        try:
            with open(filepath, "rb") as f:
                raw = f.read()
            img_bytes = self.engine.decrypt_image(raw)
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            messagebox.showinfo(tr("tg_done"), tr("tg_saved_to", save_path=save_path))
        except Exception as e:
            messagebox.showerror(tr("tg_error"), str(e))


# ═══════════════════════════════════════════════════════════════════════
# SettingsDialog
# ═══════════════════════════════════════════════════════════════════════

class SettingsDialog(tk.Toplevel):
    """Simple settings dialog."""

    def __init__(self, parent, config: dict, on_save=None):
        super().__init__(parent)
        self._config = config
        self._on_save = on_save

        self.title(tr("st_title"))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        pad = {"padx": 16, "pady": 6}

        ttk.Label(self, text=tr("st_boss_key_label"), font=("", 11)).pack(anchor="w", **pad)

        desc = ttk.Label(
            self,
            text=tr("st_boss_key_desc"),
            foreground="gray",
        )
        desc.pack(anchor="w", padx=16)

        self._combo_var = tk.StringVar(value=config.get("boss_key", "ctrl+shift+h"))
        self._entry = ttk.Entry(self, textvariable=self._combo_var, font=("", 11), width=30)
        self._entry.pack(fill="x", **pad)

        # language selector
        lang_frame = ttk.Frame(self)
        lang_frame.pack(fill="x", **pad)
        ttk.Label(lang_frame, text=tr("st_lang_label"), font=("", 11)).pack(side="left")
        self._lang_var = tk.StringVar(value=config.get("lang", "zh"))
        lang_combo = ttk.Combobox(lang_frame, textvariable=self._lang_var,
                                   values=["zh", "en"], state="readonly", width=8)
        lang_combo.pack(side="left", padx=(8, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", **pad)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        ttk.Button(btn_frame, text=tr("st_save"), command=self._on_ok).grid(
            row=0, column=0, padx=(0, 4), sticky="ew"
        )
        ttk.Button(btn_frame, text=tr("pw_cancel"), command=self.destroy).grid(
            row=0, column=1, padx=(4, 0), sticky="ew"
        )

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())

        self._entry.focus_set()
        self._entry.select_range(0, "end")

        self.update_idletasks()
        w, h = 420, 240
        ws = self.winfo_screenwidth()
        hs = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(ws - w) // 2}+{(hs - h) // 2}")

    def _on_ok(self):
        combo = self._combo_var.get().strip()
        if not combo:
            messagebox.showwarning(tr("st_title"), tr("st_key_empty"), parent=self)
            return
        from boss_key import _parse_combo
        try:
            _parse_combo(combo)
        except ValueError as e:
            messagebox.showwarning(tr("st_title"), str(e), parent=self)
            return
        self._config["boss_key"] = combo
        self._config["lang"] = self._lang_var.get()
        save_config(self._config)
        if self._on_save:
            self._on_save()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════
# VaultApp
# ═══════════════════════════════════════════════════════════════════════

class VaultApp(tk.Tk):
    """Main application window."""

    def __init__(self, engine: CryptoEngine):
        super().__init__()
        self.engine = engine
        self._config = load_config()
        set_lang(self._config.get("lang", "zh"))

        self.title(tr("va_title"))
        self.geometry("1200x800")
        self.minsize(100, 100)

        self._status_var = tk.StringVar(value=tr("va_status_ready"))
        self._active_view: str = "gallery"

        self._build_menu()
        self._build_statusbar()

        # views (lazy-created on demand)
        self._gallery: ThumbnailGallery | None = None
        self._viewer: ImageViewer | None = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # boss key (global hotkey)
        self._boss_key = BossKeyHandler(self, self._config.get("boss_key", "ctrl+shift+h"))
        self.bind("<<BossKey>>", self._toggle_boss)
        self._hidden = False

        self._show_gallery()

    # ------------------------------------------------------------------
    # menu
    # ------------------------------------------------------------------

    def _build_menu(self):
        bar = tk.Menu(self)
        self._menubar = bar
        self.config(menu=bar)

        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label=tr("va_menu_open"), command=self._open_vault)
        file_menu.add_command(label=tr("va_menu_encrypt"), command=self._encrypt_images)
        file_menu.add_command(label=tr("va_menu_decrypt"), command=self._decrypt_images)
        file_menu.add_separator()
        file_menu.add_command(label=tr("va_menu_exit"), command=self._on_close)
        bar.add_cascade(label=tr("va_menu_file"), menu=file_menu)

        view_menu = tk.Menu(bar, tearoff=0)
        view_menu.add_command(label=tr("va_menu_gallery"), command=self._show_gallery)
        view_menu.add_command(label=tr("va_menu_refresh"), command=self._refresh)
        bar.add_cascade(label=tr("va_menu_view"), menu=view_menu)

        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label=tr("va_menu_settings"), command=self._open_settings)
        help_menu.add_command(label=tr("va_menu_about"), command=self._about)
        bar.add_cascade(label=tr("va_menu_help"), menu=help_menu)

    def _build_statusbar(self):
        sb = ttk.Frame(self, relief="sunken")
        self._statusbar = sb
        sb.pack(side="bottom", fill="x")
        ttk.Label(sb, textvariable=self._status_var, anchor="w", padding=(8, 3)).pack(
            side="left", fill="x", expand=True
        )

    # ------------------------------------------------------------------
    # view switching
    # ------------------------------------------------------------------

    def _show_gallery(self):
        self._hide_viewer()
        if self._gallery is None:
            self._gallery = ThumbnailGallery(
                self, self.engine,
                on_click=self._open_viewer,
                status_var=self._status_var,
            )
        self._gallery.pack(fill="both", expand=True)
        self._active_view = "gallery"
        self._status_var.set(tr("va_status_ready_short"))

    def _open_viewer(self, idx: int):
        if self._gallery is None:
            return
        file_list = self._gallery.file_list
        if not file_list:
            return
        self._gallery.pack_forget()
        if self._viewer is None:
            self._viewer = ImageViewer(
                self, self.engine, file_list,
                status_var=self._status_var,
                on_back=self._show_gallery,
            )
        else:
            self._viewer._file_list = file_list
        self._viewer.pack(fill="both", expand=True)
        self._viewer.show_image(idx)
        self._active_view = "viewer"

    def _hide_viewer(self):
        if self._viewer is not None:
            self._viewer.pack_forget()
        self._active_view = "gallery"

    # ------------------------------------------------------------------
    # menu actions
    # ------------------------------------------------------------------

    def _open_vault(self):
        os.makedirs(VAULT_DIR, exist_ok=True)
        path = filedialog.askdirectory(title=tr("va_choose_vault"), initialdir=VAULT_DIR)
        if not path:
            return
        if self._viewer is not None:
            self._viewer.pack_forget()
        self._show_gallery()
        if self._gallery is not None:
            self._gallery.set_folder(path)

    def _refresh(self):
        if self._active_view == "gallery" and self._gallery is not None:
            self._gallery._scan()

    def _encrypt_images(self):
        paths = filedialog.askopenfilenames(
            title=tr("va_choose_images"),
            filetypes=[(tr("tg_filetype_img"), "*.jpg *.jpeg *.png *.gif *.webp *.bmp"), (tr("tg_filetype_all"), "*.*")],
        )
        if not paths:
            return

        # pick output folder
        os.makedirs(VAULT_DIR, exist_ok=True)
        out_dir = filedialog.askdirectory(title=tr("va_choose_out"), initialdir=VAULT_DIR)
        if not out_dir:
            return

        progress = _ProgressDialog(self, tr("va_encrypting"), len(paths))
        errors: list[str] = []

        def worker():
            for i, src in enumerate(paths):
                if progress.cancelled:
                    break
                try:
                    with open(src, "rb") as f:
                        data = f.read()
                    encrypted = self.engine.encrypt_image(data)
                    base = os.path.basename(src)
                    out_path = os.path.join(out_dir, base + ".dat")
                    with open(out_path, "wb") as f:
                        f.write(encrypted)
                except Exception as e:
                    errors.append(f"{os.path.basename(src)}: {e}")
                self.after(0, lambda n=i + 1: progress.update(n))
            self.after(0, _finish)

        def _finish():
            progress.destroy()
            done = len(paths) - len(errors)
            msg = tr("va_encrypted_done", done=done, total=len(paths))
            if errors:
                msg += tr("va_error_header", count=len(errors)) + "\n".join(errors[:10])
                if len(errors) > 10:
                    msg += tr("va_error_more", remain=len(errors) - 10)
            messagebox.showinfo(tr("tg_done"), msg)
            if self._gallery is not None and self._gallery.winfo_ismapped():
                folder = self._gallery._folder_var.get()
                if folder == out_dir:
                    self._gallery._scan()

        threading.Thread(target=worker, daemon=True).start()

    def _decrypt_images(self):
        paths = filedialog.askopenfilenames(
            title=tr("va_choose_dat"),
            filetypes=[(tr("va_filetype_dat"), "*.dat"), (tr("tg_filetype_all"), "*.*")],
        )
        if not paths:
            return
        os.makedirs(VAULT_DIR, exist_ok=True)
        out_dir = filedialog.askdirectory(title=tr("va_choose_decrypt_out"), initialdir=VAULT_DIR)
        if not out_dir:
            return

        progress = _ProgressDialog(self, tr("va_decrypting"), len(paths))
        errors: list[str] = []

        def worker():
            for i, src in enumerate(paths):
                if progress.cancelled:
                    break
                try:
                    with open(src, "rb") as f:
                        raw = f.read()
                    img_bytes = self.engine.decrypt_image(raw)
                    # filename.orig.ext.dat → orig.ext
                    base = os.path.basename(src)
                    if base.lower().endswith(".dat"):
                        base = base[:-4]
                    out_path = os.path.join(out_dir, base)
                    with open(out_path, "wb") as f:
                        f.write(img_bytes)
                except Exception as e:
                    errors.append(f"{os.path.basename(src)}: {e}")
                self.after(0, lambda n=i + 1: progress.update(n))
            self.after(0, _finish)

        def _finish():
            progress.destroy()
            done = len(paths) - len(errors)
            msg = tr("va_decrypted_done", done=done, total=len(paths))
            if errors:
                msg += tr("va_error_header", count=len(errors)) + "\n".join(errors[:10])
                if len(errors) > 10:
                    msg += tr("va_error_more", remain=len(errors) - 10)
            messagebox.showinfo(tr("tg_done"), msg)

        threading.Thread(target=worker, daemon=True).start()

    def _reload_boss_key(self):
        self._boss_key.unregister()
        self._boss_key = BossKeyHandler(self, self._config.get("boss_key", "ctrl+shift+h"))

    def _open_settings(self):
        SettingsDialog(self, self._config, on_save=self._reload_boss_key)

    def _about(self):
        messagebox.showinfo(
            tr("va_about_title"),
            tr("va_about_text")
        )

    def _on_close(self):
        self._boss_key.unregister()
        self.engine.zero_master_key()
        self.destroy()

    def _toggle_boss(self, _event=None):
        if self._hidden:
            self.deiconify()
            self.lift()
            self.focus_force()
            self._status_var.set(tr("va_status_ready_short"))
            self._hidden = False
        else:
            self._status_var.set(tr("va_status_hidden", key=self._config.get("boss_key", "Ctrl+Shift+H")))
            self._hidden = True
            self.withdraw()


# ═══════════════════════════════════════════════════════════════════════
# ProgressDialog
# ═══════════════════════════════════════════════════════════════════════

class _ProgressDialog(tk.Toplevel):
    """Simple progress dialog for batch operations."""

    def __init__(self, parent, title: str, total: int):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.cancelled = False
        self._total = total

        w, h = 380, 100
        ws = self.winfo_screenwidth()
        hs = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(ws - w) // 2}+{(hs - h) // 2}")

        self._label = ttk.Label(self, text=f"0/{total}", font=("", 11))
        self._label.pack(padx=16, pady=(16, 4))

        self._bar = ttk.Progressbar(self, maximum=total, length=340)
        self._bar.pack(padx=16, pady=4)

        ttk.Button(self, text=tr("pw_cancel"), command=self._cancel).pack(pady=4)

    def update(self, n: int):
        self._label.config(text=f"{n}/{self._total}")
        self._bar["value"] = n
        self.update_idletasks()

    def _cancel(self):
        self.cancelled = True
        self._label.config(text=tr("pd_cancelling"))
