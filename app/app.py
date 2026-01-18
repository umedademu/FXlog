import json
import os
import queue
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
import tkinter as tk
from tkinter import ttk


LISTVIEW_URL = "https://finance.yahoo.co.jp/cm/ds/comment/listview"
THREAD_URL = "https://finance.yahoo.co.jp/cm/message/552023129/usdjpy/{part}"
THREAD_NAME_ENC = "%E3%82%A2%E3%83%A1%E3%83%AA%E3%82%AB%20%E3%83%89%E3%83%AB%20%2F%20%E6%97%A5%E6%9C%AC%20%E5%86%86%E3%80%90usdjpy%E3%80%91"

BASE_DATE = date(2026, 1, 16)
BASE_PART = 3291

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
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


def date_to_part(day):
    diff = (day - BASE_DATE).days
    return BASE_PART + diff


def build_log_path(day):
    return os.path.join(LOG_DIR, f"usdjpy_{day.strftime('%Y%m%d')}.jsonl")


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("ログ取得")
        self.queue = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()

        self.start_var = tk.StringVar(value="2026-01-16")
        self.end_var = tk.StringVar(value="2026-01-16")
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

        frm = ttk.Frame(root, padding=10)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="開始日").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.start_var, width=16).grid(row=0, column=1, sticky="w", padx=(5, 15))
        ttk.Label(frm, text="終了日").grid(row=0, column=2, sticky="w")
        ttk.Entry(frm, textvariable=self.end_var, width=16).grid(row=0, column=3, sticky="w", padx=(5, 15))
        ttk.Label(frm, text="待ち時間(秒)").grid(row=0, column=4, sticky="w")
        ttk.Entry(frm, textvariable=self.sleep_min_var, width=6).grid(row=0, column=5, sticky="w", padx=(5, 5))
        ttk.Label(frm, text="〜").grid(row=0, column=6, sticky="w")
        ttk.Entry(frm, textvariable=self.sleep_max_var, width=6).grid(row=0, column=7, sticky="w", padx=(5, 15))

        self.start_btn = ttk.Button(frm, text="開始", command=self.start)
        self.start_btn.grid(row=0, column=8, sticky="w")
        self.stop_btn = ttk.Button(frm, text="停止", command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=9, sticky="w", padx=(5, 0))

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
        self.text.grid(row=3, column=0, columnspan=10, pady=(10, 0), sticky="nsew")
        self.text.configure(state="disabled")

        scroll = ttk.Scrollbar(frm, command=self.text.yview)
        scroll.grid(row=3, column=10, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        frm.columnconfigure(9, weight=1)
        frm.rowconfigure(3, weight=1)

        self.root.after(200, self.flush_log)

    def log(self, message):
        self.queue.put(message)

    def flush_log(self):
        while True:
            try:
                msg = self.queue.get_nowait()
            except queue.Empty:
                break
            self.text.configure(state="normal")
            self.text.insert("end", msg + "\n")
            self.text.see("end")
            self.text.configure(state="disabled")
        self.root.after(200, self.flush_log)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            start_day = parse_date(self.start_var.get())
            end_day = parse_date(self.end_var.get())
        except ValueError:
            self.log("日付の書き方が正しくありません")
            return
        if start_day > end_day:
            self.log("開始日と終了日を入れ替えてください")
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

        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.worker = threading.Thread(
            target=self.run,
            args=(
                start_day,
                end_day,
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
        start_day,
        end_day,
        sleep_min,
        sleep_max,
        extra_pages,
        extra_sleep_min,
        extra_sleep_max,
        extra2_pages,
        extra2_sleep_min,
        extra2_sleep_max,
    ):
        total_days = (end_day - start_day).days + 1
        self.log(f"期間: {start_day} 〜 {end_day} ({total_days}日)")
        self.log(f"待ち時間: {sleep_min}〜{sleep_max}秒")
        if extra_pages > 0:
            self.log(f"追加休止: {extra_pages}ページごとに{extra_sleep_min}〜{extra_sleep_max}秒")
        if extra2_pages > 0:
            self.log(f"追加休止2: {extra2_pages}ページごとに{extra2_sleep_min}〜{extra2_sleep_max}秒")

        day = start_day
        while day <= end_day:
            if self.stop_event.is_set():
                self.log("停止しました")
                break
            part = date_to_part(day)
            if part <= 0:
                self.log(f"対象外: {day} part={part}")
                day += timedelta(days=1)
                continue
            self.log(f"対象日: {day} の取得中")
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
                path = build_log_path(day)
                save_jsonl(path, comments)
                self.log(f"保存: {path} 件数={len(comments)}")
            except Exception as exc:
                self.log(f"失敗: {day} {exc}")
            day += timedelta(days=1)


def main():
    root = tk.Tk()
    root.minsize(720, 480)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
