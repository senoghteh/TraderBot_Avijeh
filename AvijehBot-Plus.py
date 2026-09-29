# -*- coding: utf-8 -*-
"""
AvijehBot-advanced (نسخه سریع / Optimized) + GUI  —  نسخه نهایی برای EXE
+ یک tk.Tk() واحد (رفع Hang در exe)
+ استفاده از alpha=0.0 به جای withdraw (رفع مشکل Toplevel)
+ لاگ فایلی برای دیباگ (avijeh_debug.log)
+ حذف sys.stdout.reconfigure
+ import محافظت‌شده MetaTrader5
"""
import sys
import io
import os
import datetime as _dt

# ==================== DEBUG LOGGING (فایل) ====================
def _dbg(msg: str):
    try:
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "avijeh_debug.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]} | {msg}\n")
    except Exception:
        pass

_dbg("=" * 60)
_dbg("PROCESS START")
_dbg(f"frozen={getattr(sys, 'frozen', False)}")
_dbg(f"executable={sys.executable}")
_dbg(f"cwd={os.getcwd()}")
# =============================================================

import threading
import queue
import json
import re
import hmac
import hashlib
import base64
import subprocess
import secrets

# (sys.stdout.reconfigure حذف شد — در exe باعث مسدود شدن خروجی می‌شود)

import time
import requests
from datetime import datetime, time as dt_time, timedelta
import pytz
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

_dbg("Standard imports OK")

# ---------- Safe MetaTrader5 import ----------
try:
    import MetaTrader5 as mt5
    _MT5_IMPORT_ERROR = None
    try:
        _dbg(f"MetaTrader5 imported, version={mt5.__version__}")
    except Exception:
        _dbg("MetaTrader5 imported (no __version__)")
except Exception as _mt5_err:
    mt5 = None
    _MT5_IMPORT_ERROR = str(_mt5_err)
    _dbg(f"MetaTrader5 import FAILED: {_mt5_err}")

# ==================== BiDi / Persian shaping ====================
_ARABIC_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _BIDI_OK = True
    _dbg("BiDi libraries OK")
except Exception as _e:
    print("BiDi setup warning (pip install arabic-reshaper python-bidi):", _e)
    _BIDI_OK = False
    _dbg(f"BiDi libraries FAILED: {_e}")


def fa(text) -> str:
    if text is None:
        return ""
    s = str(text)
    if not _BIDI_OK or not _ARABIC_RE.search(s):
        return s
    try:
        out_lines = []
        for line in s.split("\n"):
            if not _ARABIC_RE.search(line):
                out_lines.append(line)
                continue
            reshaped = arabic_reshaper.reshape(line)
            out_lines.append(get_display(reshaped, base_dir='R'))
        return "\n".join(out_lines)
    except Exception:
        return s


def to_fa_num(s) -> str:
    return ''.join(_FA_DIGITS[int(c)] if c.isdigit() else c for c in str(s))


# ==================== LICENSE / TRIAL SYSTEM ====================
_LICENSE_SECRET = b"AvijehBot_2025_M3hd1Z4r3_D0ntSh4re_Th1sK3y"
TRIAL_DAYS = 10

_LICENSE_ACTIVE  = False
_TRIAL_DAYS_LEFT = 0
_NEEDS_ACTIVATION = False


def _derive_keys(secret: bytes):
    enc_key = hashlib.sha256(secret + b"|enc-v1").digest()
    mac_key = hashlib.sha256(secret + b"|mac-v1").digest()
    return enc_key, mac_key


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(enc_key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def encrypt_license(plaintext: str, secret: bytes) -> str:
    enc_key, mac_key = _derive_keys(secret)
    nonce = secrets.token_bytes(16)
    pt = plaintext.encode("utf-8")
    ct = _xor_bytes(pt, _keystream(enc_key, nonce, len(pt)))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()[:16]
    b64 = base64.urlsafe_b64encode
    return f"AVJ1:{b64(nonce).decode()}:{b64(ct).decode()}:{b64(tag).decode()}"


def decrypt_license(blob: str, secret: bytes) -> str:
    try:
        parts = blob.strip().split(":")
        if len(parts) != 4 or parts[0] != "AVJ1":
            return ""
        b64d = base64.urlsafe_b64decode
        nonce = b64d(parts[1]); ct = b64d(parts[2]); tag = b64d(parts[3])
        enc_key, mac_key = _derive_keys(secret)
        expected = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(expected, tag):
            return ""
        pt = _xor_bytes(ct, _keystream(enc_key, nonce, len(ct)))
        return pt.decode("utf-8")
    except Exception:
        return ""


def _license_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "license.key")


def _trial_path() -> str:
    if os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AvijehBot")
    else:
        base = os.path.join(os.path.expanduser("~"), ".avijehbot")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, "trial.dat")


def _run_cmd(args, timeout=8) -> str:
    try:
        out = subprocess.check_output(
            args, shell=False, stderr=subprocess.DEVNULL, timeout=timeout,
            creationflags=(0x08000000 if os.name == "nt" else 0),
        )
        return out.decode(errors="ignore")
    except Exception:
        return ""


def get_hwid() -> str:
    _dbg("get_hwid: start")
    parts = []

    # مسیر سریع: رجیستری
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        if guid and len(guid) >= 8:
            parts.append(guid)
            _dbg(f"get_hwid: MachineGuid={guid[:8]}...")
    except Exception as e:
        _dbg(f"get_hwid: registry read failed: {e}")

    # پشتیبان: wmic
    if not parts:
        txt = _run_cmd(["wmic", "csproduct", "get", "uuid"], timeout=4)
        for line in txt.splitlines():
            line = line.strip()
            if line and "UUID" not in line.upper() and len(line) >= 8:
                parts.append(line); break

    # پشتیبان دوم: powershell
    if not parts:
        txt = _run_cmd([
            "powershell", "-NoProfile", "-Command",
            "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"
        ], timeout=4)
        for line in txt.splitlines():
            line = line.strip()
            if line and line.upper() not in ("UUID",) and len(line) >= 8:
                parts.append(line); break

    parts.append(os.environ.get("COMPUTERNAME", "unknown"))
    raw = "|".join(parts).strip().upper()
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    hwid_hex = h[:16].upper()
    result = "-".join(hwid_hex[i:i+4] for i in range(0, 16, 4))
    _dbg(f"get_hwid: result={result}")
    return result


_B32_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _b32_encode(data: bytes) -> str:
    bits = "".join(format(b, "08b") for b in data)
    while len(bits) % 5:
        bits += "0"
    return "".join(_B32_ALPHABET[int(bits[i:i+5], 2)] for i in range(0, len(bits), 5))


def generate_license(hwid: str) -> str:
    hwid = hwid.strip().upper().replace(" ", "")
    mac = hmac.new(_LICENSE_SECRET, hwid.encode("utf-8"), hashlib.sha256).digest()
    code = _b32_encode(mac[:10])
    return "-".join(code[i:i+4] for i in range(0, 16, 4))


def verify_license(hwid: str, license_key: str) -> bool:
    if not hwid or not license_key:
        return False
    expected = generate_license(hwid)
    return hmac.compare_digest(expected, license_key.strip().upper())


def save_license_file(key: str, hwid: str) -> bool:
    try:
        payload = f"{hwid.strip().upper()}|{key.strip().upper()}"
        blob = encrypt_license(payload, _LICENSE_SECRET)
        with open(_license_path(), "w", encoding="utf-8") as f:
            f.write(blob)
        _dbg("save_license_file: saved OK")
        return True
    except Exception as e:
        _dbg(f"save_license_file: ERROR {e}")
        return False


