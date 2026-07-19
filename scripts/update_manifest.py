#!/usr/bin/env python3
import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


FIELDS = [
    "序号",
    "论文名称",
    "作者",
    "DOI",
    "状态",
    "尝试次数",
    "直接下载结果",
    "浏览器结果",
    "候选链接",
    "版本类型",
    "本地文件",
    "来源页面",
    "下载链接",
    "失败原因",
    "更新时间",
]
STATUSES = [
    "待处理",
    "直接下载中",
    "需浏览器尝试",
    "浏览器下载中",
    "已验证下载",
    "需人工核验",
    "未完成下载",
]


def normalize_doi(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", cleaned, flags=re.I)
    return cleaned.strip().casefold()


def normalize_title(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def row_key(row):
    doi = normalize_doi(row.get("DOI", ""))
    return f"doi:{doi}" if doi else f"title:{normalize_title(row.get('论文名称', ''))}"


def read_rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return [{field: row.get(field, "") for field in FIELDS} for row in reader]


def sort_key(row):
    value = row.get("序号", "").strip()
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a resumable paper-download manifest.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--number", default="")
    parser.add_argument("--title", required=True)
    parser.add_argument("--authors", default="")
    parser.add_argument("--doi", default="")
    parser.add_argument("--status", required=True, choices=STATUSES)
    parser.add_argument("--version", default="")
    parser.add_argument("--local-file", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--link", default="")
    parser.add_argument("--failure", default="")
    parser.add_argument("--direct-result", default="")
    parser.add_argument("--browser-result", default="")
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--increment-attempt", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "下载结果.csv"
    rows = read_rows(manifest)

    incoming = {
        "序号": args.number.strip(),
        "论文名称": " ".join(args.title.split()),
        "作者": " ".join(args.authors.split()),
        "DOI": normalize_doi(args.doi),
        "状态": args.status,
        "尝试次数": "",
        "直接下载结果": args.direct_result.strip(),
        "浏览器结果": args.browser_result.strip(),
        "候选链接": "",
        "版本类型": args.version.strip(),
        "本地文件": args.local_file.strip(),
        "来源页面": args.source.strip(),
        "下载链接": args.link.strip(),
        "失败原因": args.failure.strip(),
        "更新时间": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    key = row_key(incoming)
    if key in {"doi:", "title:"}:
        raise ValueError("a DOI or non-empty title is required.")

    existing_index = None
    for index, row in enumerate(rows):
        if row_key(row) == key:
            existing_index = index
            break

    updated = rows[existing_index].copy() if existing_index is not None else {field: "" for field in FIELDS}
    for field in ["序号", "论文名称", "作者", "DOI", "版本类型", "本地文件", "来源页面", "下载链接"]:
        if incoming[field]:
            updated[field] = incoming[field]
    updated["状态"] = incoming["状态"]
    if incoming["直接下载结果"]:
        updated["直接下载结果"] = incoming["直接下载结果"]
    if incoming["浏览器结果"]:
        updated["浏览器结果"] = incoming["浏览器结果"]
    if incoming["失败原因"] or args.status == "已验证下载":
        updated["失败原因"] = incoming["失败原因"]

    candidates = [value.strip() for value in updated.get("候选链接", "").split(" | ") if value.strip()]
    candidates.extend(value.strip() for value in args.candidate if value.strip())
    if args.link.strip():
        candidates.append(args.link.strip())
    updated["候选链接"] = " | ".join(dict.fromkeys(candidates))

    try:
        attempts = int(updated.get("尝试次数", "") or 0)
    except ValueError:
        attempts = 0
    if args.increment_attempt:
        attempts += 1
    updated["尝试次数"] = str(attempts)
    updated["更新时间"] = incoming["更新时间"]

    if existing_index is None:
        rows.append(updated)
    else:
        rows[existing_index] = updated

    rows.sort(key=sort_key)
    with manifest.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(manifest.resolve())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
