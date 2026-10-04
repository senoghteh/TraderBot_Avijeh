# noyan.py — ربات معامله‌گر MT5 (اتصال خودکار، بدون لاگین)
# -*- coding: utf-8 -*-

import sys
import os
import csv
import json
import time
import threading
import itertools
import traceback
from datetime import datetime, timedelta

# ============================================================
#          مدیریت مسیرها در حالت EXE (PyInstaller)
# ============================================================
def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(rel):
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


# ============================================================
#                    بررسی پکیج‌ها
# ============================================================
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QSpinBox,
        QDoubleSpinBox, QCheckBox, QGroupBox, QTabWidget, QFormLayout,
        QMessageBox, QSplitter, QDateEdit, QTableWidget, QTableWidgetItem,
        QProgressBar, QHeaderView, QFileDialog, QFrame, QGridLayout,
        QSizePolicy, QScrollArea
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QObject, QDate, QTimer, QThread, QEvent
    from PyQt5.QtGui import QFont, QFontDatabase, QTextCursor, QColor, QBrush
except ImportError:
    print("خطا: PyQt5 نصب نیست. اجرا کنید: pip install PyQt5")
    sys.exit(1)

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("خطا: pandas/numpy نصب نیست. اجرا کنید: pip install pandas numpy")
    sys.exit(1)

try:
    import requests
    import pytz
except ImportError:
    print("خطا: requests/pytz نصب نیست. اجرا کنید: pip install requests pytz")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import (
        FigureCanvasQTAgg as FigureCanvas,
        NavigationToolbar2QT as NavToolbar,
    )
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
except ImportError:
    print("خطا: matplotlib نصب نیست. اجرا کنید: pip install matplotlib")
    sys.exit(1)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
    TF_MAP = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
    }
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False
    TF_MAP = {}


# ============================================================
#            اتصال خودکار به MT5 باز (بدون لاگین)
# ============================================================
def mt5_attach(symbol=None):
    if not MT5_AVAILABLE:
        return False, "MetaTrader5 نصب نیست (فقط ویندوز پشتیبانی می‌شود)"

    if not mt5.initialize():
        err = mt5.last_error()
        return False, f"اتصال به متاتریدر ناموفق: {err}\nمطمئن شوید متاتریدر ۵ باز است."

    info = mt5.terminal_info()
    if info is None:
        return False, "اطلاعات ترمینال دریافت نشد"

    acc = mt5.account_info()
    if acc is None:
        return False, "حسابی در متاتریدر لاگین نیست. ابتدا در متاتریدر لاگین کنید."

    if symbol:
        sinfo = mt5.symbol_info(symbol)
        if sinfo is None:
            if not mt5.symbol_select(symbol, True):
                return False, (f"نماد '{symbol}' در بروکر یافت نشد.\n"
                               f"نام دقیق نماد را در Market Watch متاتریدر ببینید.")
            time.sleep(0.5)
            sinfo = mt5.symbol_info(symbol)
            if sinfo is None:
                return False, f"نماد '{symbol}' در دسترس نیست."
        elif not sinfo.visible:
            mt5.symbol_select(symbol, True)
            time.sleep(0.3)

    msg = (f"✅ متصل به متاتریدر\n"
           f"حساب: {acc.login} | بروکر: {acc.server}\n"
           f"موجودی: {acc.balance:.2f} {acc.currency}")
    return True, msg


def mt5_detach():
    if MT5_AVAILABLE:
        try:
            mt5.shutdown()
        except Exception:
            pass


# ============================================================
#                    تنظیمات پیش‌فرض
# ============================================================
CONFIG_FILE = os.path.join(app_dir(), "config.json")

DEFAULT_CONFIG = {
    "symbol": "XAUUSD.st",
    "timeframe": "M15",
    "timeframe_higher": "M30",
    "lot_size": 0.01,
    "max_loss_per_trade": 0.0,
    "commission_per_lot": 7.0,
    "strict_max_loss": True,
    "stop_distances": "1.0,2",
    "limit_distances": "1.0,2",
    "risk_reward": 1.0,
    "atr_multiplier": 3.5,
    "enable_adx": True,
    "adx_period": 14,
    "adx_threshold": 30.0,
    "enable_candle_sequence": True,
    "candle_sequence_count": 2,
    "partial_profit_step": 6.0,
    "partial_profit_fraction": 0.5,
    "trailing_drop": 1.0,
    "max_daily_profit": 300.0,
    "max_daily_loss": 20.0,
    "trading_start_hour": 0,
    "trading_start_min": 00,
    "trading_end_hour": 23,
    "trading_end_min": 59,
    "enable_smc": False,
    "enable_fvg": False,
    "enable_price_action": False,
    "enable_higher_tf_confirm": False,
    "max_simultaneous_orders": 2,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "enable_telegram": True,
    "enable_loss_alert": True,
    "loss_alert_threshold": 10.0,
    "loop_interval_sec": 5,
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(data)
            return cfg
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ============================================================
#              توابع تحلیل
# ============================================================
def calc_adx(df, period=14):
    period = max(2, int(period))
    if len(df) < (period * 2 + 1):
        return {"adx": np.nan, "plus_di": np.nan, "minus_di": np.nan}

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr_w = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_w = plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    minus_w = minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * plus_w / atr_w.replace(0, np.nan)
    minus_di = 100 * minus_w / atr_w.replace(0, np.nan)
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    return {
        "adx": float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else np.nan,
        "plus_di": float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else np.nan,
        "minus_di": float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else np.nan,
    }


def confirm_candle_sequence(df, trend, count=3):
    try:
        count = max(2, int(count))
    except Exception:
        count = 3

    if trend not in ("UP", "DOWN") or df is None or len(df) < count:
        return False

    seq = df.iloc[-count:].copy()
    opens = seq["open"].astype(float).to_numpy()
    closes = seq["close"].astype(float).to_numpy()

    if trend == "UP":
        return bool(np.all(closes[1:] > opens[:-1]))
    return bool(np.all(closes[1:] < opens[:-1]))


def detect_trend(df, use_adx=True, adx_period=14, adx_threshold=20.0):
    if len(df) < 60:
        return "SIDEWAYS"

    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=50, adjust=False).mean()
    last = df.iloc[-1]
    prev = df.iloc[-5]
    slope = last['ema_fast'] - prev['ema_fast']
    above = last['close'] > last['ema_fast'] and last['close'] > last['ema_slow']
    below = last['close'] < last['ema_fast'] and last['close'] < last['ema_slow']

    adx_data = calc_adx(df, adx_period)
    if use_adx:
        adx = adx_data["adx"]
        if not np.isfinite(adx) or adx < float(adx_threshold):
            return "SIDEWAYS"

    if above and slope > 0 and last['ema_fast'] > last['ema_slow']:
        if (not use_adx or
                (np.isfinite(adx_data["plus_di"]) and
                 adx_data["plus_di"] > adx_data["minus_di"])):
            return "UP"

    if below and slope < 0 and last['ema_fast'] < last['ema_slow']:
        if (not use_adx or
                (np.isfinite(adx_data["minus_di"]) and
                 adx_data["minus_di"] > adx_data["plus_di"])):
            return "DOWN"

    return "SIDEWAYS"


def detect_fvg(df, trend):
    if len(df) < 3:
        return None
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    if trend == "UP" and c3['low'] > c1['high'] and c2['close'] > c2['open']:
        return {"type": "BULLISH_FVG", "gap_low": c1['high'], "gap_high": c3['low']}
    if trend == "DOWN" and c3['high'] < c1['low'] and c2['close'] < c2['open']:
        return {"type": "BEARISH_FVG", "gap_low": c3['high'], "gap_high": c1['low']}
    return None


def detect_bos(df, lookback=20):
    if len(df) < lookback + 5:
        return None
    highs = df['high'].rolling(lookback).max().shift(1)
    lows = df['low'].rolling(lookback).min().shift(1)
    last_close = df.iloc[-1]['close']
    if pd.notna(highs.iloc[-2]) and last_close > highs.iloc[-2]:
        return "BULLISH_BOS"
    if pd.notna(lows.iloc[-2]) and last_close < lows.iloc[-2]:
        return "BEARISH_BOS"
    return None


def detect_price_action(df):
    if len(df) < 3:
        return None
    c1, c2 = df.iloc[-3], df.iloc[-2]
    body2 = abs(c2['close'] - c2['open'])
    rng2 = c2['high'] - c2['low']
    if rng2 == 0:
        return None
    if (c2['close'] > c2['open'] and c1['close'] < c1['open']
            and c2['close'] > c1['open'] and c2['open'] < c1['close']):
        return "BULLISH_ENGULFING"
    if (c2['close'] < c2['open'] and c1['close'] > c1['open']
            and c2['close'] < c1['open'] and c2['open'] > c1['close']):
        return "BEARISH_ENGULFING"
    lower_wick = min(c2['open'], c2['close']) - c2['low']
    upper_wick = c2['high'] - max(c2['open'], c2['close'])
    if lower_wick > 2 * body2 and upper_wick < body2 * 0.5:
        return "BULLISH_PINBAR"
    if upper_wick > 2 * body2 and lower_wick < body2 * 0.5:
        return "BEARISH_PINBAR"
    return None


def calc_atr(df, period=14):
    if len(df) < period + 1:
        return 1.0
    tr = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs()
        )
    )
    return tr.rolling(period).mean().iloc[-1]


# ============================================================
#         ارزیابی استراتژی‌ها + منطق اصلی
# ============================================================
def _any_optional_strategy_enabled(cfg):
    return bool(
        cfg.get("enable_smc") or
        cfg.get("enable_fvg") or
        cfg.get("enable_price_action")
    )


def evaluate_strategies(df_closed, trend, cfg):
    if df_closed is None or len(df_closed) < 5:
        return None, None, None

    rr_default = float(cfg.get("risk_reward", 2.0))

    if not _any_optional_strategy_enabled(cfg):
        if trend not in ("UP", "DOWN"):
            return None, None, None

        if cfg.get("enable_candle_sequence", True):
            count = int(cfg.get("candle_sequence_count", 3))
            if not confirm_candle_sequence(df_closed, trend, count):
                return None, None, None

        if detect_fvg(df_closed, trend):
            return trend, "MAIN_FVG", rr_default

        return None, None, None

    if trend not in ("UP", "DOWN"):
        return None, None, None

    if cfg.get("enable_candle_sequence", True):
        count = int(cfg.get("candle_sequence_count", 3))
        if not confirm_candle_sequence(df_closed, trend, count):
            return None, None, None

    if cfg.get("enable_smc"):
        bos = detect_bos(df_closed)
        if (trend == "UP" and bos == "BULLISH_BOS") or \
           (trend == "DOWN" and bos == "BEARISH_BOS"):
            return trend, "SMC", rr_default

    if cfg.get("enable_fvg", True):
        if detect_fvg(df_closed, trend):
            return trend, "FVG", rr_default

    if cfg.get("enable_price_action"):
        pa = detect_price_action(df_closed)
        if pa:
            if trend == "UP" and "BULL" in pa:
                return "UP", "PRICE_ACTION", rr_default
            if trend == "DOWN" and "BEAR" in pa:
                return "DOWN", "PRICE_ACTION", rr_default

    return None, None, None


