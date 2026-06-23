#!/usr/bin/env python3
"""
秋招提前批监控 —— 基于 Spider_XHS 采集小红书。

做的事：
1. 用 Spider_XHS 的签名搜索接口，按关键词搜最近一周的小红书笔记。
2. 按「大厂名 + 提前批/网申/内推」给每条笔记打分，过滤出招聘相关。
3. 跟 seen.json 去重，只保留「新增」线索。
4. 可选 --detail：对高分命中再拉笔记正文确认。
5. 落本地文件：
   - recruit_out/logs/check-YYYY-MM-DD.md   每次运行的快照
   - recruit_out/2027提前批进展.md           滚动更新的公司总表
   - recruit_out/seen.json                   去重库
   - recruit_out/progress.json               每家公司的最新状态（机器用）

用法（在 Spider_XHS 目录下运行）：
    python xhs_recruit_collect.py                # 正常跑，写入去重
    python xhs_recruit_collect.py --dry-run      # 只打印，不写 seen
    python xhs_recruit_collect.py --detail       # 对高分命中拉正文确认
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import load_env
from xhs_utils.data_util import handle_note_info

# Windows 控制台默认 gbk，强制 stdout/stderr 用 utf-8，避免 emoji/中文报错
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# 收敛 loguru 输出：去掉默认那种满屏变量栈（diagnose/backtrace）
logger.remove()
logger.add(sys.stderr, level="INFO", backtrace=False, diagnose=False,
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "recruit_out"
LOG_DIR = OUT_DIR / "logs"


@dataclass
class Hit:
    note_id: str
    title: str
    desc: str
    url: str
    nickname: str
    liked: str
    keyword: str
    companies: list[str]
    score: int
    upload_time: str = ""
    note_time: int = 0  # 毫秒时间戳，用于排序

    def line(self) -> str:
        comp = "、".join(self.companies) if self.companies else "—"
        body = (
            f"- **[{self.score}分] {self.title}**\n"
            f"  - 公司：{comp}｜关键词：{self.keyword}｜👍{self.liked}｜作者：{self.nickname}\n"
            f"  - 链接：{self.url}"
        )
        if self.desc:
            snippet = self.desc.replace("\n", " ").strip()[:160]
            body += f"\n  - 摘要：{snippet}"
        return body


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def dig(d: Any, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def score_text(text: str, companies: list[str], hot_words: list[str]) -> tuple[int, list[str]]:
    score = 0
    matched: list[str] = []
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


def build_note_url(note_id: str, xsec_token: str) -> str:
    token = f"&xsec_token={xsec_token}" if xsec_token else ""
    return f"https://www.xiaohongshu.com/explore/{note_id}?xsec_source=pc_search{token}"


def collect(cfg: dict[str, Any], cookies: str, want_detail: bool) -> list[Hit]:
    apis = XHS_Apis()
    companies = cfg.get("companies", [])
    hot_words = cfg.get("hot_words", [])
    s = cfg.get("search", {})
    require_num = int(s.get("require_num", 20))
    sort_choice = int(s.get("sort_type_choice", 1))
    note_time = int(s.get("note_time", 2))
    note_type = int(s.get("note_type", 0))
    min_score = int(s.get("min_score", 4))
    detail_threshold = int(s.get("detail_threshold", 7))
    # 请求间隔：随机抖动，更像真人。兼容旧的 sleep_seconds。
    _legacy = s.get("sleep_seconds")
    sleep_min = float(s.get("sleep_min", _legacy if _legacy is not None else 3.0))
    sleep_max = float(s.get("sleep_max", _legacy if _legacy is not None else 6.5))
    max_detail = int(s.get("max_detail", 5))

    def nap() -> None:
        time.sleep(random.uniform(min(sleep_min, sleep_max), max(sleep_min, sleep_max)))

    proxies = {"http": cfg["proxy"], "https": cfg["proxy"]} if cfg.get("proxy") else None

    best: dict[str, Hit] = {}  # note_id -> 最高分的 Hit
    ok_count = 0  # 成功且有返回的关键词数（用于识别整体被限流）

    for keyword in cfg.get("keywords", []):
        try:
            success, msg, notes = apis.search_some_note(
                keyword, require_num, cookies, sort_choice, note_type, note_time, 0, 0, "", proxies
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"搜索失败 [{keyword}]: {e}")
            nap()
            continue
        if not success:
            logger.warning(f"搜索未成功 [{keyword}]: {msg}")
            nap()
            continue

        notes = [n for n in notes if n.get("model_type") == "note"]
        if notes:
            ok_count += 1
        logger.info(f"关键词 [{keyword}] 命中笔记 {len(notes)} 条")
        for n in notes:
            note_id = n.get("id", "")
            if not note_id:
                continue
            xsec = n.get("xsec_token", "")
            title = dig(n, "note_card", "display_title", default="") or ""
            nickname = dig(n, "note_card", "user", "nickname", default="") or ""
            liked = str(dig(n, "note_card", "interact_info", "liked_count", default="") or "")
            text = title
            score, matched = score_text(text, companies, hot_words)
            if score < min_score:
                continue
            url = build_note_url(note_id, xsec)
            hit = Hit(
                note_id=note_id, title=title or "（无标题）", desc="", url=url,
                nickname=nickname, liked=liked, keyword=keyword, companies=matched, score=score,
            )
            prev = best.get(note_id)
            if prev is None or hit.score > prev.score:
                best[note_id] = hit
        nap()

    hits = sorted(best.values(), key=lambda h: h.score, reverse=True)

    if want_detail:
        detail_done = 0
        for h in hits:
            if h.score < detail_threshold:
                continue
            if detail_done >= max_detail:
                logger.info(f"已达 detail 上限 {max_detail} 条，跳过剩余正文拉取")
                break
            detail_done += 1
            try:
                ok, msg, res = apis.get_note_info(h.url, cookies, proxies)
                if ok and dig(res, "data", "items"):
                    raw = res["data"]["items"][0]
                    raw["url"] = h.url
                    info = handle_note_info(raw)
                    h.desc = info.get("desc", "")
                    h.upload_time = info.get("upload_time", "")
                    # 用正文重新打分（取更高者）
                    full = f"{h.title} {h.desc}"
                    new_score, matched = score_text(full, cfg.get("companies", []), cfg.get("hot_words", []))
                    if new_score > h.score:
                        h.score = new_score
                        h.companies = matched
            except Exception as e:  # noqa: BLE001
                logger.debug(f"拉正文失败 {h.note_id}: {e}")
            nap()
        hits = sorted(hits, key=lambda h: h.score, reverse=True)

    return hits, ok_count


def update_progress(progress: dict[str, Any], fresh: list[Hit], today: str) -> tuple[dict[str, Any], list[str]]:
    """按公司维度记录最新/最强信号。返回 (progress, 本次首次出现信号的公司列表)。"""
    new_companies: list[str] = []
    for h in fresh:
        for comp in h.companies:
            cur = progress.get(comp)
            if cur is None and comp not in new_companies:
                new_companies.append(comp)  # 这家公司之前从没出现过信号 = 新开
            if cur is None or h.score >= cur.get("score", 0):
                progress[comp] = {
                    "score": h.score,
                    "title": h.title,
                    "url": h.url,
                    "keyword": h.keyword,
                    "liked": h.liked,
                    "first_seen": cur.get("first_seen", today) if cur else today,
                    "updated": today,
                }
    return progress, new_companies


def render_progress_md(progress: dict[str, Any], companies: list[str]) -> str:
    lines = [
        "# 2027届互联网大厂秋招提前批 · 进展总表",
        "",
        f"> 最近更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}（数据源：小红书搜索，仅供参考，以官方为准）",
        "",
        "| 公司 | 最新信号 | 关键词 | 👍 | 首次发现 | 更新 | 链接 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    # 已有信号的公司在前，按更新时间倒序
    seen_comps = sorted(progress.keys(), key=lambda c: progress[c].get("updated", ""), reverse=True)
    for comp in seen_comps:
        p = progress[comp]
        title = p.get("title", "").replace("|", "／")[:40]
        lines.append(
            f"| {comp} | {title} | {p.get('keyword','')} | {p.get('liked','')} | "
            f"{p.get('first_seen','')} | {p.get('updated','')} | [看笔记]({p.get('url','')}) |"
        )
    # 还没信号的公司
    rest = [c for c in companies if c not in progress]
    for comp in rest:
        lines.append(f"| {comp} | — 暂无线索 — |  |  |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def render_snapshot_md(fresh: list[Hit], all_hits: list[Hit], today: str, dry: bool) -> str:
    lines = [
        f"# 提前批监控快照 · {today}",
        "",
        f"> 本次共命中 {len(all_hits)} 条相关笔记，其中**新增 {len(fresh)} 条**。"
        + ("（dry-run，未写入去重）" if dry else ""),
        "",
    ]
    if fresh:
        lines.append("## 🆕 新增线索（按评分高到低）")
        lines.append("")
        for h in fresh:
            lines.append(h.line())
            lines.append("")
    else:
        lines.append("## 🆕 新增线索")
        lines.append("")
        lines.append("本次没有发现新的提前批线索。")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="基于 Spider_XHS 的秋招提前批监控")
    parser.add_argument("--config", default=str(ROOT / "recruit_config.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写 seen / 不更新总表")
    parser.add_argument("--detail", action="store_true", help="对高分命中拉取笔记正文确认")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    cookies = load_env()
    if not cookies or not cookies.strip():
        print("❌ 未配置小红书 Cookie。请在 Spider_XHS/.env 里填写 COOKIES='...'（登录后的 cookie）。")
        return 2
    # 清洗 cookie：去掉换行/回车/首尾空白，避免 requests 报 Invalid header value
    cookies = cookies.replace("\r", "").replace("\n", "").strip()

    today = datetime.now().strftime("%Y-%m-%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    seen_path = OUT_DIR / "seen.json"
    progress_path = OUT_DIR / "progress.json"
    seen = set(load_json(seen_path, []))
    progress = load_json(progress_path, {})

    all_hits, ok_count = collect(cfg, cookies, args.detail)

    # 所有关键词都没采到内容 = 多半被小红书限流；不要用空结果覆盖今天已有的好数据
    if ok_count == 0:
        print("⚠️ 所有关键词都没采到内容，多半是被小红书限流了。")
        print("   建议：过一段时间（比如几小时后）再跑；不要短时间内反复执行。")
        print("   本次不写入、不覆盖已有文件。")
        save_json(OUT_DIR / "new_companies.json", [])
        (OUT_DIR / "notify_message.txt").write_text("", "utf-8")
        return 0

    fresh = [h for h in all_hits if h.note_id not in seen]

    snapshot = render_snapshot_md(fresh, all_hits, today, args.dry_run)
    print(snapshot)

    if not args.dry_run:
        (LOG_DIR / f"check-{today}.md").write_text(snapshot, "utf-8")
        for h in fresh:
            seen.add(h.note_id)
        save_json(seen_path, sorted(seen))
        progress, new_companies = update_progress(progress, fresh, today)
        save_json(progress_path, progress)
        save_json(OUT_DIR / "new_companies.json", new_companies)
        # 给 run_daily.ps1 用的现成通知文案（UTF-8），避免在 ps1 里写中文
        notify_msg = (
            f"提前批新开：{'、'.join(new_companies)}（详情见 2027提前批进展.md）"
            if new_companies else ""
        )
        (OUT_DIR / "notify_message.txt").write_text(notify_msg, "utf-8")
        (OUT_DIR / "2027提前批进展.md").write_text(
            render_progress_md(progress, cfg.get("companies", [])), "utf-8"
        )
        print(f"\n✅ 已写入：{LOG_DIR / f'check-{today}.md'}")
        print(f"✅ 已更新总表：{OUT_DIR / '2027提前批进展.md'}")
        if new_companies:
            print(f"🔔 本次新开：{'、'.join(new_companies)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
