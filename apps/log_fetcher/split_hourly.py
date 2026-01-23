import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


POSTED_AT_RE = re.compile(
    r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2}):(\d{2})(?::(\d{2}))?"
)
ALT_POSTED_AT_RE = re.compile(
    r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})\s*(\d{1,2}):(\d{2})(?::(\d{2}))?"
)


def parse_posted_at(text: str, missing_year: int) -> Optional[datetime]:
    if not text:
        return None

    match = POSTED_AT_RE.search(text)
    if match:
        year_text, month_text, day_text, hour_text, minute_text, second_text = match.groups()
        year = int(year_text) if year_text else missing_year
        second = int(second_text) if second_text else 0
        try:
            return datetime(
                year,
                int(month_text),
                int(day_text),
                int(hour_text),
                int(minute_text),
                second,
            )
        except ValueError:
            return None

    match = ALT_POSTED_AT_RE.search(text)
    if match:
        year_text, month_text, day_text, hour_text, minute_text, second_text = match.groups()
        second = int(second_text) if second_text else 0
        try:
            return datetime(
                int(year_text),
                int(month_text),
                int(day_text),
                int(hour_text),
                int(minute_text),
                second,
            )
        except ValueError:
            return None

    return None


def derive_prefix(input_path: Path) -> str:
    name = input_path.name
    if "_" in name:
        return name.split("_", 1)[0]
    return input_path.stem


def ensure_empty_dir(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return
    if not path.is_dir():
        raise SystemExit(f"出力先がフォルダではありません: {path}")
    if any(path.iterdir()):
        raise SystemExit(f"出力先フォルダが空ではありません: {path}")


def write_unknown_line(unknown_path: Path, line: str, handle):
    if handle is None:
        unknown_path.parent.mkdir(parents=True, exist_ok=True)
        handle = unknown_path.open("a", encoding="utf-8", newline="\n")
    handle.write(line + "\n")
    return handle


def main() -> int:
    parser = argparse.ArgumentParser(description="jsonlログを1時間ごとに分割します")
    parser.add_argument("inputs", nargs="+", help="元のjsonlファイルのパス(複数可)")
    parser.add_argument("--out", default="logs_1h", help="出力先フォルダ(新規)")
    parser.add_argument("--missing-year", type=int, default=2026, help="年が無い場合の年")
    parser.add_argument("--prefix", default=None, help="出力ファイル名の先頭(例: usdjpy)")
    args = parser.parse_args()

    input_paths = [Path(p) for p in args.inputs]
    for path in input_paths:
        if not path.exists():
            raise SystemExit(f"入力ファイルが見つかりません: {path}")

    out_root = Path(args.out)
    ensure_empty_dir(out_root)

    writers: dict[Path, object] = {}
    unknown_handles: dict[Path, object] = {}
    total = 0
    written = 0
    unknown = 0

    for input_path in input_paths:
        prefix = args.prefix or derive_prefix(input_path)
        unknown_path = out_root / "不明" / f"{prefix}_不明.jsonl"

        with input_path.open("r", encoding="utf-8") as f:
            first_line = True
            for raw in f:
                total += 1
                line = raw.rstrip("\n")
                if first_line and line.startswith("\ufeff"):
                    line = line.lstrip("\ufeff")
                first_line = False

                if not line.strip():
                    continue

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    unknown += 1
                    handle = unknown_handles.get(unknown_path)
                    unknown_handles[unknown_path] = write_unknown_line(unknown_path, line, handle)
                    continue

                posted_at = obj.get("posted_at") if isinstance(obj, dict) else None
                dt = parse_posted_at(str(posted_at or ""), args.missing_year)
                if dt is None:
                    unknown += 1
                    handle = unknown_handles.get(unknown_path)
                    unknown_handles[unknown_path] = write_unknown_line(unknown_path, line, handle)
                    continue

                date_str = dt.strftime("%Y%m%d")
                hour_str = dt.strftime("%H")
                out_dir = out_root / date_str
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{prefix}_{date_str}{hour_str}.jsonl"

                handle = writers.get(out_path)
                if handle is None:
                    handle = out_path.open("a", encoding="utf-8", newline="\n")
                    writers[out_path] = handle
                handle.write(line + "\n")
                written += 1

    for handle in writers.values():
        handle.close()
    for handle in unknown_handles.values():
        handle.close()

    print(f"入力ファイル数: {len(input_paths)}")
    print(f"総行数: {total}")
    print(f"出力行数: {written}")
    print(f"作成ファイル数: {len(writers)}")
    if unknown:
        print(f"不明行数: {unknown}")
        unknown_paths = ", ".join(str(p) for p in sorted(unknown_handles.keys()))
        print(f"不明の保存先: {unknown_paths}")

    if written == 0:
        return 2
    if unknown:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