# ============================================================
#                      ربات زنده
# ============================================================
class TradingBot(threading.Thread):
    def __init__(self, config, log_callback):
        super().__init__(daemon=True)
        self.cfg = config
        self.log = log_callback
        self._stop_flag = threading.Event()
        self.iran_tz = pytz.timezone("Asia/Tehran")
        self.daily_start_balance = None
        self.last_reset_date = None
        self.bot_halted = False
        self.peak_profit = {}
        self.partial_levels = {}
        self.last_trend = None
        self.active_tickets = set()
        self.connected = False
        self.loss_alerted = {}

    def _log(self, msg, level="info"):
        stamp = datetime.now(self.iran_tz).strftime("%H:%M:%S")
        self.log(f"[{stamp}] {msg}", level)

    def _send_telegram(self, text):
        if not self.cfg.get("enable_telegram"):
            return
        token = self.cfg.get("telegram_bot_token", "").strip()
        chat = self.cfg.get("telegram_chat_id", "").strip()
        if not token or not chat:
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={
                "chat_id": chat, "text": text, "parse_mode": "HTML"
            }, timeout=8)
        except Exception as e:
            self._log(f"خطای تلگرام: {e}", "warn")

    def _get_iran_time(self):
        return datetime.now(pytz.utc).astimezone(self.iran_tz)

    def _is_trading_hours(self):
        now = self._get_iran_time()
        start = now.replace(hour=self.cfg["trading_start_hour"],
                            minute=self.cfg["trading_start_min"],
                            second=0, microsecond=0)
        end = now.replace(hour=self.cfg["trading_end_hour"],
                          minute=self.cfg["trading_end_min"],
                          second=0, microsecond=0)
        return start <= now <= end

    def _ensure_connection(self, symbol):
        if self.connected and MT5_AVAILABLE:
            try:
                if mt5.terminal_info() is not None:
                    return True
            except Exception:
                pass
        ok, msg = mt5_attach(symbol)
        if ok:
            self.connected = True
            for line in msg.split("\n"):
                self._log(line, "success")
        else:
            self._log(msg, "error")
        return ok

    def _get_rates(self, symbol, tf, count=600):
        rates = mt5.copy_rates_from_pos(symbol, TF_MAP[tf], 0, count)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def _current_price(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None, None
        return tick.bid, tick.ask

    def _calc_sl_tp(self, entry, direction, atr_value, rr):
        sl_d = atr_value * float(self.cfg["atr_multiplier"])
        tp_d = sl_d * float(rr)
        if direction == "BUY":
            return entry - sl_d, entry + tp_d
        return entry + sl_d, entry - tp_d

    def _calc_lot_for_max_loss(self, symbol, sl_distance):
        configured = float(self.cfg["lot_size"])
        try:
            max_loss = float(self.cfg.get("max_loss_per_trade", 0.0) or 0.0)
        except (TypeError, ValueError):
            max_loss = 0.0

        if max_loss <= 0 or sl_distance <= 0:
            return configured

        info = mt5.symbol_info(symbol)
        if info is None:
            return configured

        tick_size = float(getattr(info, "trade_tick_size", 0) or 0)
        tick_value = float(getattr(info, "trade_tick_value", 0) or 0)
        contract = float(getattr(info, "trade_contract_size", 0) or 0)
        step = float(getattr(info, "volume_step", 0.01) or 0.01)
        min_lot = float(getattr(info, "volume_min", 0.01) or 0.01)
        max_lot = float(getattr(info, "volume_max", 100.0) or 100.0)

        if tick_size > 0 and tick_value > 0:
            gross_loss_per_lot = (sl_distance / tick_size) * tick_value
        elif contract > 0:
            gross_loss_per_lot = sl_distance * contract
        else:
            return configured

        if gross_loss_per_lot <= 0:
            return configured

        try:
            est_comm_per_lot = float(self.cfg.get("commission_per_lot", 7.0) or 7.0)
        except (TypeError, ValueError):
            est_comm_per_lot = 7.0

        total_loss_per_lot = gross_loss_per_lot + 2.0 * est_comm_per_lot
        calc_lot = max_loss / total_loss_per_lot

        if step > 0:
            calc_lot = np.floor(calc_lot / step) * step
        calc_lot = round(calc_lot, 4)

        if calc_lot < min_lot:
            required = min_lot * total_loss_per_lot
            strict = bool(self.cfg.get("strict_max_loss", True))
            msg = (
                f"⚠️ نماد {symbol}: با SL={sl_distance:.2f} و min_lot={min_lot}، "
                f"حداقل ضرر {required:.2f}$ می‌شود (سقف فعلی: {max_loss:.2f}$). "
                f"راه‌حل: max_loss را حداقل {required:.2f}$ کنید، "
                f"atr_multiplier را کم کنید، یا حالت سخت‌گیرانه را بردارید."
            )
            if strict:
                self._log("⛔ " + msg, "warn")
                return None
            else:
                self._log(msg + " → اجرا با min_lot", "warn")
                return min_lot

        calc_lot = min(max_lot, calc_lot)
        calc_lot = min(calc_lot, configured)
        return calc_lot

    def _place_orders(self, symbol, trend, df, rr=None, max_new_orders=None):
        bid, ask = self._current_price(symbol)
        if bid is None:
            return []
        if rr is None:
            rr = float(self.cfg["risk_reward"])
        atr_value = calc_atr(df)
        stop_dists = [float(x) for x in str(self.cfg["stop_distances"]).split(",") if x.strip()]
        limit_dists = [float(x) for x in str(self.cfg["limit_distances"]).split(",") if x.strip()]

        sl_distance = atr_value * float(self.cfg["atr_multiplier"])
        lot = self._calc_lot_for_max_loss(symbol, sl_distance)
        if lot is None:
            self._log("سیگنال به‌دلیل عدم رعایت سقف ضرر هر معامله رد شد", "warn")
            return []

        placed = []

        if trend == "UP":
            orders = [(mt5.ORDER_TYPE_BUY_STOP, ask + d, "BUY", f"BUY_STOP_{d}")
                      for d in stop_dists] + \
                     [(mt5.ORDER_TYPE_BUY_LIMIT, bid - d, "BUY", f"BUY_LIMIT_{d}")
                      for d in limit_dists]
        else:
            orders = [(mt5.ORDER_TYPE_SELL_STOP, bid - d, "SELL", f"SELL_STOP_{d}")
                      for d in stop_dists] + \
                     [(mt5.ORDER_TYPE_SELL_LIMIT, ask + d, "SELL", f"SELL_LIMIT_{d}")
                      for d in limit_dists]

        if max_new_orders is not None and max_new_orders >= 0:
            orders = orders[:int(max_new_orders)]

        for otype, price, direction, comment in orders:
            sl, tp = self._calc_sl_tp(price, direction, atr_value, rr)
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol, "volume": lot, "type": otype,
                "price": round(price, 2), "sl": round(sl, 2),
                "tp": round(tp, 2), "deviation": 10, "magic": 202501,
                "comment": comment, "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                placed.append(res.order)
                self._log(f"سفارش ثبت شد: {comment} | {price:.2f} | "
                          f"حجم:{lot} | SL:{sl:.2f} | TP:{tp:.2f} (RR=1:{rr})",
                          "success")
                self._send_telegram(
                    f"📌 سفارش: <b>{comment}</b>\n"
                    f"💵 {price:.2f} | حجم {lot} | 🛑 {sl:.2f} | 🎯 {tp:.2f}")
            else:
                err = res.retcode if res else "None"
                self._log(f"خطا در {comment} | کد: {err}", "error")
        return placed

    def _cancel_all_pending(self, symbol):
        orders = mt5.orders_get(symbol=symbol)
        if not orders:
            return
        for o in orders:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        self._log(f"{len(orders)} سفارش معلق حذف شد", "warn")

    def _count_positions(self, symbol):
        p = mt5.positions_get(symbol=symbol)
        return len(p) if p else 0

    def _count_active_orders(self, symbol):
        pos = mt5.positions_get(symbol=symbol)
        orders = mt5.orders_get(symbol=symbol)
        npos = len(pos) if pos else 0
        norders = len(orders) if orders else 0
        return npos + norders

    def _reset_daily(self):
        today = self._get_iran_time().date()
        if self.last_reset_date != today:
            acc = mt5.account_info()
            if acc:
                self.daily_start_balance = acc.balance
            self.last_reset_date = today
            self.bot_halted = False
            self.peak_profit.clear()
            self.partial_levels.clear()
            self._log(f"ریست روزانه | موجودی: {self.daily_start_balance:.2f}")

    def _daily_pnl(self):
        acc = mt5.account_info()
        if not acc or self.daily_start_balance is None:
            return 0.0
        return acc.equity - self.daily_start_balance

    def _check_daily_limits(self):
        pnl = self._daily_pnl()
        if pnl >= float(self.cfg["max_daily_profit"]):
            self._log(f"✅ حد سود روزانه: {pnl:.2f}$", "success")
            self.bot_halted = True
            self._close_all_positions()
            return False
        if pnl <= -float(self.cfg["max_daily_loss"]):
            self._log(f"🛑 حد ضرر روزانه: {pnl:.2f}$", "error")
            self.bot_halted = True
            self._close_all_positions()
            return False
        return True

    def _close_all_positions(self):
        positions = mt5.positions_get()
        if not positions:
            return
        for p in positions:
            tick = mt5.symbol_info_tick(p.symbol)
            if p.type == mt5.POSITION_TYPE_BUY:
                price, otype = tick.bid, mt5.ORDER_TYPE_SELL
            else:
                price, otype = tick.ask, mt5.ORDER_TYPE_BUY
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol, "volume": p.volume, "type": otype,
                "position": p.ticket, "price": price, "deviation": 10,
                "magic": 202501, "comment": "close_all",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            })

    def _move_sl_to_breakeven(self, position):
        try:
            if position.type == mt5.POSITION_TYPE_BUY:
                new_sl = position.price_open
                if position.sl != 0 and new_sl <= position.sl:
                    return
            else:
                new_sl = position.price_open
                if position.sl != 0 and new_sl >= position.sl:
                    return
            mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": position.symbol,
                "position": position.ticket,
                "sl": round(new_sl, 2),
                "tp": position.tp,
            })
        except Exception as e:
            self._log(f"خطا در انتقال SL به BE: {e}", "warn")

    def _manage_partial_profit(self, symbol):
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return
        step = float(self.cfg.get("partial_profit_step", 0.0))
        frac = float(self.cfg.get("partial_profit_fraction", 0.5))
        if step <= 0 or frac <= 0 or frac >= 1.0:
            return
        for p in positions:
            cur = float(p.profit + p.swap)
            if cur <= 0:
                continue
            level = int(cur / step)
            last = int(self.partial_levels.get(p.ticket, 0))
            if level <= last:
                continue
            close_vol = round(float(p.volume) * frac, 2)
            if close_vol < 0.01:
                continue
            if close_vol >= p.volume:
                continue
            tick = mt5.symbol_info_tick(p.symbol)
            if tick is None:
                continue
            if p.type == mt5.POSITION_TYPE_BUY:
                price, otype = tick.bid, mt5.ORDER_TYPE_SELL
            else:
                price, otype = tick.ask, mt5.ORDER_TYPE_BUY
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol, "volume": close_vol, "type": otype,
                "position": p.ticket, "price": price, "deviation": 10,
                "magic": 202501, "comment": f"partial_{level}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            })
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                self.partial_levels[p.ticket] = level
                self._log(f"پله {level}: {close_vol} لات از {p.ticket} بسته شد "
                          f"(سود {cur:.2f}$)", "success")
                self._send_telegram(
                    f"💰 پله {level} | <b>{p.symbol}</b> | "
                    f"{close_vol} لات بسته شد | سود: {cur:.2f}$")
                pos_after = mt5.positions_get(ticket=p.ticket)
                if pos_after:
                    self._move_sl_to_breakeven(pos_after[0])

    def _manage_trailing_profit(self, symbol):
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return
        for p in positions:
            ticket = p.ticket
            cur = p.profit + p.swap
            self.peak_profit[ticket] = max(self.peak_profit.get(ticket, cur), cur)
            peak = self.peak_profit[ticket]
            drop = float(self.cfg["trailing_drop"])
            if peak > 0 and (peak - cur) >= drop:
                tick = mt5.symbol_info_tick(p.symbol)
                if p.type == mt5.POSITION_TYPE_BUY:
                    price, otype = tick.bid, mt5.ORDER_TYPE_SELL
                else:
                    price, otype = tick.ask, mt5.ORDER_TYPE_BUY
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": p.symbol, "volume": p.volume, "type": otype,
                    "position": p.ticket, "price": price, "deviation": 10,
                    "magic": 202501, "comment": "trailing_close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                })
                self._log(f"افت {drop}$ از سقف {peak:.2f}$ → بستن {ticket}", "warn")
                self.peak_profit.pop(ticket, None)
                self.partial_levels.pop(ticket, None)

    def _check_loss_alerts(self, symbol):
        """اگر ضرر یک پوزیشن باز از آستانه بیشتر شد، هشدار تلگرام ارسال می‌کند."""
        if not self.cfg.get("enable_loss_alert", True):
            return
        try:
            threshold = float(self.cfg.get("loss_alert_threshold", 10.0) or 10.0)
        except (TypeError, ValueError):
            threshold = 10.0
        if threshold <= 0:
            return

        positions = mt5.positions_get(symbol=symbol)
        active_tickets = set()
        if positions:
            for p in positions:
                active_tickets.add(p.ticket)
                cur = float(p.profit + p.swap)
                loss = -cur
                last_level = int(self.loss_alerted.get(p.ticket, 0))

                if loss >= threshold:
                    level = int(loss / threshold)
                    if level > last_level:
                        self.loss_alerted[p.ticket] = level
                        tick = mt5.symbol_info_tick(p.symbol)
                        if tick is None:
                            cur_price = 0.0
                        else:
                            cur_price = (tick.bid
                                         if p.type == mt5.POSITION_TYPE_BUY
                                         else tick.ask)
                        side = ("BUY" if p.type == mt5.POSITION_TYPE_BUY
                                else "SELL")
                        self._log(
                            f"⚠️ هشدار ضرر | {p.symbol} | تیکت {p.ticket} | "
                            f"{side} | ضرر: {loss:.2f}$", "warn")
                        self._send_telegram(
                            "⚠️ <b>هشدار ضرر معامله باز</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"💱 <b>نماد:</b> <code>{p.symbol}</code>\n"
                            f"🎫 <b>تیکت:</b> {p.ticket}\n"
                            f"📊 <b>نوع:</b> {side}\n"
                            f"📦 <b>حجم:</b> {p.volume}\n"
                            f"🎯 <b>قیمت ورود:</b> {p.price_open:.2f}\n"
                            f"💵 <b>قیمت فعلی:</b> {cur_price:.2f}\n"
                            f"🛑 <b>SL:</b> {p.sl:.2f}\n"
                            f"🔴 <b>ضرر فعلی:</b> {loss:.2f}$\n"
                            f"📈 <b>سطح هشدار:</b> {level} (×{threshold:.0f}$)\n"
                            "━━━━━━━━━━━━━━━━━━━━"
                        )
                else:
                    if p.ticket in self.loss_alerted:
                        self.loss_alerted[p.ticket] = 0

        for t in list(self.loss_alerted.keys()):
            if t not in active_tickets:
                self.loss_alerted.pop(t, None)

    def _send_startup_telegram(self, symbol):
        if not self.cfg.get("enable_telegram"):
            return
        token = self.cfg.get("telegram_bot_token", "").strip()
        chat = self.cfg.get("telegram_chat_id", "").strip()
        if not token or not chat:
            return

        broker = "—"
        balance = 0.0
        currency = ""
        acc_login = "—"
        try:
            acc = mt5.account_info()
            if acc:
                broker = acc.server
                balance = acc.balance
                currency = acc.currency
                acc_login = acc.login
        except Exception:
            pass

        try:
            daily_pnl = self._daily_pnl()
        except Exception:
            daily_pnl = 0.0

        pnl_emoji = "🟢" if daily_pnl >= 0 else "🔴"
        daily_txt = f"{daily_pnl:+.2f} {currency}".strip()

        sh = int(self.cfg.get("trading_start_hour", 0))
        sm = int(self.cfg.get("trading_start_min", 0))
        eh = int(self.cfg.get("trading_end_hour", 23))
        em = int(self.cfg.get("trading_end_min", 59))
        trading_hours = f"{sh:02d}:{sm:02d} تا {eh:02d}:{em:02d} (ایران)"

        strategies = []
        if self.cfg.get("enable_smc"):
            strategies.append("SMC (BOS)")
        if self.cfg.get("enable_fvg"):
            strategies.append("FVG")
        if self.cfg.get("enable_price_action"):
            strategies.append("Price Action")

        if strategies:
            strat_txt = " • ".join(strategies)
        else:
            strat_txt = "منطق اصلی (Main — روند + توالی کندل + FVG)"

        text = (
            "🚀 <b>ربات معامله‌گر آویژه شروع به کار کرد</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>طراحی و توسعه:</b> مهدی زارع\n"
            "📧 <b>ایمیل:</b> MehdiZare@Outlook.com\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💱 <b>نماد معامله:</b> <code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم:</b> {self.cfg.get('timeframe', '—')}\n"
            f"🏦 <b>نام بروکر:</b> {broker}\n"
            f"👤 <b>شماره حساب:</b> {acc_login}\n"
            f"💰 <b>موجودی حساب:</b> {balance:.2f} {currency}\n"
            f"{pnl_emoji} <b>سود/زیان روزانه:</b> {daily_txt}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 <b>ساعت معاملات:</b> {trading_hours}\n"
            f"🎯 <b>استراتژی:</b> {strat_txt}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={
                "chat_id": chat,
                "text": text,
                "parse_mode": "HTML"
            }, timeout=8)
        except Exception as e:
            self._log(f"خطای ارسال پیام شروع به تلگرام: {e}", "warn")

    def run(self):
        symbol = self.cfg["symbol"]
        self._log("اتصال خودکار به متاتریدر ...", "info")
        if not self._ensure_connection(symbol):
            self._log("اتصال ناموفق — ربات متوقف شد", "error")
            return

        self._reset_daily()
        self._log(f"🚀 ربات شروع به کار کرد | {symbol} | {self.cfg['timeframe']}", "success")
        self._send_startup_telegram(symbol)

        try:
            while not self._stop_flag.is_set():
                if not self._ensure_connection(symbol):
                    time.sleep(10)
                    continue

                self._reset_daily()

                try:
                    self._manage_partial_profit(symbol)
                    self._manage_trailing_profit(symbol)
                except Exception:
                    pass

                try:
                    self._check_loss_alerts(symbol)
                except Exception as e:
                    self._log(f"خطا در بررسی هشدار ضرر: {e}", "warn")

                if self.bot_halted:
                    time.sleep(30); continue
                if not self._is_trading_hours():
                    time.sleep(20); continue
                if not self._check_daily_limits():
                    time.sleep(30); continue

                df = self._get_rates(symbol, self.cfg["timeframe"], 600)
                if df.empty:
                    time.sleep(5); continue

                trend = detect_trend(df, self.cfg.get("enable_adx", True),
                                     self.cfg.get("adx_period", 14),
                                     self.cfg.get("adx_threshold", 20.0))
                trend_htf = trend
                if self.cfg.get("enable_higher_tf_confirm"):
                    df_htf = self._get_rates(symbol, self.cfg["timeframe_higher"], 300)
                    if not df_htf.empty:
                        trend_htf = detect_trend(df_htf, self.cfg.get("enable_adx", True),
                                              self.cfg.get("adx_period", 14),
                                              self.cfg.get("adx_threshold", 20.0))

                adx_info = calc_adx(df, self.cfg.get("adx_period", 14))
                adx_txt = (
                    f"ADX={adx_info['adx']:.1f} | +DI={adx_info['plus_di']:.1f} | "
                    f"-DI={adx_info['minus_di']:.1f}"
                    if np.isfinite(adx_info["adx"]) else "ADX=—"
                )
                self._log(f"روند {self.cfg['timeframe']}: {trend} | HTF: {trend_htf} | {adx_txt}")

                closed_df = df.iloc[:-1] if len(df) > 1 else df

                signal_dir, signal_strategy, signal_rr = \
                    evaluate_strategies(closed_df, trend, self.cfg)

                if signal_dir is None:
                    time.sleep(5); continue

                if (self.cfg.get("enable_higher_tf_confirm")
                        and signal_strategy in ("SMC", "FVG", "PRICE_ACTION", "MAIN_FVG")):
                    if trend != trend_htf:
                        time.sleep(5); continue

                max_orders = int(self.cfg.get("max_simultaneous_orders", 2))
                current = self._count_active_orders(symbol)
                if current >= max_orders:
                    time.sleep(5); continue
                remaining = max_orders - current

                self._log(
                    f"✅ سیگنال [{signal_strategy}]: {signal_dir} | "
                    f"RR=1:{signal_rr} | ظرفیت: {remaining}", "success")

                self._place_orders(symbol, signal_dir, df,
                                   rr=signal_rr, max_new_orders=remaining)

                self._manage_partial_profit(symbol)
                self._manage_trailing_profit(symbol)

                cur_pos = mt5.positions_get(symbol=symbol)
                cur_tickets = {p.ticket for p in cur_pos} if cur_pos else set()
                closed = self.active_tickets - cur_tickets
                for t in closed:
                    hist = mt5.history_deals_get(position=t)
                    if hist:
                        profit = sum(d.profit + d.swap + d.commission for d in hist)
                        self._log(f"پوزیشن {t} بسته شد: {profit:.2f}$")
                    self._cancel_all_pending(symbol)
                    self.partial_levels.pop(t, None)
                    self.peak_profit.pop(t, None)
                self.active_tickets = cur_tickets
                self.last_trend = trend
                time.sleep(int(self.cfg.get("loop_interval_sec", 10)))

        except Exception as e:
            self._log(f"خطای غیرمنتظره: {e}", "error")
            traceback.print_exc()
        finally:
            try:
                self._cancel_all_pending(symbol)
            except Exception:
                pass
            self.connected = False
            self._log("⏹ ربات متوقف شد", "warn")
            self._send_telegram("⏹ ربات متوقف شد")

    def stop(self):
        self._stop_flag.set()


