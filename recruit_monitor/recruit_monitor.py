#!/usr/bin/env python3
"""
每日监控：互联网大厂秋招提前批 / 校招提前批信息。

特点：
- 监控公开搜索结果：小红书、抖音、牛客、脉脉、B站等被搜索引擎收录的内容
- 监控官方招聘页：腾讯/阿里/字节/美团/快手/百度/京东/网易/小米/华为等
- 本地 seen.json 去重
- 支持飞书 / 企业微信机器人提醒

使用：
1. pip install -r requirements.txt
2. cp config.example.yaml config.yaml
3. python recruit_monitor.py --config config.yaml
4. 配合 crontab 每天跑：0 9 * * * cd /path/recruit_monitor && python recruit_monitor.py --config config.yaml
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus, urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


@dataclass
class Hit:
    source: str
    title: str
    url: str
    snippet: str
    keyword: str
    score: int

    @property
    def id(self) -> str:
        raw = f"{self.source}|{self.title}|{self.url}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text("utf-8")))
    except Exception:
        return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), "utf-8")


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:500]


def score_hit(text: str, companies: list[str], hot_words: list[str]) -> int:
    score = 0
    for c in companies:
        if c.lower() in text.lower():
            score += 3
    for w in hot_words:
        if w.lower() in text.lower():
            score += 2
    if "提前批" in text:
        score += 4
    if "秋招" in text:
        score += 3
    if "校招" in text:
        score += 2
    return score


def default_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        # Some career sites return brotli responses that can trip local decoders.
        "Accept-Encoding": "gzip, deflate",
    }


def fetch(client: httpx.Client, url: str, **kwargs: Any) -> str:
    resp = client.get(url, timeout=20, follow_redirects=True, **kwargs)
    resp.raise_for_status()
    return resp.text


def search_bing(client: httpx.Client, query: str, source_name: str, keyword: str, cfg: dict[str, Any]) -> list[Hit]:
    """抓取 Bing 搜索结果页。若不稳定，可替换为 SerpAPI、Bing Search API 等正式搜索 API。"""
    url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=zh-CN&cc=CN"
    html = fetch(client, url)
    soup = BeautifulSoup(html, "html.parser")
    hits: list[Hit] = []

    for item in soup.select("li.b_algo")[:10]:
        a = item.select_one("h2 a")
        if not a:
            continue
        title = clean_text(a.get_text(" "))
        link = a.get("href") or ""
        snippet = clean_text(item.get_text(" "))
        full_text = f"{title} {snippet}"
        score = score_hit(full_text, cfg["companies"], cfg.get("hot_words", []))
        if score <= 0:
            continue
        hits.append(Hit(source=source_name, title=title, url=link, snippet=snippet, keyword=keyword, score=score))
    return hits


def monitor_public_search(client: httpx.Client, cfg: dict[str, Any]) -> list[Hit]:
    hits: list[Hit] = []
    for site in cfg.get("search_sites", []):
        for keyword in cfg.get("keywords", []):
            company_part = " OR ".join(cfg.get("companies", [])[:8])
            query = f"site:{site} ({company_part}) {keyword}"
            try:
                hits.extend(search_bing(client, query, f"搜索:{site}", keyword, cfg))
                time.sleep(0.8)
            except Exception as e:
                print(f"[WARN] 搜索失败 {site} {keyword}: {e}", file=sys.stderr)
    return hits


def monitor_career_pages(client: httpx.Client, cfg: dict[str, Any]) -> list[Hit]:
    hits: list[Hit] = []
    keywords = cfg.get("keywords", []) + cfg.get("hot_words", [])
    for name, url in cfg.get("career_pages", {}).items():
        try:
            html = fetch(client, url)
            soup = BeautifulSoup(html, "html.parser")
            title = clean_text(soup.title.get_text(" ") if soup.title else name)
            text = clean_text(soup.get_text(" "))
            matched = [k for k in keywords if k.lower() in text.lower()]
            if not matched:
                # 有些官网是前端渲染，HTML 里可能没内容；仍保留标题弱信号
                matched = [k for k in ["校招", "校园招聘"] if k in title]
            if matched:
                score = score_hit(f"{title} {text}", cfg["companies"], cfg.get("hot_words", [])) + 2
                hits.append(Hit(source="官网", title=f"{name}: {title}", url=url, snippet=text[:240], keyword=matched[0], score=score))
            time.sleep(0.5)
        except Exception as e:
            print(f"[WARN] 官网检查失败 {name}: {e}", file=sys.stderr)
    return hits


def dedupe_hits(hits: Iterable[Hit], seen: set[str]) -> list[Hit]:
    fresh: list[Hit] = []
    local_seen: set[str] = set()
    for h in sorted(hits, key=lambda x: x.score, reverse=True):
        if h.id in seen or h.id in local_seen:
            continue
        local_seen.add(h.id)
        fresh.append(h)
    return fresh


def format_message(hits: list[Hit], max_items: int) -> str:
    if not hits:
        return "今天没有发现新的互联网大厂秋招提前批线索。"
    lines = [f"发现 {len(hits)} 条新的秋招提前批线索，优先展示前 {min(len(hits), max_items)} 条："]
    for i, h in enumerate(hits[:max_items], 1):
        lines.append(
            f"\n{i}. [{h.source}] {h.title}\n"
            f"关键词：{h.keyword}｜评分：{h.score}\n"
            f"链接：{h.url}\n"
            f"摘要：{h.snippet[:180]}"
        )
    return "\n".join(lines)


def post_json(client: httpx.Client, url: str, payload: dict[str, Any]) -> None:
    resp = client.post(url, json=payload, timeout=20)
    resp.raise_for_status()


def notify(client: httpx.Client, cfg: dict[str, Any], message: str) -> None:
    notify_cfg = cfg.get("notify", {})
    feishu = notify_cfg.get("feishu_webhook")
    wecom = notify_cfg.get("wecom_webhook")

    if feishu:
        post_json(client, feishu, {"msg_type": "text", "content": {"text": message}})
    if wecom:
        post_json(client, wecom, {"msgtype": "text", "text": {"content": message}})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写入 seen，不发通知")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)
    seen_path = Path(cfg.get("storage", {}).get("seen_db", "./seen.json"))
    if not seen_path.is_absolute():
        seen_path = cfg_path.parent / seen_path

    with httpx.Client(headers=default_headers()) as client:
        all_hits = []
        all_hits.extend(monitor_public_search(client, cfg))
        all_hits.extend(monitor_career_pages(client, cfg))

        seen = load_seen(seen_path)
        fresh = dedupe_hits(all_hits, seen)
        max_items = int(cfg.get("notify", {}).get("max_items", 20))
        message = format_message(fresh, max_items)
        print(message)

        if not args.dry_run:
            for h in fresh:
                seen.add(h.id)
            save_seen(seen_path, seen)
            if fresh:
                notify(client, cfg, message)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
