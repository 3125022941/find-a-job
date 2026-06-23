# 秋招提前批每日监控脚本

这个脚本用于每天监控“互联网大厂秋招提前批/校招提前批”相关信息。

它不会绕过小红书/抖音登录或风控，而是采用更稳妥的方式：

1. 通过公开搜索结果监控 `xiaohongshu.com`、`douyin.com`、牛客、脉脉、B站等站点被收录的内容。
2. 直接检查大厂官方校招页面。
3. 使用 `seen.json` 去重，避免重复提醒。
4. 支持飞书、企业微信机器人推送。

## 安装

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，按需修改公司、关键词、站点、Webhook。

## 运行

```bash
python recruit_monitor.py --config config.yaml
```

测试运行，不写入去重、不发通知：

```bash
python recruit_monitor.py --config config.yaml --dry-run
```

## 每天自动运行

macOS/Linux 使用 crontab：

```bash
crontab -e
```

每天早上 9 点运行：

```cron
0 9 * * * cd /你的路径/recruit_monitor && /usr/bin/python3 recruit_monitor.py --config config.yaml >> monitor.log 2>&1
```

## 建议关键词

- 秋招提前批
- 2027届 提前批
- 校招提前批
- 网申开启
- 内推码
- 研发提前批
- 算法提前批
- 后端提前批
- 产品经理提前批

## 注意

小红书和抖音对自动化访问限制较强。生产使用建议：

- 优先监控官方招聘页、牛客、公众号文章、B站动态、网页搜索结果。
- 不建议做 Cookie 抓取、接口逆向或绕风控。
- 如需要更稳定的搜索结果，可把 `search_bing()` 替换为 Bing Search API、SerpAPI、Tavily 等正式搜索 API。