# ============================================================
#                      بک‌تست
# ============================================================
class Backtester:
    def __init__(self, cfg, log_callback=None):
        self.cfg = cfg
        self.log = log_callback or (lambda m, l="info": print(m))
        self.iran_tz = pytz.timezone("Asia/Tehran")
        self._skip_count = 0

    def _get_rates(self, symbol, tf, start, end):
        rates = mt5.copy_rates_range(symbol, TF_MAP[tf], start, end)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df.reset_index(drop=True)

    def _get_broker_costs(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"spread": 0.0002, "contract": 1.0, "commission_per_lot": 7.0}
        spread = info.spread * info.point if info.spread else info.point * 2
        return {"spread": spread, "contract": info.trade_contract_size,
                "commission_per_lot": self._estimate_commission(symbol)}

    def _estimate_commission(self, symbol):
        try:
            from_dt = datetime.now() - timedelta(days=30)
            deals = mt5.history_deals_get(from_dt, datetime.now(),
                                          group=f"*{symbol}*")
            if not deals:
                return 7.0
            tc = sum(d.commission for d in deals if d.commission)
            tv = sum(d.volume for d in deals if d.volume)
            if tv > 0:
                return abs(tc / tv)
        except Exception:
            pass
        return 7.0

    def _calc_lot_for_max_loss(self, symbol, sl_distance, default_lot,
                               contract, comm_per_lot):
        try:
            max_loss = float(self.cfg.get("max_loss_per_trade", 0.0) or 0.0)
        except (TypeError, ValueError):
            max_loss = 0.0

        if max_loss <= 0 or sl_distance <= 0 or contract <= 0:
            return default_lot

        gross_loss_per_lot = sl_distance * contract
        total_loss_per_lot = gross_loss_per_lot + 2.0 * float(comm_per_lot or 0.0)
        if total_loss_per_lot <= 0:
            return default_lot

        calc_lot = max_loss / total_loss_per_lot

        step, min_lot, max_lot = 0.01, 0.01, 100.0
        info = mt5.symbol_info(symbol)
        if info is not None:
            step = float(getattr(info, "volume_step", 0.01) or 0.01)
            min_lot = float(getattr(info, "volume_min", 0.01) or 0.01)
            max_lot = float(getattr(info, "volume_max", 100.0) or 100.0)

        if step > 0:
            calc_lot = np.floor(calc_lot / step) * step
        calc_lot = round(calc_lot, 4)

        if calc_lot < min_lot:
            strict = bool(self.cfg.get("strict_max_loss", True))
            if strict:
                self._skip_count += 1
                return None
            else:
                return min_lot

        calc_lot = min(max_lot, calc_lot)
        return min(calc_lot, default_lot)

    def run(self, symbol, start_dt, end_dt, initial_balance=1000.0,
            progress_callback=None):

        def _progress(p, msg=""):
            if progress_callback:
                progress_callback(p, msg)

        if not MT5_AVAILABLE:
            self.log("MetaTrader5 در دسترس نیست", "error")
            return None

        self._skip_count = 0
        _progress(2, "اتصال به متاتریدر ...")
        ok, msg = mt5_attach(symbol)
        if not ok:
            self.log(msg, "error")
            return None

        _progress(4, "دریافت داده ...")
        df = self._get_rates(symbol, self.cfg["timeframe"], start_dt, end_dt)
        if df.empty:
            self.log("داده تاریخی یافت نشد", "error")
            return None
        self.log(f"{len(df)} کندل دریافت شد")

        df_htf = pd.DataFrame()
        if self.cfg.get("enable_higher_tf_confirm"):
            _progress(6, "دریافت HTF ...")
            df_htf = self._get_rates(symbol, self.cfg["timeframe_higher"],
                                     start_dt, end_dt)

        _progress(8, "خواندن اسپرد/کمیسیون ...")
        costs = self._get_broker_costs(symbol)

        default_lot = float(self.cfg["lot_size"])
        atr_mult = float(self.cfg["atr_multiplier"])
        stop_dists = [float(x) for x in str(self.cfg["stop_distances"]).split(",") if x.strip()]
        limit_dists = [float(x) for x in str(self.cfg["limit_distances"]).split(",") if x.strip()]
        spread = costs["spread"]
        contract = costs["contract"]
        comm_per_lot = costs["commission_per_lot"]
        max_sim = int(self.cfg.get("max_simultaneous_orders", 2))

        partial_step = float(self.cfg.get("partial_profit_step", 0.0))
        partial_frac = float(self.cfg.get("partial_profit_fraction", 0.5))
        use_partial = partial_step > 0 and 0 < partial_frac < 1.0

        trades = []
        balance = initial_balance
        start_h = int(self.cfg["trading_start_hour"])
        start_m = int(self.cfg["trading_start_min"])
        end_h = int(self.cfg["trading_end_hour"])
        end_m = int(self.cfg["trading_end_min"])

        i = 60
        total_bars = len(df)
        last_progress = 0

        while i < total_bars - 1:
            p = 10 + int((i / total_bars) * 80)
            if p != last_progress and p % 5 == 0:
                _progress(p, f"کندل {i}/{total_bars}")
                last_progress = p

            bar_time = df.iloc[i]['time']
            try:
                iran_dt = pytz.utc.localize(bar_time).astimezone(self.iran_tz)
            except Exception:
                iran_dt = bar_time
            hm = iran_dt.hour * 60 + iran_dt.minute
            if not (start_h * 60 + start_m <= hm <= end_h * 60 + end_m):
                i += 1; continue

            window = df.iloc[:i + 1]
            trend = detect_trend(window, self.cfg.get("enable_adx", True),
                                  self.cfg.get("adx_period", 14),
                                  self.cfg.get("adx_threshold", 20.0))

            signal_dir, signal_strategy, signal_rr = \
                evaluate_strategies(window, trend, self.cfg)

            if signal_dir is None:
                i += 1; continue

            if (self.cfg.get("enable_higher_tf_confirm") and not df_htf.empty
                    and signal_strategy in ("SMC", "FVG", "PRICE_ACTION", "MAIN_FVG")):
                htf_window = df_htf[df_htf['time'] <= bar_time]
                if len(htf_window) >= 60:
                    if detect_trend(htf_window, self.cfg.get("enable_adx", True),
                                    self.cfg.get("adx_period", 14),
                                    self.cfg.get("adx_threshold", 20.0)) != signal_dir:
                        i += 1; continue

            trend = signal_dir
            atr = calc_atr(window)
            signal_time = bar_time
            ref_close = df.iloc[i]['close']
            ask = ref_close + spread / 2
            bid = ref_close - spread / 2

            orders = []
            if trend == "UP":
                for d in stop_dists:
                    pr = ask + d
                    orders.append({"kind": "BUY_STOP", "price": pr,
                                   "sl": pr - atr * atr_mult,
                                   "tp": pr + atr * atr_mult * signal_rr})
                for d in limit_dists:
                    pr = bid - d
                    orders.append({"kind": "BUY_LIMIT", "price": pr,
                                   "sl": pr - atr * atr_mult,
                                   "tp": pr + atr * atr_mult * signal_rr})
            else:
                for d in stop_dists:
                    pr = bid - d
                    orders.append({"kind": "SELL_STOP", "price": pr,
                                   "sl": pr + atr * atr_mult,
                                   "tp": pr - atr * atr_mult * signal_rr})
                for d in limit_dists:
                    pr = ask + d
                    orders.append({"kind": "SELL_LIMIT", "price": pr,
                                   "sl": pr + atr * atr_mult,
                                   "tp": pr - atr * atr_mult * signal_rr})

            orders = orders[:max_sim]
            active = []
            filled = 0
            last_exit_bar = i

            sl_distance = atr * atr_mult
            signal_lot = self._calc_lot_for_max_loss(
                symbol, sl_distance, default_lot, contract, comm_per_lot)
            if signal_lot is None:
                i += 1; continue

            for o in orders:
                o["lot"] = signal_lot
                o["closed_vol"] = 0.0
                o["partial_level"] = 0
                o["be_moved"] = False

            for j in range(i + 1, total_bars):
                bar = df.iloc[j]
                bh, bl = bar['high'], bar['low']
                for o in orders:
                    if o.get("status", "pending") != "pending":
                        continue
                    k = o["kind"]; trig = False
                    if k == "BUY_STOP" and bh >= o["price"]: trig = True
                    elif k == "BUY_LIMIT" and bl <= o["price"]: trig = True
                    elif k == "SELL_STOP" and bl <= o["price"]: trig = True
                    elif k == "SELL_LIMIT" and bh >= o["price"]: trig = True
                    if trig:
                        o["status"] = "active"
                        o["entry"] = o["price"]
                        o["entry_time"] = bar['time']
                        active.append(o); filled += 1

                if filled >= max_sim:
                    for o in orders:
                        if o.get("status", "pending") == "pending":
                            o["status"] = "cancelled"

                for p2 in active[:]:
                    is_buy = p2["kind"].startswith("BUY")
                    p_lot = float(p2.get("lot", default_lot))

                    if use_partial:
                        best = bh if is_buy else bl
                        cur_pts = (best - p2["entry"]) if is_buy else (p2["entry"] - best)
                        cur_profit_total = cur_pts * contract * p_lot
                        level = int(cur_profit_total / partial_step) if cur_profit_total > 0 else 0
                        if level > p2["partial_level"]:
                            close_vol = round(p_lot * partial_frac, 2)
                            if close_vol >= 0.01 and (p2["closed_vol"] + close_vol) < p_lot:
                                if is_buy:
                                    exit_price = p2["entry"] + level * partial_step / (contract * p_lot)
                                else:
                                    exit_price = p2["entry"] - level * partial_step / (contract * p_lot)
                                pts = (exit_price - p2["entry"]) if is_buy else (p2["entry"] - exit_price)
                                gross = pts * contract * close_vol
                                comm = comm_per_lot * close_vol * 2
                                net = gross - comm
                                trades.append({
                                    "signal_time": signal_time,
                                    "entry_time": p2["entry_time"],
                                    "exit_time": bar['time'],
                                    "type": p2["kind"] + f"_partial{level}",
                                    "entry": p2["entry"], "exit": exit_price,
                                    "sl": p2["sl"], "tp": p2["tp"],
                                    "profit": net, "reason": f"PARTIAL_{level}",
                                })
                                balance += net
                                p2["closed_vol"] += close_vol
                                p2["partial_level"] = level
                                if not p2["be_moved"]:
                                    p2["sl"] = p2["entry"]
                                    p2["be_moved"] = True

                    remaining_vol = round(p_lot - p2.get("closed_vol", 0.0), 2)
                    if remaining_vol < 0.01:
                        p2["status"] = "closed"
                        if p2 in active:
                            active.remove(p2)
                        last_exit_bar = j
                        continue

                    ex = None; reason = None
                    if is_buy:
                        if bl <= p2["sl"]: ex, reason = p2["sl"], "SL"
                        elif bh >= p2["tp"]: ex, reason = p2["tp"], "TP"
                    else:
                        if bh >= p2["sl"]: ex, reason = p2["sl"], "SL"
                        elif bl <= p2["tp"]: ex, reason = p2["tp"], "TP"
                    if ex is not None:
                        pts = (ex - p2["entry"]) if is_buy else (p2["entry"] - ex)
                        gross = pts * contract * remaining_vol
                        comm = comm_per_lot * remaining_vol * 2
                        net = gross - comm
                        trades.append({
                            "signal_time": signal_time,
                            "entry_time": p2["entry_time"],
                            "exit_time": bar['time'],
                            "type": p2["kind"],
                            "entry": p2["entry"], "exit": ex,
                            "sl": p2["sl"], "tp": p2["tp"],
                            "profit": net, "reason": reason,
                        })
                        balance += net
                        p2["status"] = "closed"
                        active.remove(p2)
                        last_exit_bar = j

                all_done = all(o.get("status", "pending") not in ("pending", "active")
                               for o in orders)
                if all_done and not active:
                    break

            i = max(last_exit_bar + 1, i + 1)

        if self._skip_count > 0:
            self.log(
                f"⚠️ {self._skip_count} سیگنال به‌دلیل عدم رعایت سقف ضرر "
                f"(min_lot بزرگ‌تر از حد مجاز) رد شد.", "warn")

        _progress(95, "ساخت گزارش ...")
        report = self._build_report(trades, initial_balance, balance)
        _progress(100, "کامل شد")
        return report

    def _build_report(self, trades, initial_balance, final_balance):
        if not trades:
            return self._empty_report(initial_balance)
        df = pd.DataFrame(trades)
        df['exit_time'] = pd.to_datetime(df['exit_time'])
        df = df.sort_values('exit_time').reset_index(drop=True)
        wins = df[df['profit'] > 0]
        losses = df[df['profit'] <= 0]
        total_trades = len(df)
        win_rate = (len(wins) / total_trades * 100) if total_trades else 0
        gross_win = wins['profit'].sum() if len(wins) else 0.0
        gross_loss = abs(losses['profit'].sum()) if len(losses) else 0.0
        net_profit = final_balance - initial_balance
        pf = (gross_win / gross_loss) if gross_loss > 0 else 9999.0

        equity_curve = [initial_balance]
        for p in df['profit']:
            equity_curve.append(equity_curve[-1] + p)
        peak = initial_balance; max_dd = 0.0; max_dd_pct = 0.0
        for eq in equity_curve[1:]:
            peak = max(peak, eq)
            dd = peak - eq
            max_dd = max(max_dd, dd)
            max_dd_pct = max(max_dd_pct, dd / peak * 100 if peak > 0 else 0)

        returns = df['profit'].values / initial_balance
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns, ddof=1)) * np.sqrt(len(returns))
        else:
            sharpe = 0.0
        dn = returns[returns < 0]
        if len(dn) > 1 and np.std(dn, ddof=1) > 0:
            sortino = (np.mean(returns) / np.std(dn, ddof=1)) * np.sqrt(len(returns))
        else:
            sortino = 0.0
        calmar = (net_profit / max_dd) if max_dd > 0 else 0.0
        avg_win = wins['profit'].mean() if len(wins) else 0.0
        avg_loss = abs(losses['profit'].mean()) if len(losses) else 0.0
        pw = len(wins) / total_trades if total_trades else 0
        expectancy = (pw * avg_win) - ((1 - pw) * avg_loss)
        recovery = (net_profit / max_dd) if max_dd > 0 else 0.0

        mcw = mcl = cw = cl = 0
        for p in df['profit']:
            if p > 0:
                cw += 1; cl = 0; mcw = max(mcw, cw)
            else:
                cl += 1; cw = 0; mcl = max(mcl, cl)

        monthly = {}
        df['month'] = df['exit_time'].dt.strftime("%Y-%m")
        for m, g in df.groupby('month'):
            gw = g[g['profit'] > 0]; gl = g[g['profit'] <= 0]
            monthly[m] = {"trades": len(g), "wins": len(gw),
                          "losses": len(gl),
                          "profit": float(g['profit'].sum()),
                          "win_rate": (len(gw) / len(g) * 100) if len(g) else 0}

        tl = df.drop(columns=['month'], errors='ignore').to_dict(orient='records')
        for t in tl:
            for k in ('entry_time', 'exit_time', 'signal_time'):
                if k in t and pd.notna(t[k]):
                    t[k] = str(t[k])

        return {
            "total_trades": total_trades, "wins": int(len(wins)),
            "losses": int(len(losses)), "win_rate": float(win_rate),
            "initial_balance": float(initial_balance),
            "final_balance": float(final_balance),
            "total_profit": float(net_profit),
            "gross_profit": float(gross_win), "gross_loss": float(gross_loss),
            "profit_factor": float(pf), "max_dd": float(max_dd),
            "max_dd_pct": float(max_dd_pct), "sharpe": float(sharpe),
            "sortino": float(sortino), "calmar": float(calmar),
            "expectancy": float(expectancy), "avg_win": float(avg_win),
            "avg_loss": float(avg_loss), "recovery_factor": float(recovery),
            "max_consec_win": int(mcw), "max_consec_loss": int(mcl),
            "trades": tl, "monthly": monthly,
            "equity_curve": equity_curve,
        }

    def _empty_report(self, ib):
        return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "initial_balance": ib, "final_balance": ib, "total_profit": 0.0,
                "gross_profit": 0.0, "gross_loss": 0.0, "profit_factor": 0.0,
                "max_dd": 0.0, "max_dd_pct": 0.0, "sharpe": 0.0, "sortino": 0.0,
                "calmar": 0.0, "expectancy": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "recovery_factor": 0.0, "max_consec_win": 0, "max_consec_loss": 0,
                "trades": [], "monthly": {}, "equity_curve": [ib]}


