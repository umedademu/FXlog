import calendar
import json
import os
import queue
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser
import tkinter as tk
from tkinter import ttk


LISTVIEW_URL = "https://finance.yahoo.co.jp/cm/ds/comment/listview"
THREAD_URL = "https://finance.yahoo.co.jp/cm/message/552023129/usdjpy/{part}"
THREAD_NAME_ENC = "%E3%82%A2%E3%83%A1%E3%83%AA%E3%82%AB%20%E3%83%89%E3%83%AB%20%2F%20%E6%97%A5%E6%9C%AC%20%E5%86%86%E3%80%90usdjpy%E3%80%91"

PART_START_DEFAULT = 3291
PART_END_DEFAULT = 3291
MISSING_YEAR_DEFAULT = 2026

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
SLEEP_MIN_DEFAULT = 0.3
SLEEP_MAX_DEFAULT = 0.6
EXTRA_SLEEP_MIN_DEFAULT = 5
EXTRA_SLEEP_MAX_DEFAULT = 15
EXTRA2_SLEEP_MIN_DEFAULT = 15
EXTRA2_SLEEP_MAX_DEFAULT = 30
EXTRA_PAGES_DEFAULT = 50
EXTRA2_PAGES_DEFAULT = 200


class CommentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.comments = []
        self._in_comment = False
        self._comment_depth = 0
        self._current = None
        self._capture_com_num = False
        self._capture_text = False
        self._capture_time = False
        self._text_parts = []
        self._num_parts = []
        self._time_parts = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "li":
            li_id = attr.get("id", "")
            if (not self._in_comment) and li_id.startswith("c") and li_id[1:].isdigit():
                self._in_comment = True
                self._comment_depth = 1
                self._current = {"comment_no": int(li_id[1:])}
            elif self._in_comment:
                self._comment_depth += 1

        if not self._in_comment:
            return

        if tag == "div" and "comment" in attr.get("class", ""):
            comment_id = attr.get("data-comment")
            if comment_id:
                self._current.setdefault("comment_id", comment_id)

        if tag == "span" and attr.get("class") == "comNum":
            self._capture_com_num = True
            self._num_parts = []

        if tag == "p" and attr.get("class") == "comText":
            self._capture_text = True
            self._text_parts = []

        if tag == "a":
            user_id = attr.get("data-user")
            if user_id:
                self._current.setdefault("user_id", user_id)
            parent_comment = attr.get("data-parent_comment")
            if parent_comment:
                self._current.setdefault("reply_to", parent_comment)
            cl_params = attr.get("data-cl-params", "")
            if "dt" in cl_params:
                self._capture_time = True
                self._time_parts = []

        if tag == "br" and self._capture_text:
            self._text_parts.append("\n")

    def handle_endtag(self, tag):
        if self._in_comment and tag == "li":
            self._comment_depth -= 1
            if self._comment_depth <= 0:
                self._finalize_comment()
                return

        if not self._in_comment:
            return

        if tag == "span" and self._capture_com_num:
            num_text = "".join(self._num_parts).strip()
            if num_text.isdigit():
                self._current["comment_no"] = int(num_text)
            self._capture_com_num = False

        if tag == "p" and self._capture_text:
            text = "".join(self._text_parts).strip()
            self._current["text"] = text
            self._capture_text = False

        if tag == "a" and self._capture_time:
            time_text = "".join(self._time_parts).strip()
            if time_text:
                self._current["posted_at"] = time_text
            self._capture_time = False

    def handle_data(self, data):
        if not self._in_comment:
            return
        if self._capture_com_num:
            self._num_parts.append(data)
        if self._capture_text:
            self._text_parts.append(data)
        if self._capture_time:
            self._time_parts.append(data)

    def _finalize_comment(self):
        if self._current:
            self.comments.append(self._current)
        self._in_comment = False
        self._comment_depth = 0
        self._current = None
        self._capture_com_num = False
        self._capture_text = False
        self._capture_time = False
        self._text_parts = []
        self._num_parts = []
        self._time_parts = []


