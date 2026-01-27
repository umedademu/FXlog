import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from datetime import date, datetime, timedelta
import calendar
import json
import os
import re
import threading
import urllib.request
import urllib.error

class LogAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ドル円スレ ログ解析ツール")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)

        # ログディレクトリのパス
        self.logs_dir = r"C:\Users\USER\Desktop\FXlog\logs"
        # レートデータのパス（1分足）
        self.rates_dir = r"C:\Users\USER\Desktop\FXlog\data\usdjpy\m1"
        # CSV出力先
        self.csv_dir = r"C:\Users\USER\Desktop\FXlog\csv"
        # プロンプトのパス
        self.prompt_path = os.path.join(os.path.dirname(__file__), "docs", "prompt.md")
        # アプリのパス
        self.app_dir = os.path.dirname(__file__)

        # 処理中フラグ
        self.is_processing = False
        # レートの簡易キャッシュ
        self.rate_cache = {}
        # 抽出結果のまとまり管理
        self.batches = []
        self.current_batch_index = 0
        # 送信中フラグ
        self.is_sending = False
        # 自動送信フラグ
        self.auto_run_active = False
        self.auto_stop_requested = False
        self.send_context = "single"
        # バッチ情報
        self.batch_job_name = ""
        self.batch_responses_file = ""
        # CSV自動保存
        self.auto_save_csv = tk.BooleanVar(value=True)
        # CSV既存ファイルの扱い
        self.csv_mode = tk.StringVar(value="init")
        # CSV追記中の日付
        self.csv_touched_dates = set()

        self.create_widgets()

    def create_widgets(self):
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 条件エリア
        condition_frame = ttk.LabelFrame(main_frame, text="条件", padding=10)
        condition_frame.pack(fill=tk.X, pady=10)
        condition_frame.columnconfigure(6, weight=1)

        # 開始日
        ttk.Label(condition_frame, text="開始日:").grid(row=0, column=0, sticky=tk.W)
        self.start_date = tk.StringVar(value="2026-01-01")
        start_entry = ttk.Entry(condition_frame, textvariable=self.start_date, width=12)
        start_entry.grid(row=0, column=1, padx=5, sticky=tk.W)
        ttk.Button(
            condition_frame,
            text="📅",
            width=3,
            command=lambda: self.show_calendar(self.start_date)
        ).grid(row=0, column=2, padx=(0, 10), sticky=tk.W)

        # 終了日
        ttk.Label(condition_frame, text="終了日:").grid(row=0, column=3, sticky=tk.W)
        self.end_date = tk.StringVar(value="2026-01-31")
        end_entry = ttk.Entry(condition_frame, textvariable=self.end_date, width=12)
        end_entry.grid(row=0, column=4, padx=5, sticky=tk.W)
        ttk.Button(
            condition_frame,
            text="📅",
            width=3,
            command=lambda: self.show_calendar(self.end_date)
        ).grid(row=0, column=5, padx=(0, 10), sticky=tk.W)

        # 実行ボタン
        self.run_button = ttk.Button(
            condition_frame,
            text="解析実行",
            command=self.run_analysis
        )
        self.run_button.grid(row=0, column=6, rowspan=3, padx=(10, 0), sticky=tk.NS)

        # 土日除外
        self.exclude_weekends = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            condition_frame,
            text="土日は除外（月7:00〜土6:59のみ）",
            variable=self.exclude_weekends
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)

        # バッチサイズ
        ttk.Label(condition_frame, text="何レスずつAIに渡すか:").grid(row=1, column=2, sticky=tk.W)
        self.batch_size = tk.IntVar(value=20)
        batch_spin = ttk.Spinbox(
            condition_frame,
            from_=1,
            to=1000,
            textvariable=self.batch_size,
            width=6
        )
        batch_spin.grid(row=1, column=3, padx=5, sticky=tk.W)

        # モデル名
        ttk.Label(condition_frame, text="モデル名:").grid(row=1, column=4, sticky=tk.W)
        self.model_name = tk.StringVar(value="gemini-3-flash-preview")
        model_entry = ttk.Entry(condition_frame, textvariable=self.model_name, width=20)
        model_entry.grid(row=1, column=5, padx=5, sticky=tk.W)

        # 送信方式
        ttk.Label(condition_frame, text="送信方式:").grid(row=2, column=0, sticky=tk.W)
        self.send_mode = tk.StringVar(value="normal")
        ttk.Radiobutton(
            condition_frame,
            text="通常",
            variable=self.send_mode,
            value="normal",
            command=self.on_send_mode_changed
        ).grid(row=2, column=1, sticky=tk.W)
        ttk.Radiobutton(
            condition_frame,
            text="まとめ",
            variable=self.send_mode,
            value="batch",
            command=self.on_send_mode_changed
        ).grid(row=2, column=2, sticky=tk.W)

        ttk.Label(condition_frame, text="CSV既存:").grid(row=2, column=3, sticky=tk.W)
        ttk.Radiobutton(
            condition_frame,
            text="初期化",
            variable=self.csv_mode,
            value="init"
        ).grid(row=2, column=4, sticky=tk.W)
        ttk.Radiobutton(
            condition_frame,
            text="追記",
            variable=self.csv_mode,
            value="append"
        ).grid(row=2, column=5, sticky=tk.W)

        ttk.Checkbutton(
            condition_frame,
            text="CSV自動保存",
            variable=self.auto_save_csv
        ).grid(row=2, column=6, sticky=tk.W)

        # 設定確認（1行）
        self.info_var = tk.StringVar(value="")
        info_label = ttk.Label(main_frame, textvariable=self.info_var)
        info_label.pack(fill=tk.X, pady=(0, 5))

        # ステータス表示
        self.status_label = ttk.Label(main_frame, text="", foreground="blue")
        self.status_label.pack(pady=(0, 5))

        # 変更時に自動更新
        for var in (self.start_date, self.end_date, self.exclude_weekends, self.batch_size, self.model_name, self.send_mode, self.auto_save_csv, self.csv_mode):
            var.trace_add("write", lambda *_: self.update_info())
        self.update_info()

        # 結果表示エリア（横並び）
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=10)

        result_frame = ttk.LabelFrame(paned, text="送信用プレビュー", padding=10)
        ai_frame = ttk.LabelFrame(paned, text="解析結果（AI）", padding=10)
        paned.add(result_frame, weight=3)
        paned.add(ai_frame, weight=2)

        result_header = ttk.Frame(result_frame)
        result_header.pack(fill=tk.X, pady=(0, 6))

        self.result_count_var = tk.StringVar(value="抽出件数: 0件")
        self.result_count_label = ttk.Label(result_header, textvariable=self.result_count_var)
        self.result_count_label.pack(side=tk.LEFT)

        self.batch_info_var = tk.StringVar(value="まとまり: 0/0 （1まとまり: 0件）")
        self.batch_info_label = ttk.Label(result_header, textvariable=self.batch_info_var)
        self.batch_info_label.pack(side=tk.RIGHT)

        result_controls = ttk.Frame(result_frame)
        result_controls.pack(fill=tk.X, pady=(0, 8))

        left_controls = ttk.Frame(result_controls)
        left_controls.pack(side=tk.LEFT)

        right_controls = ttk.Frame(result_controls)
        right_controls.pack(side=tk.RIGHT)

        self.prev_button = ttk.Button(left_controls, text="前のまとまり", command=self.prev_batch)
        self.prev_button.pack(side=tk.LEFT)

        self.next_button = ttk.Button(left_controls, text="次のまとまり", command=self.next_batch)
        self.next_button.pack(side=tk.LEFT, padx=5)

        self.send_button = ttk.Button(left_controls, text="このまとまりを送信（テスト）", command=self.send_current_batch)
        self.send_button.pack(side=tk.LEFT, padx=5)

        self.batch_send_button = ttk.Button(left_controls, text="全部をまとめて送信", command=self.send_all_batches)
        self.batch_send_button.pack(side=tk.LEFT, padx=5)

        self.auto_send_button = ttk.Button(left_controls, text="通常を一括送信", command=self.start_auto_send_normal)
        self.auto_send_button.pack(side=tk.LEFT, padx=5)

        self.auto_stop_button = ttk.Button(left_controls, text="停止", command=self.stop_auto_send)
        self.auto_stop_button.pack(side=tk.LEFT, padx=5)

        ttk.Button(right_controls, text="このまとまりをコピー", command=self.copy_current_batch).pack(side=tk.RIGHT, padx=5)
        ttk.Button(right_controls, text="このまとまりを保存", command=self.save_current_batch).pack(side=tk.RIGHT)
        ttk.Button(right_controls, text="全件保存", command=self.save_all_results).pack(side=tk.RIGHT)
        ttk.Button(right_controls, text="クリア", command=self.clear_results).pack(side=tk.RIGHT, padx=5)

        self.result_text = scrolledtext.ScrolledText(
            result_frame,
            wrap=tk.NONE,
            font=("MS Gothic", 9)
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)
        self.result_text.config(state=tk.DISABLED)

        ai_header_top = ttk.Frame(ai_frame)
        ai_header_top.pack(fill=tk.X, pady=(0, 4))

        self.ai_status_var = tk.StringVar(value="送信状態: 待機")
        self.ai_status_label = ttk.Label(ai_header_top, textvariable=self.ai_status_var)
        self.ai_status_label.pack(side=tk.LEFT)

        self.batch_job_var = tk.StringVar(value="バッチID: なし")
        self.batch_job_label = ttk.Label(ai_header_top, textvariable=self.batch_job_var)
        self.batch_job_label.pack(side=tk.RIGHT)

        ai_header_bottom = ttk.Frame(ai_frame)
        ai_header_bottom.pack(fill=tk.X, pady=(0, 8))

        batch_controls = ttk.Frame(ai_header_bottom)
        batch_controls.pack(side=tk.LEFT)
        self.batch_status_button = ttk.Button(batch_controls, text="状態更新", command=self.check_batch_status)
        self.batch_status_button.pack(side=tk.LEFT)
        self.batch_result_button = ttk.Button(batch_controls, text="結果取得", command=self.fetch_batch_results)
        self.batch_result_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(batch_controls, text="CSV保存", command=self.save_ai_result_to_csv).pack(side=tk.LEFT, padx=5)

        ai_controls = ttk.Frame(ai_header_bottom)
        ai_controls.pack(side=tk.RIGHT)
        ttk.Button(ai_controls, text="結果をコピー", command=self.copy_ai_result).pack(side=tk.LEFT, padx=5)
        ttk.Button(ai_controls, text="結果をクリア", command=self.clear_ai_result).pack(side=tk.LEFT)

        self.ai_result_text = scrolledtext.ScrolledText(
            ai_frame,
            wrap=tk.NONE,
            font=("MS Gothic", 9)
        )
        self.ai_result_text.pack(fill=tk.BOTH, expand=True)
        self.ai_result_text.config(state=tk.DISABLED)

        self.last_posts = []
        self.update_batch_buttons()
        self.on_send_mode_changed()

    def show_calendar(self, date_var):
        """カレンダーダイアログを表示"""
        top = tk.Toplevel(self.root)
        top.title("日付選択")
        top.geometry("250x200")
        top.transient(self.root)
        top.grab_set()

        # 年月選択
        header_frame = ttk.Frame(top)
        header_frame.pack(fill=tk.X, pady=5)

        now = date.today()
        year_var = tk.IntVar(value=now.year)
        month_var = tk.IntVar(value=now.month)

        year_spin = ttk.Spinbox(header_frame, from_=2000, to=2100, textvariable=year_var, width=6)
        year_spin.pack(side=tk.LEFT, padx=5)

        month_spin = ttk.Spinbox(header_frame, from_=1, to=12, textvariable=month_var, width=4)
        month_spin.pack(side=tk.LEFT, padx=5)

        # カレンダー
        cal_frame = ttk.Frame(top)
        cal_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 曜日ヘッダー
        days = ["日", "月", "火", "水", "木", "金", "土"]
        for i, day in enumerate(days):
            lbl = ttk.Label(cal_frame, text=day, width=4)
            lbl.grid(row=0, column=i)

        # 日付ボタン
        def select_date(d):
            date_var.set(f"{year_var.get()}-{month_var.get():02d}-{d:02d}")
            top.destroy()
            self.update_info()

        buttons = []
        for week_num, week in enumerate(calendar.monthcalendar(year_var.get(), month_var.get()), start=1):
            for day_num, day in enumerate(week):
                if day == 0:
                    lbl = ttk.Label(cal_frame, text="", width=4)
                    lbl.grid(row=week_num, column=day_num)
                else:
                    btn = ttk.Button(
                        cal_frame,
                        text=str(day),
                        width=4,
                        command=lambda d=day: select_date(d)
                    )
                    btn.grid(row=week_num, column=day_num)
                    buttons.append(btn)

        # 月変更でカレンダーを更新
        def refresh_calendar(*args):
            for widget in cal_frame.winfo_children():
                widget.destroy()
            # ...（再描画処理は省略して簡略化）

    def update_info(self):
        """設定確認エリアを更新"""
        info = (
            f"開始日: {self.start_date.get()}  "
            f"終了日: {self.end_date.get()}  "
            f"土日除外: {'ON' if self.exclude_weekends.get() else 'OFF'}  "
            f"1まとまり: {self.batch_size.get()}件  "
            f"モデル: {self.model_name.get()}  "
            f"送信方式: {'通常' if self.send_mode.get() == 'normal' else 'まとめ'}  "
            f"CSV既存: {'初期化' if self.csv_mode.get() == 'init' else '追記'}  "
            f"CSV自動保存: {'ON' if self.auto_save_csv.get() else 'OFF'}"
        )
        self.info_var.set(info)

    def on_send_mode_changed(self):
        """送信方式の変更時処理"""
        if not self.is_sending:
            if self.send_mode.get() == "batch":
                self.ai_status_var.set("バッチ状態: 待機")
            else:
                self.ai_status_var.set("送信状態: 待機")
        self.update_batch_buttons()

    def run_analysis(self):
        """解析実行"""
        if self.is_processing:
            messagebox.showwarning("注意", "処理中です。しばらくお待ちください。")
            return

        if self.start_date.get() > self.end_date.get():
            messagebox.showerror("エラー", "開始日は終了日より前にしてください")
            return

        # スレッドで処理開始
        self.is_processing = True
        self.status_label.config(text="ログを読み込んでいます...")
        self.run_button.config(state=tk.DISABLED)

        thread = threading.Thread(target=self._run_analysis_thread)
        thread.start()

    def _run_analysis_thread(self):
        """バックグラウンドで解析実行"""
        try:
            # ログを読み込んでフィルタリング
            posts = self.load_and_filter_posts()

            # メインスレッドで結果を表示
            self.root.after(0, lambda: self._show_result(posts))
        except Exception as e:
            self.root.after(0, lambda: self._show_error(str(e)))

    def _show_result(self, posts):
        """結果を表示（メインスレッドから呼ばれる）"""
        self.is_processing = False
        self.status_label.config(text="")
        self.run_button.config(state=tk.NORMAL)

        if not posts:
            self.clear_results()
            messagebox.showinfo("結果", "指定された期間内のログが見つかりませんでした")
            return

        # 結果を表示
        self.show_results(posts)

    def _show_error(self, error_msg):
        """エラーを表示（メインスレッドから呼ばれる）"""
        self.is_processing = False
        self.status_label.config(text="", foreground="red")
        self.run_button.config(state=tk.NORMAL)
        messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{error_msg}")

    def load_and_filter_posts(self):
        """ログを読み込んでフィルタリング"""
        posts_with_dt = []  # (datetime, formatted_text) のタプルで保持

        # 開始日・終了日をdatetimeに変換
        try:
            start_dt = datetime.strptime(self.start_date.get(), "%Y-%m-%d")
            end_dt = datetime.strptime(self.end_date.get(), "%Y-%m-%d")
            # 終了日は23:59:59まで含める
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        except ValueError:
            messagebox.showerror("エラー", "日付フォーマットが正しくありません")
            return []

        # 対象期間に関係しそうなファイルだけを拾う（ファイル名は参考にしない）
        log_files = []
        for f in os.listdir(self.logs_dir):
            if not f.endswith(".jsonl"):
                continue
            file_path = os.path.join(self.logs_dir, f)
            max_dt = self.get_file_max_date(file_path)
            # ファイル内の最新日時が開始日より前なら除外
            if max_dt and max_dt < start_dt:
                continue
            log_files.append(f)

        for log_file in log_files:

            file_path = os.path.join(self.logs_dir, log_file)
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        posted_at = data.get('posted_at', '')
                        text = data.get('text', '')

                        # 日時をパース
                        post_dt = self.parse_posted_at(posted_at)
                        if post_dt is None:
                            continue

                        # 開始日より前ならスキップ
                        if post_dt < start_dt:
                            continue

                        # 終了日より後なら除外（ファイルは新しい順のことがあるため終了しない）
                        if post_dt > end_dt:
                            continue

                        # 土日除外チェック
                        if self.exclude_weekends.get():
                            if not self.is_weekday_hour(post_dt):
                                continue

                        # レートを取得（その時点の始値）
                        open_rate = self.get_open_rate(post_dt)

                        # フォーマット変換: YY-MM-DD HH:MM\t本文\t始値
                        formatted = self.format_post(post_dt, text, open_rate)
                        posts_with_dt.append((post_dt, formatted))

                    except (json.JSONDecodeError, KeyError):
                        continue

        # 日付順（古い順）にソート
        posts_with_dt.sort(key=lambda x: x[0])

        # フォーマット済みテキストのみを返す
        return [formatted for _, formatted in posts_with_dt]

    def parse_posted_at(self, posted_at):
        """posted_atをdatetimeに変換 (例: '2026年1月16日 23:59')"""
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})', posted_at)
        if match:
            year, month, day, hour, minute = match.groups()
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
        return None

    def get_file_max_date(self, file_path):
        """ファイル内の最新日時を取得（最初の有効行）"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    posted_at = data.get("posted_at", "")
                    post_dt = self.parse_posted_at(posted_at)
                    if post_dt:
                        return post_dt
        except OSError:
            return None
        return None

    def is_weekday_hour(self, post_dt):
        """月7:00〜土6:59の範囲内か判定"""
        weekday = post_dt.weekday()  # 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
        hour = post_dt.hour

        # 月: 7:00以降
        if weekday == 0 and hour >= 7:
            return True
        # 火〜金: 24時間全て
        elif 1 <= weekday <= 4:
            return True
        # 土: 6:59まで
        elif weekday == 5 and hour <= 6:
            return True
        # 他は除外（月0:00〜6:59、日曜、土7:00以降）
        return False

    def format_post(self, post_dt, text, open_rate):
        """レスをフォーマット: YY-MM-DD HH:MM\t本文\t始値"""
        date_str = post_dt.strftime("%y-%m-%d %H:%M")
        # 改行をスペースに置換（1行=1レスを維持）
        cleaned_text = text.replace('\n', ' ').replace('\r', ' ')
        rate_str = open_rate if open_rate else ""
        return f"{date_str}\t{cleaned_text}\t{rate_str}"

    def get_open_rate(self, post_dt):
        """投稿時点の始値を取得"""
        date_key = post_dt.strftime("%Y-%m-%d")
        minute_key = post_dt.strftime("%Y-%m-%d %H:%M")

        if date_key not in self.rate_cache:
            self.rate_cache[date_key] = self.load_rates_for_date(post_dt)

        return self.rate_cache[date_key].get(minute_key, "")

    def load_rates_for_date(self, post_dt):
        """指定日の1分足データを読み込む"""
        year_dir = post_dt.strftime("%Y")
        date_str = post_dt.strftime("%Y-%m-%d")
        file_path = os.path.join(self.rates_dir, year_dir, f"{date_str}.csv")

        rates = {}
        if not os.path.exists(file_path):
            return rates

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                header_skipped = False
                for line in f:
                    if not header_skipped:
                        header_skipped = True
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) < 2:
                        continue
                    time_raw = parts[0]
                    open_rate = parts[1]

                    # "01.01.2026 00:00:00.000 GMT+0900" -> "01.01.2026 00:00:00.000"
                    time_main = time_raw.split(" GMT")[0]
                    try:
                        dt = datetime.strptime(time_main, "%d.%m.%Y %H:%M:%S.%f")
                    except ValueError:
                        continue
                    minute_key = dt.strftime("%Y-%m-%d %H:%M")
                    rates[minute_key] = open_rate
        except OSError:
            return {}

        return rates

    def show_results(self, posts):
        """結果を同一ウィンドウ内に表示"""
        self.last_posts = posts
        self.result_count_var.set(f"抽出件数: {len(posts)}件")
        self.batch_job_name = ""
        self.batch_responses_file = ""
        self.batch_job_var.set("バッチID: なし")
        self.csv_touched_dates = set()
        self.csv_touched_dates = set()
        if not self.is_sending:
            if self.send_mode.get() == "batch":
                self.ai_status_var.set("バッチ状態: 待機")
            else:
                self.ai_status_var.set("送信状態: 待機")
        self.batches = self.build_batches(posts)
        self.current_batch_index = 0
        self.update_batch_view()

    def build_batches(self, posts):
        """指定件数ごとにまとまりを作る"""
        size = max(1, int(self.batch_size.get()))
        return [posts[i:i + size] for i in range(0, len(posts), size)]

    def update_batch_view(self):
        """現在のまとまりを表示"""
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)

        if not self.batches:
            self.batch_info_var.set("まとまり: 0/0 （1まとまり: 0件）")
            self.result_text.config(state=tk.DISABLED)
            self.update_batch_buttons()
            return

        total = len(self.batches)
        idx = self.current_batch_index
        size = max(1, int(self.batch_size.get()))
        batch = self.batches[idx]

        self.batch_info_var.set(f"まとまり: {idx + 1}/{total} （1まとまり: {size}件）")

        for post in batch:
            self.result_text.insert(tk.END, post + "\n")

        self.result_text.config(state=tk.DISABLED)
        self.update_batch_buttons()

    def update_batch_buttons(self):
        """まとまり移動ボタンの状態を更新"""
        has_batches = bool(self.batches)
        mode = self.send_mode.get() if hasattr(self, "send_mode") else "normal"
        busy = self.is_sending or self.auto_run_active

        if not has_batches:
            self.prev_button.config(state=tk.DISABLED)
            self.next_button.config(state=tk.DISABLED)
            self.send_button.config(state=tk.DISABLED)
            self.batch_send_button.config(state=tk.DISABLED)
            self.auto_send_button.config(state=tk.DISABLED)
        else:
            self.prev_button.config(
                state=tk.NORMAL if (self.current_batch_index > 0 and not busy) else tk.DISABLED
            )
            self.next_button.config(
                state=tk.NORMAL if (self.current_batch_index < len(self.batches) - 1 and not busy) else tk.DISABLED
            )
            self.send_button.config(
                state=tk.NORMAL if (mode == "normal" and not busy) else tk.DISABLED
            )
            self.batch_send_button.config(
                state=tk.NORMAL if (mode == "batch" and not busy) else tk.DISABLED
            )
            self.auto_send_button.config(
                state=tk.NORMAL if (mode == "normal" and not busy) else tk.DISABLED
            )

        self.auto_stop_button.config(
            state=tk.NORMAL if self.auto_run_active else tk.DISABLED
        )

        has_job = bool(self.batch_job_name)
        self.batch_status_button.config(
            state=tk.NORMAL if (has_job and not busy) else tk.DISABLED
        )
        self.batch_result_button.config(
            state=tk.NORMAL if (has_job and not busy) else tk.DISABLED
        )

    def prev_batch(self):
        """前のまとまりへ"""
        if self.current_batch_index > 0:
            self.current_batch_index -= 1
            self.update_batch_view()

    def next_batch(self):
        """次のまとまりへ"""
        if self.current_batch_index < len(self.batches) - 1:
            self.current_batch_index += 1
            self.update_batch_view()

    def clear_results(self):
        """結果表示をクリア"""
        self.last_posts = []
        self.batches = []
        self.current_batch_index = 0
        self.result_count_var.set("抽出件数: 0件")
        self.batch_info_var.set("まとまり: 0/0 （1まとまり: 0件）")
        self.batch_job_name = ""
        self.batch_responses_file = ""
        self.batch_job_var.set("バッチID: なし")
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state=tk.DISABLED)
        if not self.is_sending:
            if self.send_mode.get() == "batch":
                self.ai_status_var.set("バッチ状態: 待機")
            else:
                self.ai_status_var.set("送信状態: 待機")
        self.update_batch_buttons()

    def copy_current_batch(self):
        """表示中のまとまりをコピー"""
        text = self.result_text.get(1.0, tk.END).strip()
        if not text:
            messagebox.showinfo("情報", "コピーする内容がありません")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("情報", "コピーしました")

    def save_current_batch(self):
        """表示中のまとまりを保存"""
        if not self.batches:
            messagebox.showinfo("情報", "保存する内容がありません")
            return

        start_str = self.start_date.get().replace("-", "")
        end_str = self.end_date.get().replace("-", "")
        total = len(self.batches)
        index = self.current_batch_index + 1
        digits = len(str(total))
        part_str = str(index).zfill(digits)
        default_name = f"usdjpy_{start_str}_{end_str}_part{part_str}.tsv"
        file_path = filedialog.asksaveasfilename(
            title="保存先を選択",
            defaultextension=".tsv",
            initialfile=default_name,
            filetypes=[("TSV", "*.tsv"), ("テキスト", "*.txt"), ("すべてのファイル", "*.*")]
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.batches[self.current_batch_index]))
            messagebox.showinfo("情報", "保存しました")
        except OSError as e:
            messagebox.showerror("エラー", f"保存に失敗しました:\n{e}")

    def save_all_results(self):
        """抽出結果を保存（全件）"""
        if not self.last_posts:
            messagebox.showinfo("情報", "保存する内容がありません")
            return
        start_str = self.start_date.get().replace("-", "")
        end_str = self.end_date.get().replace("-", "")
        default_name = f"usdjpy_{start_str}_{end_str}.tsv"
        file_path = filedialog.asksaveasfilename(
            title="保存先を選択",
            defaultextension=".tsv",
            initialfile=default_name,
            filetypes=[("TSV", "*.tsv"), ("テキスト", "*.txt"), ("すべてのファイル", "*.*")]
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.last_posts))
            messagebox.showinfo("情報", "保存しました")
        except OSError as e:
            messagebox.showerror("エラー", f"保存に失敗しました:\n{e}")

    def send_current_batch(self):
        """現在のまとまりを送信"""
        if self.send_mode.get() != "normal":
            messagebox.showinfo("情報", "送信方式が「まとめ」になっています")
            return
        if self.is_sending:
            messagebox.showwarning("注意", "送信中です。しばらくお待ちください。")
            return
        if not self.batches:
            messagebox.showinfo("情報", "送信する内容がありません")
            return

        model = self.model_name.get().strip()
        if not model:
            messagebox.showerror("エラー", "モデル名が未入力です")
            return

        prompt_text = self.load_prompt_text()
        if not prompt_text:
            messagebox.showerror("エラー", "プロンプトが読み込めませんでした")
            return

        api_key = self.load_api_key()
        if not api_key:
            messagebox.showerror("エラー", "APIキーが見つかりません")
            return

        batch = self.batches[self.current_batch_index]
        batch_text = "\n".join(batch)
        full_text = f"{prompt_text}\n\n【投稿内容】\n{batch_text}"

        self.is_sending = True
        self.send_context = "single"
        self.ai_status_var.set("送信状態: 送信中")
        self.update_batch_buttons()

        thread = threading.Thread(
            target=self._send_to_gemini_thread,
            args=(full_text, model, api_key)
        )
        thread.start()

    def send_all_batches(self):
        """全てのまとまりをまとめて送信"""
        if self.send_mode.get() != "batch":
            messagebox.showinfo("情報", "送信方式が「通常」になっています")
            return
        if self.is_sending:
            messagebox.showwarning("注意", "送信中です。しばらくお待ちください。")
            return
        if not self.batches:
            messagebox.showinfo("情報", "送信する内容がありません")
            return

        model = self.model_name.get().strip()
        if not model:
            messagebox.showerror("エラー", "モデル名が未入力です")
            return

        prompt_text = self.load_prompt_text()
        if not prompt_text:
            messagebox.showerror("エラー", "プロンプトが読み込めませんでした")
            return

        api_key = self.load_api_key()
        if not api_key:
            messagebox.showerror("エラー", "APIキーが見つかりません")
            return

        self.is_sending = True
        self.send_context = "batch"
        self.ai_status_var.set("バッチ状態: 送信中")
        self.update_batch_buttons()

        thread = threading.Thread(
            target=self._send_batch_thread,
            args=(prompt_text, model, api_key)
        )
        thread.start()

    def start_auto_send_normal(self):
        """通常モードで全てのまとまりを順番に送信"""
        if self.send_mode.get() != "normal":
            messagebox.showinfo("情報", "送信方式が「まとめ」になっています")
            return
        if self.is_sending or self.auto_run_active:
            messagebox.showwarning("注意", "送信中です。しばらくお待ちください。")
            return
        if not self.batches:
            messagebox.showinfo("情報", "送信する内容がありません")
            return

        model = self.model_name.get().strip()
        if not model:
            messagebox.showerror("エラー", "モデル名が未入力です")
            return

        prompt_text = self.load_prompt_text()
        if not prompt_text:
            messagebox.showerror("エラー", "プロンプトが読み込めませんでした")
            return

        api_key = self.load_api_key()
        if not api_key:
            messagebox.showerror("エラー", "APIキーが見つかりません")
            return

        self.is_sending = True
        self.auto_run_active = True
        self.auto_stop_requested = False
        self.send_context = "auto"
        self.csv_touched_dates = set()
        self.ai_status_var.set("送信状態: 自動送信中")
        self.status_label.config(text=f"自動送信: 0/{len(self.batches)}")
        self.update_batch_buttons()

        thread = threading.Thread(
            target=self._auto_send_thread,
            args=(prompt_text, model, api_key)
        )
        thread.start()

    def stop_auto_send(self):
        """自動送信の停止要求"""
        if not self.auto_run_active:
            return
        self.auto_stop_requested = True
        self.status_label.config(text="自動送信: 停止要求を受け付けました")

    def _auto_send_thread(self, prompt_text, model, api_key):
        """自動送信（バックグラウンド）"""
        total = len(self.batches)
        saved_rows_total = 0
        error_count_total = 0

        for idx, batch in enumerate(self.batches, start=1):
            if self.auto_stop_requested:
                break

            batch_text = "\n".join(batch)
            full_text = f"{prompt_text}\n\n【投稿内容】\n{batch_text}"

            try:
                result_text = self.call_gemini_api(full_text, model, api_key)
            except Exception as e:
                self.root.after(0, lambda: self._show_ai_error(str(e)))
                return

            rows, error_count = self.parse_ai_output(result_text)
            error_count_total += error_count
            saved_rows = 0
            if self.auto_save_csv.get():
                try:
                    _, saved_rows = self.append_rows_to_csv(rows, self.csv_mode.get(), self.csv_touched_dates)
                    saved_rows_total += saved_rows
                except Exception as e:
                    self.root.after(0, lambda: self._show_ai_error(str(e)))
                    return

            self.root.after(
                0,
                lambda res=result_text, i=idx, t=total, saved=saved_rows_total, err=error_count_total:
                self._show_auto_progress(res, i, t, saved, err)
            )

        self.root.after(0, self._finish_auto_send)

    def _show_auto_progress(self, text, index, total, saved_rows, error_rows):
        """自動送信の進行を表示"""
        self.ai_result_text.config(state=tk.NORMAL)
        self.ai_result_text.delete(1.0, tk.END)
        self.ai_result_text.insert(tk.END, text)
        self.ai_result_text.config(state=tk.DISABLED)

        message = f"自動送信: {index}/{total} 完了  保存: {saved_rows}行"
        if error_rows:
            message += f"  読み取り不可: {error_rows}行"
        self.status_label.config(text=message)

    def _finish_auto_send(self):
        """自動送信の終了処理"""
        stopped = self.auto_stop_requested
        self.auto_run_active = False
        self.auto_stop_requested = False
        self.is_sending = False

        if stopped:
            self.ai_status_var.set("送信状態: 停止")
        else:
            self.ai_status_var.set("送信状態: 完了")
        self.update_batch_buttons()

    def _send_batch_thread(self, prompt_text, model, api_key):
        """バッチ送信処理（バックグラウンド）"""
        jsonl_path = ""
        try:
            jsonl_path = self.create_batch_jsonl(prompt_text)
            file_name = self.upload_batch_file(jsonl_path, api_key)
            batch_name = self.create_batch_job(file_name, model, api_key)
            self.root.after(0, lambda: self._show_batch_created(batch_name))
        except Exception as e:
            self.root.after(0, lambda: self._show_ai_error(str(e)))
        finally:
            if jsonl_path and os.path.exists(jsonl_path):
                try:
                    os.remove(jsonl_path)
                except OSError:
                    pass

    def _show_batch_created(self, batch_name):
        """バッチ送信完了を表示"""
        self.is_sending = False
        if not batch_name:
            self.ai_status_var.set("バッチ状態: エラー")
            self.update_batch_buttons()
            messagebox.showerror("エラー", "バッチIDが取得できませんでした")
            return

        self.batch_job_name = batch_name
        self.batch_responses_file = ""
        self.batch_job_var.set(f"バッチID: {batch_name}")
        self.ai_status_var.set("バッチ状態: 送信完了")
        self.update_batch_buttons()

    def check_batch_status(self):
        """バッチの状態を確認"""
        if not self.batch_job_name:
            messagebox.showinfo("情報", "バッチIDがありません")
            return
        if self.is_sending:
            messagebox.showwarning("注意", "処理中です。しばらくお待ちください。")
            return

        api_key = self.load_api_key()
        if not api_key:
            messagebox.showerror("エラー", "APIキーが見つかりません")
            return

        self.is_sending = True
        self.ai_status_var.set("バッチ状態: 状態確認中")
        self.update_batch_buttons()

        thread = threading.Thread(
            target=self._check_batch_status_thread,
            args=(api_key,)
        )
        thread.start()

    def _check_batch_status_thread(self, api_key):
        """バッチ状態確認（バックグラウンド）"""
        try:
            job = self.get_batch_job(self.batch_job_name, api_key)
            state, done, response_file = self.parse_batch_job_state(job)
            self.root.after(0, lambda: self._show_batch_status(state, done, response_file))
        except Exception as e:
            self.root.after(0, lambda: self._show_ai_error(str(e)))

    def _show_batch_status(self, state, done, response_file):
        """バッチ状態を表示"""
        self.is_sending = False
        state_text = state if state else "不明"
        if done:
            state_text = f"{state_text}（完了）"
        self.ai_status_var.set(f"バッチ状態: {state_text}")
        if response_file:
            self.batch_responses_file = response_file
        self.update_batch_buttons()

    def fetch_batch_results(self):
        """バッチの結果を取得"""
        if not self.batch_job_name:
            messagebox.showinfo("情報", "バッチIDがありません")
            return
        if self.is_sending:
            messagebox.showwarning("注意", "処理中です。しばらくお待ちください。")
            return

        api_key = self.load_api_key()
        if not api_key:
            messagebox.showerror("エラー", "APIキーが見つかりません")
            return

        self.is_sending = True
        self.ai_status_var.set("バッチ状態: 結果取得中")
        self.update_batch_buttons()

        thread = threading.Thread(
            target=self._fetch_batch_results_thread,
            args=(api_key,)
        )
        thread.start()

    def _fetch_batch_results_thread(self, api_key):
        """バッチ結果取得（バックグラウンド）"""
        try:
            job = self.get_batch_job(self.batch_job_name, api_key)
            state, done, response_file = self.parse_batch_job_state(job)
            if not done:
                raise Exception("まだ完了していません")

            response = job.get("response", {}) if isinstance(job, dict) else {}
            if response_file:
                raw_text = self.download_batch_file(response_file, api_key)
                result_text = self.parse_batch_output(raw_text)
            elif isinstance(response, dict) and response.get("inlinedResponses"):
                result_text = self.format_inline_responses(response.get("inlinedResponses"))
            else:
                result_text = json.dumps(job, ensure_ascii=False, indent=2)

            self.root.after(0, lambda: self._show_batch_result(result_text, state))
        except Exception as e:
            self.root.after(0, lambda: self._show_ai_error(str(e)))

    def _show_batch_result(self, text, state):
        """バッチ結果を表示"""
        self.is_sending = False
        state_text = state if state else "完了"
        self.ai_status_var.set(f"バッチ状態: {state_text}")
        self.ai_result_text.config(state=tk.NORMAL)
        self.ai_result_text.delete(1.0, tk.END)
        self.ai_result_text.insert(tk.END, text)
        self.ai_result_text.config(state=tk.DISABLED)

        if self.auto_save_csv.get() and self.send_context != "single":
            self.save_ai_result_to_csv(show_message=False)
        self.update_batch_buttons()

    def create_batch_jsonl(self, prompt_text):
        """バッチ用のJSONLを作成"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(self.app_dir, f"batch_requests_{timestamp}.jsonl")

        with open(file_path, "w", encoding="utf-8") as f:
            for idx, batch in enumerate(self.batches, start=1):
                batch_text = "\n".join(batch)
                full_text = f"{prompt_text}\n\n【投稿内容】\n{batch_text}"
                request = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": full_text}]
                        }
                    ]
                }
                item = {
                    "key": f"batch_{idx}",
                    "request": request
                }
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return file_path

    def upload_batch_file(self, file_path, api_key):
        """バッチ入力ファイルをアップロード"""
        file_size = os.path.getsize(file_path)
        start_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        metadata = {"file": {"display_name": os.path.basename(file_path)}}

        headers = {
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "application/jsonl",
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(
            start_url,
            data=json.dumps(metadata).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                upload_url = resp.headers.get("X-Goog-Upload-URL")
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
            except OSError:
                error_body = str(e)
            raise Exception(error_body) from e

        if not upload_url:
            raise Exception("アップロードURLが取得できませんでした")

        with open(file_path, "rb") as f:
            data = f.read()

        upload_headers = {
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(file_size),
            "Content-Type": "application/jsonl"
        }
        upload_req = urllib.request.Request(
            upload_url,
            data=data,
            headers=upload_headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(upload_req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
            except OSError:
                error_body = str(e)
            raise Exception(error_body) from e

        resp_json = json.loads(body) if body else {}
        file_info = resp_json.get("file", resp_json)
        file_name = file_info.get("name") or file_info.get("uri")
        if not file_name:
            raise Exception("ファイルIDが取得できませんでした")
        return file_name

    def create_batch_job(self, file_name, model, api_key):
        """バッチ処理を作成"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchGenerateContent"
        payload = {
            "batch": {
                "display_name": f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "input_config": {
                    "file_name": file_name
                }
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
            except OSError:
                error_body = str(e)
            raise Exception(error_body) from e
        resp_json = json.loads(body) if body else {}
        return resp_json.get("name") or ""

    def get_batch_job(self, batch_name, api_key):
        """バッチ状態を取得"""
        url = f"https://generativelanguage.googleapis.com/v1beta/{batch_name}"
        req = urllib.request.Request(
            url,
            headers={"x-goog-api-key": api_key},
            method="GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
            except OSError:
                error_body = str(e)
            raise Exception(error_body) from e
        return json.loads(body) if body else {}

    def parse_batch_job_state(self, job):
        """バッチ状態を解析"""
        state = ""
        done = False
        response_file = ""

        if isinstance(job, dict):
            done = bool(job.get("done"))
            metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
            state = metadata.get("state") or job.get("state") or ""
            response = job.get("response") if isinstance(job.get("response"), dict) else {}
            response_file = response.get("responsesFile") or response.get("responses_file") or ""

        return state, done, response_file

    def download_batch_file(self, file_name, api_key):
        """バッチの結果ファイルを取得"""
        url = f"https://generativelanguage.googleapis.com/download/v1beta/{file_name}:download?alt=media"
        req = urllib.request.Request(
            url,
            headers={"x-goog-api-key": api_key},
            method="GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
            except OSError:
                error_body = str(e)
            raise Exception(error_body) from e
        return body

    def parse_batch_output(self, raw_text):
        """バッチ結果のJSONLを整形"""
        lines = raw_text.splitlines()
        outputs = []

        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                outputs.append(line)
                continue

            key = item.get("key")
            if not key and isinstance(item.get("metadata"), dict):
                key = item.get("metadata", {}).get("key")

            if "error" in item:
                message = item.get("error", {}).get("message", "不明なエラー")
                text = f"エラー: {message}"
            else:
                response = item.get("response") if isinstance(item.get("response"), dict) else item
                text = self.extract_response_text(response)
                if not text:
                    text = json.dumps(item, ensure_ascii=False)

            if key:
                outputs.append(f"[{key}] {text}")
            else:
                outputs.append(text)

        return "\n\n".join(outputs)

    def format_inline_responses(self, responses):
        """インライン結果を整形"""
        outputs = []
        for item in responses:
            key = None
            if isinstance(item, dict) and isinstance(item.get("metadata"), dict):
                key = item.get("metadata", {}).get("key")
            if isinstance(item, dict) and "error" in item:
                message = item.get("error", {}).get("message", "不明なエラー")
                text = f"エラー: {message}"
            else:
                response = item.get("response") if isinstance(item, dict) else {}
                text = self.extract_response_text(response)
                if not text:
                    text = json.dumps(item, ensure_ascii=False)
            if key:
                outputs.append(f"[{key}] {text}")
            else:
                outputs.append(text)
        return "\n\n".join(outputs)

    def extract_response_text(self, response):
        """応答から本文を取り出す"""
        if not isinstance(response, dict):
            return ""
        candidates = response.get("candidates", [])
        if not candidates:
            return ""
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        texts = []
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                texts.append(part.get("text", ""))
        return "".join(texts).strip()

    def _send_to_gemini_thread(self, full_text, model, api_key):
        """送信処理（バックグラウンド）"""
        try:
            result_text = self.call_gemini_api(full_text, model, api_key)
            self.root.after(0, lambda: self._show_ai_result(result_text))
        except Exception as e:
            self.root.after(0, lambda: self._show_ai_error(str(e)))

    def _show_ai_result(self, text):
        """送信結果を表示"""
        self.is_sending = False
        label = "バッチ状態" if self.send_mode.get() == "batch" else "送信状態"
        self.ai_status_var.set(f"{label}: 完了")
        self.update_batch_buttons()

        self.ai_result_text.config(state=tk.NORMAL)
        self.ai_result_text.delete(1.0, tk.END)
        self.ai_result_text.insert(tk.END, text)
        self.ai_result_text.config(state=tk.DISABLED)

    def _show_ai_error(self, error_msg):
        """送信エラーを表示"""
        self.is_sending = False
        self.auto_run_active = False
        self.auto_stop_requested = False
        label = "バッチ状態" if self.send_mode.get() == "batch" else "送信状態"
        self.ai_status_var.set(f"{label}: エラー")
        self.update_batch_buttons()
        messagebox.showerror("エラー", f"送信に失敗しました:\n{error_msg}")

    def copy_ai_result(self):
        """送信結果をコピー"""
        text = self.ai_result_text.get(1.0, tk.END).strip()
        if not text:
            messagebox.showinfo("情報", "コピーする内容がありません")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("情報", "コピーしました")

    def clear_ai_result(self):
        """送信結果をクリア"""
        self.ai_result_text.config(state=tk.NORMAL)
        self.ai_result_text.delete(1.0, tk.END)
        self.ai_result_text.config(state=tk.DISABLED)
        if not self.is_sending:
            label = "バッチ状態" if self.send_mode.get() == "batch" else "送信状態"
            self.ai_status_var.set(f"{label}: 待機")

    def save_ai_result_to_csv(self, show_message=True):
        """送信結果をCSVとして保存"""
        text = self.ai_result_text.get(1.0, tk.END).strip()
        if not text:
            if show_message:
                messagebox.showinfo("情報", "保存する内容がありません")
            return

        rows, error_count = self.parse_ai_output(text)
        if not rows:
            if show_message:
                messagebox.showinfo("情報", "保存できる行が見つかりませんでした")
            return

        try:
            saved_files, saved_rows = self.append_rows_to_csv(
                rows,
                self.csv_mode.get(),
                set()
            )
        except Exception as e:
            messagebox.showerror("エラー", str(e))
            return

        message = f"CSV保存: {saved_files}ファイル / {saved_rows}行"
        if error_count:
            message += f"（読み取り不可: {error_count}行）"
        self.status_label.config(text=message)
        if show_message:
            messagebox.showinfo("情報", message)

    def parse_ai_output(self, text):
        """AI出力をCSV行に変換"""
        rows = []
        error_count = 0

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.upper() == "NONE":
                continue
            if line.startswith("[") and "]" in line:
                line = line.split("]", 1)[1].strip()

            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                error_count += 1
                continue

            dt_raw = parts[0]
            side = parts[1]
            entry_type = parts[2]
            entry_price = parts[3]
            reason = ",".join(parts[4:]).strip()

            dt_info = self.parse_ai_datetime(dt_raw)
            if not dt_info:
                error_count += 1
                continue

            rows.append({
                "date_key": dt_info["date_key"],
                "datetime": dt_info["datetime"],
                "side": side,
                "entry_type": entry_type,
                "entry_price": entry_price,
                "reason": reason
            })

        return rows, error_count

    def append_rows_to_csv(self, rows, mode, touched_dates):
        """CSVに追記または初期化して保存"""
        try:
            os.makedirs(self.csv_dir, exist_ok=True)
        except OSError as e:
            raise Exception(f"保存先の作成に失敗しました:\n{e}") from e

        grouped = {}
        for item in rows:
            date_key = item["date_key"]
            grouped.setdefault(date_key, []).append(item)

        saved_files = 0
        saved_rows = 0

        for date_key, items in grouped.items():
            file_name = f"usdjpy_{date_key}.csv"
            file_path = os.path.join(self.csv_dir, file_name)
            file_exists = os.path.exists(file_path)

            write_header = False
            open_mode = "a"

            if mode == "init":
                if date_key not in touched_dates:
                    open_mode = "w"
                    write_header = True
                else:
                    open_mode = "a"
            else:
                if (not file_exists) and (date_key not in touched_dates):
                    write_header = True

            try:
                with open(file_path, open_mode, encoding="utf-8") as f:
                    if write_header:
                        f.write("datetime,side,entry_type,entry_price,reason\n")
                    for row in items:
                        line = ",".join([
                            row["datetime"],
                            row["side"],
                            row["entry_type"],
                            row["entry_price"],
                            row["reason"]
                        ])
                        f.write(line + "\n")
                saved_files += 1
                saved_rows += len(items)
                touched_dates.add(date_key)
            except OSError as e:
                raise Exception(f"CSV保存に失敗しました:\n{e}") from e

        return saved_files, saved_rows

    def parse_ai_datetime(self, dt_raw):
        """AI出力の日時を解析"""
        match = re.match(r"^(\d{2})[.\-\/](\d{2})[.\-\/](\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?$", dt_raw)
        if not match:
            return None
        yy, mm, dd, hh, mi, _ = match.groups()
        try:
            year = 2000 + int(yy)
            month = int(mm)
            day = int(dd)
            hour = int(hh)
            minute = int(mi)
            datetime(int(year), month, day, hour, minute)
        except ValueError:
            return None

        date_key = f"{year:04d}{month:02d}{day:02d}"
        datetime_str = f"{int(yy):02d}.{month:02d}.{day:02d} {hour:02d}:{minute:02d}"
        return {"date_key": date_key, "datetime": datetime_str}

    def load_prompt_text(self):
        """プロンプトを読み込む"""
        if not os.path.exists(self.prompt_path):
            return ""
        try:
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def load_api_key(self):
        """APIキーを取得"""
        for key_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if os.environ.get(key_name):
                return os.environ.get(key_name)

        env_paths = [
            os.path.join(self.app_dir, ".env.local"),
            os.path.join(self.app_dir, ".env")
        ]
        for env_path in env_paths:
            if not os.path.exists(env_path):
                continue
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                            return v
            except OSError:
                continue
        return ""

    def call_gemini_api(self, full_text, model, api_key):
        """Geminiに送信して結果を返す"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": full_text}]
                }
            ]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
            except OSError:
                error_body = str(e)
            raise Exception(error_body) from e
        resp_json = json.loads(body)
        try:
            return resp_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return json.dumps(resp_json, ensure_ascii=False, indent=2)


def main():
    root = tk.Tk()
    app = LogAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