# ============================================================
#                    بهینه‌ساز
# ============================================================
class GridOptimizer(threading.Thread):
    def __init__(self, base_cfg, symbol, start_dt, end_dt, initial_balance,
                 param_grid, objective="profit_factor", min_trades=10,
                 progress_callback=None, log_callback=None, result_callback=None):
        super().__init__(daemon=True)
        self.base_cfg = dict(base_cfg); self.symbol = symbol
        self.start_dt = start_dt; self.end_dt = end_dt
        self.initial_balance = initial_balance
        self.param_grid = param_grid; self.objective = objective
        self.min_trades = min_trades
        self.progress_callback = progress_callback or (lambda p, m: None)
        self.log_callback = log_callback or (lambda m, l="info": None)
        self.result_callback = result_callback or (lambda r: None)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _combinations(self):
        keys = list(self.param_grid.keys())
        for combo in itertools.product(*[self.param_grid[k] for k in keys]):
            yield dict(zip(keys, combo))

    def _score(self, r):
        if r is None or r["total_trades"] < self.min_trades:
            return -1e9
        return {"profit_factor": r.get("profit_factor", 0),
                "sharpe": r.get("sharpe", 0),
                "calmar": r.get("calmar", 0),
                "net_profit": r.get("total_profit", 0)}.get(
                    self.objective, r.get("profit_factor", 0))

    def run(self):
        combos = list(self._combinations())
        total = len(combos)
        self.log_callback(f"شروع: {total} ترکیب")
        results = []; best = None; best_score = -1e18
        for idx, combo in enumerate(combos):
            if self._stop.is_set():
                break
            cfg = dict(self.base_cfg); cfg.update(combo)
            p = int((idx / total) * 100)
            s = " | ".join(f"{k}={v}" for k, v in combo.items())
            self.progress_callback(p, f"[{idx+1}/{total}] {s}")
            bt = Backtester(cfg, log_callback=lambda m, l="info": None)
            try:
                rep = bt.run(self.symbol, self.start_dt, self.end_dt,
                             initial_balance=self.initial_balance)
            except Exception as e:
                self.log_callback(f"خطا {idx+1}: {e}", "error"); rep = None
            if rep is None:
                continue
            score = self._score(rep)
            row = dict(combo)
            row.update({"score": score, "trades": rep["total_trades"],
                        "win_rate": rep["win_rate"],
                        "net_profit": rep["total_profit"],
                        "profit_factor": rep["profit_factor"],
                        "sharpe": rep.get("sharpe", 0),
                        "max_dd": rep.get("max_dd", 0)})
            results.append(row)
            if score > best_score:
                best_score = score
                best = {"combo": combo, "report": rep, "score": score}
        self.progress_callback(100, "کامل شد")
        df_res = pd.DataFrame(results)
        if not df_res.empty:
            df_res = df_res.sort_values("score", ascending=False).reset_index(drop=True)
        self.result_callback({"best": best, "table": df_res,
                              "objective": self.objective,
                              "combinations_tested": len(results)})


# ============================================================
#                    تلگرام
# ============================================================
class TelegramNotifier:
    def __init__(self, token, chat_id, enabled=True):
        self.token = token; self.chat_id = chat_id
        self.enabled = enabled and bool(token) and bool(chat_id)

    def _api(self, m):
        return f"https://api.telegram.org/bot{self.token}/{m}"

    def send_message(self, text):
        if not self.enabled: return
        try:
            requests.post(self._api("sendMessage"),
                          json={"chat_id": self.chat_id, "text": text,
                                "parse_mode": "HTML"}, timeout=15)
        except Exception as e:
            print(f"tg: {e}")

    def send_photo(self, path, cap=""):
        if not self.enabled or not os.path.exists(path): return
        try:
            with open(path, "rb") as f:
                requests.post(self._api("sendPhoto"),
                              data={"chat_id": self.chat_id, "caption": cap,
                                    "parse_mode": "HTML"},
                              files={"photo": f}, timeout=30)
        except Exception as e:
            print(f"tg photo: {e}")

    def send_document(self, path, cap=""):
        if not self.enabled or not os.path.exists(path): return
        try:
            with open(path, "rb") as f:
                requests.post(self._api("sendDocument"),
                              data={"chat_id": self.chat_id, "caption": cap,
                                    "parse_mode": "HTML"},
                              files={"document": f}, timeout=60)
        except Exception as e:
            print(f"tg doc: {e}")

    def send_backtest_report(self, r, image_path=None, pdf_path=None, csv_path=None):
        if not self.enabled: return
        msg = (
            "📊 <b>گزارش بک‌تست</b>\n\n"
            f"🔢 معاملات: <b>{r['total_trades']}</b>\n"
            f"✅ {r['wins']} | ❌ {r['losses']}\n"
            f"🎯 وین‌ریت: <b>{r['win_rate']:.2f}%</b>\n"
            f"💰 {r['initial_balance']:.2f}$ → {r['final_balance']:.2f}$\n"
            f"📈 سود: <b>{r['total_profit']:+.2f}$</b>\n"
            f"📉 DD: <b>{r.get('max_dd', 0):.2f}$</b>\n"
            f"📐 PF: <b>{r['profit_factor']:.2f}</b>")
        self.send_message(msg)
        if image_path: self.send_photo(image_path, "🖼 گزارش")
        if pdf_path: self.send_document(pdf_path, "📄 PDF")
        if csv_path: self.send_document(csv_path, "📑 CSV")


# ============================================================
#                    PDF/تصویر
# ============================================================
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_FA = True
except ImportError:
    _HAS_FA = False
    print("⚠️ برای نمایش صحیح متن فارسی در نمودارها نصب کنید:")
    print("   pip install arabic-reshaper python-bidi")


def _setup_persian_matplotlib():
    try:
        from matplotlib import font_manager
        candidates = [
            resource_path("fonts/Vazirmatn-Regular.ttf"),
            "C:/Windows/Fonts/tahoma.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        chosen = None
        for path in candidates:
            if os.path.exists(path):
                try:
                    font_manager.fontManager.addfont(path)
                    chosen = font_manager.FontProperties(fname=path).get_name()
                    break
                except Exception:
                    continue
        if chosen:
            matplotlib.rcParams['font.family'] = chosen
        matplotlib.rcParams['axes.unicode_minus'] = False
    except Exception:
        pass


_setup_persian_matplotlib()


def _fa(t):
    if not _HAS_FA:
        return str(t)
    try:
        return get_display(arabic_reshaper.reshape(str(t)))
    except Exception:
        return str(t)


def render_report_image(report, output_path="report.png"):
    matplotlib.rcParams['axes.unicode_minus'] = False
    fig = matplotlib.pyplot.figure(figsize=(14, 10), dpi=130, facecolor='#f8fafc')
    fig.suptitle(_fa("گزارش بک‌تست"), fontsize=18, fontweight='bold',
                 y=0.98, color='#0f172a')
    ax1 = fig.add_axes([0.06, 0.62, 0.88, 0.28])
    ec = report.get("equity_curve", [])
    if ec:
        ax1.plot(range(len(ec)), ec, color='#2563eb', linewidth=2)
        ax1.fill_between(range(len(ec)), report["initial_balance"], ec,
                         color='#2563eb', alpha=0.15)
    ax1.set_title(_fa("منحنی سرمایه"), fontsize=12)
    ax1.grid(True, alpha=0.3)

    ax2 = fig.add_axes([0.06, 0.06, 0.42, 0.48]); ax2.axis('off')
    stats = [("تعداد", f"{report['total_trades']}"),
             ("برنده", f"{report['wins']}"), ("بازنده", f"{report['losses']}"),
             ("وین‌ریت", f"{report['win_rate']:.2f}%"),
             ("بالانس اولیه", f"{report['initial_balance']:.2f}$"),
             ("بالانس نهایی", f"{report['final_balance']:.2f}$"),
             ("سود", f"{report['total_profit']:+.2f}$"),
             ("PF", f"{report['profit_factor']:.2f}"),
             ("Sharpe", f"{report.get('sharpe', 0):.2f}"),
             ("DD", f"{report.get('max_dd', 0):.2f}$")]
    td = [[_fa(k), _fa(v)] for k, v in stats]
    tbl = ax2.table(cellText=td, loc='center', cellLoc='center')
    tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.5)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor('#cbd5e1')
        cell.set_facecolor('#ffffff' if r % 2 else '#f1f5f9')
    ax2.set_title(_fa("خلاصه"), fontsize=12)

    ax3 = fig.add_axes([0.52, 0.06, 0.42, 0.48]); ax3.axis('off')
    monthly = report.get("monthly", {})
    rows = [[_fa(x) for x in ["ماه", "تعداد", "برنده", "بازنده", "وین‌ریت", "سود"]]]
    for m in sorted(monthly.keys()):
        d = monthly[m]
        rows.append([_fa(m), str(d["trades"]), str(d["wins"]),
                     str(d["losses"]), f"{d['win_rate']:.1f}%",
                     f"{d['profit']:+.2f}"])
    t2 = ax3.table(cellText=rows, loc='center', cellLoc='center')
    t2.auto_set_font_size(False); t2.set_fontsize(9); t2.scale(1, 1.6)
    for (r, c), cell in t2.get_celld().items():
        cell.set_edgecolor('#cbd5e1')
        cell.set_facecolor('#1e293b' if r == 0 else
                           ('#ffffff' if r % 2 else '#f1f5f9'))
        if r == 0:
            cell.set_text_props(color='white', fontweight='bold')
    ax3.set_title(_fa("ماهانه"), fontsize=12)
    fig.savefig(output_path, dpi=130, bbox_inches='tight', facecolor='#f8fafc')
    matplotlib.pyplot.close(fig)
    return output_path


