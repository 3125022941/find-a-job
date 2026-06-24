#!/usr/bin/env python3
"""
合并「小红书 + 抖音」两套监控的进展，生成一张总表，并算出统一的「新开公司」通知。

读：
  Spider_XHS/recruit_out/progress.json   （小红书）
  MediaCrawler/dy_out/progress.json       （抖音）
写：
  recruit_out/总表-2027提前批.md          （合并总表）
  recruit_out/master_new_companies.json    （本次相对历史新出现的公司）
  recruit_out/notify_message.txt           （现成中文通知文案，给 run_daily.ps1 读）
  recruit_out/master_seen.json             （历史已记录公司，用于判新）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(r"f:\recruit_monitor")
XHS_PROGRESS = ROOT / "Spider_XHS" / "recruit_out" / "progress.json"
DY_PROGRESS = ROOT / "MediaCrawler" / "dy_out" / "progress.json"
CFG = ROOT / "Spider_XHS" / "recruit_config.yaml"
OUT = ROOT / "recruit_out"
MASTER_SEEN = OUT / "master_seen.json"


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def companies_universe() -> list[str]:
    try:
        import yaml
        cfg = yaml.safe_load(CFG.read_text("utf-8")) or {}
        return cfg.get("companies", [])
    except Exception:
        return []


def main() -> int:
    xhs = load_json(XHS_PROGRESS, {})
    dy = load_json(DY_PROGRESS, {})
    OUT.mkdir(parents=True, exist_ok=True)

    all_companies = set(xhs) | set(dy)

    rows = []
    for comp in all_companies:
        x, d = xhs.get(comp), dy.get(comp)
        sources = [s for s, rec in (("小红书", x), ("抖音", d)) if rec]
        # 取分数更高的那条作为「最强信号」
        best, best_src = None, ""
        for rec, src in ((x, "小红书"), (d, "抖音")):
            if rec and (best is None or rec.get("score", 0) > best.get("score", 0)):
                best, best_src = rec, src
        updated = max([r.get("updated", "") for r in (x, d) if r], default="")
        rows.append({"company": comp, "sources": sources, "best": best or {},
                     "best_src": best_src, "updated": updated})

    rows.sort(key=lambda r: (r["updated"], r["best"].get("score", 0)), reverse=True)

    # ---- 渲染总表 ----
    lines = [
        "# 2027届互联网大厂秋招提前批 · 合并总表（小红书 + 抖音）",
        "",
        f"> 更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}　数据源：小红书 + 抖音搜索，仅供参考，**以官方为准**",
        "",
        "| 公司 | 来源 | 最强信号 | 关键词 | 👍 | 更新 | 链接 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        b = r["best"]
        title = (b.get("title", "") or "").replace("|", "／")[:40]
        src = "＋".join(r["sources"])
        lines.append(
            f"| {r['company']} | {src} | {title} | {b.get('keyword','')} | {b.get('liked','')} "
            f"| {r['updated']} | [看]({b.get('url','')}) |"
        )

    # 还没有任何信号的公司
    rest = [c for c in companies_universe() if c not in all_companies]
    for comp in rest:
        lines.append(f"| {comp} | — | — 暂无线索 — |  |  |  |  |")
    lines.append("")
    (OUT / "总表-2027提前批.md").write_text("\n".join(lines), "utf-8")

    # ---- 新开公司（相对历史） ----
    seen = set(load_json(MASTER_SEEN, []))
    new_companies = sorted([c for c in all_companies if c not in seen])
    notify_msg = (
        f"提前批新开：{'、'.join(new_companies)}（小红书/抖音，详情见 总表-2027提前批.md）"
        if new_companies else ""
    )
    (OUT / "master_new_companies.json").write_text(
        json.dumps(new_companies, ensure_ascii=False), "utf-8")
    (OUT / "notify_message.txt").write_text(notify_msg, "utf-8")
    # 更新历史
    (MASTER_SEEN).write_text(
        json.dumps(sorted(all_companies), ensure_ascii=False, indent=2), "utf-8")

    print(f"合并完成：{len(all_companies)} 家有信号，本次新开 {len(new_companies)} 家"
          + (f"：{'、'.join(new_companies)}" if new_companies else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
