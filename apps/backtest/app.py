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
                    signals.append(
                        {
                            "time_jst": dt_jst,
                            "time_utc": dt_jst - JST_OFFSET,
                            "action": action_norm,
                            "source": row.get("source") or os.path.basename(path),
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


def simulate_trade(bars, start_idx, end_idx, direction, stop, limit, spread):
    half = spread / 2.0
    entry_mid = bars[start_idx]["close"]
    entry_time = bars[start_idx]["time"]

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
            hit_stop = stop > 0 and low <= stop_trigger
            hit_limit = limit > 0 and high >= limit_trigger
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
        hit_stop = stop > 0 and high >= stop_trigger
        hit_limit = limit > 0 and low <= limit_trigger
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
        self.signals = []

        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.stop_var = tk.StringVar(value="0.05")
        self.limit_var = tk.StringVar(value="0.05")
        self.spread_var = tk.StringVar(value="0.02")
        self.info_var = tk.StringVar(value="サイン件数: -")

        top = ttk.Frame(root, padding=10)
        top.grid(sticky="nsew")

        ttk.Label(top, textvariable=self.info_var).grid(row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(top, text="開始(日本時間)").grid(row=1, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(top, textvariable=self.start_var, width=22).grid(row=1, column=1, sticky="w", pady=(8, 2))
        ttk.Button(top, text="日付", command=lambda: self.open_calendar(self.start_var)).grid(
            row=1, column=2, sticky="w", padx=(6, 0), pady=(8, 2)
        )
        ttk.Label(top, text="終了(日本時間)").grid(row=1, column=3, sticky="w", padx=(12, 0), pady=(8, 2))
        ttk.Entry(top, textvariable=self.end_var, width=22).grid(row=1, column=4, sticky="w", pady=(8, 2))
        ttk.Button(top, text="日付", command=lambda: self.open_calendar(self.end_var)).grid(
            row=1, column=5, sticky="w", padx=(6, 0), pady=(8, 2)
        )

        ttk.Label(top, text="ストップ幅").grid(row=2, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.stop_var, width=12).grid(row=2, column=1, sticky="w")
        ttk.Label(top, text="リミット幅").grid(row=2, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(top, textvariable=self.limit_var, width=12).grid(row=2, column=3, sticky="w")

        ttk.Label(top, text="スプレッド").grid(row=3, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.spread_var, width=12).grid(row=3, column=1, sticky="w")

        self.run_btn = ttk.Button(top, text="実行", command=self.run_backtest)
        self.run_btn.grid(row=3, column=2, sticky="w", padx=(12, 0))
        ttk.Button(top, text="再読込", command=self.reload_signals).grid(row=3, column=3, sticky="w")

        self.text = tk.Text(top, width=90, height=28)
        self.text.grid(row=4, column=0, columnspan=6, pady=(12, 0), sticky="nsew")
        self.text.configure(state="disabled")
        scroll = ttk.Scrollbar(top, command=self.text.yview)
        scroll.grid(row=4, column=6, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        top.columnconfigure(4, weight=1)
        top.rowconfigure(4, weight=1)

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

    def run_backtest(self):
        self.clear_log()
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
        try:
            stop = float(self.stop_var.get().strip())
            limit = float(self.limit_var.get().strip())
            spread = float(self.spread_var.get().strip())
        except ValueError:
            messagebox.showerror("エラー", "幅の値が数値ではありません")
            return
        if stop < 0 or limit < 0 or spread < 0:
            messagebox.showerror("エラー", "幅の値は0以上で入力してください")
            return

        start_utc = start_jst - JST_OFFSET
        end_utc = end_jst - JST_OFFSET

        period_signals = [
            item for item in self.signals if start_utc <= item["time_utc"] <= end_utc
        ]
        self.log(f"サイン総数: {len(self.signals)}")
        self.log(f"期間内サイン: {len(period_signals)}")

        if not period_signals:
            self.log("期間内のサインがありません")
            return

        bars, index_by_time, bar_errors = load_ohlc_range(DATA_DIR, start_utc, end_utc)
        for item in bar_errors:
            self.log(item)
        if not bars:
            self.log("足データが読み込めません")
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

        if not results:
            self.log("約定できたサインがありません")
            return

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
    root.minsize(820, 520)
    BacktestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
