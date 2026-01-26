import json
import os

# 入力ファイル（テスト用）
input_file = r"C:\Users\USER\Desktop\FXlog\logs_1h\usdjpy_20260116\usdjpy_2026011623.jsonl"
# 出力ディレクトリ
output_dir = r"C:\Users\USER\Desktop\FXlog\logs_1h_f\usdjpy_20260116"
# 出力ファイル名
output_file = os.path.join(output_dir, "usdjpy_2026011623.jsonl")

# 出力ディレクトリが存在しない場合は作成
os.makedirs(output_dir, exist_ok=True)

# JSONLファイルを読み込んで処理
with open(input_file, 'r', encoding='utf-8') as f_in, \
     open(output_file, 'w', encoding='utf-8') as f_out:

    for line in f_in:
        if line.strip():
            data = json.loads(line)
            # posted_at と text のみを残す
            filtered_data = {
                "posted_at": data.get("posted_at", ""),
                "text": data.get("text", "")
            }
            f_out.write(json.dumps(filtered_data, ensure_ascii=False) + '\n')

print(f"Created: {output_file}")