def fetch_text(url, extra_headers=None):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/html,*/*",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")


def get_latest_comment_no(part):
    html = fetch_text(THREAD_URL.format(part=part))
    m = re.search(r'class="threadLength">([\d,]+)</li>', html)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r'id="c(\d+)"', html)
    if not m:
        raise RuntimeError("latest comment not found")
    return int(m.group(1))


def build_listview_url(part, offset, page):
    params = [
        ("category", "552023129"),
        ("thread", "usdjpy"),
        ("part", str(part)),
        ("thread_feel_type", ""),
        ("thread_stop_flag", "1"),
        ("tieup_name", "fx"),
        ("thread_name", THREAD_NAME_ENC),
        ("offset", str(offset)),
        ("page", str(page)),
        ("_", str(int(time.time() * 1000))),
    ]
    pairs = []
    for key, value in params:
        if key == "thread_name":
            pairs.append(f"{key}={value}")
        else:
            pairs.append(f"{key}={urllib.parse.quote_plus(value)}")
    return LISTVIEW_URL + "?" + "&".join(pairs)


def fetch_page(part, offset, page):
    url = build_listview_url(part, offset, page)
    body = fetch_text(url, {"X-Requested-With": "XMLHttpRequest"})
    data = json.loads(body)
    error = data.get("feed", {}).get("Error")
    if error:
        raise RuntimeError(error.get("Message", "request failed"))
    return data.get("feed", {}).get("content", "")


def pick_sleep(min_sec, max_sec):
    if max_sec <= min_sec:
        return min_sec
    return random.uniform(min_sec, max_sec)


def collect_comments(
    part,
    stop_event,
    log_fn,
    sleep_min,
    sleep_max,
    extra_enabled,
    extra_pages,
    extra_sleep_min,
    extra_sleep_max,
    extra2_enabled,
    extra2_pages,
    extra2_sleep_min,
    extra2_sleep_max,
):
    latest = get_latest_comment_no(part)
    page = 2
    offset = latest
    all_comments = []
    seen = set()
    log_fn(f"開始 part={part} 最新={latest}")

    pages_fetched = 0
    while True:
        if stop_event.is_set():
            log_fn("停止しました")
            break
        try:
            content = fetch_page(part, offset, page)
        except Exception as exc:
            log_fn(f"取得失敗: {exc}")
            break

        if not content or "<li" not in content:
            log_fn("終了: これ以上ありません")
            break

        parser = CommentParser()
        parser.feed(content)
        if not parser.comments:
            log_fn("終了: コメントがありません")
            break

        new_count = 0
        for item in parser.comments:
            num = item.get("comment_no")
            if num is None or num in seen:
                continue
            item["part"] = part
            all_comments.append(item)
            seen.add(num)
            new_count += 1

        nums = [c.get("comment_no") for c in parser.comments if c.get("comment_no") is not None]
        if not nums:
            log_fn("終了: 番号が取れません")
            break

        min_no = min(nums)
        if min_no >= offset:
            log_fn("終了: 進みません")
            break

        log_fn(f"ページ={page} 取得={new_count} 最小={min_no} 合計={len(all_comments)}")
        offset = min_no - 1
        page += 1
        pages_fetched += 1
        time.sleep(pick_sleep(sleep_min, sleep_max))
        if extra_enabled and extra_pages > 0 and pages_fetched % extra_pages == 0:
            extra_sleep = pick_sleep(extra_sleep_min, extra_sleep_max)
            log_fn(f"追加休止: {extra_sleep:.2f}秒")
            time.sleep(extra_sleep)
        if extra2_enabled and extra2_pages > 0 and pages_fetched % extra2_pages == 0:
            extra2_sleep = pick_sleep(extra2_sleep_min, extra2_sleep_max)
            log_fn(f"追加休止2: {extra2_sleep:.2f}秒")
            time.sleep(extra2_sleep)

    return all_comments


def save_jsonl(path, comments):
    comments = sorted(comments, key=lambda x: x.get("comment_no", 0), reverse=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in comments:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def parse_date(text):
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    if re.fullmatch(r"\d{8}", text):
        return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    raise ValueError("date format error")


def parse_posted_date(text, missing_year):
    if not text:
        return None
    m = re.search(r"(?:(\d{4})年)?\s*(\d{1,2})月(\d{1,2})日", text)
    if not m:
        return None
    year_text, month_text, day_text = m.groups()
    year = int(year_text) if year_text else missing_year
    try:
        return date(year, int(month_text), int(day_text))
    except ValueError:
        return None


def determine_file_date(comments, missing_year):
    if not comments:
        return None
    oldest = min(comments, key=lambda x: x.get("comment_no", 0) or 0)
    target = parse_posted_date(oldest.get("posted_at", ""), missing_year)
    if target:
        return target
    candidates = []
    for item in comments:
        parsed = parse_posted_date(item.get("posted_at", ""), missing_year)
        if parsed:
            candidates.append(parsed)
    if not candidates:
        return None
    return min(candidates)


def build_log_path(part, day):
    return os.path.join(LOG_DIR, f"usdjpy_{part}_{day.strftime('%Y%m%d')}.jsonl")


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


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("ログ取得")
        self.queue = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.current_label = None

        self.start_part_var = tk.StringVar(value=str(PART_START_DEFAULT))
        self.end_part_var = tk.StringVar(value=str(PART_END_DEFAULT))
        self.missing_year_var = tk.StringVar(value=str(MISSING_YEAR_DEFAULT))
        self.sleep_min_var = tk.StringVar(value=str(SLEEP_MIN_DEFAULT))
        self.sleep_max_var = tk.StringVar(value=str(SLEEP_MAX_DEFAULT))
        self.extra_enabled = tk.BooleanVar(value=False)
        self.extra_pages_var = tk.StringVar(value=str(EXTRA_PAGES_DEFAULT))
        self.extra_sleep_min_var = tk.StringVar(value=str(EXTRA_SLEEP_MIN_DEFAULT))
        self.extra_sleep_max_var = tk.StringVar(value=str(EXTRA_SLEEP_MAX_DEFAULT))
        self.extra2_enabled = tk.BooleanVar(value=False)
        self.extra2_pages_var = tk.StringVar(value=str(EXTRA2_PAGES_DEFAULT))
        self.extra2_sleep_min_var = tk.StringVar(value=str(EXTRA2_SLEEP_MIN_DEFAULT))
        self.extra2_sleep_max_var = tk.StringVar(value=str(EXTRA2_SLEEP_MAX_DEFAULT))

        self.load_settings()

        frm = ttk.Frame(root, padding=10)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="開始番号").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.start_part_var, width=8).grid(row=0, column=1, sticky="w", padx=(5, 15))
        ttk.Label(frm, text="終了番号").grid(row=0, column=2, sticky="w")
        ttk.Entry(frm, textvariable=self.end_part_var, width=8).grid(row=0, column=3, sticky="w", padx=(5, 15))
        ttk.Label(frm, text="年なしの年").grid(row=0, column=4, sticky="w")
        ttk.Entry(frm, textvariable=self.missing_year_var, width=6).grid(row=0, column=5, sticky="w", padx=(5, 15))
        ttk.Label(frm, text="待ち時間(秒)").grid(row=0, column=6, sticky="w")
        ttk.Entry(frm, textvariable=self.sleep_min_var, width=6).grid(row=0, column=7, sticky="w", padx=(5, 5))
        ttk.Label(frm, text="〜").grid(row=0, column=8, sticky="w")
        ttk.Entry(frm, textvariable=self.sleep_max_var, width=6).grid(row=0, column=9, sticky="w", padx=(5, 15))

        self.start_btn = ttk.Button(frm, text="開始", command=self.start)
        self.start_btn.grid(row=0, column=10, sticky="w")
        self.stop_btn = ttk.Button(frm, text="停止", command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=11, sticky="w", padx=(5, 0))

        ttk.Checkbutton(frm, text="追加休止", variable=self.extra_enabled).grid(row=1, column=0, sticky="w")
        ttk.Label(frm, text="間隔(ページ)").grid(row=1, column=1, sticky="w")
        ttk.Entry(frm, textvariable=self.extra_pages_var, width=8).grid(row=1, column=2, sticky="w", padx=(5, 15))
        ttk.Label(frm, text="休止(秒)").grid(row=1, column=3, sticky="w")
        ttk.Entry(frm, textvariable=self.extra_sleep_min_var, width=6).grid(row=1, column=4, sticky="w", padx=(5, 5))
        ttk.Label(frm, text="〜").grid(row=1, column=5, sticky="w")
        ttk.Entry(frm, textvariable=self.extra_sleep_max_var, width=6).grid(row=1, column=6, sticky="w", padx=(5, 15))

        ttk.Checkbutton(frm, text="追加休止2", variable=self.extra2_enabled).grid(row=2, column=0, sticky="w")
        ttk.Label(frm, text="間隔(ページ)").grid(row=2, column=1, sticky="w")
        ttk.Entry(frm, textvariable=self.extra2_pages_var, width=8).grid(row=2, column=2, sticky="w", padx=(5, 15))
        ttk.Label(frm, text="休止(秒)").grid(row=2, column=3, sticky="w")
        ttk.Entry(frm, textvariable=self.extra2_sleep_min_var, width=6).grid(row=2, column=4, sticky="w", padx=(5, 5))
        ttk.Label(frm, text="〜").grid(row=2, column=5, sticky="w")
        ttk.Entry(frm, textvariable=self.extra2_sleep_max_var, width=6).grid(row=2, column=6, sticky="w", padx=(5, 15))

        self.text = tk.Text(frm, width=80, height=24)
        self.text.grid(row=3, column=0, columnspan=12, pady=(10, 0), sticky="nsew")
        self.text.configure(state="disabled")

        scroll = ttk.Scrollbar(frm, command=self.text.yview)
        scroll.grid(row=3, column=12, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        frm.columnconfigure(11, weight=1)
        frm.rowconfigure(3, weight=1)

        self.root.after(200, self.flush_log)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, message):
        prefix = ""
        if self.current_label:
            prefix = f"[{self.current_label}] "
        self.queue.put(prefix + message)

    def flush_log(self):
        while True:
            try:
                msg = self.queue.get_nowait()
            except queue.Empty:
                break
            self.text.configure(state="normal")
            self.text.insert("end", msg + "\n")
        self.text.configure(state="disabled")
        self.text.see("end")
        self.root.after(200, self.flush_log)

    def open_calendar(self, target_var):
        try:
            base = parse_date(target_var.get())
        except Exception:
            base = date.today()
        CalendarDialog(self.root, target_var, base)

    def load_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return

        def set_text(var, key):
            value = data.get(key)
            if value is None:
                return
            var.set(str(value))

        def set_flag(var, key):
            value = data.get(key)
            if value is None:
                return
            var.set(bool(value))

        set_text(self.start_part_var, "start_part")
        set_text(self.end_part_var, "end_part")
        set_text(self.missing_year_var, "missing_year")
        set_text(self.sleep_min_var, "sleep_min")
        set_text(self.sleep_max_var, "sleep_max")
        set_flag(self.extra_enabled, "extra_enabled")
        set_text(self.extra_pages_var, "extra_pages")
        set_text(self.extra_sleep_min_var, "extra_sleep_min")
        set_text(self.extra_sleep_max_var, "extra_sleep_max")
        set_flag(self.extra2_enabled, "extra2_enabled")
        set_text(self.extra2_pages_var, "extra2_pages")
        set_text(self.extra2_sleep_min_var, "extra2_sleep_min")
        set_text(self.extra2_sleep_max_var, "extra2_sleep_max")

    def save_settings(self):
        data = {
            "start_part": self.start_part_var.get().strip(),
            "end_part": self.end_part_var.get().strip(),
            "missing_year": self.missing_year_var.get().strip(),
            "sleep_min": self.sleep_min_var.get().strip(),
            "sleep_max": self.sleep_max_var.get().strip(),
            "extra_enabled": bool(self.extra_enabled.get()),
            "extra_pages": self.extra_pages_var.get().strip(),
            "extra_sleep_min": self.extra_sleep_min_var.get().strip(),
            "extra_sleep_max": self.extra_sleep_max_var.get().strip(),
            "extra2_enabled": bool(self.extra2_enabled.get()),
            "extra2_pages": self.extra2_pages_var.get().strip(),
            "extra2_sleep_min": self.extra2_sleep_min_var.get().strip(),
            "extra2_sleep_max": self.extra2_sleep_max_var.get().strip(),
        }
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
        except OSError:
            pass

    def on_close(self):
        self.save_settings()
        self.stop_event.set()
        self.root.destroy()

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            start_part = int(self.start_part_var.get().strip())
            end_part = int(self.end_part_var.get().strip())
            if start_part <= 0 or end_part <= 0:
                raise ValueError
        except ValueError:
            self.log("開始番号と終了番号は1以上の数字で入力してください")
            return
        try:
            missing_year = int(self.missing_year_var.get().strip())
            if missing_year < 1900 or missing_year > 2100:
                raise ValueError
        except ValueError:
            self.log("年なしの年は西暦で入力してください")
            return
        try:
            sleep_min = float(self.sleep_min_var.get().strip())
            sleep_max = float(self.sleep_max_var.get().strip())
            if sleep_min < 0 or sleep_max < 0 or sleep_min > sleep_max:
                raise ValueError
        except ValueError:
            self.log("待ち時間は0以上で、下限が上限以下になるように入力してください")
            return
        if self.extra_enabled.get():
            try:
                extra_pages = int(self.extra_pages_var.get().strip())
                extra_sleep_min = float(self.extra_sleep_min_var.get().strip())
                extra_sleep_max = float(self.extra_sleep_max_var.get().strip())
                if (
                    extra_pages <= 0
                    or extra_sleep_min < 0
                    or extra_sleep_max < 0
                    or extra_sleep_min > extra_sleep_max
                ):
                    raise ValueError
            except ValueError:
                self.log("追加休止はページ数と秒数を正しく入力してください")
                return
        else:
            extra_pages = 0
            extra_sleep_min = 0.0
            extra_sleep_max = 0.0
        if self.extra2_enabled.get():
            try:
                extra2_pages = int(self.extra2_pages_var.get().strip())
                extra2_sleep_min = float(self.extra2_sleep_min_var.get().strip())
                extra2_sleep_max = float(self.extra2_sleep_max_var.get().strip())
                if (
                    extra2_pages <= 0
                    or extra2_sleep_min < 0
                    or extra2_sleep_max < 0
                    or extra2_sleep_min > extra2_sleep_max
                ):
                    raise ValueError
            except ValueError:
                self.log("追加休止2はページ数と秒数を正しく入力してください")
                return
        else:
            extra2_pages = 0
            extra2_sleep_min = 0.0
            extra2_sleep_max = 0.0

        self.save_settings()
        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.worker = threading.Thread(
            target=self.run,
            args=(
                start_part,
                end_part,
                missing_year,
                sleep_min,
                sleep_max,
                extra_pages,
                extra_sleep_min,
                extra_sleep_max,
                extra2_pages,
                extra2_sleep_min,
                extra2_sleep_max,
            ),
            daemon=True,
        )
        self.worker.start()
        self.root.after(300, self.check_worker)

    def stop(self):
        self.stop_event.set()

    def check_worker(self):
        if self.worker and self.worker.is_alive():
            self.root.after(300, self.check_worker)
            return
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.log("処理が終わりました")

    def run(
        self,
        start_part,
        end_part,
        missing_year,
        sleep_min,
        sleep_max,
        extra_pages,
        extra_sleep_min,
        extra_sleep_max,
        extra2_pages,
        extra2_sleep_min,
        extra2_sleep_max,
    ):
        total_parts = abs(end_part - start_part) + 1
        self.current_label = None
        self.log(f"番号: {start_part} ～ {end_part} ({total_parts}件)")
        self.log(f"年なしの年: {missing_year}年")
        self.log(f"待ち時間: {sleep_min}～{sleep_max}秒")
        if extra_pages > 0:
            self.log(f"追加休止: {extra_pages}ページごとに{extra_sleep_min}～{extra_sleep_max}秒")
        if extra2_pages > 0:
            self.log(f"追加休止2: {extra2_pages}ページごとに{extra2_sleep_min}～{extra2_sleep_max}秒")

        step = 1 if end_part >= start_part else -1
        part = start_part
        while True:
            self.current_label = f"part={part}"
            if self.stop_event.is_set():
                self.log("停止しました")
                break
            if part <= 0:
                self.log(f"対象外: part={part}")
            else:
                self.log(f"対象番号: {part} の取得中")
                try:
                    comments = collect_comments(
                        part,
                        self.stop_event,
                        self.log,
                        sleep_min,
                        sleep_max,
                        extra_pages > 0,
                        extra_pages,
                        extra_sleep_min,
                        extra_sleep_max,
                        extra2_pages > 0,
                        extra2_pages,
                        extra2_sleep_min,
                        extra2_sleep_max,
                    )
                    file_day = determine_file_date(comments, missing_year)
                    if not file_day:
                        self.log("日付が取れないため保存を中止しました")
                    else:
                        self.current_label = f"{file_day.year}年{file_day.month}月{file_day.day}日 part={part}"
                        path = build_log_path(part, file_day)
                        save_jsonl(path, comments)
                        self.log(f"保存: {path} 件数={len(comments)}")
                except Exception as exc:
                    self.log(f"失敗: part={part} {exc}")

            if part == end_part:
                break
            part += step
        self.current_label = None



def main():
    root = tk.Tk()
    root.minsize(720, 480)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