def load_saved_license() -> tuple:
    p = _license_path()
    if not os.path.exists(p):
        return "", ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            blob = f.read().strip()
    except Exception:
        return "", ""
    plain = decrypt_license(blob, _LICENSE_SECRET)
    if not plain or "|" not in plain:
        return "", ""
    parts = plain.split("|", 1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip().upper(), parts[1].strip().upper()


def _get_or_create_trial_start(hwid: str) -> int:
    p = _trial_path()
    now_ts = int(time.time())
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                blob = f.read().strip()
            plain = decrypt_license(blob, _LICENSE_SECRET)
            if plain and plain.startswith("TRIAL|"):
                parts = plain.split("|", 2)
                if len(parts) >= 3 and parts[1] == hwid:
                    try:
                        return int(parts[2])
                    except Exception:
                        pass
        except Exception:
            pass
    try:
        payload = f"TRIAL|{hwid}|{now_ts}"
        blob = encrypt_license(payload, _LICENSE_SECRET)
        with open(p, "w", encoding="utf-8") as f:
            f.write(blob)
    except Exception:
        pass
    return now_ts


def trial_status(hwid: str) -> tuple:
    start_ts = _get_or_create_trial_start(hwid)
    elapsed = time.time() - start_ts
    total   = TRIAL_DAYS * 86400.0
    if elapsed < total:
        remaining_sec = total - elapsed
        days_left = int(remaining_sec // 86400) + 1
        if days_left > TRIAL_DAYS:
            days_left = TRIAL_DAYS
        return True, days_left
    return False, 0


# ---------- پنجره گفتگوی سفارشی RTL (همیشه روی parent) ----------
def _show_rtl_dialog(parent, title_fa: str, message_fa: str,
                     width: int = 560, height: int = 320):
    win = tk.Toplevel(parent)
    win.title(title_fa)
    win.geometry(f"{width}x{height}")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()

    try:
        win.iconbitmap("app.ico")
    except Exception:
        pass

    tk.Label(
        win,
        text=fa(title_fa),
        font=("Tahoma", 13, "bold"),
        anchor="center", justify="center",
    ).pack(pady=(20, 12), fill="x")

    tk.Label(
        win,
        text=fa(message_fa),
        font=("Tahoma", 11),
        anchor="center", justify="center",
        wraplength=width - 60,
    ).pack(padx=20, pady=8, fill="both", expand=True)

    tk.Button(
        win,
        text=fa("تأیید"),
        font=("Tahoma", 11),
        width=14,
        command=win.destroy,
    ).pack(pady=(8, 18))

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    parent.wait_window(win)


def _show_trial_dialog(parent, days_left: int):
    win = tk.Toplevel(parent)
    win.title("نسخه آزمایشی")
    win.geometry("520x340")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()
    try:
        win.iconbitmap("app.ico")
    except Exception:
        pass

    tk.Label(
        win,
        text=fa("شما در نسخه آزمایشی ربات هستید."),
        font=("Tahoma", 12, "bold"),
        anchor="center", justify="center",
    ).pack(pady=(24, 14), fill="x")

    row = tk.Frame(win)
    row.pack(pady=(0, 14))

    tk.Label(
        row,
        text=to_fa_num(days_left),
        font=("Tahoma", 22, "bold"),
        fg="#06c",
    ).pack(side="right", padx=(0, 8))

    tk.Label(
        row,
        text=fa("روز باقی‌مانده"),
        font=("Tahoma", 13, "bold"),
        fg="#06c",
    ).pack(side="right")

    tk.Label(
        win,
        text=fa("برای فعال‌سازی دائمی، کد سخت‌افزاری را\n"
                "برای پشتیبانی ارسال کنید."),
        font=("Tahoma", 10),
        anchor="center", justify="center",
    ).pack(pady=(0, 12), padx=20)

    tk.Button(
        win,
        text=fa("تأیید"),
        font=("Tahoma", 11),
        width=14,
        command=win.destroy,
    ).pack(pady=(8, 16))

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    parent.wait_window(win)


# ---------- پنجره فعال‌سازی (همیشه روی parent) ----------
def _show_activation_dialog(hwid: str, parent) -> bool:
    win = tk.Toplevel(parent)
    win.title("فعال‌سازی ربات آویژه")
    win.geometry("640x600")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()
    try:
        win.iconbitmap("app.ico")
    except Exception:
        pass

    activated = {"ok": False}

    ttk.Label(
        win,
        text=fa("فعال‌سازی ربات آویژه"),
        font=("Tahoma", 14, "bold"),
    ).pack(pady=(14, 6))

    ttk.Label(
        win,
        text=fa("برای دریافت لایسنس دائمی ربات، درخواست خود را به ایمیل زیر ارسال کنید.\n"
                "کد سخت‌افزاری زیر را همراه درخواست ارسال نمایید.\n"
                "پس از دریافت کلید، آن را در کادر پایین وارد یا Paste کنید."),
        font=("Tahoma", 10),
        justify="center", anchor="center",
        wraplength=580,
    ).pack(pady=(0, 6), padx=16)

    ttk.Label(
        win,
        text="MehdiZare@Outlook.com",
        font=("Consolas", 13, "bold"),
        foreground="#06c",
        justify="center", anchor="center",
    ).pack(pady=(0, 12))

    hwid_frame = ttk.LabelFrame(win, text=fa("کد سخت‌افزاری سیستم"))
    hwid_frame.pack(fill="x", padx=16, pady=(0, 8))

    hwid_var = tk.StringVar(value=hwid)
    ttk.Entry(hwid_frame, textvariable=hwid_var, justify="center",
              font=("Consolas", 11, "bold"), state="readonly").pack(
        fill="x", padx=10, pady=8)

    def copy_hwid():
        win.clipboard_clear()
        win.clipboard_append(hwid)
        messagebox.showinfo("کپی شد", "کد سخت‌افزاری در حافظه کپی شد.", parent=win)

    ttk.Button(hwid_frame, text=fa("کپی کد سخت‌افزاری"),
               command=copy_hwid).pack(pady=(0, 8))

    lic_frame = ttk.LabelFrame(win, text=fa("کلید فعال‌سازی"))
    lic_frame.pack(fill="x", padx=16, pady=(0, 8))

    lic_var = tk.StringVar(value="")
    e2 = ttk.Entry(lic_frame, textvariable=lic_var, justify="center",
                   font=("Consolas", 11, "bold"))
    e2.pack(fill="x", padx=10, pady=8)
    e2.focus_set()

    def _paste_into_entry():
        try:
            data = win.clipboard_get()
        except Exception:
            data = ""
        if not data:
            return
        cleaned = "".join(ch for ch in str(data).strip()
                          if ch.isalnum() or ch == "-").upper()
        lic_var.set(cleaned)
        try:
            e2.icursor("end")
        except Exception:
            pass

    def _copy_from_entry():
        try:
            sel = e2.selection_get()
        except Exception:
            sel = lic_var.get()
        if sel:
            win.clipboard_clear()
            win.clipboard_append(sel)

    def _cut_from_entry():
        _copy_from_entry()
        try:
            e2.delete("sel.first", "sel.last")
        except Exception:
            lic_var.set("")

    def _select_all_entry():
        e2.selection_range(0, "end")
        e2.icursor("end")

    def _show_ctx_menu(event):
        ctx = tk.Menu(win, tearoff=0)
        ctx.add_command(label="چسباندن (Ctrl+V)", command=_paste_into_entry)
        ctx.add_command(label="کپی (Ctrl+C)",     command=_copy_from_entry)
        ctx.add_command(label="برش (Ctrl+X)",     command=_cut_from_entry)
        ctx.add_separator()
        ctx.add_command(label="انتخاب همه (Ctrl+A)", command=_select_all_entry)
        try:
            ctx.tk_popup(event.x_root, event.y_root)
        finally:
            ctx.grab_release()

    e2.bind("<Control-v>", lambda _e: (_paste_into_entry(), "break")[1])
    e2.bind("<Control-V>", lambda _e: (_paste_into_entry(), "break")[1])
    e2.bind("<Shift-Insert>", lambda _e: (_paste_into_entry(), "break")[1])
    e2.bind("<Control-c>", lambda _e: (_copy_from_entry(), "break")[1])
    e2.bind("<Control-C>", lambda _e: (_copy_from_entry(), "break")[1])
    e2.bind("<Control-x>", lambda _e: (_cut_from_entry(), "break")[1])
    e2.bind("<Control-X>", lambda _e: (_cut_from_entry(), "break")[1])
    e2.bind("<Control-a>", lambda _e: (_select_all_entry(), "break")[1])
    e2.bind("<Control-A>", lambda _e: (_select_all_entry(), "break")[1])
    e2.bind("<Button-3>", _show_ctx_menu)
    e2.bind("<Button-2>", _show_ctx_menu)

    paste_row = ttk.Frame(lic_frame)
    paste_row.pack(pady=(0, 8))
    ttk.Button(paste_row, text=fa("چسباندن از حافظه"),
               command=_paste_into_entry).pack(side="left", padx=4)
    ttk.Button(paste_row, text=fa("پاک کردن"),
               command=lambda: lic_var.set("")).pack(side="left", padx=4)

    status_var = tk.StringVar(value=fa("در انتظار ورود کلید..."))
    status_lbl = ttk.Label(win, textvariable=status_var, foreground="#a60",
                           anchor="center", justify="center",
                           font=("Tahoma", 10))
    status_lbl.pack(pady=(0, 6))

    btn_frame = ttk.Frame(win)
    btn_frame.pack(pady=(0, 14))

    def try_activate():
        key = lic_var.get().strip().upper()
        if not key:
            status_var.set(fa("کلید فعال‌سازی را وارد کنید."))
            status_lbl.configure(foreground="#c00")
            return
        if verify_license(hwid, key):
            if save_license_file(key, hwid):
                activated["ok"] = True
                status_var.set(fa("فعال‌سازی موفق. ربات در حال اجراست..."))
                status_lbl.configure(foreground="#0a7")
                win.after(900, win.destroy)
            else:
                status_var.set(fa("خطا در ذخیره فایل لایسنس."))
                status_lbl.configure(foreground="#c00")
        else:
            status_var.set(fa("کلید نامعتبر است برای این سیستم."))
            status_lbl.configure(foreground="#c00")

    e2.bind("<Return>", lambda _e: try_activate())

    ttk.Button(btn_frame, text=fa("فعال‌سازی"), command=try_activate).pack(
        side="left", padx=6)
    ttk.Button(btn_frame, text=fa("خروج"), command=win.destroy).pack(
        side="left", padx=6)

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    parent.wait_window(win)

    return activated["ok"]


def check_license_status() -> tuple:
    """بررسی وضعیت لایسنس. هیچ پنجره‌ای نمی‌سازد.
    Returns: ("licensed", 0) یا ("trial", days) یا ("needs_activation", 0)
    """
    global _LICENSE_ACTIVE, _TRIAL_DAYS_LEFT, _NEEDS_ACTIVATION

    _dbg("check_license_status: start")
    hwid = get_hwid()
    _dbg(f"check_license_status: hwid={hwid}")

    saved_hwid, saved_key = load_saved_license()
    _dbg(f"check_license_status: saved_hwid={saved_hwid!r}")

    if saved_hwid == hwid and saved_key and verify_license(hwid, saved_key):
        _LICENSE_ACTIVE = True
        _dbg("check_license_status: licensed")
        return ("licensed", 0)

    is_active, days_left = trial_status(hwid)
    _dbg(f"check_license_status: trial active={is_active}, days={days_left}")

    if is_active:
        _TRIAL_DAYS_LEFT = days_left
        return ("trial", days_left)

    _NEEDS_ACTIVATION = True
    return ("needs_activation", 0)


# ==================== END LICENSE / TRIAL SYSTEM ====================


# ==================== CONFIG پیش‌فرض ====================
DEFAULT_CONFIG = {
    "SYMBOL": "XAUUSD.st",
    "LOT_SIZE": 0.01,
    "TIMEFRAME_STR": "M15",
    "LEVERAGE": 100,
    "ADX_PERIOD": 16,
    "ADX_THRESHOLD": 25.0,
    "ADX_STRONG_THRESHOLD": 36.0,
    "TRADE_NORMAL_TREND": False,
    "CANDLE_CLOSE_CHECK_COUNT": 3,
    "MAX_PENDING": 4,
    "ORDERS_PER_SIDE": 2,
    "FIRST_DISTANCE_PTS": 1000,
    "STEP_PTS": 1000,
    "ATR_PERIOD": 14,
    "ATR_SL_MULTIPLIER": 3.0,
    "SL_PTS": 5000,
    "SL_MIN_PTS": 300,
    "PROFIT_STEP_USD": 5.0,
    "PROFIT_TRAIL_GAP_USD": 1.0,
    "MAX_POSITION_LOSS_USD": 20.0,
    "SL_BREAKOUT_PTS": 3000,
    "SL_BREAKOUT_COOLDOWN_SEC": 120,
    "MAX_OPEN_POSITIONS": 4,
    "DAILY_MAX_LOSS_USD": 20.0,
    "DAILY_PROFIT_TARGET_USD": 85.0,
    "START_HOUR": 9, "START_MIN": 30,
    "END_HOUR": 22,  "END_MIN": 30,
    "MAGIC": 20250101,
    "DEVIATION": 30,
    "TELEGRAM_TOKEN": "YOUR TOKEN",
    "TELEGRAM_CHAT_IDS": "YOUR CHAT ID1,YOUR CHAT ID2",
    "USE_PROXY": False,
    "PROXY_HTTP": "http://127.0.0.1:10808",
    "PROXY_HTTPS": "http://127.0.0.1:10808",
}

CONFIG_FILE = "avijeh_config.json"

LEVERAGE_PT_FIELDS = (
    "FIRST_DISTANCE_PTS",
    "STEP_PTS",
    "SL_PTS",
    "SL_MIN_PTS",
    "SL_BREAKOUT_PTS",
)

SYMBOL = LOT_SIZE = TIMEFRAME_STR = None
TIMEFRAME = None
ADX_PERIOD = ADX_THRESHOLD = ADX_STRONG_THRESHOLD = None
TRADE_NORMAL_TREND = False
CANDLE_CLOSE_CHECK_COUNT = 3
MAX_PENDING = ORDERS_PER_SIDE = None
FIRST_DISTANCE_PTS = STEP_PTS = None
ATR_PERIOD = ATR_SL_MULTIPLIER = SL_PTS = SL_MIN_PTS = None
PROFIT_STEP_USD = PROFIT_TRAIL_GAP_USD = MAX_POSITION_LOSS_USD = None
SL_BREAKOUT_PTS = SL_BREAKOUT_COOLDOWN_SEC = None
MAX_OPEN_POSITIONS = None
DAILY_MAX_LOSS_USD = DAILY_PROFIT_TARGET_USD = None
START_HOUR = START_MIN = END_HOUR = END_MIN = None
MAGIC = DEVIATION = None
LEVERAGE = 100
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_IDS = []
USE_PROXY = False
PROXY = {"http": "", "https": ""}

if mt5 is not None:
    TIMEFRAME_MAP = {
        "M1":  mt5.TIMEFRAME_M1,
        "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
    }
    TIMEFRAME_NAME_MAP = {
        mt5.TIMEFRAME_M1:  "M1",
        mt5.TIMEFRAME_M5:  "M5",
        mt5.TIMEFRAME_M15: "M15",
    }
else:
    TIMEFRAME_MAP = {"M1": 1, "M5": 5, "M15": 15}
    TIMEFRAME_NAME_MAP = {1: "M1", 5: "M5", 15: "M15"}

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2

MAIN_LOOP_SLEEP      = 0.5
TICK_CACHE_TTL       = 0.15
INFO_CACHE_TTL       = 60.0
DAILY_PNL_CACHE_TTL  = 3.0
TELEGRAM_TIMEOUT     = 5

_cached_info     = None
_cached_info_ts  = 0.0
_tick_cache      = {"tick": None, "ts": 0.0}
_state           = {"positions": [], "orders": [], "valid": False}
_daily_pnl_cache = {"value": 0.0, "ts": 0.0}

STOP_EVENT = threading.Event()


def interruptible_sleep(seconds, step=0.25):
    end = time.time() + seconds
    while time.time() < end:
        if STOP_EVENT.is_set():
            return
        time.sleep(min(step, max(0.0, end - time.time())))


def apply_config(cfg: dict):
    g = globals()
    g["SYMBOL"]        = str(cfg["SYMBOL"]).strip()
    g["LOT_SIZE"]      = float(cfg["LOT_SIZE"])
    g["TIMEFRAME_STR"] = str(cfg["TIMEFRAME_STR"]).upper()
    g["TIMEFRAME"]     = TIMEFRAME_MAP.get(g["TIMEFRAME_STR"], TIMEFRAME_MAP.get("M15"))
    g["ADX_PERIOD"]            = int(cfg["ADX_PERIOD"])
    g["ADX_THRESHOLD"]         = float(cfg["ADX_THRESHOLD"])
    g["ADX_STRONG_THRESHOLD"]  = float(cfg["ADX_STRONG_THRESHOLD"])
    g["TRADE_NORMAL_TREND"]    = bool(cfg["TRADE_NORMAL_TREND"])
    g["CANDLE_CLOSE_CHECK_COUNT"] = int(cfg["CANDLE_CLOSE_CHECK_COUNT"])
    g["MAX_PENDING"]     = int(cfg["MAX_PENDING"])
    g["ORDERS_PER_SIDE"] = int(cfg["ORDERS_PER_SIDE"])
    try:
        lev_val = int(float(cfg.get("LEVERAGE", 100)))
    except Exception:
        lev_val = 100
    if lev_val <= 0:
        lev_val = 100
    g["LEVERAGE"] = lev_val
    g["FIRST_DISTANCE_PTS"] = max(1, int(cfg["FIRST_DISTANCE_PTS"]))
    g["STEP_PTS"]           = max(1, int(cfg["STEP_PTS"]))
    g["SL_PTS"]             = max(1, int(cfg["SL_PTS"]))
    g["SL_MIN_PTS"]         = max(1, int(cfg["SL_MIN_PTS"]))
    g["SL_BREAKOUT_PTS"]    = max(1, int(cfg["SL_BREAKOUT_PTS"]))
    print(f"[LEVERAGE] 1:{lev_val} | FirstDist={g['FIRST_DISTANCE_PTS']} | "
          f"Step={g['STEP_PTS']} | SL={g['SL_PTS']} | "
          f"SLmin={g['SL_MIN_PTS']} | SLBreak={g['SL_BREAKOUT_PTS']}", flush=True)
    g["ATR_PERIOD"]        = int(cfg["ATR_PERIOD"])
    g["ATR_SL_MULTIPLIER"] = float(cfg["ATR_SL_MULTIPLIER"])
    g["PROFIT_STEP_USD"]        = float(cfg["PROFIT_STEP_USD"])
    g["PROFIT_TRAIL_GAP_USD"]   = float(cfg["PROFIT_TRAIL_GAP_USD"])
    g["MAX_POSITION_LOSS_USD"]  = float(cfg["MAX_POSITION_LOSS_USD"])
    g["SL_BREAKOUT_COOLDOWN_SEC"] = int(cfg["SL_BREAKOUT_COOLDOWN_SEC"])
    g["MAX_OPEN_POSITIONS"] = int(cfg["MAX_OPEN_POSITIONS"])
    g["DAILY_MAX_LOSS_USD"]      = float(cfg["DAILY_MAX_LOSS_USD"])
    g["DAILY_PROFIT_TARGET_USD"] = float(cfg["DAILY_PROFIT_TARGET_USD"])
    g["START_HOUR"] = int(cfg["START_HOUR"]);  g["START_MIN"] = int(cfg["START_MIN"])
    g["END_HOUR"]   = int(cfg["END_HOUR"]);    g["END_MIN"]   = int(cfg["END_MIN"])
    g["MAGIC"]     = int(cfg["MAGIC"])
    g["DEVIATION"] = int(cfg["DEVIATION"])
    g["TELEGRAM_TOKEN"] = str(cfg["TELEGRAM_TOKEN"]).strip()
    raw_ids = cfg["TELEGRAM_CHAT_IDS"]
    if isinstance(raw_ids, str):
        g["TELEGRAM_CHAT_IDS"] = [c.strip() for c in raw_ids.split(",") if c.strip()]
    else:
        g["TELEGRAM_CHAT_IDS"] = list(raw_ids)
    g["USE_PROXY"] = bool(cfg["USE_PROXY"])
    PROXY["http"]  = str(cfg["PROXY_HTTP"]).strip()
    PROXY["https"] = str(cfg["PROXY_HTTPS"]).strip()


def load_config_file():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(saved)
            return cfg
        except Exception as e:
            print("load config error:", e, flush=True)
    return dict(DEFAULT_CONFIG)


def save_config_file(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_symbol_info_cached():
    global _cached_info, _cached_info_ts
    now = time.time()
    if _cached_info is None or (now - _cached_info_ts) > INFO_CACHE_TTL:
        _cached_info = mt5.symbol_info(SYMBOL)
        _cached_info_ts = now
    return _cached_info


def get_tick_cached():
    now = time.time()
    if _tick_cache["tick"] is None or (now - _tick_cache["ts"]) > TICK_CACHE_TTL:
        _tick_cache["tick"] = mt5.symbol_info_tick(SYMBOL)
        _tick_cache["ts"]   = now
    return _tick_cache["tick"]


def invalidate_state():
    _state["valid"] = False


def _refresh_state():
    ps  = mt5.positions_get(symbol=SYMBOL) or []
    os_ = mt5.orders_get(symbol=SYMBOL)    or []
    _state["positions"] = [p for p in ps  if p.magic == MAGIC]
    _state["orders"]    = [o for o in os_ if o.magic == MAGIC]
    _state["valid"]     = True


def our_positions():
    if not _state["valid"]:
        _refresh_state()
    return _state["positions"]


def our_pendings():
    if not _state["valid"]:
        _refresh_state()
    return _state["orders"]


_tg_queue    = queue.Queue(maxsize=2000)
_tg_started  = False
_tg_lock     = threading.Lock()


def _send_telegram_now(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_IDS:
        print("[TG-disabled]", msg, flush=True)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    proxies = PROXY if USE_PROXY else None
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "text": msg},
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
                timeout=TELEGRAM_TIMEOUT,
                proxies=proxies,
            )
            if r.status_code != 200:
                print(f"Telegram HTTP error for {chat_id}: {r.status_code}", flush=True)
        except Exception as e:
            print(f"Telegram error for {chat_id}: {e}", flush=True)
        time.sleep(0.03)


def _telegram_worker():
    while True:
        msg = _tg_queue.get()
        if msg is None:
            break
        try:
            _send_telegram_now(msg)
        except Exception as e:
            print("telegram worker err:", e, flush=True)


def send_telegram(msg: str):
    global _tg_started
    if not _tg_started:
        with _tg_lock:
            if not _tg_started:
                t = threading.Thread(target=_telegram_worker, daemon=True)
                t.start()
                _tg_started = True
    try:
        _tg_queue.put_nowait(msg)
    except queue.Full:
        print("[TG] queue full — dropping message", flush=True)


def initialize_mt5():
    if mt5 is None:
        raise RuntimeError(
            f"ماژول MetaTrader5 لود نشد.\nخطای اصلی: {_MT5_IMPORT_ERROR}\n"
            "لطفاً کتابخانه MetaTrader5 را نصب کنید و ترمینال MT5 را یک‌بار اجرا کنید."
        )
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
    if not mt5.symbol_select(SYMBOL, True):
        raise RuntimeError(f"Cannot select symbol {SYMBOL}")
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        raise RuntimeError(f"symbol_info({SYMBOL}) returned None")
    term = mt5.terminal_info()
    if term is not None and not term.trade_allowed:
        raise RuntimeError("AutoTrading در MT5 خاموش است (trade_allowed=False)")
    tf_name = TIMEFRAME_NAME_MAP.get(TIMEFRAME, str(TIMEFRAME))
    print(f"[MT5] {SYMBOL} @ {tf_name}: digits={info.digits}, point={info.point}, "
          f"stops_level={info.trade_stops_level}, spread={info.spread}, "
          f"filling_mode={info.filling_mode}", flush=True)
    return info


def get_filling_mode(info):
    if info.filling_mode & SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    if info.filling_mode & SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def compute_adx_from_rates(rates, period=14):
    if rates is None or len(rates) < period + 2:
        return None, None, None
    h = rates['high']; l = rates['low']; c = rates['close']
    tr, pdm, mdm = [], [], []
    for i in range(1, len(rates)):
        up  = h[i] - h[i-1]
        dn  = l[i-1] - l[i]
        tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
    if len(tr) < period:
        return None, None, None
    atr     = sum(tr[:period])  / period
    plus_s  = sum(pdm[:period]) / period
    minus_s = sum(mdm[:period]) / period
    dxs = []
    last_pdi = 0.0
    last_mdi = 0.0
    for i in range(period, len(tr)):
        atr     = (atr     * (period-1) + tr[i])  / period
        plus_s  = (plus_s  * (period-1) + pdm[i]) / period
        minus_s = (minus_s * (period-1) + mdm[i]) / period
        if atr == 0:
            continue
        pdi = 100 * plus_s  / atr
        mdi = 100 * minus_s / atr
        last_pdi, last_mdi = pdi, mdi
        s = pdi + mdi
        dxs.append(0 if s == 0 else 100 * abs(pdi - mdi) / s)
    if len(dxs) < period:
        return None, None, None
    adx = sum(dxs[:period]) / period
    for i in range(period, len(dxs)):
        adx = (adx * (period-1) + dxs[i]) / period
    return adx, last_pdi, last_mdi


def compute_atr_from_rates(rates, period=14):
    if rates is None or len(rates) < period + 2:
        return None
    h = rates['high']; l = rates['low']; c = rates['close']
    trs = []
    for i in range(1, len(rates)):
        trs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return atr


def check_candle_closes_from_rates(rates, direction, count=3):
    try:
        if rates is None or len(rates) < count + 2:
            return False
        closed = rates[:-1]
        if len(closed) < count + 1:
            return False
        segment = closed[-(count + 1):]
        for i in range(1, len(segment)):
            prev_open  = segment[i - 1]['open']
            curr_close = segment[i]['close']
            if direction == 'up':
                if curr_close <= prev_open:
                    return False
            else:
                if curr_close >= prev_open:
                    return False
        return True
    except Exception as e:
        print("check_candle_closes error:", e, flush=True)
        return False


def fetch_rates_for_cycle():
    bars_needed = max(ADX_PERIOD, ATR_PERIOD) * 4 + 20
    return mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, bars_needed)


def positions_stats():
    pos = our_positions()
    profit = sum(p.profit + p.swap for p in pos)
    return len(pos), profit


def daily_realized_pnl():
    now = datetime.now(pytz.timezone("Asia/Tehran"))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, now) or []
    total = 0.0
    for d in deals:
        if d.magic == MAGIC and d.symbol == SYMBOL:
            total += d.profit + d.swap + d.commission
    return total


