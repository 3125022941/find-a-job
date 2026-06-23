# 秋招提前批监控（基于 Spider_XHS 采集小红书）

在原版 Spider_XHS 之上加了一层招聘监控封装：
- `recruit_config.yaml` —— 关键词 / 公司 / 加分词 / 搜索参数
- `xhs_recruit_collect.py` —— 采集 + 打分 + 去重 + 落本地文件

## 一、配置 Cookie（只需一次）

1. 浏览器登录小红书 `https://www.xiaohongshu.com`
2. 按 `F12` → 网络(Network) → Fetch/XHR → 随便点一个请求 → 复制请求头里的 `cookie` 整段
3. 打开 `Spider_XHS/.env`，填进去：

   ```
   COOKIES='把整段cookie粘到这里'
   ```

> Cookie 有时效，失效后重新获取。建议用小号、一天最多跑 1~2 次，降低风控风险。

## 二、运行

在 `Spider_XHS` 目录下：

```bash
# 正常跑：采集 + 写入去重 + 更新总表
python xhs_recruit_collect.py

# 试跑：只打印，不写去重（第一次建议先这个）
python xhs_recruit_collect.py --dry-run

# 加强：对高分命中再拉笔记正文确认（请求更多，慎用）
python xhs_recruit_collect.py --detail
```

## 三、产出文件（都在 `Spider_XHS/recruit_out/`）

| 文件 | 用途 |
| --- | --- |
| `logs/check-YYYY-MM-DD.md` | 每次运行的快照（新增线索列表） |
| `2027提前批进展.md` | 滚动更新的公司总表：哪家有动静、最新信号、链接 |
| `seen.json` | 去重库（已提醒过的笔记 id） |
| `progress.json` | 每家公司最新状态（程序用） |

## 四、调参

改 `recruit_config.yaml`：
- `keywords` 别加太多，每个都会发一次搜索请求
- `search.note_time`：2=一周内，1=一天内
- `search.min_score`：调高可减少噪音
- `search.sleep_seconds`：每次请求间隔，越大越安全

## 五、风险提醒

- Spider_XHS 逆向了小红书风控签名，平台一更新可能失效，需跟仓库更新。
- 用自己 cookie 高频抓取有**限流/封号**风险。仅作个人监控公开招聘信息用，别规模化。
