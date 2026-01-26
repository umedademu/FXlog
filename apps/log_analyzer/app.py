import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
import calendar

class LogAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ドル円スレ ログ解析ツール")
        self.root.geometry("500x400")
        self.root.resizable(True, True)

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

        # 実行ボタン
        run_button = ttk.Button(
            main_frame,
            text="解析実行",
            command=self.run_analysis
        )
        run_button.pack(fill=tk.X, pady=15)

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
        if self.start_date.get() > self.end_date.get():
            messagebox.showerror("エラー", "開始日は終了日より前にしてください")
            return

        messagebox.showinfo(
            "準備中",
            "ログ読み込み・AI解析機能は次のステップで実装予定です\n\n"
            f"設定:\n"
            f"期間: {self.start_date.get()} 〜 {self.end_date.get()}\n"
            f"土日除外: {'ON' if self.exclude_weekends.get() else 'OFF'}\n"
            f"バッチサイズ: {self.batch_size.get()}レス"
        )


def main():
    root = tk.Tk()
    app = LogAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