def daily_total_pnl_cached():
    now = time.time()
    if (now - _daily_pnl_cache["ts"]) > DAILY_PNL_CACHE_TTL:
        _daily_pnl_cache["value"] = daily_realized_pnl() + positions_stats()[1]
        _daily_pnl_cache["ts"]    = now
    return _daily_pnl_cache["value"]


def invalidate_daily_pnl():
    _daily_pnl_cache["ts"] = 0.0


def daily_loss_summary():
    now = datetime.now(pytz.timezone("Asia/Tehran"))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, now) or []
    pos_deals = {}
    for d in deals:
        if d.magic == MAGIC and d.symbol == SYMBOL and d.position_id:
            pos_deals.setdefault(d.position_id, []).append(d)
    loss_count = 0; loss_total = 0.0
    win_count  = 0; win_total  = 0.0
    for pid, ds in pos_deals.items():
        closing = next((d for d in ds if d.entry == mt5.DEAL_ENTRY_OUT), None)
        if closing is None:
            continue
        comm = sum(d.commission for d in ds)
        swap = sum(d.swap      for d in ds)
        net  = closing.profit + swap + comm
        if net < 0:
            loss_count += 1; loss_total += net
        else:
            win_count  += 1; win_total  += net
    return {"loss_count": loss_count, "loss_total": loss_total,
            "win_count":  win_count,  "win_total":  win_total}


