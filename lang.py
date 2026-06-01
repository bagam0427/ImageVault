"""ImageVault i18n — dict-based, no gettext dependency."""

_STRINGS = {
    # ── PasswordDialog ──
    "pw_title":         {"zh": "ImageVault — 解锁",           "en": "ImageVault — Unlock"},
    "pw_prompt":        {"zh": "输入密码解锁保险库：",         "en": "Enter password to unlock vault:"},
    "pw_show":          {"zh": "显示",                        "en": "Show"},
    "pw_unlock":        {"zh": "解锁",                        "en": "Unlock"},
    "pw_cancel":        {"zh": "取消",                        "en": "Cancel"},

    # ── ThumbnailGallery ──
    "tg_vault_dir":     {"zh": "保险库文件夹：",              "en": "Vault folder:"},
    "tg_browse":        {"zh": "浏览...",                     "en": "Browse..."},
    "tg_scan":          {"zh": "扫描",                        "en": "Scan"},
    "tg_decrypt_save":  {"zh": "解密并另存为...",             "en": "Decrypt & Save As..."},
    "tg_delete":        {"zh": "删除",                        "en": "Delete"},
    "tg_choose_vault":  {"zh": "选择保险库文件夹",            "en": "Select Vault Folder"},
    "tg_no_dat":        {"zh": "此文件夹中未找到 .dat 文件",  "en": "No .dat files found in this folder."},
    "tg_no_dat_detail": {"zh": "未找到加密的 .dat 文件。\n\n请使用 文件 > 加密图片 添加。",
                         "en": "No encrypted .dat files found.\n\nUse File > Encrypt Images to add some."},
    "tg_loading":       {"zh": "加载中 {current}/{total}...", "en": "Loading {current}/{total}..."},
    "tg_loaded":        {"zh": "已加载 {count} 个文件",       "en": "{count} file(s) loaded"},
    "tg_saved_to":      {"zh": "已保存至：\n{save_path}",     "en": "Saved to:\n{save_path}"},
    "tg_delete_confirm": {"zh": "删除\n{name}？",             "en": "Delete\n{name}?"},
    "tg_filetype_img":  {"zh": "图片",                        "en": "Images"},
    "tg_filetype_all":  {"zh": "所有文件",                    "en": "All Files"},
    "tg_done":          {"zh": "完成",                        "en": "Done"},
    "tg_error":         {"zh": "错误",                        "en": "Error"},
    "tg_confirm":       {"zh": "确认",                        "en": "Confirm"},

    # ── ImageViewer ──
    "iv_back_gallery":  {"zh": "← 图库",                     "en": "← Gallery"},
    "iv_prev_img":      {"zh": "◀ 上一张",                   "en": "◀ Prev"},
    "iv_next_img":      {"zh": "下一张 ▶",                   "en": "Next ▶"},
    "iv_prev_frame":    {"zh": "◁",                           "en": "◁"},
    "iv_play":          {"zh": "▶",                           "en": "▶"},
    "iv_pause":         {"zh": "⏸",                           "en": "⏸"},
    "iv_next_frame":    {"zh": "▷",                           "en": "▷"},
    "iv_fit":           {"zh": "适应",                        "en": "Fit"},
    "iv_float_mode":    {"zh": "无边框查看",                  "en": "Borderless View"},
    "iv_gif_frames":    {"zh": "GIF · {n_frames}帧",         "en": "GIF · {n_frames} frames"},
    "iv_info_bar":      {"zh": "{name}  |  {w}×{h}  |  {size} 字节  {extra}",
                         "en": "{name}  |  {w}×{h}  |  {size} bytes  {extra}"},
    "iv_img_n_of_m":    {"zh": "图片 {current}/{total}",      "en": "Image {current}/{total}"},

    # ── SettingsDialog ──
    "st_title":         {"zh": "设置",                        "en": "Settings"},
    "st_boss_key_label": {"zh": "老板键快捷键:",              "en": "Boss Key:"},
    "st_boss_key_desc": {"zh": "格式如 ctrl+shift+h, ctrl+q, alt+f1\n支持: ctrl, shift, alt, win + A-Z/0-9/F1-F12/方向键等",
                         "en": "Format: ctrl+shift+h, ctrl+q, alt+f1\nSupports: ctrl, shift, alt, win + A-Z/0-9/F1-F12/arrow keys"},
    "st_lang_label":    {"zh": "界面语言:",                   "en": "Language:"},
    "st_save":          {"zh": "保存",                        "en": "Save"},
    "st_key_empty":     {"zh": "快捷键不能为空。",            "en": "Shortcut cannot be empty."},

    # ── VaultApp ──
    "va_title":         {"zh": "ImageVault",                  "en": "ImageVault"},
    "va_status_ready":  {"zh": "就绪。使用 文件 > 打开保险库 或 文件 > 加密图片。",
                         "en": "Ready. Use File > Open Vault or File > Encrypt Images."},
    "va_status_ready_short": {"zh": "就绪。",                 "en": "Ready."},
    "va_status_hidden": {"zh": "已隐藏 — {key} 恢复",         "en": "Hidden — {key} to restore"},
    "va_menu_file":     {"zh": "文件",                        "en": "File"},
    "va_menu_open":     {"zh": "打开保险库...",               "en": "Open Vault..."},
    "va_menu_encrypt":  {"zh": "加密图片...",                 "en": "Encrypt Images..."},
    "va_menu_decrypt":  {"zh": "解密图片...",                 "en": "Decrypt Images..."},
    "va_menu_exit":     {"zh": "退出",                        "en": "Exit"},
    "va_menu_view":     {"zh": "查看",                        "en": "View"},
    "va_menu_gallery":  {"zh": "图库",                        "en": "Gallery"},
    "va_menu_refresh":  {"zh": "刷新",                        "en": "Refresh"},
    "va_menu_help":     {"zh": "帮助",                        "en": "Help"},
    "va_menu_settings": {"zh": "设置...",                     "en": "Settings..."},
    "va_menu_about":    {"zh": "关于",                        "en": "About"},
    "va_choose_vault":  {"zh": "选择保险库文件夹",            "en": "Select Vault Folder"},
    "va_choose_images": {"zh": "选择要加密的图片",            "en": "Select Images to Encrypt"},
    "va_choose_out":    {"zh": "选择 .dat 文件输出文件夹",    "en": "Select Output Folder for .dat Files"},
    "va_encrypting":    {"zh": "加密中",                      "en": "Encrypting"},
    "va_encrypted_done": {"zh": "已加密 {done}/{total} 个文件。", "en": "{done}/{total} file(s) encrypted."},
    "va_error_header":  {"zh": "\n\n错误 ({count})：\n",      "en": "\n\nErrors ({count}):\n"},
    "va_error_more":    {"zh": "\n...还有 {remain} 个。",      "en": "\n...and {remain} more."},
    "va_choose_dat":    {"zh": "选择要解密的 .dat 文件",      "en": "Select .dat Files to Decrypt"},
    "va_filetype_dat":  {"zh": "加密文件",                    "en": "Encrypted Files"},
    "va_choose_decrypt_out": {"zh": "选择解密图片输出文件夹",  "en": "Select Output Folder for Decrypted Images"},
    "va_decrypting":    {"zh": "解密中",                      "en": "Decrypting"},
    "va_decrypted_done": {"zh": "已解密 {done}/{total} 个文件。", "en": "{done}/{total} file(s) decrypted."},
    "va_about_title":   {"zh": "关于 ImageVault",             "en": "About ImageVault"},
    "va_about_text":    {"zh": "ImageVault v1.0.0\n\n基于 AES-256-GCM 加密的安全图片查看器。\n图片仅在内存中解密 — 不会写入磁盘。\n\n如果觉得好用，请我喝杯咖啡 ☕",
                         "en": "ImageVault v1.0.0\n\nA secure image viewer with AES-256-GCM encryption.\nImages are only decrypted in memory — never written to disk.\n\nBuy me a coffee if you find it useful ☕"},

    # ── _ProgressDialog ──
    "pd_cancelling":    {"zh": "正在取消...",                 "en": "Cancelling..."},
}

_lang = "zh"


def tr(_key: str, *args, **kwargs) -> str:
    entry = _STRINGS.get(_key)
    if entry is None:
        return _key
    s = entry.get(_lang, entry.get("zh", _key))
    if args or kwargs:
        s = s.format(*args, **kwargs)
    return s


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang


def get_lang() -> str:
    return _lang
