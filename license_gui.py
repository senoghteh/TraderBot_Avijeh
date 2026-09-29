# -*- coding: utf-8 -*-
"""
نسخهٔ گرافیکی ابزار توسعه‌دهندهٔ ساخت کلید لایسنس.
"""

import hmac
import hashlib
import tkinter as tk
from tkinter import ttk
from datetime import datetime

# ----------------------------------------------------------------------
# هستهٔ اصلی — دقیقاً همان منطق نسخهٔ خط فرمان (خروجی یکسان)
# ----------------------------------------------------------------------
_LICENSE_SECRET = b"AvijehBot_2025_M3hd1Z4r3_D0ntSh4re_Th1sK3y"
_B32_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _b32_encode(data: bytes) -> str:
    bits = "".join(format(b, "08b") for b in data)
    while len(bits) % 5:
        bits += "0"
    return "".join(
        _B32_ALPHABET[int(bits[i:i + 5], 2)]
        for i in range(0, len(bits), 5)
    )


def generate_license(hwid: str) -> str:
    hwid = hwid.strip().upper().replace(" ", "")
    mac = hmac.new(_LICENSE_SECRET, hwid.encode("utf-8"), hashlib.sha256).digest()
    code = _b32_encode(mac[:10])
    return "-".join(code[i:i + 4] for i in range(0, 16, 4))


# ----------------------------------------------------------------------
# استایل و رنگ‌ها
# ----------------------------------------------------------------------
COLORS = {
    "bg":       "#16161e",
    "panel":    "#1f2233",
    "panel2":   "#262a40",
    "border":   "#2f3350",
    "accent":   "#7aa2f7",
    "accent2":  "#5a82d7",
    "text":     "#e8e9f0",
    "muted":    "#8b90a8",
    "ok":       "#9ece6a",
    "warn":     "#e0af68",
    "danger":   "#f7768e",
}

FONT = "Tahoma"
MONO = "Consolas"