def delete_all_pendings():
    for o in our_pendings():
        req = {"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}
        r = mt5.order_send(req)
        if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
            print("remove pending failed", o.ticket, r, flush=True)
    invalidate_state()


def close_all_positions():
    for p in our_positions():
        tick = get_tick_cached()
        if tick is None:
            continue
        if p.type == mt5.POSITION_TYPE_BUY:
            price, otype = tick.bid, mt5.ORDER_TYPE_SELL
        else:
            price, otype = tick.ask, mt5.ORDER_TYPE_BUY
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket, "symbol": SYMBOL, "volume": p.volume,
            "type": otype, "price": price, "deviation": DEVIATION,
            "magic": MAGIC, "comment": "close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        r = mt5.order_send(req)
        if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
            print("close failed", p.ticket, r, flush=True)
    invalidate_state()
    invalidate_daily_pnl()


def close_positions_list(positions_to_close):
    closed = 0
    for p in positions_to_close:
        tick = get_tick_cached()
        if tick is None:
            continue
        if p.type == mt5.POSITION_TYPE_BUY:
            price, otype = tick.bid, mt5.ORDER_TYPE_SELL
        else:
            price, otype = tick.ask, mt5.ORDER_TYPE_BUY
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket, "symbol": SYMBOL, "volume": p.volume,
            "type": otype, "price": price, "deviation": DEVIATION,
            "magic": MAGIC, "comment": "close_profit",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        r = mt5.order_send(req)
        if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
            print("close (profit list) failed", p.ticket, r, flush=True)
        else:
            closed += 1
    if closed:
        invalidate_state()
        invalidate_daily_pnl()
    return closed


def close_positions_hitting_loss_limit():
    positions = our_positions()
    to_close = [p for p in positions if (p.profit + p.swap) <= -MAX_POSITION_LOSS_USD]
    if not to_close:
        return 0
    details = "\n".join(
        f"  • #{p.ticket} | "
        f"{'BUY 🟢' if p.type == mt5.POSITION_TYPE_BUY else 'SELL 🔴'} | "
        f"{p.volume} lot | {p.profit + p.swap:.2f}$"
        for p in to_close
    )
    send_telegram(
        f"🛑 بستن پوزیشن به دلیل رسیدن به حد ضرر شناور ({MAX_POSITION_LOSS_USD:.2f}$)\n"
        f"تعداد پوزیشن: {len(to_close)}\n📋 جزئیات:\n{details}"
    )
    closed = close_positions_list(to_close)
    print(f"[CLOSE-LOSS] {closed} losing position(s) closed (limit={MAX_POSITION_LOSS_USD}$).", flush=True)
    return closed


known_positions = {}


def check_sl_breakout_and_cancel():
    global known_positions
    info = get_symbol_info_cached()
    tick = get_tick_cached()
    if info is None or tick is None:
        return False
    point = info.point
    current = our_positions()
    current_tickets = {p.ticket for p in current}

    for p in current:
        known_positions[p.ticket] = {"sl": p.sl, "type": p.type}

    disappeared = [t for t in list(known_positions.keys()) if t not in current_tickets]
    if not disappeared:
        return False

    now = datetime.now(pytz.timezone("Asia/Tehran"))
    deals = mt5.history_deals_get(now - timedelta(hours=6), now + timedelta(minutes=1)) or []

    reason_map = {
        mt5.DEAL_REASON_SL:      "🛑 حد ضرر (SL)",
        mt5.DEAL_REASON_TP:      "🎯 حد سود (TP)",
        mt5.DEAL_REASON_SO:      "📞 Stop Out",
        mt5.DEAL_REASON_CLIENT:  "👤 بستن دستی (ترمینال)",
        mt5.DEAL_REASON_MOBILE:  "📱 بستن از موبایل",
        mt5.DEAL_REASON_WEB:     "🌐 بستن از وب",
        mt5.DEAL_REASON_EXPERT:  "🤖 بستن توسط ربات/اکسپرت",
    }

    cancelled = False
    for ticket in disappeared:
        rec = known_positions.pop(ticket, None)
        if rec is None:
            continue
        sl_price = rec["sl"]
        ptype    = rec["type"]

        closing_deal = next(
            (d for d in deals if d.position_id == ticket and d.entry == mt5.DEAL_ENTRY_OUT), None)
        if closing_deal is None:
            continue
        open_deal = next(
            (d for d in deals if d.position_id == ticket and d.entry == mt5.DEAL_ENTRY_IN), None)

        total_commission = sum(d.commission for d in deals if d.position_id == ticket)
        total_swap       = sum(d.swap       for d in deals if d.position_id == ticket)
        net_profit       = closing_deal.profit + total_swap + total_commission

        reason_code = getattr(closing_deal, "reason", None)
        reason_fa   = reason_map.get(reason_code, f"نامشخص ({reason_code})")
        if reason_code == mt5.DEAL_REASON_EXPERT:
            cmt = (closing_deal.comment or "").lower()
            if "close_profit" in cmt:
                reason_fa = "📈 سیو سود پله‌ای (ربات)"
            elif "close" in cmt:
                reason_fa = "🤖 بستن توسط ربات (روزانه / خارج ساعت)"

        direction_fa = "BUY 🟢" if ptype == mt5.POSITION_TYPE_BUY else "SELL 🔴"
        open_price   = open_deal.price if open_deal else 0.0
        close_price  = closing_deal.price
        volume       = closing_deal.volume
        try:
            open_time = (datetime.fromtimestamp(open_deal.time, pytz.timezone("Asia/Tehran"))
                         .strftime("%Y-%m-%d %H:%M:%S") if open_deal else "—")
        except Exception:
            open_time = "—"
        try:
            close_time = (datetime.fromtimestamp(closing_deal.time, pytz.timezone("Asia/Tehran"))
                          .strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            close_time = "—"

        if net_profit > 0:
            send_telegram(
                "✅ پوزیشن سودده بسته شد\n"
                f"🧾 تیکت: {ticket}\n"
                f"📊 جهت: {direction_fa}  |  📦 حجم: {volume}\n"
                f"🔓 ورود : {open_price:.2f}  |  🕐 {open_time}\n"
                f"🔒 خروج : {close_price:.2f}  |  🕐 {close_time}\n"
                f"📈 دلیل بسته شدن: {reason_fa}\n"
                f"────────────────────\n"
                f"💵 سود خام : +{closing_deal.profit:.2f}$\n"
                f"🔄 سوآپ    : {total_swap:.2f}$\n"
                f"💸 کمیسیون : {total_commission:.2f}$\n"
                f"🧮 سود خالص: +{net_profit:.2f}$"
            )
        elif net_profit < 0:
            send_telegram(
                "❌ پوزیشن با ضرر بسته شد\n"
                f"🧾 تیکت: {ticket}\n"
                f"📊 جهت: {direction_fa}  |  📦 حجم: {volume}\n"
                f"🔓 ورود : {open_price:.2f}  |  🕐 {open_time}\n"
                f"🔒 خروج : {close_price:.2f}  |  🕐 {close_time}\n"
                f"📉 دلیل بسته شدن: {reason_fa}\n"
                f"────────────────────\n"
                f"💵 زیان خام : {closing_deal.profit:.2f}$\n"
                f"🔄 سوآپ     : {total_swap:.2f}$\n"
                f"💸 کمیسیون  : {total_commission:.2f}$\n"
                f"🧮 زیان خالص: {net_profit:.2f}$"
            )

        if not sl_price or sl_price == 0.0:
            continue
        if reason_code != mt5.DEAL_REASON_SL:
            continue

        if ptype == mt5.POSITION_TYPE_BUY:
            distance_pts = (sl_price - tick.bid) / point
        else:
            distance_pts = (tick.ask - sl_price) / point

        if distance_pts >= SL_BREAKOUT_PTS:
            pendings = our_pendings()
            send_telegram(
                "🚫 قیمت از حد ضرر رد شد\n"
                f"🧾 تیکت پوزیشن: {ticket}\n"
                f"📉 SL: {sl_price}\n"
                f"💱 قیمت لحظه‌ای — Bid: {tick.bid} | Ask: {tick.ask}\n"
                f"📏 فاصله از SL: {distance_pts:.0f} پوینت (≥ {SL_BREAKOUT_PTS})\n"
                f"🗑 لغو {len(pendings)} سفارش Pending فعال‌نشده"
            )
            delete_all_pendings()
            cancelled = True

    invalidate_daily_pnl()
    return cancelled


def place_pending_grid(mode="both", atr=None):
    tick = get_tick_cached()
    info = get_symbol_info_cached()
    if tick is None or info is None:
        print("place_pending_grid: tick/info None", flush=True)
        return 0

    point  = info.point
    digits = info.digits
    stops  = info.trade_stops_level * point
    base   = max(FIRST_DISTANCE_PTS * point, stops + 10 * point)
    step   = max(STEP_PTS * point, stops + 5 * point)

    if atr is not None and atr > 0:
        sl_distance = atr * ATR_SL_MULTIPLIER
        print(f"[ATR-SL] ATR={atr:.4f} → SL dist={sl_distance:.3f} "
              f"({sl_distance / point:.0f} pts)", flush=True)
    else:
        sl_distance = SL_PTS * point
        print(f"[ATR-SL] ATR نامعتبر → SL ثابت {SL_PTS} pts", flush=True)

    broker_min = (info.trade_stops_level + 10) * point
    min_sl     = max(broker_min, SL_MIN_PTS * point)
    if sl_distance < min_sl:
        sl_distance = min_sl

    filling = get_filling_mode(info)
    placed  = 0

    def _send(req, tag, price):
        nonlocal placed
        r = mt5.order_send(req)
        if r is None:
            print(f"{tag} order_send=None | last_error={mt5.last_error()}", flush=True)
        elif r.retcode == mt5.TRADE_RETCODE_DONE:
            placed += 1
            print(f"{tag} OK ticket={r.order} price={price}", flush=True)
        else:
            print(f"{tag} FAIL retcode={r.retcode} comment={r.comment}", flush=True)

    if mode == "buy_only":
        for i in range(ORDERS_PER_SIDE):
            d = base + i * step
            bp = tick.ask + d
            _send({
                "action": mt5.TRADE_ACTION_PENDING, "symbol": SYMBOL,
                "volume": LOT_SIZE, "type": mt5.ORDER_TYPE_BUY_STOP,
                "price": round(bp, digits), "sl": round(bp - sl_distance, digits),
                "magic": MAGIC, "comment": f"BS_{i}",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
            }, f"BuyStop[{i}]", bp)
        for i in range(ORDERS_PER_SIDE):
            d = base + i * step
            bp = tick.ask - d
            _send({
                "action": mt5.TRADE_ACTION_PENDING, "symbol": SYMBOL,
                "volume": LOT_SIZE, "type": mt5.ORDER_TYPE_BUY_LIMIT,
                "price": round(bp, digits), "sl": round(bp - sl_distance, digits),
                "magic": MAGIC, "comment": f"BL_{i}",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
            }, f"BuyLimit[{i}]", bp)
        invalidate_state()
        return placed

    if mode == "sell_only":
        for i in range(ORDERS_PER_SIDE):
            d = base + i * step
            sp = tick.bid - d
            _send({
                "action": mt5.TRADE_ACTION_PENDING, "symbol": SYMBOL,
                "volume": LOT_SIZE, "type": mt5.ORDER_TYPE_SELL_STOP,
                "price": round(sp, digits), "sl": round(sp + sl_distance, digits),
                "magic": MAGIC, "comment": f"SS_{i}",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
            }, f"SellStop[{i}]", sp)
        for i in range(ORDERS_PER_SIDE):
            d = base + i * step
            sp = tick.bid + d
            _send({
                "action": mt5.TRADE_ACTION_PENDING, "symbol": SYMBOL,
                "volume": LOT_SIZE, "type": mt5.ORDER_TYPE_SELL_LIMIT,
                "price": round(sp, digits), "sl": round(sp + sl_distance, digits),
                "magic": MAGIC, "comment": f"SL_{i}",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
            }, f"SellLimit[{i}]", sp)
        invalidate_state()
        return placed

    for i in range(ORDERS_PER_SIDE):
        d = base + i * step
        bp = tick.ask + d
        _send({
            "action": mt5.TRADE_ACTION_PENDING, "symbol": SYMBOL,
            "volume": LOT_SIZE, "type": mt5.ORDER_TYPE_BUY_STOP,
            "price": round(bp, digits), "sl": round(bp - sl_distance, digits),
            "magic": MAGIC, "comment": f"BS_{i}",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
        }, f"BuyStop[{i}]", bp)
        sp = tick.bid - d
        _send({
            "action": mt5.TRADE_ACTION_PENDING, "symbol": SYMBOL,
            "volume": LOT_SIZE, "type": mt5.ORDER_TYPE_SELL_STOP,
            "price": round(sp, digits), "sl": round(sp + sl_distance, digits),
            "magic": MAGIC, "comment": f"SS_{i}",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
        }, f"SellStop[{i}]", sp)
    invalidate_state()
    return placed


def in_trading_hours(now_local):
    t = now_local.time()
    s = dt_time(START_HOUR, START_MIN)
    e = dt_time(END_HOUR,   END_MIN)
    if s <= e:
        return s <= t <= e
    return t >= s or t <= e


def main():
    global known_positions
    _dbg("main: start")
    initialize_mt5()
    _dbg("main: MT5 initialized")

    tz = pytz.timezone("Asia/Tehran")
    proxy_state = "روشن" if USE_PROXY else "خاموش"
    normal_trend_state = "فعال" if TRADE_NORMAL_TREND else "غیرفعال"
    tf_name = TIMEFRAME_NAME_MAP.get(TIMEFRAME, str(TIMEFRAME))

    acc = mt5.account_info()
    broker_name = (acc.company or acc.server or "نامشخص") if acc else "نامشخص"
    balance = acc.balance if acc else 0.0
    currency = (acc.currency or "") if acc else ""

    daily_pnl = daily_realized_pnl()

    license_note = ("لایسنس دائمی" if _LICENSE_ACTIVE
                    else f"نسخه آزمایشی — {_TRIAL_DAYS_LEFT} روز باقی‌مانده")

    send_telegram(
        "🤖 ربات معامله‌گر آویژه(نسخه 1 - سریع) شروع به کار کرد\n"
        f"🌹 با صلوات بر محمد و آل محمد\n"
        f"❤️ طراحی و توسعه : مهدی زارع\n"
        f"✉️ Mehdizare@outlook.com\n"
        f"📊 نماد مورد معامله: {SYMBOL}\n"
        f"⏱️ تایم فریم: {tf_name}\n"
        f"🏦 نام بروکر: {broker_name}\n"
        f"💰 موجودی حساب: {balance:.2f} {currency}\n"
        f"📈 سود/زیان روزانه: {daily_pnl:.2f} {currency}\n"
        f"🎯 هدف سود روزانه: {DAILY_PROFIT_TARGET_USD:.2f} {currency}\n"
        f"🛑 حد ضرر هر پوزیشن: {MAX_POSITION_LOSS_USD:.2f} {currency}\n"
        f"🧰 حجم: {LOT_SIZE} لات \n"
        f"⚙️ اهرم: 1:{LEVERAGE}\n"
        f"📐 فواصل مؤثر — FirstDist={FIRST_DISTANCE_PTS}pts | Step={STEP_PTS}pts | "
        f"SL={SL_PTS}pts | SLmin={SL_MIN_PTS}pts | SLBreak={SL_BREAKOUT_PTS}pts\n"
        f"🕝 ساعت معاملات: {END_HOUR:02d}:{END_MIN:02d}-"
        f"{START_HOUR:02d}:{START_MIN:02d}\n"
        f"💻 وضعیت پروکسی : {proxy_state}\n"
        f"⚖️ معامله در روند معمولی : {normal_trend_state}\n"
        f"📜 وضعیت: {license_note}"
    )

    last_day = datetime.now(tz).date()
    daily_stop = False
    daily_target_hit = False
    cooldown_until = datetime.now(tz)
    max_pos_warned = False
    known_positions = {}
    prev_num_pos = 0
    peak_profit          = 0.0
    secured_profit_level = 0.0

    while not STOP_EVENT.is_set():
        try:
            now = datetime.now(tz)

            if now.date() != last_day:
                last_day = now.date()
                daily_stop = False
                daily_target_hit = False
                max_pos_warned = False
                peak_profit = 0.0
                secured_profit_level = 0.0
                invalidate_daily_pnl()
                send_telegram(f"📅 روز جدید {last_day} — ریست محافظ روزانه")

            dt_pnl = daily_total_pnl_cached()

            if dt_pnl >= DAILY_PROFIT_TARGET_USD:
                if not daily_target_hit:
                    s = daily_loss_summary()
                    send_telegram(
                        f"🎯 هدف سود روزانه محقق شد\n"
                        f"P&L امروز: {dt_pnl:.2f}$\n"
                        f"✅ سودها: {s['win_count']} معامله | {s['win_total']:.2f}$\n"
                        f"❌ ضررها: {s['loss_count']} معامله | {s['loss_total']:.2f}$\n"
                        f"ربات تا فردا غیرفعال می‌شود."
                    )
                    daily_target_hit = True
                delete_all_pendings()
                close_all_positions()
                interruptible_sleep(30)
                continue

            if daily_target_hit:
                interruptible_sleep(15)
                continue

            if dt_pnl <= -DAILY_MAX_LOSS_USD:
                if not daily_stop:
                    s = daily_loss_summary()
                    send_telegram(
                        f"🚨 حد ضرر روزانه فعال شد\n"
                        f"P&L امروز: {dt_pnl:.2f}$\n"
                        f"❌ ضررها: {s['loss_count']} معامله | {s['loss_total']:.2f}$\n"
                        f"ربات تا فردا متوقف می‌شود."
                    )
                    daily_stop = True
                delete_all_pendings()
                close_all_positions()
                interruptible_sleep(30)
                continue

            if daily_stop:
                interruptible_sleep(15)
                continue

            if not in_trading_hours(now):
                if our_pendings() or our_positions():
                    delete_all_pendings()
                    close_all_positions()
                interruptible_sleep(5)
                continue

            invalidate_state()
            num_pos, total_profit = positions_stats()

            if prev_num_pos > 0 and num_pos == 0:
                pendings = our_pendings()
                if pendings:
                    send_telegram(
                        f"🧹 تمام سفارشات غیرفعال بسته شدند\n"
                        f"🗑 لغو {len(pendings)} سفارش Pending فعال‌نشده"
                    )
                    delete_all_pendings()
                peak_profit = 0.0
                secured_profit_level = 0.0
            prev_num_pos = num_pos

            if num_pos >= MAX_OPEN_POSITIONS:
                if not max_pos_warned:
                    send_telegram(
                        f"⚠️ به حداکثر پوزیشن باز رسید ({num_pos}/{MAX_OPEN_POSITIONS})\n"
                        f"سفارش جدید ثبت نمی‌شود.\n"
                        f"سود شناور فعلی: {total_profit:.2f}$\n"
                        f"پوزیشن‌ها باز می‌مانند تا شرایط بستن (سوددهی) فراهم شود."
                    )
                    max_pos_warned = True
                if our_pendings():
                    delete_all_pendings()
            else:
                max_pos_warned = False

            positions  = our_positions()
            profitable = [p for p in positions if (p.profit + p.swap) > 0]

            if profitable:
                profitable_sum = sum(p.profit + p.swap for p in profitable)
                if profitable_sum > peak_profit:
                    peak_profit = profitable_sum
                    new_level = int(peak_profit / PROFIT_STEP_USD) * PROFIT_STEP_USD
                    if new_level > secured_profit_level and new_level > 0:
                        secured_profit_level = new_level
                        send_telegram(
                            f"📈 پله سود قفل شد\n"
                            f"سود جاری: {profitable_sum:.2f}$\n"
                            f"سطح قفل‌شده: {secured_profit_level:.2f}$"
                        )
                if (secured_profit_level >= PROFIT_STEP_USD and
                        profitable_sum <= secured_profit_level - PROFIT_TRAIL_GAP_USD):
                    details = "\n".join(
                        f"  • #{p.ticket} | "
                        f"{'BUY 🟢' if p.type == mt5.POSITION_TYPE_BUY else 'SELL 🔴'} | "
                        f"{p.volume} lot | +{p.profit + p.swap:.2f}$"
                        for p in profitable
                    )
                    send_telegram(
                        f"✅ سیو سود پله‌ای انجام شد\n"
                        f"سطح قفل‌شده: {secured_profit_level:.2f}$\n"
                        f"سود فعلی: {profitable_sum:.2f}$\n"
                        f"تعداد پوزیشن سودده: {len(profitable)}\n"
                        f"📋 جزئیات:\n{details}\n"
                        f"سود شناور کل: {total_profit:.2f}$\n"
                        f"🔒 معاملات ضررده باز می‌مانند."
                    )
                    closed = close_positions_list(profitable)
                    print(f"[CLOSE-STEP] {closed} profitable position(s) closed.", flush=True)
                    peak_profit = 0.0
                    secured_profit_level = 0.0
                    interruptible_sleep(1)
                    continue

            if close_positions_hitting_loss_limit():
                peak_profit = 0.0
                secured_profit_level = 0.0
                interruptible_sleep(0.5)
                continue

            if check_sl_breakout_and_cancel():
                cooldown_until = now + timedelta(seconds=SL_BREAKOUT_COOLDOWN_SEC)
                interruptible_sleep(1)
                continue

            num_pos, _ = positions_stats()
            pendings_count = len(our_pendings())
            if num_pos == 0 and pendings_count < MAX_PENDING and num_pos < MAX_OPEN_POSITIONS:
                if now >= cooldown_until:
                    rates = fetch_rates_for_cycle()
                    adx, pdi, mdi = compute_adx_from_rates(rates, ADX_PERIOD)
                    atr            = compute_atr_from_rates(rates, ATR_PERIOD)

                    print(f"[LOOP] TF={tf_name} | ADX={adx} | "
                          f"+DI={pdi if pdi is not None else 0:.1f} "
                          f"| -DI={mdi if mdi is not None else 0:.1f} | "
                          f"positions={num_pos} | pendings={pendings_count} | "
                          f"target_pendings={MAX_PENDING}", flush=True)

                    if adx is not None and adx >= ADX_THRESHOLD:
                        if adx >= ADX_STRONG_THRESHOLD and pdi > mdi:
                            if not check_candle_closes_from_rates(
                                    rates, 'up', CANDLE_CLOSE_CHECK_COUNT):
                                print(f"[LOOP] ADX={adx:.1f} strong UP but candle condition failed.", flush=True)
                                cooldown_until = now + timedelta(seconds=5)
                                interruptible_sleep(0.5)
                                continue
                            mode = "buy_only"
                            mode_fa = ("🟢 روند صعودی بسیار قوی + تأیید کندل‌ها → "
                                       f"{ORDERS_PER_SIDE} Buy Stop بالا + "
                                       f"{ORDERS_PER_SIDE} Buy Limit پایین")
                        elif adx >= ADX_STRONG_THRESHOLD and mdi > pdi:
                            if not check_candle_closes_from_rates(
                                    rates, 'down', CANDLE_CLOSE_CHECK_COUNT):
                                print(f"[LOOP] ADX={adx:.1f} strong DOWN but candle condition failed.", flush=True)
                                cooldown_until = now + timedelta(seconds=5)
                                interruptible_sleep(0.5)
                                continue
                            mode = "sell_only"
                            mode_fa = ("🔴 روند نزولی بسیار قوی + تأیید کندل‌ها → "
                                       f"{ORDERS_PER_SIDE} Sell Stop پایین + "
                                       f"{ORDERS_PER_SIDE} Sell Limit بالا")
                        else:
                            if not TRADE_NORMAL_TREND:
                                print(f"[LOOP] Normal trend (ADX={adx:.1f}) disabled.", flush=True)
                                cooldown_until = now + timedelta(seconds=5)
                                interruptible_sleep(0.5)
                                continue
                            mode = "both"
                            mode_fa = "⚖️ روند معمولی → دوطرفه"

                        placed = place_pending_grid(mode, atr=atr)
                        if placed:
                            tick = get_tick_cached()
                            send_telegram(
                                f"📤 {placed} سفارش Pending ثبت شد\n"
                                f"{mode_fa}\n"
                                f"⏱️ تایم فریم: {tf_name}\n"
                                f"ADX={adx:.1f} | +DI={pdi:.1f} | -DI={mdi:.1f}\n"
                                f"قیمت={tick.bid if tick else 0:.2f}"
                            )
                            cooldown_until = now + timedelta(seconds=30)
                        else:
                            print("[LOOP] place_pending_grid() = 0", flush=True)
                            cooldown_until = now + timedelta(seconds=10)
                    else:
                        cooldown_until = now + timedelta(seconds=5)

            interruptible_sleep(MAIN_LOOP_SLEEP)

        except Exception as e:
            send_telegram(f"⚠️ خطا:\n{e}\n{traceback.format_exc()[:500]}")
            print("MAIN LOOP ERROR:", e, flush=True)
            print(traceback.format_exc(), flush=True)
            interruptible_sleep(5)

    try:
        print("[BOT] در حال پاکسازی سفارش‌ها...", flush=True)
        delete_all_pendings()
        close_all_positions()
    except Exception:
        pass
    print("[BOT] متوقف شد.", flush=True)


# ==================== GUI ====================
class QueueWriter(io.TextIOBase):
    def __init__(self, q):
        self.q = q
    def write(self, s):
        if s:
            self.q.put(fa(s))
        return len(s)
    def flush(self):
        pass


def _safe_entry(parent, textvariable, width=24):
    e = ttk.Entry(parent, textvariable=textvariable, width=width)
    try:
        e.configure(justify="right")
    except tk.TclError:
        pass
    return e


def _safe_combobox(parent, textvariable, values, width=22):
    cb = ttk.Combobox(parent, textvariable=textvariable, values=values,
                      width=width, state="readonly")
    try:
        cb.configure(justify="right")
    except tk.TclError:
        pass
    return cb


def _safe_scrolled_text(parent, **kw):
    kw.pop("justify", None)
    st = scrolledtext.ScrolledText(parent, **kw)
    try:
        st.configure(justify="right")
    except tk.TclError:
        pass
    return st


class ConfigWindow:
    def __init__(self, root):
        self.root = root

        if _LICENSE_ACTIVE:
            self.root.title("AvijehBot — تنظیمات و اجرا (لایسنس دائمی)")
        elif _TRIAL_DAYS_LEFT > 0:
            self.root.title("AvijehBot — تنظیمات و اجرا (نسخه آزمایشی)")
        else:
            self.root.title("AvijehBot — تنظیمات و اجرا")

        self.root.geometry("820x820")
        self.root.minsize(760, 700)

        self.cfg = load_config_file()
        self.vars = {}
        self.bot_thread = None
        self.log_queue = queue.Queue()
        self.banner_frame = None

        self.lev_label_1_var = tk.StringVar(value="")
        self.lev_value_1_var = tk.StringVar(value="")
        self.lev_label_2_var = tk.StringVar(value="")
        self.lev_value_2_var = tk.StringVar(value="")

        try:
            self._prev_leverage = int(float(self.cfg.get("LEVERAGE", 100)))
        except Exception:
            self._prev_leverage = 100

        try:
            self._build_ui()
        except Exception:
            tb = traceback.format_exc()
            print("BUILD_UI ERROR:\n", tb, flush=True)
            _dbg(f"BUILD_UI ERROR:\n{tb}")
            try:
                messagebox.showerror("خطا در ساخت رابط کاربری", tb[:2500])
            except Exception:
                pass
            raise

        self._refresh_leverage_info()
        self._poll_log()

    def _add_row(self, parent, key, label, row, width=24):
        v = tk.StringVar(value=str(self.cfg.get(key, "")))
        e = _safe_entry(parent, v, width=width)
        e.grid(row=row, column=0, sticky="we", padx=8, pady=4)
        ttk.Label(parent, text=fa(label), anchor="e").grid(
            row=row, column=1, sticky="e", padx=8, pady=4)
        self.vars[key] = v
        return e

    def _add_check(self, parent, key, label, row):
        v = tk.BooleanVar(value=bool(self.cfg.get(key, False)))
        cb = ttk.Checkbutton(parent, text=fa(label), variable=v)
        cb.grid(row=row, column=1, sticky="e", padx=8, pady=4)
        self.vars[key] = v

    def _add_combo(self, parent, key, label, values, row):
        v = tk.StringVar(value=str(self.cfg.get(key, values[0])))
        cb = _safe_combobox(parent, v, values, width=22)
        cb.grid(row=row, column=0, sticky="we", padx=8, pady=4)
        ttk.Label(parent, text=fa(label), anchor="e").grid(
            row=row, column=1, sticky="e", padx=8, pady=4)
        self.vars[key] = v

    def _build_ui(self):
        if not _LICENSE_ACTIVE and _TRIAL_DAYS_LEFT > 0:
            self.banner_frame = tk.Frame(self.root, bg="#fff3cd")
            self.banner_frame.pack(fill="x", padx=10, pady=(6, 0))

            tk.Label(
                self.banner_frame,
                text=fa("نسخه آزمایشی"),
                bg="#fff3cd", fg="#856404",
                font=("Tahoma", 11, "bold"),
                anchor="center", justify="center",
            ).pack(pady=(6, 0))

            row = tk.Frame(self.banner_frame, bg="#fff3cd")
            row.pack(pady=(0, 6))

            tk.Label(
                row,
                text=to_fa_num(_TRIAL_DAYS_LEFT),
                bg="#fff3cd", fg="#856404",
                font=("Tahoma", 12, "bold"),
            ).pack(side="right", padx=(0, 6))

            tk.Label(
                row,
                text=fa("روز باقی‌مانده"),
                bg="#fff3cd", fg="#856404",
                font=("Tahoma", 11, "bold"),
            ).pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        t1 = ttk.Frame(nb); nb.add(t1, text=fa("عمومی"))
        t1.grid_columnconfigure(0, weight=1)
        self._add_row(t1, "SYMBOL", "نماد:", 0)
        self._add_row(t1, "LOT_SIZE", "حجم (لات):", 1)
        self._add_combo(t1, "TIMEFRAME_STR", "تایم‌فریم:", ["M1", "M5", "M15"], 2)
        self._add_row(t1, "MAGIC", "Magic Number:", 3)
        self._add_row(t1, "DEVIATION", "Deviation:", 4)
        self._add_row(t1, "CANDLE_CLOSE_CHECK_COUNT", "تعداد کندل تأیید:", 5)
        self._add_check(t1, "TRADE_NORMAL_TREND",
                        "معامله در روند معمولی (ADX بین آستانه و قوی)", 6)

        t2 = ttk.Frame(nb); nb.add(t2, text=fa("اندیکاتورها"))
        t2.grid_columnconfigure(0, weight=1)
        self._add_row(t2, "ADX_PERIOD", "دوره ADX:", 0)
        self._add_row(t2, "ADX_THRESHOLD", "آستانه ADX:", 1)
        self._add_row(t2, "ADX_STRONG_THRESHOLD", "آستانه ADX قوی:", 2)
        self._add_row(t2, "ATR_PERIOD", "دوره ATR:", 3)
        self._add_row(t2, "ATR_SL_MULTIPLIER", "ضریب ATR برای SL:", 4)

        t3 = ttk.Frame(nb); nb.add(t3, text=fa("سفارشات"))
        t3.grid_columnconfigure(0, weight=1)

        lev_entry = self._add_row(t3, "LEVERAGE", "اهرم:", 0)
        lev_entry.bind("<FocusOut>", self._on_leverage_commit)
        lev_entry.bind("<Return>",   self._on_leverage_commit)

        self._add_row(t3, "MAX_PENDING", "حداکثر Pending:", 1)
        self._add_row(t3, "ORDERS_PER_SIDE", "تعداد سفارش هر طرف:", 2)
        self._add_row(t3, "FIRST_DISTANCE_PTS", "فاصله اول (پوینت):", 3)
        self._add_row(t3, "STEP_PTS", "فاصله پله‌ای (پوینت):", 4)
        self._add_row(t3, "SL_PTS", "SL ثابت (پوینت):", 5)
        self._add_row(t3, "SL_MIN_PTS", "حداقل SL (پوینت):", 6)
        self._add_row(t3, "MAX_OPEN_POSITIONS", "حداکثر پوزیشن باز:", 7)

        info_frame = ttk.Frame(t3)
        info_frame.grid(row=8, column=0, columnspan=2, sticky="e", padx=8, pady=(6, 0))
        info_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(info_frame, textvariable=self.lev_value_1_var, foreground="#06c",
                  font=("Tahoma", 9, "bold"), anchor="e").grid(
            row=0, column=0, sticky="e", padx=(0, 6))
        ttk.Label(info_frame, textvariable=self.lev_label_1_var, foreground="#06c",
                  font=("Tahoma", 9, "bold"), anchor="e").grid(
            row=0, column=1, sticky="e")

        ttk.Label(info_frame, textvariable=self.lev_value_2_var, foreground="#06c",
                  font=("Tahoma", 9, "bold"), anchor="e").grid(
            row=1, column=0, sticky="e", padx=(0, 6))
        ttk.Label(info_frame, textvariable=self.lev_label_2_var, foreground="#06c",
                  font=("Tahoma", 9, "bold"), anchor="e").grid(
            row=1, column=1, sticky="e")

        t4 = ttk.Frame(nb); nb.add(t4, text=fa("مدیریت ریسک"))
        t4.grid_columnconfigure(0, weight=1)
        self._add_row(t4, "PROFIT_STEP_USD", "پله سود (USD):", 0)
        self._add_row(t4, "PROFIT_TRAIL_GAP_USD", "فاصله تریل سود (USD):", 1)
        self._add_row(t4, "MAX_POSITION_LOSS_USD", "حد ضرر هر پوزیشن (USD):", 2)
        self._add_row(t4, "DAILY_MAX_LOSS_USD", "حد ضرر روزانه (USD):", 3)
        self._add_row(t4, "DAILY_PROFIT_TARGET_USD", "هدف سود روزانه (USD):", 4)
        self._add_row(t4, "SL_BREAKOUT_PTS", "SL Breakout (پوینت):", 5)
        self._add_row(t4, "SL_BREAKOUT_COOLDOWN_SEC", "کول‌داون SL Breakout (ثانیه):", 6)

        t5 = ttk.Frame(nb); nb.add(t5, text=fa("ساعت معاملات"))
        t5.grid_columnconfigure(0, weight=1)
        self._add_row(t5, "START_HOUR", "ساعت شروع:", 0)
        self._add_row(t5, "START_MIN", "دقیقه شروع:", 1)
        self._add_row(t5, "END_HOUR", "ساعت پایان:", 2)
        self._add_row(t5, "END_MIN", "دقیقه پایان:", 3)

        t6 = ttk.Frame(nb); nb.add(t6, text=fa("تلگرام / پروکسی"))
        t6.grid_columnconfigure(0, weight=1)
        self._add_row(t6, "TELEGRAM_TOKEN", "توکن ربات:", 0, width=60)
        self._add_row(t6, "TELEGRAM_CHAT_IDS", "Chat IDs (با کاما):", 1, width=60)
        self._add_check(t6, "USE_PROXY", "استفاده از پروکسی", 2)
        self._add_row(t6, "PROXY_HTTP", "پروکسی HTTP:", 3, width=60)
        self._add_row(t6, "PROXY_HTTPS", "پروکسی HTTPS:", 4, width=60)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=6)

        self.btn_start = ttk.Button(btn_frame, text=fa("شروع ربات"),
                                    command=self.on_start)
        self.btn_start.pack(side="left", padx=4)

        self.btn_stop = ttk.Button(btn_frame, text=fa("توقف ربات"),
                                   command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        self.btn_license = ttk.Button(
            btn_frame,
            text=fa("فعال‌سازی لایسنس دائمی"),
            command=self.on_activate_license,
        )
        self.btn_license.pack(side="left", padx=4)
        if _LICENSE_ACTIVE:
            self.btn_license.configure(state="disabled", text=fa("لایسنس فعال است"))

        ttk.Button(btn_frame, text=fa("ذخیره تنظیمات"),
                   command=self.on_save).pack(side="right", padx=4)
        ttk.Button(btn_frame, text=fa("بازنشانی پیش‌فرض"),
                   command=self.on_reset).pack(side="right", padx=4)

        self.status_var = tk.StringVar(value=fa("آماده"))
        ttk.Label(self.root, textvariable=self.status_var, foreground="#0a7",
                  anchor="e", justify="right").pack(anchor="e", fill="x", padx=14)

        ttk.Label(self.root, text=fa("لاگ اجرای ربات:"),
                  anchor="e", justify="right").pack(anchor="e", fill="x", padx=14, pady=(6, 0))

        self.log_box = _safe_scrolled_text(
            self.root, height=11, wrap="word", font=("Tahoma", 9)
        )
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_box.configure(state="disabled")

    def _refresh_leverage_info(self):
        try:
            lev = int(float(self.vars["LEVERAGE"].get()))
        except Exception:
            lev = self._prev_leverage
        if lev <= 0:
            lev = 100
        self.lev_label_1_var.set(fa("اهرم فعال:"))
        self.lev_label_2_var.set(fa("ضریب مقیاس مبنا:"))
        self.lev_value_1_var.set(f"1:{lev}")
        self.lev_value_2_var.set(f"{100.0 / lev:.4f}")

    def _on_leverage_commit(self, event=None):
        try:
            new_lev = int(float(self.vars["LEVERAGE"].get()))
        except Exception:
            self._refresh_leverage_info()
            return
        if new_lev <= 0:
            self._refresh_leverage_info()
            return

        old_lev = self._prev_leverage
        if old_lev == new_lev:
            self._refresh_leverage_info()
            return

        factor = old_lev / new_lev

        for k in LEVERAGE_PT_FIELDS:
            if k not in self.vars:
                continue
            try:
                old_val = float(self.vars[k].get())
            except Exception:
                continue
            new_val = max(1, int(round(old_val * factor)))
            self.vars[k].set(str(new_val))

        self._prev_leverage = new_lev
        self._refresh_leverage_info()
        self.status_var.set(fa("اهرم تغییر کرد و مقادیر پوینتی به‌روز شد"))

    def _collect(self):
        cfg = dict(DEFAULT_CONFIG)
        for k, v in self.vars.items():
            cfg[k] = v.get()
        try:
            int_keys = ["ADX_PERIOD", "CANDLE_CLOSE_CHECK_COUNT", "MAX_PENDING",
                        "ORDERS_PER_SIDE", "FIRST_DISTANCE_PTS", "STEP_PTS",
                        "ATR_PERIOD", "SL_PTS", "SL_MIN_PTS", "SL_BREAKOUT_PTS",
                        "SL_BREAKOUT_COOLDOWN_SEC", "MAX_OPEN_POSITIONS",
                        "START_HOUR", "START_MIN", "END_HOUR", "END_MIN",
                        "MAGIC", "DEVIATION", "LEVERAGE"]
            float_keys = ["LOT_SIZE", "ADX_THRESHOLD", "ADX_STRONG_THRESHOLD",
                          "ATR_SL_MULTIPLIER", "PROFIT_STEP_USD", "PROFIT_TRAIL_GAP_USD",
                          "MAX_POSITION_LOSS_USD", "DAILY_MAX_LOSS_USD",
                          "DAILY_PROFIT_TARGET_USD"]
            bool_keys = ["TRADE_NORMAL_TREND", "USE_PROXY"]

            for k in int_keys:
                cfg[k] = int(float(cfg[k]))
            for k in float_keys:
                cfg[k] = float(cfg[k])
            for k in bool_keys:
                cfg[k] = bool(cfg[k])
        except Exception as e:
            raise ValueError(fa(f"مقدار نامعتبر در فرم: {e}"))

        if cfg["LOT_SIZE"] <= 0:
            raise ValueError(fa("حجم لات باید بزرگ‌تر از صفر باشد."))
        if cfg["MAX_OPEN_POSITIONS"] <= 0:
            raise ValueError(fa("حداکثر پوزیشن باز باید بزرگ‌تر از صفر باشد."))
        if cfg["LEVERAGE"] <= 0:
            raise ValueError(fa("اهرم باید بزرگ‌تر از صفر باشد."))
        return cfg

    def on_save(self):
        try:
            cfg = self._collect()
        except Exception as e:
            messagebox.showerror("خطا", str(e)); return
        try:
            save_config_file(cfg)
            self.cfg = cfg
            self._prev_leverage = int(cfg["LEVERAGE"])
            self.status_var.set(fa("تنظیمات ذخیره شد"))
        except Exception as e:
            messagebox.showerror("خطای ذخیره", str(e))

    def on_reset(self):
        if not messagebox.askyesno("بازنشانی",
                                   "همه مقادیر به پیش‌فرض برگردند؟"):
            return
        self.cfg = dict(DEFAULT_CONFIG)
        for k, v in self.vars.items():
            v.set(self.cfg.get(k, ""))
        try:
            self._prev_leverage = int(float(self.cfg.get("LEVERAGE", 100)))
        except Exception:
            self._prev_leverage = 100
        self._refresh_leverage_info()
        self.status_var.set(fa("مقادیر به پیش‌فرض بازگشت"))

    def on_activate_license(self):
        global _LICENSE_ACTIVE, _TRIAL_DAYS_LEFT

        if _LICENSE_ACTIVE:
            messagebox.showinfo("لایسنس فعال",
                                "لایسنس دائمی این سیستم از قبل فعال است.")
            return

        hwid = get_hwid()
        ok = _show_activation_dialog(hwid, parent=self.root)

        if ok:
            _LICENSE_ACTIVE = True
            _TRIAL_DAYS_LEFT = 0
            try:
                self.root.title("AvijehBot — تنظیمات و اجرا (لایسنس دائمی)")
            except Exception:
                pass
            if self.banner_frame is not None:
                try:
                    self.banner_frame.destroy()
                except Exception:
                    pass
                self.banner_frame = None
            try:
                self.btn_license.configure(state="disabled",
                                           text=fa("لایسنس فعال است"))
            except Exception:
                pass
            self.status_var.set(fa("لایسنس دائمی با موفقیت فعال شد."))
            try:
                messagebox.showinfo(
                    "فعال‌سازی موفق",
                    "لایسنس دائمی با موفقیت فعال شد."
                )
            except Exception:
                pass

    def on_start(self):
        if self.bot_thread and self.bot_thread.is_alive():
            messagebox.showinfo("در حال اجرا", "ربات از قبل در حال اجراست.")
            return
        self._on_leverage_commit()
        try:
            cfg = self._collect()
        except Exception as e:
            messagebox.showerror("خطا در تنظیمات", str(e)); return

        save_config_file(cfg)
        apply_config(cfg)
        STOP_EVENT.clear()

        sys.stdout = QueueWriter(self.log_queue)
        sys.stderr = QueueWriter(self.log_queue)

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set(fa("ربات در حال اجراست..."))

        self.bot_thread = threading.Thread(target=self._bot_runner, daemon=True)
        self.bot_thread.start()

    def _bot_runner(self):
        _dbg("bot_runner: start")
        try:
            main()
            _dbg("bot_runner: main returned")
        except Exception as e:
            _dbg(f"bot_runner: EXC {e}")
            _dbg(traceback.format_exc())
            print("BOT ERROR:", e, flush=True)
            print(traceback.format_exc(), flush=True)
        finally:
            try:
                if mt5 is not None:
                    mt5.shutdown()
            except Exception:
                pass
            self.root.after(0, self._on_bot_finished)

    def _on_bot_finished(self):
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.status_var.set(fa("ربات متوقف شد."))

    def on_stop(self):
        if self.bot_thread and self.bot_thread.is_alive():
            STOP_EVENT.set()
            self.status_var.set(fa("در حال توقف..."))
            self.btn_stop.configure(state="disabled")

    def _poll_log(self):
        try:
            while True:
                text = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", text)
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log)


def _report_callback_exception(exc, val, tb):
    msg = "".join(traceback.format_exception(exc, val, tb))
    _dbg(f"TK CALLBACK ERROR:\n{msg}")
    print("TK CALLBACK ERROR:\n", msg, flush=True)
    try:
        messagebox.showerror("خطای غیرمنتظره", msg[:2500])
    except Exception:
        pass


# ==================== MAIN ====================
if __name__ == "__main__":
    _dbg("__main__: enter")

    try:
        # ─── یک بار Tk() بساز ───
        root = tk.Tk()
        root.title("AvijehBot")
        root.geometry("820x820")

        # پنجره را با alpha=0 نامرئی کن (به جای withdraw)
        try:
            root.attributes("-alpha", 0.0)
        except Exception:
            pass

        root.report_callback_exception = _report_callback_exception
        root.update_idletasks()
        _dbg("__main__: root Tk() created (alpha=0)")

        # ─── بررسی لایسنس ───
        try:
            status, days = check_license_status()
            _dbg(f"__main__: status={status}, days={days}")
        except Exception as e:
            _dbg(f"__main__: check_license EXC: {e}")
            _dbg(traceback.format_exc())
            try:
                root.attributes("-alpha", 1.0)
                messagebox.showerror("خطا در بررسی لایسنس", str(e), parent=root)
            except Exception:
                pass
            root.destroy()
            sys.exit(1)

        if status == "needs_activation":
            _dbg("__main__: needs activation → showing dialog")
            try:
                root.attributes("-alpha", 1.0)
            except Exception:
                pass
            hwid = get_hwid()
            ok = _show_activation_dialog(hwid, parent=root)
            _dbg(f"__main__: activation returned {ok}")
            if not ok:
                _dbg("__main__: user cancelled activation → exit")
                root.destroy()
                sys.exit(0)
            _LICENSE_ACTIVE = True

        elif status == "trial":
            _dbg(f"__main__: trial mode, {days} days left")
            try:
                root.attributes("-alpha", 1.0)
            except Exception:
                pass
            try:
                _show_trial_dialog(root, days)
                _dbg("__main__: trial dialog closed")
            except Exception as e:
                _dbg(f"__main__: trial dialog EXC: {e}")

        # ─── هشدار BiDi ───
        if not _BIDI_OK:
            _dbg("__main__: BIDI not OK, showing warning")
            try:
                root.attributes("-alpha", 1.0)
            except Exception:
                pass
            try:
                _show_rtl_dialog(
                    root,
                    "Persian font setup required",
                    "برای نمایش صحیح متن فارسی، این دو کتابخانه را نصب کنید:\n\n"
                    "pip install arabic-reshaper python-bidi\n\n"
                    "سپس برنامه را دوباره اجرا کنید.",
                    width=540, height=280
                )
            except Exception as e:
                _dbg(f"__main__: BIDI dialog EXC: {e}")

        # ─── نمایش پنجره اصلی ───
        try:
            root.attributes("-alpha", 1.0)
        except Exception:
            pass
        root.deiconify()
        root.lift()

        _dbg("__main__: building ConfigWindow")
        try:
            app = ConfigWindow(root)
            _dbg("__main__: ConfigWindow OK")
        except Exception:
            tb = traceback.format_exc()
            _dbg(f"__main__: ConfigWindow EXC:\n{tb}")
            print("STARTUP ERROR:\n", tb, flush=True)
            try:
                messagebox.showerror("خطا در راه‌اندازی برنامه", tb[:2500])
            except Exception:
                pass
            raise

        _dbg("__main__: entering mainloop")
        root.mainloop()
        _dbg("__main__: mainloop exited")

    except SystemExit:
        raise
    except Exception:
        _dbg("__main__: FATAL EXCEPTION")
        _dbg(traceback.format_exc())
        raise