def render_report_pdf(report, output_path="report.pdf", chart_image="report.png"):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                        Spacer, Table, TableStyle,
                                        Image as RLImage)
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return None
    font_name = "Helvetica"
    _fp = resource_path("fonts/Vazirmatn-Regular.ttf")
    if os.path.exists(_fp):
        try:
            pdfmetrics.registerFont(TTFont("Vazirmatn", _fp))
            font_name = "Vazirmatn"
        except Exception:
            pass
    styles = getSampleStyleSheet()
    ts = ParagraphStyle('t', parent=styles['Title'], fontName=font_name,
                        fontSize=18, alignment=2)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontName=font_name,
                        fontSize=13, alignment=2)
    nm = ParagraphStyle('n', parent=styles['Normal'], fontName=font_name,
                        fontSize=10, alignment=2)
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            rightMargin=1.2 * cm, leftMargin=1.2 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    story = [Paragraph(_fa("گزارش بک‌تست"), ts),
             Paragraph(_fa(f"تاریخ: {datetime.now():%Y-%m-%d %H:%M}"), nm),
             Spacer(1, 10), Paragraph(_fa("خلاصه"), h2)]
    stats = [("تعداد", report['total_trades']),
             ("برنده", report['wins']), ("بازنده", report['losses']),
             ("وین‌ریت", f"{report['win_rate']:.2f}%"),
             ("بالانس اولیه", f"{report['initial_balance']:.2f}$"),
             ("بالانس نهایی", f"{report['final_balance']:.2f}$"),
             ("سود", f"{report['total_profit']:+.2f}$")]
    data = [[_fa(k), _fa(str(v))] for k, v in stats]
    t = Table(data, colWidths=[8 * cm, 6 * cm])
    t.setStyle(TableStyle([('FONTNAME', (0, 0), (-1, -1), font_name),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    story.append(t); story.append(Spacer(1, 12))
    if os.path.exists(chart_image):
        story.append(RLImage(chart_image, width=17 * cm, height=12 * cm))
    doc.build(story)
    return output_path


# ============================================================
#                    نمودار
# ============================================================
class CandleChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(10, 5), dpi=90, facecolor='#0f172a')
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = self.fig.add_subplot(111)
        self._style()

    def _style(self):
        self.ax.set_facecolor('#0f172a')
        self.ax.tick_params(colors='#cbd5e1', labelsize=8)
        for s in self.ax.spines.values():
            s.set_color('#334155')
        self.ax.grid(True, color='#1e293b', linestyle='--', linewidth=0.5)

    def plot(self, df, fvgs=None, trades=None, title="نمودار", max_bars=200):
        self.ax.clear(); self._style()
        df = df.tail(max_bars).reset_index(drop=True)
        if df.empty:
            self.draw(); return
        for idx, row in df.iterrows():
            c = '#22c55e' if row['close'] >= row['open'] else '#ef4444'
            self.ax.plot([idx, idx], [row['low'], row['high']],
                         color=c, linewidth=0.8, zorder=2)
            bl = min(row['open'], row['close'])
            bh = abs(row['close'] - row['open']) or 0.0001
            self.ax.add_patch(Rectangle((idx - 0.3, bl), 0.6, bh,
                                        facecolor=c, edgecolor=c, zorder=3))
        if fvgs:
            for fvg in fvgs:
                try:
                    ip = df[df['time'] == fvg['time']].index[0]
                except Exception:
                    continue
                c = '#22c55e' if 'BULL' in fvg.get('type', '') else '#ef4444'
                self.ax.add_patch(Rectangle(
                    (ip - 0.5, fvg['gap_low']), 3,
                    fvg['gap_high'] - fvg['gap_low'],
                    facecolor=c, alpha=0.25, edgecolor=c,
                    linestyle='--', linewidth=1, zorder=1))
        if trades:
            for t in trades:
                try:
                    ei = df[df['time'] == pd.to_datetime(t['entry_time'])].index[0]
                    xi = df[df['time'] == pd.to_datetime(t['exit_time'])].index[0]
                except Exception:
                    continue
                is_buy = t['type'].startswith('BUY')
                self.ax.scatter(ei, t['entry'],
                                marker='^' if is_buy else 'v',
                                color='#22c55e' if is_buy else '#ef4444',
                                s=80, zorder=5, edgecolor='white')
                pc = '#22c55e' if t['profit'] > 0 else '#ef4444'
                self.ax.scatter(xi, t['exit'], marker='X',
                                color=pc, s=90, zorder=5, edgecolor='white')
        self.ax.set_title(_fa(title), color='#f1f5f9', fontsize=11)
        n = len(df); step = max(1, n // 8)
        ticks = list(range(0, n, step))
        labels = [pd.to_datetime(df.iloc[i]['time']).strftime("%m/%d %H:%M")
                  for i in ticks if i < n]
        self.ax.set_xticks(ticks[:len(labels)])
        self.ax.set_xticklabels(labels, rotation=20, fontsize=7)
        self.fig.tight_layout(); self.draw()

    def plot_equity_curve(self, trades, initial_balance):
        self.ax.clear(); self._style()
        if not trades:
            self.draw(); return
        eq = [initial_balance]
        for t in trades:
            eq.append(eq[-1] + t['profit'])
        self.ax.plot(range(len(eq)), eq, color='#38bdf8', linewidth=1.5)
        self.ax.axhline(initial_balance, color='#94a3b8', linestyle='--')
        self.ax.set_title(_fa("منحنی سرمایه"), color='#f1f5f9', fontsize=11)
        self.fig.tight_layout(); self.draw()


# ============================================================
#                    Bridge Signals
# ============================================================
class LogBridge(QObject):
    new_log = pyqtSignal(str, str)


class BacktestBridge(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)


class OptimizerBridge(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)


# ============================================================
#        فیلتر سراسری برای جلوگیری از تغییر با غلتک ماوس
# ============================================================
class WheelEventFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit)):
                event.ignore()
                return True
        return False


# ============================================================
#                    پنجره اصلی
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ربات معامله‌گر آویژه")
        self.setMinimumSize(1100, 620)
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.resize(min(1500, int(sg.width() * 0.92)),
                        min(820, int(sg.height() * 0.82)))
        else:
            self.resize(1400, 760)

        self.cfg = load_config()
        self.log_bridge = LogBridge()
        self.log_bridge.new_log.connect(self.append_log)
        self.bt_bridge = BacktestBridge()
        self.bt_bridge.progress.connect(self._on_bt_progress)
        self.bt_bridge.finished.connect(self._on_bt_finished)
        self.opt_bridge = OptimizerBridge()
        self.opt_bridge.progress.connect(self._opt_progress)
        self.opt_bridge.finished.connect(self._on_optimizer_finished)

        self.bot = None
        self._bt_worker = None
        self._opt_worker = None
        self.last_report = None
        self.last_backtest_df = None

        self.setLayoutDirection(Qt.RightToLeft)
        self._build_ui()
        self._apply_font()

        self._pl_timer = QTimer()
        self._pl_timer.timeout.connect(self._refresh_live_pl)
        self._pl_timer.start(3000)

        QTimer.singleShot(500, self._auto_connect)

    def _apply_font(self):
        path = resource_path("fonts/Vazirmatn-Regular.ttf")
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            fams = QFontDatabase.applicationFontFamilies(fid)
            fam = fams[0] if fams else "Tahoma"
        else:
            fam = "Tahoma"
        QApplication.instance().setFont(QFont(fam, 10))

    def _auto_connect(self):
        if not MT5_AVAILABLE:
            return
        symbol = self.inp_symbol.text().strip()
        ok, msg = mt5_attach(symbol)
        if ok:
            for line in msg.split("\n"):
                self.append_log(line, "success")
            self.lbl_conn_status.setText("🟢 متصل به متاتریدر")
            self.lbl_conn_status.setStyleSheet(
                "color:#22c55e;font-weight:bold;font-size:13px;")
        else:
            for line in msg.split("\n"):
                self.append_log(line, "error")
            self.lbl_conn_status.setText("🔴 اتصال برقرار نیست")
            self.lbl_conn_status.setStyleSheet(
                "color:#ef4444;font-weight:bold;font-size:13px;")

    def _build_ui(self):
        c = QWidget(); self.setCentralWidget(c)
        root = QVBoxLayout(c)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QLabel("🤖 ربات معامله‌گر آویژه")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(
            "font-size:16px;font-weight:bold;padding:10px;"
            "background:#1e293b;color:#f8fafc;border-radius:6px;")
        root.addWidget(header)

        if not MT5_AVAILABLE:
            w = QLabel("⚠️ MetaTrader5 نصب نیست. برای نصب: pip install MetaTrader5 (فقط ویندوز)")
            w.setWordWrap(True)
            w.setStyleSheet("padding:8px;background:#fef3c7;color:#92400e;"
                            "border-radius:5px;font-weight:bold;")
            root.addWidget(w)

        root.addWidget(self._build_live_panel())

        sp = QSplitter(Qt.Horizontal)
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.RightToLeft)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.addTab(self._tab_connection(), "🔌 اتصال و نماد")
        self.tabs.addTab(self._tab_strategy(), "📊 استراتژی")
        self.tabs.addTab(self._tab_risk(), "💰 ریسک و مدیریت")
        self.tabs.addTab(self._tab_time_telegram(), "⏰ ساعات و تلگرام")
        self.tabs.addTab(self._tab_chart(), "📈 نمودار")
        self.tabs.addTab(self._tab_backtest(), "🔬 بک‌تست")
        self.tabs.addTab(self._tab_report(), "📋 گزارش")
        self.tabs.addTab(self._tab_optimizer(), "🔁 بهینه‌سازی")

        cb = QWidget(); cl = QVBoxLayout(cb)
        cl.addWidget(self.tabs)

        bts = QHBoxLayout()
        self.btn_start = QPushButton("▶  شروع ربات")
        self.btn_stop = QPushButton("⏹  توقف")
        self.btn_save = QPushButton("💾  ذخیره تنظیمات")
        self.btn_reset = QPushButton("↺  بازگشت به پیش‌فرض")
        self.btn_start.setStyleSheet(
            "background:#16a34a;color:white;font-weight:bold;padding:8px;border-radius:5px;")
        self.btn_stop.setStyleSheet(
            "background:#dc2626;color:white;font-weight:bold;padding:8px;border-radius:5px;")
        self.btn_save.setStyleSheet(
            "background:#2563eb;color:white;font-weight:bold;padding:8px;border-radius:5px;")
        self.btn_reset.setStyleSheet(
            "background:#f59e0b;color:white;font-weight:bold;padding:8px;border-radius:5px;")
        self.btn_start.clicked.connect(self.start_bot)
        self.btn_stop.clicked.connect(self.stop_bot)
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_reset.clicked.connect(self.reset_to_defaults)
        self.btn_stop.setEnabled(False)
        bts.addWidget(self.btn_start); bts.addWidget(self.btn_stop)
        bts.addWidget(self.btn_save); bts.addWidget(self.btn_reset)
        cl.addLayout(bts)

        lp = QWidget(); ll = QVBoxLayout(lp)
        ll.addWidget(QLabel("📋 لاگ اجرا"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLayoutDirection(Qt.RightToLeft)
        self.log_view.setStyleSheet(
            "background:#0f172a;color:#e2e8f0;font-family:'Tahoma';"
            "font-size:11px;padding:6px;border-radius:6px;")
        ll.addWidget(self.log_view)
        bc = QPushButton("🧹 پاک کردن لاگ")
        bc.clicked.connect(lambda: self.log_view.clear())
        ll.addWidget(bc)

        sp.addWidget(cb); sp.addWidget(lp)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 1)
        sp.setSizes([1050, 350])
        sp.setChildrenCollapsible(False)
        root.addWidget(sp, 1)

    def _build_live_panel(self):
        b = QGroupBox("💹 وضعیت")
        b.setStyleSheet(
            "QGroupBox{background:#0f172a;color:#f1f5f9;font-weight:bold;"
            "border:1px solid #334155;border-radius:6px;padding:8px;}"
            "QLabel{color:#e2e8f0;}")
        g = QGridLayout(b)
        self.lbl_balance = QLabel("—")
        self.lbl_equity = QLabel("—")
        self.lbl_daily = QLabel("—")
        self.lbl_pos = QLabel("—")

        def cell(t, w):
            cw = QWidget(); v = QVBoxLayout(cw)
            v.setContentsMargins(0, 0, 0, 0)
            lb = QLabel(t); lb.setAlignment(Qt.AlignCenter)
            lb.setStyleSheet("color:#94a3b8;font-size:10px;")
            w.setAlignment(Qt.AlignCenter)
            w.setStyleSheet("font-size:14px;font-weight:bold;color:#f8fafc;")
            v.addWidget(lb); v.addWidget(w)
            return cw

        g.addWidget(cell("Balance", self.lbl_balance), 0, 0)
        g.addWidget(cell("Equity", self.lbl_equity), 0, 1)
        g.addWidget(cell("P/L روزانه", self.lbl_daily), 0, 2)
        g.addWidget(cell("پوزیشن باز", self.lbl_pos), 0, 3)
        return b

    def _refresh_live_pl(self):
        if not MT5_AVAILABLE:
            return
        try:
            acc = mt5.account_info()
            if acc:
                self.lbl_balance.setText(f"{acc.balance:.2f} $")
                self.lbl_equity.setText(f"{acc.equity:.2f} $")
                pnl = acc.equity - acc.balance
                self.lbl_daily.setText(f"{pnl:+.2f} $")
                c = "#22c55e" if pnl >= 0 else "#ef4444"
                self.lbl_daily.setStyleSheet(
                    f"font-size:14px;font-weight:bold;color:{c};")
            p = mt5.positions_get()
            self.lbl_pos.setText(str(len(p)) if p else "0")
        except Exception:
            pass

    def _tab_connection(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        info = QLabel()
        info.setTextFormat(Qt.RichText)
        info.setText(
            "<div dir='rtl' style='text-align:right; line-height:180%;'>"
            "💡 <b>راهنما:</b><br>"
            "۱. متاتریدر ۵ را باز کرده و در حساب خود لاگین کنید.<br>"
            "۲. فقط نام نماد مورد نظر را وارد کنید (مثل XAUUSD یا EURUSD).<br>"
            "۳. ربات به‌طور خودکار به متاتریدر باز متصل می‌شود.<br>"
            "۴. نماد به‌صورت خودکار در Market Watch اضافه می‌شود."
            "</div>"
        )
        info.setWordWrap(True)
        info.setMinimumHeight(150)
        info.setMinimumWidth(360)
        info.setMaximumWidth(560)
        info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        info.setStyleSheet(
            "padding:14px;background:#eff6ff;color:#1e40af;"
            "border-radius:6px;font-size:11px;")

        info_row_widget = QWidget()
        info_row_widget.setLayoutDirection(Qt.LeftToRight)
        info_row = QHBoxLayout(info_row_widget)
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(0)
        info_row.addStretch(1)
        info_row.addWidget(info)
        root.addWidget(info_row_widget)

        sb = QGroupBox("وضعیت اتصال")
        sb.setStyleSheet(
            "QGroupBox{font-weight:bold;padding-top:14px;}"
            "QGroupBox::title{subcontrol-origin:margin;padding:0 6px;}"
        )
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(10, 6, 10, 10)
        sl.setSpacing(10)
        self.lbl_conn_status = QLabel("در حال بررسی ...")
        self.lbl_conn_status.setWordWrap(True)
        self.lbl_conn_status.setMinimumHeight(36)
        self.lbl_conn_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.lbl_conn_status.setStyleSheet(
            "color:#94a3b8;font-weight:bold;font-size:13px;padding:8px;")
        self.btn_reconnect = QPushButton("🔄 اتصال مجدد")
        self.btn_reconnect.setMinimumHeight(36)
        self.btn_reconnect.setStyleSheet(
            "background:#0891b2;color:white;font-weight:bold;"
            "padding:8px 16px;border-radius:5px;")
        self.btn_reconnect.clicked.connect(self._auto_connect)
        sl.addWidget(self.lbl_conn_status)
        sl.addWidget(self.btn_reconnect)
        root.addWidget(sb)

        form_box = QGroupBox("نماد و تایم‌فریم")
        form_box.setStyleSheet(
            "QGroupBox{font-weight:bold;padding-top:14px;}"
            "QGroupBox::title{subcontrol-origin:margin;padding:0 6px;}"
        )
        f = QFormLayout(form_box)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setFormAlignment(Qt.AlignRight | Qt.AlignTop)
        f.setHorizontalSpacing(16)
        f.setVerticalSpacing(12)
        f.setContentsMargins(14, 10, 14, 14)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        f.setRowWrapPolicy(QFormLayout.DontWrapRows)

        self.inp_symbol = QLineEdit(str(self.cfg["symbol"]))
        self.inp_symbol.setPlaceholderText("مثال: XAUUSD, EURUSD, GBPUSD")
        self.inp_symbol.setStyleSheet(
            "font-size:13px;padding:8px;min-height:32px;")
        self.inp_symbol.setMinimumWidth(240)

        self.cmb_tf = QComboBox()
        self.cmb_tf.addItems(["M1", "M5", "M15"])
        self.cmb_tf.setCurrentText(str(self.cfg["timeframe"]))
        self.cmb_tf.setStyleSheet("padding:6px;min-height:30px;")

        self.cmb_tf_high = QComboBox()
        self.cmb_tf_high.addItems(["M5", "M15", "M30", "H1"])
        self.cmb_tf_high.setCurrentText(str(self.cfg["timeframe_higher"]))
        self.cmb_tf_high.setStyleSheet("padding:6px;min-height:30px;")

        f.addRow("نماد معاملاتی:", self.inp_symbol)
        f.addRow("تایم‌فریم اصلی:", self.cmb_tf)
        f.addRow("تایم‌فریم بالاتر (تأیید):", self.cmb_tf_high)
        root.addWidget(form_box)

        popular = QGroupBox("نمادهای محبوب")
        popular.setStyleSheet(
            "QGroupBox{font-weight:bold;padding-top:14px;}"
            "QGroupBox::title{subcontrol-origin:margin;padding:0 6px;}"
        )
        pl = QGridLayout(popular)
        pl.setContentsMargins(14, 10, 14, 14)
        pl.setHorizontalSpacing(8)
        pl.setVerticalSpacing(8)

        sym_list = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY",
                    "BTCUSD", "US30", "NAS100"]
        for idx, s in enumerate(sym_list):
            btn = QPushButton(s)
            btn.setMinimumHeight(36)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(
                "padding:6px 10px;background:#f1f5f9;"
                "border:1px solid #cbd5e1;border-radius:4px;"
                "font-weight:bold;color:#1e293b;")
            btn.clicked.connect(lambda _, sym=s: self.inp_symbol.setText(sym))
            row = idx // 4
            col = idx % 4
            pl.addWidget(btn, row, col)

        for col in range(4):
            pl.setColumnStretch(col, 1)
        root.addWidget(popular)

        root.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def _tab_strategy(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        base = QGroupBox("⚙️ تنظیمات پایه")
        base.setStyleSheet(
            "QGroupBox{font-weight:bold;padding-top:14px;}"
            "QGroupBox::title{subcontrol-origin:margin;padding:0 6px;}"
        )
        bf = QFormLayout(base)
        bf.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bf.setFormAlignment(Qt.AlignRight | Qt.AlignTop)
        bf.setHorizontalSpacing(16)
        bf.setVerticalSpacing(10)
        bf.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        bf.setRowWrapPolicy(QFormLayout.DontWrapRows)

        self.inp_stop_d = QLineEdit(str(self.cfg["stop_distances"]))
        self.inp_stop_d.setPlaceholderText("مثال: 1.0,1.5")
        self.inp_stop_d.setMinimumWidth(200)

        self.inp_limit_d = QLineEdit(str(self.cfg["limit_distances"]))
        self.inp_limit_d.setPlaceholderText("مثال: 1.0,1.5")
        self.inp_limit_d.setMinimumWidth(200)

        self.inp_lot = QDoubleSpinBox()
        self.inp_lot.setDecimals(2)
        self.inp_lot.setSingleStep(0.01)
        self.inp_lot.setRange(0.01, 100)
        self.inp_lot.setValue(float(self.cfg["lot_size"]))
        self.inp_lot.setMinimumWidth(110)

        self.inp_atr_mult = QDoubleSpinBox()
        self.inp_atr_mult.setDecimals(2)
        self.inp_atr_mult.setRange(0.1, 10)
        self.inp_atr_mult.setValue(float(self.cfg["atr_multiplier"]))
        self.inp_atr_mult.setMinimumWidth(110)

        self.inp_rr = QDoubleSpinBox()
        self.inp_rr.setDecimals(1)
        self.inp_rr.setRange(0.5, 10)
        self.inp_rr.setValue(float(self.cfg["risk_reward"]))
        self.inp_rr.setMinimumWidth(110)

        bf.addRow("فاصله Stop:", self.inp_stop_d)
        bf.addRow("فاصله Limit:", self.inp_limit_d)
        bf.addRow("حداکثر حجم (لات):", self.inp_lot)
        bf.addRow("ضریب ATR:", self.inp_atr_mult)
        bf.addRow("ریسک به ریوارد:", self.inp_rr)
        root.addWidget(base)

        trend_box = QGroupBox("📈 فیلترهای روند")
        trend_box.setStyleSheet(
            "QGroupBox{font-weight:bold;padding-top:14px;}"
            "QGroupBox::title{subcontrol-origin:margin;padding:0 6px;}"
        )
        tf = QFormLayout(trend_box)
        tf.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tf.setFormAlignment(Qt.AlignRight | Qt.AlignTop)
        tf.setHorizontalSpacing(16)
        tf.setVerticalSpacing(10)
        tf.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        tf.setRowWrapPolicy(QFormLayout.DontWrapRows)

        self.chk_adx = QCheckBox("فعال بودن تأیید روند با ADX")
        self.chk_adx.setChecked(bool(self.cfg.get("enable_adx", True)))

        self.inp_adx_period = QSpinBox()
        self.inp_adx_period.setRange(2, 100)
        self.inp_adx_period.setValue(int(self.cfg.get("adx_period", 14)))
        self.inp_adx_period.setMinimumWidth(80)

        self.inp_adx_threshold = QDoubleSpinBox()
        self.inp_adx_threshold.setDecimals(1)
        self.inp_adx_threshold.setRange(5.0, 60.0)
        self.inp_adx_threshold.setSingleStep(0.5)
        self.inp_adx_threshold.setValue(float(self.cfg.get("adx_threshold", 20.0)))
        self.inp_adx_threshold.setMinimumWidth(80)

        adx_row = QWidget()
        adx_lay = QHBoxLayout(adx_row)
        adx_lay.setContentsMargins(0, 0, 0, 0)
        adx_lay.setSpacing(8)
        adx_lay.addWidget(QLabel("دوره:"))
        adx_lay.addWidget(self.inp_adx_period)
        adx_lay.addSpacing(12)
        adx_lay.addWidget(QLabel("حداقل قدرت:"))
        adx_lay.addWidget(self.inp_adx_threshold)
        adx_lay.addStretch()

        tf.addRow(self.chk_adx)
        tf.addRow("پارامترهای ADX:", adx_row)

        self.chk_candle_sequence = QCheckBox("تأیید روند با توالی کندل‌ها")
        self.chk_candle_sequence.setChecked(
            bool(self.cfg.get("enable_candle_sequence", True)))

        self.inp_candle_count = QSpinBox()
        self.inp_candle_count.setRange(2, 20)
        self.inp_candle_count.setValue(
            int(self.cfg.get("candle_sequence_count", 3)))
        self.inp_candle_count.setMinimumWidth(80)

        candle_row = QWidget()
        candle_lay = QHBoxLayout(candle_row)
        candle_lay.setContentsMargins(0, 0, 0, 0)
        candle_lay.setSpacing(8)
        candle_lay.addWidget(QLabel("تعداد کندل:"))
        candle_lay.addWidget(self.inp_candle_count)
        candle_lay.addWidget(QLabel("(پیش‌فرض 2)"))
        candle_lay.addStretch()

        tf.addRow(self.chk_candle_sequence)
        tf.addRow("توالی تأیید:", candle_row)
        root.addWidget(trend_box)

        strat_box = QGroupBox("🎯 استراتژی‌ها")
        strat_box.setStyleSheet(
            "QGroupBox{font-weight:bold;padding-top:14px;}"
            "QGroupBox::title{subcontrol-origin:margin;padding:0 6px;}"
        )
        sv = QVBoxLayout(strat_box)
        sv.setContentsMargins(10, 8, 10, 12)
        sv.setSpacing(8)

        main_note = QLabel(
            "🔵 منطق اصلی (Main): اگر هیچ‌کدام از استراتژی‌های زیر تیک نخورد، "
            "ربات به‌طور خودکار با منطق «روند + توالی کندل + FVG» معامله می‌کند "
            "و سیگنال با برچسب [MAIN_FVG] در لاگ ثبت می‌شود."
        )
        main_note.setWordWrap(True)
        main_note.setStyleSheet(
            "padding:8px;background:#dbeafe;color:#1e40af;"
            "border-radius:5px;font-size:11px;"
        )
        sv.addWidget(main_note)

        note = QLabel(
            "💡 هر استراتژی مستقل بررسی می‌شود. اولین استراتژی‌ای که شرطش "
            "برقرار شد سیگنال می‌دهد."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding:8px;background:#fef9c3;color:#854d0e;"
            "border-radius:5px;font-size:11px;"
        )
        sv.addWidget(note)

        self.chk_smc = QCheckBox("SMC — Break of Structure (BOS)")
        self.chk_smc.setChecked(bool(self.cfg["enable_smc"]))
        sv.addWidget(self.chk_smc)

        self.chk_fvg = QCheckBox("FVG — Fair Value Gap (گپ قیمتی)")
        self.chk_fvg.setChecked(bool(self.cfg.get("enable_fvg", True)))
        sv.addWidget(self.chk_fvg)

        self.chk_pa = QCheckBox("پرایس اکشن — Engulfing / Pinbar")
        self.chk_pa.setChecked(bool(self.cfg["enable_price_action"]))
        sv.addWidget(self.chk_pa)

        self.chk_htf = QCheckBox(
            "تأیید با تایم‌فریم بالاتر (برای SMC / FVG / PA / منطق اصلی)")
        self.chk_htf.setChecked(bool(self.cfg["enable_higher_tf_confirm"]))
        sv.addWidget(self.chk_htf)

        root.addWidget(strat_box)
        root.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def _tab_risk(self):
        page = QWidget()
        f = QFormLayout(page)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setHorizontalSpacing(16)
        f.setVerticalSpacing(10)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.inp_partial = QDoubleSpinBox()
        self.inp_partial.setRange(0, 1000)
        self.inp_partial.setDecimals(2)
        self.inp_partial.setSingleStep(0.5)
        self.inp_partial.setValue(float(self.cfg["partial_profit_step"]))
        self.inp_partial.setMinimumWidth(110)

        self.inp_partial_frac = QDoubleSpinBox()
        self.inp_partial_frac.setRange(0.1, 0.9)
        self.inp_partial_frac.setDecimals(2)
        self.inp_partial_frac.setSingleStep(0.05)
        self.inp_partial_frac.setValue(float(self.cfg.get("partial_profit_fraction", 0.5)))
        self.inp_partial_frac.setMinimumWidth(110)

        self.inp_trail = QDoubleSpinBox()
        self.inp_trail.setRange(0.1, 100)
        self.inp_trail.setValue(float(self.cfg["trailing_drop"]))
        self.inp_trail.setMinimumWidth(110)

        self.inp_max_profit = QDoubleSpinBox()
        self.inp_max_profit.setRange(0, 100000)
        self.inp_max_profit.setValue(float(self.cfg["max_daily_profit"]))
        self.inp_max_profit.setMinimumWidth(130)

        self.inp_max_loss = QDoubleSpinBox()
        self.inp_max_loss.setRange(0, 100000)
        self.inp_max_loss.setValue(float(self.cfg["max_daily_loss"]))
        self.inp_max_loss.setMinimumWidth(130)

        self.inp_max_loss_per_trade = QDoubleSpinBox()
        self.inp_max_loss_per_trade.setRange(0, 10000)
        self.inp_max_loss_per_trade.setDecimals(2)
        self.inp_max_loss_per_trade.setSingleStep(0.5)
        self.inp_max_loss_per_trade.setValue(
            float(self.cfg.get("max_loss_per_trade", 5.0)))
        self.inp_max_loss_per_trade.setSuffix(" $")
        self.inp_max_loss_per_trade.setMinimumWidth(130)

        self.inp_comm_per_lot = QDoubleSpinBox()
        self.inp_comm_per_lot.setRange(0, 1000)
        self.inp_comm_per_lot.setDecimals(2)
        self.inp_comm_per_lot.setSingleStep(0.5)
        self.inp_comm_per_lot.setValue(
            float(self.cfg.get("commission_per_lot", 7.0)))
        self.inp_comm_per_lot.setSuffix(" $")
        self.inp_comm_per_lot.setMinimumWidth(130)

        self.chk_strict_max_loss = QCheckBox(
            "حالت سخت‌گیرانه: اگر با حداقل حجم بروکر هم زیر سقف نشد، معامله رد شود")
        self.chk_strict_max_loss.setChecked(
            bool(self.cfg.get("strict_max_loss", True)))
        self.chk_strict_max_loss.setToolTip(
            "اگر تیک باشد و min_lot نقض کند، معامله اجرا نمی‌شود.\n"
            "اگر تیک را بردارید، با min_lot اجرا می‌شود (ضرر ممکن است کمی از سقف بیشتر شود)."
        )

        # --- هشدار ضرر معامله باز ---
        self.chk_loss_alert = QCheckBox(
            "ارسال هشدار تلگرام وقتی ضرر معامله باز از حد زیر بیشتر شد")
        self.chk_loss_alert.setChecked(
            bool(self.cfg.get("enable_loss_alert", True)))

        self.inp_loss_alert_threshold = QDoubleSpinBox()
        self.inp_loss_alert_threshold.setRange(1, 10000)
        self.inp_loss_alert_threshold.setDecimals(2)
        self.inp_loss_alert_threshold.setSingleStep(1.0)
        self.inp_loss_alert_threshold.setValue(
            float(self.cfg.get("loss_alert_threshold", 10.0)))
        self.inp_loss_alert_threshold.setSuffix(" $")
        self.inp_loss_alert_threshold.setMinimumWidth(130)

        self.inp_loop = QSpinBox()
        self.inp_loop.setRange(2, 3600)
        self.inp_loop.setValue(int(self.cfg["loop_interval_sec"]))
        self.inp_loop.setMinimumWidth(110)

        self.inp_max_orders = QSpinBox()
        self.inp_max_orders.setRange(1, 50)
        self.inp_max_orders.setValue(int(self.cfg.get("max_simultaneous_orders", 2)))
        self.inp_max_orders.setMinimumWidth(110)

        f.addRow("پله سود (دلار):", self.inp_partial)
        f.addRow("کسر حجم در هر پله:", self.inp_partial_frac)
        f.addRow("افت مجاز (Trailing):", self.inp_trail)

        sep0 = QLabel("─" * 40)
        sep0.setStyleSheet("color:#cbd5e1;")
        f.addRow(sep0)

        f.addRow("حداکثر ضرر هر معامله:", self.inp_max_loss_per_trade)
        f.addRow("کمیسیون هر لات (رفت‌وبرگشت):", self.inp_comm_per_lot)
        f.addRow(self.chk_strict_max_loss)

        sep_alert = QLabel("─" * 40)
        sep_alert.setStyleSheet("color:#cbd5e1;")
        f.addRow(sep_alert)

        f.addRow(self.chk_loss_alert)
        f.addRow("آستانه هشدار ضرر (دلار):", self.inp_loss_alert_threshold)

        sep1 = QLabel("─" * 40)
        sep1.setStyleSheet("color:#cbd5e1;")
        f.addRow(sep1)

        f.addRow("حداکثر سود روزانه:", self.inp_max_profit)
        f.addRow("حداکثر ضرر روزانه:", self.inp_max_loss)
        f.addRow("فاصله حلقه (ثانیه):", self.inp_loop)

        sep = QLabel("─" * 40)
        sep.setStyleSheet("color:#cbd5e1;")
        f.addRow(sep)

        f.addRow("حداکثر سفارشات همزمان:", self.inp_max_orders)

        note = QLabel(
            "💡 «حداکثر ضرر هر معامله»: حجم به‌طور خودکار طوری محاسبه می‌شود "
            "که در صورت خوردن SL، ضرر (شامل کمیسیون رفت‌وبرگشت) از این مقدار "
            "(به دلار) بیشتر نشود.\n\n"
            "🔸 اگر مقدار 0 بگذارید → حجم ثابت (lot_size) استفاده می‌شود.\n"
            "🔸 اگر «حالت سخت‌گیرانه» تیک داشته باشد و با min_lot بروکر نتوان "
            "زیر سقف ماند → آن سیگنال کاملاً رد می‌شود (در لاگ هشدار ثبت می‌شود).\n"
            "🔸 اگر «حالت سخت‌گیرانه» تیک نداشته باشد → با min_lot اجرا می‌شود "
            "حتی اگر ضرر کمی از سقف بیشتر شود.\n\n"
            "💡 «کمیسیون هر لات»: در فرمول لحاظ می‌شود. اگر مطمئن نیستید "
            "مقدار پیش‌فرض 7 دلار را نگه دارید.\n\n"
            "🔔 «هشدار ضرر معامله باز»: اگر ضرر شناور یک پوزیشن باز از آستانه "
            "مشخص‌شده (پیش‌فرض 10$) بیشتر شود، پیام هشدار به تلگرام ارسال می‌شود. "
            "منطق پله‌ای است: با هر بار عبور از مضربی از آستانه (20$، 30$، ...) "
            "یک هشدار جدید ارسال می‌شود.\n\n"
            "💡 نکته: با تنظیمات پیش‌فرض (atr_multiplier=3.5 و max_loss=5$) "
            "برای XAUUSD ممکن است همه سیگنال‌ها رد شوند. راه‌حل: ضریب ATR را به "
            "1.5~2 کاهش دهید یا max_loss را افزایش دهید یا حالت سخت‌گیرانه را بردارید."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "padding:8px;background:#dbeafe;color:#1e40af;"
            "border-radius:5px;font-size:11px;")
        f.addRow(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _tab_time_telegram(self):
        w = QWidget(); f = QFormLayout(w)
        f.setLabelAlignment(Qt.AlignRight); f.setSpacing(8)
        self.inp_sh = QSpinBox(); self.inp_sh.setRange(0, 23)
        self.inp_sh.setValue(int(self.cfg["trading_start_hour"]))
        self.inp_sm = QSpinBox(); self.inp_sm.setRange(0, 59)
        self.inp_sm.setValue(int(self.cfg["trading_start_min"]))
        self.inp_eh = QSpinBox(); self.inp_eh.setRange(0, 23)
        self.inp_eh.setValue(int(self.cfg["trading_end_hour"]))
        self.inp_em = QSpinBox(); self.inp_em.setRange(0, 59)
        self.inp_em.setValue(int(self.cfg["trading_end_min"]))

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("دقیقه:")); r1.addWidget(self.inp_sm)
        r1.addWidget(QLabel("ساعت:")); r1.addWidget(self.inp_sh)
        r1.addStretch()
        w1 = QWidget(); w1.setLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("دقیقه:")); r2.addWidget(self.inp_em)
        r2.addWidget(QLabel("ساعت:")); r2.addWidget(self.inp_eh)
        r2.addStretch()
        w2 = QWidget(); w2.setLayout(r2)

        self.inp_tg_token = QLineEdit(str(self.cfg["telegram_bot_token"]))
        self.inp_tg_chat = QLineEdit(str(self.cfg["telegram_chat_id"]))
        self.chk_tg = QCheckBox("ارسال به تلگرام")
        self.chk_tg.setChecked(bool(self.cfg["enable_telegram"]))
        f.addRow("شروع (ایران):", w1)
        f.addRow("پایان (ایران):", w2)
        f.addRow("توکن تلگرام:", self.inp_tg_token)
        f.addRow("چت آیدی:", self.inp_tg_chat)
        f.addRow(self.chk_tg)
        return w

    def _tab_chart(self):
        w = QWidget(); v = QVBoxLayout(w)
        top = QHBoxLayout()
        self.chart_symbol = QLineEdit(self.cfg["symbol"])
        self.chart_tf = QComboBox()
        self.chart_tf.addItems(["M1", "M5", "M15", "M30", "H1"])
        self.chart_tf.setCurrentText(self.cfg["timeframe"])
        self.chart_bars = QSpinBox(); self.chart_bars.setRange(50, 1000)
        self.chart_bars.setValue(200)
        self.btn_chart_load = QPushButton("🔄 بارگذاری")
        self.btn_chart_overlay = QPushButton("📌 معاملات بک‌تست")
        self.btn_chart_eq = QPushButton("📈 منحنی سرمایه")
        for b in (self.btn_chart_load, self.btn_chart_overlay, self.btn_chart_eq):
            b.setStyleSheet("padding:6px 10px;border-radius:4px;"
                            "background:#1e293b;color:white;")
        self.btn_chart_load.clicked.connect(self.load_chart)
        self.btn_chart_overlay.clicked.connect(self.overlay_backtest)
        self.btn_chart_eq.clicked.connect(self.show_equity_curve)
        top.addWidget(QLabel("نماد:")); top.addWidget(self.chart_symbol)
        top.addWidget(QLabel("TF:")); top.addWidget(self.chart_tf)
        top.addWidget(QLabel("کندل:")); top.addWidget(self.chart_bars)
        top.addWidget(self.btn_chart_load)
        top.addWidget(self.btn_chart_overlay)
        top.addWidget(self.btn_chart_eq)
        top.addStretch(); v.addLayout(top)
        self.chart_canvas = CandleChart(self)
        self.chart_toolbar = NavToolbar(self.chart_canvas, self)
        v.addWidget(self.chart_toolbar); v.addWidget(self.chart_canvas)
        return w

    def load_chart(self):
        if not MT5_AVAILABLE: return
        try:
            s = self.chart_symbol.text().strip()
            ok, msg = mt5_attach(s)
            if not ok:
                self.append_log(msg, "error"); return
            tf = self.chart_tf.currentText()
            n = self.chart_bars.value()
            r = mt5.copy_rates_from_pos(s, TF_MAP[tf], 0, n)
            if r is None or len(r) == 0:
                self.append_log("داده‌ای یافت نشد", "warn"); return
            df = pd.DataFrame(r)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            fvgs = self._find_fvgs(df)
            self.chart_canvas.plot(df, fvgs=fvgs, title=f"{s} — {tf}")
            self.append_log(f"نمودار {s} ({tf}) بارگذاری شد", "success")
        except Exception as e:
            self.append_log(f"خطای نمودار: {e}", "error")

    def _find_fvgs(self, df):
        fvgs = []
        for i in range(2, len(df)):
            c1, c2, c3 = df.iloc[i-2], df.iloc[i-1], df.iloc[i]
            if c3['low'] > c1['high'] and c2['close'] > c2['open']:
                fvgs.append({"time": df.iloc[i]['time'], "gap_low": c1['high'],
                             "gap_high": c3['low'], "type": "BULLISH_FVG"})
            elif c3['high'] < c1['low'] and c2['close'] < c2['open']:
                fvgs.append({"time": df.iloc[i]['time'], "gap_low": c3['high'],
                             "gap_high": c1['low'], "type": "BEARISH_FVG"})
        return fvgs

    def overlay_backtest(self):
        if not self.last_report or self.last_backtest_df is None:
            QMessageBox.information(self, "توجه", "ابتدا بک‌تست اجرا کنید.")
            return
        df = self.last_backtest_df
        fvgs = self._find_fvgs(df)
        self.chart_canvas.plot(df, fvgs=fvgs,
                               trades=self.last_report.get("trades", []),
                               title="نمودار + معاملات", max_bars=500)
        self.tabs.setCurrentIndex(4)

    def show_equity_curve(self):
        if not self.last_report:
            QMessageBox.information(self, "توجه", "ابتدا بک‌تست اجرا کنید.")
            return
        self.chart_canvas.plot_equity_curve(
            self.last_report["trades"], self.last_report["initial_balance"])
        self.tabs.setCurrentIndex(4)

    def _tab_backtest(self):
        w = QWidget(); v = QVBoxLayout(w)
        b = QGroupBox("⚙️ تنظیمات بک‌تست")
        b.setStyleSheet("QGroupBox{font-weight:bold;}")
        f = QFormLayout(b); f.setLabelAlignment(Qt.AlignRight)
        t = QDate.currentDate()
        self.bt_start = QDateEdit(t.addMonths(-3))
        self.bt_end = QDateEdit(t)
        self.bt_start.setCalendarPopup(True); self.bt_end.setCalendarPopup(True)
        self.bt_start.setDisplayFormat("dd-MM-yyyy")
        self.bt_end.setDisplayFormat("dd-MM-yyyy")
        self.bt_start.setAlignment(Qt.AlignRight)
        self.bt_end.setAlignment(Qt.AlignRight)
        self.bt_start.setLayoutDirection(Qt.RightToLeft)
        self.bt_end.setLayoutDirection(Qt.RightToLeft)

        self.bt_balance = QDoubleSpinBox()
        self.bt_balance.setRange(10, 10_000_000)
        self.bt_balance.setValue(100.0); self.bt_balance.setSuffix(" $")
        self.bt_symbol = QLineEdit(self.cfg["symbol"])
        self.bt_tf = QComboBox(); self.bt_tf.addItems(["M1", "M5", "M15"])
        self.bt_tf.setCurrentText(self.cfg["timeframe"])
        f.addRow("نماد:", self.bt_symbol)
        f.addRow("TF:", self.bt_tf)

        date_row_widget = QWidget()
        date_row = QHBoxLayout(date_row_widget)
        date_row.setContentsMargins(0, 0, 0, 0)
        date_row.setSpacing(6)
        date_row.addWidget(QLabel("از:"))
        date_row.addWidget(self.bt_start)
        date_row.addSpacing(15)
        date_row.addWidget(QLabel("تا:"))
        date_row.addWidget(self.bt_end)
        date_row.addStretch()
        f.addRow("بازه زمانی:", date_row_widget)

        f.addRow("موجودی اولیه:", self.bt_balance)
        v.addWidget(b)
        self.bt_progress = QProgressBar(); v.addWidget(self.bt_progress)
        self.bt_status = QLabel("آماده")
        self.bt_status.setStyleSheet("color:#94a3b8;font-weight:bold;")
        v.addWidget(self.bt_status)
        bs = QHBoxLayout()
        self.btn_bt_run = QPushButton("🚀 اجرای بک‌تست")
        self.btn_bt_run.setStyleSheet(
            "background:#7c3aed;color:white;font-weight:bold;"
            "padding:10px;border-radius:5px;")
        self.btn_bt_run.clicked.connect(self.run_backtest)
        bs.addWidget(self.btn_bt_run); v.addLayout(bs)
        v.addStretch()
        return w

    def run_backtest(self):
        if not MT5_AVAILABLE:
            QMessageBox.warning(self, "خطا", "MT5 در دسترس نیست.")
            return
        if self._bt_worker and self._bt_worker.isRunning():
            QMessageBox.warning(self, "هشدار", "در حال اجراست.")
            return
        cfg = self._collect_config()
        s = self.bt_symbol.text().strip()
        tf = self.bt_tf.currentText()
        cfg["timeframe"] = tf; cfg["symbol"] = s
        st = datetime(self.bt_start.date().year(), self.bt_start.date().month(),
                      self.bt_start.date().day())
        en = datetime(self.bt_end.date().year(), self.bt_end.date().month(),
                      self.bt_end.date().day(), 23, 59, 59)
        bal = self.bt_balance.value()
        self.bt_progress.setValue(0)
        self.bt_status.setText("شروع ...")
        self.btn_bt_run.setEnabled(False)
        self.append_log(f"بک‌تست {s} ({tf}) از {st.date()} تا {en.date()}")

        bridge = self.bt_bridge
        log = self.log_bridge.new_log

        class W(QThread):
            def run(self_inner):
                bt = Backtester(cfg, log_callback=lambda m, l="info": log.emit(m, l))
                try:
                    r = bt.run(s, st, en, initial_balance=bal,
                               progress_callback=lambda p, m: bridge.progress.emit(p, m))
                except Exception as e:
                    log.emit(f"خطای بک‌تست: {e}", "error"); r = None
                bridge.finished.emit(r)

        self._bt_worker = W()
        self._bt_worker.start()

    def _on_bt_progress(self, p, m):
        self.bt_progress.setValue(p); self.bt_status.setText(m)

    def _on_bt_finished(self, report):
        self.btn_bt_run.setEnabled(True)
        self.bt_status.setText("کامل شد")
        self.bt_progress.setValue(100)
        if report is None:
            self.append_log("بک‌تست ناموفق", "error"); return
        self.last_report = report
        try:
            s = self.bt_symbol.text().strip()
            tf = self.bt_tf.currentText()
            st = datetime(self.bt_start.date().year(), self.bt_start.date().month(),
                          self.bt_start.date().day())
            en = datetime(self.bt_end.date().year(), self.bt_end.date().month(),
                          self.bt_end.date().day(), 23, 59, 59)
            r = mt5.copy_rates_range(s, TF_MAP[tf], st, en)
            if r is not None and len(r):
                df = pd.DataFrame(r)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                self.last_backtest_df = df
        except Exception:
            self.last_backtest_df = None
        self.render_report(report)
        self.tabs.setCurrentIndex(6)
        self.append_log(
            f"✅ کامل | {report['total_trades']} معامله | "
            f"وین‌ریت {report['win_rate']:.1f}% | "
            f"سود {report['total_profit']:+.2f}$", "success")

    def _tab_report(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        cards = QGroupBox("📊 خلاصه")
        cards.setStyleSheet("QGroupBox{font-weight:bold;}")
        cg = QGridLayout(cards)
        cg.setContentsMargins(8, 12, 8, 8)
        cg.setHorizontalSpacing(7)
        cg.setVerticalSpacing(7)

        def mk(t):
            b = QFrame()
            b.setMinimumHeight(62)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setStyleSheet(
                "QFrame{background:#0f172a;border:1px solid #334155;"
                "border-radius:6px;padding:5px;}"
            )
            vl = QVBoxLayout(b)
            vl.setContentsMargins(5, 5, 5, 5)
            vl.setSpacing(3)
            lb = QLabel(t)
            lb.setAlignment(Qt.AlignCenter)
            lb.setWordWrap(True)
            lb.setStyleSheet(
                "color:#94a3b8;font-size:9px;background:transparent;border:none;"
            )
            val = QLabel("—")
            val.setAlignment(Qt.AlignCenter)
            val.setWordWrap(True)
            val.setStyleSheet(
                "color:#f8fafc;font-size:13px;font-weight:bold;"
                "background:transparent;border:none;"
            )
            vl.addWidget(lb)
            vl.addWidget(val)
            return b, val

        cards_data = [
            ("تعداد", "rp_tt"), ("برنده", "rp_w"), ("بازنده", "rp_l"), ("وین‌ریت", "rp_wr"),
            ("بالانس اولیه", "rp_ib"), ("بالانس نهایی", "rp_fb"), ("سود کل", "rp_pf_"), ("PF", "rp_pf"),
            ("Sharpe", "rp_sharpe"), ("Sortino", "rp_sortino"), ("Calmar", "rp_calmar"),
            ("Expectancy", "rp_exp"), ("حداکثر افت", "rp_dd"), ("میانگین برد", "rp_aw"),
            ("میانگین باخت", "rp_al"), ("Recovery", "rp_rf")
        ]
        for i, (title, attr) in enumerate(cards_data):
            frame, label = mk(title)
            setattr(self, attr, label)
            cg.addWidget(frame, i // 4, i % 4)

        for col in range(4):
            cg.setColumnStretch(col, 1)
        v.addWidget(cards)

        monthly_title = QLabel("📅 عملکرد ماهانه")
        monthly_title.setStyleSheet("font-weight:bold;padding-top:2px;")
        v.addWidget(monthly_title)

        self.tbl_m = QTableWidget()
        self.tbl_m.setColumnCount(6)
        self.tbl_m.setHorizontalHeaderLabels(
            ["ماه", "تعداد", "برنده", "بازنده", "وین‌ریت %", "سود/ضرر"]
        )
        self.tbl_m.setLayoutDirection(Qt.RightToLeft)
        self.tbl_m.setAlternatingRowColors(True)
        self.tbl_m.setWordWrap(True)
        self.tbl_m.verticalHeader().setVisible(False)
        self.tbl_m.setMinimumHeight(115)
        self.tbl_m.setMaximumHeight(190)
        mh = self.tbl_m.horizontalHeader()
        mh.setDefaultSectionSize(90)
        mh.setMinimumSectionSize(60)
        mh.setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.tbl_m)

        trades_title = QLabel("📋 معاملات")
        trades_title.setStyleSheet("font-weight:bold;padding-top:2px;")
        v.addWidget(trades_title)

        self.tbl_t = QTableWidget()
        self.tbl_t.setColumnCount(9)
        self.tbl_t.setHorizontalHeaderLabels(
            ["#", "ورود", "خروج", "نوع", "قیمت ورود", "قیمت خروج",
             "SL", "TP", "سود/ضرر"]
        )
        self.tbl_t.setLayoutDirection(Qt.RightToLeft)
        self.tbl_t.setAlternatingRowColors(True)
        self.tbl_t.setWordWrap(True)
        self.tbl_t.verticalHeader().setVisible(False)
        self.tbl_t.setMinimumHeight(250)
        th = self.tbl_t.horizontalHeader()
        th.setDefaultSectionSize(88)
        th.setMinimumSectionSize(58)
        th.setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.tbl_t, 1)

        bs = QHBoxLayout()
        bs.setSpacing(6)
        for txt, cb, sty in [
            ("💾 CSV", self.export_csv, "background:#2563eb;"),
            ("📈 نمودار", self.overlay_backtest, "background:#7c3aed;"),
            ("📤 تلگرام", self.send_to_telegram, "background:#0ea5e9;"),
            ("🧹 پاک کردن", self.clear_report, "background:#64748b;")
        ]:
            btn = QPushButton(txt)
            btn.setMinimumHeight(36)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(
                f"padding:7px;{sty}color:white;border-radius:5px;"
            )
            btn.clicked.connect(cb)
            bs.addWidget(btn)
        v.addLayout(bs)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def render_report(self, r):
        self.rp_tt.setText(str(r["total_trades"]))
        self.rp_w.setText(str(r["wins"]))
        self.rp_l.setText(str(r["losses"]))
        self.rp_wr.setText(f"{r['win_rate']:.1f}%")
        self.rp_ib.setText(f"{r['initial_balance']:.2f}$")
        self.rp_fb.setText(f"{r['final_balance']:.2f}$")
        p = r["total_profit"]
        self.rp_pf_.setText(f"{p:+.2f}$")
        c = "#22c55e" if p >= 0 else "#ef4444"
        self.rp_pf_.setStyleSheet(
            f"color:{c};font-size:15px;font-weight:bold;"
            "background:transparent;border:none;")
        pf = r.get("profit_factor", 0)
        self.rp_pf.setText("∞" if pf >= 9999 else f"{pf:.2f}")
        self.rp_sharpe.setText(f"{r.get('sharpe', 0):.2f}")
        self.rp_sortino.setText(f"{r.get('sortino', 0):.2f}")
        self.rp_calmar.setText(f"{r.get('calmar', 0):.2f}")
        self.rp_exp.setText(f"{r.get('expectancy', 0):+.2f}$")
        self.rp_dd.setText(f"{r.get('max_dd', 0):.2f}$")
        self.rp_aw.setText(f"{r.get('avg_win', 0):.2f}$")
        self.rp_al.setText(f"{r.get('avg_loss', 0):.2f}$")
        self.rp_rf.setText(f"{r.get('recovery_factor', 0):.2f}")

        m = r.get("monthly", {})
        self.tbl_m.setRowCount(len(m))
        for row, mm in enumerate(sorted(m.keys())):
            d = m[mm]
            items = [mm, str(d["trades"]), str(d["wins"]), str(d["losses"]),
                     f"{d['win_rate']:.1f}%", f"{d['profit']:+.2f}"]
            for col, t in enumerate(items):
                it = QTableWidgetItem(t)
                it.setTextAlignment(Qt.AlignCenter)
                if col == 5:
                    co = QColor("#22c55e") if d["profit"] >= 0 else QColor("#ef4444")
                    it.setForeground(QBrush(co))
                self.tbl_m.setItem(row, col, it)

        t = r.get("trades", [])
        self.tbl_t.setRowCount(len(t))
        for row, tr in enumerate(t):
            et = str(tr.get("entry_time", ""))[:19]
            xt = str(tr.get("exit_time", ""))[:19]
            pr = tr.get("profit", 0)
            items = [str(row+1), et, xt, tr.get("type", ""),
                     f"{tr.get('entry', 0):.2f}", f"{tr.get('exit', 0):.2f}",
                     f"{tr.get('sl', 0):.2f}", f"{tr.get('tp', 0):.2f}",
                     f"{pr:+.2f}"]
            for col, txt in enumerate(items):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                if col == 8:
                    co = QColor("#22c55e") if pr >= 0 else QColor("#ef4444")
                    it.setForeground(QBrush(co))
                self.tbl_t.setItem(row, col, it)
        self.tabs.setTabText(6, f"📋 گزارش ({len(t)} معامله)")

    def export_csv(self):
        if not self.last_report: return
        p, _ = QFileDialog.getSaveFileName(self, "ذخیره", "report.csv", "CSV (*.csv)")
        if not p: return
        try:
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                for k in ("total_trades", "wins", "losses", "win_rate",
                          "initial_balance", "final_balance", "total_profit"):
                    w.writerow([k, self.last_report.get(k)])
                w.writerow([])
                w.writerow(["#", "ورود", "خروج", "نوع", "ورود$",
                            "خروج$", "SL", "TP", "سود"])
                for i, t in enumerate(self.last_report["trades"], 1):
                    w.writerow([i, str(t.get("entry_time", ""))[:19],
                                str(t.get("exit_time", ""))[:19],
                                t.get("type", ""),
                                f"{t.get('entry', 0):.2f}",
                                f"{t.get('exit', 0):.2f}",
                                f"{t.get('sl', 0):.2f}",
                                f"{t.get('tp', 0):.2f}",
                                f"{t.get('profit', 0):+.2f}"])
            QMessageBox.information(self, "موفق", f"ذخیره شد:\n{p}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def clear_report(self):
        self.last_report = None; self.last_backtest_df = None
        for lb in (self.rp_tt, self.rp_w, self.rp_l, self.rp_wr,
                   self.rp_ib, self.rp_fb, self.rp_pf_, self.rp_pf,
                   self.rp_sharpe, self.rp_sortino, self.rp_calmar,
                   self.rp_exp, self.rp_dd, self.rp_aw, self.rp_al, self.rp_rf):
            lb.setText("—")
        self.tbl_m.setRowCount(0); self.tbl_t.setRowCount(0)
        self.tabs.setTabText(6, "📋 گزارش")
        self.append_log("گزارش پاک شد", "warn")

    def send_to_telegram(self):
        if not self.last_report:
            QMessageBox.information(self, "توجه", "گزارشی نیست."); return
        cfg = self._collect_config()
        tk = cfg.get("telegram_bot_token", "").strip()
        ch = cfg.get("telegram_chat_id", "").strip()
        if not tk or not ch:
            QMessageBox.warning(self, "خطا", "توکن/چت آیدی تنظیم نشده."); return
        n = TelegramNotifier(tk, ch, enabled=True)
        od = os.path.join(app_dir(), "reports"); os.makedirs(od, exist_ok=True)
        st = datetime.now().strftime("%Y%m%d_%H%M%S")
        ip = os.path.join(od, f"r_{st}.png")
        pp = os.path.join(od, f"r_{st}.pdf")
        cp = os.path.join(od, f"r_{st}.csv")
        self.append_log("ساخت فایل‌ها ...")
        try:
            render_report_image(self.last_report, ip)
            render_report_pdf(self.last_report, pp, chart_image=ip)
            with open(cp, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["#", "ورود", "خروج", "نوع", "ورود$", "خروج$", "سود"])
                for i, t in enumerate(self.last_report["trades"], 1):
                    w.writerow([i, str(t.get("entry_time", ""))[:19],
                                str(t.get("exit_time", ""))[:19],
                                t.get("type", ""),
                                f"{t.get('entry', 0):.2f}",
                                f"{t.get('exit', 0):.2f}",
                                f"{t.get('profit', 0):+.2f}"])
            n.send_backtest_report(self.last_report, ip, pp, cp)
            self.append_log("✅ ارسال شد", "success")
            QMessageBox.information(self, "موفق", "ارسال شد.")
        except Exception as e:
            self.append_log(f"خطا: {e}", "error")

    def _tab_optimizer(self):
        page = QWidget()
        v = QVBoxLayout(page); v.setContentsMargins(8,8,8,8); v.setSpacing(8)
        b = QGroupBox("⚙️ بهینه‌سازی"); b.setStyleSheet("QGroupBox{font-weight:bold;}")
        f = QGridLayout(b); f.setHorizontalSpacing(10); f.setVerticalSpacing(6)
        self.opt_symbol = QLineEdit(self.cfg["symbol"])
        self.opt_tf = QComboBox(); self.opt_tf.addItems(["M1","M5","M15"]); self.opt_tf.setCurrentText(self.cfg["timeframe"])
        t=QDate.currentDate(); self.opt_start=QDateEdit(t.addMonths(-2)); self.opt_end=QDateEdit(t)
        self.opt_start.setCalendarPopup(True); self.opt_end.setCalendarPopup(True)
        self.opt_start.setDisplayFormat("dd-MM-yyyy")
        self.opt_end.setDisplayFormat("dd-MM-yyyy")
        self.opt_start.setAlignment(Qt.AlignRight)
        self.opt_end.setAlignment(Qt.AlignRight)
        self.opt_start.setLayoutDirection(Qt.RightToLeft)
        self.opt_end.setLayoutDirection(Qt.RightToLeft)

        self.opt_balance=QDoubleSpinBox(); self.opt_balance.setRange(10,10_000_000); self.opt_balance.setValue(100.0); self.opt_balance.setSuffix(" $")
        self.opt_obj=QComboBox(); self.opt_obj.addItems(["profit_factor","sharpe","calmar","net_profit"])
        self.opt_min=QSpinBox(); self.opt_min.setRange(1,10000); self.opt_min.setValue(5)
        controls=[("نماد:",self.opt_symbol),("TF:",self.opt_tf),("از:",self.opt_start),("تا:",self.opt_end),("موجودی:",self.opt_balance),("معیار:",self.opt_obj),("حداقل معامله:",self.opt_min)]
        for idx,(label,widget) in enumerate(controls):
            row = idx // 2
            col = (idx % 2) * 2
            lab = QLabel(label)
            lab.setMinimumWidth(78)
            lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            f.addWidget(lab, row, col, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
            widget.setMinimumWidth(135)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            f.addWidget(widget, row, col + 1)
        f.setColumnStretch(1, 1); f.setColumnStretch(3, 1)
        v.addWidget(b)
        gb=QGroupBox("🎛 مقادیر بهینه‌سازی (با کاما)"); gb.setStyleSheet("QGroupBox{font-weight:bold;}")
        gf=QGridLayout(gb); gf.setHorizontalSpacing(10); gf.setVerticalSpacing(6)
        self.g_atr=QLineEdit("1.0,1.5,2.0"); self.g_rr=QLineEdit("1.5,2.0,3.0")
        self.g_stop=QLineEdit("1.0,1.5"); self.g_limit=QLineEdit("1.0,1.5")
        self.g_adx_period=QLineEdit("14"); self.g_adx_threshold=QLineEdit("18,20,25"); self.g_candle_count=QLineEdit("3,4,5")
        params=[("ATR:",self.g_atr),("R:R:",self.g_rr),("Stop:",self.g_stop),("Limit:",self.g_limit),("ADX دوره:",self.g_adx_period),("ADX حداقل:",self.g_adx_threshold),("تعداد کندل توالی:",self.g_candle_count)]
        for idx,(label,widget) in enumerate(params):
            row = idx // 2
            col = (idx % 2) * 2
            lab = QLabel(label)
            lab.setMinimumWidth(92)
            lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            lab.setWordWrap(False)
            gf.addWidget(lab, row, col, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
            widget.setMinimumWidth(155)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            gf.addWidget(widget, row, col + 1)
        gf.setColumnStretch(1, 1); gf.setColumnStretch(3, 1)
        v.addWidget(gb)
        self.opt_prog=QProgressBar(); self.opt_prog.setFixedHeight(20); v.addWidget(self.opt_prog)
        self.opt_status=QLabel("آماده"); self.opt_status.setMinimumHeight(28); self.opt_status.setWordWrap(True); self.opt_status.setStyleSheet("color:#94a3b8;font-weight:bold;"); v.addWidget(self.opt_status)
        bs=QHBoxLayout()
        self.btn_opt_run=QPushButton("🚀 شروع"); self.btn_opt_run.setMinimumHeight(34); self.btn_opt_run.setStyleSheet("background:#7c3aed;color:white;font-weight:bold;padding:6px;border-radius:5px;"); self.btn_opt_run.clicked.connect(self.run_optimizer)
        self.btn_opt_stop=QPushButton("⏹ توقف"); self.btn_opt_stop.setMinimumHeight(34); self.btn_opt_stop.setStyleSheet("background:#dc2626;color:white;font-weight:bold;padding:6px;border-radius:5px;"); self.btn_opt_stop.clicked.connect(self.stop_optimizer); self.btn_opt_stop.setEnabled(False)
        bs.addWidget(self.btn_opt_run); bs.addWidget(self.btn_opt_stop); v.addLayout(bs)
        v.addWidget(QLabel("📊 نتایج"))
        self.tbl_opt=QTableWidget(); self.tbl_opt.setLayoutDirection(Qt.RightToLeft); self.tbl_opt.setAlternatingRowColors(True); self.tbl_opt.setWordWrap(True); self.tbl_opt.setMinimumHeight(220); self.tbl_opt.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding); self.tbl_opt.horizontalHeader().setMinimumSectionSize(80); self.tbl_opt.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.tbl_opt.verticalHeader().setVisible(False); v.addWidget(self.tbl_opt,1)
        self.opt_best=QLabel("بهترین: —"); self.opt_best.setWordWrap(True); self.opt_best.setMinimumHeight(42); self.opt_best.setStyleSheet("padding:6px;background:#dcfce7;color:#166534;border-radius:5px;font-weight:bold;"); v.addWidget(self.opt_best)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded); scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded); scroll.setWidget(page)
        return scroll

    def run_optimizer(self):
        if not MT5_AVAILABLE: return
        if self._opt_worker and self._opt_worker.is_alive():
            QMessageBox.warning(self, "هشدار", "در حال اجراست."); return
        cfg = self._collect_config()
        cfg["timeframe"] = self.opt_tf.currentText()
        cfg["symbol"] = self.opt_symbol.text().strip()

        def pl(s): return [float(x.strip()) for x in s.split(",") if x.strip()]

        sv = [float(x.strip()) for x in self.g_stop.text().split(",") if x.strip()]
        lv = [float(x.strip()) for x in self.g_limit.text().split(",") if x.strip()]
        adx_periods = [int(float(x.strip())) for x in self.g_adx_period.text().split(",") if x.strip()]
        adx_thresholds = pl(self.g_adx_threshold.text())
        candle_counts = [int(float(x.strip())) for x in self.g_candle_count.text().split(",") if x.strip()]
        grid = {
            "atr_multiplier": pl(self.g_atr.text()),
            "risk_reward": pl(self.g_rr.text()),
            "stop_distances": [",".join(str(x) for x in sv)],
            "limit_distances": [",".join(str(x) for x in lv)],
            "adx_period": adx_periods,
            "adx_threshold": adx_thresholds,
            "candle_sequence_count": candle_counts,
        }
        grid = {k: v for k, v in grid.items() if len(v) > 1}

        st = datetime(self.opt_start.date().year(), self.opt_start.date().month(),
                      self.opt_start.date().day())
        en = datetime(self.opt_end.date().year(), self.opt_end.date().month(),
                      self.opt_end.date().day(), 23, 59, 59)
        self.btn_opt_run.setEnabled(False); self.btn_opt_stop.setEnabled(True)
        self.opt_prog.setValue(0); self.opt_status.setText("شروع ...")
        br = self.opt_bridge; lg = self.log_bridge.new_log
        self._opt_worker = GridOptimizer(
            base_cfg=cfg, symbol=cfg["symbol"], start_dt=st, end_dt=en,
            initial_balance=self.opt_balance.value(), param_grid=grid,
            objective=self.opt_obj.currentText(), min_trades=self.opt_min.value(),
            progress_callback=lambda p, m: br.progress.emit(p, m),
            log_callback=lambda m, l="info": lg.emit(m, l),
            result_callback=lambda r: br.finished.emit(r))
        self._opt_worker.start()

    def _opt_progress(self, p, m):
        self.opt_prog.setValue(p); self.opt_status.setText(m)

    def _on_optimizer_finished(self, r):
        self.btn_opt_run.setEnabled(True); self.btn_opt_stop.setEnabled(False)
        self.opt_prog.setValue(100)
        if r is None: return
        self.opt_status.setText(f"کامل | {r['combinations_tested']} ترکیب")
        df = r.get("table")
        if df is not None and not df.empty:
            cols = list(df.columns)
            self.tbl_opt.setColumnCount(len(cols))
            self.tbl_opt.setHorizontalHeaderLabels(cols)
            self.tbl_opt.setRowCount(len(df))
            for i, row in df.iterrows():
                for j, col in enumerate(cols):
                    v = row[col]
                    txt = f"{v:.3f}" if isinstance(v, float) else str(v)
                    it = QTableWidgetItem(txt)
                    it.setTextAlignment(Qt.AlignCenter)
                    if col == "net_profit":
                        c = QColor("#22c55e") if v >= 0 else QColor("#ef4444")
                        it.setForeground(QBrush(c))
                    self.tbl_opt.setItem(i, j, it)
            self.tbl_opt.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        b = r.get("best")
        if b:
            cs = " | ".join(f"{k}={v}" for k, v in b["combo"].items())
            self.opt_best.setText(
                f"🏆 {cs}\n💰 {b['report']['total_profit']:+.2f}$ | "
                f"🎯 {b['report']['win_rate']:.1f}% | "
                f"📐 {b['report']['profit_factor']:.2f}")

    def stop_optimizer(self):
        if self._opt_worker: self._opt_worker.stop()

    def _collect_config(self):
        return {
            "symbol": self.inp_symbol.text().strip(),
            "timeframe": self.cmb_tf.currentText(),
            "timeframe_higher": self.cmb_tf_high.currentText(),
            "lot_size": self.inp_lot.value(),
            "max_loss_per_trade": self.inp_max_loss_per_trade.value(),
            "commission_per_lot": self.inp_comm_per_lot.value(),
            "strict_max_loss": self.chk_strict_max_loss.isChecked(),
            "stop_distances": self.inp_stop_d.text().strip(),
            "limit_distances": self.inp_limit_d.text().strip(),
            "risk_reward": self.inp_rr.value(),
            "atr_multiplier": self.inp_atr_mult.value(),
            "enable_adx": self.chk_adx.isChecked(),
            "adx_period": self.inp_adx_period.value(),
            "adx_threshold": self.inp_adx_threshold.value(),
            "enable_candle_sequence": self.chk_candle_sequence.isChecked(),
            "candle_sequence_count": self.inp_candle_count.value(),
            "partial_profit_step": self.inp_partial.value(),
            "partial_profit_fraction": self.inp_partial_frac.value(),
            "trailing_drop": self.inp_trail.value(),
            "max_daily_profit": self.inp_max_profit.value(),
            "max_daily_loss": self.inp_max_loss.value(),
            "trading_start_hour": self.inp_sh.value(),
            "trading_start_min": self.inp_sm.value(),
            "trading_end_hour": self.inp_eh.value(),
            "trading_end_min": self.inp_em.value(),
            "enable_smc": self.chk_smc.isChecked(),
            "enable_fvg": self.chk_fvg.isChecked(),
            "enable_price_action": self.chk_pa.isChecked(),
            "enable_higher_tf_confirm": self.chk_htf.isChecked(),
            "max_simultaneous_orders": self.inp_max_orders.value(),
            "telegram_bot_token": self.inp_tg_token.text().strip(),
            "telegram_chat_id": self.inp_tg_chat.text().strip(),
            "enable_telegram": self.chk_tg.isChecked(),
            "enable_loss_alert": self.chk_loss_alert.isChecked(),
            "loss_alert_threshold": self.inp_loss_alert_threshold.value(),
            "loop_interval_sec": self.inp_loop.value(),
        }

    def save_settings(self):
        save_config(self._collect_config())
        self.append_log("تنظیمات ذخیره شد", "success")

    def reset_to_defaults(self):
        reply = QMessageBox.question(
            self, "بازگشت به پیش‌فرض",
            "آیا مطمئن هستید که می‌خواهید همه تنظیمات به مقادیر پیش‌فرض برگردد؟\n"
            "این عمل قابل بازگشت نیست و تنظیمات فعلی ذخیره نخواهند شد.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            cfg = DEFAULT_CONFIG.copy()
            self.cfg = cfg

            self.inp_symbol.setText(str(cfg["symbol"]))
            self.cmb_tf.setCurrentText(str(cfg["timeframe"]))
            self.cmb_tf_high.setCurrentText(str(cfg["timeframe_higher"]))

            self.inp_stop_d.setText(str(cfg["stop_distances"]))
            self.inp_limit_d.setText(str(cfg["limit_distances"]))
            self.inp_lot.setValue(float(cfg["lot_size"]))
            self.inp_atr_mult.setValue(float(cfg["atr_multiplier"]))
            self.inp_rr.setValue(float(cfg["risk_reward"]))

            self.chk_adx.setChecked(bool(cfg["enable_adx"]))
            self.inp_adx_period.setValue(int(cfg["adx_period"]))
            self.inp_adx_threshold.setValue(float(cfg["adx_threshold"]))
            self.chk_candle_sequence.setChecked(bool(cfg["enable_candle_sequence"]))
            self.inp_candle_count.setValue(int(cfg["candle_sequence_count"]))

            self.chk_smc.setChecked(bool(cfg["enable_smc"]))
            self.chk_fvg.setChecked(bool(cfg["enable_fvg"]))
            self.chk_pa.setChecked(bool(cfg["enable_price_action"]))
            self.chk_htf.setChecked(bool(cfg["enable_higher_tf_confirm"]))

            self.inp_partial.setValue(float(cfg["partial_profit_step"]))
            self.inp_partial_frac.setValue(float(cfg["partial_profit_fraction"]))
            self.inp_trail.setValue(float(cfg["trailing_drop"]))
            self.inp_max_profit.setValue(float(cfg["max_daily_profit"]))
            self.inp_max_loss.setValue(float(cfg["max_daily_loss"]))
            self.inp_loop.setValue(int(cfg["loop_interval_sec"]))
            self.inp_max_orders.setValue(int(cfg["max_simultaneous_orders"]))
            self.inp_max_loss_per_trade.setValue(float(cfg["max_loss_per_trade"]))
            self.inp_comm_per_lot.setValue(float(cfg["commission_per_lot"]))
            self.chk_strict_max_loss.setChecked(bool(cfg["strict_max_loss"]))

            self.chk_loss_alert.setChecked(bool(cfg.get("enable_loss_alert", True)))
            self.inp_loss_alert_threshold.setValue(
                float(cfg.get("loss_alert_threshold", 10.0)))

            self.inp_sh.setValue(int(cfg["trading_start_hour"]))
            self.inp_sm.setValue(int(cfg["trading_start_min"]))
            self.inp_eh.setValue(int(cfg["trading_end_hour"]))
            self.inp_em.setValue(int(cfg["trading_end_min"]))
            self.inp_tg_token.setText(str(cfg["telegram_bot_token"]))
            self.inp_tg_chat.setText(str(cfg["telegram_chat_id"]))
            self.chk_tg.setChecked(bool(cfg["enable_telegram"]))

            save_config(cfg)
            self.append_log("↺ همه تنظیمات به مقادیر پیش‌فرض بازگشت", "success")
            QMessageBox.information(self, "انجام شد",
                                    "همه تنظیمات به مقادیر پیش‌فرض بازگشتند.")
        except Exception as e:
            self.append_log(f"خطا در بازگشت به پیش‌فرض: {e}", "error")
            QMessageBox.critical(self, "خطا", str(e))

    def start_bot(self):
        if self.bot and self.bot.is_alive(): return
        if not MT5_AVAILABLE:
            QMessageBox.warning(self, "خطا", "MT5 در دسترس نیست."); return
        self.cfg = self._collect_config()
        self.save_settings()
        self.bot = TradingBot(self.cfg, log_callback=self._bridge_log)
        self.bot.start()
        self.btn_start.setEnabled(False); self.btn_stop.setEnabled(True)
        self.append_log("ربات راه‌اندازی شد", "success")

    def stop_bot(self):
        if self.bot: self.bot.stop()
        self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)

    def closeEvent(self, e):
        try:
            if self.bot and self.bot.is_alive(): self.bot.stop()
            if self._opt_worker: self._opt_worker.stop()
        except Exception:
            pass
        e.accept()

    def _bridge_log(self, t, l="info"):
        self.log_bridge.new_log.emit(t, l)

    def append_log(self, t, l="info"):
        c = {"info": "#e2e8f0", "success": "#4ade80",
             "warn": "#fbbf24", "error": "#f87171"}.get(l, "#e2e8f0")
        html = (f'<div dir="rtl" style="color:{c};'
                f'font-family:Tahoma;font-size:11px;">{t}</div>')
        cur = self.log_view.textCursor()
        cur.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cur)
        self.log_view.insertHtml(html)
        self.log_view.insertPlainText("\n")
        self.log_view.moveCursor(QTextCursor.End)


