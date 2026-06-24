# 秋招提前批监控 · 搭建说明

每天自动监控**小红书 + 抖音**上「互联网大厂秋招提前批」的动静，发现新公司开批时弹 Windows 通知，并汇总成一张总表。

> 本仓库**只含自己写的封装代码**，不含第三方爬虫本体（Spider_XHS / MediaCrawler）。
> 按下面步骤把两个爬虫各自 clone 下来、打几处小补丁、放入封装脚本即可。

## 本仓库自己的文件

| 文件 | 作用 |
| --- | --- |
| `Spider_XHS/xhs_recruit_collect.py` | 小红书采集封装（搜索→打分→去重→落本地） |
| `Spider_XHS/recruit_config.yaml` | 关键词 / 公司 / 加分词 / 搜索参数（**两边共用的打分口径**） |
| `Spider_XHS/run_daily.ps1` | 每日定时入口：跑小红书+抖音→合表→弹通知 |
| `MediaCrawler/dy_recruit_collect.py` | 抖音采集封装（调 MediaCrawler→打分→去重→落本地） |
| `build_master.py` | 合并两边进展，生成总表 + 统一「新开公司」通知 |
| `recruit_monitor/` | 早期版本（靠 Bing 收录搜索，无风控风险，可作兜底） |

---

## 一、小红书（Spider_XHS）

```bash
git clone https://github.com/cv-cat/Spider_XHS.git
cd Spider_XHS
pip install -r requirements.txt
npm install                       # 签名算法要 Node 跑
```

**打补丁**：`apis/xhs_pc_apis.py` 里有 18 处
```python
success, msg = res_json["success"], res_json["msg"]
```
全部改成（限流时返回里没有 `msg`，原代码会 KeyError 崩）：
```python
success, msg = res_json.get("success", False), res_json.get("msg", "")
```

把本仓库的 `xhs_recruit_collect.py`、`recruit_config.yaml`、`run_daily.ps1`、`README_招聘监控.md` 放进 `Spider_XHS/`。

**配 cookie**：新建 `Spider_XHS/.env`：
```
COOKIES='登录小红书后从浏览器复制的整段 cookie'
```

跑：`python xhs_recruit_collect.py --dry-run`

---

## 二、抖音（MediaCrawler）

```bash
git clone https://github.com/NanmiCoder/MediaCrawler.git
cd MediaCrawler
python -m venv .venv                          # 必须独立 venv，它把 pydantic/httpx 钉死老版本
.venv\Scripts\python -m pip install -r requirements.txt pyyaml
.venv\Scripts\python -m playwright install chromium
```

**打补丁**：
- `config/base_config.py`：`ENABLE_CDP_MODE = False`、`ENABLE_GET_COMMENTS = False`、`SAVE_DATA_OPTION = "json"`
- `config/dy_config.py`：`PUBLISH_TIME_TYPE = 7`（只要近一周，过滤往年爆款老视频）
- `media_platform/douyin/core.py`：把 `await self.context_page.goto(self.index_url)` 改成
  `await self.context_page.goto(self.index_url, wait_until="domcontentloaded", timeout=60000)`（抖音首页等 load 会 30s 超时）

把本仓库的 `dy_recruit_collect.py` 放进 `MediaCrawler/`。

**配 cookie**：新建 `MediaCrawler/.dy_cookie.txt`，粘贴登录抖音后的整段 cookie。

首次跑要显示浏览器登录（登录态存 `browser_data/`，之后可无头）：
```
.venv\Scripts\python dy_recruit_collect.py --show --dry-run
```

---

## 三、合表 + 每日定时

`build_master.py` 读两边的 `progress.json`，生成 `recruit_out/总表-2027提前批.md`。

每日定时（Windows 任务计划程序）：
```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -ExecutionPolicy Bypass -File "<仓库路径>\Spider_XHS\run_daily.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 9:30am
Register-ScheduledTask -TaskName "XHS_Recruit_Monitor" -Action $action -Trigger $trigger -Force
```

> ⚠️ `run_daily.ps1` 和 `build_master.py` 里写死了**本机路径**（python venv 路径、`E:\Node`、`f:\recruit_monitor`）。换机器要改成你自己的路径。

---

## 注意

- cookie / `browser_data/` / `data/` / 各 `recruit_out`、`dy_out` 产物都已被 `.gitignore` 忽略，不会上传。
- 仅用于**个人监控公开招聘信息**；别高频跑、别规模化，降低封号风险。一切以官方校招页为准。
- MediaCrawler 为「非商业学习授权」，请遵守其 LICENSE，勿商用。
