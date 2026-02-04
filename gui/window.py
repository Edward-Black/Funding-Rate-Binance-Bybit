"""
Standard Windows GUI: funding rate, time to next, interval.
Symbol input: uppercase Latin only, layout-independent (keycode-based).
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from tkinter import Tk, ttk, StringVar, Label, Entry, Frame, Button, Listbox, Scrollbar
from typing import Any

import urllib.request

from config import API_HOST, API_PORT, DEFAULT_SYMBOL, PARQUET_DIR

STATE_FILE = os.path.join(os.path.dirname(PARQUET_DIR), "window_state.json")

# Windows virtual key codes: digits 0-9, letters A-Z, hyphen
# So input is always Latin uppercase regardless of keyboard layout
VK_DIGITS = set(range(0x30, 0x3A))  # 48-57
VK_LETTERS = set(range(0x41, 0x5B))  # 65-90
VK_HYPHEN = 0xBD  # 189, VK_OEM_MINUS
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_ALLOWED = VK_DIGITS | VK_LETTERS | {VK_HYPHEN, VK_BACK, VK_DELETE}


def keycode_to_char(keycode: int) -> str | None:
    """Map Windows keycode to allowed character (uppercase Latin or digit or hyphen)."""
    if keycode in VK_DIGITS:
        return chr(keycode)
    if keycode in VK_LETTERS:
        return chr(keycode)
    if keycode == VK_HYPHEN:
        return "-"
    return None


def on_symbol_keypress(event) -> str:
    """Только латиница верхний регистр, цифры, дефис. При вводе заменять выделение. Ctrl+V — вставка с фильтром."""
    keycode = getattr(event, "keycode", None)
    widget = event.widget
    if keycode is None or not isinstance(widget, Entry):
        return "break"
    state = getattr(event, "state", 0)
    # Ctrl+V — вставить из буфера, оставив только допустимые символы
    if (state & 0x4) and keycode == 0x56:  # Control + V
        try:
            root = widget.winfo_toplevel()
            clip = root.clipboard_get()
        except Exception:
            clip = ""
        s = "".join(c for c in (clip or "").upper() if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
        try:
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
            widget.insert("insert", s)
        except Exception:
            pass
        return "break"
    if keycode not in VK_ALLOWED:
        return "break"
    if keycode == VK_BACK or keycode == VK_DELETE:
        return None  # allow default
    char = keycode_to_char(keycode)
    if char is None:
        return "break"
    try:
        if widget.selection_present():
            start = widget.index("sel.first")
            end = widget.index("sel.last")
            widget.delete(start, end)
            widget.insert(start, char)
        else:
            widget.insert(widget.index("insert"), char)
        return "break"
    except Exception:
        return "break"


def symbol_to_pair(symbol: str) -> str:
    """ZIL -> ZILUSDT, BTC -> BTCUSDT; если уже оканчивается на USDT — без изменений."""
    s = symbol.upper().strip()
    if not s:
        return s
    if s.endswith("USDT"):
        return s
    return s + "USDT"


def fetch_funding(symbol: str) -> dict[str, Any]:
    """GET /api/funding?symbol=..."""
    symbol = symbol_to_pair(symbol.upper().strip())
    url = f"http://{API_HOST}:{API_PORT}/api/funding?symbol={symbol}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def fetch_funding_history(symbol: str) -> dict[str, Any]:
    """GET /api/funding-history?symbol=... Возвращает { binance: [...], bybit: [...], okx: [...] }."""
    symbol = symbol_to_pair(symbol.upper().strip())
    url = f"http://{API_HOST}:{API_PORT}/api/funding-history?symbol={symbol}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def format_history_line(funding_time_ms: int, funding_rate: str) -> str:
    """Одна строка для списка истории: дата/время (локальный часовой пояс) и ставка в %."""
    try:
        dt = datetime.fromtimestamp(funding_time_ms / 1000.0)
        s = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        s = "—"
    try:
        r = float(funding_rate)
        rate_pct = f"{r * 100:.6f}%"
    except (ValueError, TypeError):
        rate_pct = funding_rate or "—"
    return f"{s}  {rate_pct}"


def format_funding_rate(rate_str: str) -> str:
    """Форматировать ставку как процент: 0.0001 -> 0.01%."""
    if not rate_str or rate_str == "—":
        return "—"
    try:
        r = float(rate_str)
        return f"{r * 100:.6f}%"
    except (ValueError, TypeError):
        return rate_str


def format_time_to_next(next_funding_ms: int) -> str:
    """Countdown from local time to next funding (UTC ms). Format: Xh Ym Zs."""
    if not next_funding_ms:
        return "—"
    try:
        next_utc = datetime.fromtimestamp(next_funding_ms / 1000.0, tz=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        delta = next_utc - now_utc
        if delta.total_seconds() <= 0:
            return "0h 0m 0s"
        total = int(delta.total_seconds())
        h, r = divmod(total, 3600)
        m, s = divmod(r, 60)
        return f"{h}h {m}m {s}s"
    except Exception:
        return "—"


def _separator(parent: Frame) -> Frame:
    """Горизонтальная линия-разделитель (светлый, ближе к белому)."""
    f = Frame(parent, height=2, bg="#e8e8e8")
    f.pack(fill="x", pady=(8, 8))
    return f


class FundingWindow:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Funding Rate Parser")
        self.root.minsize(400, 420)
        self.root.configure(bg="#a9a9a9")

        self.symbol_var = StringVar(value=DEFAULT_SYMBOL)
        self._load_state()
        self.data: dict[str, Any] = {}
        self.next_funding_ms: dict[str, int] = {}
        self._exchange_labels: dict[str, dict[str, Any]] = {}  # name -> {rate, ttn, interval, ...}
        self._history_visible: dict[str, bool] = {}
        self._history_loaded_symbol: dict[str, str] = {}
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_timers()

    def _load_state(self) -> None:
        """Восстановить размер, позицию окна и последнюю пару из файла."""
        try:
            if os.path.isfile(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
                w = state.get("width", 480)
                h = state.get("height", 460)
                x = state.get("x")
                y = state.get("y")
                sym = (state.get("symbol") or "").strip().upper()
                if sym and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in sym):
                    self.symbol_var.set(sym)
                if x is not None and y is not None:
                    self.root.geometry(f"{w}x{h}+{x}+{y}")
                else:
                    self.root.geometry(f"{w}x{h}")
            else:
                self.root.geometry("480x460")
        except Exception:
            self.root.geometry("480x460")

    def _save_state(self) -> None:
        """Сохранить размер, позицию окна и последнюю пару в файл. Размер/позицию берём из geometry() — так сохраняется актуальный размер после сворачивания списков."""
        try:
            geom = self.root.geometry()
            w = h = x = y = None
            if "+" in geom:
                part, pos = geom.split("+", 1)
                x_s, y_s = pos.split("+", 1)
                x, y = int(x_s), int(y_s)
            else:
                part = geom
            if "x" in part:
                w_s, h_s = part.split("x", 1)
                w, h = int(w_s), int(h_s)
            if w is None or h is None:
                w, h = self.root.winfo_width(), self.root.winfo_height()
            if x is None or y is None:
                x, y = self.root.winfo_x(), self.root.winfo_y()
            sym = (self.symbol_var.get() or "").strip().upper()
            state = {"width": w, "height": h, "x": x, "y": y, "symbol": sym or DEFAULT_SYMBOL}
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _collapse_all_history(self) -> None:
        """Свернуть все раскрытые блоки Funding Rate History (чтобы сохранить размер окна со свёрнутыми списками)."""
        total_height = 0
        to_collapse = []
        for name in ("binance", "bybit", "okx"):
            if not self._history_visible.get(name, False):
                continue
            labels = self._exchange_labels.get(name)
            if not labels:
                continue
            frame = labels["history_frame"]
            block_height = frame.winfo_height() + self._HISTORY_PADY_TOTAL
            total_height += block_height
            to_collapse.append((name, labels))
        for name, labels in to_collapse:
            frame = labels["history_frame"]
            btn = labels["history_btn"]
            frame.pack_forget()
            btn.config(text="Funding Rate History ▶")
            self._history_visible[name] = False
        if total_height > 0:
            self._resize_window_by(-total_height)

    def _on_close(self) -> None:
        self._collapse_all_history()
        self.root.update_idletasks()
        self.root.update()
        self._save_state()
        self.root.destroy()

    def _build_ui(self) -> None:
        main = Frame(self.root, padx=12, pady=12, bg="#a9a9a9")
        main.pack(fill="both", expand=True)

        title = Label(main, text="FUNDING RATE PARSER", font=("Arial", 14, "bold"), bg="#a9a9a9")
        title.pack(pady=(0, 4))

        self._status_label = Label(main, text="Status: Connected", fg="#228b22", font=("Arial", 10), bg="#a9a9a9")
        self._status_label.pack(pady=(0, 10))

        row = Frame(main, bg="#a9a9a9")
        row.pack(fill="x", pady=4)
        Label(row, text="Trading Pair:", font=("Arial", 11), bg="#a9a9a9").pack(side="left", padx=(0, 6))
        self.entry = Entry(row, textvariable=self.symbol_var, width=14, font=("Arial", 11))
        self.entry.pack(side="left", padx=2)
        self.entry.bind("<KeyPress>", on_symbol_keypress)
        self.entry.bind("<FocusOut>", self._normalize_symbol)
        self.entry.bind("<Return>", lambda e: self._on_enter_refresh())
        btn_refresh = Button(row, text="REFRESH", command=self._refresh, font=("Arial", 10, "bold"),
                             bg="#4CAF50", fg="white", activebackground="#43A047", activeforeground="white",
                             relief="raised", bd=2, cursor="hand2")
        btn_refresh.pack(side="left", padx=10)

        _separator(main)

        for name in ("binance", "bybit", "okx"):
            display_name = "OKX" if name == "okx" else name.upper()
            sec = Frame(main, bg="#a9a9a9")
            sec.pack(fill="x", pady=6)
            Label(sec, text=display_name, font=("Arial", 12, "bold"), bg="#a9a9a9").pack(anchor="w")
            row_fr = Frame(sec, bg="#a9a9a9")
            row_fr.pack(anchor="w", pady=2)
            Label(row_fr, text="Funding Rate:", font=("Arial", 10), bg="#a9a9a9", width=14, anchor="w").pack(side="left")
            lb_rate = Label(row_fr, text="—", font=("Arial", 11, "bold"), bg="#a9a9a9")
            lb_rate.pack(side="left")
            row_ttn = Frame(sec, bg="#a9a9a9")
            row_ttn.pack(anchor="w", pady=2)
            Label(row_ttn, text="Time to Next:", font=("Arial", 10), bg="#a9a9a9", width=14, anchor="w").pack(side="left")
            lb_ttn = Label(row_ttn, text="—", font=("Arial", 10), bg="#a9a9a9")
            lb_ttn.pack(side="left")
            row_int = Frame(sec, bg="#a9a9a9")
            row_int.pack(anchor="w", pady=2)
            Label(row_int, text="Interval:", font=("Arial", 10), bg="#a9a9a9", width=14, anchor="w").pack(side="left")
            lb_int = Label(row_int, text="—", font=("Arial", 10), bg="#a9a9a9")
            lb_int.pack(side="left")
            # Funding Rate History — раскрывающийся список
            self._history_visible[name] = False
            row_hist = Frame(sec, bg="#a9a9a9")
            row_hist.pack(anchor="w", pady=(6, 2))
            btn_hist = Button(
                sec, text="Funding Rate History ▶", font=("Arial", 9), bg="#a9a9a9", fg="#0066cc",
                activebackground="#a9a9a9", activeforeground="#0066cc", relief="flat", cursor="hand2",
                command=lambda n=name: self._toggle_history(n),
            )
            btn_hist.pack(anchor="w", pady=(2, 0))
            hist_frame = Frame(sec, bg="#a9a9a9")
            listbox = Listbox(hist_frame, height=6, font=("Consolas", 9), bg="white",
                                  selectbackground="#e0e0e0", selectforeground="black", selectborderwidth=0, highlightthickness=0,
                                  activestyle="none")
            scroll = Scrollbar(hist_frame, orient="vertical", command=listbox.yview)
            listbox.configure(yscrollcommand=scroll.set)
            listbox.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            self._exchange_labels[name] = {
                "rate": lb_rate, "ttn": lb_ttn, "interval": lb_int,
                "history_btn": btn_hist, "history_frame": hist_frame, "history_listbox": listbox,
            }
            if name != "okx":
                _separator(main)

    def _resize_window_by(self, delta_height: int) -> None:
        """Изменить высоту основного окна на delta_height (положительное — увеличить)."""
        try:
            geom = self.root.geometry()
            # Формат: "WxH" или "WxH+X+Y"
            if "+" in geom:
                part, pos = geom.split("+", 1)
                x, y = pos.split("+", 1)
            else:
                part = geom
                x = y = None
            if "x" in part:
                w, h = part.split("x", 1)
                new_h = max(self.root.minsize()[1], int(h) + delta_height)
                if x is not None and y is not None:
                    self.root.geometry(f"{w}x{new_h}+{x}+{y}")
                else:
                    self.root.geometry(f"{w}x{new_h}")
        except Exception:
            pass

    # Отступ между кнопкой "Funding Rate History" и выпадающим списком: pady=(2, 4)
    _HISTORY_PADY_TOTAL = 6

    def _toggle_history(self, name: str) -> None:
        """Раскрыть/свернуть блок Funding Rate History для биржи; окно растягивается/сжимается по высоте."""
        labels = self._exchange_labels.get(name)
        if not labels:
            return
        frame = labels["history_frame"]
        btn = labels["history_btn"]
        if self._history_visible.get(name, False):
            block_height = frame.winfo_height() + self._HISTORY_PADY_TOTAL
            frame.pack_forget()
            self._resize_window_by(-block_height)
            btn.config(text="Funding Rate History ▶")
            self._history_visible[name] = False
        else:
            frame.pack(anchor="w", fill="x", pady=(2, 4))
            self.root.update_idletasks()
            frame_height = frame.winfo_reqheight()
            if frame_height <= 0:
                frame_height = frame.winfo_height()
            block_height = frame_height + self._HISTORY_PADY_TOTAL
            self._resize_window_by(block_height)
            btn.config(text="Funding Rate History ▼")
            self._history_visible[name] = True
            symbol = (self.symbol_var.get() or "").upper().strip()
            if symbol and self._history_loaded_symbol.get(name) != symbol:
                self._load_history_for_exchange(name)

    def _load_history_for_exchange(self, name: str) -> None:
        """Загрузить историю фандингов для биржи в фоне и заполнить список."""
        symbol = (self.symbol_var.get() or "").upper().strip()
        if not symbol:
            return

        def do():
            data = fetch_funding_history(symbol)
            self.root.after(0, lambda: self._fill_history_listbox(name, symbol, data))

        threading.Thread(target=do, daemon=True).start()

    def _fill_history_listbox(self, name: str, symbol: str, data: dict[str, Any]) -> None:
        """Заполнить Listbox истории для биржи (вызывать из main thread)."""
        current = (self.symbol_var.get() or "").upper().strip()
        if current != symbol:
            return
        labels = self._exchange_labels.get(name)
        if not labels:
            return
        listbox = labels["history_listbox"]
        listbox.delete(0, "end")
        if data.get("error"):
            listbox.insert("end", f"Error: {data['error']}")
            self._history_loaded_symbol[name] = symbol
            return
        lst = data.get(name)
        items = list(lst) if isinstance(lst, list) else []
        items.sort(key=lambda x: x.get("fundingTime") or 0, reverse=True)
        for item in items:
            ts = item.get("fundingTime") or 0
            rate = item.get("fundingRate") or ""
            listbox.insert("end", format_history_line(ts, rate))
        self._history_loaded_symbol[name] = symbol

    def _normalize_symbol(self, event=None) -> None:
        s = "".join(c for c in self.symbol_var.get().upper() if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
        if s:
            s = symbol_to_pair(s)
        self.symbol_var.set(s)

    def _on_enter_refresh(self) -> None:
        """По Enter: нормализуем пару и сразу запрос без задержки."""
        self._normalize_symbol()
        self._refresh()

    def _refresh(self) -> None:
        symbol = self.symbol_var.get().upper().strip()
        if not symbol:
            self._status_label.config(text="Enter symbol (e.g. BTCUSDT)")
            return
        def do():
            self.data = fetch_funding(symbol)
            self.root.after(0, self._apply_data)
        threading.Thread(target=do, daemon=True).start()

    def _apply_data(self) -> None:
        if "error" in self.data and len(self.data) == 1:
            self._status_label.config(text=f"Status: Error — {self.data['error']}", fg="#b22222")
            return
        self._status_label.config(text="Status: Connected", fg="#228b22")
        for name in ("binance", "bybit", "okx"):
            labels = self._exchange_labels.get(name)
            if not labels:
                continue
            row = self.data.get(name) or {}
            if isinstance(row, dict) and "error" in row:
                labels["rate"].config(text="—", fg="black", font=("Arial", 11, "bold"))
                labels["ttn"].config(text="—")
                labels["interval"].config(text="—")
                self.next_funding_ms[name] = 0
            else:
                rate = format_funding_rate(row.get("fundingRate", "") or "")
                next_ms = row.get("nextFundingTimeMs") or 0
                self.next_funding_ms[name] = next_ms
                ttn = format_time_to_next(next_ms)
                interval = row.get("interval", "—") or "—"
                labels["rate"].config(text=rate, font=("Arial", 11, "bold"))
                try:
                    r = float(row.get("fundingRate") or 0)
                    labels["rate"].config(fg="#427b20" if r >= 0 else "#be122a")
                except (ValueError, TypeError):
                    labels["rate"].config(fg="black")
                labels["ttn"].config(text=ttn)
                labels["interval"].config(text=interval)
        for name in ("binance", "bybit", "okx"):
            if self._history_visible.get(name):
                self._history_loaded_symbol[name] = ""
                self._load_history_for_exchange(name)

    def _tick_countdown(self) -> None:
        """Update Time to Next every second."""
        for name in ("binance", "bybit", "okx"):
            next_ms = self.next_funding_ms.get(name, 0)
            if not next_ms:
                continue
            labels = self._exchange_labels.get(name)
            if labels:
                labels["ttn"].config(text=format_time_to_next(next_ms))
        self.root.after(1000, self._tick_countdown)

    def _api_poll(self) -> None:
        """Refresh data from API every 15 seconds."""
        self._refresh()
        self.root.after(15_000, self._api_poll)

    def _start_timers(self) -> None:
        self.root.after(1000, self._tick_countdown)
        self.root.after(500, self._api_poll)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = FundingWindow()
    app.run()


if __name__ == "__main__":
    main()
