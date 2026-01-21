import calendar
import csv
import glob
import os
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import messagebox, ttk


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV_DIR = os.path.join(BASE_DIR, "csv")
DATA_DIR = os.path.join(BASE_DIR, "data", "usdjpy", "m1")
JST_OFFSET = timedelta(hours=9)

DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y.%m.%d %H:%M",
)
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y%m%d",
)
CHART_HEIGHT = 520
CHART_BG = "#ffffff"
CHART_GRID = "#e0e0e0"
CHART_TEXT = "#333333"
CHART_AXIS = "#666666"
CHART_UP = "#2e7d32"
CHART_DOWN = "#c62828"
CHART_LEFT_PAD = 10
CHART_RIGHT_PAD = 80
CHART_TOP_PAD = 8
CHART_BOTTOM_PAD = 26
MAX_DRAW_BARS = 1500
EQUITY_HEIGHT = 260
ZOOM_MIN = 0.5
ZOOM_MAX = 3.0
ZOOM_STEP = 0.1
CHART_MIN_BAR_STEP = 5
CHART_MAX_BAR_STEP = 20
PIP_SIZE = 0.01
EQUITY_POINT_RADIUS = 3


def parse_datetime_text(text, is_end=False):
    text = (text or "").strip()
    if not text:
        raise ValueError("empty")
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    for fmt in DATE_FORMATS:
        try:
            base = datetime.strptime(text, fmt)
            if is_end:
                return base.replace(hour=23, minute=59)
            return base.replace(hour=0, minute=0)
        except ValueError:
            pass
    raise ValueError("format")


def parse_date_for_calendar(text):
    try:
        return parse_datetime_text(text, is_end=False).date()
    except ValueError:
        return date.today()


def parse_signal_datetime(text):
    text = (text or "").strip()
    if not text:
        return None
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def parse_flag(value):
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in ("1", "true", "yes", "y")


def normalize_action(text):
    if not text:
        return None
    cleaned = text.strip().upper()
    if cleaned in ("BUY", "LONG", "L"):
        return "BUY"
    if cleaned in ("SELL", "SHORT", "S"):
        return "SELL"
    return None


def format_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def format_price(value):
    return f"{value:.3f}"


def format_axis_time(dt, show_date):
    if show_date:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%H:%M")


def format_pips(value):
    return f"{value:.2f}"


def load_signals(csv_dir):
    signals = []
    errors = []
    if not os.path.isdir(csv_dir):
        return signals, ["サインの場所が見つかりません"]
    paths = sorted(glob.glob(os.path.join(csv_dir, "*.csv")))
    if not paths:
        return signals, ["サインのファイルがありません"]

    for path in paths:
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue
                for row in reader:
                    dt_text = row.get("datetime") or row.get("time") or row.get("日時")
                    action = row.get("action") or row.get("side") or row.get("売買")
                    symbol = row.get("symbol") or row.get("通貨")
                    if symbol and symbol.strip().upper() != "USDJPY":
                        continue
                    dt_jst = parse_signal_datetime(dt_text)
                    if not dt_jst:
                        continue
                    action_norm = normalize_action(action)
                    if not action_norm:
                        continue
                    tags = {
                        "is_boast": parse_flag(row.get("is_boast")),
                        "is_fear": parse_flag(row.get("is_fear")),
                        "is_stop": parse_flag(row.get("is_stop")),
                        "is_tp": parse_flag(row.get("is_tp")),
                    }
                    signals.append(
                        {
                            "time_jst": dt_jst,
                            "time_utc": dt_jst - JST_OFFSET,
                            "action": action_norm,
                            "source": row.get("source") or os.path.basename(path),
                            "tags": tags,
                        }
                    )
        except Exception as exc:
            errors.append(f"{os.path.basename(path)} の読み込み失敗: {exc}")

    signals.sort(key=lambda item: item["time_utc"])
    return signals, errors


class CalendarDialog(tk.Toplevel):
    def __init__(self, parent, target_var, initial_date):
        super().__init__(parent)
        self.target_var = target_var
        self.year = initial_date.year
        self.month = initial_date.month
        self.cal = calendar.Calendar(firstweekday=6)

        self.title("日付選択")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        header = ttk.Frame(self, padding=(10, 10, 10, 0))
        header.grid(row=0, column=0, sticky="ew")
        self.prev_btn = ttk.Button(header, text="前月", width=6, command=self.prev_month)
        self.prev_btn.grid(row=0, column=0, sticky="w")
        self.month_label = ttk.Label(header, text="")
        self.month_label.grid(row=0, column=1, padx=10)
        self.next_btn = ttk.Button(header, text="翌月", width=6, command=self.next_month)
        self.next_btn.grid(row=0, column=2, sticky="e")

        self.days_frame = ttk.Frame(self, padding=10)
        self.days_frame.grid(row=1, column=0)
        self.build_days()

        self.protocol("WM_DELETE_WINDOW", self.close)

    def build_days(self):
        for child in self.days_frame.winfo_children():
            child.destroy()

        self.month_label.configure(text=f"{self.year}年{self.month}月")
        weekdays = ["日", "月", "火", "水", "木", "金", "土"]
        for idx, label in enumerate(weekdays):
            ttk.Label(self.days_frame, text=label).grid(row=0, column=idx, padx=4, pady=2)

        weeks = self.cal.monthdayscalendar(self.year, self.month)
        for row_idx, week in enumerate(weeks, start=1):
            for col_idx, day_num in enumerate(week):
                if day_num == 0:
                    ttk.Label(self.days_frame, text=" ").grid(row=row_idx, column=col_idx, padx=2, pady=2)
                    continue
                btn = ttk.Button(
                    self.days_frame,
                    text=str(day_num),
                    width=3,
                    command=lambda d=day_num: self.select_day(d),
                )
                btn.grid(row=row_idx, column=col_idx, padx=2, pady=2)

    def select_day(self, day_num):
        self.target_var.set(f"{self.year:04d}-{self.month:02d}-{day_num:02d}")
        self.close()

    def prev_month(self):
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self.build_days()

    def next_month(self):
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self.build_days()

    def close(self):
        self.grab_release()
        self.destroy()