class LicenseGUI:
    MAX_HISTORY = 50

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("AvijehBot — تولیدکنندهٔ کلید لایسنس")
        root.geometry("700x620")
        root.minsize(620, 540)
        root.configure(bg=COLORS["bg"])

        self._build_styles()
        self._build_header()
        self._build_input()
        self._build_result()
        self._build_history()
        self._build_status()

        self.entry.focus_set()

    # ------------------------------------------------------------------
    # ساخت اجزای رابط
    # ------------------------------------------------------------------
    def _build_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Treeview",
            background=COLORS["panel"],
            fieldbackground=COLORS["panel"],
            foreground=COLORS["text"],
            rowheight=26,
            borderwidth=0,
            font=(FONT, 9),
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["panel2"],
            foreground=COLORS["muted"],
            font=(FONT, 9, "bold"),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["accent"])],
            foreground=[("selected", "#101018")],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", COLORS["panel2"])],
        )

    def _build_header(self):
        header = tk.Frame(self.root, bg=COLORS["bg"])
        header.pack(fill="x", padx=22, pady=(20, 6))

        tk.Label(
            header,
            text="🔐  AvijehBot License Generator",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=(FONT, 15, "bold"),
            anchor="e",
        ).pack(fill="x")

        tk.Label(
            header,
            text="ابزار توسعه‌دهنده — این فایل و کلید مخفی را با کاربر به اشتراک نگذارید.",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=(FONT, 9),
            anchor="e",
        ).pack(fill="x", pady=(4, 0))

    def _build_input(self):
        card = tk.Frame(self.root, bg=COLORS["panel"], highlightthickness=1,
                        highlightbackground=COLORS["border"])
        card.pack(fill="x", padx=22, pady=(14, 0))

        inner = tk.Frame(card, bg=COLORS["panel"])
        inner.pack(fill="x", padx=16, pady=16)

        tk.Label(
            inner,
            text="شناسهٔ سخت‌افزار کاربر (HWID):",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT, 10),
            anchor="e",
        ).pack(fill="x")

        entry_wrap = tk.Frame(inner, bg=COLORS["panel2"], highlightthickness=1,
                              highlightbackground=COLORS["border"],
                              highlightcolor=COLORS["accent"])
        entry_wrap.pack(fill="x", pady=(8, 14))

        self.entry = tk.Entry(
            entry_wrap,
            bg=COLORS["panel2"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            relief="flat",
            font=(MONO, 12),
            justify="center",
        )
        self.entry.pack(fill="x", padx=10, pady=10)
        self.entry.bind("<Return>", lambda _e: self.on_generate())
        self.entry.bind("<KP_Enter>", lambda _e: self.on_generate())

        btns = tk.Frame(inner, bg=COLORS["panel"])
        btns.pack(fill="x")

        self._make_button(
            btns, "ساخت کلید لایسنس", self.on_generate,
            bg=COLORS["accent"], fg="#101018", hover=COLORS["accent2"],
        ).pack(side="right", ipadx=16)

        self._make_button(
            btns, "پاک کردن", self.on_clear,
            bg=COLORS["panel2"], fg=COLORS["text"], hover=COLORS["border"],
        ).pack(side="right", padx=(0, 8), ipadx=12)

    def _build_result(self):
        card = tk.Frame(self.root, bg=COLORS["panel"], highlightthickness=1,
                        highlightbackground=COLORS["border"])
        card.pack(fill="x", padx=22, pady=(14, 0))

        inner = tk.Frame(card, bg=COLORS["panel"])
        inner.pack(fill="x", padx=16, pady=16)

        tk.Label(
            inner,
            text="کلید لایسنس:",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT, 10),
            anchor="e",
        ).pack(fill="x")

        self.result_var = tk.StringVar(value="")
        self.result_entry = tk.Entry(
            inner,
            textvariable=self.result_var,
            state="readonly",
            readonlybackground=COLORS["panel2"],
            fg=COLORS["ok"],
            relief="flat",
            font=(MONO, 19, "bold"),
            justify="center",
        )
        self.result_entry.pack(fill="x", ipady=12, pady=(8, 12))

        row = tk.Frame(inner, bg=COLORS["panel"])
        row.pack(fill="x")

        self.copy_btn = self._make_button(
            row, "📋 کپی در کلیپ‌بورد", self.on_copy,
            bg=COLORS["panel2"], fg=COLORS["text"], hover=COLORS["border"],
        )
        self.copy_btn.pack(side="right", ipadx=12)

    def _build_history(self):
        card = tk.Frame(self.root, bg=COLORS["panel"], highlightthickness=1,
                        highlightbackground=COLORS["border"])
        card.pack(fill="both", expand=True, padx=22, pady=(14, 0))

        inner = tk.Frame(card, bg=COLORS["panel"])
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        top = tk.Frame(inner, bg=COLORS["panel"])
        top.pack(fill="x", pady=(0, 8))

        tk.Label(
            top,
            text="تاریخچهٔ کلیدهای ساخته‌شده (دوبار کلیک = کپی)",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT, 10),
            anchor="e",
        ).pack(side="right")

        self._make_button(
            top, "پاک کردن تاریخچه", self.on_clear_history,
            bg=COLORS["panel2"], fg=COLORS["muted"], hover=COLORS["border"],
            font=(FONT, 8),
        ).pack(side="left", ipadx=8)

        wrap = tk.Frame(inner, bg=COLORS["panel"])
        wrap.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            wrap, columns=("hwid", "license", "time"),
            show="headings", selectmode="browse",
        )
        self.tree.heading("hwid", text="HWID")
        self.tree.heading("license", text="کلید لایسنس")
        self.tree.heading("time", text="زمان")
        self.tree.column("hwid", anchor="center", width=240)
        self.tree.column("license", anchor="center", width=200)
        self.tree.column("time", anchor="center", width=90)

        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.pack(side="right", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self.tree.bind("<Double-1>", self.on_tree_double_click)

    def _build_status(self):
        self.status_var = tk.StringVar(value="آماده")
        self.status_lbl = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=(FONT, 9),
            anchor="e",
        )
        self.status_lbl.pack(fill="x", padx=24, pady=(8, 14))

    # ------------------------------------------------------------------
    # ابزار کمکی
    # ------------------------------------------------------------------
    def _make_button(self, parent, text, command, bg, fg, hover, font=None):
        btn = tk.Button(
            parent, text=text, command=command,
            bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
            relief="flat", bd=0, cursor="hand2",
            font=font or (FONT, 10, "bold"),
            padx=10, pady=8,
        )
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hover))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
        return btn

    def _set_status(self, text, kind="muted"):
        self.status_var.set(text)
        self.status_lbl.configure(fg=COLORS.get(kind, COLORS["muted"]))

    # ------------------------------------------------------------------
    # رویدادها
    # ------------------------------------------------------------------
    def on_generate(self):
        raw = self.entry.get().strip()
        if not raw:
            self._set_status("لطفاً شناسهٔ سخت‌افزار (HWID) را وارد کنید.", "warn")
            self.entry.focus_set()
            return

        hwid = raw.upper().replace(" ", "")
        lic = generate_license(hwid)

        self.result_var.set(lic)
        self.result_entry.selection_range(0, "end")

        self.tree.insert(
            "", 0,
            values=(hwid, lic, datetime.now().strftime("%H:%M:%S")),
        )
        # محدود کردن تعداد رکوردهای تاریخچه
        children = self.tree.get_children()
        if len(children) > self.MAX_HISTORY:
            for item in children[self.MAX_HISTORY:]:
                self.tree.delete(item)

        self._set_status(f"کلید برای «{hwid}» ساخته شد.", "ok")

    def on_copy(self):
        lic = self.result_var.get().strip()
        if not lic:
            self._set_status("چیزی برای کپی وجود ندارد.", "warn")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(lic)
        self.root.update_idletasks()
        self._set_status("کلید لایسنس در کلیپ‌بورد کپی شد.", "ok")

    def on_clear(self):
        self.entry.delete(0, "end")
        self.result_var.set("")
        self.entry.focus_set()
        self._set_status("آماده", "muted")

    def on_clear_history(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._set_status("تاریخچه پاک شد.", "muted")

    def on_tree_double_click(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        hwid, lic, _t = self.tree.item(sel[0], "values")
        self.entry.delete(0, "end")
        self.entry.insert(0, hwid)
        self.result_var.set(lic)
        self.root.clipboard_clear()
        self.root.clipboard_append(lic)
        self.root.update_idletasks()
        self._set_status(f"کلید «{hwid}» کپی شد.", "ok")


# ----------------------------------------------------------------------
# اجرا
# ----------------------------------------------------------------------
def main():
    root = tk.Tk()
    LicenseGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
