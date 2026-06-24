#!/usr/bin/env python3
"""
抖音秋招提前批采集 —— 基于 MediaCrawler。

做的事：
1. 调 MediaCrawler 搜抖音关键词（无头 Playwright + cookie 登录）。
2. 读它存到 data/douyin/json 的结果，按「大厂名 + 提前批/网申/内推」打分过滤。
3. 跟 dy_out/seen.json 去重，只留新增。
4. 落本地文件：dy_out/logs/dy-check-YYYY-MM-DD.md + dy_out/抖音提前批进展.md

用法（在 MediaCrawler 目录下，用它的 .venv）：
    .venv\\Scripts\\python.exe dy_recruit_collect.py            # 无头跑
    .venv\\Scripts\\python.exe dy_recruit_collect.py --show     # 显示浏览器（首次登录/过验证用）
    .venv\\Scripts\\python.exe dy_recruit_collect.py --dry-run  # 不写 seen / 不更新总表
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

import yaml

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
DATA_DIR = ROOT / "data" / "douyin"
OUT_DIR = ROOT / "dy_out"
LOG_DIR = OUT_DIR / "logs"
COOKIE_FILE = ROOT / ".dy_cookie.txt"
# 复用小红书那套打分配置，保证两边口径一致
SCORING_CFG = Path(r"f:\recruit_monitor\Spider_XHS\recruit_config.yaml")

DEFAULT_KEYWORDS = ["秋招提前批", "2027届提前批", "互联网提前批", "研发提前批"]
DEFAULT_COMPANIES = ["腾讯", "阿里", "字节", "美团", "快手", "百度", "京东", "网易",
                     "小米", "华为", "拼多多", "滴滴", "携程", "蔚来", "大疆"]
DEFAULT_HOTWORDS = ["已开启", "正式启动", "提前批开启", "网申开启", "网申", "投递",
                    "投递链接", "内推码", "内推", "截止", "研发", "算法", "后端", "前端", "产品经理"]


def load_scoring() -> tuple[list[str], list[str], list[str]]:
    companies, hot_words, keywords = DEFAULT_COMPANIES, DEFAULT_HOTWORDS, DEFAULT_KEYWORDS
    if SCORING_CFG.exists():
        try:
            cfg = yaml.safe_load(SCORING_CFG.read_text("utf-8")) or {}
            companies = cfg.get("companies", companies)
            hot_words = cfg.get("hot_words", hot_words)
            keywords = cfg.get("keywords", keywords)
        except Exception:
            pass
    return companies, hot_words, keywords


def score_text(text: str, companies: list[str], hot_words: list[str]) -> tuple[int, list[str]]:
    score, matched = 0, []
    low = text.lower()
    for c in companies:
        if c.lower() in low:
            score += 3
            matched.append(c)
    for w in hot_words:
        if w.lower() in low:
            score += 2
    if "提前批" in text:
        score += 4
    if "秋招" in text:
        score += 3
    if "校招" in text or "校园招聘" in text:
        score += 2
    if "2027" in text or "27届" in text:
        score += 2
    return score, matched


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def run_mediacrawler(keywords: list[str], cookie: str, max_notes: int, show: bool) -> None:
    cmd = [
        str(VENV_PY), "main.py",
        "--platform", "dy", "--lt", "cookie", "--type", "search",
        "--keywords", ",".join(keywords),
        "--cookies", cookie,
        "--save_data_option", "json",
        "--get_comment", "no",
        "--headless", "no" if show else "yes",
        "--crawler_max_notes_count", str(max_notes),
    ]
    print(f"▶ 启动 MediaCrawler 抖音搜索：{ '、'.join(keywords) }")
    subprocess.run(cmd, cwd=str(ROOT), check=False)


def collect_items(since_ts: float) -> list[dict[str, Any]]:
    """读取本次运行后 data/douyin 下新增的 json，抽出笔记内容项。"""
    items: list[dict[str, Any]] = []
    if not DATA_DIR.exists():
        return items
    for p in DATA_DIR.rglob("*.json"):
        try:
            if p.stat().st_mtime < since_ts - 2:
                continue
            data = json.loads(p.read_text("utf-8"))
        except Exception:
            continue
        rows = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        for r in rows:
            if isinstance(r, dict) and r.get("aweme_id") and ("title" in r or "desc" in r):
                items.append(r)
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description="抖音秋招提前批采集（MediaCrawler）")
    ap.add_argument("--max", type=int, default=20, help="每个关键词最多取多少条（抖音最少 10）")
    ap.add_argument("--show", action="store_true", help="显示浏览器窗口（首次登录/过验证）")
    ap.add_argument("--dry-run", action="store_true", help="不写 seen / 不更新总表")
    args = ap.parse_args()

    cookie = (COOKIE_FILE.read_text("utf-8").strip() if COOKIE_FILE.exists() else "")
    cookie = cookie.replace("\r", "").replace("\n", "").strip()
    if not cookie:
        print(f"❌ 未配置抖音 Cookie。请把登录后的 cookie 整段贴进：{COOKIE_FILE}")
        return 2

    companies, hot_words, keywords = load_scoring()
    today = datetime.now().strftime("%Y-%m-%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    start = time.time()
    run_mediacrawler(keywords, cookie, args.max, args.show)
    raw = collect_items(start)
    print(f"📥 抖音采到 {len(raw)} 条原始内容")

    # 打分过滤 + 去重（按 aweme_id 取最高分）
    best: dict[str, dict[str, Any]] = {}
    for r in raw:
        aid = r.get("aweme_id", "")
        text = f"{r.get('title','')} {r.get('desc','')}"
        score, matched = score_text(text, companies, hot_words)
        if score < 4:
            continue
        hit = {
            "aweme_id": aid,
            "title": (r.get("title") or r.get("desc") or "（无标题）").replace("\n", " ").strip()[:80],
            "url": r.get("aweme_url") or f"https://www.douyin.com/video/{aid}",
            "nickname": r.get("nickname", ""),
            "liked": str(r.get("liked_count", "")),
            "keyword": r.get("source_keyword", ""),
            "companies": matched,
            "score": score,
        }
        if aid not in best or score > best[aid]["score"]:
            best[aid] = hit
    hits = sorted(best.values(), key=lambda h: h["score"], reverse=True)

    seen_path = OUT_DIR / "seen.json"
    progress_path = OUT_DIR / "progress.json"
    seen = set(load_json(seen_path, []))
    progress = load_json(progress_path, {})
    fresh = [h for h in hits if h["aweme_id"] not in seen]

    # 快照
    lines = [f"# 抖音提前批监控快照 · {today}", "",
             f"> 命中 {len(hits)} 条相关视频，其中**新增 {len(fresh)} 条**。"
             + ("（dry-run）" if args.dry_run else ""), ""]
    if fresh:
        lines.append("## 🆕 新增线索（按评分高到低）")
        lines.append("")
        for h in fresh:
            comp = "、".join(h["companies"]) if h["companies"] else "—"
            lines.append(f"- **[{h['score']}分] {h['title']}**")
            lines.append(f"  - 公司：{comp}｜关键词：{h['keyword']}｜👍{h['liked']}｜作者：{h['nickname']}")
            lines.append(f"  - 链接：{h['url']}")
            lines.append("")
    else:
        lines.append("本次没有发现新的抖音提前批线索。")
    snapshot = "\n".join(lines)
    print("\n" + snapshot)

    if not args.dry_run:
        (LOG_DIR / f"dy-check-{today}.md").write_text(snapshot, "utf-8")
        new_companies: list[str] = []
        for h in fresh:
            seen.add(h["aweme_id"])
            for comp in h["companies"]:
                if comp not in progress:
                    new_companies.append(comp)
                cur = progress.get(comp)
                if cur is None or h["score"] >= cur.get("score", 0):
                    progress[comp] = {"score": h["score"], "title": h["title"], "url": h["url"],
                                      "keyword": h["keyword"], "liked": h["liked"],
                                      "first_seen": cur.get("first_seen", today) if cur else today,
                                      "updated": today}
        save_json(seen_path, sorted(seen))
        save_json(progress_path, progress)
        # 进展总表
        t = ["# 抖音 · 2027届提前批进展", "",
             f"> 更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}（数据源：抖音搜索，仅供参考）", "",
             "| 公司 | 最新信号 | 关键词 | 👍 | 首次 | 更新 | 链接 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
        for comp in sorted(progress, key=lambda c: progress[c].get("updated", ""), reverse=True):
            p = progress[comp]
            t.append(f"| {comp} | {p.get('title','')[:40]} | {p.get('keyword','')} | {p.get('liked','')} "
                     f"| {p.get('first_seen','')} | {p.get('updated','')} | [看]({p.get('url','')}) |")
        (OUT_DIR / "抖音提前批进展.md").write_text("\n".join(t), "utf-8")
        print(f"\n✅ 已写入 {LOG_DIR / f'dy-check-{today}.md'}")
        if new_companies:
            print(f"🔔 抖音本次新开：{'、'.join(new_companies)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