def iter_dates(start_date, end_date):
    day = start_date
    while day <= end_date:
        yield day
        day += timedelta(days=1)


def load_ohlc_range(data_dir, start_utc, end_utc):
    bars = []
    errors = []
    if not os.path.isdir(data_dir):
        return bars, {}, ["足データの場所が見つかりません"]

    for day in iter_dates(start_utc.date(), end_utc.date()):
        year_dir = os.path.join(data_dir, f"{day.year:04d}")
        path = os.path.join(year_dir, f"{day:%Y-%m-%d}.csv")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    time_text = row.get("time") or row.get("Time")
                    if not time_text:
                        continue
                    try:
                        bar_time = datetime.strptime(time_text.strip(), "%Y.%m.%d %H:%M")
                    except ValueError:
                        continue
                    if bar_time < start_utc or bar_time > end_utc:
                        continue
                    try:
                        bars.append(
                            {
                                "time": bar_time,
                                "open": float(row.get("open") or 0),
                                "high": float(row.get("high") or 0),
                                "low": float(row.get("low") or 0),
                                "close": float(row.get("close") or 0),
                            }
                        )
                    except ValueError:
                        continue
        except Exception as exc:
            errors.append(f"{path} の読み込み失敗: {exc}")

    bars.sort(key=lambda item: item["time"])
    index_by_time = {bar["time"]: idx for idx, bar in enumerate(bars)}
    return bars, index_by_time, errors


def simulate_trade(
    bars,
    start_idx,
    end_idx,
    direction,
    stop,
    limit,
    spread,
    stop_limit_enabled,
    time_limit_enabled,
    time_limit_min,
):
    half = spread / 2.0
    entry_mid = bars[start_idx]["close"]
    entry_time = bars[start_idx]["time"]
    time_idx = None
    if time_limit_enabled and time_limit_min is not None:
        time_idx = start_idx + time_limit_min
        if time_idx > end_idx:
            time_idx = None

    if direction == "BUY":
        entry_price = entry_mid + half
        stop_price = entry_price - stop
        limit_price = entry_price + limit
        stop_trigger = stop_price + half
        limit_trigger = limit_price + half
        for idx in range(start_idx + 1, end_idx + 1):
            bar = bars[idx]
            low = bar["low"]
            high = bar["high"]
            hit_stop = stop_limit_enabled and stop > 0 and low <= stop_trigger
            hit_limit = stop_limit_enabled and limit > 0 and high >= limit_trigger
            if hit_stop and hit_limit:
                return {
                    "exit_reason": "stop",
                    "exit_price": stop_price,
                    "exit_time": bar["time"],
                }
            if hit_stop:
                return {
                    "exit_reason": "stop",
                    "exit_price": stop_price,
                    "exit_time": bar["time"],
                }
            if hit_limit:
                return {
                    "exit_reason": "limit",
                    "exit_price": limit_price,
                    "exit_time": bar["time"],
                }
            if time_idx is not None and idx >= time_idx:
                exit_mid = bar["close"]
                return {
                    "exit_reason": "time",
                    "exit_price": exit_mid - half,
                    "exit_time": bar["time"],
                }
        exit_mid = bars[end_idx]["close"]
        return {
            "exit_reason": "end",
            "exit_price": exit_mid - half,
            "exit_time": bars[end_idx]["time"],
        }

    entry_price = entry_mid - half
    stop_price = entry_price + stop
    limit_price = entry_price - limit
    stop_trigger = stop_price - half
    limit_trigger = limit_price - half
    for idx in range(start_idx + 1, end_idx + 1):
        bar = bars[idx]
        low = bar["low"]
        high = bar["high"]
        hit_stop = stop_limit_enabled and stop > 0 and high >= stop_trigger
        hit_limit = stop_limit_enabled and limit > 0 and low <= limit_trigger
        if hit_stop and hit_limit:
            return {
                "exit_reason": "stop",
                "exit_price": stop_price,
                "exit_time": bar["time"],
            }
        if hit_stop:
            return {
                "exit_reason": "stop",
                "exit_price": stop_price,
                "exit_time": bar["time"],
            }
        if hit_limit:
            return {
                "exit_reason": "limit",
                "exit_price": limit_price,
                "exit_time": bar["time"],
            }
        if time_idx is not None and idx >= time_idx:
            exit_mid = bar["close"]
            return {
                "exit_reason": "time",
                "exit_price": exit_mid + half,
                "exit_time": bar["time"],
            }
    exit_mid = bars[end_idx]["close"]
    return {
        "exit_reason": "end",
        "exit_price": exit_mid + half,
        "exit_time": bars[end_idx]["time"],
    }


class BacktestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("USDJPY バックテスト")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.signals = []
        self.chart_data = None
        self.equity_data = None
        self.zoom_var = tk.DoubleVar(value=1.5)
        self.zoom_text_var = tk.StringVar(value="")
        self.timezone_var = tk.StringVar(value="JST")
        self.stop_limit_enabled_var = tk.BooleanVar(value=True)
        self.time_limit_enabled_var = tk.BooleanVar(value=True)
        self.time_limit_var = tk.StringVar(value="30")
        self.filter_boast_var = tk.BooleanVar(value=False)
        self.filter_fear_var = tk.BooleanVar(value=False)
        self.filter_stop_var = tk.BooleanVar(value=False)
        self.filter_tp_var = tk.BooleanVar(value=False)
        self.drag_start_y = 0

        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.stop_var = tk.StringVar(value="20")
        self.limit_var = tk.StringVar(value="20")
        self.spread_var = tk.StringVar(value="1")
        self.info_var = tk.StringVar(value="サイン件数: -")

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.tab_chart = ttk.Frame(self.notebook)
        self.tab_pnl = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chart, text="チャート")
        self.notebook.add(self.tab_pnl, text="損益")
        self.tab_chart.rowconfigure(0, weight=1)
        self.tab_chart.columnconfigure(0, weight=1)
        self.tab_pnl.rowconfigure(1, weight=1)
        self.tab_pnl.columnconfigure(0, weight=1)

        top = ttk.Frame(self.tab_chart, padding=6)
        top.grid(sticky="nsew")

        ttk.Label(top, textvariable=self.info_var).grid(row=0, column=0, columnspan=6, sticky="w")

        ttk.Label(top, text="開始(日本時間)").grid(row=1, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(top, textvariable=self.start_var, width=22).grid(row=1, column=1, sticky="w", pady=(8, 2))
        ttk.Button(top, text="日付", command=lambda: self.open_calendar(self.start_var)).grid(
            row=1, column=2, sticky="w", padx=(6, 0), pady=(8, 2)
        )
        ttk.Label(top, text="終了(日本時間)").grid(row=1, column=3, sticky="w", padx=(12, 0), pady=(8, 2))
        end_frame = ttk.Frame(top)
        end_frame.grid(row=1, column=4, sticky="w", pady=(8, 2))
        ttk.Entry(end_frame, textvariable=self.end_var, width=22).grid(row=0, column=0, sticky="w")
        ttk.Button(end_frame, text="日付", command=lambda: self.open_calendar(self.end_var)).grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )

        ttk.Label(top, text="ストップ幅(0.01=1)").grid(row=2, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.stop_var, width=12).grid(row=2, column=1, sticky="w")
        ttk.Label(top, text="リミット幅(0.01=1)").grid(row=2, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(top, textvariable=self.limit_var, width=12).grid(row=2, column=3, sticky="w")

        ttk.Label(top, text="スプレッド(0.01=1)").grid(row=3, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.spread_var, width=12).grid(row=3, column=1, sticky="w")

        self.run_btn = ttk.Button(top, text="実行", command=self.run_backtest)
        self.run_btn.grid(row=3, column=2, sticky="w", padx=(12, 0))
        ttk.Button(top, text="再読込", command=self.reload_signals).grid(row=3, column=3, sticky="w")

        exit_opts = ttk.Frame(top)
        exit_opts.grid(row=4, column=0, columnspan=6, sticky="w", pady=(4, 0))
        ttk.Checkbutton(exit_opts, text="ストップ/リミットを使う", variable=self.stop_limit_enabled_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(exit_opts, text="時間クローズ", variable=self.time_limit_enabled_var).grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        ttk.Entry(exit_opts, textvariable=self.time_limit_var, width=6).grid(row=0, column=2, padx=(6, 2))
        ttk.Label(exit_opts, text="分経過でクローズ").grid(row=0, column=3, sticky="w")

        filter_opts = ttk.Frame(top)
        filter_opts.grid(row=5, column=0, columnspan=6, sticky="w", pady=(4, 0))
        ttk.Label(filter_opts, text="理由で絞り込み").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(filter_opts, text="自慢", variable=self.filter_boast_var).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        ttk.Checkbutton(filter_opts, text="恐怖", variable=self.filter_fear_var).grid(
            row=0, column=2, sticky="w", padx=(8, 0)
        )
        ttk.Checkbutton(filter_opts, text="損切り", variable=self.filter_stop_var).grid(
            row=0, column=3, sticky="w", padx=(8, 0)
        )
        ttk.Checkbutton(filter_opts, text="利確", variable=self.filter_tp_var).grid(
            row=0, column=4, sticky="w", padx=(8, 0)
        )
        ttk.Label(filter_opts, text="(どれかに該当で対象)").grid(row=0, column=5, sticky="w", padx=(8, 0))

        chart_ctrl = ttk.Frame(top)
        chart_ctrl.grid(row=6, column=0, columnspan=6, pady=(4, 0), sticky="ew")
        ttk.Label(chart_ctrl, text="表示倍率").grid(row=0, column=0, sticky="w")
        self.zoom_scale = ttk.Scale(
            chart_ctrl,
            from_=ZOOM_MIN,
            to=ZOOM_MAX,
            variable=self.zoom_var,
            command=self.on_zoom_change,
        )
        self.zoom_scale.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(chart_ctrl, textvariable=self.zoom_text_var).grid(row=0, column=2, sticky="w")
        ttk.Button(chart_ctrl, text="縮小", command=lambda: self.adjust_zoom(-1)).grid(row=0, column=3, padx=(12, 4))
        ttk.Button(chart_ctrl, text="拡大", command=lambda: self.adjust_zoom(1)).grid(row=0, column=4, padx=(0, 4))
        ttk.Label(chart_ctrl, text="時刻表示").grid(row=0, column=5, sticky="w", padx=(12, 4))
        ttk.Radiobutton(
            chart_ctrl,
            text="JST",
            variable=self.timezone_var,
            value="JST",
            command=self.on_timezone_change,
        ).grid(row=0, column=6, sticky="w")
        ttk.Radiobutton(
            chart_ctrl,
            text="UTC",
            variable=self.timezone_var,
            value="UTC",
            command=self.on_timezone_change,
        ).grid(row=0, column=7, sticky="w")
        chart_ctrl.columnconfigure(1, weight=1)

        self.chart_frame = ttk.Frame(top)
        self.chart_frame.grid(row=7, column=0, columnspan=6, pady=(2, 0), sticky="nsew")
        self.chart = tk.Canvas(
            self.chart_frame,
            background=CHART_BG,
            highlightthickness=0,
            height=CHART_HEIGHT,
        )
        self.chart.grid(row=0, column=0, sticky="nsew")
        self.chart_hbar = ttk.Scrollbar(self.chart_frame, orient="horizontal", command=self.on_xscroll)
        self.chart_hbar.grid(row=1, column=0, sticky="ew")
        self.chart_vbar = ttk.Scrollbar(self.chart_frame, orient="vertical", command=self.on_yscroll)
        self.chart_vbar.grid(row=0, column=1, sticky="ns")
        self.chart.configure(xscrollcommand=self.chart_hbar.set, yscrollcommand=self.chart_vbar.set)
        self.chart_frame.columnconfigure(0, weight=1)
        self.chart_frame.rowconfigure(0, weight=1)
        self.chart.bind("<Configure>", self.on_canvas_resize)
        self.chart.bind("<MouseWheel>", self.on_mouse_wheel)
        self.chart.bind("<ButtonPress-1>", self.on_chart_drag_start)
        self.chart.bind("<B1-Motion>", self.on_chart_drag_move)

        self.text = tk.Text(top, width=90, height=16)
        self.text.grid(row=8, column=0, columnspan=6, pady=(12, 0), sticky="nsew")
        self.text.configure(state="disabled")
        scroll = ttk.Scrollbar(top, command=self.text.yview)
        scroll.grid(row=8, column=6, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        top.columnconfigure(4, weight=1)
        top.rowconfigure(7, weight=6)
        top.rowconfigure(8, weight=2)

        stats = ttk.Frame(self.tab_pnl, padding=10)
        stats.grid(row=0, column=0, sticky="ew")
        stats.columnconfigure(1, weight=1)

        self.total_pips_var = tk.StringVar(value="-")
        self.max_dd_var = tk.StringVar(value="-")
        self.trade_count_var = tk.StringVar(value="-")
        self.win_rate_var = tk.StringVar(value="-")
        self.pf_var = tk.StringVar(value="-")

        ttk.Label(stats, text="総損益(pips)").grid(row=0, column=0, sticky="w")
        ttk.Label(stats, textvariable=self.total_pips_var).grid(row=0, column=1, sticky="w", padx=(8, 20))
        ttk.Label(stats, text="最大ドローダウン(pips)").grid(row=1, column=0, sticky="w")
        ttk.Label(stats, textvariable=self.max_dd_var).grid(row=1, column=1, sticky="w", padx=(8, 20))
        ttk.Label(stats, text="トレード総数").grid(row=2, column=0, sticky="w")
        ttk.Label(stats, textvariable=self.trade_count_var).grid(row=2, column=1, sticky="w", padx=(8, 20))
        ttk.Label(stats, text="勝ちトレード").grid(row=3, column=0, sticky="w")
        ttk.Label(stats, textvariable=self.win_rate_var).grid(row=3, column=1, sticky="w", padx=(8, 20))
        ttk.Label(stats, text="プロフィットファクター").grid(row=4, column=0, sticky="w")
        ttk.Label(stats, textvariable=self.pf_var).grid(row=4, column=1, sticky="w", padx=(8, 20))

        self.equity_chart = tk.Canvas(
            self.tab_pnl,
            background=CHART_BG,
            highlightthickness=0,
            height=EQUITY_HEIGHT,
        )
        self.equity_chart.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.equity_chart.bind("<Configure>", self.on_equity_resize)

        self.update_zoom_label()
        self.reload_signals()

    def log(self, message):
        self.text.configure(state="normal")
        self.text.insert("end", message + "\n")
        self.text.configure(state="disabled")
        self.text.see("end")

    def clear_log(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def reset_stats(self):
        self.total_pips_var.set("-")
        self.max_dd_var.set("-")
        self.trade_count_var.set("-")
        self.win_rate_var.set("-")
        self.pf_var.set("-")

    def selected_tag_keys(self):
        selected = []
        if self.filter_boast_var.get():
            selected.append("is_boast")
        if self.filter_fear_var.get():
            selected.append("is_fear")
        if self.filter_stop_var.get():
            selected.append("is_stop")
        if self.filter_tp_var.get():
            selected.append("is_tp")
        return selected

    def filter_signals_by_tags(self, signals):
        selected = self.selected_tag_keys()
        if not selected:
            return signals, None
        filtered = []
        for item in signals:
            tags = item.get("tags") or {}
            if any(tags.get(key) for key in selected):
                filtered.append(item)
        return filtered, selected

    def display_time(self, dt):
        if self.timezone_var.get() == "JST":
            return dt + JST_OFFSET
        return dt

    def on_timezone_change(self):
        if self.chart_data:
            bars, results = self.chart_data
            self.draw_chart(bars, results)
        if self.equity_data is not None:
            self.draw_equity_chart(self.equity_data)

    def reload_signals(self):
        self.signals, errors = load_signals(CSV_DIR)
        if errors:
            for item in errors:
                self.log(item)
        if self.signals:
            min_jst = min(item["time_jst"] for item in self.signals)
            max_jst = max(item["time_jst"] for item in self.signals)
            self.info_var.set(f"サイン件数: {len(self.signals)} 期間: {format_dt(min_jst)} ～ {format_dt(max_jst)}")
            if not self.start_var.get().strip():
                self.start_var.set(format_dt(min_jst))
            if not self.end_var.get().strip():
                self.end_var.set(format_dt(max_jst))
        else:
            self.info_var.set("サイン件数: 0")

    def open_calendar(self, target_var):
        base = parse_date_for_calendar(target_var.get())
        CalendarDialog(self.root, target_var, base)

    def update_zoom_label(self):
        percent = int(self.zoom_var.get() * 100)
        self.zoom_text_var.set(f"表示倍率: {percent}%")

    def set_zoom(self, value):
        if value < ZOOM_MIN:
            value = ZOOM_MIN
        if value > ZOOM_MAX:
            value = ZOOM_MAX
        current = float(self.zoom_var.get())
        if abs(current - value) > 1e-6:
            self.zoom_var.set(value)
        self.update_zoom_label()
        if self.chart_data:
            bars, results = self.chart_data
            self.draw_chart(bars, results)

    def on_zoom_change(self, _value):
        self.set_zoom(float(self.zoom_var.get()))

    def adjust_zoom(self, direction):
        current = float(self.zoom_var.get())
        next_value = current + (ZOOM_STEP * direction)
        self.set_zoom(next_value)

    def on_mouse_wheel(self, event):
        if event.state & 0x0004:
            direction = 1 if event.delta > 0 else -1
            self.adjust_zoom(direction)
            return
        if event.state & 0x0001:
            delta = -1 if event.delta > 0 else 1
            self.chart.xview_scroll(delta, "units")
            if self.chart_data:
                bars, results = self.chart_data
                self.draw_chart(bars, results)
            return
        delta = -1 if event.delta > 0 else 1
        self.chart.yview_scroll(delta, "units")

    def on_chart_drag_start(self, event):
        self.drag_start_y = event.y
        self.chart.scan_mark(event.x, event.y)

    def on_chart_drag_move(self, event):
        self.chart.scan_dragto(event.x, self.drag_start_y, gain=1)
        if self.chart_data:
            bars, results = self.chart_data
            self.draw_chart(bars, results)

    def on_xscroll(self, *args):
        self.chart.xview(*args)
        if self.chart_data:
            bars, results = self.chart_data
            self.draw_chart(bars, results)

    def on_yscroll(self, *args):
        self.chart.yview(*args)

    def clear_chart(self):
        self.chart.delete("all")
        self.chart.configure(scrollregion=(0, 0, 0, 0))
        self.chart_data = None

    def clear_equity_chart(self):
        self.equity_chart.delete("all")
        self.equity_data = None

    def on_equity_resize(self, event):
        if self.equity_data is not None:
            self.draw_equity_chart(self.equity_data)

    def on_canvas_resize(self, event):
        if self.chart_data:
            bars, results = self.chart_data
            self.draw_chart(bars, results)

    def draw_arrow(self, x, y, direction, color):
        size = 6
        if direction == "up":
            points = (x, y - size, x - size, y + size, x + size, y + size)
        else:
            points = (x, y + size, x - size, y - size, x + size, y - size)
        self.chart.create_polygon(points, fill=color, outline=color)

    def draw_chart(self, bars, results):
        xview = self.chart.xview()
        yview = self.chart.yview()
        self.chart.delete("all")
        if not bars:
            self.chart_data = None
            return
        self.chart_data = (bars, results)

        width = self.chart.winfo_width()
        height = self.chart.winfo_height()
        if width <= 1:
            width = 900
        if height <= 1:
            height = CHART_HEIGHT

        left = CHART_LEFT_PAD
        right = CHART_RIGHT_PAD
        top = CHART_TOP_PAD
        bottom = CHART_BOTTOM_PAD
        count = len(bars)
        zoom = float(self.zoom_var.get())
        bar_step = CHART_MIN_BAR_STEP * zoom
        if bar_step < 1:
            bar_step = 1
        if bar_step > CHART_MAX_BAR_STEP:
            bar_step = CHART_MAX_BAR_STEP
        base_w = left + right + max(1, (count - 1)) * bar_step
        content_w = max(width, int(base_w))
        content_h = max(height, top + bottom + 1)
        plot_w = max(1, content_w - left - right)
        plot_h = max(1, content_h - top - bottom)
        self.chart.configure(scrollregion=(0, 0, content_w, content_h))

        view_left = xview[0] * content_w
        view_right = xview[1] * content_w
        if view_right - view_left < 1:
            view_left = 0
            view_right = width

        visible_bars = bars
        start_idx = 0
        end_idx = count - 1
        if count > 1 and bar_step > 0:
            start_idx = int((view_left - left) / bar_step) - 2
            end_idx = int((view_right - left) / bar_step) + 2
            if start_idx < 0:
                start_idx = 0
            if end_idx >= count:
                end_idx = count - 1
            if end_idx < start_idx:
                start_idx = 0
                end_idx = count - 1
            visible_bars = bars[start_idx : end_idx + 1]

        min_p = min(bar["low"] for bar in visible_bars)
        max_p = max(bar["high"] for bar in visible_bars)
        if max_p == min_p:
            max_p += PIP_SIZE
            min_p -= PIP_SIZE

        def price_to_y(price):
            return top + (max_p - price) / (max_p - min_p) * plot_h

        def index_to_x(idx):
            if count == 1:
                return left + plot_w / 2
            return left + idx * bar_step

        axis_x = view_right - 6
        grid_left = view_left + left
        grid_right = view_right - right
        if grid_right <= grid_left:
            grid_right = view_right - 2

        ticks = 6
        for i in range(ticks):
            price = min_p + (max_p - min_p) * i / (ticks - 1)
            y = price_to_y(price)
            self.chart.create_line(grid_left, y, grid_right, y, fill=CHART_GRID)
            self.chart.create_text(axis_x, y, text=format_price(price), anchor="e", fill=CHART_TEXT)
        self.chart.create_line(grid_right, top, grid_right, top + plot_h, fill=CHART_AXIS)

        show_date = self.display_time(bars[0]["time"]).date() != self.display_time(bars[-1]["time"]).date()
        visible_count = end_idx - start_idx + 1
        time_ticks = min(6, visible_count) if visible_count > 1 else 1
        for i in range(time_ticks):
            idx = start_idx if time_ticks == 1 else int(start_idx + (visible_count - 1) * i / (time_ticks - 1))
            x = index_to_x(idx)
            bar_time = self.display_time(bars[idx]["time"])
            label = format_axis_time(bar_time, show_date)
            self.chart.create_line(x, top, x, top + plot_h, fill=CHART_GRID)
            self.chart.create_text(x, top + plot_h + 8, text=label, anchor="n", fill=CHART_TEXT)

        body_w = max(1, bar_step * 0.6)
        if body_w > 12:
            body_w = 12
        for idx in range(start_idx, end_idx + 1):
            bar = bars[idx]
            x = index_to_x(idx)
            y_high = price_to_y(bar["high"])
            y_low = price_to_y(bar["low"])
            y_open = price_to_y(bar["open"])
            y_close = price_to_y(bar["close"])
            color = CHART_UP if bar["close"] >= bar["open"] else CHART_DOWN
            self.chart.create_line(x, y_high, x, y_low, fill=color)
            y_top = min(y_open, y_close)
            y_bot = max(y_open, y_close)
            if y_bot - y_top < 1:
                y_bot = y_top + 1
            self.chart.create_rectangle(
                x - body_w / 2,
                y_top,
                x + body_w / 2,
                y_bot,
                fill=color,
                outline=color,
            )

        index_by_time = {bar["time"]: idx for idx, bar in enumerate(bars)}
        for item in results:
            entry_idx = index_by_time.get(item["entry_time"])
            exit_idx = index_by_time.get(item["exit_time"])
            if entry_idx is not None and exit_idx is not None:
                x1 = index_to_x(entry_idx)
                y1 = price_to_y(item["entry_price"])
                x2 = index_to_x(exit_idx)
                y2 = price_to_y(item["exit_price"])
                line_color = CHART_UP if item["action"] == "BUY" else CHART_DOWN
                self.chart.create_line(x1, y1, x2, y2, fill=line_color, dash=(4, 4))

        for item in results:
            color = CHART_UP if item["action"] == "BUY" else CHART_DOWN
            entry_idx = index_by_time.get(item["entry_time"])
            if entry_idx is not None:
                x = index_to_x(entry_idx)
                y = price_to_y(item["entry_price"])
                direction = "up" if item["action"] == "BUY" else "down"
                self.draw_arrow(x, y, direction, color)
            exit_idx = index_by_time.get(item["exit_time"])
            if exit_idx is not None:
                x = index_to_x(exit_idx)
                y = price_to_y(item["exit_price"])
                direction = "down" if item["action"] == "BUY" else "up"
                self.draw_arrow(x, y, direction, color)

        self.chart.create_text(
            grid_left,
            4,
            text="買い=上矢印 / 売り=下矢印 / クローズ=逆矢印",
            anchor="nw",
            fill=CHART_TEXT,
        )
        tz_label = "JST" if self.timezone_var.get() == "JST" else "UTC"
        self.chart.create_text(
            grid_left,
            18,
            text=f"時刻: {tz_label}",
            anchor="nw",
            fill=CHART_TEXT,
        )
        self.chart.xview_moveto(xview[0])
        self.chart.yview_moveto(yview[0])

    def draw_equity_chart(self, points):
        self.equity_chart.delete("all")
        self.equity_data = points
        width = self.equity_chart.winfo_width()
        height = self.equity_chart.winfo_height()
        if width <= 1:
            width = 900
        if height <= 1:
            height = EQUITY_HEIGHT

        left = CHART_LEFT_PAD
        right = CHART_RIGHT_PAD
        top = CHART_TOP_PAD
        bottom = CHART_BOTTOM_PAD
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)

        if not points:
            self.equity_chart.create_text(
                width / 2,
                height / 2,
                text="損益データなし",
                fill=CHART_TEXT,
            )
            return

        values = [p["value"] for p in points]
        min_v = min(values)
        max_v = max(values)
        if max_v == min_v:
            max_v += 1.0
            min_v -= 1.0

        def value_to_y(value):
            return top + (max_v - value) / (max_v - min_v) * plot_h

        count = len(points)
        if count == 1:
            step_x = 0
        else:
            step_x = plot_w / (count - 1)

        def index_to_x(idx):
            if count == 1:
                return left + plot_w / 2
            return left + idx * step_x

        axis_x = width - 6
        ticks = 6
        for i in range(ticks):
            value = min_v + (max_v - min_v) * i / (ticks - 1)
            y = value_to_y(value)
            self.equity_chart.create_line(left, y, width - right, y, fill=CHART_GRID)
            self.equity_chart.create_text(axis_x, y, text=format_pips(value), anchor="e", fill=CHART_TEXT)
        self.equity_chart.create_line(width - right, top, width - right, top + plot_h, fill=CHART_AXIS)

        show_date = self.display_time(points[0]["time"]).date() != self.display_time(points[-1]["time"]).date()
        time_ticks = min(6, count) if count > 1 else 1
        for i in range(time_ticks):
            idx = 0 if time_ticks == 1 else int((count - 1) * i / (time_ticks - 1))
            x = index_to_x(idx)
            label = format_axis_time(self.display_time(points[idx]["time"]), show_date)
            self.equity_chart.create_line(x, top, x, top + plot_h, fill=CHART_GRID)
            self.equity_chart.create_text(x, top + plot_h + 8, text=label, anchor="n", fill=CHART_TEXT)

        if min_v < 0 < max_v:
            zero_y = value_to_y(0)
            self.equity_chart.create_line(left, zero_y, width - right, zero_y, fill=CHART_AXIS, dash=(2, 2))

        last_x = None
        last_y = None
        for idx, point in enumerate(points):
            x = index_to_x(idx)
            y = value_to_y(point["value"])
            if last_x is not None:
                self.equity_chart.create_line(last_x, last_y, x, y, fill=CHART_UP)
            self.equity_chart.create_oval(
                x - EQUITY_POINT_RADIUS,
                y - EQUITY_POINT_RADIUS,
                x + EQUITY_POINT_RADIUS,
                y + EQUITY_POINT_RADIUS,
                fill=CHART_UP,
                outline=CHART_UP,
            )
            last_x = x
            last_y = y

        self.equity_chart.create_text(
            left,
            4,
            text="損益の変動(pips)",
            anchor="nw",
            fill=CHART_TEXT,
        )
        tz_label = "JST" if self.timezone_var.get() == "JST" else "UTC"
        self.equity_chart.create_text(
            left,
            18,
            text=f"時刻: {tz_label}",
            anchor="nw",
            fill=CHART_TEXT,
        )

    def update_stats(self, results):
        total = len(results)
        self.trade_count_var.set(str(total))
        if total == 0:
            self.total_pips_var.set("0.00")
            self.max_dd_var.set("0.00")
            self.win_rate_var.set("0.00% 0/0")
            self.pf_var.set("計算不可")
            return

        pips_list = [r["pnl"] / PIP_SIZE for r in results]
        total_pips = sum(pips_list)
        wins = sum(1 for p in pips_list if p > 0)
        losses = sum(1 for p in pips_list if p < 0)
        win_rate = wins / total * 100
        win_text = f"{win_rate:.2f}% {wins}/{total}"

        profit_sum = sum(p for p in pips_list if p > 0)
        loss_sum = sum(p for p in pips_list if p < 0)
        if loss_sum == 0:
            pf_text = "計算不可"
        else:
            pf_text = f"{profit_sum / abs(loss_sum):.3f}"

        equity = 0.0
        max_dd = 0.0
        peak = 0.0
        for p in pips_list:
            equity += p
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        self.total_pips_var.set(format_pips(total_pips))
        self.max_dd_var.set(format_pips(max_dd))
        self.win_rate_var.set(win_text)
        self.pf_var.set(pf_text)

    def run_backtest(self):
        self.clear_log()
        self.clear_chart()
        self.clear_equity_chart()
        self.reset_stats()
        if not self.signals:
            self.reload_signals()
        if not self.signals:
            messagebox.showerror("エラー", "サインがありません")
            return

        try:
            start_jst = parse_datetime_text(self.start_var.get(), is_end=False)
            end_jst = parse_datetime_text(self.end_var.get(), is_end=True)
        except ValueError:
            messagebox.showerror("エラー", "開始と終了は日時で入力してください")
            return
        if start_jst > end_jst:
            messagebox.showerror("エラー", "開始が終了より後です")
            return
        stop_limit_enabled = bool(self.stop_limit_enabled_var.get())
        time_limit_enabled = bool(self.time_limit_enabled_var.get())

        try:
            spread_pips = float(self.spread_var.get().strip())
        except ValueError:
            messagebox.showerror("エラー", "スプレッドの値が数値ではありません")
            return
        if spread_pips < 0:
            messagebox.showerror("エラー", "スプレッドの値は0以上で入力してください")
            return

        stop_pips = 0.0
        limit_pips = 0.0
        if stop_limit_enabled:
            try:
                stop_pips = float(self.stop_var.get().strip())
                limit_pips = float(self.limit_var.get().strip())
            except ValueError:
                messagebox.showerror("エラー", "ストップ/リミットの値が数値ではありません")
                return
            if stop_pips < 0 or limit_pips < 0:
                messagebox.showerror("エラー", "ストップ/リミットは0以上で入力してください")
                return

        time_limit_min = None
        if time_limit_enabled:
            try:
                time_limit_min = int(self.time_limit_var.get().strip())
            except ValueError:
                messagebox.showerror("エラー", "時間クローズは分で入力してください")
                return
            if time_limit_min < 1:
                messagebox.showerror("エラー", "時間クローズは1以上で入力してください")
                return

        stop = stop_pips * PIP_SIZE
        limit = limit_pips * PIP_SIZE
        spread = spread_pips * PIP_SIZE

        start_utc = start_jst - JST_OFFSET
        end_utc = end_jst - JST_OFFSET

        bars, index_by_time, bar_errors = load_ohlc_range(DATA_DIR, start_utc, end_utc)
        for item in bar_errors:
            self.log(item)
        if not bars:
            self.log("足データが読み込めません")
            return

        period_signals = [
            item for item in self.signals if start_utc <= item["time_utc"] <= end_utc
        ]
        self.log(f"サイン総数: {len(self.signals)}")
        self.log(f"期間内サイン: {len(period_signals)}")

        period_signals, selected_tags = self.filter_signals_by_tags(period_signals)
        if selected_tags is not None:
            label_map = {
                "is_boast": "自慢",
                "is_fear": "恐怖",
                "is_stop": "損切り",
                "is_tp": "利確",
            }
            labels = [label_map.get(key, key) for key in selected_tags]
            self.log(f"理由絞り込み: {' / '.join(labels)} -> {len(period_signals)}")

        if not period_signals:
            self.draw_chart(bars, [])
            self.draw_equity_chart([])
            self.update_stats([])
            self.log("期間内のサインがありません")
            return

        end_idx = len(bars) - 1
        results = []
        missing = 0

        for signal in period_signals:
            idx = index_by_time.get(signal["time_utc"])
            if idx is None:
                missing += 1
                continue
            trade = simulate_trade(
                bars,
                idx,
                end_idx,
                signal["action"],
                stop,
                limit,
                spread,
                stop_limit_enabled,
                time_limit_enabled,
                time_limit_min,
            )
            entry_mid = bars[idx]["close"]
            half = spread / 2.0
            entry_price = entry_mid + half if signal["action"] == "BUY" else entry_mid - half
            pnl = (
                trade["exit_price"] - entry_price
                if signal["action"] == "BUY"
                else entry_price - trade["exit_price"]
            )
            results.append(
                {
                    "action": signal["action"],
                    "entry_time": signal["time_utc"],
                    "entry_price": entry_price,
                    "exit_time": trade["exit_time"],
                    "exit_price": trade["exit_price"],
                    "exit_reason": trade["exit_reason"],
                    "pnl": pnl,
                }
            )

        if missing:
            self.log(f"足が無いサイン: {missing}")

        self.draw_chart(bars, results)
        if not results:
            self.draw_equity_chart([])
            self.update_stats([])
            self.log("約定できたサインがありません")
            return

        results_sorted = sorted(results, key=lambda item: item["exit_time"])
        equity = 0.0
        equity_points = []
        for item in results_sorted:
            equity += item["pnl"] / PIP_SIZE
            equity_points.append({"time": item["exit_time"], "value": equity})
        self.draw_equity_chart(equity_points)
        self.update_stats(results_sorted)

        total = len(results)
        wins = sum(1 for r in results if r["pnl"] > 0)
        losses = sum(1 for r in results if r["pnl"] < 0)
        flats = total - wins - losses
        total_pnl = sum(r["pnl"] for r in results)
        avg_pnl = total_pnl / total if total else 0.0
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) else 0.0
        buy_count = sum(1 for r in results if r["action"] == "BUY")
        sell_count = total - buy_count
        stop_count = sum(1 for r in results if r["exit_reason"] == "stop")
        limit_count = sum(1 for r in results if r["exit_reason"] == "limit")
        end_count = sum(1 for r in results if r["exit_reason"] == "end")

        self.log("")
        self.log("結果")
        self.log(f"取引数: {total} (買い {buy_count} / 売り {sell_count})")
        self.log(f"勝ち: {wins} / 負け: {losses} / 引き分け: {flats}")
        self.log(f"勝率: {win_rate:.1f}%")
        self.log(f"合計損益: {format_price(total_pnl)}")
        self.log(f"平均損益: {format_price(avg_pnl)}")
        self.log(f"損切り: {stop_count} / 利確: {limit_count} / 期間終了: {end_count}")
        self.log("")
        self.log("注意")
        self.log("・サインの時刻は日本時間として9時間引いて計算しています")
        self.log("・エントリーは該当足の終値です")
        self.log("・スプレッドは売買の両側に半分ずつ反映しています")
        self.log("・幅の入力は 0.01 を 1 として扱っています")
        self.log("・時間クローズは指定分経過後の足の終値です")
        self.log("・同じ足で両方に触れた場合は不利な方を採用します")
        self.log("")

        max_details = 120
        self.log("明細")
        for idx, item in enumerate(results):
            if idx >= max_details:
                self.log(f"... 省略 {total - max_details} 件")
                break
            entry_jst = item["entry_time"] + JST_OFFSET
            exit_jst = item["exit_time"] + JST_OFFSET
            action_label = "買い" if item["action"] == "BUY" else "売り"
            reason_label = {
                "stop": "損切り",
                "limit": "利確",
                "time": "時間",
                "end": "期間終了",
            }.get(item["exit_reason"], "不明")
            self.log(
                f"{format_dt(entry_jst)} {action_label} "
                f"入={format_price(item['entry_price'])} "
                f"出={format_price(item['exit_price'])} "
                f"損益={format_price(item['pnl'])} "
                f"{reason_label} {format_dt(exit_jst)}"
            )


def main():
    root = tk.Tk()
    root.minsize(1200, 700)
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    target_w = 1920
    target_h = 1080
    width = target_w if screen_w >= target_w else screen_w
    height = target_h if screen_h >= target_h else screen_h
    root.geometry(f"{width}x{height}")
    BacktestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
