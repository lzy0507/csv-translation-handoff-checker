"""Read-only CSV handoff checker. Python 3.10+, standard library only."""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import io
from pathlib import Path
import sys
from dataclasses import dataclass, field

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50000
csv.field_size_limit(262144)
ROLES = ("old_source", "new_source", "returned_translation")
TITLES = {
    "added": "新增ID", "deleted": "删除ID", "changed": "修改文本",
    "missing": "缺失翻译", "duplicate": "重复ID", "risk": "潜在错误覆盖",
}
@dataclass
class Table:
    role: str
    name: str
    digest: str = ""
    columns: list[str] = field(default_factory=list)
    rows: dict[str, list[dict]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

def read_table(path: Path, role: str) -> Table:
    t = Table(role, path.name)
    try:
        with path.open("rb") as f:
            data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("超过10 MiB输入上限")
        t.digest = hashlib.sha256(data).hexdigest()
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("含NUL字符；可能不是UTF-8 CSV")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        t.columns = next(reader, [])
        required = {"id", "source"}
        if role == "returned_translation":
            required.add("translation")
        if not t.columns or len(t.columns) != len(set(t.columns)):
            raise ValueError("表头为空或含重复列名")
        if any(not c or c != c.strip() for c in t.columns):
            raise ValueError("列名不能为空或带首尾空格")
        if not required.issubset(t.columns):
            raise ValueError("缺少必需列：" + ", ".join(sorted(required - set(t.columns))))
        count = 0
        for values in reader:
            if not values:  # Only truly empty physical records are skipped.
                continue
            count += 1
            if count > MAX_ROWS:
                raise ValueError("超过50000条记录上限")
            if len(values) != len(t.columns):
                raise ValueError(f"结束于物理行{reader.line_num}的记录列数不一致")
            row = dict(zip(t.columns, values))
            key = row["id"]
            if not key.strip() or key != key.strip():
                raise ValueError(f"结束于物理行{reader.line_num}的ID为空或含首尾空格")
            row["_line"] = reader.line_num
            t.rows.setdefault(key, []).append(row)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        # No traceback or CSV content in the terminal.
        t.errors.append(f"{type(exc).__name__}: {exc}")
    return t

def analyze(tables: list[Table]) -> dict:
    result = {"sections": {k: [] for k in TITLES}, "notes": [],
              "errors": [], "eligible": [], "skipped": []}
    old, new, returned = tables
    for t in tables:
        result["errors"].extend(f"{t.role}: {x}" for x in t.errors)
    if result["errors"]:
        return result
    sections = result["sections"]
    blocked = set()
    for t in tables:
        for key, rows in t.rows.items():
            if len(rows) > 1:
                blocked.add(key)
                sections["duplicate"].append({
                    "id": key, "reason": f"{t.role}重复{len(rows)}次；不选第一条或最后一条",
                    "detail": "记录结束行：" + ", ".join(str(x["_line"]) for x in rows),
                })
    # Diff membership does not depend on choosing any duplicate row.
    for key in sorted(new.rows.keys() - old.rows.keys()):
        sections["added"].append({"id": key, "reason": "新源文件出现；没有旧送译基线", "detail": ""})
    for key in sorted(old.rows.keys() - new.rows.keys()):
        sections["deleted"].append({"id": key, "reason": "旧源文件存在，新源文件已无此ID", "detail": ""})
    for key in sorted((old.rows.keys() & new.rows.keys()) - blocked):
        a, b = old.rows[key][0], new.rows[key][0]
        if a["source"] != b["source"]:
            sections["changed"].append({"id": key, "reason": "原文精确比较不同（含空格/换行）",
                                       "detail": f"旧：{a['source']}\n新：{b['source']}"})
    for key in sorted(new.rows):
        if key in blocked:
            result["skipped"].append(key)
            continue
        rs = returned.rows.get(key)
        if not rs or not rs[0]["translation"].strip():
            sections["missing"].append({
                "id": key, "reason": "返回文件缺少该ID" if not rs else "返回译文为空/仅空白",
                "detail": "表示本次回收缺失，不等于项目从未有译文；不会清空现有译文。",
            })
    can_compare_target = all("translation" in t.columns for t in (old, new))
    if not can_compare_target:
        result["notes"].append(
            "覆盖检查不完整：old_source与new_source未同时提供translation列，"
            "不能检查送译期间现有译文是否被其他人修改。")
    for key in sorted(returned.rows):
        reasons = []
        if key in blocked:
            reasons.append("ID重复，无法确定对应关系，必须人工核对")
        else:
            r = returned.rows[key][0]
            if key not in new.rows:
                reasons.append("返回ID已删除" if key in old.rows else "返回ID未知（两份源文件都没有）")
            elif key not in old.rows:
                reasons.append("新ID无旧送译基线，不能验证此次返回是否属于正确批次")
            else:
                a, b = old.rows[key][0], new.rows[key][0]
                if a["source"] != b["source"]:
                    reasons.append("送译后原文改变，返回译文可能已过期")
                if r["source"] != a["source"]:
                    reasons.append("返回source与旧送译原文不一致，可能改写原文或混入其他批次")
                if can_compare_target and b["translation"] != a["translation"]:
                    if r["translation"] != b["translation"]:
                        reasons.append("当前译文已被修改，直接回填可能覆盖该修改")
                if not r["translation"].strip():
                    reasons.append("空译文若直接回填可能清空原有内容；本工具不执行回填")
            if not reasons and r["translation"].strip():
                result["eligible"].append(key)
        if reasons:
            detail = ""
            if key not in blocked:
                values = []
                for table, label in ((old, "送译时"), (new, "当前"), (returned, "返回")):
                    if key in table.rows:
                        row = table.rows[key][0]
                        values.append(f"{label}原文：{row['source']}\n{label}译文：{row.get('translation', '（未提供该列）')}")
                detail = "\n\n".join(values)
            sections["risk"].append({"id": key, "reason": "；".join(reasons), "detail": detail})
    if blocked:
        result["notes"].append("重复ID涉及的条目不执行文本、缺译推断；所有重复位置已列出，不能视作已通过。")
    return result

def render(tables: list[Table], result: dict) -> str:
    e = lambda x: html.escape(str(x), quote=True)
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<title>CSV译文回收检查报告</title><style>',
        'body{font:16px/1.65 system-ui,sans-serif;color:#223247;background:#f7f9fc;margin:0;padding:28px}'
        'main{max-width:1120px;margin:auto}h1{font-size:28px}h2{margin-top:32px}'
        '.banner{padding:16px;background:#fff0cb;border-left:5px solid #d19a20}'
        '.cards{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}.card{background:white;padding:14px;min-width:115px;border:1px solid #d6dfe8}'
        '.card b{display:block;font-size:26px}table{width:100%;border-collapse:collapse;background:white}'
        'td,th{border:1px solid #d6dfe8;padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}'
        'th{background:#eaf0f7}pre{white-space:pre-wrap;margin:0;font:inherit;overflow-wrap:anywhere}'
        '.muted{color:#526477}code{overflow-wrap:anywhere}a{color:#185fa6}'
        '@media(max-width:600px){body{padding:12px}td,th{padding:6px}}',
        '</style></head><body><main><h1>CSV译文回收检查报告</h1>',
        '<p class="muted">只读检查 · 不翻译 · 不合并 · 不自动导入</p>']
    if result["errors"]:
        parts.append('<div class="banner"><b>输入无效：六项检查未完成。</b><ul>')
        parts.extend(f"<li>{e(x)}</li>" for x in result["errors"])
        parts.append('</ul>修复输入后重新运行；没有“全部通过”的结论。</div>')
    else:
        parts.append('<div class="banner">报告列出需要核对的变化与风险，不判断译文质量。'
                     '一个ID可能出现在多项检查中，计数不能相加当作错误总数。</div><div class="cards">')
        for k, title in TITLES.items():
            parts.append(f'<a class="card" href="#{k}">{e(title)}<b>{len(result["sections"][k])}</b></a>')
        parts.append('</div>')
        for note in result["notes"]:
            parts.append(f'<p class="banner">{e(note)}</p>')
        for k, title in TITLES.items():
            parts.append(f'<h2 id="{k}">{e(title)} ({len(result["sections"][k])})</h2>')
            items = result["sections"][k]
            if not items:
                parts.append('<p>本项未检出；重复ID跳过项及覆盖限制见说明。</p>')
                continue
            parts.append('<table><thead><tr><th>ID</th><th>判断依据</th><th>详情</th></tr></thead><tbody>')
            for item in items:
                parts.append(f'<tr><td>{e(item["id"])}</td><td>{e(item["reason"])}</td>'
                             f'<td><pre>{e(item["detail"])}</pre></td></tr>')
            parts.append('</tbody></table>')
        parts.append('<h2>未检出上述风险的返回条目</h2><p>仅表示在提供的三份文件与已启用规则范围内未检出；'
                     '不等于可直接导入，不验证语言、语义、占位符或富文本。</p>')
        parts.append('<p>' + (e(", ".join(result["eligible"])) or "无") + '</p>')
        if result["skipped"]:
            parts.append('<p>重复ID导致缺译判断跳过：' + e(", ".join(result["skipped"])) + '</p>')
    parts.append('<h2>输入追溯</h2><p>SHA-256对应读取时的字节。报告包含原文与ID，分享前请自行复核。</p>'
                 '<table><tr><th>角色 / 文件</th><th>记录数</th><th>SHA-256</th></tr>')
    for t in tables:
        parts.append(f'<tr><td>{e(t.role)} / {e(t.name)}</td><td>{sum(map(len,t.rows.values()))}</td>'
                     f'<td><code>{e(t.digest or "未取得")}</code></td></tr>')
    parts.append('</table></main></body></html>')
    return "".join(parts)

def run(paths: list[Path], output: Path) -> int:
    if output.suffix.lower() != ".html":
        raise ValueError("输出必须为.html文件")
    if any(output.resolve() == p.resolve() for p in paths):
        raise ValueError("输出不得指向输入文件")
    if output.exists() or output.is_symlink():
        raise ValueError("输出已存在；请选择新文件名，不覆盖")
    tables = [read_table(p, role) for p, role in zip(paths, ROLES)]
    result = analyze(tables)
    document = render(tables, result)
    # Exclusive creation also refuses existing hard links and race-time collisions.
    with output.open("x", encoding="utf-8", newline="\n") as f:
        f.write(document)
    if result["errors"]:
        return 2
    return int(any(result["sections"].values()) or bool(result["notes"]))

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="三份CSV只读核对，输出HTML。单一目标语言，不做回填。")
    parser.add_argument("old_source", type=Path)
    parser.add_argument("new_source", type=Path)
    parser.add_argument("returned_translation", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        code = run([args.old_source, args.new_source, args.returned_translation], args.output)
        print(f"报告已生成。退出码{code}（0无发现；1有变化/风险/检查限制；2输入无效）。")
        return code
    except (OSError, ValueError) as exc:
        print(f"未完成：{exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())

