import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from datetime import date, datetime, timedelta
import calendar
import json
import os
import re
import threading

class LogAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ドル円スレ ログ解析ツール")
        self.root.geometry("800x700")
        self.root.resizable(True, True)

        # ログディレクトリのパス
        self.logs_dir = r"C:\Users\USER\Desktop\FXlog\logs"
        # レートデータのパス（1分足）
        self.rates_dir = r"C:\Users\USER\Desktop\FXlog\data\usdjpy\m1"

        # 処理中フラグ
        self.is_processing = False
        # レートの簡易キャッシュ
        self.rate_cache = {}

        self.create_widgets()

    def create_widgets(self):
        # タイトル
        title_label = ttk.Label(
            self.root,
            text="ドル円スレ ログ解析ツール",
            font=("Meiryo UI", 14, "bold")
        )
        title_label.pack(pady=15)

        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 期間指定
        period_frame = ttk.LabelFrame(main_frame, text="期間指定", padding=10)
        period_frame.pack(fill=tk.X, pady=10)

        # 開始日
        start_frame = ttk.Frame(period_frame)
        start_frame.pack(fill=tk.X, pady=5)
        ttk.Label(start_frame, text="開始日:").pack(side=tk.LEFT)
        self.start_date = tk.StringVar(value="2026-01-01")
        start_entry = ttk.Entry(start_frame, textvariable=self.start_date, width=15)
        start_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(start_frame, text="📅", width=4, command=lambda: self.show_calendar(self.start_date)).pack(side=tk.LEFT)

        # 終了日
        end_frame = ttk.Frame(period_frame)
        end_frame.pack(fill=tk.X, pady=5)
        ttk.Label(end_frame, text="終了日:").pack(side=tk.LEFT)
        self.end_date = tk.StringVar(value="2026-01-31")
        end_entry = ttk.Entry(end_frame, textvariable=self.end_date, width=15)
        end_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(end_frame, text="📅", width=4, command=lambda: self.show_calendar(self.end_date)).pack(side=tk.LEFT)

        # オプション
        option_frame = ttk.LabelFrame(main_frame, text="オプション", padding=10)
        option_frame.pack(fill=tk.X, pady=10)

        # 土日除外
        self.exclude_weekends = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            option_frame,
            text="土日は除外（月7:00〜土6:59のみ）",
            variable=self.exclude_weekends
        ).pack(anchor=tk.W, pady=5)

        # バッチサイズ
        batch_frame = ttk.Frame(option_frame)
        batch_frame.pack(fill=tk.X, pady=5)
        ttk.Label(batch_frame, text="何レスずつAIに渡すか:").pack(side=tk.LEFT)
        self.batch_size = tk.IntVar(value=20)
        batch_spin = ttk.Spinbox(
            batch_frame,
            from_=1,
            to=1000,
            textvariable=self.batch_size,
            width=10
        )
        batch_spin.pack(side=tk.LEFT, padx=5)

        # 設定確認エリア
        info_frame = ttk.LabelFrame(main_frame, text="設定確認", padding=10)
        info_frame.pack(fill=tk.X, pady=10)

        self.info_text = tk.Text(info_frame, height=4, width=50, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True)

        # 更新ボタン
        ttk.Button(info_frame, text="設定を更新", command=self.update_info).pack(anchor=tk.E, pady=5)
        self.update_info()

        # ステータス表示
        self.status_label = ttk.Label(main_frame, text="", foreground="blue")
        self.status_label.pack(pady=5)

        # 実行ボタン
        self.run_button = ttk.Button(
            main_frame,
            text="解析実行",
            command=self.run_analysis
        )
        self.run_button.pack(fill=tk.X, pady=10)

        # 結果表示エリア（同一ウィンドウ内）
        result_frame = ttk.LabelFrame(main_frame, text="抽出結果", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        result_top = ttk.Frame(result_frame)
        result_top.pack(fill=tk.X, pady=(0, 8))

        self.result_count_var = tk.StringVar(value="抽出件数: 0件")
        self.result_count_label = ttk.Label(result_top, textvariable=self.result_count_var)
        self.result_count_label.pack(side=tk.LEFT)

        display_frame = ttk.Frame(result_top)
        display_frame.pack(side=tk.RIGHT)

        ttk.Label(display_frame, text="表示上限:").pack(side=tk.LEFT)
        self.display_limit = tk.IntVar(value=200)
        display_spin = ttk.Spinbox(
            display_frame,
            from_=10,
            to=5000,
            textvariable=self.display_limit,
            width=6
        )
        display_spin.pack(side=tk.LEFT, padx=5)

        ttk.Button(display_frame, text="クリア", command=self.clear_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(display_frame, text="コピー", command=self.copy_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(display_frame, text="保存", command=self.save_results).pack(side=tk.LEFT)

        self.result_text = scrolledtext.ScrolledText(
            result_frame,
            wrap=tk.NONE,
            font=("MS Gothic", 9)
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)
        self.result_text.config(state=tk.DISABLED)

        self.last_posts = []

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
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)

        info = f"開始日: {self.start_date.get()}\n"
        info += f"終了日: {self.end_date.get()}\n"
        info += f"土日除外: {'ON' if self.exclude_weekends.get() else 'OFF'}\n"
        info += f"バッチサイズ: {self.batch_size.get()}レス"

        self.info_text.insert(1.0, info)
        self.info_text.config(state=tk.DISABLED)

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

        # 対象期間に関係しそうなファイルだけを拾う（開始日の前日も含める）
        file_start_dt = start_dt - timedelta(days=1)
        file_end_dt = end_dt

        log_files = []
        for f in os.listdir(self.logs_dir):
            if not f.endswith(".jsonl"):
                continue
            match = re.match(r"^usdjpy_\d+_(\d{8})\.jsonl$", f)
            if not match:
                continue
            file_date_str = match.group(1)
            try:
                file_dt = datetime.strptime(file_date_str, "%Y%m%d")
            except ValueError:
                continue
            if file_start_dt.date() <= file_dt.date() <= file_end_dt.date():
                log_files.append((file_dt, f))

        # 日付順に並べる（読み込み順は結果に影響しないが見通しのため）
        log_files.sort(key=lambda x: x[0])

        for _, log_file in log_files:

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

        # 日付順（新しい順）にソート
        posts_with_dt.sort(key=lambda x: x[0], reverse=True)

        # フォーマット済みテキストのみを返す
        return [formatted for _, formatted in posts_with_dt]

    def parse_posted_at(self, posted_at):
        """posted_atをdatetimeに変換 (例: '2026年1月16日 23:59')"""
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})', posted_at)
        if match:
            year, month, day, hour, minute = match.groups()
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
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

        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)

        limit = max(1, int(self.display_limit.get()))
        display_limit = min(limit, len(posts))
        for post in posts[:display_limit]:
            self.result_text.insert(tk.END, post + "\n")

        if len(posts) > display_limit:
            self.result_text.insert(tk.END, f"\n... 他 {len(posts) - display_limit}件\n")

        self.result_text.config(state=tk.DISABLED)

    def clear_results(self):
        """結果表示をクリア"""
        self.last_posts = []
        self.result_count_var.set("抽出件数: 0件")
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state=tk.DISABLED)

    def copy_results(self):
        """表示中の結果をクリップボードへコピー"""
        text = self.result_text.get(1.0, tk.END).strip()
        if not text:
            messagebox.showinfo("情報", "コピーする内容がありません")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("情報", "コピーしました")

    def save_results(self):
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


def main():
    root = tk.Tk()
    app = LogAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