# ============================================================
#                        main
# ============================================================
def _show_error(msg):
    try:
        with open(os.path.join(app_dir(), "error.log"), "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        b = QMessageBox()
        b.setWindowTitle("خطا")
        b.setIcon(QMessageBox.Critical)
        b.setText("خطا رخ داد. جزئیات در error.log")
        b.setDetailedText(msg)
        b.setLayoutDirection(Qt.RightToLeft)
        b.exec_()
    except Exception:
        pass
    print(msg)


def main():
    if not MT5_AVAILABLE:
        print("⚠️ MetaTrader5 نصب نیست — فقط رابط کاربری اجرا می‌شود.\n"
              "   برای نصب: pip install MetaTrader5 (فقط ویندوز)\n")
    try:
        app = QApplication(sys.argv)
        app.setLayoutDirection(Qt.RightToLeft)

        _wheel_filter = WheelEventFilter()
        app.installEventFilter(_wheel_filter)

    except Exception:
        _show_error("خطا QApplication:\n" + traceback.format_exc())
        return 1
    try:
        win = MainWindow()
        win.show()
    except Exception:
        _show_error("خطا در ساخت پنجره:\n" + traceback.format_exc())
        return 1
    try:
        return app.exec_()
    except Exception:
        _show_error("خطا حلقه اصلی:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())